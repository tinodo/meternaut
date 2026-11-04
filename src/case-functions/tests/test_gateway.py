import json
import unittest
import urllib.error

from support import ENV, KEY, PRODUCT_SUBSCRIPTION, TOKEN
from cases import config
from cases.gateway import Gateway, GatewayError, GatewayRefused
from cases.http import Client, allowed_calls
from cases.redact import Redactor
from test_http import Script, ok


def gateway_with(*answers):
    redact = Redactor()
    script = Script(*answers)
    settings = config.load(ENV)
    client = Client(allowed_calls(settings.gateway_host, Gateway.key_path(settings)), redact, transport=script, sleep=lambda s: None, jitter=lambda: 0.5)
    return Gateway(settings, client, lambda resource: TOKEN, redact), script, redact


def completion(text='{"ok":1}', prompt=10, completion_tokens=5, total=None, finish="stop"):
    return ok({"choices": [{"message": {"content": text}, "finish_reason": finish}], "usage": {"prompt_tokens": prompt, "completion_tokens": completion_tokens,
                                                                                          "total_tokens": total if total is not None else prompt + completion_tokens}})


class Key(unittest.TestCase):
    def test_the_key_is_read_from_the_access_products_subscription_with_the_identitys_token_and_registered_for_redaction(self):
        gateway, script, redact = gateway_with(ok({"primaryKey": KEY, "secondaryKey": "other-secret-value-1234"}))
        gateway.open()
        ((method, url, headers, data, timeout),) = script.calls
        self.assertEqual(method, "POST")
        self.assertEqual(url, f"https://management.azure.com{PRODUCT_SUBSCRIPTION}/listSecrets?api-version=2024-05-01")
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(redact(f"x {KEY} y"), "x [redacted] y")

    def test_the_other_key_is_never_taken(self):
        gateway, script, _ = gateway_with(ok({"primaryKey": KEY, "secondaryKey": "other-secret-value-1234"}), completion())
        gateway.open()
        gateway.chat("gpt-6-luna", "s", "u", 100)
        self.assertEqual(script.calls[1][2]["api-key"], KEY)

    def test_a_refusal_or_an_answer_without_a_key_is_an_error_without_the_key_in_its_text(self):
        for answer in ((403, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right"}}'), ok({}), ok({"primaryKey": "short"}), ok({"primaryKey": 5}), ok([1])):
            gateway, _, _ = gateway_with(answer)
            with self.assertRaises(GatewayError) as raised:
                gateway.open()
            self.assertNotIn(KEY, str(raised.exception))

    def test_a_chat_before_the_key_is_read_is_an_error_and_makes_no_call(self):
        gateway, script, _ = gateway_with(completion())
        with self.assertRaises(GatewayError):
            gateway.chat("m", "s", "u", 10)
        self.assertEqual(script.calls, [])


class Chat(unittest.TestCase):
    def opened(self, *answers):
        gateway, script, redact = gateway_with(ok({"primaryKey": KEY}), *answers)
        gateway.open()
        return gateway, script, redact

    def test_the_request_goes_to_the_chat_route_with_the_key_the_model_and_the_cap(self):
        gateway, script, _ = self.opened(completion("hello", 12, 8, 20))
        chat = gateway.chat("gpt-6-luna", "system words", "user words", 2000)
        self.assertEqual((chat.text, chat.prompt_tokens, chat.completion_tokens, chat.total_tokens), ("hello", 12, 8, 20))
        method, url, headers, data, timeout = script.calls[1]
        self.assertEqual((method, url, timeout), ("POST", "https://example-apim.azure-api.net/models/chat/completions", 90))
        self.assertEqual(headers["api-key"], KEY)
        self.assertNotIn("Authorization", headers)
        self.assertEqual(json.loads(data), {"model": "gpt-6-luna", "messages": [{"role": "system", "content": "system words"}, {"role": "user", "content": "user words"}],
                                            "max_completion_tokens": 2000})

    def test_a_401_reads_the_key_again_once_and_calls_again(self):
        gateway, script, _ = self.opened((401, {}, b'{"statusCode":401}'), ok({"primaryKey": KEY}), completion("fine"))
        self.assertEqual(gateway.chat("m", "s", "u", 10).text, "fine")
        self.assertEqual([c[1].rsplit("/", 1)[-1].split("?")[0] for c in script.calls], ["listSecrets", "completions", "listSecrets", "completions"])

    def test_a_second_401_is_a_refusal_not_a_loop(self):
        gateway, script, _ = self.opened((401, {}, b"{}"), ok({"primaryKey": KEY}), (401, {}, b"{}"))
        with self.assertRaises(GatewayRefused):
            gateway.chat("m", "s", "u", 10)
        self.assertEqual(len(script.calls), 4)

    def test_a_key_that_cannot_be_read_again_after_a_401_is_a_failure_of_the_case(self):
        gateway, script, _ = self.opened((401, {}, b"{}"))
        with self.assertRaises(GatewayError) as raised:
            gateway.chat("m", "s", "u", 10)
        self.assertIn("could not be read", str(raised.exception))

    def test_a_403_and_a_long_429_are_refusals_that_are_not_retried(self):
        for answer in ((403, {}, b'{"statusCode":403,"message":"model not allowed"}'), (429, {"retry-after": "86400"}, b'{"statusCode":429,"message":"quota"}')):
            gateway, script, _ = self.opened(answer)
            with self.assertRaises(GatewayRefused) as raised:
                gateway.chat("m", "s", "u", 10)
            self.assertEqual(len(script.calls), 2)
            self.assertNotIn(KEY, str(raised.exception))

    def test_a_rate_limit_of_a_few_seconds_is_waited_for(self):
        sleeps = []
        gateway, script, _ = self.opened((429, {"retry-after": "5"}, b"{}"), completion("later"))
        gateway.client.sleep = sleeps.append
        self.assertEqual(gateway.chat("m", "s", "u", 10).text, "later")
        self.assertEqual(sleeps, [5.0])

    def test_a_server_error_is_a_failure_that_is_not_a_refusal(self):
        gateway, _, _ = self.opened((502, {}, b"{}"))
        with self.assertRaises(GatewayError) as raised:
            gateway.chat("m", "s", "u", 10)
        self.assertNotIsInstance(raised.exception, GatewayRefused)

    def test_a_call_that_may_already_have_been_carried_out_is_not_made_again(self):
        for answer in (urllib.error.URLError("down"), TimeoutError("slow"), (500, {}, b"{}"), (502, {}, b"{}"), (504, {}, b"{}")):
            gateway, script, _ = self.opened(answer, completion("twice"))
            with self.assertRaises(GatewayError, msg=str(answer)):
                gateway.chat("m", "s", "u", 10)
            self.assertEqual(len(script.calls), 2, "the key, and one call of the model")

    def test_a_refusal_that_says_not_now_is_made_again_and_only_twice(self):
        gateway, script, _ = self.opened((503, {}, b"{}"), completion("later"))
        self.assertEqual(gateway.chat("m", "s", "u", 10).text, "later")
        self.assertEqual(len(script.calls), 3)
        gateway, script, _ = self.opened((503, {}, b"{}"))
        with self.assertRaises(GatewayError):
            gateway.chat("m", "s", "u", 10)
        self.assertEqual(len(script.calls), 4, "the key and three calls of the model")

    def test_a_usage_that_is_not_valid_is_refused(self):
        for usage in ({"prompt_tokens": -5, "completion_tokens": 4, "total_tokens": -1}, {"prompt_tokens": 5, "completion_tokens": -4},
                      {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": -9}):
            gateway, _, _ = self.opened(ok({"choices": [{"message": {"content": "x"}}], "usage": usage}))
            with self.assertRaises(GatewayError, msg=str(usage)) as raised:
                gateway.chat("m", "s", "u", 10)
            self.assertIn("usage that is not valid", str(raised.exception))

    def test_the_total_is_never_less_than_the_sum_of_the_parts(self):
        gateway, _, _ = self.opened(ok({"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 5}}))
        self.assertEqual(gateway.chat("m", "s", "u", 10).total_tokens, 7)
        gateway, _, _ = self.opened(ok({"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 20}}))
        self.assertEqual(gateway.chat("m", "s", "u", 10).total_tokens, 20)

    def test_an_answer_that_is_not_a_completion_is_an_error(self):
        for answer in (ok({}), ok({"choices": []}), ok({"choices": [{}]}), ok({"choices": [{"message": {"content": "x"}}], "usage": {"total_tokens": "many"}}),
                       ok([1]), completion(""), completion("   ")):
            gateway, _, _ = self.opened(answer)
            with self.assertRaises(GatewayError, msg=str(answer)):
                gateway.chat("m", "s", "u", 10)

    def test_a_model_that_spent_its_whole_budget_on_reasoning_says_so(self):
        gateway, _, _ = self.opened(completion("", finish="length"))
        with self.assertRaises(GatewayError) as raised:
            gateway.chat("m", "s", "u", 10)
        self.assertIn("completion budget", str(raised.exception))

    def test_the_total_is_the_sum_when_the_gateway_reports_none(self):
        gateway, _, _ = self.opened(ok({"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4}}))
        self.assertEqual(gateway.chat("m", "s", "u", 10).total_tokens, 7)

    def test_the_key_is_in_no_error_text_even_when_the_gateway_echoes_it(self):
        gateway, _, _ = self.opened((400, {}, json.dumps({"error": {"code": "Bad", "message": f"your key {KEY} is bad"}}).encode()))
        with self.assertRaises(GatewayError) as raised:
            gateway.chat("m", "s", "u", 10)
        self.assertNotIn(KEY, str(raised.exception))
        self.assertNotIn(KEY, repr(raised.exception.__cause__))


if __name__ == "__main__":
    unittest.main()
