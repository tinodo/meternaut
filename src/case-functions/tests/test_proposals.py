"""The readers of what a finding proposes (cases/proposals.py): they never raise, and they leave out what is not in the shape."""
import unittest

import support  # noqa: F401  (puts the app on the path)
from cases import proposals


class ReadersTest(unittest.TestCase):
    def test_a_setting_is_read_as_it_was_kept(self):
        facts = {proposals.KEY: {"set": [{"path": "scaleUnits", "from": 4, "to": 2}]}}
        self.assertEqual(proposals.settings(facts), (proposals.Setting("scaleUnits", 4, 2),))

    def test_what_is_not_in_the_shape_is_left_out(self):
        facts = {proposals.KEY: {"set": [{"path": "", "from": 4, "to": 2}, {"path": "a", "from": None, "to": 2}, {"path": "b", "from": 1}, "text", {"path": "c", "from": 3, "to": 1}]}}
        self.assertEqual(proposals.settings(facts), (proposals.Setting("c", 3, 1),))
        for nothing in (None, {}, [], "x", {proposals.KEY: "x"}, {proposals.KEY: {"set": "x", "others": 3}}):
            self.assertEqual(proposals.settings(nothing), ())
            self.assertEqual(proposals.others(nothing), ())

    def test_at_most_the_limits_are_read(self):
        facts = {proposals.KEY: {"set": [{"path": f"p{n}", "from": 2, "to": 1} for n in range(9)], "others": [{"title": f"t{n}"} for n in range(9)]}}
        self.assertEqual(len(proposals.settings(facts)), proposals.MAX_SETTINGS)
        self.assertEqual(len(proposals.others(facts)), proposals.MAX_OTHERS)

    def test_another_way_keeps_its_words_cut_and_its_figures_typed(self):
        facts = {proposals.KEY: {"others": [{"title": "  Use  the\nsmall tier ", "givesUp": "x" * 999, "action": "switch", "inPlace": False, "lowUsd": 270.5, "highUsd": "9"}, {"givesUp": "no title"}]}}
        (one,) = proposals.others(facts)
        self.assertEqual((one.title, len(one.gives_up), one.action, one.in_place, one.low, one.high), ("Use the small tier", proposals.MAX_GIVES_UP, "switch", False, 270.5, None))

    def test_why_a_change_cannot_be_made(self):
        self.assertEqual(proposals.cannot({proposals.CANNOT_KEY: "outside"}), proposals.CANNOT["outside"])
        for nothing in (None, {}, {proposals.CANNOT_KEY: "nope"}, {proposals.CANNOT_KEY: 3}, "x"):
            self.assertEqual(proposals.cannot(nothing), "")
        for sentence in proposals.CANNOT.values():
            self.assertTrue(sentence.endswith(".") and sentence[0].isupper())

    def test_an_estimate_is_read_only_where_it_is_true_and_a_way_with_none_is_not_one(self):
        way = {"title": "Use the small tier", "lowUsd": 100.0, "highUsd": 150.0}
        for stored, read in ((True, True), (False, False), (None, False), ("yes", False), ("true", False), ("1", False), (1, False), (1.0, False), ([True], False), ({"a": True}, False)):
            with self.subTest(stored=stored):
                (one,) = proposals.others({proposals.KEY: {"others": [{**way, "estimate": stored}]}})
                self.assertIs(one.estimate, read)
        (one,) = proposals.others({proposals.KEY: {"others": [way]}})
        self.assertIs(one.estimate, False)

    def test_only_a_property_whose_last_key_names_a_count_or_a_size_is_countlike(self):
        for path in ("scaleUnits", "sku.capacity", "properties.sku.capacity", "instanceCount", "maxReplicas", "numberOfWorkers", "maximumNumberOfWorkers", "agentPoolProfiles.count", "workerCount",
                     "diskSizeGB", "vCores", "bandwidthInMbps", "count.count", "processCount"):
            self.assertTrue(proposals.countlike(path), path)
        for path in ("minimumTlsVersion", "retentionDays", "zonesCount", "ipConfigurationsCount", "timeoutInMinutes", "zoneRedundant", "diskState", "sku.tier", "replicaCount.mode", "count.state",
                     "", ".", "x.", "tier", None, 4):
            self.assertFalse(proposals.countlike(path), path)

    def test_words_of_a_key_and_a_value(self):
        self.assertEqual(proposals.label("scaleUnits"), "scale units")
        self.assertEqual(proposals.label("sku.capacity"), "sku capacity")
        self.assertEqual(proposals.label("maxIOPS"), "max iops")
        self.assertEqual([proposals.shown(v) for v in (4, 1440.0, 2.5, True, False, "Basic")], ["4", "1,440", "2.5", "on", "off", "Basic"])


if __name__ == "__main__":
    unittest.main()
