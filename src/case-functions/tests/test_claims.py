import base64
import json
import random
import unittest

from support import APP_ROOT  # noqa: F401

from cases.claims import MAX_BYTES, MAX_DEPTH, MAX_ENCODED, MAX_HEADER, MAX_KEYS, claims_challenge

SCHEME = "Bearer"
REQUEST = {"access_token": {"acrs": {"essential": True, "value": "cp1"}}}
COMPACT = '{"access_token":{"acrs":{"essential":true,"value":"cp1"}}}'
OTHER = "eyJiIjoxfQ"  # {"b":1}, the claims of a second directive
# The header of the example in Microsoft Learn ("Claims challenges, claims requests and client capabilities"), with an example host.
LEARN = (f'{SCHEME} realm="", authorization_uri="https://login.example.test/common/oauth2/authorize", error="insufficient_claims", '
         'claims="eyJhY2Nlc3NfdG9rZW4iOnsiYWNycyI6eyJlc3NlbnRpYWwiOnRydWUsInZhbHVlIjoiY3AxIn19fQ=="')


def encode(text: str | bytes, *, url: bool = False, pad: bool = True) -> str:
    raw = text.encode("utf-8") if isinstance(text, str) else text
    out = (base64.urlsafe_b64encode if url else base64.b64encode)(raw).decode("ascii")
    return out if pad else out.rstrip("=")


def header(claims: str, *, scheme: str = SCHEME, error: str = "insufficient_claims", more: str = "") -> str:
    return f'{scheme} realm="", authorization_uri="https://login.example.test/common/oauth2/authorize", error="{error}", claims="{claims}"{more}'


def of(document) -> str:
    """The header of a challenge whose claims request is this document (a Python value, or text that is sent as it is)."""
    return header(encode(document if isinstance(document, str) else json.dumps(document)))


def nested(depth: int) -> dict:
    """An object inside an object, `depth` levels in all, the object of the request included."""
    value: object = {"leaf": "x"}
    for _ in range(depth - 1):
        value = {"in": value}
    return value  # type: ignore[return-value]


class WhatAzureSends(unittest.TestCase):
    def test_the_example_of_microsoft_learn_gives_its_claims_request_as_compact_json(self):
        self.assertEqual(claims_challenge(LEARN), COMPACT)

    def test_the_result_is_the_request_in_compact_form_whatever_its_spaces_and_escapes(self):
        pretty = json.dumps(REQUEST, indent=4)
        self.assertEqual(claims_challenge(of(pretty)), COMPACT)
        self.assertEqual(claims_challenge(of('{"access_token" : {"acrs":{"essential":true,"value":"c\\u0031"}}}')), '{"access_token":{"acrs":{"essential":true,"value":"c1"}}}')
        self.assertEqual(claims_challenge(of('{"a":"x\\/y"}')), '{"a":"x/y"}')

    def test_the_order_of_the_keys_is_kept(self):
        self.assertEqual(claims_challenge(of('{"b":1,"a":2}')), '{"b":1,"a":2}')

    def test_base64_and_base64url_with_or_without_padding_are_all_read(self):
        text = json.dumps({"access_token": {"x": {"value": "~~~???>>>"}}}, separators=(",", ":"))
        self.assertNotEqual(encode(text), encode(text, url=True), "the test needs a request whose two alphabets differ")
        self.assertRegex(encode(text), r"[+/]")
        self.assertRegex(encode(text, url=True), r"[-_]")
        for url in (False, True):
            for pad in (True, False):
                with self.subTest(url=url, pad=pad):
                    self.assertEqual(claims_challenge(header(encode(text, url=url, pad=pad))), text)
        self.assertNotEqual(len(encode(text)), len(encode(text, pad=False)), "the test needs a request that has padding")

    def test_the_other_directives_may_come_in_any_order_or_be_missing_and_spaces_and_the_case_of_names_do_not_matter(self):
        claims = encode(COMPACT)
        for label, text in {
            "only the two": f'{SCHEME} error="insufficient_claims", claims="{claims}"',
            "claims first": f'{SCHEME} claims="{claims}", error="insufficient_claims", realm="x"',
            "tabs and spaces": f'{SCHEME} \t error = "insufficient_claims" ,\tclaims\t=\t"{claims}"  ',
            "a comma at the end": f'{SCHEME} error="insufficient_claims", claims="{claims}",',
            "no space after commas": f'{SCHEME} error="insufficient_claims",claims="{claims}",realm=""',
            "the scheme in lower case": f'bearer error="insufficient_claims", claims="{claims}"',
            "the scheme in capitals": f'BEARER error="insufficient_claims", claims="{claims}"',
            "names in capitals": f'{SCHEME} ERROR="insufficient_claims", Claims="{claims}"',
            "other directives of Microsoft Entra": f'{SCHEME} authorization_uri="https://login.example.test/x", client_id="11111111-2222-3333-4444-555555555555", '
                                                    f'error="insufficient_claims", error_description="more claims are needed", claims="{claims}"',
        }.items():
            with self.subTest(label):
                self.assertEqual(claims_challenge(text), COMPACT)

    def test_a_list_a_number_true_false_and_null_may_be_in_the_request(self):
        for document in ({"access_token": {"capolids": {"essential": True, "values": ["f2422f78-0000-1111-2222-333344445555"]}}},
                         {"access_token": {"nbf": {"essential": True, "value": 1597959090}}}, {"a": None, "b": False, "c": [1, -2, "x", True, None]}):
            with self.subTest(document=document):
                self.assertEqual(claims_challenge(of(document)), json.dumps(document, separators=(",", ":")))

    def test_the_limits_are_the_agreed_ones_and_not_what_a_test_of_a_limit_takes_from_the_module(self):
        self.assertEqual((MAX_BYTES, MAX_DEPTH, MAX_KEYS, MAX_ENCODED, MAX_HEADER), (2000, 4, 20, 2668, 4000))

    def test_the_limits_themselves_are_accepted(self):
        self.assertEqual(claims_challenge(of(nested(MAX_DEPTH))), json.dumps(nested(MAX_DEPTH), separators=(",", ":")))
        flat = {f"k{n}": n for n in range(MAX_KEYS)}
        self.assertEqual(claims_challenge(of(flat)), json.dumps(flat, separators=(",", ":")))
        exactly = '{"a":"' + "x" * (MAX_BYTES - 8) + '"}'
        self.assertEqual(len(exactly.encode()), MAX_BYTES)
        self.assertEqual(claims_challenge(of(exactly)), exactly)
        self.assertEqual(len(encode(exactly)), MAX_ENCODED, "MAX_ENCODED is the base64 text of MAX_BYTES")


class WhatIsOnlyARefusal(unittest.TestCase):
    """Anything that is not a challenge in the exact form gives None, and an answer of Azure with such a header is an ordinary refusal."""

    def none(self, text, label=""):
        with self.subTest(label or repr(text)[:80]):
            self.assertIsNone(claims_challenge(text))

    def test_what_is_not_a_header_of_this_kind(self):
        for value in (None, b"x", 5, 1.5, ["a"], {"error": "insufficient_claims"}, True):
            self.none(value)
        for value in ("", " ", "Bearer", "Bearer ", "nothing like it"):
            self.none(value)

    def test_another_scheme_or_no_scheme(self):
        claims = encode(COMPACT)
        for scheme in ("Basic", "PoP", "Negotiate", "Digest", "Bearers", "xBearer", "Bearer2", ""):
            self.none(header(claims, scheme=scheme), scheme)
        self.none(" " + header(claims), "a space in front")
        self.none(header(claims).replace(SCHEME + " ", SCHEME), "no space after the scheme")
        self.none(f'{SCHEME} {claims}', "a token and no directive")

    def test_another_error_or_none(self):
        claims = encode(COMPACT)
        for error in ("invalid_token", "insufficient_scope", "Insufficient_Claims", "insufficient_claims ", " insufficient_claims", "insufficient_claim", ""):
            self.none(header(claims, error=error), repr(error))
        self.none(f'{SCHEME} claims="{claims}"', "no error")
        self.none(f'{SCHEME} error=insufficient_claims, claims="{claims}"', "an error that is not in quotes")
        self.none(f'{SCHEME} error="insufficient_claims", claims={claims}', "claims that are not in quotes")

    def test_no_claims_an_empty_claims_or_two_directives_of_one_name(self):
        claims = encode(COMPACT)
        self.none(f'{SCHEME} error="insufficient_claims"', "no claims")
        self.none(header(""), "empty claims")
        self.none(header(claims, more=f', claims="{claims}"'), "two claims directives that are the same")
        self.none(header(claims, more=f', claims="{OTHER}"'), "two claims directives that are not")
        self.none(header(claims, more=f', Claims="{claims}"'), "two claims directives, one in another case")
        self.none(header(claims, more=', error="insufficient_claims"'), "two error directives")
        self.none(header(claims, more=', realm="a"'), "a directive of another name twice")

    def test_a_quote_or_a_backslash_in_a_value_or_text_after_it(self):
        claims = encode(COMPACT)
        for label, text in {
            "a quote in the claims": header(claims[:10] + '"' + claims[10:]),
            "an escaped quote": header(claims[:10] + '\\"' + claims[10:]),
            "a backslash": header(claims[:10] + "\\" + claims[10:]),
            "a quote in another value": header(claims, more=', error_description="a "quoted" word"'),
            "an escaped quote in another value": header(claims, more=', error_description="a \\"quoted\\" word"'),
            "the claims not closed": f'{SCHEME} error="insufficient_claims", claims="{claims}',
            "text after the last directive": header(claims, more=" and more"),
            "a semicolon": header(claims, more="; x=y"),
            "another challenge after it": header(claims, more=', Basic realm="x"'),
            "another challenge before it": f'Basic realm="x", {header(claims)}',
            "two headers in one text": header(claims) + "\r\n" + header(claims),
        }.items():
            self.none(text, label)

    def test_a_control_character_or_a_character_outside_ascii_anywhere_in_the_header(self):
        claims = encode(COMPACT)
        for char in ("\r", "\n", "\t", "\x00", "\x1b", "\x7f", "\u00e9", "\u200b", "\ufeff", "\u2028"):
            self.none(header(claims, more=f', error_description="a{char}b"'), repr(char) + " in a value")
            self.none(header(claims[:8] + char + claims[8:]), repr(char) + " in the claims")
            if char != "\t":  # a tab or a space after the last directive is whitespace that the form of a header allows
                self.none(header(claims) + char, repr(char) + " at the end")
        self.assertEqual(claims_challenge(header(encode(COMPACT)) + " \t"), COMPACT)

    def test_a_header_or_claims_that_are_too_long(self):
        claims = encode(COMPACT)
        self.none(header(claims, more=', error_description="' + "a" * MAX_HEADER + '"'), "a huge header")
        self.none("x" * 1_000_000, "a header of a million characters")
        self.none(header("A" * (MAX_ENCODED + 1)), "base64 text that is too long")
        self.none(header(encode('{"a":"' + "x" * (MAX_BYTES - 7) + '"}')), "2001 bytes")
        self.none(header(encode('{"a":"' + "x" * 100000 + '"}')), "100 kilobytes")

    def test_claims_that_are_not_base64(self):
        for label, claims in {
            "punctuation": "!!!!", "a space": "eyJh bGci", "a line": "eyJh\nbGci", "a star": "eyJh*bGci", "a padding in the middle": "eyJh=bGci", "a padding that is too long": "QQ===",
            "a padding that is too short": "QQ=", "a length that no base64 text has": "abcde", "mixed alphabets": "ab+c-d_e", "a dot": "ab.c", "a percent sign": "ab%3D",
        }.items():
            self.none(header(claims), label)

    def test_claims_that_are_not_utf_8_or_not_json_or_not_one_object(self):
        for label, raw in {
            "not UTF-8": b"\xff\xfe\x00{", "not JSON": b"not json", "cut off": b'{"a":', "text after the object": b'{"a":1} x', "two objects": b'{"a":1}{"b":2}',
            "a list": b"[1]", "a string": b'"x"', "a number": b"5", "null": b"null", "true": b"true", "an empty object": b"{}", "an empty list": b"[]", "nothing": b"",
            "a byte order mark": b'\xef\xbb\xbf{"a":1}', "single quotes": b"{'a':1}", "a comment": b'{"a":1}//x', "a trailing comma": b'{"a":1,}',
        }.items():
            self.none(header(encode(raw)), label)

    def test_a_name_twice_in_an_object(self):
        self.none(of('{"a":1,"a":2}'), "at the top")
        self.none(of('{"a":{"b":1,"b":1}}'), "inside")
        self.none(of('{"a":[{"b":1,"b":2}]}'), "in a list")

    def test_a_number_that_is_not_a_whole_number_and_the_constants_that_json_does_not_have(self):
        for text in ('{"a":1.5}', '{"a":1e3}', '{"a":1E+3}', '{"a":0.0}', '{"a":1e999}', '{"a":-1e999}', '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{"a":[1,2.5]}'):
            self.none(of(text), text)

    def test_text_that_is_not_printable_ascii_in_a_name_or_a_value(self):
        for label, text in {
            "a null character": '{"a":"x\\u0000y"}', "a newline": '{"a":"x\\ny"}', "a tab": '{"a":"x\\ty"}', "a carriage return": '{"a":"x\\ry"}', "a delete character": '{"a":"x\\u007fy"}',
            "an escape": '{"a":"x\\u001by"}', "a letter with an accent": '{"a":"caf\\u00e9"}', "a letter with an accent, as it is": '{"a":"caf\u00e9"}',
            "a line separator": '{"a":"x\\u2028y"}', "a lone surrogate": '{"a":"\\ud800"}', "an emoji": '{"a":"\U0001f600"}',
            "a quote": '{"a":"x\\"y"}', "a backslash": '{"a":"x\\\\y"}',
            "a control character in a name": '{"a\\u0000":1}', "an accent in a name": '{"caf\\u00e9":1}', "a quote in a name": '{"a\\"b":1}', "a backslash in a name": '{"a\\\\b":1}',
            "a bad value in a list": '{"a":["ok","bad\\u0000"]}', "a bad value deep inside": '{"a":{"b":{"c":"bad\\n"}}}',
        }.items():
            self.none(of(text), label)

    def test_printable_ascii_is_enough(self):
        every = "".join(chr(code) for code in range(0x20, 0x7F) if chr(code) not in '"\\')
        self.assertEqual(claims_challenge(of({every: every})), json.dumps({every: every}, separators=(",", ":")))

    def test_objects_and_lists_nested_too_deeply(self):
        self.none(of(nested(MAX_DEPTH + 1)), "objects")
        self.none(of({"a": [[[[1]]]]}), "an object and four lists inside each other: five levels")
        self.none(of({"a": {"b": {"c": [{"d": 1}]}}}), "an object in a list at the fifth level")
        self.assertIsNotNone(claims_challenge(of({"a": [[[1]]]})), "an object and three lists: four levels are the limit")
        self.assertIsNotNone(claims_challenge(of({"a": {"b": {"c": [1]}}})), "a list at the fourth level is the limit")
        for depth in (50, 400, 900, 990):
            self.none(of('{"a":' + "[" * depth + "]" * depth + "}"), f"{depth} lists inside each other")
        self.none(of("[" * 1000 + "]" * 1000), "a list that is a thousand deep, and not an object")
        self.none(of('{"a":' * 300 + "1" + "}" * 300), "objects that are three hundred deep")

    def test_more_keys_than_the_limit_in_all_the_objects_together(self):
        self.none(of({f"k{n}": n for n in range(MAX_KEYS + 1)}), "flat")
        self.none(of({"a": {f"k{n}": n for n in range(MAX_KEYS)}}), "one at the top and twenty inside")
        self.none(of({"a": [{f"k{n}": n for n in range(11)}, {f"j{n}": n for n in range(10)}]}), "in two objects of a list: 1 + 11 + 10 keys")
        self.assertIsNotNone(claims_challenge(of({"a": [{f"k{n}": n for n in range(10)}, {f"j{n}": n for n in range(9)}]})), "1 + 10 + 9 is 20 keys")


class NothingThatIsSentBreaksIt(unittest.TestCase):
    """Hostile and broken text of every kind gives a result or None, and never an error that the caller has to catch."""

    def test_a_header_that_is_changed_a_byte_at_a_time_never_raises_and_a_result_is_always_a_compact_object(self):
        generator = random.Random(2026)
        alphabet = ['"', "\\", "=", ",", " ", "\n", "\x00", "{", "}", "[", "]", ":", "e", "A", "-", "_", "+", "/", "\u00e9", "1", ".", "N"]
        for _ in range(3000):
            text = list(LEARN)
            for _ in range(generator.randint(1, 4)):
                where = generator.randrange(len(text) + 1)
                action = generator.choice(("insert", "replace", "delete"))
                if action == "insert":
                    text.insert(where, generator.choice(alphabet))
                elif text and action == "replace":
                    text[min(where, len(text) - 1)] = generator.choice(alphabet)
                elif text:
                    del text[min(where, len(text) - 1)]
            result = claims_challenge("".join(text))
            if result is not None:
                document = json.loads(result)
                self.assertIsInstance(document, dict)
                self.assertEqual(result, json.dumps(document, separators=(",", ":")))

    def test_claims_that_are_random_bytes_never_raise(self):
        generator = random.Random(7)
        for size in (0, 1, 2, 3, 5, 100, 1500, 2000, 2001):
            for _ in range(20):
                self.assertIsNone(claims_challenge(header(encode(bytes(generator.randrange(256) for _ in range(size))))))

    def test_a_result_is_text_that_a_person_can_be_sent_with_and_holds_no_character_that_needs_care(self):
        result = claims_challenge(LEARN)
        self.assertIsInstance(result, str)
        self.assertTrue(result.isascii() and result.isprintable())
        self.assertNotIn("\\", result)


if __name__ == "__main__":
    unittest.main()
