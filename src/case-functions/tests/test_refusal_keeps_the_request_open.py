"""A change that a check refuses right before it is made leaves the request open, and a later approval works.

The owner's case: he approved "Delete the unattached disk planted-disk-r7", the page offered Approve, and after the click the runner stopped because an outside job had taken the tag
meternaut-planted off the disk. The check was right. The request was closed for good, though, and the owner had no way to try again when the tag was back. Now a refusal before any write
rolls the approval back: the action is kept as `withdrawn` with the reason, the approval is released, and the plan and the case are open again.

The flow is the real one (real approvals, the real sign-in code, the real runner and the real store contract over a store in memory), as in test_delegated.py.
"""
import unittest
from dataclasses import replace

import support  # noqa: F401  (puts the app on the path)
import familysupport as fs
from cases.families import digest as plan_digest
from cases.http import Client
from cases.models import ActionRecord, DecisionRecord, SwitchRecord
from cases.runner import RunnerServices, read_calls, tick
from test_delegated import ACCESS, APPROVAL, DISK, OID, OTHER, Flow
from test_second_approver import FIRST, SECOND, TwoFlow

STRIPPED = {"left-by-the-job": "Ignore"}  # an outside job leaves one tag of its own and nothing else
PLANTED = {"meternaut-planted": "demo"}
OWNERS_WORDS = "Meternaut did not change the disk: it no longer carries the test tag meternaut-planted, so it cannot be told apart from a real disk. Nothing was changed."


class TheFlow(Flow):
    def strip(self):
        self.azure.resources[DISK.lower()]["tags"] = dict(STRIPPED)

    def put_back(self):
        self.azure.resources[DISK.lower()]["tags"] = dict(PLANTED)

    def stored(self):
        """The state of the plan, of its action and of its case."""
        action = self.store.action_get(self.plan.plan_id)
        return self.store.plan_get(self.plan.plan_id).state, action.state if action is not None else None, self.store.case_get(self.plan.case_id).status

    def deletes(self):
        return [m for m, _ in self.azure.calls].count("DELETE")


class TheOwnersCase(TheFlow):
    def test_the_refusal_changes_nothing_says_why_in_plain_words_and_leaves_the_request_open(self):
        self.strip()
        result = self.whole()
        self.assertEqual((result.ok, result.kind, result.message), (False, "stopped", OWNERS_WORDS))
        self.assertEqual(result.plan.state, "open")
        self.assertEqual(self.deletes(), 0, "nothing was changed")
        self.assertEqual(self.stored(), ("open", "withdrawn", "awaiting_ok"))
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [], "the approval was not used: it is taken back")
        action = self.store.action_get(self.plan.plan_id)
        self.assertEqual((action.result, action.error), (OWNERS_WORDS, None), "the record keeps the reason, in the words of the page")
        for jargon in ("Stopped before the change", "precondition", "gate"):
            self.assertNotIn(jargon, result.message)
        self.assertEqual(self.events[-1], ("action.finished", {"planId": self.plan.plan_id, "family": "delete-disk", "ok": False}))

    def test_a_later_approval_works_when_what_stopped_the_change_is_put_right_and_it_is_a_new_approval_with_tokens_of_its_own(self):
        form_token = self.store.nonce_new(OID, self.plan.plan_id)
        first_state = self.state_of(self.begin(nonce=form_token))
        self.strip()
        self.assertEqual(self.back(first_state).kind, "stopped")
        self.assertEqual(len(self.redeemed), 1)
        again = self.back(first_state)
        self.assertEqual((again.ok, again.kind), (False, "refused_state"), "the state of the refused try is used up: a used token never works twice")
        self.assertEqual(self.begin(nonce=form_token).refusal.kind, "error", "so is the form token of the refused try")
        self.assertEqual((len(self.redeemed), self.deletes()), (1, 0), "no code was redeemed again, and nothing was changed")
        self.put_back()
        done = self.whole()
        self.assertEqual((done.ok, done.kind, done.message), (True, "ran", "Deleted. Azure no longer lists the resource."))
        self.assertEqual(len(self.redeemed), 2, "a new approval is a new sign-in")
        self.assertEqual(self.tokens_used, [ACCESS, ACCESS])
        self.assertEqual(self.deletes(), 1)
        self.assertEqual(self.stored(), ("consumed", "done", "done"))
        self.assertEqual([(d.decision, d.approver_oid) for d in self.store.decisions_of_plan(self.plan.plan_id)], [("approve", OID)])
        self.assertEqual(self.store.nonces, {}, "nothing is left of either try")

    def test_the_second_try_is_refused_as_well_while_the_tag_is_still_gone_and_the_request_is_open_each_time(self):
        self.strip()
        for _ in range(3):
            result = self.whole()
            self.assertEqual((result.ok, result.kind, result.message), (False, "stopped", OWNERS_WORDS))
            self.assertEqual(self.stored(), ("open", "withdrawn", "awaiting_ok"))
        self.assertEqual((len(self.redeemed), self.deletes()), (3, 0))

    def test_a_new_refusal_replaces_the_record_of_the_old_one_and_says_its_own_reason(self):
        self.strip()
        self.whole()
        before = self.store.action_get(self.plan.plan_id)
        self.put_back()
        self.azure.locks[DISK.lower()] = [{"name": "l"}]
        result = self.whole()
        self.assertEqual((result.ok, result.kind), (False, "stopped"))
        after = self.store.action_get(self.plan.plan_id)
        self.assertEqual(after.state, "withdrawn")
        self.assertIn("management lock", after.result)
        self.assertNotEqual(after.correlation_id, before.correlation_id, "the record is the one of the latest try")
        self.assertEqual(self.stored(), ("open", "withdrawn", "awaiting_ok"))

    def test_a_request_that_changed_after_the_refusal_needs_a_new_approval_and_the_old_form_cannot_be_used_for_it(self):
        self.strip()
        self.whole()
        self.put_back()
        self.store.plan_put(replace(self.store.plan_get(self.plan.plan_id), what_changes="Somebody changed this text."))  # the digest and the code are those of the old text
        begun = self.begin()
        self.assertEqual((begun.location, begun.refusal.kind), ("", "refused_code"))
        self.assertEqual((self.deletes(), len(self.redeemed)), (0, 1))

    def test_a_request_that_changed_while_the_person_signed_in_is_refused_at_the_return_and_nothing_is_approved(self):
        begun = self.begin()
        self.store.plan_put(replace(self.store.plan_get(self.plan.plan_id), what_changes="Somebody changed this text."))
        result = self.back(self.state_of(begun))
        self.assertEqual((result.ok, result.kind), (False, "refused_code"))
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])
        self.assertIsNone(self.store.action_get(self.plan.plan_id))
        self.assertEqual(self.deletes(), 0)
        self.assertIsNotNone(plan_digest.problem(self.store.plan_get(self.plan.plan_id), self.plan.digest), "the request is not the one that its digest names")

    def test_a_request_that_is_not_the_one_that_was_approved_when_the_runner_looks_is_closed_and_not_reopened(self):
        # The digest is the one thing that a refusal does not roll back: a request that is not the one that was approved is not to be approved again, and a new one is made when the
        # resource is found again.
        world = fs.World()
        disk = world.arm.add(fs.disk(sku="StandardSSD_LRS"))
        plan, _ = world.approved(disk, "disk", "delete", 50.0, "orphan-managed-disk")
        world.store.plan_put(replace(world.store.plan_get(plan.plan_id), what_changes="Somebody changed this text."))
        done = world.run(plan)
        self.assertEqual(done.kind, "stopped")
        self.assertIn("something in the request changed after it was made", done.action.result)
        self.assertEqual(world.state(plan), ("failed", "failed", "failed"))
        self.assertEqual(world.arm.writes(), [])

    def test_a_refusal_of_azure_itself_still_closes_the_request(self):
        self.azure.delete_status = 403
        result = self.whole()
        self.assertEqual((result.ok, result.kind), (False, "azure_refused"))
        self.assertEqual(self.stored(), ("failed", "failed", "failed"), "something was tried in Azure: this is not a request to try again")

    def test_a_read_that_fails_right_before_the_change_is_a_refusal_that_leaves_the_request_open(self):
        self.azure.fail_reads = True
        result = self.whole()
        self.assertEqual((result.ok, result.kind), (False, "stopped"))
        self.assertIn("Nothing was changed.", result.message)
        self.assertEqual(self.stored(), ("open", "withdrawn", "awaiting_ok"))
        self.azure.fail_reads = False
        self.assertEqual(self.whole().kind, "ran")

    def test_changes_that_are_paused_after_the_approval_leave_the_request_open_and_a_release_lets_it_go_on(self):
        begun = self.begin()
        self.store.switch_put(SwitchRecord(name="changes", paused=True))
        result = self.back(self.state_of(begun))
        self.assertEqual(result.kind, "refused_paused", "the switch is looked at when the person comes back, before the code is redeemed")
        self.store.switch_put(SwitchRecord(name="changes", paused=False))
        self.assertEqual(self.whole().kind, "ran")

    def test_the_timer_finishes_a_refusal_that_stopped_half_way(self):
        # The store failed between the two writes of a refusal: the plan is approved, its action is withdrawn, and nothing else would ever open the request again.
        self.strip()
        self.whole()
        plan = self.store.plan_get(self.plan.plan_id)
        self.store.plan_put(replace(plan, state="approved"))
        self.store.case_put(replace(self.store.case_get(self.plan.case_id), status="approved"))
        self.store.decision_put(DecisionRecord(self.plan.plan_id, OID, "Tino", "approve", "2026-11-05T09:00:00Z", self.plan.code, plan_digest=self.plan.digest))
        self.assertEqual(self.stored(), ("approved", "withdrawn", "approved"))
        timer = RunnerServices(self.store, Client(read_calls(APPROVAL.change_scopes), lambda t: t, transport=self.azure.transport, sleep=lambda s: None, monotonic=lambda: 0.0),
                               lambda resource: "reader-token", APPROVAL, clock=self.clock, sleep=lambda s: None, emit=lambda kind, **f: None)
        tick(timer)
        self.assertEqual(self.stored(), ("open", "withdrawn", "awaiting_ok"))
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])
        tick(timer)
        self.assertEqual(self.stored(), ("open", "withdrawn", "awaiting_ok"), "the same step twice changes nothing more")


class TheStoreWhenTwoApproversMeet(TheFlow):
    def test_of_two_approvals_at_the_same_moment_after_a_refusal_only_one_takes_the_place_of_the_withdrawn_action(self):
        self.strip()
        self.whole()
        self.put_back()
        action = ActionRecord(plan_id=self.plan.plan_id, case_id=self.plan.case_id, family=self.plan.family, resource_id=self.plan.resource_id, state="queued",
                              queued_at="2026-11-05T09:00:00Z", correlation_id="mine")
        self.assertTrue(self.store.action_claim(action))
        self.assertFalse(self.store.action_claim(replace(action, correlation_id="theirs")), "the other approval finds an action that is going on")
        self.assertEqual(self.store.action_get(self.plan.plan_id).correlation_id, "mine")


class ForAChangeThatNeedsTwoPeople(TwoFlow):
    def test_a_refusal_takes_back_the_approval_of_the_second_person_and_keeps_the_confirmation_of_the_first(self):
        self.confirm()
        self.azure.resources[DISK.lower()]["tags"] = dict(STRIPPED)
        result = self.sign_in_as(SECOND)
        self.assertEqual((result.ok, result.kind), (False, "stopped"))
        self.assertEqual(self.kinds(), [(OID, "confirm")], "the confirmation of the first stays: it is not an approval")
        self.assertEqual((self.store.plan_get(self.plan.plan_id).state, self.store.action_get(self.plan.plan_id).state), ("open", "withdrawn"))
        self.azure.resources[DISK.lower()]["tags"] = dict(PLANTED)
        done = self.sign_in_as(SECOND)
        self.assertEqual((done.ok, done.kind), (True, "ran"), "the second person approves again, and the first does not have to confirm again")
        self.assertEqual(self.kinds(), [(OID, "confirm"), (OTHER, "approve")])

    def test_the_person_who_confirmed_still_cannot_be_the_one_who_approves_after_a_refusal(self):
        self.confirm()
        self.azure.resources[DISK.lower()]["tags"] = dict(STRIPPED)
        self.sign_in_as(SECOND)
        refused = self.sign_in_as(FIRST)
        self.assertEqual((refused.ok, refused.kind), (False, "refused_state"))
        self.assertEqual(self.kinds(), [(OID, "confirm")])


if __name__ == "__main__":
    unittest.main()
