"""A change that needs two people: the rule that makes it so, the first person's confirmation, the second person's approval with their own sign-in, and every way that the same person tries
to be both.

The flow is the real one (real approvals, the real sign-in code and runner) over a store in memory, a fake token endpoint and a fake Resource Manager, as in test_delegated.py. Nothing runs
in Azure. A person's name is an invented one.
"""
import json
import unittest
from dataclasses import replace

import support  # noqa: F401  (puts the app on the path)
from cases import twopeople
from cases.approvals import Approvals
from cases.families import digest as plan_digest
from cases.memory_store import MemoryStore, stamp
from cases.models import ActionRecord, DecisionRecord, Principal, SwitchRecord, TwoPeopleRule
from cases.runner import execute
from test_delegated import ACCESS, APPROVAL, APPROVER, DISK, NOW, OID, OTHER, Flow, good_claims

SECOND = Principal(OTHER, "Other", ("approver",))
FIRST = APPROVER  # OID: "Tino", owner, approver and ops
RULE = TwoPeopleRule(families=("delete-disk",))


class TheRuleDecidesTheClass(Flow):
    """A plan has the class R3 only when the rule covers it when it is made, and the class is part of its digest."""

    APPROVERS = (OID, OTHER)

    def planned(self, rule: TwoPeopleRule | None, saving: float | None):
        store = MemoryStore(clock=self.clock)
        if rule is not None:
            store.rule_put(rule)
        case = replace(self.case, saving_usd_month=saving, cost_usd_30d=saving)
        store.case_put(case)
        return Approvals(store, APPROVAL, self.clock).create(case, self.item, self.APPROVERS)

    def test_a_change_needs_one_person_until_a_rule_is_saved(self):
        self.assertEqual(self.plan.approval_class, "R2")
        self.assertFalse(twopeople.needs(self.plan))
        self.assertEqual(self.planned(TwoPeopleRule(), 900.0).approval_class, "R2", "a rule that names nothing is off")

    def test_a_rule_that_names_the_kind_of_change_covers_it_and_a_rule_that_names_another_kind_does_not(self):
        self.assertEqual(self.planned(TwoPeopleRule(families=("delete-disk",)), None).approval_class, "R3")
        self.assertEqual(self.planned(TwoPeopleRule(families=("stop-vm", "resize-vm")), 900.0).approval_class, "R2")

    def test_a_rule_that_names_an_amount_covers_a_saving_of_that_amount_or_more_and_never_a_saving_that_is_not_known(self):
        rule = TwoPeopleRule(min_usd_month=100.0)
        self.assertEqual([self.planned(rule, saving).approval_class for saving in (99.99, 100.0, 100.01, 5000.0)], ["R2", "R3", "R3", "R3"])
        self.assertEqual(self.planned(rule, None).approval_class, "R2", "no saving is known, so no amount is reached: a kind of change is how to cover it")

    def test_either_part_of_the_rule_is_enough(self):
        self.assertEqual(self.planned(TwoPeopleRule(min_usd_month=1000.0, families=("delete-disk",)), 5.0).approval_class, "R3")
        self.assertEqual(self.planned(TwoPeopleRule(min_usd_month=1.0, families=("stop-vm",)), 5.0).approval_class, "R3")

    def test_the_class_is_in_the_digest_so_a_request_cannot_be_turned_into_one_for_one_person(self):
        two = self.planned(RULE, None)
        one = replace(two, approval_class="R2")
        self.assertNotEqual(plan_digest.digest_of(two), plan_digest.digest_of(one))
        self.assertIsNotNone(plan_digest.problem(one, one.digest), "the stored digest does not match the changed class, so nothing can be approved on it")

    def test_a_rule_that_is_saved_or_taken_away_later_changes_no_open_request(self):
        two = self.planned(RULE, None)
        store = MemoryStore(clock=self.clock)
        store.plan_put(two)
        store.rule_put(TwoPeopleRule())
        self.assertEqual(store.plan_get(two.plan_id).approval_class, "R3")
        self.assertTrue(twopeople.needs(store.plan_get(two.plan_id)))

    def test_a_plan_of_advice_never_needs_two_people(self):
        self.assertFalse(twopeople.needs(replace(self.plan, family="advise", approval_class="R3")))


class TwoFlow(Flow):
    APPROVERS = (OID, OTHER)
    RULE = RULE

    def confirm(self, who=FIRST, code=None, nonce=None, note=""):
        token = self.store.nonce_new(who.oid, self.plan.plan_id) if nonce is None else nonce
        result = self.approvals.decide(who, self.plan.plan_id, "confirm", self.plan.code if code is None else code, token, note)
        self.clock.advance(minutes=5)  # what comes after it is later, so that the decisions of a plan are listed in the order in which they were given
        return result

    def sign_in_as(self, who, **kwargs):
        """The form, the sign-in and the return of one person, who signs in to Azure with their own account. A refusal of the form is the result."""
        self.claims = good_claims(oid=who.oid)
        begun = self.begin(who=who, **kwargs)
        if begun.refusal is not None:
            return begun.refusal
        return self.back(self.state_of(begun), who=who)

    def kinds(self):
        return [(d.approver_oid, d.decision) for d in self.store.decisions_of_plan(self.plan.plan_id)]

    def nothing_was_approved(self):
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "open")
        self.assertIsNone(self.store.action_get(self.plan.plan_id))
        self.assertNotIn("approve", [kind for _, kind in self.kinds()])
        self.assertEqual((self.azure.calls, self.tokens_used, self.redeemed), ([], [], []), "no call to Azure and no sign-in redeemed")


class TheFirstPersonConfirms(TwoFlow):
    def test_a_confirmation_is_recorded_with_the_digest_of_the_plan_and_changes_nothing(self):
        result = self.confirm(note="read it")
        self.assertEqual((result.ok, result.kind), (True, "confirmed"))
        (record,) = self.store.decisions_of_plan(self.plan.plan_id)
        self.assertEqual((record.decision, record.approver_oid, record.plan_code, record.plan_digest, record.note), ("confirm", OID, self.plan.code, self.plan.digest, "read it"))
        self.assertEqual(self.store.plan_get(self.plan.plan_id), self.plan, "the request is as it was: open, not approved")
        self.assertEqual((self.store.case_get(self.plan.case_id).status, self.store.action_get(self.plan.plan_id)), ("awaiting_ok", None))
        self.assertEqual((self.azure.calls, self.tokens_used, self.redeemed, self.events), ([], [], [], []), "no sign-in to Azure and no call to it")

    def test_it_needs_the_role_a_name_on_the_request_an_open_request_the_code_the_switches_and_a_form_that_was_not_used(self):
        for label, who, expected in (("a person with no role approver", Principal(OID, "Tino", ("owner", "ops")), "refused_role"),
                                     ("a person who is not named", Principal("99999999-8888-7777-6666-555555555555", "Stranger", ("approver",)), "refused_role")):
            with self.subTest(label):
                self.assertEqual(self.confirm(who=who).kind, expected)
        self.assertEqual(self.confirm(code="00000000").kind, "refused_code")
        self.assertEqual(self.confirm(nonce="x" * 30).kind, "error", "a form token that was never made")
        for name in ("changes", "all"):
            self.store.switch_put(SwitchRecord(name=name, paused=True))
            self.assertEqual(self.confirm().kind, "refused_paused", f"the switch {name} holds a confirmation as it holds an approval")
            self.store.switch_put(SwitchRecord(name=name, paused=False))
        self.clock.advance(hours=73)
        self.assertEqual(self.confirm().kind, "expired")
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])

    def test_a_plan_that_is_not_the_one_that_its_digest_names_cannot_be_confirmed(self):
        self.store.plan_put(replace(self.plan, what_changes="Somebody changed this text."))  # the digest and the code are those of the old text
        result = self.confirm()
        self.assertEqual(result.kind, "refused_code")
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])

    def test_the_form_token_is_used_up_and_a_second_confirmation_of_the_same_person_is_a_duplicate(self):
        token = self.store.nonce_new(OID, self.plan.plan_id)
        self.assertTrue(self.confirm(nonce=token).ok)
        self.assertEqual(self.confirm(nonce=token).kind, "duplicate", "the person confirmed already: said before the token is used up")
        self.assertEqual(self.confirm().kind, "duplicate")
        self.assertEqual(self.kinds(), [(OID, "confirm")])

    def test_a_request_for_one_person_has_nothing_to_confirm(self):
        one = plan_digest.sealed(replace(self.plan, approval_class="R2"))
        self.store.plan_put(one)
        result = self.approvals.decide(FIRST, one.plan_id, "confirm", one.code, self.store.nonce_new(OID, one.plan_id))
        self.assertEqual((result.kind, self.store.decisions_of_plan(one.plan_id)), ("refused_state", []))

    def test_a_request_that_fewer_than_two_people_can_approve_cannot_be_confirmed_or_approved(self):
        alone = plan_digest.sealed(replace(self.plan, approvers=(OID,)))
        self.store.plan_put(alone)
        result = self.approvals.decide(FIRST, alone.plan_id, "confirm", alone.code, self.store.nonce_new(OID, alone.plan_id))
        self.assertEqual((result.kind, result.message), ("refused_state", twopeople.ALONE))
        self.plan = alone
        self.assertEqual(self.begin(who=FIRST).refusal.message, twopeople.ALONE)

    def test_a_person_who_confirmed_can_still_decline_and_that_ends_the_request(self):
        self.confirm()
        result = self.approvals.decide(FIRST, self.plan.plan_id, "decline", self.plan.code, self.store.nonce_new(OID, self.plan.plan_id), "changed my mind", "other")
        self.assertEqual((result.ok, result.kind), (True, "declined"))
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "declined")
        self.assertEqual(self.kinds(), [(OID, "decline")], "the confirmation is not there any more")
        self.assertEqual(self.begin(who=SECOND).refusal.kind, "refused_state", "and nobody can approve it")

    def test_a_question_or_a_later_would_take_the_place_of_the_confirmation_so_it_is_refused(self):
        self.confirm()
        for decision in ("ask", "later"):
            token = self.store.nonce_new(OID, self.plan.plan_id)
            self.assertEqual(self.approvals.decide(FIRST, self.plan.plan_id, decision, self.plan.code, token, "a word").kind, "duplicate")
        self.assertEqual(self.kinds(), [(OID, "confirm")])

    def test_a_second_person_does_not_confirm_a_request_that_was_confirmed(self):
        self.confirm()
        result = self.confirm(who=SECOND)
        self.assertEqual(result.kind, "refused_state")
        self.assertIn("Tino confirmed this request already", result.message)
        self.assertEqual(self.kinds(), [(OID, "confirm")])


class TheSecondPersonApproves(TwoFlow):
    def test_without_a_confirmation_nobody_can_approve_and_nothing_is_started(self):
        for who in (FIRST, SECOND):
            with self.subTest(who=who.name):
                refusal = self.sign_in_as(who)
                self.assertEqual((refusal.ok, refusal.kind, refusal.message), (False, "refused_state", twopeople.FIRST))
        self.nothing_was_approved()
        self.assertFalse([n for n in self.store.nonces.values() if n[1] == "arm-signin"], "no sign-in was started")

    def test_the_whole_way_after_a_confirmation_is_the_second_persons_own_approval_and_change(self):
        self.confirm()
        result = self.sign_in_as(SECOND, note="second look")
        self.assertEqual((result.ok, result.kind), (True, "ran"))
        self.assertEqual(self.kinds(), [(OID, "confirm"), (OTHER, "approve")])
        approval = next(d for d in self.store.decisions_of_plan(self.plan.plan_id) if d.decision == "approve")
        self.assertEqual((approval.approver_name, approval.plan_digest, approval.note), ("Other", self.plan.digest, "second look"))
        self.assertEqual(self.tokens_used, [ACCESS], "one sign-in, the second person's")
        self.assertTrue(self.azure.headers and all(h["Authorization"] == f"Bearer {ACCESS}" for h in self.azure.headers))
        self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 1)
        self.assertNotIn(DISK.lower(), self.azure.resources)
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, self.store.action_get(self.plan.plan_id).state), ("consumed", "done"))
        self.assertEqual([kind for kind, _ in self.events], ["signin.started", "approval.recorded", "action.started", "action.finished"])

    def test_the_first_person_cannot_be_the_second_in_any_way(self):
        self.confirm()
        for label, who in (("the same account", FIRST), ("the same account spelled in capitals", Principal(OID.upper(), "Tino", ("owner", "approver", "ops")))):
            with self.subTest(label):
                refusal = self.sign_in_as(who)
                self.assertEqual((refusal.ok, refusal.kind, refusal.message), (False, "refused_state", twopeople.MINE))
        self.assertEqual(self.kinds(), [(OID, "confirm")])
        self.assertIsNone(self.store.action_get(self.plan.plan_id))
        self.assertEqual((self.azure.calls, self.tokens_used, self.redeemed), ([], [], []))

    def test_a_person_who_tries_to_approve_first_and_then_confirm_is_the_first_and_so_not_the_second(self):
        self.assertEqual(self.sign_in_as(FIRST).message, twopeople.FIRST)
        self.assertTrue(self.confirm().ok)
        self.assertEqual(self.sign_in_as(FIRST).message, twopeople.MINE)
        self.nothing_was_approved()

    def test_a_person_who_confirmed_cannot_be_recorded_as_the_approver_by_any_other_path(self):
        self.confirm()
        recorded, action = self.approvals.record_approval(FIRST, self.plan, "")
        self.assertEqual((recorded.ok, recorded.kind, recorded.message, action), (False, "refused_state", twopeople.MINE, None))
        self.assertIsNone(self.store.action_get(self.plan.plan_id), "the claim on the action was let go, so the second person is not blocked")
        self.assertEqual(self.kinds(), [(OID, "confirm")])
        recorded, action = self.approvals.record_approval(SECOND, self.plan, "")
        self.assertEqual((recorded.ok, action is not None), (True, True))

    def test_the_form_check_alone_refuses_the_first_person_before_it_uses_up_the_form_token(self):
        self.confirm()
        token = self.store.nonce_new(OID, self.plan.plan_id)
        plan, refusal = self.approvals.check_form(FIRST, self.plan.plan_id, self.plan.code, token)
        self.assertEqual((plan, refusal.kind), (None, "refused_state"))
        self.assertTrue(self.store.nonce_use(token, OID, self.plan.plan_id), "the token is still good for the answers that the person may give")

    def test_a_confirmation_of_an_earlier_form_of_the_plan_does_not_count_and_the_words_say_so(self):
        self.confirm()
        changed = plan_digest.sealed(replace(self.plan, what_changes="A text that somebody changed after the confirmation."))
        self.store.plan_put(changed)
        self.plan = changed
        refusal = self.sign_in_as(SECOND)
        self.assertEqual((refusal.ok, refusal.kind), (False, "refused_state"))
        self.assertEqual(refusal.message, twopeople.STALE.format(name="Tino"))
        self.assertEqual(twopeople.standing(changed, self.store.decisions_of_plan(changed.plan_id), OTHER).stage, "stale")
        self.nothing_was_approved()

    def test_a_stale_confirmation_is_made_again_by_the_same_person_and_then_the_second_person_may_approve(self):
        self.confirm()
        changed = plan_digest.sealed(replace(self.plan, what_changes="A text that somebody changed after the confirmation."))
        self.store.plan_put(changed)
        self.plan = changed
        self.assertTrue(self.confirm().ok, "the confirmation of the plan as it is now takes the place of the old one")
        self.assertEqual(self.kinds(), [(OID, "confirm")])
        (record,) = self.store.decisions_of_plan(changed.plan_id)
        self.assertEqual(record.plan_digest, changed.digest)
        self.assertEqual(self.sign_in_as(SECOND).kind, "ran")

    def test_a_plan_that_changes_while_the_second_person_signs_in_is_not_approved_whatever_was_confirmed(self):
        self.confirm()
        self.claims = good_claims(oid=OTHER)
        begun = self.begin(who=SECOND)
        self.assertIsNone(begun.refusal)
        self.store.plan_put(plan_digest.sealed(replace(self.plan, what_changes="Changed while the person signed in.")))
        result = self.back(self.state_of(begun), who=SECOND)
        self.assertEqual((result.ok, result.kind), (False, "refused_code"))
        self.assertEqual([kind for _, kind in self.kinds()], ["confirm"])
        self.assertEqual((self.azure.calls, self.tokens_used), ([], []))

    def test_a_decline_by_the_first_person_while_the_second_signs_in_ends_the_request(self):
        self.confirm()
        self.claims = good_claims(oid=OTHER)
        begun = self.begin(who=SECOND)
        self.approvals.decide(FIRST, self.plan.plan_id, "decline", self.plan.code, self.store.nonce_new(OID, self.plan.plan_id))
        result = self.back(self.state_of(begun), who=SECOND)
        self.assertEqual((result.ok, result.kind), (False, "refused_state"))
        self.assertEqual((self.azure.calls, self.tokens_used), ([], []))
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "declined")

    def test_a_withdrawn_confirmation_while_the_second_signs_in_is_caught_at_the_return(self):
        self.confirm()
        self.claims = good_claims(oid=OTHER)
        begun = self.begin(who=SECOND)
        self.store.decision_put(DecisionRecord(self.plan.plan_id, OID, "Tino", "not_mine", stamp(NOW), self.plan.code))  # the confirmation is gone and the request is still open
        result = self.back(self.state_of(begun), who=SECOND)
        self.assertEqual((result.ok, result.message), (False, twopeople.FIRST))
        self.assertEqual((self.azure.calls, self.tokens_used, self.redeemed), ([], [], []))

    def test_a_decline_by_the_second_person_ends_the_request_too(self):
        self.confirm()
        result = self.approvals.decide(SECOND, self.plan.plan_id, "decline", self.plan.code, self.store.nonce_new(OTHER, self.plan.plan_id))
        self.assertEqual((result.ok, result.kind), (True, "declined"))
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "declined")
        self.assertEqual(self.sign_in_as(FIRST).kind, "refused_state")


class TheRunnerAsksAgain(TwoFlow):
    """The runner reads the decisions once more right before it writes, so a plan that was approved by another way is stopped."""

    def approved(self, *decisions: DecisionRecord):
        plan = replace(self.plan, state="approved")
        self.store.plan_put(plan)
        self.store.action_claim(ActionRecord(plan_id=plan.plan_id, case_id=plan.case_id, family=plan.family, resource_id=plan.resource_id, state="queued", queued_at=stamp(NOW),
                                             plan_digest=plan.digest))
        for decision in decisions:
            self.store.decision_put(decision)
        return execute(self.delegation.run(ACCESS), self.store.action_get(plan.plan_id), approved_digest=plan.digest)

    def decision(self, kind, oid, name):
        return DecisionRecord(self.plan.plan_id, oid, name, kind, stamp(NOW), self.plan.code, plan_digest=self.plan.digest)

    def test_an_approval_with_no_confirmation_is_stopped_before_any_call(self):
        done = self.approved(self.decision("approve", OTHER, "Other"))
        self.assertEqual(done.kind, "stopped")
        self.assertIn("needs two people", done.action.result)
        self.assertEqual(self.azure.calls, [])

    def test_a_confirmation_of_a_person_who_is_not_named_on_the_request_does_not_count(self):
        done = self.approved(self.decision("confirm", "99999999-8888-7777-6666-555555555555", "Stranger"), self.decision("approve", OTHER, "Other"))
        self.assertEqual(done.kind, "stopped")
        self.assertEqual(self.azure.calls, [])

    def test_a_confirmation_of_another_form_of_the_plan_is_stopped(self):
        stale = replace(self.decision("confirm", OID, "Tino"), plan_digest="f" * 64)
        done = self.approved(stale, self.decision("approve", OTHER, "Other"))
        self.assertEqual(done.kind, "stopped")
        self.assertEqual(self.azure.calls, [])

    def test_a_confirmation_of_one_person_and_the_approval_of_another_run_the_change(self):
        done = self.approved(self.decision("confirm", OID, "Tino"), self.decision("approve", OTHER, "Other"))
        self.assertEqual(done.kind, "ran")
        self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 1)


class TheWordsAreTheWordsOfThePages(unittest.TestCase):
    def test_every_stage_has_a_sentence_and_no_word_that_the_guide_forbids(self):
        import re
        from cases.brief import SECOND_WORDS, TWO_PEOPLE
        forbidden = re.compile(r"(?<![\w-])(?:family|families|plans?|cases?|leads?|gates?|digests?|re-check(?:s|ed)?|no figure|talk to a person)(?![\w-])", re.I)
        self.assertEqual(set(SECOND_WORDS), {"first", "second", "mine", "stale", "alone"})
        for text in (TWO_PEOPLE, *SECOND_WORDS.values(), twopeople.ALONE, twopeople.FIRST, twopeople.MINE, twopeople.STALE):
            self.assertEqual(forbidden.findall(text), [], text)
            self.assertNotRegex(text, r"(?i)urgent|immediately|hurry|deadline|expires in|only \d+ hours|you must")
        for text in (twopeople.ALONE, twopeople.FIRST, twopeople.MINE, twopeople.STALE.format(name="Tino")):
            self.assertTrue(text.endswith("Nothing is approved."), text)

    def test_the_kinds_that_the_rule_page_offers_are_every_family_with_the_phrase_of_its_own(self):
        from cases.brief import kinds
        from cases.families import registry
        self.assertEqual(kinds(), {family.name: family.summary for family in registry.REGISTRY})
        self.assertNotIn("advise", kinds(), "advice changes nothing, so no rule can name it")


if __name__ == "__main__":
    unittest.main()
