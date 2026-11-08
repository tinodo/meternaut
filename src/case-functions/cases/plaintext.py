"""Plain text: the one filter that every line and every letter of the AI safeguards goes through.

Standard library only and nothing of the package imported, so that the tools of the Operator can load it from their own folder together with lockfile.py and drift_rules.py.
"""
from __future__ import annotations

import re
import unicodedata

MAX_DETAIL = 240
_ALLOWED = re.compile(r"[^A-Za-z0-9 ,.:;()/+=_-]")
_LINK = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*:/+|www\.)\S*")


def plain(text: object, limit: int = MAX_DETAIL) -> str:
    """One line of plain characters: letters, digits and a few marks, and nothing else, cut at `limit`. An address of a page is not kept: a mail program would turn it into a link."""
    kept = "".join(ch for ch in unicodedata.normalize("NFKD", str(text)) if ch.isascii())
    one = " ".join(_ALLOWED.sub(" ", _LINK.sub(" (link removed) ", kept)).split())
    return one if len(one) <= limit else one[: limit - 3].rstrip() + "..."
