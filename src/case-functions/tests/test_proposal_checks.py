"""What the Investigator may propose for a finding, and what code keeps of it (cases/proposals.py): the settings to change (`set`) and the other ways to save (`others`).

Every kind of resource, property and word here is invented. An entry is kept only when code can compare it with what the tools showed in the same run; one that fails is dropped by itself and
counted, and the finding stays. The Skeptic is shown what was kept, and the facts of a case keep it as typed data (the words of the pages are another piece of work).
"""
import json
import unittest
from collections import Counter
from dataclasses import replace
from unittest import mock

from test_investigate import (FakeFoundry, FakeToolbox, Harness, Moving, ScriptedAgent, answer, banned_in, disks_estate, entry, finding, key_of, loop_for, meter_line, metrics, resource,
                              verdicts)

from cases import agents, brief, investigate, models, pricing, proposals
from cases.toolbox import meter_word

GATEWAYS = "microsoft.example/gateways"
UNITS = "capacityUnits"
COSTS = {"r1": 200.0, "r2": 200.0}
GOOD = {"handle": "r1", "property": UNITS, "from": 4, "to": 2}
LITE = {"title": "Use the Lite tier", "gives_up": "Fewer units and no zone redundancy, as far as the documentation that was read says.", "in_place": False,
        "change": {"action": "switch", "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "assumed", "low": 0.3, "high": 0.5}}], "how": "Make it again on the Lite tier."}}
REMOVE = {"title": "Remove it", "gives_up": "Everything that uses it.", "in_place": True,
          "change": {"action": "remove", "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "none"}}], "how": "Delete it."}}


def properties(**more) -> dict:
    """What the tools showed of an invented gateway: a number that a smaller one may be stated for, a word, a flag and a count."""
    return {UNITS: 4, "tier": "Lite", "zoneRedundant": True, "retries": 8, **more}


def invented(*numbers, **more) -> FakeToolbox:
    """The invented gateways that the tools showed, each with one bill line of 200 dollars over its 30 days and `properties`."""
    handles = [f"r{n}" for n in numbers]
    evidence = {handle: {**metrics(MetricA=0), "properties": properties(**more)} for handle in handles}
    return FakeToolbox([resource(n, resource_type=GATEWAYS, name=f"gateway-{n}", cost_usd_30d=200.0) for n in numbers], evidence, meters={f"m{n}": meter_line(f"r{n}", 200.0) for n in numbers})


def reduce(handle="r1", on=UNITS, start=4, to=2, **more) -> dict:
    """The change that lowers the units by a ratio on the property, with what the Investigator may add to it."""
    return {"action": "reduce", "effects": [{"handle": handle, "meters": [f"m{handle[1:]}"], "remains": {"form": "ratio", "on": on, "from": start, "to": to}}], "how": "Lower the units.", **more}


def asked(change, handles=("r1",), **more) -> dict:
    return finding(handles=list(handles), basis="oversized", proposal="change", evidence=[entry(handle, "MetricA", 0) for handle in handles], change=change, **more)


def run(raw, box=None, **options) -> Harness:
    h = Harness(FakeFoundry(answer(raw)), box or invented(1), with_store=True, **options)
    h.go()
    return h


def facts_of(h, handle="r1") -> dict:
    return h.store.case_get(key_of(h.toolbox.handles[handle])).facts


def ways_of(h, handle="r1"):
    return facts_of(h, handle).get(proposals.KEY)


def checked(change, handles=("r1",), proposal="change", evidence=None, price=None) -> proposals.Checked:
    """The check on its own: no investigation, a made-up toolbox and a price that prices nothing unless a test gives one."""
    evidence = evidence if evidence is not None else {handle: {"properties": properties()} for handle in handles}
    return proposals.check(pricing.parse(change), proposal, list(handles), evidence, price or (lambda option: pricing.Priced(option.action)))


def priced_by_the_bill(box=None):
    box = box or invented(1, 2)
    return lambda option: pricing.price(option, ["r1"], box, COSTS, None, meter_word)


class TheKeyOfTheFacts(unittest.TestCase):
    def test_the_key_is_not_one_that_the_facts_of_a_case_already_have(self):
        made = investigate._facts(investigate.Finding(1, basis="oversized", proposal="change", asked="delete"), {"MetricA": 0}, 10.0, {}, 1)
        self.assertNotIn(proposals.KEY, made, "`proposal` is the word of the finding's proposal, and `change` is the digest of the saving")
        self.assertNotIn(proposals.KEY, (*made, pricing.KEY, models.GROUP_FACT, brief.IMPACT, brief.ADVISOR_KEY))


class WithTheRealTools(unittest.TestCase):
    """The real tools over the fake estate of test_toolbox, and an agent that copies numbers from their answers: a setting that copies what a tool returned is kept, and one that does not is dropped."""

    def run_claim(self, set_, **more):
        def claim(listed, measured):
            cols = listed["cols"]
            row = next(row for row in listed["rows"] if row[cols.index("diskSizeGB")] == 128)
            handle = row[cols.index("handle")]
            change = {"action": "reduce", "effects": [], "how": "Make it smaller.", "set": [{"handle": handle, **item} for item in set_], **more}
            return [finding(handles=[handle], basis="oversized", proposal="change", evidence=[entry(handle, "MetricX", 0)], change=change)]

        estate, real = disks_estate()
        h = Harness(ScriptedAgent(claim), real, with_store=True)
        h.go()
        (case,) = [case for case in h.store.cases_recent() if case.resource_name == "disk-a"]
        return h, case.facts.get(proposals.KEY)

    def test_a_setting_that_copies_what_the_tools_returned_is_kept(self):
        h, kept = self.run_claim([{"property": "diskSizeGB", "from": 128, "to": 64}])
        self.assertEqual(kept, {"set": [{"path": "diskSizeGB", "from": 128, "to": 64}]})
        self.assertEqual([note for note in h.notes if "dropped" in note], [])

    def test_a_setting_that_does_not_is_dropped_and_the_case_is_opened_all_the_same(self):
        for label, bad in (("an old value that the tools did not return", {"property": "diskSizeGB", "from": 127, "to": 64}),
                           ("a word that the tools returned", {"property": "diskState", "from": "Unattached", "to": "Attached"}),
                           ("a property that the tools did not show", {"property": "iops", "from": 500, "to": 250})):
            with self.subTest(label):
                h, kept = self.run_claim([bad])
                self.assertIsNone(kept)
                self.assertEqual(h.result.cases, 1, "the finding is kept: the case of the resource is opened")
                self.assertEqual(len([note for note in h.notes if note.startswith("finding 1: code dropped 1 of 1 setting")]), 1)


class WhatTheAnswerHolds(unittest.TestCase):
    def test_the_change_keeps_the_entries_as_stated_up_to_the_cap_of_its_lists(self):
        change = pricing.parse({"action": "reduce", "set": [GOOD] * 100, "others": [LITE] * 70})
        self.assertEqual((len(change.settings), len(change.others)), (pricing.MAX_EFFECTS, pricing.MAX_EFFECTS))
        self.assertEqual((change.settings[0], change.others[0]), (GOOD, LITE), "as stated: what is wrong with an entry is for the check to say")
        for text in ("x", 4, {"a": 1}, None):
            self.assertEqual(pricing.parse({"action": "reduce", "set": text, "others": text}).settings, ())
        self.assertEqual((pricing.parse({"action": "reduce"}).settings, pricing.parse({"action": "reduce"}).others), ((), ()))

    def test_nothing_that_a_model_writes_makes_the_check_raise_or_keep_anything(self):
        junk = [None, 5, 1.5, True, "x", [], [1], {}, {"handle": []}, {"handle": "r1", "property": {}}, {"handle": "r1", "property": UNITS, "from": 10 ** 400, "to": 1},
                {"handle": "r1", "property": UNITS, "from": 4, "to": 10 ** 400}, {"handle": "r1", "property": UNITS, "from": float("inf"), "to": float("-inf")},
                {"title": [], "change": []}, {"title": "ok", "change": {"action": [], "effects": "x", "set": 5, "others": {"title": 1}}}, {"title": "x" * 10 ** 5, "change": 1}]
        found = checked({"action": "reduce", "effects": [{"handle": "r1", "meters": [[]], "remains": {"form": "ratio", "on": [], "from": [], "to": {}}}], "set": junk, "others": junk})
        self.assertEqual((found.ways, found.said, sum(found.dropped.values())), ({}, (len(junk), len(junk)), 2 * len(junk)))


class WhatCodeKeepsOfTheSettings(unittest.TestCase):
    def test_a_setting_that_the_tools_showed_is_kept_in_the_shape_of_the_facts_and_read_back_by_the_readers(self):
        found = checked(reduce(set=[GOOD]))
        self.assertEqual(found.ways, {"r1": {"set": [{"path": UNITS, "from": 4, "to": 2}]}})
        self.assertEqual((found.dropped, found.said), (Counter(), (1, 0)))
        self.assertEqual(proposals.settings({proposals.KEY: found.ways["r1"]}), (proposals.Setting(UNITS, 4, 2),))

    def test_a_new_value_that_is_whole_is_kept_whole_and_one_that_is_fractional_is_kept_beside_a_fractional_old_value(self):
        self.assertEqual(checked(reduce(set=[{**GOOD, "to": 2.0}])).ways["r1"]["set"], [{"path": UNITS, "from": 4, "to": 2}])
        box = {"r1": {"properties": properties(ratio=2.5)}}
        found = checked(reduce(on="ratio", start=2.5, to=1.25, set=[{"handle": "r1", "property": "ratio", "from": 2.5, "to": 1.25}]), evidence=box)
        self.assertEqual(found.ways["r1"]["set"], [{"path": "ratio", "from": 2.5, "to": 1.25}])
        self.assertEqual(checked(reduce(to=0, set=[{**GOOD, "to": 0}])).ways["r1"]["set"][0]["to"], 0, "the new value may be nothing: 0 <= to < from")

    def test_each_entry_that_fails_a_rule_is_dropped_by_itself_and_counted_by_the_rule_and_the_others_stay(self):
        evidence = {"r1": {"properties": properties(sizes=[4, 2])}, "r2": {"properties": properties()}}
        table = (("a property that no tool showed", {**GOOD, "property": "otherUnits"}, "shown"),
                 ("an old value that differs from the tools", {**GOOD, "from": 5}, "from"),
                 ("an old value that is not a number", {**GOOD, "from": "4"}, "from"),
                 ("a new value that is not smaller", {**GOOD, "to": 4}, "to"),
                 ("a new value that is larger", {**GOOD, "to": 6}, "to"),
                 ("a new value that is negative", {**GOOD, "to": -1}, "to"),
                 ("a new value that is fractional where the old one is whole", {**GOOD, "to": 2.5}, "to"),
                 ("a new value that is text", {**GOOD, "to": "2"}, "to"),
                 ("a new value that is a flag", {**GOOD, "to": False}, "to"),
                 ("a new value that is not a number at all", {**GOOD, "to": float("nan")}, "to"),
                 ("a new value that is missing", {key: value for key, value in GOOD.items() if key != "to"}, "to"),
                 ("a word as the value", {"handle": "r1", "property": "tier", "from": "Lite", "to": "Basic"}, "number"),
                 ("a flag as the value", {"handle": "r1", "property": "zoneRedundant", "from": True, "to": False}, "number"),
                 ("a list as the value, which means that the items differ", {"handle": "r1", "property": "sizes", "from": 4, "to": 2}, "number"),
                 ("a resource that another finding has", {**GOOD, "handle": "r2"}, "handle"),
                 ("a handle that no tool showed", {**GOOD, "handle": "r99"}, "handle"),
                 ("a handle that is not text", {**GOOD, "handle": 1}, "handle"),
                 ("a property that is not text", {**GOOD, "property": 4}, "name"),
                 ("a property that is no plain name", {**GOOD, "property": "units; drop"}, "name"),
                 ("something that is no entry", "capacityUnits", "shape"),
                 ("an entry with no handle", {}, "handle"))
        for label, bad, why in table:
            with self.subTest(label):
                found = checked(reduce(set=[bad, GOOD]), evidence=evidence)
                self.assertEqual(found.ways["r1"]["set"], [{"path": UNITS, "from": 4, "to": 2}], "the good entry stays")
                self.assertEqual((found.dropped, found.said), (Counter({("set", why): 1}), (2, 0)))
        shown = {"r1": {"properties": {"units; drop": 4}}}
        self.assertEqual(checked(reduce(set=[{**GOOD, "property": "units; drop"}]), evidence=shown).dropped, Counter({("set", "name"): 1}), "a name that a tool showed is held to the form too")

    def test_a_property_is_listed_once_for_a_resource_and_the_limit_is_the_shared_one(self):
        found = checked({"action": "reduce", "effects": [], "set": [GOOD, GOOD, {**GOOD, "to": 1}]})
        self.assertEqual((found.ways["r1"]["set"], found.dropped), ([{"path": UNITS, "from": 4, "to": 2}], Counter({("set", "duplicate"): 2})))
        names = [f"count{n}" for n in range(proposals.MAX_SETTINGS + 2)]
        evidence = {"r1": {"properties": {name: 4 for name in names}}}
        many = [{"handle": "r1", "property": name, "from": 4, "to": 2} for name in names]
        found = checked({"action": "reduce", "effects": [], "set": many}, evidence=evidence)
        self.assertEqual([item["path"] for item in found.ways["r1"]["set"]], names[: proposals.MAX_SETTINGS])
        self.assertEqual((found.dropped, found.said), (Counter({("set", "limit"): 2}), (proposals.MAX_SETTINGS + 2, 0)))

    def test_only_a_finding_that_proposes_a_change_by_the_action_reduce_keeps_a_setting(self):
        for proposal, action in (("investigate", "reduce"), ("delete", "reduce"), ("change", "switch"), ("change", "remove"), ("change", "schedule"), ("change", "none")):
            with self.subTest(proposal=proposal, action=action):
                found = checked({**reduce(set=[GOOD]), "action": action}, proposal=proposal)
                self.assertEqual((found.ways, found.dropped), ({}, Counter({("set", "action"): 1})))
        self.assertEqual(checked(reduce(set=[GOOD])).dropped, Counter())

    def test_a_setting_agrees_with_a_ratio_on_the_same_property_of_the_same_resource_or_is_dropped(self):
        self.assertEqual(checked(reduce(start=4, to=2, set=[GOOD])).dropped, Counter())
        for label, setting, why in (("another new value", {**GOOD, "to": 1}, "ratio"), ("zero as the new value", {**GOOD, "to": 0}, "ratio")):
            with self.subTest(label):
                self.assertEqual(checked(reduce(start=4, to=2, set=[setting])).dropped, Counter({("set", why): 1}))
        other = {"r1": {"properties": properties(retries=8)}}
        self.assertEqual(checked(reduce(on="retries", start=8, to=4, set=[{**GOOD, "to": 1}]), evidence=other).dropped, Counter(), "a ratio on another property says nothing of this one")
        two = {"r1": {"properties": properties()}, "r2": {"properties": properties()}}
        change = reduce(handle="r2", start=4, to=2, set=[{**GOOD, "to": 1}])
        self.assertEqual(checked(change, handles=("r1", "r2"), evidence=two).dropped, Counter(), "nor does a ratio of another resource")
        self.assertEqual(checked(reduce(start="four", to=2, set=[{**GOOD, "to": 1}])).dropped, Counter(), "a ratio that is no pair of numbers is no change that was priced")

    def test_the_settings_of_each_resource_are_its_own(self):
        two = {handle: {"properties": properties(**({"retries": 6} if handle == "r2" else {}))} for handle in ("r1", "r2")}
        change = {"action": "reduce", "effects": [], "set": [GOOD, {"handle": "r2", "property": "retries", "from": 6, "to": 3}]}
        found = checked(change, handles=("r1", "r2"), evidence=two)
        self.assertEqual(found.ways, {"r1": {"set": [{"path": UNITS, "from": 4, "to": 2}]}, "r2": {"set": [{"path": "retries", "from": 6, "to": 3}]}})

    def test_nothing_is_kept_of_an_answer_with_no_change_or_a_set_that_is_no_list(self):
        self.assertEqual(proposals.check(None, "change", ["r1"], {}, lambda option: pricing.Priced("")), proposals.Checked({}, Counter(), (0, 0)))
        for text in ("capacityUnits", 4, {"handle": "r1"}, None):
            self.assertEqual(checked(reduce(set=text)), proposals.Checked({}, Counter(), (0, 0)))


class WhatCodeKeepsOfTheOtherWays(unittest.TestCase):
    def test_another_way_is_priced_from_the_bill_by_its_own_change_and_kept_with_its_words(self):
        found = checked(reduce(others=[LITE, REMOVE]), price=priced_by_the_bill())
        lite, gone = (pricing.price(pricing.parse(option["change"]), ["r1"], invented(1, 2), COSTS, None, meter_word).rows["r1"] for option in (LITE, REMOVE))
        self.assertGreater(gone.low, lite.low, "removing it saves more than a smaller tier: the figures are the bill's, each from its own change")
        self.assertEqual(found.ways, {"r1": {"others": [
            {"title": "Use the Lite tier", "givesUp": LITE["gives_up"], "action": "switch", "inPlace": False, "lowUsd": lite.low, "highUsd": lite.high},
            {"title": "Remove it", "givesUp": "Everything that uses it.", "action": "remove", "inPlace": True, "lowUsd": gone.low, "highUsd": gone.high}]}})
        self.assertEqual((found.dropped, found.said), (Counter(), (0, 2)))
        self.assertEqual([(o.title, o.in_place, o.low, o.high) for o in proposals.others({proposals.KEY: found.ways["r1"]})],
                         [("Use the Lite tier", False, lite.low, lite.high), ("Remove it", True, gone.low, gone.high)])

    def test_a_way_that_cannot_be_priced_is_kept_with_no_figure(self):
        unnamed = {**LITE, "change": {**LITE["change"], "effects": [{"handle": "r1", "meters": ["m9"], "remains": {"form": "none"}}], "action": "remove"}}
        found = checked(reduce(others=[unnamed]), price=priced_by_the_bill())
        self.assertEqual(found.ways["r1"]["others"], [{"title": "Use the Lite tier", "givesUp": LITE["gives_up"], "action": "remove", "inPlace": False}])
        (one,) = proposals.others({proposals.KEY: found.ways["r1"]})
        self.assertEqual((one.low, one.high), (None, None), "the page says that it is not priced")

    def test_a_way_whose_effects_name_another_resource_is_not_priced_for_this_one(self):
        elsewhere = {**LITE, "change": {**LITE["change"], "effects": [{"handle": "r2", "meters": ["m2"], "remains": {"form": "none"}}], "action": "remove"}}
        (one,) = proposals.others({proposals.KEY: checked(reduce(others=[elsewhere]), price=priced_by_the_bill()).ways["r1"]})
        self.assertEqual((one.low, one.high), (None, None))

    def test_the_words_of_a_way_are_cleaned_and_cut_and_a_flag_that_is_no_flag_is_none(self):
        said = {**LITE, "title": "  Use   the\nLite tier. ", "gives_up": "See https://evil.example/x or pay $500 a month. " + "x" * 400, "in_place": "yes"}
        (one,) = checked(reduce(others=[said])).ways["r1"]["others"]
        self.assertEqual(one["title"], "Use the Lite tier")
        self.assertTrue(one["givesUp"].startswith("See [link removed] or pay [figure removed]"), one["givesUp"])
        self.assertEqual((len(one["givesUp"]), one["givesUp"][-3:]), (proposals.MAX_GIVES_UP, "..."))
        self.assertNotIn("inPlace", one)
        self.assertEqual(checked(reduce(others=[{**LITE, "gives_up": 5}])).ways["r1"]["others"][0]["givesUp"], "", "what it gives up is left empty when the Investigator wrote none")

    def test_an_entry_that_fails_a_rule_is_dropped_by_itself_and_counted_and_the_others_stay(self):
        bad_title = lambda title: {**LITE, "title": title}
        table = (("a title of more than 80 characters", bad_title("x" * 81), "title"), ("a title with a link", bad_title("See https://evil.example/x"), "title"),
                 ("a title with markup", bad_title("<b>Use the Lite tier</b>"), "title"),
                 ("a title with an amount of money", bad_title("Save $500 a month"), "title"), ("a title with an amount in words of a currency", bad_title("Save 500 USD a month"), "title"),
                 ("a title that is empty", bad_title("   "), "title"), ("a title that is not text", bad_title(5), "title"), ("no title", {k: v for k, v in LITE.items() if k != "title"}, "title"),
                 ("a title with a line of a script", bad_title("Use it; drop table users"), "title"),
                 ("an action that is none", {**LITE, "change": {"action": "none"}}, "action"), ("an action that is unknown", {**LITE, "change": {**LITE["change"], "action": "teleport"}}, "action"),
                 ("no change", {k: v for k, v in LITE.items() if k != "change"}, "action"), ("a change that is no object", {**LITE, "change": "switch"}, "action"),
                 ("something that is no entry", "Use the Lite tier", "shape"))
        for label, bad, why in table:
            with self.subTest(label):
                found = checked(reduce(others=[bad, LITE]))
                self.assertEqual([item["title"] for item in found.ways["r1"]["others"]], ["Use the Lite tier"])
                self.assertEqual((found.dropped, found.said), (Counter({("other", why): 1}), (0, 2)))

    def test_a_way_that_is_the_change_itself_or_another_way_again_is_dropped(self):
        same_as_main = {"title": "Lower the units", "gives_up": "Nothing.", "change": reduce()}
        same_change = {**LITE, "title": "Switch to Lite"}
        same_title = {**REMOVE, "title": "use THE lite tier"}
        found = checked(reduce(others=[same_as_main, LITE, same_change, same_title]))
        self.assertEqual([item["title"] for item in found.ways["r1"]["others"]], ["Use the Lite tier"])
        self.assertEqual(found.dropped, Counter({("other", "duplicate"): 3}), "the main change, the same change under another title and the same title for another change")

    def test_at_most_the_limit_of_ways_is_kept(self):
        many = [{**LITE, "title": f"Way {n}", "change": {**LITE["change"], "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "assumed", "low": 0.1 * n, "high": 0.1 * n + 0.1}}]}}
                for n in range(1, proposals.MAX_OTHERS + 3)]
        found = checked(reduce(others=many))
        self.assertEqual([item["title"] for item in found.ways["r1"]["others"]], [f"Way {n}" for n in range(1, proposals.MAX_OTHERS + 1)])
        self.assertEqual(found.dropped, Counter({("other", "limit"): 2}))

    def test_a_finding_of_several_resources_keeps_none_of_its_ways_and_they_are_counted(self):
        found = checked(reduce(others=[LITE, REMOVE]), handles=("r1", "r2"))
        self.assertEqual((found.ways, found.dropped, found.said), ({}, Counter({("other", "group"): 2}), (0, 2)))

    def test_a_way_never_becomes_a_setting_and_never_nests_ways(self):
        nested = {**LITE, "change": {**LITE["change"], "set": [GOOD], "others": [REMOVE]}}
        found = checked(reduce(others=[nested]))
        self.assertEqual(list(found.ways["r1"]), ["others"], "no setting is made of what a way says")
        self.assertEqual(list(found.ways["r1"]["others"][0]), ["title", "givesUp", "action", "inPlace"])

    def test_nothing_is_kept_of_an_others_that_is_no_list(self):
        for text in ("Use the Lite tier", 4, {"title": "x"}, None):
            self.assertEqual(checked(reduce(others=text)), proposals.Checked({}, Counter(), (0, 0)))


class WhatTheCaseKeepsAndTheNotesSay(unittest.TestCase):
    def test_a_good_proposal_lands_in_the_facts_of_the_case_of_its_resource_and_nowhere_else(self):
        h = run(asked(reduce(set=[GOOD], others=[LITE])))
        facts = facts_of(h)
        lite = pricing.price(pricing.parse(LITE["change"]), ["r1"], invented(1), COSTS, None, meter_word).rows["r1"]
        self.assertEqual(facts[proposals.KEY], {"set": [{"path": UNITS, "from": 4, "to": 2}], "others": [
            {"title": "Use the Lite tier", "givesUp": LITE["gives_up"], "action": "switch", "inPlace": False, "lowUsd": lite.low, "highUsd": lite.high}]})
        self.assertEqual((facts["proposal"], facts["change"]["action"]), ("change", "reduce"), "the proposal word and the digest of the saving are where they were")
        self.assertEqual(facts["change"]["price"]["form"], "ratio")
        self.assertEqual([e for e in h.notes if "dropped" in e], [])

    def test_a_finding_with_nothing_proposed_has_the_facts_that_it_always_had(self):
        facts = facts_of(run(asked(reduce())))
        self.assertNotIn(proposals.KEY, facts)

    def test_a_bad_entry_never_drops_the_finding_and_the_notes_say_in_plain_words_what_was_dropped(self):
        bad = {**GOOD, "property": "otherUnits"}
        h = run(asked(reduce(set=[bad, GOOD, {**GOOD, "to": 9}], others=[{**LITE, "title": "https://evil.example"}, LITE, {**LITE, "change": {"action": "none"}}])))
        self.assertEqual((h.result.cases, h.of("investigation.finding")[0]["kept"]), (1, True))
        self.assertEqual(ways_of(h)["set"], [{"path": UNITS, "from": 4, "to": 2}])
        (note,) = [e for e in h.notes if "dropped" in e]
        self.assertEqual(note, "finding 1: code dropped 2 of 3 settings (a property that no tool showed: 1, a new value that is not a smaller number of the same kind: 1) "
                               "and 2 of 3 other ways (a title that is not plain words: 1, no action that code can read: 1)")

    def test_a_finding_whose_every_entry_is_bad_still_opens_its_case_with_no_proposal(self):
        h = run(asked(reduce(set=[{**GOOD, "from": 5}], others=[{"title": ""}])))
        self.assertEqual((h.result.cases, ways_of(h)), (1, None))
        self.assertEqual(h.of("investigation.finding")[0]["proposal"], "change")

    def test_the_resources_of_a_finding_each_keep_their_own_settings(self):
        change = {"action": "reduce", "effects": [], "set": [GOOD, {"handle": "r2", "property": UNITS, "from": 4, "to": 1}]}
        h = run(asked(change, handles=("r1", "r2")), invented(1, 2))
        self.assertEqual([ways_of(h, handle)["set"][0]["to"] for handle in ("r1", "r2")], [2, 1])

    def test_a_group_of_resources_that_is_one_case_keeps_no_proposal(self):
        handles = [f"r{n}" for n in range(1, investigate.GROUP_MIN + 2)]
        group = finding(handles=handles, basis="other", proposal="investigate", evidence=[])
        one = {"set": [{"path": UNITS, "from": 4, "to": 2}]}
        sure = proposals.Checked({handle: one for handle in handles}, Counter(), (len(handles), 0))
        with mock.patch.object(proposals, "check", return_value=sure):
            h = run(group, invented(*range(1, len(handles) + 1)))
        (case,) = h.store.cases_recent()
        self.assertIn(investigate.GROUP_FACT, case.facts, "it is the case of a group")
        self.assertNotIn(proposals.KEY, case.facts)
        with mock.patch.object(proposals, "check", return_value=sure):
            single = run(asked(reduce()))
        self.assertEqual(ways_of(single), one, "the same patch gives a single resource its proposal: it is the group that drops it")


class WhenTheCaseIsJudgedAgain(unittest.TestCase):
    def twice(self, between=lambda extras, plan: None, again=None):
        """A Watch that asks about r1 with a proposal and a price, and one eight days later that judges it again with `again` (a change that states nothing, by default) and no meter to price it by."""
        clock = Moving()
        extras = loop_for(clock)
        Harness(FakeFoundry(answer(asked(reduce(set=[GOOD], others=[LITE])))), invented(1), clock=clock, extras=extras).go()
        (plan,) = extras.store.plans_open()
        self.assertGreater(plan.saving_usd_month, 0, "it was asked with a saving that code priced")
        between(extras, plan)
        clock.advance(days=8)
        second = finding(handles=["r1"], basis="oversized", proposal="change", evidence=[entry("r1", "MetricA", 0)], **({"change": again} if again is not None else {}))
        shown = {"r1": {**metrics(MetricA=0), "properties": properties()}}
        h = Harness(FakeFoundry(answer(second)), FakeToolbox([resource(1, resource_type=GATEWAYS, cost_usd_30d=200.0)], shown), clock=clock, extras=extras)
        h.go()
        self.assertEqual(h.result.cases, 1, "it was judged again")
        return extras.store.case_get(key_of(resource(1, resource_type=GATEWAYS))).facts

    def test_the_proposal_is_kept_with_the_price_while_the_request_that_was_asked_with_it_is_open(self):
        facts = self.twice()
        self.assertEqual(facts["change"]["price"]["form"], "ratio", "the price that the person was shown is kept")
        self.assertEqual([item["path"] for item in facts[proposals.KEY]["set"]], [UNITS])
        self.assertEqual([item["title"] for item in facts[proposals.KEY]["others"]], ["Use the Lite tier"])

    def test_a_proposal_that_the_new_answer_states_itself_is_not_taken_from_the_earlier_one(self):
        facts = self.twice(again=reduce(to=1, set=[{**GOOD, "to": 1}]))
        self.assertEqual(facts[proposals.KEY]["set"], [{"path": UNITS, "from": 4, "to": 1}], "an answer that states a proposal again is the one that stands")

    def test_nothing_is_kept_for_a_case_that_no_open_request_waits_for(self):
        for label, between in (("a request that a person declined", lambda extras, plan: extras.store.plan_put(replace(plan, state="declined"))),
                               ("a request that is held back", lambda extras, plan: extras.store.plan_put(replace(plan, state="held"))),
                               ("no request", lambda extras, plan: extras.store.plans.pop(plan.plan_id))):
            with self.subTest(label):
                facts = self.twice(between)
                self.assertNotIn(proposals.KEY, facts)
                self.assertNotIn("change", facts)


class WhatTheSkepticIsShown(unittest.TestCase):
    def seen(self, h) -> dict:
        (one,) = json.loads(h.foundry.inputs()[1])["findings"]
        return one

    def test_the_settings_and_the_other_ways_that_code_kept_are_given_as_typed_data(self):
        h = run(asked(reduce(set=[GOOD, {**GOOD, "from": 5}], others=[LITE, {**REMOVE, "title": ""}])))
        one = self.seen(h)
        lite = pricing.price(pricing.parse(LITE["change"]), ["r1"], invented(1), COSTS, None, meter_word).rows["r1"]
        self.assertEqual(one["set"], [{"handle": "r1", "property": UNITS, "from": 4, "to": 2}])
        self.assertEqual(one["others"], [{"title": "Use the Lite tier", "givesUp": LITE["gives_up"], "action": "switch", "inPlace": False, "lowUsd": lite.low, "highUsd": lite.high}],
                         "what code dropped is not shown, and what it priced is its figure")
        self.assertEqual(one["proposal"], "change")

    def test_a_finding_that_proposes_neither_is_given_what_it_was_given_before(self):
        one = self.seen(run(asked(reduce())))
        self.assertNotIn("set", one)
        self.assertNotIn("others", one)

    def test_a_verdict_of_disagree_makes_the_finding_weaker_as_ever(self):
        h = Harness(FakeFoundry(answer(asked(reduce(set=[GOOD]))), verdicts(("disagree", ("The smaller number may not carry the peak.",), "No."))), invented(1), with_store=True)
        h.go()
        (case,) = h.store.cases_recent()
        self.assertEqual(case.status, "needs_human")
        self.assertEqual([item["path"] for item in case.facts[proposals.KEY]["set"]], [UNITS], "what was proposed is kept: the person sees it with the objection")

    def test_the_view_is_made_from_the_facts_of_the_cases_and_is_empty_for_a_case_with_none(self):
        facts = {proposals.KEY: {"set": [{"path": UNITS, "from": 4, "to": 2}], "others": [{"title": "Remove it", "givesUp": "", "action": "remove"}]}}
        self.assertEqual(proposals.view([("r1", facts), ("r2", {})]), {"set": [{"handle": "r1", "property": UNITS, "from": 4, "to": 2}],
                                                                     "others": [{"title": "Remove it", "givesUp": "", "action": "remove"}]})
        self.assertEqual(proposals.view([("r1", {}), ("r2", None)]), {})


class WhatTheInstructionsSay(unittest.TestCase):
    def test_the_investigator_is_told_the_shape_of_set_and_of_others_and_what_code_does_with_them(self):
        text = agents.INVESTIGATOR_INSTRUCTIONS
        for sentence in ('also state it in the change as "set":[{"handle":"r3","property":"<named exactly as a tool returned it>"', f"(the action reduce, at most {proposals.MAX_SETTINGS})",
                         f'List in "others", at most {proposals.MAX_OTHERS} and only for a finding of one resource', f"at most {proposals.MAX_TITLE} characters, plain words",
                         f"at most {proposals.MAX_GIVES_UP} characters", '"gives_up"', '"in_place"', "with that person's own rights", "name nothing in it that your tools did not show",
                         "never only from what you already know", "from what the documentation was read to say", "name one only after you found what it must still carry", "Price each one through the same forms of change",
                         "A price shows neither features nor limits, and an average hides a peak", "say in_place false when the documentation says that a smaller option needs the resource to be made again",
                         "A person reads gives_up marked as your own words, which code did not check"):
            self.assertIn(sentence, " ".join(text.split()), sentence)
        self.assertEqual(banned_in(text), [], "it names no kind of resource, no property, no limit and no option of any service")

    def test_the_instructions_name_none_of_the_invented_kinds_properties_or_words_of_these_tests(self):
        for text in (agents.INVESTIGATOR_INSTRUCTIONS, agents.SKEPTIC_INSTRUCTIONS):
            for word in (GATEWAYS, "capacityUnits", "Lite", "zoneRedundant", "gateway"):
                self.assertNotIn(word, text)

    def test_the_skeptic_is_told_to_judge_the_new_value_and_what_the_other_ways_give_up_and_to_say_so_when_it_is_not_right(self):
        text = agents.SKEPTIC_INSTRUCTIONS
        for sentence in ("set, the settings that it proposes", "others, other ways to save", "Judge whether the new value is safe given the evidence rows",
                         "whether what the other ways give up is right", "say disagree or unsure"):
            self.assertIn(sentence, text)
        self.assertEqual(banned_in(text), [])


if __name__ == "__main__":
    unittest.main()
