import json
import re
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from support import KEY, SUBSCRIPTION
from cases import http
from cases.redact import Redactor

ENDPOINT = "https://example-account.services.ai.azure.com/api/projects/meternaut"
GATEWAY = "aigw-meternaut-0123abcd.swedencentral-01.ai.gateway.azure.com"
ARG = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
COST = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
ADVISOR = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Advisor/recommendations?api-version=2023-01-01&$filter=Category%20eq%20%27Cost%27"
LOCKS = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Authorization/locks?api-version=2016-09-01"
SUBSCRIPTIONS = "https://management.azure.com/subscriptions?api-version=2022-12-01"
# The one route of a chat completion that the app may call: the AI Gateway's. The Foundry project's and the Foundry resource's own routes are not on the list.
CHAT = f"https://{GATEWAY}/default/models/openai/v1/chat/completions"
DIRECT_CHAT = f"{ENDPOINT}/openai/v1/chat/completions"
DIRECT_RESOURCE_CHAT = "https://example-account.services.ai.azure.com/openai/v1/chat/completions"


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
    allowed = http.allowed_calls(ENDPOINT, GATEWAY)
    return http.Client(allowed, redact or Redactor(), transport=script, sleep=sleeps.append, jitter=lambda: 0.5), script, sleeps


def ok(document=None):
    return 200, {}, json.dumps(document if document is not None else {"ok": True}).encode()


class TheList(unittest.TestCase):
    def test_the_calls_of_the_app_are_allowed(self):
        c, script, _ = client(ok())
        for method, url in (("POST", ARG), ("POST", COST), ("GET", ADVISOR), ("GET", LOCKS), ("POST", CHAT), ("GET", SUBSCRIPTIONS)):
            c.request(method, url)
        self.assertEqual(len(script.calls), 6)

    def test_the_watch_without_a_foundry_project_makes_the_reads_of_azure_and_nothing_else(self):
        plain = http.allowed_calls()
        self.assertEqual(len(plain), 24, "nineteen, the four reads of the capability profile (cases/capability.py) and the read of the display name of one subscription")
        self.assertEqual(sorted(method for method, _ in plain), ["GET"] * 21 + ["POST"] * 3)
        for method, pattern in plain:
            self.assertTrue(pattern.pattern.startswith(re.escape("https://management.azure.com")) or pattern.pattern.startswith(re.escape("https://api.loganalytics.azure.com/v1/workspaces/")),
                            pattern.pattern)
            if pattern.pattern.startswith(re.escape("https://api.loganalytics.azure.com")):
                self.assertEqual((method, pattern.pattern.endswith("/query")), ("POST", True), "the one call to the Logs query API asks a question and is on one host")
        c = http.Client(plain, Redactor(), transport=Script(ok()), sleep=lambda s: None)
        for method, url in (("POST", CHAT), ("POST", DIRECT_CHAT), ("POST", DIRECT_RESOURCE_CHAT), ("POST", "https://management.azure.com/subscriptions/" + SUBSCRIPTION +
                                                                        "/resourceGroups/rg/providers/Microsoft.ApiManagement/service/x/subscriptions/y/listSecrets")):
            with self.assertRaises(http.Refused, msg=url):
                c.request(method, url)

    def test_the_one_call_to_the_ai_gateway_is_one_exact_post_on_its_host_and_its_route(self):
        calls = http.ai_gateway_calls(GATEWAY)
        self.assertEqual([(m, p.pattern) for m, p in calls], [("POST", re.escape(f"https://{GATEWAY}/default/models/openai/v1/chat/completions"))])
        plain = http.allowed_calls()
        self.assertEqual(http.allowed_calls(None, GATEWAY), plain + calls, "the gateway's call is added to the reads of Azure, after them")
        self.assertEqual(http.allowed_calls(ENDPOINT, GATEWAY)[-1:], calls)
        self.assertEqual(http.allowed_calls(ENDPOINT, GATEWAY)[:len(http.allowed_calls(ENDPOINT))], http.allowed_calls(ENDPOINT))

    def test_everything_around_the_one_route_of_the_gateway_is_refused(self):
        c, script, _ = client(ok())
        refused = [
            ("GET", CHAT),
            ("PUT", CHAT),
            ("PATCH", CHAT),
            ("DELETE", CHAT),
            ("POST", CHAT + "/extra"),
            ("POST", CHAT[:-1]),
            ("POST", f"https://{GATEWAY}/default/models/openai/v1/responses"),
            ("POST", f"https://{GATEWAY}/default/models/openai/v1/embeddings"),
            ("POST", f"https://{GATEWAY}/default/models"),
            ("GET", f"https://{GATEWAY}/default/models"),
            ("POST", f"https://{GATEWAY}/default/models/openai/v1/chat/completions/"),
            ("POST", f"https://{GATEWAY}/openai/v1/chat/completions"),
            ("POST", f"https://{GATEWAY}/default/tools/mcp"),
            ("POST", f"https://{GATEWAY}/other/models/openai/v1/chat/completions"),
            ("POST", f"https://{GATEWAY.upper()}/default/models/openai/v1/chat/completions"),
            ("POST", f"http://{GATEWAY}/default/models/openai/v1/chat/completions"),
            ("POST", f"https://{GATEWAY}:8443/default/models/openai/v1/chat/completions"),
            ("POST", f"https://user@{GATEWAY}/default/models/openai/v1/chat/completions"),
            ("POST", f"https://{GATEWAY}.evil.example/default/models/openai/v1/chat/completions"),
            ("POST", f"https://evil.example/{GATEWAY}/default/models/openai/v1/chat/completions"),
            ("POST", f"https://aigw-other-89abcdef.eastus2-01.ai.gateway.azure.com/default/models/openai/v1/chat/completions"),
            ("POST", f"https://{GATEWAY.replace('.', '-')}/default/models/openai/v1/chat/completions"),
            ("POST", "https://example-apim.azure-api.net/default/models/openai/v1/chat/completions"),
            ("POST", f"https://api.openai.com/default/models/openai/v1/chat/completions"),
        ]
        for method, url in refused:
            with self.assertRaises(http.Refused, msg=f"{method} {url}"):
                c.request(method, url)
        self.assertEqual(script.calls, [], "nothing left the app")

    def test_the_host_of_the_gateway_is_checked_when_the_list_is_made(self):
        for host in ("", "evil.example.com", "ai.gateway.azure.com", ".ai.gateway.azure.com", GATEWAY.upper(), f"https://{GATEWAY}", f"{GATEWAY}/default", f"{GATEWAY}:443",
                     f"a b.{GATEWAY}", f"{GATEWAY}.evil.example.com", "-x.ai.gateway.azure.com", "x_y.ai.gateway.azure.com", "x" * 250 + ".ai.gateway.azure.com",
                     "example.azure-api.net", "x.services.ai.azure.com"):
            with self.assertRaises(ValueError, msg=host[:60]):
                http.ai_gateway_calls(host)
            with self.assertRaises(ValueError, msg=host[:60]):
                http.allowed_calls(None, host)
        http.ai_gateway_calls("a.ai.gateway.azure.com")
        http.ai_gateway_calls(GATEWAY)

    def test_no_chat_completion_to_the_foundry_project_or_resource_is_allowed_even_with_both_lists(self):
        c, script, _ = client(ok())
        for method, url in (("POST", DIRECT_CHAT), ("POST", DIRECT_RESOURCE_CHAT), ("POST", f"{ENDPOINT}/openai/chat/completions"), ("GET", DIRECT_CHAT)):
            with self.assertRaises(http.Refused, msg=url):
                c.request(method, url)
        self.assertEqual(script.calls, [])
        for _, pattern in http.allowed_calls(ENDPOINT, GATEWAY):
            if "services" in pattern.pattern:
                self.assertNotIn("chat", pattern.pattern, "the Foundry list holds no chat completion")
        self.assertFalse(hasattr(http, "CHAT_PATH") or hasattr(http, "resource_of"), "the direct routes and their helpers are gone")

    def test_nothing_else_is_allowed(self):
        c, script, _ = client(ok())
        arm = "https://management.azure.com"
        refused = [
            ("PUT", f"{arm}/subscriptions/{SUBSCRIPTION}/resourceGroups/rg?api-version=2021-04-01"),
            ("DELETE", f"{arm}/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/Microsoft.Compute/disks/d?api-version=2024-03-02"),
            ("PATCH", f"{arm}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Advisor/recommendations"),
            ("POST", f"{arm}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Advisor/recommendations"),
            ("GET", ARG.split("?")[0]),
            ("POST", f"{arm}/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm/deallocate"),
            ("POST", f"{arm}/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/Microsoft.ApiManagement/service/x/subscriptions/y/listSecrets"),
            ("POST", f"{arm}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/exports"),
            ("POST", "https://management.azure.com.evil.example/providers/Microsoft.ResourceGraph/resources"),
            ("POST", "http://management.azure.com/providers/Microsoft.ResourceGraph/resources"),
            ("POST", f"{ENDPOINT}/openai/v1/other"),
            ("POST", f"{ENDPOINT}/openai/v1/chat/completions/extra"),
            ("GET", CHAT),
            ("POST", "https://other-account.services.ai.azure.com/api/projects/meternaut/openai/v1/chat/completions"),
            ("POST", "https://other-account.services.ai.azure.com/openai/v1/chat/completions"),
            ("POST", "https://example-apim.azure-api.net/models/chat/completions"),
            ("POST", "https://example-account.openai.azure.com/openai/v1/chat/completions"),
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

    def test_the_one_get_of_the_list_of_subscriptions_is_allowed_and_nothing_around_it(self):
        # The Watch lists the subscriptions that its own identity can read (scope.py). That is the one call whose address ends at /subscriptions.
        arm = "https://management.azure.com"
        c, script, _ = client(ok())
        for url in (SUBSCRIPTIONS, f"{arm}/subscriptions?api-version=2022-12-01&$skiptoken=abc", f"{arm}/Subscriptions?api-version=2022-12-01"):
            c.request("GET", url)
        self.assertEqual(len(script.calls), 3)
        refused = [
            ("POST", f"{arm}/subscriptions?api-version=2022-12-01"),
            ("PUT", f"{arm}/subscriptions?api-version=2022-12-01"),
            ("DELETE", f"{arm}/subscriptions?api-version=2022-12-01"),
            ("GET", f"{arm}/subscriptions/?api-version=2022-12-01"),
            ("GET", f"{arm}/subscriptions/{SUBSCRIPTION}/resourcegroups?api-version=2021-04-01"),
            ("GET", f"{arm}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Compute/virtualMachines?api-version=2024-03-01"),
            ("GET", f"{arm}/subscriptions/{SUBSCRIPTION}/locations?api-version=2022-12-01"),
            ("GET", f"{arm}/tenants?api-version=2022-12-01"),
            ("GET", f"{arm}/providers/Microsoft.Management/managementGroups?api-version=2021-04-01"),
            ("GET", "https://management.azure.com.evil.example/subscriptions?api-version=2022-12-01"),
            ("GET", "http://management.azure.com/subscriptions?api-version=2022-12-01"),
            ("GET", "https://other.example/subscriptions"),
        ]
        for method, url in refused:
            with self.assertRaises(http.Refused, msg=f"{method} {url}"):
                c.request(method, url)
        self.assertEqual(len(script.calls), 3, "nothing else left the app")

    def test_the_one_get_of_a_subscription_gives_its_name_and_is_not_a_door_to_anything_below_it(self):
        # The display name of a subscription (Arm.subscription_name): the address ends at the id of the subscription, and only a GET of it is allowed.
        arm = "https://management.azure.com"
        c, script, _ = client(ok())
        for url in (f"{arm}/subscriptions/{SUBSCRIPTION}?api-version=2022-12-01", f"{arm}/subscriptions/{SUBSCRIPTION.upper()}?api-version=2022-12-01"):
            c.request("GET", url)
        self.assertEqual(len(script.calls), 2)
        refused = [
            ("POST", f"{arm}/subscriptions/{SUBSCRIPTION}?api-version=2022-12-01"),
            ("PUT", f"{arm}/subscriptions/{SUBSCRIPTION}?api-version=2022-12-01"),
            ("PATCH", f"{arm}/subscriptions/{SUBSCRIPTION}?api-version=2022-12-01"),
            ("DELETE", f"{arm}/subscriptions/{SUBSCRIPTION}?api-version=2022-12-01"),
            ("GET", f"{arm}/subscriptions/{SUBSCRIPTION}/?api-version=2022-12-01"),
            ("GET", f"{arm}/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-x?api-version=2021-04-01"),
            ("GET", f"{arm}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Compute/virtualMachines?api-version=2024-03-01"),
            ("GET", f"{arm}/subscriptions/not-a-subscription?api-version=2022-12-01"),
            ("GET", f"{arm}/subscriptions/{SUBSCRIPTION}x?api-version=2022-12-01"),
            ("GET", "https://management.azure.com.evil.example/subscriptions/" + SUBSCRIPTION),
        ]
        for method, url in refused:
            with self.assertRaises(http.Refused, msg=f"{method} {url}"):
                c.request(method, url)
        self.assertEqual(len(script.calls), 2, "nothing else left the app")

    def test_the_list_of_subscriptions_is_a_read_that_needs_no_foundry_project_and_changes_nothing_in_the_calls_that_there_were(self):
        plain = http.allowed_calls()
        self.assertEqual([(m, p.pattern) for m, p in plain][-1], ("GET", re.escape("https://management.azure.com") + "/subscriptions"))
        self.assertEqual(plain, http.allowed_calls(None))
        self.assertEqual(http.allowed_calls(ENDPOINT)[:len(plain)], plain)


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

    def test_the_pause_without_a_hint_is_a_parameter_that_doubles_up_to_its_ceiling(self):
        c, script, sleeps = client((429, {}, b"{}"))
        with self.assertRaises(http.HttpError):
            c.request("POST", COST, retries=5, backoff=8.0, backoff_max=30.0)
        self.assertEqual((len(script.calls), sleeps), (6, [12.0, 24.0, 30.0, 30.0, 30.0]), "8 seconds with the jitter of 0.5, doubled, and never more than 30")
        c, _, sleeps = client((503, {}, b"{}"))
        with self.assertRaises(http.HttpError):
            c.request("GET", LOCKS, retries=3, backoff=2.0, backoff_max=5.0)
        self.assertEqual(sleeps, [3.0, 5.0, 5.0])

    def test_the_default_pause_is_the_one_of_before(self):
        c, _, sleeps = client((503, {}, b"{}"))
        with self.assertRaises(http.HttpError):
            c.request("GET", LOCKS, retries=4)
        self.assertEqual(sleeps, [1.5, 3.0, 6.0, 12.0])

    def test_a_hint_beats_the_pause_and_a_hint_beyond_the_most_that_is_waited_for_is_a_refusal(self):
        c, _, sleeps = client((429, {"retry-after": "5"}, b"{}"), ok())
        c.request("POST", COST, backoff=8.0)
        self.assertEqual(sleeps, [5.0])
        c, script, sleeps = client((429, {"retry-after": "91"}, b"{}"))
        with self.assertRaises(http.HttpError) as raised:
            c.request("POST", COST, retry_after_max=90, backoff=8.0)
        self.assertEqual((raised.exception.status, len(script.calls), sleeps), (429, 1, []))


class LockLists(unittest.TestCase):
    GROUP = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-app"
    RESOURCE = f"{GROUP}/providers/Microsoft.Network/privateEndpoints/pe-one"
    LOCKS = "providers/Microsoft.Authorization/locks"

    def test_the_locks_of_a_group_a_resource_and_a_child_resource_may_be_read(self):
        c, script, _ = client(ok())
        for scope in (self.GROUP, self.RESOURCE, f"{self.RESOURCE}/privateDnsZoneGroups/default"):
            c.request("GET", f"{scope}/{self.LOCKS}?api-version=2016-09-01&$filter=atScope()")
        self.assertEqual(len(script.calls), 3)

    def test_a_lock_can_be_neither_made_nor_changed_nor_removed(self):
        c, script, _ = client(ok())
        for method in ("PUT", "DELETE", "POST", "PATCH"):
            for scope in (self.GROUP, self.RESOURCE, f"https://management.azure.com/subscriptions/{SUBSCRIPTION}"):
                for path in (f"{scope}/{self.LOCKS}/protect", f"{scope}/{self.LOCKS}"):
                    with self.assertRaises(http.Refused, msg=f"{method} {path}"):
                        c.request(method, path)
        self.assertEqual(script.calls, [])

    def test_the_list_of_a_scope_that_is_not_one_of_a_subscription_is_refused(self):
        c, script, _ = client(ok())
        arm = "https://management.azure.com"
        for scope in ("/subscriptions/not-a-guid", "/subscriptions/not-a-guid/resourceGroups/rg", f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg%20app",
                      f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/Microsoft.Network",
                      f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/Microsoft.Network/privateEndpoints",
                      "/providers/Microsoft.Management/managementGroups/mg", "", "/"):
            with self.assertRaises(http.Refused, msg=scope):
                c.request("GET", f"{arm}{scope}/{self.LOCKS}")
        self.assertEqual(script.calls, [])


def timed(*answers, now=0.0, deadline=None):
    """A client whose clock stands at `now`, with a deadline, and whose pauses move the clock."""
    clock = {"now": now}
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    script = Script(*answers)
    allowed = http.allowed_calls(ENDPOINT, GATEWAY)
    c = http.Client(allowed, Redactor(), transport=script, sleep=sleep, jitter=lambda: 0.5, monotonic=lambda: clock["now"])
    c.deadline = deadline
    return c, script, sleeps


class Deadline(unittest.TestCase):
    def test_without_a_deadline_nothing_changes(self):
        c, script, _ = timed(ok(), now=1e9)
        c.request("GET", LOCKS, timeout=7)
        self.assertEqual(script.calls[0][4], 7)
        self.assertIsNone(c.remaining())

    def test_no_call_starts_when_the_deadline_has_been_reached(self):
        for now in (100.0, 101.0):
            c, script, _ = timed(ok(), now=now, deadline=100.0)
            with self.assertRaises(http.HttpError) as raised:
                c.request("GET", LOCKS)
            self.assertEqual((raised.exception.status, script.calls), (0, []))
            self.assertIn("deadline", str(raised.exception))

    def test_the_timeout_of_a_call_never_reaches_past_the_deadline_and_is_never_less_than_a_second(self):
        for deadline, expected in ((100.0, 30), (10.0, 10.0), (0.4, 1.0)):
            c, script, _ = timed(ok(), now=0.0, deadline=deadline)
            c.request("GET", LOCKS, timeout=30)
            self.assertEqual(script.calls[0][4], expected, deadline)

    def test_a_pause_that_would_end_at_or_after_the_deadline_is_not_taken(self):
        for deadline in (1.0, 1.5):
            c, script, sleeps = timed((503, {}, b"{}"), ok(), now=0.0, deadline=deadline)
            with self.assertRaises(http.HttpError) as raised:
                c.request("GET", LOCKS)
            self.assertEqual((raised.exception.status, len(script.calls), sleeps), (503, 1, []), deadline)

    def test_a_pause_that_ends_before_the_deadline_is_taken(self):
        c, script, sleeps = timed((503, {}, b"{}"), ok(), now=0.0, deadline=100.0)
        self.assertEqual(c.request("GET", LOCKS).status, 200)
        self.assertEqual((len(script.calls), sleeps), (2, [1.5]))

    def test_the_wait_that_a_throttled_call_is_told_to_take_counts_against_the_deadline_too(self):
        c, script, sleeps = timed((429, {"retry-after": "30"}, b"{}"), ok(), now=0.0, deadline=20.0)
        with self.assertRaises(http.HttpError) as raised:
            c.request("POST", COST)
        self.assertEqual((raised.exception.status, len(script.calls), sleeps), (429, 1, []))


class WhatMayBeRepeated(unittest.TestCase):
    NOT_NOW = frozenset({429, 503})

    def test_a_call_whose_answer_did_not_arrive_is_not_repeated_when_it_may_have_been_carried_out(self):
        for failure in (urllib.error.URLError("down"), TimeoutError("slow"), ConnectionResetError(), OSError("x")):
            c, script, sleeps = client(failure, ok())
            with self.assertRaises(http.HttpError) as raised:
                c.request("POST", CHAT, retry_statuses=self.NOT_NOW, retry_network=False)
            self.assertEqual((raised.exception.status, len(script.calls), sleeps), (0, 1, []), failure)

    def test_only_the_statuses_that_were_named_are_repeated(self):
        for status in (500, 502, 504):
            c, script, sleeps = client((status, {}, b"{}"), ok())
            with self.assertRaises(http.HttpError, msg=str(status)):
                c.request("POST", CHAT, retry_statuses=self.NOT_NOW, retry_network=False)
            self.assertEqual((len(script.calls), sleeps), (1, []), status)
        for status in (429, 503):
            c, script, sleeps = client((status, {}, b"{}"), ok())
            self.assertEqual(c.request("POST", CHAT, retry_statuses=self.NOT_NOW, retry_network=False).status, 200)
            self.assertEqual(len(script.calls), 2, status)

    def test_a_call_that_is_a_read_repeats_a_network_error_by_default(self):
        c, script, _ = client(urllib.error.URLError("down"), ok())
        self.assertEqual(c.request("GET", LOCKS).status, 200)
        self.assertEqual(len(script.calls), 2)


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

    # The depth at which the C JSON parser gives up differs by platform (the C recursion limit of Python 3.13 is about 3,000 on Windows and 10,000 on Linux), so the
    # tests go far beyond both.
    DEEP = 50000

    def test_a_body_nested_too_deeply_to_be_parsed_gives_a_fixed_text_and_not_an_exception(self):
        deep = self.DEEP
        bodies = {
            "arrays": b"[" * deep + b"]" * deep, "arrays that are not closed": b"[" * deep, "objects": b'{"error":' * deep + b"1" + b"}" * deep,
            "arrays in the message": b'{"error":{"code":"X","message":' + b"[" * deep + b"]" * deep + b"}}",
            "a secret before the depth": b'{"secret":"SECRET-IN-THE-BODY","deep":' + b"[" * deep + b"]" * deep + b"}",
        }
        for what, body in bodies.items():
            for status in (400, 403, 500, 503):
                with self.subTest(what=what, status=status):
                    c, _, _ = client((status, {}, body))
                    with self.assertRaises(http.HttpError) as raised:
                        c.request("GET", LOCKS)
                    self.assertEqual(raised.exception.status, status)
                    self.assertEqual(str(raised.exception), f"GET management.azure.com: {status} the body is nested too deeply to be read")

    def test_the_error_text_of_a_body_that_cannot_be_read_is_made_without_an_exception(self):
        redact = Redactor()
        self.assertEqual(http.error_text(400, b"[" * self.DEEP, redact), "400 the body is nested too deeply to be read")
        # A number of 5000 digits is a ValueError, not a RecursionError: the first words of the body, as for any body that is not JSON.
        text = http.error_text(502, b"9" * 5000, redact)
        self.assertTrue(text.startswith("502 9") and len(text) <= 130, text)
        for body in (b"", b"{", b"\xff\xfe\x00", b"null", b"[]", b'"text"', b"5", b'{"error":5}', b'{"error":{"code":{"a":1},"message":[1]}}', b'{"error":"x","error_description":[1]}'):
            with self.subTest(body=body):
                self.assertTrue(http.error_text(500, body, redact).startswith("500"))

    def test_a_body_nested_deeply_but_still_readable_keeps_its_code_and_message(self):
        body = b'{"error":{"code":"Busy","message":"try later"},"details":' + b"[" * 500 + b"]" * 500 + b"}"
        self.assertEqual(http.error_text(429, body, Redactor()), "429 Busy: try later")

    def test_a_good_answer_that_is_not_json_is_an_error_when_read_as_json(self):
        c, _, _ = client((200, {}, b"not json"))
        with self.assertRaises(http.HttpError):
            c.request("GET", LOCKS).json()

    def test_a_good_answer_nested_too_deeply_is_an_error_when_read_as_json_and_not_a_recursion_error(self):
        for body in (b"[" * self.DEEP + b"]" * self.DEEP, b'{"a":' * self.DEEP + b"1" + b"}" * self.DEEP):
            c, _, _ = client((200, {}, body))
            with self.assertRaises(http.HttpError) as raised:
                c.request("GET", LOCKS).json()
            self.assertEqual((raised.exception.status, str(raised.exception)), (200, "the answer is nested too deeply to be read"))

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


class TheChallengeOfAnAnswer(unittest.TestCase):
    """The `www-authenticate` header of a 401 or a 403 is kept on the error for the one reader that needs it, and is in no text of the error."""

    SCHEME = "Bearer"
    HEADER = (f'{SCHEME} realm="", authorization_uri="https://login.example.test/common/oauth2/authorize", error="insufficient_claims", '
              'claims="eyJhY2Nlc3NfdG9rZW4iOnsiYWNycyI6eyJlc3NlbnRpYWwiOnRydWUsInZhbHVlIjoiY3AxIn19fQ=="')
    BODY = json.dumps({"error": {"code": "InvalidAuthenticationToken", "message": "the token lacks a claim"}}).encode()

    def failed(self, status, headers, retries=0):
        c, script, _ = client((status, headers, self.BODY))
        with self.assertRaises(http.HttpError) as raised:
            c.request("GET", LOCKS, retries=retries)
        return raised.exception, script

    def test_a_401_and_a_403_keep_the_header_as_it_came(self):
        for status in (401, 403):
            with self.subTest(status=status):
                error, _ = self.failed(status, {"www-authenticate": self.HEADER})
                self.assertEqual((error.status, error.challenge), (status, self.HEADER))

    def test_the_name_of_the_header_is_read_in_any_case(self):
        for name in ("www-authenticate", "WWW-Authenticate", "Www-Authenticate", "WWW-AUTHENTICATE"):
            with self.subTest(name=name):
                self.assertEqual(self.failed(401, {"content-type": "x", name: self.HEADER})[0].challenge, self.HEADER)

    def test_no_other_answer_keeps_it_and_an_answer_without_the_header_has_none(self):
        for status in (400, 404, 405, 409, 412, 422, 500, 502, 503, 504, 0):
            with self.subTest(status=status):
                error, _ = self.failed(status, {"www-authenticate": self.HEADER})
                self.assertEqual(error.challenge, "")
        for headers in ({}, {"content-type": "application/json"}, {"authenticate": self.HEADER}, {"x-www-authenticate": self.HEADER}):
            with self.subTest(headers=headers):
                self.assertEqual(self.failed(401, headers)[0].challenge, "")

    def test_a_throttled_call_that_is_tried_again_and_then_refused_keeps_the_header_of_the_last_answer_only(self):
        c, script, _ = client((429, {"retry-after": "1", "www-authenticate": "of a 429"}, b"{}"), (403, {"www-authenticate": self.HEADER}, self.BODY))
        with self.assertRaises(http.HttpError) as raised:
            c.request("GET", LOCKS)
        self.assertEqual((raised.exception.status, raised.exception.challenge, len(script.calls)), (403, self.HEADER, 2))

    def test_the_header_is_cut_at_1500_characters(self):
        long = self.HEADER + ', error_description="' + "x" * 5000 + '"'
        error, _ = self.failed(401, {"www-authenticate": long})
        self.assertEqual((len(error.challenge), error.challenge), (http.MAX_CHALLENGE, long[:1500]))
        self.assertEqual(http.MAX_CHALLENGE, 1500)
        exact = self.HEADER + " " * (1500 - len(self.HEADER))
        self.assertEqual(self.failed(401, {"www-authenticate": exact})[0].challenge, exact)

    def test_the_header_is_in_no_text_of_the_error(self):
        marker = "claims-marker-0123456789"
        header = f'{self.SCHEME} error="insufficient_claims", claims="{marker}"'
        error, _ = self.failed(401, {"www-authenticate": header})
        self.assertEqual(error.challenge, header)
        for text in (str(error), repr(error), repr(error.args), f"{error!s}{error!r}", " ".join(map(str, error.args))):
            for part in (marker, "insufficient_claims", self.SCHEME, "www-authenticate"):
                self.assertNotIn(part, text)
        self.assertEqual(str(error), "GET management.azure.com: 401 InvalidAuthenticationToken: the token lacks a claim", "the text is what it was before")

    def test_the_header_does_not_change_the_text_or_the_other_attributes_of_the_error(self):
        with_header, _ = self.failed(401, {"www-authenticate": self.HEADER})
        without, _ = self.failed(401, {})
        self.assertEqual((str(with_header), with_header.status, with_header.retry_after), (str(without), without.status, without.retry_after))

    def test_a_call_to_the_token_endpoint_that_is_refused_keeps_the_header_too_and_never_in_its_text(self):
        c, _ = token_client((401, {"www-authenticate": self.HEADER}, json.dumps({"error": "invalid_client", "error_description": "AADSTS7000215: bad"}).encode()))
        with self.assertRaises(http.HttpError) as raised:
            c.request("POST", TOKEN_URL, form={"a": "b"})
        self.assertEqual(raised.exception.challenge, self.HEADER)
        self.assertNotIn("claims", str(raised.exception))

    def test_an_error_that_the_app_makes_itself_has_none(self):
        self.assertEqual(http.HttpError(401, "text").challenge, "")
        self.assertEqual(http.HttpError(401, "text", 5.0).challenge, "")
        self.assertEqual(http.HttpError(401, "text", None, "kept").challenge, "kept")
        with self.assertRaises(http.HttpError) as raised:
            http.Response(401, {"www-authenticate": self.HEADER}, b"not json").json()
        self.assertEqual(raised.exception.challenge, "")

    def test_the_header_of_a_real_answer_reaches_the_function_that_reads_it(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(401)
                self.send_header("WWW-Authenticate", TheChallengeOfAnAnswer.HEADER)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, headers, _ = http.default_transport("GET", f"http://127.0.0.1:{server.server_port}/x", {}, None, 10)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(status, 401)
        self.assertEqual(http.challenge_of(status, headers), self.HEADER)
        self.assertEqual(http.challenge_of(200, headers), "")


class NoRedirects(unittest.TestCase):
    def test_an_answer_that_redirects_is_the_answer_and_is_not_followed_with_the_headers_of_the_call(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                if self.path == "/first":
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/second")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, headers, _ = http.default_transport("GET", f"http://127.0.0.1:{server.server_port}/first", {"Authorization": "a-credential-of-the-call"}, None, 10)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(status, 302)
        self.assertTrue(headers["location"].endswith("/second"))
        self.assertEqual(seen, [("/first", "a-credential-of-the-call")], "the address that the answer named was never called")


class RetryAfter(unittest.TestCase):
    def test_the_header_is_read_in_any_case_after_lower_casing_and_a_bad_value_is_ignored(self):
        self.assertEqual(http.retry_after({"retry-after": "5"}), 5.0)
        self.assertEqual(http.retry_after({"x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "7.5"}), 7.5)
        self.assertIsNone(http.retry_after({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}))
        self.assertIsNone(http.retry_after({"content-type": "x"}))

    def test_when_several_headers_give_a_wait_the_longest_binds_and_a_header_that_is_not_a_number_does_not_hide_the_others(self):
        # Cost Management has one for its entity, one for its client and one for its tenant.
        self.assertEqual(http.retry_after({"x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "9", "x-ms-ratelimit-microsoft.costmanagement-tenant-retry-after": "40",
                                           "retry-after": "12"}), 40.0)
        self.assertEqual(http.retry_after({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT", "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "7"}), 7.0)

    def test_the_time_that_the_quota_of_resource_graph_resets_after_is_a_wait_of_that_time_and_a_second_more(self):
        # Learn, "Guidance for throttled requests in Azure Resource Graph": x-ms-user-quota-resets-after, hh:mm:ss, on every answer; 15 queries in 5 seconds.
        self.assertEqual(http.retry_after({"x-ms-user-quota-resets-after": "00:00:03", "x-ms-user-quota-remaining": "0"}), 4.0)
        self.assertEqual(http.retry_after({"x-ms-user-quota-resets-after": "00:01:02.5"}), 63.5)
        self.assertEqual(http.retry_after({"x-ms-user-quota-resets-after": "1:00:00"}), 3601.0)
        self.assertEqual(http.retry_after({"x-ms-user-quota-resets-after": "00:00:03", "retry-after": "10"}), 10.0, "the longer of the two")
        for bad in ("", "soon", "00:00", "00:61:00", "-1:00:00", "00:00:03 seconds"):
            self.assertIsNone(http.retry_after({"x-ms-user-quota-resets-after": bad}), bad)

    def test_a_throttled_resource_graph_query_waits_for_the_quota_to_reset_and_is_made_again(self):
        c, script, sleeps = client((429, {"x-ms-user-quota-remaining": "0", "x-ms-user-quota-resets-after": "00:00:04"}, b'{"error":{"code":"RateLimiting","message":"slow down"}}'), ok({"data": []}))
        self.assertEqual(c.request("POST", ARG, body={"query": "q"}).status, 200)
        self.assertEqual((len(script.calls), sleeps), (2, [5.0]))

    def test_a_quota_that_resets_in_more_than_a_minute_is_a_refusal_and_not_a_wait(self):
        c, script, sleeps = client((429, {"x-ms-user-quota-resets-after": "00:05:00"}, b'{"error":{"code":"RateLimiting","message":"slow down"}}'))
        with self.assertRaises(http.HttpError) as raised:
            c.request("POST", ARG, body={"query": "q"})
        self.assertEqual((raised.exception.status, len(script.calls), sleeps, raised.exception.retry_after), (429, 1, [], 301.0))


TOKEN_URL = "https://login.microsoftonline.com/aaaaaaaa-1111-4222-8333-444444444444/oauth2/v2.0/token"


def token_client(*answers):
    script = Script(*answers)
    allowed = (("POST", re.compile(r"https://login\.microsoftonline\.com/[0-9a-f-]{36}/oauth2/v2\.0/token")),)
    return http.Client(allowed, Redactor(), transport=script, sleep=lambda s: None, jitter=lambda: 0.5), script


class Forms(unittest.TestCase):
    def test_a_form_is_sent_url_encoded_with_its_own_content_type(self):
        c, script = token_client(ok({"access_token": "x"}))
        c.request("POST", TOKEN_URL, form={"grant_type": "authorization_code", "code": "a b&c=d", "redirect_uri": "https://h.example/arm/return"})
        (_, _, headers, data, _), = script.calls
        self.assertEqual(headers["Content-Type"], "application/x-www-form-urlencoded")
        self.assertEqual(parse_qs(data.decode("ascii")), {"grant_type": ["authorization_code"], "code": ["a b&c=d"], "redirect_uri": ["https://h.example/arm/return"]})
        self.assertNotIn("a b&c=d", data.decode("ascii"), "the text is encoded")

    def test_a_body_is_still_sent_as_json_and_a_call_without_either_has_no_data(self):
        c, script = token_client(ok())
        c.request("POST", TOKEN_URL, body={"a": 1})
        c.request("POST", TOKEN_URL)
        self.assertEqual((script.calls[0][2]["Content-Type"], script.calls[0][3]), ("application/json", b'{"a":1}'))
        self.assertEqual((script.calls[1][3], "Content-Type" in script.calls[1][2]), (None, False))

    def test_a_call_with_a_body_and_a_form_is_refused_before_it_is_made(self):
        c, script = token_client(ok())
        with self.assertRaises(ValueError):
            c.request("POST", TOKEN_URL, body={"a": 1}, form={"b": "2"})
        self.assertEqual(script.calls, [])

    def test_a_call_to_a_token_endpoint_that_is_not_on_the_list_is_refused(self):
        c, script = token_client(ok())
        for url in (TOKEN_URL.replace("login.microsoftonline.com", "login.example.net"), TOKEN_URL.replace("/token", "/authorize"), "http://login.microsoftonline.com/x"):
            with self.assertRaises(http.Refused):
                c.request("POST", url, form={"a": "b"})
        with self.assertRaises(http.Refused):
            c.request("GET", TOKEN_URL)
        self.assertEqual(script.calls, [])


class OAuthErrors(unittest.TestCase):
    DESCRIPTION = ("AADSTS70008: The provided authorization code or refresh token has expired due to inactivity. Send a new interactive authorization request. "
                   "Trace ID: 0b1c2d3e-aaaa-bbbb-cccc-000000000000 Correlation ID: 11111111-2222-3333-4444-555555555555 Timestamp: 2026-11-05 09:00:00Z")

    def test_an_oauth_error_is_its_error_and_its_aadsts_code_and_nothing_of_the_description(self):
        c, _ = token_client((400, {}, json.dumps({"error": "invalid_grant", "error_description": self.DESCRIPTION}).encode()))
        with self.assertRaises(http.HttpError) as raised:
            c.request("POST", TOKEN_URL, form={"code": "the-code-of-the-person"})
        text = str(raised.exception)
        self.assertEqual(raised.exception.status, 400)
        self.assertIn("400 invalid_grant AADSTS70008", text)
        for hidden in ("Trace ID", "Correlation ID", "0b1c2d3e", "expired due to inactivity", "the-code-of-the-person"):
            self.assertNotIn(hidden, text)

    def test_an_oauth_error_without_a_code_is_only_its_error(self):
        c, _ = token_client((400, {}, json.dumps({"error": "access_denied", "error_description": "the person said no"}).encode()))
        with self.assertRaises(http.HttpError) as raised:
            c.request("POST", TOKEN_URL, form={"a": "b"})
        self.assertTrue(str(raised.exception).endswith("400 access_denied"), str(raised.exception))

    def test_an_oauth_error_is_not_retried_and_a_throttled_token_call_is(self):
        c, script = token_client((400, {}, b'{"error": "invalid_grant"}'))
        with self.assertRaises(http.HttpError):
            c.request("POST", TOKEN_URL, form={"a": "b"})
        self.assertEqual(len(script.calls), 1)
        c, script = token_client((429, {"Retry-After": "1"}, b"{}"), ok({"access_token": "x"}))
        self.assertEqual(c.request("POST", TOKEN_URL, form={"a": "b"}).status, 200)
        self.assertEqual(len(script.calls), 2)

    def test_an_error_that_is_a_text_in_a_long_error_is_cut_short(self):
        c, _ = token_client((400, {}, json.dumps({"error": "x" * 500, "error_description": "AADSTS65001: consent"}).encode()))
        with self.assertRaises(http.HttpError) as raised:
            c.request("POST", TOKEN_URL, form={"a": "b"}, retries=0)
        self.assertLess(len(str(raised.exception)), 200)
        self.assertIn("AADSTS65001", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
