"""tools/teams-params.py: the parameter file of the Teams bot's template, made from the cases app's. Nothing here reads Azure."""
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("teams_params", ROOT / "tools" / "teams-params.py")
tp = importlib.util.module_from_spec(spec)
sys.modules["teams_params"] = tp
spec.loader.exec_module(tp)

APPROVER = "11111111-1111-4111-8111-111111111111"
OPS = "22222222-2222-4222-8222-222222222222"
PEOPLE = [{"oid": APPROVER, "name": "Maya", "roles": ["owner", "approver"], "mail": "maya@example.com"}, {"oid": OPS, "name": "Omar", "roles": ["ops"]}]
CASES_APP = "func-meternaut-cases-0a1b2c3d"


def cases_file(**changes) -> dict:
    values = {"location": "swedencentral", "owner": "platform-team", "storageAccountName": "stmeternaut0a1b2c3d", "functionAppName": CASES_APP,
              "consolePeople": json.dumps(PEOPLE, separators=(",", ":")), "consoleHostName": "", "casesAppPlan": "Flex"}
    values.update(changes)
    return {"$schema": tp.SCHEMA, "contentVersion": "1.0.0.0", "parameters": {name: {"value": value} for name, value in values.items()}}


class TheNames(unittest.TestCase):
    def test_the_names_of_the_bot_follow_the_digest_of_the_cases_app(self):
        self.assertEqual(tp.names_of(CASES_APP), {"bot_app_name": "func-meternaut-teams-0a1b2c3d", "bot_name": "bot-meternaut-teams-0a1b2c3d"})

    def test_a_cases_app_that_is_not_called_what_the_workflow_calls_it_is_refused(self):
        for bad in ("", "func-meternaut-cases-0A1B2C3D", "func-meternaut-cases-0a1b2c3", "func-other-0a1b2c3d", "func-meternaut-cases-0a1b2c3d-x", None):
            with self.subTest(bad=bad):
                with self.assertRaises(tp.Problem):
                    tp.names_of(bad)


class TheValues(unittest.TestCase):
    def test_they_are_what_the_cases_app_holds_and_the_two_names_that_are_the_bots_own(self):
        values = tp.values_of(cases_file())
        self.assertEqual(values["location"], "swedencentral")
        self.assertEqual(values["owner"], "platform-team")
        self.assertEqual(values["storageAccountName"], "stmeternaut0a1b2c3d")
        self.assertEqual(json.loads(values["consolePeople"]), PEOPLE, "the same people, so that the bot and the page answer the same person")
        self.assertEqual((values["botAppName"], values["botName"]), ("func-meternaut-teams-0a1b2c3d", "bot-meternaut-teams-0a1b2c3d"))
        self.assertEqual(values["alwaysReadyInstances"], 0, "no instance is kept warm and billed")

    def test_the_host_of_the_page_is_the_gateways_name_when_there_is_one_and_the_cases_apps_own_otherwise(self):
        self.assertEqual(tp.values_of(cases_file())["consoleHost"], f"{CASES_APP}.azurewebsites.net")
        self.assertEqual(tp.values_of(cases_file(consoleHostName="console.example.com"))["consoleHost"], "console.example.com")

    def test_a_file_that_lacks_what_the_bot_needs_is_refused_with_one_line(self):
        for name in ("location", "owner", "storageAccountName", "consolePeople", "functionAppName"):
            broken = cases_file()
            del broken["parameters"][name]
            with self.subTest(missing=name):
                with self.assertRaises(tp.Problem) as caught:
                    tp.values_of(broken)
                self.assertIn(name, str(caught.exception))
        with self.assertRaises(tp.Problem):
            tp.values_of({"nothing": 1})
        with self.assertRaises(tp.Problem):
            tp.values_of([])

    def test_a_bot_without_an_approver_or_with_people_that_are_not_people_answers_nobody_so_it_is_not_made(self):
        for people in ([{"oid": OPS, "name": "Omar", "roles": ["ops"]}], [], [{"oid": "not-a-guid", "name": "x", "roles": ["approver"]}], [{"oid": APPROVER, "roles": ["approver"]}],
                       [{"oid": APPROVER, "name": "Maya", "roles": "approver"}], "not a list"):
            with self.subTest(people=people):
                with self.assertRaises(tp.Problem):
                    tp.values_of(cases_file(consolePeople=json.dumps(people) if not isinstance(people, str) else people))

    def test_values_that_are_not_what_they_should_be_are_refused(self):
        for changes in ({"location": "Sweden Central"}, {"location": "x"}, {"storageAccountName": "Not_A_Storage_Account"}, {"storageAccountName": "ab"},
                        {"consoleHostName": "not a host"}, {"consoleHostName": "https://console.example.com"}, {"functionAppName": "func-meternaut-cases-xyz"}):
            with self.subTest(changes=changes):
                with self.assertRaises(tp.Problem):
                    tp.values_of(cases_file(**changes))


class TheFile(unittest.TestCase):
    def test_the_parameters_are_the_template_s_and_nothing_else(self):
        template = (ROOT / "environment" / "teams" / "main.bicep").read_text(encoding="utf-8")
        declared = set(re.findall(r"^param (\w+) ", template, re.M))
        without_default = {m.group(1) for m in re.finditer(r"^param (\w+) \w+$", template, re.M)}
        written = set(tp.values_of(cases_file()))
        self.assertTrue(written <= declared, f"the file names a parameter that the template does not have: {written - declared}")
        self.assertTrue(without_default <= written, f"the file leaves out a parameter that the template needs: {without_default - written}")

    def test_it_is_a_deployment_parameter_file(self):
        document = tp.parameter_file({"a": 1, "b": "x"})
        self.assertEqual(document["parameters"], {"a": {"value": 1}, "b": {"value": "x"}})
        self.assertEqual(document["contentVersion"], "1.0.0.0")
        self.assertTrue(document["$schema"].endswith("deploymentParameters.json#"))


class TheCommandLine(unittest.TestCase):
    def run_main(self, folder: str, cases: dict | str):
        source, target = Path(folder) / "cases.parameters.json", Path(folder) / "teams.parameters.json"
        source.write_text(cases if isinstance(cases, str) else json.dumps(cases), encoding="utf-8")
        out = io.StringIO()
        stderr, sys.stderr = sys.stderr, io.StringIO()
        try:
            code = tp.main(["--cases-params", str(source), "--out", str(target)], out)
            message = sys.stderr.getvalue()
        finally:
            sys.stderr = stderr
        return code, out.getvalue(), message, target

    def test_it_writes_the_file_and_the_lines_for_the_workflow_s_output(self):
        with tempfile.TemporaryDirectory() as folder:
            code, text, message, target = self.run_main(folder, cases_file())
            self.assertEqual((code, message), (0, ""))
            self.assertEqual(text.splitlines(), ["teams_bot_app_name=func-meternaut-teams-0a1b2c3d", "teams_bot_name=bot-meternaut-teams-0a1b2c3d",
                                                  f"teams_console_host={CASES_APP}.azurewebsites.net"])
            written = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(written["parameters"]["botAppName"]["value"], "func-meternaut-teams-0a1b2c3d")

    def test_it_refuses_in_one_line_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            broken = cases_file()
            del broken["parameters"]["consolePeople"]
            code, text, message, target = self.run_main(folder, broken)
            self.assertEqual((code, text), (1, ""))
            self.assertTrue(message.startswith("error: "))
            self.assertEqual(message.count("\n"), 1)
            self.assertFalse(target.exists())
            code, text, message, target = self.run_main(folder, "not json")
            self.assertEqual((code, text), (1, ""))
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
