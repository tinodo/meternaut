import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1] / "apim-sync.py"
spec = importlib.util.spec_from_file_location("apim_sync", TOOL)
aps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aps)

ROOT = Path(__file__).resolve().parents[2]
APIM = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.ApiManagement/service/apim-test"
ENDPOINT = "https://aif-meternaut-dev-abc123.cognitiveservices.azure.com"
VARS = [f"FOUNDRY_ENDPOINT={ENDPOINT}", "APPINSIGHTS_LOGGER=logger-test"]
IN_ACTIONS = {"GITHUB_ACTIONS": "true"}


class FakeService:
    """The part of the API Management management API that the tool uses, with the shapes the real one answers with."""

    def __init__(self, secrets=None):
        self.objects, self.calls, self.secrets = {}, [], secrets or {}

    def request(self, method, url, body=None, headers=None):
        assert url.startswith(aps.ARM + APIM + "/"), url
        path, _, query = url[len(aps.ARM + APIM) + 1:].partition("?")
        params = dict(p.partition("=")[::2] for p in query.split("&"))
        self.calls.append((method, path, params, body, headers))
        assert params["api-version"] == "2024-05-01"
        if method == "GET":
            if path not in self.objects:
                return 404, {}, b'{"error":{"code":"ResourceNotFound"}}'
            stored = self.objects[path]
            if path.endswith("/policies/policy"):
                return 200, {}, stored.encode("utf-8")
            properties = dict(stored.get("properties", {}))
            for field in ("scope", "loggerId"):
                if field in properties:
                    properties[field] = f"{APIM}{properties[field]}"
            properties["addedByTheService"] = True
            return 200, {}, json.dumps({"id": f"{APIM}/{path}", "name": path.rsplit("/", 1)[-1], "properties": properties}).encode()
        if method == "PUT":
            if path.endswith("/policies/policy"):
                assert body["properties"]["format"] == "rawxml" and body["properties"]["value"].lstrip().startswith("<policies>")
                value = body["properties"]["value"]
            else:
                assert body is None or "properties" in body, path
                value = body or {}
            created = path not in self.objects
            self.objects[path] = value
            return (201 if created else 200), {}, b"{}"
        if method == "DELETE":
            assert (headers or {}).get("If-Match") == "*"
            if path not in self.objects:
                return 404, {}, b"{}"
            for key in [k for k in self.objects if k == path or k.startswith(path + "/")]:
                del self.objects[key]
            return 200, {}, b""
        if method == "POST" and path.endswith("/listSecrets"):
            name = path.split("/")[1]
            if name not in self.secrets:
                return 404, {}, b"{}"
            return 200, {}, json.dumps(self.secrets[name]).encode()
        raise AssertionError(f"unexpected {method} {path}")

    def writes(self):
        return [(m, p) for m, p, *_ in self.calls if m in ("PUT", "DELETE", "POST")]


def run(argv, service, environ=None):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = aps.main(argv, transport=service, environ=environ if environ is not None else IN_ACTIONS)
    return code, out.getvalue(), err.getvalue()


def rows(out, action):
    return sum(1 for line in out.splitlines() if line.startswith(f"{action:<9} "))


def vars_args(extra=()):
    args = [f"--apim={APIM}"]
    for v in VARS:
        args += ["--var", v]
    return args + list(extra)


class Substitution(unittest.TestCase):
    def test_replaces_in_strings_lists_dicts_and_keys(self):
        value = {"a-${X}": ["${X}", {"b": "p-${X}-${Y}"}], "n": 3}
        self.assertEqual(aps.substitute(value, {"X": "1", "Y": "2"}), {"a-1": ["1", {"b": "p-1-2"}], "n": 3})

    def test_a_name_without_a_value_is_an_error_not_an_empty_string(self):
        with self.assertRaises(aps.Problem) as ctx:
            aps.substitute("x ${MISSING} y", {})
        self.assertIn("MISSING", str(ctx.exception))


class Paths(unittest.TestCase):
    def test_our_objects_and_their_known_children_are_allowed(self):
        for path in ("products/meternaut-a", "apis/meternaut-llm", "subscriptions/meternaut-a-sub-01", "backends/meternaut-b",
                     "namedValues/meternaut-n", "apis/meternaut-llm/operations/chat-completions", "apis/meternaut-llm/policies/policy",
                     "apis/meternaut-llm/diagnostics/applicationinsights", "products/meternaut-a/policies/policy",
                     "products/meternaut-a/apis/meternaut-llm"):
            self.assertTrue(aps.allowed_path(path, "meternaut-"), path)

    def test_everything_else_is_refused(self):
        for path in ("", "policies/policy", "apis/other", "apis/meternaut", "products/other-a", "loggers/meternaut-x", "properties/x",
                     "apis/meternaut-llm/policies/other", "apis/meternaut-llm/diagnostics/azuremonitor", "apis/other/operations/x",
                     "products/meternaut-a/policies/policy/extra", "products/meternaut-a/apis/other", "products/other/apis/meternaut-llm",
                     "apis/meternaut-llm/../other", "apis/meternaut-llm/operations/", "tenant/access", "subscriptions/master",
                     "apis/meternaut-llm?x=1", "apis/meternaut-%2e%2e", "Apis/meternaut-llm/operations/x/policies/policy"):
            self.assertFalse(aps.allowed_path(path, "meternaut-"), path)


class Loading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def contract(self, **changes):
        value = {"name": "meternaut-test", "models": ["m1", "m2"], "tokensPerMinute": 100, "tokenQuotaPerMonth": 1000, **changes}
        path = self.dir / "contract.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_the_contract_gives_the_variables(self):
        variables = aps.load_variables(self.contract(), VARS)
        self.assertEqual(variables["CONTRACT"], "meternaut-test")
        self.assertEqual(variables["ALLOWED_MODELS"], "m1,m2")
        self.assertEqual((variables["TOKENS_PER_MINUTE"], variables["TOKEN_QUOTA_PER_MONTH"]), ("100", "1000"))
        self.assertEqual(variables["FOUNDRY_ENDPOINT"], ENDPOINT)

    def test_a_trailing_slash_on_the_endpoint_is_dropped(self):
        variables = aps.load_variables(self.contract(), [f"FOUNDRY_ENDPOINT={ENDPOINT}/"])
        self.assertEqual(variables["FOUNDRY_ENDPOINT"], ENDPOINT)

    def test_an_endpoint_that_is_not_a_model_account_is_refused(self):
        for bad in ("http://aif.cognitiveservices.azure.com", "https://evil.example.com", "https://aif.cognitiveservices.azure.com.evil.com",
                    "https://aif.cognitiveservices.azure.com/openai", "https://user@aif.cognitiveservices.azure.com", "https://x.azure-api.net"):
            with self.assertRaises(aps.Problem, msg=bad):
                aps.load_variables(self.contract(), [f"FOUNDRY_ENDPOINT={bad}"])

    def test_a_value_with_markup_or_quotes_is_refused(self):
        for bad in ('x"y', "x<y", "x&y", "x y", "x'y", "x${Y}"):
            with self.assertRaises(aps.Problem, msg=bad):
                aps.load_variables(self.contract(), [f"APPINSIGHTS_LOGGER={bad}"])
        with self.assertRaises(aps.Problem):
            aps.load_variables(self.contract(models=["a\"b"]), [])

    def test_a_contract_that_is_incomplete_is_refused(self):
        with self.assertRaises(aps.Problem):
            aps.load_variables(self.contract(tokensPerMinute="many"), [])
        with self.assertRaises(aps.Problem):
            aps.load_variables(self.contract(models=[]), [])
        with self.assertRaises(aps.Problem):
            aps.load_variables(self.contract(name=""), [])
        with self.assertRaises(aps.Problem):
            aps.load_variables(self.dir / "missing.json", [])

    def test_a_var_must_be_name_equals_value(self):
        for bad in ("FOUNDRY_ENDPOINT", "lower=1", "=1"):
            with self.assertRaises(aps.Problem, msg=bad):
                aps.load_variables(self.contract(), [bad])

    def manifest(self, objects, prefix="meternaut-"):
        path = self.dir / "manifest.json"
        path.write_text(json.dumps({"apiVersion": "2024-05-01", "prefix": prefix, "objects": objects}), encoding="utf-8")
        return path

    def test_a_manifest_object_outside_the_prefix_is_refused(self):
        for path in ("apis/other", "policies/policy", "loggers/x", "products/meternaut-a/../other"):
            with self.assertRaises(aps.Problem, msg=path):
                aps.load_manifest(self.manifest([{"path": path, "body": {}}]), {})

    def test_the_prefix_must_be_a_word_with_a_hyphen(self):
        for bad in ("", "meternaut", "Meternaut-", "a/b-", "-"):
            with self.assertRaises(aps.Problem, msg=bad):
                aps.load_manifest(self.manifest([], prefix=bad), {})

    def test_a_policy_file_must_live_next_to_the_manifest(self):
        (self.dir.parent / "outside.xml").write_text("<policies/>", encoding="utf-8")
        with self.assertRaises(aps.Problem):
            aps.load_manifest(self.manifest([{"path": "apis/meternaut-a/policies/policy", "policy": "../outside.xml"}]), {})

    def test_the_real_manifest_loads_and_stays_inside_the_prefix(self):
        variables = aps.load_variables(ROOT / "hub" / "contract.json", VARS)
        manifest = aps.load_manifest(ROOT / "hub" / "apim" / "manifest.json", variables)
        paths = [o["path"] for o in manifest["objects"]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all(aps.allowed_path(p, "meternaut-") for p in paths))
        text = json.dumps(manifest)
        self.assertNotIn("${", text)
        self.assertIn(ENDPOINT, text)
        policies = {o["path"]: o["policy"] for o in manifest["objects"] if "policy" in o}
        self.assertEqual(len(policies), 2)
        for xml in policies.values():
            self.assertTrue(xml.lstrip().startswith("<policies>"))
            self.assertEqual(xml.count("<policies>"), xml.count("</policies>"))
            self.assertNotIn("${", xml)

    def test_the_real_policies_say_what_the_contract_says(self):
        variables = aps.load_variables(ROOT / "hub" / "contract.json", VARS)
        manifest = aps.load_manifest(ROOT / "hub" / "apim" / "manifest.json", variables)
        policies = {o["path"].split("/")[0]: o["policy"] for o in manifest["objects"] if "policy" in o}
        product, api = policies["products"], policies["apis"]
        self.assertIn(f'value="{variables["ALLOWED_MODELS"]}"', product)
        self.assertIn(f'tokens-per-minute="{variables["TOKENS_PER_MINUTE"]}"', product)
        self.assertIn(f'token-quota="{variables["TOKEN_QUOTA_PER_MONTH"]}"', product)
        self.assertIn('token-quota-period="Monthly"', product)
        self.assertIn(f'base-url="{ENDPOINT}"', api)
        self.assertIn("https://cognitiveservices.azure.com", api)
        for text in (product, api):
            self.assertIn("<base />", text)
        self.assertIn('exists-action="delete"', api)  # the caller's key does not travel on to the model
        self.assertNotIn("subscription-key", api)


class Wording(unittest.TestCase):
    def test_a_message_never_carries_a_query_string_or_signature(self):
        message = str(aps.Problem("failed https://management.azure.com/x?api-version=1&sig=SECRET and sig=OTHER"))
        self.assertNotIn("SECRET", message)
        self.assertNotIn("OTHER", message)
        self.assertNotIn("api-version", message)


class Covers(unittest.TestCase):
    def test_what_is_wanted_may_be_a_part_of_what_the_service_reports(self):
        self.assertTrue(aps.covers({"a": 1, "l": [{"x": "Y"}]}, {"a": 1, "b": 2, "l": [{"x": "y", "z": 1}]}))
        self.assertTrue(aps.covers({"p": 100}, {"p": 100.0}))

    def test_a_difference_is_seen(self):
        self.assertFalse(aps.covers({"a": 1}, {"a": 2}))
        self.assertFalse(aps.covers({"a": 1}, {}))
        self.assertFalse(aps.covers({"l": [1, 2]}, {"l": [1]}))
        self.assertFalse(aps.covers({"m": True}, {"m": False}))

    def test_only_resource_id_fields_match_on_their_tail(self):
        self.assertTrue(aps.covers({"loggerId": "/loggers/x"}, {"loggerId": f"{APIM}/loggers/x"}))
        self.assertTrue(aps.covers({"scope": "/products/p"}, {"scope": f"{APIM}/products/p"}))
        self.assertFalse(aps.covers({"urlTemplate": "/chat"}, {"urlTemplate": "/v1/chat"}))
        self.assertFalse(aps.covers({"loggerId": "/loggers/x"}, {"loggerId": f"{APIM}/loggers/other"}))


class Service(unittest.TestCase):
    def test_a_first_plan_creates_everything_and_changes_nothing(self):
        service = FakeService()
        code, out, err = run(["plan", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(service.writes(), [])
        self.assertIn("Nothing was changed.", out)
        self.assertNotIn("update", out)
        self.assertEqual(rows(out, "create"), 8)

    def test_apply_writes_every_object_in_order_and_then_the_plan_is_empty(self):
        service = FakeService()
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        written = [p for m, p in service.writes()]
        self.assertEqual(written, [
            "products/meternaut-learning-demo-dev",
            "apis/meternaut-llm",
            "apis/meternaut-llm/operations/chat-completions",
            "products/meternaut-learning-demo-dev/apis/meternaut-llm",
            "apis/meternaut-llm/policies/policy",
            "products/meternaut-learning-demo-dev/policies/policy",
            "subscriptions/meternaut-learning-demo-dev-sub-01",
            "apis/meternaut-llm/diagnostics/applicationinsights",
        ])
        self.assertTrue(all(p.split("/")[-1].startswith("meternaut-") or "/" in p for p in written))
        link = next(c for c in service.calls if c[0] == "PUT" and "/apis/" in c[1] and c[1].startswith("products/"))
        self.assertIsNone(link[3])  # the link has no body
        api = service.objects["apis/meternaut-llm"]["properties"]
        self.assertEqual(api["serviceUrl"], ENDPOINT)
        self.assertEqual(api["subscriptionKeyParameterNames"], {"header": "api-key"})
        self.assertTrue(api["subscriptionRequired"])
        diag = service.objects["apis/meternaut-llm/diagnostics/applicationinsights"]["properties"]
        self.assertEqual(diag["loggerId"], "/loggers/logger-test")
        self.assertTrue(diag["metrics"])
        self.assertNotIn("request", diag)  # no bodies are logged
        self.assertNotIn("response", diag)

        service.calls.clear()
        code, out, err = run(["plan", *vars_args()], service)
        self.assertEqual(code, 0)
        self.assertEqual(rows(out, "unchanged"), 8, out)
        self.assertEqual(service.writes(), [])

    def test_a_changed_object_shows_as_an_update(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        service.objects["apis/meternaut-llm"]["properties"]["subscriptionRequired"] = False
        service.objects["products/meternaut-learning-demo-dev/policies/policy"] = "<policies><inbound><base /></inbound></policies>"
        code, out, _ = run(["plan", *vars_args()], service)
        self.assertEqual(code, 0)
        self.assertIn("update    apis/meternaut-llm\n", out)
        self.assertIn("update    products/meternaut-learning-demo-dev/policies/policy", out)
        self.assertEqual(rows(out, "unchanged"), 6)

    def test_whitespace_alone_is_not_a_policy_change(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        path = "apis/meternaut-llm/policies/policy"
        service.objects[path] = "\n".join(line.strip() for line in service.objects[path].splitlines())
        code, out, _ = run(["plan", *vars_args()], service)
        self.assertEqual(code, 0)
        self.assertEqual(rows(out, "unchanged"), 8, out)

    def test_policies_are_read_as_raw_xml(self):
        service = FakeService()
        run(["plan", *vars_args()], service)
        reads = [c for c in service.calls if c[1].endswith("/policies/policy")]
        self.assertEqual(len(reads), 2)
        self.assertTrue(all(c[2].get("format") == "rawxml" for c in reads))

    def test_apply_stops_at_the_first_refusal(self):
        service = FakeService()
        real = service.request

        def refuse(method, url, body=None, headers=None):
            if method == "PUT" and "/policies/policy" in url and "/apis/" in url:
                return 400, {}, b'{"error":{"message":"Policy is invalid"}}'
            return real(method, url, body, headers)

        service.request = refuse
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual(code, 2)
        self.assertIn("400", err)
        self.assertIn("Policy is invalid", err)
        self.assertNotIn("subscriptions/", "".join(p for m, p in service.writes()))

    def test_remove_deletes_only_what_the_manifest_names_in_reverse_order(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        service.objects["apis/other-team-api"] = {"properties": {}}
        service.objects["products/other-team-product"] = {"properties": {}}
        service.calls.clear()
        code, out, err = run(["remove", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        deleted = [(p, params) for m, p, params, *_ in service.calls if m == "DELETE"]
        self.assertEqual([p for p, _ in deleted], [
            "apis/meternaut-llm/diagnostics/applicationinsights",
            "subscriptions/meternaut-learning-demo-dev-sub-01",
            "products/meternaut-learning-demo-dev/apis/meternaut-llm",
            "apis/meternaut-llm/operations/chat-completions",
            "apis/meternaut-llm",
            "products/meternaut-learning-demo-dev",
        ])
        self.assertEqual(dict(deleted)["products/meternaut-learning-demo-dev"].get("deleteSubscriptions"), "true")
        self.assertEqual(dict(deleted)["apis/meternaut-llm"].get("deleteRevisions"), "true")
        self.assertEqual(sorted(service.objects), ["apis/other-team-api", "products/other-team-product"])

    def test_remove_twice_reports_absent_and_succeeds(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        run(["remove", *vars_args()], service)
        code, out, err = run(["remove", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(rows(out, "absent"), 6)
        self.assertEqual(service.objects, {})

    def test_apply_and_remove_run_only_from_github_actions(self):
        for command in ("apply", "remove"):
            service = FakeService()
            for environ in ({}, {"GITHUB_ACTIONS": "false"}, {"GITHUB_ACTIONS": ""}):
                code, out, err = run([command, *vars_args()], service, environ=environ)
                self.assertEqual(code, 2)
                self.assertIn("rule 18", err)
                self.assertEqual(service.calls, [])
        service = FakeService()
        self.assertEqual(run(["plan", *vars_args()], service, environ={})[0], 0)

    def test_the_variables_the_policies_need_must_be_given(self):
        service = FakeService()
        code, out, err = run(["plan", f"--apim={APIM}", "--var", f"FOUNDRY_ENDPOINT={ENDPOINT}"], service)
        self.assertEqual(code, 2)
        self.assertIn("APPINSIGHTS_LOGGER", err)
        self.assertEqual(service.calls, [])

    def test_the_instance_must_be_given_as_a_resource_id(self):
        for bad in ("apim-test", "/subscriptions/x/resourceGroups/rg/providers/Microsoft.ApiManagement/service/a",
                    APIM + "/apis", APIM.replace("Microsoft.ApiManagement", "Microsoft.Web")):
            service = FakeService()
            code, _, err = run(["plan", f"--apim={bad}", *VARS_AS_ARGS], service)
            self.assertEqual(code, 2, bad)
            self.assertEqual(service.calls, [])


VARS_AS_ARGS = ["--var", VARS[0], "--var", VARS[1]]


class Key(unittest.TestCase):
    SECRET = "k" * 32

    def test_the_key_of_the_contract_is_printed_and_nothing_else(self):
        service = FakeService(secrets={"meternaut-learning-demo-dev-sub-01": {"primaryKey": self.SECRET, "secondaryKey": "s" * 32}})
        code, out, err = run(["key", f"--apim={APIM}"], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, self.SECRET + "\n")
        self.assertEqual([(m, p) for m, p, *_ in service.calls], [("POST", "subscriptions/meternaut-learning-demo-dev-sub-01/listSecrets")])

    def test_the_key_is_never_read_for_a_subscription_that_is_not_ours(self):
        service = FakeService(secrets={"master": {"primaryKey": "x"}})
        with self.assertRaises(aps.Problem):
            aps.contract_key(aps.Apim(service, APIM, "2024-05-01"), "master", "meternaut-")
        with self.assertRaises(aps.Problem):
            aps.contract_key(aps.Apim(service, APIM, "2024-05-01"), "meternaut-a/../master", "meternaut-")
        self.assertEqual(service.calls, [])

    def test_a_missing_key_is_a_clean_error_without_the_response(self):
        service = FakeService()
        code, out, err = run(["key", f"--apim={APIM}"], service)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("404", err)


class Network(unittest.TestCase):
    def transport(self, answers):
        """A Transport whose opener is scripted: each answer is a response, or an HTTPError to raise."""
        t = aps.Transport(token_command=["token"], sleep=lambda s: self.sleeps.append(s), attempts=4)
        t._token = "TOKEN"
        self.sent = []
        queue = list(answers)

        def open_(request, timeout=None):
            self.sent.append(request)
            answer = queue.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        t._opener = mock.Mock(open=open_)
        return t

    def setUp(self):
        self.sleeps = []

    @staticmethod
    def response(status=200, data=b"{}"):
        r = mock.MagicMock()
        r.status, r.headers, r.read.return_value = status, {}, data
        r.__enter__.return_value = r
        return r

    @staticmethod
    def http_error(code, headers=None):
        return urllib.error.HTTPError("https://management.azure.com/x", code, "x", headers or {}, io.BytesIO(b"{}"))

    def test_a_get_has_no_body_and_a_post_or_put_without_one_says_so(self):
        t = self.transport([self.response()] * 3)
        t.request("GET", aps.ARM + "/x")
        t.request("POST", aps.ARM + "/x")
        t.request("PUT", aps.ARM + "/x")
        self.assertIsNone(self.sent[0].data)
        self.assertEqual(self.sent[1].data, b"")
        self.assertEqual(self.sent[2].data, b"")
        self.assertIsNone(self.sent[1].get_header("Content-type"))

    def test_a_body_is_sent_as_json(self):
        t = self.transport([self.response()])
        t.request("PUT", aps.ARM + "/x", {"properties": {"a": 1}})
        self.assertEqual(json.loads(self.sent[0].data), {"properties": {"a": 1}})
        self.assertEqual(self.sent[0].get_header("Content-type"), "application/json")
        self.assertEqual(self.sent[0].get_header("Authorization"), "Bearer TOKEN")

    def test_the_token_goes_to_the_management_host_only(self):
        t = self.transport([self.response()])
        for url in ("https://evil.example.com/x", "http://management.azure.com/x", aps.ARM + ".evil.com/x", "https://management.azure.com@evil.com/x"):
            with self.assertRaises(aps.Problem, msg=url):
                t.request("GET", url)
        self.assertEqual(self.sent, [])

    def test_a_redirect_is_not_followed(self):
        handler = aps._NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example.com"))

    def test_throttling_and_server_errors_are_retried_with_the_wait_the_service_names(self):
        t = self.transport([self.http_error(429, {"Retry-After": "7"}), self.http_error(503), self.response(200, b"ok")])
        status, _, data = t.request("GET", aps.ARM + "/x")
        self.assertEqual((status, data), (200, b"ok"))
        self.assertEqual(self.sleeps, [7.0, 4.0])

    def test_a_client_error_is_returned_not_retried(self):
        t = self.transport([self.http_error(403)])
        status, _, _ = t.request("GET", aps.ARM + "/x")
        self.assertEqual(status, 403)
        self.assertEqual(len(self.sent), 1)

    def test_the_last_attempt_returns_what_the_service_said(self):
        t = self.transport([self.http_error(503)] * 4)
        status, _, _ = t.request("GET", aps.ARM + "/x")
        self.assertEqual(status, 503)
        self.assertEqual(len(self.sent), 4)

    def test_an_unreachable_host_is_a_clean_error_without_the_query(self):
        t = self.transport([urllib.error.URLError("no route")])
        with self.assertRaises(aps.Problem) as ctx:
            t.request("GET", aps.ARM + "/x?api-version=1&sig=SECRET")
        self.assertNotIn("SECRET", str(ctx.exception))
        self.assertNotIn("api-version", str(ctx.exception))

    def test_no_token_from_the_cli_is_a_clear_message(self):
        t = aps.Transport(token_command=["token"])
        with mock.patch.object(aps.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="", stderr="boom")):
            with self.assertRaises(aps.Problem) as ctx:
                t.token()
        self.assertIn("azure/login", str(ctx.exception))
        self.assertNotIn("boom", str(ctx.exception))

    def test_the_token_is_asked_for_once(self):
        t = aps.Transport(token_command=["token"])
        with mock.patch.object(aps.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="T\n", stderr="")) as run_:
            self.assertEqual((t.token(), t.token()), ("T", "T"))
        self.assertEqual(run_.call_count, 1)


class Errors(unittest.TestCase):
    def test_an_unset_repository_variable_is_an_error_not_an_empty_value(self):
        for empty in ("APPINSIGHTS_LOGGER=", "APPINSIGHTS_LOGGER=  ", "FOUNDRY_ENDPOINT="):
            service = FakeService()
            name = empty.split("=")[0]
            other = [v for v in VARS if not v.startswith(name)]
            args = [f"--apim={APIM}", "--var", empty] + [x for v in other for x in ("--var", v)]
            code, _, err = run(["plan", *args], service)
            self.assertEqual(code, 2, empty)
            self.assertIn(name, err)
            self.assertEqual(service.calls, [])
    def test_a_missing_manifest_or_contract_is_a_clean_error(self):
        service = FakeService()
        code, _, err = run(["plan", *vars_args(["--contract=C:/does/not/exist.json"])], service)
        self.assertEqual(code, 2)
        self.assertIn("exist.json", err)
        code, _, err = run(["plan", *vars_args(["--manifest=C:/does/not/exist.json"])], service)
        self.assertEqual(code, 2)
        self.assertEqual(service.calls, [])


if __name__ == "__main__":
    unittest.main()
