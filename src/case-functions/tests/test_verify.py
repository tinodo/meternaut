"""A request ends when the bill shows what it suggested (cases/verify.py, docs/proposals/30-escalation.md item 20). Everything in it is INVENTED.

The first classes call the step with a store in memory and a fake clock, as a Watch calls it after the daily cost was read; the later ones follow the request that was closed through the ladder,
the lessons, the cards, the letters and the pages, and the last runs whole Watches against the fake estate.
"""
import datetime as dt
import json
import re
import unittest
from dataclasses import replace
from types import SimpleNamespace

import cardsupport as cs
from support import NOW as WATCH_NOW, SUBSCRIPTION, FakeEstate, run_watch

from cases import brief, escalation, events, learning, notify, offers, verify
from cases.approvals import ApprovalSettings, Approvals
from cases.families import digest as plan_digest
from cases.memory_store import MemoryStore, stamp
from cases.models import COST_AT_ASK, COST_SEEN, GROUP_FACT, DecisionRecord
from test_escalation import World as LadderWorld
from test_run_loop import OID, Moving, loop_for
from test_web_savings import tiles_of
from test_web_support import PEOPLE, SUB, TINO, Console, make_advice, make_advice_case, make_case

DAY = dt.timedelta(days=1)
TODAY = dt.datetime(2026, 11, 20, 9, 0, 0, tzinfo=dt.timezone.utc)
FLAT = (300.0, 300.0, 300.0, 300.0)  # what a month costs by each of the four whole weeks before the newest two days
FELL = (300.0, 300.0, 100.0, 100.0)  # the two newest weeks cost a third of it
SAID = "The cost of this has gone down since the request was made, as it suggested. Meternaut closed the request."


def bill(weeks=FLAT, newest=None):
    """The 30 closed days as the Watch keeps them, the oldest first: four whole weeks that each cost `weeks[n]` a month (the same every day), then the newest two days (a daily cost of the
    last week unless `newest` gives the two)."""
    days = [round(month / 30, 4) for month in weeks for _ in range(7)]
    return days + (list(newest) if newest is not None else [days[-1]] * 2)


def vm(name: str) -> str:
    return f"/subscriptions/{SUB}/resourceGroups/team-apps-rg/providers/Microsoft.Compute/virtualMachines/vm-{name}"


class Lines:
    def __init__(self):
        self.found = []

    def info(self, line):
        self.found.append(json.loads(line[len(events.EVENT_PREFIX):]))

    def of(self, kind):
        return [line for line in self.found if line["type"] == kind]


class World:
    """Open requests of advice with the daily cost that a Watch read for each, and the step that follows the read."""

    def __init__(self):
        self.now = TODAY
        self.store = MemoryStore(self.clock)
        self.approvals = Approvals(self.store, ApprovalSettings(change_scopes=()), self.clock)
        self.lines = Lines()
        self.services = SimpleNamespace(extras=SimpleNamespace(store=self.store, approvals=self.approvals), clock=self.clock, redact=str,
                                        history=events.History("run1", None, self.clock, str, logger=self.lines))

    def clock(self):
        return self.now

    def yesterday(self) -> str:
        return (self.now - DAY).date().isoformat()

    def ask(self, plan_id="p1", weeks=FLAT, saving=120.0, newest=None, sealed=False, **case_changes):
        """An open request of advice for a finding with a saving of its own, as it stands when this Watch has read its daily cost."""
        fields = dict(case_id=f"c-{plan_id}", plan_id=plan_id, resource_id=vm(plan_id), resource_name=f"vm-{plan_id}", saving_usd_month=saving, cost_usd_30d=sum(bill(weeks, newest)),
                      cost_series=bill(weeks, newest), cost_series_end=self.yesterday())
        fields.update(case_changes)
        case = make_advice_case(**fields)
        plan = make_advice(plan_id=plan_id, case_id=case.case_id, resource_id=case.resource_id, resource_name=case.resource_name, saving_usd_month=saving,
                           created_at=stamp(self.now - 20 * DAY), expires_at="")
        self.store.case_put(case)
        plan = plan_digest.sealed(plan) if sealed else plan
        self.store.plan_put(plan)
        return plan

    def read(self, weeks=FLAT, newest=None, days=1):
        """The next Watch's reading of the daily cost: the day moves on, and every open request holds these weeks."""
        self.now += days * DAY
        for plan in self.store.plans_open():
            case = self.store.case_get(plan.case_id)
            self.store.case_put(replace(case, cost_series=bill(weeks, newest), cost_series_end=self.yesterday()))

    def watch(self, there="there") -> list[str]:
        """The step of a Watch, with what it said. `there` is the word of the check of the resources for every open request."""
        said: list[str] = []
        verify.step(self.services, {plan.plan_id: there for plan in self.store.plans_open()}, said.append)
        return said

    def plan(self, plan_id="p1"):
        return self.store.plan_get(plan_id)

    def verified(self):
        """The request after a Watch that kept what it cost and a later one that read a fall."""
        self.watch()
        self.read(FELL)
        self.watch()
        return self.plan()


class TheWeeks(unittest.TestCase):
    def test_the_closed_days_are_cut_into_four_whole_weeks_that_end_two_days_before_the_newest_day_and_each_is_a_month_by_its_seven_days(self):
        days = [float(n + 1) for n in range(30)]
        found = verify.weeks(days)
        self.assertEqual(len(found), 4)
        for n, week in enumerate(found):
            self.assertAlmostEqual(week, 30 / 7 * sum(days[n * 7:n * 7 + 7]), places=6)
        self.assertAlmostEqual(found[-1], 30 / 7 * sum(range(22, 29)), places=6, msg="the newest week ends on the 28th day: the 29th and the 30th are left out")

    def test_the_two_newest_days_are_in_no_week(self):
        self.assertEqual(verify.weeks(bill(FLAT, newest=(9999.0, 9999.0))), verify.weeks(bill(FLAT)))
        self.assertEqual(verify.weeks(bill(FLAT, newest=(0.0, 0.0))), verify.weeks(bill(FLAT)))

    def test_the_cheapest_week_that_cost_anything_is_the_level_and_a_spike_or_a_week_of_nothing_is_not(self):
        self.assertEqual(verify.cheapest(bill((300.0, 900.0, 300.0, 300.0))), 300.0)
        self.assertAlmostEqual(verify.cheapest(bill((0.0, 310.0, 290.0, 300.0))), 290.0, places=2, msg="a week that cost nothing is no level")
        self.assertEqual(verify.cheapest(bill((0.0, 0.0, 0.0, 0.0))), 0.0)

    def test_both_of_the_two_newest_weeks_have_to_be_down_and_a_saving_counts_for_no_more_than_the_cost(self):
        self.assertAlmostEqual(verify.fall(bill((300.0, 300.0, 200.0, 190.0)), 300.0, 120.0), 200.0, places=2, msg="the dearer of the two")
        self.assertIsNone(verify.fall(bill((300.0, 300.0, 241.0, 100.0)), 300.0, 120.0), "the older week is not down enough")
        self.assertIsNone(verify.fall(bill((300.0, 300.0, 100.0, 241.0)), 300.0, 120.0), "the newer week is not down enough")
        self.assertIsNotNone(verify.fall(bill((300.0, 300.0, 149.0, 149.0)), 300.0, 5000.0), "a saving of more than the cost asks for half of the cost")
        self.assertIsNone(verify.fall(bill((300.0, 300.0, 151.0, 151.0)), 300.0, 5000.0))


class WhatTheStepCloses(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.world.ask()  # it costs 300 a month, and the request states a saving of 120: it is verified when both weeks cost 240 or less

    def judged(self, weeks, world=None, **more):
        world = world or World()
        if world is not self.world and not world.store.plans_open():
            world.ask(**more)
        world.watch()
        world.read(weeks)
        world.watch()
        return world

    def test_a_cost_that_fell_by_more_than_half_of_the_saving_in_both_weeks_closes_the_request_as_verified_and_says_so_without_an_amount(self):
        self.world.watch()
        self.world.read((300.0, 300.0, 200.0, 200.0))
        self.assertEqual(self.world.watch(), [])
        plan = self.world.plan()
        self.assertEqual((plan.state, plan.preconditions["takenBack"], plan.preconditions[COST_AT_ASK], plan.preconditions[COST_SEEN], plan.expires_at),
                         ("expired", "verified", 300.0, 200.0, stamp(self.world.now)))
        self.assertEqual((self.world.store.case_get("c-p1").status, self.world.store.plans_open()), ("expired", []))
        (line,) = self.world.lines.of("case.verified")
        self.assertEqual(sorted(line), sorted(["v", "ts", "runId", "requestId", "type", "caseId", "detector", "resourceType", "resourceName", "reason"]))
        self.assertEqual((line["reason"], line["caseId"]), (verify.SAID, "c-p1"))
        self.assertFalse(re.search(r"\d{3}|\$", json.dumps({k: v for k, v in line.items() if k not in ("v", "ts", "runId", "requestId")})), "no amount of money")

    def test_a_cost_that_fell_by_less_stays_and_one_that_fell_by_half_of_the_saving_and_a_cent_closes_it(self):
        for weeks, state in (((300.0, 300.0, 241.0, 241.0), "open"), ((300.0, 300.0, 239.99, 239.99), "expired")):
            with self.subTest(weeks=weeks):
                self.assertEqual(self.judged(weeks, World()).plan().state, state)

    def test_a_fall_in_the_newest_week_only_or_in_the_older_week_only_is_no_fall(self):
        for weeks in ((300.0, 300.0, 300.0, 100.0), (300.0, 300.0, 100.0, 300.0), (300.0, 300.0, 100.0, 245.0)):
            with self.subTest(weeks=weeks):
                world = self.judged(weeks, World())
                self.assertEqual((world.plan().state, world.lines.of("case.verified")), ("open", []))

    def test_a_dip_of_one_day_is_no_fall(self):
        world = World()
        world.ask(saving=20.0)  # asks for a fall to 290 a month: a day of nothing is a fall to 257 in the week that has it
        world.watch()
        days = bill(FLAT)
        days[24] = 0.0
        world.now += DAY
        world.store.case_put(replace(world.store.case_get("c-p1"), cost_series=days, cost_series_end=world.yesterday()))
        world.watch()
        self.assertEqual(world.plan().state, "open", "the older week did not fall")
        days[17] = 0.0
        world.store.case_put(replace(world.store.case_get("c-p1"), cost_series=days))
        world.watch()
        self.assertEqual(world.plan().state, "expired", "a day of nothing in each of the two weeks is a fall in both")

    def test_the_two_newest_days_are_left_out_because_the_bill_is_late(self):
        self.assertEqual(self.judged(FELL, World(), ).plan().state, "expired")
        world = World()
        world.ask()
        world.watch()
        world.read(FELL, newest=(9999.0, 9999.0))
        world.watch()
        self.assertEqual(world.plan().state, "expired", "judged on the weeks before them, whatever the last two days show")
        world = World()
        world.ask()
        world.watch()
        world.read(FLAT, newest=(0.0, 0.0))
        world.watch()
        self.assertEqual(world.plan().state, "open", "a late bill that shows nothing for two days is no fall")

    def test_the_first_watch_keeps_what_the_finding_cost_and_judges_nothing_even_when_the_cost_is_down_already(self):
        world = World()
        world.ask(weeks=FELL)
        world.watch()
        self.assertEqual((world.plan().state, world.plan().preconditions[COST_AT_ASK]), ("open", 100.0))
        world.watch()
        self.assertEqual(world.plan().state, "open", "a cost that was down when the Watch first looked is no fall since")

    def test_what_it_kept_is_kept_once_and_the_request_is_judged_from_the_next_watch_on(self):
        self.world.watch()
        self.assertEqual((self.world.plan().state, self.world.plan().preconditions[COST_AT_ASK]), ("open", 300.0))
        self.world.read((300.0, 280.0, 270.0, 260.0))
        self.world.watch()
        self.assertEqual((self.world.plan().state, self.world.plan().preconditions[COST_AT_ASK]), ("open", 300.0), "not kept again at the lower cost")
        self.world.read(FELL)
        self.world.watch()
        self.assertEqual(self.world.plan().state, "expired")

    def test_a_request_is_kept_the_cost_and_judged_in_two_different_watches_whatever_the_first_reading_shows(self):
        for weeks in (FLAT, FELL):
            with self.subTest(weeks=weeks):
                world = World()
                world.ask(weeks=weeks)
                world.watch()
                self.assertEqual((world.plan().state, len(world.lines.of("case.verified"))), ("open", 0), "the Watch that keeps the cost judges nothing")
                self.assertIn(COST_AT_ASK, world.plan().preconditions)

    def test_a_spike_in_the_weeks_before_the_request_does_not_make_a_steady_cost_look_like_a_fall(self):
        world = World()
        world.ask(weeks=(300.0, 900.0, 300.0, 300.0))  # a week of a bill three times the size, which ages out
        world.watch()
        self.assertEqual(world.plan().preconditions[COST_AT_ASK], 300.0)
        world.read((900.0, 300.0, 300.0, 300.0), days=7)
        world.watch()
        world.read((300.0, 300.0, 300.0, 300.0), days=7)
        world.watch()
        self.assertEqual((world.plan().state, world.lines.of("case.verified")), ("open", []))

    def test_a_cost_that_fell_before_the_request_is_no_fall_since_it(self):
        world = World()
        world.ask(weeks=(300.0, 300.0, 100.0, 100.0))  # the cost went down two weeks before the Watch first looked
        world.watch()
        for _ in range(3):
            world.read((300.0, 100.0, 100.0, 100.0), days=7)
            world.watch()
        self.assertEqual(world.plan().state, "open")

    def test_a_saving_of_more_than_the_cost_asks_for_half_of_the_cost(self):
        world = World()
        world.ask(saving=500.0)
        world.watch()
        world.read((300.0, 300.0, 160.0, 160.0))
        world.watch()
        self.assertEqual(world.plan().state, "open")
        world.read((300.0, 300.0, 149.0, 149.0))
        world.watch()
        self.assertEqual(world.plan().state, "expired")

    def test_the_larger_saving_of_the_request_and_of_the_finding_counts_and_the_request_keeps_the_dearer_of_the_two_weeks(self):
        self.world.watch()
        self.world.store.case_put(replace(self.world.store.case_get("c-p1"), saving_usd_month=200.0))  # judged again, and worth more now
        self.world.read((300.0, 300.0, 210.0, 150.0))
        self.world.watch()
        self.assertEqual(self.world.plan().state, "open", "a saving of 200 asks for a fall to 200, and 240 would have done for the saving that the request states")
        self.world.read((300.0, 300.0, 199.0, 150.0))
        self.world.watch()
        self.assertEqual((self.world.plan().state, self.world.plan().preconditions[COST_SEEN]), ("expired", 199.0))

    def test_two_watches_in_a_row_close_a_request_once(self):
        plan = self.world.verified()
        self.assertEqual(plan.state, "expired")
        self.assertEqual((self.world.watch(), self.world.plan(), len(self.world.lines.of("case.verified"))), ([], plan, 1))
        self.world.read(FELL)
        self.world.watch()
        self.assertEqual((self.world.plan(), len(self.world.lines.of("case.verified"))), (plan, 1))

    def test_a_request_of_a_group_is_judged_by_the_sum_of_what_its_resources_cost(self):
        for weeks, state in (((900.0, 900.0, 650.0, 650.0), "expired"), ((900.0, 900.0, 750.0, 750.0), "open")):
            with self.subTest(weeks=weeks):
                world = World()
                world.ask("g1", weeks=(900.0, 900.0, 900.0, 900.0), saving=400.0, facts={GROUP_FACT: {"count": 3, "resourceIds": [vm("a"), vm("b"), vm("c")]}})
                self.assertEqual(self.judged(weeks, world).plan("g1").state, state)

    def test_a_group_whose_daily_cost_was_never_read_is_never_verified_and_keeps_no_cost(self):
        world = World()
        world.ask("g1", facts={GROUP_FACT: {"count": 900, "resourceIds": [vm("a")]}}, cost_series=None, cost_series_end=None)
        for _ in range(3):
            self.assertEqual(world.watch(), [])
            world.now += DAY
        self.assertEqual((world.plan("g1").state, COST_AT_ASK in world.plan("g1").preconditions), ("open", False))


class WhatTheStepDoesNotClose(unittest.TestCase):
    def test_a_finding_with_no_saving_of_its_own_a_recommendation_of_advisor_and_a_whole_scope_are_never_verified_and_nothing_is_said(self):
        world = World()
        world.ask("none", saving=None)
        world.ask("zero", saving=0.0)
        world.ask("advisor", detector="advisor-cost")
        world.ask("scope", resource_id=f"/subscriptions/{SUB}/resourceGroups/team-apps-rg")
        self.assertEqual(world.watch(), [])
        world.read(FELL)
        self.assertEqual(world.watch(), [])
        self.assertEqual(([plan.state for plan in world.store.plans_open()], [COST_AT_ASK in plan.preconditions for plan in world.store.plans_open()], world.lines.found),
                         (["open"] * 4, [False] * 4, []))

    def test_a_request_to_change_something_in_azure_is_never_verified(self):
        world = World()
        plan = world.ask()
        world.store.plan_put(replace(plan, family="delete-disk"))
        world.watch()
        world.read(FELL)
        world.watch()
        self.assertEqual((world.plan().state, COST_AT_ASK in world.plan().preconditions), ("open", False))

    def test_a_daily_cost_that_was_not_read_in_full_up_to_yesterday_verifies_nothing_and_each_reason_is_said_once_with_its_count(self):
        world = World()
        for name in ("a", "b", "c"):
            world.ask(name)
        world.watch()
        world.read(FELL)
        for name in ("a", "b"):  # a read that failed leaves the series that ended the day before
            world.store.case_put(replace(world.store.case_get(f"c-{name}"), cost_series_end=(world.now - 2 * DAY).date().isoformat()))
        world.store.case_put(replace(world.store.case_get("c-c"), cost_state="currency"))
        self.assertEqual(sorted(world.watch()), ["1 request: whether the cost has gone down was not checked (the cost lines are not in US dollars)",
                                                  "2 requests: whether the cost has gone down was not checked (the daily cost was not read in full up to yesterday)"])
        self.assertEqual([plan.state for plan in world.store.plans_open()], ["open"] * 3)

    def test_a_series_that_is_not_whole_is_never_used_and_says_nothing(self):
        for label, change in (("none", {"cost_series": None}), ("a day short", {"cost_series": bill(FELL)[1:]}), ("a day is no number", {"cost_series": [*bill(FELL)[:-1], None]}),
                              ("a negative day", {"cost_series": [*bill(FELL)[:-1], -1.0]})):
            with self.subTest(label):
                world = World()
                world.ask()
                world.watch()
                world.read(FELL)
                world.store.case_put(replace(world.store.case_get("c-p1"), **change))
                self.assertEqual((world.watch(), world.plan().state), ([], "open"))

    def test_a_resource_whose_existence_was_not_checked_or_is_gone_is_not_verified_by_this_step(self):
        for word in ("partial", "read", "invisible", "type", "members", "gone", ""):
            with self.subTest(word):
                world = World()
                world.ask()
                world.watch()
                world.read(FELL)
                self.assertEqual((world.watch(there=word), world.plan().state), ([], "open"))

    def test_a_resource_that_is_gone_is_taken_back_as_gone_and_the_bill_does_not_change_that(self):
        world = World()
        world.ask()
        world.watch()
        world.read(FELL)
        world.approvals.take_back_gone(["p1"])
        self.assertEqual(world.watch(there="gone"), [])
        plan = world.plan()
        self.assertEqual((plan.state, plan.preconditions["takenBack"], world.lines.found), ("expired", "gone", []))

    def test_a_request_that_a_person_answered_in_any_way_is_theirs_and_stays(self):
        for answer in ("ask", "later", "not_mine"):
            with self.subTest(answer):
                world = World()
                world.ask()
                world.watch()
                world.store.decision_put(DecisionRecord("p1", TINO, "Tino", answer, stamp(world.now), "B4N8X2KM"))
                world.read(FELL)
                world.watch()
                self.assertEqual((world.plan().state, world.lines.found), ("open", []))

    def test_an_answer_that_comes_in_after_the_step_looked_is_not_taken_back_and_nor_is_a_request_that_is_not_open(self):
        world = World()
        world.ask()
        world.watch()
        world.store.decision_put(DecisionRecord("p1", TINO, "Tino", "later", stamp(world.now), "B4N8X2KM"))
        self.assertEqual(world.approvals.take_back_verified({"p1": 100.0}), [])
        self.assertEqual(world.plan().state, "open")
        other = world.ask("p2")
        world.store.plan_put(replace(other, state="declined"))
        self.assertEqual((world.approvals.take_back_verified({"p2": 100.0, "nobody": 1.0}), world.plan("p2").state), ([], "declined"))

    def test_a_request_that_is_sealed_keeps_its_digest_and_its_code_when_the_cost_is_kept(self):
        world = World()
        before = world.ask(sealed=True)
        world.watch()
        after = world.plan()
        self.assertEqual((after.code, plan_digest.problem(after, after.digest), after.preconditions[COST_AT_ASK]), (before.code, "", 300.0))
        self.assertNotEqual(after.digest, before.digest, "the cost is part of what the digest holds")
        world.watch()
        self.assertEqual(world.plan(), after, "kept once: a second Watch writes nothing")

    def test_the_step_never_stops_the_run_and_says_what_it_could_not_do(self):
        world = World()
        world.ask()

        def refuse():
            raise RuntimeError("the store is down")
        world.store.plans_open = refuse
        said: list[str] = []
        verify.step(world.services, {}, said.append)
        self.assertEqual(said, ["whether the cost of the open requests has gone down could not be checked (RuntimeError: the store is down)"])
        world.services.extras = None
        verify.step(world.services, {}, said.append)
        self.assertEqual(len(said), 1, "a Watch without the loop has nothing to close")

    def test_the_history_knows_the_line(self):
        self.assertIn("case.verified", events.LOOP_KINDS)
        line = events.History("run1", None, lambda: TODAY, str, logger=Lines()).emit("case.verified", caseId="c1", reason=verify.SAID)
        self.assertEqual(line["type"], "case.verified")


class TheRequestThatWasClosed(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.world.ask()
        self.plan = self.world.verified()

    def test_it_is_not_opened_again_by_the_revival_whatever_its_hours_are(self):
        made = self.world.now - dt.timedelta(hours=72)
        self.world.store.plan_put(replace(self.plan, created_at=stamp(made), expires_at=stamp(self.world.now)))  # a whole number of hours after it was made, as the old clock closed it
        self.assertEqual((escalation.clock_closed(self.world.plan()), escalation.revive(self.world.store, self.world.now + 40 * DAY)), (False, []))
        self.assertEqual((self.world.plan().state, self.world.store.case_get("c-p1").status), ("expired", "expired"))

    def test_the_same_plan_without_its_reason_would_be_taken_for_the_work_of_the_clock(self):
        bare = replace(self.plan, created_at=stamp(self.world.now - dt.timedelta(hours=72)), expires_at=stamp(self.world.now), preconditions={"family": "advise"})
        self.assertTrue(escalation.clock_closed(bare), "what keeps the request above closed is the word of its reason")

    def test_the_ladder_makes_no_step_for_it_and_tells_nobody(self):
        ladder = LadderWorld(managers=False)  # one request of advice, made at START
        services = SimpleNamespace(extras=SimpleNamespace(store=ladder.store, approvals=Approvals(ladder.store, ApprovalSettings(change_scopes=()), ladder.clock)), clock=ladder.clock,
                                   redact=str, history=events.History("run1", None, ladder.clock, str, logger=Lines()))
        ladder.store.case_put(replace(ladder.store.case_get("c1"), saving_usd_month=120.0, detector="investigation"))

        def read(weeks):
            ladder.clock.advance(days=1)
            case = ladder.store.case_get("c1")
            ladder.store.case_put(replace(case, cost_series=bill(weeks), cost_series_end=(ladder.clock.now - DAY).date().isoformat()))
            verify.step(services, {"p1": "there"}, lambda text: None)
        read(FLAT)
        ladder.clock.advance(days=3)
        ladder.mail.status = 500  # the step of the third day cannot be delivered
        ladder.tick()
        steps = len(ladder.steps("p1"))
        self.assertEqual((steps, ladder.store.plan_get("p1").state), (1, "open"))
        sent = len(ladder.mail.calls)
        ladder.mail.status = 202
        read(FELL)
        self.assertEqual(ladder.store.plan_get("p1").state, "expired")
        for _ in range(60):
            ladder.clock.advance(days=1)
            ladder.tick()
        self.assertEqual((len(ladder.steps("p1")), len(ladder.mail.calls)), (steps, sent), "no step, no second try of the step that failed, and no weekly letter that lists it")

    def test_no_card_is_made_for_it_and_a_card_that_was_posted_is_closed_in_words_without_an_amount(self):
        fresh = cs.World()
        fresh.store.plan_put(replace(cs.advice_plan(expires_at=""), state="expired", preconditions={"takenBack": "verified"}))
        fresh.channel(cs.MAYA)
        fresh.introduce(cs.MAYA)
        self.assertEqual((fresh.run(), fresh.queue_fake.messages()), (0, []))
        world = cs.World()
        plan = world.open_plan(cs.advice_plan(expires_at=""))
        world.channel(cs.MAYA)
        world.introduce(cs.MAYA)
        offers.record_posted(json.dumps({"v": 1, "request": cs.PLAN_ID, "to": "maya@example.com", "message": "1731331200001", "conversation": "19:abc@unq.gbl.spaces"}),
                             world.store, world.people, world.clock)
        world.store.plan_put(replace(plan, state="expired", expires_at=stamp(world.clock()), preconditions={**plan.preconditions, "takenBack": "verified", COST_AT_ASK: 300.0, COST_SEEN: 120.0}))
        world.run()
        (message,) = world.queue_fake.messages()
        said = " ".join(cs.texts(message["card"]))
        self.assertEqual(message["op"], "update")
        self.assertIn("Closed: the cost has gone down. " + SAID + " Nothing was changed by Meternaut.", said)
        self.assertNotRegex(said, r"\$|\d{3}")

    def test_no_letter_lists_it(self):
        person = PEOPLE.by_oid(TINO)
        self.assertIsNone(notify.digest_for(person, self.world.store, PEOPLE, "https://m.example", self.world.now), "nothing waits for the person: the request is closed")

    def test_the_lesson_is_written_once_as_a_request_that_was_acted_on_and_nobody_answered(self):
        written = learning.sync(self.world.store, self.world.now)
        (lesson,) = self.world.store.lessons_recent(10)
        self.assertEqual((written, lesson.lesson_id, lesson.family, lesson.result, lesson.answer, lesson.measured_usd_month), (1, "p1", "advise", "verified", "expired", None))
        self.assertEqual((learning.sync(self.world.store, self.world.now + DAY), self.world.store.lessons_recent(10)), (0, [lesson]), "once")
        past = learning.past_of([lesson], lesson.resource_type, "advise")
        self.assertEqual((past.answered, past.approved, past.unanswered), (0, 0, 1), "nobody answered it: it adds to no answer and to no approval")
        self.assertEqual(brief.past_line(learning.digest_of(past)), "Past cases like this: no history yet.")

    def test_a_request_that_was_taken_back_for_another_reason_still_writes_no_lesson(self):
        world = World()
        world.ask()
        world.approvals.take_back_gone(["p1"])
        self.assertEqual((learning.sync(world.store, world.now), world.store.lessons_recent(10)), (0, []))


class ThePagesSayIt(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.world.ask()
        self.world.verified()
        self.console = Console(store=self.world.store)
        self.console.now = self.world.now

    def row(self, start):
        return next(row for row in self.console.get("/ops/savings").table("savings").rows if row["What became of it"].startswith(start))

    def test_the_page_of_the_request_says_it_in_plain_words_with_its_own_figures_and_asks_for_nothing(self):
        reply = self.console.get("/ok/p1")
        self.assertEqual((reply.status, reply.problems), (200, []))
        text = reply.main.text()
        self.assertIn("Closed: the cost has gone down", text)
        self.assertIn(SAID + " Nothing was changed by Meternaut.", text)
        self.assertIn("Before the request, its cheapest week cost $300.00 a month. In each of the last two weeks of the bill it cost at most $100.00 a month", text)
        self.assertIn("(the newest two days are left out, because the bill is late). The request stated a saving of $120.00 a month.", text)
        self.assertNotIn("Nothing was changed in Azure.", text, "somebody changed it: Meternaut did not")
        self.assertNotIn("A timer closed", text)
        self.assertEqual(reply.forms(), [], "there is nothing to answer")
        self.assertEqual(self.console.get("/why/c-p1").status, 200)

    def test_what_a_person_wrote_is_escaped_on_the_page_and_in_the_lists(self):
        evil = "<script>alert(1)</script>"
        self.world.store.case_put(replace(self.world.store.case_get("c-p1"), resource_name=evil))
        self.world.store.plan_put(replace(self.world.plan(), resource_name=evil, title=f"Consider changing {evil}"))
        for path in ("/ok/p1", "/", "/history"):
            with self.subTest(path):
                reply = self.console.get(path)
                self.assertNotIn(evil, reply.text)
                self.assertIn("&lt;script&gt;", reply.text)

    def test_the_start_page_and_the_history_list_it_and_the_history_links_it_and_does_not_fold_it_into_the_requests_that_were_taken_back(self):
        start, history = self.console.get("/"), self.console.get("/history")
        self.assertIn("Closed: the cost has gone down", start.content)
        self.assertIn(SAID, history.content)
        self.assertIn("/ok/p1", " ".join(history.links()))
        self.assertNotIn("request to look at a finding", history.content, "it is not one of the requests that Meternaut took back for no reason of its own")

    def test_the_history_still_counts_the_other_requests_that_were_taken_back_in_one_line_for_a_day(self):
        self.world.ask("q1")
        self.world.approvals.take_back_gone(["q1"])
        content = self.console.get("/history").content
        self.assertIn("1 request to look at a finding", content)
        self.assertIn(SAID, content)

    def test_the_page_of_savings_has_a_row_of_its_own_with_a_word_for_each_figure_and_adds_nothing_up(self):
        reply = self.console.get("/ops/savings")
        saved, taken = self.row("Saved (seen on the bill)"), self.row("Taken back")
        self.assertEqual((saved["Findings"], saved["Saving a year"], saved["Findings with no saving figure"]),
                         ("1", "The figures are on the page of each finding. None is added up here.", "Not added up."))
        self.assertIn("Meternaut changed nothing, and a cost can also go down for another reason.", saved["What became of it"])
        self.assertEqual(taken["Findings"], "0", "a finding is in one row only")
        self.assertEqual({name: tile[0] for name, tile in tiles_of(reply).items() if name != "Saving measured"}, {"Found in all": "—", "Waiting for a person": "—"}, "nothing was added up")

    def test_an_advisor_item_about_the_same_resource_is_not_counted_beside_it_and_one_about_another_resource_is(self):
        self.world.store.case_put(make_case(case_id="c-adv", resource_id=vm("p1"), resource_name="vm-p1", detector="advisor-cost", status="needs_human", saving_usd_month=50.0, cost_usd_30d=50.0))
        tiles = tiles_of(self.console.get("/ops/savings"))
        self.assertEqual((tiles["Found in all"][0], tiles["Waiting for a person"][0]), ("—", "—"), "the figure of Advisor is not added to a saving that the bill showed")
        self.world.store.case_put(make_case(case_id="c-adv2", resource_id=vm("other"), resource_name="vm-other", detector="advisor-cost", status="needs_human", saving_usd_month=50.0, cost_usd_30d=50.0))
        self.assertNotEqual(tiles_of(self.console.get("/ops/savings"))["Found in all"][0], "—")

    def test_a_finding_that_waits_again_is_not_in_the_row_that_the_bill_showed(self):
        self.world.store.case_put(replace(self.world.store.case_get("c-p1"), status="needs_human"))
        self.assertFalse(any(row["What became of it"].startswith("Saved (seen") for row in self.console.get("/ops/savings").table("savings").rows))

    def test_the_words_of_the_closing_are_the_ones_that_the_brief_has_and_no_figure_is_made_up_when_the_plan_kept_none(self):
        shown = brief.build_brief(self.world.store.case_get("c-p1"), self.world.plan(), None, (), now=self.world.now).outcome
        self.assertEqual((shown.state, shown.title, shown.lines[:2]), ("expired", "Closed: the cost has gone down", (SAID, "Nothing was changed by Meternaut.")))
        self.assertEqual((brief.TAKEN_BACK["verified"], brief.taken_back(self.world.plan())), (SAID, "verified"))
        bare = replace(self.world.plan(), preconditions={"takenBack": "verified"})
        self.assertEqual(len(brief.build_brief(None, bare, None, (), now=self.world.now).outcome.lines), 2)


class InAWatch(unittest.TestCase):
    """Whole Watches against the fake estate: the real daily cost, the real check of the resource and the step after them."""
    GROUP = "team-apps-rg"

    class Estate(FakeEstate):
        """The fake estate, and the two queries by which a Watch asks Resource Graph whether a resource is still there (cases/escalation.py existence)."""

        def __init__(self, here=()):
            super().__init__()
            self.here = {i.lower() for i in here}

        def __call__(self, method, url, headers, data, timeout):
            body = json.loads(data.decode("utf-8")) if data else None
            if url.lower().split("?")[0].endswith("/providers/microsoft.resourcegraph/resources") and "// meternaut:existence" in body["query"]:
                if "existence-types" in body["query"]:
                    rows = [{"type": "microsoft.compute/virtualmachines", "count_": 1}]
                else:
                    rows = [{"id": i} for i in sorted({found.lower() for found in re.findall(r"id =~ '([^']+)'", body["query"])} & self.here)]
                return self._json({"count": len(rows), "data": rows})
            return super().__call__(method, url, headers, data, timeout)

    def setUp(self):
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store
        self.vm = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{self.GROUP}/providers/Microsoft.Compute/virtualMachines/vm-one"
        self.store.case_put(make_advice_case(resource_id=self.vm, resource_name="vm-one", subscription_id=SUBSCRIPTION, resource_group=self.GROUP, plan_id="plan0002", cost_series=None))
        self.store.plan_put(make_advice(resource_id=self.vm, resource_name="vm-one", subscription_id=SUBSCRIPTION, resource_group=self.GROUP, created_at=stamp(WATCH_NOW), expires_at="",
                                        approvers=(OID,)))

    def estate(self, down=0, here=True):
        """An estate whose machine cost 10 a day, and 4 a day on the newest `down` of the 30 closed days that end the day before the clock."""
        known = [f"/subscriptions/{SUBSCRIPTION}", f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{self.GROUP}", self.vm] if here else [f"/subscriptions/{SUBSCRIPTION}"]
        estate = self.Estate(known)
        last = (self.clock.now - DAY).date()
        estate.days = [(last - dt.timedelta(days=n), self.vm, 4.0 if n < down else 10.0) for n in range(30)]
        return estate

    def watch(self, estate):
        return run_watch(estate, clock=self.clock, extras=self.extras)

    def plan(self):
        return self.store.plan_get("plan0002")

    def test_the_first_watch_keeps_what_it_cost_the_next_ones_change_nothing_and_a_fall_of_two_weeks_closes_the_request_once(self):
        self.watch(self.estate())
        self.assertEqual((self.plan().state, self.plan().preconditions[COST_AT_ASK]), ("open", 300.0))
        self.clock.advance(days=1)
        self.watch(self.estate())
        self.assertEqual((self.plan().state, self.plan().preconditions[COST_AT_ASK]), ("open", 300.0))
        self.clock.advance(days=7)
        self.watch(self.estate(down=6))  # the cost fell six days ago: only the newer week is down
        self.assertEqual(self.plan().state, "open")
        self.clock.advance(days=9)
        _, found, _ = self.watch(self.estate(down=16))
        self.assertEqual((self.plan().state, self.plan().preconditions["takenBack"], self.plan().preconditions[COST_SEEN]), ("expired", "verified", 120.0))
        self.assertEqual([e["reason"] for e in found if e["type"] == "case.verified"], [verify.SAID])
        _, found, _ = self.watch(self.estate(down=16))
        self.assertEqual([e for e in found if e["type"] == "case.verified"], [], "once")

    def test_a_request_that_the_watch_first_looks_at_when_the_cost_is_down_already_is_not_closed_by_it(self):
        self.watch(self.estate(down=21))
        self.assertEqual((self.plan().state, self.plan().preconditions[COST_AT_ASK]), ("open", 120.0))
        self.clock.advance(days=1)
        self.watch(self.estate(down=22))
        self.assertEqual(self.plan().state, "open")

    def test_a_resource_that_is_gone_is_taken_back_as_gone_even_when_the_bill_shows_a_fall(self):
        self.watch(self.estate())
        self.clock.advance(days=20)
        self.watch(self.estate(down=25, here=False))
        self.assertEqual((self.plan().state, self.plan().preconditions["takenBack"]), ("expired", "gone"))

    def test_a_watch_that_did_not_read_the_subscription_in_full_verifies_nothing_and_says_why_it_did_not_look(self):
        self.watch(self.estate())
        self.clock.advance(days=20)
        estate = self.estate(down=25)
        estate.failures["graph:managed-groups"] = 500
        _, found, _ = self.watch(estate)
        self.assertEqual((self.plan().state, [e for e in found if e["type"] == "case.verified"]), ("open", []))
        self.assertTrue(any("whether the resource is still there was not checked (the subscription was not read in full)" in e.get("note", "") for e in found if e["type"] == "run.note"))

    def test_a_daily_cost_that_could_not_be_read_verifies_nothing_and_says_so_once(self):
        self.watch(self.estate())
        self.clock.advance(days=20)
        estate = self.estate(down=25)
        estate.failures["daily"] = 500
        _, found, _ = self.watch(estate)
        notes = [e["note"] for e in found if e["type"] == "run.note" and "whether the cost has gone down" in e["note"]]
        self.assertEqual((self.plan().state, notes), ("open", ["1 request: whether the cost has gone down was not checked (the daily cost was not read in full up to yesterday)"]))


if __name__ == "__main__":
    unittest.main()
