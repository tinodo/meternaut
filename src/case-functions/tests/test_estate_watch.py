"""The Watch reads every subscription that its own identity can read: the list of subscriptions (scope.py), the reading of many of them (detectors.collect_estate) and the run
(run.execute).

No test calls Azure. A fake tenant answers every call of the app, and a fake clock moves with the calls, so that the share of the deadline can be used up on purpose. The ids are made up.
"""
import json
import re
import unittest
from dataclasses import replace
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from support import ENV, NOW, SUBSCRIPTION, TOKEN, FakeEstate, Ticker, disk_row, run_watch
from test_http import Script, ok
from test_investigate import FakeFoundry, FakeToolbox
from test_run_loop import Moving, loop_for
from test_web_support import Console
from cases import arm as arm_module
from cases import config, detectors, events as events_module, investigate, run, scope
from cases.arm import Arm
from cases.http import Client, HttpError, allowed_calls
from cases.identity import IdentityError
from cases.redact import Redactor

ALL = {**ENV, "SCOPE_ALL_SUBSCRIPTIONS": "true"}
ALL_NO_LIST = {key: value for key, value in ALL.items() if key != "SCOPE_SUBSCRIPTIONS"}
ARM = "https://management.azure.com"


def sub_id(n: int) -> str:
    return f"{n:08x}-1111-4222-8333-444444444444"


def item(sub: str, state: str = "Enabled", **changes) -> dict:
    found = {"id": f"/subscriptions/{sub}", "subscriptionId": sub, "displayName": "An example subscription", "state": state, "tenantId": "00000000-0000-0000-0000-000000000000"}
    found.update(changes)
    return found


def disk_in(sub: str, name: str, group: str = "rg-app", **changes) -> dict:
    return disk_row(name, group, id=f"/subscriptions/{sub}/resourceGroups/{group}/providers/Microsoft.Compute/disks/{name}", subscriptionId=sub, **changes)


class Tenant(FakeEstate):
    """A fake tenant: the subscriptions that the identity can read, and what each of them holds. Resource Graph answers for the subscriptions that a query names (a row says which
    one it is in), and every call that is for one subscription answers from the lists of that subscription. What FakeEstate answers, it answers still (the model, the locks of a scope)."""

    PER_SUBSCRIPTION = re.compile(r"^/subscriptions/([^/]+)/providers/microsoft\.(costmanagement/query|advisor/recommendations|authorization/locks)$")
    GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    def __init__(self, subscriptions=()):
        super().__init__()
        self.listed = [item(sub) for sub in subscriptions]
        self.page_size = None
        self.costs_of: dict[str, list] = {}
        self.advisor_of: dict[str, list] = {}
        self.locks_of: dict[str, list] = {}
        self.broken: dict[tuple[str, str], object] = {}  # (source, subscription) -> a status, or a list of them, one for each call
        self.on_call = None  # called with the method and the path of each call that this fake answers itself: it moves a clock
        self.leaky = False  # True: Resource Graph answers with the rows of every subscription, not only of those that the query names
        self.retry_after = 1  # what a 429 asks for
        self.graph_calls: list[tuple[str, list[str]]] = []

    # -- the answers ---------------------------------------------------------------------------------------------------------------------------
    def _record(self, method, url, headers, body, timeout):
        if self.first_call and not self.calls:
            self.first_call()
        parts = urlsplit(url)
        self.calls.append({"method": method, "url": url, "host": parts.netloc, "path": parts.path, "headers": dict(headers), "body": body, "timeout": timeout})

    def _refused(self, status):
        return status, ({"retry-after": str(self.retry_after)} if status == 429 else {}), b'{"error":{"code":"Failed","message":"boom"}}'

    def _trouble(self, source, sub=None):
        planned = self.broken.get((source, sub)) if sub else None
        if isinstance(planned, list):
            planned = planned.pop(0) if planned else None
        return planned or self._failure(source)

    @classmethod
    def _owner(cls, row):
        for value in (row.get("subscriptionId"), row.get("id"), row.get("targetId")):
            text = str(value or "").strip().lower()
            found = detectors.SUBSCRIPTION_OF_ID.match(text)
            candidate = found.group(1) if found else text
            if cls.GUID.match(candidate):
                return candidate
        return None

    def __call__(self, method, url, headers, data, timeout):
        parts = urlsplit(url)
        path = parts.path.lower()
        body = json.loads(data.decode("utf-8")) if data else None
        mine = self.PER_SUBSCRIPTION.match(path)
        if not (path == "/subscriptions" or path.endswith("/providers/microsoft.resourcegraph/resources") or mine):
            return super().__call__(method, url, headers, data, timeout)
        self._record(method, url, headers, body, timeout)
        if self.on_call:
            self.on_call(method, path)
        if path == "/subscriptions":
            return self._list(parts)
        if mine is None:
            return self._graph(body)
        sub, source = mine.groups()
        short = {"costmanagement/query": "costs", "advisor/recommendations": "advisor", "authorization/locks": "locks"}[source]
        failed = self._trouble(short, sub)
        if failed:
            return self._refused(failed)
        if short == "costs":
            rows = [[cost, rid, self.currency] for cost, rid in self.costs_of.get(sub, [])]
            return self._json({"properties": {"columns": [{"name": "Cost"}, {"name": "ResourceId"}, {"name": "Currency"}], "rows": rows}})
        return self._json({"value": (self.advisor_of if short == "advisor" else self.locks_of).get(sub, [])})

    def _list(self, parts):
        failed = self._trouble("subscriptions")
        if failed:
            return self._refused(failed)
        start = int(parse_qs(parts.query).get("$skiptoken", ["0"])[0])
        size = self.page_size or len(self.listed) or 1
        document = {"value": self.listed[start:start + size]}
        if start + size < len(self.listed):
            document["nextLink"] = f"{ARM}/subscriptions?api-version=2022-12-01&$skiptoken={start + size}"
        return self._json(document)

    def _graph(self, body):
        name = re.match(r"// meternaut:(\S+)", body["query"]).group(1)
        self.graph_calls.append((name, list(body["subscriptions"])))
        failed = self._trouble(f"graph:{name}")
        if failed:
            return self._refused(failed)
        wanted = {sub.lower() for sub in body["subscriptions"]}
        rows = [row for row in self.graph.get(name, []) if self.leaky or self._owner(row) is None or self._owner(row) in wanted]
        return self._json({"count": len(rows), "data": rows})

    # -- what the tests ask --------------------------------------------------------------------------------------------------------------------
    def asked(self, word):
        return [c for c in self.calls if word in c["path"].lower()]

    def read_subscriptions(self, word):
        """The subscriptions for which a call of the kind was made, in the order of the calls."""
        return [re.match(r"/subscriptions/([^/]+)/", c["path"].lower()).group(1) for c in self.asked(word)]


def arm_for(*answers):
    script = Script(*answers)
    return Arm(Client(allowed_calls(), Redactor(), transport=script, sleep=lambda s: None, jitter=lambda: 0.5), lambda resource: TOKEN), script


def of_type(events, kind):
    return [e for e in events if e["type"] == kind]


def settings(**changes):
    return replace(config.load(ENV), **changes)


class StubArm:
    def __init__(self, items=None, error=None):
        self.items, self.error, self.calls = items, error, 0

    def subscriptions(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.items


# -- the list of the subscriptions of the identity ----------------------------------------------------------------------------------------------------

class TheListOfSubscriptionsOfAzure(unittest.TestCase):
    def test_the_list_is_one_get_with_the_version_of_the_api_and_the_token_of_the_identity(self):
        arm, script = arm_for(ok({"value": [item(sub_id(1)), item(sub_id(2))]}))
        self.assertEqual([found["subscriptionId"] for found in arm.subscriptions()], [sub_id(1), sub_id(2)])
        ((method, url, headers, data, _),) = script.calls
        self.assertEqual((method, url, data), ("GET", f"{ARM}/subscriptions?api-version=2022-12-01", None))
        self.assertIn("Authorization", headers)

    def test_the_next_page_is_followed_on_the_same_host_and_the_same_path_and_every_page_is_read(self):
        second = f"{ARM}/subscriptions?api-version=2022-12-01&$skiptoken=page2"
        arm, script = arm_for(ok({"value": [item(sub_id(1))], "nextLink": second}), ok({"value": [item(sub_id(2))]}))
        self.assertEqual([found["subscriptionId"] for found in arm.subscriptions()], [sub_id(1), sub_id(2)])
        self.assertEqual([call[1] for call in script.calls], [f"{ARM}/subscriptions?api-version=2022-12-01", second])

    def test_a_link_to_another_host_scheme_port_or_path_is_not_followed(self):
        for link in ("https://evil.example/subscriptions?api-version=2022-12-01", "http://management.azure.com/subscriptions?x=1", "https://management.azure.com:8443/subscriptions?x=1",
                     f"{ARM}/subscriptions/{sub_id(1)}/resourcegroups?x=1", f"{ARM}/tenants?x=1", f"{ARM}.evil.example/subscriptions?x=1", "ftp://management.azure.com/subscriptions"):
            arm, script = arm_for(ok({"value": [item(sub_id(1))], "nextLink": link}), ok({"value": [item(sub_id(2))]}))
            with self.assertRaises(HttpError, msg=link) as raised:
                arm.subscriptions()
            self.assertIn("does not understand", str(raised.exception))
            self.assertEqual(len(script.calls), 1, f"{link}: nothing was called")

    def test_a_list_that_never_ends_is_read_up_to_the_page_cap_and_then_refused(self):
        link = f"{ARM}/subscriptions?api-version=2022-12-01&$skiptoken=again"
        arm, script = arm_for(ok({"value": [item(sub_id(1))], "nextLink": link}))
        with self.assertRaises(HttpError) as raised:
            arm.subscriptions()
        self.assertEqual(len(script.calls), arm_module.SUBSCRIPTION_PAGES)
        self.assertIn("more than", str(raised.exception))

    def test_an_answer_that_is_not_a_list_is_refused_and_an_item_that_is_not_an_object_is_left_out(self):
        for document in ([], {"value": "x"}, "text", None):
            arm, _ = arm_for(ok(document) if document is not None else (200, {}, b""))
            with self.assertRaises(HttpError, msg=repr(document)):
                arm.subscriptions()
        arm, _ = arm_for(ok({"value": [item(sub_id(1)), "x", 5, None]}))
        self.assertEqual([found["subscriptionId"] for found in arm.subscriptions()], [sub_id(1)])

    def test_a_failure_of_the_call_is_an_http_error_and_a_throttled_one_is_waited_for_and_made_again(self):
        arm, _ = arm_for((403, {}, b'{"error":{"code":"AuthorizationFailed","message":"no"}}'))
        with self.assertRaises(HttpError) as raised:
            arm.subscriptions()
        self.assertEqual(raised.exception.status, 403)
        script = Script((429, {"retry-after": "3"}, b"{}"), ok({"value": [item(sub_id(1))]}))
        sleeps = []
        arm = Arm(Client(allowed_calls(), Redactor(), transport=script, sleep=sleeps.append, jitter=lambda: 0.5), lambda resource: TOKEN)
        self.assertEqual(len(arm.subscriptions()), 1)
        self.assertEqual(sleeps, [3.0])


class WhichSubscriptionsAreReadable(unittest.TestCase):
    def test_only_a_subscription_that_is_enabled_is_read_and_the_ids_are_lower_case_sorted_and_each_once(self):
        found = [item(sub_id(11).upper()), item(sub_id(1)), item(sub_id(2), "Disabled"), item(sub_id(4), "Warned"), item(sub_id(5), "PastDue"), item(sub_id(6), "Deleted"),
                 item(sub_id(1)), item(sub_id(7), "enabled"), item(sub_id(8), "ENABLED"), item(sub_id(9), None), item(sub_id(10), "")]
        self.assertEqual(scope.readable(found), [sub_id(1), sub_id(7), sub_id(8), sub_id(11)])

    def test_an_id_in_capitals_is_read_in_lower_case_and_is_the_same_subscription_as_its_lower_case_twin(self):
        capitals = "ABCDEF01-1111-4222-8333-ABCDEF012345"
        found = [item(capitals), item(capitals.lower()), item(sub_id(1)), {"id": f"/subscriptions/{capitals}", "state": "Enabled"}, {"subscriptionId": f" {capitals} ", "state": "Enabled"}]
        self.assertEqual(scope.readable(found), [sub_id(1), capitals.lower()], "sorted as text, lower case, each once")
        self.assertEqual(scope.resolve(StubArm([item(capitals)]), settings(all_subscriptions=True)).subscriptions, (capitals.lower(),))

    def test_the_id_comes_from_the_item_or_from_its_resource_id_and_what_is_not_an_id_is_left_out(self):
        found = [{"id": f"/subscriptions/{sub_id(2)}", "state": "Enabled"}, {"subscriptionId": sub_id(1), "state": "Enabled"}, {"subscriptionId": "not-a-guid", "state": "Enabled"},
                 {"id": "/subscriptions/not-a-guid", "state": "Enabled"}, {"state": "Enabled"}, {"subscriptionId": 5, "id": None, "state": "Enabled"},
                 {"subscriptionId": f" {sub_id(3)} ", "state": "Enabled"}, {"id": f"/subscriptions/{sub_id(4)}/resourceGroups/x", "state": "Enabled"}]
        self.assertEqual(scope.readable(found), [sub_id(1), sub_id(2), sub_id(3)])

    def test_nothing_in_the_list_is_nothing(self):
        self.assertEqual(scope.readable([]), [])
        self.assertEqual(scope.readable([item(sub_id(1), "Disabled")]), [])


class TheListThatTheRunReads(unittest.TestCase):
    def test_with_the_switch_off_it_is_the_list_of_the_setting_as_it_was_and_the_list_of_azure_is_not_asked_for(self):
        arm = StubArm([item(sub_id(1))])
        found = scope.resolve(arm, settings(subscriptions=(SUBSCRIPTION, sub_id(5), SUBSCRIPTION)))
        self.assertEqual((found.subscriptions, found.source, found.notes, arm.calls), ((SUBSCRIPTION, sub_id(5)), "setting", (), 0))

    def test_with_the_switch_off_and_no_list_there_is_nothing_to_read(self):
        with self.assertRaises(scope.ScopeError) as raised:
            scope.resolve(StubArm(), settings(subscriptions=()))
        self.assertIn("SCOPE_SUBSCRIPTIONS is empty", str(raised.exception))

    def test_with_the_switch_on_it_is_every_enabled_subscription_that_the_identity_lists_sorted(self):
        found = scope.resolve(StubArm([item(sub_id(3)), item(sub_id(1)), item(sub_id(14), "Disabled"), item(sub_id(14).upper())]), settings(all_subscriptions=True))
        self.assertEqual((found.subscriptions, found.source, found.notes), ((sub_id(1), sub_id(3), sub_id(14)), "estate", ()))

    def test_the_list_of_the_setting_does_not_limit_the_list_of_the_identity_it_is_only_the_fallback(self):
        found = scope.resolve(StubArm([item(sub_id(1))]), settings(all_subscriptions=True, subscriptions=(SUBSCRIPTION,)))
        self.assertEqual((found.subscriptions, found.source), ((sub_id(1),), "estate"))

    def test_when_the_list_cannot_be_had_the_list_of_the_setting_is_read_and_a_note_says_so(self):
        for error in (HttpError(500, "GET management.azure.com: 500 boom"), HttpError(403, "GET management.azure.com: 403 AuthorizationFailed"),
                      IdentityError("the managed identity endpoint gave no answer")):
            found = scope.resolve(StubArm(error=error), settings(all_subscriptions=True, subscriptions=(SUBSCRIPTION,)))
            self.assertEqual((found.subscriptions, found.source), ((SUBSCRIPTION,), "setting-fallback"), repr(error))
            (note,) = found.notes
            self.assertIn("could not be had", note)
            self.assertIn(str(error), note)
            self.assertIn("the 1 subscription of SCOPE_SUBSCRIPTIONS is read instead", note)

    def test_when_the_list_is_empty_or_has_nothing_enabled_the_list_of_the_setting_is_read_and_a_note_says_so(self):
        for items in ([], [item(sub_id(1), "Disabled")], [{"state": "Enabled"}]):
            found = scope.resolve(StubArm(items), settings(all_subscriptions=True, subscriptions=(SUBSCRIPTION, sub_id(5))))
            self.assertEqual((found.subscriptions, found.source), ((SUBSCRIPTION, sub_id(5)), "setting-fallback"), repr(items))
            self.assertEqual(found.notes, ("the identity can read no subscription that is enabled, so the 2 subscriptions of SCOPE_SUBSCRIPTIONS are read instead",))

    def test_when_the_list_cannot_be_had_and_there_is_no_list_of_the_setting_the_run_does_not_watch_nothing_in_silence(self):
        for arm, why in ((StubArm(error=HttpError(500, "boom")), "could not be had (boom)"), (StubArm([]), "can read no subscription that is enabled"),
                         (StubArm([item(sub_id(1), "Disabled")]), "can read no subscription that is enabled")):
            with self.assertRaises(scope.ScopeError) as raised:
                scope.resolve(arm, settings(all_subscriptions=True, subscriptions=()))
            self.assertIn(why, str(raised.exception))
            self.assertTrue(str(raised.exception).endswith("and SCOPE_SUBSCRIPTIONS is empty, so there is nothing to read"))

    def test_the_text_of_an_error_goes_through_the_redactor(self):
        found = scope.resolve(StubArm(error=HttpError(500, "boom with SECRET-VALUE")), settings(all_subscriptions=True, subscriptions=(SUBSCRIPTION,)),
                              redact=lambda text: str(text).replace("SECRET-VALUE", "[redacted]"))
        self.assertIn("boom with [redacted]", found.notes[0])
        self.assertNotIn("SECRET-VALUE", found.notes[0])

    def test_more_than_a_query_takes_are_cut_to_the_first_thousand_and_a_note_says_how_many_are_left_out(self):
        many = [item(sub_id(n)) for n in range(1, 1204)]
        found = scope.resolve(StubArm(many), settings(all_subscriptions=True))
        self.assertEqual(scope.MAX_SUBSCRIPTIONS, 1000, "what one Resource Graph query takes")
        self.assertEqual((len(found.subscriptions), found.subscriptions[0], found.subscriptions[-1], found.source), (1000, sub_id(1), sub_id(1000), "estate"))
        self.assertEqual(list(found.subscriptions), sorted(found.subscriptions))
        self.assertEqual(found.notes, ("the identity can read 1203 subscriptions and one query takes at most 1000: the first 1000 by id are read, the other 203 are not",))

    def test_exactly_a_thousand_are_not_cut_and_say_nothing(self):
        found = scope.resolve(StubArm([item(sub_id(n)) for n in range(1, 1001)]), settings(all_subscriptions=True))
        self.assertEqual((len(found.subscriptions), found.notes), (1000, ()))

    def test_the_subscription_where_meternaut_plants_its_own_waste_stays_in_when_the_list_is_cut(self):
        many = [item(sub_id(n)) for n in range(1, 1204)]
        found = scope.resolve(StubArm(many), settings(all_subscriptions=True), keep=sub_id(1100).upper())
        self.assertEqual((len(found.subscriptions), sub_id(1100) in found.subscriptions, sub_id(1000) in found.subscriptions), (1000, True, False))
        self.assertEqual(list(found.subscriptions), sorted(found.subscriptions))
        self.assertIn("the first 999 by id and the one where Meternaut plants its own waste", found.notes[0])
        inside = scope.resolve(StubArm(many), settings(all_subscriptions=True), keep=sub_id(20))
        self.assertEqual(inside.subscriptions[:20], tuple(sub_id(n) for n in range(1, 21)))
        self.assertIn("the first 1000 by id are read", inside.notes[0])
        missing = scope.resolve(StubArm(many), settings(all_subscriptions=True), keep=sub_id(5000))
        self.assertEqual(len(missing.subscriptions), 1000, "a subscription that the identity cannot read is not added")


# -- Resource Graph for a group of subscriptions -------------------------------------------------------------------------------------------------------

class ResourceGraphForSeveralSubscriptions(unittest.TestCase):
    PATH = f"{ARM}/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"

    def test_one_query_names_every_subscription_and_a_single_one_is_asked_as_it_always_was(self):
        arm, script = arm_for(ok({"data": [{"id": "a"}]}), ok({"data": [{"id": "b"}]}))
        self.assertEqual(arm.graph([sub_id(1), sub_id(2)], "q"), [{"id": "a"}])
        self.assertEqual(arm.graph(sub_id(3), "q"), [{"id": "b"}])
        bodies = [json.loads(call[3]) for call in script.calls]
        self.assertEqual([body["subscriptions"] for body in bodies], [[sub_id(1), sub_id(2)], [sub_id(3)]])
        self.assertTrue(all(call[1] == self.PATH for call in script.calls))

    def test_every_page_of_the_result_is_read_with_the_skip_token(self):
        arm, script = arm_for(ok({"data": [{"n": 1}], "$skipToken": "t1"}), ok({"data": [{"n": 2}], "$skipToken": "t2"}), ok({"data": [{"n": 3}]}))
        self.assertEqual(arm.graph_many([sub_id(1), sub_id(2)], "q"), [{"n": 1}, {"n": 2}, {"n": 3}])
        options = [json.loads(call[3])["options"] for call in script.calls]
        self.assertEqual([o.get("$skipToken") for o in options], [None, "t1", "t2"])
        self.assertEqual({o["$top"] for o in options}, {1000})

    def test_a_result_of_too_many_pages_is_asked_for_again_for_each_half_of_the_list_and_so_on_down_to_one_subscription(self):
        subs = [sub_id(n) for n in range(1, 5)]
        long = ok({"data": [{"n": 0}], "$skipToken": "more"})

        class Service:
            """Answers a query for more than one subscription with an endless result, and for one subscription with its own row."""

            def __init__(self):
                self.asked = []

            def __call__(self, method, url, headers, data, timeout):
                body = json.loads(data)
                self.asked.append(body["subscriptions"])
                if len(body["subscriptions"]) > 1:
                    return long
                return ok({"data": [{"subscriptionId": body["subscriptions"][0]}]})

        service = Service()
        arm = Arm(Client(allowed_calls(), Redactor(), transport=service, sleep=lambda s: None), lambda resource: TOKEN)
        rows = arm.graph_many(subs, "q")
        self.assertEqual([row["subscriptionId"] for row in rows], subs)
        self.assertEqual(service.asked[0], subs, "the first query was for the whole list")
        self.assertEqual(service.asked.count(subs[:2]) + service.asked.count(subs[2:]), 2 * arm_module.MAX_PAGES, "each half was tried until its pages were too many")
        self.assertEqual([asked for asked in service.asked if len(asked) == 1], [[sub] for sub in subs])

    def test_a_single_subscription_whose_result_is_too_long_is_refused_as_it_always_was(self):
        arm, script = arm_for(ok({"data": [{"n": 1}], "$skipToken": "again"}))
        with self.assertRaises(arm_module.TooManyPages) as raised:
            arm.graph_many([sub_id(1)], "q")
        self.assertIsInstance(raised.exception, HttpError)
        self.assertEqual((raised.exception.status, len(script.calls)), (0, arm_module.MAX_PAGES))
        self.assertIn(f"more than {arm_module.MAX_PAGES} pages", str(raised.exception))

    def test_any_other_failure_is_not_split_a_failure_of_the_whole_list_is_one_failure(self):
        for status in (400, 403, 429, 500):
            arm, script = arm_for((status, {}, b'{"error":{"code":"Failed","message":"boom"}}'))
            with self.assertRaises(HttpError) as raised:
                arm.graph_many([sub_id(1), sub_id(2), sub_id(3), sub_id(4)], "q")
            self.assertEqual(raised.exception.status, status)
            self.assertLessEqual(len(script.calls), 3, "retries of a call that may pass, and no query for the halves")
            self.assertTrue(all(len(json.loads(call[3])["subscriptions"]) == 4 for call in script.calls))


# -- the reading of many subscriptions --------------------------------------------------------------------------------------------------------------

def tenant_of(count, with_leads=True):
    subs = [sub_id(n) for n in range(1, count + 1)]
    tenant = Tenant(subs)
    for number, sub in enumerate(subs, 1):
        tenant.costs_of[sub] = [(float(number), f"/subscriptions/{sub}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/d{number}")]
    if with_leads:
        tenant.graph["orphan-managed-disk"] = [disk_in(sub, f"d{number}") for number, sub in enumerate(subs, 1)]
    return tenant, subs


def collect_all(tenant, subs, out_of_time=lambda: False, now=NOW):
    arm = Arm(Client(allowed_calls(), Redactor(), transport=tenant, sleep=lambda s: None, jitter=lambda: 0.5), lambda resource: TOKEN)
    notes: list[str] = []
    return detectors.collect_estate(arm, subs, now, notes, out_of_time), notes


class ManySubscriptionsAreReadInGroups(unittest.TestCase):
    def test_the_eight_queries_of_the_resource_graph_run_for_a_group_of_subscriptions_and_not_for_each_one(self):
        tenant, subs = tenant_of(120)
        estate, notes = collect_all(tenant, subs)
        self.assertEqual(detectors.GRAPH_CHUNK, 50, "Learn: groups of fewer than 300")
        self.assertEqual(len(tenant.graph_calls), 3 * 8, "three groups, eight queries each, not 960")
        self.assertEqual(sorted({len(asked) for _, asked in tenant.graph_calls}), [20, 50])
        self.assertEqual([asked for name, asked in tenant.graph_calls if name == "orphan-managed-disk"], [subs[:50], subs[50:100], subs[100:]])
        self.assertEqual(len(estate.contexts), 120)
        self.assertEqual(notes, [])

    def test_advisor_the_locks_and_the_cost_lines_are_read_for_each_subscription_once_in_the_order_of_the_list(self):
        tenant, subs = tenant_of(7)
        collect_all(tenant, subs)
        for word in ("advisor", "costmanagement", "authorization/locks"):
            self.assertEqual(tenant.read_subscriptions(word), subs, word)

    def test_every_lead_and_every_context_belongs_to_the_subscription_that_its_row_names(self):
        tenant, subs = tenant_of(3)
        tenant.graph["recent-creations"] = [{"targetId": f"/subscriptions/{subs[1]}/resourcegroups/rg-app/providers/microsoft.compute/disks/new"}]
        tenant.graph["managed-groups"] = [{"id": f"/subscriptions/{subs[2]}/resourcegroups/mc_cluster", "name": "mc_cluster"}]
        tenant.locks_of[subs[0]] = [{"id": f"/subscriptions/{subs[0]}/resourceGroups/rg-locked/providers/Microsoft.Authorization/locks/l"}]
        tenant.advisor_of[subs[1]] = [{"id": "rec", "properties": {"impact": "High", "impactedField": "Microsoft.Compute/virtualMachines", "impactedValue": "vm-one"}}]
        estate, _ = collect_all(tenant, subs)
        self.assertEqual({sub: sorted(lead.name for lead in found.leads) for sub, found in estate.collected.items()}, {subs[0]: ["d1"], subs[1]: ["d2", "vm-one"], subs[2]: ["d3"]})
        self.assertEqual({sub: context.recent for sub, context in estate.contexts.items()},
                         {subs[0]: set(), subs[1]: {f"/subscriptions/{subs[1]}/resourcegroups/rg-app/providers/microsoft.compute/disks/new"}, subs[2]: set()})
        self.assertEqual({sub: context.managed_groups for sub, context in estate.contexts.items()}, {subs[0]: set(), subs[1]: set(), subs[2]: {"mc_cluster"}})
        self.assertEqual({sub: context.locks for sub, context in estate.contexts.items()},
                         {subs[0]: [f"/subscriptions/{subs[0]}/resourcegroups/rg-locked"], subs[1]: [], subs[2]: []})
        self.assertEqual({sub: context.costs for sub, context in estate.contexts.items()},
                         {sub: {f"/subscriptions/{sub}/resourcegroups/rg-app/providers/microsoft.compute/disks/d{n}": float(n)} for n, sub in enumerate(subs, 1)})
        self.assertEqual(len(estate.leads), 4)

    def test_a_group_of_one_attributes_a_row_that_names_no_subscription_to_it(self):
        tenant, subs = tenant_of(1)
        tenant.graph["recent-creations"] = [{"targetId": "x/y/z"}]
        tenant.graph["managed-groups"] = [{"name": "mc_cluster"}]
        estate, _ = collect_all(tenant, subs)
        self.assertEqual((estate.contexts[subs[0]].recent, estate.contexts[subs[0]].managed_groups), ({"x/y/z"}, {"mc_cluster"}))

    def test_a_row_of_a_subscription_that_is_not_in_the_group_is_nobodys(self):
        tenant, subs = tenant_of(2, with_leads=False)
        stranger = sub_id(999)
        tenant.graph["recent-creations"] = [{"targetId": f"/subscriptions/{stranger}/resourcegroups/g/providers/p/t/n"}]
        tenant.graph["managed-groups"] = [{"id": f"/subscriptions/{stranger}/resourcegroups/mc_x", "name": "mc_x"}]
        tenant.graph["orphan-managed-disk"] = [disk_in(stranger, "elsewhere")]
        tenant.leaky = True  # a service that answers for more than it was asked
        estate, _ = collect_all(tenant, subs)
        self.assertEqual((estate.leads, [c.recent for c in estate.contexts.values()], [c.managed_groups for c in estate.contexts.values()]), ([], [set(), set()], [set(), set()]))

    def test_one_group_whose_query_fails_fails_that_source_for_every_subscription_of_the_group_and_the_others_go_on(self):
        tenant, subs = tenant_of(120)
        tenant.failures = {"graph:orphan-managed-disk": [400, 0, 0]}
        estate, notes = collect_all(tenant, subs)
        self.assertEqual(len(estate.contexts), 120)
        self.assertEqual(len(estate.leads), 70, "the disks of the other two groups")
        self.assertEqual((estate.sources_read, estate.sources_failed), (120 * 7 - 50, 50))
        self.assertEqual(notes, ["orphan-managed-disk could not be read in 50 subscriptions (00000001, 00000002, 00000003 and 47 more): POST management.azure.com: 400 Failed: boom"])


class WhatCouldNotBeReadIsOneNoteForEachSource(unittest.TestCase):
    def test_a_source_that_failed_in_one_subscription_is_a_note_of_its_own_as_it_always_was(self):
        tenant, subs = tenant_of(3)
        tenant.broken = {("advisor", subs[1]): 403, ("costs", subs[2]): 400}
        _, notes = collect_all(tenant, subs)
        self.assertEqual(notes, [f"{subs[1][:8]}: advisor-cost could not be read (GET management.azure.com: 403 Failed: boom)",
                                 f"{subs[2][:8]}: cost lines could not be read (POST management.azure.com: 400 Failed: boom)"])

    def test_a_source_that_failed_in_several_is_one_note_with_the_count_the_first_few_and_the_commonest_reason(self):
        tenant, subs = tenant_of(30)
        tenant.failures = {"costs": 400, "locks": 403}
        tenant.broken = {("costs", subs[0]): 500}
        estate, notes = collect_all(tenant, subs)
        self.assertEqual(len(estate.contexts), 30)
        self.assertEqual(notes, ["management locks could not be read in 30 subscriptions (00000001, 00000002, 00000003 and 27 more): GET management.azure.com: 403 Failed: boom",
                                 "cost lines could not be read in 30 subscriptions (00000001, 00000002, 00000003 and 27 more): POST management.azure.com: 400 Failed: boom"])
        self.assertTrue(all(len(note) <= 300 for note in notes))

    def test_the_notes_keep_the_order_of_the_sources(self):
        tenant, subs = tenant_of(2)
        tenant.failures = {"costs": 400, "locks": 400, "advisor": 400, "graph:managed-groups": 400, "graph:recent-creations": 400, "graph:stopped-vm": 400}
        _, notes = collect_all(tenant, subs)
        self.assertEqual([note.split(" could not")[0] for note in notes], ["stopped-vm", "advisor-cost", "management locks", "recent creations", "managed resource groups", "cost lines"])

    def test_a_guard_that_could_not_be_read_stays_unread_for_the_subscriptions_that_it_failed_in_only(self):
        tenant, subs = tenant_of(3)
        tenant.broken = {("locks", subs[1]): 403}
        estate, _ = collect_all(tenant, subs)
        self.assertEqual([estate.contexts[sub].locks is None for sub in subs], [False, True, False])

    def test_some_names_the_first_few_at_eight_characters_and_counts_the_rest(self):
        self.assertEqual(detectors.some([sub_id(n) for n in range(1, 3)]), "00000001, 00000002")
        self.assertEqual(detectors.some([sub_id(n) for n in range(1, 4)]), "00000001, 00000002, 00000003")
        self.assertEqual(detectors.some([sub_id(n) for n in range(1, 5)]), "00000001, 00000002, 00000003 and 1 more")
        self.assertEqual(detectors.some([sub_id(n) for n in range(1, 1001)], 5), "00000001, 00000002, 00000003, 00000004, 00000005 and 995 more")
        self.assertEqual(detectors.some([]), "")


class TheShareOfTheDeadline(unittest.TestCase):
    def test_when_the_time_is_used_up_no_further_subscription_is_started_and_the_rest_are_unread_in_the_order_of_the_list(self):
        tenant, subs = tenant_of(14)
        clock = Ticker(step=0.0)
        tenant.on_call = lambda method, path: clock.jump(10)
        deadline = clock.now + 360
        estate, _ = collect_all(tenant, subs, out_of_time=lambda: clock() >= deadline)
        # eight queries take 80 seconds, each subscription 30 more: the tenth starts at 350 seconds, the eleventh would start at 380
        self.assertEqual(list(estate.contexts), subs[:10])
        self.assertEqual((estate.unread, estate.stopped), (subs[10:], "time"))
        self.assertEqual(sorted(lead.name for lead in estate.leads), sorted(f"d{n}" for n in range(1, 11)), "no lead of a subscription that was not read")
        self.assertEqual(tenant.read_subscriptions("costmanagement"), subs[:10], "no call was made for a subscription that was not read")

    def test_when_there_is_no_time_at_all_nothing_is_read_and_no_call_is_made(self):
        tenant, subs = tenant_of(5)
        estate, _ = collect_all(tenant, subs, out_of_time=lambda: True)
        self.assertEqual((estate.unread, estate.stopped, estate.contexts, estate.leads, tenant.calls), (subs, "time", {}, [], []))

    def test_when_the_time_runs_out_in_the_middle_of_a_group_the_rest_of_the_group_is_unread_with_all_the_groups_after_it(self):
        tenant, subs = tenant_of(120)
        reads = []
        tenant.on_call = lambda method, path: reads.append(path) if "costmanagement" in path else None
        estate, _ = collect_all(tenant, subs, out_of_time=lambda: len(reads) >= 60)
        self.assertEqual((len(estate.contexts), estate.unread), (60, subs[60:]))
        self.assertEqual(len(tenant.graph_calls), 2 * 8, "the third group was not started, and the second one was read as far as the time went")

    def test_when_the_time_is_enough_nothing_is_unread(self):
        tenant, subs = tenant_of(4)
        estate, _ = collect_all(tenant, subs, out_of_time=lambda: False)
        self.assertEqual((estate.unread, estate.stopped), ([], ""))

    def test_an_identity_that_gives_no_token_stops_the_reading_with_its_reason_and_keeps_what_was_read(self):
        tenant, subs = tenant_of(6)
        arm = Arm(Client(allowed_calls(), Redactor(), transport=tenant, sleep=lambda s: None), lambda resource: TOKEN)
        calls = []

        def token(resource):
            calls.append(resource)
            if len(calls) > 8 + 3 * 2:  # the eight queries and the three reads of two subscriptions
                raise IdentityError("the managed identity endpoint answered 500 after 3 tries")
            return TOKEN

        arm.token = token
        notes: list[str] = []
        estate = detectors.collect_estate(arm, subs, NOW, notes)
        self.assertEqual((list(estate.contexts), estate.unread, estate.stopped), (subs[:2], subs[2:], "identity"))
        self.assertEqual(estate.reason, "the managed identity endpoint answered 500 after 3 tries")

    def test_collect_of_one_subscription_is_as_it_was_and_raises_the_error_of_an_identity_that_gives_no_token(self):
        tenant, subs = tenant_of(1)
        arm = Arm(Client(allowed_calls(), Redactor(), transport=tenant, sleep=lambda s: None), lambda resource: TOKEN)
        notes: list[str] = []
        collected = detectors.collect(arm, subs[0], NOW, notes)
        self.assertEqual((collected.sources_read, collected.sources_failed, notes), (7, 0, []))

        def refuses(resource):
            raise IdentityError("no token")

        arm.token = refuses
        with self.assertRaises(IdentityError):
            detectors.collect(arm, subs[0], NOW, notes)


# -- the run -----------------------------------------------------------------------------------------------------------------------------------------

def watch(tenant, env=None, ticker=None, **options):
    return run_watch(tenant, env=env or ALL, ticker=ticker or Ticker(step=0.0), **options)


class WithTheSwitchOnTheRunReadsEverySubscriptionOfTheIdentity(unittest.TestCase):
    def test_the_list_is_the_first_call_and_it_is_made_once_and_every_enabled_subscription_is_read(self):
        tenant, subs = tenant_of(5)
        tenant.listed.append(item(sub_id(77), "Disabled"))
        summary, events, _ = watch(tenant)
        self.assertEqual([(c["method"], c["path"]) for c in tenant.calls[:1]], [("GET", "/subscriptions")])
        self.assertEqual(len([c for c in tenant.calls if c["path"] == "/subscriptions"]), 1)
        self.assertEqual(tenant.read_subscriptions("costmanagement"), subs, "the one that is disabled is not read")
        self.assertEqual({tuple(asked) for _, asked in tenant.graph_calls}, {tuple(subs)})
        self.assertEqual((summary.ok, summary.leads), (True, 5))
        self.assertEqual({lead["resourceId"].split("/")[2] for lead in of_type(events, "lead.found")}, set(subs))

    def test_the_run_started_carries_the_count_the_first_few_ids_and_where_the_list_came_from(self):
        tenant, subs = tenant_of(5)
        _, events, _ = watch(tenant)
        started = events[0]
        self.assertEqual(started["type"], "run.started")
        self.assertEqual((started["subscriptions"], started["scopes"], started["scopeFrom"]), (5, [sub[:8] for sub in subs], "estate"))
        self.assertEqual((started["trigger"], len(started["detectors"])), ("control", 7))

    def test_with_two_hundred_subscriptions_it_carries_the_count_and_five_ids_and_not_two_hundred(self):
        tenant, subs = tenant_of(200, with_leads=False)
        _, events, messages = watch(tenant)
        started = events[0]
        self.assertEqual((started["subscriptions"], started["scopes"]), (200, [sub[:8] for sub in subs[:5]]))
        line = next(m for m in messages if '"run.started"' in m)
        self.assertLess(len(line), 600, "a line of the History does not grow with the estate")
        self.assertNotIn(subs[199][:8], line)

    def test_what_the_identity_can_read_only_in_the_pilot_subscription_is_read_without_a_break(self):
        tenant = Tenant([SUBSCRIPTION])
        tenant.graph["orphan-managed-disk"] = [disk_row("disk-one")]
        tenant.costs_of[SUBSCRIPTION] = [(9.0, disk_row("disk-one")["id"])]
        summary, events, _ = watch(tenant)
        self.assertEqual((summary.ok, summary.leads, summary.cases, events[0]["subscriptions"], events[0]["scopeFrom"]), (True, 1, 1, 1, "estate"))
        self.assertEqual([e["note"] for e in of_type(events, "run.note")], ["the investigation did not run: it is switched off"])

    def test_the_list_of_the_setting_is_not_read_when_the_identity_lists_other_subscriptions(self):
        tenant, subs = tenant_of(2)
        _, events, _ = watch(tenant)
        self.assertNotIn(SUBSCRIPTION, tenant.read_subscriptions("costmanagement"))
        self.assertEqual(events[0]["scopeFrom"], "estate")

    def test_the_list_is_made_once_and_every_part_of_the_run_works_with_it(self):
        tenant, subs = tenant_of(3)
        seen = {}

        class Capturing(FakeToolbox):
            def __init__(self, arm, subscriptions, now, notes):
                super().__init__()
                seen["subscriptions"] = subscriptions

        env = {**ALL, "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/meternaut", "INVESTIGATE": "true"}
        with mock.patch.object(investigate, "Toolbox", Capturing):
            _, events, _ = watch(tenant, env=env, foundry=FakeFoundry())
        self.assertEqual(seen["subscriptions"], tuple(subs), "the tools of the investigation read the same list")
        self.assertEqual(len([c for c in tenant.calls if c["path"] == "/subscriptions"]), 1, "the list is asked for once in the run")
        self.assertEqual(events[0]["subscriptions"], 3)

    def test_the_settings_of_the_run_are_not_changed_the_run_works_with_a_copy(self):
        tenant, subs = tenant_of(2)
        original = config.load(ALL)
        self.assertEqual((original.subscriptions, original.all_subscriptions), ((SUBSCRIPTION,), True))
        watch(tenant)
        self.assertEqual(config.load(ALL), original)


class WhenTheListCannotBeUsed(unittest.TestCase):
    def test_the_run_reads_the_list_of_the_setting_and_says_so_when_the_identity_cannot_list(self):
        tenant = Tenant([])
        tenant.failures = {"subscriptions": 403}
        tenant.graph["orphan-managed-disk"] = [disk_row("disk-one")]
        tenant.costs_of[SUBSCRIPTION] = [(9.0, disk_row("disk-one")["id"])]
        summary, events, _ = watch(tenant)
        self.assertEqual((summary.ok, summary.leads), (True, 1))
        self.assertEqual((events[0]["subscriptions"], events[0]["scopes"], events[0]["scopeFrom"]), (1, [SUBSCRIPTION[:8]], "setting-fallback"))
        notes = [e["note"] for e in of_type(events, "run.note")]
        self.assertEqual(len(notes), 2)
        self.assertIn("could not be had", notes[0])
        self.assertIn("403", notes[0])
        self.assertIn("the 1 subscription of SCOPE_SUBSCRIPTIONS is read instead", notes[0])

    def test_a_list_with_nothing_enabled_is_the_same(self):
        tenant = Tenant([sub_id(1)])
        tenant.listed = [item(sub_id(1), "Disabled")]
        tenant.graph["orphan-managed-disk"] = [disk_row("disk-one")]
        summary, events, _ = watch(tenant)
        self.assertEqual((summary.ok, events[0]["scopeFrom"], events[0]["scopes"]), (True, "setting-fallback", [SUBSCRIPTION[:8]]))
        self.assertEqual([e["note"] for e in of_type(events, "run.note")][0],
                         "the identity can read no subscription that is enabled, so the 1 subscription of SCOPE_SUBSCRIPTIONS is read instead")

    def test_without_a_list_of_the_setting_the_run_ends_with_run_failed_and_a_plain_reason_and_reads_nothing(self):
        tenant = Tenant([])
        tenant.failures = {"subscriptions": 500}
        summary, events, _ = watch(tenant, env=ALL_NO_LIST)
        self.assertFalse(summary.ok)
        self.assertEqual([e["type"] for e in events], ["run.started", "run.failed"])
        self.assertEqual((events[0]["subscriptions"], events[0]["scopes"], events[0]["scopeFrom"]), (0, [], "none"))
        self.assertTrue(events[1]["reason"].endswith("and SCOPE_SUBSCRIPTIONS is empty, so there is nothing to read"))
        self.assertIn("could not be had", events[1]["reason"])
        self.assertEqual([c["path"] for c in tenant.calls], ["/subscriptions"] * 3, "the list was tried (the retries of a server error), and then nothing else was called")
        self.assertEqual(tenant.chat_calls(), [])

    def test_an_empty_list_without_a_list_of_the_setting_fails_the_run_the_same_way(self):
        tenant = Tenant([])
        summary, events, _ = watch(tenant, env=ALL_NO_LIST)
        self.assertFalse(summary.ok)
        self.assertEqual(events[-1]["type"], "run.failed")
        self.assertIn("the identity can read no subscription that is enabled", events[-1]["reason"])

    def test_a_failed_run_is_kept_with_its_reason_so_that_the_history_page_shows_it(self):
        clock = Moving()
        extras = loop_for(clock)
        tenant = Tenant([])
        tenant.failures = {"subscriptions": 500}
        summary, events, _ = watch(tenant, env=ALL_NO_LIST, clock=clock, extras=extras)
        (record,) = extras.store.runs_recent()
        self.assertEqual((record.ok, record.reason, record.leads), (False, events[-1]["reason"], 0))
        self.assertIsNotNone(record.finished_at)
        reply = Console(store=extras.store).get("/history")
        self.assertEqual((reply.status, reply.problems), (200, []))

    def test_a_throttled_list_is_waited_for_and_read(self):
        tenant, subs = tenant_of(2)
        tenant.failures = {"subscriptions": [429]}
        _, events, _ = watch(tenant)
        self.assertEqual((events[0]["subscriptions"], events[0]["scopeFrom"]), (2, "estate"))
        self.assertEqual(tenant.sleeps, [1.0])

    def test_an_identity_that_gives_no_token_ends_the_run_as_before_with_the_switch_on_too(self):
        tenant, _ = tenant_of(2)
        summary, events, _ = watch(tenant, fetch=lambda url, headers, timeout: (500, b"{}"))
        self.assertFalse(summary.ok)
        self.assertEqual(events[-1]["reason"], "no detector could read any subscription")
        self.assertEqual(events[0]["scopeFrom"], "setting-fallback", "the list was asked for, the identity gave no token, and the list of the setting was read")
        self.assertTrue(any("managed identity" in e["note"] for e in of_type(events, "run.note")))
        self.assertEqual(tenant.calls, [])


class WhenThereAreMoreSubscriptionsThanTheTimeIsFor(unittest.TestCase):
    ENV = {**ALL, "RUN_DEADLINE_SECONDS": "600"}

    def slow(self, count=14):
        tenant, subs = tenant_of(count)
        ticker = Ticker(step=0.0)
        tenant.on_call = lambda method, path: ticker.jump(10) if path != "/subscriptions" else None
        return tenant, subs, ticker

    def test_the_run_reads_what_the_share_allows_says_which_were_not_read_and_goes_on_to_end_well(self):
        tenant, subs, ticker = self.slow()
        summary, events, _ = watch(tenant, env=self.ENV, ticker=ticker)
        self.assertEqual((summary.ok, summary.leads), (True, 10))
        self.assertEqual(events[-1]["type"], "run.finished")
        self.assertEqual(tenant.read_subscriptions("costmanagement"), subs[:10])
        (note,) = [e["note"] for e in of_type(events, "run.note") if "were not read" in e["note"]]
        self.assertEqual(note, "4 subscriptions were not read (0000000b, 0000000c, 0000000d and 1 more): the time for reading them (360 of the 600 seconds of the run) was used up")
        self.assertEqual({lead["resourceId"].split("/")[2] for lead in of_type(events, "lead.found")}, set(subs[:10]))
        self.assertEqual(events[0]["subscriptions"], 14, "the run started with the whole list")

    def test_the_share_is_sixty_percent_of_the_deadline_and_a_subscription_that_was_started_in_it_may_finish_in_a_tenth_more(self):
        self.assertEqual((run.READ_SHARE, run.READ_GRACE), (0.6, 0.1))
        tenant, subs, ticker = self.slow()
        watch(tenant, env={**ALL, "RUN_DEADLINE_SECONDS": "300"}, ticker=ticker)
        self.assertEqual(len(tenant.read_subscriptions("costmanagement")), 4, "80 seconds for the queries and 30 for each subscription, in 180 seconds: the fourth ends at 200")
        self.assertEqual(tenant.asked("authorization/locks")[3]["path"].split("/")[2], subs[3], "the calls of the fourth subscription were made: its end is inside the tenth")

    def test_a_call_after_the_seventy_percent_is_refused_by_the_client_and_is_a_note_of_the_subscription_that_was_in_flight(self):
        tenant, subs = tenant_of(14)
        ticker = Ticker(step=0.0)
        # eight queries of 20 seconds, then a first subscription whose Advisor takes a minute: it started inside the share (at 160 of 180) and ends beyond the 210 of the client
        tenant.on_call = lambda method, path: ticker.jump(60 if "advisor" in path else 20) if path != "/subscriptions" else None
        summary, events, _ = watch(tenant, env={**ALL, "RUN_DEADLINE_SECONDS": "300"}, ticker=ticker)
        self.assertEqual(events[-1]["type"], "run.finished")
        notes = [e["note"] for e in of_type(events, "run.note")]
        self.assertIn(f"{subs[0][:8]}: management locks could not be read (GET management.azure.com: the deadline of the run was reached)", notes)
        self.assertIn(f"{subs[0][:8]}: cost lines could not be read (POST management.azure.com: the deadline of the run was reached)", notes)
        self.assertEqual([c for c in tenant.asked("authorization/locks") if Tenant.PER_SUBSCRIPTION.match(c["path"].lower())], [], "the client made no call after its deadline")
        self.assertEqual(len(tenant.read_subscriptions("advisor")), 1)
        self.assertTrue(any(note.startswith("13 subscriptions were not read") for note in notes))

    def test_the_cases_that_follow_still_have_their_time_and_judge_the_leads_that_were_read(self):
        tenant, subs, ticker = self.slow()
        summary, events, _ = watch(tenant, env=self.ENV, ticker=ticker)
        self.assertEqual((summary.cases, summary.proposed), (3, 3))
        self.assertEqual(len(tenant.chat_calls()), 6)

    def test_the_subscription_of_the_loop_is_read_first_even_when_its_id_sorts_last(self):
        clock = Moving()
        extras = loop_for(clock)
        tenant, subs, ticker = self.slow(14)
        tenant.listed.append(item(SUBSCRIPTION))
        tenant.graph["orphan-managed-disk"].append(disk_row("planted"))
        tenant.costs_of[SUBSCRIPTION] = []
        self.assertGreater(SUBSCRIPTION, subs[-1])
        _, events, _ = watch(tenant, env=self.ENV, ticker=ticker, clock=clock, extras=extras)
        self.assertEqual(tenant.read_subscriptions("costmanagement")[0], SUBSCRIPTION)
        self.assertEqual(len(tenant.read_subscriptions("costmanagement")), 10)
        self.assertIn("planted", [e["resourceName"] for e in of_type(events, "lead.found")])
        self.assertEqual(events[0]["scopes"], [sub[:8] for sub in subs[:5]], "the line names the first of the sorted list, not the order of reading")

    def test_a_run_with_no_time_for_any_subscription_fails_with_the_reason_of_the_share_and_not_a_deadline(self):
        tenant, subs = tenant_of(3)
        ticker = Ticker(step=0.0)
        tenant.first_call = lambda: ticker.jump(70)  # the list of subscriptions is the first call: 70 of the 100 seconds of the run, and 60 are the share
        summary, events, _ = watch(tenant, env={**ALL, "RUN_DEADLINE_SECONDS": "100"}, ticker=ticker)
        self.assertFalse(summary.ok)
        self.assertEqual(events[-1], {**events[-1], "type": "run.failed",
                                      "reason": "the time for reading the subscriptions (60 of the 100 seconds of the run) was used up before any detector could read"})
        self.assertEqual(tenant.chat_calls(), [])

    def test_a_run_whose_whole_deadline_has_passed_says_so_as_before(self):
        tenant, subs = tenant_of(3)
        summary, events, _ = watch(tenant, env={**ALL, "RUN_DEADLINE_SECONDS": "60"}, ticker=Ticker(step=100))
        self.assertFalse(summary.ok)
        self.assertEqual(events[-1]["reason"], "the deadline of 60 seconds was reached before any detector could read")

    def test_the_notes_of_a_big_estate_are_a_few_lines_and_the_history_of_the_run_keeps_them(self):
        clock = Moving()
        extras = loop_for(clock)
        tenant, subs = tenant_of(60)
        tenant.failures = {"costs": 400, "advisor": 403}
        _, events, _ = watch(tenant, clock=clock, extras=extras)
        notes = [e["note"] for e in of_type(events, "run.note")]
        self.assertLessEqual(len(notes), 5)
        (record,) = extras.store.runs_recent()
        self.assertLessEqual(len(record.notes), 5)
        self.assertEqual(record.ok, True)


class ThrottlingDoesNotFailTheRun(unittest.TestCase):
    def test_a_throttled_cost_query_in_every_subscription_is_a_note_and_the_run_goes_on(self):
        tenant, subs = tenant_of(4)
        tenant.failures = {"costs": 429}
        summary, events, _ = watch(tenant)
        self.assertEqual((summary.ok, summary.leads, summary.cases), (True, 4, 3))
        self.assertEqual({e["costUsd30d"] for e in of_type(events, "lead.found")}, {None}, "no figure is made up")
        (note,) = [e["note"] for e in of_type(events, "run.note") if "cost lines" in e["note"]]
        self.assertTrue(note.startswith("cost lines could not be read in 4 subscriptions"))
        self.assertIn("429", note)

    def test_a_throttled_resource_graph_query_that_does_not_pass_is_a_note_too_and_the_other_queries_are_read(self):
        tenant, subs = tenant_of(3)
        tenant.failures = {"graph:orphan-managed-disk": 429}
        summary, events, _ = watch(tenant)
        self.assertEqual((summary.ok, summary.leads), (True, 0))
        self.assertTrue(any(e["note"].startswith("orphan-managed-disk could not be read in 3 subscriptions") for e in of_type(events, "run.note")))

    def test_a_wait_that_the_service_asks_for_is_taken_inside_the_share_and_never_beyond_it(self):
        tenant, subs = tenant_of(3)
        tenant.failures = {"costs": 429}
        tenant.retry_after = 50
        ticker = Ticker(step=0.0)
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            ticker.jump(seconds)

        _, events, _ = watch(tenant, env={**ALL, "RUN_DEADLINE_SECONDS": "100"}, ticker=ticker, sleep=sleep)
        self.assertEqual(slept, [50.0], "one wait that fits in the share, and none that does not")
        self.assertLessEqual(ticker.now - 1000.0, 60.0)
        self.assertEqual(events[-1]["type"], "run.finished")
        self.assertTrue(any(e["note"].startswith("cost lines could not be read in 3 subscriptions") for e in of_type(events, "run.note")))


class WatchingMoreDoesNotWidenWhatMayBeChanged(unittest.TestCase):
    def test_a_planted_disk_of_the_name_of_the_change_group_in_another_subscription_gets_no_plan_and_is_not_a_fixture(self):
        clock = Moving()
        extras = loop_for(clock)
        other = sub_id(5)
        tenant = Tenant([SUBSCRIPTION, other])
        tenant.graph["orphan-managed-disk"] = [disk_in(other, "planted-elsewhere", "rg-meternaut", tags={"meternaut-planted": "demo"}, timeCreated="2026-01-02T10:00:00+00:00")]
        tenant.costs_of[SUBSCRIPTION], tenant.costs_of[other] = [], []
        summary, events, _ = watch(tenant, clock=clock, extras=extras)
        self.assertEqual((summary.ok, summary.cases), (True, 1))
        (case,) = extras.store.cases_recent()
        self.assertEqual((case.subscription_id, case.status, case.plan_id), (other, "proposed", None), "a case is made and a person reads it, and no plan is made for it")
        self.assertEqual(extras.store.plans_open(), [])
        self.assertEqual(of_type(events, "plan.created"), [])

    def test_the_planted_disk_of_the_loop_still_gets_its_plan_when_the_watch_reads_the_whole_estate(self):
        clock = Moving()
        extras = loop_for(clock)
        tenant = Tenant([SUBSCRIPTION, sub_id(5)])
        tenant.graph["orphan-managed-disk"] = [disk_row("planted-disk-1", "rg-meternaut", tags={"meternaut-planted": "demo"}, timeCreated="2026-11-04T11:59:00+00:00")]
        tenant.costs_of[SUBSCRIPTION], tenant.costs_of[sub_id(5)] = [], []
        _, events, _ = watch(tenant, clock=clock, extras=extras)
        (plan,) = extras.store.plans_open()
        self.assertEqual((plan.family, plan.subscription_id), ("delete-disk", SUBSCRIPTION))
        self.assertEqual(len(of_type(events, "plan.created")), 1)


# -- the History -------------------------------------------------------------------------------------------------------------------------------------

class TheHistoryAndItsPages(unittest.TestCase):
    def test_the_run_started_line_is_short_whatever_the_estate(self):
        lines = []
        history = events_module.History("r" * 32, None, lambda: NOW, lambda text: text, logger=mock.Mock(info=lines.append))
        history.emit("run.started", trigger="timer", subscriptions=1000, scopes=[sub_id(n)[:8] for n in range(5)], scopeFrom="estate", detectors=list(detectors.DETECTOR_NAMES))
        self.assertLess(len(lines[0]), 600)

    def test_a_run_of_many_subscriptions_is_kept_and_the_history_page_still_renders_with_its_notes(self):
        clock = Moving()
        extras = loop_for(clock)
        tenant, subs = tenant_of(60)
        tenant.failures = {"costs": 400}
        watch(tenant, clock=clock, extras=extras)
        reply = Console(store=extras.store).get("/history")
        self.assertEqual((reply.status, reply.problems), (200, []))
        self.assertIn("cost lines could not be read in 60 subscriptions", reply.content)
        self.assertEqual(len(reply.table("runs").rows), 1)

    def test_the_notebook_page_of_a_case_from_a_subscription_of_a_big_estate_renders(self):
        clock = Moving()
        extras = loop_for(clock)
        tenant, subs = tenant_of(30)
        watch(tenant, clock=clock, extras=extras)
        console = Console(store=extras.store)
        cases = extras.store.cases_recent()
        self.assertTrue(cases)
        for case in cases:
            reply = console.get(f"/cases/{case.case_id}")
            self.assertIn(reply.status, (200, 404), case.case_id)
            self.assertEqual(reply.problems, [])
