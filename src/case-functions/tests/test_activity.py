"""The record of an investigation: what the tools touched, the cost by kind and the share that they looked at, the words of how it ended, the AI's own text with no id and no name in it, the size,
and the writer at the end of the investigation, which never fails the Watch (docs/proposals/23-what-the-ai-looked-at.md).

Every kind of resource here is invented (contoso.example/...), and every number of the coverage is worked out by hand in the test that checks it.
"""
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

from support import NOW, RG, SUBSCRIPTION, LogCapture, fixed_clock
from test_investigate import FakeFoundry, FakeToolbox, Harness, answer, finding, loop_for, make_settings, metrics, resource

from cases import activity, investigate, roles
from cases.detectors import Context
from cases.foundry import AgentRun, FoundryError
from cases.harness import HarnessRefused
from cases.memory_store import MemoryStore, stamp
from cases.models import INVESTIGATION_ENDS, InvestigationRecord, StoreError
from cases.store import MAX_DATA
from cases.toolbox import Resource

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

    def touched(self, *log):
        return activity.touched(toolbox_of(list(log), *self.WORLD))

    def test_a_kind_is_touched_by_the_tool_that_names_it_or_one_of_its_resources_and_the_record_says_how(self):
        found = self.touched(call("list_resources", type=WIDGETS), call("measure", type=GADGETS, metric="MetricA"), call("describe", handle="r20"),
                             call("metric_split", handle="r10", metric="MetricA", dimension="Dim"), call("data_volume", handle="r1"))
        self.assertEqual(found, {WIDGETS: "ld", GADGETS: "ms", GIZMOS: "d"}, "the letters come in the order listed, measured, described, split")
        self.assertEqual([activity.WORDS[letter] for letter in "lmds"], ["listed", "measured", "described", "split"])

    def test_a_measurement_of_handles_touches_the_kind_of_each_handle_and_a_cost_read_touches_a_kind_only_when_it_names_one(self):
        found = self.touched(call("metric_summary", handles=["r1", "r10", "r99"], metric="MetricA"), call("cost_lines", type=GIZMOS), call("cost_lines", service="Some Service"),
                             call("cost_history", handle="r2"))
        self.assertEqual(found, {WIDGETS: "lm", GADGETS: "m", GIZMOS: "l"})

    def test_a_tool_that_shows_a_list_touches_no_kind_and_neither_does_a_call_that_failed_or_that_names_nothing_that_exists(self):
        found = self.touched(call("estate_overview"), call("metric_names", type=WIDGETS), call("advisor_items"), call("paid_features"), call("commitments"), call("recall_lessons", type=WIDGETS),
                             call("recall_open_questions"), call("list_resources", ok=False, type=WIDGETS), call("describe", handle="r99"), call("list_resources", type="Not A Type!"),
                             call("list_resources", type=["microsoft.compute/disks"]), {"name": "describe", "arguments": {"truncated": True}, "ok": True}, {"name": "describe", "ok": True},
                             call("a_tool_that_is_not_there", type=WIDGETS), "not a call")
        self.assertEqual(found, {})

    def test_a_toolbox_that_shows_nothing_touched_nothing(self):
        self.assertEqual(activity.touched(None), {})
        self.assertEqual(activity.touched(SimpleNamespace()), {})


class TheCostByKind(unittest.TestCase):
    """The cost of the run, by hand: 600 + 50 in widgets, 300 in gadgets, 40 + 10 in no kind, and a credit of 5 in gizmos."""

    def costs(self):
        return {"1": context({rid(WIDGETS, 1): 600.0, rid(WIDGETS, 2): 50.0, rid(GADGETS, 3): 300.0, "": 40.0, f"/subscriptions/{SUBSCRIPTION}": 10.0, rid(GIZMOS, 4): -5.0}),
                "2": context({rid(WIDGETS, 9): 77.0}, currency="EUR"), "3": context(None, cost_error=True), "4": context({}, currency=None)}

    def test_it_adds_the_lines_of_the_subscriptions_that_were_read_in_dollars_by_kind_and_leaves_out_a_credit(self):
        kinds, read = activity.costs_by_kind(self.costs())
        self.assertEqual(kinds, {WIDGETS: 650.0, GADGETS: 300.0, "other": 50.0})
        self.assertEqual(read, 2, "the one with lines in dollars and the one that was read and has no line; euros and a read that failed are not counted")

    def test_a_kind_that_has_no_shape_of_a_kind_is_other(self):
        long = f"{RG}/g/providers/Contoso.Example/{'a' * 48}/n1/{'b' * 48}/n2"
        kinds, _ = activity.costs_by_kind({"1": context({long: 3.0, f"{RG}/g/providers/Contoso.Example/{'x' * 90}/n": 4.0})})
        self.assertEqual(kinds, {"other": 7.0}, "one is longer than a kind of resource is and the other has a part that a kind of resource has not")

    def test_the_record_says_how_much_of_the_cost_sits_in_the_kinds_that_the_tools_touched(self):
        """Touched: widgets and gizmos. 650 of the 1,000 that was read is in widgets, and gizmos has no cost above nothing, so 65.0 percent, and two kinds."""
        h = Harness(FakeFoundry(answer(finding()), tool_calls=(("list_resources", {"type": WIDGETS}), ("describe", {"handle": "r20"}))),
                    FakeToolbox([member("r20", GIZMOS)], {"r20": metrics(MetricA=0)}), with_store=True)
        h.contexts = self.costs()
        h.s.settings = replace(h.s.settings, subscriptions=("1", "2", "3", "4"))
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual((record.cost_total, record.cost_looked, record.looked), (1000.0, 650.0, 2))
        self.assertEqual(round(100 * record.cost_looked / record.cost_total, 1), 65.0)
        self.assertEqual([list(k) for k in record.kinds], [[WIDGETS, 650.0, "l"], [GADGETS, 300.0, ""], ["other", 50.0, ""]], "the dearest first, each with what the tools did to it")
        self.assertEqual((record.subs, record.subs_costed), (4, 2))

    def test_a_run_whose_cost_could_not_be_read_in_dollars_has_no_total_and_says_so_and_does_not_say_zero(self):
        h = Harness(FakeFoundry(answer(finding())), FakeToolbox(), with_store=True)
        h.contexts = {"1": context(None, cost_error=True), "2": context({rid(WIDGETS, 1): 5.0}, currency="EUR")}
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual((record.cost_total, record.cost_looked, record.kinds, record.subs_costed), (None, 0.0, (), 0))

    def test_only_the_dearest_kinds_are_kept_and_the_total_still_counts_all_of_them(self):
        costs = {rid(f"contoso.example/kind{n:02d}", n): float(n) for n in range(1, 61)}
        h = Harness(FakeFoundry(answer(finding())), FakeToolbox(), with_store=True)
        h.contexts = {"1": context(costs)}
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual(len(record.kinds), activity.MAX_KINDS)
        self.assertEqual([k[0] for k in record.kinds[:2]], ["contoso.example/kind60", "contoso.example/kind59"])
        self.assertEqual(record.cost_total, float(sum(range(1, 61))))


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

    def test_a_kept_finding_holds_what_the_page_shows(self):
        f = self.made(items=[object()] * 3, verdict=roles.SkepticAnswer("disagree", ("one", "two", "three"), "A sentence."), fates={"request": 2, "nothing": 1}, guarded=1, recent=2)
        self.assertEqual(activity.entry_of(f, frozenset()), {"n": 2, "basis": "no-usage", "proposal": "delete", "sure": 0.85, "resources": 3, "usd": 123.45, "says": "Nothing used these in the window.",
                                                              "verdict": "disagree", "doubts": ["one", "two"], "kept": True, "left": {"guarded": 1, "recent": 2},
                                                              "fates": {"request": 2, "nothing": 1}})

    def test_a_dropped_finding_says_what_the_ai_listed_and_what_became_of_it_and_a_finding_that_could_not_be_read_says_why(self):
        dropped = activity.entry_of(self.made(reason="no resource of it is left: 4 that no tool showed", unknown=4, covered_usd=None), frozenset())
        self.assertEqual((dropped["kept"], dropped["resources"], dropped["left"], "verdict" in dropped, "usd" in dropped), (False, 4, {"unknown": 4}, False, False))
        unreadable = activity.entry_of(investigate.Finding(1, reason="its confidence is not a number"), frozenset())
        self.assertEqual((unreadable["kept"], unreadable["note"], "basis" in unreadable), (False, "its confidence is not a number", False))

    def test_the_note_of_code_is_kept_for_a_finding_that_code_changed(self):
        entry_ = activity.entry_of(self.made(note="others share this kind of resource, so this asks for a look and not for a deletion", items=[object()]), frozenset())
        self.assertEqual(entry_["note"], "others share this kind of resource, so this asks for a look and not for a deletion")


def worst(char: str = "x"):
    """An investigation at its limits: twelve phrases of a hundred characters, eight findings with every text at its longest, forty kinds of cost, every kind touched in every way. `char` is what
    the texts are made of: a character that json writes six characters long makes the same record or a smaller one."""
    kinds = [f"contoso.example/kind-of-resource-{n:02d}" for n in range(60)]
    log = [call(name, type=kind) for kind in kinds for name in ("list_resources", "measure", "describe", "metric_split")]
    toolbox = toolbox_of(log)
    findings = []
    for n in range(1, 9):
        verdict = roles.SkepticAnswer("unsure", tuple(char * 200 for _ in range(3)), "s")
        findings.append(investigate.Finding(n, basis="commitment-misfit", proposal="investigate", confidence=0.85, summary=char * 300, claimed=60, covered_usd=123456.78, items=[object()] * 60,
                                            verdict=verdict, note=char * 300, unknown=60, unproven=60, repeated=60, guarded=60, recent=60, capped=60,
                                            fates={"request": 60, "person": 60, "dropped": 60, "nothing": 60, "automation": 60, "unchecked": 60, "impact": 60, "rules": 60}))
    out = investigate.Investigation(ran=True, tokens=999999, tool_calls=40, seconds=600, toolbox=toolbox, examined=[char * 100] * 12, findings=findings, note=char * 300)
    out.answer = AgentRun(text="", calls=[{"name": "t", "ok": True}])
    costs = {rid(kind, n): 123456.78 + n for n, kind in enumerate(kinds)}
    return SimpleNamespace(contexts={SUBSCRIPTION: context(costs)}), out


class TheSizeOfARecord(unittest.TestCase):
    def s(self):
        return SimpleNamespace(settings=make_settings(subscriptions=(SUBSCRIPTION,)), history=SimpleNamespace(run_id="r" * 32))

    def test_a_record_at_its_limits_is_far_below_what_a_table_property_may_hold_and_below_its_own_cap(self):
        for char in ("x", '"', "\u00e9", "\u4e2d"):
            with self.subTest(char=char):
                world, out = worst(char)
                record = activity.record_of(self.s(), out, world.contexts, trigger="control", at=stamp(NOW), seconds=600)
                size = len(record.to_json())
                self.assertEqual((len(record.examined), len(record.findings), len(record.kinds)), (12, 8, activity.MAX_KINDS))
                self.assertLessEqual(size, activity.MAX_RECORD, f"{size} characters")
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

    def test_the_coverage_of_a_run_is_worked_out_from_the_tools_that_it_called_and_the_cost_that_it_read(self):
        """The five things cost 10, 20, 30, 40 and 50, and a gadget 50: 200 in all, and the tools touched the things (listed, measured and, for r1, described): 150 of 200."""
        record = self.record(self.run_one())
        self.assertEqual((record.cost_total, record.cost_looked, record.looked), (200.0, 150.0, 1))
        self.assertEqual([list(k) for k in record.kinds], [[THINGS, 150.0, "lmd"], [GADGETS, 50.0, ""]])

    def test_a_finding_keeps_its_sentence_the_verdict_of_the_second_ai_what_it_covers_and_what_became_of_its_resources(self):
        record = self.record(self.run_one())
        (found,) = record.findings
        self.assertEqual((found["n"], found["basis"], found["proposal"], found["sure"], found["resources"], found["kept"]), (1, "no-usage", "delete", 0.9, 2, True))
        self.assertEqual((found["says"], found["verdict"], found["usd"]), ("Nothing used these in the window.", "agree", 30.0))
        self.assertEqual(found["fates"], {"request": 2}, "a request was made for each of the two")

    def test_a_dropped_finding_is_kept_with_why_and_its_resources_are_the_ones_that_the_ai_listed(self):
        h = self.run_one(FakeFoundry(answer(finding(handles=["r1", "r2"]), finding(handles=["r98", "r99", "r97"], summary="Gone."))))
        kept, dropped = self.record(h).findings
        self.assertEqual((kept["kept"], dropped["kept"], dropped["resources"], dropped["left"], dropped.get("fates")), (True, False, 3, {"unknown": 3}, None))

    def test_a_request_that_was_held_back_is_counted_with_the_reason_that_held_it(self):
        from test_missing_data import AnAutomationsResourceIsHeldBack as Held
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

    def test_the_trigger_is_what_started_the_run_and_empty_when_nothing_says(self):
        self.assertEqual(self.record(self.run_one(trigger="control")).trigger, "control")
        self.assertEqual(self.record(self.run_one(trigger="")).trigger, "")

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
