"""The record of an investigation: what the tools touched, the cost by kind and the share that they looked at, the words of how it ended, the AI's own text with no id and no name in it, the size,
and the writer at the end of the investigation, which never fails the Watch (docs/proposals/23-what-the-ai-looked-at.md).

Every kind of resource here is invented (contoso.example/...), and every number of the coverage is worked out by hand in the test that checks it.
"""
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from support import NOW, RG, SUBSCRIPTION, LogCapture, fixed_clock
from test_investigate import FakeFoundry, FakeToolbox, Harness, Moving, answer, finding, loop_for, make_settings, metrics, resource

from cases import activity, agents, investigate, roles
from cases.detectors import Context
from cases.foundry import AgentRun, FoundryError
from cases.harness import HarnessRefused
from cases.memory_store import MemoryStore, stamp
from cases.models import INVESTIGATION_ENDS, INVESTIGATION_TOUCHES, InvestigationRecord, StoreError
from cases.store import MAX_DATA
from cases.toolbox import TOOLS, Resource, type_word
from cases.web.activity import FATES

WIDGETS, GADGETS, GIZMOS = "contoso.example/widgets", "contoso.example/gadgets", "contoso.example/gizmos"
THINGS = "microsoft.example/things"  # the kind that test_investigate invents


def rid(kind: str, n: int) -> str:
    """The id of a resource of an invented kind, in lower case as Cost Management gives it."""
    provider, _, name = kind.partition("/")
    return f"{RG}/rg-app/providers/{provider}/{name}/{name}-{n}".lower()


def member(handle: str, kind: str, name: str = "") -> Resource:
    return Resource(handle=handle, resource_id=rid(kind, int(handle[1:])), resource_type=kind, name=name or f"{kind.partition('/')[2]}-{handle[1:]}", resource_group="rg-app",
                    subscription_id=SUBSCRIPTION, location="swedencentral", tags={}, managed_by="")


def call(name: str, ok: bool = True, **arguments) -> dict:
    return {"name": name, "arguments": arguments, "ok": ok, "chars": 10}


def toolbox_of(log: list, *resources: Resource) -> SimpleNamespace:
    return SimpleNamespace(handles={r.handle: r for r in resources}, log=log)


def context(costs, currency="USD", **more) -> Context:
    return Context(locks=[], recent=set(), managed_groups=set(), costs=costs, currency=currency, **more)


class WhatTheToolsTouched(unittest.TestCase):
    WORLD = (member("r1", WIDGETS), member("r2", WIDGETS), member("r10", GADGETS), member("r20", GIZMOS))

    def touched(self, *log, costed=()):
        toolbox = toolbox_of(list(log), *self.WORLD)
        return activity.touched(toolbox, activity.known(toolbox, dict.fromkeys(costed, 1.0)))

    def test_a_kind_is_touched_by_the_tool_that_names_it_or_one_of_its_resources_and_the_record_says_how(self):
        found = self.touched(call("list_resources", type=WIDGETS), call("measure", type=GADGETS, metric="MetricA"), call("describe", handle="r20"),
                             call("metric_split", handle="r10", metric="MetricA", dimension="Dim"), call("data_volume", handle="r1"))
        self.assertEqual(found, {WIDGETS: "ld", GADGETS: "ms", GIZMOS: "d"}, "the letters come in the order listed, measured, described, split")
        self.assertEqual(list(INVESTIGATION_TOUCHES.values()), ["listed", "measured", "described", "split"])

    def test_a_measurement_of_handles_touches_the_kind_of_each_handle_and_a_cost_read_touches_a_kind_only_when_it_names_one(self):
        found = self.touched(call("metric_summary", handles=["r1", "r10", "r99"], metric="MetricA"), call("cost_lines", type=GIZMOS), call("cost_lines", service="Some Service"),
                             call("cost_history", handle="r2"), call("cost_meters", handle="r10"), call("cost_meters", service="Some Service"))
        self.assertEqual(found, {WIDGETS: "lm", GADGETS: "lm", GIZMOS: "l"})

    def test_a_tool_that_shows_a_list_touches_no_kind_and_neither_does_a_call_that_failed_or_that_names_nothing_that_exists(self):
        found = self.touched(call("estate_overview"), call("metric_names", type=WIDGETS), call("advisor_items"), call("paid_features"), call("commitments"), call("recall_lessons", type=WIDGETS),
                             call("recall_open_questions"), call("list_resources", ok=False, type=WIDGETS), call("describe", handle="r99"), call("list_resources", type="Not A Type!"),
                             call("list_resources", type=[GIZMOS]), {"name": "describe", "arguments": {"truncated": True}, "ok": True}, {"name": "describe", "ok": True},
                             call("a_tool_that_is_not_there", type=WIDGETS), "not a call")
        self.assertEqual(found, {})

    def test_a_kind_that_no_handle_and_no_cost_line_shows_to_exist_is_not_one_that_a_tool_looked_at(self):
        phantom = "contoso.example/phantoms"
        log = [call("list_resources", type=phantom), call("measure", type=phantom, metric="MetricA"), call("list_resources", type=GIZMOS)]
        self.assertEqual(self.touched(*log), {GIZMOS: "l"})
        self.assertEqual(self.touched(*log, costed=[phantom]), {GIZMOS: "l", phantom: "lm"}, "a kind that has cost lines exists, whatever its handles")

    def test_the_kinds_that_the_estate_has_are_those_of_the_handles_and_of_the_cost_lines_and_a_kind_that_is_too_long_is_not_one(self):
        long = f"contoso.example/{'x' * 50}/{'y' * 20}"  # every part is as long as a part may be, and the whole is longer than MAX_KIND
        self.assertEqual((len(long) > activity.MAX_KIND, type_word(long)), (True, long))
        world = toolbox_of([], member("r1", WIDGETS), member("r2", long))
        self.assertEqual(activity.known(world, {GADGETS: 5.0}), {WIDGETS, GADGETS})
        self.assertEqual(activity.known(None, {}), set())

    def test_every_tool_of_the_toolbox_touches_kinds_or_shows_a_list_and_a_new_tool_has_to_be_put_in_one_of_the_two(self):
        shows_a_list = {"estate_overview", "metric_names", "advisor_items", "paid_features", "commitments", "recall_lessons", "recall_knowledge", "recall_open_questions", "price_alternatives"}
        self.assertEqual(set(TOOLS) - set(activity.VERBS), shows_a_list)
        self.assertLessEqual(set(activity.VERBS) - set(TOOLS), set(), "no tool is named that the toolbox has not")
        self.assertLessEqual(set("".join(activity.VERBS.values())), set(INVESTIGATION_TOUCHES))

    def test_a_reference_a_profile_and_an_age_touch_the_kind_of_each_handle_and_a_profile_describes_and_measures(self):
        found = self.touched(call("neighbors", handle="r1"), call("profile", handles=["r10", "r20"]), call("changes", handles=["r2"]))
        self.assertEqual(found, {WIDGETS: "d", GADGETS: "md", GIZMOS: "md"}, "a profile of handles of two kinds touches both, and the page says measured and described")

    def test_a_picture_credits_a_kind_only_for_the_resources_that_the_call_says_it_held_data_of_and_with_the_letters_of_what_it_held(self):
        picture = {**call("profile", handles=["r10", "r20"]), "read": {"r10": "m"}}
        found = self.touched(picture, {**call("neighbors", handle="r1"), "read": {}}, {**call("changes", handles=["r2", "r10"]), "read": {"r2": "d"}})
        self.assertEqual(found, {GADGETS: "m", WIDGETS: "d"}, "no letter for what the answer held nothing of, and none for a kind of which no resource held anything")
        self.assertEqual(self.touched({**call("profile", handles=["r10"]), "read": {"r10": "md"}}), {GADGETS: "md"})
        self.assertEqual(self.touched({**call("profile", handles=["r10"]), "read": {"r1": "md", "r10": ""}}), {}, "a resource that the call was not given is not credited, and one with no letters has none")

    def test_a_toolbox_that_shows_nothing_touched_nothing(self):
        self.assertEqual(activity.touched(None, set()), {})
        self.assertEqual(activity.touched(SimpleNamespace(), {WIDGETS}), {})


class TheKindsOfTheRun(unittest.TestCase):
    """The cost lines of the run, by hand: 600 + 50 in widgets, 300 in gadgets, 40 and 10 that no kind has, and a credit of 5 in gizmos. They only order the kinds: no amount is kept."""

    def costs(self):
        return {"1": context({rid(WIDGETS, 1): 600.0, rid(WIDGETS, 2): 50.0, rid(GADGETS, 3): 300.0, "": 40.0, f"/subscriptions/{SUBSCRIPTION}": 10.0, rid(GIZMOS, 4): -5.0}),
                "2": context({rid(WIDGETS, 9): 77.0}, currency="EUR"), "3": context(None, cost_error=True), "4": context({}, currency=None)}

    def test_it_adds_the_lines_of_the_subscriptions_that_were_read_in_dollars_by_kind_and_leaves_out_a_credit_and_a_line_of_no_kind(self):
        kinds, read = activity.costs_by_kind(self.costs())
        self.assertEqual(kinds, {WIDGETS: 650.0, GADGETS: 300.0})
        self.assertEqual(read, 2, "the one with lines in dollars and the one that was read and has no line; euros and a read that failed are not counted")

    def test_a_kind_that_has_no_shape_of_a_kind_is_left_out(self):
        long = f"{RG}/g/providers/Contoso.Example/{'a' * 48}/n1/{'b' * 48}/n2"
        kinds, _ = activity.costs_by_kind({"1": context({long: 3.0, f"{RG}/g/providers/Contoso.Example/{'x' * 90}/n": 4.0})})
        self.assertEqual(kinds, {}, "one is longer than a kind of resource is and the other has a part that a kind of resource has not")

    def test_the_record_lists_the_kinds_that_the_tools_read_and_those_that_they_did_not_each_with_the_dearest_first_and_keeps_no_amount(self):
        """Known: widgets (650), gadgets (300) and gizmos (a credit, so no cost, but its handle shows it). Read: widgets and gizmos. 2 of 3 kinds."""
        h = Harness(FakeFoundry(answer(finding()), tool_calls=(("list_resources", {"type": WIDGETS}), ("describe", {"handle": "r20"}))), FakeToolbox([member("r20", GIZMOS)], {"r20": metrics(MetricA=0)}),
                    with_store=True)
        h.contexts = self.costs()
        h.s.settings = replace(h.s.settings, subscriptions=("1", "2", "3", "4"))
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual((record.known, record.looked), (3, 2))
        self.assertEqual([list(k) for k in record.kinds], [[WIDGETS, "l"], [GIZMOS, "d"]], "what the tools did to each, the dearest first")
        self.assertEqual(record.unread, (GADGETS,))
        self.assertEqual((record.subs, record.subs_costed), (4, 2))
        data = json.loads(record.to_json())
        self.assertEqual([key for key in data if key.startswith("cost_") or "usd" in key], [], "no amount of money is in the record")
        self.assertTrue(all(isinstance(word, str) for kind in record.kinds for word in kind), "a kind and the letters of what was done, and nothing else")

    def test_the_order_is_by_the_cost_lines_and_a_kind_with_no_cost_comes_after_those_that_have_one_by_its_name(self):
        costs = {rid(GADGETS, 1): 5.0, rid(WIDGETS, 2): 9.0, rid("contoso.example/anvils", 3): 7.0}
        h = Harness(FakeFoundry(answer(finding()), tool_calls=(("describe", {"handle": "r20"}), ("describe", {"handle": "r21"}))),
                    FakeToolbox([member("r20", GIZMOS), member("r21", "contoso.example/bolts")], {}), with_store=True)
        h.contexts = {"1": context(costs)}
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual([k[0] for k in record.kinds], ["contoso.example/bolts", GIZMOS], "read, and no cost line: by name")
        self.assertEqual(record.unread, (WIDGETS, "contoso.example/anvils", GADGETS), "9, 7 and 5")

    def test_a_run_whose_cost_could_not_be_read_in_dollars_orders_by_name_and_says_that_none_was_costed(self):
        h = Harness(FakeFoundry(answer(finding())), FakeToolbox([member("r20", GIZMOS), member("r21", WIDGETS)], {}), with_store=True)
        h.contexts = {"1": context(None, cost_error=True), "2": context({rid(WIDGETS, 1): 5.0}, currency="EUR")}
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual((record.known, record.looked, record.kinds, record.unread, record.subs_costed), (2, 0, (), (GIZMOS, WIDGETS), 0))

    def test_only_the_first_kinds_of_each_list_are_kept_and_the_counts_still_count_all_of_them(self):
        costs = {rid(f"contoso.example/kind{n:02d}", n): float(n) for n in range(1, 61)}
        h = Harness(FakeFoundry(answer(finding()), tool_calls=tuple(("list_resources", {"type": f"contoso.example/kind{n:02d}"}) for n in range(31, 61))), FakeToolbox([], {}), with_store=True)
        h.contexts = {"1": context(costs)}
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual((record.known, record.looked), (60, 30))
        self.assertEqual((len(record.kinds), len(record.unread)), (activity.MAX_KINDS, activity.MAX_KINDS))
        self.assertEqual([k[0] for k in record.kinds[:2]], ["contoso.example/kind60", "contoso.example/kind59"])
        self.assertEqual(record.unread[:2], ("contoso.example/kind30", "contoso.example/kind29"))


class HowTheRunEnded(unittest.TestCase):
    @staticmethod
    def out(answer=None, **changes):
        out = investigate.Investigation()
        out.answer = answer
        for name, value in changes.items():
            setattr(out, name, value)
        return out

    @staticmethod
    def run_of(*, refused=0, out_of_time=False) -> AgentRun:
        return AgentRun(text="", calls=[{"name": "t", "ok": True}] * 2 + [{"name": "t", "ok": False, "refused": True}] * refused, out_of_time=out_of_time)

    def test_each_word_of_the_list_and_what_it_stands_for(self):
        for label, out, word in (("an answer within its limits", self.out(self.run_of(), ran=True), "answered"),
                                 ("its calls were used up", self.out(self.run_of(refused=3), ran=True), "calls"),
                                 ("its time for calls was used up", self.out(self.run_of(refused=1, out_of_time=True), ran=True), "time"),
                                 ("the harness did not let it run or stopped it", self.out(self.run_of(), held=True), "refused"),
                                 ("no answer that could be read", self.out(self.run_of(), ran=False), "failed"),
                                 ("nothing at all came of it", self.out(None), "failed"),
                                 ("its calls were used up and it gave no answer that could be read", self.out(self.run_of(refused=3), ran=False), "calls")):
            with self.subTest(label):
                self.assertEqual(activity.end_of(out), word)
                self.assertIn(word, INVESTIGATION_ENDS)

    def test_the_harness_is_asked_why_only_when_the_run_was_refused(self):
        harness = SimpleNamespace(records=[SimpleNamespace(outcome="ok", reason=""), SimpleNamespace(outcome="stopped", reason="tokens")], budget=SimpleNamespace(tool_calls=9))
        self.assertEqual(activity.stop_of(harness), "tokens")
        self.assertEqual(activity.stop_of(SimpleNamespace(records=[SimpleNamespace(outcome="refused", reason="switch")])), "switch")
        self.assertEqual(activity.stop_of(SimpleNamespace(records=[SimpleNamespace(outcome="ok", reason="")])), "")
        self.assertEqual(activity.stop_of(None), "")


class WhatTheAIWritesInARecord(unittest.TestCase):
    def test_an_id_and_the_name_of_a_resource_that_the_tools_showed_never_get_in_and_a_handle_stays(self):
        names = frozenset({"thing-one", "prod-db"})
        text = f"r1 and r53: Thing-One is idle, see /subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/x/y/z and {SUBSCRIPTION}, but prod-database is fine"
        self.assertEqual(activity.plain(text, 300, names), "r1 and r53: (name removed) is idle, see (id removed) and (id removed), but prod-database is fine")

    def test_a_name_that_ends_a_sentence_or_sits_in_brackets_is_taken_out_too_and_a_longer_word_is_not(self):
        text = "Nothing reads thing-one. Is (thing-one) used? THING-ONE: idle; thing-one-b and thing-one.example stay"
        self.assertEqual(activity.plain(text, 300, frozenset({"thing-one"})), "Nothing reads (name removed). Is ((name removed)) used? (name removed): idle; thing-one-b and thing-one.example stay")

    def test_html_is_kept_as_text_for_the_page_to_escape_and_a_link_and_a_figure_are_taken_out(self):
        self.assertEqual(activity.plain("<b>bold</b> https://evil.example/x costs 500 USD a month", 300), "<b>bold</b> [link removed] costs [figure removed] a month")

    def test_the_text_is_cut_by_the_size_of_its_json_so_that_characters_that_json_writes_long_cannot_make_a_record_large(self):
        for char in ("a", "\u00e9", "\u4e2d", '"', "\\"):
            with self.subTest(char=char):
                text = activity.plain(char * 500, 100)
                self.assertLessEqual(len(json.dumps(text)) - 2, 100)
                self.assertGreater(len(text), 10)
        self.assertEqual(activity.plain("short", 100), "short")
        self.assertEqual(activity.plain(None, 100), "")


class AFindingAsTheRecordKeepsIt(unittest.TestCase):
    @staticmethod
    def made(**changes):
        base = dict(number=2, basis="no-usage", proposal="delete", confidence=0.85, summary="Nothing used these in the window.", claimed=4, covered_usd=123.45)
        base.update(changes)
        return investigate.Finding(**base)

    def test_a_kept_finding_holds_what_the_page_shows_and_no_amount_of_money(self):
        f = self.made(items=[object()] * 3, verdict=roles.SkepticAnswer("disagree", ("one", "two", "three"), "A sentence."), fates={"request": 2, "nothing": 1}, guarded=1, recent=2)
        self.assertEqual(activity.entry_of(f, frozenset()), {"n": 2, "basis": "no-usage", "proposal": "delete", "sure": 0.85, "resources": 3, "says": "Nothing used these in the window.",
                                                              "verdict": "disagree", "doubts": ["one", "two"], "kept": True, "left": {"guarded": 1, "recent": 2},
                                                              "fates": {"request": 2, "nothing": 1}})

    def test_a_dropped_finding_says_what_the_ai_listed_and_what_became_of_it_and_a_finding_that_could_not_be_read_says_why(self):
        dropped = activity.entry_of(self.made(reason="no resource of it is left: 4 that no tool showed", unknown=4, covered_usd=None), frozenset())
        self.assertEqual((dropped["kept"], dropped["resources"], dropped["left"], "verdict" in dropped), (False, 4, {"unknown": 4}, False))
        unreadable = activity.entry_of(investigate.Finding(1, reason="its confidence is not a number"), frozenset())
        self.assertEqual((unreadable["kept"], unreadable["note"], "basis" in unreadable), (False, "its confidence is not a number", False))

    def test_the_note_of_code_is_kept_for_a_finding_that_code_changed(self):
        entry_ = activity.entry_of(self.made(note="others share this kind of resource, so this asks for a look and not for a deletion", items=[object()]), frozenset())
        self.assertEqual(entry_["note"], "others share this kind of resource, so this asks for a look and not for a deletion")


LONGEST = [f"contoso.example/{'a' * 50}/{n:013d}" for n in range(60)]  # kinds of the longest shape that a kind has (80 characters)


def worst(char: str = "x"):
    """An investigation at its limits: twelve phrases of a hundred characters, eight findings with every text at its longest, kinds of the longest shape, 30 of them touched in every way and 30 not.
    `char` is what the texts are made of: a character that json writes six characters long makes the same record or a smaller one."""
    log = [call(name, type=kind) for kind in LONGEST[:30] for name in ("list_resources", "measure", "describe", "metric_split")]
    findings = []
    for n in range(1, 9):
        verdict = roles.SkepticAnswer("unsure", tuple(char * 200 for _ in range(3)), "s")
        findings.append(investigate.Finding(n, basis="commitment-misfit", proposal="investigate", confidence=0.85, summary=char * 300, claimed=60, items=[object()] * 60,
                                            verdict=verdict, note=char * 300, unknown=60, unproven=60, repeated=60, guarded=60, recent=60, capped=60, fates={word: 60 for word in FATES}))
    out = investigate.Investigation(ran=True, tokens=999999, tool_calls=40, seconds=600, toolbox=toolbox_of(log), examined=[char * 100] * 12, findings=findings, note=char * 300)
    out.answer = AgentRun(text="", calls=[{"name": "t", "ok": True}])
    costs = {f"{RG}/rg-app/providers/contoso.example/{'a' * 50}/n/{n:013d}/m": 1000.0 - n for n in range(60)}
    return SimpleNamespace(contexts={SUBSCRIPTION: context(costs)}), out


class TheSizeOfARecord(unittest.TestCase):
    MAX_RECORD = 14_000  # the most characters that a record has at its limits (see worst: 13,649 with kinds of 80 characters); a usual one has two or three thousand

    def s(self):
        return SimpleNamespace(settings=make_settings(subscriptions=(SUBSCRIPTION,)), history=SimpleNamespace(run_id="r" * 32))

    def test_a_record_at_its_limits_is_far_below_what_a_table_property_may_hold_and_below_its_own_cap(self):
        for char in ("x", '"', "\u00e9", "\u4e2d"):
            with self.subTest(char=char):
                world, out = worst(char)
                record = activity.record_of(self.s(), out, world.contexts, trigger="control", at=stamp(NOW), seconds=out.seconds)
                size = len(record.to_json())
                self.assertEqual((len(record.examined), len(record.findings), len(record.kinds), len(record.unread)), (12, 8, activity.MAX_KINDS, activity.MAX_KINDS))
                self.assertEqual((record.known, record.looked), (60, 30))
                self.assertLessEqual(size, self.MAX_RECORD, f"{size} characters")
                self.assertLess(size, MAX_DATA // 2)
                self.assertEqual(InvestigationRecord.from_json(record.to_json()), record, "and it reads back as it was kept")

    def test_a_usual_record_is_about_six_kilobytes_or_less(self):
        h = Harness(FakeFoundry(answer(finding(handles=["r1", "r2"]), finding(handles=["r3"], proposal="investigate", basis="other"),
                                      examined=[f"{n}: a phrase of the AI that says what it looked at and what it concluded" for n in range(8)]),
                                tool_calls=tuple(("list_resources", {"type": f"contoso.example/kind{n:02d}"}) for n in range(15))), FakeToolbox(), with_store=True)
        h.contexts = {SUBSCRIPTION: context({rid(f"contoso.example/kind{n:02d}", n): 100.0 + n for n in range(40)})}
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertLess(len(record.to_json()), 6144, len(record.to_json()))


class TheRecordThatTheInvestigationKeeps(unittest.TestCase):
    TOOLS = (("estate_overview", {}), ("list_resources", {"type": THINGS}), ("measure", {"type": THINGS, "metric": "MetricA"}), ("describe", {"handle": "r1"}))

    def run_one(self, foundry=None, toolbox=None, *, trigger="timer", costs=None, **options):
        h = Harness(foundry or FakeFoundry(answer(finding(handles=["r1", "r2"], summary="Nothing used these in the window."), examined=("things: measured all 5", "gadgets: not examined")),
                                           tool_calls=self.TOOLS), toolbox or FakeToolbox(), with_store=True)
        h.s.trigger = trigger
        h.contexts = {SUBSCRIPTION: context(costs if costs is not None else {r.resource_id.lower(): r.cost_usd_30d for r in h.toolbox.handles.values()} | {rid(GADGETS, 1): 50.0})}
        h.go(**options)
        return h

    def record(self, h):
        (record,) = h.store.investigations_recent()
        return record

    def test_one_record_is_kept_with_when_what_started_it_the_models_the_limits_and_how_it_ended(self):
        h = self.run_one()
        record = self.record(h)
        self.assertEqual((record.run_id, record.at, record.trigger), ("r" * 32, stamp(NOW), "timer"))
        self.assertEqual((record.investigator, record.skeptic), ("model-investigator", "model-skeptic"))
        self.assertEqual((record.calls, record.max_calls, record.max_seconds), (4, 30, 600))
        self.assertEqual(record.tokens, 1000 + 200 + 500 + 100, "the Investigator's and the Skeptic's")
        self.assertEqual((record.end, record.answered, record.stop, record.note), ("answered", True, "", ""))
        self.assertEqual(record.seconds, h.result.seconds)
        self.assertEqual(record.examined, ("things: measured all 5", "gadgets: not examined"))
        self.assertTrue(h.result.ran, "and the investigation is what it was")

    def test_the_kinds_that_the_tools_read_are_worked_out_from_the_calls_that_they_made_and_the_cost_lines_only_order_them(self):
        """The five things cost 50, 40, 30, 20 and 10 and a gadget 50: the tools touched the things (listed, measured and, for r1, described), and the gadgets, the dearest of two, were not read."""
        record = self.record(self.run_one())
        self.assertEqual((record.known, record.looked), (2, 1))
        self.assertEqual([list(k) for k in record.kinds], [[THINGS, "lmd"]])
        self.assertEqual(record.unread, (GADGETS,))

    def test_a_finding_keeps_its_sentence_the_verdict_of_the_second_ai_and_what_became_of_its_resources_and_no_amount(self):
        record = self.record(self.run_one())
        (found,) = record.findings
        self.assertEqual((found["n"], found["basis"], found["proposal"], found["sure"], found["resources"], found["kept"]), (1, "no-usage", "delete", 0.9, 2, True))
        self.assertEqual((found["says"], found["verdict"], "usd" in found), ("Nothing used these in the window.", "agree", False))
        self.assertEqual(found["fates"], {"request": 2}, "a request was made for each of the two")

    def test_a_resource_that_says_nothing_is_held_back_and_the_record_says_so_beside_one_that_got_its_request(self):
        toolbox = FakeToolbox([resource(1, name="aaaaaaaa-1111-4222-8333-444444444444"), resource(2)], {"r1": metrics(MetricA=0), "r2": metrics(MetricA=0)})
        h = Harness(FakeFoundry(answer(finding(handles=["r1"]), finding(handles=["r2"]))), toolbox, with_store=True)
        h.go()
        first, second = self.record(h).findings
        self.assertEqual((first["fates"], second["fates"]), ({"nothing": 1}, {"request": 1}))

    def test_a_finding_that_the_ais_advise_to_keep_is_dropped_and_each_of_its_resources_is_counted_as_dropped(self):
        h = Harness(FakeFoundry(answer(finding(handles=["r1", "r2"], proposal="keep"))), FakeToolbox(), with_store=True)
        with mock.patch.object(agents, "PROPOSALS", (*agents.PROPOSALS, "keep")):  # the Investigator proposes none of them: the branch is what a finding that says keep comes to
            h.go()
        (found,) = self.record(h).findings
        self.assertEqual((found["kept"], found["proposal"], found["fates"]), (True, "keep", {"dropped": 2}))

    def test_a_run_that_failed_before_its_end_keeps_the_seconds_that_it_took(self):
        clock = Moving()
        foundry = FakeFoundry(tool_calls=self.TOOLS)
        foundry.after_run = lambda agent: clock.advance(seconds=42)
        foundry.investigator_error = RuntimeError("boom")
        h = Harness(foundry, FakeToolbox(), with_store=True, clock=clock)
        h.go()
        record = self.record(h)
        self.assertEqual((record.end, record.seconds), ("failed", 42))
        self.assertIn("it failed (RuntimeError: boom)", record.note)

    def test_a_dropped_finding_is_kept_with_why_and_its_resources_are_the_ones_that_the_ai_listed(self):
        h = self.run_one(FakeFoundry(answer(finding(handles=["r1", "r2"]), finding(handles=["r98", "r99", "r97"], summary="Gone."))))
        kept, dropped = self.record(h).findings
        self.assertEqual((kept["kept"], dropped["kept"], dropped["resources"], dropped["left"], dropped.get("fates")), (True, False, 3, {"unknown": 3}, None))

    def test_a_request_for_a_resource_that_an_automation_manages_is_counted_with_its_own_fate(self):
        from test_missing_data import AnAutomationsResourceIsAskedAboutWithAWarning as Held
        h = Harness(FakeFoundry(answer(finding(handles=["r1"]))), FakeToolbox([resource(1, cost_usd_30d=70.0)], {"r1": metrics(MetricA=0)}), with_store=True)
        h.arm.activity_events = lambda subscription, since, until, **kwargs: ([Held.written(2, Held.GUID)], True)
        h.go()
        (found,) = self.record(h).findings
        self.assertEqual(found["fates"], {"automation": 1})

    def test_a_finding_that_nobody_is_asked_about_is_left_for_a_person_and_a_group_counts_every_resource_that_it_stands_for(self):
        resources = [resource(n, name=f"pe-{n:02d}", cost_usd_30d=0.5) for n in range(1, 11)]
        h = Harness(FakeFoundry(answer(finding(handles=[r.handle for r in resources], basis="other", proposal="investigate", confidence=0.8, evidence=[]))),
                    FakeToolbox(resources, {r.handle: {} for r in resources}), with_store=True)
        h.go()
        (found,) = self.record(h).findings
        self.assertEqual((found["resources"], found["fates"]), (10, {"person": 10}), "ten resources, one case, no request: it costs too little to ask")

    def test_the_trigger_is_the_timer_or_a_request_and_never_the_words_that_a_message_carried(self):
        self.assertEqual(self.record(self.run_one(trigger="timer")).trigger, "timer")
        self.assertEqual(self.record(self.run_one(trigger="control")).trigger, "request")
        self.assertEqual(self.record(self.run_one(trigger="<b>a message</b> /subscriptions/x")).trigger, "request")
        self.assertEqual(self.record(self.run_one(trigger="")).trigger, "", "nothing says what started it")

    def test_a_run_that_used_up_its_calls_or_its_time_says_so(self):
        for label, change, word in (("calls", dict(refused_calls=2), "calls"), ("time", dict(refused_calls=1, out_of_time=True), "time")):
            with self.subTest(label):
                foundry = FakeFoundry(answer(finding()), tool_calls=self.TOOLS)
                for name, value in change.items():
                    setattr(foundry, name, value)
                record = self.record(self.run_one(foundry))
                self.assertEqual((record.end, record.answered, record.calls), (word, True, 4), "refused calls are no calls of the run")

    def test_an_investigator_that_gave_no_answer_is_kept_as_failed_with_the_words_of_the_run_and_no_finding(self):
        foundry = FakeFoundry(tool_calls=self.TOOLS)
        foundry.investigator_error = FoundryError("Foundry run stopped: the service gave no usable answer")
        h = self.run_one(foundry)
        record = self.record(h)
        self.assertEqual((record.end, record.answered, record.findings, record.examined), ("failed", False, (), ()))
        self.assertIn("the investigator gave no answer", record.note)
        self.assertFalse(h.result.ran)

    def test_an_answer_that_could_not_be_read_is_kept_as_failed(self):
        record = self.record(self.run_one(FakeFoundry("this is not a json object", tool_calls=self.TOOLS)))
        self.assertEqual((record.end, record.answered, record.calls), ("failed", False, 4))
        self.assertIn("no answer that could be read", record.note)

    def test_an_agent_that_the_harness_did_not_let_run_is_kept_as_refused_with_the_code_that_it_gave(self):
        def refuse(spec):
            raise HarnessRefused("the harness refused the run: the switch is pulled")

        h = Harness(FakeFoundry(), with_store=True)
        h.s.harness = SimpleNamespace(records=[SimpleNamespace(outcome="refused", reason="switch")], budget=SimpleNamespace(tool_calls=17), ensure=refuse, close=lambda: None)
        h.go()
        record = self.record(h)
        self.assertEqual((record.end, record.stop, record.max_calls, record.calls), ("refused", "switch", 17, 0))
        self.assertTrue(h.result.held)

    def test_a_second_ai_that_the_harness_did_not_let_run_leaves_the_answer_of_the_first_as_it_was_read(self):
        foundry = FakeFoundry(answer(finding(handles=["r1", "r2"])), tool_calls=self.TOOLS)
        foundry.skeptic_error = HarnessRefused("the harness refused the run: the switch is pulled")
        h = self.run_one(foundry)
        record = self.record(h)
        self.assertEqual((record.end, record.answered, len(record.findings), record.examined), ("refused", True, 1, ("the biggest costs", "a group of look-alike resources")))
        self.assertIn("the Skeptic was not let run", record.note)
        self.assertEqual(h.result.cases, 0, "no case was opened from findings that nobody judged")

    def test_the_marks_of_people_that_could_not_be_read_are_a_failed_investigation_that_says_why(self):
        h = Harness(FakeFoundry(), with_store=True)
        h.store.do_not_touch = lambda: (_ for _ in ()).throw(StoreError("down", 503))
        h.go()
        record = self.record(h)
        self.assertEqual((record.end, record.calls, record.tokens), ("failed", 0, 0))
        self.assertIn("the marks of people", record.note)

    def test_an_investigation_that_is_switched_off_or_has_no_store_keeps_no_record(self):
        off = Harness(FakeFoundry(), settings=make_settings(investigate=False), with_store=True)
        off.go()
        self.assertEqual((off.store.investigations_recent(), off.result.off), ([], True))
        bare = Harness(FakeFoundry(), FakeToolbox())
        bare.go()
        self.assertTrue(bare.result.ran)

    def test_each_run_adds_a_record_and_a_second_run_does_not_replace_the_first(self):
        h = self.run_one()
        h.s.history.run_id = "s" * 32
        h.s.clock = lambda: NOW.replace(day=NOW.day + 1)
        h.go()
        self.assertEqual([r.run_id for r in h.store.investigations_recent()], ["s" * 32, "r" * 32])


class AStoreThatFailsNeverFailsTheInvestigation(unittest.TestCase):
    def go(self, store):
        h = Harness(FakeFoundry(answer(finding(handles=["r1", "r2"]))), extras=loop_for(fixed_clock, store))
        h.go()
        return h

    def test_a_store_that_cannot_write_the_record_is_a_line_in_the_log_and_the_run_goes_on(self):
        class Down(MemoryStore):
            def investigation_put(self, record):
                raise StoreError("the table service is down", 503)

        with LogCapture() as capture:
            h = self.go(Down(clock=fixed_clock))
        self.assertTrue(h.result.ran)
        self.assertEqual((h.result.cases, h.result.kept), (2, 1))
        self.assertTrue(any("the record of the investigation could not be kept (StoreError)" in m for m in capture.messages()), capture.messages())

    def test_a_store_that_has_no_such_call_and_a_record_that_cannot_be_made_are_the_same(self):
        class Old(MemoryStore):
            investigation_put = None

        h = self.go(Old(clock=fixed_clock))
        self.assertEqual((h.result.ran, h.result.cases), (True, 2))
        with LogCapture() as capture:
            original = activity.record_of
            activity.record_of = lambda *a, **k: 1 / 0
            try:
                again = self.go(MemoryStore(clock=fixed_clock))
            finally:
                activity.record_of = original
        self.assertEqual((again.result.ran, again.result.cases), (True, 2))
        self.assertTrue(any("ZeroDivisionError" in m for m in capture.messages()))

    def test_the_line_in_the_log_holds_the_kind_of_the_fault_and_never_its_text(self):
        class Down(MemoryStore):
            def investigation_put(self, record):
                raise StoreError("SECRET-TEXT-OF-THE-SERVICE", 503)

        with LogCapture() as capture:
            self.go(Down(clock=fixed_clock))
        self.assertFalse(any("SECRET-TEXT" in m for m in capture.messages()))


if __name__ == "__main__":
    unittest.main()
