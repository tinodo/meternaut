import datetime as dt
import json
import unittest
from dataclasses import replace

from support import APP_ROOT  # noqa: F401

from cases.approvals import Approvals, ApprovalSettings
from cases.detectors import Lead
from cases.http import Client, HttpError, Refused
from cases.memory_store import MemoryStore, stamp
from cases.models import ActionRecord, CaseRecord, NoteRecord, Principal, SwitchRecord
from cases.runner import Executed, RunnerServices, change_calls, execute, read_calls, tick

OID = "aaaaaaaa-1111-4222-8333-444444444444"
SUB = "bbbbbbbb-2222-4333-9444-555555555555"
GROUP = "meternaut-sc-rg"
NOW = dt.datetime(2026, 11, 5, 9, 0, 0, tzinfo=dt.timezone.utc)
SETTINGS = ApprovalSettings(change_group=GROUP)
APPROVER = Principal(OID, "Tino", ("owner", "approver", "ops"))
DISK = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/planted-disk-1"
IP = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Network/publicIPAddresses/planted-ip-1"


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += dt.timedelta(**kwargs)


class FakeAzure:
    """Resource Manager, for the calls of the change and of the checks: a few resources, their locks, and a delete that takes effect after some reads.

    It answers like Azure does for a person who may not do something: a 403 with the error AuthorizationFailed."""

    def __init__(self):
        self.resources = {
            DISK.lower(): {"id": DISK, "name": "planted-disk-1", "tags": {"meternaut-planted": "demo"}, "properties": {"diskState": "Unattached"}},
            IP.lower(): {"id": IP, "name": "planted-ip-1", "tags": {"meternaut-planted": "demo"}, "properties": {}},
        }
        self.locks: dict[str, list] = {}
        self.calls: list[tuple[str, str]] = []
        self.headers: list[dict] = []
        self.delete_status = 200
        self.reads_before_gone = 1
        self.pending: dict[str, int] = {}
        self.fail_reads = False
        self.read_status = 200
        self.locks_status = 200

    def transport(self, method, url, headers, data, timeout):
        self.calls.append((method, url))
        self.headers.append(dict(headers))
        path = url.split("?")[0].replace("https://management.azure.com", "")
        key = path.lower()
        if "/providers/microsoft.authorization/locks" in key:
            if self.locks_status >= 300:
                return self.locks_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right to read the locks"}}'
            scope = key.split("/providers/microsoft.authorization/locks")[0]
            return 200, {}, json.dumps({"value": self.locks.get(scope, [])}).encode()
        if self.fail_reads and method == "GET":
            return 500, {}, b"{}"
        if method == "GET":
            if self.read_status >= 300:
                return self.read_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right to read"}}'
            if key in self.pending:
                self.pending[key] -= 1
                if self.pending[key] < 0:
                    del self.pending[key]
                    self.resources.pop(key, None)
            if key not in self.resources:
                return 404, {}, b'{"error":{"code":"ResourceNotFound","message":"gone"}}'
            return 200, {}, json.dumps(self.resources[key]).encode()
        if method == "DELETE":
            if self.delete_status >= 300:
                return self.delete_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right to delete"}}'
            if key not in self.resources:
                return 204, {}, b""
            self.pending[key] = self.reads_before_gone
            return self.delete_status, {}, b""
        return 405, {}, b"{}"


class FakeArm:
    def __init__(self, totals=None, fail=False):
        self.totals, self.fail, self.asked = totals or {}, fail, []

    def costs(self, subscription, start, end):
        self.asked.append((subscription, start, end))
        if self.fail:
            raise HttpError(500, "boom")
        return self.totals, "USD"


def lead_for(resource_id, detector, name, tags=None):
    kind = "microsoft.compute/disks" if "disks" in resource_id else "microsoft.network/publicipaddresses"
    return Lead(detector=detector, resource_id=resource_id, resource_type=kind, name=name, resource_group=GROUP, subscription_id=SUB, location="swedencentral",
                tags={"meternaut-planted": "demo"} if tags is None else tags, managed_by="", facts={}, age_days=0)


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = MemoryStore(clock=self.clock)
        self.azure = FakeAzure()
        self.events = []
        self.sleeps = []
        self.person_tokens = []
        self.reader_tokens = []
        change = Client(change_calls(SUB, GROUP), lambda t: t, transport=self.azure.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        check = Client(read_calls(SUB, GROUP), lambda t: t, transport=self.azure.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        self.arm = FakeArm()
        emit = lambda kind, **f: self.events.append((kind, f))  # noqa: E731
        # `s` makes a change with the token of the person who approved it; `t` is the timer's: the reader's token and no write on its list.
        self.s = RunnerServices(self.store, change, lambda r: (self.person_tokens.append(r), "person-token")[1], SETTINGS, SUB, clock=self.clock,
                                sleep=self.sleeps.append, emit=emit)
        self.t = RunnerServices(self.store, check, lambda r: (self.reader_tokens.append(r), "reader-token")[1], SETTINGS, SUB, arm=self.arm, clock=self.clock,
                                sleep=self.sleeps.append, emit=emit)
        self.approvals = Approvals(self.store, SETTINGS, self.clock)

    def approved(self, resource_id=DISK, detector="orphan-managed-disk", name="planted-disk-1", cost=None):
        """A plan that a person approved at the sign-in to Azure: the decision is recorded and the action waits to be made."""
        item = lead_for(resource_id, detector, name)
        case = CaseRecord(case_id="k" + item.lead_id, resource_id=resource_id, resource_name=name, resource_type=item.resource_type, resource_group=GROUP,
                          subscription_id=SUB, detector=detector, run_id="r1", status="proposed", recommendation="delete", confidence=0.9, cost_usd_30d=cost,
                          saving_usd_month=cost, updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        self.store.case_put(case)
        plan = self.approvals.create(case, item, (OID,))
        checked, refusal = self.approvals.check_approve(APPROVER, plan.plan_id, plan.code)
        assert refusal is None, refusal
        result, action = self.approvals.record_approval(APPROVER, checked, "")
        assert result.kind == "recorded", result
        return plan, action

    def make_change(self, plan):
        """Makes the change of the plan's action with the person's token, as the sign-in to Azure does."""
        return execute(self.s, self.store.action_get(plan.plan_id))


class TheListsOfCalls(unittest.TestCase):
    def setUp(self):
        self.change = Client(change_calls(SUB, GROUP), lambda t: t, transport=lambda *a: (200, {}, b"{}"), sleep=lambda s: None, monotonic=lambda: 0.0)
        self.check = Client(read_calls(SUB, GROUP), lambda t: t, transport=lambda *a: (200, {}, b"{}"), sleep=lambda s: None, monotonic=lambda: 0.0)

    def test_a_change_reads_and_deletes_a_disk_and_a_public_ip_address_in_the_one_group_and_reads_locks(self):
        base = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
        for method, path in (("GET", "/Microsoft.Compute/disks/d1"), ("DELETE", "/Microsoft.Compute/disks/d1"), ("GET", "/Microsoft.Network/publicIPAddresses/ip1"),
                             ("DELETE", "/Microsoft.Network/publicIPAddresses/ip1")):
            with self.subTest(method=method, path=path):
                self.change.request(method, base + path + "?api-version=2024-03-02")
        for scope in (f"/subscriptions/{SUB}", f"/subscriptions/{SUB}/resourceGroups/{GROUP}", DISK):
            self.change.request("GET", f"https://management.azure.com{scope}/providers/Microsoft.Authorization/locks?api-version=2016-09-01")

    def test_the_checks_of_the_timer_read_the_same_things_and_can_not_even_attempt_a_delete(self):
        base = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
        for path in ("/Microsoft.Compute/disks/d1", "/Microsoft.Network/publicIPAddresses/ip1"):
            self.check.request("GET", base + path + "?api-version=2024-03-02")
            with self.assertRaises(Refused):
                self.check.request("DELETE", base + path + "?api-version=2024-03-02")
        self.check.request("GET", f"https://management.azure.com{DISK}/providers/Microsoft.Authorization/locks?api-version=2016-09-01")
        self.assertEqual({method for method, _ in read_calls(SUB, GROUP)}, {"GET"})

    def test_everything_else_is_refused_by_both_lists(self):
        other = "22222222-2222-2222-2222-222222222222"
        base = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
        refused = [
            ("DELETE", f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/other-rg/providers/Microsoft.Compute/disks/d1"),
            ("DELETE", f"https://management.azure.com/subscriptions/{other}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/d1"),
            ("DELETE", base + "/Microsoft.Compute/virtualMachines/vm1"),
            ("DELETE", base + "/Microsoft.Storage/storageAccounts/sa1"),
            ("DELETE", f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}"),
            ("DELETE", f"https://management.azure.com/subscriptions/{SUB}"),
            ("PUT", base + "/Microsoft.Compute/disks/d1"),
            ("PATCH", base + "/Microsoft.Compute/disks/d1"),
            ("POST", base + "/Microsoft.Compute/disks/d1/beginGetAccess"),
            ("POST", base + "/Microsoft.Compute/disks/d1"),
            ("DELETE", base + "/Microsoft.Compute/disks/d1/extra"),
            ("DELETE", f"https://management.azure.com/subscriptions/{SUB}/providers/Microsoft.Authorization/locks/x"),
            ("GET", "https://example.com/subscriptions/" + SUB),
            ("GET", base + "/Microsoft.Compute/virtualMachines/vm1"),
        ]
        for client in (self.change, self.check):
            for method, url in refused:
                with self.subTest(method=method, url=url):
                    with self.assertRaises(Refused):
                        client.request(method, url)

    def test_the_only_deletes_are_the_two_kinds(self):
        deletes = [pattern.pattern for method, pattern in change_calls(SUB, GROUP) if method == "DELETE"]
        self.assertEqual(len(deletes), 2)
        self.assertTrue(all("disks" in p or "publicIPAddresses" in p for p in deletes))


class TheChange(Base):
    def test_an_approved_disk_is_deleted_after_a_new_read_and_the_records_say_so(self):
        plan, action = self.approved()
        done = self.make_change(plan)
        self.assertIsInstance(done, Executed)
        self.assertEqual((done.kind, done.action.state, done.action.verification.get("gone")), ("ran", "done", True))
        self.assertEqual(self.store.action_get(plan.plan_id), done.action)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "consumed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "done")
        self.assertNotIn(DISK.lower(), self.azure.resources)
        methods = [m for m, _ in self.azure.calls]
        self.assertEqual(methods.count("DELETE"), 1)
        self.assertLess(methods.index("GET"), methods.index("DELETE"), "it reads before it deletes")
        self.assertIn(("action.started", {"planId": plan.plan_id, "family": "delete-disk", "correlationId": action.correlation_id}), self.events)
        self.assertEqual(self.events[-1], ("action.finished", {"planId": plan.plan_id, "family": "delete-disk", "ok": True}))

    def test_a_public_ip_address_is_deleted_the_same_way(self):
        plan, _ = self.approved(IP, "orphan-public-ip", "planted-ip-1")
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"))
        self.assertNotIn(IP.lower(), self.azure.resources)

    def test_every_call_carries_the_token_of_the_person_and_the_correlation_id_goes_on_the_delete(self):
        plan, action = self.approved()
        self.make_change(plan)
        self.assertEqual(set(self.person_tokens), {"https://management.azure.com/"})
        self.assertEqual(self.reader_tokens, [], "the reader's token is not used for a change")
        self.assertTrue(all(h["Authorization"] == "Bearer person-token" for h in self.azure.headers))
        delete_headers = [h for (m, _), h in zip(self.azure.calls, self.azure.headers) if m == "DELETE"]
        self.assertEqual(delete_headers[0]["x-ms-correlation-request-id"], action.correlation_id)

    def test_the_delete_is_made_once_and_never_retried(self):
        plan, _ = self.approved()
        original = self.azure.transport
        counted = []

        def flaky(method, url, headers, data, timeout):
            if method == "DELETE":
                counted.append(1)
                return 503, {}, b'{"error":{"code":"ServerBusy","message":"later"}}'
            return original(method, url, headers, data, timeout)

        self.s.client.transport = flaky
        done = self.make_change(plan)
        self.assertEqual(len(counted), 1, "a delete that failed is not made again")
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"))

    def stops(self, expect_in_text, mutate=None, plan_mutate=None):
        plan, action = self.approved()
        if mutate:
            mutate()
        if plan_mutate:
            self.store.plan_put(replace(self.store.plan_get(plan.plan_id), **plan_mutate))
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
        self.assertIn(expect_in_text, done.action.result)
        self.assertIn("Nothing was changed", done.action.result)
        self.assertNotIn("DELETE", [m for m, _ in self.azure.calls])
        self.assertIn(DISK.lower(), self.azure.resources)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "failed")

    def test_it_stops_when_the_disk_has_been_attached_since(self):
        self.stops("not unattached any more", lambda: self.azure.resources[DISK.lower()]["properties"].update(diskState="Attached"))

    def test_it_stops_when_changes_were_paused_after_the_approval_and_nothing_is_deleted(self):
        self.stops("paused after the approval", lambda: self.store.switch_put(SwitchRecord(name="changes", paused=True, by=OID, at=stamp(NOW))))

    def test_a_resource_that_is_gone_already_is_not_stopped_by_a_pulled_switch_because_nothing_is_changed(self):
        plan, _ = self.approved()
        self.azure.resources.pop(DISK.lower())
        self.store.switch_put(SwitchRecord(name="all", paused=True, by=OID, at=stamp(NOW)))
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"))

    def test_it_stops_when_the_disk_is_managed_by_a_machine(self):
        self.stops("not unattached any more", lambda: self.azure.resources[DISK.lower()].update(managedBy="/vm"))

    def test_it_stops_when_the_tag_is_gone(self):
        self.stops("tag any more", lambda: self.azure.resources[DISK.lower()].update(tags={}))

    def test_it_stops_when_a_lock_exists_on_the_resource_or_the_group(self):
        self.stops("management lock", lambda: self.azure.locks.update({DISK.lower(): [{"name": "l"}]}))

    def test_it_stops_when_the_group_has_a_lock(self):
        self.stops("management lock", lambda: self.azure.locks.update({f"/subscriptions/{SUB}/resourcegroups/{GROUP}".lower(): [{"name": "l"}]}))

    def test_it_stops_when_a_person_marked_the_resource_do_not_touch_after_the_plan(self):
        self.stops("do-not-touch", lambda: self.store.note_put(NoteRecord(note_id="n", oid=OID, kind="do_not_touch", text="no", scope_resource_id=DISK,
                                                                           expires_at="2099-01-01T00:00:00Z")))

    def test_it_stops_when_azure_answers_with_another_resource(self):
        self.stops("another resource", lambda: self.azure.resources[DISK.lower()].update(id=DISK.replace("planted-disk-1", "other")))

    def test_it_stops_when_the_plan_names_another_group_family_or_precondition(self):
        for label, change in {
            "group": {"resource_id": DISK.replace(GROUP, "other-rg")},
            "family": {"family": "delete-public-ip"},
            "precondition": {"preconditions": {"family": "delete-disk", "tag": "meternaut-planted", "resourceGroup": "other-rg"}},
        }.items():
            with self.subTest(label):
                self.setUp()
                self.stops("a change may be made on" if label != "precondition" else "preconditions", plan_mutate=change)

    def test_it_stops_when_a_guard_cannot_be_read(self):
        plan, _ = self.approved()
        self.azure.fail_reads = True
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"))
        self.assertIn("Nothing was changed", done.action.result)

    def test_it_does_nothing_for_a_plan_without_a_recorded_approval_or_a_wrong_code(self):
        plan, _ = self.approved()
        self.store.decisions.clear()
        self.assertEqual(self.make_change(plan).action.state, "failed")
        self.assertEqual(self.azure.calls, [])
        self.setUp()
        plan, _ = self.approved()
        key = (plan.plan_id, OID)
        self.store.decisions[key] = replace(self.store.decisions[key], plan_code="00000000")
        self.assertEqual(self.make_change(plan).action.state, "failed")
        self.assertEqual(self.azure.calls, [])

    def test_a_resource_that_is_gone_already_is_done_with_nothing_to_delete(self):
        plan, _ = self.approved()
        del self.azure.resources[DISK.lower()]
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"))
        self.assertIn("did not exist", done.action.result)
        self.assertNotIn("DELETE", [m for m, _ in self.azure.calls])


class WhenAzureRefusesThePerson(Base):
    """Azure checks the person's own rights: a person who may not do something gets a 403, and nothing changes."""

    def refused(self, plan, where):
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("azure_refused", "failed"), done.action.result)
        self.assertIn("Azure refused to " + where, done.action.result)
        self.assertIn("(403, AuthorizationFailed)", done.action.result)
        self.assertIn("your account has no right to do this here", done.action.result)
        self.assertIn("Nothing was changed", done.action.result)
        self.assertIn(DISK.lower(), self.azure.resources)
        self.assertNotIn("DELETE", [m for m, _ in self.azure.calls])
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "failed")
        self.assertEqual(self.events[-1], ("action.finished", {"planId": plan.plan_id, "family": "delete-disk", "ok": False}))

    def test_a_person_who_may_not_read_the_resource_is_refused_before_anything_else(self):
        plan, _ = self.approved()
        self.azure.read_status = 403
        self.refused(plan, "read the resource")

    def test_a_person_who_may_not_read_the_locks_is_refused_and_the_unread_guard_counts_as_on(self):
        plan, _ = self.approved()
        self.azure.locks_status = 403
        self.refused(plan, "read the locks")

    def test_a_person_who_may_not_delete_is_refused_by_azure_and_the_resource_stays(self):
        plan, _ = self.approved()
        self.azure.delete_status = 403
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("azure_refused", "failed"))
        self.assertIn("Azure refused to delete the resource (403, AuthorizationFailed)", done.action.result)
        self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 1)
        self.assertIn(DISK.lower(), self.azure.resources)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")

    def test_a_token_that_azure_does_not_accept_is_refused_the_same_way(self):
        plan, _ = self.approved()
        self.azure.delete_status = 401
        self.assertEqual(self.make_change(plan).kind, "azure_refused")

    def test_a_failed_delete_that_is_not_a_refusal_is_a_failure_that_says_to_look_at_the_resource(self):
        plan, _ = self.approved()
        self.azure.delete_status = 500
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"))
        self.assertIn("refused or failed", done.action.result)
        self.assertIn("Check the resource", done.action.result)


class AfterTheDelete(Base):
    def test_a_delete_that_azure_accepted_but_that_still_shows_is_unknown_not_done(self):
        plan, _ = self.approved()
        self.azure.reads_before_gone = 99
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("ran_unconfirmed", "unknown"))
        self.assertEqual(len(self.sleeps), 5)
        self.assertEqual(set(self.sleeps), {5})
        self.assertEqual(self.store.case_get(plan.case_id).status, "running")

    def test_a_delete_that_takes_a_few_reads_to_show_is_waited_for(self):
        plan, _ = self.approved()
        self.azure.reads_before_gone = 3
        self.assertEqual(self.make_change(plan).kind, "ran")
        self.assertGreaterEqual(len(self.sleeps), 2)

    def test_a_network_error_on_the_delete_is_unknown_and_a_later_check_settles_it(self):
        plan, _ = self.approved()
        original = self.azure.transport

        def flaky(method, url, headers, data, timeout):
            if method == "DELETE":
                raise OSError("reset")
            return original(method, url, headers, data, timeout)

        self.s.client.transport = flaky
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "unknown"))
        self.s.client.transport = original
        del self.azure.resources[DISK.lower()]
        self.clock.advance(minutes=5)
        tick(self.t)
        self.assertEqual(self.store.action_get(plan.plan_id).state, "done")
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "consumed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "done")


class TheTick(Base):
    """The timer: it closes plans, closes an approval whose change never started, and checks afterwards. It makes no change."""

    def test_the_timer_makes_no_change_even_for_an_action_that_waits(self):
        plan, _ = self.approved()
        self.clock.advance(minutes=5)
        result = tick(self.t)
        self.assertEqual(result.finished, [])
        self.assertEqual(self.store.action_get(plan.plan_id).state, "queued")
        self.assertEqual(self.azure.calls, [])
        self.assertIn(DISK.lower(), self.azure.resources)

    def test_an_approval_whose_change_never_started_is_closed_with_nothing_changed(self):
        plan, _ = self.approved()
        self.clock.advance(minutes=11)
        result = tick(self.t)
        self.assertEqual([a.state for a in result.finished], ["failed"])
        action = self.store.action_get(plan.plan_id)
        self.assertEqual(action.state, "failed")
        self.assertIn("did not start", action.result)
        self.assertIn("Nothing was changed", action.result)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "failed")
        self.assertEqual(self.azure.calls, [])
        self.assertIn(DISK.lower(), self.azure.resources)

    def test_the_timer_uses_the_readers_token_and_its_list_has_no_delete(self):
        plan, _ = self.approved()
        self.s.client.transport = self.azure.transport
        self.make_change(plan)
        self.clock.advance(minutes=1)
        self.azure.calls.clear()
        self.azure.headers.clear()
        self.azure.resources[DISK.lower()] = {"id": DISK, "tags": {"meternaut-planted": "x"}, "properties": {"diskState": "Unattached"}}
        self.store.action_put(replace(self.store.action_get(plan.plan_id), state="unknown", verification={}))
        tick(self.t)
        self.assertTrue(self.azure.headers)
        self.assertTrue(all(h["Authorization"] == "Bearer reader-token" for h in self.azure.headers))
        self.assertEqual({m for m, _ in self.azure.calls}, {"GET"})

    def test_expired_plans_are_closed(self):
        item = lead_for(DISK, "orphan-managed-disk", "planted-disk-1")
        case = CaseRecord(case_id="k1", resource_id=DISK, resource_name="n", resource_type="t", resource_group=GROUP, subscription_id=SUB, detector="orphan-managed-disk",
                          run_id="r", status="proposed", recommendation="delete", updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        self.store.case_put(case)
        plan = self.approvals.create(case, item, (OID,))
        self.clock.advance(hours=73)
        self.assertEqual([p.plan_id for p in tick(self.t).expired], [plan.plan_id])
        self.assertEqual(self.store.case_get("k1").status, "expired")

    def test_a_change_that_was_stuck_running_is_looked_at_again(self):
        plan, action = self.approved()
        self.store.action_put(replace(action, state="running", started_at=stamp(NOW)))
        del self.azure.resources[DISK.lower()]
        self.clock.advance(minutes=20)
        tick(self.t)
        after = self.store.action_get(plan.plan_id)
        self.assertEqual(after.state, "done")
        self.assertTrue(after.verification["gone"])

    def test_the_cost_lines_confirm_a_saving_after_two_days_and_not_before(self):
        plan, _ = self.approved(cost=3.65)
        self.assertEqual(self.make_change(plan).action.state, "done")
        self.clock.advance(days=1)
        tick(self.t)
        self.assertEqual(self.arm.asked, [], "too early to ask Cost Management")
        self.clock.advance(days=1, hours=1)
        result = tick(self.t)
        self.assertEqual([a.state for a in result.verified], ["verified"])
        action = self.store.action_get(plan.plan_id)
        self.assertEqual(action.verification["costAfterUsd"], 0.0)
        self.assertEqual(action.verification["costBeforeUsd30d"], 3.65)
        self.assertIn("Confirmed", action.verification["note"])
        self.assertEqual(self.store.case_get(plan.case_id).status, "verified")
        self.assertEqual(self.arm.asked[0][1], dt.date(2026, 11, 6))
        self.assertIn(("action.verified", {"planId": plan.plan_id, "family": "delete-disk"}), self.events)

    def test_cost_lines_that_continue_are_not_a_confirmation(self):
        plan, _ = self.approved(cost=3.65)
        self.arm.totals = {DISK.lower(): 0.5}
        self.make_change(plan)
        self.clock.advance(days=3)
        result = tick(self.t)
        self.assertEqual(result.verified, [])
        action = self.store.action_get(plan.plan_id)
        self.assertEqual(action.state, "done")
        self.assertIn("Not confirmed", action.verification["note"])
        self.assertEqual(self.store.case_get(plan.case_id).status, "done")

    def test_cost_management_that_cannot_be_read_leaves_the_action_done_and_not_verified(self):
        plan, _ = self.approved(cost=3.65)
        self.arm.fail = True
        self.make_change(plan)
        self.clock.advance(days=3)
        self.assertEqual(tick(self.t).verified, [])
        self.assertEqual(self.store.action_get(plan.plan_id).state, "done")

    def test_without_a_cost_reader_the_deletion_is_still_checked(self):
        self.t.arm = None
        plan, _ = self.approved()
        self.make_change(plan)
        self.clock.advance(days=5)
        tick(self.t)
        self.assertEqual(self.store.action_get(plan.plan_id).state, "done")


if __name__ == "__main__":
    unittest.main()
