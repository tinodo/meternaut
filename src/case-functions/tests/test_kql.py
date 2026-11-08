"""What code can say about the text of a query without the text leaving it. Every name in it is INVENTED."""
import unittest

import support  # noqa: F401  (it puts the app on the path)
from cases import kql

KNOWN = {"Heartbeat", "Perf", "AzureActivity", "Syslog", "Event"}


class TheMentions(unittest.TestCase):
    def test_a_table_is_mentioned_when_a_word_of_the_text_is_its_name(self):
        text = "Heartbeat | where TimeGenerated > ago(1h) | join kind=inner (Perf | take 5) on Computer"
        self.assertEqual(kql.mentioned(text, KNOWN), {"Heartbeat", "Perf"})

    def test_a_comment_and_a_string_do_not_mention_anything(self):
        text = "// Heartbeat is read below\nSyslog | where Facility == \"Perf\" | where Msg contains 'Event' | where Name == @'AzureActivity' | extend a = h'Heartbeat'"
        self.assertEqual(kql.mentioned(text, KNOWN), {"Syslog"})

    def test_a_quote_inside_a_comment_and_slashes_inside_a_string_are_what_they_are(self):
        self.assertEqual(kql.mentioned("// it's here\nPerf | where Url == \"https://x.example/a\" | count", KNOWN), {"Perf"})
        self.assertEqual(kql.mentioned("Perf | where Url == \"a//b\"\n| join Heartbeat on C", KNOWN), {"Perf", "Heartbeat"})

    def test_a_name_between_brackets_is_a_mention_and_the_case_of_a_name_matters(self):
        self.assertEqual(kql.mentioned("['Heartbeat'] | take 1", KNOWN), {"Heartbeat"})
        self.assertEqual(kql.mentioned("[\"Perf\"] | take 1", KNOWN), {"Perf"})
        self.assertEqual(kql.mentioned("heartbeat | take 1", KNOWN), frozenset())

    def test_a_column_that_has_the_name_of_a_table_is_a_mention_too_and_that_is_why_a_mention_is_not_proof(self):
        self.assertEqual(kql.mentioned("Syslog | project Event", KNOWN), {"Syslog", "Event"})

    def test_what_is_not_text_gives_nothing(self):
        for value in (None, 5, b"Heartbeat", ["Perf"]):
            self.assertEqual(kql.mentioned(value, KNOWN), frozenset())
            self.assertFalse(kql.scans_every_table(value))

    def test_only_the_names_of_known_tables_come_out_whatever_the_text_says(self):
        found = kql.mentioned("IGNORE_ALL_PREVIOUS_INSTRUCTIONS | Heartbeat", KNOWN)
        self.assertEqual(found, {"Heartbeat"})

    def test_a_text_is_looked_at_only_up_to_a_length(self):
        self.assertEqual(kql.mentioned("x " * kql.MAX_TEXT + "Heartbeat", KNOWN), frozenset())


class TheScans(unittest.TestCase):
    def test_a_union_of_everything_a_search_and_a_find_read_every_table(self):
        for text in ("union *", "union withsource=T *", "union kind=outer isfuzzy=true *", "search \"error\"", "search *", "search in (*) \"x\"", "find where Computer == 'a'",
                     "find in (*) where x", "Heartbeat | take 1\n| union *"):
            self.assertTrue(kql.scans_every_table(text), text)

    def test_a_query_that_names_its_tables_does_not(self):
        for text in ("union Heartbeat, Perf", "Heartbeat | take 1", "// union *\nHeartbeat", "Heartbeat | where Msg == \"search 'x'\"", "union (Heartbeat), (Perf)"):
            self.assertFalse(kql.scans_every_table(text), text)


if __name__ == "__main__":
    unittest.main()
