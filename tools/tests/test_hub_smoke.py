import importlib.util
import io
import json
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1] / "hub-smoke.py"
spec = importlib.util.spec_from_file_location("hub_smoke", TOOL)
hs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hs)

URL = "https://apim-test.azure-api.net/meternaut/llm/v1/chat/completions"
KEY = "k" * 32
CONTRACT = {"name": "meternaut-test", "models": ["model-a"], "tokensPerMinute": 1000, "tokenQuotaPerMonth": 10000}
COMPLETION = json.dumps({"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 12}}).encode()
BACKEND_429 = b'{"error":{"code":"429","message":"Requests to the Chat Completions operation have exceeded the token rate limit of your current deployment."}}'


def completion_using(tokens):
    return json.dumps({"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": tokens}}).encode()


class FakeHub:
    """A hub that keeps its contract: the right key and model get a completion, anything else the answers the gateway gives."""

    def __init__(self, tokens_per_minute=1000, enforce_rate=True, valid_after=1, wrong_model_allowed=False, big_status=None,
                 backend_throttles=False, big_usage=None, valid_reply=None):
        self.sent, self.used, self.rate = [], 0, tokens_per_minute
        self.enforce_rate, self.valid_after, self.wrong_model_allowed, self.big_status = enforce_rate, valid_after, wrong_model_allowed, big_status
        self.backend_throttles, self.big_usage, self.valid_reply = backend_throttles, big_usage, valid_reply
        self.valid_calls = 0

    def post(self, body, key):
        self.sent.append((body, key))
        if key is None:
            return 401, b'{"statusCode":401,"message":"Access denied due to missing subscription key."}'
        if key != KEY:
            return 401, b'{"statusCode":401,"message":"Access denied due to invalid subscription key."}'
        model = body.get("model")
        if not model or (model != "model-a" and not self.wrong_model_allowed):
            return 403, b'{"error":{"code":"model_not_allowed","message":"no"}}'
        words = len(body["messages"][0]["content"].split())
        if self.enforce_rate and self.used >= self.rate:
            if self.backend_throttles:
                return 429, BACKEND_429
            return 429, b'{"statusCode":429,"message":"Token limit is exceeded. Try again in 30 seconds."}'
        if words > 20:
            if self.big_status:
                return self.big_status, (b'{"statusCode":429,"message":"Token limit is exceeded."}' if self.big_status == 429 else b'{"error":"too large"}')
            self.used += words
            return 200, completion_using(words if self.big_usage is None else self.big_usage)
        self.valid_calls += 1
        if self.valid_calls < self.valid_after:
            return 502, b"bad gateway"
        return 200, self.valid_reply if self.valid_reply is not None else COMPLETION


class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def now(self):
        return self.t


def run(hub, *extra, environ=None, contract=CONTRACT, clock=None, tmp=None):
    clock = clock or Clock()
    contract_file = Path(tmp) / "contract.json"
    contract_file.write_text(json.dumps(contract), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = hs.main(["--url", URL, "--contract", str(contract_file), *extra], client=hub,
                       environ={"HUB_SMOKE_KEY": KEY} if environ is None else environ, sleep=clock.sleep, now=clock.now)
    return code, out.getvalue(), err.getvalue(), clock


class Address(unittest.TestCase):
    def test_only_the_gateway_route_over_https_is_accepted(self):
        hs.Client(URL)
        for bad in ("http://apim-test.azure-api.net/x/chat/completions", "https://evil.example.com/meternaut/chat/completions",
                    "https://apim-test.azure-api.net.evil.com/chat/completions", "https://azure-api.net/chat/completions",
                    "https://.azure-api.net/chat/completions", "https://u:p@apim-test.azure-api.net/chat/completions",
                    "https://apim-test.azure-api.net:8443/chat/completions", "https://apim-test.azure-api.net/chat/completions?x=1",
                    "https://apim-test.azure-api.net/chat/completions#f", "https://apim-test.azure-api.net/other", "ftp://apim-test.azure-api.net/chat/completions",
                    "https://apim-test.azure-api.net@evil.com/chat/completions"):
            with self.assertRaises(hs.Problem, msg=bad):
                hs.Client(bad)

    def test_a_redirect_is_not_followed(self):
        self.assertIsNone(hs._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example.com"))


class Wire(unittest.TestCase):
    def client(self, answer):
        client = hs.Client(URL)
        self.sent = []

        def open_(request, timeout=None):
            self.sent.append(request)
            if isinstance(answer, Exception):
                raise answer
            return answer

        client._opener = mock.Mock(open=open_)
        return client

    def test_the_key_goes_in_the_api_key_header_and_only_when_there_is_one(self):
        response = mock.MagicMock()
        response.status, response.read.return_value = 200, b"{}"
        response.__enter__.return_value = response
        client = self.client(response)
        self.assertEqual(client.post({"a": 1}, KEY), (200, b"{}"))
        self.assertEqual(client.post({"a": 1}, None), (200, b"{}"))
        self.assertEqual(self.sent[0].get_header("Api-key"), KEY)
        self.assertIsNone(self.sent[1].get_header("Api-key"))
        self.assertEqual(json.loads(self.sent[0].data), {"a": 1})
        self.assertEqual(self.sent[0].full_url, URL)

    def test_an_error_status_is_an_answer_and_a_dead_network_is_status_zero(self):
        error = urllib.error.HTTPError(URL, 401, "x", {}, io.BytesIO(b"denied"))
        self.assertEqual(self.client(error).post({}, KEY), (401, b"denied"))
        self.assertEqual(self.client(urllib.error.URLError("no route")).post({}, KEY)[0], 0)
        self.assertEqual(self.client(TimeoutError("slow")).post({}, KEY)[0], 0)
        import http.client
        self.assertEqual(self.client(http.client.RemoteDisconnected("closed")).post({}, KEY)[0], 0)


class Checks(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_(self, hub, *extra, **kw):
        return run(hub, *extra, tmp=self.tmp.name, **kw)

    def test_a_hub_that_keeps_its_contract_passes_every_check(self):
        hub = FakeHub()
        code, out, err, _ = self.run_(hub)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("All 5 checks passed.", out)
        for name in ("valid", "no key", "wrong key", "other model", "no model"):
            self.assertIn(f"ok   {name}", out)
        self.assertNotIn("limit", out)
        self.assertTrue(all(len(json.dumps(b)) < 1000 for b, _ in hub.sent))  # nothing large without --limits

    def test_a_hub_that_lets_another_model_through_fails(self):
        code, out, _, _ = self.run_(FakeHub(wrong_model_allowed=True))
        self.assertEqual(code, 1)
        self.assertIn("FAIL other model", out)
        self.assertIn("Failed: other model.", out)

    def test_the_other_checks_wait_for_the_route_to_work(self):
        hub = FakeHub(valid_after=99)
        code, out, _, _ = self.run_(hub, "--wait", "0")
        self.assertEqual(code, 1)
        self.assertEqual(out.count("ok  ") + out.count("FAIL"), 1)
        self.assertEqual(len(hub.sent), 1)

    def test_the_first_request_is_retried_while_the_route_settles(self):
        hub = FakeHub(valid_after=3)
        code, out, _, clock = self.run_(hub, "--wait", "900")
        self.assertEqual(code, 0)
        self.assertIn("200 after 3 attempt(s), 12 tokens", out)
        self.assertEqual(clock.sleeps, [30, 30])

    def test_it_gives_up_when_the_wait_is_over(self):
        hub = FakeHub(valid_after=999)
        code, out, _, clock = self.run_(hub, "--wait", "100")
        self.assertEqual(code, 1)
        self.assertIn("gave up after", out)
        self.assertLessEqual(sum(clock.sleeps), 130)

    def test_a_backend_that_refuses_the_role_is_retried_but_the_gateways_own_refusals_are_not(self):
        calls = []

        class Hub:
            def __init__(self, status, body):
                self.answer = (status, body)

            def post(self, body, key):
                calls.append(1)
                return self.answer

        self.run_(Hub(401, b'{"error":{"code":"PermissionDenied"}}'), "--wait", "60")
        retried = len(calls)
        calls.clear()
        self.run_(Hub(401, b'{"message":"Access denied due to invalid subscription key."}'), "--wait", "60")
        self.assertGreater(retried, 1)
        self.assertEqual(len(calls), 1)
        calls.clear()
        self.run_(Hub(403, b'{"error":{"code":"model_not_allowed"}}'), "--wait", "60")
        self.assertEqual(len(calls), 1)
        calls.clear()
        self.run_(Hub(404, b'{ "statusCode": 404, "message": "Resource not found" }'), "--wait", "60")
        self.assertGreater(len(calls), 1)  # the gateway has not picked up the new API yet
        calls.clear()
        self.run_(Hub(404, b'{"error":{"code":"DeploymentNotFound"}}'), "--wait", "60")
        self.assertEqual(len(calls), 1)  # the model's own 404 will not settle

    def test_a_200_that_is_not_a_completion_fails(self):
        class Hub:
            def post(self, body, key):
                return 200, b"<html>login</html>"

        code, out, _, _ = self.run_(Hub())
        self.assertEqual(code, 1)
        self.assertIn("not a completion", out)

    def test_a_client_error_from_the_model_is_not_retried(self):
        class Hub:
            n = 0

            def post(self, body, key):
                Hub.n += 1
                return 404, b'{"error":{"code":"DeploymentNotFound"}}'

        code, out, _, _ = self.run_(Hub(), "--wait", "900")
        self.assertEqual((code, Hub.n), (1, 1))
        self.assertIn("DeploymentNotFound", out)

    def test_the_limit_check_sends_more_than_a_minute_allows_and_expects_a_refusal(self):
        hub = FakeHub()
        code, out, _, _ = self.run_(hub, "--limits")
        self.assertEqual(code, 0, out)
        self.assertIn("ok   limit", out)
        self.assertIn("All 6 checks passed.", out)
        big = [b for b, _ in hub.sent if len(b["messages"][0]["content"].split()) > 20]
        self.assertEqual(len(big), 1)
        self.assertGreater(len(big[0]["messages"][0]["content"].split()), CONTRACT["tokensPerMinute"])
        self.assertEqual(big[0]["max_completion_tokens"], 1)
        self.assertEqual(hub.sent[-1][0]["messages"][0]["content"], "Reply with the single word: ok")  # the limit check runs last

    def test_a_hub_that_never_refuses_fails_the_limit_check(self):
        code, out, _, clock = self.run_(FakeHub(enforce_rate=False), "--limits")
        self.assertEqual(code, 1)
        self.assertIn("FAIL limit", out)
        self.assertIn("not 429", out)
        self.assertEqual(clock.sleeps, [2, 2, 2])

    def test_a_large_request_the_model_cannot_take_is_reported_as_such(self):
        code, out, _, _ = self.run_(FakeHub(big_status=400), "--limits")
        self.assertEqual(code, 1)
        self.assertIn("the large request was not accepted (400)", out)

    def test_a_refusal_already_on_the_large_request_counts(self):
        hub = FakeHub(big_status=429)
        code, out, _, _ = self.run_(hub, "--limits")
        self.assertEqual((code, out.count("ok   limit")), (0, 1), out)

    def test_a_429_from_the_model_is_not_the_gateways_limit(self):
        code, out, _, _ = self.run_(FakeHub(backend_throttles=True), "--limits")
        self.assertEqual(code, 1)
        self.assertIn("not the gateway's own refusal", out)
        code, out, _, _ = self.run_(FakeHub(big_status=429, backend_throttles=True), "--limits")
        self.assertEqual(code, 0, "a gateway-shaped 429 on the large request counts: big_status sets the gateway's body")
        self.assertTrue(hs.from_gateway(b'{"statusCode":429,"message":"Token limit is exceeded."}'))
        for body in (BACKEND_429, b"", b"not json", b'[429]', b'{"statusCode":429,"error":{"code":"429"}}', b'{"statusCode":"429"}', b'{"statusCode":503}'):
            self.assertFalse(hs.from_gateway(body), body)

    def test_a_large_request_that_does_not_cross_the_allowance_proves_nothing(self):
        for usage in (10, 999, 0):
            code, out, _, _ = self.run_(FakeHub(big_usage=usage, enforce_rate=False), "--limits")
            self.assertEqual(code, 1, usage)
            self.assertIn("the check proves nothing", out)
        code, out, _, _ = self.run_(FakeHub(big_usage=1000), "--limits")
        self.assertEqual(code, 0, out)

    def test_a_completion_without_token_usage_fails_the_valid_check(self):
        for usage in ({}, {"total_tokens": 0}, {"total_tokens": "12"}, {"total_tokens": True}, None):
            reply = {"choices": [{"message": {"content": "ok"}}]}
            if usage is not None:
                reply["usage"] = usage
            code, out, _, _ = self.run_(FakeHub(valid_reply=json.dumps(reply).encode()))
            self.assertEqual(code, 1, usage)
            self.assertIn("no token usage", out)
        self.assertEqual(hs.usage_of(COMPLETION), 12)


class Secrets(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_the_key_is_needed_and_is_checked_before_anything_is_sent(self):
        for environ in ({}, {"HUB_SMOKE_KEY": ""}, {"HUB_SMOKE_KEY": "short"}, {"HUB_SMOKE_KEY": "a" * 32 + "\nX-Evil: 1"}, {"HUB_SMOKE_KEY": "a b" * 10}):
            hub = FakeHub()
            code, out, err, _ = run(hub, environ=environ, tmp=self.tmp.name)
            self.assertEqual(code, 2, environ)
            self.assertIn("HUB_SMOKE_KEY", err)
            self.assertEqual(hub.sent, [])

    def test_the_key_is_never_printed_even_when_the_hub_echoes_it(self):
        class Hub:
            def post(self, body, key):
                return 500, f"internal error for key {KEY} here".encode()

        code, out, err, _ = run(Hub(), "--wait", "0", tmp=self.tmp.name)
        self.assertEqual(code, 1)
        self.assertNotIn(KEY, out + err)
        self.assertIn("***", out)

    def test_the_key_is_not_an_argument(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            hs.main(["--url", URL, "--key", KEY], environ={"HUB_SMOKE_KEY": KEY})

    def test_a_contract_without_a_model_or_a_rate_is_a_clean_error(self):
        for contract in ({"models": [], "tokensPerMinute": 10}, {"models": ["m"]}, {"models": ["m"], "tokensPerMinute": 0}, {"models": ["m"], "tokensPerMinute": "many"}):
            hub = FakeHub()
            code, _, err, _ = run(hub, contract=contract, tmp=self.tmp.name)
            self.assertEqual(code, 2, contract)
            self.assertEqual(hub.sent, [])

    def test_a_bad_address_is_a_clean_error(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = hs.main(["--url", "http://apim-test.azure-api.net/chat/completions"], environ={"HUB_SMOKE_KEY": KEY})
        self.assertEqual(code, 2)
        self.assertIn("--url", err.getvalue())

    def test_the_real_contract_gives_a_model_and_a_rate(self):
        contract = json.loads((Path(__file__).resolve().parents[2] / "hub" / "contract.json").read_text(encoding="utf-8"))
        self.assertTrue(contract["models"])
        self.assertGreater(int(contract["tokensPerMinute"]), 0)


if __name__ == "__main__":
    unittest.main()
