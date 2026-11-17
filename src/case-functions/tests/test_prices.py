"""price_alternatives and cases/prices.py, against a fake estate and an INVENTED price list that answer at the level of the transport: every call also passes the real client and the Watch's list of
calls. Every service, product, SKU, meter, unit and price in it is invented."""
import datetime as dt
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
from test_toolbox import FORBIDDEN_WORDS, HOSTILE, MARKERS, SENTENCE, SUB, Clock, ask, row, toolbox
from test_toolbox_meters import FIXED, WIDGET, BillingEstate, meter, widgets

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
        self.lines, self.page_size, self.failure, self.urls, self.price_calls, self.link, self.body, self.wait = catalogue(), 1000, None, [], [], None, None, None
        self.hook, self.unfiltered = None, False  # a function (estate, url, timeout) that answers instead; and a list that gives every line whatever the filter says

    def __call__(self, method, url, headers, data, timeout):
        parts = urlsplit(url)
        self.urls.append(url)
        if parts.netloc != PRICES_HOST:
            return super().__call__(method, url, headers, data, timeout)
        self.price_calls.append({"method": method, "url": url, "path": parts.path, "query": parse_qs(parts.query), "headers": dict(headers), "timeout": timeout})
        return self.hook(self, url, timeout) if self.hook else self.price_answer(url)

    def price_answer(self, url):
        parts = urlsplit(url)
        if self.failure:
            status, headers, body = self._refused(self.failure)
            return status, {**headers, **({"retry-after": str(self.wait)} if self.wait is not None else {})}, body
        if self.body is not None:
            return 200, {}, json.dumps(self.body).encode("utf-8")
        condition = parse_qs(parts.query)["$filter"][0]
        service = re.search(r"serviceName eq '([^']*)'", condition).group(1)
        regions = re.findall(r"armRegionName eq '([^']*)'", condition)
        product = re.search(r"productName eq '([^']*)'", condition)
        kept = [found for found in self.lines if self.unfiltered or (found["serviceName"] == service and found["armRegionName"] in regions and (product is None or found["productName"] == product.group(1)))]
        skip = int(parse_qs(parts.query).get("$skip", ["0"])[0])
        more = skip + self.page_size < len(kept)
        again = url.split("&$skip=")[0].replace(f"https://{PRICES_HOST}/", f"https://{PRICES_HOST}:443/") + f"&$skip={skip + self.page_size}"  # the list writes the port into the address of the next page
        link = self.link or (again if more else None)
        return 200, {"content-type": "application/json"}, json.dumps({"BillingCurrency": "USD", "Items": kept[skip:skip + self.page_size], "NextPageLink": link, "Count": 1}).encode("utf-8")


def priced(estate=None, words=FIXED, usd=10.0, quantity=24.0, location=None, also=()):
    """An estate with one resource that is billed for one meter (70 dollars and 168 hours over the 7 days that cost_meters is asked for), its toolbox, and the handle of the meter. `also` names
    the words of other meters that it is billed for in the same amount."""
    estate = estate or PricedEstate()
    found = widgets(1)
    estate.rows, estate.cost_rows, estate.definitions = found.rows, found.cost_rows, found.definitions
    if location is not None:
        estate.rows[0]["location"] = location
    for more in (words, *also):
        for n in range(7):  # the lines of the 7 closed days, also those that cost nothing or give money back (billed() leaves out a day of no cost)
            estate.bill.append((SUB, dt.date(2026, 10, 28) + dt.timedelta(days=n), estate.rows[0]["id"].lower(), "Example Service", more, usd, quantity))
    box = toolbox(estate)
    ask(box, "list_resources", type=WIDGET)
    ask(box, "cost_meters", handle="r1", days=7)
    return estate, box


def swallowing(clock):
    """A host that takes every call and never answers: the call ends when its timeout has passed."""
    def hook(estate, url, timeout):
        clock.advance(timeout)
        raise TimeoutError("no answer")
    return hook


def taking(clock, seconds):
    """A host that answers every call after `seconds`, or not at all when the timeout of the call is shorter."""
    def hook(estate, url, timeout):
        clock.advance(min(seconds, timeout))
        if timeout < seconds:
            raise TimeoutError("no answer")
        return estate.price_answer(url)
    return hook


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
        self.assertEqual(query["$filter"], [f"serviceName eq '{SERVICE}' and priceType eq 'Consumption' and (armRegionName eq 'swedencentral' or armRegionName eq 'Global' or armRegionName eq '') and productName eq '{PRODUCT}'"])
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
        self.assertEqual([(urlsplit(url).netloc, parse_qs(urlsplit(url).query).get("$skip")) for url in estate.urls], [(PRICES_HOST, None), (PRICES_HOST, ["2"]), (PRICES_HOST, ["4"])],
                         "the list writes the port 443 into the address of the next page, and the app asks again without it")

    def test_the_next_page_is_on_the_host_and_the_path_of_the_list_with_or_without_the_default_port_and_nowhere_else(self):
        self.assertEqual(prices._next(f"https://{PRICES_HOST}:443{PRICES_PATH}?$filter=a%20b&$skip=1000"), f"https://{PRICES_HOST}{PRICES_PATH}?$filter=a%20b&$skip=1000")
        self.assertEqual(prices._next(f"https://{PRICES_HOST}{PRICES_PATH}?$skip=1000"), f"https://{PRICES_HOST}{PRICES_PATH}?$skip=1000")
        for link in (f"https://{PRICES_HOST}:8443{PRICES_PATH}", f"https://{PRICES_HOST}:abc{PRICES_PATH}", f"https://user@{PRICES_HOST}:443{PRICES_PATH}", f"http://{PRICES_HOST}{PRICES_PATH}",
                     f"https://{PRICES_HOST}.example.com{PRICES_PATH}", f"https://example.com/{PRICES_HOST}{PRICES_PATH}", f"https://{PRICES_HOST}/api/other", f"https://{PRICES_HOST}{PRICES_PATH}/x", "", None, 5):
            with self.assertRaises(prices.HttpError, msg=str(link)):
                prices._next(link)

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
        self.assertEqual(parse_qs(asked.query)["$filter"], [f"serviceName eq '{SERVICE}' and priceType eq 'Consumption' and (armRegionName eq 'swedencentral' or armRegionName eq 'Global' or armRegionName eq '') and productName eq '{PRODUCT}'"])
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
        self.assertEqual(answer["current"], {"line": None, "retail": 0.5, "paid": 0.416667, "rate_ratio": None, "steps": 2})
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
        self.assertEqual(condition, f"serviceName eq '{SERVICE}' and priceType eq 'Consumption' and (armRegionName eq 'Global' or armRegionName eq '') and productName eq '{PRODUCT}'",
                         "the region and the global one are the same: the list writes a price that holds everywhere as Global or with no region")


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

    def test_a_product_and_a_region_that_the_list_gives_and_that_are_no_word_of_the_platform_are_other_and_never_the_text(self):
        estate, box = priced()
        estate.unfiltered = True
        estate.lines += [line("Basic", "Odd Hours", 0.7, product=SENTENCE), line("Basic", "Strange Hours", 0.8, region=HOSTILE)]
        raw = box.call("price_alternatives", {"meter": "m1", "within": "service"})
        found = {item["meter"]: item for item in prices_of(json.loads(raw))}
        self.assertEqual((found["Odd Hours"]["product"], found["Strange Hours"]["region"]), ("other", "other"))
        for marker in (*MARKERS, SENTENCE):
            self.assertNotIn(marker, raw)

    def test_a_bill_that_gave_money_back_or_cost_nothing_has_no_price_that_was_paid_and_so_no_rate(self):
        for usd in (-10.0, 0.0):
            estate, box = priced(usd=usd)
            answer = ask(box, "price_alternatives", meter="m1")
            self.assertEqual(answer["current"], {"line": "p2", "retail": 0.5, "rate_ratio": None}, usd)
            self.assertEqual(box.rates, {}, usd)

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

    def test_a_list_that_is_busy_is_unavailable_too_and_is_never_waited_for_longer_than_a_few_seconds(self):
        for wait, sleeps, calls in ((None, [1.0], 2), (3, [3.0], 2), (30, [], 1)):
            estate, box = priced()
            slept = []
            box.arm.client.sleep = slept.append
            estate.failure, estate.wait = 429, wait
            self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable", "code": "Failed"}, wait)
            self.assertEqual((len(estate.price_calls), [round(s) for s in slept]), (calls, [round(s) for s in sleeps]), f"a wait of {wait}")

    def test_a_list_that_gives_no_pages_that_the_app_understands_is_unavailable_and_nothing_is_sent_elsewhere(self):
        estate, box = priced()
        estate.body = {"Items": [], "NextPageLink": "https://example.com/api/retail/prices?x=1"}
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable"})
        self.assertEqual([url for url in estate.urls if "example.com" in url], [])

    def test_the_prices_that_a_run_keeps_are_bounded_and_a_read_beyond_the_bound_is_unavailable_and_sends_nothing(self):
        estate, box = priced()
        box._books[("Other", "swedencentral", None)] = prices.Book(tuple(prices.Line("Other", "p", "s", "m", "1 Hour", 1.0, "swedencentral", 1) for _ in range(5)), True)
        with mock.patch.object(prices, "MAX_HELD", 5):
            self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable"})
            self.assertEqual(estate.price_calls, [])
            self.assertTrue([note for note in box.notes if "keeps no more" in note])
        with mock.patch.object(prices, "MAX_HELD", 6):
            self.assertEqual(ask(box, "price_alternatives", meter="m1")["match"], "found", "5 are held, and the bound is on what is held: a read that holds 5 more is still made")
        with mock.patch.object(prices, "MAX_HELD", 1):
            self.assertEqual(ask(box, "price_alternatives", meter="m1")["match"], "found", "a list that was read is not read again, whatever the bound")
        self.assertEqual(len(estate.price_calls), 1)

    def test_a_bill_in_another_currency_has_no_meter_handle_and_so_no_price_is_asked(self):
        estate = PricedEstate()
        estate.currencies = {SUB: "EUR"}
        estate, box = priced(estate)
        self.assertEqual(box.meters, {})
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unknown-handle"})
        self.assertEqual(estate.price_calls, [])


class TheRates(unittest.TestCase):
    def longer(self, estate):
        """The resource billed for 23 more days before the 7 of priced(), 230 dollars and 276 hours more: 30 days are 300 dollars and 444 hours."""
        for n in range(23):
            estate.bill.append((SUB, dt.date(2026, 10, 27) - dt.timedelta(days=n), estate.rows[0]["id"].lower(), "Example Service", FIXED, 10.0, 12.0))

    def test_a_rate_is_dropped_when_a_longer_window_replaces_the_meter_that_it_came_from_and_is_worked_out_again_from_the_new_numbers(self):
        estate, box = priced()
        self.longer(estate)
        ask(box, "price_alternatives", meter="m1")
        self.assertEqual((box.meters["m1"].days, box.rates), (7, {"m1": 0.8333}))
        ask(box, "cost_meters", handle="r1", days=30)
        self.assertEqual((box.meters["m1"].days, box.meters["m1"].usd, box.rates), (30, 300.0, {}), "the rate of 7 days is not the rate of the meter of 30 days")
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["current"]["paid"], answer["current"]["rate_ratio"], box.rates), (0.675676, 1.3514, {"m1": 1.3514}), "300 dollars for 444 hours, against 0.5 an hour")
        ask(box, "cost_meters", handle="r1", days=7)
        self.assertEqual((box.meters["m1"].days, box.rates), (30, {"m1": 1.3514}), "a shorter read later replaces neither the meter nor its rate")

    def test_a_rate_is_dropped_when_a_later_ask_for_the_meter_gives_none(self):
        estate, box = priced()
        estate.page_size = 1
        estate.lines.insert(0, estate.lines.pop())  # the other product first, so that a read of the whole service that stops at its first page does not reach the line of the meter
        with mock.patch.object(prices, "MAX_PAGES", 1):
            self.assertEqual(ask(box, "price_alternatives", meter="m1")["match"], "found")
            self.assertEqual(box.rates, {"m1": 0.8333})
            answer = ask(box, "price_alternatives", meter="m1", within="service")
        self.assertEqual((answer["match"], answer["complete"], box.rates), ("none", False, {}), "a rate that the last ask could not work out is not one that code may use")


class TheTime(unittest.TestCase):
    def clocked(self, **kinds):
        estate, box = priced(**kinds)
        clock = Clock()
        box.monotonic, box.arm.client.sleep = clock, clock.advance
        return estate, box, clock

    def test_a_host_that_gives_no_answer_is_tried_once_in_a_run_whatever_is_asked_and_the_run_says_so_once(self):
        estate, box, clock = self.clocked(also=(meter(category="Example Storage", name="Fixed Hours"),))
        estate.hook = swallowing(clock)
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable"})
        self.assertEqual((len(estate.price_calls), clock.now), (1, prices.ATTEMPT), "one try, and no pause before another")
        for arguments in ({"meter": "m1", "within": "service"}, {"meter": "m2"}, {"meter": "m1"}):
            self.assertEqual(ask(box, "price_alternatives", **arguments), {"error": "unavailable"}, arguments)
        self.assertEqual((len(estate.price_calls), clock.now), (1, prices.ATTEMPT), "not a try more for another set of prices, another service or the same one")
        self.assertEqual(len([note for note in box.notes if note.startswith("price_alternatives")]), 1)
        self.assertEqual(ask(box, "cost_meters", handle="r1", days=7)["meters"], 2, "the other tools do not notice")

    def test_what_was_read_stays_answered_when_a_later_read_of_other_prices_gets_no_answer(self):
        estate, box, clock = self.clocked(also=(meter(category="Example Storage", name="Fixed Hours"),))
        estate.lines += [line("Basic", "Fixed Hours", 0.5, service="Example Storage")]
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["match"], "found")
        estate.hook = swallowing(clock)
        self.assertEqual(ask(box, "price_alternatives", meter="m2"), {"error": "unavailable"})
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["match"], "found", "the prices that were read stay")
        self.assertEqual(len(estate.price_calls), 2)

    def test_a_read_that_goes_on_page_after_page_ends_at_the_time_that_it_may_take_and_keeps_what_it_read(self):
        estate, box, clock = self.clocked()
        estate.page_size = 1
        estate.lines = [line("Basic", "Fixed Hours", 0.5)] + [line("Basic", f"Other Hours {n}", 1 + n / 100) for n in range(20)]
        estate.hook = taking(clock, 7.5)
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["complete"], answer["match"], len(estate.price_calls), clock.now), (False, "found", 4, prices.SECONDS), "three pages of 7.5 seconds, and a fourth with the 1.5 that were left")
        self.assertLessEqual(clock.now, prices.SECONDS)

    def test_a_slow_page_and_then_a_page_that_gets_no_answer_end_the_read_inside_its_time_and_the_page_that_was_read_stays(self):
        estate, box, clock = self.clocked()
        estate.page_size = 2

        def hook(found, url, timeout):
            return (swallowing(clock) if "$skip=" in url else taking(clock, 7))(found, url, timeout)
        estate.hook = hook
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["complete"], answer["stopped"], answer["lines"], len(estate.price_calls), clock.now), (False, "unavailable", 2, 2, 7 + prices.ATTEMPT))

    def test_the_time_of_a_read_is_that_of_the_reads_of_the_other_tools_and_a_second_try_is_made_only_when_the_time_that_is_left_holds_it(self):
        estate, box, clock = self.clocked()
        box.read_seconds = 5.0
        estate.hook = swallowing(clock)
        ask(box, "price_alternatives", meter="m1")
        self.assertEqual(clock.now, 5.0, "the call ended with the time that a call may take")
        estate, box, clock = self.clocked()
        box.read_seconds = 10.0
        estate.failure, estate.wait = 429, 1
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable", "code": "Failed"})
        self.assertEqual(len(estate.price_calls), 1, "a try that leaves no time for a second one is the only one")


class ThePartialReads(unittest.TestCase):
    @staticmethod
    def busy_after_the_first_page(found, url, timeout):
        if "$skip=" in url:
            return 429, {"retry-after": "30"}, b'{"error":{"code":"TooManyRequests","message":"x"}}'
        return found.price_answer(url)

    def test_a_page_that_fails_after_a_page_that_was_read_keeps_the_prices_that_were_read_and_says_that_the_list_was_not_read_whole(self):
        estate = PricedEstate()
        estate.page_size, estate.hook = 2, self.busy_after_the_first_page
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None)
        book = prices.read(client, SERVICE, "swedencentral", PRODUCT)
        self.assertEqual((len(book.lines), book.complete, book.error.status, len(estate.price_calls)), (2, False, 429, 2), "the busy list was not waited for, and not asked again")
        with self.assertRaises(prices.HttpError):
            estate.hook = lambda found, url, timeout: (429, {}, b"{}")
            prices.read(client, SERVICE, "swedencentral", PRODUCT)

    def test_the_tool_answers_with_what_was_read_says_why_it_stopped_and_does_not_read_again(self):
        estate, box = priced()
        estate.page_size, estate.hook = 2, self.busy_after_the_first_page
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["complete"], answer["stopped"], answer["code"], answer["match"], answer["lines"]), (False, "unavailable", "TooManyRequests", "found", 2))
        self.assertEqual(answer["current"]["rate_ratio"], 0.8333)
        self.assertEqual(ask(box, "price_alternatives", meter="m1"), answer)
        self.assertEqual(len(estate.price_calls), 2)
        self.assertEqual(len([note for note in box.notes if note.startswith("price_alternatives")]), 1)
        self.assertNotIn("stopped", ask(priced()[1], "price_alternatives", meter="m1"), "a read that was whole says nothing of it")


class TheCaps(unittest.TestCase):
    def test_a_read_that_cut_its_lines_to_the_cap_is_not_complete_even_when_the_list_had_no_next_page(self):
        estate = PricedEstate()
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None)
        for cap, lines, complete in ((3, 3, False), (4, 4, False), (5, 5, True), (6, 5, True)):
            with self.subTest(cap=cap), mock.patch.object(prices, "MAX_LINES", cap):
                book = prices.read(client, SERVICE, "swedencentral", PRODUCT)
                self.assertEqual((len(book.lines), book.complete), (lines, complete))
        self.assertEqual(len(estate.price_calls), 4, "one page each")

    def test_a_page_that_is_too_large_is_refused_before_it_is_read_and_a_real_page_is_far_below_the_cap(self):
        estate, box = priced()
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None)
        with mock.patch.object(prices, "MAX_PAGE_LENGTH", 500):
            with self.assertRaises(prices.HttpError):
                prices.read(client, SERVICE, "swedencentral", PRODUCT)
            self.assertEqual(ask(box, "price_alternatives", meter="m1"), {"error": "unavailable"})
        self.assertEqual(len(prices.read(client, SERVICE, "swedencentral", PRODUCT).lines), 5)
        self.assertTrue(1_000_000 < prices.MAX_PAGE_LENGTH <= 5_000_000, "a page of 1,000 lines of the real list is about 600,000 bytes")


class TheEmptyRegion(unittest.TestCase):
    def test_a_price_that_the_list_gives_with_no_region_holds_in_every_region_and_is_read_as_global(self):
        estate, box = priced(words=meter(name="Empty Hours"))
        estate.lines.append(line("Basic", "Empty Hours", 0.6, region=""))
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual((answer["match"], answer["current"]["retail"], answer["current"]["rate_ratio"]), ("found", 0.6, 0.6944), "0.416667 against 0.6")
        (empty,) = [found for found in prices_of(answer) if found["meter"] == "Empty Hours"]
        self.assertEqual((empty["region"], box.prices[empty["price"]].region), ("global", prices.GLOBAL))

    def test_the_line_of_the_region_is_the_one_of_the_meter_before_a_line_with_no_region(self):
        estate, box = priced()
        estate.lines.append(line("Basic", "Fixed Hours", 0.9, region=""))
        self.assertEqual(ask(box, "price_alternatives", meter="m1")["current"]["retail"], 0.5)

    def test_a_line_whose_region_is_no_text_is_no_line(self):
        estate, box = priced()
        estate.unfiltered = True
        estate.lines += [line("Basic", "Odd Hours", 0.7, region=None), line("Basic", "Odd Units", 0.7, region=5), line("Basic", "Odd Minutes", 0.7, region="x" * (prices.MAX_TEXT + 1))]
        self.assertEqual(sorted(found["meter"] for found in prices_of(ask(box, "price_alternatives", meter="m1"))), sorted(["Light Hours", "Fixed Hours", "Global Hours", "Heavy Hours", "Elite Hours"]))


class TheSteps(unittest.TestCase):
    def test_a_price_with_steps_comes_after_the_prices_without_whatever_its_first_step_costs_and_has_no_handle(self):
        estate, box = priced()
        estate.lines += [line("Basic", "Free Units", 0.0), line("Basic", "Free Units", 0.4, tier=100)]
        answer = ask(box, "price_alternatives", meter="m1")
        found = prices_of(answer)
        self.assertEqual([(item["meter"], item.get("steps"), item["price"]) for item in found],
                         [("Light Hours", None, "p1"), ("Fixed Hours", None, "p2"), ("Global Hours", None, "p3"), ("Heavy Hours", None, "p4"), ("Free Units", 2, None)])
        self.assertEqual(sorted(box.prices), ["p1", "p2", "p3", "p4"], "the register holds no price that has steps, so that the code which prices a switch cannot take one")
        self.assertTrue(all(line.tiers == 1 for line in box.prices.values()))
        wide = ask(box, "price_alternatives", meter="m1", within="service")
        self.assertEqual([item["meter"] for item in prices_of(wide)][-2:], ["Elite Hours", "Free Units"])
        self.assertEqual(sorted(box.prices), ["p1", "p2", "p3", "p4", "p5"])

    def test_the_line_of_the_meter_that_has_steps_has_no_handle_either(self):
        estate, box = priced()
        estate.lines = [line("Basic", "Fixed Hours", 0.5), line("Basic", "Fixed Hours", 0.4, tier=100), line("Basic", "Light Hours", 0.25)]
        answer = ask(box, "price_alternatives", meter="m1")
        self.assertEqual(answer["current"], {"line": None, "retail": 0.5, "paid": 0.416667, "rate_ratio": None, "steps": 2})
        self.assertEqual(sorted(box.prices), ["p1"])
        self.assertEqual(box.rates, {})


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
