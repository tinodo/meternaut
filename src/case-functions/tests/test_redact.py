import unittest

import support  # noqa: F401  (puts the app on the path)
from cases.redact import REDACTED, Redactor


class Redaction(unittest.TestCase):
    def test_a_registered_secret_is_replaced_everywhere(self):
        redact = Redactor()
        redact.add("super-secret-key-12345")
        self.assertEqual(redact("a super-secret-key-12345 b super-secret-key-12345"), f"a {REDACTED} b {REDACTED}")

    def test_a_short_value_is_not_registered_so_that_ordinary_words_survive(self):
        redact = Redactor()
        redact.add("abc")
        redact.add(None)
        redact.add(5)
        self.assertEqual(redact("abc"), "abc")

    def test_header_values_and_tokens_are_removed_without_being_registered(self):
        redact = Redactor()
        for text in ("api-key: abcdef123456", "api-key=abcdef123456", "Authorization: Bearer abcdef123456", "ocp-apim-subscription-key : x1y2z3w4",
                     "X-IDENTITY-HEADER: abcdef", "token eyJhbGciOiJub25lIn0.eyJvaWQiOiJ4In0.signature-value-123 here"):
            cleaned = redact(text)
            self.assertIn(REDACTED, cleaned, text)
            for secret in ("abcdef123456", "x1y2z3w4", "eyJhbGciOiJub25lIn0", "signature-value-123"):
                self.assertNotIn(secret, cleaned, text)

    def test_the_longer_secret_goes_first(self):
        redact = Redactor()
        redact.add("key-12345678")
        redact.add("key-12345678-and-more")
        self.assertEqual(redact("x key-12345678-and-more y"), f"x {REDACTED} y")

    def test_ordinary_text_is_left_alone(self):
        self.assertEqual(Redactor()("The private endpoint is disconnected."), "The private endpoint is disconnected.")


if __name__ == "__main__":
    unittest.main()
