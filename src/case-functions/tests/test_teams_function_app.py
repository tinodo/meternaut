import ast
import re
import unittest

from support import APP_ROOT

try:
    import azure.functions as func
except ImportError:
    func = None

MESSAGES = "teams-messages"
OFFER = "teams-offer"
NAMES = sorted([MESSAGES, OFFER])
SCHEDULE = "0 * * * * *"
CASES_FUNCTIONS = ("watch-daily", "cases-control", "runner-tick", "console")


class EntrySourceTests(unittest.TestCase):
    """Reads teams_function_app.py as text, so it runs without azure-functions. The file is the entry of the Teams bot's own function app: the build puts it in place of function_app.py."""

    @classmethod
    def setUpClass(cls):
        cls.source = (APP_ROOT / "teams_function_app.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = [node for node in cls.tree.body if isinstance(node, ast.FunctionDef)]

    def test_the_app_has_the_two_functions_that_the_template_and_the_check_name(self):
        self.assertEqual(sorted(re.findall(r'function_name\(name="([a-z-]+)"\)', self.source)), NAMES)
        self.assertEqual(len(self.functions), 2)
        for name in CASES_FUNCTIONS:
            self.assertNotIn(f'"{name}"', self.source, f"{name} belongs to the cases app, which may stay private")

    def test_the_messaging_endpoint_is_the_one_route_it_is_a_post_and_it_takes_no_key(self):
        self.assertIn('@app.route(route="api/messages", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)', self.source)
        self.assertEqual(self.source.count("@app.route("), 1)
        self.assertNotIn("{*route}", self.source, "no catch-all: the web page is not in this app")
        self.assertNotIn("AuthLevel.FUNCTION", self.source, "a function key is a secret")
        self.assertNotIn("AuthLevel.ADMIN", self.source)

    def test_the_offering_timer_runs_every_minute_and_not_at_startup(self):
        self.assertIn(f'OFFER_SCHEDULE = "{SCHEDULE}"', self.source)
        self.assertIn("schedule=OFFER_SCHEDULE, run_on_startup=False", self.source)
        self.assertEqual(self.source.count("@app.timer_trigger("), 1)

    def test_only_azure_functions_and_the_teams_module_of_the_cases_package_are_imported(self):
        modules, names = set(), set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module)
                names.update(alias.name for alias in node.names)
        self.assertEqual(modules, {"azure.functions", "cases"})
        self.assertEqual(names - {"azure.functions"}, {"teams"}, "nothing of the web page, the Watch or the loop's timers is imported by the public app's entry")

    def test_every_function_is_one_call_into_cases_teams(self):
        calls = {}
        for node in self.functions:
            with self.subTest(function=node.name):
                (statement,) = node.body
                self.assertIsInstance(statement, (ast.Expr, ast.Return))
                call = statement.value
                self.assertIsInstance(call, ast.Call)
                self.assertEqual(call.func.value.id, "teams")
                calls[node.name] = (call.func.attr, [ast.unparse(a) for a in call.args])
        self.assertEqual(calls, {"teams_messages": ("handle", ["req", "func.HttpResponse"]), "teams_offer": ("tick", [])})


@unittest.skipIf(func is None, "azure-functions is not installed here; the CI runner installs it and indexes the app")
class EntryIndexingTests(unittest.TestCase):
    """Indexes the app with the real azure.functions, as the Functions host does."""

    @classmethod
    def setUpClass(cls):
        import teams_function_app

        # get_functions() builds the functions on every call and refuses a second call, so it is called once.
        cls.list = teams_function_app.app.get_functions()
        cls.functions = {function.get_function_name(): function for function in cls.list}

    def bindings(self, name: str) -> list[dict]:
        function = self.functions[name]
        found = function.get_bindings_dict()["bindings"] if hasattr(function, "get_bindings_dict") else [b.get_dict_repr() for b in function.get_bindings()]
        return [{key: getattr(value, "value", value) for key, value in binding.items()} for binding in found]

    def test_the_app_has_exactly_the_two_functions(self):
        self.assertEqual(sorted(function.get_function_name() for function in self.list), NAMES)

    def test_the_messaging_endpoint_is_an_anonymous_post_on_the_route_api_messages(self):
        trigger, output = self.bindings(MESSAGES)
        self.assertEqual((trigger["type"], str(trigger["authLevel"]).lower(), trigger["route"]), ("httpTrigger", "anonymous", "api/messages"))
        self.assertEqual([str(method).upper() for method in trigger["methods"]], ["POST"])
        self.assertEqual(output["type"], "http", "the trigger's output is the response")

    def test_the_offering_timer_is_a_timer_every_minute_that_does_not_run_at_startup(self):
        (binding,) = self.bindings(OFFER)
        self.assertEqual((binding["type"], binding["schedule"], binding["runOnStartup"]), ("timerTrigger", SCHEDULE, False))

    def test_the_parameter_of_a_trigger_is_named_in_the_binding(self):
        for name in self.functions:
            with self.subTest(function=name):
                parameters = self.functions[name].get_user_function().__code__.co_varnames[:1]
                self.assertEqual(parameters, (self.bindings(name)[0]["name"],))


if __name__ == "__main__":
    unittest.main()
