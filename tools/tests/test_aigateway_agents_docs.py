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
    def test_the_status_says_that_step_1_is_deployed_step_2_is_built_and_not_deployed_the_switch_is_false_and_the_question_is_open(self):
        status = re.search(r"\*\*Status: .*?\*\* This page records", PROPOSAL).group(0)
        for words in ("Step 1 of 2 is deployed and checked", "Step 2 of 2 is built and not deployed", "`AGENTS_VIA_AI_GATEWAY` in `tools/environment-params.py`, that is False",
                      "so that nothing changes until the owner flips it", "Nothing calls through the gateway, and the agents were not touched.",
                      "Whether the connection can call the gateway with the project's own managed identity and no key is not known, and it was not tried"):
            self.assertIn(words, status, words)
        self.assertNotIn("is not built", status)
        for old in ("Step 1 of 2 is built and not deployed", "not deployed too", "Nothing was made in Azure"):
            self.assertNotIn(old, status, old)

    def test_the_section_of_step_2_has_its_parts_in_order(self):
        headings = re.findall(r"(?m)^(##+ .*)$", PROPOSAL_TEXT)
        wanted = [STEP_2, "### The order of the real run", "### What each failure means", "### The way back from step 2", "### Choices of step 2 that the owner can change"]
        positions = [headings.index(heading) for heading in wanted]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(wanted))), "the parts follow one another")
        self.assertLess(headings.index("## Step 2 and what is not known about it"), positions[0])
        self.assertLess(positions[-1], headings.index("## The way back"), "the section of step 2 comes before the way back of the gateway")

    def test_it_says_that_nothing_changes_until_the_switch_is_flipped_and_what_the_switch_does_in_each_action(self):
        section = flat(step_2_of_the_record())
        for words in ("**Nothing changes until the owner flips one constant.**", "`AGENTS_VIA_AI_GATEWAY = False`", "next to `CASES_APP_PUBLIC_NETWORK_ACCESS`",
                      "after the owner's yes and after `aigateway` and `aigateway-check` have passed on the real estate",
                      "the parameter files, the templates and every action are what they were", "the same byte for byte, and that the new parameters are empty or false",
                      "**`foundry` makes the connection `aigateway`**", "reads it back with GET only", "no credential held",
                      "**`aigateway` gives the Foundry project's identity *AI Gateway Models User***", "**`cases` gives the app the model names `aigateway/gpt-6.1-sol` and `aigateway/gpt-6-luna`,**",
                      "exactly `<name>` or `<name>/<name>`", "The builder refuses True when it cannot name the gateway."):
            self.assertIn(words, section, words)

    def test_it_says_what_the_connection_is_and_that_its_shape_is_not_tried_and_that_no_key_path_is_built(self):
        section = flat(step_2_of_the_record())
        for words in ("Category `ApiManagement`, `authType` `ProjectManagedIdentity`, `audience` `https://azure-api.net/aigateway`, target `https://<host>/default/models/openai/v1`, empty `credentials`, "
                      "`isSharedToAll` false", "`deploymentInPath` `false`", "a static `models` list whose names are the aliases", "**The shape comes from the samples and from Learn and has not been tried**",
                      "No key is used, and no path for a key is built: if the connection needs a key, the owner decides ([rule 23](../../AGENTS.md)).",
                      "Responses routing for the AI Gateway tier is \"coming soon\" in Learn, and it is not asked for."):
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
        self.assertIn("the owner's yes and the change of one line that sets the switch to True", sentence)
        self.assertIn("about ten minutes", sentence)

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
        for words in ("Set the switch back to False", "run `cases`", "**What stays:** the connection `aigateway` in the project, the role of the project's identity on the gateway, and the gateway.",
                      "The deployment is incremental", "does not delete the connection, and no action deletes the role", "A person deletes the connection by hand"):
            self.assertIn(words, part, words)

    def test_the_table_of_what_is_known_has_the_rows_of_step_2_and_marks_the_connection_as_not_tried(self):
        table = PROPOSAL.split("## What is verified, what is inferred, what is not known")[1].split("## The frontend is public only")[0]
        for words in ("| Whether a Foundry project's connection can use its managed identity to call this gateway | **Not known; step 2 is built to find out, and has not run** |",
                      "| Inferred, **not tried** |", "| An agent names its model `<connection>/<model>`, and a wrong name is answered with \"model not found\" | Verified |",
                      "| Whether the service takes the category `ApiManagement` with a managed identity for a target that is not `*.azure-api.net` | **Not known** |",
                      "| Whether the Agent Service then calls the gateway with a token of the project's identity", "| What the Agent Service answers when the gateway refuses a call: the status, the code and the words | **Not known** |",
                      "| Whether the Agent Service reports token usage for a model behind a connection | **Not known** |",
                      "| Whether the optional version of a model in the connection's list is added to the model name in the call | **Not known** |",
                      "| That the gateway is reachable from the managed inference plane of the Agent Service | Inferred |"):
            self.assertIn(words, table, words)

    def test_the_part_of_the_record_that_is_about_step_2_holds_no_key_no_address_of_the_owner_and_no_guid(self):
        section = step_2_of_the_record()
        self.assertNotRegex(section.lower(), r"another-project|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        for word in ("api-key", "listSecrets", "primaryKey", "connection string", "bearer"):
            self.assertNotIn(word.lower(), section.lower(), word)


class TheOtherDocumentsOfStep2(unittest.TestCase):
    def test_the_bootstrap_section_has_the_order_what_is_not_known_and_the_way_back(self):
        section = flat(section_of_bootstrap())
        for words in ("**Built, not deployed, and not tried.**", "Step 2 adds no action and no hand step.", "`AGENTS_VIA_AI_GATEWAY = False` in [`tools/environment-params.py`](../tools/environment-params.py)",
                      "No Azure change was made and no Hub run was made for step 2.", "**What the constant does when it is True.**", "No key is used and none is built: if the connection needs one, the owner decides ([rule 23](../AGENTS.md)).",
                      "**What is not known.**", "**The order.**", "**Going back.**", "**What stays:** the connection `aigateway` in the Foundry project",
                      "the deployment is incremental, so a later `foundry` run does not delete it", "no action does it"):
            self.assertIn(words, section, words)
        self.assertLess(section.index("**What is not known.**"), section.index("**The order.**"))
        self.assertLess(section.index("**The order.**"), section.index("**Going back.**"))
        self.assertEqual(len(re.findall(r"```", section_of_bootstrap())), 0, "no hand step and so no block of commands")

    def test_the_bootstrap_section_says_what_to_read_in_each_step_and_when_to_stop(self):
        items = {number: flat(item) for number, item in re.findall(r"(?m)^(\d+)\. (.*)$", section_of_bootstrap())}
        self.assertIn("Read: the gateway, its subnet, its models and aliases, the limits, and who holds the role (the Operator only).", items["1"])
        self.assertIn("every alias answered with HTTP 200 and usage numbers, the call with no token answered 401, and the call with a wrong alias refused", items["2"])
        self.assertIn("A change of one line sets `AGENTS_VIA_AI_GATEWAY = True`, and it is reviewed and merged like any other change.", items["3"])
        self.assertIn("\"The switch of the agents' route is on\"", items["4"])
        self.assertIn("If Azure refuses the connection, or the read-back differs, stop.", items["5"])
        self.assertIn("the audience `https://azure-api.net/aigateway`", items["5"])
        self.assertIn("the action checks first, and stops before it deploys when it has not", items["6"])
        self.assertIn("`investigation.started` names the models `aigateway/gpt-6.1-sol` and `aigateway/gpt-6-luna`", items["7"])
        self.assertIn("A run of the Investigator that gives an answer is the proof that the route works.", items["7"])
        self.assertIn("decides whether to strike the exception of [rule 15 (c)](../AGENTS.md)", items["8"])

    def test_the_end_of_the_list_of_actions_points_to_the_section_of_step_2(self):
        after = BOOTSTRAP.split("\n## After it\n")[1].split("\n## ")[0]
        self.assertIn("Its step 2, which sends the agents through it, is a constant that is False, and its order is in [its own section](#added-on-2026-11-07-for-the-agents-route-through-the-ai-gateway-step-2).", after)
        self.assertLess(BOOTSTRAP.index("## Added on 2026-11-07 for the AI Gateway"), BOOTSTRAP.index(SECTION))
        self.assertLess(BOOTSTRAP.index(SECTION), BOOTSTRAP.index("\n## After it\n"))

    def test_rule_15_c_says_that_step_2_is_built_and_off_and_the_switch_is_false_and_the_ai_gateway_is_deployed_and_nothing_calls_through_it(self):
        (rule,) = [line for line in AGENTS.splitlines() if line.lstrip().startswith("- **(c) Every model call of Meternaut goes direct, privately and with no key, to the model deployments of its own Foundry project**")]
        self.assertIn("has been deployed since 2026-11-07, because the owner asked for it in writing (\"Create the AI Gateway with public network access and private routing.\"), and **nothing calls through it**: "
                      "step 2, which gives the project a connection to it and the agents the model names `aigateway/<alias>`, is built and off (`AGENTS_VIA_AI_GATEWAY` is False) and needs the owner's separate yes, "
                      "so until it is switched on every model call goes direct, as this rule says.", rule)
        self.assertNotIn("is not built", rule)
        self.assertNotIn("is not used either", rule)
        self.assertNotIn("the AI Gateway is not deployed", rule)
        self.assertEqual(rule.count("Planned end, 2026-11-07"), 0, "the planned end of the exception is gone with the exception: the governance-hub route ended on 2026-11-07")

    def test_the_routes_row_says_that_the_gateway_is_deployed_and_step_2_is_built_and_off_with_the_switch(self):
        rows = [line for line in FOUNDRY_AGENTS.splitlines() if line.startswith("| **AI Gateway, Azure's separate service")]
        self.assertEqual(len(rows), 1)
        row = flat(rows[0])
        for words in ("(deployed; step 2 is built and off, the switch is False)", "step 2 builds it behind one switch, `AGENTS_VIA_AI_GATEWAY` in `tools/environment-params.py`, which is False",
                      "The gateway is deployed (2026-11-07); the connection is built, not deployed and not tried", "the three outcomes of step 2 and the order of its real run",
                      "Until step 2 has run, the agents call their own resource, as in the first row", "**Deployed on 2026-11-07 at the owner's written request, and not used yet:** no call goes through it"):
            self.assertIn(words, row, words)
        self.assertNotIn("Not used since 2026-11-07", row)
        self.assertIn("`modelInvestigator` and `modelSkeptic` read `<connection>/<alias>`, for example `aigateway/gpt-6.1-sol`", FOUNDRY_AGENTS)

    def test_the_readme_says_that_step_1_is_deployed_and_step_2_is_built_and_not_deployed(self):
        rows = [line for line in README.splitlines() if line.startswith("| **[An AI Gateway for the agents](docs/proposals/08-ai-gateway.md)**")]
        (row,) = rows
        self.assertIn("step 2, the Foundry connection and a switch for the agents' model names, is built and not deployed, and the switch is False, so nothing calls through the gateway yet", row)
        (bullet,) = [line for line in README.splitlines() if line.startswith("- **An AI Gateway for the agents' model calls")]
        self.assertIn("step 2 is built and off", bullet)
        self.assertNotIn("both steps are built and not deployed", bullet)
        self.assertIn("`AGENTS_VIA_AI_GATEWAY` in [`tools/environment-params.py`](tools/environment-params.py), that is False, so that nothing changes until the owner flips it", bullet)
        self.assertNotIn("Not built: step 2", bullet)

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
