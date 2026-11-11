"""The documents of the AI security: proposal 10 and the section of environment/BOOTSTRAP.md.

What they must say, that every check that the proposal names is a control of tools/drift-check.py, that the cost in it is the price times the number of alert rules of the template, and that the sentence
that the Hub prints when CI has not passed is the same in the page and in the workflow. Nothing here calls Azure."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def flat(source):
    return re.sub(r"\s+", " ", source)


PROPOSAL = text("docs/proposals/10-ai-security-and-governance.md")
BOOTSTRAP = text("environment/BOOTSTRAP.md")
README = text("README.md")
HUB = text(".github/workflows/deploy-hub.yml")
DRIFT_TOOL = text("tools/drift-check.py")
HEADING = "## Added on 2026-11-08 for the AI security (built, not deployed)"
REFUSAL = "The checks have not passed for this commit: push it and let CI finish, then run the Hub again"
PRICE_OF_A_LOG_ALERT_RULE = 0.4489


def section():
    return BOOTSTRAP.split(HEADING + "\n")[1].split("\n## ")[0]


def anchor(heading):
    slug = re.sub(r"[^\w\- ]", "", heading.lstrip("# ").strip().lower())
    return slug.replace(" ", "-")


class TheProposal(unittest.TestCase):
    def test_it_is_short_enough_and_linked_from_the_readme_and_the_bootstrap_page(self):
        self.assertLessEqual(len(PROPOSAL.split()), 2500)
        self.assertIn("(docs/proposals/10-ai-security-and-governance.md)", README)
        self.assertIn("(../docs/proposals/10-ai-security-and-governance.md)", section())
        self.assertIn(f"(../../environment/BOOTSTRAP.md#{anchor(HEADING)})", PROPOSAL)

    def test_it_names_the_proposal_of_the_harness_in_plain_text_until_that_page_exists(self):
        if not (ROOT / "docs" / "proposals" / "11-agent-harness-and-evaluation.md").exists():
            self.assertNotIn("](11-", PROPOSAL, "a link to a page that is not in this change breaks the check of the documents")
            self.assertIn("11-agent-harness-and-evaluation.md", PROPOSAL)

    def test_every_check_that_it_names_is_a_control_of_the_tool_and_every_control_is_named(self):
        controls = set(re.findall(r'@control\("(I-[a-z0-9-]+)"', DRIFT_TOOL))
        named = set(re.findall(r"\bI-[a-z0-9]+(?:-[a-z0-9]+)*\b", PROPOSAL))
        self.assertEqual(named - controls, set(), "a check that the page names and the tool does not have")
        self.assertEqual(controls - named, set(), "a control of the tool that the page does not say where a person sees it")

    def test_the_cost_is_the_price_times_the_alert_rules_of_the_template_and_it_is_far_from_the_line_of_the_owner(self):
        rules = len(list((ROOT / "environment" / "governance" / "alerts").glob("*.kql")))
        self.assertEqual(rules, 9)
        for words in ("Nine log alert rules", f"{PRICE_OF_A_LOG_ALERT_RULE} each", f"{rules * PRICE_OF_A_LOG_ALERT_RULE:.2f}", f"{(rules - 1) * PRICE_OF_A_LOG_ALERT_RULE:.2f}",
                      "About 4.0 euro a month", "50 euro a month at which the owner decides"):
            self.assertIn(words, PROPOSAL, words)
        self.assertLess(rules * PRICE_OF_A_LOG_ALERT_RULE, 50)

    def test_it_says_what_ran_in_azure_and_what_did_not_and_what_the_hub_no_longer_does(self):
        flat_proposal = flat(PROPOSAL)
        for words in ("built, deployed from the owner's machine and read back in Azure", "Every Hub run first reads that CI passed for its commit, so the Hub does not repeat the tests", "Ran in Azure 2026-11-07",
                      "no `drift.pass` or `drift.fail` line for 26 hours", "`drift.yml` has no timer until the identity exists", "`BUILD_COMMIT`", "`PACKAGE_SHA256`"):
            self.assertIn(words, flat_proposal, words)


class TheBootstrapSection(unittest.TestCase):
    def test_each_hand_step_is_in_the_table_and_has_its_own_paragraph(self):
        page = section()
        for step in ("G1", "G2", "G3", "G4", "G5"):
            self.assertIn(f"| {step} |", page, step)
            self.assertRegex(page, rf"(?m)^\*\*{step}: ", step)

    def test_the_read_only_identity_is_written_exactly(self):
        page = flat(section())
        for words in ("a user-assigned managed identity, `id-meternaut-drift`", "It is not the deploy identity", "exactly one, *Reader* (`acdd72a7-3385-48ef-bd42-f606fba81ae7`)",
                      "the project's resource group, the Foundry account of the agents and the AI Gateway", "No write role, no role at any other place", "a federated credential with the same issuer, subject"):
            self.assertIn(words, page, words)

    def test_the_timer_of_the_independent_check_waits_for_that_identity_and_the_lint_holds_it_back(self):
        page = flat(section())
        for words in ("`drift.yml` starts by hand only, with no `schedule:` line", "the constant `DRIFT_ON_A_TIMER`", "Until the variable `DRIFT_CLIENT_ID` is set, the first step of a run stops it"):
            self.assertIn(words, page, words)

    def test_agent_365_and_entra_agent_id_are_portal_steps_and_nothing_here_writes_the_flag(self):
        page = flat(section())
        for words in ("Global Administrator", "Microsoft 365 admin center", "Microsoft Entra admin center under Agent identities", "no step here writes it", "Without that consent the flag is on and nothing arrives"):
            self.assertIn(words, page, words)

    def test_what_the_hub_no_longer_does_is_said_with_the_sentence_it_prints_and_the_reason(self):
        page = flat(section())
        for words in ("**What the Hub no longer does, and why.**", REFUSAL, "`actions: read`", "about five of the eight minutes", "[rule 35](../AGENTS.md)", "The way back is to put the two test commands back",
                      "a head with that marker has no run to find"):
            self.assertIn(words, page, words)
        self.assertIn(f"::error::{REFUSAL}.", HUB, "the sentence that the Hub prints is the one that the page quotes")

    def test_the_order_of_the_actions_starts_with_the_ci_of_the_merge_commit(self):
        page = flat(section())
        order = page.split("**The order.**")[1].split("**Going back.**")[0]
        positions = [order.index(f"({n})") for n in range(1, 9)]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("the CI run of the merge commit on `main` has to pass", order)
        self.assertLess(order.index("`base`"), order.index("`cases`"))
        self.assertLess(order.index("`gateway-telemetry`"), order.index("`governance`"))
        self.assertLess(order.index("`governance`"), order.index("`drift-check`"))


if __name__ == "__main__":
    unittest.main()
