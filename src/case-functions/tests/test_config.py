import re
import unittest

from support import ENV, REPO_ROOT, SUBSCRIPTION
from cases import config


class Load(unittest.TestCase):
    def test_the_settings_of_the_template_are_read(self):
        settings = config.load(ENV)
        self.assertEqual(settings.subscriptions, (SUBSCRIPTION,))
        self.assertEqual(settings.gateway_url, "https://example-apim.azure-api.net")
        self.assertEqual(settings.gateway_host, "example-apim.azure-api.net")
        self.assertEqual((settings.model_detective, settings.model_skeptic), ("gpt-6-luna", "gpt-6.1-sol"))
        self.assertEqual((settings.max_cases, settings.max_tokens_per_run, settings.max_completion_tokens, settings.deadline_seconds), (3, 40000, 2000, 900))

    def test_a_trailing_slash_and_upper_case_ids_are_normalised(self):
        settings = config.load({**ENV, "GATEWAY_URL": "https://example-apim.azure-api.net/", "SCOPE_SUBSCRIPTIONS": f" {SUBSCRIPTION.upper()} , {SUBSCRIPTION[:-1]}6 "})
        self.assertEqual(settings.gateway_url, "https://example-apim.azure-api.net")
        self.assertEqual(settings.subscriptions, (SUBSCRIPTION, SUBSCRIPTION[:-1] + "6"))

    def test_every_missing_setting_is_named(self):
        for name in config.REQUIRED:
            env = {k: v for k, v in ENV.items() if k != name}
            with self.assertRaises(config.ConfigError) as raised:
                config.load(env)
            self.assertIn(f"{name} is not set", str(raised.exception))

    def test_every_wrong_setting_is_named_at_once(self):
        env = {**ENV, "GATEWAY_URL": "http://example.com", "SCOPE_SUBSCRIPTIONS": "not-a-guid", "MODEL_DETECTIVE": "Bad Model", "MAX_CASES_PER_RUN": "many",
               "GATEWAY_PRODUCT_SUBSCRIPTION_ID": "/subscriptions/x", "AZURE_CLIENT_ID": "x"}
        with self.assertRaises(config.ConfigError) as raised:
            config.load(env)
        text = str(raised.exception)
        for name in ("GATEWAY_URL", "SCOPE_SUBSCRIPTIONS", "MODEL_DETECTIVE", "MAX_CASES_PER_RUN", "GATEWAY_PRODUCT_SUBSCRIPTION_ID", "AZURE_CLIENT_ID"):
            self.assertIn(name, text)

    def test_the_gateway_must_be_an_api_management_address_and_nothing_else(self):
        for url in ("https://example.com", "https://evil.azure-api.net.example.com", "https://example-apim.azure-api.net/path", "https://user@example-apim.azure-api.net",
                    "https://-x.azure-api.net"):
            with self.assertRaises(config.ConfigError, msg=url):
                config.load({**ENV, "GATEWAY_URL": url})

    def test_limits_are_bounded(self):
        for name, value in (("MAX_CASES_PER_RUN", "0"), ("MAX_CASES_PER_RUN", "11"), ("MAX_TOKENS_PER_RUN", "10"), ("MAX_TOKENS_PER_RUN", "10000000"),
                            ("MAX_COMPLETION_TOKENS", "5"), ("RUN_DEADLINE_SECONDS", "5")):
            with self.assertRaises(config.ConfigError, msg=f"{name}={value}"):
                config.load({**ENV, name: value})

    def test_the_limits_of_the_proposal_are_ceilings_that_a_setting_can_lower_and_never_raise(self):
        for name, value in (("MAX_CASES_PER_RUN", "4"), ("MAX_TOKENS_PER_RUN", "40001"), ("MAX_COMPLETION_TOKENS", "2001"), ("RUN_DEADLINE_SECONDS", "901")):
            with self.assertRaises(config.ConfigError, msg=f"{name}={value}") as raised:
                config.load({**ENV, name: value})
            self.assertIn(name, str(raised.exception))
        for name, value in (("MAX_CASES_PER_RUN", "3"), ("MAX_TOKENS_PER_RUN", "40000"), ("MAX_COMPLETION_TOKENS", "2000"), ("RUN_DEADLINE_SECONDS", "900")):
            config.load({**ENV, name: value})

    def test_the_skeptic_has_to_be_another_model_than_the_detective(self):
        with self.assertRaises(config.ConfigError) as raised:
            config.load({**ENV, "MODEL_SKEPTIC": ENV["MODEL_DETECTIVE"]})
        self.assertIn("MODEL_SKEPTIC", str(raised.exception))
        self.assertEqual(config.load({**ENV, "MODEL_SKEPTIC": "gpt-6-sol"}).model_skeptic, "gpt-6-sol")

    def test_the_optional_settings_can_be_given(self):
        settings = config.load({**ENV, "MAX_TOKENS_PER_RUN": "20000", "MAX_COMPLETION_TOKENS": "1500", "RUN_DEADLINE_SECONDS": "600"})
        self.assertEqual((settings.max_tokens_per_run, settings.max_completion_tokens, settings.deadline_seconds), (20000, 1500, 600))


class Investigation(unittest.TestCase):
    """The optional settings of the investigation by agents in Microsoft Foundry."""

    ENDPOINT = "https://acct-example.services.ai.azure.com/api/projects/proj-example"

    def investigation(self, settings):
        return (settings.foundry_endpoint, settings.investigate, settings.foundry_model_investigator, settings.foundry_model_skeptic, settings.investigate_max_calls,
                settings.investigate_max_seconds)

    def test_without_the_endpoint_the_app_does_not_investigate_and_the_defaults_are_the_ones_that_were_fixed(self):
        self.assertEqual(self.investigation(config.load(ENV)), (None, False, "gpt-6.1-sol", "gpt-6-luna", 40, 420))
        self.assertEqual(self.investigation(config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": "", "INVESTIGATE": ""})), (None, False, "gpt-6.1-sol", "gpt-6-luna", 40, 420))
        self.assertEqual((config.OPTIONAL["FOUNDRY_MODEL_INVESTIGATOR"], config.OPTIONAL["FOUNDRY_MODEL_SKEPTIC"], config.OPTIONAL["INVESTIGATE_MAX_CALLS"],
                          config.OPTIONAL["INVESTIGATE_MAX_SECONDS"]), ("gpt-6.1-sol", "gpt-6-luna", "40", "420"))
        for name in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_INVESTIGATOR", "FOUNDRY_MODEL_SKEPTIC", "INVESTIGATE", "INVESTIGATE_MAX_CALLS", "INVESTIGATE_MAX_SECONDS"):
            self.assertNotIn(name, config.REQUIRED)

    def test_the_endpoint_turns_the_investigation_on_unless_it_is_switched_off(self):
        self.assertEqual(self.investigation(config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": self.ENDPOINT})), (self.ENDPOINT, True, "gpt-6.1-sol", "gpt-6-luna", 40, 420))
        for value in ("off", "OFF", "0", "false", "False", "no", " off "):
            self.assertFalse(config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": self.ENDPOINT, "INVESTIGATE": value}).investigate, value)
        for value in ("on", "ON", "1", "true", "True", "yes", " on "):
            self.assertTrue(config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": self.ENDPOINT, "INVESTIGATE": value}).investigate, value)
        self.assertFalse(config.load({**ENV, "INVESTIGATE": "off"}).investigate)

    def test_a_switch_that_is_neither_on_nor_off_is_named(self):
        for value in ("maybe", "2", "enabled", "tru"):
            with self.assertRaises(config.ConfigError, msg=value) as raised:
                config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": self.ENDPOINT, "INVESTIGATE": value})
            self.assertEqual(str(raised.exception), "INVESTIGATE is on or off")

    def test_the_investigation_cannot_be_on_without_an_endpoint(self):
        with self.assertRaises(config.ConfigError) as raised:
            config.load({**ENV, "INVESTIGATE": "on"})
        self.assertEqual(str(raised.exception), "INVESTIGATE is on and FOUNDRY_PROJECT_ENDPOINT is not set")

    def test_the_endpoint_has_to_be_the_endpoint_of_a_project_and_a_slash_at_the_end_is_taken_off(self):
        self.assertEqual(config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": self.ENDPOINT + "/"}).foundry_endpoint, self.ENDPOINT)
        self.assertEqual(config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": "https://a1.services.ai.azure.com/api/projects/_project"}).foundry_endpoint,
                         "https://a1.services.ai.azure.com/api/projects/_project")
        self.assertEqual(config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": "https://a1.services.ai.azure.com/api/projects/proj.v2/"}).foundry_endpoint,
                         "https://a1.services.ai.azure.com/api/projects/proj.v2", "a project name may hold dots, as the name of a resource does")
        for value in ("http://acct-example.services.ai.azure.com/api/projects/p", "https://acct-example.services.ai.azure.com", "https://acct-example.services.ai.azure.com/api/projects/",
                      "https://acct-example.services.ai.azure.com/api/projects/.", "https://acct-example.services.ai.azure.com/api/projects/..",
                      "https://acct-example.services.ai.azure.com/api/projects/.p", "https://acct-example.services.ai.azure.com/api/projects/p/..",
                      "https://acct-example.services.ai.azure.com/api/projects/p/agents", "https://acct-example.services.ai.azure.com/api/projects/p//", "https://evil.example/api/projects/p",
                      "https://acct-example.services.ai.azure.com.evil.example/api/projects/p", "https://user@acct-example.services.ai.azure.com/api/projects/p",
                      "https://ACCT.services.ai.azure.com/api/projects/p", "https://acct-example.openai.azure.com/api/projects/p", "https://acct-example.services.ai.azure.com/api/projects/p?x=1",
                      "https://acct-example-services-ai-azure-com/api/projects/p",
                      "acct-example.services.ai.azure.com/api/projects/p", " " + self.ENDPOINT):
            with self.assertRaises(config.ConfigError, msg=value) as raised:
                config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": value})
            self.assertEqual(str(raised.exception), "FOUNDRY_PROJECT_ENDPOINT is https://<account>.services.ai.azure.com/api/projects/<project>")

    def test_the_two_models_are_deployment_names_and_have_to_be_two_models(self):
        settings = config.load({**ENV, "FOUNDRY_MODEL_INVESTIGATOR": "Deploy_1.a-b", "FOUNDRY_MODEL_SKEPTIC": "gpt-6-sol"})
        self.assertEqual((settings.foundry_model_investigator, settings.foundry_model_skeptic), ("Deploy_1.a-b", "gpt-6-sol"))
        for name in ("FOUNDRY_MODEL_INVESTIGATOR", "FOUNDRY_MODEL_SKEPTIC"):
            for value in ("bad name", "-x", "a/b", "x" * 65, "a\n", "é"):
                with self.assertRaises(config.ConfigError, msg=f"{name}={value}") as raised:
                    config.load({**ENV, name: value})
                self.assertEqual(str(raised.exception), f"{name} is a model name")
            self.assertEqual(config.load({**ENV, name: "x" * 64}).__dict__[name.lower()], "x" * 64)
        for investigator, skeptic in (("gpt-6-luna", "gpt-6-luna"), ("gpt-6-luna", "GPT-6-Luna"), ("gpt-6.1-sol", None)):
            env = {**ENV, "FOUNDRY_MODEL_INVESTIGATOR": investigator}
            if skeptic:
                env["FOUNDRY_MODEL_SKEPTIC"] = skeptic
            else:
                env["FOUNDRY_MODEL_SKEPTIC"] = "gpt-6.1-sol"
            with self.assertRaises(config.ConfigError, msg=f"{investigator} {skeptic}") as raised:
                config.load(env)
            self.assertEqual(str(raised.exception), "FOUNDRY_MODEL_INVESTIGATOR and FOUNDRY_MODEL_SKEPTIC are the same model, and the Skeptic has to be another model than the Investigator")

    def test_a_model_that_is_the_default_of_the_other_is_the_same_model(self):
        with self.assertRaises(config.ConfigError) as raised:
            config.load({**ENV, "FOUNDRY_MODEL_SKEPTIC": "gpt-6.1-sol"})
        self.assertIn("FOUNDRY_MODEL_SKEPTIC", str(raised.exception))
        with self.assertRaises(config.ConfigError):
            config.load({**ENV, "FOUNDRY_MODEL_INVESTIGATOR": "gpt-6-luna"})

    def test_the_limits_of_the_investigation_are_ceilings_that_a_setting_can_lower_and_never_raise(self):
        settings = config.load({**ENV, "INVESTIGATE_MAX_CALLS": "40", "INVESTIGATE_MAX_SECONDS": "600"})
        self.assertEqual((settings.investigate_max_calls, settings.investigate_max_seconds), (40, 600))
        settings = config.load({**ENV, "INVESTIGATE_MAX_CALLS": "1", "INVESTIGATE_MAX_SECONDS": "30"})
        self.assertEqual((settings.investigate_max_calls, settings.investigate_max_seconds), (1, 30))
        for name, value, low, high in (("INVESTIGATE_MAX_CALLS", "0", 1, 40), ("INVESTIGATE_MAX_CALLS", "41", 1, 40), ("INVESTIGATE_MAX_CALLS", "-3", 1, 40),
                                       ("INVESTIGATE_MAX_SECONDS", "29", 30, 600), ("INVESTIGATE_MAX_SECONDS", "601", 30, 600), ("INVESTIGATE_MAX_SECONDS", "100000", 30, 600)):
            with self.assertRaises(config.ConfigError, msg=f"{name}={value}") as raised:
                config.load({**ENV, name: value})
            self.assertEqual(str(raised.exception), f"{name} is not between {low} and {high}")
        for name in ("INVESTIGATE_MAX_CALLS", "INVESTIGATE_MAX_SECONDS"):
            with self.assertRaises(config.ConfigError) as raised:
                config.load({**ENV, name: "many"})
            self.assertEqual(str(raised.exception), f"{name} is not a whole number")
        self.assertEqual((config.LIMIT_INVESTIGATE_CALLS, config.LIMIT_INVESTIGATE_SECONDS), (40, 600))

    def test_the_default_budget_of_tool_calls_is_the_ceiling_and_a_setting_can_still_lower_it(self):
        self.assertEqual((config.DEFAULT_INVESTIGATE_CALLS, config.LIMIT_INVESTIGATE_CALLS), (40, 40))
        for env in (ENV, {**ENV, "INVESTIGATE_MAX_CALLS": ""}, {**ENV, "FOUNDRY_PROJECT_ENDPOINT": self.ENDPOINT}):
            self.assertEqual(config.load(env).investigate_max_calls, 40)
        self.assertEqual(config.load({**ENV, "INVESTIGATE_MAX_CALLS": "24"}).investigate_max_calls, 24)
        self.assertEqual(config.load({**ENV, "INVESTIGATE_MAX_CALLS": "24"}).investigate_max_seconds, 420, "the seconds are not touched")

    def test_every_problem_is_named_at_once_with_the_older_ones_and_their_texts_do_not_change(self):
        env = {**ENV, "GATEWAY_URL": "http://example.com", "FOUNDRY_PROJECT_ENDPOINT": "https://evil.example/api/projects/p", "FOUNDRY_MODEL_SKEPTIC": "gpt-6.1-sol",
               "INVESTIGATE": "maybe", "INVESTIGATE_MAX_CALLS": "99", "INVESTIGATE_MAX_SECONDS": "x", "MAX_CASES_PER_RUN": "many"}
        with self.assertRaises(config.ConfigError) as raised:
            config.load(env)
        self.assertEqual(str(raised.exception).split("; "), [
            "GATEWAY_URL is https://<name>.azure-api.net", "MAX_CASES_PER_RUN is not a whole number",
            "FOUNDRY_PROJECT_ENDPOINT is https://<account>.services.ai.azure.com/api/projects/<project>",
            "FOUNDRY_MODEL_INVESTIGATOR and FOUNDRY_MODEL_SKEPTIC are the same model, and the Skeptic has to be another model than the Investigator",
            "INVESTIGATE is on or off", "INVESTIGATE_MAX_CALLS is not between 1 and 40", "INVESTIGATE_MAX_SECONDS is not a whole number"])

    def test_settings_that_are_made_by_hand_without_the_new_fields_have_their_defaults(self):
        settings = config.Settings(client_id="c", subscriptions=("s",), gateway_url="u", gateway_host="h", product_subscription_id="p", model_detective="a", model_skeptic="b",
                                   max_cases=1, max_tokens_per_run=1000, max_completion_tokens=100, deadline_seconds=60)
        self.assertEqual(self.investigation(settings), (None, False, "gpt-6.1-sol", "gpt-6-luna", 40, 420))


class TemplateAndCode(unittest.TestCase):
    def test_the_template_sets_every_required_setting_and_no_setting_that_the_code_never_reads(self):
        template = (REPO_ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
        given = set(re.findall(r"\{ name: '([A-Za-z0-9_]+)', value: ", template))
        read = set(re.findall(r'^([A-Z][A-Z0-9_]+) = "\1"$', (REPO_ROOT / "src" / "case-functions" / "cases" / "config.py").read_text(encoding="utf-8"), re.M))
        # The settings of the loop are read by loop_config.py, the people by people.py, and the platform reads the ones of its sign-in and of its own hosting itself
        # (the Functions host's version and language, and how the Basic plan runs and builds the code).
        read |= set(re.findall(r'^([A-Z][A-Z0-9_]+) = "\1"$', (REPO_ROOT / "src" / "case-functions" / "cases" / "loop_config.py").read_text(encoding="utf-8"), re.M))
        read |= {"CONSOLE_PEOPLE", "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"}
        read |= {"FUNCTIONS_EXTENSION_VERSION", "FUNCTIONS_WORKER_RUNTIME", "WEBSITE_RUN_FROM_PACKAGE", "WEBSITES_CONTAINER_START_TIME_LIMIT", "SCM_DO_BUILD_DURING_DEPLOYMENT", "ENABLE_ORYX_BUILD"}
        self.assertIn('SETTING = "CONSOLE_PEOPLE"', (REPO_ROOT / "src" / "case-functions" / "cases" / "people.py").read_text(encoding="utf-8"))
        self.assertEqual(sorted(set(config.REQUIRED) - given), [], "the template does not set what the code requires")
        known = {name for name in given if name.isupper() and "__" not in name and not name.startswith("APPLICATIONINSIGHTS")}
        self.assertEqual(sorted(known - read), [], "the template sets a setting that the code never reads")

    def test_the_settings_that_the_environment_gives_are_the_ones_of_the_tests(self):
        self.assertTrue(set(config.REQUIRED) <= set(ENV))

    def test_the_template_cannot_ask_for_more_cases_than_the_code_accepts_and_names_two_different_models(self):
        template = (REPO_ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
        cases = re.search(r"@minValue\(1\)\s*\n@maxValue\((\d+)\)\s*\nparam maxCasesPerRun int = (\d+)", template)
        self.assertIsNotNone(cases, "maxCasesPerRun has a bounded range in the template")
        self.assertEqual((int(cases.group(1)), int(cases.group(2))), (config.LIMIT_CASES, config.LIMIT_CASES))
        models = dict(re.findall(r"^param (modelDetective|modelSkeptic) string = '([^']+)'$", template, re.M))
        self.assertEqual(sorted(models), ["modelDetective", "modelSkeptic"])
        self.assertNotEqual(models["modelDetective"], models["modelSkeptic"])
        for name in models.values():
            self.assertRegex(name, config.MODEL)


if __name__ == "__main__":
    unittest.main()
