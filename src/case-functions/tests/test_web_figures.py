import re
import unittest

import support  # noqa: F401  (puts the app on the path)
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


if __name__ == "__main__":
    unittest.main()
