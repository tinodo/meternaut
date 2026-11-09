"""What is checked after a change of a family, and what is claimed from it: the cost lines, an approval that changed nothing, and a plan whose app stopped.

Three things were wrong, each found by a review of the families, and each is pinned here with the clock of the world (familysupport.World.clock), so that a day is a call to `advance`:

1. The check by cost lines read once, too early, and took a resource with no cost line yet for a cost of zero: a resized machine that still runs could be "Verified" with its whole cost as the
   saving, and a cost that fell from 2.00 to 1.40 a day could be "Not confirmed" for good because a part of today's lines was in. It now reads whole days only, waits a day after a day ends,
   asks again the next day while there is no line, and a change that leaves the resource billing is never confirmed by "no cost".
2. An approval that found the resource in the state that the plan wants (somebody got there first) was shown as "made with their own Azure rights" and could be "Verified" with a saving two days
   later. It is marked `noChange`: it is not checked by cost lines, claims no saving, and every render says that nothing was changed.
3. A plan could stay `approved` for ever when the app stopped between the start and the write: it is closed as failed after two days, and the resource is free for a new plan.
"""
import datetime as dt
import unittest
from dataclasses import replace

import familysupport as fs
from familysupport import GROUP, SUB, World
from test_families_briefs import BASE, CONTACTS, PERSON, a_brief, console_of, texts_of

from support import APP_ROOT  # noqa: F401

from cases import brief, cardcheck, cards, letters
from cases.approvals import why_not
from cases.cards import CardContext
from cases.families import registry
from cases.families.base import per_day_check
from cases.families.words import SHOWN, Shown
from cases.memory_store import stamp
from cases.runner import APPROVED_UNKNOWN_DAYS, COST_GAVE_UP, GIVE_UP_AFTER_DAYS, NOT_MADE_APP_STOPPED, RUNNING_GIVE_UP_MINUTES, cost_window

OTHER = f"/subscriptions/{SUB}/resourcegroups/{GROUP}/providers/microsoft.compute/disks/another-disk"  # a cost line of another resource
D2 = "Standard_D2s_v5"


def machine(world, **more):
    resource = world.arm.add(fs.vm(**more))
    world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
    return resource


FAMILIES = {
    "stop-vm": (lambda w: machine(w), "vm", "delete", 60.0),
    "resize-vm": (lambda w: machine(w), "vm", "change", 60.0),
    "change-disk-tier": (lambda w: w.arm.add(fs.disk(sku="Premium_LRS")), "disk", "change", 20.0),
}


def approved(world, name):
    """A plan of the family that a person approved, and its resource."""
    make, kind, recommendation, cost = FAMILIES[name]
    resource = make(world)
    plan, _ = world.approved(resource, kind, recommendation, cost)
    return plan, resource


def to_the_aim(name, resource):
    """Somebody gets the resource to the state that the plan wants, between the plan and the OK."""
    if name == "stop-vm":
        fs.Arm.set_power(resource, "deallocated")
    elif name == "resize-vm":
        resource["properties"]["hardwareProfile"]["vmSize"] = D2
    else:
        resource["sku"] = {"name": "StandardSSD_LRS"}


def shown(world, plan, **more):
    action = world.action(plan)
    return a_brief(world.store.plan_get(plan.plan_id), world.store.case_get(plan.case_id), action, world.store.decisions_of_plan(plan.plan_id), may_answer=False, **more)


def rows_of(reply) -> dict[str, str]:
    """The names and values of every summary list on the page."""
    found = {}
    for dl in reply.main.find_all("dl", class_="summary"):
        for div in dl.find_all("div"):
            if div.find("dt") is not None and div.find("dd") is not None:
                found[div.find("dt").text()] = div.find("dd").text()
    return found


# -- 1. the cost lines ------------------------------------------------------------------------------------------------------------------------------

class TheWindowOfTheCostLines(unittest.TestCase):
    def test_it_holds_whole_days_only_from_the_day_after_the_change_to_a_day_that_ended_a_full_day_ago(self):
        finished = dt.datetime(2026, 11, 8, 9, 0, tzinfo=dt.timezone.utc)
        first_seen = None
        for hours in range(0, 24 * 10, 3):
            now = finished + dt.timedelta(hours=hours)
            window = cost_window(finished, now)
            if window is None:
                self.assertIsNone(first_seen, "once there is a window there is one for good")
                continue
            first_seen = first_seen or now
            first, last = window
            self.assertEqual(first, dt.date(2026, 11, 9), "the day of the change is part before and part after it: it is left out")
            ended = dt.datetime.combine(last + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
            self.assertGreaterEqual(now - ended, dt.timedelta(days=1), f"{last} ended less than a full day before {now}")
            self.assertLess(now - ended, dt.timedelta(days=2), "and it is the last day of which that is true")
        self.assertEqual(first_seen, dt.datetime(2026, 11, 11, 0, 0, tzinfo=dt.timezone.utc), "the first read: at midnight of the 11th, when the 9th has had its full day")

    def test_today_and_yesterday_are_never_in_it(self):
        finished = dt.datetime(2026, 11, 1, 23, 59, tzinfo=dt.timezone.utc)
        for days in range(2, 12):
            now = finished + dt.timedelta(days=days, hours=1)
            window = cost_window(finished, now)
            if window is not None:
                self.assertLessEqual(window[1], now.date() - dt.timedelta(days=2))


class ScenarioA(unittest.TestCase):
    """A resized machine that still runs has no cost line yet, and the check counted that as a cost of zero."""

    def test_the_family_never_confirms_a_saving_from_a_total_of_nothing(self):
        confirmed, note, saved = per_day_check(31.10, 0.0, 1, "the machine")
        self.assertEqual((confirmed, saved), (False, None))
        self.assertTrue(note.startswith("Not confirmed"))
        self.assertTrue(per_day_check(31.10, 1.0, 1, "the machine")[0], "a lower figure still confirms")

    def resized(self, name="resize-vm"):
        world = World()
        plan, resource = approved(world, name)
        self.assertEqual(world.run(plan).action.state, "done")
        return world, plan, resource

    def test_a_resize_or_a_tier_with_no_cost_line_of_its_own_yet_is_not_verified_and_stores_no_figure(self):
        for name in ("resize-vm", "change-disk-tier"):
            with self.subTest(name):
                world, plan, resource = self.resized(name)
                world.costs.totals = {OTHER: 12.0}  # the lines of other resources are in for the days, the line of this one is not
                world.clock.advance(days=3)
                self.assertEqual(world.tick().verified, [])
                action = world.action(plan)
                self.assertEqual(action.state, "done")
                for key in ("costAfterUsd", "savedUsdMonth", "costBeforeUsd30d", "costLinesFrom"):
                    self.assertNotIn(key, action.verification)
                self.assertEqual(world.store.case_get(plan.case_id).status, "done")
                self.assertEqual(len(world.costs.asked), 1)
                b = shown(world, plan)
                self.assertNotEqual(b.saving.level, "Verified")
                self.assertNotIn("no cost", b.saving.basis)

    def test_a_line_of_zero_for_a_resource_that_still_bills_is_no_data_either(self):
        world, plan, resource = self.resized()
        world.costs.totals = {resource["id"].lower(): 0.0}
        world.clock.advance(days=3)
        self.assertEqual(world.tick().verified, [])
        self.assertNotIn("costAfterUsd", world.action(plan).verification)

    def test_the_next_day_asks_again_and_the_figure_that_comes_is_a_lower_rate_never_no_cost(self):
        world, plan, resource = self.resized()
        world.costs.totals = {OTHER: 12.0}
        world.clock.advance(days=3)
        world.tick()
        world.tick()
        self.assertEqual(len(world.costs.asked), 1, "once a day however often the timer runs")
        world.costs.totals = {OTHER: 12.0, resource["id"].lower(): 1.5}  # the line of the machine is in: 1.5 over the two whole days from the 9th to the 10th
        world.clock.advance(days=1)
        self.assertEqual([a.state for a in world.tick().verified], ["verified"])
        self.assertEqual(world.costs.asked[-1], (SUB, dt.date(2026, 11, 9), dt.date(2026, 11, 10)))
        action = world.action(plan)
        self.assertEqual((action.verification["costLinesFrom"], action.verification["costLinesTo"]), ("2026-11-09", "2026-11-10"))
        self.assertEqual(action.verification["savedUsdMonth"], 37.5, "before: 60 over 30 days is 2 a day; after: 1.5 over two whole days is 0.75 a day; the difference of 1.25 a day over 30 days")
        b = shown(world, plan)
        self.assertEqual((b.saving.monthly, b.saving.level), (37.5, "Verified"))
        self.assertIn("lower than", b.saving.basis)
        self.assertNotIn("no cost", b.saving.basis)

    def test_the_page_says_when_the_cost_lines_were_asked_for_and_which_days_were_read(self):
        world, plan, resource = self.resized()
        world.costs.totals = {OTHER: 12.0}
        world.clock.advance(days=3)
        world.tick()
        case = world.store.case_get(plan.case_id)
        found = rows_of(console_of(world, plan, case).get(f"/ok/{plan.plan_id}"))["Checked afterwards"]
        self.assertIn("Cost lines were last asked for on 2026-11-11.", found)
        self.assertNotIn("costAskedOn", found)
        world.costs.totals = {OTHER: 12.0, resource["id"].lower(): 1.5}
        world.clock.advance(days=1)
        world.tick()
        found = rows_of(console_of(world, plan, world.store.case_get(plan.case_id)).get(f"/ok/{plan.plan_id}"))["Checked afterwards"]
        self.assertIn("Cost lines read from 2026-11-09 to 2026-11-10.", found)
        self.assertNotIn("last asked for", found)
        for raw in ("costAskedOn", "costLinesTo", "costGaveUp"):
            self.assertNotIn(raw, found)

    def test_the_whole_cost_is_not_the_saving_of_a_resize_even_when_a_record_says_that_the_cost_after_it_is_zero(self):
        for name in FAMILIES:
            with self.subTest(name):
                world = World()
                plan, _ = approved(world, name)
                world.run(plan)
                check = {"now": "x", "costAfterUsd": 0.0, "costBeforeUsd30d": 31.1, "currency": "USD"}
                if name != "stop-vm":
                    check["savedUsdMonth"] = 31.1
                world.store.action_put(replace(world.action(plan), state="verified", verified_at=stamp(fs.NOW), verification=check))
                saving = shown(world, plan).saving
                self.assertEqual((saving.level, saving.monthly), ("Verified", 31.1))
                if SHOWN[name].cost_ends:
                    self.assertEqual(saving.basis, "the cost lines after the change show no cost for this resource")
                else:
                    self.assertNotIn("no cost", saving.basis, "a resource that still bills never shows no cost")

    def test_the_words_of_no_cost_belong_to_the_families_whose_cost_ends(self):
        self.assertEqual({name for name, entry in SHOWN.items() if entry.cost_ends}, {"delete-disk", "delete-public-ip", "stop-vm", "delete-idle-resource"})
        for name in registry.names():
            family = registry.get(name)
            self.assertEqual(family.cost_ends, SHOWN[name].cost_ends)
            if family.deletes:
                self.assertTrue(family.cost_ends, f"{name} removes the resource")
        self.assertFalse(registry.get("resize-vm").cost_ends)
        self.assertFalse(registry.get("change-disk-tier").cost_ends)

    def test_a_family_that_does_not_say_that_its_cost_ends_is_read_the_safe_way(self):
        self.assertFalse(Shown.__dataclass_fields__["cost_ends"].default)

    def test_a_stop_is_still_confirmed_by_cost_lines_that_show_none_and_not_by_an_answer_without_any_line(self):
        world = World()
        plan, resource = approved(world, "stop-vm")
        self.assertEqual(world.run(plan).action.state, "done")
        world.clock.advance(days=3)
        self.assertEqual(world.tick().verified, [], "Cost Management has no line at all for the days: it is not in yet")
        self.assertNotIn("costAfterUsd", world.action(plan).verification)
        world.costs.totals = {OTHER: 12.0}
        world.clock.advance(days=1)
        self.assertEqual([a.state for a in world.tick().verified], ["verified"])
        action = world.action(plan)
        self.assertEqual(action.verification["costAfterUsd"], 0.0)
        b = shown(world, plan)
        self.assertEqual((b.saving.monthly, b.saving.level), (60.0, "Verified"))
        self.assertEqual(b.saving.basis, "the cost lines after the change show no cost for this resource")

    def test_the_days_of_waiting_are_used_up_and_the_record_says_that_no_figure_came(self):
        world, plan, resource = self.resized()
        world.costs.totals = {OTHER: 12.0}
        for _ in range(GIVE_UP_AFTER_DAYS + 1):
            world.clock.advance(days=1)
            world.tick()
        action = world.action(plan)
        self.assertEqual(action.state, "done")
        self.assertTrue(action.verification["costGaveUp"])
        self.assertEqual(action.verification["note"], COST_GAVE_UP)
        self.assertNotIn("Confirmed", COST_GAVE_UP)
        self.assertIn(COST_GAVE_UP, shown(world, plan).outcome.lines)
        asked = len(world.costs.asked)
        world.costs.totals = {OTHER: 12.0, resource["id"].lower(): 1.0}
        world.clock.advance(days=1)
        self.assertEqual(world.tick().verified, [])
        self.assertEqual(len(world.costs.asked), asked, "it stopped asking")
        self.assertNotEqual(shown(world, plan).saving.level, "Verified")


class ScenarioB(unittest.TestCase):
    """A machine whose cost fell from 2.00 to 1.40 a day was "Not confirmed" for good because 70 percent of the lines of today were in."""

    def lines(self, resource):
        mine = resource["id"].lower()
        return {dt.date(2026, 11, 8): {mine: 2.0, OTHER: 1.0},   # the day of the change: part before it and part after it
                dt.date(2026, 11, 9): {mine: 1.40, OTHER: 1.0},
                dt.date(2026, 11, 10): {mine: 1.40, OTHER: 1.0},
                dt.date(2026, 11, 11): {mine: 0.98, OTHER: 0.7}}  # today, at 9 in the morning: 70 percent of its lines are in

    def test_the_whole_days_say_a_lower_rate_and_the_part_of_today_is_not_read(self):
        world = World()
        plan, resource = approved(world, "resize-vm")
        world.run(plan)
        world.costs.days = self.lines(resource)
        world.clock.advance(days=2, hours=14)  # 10 Nov, 23:00: the 9th has not had its full day yet
        self.assertEqual(world.tick().verified, [])
        self.assertEqual(world.costs.asked, [])
        world.clock.advance(hours=10)  # 11 Nov, 09:00: the 9th ended more than a day ago, and the 10th and today are still not read
        self.assertEqual([a.state for a in world.tick().verified], ["verified"])
        self.assertEqual(world.costs.asked, [(SUB, dt.date(2026, 11, 9), dt.date(2026, 11, 9))])
        action = world.action(plan)
        self.assertEqual(action.verification["costAfterUsd"], 1.4)
        self.assertEqual(action.verification["savedUsdMonth"], 18.0, "2.00 a day before, 1.40 a day after: 0.60 a day, 18.00 over 30 days")
        self.assertIn("Confirmed", action.verification["note"])

    def test_the_same_with_more_whole_days_after_it_and_a_part_of_today_again(self):
        world = World()
        plan, resource = approved(world, "resize-vm")
        world.run(plan)
        mine = resource["id"].lower()
        world.costs.days = {dt.date(2026, 11, 8): {mine: 2.0, OTHER: 1.0}, dt.date(2026, 11, 9): {mine: 1.40, OTHER: 1.0}, dt.date(2026, 11, 10): {mine: 1.40, OTHER: 1.0},
                            dt.date(2026, 11, 11): {mine: 1.40, OTHER: 1.0}, dt.date(2026, 11, 12): {mine: 0.84, OTHER: 0.6},  # yesterday: 60 percent of its lines are in
                            dt.date(2026, 11, 13): {mine: 0.98, OTHER: 0.7}}  # today: 70 percent
        world.clock.advance(days=5)  # 13 Nov, 09:00
        self.assertEqual([a.state for a in world.tick().verified], ["verified"])
        self.assertEqual(world.costs.asked, [(SUB, dt.date(2026, 11, 9), dt.date(2026, 11, 11))])
        action = world.action(plan)
        self.assertEqual(action.verification["costAfterUsd"], 4.2, "the 9th, the 10th and the 11th: three whole days")
        self.assertEqual(action.verification["savedUsdMonth"], 18.0)

    def test_a_cost_that_did_not_fall_is_not_confirmed_and_says_so_and_is_not_asked_for_again(self):
        world = World()
        plan, resource = approved(world, "resize-vm")
        world.run(plan)
        mine = resource["id"].lower()
        world.costs.days = {dt.date(2026, 11, 9): {mine: 2.4, OTHER: 1.0}}
        world.clock.advance(days=3)
        self.assertEqual(world.tick().verified, [])
        action = world.action(plan)
        self.assertEqual(action.verification["costAfterUsd"], 2.4)
        self.assertTrue(action.verification["note"].startswith("Not confirmed"))
        world.clock.advance(days=1)
        world.tick()
        self.assertEqual(len(world.costs.asked), 1, "a figure was read: it is not read again")


# -- 2. an approval that changed nothing ------------------------------------------------------------------------------------------------------------

class AnApprovalThatChangedNothing(unittest.TestCase):
    def nothing_to_do(self, name):
        world = World()
        plan, resource = approved(world, name)
        to_the_aim(name, resource)
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("unchanged", "done"), done.action.result)
        self.assertEqual(world.arm.writes(), [], "nothing was written")
        return world, plan, resource, done.action

    def test_it_is_marked_in_the_record_of_each_family_and_of_the_old_deletes(self):
        for name in FAMILIES:
            with self.subTest(name):
                world, plan, resource, action = self.nothing_to_do(name)
                self.assertIs(action.verification["noChange"], True)
                self.assertTrue(action.no_change)
                self.assertEqual(world.state(plan), ("consumed", "done", "done"))
        for kind, name, detector in (("disk", "delete-disk", "orphan-managed-disk"), ("ip", "delete-public-ip", "orphan-public-ip")):
            with self.subTest(name):
                world = World()
                resource = world.arm.add(fs.disk() if kind == "disk" else fs.simple("ip"))
                plan, _ = world.approved(resource, kind, "delete", 20.0, detector=detector)
                del world.arm.resources[resource["id"].lower()]
                done = world.run(plan)
                self.assertEqual(done.action.state, "done")
                self.assertIs(done.action.verification["noChange"], True)
                self.assertEqual(world.arm.writes(), [])

    def test_a_change_that_was_made_is_not_marked(self):
        for name in FAMILIES:
            with self.subTest(name):
                world = World()
                plan, _ = approved(world, name)
                done = world.run(plan)
                self.assertEqual(done.action.state, "done")
                self.assertNotIn("noChange", done.action.verification)
                self.assertFalse(done.action.no_change)
                self.assertEqual(len(world.arm.writes()), 1)

    def test_two_days_later_it_is_not_verified_and_no_saving_is_booked_for_it(self):
        for name in FAMILIES:
            with self.subTest(name):
                world, plan, resource, action = self.nothing_to_do(name)
                world.costs.totals = {OTHER: 12.0}  # a stop would be "confirmed" by these lines: no line of the machine shows no cost
                for _ in range(8):
                    world.clock.advance(days=1)
                    self.assertEqual(world.tick().verified, [])
                after = world.action(plan)
                self.assertEqual((after.state, after.verified_at), ("done", None))
                for key in ("costAfterUsd", "savedUsdMonth", "costLinesFrom", "costAskedOn", "costGaveUp"):
                    self.assertNotIn(key, after.verification)
                self.assertEqual(world.costs.asked, [], "Cost Management is not even asked: there is nothing to confirm")
                self.assertEqual(world.state(plan), ("consumed", "done", "done"))
                b = shown(world, plan)
                self.assertEqual((b.saving.monthly, b.saving.level), (None, ""))
                self.assertEqual(b.saving.why_none, brief.NOTHING_CHANGED_SAVING)
                self.assertTrue(b.saving.specific)

    def test_the_decision_brief_says_that_nothing_was_changed_and_not_that_it_was_made_with_their_rights(self):
        world, plan, resource, action = self.nothing_to_do("stop-vm")
        b = shown(world, plan)
        self.assertEqual((b.outcome.state, b.outcome.title, b.outcome.result), ("unchanged", "Nothing was changed", "Nothing was changed"))
        self.assertEqual(b.outcome.lines, ("Approved by Tino.", "Nothing was changed: the machine was already stopped and released when Meternaut looked."))
        for line in b.outcome.lines:
            self.assertNotIn("their own Azure rights", line)
            self.assertNotIn("Nothing to change", line)
        self.assertEqual(b.outcome.by, "Tino")

    def test_the_line_of_each_family_and_of_the_old_deletes(self):
        said = {"stop-vm": "Nothing was changed: the machine was already stopped and released when Meternaut looked.",
                "resize-vm": "Nothing was changed: the machine was already of size Standard_D2s_v5 when Meternaut looked.",
                "change-disk-tier": "Nothing was changed: the disk was already a Standard SSD (StandardSSD_LRS) when Meternaut looked."}
        for name, line in said.items():
            with self.subTest(name):
                world, plan, resource, action = self.nothing_to_do(name)
                self.assertEqual(shown(world, plan).outcome.lines, ("Approved by Tino.", line))
        world = World()
        resource = world.arm.add(fs.disk())
        plan, _ = world.approved(resource, "disk", "delete", 20.0, detector="orphan-managed-disk")
        del world.arm.resources[resource["id"].lower()]
        world.run(plan)
        self.assertEqual(shown(world, plan).outcome.lines, ("Approved by Tino.", "Nothing was changed: the resource did not exist any more when Meternaut looked."))

    def test_the_sentence_is_cut_the_same_way_for_any_result(self):
        for result, expected in (("The machine was already stopped. Nothing to change.", "Nothing was changed: the machine was already stopped."),
                                 ("VM is off. Nothing to delete.", "Nothing was changed: VM is off."),
                                 ("", "Nothing was changed."), ("Nothing to change.", "Nothing was changed.")):
            self.assertEqual(brief._nothing_changed(result), expected)

    def test_the_page_says_it_in_the_notice_and_in_the_details_and_shows_nothing_that_was_checked_afterwards(self):
        world, plan, resource, action = self.nothing_to_do("stop-vm")
        case = world.store.case_get(plan.case_id)
        reply = console_of(world, plan, case).get(f"/ok/{plan.plan_id}")
        self.assertEqual(reply.status, 200)
        (title,) = reply.main.find_all("p", class_="notice-title")
        self.assertEqual(title.text(), "Nothing was changed")
        notice = title.parent.text()
        self.assertIn("Approved by Tino.", notice)
        self.assertIn("Nothing was changed: the machine was already stopped and released when Meternaut looked.", notice)
        self.assertNotIn("own Azure rights", notice)
        found = {}
        for dl in reply.main.find_all("dl", class_="summary"):
            for div in dl.find_all("div"):
                if div.find("dt") is not None and div.find("dd") is not None:
                    found[div.find("dt").text()] = div.find("dd").text()
        self.assertEqual(found["State"], "Done. Nothing was changed.")
        self.assertEqual(found["Checked afterwards"], "Nothing was changed, so there is nothing to check afterwards.")
        self.assertNotIn("noChange", reply.text)
        self.assertNotIn("Done and checked", reply.text)

    def test_the_letter_says_that_nothing_had_to_change_and_never_that_it_ran_or_can_be_undone(self):
        world, plan, resource, action = self.nothing_to_do("stop-vm")
        case = world.store.case_get(plan.case_id)
        letter = letters.done_letter(world.store.plan_get(plan.plan_id), action, case, PERSON, BASE, fs.NOW, CONTACTS)
        self.assertEqual(letter.subject, "[Meternaut] Nothing had to change in Azure")
        for wanted in ("You approved:", "Nothing was changed: the machine was already stopped and released when Meternaut looked.", "No saving is claimed for this approval."):
            self.assertIn(wanted, letter.text)
        for unwanted in ("Done:", "has run", "Start the machine again", "cannot be undone", "own Azure rights", "confirm it after a few days", "a month"):
            self.assertNotIn(unwanted, letter.text)

    def test_the_card_says_it_and_holds_no_saving_and_no_undo(self):
        world, plan, resource, action = self.nothing_to_do("stop-vm")
        b = shown(world, plan)
        card = cards.card_for(b, CardContext(page_url=f"{BASE}/ok/{b.plan_id}", contacts=CONTACTS))
        found = texts_of(card)
        self.assertEqual(cardcheck.check(card), [])
        self.assertEqual(found["outcome"], "Nothing was changed")
        self.assertEqual(found["outcome-line-1"], "Approved by Tino.")
        self.assertTrue(found["outcome-line-2"].startswith("Nothing was changed: the machine was already stopped"))
        for absent in ("undo", "saving-word", "value"):
            self.assertNotIn(absent, found)

    def test_the_history_does_not_say_that_a_change_was_made(self):
        world, plan, resource, action = self.nothing_to_do("stop-vm")
        reply = console_of(world, plan, world.store.case_get(plan.case_id)).get("/history")
        lines = [li.text() for ul in reply.main.find_all("ul", class_="feed") for li in ul.find_all("li")]
        self.assertTrue(any(line.startswith("Nothing was changed: Stop (deallocate) the virtual machine planted-vm-1") for line in lines), lines)
        self.assertFalse(any(line.startswith("Change made:") for line in lines), lines)

    def test_a_change_that_was_made_still_reads_as_before(self):
        world = World()
        plan, resource = approved(world, "stop-vm")
        world.run(plan)
        b = shown(world, plan)
        self.assertEqual((b.outcome.state, b.outcome.title), ("done", "Done"))
        self.assertEqual(b.outcome.lines[0], "Approved by Tino, and made with their own Azure rights.")
        letter = letters.done_letter(world.store.plan_get(plan.plan_id), world.action(plan), world.store.case_get(plan.case_id), PERSON, BASE, fs.NOW, CONTACTS)
        self.assertEqual(letter.subject, "[Meternaut] A change to Azure has run")
        self.assertIn("Done:", letter.text)


# -- 3. a plan whose app stopped ----------------------------------------------------------------------------------------------------------------------

class AnApprovedPlanWhoseAppStopped(unittest.TestCase):
    """The app began the change (the action says running) and stopped before it wrote or could say: after a quarter of an hour the action is `unknown`, and the plan stays `approved`."""

    def stopped(self):
        world = World()
        resource = machine(world)
        plan, action = world.approved(resource, "vm", "delete", 60.0)
        world.store.action_put(replace(action, state="running", started_at=stamp(world.clock())))
        self.assertEqual(world.arm.writes(), [])
        world.clock.advance(minutes=20)
        world.tick()
        self.assertEqual(world.state(plan), ("approved", "unknown", "approved"))
        return world, plan, resource

    def free(self, world, plan, resource):
        """Why a new plan for the resource cannot be made now, or None when it can."""
        lead = world.lead(resource, "vm")
        proposed = replace(world.store.case_get(plan.case_id), status="proposed")
        return why_not(proposed, lead, world.settings, world.store, registry.get("stop-vm"))

    def test_it_is_closed_as_failed_after_two_days_and_the_resource_is_free_again(self):
        world, plan, resource = self.stopped()
        self.assertEqual(self.free(world, plan, resource), "a plan for this resource is open already")
        world.clock.advance(days=APPROVED_UNKNOWN_DAYS - 1, hours=23)
        self.assertEqual(world.tick().finished, [])
        self.assertEqual(world.state(plan), ("approved", "unknown", "approved"), "not yet: the resource may still show the change")
        world.clock.advance(hours=2)
        closed = world.tick().finished
        self.assertEqual([a.state for a in closed], ["failed"])
        self.assertEqual(world.state(plan), ("failed", "failed", "failed"))
        action = world.action(plan)
        self.assertEqual((action.result, action.error), (NOT_MADE_APP_STOPPED, NOT_MADE_APP_STOPPED))
        self.assertIn("The change was not made: the app stopped before it could say", action.result)
        self.assertIsNone(action.verified_at)
        self.assertIsNone(self.free(world, plan, resource), "the resource is free again")
        self.assertEqual(world.arm.writes(), [], "nothing was written, then or later")
        self.assertEqual(world.tick().finished, [], "it is closed once")
        self.assertEqual(world.state(plan), ("failed", "failed", "failed"))

    def test_the_page_and_the_decision_brief_show_a_change_that_was_not_made(self):
        world, plan, resource = self.stopped()
        world.clock.advance(days=3)
        world.tick()
        b = shown(world, plan)
        self.assertEqual((b.state, b.outcome.state, b.outcome.title), ("failed", "failed", "Not made"))
        self.assertEqual(b.outcome.lines, (NOT_MADE_APP_STOPPED,))
        case = world.store.case_get(plan.case_id)
        reply = console_of(world, plan, case).get(f"/ok/{plan.plan_id}")
        (title,) = reply.main.find_all("p", class_="notice-title")
        self.assertEqual(title.text(), "Not made")

    def test_a_change_that_the_resource_shows_is_settled_by_the_check_and_not_closed(self):
        world, plan, resource = self.stopped()
        fs.Arm.set_power(resource, "deallocated")  # the machine is stopped in fact: the write went through before the app stopped
        world.clock.advance(minutes=1)
        self.assertEqual([a.state for a in world.tick().finished], [])
        self.assertEqual(world.state(plan), ("consumed", "done", "done"))
        self.assertIsNotNone(world.action(plan).finished_at, "the day of the change counts from the check that saw it")
        world.clock.advance(days=APPROVED_UNKNOWN_DAYS + 1)
        world.tick()
        self.assertEqual(world.state(plan), ("consumed", "done", "done"), "it is not closed as failed")

    def test_a_change_that_was_settled_late_is_confirmed_by_the_cost_lines_like_any_other(self):
        world, plan, resource = self.stopped()
        fs.Arm.set_power(resource, "deallocated")
        world.clock.advance(minutes=1)
        world.tick()
        world.costs.totals = {OTHER: 12.0}
        world.clock.advance(days=4)
        self.assertEqual([a.state for a in world.tick().verified], ["verified"])
        self.assertEqual(world.state(plan), ("consumed", "verified", "verified"))

    def test_a_plan_whose_resource_could_not_be_read_is_not_closed_as_not_made_and_is_settled_when_the_reads_work_again(self):
        world, plan, resource = self.stopped()
        world.arm.read_status = 403  # the reader is refused: nobody can say whether the change was made
        world.clock.advance(days=APPROVED_UNKNOWN_DAYS, hours=2)
        self.assertEqual(world.tick().finished, [])
        self.assertEqual(world.state(plan), ("approved", "unknown", "approved"), "the reads failed: it is not known that the change was not made")
        world.clock.advance(days=3)
        self.assertEqual(world.tick().finished, [], "however long the reads fail")
        fs.Arm.set_power(resource, "deallocated")  # the machine was stopped in fact, and the reads work again
        world.arm.read_status = 200
        world.clock.advance(minutes=1)
        self.assertEqual(world.tick().finished, [])
        self.assertEqual(world.state(plan), ("consumed", "done", "done"), "the check sees the change and settles it: it is not closed as failed")

    def test_a_resource_that_was_read_and_does_not_show_the_change_is_closed_once_the_two_days_are_over(self):
        world, plan, resource = self.stopped()
        world.clock.advance(days=APPROVED_UNKNOWN_DAYS, hours=2)
        self.assertEqual([a.state for a in world.tick().finished], ["failed"], "the reads answered: the machine runs")
        self.assertEqual(world.action(plan).verification.get("lastRead"), "pending")

    def test_a_read_that_failed_after_one_that_answered_keeps_the_plan_open(self):
        world, plan, resource = self.stopped()
        world.clock.advance(days=1)
        world.tick()
        self.assertEqual(world.action(plan).verification.get("lastRead"), "pending")
        world.arm.read_status = 500
        world.clock.advance(days=APPROVED_UNKNOWN_DAYS)
        self.assertEqual(world.tick().finished, [])
        self.assertEqual(world.action(plan).verification.get("lastRead"), "unknown")
        self.assertEqual(world.state(plan), ("approved", "unknown", "approved"))

    def test_a_plan_that_is_used_is_never_closed_by_this_rule_however_long_its_action_is_unknown(self):
        world = World()
        resource = machine(world)
        plan, _ = world.approved(resource, "vm", "delete", 60.0)
        world.arm.operation_polls = ["InProgress"]
        world.arm.stop_never = True
        self.assertEqual(world.run(plan).action.state, "running")
        world.clock.advance(minutes=RUNNING_GIVE_UP_MINUTES + 1)
        self.assertEqual([a.state for a in world.tick().finished], ["unknown"])
        self.assertEqual(world.state(plan)[0:2], ("consumed", "unknown"))
        world.clock.advance(days=APPROVED_UNKNOWN_DAYS + 2)
        self.assertEqual(world.tick().finished, [])
        self.assertEqual(world.state(plan)[0:2], ("consumed", "unknown"))


if __name__ == "__main__":
    unittest.main()
