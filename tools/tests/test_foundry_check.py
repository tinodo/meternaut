import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

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
    """A stand-in for `az`: it answers the GET requests from a table, and remembers every call. A page after the first one is the entry for its address with ?skiptoken=N."""

    def __init__(self, documents, errors=None):
        self.documents, self.errors, self.calls = documents, errors or {}, []

    def __call__(self, arguments):
        self.calls.append(arguments)
        url, _, query = arguments[arguments.index("--url") + 1].partition("?")
        token = re.search(r"skiptoken=(\w+)", query)
        key = f"{url}?skiptoken={token.group(1)}" if token else url
        for tail, text in self.errors.items():
            if key.endswith(tail):
                return 1, "", text
        # the longest matching end wins: /projects/meternaut/connections before /projects/meternaut
        for tail in sorted(self.documents, key=len, reverse=True):
            if key.endswith(tail):
                return 0, json.dumps(self.documents[tail]), ""
        return 1, "", "ERROR: (ResourceNotFound) The resource was not found."


def next_link(tail, token, host=fc.ARM):
    """The nextLink that Azure gives on the page before page `token` of the list at `tail` (a list of the Foundry resource)."""
    return f"{host}/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.CognitiveServices/accounts/{ACCOUNT}{tail}?api-version={fc.API}&$skiptoken={token}"


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

    def test_a_project_that_does_not_report_its_endpoint_is_a_failure_because_the_check_would_say_nothing_otherwise(self):
        for label, change in (("no endpoints at all", lambda d: d["properties"].pop("endpoints")),
                              ("endpoints without the one of the API", lambda d: d["properties"].update(endpoints={"Other": ENDPOINT})),
                              ("an empty endpoint", lambda d: d["properties"]["endpoints"].update({"AI Foundry API": ""})),
                              ("a null endpoint", lambda d: d["properties"]["endpoints"].update({"AI Foundry API": None})),
                              ("no properties", lambda d: d.pop("properties"))):
            found, _ = check(changed(f"/projects/{PROJECT}", change))
            self.assertEqual(failures(found), ["The project does not report its endpoint (properties.endpoints['AI Foundry API']), so the address that the cases app is given cannot be checked"], label)

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

    def test_the_two_shields_of_the_user_input_are_among_the_ones_that_are_read(self):
        self.assertIn(("Jailbreak", "Prompt"), fc.SHIELDS)
        self.assertIn(("Indirect Attack", "Prompt"), fc.SHIELDS)
        self.assertIn(("Indirect Attack", "PostToolCall"), fc.SHIELDS)
        self.assertEqual(len(fc.SHIELDS), 3, "nothing else is required of the guardrail")

    def test_a_policy_as_azure_returns_it_with_the_filters_of_its_base_policy_passes_in_whatever_order(self):
        base = [{"name": name, "severityThreshold": "Medium", "blocking": True, "enabled": True, "source": source} for name in ("Hate", "Sexual", "Selfharm", "Violence")
                for source in ("Prompt", "Completion")]
        base += [{"name": "Protected Material Text", "blocking": False, "enabled": True, "source": "Completion"},
                 {"name": "Jailbreak", "blocking": False, "enabled": False, "source": "Completion"},
                 {"name": "Task Adherence", "blocking": False, "enabled": False, "source": "PreToolCall"}]
        ours = [{"name": "Jailbreak", "source": "Prompt", "enabled": True, "blocking": True}, {"name": "Indirect Attack", "source": "Prompt", "enabled": True, "blocking": True},
                {"name": "Indirect Attack", "source": "PostToolCall", "enabled": True, "blocking": True}]
        for filters in (base + ours, ours + base, [base[0], ours[2], base[1], ours[0], *base[2:], ours[1]]):
            policy = {"name": GUARDRAIL, "properties": {"basePolicyName": "Microsoft.DefaultV2", "mode": "Blocking", "contentFilters": filters}}
            found, _ = check(changed(f"/raiPolicies/{GUARDRAIL}", lambda d: d.update(policy)))
            self.assertEqual(failures(found), [])

    def test_an_entry_that_names_a_shield_and_does_not_block_is_a_failure_even_when_another_entry_for_it_does(self):
        path = f"/raiPolicies/{GUARDRAIL}"
        for index, (name, source) in enumerate(fc.SHIELDS):
            for how, extra in (("not blocking", {"blocking": False}), ("not enabled", {"enabled": False}), ("blocking missing", {"blocking": None})):
                document = changed(path, lambda d, e=extra, n=name, s=source: d["properties"]["contentFilters"].insert(0, {"name": n, "source": s, "enabled": True, "blocking": True, **e}))
                found, _ = check(document)
                self.assertEqual(failures(found), [f"The guardrail does not block {name} at {source}"], f"{name} at {source}: {how}")

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


class Pages(unittest.TestCase):
    """The lists of deployments and connections are read to their end: Azure gives a list in pages and says where the next one is."""

    def paged(self, tail, first, second):
        documents = good()
        documents[tail] = {"value": first, "nextLink": next_link(tail, 2)}
        documents[f"{tail}?skiptoken=2"] = {"value": second}
        return documents

    def test_models_that_are_on_a_second_page_are_not_reported_as_missing(self):
        both = good()["/deployments"]["value"]
        found, az = check(self.paged("/deployments", both[:1], both[1:]))
        self.assertEqual(failures(found), [])
        links = [c[c.index("--url") + 1] for c in az.calls if "skiptoken" in c[c.index("--url") + 1]]
        self.assertEqual(links, [next_link("/deployments", 2)], "the second page is asked for with the address that Azure gave")
        found, _ = check(self.paged("/deployments", both[:1], []))
        self.assertEqual(len(failures(found)), 1, "without the second page a model is missing")
        self.assertIn(f"The deployment {MODELS[1]['name']} is not there", failures(found)[0])

    def test_a_connection_on_a_second_page_is_found_and_two_of_them_in_all_are_a_failure(self):
        other = {"name": "other", "properties": {"category": "AzureOpenAI", "authType": "AAD"}}
        traces = good()["/projects/meternaut/connections"]["value"][0]
        found, _ = check(self.paged(f"/projects/{PROJECT}/connections", [other], [traces]))
        self.assertEqual(failures(found), [])
        found, _ = check(self.paged(f"/projects/{PROJECT}/connections", [traces], [copy.deepcopy(traces)]))
        self.assertEqual(len(failures(found)), 1)
        self.assertIn("found 2", failures(found)[0])

    def test_a_next_link_that_is_not_of_azure_resource_manager_is_not_followed(self):
        both = good()["/deployments"]["value"]
        for link in ("https://evil.example/subscriptions/x?api-version=1&$skiptoken=2", "http://management.azure.com/subscriptions/x?$skiptoken=2",
                     "https://management.azure.com.evil.example/subscriptions/x?$skiptoken=2", "https://management.azure.com@evil.example/subscriptions/x?$skiptoken=2",
                     "management.azure.com/subscriptions/x?$skiptoken=2", 123, ["https://management.azure.com/x"]):
            documents = good()
            documents["/deployments"] = {"value": both[:1], "nextLink": link}
            found, az = check(documents)
            self.assertEqual(len([t for t in failures(found) if "The model deployments could not be read: the list goes on at an address that is not of Azure Resource Manager" in t]), 1, link)
            self.assertEqual([c for c in az.calls if "evil" in " ".join(c) or "skiptoken" in " ".join(c)], [], f"{link!r} is not asked for")

    def test_a_list_that_never_ends_is_given_up_after_the_page_limit(self):
        documents = good()
        documents["/deployments"] = {"value": [], "nextLink": next_link("/deployments", 2)}
        documents["/deployments?skiptoken=2"] = {"value": [], "nextLink": next_link("/deployments", 2)}
        found, az = check(documents)
        self.assertIn(f"The model deployments could not be read: the list has more than {fc.MAX_PAGES} pages", failures(found))
        self.assertEqual(len([c for c in az.calls if "/deployments" in " ".join(c)]), fc.MAX_PAGES)

    def test_a_later_page_that_cannot_be_read_is_a_failure_that_says_so(self):
        both = good()["/deployments"]["value"]
        documents = good()
        documents["/deployments"] = {"value": both, "nextLink": next_link("/deployments", 2)}
        found, _ = check(documents, errors={"/deployments?skiptoken=2": "ERROR: (AuthorizationFailed) The client has no right.\nTraceID 123"})
        self.assertEqual(failures(found), ["The model deployments could not be read: ERROR: (AuthorizationFailed) The client has no right."])
        found, _ = check(documents, errors={"/deployments?skiptoken=2": "ERROR: (ResourceNotFound) gone"})
        self.assertEqual(failures(found), ["The model deployments could not be read: a later page of the list is not there"])


class Timeout(unittest.TestCase):
    """A read that does not answer fails the run with a message, instead of holding the step to the limit of the job."""

    def test_a_read_that_does_not_answer_is_a_failure_and_nothing_more_is_read(self):
        class Slow(Azure):
            def __call__(self, arguments):
                if len(self.calls) == 2:
                    self.calls.append(arguments)
                    raise fc.Stuck("az did not answer within 120 seconds (GET /subscriptions/s/projects/meternaut)")
                return super().__call__(arguments)

        az = Slow(good())
        found = fc.read_back(az, SUBSCRIPTION, GROUP, ACCOUNT, PROJECT, GUARDRAIL, PRIVATE_ENDPOINT, ENDPOINT, MODELS)
        self.assertEqual(len(az.calls), 3, "the third read did not answer, and no fourth was made")
        self.assertEqual(len(found), 5 + 1 + 1)
        self.assertEqual(failures(found), [f"The project {PROJECT} could not be read: az did not answer within 120 seconds (GET /subscriptions/s/projects/meternaut). "
                                           "The read-back stops here: nothing after it was read"])

    def test_the_first_read_that_does_not_answer_leaves_one_line(self):
        class Never:
            calls = 0

            def __call__(self, arguments):
                Never.calls += 1
                raise fc.Stuck("az did not answer within 5 seconds (a request)")

        found = fc.read_back(Never(), SUBSCRIPTION, GROUP, ACCOUNT, PROJECT, GUARDRAIL, PRIVATE_ENDPOINT, ENDPOINT, MODELS)
        self.assertEqual((len(found), Never.calls), (1, 1))
        self.assertIn("az did not answer within 5 seconds", failures(found)[0])

    def test_a_stuck_az_is_stopped_after_the_timeout_with_a_message_that_names_the_request(self):
        with mock.patch.dict(os.environ, {"AZ": sys.executable}):
            started = time.monotonic()
            with self.assertRaises(fc.Stuck) as raised:
                fc.run_az(["-c", "import time; time.sleep(60)", "--url", f"{fc.ARM}/subscriptions/s/x?api-version=1"], timeout=1)
            self.assertLess(time.monotonic() - started, 30, "the program was not waited for")
            self.assertEqual(str(raised.exception), "az did not answer within 1 seconds (GET /subscriptions/s/x)")
            with self.assertRaises(fc.Stuck) as raised:
                fc.run_az(["-c", "import time; time.sleep(60)"], timeout=1)
            self.assertEqual(str(raised.exception), "az did not answer within 1 seconds (a request)")

    def test_an_az_that_answers_in_time_gives_its_answer_and_the_default_is_two_minutes(self):
        with mock.patch.dict(os.environ, {"AZ": sys.executable}):
            code, out, err = fc.run_az(["-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"], timeout=60)
        self.assertEqual((code, out.strip(), err.strip()), (3, "out", "err"))
        self.assertEqual(fc.TIMEOUT_SECONDS, 120)

    def test_the_command_passes_its_timeout_on_to_every_read_and_defaults_to_the_limit_of_the_module(self):
        seen = []

        def recorder(arguments, timeout=None):
            seen.append(timeout)
            return Azure(good())(arguments)

        for extra, expected in (([], fc.TIMEOUT_SECONDS), (["--timeout", "7"], 7)):
            del seen[:]
            with mock.patch.object(fc, "run_az", recorder), contextlib.redirect_stdout(io.StringIO()):
                code = fc.main([*Main.ARGS, *extra])
            self.assertEqual((code, set(seen)), (0, {expected}), extra)
            self.assertGreaterEqual(len(seen), 6)

    def test_the_timeout_is_a_number_of_seconds_of_one_or_more(self):
        for value in ("0", "-5", "soon", "1.5"):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                fc.main([*Main.ARGS, "--timeout", value], az=Azure(good()))

    def test_a_run_whose_read_did_not_answer_exits_1_and_the_summary_says_so(self):
        def stuck(arguments):
            raise fc.Stuck("az did not answer within 120 seconds (GET /subscriptions/s/accounts/a)")

        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = fc.main([*Main.ARGS, "--summary", str(summary)], az=stuck)
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 1)
        self.assertIn("FAILED: The Foundry resource aif-meternaut-agents-0123abcd could not be read: az did not answer within 120 seconds", out.getvalue())
        self.assertIn("1 thing(s) differ", err.getvalue())
        self.assertIn("az did not answer within 120 seconds", text)


if __name__ == "__main__":
    unittest.main()
