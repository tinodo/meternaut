"""The pages and the real approval loop over one in-memory store: the forms of the pages are the ones that the loop checks."""
import unittest

from test_web_support import GROUP, MAYA, NOW, OPS, SUB, TINO, Console, snapshot

try:
    from cases.approvals import Approvals, ApprovalSettings
    from cases.detectors import Lead
except ImportError as error:  # the loop is built by another part of the work
    raise unittest.SkipTest(f"the approval loop is not there: {error}")

from cases.models import CaseRecord, SwitchRecord
from cases.memory_store import stamp

APPROVE = "Approve this exact change"


def lead(kind="orphan-managed-disk", name="planted-disk-1"):
    resource = "microsoft.compute/disks" if kind == "orphan-managed-disk" else "microsoft.network/publicipaddresses"
    return Lead(detector=kind, resource_id=f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/{resource}/{name}", resource_type=resource, name=name, resource_group=GROUP,
                subscription_id=SUB, location="swedencentral", tags={"meternaut-planted": "demo"}, managed_by="", facts={"diskState": "unattached"}, age_days=0)


class WithTheRealLoop(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.loop = Approvals(self.console.store, ApprovalSettings(writer_group=GROUP), lambda: self.console.now)
        self.console.use(self.loop)
        item = lead()
        self.case = CaseRecord(case_id="k1", resource_id=item.resource_id, resource_name=item.name, resource_type=item.resource_type, resource_group=GROUP, subscription_id=SUB,
                               detector=item.detector, run_id="run00001", status="proposed", recommendation="delete", confidence=0.9, saving_usd_month=7.17, cost_usd_30d=7.17,
                               summary="The model said so.", objections=("An objection.",), updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        self.console.store.case_put(self.case)
        self.plan = self.loop.create(self.case, item, (TINO,))
        self.assertIsNotNone(self.plan)
        self.path = f"/ok/{self.plan.plan_id}"

    def form(self, who=TINO, action=None, button=None):
        return self.console.get(self.path, oid=who).form(action or self.path, has_button=button)

    def test_the_page_shows_the_plan_that_the_loop_made(self):
        reply = self.console.get(self.path)
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), [self.plan.title])
        found = reply.summary(0)
        self.assertEqual(found["What changes"], self.plan.what_changes)
        self.assertEqual(found["Estimated saving a month"], "About 7.17 US dollars. This is an estimate from cost lines of the last 30 days.")
        self.assertIn("A deleted disk cannot be restored and its data is lost.", found["How to undo it"])
        self.assertIn("This change cannot be undone.", found["How to undo it"])
        self.assertIn(f"code {self.plan.code}", reply.content)
        self.assertEqual(self.console.store.case_get("k1").status, "awaiting_ok")

    def test_an_approval_cancel_and_the_pages_that_report_them(self):
        reply = self.console.submit(self.form(button=APPROVE), APPROVE)
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), ["Your OK is recorded"])
        self.assertIn("Recorded. Nothing has changed yet.", reply.content)
        self.assertIn("The change starts at Thu 5 Nov 2026 09:02 UTC (10:02 CET).", reply.content)
        action = self.console.store.action_get(self.plan.plan_id)
        self.assertEqual((action.state, action.start_after), ("queued", "2026-11-05T09:02:00Z"))
        self.assertIn("The change starts at Thu 5 Nov 2026 09:02 UTC (10:02 CET).", self.console.get("/me/activity").content)
        cancelled = self.console.submit(self.console.get("/me/activity").form("/withdraw"))
        self.assertEqual(cancelled.status, 200)
        self.assertIn("Cancelled. Your OK is withdrawn and the request is closed. Nothing has changed.", cancelled.content)
        self.assertEqual(self.console.store.action_get(self.plan.plan_id).state, "withdrawn")
        activity = self.console.get("/me/activity")
        self.assertEqual(activity.summary(0)["State"], "Withdrawn before it started. Nothing changed.")
        self.assertEqual(activity.forms(), [])
        decisions = self.console.get("/me/decisions").table("decisions").rows[0]
        self.assertEqual(decisions["Your answer"], "Your OK")
        self.assertEqual(decisions["What came of it"], "Withdrawn before it started. Nothing changed.")
        self.assertIn("Withdrawn", self.console.get(self.path).content)

    def test_the_cancel_ends_at_the_start_time_in_the_loop_too(self):
        self.console.submit(self.form(button=APPROVE), APPROVE)
        page = self.console.get(self.path)
        cancel = page.form("/withdraw")
        self.console.now = self.console.now.replace(minute=3)
        reply = self.console.submit(cancel)
        self.assertEqual(reply.status, 409)
        self.assertIn("There is no OK of yours to cancel, or the change has started and cannot be cancelled. Nothing has changed.", reply.content)
        self.assertEqual(self.console.store.action_get(self.plan.plan_id).state, "queued")

    def test_every_refusal_of_the_loop_has_its_page(self):
        main = self.form(button=APPROVE)
        # a wrong code
        reply = self.console.submit(main, APPROVE, code="WRONG")
        self.assertEqual((reply.status, reply.headings(1)), (409, ["This plan changed"]))
        # a token that was not made for this person
        other_plan_form = self.console.get(self.path).form(self.path, has_button=APPROVE)
        self.console.store.plan_put(type(self.plan)(**{**vars(self.plan), "approvers": (TINO, MAYA)}))
        reply = self.console.submit(other_plan_form, APPROVE, oid=MAYA)
        self.assertEqual((reply.status, reply.headings(1)), (500, ["I could not take your answer"]))
        self.assertIn("This form is no longer valid.", reply.content)
        self.assertEqual(self.console.store.plan_get(self.plan.plan_id).state, "open")
        # a pulled switch
        self.console.store.switch_put(SwitchRecord("changes", True, "Otto", "2026-11-05T08:00:00Z", "drill"))
        forged = self.console.post(self.path, {**main.fields, "decision": "approve"})
        self.assertEqual((forged.status, forged.headings(1)), (409, ["Changes are paused"]))
        self.console.store.switch_put(SwitchRecord("changes"))
        # the right answer, once, and then again with the same form
        self.assertEqual(self.console.submit(main, APPROVE).status, 200)
        again = self.console.submit(main, APPROVE)
        self.assertEqual(again.status, 409)
        self.assertEqual(again.headings(1), ["This request cannot take an answer"], "the request is approved now, so it takes no answer")
        # a plan whose time is over
        self.console.store.plan_put(type(self.plan)(**{**vars(self.plan), "state": "open"}))
        self.console.now = self.console.now.replace(day=9)
        late = self.console.post(self.path, {**main.fields, "decision": "approve", "nonce": self.console.store.nonce_new(TINO, self.plan.plan_id)})
        self.assertEqual((late.status, late.headings(1)), (410, ["This request expired"]))
        self.assertIn("This request expired on Sun 8 Nov 2026 09:00 UTC", late.content)
        self.assertEqual(self.console.store.case_get("k1").status, "expired")

    def test_a_question_then_an_approval_leaves_one_answer(self):
        ask = self.console.get(self.path).form(self.path + "/ask")
        self.assertEqual(self.console.submit(ask, note="Is it the standby?").headings(1), ["Your question is recorded"])
        self.assertEqual(self.console.submit(self.form(button=APPROVE), APPROVE).headings(1), ["Your OK is recorded"])
        answers = self.console.store.decisions_of_plan(self.plan.plan_id)
        self.assertEqual([d.decision for d in answers], ["approve"])

    def test_a_decline_closes_the_request_and_the_case(self):
        declined = self.console.submit(self.form(button="Decline"), "Decline", note="Not now")
        self.assertEqual(declined.headings(1), ["Declined"])
        self.assertEqual(self.console.store.plan_get(self.plan.plan_id).state, "declined")
        self.assertEqual(self.console.store.case_get("k1").status, "declined")
        self.assertEqual(self.console.get("/me/decisions").table("decisions").rows[0]["Your answer"], "No, leave it as it is Your note: Not now")

    def test_a_person_who_is_not_named_is_refused_by_the_page_before_the_loop(self):
        self.assertEqual(self.console.get(self.path, oid=MAYA).status, 403)
        self.assertEqual(self.console.get(self.path, oid=OPS).status, 403)
        before = snapshot(self.console.store)
        main = self.form(button=APPROVE)
        self.assertEqual(self.console.submit(main, APPROVE, oid=MAYA).status, 403)
        self.assertEqual(snapshot(self.console.store), before)


if __name__ == "__main__":
    unittest.main()
