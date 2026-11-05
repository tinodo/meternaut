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


class TemplateAndCode(unittest.TestCase):
    def test_the_template_sets_every_required_setting_and_no_setting_that_the_code_never_reads(self):
        template = (REPO_ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
        given = set(re.findall(r"\{ name: '([A-Za-z0-9_]+)', value: ", template))
        read = set(re.findall(r'^([A-Z][A-Z0-9_]+) = "\1"$', (REPO_ROOT / "src" / "case-functions" / "cases" / "config.py").read_text(encoding="utf-8"), re.M))
        # The settings of the loop are read by loop_config.py, the people by people.py, and the platform reads the one of its sign-in itself.
        read |= set(re.findall(r'^([A-Z][A-Z0-9_]+) = "\1"$', (REPO_ROOT / "src" / "case-functions" / "cases" / "loop_config.py").read_text(encoding="utf-8"), re.M))
        read |= {"CONSOLE_PEOPLE", "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"}
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
