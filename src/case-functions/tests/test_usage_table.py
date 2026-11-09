"""The table of the use that a decision card draws (cases/usage.py): every kind is complete and rests on a metric that Microsoft Learn names, the numbers of a series are read as they should be,
and nothing that decides reads the table. Everything in it is INVENTED, except the names of metrics, which are Azure's."""
import ast
import datetime as dt
import math
import re
import unittest

from support import APP_ROOT

from cases import usage
from cases.usage import KINDS, TABLE, Use

FIRST = dt.date(2026, 10, 5)

# What the pages of Learn ("Supported metrics for <type>", under usage.LEARN) said on 2026-11-09: the name of each metric in the REST API and its default aggregation. A kind of the table
# rests on these and on nothing else: a metric that is not here is not in the table.
CONFIRMED = {
    "microsoft.compute/virtualmachines": {"Percentage CPU": "average"},
    "microsoft.web/serverfarms": {"CpuPercentage": "average"},
    "microsoft.network/privateendpoints": {"PEBytesIn": "total", "PEBytesOut": "total"},
    "microsoft.storage/storageaccounts": {"Transactions": "total"},
    "microsoft.cognitiveservices/accounts": {"TotalCalls": "total", "ModelRequests": "total"},
    "microsoft.network/publicipaddresses": {"ByteCount": "total"},
    "microsoft.network/loadbalancers": {"ByteCount": "total"},
    "microsoft.network/p2svpngateways": {"P2SConnectionCount": "total"},
}
# The one kind whose day is not read with the default aggregation of its metric: the highest number of connections at one time says whether anybody was connected, and a total of a count that
# is sampled every minute would say connection-minutes.
DELIBERATE = {"p2s-connections": "maximum"}


def day(n: int) -> str:
    return f"{(FIRST + dt.timedelta(days=n)).isoformat()}T00:00:00Z"


class TheTable(unittest.TestCase):
    def test_every_kind_is_complete(self):
        for resource_type, use in TABLE.items():
            with self.subTest(type=resource_type):
                self.assertIsInstance(use, Use)
                self.assertEqual(use.resource_type, resource_type)
                self.assertRegex(resource_type, r"^microsoft\.[a-z]+/[a-z0-9]+$", "a type as Azure writes it, in lower case, with one name after the provider")
                self.assertRegex(use.kind, r"^[a-z0-9]+(-[a-z0-9]+)+$")
                self.assertTrue(use.metrics and all(isinstance(m, str) and m.strip() == m and m and len(m) <= 100 and "," not in m for m in use.metrics), "names that Arm.metrics takes")
                self.assertEqual(len(set(use.metrics)), len(use.metrics))
                self.assertIn(use.combine, usage.COMBINES)
                self.assertIn(use.aggregate, usage.AGGREGATES)
                self.assertIn(use.unit, usage.UNITS)
                self.assertTrue(use.title.endswith(" per day") and use.title[0].isupper(), "the title of a chart says the thing and the period")
                self.assertIsInstance(use.additive, bool)
                self.assertEqual(use.daily, usage.DAILY_WORDS[use.aggregate])

    def test_a_kind_that_takes_the_larger_of_its_metrics_has_more_than_one_and_a_sum_of_two_is_the_traffic_of_a_private_endpoint(self):
        self.assertEqual({use.kind for use in TABLE.values() if use.combine == "max"}, {"ai-calls"})
        self.assertTrue(all(len(use.metrics) > 1 for use in TABLE.values() if use.combine == "max"))
        self.assertEqual({use.kind for use in TABLE.values() if len(use.metrics) > 1 and use.combine == "sum"}, {"pe-traffic"})

    def test_the_kinds_are_the_ones_of_the_brief_and_each_type_has_one_kind_of_its_own(self):
        self.assertEqual(sorted(TABLE), sorted(CONFIRMED), "no type without the metrics that Learn names, and no confirmed type left out")
        self.assertEqual(len(KINDS), len(TABLE), "a key of a kind is stored with a series and says which kind it is: one key for each type")
        self.assertEqual({use.kind: use.resource_type for use in TABLE.values()}, {
            "vm-cpu": "microsoft.compute/virtualmachines", "plan-cpu": "microsoft.web/serverfarms", "pe-traffic": "microsoft.network/privateendpoints",
            "storage-transactions": "microsoft.storage/storageaccounts", "ai-calls": "microsoft.cognitiveservices/accounts", "ip-traffic": "microsoft.network/publicipaddresses",
            "lb-traffic": "microsoft.network/loadbalancers", "p2s-connections": "microsoft.network/p2svpngateways"})

    def test_no_kind_rests_on_a_metric_that_learn_does_not_name_and_a_day_is_read_with_the_aggregation_that_learn_gives_it(self):
        for resource_type, use in TABLE.items():
            with self.subTest(type=resource_type):
                self.assertTrue(set(use.metrics) <= set(CONFIRMED[resource_type]), f"{use.metrics} are not all on the page of Learn")
                defaults = {CONFIRMED[resource_type][metric] for metric in use.metrics}
                self.assertEqual(len(defaults), 1, "the metrics of one kind are read alike")
                self.assertEqual(use.aggregate, DELIBERATE.get(use.kind, next(iter(defaults))))
        self.assertEqual([kind for kind, use in KINDS.items() if CONFIRMED[use.resource_type][use.metrics[0]] != use.aggregate], list(DELIBERATE))

    def test_every_kind_names_the_page_of_learn_that_it_was_read_on(self):
        self.assertEqual(usage.LEARN, "https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/")
        for resource_type, use in TABLE.items():
            with self.subTest(type=resource_type):
                self.assertEqual(use.learn, resource_type.replace("/", "-").replace(".", "-") + "-metrics")

    def test_what_may_be_added_up_is_what_is_a_total_and_a_percentage_or_a_count_at_one_time_may_not(self):
        for use in TABLE.values():
            with self.subTest(kind=use.kind):
                self.assertEqual(use.additive, use.aggregate == "total" and use.unit != "percent")
        self.assertEqual({use.kind for use in TABLE.values() if use.additive}, {"pe-traffic", "storage-transactions", "ai-calls", "ip-traffic", "lb-traffic"})

    def test_the_lines_that_a_chart_is_read_against(self):
        lines = {use.kind: (use.threshold, use.threshold_label) for use in TABLE.values() if use.threshold is not None}
        self.assertEqual(lines, {"vm-cpu": (5.0, "5% idle line"), "p2s-connections": (0.0, "no connection")})
        self.assertEqual(usage.IDLE_CPU_PERCENT, 5.0)
        self.assertEqual(TABLE["microsoft.compute/virtualmachines"].threshold, usage.IDLE_CPU_PERCENT)
        self.assertIsNone(TABLE["microsoft.web/serverfarms"].threshold, "no kind of the app says that an App Service plan is idle below some percentage")
        for use in TABLE.values():
            self.assertEqual(bool(use.threshold_label), use.threshold is not None, use.kind)
            self.assertTrue(use.threshold is None or (math.isfinite(use.threshold) and use.threshold >= 0))

    def test_the_idle_line_is_a_figure_to_read_by_and_the_investigation_is_never_given_it_or_the_table(self):
        importers = []
        for path in sorted((APP_ROOT / "cases").rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and (node.module == "usage" or (not node.module and any(alias.name == "usage" for alias in node.names))):
                    importers.append(path.relative_to(APP_ROOT / "cases").as_posix())
                elif isinstance(node, ast.Import) and any(alias.name.split(".")[-1] == "usage" for alias in node.names):
                    importers.append(path.relative_to(APP_ROOT / "cases").as_posix())
        self.assertEqual(sorted(set(importers)), ["run.py", "web/figures.py"], "the Watch reads from the table and the page draws from it; no agent, tool, rule or judge does (AGENTS.md rule 30 (a))")


class TheEntries(unittest.TestCase):
    def test_a_type_is_found_in_any_case_and_a_thing_that_is_not_a_type_is_not_found(self):
        self.assertEqual(usage.entry_of("Microsoft.Compute/virtualMachines").kind, "vm-cpu")
        self.assertEqual(usage.entry_of("  microsoft.network/privateendpoints ").kind, "pe-traffic")
        for bad in (None, "", "microsoft.compute/disks", "microsoft.compute", 5, ["microsoft.compute/virtualmachines"], "other"):
            with self.subTest(bad=bad):
                self.assertIsNone(usage.entry_of(bad))

    def test_a_resource_is_found_by_its_id_when_the_id_is_the_id_of_one_resource_of_the_type(self):
        sub = "11111111-2222-3333-4444-555555555555"
        good = f"/subscriptions/{sub}/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-1"
        self.assertEqual(usage.for_resource(good, "microsoft.compute/virtualmachines").kind, "vm-cpu")
        self.assertEqual(usage.for_resource(good.lower(), "Microsoft.Compute/virtualMachines").kind, "vm-cpu", "the case of an id is Azure's to choose")
        for bad in (f"{good}/extensions/x", f"/subscriptions/{sub}/resourceGroups/rg-a", f"/subscriptions/{sub}", f"{good}/", f"/subscriptions/{sub}/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/",
                    f"/subscriptions/{sub}/resourceGroups/rg-a/providers/Microsoft.Compute/disks/d1", f"/subscriptions/{sub}/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/..",
                    f"/subscriptions/{sub}/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/.", f"subscriptions/{sub}/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-1",
                    f"/subscriptions/{sub}/resourcegroups//providers/Microsoft.Compute/virtualMachines/vm-1", f"/x/{sub}/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-1", "", None, 7):
            with self.subTest(bad=bad):
                self.assertIsNone(usage.for_resource(bad, "microsoft.compute/virtualmachines"))
        self.assertIsNone(usage.for_resource(good, "microsoft.compute/disks"), "a type that has no kind of use")
        self.assertIsNone(usage.for_resource(good, "microsoft.network/privateendpoints"), "an id of another type than the one that was said")


class TheDays(unittest.TestCase):
    def test_a_bucket_is_a_day_only_when_it_starts_a_utc_day(self):
        self.assertEqual(usage.day_of("2026-10-05T00:00:00Z"), FIRST)
        for bad in ("2026-10-05T02:00:00Z", "2026-10-05T00:00:00+02:00", "2026-10-05T00:00:00.0000000Z", "2026-10-05", "garbage", "", None, 5):
            with self.subTest(bad=bad):
                self.assertIsNone(usage.day_of(bad))

    def test_the_days_are_a_list_of_the_length_that_was_asked_with_a_gap_for_a_day_that_has_no_value(self):
        series = usage.daily([(day(0), 1.5), (day(2), 0.0), (day(29), 2.25)], FIRST)
        self.assertEqual((len(series), series[0], series[1], series[2], series[28], series[29]), (30, 1.5, None, 0.0, None, 2.25))
        self.assertEqual(usage.days_with_value(series), 3)
        self.assertEqual(len(usage.daily([], FIRST, 7)), 7)
        self.assertEqual(usage.daily([], FIRST, 7), [None] * 7)

    def test_a_value_that_is_not_a_finite_number_not_below_zero_is_a_gap_and_never_a_zero(self):
        points = [(day(0), None), (day(1), float("nan")), (day(2), float("inf")), (day(3), -0.5), (day(4), True), (day(5), "7"), (day(6), [1]), (day(7), 0), (day(8), 3)]
        series = usage.daily(points, FIRST)
        self.assertEqual(series[:9], [None, None, None, None, None, None, None, 0.0, 3.0])
        self.assertTrue(all(isinstance(v, float) for v in series if v is not None), "an integer of a bucket is a number of the series")

    def test_a_bucket_outside_the_thirty_days_or_that_is_not_a_utc_day_is_left_out_and_a_later_bucket_of_the_same_day_wins(self):
        points = [(day(-1), 9.0), (day(30), 9.0), ("2026-10-06T12:00:00Z", 9.0), ("garbage", 9.0), (day(5), 1.0), (day(5), 2.0)]
        series = usage.daily(points, FIRST)
        self.assertEqual([i for i, v in enumerate(series) if v is not None], [5])
        self.assertEqual(series[5], 2.0)

    def test_a_value_is_kept_to_a_ten_thousandth(self):
        self.assertEqual(usage.daily([(day(0), 1.23456789), (day(1), 123456789.12345678)], FIRST)[:2], [1.2346, 123456789.1235])

    def test_metrics_of_one_kind_are_put_together_day_by_day(self):
        one, two = [1.0, None, 3.0, None], [10.0, 20.0, None, None]
        self.assertEqual(usage.combine([one, two], "sum"), [11.0, None, None, None], "a sum needs every metric: with a part missing it would be less than the use")
        self.assertEqual(usage.combine([one, two], "max"), [10.0, 20.0, 3.0, None], "the larger of the metrics that are there; none is none")
        self.assertEqual(usage.combine([one], "sum"), one)
        self.assertEqual(usage.combine([[0.1, 0.2], [0.2, 0.1]], "sum"), [0.3, 0.3], "added exactly, and kept to a ten-thousandth")


class TheWords(unittest.TestCase):
    def test_a_percentage_is_as_exact_as_a_person_needs(self):
        for value, text in ((0, "0%"), (0.004, "under 0.01%"), (0.04, "0.04%"), (0.7, "0.7%"), (2.14, "2.1%"), (9.96, "10%"), (12.4, "12%"), (100, "100%")):
            self.assertEqual(usage.value_text("percent", value), text, value)

    def test_bytes_go_by_1024_to_the_unit_that_keeps_the_number_small(self):
        for value, text in ((0, "0 bytes"), (1, "1 byte"), (812, "812 bytes"), (1536, "1.5 KB"), (12.5 * 1024 ** 2, "12.5 MB"), (150 * 1024 ** 2, "150 MB"), (3.5 * 1024 ** 3, "3.5 GB"),
                            (2 * 1024 ** 4, "2 TB"), (5000 * 1024 ** 4, "5,000 TB")):
            self.assertEqual(usage.value_text("bytes", value), text, value)

    def test_a_count_is_a_whole_number_with_thousands_separated(self):
        for value, text in ((0, "0"), (7, "7"), (1204, "1,204"), (1234567, "1,234,567"), (0.5, "0.5"), (2.0, "2")):
            self.assertEqual(usage.value_text("count", value), text, value)

    def test_the_labels_of_an_axis_are_short(self):
        self.assertEqual([usage.axis_text("percent", v, *usage.scale_of("percent", 3)) for v in (0, 4, 8, 0.5)], ["0%", "4%", "8%", "0.5%"])
        divisor, suffix = usage.scale_of("bytes", 3 * 1024 ** 3)
        self.assertEqual((divisor, suffix), (1024.0 ** 3, "GB"))
        self.assertEqual([usage.axis_text("bytes", v, divisor, suffix) for v in (0, 2 * 1024 ** 3, 4 * 1024 ** 3, 512 * 1024 ** 2)], ["0", "2GB", "4GB", "0.5GB"])
        self.assertEqual(usage.scale_of("bytes", 0), (1.0, "B"))
        self.assertEqual(usage.scale_of("count", 5000), (1.0, ""))
        self.assertEqual([usage.axis_text("count", v) for v in (0, 1, 500, 1000, 2000, 400000, 1e6, 2.5e9)], ["0", "1", "500", "1K", "2K", "400K", "1M", "2.5G"])
        for unit, peak in (("percent", 100), ("bytes", 7 * 1024 ** 4), ("bytes", 1000), ("count", 9e9)):
            divisor, suffix = usage.scale_of(unit, peak)
            for value in (0, peak / 2, peak):
                self.assertLessEqual(len(usage.axis_text(unit, value, divisor, suffix)), 6, (unit, peak, value))


class TheConstants(unittest.TestCase):
    def test_a_series_is_thirty_days_and_is_kept_when_twenty_of_them_have_a_value(self):
        self.assertEqual((usage.DAYS, usage.MIN_DAYS), (30, 20))
        self.assertTrue(re.fullmatch(r"\d+", str(usage.DAYS)))


if __name__ == "__main__":
    unittest.main()
