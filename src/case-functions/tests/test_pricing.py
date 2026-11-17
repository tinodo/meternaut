"""What a finding's change would save, worked out from the bill (cases/pricing.py): the typed block that the Investigator states, what code checks of it against what the tools showed, the
arithmetic, the words that say what it rests on, and what the second AI is shown of it. Every kind of resource, meter and number here is INVENTED.

The first part tests the module by itself. The second runs whole investigations with fakes (the Skeptic, the cases, the History), and shows that the findings that the removed modules priced
by kind are priced by the generic path. The third prices a change from the meters of the real toolbox.
"""
import ast
import dataclasses
import datetime as dt
import json
import math
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from support import APP_ROOT, NOW, SUBSCRIPTION

from cases import agents, brief, decide, investigate, pricing
from cases.detectors import Context
from cases.foundry import AgentRun
from cases.meters import Meter, rates
from cases.roles import DetectiveAnswer, SkepticAnswer
from test_investigate import HOSTILE, SAFE, FakeFoundry, FakeToolbox, Harness, agree_all, answer, finding, handles_of, meter_line, metrics, resource, verdicts
from test_toolbox import toolbox as real_toolbox
from test_toolbox_meters import WIDGET, widgets

START = dt.date(2026, 10, 5)
COMPUTE = ("Example Compute", "Standard Tier", "Fixed Hours", "OnDemand", "Usage", "1 Hour")
STORAGE = ("Example Storage", "Premium Tier", "Held Data", "OnDemand", "Usage", "1 GB/Month")
NETWORK = ("Example Network", "Standard Tier", "Moved Data", "OnDemand", "Usage", "1 GB")


def line(scope: str, usd: float, words=COMPUTE, days: int = 30, service=None, resources=None) -> Meter:
    """A meter of one scope over `days` closed days that cost `usd` in all, the same on each day."""
    daily = {START + dt.timedelta(days=n): usd / days for n in range(days)}
    return Meter(scope, service, words, 24.0 * days, usd, daily, resources, START, days)


def shaped(scope: str, costs, days: int = 30, words=COMPUTE) -> Meter:
    """A meter of one scope over `days` closed days whose last len(costs) days cost what `costs` says, day by day: the days before have no line."""
    first = days - len(costs)
    daily = {START + dt.timedelta(days=first + n): cost for n, cost in enumerate(costs)}
    return Meter(scope, None, words, 24.0 * len(costs), math.fsum(costs), daily, None, START, days)


UNITS = ("Example Gateway", "Standard Tier", "Extra Units", "OnDemand", "Usage", "1 Hour")


def billed_units(usd: float = 201.60, quantity: float = 1440.0, scope: str = "r1", days: int = 30, words=UNITS) -> Meter:
    """A meter that bills only the units above the included ones: `quantity` unit-hours that cost `usd` over `days` days, the same on each day (invented: 2 units for 720 hours of a resource with 4)."""
    return Meter(scope, None, words, quantity, usd, {START + dt.timedelta(days=n): usd / days for n in range(days)}, None, START, days)


def registry() -> dict[str, Meter]:
    return {"m1": line("r1", 60.0), "m2": line("r1", 40.0, STORAGE), "m3": line("r2", 30.0), "m4": line("r1", 25.0, NETWORK)}


def shown(**more):
    """What a Toolbox holds after a run, as far as the pricing reads it: the register of the meters and the evidence of the handles."""
    values = dict(meters=registry(), evidence={"r1": {"properties": {"units": 12, "tier": "Standard"}, "metrics": {"Used Units": {"total": 90.0, "max": 11.0, "average": 3.0, "totals": [90.0]}}},
                                                "r2": {"properties": {"units": 4}}})
    values.update(more)
    return SimpleNamespace(**values)


COSTS = {"r1": 100.0, "r2": 30.0}


def block(action="remove", *effects, how="Take it away."):
    return {"action": action, "effects": list(effects), "how": how}


def effect(handle="r1", meters=("m1", "m2"), remains=None):
    return {"handle": handle, "meters": list(meters), "remains": remains if remains is not None else {"form": "none"}}


def priced(raw, handles=("r1", "r2"), toolbox=None, costs=None, blocked=None):
    return pricing.price(pricing.parse(raw), handles, toolbox or shown(), COSTS if costs is None else costs, blocked)


class TheRatesOfAMeter(unittest.TestCase):
    """What a meter costs a month, worked out by hand from its daily cost: at the rate of its last 7 days and at the mean since its first day, over the window of 30 days that starts on START."""

    def check(self, found, week, since, life, began):
        self.assertAlmostEqual(found.week, week, places=6)
        self.assertEqual(None if found.since is None else round(found.since, 6), since)
        self.assertEqual((found.life, found.began), (life, began))

    def test_a_flat_meter_has_the_same_rate_on_every_basis(self):
        found = rates(shaped("r1", [2.0] * 30))
        self.check(found, 60.0, 60.0, 30, False)
        self.assertAlmostEqual(found.cv, 0.0)

    def test_a_meter_that_began_four_days_ago_has_the_rate_of_its_own_four_days_and_no_second_basis(self):
        self.check(rates(shaped("r1", [8.0] * 4)), 240.0, None, 4, True)

    def test_a_meter_that_began_inside_the_window_has_a_mean_since_it_began_when_it_has_more_than_a_week(self):
        self.check(rates(shaped("r1", [3.0] * 7)), 90.0, None, 7, True)
        self.check(rates(shaped("r1", [1.0] * 5 + [4.0] * 5)), 22.0 / 7 * 30, 75.0, 10, True)

    def test_a_rate_that_doubled_in_the_last_week_has_the_new_rate_as_the_week_and_the_month_total_as_the_mean(self):
        self.check(rates(shaped("r1", [1.0] * 23 + [2.0] * 7)), 60.0, 37.0, 30, False)

    def test_a_rate_that_halved_in_the_last_week_has_the_new_rate_as_the_week_and_the_month_total_as_the_mean(self):
        self.check(rates(shaped("r1", [2.0] * 23 + [1.0] * 7)), 30.0, 53.0, 30, False)

    def test_a_meter_that_stopped_has_a_week_of_nothing_and_the_mean_of_what_it_billed(self):
        self.check(rates(shaped("r1", [2.0] * 20 + [0.0] * 10)), 0.0, 40.0, 30, False)

    def test_days_without_a_line_in_the_last_week_count_as_nothing(self):
        self.check(rates(shaped("r1", [10.0] + [0.0] * 6 + [10.0] * 4)), 40.0 / 7 * 30, round(1500 / 11, 6), 11, True)

    def test_an_uneven_meter_has_a_spread_larger_than_its_mean(self):
        found = rates(shaped("r1", [10.0 if n % 5 == 0 else 0.0 for n in range(30)]))
        self.check(found, 10.0 / 7 * 30, 60.0, 30, False)
        self.assertAlmostEqual(found.cv, 2.0)

    def test_a_spread_is_over_the_days_of_life_so_that_a_young_flat_meter_is_not_uneven(self):
        self.assertAlmostEqual(rates(shaped("r1", [5.0] * 5)).cv, 0.0)

    def test_fewer_than_three_days_of_life_are_no_rate_and_three_are(self):
        for costs in ([5.0], [5.0, 5.0], [0.0, 0.0, 5.0]):
            with self.subTest(costs=costs):
                self.assertIsNone(rates(shaped("r1", costs)))
        self.check(rates(shaped("r1", [5.0] * 3)), 150.0, None, 3, True)

    def test_a_cost_on_one_day_only_is_not_stretched_into_a_month(self):
        self.assertIsNone(rates(shaped("r1", [0.0] * 29 + [5.0])))
        self.check(rates(shaped("r1", [5.0] + [0.0] * 19)), 0.0, 7.5, 20, True)

    def test_a_read_of_14_days_gives_the_week_and_no_mean_when_its_first_day_has_a_cost_because_the_meter_may_be_older(self):
        self.check(rates(shaped("r1", [2.0] * 14, days=14)), 60.0, None, 14, False)

    def test_a_read_of_14_days_gives_both_when_the_meter_began_inside_it(self):
        self.check(rates(shaped("r1", [1.0] * 5 + [4.0] * 5, days=14)), 22.0 / 7 * 30, 75.0, 10, True)

    def test_a_read_of_less_than_a_week_gives_no_rate(self):
        self.assertIsNone(rates(shaped("r1", [2.0] * 6, days=6)))
        self.check(rates(shaped("r1", [2.0] * 7, days=7)), 60.0, None, 7, False)

    def test_a_meter_with_no_cost_or_a_number_that_is_not_one_has_no_rate(self):
        for costs in ([0.0] * 30, [float("nan")] * 30, [2.0] * 29 + [float("inf")]):
            with self.subTest(costs=costs[-1]):
                self.assertIsNone(rates(shaped("r1", costs)))

    def test_a_credit_is_a_negative_rate_and_has_no_spread(self):
        found = rates(shaped("r1", [-1.0] * 30))
        self.check(found, -30.0, -30.0, 30, False)
        self.assertIsNone(found.cv)

    def test_a_day_that_is_outside_the_window_is_not_read(self):
        meter = shaped("r1", [2.0] * 30)
        daily = {**meter.daily, START - dt.timedelta(days=3): 900.0, START + dt.timedelta(days=30): 900.0}
        self.check(rates(meter._replace(daily=daily)), 60.0, 60.0, 30, False)


class WhatIsRead(unittest.TestCase):
    """The block is read strictly. What cannot be read is a change of no action, which the finding says."""

    def test_no_block_is_no_change_and_the_legacy_paths_stay(self):
        self.assertIsNone(pricing.parse(None))
        self.assertEqual(priced(None).rows, {})

    def test_a_block_that_is_not_an_object_or_has_no_known_action_is_no_action(self):
        for raw in ("remove", 7, [], {"action": "delete everything", "effects": [effect()]}, {"effects": [effect()]}, {"action": 5}):
            with self.subTest(raw=raw):
                change = pricing.parse(raw)
                self.assertEqual((change.action, change.effects), ("none", ()))

    def test_the_action_is_one_of_the_list_in_any_case(self):
        self.assertEqual(pricing.ACTIONS, ("remove", "reduce", "switch", "schedule", "commit", "none"))
        self.assertEqual(pricing.parse(block(" Remove ", effect())).action, "remove")

    def test_the_how_is_cleaned_like_every_text_of_the_ai_cut_and_never_an_amount(self):
        change = pricing.parse(block("remove", effect(), how="Delete it and save $500 a month, see https://evil.example " + "x" * 400))
        self.assertLessEqual(len(change.how), pricing.MAX_HOW)
        self.assertNotIn("500", change.how)
        self.assertNotIn("evil.example", change.how)
        self.assertEqual(pricing.parse(block("remove", effect(), how=None)).how, "")

    def test_an_effect_without_a_text_handle_is_left_out_and_a_meter_that_is_no_text_too(self):
        change = pricing.parse(block("remove", {"meters": ["m1"], "remains": {"form": "none"}}, effect("r1", ("m1", 5, None, "m2"))))
        self.assertEqual([(e.handle, e.meters) for e in change.effects], [("r1", ("m1", "m2"))])

    def test_a_meter_that_is_named_twice_in_an_effect_is_one(self):
        self.assertEqual(pricing.parse(block("remove", effect("r1", ("m1", "m1", "m2", "m1")))).effects[0].meters, ("m1", "m2"))

    def test_the_numbers_of_the_effects_and_of_their_meters_are_bounded(self):
        many = [effect(f"r{n}", [f"m{k}" for k in range(1, 100)]) for n in range(1, 100)]
        change = pricing.parse(block("remove", *many))
        self.assertEqual(len(change.effects), pricing.MAX_EFFECTS)
        self.assertEqual({len(e.meters) for e in change.effects}, {pricing.MAX_METERS})


class WhatRemainsAndHowItIsChecked(unittest.TestCase):
    def test_remove_takes_all_that_the_named_meters_bill_and_follows_from_the_bill_alone(self):
        found = priced(block("remove", effect("r1", ("m1", "m2"))))
        row = found.rows["r1"]
        self.assertEqual((row.low, row.high, row.bill, row.lines, row.form), (100.0, 100.0, 100.0, 2, "none"))
        self.assertEqual(row.level, pricing.EXPECTED)

    def test_only_the_meters_that_are_named_go_and_the_others_of_the_resource_stay(self):
        row = priced(block("remove", effect("r1", ("m1",)))).rows["r1"]
        self.assertEqual((row.low, row.high, row.bill, row.lines), (60.0, 60.0, 60.0, 1))

    def test_a_ratio_of_a_property_is_checked_against_the_number_that_the_tools_showed_and_the_remainder_is_the_codes(self):
        row = priced(block("reduce", effect("r1", ("m1", "m2"), {"form": "ratio", "on": "units", "from": 12, "to": 4}))).rows["r1"]
        self.assertEqual((row.low, row.high, row.form, row.level), (66.67, 66.67, "ratio", pricing.SCENARIO))
        self.assertEqual(row.said, {"from": 12.0, "to": 4.0, "on": "units"})

    def test_a_ratio_of_a_measurement_takes_its_total_its_highest_value_or_its_average_as_the_tools_gave_them(self):
        for said in (90, 11, 3.0):
            with self.subTest(said=said):
                row = priced(block("reduce", effect("r1", ("m1",), {"form": "ratio", "on": "Used Units", "from": said, "to": said / 3}))).rows["r1"]
                self.assertEqual(row.low, 40.0)

    def test_a_name_that_is_not_a_plain_word_is_refused_even_when_it_is_in_the_evidence(self):
        box = shown(evidence={"r1": {"properties": {"units; drop it": 12, "<b>x</b>": 12, "units": 12}}})
        for name in ("units; drop it", "<b>x</b>"):
            with self.subTest(name=name):
                found = pricing.price(pricing.parse(block("reduce", effect("r1", ("m1",), {"form": "ratio", "on": name, "from": 12, "to": 4}))), ("r1",), box, COSTS, None)
                self.assertEqual((found.rows, found.why), ({}, {"r1": "remains"}))
        found = pricing.price(pricing.parse(block("reduce", effect("r1", ("m1",), {"form": "ratio", "on": "units", "from": 12, "to": 4}))), ("r1",), box, COSTS, None)
        self.assertEqual(found.rows["r1"].low, 40.0)

    def test_a_ratio_whose_current_number_is_not_the_tools_makes_no_figure(self):
        for remains in ({"form": "ratio", "on": "units", "from": 13, "to": 4}, {"form": "ratio", "on": "other units", "from": 12, "to": 4},
                        {"form": "ratio", "on": "tier", "from": 12, "to": 4}, {"form": "ratio", "from": 12, "to": 4}, {"form": "ratio", "on": ["units"], "from": 12, "to": 4}):
            with self.subTest(remains=remains):
                found = priced(block("reduce", effect("r1", ("m1",), remains)))
                self.assertEqual((found.rows, found.why), ({}, {"r1": "remains"}))

    def test_a_ratio_of_numbers_that_are_not_a_reduction_makes_no_figure(self):
        for start, target in ((12, 12), (12, 13), (12, -1), (0, 0), (True, 4), (12, True), ("12", 4), (12, "4"), (12, None), (float("nan"), 4), (12, float("inf")), (10 ** 400, 4)):
            with self.subTest(start=start, target=target):
                found = priced(block("reduce", effect("r1", ("m1",), {"form": "ratio", "on": "units", "from": start, "to": target})))
                self.assertEqual((found.rows, found.why), ({}, {"r1": "remains"}))

    def test_a_target_of_nothing_is_a_ratio_that_removes_everything(self):
        self.assertEqual(priced(block("reduce", effect("r1", ("m1",), {"form": "ratio", "on": "units", "from": 12, "to": 0}))).rows["r1"].low, 60.0)

    def test_a_share_of_days_is_arithmetic_on_two_whole_numbers(self):
        row = priced(block("schedule", effect("r1", ("m1", "m2"), {"form": "share_of_days", "days": 5, "of": 7}))).rows["r1"]
        self.assertEqual((row.low, row.high, row.form, row.level, row.said), (28.57, 28.57, "share_of_days", pricing.SCENARIO, {"days": 5, "span": 7}))

    def test_a_share_of_days_that_is_not_a_share_makes_no_figure(self):
        for days, span in ((7, 7), (8, 7), (0, 7), (-1, 7), (5, 0), (5, 32), (5.0, 7), (5, 7.5), (True, 7), (5, True), ("5", 7), (None, 7)):
            with self.subTest(days=days, span=span):
                found = priced(block("schedule", effect("r1", ("m1",), {"form": "share_of_days", "days": days, "of": span})))
                self.assertEqual((found.rows, found.why), ({}, {"r1": "remains"}))

    def test_an_assumption_is_a_low_and_a_high_of_what_remains_the_point_is_the_low_figure_and_it_is_marked(self):
        row = priced(block("reduce", effect("r1", ("m1", "m2"), {"form": "assumed", "low": 0.4, "high": 0.7}))).rows["r1"]
        self.assertEqual((row.low, row.high, row.form, row.level), (30.0, 60.0, "assumed", pricing.SCENARIO))
        self.assertEqual(row.away, (0.3, 0.6))

    def test_an_assumption_is_never_widened_a_single_value_is_a_range_of_one_and_what_is_out_of_range_is_refused(self):
        row = priced(block("reduce", effect("r1", ("m1", "m2"), {"form": "assumed", "low": 0.5, "high": 0.5}))).rows["r1"]
        self.assertEqual((row.low, row.high), (50.0, 50.0))
        for low, high in ((0.7, 0.4), (-0.1, 0.5), (0.2, 1.2), (None, 0.5), (0.2, "0.5"), (True, 0.5), (0.2, float("nan")), (1.5, 2)):
            with self.subTest(low=low, high=high):
                found = priced(block("reduce", effect("r1", ("m1",), {"form": "assumed", "low": low, "high": high})))
                self.assertEqual((found.rows, found.why), ({}, {"r1": "remains"}))

    def test_an_assumption_that_everything_remains_saves_nothing_and_says_so(self):
        found = priced(block("reduce", effect("r1", ("m1",), {"form": "assumed", "low": 1, "high": 1})))
        self.assertEqual((found.rows, found.why), ({}, {"r1": "nothing"}))

    def test_a_switch_to_an_alternative_is_refused_until_it_is_built_with_the_reason_that_it_is_not_available_yet(self):
        found = priced(block("switch", effect("r1", ("m1",), {"form": "alternative", "to": "something"})))
        self.assertEqual((found.rows, found.why), ({}, {"r1": "later"}))
        self.assertIn("not available yet", pricing.WHY["later"])

    def test_a_form_that_does_not_go_with_the_action_is_refused(self):
        for action, remains in (("remove", {"form": "ratio", "on": "units", "from": 12, "to": 4}), ("remove", {"form": "assumed", "low": 0.1, "high": 0.2}),
                                ("reduce", {"form": "none"}), ("schedule", {"form": "none"}), ("switch", {"form": "none"}), ("commit", {"form": "none"}),
                                ("commit", {"form": "ratio", "on": "units", "from": 12, "to": 4}), ("reduce", {"form": "share_of_days", "days": 5, "of": 7})):
            with self.subTest(action=action, form=remains["form"]):
                self.assertEqual(priced(block(action, effect("r1", ("m1",), remains))).why, {"r1": "remains"})

    def test_a_form_that_is_not_a_form_makes_no_figure(self):
        for remains in ({}, {"form": "half"}, {"form": None}, {"low": 0.1, "high": 0.2}, {"form": "NONE"}):
            with self.subTest(remains=remains):
                self.assertEqual(priced(block("remove", effect("r1", ("m1",), remains))).why, {"r1": "remains"})
        self.assertEqual(priced(block("remove", {"handle": "r1", "meters": ["m1"]})).why, {"r1": "remains"})

    def test_the_other_actions_take_an_assumption(self):
        for action in ("switch", "commit"):
            with self.subTest(action=action):
                self.assertEqual(priced(block(action, effect("r1", ("m1",), {"form": "assumed", "low": 0.5, "high": 0.8}))).rows["r1"].low, 12.0)

    def test_no_action_and_no_effect_say_that_no_bill_line_was_named(self):
        for raw in (block("none", effect()), block("remove"), {"action": "remove", "effects": "r1"}):
            with self.subTest(raw=raw):
                found = priced(raw)
                self.assertEqual((found.rows, found.why, found.action), ({}, {}, pricing.parse(raw).action))
                self.assertEqual(pricing.digest(pricing.parse(raw), found, "r1", None)["missing"], "none")


class WhatMetersCount(unittest.TestCase):
    def test_a_meter_that_no_tool_showed_is_not_counted_and_the_rest_are_and_the_loss_is_said(self):
        row = priced(block("remove", effect("r1", ("m1", "m9", "x", "m10000")))).rows["r1"]
        self.assertEqual((row.low, row.lines, row.skipped), (60.0, 1, 3))

    def test_a_meter_of_another_resource_is_rejected(self):
        row = priced(block("remove", effect("r1", ("m1", "m3")))).rows["r1"]
        self.assertEqual((row.low, row.lines, row.skipped), (60.0, 1, 1))
        found = priced(block("remove", effect("r1", ("m3",))))
        self.assertEqual((found.rows, found.why), ({}, {"r1": "lines"}))

    def test_a_meter_of_a_whole_type_is_not_the_bill_of_a_resource(self):
        found = priced(block("remove", effect("r1", ("m5",))), toolbox=shown(meters={**registry(), "m5": line("microsoft.example/widgets", 900.0, resources=12)}))
        self.assertEqual((found.rows, found.why), ({}, {"r1": "lines"}))

    def test_a_meter_that_was_read_over_less_than_a_week_gives_no_rate_and_one_read_over_a_week_or_more_gives_the_rate_of_its_last_week(self):
        found = priced(block("remove", effect("r1", ("m1", "m2"))), toolbox=shown(meters={**registry(), "m1": line("r1", 12.0, days=6)}))
        self.assertEqual((found.rows["r1"].low, found.rows["r1"].skipped), (40.0, 1))
        short = shown(meters={"m1": line("r1", 12.0, days=6)})
        self.assertEqual(priced(block("remove", effect("r1", ("m1",))), toolbox=short).why, {"r1": "lines"})
        week = priced(block("remove", effect("r1", ("m1", "m2"))), toolbox=shown(meters={**registry(), "m1": line("r1", 14.0, days=7)}))
        self.assertEqual((week.rows["r1"].low, week.rows["r1"].skipped), (100.0, 0), "7 days at 2 a day are 60 a month, whatever the 30 days showed")

    def test_a_meter_with_fewer_than_three_days_of_cost_is_not_counted_and_the_reason_is_the_lines(self):
        found = priced(block("remove", effect("r1", ("m1",))), toolbox=shown(meters={"m1": shaped("r1", [9.0, 9.0])}))
        self.assertEqual((found.rows, found.why), ({}, {"r1": "lines"}))
        self.assertIn(f"less than {pricing.FEWEST} days", pricing.WHY["lines"])

    def test_a_meter_counts_once_whatever_the_number_of_times_that_it_is_named(self):
        row = priced(block("remove", effect("r1", ("m1", "m1")), effect("r1", ("m1", "m2")))).rows["r1"]
        self.assertEqual((row.low, row.lines), (100.0, 2), "m1 is counted once although both effects name it")

    def test_the_same_bill_line_read_twice_with_other_filters_is_one(self):
        meters = {**registry(), "m8": line("r1", 60.0, service="Example Service")}
        row = priced(block("remove", effect("r1", ("m1", "m8", "m2"))), toolbox=shown(meters=meters)).rows["r1"]
        self.assertEqual((row.low, row.lines), (100.0, 2))

    def test_a_meter_that_cost_nothing_or_less_adds_nothing_and_a_credit_takes_its_share_off_what_the_resource_costs(self):
        meters = {"m1": line("r1", 0.0), "m2": line("r1", -5.0, STORAGE), "m3": line("r1", 10.0, NETWORK)}
        self.assertEqual(priced(block("remove", effect("r1", ("m1", "m2", "m3"))), toolbox=shown(meters=meters)).rows["r1"].low, 5.0, "10 on the line, 5 of it given back: the resource costs 5")
        found = priced(block("remove", effect("r1", ("m1", "m2"))), toolbox=shown(meters=meters))
        self.assertEqual((found.rows, found.why), ({}, {"r1": "nothing"}))
        self.assertIn("last 7 days", pricing.WHY["nothing"])

    def test_a_meter_with_a_number_that_is_not_one_adds_nothing(self):
        meters = {"m1": line("r1", float("nan")), "m2": line("r1", 20.0, STORAGE)}
        self.assertEqual(priced(block("remove", effect("r1", ("m1", "m2"))), toolbox=shown(meters=meters)).rows["r1"].low, 20.0)

    def test_the_figure_is_never_above_what_the_resource_costs_a_month_on_the_same_rates(self):
        credit = {"m1": line("r1", 60.0), "m2": line("r1", 40.0, STORAGE), "m6": line("r1", -20.0, ("Example Credit", "None", "Given Back", "OnDemand", "Refund", "1"))}
        row = priced(block("remove", effect("r1", ("m1", "m2"))), toolbox=shown(meters=credit)).rows["r1"]
        self.assertEqual((row.low, row.high, row.bill), (80.0, 80.0, 100.0))
        row = priced(block("reduce", effect("r1", ("m1", "m2"), {"form": "assumed", "low": 0.0, "high": 0.5})), toolbox=shown(meters=credit)).rows["r1"]
        self.assertEqual((row.low, row.high), (50.0, 80.0))

    def test_the_cap_is_the_lower_rates_for_the_low_end_and_the_higher_rates_for_the_high_end(self):
        doubled = shaped("r1", [1.0] * 23 + [2.0] * 7)
        credit = shaped("r1", [-0.5] * 30, words=STORAGE)
        row = priced(block("remove", effect("r1", ("m1",))), toolbox=shown(meters={"m1": doubled, "m2": credit})).rows["r1"]
        self.assertEqual((row.low, row.high), (37.0 - 15.0, 60.0 - 15.0), "37 and 60 a month on the two rates, and the credit is 15 a month on both")

    def test_a_resource_whose_cost_was_not_read_is_capped_by_its_own_meters_only(self):
        self.assertEqual(priced(block("remove", effect("r1", ("m1", "m2"))), costs={"r1": None}).rows["r1"].low, 100.0)

    def test_the_cost_of_the_resource_in_30_days_bounds_a_rate_by_the_days_that_the_rate_rests_on(self):
        week = shown(meters={"m1": shaped("r1", [1.0] * 23 + [2.0] * 7)})
        self.assertEqual(priced(block("remove", effect("r1", ("m1",))), toolbox=week, costs={"r1": 37.0}).rows["r1"].high, 60.0, "37 in 30 days can be 60 a month: it all came in the last week")
        self.assertEqual(priced(block("remove", effect("r1", ("m1",))), toolbox=week, costs={"r1": 10.0}).rows["r1"].high, 42.86, "10 in 30 days cannot be more than 10 a week")
        young = shown(meters={"m1": shaped("r1", [8.0] * 4)})
        self.assertEqual(priced(block("remove", effect("r1", ("m1",))), toolbox=young, costs={"r1": 32.0}).rows["r1"].high, 240.0)
        self.assertEqual(priced(block("remove", effect("r1", ("m1",))), toolbox=young, costs={"r1": 24.0}).rows["r1"].high, 180.0)

    def test_a_cost_that_is_not_in_dollars_makes_no_figure_and_says_so(self):
        found = priced(block("remove", effect("r1", ("m1", "m2"))), blocked={"r1": "currency"})
        self.assertEqual((found.rows, found.why), ({}, {"r1": "currency"}))

    def test_an_effect_for_a_resource_that_is_not_of_the_finding_is_ignored(self):
        found = priced(block("remove", effect("r1", ("m1",)), effect("r2", ("m3",))), handles=("r1",))
        self.assertEqual((sorted(found.rows), found.why), (["r1"], {}))

    def test_effects_of_one_resource_with_other_forms_are_added_and_the_row_says_that_it_is_mixed(self):
        found = priced(block("reduce", effect("r1", ("m1",), {"form": "assumed", "low": 0.5, "high": 0.5}), effect("r1", ("m2",), {"form": "assumed", "low": 0.0, "high": 0.0})))
        row = found.rows["r1"]
        self.assertEqual((row.low, row.high, row.bill, row.lines, row.form), (70.0, 70.0, 100.0, 2, "mixed"))
        self.assertIsNone(row.away)

    def test_a_part_that_cannot_be_priced_is_left_out_of_the_row_and_counted(self):
        found = priced(block("reduce", effect("r1", ("m1",), {"form": "assumed", "low": 0.5, "high": 0.5}), effect("r1", ("m2",), {"form": "ratio", "on": "units", "from": 99, "to": 1})))
        self.assertEqual((found.rows["r1"].low, found.rows["r1"].skipped, found.why), (30.0, 1, {}))

    def test_a_group_is_priced_as_the_sum_of_its_resources_each_by_its_own_meters_once(self):
        found = priced(block("remove", effect("r1", ("m1", "m2")), effect("r2", ("m3",))))
        self.assertEqual({handle: (row.low, row.bill) for handle, row in found.rows.items()}, {"r1": (100.0, 100.0), "r2": (30.0, 30.0)})
        joined = pricing.combine([pricing.digest(pricing.parse(block("remove", effect())), found, handle, None) for handle in ("r1", "r2")], 3)
        self.assertEqual((joined["price"]["lowUsd"], joined["price"]["billUsd"], joined["price"]["lines"], joined["price"]["resources"], joined["price"]["members"]), (130.0, 130.0, 3, 2, 3))

    def test_a_resource_of_the_group_that_has_no_effect_has_no_figure_and_the_sum_is_of_the_others(self):
        found = priced(block("remove", effect("r1", ("m1",))), handles=("r1", "r2"))
        self.assertEqual(sorted(found.rows), ["r1"])
        change = pricing.parse(block("remove", effect("r1", ("m1",))))
        self.assertEqual(pricing.digest(change, found, "r2", None)["missing"], "none")


class WhenTheRateIsTheBase(unittest.TestCase):
    """A saving is a figure a month about what is to come: the base is what the meters cost a month now, on the lower rate for the low end and on the higher one for the high end. By hand, with invented
    meters over the 30 days that start on START."""

    def row(self, costs, remains=None, action="remove", cost=None, **options):
        meter = shaped("r1", costs, **options)
        found = priced(block(action, effect("r1", ("m1",), remains)), toolbox=shown(meters={"m1": meter}), costs={"r1": math.fsum(costs) if cost is None else cost})
        self.assertEqual(found.why, {})
        return found.rows["r1"]

    def test_a_flat_meter_has_one_base_whatever_the_basis(self):
        row = self.row([2.0] * 30)
        self.assertEqual((row.low, row.high, row.bill, row.week, row.since, row.life, row.uneven), (60.0, 60.0, 60.0, 60.0, 60.0, None, 0))

    def test_a_new_meter_of_four_days_is_priced_at_its_own_rate_and_not_at_the_30_days_that_it_did_not_live(self):
        row = self.row([8.0] * 4)
        self.assertEqual((row.low, row.high, row.week, row.since, row.life), (240.0, 240.0, 240.0, None, 4), "32 in the window, 240 a month")
        self.assertEqual(pricing.saved({pricing.KEY: pricing.digest(pricing.parse(block("remove", effect("r1", ("m1",)))), pricing.Priced("remove", {"r1": row}), "r1")}, 32.0).basis,
                         "the 1 bill line of 1 resource that the change would remove, at the rate since it began 4 days ago")

    def test_a_rate_that_doubled_in_the_last_week_counts_the_old_rate_and_shows_the_new_one(self):
        row = self.row([1.0] * 23 + [2.0] * 7)
        self.assertEqual((row.low, row.high, row.week, row.since), (37.0, 60.0, 60.0, 37.0))

    def test_a_rate_that_halved_in_the_last_week_counts_the_new_rate_and_shows_the_old_one(self):
        row = self.row([2.0] * 23 + [1.0] * 7)
        self.assertEqual((row.low, row.high, row.week, row.since), (30.0, 53.0, 30.0, 53.0), "what was saved already is not counted")

    def test_a_meter_that_stopped_saves_nothing_at_its_rate_now(self):
        found = priced(block("remove", effect("r1", ("m1",))), toolbox=shown(meters={"m1": shaped("r1", [2.0] * 20 + [0.0] * 10)}), costs={"r1": 40.0})
        self.assertEqual((found.rows, found.why), ({}, {"r1": "nothing"}))

    def test_an_uneven_meter_counts_the_lower_rate_and_says_that_it_is_uneven(self):
        row = self.row([10.0 if n % 5 == 0 else 0.0 for n in range(30)])
        self.assertEqual((row.low, row.high, row.uneven), (42.86, 60.0, 1))

    def test_an_uneven_line_makes_the_figure_rough_only_when_it_carries_a_tenth_of_what_the_figure_rests_on(self):
        def uneven(peak):
            spiky = shaped("r1", [peak if n % 10 == 0 else 0.0 for n in range(30)], words=STORAGE)
            found = priced(block("remove", effect("r1", ("m1", "m2"))), toolbox=shown(meters={"m1": shaped("r1", [10.0] * 30), "m2": spiky}), costs={"r1": 300.0 + 3 * peak})
            return found.rows["r1"].uneven

        self.assertEqual((uneven(10.0), uneven(30.0)), (0, 1), "30 of 330 a month is under a tenth, and 90 of 390 is not")

    def test_a_meter_with_one_day_or_two_has_no_rate_and_the_finding_says_that_the_lines_gave_none(self):
        for costs in ([5.0], [5.0, 5.0]):
            found = priced(block("remove", effect("r1", ("m1",))), toolbox=shown(meters={"m1": shaped("r1", costs)}))
            self.assertEqual((found.rows, found.why), ({}, {"r1": "lines"}))

    def test_a_read_of_14_days_is_priced_at_the_rate_of_its_last_week_and_claims_no_mean_since_the_start(self):
        row = self.row([2.0] * 14, days=14)
        self.assertEqual((row.low, row.high, row.week, row.since), (60.0, 60.0, 60.0, None))
        self.assertNotIn("sinceUsd", row.digest())

    def test_a_meter_read_over_14_days_that_began_inside_the_read_has_both_rates(self):
        row = self.row([1.0] * 5 + [4.0] * 5, days=14)
        self.assertEqual((row.low, row.high, row.life), (75.0, 94.29, 10))

    def test_the_shares_of_every_form_apply_to_the_low_and_to_the_high_base(self):
        doubled = [1.0] * 23 + [2.0] * 7
        ratio = self.row(doubled, {"form": "ratio", "on": "units", "from": 12, "to": 4}, "reduce")
        self.assertEqual((ratio.low, ratio.high), (24.67, 40.0), "two thirds of 37 and of 60")
        days = self.row(doubled, {"form": "share_of_days", "days": 5, "of": 7}, "schedule")
        self.assertEqual((days.low, days.high), (10.57, 17.14), "two sevenths of 37 and of 60")
        assumed = self.row(doubled, {"form": "assumed", "low": 0.4, "high": 0.7}, "reduce")
        self.assertEqual((assumed.low, assumed.high), (11.1, 36.0), "30 percent of 37 and 60 percent of 60")

    def test_the_figure_that_a_case_counts_is_the_low_end_on_the_lower_rate(self):
        row = self.row([1.0] * 23 + [2.0] * 7)
        facts = {pricing.KEY: pricing.digest(pricing.parse(block("remove", effect("r1", ("m1",)))), pricing.Priced("remove", {"r1": row}), "r1")}
        self.assertEqual((pricing.point(facts), pricing.saved(facts).high), (37.0, 60.0))
        self.assertEqual(pricing.saved(facts).basis, "the 1 bill line of 1 resource that the change would remove, at the lower of the 7-day rate and the 30-day total; $37.00 to $60.00 a month")

    def test_the_digest_of_a_group_is_the_sum_of_the_rates_of_its_resources_and_the_youngest_life(self):
        change = pricing.parse(block("remove", effect("r1", ("m1",)), effect("r2", ("m2",))))
        found = pricing.price(change, ("r1", "r2"), shown(meters={"m1": shaped("r1", [1.0] * 23 + [2.0] * 7), "m2": shaped("r2", [8.0] * 4)}), {"r1": 37.0, "r2": 32.0}, None)
        joined = pricing.combine([pricing.digest(change, found, handle, None) for handle in ("r1", "r2")], 2)["price"]
        self.assertEqual({key: joined[key] for key in ("lowUsd", "highUsd", "billUsd", "weekUsd", "sinceUsd", "life", "resources", "members")},
                         {"lowUsd": 277.0, "highUsd": 300.0, "billUsd": 300.0, "weekUsd": 300.0, "sinceUsd": 277.0, "life": 4, "resources": 2, "members": 2})
        saved = pricing.saved({pricing.KEY: {"action": "remove", "price": joined}})
        self.assertEqual((saved.low, saved.high, saved.bill, saved.per), (277.0, 300.0, 277.0, "a month"))

    def test_a_group_of_digests_made_before_the_rates_stays_without_them(self):
        old = {"action": "remove", "price": {"lowUsd": 5.0, "highUsd": 5.0, "billUsd": 5.0, "lines": 1, "resources": 1, "form": "none"}}
        joined = pricing.combine([old, old], 2)["price"]
        self.assertEqual((joined["lowUsd"], "weekUsd" in joined, "sinceUsd" in joined), (10.0, False, False))
        self.assertIn("over the last 30 days", pricing.saved({pricing.KEY: {"action": "remove", "price": joined}}).basis)

    def test_a_credit_on_the_resource_takes_its_share_off_both_rates(self):
        found = priced(block("remove", effect("r1", ("m1",))), toolbox=shown(meters={"m1": shaped("r1", [1.0] * 23 + [2.0] * 7), "m2": shaped("r1", [-0.5] * 30, words=STORAGE)}), costs={"r1": 22.0})
        self.assertEqual((found.rows["r1"].low, found.rows["r1"].high), (22.0, 45.0))


class TheQuantityOfAMeter(unittest.TestCase):
    """A change in how much of a billed meter is used is stated in that meter's own quantity, which is what the bill measures. A ratio on a property is right only when the meter follows that property.
    The meter here bills only the units above the included ones: invented numbers, 1,440 unit-hours that cost 201.60 (2 units for 720 hours), while the resource has 4 units in all."""

    def price(self, remains, action="reduce", meters=("m1",), toolbox=None, costs=None):
        box = toolbox or shown(meters={"m1": billed_units(), "m2": billed_units(scope="r2"), "m3": billed_units(words=STORAGE)},
                               evidence={"r1": {"properties": {"units": 4}}, "r2": {"properties": {"units": 4}}})
        return pricing.price(pricing.parse(block(action, effect("r1", meters, remains))), ("r1",), box, {"r1": 201.60} if costs is None else costs, None)

    def test_the_extra_units_that_go_away_are_what_the_meter_bills_and_half_of_them_are_half(self):
        row = self.price({"form": "quantity", "from": 1440, "to": 0}).rows["r1"]
        self.assertEqual((row.low, row.high, row.form, row.level, row.said), (201.6, 201.6, "quantity", pricing.SCENARIO, {"from": 1440.0, "to": 0.0, "unit": "1 Hour"}))
        row = self.price({"form": "quantity", "from": 1440, "to": 720}).rows["r1"]
        self.assertEqual((row.low, row.high), (100.8, 100.8))

    def test_a_ratio_on_the_property_of_the_resource_halves_a_meter_that_does_not_follow_it_which_is_why_the_quantity_form_exists(self):
        row = self.price({"form": "ratio", "on": "units", "from": 4, "to": 2}).rows["r1"]
        self.assertEqual((row.low, row.form), (100.8, "ratio"), "4 units to 2 books half of the meter: the meter bills the 2 above the included ones, and 2 to 0 is all of it")
        self.assertEqual(self.price({"form": "quantity", "from": 1440, "to": 0}).rows["r1"].low, 201.6)

    def test_the_quantity_that_the_ai_starts_from_is_the_meters_own_as_the_tool_showed_it(self):
        for said in (1441, 1440.5, 4, 720, 14400):
            with self.subTest(said=said):
                found = self.price({"form": "quantity", "from": said, "to": 0})
                self.assertEqual((found.rows, found.why), ({}, {"r1": "remains"}))
        self.assertEqual(self.price({"form": "quantity", "from": 1440.0001, "to": 0}).rows["r1"].low, 201.6, "within a millionth, as for a number that a ratio cites")

    def test_a_target_that_is_not_a_reduction_of_a_quantity_makes_no_figure(self):
        for start, target in ((1440, 1440), (1440, 1500), (1440, -1), (0, 0), (True, 0), (1440, True), ("1440", 0), (1440, "0"), (1440, None), (float("nan"), 0), (1440, float("inf"))):
            with self.subTest(start=start, target=target):
                found = self.price({"form": "quantity", "from": start, "to": target})
                self.assertEqual((found.rows, found.why), ({}, {"r1": "remains"}))

    def test_a_quantity_of_a_meter_of_another_resource_or_of_a_meter_that_no_tool_showed_is_not_priced(self):
        for meters in (("m2",), ("m9",)):
            with self.subTest(meters=meters):
                found = self.price({"form": "quantity", "from": 1440, "to": 0}, meters=meters)
                self.assertEqual((found.rows, found.why), ({}, {"r1": "lines"}))

    def test_a_quantity_belongs_to_one_meter_so_an_effect_that_names_two_has_no_figure_and_two_effects_add_up(self):
        found = self.price({"form": "quantity", "from": 1440, "to": 0}, meters=("m1", "m3"))
        self.assertEqual((found.rows, found.why), ({}, {"r1": "remains"}))
        box = shown(meters={"m1": billed_units(), "m3": billed_units(usd=100.0, quantity=720.0, words=STORAGE)})
        change = pricing.parse(block("reduce", effect("r1", ("m1",), {"form": "quantity", "from": 1440, "to": 720}), effect("r1", ("m3",), {"form": "quantity", "from": 720, "to": 0})))
        row = pricing.price(change, ("r1",), box, {"r1": 301.6}, None).rows["r1"]
        self.assertEqual((row.low, row.high, row.form, row.lines), (200.8, 200.8, "mixed", 2), "100.80 and 100.00, each by its own quantity")

    def test_the_quantity_goes_with_reduce_and_schedule_and_with_no_other_action(self):
        for action, fits in (("reduce", True), ("schedule", True), ("remove", False), ("switch", False), ("commit", False)):
            with self.subTest(action=action):
                found = self.price({"form": "quantity", "from": 1440, "to": 720}, action=action)
                self.assertEqual(sorted(found.rows), ["r1"] if fits else [])

    def test_the_share_that_remains_is_applied_to_both_rates_of_the_meter(self):
        meter = Meter("r1", None, UNITS, 720.0, 37.0, {START + dt.timedelta(days=n): 1.0 if n < 23 else 2.0 for n in range(30)}, None, START, 30)
        row = self.price({"form": "quantity", "from": 720, "to": 360}, toolbox=shown(meters={"m1": meter}), costs={"r1": 37.0}).rows["r1"]
        self.assertEqual((row.low, row.high), (18.5, 30.0), "half of 37 and of 60 a month")

    def test_the_basis_says_the_quantities_and_the_unit_and_whose_target_it_is(self):
        facts = {pricing.KEY: pricing.digest(pricing.parse(block("reduce", effect("r1", ("m1",), {"form": "quantity", "from": 1440, "to": 720}))),
                                             self.price({"form": "quantity", "from": 1440, "to": 720}), "r1")}
        found = pricing.saved(facts)
        self.assertEqual((found.low, found.level), (100.8, pricing.SCENARIO))
        self.assertEqual(found.basis, "the 1 bill line of 1 resource that the change would shrink, at the rate of the last 7 days, scaled by the change from 1,440 to 720 (unit: 1 Hour): the AI's target")
        for unit in ("<b>hours</b>", "a" * 25, "hours\n"):
            with self.subTest(unit=unit):
                price = {**facts[pricing.KEY]["price"], "unit": unit}
                self.assertNotIn(unit.strip(), pricing.saved({pricing.KEY: {"action": "reduce", "price": price}}).basis, "a unit that is not a plain word is never put into a sentence")
        bare = {key: value for key, value in facts[pricing.KEY]["price"].items() if key != "unit"}
        self.assertTrue(pricing.saved({pricing.KEY: {"action": "reduce", "price": bare}}).basis.endswith("scaled by the change from 1,440 to 720: the AI's target"))

    def test_a_unit_that_is_not_a_plain_word_is_not_kept_in_the_digest(self):
        meter = billed_units(words=("Example Gateway", "Standard Tier", "Extra Units", "OnDemand", "Usage", "<script>"))
        row = self.price({"form": "quantity", "from": 1440, "to": 0}, toolbox=shown(meters={"m1": meter})).rows["r1"]
        self.assertEqual(row.said, {"from": 1440.0, "to": 0.0})

    def test_the_skeptic_is_shown_the_unit_after_the_check_of_the_tools_and_the_two_quantities(self):
        change = pricing.parse(block("reduce", effect("r1", ("m1",), {"form": "quantity", "from": 1440, "to": 720})))
        box = shown(meters={"m1": billed_units()})
        found = pricing.price(change, ("r1",), box, {"r1": 201.6}, None)
        (one,) = pricing.view(change, found, box.meters, lambda word: word, 6, ())["effects"]
        self.assertEqual((one["form"], one["from"], one["to"], one["unit"], one["usd"]), ("quantity", 1440.0, 720.0, "1 Hour", 201.6))
        (one,) = pricing.view(change, found, box.meters, lambda word: None, 6, ())["effects"]
        self.assertEqual(one["unit"], "other", "a word that the check of the tools does not pass is not shown")

    def test_a_group_of_resources_that_state_the_same_quantities_keeps_the_rule_and_one_that_states_others_is_mixed(self):
        change = pricing.parse(block("reduce", effect("r1", ("m1",), {"form": "quantity", "from": 1440, "to": 720}), effect("r2", ("m2",), {"form": "quantity", "from": 1440, "to": 720})))
        box = shown(meters={"m1": billed_units(), "m2": billed_units(scope="r2")})
        found = pricing.price(change, ("r1", "r2"), box, {"r1": 201.6, "r2": 201.6}, None)
        joined = pricing.combine([pricing.digest(change, found, handle) for handle in ("r1", "r2")], 2)["price"]
        self.assertEqual((joined["form"], joined["from"], joined["to"], joined["unit"], joined["lowUsd"]), ("quantity", 1440.0, 720.0, "1 Hour", 201.6))
        other = pricing.parse(block("reduce", effect("r1", ("m1",), {"form": "quantity", "from": 1440, "to": 720}), effect("r2", ("m2",), {"form": "quantity", "from": 1440, "to": 0})))
        found = pricing.price(other, ("r1", "r2"), box, {"r1": 201.6, "r2": 201.6}, None)
        self.assertEqual(pricing.combine([pricing.digest(other, found, handle) for handle in ("r1", "r2")], 2)["price"]["form"], "mixed")


class TheDigestAndWhatItSays(unittest.TestCase):
    """The digest is typed numbers and closed words; the brief reads it again, and every number is checked once more."""

    def digest_of(self, raw, handle="r1", advisor=None, **options):
        change = pricing.parse(raw)
        return pricing.digest(change, pricing.price(change, ("r1", "r2"), options.get("toolbox") or shown(), COSTS, None), handle, advisor)

    def test_a_priced_resource_keeps_its_action_its_words_and_the_numbers_and_no_text_of_the_estate(self):
        found = self.digest_of(block("remove", effect("r1", ("m1", "m2")), how="Remove it."))
        self.assertEqual(found, {"action": "remove", "how": "Remove it.", "price": {"lowUsd": 100.0, "highUsd": 100.0, "billUsd": 100.0, "weekUsd": 100.0, "sinceUsd": 100.0,
                                                                                    "lines": 2, "resources": 1, "form": "none"}})
        json.dumps(found)

    def test_the_figure_of_a_remove_is_expected_and_every_other_form_is_a_scenario(self):
        for raw, level in ((block("remove", effect()), pricing.EXPECTED),
                           (block("reduce", effect("r1", ("m1",), {"form": "ratio", "on": "units", "from": 12, "to": 4})), pricing.SCENARIO),
                           (block("schedule", effect("r1", ("m1",), {"form": "share_of_days", "days": 5, "of": 7})), pricing.SCENARIO),
                           (block("reduce", effect("r1", ("m1",), {"form": "assumed", "low": 0.2, "high": 0.4})), pricing.SCENARIO)):
            with self.subTest(form=raw["effects"][0]["remains"]["form"]):
                self.assertEqual(pricing.saved(self.facts(raw)).level, level)

    def facts(self, raw, **options):
        return {pricing.KEY: self.digest_of(raw, **options)}

    def test_the_words_of_the_basis_say_what_the_figure_rests_on_for_each_form(self):
        removed = pricing.saved(self.facts(block("remove", effect("r1", ("m1", "m2")))))
        self.assertEqual(removed.basis, "the 2 bill lines of 1 resource that the change would remove, at the rate of the last 7 days")
        ratio = pricing.saved(self.facts(block("reduce", effect("r1", ("m1", "m2"), {"form": "ratio", "on": "units", "from": 12, "to": 4}))))
        self.assertEqual(ratio.basis, "the 2 bill lines of 1 resource that the change would shrink, at the rate of the last 7 days, scaled by the change in units from 12 to 4: the AI's target")
        days = pricing.saved(self.facts(block("schedule", effect("r1", ("m1",), {"form": "share_of_days", "days": 5, "of": 7}))))
        self.assertEqual(days.basis, "the 1 bill line of 1 resource that the change would shrink, at the rate of the last 7 days, scaled to 5 days of every 7: the AI's proposal")
        assumed = pricing.saved(self.facts(block("reduce", effect("r1", ("m1", "m2"), {"form": "assumed", "low": 0.4, "high": 0.7}))))
        self.assertEqual(assumed.basis, "the 2 bill lines of 1 resource that the change would shrink, at the rate of the last 7 days, of which 30 to 60 percent would go away: "
                                        "the AI's own assumption, not checked by code; $30.00 to $60.00 a month")
        one = pricing.saved(self.facts(block("reduce", effect("r1", ("m1", "m2"), {"form": "assumed", "low": 0.5, "high": 0.5}))))
        self.assertTrue(one.basis.endswith("of which 50 percent would go away: the AI's own assumption, not checked by code"))

    def test_a_ratio_keeps_the_name_that_a_tool_returned_and_the_page_says_what_is_scaled(self):
        found = self.digest_of(block("reduce", effect("r1", ("m1", "m2"), {"form": "ratio", "on": "units", "from": 12, "to": 4})))
        self.assertEqual(found["price"], {"lowUsd": 66.67, "highUsd": 66.67, "billUsd": 100.0, "weekUsd": 100.0, "sinceUsd": 100.0, "lines": 2, "resources": 1, "form": "ratio", "from": 12.0, "to": 4.0,
                                          "on": "units"})
        self.assertEqual(self.view_of(block("reduce", effect("r1", ("m1", "m2"), {"form": "ratio", "on": "units", "from": 12, "to": 4}))).get("on"), "units")
        for name in ("a" * 25, "units; drop it", "<b>units</b>", "units\n"):
            with self.subTest(name=name):
                digest = {"action": "reduce", "price": {**found["price"], "on": name}}
                self.assertNotIn(name, pricing.saved({pricing.KEY: digest}).basis, "a name that is not a plain word of a tool is never put into a sentence")

    def view_of(self, raw):
        change = pricing.parse(raw)
        (one,) = pricing.view(change, pricing.price(change, ("r1", "r2"), shown(), COSTS, None), shown().meters, lambda word: word, 6, ())["effects"]
        return one

    WORST = {"lowUsd": 12345.67, "highUsd": 123456.78, "billUsd": 123456.78, "weekUsd": 123456.78, "sinceUsd": 90000.0, "life": 12, "uneven": 12, "lines": 12, "resources": 40, "members": 60,
             "skipped": 12, "advisorUsd": 1234.56}

    def test_the_worst_case_of_the_basis_fits_what_a_card_shows_and_the_parts_that_are_cut_first_are_the_last_ones(self):
        for more in ({"form": "assumed", "away": [0.3, 0.6]}, {"form": "ratio", "from": 120000.0, "to": 40000.0, "on": "a" * 24}, {"form": "share_of_days", "days": 20, "span": 31}, {"form": "mixed"}):
            with self.subTest(form=more["form"]):
                basis = pricing.saved({pricing.KEY: {"action": "reduce", "price": {**self.WORST, **more}}}).basis
                self.assertLessEqual(len(basis), 390, f"a card cuts the line at 400 characters, 'Based on ' and the full stop included: {basis}")
                self.assertTrue(basis.endswith("is not added"), "the note about Azure Advisor is the last part")
                self.assertIn("40 of 60 resources", basis, "how many of the resources are priced comes with what is counted, before the long parts")

    def test_the_basis_says_which_rate_it_rests_on_in_plain_words(self):
        def basis(**numbers):
            return pricing.saved({pricing.KEY: {"action": "remove", "price": {"lowUsd": 30.0, "highUsd": 60.0, "billUsd": 60.0, "lines": 1, "resources": 1, "form": "none", **numbers}}}).basis

        self.assertEqual(basis(weekUsd=60.0), "the 1 bill line of 1 resource that the change would remove, at the rate of the last 7 days; $30.00 to $60.00 a month")
        self.assertEqual(basis(weekUsd=60.0, sinceUsd=58.0).split(", ")[1].split(";")[0], "at the rate of the last 7 days", "within 5 percent they are the same rate")
        self.assertEqual(basis(weekUsd=60.0, sinceUsd=37.0).split(", ")[1].split(";")[0], "at the lower of the 7-day rate and the 30-day total")
        self.assertEqual(basis(weekUsd=60.0, sinceUsd=37.0, life=12).split(", ")[1].split(";")[0], "at the lower of the 7-day rate and the rate since it began")
        self.assertEqual(basis(weekUsd=60.0, life=4).split(", ")[1].split(";")[0], "at the rate since it began 4 days ago")
        self.assertEqual(basis(weekUsd=60.0, life=9).split(", ")[1].split(";")[0], "at the rate of the last 7 days", "a meter of a week or more has its last 7 days")
        self.assertEqual(basis(weekUsd=60.0, life=4, resources=3).split(", ")[1].split(";")[0], "at the rate of the last 7 days", "a group does not say when each of its resources began")
        self.assertIn("over the last 30 days", basis(), "a figure made before the rates rests on the 30 days, as it said")

    def test_a_case_that_rests_on_uneven_bill_lines_says_so(self):
        found = pricing.saved({pricing.KEY: {"action": "remove", "price": {"lowUsd": 60.0, "highUsd": 60.0, "billUsd": 60.0, "weekUsd": 60.0, "lines": 3, "resources": 1, "form": "none", "uneven": 1}}})
        self.assertTrue(found.basis.endswith("; 1 bill line is uneven from day to day"), found.basis)
        found = pricing.saved({pricing.KEY: {"action": "remove", "price": {"lowUsd": 60.0, "highUsd": 60.0, "billUsd": 60.0, "weekUsd": 60.0, "lines": 3, "resources": 1, "form": "none", "uneven": 2}}})
        self.assertTrue(found.basis.endswith("; 2 bill lines are uneven from day to day"), found.basis)

    def test_a_range_is_said_to_be_one_and_the_point_is_the_low_end(self):
        found = pricing.saved(self.facts(block("reduce", effect("r1", ("m1", "m2"), {"form": "assumed", "low": 0.4, "high": 0.7}))))
        self.assertEqual((found.low, found.high), (30.0, 60.0))
        self.assertEqual(pricing.point(self.facts(block("reduce", effect("r1", ("m1", "m2"), {"form": "assumed", "low": 0.4, "high": 0.7})))), 30.0)

    def test_what_could_not_be_checked_is_said_beside_the_figure(self):
        found = pricing.saved(self.facts(block("remove", effect("r1", ("m1", "m9", "m3")))))
        self.assertTrue(found.basis.endswith("; 2 named things not counted"), found.basis)
        found = pricing.saved(self.facts(block("remove", effect("r1", ("m1", "m9")))))
        self.assertTrue(found.basis.endswith("; 1 named thing not counted"), found.basis)

    def test_advisors_own_figure_is_kept_beside_and_never_added(self):
        found = pricing.saved(self.facts(block("remove", effect("r1", ("m1", "m2"))), advisor=12.5))
        self.assertTrue(found.basis.endswith("; Azure Advisor's $12.50 is not added"), found.basis)
        self.assertEqual(found.low, 100.0)

    def test_a_group_says_how_many_of_its_resources_are_priced_and_a_mix_of_rules_says_so(self):
        change = pricing.parse(block("reduce", effect("r1", ("m1",), {"form": "assumed", "low": 0.5, "high": 0.5}), effect("r2", ("m3",), {"form": "ratio", "on": "units", "from": 4, "to": 1})))
        found = pricing.price(change, ("r1", "r2", "r3"), shown(), COSTS, None)
        joined = pricing.combine([pricing.digest(change, found, handle, None) for handle in ("r1", "r2", "r3")], 3)
        saved = pricing.saved({pricing.KEY: joined})
        self.assertEqual((saved.low, saved.level), (52.5, pricing.SCENARIO))
        self.assertEqual(saved.basis, "the 2 bill lines of 2 of 3 resources that the change would shrink, at the rate of the last 7 days, each by its own rule; part rests on the AI's own proposals")

    def test_a_group_of_the_same_rule_with_the_same_numbers_keeps_the_rule(self):
        change = pricing.parse(block("remove", effect("r1", ("m1",)), effect("r2", ("m3",))))
        found = pricing.price(change, ("r1", "r2"), shown(), COSTS, None)
        joined = pricing.combine([pricing.digest(change, found, handle, None) for handle in ("r1", "r2")], 2)
        self.assertEqual(joined["price"]["form"], "none")
        self.assertEqual(pricing.saved({pricing.KEY: joined}).level, pricing.EXPECTED)

    def test_a_group_with_nothing_priced_says_why_by_the_first_reason(self):
        change = pricing.parse(block("remove", effect("r1", ("m9",)), effect("r2", ("m3",))))
        found = pricing.price(change, ("r1", "r2"), shown(meters={"m3": line("r1", 5.0)}), COSTS, None)
        joined = pricing.combine([pricing.digest(change, found, handle, None) for handle in ("r1", "r2")], 2)
        self.assertEqual(joined["missing"], "lines")
        self.assertIsNone(pricing.combine([None, None], 2))

    def test_a_digest_that_is_not_as_it_should_be_gives_no_figure_and_never_another_one(self):
        good = self.digest_of(block("remove", effect("r1", ("m1", "m2"))))
        for label, changes in (("a low of nothing", {"lowUsd": 0}), ("a low above the high", {"lowUsd": 101.0}), ("a high above the bill", {"highUsd": 100.5}),
                               ("a text", {"lowUsd": "100"}), ("a flag", {"lowUsd": True}), ("not a number", {"highUsd": float("nan")}), ("no bill", {"billUsd": None}),
                               ("a week that is not a number", {"weekUsd": "100"}), ("a week of nothing", {"weekUsd": 0}), ("a mean of nothing", {"sinceUsd": 0.0}),
                               ("a mean that is a flag", {"sinceUsd": True}), ("days of life that are fewer than a rate needs", {"life": 2}), ("days of life that are more than the window", {"life": 31}),
                               ("days of life that are a fraction", {"life": 4.5})):
            with self.subTest(label):
                self.assertIsNone(pricing.saved({pricing.KEY: {**good, "price": {**good["price"], **changes}}}))
        for facts in (None, {}, {pricing.KEY: "x"}, {pricing.KEY: {"price": "x"}}, {pricing.KEY: {"price": {}}}, {pricing.KEY: {"missing": "none"}}):
            with self.subTest(facts=facts):
                self.assertIsNone(pricing.saved(facts))

    def test_a_forged_high_is_refused_against_the_bill_lines_and_against_what_the_finding_cost_in_30_days(self):
        good = self.facts(block("reduce", effect("r1", ("m1", "m2"), {"form": "assumed", "low": 0.4, "high": 0.7})))
        self.assertIsNotNone(pricing.saved(good, 14.0), "a high of 60 a month can all have come in the last week of 30 days that cost 14")
        self.assertIsNone(pricing.saved(good, 13.9))
        forged = {pricing.KEY: {**good[pricing.KEY], "price": {**good[pricing.KEY]["price"], "highUsd": 100.01}}}
        self.assertIsNone(pricing.saved(forged, 1000.0), "a high above what the lines cost on their higher rate is refused whatever the finding cost")
        young = {pricing.KEY: {"action": "remove", "price": {"lowUsd": 240.0, "highUsd": 240.0, "billUsd": 240.0, "weekUsd": 240.0, "life": 4, "lines": 1, "resources": 1, "form": "none"}}}
        self.assertIsNotNone(pricing.saved(young, 32.0), "four days that cost 32 are 240 a month")
        self.assertIsNone(pricing.saved(young, 31.0))
        self.assertIsNone(pricing.saved({pricing.KEY: {**young[pricing.KEY], "price": {**young[pricing.KEY]["price"], "life": 30}}}, 32.0), "a meter that is not young cannot be 240 a month on 32 in 30 days")

    def test_a_figure_made_before_the_rates_is_still_read_and_is_still_bounded_by_what_the_finding_cost(self):
        old = {pricing.KEY: {"action": "remove", "price": {"lowUsd": 60.0, "highUsd": 60.0, "billUsd": 60.0, "lines": 1, "resources": 1, "form": "none"}}}
        found = pricing.saved(old, 60.0)
        self.assertEqual((found.low, found.bill, found.per), (60.0, 60.0, "in the last 30 days"))
        self.assertIsNone(pricing.saved(old, 59.0))

    def test_the_form_decides_the_level_and_not_a_word_in_the_digest(self):
        good = self.facts(block("reduce", effect("r1", ("m1", "m2"), {"form": "assumed", "low": 0.4, "high": 0.7})))
        self.assertEqual(pricing.saved({pricing.KEY: {**good[pricing.KEY], "price": {**good[pricing.KEY]["price"], "form": "none", "level": "Verified"}}}).level, pricing.EXPECTED)

    def test_the_reasons_that_there_is_no_figure_are_plain_sentences_and_a_change_that_was_stated_and_not_priced_is_told_from_one_that_was_not_stated(self):
        for word in ("lines", "remains", "currency", "nothing", "later", "none"):
            self.assertTrue(pricing.WHY[word].startswith("No saving was worked out: ") or word == "nothing", word)
        none = {pricing.KEY: {"action": "none", "missing": "none"}}
        refused = {pricing.KEY: {"action": "remove", "missing": "lines"}}
        self.assertEqual((pricing.missing(none), pricing.refused(none)), (pricing.WHY["none"], False))
        self.assertEqual((pricing.missing(refused), pricing.refused(refused)), (pricing.WHY["lines"], True))
        self.assertEqual((pricing.missing({}), pricing.refused({}), pricing.missing({pricing.KEY: {"missing": "<script>"}}), pricing.refused({pricing.KEY: {"missing": "<script>"}})), ("", False, "", False))

    def test_a_finding_that_names_no_bill_line_says_that_a_line_that_no_resource_owns_has_no_handle_to_name(self):
        self.assertIn("no resource owns", pricing.WHY["none"])


class WhatTheSkepticIsShown(unittest.TestCase):
    def view(self, raw, limit=6, skip=(), handles=("r1", "r2")):
        change = pricing.parse(raw)
        return pricing.view(change, pricing.price(change, handles, shown(), COSTS, None), shown().meters, lambda word: word, limit, skip)

    def test_the_block_is_shown_in_typed_form_with_the_lines_the_remainder_and_the_computed_sum_and_not_the_ais_words(self):
        seen = self.view(block("reduce", effect("r1", ("m1", "m2"), {"form": "ratio", "on": "units", "from": 12, "to": 4}), how="Secret advice."))
        self.assertEqual(seen["action"], "reduce")
        (one,) = seen["effects"]
        self.assertEqual((one["handle"], one["form"], one["usd"], one["from"], one["to"]), ("r1", "ratio", 100.0, 12.0, 4.0))
        self.assertEqual([(m["meter"], m["usd"], m["days"], m["words"][2]) for m in one["lines"]], [("m1", 60.0, 30, "Fixed Hours"), ("m2", 40.0, 30, "Held Data")])
        self.assertNotIn("Secret advice", json.dumps(seen))
        self.assertNotIn("how", seen)

    def test_an_assumption_is_shown_as_one_with_its_range(self):
        (one,) = self.view(block("reduce", effect("r1", ("m1",), {"form": "assumed", "low": 0.2, "high": 0.9})))["effects"]
        self.assertEqual((one["form"], one["remains"]), ("assumed", [0.2, 0.9]))

    def test_a_resource_that_could_not_be_priced_says_why_by_the_word_and_the_lines_are_cut_to_the_room_that_there_is(self):
        seen = self.view(block("remove", effect("r1", ("m1", "m2", "m4")), effect("r2", ("m9",))), limit=2)
        by = {e["handle"]: e for e in seen["effects"]}
        self.assertEqual(len(by["r1"]["lines"]), 2)
        self.assertEqual(by["r1"]["usd"], 125.0, "the sum is of every line, not of the lines that are shown")
        self.assertEqual(by["r2"], {"handle": "r2", "unpriced": "lines"})

    def test_a_resource_that_the_skeptic_is_not_shown_is_left_out(self):
        seen = self.view(block("remove", effect("r1", ("m1",)), effect("r2", ("m3",))), skip={"r2"})
        self.assertEqual([e["handle"] for e in seen["effects"]], ["r1"])

    def test_the_words_of_a_meter_pass_the_same_check_as_in_the_answer_of_a_tool(self):
        seen = pricing.view(pricing.parse(block("remove", effect("r1", ("m1",)))), priced(block("remove", effect("r1", ("m1",)))), registry(), lambda word: None, 6, ())
        self.assertEqual(seen["effects"][0]["lines"][0]["words"], ["other"] * 6)

    def test_no_block_is_nothing_to_show(self):
        self.assertIsNone(pricing.view(None, pricing.Priced(""), {}, lambda word: word, 6, ()))


class WhatDecidesDoesWithIt(unittest.TestCase):
    """decide.py: a change has the saving that code computed from the bill lines; Advisor's figure is kept and never added; a delete without a block is priced as it always was."""

    def lead(self, facts=None, advisor=None, cost=100.0):
        from cases.detectors import Lead
        return Lead(detector="investigation", resource_id="/subscriptions/s/resourceGroups/rg/providers/Microsoft.Example/things/t", resource_type="microsoft.example/things", name="t",
                    resource_group="rg", subscription_id="s", location="x", tags={}, managed_by="", facts=facts or {}, advisor_saving_usd=advisor, cost_usd_30d=cost)

    def decided(self, recommendation, facts=None, advisor=None, verdict="agree", cost=100.0):
        from cases.guards import Guards
        return decide.decide(self.lead(facts, advisor, cost), Guards({}), DetectiveAnswer(recommendation, 0.9, "s"), SkepticAnswer(verdict, (), ""))

    def facts(self, raw=None):
        change = pricing.parse(raw or block("remove", effect("r1", ("m1",))))
        return {pricing.KEY: pricing.digest(change, pricing.price(change, ("r1",), shown(), COSTS, None), "r1", None)}

    def test_a_change_has_the_saving_of_the_model_and_not_advisors_only(self):
        for recommendation in ("change", "delete", "investigate"):
            with self.subTest(recommendation=recommendation):
                self.assertEqual(self.decided(recommendation, self.facts(), None).monthly_saving_usd, 60.0)

    def test_advisors_figure_is_not_added_and_the_model_wins_where_there_is_one(self):
        self.assertEqual(self.decided("change", self.facts(), 7.5).monthly_saving_usd, 60.0)
        self.assertEqual(self.decided("change", {}, 7.5).monthly_saving_usd, 7.5)
        self.assertIsNone(self.decided("change", {}, None).monthly_saving_usd)

    def test_a_delete_without_a_block_is_priced_at_the_cost_lines_as_it_always_was_and_a_look_without_one_has_no_figure(self):
        self.assertEqual(self.decided("delete", {}, None, cost=44.0).monthly_saving_usd, 44.0)
        self.assertIsNone(self.decided("investigate", {}, None).monthly_saving_usd)

    def test_a_block_that_was_stated_and_could_not_be_priced_keeps_its_figure_out_even_for_a_delete_and_says_none_was_named_otherwise(self):
        refused = {pricing.KEY: {"action": "remove", "missing": "lines"}}
        self.assertIsNone(self.decided("delete", refused, None, cost=44.0).monthly_saving_usd)
        self.assertEqual(self.decided("change", refused, 7.5).monthly_saving_usd, 7.5, "Advisor's own figure is not the model's")
        self.assertEqual(self.decided("delete", {pricing.KEY: {"action": "none", "missing": "none"}}, None, cost=44.0).monthly_saving_usd, 44.0)

    def test_a_figure_above_what_the_finding_cost_in_30_days_allows_is_not_believed(self):
        self.assertEqual(self.decided("delete", self.facts(), None, cost=10.0).monthly_saving_usd, 10.0, "the cost lines, as for any delete with no figure of the model: 60 a month is more than 10 in 30 days allows")
        self.assertEqual(self.decided("delete", self.facts(), None, cost=20.0).monthly_saving_usd, 60.0, "60 a month can be 20 in 30 days when it came in the last week")

    def test_a_skeptic_that_disagrees_or_is_unsure_keeps_the_figure_and_the_finding_needs_a_person(self):
        for verdict in ("disagree", "unsure"):
            with self.subTest(verdict=verdict):
                outcome = self.decided("change", self.facts(), None, verdict=verdict)
                self.assertEqual((outcome.status, outcome.monthly_saving_usd), ("needs_human", 60.0))

    def test_a_dropped_case_has_no_figure(self):
        self.assertIsNone(self.decided("keep", self.facts()).monthly_saving_usd)


# -- whole investigations with fakes -----------------------------------------------------------------------------------------------------------------

def holding(meters=None, evidence=None, costs=(100.0, 30.0)) -> FakeToolbox:
    """What a toolbox shows after a run: resources r1 and r2 that cost `costs`, a measured zero for each, the number of units of r1 and the register of the meters."""
    resources = [resource(n, cost_usd_30d=cost) for n, cost in enumerate(costs, 1)]
    held = evidence if evidence is not None else {"r1": {**metrics(MetricA=0), "properties": {"units": 12}}, "r2": metrics(MetricA=0)}
    return FakeToolbox(resources, held, meters=registry() if meters is None else meters)


def crowd(count: int = 6) -> FakeToolbox:
    """`count` resources that cost 10 times their number, each billed for one meter that costs 5 times its number."""
    numbers = range(1, count + 1)
    return FakeToolbox([resource(n, cost_usd_30d=10.0 * n) for n in numbers], {f"r{n}": metrics(MetricA=0) for n in numbers}, meters={f"m{n}": line(f"r{n}", 5.0 * n) for n in numbers})


class WhenAnInvestigationPricesAChange(unittest.TestCase):
    """The figure of a case is what code worked out from the meters that the finding names, whatever the AI wrote, and the Skeptic judges the model."""

    def go(self, change=None, toolbox=None, skeptic=None, **more):
        raw = finding(**more) if change is None else finding(change=change, **more)
        h = Harness(FakeFoundry(answer(raw), skeptic=skeptic), toolbox or holding(), with_store=True)
        h.go()
        return h

    @staticmethod
    def figures(h):
        return {r["resourceName"]: r["monthlySavingUsd"] for r in h.of("case.result")}

    @staticmethod
    def facts(h):
        return {r.resource_name: r.facts.get(pricing.KEY) for r in h.store.cases_recent()}

    def test_a_case_is_saved_what_the_meters_that_the_finding_names_cost_and_not_what_the_resource_costs(self):
        h = self.go(block("remove", effect("r1", ("m1",)), effect("r2", ("m3",))))
        self.assertEqual(self.figures(h), {"thing-1": 60.0, "thing-2": 30.0})
        self.assertEqual({r["resourceName"]: r["costUsd30d"] for r in h.of("case.result")}, {"thing-1": 100.0, "thing-2": 30.0})
        (line_,) = h.of("investigation.finding")
        self.assertEqual((line_["change"], line_["pricedHandles"], line_["savingUsdMonth"]), ("remove", 2, 90.0))
        price = self.facts(h)["thing-1"]["price"]
        self.assertEqual((self.facts(h)["thing-1"]["action"], price["form"], price["billUsd"], price["lines"]), ("remove", "none", 60.0, 1))

    def test_a_count_that_is_reduced_is_checked_against_the_number_that_the_tools_showed_and_code_does_the_rest(self):
        ratio = {"form": "ratio", "on": "units", "from": 12, "to": 3}
        h = self.go(block("reduce", effect("r1", ("m1",), ratio)), proposal="change", basis="oversized", handles=("r1",))
        self.assertEqual(self.figures(h), {"thing-1": 45.0})
        for wrong in ({**ratio, "from": 13}, {**ratio, "on": "tier"}):
            with self.subTest(wrong=wrong):
                h = self.go(block("reduce", effect("r1", ("m1",), wrong)), proposal="change", basis="oversized", handles=("r1",))
                self.assertEqual((self.figures(h), self.facts(h)["thing-1"]["missing"]), ({"thing-1": None}, "remains"))

    def test_an_assumption_is_a_range_that_is_marked_as_the_ais_and_the_case_counts_its_low_end(self):
        h = self.go(block("reduce", effect("r1", ("m1",), {"form": "assumed", "low": 0.2, "high": 0.9})), proposal="change", basis="oversized", handles=("r1",))
        self.assertEqual(self.figures(h), {"thing-1": 6.0})
        price = self.facts(h)["thing-1"]["price"]
        self.assertEqual((price["form"], price["lowUsd"], price["highUsd"]), ("assumed", 6.0, 48.0))
        found = pricing.saved({pricing.KEY: self.facts(h)["thing-1"]}, 100.0)
        self.assertEqual(found.level, pricing.SCENARIO)
        self.assertIn("the AI's own assumption", found.basis)

    def test_a_share_of_days_is_the_ais_and_the_arithmetic_is_the_codes(self):
        h = self.go(block("schedule", effect("r1", ("m1",), {"form": "share_of_days", "days": 5, "of": 7})), proposal="change", basis="oversized", handles=("r1",))
        self.assertEqual(self.figures(h), {"thing-1": 17.14})

    def test_a_change_in_the_quantity_of_a_meter_is_priced_from_the_meter_and_a_ratio_on_a_property_that_the_meter_does_not_follow_is_not(self):
        toolbox = holding(meters={"m1": billed_units()}, evidence={"r1": {**metrics(MetricA=0), "properties": {"units": 4}}, "r2": metrics(MetricA=0)}, costs=(201.6, 30.0))
        quantity = self.go(block("reduce", effect("r1", ("m1",), {"form": "quantity", "from": 1440, "to": 0})), toolbox, proposal="change", basis="oversized", handles=("r1",))
        self.assertEqual(self.figures(quantity), {"thing-1": 201.6}, "2 extra units to none is all that the meter bills")
        price = self.facts(quantity)["thing-1"]["price"]
        self.assertEqual((price["form"], price["from"], price["to"], price["unit"]), ("quantity", 1440.0, 0.0, "1 Hour"))
        ratio = self.go(block("reduce", effect("r1", ("m1",), {"form": "ratio", "on": "units", "from": 4, "to": 2})), toolbox, proposal="change", basis="oversized", handles=("r1",))
        self.assertEqual(self.figures(ratio), {"thing-1": 100.8}, "4 units to 2 books half of a meter that bills the 2 above the included ones")
        wrong = self.go(block("reduce", effect("r1", ("m1",), {"form": "quantity", "from": 4, "to": 2})), toolbox, proposal="change", basis="oversized", handles=("r1",))
        self.assertEqual((self.figures(wrong), self.facts(wrong)["thing-1"]["missing"]), ({"thing-1": None}, "remains"), "the number of a property is not the quantity of a meter")

    def test_an_amount_that_the_ai_writes_into_the_block_or_the_answer_is_never_read(self):
        raw = block("remove", {**effect("r1", ("m1",)), "monthlySavingUsd": 9999.5, "usd": 8888.5}, how="Saves 7777.5 a month.")
        raw.update(savingUsd=6666.5, usd=5555.5)
        h = self.go(raw, monthlySavingUsd=4444.5, handles=("r1",))
        self.assertEqual(self.figures(h), {"thing-1": 60.0})
        everything = json.dumps([h.events, [r.facts for r in h.store.cases_recent()]])
        for invented in ("9999.5", "8888.5", "7777.5", "6666.5", "5555.5", "4444.5"):
            self.assertNotIn(invented, everything)

    def test_a_meter_that_no_tool_showed_makes_no_figure_not_even_for_a_delete_and_the_case_says_why(self):
        h = self.go(block("remove", effect("r1", ("m9",)), effect("r2", ("m3",))))
        self.assertEqual(self.figures(h), {"thing-1": None, "thing-2": 30.0})
        self.assertEqual(self.facts(h)["thing-1"]["missing"], "lines")
        self.assertEqual(self.facts(h)["thing-2"]["price"]["lowUsd"], 30.0)

    def test_a_delete_that_states_no_change_keeps_the_cost_lines_of_the_resource_as_it_always_did_and_the_action_none_is_the_same(self):
        for change in (None, {"action": "none", "effects": [], "how": "Cannot say."}):
            with self.subTest(change=change):
                self.assertEqual(self.figures(self.go(change)), {"thing-1": 100.0, "thing-2": 30.0})

    def test_a_meter_that_the_resource_does_not_own_adds_nothing_and_the_ones_that_it_owns_are_counted_once(self):
        h = self.go(block("remove", effect("r1", ("m1", "m3", "m1")), effect("r2", ("m1",))))
        self.assertEqual(self.figures(h), {"thing-1": 60.0, "thing-2": None})

    def test_advisors_own_estimate_is_kept_beside_the_figure_and_never_added_to_it(self):
        evidence = {"r1": {**metrics(MetricA=0), "advisor": [{"savingUsdMonth": 7.5}]}, "r2": metrics(MetricA=0)}
        h = self.go(block("remove", effect("r1", ("m1",))), holding(evidence=evidence), handles=("r1",))
        self.assertEqual(self.figures(h), {"thing-1": 60.0})
        found = pricing.saved({pricing.KEY: self.facts(h)["thing-1"]}, 100.0)
        self.assertIn("Azure Advisor's $7.50 is not added", found.basis)

    def test_a_cost_that_is_not_in_dollars_makes_no_figure_and_says_so(self):
        h = Harness(FakeFoundry(answer(finding(change=block("remove", effect("r1", ("m1",)))))), holding(costs=(None, None)), with_store=True)
        h.contexts = {SUBSCRIPTION: Context(locks=[], recent=set(), managed_groups=set(), costs={resource(1).resource_id.lower(): 5.0}, currency="EUR")}
        h.go()
        self.assertEqual(self.figures(h), {"thing-1": None, "thing-2": None})
        self.assertEqual(self.facts(h)["thing-1"]["missing"], "currency")

    def test_the_skeptic_is_shown_the_model_in_typed_form_and_neither_the_words_of_the_ai_for_a_person_nor_a_name(self):
        seen = {}

        def skeptic(given):
            seen.update(given)
            return agree_all(given)

        ratio = {"form": "ratio", "on": "units", "from": 12, "to": 3}
        self.go(block("reduce", effect("r1", ("m1", "m2"), ratio), how="Take the spare units away."), skeptic=skeptic, proposal="change", basis="oversized", handles=("r1",))
        model = seen["findings"][0]["change"]
        (one,) = model["effects"]
        self.assertEqual((model["action"], one["handle"], one["form"], one["usd"], one["from"], one["to"]), ("reduce", "r1", "ratio", 100.0, 12.0, 3.0))
        self.assertEqual([(m["meter"], m["usd"], m["words"][2]) for m in one["lines"]], [("m1", 60.0, "Fixed Hours"), ("m2", 40.0, "Held Data")])
        self.assertNotIn("how", model)
        self.assertNotIn("spare units", json.dumps(seen))

    def test_a_resource_that_a_guard_took_out_of_the_finding_is_not_in_the_model_that_the_skeptic_is_shown_and_has_no_figure(self):
        seen = {}
        toolbox = holding()
        toolbox.handles["r1"] = resource(1, cost_usd_30d=100.0, tags={"keep": "yes"})
        h = self.go(block("remove", effect("r1", ("m1",)), effect("r2", ("m3",))), toolbox, skeptic=lambda given: (seen.update(given), agree_all(given))[1])
        self.assertEqual(self.figures(h), {"thing-2": 30.0})
        self.assertEqual([one["handle"] for one in seen["findings"][0]["change"]["effects"]], ["r2"], "the model that the Skeptic judges is of the resources that it is shown rows for")
        (line_,) = h.of("investigation.finding")
        self.assertEqual((line_["guarded"], line_["pricedHandles"], line_["savingUsdMonth"]), (1, 1, 30.0))

    def test_a_finding_that_states_no_change_shows_the_skeptic_no_model(self):
        seen = {}
        self.go(None, skeptic=lambda given: (seen.update(given), agree_all(given))[1])
        self.assertNotIn("change", seen["findings"][0])

    def test_a_skeptic_that_doubts_the_model_leaves_the_figure_as_it_is_and_the_finding_to_a_person(self):
        h = self.go(block("remove", effect("r1", ("m1",))), skeptic=verdicts(("disagree", ("Half of it is fixed.",), "Contested.")), handles=("r1",))
        (result,) = h.of("case.result")
        self.assertEqual((result["status"], result["monthlySavingUsd"]), ("needs_human", 60.0))

    def test_the_findings_that_the_retired_paths_priced_by_kind_follow_the_same_path_from_the_meters_that_they_name(self):
        data = [resource(1, resource_type="microsoft.example/stores", cost_usd_30d=90.0), resource(2, resource_type="microsoft.example/stores", cost_usd_30d=40.0)]
        meters = {"m1": line("r1", 50.0, STORAGE), "m2": line("r1", 40.0, COMPUTE), "m3": line("r2", 25.0, STORAGE), "m4": line("r2", 15.0, COMPUTE)}
        stores = FakeToolbox(data, {"r1": metrics(MetricA=0), "r2": metrics(MetricA=0)}, meters=meters)
        h = self.go(block("remove", effect("r1", ("m1",)), effect("r2", ("m3",))), stores)
        self.assertEqual(self.figures(h), {"thing-1": 50.0, "thing-2": 25.0}, "what holds the data goes away and the compute that serves it stays")
        gateway = [resource(1, resource_type="microsoft.example/gateways", cost_usd_30d=200.0)]
        meters = {"m1": line("r1", 160.0, COMPUTE), "m2": line("r1", 40.0, NETWORK)}
        held = {"r1": {**metrics(MetricA=0), "properties": {"units": 4}}}
        h = self.go(block("reduce", effect("r1", ("m1",), {"form": "ratio", "on": "units", "from": 4, "to": 2})), FakeToolbox(gateway, held, meters=meters), proposal="change", basis="oversized", handles=("r1",))
        self.assertEqual(self.figures(h), {"thing-1": 80.0}, "half of the units that are billed per unit, and the fixed fee stays")


class WhenAGroupIsPriced(unittest.TestCase):
    """A finding for a group of resources is priced as the sum of its resources, each by its own meters, counted once: one case, one figure."""

    def go(self, effects):
        raw = finding(handles=[f"r{n}" for n in range(1, 7)], basis="other", proposal="investigate", change=block("remove", *effects))
        h = Harness(FakeFoundry(answer(raw)), crowd(), with_store=True)
        h.go()
        return h

    def test_the_figure_of_the_group_is_the_sum_of_its_resources_each_by_its_own_meters(self):
        h = self.go([effect(f"r{n}", (f"m{n}",)) for n in range(1, 7)])
        (result,) = h.of("case.result")
        self.assertEqual((result["groupSize"], result["costUsd30d"], result["monthlySavingUsd"]), (6, 210.0, 105.0))
        (line_,) = h.of("investigation.finding")
        self.assertEqual((line_["pricedHandles"], line_["savingUsdMonth"]), (6, 105.0))
        (record,) = h.store.cases_recent()
        price = record.facts[pricing.KEY]["price"]
        self.assertEqual((price["resources"], price["members"], price["lines"], price["billUsd"]), (6, 6, 6, 105.0))

    def test_a_group_of_which_some_resources_have_no_figure_adds_up_the_others_and_says_how_many_are_priced(self):
        h = self.go([effect(f"r{n}", (f"m{n}",)) for n in range(1, 5)])
        (result,) = h.of("case.result")
        self.assertEqual(result["monthlySavingUsd"], 50.0)
        (record,) = h.store.cases_recent()
        found = pricing.saved(record.facts, record.facts["costUsd30d"])
        self.assertIn("4 of 6 resources", found.basis)

    def test_a_meter_of_another_resource_of_the_group_is_not_counted_for_this_one(self):
        h = self.go([effect(f"r{n}", ("m1",)) for n in range(1, 7)])
        (result,) = h.of("case.result")
        self.assertEqual(result["monthlySavingUsd"], 5.0, "m1 is the meter of r1 only, and r2 to r6 name it in vain")


# -- the real tools ----------------------------------------------------------------------------------------------------------------------------------

def spend(estate, resource_id: str, words, daily: float, days: int = 30) -> None:
    """The bill lines of one resource that cost `daily` on each of the last `days` closed days before the day of the fake clock (2026-11-04)."""
    for n in range(days):
        estate.bill.append((SUBSCRIPTION, dt.date(2026, 11, 3) - dt.timedelta(days=n), resource_id, "Example Service", words, daily, 24.0))


class ReadsTheBill(FakeFoundry):
    """An Investigator that asks the real tools what each widget is billed for and writes its answer from the handles that they returned. `claim` gets the meter handles of each resource,
    dearest first, and under "type" those of a whole type."""

    NAMES = {"list_resources": ("type", "order_by", "limit", "offset"), "cost_meters": ("handle", "type", "service", "days", "offset")}

    def __init__(self, claim, days=None, then=None, **options):
        super().__init__(**options)
        self.claim, self.days, self.then = claim, days, then

    def ask(self, handler, name: str, **arguments) -> dict:
        return json.loads(handler(name, {**dict.fromkeys(self.NAMES[name]), **arguments}))

    def run(self, agent, user_input, handler=None, *, max_calls=20, max_seconds=None):
        if not agent.startswith(agents.INVESTIGATOR_NAME):
            return super().run(agent, user_input, handler, max_calls=max_calls, max_seconds=max_seconds)
        self.runs.append({"agent": agent, "input": user_input, "max_calls": max_calls, "max_seconds": max_seconds, "handler": handler})
        handles = handles_of(self.ask(handler, "list_resources", type=WIDGET))
        meters = {handle: [row[0] for row in self.ask(handler, "cost_meters", handle=handle, days=self.days)["rows"] if row[0]] for handle in handles}
        if self.then:
            for handle in handles:
                self.ask(handler, "cost_meters", handle=handle, days=self.then)  # a later read of another window shows the same handles
        meters["type"] = [row[0] for row in self.ask(handler, "cost_meters", type=WIDGET, days=self.days)["rows"] if row[0]]
        text = json.dumps({"findings": self.claim(meters), "examined": ["the widgets, by what they are billed for"]})
        calls = [{"name": "list_resources", "arguments": {}, "ok": True, "chars": 1}] + [{"name": "cost_meters", "arguments": {}, "ok": True, "chars": 1}] * (len(handles) + 1)
        return AgentRun(text=text, calls=calls, input_tokens=2000, output_tokens=300, responses=len(calls) + 1)


class WithTheRealBill(unittest.TestCase):
    """The real tools over the fake estate of test_toolbox_meters: the meter handles are the ones that cost_meters showed, and the figure follows from the bill lines that they were read from."""

    def setUp(self):
        self.estate = widgets(2)
        self.one, self.two = (self.estate.id_of(name).lower() for name in ("w1", "w2"))
        self.estate.cost_rows = [(SUBSCRIPTION, 100.0, self.one, "Example Service"), (SUBSCRIPTION, 40.0, self.two, "Example Service")]
        spend(self.estate, self.one, COMPUTE, 2.0)
        spend(self.estate, self.one, STORAGE, 1.0)
        spend(self.estate, self.two, COMPUTE, 1.0)

    def go(self, claim, **options):
        foundry = ReadsTheBill(claim, **options)
        h = Harness(foundry, real_toolbox(self.estate), with_store=True)
        h.go()
        return h, foundry

    @staticmethod
    def removes(*handles):
        def claim(meters):
            effects = [effect(handle, meters[handle][:1]) for handle in handles]
            return [finding(handles=list(handles), basis="low-usage", proposal="change", evidence=[], change=block("remove", *effects))]
        return claim

    def test_the_figure_is_the_cost_of_the_meters_that_the_real_tool_showed_for_the_resource(self):
        h, _ = self.go(self.removes("r1", "r2"))
        self.assertEqual({r["resourceName"]: (r["costUsd30d"], r["monthlySavingUsd"]) for r in h.of("case.result")}, {"w1": (100.0, 60.0), "w2": (40.0, 30.0)})

    def test_all_of_the_meters_of_a_resource_are_the_sum_of_their_lines_and_never_more_than_what_the_resource_cost(self):
        def claim(meters):
            return [finding(handles=["r1"], basis="low-usage", proposal="change", evidence=[], change=block("remove", effect("r1", meters["r1"])))]

        h, _ = self.go(claim)
        self.assertEqual({r["resourceName"]: r["monthlySavingUsd"] for r in h.of("case.result")}, {"w1": 90.0})

    def test_the_meters_of_a_whole_type_are_not_the_bill_of_one_resource(self):
        shown_to_it = []

        def claim(meters):
            shown_to_it.append(meters["type"])
            return [finding(handles=["r1"], basis="low-usage", proposal="change", evidence=[], change=block("remove", effect("r1", meters["type"])))]

        h, _ = self.go(claim)
        self.assertTrue(shown_to_it[0], "the tool did show the meters of the type")
        self.assertEqual({r["resourceName"]: r["monthlySavingUsd"] for r in h.of("case.result")}, {"w1": None})
        self.assertEqual([r.facts[pricing.KEY]["missing"] for r in h.store.cases_recent()], ["lines"])

    def test_meters_read_over_a_shorter_window_give_the_rate_of_that_window_and_the_same_rate_as_a_month_when_the_bill_is_flat(self):
        h, _ = self.go(self.removes("r1"), days=7)
        self.assertEqual({r["resourceName"]: r["monthlySavingUsd"] for r in h.of("case.result")}, {"w1": 60.0}, "7 days at 2 a day")
        self.assertEqual([r.facts[pricing.KEY]["price"].get("sinceUsd") for r in h.store.cases_recent()], [None], "a read of 7 days cannot say a mean since the meter began")

    def test_a_later_shorter_read_of_the_same_meters_does_not_take_the_figure_away_and_a_later_longer_one_gives_it(self):
        h, _ = self.go(self.removes("r1"), then=7)
        self.assertEqual({r["resourceName"]: r["monthlySavingUsd"] for r in h.of("case.result")}, {"w1": 60.0}, "30 days, then 7")
        h, _ = self.go(self.removes("r1"), days=7, then=30)
        self.assertEqual({r["resourceName"]: r["monthlySavingUsd"] for r in h.of("case.result")}, {"w1": 60.0}, "7 days, then 30")

    def test_a_word_of_a_meter_that_the_estate_could_have_written_never_reaches_the_skeptic_and_the_figure_is_still_the_bills(self):
        spend(self.estate, self.one, ("Example Compute", "Standard Tier", HOSTILE, "OnDemand", "Usage", "1 Hour"), 0.1)

        def claim(meters):
            return [finding(handles=["r1"], basis="low-usage", proposal="change", evidence=[], change=block("remove", effect("r1", meters["r1"])))]

        h, foundry = self.go(claim)
        self.assertEqual({r["resourceName"]: r["monthlySavingUsd"] for r in h.of("case.result")}, {"w1": 93.0})
        text = foundry.inputs()[-1]
        model = json.loads(text)["findings"][0]["change"]
        self.assertEqual([line_["words"][2] for line_ in model["effects"][0]["lines"]], ["Fixed Hours", "Held Data", "other"])
        for marker in ("IGNORE", "evil", "answer delete", "rg-app", "swedencentral"):
            self.assertNotIn(marker, text)


class ThePurityOfTheModule(unittest.TestCase):
    """The arithmetic of a saving is code that reads nothing and writes nothing: the brief imports it (cases/brief.py) and a page shows what it says."""

    def test_it_imports_only_the_standard_library_the_meters_and_the_roles_which_import_nothing_else_and_reaches_nothing(self):
        path = APP_ROOT / "cases"

        def imports(name):
            tree = ast.parse((path / f"{name}.py").read_text(encoding="utf-8"))
            return {(node.level, node.module) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {(0, a.name) for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names}

        standard = {(0, "__future__"), (0, "datetime"), (0, "math"), (0, "re"), (0, "json"), (0, "dataclasses"), (0, "typing")}
        self.assertEqual(imports("pricing"), {(0, "__future__"), (0, "datetime"), (0, "math"), (0, "re"), (0, "dataclasses"), (0, "typing"), (1, "meters"), (1, "roles")})
        for name in ("meters", "roles"):
            self.assertLessEqual(imports(name), standard, name)
        for name in ("pricing", "meters", "roles"):
            source = (path / f"{name}.py").read_text(encoding="utf-8")
            for pattern in (r"\.(now|utcnow|today)\(", r"\bimport time\b", r"\btime\.(time|sleep|monotonic)\(", r"\bopen\(", r"\bprint\(", r"\bos\.", r"\bsys\.", r"\burlopen", r"\bsocket", r"\blogging",
                            r"\brandom\b", r"\buuid\b"):
                self.assertIsNone(re.search(pattern, source), (name, pattern))


class WhatIsRetired(unittest.TestCase):
    def test_no_saving_is_priced_by_a_kind_of_resource_any_more(self):
        for name in ("unread", "gateways"):
            self.assertFalse((APP_ROOT / "cases" / f"{name}.py").exists(), name)
        source = "\n".join(path.read_text(encoding="utf-8") for path in (APP_ROOT / "cases").rglob("*.py"))
        for symbol in ("unread_saving", "unread_of", "scenario_saving", "gateways_of", "gateway_options", "from . import unread", "from . import gateways", "from .. import unread"):
            self.assertNotIn(symbol, source)


if __name__ == "__main__":
    unittest.main()
