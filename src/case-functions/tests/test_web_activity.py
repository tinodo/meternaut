"""The page "What the AI looked at" (docs/proposals/23-what-the-ai-looked-at.md): the latest investigation as the app kept it, how much of the cost its tools read, every finding and what became of it,
and the earlier runs. Every kind of resource here is invented (contoso.example/...), and the figures of the coverage are worked out by hand in the test that checks them.
"""
import unittest

from test_web_support import MAYA, NOW, OPS, OWNER, STRANGER, SUB, TINO, XSS, XSS_ESCAPED, Console, FailingStore, at, make_case, make_plan, make_run

from cases.memory_store import MemoryStore
from cases.models import INVESTIGATION_ENDS, KEPT_INVESTIGATIONS, InvestigationRecord
from cases.web import activity, router

PATH = "/ops/activity"
WIDGETS, GADGETS, GIZMOS = "contoso.example/widgets", "contoso.example/gadgets", "contoso.example/gizmos"
HEADINGS = ["What the AI looked at and concluded", "Findings of the last run", "Where the money goes and what the AI did with it", "Earlier runs", "What this page cannot tell"]
PHRASES = ("widgets r1: MetricA is there, so no idle finding", "gadgets r53: MetricB is not offered, could not judge use", "gizmos: not examined before the tool budget ended")


def finding(n: int, **more) -> dict:
    return {**{"n": n, "basis": "no-usage", "proposal": "delete", "sure": 0.85, "resources": 4, "says": "Nothing used these in the window.", "verdict": "agree", "kept": True}, **more}


FINDINGS = (finding(1, usd=120.5, fates={"request": 3, "automation": 1}, left={"guarded": 1}),
            finding(2, basis="other", proposal="investigate", sure=0.4, resources=6, says="Looks unusual.", verdict="", kept=False, left={"unknown": 6}),
            finding(3, basis="oversized", proposal="change", sure=0.7, resources=2, says="Larger than needed.", verdict="disagree", doubts=["A monthly job may need it."], fates={"person": 2}))


def record(run_id: str = "run00001", when: str | None = None, **more) -> InvestigationRecord:
    """The latest run, by hand: 1,000 dollars were read, 600 of them in widgets (listed, measured and described), 50 in gizmos (measured), 300 in gadgets (not looked at) and 50 in no kind: 650 of 1,000."""
    base = dict(run_id=run_id, at=when or at(hours=-2), trigger="timer", investigator="model-a", skeptic="model-b", calls=30, max_calls=30, tokens=12345, seconds=140, max_seconds=600, end="calls",
                answered=True, examined=PHRASES, findings=FINDINGS, kinds=([WIDGETS, 600.0, "lmd"], [GADGETS, 300.0, ""], [GIZMOS, 50.0, "m"], ["other", 50.0, ""]), looked=2,
                cost_total=1000.0, cost_looked=650.0, subs=2, subs_costed=2)
    base.update(more)
    return InvestigationRecord(**base)


def case(case_id: str, kind: str, status: str, plan: str | None = None):
    return make_case(case_id=case_id, resource_type=kind, status=status, detector="investigation", plan_id=plan)


# The findings of the people, by kind of resource, status and the state of the plan of the request (None: no request was made). Of widgets 3 requests wait (two for a finding that needs a
# person and one for a finding that waits for its OK) and 3 findings are not asked about (the third of them has a request that ran out); a finding whose kind is written in capitals is the same
# kind; a finding that waits for its OK and has no open request, and a finding that is done, are neither. Of gadgets 1 finding is not asked about.
CASES = ((WIDGETS, "needs_human", "open"), (WIDGETS, "proposed", "open"), (WIDGETS, "awaiting_ok", "open"), (WIDGETS, "needs_human", None), (WIDGETS.upper(), "needs_human", None),
         (WIDGETS, "needs_human", "expired"), (WIDGETS, "awaiting_ok", None), (WIDGETS, "done", "consumed"), (GADGETS, "proposed", None))


def seeded(console: Console | None = None) -> Console:
    """The latest run and one before it, three runs that investigated (the second has no record) and one that did not, and the findings of CASES."""
    console = console or Console()
    store = console.store
    store.investigation_put(record())
    store.investigation_put(record("run00003", at(days=-15), calls=12, end="answered", findings=(finding(1), finding(2)), cost_looked=250.0))
    for run in (make_run(run_id="run00001", started_at=at(hours=-2), investigated=True), make_run(run_id="run00002", started_at=at(days=-8), investigated=True),
                make_run(run_id="run00003", started_at=at(days=-15), investigated=True), make_run(run_id="run00004", started_at=at(days=-1))):
        store.run_put(run)
    for n, (kind, status, state) in enumerate(CASES, 1):
        store.case_put(case(f"c{n}", kind, status, f"p{n}" if state else None))
        if state:
            store.plan_put(make_plan(plan_id=f"p{n}", case_id=f"c{n}", state="open" if state in ("open", "expired") else state, expires_at=at(minutes=-1) if state == "expired" else at(hours=71)))
    return console


def tiles_of(reply) -> dict:
    (tiles,) = reply.main.find_all("ul", class_="kpis")
    return {li.find("p", class_="k").text(): (li.find("p", class_="v").text(), li.find("p", class_="n").text()) for li in tiles.find_all("li")}


def page_of(*records: InvestigationRecord, runs=()):
    console = Console()
    for one in records:
        console.store.investigation_put(one)
    for run in runs:
        console.store.run_put(run)
    return console.get(PATH)


class TheLatestInvestigation(unittest.TestCase):
    def setUp(self):
        self.reply = seeded().get(PATH)

    def test_it_is_a_head_three_tiles_and_the_blocks_of_the_brief_in_their_order(self):
        reply = self.reply
        self.assertEqual((reply.status, reply.problems), (200, []))
        self.assertEqual(reply.headings(1), ["What the AI looked at"])
        self.assertEqual(reply.headings(2), HEADINGS)
        self.assertEqual(list(tiles_of(reply)), ["Looked at in the last run", "Findings kept", "Stopped because"], "the guide allows at most three tiles")
        self.assertEqual([reply.table(name).caption.split(".")[0] for name in ("findings", "money", "earlier")], [
            "Findings of the last run", "The dearest kinds of resource, their cost in 30 days and what the AI did with them", "The 10 investigations before the latest, newest first"])
        self.assertEqual(reply.forms(), [])
        self.assertEqual(reply.root.find("main").classes(), ["wide"])
        self.assertIn("You see this because your role ops or owner lets you see what the AI looked at.", reply.content)
        self.assertIn("This page changes nothing.", reply.main.find("div", class_="head").find("p").text())

    def test_the_tiles_say_what_share_of_the_cost_the_tools_read_how_many_findings_were_kept_and_why_the_run_stopped(self):
        looked, kept, stopped = tiles_of(self.reply).values()
        self.assertEqual(looked[0], "65% of the 30-day cost")
        self.assertIn("2 kinds of resource.", looked[1])
        self.assertIn("the cost of the kinds of resource that its tools read, divided by all the cost that the run read, in US dollars", looked[1], "it says how it was counted")
        self.assertEqual(kept, ("2 of 3 findings", "The checks of code kept 2 of the 3 findings that the AI wrote."))
        self.assertEqual(stopped, ("Its calls ran out", "It made 30 of the 30 tool calls that it was allowed and used 140 of the 600 seconds. "
                                                        "It used all its tool calls, so it was told to answer with what it had."))

    def test_the_phrases_are_the_ais_own_and_the_labels_of_a_run_are_said_to_mean_nothing_outside_it(self):
        main = self.reply.main
        self.assertEqual(main.find("p", class_="quote-label").text(), "Written by the AI")
        self.assertEqual([li.text() for li in main.find("blockquote").find_all("li")], list(PHRASES), "as the AI wrote them, labels such as r1 and r53 included")
        self.assertIn("Labels such as r1 and r53 stand for a resource inside that run only. They mean nothing outside it, and this page does not say which resource they were.", self.reply.content)
        self.assertIn("started by the daily timer. The first AI was model-a and the second AI was model-b.", self.reply.content)

    def test_each_finding_says_what_it_says_how_sure_it_is_what_it_covers_and_what_became_of_it_and_a_cost_is_never_called_a_saving(self):
        table = self.reply.table("findings")
        self.assertEqual(table.headers, ["What it says", "How sure (0 to 1)", "Resources", "What they cost in 30 days", "The second AI", "What became of it"])
        self.assertIn("not what could be saved", table.caption)
        first, dropped, third = table.rows
        self.assertEqual(first["What it says"], "Nothing used these in the window. No recorded usage. Proposal: delete.")
        self.assertEqual((first["How sure (0 to 1)"], first["Resources"], first["The second AI"]), ("0.85", "4", "Agrees"))
        self.assertEqual(first["What they cost in 30 days"], "$120.50 What they cost, not what could be saved.")
        self.assertEqual(first["What became of it"], "3 resources: a request was made 1 resource: held back, managed by an automation Left out: 1 resource held back by a guard")
        self.assertEqual((dropped["What it says"], dropped["Resources"], dropped["The second AI"]),
                         ("Looks unusual. Another reason. Proposal: investigate.", "6 listed", "Not asked: the finding was dropped before it"))
        self.assertEqual((dropped["What they cost in 30 days"], dropped["What became of it"]), ("No cost line was read for them", "Dropped: no resource of it was left (6 resources that no tool showed)"))
        self.assertEqual((third["The second AI"], third["What became of it"]), ("Disagrees A monthly job may need it.", "2 resources: left for a person, no request yet"))
        self.assertNotIn("Saves", self.reply.content)

    def test_the_money_by_kind_says_what_share_each_has_whether_the_tools_looked_at_it_and_how_many_requests_and_questions_it_has(self):
        table = self.reply.table("money")
        self.assertEqual(table.headers, ["Kind of resource", "Cost in 30 days", "Share of the cost read", "In the last investigation", "Open requests", "Open questions"])
        widgets, gadgets, gizmos, none = table.rows
        self.assertEqual(list(widgets.values()), [WIDGETS, "$600", "60%", "Looked at listed, measured, described", "3", "3"])
        self.assertEqual(list(gadgets.values()), [GADGETS, "$300", "30%", "Not looked at", "0", "1"])
        self.assertEqual(list(gizmos.values()), [GIZMOS, "$50", "5%", "Looked at measured", "0", "0"])
        self.assertEqual(list(none.values()), ["Cost that no kind of resource has", "$50", "5%", "No tool can look at it: Cost Management ties it to no resource", "Not applicable", "Not applicable"])
        self.assertIn("The rows of this table are 100% of the cost that the run read.", self.reply.content)
        self.assertIn("An open request waits for a person's answer. An open question is a finding that nobody has been asked about yet.", self.reply.content)

    def test_at_most_25_kinds_are_shown_and_the_sentence_under_the_table_says_how_much_of_the_cost_they_are(self):
        kinds = tuple([f"contoso.example/kind{n:02d}", float(100 - n), ""] for n in range(40))
        reply = page_of(record(kinds=kinds, cost_total=3220.0))  # 100 + 99 + ... + 61 in all
        rows = reply.table("money").rows
        self.assertEqual((len(rows), rows[0]["Kind of resource"], rows[-1]["Kind of resource"]), (activity.KINDS_SHOWN, "contoso.example/kind00", "contoso.example/kind24"))
        self.assertIn("The rows of this table are 68% of the cost that the run read.", reply.content, "100 + 99 + ... + 76 is 2,200 of 3,220")

    def test_the_earlier_runs_are_one_line_each_and_a_run_that_has_no_record_is_not_recorded_and_never_zero(self):
        table = self.reply.table("earlier")
        self.assertEqual(table.headers, ["Started", "Tool calls", "Findings kept", "Share of the cost looked at", "Stopped because"])
        self.assertEqual([list(row.values())[1:] for row in table.rows], [["Not recorded for earlier runs", "—", "—", "—"], ["12 of 30", "2 of 2", "25%", "It gave its answer"]],
                         "the run of the day before did not investigate and is not listed")
        self.assertNotIn("0 of 0", self.reply.content)

    def test_the_limits_of_the_page_are_said_in_one_paragraph_and_a_person_with_the_role_ops_is_pointed_to_every_run(self):
        self.assertIn("The phrases are the AI's own claims, and code did not check them. \"Looked at\" means that a tool read the kind of resource, not that the analysis went deep. The costs are the last "
                      "30 days that the run read, in US dollars", self.reply.content)
        self.assertIn("this is not a cost report, and Cost Management has the bill. A run from before this page existed was not recorded, which is not the same as nothing.", self.reply.content)
        self.assertIn("/ops/runs", self.reply.links())


class TheShareThatTheToolsRead(unittest.TestCase):
    def value(self, **more) -> tuple[str, str]:
        return tiles_of(page_of(record(**more)))["Looked at in the last run"]

    def test_the_share_is_a_whole_percent_of_the_cost_that_the_run_read(self):
        for looked, total, shown in ((650.0, 1000.0, "65%"), (200.0, 300.0, "67%"), (1.0, 3.0, "33%"), (1000.0, 1000.0, "100%"), (0.0, 400.0, "0%"), (4.0, 1000.0, "under 1%")):
            with self.subTest(looked=looked, total=total):
                self.assertEqual(self.value(cost_looked=looked, cost_total=total)[0], f"{shown} of the 30-day cost")

    def test_a_run_that_read_no_cost_in_dollars_has_no_share_and_says_so_and_does_not_say_zero(self):
        for total in (None, 0.0):
            with self.subTest(total=total):
                value, note = self.value(cost_total=total, cost_looked=0.0, kinds=(), looked=3, subs_costed=0)
                self.assertEqual(value, "—")
                self.assertIn("3 kinds of resource. No share can be told: the run read no cost in US dollars.", note)

    def test_the_tile_says_when_only_some_subscriptions_had_their_cost_read(self):
        self.assertIn("The cost of 1 of 3 subscriptions was read.", self.value(subs=3, subs_costed=1)[1])
        self.assertNotIn("subscriptions was read", self.value()[1], "all of them: nothing to say")


class HowTheRunEnded(unittest.TestCase):
    def tile(self, **more) -> tuple[str, str]:
        return tiles_of(page_of(record(**more)))["Stopped because"]

    def test_each_word_of_the_list_says_what_it_stands_for_with_the_calls_and_the_seconds_that_were_used_of_the_allowed(self):
        said = {"answered": ("It gave its answer", "It gave its answer within its limits."), "time": ("Its time ran out", "Its time for tool calls ran out, so it was told to answer with what it had."),
                "calls": ("Its calls ran out", "It used all its tool calls, so it was told to answer with what it had."),
                "refused": ("It was not allowed to run", "A safeguard around the agents did not let it run, or stopped it."), "failed": ("It failed", "It gave no answer that could be read.")}
        self.assertEqual(set(said), set(INVESTIGATION_ENDS), "every word that the record can hold has its words on the page")
        for end, (word, meaning) in said.items():
            with self.subTest(end=end):
                self.assertEqual(self.tile(end=end, calls=9, max_calls=30, seconds=61, max_seconds=600), (word, f"It made 9 of the 30 tool calls that it was allowed and used 61 of the 600 seconds. {meaning}"))

    def test_a_run_that_was_refused_says_why_in_the_words_of_the_code_that_the_safeguards_gave(self):
        for stop, why in (("tokens", "Its token limit was used up."), ("switch", "A switch that holds the agents is pulled."), ("refusals", "Too many of its tool calls were refused.")):
            with self.subTest(stop=stop):
                self.assertTrue(self.tile(end="refused", stop=stop)[1].endswith(f"or stopped it. {why}"))
        self.assertTrue(self.tile(end="refused", stop="a code that nobody listed")[1].endswith("did not let it run, or stopped it."), "what is not listed is not said")

    def test_a_run_that_used_up_its_time_or_its_calls_and_gave_no_answer_that_could_be_read_says_that_too(self):
        for end in ("time", "calls"):
            with self.subTest(end=end):
                self.assertTrue(self.tile(end=end, answered=False, findings=())[1].endswith("answer with what it had. Its answer could not be read."))

    def test_a_run_with_no_answer_has_no_finding_to_count_and_says_why(self):
        reply = page_of(record(end="failed", answered=False, findings=(), examined=(), note="the investigator gave no answer (the service gave no usable answer)", calls=3))
        self.assertEqual(tiles_of(reply)["Findings kept"], ("—", "The AI gave no answer that code could read, so there is no finding to check."))
        self.assertIn("There is no finding: the AI gave no answer that code could read.", reply.content)
        self.assertIn("The AI wrote no phrase about what it examined in this run.", reply.content)
        self.assertIn("It did not finish", reply.content)
        self.assertIn("the investigator gave no answer (the service gave no usable answer)", reply.content)

    def test_an_answer_with_no_finding_is_not_a_failure(self):
        reply = page_of(record(end="answered", findings=()))
        self.assertEqual(tiles_of(reply)["Findings kept"][0], "0 of 0 findings")
        self.assertIn("The AI wrote no finding.", reply.content)
        self.assertNotIn("It did not finish", reply.content)


class WhenThereIsNothingToShow(unittest.TestCase):
    def test_a_store_without_a_record_says_that_none_is_recorded_and_not_that_nothing_was_looked_at(self):
        reply = Console().get(PATH)
        self.assertEqual((reply.status, reply.problems), (200, []))
        self.assertEqual({label: tile[0] for label, tile in tiles_of(reply).items()}, {"Looked at in the last run": "—", "Findings kept": "—", "Stopped because": "—"})
        self.assertIn("No investigation is recorded yet. An investigation that ran before this page existed was not recorded.", reply.content)
        self.assertEqual(reply.headings(2), ["Earlier runs", "What this page cannot tell"])
        self.assertIn("No earlier investigation is recorded.", reply.content)

    def test_runs_that_investigated_before_the_page_existed_are_listed_as_not_recorded(self):
        reply = page_of(runs=[make_run(run_id=f"run{n:05d}", started_at=at(days=-n), investigated=True) for n in (1, 8)])
        self.assertEqual([row["Tool calls"] for row in reply.table("earlier").rows], ["Not recorded for earlier runs"] * 2)

    def test_a_newest_investigation_that_has_no_record_is_said_to_be_missing_and_what_follows_is_from_the_latest_one_that_is_kept(self):
        console = seeded()
        console.store.run_put(make_run(run_id="run00009", started_at=at(minutes=-30), investigated=True))
        reply = console.get(PATH)
        self.assertIn("The newest investigation was not recorded", reply.content)
        self.assertIn("What follows is from the latest one that is recorded.", reply.content)
        self.assertNotIn("The newest investigation was not recorded", seeded().get(PATH).content)

    def test_only_the_newest_ten_earlier_runs_are_shown(self):
        console = Console()
        for n in range(KEPT_INVESTIGATIONS):
            console.store.investigation_put(record(f"run{n:05d}", at(days=-n)))
        self.assertEqual(len(console.get(PATH).table("earlier").rows), activity.EARLIER)


class WhenSomethingCannotBeRead(unittest.TestCase):
    def failing(self, *calls: str) -> Console:
        return seeded(Console(store=FailingStore(fail=set(calls), clock=lambda: NOW)))

    def test_a_store_that_cannot_give_the_records_is_the_plain_fault_of_the_router_and_no_trace(self):
        reply = Console(store=FailingStore(fail={"investigations_recent"}, clock=lambda: NOW)).get(PATH)
        self.assertEqual(reply.status, 503)
        self.assertEqual(reply.headings(1), ["I cannot reach my records"])
        self.assertIn("Nothing has changed.", reply.content)
        self.assertNotIn("Traceback", reply.text)
        self.assertNotIn("StoreError", reply.text)

    def test_when_the_findings_cannot_be_read_the_counts_of_requests_and_questions_say_so_and_the_rest_is_there(self):
        for call in ("plans_open", "cases_recent"):
            with self.subTest(call=call):
                reply = self.failing(call).get(PATH)
                self.assertEqual(reply.status, 200)
                self.assertIn("Part of the findings cannot be read", reply.content)
                self.assertIn("I cannot read all of them now, so the open requests and questions are missing. Nothing has changed.", reply.content)
                self.assertEqual({(row["Open requests"], row["Open questions"]) for row in reply.table("money").rows[:3]}, {("Cannot be read now", "Cannot be read now")})
                self.assertEqual(tiles_of(reply)["Looked at in the last run"][0], "65% of the 30-day cost")

    def test_when_the_runs_cannot_be_read_the_page_says_that_a_run_with_no_record_is_not_listed(self):
        reply = self.failing("runs_recent").get(PATH)
        self.assertEqual(reply.status, 200)
        self.assertIn("I cannot read the runs now, so a run with no record is not listed. Nothing has changed.", reply.content)
        self.assertEqual([row["Tool calls"] for row in reply.table("earlier").rows], ["12 of 30"])

    def test_a_read_that_may_hold_more_says_at_least(self):
        console = Console()
        console.store.investigation_put(record())
        for n in range(1000):
            console.store.case_put(case(f"many{n}", GADGETS, "proposed"))
        rows = {row["Kind of resource"]: row for row in console.get(PATH).table("money").rows}
        self.assertEqual((rows[GADGETS]["Open requests"], rows[GADGETS]["Open questions"]), ("At least 0", "At least 1000"))


class WhatItShowsOfTheEstate(unittest.TestCase):
    HOSTILE = f"{XSS} /subscriptions/{SUB}/resourceGroups/rg-secret/providers/Contoso.Example/widgets/prod-widget and {SUB}"

    def hostile(self) -> InvestigationRecord:
        entry = finding(1, says=self.HOSTILE, doubts=[self.HOSTILE], note=self.HOSTILE, usd=5.0, fates={XSS: 2, "request": 1}, left={XSS: 3}, verdict=XSS, basis=XSS, proposal=XSS, sure=XSS)
        return record(investigator=self.HOSTILE, skeptic=XSS, trigger=XSS, end=XSS, stop=XSS, note=self.HOSTILE, examined=(self.HOSTILE, XSS), findings=(entry,),
                      kinds=([XSS, 5.0, XSS], [GADGETS, "not a number", ""], "not a kind", [WIDGETS]), looked=XSS)

    def test_a_payload_in_a_phrase_a_sentence_a_name_of_a_model_or_a_kind_is_escaped_and_an_id_is_taken_out(self):
        console = Console()
        console.store.investigation_put(self.hostile())
        reply = console.get(PATH)
        self.assertEqual((reply.status, reply.problems), (200, []))
        for payload in (XSS, "<script", "<img", "onerror=alert(2)>"):
            self.assertNotIn(payload, reply.text)
        self.assertIn(XSS_ESCAPED, reply.text, "as text")
        for estate in (SUB, "rg-secret", "prod-widget", "/subscriptions"):
            self.assertNotIn(estate, reply.text, estate)
        self.assertIn("(id removed)", reply.text)
        self.assertEqual([href for href in reply.links() if href.startswith(("http", "mailto", "javascript"))], [])
        self.assertEqual([href for href in reply.links() if "case" in href or "plan" in href or "/why/" in href or "/ok/" in href], [], "no link to a finding or a request")

    def test_what_a_record_says_that_is_not_in_a_list_of_words_is_not_taken_for_words_of_the_page(self):
        console = Console()
        console.store.investigation_put(self.hostile())
        text = console.get(PATH).content
        self.assertIn("It failed", text, "an ending that nobody listed is a failure")
        self.assertIn("started by a source that was not recorded", text)
        self.assertIn("2 resources: not known", text, "a fate that nobody listed")
        self.assertIn("Gave no verdict", text)

    def test_a_run_whose_ai_wrote_the_name_of_a_resource_and_an_id_shows_neither_from_the_investigation_to_the_page(self):
        from test_activity import context, rid
        from test_investigate import FakeFoundry, FakeToolbox, Harness, answer, finding as found
        phrase = f"Nothing reads thing-1. <b>x</b> /subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Example/things/thing-1 and {SUB} https://evil.example/x"
        h = Harness(FakeFoundry(answer(found(handles=["r1", "r2"], summary=phrase), examined=(phrase,))), FakeToolbox(), with_store=True)
        h.contexts = {SUB: context({rid("microsoft.example/things", 1): 10.0})}
        h.go()
        reply = Console(store=h.store).get(PATH)
        self.assertEqual((reply.status, reply.problems), (200, []))
        for gone in ("thing-1", SUB, "rg-app", "evil.example", "<b>", "/subscriptions"):
            self.assertNotIn(gone, reply.text, gone)
        self.assertIn("Nothing reads (name removed).", reply.text)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", reply.text, "html is text")
        self.assertIn("(id removed)", reply.text)
        self.assertIn("(link removed)", reply.text)


class WhoMayOpenIt(unittest.TestCase):
    def setUp(self):
        self.console = seeded()

    def test_a_person_with_the_role_ops_or_owner_opens_it_and_a_person_with_neither_gets_the_refusal_of_the_permissions_page(self):
        for who, status in ((TINO, 200), (OPS, 200), (OWNER, 200), (MAYA, 403)):
            with self.subTest(who=who):
                self.assertEqual(self.console.get(PATH, oid=who).status, status)
        refused = self.console.get(PATH, oid=MAYA)
        self.assertEqual(refused.text, self.console.get("/ops/permissions", oid=MAYA).text, "the same refusal as the permissions page gives, to the letter")
        self.assertIn("This page is for people with the role ops or owner.", refused.content)
        self.assertNotIn("Looked at in the last run", refused.content, "nothing of the page is shown to a person who may not open it")

    def test_a_person_who_is_not_listed_gets_the_denied_page_and_a_request_without_a_sign_in_the_same(self):
        denied = self.console.get("/", oid=None)
        for who in (STRANGER, None):
            reply = self.console.get(PATH, oid=who)
            self.assertEqual((reply.status, reply.text), (denied.status, denied.text))

    def test_the_link_to_every_run_is_for_the_role_that_may_open_that_page_and_not_for_an_owner_who_has_not_that_role(self):
        self.assertIn("/ops/runs", self.console.get(PATH, oid=OPS).links())
        self.assertNotIn("/ops/runs", self.console.get(PATH, oid=OWNER).links())

    def test_the_page_is_in_the_navigation_of_ops_and_owner_next_to_savings_found_and_marked_when_it_is_open(self):
        def names(oid):
            return [a.text() for a in self.console.get("/", oid=oid).root.find("nav").find_all("a")]
        self.assertEqual(names(OPS), ["Decisions", "History", "Settings", "Operations", "Savings found", "What the AI looked at"])
        self.assertEqual(names(OWNER), ["Decisions", "History", "Settings", "Savings found", "What the AI looked at"])
        self.assertEqual(names(MAYA), ["Decisions", "History", "Settings"])
        nav = self.console.get(PATH, oid=OWNER).root.find("nav")
        self.assertEqual([a.text() for a in nav.find_all("a") if a.attrs.get("aria-current") == "page"], ["What the AI looked at"])

    def test_the_operations_page_links_to_it_after_the_link_to_every_saving(self):
        links = self.console.get("/ops", oid=OPS).links()
        self.assertEqual(links[links.index("/ops/savings", links.index("/ops/runs")) + 1], PATH)

    def test_the_router_has_one_route_for_the_roles_ops_and_owner_and_it_is_a_get(self):
        found = [(method, roles, handler) for method, pattern, handler, roles in router.ROUTES if "activity" in pattern and not pattern.startswith("/me")]
        self.assertEqual(found, [("GET", ("ops", "owner"), activity.activity_page)])


class ItChangesNothing(unittest.TestCase):
    def test_it_reads_and_writes_nothing_head_is_a_get_without_a_body_and_a_post_is_not_a_route(self):
        class ReadOnly(MemoryStore):
            locked = False

            def __getattribute__(self, name):
                if object.__getattribute__(self, "locked") and name.endswith(("_put", "_delete", "_claim", "_update", "_release", "_new", "_use", "_take")):
                    raise AssertionError(f"the page wrote: {name}")
                return super().__getattribute__(name)

        store = ReadOnly(clock=lambda: NOW)
        console = seeded(Console(store=store))
        store.locked = True
        reply, head = console.get(PATH), console.send("HEAD", PATH)
        self.assertEqual((reply.status, head.status, head.body), (200, 200, b""))
        self.assertEqual(console.post(PATH, {}).status, 405)

    def test_the_same_records_give_the_same_page(self):
        self.assertEqual(seeded().get(PATH).text, seeded().get(PATH).text)


if __name__ == "__main__":
    unittest.main()
