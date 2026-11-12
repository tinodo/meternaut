import base64
import datetime as dt
import json
import unittest
from dataclasses import replace

from support import APP_ROOT  # noqa: F401

from cases.approvals import Approvals, ApprovalSettings
from cases.detectors import Lead
from cases.families import digest as plan_digest
from cases.families.gates import ChangeScope
from cases.http import Client, HttpError, Refused
from cases.memory_store import MemoryStore, stamp
from cases.models import ActionRecord, CaseRecord, NoteRecord, Principal, SwitchRecord
from cases.runner import ASKED_AGAIN, COST_GAVE_UP, STEP_UP_ABANDONED, STEP_UP_WAIT, Executed, RunnerServices, change_calls, execute, read_calls, tick

OID = "aaaaaaaa-1111-4222-8333-444444444444"
SUB = "bbbbbbbb-2222-4333-9444-555555555555"
GROUP = "meternaut-sc-rg"
NOW = dt.datetime(2026, 11, 5, 9, 0, 0, tzinfo=dt.timezone.utc)
SCOPES = (ChangeScope(SUB, GROUP),)
SETTINGS = ApprovalSettings(change_scopes=SCOPES)
APPROVER = Principal(OID, "Tino", ("owner", "approver", "ops"))
DISK = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/planted-disk-1"
IP = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Network/publicIPAddresses/planted-ip-1"
# A cost line of another resource, in the lower case in which Cost Management's answers are read: that Cost Management has lines at all for the days is what the checks need to know.
OTHER_LINE = f"/subscriptions/{SUB}/resourcegroups/{GROUP}/providers/microsoft.compute/disks/another-disk"
SCHEME = "Bearer"
# A claims request with a value that no page, record, line or log has any reason to hold.
CLAIMS = '{"access_token":{"acrs":{"essential":true,"value":"c-unique-4711"}}}'


def challenge(claims: str = CLAIMS, directive: str | None = None) -> dict:
    """The headers of an answer that holds a claims challenge, as Azure sends it (the transport gives the names in lower case)."""
    text = directive if directive is not None else f'claims="{base64.b64encode(claims.encode()).decode()}"'
    return {"www-authenticate": f'{SCHEME} realm="", authorization_uri="https://login.example.test/common/oauth2/authorize", error="insufficient_claims", {text}'}


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
        self.delete_headers: dict = {}  # the headers of a refused delete (a claims challenge is one of them)
        self.delete_answers: list[tuple[int, dict]] = []  # the answers of the next deletes, (status, headers), one each, before `delete_status` applies
        self.reads_before_gone = 1
        self.pending: dict[str, int] = {}
        self.fail_reads = False
        self.read_status = 200
        self.read_headers: dict = {}
        self.locks_status = 200
        self.locks_headers: dict = {}

    def transport(self, method, url, headers, data, timeout):
        self.calls.append((method, url))
        self.headers.append(dict(headers))
        path = url.split("?")[0].replace("https://management.azure.com", "")
        key = path.lower()
        if "/providers/microsoft.authorization/locks" in key:
            if self.locks_status >= 300:
                return self.locks_status, dict(self.locks_headers), b'{"error":{"code":"AuthorizationFailed","message":"no right to read the locks"}}'
            scope = key.split("/providers/microsoft.authorization/locks")[0]
            return 200, {}, json.dumps({"value": self.locks.get(scope, [])}).encode()
        if self.fail_reads and method == "GET":
            return 500, {}, b"{}"
        if method == "GET":
            if self.read_status >= 300:
                return self.read_status, dict(self.read_headers), b'{"error":{"code":"AuthorizationFailed","message":"no right to read"}}'
            if key in self.pending:
                self.pending[key] -= 1
                if self.pending[key] < 0:
                    del self.pending[key]
                    self.resources.pop(key, None)
            if key not in self.resources:
                return 404, {}, b'{"error":{"code":"ResourceNotFound","message":"gone"}}'
            return 200, {}, json.dumps(self.resources[key]).encode()
        if method == "DELETE":
            status, answer_headers = self.delete_answers.pop(0) if self.delete_answers else (self.delete_status, self.delete_headers)
            if status >= 300:
                return status, dict(answer_headers), b'{"error":{"code":"AuthorizationFailed","message":"no right to delete"}}'
            if key not in self.resources:
                return 204, {}, b""
            self.pending[key] = self.reads_before_gone
            return status, {}, b""
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
        change = Client(change_calls(SCOPES), lambda t: t, transport=self.azure.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        check = Client(read_calls(SCOPES), lambda t: t, transport=self.azure.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        self.arm = FakeArm()
        emit = lambda kind, **f: self.events.append((kind, f))  # noqa: E731
        # `s` makes a change with the token of the person who approved it; `t` is the timer's: the reader's token and no write on its list.
        self.s = RunnerServices(self.store, change, lambda r: (self.person_tokens.append(r), "person-token")[1], SETTINGS, clock=self.clock,
                                sleep=self.sleeps.append, emit=emit)
        self.t = RunnerServices(self.store, check, lambda r: (self.reader_tokens.append(r), "reader-token")[1], SETTINGS, arm=self.arm, clock=self.clock,
                                sleep=self.sleeps.append, emit=emit)
        self.approvals = Approvals(self.store, SETTINGS, self.clock)

    def approved(self, resource_id=DISK, detector="orphan-managed-disk", name="planted-disk-1", cost=None, plan_mutate=None):
        """A plan that a person approved at the sign-in to Azure: the decision is recorded and the action waits to be made. `plan_mutate` changes a field of the plan before it is approved
        (and the plan is sealed again, so that what is approved is that plan): the re-check of the family is then the only guard that can stop it."""
        item = lead_for(resource_id, detector, name)
        case = CaseRecord(case_id="k" + item.lead_id, resource_id=resource_id, resource_name=name, resource_type=item.resource_type, resource_group=GROUP,
                          subscription_id=SUB, detector=detector, run_id="r1", status="proposed", recommendation="delete", confidence=0.9, cost_usd_30d=cost,
                          saving_usd_month=cost, updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        self.store.case_put(case)
        plan = self.approvals.create(case, item, (OID,))
        if plan_mutate:
            plan = plan_digest.sealed(replace(plan, **plan_mutate))
            self.store.plan_put(plan)
        checked, refusal = self.approvals.check_approve(APPROVER, plan.plan_id, plan.code)
        assert refusal is None, refusal
        result, action = self.approvals.record_approval(APPROVER, checked, "")
        assert result.kind == "recorded", result
        return plan, action

    def make_change(self, plan):
        """Makes the change of the plan's action with the person's token, as the sign-in to Azure does."""
        return execute(self.s, self.store.action_get(plan.plan_id), approved_digest=plan.digest)


class TheListsOfCalls(unittest.TestCase):
    def setUp(self):
        self.change = Client(change_calls(SCOPES), lambda t: t, transport=lambda *a: (200, {}, b"{}"), sleep=lambda s: None, monotonic=lambda: 0.0)
        self.check = Client(read_calls(SCOPES), lambda t: t, transport=lambda *a: (200, {}, b"{}"), sleep=lambda s: None, monotonic=lambda: 0.0)

    def test_a_change_reads_and_deletes_a_disk_and_a_public_ip_address_in_the_one_group_and_reads_locks(self):
        base = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
        for method, path in (("GET", "/Microsoft.Compute/disks/d1"), ("DELETE", "/Microsoft.Compute/disks/d1"), ("GET", "/Microsoft.Network/publicIPAddresses/ip1"),
                             ("DELETE", "/Microsoft.Network/publicIPAddresses/ip1")):
            with self.subTest(method=method, path=path):
                self.change.request(method, base + path + "?api-version=2024-03-02")
        for scope in (f"/subscriptions/{SUB}", f"/subscriptions/{SUB}/resourceGroups/{GROUP}", DISK):
            self.change.request("GET", f"https://management.azure.com{scope}/providers/Microsoft.Authorization/locks?api-version=2016-09-01")

    def test_a_change_also_reads_a_machine_and_makes_the_calls_of_the_other_families_and_nothing_else_of_a_machine(self):
        base = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute"
        for method, path in (("GET", "/virtualMachines/vm1"), ("GET", "/virtualMachines/vm1/vmSizes"), ("POST", "/virtualMachines/vm1/deallocate"), ("PATCH", "/virtualMachines/vm1"),
                             ("PATCH", "/disks/d1"), ("DELETE", "/snapshots/s1")):
            with self.subTest(method=method, path=path):
                self.change.request(method, base + path + "?api-version=2026-04-01")
        for method, path in (("DELETE", "/virtualMachines/vm1"), ("POST", "/virtualMachines/vm1/restart"), ("POST", "/virtualMachines/vm1/start"), ("PUT", "/virtualMachines/vm1"),
                             ("POST", "/virtualMachines/vm1/runCommand"), ("PATCH", "/snapshots/s1"), ("PUT", "/disks/d1")):
            with self.subTest(refused=(method, path)):
                with self.assertRaises(Refused):
                    self.change.request(method, base + path + "?api-version=2026-04-01")

    def test_the_checks_of_the_timer_read_the_same_things_and_can_not_even_attempt_a_write(self):
        base = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
        for path in ("/Microsoft.Compute/disks/d1", "/Microsoft.Network/publicIPAddresses/ip1", "/Microsoft.Compute/virtualMachines/vm1"):
            self.check.request("GET", base + path + "?api-version=2024-03-02")
            for method in ("DELETE", "PATCH", "PUT"):
                with self.assertRaises(Refused):
                    self.check.request(method, base + path + "?api-version=2024-03-02")
        with self.assertRaises(Refused):
            self.check.request("POST", base + "/Microsoft.Compute/virtualMachines/vm1/deallocate?api-version=2026-04-01")
        self.check.request("GET", f"https://management.azure.com{DISK}/providers/Microsoft.Authorization/locks?api-version=2016-09-01")
        self.assertEqual({method for method, _ in read_calls(SCOPES)}, {"GET"})

    def test_everything_else_is_refused_by_both_lists(self):
        other = "22222222-2222-2222-2222-222222222222"
        base = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
        refused = [
            ("DELETE", f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/other-rg/providers/Microsoft.Compute/disks/d1"),
            ("DELETE", f"https://management.azure.com/subscriptions/{other}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/d1"),
            ("DELETE", base + "/Microsoft.Storage/storageAccounts/sa1"),
            ("DELETE", f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}"),
            ("DELETE", f"https://management.azure.com/subscriptions/{SUB}"),
            ("PUT", base + "/Microsoft.Compute/disks/d1"),
            ("POST", base + "/Microsoft.Compute/disks/d1/beginGetAccess"),
            ("POST", base + "/Microsoft.Compute/disks/d1"),
            ("DELETE", base + "/Microsoft.Compute/disks/d1/extra"),
            ("DELETE", f"https://management.azure.com/subscriptions/{SUB}/providers/Microsoft.Authorization/locks/x"),
            ("GET", "https://example.com/subscriptions/" + SUB),
            ("GET", base + "/Microsoft.Storage/storageAccounts/sa1"),
            ("GET", base + "/Microsoft.KeyVault/vaults/kv1/secrets"),
        ]
        for client in (self.change, self.check):
            for method, url in refused:
                with self.subTest(method=method, url=url):
                    with self.assertRaises(Refused):
                        client.request(method, url)

    def test_the_only_deletes_are_the_kinds_of_the_closed_list(self):
        deletes = [pattern.pattern for method, pattern in change_calls(SCOPES) if method == "DELETE"]
        self.assertEqual(len(deletes), 7)
        for kind in ("disks", "publicIPAddresses", "snapshots", "networkInterfaces", "natGateways", "loadBalancers", "privateEndpoints"):
            self.assertEqual(len([p for p in deletes if f"/{kind}/" in p]), 1, kind)

    def test_a_second_group_of_the_scopes_gets_the_same_calls_and_a_group_outside_them_gets_none(self):
        second = (*SCOPES, ChangeScope("33333333-3333-4333-9333-333333333333", "meternaut-two"))
        wide = Client(change_calls(second), lambda t: t, transport=lambda *a: (200, {}, b"{}"), sleep=lambda s: None, monotonic=lambda: 0.0)
        wide.request("DELETE", "https://management.azure.com/subscriptions/33333333-3333-4333-9333-333333333333/resourceGroups/meternaut-two/providers/Microsoft.Compute/disks/d1?api-version=2024-03-02")
        with self.assertRaises(Refused):
            self.change.request("DELETE", "https://management.azure.com/subscriptions/33333333-3333-4333-9333-333333333333/resourceGroups/meternaut-two/providers/Microsoft.Compute/disks/d1")


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
        plan, action = self.approved(plan_mutate=plan_mutate)
        if mutate:
            mutate()
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "withdrawn"), done.action.result)
        self.assertIn(expect_in_text, done.action.result)
        self.assertIn("Nothing was changed", done.action.result)
        self.assertNotIn("Stopped before the change", done.action.result, "the words of a person: no label of the runner")
        self.assertNotIn("precondition", done.action.result)
        self.assertNotIn("DELETE", [m for m, _ in self.azure.calls])
        self.assertIn(DISK.lower(), self.azure.resources)
        # Nothing was written, so the approval was not used: the request is open again, the record of the try stays, and a person can approve once more.
        self.assertEqual(self.store.action_get(plan.plan_id), done.action)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "open")
        self.assertEqual(self.store.case_get(plan.case_id).status, "awaiting_ok")
        self.assertEqual(self.store.decisions_of_plan(plan.plan_id), [])
        self.assertEqual(self.events[-1], ("action.finished", {"planId": plan.plan_id, "family": self.store.plan_get(plan.plan_id).family, "ok": False}))

    def test_it_stops_when_the_disk_has_been_attached_since(self):
        self.stops("not unattached any more", lambda: self.azure.resources[DISK.lower()]["properties"].update(diskState="Attached"))

    def test_it_stops_when_changes_were_paused_after_the_approval_and_nothing_is_deleted(self):
        self.stops("paused after the approval", lambda: self.store.switch_put(SwitchRecord(name="changes", paused=True, by=OID, at=stamp(NOW))))

    def test_a_resource_that_is_gone_already_is_not_stopped_by_a_pulled_switch_because_nothing_is_changed(self):
        plan, _ = self.approved()
        self.azure.resources.pop(DISK.lower())
        self.store.switch_put(SwitchRecord(name="all", paused=True, by=OID, at=stamp(NOW)))
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("unchanged", "done"))

    def test_it_stops_when_the_disk_is_managed_by_a_machine(self):
        self.stops("not unattached any more", lambda: self.azure.resources[DISK.lower()].update(managedBy="/vm"))

    def test_it_stops_when_the_tag_is_gone(self):
        # The words that the owner read after the first real approval of a planted disk whose tags an outside job had stripped: now in plain words, with what it means.
        self.stops("Meternaut did not change the disk: it no longer carries the test tag meternaut-planted, so it cannot be told apart from a real disk. Nothing was changed.",
                   lambda: self.azure.resources[DISK.lower()].update(tags={}))

    def test_it_stops_when_the_tag_has_no_value(self):
        self.stops("it no longer carries the test tag meternaut-planted", lambda: self.azure.resources[DISK.lower()].update(tags={"meternaut-planted": " "}))

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
        """The plan was approved as it is (sealed with its digest), so the digest cannot stop it: the re-check of the family is the guard."""
        for label, change in {
            "group": {"resource_id": DISK.replace(GROUP, "other-rg")},
            "family": {"family": "delete-public-ip"},
            "precondition": {"preconditions": {"family": "delete-disk", "tag": "meternaut-planted", "resourceGroup": "other-rg"}},
        }.items():
            with self.subTest(label):
                self.setUp()
                self.stops("a change may be made on" if label != "precondition" else "do not fit the resource that it names", plan_mutate=change)

    def test_it_stops_when_a_guard_cannot_be_read(self):
        plan, _ = self.approved()
        self.azure.fail_reads = True
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "withdrawn"))
        self.assertIn("Nothing was changed", done.action.result)
        self.assertEqual((self.store.plan_get(plan.plan_id).state, self.store.case_get(plan.case_id).status), ("open", "awaiting_ok"), "a read that failed closes nothing")

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
        self.assertEqual((done.kind, done.action.state), ("unchanged", "done"))
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


class WhenAzureAsksForAnExtraSignInCheck(Base):
    """A person who signed in without the multifactor check that a change needs can use the console, but Azure answers the delete with a claims challenge (HTTP 401 and a
    `www-authenticate` header). That is a step-up and not a refusal: nothing was deleted, the plan stays approved and the action waits for the retry."""

    def asked(self, plan=None):
        """The change of an approved plan, with a delete that Azure answers with a claims challenge."""
        if plan is None:
            plan, _ = self.approved()
        self.azure.delete_answers = [(401, challenge())]
        return plan, self.make_change(plan)

    def test_a_claims_challenge_on_the_delete_puts_the_action_back_in_the_queue_and_closes_nothing(self):
        plan, queued = self.approved()
        self.azure.delete_answers = [(401, challenge())]
        done = self.make_change(plan)
        self.assertIsInstance(done, Executed)
        self.assertEqual((done.kind, done.claims), ("step_up", CLAIMS))
        action = done.action
        self.assertEqual((action.state, action.started_at, action.finished_at, action.error, action.result, action.step_up),
                         ("queued", None, None, None, STEP_UP_WAIT, True))
        self.assertEqual((action.queued_at, action.correlation_id, action.verification), (queued.queued_at, queued.correlation_id, {}))
        self.assertEqual(self.store.action_get(plan.plan_id), action)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "approved")
        self.assertEqual(self.store.case_get(plan.case_id).status, "approved")
        self.assertEqual([d.decision for d in self.store.decisions_of_plan(plan.plan_id)], ["approve"])
        self.assertIn(DISK.lower(), self.azure.resources, "nothing was deleted")
        self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 1)
        self.assertEqual([kind for kind, _ in self.events], ["action.started"], "nothing finished: no line says that the change ended")

    def test_the_words_of_the_waiting_action_say_that_nothing_was_changed_and_what_it_waits_for(self):
        self.assertIn("extra sign-in check", STEP_UP_WAIT)
        self.assertIn("Nothing was changed yet", STEP_UP_WAIT)
        self.assertIn("waits", STEP_UP_WAIT)

    def test_the_retry_reads_everything_again_deletes_with_the_new_token_and_closes_the_plan_as_any_change_does(self):
        plan, step_up = self.asked()
        self.azure.calls.clear()
        done = execute(self.s, step_up.action, approved_digest=plan.digest)
        self.assertEqual((done.kind, done.claims, done.action.state), ("ran", "", "done"))
        self.assertEqual(done.action.result, "Deleted. Azure no longer lists the resource.", "the words of the wait are gone")
        self.assertEqual((done.action.step_up, done.action.error, bool(done.action.started_at), bool(done.action.finished_at)), (True, None, True, True))
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "consumed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "done")
        self.assertNotIn(DISK.lower(), self.azure.resources)
        self.assertEqual([m for m, _ in self.azure.calls][:4], ["GET", "GET", "GET", "DELETE"], "the resource and the locks are read again before the delete")
        self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 1)
        self.assertEqual([kind for kind, _ in self.events], ["action.started", "action.started", "action.finished"])
        self.assertEqual(len(self.store.decisions_of_plan(plan.plan_id)), 1, "one approval and one action for the whole way")

    def test_the_retry_makes_the_same_checks_as_any_change_and_stops_before_a_second_delete(self):
        for label, change, expected in (
                ("the disk was attached meanwhile", lambda: self.azure.resources[DISK.lower()]["properties"].update(diskState="Attached"), "not unattached any more"),
                ("a lock was put on it", lambda: self.azure.locks.update({DISK.lower(): [{"name": "l"}]}), "management lock"),
                ("the tag is gone", lambda: self.azure.resources[DISK.lower()].update(tags={}), "it no longer carries the test tag meternaut-planted"),
                ("changes were paused", lambda: self.store.switch_put(SwitchRecord(name="changes", paused=True, by=OID, at=stamp(NOW))), "paused after the approval"),
                ("somebody marked it do-not-touch", lambda: self.store.note_put(NoteRecord(note_id="n", oid=OID, kind="do_not_touch", text="no", scope_resource_id=DISK,
                                                                                            expires_at="2099-01-01T00:00:00Z")), "do-not-touch")):
            with self.subTest(label):
                self.setUp()
                plan, step_up = self.asked()
                change()
                done = execute(self.s, step_up.action, approved_digest=plan.digest)
                self.assertEqual((done.kind, done.action.state), ("stopped", "withdrawn"), done.action.result)
                self.assertIn(expected, done.action.result)
                self.assertIn("Nothing was changed", done.action.result)
                self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 1, "only the first delete was made")
                self.assertIn(DISK.lower(), self.azure.resources)
                self.assertEqual((self.store.plan_get(plan.plan_id).state, self.store.case_get(plan.case_id).status), ("open", "awaiting_ok"), "the extra check was passed for nothing, and the request is open again")

    def test_a_second_challenge_is_final_and_says_that_azure_asked_again_and_that_nothing_was_changed(self):
        plan, step_up = self.asked()
        self.azure.delete_answers = [(401, challenge())]
        done = execute(self.s, step_up.action, approved_digest=plan.digest)
        self.assertEqual((done.kind, done.claims, done.action.state), ("azure_refused", "", "failed"))
        self.assertEqual((done.action.result, done.action.error), (ASKED_AGAIN, ASKED_AGAIN))
        for words in ("a second time", "was not made", "Nothing was changed", "does not ask a second time", "The request is closed"):
            self.assertIn(words, ASKED_AGAIN)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "failed")
        self.assertEqual(self.store.action_get(plan.plan_id), done.action)
        self.assertIn(DISK.lower(), self.azure.resources)
        self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 2, "no third try")
        self.assertEqual(self.events[-1], ("action.finished", {"planId": plan.plan_id, "family": "delete-disk", "ok": False}))

    def test_a_third_challenge_is_not_reached_because_the_second_closed_the_plan(self):
        plan, step_up = self.asked()
        self.azure.delete_answers = [(401, challenge()), (401, challenge())]
        execute(self.s, step_up.action, approved_digest=plan.digest)
        again = execute(self.s, self.store.action_get(plan.plan_id), approved_digest=plan.digest)
        self.assertEqual((again.kind, again.action.state), ("failed", "failed"))
        self.assertIn("no approval by a named approver", again.action.result)
        self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 2)

    def test_only_a_401_with_a_valid_challenge_steps_up_and_the_rest_is_an_ordinary_refusal(self):
        good = challenge()["www-authenticate"]
        claims = base64.b64encode(CLAIMS.encode()).decode()
        for label, status, headers in (
                ("no header", 401, {}),
                ("a header that is not a challenge", 401, {"www-authenticate": f'{SCHEME} realm="x"'}),
                ("another error", 401, {"www-authenticate": good.replace("insufficient_claims", "invalid_token")}),
                ("claims that are not base64", 401, challenge(directive='claims="!!!!"')),
                ("claims that are not JSON", 401, challenge(directive=f'claims="{base64.b64encode(b"not json").decode()}"')),
                ("claims that are not an object", 401, challenge(directive=f'claims="{base64.b64encode(b"[1]").decode()}"')),
                ("claims that are too deep", 401, challenge('{"a":{"b":{"c":{"d":{"e":1}}}}}')),
                ("two claims directives", 401, {"www-authenticate": good + f', claims="{claims}"'}),
                ("a quote in the header", 401, {"www-authenticate": good.replace("claims=", 'x="a"b", claims=')}),
                ("another scheme", 401, {"www-authenticate": good.replace(SCHEME, "Basic")}),
                ("a valid challenge on a 403", 403, challenge()),
                ("a valid challenge on a 400", 400, challenge())):
            with self.subTest(label):
                self.setUp()
                plan, _ = self.approved()
                self.azure.delete_answers = [(status, headers)]
                done = self.make_change(plan)
                self.assertEqual(done.claims, "")
                self.assertFalse(done.action.step_up)
                self.assertEqual((done.kind, done.action.state), ("azure_refused", "failed") if status in (401, 403) else ("failed", "failed"), done.action.result)
                self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")
                self.assertEqual(self.store.case_get(plan.case_id).status, "failed")
                self.assertIn(DISK.lower(), self.azure.resources)
                self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 1)

    def test_an_ordinary_refusal_does_not_show_the_header_and_says_what_it_said_before(self):
        plan, _ = self.approved()
        self.azure.delete_answers = [(401, {"www-authenticate": f'{SCHEME} claims="!!!!", error="insufficient_claims"'})]
        done = self.make_change(plan)
        self.assertEqual(done.action.result, "Azure refused to delete the resource (401, AuthorizationFailed): your account has no right to do this here. Nothing was changed.")
        self.assertNotIn("insufficient_claims", done.action.result + (done.action.error or ""))

    def test_a_challenge_on_a_read_stays_a_refusal_because_only_the_delete_can_step_up(self):
        for label, attribute, status_attribute, what in (("the resource", "read_headers", "read_status", "read the resource"),
                                                          ("the locks", "locks_headers", "locks_status", "read the locks")):
            with self.subTest(label):
                self.setUp()
                plan, _ = self.approved()
                setattr(self.azure, attribute, challenge())
                setattr(self.azure, status_attribute, 401)
                done = self.make_change(plan)
                self.assertEqual((done.kind, done.claims, done.action.state, done.action.step_up), ("azure_refused", "", "failed", False))
                self.assertIn("Azure refused to " + what, done.action.result)
                self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")
                self.assertNotIn("DELETE", [m for m, _ in self.azure.calls])

    def test_the_claims_are_on_no_record_no_event_and_not_in_the_text_of_the_result_or_of_the_object(self):
        plan, step_up = self.asked()
        records = [plan.to_json(), self.store.plan_get(plan.plan_id).to_json(), self.store.action_get(plan.plan_id).to_json(), self.store.case_get(plan.case_id).to_json(),
                   *[d.to_json() for d in self.store.decisions_of_plan(plan.plan_id)], json.dumps(self.events), repr(step_up), str(step_up), repr(step_up.action)]
        seen = json.dumps(records)
        for secret in (CLAIMS, "c-unique-4711", base64.b64encode(CLAIMS.encode()).decode(), "insufficient_claims", SCHEME):
            self.assertNotIn(secret, seen)
        self.assertEqual(step_up.claims, CLAIMS, "the claims are for the one that sends the person to Microsoft Entra")
        done = execute(self.s, step_up.action, approved_digest=plan.digest)
        self.assertNotIn("c-unique-4711", json.dumps([done.action.to_json(), json.dumps(self.events), repr(done)]))

    def test_only_the_delete_that_the_runner_makes_with_a_persons_token_can_step_up_and_the_timer_has_no_part_in_it(self):
        plan, step_up = self.asked()
        self.clock.advance(minutes=5)
        calls = len(self.azure.calls)
        result = tick(self.t)
        self.assertEqual((result.finished, result.expired, result.verified), ([], [], []))
        self.assertEqual(len(self.azure.calls), calls, "the timer asks Azure nothing about a change that waits")
        self.assertEqual(self.store.action_get(plan.plan_id), step_up.action)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "approved")


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

    def test_a_step_up_that_nobody_completes_is_closed_after_the_same_limit_with_words_of_its_own_and_nothing_changed(self):
        plan, _ = self.approved()
        self.azure.delete_answers = [(401, challenge())]
        self.make_change(plan)
        calls = len(self.azure.calls)
        self.clock.advance(minutes=9)
        self.assertEqual(tick(self.t).finished, [], "the person may still complete the check")
        self.assertEqual((self.store.action_get(plan.plan_id).state, self.store.plan_get(plan.plan_id).state), ("queued", "approved"))
        self.clock.advance(minutes=2)
        result = tick(self.t)
        self.assertEqual([a.state for a in result.finished], ["failed"])
        action = self.store.action_get(plan.plan_id)
        self.assertEqual((action.state, action.result, action.error), ("failed", STEP_UP_ABANDONED, STEP_UP_ABANDONED))
        for words in ("extra sign-in check", "not completed in time", "was not made", "Nothing was changed"):
            self.assertIn(words, STEP_UP_ABANDONED)
        self.assertNotIn("restart", STEP_UP_ABANDONED, "it was not a restart that ended it")
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")
        self.assertEqual(self.store.case_get(plan.case_id).status, "failed")
        self.assertEqual(len(self.azure.calls), calls, "the timer made no call")
        self.assertIn(DISK.lower(), self.azure.resources)
        self.assertEqual(tick(self.t).finished, [], "it is closed once")

    def test_a_queued_action_that_asked_for_a_step_up_is_closed_by_the_timer_also_when_its_plan_was_closed_already(self):
        plan, _ = self.approved()
        self.azure.delete_answers = [(401, challenge())]
        self.make_change(plan)
        self.store.plan_put(replace(self.store.plan_get(plan.plan_id), state="failed"))  # the close of the plan was made and the close of the action was not
        self.clock.advance(minutes=11)
        self.assertEqual([a.state for a in tick(self.t).finished], ["failed"])
        self.assertEqual((self.store.action_get(plan.plan_id).result, self.store.plan_get(plan.plan_id).state, self.store.case_get(plan.case_id).status),
                         (STEP_UP_ABANDONED, "failed", "failed"))

    def test_a_queued_action_that_never_asked_for_a_step_up_keeps_its_own_words(self):
        plan, _ = self.approved()
        self.clock.advance(minutes=11)
        tick(self.t)
        self.assertNotIn("extra sign-in check", self.store.action_get(plan.plan_id).result)
        self.assertIn("did not start", self.store.action_get(plan.plan_id).result)

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

    def test_the_cost_lines_confirm_a_saving_from_whole_days_only_and_not_before(self):
        plan, _ = self.approved(cost=3.65)
        self.arm.totals = {OTHER_LINE: 1.5}  # Cost Management has lines of another resource for the days, and none of the deleted disk
        self.assertEqual(self.make_change(plan).action.state, "done")
        self.clock.advance(days=1)
        tick(self.t)
        self.assertEqual(self.arm.asked, [], "too early to ask Cost Management")
        self.clock.advance(days=1, hours=1)  # 7 Nov, 10:00: the day after the change ended 10 hours ago, and a whole day has to pass after a day ends
        tick(self.t)
        self.assertEqual(self.arm.asked, [], "a day that ended less than a day ago is not read: its lines may not be all in")
        self.clock.advance(days=1)  # 8 Nov, 10:00
        result = tick(self.t)
        self.assertEqual([a.state for a in result.verified], ["verified"])
        action = self.store.action_get(plan.plan_id)
        self.assertEqual(action.verification["costAfterUsd"], 0.0)
        self.assertEqual(action.verification["costBeforeUsd30d"], 3.65)
        self.assertEqual((action.verification["costLinesFrom"], action.verification["costLinesTo"]), ("2026-11-06", "2026-11-06"))
        self.assertIn("Confirmed", action.verification["note"])
        self.assertEqual(self.store.case_get(plan.case_id).status, "verified")
        self.assertEqual(self.arm.asked, [(SUB, dt.date(2026, 11, 6), dt.date(2026, 11, 6))])
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

    def test_cost_management_is_asked_once_a_day_at_most_whatever_came_of_the_ask(self):
        plan, _ = self.approved(cost=3.65)
        self.arm.fail = True
        self.make_change(plan)
        self.clock.advance(days=3)
        for _ in range(5):
            self.clock.advance(minutes=1)
            tick(self.t)
        self.assertEqual(len(self.arm.asked), 1, "the timer runs every minute, and a failed read is tried again the next day and not at once")
        self.arm.fail = False
        self.arm.totals = {OTHER_LINE: 1.5}
        self.clock.advance(days=1)
        self.assertEqual([a.state for a in tick(self.t).verified], ["verified"])
        self.assertEqual(len(self.arm.asked), 2)

    def test_an_answer_with_no_line_at_all_is_no_data_yet_and_the_next_day_asks_again(self):
        plan, _ = self.approved(cost=3.65)
        self.make_change(plan)
        self.clock.advance(days=3)
        self.assertEqual(tick(self.t).verified, [])
        action = self.store.action_get(plan.plan_id)
        self.assertEqual(action.state, "done")
        self.assertNotIn("costAfterUsd", action.verification, "no data is not a cost of zero, and nothing is stored as one")
        self.assertEqual(action.verification["costAskedOn"], "2026-11-08")
        self.arm.totals = {OTHER_LINE: 1.5}
        tick(self.t)
        self.assertEqual(len(self.arm.asked), 1, "the same day: not asked again")
        self.clock.advance(days=1)
        self.assertEqual([a.state for a in tick(self.t).verified], ["verified"])
        self.assertEqual(self.arm.asked[-1], (SUB, dt.date(2026, 11, 6), dt.date(2026, 11, 7)), "the whole days after the change, up to the day before yesterday")

    def test_the_days_of_waiting_for_cost_lines_are_used_up_and_the_record_says_that_no_figure_came(self):
        plan, _ = self.approved(cost=3.65)
        self.make_change(plan)
        for _ in range(8):
            self.clock.advance(days=1)
            tick(self.t)
        action = self.store.action_get(plan.plan_id)
        self.assertEqual(action.state, "done")
        self.assertTrue(action.verification["costGaveUp"])
        self.assertEqual(action.verification["note"], COST_GAVE_UP)
        self.assertIn("no figure", action.verification["note"])
        self.assertNotIn("costAfterUsd", action.verification)
        asked = len(self.arm.asked)
        self.assertEqual(asked, 5, "once a day from the 8th of November to the 12th")
        self.arm.totals = {OTHER_LINE: 1.5}
        self.clock.advance(days=1)
        self.assertEqual(tick(self.t).verified, [])
        self.assertEqual(len(self.arm.asked), asked, "it stopped asking")

    def test_a_delete_of_a_disk_that_was_gone_already_is_marked_no_change_and_is_never_checked_by_cost_lines(self):
        plan, _ = self.approved(cost=3.65)
        del self.azure.resources[DISK.lower()]
        self.arm.totals = {OTHER_LINE: 1.5}
        done = self.make_change(plan)
        self.assertEqual((done.kind, done.action.state), ("unchanged", "done"))
        self.assertTrue(done.action.no_change)
        self.assertEqual(done.action.verification, {"gone": True, "noChange": True, "note": "already gone"})
        self.clock.advance(days=4)
        self.assertEqual(tick(self.t).verified, [])
        self.assertEqual(self.arm.asked, [], "there is nothing to confirm: this approval wrote nothing")
        after = self.store.action_get(plan.plan_id)
        self.assertEqual((after.state, after.verified_at, "costAfterUsd" in after.verification), ("done", None, False))
        self.assertEqual(self.store.case_get(plan.case_id).status, "done")

    def test_without_a_cost_reader_the_deletion_is_still_checked(self):
        self.t.arm = None
        plan, _ = self.approved()
        self.make_change(plan)
        self.clock.advance(days=5)
        tick(self.t)
        self.assertEqual(self.store.action_get(plan.plan_id).state, "done")


if __name__ == "__main__":
    unittest.main()
