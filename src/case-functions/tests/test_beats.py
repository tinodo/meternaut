"""The beats of an investigation (cases/beats.py, docs/proposals/25-beats.md): the plan that code makes from what the kinds of resource cost, the pictures that code reads for a beat before the
Investigator starts, what a beat is told of the beats before it, and the investigation that runs the beats one after the other on one toolbox. Every kind in this file is invented."""
import json
import re
import unittest
from dataclasses import replace
from types import SimpleNamespace

from support import APP_ROOT, RG

from cases import beats
from cases.detectors import Context

# An invented estate. The cost of the last 30 days of each kind, and of the lines that no resource owns; 11,000 in all, so that 95 percent is 10,450.
ESTATE = {"contoso.compute/rigs": 3000.0, "contoso.compute/racks": 1500.0, "fabrikam.store/vaults": 2000.0, "fabrikam.store/lockers": 800.0, "northwind.net/links": 1200.0,
          "northwind.net/hubs": 500.0, "adatum.data/lakes": 400.0, "tailspin.misc/things": 300.0, "tailspin.misc/bits": 150.0, "woodgrove.tiny/dots": 100.0,
          "litware.a/x": 30.0, "litware.b/y": 20.0}
UNOWNED = 1000.0


def kinds_of(plan):
    return [list(beat.kinds) for beat in plan]


class TheFocusThatCodeChooses(unittest.TestCase):
    def test_the_plan_of_a_hand_computed_estate(self):
        # Ranked: rigs 3000, vaults 2000, racks 1500, links 1200, the lines of no resource 1000, lockers 800, hubs 500, lakes 400, things 300 (10,700 in all: the first to pass 10,450), then bits, dots, x, y.
        plan = beats.plan(ESTATE, UNOWNED, 6)
        self.assertEqual(kinds_of(plan), [["contoso.compute/rigs", "contoso.compute/racks"], ["fabrikam.store/vaults", "fabrikam.store/lockers"], ["northwind.net/links", "northwind.net/hubs"], [],
                                          ["adatum.data/lakes"], ["tailspin.misc/things", "tailspin.misc/bits", "woodgrove.tiny/dots", "litware.a/x", "litware.b/y"]])
        self.assertEqual([beat.billing for beat in plan], [False, False, False, True, False, False])
        self.assertEqual([(beat.number, beat.of) for beat in plan], [(n, 6) for n in range(1, 7)])
        self.assertEqual([beat.rest for beat in plan], [0] * 6)

    def test_a_kind_that_belongs_to_the_same_service_as_a_dearer_one_goes_with_it_and_a_beat_holds_three_kinds_at_most(self):
        costs = {f"contoso.compute/k{n}": 100.0 - n for n in range(5)} | {"fabrikam.store/s": 50.0}
        plan = beats.plan(costs, 0.0, 6)
        self.assertEqual(kinds_of(plan), [["contoso.compute/k0", "contoso.compute/k1", "contoso.compute/k2"], ["contoso.compute/k3", "contoso.compute/k4"], ["fabrikam.store/s"]])
        self.assertEqual([beat.number for beat in plan], [1, 2, 3])

    def test_the_kinds_below_the_floor_are_left_to_the_last_beat_when_the_plan_has_room_for_one(self):
        plan = beats.plan(ESTATE, UNOWNED, 8)
        self.assertEqual(kinds_of(plan)[5:], [["tailspin.misc/things"], ["tailspin.misc/bits", "woodgrove.tiny/dots", "litware.a/x", "litware.b/y"]], "the last beat holds what is left, dearest first")
        self.assertEqual(len(plan), 7)
        self.assertEqual({beat.of for beat in plan}, {7})

    def test_a_plan_never_has_more_beats_than_it_may_and_the_last_one_takes_what_does_not_fit(self):
        plan = beats.plan(ESTATE, UNOWNED, 3)
        self.assertEqual(kinds_of(plan)[:2], [["contoso.compute/rigs", "contoso.compute/racks"], ["fabrikam.store/vaults", "fabrikam.store/lockers"]])
        last = plan[2]
        self.assertEqual(len(plan), 3)
        self.assertEqual(last.kinds, ("northwind.net/links", "northwind.net/hubs", "adatum.data/lakes", "tailspin.misc/things", "tailspin.misc/bits", "woodgrove.tiny/dots", "litware.a/x", "litware.b/y"))
        self.assertTrue(last.billing, "the lines that no resource owns are in what it holds")
        one = beats.plan(ESTATE, UNOWNED, 1)
        self.assertEqual((len(one), one[0].kinds[:2], one[0].billing), (1, ("contoso.compute/rigs", "fabrikam.store/vaults"), True))

    def test_a_catch_all_names_the_dearest_few_and_counts_the_others(self):
        costs = {f"contoso.thing{n:02d}/kind": 100.0 - n for n in range(20)}
        (only,) = beats.plan(costs, 0.0, 1)
        self.assertEqual(len(only.kinds), beats.CATCH_ALL_KINDS)
        self.assertEqual(only.kinds[0], "contoso.thing00/kind")
        self.assertEqual(only.rest, 20 - beats.CATCH_ALL_KINDS)

    def test_the_lines_that_no_resource_owns_are_a_beat_of_their_own_when_they_are_all_there_is(self):
        self.assertEqual(beats.plan({}, 40.0, 4), [beats.Beat(1, (), True, 0, 1)])
        self.assertEqual(beats.plan({"contoso.compute/rigs": 10.0}, 0.0, 4)[0].billing, False)

    def test_there_is_no_plan_when_nothing_is_known_to_cost_anything(self):
        for costs, unowned in (({}, 0.0), ({"contoso.compute/rigs": 0.0}, 0.0), ({"contoso.compute/rigs": -5.0}, -1.0)):
            self.assertEqual(beats.plan(costs, unowned, 6), [])
        self.assertEqual(beats.plan(ESTATE, UNOWNED, 0), [])

    def test_the_order_does_not_depend_on_the_order_of_what_it_is_given_and_a_tie_goes_by_name(self):
        first = beats.plan(dict(reversed(list(ESTATE.items()))), UNOWNED, 6)
        self.assertEqual(first, beats.plan(ESTATE, UNOWNED, 6))
        tied = beats.plan({"b.x/y": 10.0, "a.x/y": 10.0, "c.x/y": 10.0}, 0.0, 6)
        self.assertEqual(kinds_of(tied), [["a.x/y"], ["b.x/y"], ["c.x/y"]])

    def test_one_dear_kind_is_a_beat_of_its_own_and_the_cheap_rest_waits_in_the_last_beat(self):
        plan = beats.plan({"contoso.compute/rigs": 9000.0, "tailspin.misc/a": 10.0, "tailspin.misc/b": 5.0}, 0.0, 4)
        self.assertEqual(kinds_of(plan), [["contoso.compute/rigs"], ["tailspin.misc/a", "tailspin.misc/b"]])

    def test_no_kind_of_resource_is_written_in_the_module(self):
        source = (APP_ROOT / "cases" / "beats.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"""["'][a-z0-9]+\.[a-z0-9]+/[a-z0-9]+["']""", source), [], "a kind comes from the bill, by dollars; the code names none")

    def test_the_spend_is_read_from_the_cost_lines_that_the_watch_has_by_kind_and_the_lines_of_no_resource(self):
        a = f"{RG}/rg-a/providers/Contoso.Compute/rigs/one"
        b = f"{RG}/rg-a/providers/Fabrikam.Store/vaults/two"
        contexts = {"s1": Context(costs={a: 30.0, b: 20.0, "": 7.0}, currency="USD"), "s2": Context(costs={a.replace("one", "three"): 5.0, "": 3.0}, currency="USD"),
                    "s3": Context(costs={a: 999.0, "": 999.0}, currency="EUR"), "s4": Context(costs=None)}
        kinds, unowned = beats.spend(contexts)
        self.assertEqual((kinds, unowned), ({"contoso.compute/rigs": 35.0, "fabrikam.store/vaults": 20.0}, 10.0), "a subscription whose cost is not in dollars or was not read counts for nothing")


class TheseAreTheTypedWordsOfABeat(unittest.TestCase):
    def test_a_beat_with_no_focus_is_open(self):
        self.assertTrue(beats.Beat().open)
        self.assertFalse(beats.Beat(1, ("contoso.compute/rigs",)).open)
        self.assertFalse(beats.Beat(1, (), True).open)


if __name__ == "__main__":
    unittest.main()
