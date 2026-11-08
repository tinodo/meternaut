import dataclasses
import re
import unittest

from support import ENV, ENV_NO_PROJECT, FOUNDRY_ENDPOINT, GATEWAY_HOST, REPO_ROOT, SUBSCRIPTION
from cases import config


class Load(unittest.TestCase):
    def test_the_settings_of_the_template_are_read(self):
        settings = config.load(ENV)
        self.assertEqual(settings.subscriptions, (SUBSCRIPTION,))
        self.assertEqual(settings.foundry_endpoint, FOUNDRY_ENDPOINT, "the project of the agents: the investigation's agents and conversations are there")
        self.assertEqual(settings.ai_gateway_host, GATEWAY_HOST, "every model call of the Detective and the Skeptic goes to the AI Gateway")
        self.assertEqual((settings.model_detective, settings.model_skeptic), ("gpt-6-luna", "gpt-6.1-sol"))
        self.assertEqual((settings.max_cases, settings.max_tokens_per_run, settings.max_completion_tokens, settings.deadline_seconds), (3, 40000, 2000, 900))

    def test_the_app_reads_the_host_of_the_ai_gateway_and_no_setting_of_api_management_or_a_key_and_ignores_one_that_an_older_deploy_left(self):
        for name in ("GATEWAY_URL", "GATEWAY_PRODUCT_SUBSCRIPTION_ID", "GATEWAY", "PRODUCT_SUBSCRIPTION"):
            self.assertFalse(hasattr(config, name), name)
        fields = {f.name for f in dataclasses.fields(config.Settings)}
        for name in ("gateway_url", "gateway_host", "product_subscription_id", "api_key", "key"):
            self.assertNotIn(name, fields)
        self.assertIn("ai_gateway_host", fields)
        self.assertEqual([name for name in config.REQUIRED if "GATEWAY" in name], ["AIGATEWAY_HOST"], "the one setting about a gateway is the AI Gateway's host")
        left_over = {**ENV, "GATEWAY_URL": "https://example-apim.azure-api.net", "GATEWAY_PRODUCT_SUBSCRIPTION_ID": "/subscriptions/x"}
        self.assertEqual(config.load(left_over), config.load(ENV), "a setting that nothing reads is not an error")

    def test_a_trailing_slash_and_upper_case_ids_are_normalised(self):
        settings = config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": FOUNDRY_ENDPOINT + "/", "SCOPE_SUBSCRIPTIONS": f" {SUBSCRIPTION.upper()} , {SUBSCRIPTION[:-1]}6 "})
        self.assertEqual(settings.foundry_endpoint, FOUNDRY_ENDPOINT)
        self.assertEqual(settings.subscriptions, (SUBSCRIPTION, SUBSCRIPTION[:-1] + "6"))

    def test_every_missing_setting_is_named(self):
        for name in config.REQUIRED:
            env = {k: v for k, v in ENV.items() if k != name}
            with self.assertRaises(config.ConfigError) as raised:
                config.load(env)
            self.assertIn(f"{name} is not set", str(raised.exception))

    def test_every_wrong_setting_is_named_at_once(self):
        env = {**ENV, "SCOPE_SUBSCRIPTIONS": "not-a-guid", "MODEL_DETECTIVE": "Bad Model", "MAX_CASES_PER_RUN": "many", "AZURE_CLIENT_ID": "x"}
        with self.assertRaises(config.ConfigError) as raised:
            config.load(env)
        text = str(raised.exception)
        for name in ("SCOPE_SUBSCRIPTIONS", "MODEL_DETECTIVE", "MAX_CASES_PER_RUN", "AZURE_CLIENT_ID"):
            self.assertIn(name, text)

    def test_without_the_address_of_the_foundry_project_the_app_still_starts_and_the_two_roles_still_judge_through_the_ai_gateway(self):
        settings = config.load(ENV_NO_PROJECT)
        self.assertIsNone(settings.foundry_endpoint)
        self.assertFalse(settings.investigate)
        self.assertEqual(settings.ai_gateway_host, GATEWAY_HOST)

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


class ClientId(unittest.TestCase):
    """AZURE_CLIENT_ID names a user-assigned identity. Without it the app runs as its own system-assigned identity."""

    CLIENT = ENV["AZURE_CLIENT_ID"]
    WITHOUT = {key: value for key, value in ENV.items() if key != "AZURE_CLIENT_ID"}

    def test_the_client_id_is_not_a_required_setting_and_the_other_five_are(self):
        self.assertNotIn("AZURE_CLIENT_ID", config.REQUIRED)
        self.assertEqual(config.REQUIRED, ("SCOPE_SUBSCRIPTIONS", "MODEL_DETECTIVE", "MODEL_SKEPTIC", "AIGATEWAY_HOST", "MAX_CASES_PER_RUN", "CASES_CONTROL_QUEUE_NAME"))
        self.assertEqual(config.AZURE_CLIENT_ID, "AZURE_CLIENT_ID", "the name stays: the app reads it when it is set")

    def test_without_a_client_id_the_app_runs_as_its_system_assigned_identity(self):
        for env in (self.WITHOUT, {**self.WITHOUT, "AZURE_CLIENT_ID": ""}, {**self.WITHOUT, "AZURE_CLIENT_ID": "   "}):
            self.assertEqual(config.load(env).client_id, "", env.get("AZURE_CLIENT_ID"))
        self.assertEqual(config.load(self.WITHOUT).subscriptions, (SUBSCRIPTION,), "everything else is read as before")

    def test_a_client_id_that_is_set_is_kept_and_has_to_be_one(self):
        self.assertEqual(config.load(ENV).client_id, self.CLIENT)
        self.assertEqual(config.load({**ENV, "AZURE_CLIENT_ID": f" {self.CLIENT.upper()} "}).client_id, self.CLIENT.upper())
        for value in ("x", "not-a-client-id", self.CLIENT[:-1], self.CLIENT + "0", "{" + self.CLIENT + "}"):
            with self.assertRaises(config.ConfigError, msg=value) as raised:
                config.load({**ENV, "AZURE_CLIENT_ID": value})
            self.assertEqual(str(raised.exception), "AZURE_CLIENT_ID is a client id")

    def test_the_wrong_client_id_is_named_with_the_other_problems_and_a_missing_one_is_not(self):
        with self.assertRaises(config.ConfigError) as raised:
            config.load({**self.WITHOUT, "MAX_CASES_PER_RUN": "many", "AZURE_CLIENT_ID": "x"})
        self.assertEqual(str(raised.exception).split("; "), ["AZURE_CLIENT_ID is a client id", "MAX_CASES_PER_RUN is not a whole number"])
        with self.assertRaises(config.ConfigError) as raised:
            config.load({key: value for key, value in self.WITHOUT.items() if key != "MODEL_SKEPTIC"})
        self.assertEqual(str(raised.exception), "MODEL_SKEPTIC is not set")


class Investigation(unittest.TestCase):
    """The optional settings of the investigation by agents in Microsoft Foundry."""

    ENDPOINT = "https://acct-example.services.ai.azure.com/api/projects/proj-example"

    def investigation(self, settings):
        return (settings.foundry_endpoint, settings.investigate, settings.foundry_model_investigator, settings.foundry_model_skeptic, settings.investigate_max_calls,
                settings.investigate_max_seconds)

    def test_without_the_endpoint_the_app_does_not_investigate_and_the_defaults_are_the_ones_that_were_fixed(self):
        self.assertEqual(self.investigation(config.load(ENV_NO_PROJECT)), (None, False, "gpt-5.5", "gpt-6.1-sol", 40, 420))
        self.assertEqual(self.investigation(config.load({**ENV, "FOUNDRY_PROJECT_ENDPOINT": "", "INVESTIGATE": ""})), (None, False, "gpt-5.5", "gpt-6.1-sol", 40, 420))
        self.assertEqual((config.OPTIONAL["FOUNDRY_MODEL_INVESTIGATOR"], config.OPTIONAL["FOUNDRY_MODEL_SKEPTIC"], config.OPTIONAL["INVESTIGATE_MAX_CALLS"],
                          config.OPTIONAL["INVESTIGATE_MAX_SECONDS"]), ("gpt-5.5", "gpt-6.1-sol", "40", "420"))
        for name in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_INVESTIGATOR", "FOUNDRY_MODEL_SKEPTIC", "INVESTIGATE", "INVESTIGATE_MAX_CALLS", "INVESTIGATE_MAX_SECONDS"):
            self.assertNotIn(name, config.REQUIRED)

    def test_the_endpoint_turns_the_investigation_on_unless_it_is_switched_off(self):
        self.assertEqual(self.investigation(config.load({**ENV_NO_PROJECT, "FOUNDRY_PROJECT_ENDPOINT": self.ENDPOINT})), (self.ENDPOINT, True, "gpt-5.5", "gpt-6.1-sol", 40, 420))
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
            config.load({**ENV_NO_PROJECT, "INVESTIGATE": "on"})
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
            for value in ("bad name", "-x", "x" * 65, "a\n", "é"):
                with self.assertRaises(config.ConfigError, msg=f"{name}={value}") as raised:
                    config.load({**ENV, name: value})
                self.assertEqual(str(raised.exception), f"{name} is a model name or <connection>/<model>")
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

    def test_a_model_may_be_named_by_a_connection_and_a_model_and_in_no_other_way_with_a_slash(self):
        # The agents reach the AI Gateway through a connection of the project: their model is `<connection>/<alias>` (docs/proposals/08-ai-gateway.md, step 2).
        settings = config.load({**ENV, "FOUNDRY_MODEL_INVESTIGATOR": "aigateway/gpt-6.1-sol", "FOUNDRY_MODEL_SKEPTIC": "aigateway/gpt-6-luna"})
        self.assertEqual((settings.foundry_model_investigator, settings.foundry_model_skeptic), ("aigateway/gpt-6.1-sol", "aigateway/gpt-6-luna"))
        for name in ("FOUNDRY_MODEL_INVESTIGATOR", "FOUNDRY_MODEL_SKEPTIC"):
            for value in ("a/b", "A_1.x-y/Z_2.q-r", "x" * 64 + "/" + "y" * 64):
                self.assertEqual(config.load({**ENV, name: value}).__dict__[name.lower()], value)
            for value in ("a/b/c", "/b", "a/", "/", "a//b", "a /b", "a/ b", "a/-b", "-a/b", "a/b\n", "a\n/b", "x" * 65 + "/b", "a/" + "y" * 65, "a\\b", "a/é", "é/b", "a:b/c", "a/b?x=1",
                          "a/b/", "a/.b", ".a/b", "a%2Fb", "a/b c"):
                with self.assertRaises(config.ConfigError, msg=f"{name}={value!r}") as raised:
                    config.load({**ENV, name: value})
                self.assertEqual(str(raised.exception), f"{name} is a model name or <connection>/<model>")

    def test_the_skeptic_differs_from_the_investigator_in_the_whole_name_whatever_the_case(self):
        for investigator, skeptic in (("aigateway/gpt-6-luna", "aigateway/gpt-6-luna"), ("aigateway/gpt-6-luna", "AIGateway/GPT-6-Luna")):
            with self.assertRaises(config.ConfigError, msg=f"{investigator} {skeptic}") as raised:
                config.load({**ENV, "FOUNDRY_MODEL_INVESTIGATOR": investigator, "FOUNDRY_MODEL_SKEPTIC": skeptic})
            self.assertEqual(str(raised.exception), "FOUNDRY_MODEL_INVESTIGATOR and FOUNDRY_MODEL_SKEPTIC are the same model, and the Skeptic has to be another model than the Investigator")
        # Two names are two models for this rule, also when they end in the same model: the route is part of the name.
        settings = config.load({**ENV, "FOUNDRY_MODEL_INVESTIGATOR": "aigateway/gpt-6-luna", "FOUNDRY_MODEL_SKEPTIC": "gpt-6-luna"})
        self.assertEqual((settings.foundry_model_investigator, settings.foundry_model_skeptic), ("aigateway/gpt-6-luna", "gpt-6-luna"))

    def test_a_model_that_is_the_default_of_the_other_is_the_same_model(self):
        with self.assertRaises(config.ConfigError) as raised:
            config.load({**ENV, "FOUNDRY_MODEL_SKEPTIC": "gpt-5.5"})
        self.assertIn("FOUNDRY_MODEL_SKEPTIC", str(raised.exception))
        with self.assertRaises(config.ConfigError):
            config.load({**ENV, "FOUNDRY_MODEL_INVESTIGATOR": "gpt-6.1-sol"})

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
        env = {**ENV, "MODEL_DETECTIVE": "Bad Model", "FOUNDRY_PROJECT_ENDPOINT": "https://evil.example/api/projects/p", "FOUNDRY_MODEL_SKEPTIC": "gpt-5.5",
               "INVESTIGATE": "maybe", "INVESTIGATE_MAX_CALLS": "99", "INVESTIGATE_MAX_SECONDS": "x", "MAX_CASES_PER_RUN": "many"}
        with self.assertRaises(config.ConfigError) as raised:
            config.load(env)
        self.assertEqual(str(raised.exception).split("; "), [
            "MODEL_DETECTIVE is a model name", "MAX_CASES_PER_RUN is not a whole number",
            "FOUNDRY_PROJECT_ENDPOINT is https://<account>.services.ai.azure.com/api/projects/<project>",
            "FOUNDRY_MODEL_INVESTIGATOR and FOUNDRY_MODEL_SKEPTIC are the same model, and the Skeptic has to be another model than the Investigator",
            "INVESTIGATE is on or off", "INVESTIGATE_MAX_CALLS is not between 1 and 40", "INVESTIGATE_MAX_SECONDS is not a whole number"])

    def test_settings_that_are_made_by_hand_without_the_new_fields_have_their_defaults(self):
        settings = config.Settings(client_id="c", subscriptions=("s",), model_detective="a", model_skeptic="b",
                                   max_cases=1, max_tokens_per_run=1000, max_completion_tokens=100, deadline_seconds=60)
        self.assertEqual(self.investigation(settings), (None, False, "gpt-5.5", "gpt-6.1-sol", 40, 420))


class ScopeSwitch(unittest.TestCase):
    """SCOPE_ALL_SUBSCRIPTIONS: the Watch reads every subscription that its own identity can read (the owner's order of 2026-11-07). Off or not set, only SCOPE_SUBSCRIPTIONS."""

    WITHOUT_LIST = {key: value for key, value in ENV.items() if key != "SCOPE_SUBSCRIPTIONS"}

    def test_the_switch_is_off_when_it_is_not_set_so_that_an_older_setting_file_reads_what_it_read(self):
        self.assertIs(config.load(ENV).all_subscriptions, False)
        self.assertIs(config.load({**ENV, "SCOPE_ALL_SUBSCRIPTIONS": ""}).all_subscriptions, False)
        self.assertEqual(config.SCOPE_ALL_SUBSCRIPTIONS, "SCOPE_ALL_SUBSCRIPTIONS")
        self.assertNotIn("SCOPE_ALL_SUBSCRIPTIONS", config.OPTIONAL, "the default is in the code, and the template always writes the setting")

    def test_the_values_that_the_other_switches_take_are_taken(self):
        for value in ("true", "True", " TRUE ", "on", "1", "yes"):
            self.assertIs(config.load({**ENV, "SCOPE_ALL_SUBSCRIPTIONS": value}).all_subscriptions, True, value)
        for value in ("false", "False", "off", "0", "no"):
            self.assertIs(config.load({**ENV, "SCOPE_ALL_SUBSCRIPTIONS": value}).all_subscriptions, False, value)

    def test_a_value_that_is_neither_is_named_and_does_not_turn_it_on(self):
        for value in ("maybe", "all", "2", "enabled"):
            with self.assertRaises(config.ConfigError, msg=value) as raised:
                config.load({**ENV, "SCOPE_ALL_SUBSCRIPTIONS": value})
            self.assertIn("SCOPE_ALL_SUBSCRIPTIONS is on or off", str(raised.exception))

    def test_with_the_switch_on_the_explicit_list_is_optional_and_is_kept_as_the_fallback(self):
        on = {**self.WITHOUT_LIST, "SCOPE_ALL_SUBSCRIPTIONS": "true"}
        settings = config.load(on)
        self.assertEqual((settings.all_subscriptions, settings.subscriptions), (True, ()))
        with_list = config.load({**on, "SCOPE_SUBSCRIPTIONS": f"{SUBSCRIPTION.upper()}"})
        self.assertEqual((with_list.all_subscriptions, with_list.subscriptions), (True, (SUBSCRIPTION,)))
        self.assertEqual(config.load({**ENV, "SCOPE_ALL_SUBSCRIPTIONS": "true"}).subscriptions, (SUBSCRIPTION,), "the template sets both")

    def test_with_the_switch_off_the_list_is_still_required_and_is_named_when_it_is_missing(self):
        for switch in ({}, {"SCOPE_ALL_SUBSCRIPTIONS": "false"}, {"SCOPE_ALL_SUBSCRIPTIONS": ""}):
            with self.assertRaises(config.ConfigError, msg=switch) as raised:
                config.load({**self.WITHOUT_LIST, **switch})
            self.assertIn("SCOPE_SUBSCRIPTIONS is not set", str(raised.exception))

    def test_a_list_that_is_given_is_checked_whatever_the_switch_says(self):
        for switch in ("true", "false"):
            with self.assertRaises(config.ConfigError, msg=switch) as raised:
                config.load({**ENV, "SCOPE_ALL_SUBSCRIPTIONS": switch, "SCOPE_SUBSCRIPTIONS": "not-a-guid"})
            self.assertIn("SCOPE_SUBSCRIPTIONS is a comma separated list of subscription ids", str(raised.exception))

    def test_the_other_settings_are_still_required_with_the_switch_on(self):
        for name in ("MODEL_DETECTIVE", "MODEL_SKEPTIC", "AIGATEWAY_HOST", "MAX_CASES_PER_RUN", "CASES_CONTROL_QUEUE_NAME"):
            env = {**self.WITHOUT_LIST, "SCOPE_ALL_SUBSCRIPTIONS": "true"}
            del env[name]
            with self.assertRaises(config.ConfigError, msg=name) as raised:
                config.load(env)
            self.assertIn(f"{name} is not set", str(raised.exception))

    def test_the_switch_raises_no_limit_that_the_owner_set(self):
        # The owner's standing limits (AGENTS.md rule 15 (g)) are ceilings that no setting raises, and a larger estate gets no larger budget.
        settings = config.load({**ENV, "SCOPE_ALL_SUBSCRIPTIONS": "true"})
        self.assertEqual((settings.max_cases, settings.max_tokens_per_run, settings.max_completion_tokens, settings.deadline_seconds), (3, 40000, 2000, 900))
        self.assertEqual((config.LIMIT_CASES, config.LIMIT_TOKENS_PER_RUN, config.LIMIT_COMPLETION_TOKENS, config.LIMIT_DEADLINE_SECONDS), (3, 40000, 2000, 900))
        self.assertEqual(settings.investigate_max_calls, config.DEFAULT_INVESTIGATE_CALLS)
        self.assertLessEqual(settings.investigate_max_calls, config.LIMIT_INVESTIGATE_CALLS)


class TheGateway(unittest.TestCase):
    """AIGATEWAY_HOST: the host of the AI Gateway, the one address of every model call (AGENTS.md rule 15 (c)). The Watch does not start without it."""

    def test_the_host_is_required_and_the_name_of_the_setting_is_the_one_of_the_template(self):
        self.assertEqual(config.AIGATEWAY_HOST, "AIGATEWAY_HOST")
        self.assertIn("AIGATEWAY_HOST", config.REQUIRED)
        self.assertNotIn("AIGATEWAY_HOST", config.OPTIONAL, "no default: the app never guesses a host that a token is sent to")
        for env in ({k: v for k, v in ENV.items() if k != "AIGATEWAY_HOST"}, {**ENV, "AIGATEWAY_HOST": ""}):
            with self.assertRaises(config.ConfigError) as raised:
                config.load(env)
            self.assertEqual(str(raised.exception), "AIGATEWAY_HOST is not set")

    def test_the_host_is_trimmed_and_lower_cased(self):
        for value in (GATEWAY_HOST, f"  {GATEWAY_HOST.upper()} ", f"{GATEWAY_HOST}\n"):
            self.assertEqual(config.load({**ENV, "AIGATEWAY_HOST": value}).ai_gateway_host, GATEWAY_HOST)

    def test_a_host_that_is_not_under_the_domain_of_the_service_is_refused_because_a_token_goes_to_it(self):
        for bad in ("evil.example.com", f"{GATEWAY_HOST}.evil.example.com", f"https://{GATEWAY_HOST}", f"{GATEWAY_HOST}/default", f"{GATEWAY_HOST}:443", f"user@{GATEWAY_HOST}",
                    ".ai.gateway.azure.com", "ai.gateway.azure.com", f"a b.{GATEWAY_HOST}", "x" * 250 + ".ai.gateway.azure.com", "-x.ai.gateway.azure.com", "x_y.ai.gateway.azure.com",
                    "example.azure-api.net", "example.services.ai.azure.com", "   "):
            with self.subTest(bad=bad[:40]):
                with self.assertRaises(config.ConfigError) as raised:
                    config.load({**ENV, "AIGATEWAY_HOST": bad})
                self.assertIn("AIGATEWAY_HOST is", str(raised.exception))
                for echoed in ("evil", "user@", "https://", "example.azure-api.net", "example.services", "xxxxxxxx"):
                    self.assertNotIn(echoed, str(raised.exception), "the value is not echoed")

    def test_a_host_that_is_wrong_is_named_with_the_other_problems_and_never_kept(self):
        with self.assertRaises(config.ConfigError) as raised:
            config.load({**ENV, "AIGATEWAY_HOST": "evil.example.com", "MAX_CASES_PER_RUN": "many"})
        self.assertEqual(str(raised.exception).split("; "), ["AIGATEWAY_HOST is the host name of the AI Gateway, under .ai.gateway.azure.com, without a scheme, a port or a path",
                                                              "MAX_CASES_PER_RUN is not a whole number"])


class TemplateAndCode(unittest.TestCase):
    def test_the_template_asks_for_the_host_of_the_gateway_with_no_default_and_gives_it_to_the_app(self):
        template = (REPO_ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
        self.assertRegex(template, r"@minLength\(22\)\s*\n@maxLength\(253\)\s*\nparam aiGatewayHost string\n", "a required string with the bounds of a host name, and no default")
        self.assertIn("{ name: 'AIGATEWAY_HOST', value: aiGatewayHost }", template)
    def test_the_template_asks_for_the_switch_as_a_bool_that_is_off_unless_the_parameter_files_say_so(self):
        template = (REPO_ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn("\nparam scopeAllSubscriptions bool = false\n", template)
        self.assertIn("{ name: 'SCOPE_ALL_SUBSCRIPTIONS', value: scopeAllSubscriptions ? 'true' : 'false' }", template)
        self.assertIn("{ name: 'SCOPE_SUBSCRIPTIONS', value: scopeSubscriptions }", template, "the explicit list is still given: it is the fallback")
        # the value that the template writes is one that the code reads as on, and the other as off
        self.assertIs(config.load({**ENV, "SCOPE_ALL_SUBSCRIPTIONS": "true"}).all_subscriptions, True)
        self.assertIs(config.load({**ENV, "SCOPE_ALL_SUBSCRIPTIONS": "false"}).all_subscriptions, False)

    def test_the_template_sets_every_required_setting_and_no_setting_that_the_code_never_reads(self):
        template = (REPO_ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8")
        given = set(re.findall(r"\{ name: '([A-Za-z0-9_]+)', value: ", template))
        read = set(re.findall(r'^([A-Z][A-Z0-9_]+) = "\1"$', (REPO_ROOT / "src" / "case-functions" / "cases" / "config.py").read_text(encoding="utf-8"), re.M))
        # The settings of the loop are read by loop_config.py, the people by people.py, and the platform reads the ones of its sign-in and of its own hosting itself
        # (the Functions host's version and language, and how the Basic plan runs and builds the code).
        read |= set(re.findall(r'^([A-Z][A-Z0-9_]+) = "\1"$', (REPO_ROOT / "src" / "case-functions" / "cases" / "loop_config.py").read_text(encoding="utf-8"), re.M))
        read |= {"CONSOLE_PEOPLE", "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID", "BUILD_COMMIT", "PACKAGE_SHA256"}  # the last two (the release) are read by harness.py and drift_rules.py
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
