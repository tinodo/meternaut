"""Coverage: each run looks at resources that the earlier runs did not (cases/toolbox.py, cases/activity.py, cases/beats.py, cases/investigate.py, docs/proposals/25-beats.md).

The record of a run keeps the hashes of the resources whose picture the toolbox read, the seeds that code reads for a beat put what no run of the last LOOKED_DAYS days looked at first, the last beat
names the kinds that no run touched first, and the beat is told how many of its resources were looked at. Every kind and resource in this file is invented."""
import datetime as dt
import hashlib
import json
import re
import unittest
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
import test_beats as tbeats
import test_investigate as ti
from test_toolbox import SUB, ask, row, toolbox
from test_toolbox_depth import profiled
from test_toolbox_meters import WIDGET, widgets

from cases import activity, beats, dossier
from cases import toolbox as tb
from cases.detectors import Context
from cases.memory_store import MemoryStore, stamp
from cases.models import KEPT_INVESTIGATIONS, InvestigationRecord, StoreError

FIRST_DAY = dt.datetime(2026, 11, 4, 12, 0, 0, tzinfo=dt.timezone.utc)


def digest(resource_id: str) -> str:
    """The recipe of the record, written out again: the first 12 hex characters of the SHA-256 of the lower-cased resource id."""
    return hashlib.sha256(resource_id.lower().encode()).hexdigest()[:12]


def named(box, answer) -> list[str]:
    return [box.handles[row[0]].name for row in answer["rows"]]


class TheListingThatCodeMakesForASeed(unittest.TestCase):
    """`list_resources` with the order cost, while `rotate` is on (code's own read for a beat): what no run looked at lately first, each group by cost and then by key."""

    def box(self, looked=(), count=12, estate=None):
        estate = estate or widgets(count)
        box = toolbox(estate)
        box.window = frozenset(digest(estate.id_of(f"w{n}")) for n in looked)
        return estate, box

    def listing(self, box, rotate, **more):
        box.rotate = rotate
        try:
            return ask(box, "list_resources", type=WIDGET, limit=12, **more)
        finally:
            box.rotate = False

    def test_the_resources_that_no_run_looked_at_come_first_and_each_group_is_in_the_order_of_its_cost(self):
        _, box = self.box(looked=(1, 2, 3, 4, 5, 9))
        self.assertEqual(named(box, self.listing(box, True)), ["w6", "w7", "w8", "w10", "w11", "w12", "w1", "w2", "w3", "w4", "w5", "w9"])

    def test_a_tie_in_the_cost_goes_by_the_key_in_each_group(self):
        estate = widgets(4)
        estate.rows.reverse()  # the rows come in the reverse order of their keys, so that the order of the listing cannot be the order in which they were read
        estate.cost_rows = [(SUB, 10.0, found["id"].lower(), "Example Service") for found in estate.rows]
        _, box = self.box(looked=(1, 3), estate=estate)
        self.assertEqual(named(box, self.listing(box, True)), ["w2", "w4", "w1", "w3"])

    def test_without_a_memory_the_order_is_the_one_that_it_always_was_with_the_switch_on_or_off(self):
        for rotate in (True, False):
            _, box = self.box()
            self.assertEqual(named(box, self.listing(box, rotate)), [f"w{n}" for n in range(1, 13)])

    def test_when_every_resource_of_a_kind_was_looked_at_the_order_is_the_dearest_first_and_nothing_is_left_out(self):
        _, box = self.box(looked=range(1, 13))
        answer = self.listing(box, True)
        self.assertEqual((named(box, answer), answer["total"]), ([f"w{n}" for n in range(1, 13)], 12))

    def test_the_listing_of_the_investigator_keeps_meaning_the_dearest_first_whatever_the_memory_holds(self):
        _, remembering = self.box(looked=(1, 2, 3, 4, 5))
        _, forgetting = self.box()
        asked = dict(type=WIDGET, order_by="cost", limit=5, offset=None)
        self.assertEqual(remembering.call("list_resources", asked), forgetting.call("list_resources", asked), "the answer is the same text, handles and all")
        self.assertEqual(named(remembering, self.listing(remembering, False, offset=None, order_by="cost")), [f"w{n}" for n in range(1, 13)])
        self.assertFalse(remembering.rotate, "the switch is off unless code turns it on for one read")

    def test_the_order_by_count_is_not_touched_by_the_switch(self):
        _, box = self.box(looked=(1, 2, 3))
        self.assertEqual(named(box, self.listing(box, True, order_by="count")), [f"w{n}" for n in range(1, 13)])

    def test_the_toolbox_starts_with_no_memory_and_the_switch_off(self):
        box = toolbox(widgets(2))
        self.assertEqual((box.window, box.rotate, box.looked_at()), (frozenset(), False, frozenset()))


class WhatTheToolboxKeepsOfWhatItLookedAt(unittest.TestCase):
    def opened(self, count=4):
        estate = profiled(count)
        box = toolbox(estate)
        ask(box, "list_resources", type=WIDGET)
        return estate, box

    def test_a_picture_that_was_read_is_kept_as_the_hash_of_the_lower_case_id_and_nothing_else(self):
        estate, box = self.opened()
        ask(box, "profile", handles=["r1", "r3"])
        wanted = {digest(estate.id_of("w1")), digest(estate.id_of("w3"))}
        self.assertEqual(box.looked_at(), wanted)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{12}", word) for word in box.looked_at()))
        self.assertEqual(tb.seen_hash(estate.id_of("w1").lower()), digest(estate.id_of("w1")))

    def test_a_resource_that_was_only_listed_or_described_was_not_looked_at(self):
        _, box = self.opened()
        ask(box, "describe", handle="r2")
        self.assertEqual(box.looked_at(), frozenset())

    def test_a_resource_that_another_tool_wrote_a_read_for_was_not_looked_at_either(self):
        estate, box = self.opened()
        estate.ages[estate.id_of("w1").lower()] = {"sd": {"createdAt": "2025-01-02T10:00:00Z", "createdByType": "User", "lastModifiedAt": "2025-02-01T00:00:00Z", "lastModifiedByType": "User"}}
        ask(box, "changes", handles=["r1"])
        ask(box, "neighbors", handles=["r1"])
        self.assertEqual(box.log[-2]["read"], {"r1": "d"}, "the tool for the age of a resource says that it read something of it, as the tool for a picture does")
        self.assertEqual(box.looked_at(), frozenset(), "and it is no picture")

    def test_a_picture_that_could_read_nothing_is_no_look_and_one_that_read_a_part_is(self):
        _, late = self.opened()
        late.budget_seconds = 0.0
        ask(late, "profile", handles=["r1"])
        self.assertEqual(late.looked_at(), frozenset(), "every part of it was unread")
        estate, box = self.opened()
        with mock.patch.object(dossier, "complete", return_value=False):
            ask(box, "profile", handles=["r2"])
        self.assertEqual((box._pictures, box.looked_at()), ({}, {digest(estate.id_of("w2"))}), "the picture is not kept as whole, and the resource was looked at all the same")

    def test_a_repeat_of_a_picture_that_is_kept_is_the_same_look(self):
        _, box = self.opened()
        ask(box, "profile", handles=["r1"])
        ask(box, "profile", handles=["r1"])
        self.assertEqual(len(box.looked_at()), 1)

    def test_the_resources_of_these_types_that_the_runs_of_the_last_days_looked_at_are_counted_and_not_what_this_run_looked_at(self):
        estate, box = self.opened()
        box.window = frozenset({digest(estate.id_of("w1")), digest(estate.id_of("w2")), digest("/subscriptions/x/gone")})
        ask(box, "profile", handles=["r2", "r4"])
        self.assertEqual((box.seen_in([WIDGET]), box.seen_in(["contoso.other/kind"]), box.seen_in([])), (2, 0, 0), "w1 and w2 from the window; w4 was looked at by this run, which the beat is not told of")


class TheKindsOfTheLastBeat(unittest.TestCase):
    KINDS = [f"contoso.thing{n:02d}/kind" for n in range(20)]  # the dearest first
    COSTS = {kind: 100.0 - n for n, kind in enumerate(KINDS)}

    def test_the_kinds_that_no_run_touched_come_first_and_then_the_dearest_and_the_rest_is_still_counted(self):
        (only,) = beats.plan(self.COSTS, 0.0, 1, frozenset(self.KINDS[:5] + self.KINDS[7:8]))
        self.assertEqual(only.kinds, tuple(self.KINDS[5:7] + self.KINDS[8:14]))
        self.assertEqual(only.rest, 20 - beats.CATCH_ALL_KINDS, "the others are counted as they were: eight are named")

    def test_with_nothing_touched_or_everything_touched_the_kinds_are_the_dearest_eight_as_they_were(self):
        (plain,) = beats.plan(self.COSTS, 0.0, 1)
        self.assertEqual(plain.kinds, tuple(self.KINDS[:8]))
        for touched in (frozenset(), frozenset(self.KINDS), frozenset({"contoso.elsewhere/kind"})):
            self.assertEqual(beats.plan(self.COSTS, 0.0, 1, touched), [plain])

    def test_only_the_last_beat_is_moved_by_what_was_touched(self):
        estate = tbeats.ESTATE
        touched = frozenset(estate)
        self.assertEqual(beats.plan(estate, tbeats.UNOWNED, 8, touched)[:5], beats.plan(estate, tbeats.UNOWNED, 8)[:5])
        last = beats.plan({**estate, "litware.c/z": 1.0, "litware.d/w": 0.5}, tbeats.UNOWNED, 8, frozenset(estate))[-1]
        self.assertEqual(last.kinds[:2], ("litware.c/z", "litware.d/w"), "the kinds that no run touched, though they are the cheapest")

    def test_no_kind_of_resource_is_written_in_the_module_for_this(self):
        source = (support.APP_ROOT / "cases" / "beats.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"""["'][a-z0-9]+\.[a-z0-9]+/[a-z0-9]+["']""", source), [])


class TheInputOfABeat(unittest.TestCase):
    BEAT = beats.Beat(2, ("contoso.compute/rigs",), False, 0, 3)

    def test_it_says_in_one_typed_field_how_many_of_its_resources_were_looked_at_in_how_many_days(self):
        body = json.loads(beats.beat_input(self.BEAT, 8, beats.Seed({"contoso.compute/rigs": 12}, ["r1"], None, seen=5), []))
        self.assertEqual(body["lookedAt"], {"days": activity.LOOKED_DAYS, "resources": 5})
        self.assertEqual((activity.LOOKED_DAYS, type(body["lookedAt"]["resources"]), type(body["lookedAt"]["days"])), (21, int, int))

    def test_with_none_looked_at_or_no_seed_the_input_is_the_one_that_it_always_was(self):
        seeded = beats.Seed({"contoso.compute/rigs": 12}, ["r1"], [{"profiles": [{"handle": "r1"}]}])
        self.assertNotIn("lookedAt", beats.beat_input(self.BEAT, 8, seeded, []))
        self.assertEqual(beats.beat_input(self.BEAT, 8, seeded, []), beats.beat_input(self.BEAT, 8, beats.Seed(seeded.counts, seeded.handles, seeded.pictures, seen=0), []))
        self.assertEqual(beats.beat_input(beats.Beat(), 30, None, []), '{"budget":{"toolCalls":30}}')

    def test_the_field_fits_in_the_room_that_the_input_keeps_for_the_beat_and_its_counts(self):
        kinds = tuple(f"contoso.catchall/{n}{'k' * 41}" for n in range(beats.CATCH_ALL_KINDS))
        text = beats.beat_input(beats.Beat(8, kinds, True, 40, 8), 8, beats.Seed({kind: 120 for kind in kinds[:beats.SEED_RESOURCES]}, seen=9999), [])
        self.assertLessEqual(len(text), 1000)


class TheNoteOfARun(unittest.TestCase):
    def test_it_reads_right_at_none_one_and_many(self):
        words = activity.looked_note
        self.assertEqual(words(0, 0, 52), "This run looked at no resources. In 21 days Meternaut has looked at 52 resources.")
        self.assertEqual(words(0, 0, 1), "This run looked at no resources. In 21 days Meternaut has looked at 1 resource.")
        self.assertEqual(words(1, 1, 1), "This run looked at 1 resource, for the first time in 21 days.")
        self.assertEqual(words(1, 0, 5), "This run looked at 1 resource, not for the first time in 21 days. In 21 days Meternaut has looked at 5 resources.")
        self.assertEqual(words(19, 14, 52), "This run looked at 19 resources, 14 of them for the first time in 21 days. In 21 days Meternaut has looked at 52 resources.")
        self.assertEqual(words(2, 1, 9), "This run looked at 2 resources, 1 of them for the first time in 21 days. In 21 days Meternaut has looked at 9 resources.")
        self.assertEqual(words(19, 19, 19), "This run looked at 19 resources, all of them for the first time in 21 days.")
        self.assertEqual(words(19, 0, 30), "This run looked at 19 resources, none of them for the first time in 21 days. In 21 days Meternaut has looked at 30 resources.")
        self.assertEqual(words(1234, 1000, 5678), "This run looked at 1,234 resources, 1,000 of them for the first time in 21 days. In 21 days Meternaut has looked at 5,678 resources.", "thousands are written with a separator")

    def test_every_sentence_is_whole_and_short_with_no_id_and_no_stray_space(self):
        for numbers in ((0, 0, 52), (1, 1, 1), (1, 0, 5), (19, 14, 52), (19, 19, 19), (19, 0, 30), (2, 1, 3)):
            text = activity.looked_note(*numbers)
            for sentence in re.split(r"(?<=\.) ", text):
                self.assertRegex(sentence, r"^[A-Z][^.]*\.$", numbers)
                self.assertLessEqual(len(sentence.split()), 25, numbers)
            self.assertNotRegex(text, r"\s{2}| \.|\.\.|,,|, \.")


class WhatTheEarlierRunsLookedAt(unittest.TestCase):
    NOW = FIRST_DAY + dt.timedelta(days=30)

    def record(self, n, days_ago, **more):
        return InvestigationRecord(run_id=f"run{n:03d}", at=stamp(self.NOW - dt.timedelta(days=days_ago)), **more)

    def store(self, *records):
        store = MemoryStore()
        for record in records:
            store.investigation_put(record)
        return store

    def test_the_hashes_and_the_kinds_of_the_runs_of_the_last_days_and_no_others(self):
        store = self.store(self.record(1, 22, profiled=("aaaaaaaaaaaa",), kinds=(["contoso.a/x", "l"],)), self.record(2, 20, profiled=("bbbbbbbbbbbb", "cccccccccccc"), kinds=(["contoso.b/y", "lm"],)),
                           self.record(3, 1, profiled=("cccccccccccc", "dddddddddddd"), kinds=(["contoso.c/z", "d"], ["contoso.b/y", "d"])))
        self.assertEqual(activity.earlier(store, self.NOW), ({"bbbbbbbbbbbb", "cccccccccccc", "dddddddddddd"}, {"contoso.b/y", "contoso.c/z"}), "a run of 22 days ago is outside the window of 21")

    def test_a_run_of_exactly_the_window_is_inside_it_and_one_second_older_is_not(self):
        edge = self.NOW - dt.timedelta(days=activity.LOOKED_DAYS)
        store = self.store(InvestigationRecord(run_id="a", at=stamp(edge), profiled=("aaaaaaaaaaaa",)), InvestigationRecord(run_id="b", at=stamp(edge - dt.timedelta(seconds=1)), profiled=("bbbbbbbbbbbb",)))
        self.assertEqual(activity.earlier(store, self.NOW)[0], {"aaaaaaaaaaaa"})

    def test_a_store_that_cannot_be_read_or_that_holds_nothing_remembers_nothing(self):
        class Down(MemoryStore):
            def investigations_recent(self, limit=KEPT_INVESTIGATIONS):
                raise StoreError("the table service is down")

        self.assertIsNone(activity.earlier(Down(), self.NOW), "None says that the memory could not be read: an empty memory is another thing")
        self.assertEqual(activity.earlier(MemoryStore(), self.NOW), (frozenset(), frozenset()))

    def test_the_store_keeps_the_runs_of_the_window_at_the_default_pace_of_the_timer_and_the_window_is_the_one_of_the_proposal(self):
        self.assertEqual((activity.LOOKED_DAYS, KEPT_INVESTIGATIONS), (21, 20))
        from cases import config
        self.assertGreaterEqual(KEPT_INVESTIGATIONS * config.DEFAULT_INVESTIGATE_EVERY_DAYS, activity.LOOKED_DAYS, "twenty runs, a week apart, are 140 days: the window is in the records")


class WhatTheRecordKeepsOfWhatWasLookedAt(unittest.TestCase):
    def made(self, box):
        s = type("S", (), {})()
        s.settings, s.history, s.harness = ti.make_settings(), type("H", (), {"run_id": "r" * 32})(), None
        out = ti.investigate.Investigation(ran=True, toolbox=box)
        return activity.record_of(s, out, {}, trigger="timer", at="2026-11-04T12:00:00Z", seconds=10)

    def test_the_record_holds_the_sorted_hashes_of_the_pictures_and_no_id_and_no_name(self):
        estate = profiled(3)
        box = toolbox(estate)
        ask(box, "list_resources", type=WIDGET)
        ask(box, "profile", handles=["r3", "r1"])
        record = self.made(box)
        self.assertEqual(record.profiled, tuple(sorted(digest(estate.id_of(name)) for name in ("w1", "w3"))))
        text = record.to_json()
        for found in estate.rows:
            self.assertNotIn(found["id"].lower(), text.lower())
            self.assertNotIn(found["name"], text)
        self.assertNotIn("/subscriptions/", text)
        self.assertEqual(InvestigationRecord.from_json(text), record)

    def test_a_record_that_has_no_toolbox_or_one_that_looked_at_nothing_holds_none(self):
        self.assertEqual(self.made(None).profiled, ())
        self.assertEqual(self.made(toolbox(widgets(2))).profiled, ())

    def test_a_record_keeps_at_most_as_many_hashes_as_it_has_room_for(self):
        class Many:
            handles, log = {}, []

            @staticmethod
            def looked_at():
                return frozenset(f"{n:012x}" for n in range(activity.MAX_PROFILED + 50))

        record = self.made(Many())
        self.assertEqual(len(record.profiled), activity.MAX_PROFILED)
        self.assertLess(len(record.to_json()), 30000 // 4, "a record with all of them is far below a row of the store")

    def test_a_record_from_before_the_field_reads_as_nothing_looked_at(self):
        old = InvestigationRecord.from_json(json.dumps({"run_id": "r", "at": "2026-11-05T05:30:00Z", "known": 3}))
        self.assertEqual((old.profiled, old.known), ((), 3))


def costs_of(estate, count=12):
    return {estate.id_of(f"w{n}").lower(): 100.0 - n for n in range(1, count + 1)}


class ARunInTheLastDaysOfARun(unittest.TestCase):
    """The same estate of 12 resources of one kind, run again and again against one store: the seeds move on, and nothing that a person reads or the store keeps has an id."""

    def setUp(self):
        self.clock = ti.Moving()
        self.store = MemoryStore(clock=self.clock)

    def go(self, number, *, days=1, calls=(), script=None, store=None, error=None):
        self.clock.advance(days=days)
        estate = profiled(12)
        box = toolbox(estate)
        self.spied = []
        real = box.call

        def spy(name, arguments):
            text = real(name, arguments)
            self.spied.append((name, arguments, text, box.rotate))
            return text

        box.call = spy
        found = [{"error": error}] if error else [script or tbeats.script(calls=calls)]
        h = ti.Harness(tbeats.BeatFoundry(found), box, ti.make_settings(investigate_beats=3, investigate_max_seconds=1080, investigate_beat_calls=8, investigate_beat_seconds=100), clock=self.clock,
                       extras=ti.loop_for(self.clock, store or self.store))
        h.s.history.run_id = f"{number:032d}"
        h.contexts = {SUB: Context(locks=[], recent=set(), managed_groups=set(), costs=costs_of(estate), currency="USD")}
        h.notes.append("a note of the Watch from before the investigation")
        h.go()
        return h, estate, box

    @staticmethod
    def seeded(h, box):
        body = json.loads(h.foundry.investigator_runs()[0]["input"])
        return [box.handles[p["handle"]].name for answer in body.get("pictures", []) for p in answer["profiles"]], body

    def test_three_runs_in_a_row_seed_the_dearest_five_then_the_next_five_then_the_last_two_and_the_dearest_again(self):
        first, _, box = self.go(1)
        self.assertEqual(self.seeded(first, box)[0], ["w1", "w2", "w3", "w4", "w5"])
        second, _, box = self.go(2)
        self.assertEqual(self.seeded(second, box)[0], ["w6", "w7", "w8", "w9", "w10"])
        third, _, box = self.go(3)
        self.assertEqual(self.seeded(third, box)[0], ["w11", "w12", "w1", "w2", "w3"])

    def test_the_beat_is_told_how_many_of_its_resources_were_looked_at_only_when_some_were(self):
        told = []
        for number in (1, 2, 3):
            h, _, box = self.go(number)
            told.append(self.seeded(h, box)[1].get("lookedAt"))
        self.assertEqual(told, [None, {"days": 21, "resources": 5}, {"days": 21, "resources": 10}])

    def test_the_records_hold_the_hashes_of_what_each_run_looked_at_and_the_note_and_the_history_say_it_in_counts(self):
        notes, finished = [], []
        for number in (1, 2, 3):
            h, estate, box = self.go(number)
            notes.append([n for n in h.notes if n.startswith("This run looked at")])
            finished.append({key: h.of("investigation.finished")[0].get(key) for key in ("profiled", "firstTime", "inWindow")})
            self.assertEqual(h.notes[0], notes[-1][0], "the first of the notes of the run: a run keeps its first twenty, and this is the one that says what it looked at")
        self.assertEqual(notes, [["This run looked at 5 resources, all of them for the first time in 21 days."],
                                 ["This run looked at 5 resources, all of them for the first time in 21 days. In 21 days Meternaut has looked at 10 resources."],
                                 ["This run looked at 5 resources, 2 of them for the first time in 21 days. In 21 days Meternaut has looked at 12 resources."]])
        self.assertEqual(finished, [{"profiled": 5, "firstTime": 5, "inWindow": 5}, {"profiled": 5, "firstTime": 5, "inWindow": 10}, {"profiled": 5, "firstTime": 2, "inWindow": 12}])
        oldest, middle, newest = reversed(self.store.investigations_recent())
        self.assertEqual(oldest.profiled, tuple(sorted(digest(estate.id_of(f"w{n}")) for n in range(1, 6))))
        self.assertEqual(middle.profiled, tuple(sorted(digest(estate.id_of(f"w{n}")) for n in range(6, 11))))
        self.assertEqual(len(newest.profiled), 5)

    def test_a_window_that_has_expired_brings_the_resources_back(self):
        self.go(1)
        later, _, box = self.go(2, days=22)
        self.assertEqual(self.seeded(later, box)[0], ["w1", "w2", "w3", "w4", "w5"], "the first run is 22 days old and no longer counts")
        self.assertNotIn("lookedAt", self.seeded(later, box)[1])
        self.assertEqual([n for n in later.notes if n.startswith("This run")], ["This run looked at 5 resources, all of them for the first time in 21 days."])

    def test_a_kind_that_was_all_looked_at_still_gives_a_seed_and_the_beat_is_not_empty(self):
        everything = tuple(sorted(digest(f"{estate_id}") for estate_id in costs_of(profiled(12))))
        self.store.investigation_put(InvestigationRecord(run_id="a" * 32, at=stamp(self.clock() - dt.timedelta(days=1)), profiled=everything))
        h, _, box = self.go(2)
        names, body = self.seeded(h, box)
        self.assertEqual(names, ["w1", "w2", "w3", "w4", "w5"], "the dearest first, as when nothing was looked at")
        self.assertEqual((body["lookedAt"], [e["end"] for e in h.of("investigation.beat")]), ({"days": 21, "resources": 12}, ["answered"]))

    def test_the_listing_of_the_investigator_is_the_dearest_first_while_the_listing_of_code_is_not(self):
        self.go(1)
        ask_all = {"type": WIDGET, "order_by": "cost", "limit": 12, "offset": None}
        h, _, box = self.go(2, script=tbeats.script(calls=(("list_resources", ask_all),)))
        code, agent = [(name, text, rotating) for name, _, text, rotating in self.spied if name == "list_resources"]
        self.assertEqual((code[2], agent[2]), (True, False), "only the read that code makes for the seed asks for what was not looked at first")
        self.assertEqual(named(box, json.loads(agent[1])), [f"w{n}" for n in range(1, 13)])
        self.assertEqual(named(box, json.loads(code[1]))[:5], ["w6", "w7", "w8", "w9", "w10"])
        self.assertFalse(box.rotate)

    def test_what_the_investigator_profiles_itself_is_looked_at_too(self):
        ask_all = {"type": WIDGET, "order_by": "cost", "limit": 12, "offset": None}
        calls = (("list_resources", ask_all), ("profile", {"handles": ["r11"], "days": None, "grain": None}))  # the seed showed r1 to r5, so the listing shows w6 to w12 as r6 to r12
        h, estate, box = self.go(1, script=tbeats.script(calls=calls))
        (kept,) = self.store.investigations_recent()
        self.assertEqual((len(kept.profiled), digest(estate.id_of("w11")) in kept.profiled), (6, True), "the five of the seed and the one that the Investigator asked for")
        self.assertEqual(h.of("investigation.finished")[0]["profiled"], 6)
        later, _, box = self.go(2)
        self.assertEqual(self.seeded(later, box)[0], ["w6", "w7", "w8", "w9", "w10"], "w11 is not one of them: it was looked at")
        third, _, box = self.go(3)
        self.assertEqual(self.seeded(third, box)[0], ["w12", "w1", "w2", "w3", "w4"], "w11 is looked at, so w12 is the only one that no run saw")

    def test_a_run_that_ends_early_keeps_what_it_looked_at_and_the_next_one_moves_on(self):
        h, estate, box = self.go(1, error=ti.FoundryError("the project is busy"))
        (kept,) = self.store.investigations_recent()
        self.assertEqual((kept.end, len(kept.profiled)), ("failed", 5))
        second, _, box = self.go(2)
        self.assertEqual(self.seeded(second, box)[0], ["w6", "w7", "w8", "w9", "w10"])
        self.assertEqual([n for n in h.notes if n.startswith("This run")], ["This run looked at 5 resources, all of them for the first time in 21 days."])

    def test_a_store_that_cannot_be_read_gives_the_order_that_it_always_was_and_the_run_says_so_and_claims_nothing_of_what_is_new(self):
        class Down(MemoryStore):
            def investigations_recent(self, limit=KEPT_INVESTIGATIONS):
                raise StoreError("the table service is down")

        h, _, box = self.go(1, store=Down(clock=self.clock))
        self.assertEqual(self.seeded(h, box)[0], ["w1", "w2", "w3", "w4", "w5"])
        (finished,) = h.of("investigation.finished")
        self.assertTrue(finished["ok"])
        self.assertIn("The earlier investigations could not be read, so this run took the dearest resources first.", h.notes)
        self.assertIn("The earlier investigations could not be read, so this run took the dearest resources first.", [e.get("note") for e in h.of("run.note")], "the History has it too")
        self.assertEqual([n for n in h.notes if n.startswith("This run looked at")], [], "no claim of what is new against a memory that was not read")
        self.assertEqual({key: finished.get(key) for key in ("profiled", "firstTime", "inWindow")}, {"profiled": 5, "firstTime": None, "inWindow": None}, "what the run looked at is a fact, what is new is not")

    def test_a_memory_that_was_read_and_is_empty_says_nothing_of_a_failure(self):
        h, _, _ = self.go(1)
        self.assertFalse([n for n in h.notes if "could not be read" in n])
        self.assertEqual(h.of("investigation.finished")[0].get("firstTime"), 5)

    def test_an_older_record_without_the_field_changes_nothing(self):
        self.store.investigation_put(InvestigationRecord.from_json(json.dumps({"run_id": "old", "at": stamp(self.clock() - dt.timedelta(days=2)), "end": "answered", "known": 3})))
        h, _, box = self.go(1)
        self.assertEqual(self.seeded(h, box)[0], ["w1", "w2", "w3", "w4", "w5"])

    def test_no_resource_id_or_name_is_in_the_record_the_events_or_the_notes(self):
        for number in (1, 2):
            h, estate, _ = self.go(number)
        text = "\n".join([self.store.investigations_recent()[0].to_json(), json.dumps(h.events), "\n".join(h.notes), "\n".join(h.messages)]).lower()
        for found in estate.rows:
            self.assertNotIn(found["id"].lower(), text)
            self.assertNotRegex(text, rf"\b{found['name']}\b")
        self.assertNotIn("/subscriptions/", text)
        self.assertNotIn(SUB, text)
        self.assertNotRegex(json.dumps([h.of("investigation.finished")]), r"/subscriptions|widgets/w")

    def test_a_run_with_no_picture_and_no_memory_says_nothing_of_it_and_its_history_line_is_the_one_that_it_always_was(self):
        empty = ti.Harness(tbeats.BeatFoundry([tbeats.script()]), tbeats.SeedToolbox({}), ti.make_settings(), with_store=True)
        empty.go()
        self.assertEqual([n for n in empty.notes if n.startswith("This run")], [])
        self.assertTrue(empty.of("investigation.finished") and not {"profiled", "firstTime", "inWindow"} & set(empty.of("investigation.finished")[0]))

    def test_a_run_that_looked_at_nothing_in_a_window_that_holds_some_says_so(self):
        self.store.investigation_put(InvestigationRecord(run_id="a" * 32, at=stamp(self.clock() - dt.timedelta(days=2)), profiled=("aaaaaaaaaaaa", "bbbbbbbbbbbb")))
        quiet = ti.Harness(tbeats.BeatFoundry([tbeats.script()]), tbeats.SeedToolbox({}), ti.make_settings(), extras=ti.loop_for(self.clock, self.store), clock=self.clock)
        quiet.go()
        self.assertEqual([n for n in quiet.notes if n.startswith("This run")], ["This run looked at no resources. In 21 days Meternaut has looked at 2 resources."])
        self.assertEqual({key: quiet.of("investigation.finished")[0].get(key) for key in ("profiled", "firstTime", "inWindow")}, {"profiled": 0, "firstTime": 0, "inWindow": 2})


class WhatALaterBeatOfTheSameRunSeeds(unittest.TestCase):
    """The seeds of a beat start from what neither the earlier runs nor this run looked at (the term of the run in the order of the listing is intended): a resource whose picture the Investigator of
    the first beat asked for is not seeded again by a later beat, also in a first run with an empty memory. The first beat of such a run is in the order that it always was."""

    VAULT = "fabrikam.store/vaults"

    def test_a_second_beat_does_not_seed_what_the_first_beat_profiled_and_the_first_beat_of_a_first_run_is_in_the_old_order(self):
        estate = profiled(6)
        estate.rows += [row(self.VAULT, f"v{n}") for n in range(1, 7)]
        estate.cost_rows += [(SUB, 50.0 - n, estate.id_of(f"v{n}").lower(), "Example Service") for n in range(1, 7)]
        estate.definitions[self.VAULT] = estate.definitions[WIDGET]
        box = toolbox(estate)
        listing = ("list_resources", {"type": self.VAULT, "order_by": "cost", "limit": 12, "offset": None})
        pictured = ("profile", {"handles": ["r6"], "days": None, "grain": None})  # the seed of the first beat showed r1 to r5, so the vaults that it lists are r6 to r11, the dearest first
        h = ti.Harness(tbeats.BeatFoundry([tbeats.script(calls=(listing, pictured)), tbeats.script()]), box,
                       ti.make_settings(investigate_beats=3, investigate_max_seconds=1080, investigate_beat_calls=8, investigate_beat_seconds=100), with_store=True)
        h.contexts = {SUB: Context(locks=[], recent=set(), managed_groups=set(), costs={line[2]: line[1] for line in estate.cost_rows}, currency="USD")}
        h.go()
        first, second = [json.loads(run["input"]) for run in h.foundry.investigator_runs()]
        names = lambda body: [box.handles[p["handle"]].name for answer in body["pictures"] for p in answer["profiles"]]  # noqa: E731
        self.assertEqual((first["beat"]["focus"], second["beat"]["focus"]), ([WIDGET], [self.VAULT]))
        self.assertEqual(names(first), ["w1", "w2", "w3", "w4", "w5"], "the first beat of a first run: the dearest five")
        self.assertIn(digest(estate.id_of("v1")), box.looked_at(), "the Investigator of the first beat read the picture of the dearest vault")
        self.assertEqual(names(second), ["v2", "v3", "v4", "v5", "v6"], "and the second beat leaves it for the last")


class TheLastBeatOfARunNamesTheKindsThatNoRunTouched(unittest.TestCase):
    def test_a_run_plans_its_last_beat_from_the_kinds_that_the_records_of_the_window_say_were_touched(self):
        clock = ti.Moving()
        kinds = {f"contoso.thing{n:02d}/kind": 100.0 - n for n in range(20)}
        found, costs = tbeats.pooled(kinds, per_kind=1)
        touched = list(kinds)[:3]
        store = MemoryStore(clock=clock)
        store.investigation_put(InvestigationRecord(run_id="a" * 32, at=stamp(clock() - dt.timedelta(days=2)), kinds=tuple([kind, "l"] for kind in touched)))
        h = ti.Harness(tbeats.BeatFoundry([tbeats.script(), tbeats.script()]), tbeats.SeedToolbox(found), ti.make_settings(investigate_beats=2, investigate_max_seconds=1080, investigate_beat_calls=8,
                                                                                                                         investigate_beat_seconds=100), clock=clock, extras=ti.loop_for(clock, store))
        h.contexts = {SUB: Context(locks=[], recent=set(), managed_groups=set(), costs=costs, currency="USD")}
        h.go()
        inputs = [json.loads(run["input"]) for run in h.foundry.investigator_runs()]
        self.assertEqual(inputs[0]["beat"]["focus"], list(kinds)[:1], "the dearest kind has a beat of its own, whatever was touched")
        self.assertEqual(inputs[1]["beat"]["focus"], list(kinds)[3:11], "the dearest kinds that no run touched, and not the two of the others that were")
        self.assertEqual(inputs[1]["beat"]["moreKinds"], 19 - 8, "the kinds that it does not name are counted as before")


if __name__ == "__main__":
    unittest.main()
