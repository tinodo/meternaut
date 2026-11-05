import re
import unittest

from test_web_support import (MAYA, NOW, OPS, OWNER, TINO, Console, FailingStore, ScriptedDecider, at, make_action, make_case, make_decision, make_plan, snapshot)

from cases.models import DecideResult, SwitchRecord
from cases.web import layout

APPROVE = "Approve this exact change"
DETAIL_NAMES = ["What changes", "Resource", "Who makes the change", "Estimated saving a month", "What waiting costs a day", "What could go wrong", "How to undo it", "Evidence"]


def rows(reply) -> dict[str, str]:
    """The names and values of the summary list of the page."""
    found = {}
    for dl in reply.main.find_all("dl", class_="summary"):
        for div in dl.find_all("div"):
            dt, dd = div.find("dt"), div.find("dd")
            if dt is not None and dd is not None:
                found[dt.text()] = dd.text()
    return found


class ThePage(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.console.seed()
        self.reply = self.console.get("/ok/plan0001")

    def test_the_title_is_the_stored_one_and_a_sentence_says_that_it_needs_the_persons_ok_on_this_page(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), [make_plan().title])
        lead = self.reply.main.find("p", class_="lead")
        self.assertEqual(lead.text(), "This change needs your OK on this page.")
        self.assertEqual(self.reply.root.find("title").text(), f"{make_plan().title} - Meternaut")

    def test_what_changes_who_makes_it_what_it_saves_what_waiting_costs_what_could_go_wrong_how_to_undo_it_and_the_evidence_are_there(self):
        found = rows(self.reply)
        self.assertEqual(list(found), DETAIL_NAMES)
        plan = make_plan()
        self.assertEqual(found["What changes"], plan.what_changes)
        self.assertIn("planted-disk-1, in resource group meternaut-test-rg", found["Resource"])
        self.assertIn(plan.resource_id, found["Resource"])
        self.assertIn("The runner, the part of Meternaut that changes Azure.", found["Who makes the change"])
        self.assertIn("It may only delete an unattached disk or public IP address in resource group meternaut-test-rg.", found["Who makes the change"])
        self.assertEqual(found["Estimated saving a month"], "About 7.17 US dollars. This is an estimate from cost lines of the last 30 days.")
        self.assertEqual(found["What waiting costs a day"], "About 0.24 US dollars for each day that the resource stays as it is. This is an estimate.")
        self.assertEqual(found["What could go wrong"], plan.could_go_wrong)
        self.assertIn(plan.undo, found["How to undo it"])
        self.assertIn("This change cannot be undone.", found["How to undo it"])
        self.assertIn(plan.evidence_level, found["Evidence"])

    def test_what_could_go_wrong_and_the_warning_are_always_visible(self):
        for node in self.reply.main.walk():
            self.assertNotIn(node.tag, ("details", "summary"), "nothing is folded away")
            self.assertNotIn("hidden", node.attrs)
        self.assertIn("What could go wrong", self.reply.content)
        self.assertIn("Warning: This change cannot be undone.", self.reply.main.find("p", class_="warning-text").text())

    def test_a_change_that_is_not_a_deletion_and_has_an_undo_does_not_say_that_it_cannot_be_undone(self):
        self.console.store.plan_put(make_plan(family="resize-disk", undo="Resize the disk back to its old size within 24 hours."))
        reply = self.console.get("/ok/plan0001")
        self.assertNotIn("cannot be undone", reply.content)
        self.assertIn("Resize the disk back to its old size within 24 hours.", rows(reply)["How to undo it"])
        self.assertIn(f"You approve: {make_plan().title}", reply.content)

    def test_a_change_with_no_undo_text_says_so_plainly(self):
        self.console.store.plan_put(make_plan(family="resize-disk", undo=""))
        reply = self.console.get("/ok/plan0001")
        self.assertIn("This change cannot be undone.", reply.content)
        self.assertIn("No way to undo this change is recorded.", reply.content)

    def test_the_evidence_row_links_to_the_notebook_of_the_case(self):
        evidence = [a for a in self.reply.root.find_all("a") if a.attrs["href"] == "/why/case0001"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].text(), "Open the notebook for this case")
        self.assertIn("Open the notebook for this case", rows(self.reply)["Evidence"])
        self.assertEqual(self.console.get("/why/case0001").status, 200)

    def test_check_before_you_approve_restates_the_decision_in_three_lines(self):
        box = self.reply.main.find("section", class_="check")
        self.assertEqual(box.find("h2").text(), "Check before you approve")
        lines = [li.text() for li in box.find_all("li")]
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], 'You approve: Delete an unattached managed disk: the disk named "planted-disk-1" in resource group "meternaut-test-rg".')
        self.assertEqual(lines[1], "Undo: It cannot be undone.")
        self.assertTrue(lines[2].startswith("Your OK covers this plan only: code 7F3K92QD. Answer by Sun 8 Nov 2026 08:00 UTC"))
        order = [node.tag for node in self.reply.main.walk() if node.tag in ("section", "form")]
        self.assertEqual(order[0], "section", "the box comes before the buttons")

    def test_approve_and_decline_are_buttons_of_the_same_size_and_height_in_one_row(self):
        form = self.reply.form("/ok/plan0001", has_button=APPROVE)
        row = form.node.find("div", class_="actions")
        buttons = row.find_all("button")
        self.assertEqual([b.text() for b in buttons], [APPROVE, "Decline"])
        self.assertEqual([(b.attrs["name"], b.attrs["value"]) for b in buttons], [("decision", "approve"), ("decision", "decline")])
        style = layout.STYLE
        self.assertRegex(style, r"\.btn,button\{[^}]*min-height:2\.75rem[^}]*min-width:11rem")
        self.assertRegex(style, r"\.actions>\*\{flex:1 1 14rem;max-width:22rem\}")
        for rule in re.findall(r"(?:button|\.btn)\.(?:primary|secondary|danger)[^{]*\{[^}]*\}", style):
            self.assertNotRegex(rule, r"(?<![a-z-])(?:padding|min-height|min-width|height|width|font-size|border-width)\b", rule)

    def test_the_footer_has_the_plan_code_the_expiry_with_its_time_zone_why_a_person_to_talk_to_and_the_ai_line(self):
        footer = self.reply.root.find("footer").text()
        self.assertIn("Plan code 7F3K92QD.", footer)
        self.assertIn("It is a reference, not proof that this page is genuine.", footer)
        self.assertIn("This request expires on Sun 8 Nov 2026 08:00 UTC (09:00 CET).", footer)
        self.assertIn("Why you are seeing this. You are named as an approver of this plan, and you have the role approver.", footer)
        self.assertIn("Talk to a person. Write to Tino, Olga, Otto.", footer)
        self.assertIn("Written by AI (models: model-detective-x, model-skeptic-y). A person approves every change.", footer)
        self.assertIn("This page is served from console.example.test.", footer)
        self.assertEqual([a.attrs["href"] for a in self.reply.root.find("footer").find_all("a")], ["mailto:tino@example.com", "mailto:olga@example.com"])

    def test_the_page_never_shows_what_a_model_wrote(self):
        self.console.store.case_put(make_case(plan_id="plan0001", summary="MODEL-PROSE", objections=("MODEL-OBJECTION",)))
        reply = self.console.get("/ok/plan0001")
        self.assertNotIn("MODEL-PROSE", reply.text)
        self.assertNotIn("MODEL-OBJECTION", reply.text)
        self.assertIn("MODEL-PROSE", self.console.get("/why/case0001").text)

    def test_the_forms_carry_the_code_and_a_token_for_this_person_and_this_plan_each_of_its_own(self):
        forms = self.reply.forms()
        self.assertEqual([f.action for f in forms], ["/ok/plan0001", "/ok/plan0001/ask", "/ok/plan0001/not-mine"])
        self.assertEqual({f.method for f in forms}, {"post"})
        tokens = [f.fields["nonce"] for f in forms]
        self.assertEqual(len(set(tokens)), 3)
        self.assertEqual({f.fields["code"] for f in forms}, {"7F3K92QD"})
        store = self.console.store
        self.assertFalse(store.nonce_use(tokens[0], MAYA, "plan0001"), "bound to the person")
        self.assertFalse(store.nonce_use(tokens[0], TINO, "plan0002"), "bound to the plan")
        self.assertTrue(store.nonce_use(tokens[0], TINO, "plan0001"))
        self.assertFalse(store.nonce_use(tokens[0], TINO, "plan0001"), "used once")
        self.assertTrue(store.nonce_use(tokens[1], TINO, "plan0001"))

    def test_the_token_lasts_until_the_plan_expires_but_not_longer_than_a_day(self):
        store = self.console.store
        seen = []
        original = store.nonce_new
        store.nonce_new = lambda oid, purpose, ttl_seconds=3600: seen.append(ttl_seconds) or original(oid, purpose, ttl_seconds)
        self.console.get("/ok/plan0001")
        self.assertEqual(set(seen), {86400})
        self.console.store.plan_put(make_plan(expires_at=at(minutes=30)))
        seen.clear()
        self.console.get("/ok/plan0001")
        self.assertEqual(set(seen), {1800})

    def test_a_question_that_the_person_asked_before_is_shown_to_them_alone(self):
        self.console.store.decision_put(make_decision(decision="ask", note="Is this the standby disk?"))
        self.console.store.decision_put(make_decision(approver_oid=MAYA, approver_name="Maya", decision="ask", note="MAYA-PRIVATE"))
        reply = self.console.get("/ok/plan0001")
        self.assertIn("Your earlier question or suggestion", reply.content)
        self.assertIn("Is this the standby disk?", reply.content)
        self.assertNotIn("MAYA-PRIVATE", reply.text)
        self.assertEqual(len(reply.forms()), 3, "a question is not a decision: the plan is still open")

    def test_two_people_class_says_so(self):
        self.console.store.plan_put(make_plan(approval_class="R3"))
        self.assertEqual(self.console.get("/ok/plan0001").main.find("p", class_="lead").text(), "This change needs two people, each on their own.")

    def test_time_is_in_utc_and_in_the_persons_own_zone(self):
        content = self.reply.content
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (09:00 CET)", content)
        self.assertIn('datetime="2026-11-08T08:00:00Z"', self.reply.text)


class WhenThePlanIsNotOpen(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.console.seed()

    def page(self, **changes):
        self.console.store.plan_put(make_plan(**changes))
        return self.console.get("/ok/plan0001")

    def assert_no_buttons(self, reply):
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.forms(), [], "no form and so no button")
        self.assertEqual(reply.root.find_all("button"), [])
        self.assertNotIn(APPROVE, reply.content)
        self.assertNotIn("Check before you approve", reply.content)

    def test_a_plan_whose_time_is_over_shows_it_has_expired_also_when_the_record_still_says_open(self):
        reply = self.page(expires_at=at(minutes=-1))
        self.assert_no_buttons(reply)
        self.assertIn("This request expired on Thu 5 Nov 2026 08:59 UTC (09:59 CET). Nothing has changed.", reply.content)

    def test_the_plan_that_expires_at_this_moment_has_expired(self):
        self.assert_no_buttons(self.page(expires_at=at()))

    def test_a_plan_that_has_expired_in_the_record(self):
        reply = self.page(state="expired")
        self.assert_no_buttons(reply)
        self.assertIn("Expired", reply.content)

    def test_each_other_state_shows_its_state_in_words_and_no_buttons(self):
        for state, words_ in (("declined", "This request was declined. Nothing has changed."), ("withdrawn", "This request was withdrawn. Nothing has changed."),
                              ("consumed", "The runner took this plan. A plan runs once."), ("failed", "The runner could not finish the change."),
                              ("approved", "This plan is approved. It waits for the runner. Nothing has changed yet.")):
            with self.subTest(state=state):
                reply = self.page(state=state)
                self.assert_no_buttons(reply)
                self.assertIn(words_, reply.content)
                self.assertIn(make_plan().title, reply.headings(1))
                self.assertIn("What changes", reply.content, "the plan stays readable")

    def test_a_plan_that_the_runner_took_shows_what_the_runner_did(self):
        self.console.store.action_put(make_action(state="done", started_at=at(minutes=-3), finished_at=at(minutes=-2), result="Deleted. Azure no longer lists the resource.",
                                                  verification={"gone": True, "checkedAt": at(minutes=-2)}))
        reply = self.page(state="consumed")
        self.assert_no_buttons(reply)
        found = {}
        for div in reply.main.find_all("div"):
            if div.find("dt") is not None:
                found[div.find("dt").text()] = div.find("dd").text()
        self.assertEqual(found["State"], "Done.")
        self.assertEqual(found["Result"], "Deleted. Azure no longer lists the resource.")
        self.assertIn("Azure no longer lists the resource.", found["Checked afterwards"])
        self.assertIn("What the runner did", reply.headings(2))

    def test_an_approved_plan_shows_the_start_time_and_a_cancel_to_the_person_who_approved_it_until_then(self):
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action())
        reply = self.page(state="approved")
        self.assertEqual(reply.status, 200)
        self.assertIn("Your OK is recorded since Thu 5 Nov 2026 08:59 UTC (09:59 CET). Nothing has changed yet.", reply.content)
        self.assertIn("The change starts at Thu 5 Nov 2026 09:01 UTC (10:01 CET).", reply.content)
        self.assertEqual([f.action for f in reply.forms()], ["/ok/plan0001/withdraw"])
        self.assertEqual(reply.forms()[0].buttons, [("", "", "Cancel my OK")])
        self.assertTrue(self.console.store.nonce_use(reply.forms()[0].fields["nonce"], TINO, "plan0001"))

    def test_the_cancel_ends_when_the_start_time_has_passed(self):
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action())
        self.console.now = self.console.now.replace(minute=2)
        reply = self.page(state="approved")
        self.assertEqual(reply.forms(), [])
        self.assertIn("The start time has passed. The runner starts the change at its next check, and it cannot be cancelled now.", reply.content)

    def test_no_cancel_for_a_change_that_is_not_queued_or_not_approved_by_this_person(self):
        self.console.store.decision_put(make_decision(approver_oid=MAYA, approver_name="Maya"))
        self.console.store.action_put(make_action())
        reply = self.page(state="approved", approvers=(TINO, MAYA))
        self.assertEqual(reply.forms(), [])
        self.assertIn("This plan is approved. It waits for the runner.", reply.content)
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action(state="running", started_at=at(minutes=-1)))
        self.assertEqual(self.console.get("/ok/plan0001").forms(), [])
        self.console.store.action_put(make_action(state="withdrawn"))
        self.assertEqual(self.console.get("/ok/plan0001").forms(), [])

    def test_an_approved_change_with_no_start_time_says_when_the_runner_starts_it_and_can_be_cancelled(self):
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action(start_after=None))
        reply = self.page(state="approved")
        self.assertIn("The runner starts the change when it next looks at its queue.", reply.content)
        self.assertEqual([f.action for f in reply.forms()], ["/ok/plan0001/withdraw"])


class WhenChangesArePaused(unittest.TestCase):
    PAUSED = "Changes are paused here. Nothing has changed, and your OK cannot be recorded now."

    def setUp(self):
        self.console = Console()
        self.console.seed()

    def test_a_pulled_switch_hides_the_approve_button_and_says_why(self):
        for name in ("changes", "all"):
            with self.subTest(switch=name):
                self.console.store.switch_put(SwitchRecord(name, True, "Otto", at(minutes=-1), "drill"))
                reply = self.console.get("/ok/plan0001")
                self.assertEqual(reply.status, 200)
                self.assertNotIn(APPROVE, reply.content)
                self.assertIn(self.PAUSED, reply.content)
                self.assertEqual([b[2] for f in reply.forms() for b in f.buttons], ["Decline", "Send the question or suggestion", "This is not mine"])
                self.console.store.switch_put(SwitchRecord(name))
        self.assertIn(APPROVE, self.console.get("/ok/plan0001").content)

    def test_the_switch_of_the_messages_does_not_stop_an_answer(self):
        self.console.store.switch_put(SwitchRecord("messages", True, "Otto", at(minutes=-1), "drill"))
        reply = self.console.get("/ok/plan0001")
        self.assertIn(APPROVE, reply.content)
        self.assertNotIn(self.PAUSED, reply.content)

    def test_a_switch_that_cannot_be_read_counts_as_pulled(self):
        console = Console(store=FailingStore(fail={"switch_get"}, clock=lambda: NOW))
        console.seed()
        reply = console.get("/ok/plan0001")
        self.assertEqual(reply.status, 200)
        self.assertNotIn(APPROVE, reply.content)
        self.assertIn(self.PAUSED, reply.content)


class WhoMayAnswer(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.console.seed()

    def test_a_person_who_is_not_named_gets_the_refusal_and_no_plan_details(self):
        for who, label in ((MAYA, "an approver who is not named"), (OWNER, "no approver role"), (OPS, "no approver role")):
            with self.subTest(label=label, who=who):
                reply = self.console.get("/ok/plan0001", oid=who)
                self.assertEqual(reply.status, 403)
                self.assertEqual(reply.headings(1), ["I cannot take your OK on this request."])
                for secret in (make_plan().title, "planted-disk-1", "7F3K92QD", "meternaut-test-rg", "What changes", "Estimated saving", "7.17"):
                    self.assertNotIn(secret, reply.content, f"no plan detail: {secret}")
                self.assertEqual(reply.root.find_all("button"), [])
                self.assertIn("Talk to a person.", reply.content)

    def test_a_request_that_does_not_exist_is_a_404_for_an_approver_and_the_refusal_for_anybody_else(self):
        self.assertEqual(self.console.get("/ok/nothing", oid=TINO).status, 404)
        self.assertEqual(self.console.get("/ok/nothing", oid=MAYA).status, 404)
        self.assertEqual(self.console.get("/ok/nothing", oid=OWNER).status, 403)

    def test_the_decider_is_not_called_for_a_person_who_may_not_answer(self):
        form = self.console.get("/ok/plan0001").forms()
        before = snapshot(self.console.store)
        for who in (MAYA, OWNER, OPS):
            for action, fields in (("/ok/plan0001", {"decision": "approve", "code": "7F3K92QD", "nonce": form[0].fields["nonce"]}),
                                   ("/ok/plan0001/ask", {"note": "hm", "code": "7F3K92QD", "nonce": form[1].fields["nonce"]}),
                                   ("/ok/plan0001/not-mine", {"code": "7F3K92QD", "nonce": form[2].fields["nonce"]}),
                                   ("/ok/plan0001/withdraw", {"nonce": form[0].fields["nonce"]})):
                with self.subTest(who=who, action=action):
                    reply = self.console.post(action, fields, oid=who)
                    self.assertEqual(reply.status, 403)
                    self.assertIn("I cannot take your OK on this request.", reply.content)
        self.assertEqual(self.console.decider.calls, [])
        self.assertEqual(self.console.decider.withdrawals, [])
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(self.console.post("/ok/nothing", {"decision": "approve"}, oid=OWNER).status, 403)
        self.assertEqual(self.console.post("/ok/nothing", {"decision": "approve"}, oid=TINO).status, 404)
        self.assertEqual(self.console.decider.calls, [])

    def test_the_names_in_the_plan_are_compared_without_regard_to_case(self):
        self.console.store.plan_put(make_plan(approvers=(TINO.upper(),)))
        self.assertEqual(self.console.get("/ok/plan0001").status, 200)


KINDS = {
    "recorded": (200, "Recorded. Nothing has changed yet."),
    "declined": (200, "Declined. Nothing has changed. The request is closed."),
    "asked": (200, "Recorded. Your question or suggestion approves nothing."),
    "not_mine": (200, "Recorded. Nothing is approved. The request goes back to finding the right owner."),
    "withdrawn": (200, "Cancelled. Your OK is withdrawn and the request is closed. Nothing has changed."),
    "refused_code": (409, "This plan changed. Nothing is approved. A new message will bring the new plan and code."),
    "refused_state": (409, "This request is not open for an answer now. It may be answered, cancelled, expired or replaced. Nothing has changed."),
    "refused_role": (403, "I cannot take your OK on this request."),
    "refused_paused": (409, "Changes are paused here. Nothing has changed, and your OK cannot be recorded now."),
    "expired": (410, "This request expired on Sun 8 Nov 2026 08:00 UTC (09:00 CET). Nothing has changed."),
    "duplicate": (409, "You answered this request already. Your first answer stands, and nothing has changed."),
    "error": (500, "I could not take your answer"),
}


class EveryKindOfResult(unittest.TestCase):
    def setUp(self):
        self.decider = ScriptedDecider()
        self.console = Console(decider=self.decider)
        self.console.seed()

    def answer(self, kind: str, message: str = "a message of the decider"):
        self.decider.result = DecideResult(kind in ("recorded", "declined", "asked", "not_mine", "withdrawn"), kind, message, make_plan())
        form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        return self.console.submit(form, "Decline" if kind == "declined" else APPROVE)

    def test_every_kind_has_a_plain_page_of_its_own(self):
        self.assertEqual(set(KINDS), {"recorded", "declined", "asked", "not_mine", "withdrawn", "refused_code", "refused_state", "refused_role", "refused_paused", "expired",
                                      "duplicate", "error"})
        for kind, (status, sentence) in KINDS.items():
            with self.subTest(kind=kind):
                reply = self.answer(kind)
                self.assertEqual(reply.status, status)
                self.assertIn(sentence, reply.content)
                self.assertEqual(len(reply.headings(1)), 1)
                self.assertIn("Talk to a person.", reply.content, "the same help on every page")
                self.assertIn("Written by AI (models:", reply.content)
                self.assertEqual(reply.problems, [])
                self.assertEqual(reply.root.find_all("button"), [])

    def test_the_decider_is_called_with_the_person_the_plan_the_answer_the_code_the_token_and_the_note(self):
        form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        self.console.submit(form, "Decline", note="No, thank you")
        self.assertEqual(self.decider.calls, [dict(oid=TINO, plan_id="plan0001", decision="decline", code="7F3K92QD", nonce=form.fields["nonce"], note="No, thank you")])
        self.console.submit(form, APPROVE, note="")
        self.assertEqual(self.decider.calls[1]["decision"], "approve")
        self.assertEqual(self.decider.calls[1]["note"], "")

    def test_a_refusal_of_the_role_by_the_decider_shows_no_plan_details(self):
        reply = self.answer("refused_role")
        for secret in (make_plan().title, "planted-disk-1", "7F3K92QD", "7.17"):
            self.assertNotIn(secret, reply.content)

    def test_the_message_of_the_decider_is_not_needed_to_show_a_time_it_does_not_have(self):
        self.decider.result = DecideResult(False, "expired", "x", None)
        form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        reply = self.console.submit(form, APPROVE)
        self.assertIn("This request expired on Sun 8 Nov 2026 08:00 UTC (09:00 CET).", reply.content, "the time is read from the plan in the store")

    def test_a_plan_that_is_gone_is_a_request_that_cannot_be_found(self):
        self.console.store.plans.clear()
        reply = self.console.post("/ok/plan0001", {"decision": "approve", "code": "c", "nonce": "n"})
        self.assertEqual(reply.status, 404)
        self.assertEqual(self.decider.calls, [])

    def test_an_unknown_kind_and_a_decider_that_fails_are_an_error_page(self):
        for result in (DecideResult(False, "something-new", "m"), None, "text", RuntimeError("boom with a secret detail")):
            with self.subTest(result=repr(result)):
                self.decider.result = result
                form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
                reply = self.console.submit(form, APPROVE)
                self.assertEqual(reply.status, 500)
                self.assertIn("I could not take your answer", reply.content)
                self.assertNotIn("boom", reply.text)
                self.assertNotIn("Traceback", reply.text)

    def test_the_message_of_an_error_is_shown_as_text_and_cut_short(self):
        reply = self.answer("error", "This form is no longer valid. " + "x" * 600)
        self.assertIn("This form is no longer valid.", reply.content)
        self.assertLess(len(reply.content), 2500)
        self.assertIn("Open the request again to see where it stands.", reply.content)

    def test_the_withdrawal_has_its_own_words_for_a_refusal(self):
        self.decider.result = DecideResult(False, "refused_state", "no", make_plan())
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action())
        self.console.store.plan_put(make_plan(state="approved"))
        form = self.console.get("/ok/plan0001").form("/withdraw")
        reply = self.console.submit(form)
        self.assertEqual(reply.status, 409)
        self.assertIn("There is no OK of yours to cancel, or the change has started and cannot be cancelled. Nothing has changed.", reply.content)
        self.assertEqual(self.decider.withdrawals[0]["plan_id"], "plan0001")


class WhatIsCheckedBeforeTheDecider(unittest.TestCase):
    def setUp(self):
        self.decider = ScriptedDecider()
        self.console = Console(decider=self.decider)
        self.console.seed()
        self.page = self.console.get("/ok/plan0001")
        self.main, self.ask, self.mine = self.page.forms()

    def test_an_answer_that_is_neither_approve_nor_decline_is_refused_and_the_decider_is_not_called(self):
        for decision in ("", "ask", "not_mine", "APPROVE", "approve,decline", "delete"):
            with self.subTest(decision=decision):
                reply = self.console.post("/ok/plan0001", {**self.main.fields, "decision": decision})
                self.assertEqual(reply.status, 400)
                self.assertIn("The form did not say Approve or Decline. Nothing was recorded.", reply.content)
        self.assertEqual(self.decider.calls, [])

    def test_a_form_with_no_token_is_refused_and_the_decider_is_not_called(self):
        for action, fields in (("/ok/plan0001", {"decision": "approve", "code": "7F3K92QD"}), ("/ok/plan0001/ask", {"note": "hm", "code": "7F3K92QD"}),
                               ("/ok/plan0001/not-mine", {"code": "7F3K92QD"}), ("/ok/plan0001/withdraw", {}), ("/ok/plan0001", {"decision": "approve", "nonce": ""})):
            with self.subTest(action=action, fields=fields):
                reply = self.console.post(action, fields)
                self.assertEqual(reply.status, 403)
                self.assertIn("This form cannot be used", reply.headings(1))
                self.assertIn("Nothing was changed.", reply.content)
        self.assertEqual((self.decider.calls, self.decider.withdrawals), ([], []))

    def test_the_code_goes_to_the_decider_as_the_form_sent_it(self):
        self.console.submit(self.main, APPROVE, code="WRONG")
        self.assertEqual(self.decider.calls[0]["code"], "WRONG")
        self.console.post("/ok/plan0001", {"decision": "approve", "nonce": "tok"})
        self.assertEqual(self.decider.calls[1]["code"], "")

    def test_a_note_longer_than_300_characters_is_refused_with_the_text_kept_and_the_decider_is_not_called(self):
        long = "a" * 301
        reply = self.console.submit(self.main, APPROVE, note=long)
        self.assertEqual(reply.status, 400)
        self.assertEqual(self.decider.calls, [])
        self.assertIn("There is a problem", reply.headings(2))
        self.assertIn("The note has 301 characters. The most is 300.", reply.content)
        self.assertEqual(reply.form("/ok/plan0001", has_button=APPROVE).fields["note"], long, "the person's text is still in the box")
        link = [a for a in reply.root.find_all("a") if a.attrs["href"] == "#note"]
        self.assertEqual(len(link), 1, "the list of problems links to the field")
        self.assertIsNotNone(reply.root.find("textarea", id="note"))
        self.assertEqual(self.console.submit(self.main, APPROVE, note="a" * 300).status, 200)
        self.assertEqual(self.decider.calls[0]["note"], "a" * 300)

    def test_a_question_needs_text_of_at_most_300_characters(self):
        for note, message in (("", "Write your question or suggestion."), ("a" * 301, "The text has 301 characters. The most is 300.")):
            with self.subTest(length=len(note)):
                reply = self.console.submit(self.ask, note=note)
                self.assertEqual(reply.status, 400)
                self.assertIn(message, reply.content)
                self.assertEqual(self.decider.calls, [])
        reply = self.console.submit(self.ask, note="Is it the standby disk?")
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.decider.calls, [dict(oid=TINO, plan_id="plan0001", decision="ask", code="7F3K92QD", nonce=self.ask.fields["nonce"], note="Is it the standby disk?")])

    def test_not_mine_and_the_cancel_go_to_the_decider_with_what_it_needs(self):
        self.decider.result = DecideResult(True, "not_mine", "ok", make_plan())
        self.console.submit(self.mine)
        self.assertEqual(self.decider.calls, [dict(oid=TINO, plan_id="plan0001", decision="not_mine", code="7F3K92QD", nonce=self.mine.fields["nonce"], note="")])
        self.decider.result = DecideResult(True, "withdrawn", "ok", make_plan())
        reply = self.console.post("/ok/plan0001/withdraw", {"nonce": "tok"})
        self.assertEqual(self.decider.withdrawals, [dict(oid=TINO, plan_id="plan0001", nonce="tok")])
        self.assertIn("Cancelled", reply.headings(1))

    def test_the_note_is_cleaned_of_control_characters_before_it_goes_on(self):
        self.console.post("/ok/plan0001", {**self.main.fields, "decision": "decline", "note": "line one\r\nline\ttwo\x00"})
        self.assertEqual(self.decider.calls[0]["note"], "line one line two")


class TheConfirmation(unittest.TestCase):
    def setUp(self):
        self.decider = ScriptedDecider(DecideResult(True, "recorded", "Recorded.", make_plan(state="approved")))
        self.console = Console(decider=self.decider)
        self.console.seed()
        self.form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)

    def approved(self, **action):
        self.console.store.plan_put(make_plan(state="approved"))
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action(**action))

    def test_it_says_nothing_has_changed_and_when_the_change_starts_and_offers_a_cancel(self):
        self.approved()
        reply = self.console.submit(self.form, APPROVE)
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), ["Your OK is recorded"])
        self.assertIn("Recorded. Nothing has changed yet.", reply.content)
        self.assertIn("The change starts at Thu 5 Nov 2026 09:01 UTC (10:01 CET).", reply.content)
        self.assertIn("Until then you can cancel your OK. Cancelling closes the request, and nothing changes.", reply.content)
        cancel = reply.form("/ok/plan0001/withdraw")
        self.assertEqual(cancel.buttons, [("", "", "Cancel my OK")])
        self.assertTrue(self.console.store.nonce_use(cancel.fields["nonce"], TINO, "plan0001"))

    def test_the_cancel_works_through_the_decider(self):
        self.approved()
        reply = self.console.submit(self.form, APPROVE)
        self.decider.result = DecideResult(True, "withdrawn", "ok", make_plan(state="withdrawn"))
        done = self.console.submit(reply.form("/ok/plan0001/withdraw"))
        self.assertEqual(done.status, 200)
        self.assertIn("Cancelled. Your OK is withdrawn and the request is closed. Nothing has changed.", done.content)
        self.assertEqual(len(self.decider.withdrawals), 1)

    def test_no_cancel_after_the_start_time(self):
        self.approved()
        self.console.now = self.console.now.replace(minute=5)
        reply = self.console.submit(self.form, APPROVE)
        self.assertIn("Recorded. Nothing has changed yet.", reply.content)
        self.assertEqual(reply.forms(), [])
        self.assertIn("The start time has passed.", reply.content)

    def test_no_start_time_is_shown_that_the_records_do_not_hold(self):
        reply = self.console.submit(self.form, APPROVE)
        self.assertIn("Recorded. Nothing has changed yet.", reply.content)
        self.assertNotIn("The change starts", reply.content)
        self.assertEqual(reply.forms(), [])

    def test_no_cancel_when_the_change_has_started(self):
        self.approved(state="running", started_at=at(minutes=-1))
        reply = self.console.submit(self.form, APPROVE)
        self.assertEqual(reply.forms(), [])
        self.assertNotIn("The change starts", reply.content)


class AgainstTheLoop(unittest.TestCase):
    """The pages and a small approval loop over one store: the tokens and codes of the forms are the ones that the loop checks."""

    def setUp(self):
        self.console = Console(decider="loop")
        self.console.seed()
        self.console.store.plan_put(make_plan(approvers=(TINO, MAYA)))

    def forms(self, who=TINO):
        return self.console.get("/ok/plan0001", oid=who).forms()

    def test_an_approval_is_recorded_once_and_can_be_cancelled(self):
        main, _, _ = self.forms()
        reply = self.console.submit(main, APPROVE, note="Go on")
        self.assertEqual(reply.headings(1), ["Your OK is recorded"])
        self.assertEqual(self.console.store.plan_get("plan0001").state, "approved")
        self.assertEqual(self.console.store.action_get("plan0001").state, "queued")
        self.assertEqual([d.decision for d in self.console.store.decisions_of_plan("plan0001")], ["approve"])
        again = self.console.get("/ok/plan0001")
        self.assertIn("Your OK is recorded since", again.content)
        cancelled = self.console.submit(again.form("/withdraw"))
        self.assertEqual(cancelled.headings(1), ["Cancelled"])
        self.assertEqual(self.console.store.action_get("plan0001").state, "withdrawn")
        self.assertIn("Withdrawn", self.console.get("/ok/plan0001").content)
        self.assertEqual(self.console.get("/ok/plan0001").forms(), [])

    def test_the_same_form_cannot_be_used_twice(self):
        main, _, _ = self.forms()
        self.assertEqual(self.console.submit(main, APPROVE).status, 200)
        before = snapshot(self.console.store)
        second = self.console.submit(main, APPROVE)
        self.assertEqual(second.status, 500)
        self.assertIn("This form is no longer valid.", second.content)
        self.assertEqual(snapshot(self.console.store), before)

    def test_a_wrong_code_is_refused_and_changes_nothing(self):
        main, _, _ = self.forms()
        before = snapshot(self.console.store)
        reply = self.console.submit(main, APPROVE, code="AAAAAAAA")
        self.assertEqual(reply.status, 409)
        self.assertIn("This plan changed. Nothing is approved. A new message will bring the new plan and code.", reply.content)
        self.assertEqual(snapshot(self.console.store), before)

    def test_a_missing_or_wrong_token_changes_nothing(self):
        main, _, _ = self.forms()
        before = snapshot(self.console.store)
        for token in ("", "nope", "x" * 32):
            reply = self.console.submit(main, APPROVE, nonce=token)
            self.assertIn(reply.status, (403, 500))
        self.assertEqual(snapshot(self.console.store), before)

    def test_a_token_of_another_person_or_another_plan_is_refused(self):
        main, _, _ = self.forms(TINO)
        self.console.store.plan_put(make_plan(plan_id="plan0002", approvers=(TINO,)))
        other = self.console.get("/ok/plan0002").forms()[0]
        before = snapshot(self.console.store)
        reply = self.console.submit(main, APPROVE, oid=MAYA)
        self.assertEqual(reply.status, 500)
        self.assertEqual(snapshot(self.console.store), before)
        reply = self.console.post("/ok/plan0001", {**main.fields, "decision": "approve", "nonce": other.fields["nonce"]})
        self.assertEqual(reply.status, 500)
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(self.console.submit(main, APPROVE).status, 200, "the right person with the right token still can")

    def test_a_decline_closes_the_request_and_the_page_shows_it(self):
        main, _, _ = self.forms()
        reply = self.console.submit(main, "Decline", note="Not now")
        self.assertEqual(reply.headings(1), ["Declined"])
        self.assertEqual(self.console.store.plan_get("plan0001").state, "declined")
        self.assertEqual(self.console.get("/ok/plan0001").forms(), [])
        self.assertIn("This request was declined.", self.console.get("/ok/plan0001").content)

    def test_a_question_leaves_the_request_open_and_is_shown_to_the_person_who_asked(self):
        _, ask, _ = self.forms()
        reply = self.console.submit(ask, note="Is it the standby disk?")
        self.assertEqual(reply.headings(1), ["Your question is recorded"])
        self.assertIn("The request stays open until Sun 8 Nov 2026 08:00 UTC", reply.content)
        page = self.console.get("/ok/plan0001")
        self.assertEqual(len(page.forms()), 3)
        self.assertIn("Is it the standby disk?", page.content)
        self.assertNotIn("Is it the standby disk?", self.console.get("/ok/plan0001", oid=MAYA).content)

    def test_not_mine_closes_the_request_for_the_person(self):
        _, _, mine = self.forms()
        reply = self.console.submit(mine)
        self.assertEqual(reply.headings(1), ["Recorded: not yours"])
        self.assertEqual(self.console.store.plan_get("plan0001").state, "withdrawn")


if __name__ == "__main__":
    unittest.main()
