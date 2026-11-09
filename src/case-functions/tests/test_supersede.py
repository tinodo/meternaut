"""A request for a group of resources closes the older requests for single resources of that group (cases/approvals.py: supersede, which the Watch calls after the investigation), and an
advice that nobody answered is not a row of "Recently decided" (cases/web/home.py). Everything in these tests is invented.
"""
import unittest
from dataclasses import replace

from support import APP_ROOT  # noqa: F401

from cases.approvals import Approvals
from cases.memory_store import MemoryStore, stamp
from cases.models import ADVISE, GROUP_FACT
from test_advise import NAMED, SETTINGS, Clock
from test_run import estate_with, investigating, of_type
from test_run_loop import Moving, loop_for
from test_web_support import NOW, SUB, FailingStore, make_advice_case


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
