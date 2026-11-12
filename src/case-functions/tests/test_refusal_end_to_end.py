"""The owner's story from end to end: the nightly job takes the tag off a planted disk, the page stops offering Approve, and a refusal after the click leaves the request open.

The stack is the one of test_loop_end_to_end.py (the Watch, the plan, the pages, the sign-in, the change with the person's own token), with a planted disk whose tags an outside job can take
off. Nothing here is a stand-in for the check: the page looks at the disk with the app's own reader, and the runner looks again with the person's token.
"""
import json
import unittest

import support  # noqa: F401  (puts the app on the path)
from test_loop_end_to_end import APPROVE, PERSON_TOKEN, Resources, Story, watch

PLANTED = {"meternaut-planted": "demo"}
STRIPPED = {"left-by-the-job": "Ignore"}  # an outside job leaves one tag of its own and nothing else
NOT_NOW = "Meternaut will not change this disk now"
TAG_REASON = "it no longer carries the test tag meternaut-planted, so it cannot be told apart from a real disk"


class StrippedByNight(Resources):
    """The planted disk of the fake Resource Manager, with tags that a test changes: what the outside job does at night is `tags = STRIPPED`."""

    def __init__(self, may_delete):
        super().__init__(may_delete)
        self.tags = dict(PLANTED)

    def __call__(self, method, url, headers, data, timeout):
        status, reply_headers, body = super().__call__(method, url, headers, data, timeout)
        if method == "GET" and status == 200 and body:
            found = json.loads(body)
            found["tags"] = dict(self.tags)
            body = json.dumps(found).encode()
        return status, reply_headers, body


class TheStory(Story):
    def setUp(self):
        super().setUp()
        self.world.resources = StrippedByNight({f"Bearer {PERSON_TOKEN}"})

    def plan_of_the_disk(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        return plan

    def request_page(self, plan):
        self.world.phase = "approval"
        return self.browser.send("GET", f"/ok/{plan.plan_id}")

    def buttons(self, reply):
        return [label for form in reply.forms() for _, _, label in form.buttons]

    def person_calls(self):
        return [c for c in self.world.calls if c[2] == "management.azure.com" and c[4] == f"Bearer {PERSON_TOKEN}"]

    def stored(self, plan):
        return self.store.plan_get(plan.plan_id).state, getattr(self.store.action_get(plan.plan_id), "state", None), self.store.case_get(plan.case_id).status


class WhenTheTagIsGoneBeforeThePageIsOpened(TheStory):
    def test_the_page_says_that_meternaut_will_not_change_the_disk_and_offers_no_approve_and_nobody_signs_in(self):
        plan = self.plan_of_the_disk()
        self.world.resources.tags = dict(STRIPPED)
        page = self.request_page(plan)
        self.assertEqual(page.status, 200)
        text = page.main.text()
        self.assertIn(NOT_NOW, text)
        self.assertIn(f"It {TAG_REASON[3:]}. Nothing was changed.", text)
        self.assertIn("What happens next: Meternaut looks again every time this page opens, and offers Approve again when the change can be made.", text)
        self.assertFalse(page.has_button(APPROVE))
        self.assertEqual(self.buttons(page), ["Decline", "This is not mine", "Ask or tell", "Decide later"])
        self.assertEqual(self.person_calls(), [], "the person has signed in to nothing, and nothing was asked with their token")
        self.assertEqual(self.world.entra.redemptions, [])
        self.assertEqual(self.stored(plan), ("open", None, "awaiting_ok"))
        self.assertTrue(self.world.resources.exists)

    def test_the_look_of_the_page_only_reads_with_the_token_of_the_app(self):
        plan = self.plan_of_the_disk()
        self.world.resources.tags = dict(STRIPPED)
        self.request_page(plan)
        looks = [c for c in self.world.calls if c[0] == "approval" and c[2] == "management.azure.com"]
        self.assertTrue(looks)
        self.assertEqual({c[1] for c in looks}, {"GET"})
        self.assertTrue(all(c[4].startswith("Bearer tok-") for c in looks), "the token of the app's own identity, and not the person's")

    def test_when_the_tag_is_put_back_the_same_request_offers_approve_again_and_the_change_is_made(self):
        plan = self.plan_of_the_disk()
        self.world.resources.tags = dict(STRIPPED)
        self.assertFalse(self.request_page(plan).has_button(APPROVE))
        self.world.resources.tags = dict(PLANTED)  # the action plant puts the tags back
        self.assertTrue(self.request_page(plan).has_button(APPROVE))
        done = self.approve(plan)
        self.assertEqual((done.status, done.headings(1)), (200, ["The change was made"]))
        self.assertFalse(self.world.resources.exists)
        self.assertEqual(self.stored(plan), ("consumed", "done", "done"))


class WhenTheTagIsTakenOffAfterThePageWasShown(TheStory):
    def refused_after_the_click(self, plan):
        self.world.phase = "approval"
        pressed = self.browser.press_approve(plan.plan_id)
        self.assertEqual(pressed.status, 303, "the page looked, found nothing in the way and sent the person to sign in")
        self.world.resources.tags = dict(STRIPPED)  # the outside job runs while the person signs in
        code, state = self.world.entra.sign_in(pressed.headers["Location"])
        return self.browser.send("GET", "/arm/return", query={"code": code, "state": state}), (code, state)

    def test_the_runner_refuses_and_the_result_says_in_plain_words_what_happened_and_what_to_do(self):
        plan = self.plan_of_the_disk()
        refused, _ = self.refused_after_the_click(plan)
        self.assertEqual((refused.status, refused.headings(1)), (409, ["The change was not made"]))
        text = refused.main.text()
        self.assertIn(f"Meternaut did not change the disk: {TAG_REASON}. Nothing was changed.", text)
        self.assertIn("The request is still open: you can decline it, decide later, or ask or tell. When what stopped the change is put right, this page offers Approve again.", text)
        for jargon in ("Stopped before the change", "precondition", "gate", "digest"):
            self.assertNotIn(jargon, text)
        self.assertTrue(self.world.resources.exists)
        self.assertEqual([c[1] for c in self.person_calls() if c[1] != "GET"], [], "nothing was written with the person's token")

    def test_the_request_stays_open_and_its_page_says_why_it_cannot_be_approved_now(self):
        plan = self.plan_of_the_disk()
        self.refused_after_the_click(plan)
        self.assertEqual(self.stored(plan), ("open", "withdrawn", "awaiting_ok"))
        self.assertEqual(self.store.decisions_of_plan(plan.plan_id), [], "the approval was not used")
        page = self.request_page(plan)
        self.assertEqual(page.status, 200)
        self.assertIn(NOT_NOW, page.main.text())
        self.assertFalse(page.has_button(APPROVE))
        self.assertIn("Decline", self.buttons(page))
        self.assertIn("Change not made", self.browser.send("GET", "/history").main.text())

    def test_a_later_approval_works_with_a_new_sign_in_and_the_old_sign_in_never_works_again(self):
        plan = self.plan_of_the_disk()
        _, (code, state) = self.refused_after_the_click(plan)
        again = self.browser.send("GET", "/arm/return", query={"code": code, "state": state})
        self.assertEqual((again.status, again.headings(1)), (409, ["This request cannot take an answer"]), "the state of the refused sign-in is used up")
        self.assertTrue(self.world.resources.exists)
        self.world.resources.tags = dict(PLANTED)
        done = self.approve(plan)
        self.assertEqual((done.status, done.headings(1)), (200, ["The change was made"]))
        self.assertFalse(self.world.resources.exists)
        self.assertEqual(self.stored(plan), ("consumed", "done", "done"))
        self.assertEqual(len(self.world.entra.redemptions), 2, "two approvals, each with a sign-in of its own")
        deletes = [c for c in self.world.calls if c[1] == "DELETE" and c[2] == "management.azure.com"]
        self.assertEqual([c[4] for c in deletes], [f"Bearer {PERSON_TOKEN}"], "one delete, with the person's own token")


class TheWiring(TheStory):
    def test_the_console_looks_with_a_reader_of_reads_only_that_has_a_time_limit(self):
        from cases import precheck
        from cases.http import Refused
        from test_loop_end_to_end import DISK
        checker = self.browser.services.checker
        self.assertIsInstance(checker, precheck.Precheck)
        reader = checker.reader()
        url = f"https://management.azure.com{DISK}?api-version=2026-03-02"
        for method in ("DELETE", "PATCH", "PUT", "POST"):
            with self.subTest(method=method), self.assertRaises(Refused):
                reader.client.request(method, url, headers={"Authorization": "Bearer x"})
        self.assertGreater(reader.client.remaining(), 0)
        self.assertLessEqual(reader.client.remaining(), precheck.LOOK_SECONDS)
        self.assertIsNot(checker.reader().client, reader.client, "each look has a client, and a time limit, of its own")


if __name__ == "__main__":
    unittest.main()
