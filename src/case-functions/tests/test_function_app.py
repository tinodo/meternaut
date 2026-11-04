import ast
import re
import unittest

from support import APP_ROOT, REPO_ROOT

try:
    import azure.functions as func
except ImportError:
    func = None

TIMER = "watch-daily"
CONTROL = "cases-control"
SCHEDULE = "0 30 5 * * *"


class FunctionAppSourceTests(unittest.TestCase):
    """Reads function_app.py as text, so it runs without azure-functions."""

    @classmethod
    def setUpClass(cls):
        cls.source = (APP_ROOT / "function_app.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = [node for node in cls.tree.body if isinstance(node, ast.FunctionDef)]

    def test_the_app_has_the_two_functions_that_the_checker_and_the_template_name(self):
        self.assertEqual(sorted(re.findall(r'function_name\(name="([a-z-]+)"\)', self.source)), sorted([TIMER, CONTROL]))
        self.assertEqual(len(self.functions), 2)

    def test_the_timer_runs_daily_at_half_past_five_utc_and_not_at_startup(self):
        self.assertIn(f'TIMER_SCHEDULE = "{SCHEDULE}"', self.source)
        self.assertIn("schedule=TIMER_SCHEDULE, run_on_startup=False", self.source)

    def test_the_control_function_reads_one_event_from_the_hub_that_the_template_makes_through_the_identity_connection(self):
        template = (REPO_ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn('event_hub_name="%EVENTHUB_CASES_CONTROL_NAME%"', self.source)
        self.assertIn('consumer_group="casesControl"', self.source)
        self.assertIn('cardinality="one"', self.source)
        self.assertIn('EVENT_HUB_CONNECTION = "EventHubConnection"', self.source)
        self.assertIn("name: 'casesControl'", template)
        self.assertIn("EventHubConnection__fullyQualifiedNamespace", template)

    def test_only_azure_functions_and_the_cases_package_are_imported(self):
        modules = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module)
        self.assertEqual(modules, {"azure.functions", "cases"})

    def test_every_function_is_one_call_into_the_cases_package(self):
        for node in self.functions:
            with self.subTest(function=node.name):
                (statement,) = node.body
                self.assertIsInstance(statement, ast.Expr)
                call = statement.value
                self.assertIsInstance(call, ast.Call)
                self.assertIn(call.func.value.id, {"run", "control"})


@unittest.skipIf(func is None, "azure-functions is not installed here; the CI runner installs it and indexes the app")
class FunctionAppIndexingTests(unittest.TestCase):
    """Indexes the app with the real azure.functions, as the Functions host does."""

    @classmethod
    def setUpClass(cls):
        import function_app

        # get_functions() builds the functions on every call and refuses a second call, so it is called once.
        cls.list = function_app.app.get_functions()
        cls.functions = {function.get_function_name(): function for function in cls.list}

    def binding(self, name: str) -> dict:
        function = self.functions[name]
        bindings = function.get_bindings_dict()["bindings"] if hasattr(function, "get_bindings_dict") else [b.get_dict_repr() for b in function.get_bindings()]
        self.assertEqual(len(bindings), 1, "a trigger and no other binding")
        return {key: getattr(value, "value", value) for key, value in bindings[0].items()}

    def test_the_app_has_exactly_the_two_functions(self):
        self.assertEqual(sorted(function.get_function_name() for function in self.list), sorted([TIMER, CONTROL]))

    def test_the_timer_is_a_daily_timer_that_does_not_run_at_startup(self):
        binding = self.binding(TIMER)
        self.assertEqual((binding["type"], binding["schedule"], binding["runOnStartup"]), ("timerTrigger", SCHEDULE, False))

    def test_the_control_function_reads_one_event_from_its_hub_and_consumer_group_through_the_identity_connection(self):
        binding = self.binding(CONTROL)
        self.assertEqual(binding["type"], "eventHubTrigger")
        self.assertEqual(binding["eventHubName"], "%EVENTHUB_CASES_CONTROL_NAME%")
        self.assertEqual(binding["consumerGroup"], "casesControl")
        self.assertEqual(binding["cardinality"], "one")
        self.assertEqual(binding["connection"], "EventHubConnection")

    def test_the_parameter_of_a_trigger_is_named_in_the_binding(self):
        for name in self.functions:
            with self.subTest(function=name):
                parameters = self.functions[name].get_user_function().__code__.co_varnames[:1]
                self.assertEqual(parameters, (self.binding(name)["name"],))


if __name__ == "__main__":
    unittest.main()
