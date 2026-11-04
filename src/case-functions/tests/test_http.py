import json
import unittest
import urllib.error

from support import GATEWAY_GROUP, KEY, PRODUCT_SUBSCRIPTION, SUBSCRIPTION
from cases import http
from cases.redact import Redactor

ARG = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
COST = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
ADVISOR = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Advisor/recommendations?api-version=2023-01-01&$filter=Category%20eq%20%27Cost%27"
LOCKS = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Authorization/locks?api-version=2016-09-01"
SECRETS = f"https://management.azure.com{PRODUCT_SUBSCRIPTION}/listSecrets?api-version=2024-05-01"
CHAT = "https://example-apim.azure-api.net/models/chat/completions"


class Script:
    """A transport that answers from a list, one answer for each call, and remembers the calls."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, method, url, headers, data, timeout):
        self.calls.append((method, url, dict(headers), data, timeout))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def client(*answers, redact=None):
    sleeps = []
    script = Script(*answers)
    allowed = http.allowed_calls("example-apim.azure-api.net", f"{PRODUCT_SUBSCRIPTION}/listSecrets")
    return http.Client(allowed, redact or Redactor(), transport=script, sleep=sleeps.append, jitter=lambda: 0.5), script, sleeps


def ok(document=None):
    return 200, {}, json.dumps(document if document is not None else {"ok": True}).encode()


class TheList(unittest.TestCase):
    def test_the_calls_of_the_app_are_allowed(self):
        c, script, _ = client(ok())
        for method, url in (("POST", ARG), ("POST", COST), ("GET", ADVISOR), ("GET", LOCKS), ("POST", SECRETS), ("POST", CHAT)):
            c.request(method, url)
        self.assertEqual(len(script.calls), 6)

    def test_nothing_else_is_allowed(self):
        c, script, _ = client(ok())
        arm = "https://management.azure.com"
        refused = [
            ("PUT", f"{arm}/subscriptions/{SUBSCRIPTION}/resourceGroups/rg?api-version=2021-04-01"),
            ("DELETE", f"{arm}{GATEWAY_GROUP}/subscriptions/meternaut-agents-sub-01?api-version=2024-05-01"),
            ("PATCH", f"{arm}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Advisor/recommendations"),
            ("POST", f"{arm}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Advisor/recommendations"),
            ("GET", ARG.split("?")[0]),
            ("POST", f"{arm}/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm/deallocate"),
            ("POST", f"{arm}{PRODUCT_SUBSCRIPTION}/regeneratePrimaryKey"),
            ("POST", f"{arm}{GATEWAY_GROUP}/subscriptions/another/listSecrets"),
            ("POST", f"{arm}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/exports"),
            ("POST", "https://management.azure.com.evil.example/providers/Microsoft.ResourceGraph/resources"),
            ("POST", "http://management.azure.com/providers/Microsoft.ResourceGraph/resources"),
            ("POST", "https://example-apim.azure-api.net/models/other"),
            ("POST", "https://other-apim.azure-api.net/models/chat/completions"),
            ("GET", "https://graph.microsoft.com/v1.0/me"),
            ("POST", "https://login.microsoftonline.com/common/oauth2/token"),
        ]
        for method, url in refused:
            with self.assertRaises(http.Refused, msg=f"{method} {url}"):
                c.request(method, url)
        self.assertEqual(script.calls, [], "nothing left the app")

    def test_a_query_string_does_not_change_what_a_call_is(self):
        c, _, _ = client(ok())
        with self.assertRaises(http.Refused):
            c.request("PUT", ARG)
        c.request("POST", ARG + "&x=1")


class Retries(unittest.TestCase):
    def test_a_good_answer_is_returned_with_its_json(self):
        c, script, sleeps = client(ok({"a": 1}))
        response = c.request("POST", ARG, headers={"Authorization": "Bearer t"}, body={"q": 1}, timeout=7)
        self.assertEqual(response.json(), {"a": 1})
        method, url, headers, data, timeout = script.calls[0]
        self.assertEqual((method, json.loads(data), timeout, sleeps), ("POST", {"q": 1}, 7, []))
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_server_errors_and_network_errors_are_retried_twice_with_a_pause(self):
        for first in ((503, {}, b"{}"), (500, {}, b"{}"), (502, {}, b"{}"), (504, {}, b"{}"), urllib.error.URLError("down"), TimeoutError("slow"), ConnectionResetError()):
            c, script, sleeps = client(first, first, ok())
            self.assertEqual(c.request("GET", LOCKS).status, 200, first)
            self.assertEqual((len(script.calls), len(sleeps)), (3, 2), first)
            self.assertTrue(all(0 < s <= 30 for s in sleeps))

    def test_after_two_retries_the_call_fails_and_says_what_happened(self):
        c, script, _ = client((503, {}, b'{"error":{"code":"ServiceUnavailable","message":"later"}}'))
        with self.assertRaises(http.HttpError) as raised:
            c.request("GET", LOCKS)
        self.assertEqual(len(script.calls), 3)
        self.assertEqual(raised.exception.status, 503)
        self.assertIn("ServiceUnavailable: later", str(raised.exception))

    def test_a_client_error_is_not_retried(self):
        for status in (400, 401, 403, 404):
            c, script, sleeps = client((status, {}, b"{}"))
            with self.assertRaises(http.HttpError) as raised:
                c.request("GET", LOCKS)
            self.assertEqual((raised.exception.status, len(script.calls), sleeps), (status, 1, []))

    def test_throttling_waits_as_long_as_it_is_told_up_to_a_minute(self):
        c, script, sleeps = client((429, {"retry-after": "12"}, b"{}"), ok())
        self.assertEqual(c.request("POST", COST).status, 200)
        self.assertEqual(sleeps, [12.0])

    def test_a_service_specific_retry_after_header_counts_too(self):
        c, _, sleeps = client((429, {"x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "9"}, b"{}"), ok())
        c.request("POST", COST)
        self.assertEqual(sleeps, [9.0])

    def test_a_long_wait_is_a_refusal_not_a_wait(self):
        c, script, sleeps = client((429, {"retry-after": "3600"}, b'{"statusCode":429,"message":"quota"}'))
        with self.assertRaises(http.HttpError) as raised:
            c.request("POST", CHAT)
        self.assertEqual((raised.exception.status, len(script.calls), sleeps), (429, 1, []))
        self.assertEqual(raised.exception.retry_after, 3600.0)

    def test_throttling_without_a_hint_is_retried_like_a_server_error(self):
        c, script, sleeps = client((429, {}, b"{}"), ok())
        c.request("POST", COST)
        self.assertEqual((len(script.calls), len(sleeps)), (2, 1))

    def test_the_retries_are_a_parameter(self):
        c, script, _ = client((503, {}, b"{}"))
        with self.assertRaises(http.HttpError):
            c.request("GET", LOCKS, retries=0)
        self.assertEqual(len(script.calls), 1)


class Errors(unittest.TestCase):
    def test_an_error_text_holds_the_code_and_a_short_message_and_never_a_header_or_a_secret(self):
        redact = Redactor()
        redact.add(KEY)
        c, _, _ = client((403, {"api-key": KEY}, json.dumps({"error": {"code": "Forbidden", "message": f"the key {KEY} may not do this " + "x" * 500}}).encode()),
                         redact=redact)
        with self.assertRaises(http.HttpError) as raised:
            c.request("GET", LOCKS, headers={"api-key": KEY, "Authorization": "Bearer abcdefgh12345678"})
        text = str(raised.exception)
        self.assertNotIn(KEY, text)
        self.assertNotIn("abcdefgh12345678", text)
        self.assertLess(len(text), 400)
        self.assertIn("403 Forbidden", text)

    def test_a_body_that_is_not_json_is_cut_short(self):
        c, _, _ = client((502, {}, b"<html>" + b"y" * 1000))
        with self.assertRaises(http.HttpError) as raised:
            c.request("GET", LOCKS, retries=0)
        self.assertLess(len(str(raised.exception)), 250)

    def test_a_good_answer_that_is_not_json_is_an_error_when_read_as_json(self):
        c, _, _ = client((200, {}, b"not json"))
        with self.assertRaises(http.HttpError):
            c.request("GET", LOCKS).json()

    def test_an_empty_body_is_none(self):
        c, _, _ = client((200, {}, b""))
        self.assertIsNone(c.request("GET", LOCKS).json())

    def test_a_network_failure_says_its_kind_and_nothing_else(self):
        c, _, _ = client(OSError(f"cannot reach host with {KEY}"))
        with self.assertRaises(http.HttpError) as raised:
            c.request("GET", LOCKS, retries=0)
        self.assertEqual(raised.exception.status, 0)
        self.assertNotIn(KEY, str(raised.exception))
        self.assertIn("network error: OSError", str(raised.exception))


class RetryAfter(unittest.TestCase):
    def test_the_header_is_read_in_any_case_after_lower_casing_and_a_bad_value_is_ignored(self):
        self.assertEqual(http.retry_after({"retry-after": "5"}), 5.0)
        self.assertEqual(http.retry_after({"x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "7.5"}), 7.5)
        self.assertIsNone(http.retry_after({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}))
        self.assertIsNone(http.retry_after({"content-type": "x"}))


if __name__ == "__main__":
    unittest.main()
