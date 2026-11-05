import importlib.util
import io
import re
import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(len(rows), 1 + len(cc.PAGES) + 2)

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
        self.assertEqual(len([r for r in rows if not r[2]]), 2)

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


class TheCommand(unittest.TestCase):
    def test_exit_codes_output_and_summary(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            self.assertEqual(cc.main(["door", "--host", HOST, "--summary", str(summary)], Door(), out), 0)
            self.assertIn("PASS  /healthz", out.getvalue())
            self.assertIn("Nobody gets a page without a sign-in.", summary.read_text(encoding="utf-8"))
            out = io.StringIO()
            self.assertEqual(cc.main(["door", "--host", HOST, "--summary", str(summary)], Door(leak="/history"), out), 1)
            self.assertIn("FAIL  /history", out.getvalue())
            self.assertIn("got something that it should not", summary.read_text(encoding="utf-8"))
        self.assertEqual(cc.main(["door", "--host", "bad host"], Door(), io.StringIO()), 2)

    def test_it_is_standard_library_only_and_makes_no_write(self):
        source = (ROOT / "tools" / "console-check.py").read_text(encoding="utf-8")
        modules = set(re.findall(r"^(?:import|from) (\w+)", source, re.M))
        self.assertTrue(modules <= {"argparse", "re", "ssl", "sys", "urllib", "uuid", "typing", "__future__"}, modules)
        self.assertNotRegex(source, r'method="(POST|PUT|PATCH|DELETE)"')


if __name__ == "__main__":
    unittest.main()
