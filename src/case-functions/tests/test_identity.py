import json
import unittest

import support  # noqa: F401  (puts the app on the path)
from support import NOW, TOKEN
from cases.identity import Identity, IdentityError

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


class Tokens(unittest.TestCase):
    def identity(self, *answers, env=ENV):
        fetch = Fetch(*answers)
        return Identity(env, fetch=fetch, clock=lambda: NOW.timestamp()), fetch

    def test_a_token_is_asked_for_a_resource_with_the_identitys_client_id_and_the_platforms_header(self):
        identity, fetch = self.identity(good())
        self.assertEqual(identity.token("https://management.azure.com"), TOKEN)
        ((url, headers, timeout),) = fetch.calls
        self.assertTrue(url.startswith("http://127.0.0.1:8081/msi/token?resource=https%3A%2F%2Fmanagement.azure.com&api-version=2019-08-01&client_id="))
        self.assertEqual(headers["X-IDENTITY-HEADER"], "header-value")
        self.assertEqual(timeout, 30)

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
            identity, fetch = self.identity(good(), env=env)
            with self.assertRaises(IdentityError):
                identity.token("r")
            self.assertEqual(fetch.calls, [])

    def test_a_refusal_or_a_bad_answer_is_an_error_without_a_token_in_its_text(self):
        for answer in ((400, b"{}"), (200, b"not json"), (200, b'{"expires_on":"1"}'), (200, b'{"access_token":"","expires_on":"1"}'), (200, b'{"access_token":"t","expires_on":"x"}'),
                       OSError("down")):
            identity, _ = self.identity(answer)
            with self.assertRaises(IdentityError) as raised:
                identity.token("r")
            self.assertNotIn(TOKEN, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
