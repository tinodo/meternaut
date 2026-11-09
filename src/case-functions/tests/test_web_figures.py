import re
import unittest

import support  # noqa: F401  (puts the app on the path)
from cases.brief import Saving
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


if __name__ == "__main__":
    unittest.main()
