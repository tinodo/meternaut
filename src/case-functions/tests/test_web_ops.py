import unittest

from test_web_support import ACTS_ON, MAYA, NOW, OPS, OWNER, STRANGER, TINO, Console, FailingStore, at, snapshot

from cases.models import StoreError, SwitchRecord

APPROVE = "Approve and sign in to Azure"
BUTTONS = ["Pause everything", "Pause changes", "Pause all messages", "Pause the investigation"]


class StandingPermissions(unittest.TestCase):
    def setUp(self):
        self.console = Console()

    def test_it_says_that_meternaut_holds_no_permission_and_what_the_code_can_change_for_a_person_who_approved(self):
        reply = self.console.get("/ops/permissions")
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), ["Standing permissions"])
        self.assertEqual(reply.headings(2), ["What Meternaut can change in Azure"])
        self.assertIn("Meternaut holds no permission to change Azure. A change is made only after a person approves that exact change on its own page and signs in to Azure: "
                      "it is made with that person's own permissions, and Azure refuses it if the person may not make it.", reply.content)
        self.assertIn(f"On its own, nothing. The code makes only this change, and only for a person who approved it: {ACTS_ON}.", reply.content)
        for gone in ("None exists.", "The runner may only", "What the runner may change"):
            self.assertNotIn(gone, reply.content)

    def test_it_is_read_only(self):
        reply = self.console.get("/ops/permissions")
        self.assertEqual(reply.forms(), [])
        self.assertEqual(reply.root.find_all("button"), [])
        self.assertEqual(reply.root.find_all("input"), [])
        self.assertIn("This page only shows what exists. It cannot write, change or end a permission.", reply.content)
        self.assertEqual(self.console.post("/ops/permissions", {}).status, 405)

    def test_only_the_roles_ops_and_owner_may_open_it(self):
        for who, status in ((TINO, 200), (OPS, 200), (OWNER, 200), (MAYA, 403)):
            with self.subTest(who=who):
                self.assertEqual(self.console.get("/ops/permissions", oid=who).status, status)
        reply = self.console.get("/ops/permissions", oid=MAYA)
        self.assertEqual(reply.headings(1), ["You do not have the role that this page needs"])
        self.assertIn("This page is for people with the role ops or owner.", reply.content)
        self.assertNotIn(ACTS_ON, reply.content, "nothing of the page is shown to a person who may not open it")
        self.assertEqual(self.console.get("/ops/permissions", oid=STRANGER).status, 403)


class TheKillSwitchPage(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.page = self.console.get("/ops/pause")

    def test_four_levels_each_with_what_it_stops_and_a_button(self):
        self.assertEqual(self.page.status, 200)
        self.assertEqual(self.page.headings(1), ["The kill switch"])
        self.assertEqual(self.page.headings(2), ["Everything", "Changes", "All messages", "The investigation"])
        self.assertEqual([b[2] for f in self.page.forms() for b in f.buttons], BUTTONS)
        for sentence in ("No approval is accepted, no change is made in Azure and no message is sent.", "No approval is accepted and no change is made in Azure.",
                         "No message is sent to anybody.", "The AI agents do not run and open no new case. Waste that Meternaut planted itself, approvals, changes and messages go on."):
            self.assertIn(f"What it stops: {sentence}", self.page.content)
        self.assertIn("A change that was already sent to Azure is not recalled.", self.page.content)
        self.assertIn("Only the last change of each switch is kept, with the person, the time and the reason. Earlier changes are not kept.", self.page.content)
        self.assertEqual(self.page.content.count("is kept, with the person"), 1, "the words are in one place only")
        for overclaim in ("Every pull and resume is kept", "Other work goes on", "nothing else runs by itself", "The last change of each switch is kept"):
            self.assertNotIn(overclaim, self.page.content)
        self.assertIn("A switch that cannot be read counts as pulled.", self.page.content)
        self.assertEqual(self.page.content.count("State: Running."), 4)

    def test_only_the_role_ops_may_open_it_and_pull_a_switch(self):
        for who in (MAYA, OWNER):
            with self.subTest(who=who):
                self.assertEqual(self.console.get("/ops/pause", oid=who).status, 403)
        self.assertEqual(self.console.get("/ops/pause", oid=OPS).status, 200)
        self.assertEqual(self.console.get("/ops/pause", oid=TINO).status, 200)

    def test_a_person_who_may_not_pull_a_switch_changes_nothing_with_a_token_of_their_own_or_somebody_elses(self):
        form = self.page.form("/ops/pause", has_button="Pause changes")
        before = snapshot(self.console.store)
        for who in (MAYA, OWNER):
            with self.subTest(who=who):
                reply = self.console.post("/ops/pause", form.fields, oid=who)
                self.assertEqual(reply.status, 403)
                self.assertIn("This page is for people with the role ops.", reply.content)
        self.assertEqual(snapshot(self.console.store), before)
        self.assertTrue(self.console.store.nonce_use(form.fields["nonce"], TINO, "pause"), "the refusals did not use up the token")

    def test_a_pull_is_kept_with_the_persons_name_the_time_and_the_reason_and_shown_on_the_page(self):
        form = self.page.form("/ops/pause", has_button="Pause changes")
        reply = self.console.submit(form, reason="drill of the quarter")
        self.assertEqual(reply.status, 200)
        record = self.console.store.switch_get("changes")
        self.assertEqual((record.name, record.paused, record.by, record.at, record.reason), ("changes", True, "Tino", "2026-11-05T09:00:00Z", "drill of the quarter"))
        self.assertEqual(self.console.store.switch_get("all"), SwitchRecord("all"))
        self.assertEqual(self.console.store.switch_get("messages"), SwitchRecord("messages"))
        self.assertEqual(self.console.store.switch_get("investigation"), SwitchRecord("investigation"))
        self.assertIn("Paused", [p.text() for p in reply.root.find_all("p", class_="notice-title")])
        self.assertIn("Changes: paused by Tino.", reply.content)
        self.assertIn("State: Paused by Tino on Thu 5 Nov 2026 09:00 UTC (10:00 CET). Reason: drill of the quarter", reply.content)
        self.assertEqual([b[2] for f in reply.forms() for b in f.buttons], ["Pause everything", "Resume changes", "Pause all messages", "Pause the investigation"])

    def test_every_level_can_be_pulled_and_resumed(self):
        for name, pull, resume in (("all", "Pause everything", "Resume everything"), ("changes", "Pause changes", "Resume changes"), ("messages", "Pause all messages", "Resume all messages"),
                                   ("investigation", "Pause the investigation", "Resume the investigation")):
            with self.subTest(name=name):
                reply = self.console.submit(self.console.get("/ops/pause").form("/ops/pause", has_button=pull))
                self.assertTrue(self.console.store.switch_get(name).paused)
                self.assertTrue(reply.form("/ops/pause", has_button=resume))
                reply = self.console.submit(reply.form("/ops/pause", has_button=resume), reason="all clear")
                record = self.console.store.switch_get(name)
                self.assertEqual((record.paused, record.by, record.reason), (False, "Tino", "all clear"))
                self.assertIn("Resumed", [p.text() for p in reply.root.find_all("p", class_="notice-title")])

    def test_the_reason_is_optional_up_to_200_characters_and_clean(self):
        self.assertEqual(self.console.submit(self.page.form("/ops/pause", has_button="Pause changes")).status, 200)
        self.assertEqual(self.console.store.switch_get("changes").reason, "")
        self.assertIn("State: Paused by Tino on Thu 5 Nov 2026 09:00 UTC (10:00 CET). No reason is recorded.", self.console.get("/ops/pause").content)
        reply = self.console.submit(self.console.get("/ops/pause").form("/ops/pause", has_button="Resume changes"), reason="x" * 200)
        self.assertEqual(reply.status, 200)
        self.assertEqual(len(self.console.store.switch_get("changes").reason), 200)
        self.console.submit(self.console.get("/ops/pause").form("/ops/pause", has_button="Pause changes"), reason="two\r\nlines\x00 here")
        self.assertEqual(self.console.store.switch_get("changes").reason, "two lines here")

    def test_a_reason_over_200_characters_is_refused_with_the_text_kept_and_nothing_changes(self):
        form = self.page.form("/ops/pause", has_button="Pause changes")
        before = snapshot(self.console.store)
        reply = self.console.submit(form, reason="x" * 201)
        self.assertEqual(reply.status, 400)
        self.assertIn("The reason has 201 characters. The most is 200.", reply.content)
        self.assertEqual(snapshot(self.console.store), before)
        links = [a.attrs["href"] for a in reply.root.find("h2", id="problem-title").parent.find_all("a")]
        self.assertEqual(links, ["#reason-changes"])
        self.assertEqual(reply.root.find("input", id="reason-changes").attrs["value"], "x" * 201)
        self.assertEqual(reply.root.find("input", id="reason-all").attrs["value"], "", "the text is kept in the form that it was typed in")

    def test_a_name_or_an_action_that_is_not_one_of_the_four_and_the_two_is_refused(self):
        form = self.page.form("/ops/pause", has_button="Pause changes")
        before = snapshot(self.console.store)
        for name, action in (("everything", "pause"), ("", "pause"), ("changes", "stop"), ("changes", ""), ("changes", "PAUSE"), ("changes,all", "pause"), ("switches", "resume")):
            with self.subTest(name=name, action=action):
                tokens = self.console.get("/ops/pause").form("/ops/pause", has_button="Pause changes").fields["nonce"]
                reply = self.console.post("/ops/pause", {"name": name, "action": action, "nonce": tokens})
                self.assertEqual(reply.status, 400)
                self.assertIn("The form did not name one of the four switches and one of the two actions.", reply.content)
        self.assertEqual(snapshot(self.console.store), before)

    def test_the_name_in_the_record_is_the_signed_in_persons_and_nothing_that_was_posted(self):
        form = self.page.form("/ops/pause", has_button="Pause changes")
        self.console.submit(form, by="Mallory", **{"x-ms-client-principal-name": "Mallory"})
        self.assertEqual(self.console.store.switch_get("changes").by, "Tino")
        reply = self.console.submit(self.console.get("/ops/pause", oid=OPS).form("/ops/pause", has_button="Resume changes"), oid=OPS)
        self.assertEqual(self.console.store.switch_get("changes").by, "Otto")
        self.assertEqual(reply.status, 200)

    def test_a_switch_that_cannot_be_read_counts_as_pulled_and_can_only_be_pulled(self):
        console = Console(store=FailingStore(fail={"switch_get"}, clock=lambda: NOW))
        reply = console.get("/ops/pause")
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.content.count("State: Cannot be read: treated as pulled."), 4)
        self.assertEqual([b[2] for f in reply.forms() for b in f.buttons], BUTTONS, "there is no resume while a switch cannot be read")
        console.submit(reply.form("/ops/pause", has_button="Pause changes"))
        self.assertTrue(console.store.switch_records["changes"].paused, "a pull is written")

    def test_a_switch_that_cannot_be_written_is_said_plainly_and_the_runbook_is_named(self):
        def fail(record):
            raise StoreError("down", 503)
        self.console.store.switch_put = fail
        reply = self.console.submit(self.page.form("/ops/pause", has_button="Pause changes"))
        self.assertEqual(reply.status, 503)
        self.assertEqual(reply.headings(1), ["The switch was not written"])
        self.assertIn("The store did not take the change. Nothing was changed.", reply.content)
        self.assertIn("If work must stop now, use the commands of the runbook.", reply.content)

    def test_a_form_that_is_used_twice_changes_nothing_the_second_time(self):
        form = self.page.form("/ops/pause", has_button="Pause changes")
        self.assertEqual(self.console.submit(form).status, 200)
        self.console.store.switch_put(SwitchRecord("changes"))
        self.assertEqual(self.console.submit(form).status, 403)
        self.assertFalse(self.console.store.switch_get("changes").paused)


class WhatThePullDoes(unittest.TestCase):
    def test_a_pulled_switch_takes_the_approve_button_away_and_a_resume_brings_it_back(self):
        console = Console(decider="loop")
        console.seed()
        self.assertIn(APPROVE, console.get("/ok/plan0001").content)
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Pause changes"), reason="drill")
        reply = console.get("/ok/plan0001")
        self.assertNotIn(APPROVE, reply.content)
        self.assertIn("Changes are paused here. Nothing has changed, and your OK cannot be recorded now.", reply.content)
        self.assertIn("Paused by Tino", console.get("/").content)
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Resume changes"))
        self.assertIn(APPROVE, console.get("/ok/plan0001").content)

    def test_the_switch_of_everything_takes_the_approve_button_away_too_and_the_messages_switch_does_not(self):
        console = Console(decider="loop")
        console.seed()
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Pause everything"))
        self.assertNotIn(APPROVE, console.get("/ok/plan0001").content)
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Resume everything"))
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Pause all messages"))
        self.assertIn(APPROVE, console.get("/ok/plan0001").content)


if __name__ == "__main__":
    unittest.main()
