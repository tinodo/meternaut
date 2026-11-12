"""The page of a request when the checks of the runner would refuse the change (cases/precheck.py), and the page of what came of an approval that was refused.

The page looks at the resource before it offers Approve, with the same code that the runner uses right before the change. These tests use a real plan of the family, the real look and the real
fake of Azure (familysupport), behind the real pages: a person who is offered a button must not be sent to sign in for a change that will be refused.
"""
import dataclasses
import unittest

import familysupport as fs
from test_web_support import MAYA, TINO, Console, ScriptedDecider, ScriptedDelegate, at, make_action, make_advice, make_advice_case, make_decision, make_plan, snapshot
from test_web_approval import RETURN

from cases.models import READY, REFUSED, UNKNOWN, ActionRecord, DecideResult, Readiness
from cases.precheck import Precheck

APPROVE = "Approve"
NOT_NOW = "Meternaut will not change this disk now"
TAG_REASON = "It no longer carries the test tag meternaut-planted, so it cannot be told apart from a real disk. Nothing was changed."
NEXT = ("What happens next: Meternaut looks again every time this page opens, and offers Approve again when the change can be made. "
        "Until then you can decline this request, decide later, or ask or tell.")
COULD_NOT_LOOK = "Meternaut could not look at the disk just now, so it cannot say whether the change can be made."
LOOKS_AGAIN = "It looks again right before it acts, and it changes nothing if a check fails."
LAST_TIME = "Meternaut did not make this change last time"
RECORDED = "Meternaut did not change the disk: it no longer carries the test tag meternaut-planted, so it cannot be told apart from a real disk. Nothing was changed."


class ScriptedChecker:
    """Answers what a test says and keeps the plans that it was asked about."""

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def check(self, plan):
        self.asked.append(plan.plan_id)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def boxes(reply):
    """The boxes of the page, each as (its kind, its title or "", the text of its lines)."""
    found = []
    for node in reply.main.find_all("div"):
        if "notice" in node.classes():
            title = node.find("p", class_="notice-title")
            text = node.text()
            found.append(([c for c in node.classes() if c != "notice"][0], title.text() if title is not None else "", text.replace(title.text(), "", 1).strip() if title is not None else text))
    return found


def buttons(reply):
    return [label for form in reply.forms() for _, _, label in form.buttons]


class OnARealPlan(unittest.TestCase):
    """A planted disk, its plan as the approvals make it, and the pages of a console that looks at the disk (not a stand-in)."""

    def setUp(self):
        self.world = fs.World()
        self.disk = self.world.arm.add(fs.disk(sku="StandardSSD_LRS"))
        self.plan = self.world.plan(self.disk, "disk", "delete", cost=50.0, detector="orphan-managed-disk")
        self.assertIsNotNone(self.plan)
        self.console = Console(decider=ScriptedDecider(), delegate=ScriptedDelegate())
        self.console.now = fs.NOW
        self.console.store.case_put(self.world.store.case_get(self.plan.case_id))
        self.console.store.plan_put(self.plan)
        self.look = Precheck(self.console.store, self.world.settings, lambda: self.world.reader, lambda: self.console.now)
        self.use(self.look)
        self.url = f"/ok/{self.plan.plan_id}"

    def use(self, checker):
        self.console.services = dataclasses.replace(self.console.services, checker=checker)

    def strip(self):
        """What the outside job does at night: every tag but its own is gone."""
        self.disk["tags"] = {"left-by-the-job": "Ignore"}

    def box_of_the_look(self, reply):
        (found,) = [box for box in boxes(reply) if box[1] == NOT_NOW]
        return found


class ThePageOfAChangeThatWouldBeRefused(OnARealPlan):
    def test_a_disk_that_has_lost_its_tag_gets_a_box_at_the_top_and_no_approve_button(self):
        self.strip()
        reply = self.console.get(self.url)
        self.assertEqual((reply.status, reply.problems), (200, []))
        self.assertEqual(self.box_of_the_look(reply), ("warning", NOT_NOW, f"{TAG_REASON} {NEXT}"))
        self.assertFalse(reply.has_button(APPROVE))
        self.assertEqual(buttons(reply), ["Decline", "This is not mine", "Ask or tell", "Decide later"], "the answers that approve nothing are all that is left")
        self.assertNotIn("Approve", " ".join(buttons(reply)))

    def test_the_box_is_above_the_card_of_the_change_and_the_card_says_what_the_change_would_do_and_not_what_an_approval_would_do(self):
        self.strip()
        reply = self.console.get(self.url)
        order = [node for node in reply.main.walk() if node.tag == "h2" or "notice" in node.classes()]
        names = [node.text() if node.tag == "h2" else "box" for node in order]
        self.assertEqual(names[0], "box", "the box is the first thing under the title")
        self.assertIn("What the change would do", reply.headings(2))
        self.assertNotIn("If you approve", reply.headings(2))

    def test_the_page_says_nothing_of_a_sign_in_and_says_who_makes_the_change_once(self):
        self.strip()
        main = self.console.get(self.url).main
        self.assertNotRegex(main.text(), r"(?i)\bsign(?:s|ed|ing)?[ -]in\b")
        self.assertEqual(main.text().count("own permissions"), 1)
        for word in ("precondition", "gate", "digest", "plan ", "family", "re-check"):
            self.assertNotIn(word, main.text().lower(), word)

    def test_the_look_is_made_now_each_time_the_page_is_opened_and_it_reads_only(self):
        reads = len(self.world.arm.calls)
        self.console.get(self.url)
        self.assertGreater(len(self.world.arm.calls), reads, "the disk is read now")
        self.assertEqual(self.world.arm.writes(), [])
        self.strip()
        self.assertEqual(self.box_of_the_look(self.console.get(self.url))[0], "warning")
        self.disk["tags"] = dict(fs.PLANTED)
        again = self.console.get(self.url)
        self.assertTrue(again.has_button(APPROVE), "when it is put right, Approve is there again")
        self.assertEqual([b for b in boxes(again) if b[1] == NOT_NOW], [])

    def test_a_lock_a_note_and_a_disk_that_is_in_use_are_said_in_the_same_box_in_the_words_of_the_runner(self):
        from cases.models import NoteRecord
        cases = (("a lock", lambda: self.world.arm.locks.update({self.disk["id"].lower(): [{"name": "l"}]}), "The resource or its resource group has a management lock. Nothing was changed."),
                 ("a disk that is attached", lambda: self.disk["properties"].update(diskState="Attached"), "The disk is not unattached any more. Nothing was changed."),
                 ("a note", lambda: self.console.store.note_put(NoteRecord(note_id="n", oid=TINO, kind="do_not_touch", text="no", scope_resource_id=self.disk["id"],
                                                                         expires_at="2099-01-01T00:00:00Z")),
                  "A person marked the resource do-not-touch after the request was made. Nothing was changed."))
        for label, change, reason in cases:
            with self.subTest(label):
                self.setUp()
                change()
                self.assertEqual(self.box_of_the_look(self.console.get(self.url)), ("warning", NOT_NOW, f"{reason} {NEXT}"))

    def test_the_other_answers_are_still_taken_on_that_page(self):
        self.strip()
        reply = self.console.get(self.url)
        form = reply.form(self.url, has_button="Decline")
        self.console.decider.result = DecideResult(True, "declined", "Declined.", self.plan)
        done = self.console.submit(form, "Decline")
        self.assertEqual((done.status, done.headings(1)), (200, ["Declined"]))
        self.assertEqual([(c["decision"], c["plan_id"]) for c in self.console.decider.calls], [("decline", self.plan.plan_id)])

    def test_a_press_of_approve_on_a_page_that_was_opened_before_looks_again_and_sends_nobody_to_sign_in(self):
        opened = self.console.get(self.url)
        form = opened.form(self.url, has_button=APPROVE)
        self.strip()
        pressed = self.console.submit(form, APPROVE, confirm=False)
        self.assertEqual(pressed.status, 409)
        self.assertEqual(self.box_of_the_look(pressed)[0], "warning")
        self.assertFalse(pressed.has_button(APPROVE))
        self.assertNotIn("Location", pressed.headers)
        self.assertEqual((self.console.delegate.begins, self.console.decider.calls), ([], []), "the sign-in was not started, and nothing was recorded")
        self.assertNotIn("Confirm", " ".join(pressed.headings()), "the page that asks once more is not shown for a change that would be refused")

    def test_a_press_of_approve_on_a_page_that_is_still_right_goes_on_as_it_always_did(self):
        opened = self.console.get(self.url)
        form = opened.form(self.url, has_button=APPROVE)
        asked = self.console.submit(form, APPROVE, confirm=False)
        self.assertEqual(asked.status, 200)
        self.assertTrue(any(f.fields.get("confirm") == "yes" for f in asked.forms()), "a delete cannot be undone: the page that asks once more")
        confirmed = self.console.submit(next(f for f in asked.forms() if f.fields.get("confirm") == "yes"), "Yes, delete it")
        self.assertEqual(confirmed.status, 303)
        self.assertEqual(len(self.console.delegate.begins), 1)

    def test_the_page_of_the_notebook_looks_too_and_offers_nothing_that_the_request_page_does_not(self):
        self.strip()
        reply = self.console.get(f"/why/{self.plan.case_id}")
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.box_of_the_look(reply)[0], "warning")
        self.assertFalse(reply.has_button(APPROVE))

    def test_a_look_writes_no_record(self):
        self.strip()
        before = snapshot(self.console.store)
        self.console.get(self.url)
        self.console.get(self.url)
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual((self.console.delegate.begins, self.console.delegate.finishes, self.console.decider.calls), ([], [], []))


class WhenTheLookCannotBeMade(OnARealPlan):
    def test_one_line_says_so_and_approve_stays_because_the_runner_looks_again_with_the_rights_of_the_approver(self):
        self.world.arm.read_status = 500
        reply = self.console.get(self.url)
        self.assertEqual([b for b in boxes(reply) if COULD_NOT_LOOK in b[2]], [("info", "", f"{COULD_NOT_LOOK} {LOOKS_AGAIN}")], "a box with no title: one line")
        self.assertTrue(reply.has_button(APPROVE))
        self.assertEqual([b for b in boxes(reply) if b[1] == NOT_NOW], [])

    def test_a_look_that_fails_in_any_way_never_fails_the_page(self):
        for answer in (RuntimeError("boom"), Readiness(UNKNOWN), "not a readiness", None):
            with self.subTest(answer=repr(answer)):
                self.use(ScriptedChecker(answer))
                reply = self.console.get(self.url)
                self.assertEqual(reply.status, 200)
                self.assertTrue(reply.has_button(APPROVE))
                self.assertNotIn("boom", reply.text)

    def test_without_a_checker_the_page_is_as_it_always_was(self):
        self.strip()
        self.use(None)
        reply = self.console.get(self.url)
        self.assertTrue(reply.has_button(APPROVE))
        self.assertEqual(boxes(reply), [])

    def test_a_press_of_approve_when_the_look_cannot_be_made_goes_on_to_the_runner_which_is_the_guard(self):
        form = self.console.get(self.url).form(self.url, has_button=APPROVE)
        self.world.arm.read_status = 500
        self.assertEqual(self.console.submit(form, APPROVE, confirm=False).status, 200, "the page that asks once more, as for a change that can be made")


class TheLookIsMadeOnlyWhenApproveIsOnOffer(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.console.seed()
        self.checker = ScriptedChecker(Readiness(READY))
        self.console.services = dataclasses.replace(self.console.services, checker=self.checker)

    def test_a_request_that_waits_for_the_person_is_looked_at_once(self):
        reply = self.console.get("/ok/plan0001")
        self.assertEqual((reply.status, self.checker.asked), (200, ["plan0001"]))
        self.assertTrue(reply.has_button(APPROVE))

    def test_nothing_is_looked_at_when_nobody_can_approve(self):
        from cases.models import SwitchRecord
        self.console.store.switch_put(SwitchRecord("changes", True, "Otto", at(minutes=-1), "drill"))
        self.console.get("/ok/plan0001")
        self.console.store.switch_put(SwitchRecord("changes"))
        self.console.get("/ok/plan0001", oid=MAYA)  # not named: the page refuses
        for state in ("approved", "consumed", "declined", "failed", "expired", "withdrawn"):
            self.console.store.plan_put(make_plan(state=state))
            self.console.get("/ok/plan0001")
        self.console.store.case_put(make_advice_case())
        self.console.store.plan_put(make_advice())
        self.console.get("/ok/plan0002")
        self.assertEqual(self.checker.asked, [], "no call is made for a request that cannot be approved now")

    def test_for_two_people_the_first_and_the_second_are_looked_at_and_the_one_who_has_confirmed_is_not(self):
        digest = "d" * 64
        self.console.store.plan_put(make_plan(approval_class="R3", approvers=(TINO, MAYA), digest=digest))
        self.console.get("/ok/plan0001")  # the first of two people: Confirm is on offer
        self.assertEqual(self.checker.asked, ["plan0001"])
        self.console.store.decision_put(make_decision(approver_oid=MAYA, approver_name="Maya", decision="confirm", plan_digest=digest))
        self.console.get("/ok/plan0001")  # the second: Approve is on offer
        self.assertEqual(self.checker.asked, ["plan0001", "plan0001"])
        self.console.get("/ok/plan0001", oid=MAYA)  # the one who confirmed has only Decline and Not mine
        self.assertEqual(self.checker.asked, ["plan0001", "plan0001"])

    def test_the_first_of_two_people_is_not_offered_the_confirmation_of_a_change_that_would_be_refused(self):
        digest = "d" * 64
        self.console.store.plan_put(make_plan(approval_class="R3", approvers=(TINO, MAYA), digest=digest))
        self.checker.answer = Readiness(REFUSED, "it has a management lock")
        reply = self.console.get("/ok/plan0001")
        self.assertEqual(buttons(reply), ["Decline", "This is not mine", "Ask or tell", "Decide later"])
        self.assertEqual([b[1] for b in boxes(reply) if b[1].startswith("Meternaut will not change")], ["Meternaut will not change this disk now"])


class AnOpenRequestThatWasRefusedBefore(unittest.TestCase):
    """After a refusal the request is open and its action is `withdrawn` with the reason: the page says at the top that the last try was refused, unless a look made now says more."""

    def setUp(self):
        self.console = Console()
        self.console.seed()
        self.console.store.action_put(make_action(state="withdrawn", started_at=at(minutes=-3), finished_at=at(minutes=-2), result=RECORDED))
        self.checker = ScriptedChecker(Readiness(READY))
        self.console.services = dataclasses.replace(self.console.services, checker=self.checker)

    def test_when_the_look_cannot_say_the_reason_of_the_last_try_is_at_the_top_with_the_line_that_says_so(self):
        self.checker.answer = Readiness(UNKNOWN)
        reply = self.console.get("/ok/plan0001")
        self.assertEqual([b for b in boxes(reply) if b[1] == LAST_TIME], [("warning", LAST_TIME, f"{RECORDED} {COULD_NOT_LOOK} {LOOKS_AGAIN}")])
        self.assertTrue(reply.has_button(APPROVE), "the request is open: a person may try again, and the runner looks once more")

    def test_when_no_look_is_made_the_reason_of_the_last_try_still_is_at_the_top(self):
        self.console.services = dataclasses.replace(self.console.services, checker=None)
        reply = self.console.get("/ok/plan0001")
        self.assertEqual([b for b in boxes(reply) if b[1] == LAST_TIME], [("warning", LAST_TIME, f"{RECORDED} {LOOKS_AGAIN}")])
        self.assertTrue(reply.has_button(APPROVE))

    def test_when_the_look_finds_nothing_in_the_way_the_old_reason_is_not_at_the_top(self):
        reply = self.console.get("/ok/plan0001")
        self.assertEqual(boxes(reply), [])
        self.assertTrue(reply.has_button(APPROVE))

    def test_when_the_look_refuses_the_box_of_the_look_is_the_only_one(self):
        self.checker.answer = Readiness(REFUSED, "it has a management lock")
        reply = self.console.get("/ok/plan0001")
        self.assertEqual([b[1] for b in boxes(reply)], [NOT_NOW])
        self.assertFalse(reply.has_button(APPROVE))

    def test_the_details_keep_the_record_of_the_try_in_words_and_the_history_lists_it(self):
        reply = self.console.get("/ok/plan0001")
        details = reply.main.find("details")
        self.assertIn("What happened to the change", details.text())
        self.assertIn("Not made: a check refused the change before anything was written. Nothing changed.", details.text())
        self.assertIn(RECORDED, details.text())
        history = self.console.get("/history")
        self.assertIn("Change not made", history.main.text())
        self.assertIn(RECORDED, history.main.text())

    def test_an_action_that_is_not_withdrawn_adds_no_box(self):
        for state in ("queued", "running", "done", "failed"):
            with self.subTest(state):
                self.console.store.action_put(make_action(state=state, result="some words"))
                self.assertEqual(boxes(self.console.get("/ok/plan0001")), [])


class TheResultAfterARefusal(unittest.TestCase):
    """What a person reads when the change was refused right before it: plain words, that nothing was changed, and what they can do next."""

    MESSAGE = RECORDED

    def setUp(self):
        self.delegate = ScriptedDelegate()
        self.console = Console(delegate=self.delegate)
        self.console.seed()

    def result(self, plan=True):
        self.delegate.finished = DecideResult(False, "stopped", self.MESSAGE, make_plan() if plan else None)
        return self.console.get("/arm/return", query=RETURN)

    def test_an_open_request_is_said_to_be_open_and_the_person_is_told_what_they_can_do(self):
        reply = self.result()
        self.assertEqual((reply.status, reply.headings(1)), (409, ["The change was not made"]))
        text = reply.main.text()
        self.assertIn(self.MESSAGE, text)
        self.assertIn("Nothing was changed. The request is still open: you can decline it, decide later, or ask or tell. When what stopped the change is put right, this page offers Approve again.", text)
        self.assertEqual([b[0] for b in boxes(reply)], ["warning"])
        self.assertIn(("/ok/plan0001", "Back to the request"), [(a.attrs["href"], a.text()) for a in reply.main.find_all("a") if a.text().startswith("Back to")])

    def test_the_words_are_plain_and_say_nothing_of_a_sign_in(self):
        text = self.result().main.text()
        self.assertNotRegex(text, r"(?i)\bsign(?:s|ed|ing)?[ -]?in\b")
        for jargon in ("Stopped before the change", "precondition", "gate", "digest", "family", "re-check"):
            self.assertNotIn(jargon, text)

    def test_a_request_that_is_closed_says_so_and_that_a_new_one_is_made_when_the_resource_is_found_again(self):
        self.console.store.plan_put(make_plan(state="failed"))
        text = self.result().main.text()
        self.assertIn("Nothing was changed. The request is closed. A new request is made when Meternaut finds the resource again.", text)
        self.assertNotIn("still open", text)

    def test_a_result_with_no_request_says_where_to_look(self):
        self.console.store.plans.clear()
        text = self.result(plan=False).main.text()
        self.assertIn("Nothing was changed. Open the request to see where it stands.", text)

    def test_the_page_after_the_refusal_is_followed_by_the_request_page_that_shows_it_open(self):
        self.result()
        reply = self.console.get("/ok/plan0001")
        self.assertEqual(reply.status, 200)
        self.assertTrue(reply.has_button(APPROVE) and reply.has_button("Decline"))


if __name__ == "__main__":
    unittest.main()
