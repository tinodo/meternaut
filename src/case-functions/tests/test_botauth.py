"""The check of the calls that the Bot Framework Connector makes to the bot (cases/botauth.py): RSASSA-PKCS1-v1_5 with SHA-256, the key document, and the token.

The key that signs the tokens of these tests is made from two fixed primes that the tests carry (tests/botauth_vectors.py): no PEM text is in the repository. The known answers there were
made by OpenSSL, so that the verifier is held against an implementation other than the one that signs here. No test touches the network.
"""
import base64
import hashlib
import hmac
import json
import math
import pathlib
import unittest
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
import botauth_vectors as vectors
from cases import botauth
from cases.botauth import BotAuthenticator, KeyStore, Rejected

NOW = 1_800_000_000.0
APP_ID = "0f6a4c2e-7b1d-4e35-9a58-3c2d1b0e9f47"
SERVICE_URL = "https://smba.trafficmanager.net/emea/"
KEY_ID = "test-key-0001"

P, Q = (int(prime, 16) for prime in vectors.TEST_KEY_PRIMES)
N, E = P * Q, 65537
D = pow(E, -1, math.lcm(P - 1, Q - 1))
K = (N.bit_length() + 7) // 8

# The weak key of an attacker, from two Mersenne primes: it only has to be a valid 2048-bit key that the service does not list.
N_ATTACKER = (2 ** 2203 - 1) * (2 ** 127 - 1)
D_ATTACKER = pow(E, -1, math.lcm(2 ** 2203 - 2, 2 ** 127 - 2))


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def der(tag: int, content: bytes) -> bytes:
    assert len(content) < 128
    return bytes([tag, len(content)]) + content


# The DigestInfo of RFC 8017, section 9.2, written from its parts and not taken from the module under test: SEQUENCE { SEQUENCE { OID, NULL }, OCTET STRING }.
OIDS = {"sha1": bytes.fromhex("06052b0e03021a"), "sha256": bytes.fromhex("0609608648016503040201"), "sha512": bytes.fromhex("0609608648016503040203")}


def digest_info(message: bytes, hash_name: str = "sha256", null_parameters: bool = True, hash_value: bytes | None = None) -> bytes:
    value = hashlib.new(hash_name, message).digest() if hash_value is None else hash_value
    return der(0x30, der(0x30, OIDS[hash_name] + (b"\x05\x00" if null_parameters else b"")) + der(0x04, value))


def padded(info: bytes, k: int = K, block_type: int = 1, separator: bytes = b"\x00") -> bytes:
    return b"\x00" + bytes([block_type]) + b"\xff" * (k - len(info) - 3) + separator + info


DP, DQ, QINV = D % (P - 1), D % (Q - 1), pow(Q, -1, P)


def raw_sign(encoded: bytes, d: int = D, n: int = N) -> bytes:
    """The private operation of RSA on a message that the caller encoded: what a signer who holds the key can be made to sign, whatever the encoding."""
    m = int.from_bytes(encoded, "big")
    if n == N and d == D:  # the Chinese remainder form, four times faster than one big exponentiation
        sp, sq = pow(m, DP, P), pow(m, DQ, Q)
        result = sq + ((QINV * (sp - sq)) % P) * Q
    else:
        result = pow(m, d, n)
    return result.to_bytes((n.bit_length() + 7) // 8, "big")


def sign(message: bytes) -> bytes:
    return raw_sign(padded(digest_info(message)))


def icbrt(x: int) -> int:
    """The smallest integer whose cube is at least x."""
    low, high = 0, 1 << (x.bit_length() // 3 + 2)
    while low < high:
        middle = (low + high) // 2
        if middle ** 3 < x:
            low = middle + 1
        else:
            high = middle
    return low


def jwk(kid: str = KEY_ID, n: int = N, e: int = E, endorsements=("msteams", "skype"), **extra) -> dict:
    return {"kty": "RSA", "use": "sig", "kid": kid, "n": b64(n.to_bytes((n.bit_length() + 7) // 8, "big")), "e": b64(e.to_bytes((e.bit_length() + 7) // 8, "big")),
            "endorsements": list(endorsements), **extra}


class Clock:
    def __init__(self, now: float = NOW) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class Documents:
    """The two documents of login.botframework.com, as a fetch that remembers what was asked."""

    def __init__(self, keys=None, metadata=None, fail=False) -> None:
        self.keys = {"keys": [jwk()]} if keys is None else keys
        self.metadata = {"issuer": botauth.ISSUER, "authorization_endpoint": "https://invalid.botframework.com", "jwks_uri": "https://login.botframework.com/v1/.well-known/keys",
                         "id_token_signing_alg_values_supported": ["RS256"], "token_endpoint_auth_methods_supported": ["private_key_jwt"]} if metadata is None else metadata
        self.fail, self.calls = fail, []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if self.fail:
            raise OSError("no network")
        if url == botauth.OPENID_URL:
            return json.dumps(self.metadata).encode()
        if url == "https://login.botframework.com/v1/.well-known/keys":
            return json.dumps(self.keys).encode()
        raise OSError(f"nothing at {url}")


def token(header=None, payload=None, signer=sign, signature: bytes | None = None, raw_header: bytes | None = None, raw_payload: bytes | None = None) -> str:
    """A token for the bot: the standard header and payload, changed by the arguments, and signed with the test key unless the test says otherwise."""
    head = {"alg": "RS256", "typ": "JWT", "kid": KEY_ID, "x5t": KEY_ID}
    if header is not None:
        head = {**head, **header} if not isinstance(header, dict) or "__replace__" not in header else {k: v for k, v in header.items() if k != "__replace__"}
    body = {"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600, "nbf": NOW - 60, "serviceurl": SERVICE_URL}
    if payload is not None:
        body = {**body, **payload}
    first = b64(raw_header if raw_header is not None else json.dumps(head).encode())
    second = b64(raw_payload if raw_payload is not None else json.dumps(body).encode())
    signed = f"{first}.{second}".encode("ascii")
    return f"{first}.{second}.{b64(signature if signature is not None else signer(signed))}"


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.documents = Documents()
        self.store = KeyStore(self.documents, self.clock)
        self.auth = BotAuthenticator(APP_ID, self.store, self.clock)

    def let_in(self, value: str, service_url: str = SERVICE_URL, channel: str = "msteams") -> None:
        self.auth.authenticate(f"Bearer {value}", service_url, channel)

    def refuse(self, value, status: int, reason: str, service_url: str = SERVICE_URL, channel: str = "msteams", header: str | None = None) -> None:
        with self.assertRaises(Rejected) as caught:
            self.auth.authenticate(header if header is not None else f"Bearer {value}", service_url, channel)
        self.assertEqual((caught.exception.status, caught.exception.reason), (status, reason))
        self.assertEqual(str(caught.exception), reason, "the error says a fixed word and never part of a token")


class TheKnownAnswers(unittest.TestCase):
    """Signatures that OpenSSL made: the verifier must agree with an implementation other than its own."""

    def test_every_signature_that_openssl_made_verifies(self):
        for label, modulus, exponent, message, signature in vectors.VECTORS:
            with self.subTest(label):
                self.assertTrue(botauth.rsassa_pkcs1_v15_verify(int(modulus, 16), exponent, message.encode(), bytes.fromhex(signature)))

    def test_one_changed_bit_of_the_message_the_signature_or_the_key_does_not(self):
        for label, modulus, exponent, message, signature in vectors.VECTORS:
            n, raw = int(modulus, 16), bytearray.fromhex(signature)
            with self.subTest(label):
                self.assertFalse(botauth.rsassa_pkcs1_v15_verify(n, exponent, message.encode() + b"!", bytes(raw)))
                self.assertFalse(botauth.rsassa_pkcs1_v15_verify(n, exponent, message[:-1].encode(), bytes(raw)))
                for position in (0, 1, len(raw) // 2, len(raw) - 1):
                    flipped = bytearray(raw)
                    flipped[position] ^= 0x01
                    self.assertFalse(botauth.rsassa_pkcs1_v15_verify(n, exponent, message.encode(), bytes(flipped)), position)
                self.assertFalse(botauth.rsassa_pkcs1_v15_verify(int(vectors.OTHER_KEY_MODULUS, 16), exponent, message.encode(), bytes(raw)), "another key")
                self.assertFalse(botauth.rsassa_pkcs1_v15_verify(n, exponent + 2, message.encode(), bytes(raw)), "another exponent")

    def test_a_signature_whose_first_byte_is_zero_is_as_long_as_the_modulus_and_verifies(self):
        (vector,) = [v for v in vectors.VECTORS if "first byte is zero" in v[0]]
        signature = bytes.fromhex(vector[4])
        self.assertEqual(signature[0], 0)
        n = int(vector[1], 16)
        self.assertTrue(botauth.rsassa_pkcs1_v15_verify(n, 65537, vector[3].encode(), signature))
        self.assertFalse(botauth.rsassa_pkcs1_v15_verify(n, 65537, vector[3].encode(), signature[1:]), "the zero byte may not be left out: the length is that of the modulus")

    def test_the_encoding_of_the_module_is_the_one_that_these_tests_write_from_the_rfc(self):
        for message in (b"", b"a", b"known answer one", bytes(range(256)) * 4):
            self.assertEqual(botauth.encode_message(message, K), padded(digest_info(message)))
            self.assertEqual(len(botauth.encode_message(message, K)), K)
        self.assertEqual(botauth.SHA256_DIGEST_INFO + hashlib.sha256(b"x").digest(), digest_info(b"x"))
        with self.assertRaises(ValueError):
            botauth.encode_message(b"x", 19 + 32 + 10)  # the padding would be seven bytes
        botauth.encode_message(b"x", 19 + 32 + 11)  # eight is the least

    def test_the_test_key_signs_what_the_verifier_accepts(self):
        for message in (b"", b"one", b"two" * 100):
            self.assertTrue(botauth.rsassa_pkcs1_v15_verify(N, E, message, sign(message)))
        self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, b"two", sign(b"one")))

    def test_the_comparison_is_the_constant_time_one_over_the_whole_message(self):
        with mock.patch.object(botauth.hmac, "compare_digest", wraps=hmac.compare_digest) as spy:
            self.assertTrue(botauth.rsassa_pkcs1_v15_verify(N, E, b"one", sign(b"one")))
        (call,) = spy.call_args_list
        self.assertEqual([len(x) for x in call.args], [K, K])
        self.assertEqual(call.args[1], padded(digest_info(b"one")))


class TheForgeries(unittest.TestCase):
    """The classic ways to get a loose verifier to accept what the key holder never signed. A signer who holds the key is made to sign each malformed message, which is the worst case for
    the padding check: the signature is real, and only the whole-message comparison can refuse it."""

    MESSAGE = b"header.payload"

    def refused(self, encoded: bytes, message: bytes | None = None) -> None:
        self.assertEqual(len(encoded), K)
        self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, self.MESSAGE if message is None else message, raw_sign(encoded)))

    def test_the_well_formed_message_is_the_control(self):
        self.assertTrue(botauth.rsassa_pkcs1_v15_verify(N, E, self.MESSAGE, raw_sign(padded(digest_info(self.MESSAGE)))))

    def test_a_padding_that_is_too_short(self):
        info = digest_info(self.MESSAGE)
        for short in (0, 1, 7):
            self.refused(b"\x00\x01" + b"\xff" * short + b"\x00" + info + b"\x00" * (K - 3 - short - len(info)))

    def test_garbage_after_the_hash(self):
        info = digest_info(self.MESSAGE)
        for garbage in (1, 8, 20, 100, K - len(info) - 11):
            self.refused(b"\x00\x01" + b"\xff" * (K - 3 - len(info) - garbage) + b"\x00" + info + b"\xaa" * garbage)
            self.refused(b"\x00\x01" + b"\xff" * (K - 3 - len(info) - garbage) + b"\x00" + info + b"\x00" * garbage)

    def test_a_digest_info_that_is_not_exactly_the_one_of_sha_256(self):
        no_null = digest_info(self.MESSAGE, null_parameters=False)
        self.refused(padded(no_null))
        self.refused(padded(digest_info(self.MESSAGE, "sha1")))
        self.refused(padded(digest_info(self.MESSAGE, "sha512")))
        self.refused(padded(digest_info(self.MESSAGE, hash_value=hashlib.sha256(self.MESSAGE).digest()[:20])))
        self.refused(padded(digest_info(self.MESSAGE, hash_value=b"\x00" * 32)))
        self.refused(padded(digest_info(b"another message")))

    def test_the_hash_of_another_algorithm_in_its_own_digest_info_is_not_a_signature_with_sha_256(self):
        for name in ("sha1", "sha512"):
            self.refused(padded(digest_info(self.MESSAGE, name)))

    def test_a_block_that_is_not_type_one_or_that_does_not_start_with_zero_or_has_another_padding(self):
        info = digest_info(self.MESSAGE)
        self.refused(padded(info, block_type=2))
        self.refused(padded(info, block_type=0))
        self.refused(b"\x01\x01" + b"\xff" * (K - len(info) - 3) + b"\x00" + info)
        self.refused(b"\x00\x01" + b"\xff" * 10 + b"\x00" + b"\xff" * (K - len(info) - 14) + b"\x00" + info)  # the first zero ends the padding
        self.refused(b"\x00\x01" + b"\xfe" + b"\xff" * (K - len(info) - 4) + b"\x00" + info)
        self.refused(b"\x00\x01" + b"\xff" * (K - len(info) - 3) + b"\x01" + info)
        self.refused(b"\x00\x01" + b"\xff" * (K - len(info) - 3) + info + b"\x00")

    def test_a_signature_of_another_message_and_one_that_has_the_wrong_length(self):
        signature = sign(self.MESSAGE)
        self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, b"another message", signature))
        for wrong in (b"", signature[1:], b"\x00" + signature, signature + b"\x00", signature[:-1], signature * 2):
            self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, self.MESSAGE, wrong))

    def test_a_signature_that_is_not_below_the_modulus(self):
        for value in (N, N + 1, N + 5, (1 << (8 * K)) - 1):
            self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, self.MESSAGE, value.to_bytes(K, "big")), value)
        self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, self.MESSAGE, (0).to_bytes(K, "big")))
        self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, self.MESSAGE, (1).to_bytes(K, "big")))

    def test_the_signature_plus_the_modulus_is_the_same_number_for_rsa_and_is_not_a_signature(self):
        for n in range(200):
            message = f"search {n}".encode()
            signature = int.from_bytes(sign(message), "big")
            if signature + N < 1 << (8 * K):
                self.assertTrue(botauth.rsassa_pkcs1_v15_verify(N, E, message, signature.to_bytes(K, "big")))
                self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, message, (signature + N).to_bytes(K, "big")), "a second spelling of the same signature")
                return
        self.fail("no message gave a signature below 2^2048 minus the modulus")

    def test_the_cube_root_forgery_of_a_loose_verifier_that_needs_no_key(self):
        """Bleichenbacher 2006: with the exponent 3 a signature is made of nothing but a cube root. The padding is correct up to the hash and garbage follows it, so a verifier
        that reads the padding and does not look at what comes after the hash accepts it. This one refuses the key, and it refuses the signature on its own as well."""
        info = digest_info(self.MESSAGE)
        prefix = b"\x00\x01\xff\x00" + info
        target = int.from_bytes(prefix + b"\x00" * (K - len(prefix)), "big")
        forged = icbrt(target)
        self.assertEqual((forged ** 3) >> (8 * (K - len(prefix))), int.from_bytes(prefix, "big"), "the forgery is right: its cube starts with the padded hash")
        signature = forged.to_bytes(K, "big")
        self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, 3, self.MESSAGE, signature), "an exponent of 3 is not accepted")
        self.assertFalse(botauth.acceptable_key(N, 3))
        self.assertFalse(botauth._verify(N, 3, self.MESSAGE, signature), "and with the check of the key taken away the whole message still differs from the expected one")
        self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, self.MESSAGE, signature))

    def test_a_key_that_is_too_small_or_has_a_small_exponent_is_not_used_at_all(self):
        self.assertTrue(botauth.acceptable_key(N, E))
        self.assertFalse(botauth.acceptable_key(P, E), "1024 bits")
        self.assertFalse(botauth.acceptable_key(N >> 1 | 1, E), "2047 bits")
        for exponent in (0, 1, 3, 17, 257, 65535, 65536, 65538):
            self.assertFalse(botauth.acceptable_key(N, exponent), exponent)
        self.assertFalse(botauth.acceptable_key(N + 1, E), "an even modulus")
        self.assertFalse(botauth.acceptable_key(N, N), "an exponent that is not below the modulus")
        self.assertFalse(botauth.acceptable_key(N, N + 2))
        self.assertFalse(botauth.acceptable_key(1 << 9000 | 1, E), "more than 8192 bits")
        for bad in (True, False, None, "3", 65537.0, b"x"):
            self.assertFalse(botauth.acceptable_key(N, bad), bad)
            self.assertFalse(botauth.acceptable_key(bad, E), bad)
        self.assertTrue(botauth.acceptable_key(N, 65539))
        self.assertTrue(botauth.acceptable_key(int(vectors.VECTORS[-1][1], 16), 65537), "3072 bits")
        self.assertFalse(botauth.rsassa_pkcs1_v15_verify(P, E, self.MESSAGE, sign(self.MESSAGE)[:128]))

    def test_nothing_but_bytes_is_a_message_or_a_signature(self):
        for bad in (None, "text", 5, [b"x"]):
            self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, bad, sign(b"x")))
            self.assertFalse(botauth.rsassa_pkcs1_v15_verify(N, E, b"x", bad))


class TheEncodingOfBase64Url(unittest.TestCase):
    def test_what_is_read_is_one_spelling_of_the_bytes(self):
        self.assertEqual(botauth.b64url_decode("AQAB"), b"\x01\x00\x01")
        self.assertEqual(botauth.b64url_decode("_-8"), b"\xff\xef")
        for text in ("AQAB", "AQ", "AAA", "-_-_", b64(bytes(range(256)))):
            self.assertEqual(b64(botauth.b64url_decode(text)), text)

    def test_padding_other_alphabets_whitespace_and_extra_bits_are_refused(self):
        for text in ("", "AQ==", "AQAB=", "A", "AQA B", "AQAB\n", " AQAB", "AQ+B", "AQ/B", "AQAB.", "\u00c1QAB", "AR", "AQB", "A_", None, 5, b"AQAB"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    botauth.b64url_decode(text)


class TheKeyDocument(unittest.TestCase):
    def test_the_real_keys_of_the_document_are_read(self):
        keys = botauth.parse_keys(vectors.REAL_KEYS)
        self.assertEqual(len(keys), 2)
        first, second = (keys[k["kid"]] for k in vectors.REAL_KEYS["keys"])
        self.assertEqual((first.n.bit_length(), first.e), (2048, 65537))
        self.assertIn("msteams", first.endorsements)
        self.assertNotIn("msteams", second.endorsements)
        self.assertEqual(second.endorsements, frozenset({"directlinespeech", "telephony"}))

    def test_a_key_that_is_not_an_rsa_signing_key_with_a_good_kid_and_numbers_is_left_out(self):
        good = jwk("good")
        for changed in ({"kty": "EC"}, {"use": "enc"}, {"alg": "RS512"}, {"kid": ""}, {"kid": "has space"}, {"kid": 5}, {"kid": None}, {"n": "!!"}, {"n": ""}, {"e": "AQ"},
                        {"e": b64((3).to_bytes(1, "big"))}, {"n": b64(P.to_bytes(128, "big"))}, {"endorsements": "msteams"}, {"n": 5}):
            with self.subTest(changed=changed):
                keys = botauth.parse_keys({"keys": [good, {**good, **changed, "kid": changed.get("kid", "other")}]})
                self.assertEqual(sorted(keys) if "kid" not in changed else sorted(k for k in keys if k == "good"), ["good"], changed)
        self.assertEqual(botauth.parse_keys({"keys": [jwk("a", alg="RS256")]}).keys(), {"a"})

    def test_two_keys_with_one_kid_are_both_left_out(self):
        document = {"keys": [jwk("same"), jwk("same", n=N_ATTACKER), jwk("other")]}
        self.assertEqual(sorted(botauth.parse_keys(document)), ["other"])

    def test_a_document_that_is_not_a_key_set_has_no_keys(self):
        for document in (None, [], "keys", {}, {"keys": None}, {"keys": {}}, {"keys": [None, 5, "x", []]}):
            self.assertEqual(botauth.parse_keys(document), {})

    def test_the_endorsements_are_the_channels_as_lower_case_words(self):
        key = botauth.parse_keys({"keys": [jwk("a", endorsements=["msteams", "Skype", "web chat", 5, None, "x" * 80, "ok-one"])]})["a"]
        self.assertEqual(key.endorsements, frozenset({"msteams", "ok-one"}))


class TheKeyStore(Fixture):
    def test_the_first_token_reads_the_metadata_and_then_the_keys_and_the_next_ones_read_nothing(self):
        self.assertIsNotNone(self.store.key(KEY_ID))
        self.assertEqual(self.documents.calls, [botauth.OPENID_URL, "https://login.botframework.com/v1/.well-known/keys"])
        for _ in range(10):
            self.store.key(KEY_ID)
        self.assertEqual(len(self.documents.calls), 2)

    def test_an_unknown_kid_makes_one_new_read_after_five_minutes_and_not_more_often(self):
        self.store.key(KEY_ID)
        for _ in range(50):
            self.assertIsNone(self.store.key("not-a-key"))
        self.assertEqual(len(self.documents.calls), 2, "a flood of random kids does not make the app read the document again")
        self.clock.now += botauth.UNKNOWN_KID_GAP_SECONDS - 1
        self.assertIsNone(self.store.key("not-a-key"))
        self.assertEqual(len(self.documents.calls), 2)
        self.documents.keys = {"keys": [jwk(), jwk("fresh", n=N_ATTACKER)]}
        self.clock.now += 2
        self.assertIsNotNone(self.store.key("fresh"), "a key that was added is found by the next token after the gap")
        self.assertEqual(len(self.documents.calls), 4)
        for _ in range(5):
            self.assertIsNone(self.store.key("not-a-key"))
        self.assertEqual(len(self.documents.calls), 4)

    def test_the_document_is_read_again_when_the_copy_is_old(self):
        self.store.key(KEY_ID)
        self.clock.now += botauth.REFRESH_SECONDS - 1
        self.store.key(KEY_ID)
        self.assertEqual(len(self.documents.calls), 2)
        self.clock.now += 2
        self.store.key(KEY_ID)
        self.assertEqual(len(self.documents.calls), 4)
        self.assertLess(botauth.REFRESH_SECONDS, 24 * 3600, "Microsoft asks for a read at least every 24 hours")

    def test_a_read_that_fails_is_not_tried_on_every_request_and_leaves_the_copy_alone(self):
        self.store.key(KEY_ID)
        self.documents.fail = True
        self.clock.now += botauth.REFRESH_SECONDS + 1
        self.assertIsNotNone(self.store.key(KEY_ID), "the copy that is there is used while it is not too old")
        self.assertEqual(len(self.documents.calls), 3, "one try, and it failed at the metadata")
        for _ in range(20):
            self.store.key(KEY_ID)
        self.assertEqual(len(self.documents.calls), 3)
        self.clock.now += botauth.UNKNOWN_KID_GAP_SECONDS
        self.store.key(KEY_ID)
        self.assertEqual(len(self.documents.calls), 4)

    def test_a_copy_that_could_not_be_renewed_for_three_days_is_not_used_any_more(self):
        self.store.key(KEY_ID)
        self.documents.fail = True
        self.clock.now += botauth.MAX_STALE_SECONDS - 1
        self.assertIsNotNone(self.store.key(KEY_ID))
        self.clock.now += 2
        self.assertIsNone(self.store.key(KEY_ID), "fail closed")

    def test_with_nothing_read_yet_and_no_network_there_is_no_key(self):
        self.documents.fail = True
        self.assertIsNone(self.store.key(KEY_ID))

    def test_a_metadata_document_that_does_not_say_what_is_expected_is_not_used(self):
        good = dict(self.documents.metadata)
        for name, changed in (("another issuer", {"issuer": "https://evil.example"}), ("no RS256", {"id_token_signing_alg_values_supported": ["RS384"]}),
                              ("no algorithms", {"id_token_signing_alg_values_supported": None}), ("keys on another host", {"jwks_uri": "https://evil.example/v1/.well-known/keys"}),
                              ("keys on a look-alike host", {"jwks_uri": "https://login.botframework.com.evil.example/v1/.well-known/keys"}),
                              ("keys over http", {"jwks_uri": "http://login.botframework.com/v1/.well-known/keys"}),
                              ("keys with a query", {"jwks_uri": "https://login.botframework.com/v1/.well-known/keys?x=1"}), ("no address", {"jwks_uri": None})):
            with self.subTest(name):
                documents = Documents(metadata={**good, **changed})
                self.assertIsNone(KeyStore(documents, self.clock).key(KEY_ID))
                self.assertEqual(documents.calls, [botauth.OPENID_URL], "the second document is not asked for")

    def test_a_key_document_with_no_usable_key_replaces_nothing(self):
        self.store.key(KEY_ID)
        self.documents.keys = {"keys": []}
        self.clock.now += botauth.REFRESH_SECONDS + 1
        self.assertIsNotNone(self.store.key(KEY_ID))

    def test_the_two_reads_are_the_calls_that_the_client_may_make(self):
        calls = botauth.botauth_calls()
        self.assertEqual([m for m, _ in calls], ["GET", "GET"])
        for url in (botauth.OPENID_URL, "https://login.botframework.com/v1/.well-known/keys"):
            self.assertTrue(any(p.fullmatch(url) for _, p in calls), url)
        for url in ("http://login.botframework.com/v1/.well-known/keys", "https://login.botframework.com/v1/.well-known/keys?x=1", "https://login.botframework.com.evil.example/v1/.well-known/keys",
                    "https://login.botframework.com/v2/.well-known/keys", "https://login.botframework.com/v1/.well-known/../keys", "https://login.microsoftonline.com/v1/.well-known/keys"):
            self.assertFalse(any(p.fullmatch(url) for _, p in calls), url)


class TheToken(Fixture):
    def test_a_good_token_is_let_in(self):
        self.let_in(token())

    def test_the_bearer_scheme_is_read_in_any_case_and_nothing_else_is(self):
        good = token()
        self.auth.authenticate(f"bearer {good}", SERVICE_URL, "msteams")
        self.auth.authenticate(f"BEARER {good}", SERVICE_URL, "msteams")
        for header in (None, 5, ["Bearer " + good], b"Bearer x"):
            with self.subTest(header=header):
                with self.assertRaises(Rejected) as caught:
                    self.auth.authenticate(header, SERVICE_URL, "msteams")
                self.assertEqual((caught.exception.status, caught.exception.reason), (401, "no-credentials"))
        for header in ("", "Bearer", "Bearer ", f"Bearer  {good}", f"Bearer {good} ", f" Bearer {good}", f"Basic {good}", f"Token {good}", good, f"Bearer {good}\n",
                       f"Bearer {good}, Bearer {good}", f"Bearer {good} x"):
            with self.subTest(header=header):
                self.refuse(None, 401, "no-bearer-token", header=header)

    def test_a_token_that_is_not_three_parts_of_base64url_is_refused(self):
        good = token()
        first, second, third = good.split(".")
        for value in ("", "a", "a.b", "a.b.c.d", f"{first}.{second}", f"{first}.{second}.", f".{second}.{third}", f"{first}..{third}", f"{good}.{third}", f"{first}.{second}.{third}=",
                      f"{first}=.{second}.{third}", f"{first}.{second}.{third}\n", f"{first} .{second}.{third}", f"{first}.{second}.{'A' * 9000}", "x" * 9000):
            with self.subTest(value=value[:40]):
                with self.assertRaises(Rejected) as caught:
                    self.let_in(value)
                self.assertEqual(caught.exception.status, 401)

    def test_a_part_that_is_not_json_or_not_an_object_is_refused(self):
        for raw in (b"not json", b"[]", b'"x"', b"5", b"null", b"\xff\xfe", b"{" * 5000):
            with self.subTest(raw=raw[:10]):
                self.refuse(token(raw_header=raw), 401, "malformed")
                self.refuse(token(raw_payload=raw), 401, "malformed")

    def test_the_algorithm_is_exactly_rs256(self):
        for alg in ("none", "None", "NONE", "HS256", "HS384", "HS512", "RS384", "RS512", "ES256", "PS256", "rs256", "RS256 ", "", None, 5, ["RS256"], {"a": 1}):
            with self.subTest(alg=alg):
                self.refuse(token(header={"alg": alg}), 401, "algorithm")
        header = json.dumps({"typ": "JWT", "kid": KEY_ID}).encode()
        self.refuse(token(raw_header=header), 401, "algorithm")

    def test_alg_none_with_no_signature_or_with_any_signature_is_refused(self):
        first = b64(json.dumps({"alg": "none", "typ": "JWT", "kid": KEY_ID}).encode())
        second = b64(json.dumps({"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600, "serviceurl": SERVICE_URL}).encode())
        for third in ("", "AAAA", b64(sign(f"{first}.{second}".encode()))):
            with self.subTest(third=third[:6]):
                with self.assertRaises(Rejected) as caught:
                    self.let_in(f"{first}.{second}.{third}")
                self.assertEqual(caught.exception.status, 401)

    def test_a_token_that_an_hmac_made_with_the_public_key_as_its_secret_is_refused(self):
        """The confusion of RS256 with HS256: the key of the service is public, so anybody could make this signature."""
        secrets_to_try = (N.to_bytes(K, "big"), b64(N.to_bytes(K, "big")).encode(), json.dumps(jwk()).encode(), KEY_ID.encode())
        for secret in secrets_to_try:
            for alg in ("HS256", "RS256"):
                with self.subTest(alg=alg, secret=secret[:6]):
                    head = b64(json.dumps({"alg": alg, "typ": "JWT", "kid": KEY_ID}).encode())
                    body = b64(json.dumps({"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600, "serviceurl": SERVICE_URL}).encode())
                    mac = hmac.new(secret, f"{head}.{body}".encode(), hashlib.sha256).digest()
                    with self.assertRaises(Rejected) as caught:
                        self.let_in(f"{head}.{body}.{b64(mac)}")
                    self.assertEqual(caught.exception.status, 401)
                    self.assertIn(caught.exception.reason, ("algorithm", "signature"))

    def test_the_header_is_the_one_of_the_connector(self):
        for changed in ({"typ": "jwt"}, {"typ": "at+jwt"}, {"typ": 5}, {"crit": ["exp"]}, {"crit": []}, {"kid": ""}, {"kid": 5}, {"kid": None}, {"kid": "a b"}, {"kid": "x" * 201}, {"kid": ["a"]}):
            with self.subTest(changed=changed):
                self.refuse(token(header=changed), 401, "header")
        head = json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
        self.refuse(token(raw_header=head), 401, "header")  # no kid
        self.let_in(token(header={"x5t": "other", "cty": "x"}))  # headers that nothing here reads do no harm

    def test_a_key_that_the_token_brings_along_is_never_used(self):
        def by_attacker(message: bytes) -> bytes:
            length = (N_ATTACKER.bit_length() + 7) // 8
            return raw_sign(padded(digest_info(message), length), D_ATTACKER, N_ATTACKER)
        for extra in ({"jwk": jwk(n=N_ATTACKER)}, {"jku": "https://evil.example/keys"}, {"x5u": "https://evil.example/cert"}, {"x5c": ["AAAA"]}):
            with self.subTest(extra=list(extra)):
                self.refuse(token(header=extra, signer=by_attacker), 401, "signature")

    def test_a_token_with_a_kid_that_is_not_listed_is_refused(self):
        self.refuse(token(header={"kid": "somebody-else"}), 401, "unknown-key")

    def test_a_changed_signature_or_a_changed_header_or_a_changed_payload_is_refused(self):
        good = token()
        first, second, third = good.split(".")
        raw = bytearray(botauth.b64url_decode(third))
        raw[10] ^= 0x01
        self.refuse(f"{first}.{second}.{b64(bytes(raw))}", 401, "signature")
        self.refuse(f"{first}.{b64(json.dumps({'iss': botauth.ISSUER, 'aud': APP_ID, 'exp': NOW + 99999, 'serviceurl': SERVICE_URL}).encode())}.{third}", 401, "signature")
        other = token(header={"x5t": "changed"})
        self.refuse(f"{other.split('.')[0]}.{second}.{third}", 401, "signature")
        self.refuse(token(signature=b"\x00" * K), 401, "signature")
        self.refuse(token(signature=sign(b"another message")), 401, "signature")
        self.refuse(token(signature=sign(b"x")[:-1]), 401, "signature")

    def test_the_issuer_is_exactly_the_bot_framework(self):
        for issuer in ("https://api.botframework.com/", "https://sts.windows.net/d6d49420-f39b-4df7-a1dc-d59a935871db/", "HTTPS://API.BOTFRAMEWORK.COM", "api.botframework.com", "", None, 5, ["https://api.botframework.com"]):
            with self.subTest(issuer=issuer):
                self.refuse(token(payload={"iss": issuer}), 401, "issuer")
        payload = {"aud": APP_ID, "exp": NOW + 3600, "serviceurl": SERVICE_URL}
        self.refuse(token(raw_payload=json.dumps(payload).encode()), 401, "issuer")

    def test_the_audience_is_the_app_id_of_the_bot_and_a_string(self):
        self.let_in(token(payload={"aud": APP_ID.upper()}))  # a GUID is the same GUID in capitals
        for audience in ("https://api.botframework.com", "another-app", "", None, 5, [APP_ID], [APP_ID, "x"], {"id": APP_ID}, APP_ID + "x", "x" + APP_ID):
            with self.subTest(audience=audience):
                self.refuse(token(payload={"aud": audience}), 401, "audience")
        self.refuse(token(raw_payload=json.dumps({"iss": botauth.ISSUER, "exp": NOW + 3600, "serviceurl": SERVICE_URL}).encode()), 401, "audience")

    def test_the_token_has_to_be_within_its_time_with_a_skew_of_five_minutes(self):
        self.let_in(token(payload={"exp": NOW - 299}))
        self.let_in(token(payload={"exp": NOW - 300}))
        self.refuse(token(payload={"exp": NOW - 301}), 401, "expired")
        self.refuse(token(payload={"exp": NOW - 86400}), 401, "expired")
        self.let_in(token(payload={"nbf": NOW + 299}))
        self.let_in(token(payload={"nbf": NOW + 300}))
        self.refuse(token(payload={"nbf": NOW + 301}), 401, "not-yet-valid")
        self.let_in(token(payload={"exp": NOW + 10 ** 9}))

    def test_a_time_that_is_not_a_number_is_refused_and_a_token_with_no_expiry_is_too(self):
        for exp in ("1900000000", None, True, False, [NOW + 3600], {"a": 1}, "", float("nan"), float("-inf"), 1e300):
            with self.subTest(exp=exp):
                raw = json.dumps({"iss": botauth.ISSUER, "aud": APP_ID, "exp": exp, "serviceurl": SERVICE_URL}).encode()
                self.refuse(token(raw_payload=raw), 401, "expired")
        for nbf in ("1", None, True, float("nan"), [0]):
            with self.subTest(nbf=nbf):
                raw = json.dumps({"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600, "nbf": nbf, "serviceurl": SERVICE_URL}).encode()
                self.refuse(token(raw_payload=raw), 401, "not-yet-valid")
        raw = json.dumps({"iss": botauth.ISSUER, "aud": APP_ID, "serviceurl": SERVICE_URL}).encode()
        self.refuse(token(raw_payload=raw), 401, "expired")
        raw = json.dumps({"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600, "serviceurl": SERVICE_URL}).encode()
        self.let_in(token(raw_payload=raw))  # a token with no nbf is within its time when its exp is not over

    def test_the_service_url_of_the_token_is_the_one_of_the_activity(self):
        self.let_in(token(), "https://SMBA.trafficmanager.net/emea/")
        for other in ("https://smba.trafficmanager.net/emea", "https://smba.trafficmanager.net/amer/", "https://evil.example/emea/", "http://smba.trafficmanager.net/emea/", "", " "):
            with self.subTest(other=other):
                self.refuse(token(), 401, "service-url" if other.strip() else "no-credentials", other)
        self.let_in(token(raw_payload=json.dumps({"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600, "serviceUrl": SERVICE_URL}).encode()))
        for payload in ({"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600},
                        {"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600, "serviceurl": 5},
                        {"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600, "serviceurl": "https://evil.example/"},
                        {"iss": botauth.ISSUER, "aud": APP_ID, "exp": NOW + 3600, "serviceurl": SERVICE_URL, "serviceUrl": "https://evil.example/"}):
            with self.subTest(payload=payload):
                self.refuse(token(raw_payload=json.dumps(payload).encode()), 401, "service-url")
        for missing in (None, 5, ["x"]):
            with self.assertRaises(Rejected):
                self.auth.authenticate(f"Bearer {token()}", missing, "msteams")

    def test_the_key_has_to_be_endorsed_for_teams_and_the_answer_is_403(self):
        documents = Documents(keys={"keys": [jwk(endorsements=["skype", "webchat"])]})
        auth = BotAuthenticator(APP_ID, KeyStore(documents, self.clock), self.clock)
        with self.assertRaises(Rejected) as caught:
            auth.authenticate(f"Bearer {token()}", SERVICE_URL, "msteams")
        self.assertEqual((caught.exception.status, caught.exception.reason), (403, "endorsement"))
        for key in ({"keys": [jwk(endorsements=[])]}, {"keys": [jwk(endorsements=["conversationconductorivr"])]}):
            with self.subTest(key=key["keys"][0]["endorsements"]):
                auth = BotAuthenticator(APP_ID, KeyStore(Documents(keys=key), self.clock), self.clock)
                with self.assertRaises(Rejected) as caught:
                    auth.authenticate(f"Bearer {token()}", SERVICE_URL, "msteams")
                self.assertEqual(caught.exception.status, 403)
        without = {k: v for k, v in jwk().items() if k != "endorsements"}  # a key that lists no channel at all is endorsed for none
        auth = BotAuthenticator(APP_ID, KeyStore(Documents(keys={"keys": [without]}), self.clock), self.clock)
        with self.assertRaises(Rejected) as caught:
            auth.authenticate(f"Bearer {token()}", SERVICE_URL, "msteams")
        self.assertEqual(caught.exception.status, 403)
        auth = BotAuthenticator(APP_ID, KeyStore(Documents(keys={"keys": [{**jwk(), "endorsements": None}]}), self.clock), self.clock)
        with self.assertRaises(Rejected) as caught:
            auth.authenticate(f"Bearer {token()}", SERVICE_URL, "msteams")
        self.assertEqual((caught.exception.status, caught.exception.reason), (401, "unknown-key"), "a key whose endorsements are not a list is not a key")

    def test_a_call_from_another_channel_is_not_endorsed_even_with_a_good_token_and_a_key_that_lists_it(self):
        documents = Documents(keys={"keys": [jwk(endorsements=["msteams", "webchat", "directline"])]})
        auth = BotAuthenticator(APP_ID, KeyStore(documents, self.clock), self.clock)
        for channel in ("webchat", "directline", "emulator", "MSTEAMS", "msteams ", "", "skype"):
            with self.subTest(channel=channel):
                with self.assertRaises(Rejected) as caught:
                    auth.authenticate(f"Bearer {token()}", SERVICE_URL, channel)
                self.assertEqual((caught.exception.status, caught.exception.reason), (403, "endorsement"))
        for bad in (None, 5, ["msteams"]):
            with self.assertRaises(Rejected) as caught:
                auth.authenticate(f"Bearer {token()}", SERVICE_URL, bad)
            self.assertEqual(caught.exception.status, 401)

    def test_the_endorsement_of_an_unsigned_or_badly_signed_token_is_never_the_answer(self):
        """A caller that has no valid signature learns nothing about the endorsements: it gets the 401 of every other doubt."""
        documents = Documents(keys={"keys": [jwk(endorsements=["skype"])]})
        auth = BotAuthenticator(APP_ID, KeyStore(documents, self.clock), self.clock)
        with self.assertRaises(Rejected) as caught:
            auth.authenticate(f"Bearer {token(signature=sign(b'x'))}", SERVICE_URL, "msteams")
        self.assertEqual(caught.exception.status, 401)

    def test_with_no_way_to_read_the_keys_nothing_is_let_in(self):
        auth = BotAuthenticator(APP_ID, KeyStore(Documents(fail=True), self.clock), self.clock)
        with self.assertRaises(Rejected) as caught:
            auth.authenticate(f"Bearer {token()}", SERVICE_URL, "msteams")
        self.assertEqual((caught.exception.status, caught.exception.reason), (401, "unknown-key"))

    def test_the_app_id_of_the_bot_is_needed(self):
        for bad in ("", "  ", None, 5):
            with self.assertRaises(ValueError):
                BotAuthenticator(bad, self.store)  # type: ignore[arg-type]

    def test_the_check_has_no_switch(self):
        """Nothing here lets a caller or a setting turn the check off: the module has no flag, no environment variable and no argument that skips a step."""
        source = pathlib.Path(botauth.__file__).read_text(encoding="utf-8").lower()
        for word in ("environ", "getenv", "skip", "disable", "insecure", "verify=false", "debug", "allow_none"):
            self.assertNotIn(word, source, word)


if __name__ == "__main__":
    unittest.main()
