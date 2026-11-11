import re
import unittest

from test_web_support import (ACTS_ON, MAYA, NOW, OPS, OWNER, SIGNIN_URL, STRANGER, TINO, VM, Console, FailingStore, ScriptedDecider, ScriptedDelegate, at, make_action,
                              make_advice, make_advice_case, make_case, make_decision, make_plan, snapshot)

from cases.brief import SECOND_WORDS
from cases.models import MAX_SIGNIN_PATH, Begun, DecideResult, StoreError, SwitchRecord
from cases.people import People, Person
from cases.web import approval, layout

APPROVE = "Approve and sign in to Azure"
CODE = "0.AbCdEfGhIjKlMnOpQrSt-code-from-the-sign-in"
STATE = "state-of-the-sign-in_0123456789"
RETURN = {"code": CODE, "state": STATE, "session_state": "a-session-state"}
HEADLINE = "Delete the unattached disk planted-disk-1 in group meternaut-test-rg"
TITLE = "Delete the unattached disk planted-disk-1"  # the headline without its place, which the line under the title says
ANSWERS = [("decision", "approve", APPROVE), ("decision", "decline", "Decline"), ("decision", "not_mine", "This is not mine"), ("decision", "ask", "Ask or tell"),
           ("decision", "later", "Decide later")]


def rows(reply) -> dict[str, str]:
    """The names and values of the summary list of the page."""
    found = {}
    for dl in reply.main.find_all("dl", class_="summary"):
        for div in dl.find_all("div"):
            dt, dd = div.find("dt"), div.find("dd")
            if dt is not None and dd is not None:
                found[dt.text()] = dd.text()
    return found


def _parents(node):
    while node.parent is not None:
        node = node.parent
        yield node


class ThePage(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.console.seed()
        self.reply = self.console.get("/ok/plan0001")

    def test_the_title_says_what_is_asked_and_the_card_what_it_gives(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), [TITLE])
        self.assertEqual(self.reply.root.find("title").text(), f"{TITLE} - Meternaut")
        self.assertEqual(self.reply.main.find("div", class_="head").find("p").text(),
                         "Managed disk · resource group meternaut-test-rg · found 3 days ago · open until Sun 8 Nov 2026 08:00 UTC (09:00 CET)")
        self.assertEqual(self.reply.main.find("p", class_="fig save").text(), "$86 a year")
        self.assertEqual(self.reply.main.find("p", class_="figsub").text(),
                         "Saves, Expected. $7.17 a month. Based on the cost lines of the last 30 days. Waiting costs about $0.24 a day.")
        self.assertIn("Money is in US dollars, and a year is twelve times the month.", self.reply.content)

    def test_the_page_answers_the_eight_questions_in_this_order(self):
        self.assertEqual(self.reply.headings(2)[:5], ["If you approve", "What was measured", "Why the AIs think so", "Whose is it", "Your answer"])
        self.assertIn("How sure: High.", self.reply.content)
        self.assertEqual(self.reply.measured(), {"Cost, last 30 days": ("$7.17", "Azure cost lines"), "State": ("Not attached to any virtual machine", "Azure Resource Graph"),
                                                 "Locks and keep tags": ("None found", "Azure, checked by code")})
        found = self.reply.facts()
        self.assertEqual(list(found), ["What changes", "Who does it", "Checked again", "Undo", "What could go wrong"])
        self.assertEqual(found["What changes"], "Deletes the disk planted-disk-1 in resource group meternaut-test-rg. Nothing else changes.")
        self.assertTrue(found["Who does it"].startswith("You do, with your own Azure sign-in"), found["Who does it"])
        self.assertIn("Azure checks your rights, and the change is made right then.", found["Who does it"])
        self.assertIn("Meternaut holds no right of its own to change anything.", found["Who does it"])
        self.assertNotIn("runner", found["Who does it"].lower())
        self.assertEqual(found["Undo"], "This cannot be undone.")
        self.assertEqual(found["What could go wrong"], "If something still uses the disk, that use stops, and the data on it is lost for good. Risk: medium.")
        self.assertIn("Meternaut has not looked up who owns this resource yet.", self.reply.content)
        self.assertIn("Managed disk planted-disk-1, resource group meternaut-test-rg, subscription bbbbbbbb.", self.reply.content)

    def test_three_chips_say_the_risk_how_sure_the_ais_are_and_what_a_change_leaves_behind(self):
        chips = [chip.text() for chip in self.reply.main.find("p", class_="chips").find_all("span")]
        self.assertEqual([c for c in chips if c], ["Medium risk", "High confidence", "Cannot be undone"])
        self.console.store.plan_put(make_plan(family="resize-disk", undo="Resize the disk back to its old size within 24 hours."))
        undoable = self.console.get("/ok/plan0001").main.find("p", class_="chips").text()
        self.assertIn("Can be undone", undoable)
        self.assertNotIn("Cannot be undone", undoable)

    def test_what_could_go_wrong_and_the_undo_are_not_folded_away_and_a_delete_says_in_bold_that_it_cannot_be_undone(self):
        outside = [node for node in self.reply.main.walk() if node.tag == "dl" and not any(parent.tag == "details" for parent in _parents(node))]
        text = " ".join(node.text() for node in outside)
        self.assertIn("What could go wrong", text)
        self.assertIn("Undo", text)
        self.assertIn("This cannot be undone.", [strong.text() for strong in self.reply.main.find_all("strong")])

    def test_a_change_that_has_an_undo_does_not_say_that_it_cannot_be_undone(self):
        self.console.store.plan_put(make_plan(family="resize-disk", undo="Resize the disk back to its old size within 24 hours."))
        reply = self.console.get("/ok/plan0001")
        self.assertNotIn("cannot be undone", reply.content)
        self.assertEqual(reply.facts()["Undo"], "Resize the disk back to its old size within 24 hours.")
        self.assertEqual(reply.headings(1), ["Delete an unattached managed disk in resource group meternaut-test-rg"], "a family without words of its own keeps the plan's title")

    def test_a_change_with_no_undo_text_says_so_plainly(self):
        self.console.store.plan_put(make_plan(family="resize-disk", undo=""))
        reply = self.console.get("/ok/plan0001")
        self.assertEqual(reply.facts()["Undo"], "This cannot be undone.")

    def test_the_two_ais_words_are_in_boxes_that_say_that_code_did_not_check_them(self):
        labels = [p.text() for p in self.reply.main.find_all("p", class_="quote-label")]
        self.assertEqual(labels[:2], ["The AI's reasoning (not checked by code)", "The second AI's doubt"])
        self.assertIn("The disk is not attached and nothing uses it.", self.reply.content)
        self.assertIn("It may hold data that somebody wants.", self.reply.content)

    def test_one_closed_disclosure_holds_everything_a_decision_does_not_need(self):
        (disclosure,) = self.reply.main.find_all("details")
        self.assertEqual(disclosure.find("summary").text(), "Details")
        self.assertNotIn("open", disclosure.attrs)
        inside = disclosure.text()
        outside = self.reply.main.text().replace(inside, "")
        for detail in ("Request code 7F3K92QD", "case0001", "run00001", "orphan-managed-disk", "Every step of the finding", "diskState", "Served from"):
            self.assertIn(detail, inside)
            self.assertNotIn(detail, outside, f"{detail} is not in the default view")

    def test_the_decision_is_one_form_with_a_note_a_reason_and_a_button_for_each_answer_that_exists(self):
        (form,) = self.reply.forms()
        self.assertEqual((form.action, form.method), ("/ok/plan0001", "post"))
        self.assertEqual(set(form.fields), {"code", "nonce", "note", "reason"})
        self.assertEqual(form.fields["code"], "7F3K92QD")
        self.assertEqual(form.buttons, [(name, value, text) for name, value, text in ANSWERS])
        self.assertEqual([o.text() for o in form.node.find("select").find_all("option")],
                         ["No reason", "It is still needed", "The figure is wrong", "It is already handled", "Another reason (say it in the note)"])
        self.assertIn("A question, an objection or something to remember", self.reply.content)
        self.assertIn("It is recorded with your name, Meternaut does not answer yet, and it approves nothing.", self.reply.content)

    def test_the_old_buttons_explain_challenge_and_teach_are_one_answer_ask_or_tell(self):
        labels = [text for _, _, text in self.reply.forms()[0].buttons]
        self.assertIn("Ask or tell", labels)
        for gone in ("Explain", "Challenge", "Teach", "Ask a question first", "Send the question or suggestion"):
            self.assertNotIn(gone, labels)
            self.assertNotIn(f">{gone}<", self.reply.text)

    def test_the_page_links_to_the_azure_portal_with_an_address_made_from_the_resource_id_only(self):
        portal = [a for a in self.reply.root.find_all("a") if a.attrs["href"].startswith("https://")]
        self.assertEqual([(a.text(), a.attrs["href"], a.attrs.get("rel")) for a in portal],
                         [("Open in the Azure portal", f"https://portal.azure.com/#resource{make_plan().resource_id}", "noopener")])
        self.console.store.case_put(make_case(plan_id="plan0001", resource_id='/subscriptions/x"><script>', resource_name="x"))
        self.console.store.plan_put(make_plan(resource_id='/subscriptions/x"><script>'))
        hostile = self.console.get("/ok/plan0001")
        self.assertEqual([a for a in hostile.root.find_all("a") if a.attrs["href"].startswith("https://")], [], "an id that is not the id of one resource makes no link")
        self.assertNotIn("<script>", hostile.text)

    def test_the_case_page_is_the_same_brief(self):
        case_page = self.console.get("/why/case0001")
        self.assertEqual(case_page.status, 200)
        self.assertEqual(case_page.headings(1), [TITLE])
        self.assertEqual(case_page.headings(2)[:5], ["If you approve", "What was measured", "Why the AIs think so", "Whose is it", "Your answer"])
        self.assertEqual(case_page.facts(), self.reply.facts())

    def test_the_footer_says_that_an_ai_wrote_it_and_under_about_this_page_why_the_person_sees_it_and_who_is_responsible(self):
        footer = self.reply.root.find("footer")
        self.assertEqual([p.text() for p in footer.find_all("p")], [
            "Recommendations written by AI. A person approves every change.",
            "Models: model-detective-x, model-skeptic-y. You see this because you are named as an approver of this request, and you have the role approver. "
            "Responsible for Meternaut: Olga (olga@example.com)."])
        self.assertEqual(footer.find("summary").text(), "About this page")
        self.assertEqual(footer.find_all("a"), [], "the person who is responsible is plain text with the address, not a link")
        for gone in ("Request code", "Why you are seeing this", "This page is served from", "This request expires on"):
            self.assertNotIn(gone, footer.text())

    def test_what_a_model_wrote_is_only_in_its_labelled_boxes_and_in_the_details_and_never_in_a_heading_a_link_or_a_row_of_the_change(self):
        self.console.store.case_put(make_case(plan_id="plan0001", summary="MODEL-PROSE", objections=("MODEL-OBJECTION",)))
        reply = self.console.get("/ok/plan0001")
        self.assertIn("MODEL-PROSE", reply.text)
        for tag in ("h1", "h2", "h3", "a", "button", "title", "th", "dt"):
            for node in reply.root.find_all(tag):
                self.assertNotIn("MODEL", node.text())
        for rows_ in (reply.facts(), {name: value for name, (value, _) in reply.measured().items()}):
            for name, value in rows_.items():
                self.assertNotIn("MODEL", value, name)

    def test_the_form_carries_the_code_and_a_token_for_this_person_and_this_plan(self):
        (form,) = self.reply.forms()
        token = form.fields["nonce"]
        store = self.console.store
        self.assertFalse(store.nonce_use(token, MAYA, "plan0001"), "bound to the person")
        self.assertFalse(store.nonce_use(token, TINO, "plan0002"), "bound to the plan")
        self.assertTrue(store.nonce_use(token, TINO, "plan0001"))
        self.assertFalse(store.nonce_use(token, TINO, "plan0001"), "used once")
        self.assertNotEqual(self.console.get("/ok/plan0001").forms()[0].fields["nonce"], token, "each page has a token of its own")

    def test_approve_and_decline_are_buttons_of_the_same_size_and_height_in_one_stack(self):
        form = self.reply.form("/ok/plan0001", has_button=APPROVE)
        row = form.node.find("div", class_="acts stack")
        buttons = row.find_all("button")
        self.assertEqual([b.text() for b in buttons], [APPROVE, "Decline"])
        self.assertEqual([(b.attrs["name"], b.attrs["value"]) for b in buttons], [("decision", "approve"), ("decision", "decline")])
        style = layout.STYLE
        self.assertRegex(style, r"\.btn,button\{[^}]*min-height:2\.5rem[^}]*min-width:8rem")
        self.assertRegex(style, r"\.acts\.stack\{flex-direction:column\}\n\.acts\.stack>\*\{width:100%\}")
        for rule in re.findall(r"(?:button|\.btn)\.(?:primary|secondary|danger)[^{]*\{[^}]*\}", style):
            self.assertNotRegex(rule, r"(?<![a-z-])(?:padding|min-height|min-width|height|width|font-size|border-width)\b", rule)
        other = form.node.find_all("div", class_="acts")[0]
        self.assertEqual([(b.text(), b.attrs["class"]) for b in other.find_all("button")], [("This is not mine", "subtle sm"), ("Ask or tell", "subtle sm"), ("Decide later", "subtle sm")])

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
        self.assertIn("Your earlier question", reply.content)
        self.assertIn("Is this the standby disk?", reply.content)
        self.assertNotIn("MAYA-PRIVATE", reply.text)
        self.assertEqual(len(reply.forms()), 1, "a question is not a decision: the plan is still open")

    def test_two_people_class_says_so_and_a_plan_that_only_one_person_can_approve_says_that_too(self):
        self.console.store.plan_put(make_plan(approval_class="R3", approvers=(TINO, MAYA)))
        reply = self.console.get("/ok/plan0001")
        self.assertEqual(reply.facts()["Who approves"], SECOND_WORDS["first"])
        self.assertTrue(reply.form("/ok/plan0001", has_button="Confirm this request"))
        self.assertFalse(reply.form("/ok/plan0001", has_button="Confirm this request").has_button(APPROVE), "the first person confirms; the sign-in to Azure is the second person's")
        self.console.store.plan_put(make_plan(approval_class="R3"))
        alone = self.console.get("/ok/plan0001")
        self.assertEqual(alone.facts()["Who approves"], SECOND_WORDS["alone"])
        self.assertEqual([label for _, _, label in alone.forms()[0].buttons], ["Decline", "This is not mine", "Ask or tell", "Decide later"])

    def test_time_is_in_utc_and_in_the_persons_own_zone(self):
        content = self.reply.content
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (09:00 CET)", content)
        self.assertIn('datetime="2026-11-08T08:00:00Z"', self.reply.text)

    def test_the_page_has_no_cancel_no_start_time_and_no_form_that_posts_to_withdraw(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual([f.action for f in self.reply.forms()], ["/ok/plan0001"])
        self.assertNotIn("withdraw", self.reply.text.lower())
        for gone in ("Cancel my OK", "The change starts at", "start time", "120 seconds", "runner"):
            self.assertNotIn(gone.lower(), self.reply.content.lower(), gone)

    def test_opening_the_page_starts_no_sign_in_and_asks_nobody_to_decide(self):
        before = snapshot(self.console.store)
        self.console.get("/ok/plan0001")
        self.console.get("/ok/plan0001")
        self.assertEqual((self.console.delegate.begins, self.console.delegate.finishes, self.console.decider.calls), ([], [], []))
        self.assertEqual(snapshot(self.console.store), before)


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

    def notice(self, reply):
        """The title and the lines of the one notice that says what became of the request."""
        (title,) = reply.main.find_all("p", class_="notice-title")
        return title.text(), title.parent.text().replace(title.text(), "", 1).strip()

    def test_a_plan_whose_time_is_over_shows_it_has_expired_also_when_the_record_still_says_open(self):
        reply = self.page(expires_at=at(minutes=-1))
        self.assert_no_buttons(reply)
        self.assertEqual(self.notice(reply), ("Expired", "Nobody answered in time. Nothing changed. Thu 5 Nov 2026 08:59 UTC (09:59 CET)"))
        self.assertNotIn("Open until", reply.content)

    def test_the_plan_that_expires_at_this_moment_has_expired(self):
        self.assert_no_buttons(self.page(expires_at=at()))

    def test_a_plan_that_has_expired_in_the_record(self):
        reply = self.page(state="expired")
        self.assert_no_buttons(reply)
        self.assertIn("Expired", reply.content)

    def test_each_other_state_shows_its_state_in_words_and_no_buttons(self):
        for state, title, words_ in (("declined", "Declined", "Declined by Tino. Reason: it is already handled. Nothing changed."),
                                     ("withdrawn", "Not theirs", "Tino said that this is not theirs. Nothing changed."),
                                     ("consumed", "Done", "Approved by Tino, and made with their own Azure rights. Deleted. Azure no longer lists the resource."),
                                     ("failed", "Not made", "Azure refused to delete the resource."),
                                     ("approved", "Approved", "Approved by Tino. The change is being made now.")):
            with self.subTest(state=state):
                console = Console()
                console.seed()
                console.store.decision_put(make_decision(decision={"declined": "decline", "withdrawn": "not_mine"}.get(state, "approve"), reason="handled" if state == "declined" else ""))
                if state in ("consumed", "failed"):
                    console.store.action_put(make_action(state="done" if state == "consumed" else "failed", started_at=at(minutes=-3), finished_at=at(minutes=-2),
                                                         result="Deleted. Azure no longer lists the resource." if state == "consumed" else "Azure refused to delete the resource.",
                                                         verification={"gone": True, "checkedAt": at(minutes=-2)} if state == "consumed" else {}))
                console.store.plan_put(make_plan(state=state))
                reply = console.get("/ok/plan0001")
                self.assert_no_buttons(reply)
                self.assertEqual(self.notice(reply)[0], title)
                self.assertIn(words_, self.notice(reply)[1])
                self.assertIn(TITLE, reply.headings(1))
                self.assertIn("If you approve", reply.headings(2), "the plan stays readable")

    def test_a_plan_that_was_used_shows_what_happened_to_the_change_in_the_details(self):
        self.console.store.action_put(make_action(state="done", started_at=at(minutes=-3), finished_at=at(minutes=-2), result="Deleted. Azure no longer lists the resource.",
                                                  verification={"gone": True, "checkedAt": at(minutes=-2)}))
        reply = self.page(state="consumed")
        self.assert_no_buttons(reply)
        found = rows(reply)
        self.assertEqual(found["State"], "Done.")
        self.assertEqual(found["Result"], "Deleted. Azure no longer lists the resource.")
        self.assertIn("Azure no longer lists the resource.", found["Checked afterwards"])
        (disclosure,) = reply.main.find_all("details")
        self.assertIn("What happened to the change", disclosure.text())
        self.assertNotIn("What the runner did", reply.content)

    def test_a_plan_that_failed_shows_what_happened_to_the_change_in_the_details(self):
        self.console.store.action_put(make_action(state="failed", started_at=at(minutes=-3), finished_at=at(minutes=-2), result="Azure refused to delete the resource.",
                                                  error="Azure refused to delete the resource."))
        reply = self.page(state="failed")
        self.assert_no_buttons(reply)
        found = rows(reply)
        self.assertEqual((found["State"], found["Result"]), ("Failed.", "Azure refused to delete the resource."))
        self.assertEqual(self.notice(reply)[0], "Not made")

    def test_a_plan_with_no_action_shows_no_part_for_what_happened(self):
        for state in ("approved", "consumed", "failed", "declined"):
            with self.subTest(state=state):
                self.assertNotIn("What happened to the change", self.page(state=state).main.text())

    def test_an_approved_plan_says_that_the_change_is_being_made_and_has_no_form_and_no_start_time(self):
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action())
        reply = self.page(state="approved")
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.notice(reply), ("Approved", "Approved by Tino. The change is being made now. Thu 5 Nov 2026 08:59 UTC (09:59 CET)"))
        self.assertEqual(reply.forms(), [])
        self.assertEqual(reply.root.find_all("button"), [])
        for gone in ("Cancel my OK", "Nothing has changed yet", "The change starts at", "start time", "the runner"):
            self.assertNotIn(gone.lower(), reply.content.lower(), gone)
        found = rows(reply)
        self.assertEqual(found["State"], "Queued. It has not started.")
        self.assertNotIn("Starts at", found)

    def test_an_approved_plan_that_another_person_approved_names_that_person(self):
        self.console.store.decision_put(make_decision(approver_oid=MAYA, approver_name="Maya"))
        self.console.store.action_put(make_action())
        reply = self.page(state="approved", approvers=(TINO, MAYA))
        self.assertIn("Approved by Maya. The change is being made now.", reply.content)
        self.assertEqual(reply.forms(), [])

    def test_an_approved_plan_whose_change_waits_for_the_extra_sign_in_check_says_so_and_that_nothing_was_changed_yet(self):
        wait = "Azure asked for an extra sign-in check before it would delete the resource. Nothing was changed yet. The change waits until the approver has completed the check."
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action(step_up=True, result=wait))
        reply = self.page(state="approved")
        self.assertEqual(reply.status, 200)
        self.assertIn("Approved by Tino. Azure asked for an extra sign-in check before it would make the change. "
                      "The change waits until the check is completed. Nothing was changed yet.", reply.content)
        self.assertNotIn("The change is being made now", reply.content)
        found = rows(reply)
        self.assertEqual((found["State"], found["Result"]), ("Queued. It has not started.", wait))
        self.assertEqual((reply.forms(), reply.root.find_all("button")), ([], []))
        self.assertEqual(self.notice(reply)[0], "Approved")

    def test_an_action_that_asked_for_the_check_and_is_running_again_is_being_made_now(self):
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action(step_up=True, state="running", started_at=at(seconds=-5)))
        reply = self.page(state="approved")
        self.assertIn("The change is being made now.", reply.content)
        self.assertNotIn("extra sign-in check", reply.content)

    def test_a_queued_action_of_the_earlier_design_that_holds_a_start_time_shows_none(self):
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action(start_after=at(minutes=1)))
        reply = self.page(state="approved")
        self.assertNotIn("Starts at", rows(reply))
        self.assertNotIn("09:01 UTC", reply.content)
        self.assertEqual(reply.forms(), [])

    def test_no_state_of_the_plan_has_a_form_that_posts_to_withdraw_or_a_button_to_cancel(self):
        self.console.store.decision_put(make_decision())
        self.console.store.action_put(make_action())
        for state in ("open", "approved", "consumed", "declined", "expired", "withdrawn", "failed"):
            with self.subTest(state=state):
                reply = self.page(state=state)
                self.assertEqual([f.action for f in reply.forms() if "withdraw" in f.action], [])
                self.assertNotIn("/withdraw", reply.text)
                self.assertNotIn("Cancel my OK", reply.content)


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
                self.assertEqual([b[2] for f in reply.forms() for b in f.buttons], ["Decline", "This is not mine", "Ask or tell", "Decide later"])
                self.console.store.switch_put(SwitchRecord(name))
        self.assertIn(APPROVE, self.console.get("/ok/plan0001").content)

    def test_advice_is_held_by_the_full_stop_only_because_nothing_changes_in_azure_for_it(self):
        self.console.store.case_put(make_advice_case())
        self.console.store.plan_put(make_advice())
        for name, held in (("changes", False), ("all", True)):
            with self.subTest(switch=name):
                self.console.store.switch_put(SwitchRecord(name, True, "Otto", at(minutes=-1), "drill"))
                reply = self.console.get("/ok/plan0002")
                labels = [b[2] for f in reply.forms() for b in f.buttons]
                self.assertEqual("Worth acting on" in labels, not held)
                self.assertEqual("Meternaut is paused here. Nothing has changed, and your answer cannot be recorded now." in reply.content, held)
                self.assertIn("Not worth it", labels)
                self.console.store.switch_put(SwitchRecord(name))

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
                for secret in (HEADLINE, TITLE, make_plan().title, "planted-disk-1", "7F3K92QD", "meternaut-test-rg", "If you approve", "Saves, Expected", "$86", "7.17"):
                    self.assertNotIn(secret, reply.content, f"no plan detail: {secret}")
                self.assertEqual(reply.root.find_all("button"), [])
                self.assertIn("Responsible for Meternaut: ", reply.content)

    def test_a_request_that_does_not_exist_is_a_404_for_an_approver_and_the_refusal_for_anybody_else(self):
        self.assertEqual(self.console.get("/ok/nothing", oid=TINO).status, 404)
        self.assertEqual(self.console.get("/ok/nothing", oid=MAYA).status, 404)
        self.assertEqual(self.console.get("/ok/nothing", oid=OWNER).status, 403)
        self.assertEqual(self.console.get("/ok/nothing", oid=OPS).status, 403)

    def test_an_owner_who_is_named_may_answer_advice_and_nothing_else(self):
        self.console.store.case_put(make_advice_case())
        self.console.store.plan_put(make_advice(approvers=(TINO, OWNER)))
        self.console.store.plan_put(make_plan(approvers=(TINO, OWNER)))
        advice = self.console.get("/ok/plan0002", oid=OWNER)
        self.assertEqual(advice.status, 200)
        self.assertEqual([b[2] for f in advice.forms() for b in f.buttons], ["Worth acting on", "Not worth it", "This is not mine", "Ask or tell", "Decide later"])
        change = self.console.get("/ok/plan0001", oid=OWNER)
        self.assertEqual(change.status, 403, "an owner who is not an approver cannot approve a change")
        unnamed = self.console.get("/ok/plan0002", oid=MAYA)
        self.assertEqual(unnamed.status, 403, "and a person who is not named cannot answer anything")

    def test_neither_the_decider_nor_the_delegate_is_called_for_a_person_who_may_not_answer(self):
        form = self.console.get("/ok/plan0001").forms()
        before = snapshot(self.console.store)
        for who in (MAYA, OWNER, OPS):
            for decision, note in (("approve", ""), ("decline", ""), ("ask", "hm"), ("not_mine", ""), ("later", "")):
                fields = {"decision": decision, "code": "7F3K92QD", "nonce": form[0].fields["nonce"], "note": note}
                with self.subTest(who=who, decision=decision):
                    reply = self.console.post("/ok/plan0001", fields, oid=who)
                    self.assertEqual(reply.status, 403)
                    self.assertIn("I cannot take your OK on this request.", reply.content)
                    self.assertNotIn("Location", reply.headers)
            for old in ("/ok/plan0001/ask", "/ok/plan0001/not-mine"):
                with self.subTest(who=who, address=old):
                    self.assertEqual(self.console.post(old, {"note": "hm", "code": "7F3K92QD", "nonce": form[0].fields["nonce"]}, oid=who).status, 403)
        self.assertEqual(self.console.decider.calls, [])
        self.assertEqual((self.console.delegate.begins, self.console.delegate.finishes), ([], []))
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(self.console.post("/ok/nothing", {"decision": "approve"}, oid=OWNER).status, 403)
        self.assertEqual(self.console.post("/ok/nothing", {"decision": "approve"}, oid=TINO).status, 404)
        self.assertEqual(self.console.decider.calls, [])
        self.assertEqual(self.console.delegate.begins, [])

    def test_the_route_to_cancel_an_approval_is_gone(self):
        before = snapshot(self.console.store)
        for who in (TINO, MAYA, OWNER):
            with self.subTest(who=who):
                reply = self.console.post("/ok/plan0001/withdraw", {"nonce": "tok"}, oid=who)
                self.assertEqual(reply.status, 404)
                self.assertIn("I cannot find this page", reply.content)
                self.assertEqual(self.console.get("/ok/plan0001/withdraw", oid=who).status, 404)
        self.assertEqual(self.console.post("/ok/plan0001/withdraw", {}, oid=STRANGER).status, 403)
        self.assertEqual((self.console.decider.calls, self.console.delegate.begins, self.console.delegate.finishes), ([], [], []))
        self.assertEqual(snapshot(self.console.store), before)

    def test_the_names_in_the_plan_are_compared_without_regard_to_case(self):
        self.console.store.plan_put(make_plan(approvers=(TINO.upper(),)))
        self.assertEqual(self.console.get("/ok/plan0001").status, 200)


KINDS = {  # the status, the title of the page, and a sentence that the page always has
    "declined": (200, "Declined", "Declined. Nothing has changed. The request is closed."),
    "asked": (200, "Recorded: your words", "Recorded with your name. It approves nothing, and Meternaut does not answer yet."),
    "later": (200, "Noted", "Noted. Nothing is approved and nothing has changed. The request stays in your list."),
    "acknowledged": (200, "Recorded: worth acting on", "Recorded. Nothing was changed in Azure."),
    "confirmed": (200, "Recorded: you confirmed the request", "Recorded with your name. Nothing was changed. A second person has to approve it and sign in to Azure, with their own permissions."),
    "not_mine": (200, "Recorded: not yours", "Recorded. Nothing is approved. The request goes back to finding the right owner."),
    "ran": (200, "The change was made", "It was made with your own permissions: Azure's Activity Log shows your name as the person who made it. "
                                        "Meternaut holds no right of its own to change Azure."),
    "ran_unconfirmed": (200, "The delete was accepted", "Meternaut looks again in a few minutes and records what it finds. It was made with your own permissions."),
    "running": (200, "The change is being made", "Meternaut reads the resource again in a few minutes and records what it finds. It was made with your own permissions, and it is "
                                                  "not made a second time."),
    "unchanged": (200, "Nothing was changed", "The resource was already as the request asks, so Meternaut wrote nothing, and no saving is claimed for this approval."),
    "stopped": (409, "The change was stopped", "Nothing was changed. The request is closed."),
    "azure_refused": (403, "Azure refused the change", "Meternaut holds no right of its own: the change is made with your permissions. If you should be able to make it, "
                                                       "ask whoever manages access to this resource group."),
    "failed": (502, "The change failed", "Look at the resource in Azure before anything is tried again."),
    "signin_failed": (400, "The sign-in to Azure was not completed", "The request stays open. Open it again to try again."),
    "step_up_failed": (400, "The extra sign-in check was not completed", "Nothing was changed. The request is closed."),
    "refused_code": (409, "This request changed", "This request changed. Nothing is approved. A new message will bring the new request and its code."),
    "refused_state": (409, "This request cannot take an answer", ""),
    "refused_role": (403, "I cannot take your OK on this request.", "Nothing is approved. If this request should be yours, ask the person named under About this page at the foot of this page."),
    "refused_paused": (409, "Changes are paused", "Changes are paused here. Nothing has changed, and your OK cannot be recorded now."),
    "expired": (410, "This request expired", "This request expired on Sun 8 Nov 2026 08:00 UTC (09:00 CET). Nothing has changed."),
    "duplicate": (409, "Already answered", "You answered this request already. Your first answer stands, and nothing has changed."),
    "error": (500, "I could not take your answer", "Open the request again to see where it stands."),
}
# The kinds whose page has a line for the message of the result. The page of every other kind has its own words only.
SHOWS_THE_MESSAGE = ("ran", "ran_unconfirmed", "running", "unchanged", "stopped", "azure_refused", "failed", "signin_failed", "step_up_failed", "refused_state", "error")
SUCCESSES = ("declined", "asked", "later", "acknowledged", "confirmed", "not_mine", "ran", "ran_unconfirmed", "running", "unchanged")
BACK_TO_THE_LIST = ("not_mine", "later", "refused_role")  # the pages whose back link goes to the decisions and not to the request


class EveryKindOfResult(unittest.TestCase):
    """A result looks the same to a person whichever step gave it: the decider (a decline), a refusal of `begin` (an approval) or `finish` (the return from the sign-in)."""

    def setUp(self):
        self.decider = ScriptedDecider()
        self.delegate = ScriptedDelegate()
        self.console = Console(decider=self.decider, delegate=self.delegate)
        self.console.seed()
        self.routes = (self.by_decider, self.by_begin, self.by_return)

    def result(self, kind: str, message: str, plan: bool) -> DecideResult:
        return DecideResult(kind in SUCCESSES, kind, message, make_plan() if plan else None)

    def by_decider(self, kind: str, message: str = "a message of the result", plan: bool = True):
        self.decider.result = self.result(kind, message, plan)
        form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        return self.console.submit(form, "Decline")

    def by_begin(self, kind: str, message: str = "a message of the result", plan: bool = True):
        self.delegate.begun = Begun(refusal=self.result(kind, message, plan))
        form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        return self.console.submit(form, APPROVE)

    def by_return(self, kind: str, message: str = "a message of the result", plan: bool = True):
        self.delegate.finished = self.result(kind, message, plan)
        return self.console.get("/arm/return", query=RETURN)

    def backs(self, reply) -> list[tuple[str, str]]:
        return [(a.attrs["href"], a.text()) for a in reply.main.find_all("a") if a.text().startswith("Back to")]

    def test_there_is_a_page_for_each_kind_of_result_and_for_no_other(self):
        self.assertEqual(set(KINDS), {"declined", "asked", "later", "acknowledged", "confirmed", "not_mine", "ran", "ran_unconfirmed", "running", "unchanged", "stopped", "azure_refused",
                                      "failed", "signin_failed", "step_up_failed", "refused_code", "refused_state", "refused_role", "refused_paused", "expired", "duplicate", "error"})
        self.assertEqual(set(KINDS), set(approval.STATUS))

    def test_every_kind_has_a_plain_page_of_its_own_whichever_step_gives_it(self):
        for route in self.routes:
            for kind, (status, title, sentence) in KINDS.items():
                with self.subTest(route=route.__name__, kind=kind):
                    reply = route(kind)
                    self.assertEqual(reply.status, status)
                    self.assertEqual(reply.headings(1), [title])
                    self.assertIn(sentence, reply.content)
                    self.assertIn("Responsible for Meternaut: ", reply.content, "the same help on every page")
                    self.assertIn("Recommendations written by AI. A person approves every change.", reply.content)
                    self.assertIn("Models: model-detective-x", reply.content)
                    self.assertEqual(reply.problems, [])
                    self.assertEqual(reply.root.find_all("button"), [])
                    self.assertEqual(reply.forms(), [])
                    self.assertNotIn("Location", reply.headers)

    def test_a_result_is_a_box_of_the_kind_of_news_it_is_and_the_way_back_is_a_button(self):
        self.assertEqual(set(approval.TONE), set(KINDS) - {"refused_role"}, "a refusal of the role is the plain page of its own")
        roles = {"success": "status", "error": "alert"}
        for route in self.routes:
            for kind in KINDS:
                if kind == "refused_role":
                    continue
                with self.subTest(route=route.__name__, kind=kind):
                    reply = route(kind)
                    (box,) = [node for node in reply.main.find_all("div") if "notice" in node.classes()]
                    self.assertEqual(box.classes(), ["notice", approval.TONE[kind]])
                    self.assertEqual(box.attrs.get("role"), roles.get(approval.TONE[kind]))
                    self.assertIsNone(box.find("p", class_="notice-title"), "the title of the page is the title of the box")
                    (back,) = [a for a in reply.main.find_all("a") if a.text().startswith("Back to")]
                    self.assertEqual(back.classes(), ["btn", "primary"])
        self.assertEqual([approval.TONE[kind] for kind in ("ran", "failed", "stopped", "declined")], ["success", "error", "warning", "info"])

    def test_the_back_link_goes_to_the_request_or_to_the_decisions(self):
        for route in self.routes:
            for kind in KINDS:
                with self.subTest(route=route.__name__, kind=kind):
                    wanted = ("/", "Back to the decisions") if kind in BACK_TO_THE_LIST else ("/ok/plan0001", "Back to the request")
                    self.assertEqual(self.backs(route(kind)), [wanted])

    def test_a_result_that_holds_no_plan_goes_back_to_the_decisions_after_a_return_and_to_the_request_after_an_answer(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(self.backs(self.by_return(kind, plan=False)), [("/", "Back to the decisions")])
                wanted = ("/", "Back to the decisions") if kind in BACK_TO_THE_LIST else ("/ok/plan0001", "Back to the request")
                self.assertEqual(self.backs(self.by_decider(kind, plan=False)), [wanted], "the address of the page names the plan")

    def test_the_time_of_an_expired_result_is_read_from_the_plan_in_the_store_and_left_out_when_no_plan_is_known(self):
        for route in (self.by_decider, self.by_begin):
            with self.subTest(route=route.__name__):
                reply = route("expired", plan=False)
                self.assertIn("This request expired on Sun 8 Nov 2026 08:00 UTC (09:00 CET). Nothing has changed.", reply.content)
        reply = self.by_return("expired", plan=False)
        self.assertEqual(reply.status, 410)
        self.assertNotIn("Sun 8 Nov 2026", reply.content)
        self.assertIn("Nothing has changed.", reply.content)

    def test_a_refusal_of_the_role_shows_no_plan_details(self):
        for route in self.routes:
            with self.subTest(route=route.__name__):
                reply = route("refused_role")
                for secret in (make_plan().title, "planted-disk-1", "7F3K92QD", "7.17"):
                    self.assertNotIn(secret, reply.content)

    def test_the_message_of_the_result_is_shown_on_the_pages_that_have_a_line_for_it_and_on_no_other(self):
        for route in self.routes:
            for kind in KINDS:
                with self.subTest(route=route.__name__, kind=kind):
                    self.assertEqual("MESSAGE-OF-THE-RESULT" in route(kind, "MESSAGE-OF-THE-RESULT").content, kind in SHOWS_THE_MESSAGE)

    def test_a_page_that_shows_the_message_has_a_plain_line_of_its_own_when_the_message_is_empty(self):
        lines = {"ran": "Done.", "ran_unconfirmed": "Azure accepted the delete.", "running": "Azure accepted the change and is still making it.",
                 "unchanged": "Nothing was changed.",
                 "stopped": "A check failed before the change.", "azure_refused": "Azure refused the change.",
                 "failed": "The change failed.", "signin_failed": "Nothing is approved.",
                 "step_up_failed": "The extra sign-in check that Azure asked for was not completed. The change was not made.",
                 "refused_state": "This request is not open for an answer now. It may be answered, expired or replaced. Nothing has changed.",
                 "error": "The approval service did not answer."}
        self.assertEqual(set(lines), set(SHOWS_THE_MESSAGE))
        for route in self.routes:
            for kind, line in lines.items():
                with self.subTest(route=route.__name__, kind=kind):
                    self.assertIn(line, [p.text() for p in route(kind, "").main.find_all("p")])

    def test_the_message_is_cut_to_400_characters_and_cleaned_of_control_characters(self):
        for route in self.routes:
            for kind in SHOWS_THE_MESSAGE:
                with self.subTest(route=route.__name__, kind=kind):
                    long = route(kind, "This form is no longer valid. " + "x" * 600)
                    self.assertIn("This form is no longer valid. " + "x" * 370, long.content)
                    self.assertNotIn("x" * 371, long.content)
                    self.assertIn("line one line two end", route(kind, "line one\r\nline\ttwo\x00 end").content)

    def test_an_unknown_kind_and_a_kind_that_no_longer_exists_are_an_error_page(self):
        for kind in ("something-new", "recorded", "withdrawn"):
            for route in self.routes:
                with self.subTest(route=route.__name__, kind=kind):
                    reply = route(kind)
                    self.assertEqual((reply.status, reply.headings(1)), (500, ["I could not take your answer"]))
                    self.assertIn("a message of the result", reply.content)

    def test_a_step_that_fails_or_answers_with_something_else_is_an_error_page_without_a_trace(self):
        form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        for broken in (None, "text", RuntimeError("boom with a secret detail"), StoreError("the store is down", 503)):
            with self.subTest(broken=repr(broken)):
                self.decider.result = broken
                self.delegate.finished = broken
                for reply in (self.console.submit(form, "Decline"), self.console.get("/arm/return", query=RETURN)):
                    self.assertEqual((reply.status, reply.headings(1)), (500, ["I could not take your answer"]))
                    self.assertIn("The approval service did not answer.", reply.content)
                    for leak in ("boom", "the store is down", "Traceback"):
                        self.assertNotIn(leak, reply.text)

    def test_a_plan_that_is_gone_is_a_request_that_cannot_be_found(self):
        self.console.store.plans.clear()
        for decision in ("approve", "decline"):
            with self.subTest(decision=decision):
                self.assertEqual(self.console.post("/ok/plan0001", {"decision": decision, "code": "c", "nonce": "n"}).status, 404)
        self.assertEqual((self.decider.calls, self.delegate.begins), ([], []))

    def test_a_decline_goes_to_the_decider_with_the_person_the_plan_the_answer_the_code_the_token_the_note_and_the_reason(self):
        form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        self.console.submit(form, "Decline", note="No, thank you")
        self.assertEqual(self.decider.calls, [dict(oid=TINO, plan_id="plan0001", decision="decline", code="7F3K92QD", nonce=form.fields["nonce"], note="No, thank you", reason="")])
        self.assertEqual(self.delegate.begins, [])
        self.console.submit(self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE), "Decline", reason="handled")
        self.assertEqual(self.decider.calls[-1]["reason"], "handled")


class WhatIsCheckedBeforeAnAnswerGoesOn(unittest.TestCase):
    """The checks that the page makes itself, before the decider or the delegate is asked anything."""

    def setUp(self):
        self.decider = ScriptedDecider()
        self.delegate = ScriptedDelegate()
        self.console = Console(decider=self.decider, delegate=self.delegate)
        self.console.seed()
        self.page = self.console.get("/ok/plan0001")
        (self.main,) = self.page.forms()

    def assert_nothing_was_asked(self):
        self.assertEqual((self.decider.calls, self.delegate.begins, self.delegate.finishes), ([], [], []))

    def test_an_answer_that_is_not_one_of_the_five_is_refused_and_nothing_is_asked(self):
        for decision in ("", "APPROVE", "approve,decline", "delete", "answer"):
            with self.subTest(decision=decision):
                reply = self.console.post("/ok/plan0001", {**self.main.fields, "decision": decision})
                self.assertEqual(reply.status, 400)
                self.assertIn("The form did not say which answer you chose. Nothing was recorded.", reply.content)
        self.assert_nothing_was_asked()

    def test_a_reason_that_is_not_in_the_list_is_refused_with_the_text_kept_and_nothing_is_asked(self):
        reply = self.console.submit(self.main, "Decline", note="my note", reason="because")
        self.assertEqual(reply.status, 400)
        self.assertIn("Choose one of the reasons in the list.", reply.content)
        self.assertEqual(reply.form("/ok/plan0001", has_button=APPROVE).fields["note"], "my note")
        self.assert_nothing_was_asked()

    def test_a_form_with_no_token_is_refused_and_nothing_is_asked(self):
        for action, fields in (("/ok/plan0001", {"decision": "approve", "code": "7F3K92QD"}), ("/ok/plan0001", {"decision": "decline", "code": "7F3K92QD"}),
                               ("/ok/plan0001/ask", {"note": "hm", "code": "7F3K92QD"}), ("/ok/plan0001/not-mine", {"code": "7F3K92QD"}),
                               ("/ok/plan0001", {"decision": "approve", "nonce": ""})):
            with self.subTest(action=action, fields=fields):
                reply = self.console.post(action, fields)
                self.assertEqual(reply.status, 403)
                self.assertIn("This form cannot be used", reply.headings(1))
                self.assertIn("Nothing was changed.", reply.content)
                self.assertNotIn("Location", reply.headers)
        self.assert_nothing_was_asked()

    def test_the_code_goes_to_the_decider_as_the_form_sent_it(self):
        self.console.submit(self.main, "Decline", code="WRONG")
        self.assertEqual(self.decider.calls[0]["code"], "WRONG")
        self.console.post("/ok/plan0001", {"decision": "decline", "nonce": "tok"})
        self.assertEqual(self.decider.calls[1]["code"], "")

    def test_a_note_longer_than_300_characters_is_refused_with_the_text_kept_and_nothing_is_asked(self):
        long = "a" * 301
        for button in ("Decline", APPROVE):
            with self.subTest(button=button):
                reply = self.console.submit(self.main, button, note=long)
                self.assertEqual(reply.status, 400)
                self.assertNotIn("Location", reply.headers)
                self.assertIn("There is a problem", reply.headings(2))
                self.assertIn("The note has 301 characters. The most is 300.", reply.content)
                self.assertEqual(reply.form("/ok/plan0001", has_button=APPROVE).fields["note"], long, "the person's text is still in the box")
                link = [a for a in reply.root.find_all("a") if a.attrs["href"] == "#note"]
                self.assertEqual(len(link), 1, "the list of problems links to the field")
                self.assertIsNotNone(reply.root.find("textarea", id="note"))
        self.assert_nothing_was_asked()
        self.assertEqual(self.console.submit(self.main, "Decline", note="a" * 300).status, 200)
        self.assertEqual(self.decider.calls[0]["note"], "a" * 300)
        self.assertEqual(self.console.submit(self.main, APPROVE, note="a" * 300).status, 303)
        self.assertEqual(self.delegate.begins[0]["note"], "a" * 300)

    def test_ask_or_tell_needs_text_of_at_most_300_characters(self):
        for note, message in (("", "Write your question, your objection or what to remember."), ("a" * 301, "The note has 301 characters. The most is 300.")):
            with self.subTest(length=len(note)):
                reply = self.console.submit(self.main, "Ask or tell", note=note)
                self.assertEqual(reply.status, 400)
                self.assertIn(message, reply.content)
                self.assert_nothing_was_asked()
        reply = self.console.submit(self.main, "Ask or tell", note="Is it the standby disk?")
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.decider.calls, [dict(oid=TINO, plan_id="plan0001", decision="ask", code="7F3K92QD", nonce=self.main.fields["nonce"], note="Is it the standby disk?",
                                                   reason="")])
        self.assertEqual(self.delegate.begins, [])

    def test_not_mine_and_later_go_to_the_decider_with_what_they_need(self):
        self.decider.result = DecideResult(True, "not_mine", "ok", make_plan())
        self.console.submit(self.main, "This is not mine")
        self.assertEqual(self.decider.calls, [dict(oid=TINO, plan_id="plan0001", decision="not_mine", code="7F3K92QD", nonce=self.main.fields["nonce"], note="", reason="")])
        self.decider.result = DecideResult(True, "later", "ok", make_plan())
        self.console.submit(self.main, "Decide later")
        self.assertEqual(self.decider.calls[-1]["decision"], "later")
        self.assertEqual(self.delegate.begins, [])

    def test_the_older_addresses_of_the_question_and_of_not_mine_answer_like_the_buttons(self):
        self.decider.result = DecideResult(True, "asked", "ok", make_plan())
        reply = self.console.post("/ok/plan0001/ask", {**self.main.fields, "note": "a question"})
        self.assertEqual(reply.status, 200)
        self.decider.result = DecideResult(True, "not_mine", "ok", make_plan())
        self.console.post("/ok/plan0001/not-mine", dict(self.main.fields))
        self.assertEqual([(c["decision"], c["note"]) for c in self.decider.calls], [("ask", "a question"), ("not_mine", "")])

    def test_the_note_is_cleaned_of_control_characters_before_it_goes_on(self):
        for decision in ("decline", "approve"):
            self.console.post("/ok/plan0001", {**self.main.fields, "decision": decision, "confirm": "yes", "note": "line one\r\nline\ttwo\x00"})
        self.assertEqual(self.decider.calls[0]["note"], "line one line two")
        self.assertEqual(self.delegate.begins[0]["note"], "line one line two")

    def test_an_approval_from_another_site_a_form_that_is_not_a_form_and_one_that_is_too_large_are_refused_before_the_delegate(self):
        before = snapshot(self.console.store)
        fields = {**self.main.fields, "decision": "approve"}
        self.assertEqual(self.console.send("POST", "/ok/plan0001", form=fields, headers={"Sec-Fetch-Site": "cross-site"}).status, 403)
        self.assertEqual(self.console.send("POST", "/ok/plan0001", body="decision=approve", content_type="text/plain").status, 415)
        self.assertEqual(self.console.post("/ok/plan0001", body=b"decision=approve&note=" + b"a" * 20000).status, 413)
        self.assert_nothing_was_asked()
        self.assertEqual(snapshot(self.console.store), before)


class TheConfirmationOfAChangeThatCannotBeUndone(unittest.TestCase):
    """Approving a change that cannot be undone (a delete) asks once more, on a page of its own, before the sign-in to Azure starts. The safe button is the main one."""

    YES = "Yes, delete it and sign in to Azure"

    def setUp(self):
        self.delegate = ScriptedDelegate()
        self.console = Console(delegate=self.delegate)
        self.console.seed()
        self.form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        self.reply = self.console.submit(self.form, APPROVE, confirm=False, note="Go on")

    def second_form(self, reply=None):
        return (reply or self.reply).form("/ok/plan0001", has_button=self.YES)

    def test_approving_a_delete_shows_a_page_that_asks_once_more_and_starts_no_sign_in(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), ["Confirm: Delete the unattached disk planted-disk-1"])
        self.assertEqual(self.reply.root.find("title").text(), "Confirm: Delete the unattached disk planted-disk-1 - Meternaut")
        self.assertNotIn("Location", self.reply.headers)
        self.assertEqual((self.delegate.begins, self.delegate.finishes), ([], []))
        self.assertEqual(self.console.store.plan_get("plan0001").state, "open")
        self.assertEqual(self.console.store.decisions_of_plan("plan0001"), [])

    def test_it_says_what_is_lost_who_does_it_and_that_it_cannot_be_undone_without_a_question_mark(self):
        main = self.reply.main
        self.assertEqual([p.text() for p in main.find_all("p", class_="notice-title")], ["This cannot be undone"])
        self.assertIn("If something still uses the disk, that use stops, and the data on it is lost for good. Risk: medium.", main.find("div", class_="notice warning").text())
        found = {dt.text(): dd.text() for dl in main.find_all("dl", class_="summary") for div in dl.find_all("div") for dt, dd in [(div.find("dt"), div.find("dd"))]}
        self.assertEqual(list(found), ["What changes", "Who does it", "Checked again"], "the undo and the risk are said once, in the notice")
        self.assertEqual(found["What changes"], "Deletes the disk planted-disk-1 in resource group meternaut-test-rg. Nothing else changes.")
        self.assertIn("Managed disk planted-disk-1, resource group meternaut-test-rg, subscription bbbbbbbb.", main.text())
        self.assertIn("This change cannot be undone. Nothing is changed until you confirm here and sign in to Azure.", main.text())
        self.assertNotIn("?", main.text())

    def test_the_safe_button_is_the_main_one_and_it_is_a_plain_link_back_to_the_request(self):
        (back,) = [a for a in self.reply.main.find_all("a") if a.text() == "No, go back"]
        self.assertEqual((back.attrs["href"], back.classes()), ("/ok/plan0001", ["btn", "primary"]))
        (yes,) = self.second_form().node.find_all("button")
        self.assertEqual((yes.text(), yes.classes(), yes.attrs["name"], yes.attrs["value"]), (self.YES, ["danger"], "decision", "approve"))
        self.assertEqual(self.console.get("/ok/plan0001").status, 200)
        self.assertEqual((self.delegate.begins, self.console.store.decisions_of_plan("plan0001")), ([], []))

    def test_the_form_carries_what_the_first_form_carried_and_the_word_that_the_person_saw_this_page(self):
        second = self.second_form()
        self.assertEqual((second.action, second.method), ("/ok/plan0001", "post"))
        self.assertEqual(second.fields, {"code": "7F3K92QD", "nonce": self.form.fields["nonce"], "note": "Go on", "confirm": "yes"})

    def test_confirming_starts_the_sign_in_with_the_same_code_token_and_note(self):
        reply = self.console.submit(self.second_form(), self.YES, confirm=False)
        self.assertEqual((reply.status, reply.headers["Location"]), (303, SIGNIN_URL))
        self.assertEqual(self.delegate.begins, [dict(oid=TINO, plan_id="plan0001", code="7F3K92QD", nonce=self.form.fields["nonce"], note="Go on", hint="someone@example.com")])

    def test_only_the_word_yes_counts(self):
        for value in ("", "no", "true", "1", "YES"):
            with self.subTest(confirm=value):
                reply = self.console.post("/ok/plan0001", {**self.form.fields, "decision": "approve", "confirm": value})
                self.assertEqual(reply.headings(1), ["Confirm: Delete the unattached disk planted-disk-1"])
        self.assertEqual(self.delegate.begins, [])

    def test_a_change_that_can_be_undone_goes_straight_to_the_sign_in_and_every_delete_asks_first(self):
        for family, asks in (("stop-vm", False), ("resize-vm", False), ("change-disk-tier", False), ("delete-disk", True), ("delete-public-ip", True), ("delete-idle-resource", True)):
            with self.subTest(family=family):
                delegate = ScriptedDelegate()
                console = Console(delegate=delegate)
                console.seed()
                console.store.plan_put(make_plan(family=family))
                form = console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
                reply = console.submit(form, APPROVE, confirm=False)
                if asks:
                    self.assertEqual(reply.status, 200)
                    self.assertTrue(reply.headings(1)[0].startswith("Confirm: "), reply.headings(1))
                    self.assertEqual(delegate.begins, [])
                else:
                    self.assertEqual((reply.status, reply.headers["Location"]), (303, SIGNIN_URL))
                    self.assertEqual(len(delegate.begins), 1)

    def test_the_other_answers_to_a_delete_never_ask_again(self):
        for button in ("Decline", "This is not mine", "Decide later"):
            with self.subTest(button=button):
                self.assertNotIn("Confirm:", self.console.submit(self.form, button, confirm=False).headings(1)[0])

    def test_a_change_that_is_held_by_a_switch_is_refused_by_the_sign_in_step_as_before_and_not_confirmed_first(self):
        self.console.store.switch_put(SwitchRecord("changes", True, "Otto", at(minutes=-5), "drill"))
        reply = self.console.post("/ok/plan0001", {**self.form.fields, "decision": "approve"})
        self.assertNotIn("Confirm:", reply.text)
        self.assertEqual(len(self.delegate.begins), 1, "the sign-in step is reached and refuses it in its own words (here the stand-in lets it through, which is not the point)")

    def test_a_person_who_may_not_answer_gets_the_refusal_and_never_the_page(self):
        for who in (MAYA, STRANGER):
            with self.subTest(who=who):
                reply = self.console.post("/ok/plan0001", {**self.form.fields, "decision": "approve"}, oid=who)
                self.assertEqual(reply.status, 403)
                self.assertNotIn("Confirm:", reply.text)

    def test_what_comes_from_the_estate_is_escaped_and_the_page_has_no_style_attribute_and_no_script(self):
        hostile = '<img src=x onerror=alert(1)>'
        self.console.store.case_put(make_case(plan_id="plan0001", resource_name=hostile))
        self.console.store.plan_put(make_plan(resource_name=hostile, title=f"Delete the unattached disk {hostile}"))
        form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        reply = self.console.submit(form, APPROVE, confirm=False, note=hostile)
        self.assertEqual(reply.status, 200)
        self.assertNotIn(hostile, reply.text)
        self.assertEqual([n.tag for n in reply.root.walk() if n.tag in ("script", "img", "iframe")], [])
        self.assertNotIn(" style=", reply.text)

    def test_the_page_changes_nothing_and_has_the_headers_of_every_page(self):
        before = snapshot(self.console.store)
        self.console.submit(self.form, APPROVE, confirm=False)
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual({name: self.reply.headers.get(name) for name in layout.SECURITY_HEADERS}, layout.SECURITY_HEADERS)
        self.assertIn("Recommendations written by AI. A person approves every change.", self.reply.content)


class TheSignInRedirect(unittest.TestCase):
    """Approving sends the person to the sign-in to Azure. The page records nothing and changes nothing: the approval is made when the person comes back."""

    def setUp(self):
        self.decider = ScriptedDecider()
        self.delegate = ScriptedDelegate()
        self.console = Console(decider=self.decider, delegate=self.delegate)
        self.console.seed()
        self.form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)

    def test_the_delegate_begins_the_sign_in_with_the_person_the_plan_the_code_the_token_the_note_and_the_hint(self):
        self.console.submit(self.form, APPROVE, note="Go on")
        self.assertEqual(self.delegate.begins, [dict(oid=TINO, plan_id="plan0001", code="7F3K92QD", nonce=self.form.fields["nonce"], note="Go on", hint="someone@example.com")])
        self.assertEqual(self.delegate.finishes, [])

    def test_an_approval_is_never_decided_by_the_decider(self):
        self.console.submit(self.form, APPROVE)
        self.console.submit(self.form, APPROVE, note="again")
        self.assertEqual(self.decider.calls, [])
        self.assertEqual(len(self.delegate.begins), 2)

    def test_the_answer_is_a_303_to_the_address_that_the_delegate_gave_with_no_body_and_no_caching(self):
        reply = self.console.submit(self.form, APPROVE)
        self.assertEqual(reply.status, 303)
        self.assertEqual(reply.headers["Location"], SIGNIN_URL)
        self.assertEqual(reply.headers["Cache-Control"], "no-store")
        self.assertEqual(reply.body, b"")
        self.assertEqual({name: reply.headers.get(name) for name in layout.SECURITY_HEADERS}, layout.SECURITY_HEADERS, "the redirect has every security header of a page")
        self.assertIn("form-action 'self' https://login.microsoftonline.com;", reply.headers["Content-Security-Policy"])

    def test_the_address_is_the_one_that_the_delegate_gave_and_is_not_made_by_the_page(self):
        address = "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?state=another&login_hint=a%40b.example"
        self.delegate.begun = Begun(location=address)
        reply = self.console.submit(self.form, APPROVE)
        self.assertEqual((reply.status, reply.headers["Location"]), (303, address))

    def test_the_page_records_nothing_and_changes_nothing(self):
        before = snapshot(self.console.store)
        self.console.submit(self.form, APPROVE, note="Go on")
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(self.console.store.plan_get("plan0001").state, "open")
        self.assertEqual(self.console.store.decisions_of_plan("plan0001"), [])
        self.assertIsNone(self.console.store.action_get("plan0001"))

    def test_the_code_goes_on_as_the_form_sent_it(self):
        self.console.submit(self.form, APPROVE, code="WRONG")
        self.console.post("/ok/plan0001", {"decision": "approve", "nonce": "tok", "confirm": "yes"})
        self.assertEqual([call["code"] for call in self.delegate.begins], ["WRONG", ""])
        self.assertEqual(self.delegate.begins[1]["nonce"], "tok")

    def test_the_hint_is_the_name_in_the_header_of_the_platform_and_never_a_field_of_the_form(self):
        self.console.submit(self.form, APPROVE, **{"x-ms-client-principal-name": "evil@example.com", "hint": "evil@example.com", "login_hint": "evil@example.com"})
        fields = {**self.form.fields, "decision": "approve", "confirm": "yes"}
        self.console.send("POST", "/ok/plan0001", form=fields, oid=None, headers={"x-ms-client-principal-id": TINO, "x-ms-client-principal-name": "tino@example.com"})
        self.console.send("POST", "/ok/plan0001", form=fields, oid=None, headers={"x-ms-client-principal-id": TINO})
        self.assertEqual([call["hint"] for call in self.delegate.begins], ["someone@example.com", "tino@example.com", ""])

    def test_only_an_approval_goes_to_the_delegate(self):
        self.console.submit(self.form, "Decline")
        self.console.submit(self.console.get("/ok/plan0001").form("/ok/plan0001"), "Ask or tell", note="Is it the standby disk?")
        self.console.submit(self.console.get("/ok/plan0001").form("/ok/plan0001"), "This is not mine")
        self.console.submit(self.console.get("/ok/plan0001").form("/ok/plan0001"), "Decide later")
        self.assertEqual([call["decision"] for call in self.decider.calls], ["decline", "ask", "not_mine", "later"])
        self.assertEqual((self.delegate.begins, self.delegate.finishes), ([], []))

    def test_a_refusal_from_begin_is_the_page_of_its_kind_with_no_redirect_and_changes_nothing(self):
        before = snapshot(self.console.store)
        refusals = ("refused_code", "refused_state", "refused_role", "refused_paused", "expired", "duplicate", "error")
        for kind in refusals:
            with self.subTest(kind=kind):
                self.delegate.begun = Begun(refusal=DecideResult(False, kind, "a message of the delegate", make_plan()))
                reply = self.console.submit(self.form, APPROVE)
                status, title, _ = KINDS[kind]
                self.assertEqual((reply.status, reply.headings(1)), (status, [title]))
                self.assertNotIn("Location", reply.headers)
        self.assertEqual(len(self.delegate.begins), len(refusals))
        self.assertEqual(self.decider.calls, [])
        self.assertEqual(snapshot(self.console.store), before)

    def test_a_begin_with_an_address_that_is_not_the_sign_in_of_microsoft_entra_is_an_error_page_and_no_redirect(self):
        elsewhere = ("https://login.example.test/tenant/oauth2/v2.0/authorize?state=x", "http://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?state=x",
                     "https://login.microsoftonline.com.evil.example/tenant/oauth2/v2.0/authorize", "//login.microsoftonline.com/tenant/oauth2/v2.0/authorize",
                     "https://login.microsoftonline.com@evil.example/x", "https://login.microsoftonline.com/tenant/authorize?state=x\r\nSet-Cookie: a=b",
                     "https://login.microsoftonline.com/tenant/authorize?redirect=https://evil.example", "javascript:alert(1)", "/ok/plan0001", "https://login.microsoftonline.com/")
        for address in elsewhere:
            with self.subTest(address=address):
                self.delegate.begun = Begun(location=address)
                reply = self.console.submit(self.form, APPROVE)
                self.assertEqual((reply.status, reply.headings(1)), (500, ["I could not take your answer"]))
                self.assertNotIn("Location", reply.headers)
                self.assertNotIn("evil.example", reply.text)

    def test_a_begin_that_gives_neither_an_address_nor_a_refusal_is_an_error_page(self):
        for begun in (Begun(), Begun(location=""), Begun(location="", refusal=None)):
            with self.subTest(begun=repr(begun)):
                self.delegate.begun = begun
                reply = self.console.submit(self.form, APPROVE)
                self.assertEqual((reply.status, reply.headings(1)), (500, ["I could not take your answer"]))
                self.assertNotIn("Location", reply.headers)

    def test_a_begin_that_raises_is_an_error_page_without_a_trace_and_changes_nothing(self):
        before = snapshot(self.console.store)
        for error in (RuntimeError("boom with a secret detail"), StoreError("the store is down", 503), ValueError("bad value")):
            with self.subTest(error=repr(error)):
                self.delegate.begun = error
                reply = self.console.submit(self.form, APPROVE)
                self.assertEqual((reply.status, reply.headings(1)), (500, ["I could not take your answer"]))
                self.assertIn("The approval service did not answer.", reply.content)
                for leak in ("boom", "the store is down", "bad value", "Traceback"):
                    self.assertNotIn(leak, reply.text)
                self.assertNotIn("Location", reply.headers)
        self.assertEqual(snapshot(self.console.store), before)

    def test_a_begin_that_gives_something_that_is_not_a_begun_is_a_plain_error_page(self):
        for begun in (None, "text"):
            with self.subTest(begun=repr(begun)):
                self.delegate.begun = begun
                reply = self.console.submit(self.form, APPROVE)
                self.assertEqual(reply.status, 500)
                self.assertNotIn("Location", reply.headers)
                self.assertNotIn("Traceback", reply.text)


class TheReturnFromTheSignIn(unittest.TestCase):
    """The page that the sign-in sends the person back to. The delegate records the approval and makes the change; the page shows the result."""

    def setUp(self):
        self.decider = ScriptedDecider()
        self.delegate = ScriptedDelegate()
        self.console = Console(decider=self.decider, delegate=self.delegate)
        self.console.seed()

    def test_the_delegate_finishes_the_sign_in_with_the_person_and_the_query_as_it_came(self):
        reply = self.console.get("/arm/return", query=RETURN)
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.delegate.finishes, [dict(oid=TINO, query=RETURN)])
        self.assertEqual((self.delegate.begins, self.decider.calls), ([], []))

    def test_an_error_of_the_sign_in_goes_on_with_its_text_on_one_line(self):
        description = "AADSTS65004: The user declined to consent to access the app.\r\nTrace ID: 0b0c\r\nCorrelation ID: 7e1f\r\nTimestamp: 2026-11-05 08:00:00Z"
        self.console.get("/arm/return", query={"state": STATE, "error": "access_denied", "error_description": description})
        self.assertEqual(self.delegate.finishes[0]["query"], {"state": STATE, "error": "access_denied", "error_description":
                         "AADSTS65004: The user declined to consent to access the app. Trace ID: 0b0c Correlation ID: 7e1f Timestamp: 2026-11-05 08:00:00Z"})

    def test_only_plain_names_go_on_and_a_name_that_comes_twice_is_joined(self):
        self.console.get("/arm/return?state=a&state=b&bad%20name=1&ok-name=2&%3Cb%3E=3")
        self.assertEqual(self.delegate.finishes[0]["query"], {"state": "a,b", "ok-name": "2"})

    def test_a_return_with_no_query_goes_on_as_an_empty_query(self):
        self.console.get("/arm/return")
        self.assertEqual(self.delegate.finishes, [dict(oid=TINO, query={})])

    def test_a_person_who_is_not_listed_gets_the_denial_and_the_delegate_is_not_asked(self):
        denial = self.console.get("/", oid=None)
        for who in (None, STRANGER):
            with self.subTest(who=who):
                reply = self.console.get("/arm/return", query=RETURN, oid=who)
                self.assertEqual((reply.status, reply.text), (denial.status, denial.text))
                self.assertEqual(reply.content, "No access This account cannot open this page.")
        self.assertEqual(self.delegate.finishes, [])

    def test_a_listed_person_needs_no_role_to_come_back_and_the_delegate_decides_what_the_return_is_worth(self):
        for who in (OWNER, OPS, MAYA):
            with self.subTest(who=who):
                reply = self.console.get("/arm/return", query=RETURN, oid=who)
                self.assertEqual((reply.status, reply.headings(1)), (200, ["The change was made"]))
        nobody = "44444444-5555-6666-7777-888888888888"
        roleless = Console(people=People((Person(nobody, "Nobody", (), ""),)), delegate=self.delegate)
        self.assertEqual(roleless.get("/arm/return", query=RETURN, oid=nobody).status, 200)
        self.assertEqual([call["oid"] for call in self.delegate.finishes], [OWNER, OPS, MAYA, nobody])

    def test_a_return_that_the_sign_in_sends_from_another_site_is_taken(self):
        headers = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        reply = self.console.get("/arm/return", query=RETURN, headers=headers)
        self.assertEqual(reply.status, 200)
        self.assertEqual(len(self.delegate.finishes), 1)

    def test_only_get_is_taken_and_a_head_request_does_not_finish_a_sign_in(self):
        post = self.console.post("/arm/return", dict(RETURN))
        self.assertEqual((post.status, post.headers["Allow"]), (405, "GET"))
        for method in ("PUT", "PATCH", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                reply = self.console.send(method, "/arm/return", query=RETURN)
                self.assertEqual((reply.status, reply.headers["Allow"]), (405, "GET, HEAD, POST"))
        head = self.console.send("HEAD", "/arm/return", query=RETURN)
        self.assertEqual((head.status, head.headers["Allow"], head.body), (405, "GET", b""))
        self.assertEqual(head.headers["Cache-Control"], "no-store")
        self.assertEqual(self.delegate.finishes, [], "a HEAD request (a prefetch, a link check) cannot use up a sign-in")
        self.assertEqual(self.console.send("HEAD", "/history").status, 200, "the pages that only show something still answer HEAD")

    def test_the_head_request_of_a_page_that_only_shows_something_has_its_status_and_headers_and_no_body(self):
        get = self.console.get("/history")
        head = self.console.send("HEAD", "/history")
        self.assertEqual((head.status, head.body), (get.status, b""))
        self.assertEqual(head.headers["Cache-Control"], "no-store")
        self.assertEqual(head.headers["Content-Security-Policy"], get.headers["Content-Security-Policy"])

    def test_the_page_shows_nothing_of_the_query_and_nothing_of_the_address_of_the_sign_in(self):
        query = {**RETURN, "error": "access_denied", "error_description": "AADSTS70000: details of the error"}
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.delegate.finished = DecideResult(kind in SUCCESSES, kind, "a message of the result", make_plan())
                reply = self.console.get("/arm/return", query=query)
                for value in (CODE, STATE, "a-session-state", "AADSTS70000", "details of the error", "access_denied", SIGNIN_URL, "login.example.test"):
                    self.assertNotIn(value, reply.text)

    def test_the_page_changes_nothing_by_itself_and_is_never_cached(self):
        before = snapshot(self.console.store)
        reply = self.console.get("/arm/return", query=RETURN)
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(reply.headers["Cache-Control"], "no-store")


STEP_UP_ADDRESS = ("https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?state=second-state&claims="
                   "%7B%22access_token%22%3A%7B%22acrs%22%3A%7B%22essential%22%3Atrue%2C%22value%22%3A%22c-unique-4711%22%7D%7D%7D")


class TheReturnThatAsksForAnExtraCheck(unittest.TestCase):
    """Azure asked the approver for an extra sign-in check: the result of the return holds the address of the sign-in, and the page is a redirect to it."""

    def setUp(self):
        self.delegate = ScriptedDelegate()
        self.console = Console(delegate=self.delegate)
        self.console.seed()

    def step_up(self, location=STEP_UP_ADDRESS, kind="step_up", plan=True):
        self.delegate.finished = DecideResult(False, kind, "Azure asks for an extra sign-in check.", make_plan() if plan else None, location)
        return self.console.get("/arm/return", query=RETURN)

    def test_the_answer_is_a_303_to_the_address_that_the_delegate_gave_with_no_body_and_no_caching(self):
        reply = self.step_up()
        self.assertEqual((reply.status, reply.headers["Location"], reply.body), (303, STEP_UP_ADDRESS, b""))
        self.assertEqual(reply.headers["Cache-Control"], "no-store")
        self.assertEqual(len(self.delegate.finishes), 1)
        self.assertEqual(self.delegate.begins, [])

    def test_the_redirect_has_every_security_header_and_the_policy_is_what_it_was(self):
        reply = self.step_up()
        self.assertEqual({name: reply.headers.get(name) for name in layout.SECURITY_HEADERS}, layout.SECURITY_HEADERS)
        self.assertEqual(reply.headers["Content-Security-Policy"],
                         "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://login.microsoftonline.com; frame-ancestors 'none'; base-uri 'none'")
        self.assertEqual(layout.CSP, reply.headers["Content-Security-Policy"])

    def test_it_is_the_same_redirect_whether_the_result_holds_a_plan_or_not(self):
        self.assertEqual(self.step_up(plan=False).headers["Location"], STEP_UP_ADDRESS)
        self.assertEqual(self.step_up(plan=True).headers["Location"], STEP_UP_ADDRESS)

    def test_the_address_has_to_be_the_sign_in_of_microsoft_entra_by_the_check_of_the_first_sign_in_and_anything_else_is_the_error_page(self):
        elsewhere = ("https://login.example.test/tenant/oauth2/v2.0/authorize?state=x", "http://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?state=x",
                     "https://login.microsoftonline.com.evil.example/tenant/oauth2/v2.0/authorize", "//login.microsoftonline.com/tenant/oauth2/v2.0/authorize",
                     "https://login.microsoftonline.com@evil.example/x", "https://login.microsoftonline.com/tenant/authorize?state=x\r\nSet-Cookie: a=b",
                     "https://login.microsoftonline.com/tenant/authorize?redirect=https://evil.example", "javascript:alert(1)", "/ok/plan0001", "https://login.microsoftonline.com/",
                     "https://login.microsoftonline.com/tenant/authorize?claims={\"a\":1}", "https://login.microsoftonline.com/tenant/authorize?claims=%7B%22a%22:1%7D x")
        for address in elsewhere:
            with self.subTest(address=address):
                reply = self.step_up(address)
                self.assertEqual((reply.status, reply.headings(1)), (500, ["I could not take your answer"]))
                self.assertNotIn("Location", reply.headers)
                self.assertNotIn("evil.example", reply.text)
                self.assertNotIn("Azure asks for an extra sign-in check", reply.text, "the message of a result that is not whole is not shown")

    def test_the_limit_of_the_address_is_the_one_of_the_first_sign_in_and_is_kept_in_one_place(self):
        origin = "https://login.microsoftonline.com/"
        self.assertEqual(self.step_up(origin + "a" * MAX_SIGNIN_PATH).status, 303)
        self.assertEqual(self.step_up(origin + "a" * (MAX_SIGNIN_PATH + 1)).status, 500)
        form = self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        self.delegate.begun = Begun(location=origin + "a" * (MAX_SIGNIN_PATH + 1))
        self.assertEqual(self.console.submit(form, APPROVE).status, 500)
        self.delegate.begun = Begun(location=origin + "a" * MAX_SIGNIN_PATH)
        self.assertEqual(self.console.submit(form, APPROVE).status, 303)
        self.assertEqual(MAX_SIGNIN_PATH, 2000)

    def test_a_result_that_is_not_whole_is_an_error_page_and_not_a_redirect(self):
        for label, kwargs in (("a step-up without an address", {"location": ""}), ("an address on a result that is not a step-up", {"kind": "ran"}),
                              ("an address on a refusal", {"kind": "refused_state"}), ("an address that is not text", {"location": 5}),
                              ("an address that is a list", {"location": [STEP_UP_ADDRESS]})):
            with self.subTest(label):
                reply = self.step_up(**kwargs)
                self.assertEqual((reply.status, reply.headings(1)), (500, ["I could not take your answer"]))
                self.assertNotIn("Location", reply.headers)

    def test_a_result_of_another_kind_without_an_address_is_the_page_of_its_kind(self):
        self.delegate.finished = DecideResult(True, "ran", "Deleted.", make_plan())
        reply = self.console.get("/arm/return", query=RETURN)
        self.assertEqual((reply.status, reply.headings(1)), (200, ["The change was made"]))
        self.assertNotIn("Location", reply.headers)

    def test_nothing_of_the_address_or_the_claims_is_on_any_page(self):
        for kind in ("step_up", "ran", "stopped", "azure_refused", "step_up_failed", "refused_state", "error"):
            with self.subTest(kind=kind):
                reply = self.step_up(kind=kind) if kind == "step_up" else self.step_up(location="", kind=kind)
                for value in ("c-unique-4711", "claims", "second-state", "login.microsoftonline.com/tenant"):
                    self.assertNotIn(value, reply.text)

    def test_a_head_request_cannot_start_the_second_sign_in_either(self):
        self.delegate.finished = DecideResult(False, "step_up", "Azure asks for an extra sign-in check.", make_plan(), STEP_UP_ADDRESS)
        head = self.console.send("HEAD", "/arm/return", query=RETURN)
        self.assertEqual((head.status, head.headers["Allow"], head.body), (405, "GET", b""))
        self.assertNotIn("Location", head.headers)
        self.assertEqual(self.delegate.finishes, [])

    def test_the_redirect_records_nothing_and_changes_nothing_by_itself(self):
        before = snapshot(self.console.store)
        self.step_up()
        self.assertEqual(snapshot(self.console.store), before)

    def test_a_person_who_is_not_listed_is_not_sent_anywhere(self):
        self.delegate.finished = DecideResult(False, "step_up", "x", make_plan(), STEP_UP_ADDRESS)
        reply = self.console.get("/arm/return", query=RETURN, oid=STRANGER)
        self.assertEqual(reply.status, 403)
        self.assertNotIn("Location", reply.headers)
        self.assertEqual(self.delegate.finishes, [])


class AgainstTheLoop(unittest.TestCase):
    """The pages and a small loop over one store, for the answers that change nothing in Azure: the tokens and codes of the forms are the ones that the loop checks."""

    def setUp(self):
        self.console = Console(decider="loop")
        self.console.seed()
        self.console.store.plan_put(make_plan(approvers=(TINO, MAYA)))

    def form(self, who=TINO):
        (form,) = self.console.get("/ok/plan0001", oid=who).forms()
        return form

    def test_a_decline_is_recorded_once_with_its_reason_and_the_same_form_cannot_be_used_twice(self):
        main = self.form()
        self.assertEqual(self.console.submit(main, "Decline", note="Not now", reason="handled").status, 200)
        (record,) = self.console.store.decisions_of_plan("plan0001")
        self.assertEqual((record.decision, record.note, record.reason), ("decline", "Not now", "handled"))
        before = snapshot(self.console.store)
        second = self.console.submit(main, "Decline")
        self.assertEqual(second.status, 500)
        self.assertIn("This form is no longer valid.", second.content)
        self.assertEqual(snapshot(self.console.store), before)

    def test_a_wrong_code_is_refused_and_changes_nothing(self):
        main = self.form()
        before = snapshot(self.console.store)
        reply = self.console.submit(main, "Decline", code="AAAAAAAA")
        self.assertEqual(reply.status, 409)
        self.assertIn("This request changed. Nothing is approved. A new message will bring the new request and its code.", reply.content)
        self.assertEqual(snapshot(self.console.store), before)

    def test_a_missing_or_wrong_token_changes_nothing(self):
        main = self.form()
        before = snapshot(self.console.store)
        for token in ("", "nope", "x" * 32):
            reply = self.console.submit(main, "Decline", nonce=token)
            self.assertIn(reply.status, (403, 500))
        self.assertEqual(snapshot(self.console.store), before)

    def test_a_token_of_another_person_or_another_plan_is_refused(self):
        main = self.form(TINO)
        self.console.store.plan_put(make_plan(plan_id="plan0002", approvers=(TINO,)))
        (other,) = self.console.get("/ok/plan0002").forms()
        before = snapshot(self.console.store)
        reply = self.console.submit(main, "Decline", oid=MAYA)
        self.assertEqual(reply.status, 500)
        self.assertEqual(snapshot(self.console.store), before)
        reply = self.console.post("/ok/plan0001", {**main.fields, "decision": "decline", "nonce": other.fields["nonce"]})
        self.assertEqual(reply.status, 500)
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(self.console.submit(main, "Decline").status, 200, "the right person with the right token still can")

    def test_an_approval_never_reaches_the_loop_and_records_nothing(self):
        main = self.form()
        before = snapshot(self.console.store)
        reply = self.console.submit(main, APPROVE, note="Go on")
        self.assertEqual(reply.status, 303)
        self.assertEqual(self.console.decider.calls, 0)
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(self.console.store.plan_get("plan0001").state, "open")

    def test_a_decline_closes_the_request_and_the_page_shows_it(self):
        reply = self.console.submit(self.form(), "Decline", note="Not now")
        self.assertEqual(reply.headings(1), ["Declined"])
        self.assertEqual(self.console.store.plan_get("plan0001").state, "declined")
        page = self.console.get("/ok/plan0001")
        self.assertEqual(page.forms(), [])
        self.assertIn("Declined by Tino.", page.content)

    def test_asking_or_telling_leaves_the_request_open_and_is_shown_to_the_person_who_wrote_it(self):
        reply = self.console.submit(self.form(), "Ask or tell", note="Is it the standby disk?")
        self.assertEqual(reply.headings(1), ["Recorded: your words"])
        self.assertIn("The request stays open until Sun 8 Nov 2026 08:00 UTC", reply.content)
        page = self.console.get("/ok/plan0001")
        self.assertEqual(len(page.forms()), 1)
        self.assertIn("Is it the standby disk?", page.content)
        self.assertNotIn("Is it the standby disk?", self.console.get("/ok/plan0001", oid=MAYA).content)

    def test_later_leaves_the_request_open_and_a_second_answer_is_still_possible(self):
        reply = self.console.submit(self.form(), "Decide later")
        self.assertEqual(reply.headings(1), ["Noted"])
        self.assertEqual(self.console.store.plan_get("plan0001").state, "open")
        page = self.console.get("/ok/plan0001")
        self.assertIn("You chose to decide later. Nothing has changed.", page.content)
        self.assertEqual(self.console.submit(page.forms()[0], "Decline").status, 200)
        self.assertEqual(self.console.store.plan_get("plan0001").state, "declined")

    def test_not_mine_closes_the_request_for_the_person(self):
        reply = self.console.submit(self.form(), "This is not mine")
        self.assertEqual(reply.headings(1), ["Recorded: not yours"])
        self.assertEqual(self.console.store.plan_get("plan0001").state, "withdrawn")


if __name__ == "__main__":
    unittest.main()
