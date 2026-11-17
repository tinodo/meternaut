"""The beats of an investigation (cases/beats.py, docs/proposals/25-beats.md): the plan that code makes from what the kinds of resource cost, the pictures that code reads for a beat before the
Investigator starts, what a beat is told of the beats before it, and the investigation that runs the beats one after the other on one toolbox. Every kind in this file is invented."""
import json
import re
import unittest
from types import SimpleNamespace
from unittest import mock

from support import APP_ROOT, RG, SUBSCRIPTION, Ticker

import test_investigate as ti
from cases import activity, agents, beats, investigate
from cases import toolbox as tb
from cases.detectors import Context
from cases.foundry import AgentRun, FoundryError
from cases.harness import HarnessRefused
from cases.store import MAX_DATA

# An invented estate. The cost of the last 30 days of each kind, and of the lines that no resource owns; 11,000 in all, so that 95 percent is 10,450.
ESTATE = {"contoso.compute/rigs": 3000.0, "contoso.compute/racks": 1500.0, "fabrikam.store/vaults": 2000.0, "fabrikam.store/lockers": 800.0, "northwind.net/links": 1200.0,
          "northwind.net/hubs": 500.0, "adatum.data/lakes": 400.0, "tailspin.misc/things": 300.0, "tailspin.misc/bits": 150.0, "woodgrove.tiny/dots": 100.0,
          "litware.a/x": 30.0, "litware.b/y": 20.0}
UNOWNED = 1000.0


def kinds_of(plan):
    return [list(beat.kinds) for beat in plan]


class TheFocusThatCodeChooses(unittest.TestCase):
    def test_the_plan_of_a_hand_computed_estate(self):
        # Ranked: rigs 3000, vaults 2000, racks 1500, links 1200, the lines of no resource 1000, lockers 800, hubs 500, lakes 400, things 300 (10,700 in all: the first to pass 10,450), then bits, dots, x, y.
        plan = beats.plan(ESTATE, UNOWNED, 6)
        self.assertEqual(kinds_of(plan), [["contoso.compute/rigs", "contoso.compute/racks"], ["fabrikam.store/vaults", "fabrikam.store/lockers"], ["northwind.net/links", "northwind.net/hubs"], [],
                                          ["adatum.data/lakes"], ["tailspin.misc/things", "tailspin.misc/bits", "woodgrove.tiny/dots", "litware.a/x", "litware.b/y"]])
        self.assertEqual([beat.billing for beat in plan], [False, False, False, True, False, False])
        self.assertEqual([(beat.number, beat.of) for beat in plan], [(n, 6) for n in range(1, 7)])
        self.assertEqual([beat.rest for beat in plan], [0] * 6)

    def test_a_kind_that_belongs_to_the_same_service_as_a_dearer_one_goes_with_it_and_a_beat_holds_three_kinds_at_most(self):
        costs = {f"contoso.compute/k{n}": 100.0 - n for n in range(5)} | {"fabrikam.store/s": 50.0}
        plan = beats.plan(costs, 0.0, 6)
        self.assertEqual(kinds_of(plan), [["contoso.compute/k0", "contoso.compute/k1", "contoso.compute/k2"], ["contoso.compute/k3", "contoso.compute/k4"], ["fabrikam.store/s"]])
        self.assertEqual([beat.number for beat in plan], [1, 2, 3])

    def test_the_kinds_below_the_floor_are_left_to_the_last_beat_when_the_plan_has_room_for_one(self):
        plan = beats.plan(ESTATE, UNOWNED, 8)
        self.assertEqual(kinds_of(plan)[5:], [["tailspin.misc/things"], ["tailspin.misc/bits", "woodgrove.tiny/dots", "litware.a/x", "litware.b/y"]], "the last beat holds what is left, dearest first")
        self.assertEqual(len(plan), 7)
        self.assertEqual({beat.of for beat in plan}, {7})

    def test_a_plan_never_has_more_beats_than_it_may_and_the_last_one_takes_what_does_not_fit(self):
        plan = beats.plan(ESTATE, UNOWNED, 3)
        self.assertEqual(kinds_of(plan)[:2], [["contoso.compute/rigs", "contoso.compute/racks"], ["fabrikam.store/vaults", "fabrikam.store/lockers"]])
        last = plan[2]
        self.assertEqual(len(plan), 3)
        self.assertEqual(last.kinds, ("northwind.net/links", "northwind.net/hubs", "adatum.data/lakes", "tailspin.misc/things", "tailspin.misc/bits", "woodgrove.tiny/dots", "litware.a/x", "litware.b/y"))
        self.assertTrue(last.billing, "the lines that no resource owns are in what it holds")
        one = beats.plan(ESTATE, UNOWNED, 1)
        self.assertEqual((len(one), one[0].kinds[:2], one[0].billing), (1, ("contoso.compute/rigs", "fabrikam.store/vaults"), True))

    def test_a_catch_all_names_the_dearest_few_and_counts_the_others(self):
        costs = {f"contoso.thing{n:02d}/kind": 100.0 - n for n in range(20)}
        (only,) = beats.plan(costs, 0.0, 1)
        self.assertEqual(len(only.kinds), beats.CATCH_ALL_KINDS)
        self.assertEqual(only.kinds[0], "contoso.thing00/kind")
        self.assertEqual(only.rest, 20 - beats.CATCH_ALL_KINDS)

    def test_the_lines_that_no_resource_owns_are_a_beat_of_their_own_when_they_are_all_there_is(self):
        self.assertEqual(beats.plan({}, 40.0, 4), [beats.Beat(1, (), True, 0, 1)])
        self.assertEqual(beats.plan({"contoso.compute/rigs": 10.0}, 0.0, 4)[0].billing, False)

    def test_there_is_no_plan_when_nothing_is_known_to_cost_anything(self):
        for costs, unowned in (({}, 0.0), ({"contoso.compute/rigs": 0.0}, 0.0), ({"contoso.compute/rigs": -5.0}, -1.0)):
            self.assertEqual(beats.plan(costs, unowned, 6), [])
        self.assertEqual(beats.plan(ESTATE, UNOWNED, 0), [])

    def test_the_order_does_not_depend_on_the_order_of_what_it_is_given_and_a_tie_goes_by_name(self):
        first = beats.plan(dict(reversed(list(ESTATE.items()))), UNOWNED, 6)
        self.assertEqual(first, beats.plan(ESTATE, UNOWNED, 6))
        tied = beats.plan({"b.x/y": 10.0, "a.x/y": 10.0, "c.x/y": 10.0}, 0.0, 6)
        self.assertEqual(kinds_of(tied), [["a.x/y"], ["b.x/y"], ["c.x/y"]])

    def test_one_dear_kind_is_a_beat_of_its_own_and_the_cheap_rest_waits_in_the_last_beat(self):
        plan = beats.plan({"contoso.compute/rigs": 9000.0, "tailspin.misc/a": 10.0, "tailspin.misc/b": 5.0}, 0.0, 4)
        self.assertEqual(kinds_of(plan), [["contoso.compute/rigs"], ["tailspin.misc/a", "tailspin.misc/b"]])

    def test_no_kind_of_resource_is_written_in_the_module(self):
        source = (APP_ROOT / "cases" / "beats.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"""["'][a-z0-9]+\.[a-z0-9]+/[a-z0-9]+["']""", source), [], "a kind comes from the bill, by dollars; the code names none")

    def test_the_spend_is_read_from_the_cost_lines_that_the_watch_has_by_kind_and_the_lines_of_no_resource(self):
        a = f"{RG}/rg-a/providers/Contoso.Compute/rigs/one"
        b = f"{RG}/rg-a/providers/Fabrikam.Store/vaults/two"
        contexts = {"s1": Context(costs={a: 30.0, b: 20.0, "": 7.0}, currency="USD"), "s2": Context(costs={a.replace("one", "three"): 5.0, "": 3.0}, currency="USD"),
                    "s3": Context(costs={a: 999.0, "": 999.0}, currency="EUR"), "s4": Context(costs=None)}
        kinds, unowned = beats.spend(contexts)
        self.assertEqual((kinds, unowned), ({"contoso.compute/rigs": 35.0, "fabrikam.store/vaults": 20.0}, 10.0), "a subscription whose cost is not in dollars or was not read counts for nothing")


class TheTypedWordsOfABeat(unittest.TestCase):
    def test_a_beat_with_no_focus_is_open(self):
        self.assertTrue(beats.Beat().open)
        self.assertFalse(beats.Beat(1, ("contoso.compute/rigs",)).open)
        self.assertFalse(beats.Beat(1, (), True).open)


class WhatCodeReadsForABeatBeforeTheInvestigatorStarts(unittest.TestCase):
    def test_the_dearest_resource_of_each_kind_comes_first_then_the_next_dearest_of_each_and_one_picture_is_read_of_them(self):
        by_kind = {"contoso.compute/rigs": [resource_of(n, "contoso.compute/rigs") for n in (1, 2, 3, 4)], "fabrikam.store/vaults": [resource_of(n, "fabrikam.store/vaults") for n in (5, 6)],
                   "northwind.net/links": [resource_of(7, "northwind.net/links")]}
        box = SeedToolbox(by_kind)
        found = beats.seed(box.call, beats.Beat(1, tuple(by_kind), False, 0, 1))
        self.assertEqual(found.handles, ["r1", "r5", "r7", "r2", "r6"], "the dearest of each kind, then the second dearest of each, five in all")
        self.assertEqual(found.counts, {"contoso.compute/rigs": 4, "fabrikam.store/vaults": 2, "northwind.net/links": 1})
        self.assertEqual([entry["name"] for entry in box.log], ["list_resources"] * 3 + ["profile"], "three listings and one picture: the reads that the Investigator would have made")
        self.assertEqual(box.log[-1]["arguments"], {"handles": ["r1", "r5", "r7", "r2", "r6"], "days": None, "grain": None})
        self.assertEqual([p["handle"] for p in found.pictures["profiles"]], found.handles)
        self.assertEqual(found.failed, 0)

    def test_a_read_that_gives_no_answer_is_counted_and_the_beat_goes_on_with_what_it_has(self):
        box = SeedToolbox({"contoso.compute/rigs": [resource_of(1, "contoso.compute/rigs")]}, answers={"list_resources": '{"error":"unavailable"}'})
        found = beats.seed(box.call, beats.Beat(1, ("contoso.compute/rigs",), False, 0, 1))
        self.assertEqual((found.handles, found.pictures, found.failed, found.counts), ([], None, 1, {}))
        box = SeedToolbox({"contoso.compute/rigs": [resource_of(1, "contoso.compute/rigs")]}, answers={"profile": "not json"})
        found = beats.seed(box.call, beats.Beat(1, ("contoso.compute/rigs",), False, 0, 1))
        self.assertEqual((found.handles, found.pictures, found.failed), (["r1"], None, 1))

    def test_a_beat_of_the_lines_that_no_resource_owns_reads_nothing(self):
        box = SeedToolbox({})
        found = beats.seed(box.call, beats.Beat(1, (), True, 0, 1))
        self.assertEqual((box.log, found.handles, found.pictures), ([], [], None))

    def test_a_beat_seeds_the_first_five_of_its_kinds_and_never_more_than_five_resources(self):
        kinds = [f"contoso.thing{n}/kind" for n in range(8)]
        box = SeedToolbox({kind: [resource_of(n + 1, kind)] for n, kind in enumerate(kinds)})
        found = beats.seed(box.call, beats.Beat(1, tuple(kinds), False, 3, 1))
        self.assertEqual((len(found.handles), len([e for e in box.log if e["name"] == "list_resources"])), (5, 5))
        self.assertLessEqual(len(box.log), beats.SEED_CALLS)


class WhatABeatIsToldOfTheBeatsBeforeIt(unittest.TestCase):
    def test_the_input_of_an_open_beat_is_the_budget_alone_as_it_always_was(self):
        self.assertEqual(beats.beat_input(beats.Beat(), 30, None, []), '{"budget":{"toolCalls":30}}')

    def test_the_input_of_a_beat_holds_its_focus_its_counts_its_pictures_and_what_the_beats_before_it_concluded(self):
        beat = beats.Beat(2, ("contoso.compute/rigs",), True, 4, 3)
        seeded = beats.Seed({"contoso.compute/rigs": 2}, ["r1"], {"profiles": [{"handle": "r1"}]})
        earlier = [{"beat": 1, "kinds": ["fabrikam.store/vaults"], "findings": [], "examined": ["a phrase"]}]
        body = json.loads(beats.beat_input(beat, 8, seeded, earlier))
        self.assertEqual(body, {"budget": {"toolCalls": 8}, "beat": {"number": 2, "of": 3, "focus": ["contoso.compute/rigs"], "billingOnly": True, "moreKinds": 4},
                                "counts": {"contoso.compute/rigs": 2}, "pictures": {"profiles": [{"handle": "r1"}]}, "earlier": earlier})

    def test_a_beat_that_gave_no_answer_is_carried_as_one_that_did_not_conclude_so_that_the_next_one_knows_its_kinds_were_not_judged(self):
        done = beats.Result(beats.Beat(1, ("contoso.compute/rigs",)), end="answered", examined=["a phrase"], lines=[{"basis": "no-usage", "proposal": "delete", "handles": ["r1"]}])
        lost = beats.Result(beats.Beat(2, ("fabrikam.store/vaults",)), end="failed")
        self.assertEqual(beats.carry([done, lost]), [{"beat": 1, "kinds": ["contoso.compute/rigs"], "findings": done.lines, "examined": ["a phrase"]},
                                                     {"beat": 2, "kinds": ["fabrikam.store/vaults"], "concluded": False}])

    def test_what_is_carried_is_cut_to_its_size_with_the_oldest_phrases_first(self):
        results = [beats.Result(beats.Beat(n, (f"contoso.thing{n}/kind",)), end="answered", examined=[f"phrase {n}-{m} " + "x" * 90 for m in range(6)]) for n in range(1, 9)]
        lines = beats.carry(results)
        self.assertLessEqual(len(json.dumps(lines, separators=(",", ":"))), beats.CARRY_CHARS)
        self.assertEqual([line["beat"] for line in lines], list(range(1, 9)), "every beat is still named")
        self.assertLess(len(lines[0].get("examined", [])), len(lines[-1].get("examined", [])), "the oldest lose their phrases first")
        self.assertEqual(len(lines[-1]["examined"]), 6, "and the newest keep all of theirs")

    def test_the_words_of_the_agent_that_are_carried_pass_through_nothing_but_what_the_investigation_hands_them(self):
        lines = beats.carry([beats.Result(beats.Beat(1, ("contoso.compute/rigs",)), end="answered", examined=["x"] * 20, lines=[{"handles": ["r1"]}] * 20)])
        self.assertEqual((len(lines[0]["examined"]), len(lines[0]["findings"])), (beats.CARRY_ITEMS, beats.CARRY_ITEMS))


# -- the investigation of beats, with the fakes of test_investigate.py (the seeds above are read from the toolbox below) -----------------------------------------------------

KINDS = {"contoso.compute/rigs": 3000.0, "fabrikam.store/vaults": 2000.0, "northwind.net/links": 1200.0}


def resource_of(number: int, kind: str, usd: float = 100.0):
    provider, _, name = kind.partition("/")
    return ti.resource(number, resource_id=f"{RG}/rg-app/providers/{provider.title()}/{name}/item-{number}", resource_type=kind, name=f"item-{number}", cost_usd_30d=usd)


class SeedToolbox(ti.FakeToolbox):
    """A toolbox that shows the handles of its kinds and answers the two reads that code makes for a beat: the listing of a kind and the picture of some resources. `answers` replaces an answer by a text.
    It keeps the limit of the real one: the calls beyond MAX_CALLS and what a run has added (`extra_calls`) answer limit and read nothing."""

    def __init__(self, by_kind, answers=None, **more):
        resources = [r for found in by_kind.values() for r in found]
        super().__init__(resources, evidence={r.handle: ti.metrics(MetricA=0) for r in resources}, **more)
        self.by_kind, self.answers, self.extra_calls, self.limited = by_kind, answers or {}, 0, 0

    def call(self, name, arguments):
        self.log.append({"name": name, "arguments": arguments, "ok": True, "chars": 2})
        if len(self.log) > tb.MAX_CALLS + self.extra_calls:
            self.limited += 1
            return '{"error":"limit"}'
        if name in self.answers:
            return self.answers[name]
        if name == "list_resources":
            found = self.by_kind.get(arguments["type"], [])
            return json.dumps({"type": arguments["type"], "total": len(found), "cols": ["handle", "usd30d"], "rows": [[r.handle, r.cost_usd_30d] for r in found[: arguments["limit"]]]})
        if name == "profile":
            return json.dumps({"days": 30, "profiles": [{"handle": h, "type": self.handles[h].resource_type} for h in arguments["handles"]]})
        return "{}"


class BeatFoundry(ti.FakeFoundry):
    """Plays the Investigator once for each beat, from a list of scripts, and the Skeptic as FakeFoundry does. A script is {"text", "tokens", "calls": [(tool, arguments)], and perhaps "error", "out_of_tokens"}.
    It keeps the agents as the project stores them and asks the brake before a request, as the real client does, so that it can stand under a harness."""

    def __init__(self, beats_=(), **more):
        super().__init__(**more)
        self.beats, self.stored = list(beats_), {}

    def ensure_agent(self, spec):
        reference = super().ensure_agent(spec)
        from cases import foundry
        self.stored[spec.name] = {"name": spec.name, "version": reference.partition(":")[2], "definition": foundry.definition_of(spec)}
        return reference

    def read_agent(self, name):
        return self.stored.get(name)

    def run(self, agent, user_input, handler=None, *, max_calls=20, max_seconds=None, stop=None, max_tokens=None):
        if stop is not None:
            why = stop(AgentRun(text=""))
            if why:
                raise FoundryError(f"Foundry run stopped by the harness: {why}")
        if not agent.startswith(agents.INVESTIGATOR_NAME):
            return super().run(agent, user_input, handler, max_calls=max_calls, max_seconds=max_seconds)
        self.runs.append({"agent": agent, "input": user_input, "max_calls": max_calls, "max_seconds": max_seconds, "max_tokens": max_tokens, "handler": handler})
        if self.after_run:
            self.after_run(agent)
        script = self.beats.pop(0)
        if script.get("error"):
            raise script["error"]
        calls = []
        for name, arguments in script["calls"]:
            calls.append({"name": name, "arguments": arguments, "ok": True, "chars": len(handler(name, arguments))})
        return AgentRun(text=script["text"], calls=calls, input_tokens=script["tokens"][0], output_tokens=script["tokens"][1], responses=len(calls) + 1,
                        out_of_tokens=bool(script.get("out_of_tokens")))

    def investigator_runs(self):
        return [run for run in self.runs if run["agent"].startswith(agents.INVESTIGATOR_NAME)]

    def skeptic_runs(self):
        return [run for run in self.runs if run["agent"].startswith(agents.SKEPTIC_NAME)]


def script(*raw, examined=("looked at the focus",), tokens=(40_000, 4_000), calls=(("tool_one", {}),), **more):
    return {"text": ti.answer(*raw, examined=examined), "tokens": tokens, "calls": list(calls), **more}


def pooled(by_kind=None, per_kind=2):
    """The invented estate: `per_kind` resources of each kind with handles in order (r1, r2 for the first kind, and so on), and the cost lines of the Watch for them."""
    by_kind, number, found, costs = by_kind or KINDS, 0, {}, {}
    for kind, usd in by_kind.items():
        for _ in range(per_kind):
            number += 1
            made = resource_of(number, kind, usd / per_kind)
            found.setdefault(kind, []).append(made)
            costs[made.resource_id.lower()] = usd / per_kind
    return found, costs


def rig(beats_, *, by_kind=None, per_kind=2, skeptic=None, foundry=None, **settings):
    found, costs = pooled(by_kind, per_kind)
    values = dict(investigate_beats=3, investigate_max_seconds=1080)
    values.update(settings)
    h = ti.Harness(foundry or BeatFoundry(beats_, skeptic=skeptic), SeedToolbox(found), ti.make_settings(**values), with_store=True)
    h.contexts = {SUBSCRIPTION: Context(locks=[], recent=set(), managed_groups=set(), costs=costs, currency="USD")}
    return h


def one(handle: str, **more):
    return ti.finding(handles=[handle], **more)


class TheInvestigationInBeats(unittest.TestCase):
    def test_three_beats_with_different_focus_each_get_their_own_budget_pictures_and_session_on_one_toolbox(self):
        h = rig([script(one("r1"), examined=("rigs: looked at",)), script(one("r3"), examined=("vaults: looked at",)), script(one("r5"), examined=("links: looked at",))])
        result = h.go()
        runs = h.foundry.investigator_runs()
        inputs = [json.loads(run["input"]) for run in runs]
        self.assertEqual((result.state, len(runs), len(h.foundry.skeptic_runs())), ("ran", 3, 1), "three sessions of the Investigator and one of the Skeptic for what they found")
        self.assertEqual([i["beat"] for i in inputs], [{"number": n, "of": 3, "focus": [kind]} for n, kind in enumerate(KINDS, 1)])
        self.assertEqual([i["budget"] for i in inputs], [{"toolCalls": 8}] * 3)
        self.assertEqual([i["counts"] for i in inputs], [{kind: 2} for kind in KINDS])
        self.assertEqual([[p["handle"] for p in i["pictures"]["profiles"]] for i in inputs], [["r1", "r2"], ["r3", "r4"], ["r5", "r6"]])
        self.assertEqual([(run["max_calls"], run["max_tokens"]) for run in runs], [(8, 100_000)] * 3)
        self.assertTrue(all(0 < run["max_seconds"] <= 160 for run in runs), [run["max_seconds"] for run in runs])
        self.assertEqual([entry["name"] for entry in h.toolbox.log], ["list_resources", "profile", "tool_one"] * 3, "what code reads for a beat and the call of the beat are in one log")
        self.assertEqual((result.tool_calls, result.tokens, result.cases), (3, 3 * 44_000 + 600, 3))
        self.assertEqual([e["finding"] for e in h.of("investigation.finding")], [1, 2, 3])
        self.assertEqual([e["beat"] for e in h.of("investigation.finding")], [1, 2, 3])

    def test_the_history_has_one_line_for_each_beat_and_the_start_and_the_end_say_how_many_there_were(self):
        h = rig([script(one("r1")), script(one("r3")), script(one("r5"))])
        h.go()
        (started,), (finished,) = h.of("investigation.started"), h.of("investigation.finished")
        self.assertEqual((started["beats"], started["maxCalls"], finished["beats"], finished["ok"]), (3, 24, 3, True))
        lines = h.of("investigation.beat")
        self.assertEqual([(e["beat"], e["of"], e["kinds"], e["toolCalls"], e["tokens"], e["end"], e["ok"], e["seeded"]) for e in lines],
                         [(n, 3, 1, 1, 44_000, "answered", True, 2) for n in (1, 2, 3)])
        self.assertEqual(sum(e["tokens"] for e in lines) + 600, finished["tokens"])

    def test_a_beat_is_told_what_the_beats_before_it_concluded_as_typed_lines_and_the_first_is_told_nothing(self):
        h = rig([script(one("r1"), examined=("the first beat looked at its kind",)), script(one("r3"), examined=("the second beat looked at its kind",)), script()])
        h.go()
        inputs = [json.loads(run["input"]) for run in h.foundry.investigator_runs()]
        self.assertNotIn("earlier", inputs[0])
        self.assertEqual(inputs[1]["earlier"], [{"beat": 1, "kinds": ["contoso.compute/rigs"], "findings": [{"basis": "no-usage", "proposal": "delete", "handles": ["r1"]}],
                                                  "examined": ["the first beat looked at its kind"]}])
        self.assertEqual([line["beat"] for line in inputs[2]["earlier"]], [1, 2])

    def test_a_resource_is_in_one_finding_only_and_a_later_beats_finding_about_it_loses_it_with_a_word_for_the_history(self):
        both = ti.finding(handles=["r1", "r2"])
        h = rig([script(both), script(ti.finding(handles=["r2", "r3"])), script(one("r1"))])
        result = h.go()
        lines = {e["finding"]: e for e in h.of("investigation.finding")}
        self.assertEqual((lines[2]["repeated"], lines[2]["handles"], lines[2]["kept"]), (1, 1, True))
        self.assertEqual((lines[3]["repeated"], lines[3]["handles"], lines[3]["kept"]), (1, 0, False))
        self.assertEqual(lines[3]["reason"], "no resource of it is left: 1 that an earlier finding has")
        self.assertEqual(result.cases, 3, "r1 and r2 from the first finding, r3 from the second: each resource once")

    def test_a_beat_that_fails_is_a_note_and_the_others_still_count(self):
        h = rig([script(one("r1")), {"error": FoundryError("the project is busy")}, script(one("r5"))])
        result = h.go()
        self.assertEqual((result.ran, result.cases, result.held, len(h.foundry.investigator_runs())), (True, 2, False, 3))
        self.assertTrue([n for n in h.notes if n.startswith("beat 2") and "the project is busy" in n], h.notes)
        lines = h.of("investigation.beat")
        self.assertEqual([(e["beat"], e["ok"], e["end"]) for e in lines], [(1, True, "answered"), (2, False, "failed"), (3, True, "answered")])
        self.assertEqual([r.end for r in result.beats], ["answered", "failed", "answered"])
        self.assertEqual(h.of("investigation.finished")[0]["ok"], True, "one beat that failed is not an investigation that failed")
        inputs = [json.loads(run["input"]) for run in h.foundry.investigator_runs()]
        self.assertEqual(inputs[2]["earlier"][1], {"beat": 2, "kinds": ["fabrikam.store/vaults"], "concluded": False})

    def test_a_beat_with_an_answer_that_cannot_be_read_is_a_note_too(self):
        h = rig([script(one("r1")), {"text": "I think the biggest one is waste.", "tokens": (10, 5), "calls": []}, script(one("r5"))])
        result = h.go()
        self.assertEqual((result.ran, result.cases), (True, 2))
        self.assertTrue([n for n in h.notes if n.startswith("beat 2") and "no answer that could be read" in n], h.notes)

    def test_when_no_beat_gives_an_answer_the_investigation_failed_as_it_does_for_one_session(self):
        h = rig([{"error": FoundryError("the project is busy")}] * 3)
        result = h.go()
        self.assertEqual((result.ran, result.state, result.cases), (False, "failed", 0))
        self.assertTrue(result.note.endswith("(the project is busy)"), result.note)
        self.assertEqual(h.of("investigation.finished")[0]["ok"], False)

    def test_a_refusal_of_the_harness_in_any_beat_holds_the_whole_investigation_and_opens_no_case(self):
        h = rig([script(one("r1")), {"error": HarnessRefused("the harness refused the run: the switch investigation is pulled")}, script(one("r5"))])
        result = h.go()
        self.assertEqual((result.state, result.held, result.cases, len(h.foundry.investigator_runs()), len(h.foundry.skeptic_runs())), ("held", True, 0, 2, 0))
        self.assertEqual(h.store.cases_recent(10), [], "findings that nobody judged open nothing")
        self.assertIn("the investigator gave no answer", result.note)
        self.assertEqual([(e["beat"], e["end"]) for e in h.of("investigation.beat")], [(1, "answered"), (2, "refused")])

    def test_the_tokens_of_the_whole_investigation_stop_the_beats_and_the_beat_that_starts_with_less_gets_what_is_left(self):
        h = rig([script(one("r1"), tokens=(90_000, 10_000)), script(one("r3"), tokens=(90_000, 10_000)), script(one("r5"))], investigate_total_tokens=150_000)
        result = h.go()
        runs = h.foundry.investigator_runs()
        self.assertEqual([run["max_tokens"] for run in runs], [100_000, 50_000], "the second beat has the tokens that are left")
        self.assertEqual((len(runs), result.cases), (2, 2))
        self.assertTrue([n for n in h.notes if "the tokens of the investigation" in n and "2 of 3 beats" in n], h.notes)

    def test_the_seconds_of_the_whole_investigation_stop_the_beats_too_and_the_skeptic_keeps_its_reserve(self):
        ticker = Ticker()
        foundry = BeatFoundry([script(one("r1")), script(one("r3")), script(one("r5"))])
        foundry.after_run = lambda agent: ticker.jump(100) if agent.startswith(agents.INVESTIGATOR_NAME) else None
        h = rig(None, foundry=foundry, investigate_max_seconds=300)
        h.ticker, h.s.monotonic = ticker, ticker
        h.go()
        runs = foundry.investigator_runs()
        self.assertEqual(len(runs), 2, "the third beat had 25 seconds: not enough to start")
        self.assertTrue(100 < runs[1]["max_seconds"] < 126, runs[1]["max_seconds"])
        self.assertTrue([n for n in h.notes if "the time of the investigation" in n and "2 of 3 beats" in n], h.notes)
        self.assertEqual(len(foundry.skeptic_runs()), 1)

    def test_a_beat_may_have_fewer_calls_seconds_and_tokens_than_the_settings_ceiling_gives_it(self):
        h = rig([script(one("r1")), script(), script()], investigate_beat_calls=5, investigate_beat_seconds=40, investigate_beat_tokens=20_000)
        h.go()
        runs = h.foundry.investigator_runs()
        self.assertEqual([(run["max_calls"], run["max_tokens"]) for run in runs], [(5, 20_000)] * 3)
        self.assertTrue(all(run["max_seconds"] <= 40 for run in runs))
        self.assertEqual(json.loads(runs[0]["input"])["budget"], {"toolCalls": 5})

    def test_a_beat_that_used_its_tokens_says_so_and_the_investigation_ends_as_answered(self):
        h = rig([script(one("r1"), out_of_tokens=True), script(), script()])
        result = h.go()
        self.assertEqual([r.end for r in result.beats][0], "tokens")
        self.assertEqual(h.of("investigation.beat")[0]["end"], "tokens")

    def test_without_a_cost_to_rank_by_the_whole_estate_is_one_open_beat_exactly_as_one_session_always_was(self):
        h = ti.Harness(BeatFoundry([script(one("r1"))]), SeedToolbox(pooled()[0]), ti.make_settings(investigate_beats=3), with_store=True)
        result = h.go()
        (run,) = h.foundry.investigator_runs()
        self.assertEqual((run["input"], run["max_calls"], run["max_tokens"], h.toolbox.extra_calls), ('{"budget":{"toolCalls":30}}', 30, None, 0))
        self.assertEqual((result.state, len(result.beats), h.of("investigation.beat")), ("ran", 1, []), "no line for a beat that is the whole investigation")
        self.assertNotIn("beats", h.of("investigation.started")[0])
        self.assertEqual([e["name"] for e in h.toolbox.log], ["tool_one"], "nothing is read by code for an open beat")

    def test_a_beat_that_starts_late_still_has_its_own_allowance_of_calls_on_the_shared_toolbox_which_allows_forty_and_what_is_added(self):
        kinds = {f"contoso.thing{n}/kind": 100.0 for n in range(6)}
        calls = [("tool_one", {"n": k}) for k in range(8)]
        h = rig([script(one(f"r{n}"), calls=calls) for n in range(1, 7)], by_kind=kinds, per_kind=1, investigate_beats=6)
        result = h.go()
        self.assertEqual(len(h.foundry.investigator_runs()), 6)
        self.assertEqual((h.toolbox.limited, len(h.toolbox.log)), (0, 6 * (1 + 1 + 8)), "sixty calls on a toolbox that allows forty: none was answered limit")
        self.assertEqual((result.tool_calls, result.cases), (48, 6))
        self.assertGreater(h.toolbox.extra_calls, 0)
        self.assertGreaterEqual(tb.MAX_CALLS + h.toolbox.extra_calls, len(h.toolbox.log), "the toolbox allows what its beats used")

    def test_the_allowance_of_a_beat_is_made_when_it_starts_from_the_calls_that_were_made_and_never_lowered(self):
        seen = []
        kinds = {f"contoso.thing{n}/kind": 100.0 for n in range(6)}
        calls = [("tool_one", {"n": k}) for k in range(8)]
        foundry = BeatFoundry([script(one(f"r{n}"), calls=calls) for n in range(1, 7)])
        foundry.after_run = lambda agent: seen.append((len(h.toolbox.log), h.toolbox.extra_calls)) if agent.startswith(agents.INVESTIGATOR_NAME) else None
        h = rig(None, foundry=foundry, by_kind=kinds, per_kind=1, investigate_beats=6)
        h.go()
        self.assertEqual([made for made, _ in seen], [2, 12, 22, 32, 42, 52], "two reads of code in each beat and eight calls in each beat before it")
        for made, extra in seen:
            self.assertGreaterEqual(tb.MAX_CALLS + extra, made + 8, "at the start of a beat the toolbox allows the beat the calls that its session may make")
        self.assertEqual(h.toolbox.limited, 0)
        self.assertEqual(sorted(extra for _, extra in seen), [extra for _, extra in seen], "an allowance is never taken back")
        h = rig([script(one("r1"))], by_kind={"contoso.compute/rigs": 100.0}, investigate_beats=1)
        result = h.go()
        (run,) = h.foundry.investigator_runs()
        self.assertEqual((run["input"], run["max_calls"], run["max_tokens"], h.toolbox.extra_calls, h.of("investigation.beat")), ('{"budget":{"toolCalls":30}}', 30, None, 0, []))
        self.assertEqual((result.state, len(result.beats)), ("ran", 1))

    def test_a_plan_of_two_beats_of_a_small_estate_is_two_beats_with_the_rest_in_the_last_one(self):
        h = rig([script(one("r1")), script(one("r3"))], by_kind={"contoso.compute/rigs": 100.0, "fabrikam.store/vaults": 90.0}, investigate_beats=2)
        h.go()
        self.assertEqual([json.loads(run["input"])["beat"]["focus"] for run in h.foundry.investigator_runs()], [["contoso.compute/rigs"], ["fabrikam.store/vaults"]])


class TheSkepticJudgesAsManyFindingsAsItTakes(unittest.TestCase):
    def many(self, count, chars, skeptic=None, **settings):
        raw = [one(f"r{n}", summary="BAD finding." if n == 2 else "A finding.") for n in range(1, count + 1)]
        scripts = [script(*raw[start:start + 2]) for start in range(0, len(raw), 2)]
        h = rig(scripts + [script()] * 3, skeptic=skeptic or (lambda seen: ti.verdicts(*[("disagree" if "BAD" in f["summary"] else "agree", ("it is shared",) if "BAD" in f["summary"] else (), "ok")
                                                                                         for f in seen["findings"]])), investigate_beats=3, **settings)
        with mock.patch.object(investigate, "SKEPTIC_CHARS", chars):
            return h, h.go()

    def test_findings_that_do_not_fit_in_one_input_go_to_it_in_as_many_calls_as_they_take_and_each_verdict_reaches_its_own_finding(self):
        h, result = self.many(4, 500)  # one finding of one resource is about 340 characters of input
        calls = h.foundry.skeptic_runs()
        self.assertEqual(len(calls), 4)
        self.assertEqual(sum(len(json.loads(call["input"])["findings"]) for call in calls), 4, "every finding was given to it once")
        self.assertEqual([e["verdict"] for e in h.of("investigation.finding")], ["agree", "disagree", "agree", "agree"], "the verdict of a finding is the one of its own index in its own call")
        self.assertEqual((result.cases, h.of("investigation.finding")[1]["shown"]), (4, 1))
        self.assertFalse([n for n in h.notes if "not shown to the Skeptic" in n], "every resource was shown")
        steps = {c.resource_name: c.steps for c in h.store.cases_recent()}
        self.assertTrue(all(s[-1]["step"] == "skeptic" and s[-1]["ok"] for s in steps.values()), steps)

    def test_two_findings_that_fit_together_are_given_together_and_findings_that_fit_in_one_input_are_judged_in_one_call_as_before(self):
        h, _ = self.many(4, 800)
        self.assertEqual([len(json.loads(call["input"])["findings"]) for call in h.foundry.skeptic_runs()], [2, 2])
        h, _ = self.many(4, 30000)
        self.assertEqual(len(h.foundry.skeptic_runs()), 1)

    def test_the_calls_of_the_skeptic_are_few_and_a_finding_that_gets_none_is_left_to_a_person_with_a_note(self):
        h, result = self.many(6, 500)
        self.assertEqual(len(h.foundry.skeptic_runs()), investigate.SKEPTIC_CALLS)
        verdicts = [e["verdict"] for e in h.of("investigation.finding")]
        self.assertEqual(verdicts.count(None), 6 - investigate.SKEPTIC_CALLS, verdicts)
        self.assertTrue([n for n in h.notes if "the Skeptic could not judge every finding" in n and "a finding without a verdict needs a person" in n], h.notes)
        unjudged = [c for c in h.store.cases_recent() if c.steps[-1]["step"] == "skeptic" and not c.steps[-1]["ok"]]
        self.assertEqual(len(unjudged), 6 - investigate.SKEPTIC_CALLS)
        self.assertEqual({c.status for c in unjudged}, {"needs_human"})

    def test_a_call_of_the_skeptic_that_fails_leaves_its_findings_to_a_person_and_the_others_keep_their_verdicts(self):
        foundry = BeatFoundry([script(one("r1"), one("r2")), script(one("r3"), one("r4")), script()])
        calls = {"n": 0}

        def skeptic(seen):
            calls["n"] += 1
            if calls["n"] == 2:
                raise FoundryError("the project is busy")
            return ti.agree_all(seen)

        foundry.skeptic = skeptic
        h = rig(None, foundry=foundry)
        with mock.patch.object(investigate, "SKEPTIC_CHARS", 800):
            h.go()
        verdicts = [e["verdict"] for e in h.of("investigation.finding")]
        self.assertEqual(verdicts[:2], ["agree", "agree"])
        self.assertEqual(verdicts[2:], [None, None])
        self.assertTrue([n for n in h.notes if "the project is busy" in n], h.notes)


class WhenTheBeatsRunUnderTheHarness(unittest.TestCase):
    def test_every_beat_is_a_run_of_its_own_with_its_own_tokens_and_a_beat_that_used_its_tokens_trips_nothing(self):
        import test_harness as th
        found, costs = pooled()
        foundry = BeatFoundry([script(one("r1")), script(one("r3"), out_of_tokens=True), script(one("r5"))])
        rigged = th.UnderTheHarness(foundry, SeedToolbox(found), investigate_beats=3)
        rigged.rig.contexts = {SUBSCRIPTION: Context(locks=[], recent=set(), managed_groups=set(), costs=costs, currency="USD")}
        result = rigged.go()
        runs = rigged.lines("harness.run")
        investigator = [line for line in runs if line["agent"] == agents.INVESTIGATOR_NAME]
        self.assertEqual((result.state, result.cases), ("ran", 3))
        self.assertEqual([(line["tokens"], line["toolCalls"], line["outcome"]) for line in investigator], [(44_000, 1, "ok")] * 3, "three lines, each with the numbers of one beat")
        self.assertEqual((rigged.pulled(), rigged.letters), ([], []))
        self.assertEqual(len([line for line in runs if line["agent"] == agents.SKEPTIC_NAME]), 1)


class WhatTheRecordKeepsOfTheBeats(unittest.TestCase):
    def test_a_beat_is_a_line_with_its_kinds_its_calls_seconds_and_tokens_how_it_ended_how_many_of_its_kinds_were_looked_at_and_what_it_concluded(self):
        h = rig([script(one("r1"), examined=("rigs: no idle finding",)), script(one("r3"), out_of_tokens=True), script(one("r5"))])
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual([(b["n"], b["kinds"], b["calls"], b["max_calls"], b["tokens"], b["end"], b["seeded"], b["looked"], b["found"]) for b in record.beats],
                         [(n, [kind], 1, 8, 44_000, end, 2, 1, 1) for n, (kind, end) in enumerate(zip(KINDS, ("answered", "tokens", "answered")), 1)])
        self.assertEqual(record.beats[0]["says"], ["rigs: no idle finding"])
        self.assertEqual((record.calls, record.max_calls, record.tokens, record.end), (3, 24, 3 * 44_000 + 600, "tokens"))
        self.assertEqual((record.known, record.looked), (3, 3), "the kinds that the tools of all the beats read, against the kinds that the estate has: a count")
        self.assertEqual([f["beat"] for f in record.findings], [1, 2, 3])
        self.assertNotRegex(json.dumps([record.beats, record.findings]), r"(?i)usd|cost|[$€£]|share|percent")

    def test_a_record_of_one_open_beat_has_no_beats_and_the_ends_and_calls_are_what_they_were(self):
        h = ti.Harness(BeatFoundry([script(one("r1"))]), SeedToolbox(pooled()[0]), ti.make_settings(), with_store=True)
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual((record.beats, record.more, record.max_calls, record.end), ((), 0, 30, "answered"))

    def test_a_beat_that_failed_is_a_line_that_says_so_and_the_investigation_still_ends_as_answered(self):
        h = rig([script(one("r1")), {"error": FoundryError("the project is busy")}, script(one("r5"))])
        h.go()
        (record,) = h.store.investigations_recent()
        self.assertEqual([(b["end"], b["found"]) for b in record.beats], [("answered", 1), ("failed", 0), ("answered", 1)])
        self.assertEqual((record.end, record.answered), ("answered", True))
        self.assertNotIn("busy", json.dumps(record.beats), "what a service said is not kept in a line of a beat")

    def test_the_end_of_all_the_beats_is_the_first_of_time_tokens_and_calls_that_one_ran_out_of_and_failed_when_none_answered(self):
        h = rig([{"error": FoundryError("busy")}] * 3)
        h.go()
        self.assertEqual(h.store.investigations_recent()[0].end, "failed")
        for ends, word in ((("answered", "calls", "tokens"), "tokens"), (("answered", "calls", "time"), "time"), (("answered", "calls", "answered"), "calls")):
            out = investigate.Investigation(ran=True, beats=[beats.Result(beats.Beat(n), end=end) for n, end in enumerate(ends, 1)])
            self.assertEqual(activity.end_of(out), word, ends)
        self.assertEqual(activity.end_of(investigate.Investigation(ran=True, held=True, beats=[beats.Result(beats.Beat(1), end="answered")])), "refused")

    def test_a_record_of_many_beats_and_findings_that_would_not_fit_a_row_of_the_store_is_cut_to_fit_and_says_how_many_findings_it_left_out(self):
        verdict = SimpleNamespace(verdict="disagree", objections=("o" * 300, "p" * 300))
        findings = [investigate.Finding(n, basis="no-usage", proposal="delete", confidence=0.9, summary="s" * 300, note="n" * 300, verdict=verdict, claimed=60, fates={"request": 3, "person": 2},
                                        guarded=1, recent=1, beat=1 + n % 8) for n in range(1, 41)]
        results = [beats.Result(beats.Beat(n, tuple(f"{'k' * 20}{n}.{'a' * 20}/{'b' * 40}" for _ in range(8)), True, 20, 8), 8, 8, 100_000, 160, "answered", 5, 3, 8, "",
                                ["x" * 100] * 12, [{}]) for n in range(1, 9)]
        out = investigate.Investigation(ran=True, beats=results, findings=findings, examined=["e" * 100] * 24, toolbox=SeedToolbox(pooled()[0]))
        s = SimpleNamespace(settings=ti.make_settings(), history=SimpleNamespace(run_id="r" * 32), harness=None)
        record = activity.record_of(s, out, {}, trigger="timer", at="2026-11-17T05:30:00Z", seconds=1000)
        self.assertLessEqual(len(record.to_json()), MAX_DATA)
        self.assertEqual(len(record.beats), 8)
        self.assertEqual((len(record.findings), record.more), (len(record.findings), 40 - len(record.findings)))
        self.assertGreater(len(record.findings), 0)
        self.assertEqual(type(record).from_json(record.to_json()), record)


if __name__ == "__main__":
    unittest.main()
