import unittest

from test_web_pages import INVESTIGATED
from test_web_support import ACTS_ON, MAYA, NOW, OPS, OWNER, STRANGER, TINO, Console, FailingStore, at, make_case, make_run, snapshot

from cases.models import StoreError, SwitchRecord

APPROVE = "Approve and sign in to Azure"
BUTTONS = ["Pause everything", "Pause changes", "Pause all messages", "Pause the investigation"]


class TheOperationsPage(unittest.TestCase):
    """Operations: what the start page no longer carries (the switches, the latest runs, what Meternaut may change), for the role ops."""

    def setUp(self):
        self.console = Console()
        self.console.seed()
        self.reply = self.console.get("/ops")

    def test_it_holds_the_switches_the_latest_runs_and_what_meternaut_may_change(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), ["Operations"])
        self.assertEqual(self.reply.headings(2), ["The four switches", "Latest runs", "What Meternaut can change in Azure"])
        self.assertEqual([r["Switch"] for r in self.reply.table("switches").rows], ["Everything", "Changes", "All messages", "The investigation"])
        self.assertEqual([r["State"] for r in self.reply.table("switches").rows], ["Running.", "Running.", "Running.", "Running."])
        self.assertEqual([r["What it stops"] for r in self.reply.table("switches").rows], [
            "No approval is accepted, no change is made in Azure and no message is sent.", "No approval is accepted and no change is made in Azure.", "No message is sent to anybody.",
            "The AI agents do not run and open no new case. Waste that Meternaut planted itself, approvals, changes and messages go on."])
        run = self.reply.table("latest-runs").rows[0]
        self.assertEqual((run["Trigger"], run["Result"], run["Cases"], run["Proposed"], run["Needs a person"], run["Errors"]), ("timer", "OK", "3", "3", "0", "0"))
        self.assertIn("On its own, nothing: Meternaut holds no right to change Azure. When a person approves a change, they sign in to Azure and Meternaut makes that one change "
                      f"with their own permissions. The code makes only this change: {ACTS_ON}.", self.reply.content)
        self.assertEqual([l for l in self.reply.links() if l.startswith("/ops")], ["/ops", "/ops/pause", "/ops/runs", "/ops/permissions"])

    def test_the_state_of_a_pulled_switch_is_in_words(self):
        self.console.store.switch_put(SwitchRecord("changes", True, "Otto", at(minutes=-5), "drill"))
        self.console.store.switch_put(SwitchRecord("messages", True, "", "", ""))
        rows = self.console.get("/ops").table("switches").rows
        self.assertEqual(rows[1]["State"], "Paused by Otto on Thu 5 Nov 2026 08:55 UTC (09:55 CET). Reason: drill")
        self.assertEqual(rows[2]["State"], "Paused on a time that is not recorded. No reason is recorded.")

    def test_a_switch_that_cannot_be_read_is_shown_as_pulled(self):
        console = Console(store=FailingStore(fail={"switch_get"}, clock=lambda: NOW))
        console.seed()
        reply = console.get("/ops")
        self.assertEqual(reply.status, 200)
        self.assertEqual([r["State"] for r in reply.table("switches").rows], ["Cannot be read: treated as pulled."] * 4)

    def test_five_runs_are_shown_and_a_part_that_cannot_be_read_says_so(self):
        for n in range(8):
            self.console.store.run_put(make_run(run_id=f"run1000{n}", started_at=at(hours=-n - 3)))
        self.assertEqual(len(self.console.get("/ops").table("latest-runs").rows), 5)
        broken = Console(store=FailingStore(fail={"runs_recent"}, clock=lambda: NOW))
        reply = broken.get("/ops")
        self.assertIn("I cannot read the runs now.", reply.content)
        self.assertIn("State of each switch", reply.content)
        self.assertEqual(Console().get("/ops").content.count("No run is recorded yet."), 1)

    def test_only_the_role_ops_may_open_it_and_it_changes_nothing(self):
        for who, status in ((TINO, 200), (OPS, 200), (OWNER, 403), (MAYA, 403), (STRANGER, 403)):
            with self.subTest(who=who):
                self.assertEqual(self.console.get("/ops", oid=who).status, status)
        reply = self.console.get("/ops", oid=MAYA)
        self.assertIn("This page is for people with the role ops.", reply.content)
        self.assertNotIn(ACTS_ON, reply.content)
        before = snapshot(self.console.store)
        self.console.get("/ops")
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(self.console.post("/ops", {}).status, 405)


class TheRunsPage(unittest.TestCase):
    """Every run and every case, the page that History used to be: the tables moved here, for the role ops."""

    def setUp(self):
        self.console = Console()
        self.console.seed()
        self.console.store.run_put(make_run(run_id="run00002", started_at=at(hours=-1), ok=False, reason="no detector could read any subscription", leads=0, cases=0, proposed=0,
                                            tokens=0, seconds=3, notes=()))
        self.console.store.run_put(make_run(run_id="run00003", started_at=at(minutes=-5), finished_at=None, notes=("a", "b")))
        self.console.store.case_put(make_case(case_id="case0002", run_id="run00002", resource_name="other-disk", status="needs_human", recommendation="investigate",
                                              confidence=0.5, saving_usd_month=None, updated_at=at(hours=-1)))

    def test_every_run_is_there_with_all_of_its_numbers(self):
        reply = self.console.get("/ops/runs")
        table = reply.table("runs")
        self.assertEqual(table.headers, ["Started", "Trigger", "Result", "Leads", "Cases", "Proposed", "Needs a person", "Dropped", "Errors", "Tokens", "Seconds", "Notes", "Cases of the run"])
        by_start = {row["Started"].split(" (")[0]: row for row in table.rows}
        ok = by_start["Thu 5 Nov 2026 07:00 UTC"]
        self.assertEqual((ok["Trigger"], ok["Result"], ok["Leads"], ok["Cases"], ok["Proposed"], ok["Needs a person"], ok["Dropped"], ok["Errors"], ok["Tokens"], ok["Seconds"], ok["Notes"]),
                         ("timer", "OK", "4", "3", "3", "0", "0", "0", "2,089", "28", "one source was not read"))
        self.assertEqual((by_start["Thu 5 Nov 2026 08:00 UTC"]["Result"], by_start["Thu 5 Nov 2026 08:00 UTC"]["Notes"]), ("Failed: no detector could read any subscription", "none"))
        self.assertEqual((by_start["Thu 5 Nov 2026 08:55 UTC"]["Result"], by_start["Thu 5 Nov 2026 08:55 UTC"]["Notes"]), ("Started, not finished", "a b"))
        self.assertEqual([row["Started"].split(" (")[0] for row in table.rows], ["Thu 5 Nov 2026 08:55 UTC", "Thu 5 Nov 2026 08:00 UTC", "Thu 5 Nov 2026 07:00 UTC"], "newest first")

    def test_every_case_is_there_with_its_recommendation_confidence_and_estimated_saving_and_a_link_to_its_page(self):
        reply = self.console.get("/ops/runs")
        table = reply.table("cases")
        self.assertEqual(table.headers, ["Resource", "Found by", "Status", "Recommendation", "Confidence (0 to 1)", "Estimated saving a month", "Last updated", "Page"])
        self.assertEqual([r["Status"] for r in table.rows], ["Needs a person", "Proposed"], "most recently updated first")
        first = next(r for r in table.rows if r["Status"] == "Proposed")
        self.assertIn("planted-disk-1", first["Resource"])
        self.assertIn("Managed disk (microsoft.compute/disks)", first["Resource"])
        self.assertIn("Resource group meternaut-test-rg.", first["Resource"])
        self.assertEqual((first["Recommendation"], first["Confidence (0 to 1)"], first["Estimated saving a month"]), ("Delete", "0.91", "7.17 US dollars"))
        second = next(r for r in table.rows if r["Status"] == "Needs a person")
        self.assertEqual((second["Recommendation"], second["Confidence (0 to 1)"], second["Estimated saving a month"]), ("Investigate", "0.50", "no figure"))
        self.assertIn("/why/case0001", reply.links())
        self.assertIn("/why/case0002", reply.links())

    def test_a_run_filters_the_cases(self):
        reply = self.console.get("/ops/runs", query={"run": "run00002"})
        self.assertEqual(reply.status, 200)
        rows = reply.table("cases").rows
        self.assertEqual(len(rows), 1)
        self.assertIn("other-disk", rows[0]["Resource"])
        self.assertIn("Cases of the run run00002.", reply.content)
        self.assertIn("/ops/runs", reply.links(), "a link shows all cases again")
        self.assertEqual(len(reply.table("runs").rows), 3, "every run is still listed")
        self.assertEqual(sum("Selected." in r["Started"] for r in reply.table("runs").rows), 1)
        self.assertIn("/ops/runs?run=run00002", reply.links())

    def test_a_run_with_no_cases_and_an_unknown_run_say_so(self):
        reply = self.console.get("/ops/runs", query={"run": "run00003"})
        self.assertFalse(reply.has_table("cases"))
        self.assertIn("No case is recorded for this run.", reply.content)
        self.assertIn("No case is recorded for this run.", self.console.get("/ops/runs", query={"run": "nothing"}).content)

    def test_a_run_id_that_is_not_a_run_id_is_said_so_and_shows_every_case(self):
        for bad in ("a b", "<script>", "x" * 81, "a/b", "%00"):
            with self.subTest(bad=bad):
                reply = self.console.get("/ops/runs", query={"run": bad})
                self.assertEqual(reply.status, 200)
                self.assertIn("That run id is not valid", reply.content)
                self.assertEqual(len(reply.table("cases").rows), 2)

    def test_the_page_is_complete_the_latest_100_cases_and_the_cases_of_any_run(self):
        console = Console()
        console.seed()
        for n in range(130):
            console.store.case_put(make_case(case_id=f"c{n:04d}", run_id="run00009", updated_at=at(minutes=-n - 1), resource_name=f"disk-{n}"))
        console.store.case_put(make_case(case_id="old", run_id="run00001", resource_name="very-old", updated_at=at(days=-30)))
        reply = console.get("/ops/runs")
        self.assertEqual(len(reply.table("cases").rows), 100)
        self.assertIn("The latest 100 cases, most recently updated first.", reply.content)
        self.assertNotIn("very-old", reply.content)
        self.assertIn("very-old", console.get("/ops/runs", query={"run": "run00001"}).content, "a run that is far back is complete")

    def test_the_page_says_that_a_case_is_a_resource_that_meternaut_only_reads_and_that_it_is_not_a_cost_report(self):
        reply = self.console.get("/ops/runs")
        self.assertIn("A case is a resource in the subscription that the search found and that may be unused or too big. Meternaut only reads it and does not use it. "
                      "Nothing is changed until a person approves a plan.", reply.content)
        self.assertIn("It is not a cost report.", reply.content)
        for node in reply.root.walk():
            self.assertNotIn(node.tag, ("svg", "canvas", "img", "script", "video"))
        for word in ("chart", "dashboard", "graph"):
            self.assertNotIn(word, reply.content.lower())

    def test_twenty_runs_are_shown_newest_first(self):
        console = Console()
        for n in range(25):
            console.store.run_put(make_run(run_id=f"r{n:03d}", started_at=at(hours=-n)))
        self.assertEqual(len(console.get("/ops/runs").table("runs").rows), 20)

    def test_the_words_of_every_status_are_explained(self):
        reply = self.console.get("/ops/runs")
        self.assertIn("What the status words mean", reply.headings(2))
        legend = reply.summary(0)
        self.assertEqual(list(legend), ["Proposed", "Needs a person", "Dropped", "Error", "Waiting for an OK", "Approved", "Running", "Done", "Failed", "Declined", "Expired", "Done and verified",
                                        "Worth acting on"])
        self.assertEqual(legend["Declined"], "A person said no. Nothing changed.")
        self.assertEqual(legend["Worth acting on"], "A person said that this is worth acting on. Meternaut changed nothing in Azure.")
        self.assertNotIn("runner", " ".join(legend.values()).lower())

    def test_an_empty_page_says_so_and_a_store_that_cannot_be_read_is_said_plainly(self):
        reply = Console().get("/ops/runs")
        self.assertIn("No run is recorded yet.", reply.content)
        self.assertIn("No case is recorded yet.", reply.content)
        reply = Console(store=FailingStore(fail={"runs_recent", "cases_recent"}, clock=lambda: NOW)).get("/ops/runs")
        self.assertEqual(reply.status, 200)
        self.assertIn("The runs cannot be read", reply.content)
        self.assertIn("The cases cannot be read", reply.content)

    def test_a_status_that_is_not_in_the_list_is_shown_as_stored_and_a_case_of_the_investigation_is_a_row_like_any_other(self):
        self.console.store.case_put(make_case(case_id="case0003", status="something new"))
        self.console.store.case_put(make_case(**{**INVESTIGATED, "resource_name": "oversized-thing", "updated_at": at(minutes=-1)}))
        rows = self.console.get("/ops/runs").table("cases").rows
        self.assertIn("something new", [r["Status"] for r in rows])
        row = next(r for r in rows if "oversized-thing" in r["Resource"])
        self.assertIn("Found by the Watch's own investigation", row["Found by"])
        self.assertEqual((row["Status"], row["Recommendation"], row["Confidence (0 to 1)"], row["Estimated saving a month"]), ("Proposed", "Change", "0.85", "no figure"))

    def test_only_the_role_ops_may_open_it(self):
        for who, status in ((TINO, 200), (OPS, 200), (OWNER, 403), (MAYA, 403), (STRANGER, 403)):
            with self.subTest(who=who):
                self.assertEqual(self.console.get("/ops/runs", oid=who).status, status)
        self.assertNotIn("planted-disk-1", self.console.get("/ops/runs", oid=MAYA).content)

    def test_the_words_of_the_recommendations_are_the_four_and_a_word_that_is_not_listed_is_shown_as_stored(self):
        from cases.web import words
        self.assertEqual([words.recommendation_word(r) for r in ("delete", "change", "keep", "investigate")], ["Delete", "Change", "Keep", "Investigate"])
        self.assertEqual((words.recommendation_word(None), words.recommendation_word(""), words.recommendation_word("something new")), ("none", "none", "Something new"))
        self.assertEqual(words.recommendation_meaning("change"), "Keep the resource and change it, for example to a smaller size or another tier.")
        self.assertEqual(words.DETECTOR["investigation"], "Found by the Watch's own investigation")


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
        self.assertIn("Paused by Tino", console.get("/ops").content)
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
