import json
import unittest
import urllib.error

from support import ENV, FOUNDRY_ENDPOINT, KEY, TOKEN
from cases import config
from cases.foundry import RESOURCE
from cases.http import Client, allowed_calls
from cases.identity import IdentityError
from cases.modelcalls import Models, ModelError, ModelRefused
from cases.redact import Redactor
from test_http import CHAT, RESOURCE_CHAT, Script, ok


def models_with(*answers, env=None, token=None):
    redact = Redactor()
    script = Script(*answers)
    settings = config.load(env or ENV)
    client = Client(allowed_calls(settings.foundry_endpoint), redact, transport=script, sleep=lambda s: None, jitter=lambda: 0.5)
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
    def test_a_run_opens_the_models_without_a_call_and_without_the_address_of_the_project(self):
        models, script, _ = models_with(completion())
        models.open()
        self.assertEqual((script.calls, models.asked), ([], []), "nothing is read first: the identity is the credential")
        without = {k: v for k, v in ENV.items() if k != "FOUNDRY_PROJECT_ENDPOINT"}
        models, script, _ = models_with(completion(), env=without)
        models.open()
        self.assertEqual(script.calls, [])

    def test_a_chat_without_the_address_of_the_project_is_an_error_of_that_one_call_and_makes_no_call(self):
        without = {k: v for k, v in ENV.items() if k != "FOUNDRY_PROJECT_ENDPOINT"}
        models, script, _ = models_with(completion(), env=without)
        with self.assertRaises(ModelError) as raised:
            models.chat("gpt-6-luna", "s", "u", 10)
        self.assertEqual(str(raised.exception), "the Foundry project's address is not set")
        self.assertNotIsInstance(raised.exception, ModelRefused)
        self.assertEqual((script.calls, models.asked), ([], []))

    def test_the_module_reads_no_key_and_names_no_gateway(self):
        import cases.modelcalls as module
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read().lower()
        for word in ("listsecrets", "primarykey", "api-key", "azure-api.net", "gateway", "subscription"):
            self.assertNotIn(word, source, word)


class Chat(unittest.TestCase):
    def test_the_request_goes_to_the_chat_route_of_the_project_with_the_token_the_model_and_the_cap(self):
        models, script, _ = models_with(completion("hello", 12, 8, 20))
        chat = models.chat("gpt-6-luna", "system words", "user words", 2000)
        self.assertEqual((chat.text, chat.prompt_tokens, chat.completion_tokens, chat.total_tokens), ("hello", 12, 8, 20))
        ((method, url, headers, data, timeout),) = script.calls
        self.assertEqual((method, url, timeout), ("POST", CHAT, 90))
        self.assertEqual(url, f"{FOUNDRY_ENDPOINT}/openai/v1/chat/completions")
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.assertNotIn("api-key", headers)
        self.assertEqual(models.asked, [RESOURCE], "the token is the one of https://ai.azure.com, as the agents' token is")
        self.assertEqual(json.loads(data), {"model": "gpt-6-luna", "messages": [{"role": "system", "content": "system words"}, {"role": "user", "content": "user words"}],
                                            "max_completion_tokens": 2000})

    def test_a_token_is_asked_for_every_call_so_that_an_old_one_is_never_kept(self):
        models, _, _ = models_with(completion())
        models.chat("m", "s", "u", 10)
        models.chat("m", "s", "u", 10)
        self.assertEqual(models.asked, [RESOURCE, RESOURCE])

    def test_the_token_is_not_in_the_text_of_an_error_even_when_the_service_echoes_it(self):
        models, _, _ = models_with((400, {}, json.dumps({"error": {"code": "Bad", "message": f"your token {TOKEN} is bad"}}).encode()))
        with self.assertRaises(ModelError) as raised:
            models.chat("gpt-6-luna", "s", "u", 10)
        for text in (str(raised.exception), repr(raised.exception.__cause__), str(raised.exception.__cause__)):
            self.assertNotIn(TOKEN, text)
        self.assertNotIn("Bearer", str(raised.exception))

    def test_a_token_that_cannot_be_had_is_an_error_of_that_call_and_makes_no_call(self):
        def refused(resource):
            raise IdentityError(f"the identity endpoint refused the request for {resource}")

        models, script, _ = models_with(completion(), token=refused)
        with self.assertRaises(ModelError) as raised:
            models.chat("m", "s", "u", 10)
        self.assertIn("no token could be had for the model service", str(raised.exception))
        self.assertEqual(script.calls, [])

    def test_a_403_a_401_and_a_long_429_are_refusals_that_are_not_retried(self):
        for answer in ((403, {}, b'{"error":{"code":"PermissionDenied","message":"no role"}}'), (401, {}, b'{"error":{"code":"Unauthorized","message":"bad token"}}'),
                       (429, {"retry-after": "86400"}, b'{"error":{"code":"429","message":"quota"}}')):
            models, script, _ = models_with(answer)
            with self.assertRaises(ModelRefused, msg=str(answer)) as raised:
                models.chat("m", "s", "u", 10)
            self.assertEqual(len(script.calls), 1)
            self.assertIn("the Foundry resource refused the model call on the project's route", str(raised.exception))
            self.assertNotIn(TOKEN, str(raised.exception))

    def test_a_rate_limit_of_a_few_seconds_is_waited_for(self):
        sleeps = []
        models, script, _ = models_with((429, {"retry-after": "5"}, b"{}"), completion("later"))
        models.client.sleep = sleeps.append
        self.assertEqual(models.chat("m", "s", "u", 10).text, "later")
        self.assertEqual(sleeps, [5.0])
        self.assertEqual(len(script.calls), 2)

    def test_a_server_error_is_a_failure_that_is_not_a_refusal(self):
        models, _, _ = models_with((502, {}, b"{}"))
        with self.assertRaises(ModelError) as raised:
            models.chat("m", "s", "u", 10)
        self.assertNotIsInstance(raised.exception, ModelRefused)
        self.assertIn("gave no answer to the model call", str(raised.exception))

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
                       ok([1]), completion(""), completion("   ")):
            models, _, _ = models_with(answer)
            with self.assertRaises(ModelError, msg=str(answer)):
                models.chat("m", "s", "u", 10)

    def test_a_model_that_gave_no_text_says_so_and_one_that_spent_its_whole_budget_on_reasoning_says_that(self):
        models, _, _ = models_with(completion("", finish="stop"))
        with self.assertRaises(ModelError) as raised:
            models.chat("m", "s", "u", 10)
        self.assertEqual(str(raised.exception), "the model gave no text")
        models, _, _ = models_with(completion("", finish="length"))
        with self.assertRaises(ModelError) as raised:
            models.chat("m", "s", "u", 10)
        self.assertIn("completion budget", str(raised.exception))


class TheRoute(unittest.TestCase):
    """What the first run of the service will show: which route takes a chat completion. The pages that were read show it on the resource and not on the project, so a route that is not served
    sends the call to the other one, once, and a failure says which routes were asked."""

    NOT_SERVED = (404, {}, b'{"error":{"code":"404","message":"Resource not found"}}')

    def test_a_404_of_the_projects_route_sends_the_call_once_to_the_route_of_the_resource_and_that_route_is_kept(self):
        models, script, _ = models_with(self.NOT_SERVED, completion("one"), completion("two"))
        self.assertEqual(models.chat("m", "s", "u", 10).text, "one")
        self.assertEqual(models.chat("m", "s", "u", 10).text, "two")
        self.assertEqual([call[1] for call in script.calls], [CHAT, RESOURCE_CHAT, RESOURCE_CHAT], "the second call does not try the route that was not served first")
        for call in script.calls:
            self.assertEqual(call[2]["Authorization"], f"Bearer {TOKEN}", "the same token, for the same host")

    def test_a_405_does_the_same(self):
        models, script, _ = models_with((405, {}, b"{}"), completion("one"))
        self.assertEqual(models.chat("m", "s", "u", 10).text, "one")
        self.assertEqual([call[1] for call in script.calls], [CHAT, RESOURCE_CHAT])

    def test_a_project_that_serves_the_route_is_never_asked_for_the_other_one(self):
        models, script, _ = models_with(completion("one"), completion("two"))
        models.chat("m", "s", "u", 10)
        models.chat("m", "s", "u", 10)
        self.assertEqual([call[1] for call in script.calls], [CHAT, CHAT])

    def test_when_neither_route_takes_the_call_the_error_says_which_routes_were_asked_and_what_each_answered(self):
        models, script, _ = models_with(self.NOT_SERVED)
        with self.assertRaises(ModelError) as raised:
            models.chat("gpt-6-luna", "s", "u", 10)
        said = str(raised.exception)
        self.assertEqual([call[1] for call in script.calls], [CHAT, RESOURCE_CHAT], "each route once, and nothing is repeated")
        self.assertNotIsInstance(raised.exception, ModelRefused)
        self.assertIn("no chat completions route took the call: POST /openai/v1/chat/completions, the project's route answered 404 and the resource's route answered 404", said)
        self.assertIn("Check that gpt-6-luna is a deployment of the resource", said)
        self.assertIn("Resource not found", said, "the words of the service follow")
        self.assertTrue(said[:200].count("answered 404") == 2, "the first 200 characters are what the History keeps of a failed role: they hold both answers")
        self.assertNotIn(TOKEN, said)

    def test_a_400_is_not_a_missing_route_and_says_which_route_did_not_accept_the_call(self):
        models, script, _ = models_with((400, {}, b'{"error":{"code":"invalid_model","message":"The model does not exist"}}'), completion("never asked"))
        with self.assertRaises(ModelError) as raised:
            models.chat("gpt-6-luna", "s", "u", 10)
        self.assertEqual(len(script.calls), 1)
        said = str(raised.exception)
        self.assertIn("the project's route (POST /openai/v1/chat/completions) did not accept the call", said)
        self.assertIn("check that gpt-6-luna is a deployment of the resource", said)
        self.assertIn("invalid_model", said)

    def test_a_refusal_after_a_fallback_names_the_route_that_refused(self):
        models, script, _ = models_with(self.NOT_SERVED, (403, {}, b'{"error":{"code":"PermissionDenied","message":"no role"}}'))
        with self.assertRaises(ModelRefused) as raised:
            models.chat("m", "s", "u", 10)
        self.assertEqual(len(script.calls), 2)
        self.assertIn("on the resource's route", str(raised.exception))

    def test_a_route_that_stops_being_served_sends_the_call_back_to_the_other_one(self):
        models, script, _ = models_with(self.NOT_SERVED, completion("a"), self.NOT_SERVED, completion("b"))
        models.chat("m", "s", "u", 10)
        self.assertEqual(models.chat("m", "s", "u", 10).text, "b")
        self.assertEqual([call[1] for call in script.calls], [CHAT, RESOURCE_CHAT, RESOURCE_CHAT, CHAT])

    def test_the_two_routes_are_on_the_host_of_the_project_and_nowhere_else(self):
        models, _, _ = models_with(completion())
        routes = models.routes()
        self.assertEqual([url for _, url in routes], [CHAT, RESOURCE_CHAT])
        self.assertEqual({url.split("/")[2] for _, url in routes}, {FOUNDRY_ENDPOINT.split("/")[2]})

    def test_a_service_that_echoes_the_key_style_headers_does_not_get_them_into_an_error(self):
        models, _, _ = models_with((400, {"api-key": KEY}, json.dumps({"error": {"code": "Bad", "message": f"api-key: {KEY} and authorization: Bearer {TOKEN}"}}).encode()))
        with self.assertRaises(ModelError) as raised:
            models.chat("m", "s", "u", 10)
        self.assertNotIn(KEY, str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
