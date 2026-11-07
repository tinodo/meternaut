import ast
import contextlib
import http.client
import importlib.util
import io
import re
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("console_check", ROOT / "tools" / "console-check.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

HOST = "func-example.azurewebsites.net"


class Door:
    """The front door as the platform's sign-in presents it, or as the app's own refusal does."""

    def __init__(self, mode="signin", health=(200, b"ok"), leak=None, trust_header=False):
        self.mode, self.health, self.leak, self.trust_header = mode, health, leak, trust_header
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        path = url.split(HOST, 1)[1]
        if path == "/healthz":
            return self.health[0], {}, self.health[1]
        if self.leak and path == self.leak:
            return 200, {}, b"<html>"
        if self.trust_header and "x-ms-client-principal-id" in headers:
            return 200, {}, b"<html>"
        if self.mode == "signin":
            return 302, {"location": f"/.auth/login/aad?post_login_redirect_uri=https%3A%2F%2F{HOST}{path}"}, b""
        return 503, {}, b"sign-in is not set up"


class TheDoor(unittest.TestCase):
    def test_a_door_that_sends_everybody_to_the_sign_in_passes(self):
        passed, rows = cc.door(HOST, "signin", Door())
        self.assertTrue(passed, rows)
        self.assertEqual(len(rows), 1 + len(cc.PAGES) + len(cc.FORGED_PAGES))

    def test_a_door_that_refuses_everybody_passes_when_a_refusal_is_expected(self):
        passed, _ = cc.door(HOST, "refuse", Door("refuse"))
        self.assertTrue(passed)

    def test_a_refusal_is_not_a_sign_in_and_the_other_way_round(self):
        self.assertFalse(cc.door(HOST, "signin", Door("refuse"))[0])
        self.assertFalse(cc.door(HOST, "refuse", Door("signin"))[0])

    def test_a_page_that_is_served_without_a_sign_in_fails_whichever_it_is(self):
        for path in cc.PAGES:
            with self.subTest(path=path):
                passed, rows = cc.door(HOST, "signin", Door(leak=path))
                self.assertFalse(passed)
                self.assertEqual({r[0] for r in rows if not r[2]}, {path})

    def test_a_made_up_sign_in_header_that_the_app_would_trust_fails(self):
        passed, rows = cc.door(HOST, "signin", Door(trust_header=True))
        self.assertFalse(passed)
        self.assertTrue(all(r[1] == "made-up sign-in header" for r in rows if not r[2]))
        self.assertEqual([r[0] for r in rows if not r[2]], list(cc.FORGED_PAGES))
        self.assertEqual(len(cc.FORGED_PAGES), 3)

    def test_the_return_address_of_the_azure_sign_in_is_asked_for_with_and_without_a_code_and_never_serves_a_page(self):
        bare, coded = "/arm/return", "/arm/return?code=x&state=y"
        self.assertIn(bare, cc.PAGES)
        self.assertIn(coded, cc.PAGES)
        door = Door()
        passed, rows = cc.door(HOST, "signin", door)
        self.assertTrue(passed, rows)
        asked = [url for url, headers in door.calls if "/arm/return" in url and "x-ms-client-principal-id" not in headers]
        self.assertEqual(asked, [f"https://{HOST}{bare}", f"https://{HOST}{coded}"])
        for path in (bare, coded):
            with self.subTest(path=path):
                passed, rows = cc.door(HOST, "signin", Door(leak=path))
                self.assertFalse(passed)
                self.assertEqual({r[0] for r in rows if not r[2]}, {path})
                self.assertIn((path, "no sign-in"), [(r[0], r[1]) for r in rows if not r[2]])

    def test_the_return_address_gets_the_verdict_of_every_other_page_in_both_modes_and_a_made_up_header_does_not_open_it(self):
        for expect in ("signin", "refuse"):
            with self.subTest(expect=expect):
                passed, rows = cc.door(HOST, expect, Door(expect))
                self.assertTrue(passed, rows)
                arm = [r for r in rows if r[0].startswith("/arm/return")]
                self.assertEqual([(r[0], r[1]) for r in arm], [("/arm/return", "no sign-in"), ("/arm/return?code=x&state=y", "no sign-in"),
                                                              ("/arm/return?code=x&state=y", "made-up sign-in header")])
                self.assertTrue(all(r[2] for r in arm))
        self.assertFalse(cc.door(HOST, "signin", Door("refuse"))[0], "the refusal is not the sign-in, here as for any other page")
        passed, rows = cc.door(HOST, "signin", Door(trust_header=True))
        self.assertIn(("/arm/return?code=x&state=y", "made-up sign-in header"), [(r[0], r[1]) for r in rows if not r[2]])

    def test_the_health_probe_has_to_answer_ok(self):
        self.assertFalse(cc.door(HOST, "signin", Door(health=(200, b"hello")))[0])
        self.assertFalse(cc.door(HOST, "signin", Door(health=(503, b"ok")))[0])

    def test_a_redirect_to_anywhere_else_is_not_a_sign_in(self):
        def elsewhere(url, headers):
            if url.endswith("/healthz"):
                return 200, {}, b"ok"
            return 302, {"location": "https://example.com/login"}, b""

        self.assertFalse(cc.door(HOST, "signin", elsewhere)[0])

    def test_it_sends_no_credential_and_only_reads(self):
        door = Door()
        cc.door(HOST, "signin", door)
        for url, headers in door.calls:
            self.assertTrue(url.startswith(f"https://{HOST}/"))
            self.assertFalse({k.lower() for k in headers} & {"authorization", "cookie", "x-api-key", "ocp-apim-subscription-key"})

    def test_a_bad_host_or_expectation_is_refused(self):
        for host, expect in (("not a host", "signin"), ("Example.com/", "signin"), (HOST, "maybe")):
            with self.assertRaises(cc.Problem):
                cc.door(host, expect)

    def test_a_slow_first_answer_is_waited_for_and_no_answer_at_all_is_a_problem_and_not_a_trace(self):
        from unittest import mock

        answers = [TimeoutError("timed out"), TimeoutError("timed out")]

        class Response:
            status, headers = 200, {}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                return b"ok"

        class Opener:
            calls = 0

            def open(self, request, timeout):
                Opener.calls += 1
                assert timeout == cc.TIMEOUT
                if answers:
                    raise answers.pop(0)
                return Response()

        with mock.patch("urllib.request.build_opener", return_value=Opener()):
            self.assertEqual(cc.fetch(f"https://{HOST}/healthz", {})[0], 200)
            self.assertEqual(Opener.calls, 3, "two timeouts, then the answer")
            answers[:] = [TimeoutError("timed out")] * cc.TRIES
            with self.assertRaises(cc.Problem) as raised:
                cc.fetch(f"https://{HOST}/", {})
            self.assertIn("no answer", str(raised.exception))


    def test_it_asks_the_way_a_browser_does_because_only_a_browser_is_sent_to_the_sign_in(self):
        from unittest import mock

        seen = []

        class Response:
            status, headers = 302, {"Location": "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize"}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                return b""

        class Opener:
            def open(self, request, timeout):
                seen.append(request)
                return Response()

        with mock.patch("urllib.request.build_opener", return_value=Opener()):
            cc.fetch(f"https://{HOST}/", {})
        self.assertTrue(seen[0].get_header("User-agent").startswith("Mozilla/5.0 ("), "a client that is not a browser gets a 401 from the platform, which proves nothing about the sign-in")
        self.assertIn("meternaut-console-check", seen[0].get_header("User-agent"))


class TheCommand(unittest.TestCase):
    def test_exit_codes_output_and_summary(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            self.assertEqual(cc.main(["door", "--host", HOST, "--summary", str(summary)], Door(), out), 0)
            self.assertIn("PASS  /healthz", out.getvalue())
            self.assertIn("PASS  /arm/return?code=x&state=y", out.getvalue())
            self.assertIn("Nobody gets a page without a sign-in.", summary.read_text(encoding="utf-8"))
            out = io.StringIO()
            self.assertEqual(cc.main(["door", "--host", HOST, "--summary", str(summary)], Door(leak="/history"), out), 1)
            self.assertIn("FAIL  /history", out.getvalue())
            self.assertIn("got something that it should not", summary.read_text(encoding="utf-8"))
        self.assertEqual(cc.main(["door", "--host", "bad host"], Door(), io.StringIO()), 2)

    def test_it_is_standard_library_only_and_makes_no_write(self):
        source = (ROOT / "tools" / "console-check.py").read_text(encoding="utf-8")
        modules = set(re.findall(r"^(?:import|from) (\w+)", source, re.M))
        self.assertTrue(modules <= {"argparse", "datetime", "http", "ipaddress", "re", "socket", "ssl", "sys", "time", "urllib", "uuid", "typing", "__future__"}, modules)
        self.assertNotRegex(source, r'method="(POST|PUT|PATCH|DELETE)"')


PROXY = "console.example.net"


class Proxied:
    """The console behind a reverse proxy, the platform's Application Gateway: the platform's sign-in redirects, and `named` is the host that its return address names.

    `form` is how the redirect looks. "entra": straight to Microsoft Entra, with redirect_uri. "own": the sign-in's own address, with post_login_redirect_uri.
    "path": the same, with a return address that is a path. "bare": the sign-in's own address and no return address at all."""

    def __init__(self, host=PROXY, named=None, form="entra"):
        self.host, self.named, self.form = host, named or host, form
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        path = url.split(self.host, 1)[1]
        if path == "/healthz":
            return 200, {}, b"ok"
        if self.form == "entra":
            query = urllib.parse.urlencode({"response_type": "code id_token", "client_id": "client", "redirect_uri": f"https://{self.named}/.auth/login/aad/callback", "state": "s"})
            where = f"https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?{query}"
        elif self.form == "own":
            where = "/.auth/login/aad?" + urllib.parse.urlencode({"post_login_redirect_uri": f"https://{self.named}{path}"})
        elif self.form == "path":
            where = "/.auth/login/aad?" + urllib.parse.urlencode({"post_login_redirect_uri": path})
        else:
            where = "/.auth/login/aad"
        return 302, {"location": where}, b""


class TheDoorBehindAReverseProxy(unittest.TestCase):
    """The front door that people use once the cases app is closed is the console's host name on the platform's Application Gateway. The sign-in of the app builds its return address from the
    host that it believes the request was made to, so the check also asks that the address names the proxy's name: a sign-in that returns to the app's own name sends a person to a name that
    a closed app cannot answer on."""

    def test_a_sign_in_that_returns_to_the_proxys_name_passes_in_both_forms_and_the_row_says_so(self):
        for form in ("entra", "own"):
            with self.subTest(form=form):
                passed, rows = cc.door(PROXY, "signin", Proxied(form=form), proxied=True)
                self.assertTrue(passed, rows)
                self.assertEqual(len(rows), 1 + len(cc.PAGES) + len(cc.FORGED_PAGES))
                for path, how, ok, text in rows:
                    if path != "/healthz":
                        self.assertTrue(text.endswith(", return address names the host"), text)

    def test_a_sign_in_that_returns_to_the_apps_own_name_fails_behind_a_proxy_and_passes_without_the_flag(self):
        # What the platform's sign-in does when forwardProxy does not read the proxy's header: the redirect is right and the return address is the app's own name.
        for form in ("entra", "own"):
            with self.subTest(form=form):
                passed, rows = cc.door(PROXY, "signin", Proxied(named=HOST, form=form), proxied=True)
                self.assertFalse(passed)
                failed = [row for row in rows if not row[2]]
                self.assertEqual(len(failed), len(cc.PAGES) + len(cc.FORGED_PAGES), "every redirect names the wrong host; /healthz is no redirect and passes")
                for path, how, ok, text in failed:
                    self.assertIn(f"but the return address names {HOST}", text)
                self.assertTrue(cc.door(PROXY, "signin", Proxied(named=HOST, form=form))[0], "without --proxied the check is what it was")

    def test_a_redirect_that_shows_no_return_address_with_a_host_in_it_passes_and_the_row_says_that_none_was_seen(self):
        for form in ("bare", "path"):
            with self.subTest(form=form):
                passed, rows = cc.door(PROXY, "signin", Proxied(form=form), proxied=True)
                self.assertTrue(passed, rows)
                for path, how, ok, text in rows:
                    if path != "/healthz":
                        self.assertTrue(text.endswith(", no return address with a host in it"), text)

    def test_a_redirect_that_is_no_sign_in_is_no_sign_in_whatever_it_names(self):
        elsewhere = "https://example.com/login?redirect_uri=https%3A%2F%2Fconsole.example.net%2F"
        self.assertEqual(cc.verdict("/", 302, {"location": elsewhere}, "signin", PROXY)[0], False)
        self.assertEqual(cc.verdict("/", 200, {}, "signin", PROXY)[0], False)

    def test_the_hosts_that_a_redirect_names_are_read_from_both_parameters_in_lower_case_without_a_port(self):
        entra = "https://login.microsoftonline.com/t/oauth2/v2.0/authorize?"
        for where, hosts in ((f"{entra}redirect_uri=https%3A%2F%2F{PROXY}%2F.auth%2Flogin%2Faad%2Fcallback", [PROXY]),
                             ("/.auth/login/aad?post_login_redirect_uri=https%3A%2F%2FConsole.Example.NET%3A443%2Fhistory", [PROXY]),
                             ("/.auth/login/aad?post_login_redirect_uri=%2Fhistory", []),
                             ("/.auth/login/aad", []),
                             (f"{entra}redirect_uri=https%3A%2F%2Fa.example.net%2Fx&post_login_redirect_uri=https%3A%2F%2Fb.example.net%2F", ["a.example.net", "b.example.net"]),
                             ("/.auth/login/aad?other=https%3A%2F%2Fc.example.net%2F", []),
                             ("", [])):
            self.assertEqual(cc.return_hosts(where), hosts, where)

    def test_a_return_address_that_also_names_another_host_fails_even_when_the_first_is_right(self):
        entra = "https://login.microsoftonline.com/t/oauth2/v2.0/authorize?"
        where = f"{entra}redirect_uri=https%3A%2F%2F{PROXY}%2Fa&post_login_redirect_uri=https%3A%2F%2F{HOST}%2F"
        ok, text = cc.verdict("/", 302, {"location": where}, "signin", PROXY)
        self.assertFalse(ok)
        self.assertIn(HOST, text)
        self.assertTrue(cc.verdict("/", 302, {"location": f"{where.split('&')[0]}&post_login_redirect_uri=https%3A%2F%2F{PROXY}%2F"}, "signin", PROXY)[0])

    def test_a_refusal_has_no_redirect_to_read_so_the_flag_changes_nothing(self):
        def refuses(url, headers):
            return (200, {}, b"ok") if url.endswith("/healthz") else (503, {}, b"sign-in is not set up")

        self.assertTrue(cc.door(PROXY, "refuse", refuses, proxied=True)[0])
        self.assertFalse(cc.door(PROXY, "signin", refuses, proxied=True)[0])

    def test_a_page_served_without_a_sign_in_and_a_made_up_header_that_is_trusted_fail_behind_a_proxy_too(self):
        def leaks(path):
            def get(url, headers):
                return (200, {}, b"<html>") if url.split(PROXY, 1)[1] == path else Proxied()(url, headers)
            return get

        for path in cc.PAGES:
            with self.subTest(path=path):
                passed, rows = cc.door(PROXY, "signin", leaks(path), proxied=True)
                self.assertFalse(passed)
                self.assertEqual({row[0] for row in rows if not row[2]}, {path})

    def test_every_request_goes_to_the_proxys_name_and_carries_no_credential(self):
        door = Proxied()
        cc.door(PROXY, "signin", door, proxied=True)
        self.assertEqual(len(door.calls), 1 + len(cc.PAGES) + len(cc.FORGED_PAGES))
        for url, headers in door.calls:
            self.assertTrue(url.startswith(f"https://{PROXY}/"), url)
            self.assertFalse({key.lower() for key in headers} & {"authorization", "cookie", "x-api-key", "ocp-apim-subscription-key", "x-original-host"}, headers)

    def test_the_flag_reaches_the_check_through_the_command_line(self):
        out = io.StringIO()
        self.assertEqual(cc.main(["door", "--host", PROXY, "--proxied"], Proxied(), out), 0)
        self.assertIn(f"PASS  /                            no sign-in", out.getvalue().splitlines()[1])
        out = io.StringIO()
        self.assertEqual(cc.main(["door", "--host", PROXY, "--proxied"], Proxied(named=HOST), out), 1)
        self.assertIn(f"but the return address names {HOST}", out.getvalue())
        self.assertEqual(cc.main(["door", "--host", PROXY], Proxied(named=HOST), io.StringIO()), 0, "without the flag nothing is asked of the return address")


class TheDoorInsideTheNetwork(unittest.TestCase):
    """The check of a closed app's front door runs in the Operator, at the app's own name, and asks first for a private address (--private): a closed app answers nobody outside the network, and an answer
    over a public address would prove nothing about the path that people take."""

    @staticmethod
    def resolver(*answers):
        """A name that resolves to the answers one after the other (a list of addresses, or an exception to raise); the last answer is the answer of every lookup after the list."""
        pending, calls = list(answers), []

        def resolve(name):
            calls.append(name)
            answer = pending.pop(0) if len(pending) > 1 else pending[0]
            if isinstance(answer, BaseException):
                raise answer
            return answer

        resolve.calls = calls
        return resolve

    def test_a_private_name_passes_the_first_row_says_which_address_and_every_other_row_is_the_door_as_it_was(self):
        resolve, door = self.resolver(["10.53.0.21"]), Door()
        passed, rows = cc.door(HOST, "signin", door, private=True, resolve=resolve)
        self.assertTrue(passed, rows)
        self.assertEqual(rows[0], ("name", "private address", True, "10.53.0.21 (private)"))
        self.assertEqual(len(rows), 1 + 1 + len(cc.PAGES) + len(cc.FORGED_PAGES))
        self.assertEqual(rows[1:], cc.door(HOST, "signin", Door())[1], "the rows of the door itself are the ones of a door that was not asked for a private name")
        self.assertEqual(resolve.calls, [HOST], "the name is looked up once, before anything is asked")
        self.assertEqual(len(door.calls), 1 + len(cc.PAGES) + len(cc.FORGED_PAGES))

    def test_the_expected_answers_do_not_change_inside_the_network(self):
        resolve = self.resolver(["10.53.0.21"])
        self.assertTrue(cc.door(HOST, "refuse", Door("refuse"), private=True, resolve=resolve)[0])
        self.assertFalse(cc.door(HOST, "signin", Door("refuse"), private=True, resolve=resolve)[0])
        self.assertFalse(cc.door(HOST, "signin", Door(leak="/history"), private=True, resolve=resolve)[0])
        passed, rows = cc.door(HOST, "signin", Door(trust_header=True), private=True, resolve=resolve)
        self.assertFalse(passed)
        self.assertEqual([row[0] for row in rows if not row[2]], list(cc.FORGED_PAGES), "a made-up sign-in header that the app would trust fails, here too")

    def test_a_public_name_or_one_that_does_not_resolve_ends_the_check_with_one_failed_line_and_no_request(self):
        required = ", and a private address is required: the landing zone has not registered the endpoint's name, or this DNS does not see it"
        for answer, text in ((["20.50.1.2"], f"{HOST} resolves to 20.50.1.2 (public){required}"),
                             (["10.53.0.21", "20.50.1.2"], f"{HOST} resolves to 20.50.1.2 (public){required}"),
                             (["100.64.0.1"], f"{HOST} resolves to 100.64.0.1 (public){required}"),
                             ([], f"{HOST} resolves to no address{required}"),
                             (socket.gaierror("no such name"), f"{HOST} does not resolve (gaierror)"),
                             (TimeoutError("timed out"), f"{HOST} does not resolve (TimeoutError)")):
            with self.subTest(answer=repr(answer)):
                door = Door()
                passed, rows = cc.door(HOST, "signin", door, private=True, resolve=self.resolver(answer))
                self.assertFalse(passed)
                self.assertEqual(rows, [("name", "private address", False, text)])
                self.assertEqual(door.calls, [], "no request is made to a name that is not private: a closed app refuses it, and it proves nothing")

    def test_without_the_option_nothing_is_looked_up_and_the_door_is_what_it_was(self):
        resolve = self.resolver(["20.50.1.2"])
        passed, rows = cc.door(HOST, "signin", Door(), resolve=resolve)
        self.assertTrue(passed)
        self.assertEqual(resolve.calls, [])
        self.assertEqual(len(rows), 1 + len(cc.PAGES) + len(cc.FORGED_PAGES))
        self.assertNotIn("private address", [row[1] for row in rows])

    def test_a_bad_host_or_expectation_is_refused_before_the_name_is_looked_up(self):
        resolve = self.resolver(["10.53.0.21"])
        for host, expect in (("not a host", "signin"), ("not_a_host", "signin"), (HOST, "maybe")):
            with self.assertRaises(cc.Problem):
                cc.door(host, expect, Door(), private=True, resolve=resolve)
        self.assertEqual(resolve.calls, [])

    def test_the_option_reaches_the_check_through_the_command_line_and_the_lines_and_the_exit_codes_say_what_was_seen(self):
        out = io.StringIO()
        self.assertEqual(cc.main(["door", "--host", HOST, "--private"], Door(), out, self.resolver(["10.53.0.21"])), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], f"PASS  {'name':28} {'private address':24} 10.53.0.21 (private)")
        self.assertEqual(len(lines), 1 + 1 + len(cc.PAGES) + len(cc.FORGED_PAGES))
        door, out = Door(), io.StringIO()
        self.assertEqual(cc.main(["door", "--host", HOST, "--private"], door, out, self.resolver(["20.50.1.2"])), 1)
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertTrue(out.getvalue().startswith(f"FAIL  {'name':28} {'private address':24} {HOST} resolves to 20.50.1.2 (public)"), out.getvalue())
        self.assertEqual(door.calls, [])
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            self.assertEqual(cc.main(["door", "--host", HOST, "--private", "--summary", str(summary)], Door(), io.StringIO(), self.resolver(["10.53.0.21"])), 0)
            self.assertIn("PASS  name", summary.read_text(encoding="utf-8"))
        self.assertEqual(cc.main(["door", "--host", HOST], Door(), io.StringIO(), self.resolver(OSError("must not be asked"))), 0, "without the option the lookup is never made")

    def test_the_option_is_off_unless_it_is_asked_for_and_goes_with_the_other_options(self):
        seen = []

        def spy(host, expect, get, proxied, private, resolve):
            seen.append((host, expect, proxied, private))
            return True, []

        with mock.patch.object(cc, "door", spy):
            cc.main(["door", "--host", HOST.upper()], Door(), io.StringIO())
            cc.main(["door", "--host", HOST, "--private", "--expect", "refuse"], Door(), io.StringIO())
            cc.main(["door", "--host", HOST, "--proxied", "--private"], Door(), io.StringIO())
        self.assertEqual(seen, [(HOST, "signin", False, False), (HOST, "refuse", False, True), (HOST, "signin", True, True)])

    def test_the_lookup_is_the_one_of_the_health_check_and_the_private_ranges_are_the_same(self):
        answer = [(2, 1, 6, "", ("10.53.0.21", 443)), (2, 1, 6, "", ("10.53.0.20", 443))]
        with mock.patch("socket.getaddrinfo", return_value=answer) as lookup:
            passed, rows = cc.door(HOST, "signin", Door(), private=True)
        self.assertTrue(passed, rows)
        lookup.assert_called_once_with(HOST, 443, type=socket.SOCK_STREAM)
        self.assertEqual(rows[0][3], "10.53.0.20 (private)", "the addresses are sorted, as the health check lists them")
        for address in ("10.0.0.1", "172.16.0.1", "192.168.1.1"):
            self.assertTrue(cc.private_name(HOST, lambda name, address=address: [address])[0], address)
        for address in ("9.255.255.255", "172.32.0.1", "192.169.0.1", "127.0.0.1", "169.254.169.254", "::1"):
            self.assertFalse(cc.private_name(HOST, lambda name, address=address: [address])[0], address)


class Answers:
    """The health address as it answers one try after another: (status, body) or an exception to raise. The last answer is the answer of every try after the list."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers), timeout))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        status, body = answer
        return status, {}, body


def run_health(get, addresses=("10.53.0.21",), tries=5, private=True, interval=10.0, timeout=15.0, host=HOST):
    """cc.health with a name that resolves to `addresses` (a list, or a list of lists and exceptions, one for each try), and a clock that only counts."""
    sleeps, out = [], io.StringIO()
    results = list(addresses) if addresses and isinstance(addresses[0], (list, BaseException)) else [list(addresses)]

    def resolve(name):
        result = results.pop(0) if len(results) > 1 else results[0]
        if isinstance(result, BaseException):
            raise result
        return result

    ok = cc.health(host, tries, interval, timeout, private, get, resolve, sleeps.append, out)
    return ok, sleeps, out.getvalue().splitlines()


class TheHealthCheckInsideTheNetwork(unittest.TestCase):
    """The check that the cases app answers once its code is published: made from the Operator, over the app's private endpoint, on the app's own name."""

    URL = f"https://{HOST}/healthz"

    def test_an_app_that_answers_ok_at_once_ends_the_wait_with_one_request_and_no_sleep(self):
        get = Answers((200, b"ok"))
        ok, sleeps, lines = run_health(get)
        self.assertTrue(ok)
        self.assertEqual(sleeps, [])
        self.assertEqual(lines, [f"ok: {self.URL} answered 200 ok at try 1, 10.53.0.21 (private)"])
        self.assertEqual(get.calls, [(self.URL, {}, 15.0)], "one plain request to the health address: no header, no credential, the timeout that was asked for")

    def test_an_app_that_is_still_starting_is_waited_for_with_the_interval_between_the_tries_and_each_try_says_what_it_saw(self):
        ok, sleeps, lines = run_health(Answers((503, b""), (502, b"Bad Gateway"), (200, b"ok")), interval=7.0)
        self.assertTrue(ok)
        self.assertEqual(sleeps, [7.0, 7.0])
        self.assertEqual(lines, ["try 1 of 5: 10.53.0.21 (private), HTTP 503", "try 2 of 5: 10.53.0.21 (private), HTTP 502 Bad Gatewa",
                                 f"ok: {self.URL} answered 200 ok at try 3, 10.53.0.21 (private)"])

    def test_an_app_that_never_answers_ok_fails_after_all_its_tries_and_sleeps_between_them_and_not_after_the_last(self):
        ok, sleeps, lines = run_health(Answers((503, b"")), tries=4)
        self.assertFalse(ok)
        self.assertEqual(len(sleeps), 3)
        self.assertEqual(lines[-1], f"FAIL: {self.URL} did not answer 200 ok in 4 tries")
        self.assertEqual(len(lines), 5)

    def test_only_the_word_ok_with_status_200_is_healthy_and_a_redirect_is_not_followed_or_taken_for_health(self):
        for answer in ((200, b"hello"), (200, b""), (302, b"ok"), (301, b""), (204, b"ok"), (401, b"ok"), (403, b"ok")):
            with self.subTest(answer=answer):
                self.assertFalse(run_health(Answers(answer), tries=2)[0])
        self.assertTrue(run_health(Answers((200, b"ok\n")))[0], "a line break after the word is no difference")

    def test_a_try_that_gets_no_answer_says_what_kind_of_failure_it_was_and_the_wait_goes_on(self):
        for error in (TimeoutError("timed out"), urllib.error.URLError("refused"), http.client.RemoteDisconnected("closed"), ConnectionRefusedError("no"), cc.Problem("no answer")):
            with self.subTest(error=type(error).__name__):
                ok, sleeps, lines = run_health(Answers(error, (200, b"ok")))
                self.assertTrue(ok)
                self.assertEqual(lines[0], f"try 1 of 5: 10.53.0.21 (private), no answer ({type(error).__name__})")
                self.assertEqual(len(sleeps), 1)

    def test_a_name_that_does_not_resolve_yet_is_waited_for_and_never_asked(self):
        import socket

        get = Answers((200, b"ok"))
        ok, sleeps, lines = run_health(get, addresses=[socket.gaierror("no such name"), socket.gaierror("no such name"), ["10.53.0.21"]])
        self.assertTrue(ok)
        self.assertEqual(lines[:2], [f"try 1 of 5: {HOST} does not resolve (gaierror)", f"try 2 of 5: {HOST} does not resolve (gaierror)"])
        self.assertEqual(len(get.calls), 1, "nothing is asked until the name resolves")

    def test_a_private_name_is_required_when_it_is_asked_for_and_no_request_is_made_to_a_public_address(self):
        get = Answers((200, b"ok"))
        ok, sleeps, lines = run_health(get, addresses=["20.50.1.2"], tries=3, private=True)
        self.assertFalse(ok)
        self.assertEqual(get.calls, [], "an answer over a public address proves nothing about the path that people take, and a closed app refuses it")
        self.assertEqual(lines[0], f"try 1 of 3: {HOST} resolves to 20.50.1.2 (public), and a private address is required: the landing zone has not registered the endpoint's name, "
                                   "or this DNS does not see it")
        self.assertEqual(len(sleeps), 2)
        ok, _, lines = run_health(Answers((200, b"ok")), addresses=["20.50.1.2"], private=False)
        self.assertTrue(ok)
        self.assertEqual(lines, [f"ok: {self.URL} answered 200 ok at try 1, 20.50.1.2 (public)"])

    def test_one_public_address_among_the_private_ones_makes_the_name_public(self):
        for addresses in (["10.53.0.21", "20.50.1.2"], ["::1"], ["fd00::1"], ["100.64.0.1"], ["172.32.0.1"], ["192.169.0.1"], [], ["not an address"]):
            with self.subTest(addresses=addresses):
                get = Answers((200, b"ok"))
                self.assertFalse(run_health(get, addresses=addresses, tries=1, private=True)[0])
                self.assertEqual(get.calls, [])

    def test_the_addresses_of_the_three_private_ranges_are_private_and_nothing_else_is(self):
        for address in ("10.0.0.1", "10.255.255.255", "172.16.0.1", "172.31.255.255", "192.168.0.1", "192.168.255.255"):
            self.assertTrue(cc.is_private(address), address)
        for address in ("9.255.255.255", "11.0.0.1", "172.15.255.255", "172.32.0.0", "192.167.255.255", "192.169.0.0", "127.0.0.1", "169.254.169.254", "20.50.1.2", "::1", "", "x"):
            self.assertFalse(cc.is_private(address), address)

    def test_a_bad_host_or_a_bad_number_is_refused_before_anything_is_asked(self):
        get = Answers((200, b"ok"))
        for host, tries, interval, timeout in (("bad host", 5, 10, 15), ("Example.com/", 5, 10, 15), (HOST, 0, 10, 15), (HOST, 121, 10, 15), (HOST, 5, -1, 15), (HOST, 5, 61, 15),
                                              (HOST, 5, 10, 0), (HOST, 5, 10, 61)):
            with self.subTest(host=host, tries=tries, interval=interval, timeout=timeout):
                with self.assertRaises(cc.Problem):
                    cc.health(host, tries, interval, timeout, True, get, lambda name: ["10.53.0.21"], lambda seconds: None, io.StringIO())
        self.assertEqual(get.calls, [])

    def test_the_bounds_that_are_allowed_are_the_ones_that_the_workflow_uses_and_a_little_more(self):
        self.assertEqual((cc.HEALTH_TRIES_MAX, cc.HEALTH_INTERVAL_MAX, cc.HEALTH_TIMEOUT_MAX), (120, 60, 60))
        self.assertTrue(run_health(Answers((200, b"ok")), tries=120, interval=60.0, timeout=60.0)[0])
        self.assertTrue(run_health(Answers((200, b"ok")), tries=1, interval=0.0, timeout=1.0)[0])

    def test_one_request_is_made_by_the_default_getter_with_the_timeout_it_is_given_and_no_second_try(self):
        seen = []

        class Response:
            status, headers = 200, {"Content-Type": "text/plain"}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                return b"ok"

        class Opener:
            def open(self, request, timeout):
                seen.append((request.full_url, request.get_method(), timeout, request.get_header("User-agent")))
                if len(seen) == 1:
                    return Response()
                raise TimeoutError("timed out")

        with mock.patch("urllib.request.build_opener", return_value=Opener()):
            self.assertEqual(cc.fetch_once(self.URL, {}, 7), (200, {"content-type": "text/plain"}, b"ok"))
            with self.assertRaises(TimeoutError):
                cc.fetch_once(self.URL, {}, 7)
        self.assertEqual([entry[:3] for entry in seen], [(self.URL, "GET", 7), (self.URL, "GET", 7)], "each call asks once: the loop of the check is the one that tries again")

    def test_an_error_status_is_an_answer_and_not_a_failure_to_answer(self):
        error = urllib.error.HTTPError(self.URL, 503, "unavailable", {"Retry-After": "5"}, io.BytesIO(b"busy"))

        class Opener:
            def open(self, request, timeout):
                raise error

        with mock.patch("urllib.request.build_opener", return_value=Opener()):
            self.assertEqual(cc.fetch_once(self.URL, {}, 7), (503, {"retry-after": "5"}, b"busy"))

    def test_the_name_is_resolved_for_the_port_of_https_and_the_addresses_are_sorted_and_listed_once(self):
        import socket

        answer = [(2, 1, 6, "", ("10.53.0.21", 443)), (2, 1, 6, "", ("10.53.0.21", 443)), (2, 1, 6, "", ("10.53.0.20", 443))]
        with mock.patch("socket.getaddrinfo", return_value=answer) as lookup:
            self.assertEqual(cc.resolve_host(HOST), ["10.53.0.20", "10.53.0.21"])
        lookup.assert_called_once_with(HOST, 443, type=socket.SOCK_STREAM)

    def test_the_command_exits_0_when_the_app_answers_1_when_it_does_not_and_2_for_a_host_that_is_none(self):
        out = io.StringIO()
        get = Answers((503, b""), (200, b"ok"))
        slept = []
        self.assertEqual(cc.main(["health", "--host", HOST, "--tries", "3", "--interval", "4", "--timeout", "5", "--private"], get, out, lambda name: ["10.53.0.21"], slept.append), 0)
        self.assertEqual(slept, [4.0])
        self.assertEqual([call[2] for call in get.calls], [5.0, 5.0])
        self.assertIn(f"ok: {self.URL} answered 200 ok at try 2", out.getvalue())
        out = io.StringIO()
        self.assertEqual(cc.main(["health", "--host", HOST, "--tries", "2", "--interval", "0"], Answers((500, b"")), out, lambda name: ["10.53.0.21"], lambda seconds: None), 1)
        self.assertIn("FAIL: ", out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as complaints:
            self.assertEqual(cc.main(["health", "--host", "bad host"], Answers((200, b"ok")), io.StringIO(), lambda name: ["10.53.0.21"], lambda seconds: None), 2)
            self.assertEqual(cc.main(["health", "--host", HOST, "--tries", "0"], Answers((200, b"ok")), io.StringIO(), lambda name: ["10.53.0.21"], lambda seconds: None), 2)
            with self.assertRaises(SystemExit) as refused:
                cc.main(["health", "--host", HOST, "--tries", "many"], Answers((200, b"ok")), io.StringIO())
        self.assertEqual(refused.exception.code, 2)
        self.assertIn("console-check: --tries is a number from 1 to 120", complaints.getvalue())

    def test_private_is_off_unless_it_is_asked_for_and_the_defaults_are_the_ones_of_the_workflow(self):
        seen = []

        def spy(host, tries, interval, timeout, private, *rest):
            seen.append((host, tries, interval, timeout, private))
            return True

        with mock.patch.object(cc, "health", spy):
            cc.main(["health", "--host", HOST.upper()], Answers((200, b"ok")), io.StringIO())
            cc.main(["health", "--host", HOST, "--private"], Answers((200, b"ok")), io.StringIO())
        self.assertEqual(seen, [(HOST, 60, 10.0, 15.0, False), (HOST, 60, 10.0, 15.0, True)])


class Clock:
    """A clock that only counts: the monotonic reading, the sleeps that move it, and the time of day (UTC) that goes with it."""

    START = cc.datetime.datetime(2026, 11, 7, 12, 0, 0, tzinfo=cc.datetime.timezone.utc)

    def __init__(self):
        self.t = 0.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds

    def now(self):
        return self.START + cc.datetime.timedelta(seconds=self.t)


class Timed:
    """The health address as it answers, request after request, with the time that each answer takes on the fake clock: (status, body, seconds) or (exception, seconds). The last
    answer is the answer of every request after the list. The seconds that each request was started at are kept."""

    def __init__(self, clock, *answers):
        self.clock, self.answers, self.started, self.timeouts = clock, list(answers), [], []

    def __call__(self, url, headers, timeout):
        self.started.append(self.clock.t)
        self.timeouts.append(timeout)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        self.clock.t += answer[-1]
        if isinstance(answer[0], BaseException):
            raise answer[0]
        status, body, _ = answer
        return status, {}, body


def run_latency(*answers, minutes=4, interval=10.0, private=True, idle=None, after_idle=3, timeout=75.0, addresses=("10.53.0.21",), host=HOST):
    """cc.latency on the fake clock; the answers are those of Timed, and the name resolves to `addresses`."""
    clock = Clock()
    get = Timed(clock, *answers)
    out = io.StringIO()
    code = cc.latency(host, minutes, interval, private, idle, after_idle, timeout, get, lambda name: list(addresses), clock.sleep, clock, clock.now, out)
    return code, out.getvalue().splitlines(), get, clock


class TheLatencyMeasurement(unittest.TestCase):
    """The web page's answering time, measured from inside the network over the app's private endpoint, for the decision in docs/proposals/07-private-by-default.md."""

    URL = f"https://{HOST}/healthz"
    FAST = (200, b"ok", 0.25)

    def test_a_run_asks_every_interval_for_its_minutes_with_a_quiet_gap_and_three_requests_after_it(self):
        code, lines, get, clock = run_latency(self.FAST, minutes=20)
        # 20 minutes: 8 of them quiet (the default for a run of 16 minutes or more), then 3 requests ten seconds apart, so the requests before the gap fill 700 seconds
        self.assertEqual(len(get.started), 70 + 3)
        self.assertEqual(get.started[:3], [0.0, 10.0, 20.0], "the interval is counted from the start of a request, not from its end")
        self.assertEqual(get.started[69], 690.0)
        self.assertEqual(get.started[70], 690.0 + 0.25 + 480.0, "the first request after the gap is made when the gap, which starts when the last request is answered, is over")
        self.assertEqual(get.started[71] - get.started[70], 10.0)
        self.assertEqual(clock.slept.count(480.0), 1, "one quiet gap of eight minutes")
        self.assertLessEqual(clock.t, 20 * 60, "the run does not take more than the minutes that were asked for")
        self.assertGreater(clock.t, 19 * 60)
        self.assertEqual(code, 0)

    def test_every_request_is_a_line_with_the_time_the_status_and_the_seconds_and_the_gap_and_the_requests_after_it_are_named(self):
        code, lines, get, clock = run_latency(self.FAST, (503, b"", 21.5), self.FAST, minutes=4, interval=10.0)
        self.assertEqual(lines[0], "name: 10.53.0.21 (private)")
        self.assertTrue(lines[1].startswith(f"latency: {self.URL} every 10 seconds for 4 minutes"), lines[1])
        requests = [line for line in lines if re.match(r"^\d\d:\d\d:\d\d  ", line)]
        self.assertEqual(requests[0], f"12:00:00  {'200':24} {0.25:7.3f} s")
        self.assertEqual(requests[1], f"12:00:10  {'503':24} {21.5:7.3f} s", "the time is when the request was made")
        self.assertEqual(requests[2], f"12:00:31  {'200':24} {0.25:7.3f} s", "a request that took longer than the interval is followed at once, and nothing is asked in parallel")
        self.assertIn("quiet gap of 2 minutes: no request", "\n".join(lines))
        after = [line for line in requests if line.endswith("after the quiet gap")]
        self.assertEqual(len(after), 3)

    def test_the_summary_line_has_the_count_the_median_the_95th_percentile_the_slowest_and_the_three_counts(self):
        # 10 requests before the gap and 3 after it: twelve at 0.25 s, and one of 16 s that is not answered 200
        code, lines, get, clock = run_latency(*[self.FAST] * 4, (503, b"unavailable", 16.0), *[self.FAST] * 8, minutes=4, interval=10.0)
        summary = [line for line in lines if line.startswith("latency: ") and "requests, p50" in line]
        self.assertEqual(summary, ["latency: 13 requests, p50 0.25 s, p95 16.00 s, max 16.00 s, 1 not 200, 1 slower than 5 s, 1 slower than 15 s"])
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], "verdict: 1 of 13 requests took more than 15 seconds and 1 did not answer 200: the rule of docs/proposals/07-private-by-default.md is not met")

    def test_a_run_with_no_request_over_15_seconds_and_none_that_was_not_200_meets_the_rule_even_when_one_took_more_than_5(self):
        code, lines, get, clock = run_latency(self.FAST, (200, b"ok", 6.5), self.FAST, minutes=4)
        self.assertEqual(code, 0)
        self.assertIn("1 slower than 5 s, 0 slower than 15 s", "\n".join(lines))
        self.assertEqual(lines[-1], "verdict: no request took more than 15 seconds and none was not 200")

    def test_exactly_15_seconds_is_not_more_than_15_and_exactly_5_is_not_more_than_5(self):
        code, lines, _, _ = run_latency((200, b"ok", 15.0), (200, b"ok", 5.0), self.FAST, minutes=4)
        self.assertEqual(code, 0)
        self.assertIn("0 not 200, 1 slower than 5 s, 0 slower than 15 s", "\n".join(lines))

    def test_a_request_that_gets_no_answer_is_a_line_and_is_not_200_and_the_run_goes_on(self):
        code, lines, get, clock = run_latency(self.FAST, (TimeoutError("timed out"), 75.0), self.FAST, minutes=4)
        self.assertEqual(code, 1)
        self.assertIn(f"12:00:10  {'no answer (TimeoutError)':24} {75.0:7.3f} s", lines)
        self.assertIn("1 not 200, 1 slower than 5 s, 1 slower than 15 s", "\n".join(lines))
        for error in (urllib.error.URLError("refused"), http.client.RemoteDisconnected("closed"), ConnectionResetError("reset"), cc.Problem("no answer")):
            with self.subTest(error=type(error).__name__):
                _, lines, _, _ = run_latency(self.FAST, (error, 0.5), self.FAST, minutes=4)
                self.assertTrue(any(f"no answer ({type(error).__name__})" in line for line in lines))

    def test_only_status_200_with_the_word_ok_is_an_answer(self):
        for answer in ((200, b"hello", 0.25), (200, b"", 0.25), (302, b"ok", 0.25), (401, b"ok", 0.25), (500, b"", 0.25)):
            with self.subTest(answer=answer):
                code, lines, _, _ = run_latency(self.FAST, answer, self.FAST, minutes=4)
                self.assertEqual(code, 1)
                self.assertIn("1 not 200,", "\n".join(lines))
        self.assertEqual(run_latency((200, b"ok\n", 0.25), minutes=4)[0], 0)

    def test_a_name_that_is_not_private_makes_no_request_when_private_is_asked_for_and_is_a_failure(self):
        for addresses in (["20.50.1.2"], ["10.53.0.21", "20.50.1.2"], [], ["::1"]):
            with self.subTest(addresses=addresses):
                code, lines, get, clock = run_latency(self.FAST, addresses=addresses)
                self.assertEqual(code, 1)
                self.assertEqual(get.started, [], "a closed app refuses a request over a public address, and an answer over one proves nothing about the path that people take")
                self.assertTrue(lines[0].startswith("name: "), lines[0])
                self.assertEqual(lines[-1], "FAIL: no request was made: with --private the name has to resolve to private addresses only")
        code, lines, get, _ = run_latency(self.FAST, addresses=["20.50.1.2"], private=False, minutes=4)
        self.assertEqual(code, 0, "without --private the name is not looked at")
        self.assertNotEqual(get.started, [])

    def test_the_defaults_are_eight_quiet_minutes_for_a_run_of_sixteen_or_more_half_the_run_below_that_and_none_when_it_is_off(self):
        for minutes, idle in ((20, 8), (16, 8), (15, 7), (10, 5), (4, 2), (3, 1), (2, 1), (1, 0)):
            with self.subTest(minutes=minutes):
                _, lines, _, clock = run_latency(self.FAST, minutes=minutes)
                if idle:
                    self.assertIn(f"quiet gap of {idle} minutes: no request", "\n".join(lines))
                    self.assertEqual(clock.slept.count(idle * 60.0), 1)
                else:
                    self.assertNotIn("quiet gap", "\n".join(lines))
        _, lines, get, clock = run_latency(self.FAST, minutes=4, idle=0)
        self.assertNotIn("quiet gap", "\n".join(lines))
        self.assertEqual(len(get.started), 24, "four minutes of a request every ten seconds")
        self.assertFalse(any(line.endswith("after the quiet gap") for line in lines))
        _, lines, get, _ = run_latency(self.FAST, minutes=10, idle=3, after_idle=2)
        self.assertEqual(sum(1 for line in lines if line.endswith("after the quiet gap")), 2)

    def test_the_first_answer_after_the_gap_is_reported_apart_so_that_a_start_from_zero_shows(self):
        code, lines, get, clock = run_latency(*[self.FAST] * 10, (200, b"ok", 8.0), self.FAST, self.FAST, minutes=4)
        self.assertEqual(code, 0)
        self.assertIn("after the quiet gap: 3 requests, the first took 8.00 s, the slowest 8.00 s", lines)
        self.assertEqual(lines[-1], "verdict: no request took more than 15 seconds and none was not 200")

    def test_the_percentiles_are_the_nearest_rank_ones(self):
        values = [float(n) for n in range(1, 101)]
        self.assertEqual((cc.percentile(values, 50), cc.percentile(values, 95), cc.percentile(values, 100)), (50.0, 95.0, 100.0))
        self.assertEqual((cc.percentile([3.0], 50), cc.percentile([3.0], 95)), (3.0, 3.0))
        self.assertEqual((cc.percentile([1.0, 9.0], 50), cc.percentile([1.0, 9.0], 95)), (1.0, 9.0))
        self.assertEqual(cc.percentile([1.0, 2.0, 3.0, 4.0], 50), 2.0)

    def test_the_timeout_that_was_asked_for_goes_to_every_request_and_the_default_is_longer_than_the_minute_that_the_front_end_held_requests_for(self):
        _, _, get, _ = run_latency(self.FAST, minutes=4, timeout=90.0)
        self.assertEqual(set(get.timeouts), {90.0})
        self.assertGreater(cc.LATENCY_TIMEOUT_DEFAULT, 60)
        self.assertEqual(cc.LATENCY_MINUTES_MAX, 20)

    def test_bad_numbers_and_a_bad_host_are_refused_before_anything_is_asked(self):
        for kwargs in ({"minutes": 0}, {"minutes": 21}, {"interval": 4.0}, {"interval": 61.0}, {"timeout": 0.0}, {"timeout": 121.0}, {"idle": -1}, {"idle": 4, "minutes": 4},
                       {"idle": 2, "after_idle": 0}, {"idle": 2, "after_idle": 11}, {"minutes": 2, "idle": 1, "interval": 60.0}, {"host": "not a host"}, {"host": "Example.com/"}):
            with self.subTest(kwargs=kwargs):
                clock = Clock()
                get = Timed(clock, self.FAST)
                arguments = {"minutes": 4, "interval": 10.0, "idle": None, "after_idle": 3, "timeout": 75.0, "host": HOST, **kwargs}
                with self.assertRaises(cc.Problem):
                    cc.latency(arguments["host"], arguments["minutes"], arguments["interval"], True, arguments["idle"], arguments["after_idle"], arguments["timeout"], get,
                               lambda name: ["10.53.0.21"], clock.sleep, clock, clock.now, io.StringIO())
                self.assertEqual(get.started, [])

    def test_the_command_runs_the_measurement_with_the_flags_of_the_workflow_and_exits_with_the_rule(self):
        clock = Clock()
        get = Timed(clock, self.FAST)
        out = io.StringIO()
        code = cc.main(["latency", "--host", HOST.upper(), "--private", "--minutes", "4", "--interval", "10"], get, out, lambda name: ["10.53.0.21"], clock.sleep, clock, clock.now)
        self.assertEqual(code, 0)
        self.assertEqual(set(get.timeouts), {75.0})
        self.assertIn("latency: 13 requests, p50 0.25 s", out.getvalue())
        clock = Clock()
        code = cc.main(["latency", "--host", HOST, "--private", "--minutes", "4", "--interval", "10"], Timed(clock, (200, b"ok", 0.25), (504, b"", 30.0)), io.StringIO(),
                       lambda name: ["10.53.0.21"], clock.sleep, clock, clock.now)
        self.assertEqual(code, 1)
        with contextlib.redirect_stderr(io.StringIO()) as complaints:
            self.assertEqual(cc.main(["latency", "--host", HOST, "--minutes", "21"], Timed(clock, self.FAST), io.StringIO(), lambda name: ["10.53.0.21"], clock.sleep, clock, clock.now), 2)
        self.assertIn("console-check: --minutes is a whole number from 1 to 20", complaints.getvalue())

    def test_the_other_commands_keep_their_defaults(self):
        seen = []

        def spy(host, tries, interval, timeout, private, *rest):
            seen.append((host, tries, interval, timeout, private))
            return True

        with mock.patch.object(cc, "health", spy):
            cc.main(["health", "--host", HOST], Answers((200, b"ok")), io.StringIO())
            cc.main(["health", "--host", HOST, "--timeout", "7"], Answers((200, b"ok")), io.StringIO())
        self.assertEqual(seen, [(HOST, 60, 10.0, 15.0, False), (HOST, 60, 10.0, 7.0, False)], "the health check still asks for 15 seconds a request unless it is told otherwise")


class TheToolInTheContainer(unittest.TestCase):
    """tools/console-check.py runs in the Operator like the two check tools: the image has Python 3.12, and the file is the only one in the secret volume."""

    def test_it_parses_as_python_3_12_and_imports_the_standard_library_only(self):
        # CI and the function app use Python 3.13, the image of the Operator has 3.12: a syntax of 3.13 would pass every test here and fail in the container.
        tree = ast.parse((ROOT / "tools" / "console-check.py").read_text(encoding="utf-8"), feature_version=(3, 12))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        self.assertLessEqual(imported, set(sys.stdlib_module_names), sorted(imported - set(sys.stdlib_module_names)))

    def test_it_runs_from_a_folder_that_holds_only_it_and_leaves_nothing_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            volume = Path(tmp)
            (volume / "console-check.py").write_bytes((ROOT / "tools" / "console-check.py").read_bytes())
            for command, option in (("health", "--private"), ("door", "--proxied"), ("door", "--private"), ("latency", "--minutes"), ("latency", "--idle-minutes")):
                done = subprocess.run([sys.executable, "-B", str(volume / "console-check.py"), command, "--help"], capture_output=True, text=True, cwd=volume)
                self.assertEqual((done.returncode, done.stderr), (0, ""), command)
                self.assertIn(option, done.stdout, command)
            self.assertEqual([path.name for path in volume.iterdir()], ["console-check.py"], "nothing was written to the folder: no bytecode, no cache")

    def test_a_host_that_is_not_one_is_refused_with_exit_code_2_and_without_a_trace(self):
        done = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "console-check.py"), "health", "--host", "not a host"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stderr.strip(), "console-check: --host is a host name")
        self.assertEqual(done.stdout, "")


if __name__ == "__main__":
    unittest.main()
