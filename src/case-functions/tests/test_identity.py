import io
import json
import logging
import time
import unittest
import urllib.error
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
from support import NOW, TOKEN, FakeEstate, Ticker, run_watch
from cases import console, loop
from cases.identity import Identity, IdentityError, default_fetch
from test_loop_end_to_end import LOOP_ENV

ENV = {"IDENTITY_ENDPOINT": "http://127.0.0.1:8081/msi/token", "IDENTITY_HEADER": "header-value", "AZURE_CLIENT_ID": "99999999-8888-7777-6666-555555555555"}


class Fetch:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers), timeout))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def good(token=TOKEN, expires=None):
    return 200, json.dumps({"access_token": token, "expires_on": str(expires or int(NOW.timestamp()) + 3600)}).encode()


class Rig(unittest.TestCase):
    """An identity with a fake endpoint and a sleep that only writes down how long it was asked to wait."""

    def setUp(self):
        self.sleeps = []

    def identity(self, *answers, env=ENV):
        fetch = Fetch(*answers)
        return Identity(env, fetch=fetch, clock=lambda: NOW.timestamp(), sleep=self.sleeps.append), fetch

    def fails(self, *answers, env=ENV):
        """The error that the token request ends in, and the fetch that made the tries."""
        identity, fetch = self.identity(*answers, env=env)
        with self.assertRaises(IdentityError) as raised:
            identity.token("r")
        return raised.exception, fetch


class Tokens(Rig):
    def test_a_token_is_asked_for_a_resource_with_the_identitys_client_id_and_the_platforms_header(self):
        identity, fetch = self.identity(good())
        self.assertEqual(identity.token("https://management.azure.com"), TOKEN)
        ((url, headers, timeout),) = fetch.calls
        self.assertTrue(url.startswith("http://127.0.0.1:8081/msi/token?resource=https%3A%2F%2Fmanagement.azure.com&api-version=2019-08-01&client_id="))
        self.assertEqual(headers["X-IDENTITY-HEADER"], "header-value")
        self.assertEqual(timeout, 15)
        self.assertEqual(self.sleeps, [])

    def test_a_token_is_kept_until_five_minutes_before_it_ends(self):
        identity, fetch = self.identity(good(expires=int(NOW.timestamp()) + 301), good("second-token-value"))
        self.assertEqual(identity.token("r"), TOKEN)
        self.assertEqual(identity.token("r"), TOKEN)
        self.assertEqual(len(fetch.calls), 1)
        short, fetch = self.identity(good(expires=int(NOW.timestamp()) + 200), good("second-token-value"))
        short.token("r")
        self.assertEqual(short.token("r"), "second-token-value")
        self.assertEqual(len(fetch.calls), 2)

    def test_each_resource_has_its_own_token(self):
        identity, fetch = self.identity(good("a-token-value-1"), good("b-token-value-2"))
        self.assertEqual((identity.token("one"), identity.token("two")), ("a-token-value-1", "b-token-value-2"))

    def test_no_endpoint_is_an_error_that_says_so(self):
        for env in ({}, {"IDENTITY_ENDPOINT": ENV["IDENTITY_ENDPOINT"]}, {"IDENTITY_HEADER": "x"}, {**ENV, "IDENTITY_ENDPOINT": "file:///etc/passwd"}):
            error, fetch = self.fails(good(), env=env)
            self.assertEqual(str(error), "the platform's managed identity endpoint is not available")
            self.assertEqual((fetch.calls, self.sleeps), ([], []))

    def test_a_refusal_or_a_bad_answer_is_an_error_without_a_token_in_its_text(self):
        leaking = json.dumps({"access_token": TOKEN, "expires_on": "x"}).encode()
        for answer in ((400, b"{}"), (400, leaking), (500, leaking), (200, b"not json"), (200, b'{"expires_on":"1"}'), (200, b'{"access_token":"","expires_on":"1"}'),
                       (200, b'{"access_token":"t","expires_on":"x"}'), (200, leaking), OSError("down")):
            error, _ = self.fails(answer)
            self.assertNotIn(TOKEN, str(error))


class TriesAgain(Rig):
    def test_a_timeout_and_then_an_answer_gives_the_token_after_a_pause_of_two_seconds(self):
        identity, fetch = self.identity(TimeoutError("slow"), good())
        self.assertEqual(identity.token("r"), TOKEN)
        self.assertEqual((len(fetch.calls), self.sleeps), (2, [2]))

    def test_the_token_of_a_try_that_was_made_again_is_kept(self):
        identity, fetch = self.identity(TimeoutError("slow"), good(), good("second-token-value"))
        self.assertEqual((identity.token("r"), identity.token("r")), (TOKEN, TOKEN))
        self.assertEqual((len(fetch.calls), self.sleeps), (2, [2]))

    def test_every_try_makes_the_same_request_with_a_timeout_of_fifteen_seconds(self):
        identity, fetch = self.identity(TimeoutError("slow"), (503, b""), good())
        identity.token("r")
        self.assertEqual([timeout for _, _, timeout in fetch.calls], [15, 15, 15])
        self.assertEqual(len({(url, tuple(sorted(headers.items()))) for url, headers, _ in fetch.calls}), 1)

    def test_three_timeouts_end_in_an_error_that_says_how_many_tries_were_made(self):
        error, fetch = self.fails(TimeoutError("slow"))
        self.assertEqual(str(error), "the managed identity endpoint gave no answer (TimeoutError) after 3 tries")
        self.assertIsInstance(error.__cause__, TimeoutError)
        self.assertEqual((len(fetch.calls), self.sleeps), (3, [2, 5]))

    def test_the_pauses_are_two_seconds_before_the_second_try_and_five_before_the_third_and_nowhere_else(self):
        events = []

        def fetch(url, headers, timeout):
            events.append("try")
            raise TimeoutError("slow")

        identity = Identity(ENV, fetch=fetch, clock=lambda: NOW.timestamp(), sleep=events.append)
        with self.assertRaises(IdentityError):
            identity.token("r")
        self.assertEqual(events, ["try", 2, "try", 5, "try"])

    def test_a_500_and_then_an_answer_gives_the_token(self):
        identity, fetch = self.identity((500, b'{"error":"busy"}'), good())
        self.assertEqual(identity.token("r"), TOKEN)
        self.assertEqual((len(fetch.calls), self.sleeps), (2, [2]))

    def test_a_429_and_then_an_answer_gives_the_token(self):
        identity, fetch = self.identity((429, b'{"error":"slow down"}'), good())
        self.assertEqual(identity.token("r"), TOKEN)
        self.assertEqual((len(fetch.calls), self.sleeps), (2, [2]))

    def test_a_third_try_can_still_give_the_token(self):
        identity, fetch = self.identity(TimeoutError("slow"), (503, b""), good())
        self.assertEqual(identity.token("r"), TOKEN)
        self.assertEqual((len(fetch.calls), self.sleeps), (3, [2, 5]))

    def test_a_429_and_every_5xx_are_tried_again(self):
        for status in (429, 500, 501, 502, 503, 504, 599):
            with self.subTest(status=status):
                self.sleeps.clear()
                error, fetch = self.fails((status, b"{}"))
                self.assertEqual(str(error), f"the managed identity endpoint answered {status} after 3 tries")
                self.assertEqual((len(fetch.calls), self.sleeps), (3, [2, 5]))

    def test_a_401_and_a_403_are_not_tried_again(self):
        for status in (401, 403):
            with self.subTest(status=status):
                error, fetch = self.fails((status, b"{}"))
                self.assertEqual(str(error), f"the managed identity endpoint answered {status}")
                self.assertEqual((len(fetch.calls), self.sleeps), (1, []))

    def test_no_other_answer_is_tried_again(self):
        for status in (100, 204, 301, 302, 400, 404, 408, 409, 422, 499, 600):
            with self.subTest(status=status):
                error, fetch = self.fails((status, b"{}"))
                self.assertEqual(str(error), f"the managed identity endpoint answered {status}")
                self.assertEqual((len(fetch.calls), self.sleeps), (1, []))

    def test_an_answer_without_a_token_is_not_tried_again(self):
        for body in (b"not json", b"\xff", b"[]", b"{}", b'{"expires_on":"1"}', b'{"access_token":"","expires_on":"1"}', b'{"access_token":5,"expires_on":"1"}',
                     b'{"access_token":"t","expires_on":"x"}'):
            with self.subTest(body=body):
                error, fetch = self.fails((200, body))
                self.assertEqual(str(error), "the managed identity endpoint gave an answer without a token")
                self.assertEqual((len(fetch.calls), self.sleeps), (1, []))

    def test_a_missing_endpoint_or_header_is_not_tried_again(self):
        for env in ({}, {"IDENTITY_ENDPOINT": ENV["IDENTITY_ENDPOINT"]}, {"IDENTITY_HEADER": "x"}):
            with self.subTest(env=sorted(env)):
                error, fetch = self.fails(TimeoutError("slow"), env=env)
                self.assertEqual((str(error), fetch.calls, self.sleeps), ("the platform's managed identity endpoint is not available", [], []))

    def test_every_kind_of_network_failure_is_tried_again(self):
        for failure in (TimeoutError("slow"), OSError("down"), ConnectionRefusedError("refused"), ConnectionResetError("reset"), urllib.error.URLError("unreachable")):
            with self.subTest(failure=type(failure).__name__):
                self.sleeps.clear()
                error, fetch = self.fails(failure)
                self.assertEqual(str(error), f"the managed identity endpoint gave no answer ({type(failure).__name__}) after 3 tries")
                self.assertEqual((len(fetch.calls), self.sleeps), (3, [2, 5]))

    def test_another_kind_of_error_is_not_caught_and_not_tried_again(self):
        for failure in (ValueError("odd"), RuntimeError("odd"), KeyError("odd")):
            with self.subTest(failure=type(failure).__name__):
                identity, fetch = self.identity(failure)
                with self.assertRaises(type(failure)):
                    identity.token("r")
                self.assertEqual((len(fetch.calls), self.sleeps), (1, []))

    def test_the_text_is_that_of_the_last_try_and_counts_the_tries_made(self):
        slow = TimeoutError("slow")
        for answers, text, tries, pauses in (
                ((slow, (503, b""), (500, b"")), "answered 500 after 3 tries", 3, [2, 5]),
                ((slow, (503, b""), TimeoutError("again")), "gave no answer (TimeoutError) after 3 tries", 3, [2, 5]),
                ((slow, (401, b"")), "answered 401 after 2 tries", 2, [2]),
                ((slow, (200, b"{}")), "gave an answer without a token after 2 tries", 2, [2]),
                ((slow, (503, b""), (200, b"{}")), "gave an answer without a token after 3 tries", 3, [2, 5])):
            with self.subTest(text=text):
                self.sleeps.clear()
                error, fetch = self.fails(*answers)
                self.assertEqual(str(error), f"the managed identity endpoint {text}")
                self.assertEqual((len(fetch.calls), self.sleeps), (tries, pauses))

    def test_a_cached_token_is_not_asked_for_again_and_makes_no_pause(self):
        identity, fetch = self.identity(good(), TimeoutError("slow"))
        for _ in range(3):
            self.assertEqual(identity.token("r"), TOKEN)
        self.assertEqual((len(fetch.calls), self.sleeps), (1, []))

    def test_a_token_that_is_about_to_end_is_asked_for_again_with_a_new_round_of_tries(self):
        ending = good(expires=int(NOW.timestamp()) + 200)
        identity, fetch = self.identity(TimeoutError("slow"), ending, TimeoutError("slow"), good("second-token-value"))
        self.assertEqual(identity.token("r"), TOKEN)
        self.assertEqual(identity.token("r"), "second-token-value")
        self.assertEqual((len(fetch.calls), self.sleeps), (4, [2, 2]))
        self.assertEqual(identity.token("r"), "second-token-value")
        self.assertEqual(len(fetch.calls), 4)

    def test_the_real_pause_is_the_default(self):
        self.assertIs(Identity(ENV).sleep, time.sleep)


class OnTheWire(Rig):
    """The tries through the real fetch, with the opening of the connection replaced: no call leaves the test."""

    @staticmethod
    def answer(body):
        response = mock.MagicMock(status=200)
        response.read.return_value = body
        opened = mock.MagicMock()
        opened.__enter__.return_value = response
        return opened

    @staticmethod
    def refusal(status):
        return urllib.error.HTTPError(ENV["IDENTITY_ENDPOINT"], status, "refused", {}, io.BytesIO(b"{}"))

    def test_the_timeout_of_every_try_and_the_header_reach_the_connection(self):
        identity = Identity(ENV, clock=lambda: NOW.timestamp(), sleep=self.sleeps.append)
        with mock.patch("urllib.request.urlopen", side_effect=[TimeoutError("slow"), self.refusal(503), self.answer(good()[1])]) as urlopen:
            self.assertEqual(identity.token("r"), TOKEN)
        self.assertEqual([call.kwargs["timeout"] for call in urlopen.call_args_list], [15, 15, 15])
        request = urlopen.call_args_list[0].args[0]
        self.assertEqual((request.get_method(), request.get_header("X-identity-header")), ("GET", "header-value"))
        self.assertEqual(self.sleeps, [2, 5])

    def test_a_refusal_of_the_endpoint_is_an_answer_with_a_status_and_a_body(self):
        with mock.patch("urllib.request.urlopen", side_effect=self.refusal(429)):
            self.assertEqual(default_fetch(ENV["IDENTITY_ENDPOINT"], {"X-IDENTITY-HEADER": "header-value"}, 15), (429, b"{}"))


class TheCallers(unittest.TestCase):
    """A caller that is given a sleep (the tests give one that does not wait) has it used for the pauses between the tries of a token request too."""

    @staticmethod
    def down(url, headers, timeout):
        return 503, b"{}"

    @staticmethod
    def no_call(*arguments):
        raise AssertionError("no call may be made when there is no token")

    def test_a_run_pauses_with_the_sleep_that_it_was_given(self):
        estate = FakeEstate()
        summary, events, _ = run_watch(estate, fetch=self.down)
        self.assertFalse(summary.ok)
        self.assertEqual((events[-1]["type"], events[-1]["reason"]), ("run.failed", "IdentityError: the managed identity endpoint answered 503 after 3 tries"))
        self.assertEqual((estate.sleeps, estate.calls), ([2, 5], []))

    def test_the_timer_pauses_with_the_sleep_that_it_was_given(self):
        sleeps = []
        with self.assertLogs("meternaut.loop", level=logging.ERROR) as logged:
            self.assertIsNone(loop.tick(dict(LOOP_ENV), transport=self.no_call, sleep=sleeps.append, monotonic=Ticker(), clock=lambda: NOW, fetch=self.down))
        self.assertIn("the managed identity endpoint answered 503 after 3 tries", logged.output[0])
        self.assertEqual(sleeps, [2, 5])

    def test_the_console_gives_its_sleep_to_the_identity_of_the_store_and_to_the_one_of_the_sign_in(self):
        def sleep(seconds):
            raise AssertionError("nothing waits while the services are built")

        with mock.patch.object(console, "Identity", wraps=Identity) as built:
            console.build_services(dict(LOOP_ENV), transport=self.no_call, sleep=sleep, fetch=self.down)
        self.assertEqual([call.kwargs["sleep"] for call in built.call_args_list], [sleep, sleep])
        self.assertEqual([call.kwargs["fetch"] for call in built.call_args_list], [self.down, self.down])


if __name__ == "__main__":
    unittest.main()
