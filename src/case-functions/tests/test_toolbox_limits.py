"""The limits that the tools show (cases/toolbox.py, cases/ranges.py): for a count or a size that an answer shows, the lowest and highest number that Microsoft's reference page of the type documents.

Every kind of resource, property and number here is INVENTED. The reader of the pages is a stand-in that answers from a table, or the real one over a fake web (test_ranges.py), and no test touches a network.
"""
import json
import unittest
from unittest import mock

import support  # noqa: F401  (it puts the app on the path)
from cases import http, investigate
from cases import toolbox as tb
from cases.http import Client
from cases.ranges import Range, Reader
from cases.toolbox import Toolbox
from test_investigate import FakeFoundry, FakeToolbox, Harness, answer, finding, metrics, resource
from test_ranges import BOUNDED, URL, Web, of
from test_toolbox import NOW, SUB, ask, definition, row, toolbox
from test_toolbox_depth import DepthEstate

GATEWAYS = "microsoft.example/gateways"
THINGS = "microsoft.example/things"
RANGES = {"capacityUnits": Range(2, 50), "capacity": Range(1, None), "maxReplicas": Range(None, 30), "tier": Range(1, 3), "zoneRedundant": Range(0, 1), "provisioningState": Range(1, 2)}
SAID = {"capacityUnits": {"lowest": 2, "highest": 50}, "sku.capacity": {"lowest": 1}, "maxReplicas": {"highest": 30}}
NOTE = "the documented limits of microsoft.example/gateways were not read, so no tool shows any for it"


class Fake:
    """A reader of the limits of the types: a table of what it gives for each type (None for a type that is not in it, a page that was not read), and what it was asked."""

    def __init__(self, found=None):
        self.found, self.asked = dict(found or {}), []

    def limits(self, kind):
        self.asked.append(kind)
        return self.found.get(kind)


def gateways(count=2):
    """Gateways with a count in the properties, a count in the SKU, a count that is the same for both, a word, a flag and a state, each of which a table of ranges could name."""
    estate = DepthEstate()
    estate.rows = [row(GATEWAYS, f"g{n}", properties={"capacityUnits": 6 - 2 * n, "maxReplicas": 8, "tier": "Lite", "zoneRedundant": False, "provisioningState": "Succeeded"},
                       sku={"name": "Lite", "capacity": n}) for n in range(1, count + 1)]
    estate.cost_rows = [(SUB, 200.0 - n, estate.rows[n - 1]["id"].lower(), "Example Service") for n in range(1, count + 1)]
    estate.definitions[GATEWAYS] = [definition("Day Metric", "Count", "Total")]
    return estate


def read_by(found=RANGES, notes=None, count=2):
    box = toolbox(gateways(count), notes=notes)
    box.ranges = Fake({GATEWAYS: found}) if found is not None else Fake()
    return box


class WhatTheToolsShow(unittest.TestCase):
    def test_a_listing_shows_one_limits_for_the_whole_table_for_each_count_or_size_that_it_shows_and_that_the_page_bounds(self):
        box = read_by()
        text = box.call("list_resources", {"type": GATEWAYS, "order_by": None, "limit": None, "offset": None})
        answer_ = json.loads(text)
        self.assertEqual(answer_["limits"], SAID)
        self.assertEqual(text.count('"limits"'), 1, "one mapping for the whole answer, and none for each row")
        self.assertEqual((answer_["same"]["maxReplicas"], "capacityUnits" in answer_["cols"], "sku.capacity" in answer_["cols"]), (8, True, True), "the answer is the one that it was, with the limits added")
        self.assertEqual(box.ranges.asked, [GATEWAYS])

    def test_a_property_that_is_a_word_a_flag_or_a_state_has_no_limits_whatever_the_page_says_of_its_name(self):
        shown = ask(read_by(), "list_resources", type=GATEWAYS)
        for name in ("tier", "zoneRedundant", "provisioningState"):
            self.assertIn(name, (*shown["cols"], *shown["same"]), "the property is shown")
            self.assertNotIn(name, shown["limits"])

    def test_a_number_that_is_not_a_count_or_a_size_has_no_limits_either_whatever_the_page_says_of_its_name(self):
        estate = DepthEstate()
        estate.rows = [row(THINGS, "t1", properties={"retentionDays": 30, "capacityUnits": 4})]
        estate.cost_rows = [(SUB, 10.0, estate.rows[0]["id"].lower(), "Example Service")]
        box = toolbox(estate)
        box.ranges = Fake({THINGS: {"retentionDays": Range(1, 35), "capacityUnits": Range(2, 50)}})
        shown = ask(box, "list_resources", type=THINGS)
        for name in ("retentionDays", "capacityUnits"):
            self.assertIn(name, (*shown["cols"], *shown.get("same", {})), "the property is shown")
        self.assertEqual(shown["limits"], {"capacityUnits": {"lowest": 2, "highest": 50}})

    def test_a_bound_that_the_page_does_not_give_is_left_out_and_a_property_that_the_page_does_not_name_has_no_entry(self):
        shown = ask(read_by({"capacityUnits": Range(2, None)}), "list_resources", type=GATEWAYS)
        self.assertEqual(shown["limits"], {"capacityUnits": {"lowest": 2}})
        self.assertNotIn("limits", ask(read_by({"somethingElse": Range(1, 2)}), "list_resources", type=GATEWAYS))
        self.assertNotIn("limits", ask(read_by({}), "list_resources", type=GATEWAYS), "a page that was read and bounds nothing says nothing, and is not a page that was not read")

    def test_a_resource_that_lacks_a_property_that_another_has_keeps_no_limits_for_it_in_its_evidence(self):
        estate = DepthEstate()
        estate.rows = [row(THINGS, "t1", properties={"capacityUnits": 4, "maxReplicas": 8}), row(THINGS, "t2", properties={"capacityUnits": 3})]
        estate.cost_rows = [(SUB, 20.0 - n, estate.rows[n]["id"].lower(), "Example Service") for n in range(2)]
        box = toolbox(estate)
        box.ranges = Fake({THINGS: {"capacityUnits": Range(2, 50), "maxReplicas": Range(None, 30)}})
        ask(box, "list_resources", type=THINGS)
        self.assertEqual(sorted(box.evidence["r1"]["limits"]), ["capacityUnits", "maxReplicas"])
        self.assertEqual(sorted(box.evidence["r2"]["limits"]), ["capacityUnits"], "the limit of a property that the resource does not hold in the evidence is not kept for it")

    def test_a_resource_is_described_with_the_limits_of_the_properties_that_it_shows(self):
        box = read_by()
        ask(box, "list_resources", type=GATEWAYS)
        described = ask(box, "describe", handle="r1")
        self.assertEqual(described["limits"], SAID)
        self.assertEqual(set(described["limits"]), {"capacityUnits", "sku.capacity", "maxReplicas"})
        self.assertTrue(set(described["limits"]) <= set(described["properties"]))

    def test_a_profile_shows_the_limits_in_the_part_of_each_resource(self):
        box = read_by()
        ask(box, "list_resources", type=GATEWAYS)
        first, second = ask(box, "profile", handles=["r1", "r2"])["profiles"]
        self.assertEqual((first["limits"], second["limits"]), (SAID, SAID))
        self.assertTrue(set(first["limits"]) <= set(first["properties"]))

    def test_a_profile_keeps_the_limits_with_the_properties_in_the_evidence_of_its_handles(self):
        box = read_by()
        ask(box, "list_resources", type=GATEWAYS)
        box.evidence.clear()
        ask(box, "profile", handles=["r1"])
        self.assertEqual(box.evidence["r1"]["limits"], SAID)
        self.assertTrue(set(box.evidence["r1"]["limits"]) <= set(box.evidence["r1"]["properties"]))

    def test_the_evidence_of_a_handle_holds_the_limits_next_to_its_properties_so_that_code_can_compare_a_number_with_them(self):
        box = read_by()
        ask(box, "list_resources", type=GATEWAYS)
        self.assertEqual(box.evidence["r1"]["limits"], SAID)
        self.assertEqual(box.evidence["r2"]["limits"], SAID)
        self.assertTrue(set(box.evidence["r1"]["limits"]) <= set(box.evidence["r1"]["properties"]))
        only_one = read_by()
        ask(only_one, "list_resources", type=GATEWAYS, limit=1)
        self.assertEqual(sorted(only_one.evidence), ["r1"], "the evidence is that of the handles that an answer showed")
        ask(only_one, "describe", handle="r1")
        self.assertEqual(only_one.evidence["r1"]["limits"], SAID)

    def test_a_limits_of_the_evidence_never_names_a_property_that_the_evidence_does_not_hold(self):
        box = read_by()
        ask(box, "list_resources", type=GATEWAYS)
        ask(box, "describe", handle="r1")
        ask(box, "profile", handles=["r1", "r2"])
        for block in box.evidence.values():
            self.assertTrue(set(block["limits"]) <= set(block["properties"]))

    def test_a_type_is_asked_of_the_reader_by_its_name_and_only_when_a_count_or_a_size_is_shown(self):
        box = read_by()
        ask(box, "list_resources", type=GATEWAYS)
        ask(box, "describe", handle="r1")
        ask(box, "profile", handles=["r1"])
        self.assertEqual(set(box.ranges.asked), {GATEWAYS}, "the reader keeps what it read: a page is read once in a run")
        estate = DepthEstate()
        estate.rows = [row(THINGS, "t1", properties={"tier": "Lite", "zoneRedundant": True, "provisioningState": "Succeeded"})]
        estate.cost_rows = [(SUB, 10.0, estate.rows[0]["id"].lower(), "Example Service")]
        quiet = toolbox(estate)
        quiet.ranges = Fake({THINGS: {"tier": Range(1, 3)}})
        ask(quiet, "list_resources", type=THINGS)
        ask(quiet, "describe", handle="r1")
        self.assertEqual(quiet.ranges.asked, [], "no number that is a count or a size is shown, so no page is read for it")
        self.assertEqual(quiet.notes, [])


class WhenThereIsNoReaderOrThePageWasNotRead(unittest.TestCase):
    @staticmethod
    def tools(make):
        box = make()
        listed = ask(box, "list_resources", type=GATEWAYS)
        return box, [listed, ask(box, "describe", handle="r1"), ask(box, "profile", handles=["r1"])]

    def test_a_toolbox_with_no_reader_answers_as_it_always_did(self):
        self.assertIsNone(Toolbox(None, (), NOW, []).ranges)
        notes: list[str] = []
        box, answers = self.tools(lambda: toolbox(gateways(), notes=notes))
        for shown in answers:
            self.assertNotIn('"limits"', json.dumps(shown))
        for block in box.evidence.values():
            self.assertNotIn("limits", block)
        self.assertEqual(notes, [])
        self.assertEqual(self.tools(lambda: read_by({}))[1], answers, "a reader that has read a page with no bounded number changes nothing in an answer")

    def test_a_page_that_was_not_read_says_nothing_in_the_answer_and_one_note_for_the_type_in_the_run(self):
        notes: list[str] = []
        box, answers = self.tools(lambda: read_by(None, notes))
        for shown in answers:
            self.assertNotIn("limits", shown)
        self.assertEqual([note for note in notes if "limits" in note], [NOTE], "said once, not for each call")
        for block in box.evidence.values():
            self.assertNotIn("limits", block)
        self.assertEqual(answers, self.tools(lambda: toolbox(gateways()))[1], "the answers are those of a toolbox with no reader")

    def test_another_type_that_was_not_read_has_a_note_of_its_own(self):
        estate = gateways()
        estate.rows.append(row(THINGS, "t1", properties={"instanceCount": 3}))
        estate.cost_rows.append((SUB, 5.0, estate.rows[-1]["id"].lower(), "Example Service"))
        notes: list[str] = []
        box = toolbox(estate, notes=notes)
        box.ranges = Fake()
        ask(box, "list_resources", type=GATEWAYS)
        ask(box, "list_resources", type=THINGS)
        ask(box, "list_resources", type=THINGS)
        self.assertEqual([note for note in notes if "limits" in note], [NOTE, NOTE.replace("gateways", "things")])

    def test_a_reader_that_raises_is_a_page_that_was_not_read_and_stops_no_answer(self):
        class Breaks:
            def limits(self, kind):
                raise RuntimeError("the real reader never raises")

        notes: list[str] = []
        box = toolbox(gateways(), notes=notes)
        box.ranges = Breaks()
        shown = ask(box, "list_resources", type=GATEWAYS)
        self.assertEqual(("error" in shown, "limits" in shown), (False, False))
        self.assertEqual([note for note in notes if "limits" in note], [NOTE])


class WhenAnAnswerIsCut(unittest.TestCase):
    def test_what_is_cut_from_the_properties_of_a_description_is_cut_from_its_limits_and_from_its_evidence(self):
        estate = DepthEstate()
        names = [f"unit{n:02d}Count" for n in range(30)]
        estate.rows = [row(GATEWAYS, "g1", properties={name: n + 1 for n, name in enumerate(names)})]
        estate.cost_rows = [(SUB, 10.0, estate.rows[0]["id"].lower(), "Example Service")]
        box = toolbox(estate)
        box.ranges = Fake({GATEWAYS: {name: Range(1, 100 + n) for n, name in enumerate(names)}})
        ask(box, "list_resources", type=GATEWAYS)
        with mock.patch.object(tb, "MAX_RESULT_CHARS", 1500):
            shown = ask(box, "describe", handle="r1")
        self.assertLess(len(shown["properties"]), 30, "some of the properties were cut to fit the cap")
        self.assertEqual(set(shown["limits"]), set(shown["properties"]), "and the limits of what was cut with them")
        self.assertEqual(set(box.evidence["r1"]["limits"]) - set(box.evidence["r1"]["properties"]), set())
        self.assertEqual(set(box.evidence["r1"]["limits"]), set(shown["limits"]))

    def test_the_fit_of_a_picture_takes_the_limits_of_a_property_with_the_property(self):
        part = {"properties": {"aCount": 1, "bCount": 2, "cCount": 3}, "limits": {"aCount": {"lowest": 1}, "bCount": {"lowest": 1}, "cCount": {"lowest": 1}}}
        Toolbox._fit(part, [(part["properties"], part, "properties")], cap=len(tb._dump(part)) - 5)
        self.assertEqual((list(part["properties"]), list(part["limits"]), part["properties_not_shown"]), (["aCount", "bCount"], ["aCount", "bCount"], 1))


class WhatTheToolsSayThatItIs(unittest.TestCase):
    SPECS = {spec.name: spec for spec in tb.SPECS}

    def test_the_description_of_describe_says_what_limits_are_and_that_none_is_not_the_same_as_none_read(self):
        text = " ".join(self.SPECS["describe"].description.split())
        for words in ("limits", "lowest and highest number", "Microsoft's reference page", "no limits entry", "none that was read", "not the same as none"):
            self.assertIn(words, text)

    def test_the_other_two_tools_that_show_it_say_so_and_none_of_the_descriptions_names_a_kind_a_property_or_a_number_of_a_service(self):
        for name in ("list_resources", "profile"):
            self.assertIn("limits", self.SPECS[name].description)
        for spec in tb.SPECS:
            for word in ("capacityUnits", "scaleUnits", "Bastion", "bastion", "gateways", "Min value", "Max value"):
                self.assertNotIn(word, spec.description + json.dumps(spec.parameters), spec.name)
        self.assertEqual([spec.name for spec in tb.SPECS if "Microsoft's reference page" in spec.description], ["describe"], "what limits are is said once, where the properties are described")


class WithTheRealReader(unittest.TestCase):
    def test_the_page_of_a_type_is_read_once_and_its_ranges_are_shown_by_the_tools(self):
        web = Web({URL: (200, of(("capacityUnits", "The units.", BOUNDED), ("capacity", "The capacity.", "int"), ("maxReplicas", "The most.", "int <br><br>Constraints:<br>Max value = 30")))})
        client = Client(http.docs_calls(), lambda text: text, transport=web, sleep=lambda s: None)
        box = toolbox(gateways())
        box.ranges = Reader(client)
        listed = ask(box, "list_resources", type=GATEWAYS)
        self.assertEqual(listed["limits"], {"capacityUnits": {"lowest": 2, "highest": 50}, "maxReplicas": {"highest": 30}})
        ask(box, "describe", handle="r1")
        ask(box, "profile", handles=["r2"])
        self.assertEqual(len(web.calls), 1, "one page for one type in one run")
        self.assertEqual(box.evidence["r1"]["limits"], {"capacityUnits": {"lowest": 2, "highest": 50}, "maxReplicas": {"highest": 30}})

    def test_a_page_that_cannot_be_read_is_one_note_and_no_field(self):
        web = Web({})
        client = Client(http.docs_calls(), lambda text: text, transport=web, sleep=lambda s: None)
        notes: list[str] = []
        box = toolbox(gateways(), notes=notes)
        box.ranges = Reader(client)
        self.assertNotIn("limits", ask(box, "list_resources", type=GATEWAYS))
        ask(box, "describe", handle="r1")
        self.assertEqual([note for note in notes if "limits" in note], [NOTE])
        self.assertEqual(len(web.calls), 1)


class TheInvestigationGivesTheToolboxItsReader(unittest.TestCase):
    def built(self, docs="absent"):
        made: list[Toolbox] = []

        class Recording(Toolbox):
            def __init__(self, *args):
                super().__init__(*args)
                made.append(self)

        harness = Harness(FakeFoundry(answer(finding(handles=["r1"]))), FakeToolbox([resource(1)], {"r1": metrics(MetricA=0)}))
        harness.toolbox = None
        if docs != "absent":
            harness.s.docs = docs
        with mock.patch.object(investigate, "Toolbox", Recording):
            harness.go()
        self.assertEqual(len(made), 1)
        return made[0]

    def test_the_toolbox_that_the_investigation_builds_gets_a_reader_made_on_the_docs_client_of_the_run(self):
        client = Client(http.docs_calls(), lambda text: text, transport=Web({}), sleep=lambda s: None)
        tools = self.built(client)
        self.assertIsInstance(tools.ranges, Reader)
        self.assertIs(tools.ranges.docs, client)
        self.assertIsNotNone(client.deadline, "no read of a page goes on past the end of the investigation, as no call of the Watch does")

    def test_a_run_with_no_docs_client_gives_it_none_and_the_tools_answer_as_they_did(self):
        self.assertIsNone(self.built().ranges)
        self.assertIsNone(self.built(None).ranges)

    def test_the_reader_has_the_clock_of_the_run_so_that_a_toolbox_with_no_clock_of_its_own_stops_nothing(self):
        client = Client(http.docs_calls(), lambda text: text, transport=Web({}), sleep=lambda s: None)
        fake = FakeToolbox([resource(1)], {"r1": metrics(MetricA=0)})
        harness = Harness(FakeFoundry(answer(finding(handles=["r1"]))), fake)
        harness.toolbox, harness.s.docs = None, client
        self.assertFalse(hasattr(fake, "monotonic"))
        with mock.patch.object(investigate, "Toolbox", lambda *args: fake):
            summary = harness.go()
        reader = getattr(fake, "ranges", None)
        self.assertIsNotNone(reader, summary.note)
        self.assertIs(reader.monotonic, harness.s.monotonic)


if __name__ == "__main__":
    unittest.main()
