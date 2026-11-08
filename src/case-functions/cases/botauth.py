"""Who may call the bot: the check of the JWT that the Bot Framework Connector sends with every request to the messaging endpoint.

There is no vetted JWT or RSA library that this repository may install (the package registries are blocked on the machines that build it, and AGENTS.md rule 15 (d) says the
standard library first), and the endpoint is public, so this is the one hand-written piece of cryptography of the project. It checks exactly what the Learn page "Authentication
with the Bot Connector API" asks of a bot that has no SDK (read on 2026-11-08), and nothing more is trusted:

1. the token comes in the Authorization header with the Bearer scheme, and is three base64url parts that are valid JSON;
2. the algorithm is exactly RS256 (no "none", no HS256: the key of an HMAC would be a public key), and the header is the shape of the Connector's own (typ JWT, a kid, no crit);
3. the key is the one that the OpenID key document lists for the kid (the document is fetched from login.botframework.com, kept for hours, and read again at once when a kid is
   not in it, at most once in five minutes), with at least 2048 bits and an exponent of at least 65537;
4. the signature is valid: RSASSA-PKCS1-v1_5 with SHA-256, checked as RFC 8017 sections 8.2.2 and 9.2 say. The expected encoded message is BUILT (00 01, the padding of ff bytes, 00,
   the DigestInfo of SHA-256 and the hash) and the WHOLE of it is compared with the recovered one in constant time. The padding of the recovered message is never parsed, so there is
   no parser to fool: the forgeries that parse (a short padding, garbage after the hash, a DigestInfo of another form or another hash) differ from the expected string and fail;
5. the issuer is https://api.botframework.com, the audience is the bot's own app id, the token is within its time (a skew of 5 minutes), and its service URL claim (the SDKs call
   it serviceurl and Learn calls it serviceUrl: either is read) is the serviceUrl of the activity that came with it;
6. the key is endorsed for the channel of the activity: the key document gives each key the channels that it may sign for, and a call from msteams needs a key with msteams. The
   documented answer to a missing endorsement is 403, and every other doubt is 401, with an empty body in both cases: nothing is told to a caller who fails.

What this check does not do: it does not say who the person is. The Connector vouches that the request came from Teams, and the activity names the person (from.aadObjectId); a forged
token would let a caller name any person. That is bounded by design, in teams.py: an approval that changes Azure is never taken from a card, and every answer needs the plan's code and
a one-time token that was made for that person.

It was tested against signatures that OpenSSL made (tests/botauth_vectors.py), against the classic forgeries of PKCS#1 v1.5, and against crafted tokens. It is meant to be replaced
by a vetted library as soon as one is available on an approved package feed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping

OPENID_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
KEYS_URL = re.compile(r"https://login\.botframework\.com/v1/\.well-known/[A-Za-z0-9._-]{1,64}")
ISSUER = "https://api.botframework.com"
CHANNEL = "msteams"
ALGORITHM = "RS256"
SKEW_SECONDS = 300  # the industry-standard clock skew that the Learn page names
REFRESH_SECONDS = 6 * 3600  # Microsoft asks for a fresh key document at least every 24 hours
UNKNOWN_KID_GAP_SECONDS = 300  # a kid that is not in the document makes one new read, and not more than one in this time, so that random kids cannot make the app fetch all day
MAX_STALE_SECONDS = 3 * 86400  # keys are used for this long when the document cannot be read, and then nothing is accepted
MAX_TOKEN_CHARS = 8192
MIN_MODULUS_BITS = 2048
MAX_MODULUS_BITS = 8192
MIN_EXPONENT = 65537
# DER of the DigestInfo of SHA-256 without its hash (RFC 8017, section 9.2, note 1): SEQUENCE { SEQUENCE { OID sha-256, NULL }, OCTET STRING of 32 bytes }.
SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
KID = re.compile(r"[A-Za-z0-9_.:+=/-]{1,200}")
BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
ENDORSEMENT = re.compile(r"[a-z0-9._-]{1,64}")
SERVICE_URL_CLAIMS = ("serviceurl", "serviceUrl")

Fetch = Callable[[str], bytes]


class Rejected(Exception):
    """The call is not let in. `status` is 401, or 403 for a key that is not endorsed for the channel; `reason` is a fixed word for the log and never holds part of a token."""

    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def botauth_calls() -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The two reads that this module makes, as the entries of the list of calls that the HTTP client allows: the OpenID metadata and the key document, on the one host."""
    return (("GET", re.compile(re.escape(OPENID_URL))), ("GET", KEYS_URL))


# -- base64url and integers ----------------------------------------------------------------------------------------------------------------------

def b64url_decode(text: object) -> bytes:
    """The bytes of a base64url text, and nothing else is accepted: no padding, no other alphabet, no whitespace, and no extra bits in the last character, so that one value
    has one spelling."""
    if not isinstance(text, str) or not BASE64URL.fullmatch(text) or len(text) % 4 == 1:
        raise ValueError("not base64url")
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != text:
        raise ValueError("not the canonical form of base64url")
    return raw


# -- RSASSA-PKCS1-v1_5 with SHA-256 (RFC 8017, sections 8.2.2 and 9.2) ---------------------------------------------------------------------------------

def encode_message(message: bytes, length: int) -> bytes:
    """EMSA-PKCS1-v1_5 (RFC 8017, 9.2): 00 01 ff..ff 00 DigestInfo(SHA-256, hash of the message), `length` bytes long. Raises ValueError when `length` is too short for it."""
    digest_info = SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
    if length < len(digest_info) + 11:  # the padding is at least 8 bytes of ff, with the three other bytes around it
        raise ValueError("the intended length of the encoded message is too short")
    return b"\x00\x01" + b"\xff" * (length - len(digest_info) - 3) + b"\x00" + digest_info


def acceptable_key(n: object, e: object) -> bool:
    """A public key that this verifier will use: integers, a modulus of 2048 to 8192 bits that is odd, and an odd exponent of at least 65537 that is below the modulus. A small
    exponent is what makes a cube-root forgery of a loosely checked signature possible, and a short modulus can be factored."""
    if type(n) is not int or type(e) is not int:
        return False
    return MIN_MODULUS_BITS <= n.bit_length() <= MAX_MODULUS_BITS and n % 2 == 1 and MIN_EXPONENT <= e < n and e % 2 == 1


def _verify(n: int, e: int, message: bytes, signature: bytes) -> bool:
    """RSASSAVERIFY of RFC 8017, 8.2.2, without the check of the key: the length of the signature is that of the modulus, the signature representative is below the modulus, and
    the message that it recovers is the whole of the encoded message that was built from `message`, compared in constant time."""
    length = (n.bit_length() + 7) // 8
    if len(signature) != length:
        return False
    s = int.from_bytes(signature, "big")
    if s >= n:  # RSAVP1: the representative is between 0 and n - 1
        return False
    recovered = pow(s, e, n).to_bytes(length, "big")  # I2OSP: the result is below n, so it fits in `length` bytes
    try:
        expected = encode_message(message, length)
    except ValueError:
        return False
    return hmac.compare_digest(recovered, expected)


def rsassa_pkcs1_v15_verify(n: int, e: int, message: bytes, signature: bytes) -> bool:
    """True when `signature` is a valid RSASSA-PKCS1-v1_5 signature with SHA-256 of `message` under the public key (n, e). It never raises for a signature or a key that is wrong."""
    if not acceptable_key(n, e) or not isinstance(message, (bytes, bytearray)) or not isinstance(signature, (bytes, bytearray)):
        return False
    return _verify(n, e, bytes(message), bytes(signature))


# -- the key document ----------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Key:
    kid: str
    n: int
    e: int
    endorsements: frozenset[str]


def parse_keys(document: object) -> dict[str, Key]:
    """The usable keys of a JWK set as the Bot Framework publishes it: RSA, for signing, with a kid, a modulus and an exponent that pass acceptable_key. A key that is anything else
    is left out, and so is a second key with the same kid (nothing is chosen between two). Its endorsements are the channels that it may sign for."""
    items = document.get("keys") if isinstance(document, dict) else None
    if not isinstance(items, list):
        return {}
    found: dict[str, Key] = {}
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        kid = item.get("kid")
        if not isinstance(kid, str) or not KID.fullmatch(kid):
            continue
        if kid in seen:
            found.pop(kid, None)
            continue
        seen.add(kid)
        if item.get("kty") != "RSA" or item.get("use", "sig") != "sig" or item.get("alg", ALGORITHM) != ALGORITHM:
            continue
        try:
            n, e = int.from_bytes(b64url_decode(item.get("n")), "big"), int.from_bytes(b64url_decode(item.get("e")), "big")
        except ValueError:
            continue
        endorsements = item.get("endorsements", [])
        if not acceptable_key(n, e) or not isinstance(endorsements, list):
            continue
        found[kid] = Key(kid, n, e, frozenset(x for x in endorsements if isinstance(x, str) and ENDORSEMENT.fullmatch(x)))
    return found


class KeyStore:
    """The keys of the Connector, read from login.botframework.com and kept in memory. `fetch` gives the bytes of an address or raises; it is the one place that touches the network.

    The document is read when the first token comes, again when the copy is six hours old, and again, at most once in five minutes, when a token names a kid that the copy does not
    hold. A read that fails leaves the copy as it is, which is used for up to three days and then no more."""

    def __init__(self, fetch: Fetch, clock: Callable[[], float] = time.time) -> None:
        self.fetch, self.clock = fetch, clock
        self._keys: dict[str, Key] = {}
        self._read_at: float | None = None  # when the copy was made
        self._tried_at: float | None = None  # when a read was last tried
        self._lock = threading.Lock()

    def _read(self) -> None:
        self._tried_at = self.clock()
        metadata = json.loads(self.fetch(OPENID_URL).decode("utf-8"))
        algorithms = metadata.get("id_token_signing_alg_values_supported") if isinstance(metadata, dict) else None
        address = metadata.get("jwks_uri") if isinstance(metadata, dict) else None
        if not isinstance(algorithms, list) or ALGORITHM not in algorithms or metadata.get("issuer") != ISSUER:
            raise ValueError("the OpenID metadata does not say what was expected")
        if not isinstance(address, str) or not KEYS_URL.fullmatch(address):
            raise ValueError("the key document is not on the host of the Bot Framework")
        keys = parse_keys(json.loads(self.fetch(address).decode("utf-8")))
        if not keys:
            raise ValueError("the key document holds no usable key")
        self._keys, self._read_at = keys, self.clock()

    def key(self, kid: str) -> Key | None:
        """The key of a kid, or None. It reads the document when it must, and it never raises: a read that fails is a key that is not there. A read is tried when none was made
        yet, when the copy is six hours old or when the kid is not in it, and then at most once in five minutes, whatever the reason: a failing host is not asked on every request."""
        with self._lock:
            now = self.clock()
            wanted = self._read_at is None or now - self._read_at >= REFRESH_SECONDS or kid not in self._keys
            if wanted and (self._tried_at is None or now - self._tried_at >= UNKNOWN_KID_GAP_SECONDS):
                try:
                    self._read()
                except Exception:  # noqa: BLE001 (any failure leaves the copy as it was)
                    pass
            if self._read_at is None or self.clock() - self._read_at >= MAX_STALE_SECONDS:
                return None
            return self._keys.get(kid)


# -- the token -----------------------------------------------------------------------------------------------------------------------------------

def _json_object(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as error:
        raise Rejected(401, "malformed") from error
    if not isinstance(value, dict):
        raise Rejected(401, "malformed")
    return value


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) < 1e15 else None


class BotAuthenticator:
    """Lets a request in or raises Rejected. `app_id` is the bot's own app id: the audience of every token that is meant for it."""

    def __init__(self, app_id: str, keys: KeyStore, clock: Callable[[], float] = time.time) -> None:
        if not isinstance(app_id, str) or not app_id.strip():
            raise ValueError("the bot has no app id")
        self.app_id, self.keys, self.clock = app_id.strip().lower(), keys, clock

    def authenticate(self, authorization: object, service_url: object, channel_id: object) -> None:
        """Checks the Authorization header of a request against the serviceUrl and the channelId of the activity in it. Returns nothing; raises Rejected(401 or 403)."""
        if not isinstance(authorization, str) or not isinstance(service_url, str) or not service_url.strip() or not isinstance(channel_id, str):
            raise Rejected(401, "no-credentials")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token or token != token.strip() or len(token) > MAX_TOKEN_CHARS or not TOKEN_SHAPE.fullmatch(token):
            raise Rejected(401, "no-bearer-token")
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        try:
            raw_header, raw_payload, signature = b64url_decode(encoded_header), b64url_decode(encoded_payload), b64url_decode(encoded_signature)
        except ValueError as error:
            raise Rejected(401, "malformed") from error
        header, claims = _json_object(raw_header), _json_object(raw_payload)
        if header.get("alg") != ALGORITHM:
            raise Rejected(401, "algorithm")
        if "crit" in header or ("typ" in header and header["typ"] != "JWT"):
            raise Rejected(401, "header")
        kid = header.get("kid")
        if not isinstance(kid, str) or not KID.fullmatch(kid):
            raise Rejected(401, "header")
        key = self.keys.key(kid)
        if key is None:
            raise Rejected(401, "unknown-key")
        if not rsassa_pkcs1_v15_verify(key.n, key.e, f"{encoded_header}.{encoded_payload}".encode("ascii"), signature):
            raise Rejected(401, "signature")
        self._claims(claims, service_url)
        # The endorsement comes after the signature, because only a signature that was checked says which key signed. A channel that is not msteams is not endorsed for either:
        # the bot is registered for Teams alone.
        if channel_id != CHANNEL or CHANNEL not in key.endorsements:
            raise Rejected(403, "endorsement")

    def _claims(self, claims: Mapping[str, object], service_url: str) -> None:
        if claims.get("iss") != ISSUER:
            raise Rejected(401, "issuer")
        audience = claims.get("aud")
        if not isinstance(audience, str) or audience.strip().lower() != self.app_id:
            raise Rejected(401, "audience")
        now = self.clock()
        expires, not_before = _number(claims.get("exp")), _number(claims.get("nbf")) if "nbf" in claims else None
        if expires is None or expires < now - SKEW_SECONDS:
            raise Rejected(401, "expired")
        if "nbf" in claims and (not_before is None or not_before > now + SKEW_SECONDS):
            raise Rejected(401, "not-yet-valid")
        claimed = [claims[name] for name in SERVICE_URL_CLAIMS if name in claims]  # the SDKs read "serviceurl"; the page of Learn writes "serviceUrl": either, and never two that differ
        if not claimed or not all(isinstance(value, str) and value.lower() == service_url.lower() for value in claimed):
            raise Rejected(401, "service-url")
