"""The tools of the investigator on an estate with many subscriptions (the Watch reads every subscription that its identity can read).

A call of a tool may spend `read_seconds` on reading subscriptions and then reads no more: it says how many it left (`not_read`), keeps what it read, and the next call goes on from
there. The estate here answers on a fake clock, so no test waits: every answer of Azure takes ten seconds of it."""
import json
import unittest
from unittest import mock

import support  # noqa: F401 (it puts the app on the path)
from cases import investigate
from cases import toolbox as tb
from cases.toolbox import MAX_RESULT_CHARS, Toolbox
from test_toolbox import ADDRESS, DISK, VM, Clock, Estate, ask, row, toolbox

WHY = "the time of one call for reading subscriptions was used up; call again to go on with them"


def subscription(number: int) -> str:
    return f"{number:08d}-1111-4222-8333-444444444444"


class Slow(Estate):
    """An estate whose every answer takes `seconds` of the clock that the toolbox is given."""

    def __init__(self, clock: Clock, seconds: float = 10.0):
        super().__init__()
        self.clock, self.seconds = clock, seconds

    def __call__(self, method, url, headers, data, timeout):
        self.clock.advance(self.seconds)
        return super().__call__(method, url, headers, data, timeout)


def many(count: int, seconds: float = 10.0, disks: int = 2):
    """`count` subscriptions, each with `disks` disks and cost lines (the dearest subscription is the last), and the toolbox over them with the fake clock."""
    clock = Clock()
    estate = Slow(clock, seconds)
    subs = [subscription(n + 1) for n in range(count)]
    for n, sub in enumerate(subs):
        for k in range(disks):
            estate.rows.append(row(DISK, f"d{n}-{k}", sub=sub))
            estate.cost_rows.append((sub, float(10 * (n + 1) + k), estate.rows[-1]["id"].lower(), "Storage"))
    notes: list[str] = []
    box = toolbox(estate, tuple(subs), notes)
    box.monotonic = clock
    return estate, box, subs, notes


def labels(block_list):
    return [block["subscription"] for block in block_list]


def reads_of(estate: Estate, word: str) -> dict:
    """How many calls whose address holds the word were made for each subscription."""
    found: dict[str, int] = {}
    for call in estate.paths(word):
        sub = call["path"].lower().split("/")[2]
        found[sub] = found.get(sub, 0) + 1
    return found


class WhenTheTimeOfACallIsUsedUp(unittest.TestCase):
    def test_the_default_is_forty_five_seconds_of_reading_in_one_call(self):
        self.assertEqual(tb.SUBSCRIPTION_SECONDS, 45.0)
        self.assertEqual(Toolbox(None, (), None, []).read_seconds, 45.0)

    def test_the_overview_reads_the_subscriptions_that_it_has_time_for_names_the_rest_and_the_next_call_goes_on_where_the_last_one_stopped(self):
        estate, box, subs, notes = many(10)
        first = ask(box, "estate_overview")
        self.assertEqual(labels(first["subscriptions"]), ["s1", "s2", "s3"], "20 seconds for each: the fourth would start at 60 of the 45")
        self.assertEqual(first["not_read"], {"count": 7, "first": ["s4", "s5", "s6", "s7", "s8"], "why": WHY})
        self.assertEqual(len(notes), 1)
        self.assertRegex(notes[0], r"^estate_overview: the time for reading the subscriptions \(45 seconds in one call\) was used up, so 7 were not read in this call \(")
        for sub in subs[3:6]:
            self.assertIn(sub[:8], notes[0], "the note names the first of them, eight characters of each")
        self.assertNotIn(subs[-1][:8], notes[0])

        second = ask(box, "estate_overview")
        self.assertEqual(labels(second["subscriptions"]), ["s1", "s2", "s3", "s4", "s5", "s6"], "what was read costs no time in the next call")
        self.assertEqual(second["not_read"]["count"], 4)
        self.assertEqual(second["not_read"]["first"], ["s7", "s8", "s9", "s10"])
        third = ask(box, "estate_overview")
        self.assertEqual((len(third["subscriptions"]), third["not_read"]["count"], third["not_read"]["first"]), (9, 1, ["s10"]))
        fourth = ask(box, "estate_overview")
        self.assertEqual(labels(fourth["subscriptions"]), [f"s{n}" for n in range(1, 11)])
        self.assertNotIn("not_read", fourth)
        self.assertEqual(len(notes), 3, "one note for each call that left subscriptions, and none for the call that left none")

        self.assertEqual(estate.graph_names(), ["estate-types"] * 10, "one read of the types of each subscription, in all four calls")
        self.assertEqual(sorted(reads_of(estate, "costmanagement").values()), [1] * 10, "and one read of the cost lines of each")
        block = fourth["subscriptions"][3]
        self.assertEqual((block["subscription"], block["resources"], block["cost30d"]), ("s4", 2, 81.0))

    def test_a_subscription_whose_read_failed_is_a_note_and_an_error_block_and_is_not_counted_as_unread(self):
        estate, box, subs, notes = many(4, seconds=1.0)
        estate.failures["graph"] = [None, 403, None, None]
        answer = ask(box, "estate_overview")
        self.assertEqual(answer["subscriptions"][1], {"subscription": "s2", "error": "unavailable"})
        self.assertNotIn("not_read", answer, "the time was not used up")
        self.assertEqual(len(notes), 1)
        self.assertIn(f"{subs[1][:8]}: the resources could not be read", notes[0])

    def test_the_listing_keeps_what_it_read_and_every_call_makes_progress_until_all_subscriptions_are_read_once(self):
        estate, box, subs, notes = many(10)
        totals, calls = [], 0
        while True:
            answer = ask(box, "list_resources", type=DISK)
            calls += 1
            totals.append(answer["total"])
            if "not_read" not in answer:
                break
            self.assertEqual(answer["not_read"]["why"], WHY)
            self.assertLessEqual(len(answer["not_read"]["first"]), tb.NOT_READ_SHOWN)
            self.assertLess(calls, 10, "a call that reads nothing new would loop for ever")
        self.assertEqual(totals[0], 10, "five subscriptions of two disks in the first 45 seconds")
        self.assertEqual(totals[-1], 20)
        self.assertEqual(totals, sorted(totals), "the listing grows from call to call and never loses what an earlier call read")
        self.assertEqual(estate.graph_names(), ["type-resources"] * 10, "each subscription's resources were read once")
        self.assertEqual(sorted(reads_of(estate, "costmanagement").values()), [1] * 10)
        self.assertEqual(len(notes), calls - 1)

    def test_an_answer_that_names_many_subscriptions_names_the_first_few_and_counts_the_rest(self):
        estate, box, subs, notes = many(12)
        answer = ask(box, "list_resources", type=DISK)
        self.assertEqual(len(answer["not_read"]["first"]), tb.NOT_READ_SHOWN)
        self.assertGreater(answer["not_read"]["count"], tb.NOT_READ_SHOWN)

    def test_the_advice_of_the_subscriptions_that_were_read_is_listed_and_the_next_call_reads_the_rest(self):
        estate, box, subs, notes = many(10)
        for n, sub in enumerate(subs):
            estate.advisor.append((sub, {"properties": {"category": "Cost", "impact": "Medium", "impactedField": "Microsoft.Subscriptions/subscriptions", "impactedValue": sub,
                                                        "recommendationTypeId": "11111111-1111-1111-1111-111111111111",
                                                        "extendedProperties": {"savingsCurrency": "USD", "annualSavingsAmount": str(1000 + n)},
                                                        "resourceMetadata": {"resourceId": f"/subscriptions/{sub}"}}}))
        first = ask(box, "advisor_items")
        self.assertEqual((first["total"], first["not_read"]["count"], first["not_read"]["first"]), (5, 5, ["s6", "s7", "s8", "s9", "s10"]))
        self.assertEqual([item["annual_savings"] for item in first["items"]], [1004.0, 1003.0, 1002.0, 1001.0, 1000.0])
        second = ask(box, "advisor_items")
        self.assertEqual(second["total"], 10)
        self.assertNotIn("not_read", second)
        self.assertEqual([item["annual_savings"] for item in second["items"]], [float(1000 + n) for n in range(9, -1, -1)])
        self.assertEqual(sorted(reads_of(estate, "advisor").values()), [1] * 10, "Advisor was asked once for each subscription")

    def test_the_paid_features_of_the_subscriptions_that_were_read_are_shown_and_asked_for_once_each(self):
        estate, box, subs, notes = many(10)
        estate.pricings = [(sub, {"name": "Plan", "properties": {"pricingTier": "Standard"}}) for sub in subs]
        first = ask(box, "paid_features")
        self.assertEqual(labels(first["subscriptions"]), ["s1", "s2", "s3", "s4", "s5"])
        self.assertEqual((first["not_read"]["count"], first["not_read"]["first"]), (5, ["s6", "s7", "s8", "s9", "s10"]))
        second = ask(box, "paid_features")
        self.assertEqual(labels(second["subscriptions"]), [f"s{n}" for n in range(1, 11)])
        self.assertNotIn("not_read", second)
        self.assertEqual(sorted(reads_of(estate, "pricings").values()), [1] * 10, "a subscription that was read is not read again")

    def test_the_cost_lines_come_from_the_subscriptions_that_were_read_and_the_others_are_unread_and_not_unavailable(self):
        estate, box, subs, notes = many(10)
        first = ask(box, "cost_lines")
        self.assertEqual((first["total"], first["not_read"]["count"]), (10, 5))
        self.assertNotIn("costs", first, "a subscription that was not read is not a subscription whose costs are unavailable")
        second = ask(box, "cost_lines")
        self.assertEqual(second["total"], 20)
        self.assertNotIn("not_read", second)
        self.assertEqual(sorted(reads_of(estate, "costmanagement").values()), [1] * 10)

    def test_when_the_time_is_used_up_before_any_subscription_is_read_the_cost_lines_are_unread_and_say_so(self):
        estate, box, subs, notes = many(3)
        box.read_seconds = 0.0
        answer = ask(box, "cost_lines")
        self.assertEqual(answer, {"costs": "unavailable", "lines": [], "not_read": {"count": 3, "first": ["s1", "s2", "s3"], "why": WHY}})
        self.assertEqual(estate.calls, [], "nothing was read")

    def test_the_metric_names_look_for_a_resource_of_the_type_one_subscription_after_the_other_and_remember_where_there_was_none(self):
        estate, box, subs, notes = many(10)
        estate.rows.append(row(VM, "vm-7", sub=subs[6]))
        estate.offer(VM, "Percentage CPU")
        first = ask(box, "metric_names", type=VM)
        self.assertEqual((first["total"], first["metrics"], first["not_read"]["count"]), (0, [], 5), "five subscriptions have no machine, and the time is used up before the seventh")
        self.assertEqual(estate.graph_names(), ["one-of-type"] * 5)
        second = ask(box, "metric_names", type=VM)
        self.assertEqual((second["total"], [m["name"] for m in second["metrics"]]), (1, ["Percentage CPU"]))
        self.assertNotIn("not_read", second)
        self.assertEqual(estate.graph_names(), ["one-of-type"] * 7, "the five were not looked at again: six and seven were")
        third = ask(box, "metric_names", type=VM)
        self.assertEqual(third["total"], 1)
        self.assertEqual(estate.graph_names(), ["one-of-type"] * 7, "and the names are remembered once they were found")

    def test_an_incomplete_search_is_not_remembered_as_a_type_without_metrics(self):
        estate, box, subs, notes = many(10)
        first = ask(box, "metric_names", type=VM)
        self.assertEqual((first["total"], first["not_read"]["count"]), (0, 5))
        estate.rows.append(row(VM, "vm-9", sub=subs[8]))
        estate.offer(VM, "Percentage CPU")
        second = ask(box, "metric_names", type=VM)
        self.assertEqual(second["total"], 1, "the empty answer of the first call was not kept")

    def test_a_search_that_looked_everywhere_and_found_nothing_is_remembered_and_is_not_repeated(self):
        estate, box, subs, notes = many(3, seconds=1.0)
        self.assertEqual(ask(box, "metric_names", type=VM)["total"], 0)
        self.assertEqual(ask(box, "metric_names", type=VM)["total"], 0)
        self.assertEqual(estate.graph_names(), ["one-of-type"] * 3)

    def test_the_time_of_a_call_is_its_own_and_a_tool_that_reads_no_subscription_is_never_cut(self):
        estate, box, subs, notes = many(10)
        ask(box, "estate_overview")
        box.monotonic.advance(10_000)
        again = ask(box, "list_resources", type=DISK)
        self.assertGreater(again["total"], 0, "a new call has its own forty-five seconds, however late the clock is")
        self.assertEqual(box.read_seconds, 45.0)


class WhenThereAreManySubscriptionsAndTimeIsNotShort(unittest.TestCase):
    def test_nothing_is_cut_and_nothing_is_said_about_time_with_the_real_clock(self):
        estate = Estate()
        subs = [subscription(n + 1) for n in range(8)]
        for n, sub in enumerate(subs):
            estate.rows.append(row(DISK, f"d{n}", sub=sub))
            estate.cost_rows.append((sub, float(n + 1), estate.rows[-1]["id"].lower(), "Storage"))
            estate.advisor.append((sub, {"properties": {"category": "Cost", "impact": "Low", "impactedField": "Microsoft.Subscriptions/subscriptions", "impactedValue": sub,
                                                        "recommendationTypeId": "11111111-1111-1111-1111-111111111111", "resourceMetadata": {"resourceId": f"/subscriptions/{sub}"}}}))
            estate.pricings.append((sub, {"name": "Plan", "properties": {"pricingTier": "Free"}}))
        box = toolbox(estate, tuple(subs))
        for name, arguments in (("estate_overview", {}), ("list_resources", {"type": DISK}), ("cost_lines", {}), ("advisor_items", {}), ("paid_features", {}), ("metric_names", {"type": DISK})):
            answer = ask(box, name, **arguments)
            self.assertNotIn("not_read", answer, name)
            self.assertNotIn("subscriptions_not_shown", answer, name)
        self.assertEqual(box.notes, [])

    def test_the_overview_shows_the_dearest_twenty_subscriptions_and_counts_the_others(self):
        estate, box, subs, notes = many(30, seconds=0.0)
        answer = ask(box, "estate_overview")
        shown = answer["subscriptions"]
        self.assertEqual((len(shown), answer["subscriptions_not_shown"], tb.MAX_BLOCKS), (20, 10, 20))
        self.assertEqual(labels(shown), [f"s{n}" for n in range(30, 10, -1)], "the dearest first: the subscription n costs 10 n")
        self.assertNotIn("not_read", answer)
        self.assertLessEqual(len(json.dumps(answer)), MAX_RESULT_CHARS)

    def test_the_overview_of_subscriptions_with_long_lists_drops_lists_and_then_subscriptions_and_never_fails(self):
        estate = Estate()
        subs = [subscription(n + 1) for n in range(30)]
        for sub in subs:
            for n in range(40):
                estate.rows.append(row(f"microsoft.namespace{n:02d}.something/{'longtypename' * 3}{n:02d}", f"x{n}-{sub[:8]}", sub=sub))
                estate.cost_rows.append((sub, float(n + 1), estate.rows[-1]["id"].lower(), f"Long Service Name {n % 25:02d} " + "Z" * 15))
        raw = toolbox(estate, tuple(subs)).call("estate_overview", {})
        answer = json.loads(raw)
        self.assertNotIn("error", answer)
        self.assertLessEqual(len(raw), MAX_RESULT_CHARS)
        self.assertEqual(len(answer["subscriptions"]) + answer["subscriptions_not_shown"], 30, "every subscription is shown or counted")
        self.assertGreaterEqual(answer["subscriptions_not_shown"], 10)

    def test_the_paid_features_show_the_subscriptions_with_the_most_paid_plans_and_count_the_others(self):
        estate = Estate()
        subs = [subscription(n + 1) for n in range(25)]
        for n, sub in enumerate(subs, start=1):
            estate.pricings.append((sub, {"name": "Free", "properties": {"pricingTier": "Free"}}))
            estate.pricings += [(sub, {"name": f"Paid{k}", "properties": {"pricingTier": "Standard"}}) for k in range(n % 5)]
        answer = ask(toolbox(estate, tuple(subs)), "paid_features")
        shown = labels(answer["subscriptions"])
        self.assertEqual((len(shown), answer["subscriptions_not_shown"]), (20, 5))
        left_out = {f"s{n}" for n in (5, 10, 15, 20, 25)}
        self.assertFalse(left_out & set(shown), "the five without a paid plan are the ones that are left out")

    def test_the_notes_about_subscriptions_that_could_not_be_read_are_the_first_ten_and_one_more(self):
        estate = Estate()
        subs = [subscription(n + 1) for n in range(15)]
        for sub in subs:
            estate.rows.append(row(DISK, f"d-{sub[:8]}", sub=sub))
        estate.failures["graph"] = [None] + [403] * 14
        notes: list[str] = []
        answer = ask(toolbox(estate, tuple(subs), notes), "estate_overview")
        self.assertEqual(len([block for block in answer["subscriptions"] if "error" in block]), 14)
        self.assertEqual(len(notes), tb.SUBSCRIPTION_NOTES + 1)
        self.assertEqual(sum("could not be read" in note and note[:8] in {s[:8] for s in subs} for note in notes), tb.SUBSCRIPTION_NOTES)
        self.assertTrue(notes[-1].startswith("more subscriptions could not be read"))

    def test_the_subscriptions_that_could_not_be_read_or_have_no_costs_are_named_by_label_the_first_few_and_the_rest_counted(self):
        estate = Estate()
        subs = [subscription(n + 1) for n in range(9)]
        for sub in subs:
            estate.rows.append(row(DISK, f"d-{sub[:8]}", sub=sub))
        estate.failures["costs"] = 403
        answer = ask(toolbox(estate, tuple(subs)), "list_resources", type=DISK)
        self.assertEqual(answer["costs"], "unavailable")
        self.assertNotIn("costs_unavailable", answer, "no subscription had costs: the plain word says it")
        estate = Estate()
        for sub in subs:
            estate.rows.append(row(DISK, f"d-{sub[:8]}", sub=sub))
        estate.cost_rows.append((subs[0], 1.0, estate.rows[0]["id"].lower(), "Storage"))
        estate.failures["costs"] = [None] + [403] * 8
        answer = ask(toolbox(estate, tuple(subs)), "list_resources", type=DISK)
        self.assertEqual(answer["costs_unavailable"], ["s2", "s3", "s4", "s5", "s6"])
        self.assertEqual(answer["costs_unavailable_count"], 8)


class WhenTheInvestigationBuildsTheToolbox(unittest.TestCase):
    """The time that one call may use for reading subscriptions is at most an eighth of the investigation's own time, so that a call over a large estate cannot take the time that
    the Investigator needs for its answer and the Skeptic for its verdicts."""

    def read_seconds(self, investigate_max_seconds):
        from test_investigate import FakeFoundry, Harness, make_settings
        made: list[Toolbox] = []

        class Recording(Toolbox):
            def __init__(self, *args):
                super().__init__(*args)
                made.append(self)

        harness = Harness(FakeFoundry(), settings=make_settings(investigate_max_seconds=investigate_max_seconds))
        harness.toolbox = None
        with mock.patch.object(investigate, "Toolbox", Recording):
            harness.go()
        self.assertEqual(len(made), 1)
        return made[0].read_seconds

    def test_it_is_an_eighth_of_the_budget_and_never_more_than_the_default_or_less_than_five_seconds(self):
        for budget, expected in ((600, 45.0), (420, 45.0), (360, 45.0), (300, 37.5), (120, 15.0), (40, 5.0), (8, 5.0)):
            self.assertEqual(self.read_seconds(budget), expected, budget)

    def test_the_other_toolbox_that_is_given_to_the_investigation_is_left_as_it_is(self):
        from test_investigate import FakeToolbox, Harness
        harness = Harness(toolbox=FakeToolbox())
        harness.go()
        self.assertFalse(hasattr(harness.toolbox, "read_seconds"))
