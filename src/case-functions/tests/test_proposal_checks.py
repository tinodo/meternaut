"""What the Investigator may propose for a finding, and what code keeps of it (cases/proposals.py): the settings to change (`set`) and the other ways to save (`others`).

Every kind of resource, property and word here is invented. An entry is kept only when code can compare it with what the tools showed in the same run; one that fails is dropped by itself and
counted, and the finding stays. The Skeptic is shown what was kept, and the facts of a case keep it as typed data (the words of the pages are another piece of work).
"""
import json
import re
import unittest
from collections import Counter
from dataclasses import replace
from unittest import mock

from test_investigate import (FakeFoundry, FakeToolbox, Harness, Moving, ScriptedAgent, answer, banned_in, built, disks_estate, entry, finding, key_of, loop_for, meter_line, metrics, resource,
                              verdicts)

from cases import agents, brief, investigate, models, pricing, proposals
from cases.prices import Line as Listed
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
    """What the tools showed of an invented gateway: a number that a smaller one may be stated for, a word, a flag and another count."""
    return {UNITS: 4, "tier": "Lite", "zoneRedundant": True, "maxReplicas": 8, **more}


LIMITS = {UNITS: {"lowest": 2, "highest": 50}}


def limited(limits=LIMITS, **more) -> dict:
    """The evidence of an invented gateway as `checked` takes it, with the limits that the tools showed for its properties: the units may be 2 to 50."""
    return {"r1": {"properties": properties(**more), "limits": limits}}


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


def priced_as(form: str):
    """A price that gives the resource one figure of this form of change, 20 to 40 dollars a month: the shape of a row of the bill with invented numbers."""
    row = pricing.Row("r1", 20.0, 40.0, 200.0, 1, form, {}, None, 0, ("m1",), 200.0, None, None, 0, None)
    return lambda option: pricing.Priced(option.action, {"r1": row})


def via(title: str, meter: str, price: str | None = None) -> dict:
    """Another way to save on r1: a switch of the bill line `meter` to a price of the list (by default the one that has the number of that meter), with the words that the Investigator gives it."""
    return {"title": title, "gives_up": "Fewer units.", "in_place": False,
            "change": {"action": "switch", "effects": [{"handle": "r1", "meters": [meter], "remains": {"form": "alternative", "price": price or f"p{meter[1:]}"}}], "how": "Make it again."}}


def stopped_at(reasons: dict):
    """A price that gives a way the figure of a row (20 to 40 dollars) unless `reasons` names the bill line of its effect: then it gives no figure and the word of cases/pricing.py WHY that `reasons` holds."""
    row = pricing.Row("r1", 20.0, 40.0, 200.0, 1, "alternative", {}, None, 0, ("m1",), 200.0, None, None, 0, None)

    def price(option):
        meter = option.effects[0].meters[0]
        return pricing.Priced(option.action, {} if meter in reasons else {"r1": row}, {"r1": reasons[meter]} if meter in reasons else {})

    return price


LIST = {"p1": Listed("Example Compute", "Basic Tier", "Small", "Light Hours", "1 Hour", 0.10, "swedencentral", 1),
        "p2": Listed("Example Compute", "Premium Tier", "Large", "Heavy Hours", "1 Hour", 0.50, "swedencentral", 1)}


def with_list(box: FakeToolbox) -> FakeToolbox:
    """The invented gateways of a run that also hold the list that the tool for alternatives showed for the bill line m1: the bill pays 0.28 an hour for it and the list has 0.30 for it, 0.10 for a Small
    price and 0.50 for a Large one."""
    box.prices, box.retail, box.offers = LIST, {"m1": 0.30}, {"m1": {"p1", "p2"}}
    return box


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
        box = {"r1": {"properties": properties(computeCapacity=2.5)}}
        found = checked(reduce(on="computeCapacity", start=2.5, to=1.25, set=[{"handle": "r1", "property": "computeCapacity", "from": 2.5, "to": 1.25}]), evidence=box)
        self.assertEqual(found.ways["r1"]["set"], [{"path": "computeCapacity", "from": 2.5, "to": 1.25}])
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
        names = [f"pool{letter}Count" for letter in "ABCDE"][: proposals.MAX_SETTINGS + 2]
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
        other = {"r1": {"properties": properties(maxReplicas=8)}}
        self.assertEqual(checked(reduce(on="maxReplicas", start=8, to=4, set=[{**GOOD, "to": 1}]), evidence=other).dropped, Counter(), "a ratio on another property says nothing of this one")
        two = {"r1": {"properties": properties()}, "r2": {"properties": properties()}}
        change = reduce(handle="r2", start=4, to=2, set=[{**GOOD, "to": 1}])
        self.assertEqual(checked(change, handles=("r1", "r2"), evidence=two).dropped, Counter(), "nor does a ratio of another resource")
        self.assertEqual(checked(reduce(start="four", to=2, set=[{**GOOD, "to": 1}])).dropped, Counter(), "a ratio that is no pair of numbers is no change that was priced")

    def test_the_settings_of_each_resource_are_its_own(self):
        two = {handle: {"properties": properties(**({"maxReplicas": 6} if handle == "r2" else {}))} for handle in ("r1", "r2")}
        change = {"action": "reduce", "effects": [], "set": [GOOD, {"handle": "r2", "property": "maxReplicas", "from": 6, "to": 3}]}
        found = checked(change, handles=("r1", "r2"), evidence=two)
        self.assertEqual(found.ways, {"r1": {"set": [{"path": UNITS, "from": 4, "to": 2}]}, "r2": {"set": [{"path": "maxReplicas", "from": 6, "to": 3}]}})

    def test_a_property_whose_last_key_is_no_count_or_size_is_dropped_whatever_number_the_tools_showed(self):
        shown = {"minimumTlsVersion": (1.2, 0.6), "retentionDays": (30, 0), "zonesCount": (3, 1), "ipConfigurationsCount": (2, 1), "timeoutInMinutes": (10, 5), "sku.tier": (3, 1),
                 "capacity.state": (2, 1)}
        evidence = {"r1": {"properties": properties(**{name: now for name, (now, _) in shown.items()})}}
        for name, (now, to) in shown.items():
            with self.subTest(name):
                found = checked(reduce(set=[{"handle": "r1", "property": name, "from": now, "to": to}, GOOD]), evidence=evidence)
                self.assertEqual(found.ways["r1"]["set"], [{"path": UNITS, "from": 4, "to": 2}], "the good entry stays")
                self.assertEqual((found.dropped, found.said), (Counter({("set", "count"): 1}), (2, 0)), "refused by its own rule, with every other rule met")

    def test_a_number_of_days_or_of_another_period_is_dropped_as_a_period_with_its_own_words_in_the_notes(self):
        shown = {"numberOfDays": (30, 15), "maximumNumberOfHours": (24, 12), "numberOfMonths": (12, 6), "sku.numberOfYears": (3, 1)}
        evidence = {"r1": {"properties": properties(**{name: now for name, (now, _) in shown.items()})}}
        for name, (now, to) in shown.items():
            with self.subTest(name):
                found = checked(reduce(set=[{"handle": "r1", "property": name, "from": now, "to": to}, GOOD]), evidence=evidence)
                self.assertEqual(found.ways["r1"]["set"], [{"path": UNITS, "from": 4, "to": 2}], "the good entry stays")
                self.assertEqual((found.dropped, found.said), (Counter({("set", "period"): 1}), (2, 0)), "refused by its own rule, with every other rule met")
                self.assertEqual(proposals.note_of(found), "code dropped 1 of 2 settings (a period, not a count or a size: 1)")

    def test_a_property_whose_last_key_is_a_count_or_a_size_is_kept(self):
        shown = {"scaleUnits": (4, 2), "sku.capacity": (3, 1), "instanceCount": (5, 2), "maxReplicas": (10, 3), "numberOfWorkers": (6, 3), "diskSizeGB": (128, 64), "count.count": (2, 1),
                 "numberOfSites": (7, 3)}
        for name, (now, to) in shown.items():
            with self.subTest(name):
                found = checked({"action": "reduce", "effects": [], "set": [{"handle": "r1", "property": name, "from": now, "to": to}]}, evidence={"r1": {"properties": {name: now}}})
                self.assertEqual((found.ways, found.dropped), ({"r1": {"set": [{"path": name, "from": now, "to": to}]}}, Counter()))

    def test_the_old_value_that_is_kept_is_the_one_that_the_tools_showed_and_not_the_spelling_of_the_ai(self):
        for now, said, to in ((4, 4.0, 2), (4, 4.0000001, 2), (2.5, 2.5000001, 1.25)):
            with self.subTest(now=now, said=said):
                found = checked({"action": "reduce", "effects": [], "set": [{"handle": "r1", "property": "computeCapacity", "from": said, "to": to}]},
                                evidence={"r1": {"properties": {"computeCapacity": now}}})
                (kept,) = found.ways["r1"]["set"]
                self.assertEqual(kept["from"], now)
                self.assertIs(type(kept["from"]), type(now), "an int that the tools showed stays an int, whatever the AI wrote")

    def test_nothing_is_kept_of_an_answer_with_no_change_or_a_set_that_is_no_list(self):
        self.assertEqual(proposals.check(None, "change", ["r1"], {}, lambda option: pricing.Priced("")), proposals.Checked({}, Counter(), (0, 0)))
        for text in ("capacityUnits", 4, {"handle": "r1"}, None):
            self.assertEqual(checked(reduce(set=text)), proposals.Checked({}, Counter(), (0, 0)))


class WhatCodeKeepsWithTheDocumentedRange(unittest.TestCase):
    """The limits that the tools showed for a property (the `limits` of its evidence: the lowest and highest number that Microsoft's reference page of the type gives, cases/ranges.py): a new number that lies
    outside them is a number that the platform refuses, so the setting is dropped like any other that fails a rule, with the words that name the number, and the finding stays."""

    LOWER = {**GOOD, "to": 1}

    def test_a_new_number_below_the_lowest_that_the_page_gives_is_dropped_by_itself_and_the_finding_and_the_other_entries_stay(self):
        other = {"handle": "r1", "property": "maxReplicas", "from": 8, "to": 4}
        found = checked(reduce(to=1, set=[self.LOWER, other]), evidence=limited())
        self.assertEqual(found.ways["r1"]["set"], [{"path": "maxReplicas", "from": 8, "to": 4}])
        self.assertEqual((found.dropped, found.said), (Counter({("set", "lowest 2"): 1}), (2, 0)))

    def test_a_new_number_above_the_highest_that_the_page_gives_is_dropped_the_same_way(self):
        found = checked(reduce(start=60, to=55, set=[{**GOOD, "from": 60, "to": 55}]), evidence=limited(**{UNITS: 60}))
        self.assertEqual((found.ways, found.dropped), ({}, Counter({("set", "highest 50"): 1})))

    def test_a_number_at_the_lowest_or_the_highest_or_inside_the_range_is_kept(self):
        for start, to in ((4, 2), (4, 3), (50, 50 - 1), (60, 50)):
            with self.subTest(start=start, to=to):
                found = checked(reduce(start=start, to=to, set=[{**GOOD, "from": start, "to": to}]), evidence=limited(**{UNITS: start}))
                self.assertEqual((found.ways["r1"]["set"], found.dropped), ([{"path": UNITS, "from": start, "to": to}], Counter()))

    def test_a_bound_that_the_page_does_not_give_bounds_nothing(self):
        self.assertEqual(checked(reduce(to=1, set=[self.LOWER]), evidence=limited({UNITS: {"lowest": 2}})).dropped, Counter({("set", "lowest 2"): 1}))
        self.assertEqual(checked(reduce(to=1, set=[self.LOWER]), evidence=limited({UNITS: {"highest": 50}})).dropped, Counter(), "a highest says nothing of a number below it")
        self.assertEqual(checked(reduce(to=2, set=[{**GOOD, "to": 2}]), evidence=limited({UNITS: {"lowest": 2}})).dropped, Counter())
        self.assertEqual(checked(reduce(start=60, to=55, set=[{**GOOD, "from": 60, "to": 55}]), evidence=limited({UNITS: {"lowest": 2}}, **{UNITS: 60})).dropped, Counter())

    def test_with_no_limits_for_the_property_nothing_changes_and_a_limit_of_another_property_does_not_bound_this_one(self):
        for label, evidence in (("none at all", {"r1": {"properties": properties()}}), ("an empty one", limited({})), ("another property", limited({"maxReplicas": {"lowest": 5}})),
                                ("the key of another case", limited({UNITS.upper(): {"lowest": 2}}))):
            with self.subTest(label):
                found = checked(reduce(to=1, set=[self.LOWER]), evidence=evidence)
                self.assertEqual((found.ways["r1"]["set"], found.dropped), ([{"path": UNITS, "from": 4, "to": 1}], Counter()))

    def test_the_limits_are_those_of_the_handle_and_a_resource_with_none_is_not_bounded_by_those_of_another(self):
        evidence = {"r1": {"properties": properties(), "limits": LIMITS}, "r2": {"properties": properties()}}
        found = checked({"action": "reduce", "effects": [], "set": [self.LOWER, {**self.LOWER, "handle": "r2"}]}, handles=("r1", "r2"), evidence=evidence)
        self.assertEqual((found.ways, found.dropped), ({"r2": {"set": [{"path": UNITS, "from": 4, "to": 1}]}}, Counter({("set", "lowest 2"): 1})))

    def test_limits_that_are_not_in_the_shape_never_raise_and_bound_nothing(self):
        for junk in ("x", 5, [], None, {UNITS: "x"}, {UNITS: 5}, {UNITS: []}, {UNITS: {"lowest": True, "highest": float("nan")}}, {UNITS: {"lowest": "2"}}, {UNITS: {"lowest": 2.5}},
                     {UNITS: {"lowest": None, "highest": None}}):
            with self.subTest(repr(junk)[:30]):
                found = checked(reduce(to=1, set=[self.LOWER]), evidence={"r1": {"properties": properties(), "limits": junk}})
                self.assertEqual((found.ways["r1"]["set"], found.dropped), ([{"path": UNITS, "from": 4, "to": 1}], Counter()))

    def test_the_rule_that_a_number_is_smaller_than_the_old_one_is_read_before_the_range(self):
        found = checked(reduce(set=[{**GOOD, "to": 6}]), evidence=limited())
        self.assertEqual(found.dropped, Counter({("set", "to"): 1}))

    def test_a_setting_is_never_repaired_to_the_lowest_number_that_the_page_gives(self):
        found = checked(reduce(to=1, set=[self.LOWER]), evidence=limited())
        self.assertEqual(found.ways, {}, "no entry with the number 2 is made of the one with the number 1")

    def test_the_notes_say_in_plain_words_which_number_the_page_gives(self):
        low = checked(reduce(to=1, set=[self.LOWER]), evidence=limited())
        self.assertEqual(proposals.note_of(low), "code dropped 1 of 1 setting (a new value below 2, the lowest that Microsoft's reference page gives for the setting: 1)")
        high = checked(reduce(start=60, to=55, set=[{**GOOD, "from": 60, "to": 55}]), evidence=limited(**{UNITS: 60}))
        self.assertEqual(proposals.note_of(high), "code dropped 1 of 1 setting (a new value above 50, the highest that Microsoft's reference page gives for the setting: 1)")
        both = checked(reduce(set=[self.LOWER, {"handle": "r1", "property": "maxReplicas", "from": 8, "to": 0}]),
                       evidence={"r1": {"properties": properties(), "limits": {**LIMITS, "maxReplicas": {"lowest": 1}}}})
        self.assertEqual(proposals.note_of(both), "code dropped 2 of 2 settings (a new value below 2, the lowest that Microsoft's reference page gives for the setting: 1, "
                                                  "a new value below 1, the lowest that Microsoft's reference page gives for the setting: 1)")

    def test_the_words_of_a_rule_with_no_number_are_those_of_the_table_and_a_rule_with_one_names_it(self):
        self.assertEqual(proposals.reason("set", "count"), proposals.WHY["set"]["count"])
        self.assertEqual(proposals.reason("other", "title"), proposals.WHY["other"]["title"])
        self.assertEqual(proposals.reason("set", "lowest 2"), "a new value below 2, the lowest that Microsoft's reference page gives for the setting")
        self.assertEqual(proposals.reason("set", "highest 1000"), "a new value above 1,000, the highest that Microsoft's reference page gives for the setting")
        self.assertEqual(proposals.reason("set", "lowest -1"), "a new value below -1, the lowest that Microsoft's reference page gives for the setting")

    def test_a_finding_that_states_a_number_below_the_lowest_keeps_its_case_with_no_setting_and_no_figure_and_says_why_in_the_notes(self):
        box = invented(1)
        box.evidence["r1"]["limits"] = LIMITS
        h = run(asked(reduce(to=1, set=[self.LOWER])), box)
        self.assertEqual((h.result.cases, ways_of(h)), (1, None))
        (note,) = [e for e in h.notes if "dropped" in e]
        self.assertEqual(note, "finding 1: code dropped 1 of 1 setting (a new value below 2, the lowest that Microsoft's reference page gives for the setting: 1)")
        change = facts_of(h)["change"]
        self.assertEqual((change.get("missing"), "price" in change), ("range", False), "the saving of a number that the platform refuses is not worked out either")
        self.assertIn("range", pricing.WHY)

    def test_the_same_finding_with_the_lowest_number_is_kept_with_its_setting_and_its_figure(self):
        box = invented(1)
        box.evidence["r1"]["limits"] = LIMITS
        h = run(asked(reduce(to=2, set=[GOOD])), box)
        self.assertEqual(ways_of(h)["set"], [{"path": UNITS, "from": 4, "to": 2}])
        self.assertEqual(facts_of(h)["change"]["price"]["form"], "ratio")
        self.assertEqual([e for e in h.notes if "dropped" in e], [])

    # The forms that name no property: only the setting can be held to the range, and the figure of the resource is held back with it.
    FORMS = {"assumed": {"form": "assumed", "low": 0.3, "high": 0.5}, "quantity": {"form": "quantity", "from": 720, "to": 360}}

    def stated(self, form, to):
        return {"action": "reduce", "effects": [{"handle": "r1", "meters": ["m1"], "remains": self.FORMS[form]}], "how": f"Lower the units from 4 to {to}.", "set": [{**GOOD, "to": to}]}

    def test_a_resource_whose_setting_the_range_refused_has_no_figure_whatever_the_form_and_the_finding_says_so(self):
        for form in self.FORMS:
            with self.subTest(form):
                box = invented(1)
                box.evidence["r1"]["limits"] = LIMITS
                h = run(asked(self.stated(form, 1)), box)
                self.assertEqual(h.result.cases, 1, "the finding stays and its case is opened")
                self.assertIsNone(ways_of(h))
                change = facts_of(h)["change"]
                self.assertEqual((change.get("missing"), "price" in change), ("range", False), "the figure of the resource may rest on the number that the platform refuses")
                self.assertEqual(pricing.missing(facts_of(h)), pricing.WHY["range"])
                self.assertEqual([e for e in h.notes if "dropped" in e], ["finding 1: code dropped 1 of 1 setting (a new value below 2, the lowest that Microsoft's reference page gives for the setting: 1)"])

    def test_the_words_of_how_are_the_ais_own_and_nothing_reads_them_for_a_number(self):
        box = invented(1)
        box.evidence["r1"]["limits"] = LIMITS
        h = run(asked(self.stated("quantity", 1)), box)
        self.assertEqual(facts_of(h)["change"]["how"], "Lower the units from 4 to 1.", "kept as the AI wrote it, with the number that the platform refuses in it")
        h = run(asked({**reduce(to=3), "how": "Lower the units from 4 to 1.", "effects": [{"handle": "r1", "meters": ["m1"], "remains": self.FORMS["assumed"]}]}), box)
        self.assertEqual((facts_of(h)["change"]["price"]["form"], facts_of(h)["change"]["how"]), ("assumed", "Lower the units from 4 to 1."), "no setting, so nothing to hold to the range")

    def test_the_same_finding_with_a_number_inside_the_range_or_with_no_range_shown_keeps_its_figure_whatever_the_form(self):
        for form in self.FORMS:
            for label, to, limits in (("inside", 2, LIMITS), ("no range shown", 1, None)):
                with self.subTest(form=form, case=label):
                    box = invented(1)
                    if limits is not None:
                        box.evidence["r1"]["limits"] = limits
                    h = run(asked(self.stated(form, to)), box)
                    self.assertEqual(facts_of(h)["change"]["price"]["form"], form)
                    self.assertEqual(ways_of(h)["set"], [{"path": UNITS, "from": 4, "to": to}])

    def test_the_handles_whose_setting_was_refused_for_the_range_are_named_and_no_others(self):
        evidence = {"r1": {"properties": properties(), "limits": LIMITS}, "r2": {"properties": properties(), "limits": LIMITS}, "r3": {"properties": properties()}}
        change = {"action": "reduce", "effects": [], "set": [self.LOWER, {**self.LOWER, "handle": "r2", "to": 3}, {**self.LOWER, "handle": "r3"}]}
        found = checked(change, handles=("r1", "r2", "r3"), evidence=evidence)
        self.assertEqual(found.ranged, frozenset({"r1"}), "r2 is inside the range and r3 has none shown")
        self.assertEqual(sorted(found.ways), ["r2", "r3"])
        self.assertEqual(checked(change, handles=("r2", "r3"), evidence=evidence).ranged, frozenset(), "a setting of a resource that is not the finding's is no one's")

    def test_a_setting_refused_for_another_reason_or_not_asked_for_does_not_name_its_handle(self):
        for label, bad in (("an old value that no tool showed", {**GOOD, "from": 5, "to": 1}), ("a number that is not smaller", {**GOOD, "to": 6}), ("a property that is no count", {**GOOD, "property": "tier", "to": 1}),
                           ("a resource that is not the finding's", {**GOOD, "handle": "r9", "to": 1})):
            with self.subTest(label):
                self.assertEqual(checked(reduce(set=[bad]), evidence=limited()).ranged, frozenset())
        self.assertEqual(checked(reduce(to=1, set=[self.LOWER]), proposal="investigate", evidence=limited()).ranged, frozenset(), "a finding that is not a change keeps no setting, and holds no figure back")
        self.assertEqual(checked(None).ranged, frozenset())


class WhatCodeKeepsOfTheOtherWays(unittest.TestCase):
    def test_another_way_is_priced_from_the_bill_by_its_own_change_and_kept_with_its_words(self):
        found = checked(reduce(others=[LITE, REMOVE]), price=priced_by_the_bill())
        lite, gone = (pricing.price(pricing.parse(option["change"]), ["r1"], invented(1, 2), COSTS, None, meter_word).rows["r1"] for option in (LITE, REMOVE))
        self.assertGreater(gone.low, lite.low, "removing it saves more than a smaller tier: the figures are the bill's, each from its own change")
        self.assertEqual(found.ways, {"r1": {"others": [
            {"title": "Use the Lite tier", "givesUp": LITE["gives_up"], "action": "switch", "inPlace": False, "lowUsd": lite.low, "highUsd": lite.high, "estimate": True},
            {"title": "Remove it", "givesUp": "Everything that uses it.", "action": "remove", "inPlace": True, "lowUsd": gone.low, "highUsd": gone.high}]}})
        self.assertEqual((found.dropped, found.said), (Counter(), (0, 2)))
        self.assertEqual([(o.title, o.in_place, o.low, o.high, o.estimate) for o in proposals.others({proposals.KEY: found.ways["r1"]})],
                         [("Use the Lite tier", False, lite.low, lite.high, True), ("Remove it", True, gone.low, gone.high, False)])

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
                 ("a title with an amount a month and no currency", bad_title("Saves 500/month"), "title"), ("a title with an amount a year and no currency", bad_title("Saves 500/year"), "title"),
                 ("a title with an amount and no unit", bad_title("Save 1200"), "title"), ("a title with an amount that has a comma in it", bad_title("Save 1,200"), "title"),
                 ("a title with a slash", bad_title("Lite/Basic tier"), "title"), ("a title with a colon, which loses the whole way", bad_title("Lite tier: free"), "title"),
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

    def test_a_title_may_hold_a_small_number_and_never_a_run_of_three_digits_which_is_an_amount(self):
        for title, kept in (("Halve to 2 units (4 to 2)", True), ("Use 99 units", True), ("Use 100 units", False), ("Use 1 000 units", False)):
            with self.subTest(title):
                found = checked(reduce(others=[{**LITE, "title": title}]))
                self.assertEqual([item["title"] for item in found.ways.get("r1", {}).get("others", [])], [title] if kept else [])
                self.assertEqual(found.dropped, Counter() if kept else Counter({("other", "title"): 1}))

    def test_a_way_is_an_estimate_when_its_share_that_remains_is_the_ais_word_and_it_keeps_its_figure_whatever_the_form(self):
        for form in ("assumed", "mixed", "none", "quantity", "ratio", "share_of_days", "alternative"):
            with self.subTest(form):
                found = checked(reduce(others=[LITE]), price=priced_as(form))
                (way,) = found.ways["r1"]["others"]
                says = form in ("assumed", "mixed")
                self.assertEqual((way["lowUsd"], way["highUsd"]), (20.0, 40.0), "a figure is kept for every form, an estimate or not")
                self.assertEqual(("estimate" in way, way.get("estimate")), (says, True if says else None))
                (read,) = proposals.others({proposals.KEY: found.ways["r1"]})
                self.assertEqual((read.estimate, read.low, read.high), (says, 20.0, 40.0))

    def test_the_forms_that_the_bill_prices_make_an_estimate_of_the_assumed_one_only(self):
        halve = {"title": "Halve the hours", "gives_up": "Half of the hours.", "in_place": True,
                 "change": {"action": "reduce", "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "quantity", "from": 720, "to": 360}}], "how": "Halve them."}}
        lower = {"title": "Lower the units to one", "gives_up": "Three of the four units.", "in_place": True, "change": reduce(to=1)}
        gone = {"title": "Use the free tier", "gives_up": "Everything that the free tier does not have.", "in_place": False,
                "change": {"action": "switch", "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "none"}}], "how": "Make it again on the free tier."}}
        # A switch whose effect says `none` (the new price has no counterpart for the charge) is priced as an assumed share with nothing remaining, so it is an estimate; a removal, which says the same of the
        # bill, is not: there it is the bill alone that says so.
        for way, estimate in ((LITE, True), (REMOVE, False), (halve, False), (lower, False), (gone, True)):
            with self.subTest(way["title"]):
                (kept,) = checked(reduce(others=[way]), price=priced_by_the_bill()).ways["r1"]["others"]
                self.assertEqual(("lowUsd" in kept, kept.get("estimate", False)), (True, estimate))

    def test_a_way_with_no_row_is_no_estimate_for_it_has_no_figure(self):
        (one,) = checked(reduce(others=[LITE])).ways["r1"]["others"]
        self.assertEqual(sorted(one), ["action", "givesUp", "inPlace", "title"])

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


class WhenAWayCostsAsMuchOrMore(unittest.TestCase):
    """A way that code priced and found to be no saving (the new price is not below what the charge costs now: the word `dearer` of cases/pricing.py WHY) is dropped by its own rule. A way that code could
    not price for any other reason is kept with no figure, as it always was. The prices of the first tests are made by hand, and the last tests run a whole investigation over an invented price list."""

    LARGE, SMALL = via("Use the Large tier", "m2"), via("Use the Small tier", "m3")

    def test_a_way_that_code_priced_as_no_saving_is_dropped_by_its_own_rule_counted_and_said_in_the_notes_and_the_way_that_saves_keeps_its_figure(self):
        price = stopped_at({"m2": "dearer"})
        found = checked(reduce(others=[self.LARGE, self.SMALL]), price=price)
        (kept,) = found.ways["r1"]["others"]
        self.assertEqual((kept["title"], kept["lowUsd"], kept["highUsd"]), ("Use the Small tier", 20.0, 40.0))
        self.assertEqual((found.dropped, found.said), (Counter({("other", "dearer"): 1}), (0, 2)))
        self.assertEqual(proposals.note_of(found), "code dropped 1 of 2 other ways (the new price is not below what the charge costs now: 1)")
        alone = checked(reduce(others=[self.LARGE]), price=price)
        self.assertEqual((alone.ways, alone.dropped, alone.said), ({}, Counter({("other", "dearer"): 1}), (0, 1)), "nothing of the way is kept, not even a title")

    def test_the_words_of_the_rule_are_one_plain_clause_that_the_notes_and_the_replay_both_say(self):
        words = "the new price is not below what the charge costs now"
        self.assertEqual((proposals.WHY["other"]["dearer"], proposals.reason("other", "dearer")), (words, words))
        self.assertEqual(proposals.note_of(checked(reduce(others=[self.LARGE]), price=stopped_at({"m2": "dearer"}))), f"code dropped 1 of 1 other way ({words}: 1)")

    def test_a_way_that_code_could_not_price_for_any_other_reason_is_kept_with_no_figure_whatever_the_reason(self):
        self.assertIn("dearer", pricing.WHY, "the key that the rule reads is still the app's own")
        for why in (why for why in pricing.WHY if why != "dearer"):
            with self.subTest(why=why):
                found = checked(reduce(others=[self.LARGE]), price=stopped_at({"m2": why}))
                self.assertEqual(found.ways["r1"]["others"], [{"title": "Use the Large tier", "givesUp": "Fewer units.", "action": "switch", "inPlace": False}])
                self.assertEqual(found.dropped, Counter())

    def test_a_way_that_no_bill_could_price_is_kept_with_no_figure_and_so_is_one_that_the_price_says_nothing_of(self):
        for label, price in (("a price that gives nothing, as when no bill was read", None), ("a price that has neither a row nor a reason", lambda option: pricing.Priced(option.action))):
            with self.subTest(label):
                found = checked(reduce(others=[self.LARGE]), price=price)
                self.assertEqual(([item["title"] for item in found.ways["r1"]["others"]], found.dropped), (["Use the Large tier"], Counter()))
        bare = checked(reduce(others=[self.LARGE]), price=lambda option: pricing.price(option, ["r1"], FakeToolbox([]), COSTS, None, meter_word))
        self.assertEqual(([item["title"] for item in bare.ways["r1"]["others"]], bare.dropped), (["Use the Large tier"], Counter()), "the real pricing with no meter shown is no refusal of the way")

    def test_a_way_that_costs_more_is_dropped_wherever_it_stands_among_the_ways_that_save_and_they_keep_their_order(self):
        ways = [self.LARGE, self.SMALL, via("Use the Medium tier", "m4"), via("Use the Large tier too", "m5")]
        found = checked(reduce(others=ways), price=stopped_at({"m2": "dearer", "m5": "dearer"}))
        self.assertEqual([item["title"] for item in found.ways["r1"]["others"]], ["Use the Small tier", "Use the Medium tier"])
        self.assertEqual(found.dropped, Counter({("other", "dearer"): 2}))

    def test_the_limit_counts_only_the_ways_that_are_kept_and_a_way_that_is_over_it_is_over_the_limit_whatever_it_costs(self):
        larges = [via(f"Large {n}", f"m{n}") for n in (2, 3)]
        smalls = [via(f"Small {n}", f"m{n}") for n in range(10, 11 + proposals.MAX_OTHERS)]
        found = checked(reduce(others=[larges[0], smalls[0], larges[1], *smalls[1:]]), price=stopped_at({"m2": "dearer", "m3": "dearer"}))
        self.assertEqual([item["title"] for item in found.ways["r1"]["others"]], [f"Small {n}" for n in range(10, 10 + proposals.MAX_OTHERS)], "the ways that cost more did not take a place")
        self.assertEqual(found.dropped, Counter({("other", "dearer"): 2, ("other", "limit"): 1}))
        late = checked(reduce(others=[*smalls[:proposals.MAX_OTHERS], larges[0]]), price=stopped_at({"m2": "dearer"}))
        self.assertEqual(late.dropped, Counter({("other", "limit"): 1}), "it is over the limit before it is priced")

    def test_a_way_that_was_dropped_is_no_way_that_was_kept_so_its_repeat_is_priced_again_and_its_title_stays_free(self):
        again = {**self.LARGE, "title": "Use the Large tier once more"}
        found = checked(reduce(others=[self.LARGE, again, {**self.SMALL, "title": "use THE large TIER"}]), price=stopped_at({"m2": "dearer"}))
        self.assertEqual(found.dropped, Counter({("other", "dearer"): 2}), "the repeat is as dear as the first, and is no repeat of a way that was kept")
        self.assertEqual([item["title"] for item in found.ways["r1"]["others"]], ["use THE large TIER"], "the title of a way that was dropped is free for another way")

    def test_a_way_that_costs_more_in_a_finding_of_several_resources_is_a_way_of_a_group_and_is_dropped_for_that_reason(self):
        found = checked(reduce(others=[self.LARGE, self.SMALL]), handles=("r1", "r2"), price=stopped_at({"m2": "dearer"}))
        self.assertEqual((found.ways, found.dropped), ({}, Counter({("other", "group"): 2})), "a group's ways are never priced")

    def test_the_real_pricing_over_an_invented_list_says_dearer_for_a_price_that_is_not_below_what_the_bill_pays_and_the_way_is_dropped(self):
        box = with_list(invented(1))
        price = lambda option: pricing.price(option, ["r1"], box, COSTS, None, meter_word)
        large, small = via("Use the Large tier", "m1", "p2"), via("Use the Small tier", "m1", "p1")
        self.assertEqual(price(pricing.parse(large["change"])).why, {"r1": "dearer"}, "0.50 an hour against the 0.28 that the bill pays and the 0.30 of the list")
        self.assertIn("r1", price(pricing.parse(small["change"])).rows)
        found = checked(reduce(others=[large, small]), price=price)
        self.assertEqual(([item["title"] for item in found.ways["r1"]["others"]], found.dropped), (["Use the Small tier"], Counter({("other", "dearer"): 1})))
        self.assertGreater(found.ways["r1"]["others"][0]["lowUsd"], 0)
        # 0.29 is below the list price of the line (0.30), so it saves like for like, and above what the bill pays (0.28): at list prices alone it costs more, and either end is enough
        box.prices, box.offers = {**LIST, "p3": Listed("Example Compute", "Basic Tier", "Medium", "Mid Hours", "1 Hour", 0.29, "swedencentral", 1)}, {"m1": {"p1", "p2", "p3"}}
        middle = via("Use the Medium tier", "m1", "p3")
        self.assertEqual(price(pricing.parse(middle["change"])).why, {"r1": "dearer"})
        self.assertEqual(checked(reduce(others=[middle]), price=price).dropped, Counter({("other", "dearer"): 1}))


class WhenAnInvestigationMeetsAWayThatCostsMore(unittest.TestCase):
    SMALL, LARGE = via("Use the Small tier", "m1", "p1"), via("Use the Large tier", "m1", "p2")

    def test_the_case_keeps_the_way_that_saves_with_its_figure_and_the_notes_say_what_was_dropped_and_why(self):
        h = run(asked(reduce(others=[self.LARGE, self.SMALL])), with_list(invented(1)))
        self.assertEqual(h.result.cases, 1, "the finding stays whatever its ways cost")
        (kept,) = ways_of(h)["others"]
        small = pricing.price(pricing.parse(self.SMALL["change"]), ["r1"], with_list(invented(1)), COSTS, None, meter_word).rows["r1"]
        self.assertEqual((kept["title"], kept["lowUsd"], kept["highUsd"]), ("Use the Small tier", small.low, small.high))
        self.assertEqual([e for e in h.notes if "dropped" in e], ["finding 1: code dropped 1 of 2 other ways (the new price is not below what the charge costs now: 1)"])

    def test_the_skeptic_is_shown_the_way_that_saves_and_not_the_one_that_code_found_to_cost_more(self):
        h = run(asked(reduce(others=[self.LARGE, self.SMALL])), with_list(invented(1)))
        (one,) = json.loads(h.foundry.inputs()[1])["findings"]
        self.assertEqual([way["title"] for way in one["others"]], ["Use the Small tier"])

    def test_a_finding_whose_only_way_costs_more_opens_its_case_with_no_way_at_all(self):
        h = run(asked(reduce(others=[self.LARGE])), with_list(invented(1)))
        self.assertEqual((h.result.cases, ways_of(h)), (1, None))
        self.assertEqual([e for e in h.notes if "dropped" in e], ["finding 1: code dropped 1 of 1 other way (the new price is not below what the charge costs now: 1)"])

    def test_with_no_list_shown_nothing_can_be_found_to_cost_more_and_the_way_is_kept_with_no_figure_as_before(self):
        h = run(asked(reduce(others=[self.LARGE])), invented(1))
        (kept,) = ways_of(h)["others"]
        self.assertEqual((kept["title"], "lowUsd" in kept), ("Use the Large tier", False))
        self.assertEqual([e for e in h.notes if "dropped" in e], [])


class WhatTheCaseKeepsAndTheNotesSay(unittest.TestCase):
    def test_a_good_proposal_lands_in_the_facts_of_the_case_of_its_resource_and_nowhere_else(self):
        h = run(asked(reduce(set=[GOOD], others=[LITE])))
        facts = facts_of(h)
        lite = pricing.price(pricing.parse(LITE["change"]), ["r1"], invented(1), COSTS, None, meter_word).rows["r1"]
        self.assertEqual(facts[proposals.KEY], {"set": [{"path": UNITS, "from": 4, "to": 2}], "others": [
            {"title": "Use the Lite tier", "givesUp": LITE["gives_up"], "action": "switch", "inPlace": False, "lowUsd": lite.low, "highUsd": lite.high, "estimate": True}]})
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

    def test_a_setting_that_is_no_count_is_dropped_with_its_own_words_in_the_notes_and_the_finding_stays(self):
        h = run(asked(reduce(set=[{"handle": "r1", "property": "minimumTlsVersion", "from": 1.2, "to": 1.0}])), invented(1, minimumTlsVersion=1.2))
        self.assertEqual((h.result.cases, ways_of(h)), (1, None))
        (note,) = [e for e in h.notes if "dropped" in e]
        self.assertEqual(note, "finding 1: code dropped 1 of 1 setting (a property that is not a count or a size: 1)")

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

    def test_the_case_of_a_group_that_is_judged_again_keeps_none_of_the_ways_of_the_resource_it_belongs_to(self):
        clock = Moving()
        extras = loop_for(clock)
        Harness(FakeFoundry(answer(asked(reduce(set=[GOOD], others=[LITE])))), invented(1), clock=clock, extras=extras).go()
        (plan,) = extras.store.plans_open()
        self.assertGreater(plan.saving_usd_month, 0, "r1 was asked with a saving that code priced, and its request is open")
        clock.advance(days=8)
        numbers = range(1, investigate.GROUP_MIN + 2)
        group = finding(handles=[f"r{n}" for n in numbers], basis="other", proposal="investigate", evidence=[])
        h = Harness(FakeFoundry(answer(group)), invented(*numbers), clock=clock, extras=extras)
        h.go()
        facts = extras.store.case_get(key_of(resource(1, resource_type=GATEWAYS))).facts
        self.assertIn(models.GROUP_FACT, facts, "it is the case of a group, which belongs to r1")
        self.assertEqual(facts["change"]["price"]["form"], "ratio", "what the open request was asked with stays: this run took the way that keeps it")
        self.assertNotIn(proposals.KEY, facts, "a group keeps no proposal: the settings and the ways of r1 are those of r1 alone")

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
        self.assertEqual(one["others"], [{"title": "Use the Lite tier", "givesUp": LITE["gives_up"], "action": "switch", "inPlace": False, "lowUsd": lite.low, "highUsd": lite.high, "estimate": True}],
                         "what code dropped is not shown, and what it priced is its figure, with the word that it is an estimate")
        self.assertEqual(one["proposal"], "change")

    def test_a_finding_that_proposes_neither_is_given_what_it_was_given_before(self):
        one = self.seen(run(asked(reduce())))
        self.assertNotIn("set", one)
        self.assertNotIn("others", one)

    def test_a_resource_whose_setting_the_range_refused_is_shown_with_the_word_that_says_why_it_has_no_figure(self):
        box = invented(1)
        box.evidence["r1"]["limits"] = LIMITS
        assumed = [{"handle": "r1", "meters": ["m1"], "remains": {"form": "assumed", "low": 0.3, "high": 0.5}}]
        one = self.seen(run(asked({**reduce(to=1, set=[{**GOOD, "to": 1}]), "effects": assumed}), box))
        self.assertEqual(one["change"]["effects"], [{"handle": "r1", "unpriced": "range"}])
        self.assertNotIn("set", one, "and the setting that was dropped is not shown as one")
        inside = self.seen(run(asked({**reduce(to=2, set=[GOOD]), "effects": assumed}), box))
        self.assertEqual(inside["change"]["effects"][0]["handle"], "r1")
        self.assertNotIn("unpriced", inside["change"]["effects"][0], "inside the range it has the figure that the bill gives")

    def test_a_verdict_of_disagree_makes_the_finding_weaker_as_ever(self):
        h = Harness(FakeFoundry(answer(asked(reduce(set=[GOOD]))), verdicts(("disagree", ("The smaller number may not carry the peak.",), "No."))), invented(1), with_store=True)
        h.go()
        (case,) = h.store.cases_recent()
        self.assertEqual(case.status, "needs_human")
        self.assertEqual([item["path"] for item in case.facts[proposals.KEY]["set"]], [UNITS], "what was proposed is kept: the person sees it with the objection")

    def test_a_resource_that_was_left_out_of_what_the_skeptic_is_shown_has_none_of_its_proposals_in_it(self):
        box = invented(1, 2)
        (one,) = built(box, ["r1", "r2"])
        one.items[0].lead.facts[proposals.KEY] = {"set": [{"path": UNITS, "from": 4, "to": 2}], "others": [{"title": "Use the Lite tier", "givesUp": "", "action": "switch"}]}
        one.items[1].lead.facts[proposals.KEY] = {"set": [{"path": UNITS, "from": 4, "to": 1}], "others": [{"title": "Remove it", "givesUp": "", "action": "remove"}]}
        shown = json.loads(investigate._skeptic_text([one], box, investigate.DETAIL[0]))["findings"][0]
        self.assertEqual([(item["handle"], item["to"]) for item in shown["set"]], [("r1", 2), ("r2", 1)])
        self.assertEqual([item["title"] for item in shown["others"]], ["Use the Lite tier", "Remove it"])
        left = json.loads(investigate._skeptic_text([one], box, investigate.DETAIL[0], {"r2"}))["findings"][0]
        self.assertEqual([item["handle"] for item in left["evidence"]], ["r1"])
        self.assertEqual([(item["handle"], item["to"]) for item in left["set"]], [("r1", 2)], "what was proposed for a resource that the Skeptic is not shown is not shown either")
        self.assertEqual([item["title"] for item in left["others"]], ["Use the Lite tier"])

    def test_the_view_is_made_from_the_facts_of_the_cases_and_is_empty_for_a_case_with_none(self):
        facts = {proposals.KEY: {"set": [{"path": UNITS, "from": 4, "to": 2}], "others": [{"title": "Remove it", "givesUp": "", "action": "remove"}]}}
        self.assertEqual(proposals.view([("r1", facts), ("r2", {})]), {"set": [{"handle": "r1", "property": UNITS, "from": 4, "to": 2}],
                                                                     "others": [{"title": "Remove it", "givesUp": "", "action": "remove"}]})
        self.assertEqual(proposals.view([("r1", {}), ("r2", None)]), {})

    def test_a_way_that_is_an_estimate_says_so_to_the_skeptic_and_a_way_that_is_not_says_nothing_of_it(self):
        stored = lambda estimate: {proposals.KEY: {"others": [{"title": "Use the Lite tier", "givesUp": "", "action": "switch", "lowUsd": 10.0, "highUsd": 20.0, "estimate": estimate}]}}
        self.assertIs(proposals.view([("r1", stored(True))])["others"][0]["estimate"], True)
        self.assertIn('"estimate": true', json.dumps(proposals.view([("r1", stored(True))])))
        for not_one in (False, None, "yes", 1, "true"):
            self.assertNotIn("estimate", proposals.view([("r1", stored(not_one))])["others"][0])


class WhatTheInstructionsSay(unittest.TestCase):
    def test_the_investigator_is_told_the_shape_of_set_and_of_others_and_what_code_does_with_them(self):
        text = agents.INVESTIGATOR_INSTRUCTIONS
        for sentence in ('state it inside the change too, as "set":[{"handle":"r3","property":"<named exactly as a tool returned it>"', f"(the action reduce, at most {proposals.MAX_SETTINGS})",
                         f'For a finding of one resource, list every other way that you found to save on it inside the change as "others", at most {proposals.MAX_OTHERS}',
                         f"at most {proposals.MAX_TITLE} characters of letters, digits, spaces and the marks , ( ) + - only, with no run of three digits",
                         f"at most {proposals.MAX_GIVES_UP} characters", '"gives_up"', '"in_place"', "name nothing in it that your tools did not show",
                         "never only from what you already know", "from what the documentation was read to say", "its own change, in the forms above",
                         "as the documentation says that it can be altered where it is or must be made again, else left out"):
            self.assertIn(sentence, " ".join(text.split()), sentence)
        self.assertEqual(banned_in(text), [], "it names no kind of resource, no property, no limit and no option of any service")

    def test_the_investigator_is_told_that_a_number_lies_within_the_limits_that_an_answer_shows_and_may_still_state_a_setting_where_none_is_shown(self):
        text = " ".join(agents.INVESTIGATOR_INSTRUCTIONS.split())
        for sentence in ("A number in a setting lies within the limits that an answer shows for that property.",
                         "Where none are shown you may still state the setting, and then say in how that no tool showed the lowest number that the platform takes, and nothing more about it."):
            self.assertIn(sentence, text)
        self.assertLess(text.index("name nothing in it that your tools did not show"), text.index("A number in a setting lies within the limits"))
        self.assertLess(text.index("and nothing more about it"), text.index("For a finding of one resource"), "the two sentences belong to the paragraph about set")
        for old in ("must be one that the platform takes", "is not known to you", "do not claim that the smaller number is allowed"):
            self.assertNotIn(old, text, "where no limits are shown the Investigator is not told that it knows nothing, which would read as no limits and no setting")
        self.assertEqual(banned_in(text), [], "no kind, property, limit or option is named")

    def test_the_marks_that_the_instruction_allows_in_a_title_are_the_marks_that_code_keeps(self):
        listed = re.search(r"the marks (.+?) only", agents.INVESTIGATOR_INSTRUCTIONS).group(1).split()
        self.assertEqual(listed, [",", "(", ")", "+", "-"])
        for mark in listed:
            with self.subTest(mark):
                title = f"Use a {mark} b"
                self.assertEqual([item["title"] for item in checked(reduce(others=[{**LITE, "title": title}])).ways["r1"]["others"]], [title])

    def test_the_instructions_name_none_of_the_invented_kinds_properties_or_words_of_these_tests(self):
        for text in (agents.INVESTIGATOR_INSTRUCTIONS, agents.SKEPTIC_INSTRUCTIONS):
            for word in (GATEWAYS, "capacityUnits", "Lite", "zoneRedundant", "gateway"):
                self.assertNotIn(word, text)

    def test_the_skeptic_is_told_to_judge_the_new_value_and_what_the_other_ways_give_up_and_to_say_so_when_it_is_not_right(self):
        text = agents.SKEPTIC_INSTRUCTIONS
        for sentence in ("set, the settings that it proposes", "others, other ways to save", "Judge whether the new value is safe given the evidence rows",
                         "a way marked estimate has a figure that rests on a share that the Investigator assumed", "whether what the other ways give up is right", "say disagree or unsure"):
            self.assertIn(sentence, text)
        self.assertEqual(banned_in(text), [])


if __name__ == "__main__":
    unittest.main()
