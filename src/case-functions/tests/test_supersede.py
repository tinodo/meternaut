"""A request for a group of resources closes the older requests for single resources of that group (cases/approvals.py: supersede, which the Watch calls after the investigation), and an
advice that nobody answered is not a row of "Recently decided" (cases/web/home.py). Everything in these tests is invented.
"""
import datetime as dt
import unittest
from dataclasses import replace

from support import APP_ROOT  # noqa: F401

from cases.approvals import Approvals
from cases.brief import waiting_cost
from cases.memory_store import MemoryStore, stamp
from cases.models import ADVISE, GROUP_FACT, EscalationRecord, started
from test_advise import NAMED, SETTINGS, Clock
from test_run import estate_with, investigating, of_type
from test_run_loop import Moving, loop_for
from test_web_support import NOW, SUB, FailingStore, make_advice_case, make_decision

OID = "aaaaaaaa-1111-4222-8333-444444444444"


def short(n: int) -> str:
    return f"{n:012x}"


def single(n: int, **changes):
    """The case of one private endpoint, as the first version made one for each resource of a finding."""
    base = dict(case_id=f"k{short(n)}", resource_id=f"/subscriptions/{SUB}/resourceGroups/rg-{n % 3}/providers/microsoft.network/privateendpoints/pe-{n}", resource_name=f"pe-{n}",
                resource_type="microsoft.network/privateendpoints", resource_group=f"rg-{n % 3}", subscription_id=SUB, recommendation="investigate", saving_usd_month=None,
                cost_usd_30d=100.0, plan_id=None, updated_at=stamp(NOW), first_seen_at=stamp(NOW), facts={"basis": "other"})
    base.update(changes)
    return make_advice_case(**base)


def grouped(case, numbers):
    """The same case as the case of a group that stands for the resources of `numbers`."""
    return replace(case, facts={**case.facts, GROUP_FACT: {"count": len(numbers), "members": [short(n) for n in numbers], "capped": 0, "silenced": 0}})


def asked(store, clock, numbers, group=None, of=None):
    """The cases of `numbers`, each with the open request that the first version made, and then the case `group` of them made the case of the group of `of`."""
    approvals = Approvals(store, SETTINGS, clock)
    plans = {}
    for n in numbers:
        case = single(n)
        store.case_put(case)
        plans[n] = approvals.advise(case, NAMED)
        assert plans[n] is not None, n
    if group is not None:
        store.case_put(grouped(store.case_get(f"k{short(group)}"), of))
    return plans


class WhenTheRequestOfAGroupWaits(unittest.TestCase):
    """Six private endpoints, each with the open request that the first version made, and the case of the sixth is now the case of the group of all six."""

    def setUp(self):
        self.clock = Clock()
        self.store = MemoryStore(clock=self.clock)
        self.approvals = Approvals(self.store, SETTINGS, self.clock)
        self.plans = asked(self.store, self.clock, range(1, 7), group=6, of=range(1, 7))

    def state(self, n):
        return self.store.plan_get(self.plans[n].plan_id).state

    def test_the_older_requests_of_the_other_resources_are_closed_as_expired_and_the_request_of_the_group_stays(self):
        closed = self.approvals.supersede()
        self.assertEqual(sorted(plan.case_id for plan in closed), sorted(f"k{short(n)}" for n in range(1, 6)))
        self.assertEqual([self.state(n) for n in range(1, 7)], ["expired"] * 5 + ["open"])
        self.assertEqual([self.store.case_get(f"k{short(n)}").status for n in range(1, 7)], ["expired"] * 5 + ["needs_human"])
        self.assertEqual([plan.plan_id for plan in self.store.plans_open()], [self.plans[6].plan_id])
        self.assertEqual(self.approvals.supersede(), [], "a second time there is nothing left to close")

    def test_nothing_is_closed_when_the_request_of_the_group_is_not_open(self):
        for state in ("declined", "expired", "withdrawn"):
            with self.subTest(state=state):
                store = MemoryStore(clock=self.clock)
                plans = asked(store, self.clock, range(1, 7), group=6, of=range(1, 7))
                store.plan_put(replace(plans[6], state=state))
                self.assertEqual(Approvals(store, SETTINGS, self.clock).supersede(), [])
                self.assertEqual(len(store.plans_open()), 5, "the older requests wait as they did")

    def test_only_the_resources_that_the_group_stands_for_are_closed(self):
        store = MemoryStore(clock=self.clock)
        asked(store, self.clock, range(1, 8), group=6, of=[4, 5, 6])
        closed = Approvals(store, SETTINGS, self.clock).supersede()
        self.assertEqual(sorted(plan.case_id for plan in closed), [f"k{short(4)}", f"k{short(5)}"])
        self.assertEqual(len(store.plans_open()), 5, "1, 2, 3, 6 and 7 still wait")

    def test_a_plan_of_a_change_and_the_request_of_another_group_are_never_closed(self):
        self.store.plan_put(replace(self.plans[1], family="stop-vm"))
        self.store.case_put(grouped(self.store.case_get(f"k{short(3)}"), [3, 4]))
        closed = self.approvals.supersede()
        self.assertEqual(sorted(plan.case_id for plan in closed), [f"k{short(2)}", f"k{short(4)}", f"k{short(5)}"])
        self.assertEqual((self.state(1), self.state(3), self.state(6)), ("open", "open", "open"))

    def test_a_plan_that_a_person_answered_is_not_touched(self):
        self.store.plan_put(replace(self.plans[2], state="declined"))
        self.store.plan_put(replace(self.plans[3], state="consumed"))
        closed = self.approvals.supersede()
        self.assertEqual(sorted(plan.case_id for plan in closed), [f"k{short(1)}", f"k{short(4)}", f"k{short(5)}"])
        self.assertEqual((self.state(2), self.state(3)), ("declined", "consumed"))

    def test_a_plan_that_a_person_put_off_or_asked_about_stays_open_with_its_decision(self):
        for number, decision in ((1, "later"), (2, "ask")):
            self.store.decision_put(make_decision(plan_id=self.plans[number].plan_id, decision=decision))
        closed = self.approvals.supersede()
        self.assertEqual(sorted(plan.case_id for plan in closed), [f"k{short(3)}", f"k{short(4)}", f"k{short(5)}"])
        self.assertEqual((self.state(1), self.state(2)), ("open", "open"))

    def test_a_closed_plan_ends_when_it_was_closed_and_says_why_it_was_taken_back(self):
        self.clock.advance(hours=5)
        self.approvals.supersede()
        closed = self.store.plan_get(self.plans[1].plan_id)
        self.assertEqual((closed.state, closed.expires_at, closed.preconditions["takenBack"]), ("expired", stamp(self.clock()), "group"))
        self.assertEqual(self.store.plan_get(self.plans[6].plan_id).expires_at, self.plans[6].expires_at, "the request of the group is not touched")

    def test_a_member_list_that_is_not_a_list_of_text_closes_nothing_and_raises_nothing(self):
        for members in ("text", None, [1, 2, None], {"a": 1}):
            with self.subTest(members=members):
                case = self.store.case_get(f"k{short(6)}")
                self.store.case_put(replace(case, facts={**case.facts, GROUP_FACT: {"count": 6, "members": members}}))
                self.assertEqual(self.approvals.supersede(), [])
                self.assertEqual(len(self.store.plans_open()), 6)

    def test_a_store_that_cannot_be_read_closes_nothing_and_raises_nothing(self):
        for name in ("plans_open", "cases_recent", "plan_put"):
            with self.subTest(name=name):
                store = FailingStore(clock=self.clock)
                asked(store, self.clock, range(1, 7), group=6, of=range(1, 7))
                store.fail = {name}
                self.assertEqual(Approvals(store, SETTINGS, self.clock).supersede(), [])


class WhenARequestIsMadeAgain(unittest.TestCase):
    """The wait of a finding does not start again when a request stands for another one: the Watch makes requests again often, and a wait that restarted would never reach its first step."""

    def setUp(self):
        self.clock = Clock()
        self.store = MemoryStore(clock=self.clock)
        self.approvals = Approvals(self.store, SETTINGS, self.clock)

    def test_the_request_of_a_group_keeps_the_oldest_start_and_the_steps_that_were_made_for_the_requests_that_it_stands_for(self):
        plans = asked(self.store, self.clock, range(1, 7), group=6, of=range(1, 7))
        self.store.plan_put(replace(plans[1], created_at="2026-10-20T08:00:00Z"))
        self.store.escalation_claim(EscalationRecord(plans[1].plan_id, "step", 1, "2026-10-23T08:00:00Z", "same", (OID,), ("Ada",), (OID,), "email", "sent"))
        self.approvals.supersede()
        stands = self.store.plan_get(plans[6].plan_id)
        self.assertEqual((started(stands), stands.created_at), ("2026-10-20T08:00:00Z", plans[6].created_at))
        self.assertEqual([(r.kind, r.number, r.delivered) for r in self.store.escalations_of(stands.plan_id)], [("step", 1, (OID,))], "the reminder that was sent is not sent again")
        self.assertEqual(stands.digest, plans[6].digest, "the start is no part of what a person approves")

    def test_a_fresher_request_of_a_group_that_stands_for_an_older_one_keeps_the_start_of_the_older(self):
        older = single(6)
        self.store.case_put(older)
        before = self.approvals.advise(older, NAMED)
        self.store.case_put(grouped(older, range(1, 7)))
        self.clock.advance(days=2)
        newer = single(7)
        self.store.case_put(newer)
        after = self.approvals.advise(newer, NAMED)
        self.store.case_put(grouped(newer, range(2, 8)))
        self.approvals.supersede()
        self.assertEqual(self.store.plan_get(before.plan_id).state, "expired")
        stands = self.store.plan_get(after.plan_id)
        self.assertEqual((stands.state, started(stands), stands.created_at), ("open", before.created_at, after.created_at))

    def test_a_group_that_stands_for_singles_costs_the_sum_of_what_each_cost_for_its_own_days_and_not_its_whole_figure_for_the_oldest_days(self):
        plans = asked(self.store, self.clock, range(1, 4), group=3, of=range(1, 4))
        for n, days, saving in ((1, 10, 30.0), (2, 5, 60.0)):  # one waited 10 days at $30 a month, the other 5 days at $60, and the group is made now with all three
            self.store.plan_put(replace(plans[n], created_at=stamp(self.clock() - dt.timedelta(days=days)), saving_usd_month=saving))
        self.store.plan_put(replace(plans[3], saving_usd_month=120.0))
        self.approvals.supersede()
        stands = self.store.plan_get(plans[3].plan_id)
        self.assertEqual((stands.waited_usd, started(stands)), (20.0, stamp(self.clock() - dt.timedelta(days=10))), "$10 and $10: not $120 a month over 10 days, which is $40")
        self.assertEqual(stands.digest, plans[3].digest, "what was carried is no part of what a person approves")
        self.clock.advance(days=3)
        text = waiting_cost(120.0, "Expected", 13, stands.waited_usd, 3)
        self.assertIn("$32 so far, of which $20 is what the requests that this one replaced cost for the days that each of them waited", text)
        self.assertEqual(waiting_cost(120.0, "Expected", 13), "13 days at $120.00 a month is $52", "a request that replaced none reads as it always did")

    def test_a_request_that_stands_for_one_with_the_same_members_carries_what_it_cost_so_far(self):
        older = single(6)
        self.store.case_put(older)
        before = self.approvals.advise(older, NAMED)
        self.store.plan_put(replace(before, saving_usd_month=90.0, waited_usd=6.0))
        self.store.case_put(grouped(older, range(1, 7)))
        self.clock.advance(days=2)
        newer = single(7)
        self.store.case_put(newer)
        after = self.approvals.advise(newer, NAMED)
        self.store.case_put(grouped(newer, range(2, 8)))
        self.approvals.supersede()
        self.assertEqual(self.store.plan_get(after.plan_id).waited_usd, 12.0, "$6 that it carried and $90 a month for the 2 days that it stood")

    def test_a_request_that_asks_another_question_starts_when_it_is_made_and_the_closed_word_of_the_old_one_says_why(self):
        case = single(1)
        self.store.case_put(case)
        old = self.approvals.advise(case, NAMED)
        self.store.plan_put(replace(old, state="expired", preconditions={**old.preconditions, "takenBack": "rules"}))
        self.clock.advance(days=9)
        self.store.case_put(replace(case, plan_id=None))
        again = self.approvals.advise(self.store.case_get(case.case_id), NAMED)
        self.assertEqual((again.waiting_since, again.created_at), ("", stamp(self.clock())))
        self.assertEqual(self.store.plan_get(old.plan_id).preconditions["takenBack"], "rules")


class WhenTheWatchRuns(unittest.TestCase):
    def test_the_watch_closes_the_older_requests_after_the_investigation_and_says_so_once(self):
        clock = Moving()
        extras = loop_for(clock)
        asked(extras.store, clock, range(1, 5), group=4, of=range(1, 5))
        _, events, _, _, _ = investigating(estate_with(planted_disk=False, endpoints=0), clock=clock, extras=extras)
        notes = [e["note"] for e in of_type(events, "run.note")]
        self.assertIn("3 earlier requests about single resources were closed: the request for the group of resources that they belong to waits", notes)
        self.assertEqual(len([note for note in notes if "earlier request" in note]), 1)
        self.assertEqual([plan.case_id for plan in extras.store.plans_open() if plan.family == ADVISE and plan.case_id.startswith("k0000000")], [f"k{short(4)}"],
                         "the three older requests are closed and the request of the group waits (the investigation of this fake estate made two requests of its own, which are not these)")
        _, again, _, _, _ = investigating(estate_with(planted_disk=False, endpoints=0), clock=clock, extras=extras)
        self.assertFalse([e for e in of_type(again, "run.note") if "earlier request" in e["note"]], "nothing is left to close the next time")

    def test_a_note_is_not_made_when_nothing_was_closed(self):
        clock = Moving()
        _, events, _, _, _ = investigating(estate_with(planted_disk=False, endpoints=0), clock=clock, extras=loop_for(clock))
        self.assertFalse([e for e in of_type(events, "run.note") if "earlier request" in e["note"]])


if __name__ == "__main__":
    unittest.main()
