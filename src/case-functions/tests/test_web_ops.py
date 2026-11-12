import dataclasses
import datetime as dt
import unittest
from unittest import mock

from test_web_pages import INVESTIGATED
from test_web_support import ACTS_ON, MAYA, NOW, OPS, OWNER, STRANGER, TINO, Console, FailingStore, at, make_case, make_run, snapshot

from cases.models import CheckRecord, StoreError, SwitchRecord, TwoPeopleRule
from cases.people import People, Person

APPROVE = "Approve"
BUTTONS = ["Pause everything", "Pause changes", "Pause all messages", "Pause the investigation"]


def _ancestors(node):
    while node.parent is not None:
        node = node.parent
        yield node


class TheOperationsPage(unittest.TestCase):
    """Operations: what the start page no longer carries (the switches, the latest runs, what Meternaut may change), for the role ops."""

    def setUp(self):
        self.console = Console()
        self.console.seed()
        self.reply = self.console.get("/ops")

    def test_it_holds_the_switches_the_latest_runs_and_what_meternaut_may_change(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), ["Operations"])
        self.assertEqual(self.reply.headings(2), ["The four switches", "When a change needs two people", "Latest runs", "The drift check", "What people answered before",
                                                  "What Meternaut can change in Azure"])
        self.assertEqual([r["Switch"] for r in self.reply.table("switches").rows], ["Everything", "Changes", "All messages", "The investigation"])
        self.assertEqual([r["State"] for r in self.reply.table("switches").rows], ["Running", "Running", "Running", "Running"])
        self.assertEqual([r["What it stops"] for r in self.reply.table("switches").rows], [
            "No approval is accepted, no change is made in Azure and no message is sent.", "No approval is accepted and no change is made in Azure.", "No message is sent to anybody.",
            "The AI agents do not run and open no new finding. Waste that Meternaut planted itself, approvals, changes and messages go on."])
        run = self.reply.table("latest-runs").rows[0]
        self.assertEqual((run["Trigger"], run["Result"], run["Findings"], run["Proposed"], run["Needs a person"], run["Errors"]), ("timer", "OK", "3", "3", "0", "0"))
        self.assertIn("On its own, nothing: Meternaut holds no right to change Azure. When a person approves a change, Meternaut makes that one change "
                      f"with their own permissions. The code makes only this change: {ACTS_ON}.", self.reply.content)
        self.assertEqual([l for l in self.reply.links() if l.startswith("/ops")], ["/ops", "/ops/pause", "/ops/two-people", "/ops/runs", "/ops/permissions"])

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
        self.assertEqual(table.headers, ["Started", "Trigger", "Result", "Candidates", "Findings", "Proposed", "Needs a person", "Dropped", "Errors", "Tokens", "Seconds", "Notes",
                                         "Findings of the run"])
        by_start = {row["Started"].split(" (")[0]: row for row in table.rows}
        ok = by_start["Thu 5 Nov 2026 07:00 UTC"]
        self.assertEqual((ok["Trigger"], ok["Result"], ok["Candidates"], ok["Findings"], ok["Proposed"], ok["Needs a person"], ok["Dropped"], ok["Errors"], ok["Tokens"], ok["Seconds"],
                          ok["Notes"]), ("timer", "OK", "4", "3", "3", "0", "0", "0", "2,089", "28", "one source was not read"))
        self.assertEqual((by_start["Thu 5 Nov 2026 08:00 UTC"]["Result"], by_start["Thu 5 Nov 2026 08:00 UTC"]["Notes"]), ("Failed: no detector could read any subscription", "none"))
        self.assertEqual((by_start["Thu 5 Nov 2026 08:55 UTC"]["Result"], by_start["Thu 5 Nov 2026 08:55 UTC"]["Notes"]), ("Started, not finished", "a b"))
        self.assertEqual([row["Started"].split(" (")[0] for row in table.rows], ["Thu 5 Nov 2026 08:55 UTC", "Thu 5 Nov 2026 08:00 UTC", "Thu 5 Nov 2026 07:00 UTC"], "newest first")

    def test_every_case_is_there_with_its_recommendation_confidence_and_what_it_would_save_and_a_link_to_its_page(self):
        reply = self.console.get("/ops/runs")
        table = reply.table("cases")
        self.assertEqual(table.headers, ["Resource", "Found by", "Status", "Recommendation", "Confidence (0 to 1)", "What it would save", "Last updated", "Page"])
        self.assertEqual([r["Status"] for r in table.rows], ["Needs a person", "Proposed"], "most recently updated first")
        first = next(r for r in table.rows if r["Status"] == "Proposed")
        self.assertIn("planted-disk-1", first["Resource"])
        self.assertIn("Managed disk (microsoft.compute/disks)", first["Resource"])
        self.assertIn("Resource group meternaut-test-rg.", first["Resource"])
        self.assertEqual((first["Recommendation"], first["Confidence (0 to 1)"]), ("Delete", "0.91"))
        self.assertIn("$86 a year", first["What it would save"])
        self.assertIn("Saves, Expected. $7.17 a month. Based on the cost lines of the last 30 days.", first["What it would save"], "a figure carries its level and its basis (rule 13)")
        second = next(r for r in table.rows if r["Status"] == "Needs a person")
        self.assertEqual((second["Recommendation"], second["Confidence (0 to 1)"]), ("Investigate", "0.50"))
        self.assertIn("Costs, saving not measured. $7.17 a month.", second["What it would save"], "no saving is claimed where none was measured")
        self.assertNotIn("Saves", second["What it would save"])
        self.assertIn("/why/case0001", reply.links())
        self.assertIn("/why/case0002", reply.links())

    def test_a_run_filters_the_cases(self):
        reply = self.console.get("/ops/runs", query={"run": "run00002"})
        self.assertEqual(reply.status, 200)
        rows = reply.table("cases").rows
        self.assertEqual(len(rows), 1)
        self.assertIn("other-disk", rows[0]["Resource"])
        self.assertIn("Findings of the run run00002.", reply.content)
        self.assertIn("/ops/runs", reply.links(), "a link shows all findings again")
        self.assertEqual(len(reply.table("runs").rows), 3, "every run is still listed")
        self.assertEqual(sum("Selected." in r["Started"] for r in reply.table("runs").rows), 1)
        self.assertIn("/ops/runs?run=run00002", reply.links())

    def test_a_run_with_no_cases_and_an_unknown_run_say_so(self):
        reply = self.console.get("/ops/runs", query={"run": "run00003"})
        self.assertFalse(reply.has_table("cases"))
        self.assertIn("No finding is recorded for this run.", reply.content)
        self.assertIn("No finding is recorded for this run.", self.console.get("/ops/runs", query={"run": "nothing"}).content)

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
        self.assertIn("The latest 100 findings, most recently updated first.", reply.content)
        self.assertNotIn("very-old", reply.content)
        self.assertIn("very-old", console.get("/ops/runs", query={"run": "run00001"}).content, "a run that is far back is complete")

    def test_the_page_says_that_a_finding_is_a_resource_that_meternaut_only_reads_and_that_it_is_not_a_cost_report(self):
        reply = self.console.get("/ops/runs")
        self.assertIn("A finding is a resource in the subscription that the search found and that may be unused or too big. Meternaut only reads it and does not use it. "
                      "Nothing is changed until a person approves the request.", reply.content)
        self.assertIn("It is not a cost report.", reply.content)
        for node in reply.root.walk():
            if node.tag == "svg":
                self.assertIn("chip", " ".join(p.attrs.get("class", "") for p in _ancestors(node)), "the only drawings are the shapes of the chips")
            self.assertNotIn(node.tag, ("canvas", "img", "script", "video"))
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
        self.assertIn("No finding is recorded yet.", reply.content)
        reply = Console(store=FailingStore(fail={"runs_recent", "cases_recent"}, clock=lambda: NOW)).get("/ops/runs")
        self.assertEqual(reply.status, 200)
        self.assertIn("The runs cannot be read", reply.content)
        self.assertIn("The findings cannot be read", reply.content)

    def test_a_status_that_is_not_in_the_list_is_shown_as_stored_and_a_case_of_the_investigation_is_a_row_like_any_other(self):
        self.console.store.case_put(make_case(case_id="case0003", status="something new"))
        self.console.store.case_put(make_case(**{**INVESTIGATED, "resource_name": "oversized-thing", "updated_at": at(minutes=-1)}))
        rows = self.console.get("/ops/runs").table("cases").rows
        self.assertIn("something new", [r["Status"] for r in rows])
        row = next(r for r in rows if "oversized-thing" in r["Resource"])
        self.assertIn("Found by the Watch's own investigation", row["Found by"])
        self.assertEqual((row["Status"], row["Recommendation"], row["Confidence (0 to 1)"]), ("Proposed", "Change", "0.85"))
        self.assertNotIn("Saves", row["What it would save"], "a finding with no saving of its own claims none, whatever the cost lines say")

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
        self.assertIn("Meternaut holds no permission to change Azure. A change is made only after a person approves that exact change on its own page: "
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
                         "No message is sent to anybody.", "The AI agents do not run and open no new finding. Waste that Meternaut planted itself, approvals, changes and messages go on."):
            self.assertIn(f"What it stops: {sentence}", self.page.content)
        self.assertIn("A change that was already sent to Azure is not recalled.", self.page.content)
        self.assertIn("Only the last change of each switch is kept, with the person, the time and the reason. Earlier changes are not kept.", self.page.content)
        self.assertEqual(self.page.content.count("is kept, with the person"), 1, "the words are in one place only")
        for overclaim in ("Every pull and resume is kept", "Other work goes on", "nothing else runs by itself", "The last change of each switch is kept"):
            self.assertNotIn(overclaim, self.page.content)
        self.assertIn("A switch that cannot be read counts as pulled.", self.page.content)
        self.assertEqual(self.page.content.count("State: Running"), 4)

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
        self.assertTrue(console.get("/ok/plan0001").has_button(APPROVE))
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Pause changes"), reason="drill")
        reply = console.get("/ok/plan0001")
        self.assertFalse(reply.has_button(APPROVE))
        self.assertIn("Changes are paused here. Nothing has changed, and your OK cannot be recorded now.", reply.content)
        self.assertIn("Paused by Tino", console.get("/ops").content)
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Resume changes"))
        self.assertTrue(console.get("/ok/plan0001").has_button(APPROVE))

    def test_the_switch_of_everything_takes_the_approve_button_away_too_and_the_messages_switch_does_not(self):
        console = Console(decider="loop")
        console.seed()
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Pause everything"))
        self.assertFalse(console.get("/ok/plan0001").has_button(APPROVE))
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Resume everything"))
        console.submit(console.get("/ops/pause").form("/ops/pause", has_button="Pause all messages"))
        self.assertTrue(console.get("/ok/plan0001").has_button(APPROVE))


class TheTwoPeopleRulePage(unittest.TestCase):
    """When a change needs two people: off until the owner turns it on; the owner changes it; the hub shows it."""
    OFF = "Off. Every change needs one approver."

    def setUp(self):
        self.console = Console()

    def save(self, console=None, **fields):
        console = console or self.console
        return console.submit(console.get("/ops/two-people").form("/ops/two-people", has_button="Save the rule"), "Save the rule", **fields)

    def test_it_is_off_until_the_owner_turns_it_on_and_says_so(self):
        page = self.console.get("/ops/two-people")
        self.assertEqual((page.status, page.headings(1)), (200, ["Changes that need two people"]))
        self.assertIn(self.OFF, page.content)
        self.assertIn("2 people have the role approver.", page.content)
        self.assertEqual(self.console.store.rule_get(), TwoPeopleRule())
        self.assertIn(self.OFF, self.console.get("/ops").content)

    def test_ops_and_the_owner_see_it_and_only_the_owner_changes_it(self):
        self.assertEqual([self.console.get("/ops/two-people", oid=who).status for who in (TINO, OWNER, OPS, MAYA, STRANGER)], [200, 200, 200, 403, 403])
        self.assertTrue(self.console.get("/ops/two-people", oid=OWNER).form("/ops/two-people", has_button="Save the rule"))
        seen = self.console.get("/ops/two-people", oid=OPS)
        self.assertEqual(seen.forms(), [])
        self.assertIn("Only the owner changes it.", seen.content)
        token = self.console.get("/ops/two-people").form("/ops/two-people").fields["nonce"]
        for who in (OPS, MAYA, STRANGER):
            with self.subTest(who=who):
                self.assertEqual(self.console.post("/ops/two-people", {"nonce": token, "min_usd": "100"}, oid=who).status, 403)
        self.assertEqual(self.console.store.rule_get(), TwoPeopleRule())

    def test_an_amount_and_kinds_are_saved_with_the_owners_name_and_the_time_and_shown_again(self):
        reply = self.save(min_usd="150.5", families="resize-vm,stop-vm")
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.console.store.rule_get(), TwoPeopleRule(min_usd_month=150.5, families=("stop-vm", "resize-vm"), by="Tino", at="2026-11-05T09:00:00Z"))
        self.assertIn("On. A change needs two people when it saves at least $150.50 a month or it is one of these: stop a virtual machine", reply.content)
        self.assertIn("One confirms the request, and another approves it.", reply.content)
        self.assertIn("It was last changed by Tino on Thu 5 Nov 2026 09:00 UTC (10:00 CET).", reply.content)
        self.assertEqual(reply.root.find("input", id="min_usd").attrs["value"], "150.5")
        self.assertEqual([box.attrs["value"] for box in reply.root.find_all("input") if box.attrs.get("type") == "checkbox" and "checked" in box.attrs], ["stop-vm", "resize-vm"])
        self.assertIn("On. A change needs two people when it saves at least $150.50 a month", self.console.get("/ops").content)

    def test_an_amount_alone_or_kinds_alone_is_a_rule_and_neither_turns_it_off(self):
        self.save(min_usd="20")
        self.assertEqual((self.console.store.rule_get().min_usd_month, self.console.store.rule_get().families), (20.0, ()))
        self.save(min_usd="", families="delete-disk")
        self.assertEqual((self.console.store.rule_get().min_usd_month, self.console.store.rule_get().families), (None, ("delete-disk",)))
        reply = self.save(min_usd="", families="")
        self.assertFalse(self.console.store.rule_get().on)
        self.assertIn(self.OFF, reply.content)

    def test_an_amount_that_is_not_above_zero_and_a_kind_that_is_not_listed_are_refused_and_nothing_is_saved(self):
        for amount in ("0", "-5", "abc", "1e3", "12.345", "99999999", "1,5", "0.00"):
            with self.subTest(amount=amount):
                reply = self.save(min_usd=amount)
                self.assertEqual(reply.status, 400)
                self.assertIn("Enter an amount above zero, with up to two decimals, or leave it empty.", reply.content)
                self.assertEqual(reply.root.find("input", id="min_usd").attrs["value"], amount, "the text stays in the field")
        for named in ("advise", "nonsense", "stop-vm,advise"):
            with self.subTest(named=named):
                reply = self.save(families=named)
                self.assertEqual(reply.status, 400)
                self.assertIn("Choose kinds of change from the list.", reply.content)
        self.assertEqual(self.console.store.rule_get(), TwoPeopleRule())

    def test_a_rule_is_refused_while_fewer_than_two_people_can_approve_and_off_is_always_allowed(self):
        alone = Console(people=People((Person(TINO, "Tino", ("owner", "approver", "ops"), "tino@example.com"),)))
        reply = self.save(alone, min_usd="100")
        self.assertEqual(reply.status, 400)
        self.assertIn("A rule that needs two people needs at least two people with the role approver, and 1 is listed. Nothing was saved.", reply.content)
        self.assertEqual(alone.store.rule_get(), TwoPeopleRule())
        alone.store.rule_put(TwoPeopleRule(min_usd_month=100.0))
        self.assertEqual(self.save(alone, min_usd="").status, 200)
        self.assertFalse(alone.store.rule_get().on)

    def test_a_form_is_used_once_and_a_form_without_a_token_is_not_taken(self):
        form = self.console.get("/ops/two-people").form("/ops/two-people", has_button="Save the rule")
        self.assertEqual(self.console.submit(form, "Save the rule", min_usd="40").status, 200)
        self.console.store.rule_put(TwoPeopleRule())
        self.assertEqual(self.console.submit(form, "Save the rule", min_usd="40").status, 403)
        self.assertEqual(self.console.post("/ops/two-people", {"min_usd": "40"}).status, 403)
        self.assertFalse(self.console.store.rule_get().on)

    def test_a_store_that_cannot_be_written_or_read_is_said_plainly(self):
        broken = Console(store=FailingStore(fail=("rule_put",)))
        reply = self.save(broken, min_usd="40")
        self.assertEqual((reply.status, reply.headings(1)), (503, ["The rule was not saved"]))
        self.assertIn("Nothing was changed.", reply.content)
        unread = Console(store=FailingStore(fail=("rule_get",)))
        reply = unread.get("/ops/two-people")
        self.assertEqual(reply.status, 200)
        self.assertIn("I cannot read the rule now, so what is shown is the starting rule: off. Nothing has changed.", reply.content)


class FakeCheck:
    """What the console starts: it keeps what it was asked and, as cases/drift.py does, keeps its result as the latest check."""

    def __init__(self, console, results=None, tripped=False, silent=False):
        self.console, self.tripped, self.silent, self.calls = console, tripped, silent, []
        self.results = results if results is not None else (
            {"control": "A-LOCK", "layer": "L2", "state": "PASS", "detail": "the code of 3 agents and 9 tools equals the lock"},
            {"control": "A-CONNECTIONS", "layer": "L1", "state": "FAIL", "detail": "the connection to the gateway uses a key"},
            {"control": "A-TRACING", "layer": "L2", "state": "UNKNOWN", "detail": "the project could not be read (HTTP 403)"})

    def __call__(self, by, started_at):
        self.calls.append((by, started_at))
        if not self.silent:  # a check that never reports leaves the claim as it was
            self.console.store.check_put(CheckRecord(started_at=started_at, trigger="console", by=by, finished_at=started_at, tripped=self.tripped, results=self.results))


def check_console(**kwargs):
    console = Console()
    console.fake = FakeCheck(console, **kwargs)
    console.services = dataclasses.replace(console.services, drift=console.fake)
    return console


def start(console, oid=TINO):
    """Opens the page and presses the button, as a person does."""
    return console.submit(console.get("/ops", oid=oid).form("/ops/drift", has_button="Check now"), oid=oid)


class TheDriftCheckAtTheConsole(unittest.TestCase):
    def test_a_person_with_the_role_ops_starts_it_and_the_page_shows_what_it_found_the_ones_that_need_a_look_first(self):
        console = check_console()
        self.assertIn("No check is recorded yet.", console.get("/ops").content)
        reply = start(console)
        self.assertEqual(reply.status, 200)
        self.assertEqual(console.fake.calls, [("Tino", "2026-11-05T09:00:00Z")])
        self.assertIn("The check ran", [p.text() for p in reply.root.find_all("p", class_="notice-title")])
        self.assertIn("Latest check: Thu 5 Nov 2026 09:00 UTC (10:00 CET), started by Tino. 1 pass, 1 fail and 1 cannot be told.", reply.content)
        rows = reply.table("drift").rows
        self.assertEqual([(r["Control"], r["Result"]) for r in rows], [("A-CONNECTIONS", "Fail"), ("A-TRACING", "Cannot be told"), ("A-LOCK", "Pass")])
        self.assertEqual(rows[1]["What it found"], "the project could not be read (HTTP 403)")
        self.assertNotIn("paused the investigation", reply.content)

    def test_two_checks_are_never_less_than_fifteen_minutes_apart_whoever_asks_and_the_timers_check_counts(self):
        console = check_console()
        start(console)
        console.now += dt.timedelta(minutes=14)
        self.assertNotIn("Check now", console.get("/ops").content)
        self.assertIn("The next check can start Thu 5 Nov 2026 09:15 UTC (10:15 CET). At most one check starts in 15 minutes, whoever asks.", console.get("/ops").content)
        token = console.store.nonce_new(OPS, "drift")
        reply = console.post("/ops/drift", {"nonce": token}, oid=OPS)
        self.assertEqual(reply.status, 429)
        self.assertIn("A check began Thu 5 Nov 2026 09:00 UTC (10:00 CET). The next one can start Thu 5 Nov 2026 09:15 UTC (10:15 CET).", reply.content)
        self.assertIn("Nothing was started.", reply.content)
        self.assertEqual(len(console.fake.calls), 1)
        console.now += dt.timedelta(minutes=1)
        self.assertEqual(start(console, OPS).status, 200, "exactly fifteen minutes later is allowed")
        self.assertEqual(console.fake.calls[-1], ("Otto", "2026-11-05T09:15:00Z"))
        timer = check_console()
        timer.store.check_put(CheckRecord(started_at=at(minutes=-5), trigger="timer", finished_at=at(minutes=-4), results=()))
        self.assertEqual(timer.post("/ops/drift", {"nonce": timer.store.nonce_new(TINO, "drift")}).status, 429)
        self.assertEqual(timer.fake.calls, [])

    def test_two_people_who_ask_at_the_same_moment_start_one_check(self):
        console = check_console()
        console.store.check_put(CheckRecord(started_at=at(minutes=-1), trigger="console", by="Otto"))
        newer = console.store.check
        with mock.patch.object(console.store, "check_latest", side_effect=[None, newer]):  # the first read was made before the other person's claim
            reply = console.post("/ops/drift", {"nonce": console.store.nonce_new(TINO, "drift")})
        self.assertEqual(reply.status, 429)
        self.assertEqual((console.fake.calls, console.store.check), ([], newer), "the claim of the other person stands and nothing runs")

    def test_a_claim_is_kept_before_the_check_runs_so_that_a_check_that_never_reports_still_holds_the_gap(self):
        console = check_console(silent=True)
        reply = start(console)
        self.assertIn("A check began Thu 5 Nov 2026 09:00 UTC (10:00 CET) by Tino and has not reported.", reply.content)
        self.assertEqual(console.store.check, CheckRecord(started_at="2026-11-05T09:00:00Z", trigger="console", by="Tino"))
        self.assertEqual(console.post("/ops/drift", {"nonce": console.store.nonce_new(TINO, "drift")}).status, 429)

    def test_the_timers_check_is_shown_like_a_persons_and_a_check_that_paused_the_investigation_says_so(self):
        console = check_console()
        console.store.check_put(CheckRecord(started_at=at(hours=-4), trigger="timer", finished_at=at(hours=-4), tripped=True, results=(
            {"control": "A-RELEASE", "layer": "L2", "state": "FAIL", "detail": "the files that run are not the files that were released"},)))
        reply = console.get("/ops")
        self.assertIn("Latest check: Thu 5 Nov 2026 05:00 UTC (06:00 CET), started by the timer. 0 pass, 1 fail and 0 cannot be told.", reply.content)
        self.assertIn("This check paused the investigation", [p.text() for p in reply.root.find_all("p", class_="notice-title")])
        self.assertIn("/ops/pause", reply.links())
        self.assertTrue(reply.form("/ops/drift", has_button="Check now"), "four hours later a person may check again")

    def test_the_form_needs_its_own_token_and_the_role_ops_and_a_refusal_starts_nothing(self):
        console = check_console()
        form = console.get("/ops").form("/ops/drift", has_button="Check now")
        for fields, oid, status in (({}, TINO, 403), ({"nonce": "not-a-token"}, TINO, 403), (form.fields, MAYA, 403), (form.fields, OWNER, 403), (form.fields, STRANGER, 403)):
            with self.subTest(oid=oid, fields=fields):
                self.assertEqual(console.post("/ops/drift", fields, oid=oid).status, status)
        self.assertEqual((console.fake.calls, console.store.check), ([], None))
        self.assertTrue(console.store.nonce_use(form.fields["nonce"], TINO, "drift"), "the refusals did not use up the token")
        self.assertEqual(console.post("/ops/drift", {"nonce": console.store.nonce_new(TINO, "pause")}).status, 403, "a token of another form is no token")
        self.assertEqual(console.get("/ops/drift").status, 405, "a page that starts something is a POST")

    def test_a_console_that_cannot_run_the_check_says_so_and_the_page_still_shows_the_latest_one(self):
        console = Console()
        reply = console.get("/ops")
        self.assertIn("This console cannot start a check.", reply.content)
        self.assertNotIn("/ops/drift", [f.action for f in reply.forms()])
        refused = console.post("/ops/drift", {"nonce": console.store.nonce_new(TINO, "drift")})
        self.assertEqual(refused.status, 503)
        self.assertIn("Nothing was started.", refused.content)

    def test_a_latest_check_that_cannot_be_read_is_said_and_the_rest_of_the_page_shows(self):
        console = Console(store=FailingStore(fail={"check_latest"}, clock=lambda: NOW))
        reply = console.get("/ops")
        self.assertEqual(reply.status, 200)
        self.assertIn("The check cannot be read", [p.text() for p in reply.root.find_all("p", class_="notice-title")])
        self.assertIn("The four switches", reply.headings(2))

    def test_starting_it_writes_nothing_but_the_check_and_its_token(self):
        console = check_console()
        console.seed()
        before = snapshot(console.store)
        start(console)
        self.assertEqual(snapshot(console.store), before)


class ThePastAnswers(unittest.TestCase):
    def make(self):
        console = Console(lessons=lambda: "{}\n")
        return console

    def test_the_file_is_a_post_of_the_role_ops_with_a_token_and_changes_nothing(self):
        console = self.make()
        console.seed()
        form = console.get("/ops").form("/ops/answers", has_button="Download the answers")
        before = snapshot(console.store)
        reply = console.submit(form)
        self.assertEqual((reply.status, reply.text), (200, "{}\n"))
        self.assertEqual(reply.headers["Content-Disposition"], 'attachment; filename="meternaut-answers.jsonl"')
        self.assertTrue(reply.headers["Content-Type"].startswith("text/plain"))
        self.assertEqual(snapshot(console.store), before)
        for fields, oid in (({}, TINO), (form.fields, TINO), (form.fields, MAYA), (form.fields, STRANGER)):
            with self.subTest(oid=oid, fields=fields):
                self.assertEqual(console.post("/ops/answers", fields, oid=oid).status, 403)

    def test_a_console_that_cannot_make_it_says_so(self):
        console = Console()
        self.assertIn("This console cannot make the file.", console.get("/ops").content)
        self.assertEqual(console.post("/ops/answers", {"nonce": console.store.nonce_new(TINO, "answers")}).status, 503)

    def test_the_page_says_what_the_file_holds_and_leaves_out_the_words_of_the_design(self):
        text = self.make().get("/ops").content
        self.assertIn("It holds no name of a person and no name of a resource.", text)
        for word in ("lesson", "Lesson"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
