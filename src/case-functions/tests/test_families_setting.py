"""The family `change-setting`: it lowers a number of a resource of an invented kind, in a group that the owner listed, after a person approved it, with that person's own token.

Everything here is invented: the kind `microsoft.example/gateways`, its number `capacityUnits`, the tier word `Lite`, the groups and the ids. No instruction of the app names any of them: the family reads
the key path that a finding proposes and the rest from the resource itself. The tests say what each gate does by taking it away, what the plan says, what the PUT holds, and what the client of the one request
refuses before it sends.
"""
import datetime as dt
import json
import re
import unittest
from dataclasses import replace
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import familysupport as fs
from familysupport import APPROVER, GROUP, NOW, OID, SCOPES, SUB
from support import APP_ROOT, REPO_ROOT
from test_cards import buttons_for, by_id
from test_families_briefs import console_of

from cases import approvals as approvals_module
from cases import brief as brief_mod
from cases import cardcheck, cards, letters, loop_config, proposals
from cases.approvals import ApprovalSettings, Approvals, SETTING, why_not
from cases.delegated import Delegation, SigninSettings, Tokens
from cases.detectors import Lead
from cases.families import calls, registry, words
from cases.families import digest as plan_digest
from cases.families import gates as gates_module
from cases.families import setting as setting_module
from cases.families.azure import Azure
from cases.families.base import Env, Stop
from cases.families.gates import ChangeScope, Gates, parse_scopes
from cases.families.setting import ChangeSetting, differences, kept_of, provisioning_of, put_body
from cases.http import Client, HttpError, Refused
from cases.memory_store import MemoryStore, stamp
from cases.models import AUTOMATED, HELD, CaseRecord, DecisionRecord, NoteRecord, SwitchRecord
from cases.people import Person
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
        self.also: dict = {}  # properties that Azure changes by itself when it carries out the update
        self.etag_header: str | None = None  # the ETag header that a read of the resource carries (else the etag of its body is all that there is)
        self.timeout_put = False  # the request of the PUT is sent and no answer comes

    def transport(self, method, url, headers, data, timeout):
        if method == "PUT" and self.timeout_put:
            self.calls.append((method, url))
            raise TimeoutError("timed out")
        return super().transport(method, url, headers, data, timeout)

    def read(self, key: str):
        status, headers, body = super().read(key)
        return (status, {**headers, "ETag": self.etag_header}, body) if status == 200 and self.etag_header else (status, headers, body)

    def settled(self, found):
        if found is not None:
            found["properties"].update(self.also)
        return self.set_provisioning(found, "Failed" if self.fails else "Succeeded")

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
            sent = self.headers[-1].get("If-Match")
            current = self.etag_header or self.resources.get(key, {}).get("etag")
            if sent is not None and (key not in self.resources or str(sent).removeprefix("W/").strip('"') != str(current).removeprefix("W/").strip('"')):
                return 412, {}, b'{"error":{"code":"PreconditionFailed","message":"the etag does not match"}}'
            self.puts.append((key, urlsplit(self.url).query, body))
            if key not in self.resources:
                return 404, {}, b'{"error":{"code":"ResourceNotFound","message":"gone"}}'
            old = self.resources[key]
            stated = {"id": old["id"], "name": old["name"], "type": old["type"], "systemData": old["systemData"], "etag": 'W/"new"', **body}
            stated["properties"] = {**body["properties"], "provisioningState": "Updating"}
            self.resources[key] = stated
            if not self.never:
                self.effects[key] = fs.Effect(self.reads_before_effect, self.settled)
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

    def regroup(self, real) -> None:
        """The owner lists other groups: the settings, the reader and the approvals are made again, over the same records."""
        self.settings = replace(self.settings, real_change_scopes=tuple(real))
        self.reader = Azure(self.client(read_calls(SCOPES, tuple(real))), lambda resource: "reader-token")
        self.approvals = Approvals(self.store, self.settings, self.clock, reader=self.reader)

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
        self.assertIn("It uses your own permissions", said)
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
        self.assertIn("with this change: capacity units from 4 to 3 and sku capacity from 2 to 1", plan.what_changes)
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
        world.regroup((REAL,))
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
                     {"path": "ipConfigurations[0].x", "from": 4, "to": 2}, {"path": "nothing.here", "from": 4, "to": 2},
                     {"path": "tier", "from": 4, "to": 2}, {"path": "label", "from": 4, "to": 2}):
            with self.subTest(item):
                world = Real()
                plan = world.plan_for(facts={proposals.KEY: {"set": [item]}})
                self.assertEqual(plan.family, "advise")
                self.assertIn(plan.preconditions.get(proposals.CANNOT_KEY), ("unsupported", "mismatch", "not-a-count"))
        world = Real()
        too_many = [{"path": p, "from": 4, "to": 2} for p in ("capacityUnits", "retentionDays", "sku.capacity", "tier")]
        self.assertEqual(world.plan_for(facts={proposals.KEY: {"set": too_many}}).family, "advise")

    def test_a_finding_that_proposes_no_setting_gets_no_change_plan_and_nothing_is_said_about_it(self):
        world = Real()
        plan = world.plan_for(facts={"metrics": {}})
        self.assertEqual((plan.family, proposals.CANNOT_KEY in plan.preconditions), ("advise", False))
        self.assertEqual(world.arm.calls, [], "no read for a finding that proposes no number")

    def test_a_resource_in_a_group_of_meternauts_own_is_never_offered_to_it(self):
        world = Real(real=(ChangeScope(SUB, GROUP),))
        lead = lead_of(world.resource, resource_group=GROUP, subscription_id=SUB)
        self.assertEqual(why_not(world.case(lead), lead, world.settings, world.store, registry.get(SETTING)), "the resource is in a group of Meternaut's own, where its own planted waste lives")


class TheBodyOfThePut(unittest.TestCase):
    def test_it_is_the_resource_as_read_with_the_one_number_changed_and_what_azure_fills_in_itself_at_the_root_left_out(self):
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
        self.assertEqual(body, expected, "exactly the resource as read: only the number is changed and the keys that Azure fills in at the root are out; the tags, the sku, the list and its child (with its etag and its state) are as they were")
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

    def test_a_number_that_changes_between_the_check_and_the_write_is_stopped_by_the_second_reading_and_nothing_is_written(self):
        world = Real()
        plan = world.plan()
        world.approve(plan)
        reads = []

        def hold_after(method, key):
            if method == "GET" and key == RID.lower():
                reads.append(key)
                if len(reads) == 1:  # the first reading after the approval is the check: somebody changes the number right after it
                    world.arm.get(RID)["properties"]["capacityUnits"] = 3
        world.arm.hold_after = hold_after
        done = execute(world.services(plan), world.store.action_get(plan.plan_id), approved_digest=plan.digest)
        self.assertEqual(done.kind, "stopped", done.action.result)
        self.assertIn("the resource changed after it was checked: capacity units is 3 now and was 4", done.action.result)
        self.assertEqual((len(reads), world.arm.writes()), (2, []))

    def test_a_plan_that_names_a_number_or_a_version_that_the_family_does_not_make_is_refused_before_any_call(self):
        world = Real()
        plan = world.plan()
        calls_before = len(world.arm.calls)
        for target in ({**plan.target, "apiVersion": "2024-05-01-preview"}, {**plan.target, "apiVersion": "x"}, {**plan.target, "set": []},
                       {**plan.target, "set": [{"path": "capacityUnits", "from": 2, "to": 4}]}, {**plan.target, "set": [{"path": "capacityUnits", "from": True, "to": 0}]}):
            with self.subTest(target):
                with self.assertRaises(Stop):
                    registry.get(SETTING).recheck(Env(world.reader, world.settings.gates, world.store.do_not_touch, world.clock), replace(plan, target=target))
        self.assertEqual(len(world.arm.calls), calls_before)


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
            self.assertIsNone(pattern.fullmatch(f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Example/gateways/gw-x"),
                              "nor a resource of a kind that no family names, not even in the group of Meternaut's own")
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
        world.store.plan_put(replace(old, waiting_since="2026-11-03T09:00:00Z"))
        old = world.store.plan_get(old.plan_id)
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
        world.regroup((REAL,))
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
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

    def test_a_read_that_fails_takes_nothing_back_of_an_open_change_and_a_request_that_asks_says_that_azure_could_not_be_read(self):
        world = Real()
        plan = world.plan()
        world.arm.provider_status = 503
        self.assertEqual(world.approvals.upgrade((OID,)), [])
        self.assertEqual(world.store.plan_get(plan.plan_id), plan, "a blip of Azure does not take back a request that a person may be about to answer")
        world = Real()
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            asked = self.asked(world)
        world.arm.provider_status = 503
        self.assertEqual(world.approvals.upgrade((OID,)), [])
        self.assertEqual(world.store.plan_get(asked.plan_id).preconditions[proposals.CANNOT_KEY], "unreadable")

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


PERSON = Person(OID, "Tino", ("approver", "owner"), "tino@example.com")
BASE = "https://meternaut.example"
CONTACTS = ("Maya (maya@example.com)", "Ops (ops@example.com)")


def shown(world, plan, action=None, **more):
    """The brief of the request of a plan, for the person who may answer it."""
    more.setdefault("may_answer", True)
    return brief_mod.build_brief(world.store.case_get(plan.case_id), plan, action, [], now=NOW, **more)


def card_of(b):
    return cards.decision_card(b, buttons_for(b))


class TheRulesOfAskingApplyToAChange(unittest.TestCase):
    def test_a_finding_that_no_saving_was_priced_for_gets_no_request_of_any_kind_and_nothing_is_read(self):
        world = Real()
        lead = lead_of(world.resource)
        case = world.case(lead, saving_usd_month=None)
        self.assertIsNone(world.approvals.plan_for(case, lead, (OID,)))
        self.assertEqual((world.store.plans_open(), world.arm.calls), ([], []))
        self.assertEqual(Real().plan_for().family, SETTING, "the same finding with a priced saving gets its change")

    def test_a_declined_change_is_not_asked_again_within_the_quiet_days_and_is_again_after_them(self):
        world = Real()
        plan = world.plan()
        world.store.plan_put(replace(plan, state="declined"))
        lead, case = lead_of(world.resource), replace(world.store.case_get(plan.case_id), status="proposed")
        world.clock.advance(days=10)
        self.assertIsNone(world.approvals.plan_for(case, lead, (OID,)), "a person said no ten days ago: nothing is made, not the change and not advice")
        world.clock.advance(days=25)
        self.assertEqual(world.approvals.plan_for(case, lead, (OID,)).family, SETTING)

    def test_the_quiet_days_count_from_the_answer_and_not_from_the_day_that_the_request_was_made(self):
        for kind in ("change", "advice"):
            with self.subTest(kind):
                world = Real()
                if kind == "advice":
                    with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
                        plan = world.plan_for()
                    self.assertEqual(plan.family, "advise")
                else:
                    plan = world.plan()
                world.clock.advance(days=40)  # it waited forty days, and then a person declined it
                world.store.decision_put(DecisionRecord(plan_id=plan.plan_id, approver_oid=OID, approver_name="Tino", decision="decline", at=stamp(world.clock()), plan_code=plan.code))
                world.store.plan_put(replace(world.store.plan_get(plan.plan_id), state="declined"))
                lead, case = lead_of(world.resource), replace(world.store.case_get(plan.case_id), status="proposed")
                world.clock.advance(days=5)
                self.assertIsNone(world.approvals.plan_for(case, lead, (OID,)), "five days after the answer, though the request is forty-five days old: nothing is made")
                world.clock.advance(days=24)
                self.assertIsNone(world.approvals.plan_for(case, lead, (OID,)), "twenty-nine days after the answer is still within the quiet days")
                world.clock.advance(days=2)
                self.assertIsNotNone(world.approvals.plan_for(case, lead, (OID,)), "thirty-one days after the answer it is asked again")

    def test_a_resource_that_an_automation_changed_lately_gets_the_warning_on_the_change_request_on_the_page_the_card_and_the_letter(self):
        world = Real()
        lead = lead_of(world.resource)
        since = stamp(NOW - dt.timedelta(days=3))
        plan = world.approvals.plan_for(world.case(lead, owner={"automatedAt": since}), lead, (OID,))
        self.assertEqual((plan.family, plan.preconditions[AUTOMATED]), (SETTING, since))
        b = shown(world, plan)
        self.assertTrue(b.heads_up.startswith("An automation changed this"), b.heads_up)
        self.assertIn(brief_mod.AUTOMATION_ACT, b.heads_up)
        self.assertEqual(by_id(card_of(b))["heads-up"]["text"], f"**Heads-up:** {b.heads_up}")
        letter = letters.approval_letter(plan, world.store.case_get(plan.case_id), PERSON, BASE, NOW, CONTACTS)
        self.assertIn(f"Heads-up: {b.heads_up}", letter.text)
        reply = console_of(world, plan, world.store.case_get(plan.case_id)).get(f"/ok/{plan.plan_id}")
        self.assertIn("An automation changed this", reply.main.text())
        old = Real()
        lead = lead_of(old.resource)
        quiet = old.approvals.plan_for(old.case(lead, owner={"automatedAt": stamp(NOW - dt.timedelta(days=20))}), lead, (OID,))
        self.assertEqual((quiet.family, AUTOMATED in quiet.preconditions), (SETTING, False), "an automation that changed it three weeks ago is no warning")


class ThePromiseAfterTheWrite(unittest.TestCase):
    def test_the_plan_does_not_promise_that_nothing_else_changes_and_says_what_is_checked_and_what_is_not_seen(self):
        plan = Real().plan()
        self.assertNotIn("nothing else of the", " ".join((plan.what_changes, plan.could_go_wrong, plan.undo)).lower(), "the promise that was made before is gone")
        self.assertIn("A property that Azure does not show when it is read is not sent, so Meternaut cannot promise that nothing else changes.", plan.what_changes)
        self.assertIn("Afterwards it reads the gateway again and checks the number, and that every other number and flag that it sent is still what it sent. It does not compare texts, such as a tier or a name.", plan.what_changes)
        self.assertNotIn("every other property", plan.what_changes, "the old promise covered more than the check holds")

    def test_a_text_that_azure_rewrites_after_the_put_is_not_seen_and_the_plan_said_that_texts_are_not_compared(self):
        world = Real()
        world.arm.also = {"tier": "Free"}  # Azure rewrites a text (Lite to Free) when it carries out the update
        plan = world.plan()
        self.assertIn("It does not compare texts, such as a tier or a name.", plan.what_changes)
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state, done.action.verification["compared"], "differences" in done.action.verification), ("ran", "done", True, False))
        self.assertNotIn("also changed", done.action.result)
        self.assertEqual(world.live("tier"), "Free", "the text did change, and the check does not look at texts: what the plan said")

    def test_a_property_that_azure_changes_besides_the_number_is_said_and_the_request_is_done_with_a_difference_and_never_verified(self):
        world = Real()
        world.arm.also = {"retentionDays": 99}
        plan = world.plan()
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"))
        self.assertIn("Azure also changed: properties.retentionDays.", done.action.result)
        self.assertEqual((done.action.verification["differences"], done.action.verification["compared"]), ("properties.retentionDays", True))
        kept, case = world.store.plan_get(plan.plan_id), world.store.case_get(plan.case_id)
        b = shown(world, kept, done.action)
        self.assertEqual((b.outcome.title, b.outcome.result), ("Done, with a difference", "Done, with a difference"))
        self.assertTrue(any("Azure also changed: properties.retentionDays." in line for line in b.outcome.lines), b.outcome.lines)
        self.assertEqual(letters.done_letter(kept, done.action, case, PERSON, BASE, NOW, CONTACTS).subject, "[Meternaut] " + letters.DIFFERENT_SUBJECT)
        result = cards.result_card(b, cards.CardContext(page_url=f"{BASE}/ok/{b.plan_id}", contacts=CONTACTS))
        self.assertEqual(by_id(result)["outcome"]["text"], "Done, with a difference")
        world.costs.totals = {RID.lower(): 30.0}
        world.clock.advance(days=5)
        tick(world.timer)
        self.assertEqual(world.store.action_get(plan.plan_id).verification["costAfterUsd"], 30.0, "the cost lines were read and they show the saving")
        self.assertEqual(world.store.action_get(plan.plan_id).state, "done", "the cost lines confirm the saving, and a change that also changed something else is still no 'done and checked'")
        clean = Real()
        plan = clean.plan()
        done = clean.run(plan)
        self.assertEqual((done.action.verification["compared"], "differences" in done.action.verification, "also changed" in done.action.result), (True, False, False))
        self.assertEqual(shown(clean, clean.store.plan_get(plan.plan_id), done.action).outcome.title, "Done")
        clean.costs.totals = {RID.lower(): 30.0}
        clean.clock.advance(days=5)
        tick(clean.timer)
        self.assertEqual(clean.store.action_get(plan.plan_id).state, "verified", "the control: with nothing else changed the same cost lines verify it")

    def test_what_was_sent_is_kept_for_the_timer_and_the_comparison_is_made_when_azure_finishes_later(self):
        world = Real()
        world.arm.also = {"retentionDays": 99}
        world.arm.operation_polls = ["InProgress"]
        world.arm.reads_before_effect = 50
        plan = world.plan()
        done = world.run(plan)
        self.assertEqual(done.action.state, "running")
        self.assertIn("kept", done.action.operation, "the check that comes later has what was sent to compare with")
        self.assertLess(len(json.dumps(done.action.operation)), 4000)
        world.arm.effects[RID.lower()].reads = 0
        tick(world.timer)
        action = world.store.action_get(plan.plan_id)
        self.assertEqual((action.state, action.verification["differences"]), ("done", "properties.retentionDays"))
        self.assertIn("Azure also changed: properties.retentionDays", action.result)

    def test_a_check_that_has_nothing_to_compare_with_says_so_and_is_still_done(self):
        world = Real()
        plan = world.plan()
        world.arm.get(RID)["properties"]["capacityUnits"] = 2
        verdict = registry.get(SETTING).verify(Env(world.reader, world.settings.gates, world.store.do_not_touch, world.clock), plan)
        self.assertEqual((verdict.state, verdict.evidence["compared"]), ("done", False))
        self.assertTrue(verdict.text.endswith("Meternaut could not compare the other numbers and flags with what it sent."), verdict.text)
        clean = Real()
        plan = clean.plan()
        done = clean.run(plan)
        clean.store.action_put(replace(done.action, verification={**done.action.verification, "compared": False}))
        page = console_of(clean, plan, clean.store.case_get(plan.case_id)).get(f"/ok/{plan.plan_id}").main.text()
        self.assertIn("Meternaut could not compare the other numbers and flags with what it sent.", page, "the page of the request says the same, in the same words")
        self.assertNotIn("other properties", page)

    def test_only_numbers_and_booleans_are_kept_and_compared_so_a_rewritten_text_is_no_difference_and_a_changed_number_or_flag_is(self):
        body = {"location": "x", "tags": {"team": "blue"}, "sku": {"name": "Lite", "capacity": 1},
                "properties": {"capacityUnits": 2, "autoScale": False, "label": "front", "created": "2026-11-01T10:00:00Z", "list": [1, 2], "items": [{"port": 80, "name": "a"}, {"port": 443, "name": "b"}]}}
        kept = kept_of(body)
        self.assertEqual(set(kept["hashes"]), {"sku.capacity", "properties.capacityUnits", "properties.autoScale", "properties.list", "properties.items"}, "no text of the reading is kept, not even as a hash")
        same = json.loads(json.dumps(body))
        added = {**same, "id": "i", "etag": "e", "systemData": {"a": 1}, "properties": {**same["properties"], "added": 5, "provisioningState": "Succeeded"}}
        self.assertEqual(differences(added, kept), [])
        rewritten = {**same, "location": "y", "tags": {"team": "red"}, "properties": {**same["properties"], "created": "2026-11-20T21:55:00.1234567Z", "label": "back"}}
        self.assertEqual(differences(rewritten, kept), [], "a timestamp or a text that Azure rewrites is no difference")
        self.assertEqual(differences({**same, "sku": {"name": "Lite", "capacity": 2}}, kept), ["sku.capacity"], "a changed number is")
        self.assertEqual(differences({**same, "properties": {**same["properties"], "autoScale": True}}, kept), ["properties.autoScale"], "a changed boolean is")
        self.assertEqual(differences({**same, "properties": {**same["properties"], "capacityUnits": 2.0}}, kept), [], "2 and 2.0 are one number")
        self.assertEqual(differences({**same, "properties": {**same["properties"], "capacityUnits": True}}, kept), ["properties.capacityUnits"], "a flag is no number")
        self.assertEqual(differences({**same, "properties": {**same["properties"], "capacityUnits": "2"}}, kept), ["properties.capacityUnits"], "a number that became a text is no number any more")
        self.assertEqual(differences({**same, "properties": {k: v for k, v in same["properties"].items() if k != "capacityUnits"}}, kept), ["properties.capacityUnits"], "a number that is gone is")
        self.assertIsNone(differences(same, None))
        self.assertIsNone(differences(same, {"depth": 99, "hashes": {}}))

    def test_a_list_that_azure_reorders_is_no_difference_and_a_changed_item_is(self):
        body = {"properties": {"list": [3, 1, 2], "flags": [True, False], "items": [{"port": 80, "name": "a"}, {"port": 443, "name": "b"}]}}
        kept = kept_of(body)
        reordered = {"properties": {"list": [2, 3, 1], "flags": [False, True], "items": [{"port": 443, "name": "b"}, {"port": 80, "name": "a"}]}}
        self.assertEqual(differences(reordered, kept), [], "the same numbers, flags and items in another order")
        self.assertEqual(differences({"properties": {**reordered["properties"], "list": [2, 3, 4]}}, kept), ["properties.list"], "a changed item is a difference")
        self.assertEqual(differences({"properties": {**reordered["properties"], "list": [2, 3]}}, kept), ["properties.list"], "and so is a missing one")
        self.assertEqual(differences({"properties": {**reordered["properties"], "items": [{"port": 443, "name": "b"}, {"port": 81, "name": "a"}]}}, kept), ["properties.items"])
        self.assertEqual(differences({"properties": {**reordered["properties"], "flags": [True, True]}}, kept), ["properties.flags"])

    def test_what_is_kept_of_a_large_body_is_small_and_still_compares(self):
        big = {"properties": {f"k{n}": {"a": n, "b": [n]} for n in range(400)}}
        kept = kept_of(big)
        self.assertLessEqual(len(kept["hashes"]), setting_module.KEPT_MOST)
        self.assertLess(kept["depth"], setting_module.KEPT_DEPTH)
        self.assertLess(len(json.dumps(kept)), 8000)
        self.assertEqual(differences(big, kept), [])
        self.assertEqual(differences({"properties": {**big["properties"], "k7": {"a": 8, "b": [7]}}}, kept), ["properties"], "below the depth that is kept a change is one change of the part that holds it")
        long = {"properties": {f"{'k' * 100}{n}": n for n in range(100)}}
        kept = kept_of(long)
        self.assertEqual(kept["depth"], 1, "a hundred long names are more bytes than a record of an action should carry")
        self.assertLessEqual(len(json.dumps(kept)), setting_module.KEPT_BYTES)
        self.assertEqual(kept_of({f"{'k' * 9000}": 1}), {}, "when even the first level is too large nothing is kept, and the check says that it could not compare")

    def test_a_number_that_is_neither_the_old_one_nor_the_new_one_when_azure_is_done_is_a_failure_in_plain_words(self):
        world = Real()
        plan = world.plan()
        env = Env(world.reader, world.settings.gates, world.store.do_not_touch, world.clock)
        world.arm.get(RID)["properties"]["capacityUnits"] = 3
        verdict = registry.get(SETTING).verify(env, plan)
        self.assertEqual((verdict.state, verdict.text), ("failed", "Azure shows capacity units at 3, which is neither the old value 4 nor the new value 2."))
        world.arm.get(RID)["properties"]["provisioningState"] = "Updating"
        self.assertEqual(registry.get(SETTING).verify(env, plan).state, "pending", "while Azure is still at it a number in between is no end")
        world = Real()
        world.arm.also = {"capacityUnits": 3}
        plan = world.plan()
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"))
        self.assertIn("neither the old value 4 nor the new value 2", done.action.result)

    def test_with_no_state_shown_a_third_number_stays_pending_and_the_timer_reads_it_again_until_azure_shows_the_new_one(self):
        world = Real()
        plan = world.plan()
        env = Env(world.reader, world.settings.gates, world.store.do_not_touch, world.clock)
        world.arm.get(RID)["properties"].pop("provisioningState")
        world.arm.get(RID)["properties"]["capacityUnits"] = 3
        verdict = registry.get(SETTING).verify(env, plan)
        self.assertEqual((verdict.state, verdict.text), ("pending", "Azure does not show the new numbers as made yet."), "no state is shown: Azure may still be at it, and the number may yet be the new one")
        world.arm.get(RID)["properties"]["provisioningState"] = "Succeeded"
        self.assertEqual(registry.get(SETTING).verify(env, plan).state, "failed", "the control: with a state that says it is done the same number is a failure")
        world = Real()

        def settled(found):
            found["properties"].pop("provisioningState", None)
            found["properties"]["capacityUnits"] = 3
            return found
        world.arm.settled = settled
        plan = world.plan()
        done = world.run(plan)
        self.assertEqual(done.action.state, "running", done.action.result)
        tick(world.timer)
        self.assertEqual(world.store.action_get(plan.plan_id).state, "running", "the timer reads it again and it is still not the new number: it is not failed")
        world.arm.get(RID)["properties"]["capacityUnits"] = 2
        tick(world.timer)
        self.assertEqual(world.store.action_get(plan.plan_id).state, "done", "and when Azure shows the new number the timer ends it")


class TheBodyKeepsWhatIsNotAzuresOwn(unittest.TestCase):
    def test_only_the_root_keys_and_the_provisioning_state_of_the_root_properties_are_left_out_and_everything_deeper_is_sent_as_it_was_read(self):
        resource = gateway(tags={"name": "front", "ETag": "mine", "provisioningState": "mine", "team": "blue"})
        resource["properties"]["settings"] = {"etag": "free", "provisioningState": "free", "other": 1}
        resource["properties"]["headers"] = {"Name": "x-name", "ETag": "e-1"}
        resource["properties"]["extra"] = {"properties": {"etag": "inner", "provisioningState": "inner"}, "name": "n", "etag": "e-2", "systemData": {"by": "free"}}
        resource["properties"]["ipConfigurations"][0]["etag"] = 'W/"x"'
        resource["properties"]["ipConfigurations"][0]["systemData"] = {"createdBy": "somebody"}
        resource["provisioningState"] = "Succeeded"
        body = put_body(resource, [("capacityUnits", 4, 2)])
        self.assertEqual(body["tags"], {"name": "front", "ETag": "mine", "provisioningState": "mine", "team": "blue"}, "a tag is a value like any other, whatever its name")
        self.assertEqual(body["properties"]["settings"], {"etag": "free", "provisioningState": "free", "other": 1})
        self.assertEqual(body["properties"]["headers"], {"Name": "x-name", "ETag": "e-1"}, "a map of headers with a Name and an ETag is no part of the resource")
        self.assertEqual(body["properties"]["extra"], {"properties": {"etag": "inner", "provisioningState": "inner"}, "name": "n", "etag": "e-2", "systemData": {"by": "free"}},
                         "a map under a key called properties, with a name and an etag, is sent whole")
        child = body["properties"]["ipConfigurations"][0]
        self.assertEqual((child["etag"], child["properties"]["provisioningState"], child["systemData"]), ('W/"x"', "Succeeded", {"createdBy": "somebody"}),
                         "a part of the resource is sent back as it was read, with its etag, its state and its systemData, as az resource update does")
        self.assertEqual(body["provisioningState"], "Succeeded", "Azure puts the state in properties: one that is at the root is a value like any other and stays")
        self.assertNotIn("provisioningState", body["properties"])
        for key in ("id", "name", "type", "systemData", "etag"):
            self.assertNotIn(key, body)

    def test_the_keys_of_the_root_are_found_in_any_case_and_nothing_else_is_taken_out(self):
        stripped = setting_module._strip({"ETag": "x", "Id": "y", "NAME": "n", "Type": "t", "SystemData": {"a": 1}, "Properties": {"ProvisioningState": "Succeeded", "a": 1, "etag": "kept"}, "Tags": {"etag": "t"}})
        self.assertEqual(stripped, {"Properties": {"a": 1, "etag": "kept"}, "Tags": {"etag": "t"}})

    def test_the_provisioning_state_is_found_in_any_case_under_properties_and_at_the_root_and_the_busy_guard_fires(self):
        for resource, wanted in (({"properties": {"provisioningState": "Updating"}}, "updating"), ({"properties": {"PROVISIONINGSTATE": "Updating"}}, "updating"),
                                 ({"provisioningstate": "Failed"}, "failed"), ({"properties": {"provisioningState": "Succeeded"}, "provisioningState": "Updating"}, "updating"),
                                 ({"properties": {}}, ""), ({"properties": {"provisioningState": "Succeeded"}}, "succeeded"), ({"properties": {"provisioningState": " "}}, "")):
            self.assertEqual(provisioning_of(resource), wanted, resource)
        for spelled in ({"properties": {"ProvisioningState": "Updating"}}, {"provisioningState": "Updating"}):
            world = Real()
            world.arm.get(RID)["properties"].pop("provisioningState")
            for key, value in spelled.items():
                (world.arm.get(RID)["properties"] if key == "properties" else world.arm.get(RID)).update(value if key == "properties" else {key: value})
            plan = world.plan_for()
            self.assertEqual((plan.family, plan.preconditions[proposals.CANNOT_KEY]), ("advise", "busy"), spelled)


class TheWriteIsMadeOnlyOnWhatWasRead(unittest.TestCase):
    def sent(self, world):
        return [header["If-Match"] for header in world.arm.headers if "If-Match" in header]

    def test_the_put_carries_the_etag_of_the_last_reading_the_header_first_and_else_the_one_of_the_body(self):
        world = Real()
        world.run(world.plan())
        self.assertEqual(self.sent(world), ['W/"11111111-2222-3333-4444-555555555555"'])
        world = Real()
        world.arm.etag_header = '"from-the-header"'
        world.run(world.plan())
        self.assertEqual(self.sent(world), ['"from-the-header"'])

    def test_a_resource_that_changed_after_the_last_reading_or_is_gone_is_refused_with_a_412_in_plain_words_and_the_put_is_tried_once(self):
        for what in ("changed", "gone"):
            with self.subTest(what):
                world = Real()
                plan = world.plan()
                world.approve(plan)
                gets = []

                def hold_after(method, key):
                    if method == "GET" and key == RID.lower():
                        gets.append(key)
                        if len(gets) == 2:  # the first reading is the check and the second is the one that the body is made from: somebody acts right after it
                            if what == "changed":
                                world.arm.get(RID)["etag"] = 'W/"somebody-else"'
                            else:
                                del world.arm.resources[RID.lower()]
                world.arm.hold_after = hold_after
                done = execute(world.services(plan), world.store.action_get(plan.plan_id), approved_digest=plan.digest)
                self.assertEqual(done.kind, "stopped", done.action.result)
                self.assertEqual(done.action.result, "Meternaut did not change the gateway: the gateway changed while Meternaut was about to change it. Nothing was changed.")
                self.assertEqual((world.arm.puts, len(world.arm.writes_of("PUT"))), ([], 1), "one try, which Azure refused, and no other")
                self.assertEqual(world.store.plan_get(plan.plan_id).state, "open", "open again: a person approves it again, and it is read again")

    def test_a_resource_that_shows_no_etag_is_written_with_no_header(self):
        world = Real()
        world.arm.get(RID).pop("etag")
        done = world.run(world.plan())
        self.assertEqual((done.kind, self.sent(world)), ("ran", []))

    def test_an_etag_that_the_body_shows_bare_is_quoted_and_one_that_is_not_an_etag_is_not_sent(self):
        world = Real()
        world.arm.get(RID)["etag"] = "0x8DB-bare-1"
        self.assertEqual(world.run(world.plan()).kind, "ran")
        self.assertEqual(self.sent(world), ['"0x8DB-bare-1"'])
        for hostile in ('"a"\r\nX-Evil: yes', 'has space', '"' + "x" * 300 + '"', 7):
            with self.subTest(ascii(hostile)):
                world = Real()
                world.arm.get(RID)["etag"] = hostile
                self.assertEqual(world.run(world.plan()).kind, "ran")
                self.assertEqual(self.sent(world), [], "nothing that is not an entity tag goes into a header")


class WhenThePutFails(unittest.TestCase):
    def test_each_failure_of_the_put_is_recorded_in_plain_words_and_the_put_is_made_once(self):
        wanted = {403: ("azure_refused", "Azure refused to change the resource"), 404: ("failed", "The change was refused or failed"), 409: ("failed", "The change was refused or failed"),
                  429: ("failed", "The change was refused or failed"), 500: ("failed", "The change was refused or failed"), 503: ("failed", "The change was refused or failed")}
        for status, (kind, text) in wanted.items():
            with self.subTest(status):
                world = Real()
                plan = world.plan()
                world.arm.write_answers = [(status, {}, b'{"error":{"code":"Conflict","message":"no"}}')]
                done = world.run(plan)
                self.assertEqual((done.kind, done.action.state), (kind, "failed"))
                self.assertIn(text, done.action.result)
                self.assertEqual((len(world.arm.writes_of("PUT")), world.arm.puts, world.live()), (1, [], 4), "one try, nothing stored, the number as it was")
                self.assertEqual(world.store.plan_get(plan.plan_id).state, "failed")
                tick(world.timer)
                self.assertEqual(len(world.arm.writes_of("PUT")), 1, "nothing makes a second try")

    def test_a_claims_challenge_asks_for_the_check_once_and_the_one_write_that_follows_it_is_the_only_one_that_is_stored(self):
        world = Real()
        plan = world.plan()
        world.arm.write_answers = [(401, challenge(), b'{"error":{"code":"InsufficientClaims","message":"a check is needed"}}')]
        first = world.run(plan)
        self.assertEqual((first.kind, first.action.state), ("step_up", "queued"))
        self.assertEqual((world.store.plan_get(plan.plan_id).state, world.arm.puts, len(world.arm.writes_of("PUT"))), ("approved", [], 1), "nothing was written and the plan waits for the check")
        again = execute(world.services(plan), world.store.action_get(plan.plan_id), approved_digest=plan.digest)
        self.assertEqual((again.kind, again.action.state), ("ran", "done"))
        self.assertEqual((len(world.arm.puts), len(world.arm.writes_of("PUT")), world.live()), (1, 2, 2), "two requests were sent, and Azure carried out one")

    def test_a_timeout_after_the_request_was_sent_is_not_known_and_nothing_writes_again(self):
        world = Real()
        world.arm.timeout_put = True
        plan = world.plan()
        done = world.run(plan)
        self.assertEqual(done.action.state, "unknown", done.action.result)
        self.assertIn("Check the resource before anything is tried again", done.action.result)
        tick(world.timer)
        world.clock.advance(minutes=30)
        tick(world.timer)
        self.assertEqual(len(world.arm.writes_of("PUT")), 1)

    def test_a_plan_that_was_changed_after_the_approval_is_refused_and_nothing_is_written(self):
        world = Real()
        plan = world.plan()
        action = world.approve(plan)
        self.assertEqual(world.store.action_get(plan.plan_id).plan_digest, plan.digest)
        world.store.plan_put(replace(world.store.plan_get(plan.plan_id), target={**plan.target, "set": [{"path": "capacityUnits", "from": 4, "to": 1}]}))
        done = execute(world.services(plan), action, approved_digest=plan.digest)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"))
        self.assertEqual(world.arm.writes(), [])
        self.assertIsNotNone(plan_digest.problem(world.store.plan_get(plan.plan_id), plan.digest))


class TheUndoIsExact(unittest.TestCase):
    def target(self, *settings):
        return {"set": [{"path": path, "from": old, "to": new} for path, old, new in settings], "apiVersion": API}

    def test_the_command_takes_the_raw_numbers_and_puts_a_path_at_the_root_by_one_test(self):
        said = words.setting_words("gateway", "gw-one", "rg", self.target(("unitCount", 1440, 720), ("scaleUnits", 0.125, 0.0625), ("skuCount", 8, 4)), {})
        self.assertIn("--set properties.unitCount=1440 properties.scaleUnits=0.125 properties.skuCount=8 --api-version 2024-05-01", said.undo)
        self.assertIn("Set unit count to 1440, scale units to 0.125 and sku count to 8 again:", said.undo)
        for rounded in ("1,440", "0.12 ", "0.12,"):
            self.assertNotIn(rounded, said.undo)
        self.assertIn("--set sku.capacity=2 ", words.setting_words("gateway", "gw-one", "rg", self.target(("sku.capacity", 2, 1)), {}).undo)
        for path, root in (("sku.capacity", True), ("SKU.Capacity", True), ("skuCount", False), ("skuname.x", False), ("capacityUnits", False), ("properties.x", False)):
            self.assertEqual(words.at_root(path), root, path)

    def test_the_finder_of_a_path_and_the_command_agree_on_where_it_is(self):
        resource = gateway()
        resource["properties"]["skuCount"] = 8
        for path in ("skuCount", "sku.capacity", "capacityUnits"):
            parent, _, _ = setting_module.find(resource, path)
            command = words.setting_words("gateway", "g", "rg", self.target((path, 1, 0)), {}).undo
            self.assertIn(f"--set {'' if parent is resource['sku'] else 'properties.'}{path}=1 ", command, path)
        body = put_body(resource, [("skuCount", 8, 4)])
        self.assertEqual((body["properties"]["skuCount"], body["sku"]), (4, {"name": "Lite", "capacity": 2}), "skuCount is under properties and sku is untouched")

    def test_a_card_and_a_letter_say_the_first_sentence_of_the_undo_and_never_cut_a_command_while_the_page_says_it_whole(self):
        world = Real()
        world.arm.get(RID)["properties"]["replicaCount"] = 3
        three = {proposals.KEY: {"set": [{"path": "capacityUnits", "from": 4, "to": 2}, {"path": "sku.capacity", "from": 2, "to": 1}, {"path": "replicaCount", "from": 3, "to": 2}]}}
        plan = world.plan(facts=three)
        self.assertGreater(len(plan.undo), 300)
        command = "az resource update --ids <resource id> --set properties.capacityUnits=4 sku.capacity=2 properties.replicaCount=3 --api-version 2024-05-01"
        short = "Set the numbers back to what they were in the Azure portal. It does not bring back what the lower number cut off meanwhile. The page has the command."
        b = shown(world, plan)
        self.assertEqual((b.undo.short, command in b.undo.how), (short, True))
        self.assertLessEqual(len(b.undo.short), 150, "it fits a line of a letter (160 characters) and a card (200) whole")
        self.assertEqual(by_id(card_of(b))["undo"]["text"], f"**Undo:** {short}")
        case = world.store.case_get(plan.case_id)
        letter = letters.approval_letter(plan, case, PERSON, BASE, NOW, CONTACTS)
        self.assertIn(short, letter.text)
        self.assertNotIn("az resource", letter.text)
        self.assertIn(command, console_of(world, plan, case).get(f"/ok/{plan.plan_id}").facts()["Undo"])
        done = world.run(plan)
        self.assertEqual(done.kind, "ran", done.action.result)
        after = letters.done_letter(world.store.plan_get(plan.plan_id), done.action, case, PERSON, BASE, NOW, CONTACTS)
        self.assertIn(short, after.text)
        self.assertNotIn("az resource", after.text)
        wordy = self.target(*((f"{'a' * 40}{word}Units", 1, 0) for word in ("One", "Two", "Three")))
        self.assertEqual(words.setting_words("gateway", "g", "rg", wordy, {}).short_undo, short)

    def test_the_short_undo_of_a_card_and_a_letter_says_that_setting_it_back_does_not_bring_back_what_was_cut_off_and_stays_whole_in_each(self):
        caveat = "It does not bring back what the lower number cut off meanwhile."
        world = Real()
        plan = world.plan()
        b = shown(world, plan)
        short = f"Set capacity units to 4 again in the Azure portal. {caveat} The page has the command."
        self.assertEqual(b.undo.short, short, "one setting: its own first sentence, then the caveat, then where the command is")
        self.assertEqual(by_id(card_of(b))["undo"]["text"], f"**Undo:** {short}")
        case = world.store.case_get(plan.case_id)
        letter = letters.approval_letter(plan, case, PERSON, BASE, NOW, CONTACTS)
        self.assertIn(f"Undo: {short}", letter.text, "the chip of the letter, which holds 160 characters")
        for settings in ((("capacityUnits", 4, 2),), (("capacityUnits", 4, 2), ("scaleUnits", 8, 4)), tuple((f"{'a' * 40}{n}Units", 1, 0) for n in ("One", "Two", "Three"))):
            said = words.setting_words("gateway", "g", "rg", {"set": [{"path": p, "from": a, "to": b_} for p, a, b_ in settings], "apiVersion": API}, {}).short_undo
            self.assertTrue(said.endswith(f"{caveat} The page has the command."), said)
            self.assertLessEqual(len(said), 150, said)
        self.assertIn("Setting it back does not bring back what the lower number cut off meanwhile.", plan.undo, "the page says it in its own sentence")


class TheCountGate(unittest.TestCase):
    def test_only_what_proposals_countlike_accepts_is_lowered_with_no_rule_of_the_family_of_its_own(self):
        for path in ("scaleUnits", "sku.capacity", "instanceCount", "maxReplicas", "capacityUnits", "numberOfNodes", "replicaCount"):
            self.assertTrue(setting_module._countlike(path), path)
        for path in ("retentionDays", "minimumTlsVersion", "zonesCount", "numberOfRetentionDays", "tier", "label", "autoScaleEnabled", "accessMode", "sizeLimit", "\u0131nstanceCount", "instanceCount\u200b", ""):
            self.assertFalse(setting_module._countlike(path), path)
        for path in ("scaleUnits", "zonesCount", "retentionDays", "numberOfHoursWorkers", "\u0131nstanceCount"):
            self.assertEqual(setting_module._countlike(path), proposals.countlike(path), path)
        for answer in (True, False):
            with mock.patch.object(proposals, "countlike", return_value=answer) as asked:
                self.assertIs(setting_module._countlike("whatever"), answer)
                asked.assert_called_once_with("whatever")
        with mock.patch.object(proposals, "countlike", return_value=False):
            with self.assertRaises(setting_module.Cannot) as raised:
                setting_module.aims_of(proposals.settings({proposals.KEY: {"set": [{"path": "capacityUnits", "from": 4, "to": 2}]}}))
            self.assertEqual(raised.exception.key, "not-a-count")
        with mock.patch.object(proposals, "countlike", return_value=True):
            self.assertEqual(setting_module.aims_of(proposals.settings({proposals.KEY: {"set": [{"path": "retentionDays", "from": 30, "to": 7}]}})), [("retentionDays", 30, 7)])

    def test_a_count_that_the_proposals_accept_is_planned_as_a_change_and_one_that_they_refuse_is_advice_with_its_own_words_before_any_read(self):
        for name in ("scaleUnits", "instanceCount", "maxReplicas"):
            with self.subTest(accepted=name):
                world = Real()
                world.arm.get(RID)["properties"][name] = 4
                plan = world.plan_for(facts={proposals.KEY: {"set": [{"path": name, "from": 4, "to": 2}]}})
                self.assertEqual((plan.family, proposals.CANNOT_KEY in plan.preconditions), (SETTING, False))
        refused = (("retentionDays", 30, 7, "not-a-count"), ("minimumTlsVersion", 12, 10, "not-a-count"), ("zonesCount", 3, 1, "not-a-count"), ("numberOfRetentionDays", 30, 7, "not-a-count"),
                   ("\u0131nstanceCount", 4, 2, "unsupported"))
        for name, now, to, key in refused:
            with self.subTest(refused=name):
                world = Real()
                plan = world.plan_for(facts={proposals.KEY: {"set": [{"path": name, "from": now, "to": to}]}})
                self.assertEqual((plan.family, plan.preconditions[proposals.CANNOT_KEY]), ("advise", key))
                self.assertEqual(world.arm.calls, [], "nothing is read for a setting that Meternaut would not lower")

    def test_a_key_that_decides_how_much_is_kept_is_refused_with_its_own_reason_and_a_count_or_a_size_is_still_accepted(self):
        kept = ("retentionCount", "retentionSizeGB", "numberOfDaysToKeep", "keepCount", "backupCount", "snapshotCount", "backup.count", "numberOfBackups", "properties.retention.maxCount",
                "keepcount", "backupcount", "BACKUPCOUNT", "ttlcount", "retentionpolicy.count", "numberOfSnapShots", "maxHistoryCount", "maxVersionCount", "restorePointCount", "archiveCount", "purgeCount",
                "maxThrottleCount")  # the last holds ttl inside another word: a name that merely contains one of the words is refused too
        self.assertEqual(proposals.KEPT_WORDS, ("retention", "retain", "retained", "keep", "kept", "ttl", "backup", "snapshot", "history", "version", "restore", "archive", "purge"))
        for path in (*kept, "ttl", "ttlSeconds"):
            with self.subTest(path):
                self.assertFalse(proposals.countlike(path), path)
                self.assertFalse(setting_module._countlike(path), path)
        for path in kept:
            self.assertEqual(proposals._refusal(path), "kept", path)
        for path in ("scaleUnits", "sku.capacity", "instanceCount", "maxReplicas", "numberOfWorkers", "dailyQuotaGb", "diskSizeGB"):
            self.assertTrue(proposals.countlike(path), path)
        self.assertEqual(proposals.WHY["set"]["kept"], "a setting that decides how much is kept, which a lower number deletes")
        self.assertEqual(proposals._setting({"handle": "r1", "property": "retentionCount", "from": 30, "to": 7}, ["r1"], {"r1": {"properties": {"retentionCount": 30}}}, {}), "kept",
                         "the AI side drops it by that rule")
        for path in ("retentionCount", "keepCount", "backupCount", "keepcount", "maxHistoryCount", "BACKUPCOUNT"):
            plan = Real().plan_for(facts={proposals.KEY: {"set": [{"path": path, "from": 30, "to": 7}]}})
            self.assertEqual((plan.family, plan.preconditions[proposals.CANNOT_KEY]), ("advise", "not-a-count"), path)

    def test_a_setting_that_is_not_a_count_is_refused_at_the_plan_with_its_own_words_before_any_read(self):
        world = Real()
        plan = world.plan_for(facts={proposals.KEY: {"set": [{"path": "retentionDays", "from": 30, "to": 7}]}})
        self.assertEqual((plan.family, plan.preconditions[proposals.CANNOT_KEY]), ("advise", "not-a-count"))
        self.assertEqual(proposals.cannot(plan.preconditions), "Meternaut only lowers a count of units, and this setting is not one.")
        self.assertEqual(world.arm.calls, [], "nothing is read for a setting that Meternaut would not lower")
        mixed = Real().plan_for(facts={proposals.KEY: {"set": [{"path": "capacityUnits", "from": 4, "to": 2}, {"path": "retentionDays", "from": 30, "to": 7}]}})
        self.assertEqual(mixed.preconditions[proposals.CANNOT_KEY], "not-a-count", "one setting that is not a count is enough")

    def test_a_plan_that_names_one_is_refused_again_right_before_the_write_by_the_look_and_by_the_runner(self):
        world = Real()
        good = world.plan()
        for name in ("retentionDays", "zonesCount", "numberOfRetentionDays", "minimumTlsVersion"):
            with self.subTest(name):
                old = replace(plan_digest.sealed(replace(good, target={**good.target, "set": [{"path": name, "from": 30, "to": 7}]})), code=good.code)
                with self.assertRaises(Stop) as raised:
                    registry.get(SETTING).recheck(Env(world.reader, world.settings.gates, world.store.do_not_touch, world.clock), old)
                self.assertEqual(str(raised.exception), "a number of the request is not a count of units, which is all that Meternaut lowers")
        old = replace(plan_digest.sealed(replace(good, target={**good.target, "set": [{"path": "retentionDays", "from": 30, "to": 7}]})), code=good.code)
        world.store.plan_put(old)
        done = execute(world.services(old), world.approve(old), approved_digest=old.digest)
        self.assertEqual(done.kind, "stopped")
        self.assertEqual(done.action.result, "Meternaut did not change the gateway: a number of the request is not a count of units, which is all that Meternaut lowers. Nothing was changed.")
        self.assertEqual(world.arm.writes(), [])

    def test_the_undo_says_that_setting_the_number_back_does_not_bring_back_what_was_cut_off(self):
        self.assertTrue(Real().plan().undo.endswith("Setting it back does not bring back what the lower number cut off meanwhile."))


class TheRealChangeAsksOnceMore(unittest.TestCase):
    def made(self):
        world = Real()
        plan = world.plan()
        return world, plan, world.store.case_get(plan.case_id)

    def test_the_brief_of_a_real_change_asks_once_more_although_it_can_be_undone_and_no_old_family_does(self):
        world, plan, _ = self.made()
        b = shown(world, plan)
        self.assertEqual((b.confirm, b.undo.reversible), (True, True))
        old = fs.World()
        done = old.plan(old.arm.add(fs.disk()), "disk", "delete", cost=20.0)
        before = brief_mod.build_brief(old.store.case_get(done.case_id), done, now=NOW, may_answer=True)
        self.assertEqual((before.confirm, before.undo.short), (False, ""))
        for name in ("stop-vm", "resize-vm", "change-disk-tier", "scale-vpn-gateway"):
            self.assertFalse(words.words_of(name, None, "", "x", "g").confirm, name)

    def test_approving_asks_on_a_page_of_its_own_with_words_that_are_true_and_starts_no_sign_in(self):
        world, plan, case = self.made()
        console = console_of(world, plan, case)
        form = console.get(f"/ok/{plan.plan_id}").form(f"/ok/{plan.plan_id}", has_button="Approve")
        reply = console.submit(form, "Approve", confirm=False, note="Go on")
        self.assertEqual(reply.status, 200)
        self.assertTrue(reply.headings(1)[0].startswith("Confirm: Scale down the gateway gw-one in resource group rg-owner-real"), reply.headings(1))
        text = reply.main.text()
        self.assertIn("This changes a real resource. Nothing is changed until you confirm here.", text)
        self.assertEqual([p.text() for p in reply.main.find_all("p", class_="notice-title")], ["This changes a real resource"])
        self.assertIn("Meternaut does not know what a lower number takes away", reply.main.find("div", class_="notice warning").text())
        self.assertNotIn("cannot be undone", text)
        self.assertEqual((console.delegate.begins, console.delegate.finishes), ([], []))
        self.assertEqual(world.store.decisions_of_plan(plan.plan_id), [])
        (back,) = [a for a in reply.main.find_all("a") if a.text() == "No, go back"]
        self.assertEqual(back.attrs["href"], f"/ok/{plan.plan_id}")
        second = reply.form(f"/ok/{plan.plan_id}", has_button="Yes, change it")
        self.assertEqual(second.fields["confirm"], "yes")
        sent = console.submit(second, "Yes, change it", confirm=False)
        self.assertEqual(sent.status, 303)
        self.assertEqual(len(console.delegate.begins), 1)

    def test_the_card_asks_twice_and_says_that_a_real_resource_changes(self):
        world, plan, _ = self.made()
        b = shown(world, plan)
        card = card_of(b)
        self.assertEqual(cardcheck.check(card), [])
        ids = by_id(card)
        approve, decline, _ = ids["decisions"]["actions"]
        self.assertEqual((approve["type"], approve["title"], approve["tooltip"]), ("Action.ToggleVisibility", "Approve", "Asks once more: this changes a real resource."))
        self.assertNotIn("url", approve)
        self.assertEqual(decline["type"], "Action.OpenUrl")
        where = f"{b.where.kind} {b.where.name} in resource group {b.where.group}"
        self.assertEqual(ids["sure-text"]["text"], f"This changes a real resource: {where}. Nothing is changed until you press Yes.")
        back, yes = ids["sure-actions"]["actions"]
        self.assertEqual((back["title"], yes["title"], yes["type"]), ("No, go back", "Yes, change it", "Action.OpenUrl"))

    def test_the_letter_says_what_can_be_undone_and_asks_for_the_decision_on_the_page(self):
        world, plan, case = self.made()
        letter = letters.approval_letter(plan, case, PERSON, BASE, NOW, CONTACTS)
        self.assertIn("Can be undone", letter.text)
        self.assertIn("Undo: Set capacity units to 4 again in the Azure portal. It does not bring back what the lower number cut off meanwhile. The page has the command.", letter.text)
        self.assertIn("It runs with your own permissions.", letter.text)
        self.assertIn("Review and decide: ", letter.text)

    def test_a_delete_that_cannot_be_undone_keeps_its_own_words_on_the_card_and_in_the_letter(self):
        old = fs.World()
        plan = old.plan(old.arm.add(fs.disk()), "disk", "delete", cost=20.0)
        case = old.store.case_get(plan.case_id)
        b = brief_mod.build_brief(case, plan, now=NOW, may_answer=True)
        ids = by_id(card_of(b))
        self.assertTrue(ids["sure-text"]["text"].startswith("This cannot be undone: "), ids["sure-text"]["text"])
        self.assertEqual(ids["approve"]["tooltip"], "Asks once more: this cannot be undone.")
        self.assertEqual(ids["sure-yes"]["title"], "Yes, delete it")
        letter = letters.approval_letter(plan, case, PERSON, BASE, NOW, CONTACTS)
        self.assertIn("Cannot be undone", letter.text)
        self.assertNotIn("real resource", letter.text)


class TheIdsAreAsciiOnly(unittest.TestCase):
    FOLDING = (("prod-k", "prod-\u212a"), ("rg-s", "rg-\u017f"), ("rg-i", "rg-\u0131"), ("rg-i", "rg-\u0130"), ("rg-k", "rg-\u212a"))

    def test_a_letter_that_folds_into_an_ascii_one_is_no_name_of_a_listed_group_and_no_id_is_accepted_for_it(self):
        for listed, folded in self.FOLDING:
            with self.subTest(listed, folded=ascii(folded)):
                gates = Gates((), real_scopes=(ChangeScope(REAL_SUB, listed),))
                self.assertIsNotNone(gates.real_scope_of(REAL_SUB, listed.upper()), "the ASCII spelling in any case is the listed group")
                self.assertIsNone(gates.real_scope_of(REAL_SUB, folded))
                self.assertIsNone(gates.real_scope_of(REAL_SUB.replace("d", "\uff44"), listed))
                rid = f"/subscriptions/{REAL_SUB}/resourceGroups/{folded}/providers/Microsoft.Example/gateways/gw-one"
                self.assertIsNone(calls.GENERIC_ID.fullmatch(rid))
                self.assertIsNone(calls.RESOURCE_ID.fullmatch(rid))
                self.assertIsNone(calls.located_for(rid, gates))
                self.assertIsNone(calls.one_write(rid, API, gates, lambda text: text).put_url)
                with self.assertRaises(Stop):
                    registry.get(SETTING).locate(rid, gates)
                for _, pattern in calls.real_reads(gates.real_scopes):
                    self.assertIsNone(pattern.fullmatch(f"https://management.azure.com/subscriptions/{REAL_SUB}/resourceGroups/{folded}/providers/Microsoft.Example/gateways/gw-one"))

    def test_a_name_of_a_resource_a_provider_or_a_version_that_is_not_ascii_is_refused_too(self):
        gates = Gates((), real_scopes=(REAL,))
        for rid in (f"/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Example/gateways/gw-\u017f",
                    f"/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Example/gateway\u017f/gw-one",
                    f"/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Examp\u212ae/gateways/gw-one"):
            self.assertIsNone(calls.located_for(rid, gates), ascii(rid))
        self.assertIsNone(calls.RELEASED.fullmatch("\u0662\u0660\u0662\u0664-\u0660\u0661-\u0660\u0661"), "digits of another script are no version")
        self.assertIsNone(words.API_VERSION.fullmatch("\u0662\u0660\u0662\u0664-\u0660\u0661-\u0660\u0661"))
        self.assertIsNotNone(calls.RELEASED.fullmatch("2024-05-01"))

    def test_the_old_families_are_held_by_the_same_comparison(self):
        scopes = (ChangeScope(SUB, "meternaut-k"),)
        self.assertIsNotNone(gates_module.scope_of(scopes, SUB, "METERNAUT-K"))
        self.assertIsNone(gates_module.scope_of(scopes, SUB, "meternaut-\u212a"))
        self.assertIsNone(gates_module.scope_of(scopes, SUB, None))


class TheUpgradeAsksTheSameRules(unittest.TestCase):
    def test_a_do_not_touch_mark_after_a_change_request_closes_it_as_left_alone_and_no_advice_is_made(self):
        world = Real()
        plan = world.plan()
        world.store.note_put(NoteRecord(**DO_NOT_TOUCH))
        (taken, new, case), = world.approvals.upgrade((OID,))
        self.assertEqual((taken.plan_id, new), (plan.plan_id, None))
        self.assertEqual(world.store.plan_get(plan.plan_id).preconditions["takenBack"], "left-alone")
        self.assertEqual(world.store.plans_open(), [])
        self.assertEqual(world.store.case_get(case.case_id).status, "proposed", "nobody waits for an OK on it now")
        self.assertEqual(world.approvals.upgrade((OID,)), [], "and the next Watch finds nothing to do")

    def test_a_resource_that_is_being_changed_right_now_takes_nothing_back(self):
        world = Real()
        plan = world.plan()
        world.arm.get(RID)["properties"]["provisioningState"] = "Updating"
        self.assertEqual(world.approvals.upgrade((OID,)), [])
        self.assertEqual(world.store.plan_get(plan.plan_id), plan)
        world.arm.get(RID)["properties"]["provisioningState"] = "Succeeded"
        self.assertEqual(world.approvals.upgrade((OID,)), [], "and when it is done it is as it was asked")

    def test_the_request_that_replaces_a_change_is_made_by_advise_so_its_rules_and_the_quiet_days_hold_it_back_too(self):
        world = Real()
        plan = world.plan()
        world.arm.get(RID)["properties"]["capacityUnits"] = 5
        world.store.plan_put(replace(approvals_module.build_advice(world.store.case_get(plan.case_id), (OID,), NOW, world.settings), state="declined"))
        (taken, new, _), = world.approvals.upgrade((OID,))
        self.assertEqual((taken.plan_id, new), (plan.plan_id, None), "a person said no a moment ago: the change is taken back and no advice takes its place")
        self.assertEqual(world.store.plan_get(plan.plan_id).preconditions["takenBack"], "changed")
        again = Real()
        plan = again.plan()
        again.arm.get(RID)["properties"]["capacityUnits"] = 5
        (taken, new, _), = again.approvals.upgrade((OID,))
        self.assertEqual((new.family, new.preconditions[proposals.CANNOT_KEY]), ("advise", "mismatch"), "when the rules let it through advice is made, with its reason")

    def test_the_new_request_is_announced_once_and_not_at_every_watch(self):
        from cases import upkeep
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            world = Real()
            self.assertEqual(world.plan_for().family, "advise")
        announced = []
        extras = mock.Mock(approvals=world.approvals, approvers=lambda: (OID,), store=world.store, on_plan=lambda plan, case: announced.append((plan.family, case.status)))
        history = mock.Mock(emit=lambda kind, **fields: None)
        self.assertEqual(len(upkeep.upgrade(extras, history)), 1)
        self.assertEqual(announced, [(SETTING, "awaiting_ok")])
        for _ in range(3):
            self.assertEqual(upkeep.upgrade(extras, history), [])
        self.assertEqual(len(announced), 1, "a request that holds is not announced again")

    def test_a_change_request_stays_open_when_a_later_judgment_has_no_price_and_its_wait_is_not_restarted(self):
        world = Real()
        plan = world.plan()
        self.assertEqual(plan.saving_usd_month, 201.6)
        world.store.plan_put(replace(plan, waiting_since="2026-11-03T09:00:00Z"))
        kept = world.store.plan_get(plan.plan_id)
        case = world.store.case_get(plan.case_id)
        world.store.case_put(replace(case, saving_usd_month=None))  # judged again, and nothing was priced this time
        self.assertEqual(world.approvals.asked_saving(world.store.case_get(plan.case_id)), 201.6, "the case keeps what the open change request was asked with, as the case of an advice does")
        for _ in range(2):
            self.assertEqual(world.approvals.upgrade((OID,)), [])
        self.assertEqual(world.store.plan_get(plan.plan_id), kept, "open, with the start of its wait, and with no reason of being taken back")
        self.assertNotIn("takenBack", world.store.plan_get(plan.plan_id).preconditions)
        world.store.case_put(replace(world.store.case_get(plan.case_id), saving_usd_month=201.6))  # the finding comes back with its price
        self.assertEqual(world.approvals.upgrade((OID,)), [])
        self.assertEqual([p.plan_id for p in world.store.plans_open() if p.state == "open"], [plan.plan_id], "the same request, and no new one that starts its wait again (rule 38)")

    def test_a_change_request_is_left_alone_when_the_rules_of_making_a_plan_say_no_and_no_reason_says_that_the_change_is_gone(self):
        world = Real()
        plan = world.plan()
        world.store.plan_put(approvals_module.build_advice(world.store.case_get(plan.case_id), (OID,), NOW, world.settings))  # another request is open for the resource
        self.assertEqual(world.approvals.upgrade((OID,)), [])
        self.assertEqual(world.store.plan_get(plan.plan_id).state, "open", "no reason is true here: nothing is taken back")

    def test_each_true_reason_takes_a_change_request_back_with_a_word_that_is_true_whether_or_not_a_price_is_missing(self):
        def mismatch(world, case):
            world.arm.get(RID)["properties"]["capacityUnits"] = 5

        def lock(world, case):
            world.arm.locks[RID.lower()] = [{"name": "keep"}]

        def mark(world, case):
            world.store.note_put(NoteRecord(**DO_NOT_TOUCH))

        def group_closed(world, case):
            world.regroup(())

        def not_a_count(world, case):
            world.store.case_put(replace(case, facts={proposals.KEY: {"set": [{"path": "retentionDays", "from": 30, "to": 7}]}}))

        reasons = (("mismatch", mismatch, "changed", "mismatch"), ("locked", lock, "changed", "locked"), ("do-not-touch", mark, "left-alone", None), ("outside", group_closed, "changed", "outside"),
                   ("not-a-count", not_a_count, "changed", "not-a-count"), ("switch-off", None, "changed", "switch-off"))
        for name, change, word, key in reasons:
            for priced in (True, False):
                with self.subTest(reason=name, priced=priced):
                    world = Real()
                    plan = world.plan()
                    case = world.store.case_get(plan.case_id)
                    if not priced:
                        case = replace(case, saving_usd_month=None)
                        world.store.case_put(case)
                    with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", name != "switch-off"):
                        if change is not None:
                            change(world, case)
                        (taken, new, _), = world.approvals.upgrade((OID,))
                    self.assertEqual((taken.plan_id, world.store.plan_get(plan.plan_id).state, world.store.plan_get(plan.plan_id).preconditions["takenBack"]), (plan.plan_id, "expired", word))
                    if priced and key is not None:
                        self.assertEqual((new.family, new.preconditions[proposals.CANNOT_KEY]), ("advise", key), "the request that asks instead says why")
                    else:
                        self.assertIsNone(new, "a person marked it, or nothing was priced: the rules of asking make no other request")

    def test_a_finding_judged_again_with_other_numbers_replaces_the_request_only_when_the_rules_of_asking_let_it_through(self):
        for priced in (True, False):
            with self.subTest(priced=priced):
                world = Real()
                plan = world.plan()
                case = world.store.case_get(plan.case_id)
                world.store.case_put(replace(case, saving_usd_month=201.6 if priced else None, facts={**case.facts, proposals.KEY: {"set": [{"path": "capacityUnits", "from": 4, "to": 1}]}}))
                (taken, new, _), = world.approvals.upgrade((OID,))
                self.assertEqual(world.store.plan_get(plan.plan_id).preconditions["takenBack"], "changed")
                if priced:
                    self.assertEqual((new.family, new.target["set"][0]["to"]), (SETTING, 1))
                else:
                    self.assertIsNone(new, "nothing was priced for the new numbers: no request is made for them")
                    self.assertEqual(world.store.plans_open(), [])

    def test_a_request_that_was_closed_because_of_a_do_not_touch_mark_says_request_and_the_note_of_a_held_finding_keeps_the_words_that_say_note(self):
        world = Real()
        plan = world.plan()
        world.store.note_put(NoteRecord(**DO_NOT_TOUCH))
        world.approvals.upgrade((OID,))
        closed = world.store.plan_get(plan.plan_id)
        b = shown(world, closed)
        self.assertEqual((b.outcome.title, b.outcome.lines), ("Left alone", ("Meternaut closed this request, because a person marked the resource do-not-touch.", "Nothing was changed in Azure.")))
        note = replace(closed, family="advise", preconditions={**closed.preconditions, HELD: "unchecked"})  # the note of a held finding that was closed for the same reason keeps its reason that it was held
        self.assertEqual(brief_mod.taken_back_words(note, "left-alone"), brief_mod.TAKEN_BACK["left-alone"])
        self.assertIn("closed this note", brief_mod.TAKEN_BACK["left-alone"])
        self.assertNotIn("note", brief_mod.TAKEN_BACK["left-alone-request"])
        self.assertEqual(brief_mod.taken_back_words(closed, "changed"), brief_mod.TAKEN_BACK["changed"], "every other reason keeps its one sentence")

    def test_the_history_has_a_row_for_a_request_that_was_closed_for_a_mark_in_the_words_of_a_request_and_none_for_a_note_that_was_closed_the_same_way(self):
        world = Real()
        plan = world.plan()
        world.store.note_put(NoteRecord(**DO_NOT_TOUCH))
        world.approvals.upgrade((OID,))
        closed = world.store.plan_get(plan.plan_id)
        case = world.store.case_get(plan.case_id)
        request_words = "Meternaut closed this request, because a person marked the resource do-not-touch."
        self.assertEqual(closed.preconditions["takenBack"], "left-alone")
        page = console_of(world, plan, case).get("/history").content
        self.assertIn(request_words, page, "people were asked about the request: its closing is a row, in the words of a request")
        self.assertNotIn("closed this note", page)
        world.store.plan_put(replace(closed, family="advise", preconditions={**closed.preconditions, HELD: "unchecked"}))  # the note of a held finding, closed for the same mark
        page = console_of(world, plan, case).get("/history").content
        for words in (request_words, brief_mod.TAKEN_BACK["left-alone"], "request to look at a finding"):
            self.assertNotIn(words, page, "nobody was asked about a note: it has no row")

    def test_a_closed_gate_takes_a_change_request_back_whatever_else_stops_a_plan_short_of_the_family_a_second_open_request_or_no_reader(self):
        def line_off(world, case):
            return mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False)

        def group_off(world, case):
            world.regroup(())
            return mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", True)

        def not_a_count(world, case):
            world.store.case_put(replace(case, facts={proposals.KEY: {"set": [{"path": "retentionDays", "from": 30, "to": 7}]}}))
            return mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", True)

        def mark(world, case):
            world.store.note_put(NoteRecord(**DO_NOT_TOUCH))
            return mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", True)

        gates = (("switch-off", line_off, "changed"), ("outside", group_off, "changed"), ("not-a-count", not_a_count, "changed"), ("do-not-touch", mark, "left-alone"))
        for name, close, word in gates:
            for stop in ("a second open request", "no reader"):
                with self.subTest(gate=name, stop=stop):
                    world = Real()
                    plan = world.plan()
                    case = world.store.case_get(plan.case_id)
                    patch = close(world, case)
                    other = None
                    if stop == "no reader":
                        world.approvals.reader = None
                    else:
                        other = approvals_module.build_advice(world.store.case_get(plan.case_id), (OID,), NOW, world.settings)
                        world.store.plan_put(other)
                    with patch:
                        done = world.approvals.upgrade((OID,))
                    mine = [(taken, new) for taken, new, _ in done if taken.plan_id == plan.plan_id]
                    self.assertEqual(len(mine), 1, "the closed gate takes the request back")
                    self.assertEqual((world.store.plan_get(plan.plan_id).state, world.store.plan_get(plan.plan_id).preconditions["takenBack"]), ("expired", word))
                    new = mine[0][1]
                    if stop == "a second open request" or name == "do-not-touch":
                        self.assertIsNone(new, "another request is open, or a person marked it: no other request is made")
                    else:
                        self.assertEqual((new.family, new.preconditions[proposals.CANNOT_KEY]), ("advise", name), "with nothing in the way the request that asks instead says why")
                    if other is not None:
                        self.assertEqual(world.store.plan_get(other.plan_id).state, "open", "the other request is not touched")


class EveryReasonThatAChangeCannotBeMadeHasItsKeyAndItsWords(unittest.TestCase):
    def key_of(self, plan):
        self.assertEqual((plan.family, plan.state), ("advise", "open"))
        return plan.preconditions.get(proposals.CANNOT_KEY)

    def test_every_key_of_the_table_is_made_by_a_case_here_and_says_a_whole_sentence(self):
        made = {}
        with mock.patch("cases.families.gates.REAL_CHANGES_ALLOWED", False):
            made["switch-off"] = self.key_of(Real().plan_for())
        made["outside"] = self.key_of(Real(real=()).plan_for())
        world = Real()
        world.arm.locks[RID.lower()] = [{"name": "keep"}]
        made["locked"] = self.key_of(world.plan_for())
        world = Real(real=())
        old = world.plan_for()
        world.regroup((REAL,))
        world.store.note_put(NoteRecord(**DO_NOT_TOUCH))
        world.approvals.upgrade((OID,))
        made["do-not-touch"] = self.key_of(world.store.plan_get(old.plan_id))
        world = Real()
        world.arm.read_status = 403
        made["unreadable"] = self.key_of(world.plan_for())
        world = Real()
        world.arm.get(RID)["properties"]["capacityUnits"] = 5
        made["mismatch"] = self.key_of(world.plan_for())
        world = Real()
        world.arm.get(RID)["properties"]["provisioningState"] = "Updating"
        made["busy"] = self.key_of(world.plan_for())
        made["unsupported"] = self.key_of(Real().plan_for(facts={proposals.KEY: {"set": [{"path": "capacityUnits", "from": 4, "to": 6}]}}))
        world = Real()
        world.arm.versions = ["2025-02-01-preview", "2026-01-01-preview"]
        made["no-version"] = self.key_of(world.plan_for())
        made["not-a-count"] = self.key_of(Real().plan_for(facts={proposals.KEY: {"set": [{"path": "retentionDays", "from": 30, "to": 7}]}}))
        world = Real()
        lead = lead_of(world.resource)
        made["unsettled"] = self.key_of(world.approvals.plan_for(world.case(lead, status="needs_human"), lead, (OID,)))
        world = Real()
        lead = lead_of(world.resource)
        case = world.case(lead)
        self.assertIsNone(world.approvals.plan_for(case, lead, ()), "with nobody to ask nothing is made")
        made["approvers"] = world.approvals._reason(case, ())
        self.assertEqual(set(made), set(proposals.CANNOT), "a key of the table that no case here makes has no test")
        for key, found in made.items():
            self.assertEqual(found, key)
            sentence = proposals.CANNOT[key]
            self.assertTrue(sentence[:1].isupper() and sentence.endswith(".") and len(sentence.split()) >= 6, sentence)

    def test_a_finding_that_carries_settings_always_gets_a_reason_whatever_stopped_the_change(self):
        world = Real()
        lead = lead_of(world.resource)
        world.approvals.reader = None
        self.assertEqual(self_key(world.approvals.plan_for(world.case(lead), lead, (OID,))), "unreadable", "no reader here: the change cannot be checked")
        world = Real(real=(ChangeScope(SUB, GROUP),))
        lead = lead_of(world.resource, resource_group=GROUP, subscription_id=SUB)
        self.assertEqual(self_key(world.approvals.plan_for(world.case(lead), lead, (OID,))), "outside", "a group of Meternaut's own is no place of this family")


def self_key(plan):
    return plan.preconditions.get(proposals.CANNOT_KEY) if plan is not None else None


class TheOldFamiliesAreAsTheyWere(unittest.TestCase):
    def test_the_registry_holds_the_new_family_last_and_its_words_and_it_is_the_only_one_that_is_real(self):
        self.assertEqual(registry.names()[-1], SETTING)
        self.assertEqual([f.name for f in registry.REGISTRY if f.real], [SETTING])
        self.assertEqual(words.shown(SETTING).summary, registry.get(SETTING).summary)
        self.assertEqual({name: words.shown(name).real for name in registry.names()}, {name: registry.get(name).real for name in registry.names()}, "the two flags cannot drift apart")
        self.assertEqual([name for name in registry.names() if words.words_of(name, None, "", "x", "g").confirm], [SETTING], "only the family of real resources asks once more although it can be undone")
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
