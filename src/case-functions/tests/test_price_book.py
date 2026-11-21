"""The price book (cases/prices.py pack and unpack, the table `mnpricebook` of cases/store.py, and the order of price_alternatives in cases/toolbox.py): what a complete read of the public price list gave is kept,
a fresh copy answers without a read of the list, an old one answers only when the list cannot be read, and a broken one is no copy. Everything is INVENTED: the services, the products, the prices; the store is the
Table store over a fake of the table service, which makes every call pass the real client and the list of calls that the store may make."""
import base64
import datetime as dt
import json
import random
import unittest
import zlib
from unittest import mock

from support import NOW

from cases import prices
from cases import toolbox as tb
from cases.http import Client
from cases.memory_store import MemoryStore, stamp
from cases.models import PriceBookRecord, StoreError
from cases.store import MAX_DATA, PRICEBOOK, TABLES, TableStore, table_calls
from test_prices import OTHER_PRODUCT, PRODUCT, SERVICE, priced, prices_of, swallowing
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

    def test_a_copy_is_fresh_while_it_is_younger_than_three_days_and_then_the_list_is_read_and_its_answer_replaces_it(self):
        self.assertEqual((prices.FRESH_DAYS, prices.STALE_DAYS), (3, 45))
        estate, box, store, tables = booked()
        keep(store, 3, read_at=stamp(NOW - dt.timedelta(days=3) + dt.timedelta(seconds=1)))
        self.assertEqual((ask(box, "price_alternatives", meter="m1")["age_days"], estate.price_calls), (2, []))
        estate, box, store, tables = booked()
        keep(store, 3)
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["source"], "age_days" in answer, len(estate.price_calls), answer["current"]["retail"]), ("list", False, 1, 0.5), "three days old is not fresh: the list answers")
        kept = store.book_get(SERVICE, REGION, PRODUCT)
        self.assertEqual((kept.read_at, kept.count, kept.complete), (stamp(NOW), 5, True), "and the book has what it read, today")
        self.assertEqual(sorted((found.meter, found.usd) for found in prices.unpack(SERVICE, kept.lines, kept.count)), [("Data Units", 0.1), ("Fixed Hours", 0.5), ("Global Hours", 0.75), ("Heavy Hours", 1.0), ("Light Hours", 0.25)])

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


if __name__ == "__main__":
    unittest.main()
