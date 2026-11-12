"""The addresses of the buttons of a Teams card that answer, and the link tokens in them (docs/proposals/19-teams-cards-through-power-automate.md).

An answer is an Action.OpenUrl to <page of the request>/<approve|confirm|decline>?code=<plan code>&token=<link token>. Opening it changes nothing: the page checks the person, the request, the code and
the token and sends the form of the answer by itself (cases/web/approval.py), so every check of that answer stays. The link token is a one-time token of the store, made with the card for one person and one
request; it keeps the answer, the plan's code and whether the card asked twice already. The page only peeks at it and the form uses it up. Pure functions over the standard library, imported by the pages.
"""
from __future__ import annotations

import json
import re
from typing import Callable, NamedTuple

VERBS = ("approve", "confirm", "decline")
PAGE_ADDRESS = re.compile(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~-]+)*/ok/[A-Za-z0-9_-]{1,64}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{20,64}")
ANSWER_ADDRESS = re.compile(rf"(?P<page>{PAGE_ADDRESS.pattern})/(?P<verb>{'|'.join(VERBS)})\?code=(?P<code>[A-Za-z0-9]{{4,16}})&token=(?P<token>{TOKEN.pattern})")
MIN_SECONDS = 900  # a token lives at least a quarter of an hour: a request about to expire still has its buttons

# The words on the buttons, by kind of request: the same on the card, on the page that sends the answer and on the page of the request.
LABEL = {
    "change": {"approve": "Approve", "confirm": "Confirm", "decline": "Decline"},
    "advice": {"approve": "Worth acting on", "decline": "Not worth it"},
}
PAGE_LABEL = "Open the request"
BACK_LABEL = "No, go back"


class Link(NamedTuple):
    verb: str
    code: str
    sure: bool


def sure_label(called: str) -> str:
    return f"Yes, {called} it"


def answer_url(page_url: str, verb: str, code: str, token: str) -> str:
    """The address of a button that answers; ValueError for anything that is not exactly that."""
    url = f"{page_url}/{verb}?code={code}&token={token}"
    if not ANSWER_ADDRESS.fullmatch(url):
        raise ValueError("not the address of a button that answers")
    return url


def mint(new: Callable[..., str], oid: str, plan_id: str, code: str, verb: str, sure: bool, seconds: float) -> str:
    """A link token for this person and request (`new` is the store's nonce_new) that lives `seconds`, at least MIN_SECONDS."""
    return new(oid, plan_id, max(MIN_SECONDS, int(seconds)), json.dumps([verb, code, int(sure)], separators=(",", ":")))


def read(peek: Callable[[str, str, str], str | None], oid: str, plan_id: str, token: object) -> Link | None:
    """What a link token keeps, without using it up (`peek` is the store's nonce_peek); None for anything that is not a good token for this person and request."""
    kept = peek(token, oid, plan_id) if isinstance(token, str) and TOKEN.fullmatch(token) else None
    try:
        verb, code, sure = json.loads(kept) if kept else (None, None, None)
    except (ValueError, TypeError):
        return None
    return Link(verb, code, bool(sure)) if verb in VERBS and isinstance(code, str) else None
