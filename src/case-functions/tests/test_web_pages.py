import datetime as dt
import re
import unittest
from unittest import mock

from support import APP_ROOT
from test_web_support import (MAYA, NOW, OPS, OWNER, TINO, VM, Console, FailingStore, at, make_action, make_advice, make_advice_case, make_case, make_decision, make_plan, snapshot)

from cases.models import SettingsRecord
from cases.web import core

VM_ID = VM

NAV_ALL = ["Decisions", "History", "Settings", "Operations"]
HEADLINE = "Delete the unattached disk planted-disk-1 in group meternaut-test-rg"


def seeded() -> Console:
    console = Console()
    console.seed()
    return console


def waiting(reply) -> list[tuple[str, str, str]]:
    """The rows of "Waiting for you": the headline, what it is worth with the risk and the age, and where its one button goes."""
    (listing,) = reply.main.find_all("ol", class_="rows")
    return [(li.find("p", class_="row-title").text(), li.find("p", class_="row-meta").text(), li.find("a").attrs["href"]) for li in listing.find_all("li")]


def more_plans(console: Console, count: int, *, saving=lambda n: 1.0 + n, seen=lambda n: -3) -> None:
    """`count` more open requests, each for a disk of its own."""
    for n in range(count):
        console.store.case_put(make_case(case_id=f"case1{n:03d}", resource_name=f"disk-{n}", saving_usd_month=saving(n), first_seen_at=at(days=seen(n)), plan_id=f"plan1{n:03d}"))
        console.store.plan_put(make_plan(plan_id=f"plan1{n:03d}", case_id=f"case1{n:03d}", resource_name=f"disk-{n}", saving_usd_month=saving(n)))


class TheDecisionsPage(unittest.TestCase):
    def test_it_is_a_short_page_of_two_lists_and_nothing_else(self):
        reply = seeded().get("/")
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), ["Decisions"])
        self.assertEqual(reply.headings(2), ["Waiting for you (1)", "Recently decided"])
        self.assertEqual(reply.root.find_all("table"), [], "no table: a list of what waits and a list of what was decided")
        self.assertEqual(reply.forms(), [])

    def test_a_row_is_the_headline_what_it_is_worth_with_its_level_the_risk_the_age_and_one_button(self):
        reply = seeded().get("/")
        self.assertEqual(waiting(reply), [(HEADLINE, "About 7.17 US dollars a month, Expected. Risk: medium. Found 3 days ago.", "/ok/plan0001")])
        button = reply.main.find("ol", class_="rows").find("a")
        self.assertEqual((button.attrs["class"], button.text()), ("btn primary", f"Open: {HEADLINE}"))
        self.assertEqual(len(reply.main.find("ol", class_="rows").find_all("a")), 1, "one button for each row")

    def test_the_largest_saving_comes_first_then_the_one_that_has_waited_longest(self):
        console = seeded()
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        more_plans(console, 2, saving=lambda n: 30.0, seen=lambda n: (-3, -10)[n])
        order = [href for _, _, href in waiting(console.get("/"))]
        self.assertEqual(order, ["/ok/plan0002", "/ok/plan1001", "/ok/plan1000", "/ok/plan0001"])

    def test_a_request_that_the_person_put_off_goes_to_the_end_and_says_so(self):
        console = seeded()
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        console.store.decision_put(make_decision(plan_id="plan0002", decision="later"))
        rows = waiting(console.get("/"))
        self.assertEqual([href for _, _, href in rows], ["/ok/plan0001", "/ok/plan0002"])
        self.assertTrue(rows[1][1].endswith("You chose to decide later."), rows[1][1])
        self.assertNotIn("decide later", rows[0][1])

    def test_a_request_of_advice_says_that_its_saving_is_a_scenario_when_azure_advisor_is_the_only_basis(self):
        console = seeded()
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        self.assertEqual(waiting(console.get("/"))[0][1], "About 120.00 US dollars a month, Scenario. Risk: low. Found 3 days ago.")

    def test_a_person_who_is_not_named_sees_nothing_to_answer_and_a_plan_that_is_not_open_or_has_expired_is_not_listed(self):
        console = seeded()
        for who in (MAYA, OWNER, OPS):
            with self.subTest(who=who):
                reply = console.get("/", oid=who)
                self.assertIn("Nothing waits for you.", reply.content)
                self.assertEqual(reply.main.find_all("ol", class_="rows"), [])
        for changes in (dict(state="approved"), dict(state="declined"), dict(state="expired"), dict(expires_at=at(minutes=-1)), dict(expires_at="not a time")):
            with self.subTest(changes=changes):
                console.store.plan_put(make_plan(**changes))
                self.assertIn("Nothing waits for you.", console.get("/").content)

    def test_when_nothing_waits_one_sentence_says_so_and_when_the_next_search_is(self):
        console = Console()
        self.assertIn("Nothing waits for you. The next search is tomorrow at 06:30.", console.get("/").content)
        console.now = NOW.replace(hour=4)
        self.assertIn("Nothing waits for you. The next search is at 06:30.", console.get("/").content)
        self.assertIn("Nothing was decided yet.", console.get("/").content)

    def test_the_time_of_the_next_search_is_the_one_of_the_daily_timer(self):
        source = (APP_ROOT / "function_app.py").read_text(encoding="utf-8")
        second, minute, hour, *_ = re.search(r'TIMER_SCHEDULE = "([^"]+)"', source).group(1).split()
        self.assertEqual((second, core.WATCH_AT), ("0", (int(hour), int(minute))), "the page says when the timer of function_app.py runs, in UTC")

    def test_ten_rows_are_shown_and_all_of_them_on_request(self):
        console = seeded()
        more_plans(console, 13)
        reply = console.get("/")
        self.assertEqual(len(waiting(reply)), 10)
        self.assertIn("Waiting for you (14)", reply.headings(2))
        self.assertIn("4 more wait. Show all.", reply.content)
        self.assertIn("/?all=1", reply.links())
        everything = console.get("/", query={"all": "1"})
        self.assertEqual(len(waiting(everything)), 14)
        self.assertNotIn("more wait", everything.content)

    def held(self, console: Console, count: int, **changes) -> None:
        """`count` findings of the investigation that need a person and that no request waits for."""
        for n in range(count):
            fields = dict(case_id=f"case3{n:03d}", resource_id=f"{VM_ID}-{n}", resource_name=f"endpoint-{n}", plan_id=None)
            fields.update(changes)
            console.store.case_put(make_advice_case(**fields))

    def test_findings_that_no_request_waits_for_are_counted_in_one_sentence_so_that_nothing_is_dropped_silently(self):
        console = seeded()
        self.assertNotIn("held back", console.get("/").content, "none is held")
        self.held(console, 3)
        reply = console.get("/")
        self.assertIn("3 findings are held back: no measurement backs them yet, or the places for requests are full. The AIs look at them again at the next investigation.", reply.content)
        self.assertEqual(len(waiting(reply)), 1, "they are not rows: nobody has to decide them")
        self.held(console, 1, case_id="case3900", resource_id=f"{VM_ID}-x", resource_name="endpoint-x")
        self.assertIn("4 findings are held back", console.get("/").content)

    def test_one_finding_is_said_in_the_singular_and_the_sentence_is_there_when_nothing_waits(self):
        console = Console()
        self.held(console, 1)
        content = console.get("/").content
        self.assertIn("Nothing waits for you. The next search is tomorrow at 06:30.", content)
        self.assertIn("1 finding is held back: no measurement backs it yet, or the places for requests are full. The AIs look at it again at the next investigation.", content)

    def test_a_finding_with_a_request_an_answered_one_a_finding_of_another_detector_and_one_that_is_over_are_not_held(self):
        console = seeded()
        self.held(console, 1, case_id="case3001", status="expired")
        self.held(console, 1, case_id="case3002", resource_id=f"{VM_ID}-b", detector="orphan-managed-disk")
        self.held(console, 1, case_id="case3003", resource_id=f"{VM_ID}-c", plan_id="plan3003")
        console.store.plan_put(make_advice(plan_id="plan3003", case_id="case3003", resource_id=f"{VM_ID}-c"))
        self.assertNotIn("held back", console.get("/").content)
        self.held(console, 1, case_id="case3004", resource_id=f"{VM_ID}-d")
        console.store.plan_put(make_advice(plan_id="plan3004", case_id="case3004", resource_id=f"{VM_ID}-d", state="declined", created_at=at(days=-2)))
        self.assertNotIn("held back", console.get("/").content, "a person answered it lately: nobody is to be asked again")

    def test_a_store_that_cannot_be_read_says_nothing_of_the_held_findings_and_the_page_is_there(self):
        console = Console(store=FailingStore(fail={"cases_recent"}, clock=lambda: NOW))
        console.seed()
        reply = console.get("/")
        self.assertEqual(reply.status, 200)
        self.assertNotIn("held back", reply.content)
        self.assertIn("Waiting for you (1)", reply.headings(2))

    def test_the_last_five_decisions_are_one_line_each_newest_first(self):
        console = seeded()
        for n in range(7):
            console.store.plan_put(make_plan(plan_id=f"plan2{n:03d}", case_id=f"case2{n:03d}", resource_name=f"gone-{n}", state="declined"))
            console.store.decision_put(make_decision(plan_id=f"plan2{n:03d}", decision="decline", at=at(hours=-n - 1)))
        reply = console.get("/")
        listing = [li.text() for li in reply.main.find("ul", class_="feed").find_all("li")]
        self.assertEqual(listing, [f"Delete the unattached disk gone-{n} in group meternaut-test-rg: Declined, Tino on Thu 5 Nov." for n in range(5)])

    def test_an_advice_that_nobody_answered_is_no_row_of_recently_decided_and_a_change_that_nobody_answered_is(self):
        console = seeded()
        for n in range(6):
            console.store.case_put(make_advice_case(case_id=f"case4{n:03d}", resource_id=f"{VM_ID}-e{n}", resource_name=f"endpoint-e{n}", plan_id=f"plan4{n:03d}"))
            console.store.plan_put(make_advice(plan_id=f"plan4{n:03d}", case_id=f"case4{n:03d}", resource_id=f"{VM_ID}-e{n}", state="expired", created_at=at(days=-6), expires_at=at(days=-1)))
        console.store.plan_put(make_plan(plan_id="plan0005", case_id="case0005", state="expired", created_at=at(days=-6), expires_at=at(days=-2)))
        listing = [li.text() for li in console.get("/").main.find("ul", class_="feed").find_all("li")]
        self.assertEqual(len(listing), 1, "six advices that expired are not rows, and the change that expired is")
        self.assertIn("Expired", listing[0])
        self.assertNotIn("oversized-vm-1", listing[0])

    def test_what_moved_to_the_page_of_the_platform_team_is_not_on_the_start_page(self):
        reply = seeded().get("/")
        for gone in ("What Meternaut can change in Azure", "State of each switch", "The kill switch", "Latest runs", "Latest cases", "Needs a person"):
            self.assertNotIn(gone, reply.content)
        for table in ("switches", "latest-runs", "latest-cases", "needs-ok"):
            self.assertFalse(reply.has_table(table))

    def test_a_part_that_cannot_be_read_says_so_and_the_rest_of_the_page_is_there(self):
        for failing, notice, kept in (("plans_open", "I cannot read the open requests now.", "Recently decided"), ("plans_recent", "I cannot read the recent decisions now.", "Waiting for you")):
            with self.subTest(failing=failing):
                console = Console(store=FailingStore(fail={failing}, clock=lambda: NOW))
                console.seed()
                reply = console.get("/")
                self.assertEqual(reply.status, 200)
                self.assertIn(notice, reply.content)
                self.assertIn(kept, reply.content)
                self.assertEqual(reply.problems, [])

    def test_the_page_only_shows_and_changes_nothing(self):
        console = seeded()
        before = snapshot(console.store)
        console.get("/")
        console.get("/", query={"all": "1"})
        self.assertEqual(snapshot(console.store), before)


class TheNavigation(unittest.TestCase):
    def names(self, who, path="/"):
        reply = seeded().get(path, oid=who)
        return [a.text() for a in reply.root.find("nav").find_all("a")]

    def test_each_person_sees_the_pages_that_the_role_allows(self):
        self.assertEqual(self.names(TINO), NAV_ALL)
        self.assertEqual(self.names(MAYA), NAV_ALL[:3])
        self.assertEqual(self.names(OWNER), NAV_ALL[:3])
        self.assertEqual(self.names(OPS), NAV_ALL, "the role ops sees Operations")

    def test_the_page_that_is_open_is_marked(self):
        console = seeded()
        for path, name in (("/", "Decisions"), ("/history", "History"), ("/me/decisions", "History"), ("/me/activity", "History"), ("/me/settings", "Settings"),
                           ("/me/notes", "Settings"), ("/ops", "Operations"), ("/ops/runs", "Operations"), ("/ops/permissions", "Operations"), ("/ops/pause", "Operations")):
            with self.subTest(path=path):
                reply = console.get(path)
                current = [a.text() for a in reply.root.find("nav").find_all("a") if a.attrs.get("aria-current") == "page"]
                self.assertEqual(current, [name])

    def test_the_header_names_the_person_and_the_roles(self):
        self.assertIn("Signed in as Maya. Roles: approver.", seeded().get("/", oid=MAYA).content)


class TheBriefOfACase(unittest.TestCase):
    """The page of a case, `/why/<case>`: the same decision brief as the page of its request."""

    def setUp(self):
        self.console = seeded()
        self.reply = self.console.get("/why/case0001")

    def test_it_is_the_brief_of_the_case_with_its_form_for_a_person_who_may_answer(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), [HEADLINE])
        self.assertEqual(self.reply.headings(2)[:4], ["Evidence", "If you approve", "Whose is it", "Your answer"])
        self.assertEqual([f.action for f in self.reply.forms()], ["/ok/plan0001"])

    def test_a_person_who_is_not_named_reads_the_brief_and_cannot_answer_and_sees_nobody_elses_decisions(self):
        self.console.store.decision_put(make_decision(decision="ask", note="TINO-PRIVATE-QUESTION"))
        reply = self.console.get("/why/case0001", oid=OWNER)
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), [HEADLINE])
        self.assertEqual(reply.forms(), [])
        self.assertIn("Only the people who are named for this request can answer it.", reply.content)
        self.assertNotIn("TINO-PRIVATE-QUESTION", reply.text)

    def test_a_case_without_a_request_has_no_form_and_says_that_no_request_is_open(self):
        console = Console()
        console.seed(plan=False)
        reply = console.get("/why/case0001")
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), ["Consider deleting the disk planted-disk-1 in group meternaut-test-rg"])
        self.assertEqual(reply.forms(), [])
        self.assertNotIn("Your answer", reply.headings(2))
        self.assertIn("No request is open for this case. Nothing changes in Azure.", reply.content)
        self.assertIn("Whose is it", reply.headings(2))

    def test_the_guards_that_fired_are_a_fact_and_are_explained_in_the_details(self):
        self.assertIn("Locks and keep tags", self.reply.summary(0))
        self.assertIn("No guard fired.", self.reply.content)
        self.console.store.case_put(make_case(guards=("locked", "keep-tag", "too-new", "managed-group", "unverified", "something-else"), status="needs_human", plan_id=None))
        reply = self.console.get("/why/case0001")
        self.assertIn("Held back by", reply.summary(0))
        self.assertIn("A management lock covers the resource.", reply.summary(0)["Held back by"])
        self.assertIn("How sure: Low.", reply.content)
        (disclosure,) = reply.main.find_all("details")
        self.assertIn("A management lock covers the resource.", disclosure.text())
        self.assertIn("A guard could not be read, so it counts as on.", disclosure.text())
        self.assertIn("no model can lift it", disclosure.text())

    def test_the_second_ai_that_was_not_asked_or_has_no_objection_says_so(self):
        self.console.store.case_put(make_case(status="dropped", recommendation="keep", models={"detective": "model-detective-x", "skeptic": None}, objections=(), plan_id=None))
        self.assertIn("The second AI was not asked.", self.console.get("/why/case0001").content)
        self.console.store.case_put(make_case(objections=()))
        self.assertIn("The second AI raised no objection.", self.console.get("/why/case0001").content)

    def test_a_case_that_ended_in_an_error_shows_its_reason_as_a_note_of_meternaut_and_not_as_ai_text(self):
        self.console.store.case_put(make_case(status="error", recommendation=None, confidence=None, summary="the token budget of the run was reached", objections=(), models={},
                                              plan_id=None))
        reply = self.console.get("/why/case0001")
        self.assertIn("Why the case ended", reply.headings(3))
        self.assertEqual([p.text() for p in reply.main.find_all("p", class_="quote-label")], ["Recorded by Meternaut"])
        self.assertNotIn("The AI's reasoning", reply.content)
        self.assertIn("the token budget of the run was reached", reply.content)

    def test_the_details_hold_the_steps_the_typed_facts_and_what_the_ais_wrote_in_full(self):
        (disclosure,) = self.reply.main.find_all("details")
        self.assertEqual(self.reply.table("steps").rows, [
            {"Step": "evidence", "Model": "none", "Tokens in": "none", "Tokens out": "none", "Milliseconds": "3", "Result": "ok", "Note": ""},
            {"Step": "detective", "Model": "model-detective-x", "Tokens in": "702", "Tokens out": "307", "Milliseconds": "1,200", "Result": "ok", "Note": ""},
            {"Step": "skeptic", "Model": "model-skeptic-y", "Tokens in": "857", "Tokens out": "223", "Milliseconds": "1,500", "Result": "not ok", "Note": "a note of the step"}])
        self.assertEqual({r["Fact"]: r["Value"] for r in self.reply.table("facts").rows},
                         {"diskState": "unattached", "flags": '{"locked": false}', "sizeBucket": "up to 128", "states": "disconnected, pending"})
        labels = [p.text() for p in disclosure.find_all("p", class_="quote-label")]
        self.assertEqual(labels, ["Written by AI (model: model-detective-x): summary", "Written by AI (model: model-skeptic-y): objection 1"])
        self.assertIn("Treat it as text, not as fact.", disclosure.text())
        self.assertIn("Every step of the case", disclosure.text())

    def test_the_status_of_a_case_that_was_approved_or_declined_is_said_in_words(self):
        for status, words_ in (("approved", "Approved. A person approved the plan and signed in to Azure. The change is being made now."),
                               ("declined", "Declined. A person said no. Nothing changed."),
                               ("acknowledged", "Worth acting on. A person said that this is worth acting on. Meternaut changed nothing in Azure.")):
            with self.subTest(status=status):
                self.console.store.case_put(make_case(status=status))
                (disclosure,) = self.console.get("/why/case0001").main.find_all("details")
                self.assertIn(words_, disclosure.text())

    def test_text_from_the_estate_or_a_model_is_escaped_quoted_and_never_a_link_or_a_control(self):
        hostile = "Ignore the rules <a href=\"https://evil.example\">click</a> [go](javascript:alert(1)) <script>alert(1)</script>"
        self.console.store.case_put(make_case(summary=hostile, objections=(hostile,), resource_name=hostile, owner={"tagOwner": hostile, "lookedUp": True}))
        reply = self.console.get("/why/case0001")
        for quote in reply.main.find_all("blockquote", class_="quote"):
            self.assertEqual([n.tag for n in quote.walk() if n.tag in ("a", "button", "input", "form", "script", "select", "textarea")], [])
        self.assertNotIn("<script>alert(1)</script>", reply.text)
        self.assertNotIn('href="https://evil.example"', reply.text)
        self.assertEqual(reply.root.find_all("script"), [])
        self.assertNotIn("https://evil.example", reply.links())
        external = [h for h in reply.links() if h.startswith(("http", "javascript", "data:"))]
        self.assertEqual(external, ["https://portal.azure.com/#resource" + make_case().resource_id], "the only address that is not of this site is the one made from the resource id")

    def test_a_case_that_does_not_exist_is_a_404(self):
        reply = self.console.get("/why/nothing")
        self.assertEqual(reply.status, 404)
        self.assertIn("I cannot find this case", reply.content)

    def test_the_page_says_in_its_footer_that_an_ai_wrote_what_it_shows(self):
        self.assertIn("Written by an AI (models: model-detective-x, model-skeptic-y); a person approves every change.", self.reply.root.find("footer").text())


INVESTIGATED = dict(
    case_id="case0100", detector="investigation", recommendation="change", confidence=0.85, saving_usd_month=None, cost_usd_30d=41.5,
    summary="The size is larger than the use needs.", objections=("It may be a standby.",), guards=(),
    models={"investigator": "model-investigator-x", "skeptic": "model-skeptic-y"},
    steps=({"step": "investigator", "model": "model-investigator-x", "promptTokens": 4100, "completionTokens": 900, "ms": 61000, "ok": True, "note": "12 tool calls"},
           {"step": "skeptic", "model": "model-skeptic-y", "promptTokens": 1500, "completionTokens": 200, "ms": 9000, "ok": True, "note": None}),
    facts={"basis": "oversized", "proposal": "change", "metrics": {"MetricA": 40}, "costUsd30d": 41.5, "finding": 1}, plan_id=None)


class TheBriefOfAnInvestigation(unittest.TestCase):
    def setUp(self):
        self.console = seeded()
        self.console.store.case_put(make_case(**INVESTIGATED))
        self.reply = self.console.get("/why/case0100")

    def test_it_says_what_the_investigation_found_in_the_words_of_its_basis_and_what_the_tools_measured(self):
        self.assertEqual(self.reply.status, 200)
        facts = self.reply.summary(0)
        self.assertEqual(list(facts)[:3], ["Cost, last 30 days", "MetricA", "What the investigation found"])
        self.assertTrue(facts["MetricA"].startswith("40 in the period measured"), facts["MetricA"])
        self.assertTrue(facts["What the investigation found"].startswith("Larger than its use needs"))
        self.assertIn("Azure Monitor", facts["MetricA"])

    def test_the_headline_says_consider_changing_and_the_page_says_how_sure_it_is(self):
        self.assertEqual(self.reply.headings(1), ["Consider changing the disk planted-disk-1 in group meternaut-test-rg"])
        self.assertIn("How sure: ", self.reply.content)

    def test_the_two_agents_words_are_in_labelled_boxes_and_in_full_in_the_details(self):
        labels = [p.text() for p in self.reply.main.find_all("p", class_="quote-label")]
        self.assertEqual(labels[:2], ["The AI's reasoning (not checked by code)", "The second AI's doubt"])
        self.assertIn("Written by AI (model: model-investigator-x): summary", labels)
        self.assertIn("Written by AI (model: model-skeptic-y): objection 1", labels)

    def test_its_steps_are_the_two_runs_of_the_agents(self):
        self.assertEqual(self.reply.table("steps").rows, [
            {"Step": "investigator", "Model": "model-investigator-x", "Tokens in": "4,100", "Tokens out": "900", "Milliseconds": "61,000", "Result": "ok", "Note": "12 tool calls"},
            {"Step": "skeptic", "Model": "model-skeptic-y", "Tokens in": "1,500", "Tokens out": "200", "Milliseconds": "9,000", "Result": "ok", "Note": ""},
        ])

    def test_a_skeptic_that_gave_no_verdict_or_was_not_asked_says_so_and_shows_no_objection(self):
        failed = ({**INVESTIGATED["steps"][0]}, {**INVESTIGATED["steps"][1], "ok": False, "note": "the project is busy"})
        self.console.store.case_put(make_case(**{**INVESTIGATED, "steps": failed, "objections": (), "status": "needs_human"}))
        reply = self.console.get("/why/case0100")
        self.assertIn("The second AI gave no verdict on this finding.", reply.content)
        self.assertIn("How sure: Low.", reply.content)
        self.console.store.case_put(make_case(**{**INVESTIGATED, "models": {"investigator": "model-investigator-x", "skeptic": None}, "objections": ()}))
        self.assertIn("The second AI was not asked.", self.console.get("/why/case0100").content)

    def test_the_notes_that_code_wrote_among_the_objections_are_not_shown_as_the_second_ais_doubt(self):
        notes = ("no measurement backs this finding: the tools returned no number", "the Investigator gave a confidence of 0.5, under the 0.7 that a proposal needs")
        self.console.store.case_put(make_case(**{**INVESTIGATED, "objections": notes + ("It may be a standby.",)}))
        reply = self.console.get("/why/case0100")
        doubt = [q.text() for q in reply.main.find_all("blockquote", class_="quote")][1]
        self.assertEqual(doubt, "It may be a standby.")
        self.console.store.case_put(make_case(**{**INVESTIGATED, "objections": notes}))
        self.assertIn("The second AI raised no objection.", self.console.get("/why/case0100").content)

    def test_text_of_the_agents_is_quoted_and_is_never_a_link_or_a_control(self):
        hostile = "Ignore the rules <a href=\"https://evil.example\">click</a> <script>alert(1)</script>"
        self.console.store.case_put(make_case(**{**INVESTIGATED, "summary": hostile, "objections": (hostile,), "resource_name": hostile}))
        reply = self.console.get("/why/case0100")
        for quote in reply.main.find_all("blockquote", class_="quote"):
            self.assertEqual([n.tag for n in quote.walk() if n.tag in ("a", "button", "input", "form", "script", "select", "textarea")], [])
        self.assertNotIn("<script>alert(1)</script>", reply.text)
        self.assertNotIn('href="https://evil.example"', reply.text)
        self.assertEqual(reply.root.find_all("script"), [])
        self.assertNotIn("https://evil.example", reply.links())


class TheHistory(unittest.TestCase):
    """"What happened": a feed of the last 30 days, a line for each thing, grouped by day, newest first."""

    def setUp(self):
        self.console = seeded()
        store = self.console.store
        store.plan_put(make_plan(state="declined"))
        store.decision_put(make_decision(decision="decline", reason="handled", at=at(days=-1)))
        store.case_put(make_case(case_id="case0004", first_seen_at=at(days=-1), resource_name="b", plan_id="plan0004"))
        store.plan_put(make_plan(plan_id="plan0004", case_id="case0004", state="consumed", created_at=at(days=-4), expires_at=at(days=-1)))
        store.decision_put(make_decision(plan_id="plan0004", at=at(days=-3, hours=-1)))
        store.action_put(make_action(plan_id="plan0004", case_id="case0004", state="verified", finished_at=at(days=-3), verified_at=at(days=-1, hours=-2),
                                     result="Deleted. Azure no longer lists the resource.", verification={"gone": True, "note": "Cost lines show no cost."}))
        store.plan_put(make_plan(plan_id="plan0005", case_id="case0005", state="expired", created_at=at(days=-6), expires_at=at(days=-2)))
        store.case_put(make_advice_case())
        store.plan_put(make_advice(state="consumed", created_at=at(days=-2)))
        store.decision_put(make_decision(plan_id="plan0002", decision="approve", at=at(days=-2, hours=-1)))
        self.reply = self.console.get("/history")

    def feed(self, reply):
        days = reply.headings(2)
        lists = [[li.text() for li in ul.find_all("li")] for ul in reply.main.find_all("ul", class_="feed")]
        return dict(zip(days, lists))

    def test_it_is_a_feed_grouped_by_day_newest_first(self):
        self.assertEqual(self.reply.headings(1), ["What happened"])
        self.assertEqual(self.reply.headings(2), ["Wed 4 Nov", "Tue 3 Nov", "Mon 2 Nov"])
        self.assertEqual(self.reply.root.find_all("table"), [], "no run table and no case table: they are on the Operations page")

    def test_each_line_says_what_was_decided_changed_or_found(self):
        feed = self.feed(self.reply)
        self.assertEqual(feed["Wed 4 Nov"], [
            f"Tino declined: {HEADLINE}. Reason: it is already handled.",
            "1 new finding.",
            f"Change checked: {HEADLINE}. Cost lines show no cost."])
        self.assertEqual(feed["Tue 3 Nov"], [f"Nobody answered in time: {HEADLINE}.",
                                              "Tino said it is worth acting on: Consider changing the virtual machine oversized-vm-1 in group team-apps-rg."])
        self.assertIn(f"Change made: {HEADLINE}. Deleted. Azure no longer lists the resource.", feed["Mon 2 Nov"])
        self.assertIn(f"Tino approved: {HEADLINE}.", feed["Mon 2 Nov"])

    def test_the_count_of_the_advice_that_nobody_answered_is_not_cut_and_does_not_take_the_places_of_the_other_plans(self):
        store = self.console.store
        for n in range(49):
            store.case_put(make_advice_case(case_id=f"case6{n:03d}", resource_id=f"{VM_ID}-k{n}", resource_name=f"endpoint-k{n}", plan_id=f"plan6{n:03d}"))
            store.plan_put(make_advice(plan_id=f"plan6{n:03d}", case_id=f"case6{n:03d}", resource_id=f"{VM_ID}-k{n}", state="expired", created_at=at(days=-1, hours=-1), expires_at=at(days=-1)))
        feed = self.feed(self.console.get("/history"))
        self.assertIn("Closed with no answer: 49 requests to look at a finding.", feed["Wed 4 Nov"])
        self.assertIn(f"Tino declined: {HEADLINE}. Reason: it is already handled.", feed["Wed 4 Nov"], "the decisions of the other plans are still there")

    def test_a_line_that_names_a_request_links_to_its_page(self):
        self.assertIn("/ok/plan0001", self.reply.links())
        self.assertIn("/ok/plan0002", self.reply.links())

    def test_advice_that_nobody_answered_is_one_line_for_each_day_and_a_change_that_nobody_answered_is_a_line_of_its_own(self):
        store = self.console.store
        for n in range(3):
            store.case_put(make_advice_case(case_id=f"case5{n:03d}", resource_id=f"{VM_ID}-h{n}", resource_name=f"endpoint-h{n}", plan_id=f"plan5{n:03d}"))
            store.plan_put(make_advice(plan_id=f"plan5{n:03d}", case_id=f"case5{n:03d}", resource_id=f"{VM_ID}-h{n}", state="expired", created_at=at(days=-3), expires_at=at(days=-1, hours=-n)))
        feed = self.feed(self.console.get("/history"))
        self.assertEqual(feed["Tue 3 Nov"][0], f"Nobody answered in time: {HEADLINE}.", "the change that expired is a line of its own")
        self.assertIn("Closed with no answer: 3 requests to look at a finding.", feed["Wed 4 Nov"])
        self.assertFalse([line for lines in feed.values() for line in lines if "Nobody answered in time: Consider" in line], feed)

    def test_the_old_addresses_of_my_decisions_and_what_i_did_here_answer_with_the_same_page(self):
        for path in ("/me/decisions", "/me/activity"):
            with self.subTest(path=path):
                reply = self.console.get(path)
                self.assertEqual((reply.status, reply.headings(1)), (200, ["What happened"]))
                self.assertEqual(self.feed(reply), self.feed(self.reply))

    def test_a_person_who_is_not_named_sees_the_number_of_findings_and_none_of_the_decisions(self):
        reply = self.console.get("/history", oid=MAYA)
        lines = [line for lines_ in self.feed(reply).values() for line in lines_]
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, r"^\d+ new findings?\.$")

    def test_an_empty_history_says_so(self):
        reply = Console().get("/history")
        self.assertIn("Nothing has happened in the last 30 days.", reply.content)

    def test_what_is_older_than_30_days_is_not_in_the_feed(self):
        console = Console()
        console.store.plan_put(make_plan(created_at=at(days=-40), expires_at=at(days=-37)))
        console.store.decision_put(make_decision(at=at(days=-38), decision="decline"))
        console.store.case_put(make_case(first_seen_at=at(days=-35)))
        self.assertIn("Nothing has happened in the last 30 days.", console.get("/history").content)

    def test_the_page_is_not_a_cost_report(self):
        for gone in ("cost report", "Cost, last 30 days", "per month in total", "Total"):
            self.assertNotIn(gone, self.reply.content)

    def test_a_store_that_cannot_be_read_is_said_plainly(self):
        console = Console(store=FailingStore(fail={"plans_recent"}, clock=lambda: NOW))
        console.seed()
        reply = console.get("/history")
        self.assertEqual(reply.status, 200)
        self.assertIn("The history cannot be read", reply.content)


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
        reply = self.console.get("/ok/plan0001")
        self.assertIn("Sun 8 Nov 2026 08:00 UTC.", reply.content)
        self.assertNotIn("UTC (", reply.content)
        self.console.store.settings_put(SettingsRecord(oid=TINO, timezone="Mars/Olympus_Mons"))
        self.assertIn("Sun 8 Nov 2026 08:00 UTC.", self.console.get("/ok/plan0001").content)
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
        self.assertEqual(reply.status, 200)
        self.assertNotIn("<b>soon</b>", reply.text)
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
