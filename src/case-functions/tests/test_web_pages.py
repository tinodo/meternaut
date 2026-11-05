import datetime as dt
import unittest
from unittest import mock

from test_web_support import (DISK, MAYA, NOW, OPS, OWNER, SUB, TINO, WRITER, Console, FailingStore, at, make_action, make_case, make_decision, make_plan, make_run)

from cases.models import SettingsRecord, SwitchRecord
from cases.web import core
from cases.web.home import ABOUT

NAV_ALL = ["Home", "What Meternaut did", "My decisions", "What I did here", "What I know about your resources", "Settings", "Standing permissions", "The kill switch"]


def seeded() -> Console:
    console = Console()
    console.seed()
    return console


class TheStartPage(unittest.TestCase):
    def test_one_plain_paragraph_says_what_meternaut_is_and_does(self):
        reply = seeded().get("/")
        self.assertEqual(reply.headings(1), ["Meternaut"])
        self.assertEqual(reply.main.find("p", class_="lead").text(), ABOUT)
        self.assertIn("a person approves every change", ABOUT)
        self.assertIn("the runner", ABOUT)

    def test_what_needs_the_persons_ok_is_listed_with_a_button_link_to_its_page(self):
        reply = seeded().get("/")
        table = reply.table("needs-ok")
        self.assertEqual(table.headers, ["Request", "Estimated saving a month", "Answer by", "Open"])
        self.assertEqual(len(table.rows), 1)
        row = table.rows[0]
        self.assertIn(make_plan().title, row["Request"])
        self.assertIn("planted-disk-1", row["Request"])
        self.assertEqual(row["Estimated saving a month"], "7.17 US dollars")
        self.assertEqual(row["Answer by"], "Sun 8 Nov 2026 08:00 UTC (09:00 CET)")
        link = table.cells[0][3].find("a")
        self.assertEqual(link.attrs["href"], "/ok/plan0001")
        self.assertEqual(link.attrs["class"], "btn primary")
        self.assertEqual(link.text(), f"Review and give your OK for {make_plan().title}")
        self.assertIn("Opening a page approves nothing.", reply.content)

    def test_the_requests_come_soonest_expiry_first(self):
        console = seeded()
        console.store.plan_put(make_plan(plan_id="plan0002", title="Second", expires_at=at(hours=2)))
        console.store.plan_put(make_plan(plan_id="plan0003", title="Third", expires_at=at(hours=1)))
        titles = [row["Request"] for row in console.get("/").table("needs-ok").rows]
        self.assertEqual([t.split(" planted")[0].split(" Delete")[0] for t in titles][:2], ["Third", "Second"])

    def test_a_person_who_is_not_named_sees_nothing_to_answer_and_a_plan_that_is_not_open_or_has_expired_is_not_listed(self):
        console = seeded()
        for who in (MAYA, OWNER, OPS):
            with self.subTest(who=who):
                reply = console.get("/", oid=who)
                self.assertIn("Nothing needs your OK now.", reply.content)
                self.assertFalse(reply.has_table("needs-ok"))
        for changes in (dict(state="approved"), dict(state="declined"), dict(state="expired"), dict(expires_at=at(minutes=-1)), dict(expires_at="not a time")):
            with self.subTest(changes=changes):
                console.store.plan_put(make_plan(**changes))
                self.assertIn("Nothing needs your OK now.", console.get("/").content)

    def test_the_state_of_the_three_switches_is_in_words(self):
        console = seeded()
        reply = console.get("/")
        self.assertEqual([r["State"] for r in reply.table("switches").rows], ["Running.", "Running.", "Running."])
        self.assertEqual([r["Switch"] for r in reply.table("switches").rows], ["Everything", "Changes", "All messages"])
        console.store.switch_put(SwitchRecord("changes", True, "Otto", at(minutes=-5), "drill"))
        console.store.switch_put(SwitchRecord("messages", True, "", "", ""))
        rows = console.get("/").table("switches").rows
        self.assertEqual(rows[1]["State"], "Paused by Otto on Thu 5 Nov 2026 08:55 UTC (09:55 CET). Reason: drill")
        self.assertEqual(rows[2]["State"], "Paused on a time that is not recorded. No reason is recorded.")
        self.assertEqual(rows[1]["What it stops"], "No OK is recorded and the runner makes no change in Azure.")

    def test_a_switch_that_cannot_be_read_is_shown_as_pulled(self):
        console = Console(store=FailingStore(fail={"switch_get"}, clock=lambda: NOW))
        console.seed()
        reply = console.get("/")
        self.assertEqual(reply.status, 200)
        self.assertEqual([r["State"] for r in reply.table("switches").rows], ["Cannot be read: treated as pulled."] * 3)

    def test_what_the_runner_may_change_is_said_in_the_services_words(self):
        reply = seeded().get("/")
        self.assertIn(f"The runner may only {WRITER}. It changes nothing else.", reply.content)

    def test_the_latest_runs_and_cases_are_listed_with_a_link_to_the_notebook(self):
        console = seeded()
        reply = console.get("/")
        run = reply.table("latest-runs").rows[0]
        self.assertEqual((run["Trigger"], run["Result"], run["Cases"], run["Proposed"], run["Needs a person"], run["Errors"]), ("timer", "OK", "3", "3", "0", "0"))
        case = reply.table("latest-cases").rows[0]
        self.assertIn("planted-disk-1", case["Resource"])
        self.assertEqual((case["Status"], case["Recommendation"], case["Confidence (0 to 1)"], case["Estimated saving a month"]), ("Proposed", "Delete", "0.91", "7.17 US dollars"))
        self.assertIn("/why/case0001", reply.links())
        self.assertIn("/history", reply.links())

    def test_five_runs_and_ten_cases_are_shown(self):
        console = seeded()
        for n in range(8):
            console.store.run_put(make_run(run_id=f"run1000{n}", started_at=at(hours=-n - 3)))
        for n in range(14):
            console.store.case_put(make_case(case_id=f"case1000{n:02d}", updated_at=at(minutes=-n)))
        reply = console.get("/")
        self.assertEqual(len(reply.table("latest-runs").rows), 5)
        self.assertEqual(len(reply.table("latest-cases").rows), 10)

    def test_a_part_that_cannot_be_read_says_so_and_the_rest_of_the_page_is_there(self):
        for failing, notice in (("plans_open", "I cannot read the open requests now."), ("runs_recent", "I cannot read the runs now."), ("cases_recent", "I cannot read the cases now.")):
            with self.subTest(failing=failing):
                console = Console(store=FailingStore(fail={failing}, clock=lambda: NOW))
                console.seed()
                reply = console.get("/")
                self.assertEqual(reply.status, 200)
                self.assertIn(notice, reply.content)
                self.assertIn("State of each switch", reply.content)
                self.assertIn("The runner may only", reply.content)
                self.assertEqual(reply.problems, [])

    def test_a_part_that_is_empty_says_so(self):
        reply = Console().get("/")
        self.assertIn("Nothing needs your OK now.", reply.content)
        self.assertIn("No run is recorded yet.", reply.content)
        self.assertIn("No case is recorded yet.", reply.content)


class TheNavigation(unittest.TestCase):
    def names(self, who, path="/"):
        reply = seeded().get(path, oid=who)
        return [a.text() for a in reply.root.find("nav").find_all("a")]

    def test_each_person_sees_the_pages_that_the_role_allows(self):
        self.assertEqual(self.names(TINO), NAV_ALL)
        self.assertEqual(self.names(MAYA), NAV_ALL[:6])
        self.assertEqual(self.names(OWNER), NAV_ALL[:7])
        self.assertEqual(self.names(OPS), NAV_ALL, "the role ops may see the standing permissions and pull a switch")
        self.assertNotIn("The kill switch", self.names(OWNER))

    def test_the_page_that_is_open_is_marked(self):
        console = seeded()
        for path, name in (("/", "Home"), ("/history", "What Meternaut did"), ("/me/decisions", "My decisions"), ("/me/activity", "What I did here"),
                           ("/me/notes", "What I know about your resources"), ("/me/settings", "Settings"), ("/ops/permissions", "Standing permissions"), ("/ops/pause", "The kill switch")):
            with self.subTest(path=path):
                reply = console.get(path)
                current = [a.text() for a in reply.root.find("nav").find_all("a") if a.attrs.get("aria-current") == "page"]
                self.assertEqual(current, [name])

    def test_the_header_names_the_person_and_the_roles(self):
        self.assertIn("Signed in as Maya. Roles: approver.", seeded().get("/", oid=MAYA).content)


class TheNotebook(unittest.TestCase):
    def setUp(self):
        self.console = seeded()
        self.reply = self.console.get("/why/case0001")

    def test_it_holds_the_whole_record_of_the_case(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), ["Notebook: planted-disk-1"])
        found = self.reply.summary(0)
        self.assertEqual(found["Resource name"], "planted-disk-1")
        self.assertEqual(found["Resource group"], "meternaut-test-rg")
        self.assertEqual(found["Kind"], "Managed disk (microsoft.compute/disks)")
        self.assertEqual(found["Resource id"], DISK)
        self.assertEqual(found["Subscription"], SUB)
        self.assertIn("A managed disk that is not attached", found["Found by"])
        self.assertIn("orphan-managed-disk", found["Found by"])
        self.assertTrue(found["Status"].startswith("Proposed. A change is suggested."))
        self.assertEqual(found["Run"], "run00001")
        self.assertIn("/history?run=run00001", self.reply.links())
        self.assertEqual(found["Seen in"], "2 runs")
        self.assertEqual(self.reply.summary(1), {"Cost lines, last 30 days": "7.17 US dollars", "Estimated saving a month": "7.17 US dollars. An estimate from cost lines of the last 30 days."})

    def test_the_typed_facts_that_the_models_saw_are_shown(self):
        table = self.reply.table("facts")
        self.assertEqual(table.headers, ["Fact", "Value"])
        self.assertEqual({r["Fact"]: r["Value"] for r in table.rows}, {"diskState": "unattached", "flags": '{"locked": false}', "sizeBucket": "up to 128", "states": "disconnected, pending"})
        self.assertIn("A name, a tag or a description from the estate never reaches a model.", self.reply.content)

    def test_both_models_words_are_marked_as_written_by_ai(self):
        labels = [p.text() for p in self.reply.main.find_all("p", class_="quote-label")]
        self.assertEqual(labels, ["Written by AI (model: model-detective-x): summary", "Written by AI (model: model-skeptic-y): objection 1"])
        quotes = [q.text() for q in self.reply.main.find_all("blockquote", class_="quote")]
        self.assertEqual(quotes, ["The disk is not attached and nothing uses it.", "It may hold data that somebody wants."])
        self.assertIn("First model: judges whether the resource is waste", self.reply.headings(3))
        self.assertIn("Second model: looks for reasons to keep the resource", self.reply.headings(3))
        self.assertIn("Recommendation Delete Confidence (0 to 1) 0.91", self.reply.content)
        self.assertEqual([self.reply.summary(2)], [{"Recommendation": "Delete", "Confidence (0 to 1)": "0.91"}])

    def test_every_step_has_its_model_tokens_time_and_result(self):
        table = self.reply.table("steps")
        self.assertEqual(table.headers, ["Step", "Model", "Tokens in", "Tokens out", "Milliseconds", "Result", "Note"])
        self.assertEqual(table.rows, [
            {"Step": "evidence", "Model": "none", "Tokens in": "none", "Tokens out": "none", "Milliseconds": "3", "Result": "ok", "Note": ""},
            {"Step": "detective", "Model": "model-detective-x", "Tokens in": "702", "Tokens out": "307", "Milliseconds": "1,200", "Result": "ok", "Note": ""},
            {"Step": "skeptic", "Model": "model-skeptic-y", "Tokens in": "857", "Tokens out": "223", "Milliseconds": "1,500", "Result": "not ok", "Note": "a note of the step"},
        ])

    def test_the_guards_that_fired_are_explained_in_words(self):
        self.assertIn("No guard fired.", self.reply.content)
        self.console.store.case_put(make_case(guards=("locked", "keep-tag", "too-new", "managed-group", "unverified", "something-else")))
        reply = self.console.get("/why/case0001")
        found = reply.summary(2)
        self.assertEqual(found["locked"], "A management lock covers the resource.")
        self.assertEqual(found["keep-tag"], "A tag asks to keep the resource.")
        self.assertEqual(found["too-new"], "The resource is less than 7 days old.")
        self.assertEqual(found["managed-group"], "A platform manages the resource group.")
        self.assertEqual(found["unverified"], "A guard could not be read, so it counts as on.")
        self.assertEqual(found["something-else"], "")
        self.assertIn("no model can lift it", reply.content)

    def test_the_evidence_level_is_the_plans_in_words_or_says_that_there_is_none(self):
        self.console.store.case_put(make_case(plan_id=None))
        self.assertIn("No plan was made for this case, so no evidence level is stored.", self.console.get("/why/case0001").content)
        self.console.store.case_put(make_case(plan_id="plan0001"))
        self.console.store.plan_put(make_plan())
        reply = self.console.get("/why/case0001")
        self.assertIn(make_plan().evidence_level, reply.content)
        self.assertNotIn("No plan was made", reply.content)
        self.assertIn("Cost lines of the last 30 days for this resource: 7.17 US dollars.", reply.content)
        self.console.store.case_put(make_case(plan_id=None, cost_usd_30d=None, saving_usd_month=None))
        reply = self.console.get("/why/case0001")
        self.assertIn("No cost lines of the last 30 days were read for this resource.", reply.content)
        self.assertEqual(reply.summary(1), {"Cost lines, last 30 days": "not available", "Estimated saving a month": "no figure"})

    def test_what_happened_afterwards_shows_the_plan_and_what_the_runner_did(self):
        self.console.store.case_put(make_case(plan_id="plan0001"))
        self.console.store.plan_put(make_plan(state="consumed"))
        self.console.store.action_put(make_action(state="done", started_at=at(minutes=-3), finished_at=at(minutes=-2), result="Deleted. Azure no longer lists the resource.",
                                                  verification={"gone": True, "costAfterUsd": 0.0, "costLinesFrom": "2026-11-06", "costBeforeUsd30d": 7.17, "note": "Confirmed."}))
        reply = self.console.get("/why/case0001")
        self.assertIn("What happened afterwards", reply.headings(2))
        found = reply.summary(3)
        self.assertEqual(found["State of the plan"], "Used. The runner took this plan, and a plan runs once.")
        self.assertEqual(found["Plan code"], "7F3K92QD")
        after = reply.summary(4)
        self.assertEqual(after["State"], "Done.")
        self.assertEqual(after["Result"], "Deleted. Azure no longer lists the resource.")
        self.assertIn("Azure no longer lists the resource.", after["Checked afterwards"])
        self.assertIn("Cost lines after the change: 0.00 US dollars.", after["Checked afterwards"])
        self.assertIn("Cost lines of the 30 days before: 7.17 US dollars.", after["Checked afterwards"])
        self.assertIn("Note: Confirmed.", after["Checked afterwards"])

    def test_the_plan_is_linked_only_for_a_person_who_may_answer_it(self):
        self.console.store.case_put(make_case(plan_id="plan0001"))
        self.console.store.plan_put(make_plan())
        self.assertIn("/ok/plan0001", self.console.get("/why/case0001").links())
        self.assertNotIn("/ok/plan0001", self.console.get("/why/case0001", oid=OWNER).links())
        self.assertIn(make_plan().title, self.console.get("/why/case0001", oid=OWNER).content)

    def test_a_plan_that_has_no_action_yet_says_so(self):
        self.console.store.case_put(make_case(plan_id="plan0001"))
        self.console.store.plan_put(make_plan())
        self.assertIn("The runner has not been asked to change anything for this plan.", self.console.get("/why/case0001").content)

    def test_a_case_that_ended_in_an_error_shows_its_reason_as_a_note_of_meternaut_and_not_as_ai_text(self):
        self.console.store.case_put(make_case(status="error", recommendation=None, confidence=None, summary="the token budget of the run was reached", objections=(), models={}))
        reply = self.console.get("/why/case0001")
        self.assertIn("Why the case ended", reply.headings(2))
        self.assertEqual([p.text() for p in reply.main.find_all("p", class_="quote-label")], ["Recorded by Meternaut"])
        self.assertNotIn("First model", reply.content)
        self.assertIn("the token budget of the run was reached", reply.content)

    def test_the_second_model_that_was_not_asked_and_the_one_without_an_objection_say_so(self):
        self.console.store.case_put(make_case(status="dropped", recommendation="keep", models={"detective": "model-detective-x", "skeptic": None}, objections=()))
        reply = self.console.get("/why/case0001")
        self.assertIn("The second model was not asked.", reply.content)
        self.console.store.case_put(make_case(objections=()))
        self.assertIn("The second model raised no objection.", self.console.get("/why/case0001").content)
        self.console.store.case_put(make_case(models={}))
        self.assertIn("Model: not recorded.", self.console.get("/why/case0001").content)

    def test_a_case_with_no_steps_and_no_facts_says_so(self):
        self.console.store.case_put(make_case(steps=(), facts={}))
        reply = self.console.get("/why/case0001")
        self.assertIn("No step is recorded for this case.", reply.content)
        self.assertIn("No typed fact is recorded for this case.", reply.content)

    def test_text_from_the_estate_or_a_model_is_quoted_and_is_never_a_link_or_a_control(self):
        quotes = self.reply.main.find_all("blockquote", class_="quote")
        for quote in quotes:
            self.assertEqual([n.tag for n in quote.walk() if n.tag in ("a", "button", "input", "form", "select", "textarea")], [])
        self.assertIn("never a link or a control", self.reply.content)

    def test_a_case_that_does_not_exist_is_a_404(self):
        reply = self.console.get("/why/nothing")
        self.assertEqual(reply.status, 404)
        self.assertIn("I cannot find this case", reply.content)

    def test_the_page_says_that_it_shows_text_written_by_ai(self):
        self.assertIn("Written by AI (models: model-detective-x, model-skeptic-y). A person approves every change.", self.reply.root.find("footer").text())


class TheHistory(unittest.TestCase):
    def setUp(self):
        self.console = seeded()
        self.console.store.run_put(make_run(run_id="run00002", started_at=at(hours=-1), ok=False, reason="no detector could read any subscription", leads=0, cases=0, proposed=0,
                                            tokens=0, seconds=3, notes=()))
        self.console.store.run_put(make_run(run_id="run00003", started_at=at(minutes=-5), finished_at=None, notes=("a", "b")))
        self.console.store.case_put(make_case(case_id="case0002", run_id="run00002", resource_name="other-disk", status="needs_human", recommendation="investigate",
                                              confidence=0.5, saving_usd_month=None, updated_at=at(hours=-1)))

    def test_every_run_is_there_with_all_of_its_numbers(self):
        reply = self.console.get("/history")
        table = reply.table("runs")
        self.assertEqual(table.headers, ["Started", "Trigger", "Result", "Leads", "Cases", "Proposed", "Needs a person", "Dropped", "Errors", "Tokens", "Seconds", "Notes", "Cases of the run"])
        by_start = {row["Started"].split(" (")[0]: row for row in table.rows}
        ok = by_start["Thu 5 Nov 2026 07:00 UTC"]
        self.assertEqual((ok["Trigger"], ok["Result"], ok["Leads"], ok["Cases"], ok["Proposed"], ok["Needs a person"], ok["Dropped"], ok["Errors"], ok["Tokens"], ok["Seconds"], ok["Notes"]),
                         ("timer", "OK", "4", "3", "3", "0", "0", "0", "2,089", "28", "one source was not read"))
        failed = by_start["Thu 5 Nov 2026 08:00 UTC"]
        self.assertEqual((failed["Result"], failed["Notes"]), ("Failed: no detector could read any subscription", "none"))
        unfinished = by_start["Thu 5 Nov 2026 08:55 UTC"]
        self.assertEqual((unfinished["Result"], unfinished["Notes"]), ("Started, not finished", "a b"))
        self.assertEqual([row["Started"].split(" (")[0] for row in table.rows], ["Thu 5 Nov 2026 08:55 UTC", "Thu 5 Nov 2026 08:00 UTC", "Thu 5 Nov 2026 07:00 UTC"], "newest first")

    def test_every_case_is_there_with_its_recommendation_confidence_and_estimated_saving_and_a_link_to_the_notebook(self):
        reply = self.console.get("/history")
        table = reply.table("cases")
        self.assertEqual(table.headers, ["Resource", "Found by", "Status", "Recommendation", "Confidence (0 to 1)", "Estimated saving a month", "Last updated", "Notebook"])
        self.assertEqual([r["Status"] for r in table.rows], ["Needs a person", "Proposed"], "most recently updated first")
        first = next(r for r in table.rows if r["Status"] == "Proposed")
        self.assertIn("planted-disk-1", first["Resource"])
        self.assertIn("Managed disk (microsoft.compute/disks)", first["Resource"])
        self.assertIn("Resource group meternaut-test-rg.", first["Resource"])
        self.assertIn("A managed disk that is not attached", first["Found by"])
        self.assertEqual((first["Recommendation"], first["Confidence (0 to 1)"], first["Estimated saving a month"]), ("Delete", "0.91", "7.17 US dollars"))
        second = next(r for r in table.rows if r["Status"] == "Needs a person")
        self.assertEqual((second["Recommendation"], second["Confidence (0 to 1)"], second["Estimated saving a month"]), ("Investigate", "0.50", "no figure"))
        self.assertIn("/why/case0001", reply.links())
        self.assertIn("/why/case0002", reply.links())

    def test_a_run_filters_the_cases(self):
        reply = self.console.get("/history", query={"run": "run00002"})
        self.assertEqual(reply.status, 200)
        rows = reply.table("cases").rows
        self.assertEqual(len(rows), 1)
        self.assertIn("other-disk", rows[0]["Resource"])
        self.assertIn("Cases of the run run00002.", reply.content)
        self.assertIn("/history", reply.links(), "a link shows all cases again")
        self.assertEqual(len(reply.table("runs").rows), 3, "every run is still listed")
        self.assertIn("Selected.", reply.table("runs").rows[1]["Started"])
        self.assertEqual(sum("Selected." in r["Started"] for r in reply.table("runs").rows), 1)
        self.assertIn("/history?run=run00002", reply.links())

    def test_a_run_with_no_cases_and_an_unknown_run_say_so(self):
        reply = self.console.get("/history", query={"run": "run00003"})
        self.assertFalse(reply.has_table("cases"))
        self.assertIn("No case is recorded for this run.", reply.content)
        self.assertIn("No case is recorded for this run.", self.console.get("/history", query={"run": "nothing"}).content)

    def test_a_run_id_that_is_not_a_run_id_is_said_so_and_shows_every_case(self):
        for bad in ("a b", "<script>", "x" * 81, "a/b", "%00"):
            with self.subTest(bad=bad):
                reply = self.console.get("/history", query={"run": bad})
                self.assertEqual(reply.status, 200)
                self.assertIn("That run id is not valid", reply.content)
                self.assertEqual(len(reply.table("cases").rows), 2)

    def test_the_page_is_complete_the_latest_100_cases_and_the_cases_of_any_run(self):
        console = seeded()
        for n in range(130):
            console.store.case_put(make_case(case_id=f"c{n:04d}", run_id="run00009", updated_at=at(minutes=-n - 1), resource_name=f"disk-{n}"))
        console.store.case_put(make_case(case_id="old", run_id="run00001", resource_name="very-old", updated_at=at(days=-30)))
        reply = console.get("/history")
        self.assertEqual(len(reply.table("cases").rows), 100)
        self.assertIn("The latest 100 cases, most recently updated first.", reply.content)
        self.assertNotIn("very-old", reply.content)
        older = console.get("/history", query={"run": "run00001"})
        self.assertIn("very-old", older.content, "a run that is far back is complete")

    def test_twenty_runs_are_shown_newest_first(self):
        console = Console()
        for n in range(25):
            console.store.run_put(make_run(run_id=f"r{n:03d}", started_at=at(hours=-n)))
        rows = console.get("/history").table("runs").rows
        self.assertEqual(len(rows), 20)

    def test_the_words_of_every_status_are_explained(self):
        reply = self.console.get("/history")
        self.assertIn("What the status words mean", reply.headings(2))
        legend = reply.summary(0)
        self.assertEqual(list(legend), ["Proposed", "Needs a person", "Dropped", "Error", "Waiting for an OK", "Approved", "Running", "Done", "Failed", "Declined", "Expired", "Done and verified"])

    def test_it_is_not_a_cost_report(self):
        reply = self.console.get("/history")
        self.assertIn("It is not a cost report.", reply.content)
        for node in reply.root.walk():
            self.assertNotIn(node.tag, ("svg", "canvas", "img", "script", "video"))
        for word in ("chart", "dashboard", "graph"):
            self.assertNotIn(word, reply.content.lower())

    def test_an_empty_history_says_so(self):
        reply = Console().get("/history")
        self.assertIn("No run is recorded yet.", reply.content)
        self.assertIn("No case is recorded yet.", reply.content)
        reply = Console(store=FailingStore(fail={"runs_recent", "cases_recent"}, clock=lambda: NOW)).get("/history")
        self.assertEqual(reply.status, 200)
        self.assertIn("The runs cannot be read", reply.content)
        self.assertIn("The cases cannot be read", reply.content)

    def test_a_status_that_is_not_in_the_list_is_shown_as_stored(self):
        self.console.store.case_put(make_case(case_id="case0003", status="something new"))
        self.assertIn("something new", [r["Status"] for r in self.console.get("/history").table("cases").rows])


class TheDecisions(unittest.TestCase):
    def setUp(self):
        self.console = seeded()
        self.console.store.decision_put(make_decision())

    def rows(self, who=TINO):
        return self.console.get("/me/decisions", oid=who).table("decisions").rows

    def test_a_queued_change_says_when_it_starts_and_that_a_deletion_cannot_be_undone(self):
        self.console.store.plan_put(make_plan(state="approved"))
        self.console.store.action_put(make_action())
        row = self.rows()[0]
        self.assertEqual(row["When"], "Thu 5 Nov 2026 08:59 UTC (09:59 CET)")
        self.assertIn(make_plan().title, row["Request"])
        self.assertIn("Plan code 7F3K92QD", row["Request"])
        self.assertEqual(row["Your answer"], "Your OK")
        self.assertEqual(row["What came of it"], "Queued. It has not started. It starts at Thu 5 Nov 2026 09:01 UTC (10:01 CET). Once it has run, a deletion cannot be undone.")

    def test_what_ran_and_the_outcome_are_in_plain_words(self):
        self.console.store.plan_put(make_plan(state="consumed"))
        cases = (
            (dict(state="running", started_at=at(minutes=-1)), ["Running.", "A deletion cannot be undone."]),
            (dict(state="done", finished_at=at(), result="Deleted. Azure no longer lists the resource.", verification={"gone": True}),
             ["Done.", "Deleted. Azure no longer lists the resource.", "Azure no longer lists the resource.", "A deletion cannot be undone."]),
            (dict(state="verified", result="Deleted.", verification={"gone": True, "costAfterUsd": 0.0, "note": "Confirmed: no cost lines for this resource after the day of the change."}),
             ["Done and verified.", "Cost lines after the change: 0.00 US dollars.", "Confirmed: no cost lines", "A deletion cannot be undone."]),
            (dict(state="unknown", result="Azure accepted the delete and still lists the resource."), ["The result is not known yet.", "A deletion cannot be undone."]),
            (dict(state="failed", result="Stopped before the change: the disk is not unattached any more. Nothing was changed.", error="Stopped before the change: x"),
             ["Failed.", "Stopped before the change: the disk is not unattached any more. Nothing was changed.", "Stopped before the change: x"]),
            (dict(state="withdrawn", result="Withdrawn before it started. Nothing changed."), ["Withdrawn before it started. Nothing changed."]),
        )
        for changes, expected in cases:
            with self.subTest(state=changes["state"]):
                self.console.store.action_put(make_action(**changes))
                text = self.rows()[0]["What came of it"]
                for fragment in expected:
                    self.assertIn(fragment, text)
                if changes["state"] in ("failed", "withdrawn"):
                    self.assertNotIn("cannot be undone", text)
        self.assertEqual(self.rows()[0]["What came of it"], "Withdrawn before it started. Nothing changed.", "the sentence is not said twice")

    def test_no_leave_it_as_it_is_and_the_other_answers_are_listed_too(self):
        store = self.console.store
        store.decision_put(make_decision(plan_id="plan0002", decision="decline", note="Not now", at=at(minutes=-30)))
        store.decision_put(make_decision(plan_id="plan0003", decision="not_mine", at=at(minutes=-40)))
        store.decision_put(make_decision(plan_id="plan0004", decision="ask", note="Is it the standby?", at=at(minutes=-50)))
        for plan_id, state in (("plan0002", "declined"), ("plan0003", "withdrawn"), ("plan0004", "open")):
            store.plan_put(make_plan(plan_id=plan_id, state=state))
        rows = self.rows()
        answers = [r["Your answer"] for r in rows]
        self.assertEqual(answers, ["Your OK", "No, leave it as it is Your note: Not now", "Not mine", "A question or suggestion Your note: Is it the standby?"])
        outcomes = [r["What came of it"] for r in rows]
        self.assertEqual(outcomes[1], "You said no. Nothing changed, and the request is closed.")
        self.assertEqual(outcomes[2], "You said that this is not yours. Nothing is approved.")
        self.assertEqual(outcomes[3], "You asked a question or made a suggestion. It approves nothing. Open. It waits for an OK.")

    def test_a_decision_with_no_plan_in_the_store_says_so_and_keeps_the_code(self):
        self.console.store.plans.clear()
        row = self.rows()[0]
        self.assertEqual(row["Request"], "The request is no longer stored. Plan code 7F3K92QD")
        self.assertEqual(row["What came of it"], "The request is no longer stored.")

    def test_only_the_persons_own_decisions_are_listed(self):
        self.console.store.decision_put(make_decision(approver_oid=MAYA, approver_name="Maya", note="MAYA-NOTE"))
        self.assertNotIn("MAYA-NOTE", self.console.get("/me/decisions").text)
        self.assertEqual(len(self.rows(MAYA)), 1)
        self.assertIn("MAYA-NOTE", self.console.get("/me/decisions", oid=MAYA).text)
        self.assertIn("You have not answered a request yet.", self.console.get("/me/decisions", oid=OWNER).content)

    def test_the_request_is_linked_only_for_a_person_who_is_named(self):
        self.assertIn("/ok/plan0001", self.console.get("/me/decisions").links())
        self.console.store.plan_put(make_plan(approvers=(MAYA,)))
        self.assertNotIn("/ok/plan0001", self.console.get("/me/decisions").links())

    def test_it_invites_the_person_to_check_that_each_approval_is_theirs(self):
        self.assertIn("Check that each approval is one that you gave.", self.console.get("/me/decisions").content)

    def test_fifty_decisions_are_shown_newest_first(self):
        for n in range(60):
            self.console.store.decision_put(make_decision(plan_id=f"p{n:03d}", at=at(minutes=-n - 5)))
        rows = self.rows()
        self.assertEqual(len(rows), 50)
        self.assertEqual(rows[0]["When"], "Thu 5 Nov 2026 08:59 UTC (09:59 CET)")


class WhatIDidHere(unittest.TestCase):
    def setUp(self):
        self.console = seeded()
        self.console.store.decision_put(make_decision())
        self.console.store.plan_put(make_plan(state="approved"))
        self.console.store.action_put(make_action())

    def test_it_says_that_no_standing_permission_exists(self):
        self.assertIn("No standing permission exists yet.", self.console.get("/me/activity").content)

    def test_a_queued_change_of_an_approved_plan_shows_its_start_and_a_cancel_until_then(self):
        reply = self.console.get("/me/activity")
        self.assertEqual(reply.headings(2), ["Delete an unattached managed disk: planted-disk-1"])
        found = reply.summary(0)
        self.assertEqual(found["What changed"], make_plan().title)
        self.assertEqual(found["Where"], f"Resource group meternaut-test-rg, subscription {SUB}")
        self.assertEqual(found["State"], "Queued. It has not started.")
        self.assertEqual(found["Starts at"], "Thu 5 Nov 2026 09:01 UTC (10:01 CET)")
        self.assertIn("The change starts at Thu 5 Nov 2026 09:01 UTC (10:01 CET).", reply.content)
        cancel = reply.form("/ok/plan0001/withdraw")
        self.assertEqual(cancel.buttons, [("", "", "Cancel my OK")])
        self.assertTrue(self.console.store.nonce_use(cancel.fields["nonce"], TINO, "plan0001"))

    def test_the_cancel_ends_at_the_start_time(self):
        self.console.now = self.console.now.replace(minute=2)
        reply = self.console.get("/me/activity")
        self.assertEqual(reply.forms(), [])
        self.assertIn("The start time has passed.", reply.content)

    def test_a_change_that_was_made_shows_the_result_and_what_the_check_found(self):
        self.console.store.plan_put(make_plan(state="consumed"))
        self.console.store.action_put(make_action(state="verified", started_at=at(minutes=-3), finished_at=at(minutes=-2), verified_at=at(minutes=-1),
                                                  result="Deleted. Azure no longer lists the resource.", verification={"gone": True, "checkedAt": at(minutes=-2)}))
        reply = self.console.get("/me/activity")
        found = reply.summary(0)
        self.assertEqual((found["State"], found["Result"]), ("Done and verified.", "Deleted. Azure no longer lists the resource."))
        self.assertIn("Azure no longer lists the resource.", found["Checked afterwards"])
        self.assertIn("Thu 5 Nov 2026", found["Verified"])
        self.assertEqual(reply.forms(), [])

    def test_only_the_changes_of_the_persons_own_plans_are_listed(self):
        store = self.console.store
        store.plan_put(make_plan(plan_id="plan0002", approvers=(MAYA,), resource_name="maya-disk"))
        store.action_put(make_action(plan_id="plan0002", resource_id=DISK + "2"))
        self.assertEqual(len(self.console.get("/me/activity").headings(2)), 1)
        self.assertNotIn("maya-disk", self.console.get("/me/activity").content)
        reply = self.console.get("/me/activity", oid=MAYA)
        self.assertEqual(reply.headings(2), ["Delete an unattached managed disk: maya-disk"])
        self.assertEqual(reply.forms(), [], "she did not approve it, so she cannot cancel it")
        self.assertIn("Nothing was changed for your plans yet.", self.console.get("/me/activity", oid=OWNER).content)

    def test_a_plan_that_a_person_answered_is_listed_even_when_the_plan_names_somebody_else_now(self):
        self.console.store.plan_put(make_plan(approvers=(MAYA,), state="approved"))
        self.assertEqual(len(self.console.get("/me/activity").headings(2)), 1)

    def test_an_action_whose_plan_is_gone_is_shown_from_its_own_record(self):
        self.console.store.plans.clear()
        reply = self.console.get("/me/activity")
        self.assertEqual(reply.headings(2), ["Delete an unattached managed disk: planted-disk-1"])
        self.assertEqual(reply.summary(0)["Where"], f"Resource group meternaut-test-rg, subscription {SUB}")
        self.assertEqual(reply.forms(), [])

    def test_a_store_that_cannot_be_read_is_said_plainly(self):
        console = Console(store=FailingStore(fail={"actions_recent"}, clock=lambda: NOW))
        reply = console.get("/me/activity")
        self.assertEqual(reply.status, 200)
        self.assertIn("The changes cannot be read", reply.content)


class Times(unittest.TestCase):
    def setUp(self):
        self.console = seeded()

    def zone(self, name, offset_hours, label):
        return mock.patch.object(core, "zone_of", return_value=dt.timezone(dt.timedelta(hours=offset_hours), label))

    def test_a_time_is_shown_in_utc_and_in_the_persons_zone_with_its_name(self):
        with self.zone("America/New_York", -5, "EST"):
            reply = self.console.get("/ok/plan0001")
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (03:00 EST)", reply.content)

    def test_a_zone_on_another_day_names_the_day(self):
        self.console.store.plan_put(make_plan(expires_at="2026-11-08T20:30:00Z"))
        with self.zone("Asia/Tokyo", 9, "JST"):
            reply = self.console.get("/ok/plan0001")
        self.assertIn("Sun 8 Nov 2026 20:30 UTC (Mon 9 Nov 2026 05:30 JST)", reply.content)

    def test_utc_and_a_zone_that_is_not_known_show_utc_alone(self):
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="UTC"))
        self.assertIn("Sun 8 Nov 2026 08:00 UTC.", self.console.get("/ok/plan0001").content)
        self.assertNotIn("(", self.console.get("/ok/plan0001").root.find("footer").find_all("p")[1].text())
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="Mars/Olympus_Mons"))
        reply = self.console.get("/ok/plan0001")
        self.assertIn("Sun 8 Nov 2026 08:00 UTC.", reply.content)
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="../../etc/passwd"))
        self.assertIn("Sun 8 Nov 2026 08:00 UTC.", self.console.get("/ok/plan0001").content)

    def test_a_person_whose_settings_cannot_be_read_still_gets_the_page_in_utc(self):
        console = Console(store=FailingStore(fail={"settings_get"}, clock=lambda: NOW))
        console.seed()
        reply = console.get("/ok/plan0001")
        self.assertEqual(reply.status, 200)
        self.assertIn("Sun 8 Nov 2026 08:00 UTC.", reply.content)

    def test_a_time_that_is_not_a_time_is_shown_as_it_is_stored_and_escaped(self):
        self.console.store.plan_put(make_plan(expires_at="<b>soon</b>"))
        reply = self.console.get("/ok/plan0001")
        self.assertIn("&lt;b&gt;soon&lt;/b&gt;", reply.text)
        self.assertNotIn("<b>", reply.text)

    def test_the_time_zone_database_of_the_machine_is_used_when_it_has_the_zone(self):
        try:
            import zoneinfo
            zoneinfo.ZoneInfo("Europe/Amsterdam")
        except Exception:  # noqa: BLE001
            self.skipTest("this machine has no time zone database")
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (09:00 CET)", self.console.get("/ok/plan0001").content)
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="America/New_York"))
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (03:00 EST)", self.console.get("/ok/plan0001").content)
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="Australia/Sydney"))
        self.assertIn("Sun 8 Nov 2026 08:00 UTC (19:00 AEDT)", self.console.get("/ok/plan0001").content)

    def test_without_a_time_zone_database_a_short_list_of_names_is_accepted_and_times_stay_in_utc(self):
        core.zone_index.cache_clear()
        try:
            with mock.patch.object(core.zoneinfo, "available_timezones", return_value=set()), mock.patch.object(core.zoneinfo, "ZoneInfo", side_effect=KeyError("no database")):
                self.assertEqual(core.canonical_zone("europe/amsterdam"), "Europe/Amsterdam")
                self.assertEqual(core.canonical_zone("UTC"), "UTC")
                self.assertIsNone(core.canonical_zone("Mars/Olympus_Mons"))
                self.assertIsNone(core.canonical_zone("Europe"))
                self.assertIsNone(core.zone_of("Europe/Amsterdam"))
                self.assertIn("Sun 8 Nov 2026 08:00 UTC.", self.console.get("/ok/plan0001").content)
        finally:
            core.zone_index.cache_clear()

    def test_the_names_are_taken_from_the_database_with_its_spelling(self):
        core.zone_index.cache_clear()
        with mock.patch.object(core.zoneinfo, "available_timezones", return_value={"Europe/Amsterdam", "UTC"}):
            try:
                self.assertEqual(core.canonical_zone("EUROPE/amsterdam"), "Europe/Amsterdam")
                self.assertIsNone(core.canonical_zone("Europe/Berlin"))
            finally:
                core.zone_index.cache_clear()


if __name__ == "__main__":
    unittest.main()
