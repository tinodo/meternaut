"""The daily cost of the cases that have an open plan (cases/run.py: read_cost_series, the last step of a Watch), which the start page draws for each request. Everything in it is INVENTED.

The first classes call the step with a fake of Cost Management by day and a store in memory; the last runs whole Watches against the fake estate, so that the real client, the real
list of calls and the real query are in the test.
"""
import datetime as dt
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

from support import NOW, SUBSCRIPTION, FakeEstate, run_watch

from cases import run
from cases.detectors import Context
from cases.http import HttpError
from cases.memory_store import MemoryStore, stamp
from cases.models import GROUP_FACT, CaseRecord, StoreError
from cases.redact import Redactor
from test_run_loop import Moving, estate_with, loop_for, watch
from test_web_support import make_case, make_plan

OTHER = "cccccccc-3333-4444-8555-666666666666"  # a second subscription
DAY = dt.timedelta(days=1)
LAST, FIRST = dt.date(2026, 11, 3), dt.date(2026, 10, 5)  # the thirty closed days of a run at support.NOW


def rid(n: int, sub: str = SUBSCRIPTION) -> str:
    """The id of an invented private endpoint, in the mixed case that Resource Graph gives."""
    return f"/subscriptions/{sub}/resourceGroups/rg-{n % 3}/providers/Microsoft.Network/privateEndpoints/pe-{n:03d}"


def open_case(store, n: int, sub: str = SUBSCRIPTION, **changes) -> CaseRecord:
    """A case with an open plan, in the store."""
    case = make_case(case_id=f"k{n:03d}", resource_id=rid(n, sub), resource_name=f"pe-{n:03d}", subscription_id=sub, plan_id=f"p{n:03d}", status="needs_human", **changes)
    store.case_put(case)
    store.plan_put(make_plan(plan_id=f"p{n:03d}", case_id=case.case_id, resource_id=case.resource_id, state="open"))
    return case


def group_case(store, n: int, members: list[str], **changes) -> CaseRecord:
    """The case of a group that stands for `members` (resource ids), with an open plan."""
    ids = sorted(member.lower() for member in members)
    together = {"count": len(ids), "costUsd30d": 1.0, "type": "microsoft.network/privateendpoints", "groups": 1, "names": [], "capped": 0, "silenced": 0, "members": [], "resourceIds": ids}
    return open_case(store, n, facts={GROUP_FACT: together}, **changes)


class FakeCosts:
    """Cost Management by day, as Arm.cost_days gives it. `days` maps a resource id in lower case to {a day: its cost}; `odd` maps one to the currency that it is billed in. Every query is
    kept in `queries`. `fail` is raised by every query, or, as a dict, by the query of that number (the first is 0). `during` is called while a query is answered."""

    def __init__(self, days=None, currency="USD", odd=None, fail=None, during=None):
        self.days, self.currency, self.odd, self.fail, self.during, self.queries = days or {}, currency, odd or {}, fail, during, []

    def cost_days(self, subscription, start, end, *, amortized=False, where=None):
        self.queries.append((subscription, start, end, where))
        if self.during:
            self.during()
        error = self.fail.get(len(self.queries) - 1) if isinstance(self.fail, dict) else self.fail
        if error:
            raise error
        return [(day, resource.lower(), cost, self.odd.get(resource.lower(), self.currency)) for resource in where[1] for day, cost in self.days.get(resource.lower(), {}).items()]

    def asked(self) -> list[tuple]:
        """What each query asked for: (subscription, how many ids)."""
        return [(query[0], len(query[3][1])) for query in self.queries]


def read(store, costs, contexts=None, now=NOW) -> list[str]:
    """One run of the step. Returns what it told the History."""
    said: list[str] = []
    run.read_cost_series(SimpleNamespace(extras=SimpleNamespace(store=store), arm=costs, clock=lambda: now, redact=Redactor()), contexts or {}, said.append)
    return said


def store_of() -> MemoryStore:
    return MemoryStore(clock=lambda: NOW)


class TheSeriesOfOneCase(unittest.TestCase):
    def setUp(self):
        self.store = store_of()
        self.case = open_case(self.store, 1)

    def test_the_days_of_these_tests_are_the_thirty_closed_days_before_the_day_of_the_run(self):
        self.assertEqual((FIRST, LAST), ((NOW - 30 * DAY).date(), (NOW - DAY).date()))

    def test_thirty_closed_days_oldest_first_ending_yesterday_in_dollars_with_zero_for_a_day_without_a_cost_line(self):
        costs = FakeCosts({rid(1).lower(): {LAST: 1.25, LAST - DAY: 2.0, FIRST: 0.5}})
        self.assertEqual(read(self.store, costs), [])
        got = self.store.case_get(self.case.case_id)
        self.assertEqual(len(got.cost_series), 30)
        self.assertEqual((got.cost_series[0], got.cost_series[28], got.cost_series[29], got.cost_series_end), (0.5, 2.0, 1.25, "2026-11-03"))
        self.assertEqual(sum(got.cost_series), 3.75, "every other day is zero")
        self.assertTrue(all(isinstance(value, float) for value in got.cost_series))
        self.assertEqual(replace(got, cost_series=None, cost_series_end=None), self.case, "the step changes nothing else of the case: not its status and not the time that it was judged")

    def test_one_query_for_the_resource_over_the_thirty_closed_days_with_its_id_in_lower_case(self):
        costs = FakeCosts()
        read(self.store, costs)
        self.assertEqual(costs.queries, [(SUBSCRIPTION, FIRST, LAST, ("ResourceId", (rid(1).lower(),)))])
        self.assertEqual((LAST - FIRST).days + 1, run.COST_DAYS)

    def test_a_resource_with_no_cost_line_at_all_is_thirty_zeros(self):
        read(self.store, FakeCosts())
        got = self.store.case_get(self.case.case_id)
        self.assertEqual((got.cost_series, got.cost_series_end), ([0.0] * 30, "2026-11-03"))

    def test_the_figures_are_rounded_to_a_hundredth_of_a_cent_and_never_to_minus_zero(self):
        read(self.store, FakeCosts({rid(1).lower(): {LAST: 0.0049, LAST - DAY: 1.23456789, LAST - 2 * DAY: -0.00001}}))
        got = self.store.case_get(self.case.case_id)
        self.assertEqual(got.cost_series[27:], [0.0, 1.2346, 0.0049])
        self.assertNotIn("-0.0", got.to_json())

    def test_a_day_that_is_not_one_of_the_thirty_is_left_out(self):
        read(self.store, FakeCosts({rid(1).lower(): {FIRST - DAY: 9.0, LAST + DAY: 8.0, LAST: 1.0}}))
        got = self.store.case_get(self.case.case_id)
        self.assertEqual((len(got.cost_series), sum(got.cost_series)), (30, 1.0))


class TheSeriesOfAGroup(unittest.TestCase):
    def setUp(self):
        self.store = store_of()

    def test_a_group_case_is_the_sum_of_its_members_for_each_day(self):
        members = [rid(n) for n in range(1, 5)]
        group = group_case(self.store, 1, members)
        costs = FakeCosts({members[0].lower(): {LAST: 0.1, FIRST: 5.0}, members[1].lower(): {LAST: 0.2}, members[2].lower(): {LAST: 0.3}, members[3].lower(): {LAST: 0.4}})
        self.assertEqual(read(self.store, costs), [])
        got = self.store.case_get(group.case_id)
        self.assertEqual((got.cost_series[0], got.cost_series[29], got.cost_series_end), (5.0, 1.0, "2026-11-03"))
        self.assertEqual(sum(got.cost_series), 6.0)
        self.assertEqual(costs.queries, [(SUBSCRIPTION, FIRST, LAST, ("ResourceId", tuple(sorted(member.lower() for member in members))))], "one query for all of them")

    def test_a_group_of_two_subscriptions_is_read_with_a_query_for_each_and_summed(self):
        members = [rid(1), rid(2, OTHER)]
        group = group_case(self.store, 1, members)
        costs = FakeCosts({members[0].lower(): {LAST: 1.5}, members[1].lower(): {LAST: 2.0}})
        read(self.store, costs)
        self.assertEqual((costs.asked(), self.store.case_get(group.case_id).cost_series[29]), ([(SUBSCRIPTION, 1), (OTHER, 1)], 3.5))

    def test_ids_are_asked_for_fifty_at_a_time_for_each_subscription(self):
        self.assertEqual((run.COST_DAYS, run.COST_IDS), (30, 50))
        members = [rid(n) for n in range(1, 121)]
        group = group_case(self.store, 1, members)
        costs = FakeCosts({member.lower(): {LAST: 1.0} for member in members})
        read(self.store, costs)
        self.assertEqual(costs.asked(), [(SUBSCRIPTION, 50), (SUBSCRIPTION, 50), (SUBSCRIPTION, 20)])
        self.assertEqual([found for query in costs.queries for found in query[3][1]], sorted(member.lower() for member in members), "every id once, in order")
        self.assertEqual(self.store.case_get(group.case_id).cost_series[29], 120.0, "a case of many chunks is the sum of all of them")

    def test_cases_share_the_queries_of_their_subscription(self):
        for n in range(1, 4):
            open_case(self.store, n)
        for n in range(4, 6):
            open_case(self.store, n, OTHER)
        costs = FakeCosts()
        read(self.store, costs)
        self.assertEqual(costs.asked(), [(SUBSCRIPTION, 3), (OTHER, 2)])

    def test_a_resource_that_two_cases_have_is_asked_for_once_and_counts_in_both(self):
        group = group_case(self.store, 1, [rid(1), rid(2)])
        single = open_case(self.store, 2)
        costs = FakeCosts({rid(2).lower(): {LAST: 4.0}, rid(1).lower(): {LAST: 1.0}})
        read(self.store, costs)
        self.assertEqual(costs.asked(), [(SUBSCRIPTION, 2)])
        self.assertEqual((self.store.case_get(group.case_id).cost_series[29], self.store.case_get(single.case_id).cost_series[29]), (5.0, 4.0))

    def test_a_group_that_did_not_keep_all_its_resource_ids_is_not_read_and_nothing_is_said(self):
        older = open_case(self.store, 1, facts={GROUP_FACT: {"count": 6, "members": ["0123456789ab"] * 6}})
        short = group_case(self.store, 2, [rid(n) for n in range(1, 6)])
        short = replace(short, facts={GROUP_FACT: {**short.facts[GROUP_FACT], "count": 6}})
        self.store.case_put(short)
        bad = open_case(self.store, 3, facts={GROUP_FACT: {"count": 2, "resourceIds": [rid(1), 5]}})
        costs = FakeCosts()
        self.assertEqual(read(self.store, costs), [])
        self.assertEqual(costs.queries, [])
        self.assertEqual([self.store.case_get(case.case_id).cost_series for case in (older, short, bad)], [None, None, None])


class WhatIsRead(unittest.TestCase):
    def setUp(self):
        self.store = store_of()

    def test_a_case_without_an_open_plan_is_not_read(self):
        self.store.case_put(make_case(case_id="k100", resource_id=rid(100), subscription_id=SUBSCRIPTION, plan_id=None, status="proposed"))
        for number, state in enumerate(("declined", "expired", "consumed", "withdrawn", "failed"), 101):
            case = open_case(self.store, number)
            self.store.plan_put(replace(self.store.plan_get(case.plan_id), state=state))
        costs = FakeCosts()
        self.assertEqual(read(self.store, costs), [])
        self.assertEqual(costs.queries, [])
        self.assertEqual(len(self.store.cases_recent()), 6)
        self.assertTrue(all(case.cost_series is None for case in self.store.cases_recent()))

    def test_an_approved_plan_that_is_not_done_yet_is_open_too(self):
        case = open_case(self.store, 1)
        self.store.plan_put(replace(self.store.plan_get(case.plan_id), state="approved"))
        read(self.store, FakeCosts())
        self.assertIsNotNone(self.store.case_get(case.case_id).cost_series)

    def test_a_plan_of_a_case_that_is_gone_is_left_alone(self):
        self.store.plan_put(make_plan(plan_id="p-lost", case_id="k-lost"))
        costs = FakeCosts()
        self.assertEqual(read(self.store, costs), [])
        self.assertEqual(costs.queries, [])

    def test_no_query_is_made_when_nothing_needs_a_read(self):
        costs = FakeCosts()
        self.assertEqual((read(self.store, costs), costs.queries), ([], []), "no case at all")
        case = open_case(self.store, 1, cost_series=[1.5] * 30, cost_series_end="2026-11-03")
        self.assertEqual((read(self.store, costs), costs.queries), ([], []), "a series that ends yesterday")
        self.assertEqual(self.store.case_get(case.case_id), case)

    def test_a_series_that_does_not_end_yesterday_or_has_not_thirty_days_is_read_again(self):
        for number, (series, end) in enumerate((([9.0] * 30, "2026-11-02"), ([9.0] * 29, "2026-11-03"), ([9.0] * 30, None), (None, "2026-11-03"), ([9.0] * 30, "garbage")), 1):
            with self.subTest(end=end, days=len(series or ())):
                case = open_case(self.store, number, cost_series=series, cost_series_end=end)
                read(self.store, FakeCosts({rid(number).lower(): {LAST: 2.0}}))
                got = self.store.case_get(case.case_id)
                self.assertEqual((len(got.cost_series), got.cost_series[29], got.cost_series_end), (30, 2.0, "2026-11-03"))

    def test_a_series_is_read_again_the_next_day_and_never_twice_in_one_day(self):
        case = open_case(self.store, 1)
        costs = FakeCosts({rid(1).lower(): {LAST: 1.0, LAST + DAY: 7.0}})
        read(self.store, costs)
        read(self.store, costs, now=NOW + dt.timedelta(hours=8))
        self.assertEqual(len(costs.queries), 1, "the same day")
        read(self.store, costs, now=NOW + dt.timedelta(days=1))
        got = self.store.case_get(case.case_id)
        self.assertEqual((len(costs.queries), got.cost_series[28:], got.cost_series_end), (2, [1.0, 7.0], "2026-11-04"))
        self.assertEqual(costs.queries[1][1:3], (FIRST + DAY, LAST + DAY))

    def test_the_day_is_the_utc_day(self):
        case = open_case(self.store, 1)
        late = dt.datetime(2026, 11, 4, 23, 30, tzinfo=dt.timezone(dt.timedelta(hours=-3)))  # 02:30 on the 5th in UTC
        read(self.store, FakeCosts(), now=late)
        self.assertEqual(self.store.case_get(case.case_id).cost_series_end, "2026-11-04")

    def test_a_person_who_answered_while_the_cost_was_read_keeps_the_answer(self):
        case = open_case(self.store, 1)
        costs = FakeCosts({rid(1).lower(): {LAST: 3.0}}, during=lambda: self.store.case_put(replace(self.store.case_get(case.case_id), status="approved", updated_at=stamp(NOW))))
        read(self.store, costs)
        got = self.store.case_get(case.case_id)
        self.assertEqual((got.status, got.updated_at, got.cost_series[29]), ("approved", stamp(NOW), 3.0))

    def test_without_the_loop_there_is_nothing_to_read(self):
        said: list[str] = []
        costs = FakeCosts()
        run.read_cost_series(SimpleNamespace(extras=None, arm=costs, clock=lambda: NOW, redact=Redactor()), {}, said.append)
        self.assertEqual((said, costs.queries), ([], []))


class WhenTheCostCannotBeRead(unittest.TestCase):
    def setUp(self):
        self.store = store_of()
        self.case = open_case(self.store, 1, cost_series=[4.0] * 30, cost_series_end="2026-11-02")  # an earlier day's: it is read again

    def kept(self, case=None):
        return self.store.case_get((case or self.case).case_id)

    def test_a_currency_that_is_not_dollars_leaves_the_old_value_and_is_said_once(self):
        said = read(self.store, FakeCosts({rid(1).lower(): {LAST: 3.0}}, currency="EUR"))
        self.assertEqual(self.kept(), self.case)
        self.assertEqual(said, ["the daily cost of 1 open request could not be read (the cost lines are not in US dollars); what was read before stays"])

    def test_a_case_that_never_had_a_series_stays_without_one_in_another_currency(self):
        fresh = open_case(self.store, 2)
        read(self.store, FakeCosts({rid(2).lower(): {LAST: 3.0}}, currency="GBP"))
        self.assertEqual((self.kept(fresh).cost_series, self.kept(fresh).cost_series_end), (None, None))

    def test_one_resource_in_another_currency_makes_the_whole_answer_mixed_and_leaves_none(self):
        members = [rid(n) for n in range(2, 5)]
        group = group_case(self.store, 2, members)
        said = read(self.store, FakeCosts({member.lower(): {LAST: 1.0} for member in members}, odd={members[1].lower(): "EUR"}))
        self.assertIsNone(self.kept(group).cost_series)
        self.assertEqual(len(said), 1)

    def test_a_subscription_whose_cost_lines_this_run_found_to_be_in_another_currency_is_not_asked_and_nothing_is_said(self):
        for currency in ("EUR", "mixed"):
            costs = FakeCosts()
            self.assertEqual(read(self.store, costs, {SUBSCRIPTION: Context(currency=currency)}), [], currency)
            self.assertEqual((costs.queries, self.kept()), ([], self.case), "the Watch said so already")

    def test_a_subscription_with_dollars_or_with_no_known_currency_is_asked(self):
        for known in ({SUBSCRIPTION: Context(currency="USD")}, {SUBSCRIPTION: Context()}, {}):
            with self.subTest(known=known):
                store = store_of()
                case = open_case(store, 1)
                costs = FakeCosts()
                read(store, costs, known)
                self.assertEqual((len(costs.queries), store.case_get(case.case_id).cost_series_end), (1, "2026-11-03"))

    def test_a_group_with_a_resource_in_a_subscription_that_is_not_in_dollars_is_not_asked_at_all(self):
        group = group_case(self.store, 2, [rid(5), rid(6, OTHER)])
        costs = FakeCosts()
        read(self.store, costs, {OTHER: Context(currency="EUR")})
        self.assertEqual(costs.asked(), [(SUBSCRIPTION, 1)], "the single case is asked about, and no resource of the group")
        self.assertIsNone(self.kept(group).cost_series)

    def test_an_error_of_azure_leaves_the_old_value_and_is_said_once_with_what_azure_said(self):
        said = read(self.store, FakeCosts(fail=HttpError(500, "POST management.azure.com: 500 InternalServerError: boom")))
        self.assertEqual(self.kept(), self.case)
        self.assertEqual(said, ["the daily cost of 1 open request could not be read (POST management.azure.com: 500 InternalServerError: boom); what was read before stays"])

    def test_an_answer_that_the_app_does_not_understand_is_an_error_like_any_other(self):
        said = read(self.store, FakeCosts(fail=HttpError(200, "Cost Management gave an answer that the app does not understand")))
        self.assertEqual((self.kept(), len(said)), (self.case, 1))

    def test_a_limit_stops_the_step_at_the_first_query_and_every_case_keeps_what_it_had(self):
        group = group_case(self.store, 2, [rid(n) for n in range(10, 130)])  # with the first case 121 ids in one subscription: three queries, and one more for the other
        far = open_case(self.store, 3, OTHER)
        costs = FakeCosts(fail=HttpError(429, "POST management.azure.com: 429 Throttled: slow down", 30.0))
        said = read(self.store, costs)
        self.assertEqual(len(costs.queries), 1, "four queries were due: no loop of retries and no second try")
        self.assertEqual((self.kept(), self.kept(group).cost_series, self.kept(far).cost_series), (self.case, None, None))
        self.assertEqual(said, ["the daily cost of 3 open requests could not be read (POST management.azure.com: 429 Throttled: slow down); what was read before stays"])

    def test_another_error_goes_on_with_the_other_queries_and_only_a_case_with_all_its_resources_is_updated(self):
        group = group_case(self.store, 2, [rid(n) for n in range(10, 70)])  # with the first case 61 ids: a query of 50 and one of 11
        far = open_case(self.store, 3, OTHER)
        costs = FakeCosts({rid(3, OTHER).lower(): {LAST: 6.0}}, fail={1: HttpError(403, "POST management.azure.com: 403 AuthorizationFailed: no right")})
        said = read(self.store, costs)
        self.assertEqual(costs.asked(), [(SUBSCRIPTION, 50), (SUBSCRIPTION, 11), (OTHER, 1)], "the query after the one that failed was made")
        self.assertEqual((self.kept(far).cost_series[29], self.kept(self.case).cost_series_end, self.kept(group).cost_series), (6.0, "2026-11-03", None))
        self.assertEqual(said, ["the daily cost of 1 open request could not be read (POST management.azure.com: 403 AuthorizationFailed: no right); what was read before stays"])

    def test_a_fault_that_nobody_expected_is_said_and_never_raised(self):
        said = read(self.store, FakeCosts(fail=ValueError("a row that is not a row")))
        self.assertEqual((self.kept(), said), (self.case, ["the daily cost of the open requests could not be read (ValueError: a row that is not a row)"]))

    def test_a_secret_in_an_error_is_redacted(self):
        said = read(self.store, FakeCosts(fail=HttpError(401, "authorization: Bearer abcdefghijklmnop")))
        self.assertNotIn("abcdefghijklmnop", said[0])

    def test_a_store_that_cannot_be_read_is_said_and_never_raised(self):
        class Down(MemoryStore):
            def plans_open(self):
                raise StoreError("the table service is down")

        said = read(Down(), FakeCosts())
        self.assertEqual(said, ["the daily cost of the open requests could not be read (StoreError: the table service is down)"])

    def test_a_case_that_cannot_be_written_does_not_stop_the_others(self):
        class Picky(MemoryStore):
            def case_put(self, case):
                if case.case_id == "k001" and case.cost_series_end == "2026-11-03":
                    raise StoreError("a record is larger than a table property may be")
                super().case_put(case)

        picky = Picky(clock=lambda: NOW)
        stale = open_case(picky, 1, cost_series=[4.0] * 30, cost_series_end="2026-11-02")
        other = open_case(picky, 2)
        said = read(picky, FakeCosts())
        self.assertEqual((picky.case_get("k001"), picky.case_get(other.case_id).cost_series_end), (stale, "2026-11-03"))
        self.assertEqual(said, ["the daily cost of 1 open request could not be read (a record is larger than a table property may be); what was read before stays"])


class TheRecord(unittest.TestCase):
    def test_a_case_with_a_series_survives_a_round_trip_and_the_json_holds_the_numbers_and_the_day(self):
        case = make_case(cost_series=[0.0, 1.5] * 15, cost_series_end="2026-11-03")
        again = CaseRecord.from_json(case.to_json())
        self.assertEqual(again, case)
        data = json.loads(case.to_json())
        self.assertEqual((data["cost_series"], data["cost_series_end"]), ([0.0, 1.5] * 15, "2026-11-03"))
        self.assertIsInstance(again.cost_series, list)

    def test_a_case_without_the_field_round_trips_as_none(self):
        case = make_case()
        self.assertEqual((case.cost_series, case.cost_series_end), (None, None))
        self.assertEqual(CaseRecord.from_json(case.to_json()), case)

    def test_a_case_that_was_stored_before_the_field_existed_reads_with_none(self):
        old = json.loads(make_case().to_json())
        del old["cost_series"], old["cost_series_end"]
        got = CaseRecord.from_json(json.dumps(old))
        self.assertEqual((got.cost_series, got.cost_series_end, got.resource_name), (None, None, "planted-disk-1"))
        self.assertEqual(got, make_case())


class InTheWatch(unittest.TestCase):
    """Whole Watches over the fake estate: the planted disk has an open plan, so its case is read."""

    def setUp(self):
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store
        self.estate = estate_with()
        self.disk = self.estate.graph["orphan-managed-disk"][0]["id"]
        self.estate.days = [(LAST, self.disk, 1.25), (LAST - DAY, self.disk.upper(), 0.75), (FIRST, self.disk, 0.5)]

    def daily(self):
        return [c for c in self.estate.calls if "costmanagement" in c["path"].lower() and c["body"]["dataset"]["granularity"] == "Daily"]

    def case(self):
        (case,) = self.store.cases_recent()
        return case

    @staticmethod
    def said(events):
        return [e["note"] for e in events if e["type"] == "run.note" and "daily cost" in e["note"]]

    def test_the_series_of_the_case_with_an_open_plan_is_filled_at_the_end_of_the_watch(self):
        summary, events, _ = watch(self.estate, self.extras, self.clock)
        self.assertTrue(summary.ok)
        case = self.case()
        (plan,) = self.store.plans_open()
        self.assertEqual((case.status, plan.case_id), ("awaiting_ok", case.case_id))
        self.assertEqual(len(case.cost_series), 30)
        self.assertEqual((case.cost_series[0], case.cost_series[28], case.cost_series[29], case.cost_series_end), (0.5, 0.75, 1.25, "2026-11-03"))
        self.assertEqual(sum(case.cost_series), 2.5)
        self.assertEqual(self.said(events), [])
        self.assertEqual(events[-1]["type"], "run.finished")

    def test_it_is_one_query_by_day_with_the_id_of_the_resource_and_the_thirty_closed_days_and_the_client_type(self):
        watch(self.estate, self.extras, self.clock)
        (call,) = self.daily()
        self.assertEqual(call["body"]["timePeriod"], {"from": "2026-10-05T00:00:00Z", "to": "2026-11-03T23:59:59Z"})
        self.assertEqual(call["body"]["dataset"]["filter"], {"dimensions": {"name": "ResourceId", "operator": "In", "values": [self.disk.lower()]}})
        self.assertEqual((call["method"], call["body"]["type"], call["headers"].get("ClientType")), ("POST", "ActualCost", "Meternaut"))

    def test_a_second_watch_on_the_same_day_makes_no_query_by_day_and_leaves_the_case_as_it_is(self):
        watch(self.estate, self.extras, self.clock)
        before = self.case()
        self.estate.calls.clear()
        self.clock.advance(hours=3)
        watch(self.estate, self.extras, self.clock)
        self.assertEqual(self.daily(), [])
        self.assertEqual(self.case(), before)

    def test_the_next_day_the_series_is_read_again_and_moves_on_by_a_day(self):
        watch(self.estate, self.extras, self.clock)
        self.estate.days.append((LAST + DAY, self.disk, 9.0))
        self.estate.calls.clear()
        self.clock.advance(days=1)
        watch(self.estate, self.extras, self.clock)
        self.assertEqual(len(self.daily()), 1)
        case = self.case()
        self.assertEqual((case.cost_series[27:], case.cost_series_end, len(case.cost_series)), ([0.75, 1.25, 9.0], "2026-11-04", 30))

    def test_a_watch_with_no_open_plan_makes_no_query_by_day(self):
        extras = loop_for(self.clock, approvers=False)
        watch(self.estate, extras, self.clock)
        (case,) = extras.store.cases_recent()
        self.assertEqual((extras.store.plans_open(), self.daily(), case.cost_series), ([], [], None))

    def test_a_watch_without_the_loop_makes_no_query_by_day(self):
        run_watch(self.estate)
        self.assertEqual(self.daily(), [])

    def test_a_query_that_fails_leaves_the_old_value_and_the_watch_ends_well_with_a_line_in_the_history(self):
        watch(self.estate, self.extras, self.clock)
        first = self.case()
        self.estate.calls.clear()
        self.estate.failures["daily"] = 500
        self.clock.advance(days=1)
        summary, events, _ = watch(self.estate, self.extras, self.clock)
        self.assertTrue(summary.ok)
        self.assertEqual(events[-1]["type"], "run.finished")
        (note,) = self.said(events)
        self.assertEqual(note, "the daily cost of 1 open request could not be read (POST management.azure.com: 500 Throttled: slow down); what was read before stays")
        self.assertEqual((self.case().cost_series, self.case().cost_series_end), (first.cost_series, "2026-11-03"))
        record = self.store.runs_recent()[0]
        self.assertEqual((record.ok, note in record.notes), (True, True))
        self.assertEqual(len(self.daily()), 3, "the client's own two repeats and nothing else")

    def test_a_limit_is_waited_for_by_the_client_as_for_any_read_and_the_step_asks_no_more(self):
        self.estate.failures["daily"] = 429
        summary, events, _ = watch(self.estate, self.extras, self.clock)
        self.assertTrue(summary.ok)
        self.assertEqual(len(self.daily()), 3, "one query and its two repeats")
        self.assertEqual(self.estate.sleeps, [1.0, 1.0], "the waits that Cost Management asked for, and no other")
        self.assertIsNone(self.case().cost_series)
        self.assertEqual(len(self.said(events)), 1)

    def test_cost_lines_in_another_currency_leave_none_and_no_query_by_day_is_made(self):
        self.estate.cost_rows, self.estate.currency = [(5.0, self.disk.lower())], "EUR"
        summary, events, _ = watch(self.estate, self.extras, self.clock)
        self.assertTrue(summary.ok)
        self.assertEqual(self.daily(), [])
        self.assertIsNone(self.case().cost_series)
        self.assertTrue(any("EUR" in e["note"] for e in events if e["type"] == "run.note"), "the Watch said so already")
        self.assertEqual(self.said(events), [])

    def test_a_query_by_day_in_another_currency_leaves_none_although_the_cost_lines_were_in_dollars(self):
        class Odd(FakeEstate):
            def __call__(self, method, url, headers, data, timeout):
                status, answer_headers, body = super().__call__(method, url, headers, data, timeout)
                return status, answer_headers, body.replace(b'"USD"', b'"EUR"') if data and b'"Daily"' in data else body

        estate = Odd()
        estate.graph, estate.days = self.estate.graph, self.estate.days
        summary, events, _ = watch(estate, self.extras, self.clock)
        self.assertTrue(summary.ok)
        self.assertIsNone(self.case().cost_series)
        self.assertEqual(self.said(events), ["the daily cost of 1 open request could not be read (the cost lines are not in US dollars); what was read before stays"])


if __name__ == "__main__":
    unittest.main()
