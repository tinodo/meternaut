"""The records of 2026-11-07 about the whole-estate Watch: it is deployed and checked.

The owner ordered it in writing ("That must be on the root management group; watch the entire estate."), a person gave the two read roles at the tenant root management group, and the Hub actions
`cases` and `cases-run` ran: the changelog says what they showed. These tests hold that entry, and the pages that said "built, not deployed" to one story, and check that none of them carries an id of a real
tenant, subscription, group or resource. They call neither Azure nor GitHub."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TITLE = "The whole-estate Watch is deployed and checked — 2026-11-07"
ORDER = "That must be on the root management group; watch the entire estate."
GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
BOOTSTRAP_SECTION = "## Changed on 2026-11-07: the Watch reads every subscription that its identity can read\n"
RECORD_SECTION = "## The Watch reads every subscription that its identity can read\n"


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def flat(source):
    return re.sub(r"\s+", " ", source)


def section(source, heading):
    return source.split(heading)[1].split("\n## ")[0]


CHANGELOG = text("CHANGELOG.md")
ENTRY = CHANGELOG.split("\n## ")[4]
README = text("README.md")
BOOTSTRAP = text("environment/BOOTSTRAP.md")
RECORD = text("docs/proposals/03-access-and-onboarding.md")
FIRST_CASES = text("docs/proposals/02-first-cases.md")


class TheChangelogEntry(unittest.TestCase):
    def test_it_is_the_newest_entry_and_has_at_most_ten_lines(self):
        self.assertEqual(re.findall(r"(?m)^## (.*)$", CHANGELOG)[3], TITLE)
        self.assertTrue(ENTRY.startswith(TITLE))
        self.assertLessEqual(len(ENTRY.strip().splitlines()), 10, "the owner reads nothing long")

    def test_it_says_what_the_owner_ordered_who_gave_which_roles_where_what_ran_what_it_found_and_what_is_not_checked(self):
        entry = flat(ENTRY)
        leads = ["**What the owner ordered, and who gave what.**", "**What ran.**", "**What it found.**", "**Not checked.**"]
        positions = [entry.index(lead) for lead in leads]
        self.assertEqual(positions, sorted(positions))
        for words in (f'"{ORDER}"', "in the owner's own session and on his word", "the read-only roles *Reader* and *Cost Management Reader* at the tenant root management group",
                      "`tools/access-requirements.py grant --only R1,R2 --estate <the group>`", "read back 2 of 2 present",
                      "Hub `cases` (run 42402199092, from `main` at 9ecb3e9) deployed the app with `SCOPE_ALL_SUBSCRIPTIONS` true",
                      "that setting true, `SCOPE_SUBSCRIPTIONS` kept as the fallback, no `GATEWAY_*` setting left", "Hub `cases-run` (run 42402901444) ended well",
                      "\"The Watch read 10 subscriptions (every subscription that the app's identity can read)\", in 345 seconds, with 11 leads (advisor-cost 4, orphan-managed-disk 1, orphan-private-endpoint 6)",
                      "The History page showed the run correctly in a read-only browser check", "`what-if` (run 42404194478) is green for every template",
                      "The investigation ran 261 seconds, with 9 tool calls and 29,290 tokens, and opened 4 cases (investigate, needs a person) about private endpoints in a subscription other than the pilot's",
                      "its `estate_overview` tool stopped at its 45-second budget and left one subscription unread in that call",
                      "one tool call got a 400 for a metric namespace that is not supported (a detail of the agent's request)",
                      "The scheduled daily run (05:30 UTC) unattended on the whole estate; Advisor, which is still read for each subscription; throttling on a much larger estate",
                      "nothing was read from Azure or GitHub here"):
            self.assertIn(words, entry, words)

    def test_nothing_of_the_owners_estate_is_in_it(self):
        self.assertNotRegex(ENTRY, GUID, "no id")
        self.assertNotRegex(ENTRY, r"[\w.+-]+@[\w-]+\.[\w.]+", "no e-mail address")
        self.assertNotRegex(ENTRY, r"managementGroups/(?!<)[A-Za-z0-9]", "no management group of a real tenant")
        self.assertNotRegex(ENTRY, r"aigw-meternaut-[0-9a-f]{6,}|func-meternaut-(cases|usage)-[0-9a-f]{6,}|-[0-9a-f]{8}\b", "no real name of a resource")


class ThePagesSayThatItIsDeployed(unittest.TestCase):
    def test_the_readme_the_first_cases_page_the_access_page_and_the_bootstrap_page_say_that_the_two_roles_are_at_the_tenant_root_management_group_and_the_watch_read_10_subscriptions(self):
        self.assertIn("(and, since 2026-11-07, in every subscription that its identity can read: it read 10 on its first run there, once a person had given it the two read roles at the tenant root management group;", README)
        cases = flat(FIRST_CASES.split("**Changed on 2026-11-07, a second time.**")[1].split("\n\n")[0])
        self.assertIn("It is deployed and has run so: on 2026-11-07 a person gave the two roles at the tenant root management group, and a run read 10 subscriptions", cases)
        self.assertIn("(on 2026-11-07 a person gave them at the tenant root management group, and the Watch now reads every subscription below it)", flat(FIRST_CASES))
        record = flat(section(RECORD, RECORD_SECTION))
        for words in ("**Done on 2026-11-07:** a person did it in the owner's own session and on his word, and `check` read back 2 of 2 present.",
                      "With the roles at the tenant root management group, Hub `cases` deployed the app with `SCOPE_ALL_SUBSCRIPTIONS` true, and Hub `cases-run` ended well: the Watch read 10 subscriptions in 345 seconds"):
            self.assertIn(words, record, words)
        self.assertIn("a person gave R1 and R2 once at the tenant root management group (2 of 2 present; the Watch then read 10 subscriptions:", flat(RECORD))
        page = flat(section(BOOTSTRAP, BOOTSTRAP_SECTION))
        for words in ("**Done on 2026-11-07:** both steps below were done, and a run of the Watch read 10 subscriptions", "**Done on 2026-11-07,** by a person in the owner's own session, on his word, with `grant --only R1,R2 --estate <the group>`; `check` read back 2 of 2 present.",
                      "`cases` deployed the app with `SCOPE_ALL_SUBSCRIPTIONS` true (read back from the app: `SCOPE_SUBSCRIPTIONS` kept as the fallback, and no `GATEWAY_*` setting left), and `cases-run` ended well"):
            self.assertIn(words, page, words)

    def test_no_live_page_says_any_more_that_the_whole_estate_watch_is_built_and_not_deployed(self):
        stale = ("built and not yet deployed", "Nothing is deployed by this change", "It has run only against models of Azure", "no grant at a management group",
                 "a person may give them at the tenant root management group instead", "Reader is the built-in role on the whole pilot subscription")
        for page, source in (("README.md", README), ("docs/proposals/02-first-cases.md", FIRST_CASES), ("docs/proposals/03-access-and-onboarding.md", RECORD), ("environment/BOOTSTRAP.md", BOOTSTRAP)):
            for words in stale:
                self.assertNotIn(words, source, f"{page}: {words}")

    def test_the_entry_of_the_build_keeps_what_was_true_on_its_day(self):
        self.assertIn("\n## The Watch reads every subscription that its identity can read (built, not deployed) — 2026-11-07\n", CHANGELOG)


if __name__ == "__main__":
    unittest.main()
