import ast
import dataclasses
import importlib
import re
import socket
import subprocess
import sys
import unittest
from unittest import mock

from support import APP_ROOT
from test_packaging import FORBIDDEN, KEY_WORDS
from test_web_support import MAYA, OPS, TINO, Console, make_action, make_decision

WEB = APP_ROOT / "cases" / "web"
OUR_TESTS = sorted((APP_ROOT / "tests").glob("test_web_*.py"))
NOT_FOR_A_PAGE = {"socket", "ssl", "http", "urllib.request", "urllib.error", "subprocess", "ftplib", "smtplib", "telnetlib", "xmlrpc", "asyncio", "threading", "multiprocessing", "os",
                  "pathlib", "shutil", "tempfile", "sqlite3", "pickle", "shelve", "ctypes", "importlib", "webbrowser", "glob", "fileinput", "random", "secrets", "uuid"}


def modules():
    return sorted(p for p in WEB.glob("*.py"))


def imported(path):
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [(alias.name, 0) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append((node.module, node.level))
            else:  # `from .. import costs`: what is imported is the module
                found += [(alias.name, node.level) for alias in node.names]
    return found


class ThePackage(unittest.TestCase):
    def test_the_files_are_where_they_should_be_and_nothing_else_is(self):
        self.assertEqual([p.name for p in modules()], ["__init__.py", "approval.py", "brief_page.py", "common.py", "core.py", "figures.py", "history.py", "home.py", "layout.py",
                                                       "notebook.py", "notes.py", "ops.py", "router.py", "settings.py", "style.py", "words.py"])
        self.assertEqual(sorted(p.name for p in WEB.iterdir() if p.name != "__pycache__"), [p.name for p in modules()])

    def test_it_imports_the_standard_library_only_and_the_modules_of_the_contract(self):
        standard = set(sys.stdlib_module_names)
        for path in modules():
            for module, level in imported(path):
                with self.subTest(file=path.name, module=module, level=level):
                    if level == 0:
                        self.assertIn(module.split(".")[0], standard)
                    elif level == 1:
                        self.assertIn(module.split(".")[0], {"", "core", "layout", "common", "words", "approval", "brief_page", "figures", "history", "home", "notebook", "notes", "ops", "router",
                                                             "settings", "style"})
                    else:
                        self.assertEqual(level, 2)
                        # `usage` joined the three modules of the contract with the chart of use: a table of data and a few pure functions that reads nothing (the test below pins that). `costs` and
                        # `estimate` joined them with the cost of a whole subscription and the estimate at list price: the words and the address of the cost, and a table of prices (the test after it
                        # pins that they are of the same kind). `cardlinks` joined them with the buttons of a Teams card: the shape of their addresses and of their link tokens (pinned the same way).
                        self.assertIn(module, {"brief", "models", "people", "usage", "costs", "estimate", "cardlinks"}, "the pages know the records, the people, the decision brief, the table of the use "
                                                                                                                         "that is drawn, the words of the cost and the addresses of the buttons of a "
                                                                                                                         "card, and nothing of how they are kept")

    def test_the_table_of_use_that_the_pages_know_is_data_and_pure_functions_over_the_standard_library_and_nothing_of_the_app(self):
        self.check_that_a_module_is_pure("usage")

    def test_the_words_of_the_cost_and_the_table_of_list_prices_that_the_pages_know_are_pure_functions_over_the_standard_library_and_nothing_of_the_app(self):
        for name in ("costs", "estimate"):
            self.check_that_a_module_is_pure(name)

    def check_that_a_module_is_pure(self, name):
        path = APP_ROOT / "cases" / f"{name}.py"
        found = imported(path)
        self.assertEqual({level for _, level in found}, {0}, "it imports no module of the app: the pages must not reach the client, the store or the network through it")
        self.assertLessEqual({module.split(".")[0] for module, _ in found}, set(sys.stdlib_module_names))
        self.assertEqual({module for module, _ in found} & NOT_FOR_A_PAGE, set())
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"open", "eval", "exec", "compile", "__import__", "input", "print"}, f"{name}.py:{node.lineno}")
        self.assertNotRegex(source, r"\.now\(|\.today\(|time\.time\(", "no clock: a page gives it the day")

    def test_the_addresses_of_the_buttons_of_a_card_that_the_pages_know_are_data_and_pure_functions_over_the_standard_library_and_nothing_of_the_app(self):
        self.check_that_a_module_is_pure("cardlinks")

    def test_a_page_does_not_touch_a_network_a_process_or_a_file(self):
        for path in modules():
            names = {module for module, level in imported(path) if level == 0}
            with self.subTest(file=path.name):
                self.assertEqual(sorted(names & NOT_FOR_A_PAGE), [])
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"open", "eval", "exec", "compile", "__import__", "input", "print", "breakpoint"}, f"{path.name}:{node.lineno}")

    def test_no_file_of_the_package_or_of_its_tests_holds_a_word_that_a_key_or_a_secret_leaves_behind(self):
        also = ("".join(parts) for parts in (("instrumentation", "key"), ("DefaultEndpoints", "Protocol"), ("list", "Keys"), ("list", "Connection", "Strings"), ("secondary", "Key")))
        words = tuple(FORBIDDEN) + tuple(KEY_WORDS) + tuple(also)
        for path in modules() + OUR_TESTS:
            text = path.read_text(encoding="utf-8").lower()
            for word in words:
                with self.subTest(file=path.name, word=word):
                    self.assertNotIn(word.lower(), text)

    def test_the_package_exports_what_the_wiring_uses(self):
        web = importlib.import_module("cases.web")
        self.assertEqual(sorted(web.__all__), ["Request", "Response", "Services", "handle", "parse_request"])
        for name in web.__all__:
            self.assertTrue(hasattr(web, name))
        self.assertEqual([f.name for f in dataclasses.fields(web.Services)], ["store", "decider", "delegate", "people", "now", "host", "acts_on", "models", "base", "drift", "lessons", "checker"])
        self.assertEqual([f.name for f in dataclasses.fields(web.Request)], ["method", "path", "query", "headers", "form", "body", "problem"])
        self.assertEqual([f.name for f in dataclasses.fields(web.Response)], ["status", "headers", "body"])

    def test_the_pages_never_handle_a_token_and_the_only_outside_address_that_they_name_is_the_sign_in_in_the_policy(self):
        for path in modules():
            text = path.read_text(encoding="utf-8").lower()
            for word in ("bearer", "access_token", "id_token", "refresh_token", "client_assertion", "management.azure.com"):
                with self.subTest(file=path.name, word=word):
                    self.assertNotIn(word, text)
        found = sorted((path.name, address) for path in modules() for address in re.findall(r"https?://[^\s\"';)]+", path.read_text(encoding="utf-8")))
        self.assertEqual(found, [("layout.py", "https://login.microsoftonline.com")])

    def test_every_module_says_what_it_is_for(self):
        for path in modules():
            module = ast.parse(path.read_text(encoding="utf-8"))
            self.assertTrue(ast.get_docstring(module), path.name)

    def test_importing_it_loads_no_azure_module_and_opens_nothing(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import cases.web; "
                "print(sorted(n for n in sys.modules if n == 'azure' or n.startswith('azure.') or n in ('socket', 'ssl', 'subprocess', 'http.client', 'urllib.request')))")
        done = subprocess.run([sys.executable, "-c", code, str(APP_ROOT)], capture_output=True, text=True, check=True)
        self.assertEqual(done.stdout.strip(), "[]", "importing the pages loads no Azure library and nothing that opens a connection or a process")

    def test_handling_requests_opens_no_socket_and_starts_no_process(self):
        console = Console(decider="loop")
        console.seed()
        console.store.action_put(make_action())
        console.store.decision_put(make_decision())

        def refuse(*args, **kwargs):
            raise AssertionError("the console reached for the network or for a process")
        with mock.patch.object(socket, "socket", refuse), mock.patch.object(socket, "create_connection", refuse), mock.patch.object(subprocess, "Popen", refuse):
            for oid in (TINO, MAYA, OPS):
                for path in ("/", "/ok/plan0001", "/why/case0001", "/history", "/me/decisions", "/me/activity", "/me/settings", "/me/notes", "/ops", "/ops/runs", "/ops/permissions",
                             "/ops/pause", "/ops/two-people", "/arm/return?code=" + "c" * 24 + "&state=" + "s" * 24):
                    console.get(path, oid=oid)
            form = console.get("/me/settings").form("/me/settings/export")
            self.assertEqual(console.submit(form).status, 200)
            approve = console.get("/ok/plan0001").form("/ok/plan0001", has_button="Approve")
            self.assertEqual(console.submit(approve, "Approve").status, 303, "the page answers with a redirect and does not make the call itself")

    def test_the_routes_are_in_one_table_and_are_the_pages_of_the_design(self):
        from cases.web import router
        shown = {(method, re.sub(r"\(\?P<\w+>[^)]*\)", "<id>", pattern)) for method, pattern, _, _ in router.ROUTES}
        self.assertEqual(len(shown), len(router.ROUTES), "no route is listed twice")
        self.assertEqual(shown, {
            ("GET", "/"), ("GET", "/ok/<id>"), ("GET", "/ok/<id>/approve"), ("GET", "/ok/<id>/confirm"), ("GET", "/ok/<id>/decline"), ("POST", "/ok/<id>"), ("POST", "/ok/<id>/ask"),
            ("POST", "/ok/<id>/not-mine"), ("GET", "/arm/return"), ("GET", "/why/<id>"),
            ("GET", "/history"), ("GET", "/me/decisions"), ("GET", "/me/activity"), ("GET", "/me/settings"), ("POST", "/me/settings"), ("POST", "/me/settings/export"),
            ("POST", "/me/settings/delete"), ("GET", "/me/notes"), ("POST", "/me/notes"), ("POST", "/me/notes/<id>/delete"), ("GET", "/ops"), ("GET", "/ops/runs"),
            ("GET", "/ops/permissions"), ("GET", "/ops/pause"), ("POST", "/ops/pause"), ("GET", "/ops/two-people"), ("POST", "/ops/two-people"), ("POST", "/ops/drift"),
            ("POST", "/ops/answers")})
        self.assertNotIn(("POST", "/ok/<id>/withdraw"), shown, "an approval cannot be cancelled: the change is made right after the sign-in")
        self.assertEqual({method for method, *_ in router.ROUTES}, {"GET", "POST"}, "a page that shows something is a GET and a change is a POST")
        needs = {(method, re.sub(r"\(\?P<\w+>[^)]*\)", "<id>", pattern)): tuple(roles) for method, pattern, _, roles in router.ROUTES if roles}
        self.assertEqual(needs, {("GET", "/ops"): ("ops",), ("GET", "/ops/runs"): ("ops",), ("GET", "/ops/permissions"): ("ops", "owner"), ("GET", "/ops/pause"): ("ops",),
                                 ("POST", "/ops/pause"): ("ops",), ("GET", "/ops/two-people"): ("ops", "owner"), ("POST", "/ops/two-people"): ("owner",), ("POST", "/ops/drift"): ("ops",),
                                 ("POST", "/ops/answers"): ("ops",)})
        self.assertNotIn(("GET", "/arm/return"), needs, "any listed person may come back from the sign-in: the delegate checks that the sign-in was started by this person")


if __name__ == "__main__":
    unittest.main()
