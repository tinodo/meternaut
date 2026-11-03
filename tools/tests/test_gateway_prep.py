import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1] / "gateway-prep.py"
spec = importlib.util.spec_from_file_location("gateway_prep", TOOL)
gp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gp)

SUB = "66666666-7777-8888-9999-000000000000"
APIM = f"/subscriptions/{SUB}/resourceGroups/rg-gateway/providers/Microsoft.ApiManagement/service/example-apim"
INSIGHTS = f"/subscriptions/{SUB}/resourceGroups/rg-gateway/providers/microsoft.insights/components/example-insights"
UAMI = f"/subscriptions/{SUB}/resourceGroups/rg-gateway/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-gateway"
OTHER = f"/subscriptions/{SUB}/resourceGroups/rg-other/providers/Microsoft.ManagedIdentity/userAssignedIdentities/other"


class Merge(unittest.TestCase):
    def test_a_system_assigned_identity_is_kept(self):
        body, changes = gp.merged_identity({"type": "SystemAssigned", "principalId": "p", "tenantId": "t"}, UAMI)
        self.assertTrue(changes)
        self.assertEqual(body, {"type": "SystemAssigned, UserAssigned", "userAssignedIdentities": {UAMI: {}}})

    def test_other_user_assigned_identities_are_kept(self):
        body, changes = gp.merged_identity({"type": "SystemAssigned, UserAssigned", "userAssignedIdentities": {OTHER: {"clientId": "c", "principalId": "p"}}}, UAMI)
        self.assertTrue(changes)
        self.assertEqual(body["type"], "SystemAssigned, UserAssigned")
        self.assertEqual(body["userAssignedIdentities"], {OTHER: {}, UAMI: {}})

    def test_an_instance_without_identity_gets_only_the_user_assigned_one(self):
        for current in (None, {}, {"type": "None"}):
            body, changes = gp.merged_identity(current, UAMI)
            self.assertTrue(changes)
            self.assertEqual(body, {"type": "UserAssigned", "userAssignedIdentities": {UAMI: {}}})

    def test_the_type_is_read_without_spaces_and_in_any_case(self):
        body, _ = gp.merged_identity({"type": "systemassigned,userassigned", "userAssignedIdentities": {OTHER: {}}}, UAMI)
        self.assertEqual(body["type"], "SystemAssigned, UserAssigned")

    def test_an_identity_that_is_attached_already_changes_nothing(self):
        body, changes = gp.merged_identity({"type": "SystemAssigned, UserAssigned", "userAssignedIdentities": {UAMI.upper(): {}}}, UAMI)
        self.assertEqual((body, changes), (None, False))


class Wait(unittest.TestCase):
    def clock(self):
        now = [0.0]
        def tick():
            return now[0]
        def sleep(seconds):
            now[0] += seconds
        return tick, sleep

    def test_it_returns_when_the_state_is_succeeded_and_polls_before(self):
        tick, sleep = self.clock()
        states = iter(["Updating", "Updating", "Succeeded"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(gp.wait_until_succeeded(lambda: next(states), 5, sleep=sleep, clock=tick, interval=30), "Succeeded")
        self.assertEqual(tick(), 60)

    def test_a_failed_or_canceled_state_stops_it_at_once(self):
        tick, sleep = self.clock()
        for bad in ("Failed", "Canceled", "failed"):
            with self.assertRaises(gp.Problem):
                gp.wait_until_succeeded(lambda bad=bad: bad, 5, sleep=sleep, clock=tick)
        self.assertEqual(tick(), 0)

    def test_it_gives_up_when_the_time_is_up(self):
        tick, sleep = self.clock()
        with redirect_stdout(io.StringIO()), self.assertRaises(gp.Problem) as caught:
            gp.wait_until_succeeded(lambda: "Updating", 2, sleep=sleep, clock=tick, interval=30)
        self.assertIn("2 minutes", str(caught.exception))


class Fake:
    """A stand-in for the management service: the instance, its logging setting, its loggers and the component."""

    DIAGNOSTIC = {
        "loggerId": "/x/loggers/old", "sampling": {"samplingType": "fixed", "percentage": 100.0}, "alwaysLog": "allErrors",
        "logClientIp": True, "metrics": None, "verbosity": None, "httpCorrelationProtocol": "Legacy",
        "frontend": {"request": {"headers": ["Accept"], "body": {"bytes": 512}}, "response": {"headers": [], "body": {"bytes": 0}}},
        "backend": {"request": {"headers": [], "body": {"bytes": 128}}, "response": {"headers": ["X-A"], "body": {"bytes": 0}}},
    }

    def __init__(self, state="Succeeded", identity=None, dimensions="WithDimensions", loggers=("azuremonitor", "old"), patch_failures=()):
        self.state, self.identity, self.dimensions, self.loggers = state, identity, dimensions, list(loggers)
        self.patch_failures = list(patch_failures)
        self.etag = 1
        self.calls = []

    def __call__(self, method, resource, api=gp.API, body=None, suffix="", headers=None):
        self.calls.append((method, resource, suffix, body, headers))
        if method == "patch":
            if self.patch_failures:
                failure = self.patch_failures.pop(0)
                if failure == "concurrent":  # somebody else attached an identity between the read and the write
                    self.identity = {"type": "SystemAssigned, UserAssigned", "userAssignedIdentities": {OTHER: {}}}
                    self.etag += 1
                raise gp.Problem("patch service/example-apim failed: (PreconditionFailed) The ETag does not match")
            self.identity = {"type": body["identity"]["type"], "userAssignedIdentities": body["identity"]["userAssignedIdentities"]}
            self.state = "Succeeded"
            self.etag += 1
            return {}
        if resource == INSIGHTS:
            return {"properties": {"CustomMetricsOptedInType": self.dimensions}}
        if suffix == "/diagnostics/applicationinsights":
            return {"properties": dict(self.DIAGNOSTIC)}
        if suffix == "/loggers":
            return {"value": [{"name": name} for name in self.loggers]}
        return {"etag": f"etag{self.etag}", "sku": {"name": "Developer", "capacity": 1}, "identity": self.identity,
                "properties": {"provisioningState": self.state, "virtualNetworkType": "External"}}

    def writes(self):
        return [c for c in self.calls if c[0] != "get"]


def run(argv, fake, env=None):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(gp, "az_rest", fake), mock.patch.dict(os.environ, env or {}, clear=False), redirect_stdout(out), redirect_stderr(err):
        code = gp.main(argv)
    return code, out.getvalue(), err.getvalue()


class Facts(unittest.TestCase):
    def test_it_reads_and_writes_nothing(self):
        fake = Fake(identity={"type": "SystemAssigned"})
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, err = run(["facts", "--apim", APIM, "--insights", INSIGHTS, "--summary", str(summary)], fake)
            text = summary.read_text(encoding="utf-8")
        self.assertEqual((code, err), (0, ""))
        document = json.loads(out)
        self.assertEqual(document["identity"], {"type": "SystemAssigned", "userAssigned": []})
        self.assertEqual(document["serviceLevelLogging"]["sampling"]["percentage"], 100.0)
        self.assertEqual(document["loggers"], ["azuremonitor", "old"])
        self.assertEqual(fake.writes(), [])
        self.assertIn("put these values back", text)
        self.assertIn("**on**", text)

    def test_the_logging_setting_is_recorded_complete_so_that_it_can_be_put_back(self):
        fake = Fake()
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, _ = run(["facts", "--apim", APIM, "--insights", INSIGHTS, "--summary", str(summary)], fake)
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["serviceLevelLogging"], Fake.DIAGNOSTIC)
        recorded = json.loads(text.split("```json\n", 1)[1].split("```", 1)[0])
        self.assertEqual(recorded, Fake.DIAGNOSTIC)
        self.assertEqual(recorded["frontend"]["request"]["body"]["bytes"], 512)
        self.assertEqual(recorded["backend"]["response"]["headers"], ["X-A"])

    def test_it_says_when_metrics_cannot_carry_dimensions_and_changes_nothing(self):
        fake = Fake(dimensions="WithoutDimensions")
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, _, _ = run(["facts", "--apim", APIM, "--insights", INSIGHTS, "--summary", str(summary)], fake)
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("**off**", text)
        self.assertIn("nothing here changes it", text)
        self.assertEqual(fake.writes(), [])

    def test_an_instance_that_is_being_updated_stops_it(self):
        code, out, err = run(["facts", "--apim", APIM, "--insights", INSIGHTS], Fake(state="Updating"))
        self.assertEqual(code, 2)
        self.assertIn("Updating", err)
        self.assertEqual(out, "")


class Attach(unittest.TestCase):
    ACTIONS = {"GITHUB_ACTIONS": "true"}

    def test_it_adds_the_identity_and_keeps_the_system_assigned_one(self):
        fake = Fake(identity={"type": "SystemAssigned", "principalId": "p"})
        code, out, err = run(["attach-identity", "--apim", APIM, "--identity", UAMI], fake, self.ACTIONS)
        self.assertEqual((code, err), (0, ""))
        (write,) = fake.writes()
        self.assertEqual(write[0], "patch")
        self.assertEqual(write[3], {"identity": {"type": "SystemAssigned, UserAssigned", "userAssignedIdentities": {UAMI: {}}}})
        self.assertIn("The update has finished", out)

    def test_the_write_is_conditional_on_the_etag_that_was_read(self):
        fake = Fake(identity={"type": "SystemAssigned"})
        run(["attach-identity", "--apim", APIM, "--identity", UAMI], fake, self.ACTIONS)
        (write,) = fake.writes()
        self.assertEqual(write[4], {"If-Match": "etag1"})

    def test_a_change_made_in_between_is_read_again_and_not_overwritten(self):
        fake = Fake(identity={"type": "SystemAssigned"}, patch_failures=["concurrent"])
        with mock.patch.object(gp.time, "sleep"):
            code, out, err = run(["attach-identity", "--apim", APIM, "--identity", UAMI], fake, self.ACTIONS)
        self.assertEqual((code, err), (0, ""))
        patches = [c for c in fake.calls if c[0] == "patch"]
        self.assertEqual(len(patches), 2)
        self.assertEqual(patches[1][3]["identity"]["userAssignedIdentities"], {OTHER: {}, UAMI: {}})
        self.assertEqual(patches[1][4], {"If-Match": "etag2"})
        self.assertIn("reading it again", out)

    def test_it_gives_up_after_three_conflicts(self):
        fake = Fake(identity={"type": "SystemAssigned"}, patch_failures=["x", "x", "x"])
        with mock.patch.object(gp.time, "sleep"):
            code, _, err = run(["attach-identity", "--apim", APIM, "--identity", UAMI], fake, self.ACTIONS)
        self.assertEqual(code, 2)
        self.assertIn("PreconditionFailed", err)
        self.assertEqual(len([c for c in fake.calls if c[0] == "patch"]), 3)

    def test_a_second_run_changes_nothing(self):
        fake = Fake(identity={"type": "SystemAssigned, UserAssigned", "userAssignedIdentities": {UAMI: {}}})
        code, out, _ = run(["attach-identity", "--apim", APIM, "--identity", UAMI], fake, self.ACTIONS)
        self.assertEqual(code, 0)
        self.assertEqual(fake.writes(), [])
        self.assertIn("attached already", out)

    def test_it_refuses_to_write_outside_github_actions(self):
        fake = Fake(identity={"type": "SystemAssigned"})
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_ACTIONS", None)
            code, _, err = run(["attach-identity", "--apim", APIM, "--identity", UAMI], fake)
        self.assertEqual(code, 2)
        self.assertIn("GitHub Actions", err)
        self.assertEqual(fake.calls, [])

    def test_it_does_not_write_while_the_instance_is_being_updated(self):
        fake = Fake(state="Updating", identity={"type": "SystemAssigned"})
        code, _, err = run(["attach-identity", "--apim", APIM, "--identity", UAMI], fake, self.ACTIONS)
        self.assertEqual(code, 2)
        self.assertEqual(fake.writes(), [])

    def test_the_ids_are_checked(self):
        fake = Fake()
        for argv in (["attach-identity", "--apim", "x", "--identity", UAMI],
                     ["attach-identity", "--apim", APIM, "--identity", INSIGHTS],
                     ["attach-identity", "--apim", APIM + "/apis/x", "--identity", UAMI],
                     ["facts", "--apim", APIM, "--insights", APIM]):
            self.assertEqual(run(argv, fake, self.ACTIONS)[0], 2, argv)
        self.assertEqual(fake.calls, [])


class Prepared(unittest.TestCase):
    def test_a_ready_gateway_passes(self):
        fake = Fake(identity={"type": "SystemAssigned, UserAssigned", "userAssignedIdentities": {UAMI.upper(): {}}}, loggers=("azuremonitor", "appinsights-logger"))
        code, out, err = run(["prepared", "--apim", APIM, "--identity", UAMI], fake)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("ready", out)
        self.assertEqual(fake.writes(), [])

    def test_what_is_missing_is_named(self):
        code, _, err = run(["prepared", "--apim", APIM, "--identity", UAMI], Fake(identity={"type": "SystemAssigned"}))
        self.assertEqual(code, 2)
        self.assertIn("identity is not attached", err)
        self.assertIn("appinsights-logger", err)
        self.assertIn("gateway-prepare", err)
        code, _, err = run(["prepared", "--apim", APIM, "--identity", UAMI],
                           Fake(state="Updating", identity={"userAssignedIdentities": {UAMI: {}}}, loggers=("appinsights-logger",)))
        self.assertEqual(code, 2)
        self.assertIn("Updating", err)


if __name__ == "__main__":
    unittest.main()
