import json
import logging
import time
import unittest
from urllib.parse import parse_qs, urlsplit

from cases import console

from test_loop_end_to_end import LOOP_ENV, OID
from test_store import FakeTables

OTHER = "11111111-2222-3333-4444-555555555555"
SIGNED_IN = {**LOOP_ENV, "WEBSITE_AUTH_ENABLED": "true"}
PRINCIPAL = "x-ms-client-principal-id"


def fetch(url, headers, timeout):
    """The platform's token endpoint, with a token that is valid now."""
    client = parse_qs(urlsplit(url).query).get("client_id", ["none"])[0]
    return 200, json.dumps({"access_token": f"tok-{client}", "expires_on": str(int(time.time()) + 3600), "resource": "x"}).encode("utf-8")


class Req:
    """What the platform hands to the function: a method, an address, headers and a body."""

    def __init__(self, path="/", method="GET", headers=None, body=b"", host="func.example.net"):
        self.method, self.url, self.headers, self._body = method, f"https://{host}{path}", headers or {}, body

    def get_body(self):
        return self._body


class Resp:
    def __init__(self, body=b"", status_code=200, headers=None):
        self.body, self.status_code, self.headers = body, status_code, headers or {}


class TheFrontDoor(unittest.TestCase):
    def setUp(self):
        console._RUNTIME.clear()
        self.addCleanup(console._RUNTIME.clear)
        self.tables = FakeTables()
        self.calls, self.tokens = [], []

        def transport(method, url, headers, data, timeout):
            self.calls.append((method, url))
            return self.tables.transport(method, url, headers, data, timeout)

        def counting_fetch(url, headers, timeout):
            self.tokens.append(url)
            return fetch(url, headers, timeout)

        self.transport, self.fetch = transport, counting_fetch

    def handle(self, req, env):
        return console.handle(req, Resp, env=env, transport=self.transport, fetch=self.fetch, sleep=lambda s: None)

    def test_the_health_probe_answers_without_a_sign_in_and_touches_nothing(self):
        for path in ("/healthz", "/healthz?probe=1"):
            for env in ({}, {"WEBSITE_AUTH_ENABLED": "false"}, SIGNED_IN):
                answer = self.handle(Req(path), env)
                self.assertEqual((answer.status_code, answer.body), (200, b"ok"), (path, env.get("WEBSITE_AUTH_ENABLED")))
                self.assertEqual(answer.headers["Cache-Control"], "no-store")
        self.assertEqual((self.calls, self.tokens), ([], []))

    def test_nothing_else_is_served_when_the_platform_sign_in_is_not_on_even_with_a_forged_header(self):
        for env in ({}, {"WEBSITE_AUTH_ENABLED": ""}, {"WEBSITE_AUTH_ENABLED": "false"}, {"WEBSITE_AUTH_ENABLED": "0"}, {**LOOP_ENV}):
            for path in ("/", "/history", "/me/settings", "/ops/pause", "/ok/abc123", "/why/abc123"):
                for method in ("GET", "POST"):
                    answer = self.handle(Req(path, method, {PRINCIPAL: OID, "content-type": "application/x-www-form-urlencoded"}, b"decision=approve"), env)
                    self.assertEqual(answer.status_code, 503, (path, method, env.get("WEBSITE_AUTH_ENABLED")))
                    self.assertIn(b"sign-in is not set up", answer.body)
                    self.assertTrue(answer.headers["Content-Type"].startswith("text/plain"))
                    self.assertEqual(answer.headers["Content-Security-Policy"], "default-src 'none'")
        self.assertEqual((self.calls, self.tokens), ([], []), "nothing was read or written")

    def test_the_flag_is_read_in_any_case_and_with_spaces(self):
        for value in ("true", "True", "TRUE", " true "):
            answer = self.handle(Req("/", headers={PRINCIPAL: OID}), {**LOOP_ENV, "WEBSITE_AUTH_ENABLED": value})
            self.assertEqual(answer.status_code, 200, repr(value))

    def test_a_listed_person_gets_the_start_page_with_the_security_headers_and_no_script(self):
        answer = self.handle(Req("/", headers={PRINCIPAL: OID}), SIGNED_IN)
        self.assertEqual(answer.status_code, 200)
        self.assertTrue(answer.headers["Content-Type"].startswith("text/html"))
        for name in ("Content-Security-Policy", "X-Content-Type-Options"):
            self.assertIn(name, answer.headers)
        self.assertNotIn(b"<script", answer.body.lower())
        self.assertTrue(all(host.endswith(".table.core.windows.net") for _, host in ((m, u.split("/")[2]) for m, u in self.calls)))

    def test_a_person_who_is_not_listed_or_gives_no_header_gets_no_access_and_nothing_is_written(self):
        for headers in ({PRINCIPAL: OTHER}, {}, {PRINCIPAL: ""}, {PRINCIPAL: "not-a-guid"}):
            answer = self.handle(Req("/history", headers=headers), SIGNED_IN)
            self.assertEqual(answer.status_code, 403, headers)
            self.assertIn(b"No access", answer.body)
        self.assertEqual([c for c in self.calls if c[0] != "GET"], [])

    def test_a_header_in_another_case_is_read_the_same_way(self):
        answer = self.handle(Req("/", headers={"X-MS-CLIENT-PRINCIPAL-ID": OID}), SIGNED_IN)
        self.assertEqual(answer.status_code, 200)

    def test_a_loop_that_is_not_set_up_fails_plainly_and_says_nothing_about_why(self):
        env = {"WEBSITE_AUTH_ENABLED": "true"}
        with self.assertLogs("meternaut.console", level=logging.ERROR) as logged:
            answer = self.handle(Req("/", headers={PRINCIPAL: OID}), env)
        self.assertEqual(answer.status_code, 500)
        self.assertEqual(answer.body, b"Something went wrong. Nothing was changed.")
        self.assertNotIn(b"STORE_ACCOUNT_NAME", answer.body)
        self.assertIn("the console failed", logged.output[0])

    def test_a_people_list_that_is_wrong_fails_plainly_too(self):
        answer = self.handle(Req("/", headers={PRINCIPAL: OID}), {**SIGNED_IN, "CONSOLE_PEOPLE": "not json"})
        self.assertEqual((answer.status_code, answer.body), (500, b"Something went wrong. Nothing was changed."))

    def test_a_request_that_cannot_be_read_never_raises(self):
        class Broken:
            method, url, headers = "GET", "https://func.example.net/", {PRINCIPAL: OID}

            def get_body(self):
                raise RuntimeError("the body cannot be read")

        answer = self.handle(Broken(), SIGNED_IN)
        self.assertEqual(answer.status_code, 500)
        self.assertNotIn(b"cannot be read", answer.body)

    def test_the_services_are_built_once_and_the_token_is_asked_for_once(self):
        for _ in range(3):
            self.assertEqual(self.handle(Req("/", headers={PRINCIPAL: OID}), SIGNED_IN).status_code, 200)
        self.assertEqual(len(self.tokens), 1)
        first = console.services(SIGNED_IN)
        self.assertIs(console.services(SIGNED_IN), first)

    def test_a_form_that_does_not_come_from_the_same_site_is_refused_before_anything_is_written(self):
        answer = self.handle(Req("/me/settings", "POST", {PRINCIPAL: OID, "sec-fetch-site": "cross-site", "content-type": "application/x-www-form-urlencoded"}, b"channel=desk"), SIGNED_IN)
        self.assertEqual(answer.status_code, 403)
        self.assertEqual([c for c in self.calls if c[0] != "GET"], [])


class TheSignInFlag(unittest.TestCase):
    def test_only_the_word_true_switches_it_on(self):
        for value, expected in (("true", True), ("True", True), (" TRUE ", True), ("false", False), ("", False), ("1", False), ("yes", False)):
            self.assertIs(console.sign_in_is_on({"WEBSITE_AUTH_ENABLED": value}), expected, value)
        self.assertIs(console.sign_in_is_on({}), False)


if __name__ == "__main__":
    unittest.main()
