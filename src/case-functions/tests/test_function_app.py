import ast
import re
import unittest

from support import APP_ROOT, REPO_ROOT

try:
    import azure.functions as func
except ImportError:
    func = None

TIMER = "watch-daily"
DRIFT = "drift-daily"
CONTROL = "cases-control"
TICK = "runner-tick"
CONSOLE = "console"
SCHEDULE = "0 30 5 * * *"
DRIFT_SCHEDULE = "0 10 5 * * *"
TICK_SCHEDULE = "0 * * * * *"
NAMES = sorted([TIMER, DRIFT, CONTROL, TICK, CONSOLE])


class FunctionAppSourceTests(unittest.TestCase):
    """Reads function_app.py as text, so it runs without azure-functions."""

    @classmethod
    def setUpClass(cls):
        cls.source = (APP_ROOT / "function_app.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = [node for node in cls.tree.body if isinstance(node, ast.FunctionDef)]

    def test_the_app_has_the_five_functions_that_the_checker_and_the_template_name(self):
        self.assertEqual(sorted(re.findall(r'function_name\(name="([a-z-]+)"\)', self.source)), NAMES)
        self.assertEqual(len(self.functions), 5)

    def test_the_timer_runs_daily_at_half_past_five_utc_and_not_at_startup(self):
        self.assertIn(f'TIMER_SCHEDULE = "{SCHEDULE}"', self.source)
        self.assertIn("schedule=TIMER_SCHEDULE, run_on_startup=False", self.source)

    def test_the_drift_check_runs_daily_at_ten_past_five_utc_twenty_minutes_before_the_watch_and_not_at_startup(self):
        self.assertIn(f'DRIFT_SCHEDULE = "{DRIFT_SCHEDULE}"', self.source)
        self.assertIn("schedule=DRIFT_SCHEDULE, run_on_startup=False", self.source)
        self.assertEqual((SCHEDULE.split()[2], DRIFT_SCHEDULE.split()[2], int(SCHEDULE.split()[1]) - int(DRIFT_SCHEDULE.split()[1])), ("5", "5", 20))

    def test_the_app_says_which_package_runs_when_it_starts_and_that_is_the_one_call_outside_a_function(self):
        self.assertIn("harness.announce()", self.source)
        calls = [node for node in self.tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]
        self.assertEqual([ast.unparse(node.value) for node in calls], ["harness.announce()"])

    def test_the_tick_runs_every_minute_and_not_at_startup(self):
        self.assertIn(f'TICK_SCHEDULE = "{TICK_SCHEDULE}"', self.source)
        self.assertIn("schedule=TICK_SCHEDULE, run_on_startup=False", self.source)

    def test_the_console_is_one_catch_all_route_for_get_and_post_that_the_platform_sign_in_stands_in_front_of(self):
        self.assertIn('@app.route(route="{*route}", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)', self.source)
        self.assertNotIn("AuthLevel.FUNCTION", self.source, "a function key is a secret")
        self.assertNotIn("AuthLevel.ADMIN", self.source)
        self.assertEqual(self.source.count("@app.route("), 1)

    def test_the_control_function_reads_one_message_from_the_queue_that_the_template_makes_through_the_host_storage_connection(self):
        template = (REPO_ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn('queue_name="%CASES_CONTROL_QUEUE_NAME%"', self.source)
        self.assertIn('HOST_STORAGE_CONNECTION = "AzureWebJobsStorage"', self.source)
        self.assertIn("connection=HOST_STORAGE_CONNECTION", self.source)
        self.assertIn("func.QueueMessage", self.source)
        self.assertNotIn("event_hub", self.source.lower())
        self.assertIn("Microsoft.Storage/storageAccounts/queueServices/queues@", template)
        self.assertIn("{ name: 'CASES_CONTROL_QUEUE_NAME', value: controlQueueName }", template)
        for setting in ("AzureWebJobsStorage__credential", "AzureWebJobsStorage__queueServiceUri"):
            self.assertIn(f"{{ name: '{setting}'", template)
        self.assertNotIn("{ name: 'AzureWebJobsStorage',", template, "a connection string is a key: the host storage connection is the identity-based settings alone")

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
                self.assertIsInstance(statement, (ast.Expr, ast.Return))
                call = statement.value
                self.assertIsInstance(call, ast.Call)
                self.assertIn(call.func.value.id, {"run", "control", "loop", "console", "drift"})


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
        self.assertEqual(len(bindings), 1 if name != CONSOLE else 2, "a trigger and no other binding (the web trigger has its output)")
        return {key: getattr(value, "value", value) for key, value in bindings[0].items()}

    def test_the_app_has_exactly_the_five_functions(self):
        self.assertEqual(sorted(function.get_function_name() for function in self.list), NAMES)

    def test_the_timer_is_a_daily_timer_that_does_not_run_at_startup(self):
        binding = self.binding(TIMER)
        self.assertEqual((binding["type"], binding["schedule"], binding["runOnStartup"]), ("timerTrigger", SCHEDULE, False))

    def test_the_drift_check_is_a_daily_timer_that_does_not_run_at_startup(self):
        binding = self.binding(DRIFT)
        self.assertEqual((binding["type"], binding["schedule"], binding["runOnStartup"]), ("timerTrigger", DRIFT_SCHEDULE, False))

    def test_the_tick_is_a_timer_every_minute_that_does_not_run_at_startup(self):
        binding = self.binding(TICK)
        self.assertEqual((binding["type"], binding["schedule"], binding["runOnStartup"]), ("timerTrigger", TICK_SCHEDULE, False))

    def test_the_console_is_an_anonymous_catch_all_for_get_and_post(self):
        binding = self.binding(CONSOLE)
        self.assertEqual((binding["type"], str(binding["authLevel"]).lower(), binding["route"]), ("httpTrigger", "anonymous", "{*route}"))
        self.assertEqual(sorted(str(method).upper() for method in binding["methods"]), ["GET", "POST"])

    def test_the_control_function_reads_one_message_from_its_queue_through_the_host_storage_connection(self):
        binding = self.binding(CONTROL)
        self.assertEqual(binding["type"], "queueTrigger")
        self.assertEqual(binding["queueName"], "%CASES_CONTROL_QUEUE_NAME%")
        self.assertEqual(binding["connection"], "AzureWebJobsStorage")

    def test_the_parameter_of_a_trigger_is_named_in_the_binding(self):
        for name in self.functions:
            with self.subTest(function=name):
                parameters = self.functions[name].get_user_function().__code__.co_varnames[:1]
                self.assertEqual(parameters, (self.binding(name)["name"],))


if __name__ == "__main__":
    unittest.main()
