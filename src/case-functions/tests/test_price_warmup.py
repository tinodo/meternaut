"""The warm-up of the price book (Toolbox.warm_prices in cases/toolbox.py, called by cases/investigate.py before the first beat): the products of the dearest meters are read from the public price list one at a
time, with a gap and the wait that the list asks for, within three minutes, and never fail the run. A fake estate with a bill by meter, an INVENTED price list and a fake clock; every service, product and price
is invented."""
import datetime as dt
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from support import NOW

import test_investigate as ti
from cases import prices
from cases import toolbox as tb
from cases.memory_store import MemoryStore, stamp
from cases.models import PriceBookRecord
from test_price_book import table_store
from test_prices import SERVICE, PricedEstate, line, swallowing, taking
from test_toolbox import SUB, Clock, toolbox
from test_toolbox_meters import meter, widgets

DAY = dt.date(2026, 10, 20)


def estate_of(count=15, west=2, usd=100.0):
    """An estate of `count` resources of one invented type: resource n costs usd - n, bills one meter of the product `Tier n` of the service, in the same amount, and has its prices in the invented list. The first `west`
    resources are in another region than the others."""
    estate = PricedEstate()
    found = widgets(count)
    estate.rows, estate.cost_rows, estate.definitions = found.rows, [(SUB, usd - n, found.rows[n - 1]["id"].lower(), "Example Service") for n in range(1, count + 1)], found.definitions
    estate.lines = []
    for n in range(1, count + 1):
        estate.rows[n - 1]["location"] = "westeurope" if n <= west else "swedencentral"
        estate.bill.append((SUB, DAY, estate.rows[n - 1]["id"].lower(), "Example Service", meter(category=SERVICE, subcategory=f"Tier {n}"), usd - n, 24.0))
        estate.lines += [line("Basic", "Unit Hours", 0.5 + n / 100, product=f"Tier {n}", region=region) for region in ("westeurope", "swedencentral")]
    return estate


def warmed(count=15, **more):
    """The estate, its toolbox with the Table store as its book and a fake clock that the waits advance, and what the toolbox slept and when the list was asked."""
    estate = estate_of(count, **more)
    box = toolbox(estate)
    box.memory, tables = table_store()
    clock = Clock()
    box.monotonic, box.slept, box.starts = clock, [], []
    box.arm.client.sleep = lambda seconds: (box.slept.append(seconds), clock.advance(seconds))
    answer = estate.price_answer

    def hook(found, url, timeout):
        box.starts.append(clock.now)
        clock.advance(0.3)
        return answer(url)
    estate.hook = hook
    return estate, box, box.memory, tables, clock


def asked(estate):
    """(product, region) of each call that went to the list, in order."""
    found = []
    for call in estate.price_calls:
        condition = parse_qs(urlsplit(call["url"]).query)["$filter"][0]
        region = [word for word in ("westeurope", "swedencentral") if f"armRegionName eq '{word}'" in condition][0]
        found.append((condition.split("productName eq '")[1].rstrip("'"), region))
    return found


def put(store, product, region, days):
    lines = (prices.Line(SERVICE, product, "Basic", "Unit Hours", "1 Hour", 9.0, region, 1),)
    store.book_put(PriceBookRecord(SERVICE, region, product, stamp(NOW - dt.timedelta(days=days)), prices.pack(lines), 1))


class TheProducts(unittest.TestCase):
    def test_the_twelve_dearest_meters_give_the_products_that_are_read_in_the_order_of_their_cost_each_in_the_region_of_its_resource(self):
        estate, box, store, tables, clock = warmed()
        self.assertEqual(box.warm_prices(), (12, 0, 0))
        expected = [(f"Tier {n}", "westeurope" if n <= 2 else "swedencentral") for n in range(1, 13)]
        self.assertEqual(asked(estate), expected, "Tier 13, 14 and 15 are not among the twelve dearest")
        for product, region in expected:
            record = store.book_get(SERVICE, region, product)
            self.assertEqual((record.read_at, record.count), (stamp(NOW), 1), product)
        self.assertEqual((box.log, box.handles), ([], {}), "it is no call of a tool, and it gives no handle")

    def test_one_query_for_the_subscription_names_the_meters_of_the_resources_that_cost_most_and_the_lines_of_the_cost_that_the_run_holds_are_not_read_again(self):
        estate, box, store, tables, clock = warmed(30)
        box._costs_of(SUB)
        cost_lines = [call for call in estate.calls if "costmanagement/query" in call["path"].lower() and [g["name"] for g in call["body"]["dataset"]["grouping"]] == ["ResourceId", "ServiceName"]]
        self.assertEqual(len(cost_lines), 1)
        box.warm_prices()
        self.assertEqual(len([call for call in estate.calls if "costmanagement/query" in call["path"].lower() and "ServiceName" in str(call["body"])]), 1, "the lines were read once for the run")
        (query,) = estate.queries()
        self.assertEqual([g["name"] for g in query["body"]["dataset"]["grouping"]], ["ResourceId", "MeterCategory", "MeterSubCategory"])
        self.assertEqual(query["body"]["dataset"]["granularity"], "None", "no days")
        names = query["body"]["dataset"]["filter"]["dimensions"]
        self.assertEqual((names["name"], names["operator"], len(names["values"])), ("ResourceId", "In", tb.WARM_RESOURCES), "the 24 dearest resources of 30, in one query")
        self.assertEqual(set(names["values"]), {estate.rows[n]["id"] for n in range(tb.WARM_RESOURCES)}, "the ids as Resource Graph gave them, and no more than the dearest")

    def test_a_meter_with_no_product_a_resource_with_no_region_word_and_a_cost_in_another_currency_are_left_out(self):
        estate, box, store, tables, clock = warmed(5, west=0)
        estate.bill.append((SUB, DAY, estate.rows[0]["id"].lower(), "Example Service", meter(category=SERVICE, subcategory=""), 500.0, 1.0))  # the dearest meter of all, with no product: a whole service
        estate.rows[1]["location"] = "Sweden Central"  # no region word
        self.assertEqual(box.warm_prices(), (4, 0, 0))
        self.assertEqual([product for product, _ in asked(estate)], ["Tier 1", "Tier 3", "Tier 4", "Tier 5"])
        estate, box, store, tables, clock = warmed(5)
        estate.currencies = {SUB: "EUR"}
        self.assertEqual((box.warm_prices(), estate.price_calls), ((0, 0, 0), []), "a bill that is not in dollars gives no product")

    def test_the_most_products_that_it_asks_for_are_the_dearest_few_and_a_product_of_two_resources_is_asked_once(self):
        estate, box, store, tables, clock = warmed(15, west=0)
        estate.bill.append((SUB, DAY, estate.rows[13]["id"].lower(), "Example Service", meter(category=SERVICE, subcategory="Tier 1"), 98.5, 1.0))  # the same product on another resource
        with mock.patch.object(tb, "WARM_PRODUCTS", 4):
            self.assertEqual(box.warm_prices(), (3, 0, 0))
        self.assertEqual([product for product, _ in asked(estate)], ["Tier 1", "Tier 2", "Tier 3"], "the four dearest meters are three products")


class TheBook(unittest.TestCase):
    def test_a_product_that_the_book_holds_fresh_is_not_read_again_and_an_older_one_is(self):
        estate, box, store, tables, clock = warmed()
        put(store, "Tier 2", "westeurope", 1)
        put(store, "Tier 5", "swedencentral", 2)
        put(store, "Tier 3", "swedencentral", 10)
        self.assertEqual(box.warm_prices(), (10, 2, 0))
        self.assertNotIn(("Tier 2", "westeurope"), asked(estate))
        self.assertNotIn(("Tier 5", "swedencentral"), asked(estate))
        self.assertIn(("Tier 3", "swedencentral"), asked(estate))
        self.assertEqual((store.book_get(SERVICE, "swedencentral", "Tier 3").read_at, store.book_get(SERVICE, "westeurope", "Tier 2").read_at), (stamp(NOW), stamp(NOW - dt.timedelta(days=1))))

    def test_a_book_that_holds_all_twelve_makes_no_call_to_the_list_at_all(self):
        estate, box, store, tables, clock = warmed()
        for n in range(1, 13):
            put(store, f"Tier {n}", "westeurope" if n <= 2 else "swedencentral", 0)
        self.assertEqual((box.warm_prices(), estate.price_calls, box.slept), ((0, 12, 0), [], []))

    def test_a_product_that_the_list_has_no_line_for_is_not_read_into_the_book_and_is_counted_with_those_that_were_not_read(self):
        estate, box, store, tables, clock = warmed()
        estate.lines = [found for found in estate.lines if found["productName"] != "Tier 3"]
        self.assertEqual(box.warm_prices(), (11, 0, 1))
        self.assertIsNone(store.book_get(SERVICE, "swedencentral", "Tier 3"))
        self.assertEqual(len(estate.price_calls), 12, "it was asked for, and the list had nothing")

    def test_without_a_book_it_does_nothing_and_asks_for_nothing(self):
        for memory in (None, MemoryStore(), object()):
            with self.subTest(memory=type(memory).__name__):
                estate, box, store, tables, clock = warmed()
                box.memory = memory
                self.assertIsNone(box.warm_prices())
                self.assertEqual((estate.calls, estate.urls), ([], []), "not a read of Azure and not of the list")


class TheTime(unittest.TestCase):
    def test_the_reads_are_one_at_a_time_and_a_gap_apart(self):
        estate, box, store, tables, clock = warmed()
        box.warm_prices()
        gaps = [later - earlier for earlier, later in zip(box.starts, box.starts[1:])]
        self.assertEqual((len(gaps), min(gaps) >= tb.WARM_GAP, tb.WARM_GAP), (11, True, 6.0))
        self.assertEqual(box.slept, [tb.WARM_GAP] * 11, "the gap is a sleep, before every read but the first")

    def test_the_whole_warm_up_ends_after_three_minutes_whatever_the_list_does(self):
        estate, box, store, tables, clock = warmed(30)
        estate.hook = taking(clock, 8.0)
        with mock.patch.object(tb, "WARM_PRODUCTS", 30), mock.patch.object(tb, "WARM_RESOURCES", 30):
            read, fresh, left = box.warm_prices()
        self.assertEqual((tb.WARM_SECONDS, fresh, read + left), (180.0, 0, 30))
        self.assertTrue(0 < read < 30, read)
        self.assertLessEqual(clock.now, tb.WARM_SECONDS, "reads of 8 seconds and gaps of 6 are 14 a product, so 12 products and a half fit")
        estate, box, store, tables, clock = warmed(30)
        estate.hook = taking(clock, 1.0)
        with mock.patch.object(tb, "WARM_PRODUCTS", 30), mock.patch.object(tb, "WARM_RESOURCES", 30):
            read, fresh, left = box.warm_prices()
        self.assertEqual((read, left), (26, 4), "a list that answers in a second gives 7 seconds a product: the 26th is read from 175 to 176, and the 27th would start after the 180")
        self.assertLessEqual(clock.now, tb.WARM_SECONDS)

    def test_a_list_that_asks_to_wait_a_minute_is_waited_for_in_the_warm_up_once_and_the_product_is_read(self):
        estate, box, store, tables, clock = warmed()
        answer = estate.hook

        def busy_once(found, url, timeout):
            if not busy_once.done:
                busy_once.done = True
                return 429, {"x-ms-ratelimit-retailprices-retry-after": "60"}, b"{}"
            return answer(found, url, timeout)
        busy_once.done = False
        estate.hook = busy_once
        self.assertEqual(box.warm_prices(), (12, 0, 0))
        self.assertEqual((60.0 in box.slept, len(estate.price_calls)), (True, 13))

    def test_a_wait_that_is_longer_than_the_warm_up_takes_is_not_taken_but_the_next_read_waits_for_it_to_pass(self):
        estate, box, store, tables, clock = warmed()
        answer = estate.hook
        asks = iter([61])

        def busy(found, url, timeout):
            wait = next(asks, None)
            return (429, {"x-ms-ratelimit-retailprices-retry-after": str(wait)}, b"{}") if wait else answer(found, url, timeout)
        estate.hook = busy
        self.assertEqual(box.warm_prices(), (11, 0, 1), "the first product was not read, and the other eleven were")
        self.assertIn(61.0, [round(seconds, 1) for seconds in box.slept], "the next read waited until the time that the list asked for had passed")
        self.assertEqual([note for note in box.notes if note.startswith("the price book")], ["the price book: the price list could not be read (the price list asked to wait 61 seconds (429))"])

    def test_a_list_that_gives_no_answer_ends_the_warm_up_at_the_first_read_and_is_no_error_and_not_a_host_that_is_down_for_the_run(self):
        estate, box, store, tables, clock = warmed()
        estate.hook = swallowing(clock)
        self.assertEqual(box.warm_prices(), (0, 0, 12))
        self.assertEqual((len(estate.price_calls), box._prices_down, [note for note in box.notes if "warmed" in note]), (1, None, []))

    def test_a_product_that_fails_is_counted_and_the_next_one_is_read(self):
        estate, box, store, tables, clock = warmed()
        answer, calls = estate.hook, []

        def failing_first(found, url, timeout):
            calls.append(url)
            return (500, {}, b"{}") if len(calls) <= 2 else answer(found, url, timeout)
        estate.hook = failing_first
        self.assertEqual(box.warm_prices(), (11, 0, 1))
        self.assertEqual(len(calls), 2 + 11, "two tries of the first product, and one read for each of the others")
        self.assertEqual(len([note for note in box.notes if note.startswith("the price book: the price list could not be read")]), 1, "a failure is a note, once")

    def test_a_fault_is_a_note_and_never_an_error_and_the_deadline_of_the_client_is_given_back_and_is_never_later_than_the_end_of_the_warm_up(self):
        estate, box, store, tables, clock = warmed()
        client, seen = box.arm.client, []

        def boom():
            seen.append(client.deadline)
            raise RuntimeError("boom")
        box._warm_keys = boom
        for before in (None, client.monotonic() + 1000, client.monotonic() + 10):
            with self.subTest(before=before):
                client.deadline = before
                self.assertEqual(box.warm_prices(), (0, 0, 0))
                during = seen[-1]
                self.assertEqual(client.deadline, before, "given back as it was")
                if before is None or before > client.monotonic() + tb.WARM_SECONDS:
                    self.assertAlmostEqual(during, client.monotonic() + tb.WARM_SECONDS, delta=5)
                else:
                    self.assertEqual(during, before, "a deadline that comes sooner is kept")
        self.assertEqual(set(note for note in box.notes if "warmed" in note), {"the price book could not be warmed (RuntimeError)"})

    def test_every_try_of_the_warm_up_is_a_line_of_the_history(self):
        estate, box, store, tables, clock = warmed()
        seen = []
        box.emit = lambda kind, **fields: seen.append((kind, fields["status"]))
        box.warm_prices()
        self.assertEqual(seen, [("prices.read", 200)] * 12)


class WhatTheInvestigationDoesWithIt(unittest.TestCase):
    """cases/investigate.py: the warm-up before the first beat, the line that says what it did, and a fault of it that does not fail the run."""

    class Toolbox(ti.FakeToolbox):
        def __init__(self, order, outcome):
            super().__init__()
            self.order, self.outcome, self.emit = order, outcome, None

        def warm_prices(self):
            self.order.append("warm")
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

        def call(self, name, arguments):
            self.order.append("call")
            return super().call(name, arguments)

    def run_with(self, outcome):
        order = []
        h = ti.Harness(toolbox=self.Toolbox(order, outcome))
        h.go()
        return h, order

    def test_the_warm_up_runs_before_the_first_call_says_one_line_and_the_toolbox_has_the_history_to_write_its_tries_to(self):
        h, order = self.run_with((7, 3, 2))
        self.assertEqual(order[:2], ["warm", "call"])
        line_of_it = "the price book: 7 products read from the price list, 3 already in the book, 2 not read"
        self.assertEqual(h.notes.count(line_of_it), 1)
        self.assertEqual([e["note"] for e in h.of("run.note") if "price book" in e["note"]], [line_of_it])
        self.assertTrue(h.result.ran)
        self.assertEqual(h.toolbox.emit.__self__, h.s.history, "a try that reaches the price list is a line of this run's History")

    def test_a_fault_in_it_is_a_note_and_the_investigation_goes_on(self):
        h, order = self.run_with(RuntimeError("boom"))
        self.assertEqual([note for note in h.notes if "price book" in note], ["the price book could not be warmed (RuntimeError)"])
        self.assertTrue(h.result.ran)
        self.assertIn("call", order)

    def test_a_store_with_no_book_says_nothing(self):
        h, order = self.run_with(None)
        self.assertEqual([note for note in h.notes if "price book" in note], [])
        self.assertTrue(h.result.ran)

    def test_a_toolbox_that_has_no_warm_up_is_left_alone(self):
        h = ti.Harness()
        h.go()
        self.assertEqual([note for note in h.notes if "price book" in note], [])
        self.assertTrue(h.result.ran)


if __name__ == "__main__":
    unittest.main()
