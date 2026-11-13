"""The Azure side of the Teams bot (docs/proposals/20-teams-cards-through-a-bot.md): the template environment/teams/main.bicep, the settings that the cases template and the parameter builder carry, and the Hub
actions teams and teams-test of .github/workflows/deploy-hub.yml. What these tests pin: that the bot is off unless it is switched on and nothing else changes, that the identity holds no role and the bot is single
tenant with local authentication off, that no identifier of the estate is printed, that the steps run in the order that keeps the objects consistent, and that nothing writes but the one deployment. The scripts of the
steps are run with bash and stand-ins for the commands that they call: no test calls Azure, GitHub, Microsoft Entra or Teams."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(file_name, label):
    spec = importlib.util.spec_from_file_location(label, ROOT / file_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


ws = load("tools/tests/test_workflow_scripts.py", "workflow_scripts_of_the_teams_bot_hub_tests")
ep = load("tools/environment-params.py", "environment_params_of_the_teams_bot_hub_tests")
wl = load("tools/workflow-lint.py", "workflow_lint_of_the_teams_bot_hub_tests")


def read(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


WORKFLOW = ws.WORKFLOW
TEMPLATE = read("environment/teams/main.bicep")
CASES = read("environment/cases/main.bicep")
BASH = ws.BASH
SKIP_BASH = unittest.skipIf(BASH is None, "no bash on this machine")
AZ = shutil.which("az")
SKIP_AZ = unittest.skipIf(AZ is None, "no Azure CLI on this machine, which compiles the templates")

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-of-the-project"
CLIENT = "12345678-aaaa-bbbb-cccc-0123456789ab"
IDENTITY_CLIENT = "12345678-bbbb-cccc-dddd-0123456789ab"
PRINCIPAL = "5a1c0de0-0000-4000-8000-0000000000de"
HOST = "func-meternaut-cases-0123abcd.azurewebsites.net"
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

FACTS = "Find out which phase of the Teams identity and bot this run is, and read what phase 2 needs from Azure"
SETTINGS = "Work out the settings of the Teams identity and bot"
PREVIEW = "What the Teams identity and bot would change"
DEPLOY = "Deploy the Teams identity and bot"
LOGIN = "Sign in to Azure again for the read-back of the Teams identity and bot, because the first sign-in's credential lasts five minutes"
READ_BACK = "Read the Teams identity and bot back from Azure, and check that the identity holds no role"
HAND_STEPS = "The steps that a person does by hand for the Teams bot"
TEAMS_CHAIN = [FACTS, SETTINGS, PREVIEW, DEPLOY, LOGIN, READ_BACK, HAND_STEPS]
TEST = "Test the way out to Teams, and send one test card, from inside the network, in the Operator"
TEST_CLEANUP = "Delete any container group of the Teams test that is left"
TEST_CHAIN = [TEST, TEST_CLEANUP]
IDENTITY_STEP = "Read the Teams identity, which the cases app is given while it is there"


def blocks():
    return re.findall(r"(?ms)^      - name: (.+?)\n(.*?)(?=^      - |\Z)", WORKFLOW)


def step(name):
    (text,) = [body for title, body in blocks() if title == name]
    return text


def code_of(name):
    run = step(name).split("        run: |\n", 1)[1]
    return "\n".join(line for line in run.splitlines() if not line.lstrip().startswith("#"))


def code_lines(text):
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


BASE_ENV = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "GITHUB_RUN_ID": "12345", "ACTION": "teams", "FUNCTION_APP": "func-meternaut-cases-0123abcd"}


def run(name, stand_ins, **env):
    return ws.run_step_script(name, stand_ins, {**BASE_ENV, **env})


def said(done):
    return done.stdout + done.stderr


ENV = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": "rg-example", "ENV_LOCATION": "swedencentral", "ENV_VNET_PREFIX": "10.53.0.0/24", "ENV_PE_SUBNET_PREFIX": "10.53.0.0/27", "ENV_DNS_SERVERS": "10.20.0.4",
       "ENV_OWNER": "owner@example.com", "ENV_BUDGET_AMOUNT": "25", "ENV_ALERT_EMAILS": "owner@example.com", "ENV_BUDGET_START": "2026-11-01", "AIGATEWAY_HOST": "aigw-meternaut-0123abcd.swedencentral.ai.gateway.azure.com"}


def build(models=None, **extra):
    models = models or ep.read_models(ROOT / "environment" / "models.json")
    preview = extra.pop("preview", False)
    teams = extra.pop("teams", False)
    return ep.build({**ENV, **extra}, models, preview=preview, teams=teams)


class TheTemplateMakesTheIdentityAndTheBotAndNothingElse(unittest.TestCase):
    def test_the_identity_is_user_assigned_named_like_the_others_and_holds_no_role(self):
        code = code_lines(TEMPLATE)
        self.assertIn("resource teamsIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31'", code)
        self.assertIn("name: 'id-${workload}-teams'", code)
        self.assertEqual(ep.TEAMS_IDENTITY_NAME, "id-meternaut-teams")
        for forbidden in ("Microsoft.Authorization", "roleAssignments", "roleDefinition", "listKeys", "secret", "password", "certificate", "keyVault"):
            self.assertNotIn(forbidden.lower(), code.lower(), f"no role, no key and no secret: {forbidden}")
        self.assertIn("'meternaut-stage': 'teams-bot'", code)

    def test_the_bot_is_single_tenant_azurebot_on_the_free_sku_with_no_local_authentication_and_an_endpoint_that_nothing_calls(self):
        code = code_lines(TEMPLATE)
        for line in ("resource bot 'Microsoft.BotService/botServices@2022-09-15' = if (botIsWanted) {", "kind: 'azurebot'", "location: 'global'", "msaAppType: 'SingleTenant'", "msaAppId: botAppId",
                     "msaAppTenantId: tenant().tenantId", "disableLocalAuth: true", "endpoint: 'https://${functionAppHost}/api/messages'", "var botIsWanted = !empty(botAppId)",
                     "param botSku string = 'F0'", "displayName: 'Meternaut (AI)'"):
            self.assertIn(line, code, line)
        self.assertNotIn("UserAssignedMSI", code, "the legacy type")
        self.assertNotIn("MultiTenant", code, "the deprecated type")
        self.assertNotIn("msaAppMSIResourceId", code)
        self.assertIn("@allowed([\n  'F0'\n  'S1'\n])", TEMPLATE)

    def test_the_teams_channel_is_enabled_with_calling_off_and_is_a_child_of_the_bot(self):
        code = code_lines(TEMPLATE)
        channel = code.split("resource teamsChannel", 1)[1].split("output ", 1)[0]
        for line in ("'Microsoft.BotService/botServices/channels@2022-09-15' = if (botIsWanted)", "parent: bot", "name: 'MsTeamsChannel'", "channelName: 'MsTeamsChannel'", "isEnabled: true", "enableCalling: false"):
            self.assertIn(line, channel, line)
        self.assertEqual(code.count("Microsoft.BotService"), 2, "the bot and its channel are the only resources of the service")

    def test_phase_one_is_the_identity_alone_and_the_outputs_give_what_the_workflow_reads(self):
        code = code_lines(TEMPLATE)
        self.assertEqual(len(re.findall(r"(?m)^resource ", code)), 3)
        self.assertEqual(len(re.findall(r"= if \(botIsWanted\)", code)), 2, "only the identity is made without the client id")
        for output in ("identityName", "identityId", "identityPrincipalId", "identityClientId", "botName"):
            self.assertRegex(code, rf"(?m)^output {output} string = ")

    @SKIP_AZ
    def test_it_compiles_to_the_three_resources_and_the_two_conditions_and_the_parameter_files_fit_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([AZ, "bicep", "build", "--file", str(ROOT / "environment" / "teams" / "main.bicep"), "--outfile", str(Path(tmp) / "teams.json")], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            compiled = json.loads((Path(tmp) / "teams.json").read_text(encoding="utf-8"))
            resources = compiled["resources"]
            resources = list(resources.values()) if isinstance(resources, dict) else resources
            self.assertEqual(sorted(r["type"] for r in resources), ["Microsoft.BotService/botServices", "Microsoft.BotService/botServices/channels", "Microsoft.ManagedIdentity/userAssignedIdentities"])
            for phase, extra in (("1", {}), ("2", {"TEAMS_BOT_APP_ID": CLIENT, "TEAMS_FUNCTION_HOST": HOST})):
                files, _ = build(teams=True, **extra)
                self.assertEqual(ep.check_against(files["teams.parameters.json"], compiled, f"teams phase {phase}"), [])
            done = subprocess.run([AZ, "bicep", "build", "--file", str(ROOT / "environment" / "cases" / "main.bicep"), "--outfile", str(Path(tmp) / "cases.json")], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            cases = json.loads((Path(tmp) / "cases.json").read_text(encoding="utf-8"))
            files, _ = build(TEAMS_DELIVERY="bot", TEAMS_BOT_APP_ID=CLIENT, TEAMS_BOT_IDENTITY_CLIENT_ID=IDENTITY_CLIENT, ACTION="cases")
            self.assertEqual(ep.check_against(files["cases.parameters.json"], cases, "cases with the bot"), [])


class TheCasesTemplateGetsTheFourSettingsAndTheIdentityAndNothingMore(unittest.TestCase):
    def test_the_four_settings_have_the_names_of_the_contract_and_the_default_is_the_queue(self):
        code = code_lines(CASES)
        for setting in ("TEAMS_DELIVERY", "TEAMS_BOT_APP_ID", "TEAMS_BOT_IDENTITY_CLIENT_ID", "TEAMS_SERVICE_URL"):
            self.assertEqual(len(re.findall(rf"name: '{setting}'", code)), 1, setting)
        self.assertEqual(len(re.findall(r"name: 'TEAMS_", code)), 6, "the four new ones and the two queues of proposal 19")
        for line in ("param teamsDelivery string = 'queue'", "param teamsServiceUrl string = 'https://smba.trafficmanager.net/teams/'", "param teamsIdentityId string = ''", "param teamsIdentityClientId string = ''",
                     "param teamsBotAppId string = ''", "{ name: 'TEAMS_DELIVERY', value: teamsDelivery }", "{ name: 'TEAMS_SERVICE_URL', value: teamsServiceUrl }"):
            self.assertIn(line, code, line)
        self.assertIn("@allowed([\n  'queue'\n  'bot'\n])\nparam teamsDelivery", CASES)
        self.assertIn("@allowed([\n  'https://smba.trafficmanager.net/teams/'\n])\nparam teamsServiceUrl", CASES, "the one address that the app accepts (cases/loop_config.py DEFAULT_SERVICE_URL, tools/teams-check.py HOSTS)")

    def test_the_identity_is_attached_only_when_it_is_given_and_the_one_of_the_sign_in_stays(self):
        code = code_lines(CASES)
        self.assertIn("userAssignedIdentities: union({\n      '${authIdentity.id}': {}\n    }, empty(teamsIdentityId) ? {} : {\n      '${teamsIdentityId}': {}\n    })", code)
        self.assertIn("type: 'SystemAssigned, UserAssigned'", code)
        self.assertNotIn("id-${workload}-teams", code, "the cases template does not make the identity: the action teams does")

    def test_the_template_of_the_bot_gives_the_cases_app_no_role(self):
        self.assertEqual(len(re.findall(r"(?m)^resource .*roleAssignments", code_lines(TEMPLATE))), 0)
        self.assertEqual(code_lines(CASES).count("roleAssignments@"), code_lines(read("environment/cases/main.bicep")).count("roleAssignments@"))


class TheBuilderChangesNothingWhileTheBotIsOff(unittest.TestCase):
    def test_a_build_without_the_settings_writes_the_files_that_it_wrote_and_no_line_of_the_bot(self):
        files, outputs = build()
        self.assertNotIn("teams.parameters.json", files)
        self.assertFalse([key for key in outputs if key.startswith("teams_")])
        cases = files["cases.parameters.json"]["parameters"]
        self.assertFalse([name for name in cases if name.lower().startswith("teams")], "the template's defaults are the bot being off")

    def test_phase_one_makes_the_identity_alone_and_phase_two_the_bot_with_the_host_of_the_app(self):
        files, outputs = build(teams=True)
        values = {k: v["value"] for k, v in files["teams.parameters.json"]["parameters"].items()}
        self.assertEqual(sorted(values), ["botName", "botSku", "location", "owner"])
        self.assertEqual((outputs["teams_phase"], outputs["teams_identity_name"], outputs["teams_bot_sku"], outputs["teams_delivery"]), ("1", "id-meternaut-teams", "F0", "queue"))
        self.assertRegex(outputs["teams_bot_name"], r"^bot-meternaut-[0-9a-f]{8}$")
        self.assertEqual(values["botName"], outputs["teams_bot_name"])
        files, outputs = build(teams=True, TEAMS_BOT_APP_ID=CLIENT.upper(), TEAMS_FUNCTION_HOST=HOST.upper())
        values = {k: v["value"] for k, v in files["teams.parameters.json"]["parameters"].items()}
        self.assertEqual((values["botAppId"], values["functionAppHost"], outputs["teams_phase"]), (CLIENT, HOST, "2"))

    def test_phase_two_needs_the_host_unless_it_is_a_preview(self):
        with self.assertRaises(ep.Problem) as raised:
            build(teams=True, TEAMS_BOT_APP_ID=CLIENT)
        self.assertIn("TEAMS_FUNCTION_HOST is not set", str(raised.exception))
        files, _ = build(teams=True, preview=True, TEAMS_BOT_APP_ID=CLIENT)
        self.assertEqual(files["teams.parameters.json"]["parameters"]["functionAppHost"]["value"], "placeholder.azurewebsites.net")

    def test_the_cases_file_carries_what_is_set_the_identity_in_the_projects_own_group_and_the_delivery_only_when_it_is_not_the_queue(self):
        files, _ = build(TEAMS_BOT_IDENTITY_CLIENT_ID=IDENTITY_CLIENT, TEAMS_BOT_APP_ID=CLIENT)
        cases = {k: v["value"] for k, v in files["cases.parameters.json"]["parameters"].items()}
        self.assertEqual(cases["teamsIdentityId"], f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-example/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-teams")
        self.assertEqual((cases["teamsIdentityClientId"], cases["teamsBotAppId"]), (IDENTITY_CLIENT, CLIENT))
        self.assertNotIn("teamsDelivery", cases, "queue is the template's default")
        files, _ = build(TEAMS_DELIVERY="bot", TEAMS_BOT_IDENTITY_CLIENT_ID=IDENTITY_CLIENT, TEAMS_BOT_APP_ID=CLIENT)
        self.assertEqual(files["cases.parameters.json"]["parameters"]["teamsDelivery"]["value"], "bot")

    def test_only_the_action_cases_refuses_bot_without_the_bot_and_a_preview_never_does(self):
        with self.assertRaises(ep.Problem) as raised:
            build(TEAMS_DELIVERY="bot", ACTION="cases")
        self.assertIn("TEAMS_DELIVERY is bot, and the bot is not set up", str(raised.exception))
        with self.assertRaises(ep.Problem):
            build(TEAMS_DELIVERY="bot", ACTION="cases", TEAMS_BOT_APP_ID=CLIENT)
        for action in ("teams", "base", "foundry", "what-if", "teams-test", ""):
            build(TEAMS_DELIVERY="bot", ACTION=action)
        build(TEAMS_DELIVERY="bot", ACTION="cases", preview=True)
        build(TEAMS_DELIVERY="bot", ACTION="cases", TEAMS_BOT_APP_ID=CLIENT, TEAMS_BOT_IDENTITY_CLIENT_ID=IDENTITY_CLIENT)

    def test_every_setting_is_checked_and_never_echoed(self):
        for name, value in (("TEAMS_DELIVERY", "e-mail"), ("TEAMS_BOT_APP_ID", "not-a-guid"), ("TEAMS_BOT_IDENTITY_CLIENT_ID", "not-a-guid"), ("TEAMS_FUNCTION_HOST", "example.com"), ("TEAMS_FUNCTION_HOST", "https://x.azurewebsites.net")):
            with self.assertRaises(ep.Problem, msg=name) as raised:
                build(**{name: value})
            self.assertNotIn(value + " ", str(raised.exception).replace(f"{value!r}", ""), name)
        self.assertEqual(build(TEAMS_DELIVERY=" Bot ")[0]["cases.parameters.json"]["parameters"]["teamsDelivery"]["value"], "bot")

    def test_the_command_line_and_the_ci_check_the_new_file_too(self):
        source = read("tools/environment-params.py")
        self.assertIn('--teams", action="store_true"', source)
        ci = read(".github/workflows/checks.yml")
        for text in ("environment/teams/main.bicep", "--teams --governance", "--label teams", "TEAMS_BOT_APP_ID: 12345678"):
            self.assertIn(text, ci, text)
        self.assertEqual(ci.count("environment/teams/main.bicep"), 3, "compiled and linted in the step of the templates (two lines), and compiled for the parameter check")


class TheActionsAreOfferedAndTheEnvironmentHoldsTheTwoSettings(unittest.TestCase):
    def test_the_two_actions_are_offered_after_cases_run_and_the_pins_of_the_other_options_still_hold(self):
        options = re.findall(r"(?m)^          - (\S+)$", re.search(r"(?ms)^      action:\n(.*?)^      \w", WORKFLOW).group(1))
        self.assertEqual(options[options.index("cases-run"):options.index("cases-run") + 4], ["cases-run", "teams", "teams-test", "page-latency"])
        self.assertEqual((options.count("teams"), options.count("teams-test")), (1, 1))
        self.assertEqual(options[options.index("operator-probe") + 1:options.index("operator-probe") + 3], ["aigateway", "aigateway-check"], "the pair of the AI Gateway still follows operator-probe at once")
        self.assertEqual(options[options.index("loop-check") + 1:options.index("loop-check") + 3], ["powerplatform", "operator"])
        self.assertEqual(options[-4:], ["agents-drift", "foundry-evals", "foundry-redteam", "agent365-check"])

    def test_the_description_says_what_each_phase_makes_and_what_it_does_not(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)
        sentence = description.split(" teams: ")[1].split(" aigateway: ")[0]
        for words in ("docs/proposals/20-teams-cards-through-a-bot.md", "Phase 1, while the secret TEAMS_BOT_APP_ID is empty: only the user-assigned identity id-meternaut-teams",
                      "no API permission", "Phase 2, once the secret is set: the Azure Bot resource (single tenant, free SKU, local authentication off", "unless the resource provider Microsoft.BotService is registered",
                      "reads the role assignments of the identity, which has to be none", "It makes no role, no private endpoint and no key", "the action cases attaches the identity", "teams-test: from inside the network",
                      "any HTTP answer proves the path", "teams-card-test", "no id and no name"):
            self.assertIn(words, sentence, words)
        self.assertNotIn('"', sentence, "the description is one quoted value on one line")

    def test_the_client_id_is_a_secret_the_delivery_is_a_variable_and_the_lint_and_bootstrap_say_so(self):
        job_env = re.search(r"(?ms)^    env:\n(.*?)^    steps:", WORKFLOW).group(1)
        self.assertIn("      TEAMS_BOT_APP_ID: ${{ secrets.TEAMS_BOT_APP_ID }}\n", job_env)
        self.assertIn("      TEAMS_DELIVERY: ${{ vars.TEAMS_DELIVERY }}\n", job_env)
        self.assertIn("TEAMS_BOT_APP_ID", wl.ESTATE_SECRETS)
        self.assertIn("TEAMS_BOT_APP_ID", wl.NEVER_VARIABLES, "a client id is an identifier of the estate: GitHub masks a secret in the public log and does not mask a variable")
        self.assertNotIn("TEAMS_DELIVERY", wl.NEVER_VARIABLES)
        self.assertEqual(wl.lint_text(WORKFLOW, "deploy-hub.yml") if hasattr(wl, "lint_text") else [], [])
        bootstrap = read("environment/BOOTSTRAP.md")
        for words in ("`TEAMS_BOT_APP_ID` is a **secret**", "`TEAMS_DELIVERY` is a **variable**", "| B1 |", "| B5 |", "**The order.**", "**Going back:**", "global default app setup policy"):
            self.assertIn(words, bootstrap, words)
        self.assertIn("(#added-on-2026-11-13-for-the-teams-bot-built-not-deployed-the-owners-plain-yes-of-2026-11-13)", bootstrap)
        self.assertNotIn("TEAMS_BOT_ENABLED", bootstrap, "the switch of the earlier bot is gone, and the new one is TEAMS_DELIVERY")
        masks = code_of("Mask the identifiers of the estate in this run's log")
        self.assertIn('"$TEAMS_BOT_APP_ID"', masks)

    def test_the_mask_step_reads_the_identity_of_the_cases_app_only_for_cases_and_what_if_and_the_shared_step_gets_one_more_line(self):
        self.assertIn("if: inputs.action == 'cases' || inputs.action == 'what-if'", step(IDENTITY_STEP))
        self.assertIn("TEAMS_BOT_IDENTITY_CLIENT_ID: ${{ steps.teams_identity.outputs.client_id }}", step("Work out the settings"))
        script = code_of(IDENTITY_STEP)
        self.assertIn("::add-mask::", script)
        self.assertIn("id-meternaut-teams", script)
        for line in script.splitlines():
            if "$client" in line and "echo" in line:
                self.assertIn('>> "$GITHUB_OUTPUT"', line, "the client id goes to the step output and is masked, never printed")


class TheStepsFollowTheOrderThatKeepsTheObjectsConsistent(unittest.TestCase):
    def names(self):
        return [title for title, _ in blocks()]

    def test_the_steps_of_teams_are_these_seven_in_this_order_before_the_two_of_teams_test_and_the_summary(self):
        ran = [title for title, body in blocks() if re.search(r"(?m)^        if: inputs\.action == 'teams'$", body)]
        self.assertEqual(ran, TEAMS_CHAIN)
        names = self.names()
        positions = [names.index(name) for name in TEAMS_CHAIN + TEST_CHAIN]
        self.assertEqual(positions, list(range(positions[0], positions[0] + 9)), "no step of another action is in between")
        self.assertEqual(names[positions[-1] + 1], "What was done")
        self.assertEqual(len([t for t, b in blocks() if "inputs.action == 'teams'" in b]), 7)
        self.assertEqual(len(re.findall(r"inputs\.action == 'teams-test'", WORKFLOW)), 2, "the Operator is found for it, and the test step runs for it (the cleanup follows the test step's outcome)")

    def test_the_operator_is_found_for_the_test_and_the_test_runs_the_tool_in_the_operator_with_arguments_that_the_container_accepts(self):
        self.assertIn("inputs.action == 'teams-test'", step("Find the Operator, which runs the check from inside the network"))
        script = code_of(TEST)
        for text in ('--secret-file "teams-check.py=tools/teams-check.py"', '--secret-file "check-helpers.py=tools/check-helpers.py"', "--env \"TOOL_NAME=teams-check\"", '--name "op-teams-$GITHUB_RUN_ID"',
                     "--script operator/run-tool.sh", '--summary "$GITHUB_STEP_SUMMARY"', '"${dns[@]}"', "--timeout-seconds 1500"):
            self.assertIn(text, script, text)
        arguments = re.search(r'TOOL_ARGS=([^"]+)"', script).group(1)
        self.assertRegex(arguments.replace("$STORAGE_ACCOUNT", "stexample").replace("$insights", "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg/providers/Microsoft.Insights/components/appi"), r"^[A-Za-z0-9 ./:_=-]+$")
        self.assertTrue(arguments.startswith("run "))
        self.assertLessEqual(len(arguments), 200)
        self.assertTrue((ROOT / "tools" / "teams-check.py").is_file())
        self.assertIn("operator-run.py cleanup --resource-group \"$ENV_RESOURCE_GROUP\" --prefix op-teams-", code_of(TEST_CLEANUP))
        self.assertIn("if: always() && steps.teams_test.outcome != 'skipped'", step(TEST_CLEANUP))

    def test_nothing_writes_but_the_one_deployment_and_no_role_key_or_login_is_made(self):
        for name in [n for n in TEAMS_CHAIN + TEST_CHAIN + [IDENTITY_STEP] if n != LOGIN]:
            script = code_of(name)
            for forbidden in (r"az role\b", r"az ad\b", r"az login", r"az group\b", r"az resource (create|delete|update)", r"az deployment", r"az bot\b", r"--method (put|post|patch|delete)", r"az keyvault", r"listKeys", r"\bgh \w+ (run|set)"):
                self.assertNotRegex(script, forbidden, f"{name}: {forbidden}")
        self.assertEqual(code_of(DEPLOY).count("tools/az-deploy.py create"), 1)
        self.assertIn("--output identityName", code_of(DEPLOY))
        self.assertIn("--template environment/teams/main.bicep", code_of(DEPLOY))
        self.assertIn("--teams)", code_of(SETTINGS) + ")")

    def test_the_read_back_reads_the_role_assignments_of_the_identity_and_the_properties_that_matter(self):
        script = code_of(READ_BACK)
        for text in ("providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01&%24filter=principalId%20eq%20%27${principal}%27", "properties.msaAppType", "SingleTenant", "azurebot", "properties.disableLocalAuth",
                     "properties.msaAppId", "properties.endpoint", "channels/MsTeamsChannel", "properties.properties.isEnabled", "properties.properties.enableCalling", "properties.principalId"):
            self.assertIn(text, script, text)
        self.assertNotIn("UserAssignedMSI", script.replace("(the legacy UserAssignedMSI and the deprecated MultiTenant are refused)", ""), "the legacy type is only named in the words that refuse it")

    def test_the_identity_is_never_asked_for_a_state_that_it_does_not_have(self):
        """A user-assigned identity answers a GET (2023-01-31) with its client id, its object id and its tenant under properties, and no provisioningState (Learn, Microsoft.ManagedIdentity/userAssignedIdentities):
        a check of one would fail every run of `teams` after a deployment that went well."""
        for name in (IDENTITY_STEP, FACTS, READ_BACK):
            self.assertNotIn("provisioningState", code_of(name), name)
        self.assertEqual(sorted(re.findall(r'read_value "\$identity" 2023-01-31 ([A-Za-z.]+)', code_of(READ_BACK))), ["properties.clientId", "properties.principalId"])
        for name in (IDENTITY_STEP, FACTS):
            self.assertIn('--query "[properties.principalId, properties.clientId]"', code_of(name), name)

    def test_the_same_azure_login_is_pinned_and_no_new_secret_beyond_the_client_id_is_read(self):
        self.assertEqual(set(re.findall(r"\bsecrets\.([A-Za-z_]+)", "\n".join(line for line in WORKFLOW.splitlines() if not line.lstrip().startswith("#")))), wl.ESTATE_SECRETS)
        self.assertRegex(step(LOGIN), r"uses: azure/login@[0-9a-f]{40} # v[\d.]+\n")


@SKIP_BASH
class TheScriptsRunWithStandIns(unittest.TestCase):
    FACTS_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"provider show"*)
    if [ "$FAKE_PROVIDER" = DENIED ]; then echo "$FAKE_DENIED" >&2; exit 1; fi
    printf '%s' "$FAKE_PROVIDER" ;;
  *"userAssignedIdentities/id-meternaut-teams?api-version=2023-01-31"*)
    if [ "$FAKE_IDENTITY" = NOTFOUND ]; then echo "ERROR: (ResourceNotFound) not found" >&2; exit 1; fi
    if [ "$FAKE_IDENTITY" = DENIED ]; then echo "$FAKE_DENIED" >&2; exit 1; fi
    printf '%s\\t%s\\n' "$FAKE_PRINCIPAL" "$FAKE_CLIENT" ;;
  *"/providers/Microsoft.Web/sites/"*)
    if [ "$FAKE_SITE" = NOTFOUND ]; then echo "ERROR: (ResourceNotFound) not found" >&2; exit 1; fi
    if [ "$FAKE_SITE" = DENIED ]; then echo "$FAKE_DENIED" >&2; exit 1; fi
    printf '%s' "$FAKE_SITE" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

    def facts(self, **env):
        return run(FACTS, {"az": self.FACTS_AZ}, **{"FAKE_PROVIDER": "Registered", "FAKE_IDENTITY": "there", "FAKE_PRINCIPAL": PRINCIPAL, "FAKE_CLIENT": IDENTITY_CLIENT, "FAKE_SITE": HOST, **env})

    def test_phase_one_is_the_default_reads_nothing_and_says_that_the_hand_step_is_next(self):
        for value in ("", "   "):
            done, lines, out = self.facts(TEAMS_BOT_APP_ID=value)
            self.assertEqual(done.returncode, 0, said(done))
            self.assertEqual(lines, [], "phase 1 asks Azure nothing")
            self.assertEqual(out.splitlines(), ["phase=1", "function_host="])
            self.assertIn("Phase 1: the secret TEAMS_BOT_APP_ID of the environment hub is empty", done.stdout)
            self.assertIn("The Microsoft Entra hand step is next", done.stdout)

    def test_phase_two_reads_the_provider_the_identity_and_the_host_and_masks_what_it_read_without_printing_it(self):
        done, lines, out = self.facts(TEAMS_BOT_APP_ID=CLIENT)
        self.assertEqual(done.returncode, 0, said(done))
        self.assertIn("function_host=" + HOST, out)
        self.assertIn("phase=2", out)
        for value in (PRINCIPAL, IDENTITY_CLIENT, HOST, HOST.upper()):
            self.assertIn(f"::add-mask::{value}", done.stdout, value)
        printed = "\n".join(line for line in done.stdout.splitlines() if not line.startswith("::add-mask::"))
        for secret in (PRINCIPAL, IDENTITY_CLIENT, HOST, CLIENT):
            self.assertNotIn(secret, printed)
        self.assertFalse(GUID.search(printed))

    def test_phase_two_stops_before_anything_is_changed_and_says_what_is_missing(self):
        for env, words in (({"FAKE_PROVIDER": "NotRegistered"}, "The resource provider Microsoft.BotService is NotRegistered"), ({"FAKE_PROVIDER": ""}, "is not registered in the subscription"),
                           ({"FAKE_PROVIDER": "Registering"}, "is still registering in the subscription (a registration takes a few minutes). Wait until it says Registered"),
                           ({"FAKE_IDENTITY": "NOTFOUND"}, "The identity id-meternaut-teams is not there, and the secret TEAMS_BOT_APP_ID is set"), ({"FAKE_SITE": "NOTFOUND"}, "The cases app is not there"),
                           ({"FAKE_SITE": "not-a-host"}, "does not report a default host name")):
            done, _, out = self.facts(TEAMS_BOT_APP_ID=CLIENT, **env)
            self.assertNotEqual(done.returncode, 0, env)
            self.assertIn(words, said(done))
            self.assertIn("Nothing was changed.", said(done))
            self.assertNotIn("function_host=", out)
        done, _, _ = self.facts(TEAMS_BOT_APP_ID=CLIENT, FAKE_PROVIDER="Registering")
        self.assertNotIn("register it once", said(done), "a provider that is registering is not asked to be registered again")

    DENIED = (f"ERROR: (AuthorizationFailed) The client '{PRINCIPAL}' with object id '{PRINCIPAL}' does not have authorization to perform action 'Microsoft.Web/sites/read' "
              f"over scope '/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}' or the scope is invalid.")

    def test_what_azure_says_when_a_read_fails_is_printed_with_every_id_replaced(self):
        for what, env in (("the provider", {"FAKE_PROVIDER": "DENIED"}), ("the identity", {"FAKE_IDENTITY": "DENIED"}), ("the cases app", {"FAKE_SITE": "DENIED"})):
            done, _, out = self.facts(TEAMS_BOT_APP_ID=CLIENT, FAKE_DENIED=self.DENIED, **env)
            self.assertNotEqual(done.returncode, 0, what)
            self.assertIn("<id>", said(done), what)
            self.assertFalse(GUID.search("\n".join(line for line in said(done).splitlines() if not line.startswith("::add-mask::"))), f"{what}: an id of the estate was printed")
            self.assertIn("does not have authorization to perform action", said(done), "the rest of what Azure said is kept")

    IDENTITY_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$FAKE_IDENTITY" in
  there) printf '%s\\t%s\\n' "$FAKE_PRINCIPAL" "$FAKE_CLIENT" ;;
  NOTFOUND) echo "ERROR: (ResourceNotFound) not found" >&2; exit 1 ;;
  *) echo "$FAKE_DENIED" >&2; exit 1 ;;
esac
"""

    def test_the_read_of_the_identity_for_cases_masks_the_ids_it_reads_and_prints_what_azure_says_without_an_id(self):
        base = {"ACTION": "cases", "FAKE_PRINCIPAL": PRINCIPAL, "FAKE_CLIENT": IDENTITY_CLIENT, "FAKE_DENIED": self.DENIED}
        done, _, out = run(IDENTITY_STEP, {"az": self.IDENTITY_AZ}, **{**base, "FAKE_IDENTITY": "there"})
        self.assertEqual(done.returncode, 0, said(done))
        self.assertIn("client_id=" + IDENTITY_CLIENT, out)
        self.assertIn(f"::add-mask::{IDENTITY_CLIENT}", done.stdout)
        done, _, out = run(IDENTITY_STEP, {"az": self.IDENTITY_AZ}, **{**base, "FAKE_IDENTITY": "NOTFOUND"})
        self.assertEqual((done.returncode, out), (0, "client_id=\n"), "not there is an answer: the app is not given the identity")
        done, _, _ = run(IDENTITY_STEP, {"az": self.IDENTITY_AZ}, **{**base, "FAKE_IDENTITY": "DENIED"})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("<id>", said(done))
        self.assertFalse(GUID.search("\n".join(line for line in said(done).splitlines() if not line.startswith("::add-mask::"))))

    # What the real API answers (Learn, GET of an identity at 2023-01-31: clientId, principalId and tenantId under properties and nothing else; the bot and its channel: the properties of their templates). The
    # query that the script sends is matched whole: a property that the service does not have answers None, as the Azure CLI does, so a wrong path of a property fails the run as it would live.
    READ_BACK_AZ = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
url=""; query=""
for argument in "$@"; do
  if [ "$previous" = --url ]; then url="$argument"; fi
  if [ "$previous" = --query ]; then query="$argument"; fi
  previous="$argument"
done
case "$*" in
  *"account show"*) printf '%s' "$FAKE_TENANT" ;;
  *"/resourceGroups/$ENV_RESOURCE_GROUP/providers/Microsoft.Authorization/roleAssignments"*)
    if [ "$FAKE_GROUP_ROLES" = FAIL ]; then echo "ERROR: (AuthorizationFailed) denied" >&2; exit 1; fi
    printf '%s' "$FAKE_GROUP_ROLES" ;;
  *"channels/MsTeamsChannel"*)
    case "$query" in properties.properties.isEnabled) printf '%s' "$FAKE_ENABLED" ;; properties.properties.enableCalling) printf '%s' "$FAKE_CALLING" ;; *) printf None ;; esac ;;
  *"botServices/bot-meternaut-0123abcd?api-version=2022-09-15"*)
    case "$query" in
      kind) printf '%s' azurebot ;;
      sku.name) printf '%s' F0 ;;
      properties.msaAppType) printf '%s' "$FAKE_TYPE" ;;
      properties.msaAppId) printf '%s' "$FAKE_APP" ;;
      properties.msaAppTenantId) printf '%s' "$FAKE_TENANT" ;;
      properties.disableLocalAuth) printf '%s' "$FAKE_LOCAL" ;;
      properties.endpoint) printf '%s' "$FAKE_ENDPOINT" ;;
      *) printf None ;;
    esac ;;
  *"userAssignedIdentities/id-meternaut-teams?api-version=2023-01-31"*)
    if [ -n "$FAKE_DENIED" ]; then echo "$FAKE_DENIED" >&2; exit 1; fi
    case "$query" in properties.principalId) printf '%s' "$FAKE_PRINCIPAL" ;; properties.clientId) printf '%s' "$FAKE_CLIENT" ;; properties.tenantId) printf '%s' "$FAKE_TENANT" ;; *) printf None ;; esac ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

    def read_back(self, **env):
        base = {"PHASE": "2", "IDENTITY_NAME": "id-meternaut-teams", "BOT_NAME": "bot-meternaut-0123abcd", "SKU": "F0", "FUNCTION_HOST": HOST, "TEAMS_BOT_APP_ID": CLIENT, "FAKE_TENANT": "99999999-8888-7777-6666-555555555555",
                "FAKE_GROUP_ROLES": "0", "FAKE_ENABLED": "True", "FAKE_CALLING": "False", "FAKE_TYPE": "SingleTenant", "FAKE_APP": CLIENT.upper(), "FAKE_LOCAL": "True", "FAKE_ENDPOINT": f"https://{HOST}/api/messages",
                "FAKE_PRINCIPAL": PRINCIPAL, "FAKE_CLIENT": IDENTITY_CLIENT}
        return run(READ_BACK, {"az": self.READ_BACK_AZ}, **{**base, **env})

    def test_a_good_read_back_says_that_the_identity_holds_no_role_and_that_the_bot_is_single_tenant_and_prints_no_identifier(self):
        done, lines, _ = self.read_back()
        self.assertEqual(done.returncode, 0, said(done))
        for words in ("The identity id-meternaut-teams holds no role assignment at the project's resource group, above it or below it, as the design says: 0", "The type of the bot's application (the legacy UserAssignedMSI and the deprecated MultiTenant are refused): SingleTenant.",
                      "The client id of the bot's application matches the secret TEAMS_BOT_APP_ID.", "The bot's application is in this tenant.", "Local authentication of the bot is off (disableLocalAuth): true.",
                      "The Microsoft Teams channel is enabled: true.", "Calling on the Microsoft Teams channel is off: false.", "the bot bot-meternaut-0123abcd and its Microsoft Teams channel are in Azure as the template wrote them, and the identity holds no role"):
            self.assertIn(words, done.stdout, words)
        printed = "\n".join(line for line in done.stdout.splitlines() if not line.startswith("::add-mask::"))
        self.assertFalse(GUID.search(printed), "no identifier is printed")
        self.assertNotIn(HOST, printed)
        self.assertNotRegex("\n".join(lines), r"--method (put|post|patch|delete)")

    def test_phase_one_checks_the_identity_alone(self):
        done, lines, _ = self.read_back(PHASE="1")
        self.assertEqual(done.returncode, 0, said(done))
        self.assertIn("The identity id-meternaut-teams is in Azure as the template wrote it, and it holds no role. The bot is made in phase 2.", done.stdout)
        self.assertFalse([line for line in lines if "botServices" in line])
        self.assertFalse([line for line in lines if "provisioningState" in line], "a user-assigned identity has no state to read")

    def test_an_identity_that_reports_no_object_id_fails_the_run_and_what_azure_says_when_it_cannot_be_read_is_printed_without_an_id(self):
        done, _, _ = self.read_back(FAKE_PRINCIPAL="")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("The identity reports no object id, so its role assignments cannot be read.", said(done))
        done, _, _ = self.read_back(FAKE_DENIED=self.DENIED)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("<id>", said(done))
        self.assertIn("does not have authorization to perform action", said(done))
        self.assertFalse(GUID.search("\n".join(line for line in said(done).splitlines() if not line.startswith("::add-mask::"))))

    def test_a_role_assignment_fails_the_run_and_the_count_is_said_without_an_id(self):
        done, _, _ = self.read_back(FAKE_GROUP_ROLES="2")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("holds 2 role assignment(s) at or around the project's resource group. It must hold none", said(done))
        self.assertFalse(GUID.search("\n".join(line for line in said(done).splitlines() if not line.startswith("::add-mask::"))))

    def test_when_the_role_assignments_cannot_be_read_the_run_fails_and_says_that_it_is_not_known_that_there_are_none(self):
        done, lines, _ = self.read_back(FAKE_GROUP_ROLES="FAIL")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("The role assignments of the identity could not be read, so it is not known that it holds none.", said(done))
        self.assertNotIn("holds no role assignment", done.stdout)
        self.assertEqual([line for line in lines if "roleAssignments" in line and "/resourceGroups/" not in line], [], "the read stays in the project's resource group: nothing is asked of the subscription")

    def test_a_bot_that_is_not_what_the_template_wrote_fails_the_run_and_the_values_are_not_printed(self):
        for change, words in (({"FAKE_TYPE": "UserAssignedMSI"}, "expected SingleTenant, read UserAssignedMSI"), ({"FAKE_TYPE": "MultiTenant"}, "expected SingleTenant, read MultiTenant"), ({"FAKE_APP": "00000000-0000-4000-8000-000000000000"}, "does not match the secret TEAMS_BOT_APP_ID"),
                              ({"FAKE_LOCAL": "False"}, "expected true, read false"), ({"FAKE_ENDPOINT": "https://elsewhere.example/api/messages"}, "endpoint is not the one that the template wrote (the value is not printed)"),
                              ({"FAKE_ENABLED": "False"}, "The Microsoft Teams channel is enabled: expected true, read false"), ({"FAKE_CALLING": "True"}, "Calling on the Microsoft Teams channel is off: expected false, read true"),
                              ({"FAKE_TENANT": ""}, "is not reported to be in this tenant")):
            done, _, _ = self.read_back(**change)
            self.assertNotEqual(done.returncode, 0, change)
            self.assertIn(words, said(done))
            self.assertNotIn("elsewhere.example", said(done))
            self.assertNotIn("00000000-0000-4000-8000-000000000000", said(done))

    def test_the_hand_steps_are_printed_with_placeholders_for_each_phase_and_into_the_summary(self):
        for phase, words in (("1", ("python tools/entra-setup.py teams-bot", "environment/BOOTSTRAP.md, step B2, has the whole command", "no secret, no certificate, no API permission, no redirect address",
                                    "registers the resource provider Microsoft.BotService once (environment/BOOTSTRAP.md, step B1)", "(phase 1 is done)")),
                             ("2", ("GLOBAL default app setup policy", "https://teams.microsoft.com/l/app/<Teams app id>", "then the action teams-test", "set the variable TEAMS_DELIVERY of the environment hub to bot", "(phase 2 is done)"))):
            done, _, _ = run(HAND_STEPS, {}, PHASE=phase)
            self.assertEqual(done.returncode, 0, said(done))
            for text in words:
                self.assertIn(text, done.stdout, text)
            self.assertFalse(GUID.search(done.stdout), "no identifier is printed: the log of a public repository is public")
            self.assertNotIn(SUBSCRIPTION, done.stdout)

    def summary(self, action, status, phase=""):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            summary.write_text("", encoding="utf-8")
            script = Path(tmp) / "step.sh"
            script.write_text(ws.step_script("What was done"), encoding="utf-8", newline="\n")
            env = {**os.environ, "ACTION": action, "JOB_STATUS": status, "ENV_RESOURCE_GROUP": GROUP, "TEAMS_PHASE": phase, "GITHUB_RUN_ID": "12345", "GITHUB_STEP_SUMMARY": summary.as_posix()}
            done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=env, cwd=ROOT)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stderr, "", "a backtick that is not escaped inside the quotes runs a command in bash")
            return summary.read_text(encoding="utf-8")

    def test_the_summary_says_what_is_true_for_each_phase_and_for_a_run_that_did_not_finish(self):
        one = self.summary("teams", "success", "1")
        for words in ("### Hub: teams, success", "holds NO role assignment (zero were found", "No bot is made yet. **The Microsoft Entra hand step is next:**", "stores the client id that it prints as the secret TEAMS_BOT_APP_ID", "The cases app was not changed."):
            self.assertIn(words, one, words)
        two = self.summary("teams", "success", "2")
        for words in ("single tenant, on the free SKU", "local authentication off and a notification-only endpoint that is never called", "enabled with calling off", "it still sends Teams cards through the queue",
                      "only after it passes set TEAMS_DELIVERY to bot"):
            self.assertIn(words, two, words)
        failed = self.summary("teams", "failure", "2")
        for words in ("**The run did not finish.**", "Part of the Azure side of the Teams bot may exist now", "a person who may registers it once: environment/BOOTSTRAP.md, step B1", "Teams cards still go through the queue until the owner sets TEAMS_DELIVERY to bot",
                      "Running `teams` again is safe"):
            self.assertIn(words, failed, words)
        test = self.summary("teams-test", "success")
        for words in ("probed the two hosts that the app talks to", "plain words and status classes only", "The owner received one test card and then its closing card.", "A pass proves the path that it covers and nothing more"):
            self.assertIn(words, test, words)
        broken = self.summary("teams-test", "failure")
        for words in ("op-teams-12345", "a finding about the network, and the owner decides what to ask for", "AADSTS code", "A 403 when the chat is created means that the Teams app is not installed"):
            self.assertIn(words, broken, words)
        for text in (one, two, failed, test, broken):
            self.assertFalse(GUID.search(text))


if __name__ == "__main__":
    unittest.main()
