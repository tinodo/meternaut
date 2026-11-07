"""The read-back of the project's connection to the AI Gateway (tools/foundry-check.py with --ai-gateway-host and --connection), step 2 of docs/proposals/08-ai-gateway.md.

The stand-in for `az` answers GET requests from a table; no test calls Azure. The connection is held to what environment/foundry/main.bicep writes, and nothing of an answer is printed but fixed words,
the names of the models, a few plain values and the names of credentials, never their values."""
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
spec = importlib.util.spec_from_file_location("foundry_check_of_the_agents_route", ROOT / "tools" / "foundry-check.py")
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)
# The helpers of the tests of the tool itself: the answers of a Foundry resource that is as its template says, and the stand-in for az.
helpers_spec = importlib.util.spec_from_file_location("test_foundry_check_helpers", ROOT / "tools" / "tests" / "test_foundry_check.py")
helpers = importlib.util.module_from_spec(helpers_spec)
helpers_spec.loader.exec_module(helpers)

HOST = "aigw-meternaut-0123abcd.swedencentral.ai.gateway.azure.com"
CONNECTION = "aigateway"
MODELS = helpers.MODELS
SECRET = "SECRET-VALUE-0123456789"
PATH = f"/projects/{helpers.PROJECT}/connections/{CONNECTION}"


def connection():
    """What Azure answers for the connection as the template writes it (it never returns a secret)."""
    return {"name": CONNECTION, "properties": {
        "category": "ApiManagement", "authType": "ProjectManagedIdentity", "audience": "https://azure-api.net/aigateway", "isSharedToAll": False,
        "target": f"https://{HOST}/default/models/openai/v1", "credentials": {},
        "metadata": {"deploymentInPath": "false", "models": json.dumps(
            [{"name": m["name"], "properties": {"model": {"name": m["name"], "version": m["version"], "format": "OpenAI"}}} for m in MODELS], separators=(",", ":"))}}}


def documents(**changes):
    document = helpers.good()
    document[PATH] = connection()
    return {**document, **changes}


def read(docs=None, errors=None, host=HOST):
    az = helpers.Azure(docs if docs is not None else documents(), errors)
    found = fc.read_back(az, helpers.SUBSCRIPTION, helpers.GROUP, helpers.ACCOUNT, helpers.PROJECT, helpers.GUARDRAIL, helpers.PRIVATE_ENDPOINT, helpers.ENDPOINT, MODELS, host, CONNECTION if host else "")
    return found, az


def failures(found):
    return [text for ok, text in found if not ok]


def altered(change):
    document = copy.deepcopy(connection())
    change(document["properties"])
    return documents(**{PATH: document})


class TheConnectionIsReadBackAndHeldToTheTemplate(unittest.TestCase):
    def test_a_connection_as_the_template_writes_it_passes_and_the_other_checks_are_still_made(self):
        found, az = read()
        self.assertEqual(failures(found), [])
        plain_found, _ = helpers.check()
        self.assertEqual(len(found), len(plain_found) + 7, "the seven things of the connection, and the same ones as before")
        self.assertEqual(found[:len(plain_found)], plain_found)
        text = "\n".join(t for _, t in found[len(plain_found):])
        for words in ("of the category ApiManagement and authenticates with the project's own identity (ProjectManagedIdentity)", "audience is https://azure-api.net/aigateway",
                      "target is the gateway's host with the path /default/models/openai/v1", "holds no credentials: the project's identity is the credential",
                      "not shared with the other projects of the resource", "the model is sent in the body", "lists the models gpt-6-luna, gpt-6.1-sol: each named by its alias"):
            self.assertIn(words.lower(), text.lower(), words)

    def test_it_reads_the_connection_with_a_get_of_its_own_and_only_reads(self):
        _, az = read()
        urls = [c[c.index("--url") + 1] for c in az.calls]
        mine = [u for u in urls if u.split("?")[0].endswith(PATH)]
        self.assertEqual(len(mine), 1)
        self.assertTrue(mine[0].endswith(f"{PATH}?api-version=2026-09-01"), "the version of the connection for traces and of the template")
        for call in az.calls:
            self.assertEqual(call[:3], ["rest", "--method", "get"])
            for word in ("--method post", "--method put", "--method patch", "--method delete", "listsecrets", "listkeys"):
                self.assertNotIn(word, " ".join(call).lower())

    def test_without_a_host_the_connection_is_not_read_and_nothing_is_different(self):
        found, az = read(host="")
        self.assertEqual(found, helpers.check()[0])
        self.assertFalse([c for c in az.calls if "/connections/" in " ".join(c)], "the connection of the gateway is looked for only when the switch is on")

    def test_a_connection_that_is_not_there_is_a_failure_that_says_so(self):
        docs = helpers.good()
        found, _ = read(docs)
        self.assertEqual(failures(found), [f"The connection {CONNECTION} to the AI Gateway is not there"])

    def test_a_read_that_fails_is_a_failure_and_the_error_is_its_first_line(self):
        found, _ = read(errors={PATH: "ERROR: (InternalServerError) try again later\nsecond line"})
        self.assertEqual(failures(found), [f"The connection {CONNECTION} to the AI Gateway could not be read: ERROR: (InternalServerError) try again later"])

    def test_each_property_that_it_rests_on_is_a_failure_when_it_differs_and_one_failure_each(self):
        cases = (
            ("category", lambda p: p.update(category="ModelGateway"), "differs from its template: its category is ModelGateway"),
            ("authentication", lambda p: p.update(authType="ApiKey"), "its authentication ApiKey, not ApiManagement and ProjectManagedIdentity"),
            ("authentication of another name", lambda p: p.update(authType="AAD"), "its authentication AAD"),
            ("audience", lambda p: p.update(audience="https://cognitiveservices.azure.com"), "audience is not https://azure-api.net/aigateway: the service reports https://cognitiveservices.azure.com"),
            ("audience missing", lambda p: p.pop("audience"), "the service reports none"),
            ("target host", lambda p: p.update(target="https://evil.example.com/default/models/openai/v1"), "not on the gateway's host"),
            ("target scheme", lambda p: p.update(target=f"http://{HOST}/default/models/openai/v1"), "not on the gateway's host"),
            ("target port", lambda p: p.update(target=f"https://{HOST}:8443/default/models/openai/v1"), "not on the gateway's host"),
            ("target user", lambda p: p.update(target=f"https://user@{HOST}/default/models/openai/v1"), "not on the gateway's host"),
            ("target path", lambda p: p.update(target=f"https://{HOST}/default/models/openai"), "its path is /default/models/openai, and it has to be /default/models/openai/v1"),
            ("target query", lambda p: p.update(target=f"https://{HOST}/default/models/openai/v1?x=1"), "its path is /default/models/openai/v1 with a query or a fragment, and it has to be"),
            ("target missing", lambda p: p.pop("target"), "has no target"),
            ("shared", lambda p: p.update(isSharedToAll=True), "shared with every project"),
            ("deploymentInPath", lambda p: p["metadata"].update(deploymentInPath="true"), "deploymentInPath is true, and it has to be false"),
            ("deploymentInPath missing", lambda p: p["metadata"].pop("deploymentInPath"), "deploymentInPath is not set"),
            ("models missing", lambda p: p["metadata"].pop("models"), "lists no models that can be read"),
            ("models not json", lambda p: p["metadata"].update(models="not json"), "lists no models that can be read"),
        )
        for label, change, words in cases:
            with self.subTest(label=label):
                found, _ = read(altered(change))
                self.assertEqual(len(failures(found)), 1, (label, failures(found)))
                self.assertIn(words, failures(found)[0], label)

    def test_the_models_are_held_to_models_json_by_alias_version_format_and_count(self):
        def models_of(entries):
            return lambda p: p["metadata"].update(models=json.dumps(entries))

        def entry(m, **model):
            return {"name": m["name"], "properties": {"model": {"name": m["name"], "version": m["version"], "format": "OpenAI", **model}}}

        for label, entries, words in (
                ("one missing", [entry(MODELS[0])], f"missing {MODELS[1]['name']}"),
                ("another version", [entry(MODELS[0], version="1999-01-01"), entry(MODELS[1])], f"another model or version for {MODELS[0]['name']}"),
                ("another format", [entry(MODELS[0]), entry(MODELS[1], format="Anthropic")], f"another model or version for {MODELS[1]['name']}"),
                ("another model name", [entry(MODELS[0]), entry(MODELS[1], name="other")], f"another model or version for {MODELS[1]['name']}"),
                ("an extra model", [entry(MODELS[0]), entry(MODELS[1]), {"name": "extra-model", "properties": {"model": {"name": "extra-model", "version": "x", "format": "OpenAI"}}}],
                 "not an alias of the gateway: extra-model"),
                ("a model twice", [entry(MODELS[0]), entry(MODELS[1]), entry(MODELS[1])], "a model is listed twice")):
            with self.subTest(label=label):
                found, _ = read(altered(models_of(entries)))
                self.assertEqual(len(failures(found)), 1, (label, failures(found)))
                self.assertIn(words, failures(found)[0], label)
        found, _ = read(altered(lambda p: p["metadata"].update(models=[entry(m) for m in MODELS])))
        self.assertEqual(failures(found), [], "a service that returns the list as a list and not as text is read too")

    def test_credentials_that_hold_anything_fail_and_only_their_names_are_printed(self):
        for credentials in ({"key": SECRET}, {"key": SECRET, "clientSecret": SECRET}, [SECRET], SECRET, {"a": {"b": SECRET}}):
            with self.subTest(credentials=type(credentials).__name__):
                found, _ = read(altered(lambda p: p.update(credentials=credentials)))
                (failure,) = failures(found)
                self.assertIn("holds credentials", failure)
                self.assertIn("No key is used by this project (AGENTS.md rule 23)", failure)
                self.assertNotIn(SECRET, "\n".join(t for _, t in found))
        for fine in (None, {}):
            found, _ = read(altered(lambda p: p.update(credentials=fine)))
            self.assertEqual(failures(found), [], "an empty object and no property are what a connection with no key has")
        found, _ = read(altered(lambda p: p.pop("credentials")))
        self.assertEqual(failures(found), [])

    def test_no_value_of_an_answer_is_printed_that_the_tool_does_not_check_and_a_hostile_one_is_made_harmless(self):
        hostile = "x\n::error::injected `` ##[group] " + SECRET
        found, _ = read(altered(lambda p: p.update(category=hostile, authType=hostile, audience=hostile, target=hostile)))
        for ok, text in found:
            self.assertNotIn("::error::", text)
            self.assertNotIn("##[", text)
            self.assertNotIn("`", text)
            self.assertNotIn("\n", text)
        self.assertLessEqual(max(len(t) for _, t in found), 400)

    def test_metadata_and_the_other_properties_that_a_service_may_return_are_never_printed(self):
        def change(p):
            p["metadata"]["note"] = SECRET
            p["secretsHint"] = SECRET
            p["credentials"] = {"key": SECRET}
        found, _ = read(altered(change))
        self.assertNotIn(SECRET, "\n".join(t for _, t in found))

    def test_a_read_of_azure_that_does_not_answer_in_time_stops_the_rest_and_says_so(self):
        class Slow(helpers.Azure):
            def __call__(self, arguments):
                if arguments[arguments.index("--url") + 1].split("?")[0].endswith(PATH):
                    raise fc.Stuck("az did not answer within 120 seconds (GET /x)")
                return super().__call__(arguments)

        az = Slow(documents())
        found = fc.read_back(az, helpers.SUBSCRIPTION, helpers.GROUP, helpers.ACCOUNT, helpers.PROJECT, helpers.GUARDRAIL, helpers.PRIVATE_ENDPOINT, helpers.ENDPOINT, MODELS, HOST, CONNECTION)
        self.assertEqual(len(failures(found)), 1)
        self.assertIn("could not be read: az did not answer within 120 seconds", failures(found)[0])


class TheCommandLine(unittest.TestCase):
    def run_main(self, *extra, docs=None):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            out, err = io.StringIO(), io.StringIO()
            az = helpers.Azure(docs if docs is not None else documents())
            arguments = ["read-back", "--subscription", helpers.SUBSCRIPTION, "--resource-group", helpers.GROUP, "--account", helpers.ACCOUNT, "--project", helpers.PROJECT,
                         "--guardrail", helpers.GUARDRAIL, "--private-endpoint", helpers.PRIVATE_ENDPOINT, "--endpoint", helpers.ENDPOINT, "--models", str(helpers.MODELS_FILE),
                         "--summary", str(summary), *extra]
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = fc.main(arguments, az=az)
                except SystemExit as raised:
                    code = raised.code
            return code, out.getvalue(), err.getvalue(), summary.read_text(encoding="utf-8") if summary.exists() else ""

    def test_with_the_host_and_the_name_the_connection_is_read_and_the_summary_has_its_lines_and_no_host(self):
        code, out, err, summary = self.run_main("--ai-gateway-host", HOST, "--connection", CONNECTION)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("ok: The connection aigateway to the AI Gateway is of the category ApiManagement", out)
        self.assertIn("The connection aigateway to the AI Gateway is of the category ApiManagement", summary)
        self.assertNotIn(HOST, out + summary, "the host name is not printed")

    def test_a_connection_that_differs_fails_the_run_and_nothing_is_repaired(self):
        code, out, err, _ = self.run_main("--ai-gateway-host", HOST, "--connection", CONNECTION, docs=altered(lambda p: p.update(authType="ApiKey", credentials={"key": SECRET})))
        self.assertEqual(code, 1)
        self.assertIn("FAILED: The connection aigateway differs from its template", out)
        self.assertIn("The run fails; nothing is repaired from here.", err)
        self.assertNotIn(SECRET, out + err)

    def test_without_them_the_run_is_what_it_was_and_the_connection_is_not_asked_for(self):
        code, out, err, _ = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("AI Gateway", out)

    def test_the_host_and_the_name_go_together_and_are_checked(self):
        for extra in (("--ai-gateway-host", HOST), ("--connection", CONNECTION), ("--ai-gateway-host", "evil.example.com", "--connection", CONNECTION),
                      ("--ai-gateway-host", HOST, "--connection", "a b"), ("--ai-gateway-host", HOST, "--connection", "x")):
            with self.subTest(extra=extra):
                code, out, err, _ = self.run_main(*extra)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertRegex(err, r"--ai-gateway-host|--connection")

    def test_the_tool_holds_no_word_of_a_key(self):
        source = re.sub(r"(?m)^\s*#.*$", "", (ROOT / "tools" / "foundry-check.py").read_text(encoding="utf-8"))
        for word in ("listKeys", "listSecrets", "primaryKey", "AccountKey", "SharedAccessKey", "--method post", "--method put"):
            self.assertNotIn(word, source, word)


if __name__ == "__main__":
    unittest.main()
