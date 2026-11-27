"""Nobody is asked about what Meternaut is made of (docs/proposals/29-held-findings.md, 2026-11-27).

The group that Meternaut is deployed in holds two things: the waste that it planted to prove its loop on, and what it is made of (its AI account, its gateway, its app, its storage, its logs). The rules of
asking left everything in that group alone, so on 2026-11-27 the owner was asked to check whether Meternaut's own AI account was still used. A resource in such a group that is not named as the planting names
its waste is a part of Meternaut itself: no request is made for it by any path, the one that is open is taken back, and no held request shows it either. Everything here is invented.
"""
import unittest

import support  # noqa: F401  (it puts the app on the path)
from test_web_support import GROUP, NOW, SUB, TINO, make_advice, make_advice_case

from cases import brief, guards, upkeep
from cases.approvals import HELD_BACK, OWN_PART, ApprovalSettings, Approvals, build_advice, is_own_part, own_part
from cases.detectors import Context, Lead
from cases.families.gates import ChangeScope
from cases.memory_store import MemoryStore
from cases.models import ADVISE, HELD, Principal

OWN = ApprovalSettings(change_scopes=(ChangeScope(SUB, GROUP),))
NONE = ApprovalSettings(change_scopes=())
BASE = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"
OTHER_SUB = "cccccccc-3333-4444-8555-666666666666"
BOB = Principal(TINO, "Tino", ("owner", "approver", "ops"))


def part(**more):
    """Meternaut's own AI account: in the group that the app is deployed in, and not named as the planting names its waste."""
    base = dict(case_id="k-own", resource_id=f"{BASE}/Microsoft.CognitiveServices/accounts/aif-agents-1", resource_name="aif-agents-1", resource_type="microsoft.cognitiveservices/accounts",
                resource_group=GROUP, status="needs_human", recommendation="investigate", plan_id=None)
    return make_advice_case(**{**base, **more})


def planted(**more):
    """A disk that Meternaut planted: named as its planting names it, in the same group."""
    base = dict(case_id="k-planted", resource_id=f"{BASE}/Microsoft.Compute/disks/planted-disk-1", resource_name="planted-disk-1", resource_type="microsoft.compute/disks",
                resource_group=GROUP, status="needs_human", recommendation="investigate", plan_id=None)
    return make_advice_case(**{**base, **more})


def lead_of(case, tags=None) -> Lead:
    return Lead(detector=case.detector, resource_id=case.resource_id, resource_type=case.resource_type, name=case.resource_name, resource_group=case.resource_group,
                subscription_id=case.subscription_id, location="swedencentral", tags=tags or {}, managed_by="", facts={})


class World(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(lambda: NOW)
        self.approvals = Approvals(self.store, OWN, lambda: NOW)


class WhatIsOwn(World):
    def test_a_resource_of_the_own_group_is_a_part_of_meternaut_unless_it_is_named_as_the_planting_names_its_waste(self):
        self.assertEqual((own_part(part(), OWN), self.approvals.held_why(part())), (True, "own"))
        self.assertEqual((own_part(planted(), OWN), self.approvals.held_why(planted())), (False, ""))
        for label, case in (("a planted name on a resource of another kind", part(resource_name="planted-disk-1")),
                            ("a planted kind that is not named as the planting names it", part(resource_name="disk-1", resource_type="microsoft.compute/disks"))):
            with self.subTest(case=label):
                self.assertTrue(own_part(case, OWN))

    def test_it_takes_the_subscription_and_the_group_together_and_never_the_name_alone(self):
        for label, case in (("another group", part(resource_group="team-apps-rg")), ("a group of the same name in another subscription", part(subscription_id=OTHER_SUB)),
                            ("a case with no group", part(resource_group=""))):
            with self.subTest(case=label):
                self.assertEqual((own_part(case, OWN), self.approvals.held_why(case)), (False, ""))
        self.assertEqual(own_part(part(resource_group=GROUP.upper()), OWN), True, "a group is compared without case, as everywhere")
        self.assertEqual(own_part(part(), NONE), False, "with no group of its own listed, nothing is its own")

    def test_a_lead_is_judged_as_a_case_is(self):
        for case in (part(), planted(), part(resource_group="team-apps-rg"), part(subscription_id=OTHER_SUB)):
            with self.subTest(resource=case.resource_name, group=case.resource_group, subscription=case.subscription_id[:8]):
                self.assertEqual(is_own_part(lead_of(case), OWN), own_part(case, OWN))
        self.assertEqual(is_own_part(lead_of(planted(), {"meternaut-planted": "demo"}), OWN), False, "the planted tag changes nothing about what is a part of Meternaut")

    def test_the_guard_names_it_and_adds_a_flag_only_when_it_is_on(self):
        safe = Context(locks=[], recent=set(), managed_groups=set(), costs={}, currency="USD")
        lead = lead_of(part())
        plain = guards.evaluate(lead, safe, [])
        self.assertEqual((plain.names, sorted(plain.flags)), ([], ["keepTag", "locked", "managedGroup", "tooNew", "unverified"]), "what the roles are shown of any other resource is what it was")
        found = guards.evaluate(lead, safe, [], own=True)
        self.assertEqual((found.names, found.flags["ownPart"]), (["own-part"], True))
        self.assertEqual(guards.evaluate(lead, safe, [], fixture=True, own=True).names, ["own-part"], "a fixture is never one, and if it were nothing lifts the guard")


class NobodyIsAsked(World):
    def test_no_path_makes_a_request_for_a_part_of_meternaut_whatever_finds_it_or_says_about_it(self):
        for detector in ("investigation", "advisor-cost", "orphan-managed-disk", "idle-vm", "unused-public-ip"):
            for recommendation in ("delete", "change", "investigate"):
                with self.subTest(detector=detector, recommendation=recommendation):
                    store = MemoryStore(lambda: NOW)
                    approvals = Approvals(store, OWN, lambda: NOW)
                    case = part(detector=detector, status="proposed" if recommendation != "investigate" else "needs_human", recommendation=recommendation)
                    store.case_put(case)
                    self.assertEqual(approvals.held_why(case), "own")
                    self.assertIsNone(approvals.advise(case, (TINO,)))
                    self.assertIsNone(approvals.plan_for(case, lead_of(case), (TINO,)))
                    self.assertEqual((store.plans_open(), store.plans_held()), ([], []))

    def test_the_waste_that_meternaut_planted_and_a_resource_elsewhere_are_asked_about_as_ever(self):
        for label, case in (("planted waste in the own group", planted()), ("a resource in another group", part(resource_group="team-apps-rg"))):
            with self.subTest(case=label):
                store = MemoryStore(lambda: NOW)
                plan = Approvals(store, OWN, lambda: NOW).advise(case, (TINO,))
                self.assertEqual((plan.family, plan.state), (ADVISE, "open"))

    def test_the_same_part_is_asked_about_when_the_app_knows_no_group_of_its_own(self):
        store = MemoryStore(lambda: NOW)
        plan = Approvals(store, NONE, lambda: NOW).advise(part(), (TINO,))
        self.assertEqual((plan.family, plan.state), (ADVISE, "open"), "the rule belongs to the group that the app is deployed in, and a test of the other rules is not changed by it")


class TheRequestThatIsOpen(World):
    def old_request(self, case=None):
        """A request that was made before the rule, when nothing held a part of Meternaut back: made by an app that knew no group of its own."""
        case = case or part()
        self.store.case_put(case)
        return case, Approvals(self.store, NONE, lambda: NOW).advise(case, (TINO,))

    def test_it_is_taken_back_with_its_reason_and_the_history_and_the_page_say_it_in_words(self):
        case, plan = self.old_request()
        self.assertEqual(plan.state, "open")
        ((closed, found),) = self.approvals.hold_back_empty()
        self.assertEqual((closed.plan_id, closed.state, found.case_id), (plan.plan_id, "expired", case.case_id))
        self.assertEqual((brief.taken_back(closed), closed.preconditions["takenBack"]), ("own", "own"))
        self.assertEqual(brief.taken_back_words(closed, "own"), "Meternaut took this request back, because the resource is one of Meternaut's own parts. Meternaut does not ask about itself.")
        self.assertEqual(self.store.plans_open(), [])

    def test_the_history_says_it_in_the_words_of_a_held_finding(self):
        self.assertEqual(HELD_BACK["own"], OWN_PART)
        self.assertEqual(OWN_PART, "held back: it is one of Meternaut's own parts")
        lines = []

        class History:
            def emit(self, kind, **fields):
                lines.append((kind, fields))

        self.assertEqual(upkeep.held(History(), part(), "own"), OWN_PART)
        self.assertEqual([(kind, fields["reason"]) for kind, fields in lines], [("case.held", OWN_PART)])

    def test_an_answer_of_a_person_is_never_taken_back_and_the_request_stays_theirs(self):
        case, plan = self.old_request()
        self.approvals.decide(BOB, plan.plan_id, "later", plan.code, self.store.nonce_new(BOB.oid, plan.plan_id), "", "")
        self.assertEqual(self.approvals.hold_back_empty(), [])
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "open")

    def test_the_request_of_planted_waste_in_the_same_group_stays(self):
        _, plan = self.old_request(planted())
        self.assertEqual(self.approvals.hold_back_empty(), [])
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "open")


class NoHeldRequestShowsIt(World):
    def test_a_part_of_meternaut_is_not_shown_even_as_a_finding_that_a_guard_holds_back(self):
        case = part()
        self.store.case_put(case)
        self.assertEqual(self.approvals.settle((TINO,)), [])
        self.assertEqual(self.store.plans_held(), [])
        other = planted(case_id="k-planted", status="needs_human")
        self.store.case_put(other)
        self.assertEqual(self.store.plans_held(), [], "nothing holds the planted waste back either, so nothing is shown for it")

    def test_one_that_was_made_for_it_before_is_closed(self):
        case = part()
        self.store.case_put(case)
        held = build_advice(case, (TINO,), NOW, NONE, held="waiting")
        self.store.plan_put(held)
        self.assertEqual(self.store.plan_get(held.plan_id).state, HELD)
        ((closed, _),) = self.approvals.settle((TINO,))
        self.assertEqual((closed.plan_id, closed.state, closed.preconditions["takenBack"]), (held.plan_id, "expired", "released"))
        self.assertEqual(self.store.plans_held(), [])


if __name__ == "__main__":
    unittest.main()
