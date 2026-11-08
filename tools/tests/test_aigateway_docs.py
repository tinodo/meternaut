"""The documents of the AI Gateway (step 1): what they say about the public frontend, the order of the actions, the rule that records the planned end of the exception, and the one hand step.

The hand step is run the way the other two are (test_workflow_scripts.py): in every PowerShell on the machine, against a stand-in for az, with the commands that a person would copy out of
environment/BOOTSTRAP.md. The template, the workflow actions and the tools have tests of their own (test_aigateway_template.py, test_aigateway_workflow.py, test_aigateway_prep.py,
test_aigateway_check.py)."""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS_USER = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"
DATAPLANE = "18550318-e177-4205-a743-6816d6fcdc3f"


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def flat(source):
    return re.sub(r"\s+", " ", source)


PROPOSAL = flat(text("docs/proposals/08-ai-gateway.md"))
BOOTSTRAP = text("environment/BOOTSTRAP.md")
AGENTS = text("AGENTS.md")
FOUNDRY_AGENTS = text("docs/proposals/06-foundry-agents.md")
CHANGELOG = text("CHANGELOG.md")
README = text("README.md")
SECTION = "## Added on 2026-11-07 for the AI Gateway"


def section_of_bootstrap():
    return BOOTSTRAP.split(SECTION)[1].split("\n## ")[0]


class TheDecisionRecord(unittest.TestCase):
    def test_it_says_plainly_that_the_frontend_is_public_only_and_that_the_owner_decides_before_anything_is_deployed(self):
        for words in ("The owner believed that the gateway can be made private. It cannot, today.", "The service has no private endpoint.",
                      "He decides whether to accept it before anything is deployed, and he did, in writing, on 2026-11-07", "Create the AI Gateway with public network access and private routing.",
                      "Had he not, the gateway would not have been made, and nothing would have been lost: the agents would have kept calling their own resource",
                      "AIGatewayPrivateEndpointsNotEnabled", "Reported with this change; not read again here", "Only the way from the gateway to the Foundry resource can be private",
                      "That breaks the rule of [private by default]"):
            self.assertIn(words, PROPOSAL, words)
        self.assertRegex(PROPOSAL, r"\*\*Status: .*Step 1 of 2 is deployed and checked.*Step 2 of 2 is built and on in code, and it ran in Azure on 2026-11-08.*the fix, the Investigator on gpt-5.5, a third model of the gateway, has not been run.*The Detective and the Skeptic of the cases app call the gateway, and ran through it in those runs",
                         "the status at the top says what is true")

    def test_it_lists_what_protects_the_public_endpoint_and_what_is_not_done_and_why(self):
        for words in ("1. **Microsoft Entra ID, and a role.**", "2. **No API key resource.**", "3. **Limits at the gateway.**", "4. **Content safety at the gateway,**",
                      "The service makes a key named `master` on every gateway and has no switch to refuse key authentication.",
                      "If the service refuses, that is a recorded finding and not a failure: the key then exists and is unused.",
                      "**No `ipFilter`.**", "Microsoft publishes no service tag and no address range for the Foundry Agent Service", "so a list that admits the agents cannot be made",
                      "**No private endpoint.**", "**No DDoS protection plan.** The owner said not to make one."):
            self.assertIn(words, PROPOSAL, words)

    def test_it_says_what_the_gateway_adds_to_ai_security_and_what_it_does_not_and_the_layers_stay(self):
        for words in ("It does not add Prompt Shields.", "The gateway has no policy for jailbreak or indirect-attack detection.", "The guardrail `meternaut-agents` stays where it is, on the model deployments",
                      "Foundry's agent-level guardrails are not supported for connected models (Learn)",
                      "| Limits and content safety | The AI Gateway |", "| Guardrail with Prompt Shields | The model deployments |", "| Typed read-only tools | The cases app's code |",
                      "| Checks in code ([rule 30 (b)](../../AGENTS.md)) | The cases app's code |"):
            self.assertIn(words, PROPOSAL, words)

    def test_it_states_the_cost_and_the_terms_of_a_preview(self):
        for words in ("One meter, \"10k AI Gateway Requests\"", "0.00 US dollars in Sweden Central", "free during public preview", "A preview has no service level and its terms may change"):
            self.assertIn(words, PROPOSAL, words)

    def test_it_names_the_three_outcomes_of_step_2_and_who_decides_each(self):
        for words in ("| It works without a key |", "The part of [rule 15 (c)](../../AGENTS.md) that is not proved yet ends", "The owner reads the proof, and the record of the run is written", "| It needs a key |", "[Rule 23](../../AGENTS.md) says no key",
                      "| It fails (the Agent Service cannot call the gateway, or Responses is not supported) |", "The investigation does not run, and the History says why. The way back makes the agents call their deployments again",
                      "The subnet cannot be changed", "delete the gateway and make another"):
            self.assertIn(words, PROPOSAL, words)

    def test_the_order_of_the_actions_is_the_same_in_the_record_and_on_the_bootstrap_page(self):
        self.assertIn("**The order of the actions:** `foundry` and `cases` have run, and `operator` has. Then `aigateway`. Wait about ten minutes, because a new role takes up to that long to apply. Then `aigateway-check`.", PROPOSAL)
        order = flat(section_of_bootstrap().split("**The order.**")[1].split("**Going back.**")[0])
        positions = [order.index(f"`{name}`") for name in ("foundry", "cases", "operator", "aigateway")] + [order.index("`aigateway-check`")]
        self.assertEqual(positions, sorted(positions), "foundry, cases and operator, then aigateway, then aigateway-check")
        self.assertIn("About ten minutes later, because a new role takes up to that long to apply, `aigateway-check`.", order)

    def test_the_numbers_of_the_record_are_the_numbers_of_the_file_of_limits(self):
        policies = json.loads(text("environment/aigateway/policies.json"))
        by_type = {}
        for policy in policies:
            by_type.setdefault(policy["type"], []).append(policy)
        (token,), (rate,) = by_type["tokenLimit"], by_type["requestRateLimit"]
        costs = {cost["period"]: cost["amount"] for cost in by_type["costLimit"]}
        self.assertEqual((token["count"], token["period"], rate["callsPerPeriod"], rate["periodSeconds"], costs), (50000, "minute", 60, 60, {"day": 5, "month": 25}))
        self.assertIn("50,000 tokens a minute", PROPOSAL)
        self.assertIn("60 requests a minute", PROPOSAL)
        self.assertIn("5 US dollars a day and 25 US dollars a month", PROPOSAL)
        self.assertIn("Each limit counts for every caller identity alone.", PROPOSAL)

    def test_the_sources_that_it_relies_on_are_named(self):
        sources = PROPOSAL.split("## Sources, read on 2026-11-07")[1]
        for words in ("Azure/azure-rest-api-specs", "Azure/aigateway", "MicrosoftDocs/azure-docs", "Bring your own model to Foundry Agent Service", "Azure Retail Prices API"):
            self.assertIn(words, sources, words)


class TheOtherDocuments(unittest.TestCase):
    def test_the_bootstrap_section_has_one_block_of_commands_the_decision_of_the_owner_and_the_service_principal_to_read_first(self):
        section = section_of_bootstrap()
        self.assertEqual(len(re.findall(r"```powershell\n", section)), 1, "one hand step with commands; the one about the service principal is read first and is not a block")
        for words in ("**The decision of the owner: the frontend is public.**", "or the gateway is not made", "It is break-glass ([rule 18](../AGENTS.md))", "Nothing is written until the person types `yes`.",
                      f"`az ad sp show --id {DATAPLANE}`", f"`az ad sp create --id {DATAPLANE}`", "The workflow's identity holds no right in the directory and gets none ([rules 18 and 24](../AGENTS.md)), so no action does it.",
                      "stops with a clear message when the id is not in it", "No action deletes the gateway"):
            self.assertIn(words, flat(section), words)
        self.assertIn(MODELS_USER, section)

    def test_the_top_of_the_bootstrap_page_counts_the_roles_that_the_condition_will_hold(self):
        top = BOOTSTRAP.split("\n## ")[0] + BOOTSTRAP.split("\n## ")[1]
        self.assertRegex(top, r"one of nine roles")
        self.assertIn("A tenth, *AI Gateway Models User*", top)
        self.assertIn("was added by hand on 2026-11-07", top)
        self.assertIn("except the nine above (and the tenth, [for the AI Gateway](#added-on-2026-11-07-for-the-ai-gateway), whose hand step was done on 2026-11-07)", BOOTSTRAP)
        self.assertIn("lists eight roles and Reader is not one of them", BOOTSTRAP, "the sentence of 2026-11-06 about the Operator is a record, and it is left as it was")

    def test_the_bootstrap_page_names_the_two_actions_after_the_order_of_the_others(self):
        after = BOOTSTRAP.split("\n## After it\n")[1].split("\n## ")[0]
        self.assertIn("The AI Gateway has two actions, `aigateway` and `aigateway-check`, and they are not on that list either", after)
        self.assertLess(after.index("The console behind the platform's Application Gateway is not on that list"), after.index("The AI Gateway has two actions"))

    def test_rule_15_c_says_that_every_model_call_goes_through_the_ai_gateway_with_no_direct_path_and_keeps_its_history_in_one_sentence(self):
        (rule,) = [line for line in AGENTS.splitlines()
                   if line.lstrip().startswith("- **(c) Every model call of Meternaut goes through the AI Gateway, the governance hub of the Citadel design, with no direct path, not even for a test, unless the owner makes a written exception**")]
        for words in ("(2026-11-07, the owner, in capitals: \"IT NEEDS TO ADHERE TO THE CITADEL DESIGN PRINCIPLES\")",
                      "The AI Gateway is Azure's separate service ([the decision record](docs/proposals/08-ai-gateway.md), which also says how it meets the Citadel principles and what is still missing)",
                      "it has been deployed since 2026-11-07, because the owner asked for it in writing (\"Create the AI Gateway with public network access and private routing.\")",
                      "The Detective and the Skeptic call it with the cases app's own identity and a Microsoft Entra token for its audience, and no key, and the app's list of allowed calls holds no chat completion to the Foundry resource or to its project.",
                      "*History:* through API Management until the owner ordered its removal on 2026-11-07, then direct to the Foundry project for a few hours the same day, now through the AI Gateway.",
                      "**The agents' route through the gateway is on in code and ran in Azure** (2026-11-07, the owner: \"Route [the agents] to the AI gateway ... IT NEEDS TO ADHERE TO THE CITADEL DESIGN PRINCIPLES\"): "
                      "the two agents of the investigation (rule 30) go through the gateway by step 2",
                      "(`AGENTS_VIA_AI_GATEWAY` in `tools/environment-params.py`, True)", "A request that carries no prompt, or that the model service refuses before it runs a model, is not a model call"):
            self.assertIn(words, rule, words)
        for old in ("goes direct, privately and with no key", "**nothing calls through it**", "This ends the \"governance hub\" route", "Planned end, 2026-11-07", "**Exception, 2026-11-06", "is not used either", "the AI Gateway is not deployed"):
            self.assertNotIn(old, rule, old)

    def test_the_routes_table_of_the_foundry_agents_has_the_new_row_last_and_every_old_row_is_still_there(self):
        table = [line for line in FOUNDRY_AGENTS.splitlines() if line.startswith("| **")]
        firsts = [line.split("|")[1].strip() for line in table]
        old = ["**Agents call their own resource (built)**", "**Foundry's API Management connection, with Microsoft Entra authentication**", "**Foundry's generic model-gateway connection**", "**Move the gateway to Standard v2**"]
        for row in old:
            self.assertIn(row, firsts, "a row of the table is not deleted")
        self.assertEqual(firsts[-1], "**AI Gateway, Azure's separate service (deployed; step 2 is on in code, the switch is True, and ran in Azure)**")
        self.assertEqual([first for first in firsts if first in old], old, "the old rows keep their order")
        last = flat(table[-1])
        for words in ("`Microsoft.ApiManagement/aigateways`", "not an API Management instance", "no key", "not known, and step 2", "I LEAN STRONG TOWARDS YOU CREATING AN AI GATEWAY",
                      "Its frontend is public only", "`10k AI Gateway Requests`", "no service level", "(08-ai-gateway.md)", "The real run of step 2 was made on 2026-11-08, three times at `cases-run`, and stopped at the Investigator's first call each time"):
            self.assertIn(words, last, words)

    def test_the_changelog_has_the_entry_of_step_1_above_the_console_entry_and_says_what_it_must(self):
        headings = re.findall(r"(?m)^## (.*)$", CHANGELOG)
        self.assertEqual(headings[9], "An AI Gateway for the agents' model calls, step 1 of 2: built, not deployed — 2026-11-07")
        self.assertTrue(headings[10].startswith("The console behind the platform's Application Gateway"), "the entry of the console change follows, as the owner's coordinator asked")
        entry = flat(CHANGELOG.split("\n## ")[10])
        for words in ("**What the owner said.**", "I LEAN STRONG TOWARDS YOU CREATING AN AI GATEWAY", "You should NOT create a DDOS PLAN.", "**What the owner has to know first: the frontend is public, and he decides whether to accept that.**",
                      "**What is built.**", "Nothing is deployed: no Azure change, no Hub run and no workflow run was made", "**What was checked.**", "**Not checked.**", "**What a person has to do, in order.**",
                      "That is an exception to the rule of [private by default]", "Microsoft publishes no address range and no service tag for the Foundry Agent Service"):
            self.assertIn(words, entry, words)
        self.assertFalse("NNNN" in entry, "the line about what was checked is written")
        self.assertRegex(entry.split("**What was checked.**")[1].split("**Not checked.**")[0], r"\d,\d{3} tests", "and it says how many tests passed")

    def test_the_readme_lists_the_record_in_its_table_and_in_its_status(self):
        rows = [line for line in README.splitlines() if line.startswith("| **[An AI Gateway for the agents](docs/proposals/08-ai-gateway.md)**")]
        self.assertEqual(len(rows), 1)
        self.assertIn("is on in code (the switch is True) and ran in Azure on 2026-11-08", rows[0])
        self.assertIn("is deployed and checked since 2026-11-07", rows[0])
        bullets = [line for line in README.splitlines() if line.startswith("- **An AI Gateway for every model call (deployed on 2026-11-07; the Detective and the Skeptic call it and ran through it on 2026-11-08; step 2 for the agents is on in code and ran three times at `cases-run`, and its fix has not been run)**")]
        self.assertEqual(len(bullets), 1)
        self.assertIn("The owner believed that the gateway can be private. It cannot", bullets[0])
        self.assertLess(README.index("| **[Private by default](docs/proposals/07-private-by-default.md)**"), README.index(rows[0]), "the new row follows the row of the record before it")


def load_the_workflow_script_tests():
    """test_workflow_scripts.py by its path: the hand-step harness (the stand-in for az, the list of PowerShells and the way to run them) is there, and the tests are run one folder up or down."""
    spec = importlib.util.spec_from_file_location("workflow_scripts_of_the_aigateway_docs_tests", ROOT / "tools" / "tests" / "test_workflow_scripts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TWS = load_the_workflow_script_tests()
# What the condition lists once the two hand steps before this one are done: the first seven roles, Foundry User and Reader.
BEFORE = TWS.CONDITION_ROLES + [TWS.FOUNDRY_USER, TWS.READER]


def models_user_hand_step_script():
    """The commands of the hand step of the AI Gateway in environment/BOOTSTRAP.md, as a person would copy them."""
    (script,) = re.findall(r"```powershell\n(.*?)\n```", section_of_bootstrap(), re.S)
    return script


class TheModelsUserHandStep(unittest.TestCase):
    """The commands of the section that add the AI Gateway Models User role to the condition of the deploy identity's assignment: the stand-in for az and the harness of the two hand steps before it,
    so that what is tested is what a person would paste."""

    run_step = TWS.TheFoundryUserHandStep.run_step
    said = TWS.TheFoundryUserHandStep.said
    kinds = TWS.TheFoundryUserHandStep.kinds
    first_engine = TWS.TheFoundryUserHandStep.first_engine

    @classmethod
    def setUpClass(cls):
        cls.engines = TWS.powershells()
        if not cls.engines:
            raise unittest.SkipTest("no PowerShell on this machine")
        first, cls.rest = models_user_hand_step_script().split("\n", 1)
        assert first.startswith("function az {"), "the first line of the commands is the az function, which the stand-in replaces"

    def current(self):
        return TWS.assignment(TWS.condition_of(BEFORE))

    def test_the_role_that_it_adds_is_the_one_of_the_template_and_of_the_action_and_the_condition_does_not_hold_it_yet(self):
        self.assertIn(f"$modelsUser = '{MODELS_USER}'", models_user_hand_step_script())
        self.assertIn(f"var aiGatewayModelsUserRoleId = '{MODELS_USER}'", text("environment/aigateway/main.bicep"))
        self.assertIn(f"models_user={MODELS_USER}", text(".github/workflows/deploy-hub.yml"))
        self.assertNotIn(MODELS_USER, BEFORE)

    def test_a_good_run_changes_the_condition_in_place_with_one_write_adds_the_role_to_both_lists_and_reads_it_back(self):
        for name, engine in self.engines:
            with self.subTest(engine=name):
                done, calls, left = self.run_step(engine, [self.current()])
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(self.kinds(calls), ["role assignment list"] * 2 + ["role assignment update"] + ["role assignment list"] * 2, "read, read, one write, read back, read back")
                (update,) = [call for call in calls if call[2] == "update"]
                sent = json.loads(update[6].replace('""', '"'))
                self.assertEqual(sent["id"], TWS.HAND_ASSIGNMENT, "the assignment that is changed is the one that was read")
                (stored,) = left
                self.assertEqual(stored["id"], TWS.HAND_ASSIGNMENT, "the assignment keeps its id")
                self.assertEqual(TWS.id_lists(stored["condition"]), [sorted(BEFORE + [MODELS_USER])] * 2, "the role is in the list for a write and in the list for a delete, and no id was lost")
                self.assertEqual(TWS.shape_of(stored["condition"]), TWS.shape_of(self.current()["condition"]), "nothing else of the condition changed")
                text_said = self.said(done)
                self.assertIn("PROMPT: Change the condition as shown? Type yes", text_said)
                self.assertIn(f"Added: {MODELS_USER} (AI Gateway Models User)", text_said)
                self.assertIn(f"Read back: one assignment, with the same id, and both lists hold the old role ids and {MODELS_USER} (AI Gateway Models User).", text_said)
                self.assertFalse([call for call in calls if call[2] in ("delete", "create")], "the commands never delete or make an assignment")

    def test_an_update_that_fails_says_that_the_assignment_is_unchanged_and_nothing_is_written_without_a_yes(self):
        before = [self.current()]
        done, calls, left = self.run_step(self.first_engine(), before, FAKE_UPDATE_FAILS="1")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("The update failed (exit code 1). It is one write and nothing else was done, so the assignment is unchanged.", self.said(done))
        self.assertEqual((self.kinds(calls)[-1], left), ("role assignment update", before))
        done, calls, left = self.run_step(self.first_engine(), before, answer="no")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Stopped. Nothing was changed.", self.said(done))
        self.assertEqual((self.kinds(calls), left), (["role assignment list"] * 2, before))

    def test_a_condition_that_lists_the_role_already_means_nothing_to_do_and_a_read_back_that_differs_fails(self):
        done, calls, _ = self.run_step(self.first_engine(), [TWS.assignment(TWS.condition_of(BEFORE + [MODELS_USER]))])
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("The condition lists the AI Gateway Models User role already: nothing to do.", self.said(done))
        self.assertEqual(self.kinds(calls), ["role assignment list"] * 2)
        done, calls, _ = self.run_step(self.first_engine(), [self.current()], FAKE_STORE_CONDITION=TWS.condition_of(BEFORE))
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("not as meant", self.said(done))
        self.assertEqual(self.kinds(calls).count("role assignment update"), 1)

    def test_nothing_is_written_when_there_is_not_exactly_one_assignment_or_the_condition_is_not_the_one_of_the_templates(self):
        for label, assignments, words in (("none", [], "the list says '0'"), ("two", [self.current(), TWS.assignment(TWS.condition_of(BEFORE), id=TWS.HAND_ASSIGNMENT + "-2")], "the list says '2'"),
                                          ("the two lists differ", [TWS.assignment(TWS.condition_of(BEFORE, BEFORE[:-1]))], "two lists of the same role ids")):
            with self.subTest(label=label):
                done, calls, left = self.run_step(self.first_engine(), assignments)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn(words, self.said(done))
                self.assertFalse([call for call in calls if call[2] == "update"])
                self.assertEqual(left, assignments)
