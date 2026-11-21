"""The price book (cases/prices.py pack and unpack, the table `mnpricebook` of cases/store.py, and the order of price_alternatives in cases/toolbox.py): what a complete read of the public price list gave is kept,
a fresh copy answers without a read of the list, an old one answers only when the list cannot be read, and a broken one is no copy. Everything is INVENTED: the services, the products, the prices; the store is the
Table store over a fake of the table service, which makes every call pass the real client and the list of calls that the store may make."""
import base64
import dataclasses
import datetime as dt
import json
import random
import unittest
import zlib
from unittest import mock

from support import NOW

from cases import prices, pricing
from cases import toolbox as tb
from cases.config import DEFAULT_INVESTIGATE_EVERY_DAYS
from cases.http import Client
from cases.memory_store import MemoryStore, stamp
from cases.models import PriceBookRecord, StoreError
from cases.store import MAX_DATA, PRICEBOOK, TABLES, TableStore, table_calls
from test_prices import OTHER_PRODUCT, PRODUCT, SERVICE, priced, prices_of, swallowing
from test_prices import line as list_line
from test_store import ACCOUNT, FakeTables
from test_toolbox import Clock, ask

REGION = "swedencentral"
COPY = (prices.Line(SERVICE, PRODUCT, "Basic", "Fixed Hours", "1 Hour", 0.9, REGION, 1), prices.Line(SERVICE, PRODUCT, "Basic", "Light Hours", "1 Hour", 0.45, REGION, 1),
        prices.Line(SERVICE, PRODUCT, "Plus", "Heavy Hours", "1 Hour", 1.8, REGION, 1), prices.Line(SERVICE, PRODUCT, "Plus", "Stepped Hours", "1 Hour", 2.5, REGION, 3),
        prices.Line(SERVICE, PRODUCT, "Basic", "Global Hours", "1 Hour", 1.1, prices.GLOBAL, 1))  # a copy that is not what the invented list says: its Fixed Hours cost 0.9 and not 0.5


def table_store():
    tables = FakeTables()
    client = Client(table_calls(ACCOUNT), lambda text: text, transport=tables.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
    return TableStore(client, lambda resource: "token-value", ACCOUNT, clock=lambda: NOW), tables


def keep(store, days, copy=COPY, product=PRODUCT, **more):
    """A record of the book for the product (or, with None, the whole service) of the meter of priced(), read `days` days before the run began; `more` overrides a field of the record."""
    fields = dict(service=SERVICE, region=REGION, product=product or "", read_at=stamp(NOW - dt.timedelta(days=days)), lines=prices.pack(copy), count=len(copy), complete=True)
    store.book_put(PriceBookRecord(**{**fields, **more}))


def booked(**kinds):
    """The fake estate, its toolbox with the Table store as its memory, the store, and the fake table service."""
    estate, box = priced(**kinds)
    box.memory, tables = table_store()
    return estate, box, box.memory, tables


def invented(count, seed=7):
    """Lines of an invented product list: the prices are random digits, as the real ones are, so that they compress no better than real ones do."""
    chance = random.Random(seed)
    return tuple(prices.Line(SERVICE, f"Series {n % 40} Tier", f"Size {n}", f"Meter {n % 7} Hours", "1 Hour", round(chance.uniform(0.01, 9.0), 6), REGION, 1) for n in range(count))


class TheText(unittest.TestCase):
    def test_the_lines_of_a_read_come_back_from_their_text_as_they_were(self):
        lines = (*COPY, prices.Line(SERVICE, OTHER_PRODUCT, "Elite", "Elite Hours", "1 GB", 0.000123, prices.GLOBAL, 2))
        text = prices.pack(lines)
        self.assertEqual(prices.unpack(SERVICE, text, len(lines)), lines)
        self.assertEqual(json.loads(zlib.decompress(base64.b64decode(text)))[0], [PRODUCT, "Basic", "Fixed Hours", "1 Hour", 0.9, REGION, 1], "the service is the key of the copy and is not in every line")

    def test_a_product_is_some_hundreds_of_characters_and_a_thousand_lines_fit_a_property_of_the_table_and_a_whole_large_list_does_not(self):
        self.assertLess(len(prices.pack(invented(40))), 1200)
        thousand = PriceBookRecord(SERVICE, REGION, "", "2026-11-04T12:00:00Z", prices.pack(invented(1000)), 1000)
        self.assertLess(len(thousand.to_json()), MAX_DATA, "a record that the store writes in one property")
        store, tables = table_store()
        large = PriceBookRecord(SERVICE, REGION, "", "2026-11-04T12:00:00Z", prices.pack(invented(5000)), 5000)
        self.assertGreater(len(large.to_json()), MAX_DATA)
        with self.assertRaises(StoreError):
            store.book_put(large)
        self.assertEqual(tables.calls, [], "refused before any call")

    def test_a_text_that_is_not_what_pack_made_is_no_lines(self):
        good = [[PRODUCT, "Basic", "Fixed Hours", "1 Hour", 0.5, REGION, 1]]

        def made(rows):
            return base64.b64encode(zlib.compress(json.dumps(rows).encode())).decode()

        for what, text, count in (("not base64", "this is not base64!", 1), ("not deflate", base64.b64encode(b"plain text").decode(), 1), ("not JSON", base64.b64encode(zlib.compress(b"{not json")).decode(), 1),
                                  ("a bomb", made(good * 80_000), 80_000), ("an object", made({"a": 1}), 1), ("a number", made(5), 1),
                                  ("a short row", made([[PRODUCT, "Basic"]]), 1), ("a word row", made(["abcdefg"]), 1), ("another count", made(good), 2),
                                  ("a price of nothing", made([[*good[0][:4], 0, REGION, 1]]), 1), ("a negative price", made([[*good[0][:4], -1.0, REGION, 1]]), 1),
                                  ("a price that is a text", made([[*good[0][:4], "0.5", REGION, 1]]), 1), ("a flag for a price", made([[*good[0][:4], True, REGION, 1]]), 1),
                                  ("a region that is no word", made([[*good[0][:4], 0.5, "Sweden Central", 1]]), 1), ("no step", made([[*good[0][:4], 0.5, REGION, 0]]), 1),
                                  ("a step that is a text", made([[*good[0][:4], 0.5, REGION, "1"]]), 1), ("a long word", made([["x" * 101, "Basic", "Fixed Hours", "1 Hour", 0.5, REGION, 1]]), 1),
                                  ("an empty word", made([[PRODUCT, "", "Fixed Hours", "1 Hour", 0.5, REGION, 1]]), 1)):
            with self.subTest(what):
                self.assertIsNone(prices.unpack(SERVICE, text, count))
        self.assertEqual(len(prices.unpack(SERVICE, made(good), 1)), 1, "and the same row is a line when it is right")


class TheTable(unittest.TestCase):
    def test_a_record_is_kept_in_a_table_of_its_own_that_is_made_by_the_first_write_and_never_by_a_read_and_comes_back_as_it_was(self):
        store, tables = table_store()
        self.assertIsNone(store.book_get(SERVICE, REGION, PRODUCT))
        self.assertEqual(tables.tables, {}, "a read makes no table")
        keep(store, 1)
        self.assertEqual((list(tables.tables), PRICEBOOK, PRICEBOOK in TABLES), ([PRICEBOOK], "mnpricebook", True))
        record = store.book_get(SERVICE, REGION, PRODUCT)
        self.assertEqual((record.service, record.region, record.product, record.read_at, record.count, record.complete), (SERVICE, REGION, PRODUCT, "2026-11-03T12:00:00Z", 5, True))
        self.assertEqual(prices.unpack(SERVICE, record.lines, record.count), COPY)

    def test_the_row_is_the_hash_of_the_three_words_and_a_key_that_differs_in_any_of_them_is_another_row(self):
        store, tables = table_store()
        keep(store, 1)
        keep(store, 1, product=None)
        keep(store, 1, product=OTHER_PRODUCT, copy=COPY[:1])
        keep(store, 1, region="global", copy=COPY[:1])
        ((partition, row), *_), rows = list(tables.tables[PRICEBOOK]), list(tables.tables[PRICEBOOK])
        self.assertEqual((len(rows), partition), (4, "b"))
        self.assertRegex(row, r"^[0-9a-f]{32}$", "the words of a platform name hold spaces and marks that a key may not")
        self.assertIsNone(store.book_get(SERVICE, "westeurope", PRODUCT))
        self.assertEqual(store.book_get(SERVICE, REGION, "").product, "", "the whole service has no product")
        keep(store, 9)
        self.assertEqual((len(tables.tables[PRICEBOOK]), store.book_get(SERVICE, REGION, PRODUCT).read_at), (4, "2026-10-26T12:00:00Z"), "a read of the same words replaces the record of it")
        self.assertLess(len(next(iter(tables.tables[PRICEBOOK].values()))[0]["data"]), MAX_DATA)


class TheOrderOfTheTool(unittest.TestCase):
    def test_a_fresh_copy_answers_without_a_read_of_the_list_and_says_that_it_is_a_copy_and_how_old(self):
        estate, box, store, tables = booked()
        keep(store, 2)
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["source"], answer["age_days"], answer["complete"], answer["match"], estate.price_calls), ("book", 2, True, "found", []))
        self.assertEqual(answer["current"], {"line": "p2", "retail": 0.9, "paid": 0.416667, "rate_ratio": 0.463}, "the copy's own prices, and the rate that the bill shows against them")
        self.assertEqual(box.retail, {"m1": 0.9})
        self.assertEqual({found["meter"] for found in prices_of(answer)}, {"Light Hours", "Fixed Hours", "Global Hours", "Heavy Hours", "Stepped Hours"})
        self.assertNotIn("ended", answer)

    def test_a_copy_is_fresh_while_it_is_younger_than_ten_days_and_then_the_list_is_read_and_its_answer_replaces_it(self):
        # The limit was 3 days: the investigation runs every 7 (config.DEFAULT_INVESTIGATE_EVERY_DAYS), so a copy of the last run was always stale at the next one and every run paid for the warm-up. A list
        # price changes rarely, and the limit of the list is for the reads that cannot be spared; the stale limit stays.
        self.assertEqual((prices.FRESH_DAYS, prices.STALE_DAYS), (10, 45))
        self.assertGreater(prices.FRESH_DAYS, DEFAULT_INVESTIGATE_EVERY_DAYS, "a copy that is fresh for less than the days between two investigations is stale at every one")
        estate, box, store, tables = booked()
        keep(store, 10, read_at=stamp(NOW - dt.timedelta(days=10) + dt.timedelta(seconds=1)))
        self.assertEqual((ask(box, "price_alternatives", meter="m1")["age_days"], estate.price_calls), (9, []))
        estate, box, store, tables = booked()
        keep(store, DEFAULT_INVESTIGATE_EVERY_DAYS)
        self.assertEqual((ask(box, "price_alternatives", meter="m1")["age_days"], estate.price_calls), (7, []), "what the last weekly run read answers at the next one")
        estate, box, store, tables = booked()
        keep(store, 10)
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["source"], "age_days" in answer, len(estate.price_calls), answer["current"]["retail"]), ("list", False, 1, 0.5), "ten days old is not fresh: the list answers")
        kept = store.book_get(SERVICE, REGION, PRODUCT)
        self.assertEqual((kept.read_at, kept.count, kept.complete), (stamp(NOW), 5, True), "and the book has what it read, today")
        self.assertEqual(sorted((found.meter, found.usd) for found in prices.unpack(SERVICE, kept.lines, kept.count)), [("Data Units", 0.1), ("Fixed Hours", 0.5), ("Global Hours", 0.75), ("Heavy Hours", 1.0), ("Light Hours", 0.25)])

    def test_a_copy_that_was_written_in_the_future_is_no_copy_but_a_clock_that_is_a_day_out_is_no_reason_to_refuse_one(self):
        # A copy from the future had a negative age, and a negative age is younger than any limit: it was fresh for ever, and its age said 0.
        for ahead, served in ((dt.timedelta(hours=2), True), (dt.timedelta(days=1), True), (dt.timedelta(days=1, seconds=1), False), (dt.timedelta(days=400), False)):
            with self.subTest(ahead=ahead):
                estate, box, store, tables = booked()
                keep(store, 0, read_at=stamp(NOW + ahead))
                answer = ask(box, "price_alternatives", meter="m1")
                self.assertEqual((answer["source"], len(estate.price_calls)), ("book", 0) if served else ("list", 1))
                if served:
                    self.assertEqual(answer["age_days"], 0)
        estate, box, store, tables = booked()
        keep(store, 0, read_at=stamp(NOW + dt.timedelta(days=3)))
        estate.failure = 500
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable", "code": "Failed"}, "and it is no stand-in for a list that cannot be read")

    def test_a_list_that_cannot_be_read_gives_the_old_copy_with_its_age_and_the_failure_is_a_note_and_the_run_reads_the_book_once(self):
        estate, box, store, tables = booked()
        keep(store, 10)
        estate.failure = 500
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["source"], answer["age_days"], answer["match"], len(estate.price_calls)), ("book", 10, "found", 2))
        notes = [note for note in box.notes if note.startswith("price_alternatives")]
        self.assertEqual(len(notes), 2)
        self.assertIn("could not be read", notes[0])
        self.assertEqual(notes[1], "price_alternatives: a copy of the price book, 10 days old, is shown instead")
        reads = len(tables.calls)
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), answer)
        self.assertEqual((len(estate.price_calls), len(tables.calls)), (2, reads), "the run keeps what it got: neither the list nor the book is asked again")

    def test_a_list_that_asks_for_a_wait_that_a_call_cannot_take_gives_the_old_copy_too(self):
        estate, box, store, tables = booked()
        keep(store, 30)
        estate.failure, estate.wait = 429, 60
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["source"], answer["age_days"], len(estate.price_calls)), ("book", 30, 1))
        self.assertTrue(any("the price list asked to wait 60 seconds" in note for note in box.notes))

    def test_a_read_that_a_failure_cut_short_gives_the_old_copy_of_the_whole_list_and_one_that_a_cap_cut_short_does_not(self):
        estate, box, store, tables = booked()
        keep(store, 10)
        estate.page_size = 2
        estate.hook = lambda found, url, timeout: (429, {"retry-after": "30"}, b"{}") if "$skip=" in url else found.price_answer(url)
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["source"], answer["age_days"], answer["complete"], answer["lines"]), ("book", 10, True, 5), "the first page was read and the second was refused")
        self.assertEqual([note for note in box.notes if "shown instead" in note], ["price_alternatives: a copy of the price book, 10 days old, is shown instead"])
        estate, box, store, tables = booked()
        keep(store, 10)
        estate.page_size = 2
        with mock.patch.object(prices, "MAX_PAGES", 2):
            answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["source"], answer["complete"], answer["lines"]), ("list", False, 3), "a cap is no failure: what was read is shown, as it always was (four lines, three in the unit of the meter)")

    def test_a_copy_that_is_forty_five_days_old_is_no_copy_and_one_of_forty_four_is(self):
        for days, served in ((44, True), (45, False), (200, False)):
            with self.subTest(days=days):
                estate, box, store, tables = booked()
                keep(store, days)
                estate.failure = 500
                answer = ask(box, "price_alternatives", meter="m1")
                if served:
                    self.assertEqual((answer["source"], answer["age_days"]), ("book", days))
                else:
                    self.assertEqual(answer, {"error": "unavailable", "code": "Failed"})

    def test_a_record_of_a_read_that_was_not_complete_is_no_copy(self):
        estate, box, store, tables = booked()
        keep(store, 1, complete=False)
        self.assertEqual((ask(box, "price_alternatives", meter="m1")["source"], len(estate.price_calls)), ("list", 1))

    def test_a_broken_record_is_no_copy_and_the_call_goes_to_the_list(self):
        words = dict(service=SERVICE, region=REGION, product=PRODUCT)
        for what, change in (("a text that is no lines", dict(lines="garbage")), ("a time that is no time", dict(read_at="yesterday")), ("another count", dict(count=99)),
                             ("the words of another product", dict(product=OTHER_PRODUCT)), ("the words of another region", dict(region="westeurope")), ("no lines", dict(lines=prices.pack(()), count=0))):
            with self.subTest(what):
                estate, box, store, tables = booked()
                keep(store, 1)
                if "product" in change or "region" in change:
                    # the row of the asked words holds a record that names others: the hash of the words found it, and the record does not say the same
                    row = next(iter(tables.tables[PRICEBOOK].values()))[0]
                    row["data"] = PriceBookRecord(**{**words, "read_at": stamp(NOW), "lines": prices.pack(COPY), "count": 5, **change}).to_json()
                else:
                    keep(store, 1, **change)
                answer = ask(box, "price_alternatives", meter="m1")
                self.assertEqual((answer["source"], len(estate.price_calls)), ("list", 1), what)

    def test_a_store_that_cannot_be_read_is_no_book_and_costs_the_call_nothing(self):
        for failure in (StoreError("the table service is not there", 503), RuntimeError("anything")):
            with self.subTest(failure=type(failure).__name__):
                estate, box, store, tables = booked()
                box.memory = mock.Mock(book_get=mock.Mock(side_effect=failure), book_put=mock.Mock(side_effect=failure))
                answer = ask(box, "price_alternatives", meter="m1")
                self.assertEqual((answer["source"], answer["match"], len(estate.price_calls)), ("list", "found", 1))
                self.assertEqual(len([note for note in box.notes if "the price book could not keep this read" in note]), 1, "a write that fails is a note and nothing more")

    def test_only_a_complete_read_with_some_lines_is_kept(self):
        estate, box, store, tables = booked()
        estate.page_size = 2
        with mock.patch.object(prices, "MAX_PAGES", 2):
            self.assertFalse(ask(box, "price_alternatives", meter="m1")["complete"])
        self.assertEqual(tables.tables, {}, "a read that a cap ended is not kept")
        estate, box, store, tables = booked()
        estate.lines = []
        self.assertEqual(ask(box, "price_alternatives", meter="m1", within="service")["lines"], 0)
        self.assertEqual(tables.tables, {}, "a list with no line is no copy")

    def test_the_service_and_the_product_are_two_rows_of_the_book(self):
        estate, box, store, tables = booked()
        ask(box, "price_alternatives", meter="m1", within="service")
        ask(box, "price_alternatives", meter="m1")
        self.assertEqual((store.book_get(SERVICE, REGION, "").count, store.book_get(SERVICE, REGION, PRODUCT).count), (6, 5), "the whole service has both products, and the product its own")

    def test_a_trial_read_of_code_is_kept_too_and_a_trial_is_answered_from_a_fresh_copy(self):
        estate, box, store, tables = booked()
        box.trial = True
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["source"], "list")
        self.assertEqual(store.book_get(SERVICE, REGION, PRODUCT).count, 5)
        estate, box, store, tables = booked()
        keep(store, 1)
        box.trial = True
        self.assertEqual((ask(box, "price_alternatives", meter="m1")["source"], estate.price_calls), ("book", []))

    def test_a_host_that_gave_no_answer_does_not_keep_a_fresh_copy_of_another_set_of_prices_from_answering(self):
        estate, box, store, tables = booked()
        clock = Clock()
        box.monotonic, box.arm.client.sleep = clock, clock.advance
        estate.hook = swallowing(clock)
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable"})
        keep(store, 1, product=None)
        answer = ask(box, "price_alternatives", meter="m1", within="service")
        self.assertEqual((answer["source"], len(estate.price_calls)), ("book", 1), "the host that gives no answer is not asked again, and the book needs no host")
        self.assertEqual([note for note in box.notes if "shown instead" in note], [], "a fresh copy is no stand-in for a failure: the failure is not even said for it")

    def test_without_a_book_nothing_changes(self):
        for memory in (None, MemoryStore(), object()):
            with self.subTest(memory=type(memory).__name__):
                estate, box = priced()
                box.memory = memory
                answer = ask(box, "price_alternatives", meter="m1")
                self.assertEqual((answer["source"], "age_days" in answer, len(estate.price_calls)), ("list", False, 1))
        self.assertFalse(hasattr(MemoryStore(), "book_get") or hasattr(MemoryStore(), "book_put"), "the memory store of the tests of the investigation has no book: with one, the warm-up would run in every one of them")

    def test_the_description_says_where_the_lines_come_from_and_when_a_copy_is_stale(self):
        text = tb.TOOLS["price_alternatives"].description
        self.assertIn(f"source says list (read now) or book (a copy, age_days old; over {prices.FRESH_DAYS} days it is stale, shown because the list could not be read)", text)
        self.assertLessEqual(len(text), 1000)


TINY = (prices.Line(SERVICE, PRODUCT, "Basic", "Fixed Hours", "1 Hour", 0.9, REGION, 1), prices.Line(SERVICE, PRODUCT, "Basic", "Tiny Hours", "1 Hour", 0.3, REGION, 1))  # one that the bill (0.4167 an hour) would save by


class TheAgeThatReachesTheOwner(unittest.TestCase):
    """A copy of the price book may be weeks old. The toolbox keeps its age with what it showed (Toolbox.ages: the meter and the price handles), so that the code that prices a switch says it with the figure
    (cases/pricing.py), and a read of the list or a copy of today says nothing."""

    def test_a_copy_of_nine_days_registers_its_age_with_the_meter_and_with_every_price_that_it_showed(self):
        estate, box, store, tables = booked()
        keep(store, 9)
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["source"], answer["age_days"], estate.price_calls), ("book", 9, []))
        self.assertEqual((sorted(box.prices), box.ages), (["p1", "p2", "p3", "p4"], dict.fromkeys(["m1", "p1", "p2", "p3", "p4"], 9)), "the price with steps has no handle, and no age")

    def test_a_stale_copy_that_stands_in_for_a_list_that_cannot_be_read_registers_its_age_too(self):
        estate, box, store, tables = booked()
        keep(store, 30)
        estate.failure = 500
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["age_days"], 30)
        self.assertEqual(box.ages, dict.fromkeys(["m1", "p1", "p2", "p3", "p4"], 30))

    def test_a_read_of_the_list_and_a_copy_of_less_than_a_day_leave_no_age_and_a_copy_of_a_day_or_more_leaves_it(self):
        for hours, days in ((None, None), (0, None), (23, None), (24, 1), (25, 1), (47, 1), (48, 2), (24 * 9, 9)):
            with self.subTest(hours=hours):
                estate, box, store, tables = booked()
                if hours is not None:
                    keep(store, 0, read_at=stamp(NOW - dt.timedelta(hours=hours)))
                answer = ask(box, "price_alternatives", meter="m1")
                self.assertEqual((answer["source"], answer.get("age_days")), ("list", None) if hours is None else ("book", hours // 24))
                self.assertEqual(box.ages, {} if days is None else dict.fromkeys(["m1", "p1", "p2", "p3", "p4"], days))

    def test_a_later_ask_that_shows_the_same_prices_from_the_list_takes_their_age_away(self):
        estate, box, store, tables = booked()
        keep(store, 9)
        ask(box, "price_alternatives", meter="m1")
        self.assertEqual(box.ages["m1"], 9)
        answer = ask(box, "price_alternatives", meter="m1", within="service")
        self.assertEqual((answer["source"], box.ages, box.retail), ("list", {}, {"m1": 0.5}), "the list showed the meter and its lines again: nothing of the copy is left to say")

    def test_a_later_ask_that_finds_that_the_meter_has_steps_takes_its_age_away_with_its_list_price(self):
        steps = tuple(dataclasses.replace(found, tiers=3) if found.meter == "Fixed Hours" else found for found in COPY)
        estate, box, store, tables = booked()
        keep(store, 9)
        ask(box, "price_alternatives", meter="m1")
        keep(store, 5, product=None, copy=steps)
        answer = ask(box, "price_alternatives", meter="m1", within="service")
        self.assertEqual((answer["source"], answer["current"]["steps"], "m1" in box.retail, "m1" in box.ages), ("book", 3, False, False))

    def test_a_later_ask_whose_read_was_cut_before_the_line_of_the_meter_leaves_the_age_of_the_list_price_that_stays(self):
        estate, box, store, tables = booked()
        keep(store, 9)
        estate.page_size = 1
        estate.lines.insert(0, estate.lines.pop())  # the other product first: a read of the whole service that ends at its first page does not reach the line of the meter
        ask(box, "price_alternatives", meter="m1")
        with mock.patch.object(prices, "MAX_PAGES", 1):
            answer = ask(box, "price_alternatives", meter="m1", within="service")
        self.assertEqual((answer["match"], answer["complete"], box.retail, box.ages["m1"]), ("none", False, {"m1": 0.9}, 9))

    def test_the_age_goes_from_the_copy_through_the_figure_to_the_words_that_say_what_it_rests_on_and_a_read_of_the_list_says_nothing_of_it(self):
        def basis_of(box, answer):
            tiny = next(found["price"] for found in prices_of(answer) if found["meter"] == "Tiny Hours")
            scope = box.meters["m1"].scope
            change = pricing.parse({"action": "switch", "effects": [{"handle": scope, "meters": ["m1"], "remains": {"form": "alternative", "price": tiny}}], "how": "Take the tiny one."})
            found = pricing.price(change, (scope,), box, {scope: 70.0}, None, lambda text: text)
            digest = {pricing.KEY: pricing.digest(change, found, scope)}
            return digest[pricing.KEY]["price"], pricing.saved(digest).basis

        estate, box, store, tables = booked()
        keep(store, 9, copy=TINY)
        price, basis = basis_of(box, ask(box, "price_alternatives", meter="m1"))
        self.assertEqual(price["listAge"], 9)
        self.assertIn("Your bill pays about 46 percent of the list price of Fixed Hours as it was 9 days ago. Meternaut prices Tiny Hours both at its list price and at 46 percent of it.", basis)
        estate, box, store, tables = booked()
        estate.lines.append(list_line("Basic", "Tiny Hours", 0.3))
        price, basis = basis_of(box, ask(box, "price_alternatives", meter="m1"))
        self.assertNotIn("listAge", price)
        self.assertNotIn(" ago", basis)


if __name__ == "__main__":
    unittest.main()
