"""The documented range of the numbers of a resource type (cases/ranges.py): what is read from the tables of Microsoft's reference page of a type, and the reader that the toolbox is given.

Every type, property and number here is invented, in the markup that the real pages have (the cell of a bounded number is `int <br><br>Constraints:<br>Min value = 2<br>Max value = 50`). No test
touches a network: a fake web answers, and a fake clock says how long it took.
"""
import unittest
from unittest import mock

from cases import http, library, ranges
from cases.http import Client
from cases.ranges import Range, Reader, find, parse

TYPE = "microsoft.example/gateways"
URL = "https://learn.microsoft.com/en-us/azure/templates/microsoft.example/gateways"
BOUNDED = "int <br><br>Constraints:<br>Min value = 2<br>Max value = 50"
LOW_ONLY = "int <br><br>Constraints:<br>Min value = 2"
HIGH_ONLY = "int <br><br>Constraints:<br>Max value = 9 (required)"
HEAD = ("Name", "Description", "Value")


def table(rows, head=HEAD):
    """A table of Learn: a header row of th cells, and a row of three td cells for each property, each tag on a line of its own."""
    top = "<thead>\n<tr>\n" + "".join(f"<th>{word}</th>\n" for word in head) + "</tr>\n</thead>\n"
    body = "".join("<tr>\n" + "".join(f"<td>{cell}</td>\n" for cell in row) + "</tr>\n" for row in rows)
    return f"<table>\n{top}<tbody>\n{body}</tbody>\n</table>\n"


def page(*tables):
    return "<html><body><h1>Microsoft.Example/gateways</h1><pre><code>units: int</code></pre><h2 id=\"property-values\">Property Values</h2>\n" + "".join(tables) + "</body></html>"


def of(*rows):
    """A page with one table of property values."""
    return page(table(rows))


class TheTablesOfAPage(unittest.TestCase):
    def test_a_bounded_number_is_read_from_the_cell_of_its_row_in_the_markup_of_the_real_pages(self):
        found = parse(of(("name", "The resource name", "string (required)"), ("capacityUnits", "The units of the gateway.", BOUNDED), ("tier", "The tier.", "'Lite'<br>'Plus' (required)")))
        self.assertEqual(found, {"capacityUnits": Range(2, 50)})

    def test_one_bound_alone_is_a_range_and_so_is_a_negative_bound_and_a_word_after_the_number_changes_nothing(self):
        found = parse(of(("onlyLow", "x", LOW_ONLY), ("onlyHigh", "x", HIGH_ONLY), ("below", "x", "int <br><br>Constraints:<br>Min value = -1<br>Max value = 10"),
                         ("both", "x", "int <br><br>Constraints:<br>Min value = 1<br>Max value = 1000 (required)")))
        self.assertEqual(found, {"onlyLow": Range(2, None), "onlyHigh": Range(None, 9), "below": Range(-1, 10), "both": Range(1, 1000)})

    def test_the_same_words_with_spaces_line_ends_or_nothing_between_them_are_read_alike(self):
        for value in ("int Constraints:Min value = 2Max value = 50", "int Constraints: Min value = 2 Max value = 50", "int\nConstraints:\nMin value = 2\nMax value = 50",
                      "int <br />Constraints:<ul><li>Min value = 2</li><li>Max value = 50</li></ul>", "int <p>Constraints:</p><p>Min value = 2</p><p>Max value = 50</p>"):
            with self.subTest(value=value):
                self.assertEqual(parse(of(("units", "x", value))), {"units": Range(2, 50)})

    def test_a_number_that_is_not_whole_is_no_bound_and_is_never_read_as_the_whole_part_of_it(self):
        for value, read in (("Min value = 0.5", {}), ("Min value = 1,000", {}), ("Min value = 1e3", {}), ("Max value = 12.5", {}), ("Max value = 1,5", {}), ("Max value = 7E2", {}),
                            ("Min value = 2.5<br>Max value = 3", {"units": Range(None, 3)}), ("Min value = 4<br>Max value = 3.5", {"units": Range(4, None)})):
            with self.subTest(value=value):
                self.assertEqual(parse(of(("units", "x", f"int <br><br>Constraints:<br>{value}"))), read)

    def test_what_is_not_a_bound_of_a_number_is_left_alone_a_length_a_pattern_a_list_of_words_a_flag(self):
        for value in ("string <br><br>Constraints:<br>Min length = 1<br>Max length = 80", "string <br><br>Constraints:<br>Pattern = <code>^[a-z]{2,5}$</code> (required)",
                      "'Lite'<br>'Plus'", "string <br><br>Constraints:<br>Sensitive value. Pass in as a secure parameter.", "bool", "string[]", "<a href=\"#thing\">Thing</a>[]"):
            with self.subTest(value=value):
                self.assertEqual(parse(of(("units", "x", value))), {})

    def test_a_range_that_turns_round_is_no_range(self):
        self.assertEqual(parse(of(("units", "x", "int <br><br>Constraints:<br>Min value = 9<br>Max value = 3"))), {})

    def test_the_name_is_the_first_cell_and_the_bound_is_the_last_whatever_is_between(self):
        found = parse(page(table([("<a href=\"#capacity\">capacityUnits</a>", "Min value = 7 is said here, and no bound", BOUNDED)]),
                           table([("capacity", "Max value = 3 is said in the middle", "The value", LOW_ONLY)], head=("Name", "Description", "Extra", "Value"))))
        self.assertEqual(found, {"capacityUnits": Range(2, 50)}, "the second table has four columns: it is no table of property values")

    def test_the_three_copies_of_the_tables_on_a_page_that_agree_give_the_range(self):
        copy = table([("units", "x", BOUNDED), ("other", "x", "string")])
        self.assertEqual(parse(page(copy, copy, copy)), {"units": Range(2, 50)})

    def test_a_name_that_two_rows_bound_in_different_ways_has_no_range_for_the_table_does_not_say_which_object_it_is_of(self):
        self.assertEqual(parse(page(table([("units", "x", BOUNDED)]), table([("units", "x", "int <br><br>Constraints:<br>Min value = 1<br>Max value = 50")]))), {})
        self.assertEqual(parse(page(table([("units", "x", BOUNDED)]), table([("units", "x", LOW_ONLY)]))), {})
        found = parse(of(("units", "x", BOUNDED), ("other", "x", BOUNDED), ("units", "x", "int <br><br>Constraints:<br>Min value = 1<br>Max value = 50")))
        self.assertEqual(found, {"other": Range(2, 50)}, "another name on the page keeps its range")

    def test_a_name_that_one_row_bounds_and_another_does_not_has_no_range(self):
        self.assertEqual(parse(page(table([("units", "x", BOUNDED)]), table([("units", "x", "int")]))), {})
        self.assertEqual(parse(page(table([("units", "x", "int")]), table([("units", "x", BOUNDED)]))), {})
        self.assertEqual(parse(page(table([("units", "x", BOUNDED)]), table([("units", "x", "string <br><br>Constraints:<br>Max length = 4")]))), {})

    def test_two_spellings_of_a_name_that_differ_in_case_only_are_one_name(self):
        self.assertEqual(parse(page(table([("units", "x", BOUNDED)]), table([("Units", "x", LOW_ONLY)]))), {})
        self.assertEqual(parse(page(table([("units", "x", BOUNDED)]), table([("Units", "x", BOUNDED)]))), {"units": Range(2, 50)}, "the first spelling is the one that is kept")

    def test_a_row_whose_first_cell_is_no_plain_name_names_nothing(self):
        found = parse(of(("{customized property}", "x", BOUNDED), ("two words", "x", BOUNDED), ("", "x", BOUNDED), ("9lives", "x", BOUNDED), ("a" * 65, "x", BOUNDED), ("units", "x", BOUNDED)))
        self.assertEqual(found, {"units": Range(2, 50)})

    def test_a_table_that_is_not_a_table_of_property_values_is_not_read(self):
        other = table([("Some.bicep", "A quickstart", "Min value = 2<br>Max value = 3")], head=("Bicep File", "Description", "Value"))
        self.assertEqual(parse(page(other, table([("units", "x", BOUNDED)]))), {"units": Range(2, 50)})
        self.assertIsNone(parse(page(other)), "a page whose tables are not those of property values is no reference page: it is not read")

    def test_a_page_with_no_table_or_with_none_of_property_values_is_not_read_and_one_with_no_bound_is_read_and_has_none(self):
        for text in ("", "<p>No table here</p>", "plain text", "<html><body>" + "<div>" * 50, "\x00\x01"):
            with self.subTest(text=text[:20]):
                self.assertIsNone(parse(text))
        self.assertEqual(parse(of(("name", "x", "string (required)"))), {})

    def test_a_table_inside_a_table_is_not_read_for_which_name_it_would_give_a_bound_to_is_not_known(self):
        inner = table([("units", "x", BOUNDED)])
        self.assertIsNone(parse(page(f"<table><thead><tr><th>Name</th><th>Description</th><th>Value</th></tr></thead><tbody><tr><td>outer</td><td>x</td><td>{inner}</td></tr></tbody></table>")))

    def test_a_page_that_is_cut_or_ill_formed_gives_what_could_be_read_and_never_raises(self):
        found = parse(of(("units", "x", BOUNDED)) + "<table><thead><tr><th>Name</th><th>Desc")
        self.assertEqual(found, {"units": Range(2, 50)})
        for text in ("<table><tr><td>units</td><td>x</td><td>Min value = 2", "</td></tr></table></table>", "<td>units</td>", "<tr><td>a</td></tr>"):
            parse(text)

    def test_the_markup_of_a_page_that_is_read_whole_gives_the_range_of_each_name_once(self):
        top = table([("identity", "The identity.", "<a href=\"#managed\" data-linktype=\"self-bookmark\">Managed</a>"), ("name", "The resource name", "string (required)"),
                     ("properties", "The properties.", "<a href=\"#props\" data-linktype=\"self-bookmark\">GatewayProps</a>")])
        props = table([("capacityUnits", "The units of the gateway.", BOUNDED), ("zones", "Zones.", "string[]"), ("minUnits", "The least.", LOW_ONLY)])
        found = parse(page(top, props, top, props, top, props))
        self.assertEqual(found, {"capacityUnits": Range(2, 50), "minUnits": Range(2, None)})


class TheLookUp(unittest.TestCase):
    FOUND = {"capacityUnits": Range(2, 50), "count": Range(0, None)}

    def test_a_key_path_of_an_answer_is_found_by_its_last_key(self):
        self.assertEqual(find(self.FOUND, "capacityUnits"), Range(2, 50))
        self.assertEqual(find(self.FOUND, "properties.capacityUnits"), Range(2, 50))
        self.assertEqual(find(self.FOUND, "sku.count"), Range(0, None))

    def test_a_name_that_the_platform_spells_in_another_case_is_found_all_the_same(self):
        self.assertEqual(find(self.FOUND, "capacityunits"), Range(2, 50))
        self.assertEqual(find(self.FOUND, "sku.COUNT"), Range(0, None))

    def test_a_name_that_the_page_does_not_have_is_none(self):
        for path in ("capacity", "units", "", "x.", "capacityUnitsCount"):
            self.assertIsNone(find(self.FOUND, path), path)
        self.assertIsNone(find({}, "capacityUnits"))

    def test_a_range_says_its_bounds_as_the_answers_do_and_leaves_out_a_bound_that_the_page_does_not_give(self):
        self.assertEqual((Range(2, 50).bounds(), Range(2, None).bounds(), Range(None, 9).bounds(), Range(None, None).bounds()),
                         ({"lowest": 2, "highest": 50}, {"lowest": 2}, {"highest": 9}, {}))


class Web:
    """The public pages as a transport. It records each call and answers like the real transport, which reads at most `limit` bytes of a body."""

    def __init__(self, pages=None, fail=None, clock=None, seconds=0.0):
        self.pages, self.fail, self.clock, self.seconds, self.calls = dict(pages or {}), fail, clock, seconds, []

    def __call__(self, method, url, headers, data, timeout, limit=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "timeout": timeout, "limit": limit})
        if self.clock is not None:
            self.clock.now += self.seconds
        if self.fail is not None:
            raise self.fail
        status, body = self.pages.get(url, (404, "not here"))
        raw = body.encode("utf-8")
        return status, {"content-type": "text/html; charset=utf-8"}, raw if limit is None else raw[:limit]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def reader_of(web, clock=None, allowed=None):
    clock = clock or Clock()
    client = Client(allowed or http.docs_calls(), lambda text: text, transport=web, sleep=lambda s: None, monotonic=clock)
    return Reader(client, monotonic=clock), clock


class TheReader(unittest.TestCase):
    PAGES = {URL: (200, of(("capacityUnits", "x", BOUNDED)))}

    def test_the_page_of_a_type_is_read_with_one_get_and_no_token_and_gives_its_ranges(self):
        web = Web(self.PAGES)
        reader, _ = reader_of(web)
        self.assertEqual(reader.limits(TYPE), {"capacityUnits": Range(2, 50)})
        (call,) = web.calls
        self.assertEqual((call["method"], call["url"]), ("GET", URL))
        self.assertEqual(call["url"], library.reference_url(TYPE))
        self.assertNotIn("Authorization", {name.title() for name in call["headers"]})
        self.assertEqual(call["limit"], library.MAX_DOWNLOAD + 1, "the transport reads one byte more than a page may have, to see that it has more")
        self.assertLessEqual(call["timeout"], ranges.ATTEMPT)

    def test_a_type_is_read_once_in_a_run_and_a_second_ask_gets_the_same_answer_with_no_call(self):
        web = Web(self.PAGES)
        reader, _ = reader_of(web)
        first = reader.limits(TYPE)
        self.assertIs(reader.limits(TYPE), first)
        self.assertEqual(len(web.calls), 1)

    def test_a_page_that_could_not_be_read_is_none_and_is_not_asked_for_again(self):
        for label, web in (("a page that is not there", Web({})), ("a host that fails", Web(self.PAGES, fail=OSError("down"))), ("a host that takes too long", Web(self.PAGES, fail=TimeoutError())),
                           ("a server error", Web({URL: (500, "error")})), ("a page that moved", Web({URL: (301, "")})),
                           ("an answer that is no reference page", Web({URL: (200, "<p>Not a reference page</p>")}))):
            with self.subTest(label):
                reader, _ = reader_of(web)
                self.assertIsNone(reader.limits(TYPE))
                self.assertIsNone(reader.limits(TYPE))
                self.assertEqual(len(web.calls), 1, "a failure is kept like an answer: there is no storm of tries")
                self.assertEqual(web.calls[0]["url"], URL)

    def test_a_type_whose_address_the_study_may_not_read_is_none_and_nothing_is_asked(self):
        web = Web(self.PAGES)
        reader, _ = reader_of(web)
        for bad in ("microsoft.example/bad name", "microsoft.example/../x", "microsoft.example/%2e", "", "x" * 400, "microsoft.example//x"):
            self.assertIsNone(reader.limits(bad), bad)
        for not_text in (None, 5, ["microsoft.example/gateways"], b"microsoft.example/gateways", {}):
            self.assertIsNone(reader.limits(not_text), repr(not_text))
        self.assertEqual(web.calls, [])

    def test_a_page_over_the_cap_of_the_library_is_not_read(self):
        web = Web(self.PAGES)
        reader, _ = reader_of(web)
        with mock.patch.object(library, "MAX_DOWNLOAD", len(self.PAGES[URL][1]) - 1):
            self.assertIsNone(reader.limits(TYPE))
        other, _ = reader_of(Web(self.PAGES))
        with mock.patch.object(library, "MAX_DOWNLOAD", len(self.PAGES[URL][1])):
            self.assertEqual(other.limits(TYPE), {"capacityUnits": Range(2, 50)}, "a page that is as long as the cap is read")

    def test_it_asks_only_for_pages_of_the_list_of_the_study_and_a_client_that_has_none_reads_nothing(self):
        web = Web(self.PAGES)
        reader, _ = reader_of(web, allowed=http.allowed_calls())
        self.assertIsNone(reader.limits(TYPE))
        self.assertEqual(web.calls, [], "the list of the Watch holds no page of documentation: the call never leaves the app")

    def test_what_the_reader_is_never_allowed_to_do_is_raise_into_the_toolbox(self):
        for label, error in (("a fault of the transport", RuntimeError("boom")), ("a value error", ValueError("x")), ("a recursion", RecursionError())):
            with self.subTest(label):
                reader, _ = reader_of(Web(self.PAGES, fail=error))
                self.assertIsNone(reader.limits(TYPE))
        reader, _ = reader_of(Web(self.PAGES))
        with mock.patch.object(ranges, "parse", side_effect=RecursionError()):
            self.assertIsNone(reader.limits(TYPE))

    def test_no_more_than_the_pages_of_a_run_are_read_and_the_ones_after_them_are_none_with_no_call(self):
        types = [f"microsoft.example/kind{n}" for n in range(5)]
        pages = {library.reference_url(kind): (200, of(("capacityUnits", "x", BOUNDED))) for kind in types}
        web = Web(pages)
        reader, _ = reader_of(web)
        with mock.patch.object(ranges, "MAX_READS", 3):
            found = [reader.limits(kind) for kind in types]
        self.assertEqual([item is not None for item in found], [True, True, True, False, False])
        self.assertEqual(len(web.calls), 3)

    def test_a_read_is_given_the_time_that_is_left_and_when_it_is_used_up_the_next_types_are_none_with_no_call(self):
        types = [f"microsoft.example/kind{n}" for n in range(4)]
        pages = {library.reference_url(kind): (200, of(("capacityUnits", "x", BOUNDED))) for kind in types}
        clock = Clock()
        web = Web(pages, clock=clock, seconds=25.0)
        reader, _ = reader_of(web, clock)
        with mock.patch.object(ranges, "SECONDS", 30.0), mock.patch.object(ranges, "ATTEMPT", 8.0):
            found = [reader.limits(kind) for kind in types]
        self.assertEqual([item is not None for item in found], [True, True, False, False], "a slow host uses the time of the run in two reads, the second with the time that is left")
        self.assertEqual([call["timeout"] for call in web.calls], [8.0, 5.0])

    def test_a_read_never_takes_more_than_one_attempt_whatever_time_is_left(self):
        web = Web(self.PAGES)
        reader, _ = reader_of(web)
        reader.limits(TYPE)
        self.assertEqual(web.calls[0]["timeout"], min(ranges.ATTEMPT, ranges.SECONDS))

    def test_the_numbers_of_the_caps_are_such_that_a_few_slow_reads_cannot_hold_a_tool_for_long(self):
        self.assertLessEqual(ranges.ATTEMPT, 8.0)
        self.assertLessEqual(ranges.SECONDS, 45.0, "a call of a tool of the toolbox may take 45 seconds in all")
        self.assertGreaterEqual(ranges.MAX_READS, 12)
        self.assertGreaterEqual(ranges.SECONDS, ranges.ATTEMPT)

    def test_threads_that_ask_for_the_same_type_at_once_read_it_once(self):
        import threading
        import time

        class Slow(Web):
            def __call__(self, *args, **kwargs):
                time.sleep(0.05)
                return super().__call__(*args, **kwargs)

        web = Slow(self.PAGES)
        reader, _ = reader_of(web)
        start, answers = threading.Barrier(6), []

        def ask():
            start.wait()
            answers.append(reader.limits(TYPE))

        threads = [threading.Thread(target=ask) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(web.calls), 1, "the read of a page is not started again by a thread that comes while it is made")
        self.assertEqual(len(answers), 6)
        self.assertTrue(all(found == answers[0] and found is not None for found in answers))


if __name__ == "__main__":
    unittest.main()
