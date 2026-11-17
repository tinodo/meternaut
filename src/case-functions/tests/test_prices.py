"""price_alternatives and cases/prices.py, against a fake estate and an INVENTED price list that answer at the level of the transport: every call also passes the real client and the Watch's list of
calls. Every service, product, SKU, meter, unit and price in it is invented."""
import json
import re
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import support  # noqa: F401  (it puts the app on the path)
from cases import prices
from cases import toolbox as tb
from cases.http import PRICE_CALL, PRICES_HOST, PRICES_PATH, Client, Refused, allowed_calls
from cases.redact import Redactor
from test_toolbox import FORBIDDEN_WORDS, HOSTILE, MARKERS, SENTENCE, SUB, ask, row, toolbox
from test_toolbox_meters import FIXED, WIDGET, BillingEstate, billed, meter, widgets

SERVICE, PRODUCT, OTHER_PRODUCT = "Example Compute", "Standard Tier", "Premium Tier"
VERDICTS = ("cheaper", "cheapest", "better", "best", "save", "saving", "waste", "recommend", "should", "worth", "instead")


def line(sku="Basic", name="Fixed Hours", usd=0.5, unit="1 Hour", product=PRODUCT, region="swedencentral", service=SERVICE, tier=0, kind="Consumption", currency="USD"):
    """One line of the price list, in the fields that the list has."""
    return {"currencyCode": currency, "tierMinimumUnits": tier, "retailPrice": usd, "unitPrice": usd, "armRegionName": region, "location": "Invented Place", "meterId": "0000", "productName": product,
            "skuName": sku, "meterName": name, "serviceName": service, "unitOfMeasure": unit, "type": kind}


def catalogue():
    """The invented list of one service: five prices of one product in one region (one of them in another unit, one holding in every region), a reservation, and another product."""
    return [line("Basic", "Fixed Hours", 0.5), line("Basic", "Light Hours", 0.25), line("Plus", "Heavy Hours", 1.0), line("Basic", "Data Units", 0.1, unit="1 GB"),
            line("Basic", "Global Hours", 0.75, region="Global"), line("Basic", "Fixed Hours", 3000.0, kind="Reservation"), line("Elite", "Elite Hours", 2.0, product=OTHER_PRODUCT)]


class PricedEstate(BillingEstate):
    """The estate of test_toolbox_meters with an invented price list on the host that the tool reads. The list answers a page at a time, for the service, the regions and the product that the filter of the call
    names (it does not filter the kind of price, so that a line that is no pay-as-you-go price reaches the parser)."""

    def __init__(self):
        super().__init__()
        self.lines, self.page_size, self.failure, self.urls, self.price_calls, self.link, self.body = catalogue(), 1000, None, [], [], None, None

    def __call__(self, method, url, headers, data, timeout):
        parts = urlsplit(url)
        self.urls.append(url)
        if parts.netloc != PRICES_HOST:
            return super().__call__(method, url, headers, data, timeout)
        self.price_calls.append({"method": method, "url": url, "path": parts.path, "query": parse_qs(parts.query), "headers": dict(headers)})
        if self.failure:
            return self._refused(self.failure)
        if self.body is not None:
            return 200, {}, json.dumps(self.body).encode("utf-8")
        condition = parse_qs(parts.query)["$filter"][0]
        service = re.search(r"serviceName eq '([^']*)'", condition).group(1)
        regions = re.findall(r"armRegionName eq '([^']*)'", condition)
        product = re.search(r"productName eq '([^']*)'", condition)
        kept = [found for found in self.lines if found["serviceName"] == service and found["armRegionName"] in regions and (product is None or found["productName"] == product.group(1))]
        skip = int(parse_qs(parts.query).get("$skip", ["0"])[0])
        more = skip + self.page_size < len(kept)
        link = self.link or (url.split("&$skip=")[0] + f"&$skip={skip + self.page_size}" if more else None)
        return 200, {"content-type": "application/json"}, json.dumps({"BillingCurrency": "USD", "Items": kept[skip:skip + self.page_size], "NextPageLink": link, "Count": 1}).encode("utf-8")


def priced(estate=None, words=FIXED, usd=10.0, quantity=24.0, location=None):
    """An estate with one resource that is billed for one meter (70 dollars and 168 hours over the 7 days that cost_meters is asked for), its toolbox, and the handle of the meter."""
    estate = estate or PricedEstate()
    found = widgets(1)
    estate.rows, estate.cost_rows, estate.definitions = found.rows, found.cost_rows, found.definitions
    if location is not None:
        estate.rows[0]["location"] = location
    billed(estate, estate.rows[0]["id"].lower(), words, [usd] * 7, quantity)
    box = toolbox(estate)
    ask(box, "list_resources", type=WIDGET)
    ask(box, "cost_meters", handle="r1", days=7)
    return estate, box


def prices_of(answer):
    return [dict(zip(answer["cols"], row)) for row in answer["rows"]]


class TheAddress(unittest.TestCase):
    def test_the_address_names_the_one_path_of_the_one_host_and_holds_typed_words_only(self):
        url = prices.address(SERVICE, "swedencentral", PRODUCT)
        parts = urlsplit(url)
        self.assertEqual((parts.scheme, parts.netloc, parts.path), ("https", PRICES_HOST, PRICES_PATH))
        query = parse_qs(parts.query)
        self.assertEqual(query["api-version"], ["2023-01-01-preview"])
        self.assertEqual(query["currencyCode"], ["'USD'"])
        self.assertEqual(query["$filter"], [f"serviceName eq '{SERVICE}' and priceType eq 'Consumption' and (armRegionName eq 'swedencentral' or armRegionName eq 'Global') and productName eq '{PRODUCT}'"])
        self.assertNotIn("productName", parse_qs(urlsplit(prices.address(SERVICE, "swedencentral", None)).query)["$filter"][0])

    def test_a_word_that_is_not_made_of_the_marks_of_a_platform_name_makes_no_address(self):
        for service, region, product in (("Example' or 1 eq 1 or serviceName eq '", "swedencentral", None), (SERVICE, "swedencentral", "x' and 'a' eq 'a"), (SERVICE, "Sweden Central", None),
                                         (SERVICE, "swedencentral;", None), ("", "swedencentral", None), (SERVICE, "x" * 25, None), ("a\\b", "swedencentral", None), ("a%27b", "swedencentral", None),
                                         ("a b" + " c" * 10, "swedencentral", None)):
            with self.subTest(service=service[:20], region=region, product=product):
                with self.assertRaises(ValueError):
                    prices.address(service, region, product)

    def test_the_region_global_is_the_one_that_the_list_writes_with_a_capital(self):
        self.assertEqual([prices.region_of(word) for word in ("swedencentral", "global", "Global", "Sweden", "", None, 5)], ["swedencentral", "Global", None, None, None, None, None])
        self.assertIn("armRegionName eq 'Global'", parse_qs(urlsplit(prices.address(SERVICE, "Global", None)).query)["$filter"][0])

    def test_the_watch_may_make_this_one_call_and_nothing_wider_on_the_host(self):
        client = Client(allowed_calls(), Redactor(), transport=lambda *a: (200, {}, b"{}"), sleep=lambda s: None)
        client.check("GET", prices.address(SERVICE, "swedencentral", None))
        for method, url in (("POST", f"https://{PRICES_HOST}{PRICES_PATH}"), ("PUT", f"https://{PRICES_HOST}{PRICES_PATH}"), ("DELETE", f"https://{PRICES_HOST}{PRICES_PATH}"),
                            ("PATCH", f"https://{PRICES_HOST}{PRICES_PATH}"), ("GET", f"https://{PRICES_HOST}{PRICES_PATH}/"), ("GET", f"https://{PRICES_HOST}{PRICES_PATH}x"),
                            ("GET", f"https://{PRICES_HOST}/api/retail"), ("GET", f"https://{PRICES_HOST}/api/other"), ("GET", f"https://{PRICES_HOST}/"), ("GET", f"http://{PRICES_HOST}{PRICES_PATH}"),
                            ("GET", f"https://{PRICES_HOST}:8443{PRICES_PATH}"), ("GET", f"https://user@{PRICES_HOST}{PRICES_PATH}"), ("GET", f"https://{PRICES_HOST}.example.com{PRICES_PATH}"),
                            ("GET", f"https://example.com/{PRICES_HOST}{PRICES_PATH}"), ("GET", f"https://{PRICES_HOST.upper()}{PRICES_PATH}")):
            with self.assertRaises(Refused, msg=f"{method} {url}"):
                client.check(method, url)
        self.assertEqual([(method, pattern.pattern) for method, pattern in allowed_calls() if PRICES_HOST in pattern.pattern.replace("\\", "")], [("GET", re.escape(f"https://{PRICES_HOST}{PRICES_PATH}"))])
        self.assertIn(PRICE_CALL, allowed_calls())


class TheReads(unittest.TestCase):
    def test_a_read_follows_the_next_page_and_keeps_only_pay_as_you_go_prices_of_the_list(self):
        estate = PricedEstate()
        estate.page_size = 2
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None, jitter=lambda: 0.5)
        book = prices.read(client, SERVICE, "swedencentral", PRODUCT)
        self.assertEqual((len(estate.price_calls), book.complete), (3, True), "six items of the list, two a page")
        self.assertEqual(sorted((found.sku, found.meter, found.usd) for found in book.lines),
                         [("Basic", "Data Units", 0.1), ("Basic", "Fixed Hours", 0.5), ("Basic", "Global Hours", 0.75), ("Basic", "Light Hours", 0.25), ("Plus", "Heavy Hours", 1.0)],
                         "the reservation is not a pay-as-you-go price")
        self.assertEqual({found.service for found in book.lines}, {SERVICE})
        self.assertEqual([call["method"] for call in estate.price_calls], ["GET"] * 3)

    def test_a_read_ends_at_the_cap_of_pages_and_says_that_it_did_not_read_the_whole_list(self):
        estate = PricedEstate()
        estate.page_size = 2
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None)
        with mock.patch.object(prices, "MAX_PAGES", 2):
            book = prices.read(client, SERVICE, "swedencentral", PRODUCT)
        self.assertEqual((len(estate.price_calls), book.complete, len(book.lines)), (2, False, 4), "two pages of two items hold four prices")

    def test_a_read_keeps_at_most_the_cap_of_lines_and_stops_reading(self):
        estate = PricedEstate()
        estate.page_size = 2
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None)
        with mock.patch.object(prices, "MAX_LINES", 3):
            book = prices.read(client, SERVICE, "swedencentral", PRODUCT)
        self.assertEqual((len(book.lines), book.complete, len(estate.price_calls)), (3, False, 2))

    def test_a_read_ends_at_the_time_that_it_may_take(self):
        estate = PricedEstate()
        estate.page_size = 1
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None)
        clock = iter([0.0, 1.0, prices.SECONDS + 1.0, prices.SECONDS + 2.0])
        book = prices.read(client, SERVICE, "swedencentral", PRODUCT, lambda: next(clock))
        self.assertEqual((len(estate.price_calls), book.complete), (1, False))

    def test_a_price_that_has_steps_is_one_line_with_its_first_price_and_the_number_of_steps_and_a_price_given_twice_with_two_values_is_left_out(self):
        estate = PricedEstate()
        estate.lines = [line("Basic", "Stepped Units", 0.4, unit="1 GB"), line("Basic", "Stepped Units", 0.3, unit="1 GB", tier=100), line("Basic", "Stepped Units", 0.2, unit="1 GB", tier=1000),
                        line("Basic", "Twice Units", 0.4), line("Basic", "Twice Units", 0.6), line("Basic", "Late Units", 0.3, tier=50), line("Basic", "Same Units", 0.3), line("Basic", "Same Units", 0.3),
                        line("Basic", "Negative", -1.0), line("Basic", "Not A Number", "free"), line("Basic", "x" * (prices.MAX_TEXT + 1)), line("Basic", "Foreign", 1.0, currency="EUR")]
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None)
        book = prices.read(client, SERVICE, "swedencentral", PRODUCT)
        self.assertEqual(sorted((found.meter, found.usd, found.tiers) for found in book.lines), [("Same Units", 0.3, 1), ("Stepped Units", 0.4, 3)])

    def test_an_item_that_is_not_a_line_is_passed_over(self):
        estate = PricedEstate()
        estate.body = {"Items": ["text", None, 5, [], {"type": "Consumption"}, line("Basic", "Fixed Hours", 0.5)], "NextPageLink": None}
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None)
        self.assertEqual([(found.meter, found.usd) for found in prices.read(client, SERVICE, "swedencentral", PRODUCT).lines], [("Fixed Hours", 0.5)])

    def test_an_answer_that_is_not_the_list_and_a_next_page_somewhere_else_are_failures_and_nothing_is_sent_there(self):
        for body in ({"Items": "text"}, {"Other": []}, [], {"Items": [], "NextPageLink": f"https://example.com{PRICES_PATH}?x=1"}, {"Items": [], "NextPageLink": f"http://{PRICES_HOST}{PRICES_PATH}"},
                     {"Items": [], "NextPageLink": f"https://{PRICES_HOST}/api/other"}):
            estate = PricedEstate()
            estate.body = body
            client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None)
            with self.assertRaises(prices.HttpError, msg=str(body)):
                prices.read(client, SERVICE, "swedencentral", PRODUCT)
            self.assertEqual([url for url in estate.urls if not url.startswith(f"https://{PRICES_HOST}")], [], "no call went anywhere else")

    def test_the_read_sends_no_token_and_says_what_it_is(self):
        estate, box = priced()
        ask(box, "price_alternatives", meter="m1")
        (call,) = estate.price_calls
        self.assertEqual(sorted(call["headers"]), ["Accept", "User-Agent"], "no Authorization: the list is public")
        self.assertTrue(call["headers"]["User-Agent"].startswith("Meternaut-Watch/"))


class TheTable(unittest.TestCase):
    def test_a_meter_gives_the_prices_of_its_product_in_its_unit_the_lowest_first_and_the_line_of_the_meter_itself_with_the_rate_that_the_bill_shows(self):
        estate, box = priced()
        answer = ask(box, "price_alternatives", meter="m1")
        # The bill paid 70 dollars for 168 hours: 0.416667 an hour. The list has 0.5 for the meter's own words, so the rate ratio is 0.8333.
        self.assertEqual({key: answer[key] for key in ("meter", "service", "region", "within", "unit", "match", "lines", "other_units", "complete", "offset", "returned")},
                         {"meter": "m1", "service": SERVICE, "region": "swedencentral", "within": "product", "unit": "1 Hour", "match": "found", "lines": 4, "other_units": 1, "complete": True,
                          "offset": 0, "returned": 4})
        self.assertEqual(answer["current"], {"line": "p2", "retail": 0.5, "paid": 0.416667, "rate_ratio": 0.8333})
        self.assertEqual(answer["same"], {"product": PRODUCT})
        self.assertEqual(answer["cols"], ["price", "sku", "meter", "usd", "region"])
        self.assertEqual(answer["rows"], [["p1", "Basic", "Light Hours", 0.25, "swedencentral"], ["p2", "Basic", "Fixed Hours", 0.5, "swedencentral"], ["p3", "Basic", "Global Hours", 0.75, "global"],
                                          ["p4", "Plus", "Heavy Hours", 1, "swedencentral"]])
        self.assertNotIn("next_offset", answer)
        self.assertEqual(len(estate.price_calls), 1)

    def test_the_address_of_a_read_holds_the_words_of_the_bill_and_the_region_of_the_resource_and_nothing_else(self):
        estate, box = priced()
        ask(box, "price_alternatives", meter="m1")
        asked = urlsplit(estate.price_calls[0]["url"])
        self.assertEqual(parse_qs(asked.query)["$filter"], [f"serviceName eq '{SERVICE}' and priceType eq 'Consumption' and (armRegionName eq 'swedencentral' or armRegionName eq 'Global') and productName eq '{PRODUCT}'"])
        self.assertEqual(parse_qs(asked.query)["currencyCode"], ["'USD'"])
        text = json.dumps(estate.price_calls)
        for private in (SUB, "w1", "rg-app", "Example Service", "subscriptions"):
            self.assertNotIn(private, text, "nothing of the estate leaves the app: not an id, a name or a group, and not the service of the cost line")

    def test_the_whole_service_is_every_product_of_it_and_is_read_once_more(self):
        estate, box = priced()
        ask(box, "price_alternatives", meter="m1")
        answer = ask(box, "price_alternatives", meter="m1", within="service")
        self.assertEqual((answer["within"], answer["lines"], answer["other_units"], len(estate.price_calls)), ("service", 5, 1, 2))
        self.assertNotIn("productName", parse_qs(urlsplit(estate.price_calls[1]["url"]).query)["$filter"][0])
        self.assertEqual([found["meter"] for found in prices_of(answer)], ["Light Hours", "Fixed Hours", "Global Hours", "Heavy Hours", "Elite Hours"])
        self.assertEqual(prices_of(answer)[-1]["product"], OTHER_PRODUCT)

    def test_a_second_ask_is_free_and_so_is_another_meter_of_the_same_service_region_and_product(self):
        estate, box = priced()
        first = ask(box, "price_alternatives", meter="m1")
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), first)
        self.assertEqual(ask(box, "price_alternatives", meter="m1", offset=0), first)
        estate.lines.append(line("Basic", "Late Hours", 9.0))
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), first, "the list is read once in a run")
        self.assertEqual(len(estate.price_calls), 1)

    def test_a_handle_is_the_same_for_the_same_line_in_every_answer_and_the_register_holds_what_code_needs(self):
        estate, box = priced()
        ask(box, "price_alternatives", meter="m1")
        wide = ask(box, "price_alternatives", meter="m1", within="service")
        self.assertEqual({found["meter"]: found["price"] for found in prices_of(wide)}, {"Light Hours": "p1", "Fixed Hours": "p2", "Global Hours": "p3", "Heavy Hours": "p4", "Elite Hours": "p5"})
        self.assertEqual(wide["current"]["line"], "p2")
        self.assertEqual(box.prices["p2"], prices.Line(SERVICE, PRODUCT, "Basic", "Fixed Hours", "1 Hour", 0.5, "swedencentral", 1))
        self.assertEqual((box.prices["p3"].region, box.prices["p5"].product), (prices.GLOBAL, OTHER_PRODUCT))
        self.assertEqual(sorted(box.prices), ["p1", "p2", "p3", "p4", "p5"], "a handle is there only for a line that an answer showed: the line in another unit has none")
        self.assertEqual(box.rates, {"m1": 0.8333})

    def test_the_pages_of_a_long_table_follow_one_another_and_no_answer_is_longer_than_the_cap(self):
        estate, box = priced()
        estate.lines = [line("Basic", "Fixed Hours", 0.5)] + [line(f"Size {n}", f"Unit Hours {n}", 1 + n / 100) for n in range(99)]
        seen, offset = [], 0
        while offset is not None:
            raw = box.call("price_alternatives", {"meter": "m1", "within": None, "offset": offset})
            self.assertLessEqual(len(raw), tb.MAX_RESULT_CHARS)
            answer = json.loads(raw)
            seen += [found["price"] for found in prices_of(answer)]
            self.assertEqual(answer["returned"], len(answer["rows"]))
            offset = answer.get("next_offset")
        self.assertEqual((len(seen), len(set(seen))), (100, 100))
        self.assertEqual(ask(box, "price_alternatives", meter="m1", offset=90)["returned"], 10)
        self.assertEqual(ask(box, "price_alternatives", meter="m1", offset=100)["rows"], [])
        usd = [found["usd"] for found in prices_of(ask(box, "price_alternatives", meter="m1"))]
        self.assertEqual(usd, sorted(usd), "the lowest price first")

    def test_it_shows_prices_and_never_a_verdict(self):
        estate, box = priced()
        text = (box.call("price_alternatives", {"meter": "m1"}) + tb.TOOLS["price_alternatives"].description + json.dumps(tb.TOOLS["price_alternatives"].spec().parameters)).lower()
        for word in VERDICTS:
            self.assertNotIn(word, text, word)


class TheMatch(unittest.TestCase):
    def test_the_line_of_the_region_itself_is_the_one_of_the_meter_and_a_price_that_holds_everywhere_is_its_line_only_when_the_region_has_none(self):
        estate, box = priced(words=meter(name="Global Hours"))
        estate.lines.append(line("Basic", "Global Hours", 0.9))
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["match"], answer["current"]["retail"]), ("found", 0.9), "the line of the region wins")
        estate, box = priced(words=meter(name="Global Hours"))
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["match"], answer["current"]["retail"], answer["current"]["rate_ratio"]), ("found", 0.75, 0.5556), "416667 / 0.75, from the line that holds in every region")

    def test_skus_of_one_meter_that_share_a_price_are_one_line_and_lines_that_disagree_are_none_of_them(self):
        estate, box = priced()
        estate.lines += [line("Other", "Fixed Hours", 0.5)]
        self.assertEqual((ask(box, "price_alternatives", meter="m1")["match"], box.rates), ("found", {"m1": 0.8333}))
        estate, box = priced()
        estate.lines += [line("Other", "Fixed Hours", 0.6)]
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["match"], "current" in answer, box.rates), ("several", False, {}), "no rate is carried when the words do not tell the line")
        self.assertEqual(answer["lines"], 5, "the table is still shown")

    def test_a_meter_that_no_line_names_has_the_table_and_no_rate(self):
        estate, box = priced(words=meter(name="Unknown Hours"))
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["match"], "current" in answer, answer["lines"], box.rates), ("none", False, 4, {}))

    def test_a_unit_that_is_not_the_meters_is_counted_and_not_listed(self):
        estate, box = priced(words=meter(name="Data Units", unit="1 GB"), quantity=7.0)
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["unit"], answer["lines"], answer["other_units"], answer["match"]), ("1 GB", 1, 4, "found"))
        self.assertEqual([found["meter"] for found in prices_of(answer)], ["Data Units"])
        estate, box = priced(words=meter(name="Fixed Hours", unit="1 Day"))
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["rows"], answer["lines"], answer["other_units"], answer["match"], box.rates), ([], 0, 5, "none", {}), "the same words in another unit are no line")

    def test_a_rate_is_what_the_bill_paid_for_a_unit_over_the_list_price_and_may_be_above_one(self):
        estate, box = priced(usd=10.0, quantity=12.0)  # 70 dollars for 84 hours: 0.833333 an hour against 0.5
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["current"], {"line": "p2", "retail": 0.5, "paid": 0.833333, "rate_ratio": 1.6667})
        self.assertEqual(box.rates, {"m1": 1.6667})

    def test_a_rate_is_not_worked_out_for_a_price_with_steps_a_price_of_nothing_or_a_quantity_of_nothing(self):
        estate, box = priced()
        estate.lines = [line("Basic", "Fixed Hours", 0.5), line("Basic", "Fixed Hours", 0.4, tier=100)]
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual(answer["current"], {"line": "p1", "retail": 0.5, "paid": 0.416667, "rate_ratio": None, "steps": 2})
        self.assertEqual(prices_of(answer)[0]["steps"], 2)
        estate, box = priced()
        estate.lines = [line("Basic", "Fixed Hours", 0.0)]
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["current"], {"line": "p1", "retail": 0, "paid": 0.416667, "rate_ratio": None})
        estate, box = priced(quantity=0.0)
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["current"], {"line": "p2", "retail": 0.5, "rate_ratio": None})
        self.assertEqual(box.rates, {})

    def test_a_resource_in_the_region_global_is_asked_for_the_prices_that_the_list_writes_for_global(self):
        estate, box = priced(location="global")
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual(answer["region"], "global")
        condition = parse_qs(urlsplit(estate.price_calls[0]["url"]).query)["$filter"][0]
        self.assertIn("armRegionName eq 'Global'", condition)
        self.assertNotIn(" or ", condition, "the region and the global one are the same")


class TheWords(unittest.TestCase):
    def test_a_text_of_the_list_that_is_no_word_of_the_platform_is_other_and_never_the_text(self):
        estate, box = priced()
        estate.lines += [line(SENTENCE, "Odd One", 0.7), line("Basic", HOSTILE, 0.8), line("Basic", "x" * 70, 0.9), line("Basic", "Odd Hours", 1.1, unit=HOSTILE)]
        raw = box.call("price_alternatives", {"meter": "m1"})
        answer = json.loads(raw)
        self.assertIn("other", [found["sku"] for found in prices_of(answer)])
        self.assertEqual([found["meter"] for found in prices_of(answer)].count("other"), 2)
        for marker in (*MARKERS, SENTENCE, "xxxxxxxx"):
            self.assertNotIn(marker, raw)
        self.assertEqual(answer["other_units"], 2, "the line with a hostile unit is in none of the units that the meter has")

    def test_a_text_of_the_list_longer_than_a_word_is_no_line(self):
        estate, box = priced()
        estate.lines += [line("Basic", "Long " * 30, 0.7)]
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["lines"], 4)

    def test_a_hostile_word_of_the_bill_is_never_sent(self):
        for words in (meter(category=HOSTILE), meter(category="Example' or 1 eq 1"), meter(name=SENTENCE), meter(unit=HOSTILE)):
            estate, box = priced(words=words)
            self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "not-offered"}, words)
            self.assertEqual(estate.price_calls, [])

    def test_a_subcategory_that_is_no_word_means_the_whole_service_and_is_never_a_filter(self):
        estate, box = priced(words=meter(subcategory=HOSTILE))
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["within"], answer["match"]), ("service", "none"))
        self.assertNotIn("productName", parse_qs(urlsplit(estate.price_calls[0]["url"]).query)["$filter"][0])


class TheFailures(unittest.TestCase):
    def test_a_read_that_fails_is_unavailable_with_the_code_word_the_rest_of_the_tools_go_on_and_the_failure_is_not_asked_again(self):
        estate, box = priced()
        estate.failure = 500
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable", "code": "Failed"})
        self.assertEqual(len(estate.price_calls), 2, "the client tried twice")
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable", "code": "Failed"})
        self.assertEqual(len(estate.price_calls), 2, "a read that failed is not made again in the run")
        notes = [note for note in box.notes if note.startswith("price_alternatives")]
        self.assertEqual(len(notes), 1)
        self.assertNotIn("serviceName", notes[0])
        self.assertEqual(ask(box, "cost_meters", handle="r1", days=7)["meters"], 1, "the other tools do not notice")

    def test_a_list_that_is_busy_is_unavailable_too(self):
        estate, box = priced()
        estate.failure = 429
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable", "code": "Failed"})

    def test_a_list_that_gives_no_pages_that_the_app_understands_is_unavailable_and_nothing_is_sent_elsewhere(self):
        estate, box = priced()
        estate.body = {"Items": [], "NextPageLink": "https://example.com/api/retail/prices?x=1"}
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable"})
        self.assertEqual([url for url in estate.urls if "example.com" in url], [])

    def test_the_prices_of_only_so_many_services_are_read_in_a_run(self):
        estate, box = priced()
        for n in range(prices.MAX_BOOKS):
            box._books[(f"Other {n}", "swedencentral", None)] = prices.Book((), True)
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable"})
        self.assertEqual(estate.price_calls, [])
        self.assertTrue([note for note in box.notes if "no more" in note])
        box._books.pop(("Other 0", "swedencentral", None))
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["match"], "found")

    def test_a_bill_in_another_currency_has_no_meter_handle_and_so_no_price_is_asked(self):
        estate = PricedEstate()
        estate.currencies = {SUB: "EUR"}
        estate, box = priced(estate)
        self.assertEqual(box.meters, {})
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unknown-handle"})
        self.assertEqual(estate.price_calls, [])


class TheArguments(unittest.TestCase):
    def test_what_the_tool_takes(self):
        estate, box = priced()
        for arguments in ({}, {"meter": "r1"}, {"meter": "m"}, {"meter": "m12345"}, {"meter": 1}, {"meter": "m1", "within": "all"}, {"meter": "m1", "offset": -1}, {"meter": "m1", "offset": True},
                          {"meter": "m1", "limit": 5}, {"meter": "m1 "}, {"meter": "m1\n"}):
            self.assertEqual(box.call("price_alternatives", arguments), '{"error":"bad-arguments"}', arguments)
        self.assertEqual(estate.price_calls, [])
        self.assertEqual(ask(box, "price_alternatives", meter="m9"), {"error": "unknown-handle"})

    def test_the_meter_of_a_whole_type_and_a_resource_with_no_region_word_are_not_offered(self):
        estate, box = priced()
        ask(box, "cost_meters", type=WIDGET, days=7)
        (kind,) = [name for name, held in box.meters.items() if held.scope == WIDGET]
        self.assertEqual(ask(box, "price_alternatives", meter=kind), {"error": "not-offered"})
        for location in ("", "Sweden Central", "other"):
            estate, box = priced(location=location)
            self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "not-offered"}, location)
            self.assertEqual(estate.price_calls, [])

    def test_a_call_counts_as_one_of_the_calls_of_the_run_and_is_logged_by_its_name_alone_in_the_words_of_the_tool(self):
        estate, box = priced()
        ask(box, "price_alternatives", meter="m1")
        self.assertEqual({key: box.log[-1][key] for key in ("name", "arguments", "ok")}, {"name": "price_alternatives", "arguments": {"meter": "m1"}, "ok": True})

    def test_the_layout_of_a_table(self):
        self.assertEqual(prices.layout(("a", "b", "c", "d"), [["x", 1, 2, None], ["y", 1, 3, None]]), ({"b": 1}, ["a", "c"], [["x", 2], ["y", 3]]))
        self.assertEqual(prices.layout(("a", "b"), [["x", 1]]), ({}, ["a", "b"], [["x", 1]]), "one row has nothing in common with the others")
        self.assertEqual(prices.layout(("a", "b"), []), ({}, ["a"], []))
        self.assertEqual(prices.layout(("a", "b", "c"), [["x", None, None], ["y", 1, None]]), ({}, ["a", "b"], [["x"], ["y", 1]]), "a null at the end of a row is left off")


class TheSource(unittest.TestCase):
    def test_the_module_names_no_rule_no_kind_of_resource_and_no_resource_type_and_imports_only_the_standard_library_and_the_client(self):
        source = (support.APP_ROOT / "cases" / "prices.py").read_text(encoding="utf-8")
        self.assertEqual([word for word in FORBIDDEN_WORDS if word in source.lower()], [])
        self.assertEqual(re.findall(r"microsoft\.[a-z]+/[a-z]+", source.lower()), [])
        self.assertEqual(sorted(re.findall(r"^(?:from|import) ([\w.]+)", source, re.M)), [".http", "__future__", "dataclasses", "math", "re", "time", "typing", "urllib.parse"])


if __name__ == "__main__":
    unittest.main()
