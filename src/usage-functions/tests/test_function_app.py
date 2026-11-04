import ast
import re
import unittest

from support import APP_ROOT

from usage import jobs

try:
    import azure.functions as func
except ImportError:
    func = None

TIMED = ("llm-usage-ingestion", "mcp-usage-ingestion", "agent-usage-ingestion")
EVENT_HUBS = {
    "ai-usage-ingestion": ("%EVENTHUB_USAGE_NAME%", "aiUsageIngestion"),
    "pii-usage-ingestion": ("%EVENTHUB_PII_NAME%", "piiUsageIngestion"),
    "usage-control": ("%EVENTHUB_CONTROL_NAME%", "usageControl"),
}
SIX = set(TIMED) | set(EVENT_HUBS)
SCHEDULE = "0 0 3,6,9,12,15,18,21,23 * * *"


class FunctionAppSourceTests(unittest.TestCase):
    """Reads function_app.py as text, so it runs without azure-functions."""

    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse((APP_ROOT / "function_app.py").read_text(encoding="utf-8"))
        cls.functions = [node for node in cls.tree.body if isinstance(node, ast.FunctionDef)]

    @staticmethod
    def function_name(node: ast.FunctionDef) -> str:
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "function_name":
                return decorator.keywords[0].value.value
        raise AssertionError(f"{node.name} has no function_name decorator")

    def test_the_app_has_the_six_functions(self):
        self.assertEqual(sorted(self.function_name(node) for node in self.functions), sorted(SIX))

    def test_the_names_are_written_as_the_recording_check_reads_them(self):
        source = (APP_ROOT / "function_app.py").read_text(encoding="utf-8")
        self.assertEqual(sorted(re.findall(r'function_name\(name="([a-z-]+)"\)', source)), sorted(SIX))

    def test_the_names_of_the_timers_are_the_names_of_the_jobs(self):
        self.assertEqual(set(TIMED), set(jobs.JOBS))

    def test_only_azure_functions_typing_and_the_usage_package_are_imported(self):
        modules = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module)
        self.assertEqual(modules, {"typing", "azure.functions", "usage"})

    def test_every_function_is_one_call_into_the_usage_package(self):
        for node in self.functions:
            with self.subTest(function=node.name):
                (statement,) = node.body
                self.assertIsInstance(statement, ast.Expr)
                call = statement.value
                self.assertIsInstance(call, ast.Call)
                self.assertIn(call.func.value.id, {"jobs", "events", "control"})


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

    def test_the_app_has_exactly_the_six_functions(self):
        self.assertEqual(sorted(function.get_function_name() for function in self.list), sorted(SIX))

    def test_the_three_exports_are_timers_at_the_hours_of_the_kit_and_do_not_run_at_startup(self):
        for name in TIMED:
            with self.subTest(function=name):
                binding = self.binding(name)
                self.assertEqual(binding["type"], "timerTrigger")
                self.assertEqual(binding["schedule"], SCHEDULE)
                self.assertIs(binding["runOnStartup"], False)

    def test_the_three_event_hub_functions_read_batches_from_their_hub_and_consumer_group_through_the_identity_connection(self):
        for name, (hub, group) in EVENT_HUBS.items():
            with self.subTest(function=name):
                binding = self.binding(name)
                self.assertEqual(binding["type"], "eventHubTrigger")
                self.assertEqual(binding["eventHubName"], hub)
                self.assertEqual(binding["consumerGroup"], group)
                self.assertEqual(binding["cardinality"], "many")
                self.assertEqual(binding["connection"], "EventHubConnection")

    def test_the_parameter_of_a_trigger_is_named_in_the_binding(self):
        for name in self.functions:
            with self.subTest(function=name):
                parameters = self.functions[name].get_user_function().__code__.co_varnames[:1]
                self.assertEqual(parameters, (self.binding(name)["name"],))


if __name__ == "__main__":
    unittest.main()
