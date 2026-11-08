"""The records of 2026-11-07 about the estate-wide Watch: it reads every subscription that its identity can read, a person grants the two read roles once at the group above them, and nothing
else about what may be changed has moved.

The owner ordered it in writing ("Watch is what checks for cost savings? That must be on the root management group; watch the entire estate."). These tests hold the newest changelog entry, the
rules and the pages to one story, and check that none of them carries an id of a real tenant, subscription or group. They call neither Azure nor GitHub."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TITLE = "The Watch reads every subscription that its identity can read (built, not deployed) — 2026-11-07"
ORDER = "Watch is what checks for cost savings? That must be on the root management group; watch the entire estate."
GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
BOOTSTRAP_SECTION = "## Changed on 2026-11-07: the Watch reads every subscription that its identity can read\n"
RECORD_SECTION = "## The Watch reads every subscription that its identity can read\n"


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def flat(source):
    return re.sub(r"\s+", " ", source)


CHANGELOG = text("CHANGELOG.md")
ENTRY = CHANGELOG.split("\n## ")[4]
BOOTSTRAP = text("environment/BOOTSTRAP.md")
RECORD = text("docs/proposals/03-access-and-onboarding.md")
FIRST_CASES = text("docs/proposals/02-first-cases.md")
AGENTS = text("AGENTS.md")


def section(source, heading):
    return source.split(heading)[1].split("\n## ")[0]


class TheChangelogEntry(unittest.TestCase):
    def test_it_is_the_third_entry_and_is_short(self):
        self.assertEqual(re.findall(r"(?m)^## (.*)$", CHANGELOG)[3], TITLE, "the entry of the whole-estate Watch that is deployed (test_estate_watch_deployed.py) and the one of the web page (test_console_gateway.py) are above it")
        self.assertTrue(ENTRY.startswith(TITLE))
        self.assertLessEqual(len(ENTRY.strip().splitlines()), 15, "the owner reads nothing long")

    def test_it_says_what_the_owner_ordered_what_changed_what_a_person_does_and_what_is_not_checked(self):
        entry = flat(ENTRY)
        leads = ["**What the owner ordered.**", "**What changed.**", "**What a person does.**", "**Not checked.**"]
        positions = [entry.index(lead) for lead in leads]
        self.assertEqual(positions, sorted(positions))
        for words in (f'"{ORDER}"', "asks Azure which subscriptions its own identity can read", "the enabled ones, at most 1,000", "`SCOPE_ALL_SUBSCRIPTIONS` (Bicep default false; the Hub's builder passes true",
                      "`SCOPE_SUBSCRIPTIONS` stays as the fallback; with neither, the run says why and stops", "The limits are as they were: three cases, the same tokens and calls",
                      "60% of the run's deadline for reading", "the subscriptions that were not read are named in a note", "`run.started` carries the count and the first five ids",
                      "A change can still be made only in the one resource group of the loop", "*Reader* and *Cost Management Reader* at the tenant root management group",
                      "`python tools/access-requirements.py grant --estate <the group's id> --only R1,R2` (a dry run; `--apply` makes it)", "the Hub actions `cases` and `cases-run`",
                      "Until the grant exists, the Watch reads the pilot subscription only", "This change grants nothing", "Nothing ran against Azure", "Advisor is still read for each subscription"):
            self.assertIn(words, entry, words)

    def test_nothing_of_the_owners_estate_is_in_it(self):
        self.assertNotRegex(ENTRY, GUID, "no id")
        self.assertNotRegex(ENTRY, r"[\w.+-]+@[\w-]+\.[\w.]+", "no e-mail address")
        self.assertNotRegex(ENTRY, r"managementGroups/[A-Za-z0-9]", "no management group")


class TheRulesAndThePages(unittest.TestCase):
    def test_the_rules_say_that_the_watch_reads_what_its_identity_can_read_and_that_a_person_grants_the_roles_at_the_group_above(self):
        rule_24 = AGENTS.split("\n24. ")[1].split("\n25. ")[0]
        for words in (f'"{ORDER}"', "**The Watch reads every subscription that its own identity can read**", "Reader and Cost Management Reader (R1 and R2) once at the group above the subscriptions, the tenant root management group, or at each subscription",
                      "the template, the pipeline and the app grant nothing there"):
            self.assertIn(words, rule_24, words)
        rule_29 = AGENTS.split("\n29. ")[1].split("\n30. ")[0]
        for words in ("every subscription that the cases app's identity can read, and nothing more than reads", "**Reading more does not widen what may be changed:**",
                      "a change is planned and made only in the one resource group of `CHANGE_RESOURCE_GROUP` in `CHANGE_SUBSCRIPTION_ID`"):
            self.assertIn(words, rule_29, words)
        rule_31 = AGENTS.split("\n31. ")[1]
        self.assertIn("The Watch reads every subscription that its identity can read (rules 24 and 29), so an agent's finding can be about a resource that belongs to somebody else", rule_31)
        self.assertNotIn("The Watch reads the subscription that it is given", AGENTS)

    def test_the_access_page_has_the_section_and_says_what_a_person_does_and_what_is_not_checked(self):
        page = flat(section(RECORD, RECORD_SECTION))
        for words in (f'"{ORDER}"', "`GET /subscriptions`", "the ones that are enabled, at most 1000", "`SCOPE_ALL_SUBSCRIPTIONS`", "`SCOPE_SUBSCRIPTIONS`, a list of subscription ids, is what the Watch reads when the list cannot be had",
                      "a run that has neither ends with a plain reason and never watches nothing in silence", "One grant of R1 and R2 at the tenant root management group",
                      "`python tools/access-requirements.py grant --estate /providers/Microsoft.Management/managementGroups/<the group's id> --only R1,R2`",
                      "Until the grant exists the identity reads only the subscription that it holds the roles on", "Neither the template nor the Hub grants anything there",
                      "A change to Azure is still made only in the one resource group of `CHANGE_RESOURCE_GROUP` in `CHANGE_SUBSCRIPTION_ID`", "The limits of rule 15 (g) are as they were",
                      "60%, and a subscription that was started inside it may finish within 10% more", "HTTP 429", "the first five ids (eight characters each), never all of them",
                      "Not checked: the scheduled daily run on the whole estate, unattended; Advisor, which is still read for each subscription; throttling on a much larger estate"):
            self.assertIn(words, page, words)
        calls = flat(RECORD).split("**Which call needs which grant.**")[1].split("**The calls are checked against the file.**")[0]
        self.assertIn("21 kinds of call", calls)
        self.assertIn("The Watch makes nineteen: the list of the subscriptions that its identity can read", calls)

    def test_the_first_cases_page_says_that_the_watch_is_no_longer_limited_to_the_pilot_subscription(self):
        page = flat(FIRST_CASES)
        for words in ("**Changed on 2026-11-07, a second time.**", f'"{ORDER}"', "the Watch reads every subscription that the app's own identity can read, not one that is listed in a setting",
                      "Watching more changes nothing of what may be changed", "`subscriptions` (how many the run reads), `scopes` (the first five of them, eight characters of each id, never all)",
                      "`scopeFrom` (`estate`: the list that the identity can read; `setting` or `setting-fallback`: the explicit list; `none`)"):
            self.assertIn(words, page, words)

    def test_the_bootstrap_page_has_the_hand_step_before_the_list_of_what_comes_after_it_and_names_no_real_group(self):
        page = section(BOOTSTRAP, BOOTSTRAP_SECTION)
        self.assertLess(BOOTSTRAP.index(BOOTSTRAP_SECTION), BOOTSTRAP.index("\n## After it"))
        for words in (f'"{ORDER}"', "**Hand step: *Reader* and *Cost Management Reader* at the tenant root management group**", "It is break-glass ([rule 18](../AGENTS.md))",
                      '$root = "/providers/Microsoft.Management/managementGroups/<the id of the tenant root management group>"',
                      "--estate $root --only R1,R2 --apply", "The roles on the pilot subscription stay", "**The Hub: `cases`, then `cases-run` once.**", "`scopeAllSubscriptions` as true",
                      "A change is still made only in the one resource group of `CHANGE_RESOURCE_GROUP`", "**Going back.**", '--role "Reader" --scope $root', "**Costs.** Nothing that is priced is added"):
            self.assertIn(words, page, words)
        self.assertNotRegex(page, GUID, "no id")
        self.assertEqual(len(re.findall(r"```powershell", page)), 1)

    def test_none_of_the_pages_that_were_written_carries_an_id_of_a_real_estate(self):
        for label, part in (("the record", section(RECORD, RECORD_SECTION)), ("the first cases page", FIRST_CASES.split("**Changed on 2026-11-07, a second time.**")[1].split("\n\n")[0]),
                            ("the bootstrap page", section(BOOTSTRAP, BOOTSTRAP_SECTION))):
            self.assertNotRegex(part, GUID, f"{label}: no id")
            self.assertNotRegex(part, r"[\w.+-]+@[\w-]+\.[\w.]+", f"{label}: no e-mail address")
            self.assertNotRegex(part, r"managementGroups/(?!<)[A-Za-z0-9]", f"{label}: no management group of a real tenant")


if __name__ == "__main__":
    unittest.main()
