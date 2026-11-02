import io
import json
import unittest
import urllib.error
from unittest import mock

from harness.client import ClientError, Completion, GuardedClient, HubClient, ScriptedClient, StopRun

ENV = {"C14_HUB_CHAT_URL": "https://hub.example/openai/chat/completions", "C14_HUB_MODEL": "reasoner", "C14_HUB_KEY": "k"}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def reply(text="hello", prompt=11, completion=7):
    body = {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}
    return FakeResponse(json.dumps(body).encode("utf-8"))


def http_error(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://hub.example", code, "x", headers, io.BytesIO(b"busy"))


class HubClientTests(unittest.TestCase):
    def test_the_route_and_the_credentials_are_required(self):
        with self.assertRaises(ClientError) as raised:
            HubClient({})
        self.assertIn("C14_HUB_CHAT_URL", str(raised.exception))
        with self.assertRaises(ClientError):
            HubClient({"C14_HUB_CHAT_URL": "https://hub.example/x", "C14_HUB_MODEL": "m"})

    def test_only_https_is_accepted(self):
        with self.assertRaises(ClientError):
            HubClient({**ENV, "C14_HUB_CHAT_URL": "http://hub.example/x"})

    def test_a_call_sends_the_key_the_model_and_both_messages(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["headers"] = {k.lower(): v for k, v in request.header_items()}
            seen["body"] = json.loads(request.data)
            return reply("answer", 5, 2)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            completion = HubClient({**ENV, "C14_HUB_MAX_TOKENS": "900"}).complete("system text", "user text")
        self.assertEqual(completion, Completion("answer", 5, 2))
        self.assertEqual(seen["headers"]["api-key"], "k")
        self.assertNotIn("authorization", seen["headers"])
        self.assertEqual(seen["body"]["model"], "reasoner")
        self.assertEqual([m["role"] for m in seen["body"]["messages"]], ["system", "user"])
        self.assertEqual(seen["body"]["max_completion_tokens"], 900)

    def test_a_bearer_token_is_used_instead_of_the_key(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["headers"] = {k.lower(): v for k, v in request.header_items()}
            return reply()

        env = {**ENV, "C14_HUB_BEARER": "token"}
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            HubClient(env).complete("s", "u")
        self.assertEqual(seen["headers"]["authorization"], "Bearer token")
        self.assertNotIn("api-key", seen["headers"])

    def test_a_busy_hub_is_retried_with_its_retry_after(self):
        outcomes = [http_error(429, "3"), reply("late")]
        sleeps = []

        def fake_urlopen(request, timeout):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        client = HubClient(ENV, sleep=sleeps.append)
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            self.assertEqual(client.complete("s", "u").text, "late")
        self.assertEqual(sleeps, [3.0])
        self.assertEqual(client.requests, 2)

    def test_a_refusal_is_an_error_and_never_shows_the_key(self):
        def fake_urlopen(request, timeout):
            raise http_error(401)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(ClientError) as raised:
                HubClient({**ENV, "C14_HUB_KEY": "SECRET-KEY-123"}).complete("s", "u")
        self.assertIn("401", str(raised.exception))
        self.assertNotIn("SECRET-KEY-123", str(raised.exception))

    def test_a_reply_that_is_not_a_chat_completion_is_an_error(self):
        with mock.patch("urllib.request.urlopen", lambda request, timeout: FakeResponse(b'{"nope": 1}')):
            with self.assertRaises(ClientError):
                HubClient(ENV).complete("s", "u")


class GuardTests(unittest.TestCase):
    def test_the_call_limit_stops_the_run(self):
        client = GuardedClient(ScriptedClient(lambda s, u: "x"), max_calls=2)
        client.complete("s", "u")
        client.complete("s", "u")
        with self.assertRaises(StopRun):
            client.complete("s", "u")

    def test_the_cap_stops_the_run_once_the_cost_reaches_it(self):
        client = GuardedClient(ScriptedClient(lambda s, u: Completion("x", 1_000_000, 0)), max_calls=10, prices=(1.0, 1.0),
                               cap_eur=1.0, max_completion_tokens=100)
        client.complete("s", "u")
        self.assertAlmostEqual(client.cost_eur, 1.0)
        with self.assertRaises(StopRun):
            client.complete("s", "u")

    def test_a_call_that_could_pass_the_cap_is_refused_before_it_is_made(self):
        inner = ScriptedClient(lambda s, u: "x")
        client = GuardedClient(inner, max_calls=10, prices=(1.0, 1.0), cap_eur=0.5, max_completion_tokens=600_000)
        with self.assertRaises(StopRun) as raised:
            client.complete("s", "u")
        self.assertIn("could pass the spending cap", str(raised.exception))
        self.assertEqual(inner.calls, 0)

    def test_the_prompt_is_part_of_the_worst_case(self):
        inner = ScriptedClient(lambda s, u: "x")
        client = GuardedClient(inner, max_calls=10, prices=(1.0, 1.0), cap_eur=0.4, max_completion_tokens=1)
        with self.assertRaises(StopRun):
            client.complete("s", "u" * 1_000_000)
        self.assertEqual(inner.calls, 0)

    def test_a_cap_needs_prices_and_a_reply_limit(self):
        inner = ScriptedClient(lambda s, u: "x")
        with self.assertRaises(ValueError):
            GuardedClient(inner, max_calls=2, cap_eur=1.0)
        with self.assertRaises(ValueError):
            GuardedClient(inner, max_calls=2, cap_eur=1.0, prices=(1.0, 1.0))
        with self.assertRaises(ValueError):
            GuardedClient(inner, max_calls=2, cap_eur=1.0, max_completion_tokens=10)

    def test_calls_already_used_count_against_the_limit_and_the_cost(self):
        client = GuardedClient(ScriptedClient(lambda s, u: Completion("x", 10, 0)), max_calls=2, prices=(1.0, 1.0), used=(1, 100, 10))
        client.complete("s", "u")
        self.assertEqual((client.calls, client.prompt_tokens, client.completion_tokens), (2, 110, 10))
        with self.assertRaises(StopRun):
            client.complete("s", "u")

    def test_the_hub_is_told_the_reply_limit_of_the_stage(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["body"] = json.loads(request.data)
            return reply()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            HubClient({**ENV, "C14_HUB_MAX_TOKENS": "900"}, max_tokens=50).complete("s", "u")
        self.assertEqual(seen["body"]["max_completion_tokens"], 50)

    def test_without_prices_the_cost_is_unknown(self):
        client = GuardedClient(ScriptedClient(lambda s, u: "x"), max_calls=2)
        client.complete("s", "u")
        self.assertIsNone(client.cost_eur)


if __name__ == "__main__":
    unittest.main()
