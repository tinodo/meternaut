"""The claims challenge of Azure Resource Manager, read strictly.

A person who signed in without the multifactor check can use the console, but a create, update or delete then reaches Azure Resource Manager with a token that lacks it.
Azure answers 401 with a `www-authenticate` header: the scheme Bearer, the error `insufficient_claims` and a `claims` directive that holds a claims request (JSON, in base64).
The client has to send the person back to Microsoft Entra with that claims request and try again (Microsoft Learn: "Claims challenges, claims requests and client
capabilities"). The header comes from outside, so nothing of it is used unless it passes every rule below. Anything else is an ordinary refusal.

`claims_challenge` is pure: it reads text and returns text.
"""
from __future__ import annotations

import base64
import json
import re

MAX_HEADER = 4000
MAX_ENCODED = 2668  # the base64 text of 2000 bytes
MAX_BYTES = 2000
MAX_DEPTH = 4  # objects and lists inside each other, the object of the request included
MAX_KEYS = 20  # in all the objects together

_SCHEME = re.compile(r"Bearer[ \t]+", re.I)
# One directive: a name, and a value in quotes that holds printable ASCII without a quote or a backslash (so no escape is read), then a comma or the end. Nothing else is read.
_DIRECTIVE = re.compile(r'([A-Za-z][A-Za-z0-9_-]{0,40})[ \t]*=[ \t]*"([ !#-\[\]-~]*)"[ \t]*(?:,[ \t]*|\Z)')
_PRINTABLE = re.compile(r"[ !#-\[\]-~]*")
_STANDARD = re.compile(r"[A-Za-z0-9+/]*")
_URL_SAFE = re.compile(r"[A-Za-z0-9_-]*")
_TO_STANDARD = str.maketrans("-_", "+/")


def _directives(header: str) -> dict[str, str] | None:
    """The directives of a Bearer challenge by lower-case name, or None when it is not one that is made only of directives or names one twice."""
    scheme = _SCHEME.match(header)
    if scheme is None:
        return None
    found: dict[str, str] = {}
    position = scheme.end()
    while position < len(header):
        item = _DIRECTIVE.match(header, position)
        if item is None:
            return None
        name = item.group(1).lower()
        if name in found:
            return None
        found[name] = item.group(2)
        position = item.end()
    return found


def _decode(text: str) -> bytes | None:
    """Base64 or base64url, with the padding or without it (a padding that is there has to be the right one). Never a mix of the two alphabets."""
    plain = text.rstrip("=")
    missing = -len(plain) % 4
    if len(text) > MAX_ENCODED or len(text) - len(plain) not in (0, missing) or not (_STANDARD.fullmatch(plain) or _URL_SAFE.fullmatch(plain)):
        return None
    try:
        return base64.b64decode(plain.translate(_TO_STANDARD) + "=" * missing, validate=True)
    except ValueError:
        return None


def _refuse(_: str) -> None:
    raise ValueError("not allowed")


def _object(pairs: list[tuple[str, object]]) -> dict:
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("a key twice")
    return dict(pairs)


def _fits(value: object, depth: int, keys: list[int]) -> bool:
    """True when the value holds only what a claims request may hold: whole numbers, true, false, null, printable ASCII text, and at most MAX_DEPTH levels and MAX_KEYS keys."""
    if isinstance(value, str):
        return _PRINTABLE.fullmatch(value) is not None
    if value is None or isinstance(value, (bool, int)):
        return True
    if isinstance(value, dict):
        keys[0] += len(value)
        return depth <= MAX_DEPTH and keys[0] <= MAX_KEYS and all(_PRINTABLE.fullmatch(key) and _fits(item, depth + 1, keys) for key, item in value.items())
    if isinstance(value, list):
        return depth <= MAX_DEPTH and all(_fits(item, depth + 1, keys) for item in value)
    return False


def claims_challenge(header: object) -> str | None:
    """The claims request of a claims challenge as compact JSON text, or None when the header is anything else.

    The header has to be a Bearer challenge of quoted directives, with the error `insufficient_claims` and one `claims` directive (a directive that comes twice is refused).
    The claims are base64 or base64url of at most 2000 bytes of UTF-8 that hold one JSON object with at least one key, and nothing but what `_fits` allows. A number with a
    fraction or an exponent, a name that comes twice in an object and a text with a control character, a quote, a backslash or a character outside ASCII are refused."""
    if not isinstance(header, str) or len(header) > MAX_HEADER:
        return None
    directives = _directives(header)
    if directives is None or directives.get("error") != "insufficient_claims" or not directives.get("claims"):
        return None
    raw = _decode(directives["claims"])
    if raw is None or len(raw) > MAX_BYTES:
        return None
    try:
        request = json.loads(raw.decode("utf-8"), parse_float=_refuse, parse_constant=_refuse, object_pairs_hook=_object)
    except (ValueError, RecursionError):
        return None
    if not isinstance(request, dict) or not request or not _fits(request, 1, [0]):
        return None
    return json.dumps(request, separators=(",", ":"))
