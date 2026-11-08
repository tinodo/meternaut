"""The records of 2026-11-07 about the AI Gateway: it is deployed and checked, and the changelog entry of that day says what was true on its day (nothing called through the gateway yet, and step 2 was off).

The owner asked in writing for the gateway ("Create the AI Gateway with public network access and private routing."), the actions `aigateway` and `aigateway-check` ran, and the changelog says what they made,
proved and found. These tests hold the changelog entry (it keeps what was true on its day), the switch (True in the code since the owner ordered the agents' route, 2026-11-07) and the pages that used to say
"not deployed" to one story. They call neither Azure nor GitHub."""
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
ENTRY = CHANGELOG.split("\n## ")[4]
RECORD = flat(text("docs/proposals/08-ai-gateway.md"))


class TheChangelogEntry(unittest.TestCase):
    def test_it_is_the_entry_under_the_two_entries_of_the_estate_watch_and_the_web_page_and_has_at_most_twelve_lines(self):
        headings = re.findall(r"(?m)^## (.*)$", CHANGELOG)
        self.assertTrue(headings[2].startswith("The Watch reads every subscription that its identity can read"), "the entry of 2026-11-07 about the build of the estate-wide Watch follows the entries of the deployed Watch and of the web page")
        self.assertEqual(headings[3], TITLE)
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

    def test_the_entry_says_that_on_its_day_step_2_and_its_switch_were_off_and_that_nothing_called_through_the_gateway(self):
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


class TheSwitchIsOnInTheCode(unittest.TestCase):
    def test_the_constant_is_true_in_the_code(self):
        self.assertRegex(text("tools/environment-params.py"), r"(?m)^AGENTS_VIA_AI_GATEWAY = True$")


class TheRulesAndTheRecordSayTheSame(unittest.TestCase):
    def test_rule_15_c_says_that_every_model_call_goes_through_the_ai_gateway_and_that_the_agents_route_is_on_in_code_and_ran_once(self):
        (rule,) = [line for line in text("AGENTS.md").splitlines()
                   if line.lstrip().startswith("- **(c) Every model call of Meternaut goes through the AI Gateway, the governance hub of the Citadel design, with no direct path, not even for a test, unless the owner makes a written exception**")]
        for words in ("**The agents' route through the gateway is on in code and ran in Azure**", "(`AGENTS_VIA_AI_GATEWAY` in `tools/environment-params.py`, True)",
                      "so a new deployment of it needs his written request again", "The owner's own, existing AI Gateway in another subscription is not touched"):
            self.assertIn(words, rule, words)
        self.assertNotIn("False today", rule)

    def test_the_record_marks_steps_1_to_4_done_and_step_5_half_done(self):
        section = RECORD.split("## What a person does")[1].split("## Telemetry is off")[0]
        for words in ("Steps 1 to 4 were done on 2026-11-07. Step 5 is half done: the owner ordered it, the switch is on in code, and the real run was made on 2026-11-08 and stopped at the model's refusal of the Investigator's function tools; the fix has not been run. Step 6, the judges' route, ran in that run: 3 cases through the gateway.", f'"{REQUEST}"',
                      "**Not needed on 2026-11-07, for the Operator's identity:**",
                      "Whether the Foundry Agent Service needs it in step 2 is not known.", "from inside the network in the Operator, passed 4 of 4", "the service never returns `apiFormat` for a model",
                      "**Done:** the owner ordered it (2026-11-07), the switch is True, and the real run was made on 2026-11-08 up to `cases-run`, three times: the agents were made with the model names of the gateway, and the Investigator was refused at its first call each time",
                      "**Not done:** the run with the third fix, which makes the Investigator gpt-5.5 (`foundry`, `aigateway`, `cases`, `cases-run`).", "**Done on 2026-11-08:** the judges ran through the gateway with the app's own identity, in the first real run of step 5: 3 cases, every step ok."):
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
