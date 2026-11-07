"""The records of 2026-11-07 about the AI Gateway: it is deployed and checked, nothing calls through it yet, and step 2 is still off.

The owner asked in writing for the gateway ("Create the AI Gateway with public network access and private routing."), the actions `aigateway` and `aigateway-check` ran, and the changelog says what they made,
proved and found. These tests hold the newest changelog entry, the switch that is still False and the pages that used to say "not deployed" to one story. They call neither Azure nor GitHub."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TITLE = "The AI Gateway is deployed and checked, and nothing calls through it yet — 2026-11-07"
REQUEST = "Create the AI Gateway with public network access and private routing."
GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def flat(source):
    return re.sub(r"\s+", " ", source)


CHANGELOG = text("CHANGELOG.md")
ENTRY = CHANGELOG.split("\n## ")[3]
RECORD = flat(text("docs/proposals/08-ai-gateway.md"))


class TheChangelogEntry(unittest.TestCase):
    def test_it_is_the_entry_under_the_newest_one_which_is_the_estate_wide_watch_and_has_at_most_twelve_lines(self):
        headings = re.findall(r"(?m)^## (.*)$", CHANGELOG)
        self.assertTrue(headings[1].startswith("The Watch reads every subscription that its identity can read"), "the entry of 2026-11-07 about the estate-wide Watch follows the newest, the entry of the web page")
        self.assertEqual(headings[2], TITLE)
        self.assertTrue(ENTRY.startswith(TITLE))
        self.assertLessEqual(len(ENTRY.strip().splitlines()), 12, "the owner reads nothing long")

    def test_it_says_what_the_owner_asked_what_was_made_what_was_proved_what_was_found_and_what_is_not_done(self):
        entry = flat(ENTRY)
        leads = ["**What the owner asked.**", "**What was made.**", "**What was proved.**", "**What was found.**", "**Not done, and cost.**"]
        positions = [entry.index(lead) for lead in leads]
        self.assertEqual(positions, sorted(positions))
        for words in (f'"{REQUEST}"', "no public endpoints unless specifically requested", "I LEAN STRONG TOWARDS YOU CREATING AN AI GATEWAY",
                      "in another subscription, is not touched", "Hub run 42390204642", "`public_ai_gateway_requested` set", "the wait for the landing zone's route table passed",
                      "state Succeeded, SKU Standard", "`publicNetworkAccess` reported Enabled", "backend subnet `snet-aigw` (private routing)", "a system-assigned identity",
                      "the provider `foundry` (managed identity, no key)", "two models and two aliases (`gpt-6-luna`, `gpt-6.1-sol`) with content safety at Medium",
                      "50,000 tokens and 60 requests a minute, 5 US dollars a day and 25 a month, for each caller", "the built-in key deleted",
                      "*AI Gateway Models User* for the Operator and *Foundry User* for the gateway's identity", "Hub run 42391201068", "from inside the network in the Operator, passed 4 of 4",
                      "both aliases answered 200 with the Operator's own token (12 prompt and 4 completion tokens each)", "a request with no token got 401, a wrong alias got 404",
                      "the service never returns `apiFormat` for a model", "PR 84 fixed the check", "Hub run 42392996525", "was green, read-back included",
                      "was not needed in this tenant on 2026-11-07, for the Operator's identity", "Whether the Foundry Agent Service needs it in step 2 is not known",
                      "The meter \"10k AI Gateway Requests\" is 0.00 US dollars in the preview", "nothing was read from Azure or GitHub here"):
            self.assertIn(words, entry, words)

    def test_it_says_that_step_2_and_its_switch_are_still_off_and_that_nothing_calls_through_the_gateway(self):
        entry = flat(ENTRY)
        for words in ("Step 2 is still off", "`AGENTS_VIA_AI_GATEWAY` in `tools/environment-params.py` is False", "Nothing calls through the gateway",
                      "the agents and the Detective and the Skeptic call their Foundry deployments direct ([rule 15 (c)](AGENTS.md))", "Step 2 needs the owner's separate yes",
                      "a new deployment needs his written request again"):
            self.assertIn(words, entry, words)

    def test_nothing_of_the_owners_estate_is_in_it(self):
        self.assertNotRegex(ENTRY, GUID, "no id")
        self.assertNotRegex(ENTRY, r"[\w.+-]+@[\w-]+\.[\w.]+", "no e-mail address")
        self.assertNotRegex(ENTRY, r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "no address of the estate")
        self.assertNotRegex(ENTRY, r"aigw-meternaut-[0-9a-f]{6,}|-[0-9a-f]{8}\b", "no real name of a resource")


class TheSwitchIsStillFalse(unittest.TestCase):
    def test_the_constant_is_false_in_the_code(self):
        self.assertRegex(text("tools/environment-params.py"), r"(?m)^AGENTS_VIA_AI_GATEWAY = False$")


class TheRulesAndTheRecordSayTheSame(unittest.TestCase):
    def test_rule_15_c_still_says_that_every_model_call_goes_direct_until_step_2_is_switched_on(self):
        (rule,) = [line for line in text("AGENTS.md").splitlines()
                   if line.lstrip().startswith("- **(c) Every model call of Meternaut goes direct, privately and with no key, to the model deployments of its own Foundry project**")]
        for words in ("**nothing calls through it**", "needs the owner's separate yes, so until it is switched on every model call goes direct, as this rule says.",
                      "so a new deployment of it needs his written request again", "The owner's own, existing AI Gateway in another subscription is not touched"):
            self.assertIn(words, rule, words)

    def test_the_record_marks_steps_1_to_4_done_and_step_5_not_done(self):
        section = RECORD.split("## What a person does")[1].split("## Telemetry is off")[0]
        for words in ("Steps 1 to 4 were done on 2026-11-07. Step 5 was not, and it needs the owner's separate yes.", f'"{REQUEST}"', "**Not needed on 2026-11-07, for the Operator's identity:**",
                      "Whether the Foundry Agent Service needs it in step 2 is not known.", "from inside the network in the Operator, passed 4 of 4", "the service never returns `apiFormat` for a model",
                      "**Not done:** the switch is False, and nothing calls through the gateway."):
            self.assertIn(words, section, words)

    def test_no_live_page_says_any_more_that_the_gateway_is_not_deployed_or_not_used(self):
        stale = ("AI Gateway is not deployed", "is not deployed either", "AI Gateway is not used", "not used and not deployed", "Not used since 2026-11-07", "both steps are built and not deployed",
                 "Step 1 of 2 is built and not deployed", "Nothing was made in Azure", "is not added yet")
        for page in ("README.md", "AGENTS.md", "environment/BOOTSTRAP.md", "docs/proposals/01-first-environment.md", "docs/proposals/06-foundry-agents.md", "docs/proposals/07-private-by-default.md",
                     "docs/proposals/08-ai-gateway.md", ".github/workflows/deploy-hub.yml"):
            source = text(page)
            for words in stale:
                self.assertNotIn(words, source, f"{page}: {words}")

    def test_the_older_entries_keep_what_was_true_on_their_day(self):
        for heading in ("An AI Gateway for the agents' model calls, step 1 of 2: built, not deployed — 2026-11-07",
                        "An AI Gateway for the agents' model calls, step 2 of 2: built, not deployed, and one switch that is False — 2026-11-07"):
            self.assertIn(f"\n## {heading}\n", CHANGELOG)


if __name__ == "__main__":
    unittest.main()
