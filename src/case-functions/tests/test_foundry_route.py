"""Tests of the fixed words for a call of an agent whose model goes through a connection of the Foundry project (docs/proposals/08-ai-gateway.md, step 2).

No network and no Azure: the fake service of test_foundry answers in the shapes of its REST reference. What the real Agent Service says when the gateway refuses a call is NOT known (nothing of this has run). These tests
pin what the client does with a status and with words, so that a person can act on the History: they do not claim to know what the service says.
"""
import unittest

from support import APP_ROOT  # noqa: F401  (puts the app on the path)
from test_foundry import JWT, NAME, PASS, TOKEN, Handler, Lookup, Rig, call, message, reply, spec
from cases import foundry as fo
from cases.foundry import FoundryError

ROUTED = "aigateway/gpt-6.1-sol"
START = "the model call through the connection aigateway failed: "
# (status, code, message, what the fixed words say happened, what they say to check)
KINDS = (
    (401, "Unauthorized", "The gateway did not accept the token: the audience is wrong.", "the gateway did not accept the token of the project",
     "Check the audience and the service principal."),
    (403, "PermissionDenied", "The gateway refused the identity of the project.", "the gateway refused the project's identity",
     "Check its role AI Gateway Models User on the gateway."),
    (404, "model_not_found", "The model does not exist on the connection.", "the connection or the model was not found",
     "Check the target and the model names of the connection."),
    (429, "rate_limit_exceeded", "Too many requests.", "the call was told to wait", "Check the limits of the gateway and of the model."),
    (502, "bad_gateway", "", "the gateway did not answer well", "Run aigateway-check and read the status of the Agent Service."),
    (424, "failed_dependency", "The call failed.", "the call to the gateway failed", "Read the log of the gateway."),
    (400, "invalid_request", "The connection is not valid.", "the connection or the gateway cannot be used", "Check the connection in the project."),
)
NOT_FOUND = (KINDS[2][3], KINDS[2][4])


def failing(status, code, words, **headers):
    """An answer of the service with an error object. A 429 comes with a long Retry-After, so that the client does not wait and repeat: it raises at once."""
    if status == 429:
        headers.setdefault("retry-after", "3600")
    return status, headers, {"error": {"code": code, "message": words}}


def expected(cause, check, status, code):
    detail = ", ".join(part for part in (f"HTTP {status}" if status else "", f"code {code}" if code else "") if part)
    return f"{START}{cause}" + (f" ({detail})" if detail else "") + f". {check}"


def routed_rig(model=ROUTED, **options):
    rig = Rig(**options)
    rig.foundry.ensure_agent(spec(model=model))
    return rig


class RouteTest(unittest.TestCase):
    def raises(self, action):
        with self.assertRaises(FoundryError) as raised:
            action()
        return raised.exception

    def response_fails(self, rig, planned):
        rig.service.failures["POST responses"] = planned
        return self.raises(rig.run)


class TheFixedWordsOfAFailedCall(RouteTest):
    def test_each_kind_of_answer_has_its_cause_and_what_to_check_and_the_status_and_the_code_of_the_service(self):
        for status, code, words, cause, check in KINDS:
            with self.subTest(status=status):
                error = self.response_fails(routed_rig(), failing(status, code, words))
                self.assertEqual(error.route, expected(cause, check, status, code))
                self.assertEqual((error.status, error.code), (status, code))

    def test_the_text_of_the_error_is_what_it_always_was(self):
        error = self.response_fails(routed_rig(), failing(404, "model_not_found", "The model does not exist on the connection."))
        self.assertEqual(str(error), "Foundry response failed: HTTP 404; DNS of the endpoint host: private; model_not_found: The model does not exist on the connection.")
        self.assertEqual(error.words, "model_not_found: The model does not exist on the connection.")
        error = self.response_fails(routed_rig(), failing(429, "rate_limit_exceeded", "Slow down"))
        self.assertEqual(str(error), "Foundry response failed: HTTP 429; rate_limit_exceeded: Slow down")

    def test_a_plain_deployment_name_has_no_fixed_words_whatever_the_answer(self):
        for status, code, words, *_ in KINDS:
            with self.subTest(status=status):
                error = self.response_fails(routed_rig("gpt-6.1-sol"), failing(status, code, words))
                self.assertEqual((error.route, error.status, error.code), ("", status, code))

    def test_an_agent_that_this_client_did_not_make_sure_of_has_no_fixed_words(self):
        error = self.response_fails(Rig(), failing(404, "model_not_found", "The model does not exist on the connection."))
        self.assertEqual(error.route, "")

    def test_the_model_of_each_agent_is_the_one_that_counts_for_its_calls(self):
        rig = routed_rig()
        skeptic = rig.foundry.ensure_agent(spec(name="meternaut-skeptic", model="gpt-6-luna"))
        rig.service.failures["POST responses"] = failing(404, "model_not_found", "The model does not exist on the connection.")
        plain = self.raises(lambda: rig.foundry.run(skeptic, "Judge.", None, max_calls=0))
        routed = self.raises(lambda: rig.foundry.run(f"{NAME}:3", "Look.", None))
        self.assertEqual((plain.route, routed.route), ("", expected(*NOT_FOUND, 404, "model_not_found")))

    def test_an_answer_about_something_else_keeps_its_own_words_and_gets_no_fixed_words(self):
        others = ((400, "invalid_request_error", "The conversation is not valid."), (500, "server_error", "The server had an error while processing your request."),
                  (401, "Unauthorized", "Access token is missing or invalid."), (403, "PermissionDenied", "The principal lacks the data action on the project."),
                  (404, "not_found", "The agent was not found."), (409, "conflict", "The agent exists."), (422, "unprocessable", "Unknown parameter."), (400, "", ""))
        for status, code, words in others:
            with self.subTest(status=status, words=words):
                error = self.response_fails(routed_rig(), failing(status, code, words))
                self.assertEqual(error.route, "")
                self.assertIn(f"HTTP {status}", str(error))

    def test_a_failure_of_the_network_or_an_answer_that_is_not_json_is_no_failure_of_the_route(self):
        error = self.response_fails(routed_rig(), (200, {}, b"not json"))
        self.assertEqual(error.route, "")
        error = self.response_fails(routed_rig(), TimeoutError("slow"))
        self.assertEqual((error.route, error.status), ("", None))

    def test_a_403_or_a_404_is_the_routes_only_when_the_host_of_the_project_leads_to_a_private_address(self):
        # Otherwise the call may have failed before it reached the project's endpoint: the text of the error says what the DNS says, and that is what a person has to read.
        for lookup, dns in ((Lookup("52.1.2.3"), "public"), (Lookup(error=OSError("no")), "unresolved")):
            for status, code, words in ((403, "PermissionDenied", "The gateway refused the identity of the project."), (404, "model_not_found", "The model does not exist.")):
                with self.subTest(dns=dns, status=status):
                    error = self.response_fails(routed_rig(lookup=lookup), failing(status, code, words))
                    self.assertEqual(error.route, "")
                    self.assertIn(f"DNS of the endpoint host: {dns}", str(error))
        for status, code, words in ((401, "Unauthorized", "The gateway did not accept the token."), (429, "rate_limit_exceeded", "Too many requests."), (502, "bad_gateway", "")):
            with self.subTest(status=status):
                self.assertTrue(self.response_fails(routed_rig(lookup=Lookup("52.1.2.3")), failing(status, code, words)).route)

    def test_a_response_that_completed_with_an_error_object_is_explained_by_its_code_and_its_words(self):
        for code, words, cause, check in (("model_not_found", "The model does not exist.", *NOT_FOUND), ("rate_limit_exceeded", "Rate limit is exceeded.", KINDS[3][3], KINDS[3][4]),
                                          ("upstream_error", "The upstream gateway failed.", KINDS[6][3], KINDS[6][4])):
            with self.subTest(code=code):
                rig = routed_rig()
                error = self.raises(lambda: rig.run(reply([message("x")], error={"code": code, "message": words})))
                self.assertEqual((error.status, error.route), (None, expected(cause, check, None, code)))
                self.assertEqual(str(error), f"Foundry response failed: the response failed; {code}: {words}")
        for answer in ({"code": "server_error", "message": "boom"}, {"code": "content_filter", "message": "The prompt was filtered."}, {"message": "boom"}):
            with self.subTest(answer=answer):
                rig = routed_rig()
                self.assertEqual(self.raises(lambda: rig.run(reply([message("x")], error=answer))).route, "")
        rig = routed_rig("gpt-6.1-sol")
        self.assertEqual(self.raises(lambda: rig.run(reply([message("x")], error={"code": "model_not_found", "message": "The model does not exist."}))).route, "")

    def test_the_calls_that_a_model_can_fail_are_the_ones_that_get_fixed_words(self):
        planned = failing(404, "model_not_found", "The model does not exist on the connection.")
        rig = Rig()
        rig.service.failures["POST agents"] = planned
        created = self.raises(lambda: rig.foundry.ensure_agent(spec(model=ROUTED)))
        rig = routed_rig()
        rig.service.failures["POST versions"] = planned
        versioned = self.raises(lambda: rig.foundry.ensure_agent(spec(model=ROUTED, instructions="Other instructions.")))
        rig = routed_rig()
        rig.service.replies = [reply([call("t", {}, "c1")])]
        rig.service.failures["POST responses"] = [PASS, planned]
        answered = self.raises(lambda: rig.foundry.run(f"{NAME}:3", "Look.", Handler()))
        for what, error in (("create agent", created), ("new version", versioned), ("function output", answered)):
            with self.subTest(what):
                self.assertIn(f"Foundry {what} failed", str(error))
                self.assertEqual(error.route, expected(*NOT_FOUND, 404, "model_not_found"))

    def test_the_calls_that_say_nothing_of_a_model_get_none_even_when_their_words_name_the_gateway(self):
        words = "The gateway did not accept the token and the connection failed upstream."
        rig = routed_rig()
        rig.service.failures["GET agent"] = failing(401, "Unauthorized", words)
        read = self.raises(lambda: rig.foundry.ensure_agent(spec(model=ROUTED)))
        rig = routed_rig()
        rig.service.failures["POST conversations"] = failing(401, "Unauthorized", words)
        conversation = self.raises(rig.run)
        for error in (read, conversation):
            self.assertEqual((error.route, error.status), ("", 401))

    def test_the_code_is_quoted_only_when_it_is_a_plain_token_that_the_redactor_leaves_alone(self):
        for code, quoted in (("model_not_found", "model_not_found"), (404, "404"), ("a" * 24, "a" * 24), ("a" * 25, ""), ("Bad Code", ""), ("a;b", ""), ("", ""),
                             (f"Invalid-{JWT}", ""), ("api-key=SECRETKEYVALUE", ""), (True, ""), ({"a": 1}, "")):
            with self.subTest(code=code):
                error = self.response_fails(routed_rig(), (404, {}, {"error": {"code": code, "message": "The model does not exist."}}))
                self.assertEqual(error.code, quoted)
                self.assertEqual(error.route, expected(*NOT_FOUND, 404, quoted))

    def test_a_token_a_header_or_the_message_of_the_service_never_reaches_the_fixed_words(self):
        words = f"The gateway refused the token {JWT} and Bearer abcdefgh12345678 and api-key: SECRETKEYVALUE and {TOKEN} for the project."
        error = self.response_fails(routed_rig(), failing(403, "PermissionDenied", words))
        self.assertEqual(error.route, expected(KINDS[1][3], KINDS[1][4], 403, "PermissionDenied"))
        for secret in (JWT, "abcdefgh12345678", "SECRETKEYVALUE", TOKEN, "api-key", "refused the token"):
            self.assertNotIn(secret, error.route)
        for secret in (JWT, "abcdefgh12345678", "SECRETKEYVALUE", TOKEN):
            self.assertNotIn(secret, str(error) + error.words, "the words of the service are redacted as they always were")

    def test_the_words_are_fixed_and_short_enough_for_the_notes_of_the_history_with_a_longer_code_than_any_real_one(self):
        for status, code, words, cause, check in KINDS:
            with self.subTest(status=status):
                text = fo.route_failure(ROUTED, "response", status, "c" * 24, words, "private")
                self.assertEqual(text, expected(cause, check, status, "c" * 24))
                self.assertLessEqual(len(text), 200, text)
        text = fo.route_failure(ROUTED, "response", None, "c" * 24, KINDS[2][2], "private")
        self.assertLessEqual(len(text), 200, text)

    def test_every_cause_and_every_check_is_a_plain_sentence_with_no_key_no_token_and_no_address(self):
        for _, _, _, cause, check in KINDS:
            for text in (cause, check):
                self.assertRegex(text, r"^[A-Za-z' -]+\.?$")
                for word in ("key", "secret", "password", "bearer", "http", "azure.com", "azure-api.net"):
                    self.assertNotIn(word, text.lower(), text)
            self.assertTrue(check.endswith(".") and check[0].isupper(), check)


class TheConnectionOfAModel(unittest.TestCase):
    def test_it_is_the_part_before_the_slash_of_a_name_with_two_parts_and_nothing_otherwise(self):
        for model, connection in (("aigateway/gpt-6.1-sol", "aigateway"), ("a/b", "a"), ("My_conn.1-x/Model.2", "My_conn.1-x"), ("x" * 64 + "/y", "x" * 64),
                                  ("gpt-6.1-sol", ""), ("", ""), ("/x", ""), ("x/", ""), ("a b/c", ""), ("-a/b", ""), ("x" * 65 + "/y", ""), (None, ""), (3, ""), (b"a/b", "")):
            with self.subTest(model=model):
                self.assertEqual(fo.connection_of(model), connection)

    def test_an_error_has_no_fixed_words_and_no_code_until_the_client_gives_them(self):
        error = FoundryError("x")
        self.assertEqual((str(error), error.status, error.words, error.code, error.route, error.partial), ("x", None, "", "", "", None))
        self.assertEqual(fo.route_failure(None, "response", 404, "c", "model not found"), "")
        self.assertEqual(fo.route_failure("gpt-6.1-sol", "response", 404, "c", "model not found"), "")
        self.assertEqual(fo.route_failure(ROUTED, "read agent", 404, "c", "model not found"), "")
        self.assertEqual(fo.route_failure(ROUTED, "delete conversation", 429, "c", "slow"), "")


if __name__ == "__main__":
    unittest.main()
