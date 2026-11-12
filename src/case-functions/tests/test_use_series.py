"""The daily use of the cases that have an open plan (cases/run.py: read_use_series, the step after read_cost_series), which the request page and the Decisions page draw as the second chart of a
card. Everything in it is INVENTED.

The first classes call the step with a fake of Azure Monitor and a store in memory; the last runs whole Watches against the fake estate, so that the real client, the real list of calls and the
real read are in the test.
"""
import datetime as dt
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from support import APP_ROOT, ENV, NOW, SUBSCRIPTION, Ticker, run_watch

from cases import run, usage
from cases.arm import MetricPoint
from cases.http import HttpError
from cases.memory_store import MemoryStore, stamp
from cases.models import GROUP_FACT, CaseRecord, StoreError
from cases.redact import Redactor
from test_run_loop import Moving, estate_with, loop_for, watch
from test_web_support import make_case, make_plan

OTHER = "cccccccc-3333-4444-8555-666666666666"  # a second subscription
DAY = dt.timedelta(days=1)
LAST, FIRST = dt.date(2026, 11, 3), dt.date(2026, 10, 5)  # the thirty closed days of a run at support.NOW
START, END = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc), dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc)  # what Azure Monitor is asked for: those days as UTC days
VM_TYPE, PE_TYPE = "microsoft.compute/virtualmachines", "microsoft.network/privateendpoints"


def vm_id(n: int, sub: str = SUBSCRIPTION) -> str:
    """The id of an invented virtual machine, in the mixed case that Resource Graph gives."""
    return f"/subscriptions/{sub}/resourceGroups/rg-{n % 3}/providers/Microsoft.Compute/virtualMachines/vm-{n:03d}"


def pe_id(n: int, sub: str = SUBSCRIPTION) -> str:
    return f"/subscriptions/{sub}/resourceGroups/rg-{n % 3}/providers/Microsoft.Network/privateEndpoints/pe-{n:03d}"


def open_case(store, n: int, resource_id=None, resource_type=VM_TYPE, **changes) -> CaseRecord:
    """A case with an open plan, in the store: a virtual machine unless it is said to be another thing."""
    resource_id = resource_id or (vm_id(n) if resource_type == VM_TYPE else pe_id(n))
    case = make_case(case_id=f"k{n:03d}", resource_id=resource_id, resource_name=f"r-{n:03d}", resource_type=resource_type, subscription_id=SUBSCRIPTION, plan_id=f"p{n:03d}",
                     status="needs_human", **changes)
    store.case_put(case)
    store.plan_put(make_plan(plan_id=f"p{n:03d}", case_id=case.case_id, resource_id=case.resource_id, state="open"))
    return case


def values(**by_day) -> dict:
    """{a day: a value} from keyword arguments d0 .. d29 (the thirty days from the first)."""
    return {FIRST + n * DAY: value for n in range(30) if (value := by_day.get(f"d{n}", ...)) is not ...}


def every_day(value=1.0, skipping=()) -> dict:
    """Every one of the thirty days has `value`, except the days (by number) that are skipped."""
    return {FIRST + n * DAY: value for n in range(30) if n not in skipping}


class FakeMonitor:
    """Azure Monitor by day, as Arm.metrics gives it. `days` maps (a resource id in lower case, a metric name) to {a day: a value}: a number (the bucket has it as total, maximum and average), a
    tuple (total, maximum, average) or None (a bucket with no value); a day that is not there has a bucket with no value too. Every read is kept in `reads`. `fail` is raised by every read, or,
    as a dict, by the read of that metric (a name) or of that number (the first is 0). `during` is called while a read is answered."""

    def __init__(self, days=None, fail=None, during=None):
        self.days, self.fail, self.during, self.reads = days or {}, fail, during, []

    def metrics(self, resource_id, metric, start, end):
        number = len(self.reads)
        self.reads.append((resource_id, metric, start, end))
        if self.during:
            self.during()
        error = self.fail
        if isinstance(self.fail, dict):
            error = self.fail.get(number) or self.fail.get(metric)
        if error:
            raise error
        known = self.days.get((resource_id.lower(), metric), {})
        points = []
        for n in range((end - start).days):
            day = start.date() + n * DAY
            value = known.get(day)
            total, maximum, average = value if isinstance(value, tuple) else (value, value, value)
            points.append(MetricPoint(f"{day.isoformat()}T00:00:00Z", total, maximum, average))
        return "Percent", points

    def asked(self) -> list[tuple]:
        """What each read asked for: (the resource's name, the metric)."""
        return [(resource.rsplit("/", 1)[1], metric) for resource, metric, _, _ in self.reads]


def series_of_vm(n: int, days: dict) -> dict:
    return {(vm_id(n).lower(), "Percentage CPU"): days}


def read(store, monitor, now=NOW, left=None) -> list[str]:
    """One run of the step. Returns what it told the History. `left` is what the client says the run has left: a number, a function that gives one, or None (no deadline)."""
    said: list[str] = []
    client = SimpleNamespace(remaining=left if callable(left) else (lambda: left))
    run.read_use_series(SimpleNamespace(extras=SimpleNamespace(store=store), arm=monitor, client=client, clock=lambda: now, redact=Redactor()), said.append)
    return said


def store_of() -> MemoryStore:
    return MemoryStore(clock=lambda: NOW)


def kept(store, case_id="k001") -> CaseRecord:
    return store.case_get(case_id)


class TheUseOfOneCase(unittest.TestCase):
    def setUp(self):
        self.store = store_of()
        self.case = open_case(self.store, 1)

    def test_the_days_of_these_tests_are_the_thirty_closed_days_before_the_day_of_the_run(self):
        self.assertEqual((FIRST, LAST), ((NOW - 30 * DAY).date(), (NOW - DAY).date()))
        self.assertEqual((START, END), (dt.datetime.combine(FIRST, dt.time.min, tzinfo=dt.timezone.utc), dt.datetime.combine(LAST + DAY, dt.time.min, tzinfo=dt.timezone.utc)))

    def test_thirty_closed_days_oldest_first_ending_yesterday_with_a_gap_for_a_day_that_has_no_value_and_the_kind_that_was_read(self):
        days = values(d0=0.5, d1=2.0, d5=0.0, d28=3.25, d29=1.25, **{f"d{n}": 1.0 for n in range(6, 28)})
        self.assertEqual(read(self.store, FakeMonitor(series_of_vm(1, days))), [])
        got = kept(self.store)
        self.assertEqual((len(got.use_series), got.use_series_end, got.use_kind), (30, "2026-11-03", "vm-cpu"))
        self.assertEqual((got.use_series[0], got.use_series[1], got.use_series[2], got.use_series[5], got.use_series[27], got.use_series[28], got.use_series[29]),
                         (0.5, 2.0, None, 0.0, 1.0, 3.25, 1.25))
        self.assertEqual([i for i, v in enumerate(got.use_series) if v is None], [2, 3, 4], "a gap, and never a zero")
        self.assertEqual(replace(got, use_series=None, use_series_end=None, use_kind=None), self.case, "the step changes nothing else of the case: not its status and not the time that it was judged")

    def test_one_read_of_the_metric_of_the_kind_over_the_thirty_closed_days_as_utc_days_with_the_id_as_it_is(self):
        monitor = FakeMonitor(series_of_vm(1, every_day()))
        read(self.store, monitor)
        self.assertEqual(monitor.reads, [(vm_id(1), "Percentage CPU", START, END)])
        self.assertEqual((END - START).days, usage.DAYS)

    def test_the_day_of_a_series_is_the_aggregation_of_the_kind_that_the_table_names(self):
        triple = (100.0, 50.0, 3.5)  # the total, the highest and the average of a bucket
        for n, (resource_type, metric, expected) in enumerate(((VM_TYPE, "Percentage CPU", 3.5), ("microsoft.web/serverfarms", "CpuPercentage", 3.5),
                                                                ("microsoft.network/p2svpngateways", "P2SConnectionCount", 50.0), ("microsoft.storage/storageaccounts", "Transactions", 100.0)), 20):
            with self.subTest(kind=resource_type):
                kind = usage.entry_of(resource_type)
                rid = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-1/providers/{kind.resource_type}/x{n}"
                case = open_case(self.store, n, resource_id=rid, resource_type=resource_type)
                read(self.store, FakeMonitor({(rid.lower(), metric): every_day(triple)}))
                self.assertEqual((kept(self.store, case.case_id).use_series[3], kept(self.store, case.case_id).use_kind), (expected, kind.kind))

    def test_a_value_is_kept_to_a_ten_thousandth_a_zero_stays_a_zero_and_a_value_that_cannot_be_a_use_is_a_gap(self):
        monitor = FakeMonitor(series_of_vm(1, {**every_day(1.0), FIRST: 0.12345678, FIRST + DAY: 0, FIRST + 2 * DAY: -1.0, FIRST + 3 * DAY: float("nan")}))
        read(self.store, monitor)
        self.assertEqual(kept(self.store).use_series[:5], [0.1235, 0.0, None, None, 1.0])
        self.assertNotIn("NaN", kept(self.store).to_json())
        self.assertNotIn("-0.0", kept(self.store).to_json())

    def test_fewer_than_twenty_days_with_a_value_store_nothing_and_say_nothing_and_twenty_do_store(self):
        for have, stored in ((19, False), (20, True), (1, False), (0, False), (30, True)):
            with self.subTest(days=have):
                store = store_of()
                open_case(store, 1)
                self.assertEqual(read(store, FakeMonitor(series_of_vm(1, every_day(1.0, skipping=range(have, 30))))), [])
                got = kept(store)
                self.assertEqual((got.use_series is not None, got.use_series_end, got.use_kind), (stored, "2026-11-03" if stored else None, "vm-cpu" if stored else None))
        self.assertEqual(usage.MIN_DAYS, 20)

    def test_a_case_with_an_older_series_that_has_too_few_days_now_keeps_the_older_one(self):
        old = open_case(self.store, 2, use_series=[7.0] * 30, use_series_end="2026-11-02", use_kind="vm-cpu")
        read(self.store, FakeMonitor(series_of_vm(2, every_day(1.0, skipping=range(11)))))  # 19 days with a value
        self.assertEqual(kept(self.store, "k002"), old)

    def test_the_private_endpoint_reads_both_of_its_metrics_and_adds_them_and_a_day_that_one_has_no_value_for_is_a_gap(self):
        case = open_case(self.store, 5, resource_type=PE_TYPE)
        inside, outside = ((pe_id(5).lower(), metric) for metric in ("PEBytesIn", "PEBytesOut"))
        monitor = FakeMonitor({inside: {**every_day(100.0), FIRST: None}, outside: every_day(25.5, skipping=[7])})
        self.assertEqual(read(self.store, monitor), [])
        self.assertEqual([asked for asked in monitor.asked() if asked[0] == "pe-005"], [("pe-005", "PEBytesIn"), ("pe-005", "PEBytesOut")])
        got = kept(self.store, case.case_id)
        self.assertEqual((got.use_kind, got.use_series[0], got.use_series[1], got.use_series[7], got.use_series[29]), ("pe-traffic", None, 125.5, None, 125.5))

    def test_a_kind_that_adds_its_metrics_fails_when_one_of_them_cannot_be_read_so_that_a_sum_is_never_less_than_the_use(self):
        case = open_case(self.store, 5, resource_type=PE_TYPE)
        for error in (HttpError(400, "GET management.azure.com: 400 BadRequest: no such metric"), HttpError(500, "GET management.azure.com: 500 InternalServerError: boom")):
            with self.subTest(status=error.status):
                monitor = FakeMonitor({(pe_id(5).lower(), "PEBytesIn"): every_day(1.0)}, fail={"PEBytesOut": error})
                said = read(self.store, monitor)
                self.assertIsNone(kept(self.store, case.case_id).use_series)
                self.assertEqual(said, [f"the use of 1 open request could not be read ({error}); what was read before stays"])

    def test_a_kind_that_takes_the_larger_of_its_metrics_is_the_larger_for_each_day_and_zero_only_when_both_are(self):
        rid = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-1/providers/Microsoft.CognitiveServices/accounts/ai-1"
        case = open_case(self.store, 6, resource_id=rid, resource_type="microsoft.cognitiveservices/accounts")
        calls = {(rid.lower(), "TotalCalls"): {**every_day(0.0), FIRST + DAY: 9.0}, (rid.lower(), "ModelRequests"): {**every_day(4.0), FIRST + DAY: 2.0, FIRST + 2 * DAY: 0.0}}
        read(self.store, FakeMonitor(calls))
        got = kept(self.store, case.case_id)
        self.assertEqual((got.use_kind, got.use_series[0], got.use_series[1], got.use_series[2]), ("ai-calls", 4.0, 9.0, 0.0), "the larger of the two for each day: 4 or 0, 9 or 2, and 0 or 0")
        quiet = {(rid.lower(), "TotalCalls"): every_day(0.0), (rid.lower(), "ModelRequests"): every_day(0.0)}
        read(self.store, FakeMonitor(quiet), now=NOW + DAY)
        self.assertEqual({v for v in kept(self.store, case.case_id).use_series if v is not None}, {0.0})

    def test_a_metric_that_a_resource_does_not_have_is_left_out_when_another_of_the_kind_is_read_and_only_then(self):
        rid = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-1/providers/Microsoft.CognitiveServices/accounts/ai-1"
        case = open_case(self.store, 6, resource_id=rid, resource_type="microsoft.cognitiveservices/accounts")
        no_metric = HttpError(400, "GET management.azure.com: 400 BadRequest: no such metric")
        read(self.store, FakeMonitor({(rid.lower(), "TotalCalls"): every_day(3.0)}, fail={"ModelRequests": no_metric}))
        self.assertEqual(kept(self.store, case.case_id).use_series[0], 3.0)
        store = store_of()
        case = open_case(store, 6, resource_id=rid, resource_type="microsoft.cognitiveservices/accounts")
        said = read(store, FakeMonitor(fail=no_metric))
        self.assertEqual((kept(store, case.case_id).use_series, said), (None, [f"the use of 1 open request could not be read ({no_metric}); what was read before stays"]))

    def test_a_failed_read_of_one_of_the_larger_of_two_is_a_failure_and_never_a_series_of_the_other_alone(self):
        rid = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-1/providers/Microsoft.CognitiveServices/accounts/ai-1"
        case = open_case(self.store, 6, resource_id=rid, resource_type="microsoft.cognitiveservices/accounts")
        for status in (500, 403, 404):
            with self.subTest(status=status):
                said = read(self.store, FakeMonitor({(rid.lower(), "TotalCalls"): every_day(0.0)}, fail={"ModelRequests": HttpError(status, f"GET management.azure.com: {status} X: no")}))
                self.assertIsNone(kept(self.store, case.case_id).use_series, "a zero that is the other metric's alone could say that a busy account is idle")
                self.assertEqual(len(said), 1)

    def test_the_kinds_of_the_table_all_work_through_the_step_with_the_metrics_that_they_name(self):
        for n, (resource_type, kind) in enumerate(usage.TABLE.items(), 30):
            with self.subTest(kind=kind.kind):
                store = store_of()
                rid = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-1/providers/{resource_type.replace('microsoft.', 'Microsoft.')}/x{n}"
                case = open_case(store, n, resource_id=rid, resource_type=resource_type)
                monitor = FakeMonitor({(rid.lower(), metric): every_day(2.0) for metric in kind.metrics})
                self.assertEqual(read(store, monitor), [])
                self.assertEqual([metric for _, metric, _, _ in monitor.reads], list(kind.metrics))
                got = kept(store, case.case_id)
                self.assertEqual((got.use_kind, got.use_series_end, len(got.use_series)), (kind.kind, "2026-11-03", 30))
                self.assertEqual(set(got.use_series), {4.0} if kind.combine == "sum" and len(kind.metrics) == 2 else {2.0})


class WhichCasesAreRead(unittest.TestCase):
    def setUp(self):
        self.store = store_of()

    def test_a_case_without_an_open_plan_is_not_read(self):
        self.store.case_put(make_case(case_id="k100", resource_id=vm_id(100), resource_type=VM_TYPE, plan_id=None, status="proposed"))
        for number, state in enumerate(("declined", "expired", "consumed", "withdrawn", "failed"), 101):
            case = open_case(self.store, number)
            self.store.plan_put(replace(self.store.plan_get(case.plan_id), state=state))
        monitor = FakeMonitor()
        self.assertEqual(read(self.store, monitor), [])
        self.assertEqual(monitor.reads, [])
        self.assertTrue(all(case.use_series is None for case in self.store.cases_recent()))

    def test_an_approved_plan_that_is_not_done_yet_is_open_too(self):
        case = open_case(self.store, 1)
        self.store.plan_put(replace(self.store.plan_get(case.plan_id), state="approved"))
        read(self.store, FakeMonitor(series_of_vm(1, every_day())))
        self.assertIsNotNone(kept(self.store).use_series)

    def test_a_plan_of_a_case_that_is_gone_is_left_alone(self):
        self.store.plan_put(make_plan(plan_id="p-lost", case_id="k-lost"))
        monitor = FakeMonitor()
        self.assertEqual((read(self.store, monitor), monitor.reads), ([], []))

    def test_a_case_of_a_type_that_has_no_kind_of_use_or_whose_id_is_not_the_id_of_one_resource_of_it_is_not_read(self):
        disk = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-1/providers/Microsoft.Compute/disks/d1"
        open_case(self.store, 1, resource_id=disk, resource_type="microsoft.compute/disks")
        open_case(self.store, 2, resource_id=f"{vm_id(2)}/extensions/x", resource_type=VM_TYPE)
        open_case(self.store, 3, resource_id=f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-1", resource_type=VM_TYPE)
        open_case(self.store, 4, resource_id=pe_id(4), resource_type=VM_TYPE)
        open_case(self.store, 5, resource_type="")
        monitor = FakeMonitor()
        self.assertEqual((read(self.store, monitor), monitor.reads), ([], []))

    def test_a_case_that_stands_for_many_resources_gets_no_use_series_although_its_type_has_a_kind(self):
        group = {"count": 4, "costUsd30d": 1.0, "type": PE_TYPE, "groups": 1, "names": [], "capped": 0, "silenced": 0, "members": [], "resourceIds": [pe_id(n).lower() for n in range(4)]}
        open_case(self.store, 1, resource_type=PE_TYPE, facts={GROUP_FACT: group})
        open_case(self.store, 2, resource_type=PE_TYPE, facts={GROUP_FACT: "not a group"})
        open_case(self.store, 3, resource_type=PE_TYPE, facts={})
        monitor = FakeMonitor()
        self.assertEqual(read(self.store, monitor), [])
        self.assertEqual(monitor.asked(), [("pe-003", "PEBytesIn"), ("pe-003", "PEBytesOut")], "the case of one resource is read, and the cases of a group are not")

    def test_no_read_is_made_when_nothing_needs_one(self):
        monitor = FakeMonitor()
        self.assertEqual((read(self.store, monitor), monitor.reads), ([], []), "no case at all")
        case = open_case(self.store, 1, use_series=[1.5] * 30, use_series_end="2026-11-03", use_kind="vm-cpu")
        self.assertEqual((read(self.store, monitor), monitor.reads), ([], []), "a series that ends yesterday")
        self.assertEqual(kept(self.store), case)

    def test_a_series_that_does_not_end_yesterday_has_not_thirty_days_or_is_of_another_kind_is_read_again(self):
        for number, (series, end, kind) in enumerate((([9.0] * 30, "2026-11-02", "vm-cpu"), ([9.0] * 29, "2026-11-03", "vm-cpu"), ([9.0] * 30, None, "vm-cpu"), (None, "2026-11-03", "vm-cpu"),
                                                      ([9.0] * 30, "garbage", "vm-cpu"), ([9.0] * 30, "2026-11-03", "plan-cpu"), ([9.0] * 30, "2026-11-03", None)), 1):
            with self.subTest(end=end, days=len(series or ()), kind=kind):
                case = open_case(self.store, number, use_series=series, use_series_end=end, use_kind=kind)
                read(self.store, FakeMonitor(series_of_vm(number, every_day(2.0))))
                got = kept(self.store, case.case_id)
                self.assertEqual((got.use_series, got.use_series_end, got.use_kind), ([2.0] * 30, "2026-11-03", "vm-cpu"))

    def test_a_series_is_read_again_the_next_day_and_never_twice_in_one_day(self):
        case = open_case(self.store, 1)
        monitor = FakeMonitor(series_of_vm(1, {**every_day(1.0), LAST + DAY: 7.0}))
        read(self.store, monitor)
        read(self.store, monitor, now=NOW + dt.timedelta(hours=8))
        self.assertEqual(len(monitor.reads), 1, "the same day")
        read(self.store, monitor, now=NOW + DAY)
        got = kept(self.store, case.case_id)
        self.assertEqual((len(monitor.reads), got.use_series[28:], got.use_series_end), (2, [1.0, 7.0], "2026-11-04"))
        self.assertEqual(monitor.reads[1][2:], (START + DAY, END + DAY))

    def test_the_day_is_the_utc_day(self):
        case = open_case(self.store, 1)
        late = dt.datetime(2026, 11, 4, 23, 30, tzinfo=dt.timezone(dt.timedelta(hours=-3)))  # 02:30 on the 5th in UTC
        read(self.store, FakeMonitor(series_of_vm(1, every_day())), now=late)
        self.assertEqual(kept(self.store, case.case_id).use_series_end, "2026-11-04")

    def test_a_resource_that_two_cases_have_is_read_once_and_both_cases_are_written(self):
        first = open_case(self.store, 1)
        second = open_case(self.store, 2, resource_id=vm_id(1).lower())  # the same machine as Azure spelled it another time
        monitor = FakeMonitor(series_of_vm(1, every_day(3.0)))
        read(self.store, monitor)
        self.assertEqual(len(monitor.reads), 1)
        self.assertEqual([kept(self.store, case.case_id).use_series[0] for case in (first, second)], [3.0, 3.0])

    def test_the_resources_of_other_subscriptions_are_read_like_any_other(self):
        rid = vm_id(1, OTHER)
        open_case(self.store, 1, resource_id=rid)
        monitor = FakeMonitor({(rid.lower(), "Percentage CPU"): every_day()})
        read(self.store, monitor)
        self.assertEqual([resource for resource, _, _, _ in monitor.reads], [rid])

    def test_a_person_who_answered_while_the_use_was_read_keeps_the_answer(self):
        case = open_case(self.store, 1)
        monitor = FakeMonitor(series_of_vm(1, every_day(3.0)), during=lambda: self.store.case_put(replace(kept(self.store, case.case_id), status="approved", updated_at=stamp(NOW))))
        read(self.store, monitor)
        got = kept(self.store, case.case_id)
        self.assertEqual((got.status, got.updated_at, got.use_series[0]), ("approved", stamp(NOW), 3.0))

    def test_the_step_has_no_effect_on_the_cost_of_the_case_and_the_cost_step_none_on_its_use(self):
        case = open_case(self.store, 1, cost_series=[1.0] * 30, cost_series_end="2026-11-03")
        read(self.store, FakeMonitor(series_of_vm(1, every_day())))
        got = kept(self.store, case.case_id)
        self.assertEqual((got.cost_series, got.cost_series_end), ([1.0] * 30, "2026-11-03"))
        costs = SimpleNamespace(cost_days=lambda subscription, first, last, where=None: [(last, where[1][0], 2.0, "USD")])  # one day with a cost line, the day that closed
        run.read_cost_series(SimpleNamespace(extras=SimpleNamespace(store=self.store), arm=costs, clock=lambda: NOW + DAY, redact=Redactor()), {}, lambda text: None)
        again = kept(self.store, case.case_id)
        self.assertEqual((again.use_series, again.use_series_end, again.use_kind), (got.use_series, "2026-11-03", "vm-cpu"))
        self.assertEqual(again.cost_series_end, "2026-11-04")

    def test_a_plan_that_a_person_answered_while_the_use_was_read_leaves_the_case_with_its_series_and_its_status(self):
        case = open_case(self.store, 1)
        monitor = FakeMonitor(series_of_vm(1, every_day(3.0)), during=lambda: self.store.plan_put(replace(self.store.plan_get(case.plan_id), state="declined")))
        self.assertEqual(read(self.store, monitor), [])
        got = kept(self.store, case.case_id)
        self.assertEqual((got.status, got.use_series[0]), (case.status, 3.0))
        self.assertEqual(self.store.plan_get(case.plan_id).state, "declined", "the step changes no plan")

    def test_the_step_is_the_one_after_the_daily_cost_at_the_end_of_the_watch(self):
        source = (APP_ROOT / "cases" / "run.py").read_text(encoding="utf-8")
        self.assertRegex(source, r"\n    read_cost_series\(s, contexts, say\)\n    read_use_series\(s, say\)\n    summary\.tokens = tokens\n")
        self.assertEqual(source.count("read_use_series(s, say)"), 1)

    def test_without_the_loop_there_is_nothing_to_read(self):
        said: list[str] = []
        monitor = FakeMonitor()
        run.read_use_series(SimpleNamespace(extras=None, arm=monitor, client=SimpleNamespace(remaining=lambda: None), clock=lambda: NOW, redact=Redactor()), said.append)
        self.assertEqual((said, monitor.reads), ([], []))


class TheLimits(unittest.TestCase):
    def setUp(self):
        self.store = store_of()

    def test_at_most_thirty_resources_are_read_in_a_watch_and_the_others_are_said_to_wait(self):
        self.assertEqual(run.USE_MAX_RESOURCES, 30)
        for n in range(1, 34):
            open_case(self.store, n)
        monitor = FakeMonitor({(vm_id(n).lower(), "Percentage CPU"): every_day() for n in range(1, 34)})
        said = read(self.store, monitor)
        self.assertEqual(len(monitor.reads), 30)
        self.assertEqual(said, ["3 more open requests wait for the next search: at most 30 resources are read in one search"])
        self.assertEqual(sum(1 for case in self.store.cases_recent(100) if case.use_series is not None), 30)

    def test_a_resource_that_was_never_read_goes_before_one_that_was_read_longest_ago_and_that_before_the_others(self):
        open_case(self.store, 1, use_series=[1.0] * 30, use_series_end="2026-11-02", use_kind="vm-cpu")
        open_case(self.store, 2, use_series=[1.0] * 30, use_series_end="2026-10-28", use_kind="vm-cpu")
        open_case(self.store, 3)
        open_case(self.store, 4, use_series=[1.0] * 30, use_series_end="2026-11-01", use_kind="vm-cpu")
        monitor = FakeMonitor({(vm_id(n).lower(), "Percentage CPU"): every_day() for n in range(1, 5)})
        with mock.patch.object(run, "USE_MAX_RESOURCES", 2):
            said = read(self.store, monitor)
        self.assertEqual([name for name, _ in monitor.asked()], ["vm-003", "vm-002"])
        self.assertEqual(said, ["2 more open requests wait for the next search: at most 2 resources are read in one search"])

    def test_the_cap_counts_resources_and_not_cases(self):
        for n in range(1, 4):
            open_case(self.store, n, resource_id=vm_id(1).lower() if n > 1 else vm_id(1))
        monitor = FakeMonitor(series_of_vm(1, every_day()))
        with mock.patch.object(run, "USE_MAX_RESOURCES", 1):
            self.assertEqual(read(self.store, monitor), [])
        self.assertEqual(len(monitor.reads), 1)
        self.assertEqual(sum(1 for case in self.store.cases_recent() if case.use_series is not None), 3)

    def test_no_resource_is_read_when_the_run_has_less_than_thirty_seconds_left_and_the_history_says_so(self):
        self.assertEqual(run.USE_MIN_SECONDS, 30)
        for n in (1, 2):
            open_case(self.store, n)
        monitor = FakeMonitor()
        for left in (29.9, 0.0, -5.0):
            with self.subTest(left=left):
                self.assertEqual(read(self.store, monitor, left=left), ["the use of 2 open requests was not read: the run had too little time left"])
        self.assertEqual(monitor.reads, [])
        self.assertEqual(read(self.store, FakeMonitor(), left=30.0), [], "thirty seconds are enough, and a case with no value is silent")

    def test_the_run_is_asked_for_its_time_before_each_resource_and_the_step_stops_when_it_runs_out(self):
        for n in (1, 2, 3):
            open_case(self.store, n)
        times = iter([200.0, 100.0, 12.0, 500.0])
        monitor = FakeMonitor({(vm_id(n).lower(), "Percentage CPU"): every_day() for n in range(1, 4)})
        said = read(self.store, monitor, left=lambda: next(times))
        self.assertEqual(len(monitor.reads), 2)
        self.assertEqual(said, ["the use of 1 open request was not read: the run had too little time left"])
        self.assertEqual(sum(1 for case in self.store.cases_recent() if case.use_series is not None), 2)

    def test_a_run_with_no_deadline_is_not_short_of_time(self):
        open_case(self.store, 1)
        read(self.store, FakeMonitor(series_of_vm(1, every_day())), left=None)
        self.assertIsNotNone(kept(self.store).use_series)

    def test_a_limit_ends_the_step_at_the_first_read_and_every_case_keeps_what_it_had(self):
        old = open_case(self.store, 1, use_series=[4.0] * 30, use_series_end="2026-11-02", use_kind="vm-cpu")
        for n in (2, 3):
            open_case(self.store, n)
        pe = open_case(self.store, 4, resource_type=PE_TYPE)
        monitor = FakeMonitor(fail=HttpError(429, "GET management.azure.com: 429 Throttled: slow down", 30.0))
        said = read(self.store, monitor)
        self.assertEqual(len(monitor.reads), 1, "four resources were due: no second read and no loop of retries")
        self.assertEqual((kept(self.store, old.case_id), kept(self.store, "k002").use_series, kept(self.store, pe.case_id).use_series), (old, None, None))
        self.assertEqual(said, ["the use of 4 open requests could not be read (GET management.azure.com: 429 Throttled: slow down); what was read before stays"])

    def test_a_limit_after_some_reads_keeps_what_was_read_and_does_not_ask_for_more(self):
        for n in (1, 2, 3):
            open_case(self.store, n)
        monitor = FakeMonitor({(vm_id(n).lower(), "Percentage CPU"): every_day() for n in range(1, 4)}, fail={1: HttpError(429, "GET management.azure.com: 429 Throttled: slow down", 30.0)})
        said = read(self.store, monitor)
        self.assertEqual(len(monitor.reads), 2)
        self.assertEqual(sum(1 for case in self.store.cases_recent() if case.use_series is not None), 1, "the first read worked and its case is written")
        self.assertEqual(said, ["the use of 2 open requests could not be read (GET management.azure.com: 429 Throttled: slow down); what was read before stays"])


class WhenTheUseCannotBeRead(unittest.TestCase):
    def setUp(self):
        self.store = store_of()
        self.case = open_case(self.store, 1, use_series=[4.0] * 30, use_series_end="2026-11-02", use_kind="vm-cpu")  # an earlier day's: it is read again

    def test_an_error_of_azure_leaves_the_old_value_and_is_said_once_with_what_azure_said(self):
        said = read(self.store, FakeMonitor(fail=HttpError(500, "GET management.azure.com: 500 InternalServerError: boom")))
        self.assertEqual(kept(self.store), self.case)
        self.assertEqual(said, ["the use of 1 open request could not be read (GET management.azure.com: 500 InternalServerError: boom); what was read before stays"])

    def test_an_answer_that_the_app_does_not_understand_is_an_error_like_any_other(self):
        said = read(self.store, FakeMonitor(fail=HttpError(200, "Azure Monitor gave an answer that the app does not understand")))
        self.assertEqual((kept(self.store), len(said)), (self.case, 1))

    def test_a_bucket_that_is_not_a_utc_day_is_an_answer_of_another_shape_and_said_so_and_not_a_day_without_a_value(self):
        class Odd(FakeMonitor):
            def __init__(self, time):
                super().__init__(series_of_vm(1, every_day()))
                self.time = time

            def metrics(self, resource_id, metric, start, end):
                unit, points = super().metrics(resource_id, metric, start, end)
                return unit, [points[0]._replace(time=self.time), *points[1:]]

        for time in ("2026-10-05T12:00:00Z", "2026-10-05T00:00:00+02:00", "2026-10-05", "garbage", ""):
            with self.subTest(time=time):
                said = read(self.store, Odd(time))
                self.assertEqual(kept(self.store), self.case, "nothing is stored from an answer of another shape")
                self.assertEqual(said, ["the use of 1 open request could not be read (Azure Monitor gave a bucket that is not a UTC day); what was read before stays"])

    def test_another_error_goes_on_with_the_other_resources_and_one_line_counts_the_cases_that_failed(self):
        second, third = open_case(self.store, 2), open_case(self.store, 3)
        monitor = FakeMonitor({(vm_id(n).lower(), "Percentage CPU"): every_day(float(n)) for n in (1, 2, 3)}, fail={1: HttpError(403, "GET management.azure.com: 403 AuthorizationFailed: no right")})
        said = read(self.store, monitor)
        self.assertEqual(len(monitor.reads), 3, "the read after the one that failed was made")
        written = [c.case_id for c in (self.case, second, third) if kept(self.store, c.case_id).use_series_end == "2026-11-03"]
        self.assertEqual(len(written), 2, "the cases of the reads that worked are written and the case of the read that failed is as it was")
        self.assertEqual(said, ["the use of 1 open request could not be read (GET management.azure.com: 403 AuthorizationFailed: no right); what was read before stays"])

    def test_a_fault_that_nobody_expected_is_said_and_never_raised(self):
        said = read(self.store, FakeMonitor(fail=ValueError("a row that is not a row")))
        self.assertEqual((kept(self.store), said), (self.case, ["the use of the open requests could not be read (ValueError: a row that is not a row)"]))

    def test_a_secret_in_an_error_is_redacted(self):
        said = read(self.store, FakeMonitor(fail=HttpError(401, "authorization: ******")))
        self.assertNotIn("abcdefghijklmnop", said[0])

    def test_a_resource_id_that_the_app_refuses_is_an_error_of_that_resource_and_not_of_the_step(self):
        from cases.arm import Arm

        def no_call(*args, **kwargs):
            raise AssertionError("no call is made for an id that is refused")

        store = store_of()
        bad = open_case(store, 2, resource_id=f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg 1/providers/Microsoft.Compute/virtualMachines/vm-2")
        said = read(store, Arm(SimpleNamespace(request=no_call), lambda resource: "token"))
        self.assertEqual((kept(store, bad.case_id).use_series, len(said)), (None, 1))
        self.assertIn("the scope is not the id of an Azure resource", said[0])

    def test_a_store_that_cannot_be_read_is_said_and_never_raised(self):
        class Down(MemoryStore):
            def plans_open(self):
                raise StoreError("the table service is down")

        self.assertEqual(read(Down(), FakeMonitor()), ["the use of the open requests could not be read (StoreError: the table service is down)"])

    def test_a_case_that_cannot_be_written_does_not_stop_the_others(self):
        class Picky(MemoryStore):
            def case_put(self, case):
                if case.case_id == "k001" and case.use_series_end == "2026-11-03":
                    raise StoreError("a record is larger than a table property may be")
                super().case_put(case)

        picky = Picky(clock=lambda: NOW)
        stale = open_case(picky, 1, use_series=[4.0] * 30, use_series_end="2026-11-02", use_kind="vm-cpu")
        open_case(picky, 2)
        said = read(picky, FakeMonitor({(vm_id(n).lower(), "Percentage CPU"): every_day() for n in (1, 2)}))
        self.assertEqual((kept(picky), kept(picky, "k002").use_series_end), (stale, "2026-11-03"))
        self.assertEqual(said, ["the use of 1 open request could not be read (a record is larger than a table property may be); what was read before stays"])

    def test_one_line_for_each_kind_of_problem(self):
        for n in range(2, 5):
            open_case(self.store, n)
        times = iter([100.0, 5.0])
        monitor = FakeMonitor(fail={0: HttpError(500, "GET management.azure.com: 500 InternalServerError: boom")})
        with mock.patch.object(run, "USE_MAX_RESOURCES", 3):
            said = read(self.store, monitor, left=lambda: next(times))
        self.assertEqual(said, ["the use of 1 open request could not be read (GET management.azure.com: 500 InternalServerError: boom); what was read before stays",
                                "the use of 2 open requests was not read: the run had too little time left",
                                "1 more open request waits for the next search: at most 3 resources are read in one search"])


class TheRecord(unittest.TestCase):
    def test_a_case_with_a_use_series_that_has_gaps_survives_a_round_trip_and_the_json_holds_the_numbers_the_gaps_and_the_day(self):
        series = [0.0, 1.5, None, 3.25] * 7 + [None, 2.0]
        case = make_case(use_series=series, use_series_end="2026-11-03", use_kind="vm-cpu")
        again = CaseRecord.from_json(case.to_json())
        self.assertEqual(again, case)
        data = json.loads(case.to_json())
        self.assertEqual((data["use_series"], data["use_series_end"], data["use_kind"]), (series, "2026-11-03", "vm-cpu"))
        self.assertIn("null", case.to_json(), "a gap is a null in the JSON")
        self.assertIsInstance(again.use_series, list)
        self.assertIsNone(again.use_series[2])

    def test_a_case_without_the_fields_round_trips_as_none(self):
        case = make_case()
        self.assertEqual((case.use_series, case.use_series_end, case.use_kind), (None, None, None))
        self.assertEqual(CaseRecord.from_json(case.to_json()), case)

    def test_a_case_that_was_stored_before_the_fields_existed_reads_with_none(self):
        old = json.loads(make_case().to_json())
        del old["use_series"], old["use_series_end"], old["use_kind"]
        got = CaseRecord.from_json(json.dumps(old))
        self.assertEqual((got.use_series, got.use_series_end, got.use_kind, got.resource_name), (None, None, None, "planted-disk-1"))
        self.assertEqual(got, make_case())

    def test_a_case_with_a_series_that_a_later_version_wrote_still_reads_in_this_one(self):
        later = json.loads(make_case(use_series=[1.0] * 30, use_series_end="2026-11-03", use_kind="vm-cpu").to_json())
        later["a_field_of_a_later_version"] = {"x": 1}
        got = CaseRecord.from_json(json.dumps(later))
        self.assertEqual((got.use_kind, len(got.use_series)), ("vm-cpu", 30))

    def test_a_record_with_a_series_of_use_and_one_of_cost_stays_far_below_what_a_table_property_may_hold(self):
        case = make_case(cost_series=[1234.5678] * 30, cost_series_end="2026-11-03", use_series=[123456789012.3456] * 30, use_series_end="2026-11-03", use_kind="pe-traffic")
        self.assertLess(len(case.to_json()), 5000)


class InTheWatch(unittest.TestCase):
    """Whole Watches over the fake estate: an orphan private endpoint is judged, gets a request (advice, open), and its use is read at the end of the Watch."""

    def setUp(self):
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store
        self.estate = estate_with(planted_disk=False, endpoints=1)
        self.pe = self.estate.graph["orphan-private-endpoint"][0]["id"]
        for metric, value in (("PEBytesIn", 1000.0), ("PEBytesOut", 24.5)):
            self.estate.metrics[(self.pe.lower(), metric)] = every_day(value, skipping=[3, 4])

    def monitor_calls(self):
        return [c for c in self.estate.calls if c["path"].lower().endswith("/providers/microsoft.insights/metrics")]

    def case(self):
        (case,) = self.store.cases_recent()
        return case

    @staticmethod
    def said(events):
        return [e["note"] for e in events if e["type"] == "run.note" and "the use of" in e["note"]]

    def test_the_use_of_the_case_with_an_open_plan_is_read_at_the_end_of_the_watch(self):
        summary, events, _ = watch(self.estate, self.extras, self.clock)
        self.assertTrue(summary.ok)
        (plan,) = self.store.plans_open()
        case = self.case()
        self.assertEqual(plan.case_id, case.case_id)
        self.assertEqual((case.use_kind, case.use_series_end, len(case.use_series)), ("pe-traffic", "2026-11-03", 30))
        self.assertEqual((case.use_series[0], case.use_series[3], case.use_series[4], case.use_series[29]), (1024.5, None, None, 1024.5))
        self.assertEqual(self.said(events), [])
        self.assertEqual(events[-1]["type"], "run.finished")

    def test_it_is_one_read_for_each_metric_of_the_kind_with_the_thirty_closed_days_as_daily_buckets_and_the_three_aggregations(self):
        watch(self.estate, self.extras, self.clock)
        calls = self.monitor_calls()
        self.assertEqual([c["method"] for c in calls], ["GET", "GET"])
        self.assertEqual([c["path"] for c in calls], [self.pe + "/providers/Microsoft.Insights/metrics"] * 2)
        queries = [dict(part.split("=", 1) for part in c["url"].split("?", 1)[1].split("&")) for c in calls]
        self.assertEqual([q["metricnames"] for q in queries], ["PEBytesIn", "PEBytesOut"])
        self.assertEqual({q["timespan"] for q in queries}, {"2026-10-05T00:00:00Z/2026-11-04T00:00:00Z"})
        self.assertEqual({(q["interval"], q["aggregation"]) for q in queries}, {("P1D", "Total,Maximum,Average")})

    def test_a_second_watch_on_the_same_day_makes_no_read_and_leaves_the_case_as_it_is(self):
        watch(self.estate, self.extras, self.clock)
        before = self.case()
        self.estate.calls.clear()
        self.clock.advance(hours=3)
        watch(self.estate, self.extras, self.clock)
        self.assertEqual(self.monitor_calls(), [])
        self.assertEqual(self.case(), before)

    def test_the_next_day_the_series_is_read_again_and_moves_on_by_a_day(self):
        watch(self.estate, self.extras, self.clock)
        for metric in ("PEBytesIn", "PEBytesOut"):
            self.estate.metrics[(self.pe.lower(), metric)][LAST + DAY] = 5.0
        self.estate.calls.clear()
        self.clock.advance(days=1)
        watch(self.estate, self.extras, self.clock)
        self.assertEqual(len(self.monitor_calls()), 2)
        case = self.case()
        self.assertEqual((case.use_series[28:], case.use_series_end, len(case.use_series)), ([1024.5, 10.0], "2026-11-04", 30))

    def test_a_watch_with_no_open_plan_makes_no_read(self):
        extras = loop_for(self.clock, approvers=False)
        watch(self.estate, extras, self.clock)
        (case,) = extras.store.cases_recent()
        self.assertEqual((extras.store.plans_open(), self.monitor_calls(), case.use_series), ([], [], None))

    def test_a_watch_without_the_loop_makes_no_read(self):
        run_watch(self.estate)
        self.assertEqual(self.monitor_calls(), [])

    def test_the_planted_disk_is_a_type_with_no_kind_of_use_and_is_not_read(self):
        estate = estate_with()
        watch(estate, self.extras, self.clock)
        (case,) = self.store.cases_recent()
        self.assertEqual((case.resource_type, case.use_series, [c for c in estate.calls if "insights" in c["path"].lower()]), ("microsoft.compute/disks", None, []))

    def test_a_read_that_fails_leaves_the_old_value_and_the_watch_ends_well_with_a_line_in_the_history(self):
        watch(self.estate, self.extras, self.clock)
        first = self.case()
        self.estate.calls.clear()
        self.estate.failures["metrics"] = 500
        self.clock.advance(days=1)
        summary, events, _ = watch(self.estate, self.extras, self.clock)
        self.assertTrue(summary.ok)
        self.assertEqual(events[-1]["type"], "run.finished")
        (note,) = self.said(events)
        self.assertEqual(note, "the use of 1 open request could not be read (GET management.azure.com: 500 Throttled: slow down); what was read before stays")
        self.assertEqual((self.case().use_series, self.case().use_series_end), (first.use_series, "2026-11-03"))
        record = self.store.runs_recent()[0]
        self.assertEqual((record.ok, note in record.notes), (True, True))
        self.assertEqual(len(self.monitor_calls()), 2, "the client's own repeat of the first read and nothing else: the second metric of the kind is not asked for")

    def test_a_limit_is_waited_for_by_the_client_as_for_any_read_and_the_step_asks_no_more(self):
        self.estate.failures["metrics"] = 429
        summary, events, _ = watch(self.estate, self.extras, self.clock)
        self.assertTrue(summary.ok)
        self.assertEqual(len(self.monitor_calls()), 2, "one read and its one repeat (a metric is read with one repeat)")
        self.assertEqual(self.estate.sleeps, [1.0], "the wait that Azure Monitor asked for, and no other")
        self.assertIsNone(self.case().use_series)
        self.assertEqual(len(self.said(events)), 1)

    def test_a_metric_that_a_resource_does_not_have_is_an_error_of_a_kind_that_adds_its_metrics(self):
        self.estate.failures["metrics:PEBytesOut"] = 400
        summary, events, _ = watch(self.estate, self.extras, self.clock)
        self.assertTrue(summary.ok)
        self.assertIsNone(self.case().use_series)
        self.assertEqual(len(self.said(events)), 1)

    def test_a_run_that_is_out_of_time_reads_no_use_and_says_so(self):
        ticker = Ticker()
        self.estate.after_chat = lambda: ticker.jump(50)  # the run's deadline is 60 seconds: the two model calls of the one case end it
        summary, events, _ = run_watch(self.estate, env={**ENV, "RUN_DEADLINE_SECONDS": "60"}, ticker=ticker, clock=self.clock, extras=self.extras)
        self.assertEqual(self.monitor_calls(), [])
        self.assertEqual(self.said(events), ["the use of 1 open request was not read: the run had too little time left"])
        self.assertEqual(events[-1]["type"], "run.finished")

    def test_the_series_of_a_case_that_was_judged_again_is_read_again_in_the_same_watch(self):
        watch(self.estate, self.extras, self.clock)
        self.assertIsNotNone(self.case().use_series)
        self.clock.advance(days=8)  # a case that was judged more than recheck_days ago is judged again, which makes its record again without a series
        self.estate.calls.clear()
        watch(self.estate, self.extras, self.clock)
        self.assertEqual(self.case().use_series_end, "2026-11-11")


if __name__ == "__main__":
    unittest.main()
