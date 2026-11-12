"""The estimate at list price of a managed disk that Azure has no cost line for (cases/estimate.py). Everything in it is INVENTED, except the table that the module holds."""
import datetime as dt
import unittest

import support  # noqa: F401  (puts the app on the path)

from cases import estimate


class TheTable(unittest.TestCase):
    def test_a_disk_is_priced_at_the_smallest_tier_that_holds_its_size(self):
        found = {("Standard_LRS", 4): ("S4", 1.54), ("Standard_LRS", 32): ("S4", 1.54), ("Standard_LRS", 33): ("S6", 3.01), ("StandardSSD_LRS", 4): ("E1", 0.3),
                 ("StandardSSD_LRS", 5): ("E2", 0.6), ("Premium_LRS", 1): ("P1", 0.6), ("Premium_LRS", 128): ("P10", 19.71), ("Premium_LRS", 129): ("P15", 38.01),
                 ("Premium_ZRS", 4096): ("P50", 743.35), ("StandardSSD_ZRS", 1024): ("E30", 115.2)}
        for (sku, size), (tier, price) in found.items():
            with self.subTest(sku=sku, size=size):
                got = estimate.disk_estimate(sku, size)
                self.assertEqual((got["tier"], got["usdMonth"], got["table"]), (tier, price, estimate.TABLE_DATE))

    def test_a_type_or_a_size_that_the_table_does_not_have_has_no_estimate(self):
        for sku, size in (("UltraSSD_LRS", 128), ("PremiumV2_LRS", 128), ("Nonsense", 128), ("", 128), (None, 128), ("Standard_LRS", 4097), ("Standard_LRS", 0), ("Standard_LRS", -4),
                          ("Standard_LRS", True), ("Standard_LRS", "4"), ("Standard_LRS", None), ("Standard_LRS", 4.5), ("Standard_LRS", float("nan"))):
            with self.subTest(sku=sku, size=size):
                self.assertEqual(estimate.disk_estimate(sku, size), {})

    def test_the_type_is_read_without_regard_to_case_and_a_whole_number_that_came_as_a_float_is_a_size(self):
        self.assertEqual(estimate.disk_estimate(" standard_lrs ", 4.0), estimate.disk_estimate("Standard_LRS", 4))
        self.assertEqual(estimate.disk_estimate("STANDARDSSD_ZRS", 8)["tier"], "E2")

    def test_every_tier_is_larger_and_dearer_than_the_one_before_it_and_the_largest_is_the_limit(self):
        for sku, tiers in estimate.TIERS.items():
            with self.subTest(sku=sku):
                sizes, prices = [size for size, _, _ in tiers], [price for _, _, price in tiers]
                self.assertEqual(sizes, sorted(set(sizes)))
                self.assertEqual(prices, sorted(set(prices)))
                self.assertEqual(sizes[-1], estimate.MAX_SIZE_GIB)
                for _, tier, price in tiers:
                    self.assertRegex(tier, r"^[SEP][0-9]{1,2}$")
                    self.assertGreater(price, 0)

    def test_the_table_has_a_date_and_the_words_that_say_what_it_is(self):
        self.assertEqual(dt.date.fromisoformat(estimate.TABLE_DATE), dt.date(2026, 11, 12))
        self.assertEqual(estimate.LABEL, "Estimate at list price, not Azure's bill")
        self.assertEqual(estimate.date_words(estimate.TABLE_DATE), "12 November 2026")
        for bad in ("", None, "2026-13-01", "12 November 2026", "2026-11-1", 20261112):
            self.assertEqual(estimate.date_words(bad), "", bad)


class WhatARecordHolds(unittest.TestCase):
    def test_an_estimate_that_a_record_holds_is_read_back_only_when_it_is_what_the_table_makes(self):
        made = estimate.disk_estimate("Standard_LRS", 4)
        got = estimate.estimate_of(made)
        self.assertEqual((got.monthly, got.tier, got.table, got.count), (1.54, "S4", estimate.TABLE_DATE, 1))
        for damaged in (None, {}, [], "x", {"usdMonth": 1.5}, {**made, "usdMonth": 0}, {**made, "usdMonth": -1}, {**made, "usdMonth": float("nan")}, {**made, "usdMonth": True},
                        {**made, "usdMonth": 1_000_000}, {**made, "tier": "X9"}, {**made, "tier": 5}, {**made, "table": "yesterday"}, {**made, "table": None}):
            with self.subTest(damaged=str(damaged)[:60]):
                self.assertIsNone(estimate.estimate_of(damaged))

    def test_the_estimates_of_several_disks_add_up_only_when_every_one_has_one_and_they_are_of_one_table(self):
        one, two = (estimate.estimate_of(estimate.disk_estimate("Standard_LRS", size)) for size in (4, 64))
        total = estimate.summed([one, two])
        self.assertEqual((total.monthly, total.tier, total.count), (4.55, "S4/S6", 2))
        self.assertIsNone(estimate.summed([one, None]))
        self.assertIsNone(estimate.summed([]))
        self.assertIsNone(estimate.summed([one, estimate.Estimate(1.0, "S4", "2026-01-01")]))
        self.assertEqual(estimate.summed([one, one]).tier, "S4")


class TheSentence(unittest.TestCase):
    def test_it_says_that_it_is_an_estimate_at_list_price_what_it_is_the_price_of_and_the_date_of_the_table(self):
        text = estimate.words(estimate.estimate_of(estimate.disk_estimate("Standard_LRS", 4)))
        self.assertEqual(text, "Estimate at list price, not Azure's bill: about $1.54 a month for a disk of this type and size (tier S4). East US list prices of 12 November 2026.")

    def test_the_sentence_of_a_sum_says_how_many_disks_and_which_tiers(self):
        both = estimate.summed([estimate.estimate_of(estimate.disk_estimate("Standard_LRS", size)) for size in (4, 64, 4)])
        self.assertEqual(estimate.words(both), "Estimate at list price, not Azure's bill: about $6.09 a month for these 3 disks (tiers S4, S6). East US list prices of 12 November 2026.")

    def test_a_large_price_has_its_thousands_and_its_cents(self):
        text = estimate.words(estimate.estimate_of(estimate.disk_estimate("Premium_ZRS", 4096)))
        self.assertIn("about $743.35 a month", text)


if __name__ == "__main__":
    unittest.main()
