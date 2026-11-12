"""How the app reads what Cost Management shows: the cost of a whole subscription and of a resource group by service, the lines of one resource whatever the case of its id, more than one page,
what it does when Cost Management says "too many requests", and the display name of a subscription. A fake of the Query API of Cost Management stands in for Azure. Everything in it is INVENTED."""
import datetime as dt
import json
import unittest
from collections import namedtuple
from urllib.parse import parse_qs, urlsplit

import support  # noqa: F401  (puts the app on the path)

from support import TOKEN
from cases import detectors
from cases.arm import COST_RETRIES, COST_WAIT_MAX, Arm, ScopeCost
from cases.detectors import Context, Lead
from cases.http import Client, HttpError, allowed_calls
from cases.redact import Redactor

SUB = "11111111-2222-4333-8444-555555555555"
OTHER = "22222222-3333-4444-8555-666666666666"
FIRST, LAST = dt.date(2026, 10, 14), dt.date(2026, 11, 12)

Line = namedtuple("Line", "day resource group service cost currency")


def line(cost: float, service: str, resource: str = "", group: str = "", day: dt.date = LAST, currency: str = "USD") -> Line:
    """One cost line as Cost Management keeps it: the resource id and the group in lower case, or empty for a line that has none (a plan of Microsoft Defender for Cloud, a purchase)."""
    return Line(day, resource.lower(), group.lower(), service, cost, currency)


class CostManagement:
    """The Query API of Cost Management as far as the app uses it: ActualCost over a custom period, grouped by dimensions, one In filter on a dimension, daily or not, a page of `page_size` rows
    and a nextLink for the rest. A filter is matched without regard to case. `limits` are answered first, one for each call: (status, headers). Every call is kept in `calls`."""

    def __init__(self, lines, page_size: int = 1000):
        self.lines, self.page_size, self.limits, self.calls = list(lines), page_size, [], []

    def __call__(self, method, url, headers, data, timeout):
        body = json.loads(data) if data else None
        self.calls.append({"method": method, "url": url, "body": body, "headers": dict(headers)})
        if self.limits:
            status, answer_headers = self.limits.pop(0)
            return status, answer_headers, b'{"error":{"code":"429","message":"Too many requests"}}'
        if "/providers/microsoft.costmanagement/query" not in urlsplit(url).path.lower():
            return 404, {}, b"{}"
        dataset = body["dataset"]
        asked = dataset.get("filter", {}).get("dimensions")
        keep = [item for item in self.lines if not asked or self.value_of(item, asked["name"]).lower() in {value.lower() for value in asked["values"]}]
        daily = dataset["granularity"] == "Daily"
        names = [group["name"] for group in dataset.get("grouping", [])]
        if daily:
            names = ["UsageDate", *names]
        sums: dict[tuple, float] = {}
        currencies: dict[tuple, str] = {}
        for item in keep:
            key = tuple(self.value_of(item, name) for name in names)
            sums[key] = sums.get(key, 0.0) + item.cost
            currencies[key] = item.currency
        rows = [[amount, *key, currencies[key]] for key, amount in sums.items()]
        start = int(parse_qs(urlsplit(url).query).get("$skiptoken", ["0"])[0])
        page, more = rows[start:start + self.page_size], start + self.page_size < len(rows)
        columns = [{"name": "Cost"}, *({"name": name} for name in names), {"name": "Currency"}]
        properties = {"columns": columns, "rows": page}
        if more:
            properties["nextLink"] = f"https://management.azure.com{urlsplit(url).path}?api-version=2023-11-01&$skiptoken={start + self.page_size}"
        return 200, {}, json.dumps({"properties": properties}).encode()

    @staticmethod
    def value_of(item: Line, dimension: str) -> str:
        return {"ResourceId": item.resource, "ServiceName": item.service, "ResourceGroup": item.group, "UsageDate": item.day.strftime("%Y%m%d")}[dimension]

    def bodies(self) -> list[dict]:
        return [call["body"] for call in self.calls]


def reader(lines=(), **options):
    """An Arm over the fake, with the waits that the client asked for in `sleeps`."""
    sleeps: list[float] = []
    fake = CostManagement(lines, **options)
    client = Client(allowed_calls(), Redactor(), transport=fake, sleep=sleeps.append, jitter=lambda: 0.5)
    return Arm(client, lambda resource: TOKEN), fake, sleeps


# A subscription as Cost Analysis shows it: a few services in a few groups, a plan with no resource and no group, and the resources of Meternaut's own group.
BILL = [
    line(88.10, "Virtual Network", f"/subscriptions/{SUB}/resourceGroups/rg-net/providers/Microsoft.Network/virtualNetworks/vnet-a", "rg-net"),
    line(41.25, "Microsoft Defender for Cloud"),
    line(19.60, "Azure Cognitive Search", f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Search/searchServices/srch-a", "rg-app"),
    line(9.90, "Grafana", f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Dashboard/grafana/graf-a", "rg-app"),
    line(1.50, "Virtual Network", f"/subscriptions/{SUB}/resourceGroups/rg-meternaut/providers/Microsoft.Network/privateEndpoints/pe-a", "rg-meternaut"),
    line(0.25, "Storage", f"/subscriptions/{SUB}/resourceGroups/rg-meternaut/providers/Microsoft.Storage/storageAccounts/stmeter", "rg-meternaut", day=LAST - dt.timedelta(days=3)),
]


class TheCostOfAWholeSubscription(unittest.TestCase):
    def test_every_cost_line_of_the_subscription_is_in_its_total_also_the_lines_that_no_resource_and_no_group_have(self):
        arm, fake, _ = reader(BILL)
        found = arm.scope_costs(SUB, FIRST, LAST)
        self.assertEqual(found.total, 160.6)
        self.assertEqual(found.services, {"Virtual Network": 89.6, "Microsoft Defender for Cloud": 41.25, "Azure Cognitive Search": 19.6, "Grafana": 9.9, "Storage": 0.25})
        self.assertEqual((found.currency, found.rows), ("USD", 5))
        self.assertIn(41.25, found.services.values(), "the plan of Microsoft Defender for Cloud has no resource and no group and is in the subscription")

    def test_it_is_one_query_by_service_for_the_actual_cost_of_the_whole_period_with_no_filter(self):
        arm, fake, _ = reader(BILL)
        arm.scope_costs(SUB, FIRST, LAST)
        (call,) = fake.calls
        self.assertEqual((call["method"], call["url"]), ("POST", f"https://management.azure.com/subscriptions/{SUB}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"))
        body = call["body"]
        self.assertEqual((body["type"], body["timePeriod"]), ("ActualCost", {"from": "2026-10-14T00:00:00Z", "to": "2026-11-12T23:59:59Z"}))
        self.assertEqual(body["dataset"]["grouping"], [{"type": "Dimension", "name": "ServiceName"}])
        self.assertNotIn("filter", body["dataset"])
        self.assertEqual(call["headers"].get("ClientType"), "Meternaut")

    def test_a_resource_group_is_asked_with_a_filter_on_the_group_in_lower_case_and_in_the_case_that_the_id_gave_and_has_only_its_lines(self):
        arm, fake, _ = reader(BILL)
        found = arm.scope_costs(SUB, FIRST, LAST, "Rg-Meternaut")
        self.assertEqual((found.total, found.services, found.rows), (1.75, {"Virtual Network": 1.5, "Storage": 0.25}, 2))
        self.assertEqual(fake.bodies()[0]["dataset"]["filter"], {"dimensions": {"name": "ResourceGroup", "operator": "In", "values": ["rg-meternaut", "Rg-Meternaut"]}})
        self.assertEqual(arm.scope_costs(SUB, FIRST, LAST, "rg-app").total, 29.5)
        self.assertEqual(fake.bodies()[1]["dataset"]["filter"]["dimensions"]["values"], ["rg-app"], "one value when the two cases are the same")

    def test_no_line_at_all_is_a_cost_with_no_lines_and_never_a_figure(self):
        arm, _, _ = reader([])
        found = arm.scope_costs(SUB, FIRST, LAST)
        self.assertEqual(found, ScopeCost(0.0, None, {}, 0))
        arm, _, _ = reader(BILL)
        self.assertEqual(arm.scope_costs(SUB, FIRST, LAST, "rg-that-is-not-there").rows, 0)

    def test_more_than_one_page_is_added_up_and_every_page_is_asked_for_with_the_same_question(self):
        many = [line(1.0 + n, f"Service {n:02d}", day=LAST) for n in range(7)]
        arm, fake, _ = reader(many, page_size=3)
        found = arm.scope_costs(SUB, FIRST, LAST)
        self.assertEqual((found.total, found.rows, len(found.services)), (28.0, 7, 7))
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual([call["url"].rsplit("skiptoken=", 1)[-1] for call in fake.calls[1:]], ["3", "6"], "the pages that Cost Management linked to")
        self.assertEqual({json.dumps(body, sort_keys=True) for body in fake.bodies()}, {json.dumps(fake.bodies()[0], sort_keys=True)})

    def test_a_next_page_on_another_host_or_of_another_subscription_or_service_is_never_followed(self):
        for link in ("https://evil.example/subscriptions/{sub}/providers/Microsoft.CostManagement/query?x=1",
                     "https://management.azure.com/subscriptions/{other}/providers/Microsoft.CostManagement/query?x=1",
                     "https://management.azure.com/subscriptions/{sub}/providers/Microsoft.Compute/disks?x=1",
                     "http://management.azure.com/subscriptions/{sub}/providers/Microsoft.CostManagement/query?x=1"):
            with self.subTest(link=link):
                arm, fake, _ = reader(BILL)
                original = fake.__call__

                def hostile(method, url, headers, data, timeout, link=link, original=original):
                    status, answer_headers, answer = original(method, url, headers, data, timeout)
                    document = json.loads(answer)
                    document["properties"]["nextLink"] = link.format(sub=SUB, other=OTHER)
                    return status, answer_headers, json.dumps(document).encode()

                arm.client.transport = hostile
                with self.assertRaises(HttpError):
                    arm.scope_costs(SUB, FIRST, LAST)
                self.assertEqual(len(fake.calls), 1, "no second call is made")

    def test_a_service_without_a_name_is_other_a_name_with_spaces_is_one_line_and_a_line_in_another_currency_is_said(self):
        arm, _, _ = reader([line(2.0, ""), line(3.0, "  Storage  "), line(4.0, "Storage", currency="EUR")])
        found = arm.scope_costs(SUB, FIRST, LAST)
        self.assertEqual(found.services, {"Other": 2.0, "Storage": 7.0})
        self.assertEqual(found.currency, "mixed")
        arm, _, _ = reader([line(2.0, "Storage", currency="EUR")])
        self.assertEqual(arm.scope_costs(SUB, FIRST, LAST).currency, "EUR")

    def test_a_question_that_cost_management_answers_with_something_else_is_an_error_and_not_a_cost_of_nothing(self):
        for answer in ({"nope": 1}, {"properties": {"columns": [{"name": "Cost"}], "rows": [[1.0]]}}, {"properties": {"columns": [{"name": "Cost"}, {"name": "ServiceName"}], "rows": [["x", "S"]]}},
                       {"properties": {"columns": [{"name": "Cost"}, {"name": "ServiceName"}], "rows": [[float("inf"), "S"]]}}, []):
            arm = Arm(Client(allowed_calls(), Redactor(), transport=lambda *call, answer=answer: (200, {}, json.dumps(answer).encode()), sleep=lambda seconds: None), lambda resource: TOKEN)
            with self.assertRaises(HttpError, msg=str(answer)[:60]):
                arm.scope_costs(SUB, FIRST, LAST)


class TheCostOfEachDayOfAScope(unittest.TestCase):
    def test_every_line_of_a_day_is_summed_and_a_day_without_a_line_is_not_there(self):
        arm, fake, _ = reader(BILL)
        days = arm.scope_days(SUB, FIRST, LAST)
        self.assertEqual(days, [(LAST, 160.35, "USD"), (LAST - dt.timedelta(days=3), 0.25, "USD")])
        body = fake.bodies()[0]
        self.assertEqual((body["dataset"]["granularity"], "grouping" in body["dataset"], "filter" in body["dataset"]), ("Daily", False, False))

    def test_a_resource_group_has_only_its_own_days(self):
        arm, fake, _ = reader(BILL)
        self.assertEqual(arm.scope_days(SUB, FIRST, LAST, "rg-meternaut"), [(LAST, 1.5, "USD"), (LAST - dt.timedelta(days=3), 0.25, "USD")])
        self.assertEqual(fake.bodies()[0]["dataset"]["filter"]["dimensions"]["name"], "ResourceGroup")

    def test_no_line_in_the_period_is_no_day_at_all(self):
        arm, _, _ = reader([])
        self.assertEqual(arm.scope_days(SUB, FIRST, LAST), [])


class TheLinesOfOneResourceWhateverTheCaseOfItsId(unittest.TestCase):
    DISK = f"/subscriptions/{SUB}/resourceGroups/Rg-App/providers/Microsoft.Compute/disks/Planted-Disk"

    def test_cost_management_gives_ids_in_lower_case_and_the_lines_are_found_by_the_id_in_lower_case(self):
        arm, _, _ = reader([line(7.5, "Storage", self.DISK, "Rg-App"), line(0.5, "Bandwidth", self.DISK.upper(), "Rg-App")])
        totals, currency = arm.costs(SUB, FIRST, LAST)
        self.assertEqual((totals, currency), ({self.DISK.lower(): 8.0}, "USD"))

    def test_a_lead_is_found_whatever_the_case_of_its_id_in_resource_graph_or_in_advisor(self):
        arm, _, _ = reader([line(7.5, "Storage", self.DISK, "Rg-App")])
        totals, currency = arm.costs(SUB, FIRST, LAST)
        for resource_id in (self.DISK, self.DISK.lower(), self.DISK.upper(), self.DISK.replace("Compute", "COMPUTE")):
            with self.subTest(resource_id=resource_id[-30:]):
                lead = Lead("orphan-managed-disk", resource_id, "microsoft.compute/disks", "Planted-Disk", "Rg-App", SUB, "swedencentral", {}, "", {})
                (ranked,) = detectors.rank([lead], {SUB: Context(costs=totals, currency=currency)})
                self.assertEqual((ranked.cost_usd_30d, ranked.cost_state), (7.5, "lines"))

    def test_a_resource_that_has_no_line_is_a_resource_that_azure_has_no_cost_line_for_and_not_a_cost_of_nothing_that_was_measured(self):
        arm, _, _ = reader([line(7.5, "Storage", self.DISK, "Rg-App")])
        totals, currency = arm.costs(SUB, FIRST, LAST)
        lead = Lead("orphan-managed-disk", self.DISK.replace("Planted-Disk", "Another-Disk"), "microsoft.compute/disks", "Another-Disk", "Rg-App", SUB, "swedencentral", {}, "", {})
        (ranked,) = detectors.rank([lead], {SUB: Context(costs=totals, currency=currency)})
        self.assertEqual((ranked.cost_usd_30d, ranked.cost_state), (0.0, "none"))

    def test_a_subscription_with_no_line_at_all_has_a_state_of_none_and_no_figure(self):
        arm, _, _ = reader([])
        totals, currency = arm.costs(SUB, FIRST, LAST)
        self.assertEqual((totals, currency), ({}, None))
        lead = Lead("orphan-managed-disk", self.DISK, "microsoft.compute/disks", "Planted-Disk", "Rg-App", SUB, "swedencentral", {}, "", {})
        (ranked,) = detectors.rank([lead], {SUB: Context(costs=totals, currency=currency)})
        self.assertEqual((ranked.cost_usd_30d, ranked.cost_state), (None, "none"))

    def test_lines_that_are_not_in_dollars_make_no_figure_in_dollars(self):
        arm, _, _ = reader([line(7.5, "Storage", self.DISK, "Rg-App", currency="EUR")])
        totals, currency = arm.costs(SUB, FIRST, LAST)
        lead = Lead("orphan-managed-disk", self.DISK, "microsoft.compute/disks", "Planted-Disk", "Rg-App", SUB, "swedencentral", {}, "", {})
        (ranked,) = detectors.rank([lead], {SUB: Context(costs=totals, currency=currency)})
        self.assertEqual((ranked.cost_usd_30d, ranked.cost_state), (None, "currency"))


class WhenCostManagementSaysTooManyRequests(unittest.TestCase):
    def test_the_client_waits_as_long_as_retry_after_says_and_reads_again(self):
        arm, fake, sleeps = reader(BILL)
        fake.limits = [(429, {"retry-after": "3"})]
        found = arm.scope_costs(SUB, FIRST, LAST)
        self.assertEqual((found.total, len(fake.calls), sleeps), (160.6, 2, [3.0]))

    def test_it_waits_as_long_as_the_headers_of_cost_management_say_the_longest_binding(self):
        for name in ("x-ms-ratelimit-microsoft.costmanagement-entity-retry-after", "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after",
                     "x-ms-ratelimit-microsoft.costmanagement-client-retry-after"):
            with self.subTest(header=name):
                arm, fake, sleeps = reader(BILL)
                fake.limits = [(429, {name: "7", "x-ms-ratelimit-microsoft.costmanagement-qpu-remaining": "0"})]
                self.assertEqual(arm.scope_costs(SUB, FIRST, LAST).total, 160.6)
                self.assertEqual(sleeps, [7.0])
        arm, fake, sleeps = reader(BILL)
        fake.limits = [(429, {"x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "4", "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after": "9", "retry-after": "2"})]
        arm.scope_costs(SUB, FIRST, LAST)
        self.assertEqual(sleeps, [9.0])

    def test_it_asks_again_four_times_and_then_gives_up_with_the_error_of_cost_management(self):
        arm, fake, sleeps = reader(BILL)
        fake.limits = [(429, {"retry-after": "2"})] * 10
        with self.assertRaises(HttpError) as raised:
            arm.scope_costs(SUB, FIRST, LAST)
        self.assertEqual((raised.exception.status, len(fake.calls), sleeps), (429, 1 + COST_RETRIES, [2.0] * COST_RETRIES))
        self.assertEqual(raised.exception.retry_after, 2.0)

    def test_a_wait_of_more_than_a_minute_is_not_waited_for_and_the_read_fails_at_once(self):
        arm, fake, sleeps = reader(BILL)
        fake.limits = [(429, {"retry-after": str(COST_WAIT_MAX + 1)})]
        with self.assertRaises(HttpError) as raised:
            arm.scope_costs(SUB, FIRST, LAST)
        self.assertEqual((raised.exception.status, len(fake.calls), sleeps), (429, 1, []))

    def test_every_kind_of_cost_read_waits_the_same_way(self):
        reads = {"the lines of every resource": lambda arm: arm.cost_lines(SUB, FIRST, LAST), "the totals of every resource": lambda arm: arm.costs(SUB, FIRST, LAST),
                 "the days of some resources": lambda arm: arm.cost_days(SUB, FIRST, LAST, where=("ResourceId", ("/x",))), "the days of a scope": lambda arm: arm.scope_days(SUB, FIRST, LAST)}
        for what, read in reads.items():
            with self.subTest(read=what):
                arm, fake, sleeps = reader(BILL)
                fake.limits = [(429, {"retry-after": "1"}), (429, {"retry-after": "1"})]
                read(arm)
                self.assertEqual((len(fake.calls), sleeps), (3, [1.0, 1.0]))

    def test_the_watch_says_that_the_cost_could_not_be_read_and_never_a_cost_of_nothing(self):
        """A Watch that Cost Management keeps turning away: the lead has no figure, its state is failed, and the figure of the page says so in the words of the page."""
        from cases import brief as brief_mod
        from cases.web import figures
        from test_web_support import make_case

        arm, fake, sleeps = reader(BILL)
        fake.limits = [(429, {"retry-after": "1"})] * 100
        estate = SimpleEstate(arm)
        collected = detectors.collect(estate, SUB, dt.datetime(2026, 11, 13, tzinfo=dt.timezone.utc), notes := [])
        context = collected.context
        self.assertEqual((context.costs, context.cost_error), (None, True))
        self.assertTrue(any("cost lines" in note for note in notes))
        lead = Lead("orphan-managed-disk", "/subscriptions/%s/resourceGroups/rg/providers/Microsoft.Compute/disks/d" % SUB, "microsoft.compute/disks", "d", "rg", SUB, "x", {}, "", {})
        (ranked,) = detectors.rank([lead], {SUB: context})
        self.assertEqual((ranked.cost_usd_30d, ranked.cost_state), (None, "failed"))
        case = make_case(cost_usd_30d=ranked.cost_usd_30d, cost_state=ranked.cost_state, saving_usd_month=None, resource_id=lead.resource_id)
        made = brief_mod.build_brief(case, None, now=dt.datetime(2026, 11, 13, tzinfo=dt.timezone.utc))
        figure = figures.figure_for([made], [figures.cost_of(made, case)])
        self.assertEqual((figure.state, figure.monthly, figure.note), ("none", None, "Cost could not be read just now."))
        self.assertEqual(figures.series_reason(made, case), "Cost could not be read just now. The next search reads it again.")


class SimpleEstate:
    """What the Watch's own read needs of an Arm for one subscription, answered by the reader above and with nothing else: no Advisor, no locks, no Resource Graph row."""

    def __init__(self, arm):
        self.arm = arm

    def __getattr__(self, name):
        if name in ("advisor_cost", "graph", "graph_many", "locks"):
            return lambda *args, **kwargs: []
        return getattr(self.arm, name)


class TheNameOfASubscription(unittest.TestCase):
    def reader(self, *answers):
        from test_arm import arm_with
        return arm_with(*answers)

    @staticmethod
    def named(name):
        return 200, {}, json.dumps({"id": f"/subscriptions/{SUB}", "subscriptionId": SUB, "displayName": name, "state": "Enabled"}).encode()

    def test_the_name_is_read_once_with_the_identity_that_reads_and_kept_for_the_run(self):
        arm, script = self.reader(self.named("contoso-dev"))
        self.assertEqual(arm.subscription_name(SUB), "contoso-dev")
        self.assertEqual(arm.subscription_name(SUB.upper()), "contoso-dev", "the id is read in lower case")
        self.assertEqual(len(script.calls), 1)
        ((method, url, headers, data, _),) = script.calls
        self.assertEqual((method, url, data), ("GET", f"https://management.azure.com/subscriptions/{SUB}?api-version=2022-12-01", None))
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")

    def test_the_list_of_the_subscriptions_that_the_run_reads_gives_the_names_and_no_more_call_is_made(self):
        listed = {"value": [{"subscriptionId": SUB, "displayName": "contoso-dev"}, {"subscriptionId": OTHER, "displayName": "  contoso   prod "}, {"subscriptionId": "x", "displayName": "no id"}]}
        arm, script = self.reader((200, {}, json.dumps(listed).encode()))
        arm.subscriptions()
        self.assertEqual((arm.subscription_name(SUB), arm.subscription_name(OTHER)), ("contoso-dev", "contoso prod"))
        self.assertEqual(len(script.calls), 1, "one read of the list and nothing for the names")

    def test_a_read_that_fails_is_a_name_of_nothing_and_is_not_asked_again_in_the_run(self):
        arm, script = self.reader((403, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right"}}'))
        self.assertEqual(arm.subscription_name(SUB), "")
        self.assertEqual(arm.subscription_name(SUB), "")
        self.assertEqual(len(script.calls), 1)

    def test_an_answer_with_no_name_or_with_a_name_that_is_not_text_is_a_name_of_nothing(self):
        for document in ({"subscriptionId": SUB}, {"displayName": None}, {"displayName": 5}, [], "text"):
            with self.subTest(document=str(document)):
                arm, _ = self.reader((200, {}, json.dumps(document).encode()))
                self.assertEqual(arm.subscription_name(SUB), "")

    def test_the_name_is_one_line_and_is_cut(self):
        arm, _ = self.reader(self.named("line one\nline two  " + "x" * 300))
        found = arm.subscription_name(SUB)
        self.assertEqual((found.startswith("line one line two xxx"), len(found), "\n" in found), (True, 120, False))

    def test_an_id_that_is_not_the_id_of_a_subscription_is_never_asked_for(self):
        arm, script = self.reader(self.named("never"))
        for bad in ("", None, "x", f"{SUB}/resourceGroups/rg", "../" + SUB, SUB + "0"):
            self.assertEqual(arm.subscription_name(bad), "", bad)
        self.assertEqual(script.calls, [])


if __name__ == "__main__":
    unittest.main()
