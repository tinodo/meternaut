import contextlib
import copy
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("foundry_check", ROOT / "tools" / "foundry-check.py")
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)

MODELS_FILE = ROOT / "environment" / "models.json"
MODELS = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
ACCOUNT = "aif-meternaut-agents-0123abcd"
PROJECT = "meternaut"
GUARDRAIL = "meternaut-agents"
ENDPOINT = f"https://{ACCOUNT}.services.ai.azure.com/api/projects/{PROJECT}"
PRIVATE_ENDPOINT = f"pe-{ACCOUNT}"


def good():
    """What Azure answers for a resource that came out as the template says, by the end of the address that was asked."""
    return {
        f"/accounts/{ACCOUNT}": {"kind": "AIServices", "identity": {"type": "SystemAssigned", "principalId": "p"},
                                 "properties": {"publicNetworkAccess": "Disabled", "disableLocalAuth": True, "allowProjectManagement": True}},
        f"/privateEndpoints/{PRIVATE_ENDPOINT}": {"properties": {"provisioningState": "Succeeded", "privateLinkServiceConnections": [
            {"properties": {"privateLinkServiceConnectionState": {"status": "Approved"}}}]}},
        f"/projects/{PROJECT}": {"identity": {"principalId": "q"}, "properties": {"endpoints": {"AI Foundry API": ENDPOINT}}},
        "/deployments": {"value": [{"name": m["name"], "sku": {"name": m["sku"], "capacity": m["capacity"]},
                                    "properties": {"model": {"format": "OpenAI", "name": m["name"], "version": m["version"]}, "raiPolicyName": GUARDRAIL}} for m in MODELS]},
        f"/raiPolicies/{GUARDRAIL}": {"properties": {"contentFilters": [
            {"name": "Jailbreak", "source": "Prompt", "enabled": True, "blocking": True},
            {"name": "Indirect Attack", "source": "Prompt", "enabled": True, "blocking": True},
            {"name": "Indirect Attack", "source": "PostToolCall", "enabled": True, "blocking": True}]}},
        f"/projects/{PROJECT}/connections": {"value": [{"name": "appi-meternaut", "properties": {"category": "AppInsights", "authType": "ProjectManagedIdentity"}}]},
    }


class Azure:
    """A stand-in for `az`: it answers the GET requests from a table, and remembers every call."""

    def __init__(self, documents, errors=None):
        self.documents, self.errors, self.calls = documents, errors or {}, []

    def __call__(self, arguments):
        self.calls.append(arguments)
        url = arguments[arguments.index("--url") + 1].split("?")[0]
        for tail, text in self.errors.items():
            if url.endswith(tail):
                return 1, "", text
        # the longest matching end wins: /projects/meternaut/connections before /projects/meternaut
        for tail in sorted(self.documents, key=len, reverse=True):
            if url.endswith(tail):
                return 0, json.dumps(self.documents[tail]), ""
        return 1, "", "ERROR: (ResourceNotFound) The resource was not found."


def check(documents=None, errors=None, models=MODELS):
    az = Azure(documents if documents is not None else good(), errors)
    found = fc.read_back(az, SUBSCRIPTION, GROUP, ACCOUNT, PROJECT, GUARDRAIL, PRIVATE_ENDPOINT, ENDPOINT, models)
    return found, az


def failures(found):
    return [text for ok, text in found if not ok]


def changed(path, change):
    documents = good()
    change(documents[path])
    return documents


class ReadBack(unittest.TestCase):
    def test_a_resource_that_came_out_as_the_template_says_passes_every_check(self):
        found, az = check()
        self.assertEqual(failures(found), [])
        text = "\n".join(t for _, t in found)
        for words in ("public network access is Disabled", "local authentication is off", "project management is on", "made and approved", "with an identity of its own",
                      "is the one that the cases app is given", f"The deployment {MODELS[0]['name']}", f"The deployment {MODELS[1]['name']}",
                      "blocks Jailbreak at Prompt", "blocks Indirect Attack at PostToolCall", "traces to Application Insights with its identity"):
            self.assertIn(words, text)
        self.assertEqual(len(found), 5 + 1 + 2 + len(MODELS) + 3 + 1)

    def test_only_reads_are_made_and_no_key_is_asked_for(self):
        _, az = check()
        self.assertGreaterEqual(len(az.calls), 6)
        for call in az.calls:
            self.assertEqual(call[:3], ["rest", "--method", "get"], call)
            joined = " ".join(call).lower()
            for word in ("listkeys", "listsecrets", "list-keys", "--method post", "--method put", "--method delete", "--method patch"):
                self.assertNotIn(word, joined)
        self.assertEqual({c[c.index("--url") + 1].split("/providers/")[1].split("/")[0] for c in az.calls}, {"Microsoft.CognitiveServices", "Microsoft.Network"})

    def test_each_property_that_the_design_rests_on_is_a_failure_when_it_differs(self):
        account = f"/accounts/{ACCOUNT}"
        for label, change in (("public network access", lambda d: d["properties"].update(publicNetworkAccess="Enabled")),
                              ("public network access, taken away by a policy", lambda d: d["properties"].pop("publicNetworkAccess")),
                              ("local authentication", lambda d: d["properties"].update(disableLocalAuth=False)),
                              ("local authentication, missing", lambda d: d["properties"].pop("disableLocalAuth")),
                              ("project management", lambda d: d["properties"].update(allowProjectManagement=False)),
                              ("project management, missing", lambda d: d["properties"].pop("allowProjectManagement")),
                              ("identity", lambda d: d.pop("identity")),
                              ("kind", lambda d: d.update(kind="OpenAI"))):
            found, _ = check(changed(account, change))
            self.assertEqual(len(failures(found)), 1, label)
            self.assertTrue(failures(found)[0].startswith("The Foundry resource differs"), label)

    def test_a_value_that_is_a_string_and_not_a_boolean_is_no_pass(self):
        for value in ("true", "True", 1, "Disabled"):
            found, _ = check(changed(f"/accounts/{ACCOUNT}", lambda d: d["properties"].update(disableLocalAuth=value, allowProjectManagement=value)))
            self.assertEqual(len(failures(found)), 2, value)

    def test_a_missing_resource_is_a_failure_that_names_it(self):
        for path, words in ((f"/accounts/{ACCOUNT}", "The Foundry resource"), (f"/privateEndpoints/{PRIVATE_ENDPOINT}", "The private endpoint"),
                            (f"/projects/{PROJECT}", "The project meternaut is not there"), ("/deployments", "The model deployments"),
                            (f"/raiPolicies/{GUARDRAIL}", "The guardrail"), (f"/projects/{PROJECT}/connections", "The connections of the project")):
            documents = good()
            del documents[path]
            found, _ = check(documents)
            self.assertEqual(len(failures(found)), 1 + (len(MODELS) * 0), path)
            self.assertIn(words, failures(found)[0], path)
            self.assertIn("is not there", failures(found)[0], path)

    def test_an_answer_that_is_not_not_found_is_a_failure_with_the_first_line_of_the_error_only(self):
        found, _ = check(errors={f"/projects/{PROJECT}": "ERROR: (AuthorizationFailed) The client has no right.\nTraceID 123\nmore text"})
        (text,) = failures(found)
        self.assertIn("could not be read: ERROR: (AuthorizationFailed) The client has no right.", text)
        self.assertNotIn("TraceID", text)

    def test_an_answer_that_is_not_json_or_not_an_object_is_a_failure(self):
        class Odd:
            def __init__(self, out):
                self.out = out

            def __call__(self, arguments):
                return 0, self.out, ""

        for out in ("not json", "[1, 2]", ""):
            found = fc.read_back(Odd(out), SUBSCRIPTION, GROUP, ACCOUNT, PROJECT, GUARDRAIL, PRIVATE_ENDPOINT, ENDPOINT, MODELS)
            self.assertEqual(len(failures(found)), len(found), out)

    def test_a_private_endpoint_that_is_not_made_or_not_approved_is_a_failure(self):
        path = f"/privateEndpoints/{PRIVATE_ENDPOINT}"
        for label, change in (("pending", lambda d: d["properties"]["privateLinkServiceConnections"][0]["properties"]["privateLinkServiceConnectionState"].update(status="Pending")),
                              ("rejected", lambda d: d["properties"]["privateLinkServiceConnections"][0]["properties"]["privateLinkServiceConnectionState"].update(status="Rejected")),
                              ("failed", lambda d: d["properties"].update(provisioningState="Failed")),
                              ("no connection", lambda d: d["properties"].update(privateLinkServiceConnections=[]))):
            found, _ = check(changed(path, change))
            self.assertEqual(len(failures(found)), 1, label)
            self.assertIn("is not made and approved", failures(found)[0], label)

    def test_a_project_without_an_identity_or_with_another_endpoint_is_a_failure(self):
        found, _ = check(changed(f"/projects/{PROJECT}", lambda d: d.pop("identity")))
        self.assertEqual(failures(found), ["The project meternaut: has no identity of its own"])
        found, _ = check(changed(f"/projects/{PROJECT}", lambda d: d["properties"]["endpoints"].update({"AI Foundry API": "https://other.services.ai.azure.com/api/projects/x"})))
        self.assertEqual(len(failures(found)), 1)
        self.assertIn("is not the one that the cases app is given", failures(found)[0])
        for same in (ENDPOINT + "/", ENDPOINT.upper()):
            found, _ = check(changed(f"/projects/{PROJECT}", lambda d: d["properties"]["endpoints"].update({"AI Foundry API": same})))
            self.assertEqual(failures(found), [], same)
        found, _ = check(changed(f"/projects/{PROJECT}", lambda d: d["properties"].pop("endpoints")))
        self.assertEqual(failures(found), [], "an answer without the endpoint says nothing to compare")

    def test_every_model_of_models_json_must_be_deployed_as_it_says_with_the_guardrail(self):
        for label, change in (("a model is missing", lambda d: d["value"].pop()),
                              ("another version", lambda d: d["value"][0]["properties"]["model"].update(version="2020-01-01")),
                              ("another type", lambda d: d["value"][0]["sku"].update(name="GlobalStandard")),
                              ("another capacity", lambda d: d["value"][0]["sku"].update(capacity=1)),
                              ("another model", lambda d: d["value"][0]["properties"]["model"].update(name="gpt-x")),
                              ("another guardrail", lambda d: d["value"][0]["properties"].update(raiPolicyName="Microsoft.DefaultV2")),
                              ("no guardrail", lambda d: d["value"][0]["properties"].pop("raiPolicyName"))):
            found, _ = check(changed("/deployments", change))
            self.assertEqual(len(failures(found)), 1, label)
            self.assertIn("The deployment", failures(found)[0], label)
        extra = changed("/deployments", lambda d: d["value"].append({"name": "added-by-hand", "properties": {}}))
        self.assertEqual(failures(check(extra)[0]), [], "a deployment that somebody added is not a failure")
        no_models = changed("/deployments", lambda d: d.update(value=[]))
        self.assertEqual(len(failures(check(no_models)[0])), len(MODELS))

    def test_the_guardrail_must_block_the_three_shields_it_is_for(self):
        path = f"/raiPolicies/{GUARDRAIL}"
        for index, label in enumerate(("Jailbreak at Prompt", "Indirect Attack at Prompt", "Indirect Attack at PostToolCall")):
            for how, change in (("missing", lambda d, i=index: d["properties"]["contentFilters"].pop(i)),
                                ("not blocking", lambda d, i=index: d["properties"]["contentFilters"][i].update(blocking=False)),
                                ("not enabled", lambda d, i=index: d["properties"]["contentFilters"][i].update(enabled=False)),
                                ("another source", lambda d, i=index: d["properties"]["contentFilters"][i].update(source="Completion"))):
                found, _ = check(changed(path, change))
                self.assertEqual(failures(found), [f"The guardrail does not block {label}"], f"{label}: {how}")
        found, _ = check(changed(path, lambda d: d["properties"].pop("contentFilters")))
        self.assertEqual(len(failures(found)), 3)

    def test_the_connection_to_application_insights_must_exist_once_and_use_an_identity(self):
        path = f"/projects/{PROJECT}/connections"
        for label, change in (("an api key", lambda d: d["value"][0]["properties"].update(authType="ApiKey")),
                              ("a shared key", lambda d: d["value"][0]["properties"].update(authType="AccountKey")),
                              ("no connection", lambda d: d.update(value=[])),
                              ("another category", lambda d: d["value"][0]["properties"].update(category="AzureOpenAI")),
                              ("two connections", lambda d: d["value"].append(copy.deepcopy(d["value"][0])))):
            found, _ = check(changed(path, change))
            self.assertEqual(len(failures(found)), 1, label)
            self.assertIn("connection to Application Insights", failures(found)[0], label)
        for kind in fc.ENTRA_AUTH_TYPES:
            found, _ = check(changed(path, lambda d, k=kind: d["value"][0]["properties"].update(authType=k)))
            self.assertEqual(failures(found), [], kind)

    def test_the_check_names_the_same_api_versions_as_the_templates(self):
        template = (ROOT / "environment" / "foundry" / "main.bicep").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"'Microsoft\.CognitiveServices/[A-Za-z/]+@([0-9-]+)'", template)), {fc.API})
        self.assertIn(f"'Microsoft.Network/privateEndpoints@{fc.NETWORK_API}'", template)
        self.assertEqual(sorted(fc.SHIELDS), sorted((n, s) for n, s in re.findall(r"\{ name: '([A-Za-z ]+)', source: '(\w+)', enabled: true, blocking: true \}", template)))
        for word in fc.ENTRA_AUTH_TYPES[:1]:
            self.assertIn(f"authType: '{word}'", template)


class Main(unittest.TestCase):
    ARGS = ["read-back", "--subscription", SUBSCRIPTION, "--resource-group", GROUP, "--account", ACCOUNT, "--project", PROJECT, "--guardrail", GUARDRAIL,
            "--private-endpoint", PRIVATE_ENDPOINT, "--endpoint", ENDPOINT, "--models", str(MODELS_FILE)]

    def run_main(self, documents=None, extra=()):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fc.main([*self.ARGS, *extra], az=Azure(documents if documents is not None else good()))
        return code, out.getvalue(), err.getvalue()

    def test_a_good_resource_exits_0_and_prints_ok_lines_only(self):
        code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("FAILED", out)
        self.assertEqual(len(out.splitlines()), 5 + 1 + 2 + len(MODELS) + 3 + 1, "the resource, its endpoint, its project, its models, the shields and the connection")

    def test_a_difference_exits_1_names_it_and_says_that_nothing_is_repaired(self):
        code, out, err = self.run_main(changed(f"/accounts/{ACCOUNT}", lambda d: d["properties"].update(publicNetworkAccess="Enabled")))
        self.assertEqual(code, 1)
        self.assertIn("FAILED: The Foundry resource differs from its template: public network access is Disabled is not so", out)
        self.assertIn("1 thing(s) differ", err)
        self.assertIn("nothing is repaired from here", err)

    def test_the_summary_holds_the_endpoint_and_the_lines_and_no_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            summary.write_text("earlier\n", encoding="utf-8")
            code, out, _ = self.run_main(extra=("--summary", str(summary)))
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith("earlier\n### The Foundry resource, read back from Azure"), "it appends")
        self.assertIn(f"Project endpoint: `{ENDPOINT}`", text)
        self.assertIn(out.strip(), text)
        for word in ("key", "secret", "password", "token"):
            self.assertNotIn(word, text.lower().replace("tokens a minute", ""), word)

    def test_a_models_file_that_is_not_a_list_of_models_is_refused_before_anything_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            for text in ("{", "[]", "{}", '[{"name": "x"}]', '["gpt"]'):
                path = Path(tmp) / "models.json"
                path.write_text(text, encoding="utf-8")
                az = Azure(good())
                with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
                    fc.main([*self.ARGS[:-1], str(path)], az=az)
                self.assertIn("models", str(raised.exception.code), text)
                self.assertEqual(az.calls, [], text)

    def test_every_argument_is_required(self):
        for name in ("--subscription", "--account", "--project", "--guardrail", "--private-endpoint", "--endpoint", "--models"):
            args = list(self.ARGS)
            index = args.index(name)
            del args[index:index + 2]
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                fc.main(args, az=Azure(good()))


if __name__ == "__main__":
    unittest.main()
