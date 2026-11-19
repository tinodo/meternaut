"""The page "What the AI looked at" (docs/proposals/23-what-the-ai-looked-at.md): the latest investigation as the app kept it, which kinds of resource its tools read and which not, every finding and
what became of it, and the earlier runs. The page shows no amount of money and no share of the bill (rule 25). Every kind of resource here is invented (contoso.example/...).
"""
import unittest

from test_web_support import MAYA, NOW, OPS, OWNER, STRANGER, SUB, TINO, XSS, XSS_ESCAPED, Console, FailingStore, at, make_run

from cases.memory_store import MemoryStore
from cases.models import INVESTIGATION_ENDS, KEPT_INVESTIGATIONS, InvestigationRecord
from cases.web import activity, router

PATH = "/ops/activity"
WIDGETS, GADGETS, GIZMOS, ANVILS = "contoso.example/widgets", "contoso.example/gadgets", "contoso.example/gizmos", "contoso.example/anvils"
HEADINGS = ["What the AI looked at and concluded", "Findings of the last run", "Which kinds of resource the AI looked at", "Earlier runs", "What this page cannot tell"]
PHRASES = ("widgets r1: MetricA is there, so no idle finding", "gadgets r53: MetricB is not offered, could not judge use", "gizmos: not examined before the tool budget ended")


def finding(n: int, **more) -> dict:
    return {**{"n": n, "basis": "no-usage", "proposal": "delete", "sure": 0.85, "resources": 4, "says": "Nothing used these in the window.", "verdict": "agree", "kept": True}, **more}


FINDINGS = (finding(1, fates={"request": 3, "automation": 1, "managed": 2}, left={"guarded": 1}),
            finding(2, basis="other", proposal="investigate", sure=0.4, resources=6, says="Looks unusual.", verdict="", kept=False, left={"unknown": 6}),
            finding(3, basis="oversized", proposal="change", sure=0.7, resources=2, says="Larger than needed.", verdict="disagree", doubts=["A monthly job may need it."], fates={"person": 2}))


def record(run_id: str = "run00001", when: str | None = None, **more) -> InvestigationRecord:
    """The latest run: the estate has 5 kinds, the tools read widgets (listed, measured and described) and gizmos (measured), and the 3 others were not read (the dearest first)."""
    base = dict(run_id=run_id, at=when or at(hours=-2), trigger="timer", investigator="model-a", skeptic="model-b", calls=30, max_calls=30, tokens=12345, seconds=140, max_seconds=600, end="calls",
                answered=True, examined=PHRASES, findings=FINDINGS, known=5, looked=2, kinds=([WIDGETS, "lmd"], [GIZMOS, "m"]), unread=(GADGETS, ANVILS, "contoso.example/bolts"), subs=2, subs_costed=2)
    base.update(more)
    return InvestigationRecord(**base)


def seeded(console: Console | None = None) -> Console:
    """The latest run and one before it, three runs that investigated (the second has no record) and one that did not."""
    console = console or Console()
    store = console.store
    store.investigation_put(record())
    store.investigation_put(record("run00003", at(days=-15), calls=12, end="answered", findings=(finding(1), finding(2)), known=10, looked=4))
    for run in (make_run(run_id="run00001", started_at=at(hours=-2), investigated=True), make_run(run_id="run00002", started_at=at(days=-8), investigated=True),
                make_run(run_id="run00003", started_at=at(days=-15), investigated=True), make_run(run_id="run00004", started_at=at(days=-1))):
        store.run_put(run)
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
        self.assertEqual([reply.table(name).caption for name in ("findings", "looked", "unread", "earlier")], [
            "Findings of the last run", "Looked at: kinds of resource, the dearest first", "Not looked at: kinds of resource, the dearest first",
            "The 10 investigations before the latest, newest first"])
        self.assertEqual(reply.forms(), [])
        self.assertEqual(reply.root.find("main").classes(), ["wide"])
        self.assertIn("You see this because your role ops or owner lets you see what the AI looked at.", reply.content)
        self.assertIn("This page changes nothing.", reply.main.find("div", class_="head").find("p").text())

    def test_the_page_shows_no_amount_of_money_and_no_share_of_the_bill(self):
        for reply in (self.reply, page_of(record(), runs=[make_run(run_id="run00002", started_at=at(days=-8), investigated=True)])):
            text = reply.main.text()
            self.assertNotRegex(text, r"[$€£]|\d\s?%|\bpercent\b|\bUSD\b|\bsaves?\b", "no amount, no percentage, no saving")
            for words in ("Cost in 30 days", "Share of the cost", "What they cost", "cost report", "Where the money goes"):
                self.assertNotIn(words, text)

    def test_the_tiles_say_how_many_kinds_the_tools_read_how_many_findings_were_kept_and_why_the_run_stopped(self):
        looked, kept, stopped = tiles_of(self.reply).values()
        self.assertEqual(looked, ("2 of 5 kinds of resource", "A tool read 2 of the 5 kinds of resource that the estate is known to have."))
        self.assertEqual(kept, ("2 of 3 findings", "The checks of code kept 2 of the 3 findings that the AI wrote."))
        self.assertEqual(stopped, ("Its calls ran out", "It made 30 of the 30 tool calls that it was allowed and used 140 of the 600 seconds. "
                                                        "It used all its tool calls, so it was told to answer with what it had."))

    def test_the_phrases_are_the_ais_own_and_the_labels_of_a_run_are_said_to_mean_nothing_outside_it(self):
        main = self.reply.main
        self.assertEqual(main.find("p", class_="quote-label").text(), "Written by the AI")
        self.assertEqual([li.text() for li in main.find("blockquote").find_all("li")], list(PHRASES), "as the AI wrote them, labels such as r1 and r53 included")
        self.assertIn("Labels such as r1 and r53 stand for a resource inside that run only. They mean nothing outside it, and this page does not say which resource they were.", self.reply.content)
        self.assertIn("started by the daily timer. The first AI was model-a and the second AI was model-b.", self.reply.content)

    def test_each_finding_says_what_it_says_how_sure_it_is_how_many_resources_and_what_became_of_them(self):
        table = self.reply.table("findings")
        self.assertEqual(table.headers, ["What it says", "How sure (0 to 1)", "Resources", "The second AI", "What became of it"])
        first, dropped, third = table.rows
        self.assertEqual(first["What it says"], "Nothing used these in the window. No recorded usage. Proposal: delete.")
        self.assertEqual((first["How sure (0 to 1)"], first["Resources"], first["The second AI"]), ("0.85", "4", "Agrees"))
        self.assertEqual(first["What became of it"], "3 resources: a request was made 1 resource: held back, managed by an automation 2 resources: a request was made; an automation manages the resource "
                         "Left out: 1 resource held back by a guard", "a record of a run before the warning says what it said (`automation`), and a record of a run after it says `managed`")
        self.assertEqual((dropped["What it says"], dropped["Resources"], dropped["The second AI"]),
                         ("Looks unusual. Another reason. Proposal: investigate.", "6 listed", "Not asked: the finding was dropped before it"))
        self.assertEqual(dropped["What became of it"], "Dropped: no resource of it was left (6 resources that no tool showed)")
        self.assertEqual((third["The second AI"], third["What became of it"]), ("Disagrees A monthly job may need it.", "2 resources: left for a person, no request yet"))

    def test_the_kinds_are_two_lists_the_ones_that_the_tools_read_with_what_they_did_and_the_ones_that_they_did_not_each_with_its_count_and_the_dearest_first(self):
        reply = self.reply
        self.assertEqual([list(row.values()) for row in reply.table("looked").rows], [[WIDGETS, "listed, measured, described"], [GIZMOS, "measured"]])
        self.assertEqual([list(row.values()) for row in reply.table("unread").rows], [[GADGETS], [ANVILS], ["contoso.example/bolts"]], "in the order that the record gives")
        self.assertEqual(reply.table("looked").headers, ["Kind of resource", "What the tools did"])
        self.assertIn("Looked at: 2 of 5 kinds.", reply.content)
        self.assertIn("Not looked at: 3 of 5 kinds.", reply.content)
        self.assertIn("They are in the order of what each cost in the last 30 days, the dearest first, and no amount is shown.", reply.content)
        self.assertIn("\"Looked at\" means that a tool read that kind in the last investigation. It does not mean that the AI judged all of it.", reply.content)

    def test_when_a_list_is_longer_than_the_record_keeps_the_page_says_how_many_are_shown(self):
        kinds = tuple([f"contoso.example/kind{n:02d}", "l"] for n in range(20))
        unread = tuple(f"contoso.example/other{n:02d}" for n in range(20))
        reply = page_of(record(known=70, looked=30, kinds=kinds, unread=unread))
        self.assertIn("Looked at: 30 of 70 kinds. The 20 dearest are shown.", reply.content)
        self.assertIn("Not looked at: 40 of 70 kinds. The 20 dearest are shown.", reply.content)
        self.assertEqual((len(reply.table("looked").rows), len(reply.table("unread").rows)), (20, 20))
        self.assertIn("Looked at: 2 of 5 kinds.", self.reply.content)
        self.assertNotIn("dearest are shown", self.reply.content, "all of them are shown")

    def test_a_list_with_nothing_in_it_has_a_count_and_no_table(self):
        reply = page_of(record(known=2, looked=2, kinds=([WIDGETS, "l"], [GIZMOS, "l"]), unread=()))
        self.assertIn("Not looked at: 0 of 2 kinds.", reply.content)
        self.assertFalse(reply.has_table("unread"))
        reply = page_of(record(known=2, looked=0, kinds=(), unread=(WIDGETS, GIZMOS)))
        self.assertIn("Looked at: 0 of 2 kinds.", reply.content)
        self.assertEqual((reply.has_table("looked"), len(reply.table("unread").rows)), (False, 2))

    def test_the_order_rests_on_the_cost_that_was_read_and_the_page_says_where_none_or_not_all_of_it_was(self):
        self.assertNotIn("The order rests on", self.reply.content, "all the subscriptions were costed")
        self.assertIn("The order rests on the cost of 1 of 3 subscriptions.", page_of(record(subs=3, subs_costed=1)).content)
        self.assertIn("No cost was read in US dollars, so the kinds are in the order of their names.", page_of(record(subs=3, subs_costed=0)).content)

    def test_a_run_that_knows_no_kind_says_so_and_does_not_say_zero(self):
        reply = page_of(record(known=0, looked=0, kinds=(), unread=()))
        self.assertEqual(tiles_of(reply)["Looked at in the last run"], ("—", activity.NO_KINDS))
        self.assertEqual(reply.main.text().count(activity.NO_KINDS), 2, "the tile and the block")
        self.assertFalse(reply.has_table("looked"))

    def test_the_earlier_runs_are_one_line_each_and_a_run_that_has_no_record_is_not_recorded_and_never_zero(self):
        table = self.reply.table("earlier")
        self.assertEqual(table.headers, ["Started", "Tool calls", "Findings kept", "Kinds looked at", "Stopped because"])
        self.assertEqual([list(row.values())[1:] for row in table.rows], [["Not recorded for earlier runs", "—", "—", "—"], ["12 of 30", "2 of 2", "4 of 10", "It gave its answer"]],
                         "the run of the day before did not investigate and is not listed")
        self.assertNotIn("0 of 0", self.reply.content)
        self.assertEqual(page_of(record("run00005", known=0, looked=0), record("run00006", at(days=-3), known=0, looked=0)).table("earlier").rows[0]["Kinds looked at"], "not known")

    def test_the_limits_of_the_page_are_said_in_one_paragraph_and_a_person_with_the_role_ops_is_pointed_to_every_run(self):
        self.assertIn("The phrases are the AI's own claims, and code did not check them. \"Looked at\" means that a tool read the kind of resource. It does not mean that the AI judged all of it. "
                      "A run from before this page existed was not recorded, which is not the same as nothing.", self.reply.content)
        self.assertIn("/ops/runs", self.reply.links())


class HowTheRunEnded(unittest.TestCase):
    def tile(self, **more) -> tuple[str, str]:
        return tiles_of(page_of(record(**more)))["Stopped because"]

    def test_the_small_label_of_what_left_a_finding_is_on_the_page_for_a_kept_finding_and_for_a_dropped_one(self):
        small = "in a finding that together costs too little to open a case"
        reply = page_of(record(findings=(finding(1, left={"small": 3}), finding(2, kept=False, resources=2, left={"small": 2}))))
        kept, dropped = reply.table("findings").rows
        self.assertEqual(kept["What became of it"], f"Left out: 3 resources {small}")
        self.assertEqual(dropped["What became of it"], f"Dropped: no resource of it was left (2 resources {small})")

    def test_each_word_of_the_list_says_what_it_stands_for_with_the_calls_and_the_seconds_that_were_used_of_the_allowed(self):
        said = {"answered": ("It gave its answer", "It gave its answer within its limits."), "time": ("Its time ran out", "Its time for tool calls ran out, so it was told to answer with what it had."),
                "calls": ("Its calls ran out", "It used all its tool calls, so it was told to answer with what it had."),
                "tokens": ("Its tokens ran out", "The tokens that it was allowed ran out, so it was told to answer with what it had."),
                "refused": ("It was not allowed to run", "A safeguard around the agents did not let it run, or stopped it."),
                "empty": ("It had nothing to look at", "No resource of its kinds was listed, so it was not asked."), "failed": ("It failed", "It gave no answer that could be read.")}
        self.assertEqual(set(said), set(INVESTIGATION_ENDS), "every word that the record can hold has its words on the page")
        for end, (word, meaning) in said.items():
            with self.subTest(end=end):
                self.assertEqual(self.tile(end=end, calls=9, max_calls=30, seconds=61, max_seconds=600), (word, f"It made 9 of the 30 tool calls that it was allowed and used 61 of the 600 seconds. {meaning}"))

    def test_a_run_that_was_refused_says_why_in_the_words_of_the_code_that_the_safeguards_gave(self):
        for stop, why in (("tokens", "Its token limit was used up."), ("switch", "A switch that holds the agents is pulled."), ("refusals", "Too many of its tool calls were refused.")):
            with self.subTest(stop=stop):
                self.assertTrue(self.tile(end="refused", stop=stop)[1].endswith(f"or stopped it. {why}"))
        self.assertTrue(self.tile(end="refused", stop="a code that nobody listed")[1].endswith("did not let it run, or stopped it."), "what is not listed is not said")

    def test_a_run_that_used_up_its_time_its_calls_or_its_tokens_and_gave_no_answer_that_could_be_read_says_that_too(self):
        for end in ("time", "calls", "tokens"):
            with self.subTest(end=end):
                self.assertTrue(self.tile(end=end, answered=False, findings=())[1].endswith("answer with what it had. Its answer could not be read."))

    def test_a_run_with_no_answer_has_no_finding_to_count_and_says_why(self):
        reply = page_of(record(end="failed", answered=False, findings=(), examined=(), note="the investigator gave no answer (the service gave no usable answer)", calls=3, seconds=42))
        self.assertEqual(tiles_of(reply)["Findings kept"], ("—", "The AI gave no answer that code could read, so there is no finding to check."))
        self.assertIn("used 42 of the 600 seconds", tiles_of(reply)["Stopped because"][1])
        self.assertIn("There is no finding: the AI gave no answer that code could read.", reply.content)
        self.assertIn("The AI wrote no phrase about what it examined in this run.", reply.content)
        self.assertIn("It did not finish", reply.content)
        self.assertIn("the investigator gave no answer (the service gave no usable answer)", reply.content)

    def test_an_answer_with_no_finding_is_not_a_failure(self):
        reply = page_of(record(end="answered", findings=()))
        self.assertEqual(tiles_of(reply)["Findings kept"][0], "0 of 0 findings")
        self.assertIn("The AI wrote no finding.", reply.content)
        self.assertNotIn("It did not finish", reply.content)


def beat_row(n: int, kinds=(WIDGETS,), **more) -> dict:
    return {**{"n": n, "kinds": list(kinds), "billing": False, "more": 0, "calls": 7, "max_calls": 8, "tokens": 98765, "seconds": 131, "end": "answered", "seeded": 3, "looked": 1, "found": 2,
               "says": ["widgets: nothing idle, one is larger than its use needs"]}, **more}


BEATS = (beat_row(1, (WIDGETS, GADGETS)), beat_row(2, (GIZMOS,), end="tokens", looked=0, found=0, says=[]), beat_row(3, (), billing=True, looked=0, says=["the bill lines were looked at"]),
         beat_row(4, (ANVILS,), more=5, end="failed", calls=0, tokens=0))


class TheBeatsOfTheLatestInvestigation(unittest.TestCase):
    def setUp(self):
        self.reply = page_of(record(beats=BEATS, findings=(finding(1, beat=1), finding(2, beat=3)), more=4, max_calls=32, calls=21))

    def test_the_page_has_a_block_for_the_parts_between_what_the_ai_concluded_and_its_findings_and_no_block_for_a_run_that_had_none(self):
        self.assertEqual(self.reply.headings(2), [HEADINGS[0], "The parts that the AI looked at", *HEADINGS[1:]])
        self.assertEqual(page_of(record()).headings(2), HEADINGS, "an investigation of one session has no such block")
        self.assertIn("Code chose the parts by what each kind of resource cost in the last 30 days, the dearest first, and no amount is shown.", self.reply.content)

    def test_each_part_is_a_row_with_its_kinds_what_it_used_how_it_ended_how_many_of_its_kinds_its_tools_read_and_what_it_found(self):
        table = self.reply.table("beats")
        self.assertEqual(table.headers, ["Part", "Kinds of resource", "Tool calls", "Seconds", "Tokens", "Stopped because", "Kinds looked at", "Findings", "What the AI said it examined"])
        rows = [list(row.values()) for row in table.rows]
        self.assertEqual(rows[0][2:], ["7 of 8", "131", "98,765", "It gave its answer", "1 of 2", "2", "widgets: nothing idle, one is larger than its use needs"])
        self.assertEqual((rows[1][5], rows[1][6], rows[1][7], rows[1][8]), ("Its tokens ran out", "0 of 1", "0", "—"))
        self.assertEqual((rows[2][1], rows[2][6]), ("the lines of the bill that no resource owns", "—"), "a part with no kind has nothing to count")
        self.assertIn("5 more kinds", rows[3][1])
        self.assertEqual((rows[3][5], rows[3][3]), ("It failed", "131"))
        for kind in (WIDGETS, GADGETS, GIZMOS, ANVILS):
            self.assertIn(kind, self.reply.content)

    def test_the_findings_say_which_part_wrote_them_and_how_many_the_record_had_no_room_for(self):
        table = self.reply.table("findings")
        self.assertEqual(table.headers[:2], ["Part", "What it says"])
        self.assertEqual([row["Part"] for row in table.rows], ["1", "3"])
        self.assertIn("The sentences of the second column were written by the AI.", self.reply.content)
        self.assertIn("The record has room for 2 findings. 4 more were written, and they are not listed here.", self.reply.content)
        self.assertEqual(page_of(record()).table("findings").headers[0], "What it says", "no column for a part when there are none")

    def test_the_tile_counts_the_calls_of_all_the_parts_and_the_page_shows_no_amount_and_no_share_of_the_bill(self):
        self.assertEqual(tiles_of(self.reply)["Stopped because"][1].split(" It ")[0], "It made 21 of the 32 tool calls that it was allowed and used 140 of the 600 seconds.")
        text = self.reply.main.text()
        self.assertNotRegex(text, r"[$€£]|\d\s?%|\bpercent\b|\bUSD\b|\bsaves?\b", "no amount, no percentage, no saving")
        self.assertEqual(self.reply.problems, [])

    def test_a_payload_in_the_kinds_or_the_phrases_of_a_part_is_escaped_and_an_id_is_taken_out(self):
        hostile = f"{XSS} /subscriptions/{SUB}/resourceGroups/rg-secret/providers/Contoso.Example/widgets/prod-widget"
        reply = page_of(record(beats=({**beat_row(1, (XSS, "not a kind", GADGETS), says=[hostile], end=XSS, calls=XSS, tokens=-5, looked=XSS), "n": XSS},)))
        for payload in (XSS, "<script", "<img", "onerror=alert(2)>"):
            self.assertNotIn(payload, reply.text)
        for estate in (SUB, "rg-secret", "prod-widget", "/subscriptions"):
            self.assertNotIn(estate, reply.text, estate)
        self.assertEqual(reply.status, 200)
        (row,) = [list(row.values()) for row in reply.table("beats").rows]
        self.assertEqual((row[0], row[2], row[4], row[5]), ("0", "0 of 8", "0", "It failed"), "what is not a number is not shown as one, and an ending that nobody listed is a failure")


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
    def test_a_store_that_cannot_give_the_records_is_the_plain_fault_of_the_router_and_no_trace(self):
        reply = Console(store=FailingStore(fail={"investigations_recent"}, clock=lambda: NOW)).get(PATH)
        self.assertEqual(reply.status, 503)
        self.assertEqual(reply.headings(1), ["Meternaut cannot reach its records"])
        self.assertIn("Nothing has changed.", reply.content)
        self.assertNotIn("Traceback", reply.text)
        self.assertNotIn("StoreError", reply.text)

    def test_when_the_runs_cannot_be_read_the_page_says_that_a_run_with_no_record_is_not_listed(self):
        reply = seeded(Console(store=FailingStore(fail={"runs_recent"}, clock=lambda: NOW))).get(PATH)
        self.assertEqual(reply.status, 200)
        self.assertIn("Meternaut cannot read the runs now, so a run with no record is not listed. Nothing has changed.", reply.content)
        self.assertEqual([row["Tool calls"] for row in reply.table("earlier").rows], ["12 of 30"])

    def test_the_page_reads_the_records_and_the_runs_and_nothing_else(self):
        reply = seeded(Console(store=FailingStore(fail={"cases_recent", "plans_open", "plans_recent", "actions_recent", "decisions_of_plan", "switch_get"}, clock=lambda: NOW))).get(PATH)
        self.assertEqual((reply.status, reply.problems), (200, []))
        self.assertEqual(reply.headings(2), HEADINGS)


class WhatItShowsOfTheEstate(unittest.TestCase):
    HOSTILE = f"{XSS} /subscriptions/{SUB}/resourceGroups/rg-secret/providers/Contoso.Example/widgets/prod-widget and {SUB}"

    def hostile(self) -> InvestigationRecord:
        entry = finding(1, says=self.HOSTILE, doubts=[self.HOSTILE], note=self.HOSTILE, fates={XSS: 2, "request": 1}, left={XSS: 3}, verdict=XSS, basis=XSS, proposal=XSS, sure=XSS)
        return record(investigator=self.HOSTILE, skeptic=XSS, trigger=XSS, end=XSS, stop=XSS, note=self.HOSTILE, examined=(self.HOSTILE, XSS), findings=(entry,),
                      known=4, looked=1, kinds=([XSS, XSS], [GADGETS, 5], "not a kind", [WIDGETS]), unread=(XSS, 7))

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
        self.assertEqual([row["Kind of resource"] for row in reply.table("unread").rows], ["microsoft.example/things"], "the kind is a word of the platform: it is there, and no tool read it")


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
