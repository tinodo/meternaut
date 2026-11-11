"""The listings of the tools through Resource Graph (cases/toolbox.py, `_graph`): one question for every subscription of the list and for no other, its pages, and what is done when it
answers an error or a limit: the subscriptions are asked one at a time, the one that cannot be read is named and never counted as having none, and a limit is not hammered.

The estate is the fake of test_toolbox.py, which pages its answers and refuses a subscription here. Nothing of this has run in Azure.
"""
import json
import unittest

import support  # noqa: F401 (it puts the app on the path)
from cases import toolbox as tb
from cases.arm import Arm
from cases.http import Client, allowed_calls
from cases.redact import Redactor
from support import NOW, TOKEN
from test_toolbox import DISK, HOSTILE, MARKERS, SUB, SUB2, Estate, ask, row

OUTSIDE = "77777777-6666-4555-8444-333333333333"  # a subscription that is not on the list of the run


class Graphed(Estate):
    """An estate whose Resource Graph pages its answers (`page` rows to a page, with a `$skipToken`), refuses a group that holds a subscription of `denied` with its status, and, when `leak`
    is set, gives the rows of every subscription whatever it was asked for."""

    def __init__(self):
        super().__init__()
        self.page, self.denied, self.leak = None, {}, False

    def graph_calls(self):
        return [c for c in self.calls if c["path"].lower().endswith("microsoft.resourcegraph/resources")]

    def _graph(self, body):
        for sub in body["subscriptions"]:
            if sub.lower() in self.denied:
                return self._refused(self.denied[sub.lower()])
        reply = super()._graph({**body, "subscriptions": [SUB, SUB2, OUTSIDE]} if self.leak else body)
        if self.page is None or reply[0] != 200:
            return reply
        rows = json.loads(reply[2])["data"]
        start = int(body["options"].get("$skipToken") or 0)
        more = start + self.page < len(rows)
        return self._json({"count": len(rows[start:start + self.page]), "data": rows[start:start + self.page], **({"$skipToken": str(start + self.page)} if more else {})})


def toolbox(estate, subs=(SUB, SUB2)):
    client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda seconds: None, jitter=lambda: 0.5)
    box = tb.Toolbox(Arm(client, lambda resource: TOKEN), tuple(subs), NOW, [])
    return box


def estate_of(*placed):
    estate = Graphed()
    for name, sub in placed:
        estate.rows.append(row(DISK, name, sub=sub))
    return estate


def listed(box, kind=DISK):
    return ask(box, "list_resources", type=kind)


class WhatItIsAskedFor(unittest.TestCase):
    def test_every_question_names_the_subscriptions_of_the_list_and_no_other_and_asks_for_no_group_of_management(self):
        estate = estate_of(("a", SUB), ("b", SUB2), ("c", OUTSIDE))
        box = toolbox(estate)
        listed(box)
        ask(box, "estate_overview")
        for call in estate.graph_calls():
            body = call["body"]
            self.assertEqual(sorted(body["subscriptions"]), sorted([SUB, SUB2]))
            self.assertEqual(set(body), {"subscriptions", "query", "options"}, "no management group and no tenant: only the subscriptions that the run was given")
            self.assertLessEqual(set(body["options"]), {"resultFormat", "$top", "$skipToken"})
        self.assertEqual(estate.graph_names(), ["type-resources", "estate-types"])

    def test_the_pages_of_one_answer_are_followed_with_the_token_of_the_page_before_and_the_rows_are_all_there(self):
        estate = estate_of(*[(f"d{n}", SUB if n % 2 else SUB2) for n in range(5)])
        estate.page = 2
        answer = listed(toolbox(estate))
        self.assertEqual(answer["total"], 5)
        self.assertEqual([c["body"]["options"].get("$skipToken") for c in estate.graph_calls()], [None, "2", "4"])
        self.assertNotIn("unavailable", answer)

    def test_a_row_of_a_subscription_that_is_not_on_the_list_is_dropped_even_when_resource_graph_gives_it(self):
        estate = estate_of(("a", SUB), ("c", OUTSIDE))
        estate.leak = True
        box = toolbox(estate)
        self.assertEqual(listed(box)["total"], 1)
        overview = ask(box, "estate_overview")
        self.assertEqual([block["subscription"] for block in overview["subscriptions"]], ["s1", "s2"])
        self.assertEqual(sum(block["resources"] for block in overview["subscriptions"]), 1)
        self.assertNotIn(OUTSIDE.lower(), json.dumps([handle.resource_id.lower() for handle in box.handles.values()]))


class WhenItAnswersAnError(unittest.TestCase):
    def test_a_group_that_is_refused_is_asked_again_one_subscription_at_a_time_and_the_whole_listing_is_there(self):
        estate = estate_of(("a", SUB), ("b", SUB2))
        estate.failures["graph:type-resources"] = [400]
        answer = listed(toolbox(estate))
        self.assertEqual((answer["total"], "unavailable" in answer), (2, False))
        self.assertEqual([sorted(c["body"]["subscriptions"]) for c in estate.graph_calls()], [sorted([SUB, SUB2]), [SUB], [SUB2]])

    def test_a_subscription_that_is_denied_is_named_and_the_others_are_listed_and_it_is_not_asked_again_in_the_run(self):
        estate = estate_of(("a", SUB), ("b", SUB2))
        estate.denied = {SUB2: 403}
        box = toolbox(estate)
        answer = listed(box)
        self.assertEqual((answer["total"], answer["unavailable"]), (1, ["s2"]))
        self.assertTrue(any("could not be read" in note for note in box.notes), box.notes)
        asked = len(estate.graph_calls())
        estate.rows.append(row("microsoft.compute/virtualmachines", "vm", sub=SUB))
        again = listed(box, "microsoft.compute/virtualmachines")
        self.assertEqual((again["total"], again["unavailable"]), (1, ["s2"]))
        self.assertEqual([c["body"]["subscriptions"] for c in estate.graph_calls()[asked:]], [[SUB]], "one question, for the subscription that can be read")

    def test_the_overview_and_the_counts_of_a_subscription_that_cannot_be_read_are_left_out_and_not_shown_as_none(self):
        estate = estate_of(("a", SUB), ("b", SUB2))
        estate.denied = {SUB2: 403}
        overview = ask(toolbox(estate), "estate_overview")
        self.assertEqual([(block["subscription"], block["resources"]) for block in overview["subscriptions"]], [("s1", 1)])
        self.assertEqual(overview["unavailable"], ["s2"])
        self.assertEqual(len(estate.paths("costmanagement/query")), 1, "no cost is read for what could not be listed")

    def test_when_no_subscription_can_be_read_the_answer_is_unavailable_and_a_single_subscription_is_not_asked_twice(self):
        estate = estate_of(("a", SUB), ("b", SUB2))
        estate.denied = {SUB: 403, SUB2: 403}
        self.assertEqual(listed(toolbox(estate)), {"error": "unavailable"})
        self.assertEqual(ask(toolbox(estate), "estate_overview"), {"error": "unavailable"})
        alone = estate_of(("a", SUB))
        alone.failures["graph"] = 403
        self.assertEqual(listed(toolbox(alone, (SUB,))), {"error": "unavailable"})
        self.assertEqual(len(alone.graph_calls()), 1)

    def test_the_metrics_of_a_type_are_not_remembered_as_none_when_a_subscription_could_not_be_read(self):
        estate = estate_of(("b", SUB2))
        estate.denied = {SUB: 403}
        estate.offer(DISK, "Composite Disk Read Bytes/sec")
        box = toolbox(estate)
        self.assertEqual(ask(box, "metric_names", type=DISK)["total"], 1)
        empty = estate_of(("x", SUB2))
        empty.denied = {SUB: 403}
        box = toolbox(empty)
        self.assertEqual(ask(box, "metric_names", type="microsoft.compute/virtualmachines")["total"], 0)
        self.assertNotIn("microsoft.compute/virtualmachines", box._without, "nothing was found where it could be read, and one subscription could not be: a later call looks again")

    def test_a_name_of_the_estate_is_still_no_text_of_an_answer_when_the_listing_was_made_by_the_fallback(self):
        estate = Graphed()
        estate.rows.append(row(DISK, "a", sub=SUB, name=HOSTILE, tags={"owner": HOSTILE}))
        estate.rows.append(row(DISK, "b", sub=SUB2))
        estate.denied = {SUB2: 403}
        box = toolbox(estate)
        text = box.call("list_resources", {"type": DISK})
        for marker in MARKERS:
            self.assertNotIn(marker, text)
        self.assertNotIn(SUB, text)


class WhenItAnswersALimit(unittest.TestCase):
    def test_a_limit_that_holds_is_asked_about_once_more_for_the_first_subscription_and_then_not_at_all(self):
        estate = estate_of(("a", SUB), ("b", SUB2))
        estate.failures["graph:type-resources"] = 429
        box = toolbox(estate)
        self.assertEqual(listed(box), {"error": "unavailable"})
        asked = [c["body"]["subscriptions"] for c in estate.graph_calls()]
        self.assertEqual(asked, [[SUB, SUB2]] * 3 + [[SUB]] * 3, "the client asked three times each: a limit is waited for, then it is given up")
        self.assertTrue(any("the limit of Resource Graph holds" in note for note in box.notes), box.notes)

    def test_a_limit_that_has_passed_when_the_subscriptions_are_asked_one_at_a_time_gives_the_whole_listing(self):
        estate = estate_of(("a", SUB), ("b", SUB2))
        estate.failures["graph:type-resources"] = [429, 429, 429]
        answer = listed(toolbox(estate))
        self.assertEqual((answer["total"], "unavailable" in answer), (2, False))

    def test_a_limit_in_the_middle_leaves_what_was_read_and_names_the_rest_without_asking_for_them(self):
        subs = (SUB, SUB2, "88888888-7777-4666-8555-444444444444")
        estate = estate_of(("a", subs[0]), ("b", subs[1]), ("c", subs[2]))
        estate.failures["graph:type-resources"] = [400, None, 429, 429, 429]  # the group fails, the first subscription is read, the second is limited
        answer = listed(toolbox(estate, subs))
        self.assertEqual((answer["total"], answer["unavailable"]), (1, ["s2", "s3"]))
        self.assertEqual([c["body"]["subscriptions"] for c in estate.graph_calls()], [list(subs), [subs[0]], [subs[1]], [subs[1]], [subs[1]]], "the third subscription is not asked for")


if __name__ == "__main__":
    unittest.main()
