import unittest
from unittest import mock

from support import ENV

from usage import config


class GetSettingsTests(unittest.TestCase):
    def test_the_values_of_the_named_settings(self):
        values = config.get_settings(("COSMOS_ENDPOINT", "COSMOS_DATABASE"), ENV)
        self.assertEqual(values, {"COSMOS_ENDPOINT": ENV["COSMOS_ENDPOINT"], "COSMOS_DATABASE": "usage-db"})

    def test_a_missing_setting_is_named(self):
        for name in ENV:
            with self.subTest(setting=name):
                env = {key: value for key, value in ENV.items() if key != name}
                with self.assertRaises(config.ConfigError) as caught:
                    config.get_settings(list(ENV), env)
                self.assertEqual(str(caught.exception), f"Missing required app setting(s): {name}")

    def test_an_empty_or_blank_setting_is_missing(self):
        for value in ("", "   ", None):
            with self.subTest(value=value), self.assertRaises(config.ConfigError) as caught:
                config.get_settings(("COSMOS_ENDPOINT",), {"COSMOS_ENDPOINT": value})
            self.assertIn("COSMOS_ENDPOINT", str(caught.exception))

    def test_every_missing_setting_is_named_in_one_error(self):
        with self.assertRaises(config.ConfigError) as caught:
            config.get_settings(("AZURE_CLIENT_ID", "COSMOS_ENDPOINT", "COSMOS_DATABASE"), {"COSMOS_DATABASE": "db"})
        self.assertEqual(str(caught.exception), "Missing required app setting(s): AZURE_CLIENT_ID, COSMOS_ENDPOINT")

    def test_the_message_holds_no_value(self):
        env = dict(ENV, COSMOS_ENDPOINT="")
        with self.assertRaises(config.ConfigError) as caught:
            config.get_settings(("COSMOS_ENDPOINT", "COSMOS_DATABASE", "AZURE_CLIENT_ID"), env)
        for value in ("usage-db", ENV["AZURE_CLIENT_ID"]):
            self.assertNotIn(value, str(caught.exception))

    def test_a_value_is_stripped(self):
        self.assertEqual(config.get_settings(("COSMOS_DATABASE",), {"COSMOS_DATABASE": " db \n"}), {"COSMOS_DATABASE": "db"})

    def test_the_environment_is_read_when_no_mapping_is_given(self):
        with mock.patch.dict("os.environ", {"COSMOS_DATABASE": "from-environment"}, clear=True):
            self.assertEqual(config.get_settings(("COSMOS_DATABASE",)), {"COSMOS_DATABASE": "from-environment"})
            with self.assertRaises(config.ConfigError):
                config.get_settings(("COSMOS_ENDPOINT",))

    def test_the_names_are_the_app_settings_of_the_function_app(self):
        names = {
            config.AZURE_CLIENT_ID, config.COSMOS_ENDPOINT, config.COSMOS_DATABASE, config.COSMOS_CONTAINER_CONFIG,
            config.COSMOS_CONTAINER_AI_USAGE, config.COSMOS_CONTAINER_PII_USAGE, config.COSMOS_CONTAINER_LLM_USAGE,
            config.COSMOS_CONTAINER_MCP_USAGE, config.COSMOS_CONTAINER_AGENT_USAGE, config.GATEWAY_APPINSIGHTS_ID,
        }
        self.assertEqual(names, set(ENV))


if __name__ == "__main__":
    unittest.main()
