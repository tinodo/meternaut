import datetime as dt
import re
import unittest
from dataclasses import replace

import support  # noqa: F401  (puts the app on the path)
from test_web_support import NOW, SUB, make_advice, make_advice_case, make_case, make_plan

from cases import usage
from cases.brief import Saving, build_brief
from cases.models import GROUP_FACT
from cases.web import figures


class TheSeries(unittest.TestCase):
    def test_a_series_is_a_list_of_two_to_sixty_numbers_that_are_not_below_zero(self):
        self.assertEqual(figures.series_of([1, 2.5, 0]), [1.0, 2.5, 0.0])
        self.assertEqual(len(figures.series_of([0.5] * 60)), 60)
        for bad in (None, "1,2", [1], [], list(range(61)), [1, -0.01], [1, float("nan")], [1, float("inf")], [1, True], [1, "2"], (1, 2), {"a": 1}):
            with self.subTest(bad=bad):
                self.assertIsNone(figures.series_of(bad))

    def test_series_of_one_length_are_added_day_by_day_and_nothing_else_is(self):
        self.assertEqual(figures.summed([[1.0, 2.0], [0.5, 0.5]]), [1.5, 2.5])
        for bad in ([], [[1.0, 2.0], None], [[1.0, 2.0], [1.0, 2.0, 3.0]]):
            with self.subTest(bad=bad):
                self.assertIsNone(figures.summed(bad))

    def test_the_shape_of_a_series_is_said_in_words(self):
        self.assertEqual(figures.describe([4.67] * 30), "flat at about $4.67 a day")
        self.assertEqual(figures.describe([0.0, 0.0]), "no cost on any day")
        self.assertEqual(figures.describe([1.0, 5.0, 3.0]), "from $1.00 to $5.00 a day, $3.00 on the last day")


class TheMoney(unittest.TestCase):
    def test_a_year_is_twelve_times_the_month_in_whole_dollars_and_a_month_has_its_cents(self):
        self.assertEqual([figures.a_year(value) for value in (7.17, 100.74, 358.11, 0.01, 0.0)], ["$86", "$1,209", "$4,297", "under $1", "$0"])
        self.assertEqual((figures.dollars(7.17), figures.dollars(1209.0), figures.dollars(1209.0, cents=False)), ("$7.17", "$1,209.00", "$1,209"))

    def test_only_a_finite_number_is_a_number(self):
        self.assertEqual([figures.number_of(value) for value in (1, 2.5, 0)], [1.0, 2.5, 0.0])
        for bad in (None, True, "1", float("nan"), float("inf"), [1]):
            with self.subTest(bad=bad):
                self.assertIsNone(figures.number_of(bad))


class TheCharts(unittest.TestCase):
    def test_a_chart_starts_at_zero_ends_on_the_last_day_and_has_a_scale_of_round_numbers(self):
        svg = str(figures.chart([1.0, 3.0, 4.67]))
        for label in (">$5<", ">$2.5<", ">$0<", "3 days ago", "yesterday", "last 3 days, yesterday $4.67"):
            self.assertIn(label, svg)
        last = re.search(r'<circle class="dt" cx="352.0" cy="([0-9.]+)"', svg)
        self.assertAlmostEqual(float(last.group(1)), 96 - 88 * 4.67 / 5, places=1)
        self.assertIn('aria-label="Cost per day for the last 3 days: from $1.00 to $4.67 a day, $4.67 on the last day."', svg)

    def test_a_small_chart_has_a_line_an_area_and_a_dot_on_the_last_day_and_says_in_words_what_it_shows(self):
        svg = str(figures.spark([1.0] * 30))
        self.assertEqual(len(re.findall(r"<path", svg)), 2)
        self.assertEqual(len(re.findall(r"<circle", svg)), 1)
        self.assertIn('aria-label="Cost per day, last 30 days: flat at about $1.00 a day."', svg)
        self.assertIn('class="sp"', svg)

    def test_without_a_series_a_chart_says_so_in_words_and_why(self):
        svg = str(figures.spark(None))
        self.assertIn('class="sp none"', svg)
        self.assertIn("No daily costs yet", svg)
        self.assertIn(figures.NO_LINES, svg)
        self.assertIn(figures.READ_LATER, str(figures.spark(None, figures.READ_LATER)))
        self.assertIn(f"{figures.READ_LATER} The chart fills in then.", str(figures.chart(None, figures.READ_LATER)))

    def test_a_series_of_zeros_is_drawn_on_the_floor_and_never_divides_by_zero(self):
        for series in ([0.0, 0.0], [0.0] * 30):
            with self.subTest(days=len(series)):
                svg = str(figures.chart(series)) + str(figures.spark(series))
                self.assertNotRegex(svg, r"nan|inf")
                self.assertIn(">$1<", svg)

    def test_a_bar_is_never_less_than_a_sliver_or_more_than_the_whole(self):
        widths = [re.search(r'<rect class="bv" width="(\d+)"', str(figures.bar(share))).group(1) for share in (0.0, 0.004, 0.5, 1.0, 5.0)]
        self.assertEqual(widths, ["2", "2", "50", "100", "100"])

    def test_a_chip_is_a_word_and_a_shape_and_its_word_is_escaped(self):
        chip = str(figures.chip("<b>x</b>", "low", "circle"))
        self.assertEqual(chip, '<span class="chip low"><svg viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="4"/></svg>&lt;b&gt;x&lt;/b&gt;</span>')
        self.assertIn('class="chip"', str(figures.chip("Needs measuring")))

    def test_a_figure_holds_numbers_and_the_names_of_the_stylesheet_and_nothing_else(self):
        for part in (figures.chart([1.0, 2.0]), figures.spark([1.0, 2.0]), figures.spark(None), figures.bar(0.5), figures.chip("Low risk", "low", "circle")):
            with self.subTest(part=str(part)[:40]):
                self.assertNotRegex(str(part), r"\sstyle\s*=|#[0-9a-fA-F]{3,8}\b|<script|url\(")


class TheFigure(unittest.TestCase):
    def saving(self, monthly, level="Expected", basis="the cost lines of the last 30 days"):
        return Saving(monthly, level, basis, None, "")

    def test_a_saving_is_the_figure_when_every_request_has_one_and_it_says_its_level_and_its_basis(self):
        one = figures.figure_of([self.saving(30.0)], [215.1])
        self.assertEqual((one.state, one.label, one.monthly, one.level, one.note), ("save", "Saves, Expected", 30.0, "Expected", "Based on the cost lines of the last 30 days."))
        many = figures.figure_of([self.saving(30.0), self.saving(10.0, "Scenario", "Azure Advisor's own estimate")], [None, None], "the figures of each, added up")
        self.assertEqual((many.label, many.monthly, many.note), ("Saves, Scenario", 40.0, "Based on the figures of each, added up."), "the weakest level of them")
        verified = figures.figure_of([self.saving(30.0, "Verified"), self.saving(1.0)], [None, None], "the figures of each, added up")
        self.assertEqual(verified.level, "Expected")

    def test_without_a_saving_the_cost_is_the_figure_and_without_a_cost_nothing_is_and_the_reason_is_said(self):
        cost = figures.figure_of([self.saving(None)], [10.0, None, 5.0])
        self.assertEqual((cost.state, cost.label, cost.monthly, cost.level), ("cost", "Costs, saving not measured", 15.0, ""))
        self.assertIn("what it would save was not worked out", cost.note)
        free = figures.figure_of([self.saving(None)], [0.0])
        self.assertEqual((free.state, free.label, free.monthly, free.note), ("none", "Cost not visible", None, "No cost line in the last 30 days."))
        unread = figures.figure_of([self.saving(None)], [None])
        self.assertEqual((unread.state, unread.note), ("none", "No cost line was read yet."))
        self.assertEqual(figures.figure_of([], []).state, "none")

    def test_one_saving_without_a_figure_among_many_makes_the_row_a_cost_and_never_a_partial_sum(self):
        mixed = figures.figure_of([self.saving(30.0), self.saving(None)], [5.0, 6.0])
        self.assertEqual((mixed.state, mixed.monthly), ("cost", 11.0))

    def test_a_risk_chip_is_a_word_and_a_shape_and_an_unknown_risk_is_read_as_medium(self):
        self.assertEqual([figures.RISKS[level][0] for level in ("low", "medium", "high")], ["Low risk", "Medium risk", "High risk"])
        self.assertIn('class="chip low"><svg viewBox="0 0 12 12" aria-hidden="true"><circle', str(figures.risk_chip("low")))
        self.assertIn('class="chip high"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1 11 6 6 11 1 6z"', str(figures.risk_chip("high")))
        self.assertEqual(str(figures.risk_chip("unheard of")), str(figures.risk_chip("medium")))


VM = usage.TABLE["microsoft.compute/virtualmachines"]
PE = usage.TABLE["microsoft.network/privateendpoints"]
P2S = usage.TABLE["microsoft.network/p2svpngateways"]
STORAGE = usage.TABLE["microsoft.storage/storageaccounts"]
TODAY, YESTERDAY = dt.date(2026, 11, 9), "2026-11-08"
GB = 1024 ** 3
CLASSES = {"chart", "gl", "ax", "thr", "thr-t", "ar", "ln", "dt", "m"}


def drawn(use, values, end=YESTERDAY, today=TODAY) -> str:
    return str(figures.use_chart(use, values, end, today))


def stretches(svg: str, name: str) -> list[list[tuple[float, float]]]:
    """The stretches of the path of a class (ln or ar) as lists of (x, y): a path of a broken line has one `M` for each."""
    found = re.search(rf'<path class="{name}" d="([^"]*)"', svg)
    return [[(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", part)] for part in found.group(1).split("M")[1:]] if found else []


def labels(svg: str) -> list[str]:
    """The text of every axis label, in the order of the chart: the three lines of the scale and the two ends of the time axis."""
    return re.findall(r'<text class="ax"[^>]*>([^<]*)</text>', svg)


def circles(svg: str) -> list[tuple[float, float, int]]:
    return [(float(x), float(y), int(r)) for x, y, r in re.findall(r'<circle class="dt" cx="([\d.]+)" cy="([\d.]+)" r="(\d)"/>', svg)]


class TheSeriesOfUse(unittest.TestCase):
    def test_a_series_of_use_is_two_to_sixty_entries_that_are_a_number_not_below_zero_or_none_and_one_of_them_is_a_number(self):
        self.assertEqual(figures.use_values([1, None, 2.5, 0]), [1.0, None, 2.5, 0.0])
        self.assertEqual(len(figures.use_values([None] * 59 + [1.0])), 60)
        for bad in (None, "1,2", [1.0], [], [1.0] * 61, [1, -0.01], [1, float("nan")], [1, float("inf")], [1, True], [1, "2"], (1, 2), {"a": 1}, [None, None], [None] * 30):
            with self.subTest(bad=bad):
                self.assertIsNone(figures.use_values(bad))

    def test_a_day_is_a_date_of_ten_characters_and_nothing_else_is(self):
        self.assertEqual(figures.kept_day("2026-11-04"), dt.date(2026, 11, 4))
        for bad in ("2026-11-4", "2026-13-01", "20261104", "2026-11-04T00:00:00Z", None, 20261104, "", "garbage"):
            with self.subTest(bad=bad):
                self.assertIsNone(figures.kept_day(bad))


class TheUseOfACase(unittest.TestCase):
    @staticmethod
    def machine(**changes):
        base = dict(resource_type="microsoft.compute/virtualmachines", use_series=[1.0, None] * 15, use_series_end="2026-11-04", use_kind="vm-cpu")
        return make_case(**{**base, **changes})

    def test_a_case_of_one_resource_of_a_type_with_a_kind_that_holds_a_series_of_that_kind_has_its_use(self):
        data = figures.use_of(self.machine())
        self.assertEqual((data.use.kind, data.values, data.end), ("vm-cpu", [1.0, None] * 15, "2026-11-04"))
        self.assertEqual(figures.use_of(self.machine(resource_type="Microsoft.Compute/virtualMachines")).use.kind, "vm-cpu", "the case of the type is Azure's")

    def test_a_case_that_has_nothing_to_draw_has_no_use(self):
        group = {"count": 4, "type": "microsoft.compute/virtualmachines", "groups": 1, "names": [], "costUsd30d": 1.0}
        for name, case in (("no case", None), ("no series", self.machine(use_series=None)), ("another kind", self.machine(use_kind="plan-cpu")), ("no kind", self.machine(use_kind=None)),
                           ("a type with no kind of use", self.machine(resource_type="microsoft.compute/disks")), ("a case of a group", self.machine(facts={GROUP_FACT: group})),
                           ("a series that is not one", self.machine(use_series=[1.0])), ("a series of nothing", self.machine(use_series=[None] * 30))):
            with self.subTest(name):
                self.assertIsNone(figures.use_of(case))

    def test_the_day_that_a_series_ends_on_is_known_only_when_it_is_a_day(self):
        self.assertIsNone(figures.use_of(self.machine(use_series_end="garbage")).end)
        self.assertIsNone(figures.use_of(self.machine(use_series_end=None)).end)


class TheSumOfUse(unittest.TestCase):
    @staticmethod
    def data(use, values, end=YESTERDAY):
        return figures.UseData(use, values, end)

    def test_the_use_of_several_requests_is_added_up_day_by_day_for_a_kind_that_may_be_added(self):
        total = figures.use_summed([self.data(STORAGE, [1.0, 2.0, 3.0]), self.data(STORAGE, [10.0, 20.0, 30.0]), self.data(STORAGE, [100.0, 200.0, 300.0])])
        self.assertEqual((total.use, total.values, total.end), (STORAGE, [111.0, 222.0, 333.0], YESTERDAY))

    def test_a_day_that_one_of_them_has_no_value_for_is_a_gap_and_never_the_sum_of_the_others(self):
        total = figures.use_summed([self.data(STORAGE, [1.0, None, 3.0]), self.data(STORAGE, [10.0, 20.0, None])])
        self.assertEqual(total.values, [11.0, None, None])

    def test_nothing_is_added_that_may_not_be_added_or_that_is_not_of_one_kind_or_one_length_or_that_is_not_there(self):
        self.assertIsNone(figures.use_summed([self.data(VM, [1.0, 2.0]), self.data(VM, [1.0, 2.0])]), "a percentage")
        self.assertIsNone(figures.use_summed([self.data(P2S, [1.0, 2.0]), self.data(P2S, [1.0, 2.0])]), "connections at one time")
        self.assertIsNone(figures.use_summed([self.data(STORAGE, [1.0, 2.0]), self.data(PE, [1.0, 2.0])]), "two kinds")
        self.assertIsNone(figures.use_summed([self.data(STORAGE, [1.0, 2.0]), self.data(STORAGE, [1.0, 2.0, 3.0])]), "two lengths")
        self.assertIsNone(figures.use_summed([self.data(STORAGE, [1.0, 2.0]), None]), "one without a series")
        self.assertIsNone(figures.use_summed([]))

    def test_the_end_of_a_sum_is_the_end_of_its_parts_when_they_have_one_and_not_known_when_they_differ(self):
        self.assertEqual(figures.use_summed([self.data(STORAGE, [1.0, 2.0], "2026-11-03"), self.data(STORAGE, [1.0, 2.0], "2026-11-04")]).end, None)
        self.assertEqual(figures.use_summed([self.data(STORAGE, [1.0, 2.0], None), self.data(STORAGE, [1.0, 2.0], None)]).end, None)


class TheUseChart(unittest.TestCase):
    def test_the_chart_starts_at_zero_ends_on_the_last_day_and_says_what_it_is_in_a_caption_and_in_a_sentence(self):
        svg = drawn(VM, [0.8, 0.9, 0.7, 3.9, 0.6, 2.1])
        self.assertEqual(labels(svg), ["8%", "4%", "0%", "6 days ago", "yesterday"])
        self.assertIn("<figcaption>CPU use per day <span>daily average, last 6 days, yesterday 2.1%</span></figcaption>", svg)
        self.assertIn('aria-label="CPU use per day (daily average) for the last 6 days: from 0.6% to 3.9%, 2.1% on the last day, at or under the 5% idle line on 6 of 6 days with data."', svg)
        (line,) = stretches(svg, "ln")
        self.assertEqual((line[0][0], line[-1][0]), (40.0, 352.0))
        self.assertEqual(circles(svg), [(352.0, line[-1][1], 3)])
        self.assertAlmostEqual(line[-1][1], 96 - 88 * 2.1 / 8, places=1)

    def test_every_point_is_inside_the_plot_and_none_is_below_zero_for_any_unit_and_size(self):
        cases = [(VM, [0.0] * 30), (VM, [100.0] * 30), (VM, [0.01, 99.9] * 15), (PE, [0.0] * 30), (PE, [3 * GB] * 30), (PE, [1.0, 1e15] * 15), (STORAGE, [1.0] * 30), (STORAGE, [4e9, 0.0] * 15),
                 (P2S, [0.0] * 30), (P2S, [0.0] * 29 + [1.0]), (P2S, [12.0] * 30)]
        for use, values in cases:
            with self.subTest(kind=use.kind, peak=max(values)):
                svg = drawn(use, values)
                self.assertNotRegex(svg, r"nan|inf")
                for part in stretches(svg, "ln") + stretches(svg, "ar"):
                    for x, y in part:
                        self.assertTrue(40 <= x <= 352 and 8 <= y <= 96, (x, y))
                for label in labels(svg):
                    self.assertLessEqual(len(label), 11, label)
                for label in labels(svg)[:3]:
                    self.assertLessEqual(len(label), 6, f"{label}: the scale stands in a margin of 34 units")

    def test_a_series_of_zeros_is_drawn_on_the_floor_with_a_scale_that_is_not_empty(self):
        for use, scale in ((VM, ["8%", "4%", "0%"]), (PE, ["1KB", "0.5KB", "0"]), (STORAGE, ["2", "1", "0"]), (P2S, ["2", "1", "0"])):
            with self.subTest(kind=use.kind):
                svg = drawn(use, [0.0] * 30)
                self.assertEqual(labels(svg)[:3], scale)
                self.assertEqual({y for _, y in stretches(svg, "ln")[0]}, {96.0})
                self.assertIn("zero on every day with data", svg)

    def test_the_ceiling_is_a_round_number_that_holds_the_peak_and_the_line_with_room_above_it(self):
        for peak, top in ((0.7, "8%"), (5.0, "8%"), (7.9, "8%"), (8.0, "8%"), (8.1, "10%"), (20.0, "20%"), (39.0, "40%"), (62.0, "80%"), (100.0, "100%")):
            with self.subTest(peak=peak):
                svg = drawn(VM, [peak * 0.5, peak] * 15)
                self.assertEqual(labels(svg)[0], top)
                ceiling = float(top.rstrip("%"))
                self.assertGreaterEqual(ceiling, peak)
                self.assertGreaterEqual(ceiling, 1.5 * usage.IDLE_CPU_PERCENT, "the line has room above it")
                y = float(re.search(r'<line class="thr" x1="40" y1="([\d.]+)"', svg).group(1))
                self.assertAlmostEqual(y, 96 - 88 * 5.0 / ceiling, places=1)
                self.assertGreaterEqual(y - 4, 8 + 29, "and so has the name of the line: it is not cut off at the top")

    def test_the_line_that_a_chart_is_read_against_is_dashed_named_and_at_the_height_of_its_value(self):
        svg = drawn(VM, [1.0] * 30)
        self.assertIn('<line class="thr" x1="40" y1="41.0" x2="352" y2="41.0"/><text class="thr-t" x="348" y="37.0" text-anchor="end">5% idle line</text>', svg)
        self.assertLess(svg.index('class="thr"'), svg.index('class="ar"'), "under the data, as the style guide draws it")
        floor = drawn(P2S, [0.0, 3.0] * 15)
        self.assertIn('<line class="thr" x1="40" y1="96.0" x2="352" y2="96.0"/><text class="thr-t" x="348" y="92.0" text-anchor="end">no connection</text>', floor)
        for use in (PE, STORAGE, usage.TABLE["microsoft.web/serverfarms"]):
            self.assertNotIn("thr", drawn(use, [1.0, 2.0, 3.0]), use.kind)

    def test_the_line_is_broken_at_a_day_with_no_value_and_the_area_with_it_and_nothing_is_drawn_for_the_day(self):
        values = [1.0, 2.0, 3.0, None, 5.0, 6.0, None, None, 2.0, 1.0]
        svg = drawn(P2S, values)
        line, area = stretches(svg, "ln"), stretches(svg, "ar")
        step = (352 - 40) / 9
        self.assertEqual([[round((x - 40) / step) for x, _ in part] for part in line], [[0, 1, 2], [4, 5], [8, 9]])
        self.assertEqual([[round((x - 40) / step) for x, _ in part if _ != 96.0] for part in area], [[0, 1, 2], [4, 5], [8, 9]], "each stretch has its own area, down to the floor")
        self.assertEqual(svg.count("M"), len(line) + len(area) + 0, "one move for each stretch of the line and of the area")
        self.assertEqual(len(re.findall(r" Z", svg)), 3)
        for day in (3, 6, 7):
            self.assertNotIn(f"{40 + day * step:.1f},", svg, "no point on a day that has no value")

    def test_a_value_between_two_gaps_is_a_dot_and_the_last_day_with_a_value_has_the_dot_of_the_last_day(self):
        svg = drawn(P2S, [None, 2.0, None, 4.0, None, None])
        self.assertEqual(stretches(svg, "ln"), [], "nothing to join")
        self.assertNotIn('class="ln"', svg)
        step = 312 / 5
        self.assertEqual([(round((x - 40) / step), r) for x, _, r in circles(svg)], [(1, 2), (3, 3)], "a small dot for each lone value, and the larger dot on the last day with a value")
        self.assertIn("4 days without data are left blank.", svg)

    def test_a_series_of_one_value_is_a_dot_and_never_a_division_by_zero(self):
        svg = drawn(VM, [None] * 29 + [3.0])
        self.assertEqual(circles(svg), [(352.0, 96 - 88 * 3.0 / 8, 3)])
        self.assertIn("flat at about 3%, at or under the 5% idle line on 1 of 1 days with data. 29 days without data are left blank.", svg)
        two = drawn(VM, [1.0, 2.0])
        self.assertEqual([x for x, _ in stretches(two, "ln")[0]], [40.0, 352.0])
        self.assertIn("for the last 2 days", two)

    def test_a_chart_with_nothing_to_draw_is_the_quiet_figure(self):
        for values in ([], [1.0], [None, None, None]):
            with self.subTest(values=values):
                svg = drawn(VM, values)
                self.assertNotIn("<svg", svg)
                self.assertIn(figures.USE_LATER, svg)

    def test_the_sentence_says_how_the_use_runs_and_how_it_stands_to_the_line_and_how_many_days_are_blank(self):
        for use, values, said in (
                (VM, [0.7] * 30, "CPU use per day (daily average) for the last 30 days: flat at about 0.7%, at or under the 5% idle line on 30 of 30 days with data."),
                (VM, [0.8] * 26 + [7.5, 7.5, 0.8, 2.1], "CPU use per day (daily average) for the last 30 days: from 0.8% to 7.5%, 2.1% on the last day, at or under the 5% idle line on 28 of 30 days with data."),
                (VM, [0.8] * 29 + [None], "CPU use per day (daily average) for the last 30 days: flat at about 0.8%, at or under the 5% idle line on 29 of 29 days with data. 1 day without data is left blank."),
                (VM, [0.8, 2.0, 3.0] + [None] * 27, "CPU use per day (daily average) for the last 30 days: from 0.8% to 3%, 3% on the last day with data, at or under the 5% idle line on 3 of 3 days with data. "
                                                      "27 days without data are left blank."),
                (P2S, [0.0] * 30, "Connections per day (daily highest) for the last 30 days: zero on every day with data, at or under the no connection line on 30 of 30 days with data."),
                (P2S, [0.0, 3.0] * 15, "Connections per day (daily highest) for the last 30 days: from 0 to 3, 3 on the last day, at or under the no connection line on 15 of 30 days with data."),
                (PE, [1.5 * GB] * 30, "Traffic per day for the last 30 days: flat at about 1.5 GB."),
                (PE, [512.0, 2 * GB], "Traffic per day for the last 2 days: from 512 bytes to 2 GB, 2 GB on the last day."),
                (STORAGE, [1204.0, 1500.0, 1210.0], "Transactions per day for the last 3 days: from 1,204 to 1,500, 1,210 on the last day.")):
            with self.subTest(kind=use.kind, said=said[-40:]):
                self.assertIn(f'aria-label="{said}"', drawn(use, values))

    def test_the_caption_names_the_last_day_with_a_value_as_yesterday_or_by_its_date_or_as_the_last_day(self):
        values = [1.0] * 28 + [2.5, 3.5]
        for end, today, said in ((YESTERDAY, TODAY, "last 30 days, yesterday 3.5"), ("2026-11-06", TODAY, "last 30 days, 3.5 on Fri 6 Nov"), (YESTERDAY, None, "last 30 days, 3.5 on Sun 8 Nov"),
                                 (None, TODAY, "last 30 days, 3.5 on the last day"), ("garbage", TODAY, "last 30 days, 3.5 on the last day")):
            with self.subTest(end=end, today=today):
                svg = drawn(STORAGE, values, end, today)
                self.assertIn(f"<span>{said}</span>", svg)
        gap = drawn(STORAGE, values[:-1] + [None], YESTERDAY, TODAY)
        self.assertIn("<span>last 30 days, 2.5 on Sat 7 Nov</span>", gap, "the last value was not yesterday's")
        self.assertIn("<span>last 30 days, 2.5 on the last day with data</span>", drawn(STORAGE, values[:-1] + [None], None, TODAY))

    def test_the_two_ends_of_the_time_axis_are_the_days_when_the_chart_does_not_end_yesterday(self):
        values = [1.0] * 30
        self.assertEqual(labels(drawn(STORAGE, values, YESTERDAY, TODAY))[3:], ["30 days ago", "yesterday"])
        self.assertEqual(labels(drawn(STORAGE, values, "2026-11-06", TODAY))[3:], ["Thu 8 Oct", "Fri 6 Nov"])
        self.assertEqual(labels(drawn(STORAGE, values, None, TODAY))[3:], ["first day", "last day"])
        self.assertEqual(labels(drawn(STORAGE, values, YESTERDAY, None))[3:], ["Sat 10 Oct", "Sun 8 Nov"])

    def test_the_numbers_of_the_scale_and_of_the_caption_are_in_the_unit_of_the_kind_and_the_size_of_the_values(self):
        self.assertEqual(labels(drawn(PE, [3 * GB] * 30))[:3], ["4GB", "2GB", "0"])
        self.assertEqual(labels(drawn(PE, [700 * 1024 ** 2] * 30))[:3], ["800MB", "400MB", "0"])
        self.assertEqual(labels(drawn(PE, [900.0] * 30))[:3], ["1000B", "500B", "0"])
        self.assertEqual(labels(drawn(STORAGE, [3.0e6] * 30))[:3], ["4M", "2M", "0"])
        self.assertEqual(labels(drawn(STORAGE, [750.0] * 30))[:3], ["800", "400", "0"])
        self.assertEqual(labels(drawn(VM, [62.0] * 30))[:3], ["80%", "40%", "0%"])
        self.assertIn("yesterday 2.33 GB", drawn(PE, [1.0, 2.5e9]))
        self.assertIn("yesterday 12", drawn(P2S, [1.0, 12.0]))

    def test_a_chart_holds_numbers_and_the_names_of_the_stylesheet_and_nothing_else(self):
        for svg in (drawn(VM, [0.7, None, 2.0] * 10), drawn(P2S, [0.0] * 30), drawn(PE, [1e9, None] * 15), str(figures.use_quiet(VM, figures.USE_LATER))):
            with self.subTest(svg=svg[:60]):
                self.assertNotRegex(svg, r"\sstyle\s*=|#[0-9a-fA-F]{3,8}\b|<script|url\(|\d+px|javascript|\bon[a-z]+=")
                self.assertLessEqual(set(re.findall(r'class="([^"]+)"', svg)), CLASSES)

    def test_what_is_put_into_a_chart_is_escaped_though_the_kinds_are_the_code_s_own(self):
        hostile = usage.Use("x-y", "microsoft.x/y", ("M",), "sum", "total", "count", '<img src=x onerror=1> per day', True, "x", 1.0, "<script>alert(1)</script>")
        svg = drawn(hostile, [0.5, 1.0, 2.0])
        self.assertNotIn("<img", svg)
        self.assertNotIn("<script", svg)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", svg)
        self.assertIn("&lt;img src=x onerror=1&gt; per day", svg)
        quiet = str(figures.use_quiet(hostile, "<b>why</b>"))
        self.assertNotIn("<b>", quiet)
        self.assertIn("&lt;b&gt;why&lt;/b&gt;", quiet)

    def test_the_quiet_figure_is_a_caption_and_a_reason_and_no_drawing(self):
        self.assertEqual(str(figures.use_quiet(VM, "A reason.")), '<figure class="chart"><figcaption>CPU use per day <span>no use figures yet</span></figcaption><p class="m">A reason.</p></figure>')
        self.assertIn("<span>not drawn</span>", str(figures.use_quiet(PE, figures.USE_MANY, "not drawn")))
        self.assertEqual(figures.USE_LATER, "Azure Monitor shows use a few hours after it happens. The next search reads it. A chart is drawn once 20 of the last 30 days have a value: "
                                            "a new resource, a stopped machine and a resource that does not offer this metric have fewer.")
        self.assertEqual(figures.USE_MANY, "Use is not drawn for a finding about many resources.")


class TheUseOfWhatACardStandsFor(unittest.TestCase):
    """figures.use_block: what a decision card shows of use under its cost chart, for one request or for a row of several."""

    @staticmethod
    def request(n, resource_type, kind=None, series=None, **changes):
        rid = f"/subscriptions/{SUB}/resourceGroups/rg-{n}/providers/{resource_type.replace('microsoft.', 'Microsoft.')}/r{n}"
        case = make_advice_case(case_id=f"c{n}", plan_id=f"p{n}", resource_id=rid, resource_name=f"r{n}", resource_type=resource_type, use_series=series,
                                use_series_end="2026-11-04" if series else None, use_kind=kind, **changes)
        plan = make_advice(plan_id=f"p{n}", case_id=f"c{n}", resource_id=rid, resource_name=f"r{n}")
        return build_brief(case, plan, now=NOW), case

    def block(self, *members):
        return str(figures.use_block(list(members), NOW))

    def test_one_request_of_a_resource_with_a_series_has_the_chart_and_without_one_the_quiet_figure_and_the_reason(self):
        shown = self.block(self.request(1, "microsoft.compute/virtualmachines", "vm-cpu", [0.5] * 30))
        self.assertIn("<svg", shown)
        self.assertIn("<span>daily average, last 30 days, yesterday 0.5%</span>", shown)
        quiet = self.block(self.request(1, "microsoft.compute/virtualmachines"))
        self.assertNotIn("<svg", quiet)
        self.assertIn(figures.USE_LATER, quiet)

    def test_nothing_is_shown_for_a_type_that_has_no_kind_of_use_or_for_no_case(self):
        self.assertEqual(self.block(self.request(1, "microsoft.compute/disks")), "")
        brief, _ = self.request(1, "microsoft.compute/virtualmachines")
        self.assertEqual(self.block((brief, None)), "")

    def test_a_finding_about_many_resources_is_the_quiet_figure_with_its_own_reason_when_its_type_has_a_kind_and_nothing_when_it_has_none(self):
        group = {"basis": "idle", GROUP_FACT: {"count": 4, "groups": 2, "type": "microsoft.network/privateendpoints", "names": ["a"], "costUsd30d": 9.0}}
        shown = self.block(self.request(1, "microsoft.network/privateendpoints", "pe-traffic", [1.0] * 30, facts=group))
        self.assertIn(figures.USE_MANY, shown)
        self.assertIn("<span>not drawn</span>", shown)
        self.assertNotIn("<svg", shown)
        other = {"basis": "idle", GROUP_FACT: {"count": 4, "groups": 2, "type": "other", "names": [], "costUsd30d": 9.0}}
        self.assertEqual(self.block(self.request(1, "microsoft.network/privateendpoints", facts=other)), "")

    def test_the_requests_of_a_row_are_added_up_for_a_kind_that_may_be_added_and_only_when_every_one_has_a_series_of_it(self):
        members = [self.request(n, "microsoft.storage/storageaccounts", "storage-transactions", [100.0 * n] * 30) for n in (1, 2, 3)]
        shown = self.block(*members)
        self.assertIn("<span>last 30 days, yesterday 600</span>", shown)
        self.assertIn("flat at about 600.", shown)
        for name, changed in (("one has none", [*members[:2], self.request(3, "microsoft.storage/storageaccounts", "storage-transactions")]),
                              ("one is of another kind", [*members[:2], self.request(3, "microsoft.network/privateendpoints", "pe-traffic", [1.0] * 30)]),
                              ("one has a series of another kind", [*members[:2], self.request(3, "microsoft.storage/storageaccounts", "pe-traffic", [1.0] * 30)]),
                              ("none is of a type with a kind", [self.request(n, "microsoft.compute/disks") for n in (1, 2)])):
            with self.subTest(name):
                self.assertEqual(self.block(*changed), "", "nothing: the quiet figure is for one request")

    def test_the_requests_of_a_row_of_a_kind_that_may_not_be_added_draw_nothing(self):
        members = [self.request(n, "microsoft.compute/virtualmachines", "vm-cpu", [0.5] * 30) for n in (1, 2)]
        self.assertEqual(self.block(*members), "", "the sum of two percentages is not a percentage")

    def test_a_day_without_a_value_in_any_of_the_requests_of_a_row_is_a_gap_in_the_sum(self):
        first = self.request(1, "microsoft.storage/storageaccounts", "storage-transactions", [10.0] * 29 + [None])
        second = self.request(2, "microsoft.storage/storageaccounts", "storage-transactions", [20.0] * 30)
        shown = self.block(first, second)
        self.assertIn("1 day without data is left blank.", shown)
        self.assertIn("flat at about 30", shown)


if __name__ == "__main__":
    unittest.main()
