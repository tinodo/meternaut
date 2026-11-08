import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("teams_check", ROOT / "tools" / "teams-check.py")
tc = importlib.util.module_from_spec(spec)
sys.modules["teams_check"] = tc
spec.loader.exec_module(tc)

SUB = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
APP = "func-meternaut-teams-0a1b2c3d"
BOT = "bot-meternaut-teams-0a1b2c3d"
IDENTITY = "id-meternaut-teams-bot"
CLIENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PRINCIPAL = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
TENANT = "cccccccc-dddd-eeee-ffff-000000000000"
HOST = "func-meternaut-teams-0a1b2c3d.azurewebsites.net"
BASE = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
IDENTITY_ID = f"{BASE}/Microsoft.ManagedIdentity/userAssignedIdentities/{IDENTITY}"
FAILED_READ = (1, "", "ERROR: something unexpected happened in the service")


def good():
    """What Azure shows for a bot that came out as its template says, by the path of each read."""
    return {
        f"{BASE}/Microsoft.ManagedIdentity/userAssignedIdentities/{IDENTITY}": {"properties": {"clientId": CLIENT, "principalId": PRINCIPAL, "tenantId": TENANT}},
        f"{BASE}/Microsoft.Authorization/roleAssignments": {"value": []},
        f"{BASE}/Microsoft.Web/sites/{APP}": {
            "kind": "functionapp,linux", "identity": {"type": "SystemAssigned, UserAssigned", "principalId": "dddddddd-0000-4000-8000-000000000001",
                                                       "userAssignedIdentities": {IDENTITY_ID: {"principalId": PRINCIPAL, "clientId": CLIENT}}},
            "properties": {"state": "Running", "httpsOnly": True, "defaultHostName": HOST,
                           "virtualNetworkSubnetId": f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-func"}},
        f"{BASE}/Microsoft.BotService/botServices/{BOT}": {
            "kind": "azurebot", "sku": {"name": "F0"},
            "properties": {"msaAppType": "UserAssignedMSI", "msaAppId": CLIENT, "msaAppMSIResourceId": IDENTITY_ID, "msaAppTenantId": TENANT, "disableLocalAuth": True,
                           "endpoint": f"https://{HOST}/api/messages"}},
        f"{BASE}/Microsoft.BotService/botServices/{BOT}/channels/MsTeamsChannel": {"properties": {"channelName": "MsTeamsChannel", "provisioningState": "Succeeded",
                                                                                                    "properties": {"isEnabled": True}}},
        f"{BASE}/Microsoft.Web/sites/{APP}/config/web": {"properties": {"minTlsVersion": "1.2", "ipSecurityRestrictionsDefaultAction": "Allow",
                                                                        "ipSecurityRestrictions": [{"ipAddress": "Any", "action": "Allow", "priority": 2147483647}]}},
        f"{BASE}/Microsoft.Web/sites/{APP}/basicPublishingCredentialsPolicies/scm": {"properties": {"allow": False}},
        f"{BASE}/Microsoft.Web/sites/{APP}/functions": {"value": [{"name": f"{APP}/teams-messages"}, {"name": f"{APP}/teams-offer"}]},
    }


class FakeAzure:
    """Answers each `az rest --method get` from a dict of documents, by the path, and keeps every call."""

    def __init__(self, documents=None):
        self.documents = good() if documents is None else documents
        self.calls, self.failures = [], {}

    def __call__(self, arguments):
        self.calls.append(list(arguments))
        assert arguments[:2] == ["rest", "--method"] and arguments[2] == "get", arguments
        url = arguments[arguments.index("--url") + 1]
        assert url.startswith(tc.ARM + "/") and "api-version=" in url and " " not in url, url
        path = url[len(tc.ARM):].split("?")[0]
        if path in self.failures:
            return self.failures[path]
        if path not in self.documents:
            return 1, "", "ERROR: (ResourceNotFound) The Resource was not found."
        return 0, json.dumps(self.documents[path]), ""

    def paths(self):
        return [a[a.index("--url") + 1][len(tc.ARM):].split("?")[0] for a in self.calls]


def read(azure, **options):
    return tc.read_back(azure, SUB, GROUP, APP, BOT, IDENTITY, sleep=lambda s: None, **options)


def failed(findings):
    return [text for ok, text in findings if not ok]


class ReadBack(unittest.TestCase):
    def test_a_bot_that_is_as_its_template_says_passes_every_line_and_only_gets_are_made(self):
        azure = FakeAzure()
        findings = read(azure)
        self.assertEqual(failed(findings), [])
        self.assertGreaterEqual(len(findings), 20)
        self.assertTrue(all(call[2] == "get" for call in azure.calls), "reads only")
        texts = " ".join(text for _, text in findings)
        for words in ("holds no role assignment", "is the free tier F0", "its app type is UserAssignedMSI", "its app id is the client id of the bot's identity", "local authentication is off",
                      "its endpoint is the one route of the app", "Teams channel of the bot is there", "runs in the function subnet snet-func", "no password", "exactly its two functions",
                      "Inbound: open to the internet, as designed"):
            self.assertIn(words, texts, words)

    def test_the_role_assignments_are_asked_for_the_principal_of_the_identity_and_nothing_is_a_post_or_a_list_of_settings(self):
        azure = FakeAzure()
        read(azure)
        urls = [call[call.index("--url") + 1] for call in azure.calls]
        asked = [u for u in urls if "roleAssignments" in u]
        self.assertEqual(len(asked), 1)
        self.assertIn(f"$filter=principalId%20eq%20'{PRINCIPAL}'", asked[0])
        self.assertFalse([u for u in urls if "appsettings" in u.lower() or "/list" in u], "no setting and no key is read")

    def test_each_difference_is_a_failed_line_that_names_it(self):
        def change(path, edit):
            def apply(documents):
                edit(documents[f"{BASE}/{path}"])
            return apply
        cases = {
            "the free tier": (change(f"Microsoft.BotService/botServices/{BOT}", lambda d: d["sku"].update(name="S1")), "it is the free tier F0"),
            "the app type": (change(f"Microsoft.BotService/botServices/{BOT}", lambda d: d["properties"].update(msaAppType="SingleTenant")), "its app type is UserAssignedMSI"),
            "the app id": (change(f"Microsoft.BotService/botServices/{BOT}", lambda d: d["properties"].update(msaAppId=PRINCIPAL)), "its app id is the client id of the bot's identity"),
            "the identity": (change(f"Microsoft.BotService/botServices/{BOT}", lambda d: d["properties"].update(msaAppMSIResourceId="/x")), "its identity is the bot's identity"),
            "the tenant": (change(f"Microsoft.BotService/botServices/{BOT}", lambda d: d["properties"].update(msaAppTenantId=CLIENT)), "its tenant is the tenant"),
            "local authentication": (change(f"Microsoft.BotService/botServices/{BOT}", lambda d: d["properties"].update(disableLocalAuth=False)), "local authentication is off"),
            "the endpoint": (change(f"Microsoft.BotService/botServices/{BOT}", lambda d: d["properties"].update(endpoint="https://elsewhere.example/api/messages")), "its endpoint is the one route"),
            "the channel": (change(f"Microsoft.BotService/botServices/{BOT}/channels/MsTeamsChannel", lambda d: d["properties"]["properties"].update(isEnabled=False)), "not MsTeamsChannel, is not Succeeded or is disabled"),
            "the state": (change(f"Microsoft.Web/sites/{APP}", lambda d: d["properties"].update(state="Stopped")), "it is Running"),
            "https": (change(f"Microsoft.Web/sites/{APP}", lambda d: d["properties"].update(httpsOnly=False)), "it takes https only"),
            "the bot's identity on the app": (change(f"Microsoft.Web/sites/{APP}", lambda d: d["identity"].update(userAssignedIdentities={})), "it has the bot's identity"),
            "the system identity": (change(f"Microsoft.Web/sites/{APP}", lambda d: d["identity"].update(type="UserAssigned")), "it has an identity of its own"),
            "the subnet": (change(f"Microsoft.Web/sites/{APP}", lambda d: d["properties"].update(virtualNetworkSubnetId="/subscriptions/x/subnets/snet-other")), "it runs in the function subnet snet-func"),
            "tls": (change(f"Microsoft.Web/sites/{APP}/config/web", lambda d: d["properties"].update(minTlsVersion="1.0")), "does not require TLS 1.2"),
            "the password policy": (change(f"Microsoft.Web/sites/{APP}/basicPublishingCredentialsPolicies/scm", lambda d: d["properties"].update(allow=True)), "takes a password"),
            "a function of the cases app": (change(f"Microsoft.Web/sites/{APP}/functions", lambda d: d["value"].append({"name": f"{APP}/console"})), "and not exactly teams-messages, teams-offer"),
            "a missing function": (change(f"Microsoft.Web/sites/{APP}/functions", lambda d: d["value"].pop()), "and not exactly teams-messages, teams-offer"),
            "a role held": (change("Microsoft.Authorization/roleAssignments", lambda d: d["value"].append({"properties": {"roleDefinitionId": "x"}})), "holds 1 role assignment(s)"),
        }
        for name, (edit, words) in cases.items():
            documents = good()
            edit(documents)
            problems = failed(read(FakeAzure(documents)))
            self.assertTrue(any(words in p for p in problems), (name, problems))
            self.assertLessEqual(len(problems), 2, (name, problems))

    def test_a_resource_that_is_not_there_is_one_failed_line_and_the_rest_is_still_read(self):
        documents = good()
        del documents[f"{BASE}/Microsoft.BotService/botServices/{BOT}"]
        findings = read(FakeAzure(documents))
        self.assertEqual(failed(findings), [f"The Azure Bot resource {BOT} is not there"])
        self.assertIn("exactly its two functions", " ".join(text for _, text in findings))

    def test_a_read_that_azure_refuses_is_a_failed_line_with_the_first_line_of_its_error(self):
        azure = FakeAzure()
        azure.failures[f"{BASE}/Microsoft.Web/sites/{APP}/config/web"] = FAILED_READ
        problems = failed(read(azure))
        self.assertEqual(problems, [f"The configuration of the function app {APP} could not be read: ERROR: something unexpected happened in the service"])

    def test_an_az_that_does_not_answer_stops_the_read_back_and_says_so(self):
        calls = []

        def stuck(arguments):
            calls.append(arguments)
            raise tc.Stuck("az did not answer within 5 seconds")

        findings = read(stuck)
        self.assertEqual(len(calls), 1, "nothing is read after the first read that does not answer")
        self.assertIn("The read-back stops here: nothing after it was read", failed(findings)[0])

    def test_the_inbound_side_is_said_when_it_is_narrowed_and_is_no_failure(self):
        documents = good()
        documents[f"{BASE}/Microsoft.Web/sites/{APP}/config/web"]["properties"].update(
            ipSecurityRestrictionsDefaultAction="Deny", ipSecurityRestrictions=[{"ipAddress": "AzureBotService", "tag": "ServiceTag", "action": "Allow", "priority": 100}])
        findings = read(FakeAzure(documents))
        self.assertEqual(failed(findings), [])
        self.assertIn("Inbound: only AzureBotService (the rest is denied)", " ".join(text for _, text in findings))

    def test_a_site_that_has_just_been_given_its_code_is_waited_for_and_a_list_that_stays_wrong_fails_when_the_time_is_up(self):
        documents = good()
        functions = documents[f"{BASE}/Microsoft.Web/sites/{APP}/functions"]
        first = list(functions["value"])
        functions["value"] = []
        azure, slept, now = FakeAzure(documents), [], [0.0]

        def sleep(seconds):
            slept.append(seconds)
            now[0] += seconds
            if len(slept) == 2:
                functions["value"] = first

        findings = tc.read_back(azure, SUB, GROUP, APP, BOT, IDENTITY, 120, sleep, lambda: now[0])
        self.assertEqual((failed(findings), slept), ([], [15, 15]))
        functions["value"] = []
        slept.clear()
        now[0] = 0.0
        findings = tc.read_back(FakeAzure(documents), SUB, GROUP, APP, BOT, IDENTITY, 45, lambda s: now.__setitem__(0, now[0] + s), lambda: now[0])
        self.assertEqual(failed(findings), [f"The app lists no function, and not exactly teams-messages, teams-offer"])


class Door(unittest.TestCase):
    def transport(self, answers):
        """A stand-in for the request: `answers` is a list of results, in order, each (status, length) or an exception to raise."""
        calls = []
        script = list(answers)

        def send(method, url, headers, body, timeout):
            calls.append((method, url, headers, body, timeout))
            answer = script.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        return send, calls

    def test_a_door_that_refuses_everything_passes_and_the_requests_are_the_four_that_the_docstring_says(self):
        send, calls = self.transport([(401, 0), (401, 0), (404, 0), (401, 0)])
        findings = tc.door(HOST, 3, 1, 5, send, lambda s: None)
        self.assertEqual(failed(findings), [])
        self.assertEqual([(m, u) for m, u, *_ in calls], [("POST", f"https://{HOST}/api/messages"), ("POST", f"https://{HOST}/api/messages"), ("GET", f"https://{HOST}/api/messages"),
                                                          ("GET", f"https://{HOST}/admin/host/status")])
        self.assertNotIn("Authorization", calls[0][2], "the first request carries no token")
        self.assertEqual(calls[1][2]["Authorization"], "Bearer not.a.token", "the second carries one that is not one")
        self.assertEqual({c[4] for c in calls}, {5})

    def test_each_answer_that_is_not_the_refusal_is_a_failed_line_that_says_what_it_got(self):
        right = [(401, 0), (401, 0), (404, 0), (401, 0)]
        for position, wrong, words in (
            (0, (200, 0), "a POST with no token: was answered with 200"),
            (1, (200, 12), "a POST with a token that is not one: was answered with 200"),
            (0, (403, 0), "a POST with no token: was answered with 403"),
            (1, (401, 7), "a POST with a token that is not one: was answered with 401 and 7+ bytes of body"),
            (2, (200, 400), "a GET of the route: was answered with 200"),
            (3, (200, 90), "the host's admin endpoint with no key: was answered with 200"),
        ):
            answers = list(right)
            answers[position] = wrong
            send, _ = self.transport(answers)
            problems = failed(tc.door(HOST, 1, 0, 5, send, lambda s: None))
            self.assertEqual(len(problems), 1, (words, problems))
            self.assertIn(words, problems[0])

    def test_a_cold_start_is_waited_for_and_a_door_that_never_answers_fails(self):
        send, _ = self.transport([tc.NoAnswer("TimeoutError"), (503, 0), (401, 0), (401, 0), (404, 0), (401, 0)])
        slept = []
        findings = tc.door(HOST, 4, 15, 5, send, slept.append)
        self.assertEqual((failed(findings), slept), ([], [15, 15]))
        send, _ = self.transport([tc.NoAnswer("ConnectionResetError")] * 8)
        problems = failed(tc.door(HOST, 2, 0, 5, send, lambda s: None))
        self.assertEqual(len(problems), 4, "every knock failed")
        self.assertIn("got no answer (ConnectionResetError) at try 2 of 2; the app did not answer as a closed door does", problems[0])

    def test_a_server_error_is_not_a_refusal(self):
        send, _ = self.transport([(500, 0)] * 8)
        problems = failed(tc.door(HOST, 2, 0, 5, send, lambda s: None))
        self.assertEqual(len(problems), 4)
        self.assertIn("was answered with 500 at try 2 of 2", problems[0])


class TheCommandLine(unittest.TestCase):
    def run_main(self, argv, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = tc.main(argv, **kwargs)
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue(), err.getvalue()

    READ = ["read-back", "--subscription", SUB, "--resource-group", GROUP, "--app", APP, "--bot", BOT, "--identity", IDENTITY]

    def test_read_back_exits_0_and_writes_the_summary_when_all_is_well_and_1_when_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, _ = self.run_main([*self.READ, "--summary", str(summary)], az=FakeAzure(), sleep=lambda s: None)
            self.assertEqual(code, 0, out)
            text = summary.read_text(encoding="utf-8")
            self.assertIn("### The Teams bot, read back from Azure", text)
            self.assertIn(f"Function app `{APP}`", text)
            documents = good()
            documents[f"{BASE}/Microsoft.Web/sites/{APP}"]["properties"]["state"] = "Stopped"
            code, out, err = self.run_main([*self.READ, "--summary", str(summary)], az=FakeAzure(documents), sleep=lambda s: None)
            self.assertEqual(code, 1)
            self.assertIn("FAILED: The function app", out)
            self.assertIn("1 thing(s) are not as they should be", err)
            self.assertIn("FAILED:", summary.read_text(encoding="utf-8"))

    def test_the_inputs_are_checked_before_anything_is_read(self):
        azure = FakeAzure()
        for argv in (["read-back", "--subscription", "x", "--resource-group", GROUP, "--app", APP, "--bot", BOT, "--identity", IDENTITY],
                     ["read-back", "--subscription", SUB, "--resource-group", "a b", "--app", APP, "--bot", BOT, "--identity", IDENTITY],
                     [*self.READ, "--timeout", "0"], [*self.READ, "--wait-seconds", "-1"], ["door", "--host", "not a host"], ["door", "--host", HOST, "--tries", "0"], ["door"]):
            code, _, err = self.run_main(argv, az=azure)
            self.assertEqual(code, 2, argv)
        self.assertEqual(azure.calls, [])

    def test_door_exits_0_for_a_closed_door_and_1_for_an_open_one(self):
        def send_all(status):
            return lambda method, url, headers, body, timeout: (status, 0)
        code, out, _ = self.run_main(["door", "--host", HOST.upper(), "--tries", "1", "--interval", "0"], transport=lambda m, u, h, b, t: (401 if m == "POST" or "admin" in u else 404, 0))
        self.assertEqual(code, 0, out)
        self.assertIn("ok: a POST with no token: refused with 401 and an empty body", out)
        code, out, err = self.run_main(["door", "--host", HOST, "--tries", "1", "--interval", "0"], transport=send_all(200))
        self.assertEqual(code, 1)
        self.assertEqual(out.count("FAILED:"), 4)

    def test_the_tool_makes_no_request_that_changes_anything(self):
        source = (ROOT / "tools" / "teams-check.py").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'"--method", "(\w+)"', source)), {"get"}, "the reads of Azure are GET requests")
        self.assertNotIn("/list", source.replace("/list.", ""), "no list of settings or keys (a POST) is read")


if __name__ == "__main__":
    unittest.main()
