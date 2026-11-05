import datetime as dt
import json
import re
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from support import APP_ROOT  # noqa: F401  (puts the app on the path)

from cases.http import Client
from cases.memory_store import MemoryStore, stamp
from cases.models import (ActionRecord, CaseRecord, DecisionRecord, MailRecord, NoteRecord, PlanRecord, RunRecord, SettingsRecord, StoreError, SwitchRecord)
from cases.store import MAX_DATA, MAX_NONCE_DATA, RESOURCE, TableStore, table_calls

ACCOUNT = "stexample"
OID = "aaaaaaaa-1111-4222-8333-444444444444"
OTHER = "11111111-2222-3333-4444-555555555555"
T0 = dt.datetime(2026, 11, 5, 9, 0, 0, tzinfo=dt.timezone.utc)


class Clock:
    def __init__(self, start=T0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += dt.timedelta(**kwargs)


def tokens(text: str):
    return re.findall(r"\(|\)|'(?:[^']|'')*'|[A-Za-z0-9_.-]+", text)


def evaluate(text: str, row: dict) -> bool:
    """The part of OData's $filter that the store uses: eq ne ge le gt lt, and, or, parentheses, string literals."""
    items = tokens(text)
    position = 0

    def peek():
        return items[position] if position < len(items) else None

    def take():
        nonlocal position
        position += 1
        return items[position - 1]

    def comparison():
        if peek() == "(":
            take()
            value = disjunction()
            assert take() == ")"
            return value
        name, op, literal = take(), take(), take()
        assert literal.startswith("'"), literal
        wanted = literal[1:-1].replace("''", "'")
        have = row.get(name)
        have = "" if have is None else str(have)
        return {"eq": have == wanted, "ne": have != wanted, "ge": have >= wanted, "le": have <= wanted, "gt": have > wanted, "lt": have < wanted}[op]

    def conjunction():
        value = comparison()
        while peek() == "and":
            take()
            value = comparison() and value
        return value

    def disjunction():
        value = conjunction()
        while peek() == "or":
            take()
            value = conjunction() or value
        return value

    result = disjunction()
    assert position == len(items), f"filter not understood: {text}"
    return result


class FakeTables:
    """What the REST API of Azure Tables does for the calls that the store makes."""

    def __init__(self):
        self.tables: dict[str, dict[tuple[str, str], tuple[dict, int]]] = {}
        self.calls: list[tuple[str, str]] = []
        self.headers: list[dict] = []
        self.counter = 0

    def transport(self, method, url, headers, data, timeout):
        self.calls.append((method, url))
        self.headers.append(dict(headers))
        parts = urlsplit(url)
        path = unquote(parts.path)
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        body = json.loads(data.decode()) if data else None
        if method == "POST" and path == "/Tables":
            if body["TableName"] in self.tables:
                return 409, {}, b'{"odata.error":{"code":"TableAlreadyExists"}}'
            self.tables[body["TableName"]] = {}
            return 204, {}, b""
        entity = re.fullmatch(r"/(\w+)\(PartitionKey='([^']+)',RowKey='([^']+)'\)", path)
        listing = re.fullmatch(r"/(\w+)\(\)", path)
        if method == "POST" and re.fullmatch(r"/\w+", path):
            table = self.tables.get(path[1:])
            if table is None:
                return 404, {}, b'{"odata.error":{"code":"TableNotFound"}}'
            key = (body["PartitionKey"], body["RowKey"])
            if key in table:
                return 409, {}, b'{"odata.error":{"code":"EntityAlreadyExists"}}'
            self.counter += 1
            table[key] = (body, self.counter)
            return 204, {}, b""
        if entity:
            name, pk, rk = entity.groups()
            table = self.tables.get(name)
            if table is None:
                return 404, {}, b'{"odata.error":{"code":"TableNotFound"}}'
            current = table.get((pk, rk))
            if method == "GET":
                if current is None:
                    return 404, {}, b'{"odata.error":{"code":"ResourceNotFound"}}'
                return 200, {"etag": f'W/"{current[1]}"'}, json.dumps(current[0]).encode()
            match = headers.get("If-Match")
            if method == "PUT":
                if match and match != "*" and (current is None or match != f'W/"{current[1]}"'):
                    return (404 if current is None else 412), {}, b""
                if match == "*" and current is None:
                    return 404, {}, b""
                self.counter += 1
                table[(pk, rk)] = (body, self.counter)
                return 204, {}, b""
            if method == "DELETE":
                if current is None:
                    return 404, {}, b""
                if match and match != "*" and match != f'W/"{current[1]}"':
                    return 412, {}, b""
                del table[(pk, rk)]
                return 204, {}, b""
        if method == "GET" and listing:
            table = self.tables.get(listing.group(1))
            if table is None:
                return 404, {}, b'{"odata.error":{"code":"TableNotFound"}}'
            rows = [row for _, (row, _) in sorted(table.items())]
            if "$filter" in query:
                rows = [r for r in rows if evaluate(query["$filter"], r)]
            rows = rows[: int(query.get("$top", "1000"))]
            return 200, {}, json.dumps({"value": rows}).encode()
        return 400, {}, b"{}"


def case(case_id="k1", status="proposed", updated="2026-11-05T08:00:00Z", **extra):
    base = dict(case_id=case_id, resource_id=f"/subscriptions/s/resourceGroups/g/providers/Microsoft.Compute/disks/{case_id}", resource_name=case_id,
                resource_type="microsoft.compute/disks", resource_group="g", subscription_id="s", detector="orphan-managed-disk", run_id="r1", status=status,
                updated_at=updated, first_seen_at=updated)
    base.update(extra)
    return CaseRecord(**base)


def plan(plan_id="p1", state="open", created="2026-11-05T08:00:00Z"):
    return PlanRecord(plan_id=plan_id, case_id="k1", family="delete-disk", resource_id="/r", resource_name="n", resource_group="g", subscription_id="s", code="ABCD1234",
                      title="Delete a disk", what_changes="w", saving_usd_month=1.5, waiting_costs_usd_day=0.05, could_go_wrong="x", undo="none", evidence_level="e",
                      approvers=(OID,), created_at=created, expires_at="2026-11-08T08:00:00Z", state=state)


class StoreContract:
    """What every store must do, whatever it keeps the records in."""

    def make(self):
        raise NotImplementedError

    def setUp(self):
        self.clock = Clock()
        self.store = self.make()

    def test_runs_come_newest_first_and_a_later_put_of_the_same_run_replaces_it(self):
        self.store.run_put(RunRecord(run_id="a", trigger="timer", started_at="2026-11-04T05:30:00Z"))
        self.store.run_put(RunRecord(run_id="b", trigger="control", started_at="2026-11-05T05:30:00Z"))
        self.store.run_put(RunRecord(run_id="b", trigger="control", started_at="2026-11-05T05:30:00Z", finished_at="2026-11-05T05:31:00Z", leads=4, cases=3))
        runs = self.store.runs_recent(10)
        self.assertEqual([r.run_id for r in runs], ["b", "a"])
        self.assertEqual((runs[0].leads, runs[0].cases), (4, 3))
        self.assertEqual(len(self.store.runs_recent(1)), 1)

    def test_a_case_is_kept_by_its_id_and_listed_newest_first_and_by_status(self):
        self.store.case_put(case("k1", "proposed", "2026-11-05T08:00:00Z"))
        self.store.case_put(case("k2", "dropped", "2026-11-05T09:00:00Z", summary="s", objections=("a", "b"), guards=("locked",), models={"detective": "m"}, steps=({"step": "x", "ok": True},)))
        self.store.case_put(case("k1", "awaiting_ok", "2026-11-05T10:00:00Z"))
        self.assertEqual([c.case_id for c in self.store.cases_recent()], ["k1", "k2"])
        self.assertEqual([c.case_id for c in self.store.cases_recent(status="dropped")], ["k2"])
        got = self.store.case_get("k2")
        self.assertEqual((got.objections, got.guards, got.models, got.steps), (("a", "b"), ("locked",), {"detective": "m"}, ({"step": "x", "ok": True},)))
        self.assertIsNone(self.store.case_get("missing"))
        self.assertEqual(len(self.store.cases_recent(limit=1)), 1)

    def test_plans_open_holds_the_open_and_approved_ones(self):
        self.store.plan_put(plan("p1", "open", "2026-11-05T08:00:00Z"))
        self.store.plan_put(plan("p2", "approved", "2026-11-05T09:00:00Z"))
        self.store.plan_put(plan("p3", "consumed", "2026-11-05T10:00:00Z"))
        self.assertEqual([p.plan_id for p in self.store.plans_open()], ["p2", "p1"])
        self.assertEqual([p.plan_id for p in self.store.plans_recent(2)], ["p3", "p2"])
        self.store.plan_put(plan("p1", "declined", "2026-11-05T08:00:00Z"))
        self.assertEqual([p.plan_id for p in self.store.plans_open()], ["p2"])
        self.assertEqual(self.store.plan_get("p1").state, "declined")
        self.assertIsNone(self.store.plan_get("nope"))

    def test_one_decision_for_each_approver_and_plan_and_a_question_is_not_one(self):
        question = DecisionRecord(plan_id="p1", approver_oid=OID, approver_name="A", decision="ask", at="2026-11-05T08:55:00Z", plan_code="ABCD1234", note="why")
        first = DecisionRecord(plan_id="p1", approver_oid=OID, approver_name="A", decision="approve", at="2026-11-05T09:00:00Z", plan_code="ABCD1234")
        again = DecisionRecord(plan_id="p1", approver_oid=OID, approver_name="A", decision="decline", at="2026-11-05T09:05:00Z", plan_code="ABCD1234")
        other = DecisionRecord(plan_id="p1", approver_oid=OTHER, approver_name="B", decision="decline", at="2026-11-05T09:06:00Z", plan_code="ABCD1234")
        self.assertTrue(self.store.decision_put(question))
        self.assertTrue(self.store.decision_put(first))
        self.assertFalse(self.store.decision_put(again))
        self.assertTrue(self.store.decision_put(other))
        self.assertEqual([d.decision for d in self.store.decisions_of_plan("p1")], ["approve", "decline"])
        self.assertEqual([d.approver_oid for d in self.store.decisions_by(OID)], [OID])
        self.assertEqual(self.store.decisions_by(OID)[0].decision, "approve")

    def test_an_action_per_plan(self):
        self.assertIsNone(self.store.action_get("p1"))
        self.store.action_put(ActionRecord(plan_id="p1", case_id="k1", family="delete-disk", resource_id="/r", state="queued", queued_at="2026-11-05T09:00:00Z"))
        self.store.action_put(ActionRecord(plan_id="p1", case_id="k1", family="delete-disk", resource_id="/r", state="done", queued_at="2026-11-05T09:00:00Z",
                                           verification={"gone": True}))
        self.assertEqual(self.store.action_get("p1").state, "done")
        self.assertEqual(self.store.action_get("p1").verification, {"gone": True})
        self.assertEqual([a.plan_id for a in self.store.actions_recent()], ["p1"])

    def test_the_action_of_a_plan_is_claimed_once_and_released_only_while_it_has_not_started(self):
        queued = ActionRecord(plan_id="p9", case_id="k1", family="delete-disk", resource_id="/r", state="queued", queued_at="2026-11-05T09:00:00Z")
        rival = ActionRecord(plan_id="p9", case_id="k1", family="delete-disk", resource_id="/r", state="queued", queued_at="2026-11-05T09:00:01Z", correlation_id="rival")
        self.assertTrue(self.store.action_claim(queued))
        self.assertFalse(self.store.action_claim(rival), "the second claim of the same plan loses")
        self.assertEqual(self.store.action_get("p9"), queued, "and changes nothing")
        self.store.action_release("p9")
        self.assertIsNone(self.store.action_get("p9"))
        self.assertTrue(self.store.action_claim(rival), "a released claim can be made again")
        self.store.action_put(ActionRecord(plan_id="p9", case_id="k1", family="delete-disk", resource_id="/r", state="running", queued_at="2026-11-05T09:00:01Z",
                                           started_at="2026-11-05T09:00:05Z"))
        self.store.action_release("p9")
        self.assertEqual(self.store.action_get("p9").state, "running", "an action that has started is never released")
        self.store.action_release("nothing-here")
        self.assertFalse(self.store.action_claim(queued))

    def test_switches_start_released_and_keep_what_was_set(self):
        self.assertEqual([s.paused for s in self.store.switches()], [False, False, False])
        self.store.switch_put(SwitchRecord(name="changes", paused=True, by=OID, at="2026-11-05T09:00:00Z", reason="drill"))
        self.assertTrue(self.store.switch_get("changes").paused)
        self.assertFalse(self.store.switch_get("all").paused)
        with self.assertRaises((StoreError, ValueError)):
            self.store.switch_get("nothing")

    def test_settings_default_save_and_delete(self):
        self.assertEqual(self.store.settings_get(OID), SettingsRecord(oid=OID))
        changed = SettingsRecord(oid=OID, channel="desk", weekly_budget=1, working_days=(1, 3), mutes=("digest",), paused_until="2026-12-01")
        self.store.settings_put(changed)
        self.assertEqual(self.store.settings_get(OID), changed)
        self.store.settings_delete(OID)
        self.assertEqual(self.store.settings_get(OID), SettingsRecord(oid=OID))

    def test_notes_and_the_do_not_touch_marks_that_have_not_expired(self):
        rid = "/subscriptions/s/resourceGroups/G/providers/Microsoft.Compute/disks/d"
        live = NoteRecord(note_id="n1", oid=OID, kind="do_not_touch", text="keep", scope_resource_id=rid, created_at="2026-11-05T08:00:00Z", expires_at="2026-12-05T08:00:00Z")
        old = NoteRecord(note_id="n2", oid=OID, kind="do_not_touch", text="old", scope_resource_id="/x", created_at="2026-10-01T08:00:00Z", expires_at="2026-11-01T08:00:00Z")
        plain = NoteRecord(note_id="n3", oid=OID, kind="note", text="hi", scope_resource_id="/y", created_at="2026-11-05T07:00:00Z", expires_at="2026-12-05T08:00:00Z")
        for note in (live, old, plain):
            self.store.note_put(note)
        self.assertEqual([n.note_id for n in self.store.notes_of(OID)], ["n1", "n3", "n2"])
        self.assertEqual(self.store.notes_of(OTHER), [])
        self.assertEqual(self.store.do_not_touch(), {rid.lower()})
        self.store.note_delete(OID, "n1")
        self.assertEqual(self.store.do_not_touch(), set())

    def test_a_one_time_token_works_once_for_its_person_and_purpose_and_expires(self):
        token = self.store.nonce_new(OID, "plan-1", 60)
        self.assertFalse(self.store.nonce_use(token, OTHER, "plan-1"))
        self.assertFalse(self.store.nonce_use(token, OID, "plan-2"))
        self.assertTrue(self.store.nonce_use(token, OID, "plan-1"))
        self.assertFalse(self.store.nonce_use(token, OID, "plan-1"))
        late = self.store.nonce_new(OID, "plan-1", 60)
        self.clock.advance(seconds=61)
        self.assertFalse(self.store.nonce_use(late, OID, "plan-1"))
        self.assertFalse(self.store.nonce_use("not-a-token", OID, "plan-1"))
        self.assertFalse(self.store.nonce_use("", OID, "plan-1"))

    def test_a_one_time_token_can_hold_data_that_is_given_back_once_to_the_same_person_and_purpose(self):
        data = json.dumps({"verifier": "v" * 43, "nonce": "n" * 22})
        token = self.store.nonce_new(OID, "signin:p1", 600, data)
        self.assertIsNone(self.store.nonce_take(token, OTHER, "signin:p1"), "another person gets nothing, and the token stays for the right one")
        self.assertIsNone(self.store.nonce_take(token, OID, "signin:p2"))
        self.assertEqual(self.store.nonce_take(token, OID, "signin:p1"), data)
        self.assertIsNone(self.store.nonce_take(token, OID, "signin:p1"), "it is given back once")

    def test_a_token_without_data_gives_back_an_empty_text_and_not_nothing(self):
        token = self.store.nonce_new(OID, "plan-1", 60)
        self.assertEqual(self.store.nonce_take(token, OID, "plan-1"), "")

    def test_an_expired_token_gives_back_nothing_and_is_gone(self):
        token = self.store.nonce_new(OID, "p", 60, "a-verifier")
        self.clock.advance(seconds=61)
        self.assertIsNone(self.store.nonce_take(token, OID, "p"))
        self.assertIsNone(self.store.nonce_take(token, OID, "p"))
        self.assertFalse(self.store.nonce_use(token, OID, "p"))

    def test_a_token_that_is_used_with_nonce_use_takes_its_data_with_it(self):
        token = self.store.nonce_new(OID, "p", 60, "a-verifier")
        self.assertTrue(self.store.nonce_use(token, OID, "p"))
        self.assertIsNone(self.store.nonce_take(token, OID, "p"))

    def test_mails_since_counts_the_messages_of_one_person(self):
        for index, when in enumerate(("2026-11-03T09:00:00Z", "2026-11-05T09:00:00Z", "2026-11-05T10:00:00Z")):
            self.store.mail_put(MailRecord(mail_id=f"m{index}", oid=OID, kind="digest", subject="s", sent_at=when, status="sent"))
        self.store.mail_put(MailRecord(mail_id="x", oid=OTHER, kind="digest", subject="s", sent_at="2026-11-05T09:30:00Z", status="sent"))
        self.assertEqual([m.mail_id for m in self.store.mails_since(OID, "2026-11-05T00:00:00Z")], ["m1", "m2"])
        self.assertEqual(len(self.store.mails_since(OID, "2026-11-01T00:00:00Z")), 3)


class MemoryStoreMeetsTheContract(StoreContract, unittest.TestCase):
    def make(self):
        return MemoryStore(clock=self.clock)


class TableStoreMeetsTheContract(StoreContract, unittest.TestCase):
    def make(self):
        self.service = FakeTables()
        self.minted = []

        def token(resource):
            self.minted.append(resource)
            return "token-value"

        client = Client(table_calls(ACCOUNT), lambda text: text, transport=self.service.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        return TableStore(client, token, ACCOUNT, clock=self.clock)


class TableStoreOnItsOwn(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.service = FakeTables()
        self.minted = []
        client = Client(table_calls(ACCOUNT), lambda text: text, transport=self.service.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        self.store = TableStore(client, lambda r: (self.minted.append(r), "token-value")[1], ACCOUNT, clock=self.clock)

    def test_every_call_goes_to_the_accounts_table_service_with_a_token_for_storage_and_nothing_else(self):
        self.store.case_put(case("k1"))
        self.store.case_get("k1")
        self.store.cases_recent()
        self.assertTrue(all(url.startswith(f"https://{ACCOUNT}.table.core.windows.net/") for _, url in self.service.calls))
        self.assertEqual(set(self.minted), {RESOURCE})
        for headers in self.service.headers:
            self.assertEqual(headers["Authorization"], "Bearer token-value")
            self.assertEqual(sorted(k for k in headers if k.lower() in ("authorization", "x-ms-version", "x-ms-date")), ["Authorization", "x-ms-date", "x-ms-version"])
            self.assertFalse(any(k.lower() in ("sharedkey", "x-ms-signature") for k in headers))

    def test_a_table_is_made_once_and_only_when_it_is_first_written(self):
        self.store.case_put(case("k1"))
        self.store.case_put(case("k2"))
        creations = [c for c in self.service.calls if c[1].endswith("/Tables")]
        self.assertEqual(len(creations), 1)
        self.assertEqual(list(self.service.tables), ["mncases"])

    def test_a_read_never_makes_a_table_and_a_table_that_is_not_there_has_no_rows(self):
        self.assertEqual(self.store.cases_recent(), [])
        self.assertEqual(self.store.runs_recent(), [])
        self.assertEqual(self.store.plans_open(), [])
        self.assertIsNone(self.store.case_get("k1"))
        self.assertIsNone(self.store.plan_get("p1"))
        self.assertEqual(self.store.mails_since(OID, "2000-01-01T00:00:00Z"), [])
        self.assertFalse(self.store.nonce_use("x" * 24, OID, "p"))
        self.assertEqual({m for m, _ in self.service.calls}, {"GET"}, "only reads were made")
        self.assertEqual(self.service.tables, {})

    def test_the_methods_are_the_ones_on_the_list_and_a_call_to_another_table_is_refused(self):
        self.store.case_put(case("k1"))
        self.store.nonce_use("x" * 24, OID, "p")
        self.assertTrue({m for m, _ in self.service.calls} <= {"GET", "POST", "PUT", "DELETE"})
        client = self.store.client
        with self.assertRaises(Exception):
            client.request("PUT", f"https://{ACCOUNT}.table.core.windows.net/other(PartitionKey='a',RowKey='b')", body={})
        with self.assertRaises(Exception):
            client.request("DELETE", f"https://{ACCOUNT}.table.core.windows.net/Tables('mncases')")
        with self.assertRaises(Exception):
            client.request("GET", "https://example.com/mncases()")

    def test_a_key_with_a_character_that_a_key_may_not_have_is_refused_before_a_call(self):
        before = len(self.service.calls)
        with self.assertRaises(StoreError):
            self.store.case_get("a/b")
        with self.assertRaises(StoreError):
            self.store.case_get("a'b")
        self.assertEqual(len(self.service.calls), before)

    def test_a_record_that_is_too_large_is_refused(self):
        with self.assertRaises(StoreError):
            self.store.case_put(case("k1", summary="x" * (MAX_DATA + 1)))

    def test_an_error_of_the_service_is_a_store_error_with_its_status(self):
        def failing(method, url, headers, data, timeout):
            return 403, {}, b'{"odata.error":{"code":"AuthorizationPermissionMismatch"}}'

        client = Client(table_calls(ACCOUNT), lambda text: text, transport=failing, sleep=lambda s: None, monotonic=lambda: 0.0)
        store = TableStore(client, lambda r: "t", ACCOUNT, clock=self.clock)
        with self.assertRaises(StoreError) as caught:
            store.switch_get("all")
        self.assertEqual(caught.exception.status, 403)
        self.assertNotIn("token", str(caught.exception).lower())

    def test_expired_one_time_tokens_are_purged(self):
        old = self.store.nonce_new(OID, "a", 10)
        fresh = self.store.nonce_new(OID, "a", 3600)
        self.clock.advance(seconds=120)
        self.assertEqual(self.store.nonces_purge(), 1)
        self.assertFalse(self.store.nonce_use(old, OID, "a"))
        self.assertTrue(self.store.nonce_use(fresh, OID, "a"))

    def test_the_token_is_stored_only_as_a_digest(self):
        token = self.store.nonce_new(OID, "a", 60)
        for table in self.service.tables.values():
            for (_, key), (row, _) in table.items():
                self.assertNotIn(token, json.dumps(row))
                self.assertNotEqual(key, token)

    def test_the_data_of_a_token_is_in_the_row_and_never_in_a_key_or_a_web_address(self):
        token = self.store.nonce_new(OID, "a", 60, "the-verifier-text")
        self.assertFalse(any("the-verifier-text" in url or token in url for _, url in self.service.calls), "only the digest of the token is in an address")
        rows = [row for table in self.service.tables.values() for (_, key), (row, _) in table.items()]
        self.assertEqual([row.get("payload") for row in rows], ["the-verifier-text"])
        self.assertEqual(self.store.nonce_take(token, OID, "a"), "the-verifier-text")

    def test_data_that_is_too_large_for_a_token_is_refused_before_any_call(self):
        before = len(self.service.calls)
        with self.assertRaises(StoreError):
            self.store.nonce_new(OID, "a", 60, "x" * (MAX_NONCE_DATA + 1))
        self.assertEqual(len(self.service.calls), before)
        self.store.nonce_new(OID, "a", 60, "x" * MAX_NONCE_DATA)

    def test_a_name_that_is_not_a_storage_account_is_refused(self):
        for name in ("", "UPPER", "has-dash", "x" * 25, "ab"):
            with self.assertRaises(StoreError):
                TableStore(self.store.client, lambda r: "t", name)


if __name__ == "__main__":
    unittest.main()
