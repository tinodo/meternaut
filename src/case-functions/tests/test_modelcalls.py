"""The model calls of the Detective and the Skeptic: a chat completion through the AI Gateway, with the app's own identity and no key (AGENTS.md rule 15 (c)).

The transport is a stand-in for the gateway: nothing here needs a network or a subscription."""
import dataclasses
import json
import unittest
import urllib.error

from support import ENV, FOUNDRY_ENDPOINT, GATEWAY_HOST, KEY, TOKEN
from cases import config
from cases.http import Client, Refused, allowed_calls
from cases.identity import IdentityError
from cases.modelcalls import AUDIENCE, Models, ModelError, ModelRefused
from cases.redact import Redactor
from test_http import Script, ok

URL = f"https://{GATEWAY_HOST}/default/models/openai/v1/chat/completions"


def models_with(*answers, env=None, token=None, host=None):
    """`host` replaces the host of the settings when it is given (an empty one, to see what a chat does without it)."""
    redact = Redactor()
    script = Script(*answers)
    settings = config.load(env or ENV)
    if host is not None:
        settings = dataclasses.replace(settings, ai_gateway_host=host)
    client = Client(allowed_calls(settings.foundry_endpoint, settings.ai_gateway_host or None), redact, transport=script, sleep=lambda s: None, jitter=lambda: 0.5)
    asked = []

    def issue(resource):
        asked.append(resource)
        return token(resource) if token else TOKEN

    models = Models(settings, client, issue, redact)
    models.asked = asked
    return models, script, redact


def completion(text='{"ok":1}', prompt=10, completion_tokens=5, total=None, finish="stop"):
    return ok({"choices": [{"message": {"content": text}, "finish_reason": finish}], "usage": {"prompt_tokens": prompt, "completion_tokens": completion_tokens,
                                                                                          "total_tokens": total if total is not None else prompt + completion_tokens}})


class NoKey(unittest.TestCase):
    def test_a_run_opens_the_models_without_a_call_and_without_a_token(self):
        models, script, _ = models_with(completion())
        models.open()
        self.assertEqual((script.calls, models.asked), ([], []), "nothing is read first: the identity is the credential")

    def test_a_chat_without_the_host_of_the_gateway_is_an_error_of_that_one_call_and_makes_no_call(self):
        models, script, _ = models_with(completion(), host="")
        with self.assertRaises(ModelError) as raised:
            models.chat("gpt-6-luna", "s", "u", 10)
        self.assertEqual(str(raised.exception), "the AI Gateway's host name is not set")
        self.assertNotIsInstance(raised.exception, ModelRefused)
        self.assertEqual((script.calls, models.asked), ([], []))

    def test_the_settings_do_not_load_without_the_host_of_the_gateway(self):
        without = {k: v for k, v in ENV.items() if k != "AIGATEWAY_HOST"}
        with self.assertRaises(config.ConfigError) as raised:
            config.load(without)
        self.assertEqual(str(raised.exception), "AIGATEWAY_HOST is not set")

    def test_the_module_reads_no_key_and_has_no_direct_route_to_a_model(self):
        import cases.modelcalls as module
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read().lower()
        for word in ("listsecrets", "primarykey", "api-key", "ocp-apim", "subscription key", "services.ai.azure.com", "cognitiveservices", "foundry_endpoint", "resource_of"):
            self.assertNotIn(word, source, word)

    def test_the_audience_is_the_one_of_the_ai_gateway(self):
        self.assertEqual(AUDIENCE, "https://azure-api.net/aigateway")


class Chat(unittest.TestCase):
    def test_the_request_goes_to_the_route_of_the_gateway_with_the_token_the_alias_and_the_cap(self):
        models, script, _ = models_with(completion("hello", 12, 8, 20))
        chat = models.chat("gpt-6-luna", "system words", "user words", 2000)
        self.assertEqual((chat.text, chat.prompt_tokens, chat.completion_tokens, chat.total_tokens), ("hello", 12, 8, 20))
        ((method, url, headers, data, timeout),) = script.calls
        self.assertEqual((method, url, timeout), ("POST", URL, 90))
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.assertNotIn("api-key", headers)
        self.assertEqual(models.asked, [AUDIENCE], "the token is the one for the audience of the gateway, https://azure-api.net/aigateway")
        self.assertEqual(json.loads(data), {"model": "gpt-6-luna", "messages": [{"role": "system", "content": "system words"}, {"role": "user", "content": "user words"}],
                                            "max_completion_tokens": 2000})

    def test_the_alias_is_the_model_of_the_request_for_both_roles(self):
        for alias in ("gpt-6-luna", "gpt-6.1-sol"):
            models, script, _ = models_with(completion())
            models.chat(alias, "s", "u", 10)
            self.assertEqual(json.loads(script.calls[0][3])["model"], alias)

    def test_a_token_is_asked_for_every_call_so_that_an_old_one_is_never_kept(self):
        models, _, _ = models_with(completion())
        models.chat("m", "s", "u", 10)
        models.chat("m", "s", "u", 10)
        self.assertEqual(models.asked, [AUDIENCE, AUDIENCE])

    def test_the_token_is_not_in_the_text_of_an_error_even_when_the_service_echoes_it(self):
        for status in (400, 401, 403, 404, 429, 500, 502):
            models, _, _ = models_with((status, {}, json.dumps({"error": {"code": "Bad", "message": f"your token {TOKEN} is bad"}}).encode()))
            with self.assertRaises(ModelError, msg=str(status)) as raised:
                models.chat("gpt-6-luna", "s", "u", 10)
            for text in (str(raised.exception), repr(raised.exception.__cause__), str(raised.exception.__cause__)):
                self.assertNotIn(TOKEN, text, status)
            self.assertNotIn("Bearer", str(raised.exception))

    def test_a_token_that_cannot_be_had_is_an_error_of_that_call_and_makes_no_call_and_holds_no_token(self):
        def refused(resource):
            raise IdentityError(f"the identity endpoint refused the request for {resource}")

        models, script, _ = models_with(completion(), token=refused)
        with self.assertRaises(ModelError) as raised:
            models.chat("m", "s", "u", 10)
        self.assertIn("no token could be had for the AI Gateway", str(raised.exception))
        self.assertNotIsInstance(raised.exception, ModelRefused)
        self.assertEqual(script.calls, [])

    def test_a_401_is_a_refusal_that_says_the_token_was_not_accepted_and_is_not_repeated(self):
        models, script, _ = models_with((401, {}, b'{"error":{"code":"Unauthorized","message":"bad token"}}'))
        with self.assertRaises(ModelRefused) as raised:
            models.chat("m", "s", "u", 10)
        self.assertEqual(len(script.calls), 1)
        self.assertIn("the AI Gateway did not accept the app's token", str(raised.exception))
        self.assertIn(AUDIENCE, str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))

    def test_a_403_is_a_refusal_that_names_the_role_and_is_not_repeated(self):
        models, script, _ = models_with((403, {}, b'{"error":{"code":"PermissionDenied","message":"no role"}}'))
        with self.assertRaises(ModelRefused) as raised:
            models.chat("m", "s", "u", 10)
        self.assertEqual(len(script.calls), 1)
        self.assertIn("the AI Gateway refused the app's identity", str(raised.exception))
        self.assertIn("AI Gateway Models User", str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))

    def test_a_429_with_a_long_retry_after_is_a_refusal_that_is_not_waited_for(self):
        sleeps = []
        models, script, _ = models_with((429, {"retry-after": "86400"}, b'{"error":{"code":"429","message":"quota"}}'))
        models.client.sleep = sleeps.append
        with self.assertRaises(ModelRefused) as raised:
            models.chat("m", "s", "u", 10)
        self.assertEqual((len(script.calls), sleeps), (1, []))
        self.assertIn("the AI Gateway told the call to wait", str(raised.exception))

    def test_a_rate_limit_of_a_few_seconds_is_waited_for(self):
        sleeps = []
        models, script, _ = models_with((429, {"retry-after": "5"}, b"{}"), completion("later"))
        models.client.sleep = sleeps.append
        self.assertEqual(models.chat("m", "s", "u", 10).text, "later")
        self.assertEqual(sleeps, [5.0])
        self.assertEqual(len(script.calls), 2)

    def test_a_429_without_a_retry_after_is_made_again_twice_with_a_pause_and_then_is_a_refusal(self):
        sleeps = []
        models, script, _ = models_with((429, {}, b'{"error":{"code":"429","message":"slow down"}}'))
        models.client.sleep = sleeps.append
        with self.assertRaises(ModelRefused):
            models.chat("m", "s", "u", 10)
        self.assertEqual(len(script.calls), 3, "the call and two repeats")
        self.assertEqual(sleeps, [1.5, 3.0], "a pause that grows, with the jitter of the test")

    def test_a_404_is_an_alias_that_the_gateway_does_not_know_and_not_a_refusal(self):
        models, script, _ = models_with((404, {}, b'{"error":{"code":"404","message":"alias not found"}}'), completion("never asked"))
        with self.assertRaises(ModelError) as raised:
            models.chat("gpt-6-luna", "s", "u", 10)
        self.assertNotIsInstance(raised.exception, ModelRefused)
        self.assertEqual(len(script.calls), 1, "no other route is asked: there is none")
        said = str(raised.exception)
        self.assertIn("the AI Gateway knows no alias named gpt-6-luna", said)
        self.assertIn("alias not found", said, "the words of the service follow")

    def test_a_400_says_that_the_gateway_did_not_accept_the_call_and_what_to_check(self):
        models, script, _ = models_with((400, {}, b'{"error":{"code":"content_filter","message":"blocked"}}'), completion("never asked"))
        with self.assertRaises(ModelError) as raised:
            models.chat("gpt-6-luna", "s", "u", 10)
        self.assertNotIsInstance(raised.exception, ModelRefused)
        self.assertEqual(len(script.calls), 1)
        said = str(raised.exception)
        self.assertIn("the AI Gateway did not accept the call", said)
        self.assertIn("gpt-6-luna is an alias that takes chat completions", said)
        self.assertIn("content_filter", said)

    def test_a_server_error_is_a_failure_that_is_not_a_refusal(self):
        models, _, _ = models_with((502, {}, b"{}"))
        with self.assertRaises(ModelError) as raised:
            models.chat("m", "s", "u", 10)
        self.assertNotIsInstance(raised.exception, ModelRefused)
        self.assertIn("the AI Gateway gave no answer to the model call", str(raised.exception))

    def test_a_call_that_may_already_have_been_carried_out_is_not_made_again(self):
        for answer in (urllib.error.URLError("down"), TimeoutError("slow"), (500, {}, b"{}"), (502, {}, b"{}"), (504, {}, b"{}")):
            models, script, _ = models_with(answer, completion("twice"))
            with self.assertRaises(ModelError, msg=str(answer)):
                models.chat("m", "s", "u", 10)
            self.assertEqual(len(script.calls), 1, "one call of the model, and a failure that does not say 'not now' is not repeated")

    def test_a_refusal_that_says_not_now_is_made_again_and_only_twice(self):
        models, script, _ = models_with((503, {}, b"{}"), completion("later"))
        self.assertEqual(models.chat("m", "s", "u", 10).text, "later")
        self.assertEqual(len(script.calls), 2)
        models, script, _ = models_with((503, {}, b"{}"))
        with self.assertRaises(ModelError):
            models.chat("m", "s", "u", 10)
        self.assertEqual(len(script.calls), 3, "the call and two repeats")

    def test_a_usage_that_is_not_valid_is_refused(self):
        for usage in ({"prompt_tokens": -5, "completion_tokens": 4, "total_tokens": -1}, {"prompt_tokens": 5, "completion_tokens": -4},
                      {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": -9}):
            models, _, _ = models_with(ok({"choices": [{"message": {"content": "x"}}], "usage": usage}))
            with self.assertRaises(ModelError, msg=str(usage)) as raised:
                models.chat("m", "s", "u", 10)
            self.assertIn("usage that is not valid", str(raised.exception))

    def test_the_total_is_never_less_than_the_sum_of_the_parts(self):
        models, _, _ = models_with(ok({"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 5}}))
        self.assertEqual(models.chat("m", "s", "u", 10).total_tokens, 7)
        models, _, _ = models_with(ok({"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 20}}))
        self.assertEqual(models.chat("m", "s", "u", 10).total_tokens, 20)

    def test_the_total_is_the_sum_when_the_service_reports_none(self):
        models, _, _ = models_with(ok({"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4}}))
        self.assertEqual(models.chat("m", "s", "u", 10).total_tokens, 7)

    def test_an_answer_that_is_not_a_completion_is_an_error(self):
        for answer in (ok({}), ok({"choices": []}), ok({"choices": [{}]}), ok({"choices": [{"message": {"content": "x"}}], "usage": {"total_tokens": "many"}}),
                       ok([1]), (200, {}, b"<html>a page, not a completion</html>")):
            models, _, _ = models_with(answer)
            with self.assertRaises(ModelError, msg=str(answer)) as raised:
                models.chat("m", "s", "u", 10)
            self.assertNotIsInstance(raised.exception, ModelRefused)
        for answer in (ok({}), ok({"choices": []}), ok({"choices": [{}]})):
            models, _, _ = models_with(answer)
            with self.assertRaises(ModelError) as raised:
                models.chat("m", "s", "u", 10)
            self.assertEqual(str(raised.exception), "the answer of the AI Gateway is not a completion")

    def test_a_model_that_gave_no_text_says_so_and_one_that_spent_its_whole_budget_on_reasoning_says_that(self):
        for empty in ("", "   "):
            models, _, _ = models_with(completion(empty, finish="stop"))
            with self.assertRaises(ModelError) as raised:
                models.chat("m", "s", "u", 10)
            self.assertEqual(str(raised.exception), "the model gave no text")
        models, _, _ = models_with(completion("", finish="length"))
        with self.assertRaises(ModelError) as raised:
            models.chat("m", "s", "u", 10)
        self.assertIn("completion budget", str(raised.exception))


class TheRoute(unittest.TestCase):
    """There is one route, the gateway's, and no direct path to a model: the call has no other address and no fallback."""

    def test_the_call_goes_to_the_host_of_the_gateway_and_to_no_other_address_even_when_a_foundry_project_is_set(self):
        models, script, _ = models_with(completion(), completion())
        self.assertTrue(models.settings.foundry_endpoint, "the project's address is set, and nothing of it is used")
        models.chat("m", "s", "u", 10)
        models.chat("m", "s", "u", 10)
        self.assertEqual([call[1] for call in script.calls], [URL, URL])

    def test_the_host_comes_from_the_setting_and_only_from_it(self):
        other = "aigw-other-89abcdef.eastus2-01.ai.gateway.azure.com"
        models, script, _ = models_with(completion(), env={**ENV, "AIGATEWAY_HOST": other.upper()})
        models.chat("m", "s", "u", 10)
        self.assertEqual(script.calls[0][1], f"https://{other}/default/models/openai/v1/chat/completions", "the host is trimmed and in lower case")

    def test_the_client_of_the_app_refuses_a_chat_completion_to_the_foundry_resource_and_to_the_project(self):
        models, script, _ = models_with(completion())
        host = FOUNDRY_ENDPOINT.split("/api/")[0]
        for url in (f"{FOUNDRY_ENDPOINT}/openai/v1/chat/completions", f"{host}/openai/v1/chat/completions", f"{host}/openai/deployments/gpt-6-luna/chat/completions"):
            with self.assertRaises(Refused, msg=url):
                models.client.request("POST", url, body={"model": "gpt-6-luna"})
        self.assertEqual(script.calls, [], "no direct path to a model: nothing left the app")

    def test_a_service_that_echoes_the_key_style_headers_does_not_get_them_into_an_error(self):
        models, _, _ = models_with((400, {"api-key": KEY}, json.dumps({"error": {"code": "Bad", "message": f"api-key: {KEY} and authorization: Bearer {TOKEN}"}}).encode()))
        with self.assertRaises(ModelError) as raised:
            models.chat("m", "s", "u", 10)
        self.assertNotIn(KEY, str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
