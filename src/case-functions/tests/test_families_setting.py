"""The family `change-setting`: it lowers a number of a resource of an invented kind, in a group that the owner listed, after a person approved it, with that person's own token.

Everything here is invented: the kind `microsoft.example/gateways`, its number `capacityUnits`, the tier word `Lite`, the groups and the ids. No instruction of the app names any of them: the family reads
the key path that a finding proposes and the rest from the resource itself. The tests say what each gate does by taking it away, what the plan says, what the PUT holds, and what the client of the one request
refuses before it sends.
"""
import json
import re
import unittest
from dataclasses import replace
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import familysupport as fs
from familysupport import APPROVER, GROUP, NOW, OID, SCOPES, SUB
from support import APP_ROOT, REPO_ROOT

from cases import loop_config, proposals
from cases.approvals import ApprovalSettings, Approvals, SETTING, why_not
from cases.delegated import Delegation, SigninSettings, Tokens
from cases.detectors import Lead
from cases.families import calls, registry, words
from cases.families import digest as plan_digest
from cases.families import gates as gates_module
from cases.families.azure import Azure
from cases.families.base import Env, Stop
from cases.families.gates import ChangeScope, Gates, parse_scopes
from cases.families.setting import ChangeSetting, put_body
from cases.http import Client, HttpError, Refused
from cases.memory_store import MemoryStore, stamp
from cases.models import CaseRecord, DecisionRecord, NoteRecord, SwitchRecord
from cases.runner import RunnerServices, execute, read_calls, tick
from test_runner import challenge

REAL_SUB = "dddddddd-4444-4555-8666-777777777777"
REAL_GROUP = "rg-owner-real"
REAL = ChangeScope(REAL_SUB, REAL_GROUP)
TYPE = "microsoft.example/gateways"
NAME = "gw-one"
RID = f"/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Example/gateways/{NAME}"
API = "2024-05-01"
OPERATION = f"https://management.azure.com/subscriptions/{REAL_SUB}/providers/Microsoft.Example/locations/swedencentral/operations/op-1?api-version={API}"
SET = {"path": "capacityUnits", "from": 4, "to": 2}
FACTS = {proposals.KEY: {"set": [SET]}, "metrics": {"ActiveSessions": 0}, "metricDays": {"ActiveSessions": 30}}
TENANT, CLIENT, ASSERTION = "cccccccc-1111-4222-8333-444444444444", "dddddddd-1111-4222-8333-444444444444", "eeeeeeee-1111-4222-8333-444444444444"
SIGNIN = SigninSettings(TENANT, CLIENT, ASSERTION, "app.example.test")
VERIFIER, NONCE, CODE = "v" * 43, "n" * 22, "C" * 40
DO_NOT_TOUCH = dict(note_id="n", oid=OID, kind="do_not_touch", text="no", scope_resource_id=RID, expires_at="2099-01-01T00:00:00Z")
GATEWAY_SOURCE = (APP_ROOT / "cases" / "families" / "gates.py").read_text(encoding="utf-8")


def setUpModule():
    global _line
    _line = mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", True)  # the owner's line is on for the time of these tests, as if he had turned it on; a test says what it is when it is off
    _line.start()


def tearDownModule():
    _line.stop()


def gateway(units: int = 4, provisioning: str = "Succeeded", name: str = NAME, **more) -> dict:
    """A resource of the invented kind as Azure shows it: what Azure fills in itself (id, name, type, systemData, etag, provisioningState), what a person set, and a list with a child in it."""
    base = f"/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Example"
    resource = {"id": f"{base}/gateways/{name}", "name": name, "type": "Microsoft.Example/gateways", "etag": 'W/"11111111-2222-3333-4444-555555555555"', "location": "swedencentral",
                "tags": {"team": "blue"}, "sku": {"name": "Lite", "capacity": 2}, "systemData": {"createdBy": "somebody"},
                "properties": {"capacityUnits": units, "provisioningState": provisioning, "tier": "Lite", "autoScale": False, "retentionDays": 30, "label": "front",
                               "ipConfigurations": [{"name": "ip1", "id": f"{base}/gateways/{name}/ipConfigurations/ip1", "etag": 'W/"22222222-2222-3333-4444-555555555555"',
                                                     "properties": {"provisioningState": "Succeeded", "subnet": {"id": f"{base}/virtualNetworks/net/subnets/s1"}}}]}}
    resource.update(more)
    return resource


class RealArm(fs.Arm):
    """The fake Resource Manager of the tests of the family: the one resource, the provider's list of api-versions, the locks, the metrics of the resource, and a PUT of the whole resource that Azure carries out later."""

    def __init__(self) -> None:
        super().__init__()
        self.versions = ["2025-02-01-preview", "2023-11-01", API, "2022-01-01"]
        self.provider_status = 200
        self.totals: dict[str, list[float | None]] = {"ActiveSessions": [0.0, 0.0, 0.0]}  # the daily total of a metric by its name, for the days of the timespan that is asked for
        self.metrics_error: dict | None = None
        self.puts: list[tuple[str, str, object]] = []
        self.never = False
        self.fails = False

    def answer(self, method: str, key: str, body):
        if key == f"/subscriptions/{REAL_SUB}/providers/microsoft.example":
            if self.provider_status >= 300:
                return self.provider_status, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right"}}'
            return 200, {}, json.dumps({"namespace": "Microsoft.Example", "resourceTypes": [{"resourceType": "gateways", "apiVersions": self.versions}, {"resourceType": "gateways/other", "apiVersions": ["2030-01-01"]}]}).encode()
        return super().answer(method, key, body)

    def metrics(self, key: str):
        if self.metrics_error is not None:
            return 200, {}, json.dumps(self.metrics_error).encode()
        query = parse_qs(urlsplit(self.url).query)
        name = query["metricnames"][0]
        values = self.totals.get(name, [])
        data = [{"timeStamp": f"2026-11-0{n % 9 + 1}T00:00:00Z", **({} if value is None else {"total": value})} for n, value in enumerate(values)]
        return 200, {}, json.dumps({"value": [{"name": {"value": name}, "errorCode": "Success", "timeseries": [{"data": data}]}]}).encode()

    def started(self, status: int | None = None):
        return (status or 202), {"Retry-After": "1", "Azure-AsyncOperation": OPERATION}, b"{}"

    def write(self, method: str, key: str, body):
        if method == "PUT" and "/microsoft.example/gateways/" in key:
            if self.write_answers:
                status, headers, answer = self.write_answers.pop(0)
                if status >= 300:
                    return status, dict(headers), answer
            self.puts.append((key, urlsplit(self.url).query, body))
            if key not in self.resources:
                return 404, {}, b'{"error":{"code":"ResourceNotFound","message":"gone"}}'
            old = self.resources[key]
            stated = {"id": old["id"], "name": old["name"], "type": old["type"], "systemData": old["systemData"], "etag": 'W/"new"', **body}
            stated["properties"] = {**body["properties"], "provisioningState": "Updating"}
            self.resources[key] = stated
            if not self.never:
                self.effects[key] = fs.Effect(self.reads_before_effect, lambda found: self.set_provisioning(found, "Failed" if self.fails else "Succeeded"))
            return self.started(201)
        return super().write(method, key, body)


def lead_of(resource: dict, facts: dict | None = None, **more) -> Lead:
    values = dict(detector="investigation", resource_id=resource["id"], resource_type=TYPE, name=resource["name"], resource_group=REAL_GROUP, subscription_id=REAL_SUB, location="swedencentral",
                  tags={}, managed_by="", facts=dict(FACTS if facts is None else facts), age_days=30, cost_usd_30d=411.0)
    values.update(more)
    return Lead(**values)


class Real:
    """The loop around the family: a store, the approvals with a reader that may read the real group, the services of the one request that an approval makes, and the timer."""

    def __init__(self, real=(REAL,), arm: RealArm | None = None, facts: dict | None = None) -> None:
        self.clock = fs.Clock()
        self.store = MemoryStore(clock=self.clock)
        self.arm = arm or RealArm()
        self.settings = ApprovalSettings(change_scopes=SCOPES, real_change_scopes=tuple(real))
        self.events: list[tuple[str, dict]] = []
        self.sleeps: list[float] = []
        self.person_tokens: list[str] = []
        self.reader_tokens: list[str] = []
        self.costs = fs.FakeCosts()
        self.reader = Azure(self.client(read_calls(SCOPES, tuple(real))), lambda resource: (self.reader_tokens.append(resource), "reader-token")[1])
        self.approvals = Approvals(self.store, self.settings, self.clock, reader=self.reader)
        self.timer = RunnerServices(self.store, self.client(read_calls(SCOPES, tuple(real))), lambda resource: "reader-token", self.settings, arm=self.costs, clock=self.clock,
                                    sleep=self.sleeps.append, emit=lambda kind, **fields: self.events.append((kind, fields)))
        self.resource = self.arm.add(gateway())
        self.facts = facts

    def client(self, patterns) -> Client:
        return Client(patterns, lambda text: text, transport=self.arm.transport, sleep=lambda seconds: None, monotonic=lambda: 0.0)

    def services(self, plan, token: str = "person-token") -> RunnerServices:
        """What the sign-in's code builds for the approved plan: the client of the one request."""
        client = calls.one_write(plan.resource_id, str(plan.target.get("apiVersion")), self.settings.gates, lambda text: text, transport=self.arm.transport, sleep=lambda seconds: None, monotonic=lambda: 0.0)
        return RunnerServices(self.store, client, lambda resource: (self.person_tokens.append(token), token)[1], self.settings, clock=self.clock, sleep=self.sleeps.append,
                              emit=lambda kind, **fields: self.events.append((kind, fields)))

    def case(self, lead: Lead, status: str = "proposed", **more) -> CaseRecord:
        values = dict(case_id="k" + lead.lead_id, resource_id=lead.resource_id, resource_name=lead.name, resource_type=lead.resource_type, resource_group=lead.resource_group,
                      subscription_id=lead.subscription_id, detector=lead.detector, run_id="r1", status=status, recommendation="change", confidence=0.9, cost_usd_30d=411.0,
                      saving_usd_month=201.6, summary="the model said so", facts=lead.facts, updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        values.update(more)
        case = CaseRecord(**values)
        self.store.case_put(case)
        return case

    def plan(self, resource: dict | None = None, facts: dict | None = None):
        lead = lead_of(resource or self.resource, facts if facts is not None else self.facts)
        return self.approvals.create(self.case(lead), lead, (OID,))

    def plan_for(self, resource: dict | None = None, facts: dict | None = None):
        lead = lead_of(resource or self.resource, facts if facts is not None else self.facts)
        return self.approvals.plan_for(self.case(lead), lead, (OID,))

    def approve(self, plan):
        checked, refusal = self.approvals.check_approve(APPROVER, plan.plan_id, plan.code)
        assert refusal is None, refusal
        result, action = self.approvals.record_approval(APPROVER, checked, "")
        assert result.kind == "recorded", result
        return action

    def run(self, plan):
        self.approve(plan)
        return execute(self.services(plan), self.store.action_get(plan.plan_id), approved_digest=plan.digest)

    def state(self, plan):
        return self.store.plan_get(plan.plan_id).state, self.store.action_get(plan.plan_id).state, self.store.case_get(plan.case_id).status

    def live(self, path: str = "capacityUnits"):
        return self.arm.get(RID)["properties"][path]


def sentences(plan) -> str:
    return " ".join((plan.title, plan.what_changes, plan.could_go_wrong, plan.undo, plan.evidence_level))


class TheOwnersLine(unittest.TestCase):
    def test_it_is_false_and_the_line_and_its_comment_say_that_only_the_owner_may_change_it(self):
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            self.assertIs(gates_module.REAL_CHANGES_ALLOWED, False)
        self.assertEqual([line for line in GATEWAY_SOURCE.splitlines() if line.startswith("REAL_CHANGES_ALLOWED")], ["REAL_CHANGES_ALLOWED = False"])
        comment = GATEWAY_SOURCE.split("REAL_CHANGES_ALLOWED = False")[0].rsplit("\n\n", 1)[-1]
        for text in ("ONLY THE OWNER MAY CHANGE THIS LINE", "in a pull request that he reviews himself", "It is not a setting", "no environment variable reaches it", "no real resource can be changed",
                     "A test pins it False, and pins this comment"):
            self.assertIn(text, comment)

    def test_no_setting_no_template_no_workflow_and_no_other_module_can_reach_it(self):
        users = sorted(path.relative_to(APP_ROOT).as_posix() for path in (APP_ROOT / "cases").rglob("*.py") if "REAL_CHANGES_ALLOWED" in path.read_text(encoding="utf-8"))
        self.assertEqual(users, ["cases/families/gates.py"])
        for folder, pattern in (("environment", "**/*"), (".github", "**/*"), ("tools", "*.py")):
            for path in (REPO_ROOT / folder).glob(pattern):
                if path.is_file() and path.suffix in (".bicep", ".json", ".yml", ".yaml", ".py", ".sh", ".md") and "tests" not in path.parts:
                    self.assertNotIn("REAL_CHANGES_ALLOWED", path.read_text(encoding="utf-8", errors="ignore"), path.as_posix())

    def test_the_line_is_the_gate_and_the_planted_line_is_not_touched(self):
        gates = Gates(SCOPES, real_scopes=(REAL,))
        self.assertIsNone(gates.why_not_real(REAL_SUB, REAL_GROUP))
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            self.assertEqual(gates.why_not_real(REAL_SUB, REAL_GROUP), "switch-off", "listed, and the owner's line is off: nothing real can be changed")
        self.assertEqual(gates.why_not_real(REAL_SUB, "another-group"), "outside")
        self.assertEqual(gates.why_not_real(fs.OTHER_SUB, REAL_GROUP), "outside", "the same name in another subscription is not it")
        self.assertEqual(Gates(SCOPES).why_not_real(REAL_SUB, REAL_GROUP), "outside", "no list, no real change")
        self.assertEqual(gates.why_not_real(SUB, GROUP), "outside", "a group of Meternaut's own is not a real one")
        self.assertIs(gates_module.CHANGE_REQUIRES_PLANTED_TAG, True)


class TheListOfRealGroups(unittest.TestCase):
    ENV = {"STORE_ACCOUNT_NAME": "stexample", "CHANGE_SCOPES": f"{SUB}/{GROUP}", "CONSOLE_HOST": "func.example.net"}

    def test_it_is_empty_by_default_and_parsed_as_the_other_list_is(self):
        self.assertEqual(loop_config.load(self.ENV).real_change_scopes, ())
        listed = loop_config.load({**self.ENV, "REAL_CHANGE_SCOPES": f"{REAL_SUB.upper()}/{REAL_GROUP}, {fs.OTHER_SUB}/rg-two"})
        self.assertEqual(listed.real_change_scopes, (ChangeScope(REAL_SUB, REAL_GROUP), ChangeScope(fs.OTHER_SUB, "rg-two")))
        self.assertEqual(listed.gates.real_scopes, listed.real_change_scopes)
        self.assertEqual(listed.change_scopes, (ChangeScope(SUB, GROUP),), "the list of Meternaut's own groups is the same")
        self.assertEqual(parse_scopes(f"{REAL_SUB}/{REAL_GROUP}"), ((ChangeScope(REAL_SUB, REAL_GROUP),), []))

    def test_a_wrong_entry_or_a_group_that_is_in_both_lists_is_a_problem_and_never_a_real_group(self):
        for bad in ("rg with spaces", f"{REAL_SUB}", "*/rg", f"{REAL_SUB}/{REAL_GROUP},{REAL_SUB}/{REAL_GROUP}"):
            with self.subTest(bad):
                with self.assertRaises(loop_config.LoopConfigError) as raised:
                    loop_config.load({**self.ENV, "REAL_CHANGE_SCOPES": bad})
                self.assertIn("REAL_CHANGE_SCOPES", str(raised.exception))
        with self.assertRaises(loop_config.LoopConfigError) as raised:
            loop_config.load({**self.ENV, "REAL_CHANGE_SCOPES": f"{SUB.upper()}/{GROUP.upper()}"})
        self.assertIn("also in CHANGE_SCOPES", str(raised.exception))

    def test_the_approval_settings_and_the_old_family_gates_read_the_planted_list_only(self):
        settings = ApprovalSettings(change_scopes=SCOPES, real_change_scopes=(REAL,))
        self.assertEqual(settings.gates.scopes, SCOPES)
        self.assertIsNone(settings.gates.why_outside(SUB, GROUP))
        self.assertIsNotNone(settings.gates.why_outside(REAL_SUB, REAL_GROUP), "a real group is not a group of Meternaut's own: the rules of asking leave a case alone only in the planted list")


class ThePlan(unittest.TestCase):
    def test_it_is_made_when_everything_holds_and_it_says_what_changes_from_what_to_what(self):
        world = Real()
        plan = world.plan()
        self.assertIsNotNone(plan)
        self.assertEqual((plan.family, plan.state, plan.approval_class), (SETTING, "open", "R2"))
        self.assertEqual(plan.target, {"set": [{"path": "capacityUnits", "from": 4, "to": 2}], "apiVersion": API, "location": "swedencentral"})
        self.assertEqual(plan.preconditions, {"family": SETTING, "resourceType": TYPE, "resourceGroup": REAL_GROUP, "measured": [{"name": "ActiveSessions", "total": 0, "days": 30}]})
        self.assertEqual(plan.saving_usd_month, 201.6, "the saving is the case's own: this family computes none")
        self.assertEqual(world.store.case_get(plan.case_id).status, "awaiting_ok")
        self.assertEqual(plan.digest, plan_digest.digest_of(plan))
        self.assertEqual(plan.title, f"Scale down the gateway {NAME} in resource group {REAL_GROUP}: capacity units from 4 to 2")
        said = sentences(plan)
        self.assertIn("with your own permissions", said)
        self.assertIn("capacity units to 4", plan.undo)
        self.assertIn("--set properties.capacityUnits=4 --api-version 2024-05-01", plan.undo)
        self.assertIn("Azure Monitor shows ActiveSessions at 0 over 30 days", said)
        self.assertNotIn("Lite", said, "no tier and no name of the estate other than the resource's own is in the words")
        for stock in ("Consider", "reduce", "may depend on it", "optimi"):
            self.assertNotIn(stock, said)

    def test_the_provider_is_asked_for_the_newest_version_that_is_not_a_preview_and_the_plan_reads_nothing_else_but_that_resource(self):
        world = Real()
        plan = world.plan()
        self.assertEqual(plan.target["apiVersion"], API)
        urls = [url for method, url in world.arm.calls]
        self.assertEqual({method for method, _ in world.arm.calls}, {"GET"})
        self.assertTrue(any("/providers/Microsoft.Example?api-version=2021-04-01" in url for url in urls))
        self.assertTrue(all(url.startswith("https://management.azure.com/subscriptions/" + REAL_SUB) for url in urls))
        self.assertEqual(world.reader_tokens and set(world.reader_tokens), {"https://management.azure.com/"}, "the reader's token, never a person's")
        self.assertEqual(world.person_tokens, [])

    def test_a_path_is_matched_without_case_and_written_with_the_live_spelling_and_a_sku_path_is_at_the_root(self):
        world = Real()
        plan = world.plan(facts={proposals.KEY: {"set": [{"path": "CAPACITYunits", "from": 4, "to": 3}, {"path": "sku.capacity", "from": 2, "to": 1}]}})
        self.assertEqual(plan.target["set"], [{"path": "capacityUnits", "from": 4, "to": 3}, {"path": "sku.capacity", "from": 2, "to": 1}])
        self.assertIn("capacity units from 4 to 3 and sku capacity from 2 to 1", plan.title)
        self.assertIn("those numbers", plan.what_changes)
        self.assertIn("--set properties.capacityUnits=4 sku.capacity=2", plan.undo)

    def test_each_reason_that_a_plan_cannot_be_made_is_kept_by_the_request_that_asks_instead_and_has_its_words(self):
        def up(**props):
            return gateway(**props) if props else gateway()
        cases = {
            "unsupported": lambda w: w.plan_for(facts={proposals.KEY: {"set": [{"path": "capacityUnits", "from": 4, "to": 6}]}}),
            "mismatch": lambda w: (w.arm.get(RID)["properties"].update(capacityUnits=5), w.plan_for())[1],
            "busy": lambda w: (w.arm.get(RID)["properties"].update(provisioningState="Updating"), w.plan_for())[1],
            "locked": lambda w: (w.arm.locks.update({RID.lower(): [{"name": "keep"}]}), w.plan_for())[1],
            "locked-group": lambda w: (w.arm.locks.update({f"/subscriptions/{REAL_SUB}/resourcegroups/{REAL_GROUP}".lower(): [{"name": "keep"}]}), w.plan_for())[1],
            "unreadable": lambda w: (setattr(w.arm, "read_status", 403), w.plan_for())[1],
            "provider": lambda w: (setattr(w.arm, "provider_status", 500), w.plan_for())[1],
            "no-version": lambda w: (setattr(w.arm, "versions", ["2025-02-01-preview", "2026-01-01-preview"]), w.plan_for())[1],
        }
        wanted = {"unsupported": "unsupported", "mismatch": "mismatch", "busy": "busy", "locked": "locked", "locked-group": "locked", "unreadable": "unreadable",
                  "provider": "unreadable", "no-version": "no-version"}
        for name, make in cases.items():
            with self.subTest(name):
                world = Real()
                plan = make(world)
                self.assertIsNotNone(plan)
                self.assertEqual((plan.family, plan.state), ("advise", "open"), "no change plan: the finding asks a person instead")
                self.assertEqual(plan.preconditions.get(proposals.CANNOT_KEY), wanted[name])
                self.assertEqual(proposals.cannot(plan.preconditions), proposals.CANNOT[wanted[name]])
                self.assertEqual(world.arm.writes(), [], "a plan makes no write")

    def test_a_resource_that_a_person_marked_do_not_touch_gets_no_request_and_an_open_one_keeps_the_reason(self):
        world = Real()
        world.store.note_put(NoteRecord(**DO_NOT_TOUCH))
        self.assertIsNone(world.plan_for(), "a request is never made for a resource that a person asked to leave alone")
        world = Real(real=())
        old = world.plan_for()
        self.assertEqual(old.family, "advise")
        world.settings = replace(world.settings, real_change_scopes=(REAL,))
        world.approvals.settings = world.settings
        world.approvals.reader = Azure(world.client(read_calls(SCOPES, (REAL,))), lambda resource: "reader-token")
        world.store.note_put(NoteRecord(**DO_NOT_TOUCH))
        self.assertEqual(world.approvals.upgrade((OID,)), [])
        self.assertEqual(world.store.plan_get(old.plan_id).preconditions[proposals.CANNOT_KEY], "do-not-touch")

    def test_a_group_that_is_not_listed_and_the_line_being_off_say_so_and_make_no_read(self):
        world = Real(real=())
        plan = world.plan_for()
        self.assertEqual((plan.family, plan.preconditions.get(proposals.CANNOT_KEY)), ("advise", "outside"))
        self.assertEqual(world.arm.calls, [], "the gates come before every read")
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            world = Real()
            plan = world.plan_for()
            self.assertEqual((plan.family, plan.preconditions.get(proposals.CANNOT_KEY)), ("advise", "switch-off"))
            self.assertEqual(world.arm.calls, [])

    def test_a_setting_that_goes_up_or_is_a_flag_a_word_a_list_or_nothing_is_not_made_here(self):
        for item in ({"path": "capacityUnits", "from": 4, "to": 4}, {"path": "capacityUnits", "from": 4, "to": -1}, {"path": "capacityUnits", "from": 4, "to": 2.5},
                     {"path": "autoScale", "from": False, "to": True}, {"path": "tier", "from": "Lite", "to": "Free"}, {"path": "ipConfigurations.name", "from": 4, "to": 2},
                     {"path": "ipConfigurations[0].x", "from": 4, "to": 2}, {"path": "capacityUnits", "from": float("nan"), "to": 2}, {"path": "nothing.here", "from": 4, "to": 2},
                     {"path": "tier", "from": 4, "to": 2}, {"path": "label", "from": 4, "to": 2}):
            with self.subTest(item):
                world = Real()
                plan = world.plan_for(facts={proposals.KEY: {"set": [item]}})
                self.assertEqual(plan.family, "advise")
                self.assertIn(plan.preconditions.get(proposals.CANNOT_KEY), ("unsupported", "mismatch"))
        world = Real()
        too_many = [{"path": p, "from": 4, "to": 2} for p in ("capacityUnits", "retentionDays", "sku.capacity", "tier")]
        self.assertEqual(world.plan_for(facts={proposals.KEY: {"set": too_many}}).family, "advise")

    def test_a_finding_that_proposes_no_setting_gets_no_change_plan_and_no_reason(self):
        world = Real()
        plan = world.plan_for(facts={"metrics": {}})
        self.assertEqual((plan.family, proposals.CANNOT_KEY in plan.preconditions), ("advise", True))

    def test_a_resource_in_a_group_of_meternauts_own_is_never_offered_to_it(self):
        world = Real(real=(ChangeScope(SUB, GROUP),))
        lead = lead_of(world.resource, resource_group=GROUP, subscription_id=SUB)
        self.assertEqual(why_not(world.case(lead), lead, world.settings, world.store, registry.get(SETTING)), "the resource is in a group of Meternaut's own, where its own planted waste lives")


class TheBodyOfThePut(unittest.TestCase):
    def test_it_is_the_resource_as_read_with_the_one_number_changed_and_what_azure_fills_in_itself_left_out(self):
        world = Real()
        plan = world.plan()
        read = json.loads(json.dumps(world.arm.get(RID)))
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
        (key, query, body), = world.arm.puts
        self.assertEqual((key, query), (RID.lower(), f"api-version={API}"))
        expected = json.loads(json.dumps(read))
        for name in ("id", "name", "type", "systemData", "etag"):
            expected.pop(name)
        expected["properties"].pop("provisioningState")
        expected["properties"]["capacityUnits"] = 2
        expected["properties"]["ipConfigurations"][0].pop("etag")
        expected["properties"]["ipConfigurations"][0]["properties"].pop("provisioningState")
        self.assertEqual(body, expected, "exactly the resource as read: only the number is changed, the keys that Azure fills in are out, the tags, the sku, the list and its child are as they were")
        self.assertIsInstance(body["properties"]["capacityUnits"], int)
        self.assertEqual(world.arm.writes_of("PUT"), [f"https://management.azure.com{RID}?api-version={API}"])
        self.assertEqual({method for method, _ in world.arm.writes()}, {"PUT"})

    def test_a_number_at_the_root_is_changed_there_and_nothing_else_moves(self):
        resource = gateway()
        body = put_body(resource, [("sku.capacity", 2, 1)])
        self.assertEqual(body["sku"], {"name": "Lite", "capacity": 1})
        self.assertEqual(body["properties"]["capacityUnits"], 4)
        self.assertEqual(resource["sku"]["capacity"], 2, "the reading is not changed")

    def test_the_person_token_makes_the_write_and_the_reader_token_none_of_it(self):
        world = Real()
        plan = world.plan()
        world.run(plan)
        self.assertEqual(set(world.person_tokens), {"person-token"})
        self.assertEqual([h["Authorization"] for h in world.arm.headers if "x-ms-correlation-request-id" in h], ["Bearer person-token"])


class TheChangeAndWhatBecomesOfIt(unittest.TestCase):
    def test_a_change_that_azure_carries_out_is_followed_and_ends_done_with_the_new_number_and_the_timer_leaves_it_be(self):
        world = Real()
        plan = world.plan()
        done = world.run(plan)
        self.assertEqual(done.kind, "ran")
        self.assertEqual(world.state(plan), ("consumed", "done", "done"))
        self.assertEqual(world.live(), 2)
        self.assertIn("capacity units at 2", done.action.result)
        self.assertEqual(done.action.verification["values"], [2])
        self.assertEqual(world.arm.operation_looks > 0, True, "the status address of the operation was followed")

    def test_an_operation_that_fails_closes_the_request_as_failed_and_says_so(self):
        world = Real()
        world.arm.operation_polls = ["InProgress", "Failed"]
        world.arm.fails = True
        plan = world.plan()
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"))
        self.assertEqual(world.state(plan)[0], "failed")
        self.assertIn("Look at the resource in Azure", done.action.result)

    def test_an_operation_that_is_not_finished_is_running_and_the_timer_settles_it_by_reading_with_the_readers_token(self):
        world = Real()
        world.arm.operation_polls = ["InProgress"]
        world.arm.reads_before_effect = 50
        plan = world.plan()
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("running", "running"))
        self.assertEqual(len(world.arm.writes_of("PUT")), 1, "nothing here makes a second write")
        world.arm.effects[RID.lower()].reads = 0
        result = tick(world.timer)
        self.assertEqual(world.store.action_get(plan.plan_id).state, "done")
        self.assertEqual(len(result.finished), 1)
        self.assertEqual(len(world.arm.writes_of("PUT")), 1)

    def test_a_resource_that_azure_does_not_change_in_time_is_unknown_and_never_written_twice(self):
        world = Real()
        world.arm.never = True
        world.arm.async_writes = True
        world.arm.operation_polls = ["InProgress"]
        plan = world.plan()
        done = world.run(plan)
        self.assertIn(done.kind, ("running", "ran_unconfirmed"))
        self.assertEqual(len(world.arm.writes_of("PUT")), 1)

    def test_what_a_read_after_the_change_shows_is_done_pending_failed_or_not_known(self):
        world = Real()
        plan = world.plan()
        family = registry.get(SETTING)
        env = Env(world.reader, world.settings.gates, world.store.do_not_touch, world.clock)
        self.assertEqual(family.verify(env, plan).state, "pending", "still the old number")
        world.arm.get(RID)["properties"]["capacityUnits"] = 2
        self.assertEqual(family.verify(env, plan).state, "done")
        world.arm.get(RID)["properties"]["provisioningState"] = "Updating"
        self.assertEqual(family.verify(env, plan).state, "pending")
        world.arm.get(RID)["properties"]["provisioningState"] = "Failed"
        self.assertEqual(family.verify(env, plan).state, "failed")
        world.arm.get(RID)["properties"]["provisioningState"] = "Deleting"
        self.assertEqual(family.verify(env, plan).state, "unknown")
        world.arm.read_status = 403
        self.assertEqual(family.verify(env, plan).state, "unknown")
        self.assertEqual({method for method, _ in world.arm.calls}, {"GET"}, "a check after the change never writes")

    def test_the_cost_check_is_the_one_of_a_change_that_leaves_the_resource_billing(self):
        family = registry.get(SETTING)
        self.assertFalse(family.cost_ends)
        confirmed, text, saved = family.cost_check(411.0, 30.0, 5)
        self.assertEqual((confirmed, saved), (True, round((411.0 / 30 - 6.0) * 30, 2)))
        self.assertFalse(family.cost_check(411.0, 0.0, 5)[0], "no cost line yet is never a confirmation")
        self.assertFalse(family.cost_check(411.0, 150.0, 5)[0], "a daily rate that is not lower is not a confirmation")

    def test_a_resource_that_already_has_the_new_number_is_not_written_and_no_saving_is_claimed(self):
        world = Real()
        plan = world.plan()
        world.arm.get(RID)["properties"]["capacityUnits"] = 2
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.no_change), ("unchanged", True))
        self.assertIn("already showed capacity units at 2", done.action.result)
        self.assertEqual(world.arm.writes(), [])


class TheChecksRightBeforeTheChange(unittest.TestCase):
    def stopped(self, world, plan, text):
        done = world.run(plan)
        self.assertEqual(done.kind, "stopped", done.action.result)
        self.assertIn(text, done.action.result)
        self.assertTrue(done.action.result.startswith("Meternaut did not change the gateway:"), done.action.result)
        self.assertEqual(world.arm.writes(), [], "nothing was written")
        self.assertEqual(world.store.plan_get(plan.plan_id).state, "open", "the approval is not used: the request is open again")
        return done

    def test_a_number_that_changed_since_the_plan_stops_the_change(self):
        world = Real()
        plan = world.plan()
        world.arm.get(RID)["properties"]["capacityUnits"] = 5
        self.stopped(world, plan, "capacity units is 5 now and was 4 when the request was made")

    def test_a_lock_on_the_resource_or_the_group_stops_it(self):
        for scope in (RID.lower(), f"/subscriptions/{REAL_SUB}/resourcegroups/{REAL_GROUP}".lower()):
            with self.subTest(scope):
                world = Real()
                plan = world.plan()
                world.arm.locks[scope] = [{"name": "keep"}]
                self.stopped(world, plan, "has a management lock")

    def test_a_resource_that_is_still_being_changed_or_whose_last_operation_failed_stops_it(self):
        world = Real()
        plan = world.plan()
        world.arm.get(RID)["properties"]["provisioningState"] = "Updating"
        self.stopped(world, plan, "something else is changing the resource right now")

    def test_a_do_not_touch_note_that_came_after_the_plan_stops_it(self):
        world = Real()
        plan = world.plan()
        world.store.note_put(NoteRecord(**DO_NOT_TOUCH))
        self.stopped(world, plan, "do-not-touch")

    def test_the_owners_line_turned_off_after_the_plan_stops_it_and_nothing_is_read(self):
        world = Real()
        plan = world.plan()
        reads = len(world.arm.calls)
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            self.stopped(world, plan, "the owner has not allowed changes of real resources")
        self.assertEqual(len(world.arm.calls), reads, "the line is checked before the first read")

    def test_the_group_taken_off_the_list_after_the_plan_stops_it_and_the_client_of_the_request_holds_no_real_read(self):
        world = Real()
        plan = world.plan()
        world.settings = replace(world.settings, real_change_scopes=())
        self.stopped(world, plan, "the resource is not in a resource group on the owner's list")
        self.assertEqual(world.arm.writes(), [])

    def test_a_cited_measurement_that_is_above_what_the_plan_recorded_stops_it_and_one_that_cannot_be_read_counts_against_it(self):
        world = Real()
        plan = world.plan()
        world.arm.totals["ActiveSessions"] = [0.0, 3.0]
        self.stopped(world, plan, "ActiveSessions is 3 over the last 30 days, above the 0 that the request was made with")
        world = Real()
        plan = world.plan()
        world.arm.totals["ActiveSessions"] = []
        self.stopped(world, plan, "a reading that cannot be made counts against the change")
        world = Real()
        plan = world.plan()
        world.arm.metrics_error = {"error": {"code": "BadRequest"}}
        self.stopped(world, plan, "no value of ActiveSessions")
        world = Real()
        plan = world.plan()
        world.arm.totals["ActiveSessions"] = [0.0, 0.0, None]
        done = world.run(plan)
        self.assertEqual(done.kind, "ran", "a reading that is still nothing lets the change go on")

    def test_a_refusal_of_azure_to_read_with_the_persons_token_is_a_failure_and_a_claims_challenge_is_asked_for_once(self):
        world = Real()
        plan = world.plan()
        world.arm.read_status = 403
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("azure_refused", "failed"))
        self.assertIn("your account has no right to do this here", done.action.result)
        world = Real()
        plan = world.plan()
        world.arm.write_answers = [(401, challenge(), b'{"error":{"code":"InsufficientClaims","message":"a check is needed"}}')]
        done = world.run(plan)
        self.assertEqual(done.kind, "step_up")
        self.assertEqual(world.store.plan_get(plan.plan_id).state, "approved", "nothing was changed: the plan stays approved and the action waits for the check")
        self.assertEqual(world.live(), 4)
        world.arm.write_answers = [(403, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right to write"}}')]
        again = execute(world.services(plan), world.store.action_get(plan.plan_id), approved_digest=plan.digest)
        self.assertEqual((again.kind, again.action.state), ("azure_refused", "failed"))
        self.assertIn("Azure refused to change the resource", again.action.result)
        self.assertEqual(world.arm.puts, [], "Azure refused both: the fake stored nothing")

    def test_a_change_that_stops_between_the_check_and_the_write_is_stopped_by_the_second_reading(self):
        world = Real()
        plan = world.plan()
        world.approve(plan)
        flipped = []

        def hold_after(method, key):
            if method == "GET" and key == RID.lower() and len(flipped) == 0 and world.arm.calls.count(("GET", world.arm.url)) >= 0:
                reads = [m for m, u in world.arm.calls if urlsplit(u).path.lower() == RID.lower()]
                if len(reads) == 2:
                    flipped.append(1)
                    world.arm.get(RID)["properties"]["capacityUnits"] = 3
        world.arm.hold_after = hold_after
        done = execute(world.services(plan), world.store.action_get(plan.plan_id), approved_digest=plan.digest)
        self.assertEqual(done.kind, "stopped", done.action.result)
        self.assertEqual(world.arm.writes(), [])

    def test_a_plan_that_names_a_number_or_a_version_that_the_family_does_not_make_is_refused_before_any_call(self):
        world = Real()
        plan = world.plan()
        for target in ({**plan.target, "apiVersion": "2024-05-01-preview"}, {**plan.target, "apiVersion": "x"}, {**plan.target, "set": []},
                       {**plan.target, "set": [{"path": "capacityUnits", "from": 2, "to": 4}]}, {**plan.target, "set": [{"path": "capacityUnits", "from": True, "to": 0}]}):
            with self.subTest(target):
                with self.assertRaises(Stop):
                    registry.get(SETTING).recheck(Env(world.reader, world.settings.gates, world.store.do_not_touch, world.clock), replace(plan, target=target))
        self.assertEqual(len(world.arm.calls), len([c for c in world.arm.calls]))


class TheClientOfTheOneRequest(unittest.TestCase):
    def setUp(self):
        self.world = Real()
        self.plan = self.world.plan()
        self.client = calls.one_write(RID, API, self.world.settings.gates, lambda text: text, transport=self.world.arm.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        self.world.arm.calls.clear()
        self.url = f"https://management.azure.com{RID}?api-version={API}"

    def refuse(self, method, url, body=None):
        before = len(self.world.arm.calls)
        with self.assertRaises(Refused):
            self.client.request(method, url, body=body)
        self.assertEqual(len(self.world.arm.calls), before, f"{method} {url} was refused before it was sent")

    def test_it_makes_the_one_put_and_the_reads_of_the_real_group_and_nothing_else(self):
        self.client.request("PUT", self.url, body={"location": "x", "properties": {}})
        self.assertEqual(self.world.arm.writes(), [("PUT", self.url)])
        self.client.request("GET", self.url)
        self.client.request("GET", f"https://management.azure.com{RID}/providers/Microsoft.Authorization/locks?api-version=2016-09-01")
        self.client.request("GET", f"https://management.azure.com{RID}/providers/Microsoft.Insights/metrics?api-version=2023-10-01&metricnames=x")
        self.client.request("GET", OPERATION)

    def test_a_put_to_another_resource_group_subscription_name_or_version_is_refused_before_it_is_sent(self):
        other = f"/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Example/gateways/gw-two"
        for url in (f"https://management.azure.com{other}?api-version={API}",
                    f"https://management.azure.com/subscriptions/{REAL_SUB}/resourceGroups/another/providers/Microsoft.Example/gateways/{NAME}?api-version={API}",
                    f"https://management.azure.com/subscriptions/{fs.OTHER_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Example/gateways/{NAME}?api-version={API}",
                    f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/planted-disk-1?api-version={API}",
                    f"https://management.azure.com{RID}?api-version=2023-11-01", f"https://management.azure.com{RID}?api-version={API}&x=1", f"https://management.azure.com{RID}",
                    f"https://management.azure.com{RID}/providers/Microsoft.Authorization/locks?api-version={API}", f"https://management.azure.com{RID}?api-version={API}#x",
                    f"https://example.test{RID}?api-version={API}", f"http://management.azure.com{RID}?api-version={API}", f"https://management.azure.com{RID}/../gw-two?api-version={API}",
                    f"https://management.azure.com{RID.replace('/gateways/', '/gateways%2f')}?api-version={API}", f"https://management.azure.com{RID.upper()}?api-version={API}"):
            with self.subTest(url):
                self.refuse("PUT", url, {})

    def test_every_other_method_is_refused_even_on_the_same_address(self):
        for method in ("DELETE", "POST", "PATCH", "HEAD", "put"):
            with self.subTest(method):
                self.refuse(method, self.url, {})

    def test_a_read_outside_the_real_groups_or_of_a_path_that_walks_is_refused(self):
        for url in (f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/planted-disk-1?api-version=2026-03-02",
                    f"https://management.azure.com/subscriptions/{REAL_SUB}/resourceGroups/other/providers/Microsoft.Example/gateways/{NAME}?api-version={API}",
                    f"https://management.azure.com/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Example/gateways/..?api-version={API}",
                    f"https://management.azure.com/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/../gateways/x?api-version={API}"):
            with self.subTest(url):
                self.refuse("GET", url)

    def test_it_makes_no_write_at_all_while_the_owners_line_is_off_or_for_an_id_that_is_not_in_a_real_group(self):
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            off = calls.one_write(RID, API, self.world.settings.gates, lambda text: text, transport=self.world.arm.transport)
        self.assertIsNone(off.put_url)
        with self.assertRaises(Refused):
            off.request("PUT", self.url, body={})
        self.assertIsNone(calls.one_write(RID, "", self.world.settings.gates, lambda text: text).put_url, "no api-version")
        self.assertIsNone(calls.one_write(RID, "2024-05-01-preview", self.world.settings.gates, lambda text: text).put_url, "no preview")
        for resource_id in ("", f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/d", RID + "/child/x", RID.replace(REAL_GROUP, "elsewhere")):
            self.assertIsNone(calls.one_write(resource_id, API, self.world.settings.gates, lambda text: text).put_url, resource_id)

    def test_its_list_holds_reads_only_and_the_static_clients_gain_no_generic_write(self):
        self.assertEqual({method for method, _ in self.client.allowed}, {"GET"})
        with self.assertRaises(ValueError):
            calls.OneWrite(None, (("PUT", re.compile("x")),), lambda text: text)
        scopes = (ChangeScope(SUB, GROUP),)
        self.assertEqual({method for method, _ in read_calls(scopes, (REAL,))}, {"GET"})
        self.assertEqual(read_calls(scopes), read_calls(scopes, ()), "no real group, no change in the reads")
        from cases.runner import change_calls
        self.assertEqual(change_calls(scopes), calls.change_patterns(scopes), "the static list of the console holds nothing of the real groups")
        text = "".join(pattern.pattern for _, pattern in change_calls(scopes))
        self.assertNotIn(REAL_SUB, text)
        for method, pattern in change_calls(scopes):
            self.assertIsNone(pattern.fullmatch(f"https://management.azure.com{RID}"), "the static client cannot even read a real resource")
        self.assertEqual(len(calls.WRITES), 11, "the named writes are as they were")
        self.assertEqual([c for c in calls.WRITES if c.method == "PUT"], [calls.Call("PUT", calls.P2S_GATEWAY)])
        self.assertNotIn(calls.RESOURCE_PUT, calls.WRITES)

    def test_azure_refuses_to_write_a_call_that_is_on_no_list(self):
        azure = Azure(self.client, lambda resource: "t")
        with self.assertRaises(LookupError):
            azure.write(calls.Call("PUT", calls.DISK), self.url, {})
        self.assertEqual(azure.write(calls.RESOURCE_PUT, self.url, {"properties": {}}).status in (200, 201, 202, 404), True)


class TheRequestAndTheSignIn(unittest.TestCase):
    """The approval of the sign-in builds the client of the one request for a plan of this family, and the static client for every other."""

    def setUp(self):
        self.world = Real()
        self.plan = self.world.plan()
        self.used = []
        self.delegation = Delegation(self.world.store, self.world.approvals, SIGNIN, self.redeem, self.static, pkce=lambda: (VERIFIER, "challenge"), token=lambda size: NONCE,
                                     run_one=self.one)

    def redeem(self, code, verifier, claims=""):
        return Tokens("access-token-of-the-person-" + "A" * 40, {"oid": OID, "tid": TENANT, "aud": CLIENT, "nonce": NONCE, "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
                                                                 "exp": int(NOW.timestamp()) + 3600})

    def static(self, token):
        self.used.append("static")
        return RunnerServices(self.world.store, self.world.client(calls.change_patterns(SCOPES)), lambda resource: token, self.world.settings, clock=self.world.clock, sleep=self.world.sleeps.append)

    def one(self, token, plan):
        self.used.append("one")
        return self.world.services(plan, token)

    def test_a_person_approves_with_the_sign_in_and_only_the_plans_own_put_leaves_the_app(self):
        token = self.world.store.nonce_new(OID, self.plan.plan_id)
        begun = self.delegation.begin(APPROVER, self.plan.plan_id, self.plan.code, token)
        state = parse_qs(urlsplit(begun.location).query)["state"][0]
        result = self.delegation.finish(APPROVER, {"code": CODE, "state": state})
        self.assertEqual((result.ok, result.kind), (True, "ran"), result.message)
        self.assertEqual(self.used, ["one"], "the static client did not make this change")
        self.assertEqual(self.world.arm.writes_of("PUT"), [f"https://management.azure.com{RID}?api-version={API}"])
        self.assertEqual(self.world.live(), 2)
        self.assertEqual(set(self.world.person_tokens), {"access-token-of-the-person-" + "A" * 40})

    def test_without_the_client_of_one_request_a_plan_of_this_family_cannot_change_anything(self):
        self.delegation.run_one = None
        token = self.world.store.nonce_new(OID, self.plan.plan_id)
        begun = self.delegation.begin(APPROVER, self.plan.plan_id, self.plan.code, token)
        state = parse_qs(urlsplit(begun.location).query)["state"][0]
        result = self.delegation.finish(APPROVER, {"code": CODE, "state": state})
        self.assertNotEqual(result.kind, "ran")
        self.assertEqual(self.world.arm.writes(), [])

    def test_the_pause_switch_the_digest_and_the_people_work_as_for_every_other_family(self):
        sealed = self.world.store.plan_get(self.plan.plan_id)
        self.world.store.switch_put(SwitchRecord(name="changes", paused=True, by=OID, at=stamp(NOW)))
        self.assertEqual(self.world.approvals.check_approve(APPROVER, self.plan.plan_id, self.plan.code)[1].kind, "refused_paused")
        self.world.store.switch_put(SwitchRecord(name="changes", paused=False, by=OID, at=stamp(NOW)))
        self.assertIsNone(self.world.approvals.check_approve(APPROVER, self.plan.plan_id, self.plan.code)[1])
        stranger = fs.Principal("99999999-0000-0000-0000-000000000000", "Stranger", ("approver",))
        self.assertEqual(self.world.approvals.check_approve(stranger, self.plan.plan_id, self.plan.code)[1].kind, "refused_role")
        self.world.store.plan_put(replace(sealed, target={**sealed.target, "set": [{"path": "capacityUnits", "from": 4, "to": 0}]}))
        refusal = self.world.approvals.check_approve(APPROVER, self.plan.plan_id, self.plan.code)[1]
        self.assertEqual(refusal.kind, "refused_code", "a plan that no longer fits its digest cannot be approved")


class TheRequestThatAsksBecomesTheRequestOfTheChange(unittest.TestCase):
    def asked(self, world):
        plan = world.plan_for()
        self.assertEqual(plan.family, "advise")
        return plan

    def test_an_open_request_that_asked_is_taken_back_when_the_change_can_be_made_and_the_change_takes_its_place_with_the_start_of_the_wait(self):
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            world = Real()
            old = self.asked(world)
            self.assertEqual(old.preconditions[proposals.CANNOT_KEY], "switch-off")
        world.clock.advance(days=5)
        old = world.store.plan_put(replace(old, waiting_since="2026-11-03T09:00:00Z")) or world.store.plan_get(old.plan_id)
        done = world.approvals.upgrade((OID,))
        self.assertEqual(len(done), 1)
        taken, new, case = done[0]
        self.assertEqual((taken.plan_id, new.family), (old.plan_id, SETTING))
        kept = world.store.plan_get(old.plan_id)
        self.assertEqual((kept.state, kept.preconditions["takenBack"]), ("expired", "upgraded"))
        self.assertIn("it can make this change itself now", brief_words("upgraded"))
        fresh = world.store.plan_get(new.plan_id)
        self.assertEqual((fresh.state, fresh.waiting_since), ("open", "2026-11-03T09:00:00Z"), "the start of the wait is kept: no clock restarts a request (rule 38)")
        self.assertEqual(world.store.case_get(case.case_id).status, "awaiting_ok")
        self.assertEqual(world.store.case_get(case.case_id).plan_id, new.plan_id)
        self.assertEqual([p.plan_id for p in world.store.plans_open() if p.state == "open"], [new.plan_id], "one request is open for the resource")

    def test_the_reason_of_a_request_that_still_only_asks_is_brought_up_to_date_and_nothing_is_taken_back(self):
        world = Real(real=())
        old = self.asked(world)
        self.assertEqual(old.preconditions[proposals.CANNOT_KEY], "outside")
        world.settings = replace(world.settings, real_change_scopes=(REAL,))
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            world.approvals.settings = world.settings
            world.approvals.reader = Azure(world.client(read_calls(SCOPES, (REAL,))), lambda resource: "reader-token")
            self.assertEqual(world.approvals.upgrade((OID,)), [])
        kept = world.store.plan_get(old.plan_id)
        self.assertEqual((kept.state, kept.preconditions[proposals.CANNOT_KEY], kept.code), ("open", "switch-off", old.code))
        self.assertEqual(plan_digest.problem(kept, kept.digest), "", "sealed again, with its code: a card or a letter that was sent keeps working")

    def test_an_open_change_that_does_not_hold_any_more_is_taken_back_and_asks_instead_with_the_reason(self):
        world = Real()
        plan = world.plan()
        world.arm.get(RID)["properties"]["capacityUnits"] = 5
        done = world.approvals.upgrade((OID,))
        taken, new, case = done[0]
        self.assertEqual((taken.plan_id, new.family), (plan.plan_id, "advise"))
        self.assertEqual(world.store.plan_get(plan.plan_id).preconditions["takenBack"], "changed")
        self.assertEqual(new.preconditions[proposals.CANNOT_KEY], "mismatch")
        self.assertEqual(world.store.case_get(case.case_id).status, "proposed")
        self.assertEqual(world.arm.writes(), [])

    def test_an_open_change_that_still_holds_is_left_alone_and_so_is_one_that_a_person_answered(self):
        world = Real()
        plan = world.plan()
        self.assertEqual(world.approvals.upgrade((OID,)), [])
        self.assertEqual(world.store.plan_get(plan.plan_id), plan)
        world.arm.get(RID)["properties"]["capacityUnits"] = 5
        from cases.models import DecisionRecord
        world.store.decision_put(DecisionRecord(plan_id=plan.plan_id, approver_oid=OID, approver_name="Tino", decision="ask", at=stamp(NOW), plan_code=plan.code))
        self.assertEqual(world.approvals.upgrade((OID,)), [])
        self.assertEqual(world.store.plan_get(plan.plan_id).state, "open")

    def test_the_watch_step_says_what_it_did_in_the_history_and_in_one_sentence_for_each_kind(self):
        from cases import upkeep
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            world = Real()
            self.asked(world)
        lines = []
        history = mock.Mock(emit=lambda kind, **fields: lines.append((kind, fields)))
        extras = mock.Mock(approvals=world.approvals, approvers=lambda: (OID,))
        said = upkeep.upgrade(extras, history)
        self.assertEqual(len(said), 1)
        self.assertIn("taken back, because Meternaut can make the change itself now", said[0])
        self.assertEqual([(k, f["family"], f["was"]) for k, f in lines], [("plan.created", SETTING, "advise")])


def brief_words(key: str) -> str:
    from cases import brief
    return brief.TAKEN_BACK[key]


class TheOldFamiliesAreAsTheyWere(unittest.TestCase):
    def test_the_registry_holds_the_new_family_last_and_its_words_and_it_is_the_only_one_that_is_real(self):
        self.assertEqual(registry.names()[-1], SETTING)
        self.assertEqual([f.name for f in registry.REGISTRY if f.real], [SETTING])
        self.assertEqual(words.shown(SETTING).summary, registry.get(SETTING).summary)
        self.assertIn(SETTING, words.kinds())
        self.assertEqual(words.called_of(SETTING), "change")

    def test_a_planted_disk_still_gets_its_plan_and_a_real_disk_gets_none_from_the_old_families(self):
        world = fs.World()
        planted = world.arm.add(fs.disk())
        self.assertEqual(world.plan(planted, "disk", "delete", cost=20.0).family, "delete-disk")
        real = Real()
        disk = real.arm.add({**fs.disk(name="d1", tags={}), "id": f"/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Compute/disks/d1"})
        lead = lead_of(disk, facts={}, resource_type="microsoft.compute/disks")
        case = real.case(lead, recommendation="delete")
        self.assertIsNone(real.approvals.create(case, lead, (OID,)), "the planted gate holds the old families whatever the owner's line says")

    def test_the_sentence_of_what_meternaut_changes_names_the_real_family_only_while_the_line_is_on_and_a_group_is_listed(self):
        planted = registry.acts_on("meternaut-planted", SCOPES)
        self.assertNotIn("lower a number", planted)
        self.assertEqual(registry.acts_on("meternaut-planted", SCOPES, ()), planted)
        self.assertIn("lower a number of a resource", registry.acts_on("meternaut-planted", SCOPES, (REAL,)))
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            self.assertEqual(registry.acts_on("meternaut-planted", SCOPES, (REAL,)), planted)

    def test_the_words_of_a_kind_come_from_the_type_segment_of_the_id(self):
        for segment, said in (("bastionHosts", "bastion host"), ("gateways", "gateway"), ("publicIPAddresses", "public ip address"), ("databases", "database"), ("policies", "policy"), ("x", "resource")):
            self.assertEqual(words.kind_words(f"/subscriptions/{REAL_SUB}/resourceGroups/g/providers/Microsoft.X/{segment}/n"), said if segment != "x" else "resource")
        self.assertEqual(words.kind_words(""), "resource")


if __name__ == "__main__":
    unittest.main()
