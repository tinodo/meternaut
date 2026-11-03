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
    """The part of the API Management management API that the tool uses, with the shapes the real one answers with.

    It also keeps the service's rules that the tool has to honour: an update needs If-Match, a product that
    still has subscriptions cannot be deleted unless the caller says to delete them too, a write that is
    only accepted (202) shows up later, deleting an API may only be accepted (202) and take a while, and the
    link between a product and an API has HEAD, PUT and DELETE only (a GET is a 405, and it takes no If-Match):
    the first real read of it, on the real instance, found that out.
    """

    def __init__(self, secrets=None, async_paths=(), ready_after=2, states=None, async_deletes=(), delete_missing_204=False):
        self.objects, self.calls, self.secrets = {}, [], secrets or {}
        self.async_paths, self.ready_after = set(async_paths), ready_after
        self.async_deletes, self.deleting = set(async_deletes), {}
        self.delete_missing_204 = delete_missing_204  # the real service answers 204, not 404, to a DELETE of what is not there
        self.states = {path: list(script) for path, script in (states or {}).items()}  # provisioningState of successive reads
        self.pending, self.polls, self.slept = {}, {}, []

    def sleep(self, seconds):
        self.slept.append(seconds)

    def _remove(self, path):
        for key in [k for k in self.objects if k == path or k.startswith(path + "/")]:
            del self.objects[key]

    def request(self, method, url, body=None, headers=None):
        assert url.startswith(aps.ARM + APIM + "/"), url
        path, _, query = url[len(aps.ARM + APIM) + 1:].partition("?")
        params = dict(p.partition("=")[::2] for p in query.split("&"))
        self.calls.append((method, path, params, body, headers))
        assert params["api-version"] == "2024-05-01"
        link = bool(aps.LINK.fullmatch(path))
        if link and method == "GET":
            return 405, {}, b'{"Message":"The requested resource does not support http method \'GET\'."}'
        if link and method == "HEAD":
            return (204, {}, b"") if path in self.objects else (404, {}, b"")
        assert method != "HEAD", f"the reference defines HEAD only for the link, not for {path}"
        if method == "GET":
            if path in self.pending:
                self.polls[path] = self.polls.get(path, 0) + 1
                if self.polls[path] <= self.ready_after:
                    return 404, {}, b'{"error":{"code":"ResourceNotFound"}}'
                self.objects[path] = self.pending.pop(path)
            if path in self.deleting:
                if self.deleting[path] <= 0:
                    self._remove(path)
                    del self.deleting[path]
                else:
                    self.deleting[path] -= 1
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
            script = self.states.get(path)
            properties["provisioningState"] = (script.pop(0) if len(script) > 1 else script[0]) if script else "Succeeded"
            return 200, {}, json.dumps({"id": f"{APIM}/{path}", "name": path.rsplit("/", 1)[-1], "properties": properties}).encode()
        if method == "PUT":
            if path.endswith("/policies/policy"):
                assert body["properties"]["format"] == "rawxml" and body["properties"]["value"].lstrip().startswith("<policies>")
                value = body["properties"]["value"]
            else:
                assert body is None or "properties" in body, path
                value = body or {}
            exists = path in self.objects
            if exists and body is not None and (headers or {}).get("If-Match") != "*":
                return 412, {}, b'{"error":{"code":"PreconditionFailed","message":"If-Match is required to update an entity"}}'
            if path in self.async_paths and not exists:
                self.pending[path] = value
                return 202, {}, b"{}"
            self.objects[path] = value
            return (200 if exists else 201), {}, b"{}"
        if method == "DELETE":
            if link:
                assert "If-Match" not in (headers or {}), "the reference defines no If-Match for the link"
            else:
                assert (headers or {}).get("If-Match") == "*"
            if path not in self.objects:
                return (204 if self.delete_missing_204 else 404), {}, b"{}"
            if path.startswith("products/") and "/" not in path[len("products/"):]:
                using = [p for p, v in self.objects.items() if p.startswith("subscriptions/") and v["properties"].get("scope") == f"/{path}"]
                if using and params.get("deleteSubscriptions") != "true":
                    return 409, {}, b'{"error":{"code":"Conflict","message":"The product has subscriptions"}}'
                for p in using:
                    del self.objects[p]
            if path in self.async_deletes:
                self.deleting[path] = self.ready_after
                return 202, {}, b"{}"
            self._remove(path)
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
        for path in ("", "policies/policy", "apis/other", "apis/meternaut", "apis/meternaut-", "products/meternaut-", "subscriptions/meternaut-",
                     "products/other-a", "loggers/meternaut-x", "properties/x",
                     "apis/meternaut-llm/policies/other", "apis/meternaut-llm/diagnostics/azuremonitor", "apis/other/operations/x",
                     "products/meternaut-a/policies/policy/extra", "products/meternaut-a/apis/other", "products/other/apis/meternaut-llm",
                     "apis/meternaut-llm/../other", "apis/meternaut-llm/operations/", "tenant/access", "subscriptions/master",
                     "apis/meternaut-llm?x=1", "apis/meternaut-llm#x", "apis/meternaut-%2e%2e", "Apis/meternaut-llm/operations/x/policies/policy"):
            self.assertFalse(aps.allowed_path(path, "meternaut-"), path)

    def test_the_prefix_is_a_constant_of_the_tool(self):
        self.assertEqual(aps.PREFIX, "meternaut-")
        self.assertTrue(aps.allowed_path("apis/meternaut-llm"))
        self.assertFalse(aps.allowed_path("apis/otherteam-gateway"))


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

    def test_the_manifests_prefix_is_the_tools_own_and_cannot_be_another(self):
        for bad in ("", "meternaut", "Meternaut-", "a/b-", "-", "otherteam-", "another-", "meternaut-x-"):
            with self.assertRaises(aps.Problem, msg=bad):
                aps.load_manifest(self.manifest([{"path": "apis/otherteam-gateway", "body": {}}], prefix=bad), {})
        with self.assertRaises(aps.Problem):  # an object of another team under their own prefix, as the manifest would declare it
            aps.load_manifest(self.manifest([{"path": "apis/otherteam-gateway", "body": {}}], prefix="otherteam-"), {})
        with self.assertRaises(aps.Problem):  # and the key of one of their subscriptions
            aps.manifest_header(self.manifest([], prefix="otherteam-"))
        self.assertEqual(aps.manifest_header(self.manifest([]))[1], "meternaut-")

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

    def test_the_real_policies_refuse_before_they_count_and_before_they_route(self):
        variables = aps.load_variables(ROOT / "hub" / "contract.json", VARS)
        manifest = aps.load_manifest(ROOT / "hub" / "apim" / "manifest.json", variables)
        policies = {o["path"].split("/")[0]: o["policy"] for o in manifest["objects"] if "policy" in o}
        product, api = policies["products"], policies["apis"]
        # contract: read the request, refuse a model that is not allowed and streaming, and only then count tokens
        order = [product.index(x) for x in ('name="requestedModel"', 'name="streamRequested"', "model_not_allowed", "streaming_not_supported", "<llm-token-limit")]
        self.assertEqual(order, sorted(order), "the contract refuses before the token limiter counts")
        self.assertIn("JTokenType.String", product)  # a model that is not a string is no model
        self.assertIn('code="403"', product)
        self.assertIn('code="400"', product)
        self.assertIn('estimate-prompt-tokens="false"', product)  # the limiter counts what the model reports
        # API: fails closed for a key that never ran the contract's policy, before anything is routed or authenticated
        gate = api.index("model_not_allowed")
        for later in ("<set-backend-service", "<rewrite-uri", "<authentication-managed-identity", "<llm-emit-token-metric"):
            self.assertLess(gate, api.index(later), later)
        self.assertIn('GetValueOrDefault<string>("requestedModel", string.Empty)', api)
        self.assertIn('GetValueOrDefault<string>("allowedModels", string.Empty)', api)
        self.assertIn("requested.Length == 0", api)
        self.assertNotIn("<set-body>@", api)  # nothing of the request is echoed back
        self.assertNotIn("log-to-eventhub", api + product)


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

    def test_a_second_apply_writes_nothing(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        service.calls.clear()
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(service.writes(), [])
        self.assertEqual(rows(out, "unchanged"), 8, out)

    def test_apply_writes_only_what_the_plan_shows_and_an_update_carries_if_match(self):
        first = FakeService()
        run(["apply", *vars_args()], first)
        self.assertEqual(rows(run(["plan", *vars_args()], first)[1], "unchanged"), 8)
        creates = [h for m, _, _, _, h in first.calls if m == "PUT"]
        self.assertEqual(len(creates), 8)
        self.assertTrue(all(h is None for h in creates), "a new object is written without If-Match")

        service = FakeService()
        run(["apply", *vars_args()], service)
        service.objects["apis/meternaut-llm"]["properties"]["subscriptionRequired"] = False
        service.objects["products/meternaut-learning-demo-dev/policies/policy"] = "<policies><inbound><base /></inbound></policies>"
        service.calls.clear()
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        puts = [(p, h) for m, p, _, _, h in service.calls if m == "PUT"]
        self.assertEqual([p for p, _ in puts], ["apis/meternaut-llm", "products/meternaut-learning-demo-dev/policies/policy"])
        self.assertTrue(all(h == {"If-Match": "*"} for _, h in puts), "an update says it replaces what is there")
        self.assertEqual((rows(out, "updated"), rows(out, "unchanged"), rows(out, "created")), (2, 6, 0))

    def test_the_service_refusing_an_update_is_an_error_not_a_success(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        apim = aps.Apim(service, APIM, "2024-05-01")
        item = {"path": "apis/meternaut-llm", "body": {"properties": {"displayName": "x"}}}
        with self.assertRaises(aps.Problem) as ctx:
            apim.write(item)
        self.assertIn("412", str(ctx.exception))
        apim.write(item, exists=True)

    def test_a_write_that_is_only_accepted_is_waited_for_before_the_next_object(self):
        service = FakeService(async_paths={"apis/meternaut-llm"}, ready_after=2)
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(service.slept, [10.0, 10.0])
        self.assertEqual(rows(out, "created"), 8)
        calls = [(m, p) for m, p, *_ in service.calls]
        accepted = calls.index(("PUT", "apis/meternaut-llm"))
        dependent = calls.index(("PUT", "apis/meternaut-llm/operations/chat-completions"))
        polls = [i for i, c in enumerate(calls) if c == ("GET", "apis/meternaut-llm") and i > accepted]
        self.assertEqual(len(polls), 3)
        self.assertTrue(all(i < dependent for i in polls), "the operation is written after the API is there")

    def test_an_accepted_write_that_fails_or_never_finishes_stops_the_apply(self):
        failed = FakeService(async_paths={"apis/meternaut-llm"}, ready_after=0, states={"apis/meternaut-llm": ["Failed"]})
        code, _, err = run(["apply", *vars_args()], failed)
        self.assertEqual(code, 2)
        self.assertIn("failed", err)
        self.assertNotIn("apis/meternaut-llm/operations/chat-completions", [p for _, p in failed.writes()])
        stuck = FakeService(async_paths={"apis/meternaut-llm"}, ready_after=10 ** 6)
        code, _, err = run(["apply", *vars_args()], stuck)
        self.assertEqual(code, 2)
        self.assertIn("still not ready", err)
        self.assertEqual(len(stuck.slept), 30)
        self.assertNotIn("apis/meternaut-llm/operations/chat-completions", [p for _, p in stuck.writes()])

    def test_a_201_that_reports_in_progress_is_waited_for_like_a_202(self):
        # Microsoft's reference for creating an API answers 200 or 201 with provisioningState InProgress
        service = FakeService(states={"apis/meternaut-llm": ["InProgress", "InProgress", "Succeeded"]})
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(service.slept, [10.0, 10.0])
        calls = [(m, p) for m, p, *_ in service.calls]
        created = calls.index(("PUT", "apis/meternaut-llm"))
        dependent = calls.index(("PUT", "apis/meternaut-llm/operations/chat-completions"))
        polls = [i for i, c in enumerate(calls) if c == ("GET", "apis/meternaut-llm") and i > created]
        self.assertEqual(len(polls), 3)
        self.assertTrue(all(i < dependent for i in polls), "nothing that depends on the API is written while it is being made")

    def test_every_write_is_followed_by_a_read_that_must_come_back_final(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        calls = [(m, p) for m, p, *_ in service.calls]
        for put in [c for c in calls if c[0] == "PUT"]:
            nxt = calls[calls.index(put) + 1]
            self.assertEqual(nxt, ("HEAD" if aps.LINK.fullmatch(put[1]) else "GET", put[1]), put)

    def test_a_state_the_reference_does_not_name_is_final_not_a_reason_to_wait(self):
        # the reference gives no list of final states for an API; waiting on an unknown word would fail every run
        for word in ("Succeeded", "Created", "Ready", "OK", "something-new"):
            service = FakeService(states={"apis/meternaut-llm": [word]})
            code, out, err = run(["apply", *vars_args()], service)
            self.assertEqual((code, err, service.slept), (0, "", []), word)
            self.assertEqual(rows(out, "created"), 8, word)

    def test_states_that_mean_working_are_waited_for_whatever_their_case(self):
        for word in ("InProgress", "inprogress", "INPROGRESS", "Updating", "Creating", "Accepted",
                     "In Progress", "in_progress", "In-Progress", "Queued", "NotStarted", "Not Started", "Deploying"):
            service = FakeService(states={"apis/meternaut-llm": [word, "Created"]})
            code, _, err = run(["apply", *vars_args()], service)
            self.assertEqual((code, err, service.slept), (0, "", [10.0]), word)

    def test_a_state_is_compared_without_case_spaces_underscores_and_hyphens(self):
        for word in ("InProgress", "In Progress", "in_progress", "In-Progress", " inprogress "):
            self.assertEqual(aps.state_of({"properties": {"provisioningState": word}}), "inprogress", word)
        self.assertEqual(aps.raw_state({"properties": {"provisioningState": "In Progress"}}), "In Progress")
        self.assertIsNone(aps.state_of("<policies/>"))
        self.assertIsNone(aps.state_of({"properties": {}}))

    def test_a_state_word_nobody_listed_is_printed_once_so_the_first_run_shows_the_vocabulary(self):
        for word in ("Succeeded", "Created", "Ready", "Completed", "Active", "InProgress", "Failed"):
            service = FakeService(states={"apis/meternaut-llm": [word, "Succeeded"]})
            _, out, _ = run(["plan", *vars_args()], service)
            self.assertNotIn("note:", out, word)
        service = FakeService(states={"apis/meternaut-llm": ["Brand New"]})
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.count("note: "), 1, out)  # once, though the object was read several times
        self.assertIn("note: apis/meternaut-llm reports the state 'Brand New', which this tool does not know", out)
        _, out, _ = run(["plan", *vars_args()], service)  # an existing object is noted by plan as well
        self.assertEqual(out.count("note: "), 1, out)

    def test_a_state_word_that_is_not_plain_text_cannot_become_a_workflow_command(self):
        hostile = "x\n::add-mask::secret\r\n::error::boom"
        service = FakeService(states={"apis/meternaut-llm": [hostile]})
        _, out, _ = run(["apply", *vars_args()], service)
        self.assertNotIn("::", out)
        self.assertTrue(all(line.startswith(("note: ", "created ", "unchanged ", "updated ", "8 created")) for line in out.splitlines() if line), out)

    def test_the_notes_are_printed_when_the_run_stops_too(self):
        class Refuses(FakeService):
            def request(self, method, url, body=None, headers=None):
                if method == "PUT" and "/operations/" in url:
                    return 409, {}, b'{"error":{"code":"Conflict"}}'
                return super().request(method, url, body, headers)

        service = Refuses(states={"apis/meternaut-llm": ["Brand New"]})
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual(code, 2)
        self.assertIn("note: apis/meternaut-llm reports the state 'Brand New'", err)
        self.assertIn("error: ", err)
        self.assertLess(err.index("note: "), err.index("error: "))

    def test_a_write_that_ends_failed_or_cancelled_is_an_error(self):
        for state in ("Failed", "Canceled", "Cancelled", "failed", "Error", "Rejected", "Aborted", "TimedOut"):
            service = FakeService(states={"apis/meternaut-llm": ["InProgress", state]})
            code, _, err = run(["apply", *vars_args()], service)
            self.assertEqual(code, 2, state)
            self.assertIn(state.lower(), err)
            self.assertNotIn("apis/meternaut-llm/operations/chat-completions", [p for _, p in service.writes()])

    def test_an_existing_object_that_reports_failed_is_made_again_not_skipped(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        service.states["apis/meternaut-llm"] = ["Failed", "Succeeded"]  # it matches the definition, and still failed
        code, out, _ = run(["plan", *vars_args()], service)
        self.assertEqual(code, 0)
        self.assertIn("update    apis/meternaut-llm\n", out)
        service.states["apis/meternaut-llm"] = ["Failed", "Succeeded"]
        service.calls.clear()
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        puts = [(p, h) for m, p, _, _, h in service.calls if m == "PUT"]
        self.assertEqual(puts, [("apis/meternaut-llm", {"If-Match": "*"})])
        self.assertEqual(rows(out, "updated"), 1)
        service.states["apis/meternaut-llm"] = ["Failed"]  # and made again, but failing again
        code, _, err = run(["apply", *vars_args()], service)
        self.assertEqual(code, 2)
        self.assertIn("failed", err)

    def test_an_existing_object_that_is_still_in_progress_is_waited_for_before_it_is_compared(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        service.states["apis/meternaut-llm"] = ["InProgress", "Succeeded"]
        service.slept.clear()
        service.calls.clear()
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(service.slept, [10.0])
        self.assertEqual(service.writes(), [])
        self.assertEqual(rows(out, "unchanged"), 8, out)

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
        self.assertTrue(all("deleteSubscriptions" not in params for _, params in deleted), "no cascade into subscriptions")
        self.assertEqual(dict(deleted)["apis/meternaut-llm"].get("deleteRevisions"), "true")
        self.assertEqual(sorted(service.objects), ["apis/other-team-api", "products/other-team-product"])

    def test_remove_never_deletes_a_subscription_the_manifest_does_not_name(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        service.objects["subscriptions/someone-elses-key"] = {"properties": {"scope": "/products/meternaut-learning-demo-dev", "state": "active"}}
        code, out, err = run(["remove", *vars_args()], service)
        self.assertEqual(code, 2)
        self.assertIn("409", err)
        self.assertIn("not in the manifest", err)
        self.assertIn("subscriptions/someone-elses-key", service.objects)  # still there
        self.assertNotIn("subscriptions/meternaut-learning-demo-dev-sub-01", service.objects)  # ours went first
        self.assertTrue(all("deleteSubscriptions" not in params for _, _, params, *_ in service.calls))

    def test_remove_twice_reports_absent_and_succeeds(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        run(["remove", *vars_args()], service)
        code, out, err = run(["remove", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(rows(out, "absent"), 6)
        self.assertEqual(service.objects, {})

    LINK = "products/meternaut-learning-demo-dev/apis/meternaut-llm"

    def test_what_is_not_there_is_absent_and_no_delete_is_sent_for_it(self):
        # the real service answers a DELETE of an object that does not exist with 204, which would read as "deleted"
        service = FakeService(delete_missing_204=True)
        code, out, err = run(["remove", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(rows(out, "absent"), 6)
        self.assertEqual(rows(out, "deleted"), 0)
        self.assertEqual(service.writes(), [])

    def test_a_part_removed_instance_reports_each_object_as_it_is(self):
        service = FakeService(delete_missing_204=True)
        run(["apply", *vars_args()], service)
        del service.objects["subscriptions/meternaut-learning-demo-dev-sub-01"]
        del service.objects[self.LINK]
        code, out, err = run(["remove", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual((rows(out, "deleted"), rows(out, "absent")), (4, 2))
        self.assertIn("absent    subscriptions/meternaut-learning-demo-dev-sub-01\n", out)
        self.assertIn(f"absent    {self.LINK}\n", out)
        self.assertEqual(service.objects, {})

    def test_only_the_link_between_a_product_and_an_api_is_the_link(self):
        self.assertTrue(aps.LINK.fullmatch(self.LINK))
        for other in ("products/meternaut-learning-demo-dev", "apis/meternaut-llm", "apis/meternaut-llm/operations/chat-completions",
                      "products/meternaut-learning-demo-dev/policies/policy", "apis/meternaut-llm/policies/policy",
                      "products/a/apis/b/c", "products/a/apis/", "xproducts/a/apis/b"):
            self.assertFalse(aps.LINK.fullmatch(other), other)

    def test_the_link_between_a_product_and_an_api_is_looked_for_with_head_never_get(self):
        # the real instance answers a GET on it with 405; the reference defines HEAD (204), PUT and DELETE only
        service = FakeService()
        code, out, err = run(["plan", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"create    {self.LINK}\n", out)
        self.assertEqual({m for m, p, *_ in service.calls if p == self.LINK}, {"HEAD"})
        code, out, err = run(["apply", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual([m for m, p, *_ in service.calls if p == self.LINK], ["HEAD", "HEAD", "PUT", "HEAD"])  # plan, apply's plan, the write, the check
        code, out, err = run(["plan", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"unchanged {self.LINK}\n", out)
        self.assertNotIn("GET", {m for m, p, *_ in service.calls if p == self.LINK})

    def test_a_405_or_any_other_answer_to_looking_for_the_link_is_an_error_not_a_guess(self):
        class Odd(FakeService):
            def request(self, method, url, body=None, headers=None):
                if method == "HEAD":
                    return 403, {}, b""
                return super().request(method, url, body, headers)

        code, _, err = run(["plan", *vars_args()], Odd())
        self.assertEqual(code, 2)
        self.assertIn(f"{self.LINK}: looking for it gave 403", err)

    def test_the_link_is_removed_without_if_match_and_everything_else_with_it(self):
        service = FakeService()
        run(["apply", *vars_args()], service)
        service.calls.clear()
        code, out, err = run(["remove", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        deletes = {p: h for m, p, _, _, h in service.calls if m == "DELETE"}
        self.assertIsNone(deletes[self.LINK])
        self.assertTrue(all(h == {"If-Match": "*"} for p, h in deletes.items() if p != self.LINK), deletes)

    def test_an_api_whose_removal_is_only_accepted_is_waited_for_before_the_product_goes(self):
        # the reference answers a delete of an API with 202 or 204
        service = FakeService(async_deletes={"apis/meternaut-llm"}, ready_after=2)
        run(["apply", *vars_args()], service)
        service.calls.clear()
        service.slept.clear()
        code, out, err = run(["remove", *vars_args()], service)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(service.slept, [10.0, 10.0])
        calls = [(m, p) for m, p, *_ in service.calls]
        deleted_api = calls.index(("DELETE", "apis/meternaut-llm"))
        deleted_product = calls.index(("DELETE", "products/meternaut-learning-demo-dev"))
        polls = [i for i, c in enumerate(calls) if c == ("GET", "apis/meternaut-llm") and i > deleted_api]
        self.assertEqual(len(polls), 3)  # two reads that still see it, one that does not
        self.assertTrue(all(i < deleted_product for i in polls), "the product is removed after the API is gone")
        self.assertEqual(rows(out, "deleted"), 6)
        self.assertEqual(service.objects, {})

    def test_an_api_that_is_never_gone_is_an_error_not_a_hang(self):
        service = FakeService(async_deletes={"apis/meternaut-llm"}, ready_after=10 ** 6)
        run(["apply", *vars_args()], service)
        service.slept.clear()
        code, _, err = run(["remove", *vars_args()], service)
        self.assertEqual(code, 2)
        self.assertIn("apis/meternaut-llm: still there after 300 seconds", err)
        self.assertEqual(len(service.slept), 30)
        self.assertNotIn(("DELETE", "products/meternaut-learning-demo-dev"), service.writes())

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

    def test_a_query_a_fragment_or_a_separator_in_the_instance_id_is_refused_before_anything_is_sent(self):
        # The id comes from a repository secret. Once an id ending in ?api-version=...# was accepted: everything after
        # the # is dropped on the wire, so the DELETE of a meternaut- object became a DELETE of the instance itself.
        for tail in ("?api-version=2024-05-01#", "#", "?x=1", "%3Fx", "%23", "\\x", " x", "x/../y", "x;y", "x\n", "x?", "x:y", "x@y"):
            bad = APIM + tail
            for command in ("plan", "remove", "key"):
                service = FakeService()
                code, _, err = run([command, f"--apim={bad}", *VARS_AS_ARGS], service)
                self.assertEqual(code, 2, (command, tail))
                self.assertEqual(service.calls, [], (command, tail))
        for bad_group in ("rg?x", "rg#", "rg/x", "rg x", "rg%2f"):
            self.assertIsNone(aps.APIM_ID.fullmatch(APIM.replace("rg-test", bad_group)), bad_group)
        for tail in ("\n", "\r\n", "\t", "\x00", "\u00e9"):  # a pattern that ends in $ lets a trailing newline through; this one must not
            self.assertIsNone(aps.APIM_ID.fullmatch(APIM + tail), repr(tail))
        self.assertIsNotNone(aps.APIM_ID.fullmatch(APIM))

    def test_an_address_is_always_inside_the_instance_whatever_the_path(self):
        apim = aps.Apim(FakeService(), APIM, "2024-05-01")
        url = apim.url("products/meternaut-x", deleteRevisions="true")
        wire = urllib.request.Request(url, method="DELETE")
        self.assertTrue(wire.selector.startswith(APIM + "/products/meternaut-x?"), wire.selector)
        self.assertEqual(wire.host, "management.azure.com")
        for bad_path in ("products/meternaut-x?y=1", "products/meternaut-x#z", "products/meternaut-x%2f", "products/meternaut x", "a\\b"):
            with self.assertRaises(aps.Problem, msg=bad_path):
                apim.url(bad_path)

    def test_the_api_version_is_a_date(self):
        for bad in ("", "latest", "2024-05-01&x=1", "2024-05-01#", "../2024-05-01"):
            with self.assertRaises(aps.Problem, msg=bad):
                aps.Apim(FakeService(), APIM, bad)
        aps.Apim(FakeService(), APIM, "2024-06-01-preview")


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
        for url in ("https://evil.example.com/x", "http://management.azure.com/x", aps.ARM + ".evil.com/x", "https://management.azure.com@evil.com/x",
                    "https://management.azure.com/x#fragment", "https://management.azure.com/x?y=1#/z", "https://user:pw@management.azure.com/x",
                    "https://management.azure.com:8443/x"):
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
