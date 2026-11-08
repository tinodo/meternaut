"""The documents of step 2 of the AI Gateway: what they say about the switch, the order of the real run, what each failure means, and the way back.

Step 1's documents have their own tests (test_aigateway_docs.py). The code of step 2 has tests of its own (test_aigateway_agents_params.py, _template.py, _check.py, _workflow.py, and the cases app's
test_foundry_route.py and test_investigate_route.py). Here the documents are held to the code: the names, the audience, the order of the actions and the fixed words of the app are the ones that the code has."""
import ast
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("environment_params_of_the_agents_route_docs", ROOT / "tools" / "environment-params.py")
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)

ACTIONS = ("aigateway", "aigateway-check", "foundry", "cases", "cases-run")


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def flat(source):
    return re.sub(r"\s+", " ", source)


PROPOSAL_TEXT = text("docs/proposals/08-ai-gateway.md")
PROPOSAL = flat(PROPOSAL_TEXT)
BOOTSTRAP = text("environment/BOOTSTRAP.md")
AGENTS = text("AGENTS.md")
FOUNDRY_AGENTS = text("docs/proposals/06-foundry-agents.md")
CHANGELOG = text("CHANGELOG.md")
README = text("README.md")
FOUNDRY_TEMPLATE = text("environment/foundry/main.bicep")
STEP_2 = "## Step 2: what is built, the switch and the real run"
SECTION = "## Added on 2026-11-07 for the agents' route through the AI Gateway (step 2)"


def step_2_of_the_record():
    return PROPOSAL_TEXT.split(STEP_2 + "\n")[1].split("\n## ")[0]


def section_of_bootstrap():
    return BOOTSTRAP.split(SECTION + "\n")[1].split("\n## ")[0]


def causes_of_the_app():
    """The `cause` of every RouteCause of src/case-functions/cases/foundry.py, read from the source: the app is not importable from here."""
    tree = ast.parse(text("src/case-functions/cases/foundry.py"))
    (table,) = [node.value for node in tree.body if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ROUTE_CAUSES" for t in node.targets)]
    causes = []
    for call in table.elts:
        strings = [arg.value for arg in call.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
        causes.append(strings[-2])
    return causes


class TheRecordOfStep2(unittest.TestCase):
    def test_the_status_says_that_step_1_is_deployed_step_2_is_on_in_code_and_ran_the_switch_is_true_and_the_question_is_open(self):
        status = re.search(r"\*\*Status: .*?\*\* This page records", PROPOSAL).group(0)
        for words in ("Step 1 of 2 is deployed and checked", "Step 2 of 2 is built and on in code, and it ran in Azure on 2026-11-08, with two `cases-run`s", "`AGENTS_VIA_AI_GATEWAY` in `tools/environment-params.py`, that is True since the owner's order of 2026-11-07",
                      "The Detective and the Skeptic of the cases app call the gateway, and ran through it in those runs", "the fix, the Investigator on gpt-6-luna with the effort `none`, has not been run",
                      "Whether the connection calls the gateway with the project's own managed identity and no key is not proved"):
            self.assertIn(words, status, words)
        self.assertNotIn("is not built", status)
        for old in ("Step 1 of 2 is built and not deployed", "not deployed too", "Nothing was made in Azure", "Step 2 of 2 is built and not deployed", "that is False", "so that nothing changes until the owner flips it",
                    "the agents were not touched", "it has not run in Azure", "which has not run either", "it was not tried", "ran once"):
            self.assertNotIn(old, status, old)
        first = PROPOSAL.split("**Update, 2026-11-08:")[1].split("**Update, 2026-11-07: the agents' route is on in code.**")[0]
        for words in ("The judges ran through the gateway (3 cases, every step ok).", "function tools do not work together with a reasoning effort for its model",
                      "So the Agent Service does call the gateway on the Chat Completions route (read from that answer: the gateway's own log is off, so it is not seen from the gateway's side).",
                      "The Responses route, which the answer names as the other way, is not offered for this service.", "The first fix asked for the reasoning effort `none`",
                      "In the second run the same model, gpt-6.1-sol, refused the effort `none` too: it takes low, medium and high only.",
                      "So gpt-6.1-sol cannot use function tools on the one route that the Agent Service has for the gateway.",
                      "The agents' models are now swapped: the Investigator is gpt-6-luna, which takes the effort `none`, and the Skeptic, which has no tools and sends no effort, is gpt-6.1-sol",
                      "no longer made again with the old key `agent`", "**That fix has not been run in Azure**", "it makes a new version of each agent on the next `cases-run`",
                      "If gpt-6-luna refuses too, the agents cannot use the gateway until the Responses route is offered for it, and the way back is the switch `AGENTS_VIA_AI_GATEWAY` set to False (the owner decides)."):
            self.assertIn(words, first, words)
        update = PROPOSAL.split("**Update, 2026-11-07: the agents' route is on in code.**")[1].split("**Update, 2026-11-07, before that:")[0]
        for words in ("\"Route [the agents] to the AI gateway ... IT NEEDS TO ADHERE TO THE CITADEL DESIGN PRINCIPLES\"", "the switch `AGENTS_VIA_AI_GATEWAY` in `tools/environment-params.py` is True",
                      "The order of the real run is `aigateway`, about ten minutes, `foundry`, `cases`, `cases-run`", "the update above says what came of it", "The way back is the switch set to False"):
            self.assertIn(words, update, words)
        self.assertNotIn("Nothing of it has run in Azure", update)

    def test_the_section_of_step_2_has_its_parts_in_order(self):
        headings = re.findall(r"(?m)^(##+ .*)$", PROPOSAL_TEXT)
        wanted = [STEP_2, "### The order of the real run", "### What the first real run showed", "### What each failure means", "### The way back from step 2", "### Choices of step 2 that the owner can change"]
        positions = [headings.index(heading) for heading in wanted]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(wanted))), "the parts follow one another")
        self.assertLess(headings.index("## Step 2 and what is not known about it"), positions[0])
        self.assertLess(positions[-1], headings.index("## The way back"), "the section of step 2 comes before the way back of the gateway")

    def test_it_says_what_the_switch_is_and_that_the_hub_changes_nothing_until_an_action_is_run_and_what_the_switch_does_in_each_action(self):
        section = flat(step_2_of_the_record())
        for words in ("**The Hub changes what Azure holds only when an action is run, and the real run follows the order below.**", "`AGENTS_VIA_AI_GATEWAY = True`", "next to `CASES_APP_PUBLIC_NETWORK_ACCESS`",
                      "after the owner's order of 2026-11-07 and after `aigateway` and `aigateway-check` had passed on the real estate", "The way back is the same line set to False.",
                      "the parameter files, the templates and every action are what they were before step 2", "the same byte for byte, and that the new parameters are empty or false",
                      "**`foundry` makes the connection `aigateway`**", "reads it back with GET only", "no credential held",
                      "**`aigateway` gives the Foundry project's identity *AI Gateway Models User***", "**`cases` gives the app the model names `aigateway/gpt-6-luna` and `aigateway/gpt-6.1-sol`,**",
                      "exactly `<name>` or `<name>/<name>`", "The builder refuses True when it cannot name the gateway."):
            self.assertIn(words, section, words)
        for old in ("Nothing changes until the owner flips one constant", "`AGENTS_VIA_AI_GATEWAY = False`", "Nothing of step 2 is deployed"):
            self.assertNotIn(old, section, old)

    def test_it_says_what_the_connection_is_and_that_its_shape_was_tried_once_and_that_no_key_path_is_built(self):
        section = flat(step_2_of_the_record())
        for words in ("Category `ApiManagement`, `authType` `ProjectManagedIdentity`, `audience` `https://azure-api.net/aigateway`, target `https://<host>/default/models/openai/v1`, empty `credentials`, "
                      "`isSharedToAll` false", "`deploymentInPath` `false`", "a static `models` list whose names are the aliases",
                      "**The shape comes from the samples and from Learn; it was tried on 2026-11-08, and the Agent Service called the gateway's route**",
                      "No key is used, and no path for a key is built: if the connection needs a key, the owner decides ([rule 23](../../AGENTS.md)).",
                      "Responses routing for the AI Gateway tier is \"coming soon\" in Learn, so the Responses route is not offered for this service and is not asked for."):
            self.assertIn(words, section, words)

    def test_it_says_the_order_of_the_writes_that_the_template_keeps(self):
        section = flat(step_2_of_the_record())
        for words in ("The Foundry resource takes one write at a time, the project after the last model deployment, and its private endpoint after every other write to the resource",
                      "So the connection comes after the traces connection and before the private endpoint, in the same deployment, and the private endpoint waits for it.",
                      "When the parameters are empty nothing is made"):
            self.assertIn(words, section, words)
        resources = re.findall(r"(?m)^resource (\w+) '", FOUNDRY_TEMPLATE)
        self.assertLess(resources.index("tracesConnection"), resources.index("aiGatewayConnection"))
        self.assertLess(resources.index("aiGatewayConnection"), resources.index("privateEndpoint"))
        self.assertRegex(FOUNDRY_TEMPLATE, r"(?s)resource privateEndpoint .*?dependsOn: \[[^\]]*aiGatewayConnection")

    def test_the_names_and_the_audience_of_the_record_are_the_ones_of_the_code(self):
        section = flat(step_2_of_the_record())
        self.assertEqual(ep.AIGATEWAY_CONNECTION_NAME, "aigateway")
        self.assertIn(f"the connection `{ep.AIGATEWAY_CONNECTION_NAME}`", section)
        for model in ep.AGENT_MODELS.values():
            self.assertIn(f"`{ep.AIGATEWAY_CONNECTION_NAME}/{model}`", section)
        self.assertEqual(set(ep.AGENT_MODELS), {"foundryModelInvestigator", "foundryModelSkeptic"})
        self.assertIn("audience: 'https://azure-api.net/aigateway'", FOUNDRY_TEMPLATE)
        self.assertIn("target: 'https://${aiGatewayHost}/default/models/openai/v1'", FOUNDRY_TEMPLATE)
        self.assertIn("deploymentInPath: 'false'", FOUNDRY_TEMPLATE)

    def test_the_order_of_the_real_run_is_the_same_in_the_record_and_on_the_bootstrap_page(self):
        (sentence,) = re.findall(r"\*\*The order of the real run of step 2:\*\* (.*?)\. \[The bootstrap page\]", flat(step_2_of_the_record()))
        in_the_record = [name for name in re.findall(r"`([^`]+)`", sentence) if name in ACTIONS]
        self.assertEqual(in_the_record, ["aigateway", "aigateway-check", "aigateway", "foundry", "cases", "cases-run"])
        items = re.findall(r"(?m)^(\d+)\. (.*)$", section_of_bootstrap())
        self.assertEqual([number for number, _ in items], [str(n) for n in range(1, 9)])
        on_the_page = []
        for _, item in items:
            names = [name for name in re.findall(r"`([^`]+)`", item) if name in ACTIONS]
            if names:
                on_the_page.append(names[0])
        self.assertEqual(on_the_page, in_the_record, "the actions come in the same order on the page")
        self.assertIn("the owner's order and the change of one line that sets the switch to True (made)", sentence)
        self.assertIn("about ten minutes", sentence)
        self.assertIn("The last five are the real run. It was made on 2026-11-08 and repeated after the first fix, and both times the investigation stopped at the model's refusal of function tools:", flat(step_2_of_the_record()))
        self.assertIn("and the run with the second fix, which makes the Investigator gpt-6-luna with the effort `none`, has not been made.", flat(step_2_of_the_record()))
        self.assertIn("On an estate that has neither the Foundry project nor the gateway, `foundry` and `aigateway` each ask for the other while the switch is True, so they are made with the switch False first.",
                      flat(step_2_of_the_record()))

    def test_every_cause_that_the_app_says_is_in_the_table_of_what_each_failure_means(self):
        causes = causes_of_the_app()
        self.assertEqual(len(causes), 7)
        table = PROPOSAL.split("### What each failure means")[1].split("### The way back from step 2")[0]
        for cause in causes:
            self.assertIn(cause[0].upper() + cause[1:], table, cause)
        for words in ("the words of the Agent Service as they came (redacted and cut)", "never a message, a token or a header", "Only when the model has a connection does it say anything",
                      "| `aigateway`, early | The Foundry project is not in Azure |", "| `foundry`, early | The AI Gateway is not in Azure |", "| `foundry`, the deployment | Azure refuses the connection and names it |",
                      "| `foundry`, the read-back | One field differs, or a credential is held |", "| `cases`, before the deploy | The connection does not exist |",
                      "his decision under rule 23; no path for it is built"):
            self.assertIn(words, table, words)

    def test_the_way_back_says_exactly_what_stays(self):
        part = flat(PROPOSAL_TEXT.split("### The way back from step 2")[1].split("\n### ")[0])
        for words in ("Set the switch back to False", "run `foundry` and `cases`", "**What stays:** the connection `aigateway` in the project, the role of the project's identity on the gateway, and the gateway.",
                      "The deployment is incremental", "does not delete the connection, and no action deletes the role", "A person deletes the connection by hand",
                      "which [rule 15 (c)](../../AGENTS.md) allows only on the owner's written exception"):
            self.assertIn(words, part, words)

    def test_the_table_of_what_is_known_has_the_rows_of_step_2_and_says_what_the_first_real_run_answered(self):
        table = PROPOSAL.split("## What is verified, what is inferred, what is not known")[1].split("## The frontend is public only")[0]
        for words in ("| Whether a Foundry project's connection can use its managed identity to call this gateway | **Not proved: the first real run (2026-11-08) was refused for the call's options and not for the token, which suggests that the identity was taken (inferred)** |",
                      "| Inferred, **tried on 2026-11-08: the connection exists, and the Agent Service called the gateway's route** |",
                      "| An agent names its model `<connection>/<model>`, and a wrong name is answered with \"model not found\" | Verified |",
                      "| Whether the service takes the category `ApiManagement` with a managed identity for a target that is not `*.azure-api.net` | **Yes: the connection was made (2026-11-08)** |",
                      "| Whether the Agent Service then calls the gateway with a token of the project's identity", "| What the Agent Service answers when the gateway refuses a call: the status, the code and the words | **Not known** |",
                      "| Whether the Agent Service reports token usage for a model behind a connection | **Not known** |",
                      "| Whether the optional version of a model in the connection's list is added to the model name in the call | **Not known** |",
                      "| That the gateway is reachable from the managed inference plane of the Agent Service | Inferred |"):
            self.assertIn(words, table, words)

    def test_the_section_of_the_first_real_run_says_what_it_showed_what_the_fix_is_and_that_the_fix_is_not_run(self):
        part = flat(PROPOSAL_TEXT.split("### What the first real run showed")[1].split("\n### ")[0])
        for words in ("On 2026-11-08 `cases-run` ran twice with the agents on the gateway", "`aigateway/gpt-6.1-sol` for the Investigator and `aigateway/gpt-6-luna` for the Skeptic",
                      "**The judges ran through the gateway.**", "judged 3 cases, and every step was ok", "**Run 1: the Agent Service calls the gateway's route, on Chat Completions.**",
                      "HTTP 400 and the code `model_error`", "Function tools with reasoning_effort are not supported for gpt-6.1-sol in /v1/chat/completions.",
                      "To use function tools, use /v1/responses or set reasoning_effort to 'none'.", "It is not known whether the model or the Agent Service itself refused it, because the gateway's own log is off.",
                      "**The Responses route is not offered for this service.**", "\"coming soon\"", "**`agent_reference` is the key.**",
                      "The 'agent' property is deprecated. Use 'agent_reference' instead", "That answer hid the first one.",
                      "**Run 2, with the effort `none` asked for: the same model refuses it.**", "the code `unsupported_value`",
                      "Unsupported value: 'none' is not supported with the 'gpt-6.1-sol-2026-09-29' model. Supported values are: 'low', 'medium', and 'high'.",
                      "**So gpt-6.1-sol cannot use function tools on this route.**", "The model that uses tools has to be one that takes the effort none.",
                      "**The fix, built and not run yet.**", "The agents' models are swapped: the Investigator is `gpt-6-luna` with `reasoning: {\"effort\": \"none\"}` in its definition",
                      "`PromptAgentDefinition.reasoning`", "and the Skeptic is `gpt-6.1-sol`, with no tools and no effort sent, so that the stronger model judges.",
                      "a test holds the pair together with the reason: the Investigator's model is not one that refuses the effort `none`",
                      "The capacities of `environment/models.json` moved with the roles (gpt-6-luna 50 thousand tokens a minute for the agents, gpt-6.1-sol 20)",
                      "they apply when `foundry` is run", "Both agents get a new version on the next `cases-run`.",
                      "is not made again with the other key, and is shown as it came", "the first answer is shown and `agent_reference` stays",
                      "**If gpt-6-luna refuses too,** the agents cannot use the gateway until the Responses route is offered for it", "the owner decides",
                      "**Not known:** that an investigation completes on gpt-6-luna with the effort `none`, that the Skeptic agent runs on gpt-6.1-sol, and whether the Agent Service reports token numbers for a model behind a connection."):
            self.assertIn(words, part, words)
        for secret in ("request id", "request-id"):
            self.assertNotIn(secret, part)
        table = flat(PROPOSAL_TEXT.split("### What each failure means")[1].split("### The way back from step 2")[0])
        self.assertIn("An answer of the model itself (the code `model_error`, or words about the reasoning effort or the function tools) is about something else too, even when it names the ModelGateway.", table)
        known = PROPOSAL.split("## What is verified, what is inferred, what is not known")[1].split("## The frontend is public only")[0]
        self.assertIn("| Whether gpt-6-luna does function tools with the effort `none` on the Chat Completions route, which is the only route that the Agent Service has for the gateway | **Not known; the next `cases-run` answers** |", known)

    def test_the_part_of_the_record_that_is_about_step_2_holds_no_key_no_address_of_the_owner_and_no_guid(self):
        section = step_2_of_the_record()
        self.assertNotRegex(section.lower(), r"another-project|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        for word in ("api-key", "listSecrets", "primaryKey", "connection string", "bearer"):
            self.assertNotIn(word.lower(), section.lower(), word)


class TheOtherDocumentsOfStep2(unittest.TestCase):
    def test_the_bootstrap_section_has_the_order_what_is_not_known_and_the_way_back(self):
        section = flat(section_of_bootstrap())
        for words in ("**Built, on in code, and run in Azure (2026-11-08).**", "Step 2 adds no action and no hand step.",
                      "`AGENTS_VIA_AI_GATEWAY` in [`tools/environment-params.py`](../tools/environment-params.py), which is `True` since the owner's order of 2026-11-07",
                      "No Azure change was made and no Hub run was made for step 2 when this page was written.",
                      "It was run on 2026-11-08 (items 4 to 7 below, up to `cases-run`, and `cases-run` again after a first fix): the Investigator was refused at its first call both times, because its model, gpt-6.1-sol, does not take function tools together with a reasoning effort and does not take the effort none either. The Investigator is now gpt-6-luna with the effort `none`, and the Skeptic gpt-6.1-sol. That fix has not been run",
                      "`cases` gives the app the model names `aigateway/gpt-6-luna` for the Investigator and `aigateway/gpt-6.1-sol` for the Skeptic",
                      "**What the constant does when it is True.**",
                      "No key is used and none is built: if the connection needs one, the owner decides ([rule 23](../AGENTS.md)).",
                      "**What is not known.**", "**The order.**", "**Going back.**", "**What stays:** the connection `aigateway` in the Foundry project",
                      "a later `foundry` run does not delete it", "because the deployment is incremental", "no action does it",
                      "which [rule 15 (c)](../AGENTS.md) allows only on the owner's written exception",
                      "Items 1 to 3 are done. Items 4 to 7 are the real run of step 2: `aigateway`, about ten minutes, `foundry`, `cases`, `cases-run`. They were made on 2026-11-08, and `cases-run` stopped at the Investigator's first call; the run with the fix repeats the last two, `cases` and `cases-run`.",
                      "On an estate that has neither the Foundry project nor the gateway, `foundry` and `aigateway` each ask for the other while the constant is `True`: make them with the constant `False` first, and set it to `True` afterwards."):
            self.assertIn(words, section, words)
        for old in ("Built, not deployed, and not tried", "`AGENTS_VIA_AI_GATEWAY = False`", "If the owner says no to the connection, the constant stays False and nothing is lost.", "and not run in Azure.**"):
            self.assertNotIn(old, section, old)
        self.assertLess(section.index("**What is not known.**"), section.index("**The order.**"))
        self.assertLess(section.index("**The order.**"), section.index("**Going back.**"))
        self.assertEqual(len(re.findall(r"```", section_of_bootstrap())), 0, "no hand step and so no block of commands")

    def test_the_bootstrap_section_says_what_to_read_in_each_step_and_when_to_stop(self):
        items = {number: flat(item) for number, item in re.findall(r"(?m)^(\d+)\. (.*)$", section_of_bootstrap())}
        self.assertIn("Read: the gateway, its subnet, its models and aliases, the limits, and who holds the role (the Operator only).", items["1"])
        self.assertIn("every alias answered with HTTP 200 and usage numbers, the call with no token answered 401, and the call with a wrong alias refused", items["2"])
        self.assertIn("The owner ordered the route in plain words on 2026-11-07, and a change of one line sets `AGENTS_VIA_AI_GATEWAY = True`; it is reviewed and merged like any other change.", items["3"])
        self.assertIn("\"The switch of the agents' route is on\"", items["4"])
        self.assertIn("If Azure refuses the connection, or the read-back differs, stop.", items["5"])
        self.assertIn("the audience `https://azure-api.net/aigateway`", items["5"])
        self.assertIn("the action checks first, and stops before it deploys when it has not", items["6"])
        self.assertIn("`investigation.started` names the models `aigateway/gpt-6-luna` and `aigateway/gpt-6.1-sol`", items["7"])
        self.assertIn("A run of the Investigator that gives an answer is the proof that the route works.", items["7"])
        self.assertIn("the sentence of [rule 15 (c)](../AGENTS.md) about the agents is struck", items["8"])

    def test_the_end_of_the_list_of_actions_points_to_the_section_of_step_2(self):
        after = BOOTSTRAP.split("\n## After it\n")[1].split("\n## ")[0]
        self.assertIn("Its step 2, which sends the agents through it, is a constant that is True (the owner ordered the route on 2026-11-07, and it ran in Azure on 2026-11-08 and stopped at the Investigator's first call), "
                      "and its order is in [its own section](#added-on-2026-11-07-for-the-agents-route-through-the-ai-gateway-step-2).", after)
        self.assertLess(BOOTSTRAP.index("## Added on 2026-11-07 for the AI Gateway"), BOOTSTRAP.index(SECTION))
        self.assertLess(BOOTSTRAP.index(SECTION), BOOTSTRAP.index("\n## After it\n"))

    def test_rule_15_c_says_that_the_agents_route_is_on_in_code_and_ran_with_the_switch_true_and_that_the_judges_go_through_the_ai_gateway(self):
        (rule,) = [line for line in AGENTS.splitlines()
                   if line.lstrip().startswith("- **(c) Every model call of Meternaut goes through the AI Gateway, the governance hub of the Citadel design, with no direct path, not even for a test, unless the owner makes a written exception**")]
        self.assertIn("**The agents' route through the gateway is on in code and ran in Azure** (2026-11-07, the owner: \"Route [the agents] to the AI gateway ... IT NEEDS TO ADHERE TO THE CITADEL DESIGN PRINCIPLES\"): "
                      "the two agents of the investigation (rule 30) go through the gateway by step 2, the connection of the Foundry project to the gateway, which one line switches on "
                      "(`AGENTS_VIA_AI_GATEWAY` in `tools/environment-params.py`, True). The order of the real run is `aigateway`, about ten minutes, `foundry`, `cases`, `cases-run`; "
                      "it was made on 2026-11-08 and repeated after a first fix, and the Investigator was refused at its first call both times, because its model (gpt-6.1-sol) does not take function tools "
                      "together with a reasoning effort and does not take the effort none either. The Investigator is now gpt-6-luna with the effort `none` and the Skeptic gpt-6.1-sol, "
                      "and that fix has not been run, so no investigation has completed through the gateway yet", rule)
        self.assertIn("If gpt-6-luna refuses too, the agents cannot use the gateway until the Responses route is offered for it, and the owner decides.", rule)
        self.assertNotIn("the agents that are deployed still call the model deployments of their own Foundry resource", rule)
        self.assertNotIn("has not run in Azure", rule)
        self.assertIn("The way back is the line set to False and a run of `foundry` and `cases`; it is a direct route, so it needs the owner's written exception.", rule)
        self.assertIn("The Detective and the Skeptic call it with the cases app's own identity", rule)
        self.assertNotIn("One gap is left", rule)
        self.assertNotIn("False today", rule)
        self.assertNotIn("is not built", rule)
        self.assertNotIn("is not used either", rule)
        self.assertNotIn("the AI Gateway is not deployed", rule)
        self.assertEqual(rule.count("Planned end, 2026-11-07"), 0, "the planned end of the exception is gone with the exception: the governance-hub route ended on 2026-11-07")

    def test_the_routes_row_says_that_the_gateway_is_deployed_and_step_2_is_on_in_code_and_ran_with_the_switch(self):
        rows = [line for line in FOUNDRY_AGENTS.splitlines() if line.startswith("| **AI Gateway, Azure's separate service")]
        self.assertEqual(len(rows), 1)
        row = flat(rows[0])
        for words in ("(deployed; step 2 is on in code, the switch is True, and ran in Azure)",
                      "step 2 builds it behind one switch, `AGENTS_VIA_AI_GATEWAY` in `tools/environment-params.py`, which is True since the owner's order of 2026-11-07",
                      "The gateway is deployed (2026-11-07); the connection was made, and the Agent Service called the gateway's route on 2026-11-08, with answers that refused function tools for the Investigator's model, first together with a reasoning effort and then with the effort `none`.",
                      "the three outcomes of step 2 and the order of its real run",
                      "The real run of step 2 was made on 2026-11-08 and stopped at the Investigator's first call; the fix has not been run.",
                      "**Deployed on 2026-11-07 at the owner's written request; the Detective and the Skeptic of the cases app call it (they ran through it on 2026-11-08), and the agents are made with its model names "
                      "(the fix of the Investigator has not been run):** the one line that switches step 2 on is made"):
            self.assertIn(words, row, words)
        self.assertNotIn("Until the real run of step 2 has been made, the deployed agents call their own resource", row)
        self.assertNotIn("Not used since 2026-11-07", row)
        self.assertIn("`modelInvestigator` and `modelSkeptic` read `<connection>/<alias>`, for example `aigateway/gpt-6-luna`", FOUNDRY_AGENTS)
        self.assertIn("so an answer about the model, its reasoning effort or its function tools (the code `model_error`) is not sent again, and when the second answer says that `agent` is deprecated, the first answer is the one that is shown",
                      flat(FOUNDRY_AGENTS))
        self.assertNotIn("whatever it says", FOUNDRY_AGENTS)

    def test_the_readme_says_that_step_1_is_deployed_and_step_2_is_on_in_code_and_ran(self):
        rows = [line for line in README.splitlines() if line.startswith("| **[An AI Gateway for the agents](docs/proposals/08-ai-gateway.md)**")]
        (row,) = rows
        self.assertIn("step 2, the Foundry connection and a switch for the agents' model names, is on in code (the switch is True) and ran in Azure on 2026-11-08, twice at `cases-run`: the Investigator was refused at its first call both times, "
                      "because its model (gpt-6.1-sol) does not take function tools together with a reasoning effort and does not take the effort none either, and the fix (the Investigator on gpt-6-luna with the effort `none`, "
                      "the Skeptic on gpt-6.1-sol) has not been run", row)
        self.assertNotIn("so the deployed agents do not call through the gateway yet", row)
        (bullet,) = [line for line in README.splitlines() if line.startswith("- **An AI Gateway for every model call")]
        self.assertIn("step 2 for the agents is on in code and ran twice at `cases-run`, and its fix has not been run", bullet)
        self.assertNotIn("both steps are built and not deployed", bullet)
        self.assertIn("`AGENTS_VIA_AI_GATEWAY` in [`tools/environment-params.py`](tools/environment-params.py), that is True since the owner's order of 2026-11-07", bullet)
        self.assertIn("The order of the real run is `aigateway`, about ten minutes, `foundry`, `cases`, `cases-run`; it was made on 2026-11-08 and repeated after a first fix, and the Investigator was refused at its first call both times, "
                      "because its model (gpt-6.1-sol) does not take function tools together with a reasoning effort and does not take the effort none either. The Investigator is now gpt-6-luna with the effort `none` "
                      "and the Skeptic gpt-6.1-sol, and that fix has not been run", bullet)
        self.assertNotIn("until it has been made, the deployed agents keep calling their model deployments", bullet)
        self.assertNotIn("Not built: step 2", bullet)
        self.assertNotIn("that is False, so that nothing changes until the owner flips it", bullet)

    def test_the_changelog_has_the_entry_of_step_2_above_the_one_of_step_1_and_below_the_one_of_the_subnet_and_says_what_it_must(self):
        headings = re.findall(r"(?m)^## (.*)$", CHANGELOG)
        self.assertEqual(headings[7], "An AI Gateway for the agents' model calls, step 2 of 2: built, not deployed, and one switch that is False — 2026-11-07")
        self.assertEqual(headings[8], "An AI Gateway for the agents' model calls, step 1 of 2: built, not deployed — 2026-11-07")
        entry = CHANGELOG.split("\n## ")[8]
        leads = ["**What the owner said, and what this step is.**", "**The open question, and why this step exists.**", "**What is built.**", "**What was verified in sources on 2026-11-07, and what was not.**",
                 "**What was checked.**", "**Not checked.**", "**Who decides, and what a person does, in order.**"]
        positions = [entry.index(lead) for lead in leads]
        self.assertEqual(positions, sorted(positions))
        flat_entry = flat(entry)
        for words in ("I LEAN STRONG TOWARDS YOU CREATING AN AI GATEWAY", "**nothing changes until the owner flips one constant**", "no path for a key is built",
                      "Nothing is deployed: no Azure change, no Hub run and no workflow run was made, and the agents were not touched.", "**Not known, and not tried:**",
                      "None of it has run.", "The way back is the switch set to False and a run of `cases`; the connection, the project's role and the gateway stay"):
            self.assertIn(words, flat_entry, words)
        for placeholder in ("TOOLS_TOTAL", "TOOLS_NEW", "NNNN"):
            self.assertNotIn(placeholder, flat_entry, "the line about what was checked is written")
        checked = flat_entry.split("**What was checked.**")[1].split("**Not checked.**")[0]
        self.assertRegex(checked, r"\d,\d{3} tests", "and it says how many tests passed")
        self.assertIn("2,046", checked)
        self.assertIn("159", checked)


if __name__ == "__main__":
    unittest.main()
