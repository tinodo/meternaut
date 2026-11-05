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
from cases.runner import MAX_PER_TICK, RunnerServices, execute, runner_calls, tick

OID = "aaaaaaaa-1111-4222-8333-444444444444"
SUB = "bbbbbbbb-2222-4333-9444-555555555555"
GROUP = "meternaut-sc-rg"
NOW = dt.datetime(2026, 11, 5, 9, 0, 0, tzinfo=dt.timezone.utc)
SETTINGS = ApprovalSettings(writer_group=GROUP, delay_seconds=120)
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
    """Resource Manager, for the calls of the runner: a few resources, their locks, and a delete that takes effect after some reads."""

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

    def transport(self, method, url, headers, data, timeout):
        self.calls.append((method, url))
        self.headers.append(dict(headers))
        path = url.split("?")[0].replace("https://management.azure.com", "")
        key = path.lower()
        if "/providers/microsoft.authorization/locks" in key:
            scope = key.split("/providers/microsoft.authorization/locks")[0]
            return 200, {}, json.dumps({"value": self.locks.get(scope, [])}).encode()
        if self.fail_reads and method == "GET":
            return 500, {}, b"{}"
        if method == "GET":
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
                return self.delete_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no"}}'
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
        self.tokens = []
        client = Client(runner_calls(SUB, GROUP), lambda t: t, transport=self.azure.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        self.arm = FakeArm()
        self.s = RunnerServices(self.store, client, lambda r: (self.tokens.append(r), "writer-token")[1], SETTINGS, SUB, arm=self.arm, clock=self.clock,
                                sleep=self.sleeps.append, emit=lambda kind, **f: self.events.append((kind, f)))
        self.approvals = Approvals(self.store, SETTINGS, self.clock)

    def approved(self, resource_id=DISK, detector="orphan-managed-disk", name="planted-disk-1", cost=None):
        item = lead_for(resource_id, detector, name)
        case = CaseRecord(case_id="k" + item.lead_id, resource_id=resource_id, resource_name=name, resource_type=item.resource_type, resource_group=GROUP,
                          subscription_id=SUB, detector=detector, run_id="r1", status="proposed", recommendation="delete", confidence=0.9, cost_usd_30d=cost,
                          saving_usd_month=cost, updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        self.store.case_put(case)
        plan = self.approvals.create(case, item, (OID,))
        result = self.approvals.decide(APPROVER, plan.plan_id, "approve", plan.code, self.store.nonce_new(OID, plan.plan_id))
        assert result.kind == "recorded", result
        return plan, self.store.action_get(plan.plan_id)


class TheListOfCalls(unittest.TestCase):
    def setUp(self):
        self.client = Client(runner_calls(SUB, GROUP), lambda t: t, transport=lambda *a: (200, {}, b"{}"), sleep=lambda s: None, monotonic=lambda: 0.0)

    def test_it_reads_and_deletes_a_disk_and_a_public_ip_address_in_the_one_group_and_reads_locks(self):
        base = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
        for method, path in (("GET", "/Microsoft.Compute/disks/d1"), ("DELETE", "/Microsoft.Compute/disks/d1"), ("GET", "/Microsoft.Network/publicIPAddresses/ip1"),
                             ("DELETE", "/Microsoft.Network/publicIPAddresses/ip1")):
            with self.subTest(method=method, path=path):
                self.client.request(method, base + path + "?api-version=2024-03-02")
        for scope in (f"/subscriptions/{SUB}", f"/subscriptions/{SUB}/resourceGroups/{GROUP}", DISK):
            self.client.request("GET", f"https://management.azure.com{scope}/providers/Microsoft.Authorization/locks?api-version=2016-09-01")

    def test_everything_else_is_refused(self):
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
        ]
        for method, url in refused:
            with self.subTest(method=method, url=url):
                with self.assertRaises(Refused):
                    self.client.request(method, url)

    def test_the_only_deletes_are_the_two_kinds(self):
        deletes = [pattern.pattern for method, pattern in runner_calls(SUB, GROUP) if method == "DELETE"]
        self.assertEqual(len(deletes), 2)
        self.assertTrue(all("disks" in p or "publicIPAddresses" in p for p in deletes))


class TheChange(Base):
    def test_an_approved_disk_is_deleted_after_a_new_read_and_the_records_say_so(self):
        plan, action = self.approved()
        self.clock.advance(seconds=121)
        done = execute(self.s, self.store.action_get(plan.plan_id))
        self.assertEqual((done.state, done.verification.get("gone")), ("done", True))
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
        self.clock.advance(seconds=121)
        done = execute(self.s, self.store.action_get(plan.plan_id))
        self.assertEqual(done.state, "done")
        self.assertNotIn(IP.lower(), self.azure.resources)

    def test_every_call_carries_the_token_of_the_writer_identity_and_the_correlation_id_goes_on_the_delete(self):
        plan, action = self.approved()
        execute(self.s, self.store.action_get(plan.plan_id))
        self.assertEqual(set(self.tokens), {"https://management.azure.com/"})
        self.assertTrue(all(h["Authorization"] == "Bearer writer-token" for h in self.azure.headers))
        delete_headers = [h for (m, _), h in zip(self.azure.calls, self.azure.headers) if m == "DELETE"]
        self.assertEqual(delete_headers[0]["x-ms-correlation-request-id"], action.correlation_id)

    def stops(self, expect_in_text, mutate=None, plan_mutate=None):
        plan, action = self.approved()
        if mutate:
            mutate()
        if plan_mutate:
            self.store.plan_put(replace(self.store.plan_get(plan.plan_id), **plan_mutate))
        done = execute(self.s, self.store.action_get(plan.plan_id))
        self.assertEqual(done.state, "failed", done.result)
        self.assertIn(expect_in_text, done.result)
        self.assertIn("Nothing was changed", done.result)
        self.assertNotIn("DELETE", [m for m, _ in self.azure.calls])
        self.assertIn(DISK.lower(), self.azure.resources)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "failed")

    def test_it_stops_when_the_disk_has_been_attached_since(self):
        self.stops("not unattached any more", lambda: self.azure.resources[DISK.lower()]["properties"].update(diskState="Attached"))

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
                self.stops("may act on" if label != "precondition" else "preconditions", plan_mutate=change)

    def test_it_stops_when_a_guard_cannot_be_read(self):
        plan, _ = self.approved()
        self.azure.fail_reads = True
        done = execute(self.s, self.store.action_get(plan.plan_id))
        self.assertEqual(done.state, "failed")
        self.assertIn("Nothing was changed", done.result)

    def test_it_does_nothing_for_a_plan_without_a_recorded_approval_or_a_wrong_code(self):
        plan, _ = self.approved()
        self.store.decisions.clear()
        self.assertEqual(execute(self.s, self.store.action_get(plan.plan_id)).state, "failed")
        self.assertEqual(self.azure.calls, [])
        self.setUp()
        plan, _ = self.approved()
        key = (plan.plan_id, OID)
        self.store.decisions[key] = replace(self.store.decisions[key], plan_code="00000000")
        self.assertEqual(execute(self.s, self.store.action_get(plan.plan_id)).state, "failed")
        self.assertEqual(self.azure.calls, [])

    def test_a_resource_that_is_gone_already_is_done_with_nothing_to_delete(self):
        plan, _ = self.approved()
        del self.azure.resources[DISK.lower()]
        done = execute(self.s, self.store.action_get(plan.plan_id))
        self.assertEqual(done.state, "done")
        self.assertIn("did not exist", done.result)
        self.assertNotIn("DELETE", [m for m, _ in self.azure.calls])

    def test_a_refused_delete_is_a_failure_that_says_so_and_a_withdrawn_plan_is_never_run(self):
        plan, _ = self.approved()
        self.azure.delete_status = 403
        done = execute(self.s, self.store.action_get(plan.plan_id))
        self.assertEqual(done.state, "failed")
        self.assertIn("refused or failed", done.result)
        self.assertIn(DISK.lower(), self.azure.resources)
        self.setUp()
        plan, _ = self.approved()
        self.approvals.withdraw(APPROVER, plan.plan_id, self.store.nonce_new(OID, plan.plan_id))
        self.assertEqual(execute(self.s, self.store.action_get(plan.plan_id)).state, "withdrawn")
        self.assertEqual(self.azure.calls, [])

    def test_a_delete_that_azure_accepted_but_that_still_shows_is_unknown_not_done(self):
        plan, _ = self.approved()
        self.azure.reads_before_gone = 99
        done = execute(self.s, self.store.action_get(plan.plan_id))
        self.assertEqual(done.state, "unknown")
        self.assertEqual(len(self.sleeps), 5)
        self.assertEqual(self.store.case_get(plan.case_id).status, "running")

    def test_a_delete_that_takes_a_few_reads_to_show_is_waited_for(self):
        plan, _ = self.approved()
        self.azure.reads_before_gone = 3
        self.assertEqual(execute(self.s, self.store.action_get(plan.plan_id)).state, "done")
        self.assertGreaterEqual(len(self.sleeps), 2)

    def test_a_network_error_on_the_delete_is_unknown_and_a_later_check_settles_it(self):
        plan, _ = self.approved()
        original = self.azure.transport

        def flaky(method, url, headers, data, timeout):
            if method == "DELETE":
                raise OSError("reset")
            return original(method, url, headers, data, timeout)

        self.s.client.transport = flaky
        done = execute(self.s, self.store.action_get(plan.plan_id))
        self.assertEqual(done.state, "unknown")
        self.s.client.transport = original
        del self.azure.resources[DISK.lower()]
        self.clock.advance(minutes=5)
        result = tick(self.s)
        self.assertEqual(self.store.action_get(plan.plan_id).state, "done")
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "consumed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "done")


class TheTick(Base):
    def test_nothing_runs_before_its_start_time_and_everything_runs_after(self):
        plan, _ = self.approved()
        result = tick(self.s)
        self.assertEqual(result.finished, [])
        self.assertEqual(self.store.action_get(plan.plan_id).state, "queued")
        self.assertEqual(self.azure.calls, [])
        self.clock.advance(seconds=121)
        result = tick(self.s)
        self.assertEqual([a.state for a in result.finished], ["done"])

    def test_a_pulled_switch_leaves_the_change_waiting_and_a_released_one_lets_it_run(self):
        plan, _ = self.approved()
        self.clock.advance(seconds=121)
        for name in ("changes", "all"):
            self.store.switch_put(SwitchRecord(name=name, paused=True))
            self.assertEqual(tick(self.s).finished, [])
            self.assertEqual(self.store.action_get(plan.plan_id).state, "queued")
            self.assertEqual(self.azure.calls, [])
            self.store.switch_put(SwitchRecord(name=name, paused=False))
        self.assertEqual(len(tick(self.s).finished), 1)

    def test_a_switch_that_cannot_be_read_counts_as_pulled(self):
        plan, _ = self.approved()
        self.clock.advance(seconds=121)

        def broken(name):
            raise RuntimeError("down")

        self.store.switch_get = broken
        self.assertEqual(tick(self.s).finished, [])
        self.assertEqual(self.azure.calls, [])

    def test_at_most_three_changes_run_in_one_tick(self):
        for index in range(MAX_PER_TICK + 2):
            rid = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/d{index}"
            self.azure.resources[rid.lower()] = {"id": rid, "tags": {"meternaut-planted": "x"}, "properties": {"diskState": "Unattached"}}
            self.approved(rid, "orphan-managed-disk", f"d{index}")
        self.clock.advance(seconds=121)
        self.assertEqual(len(tick(self.s).finished), MAX_PER_TICK)
        self.assertEqual(len(tick(self.s).finished), 2)

    def test_expired_plans_are_closed(self):
        item = lead_for(DISK, "orphan-managed-disk", "planted-disk-1")
        case = CaseRecord(case_id="k1", resource_id=DISK, resource_name="n", resource_type="t", resource_group=GROUP, subscription_id=SUB, detector="orphan-managed-disk",
                          run_id="r", status="proposed", recommendation="delete", updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        self.store.case_put(case)
        plan = self.approvals.create(case, item, (OID,))
        self.clock.advance(hours=73)
        self.assertEqual([p.plan_id for p in tick(self.s).expired], [plan.plan_id])
        self.assertEqual(self.store.case_get("k1").status, "expired")

    def test_a_change_that_was_stuck_running_is_looked_at_again(self):
        plan, action = self.approved()
        self.store.action_put(replace(action, state="running", started_at=stamp(NOW)))
        del self.azure.resources[DISK.lower()]
        self.clock.advance(minutes=20)
        tick(self.s)
        after = self.store.action_get(plan.plan_id)
        self.assertEqual(after.state, "done")
        self.assertTrue(after.verification["gone"])

    def test_the_cost_lines_confirm_a_saving_after_two_days_and_not_before(self):
        plan, _ = self.approved(cost=3.65)
        self.clock.advance(seconds=121)
        tick(self.s)
        self.assertEqual(self.store.action_get(plan.plan_id).state, "done")
        self.clock.advance(days=1)
        tick(self.s)
        self.assertEqual(self.arm.asked, [], "too early to ask Cost Management")
        self.clock.advance(days=1, hours=1)
        result = tick(self.s)
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
        self.clock.advance(seconds=121)
        tick(self.s)
        self.clock.advance(days=3)
        result = tick(self.s)
        self.assertEqual(result.verified, [])
        action = self.store.action_get(plan.plan_id)
        self.assertEqual(action.state, "done")
        self.assertIn("Not confirmed", action.verification["note"])
        self.assertEqual(self.store.case_get(plan.case_id).status, "done")

    def test_cost_management_that_cannot_be_read_leaves_the_action_done_and_not_verified(self):
        plan, _ = self.approved(cost=3.65)
        self.arm.fail = True
        self.clock.advance(seconds=121)
        tick(self.s)
        self.clock.advance(days=3)
        self.assertEqual(tick(self.s).verified, [])
        self.assertEqual(self.store.action_get(plan.plan_id).state, "done")

    def test_without_a_cost_reader_the_deletion_is_still_checked(self):
        self.s.arm = None
        plan, _ = self.approved()
        self.clock.advance(seconds=121)
        tick(self.s)
        self.clock.advance(days=5)
        tick(self.s)
        self.assertEqual(self.store.action_get(plan.plan_id).state, "done")


if __name__ == "__main__":
    unittest.main()
