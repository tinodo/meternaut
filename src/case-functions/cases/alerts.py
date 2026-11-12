"""The words of a trip, and the one letter that tells the owner about it.

A trip is the harness or the drift check pulling the switch `investigation`: the AI agents stop, new cases of the investigation stop, and everything else goes on (cases/harness.py). It
is narrow by construction: no other switch is ever pulled, and a person releases it. The letter is written by code from the fixed sentences below plus a detail that code composes from a
closed vocabulary (control ids, counts, the names of settings): it holds no text of an estate and no text that a model wrote, so nothing in it can steer a reader. It goes to the people
with the role owner, through the one mail path (mail.py), as the kind `alert`.
"""
from __future__ import annotations

import datetime as dt
import html

from .letters import SUBJECT_PREFIX, Letter
from .plaintext import MAX_DETAIL, plain

# code -> (what the kill switch page shows as the reason, what the letter says happened)
REASONS = {
    "refusals": ("An agent was refused three times in one run.",
                 "In one run an AI agent was refused three times: it asked for a tool or for arguments outside its list, repeated a call, or gave an answer that code rejected."),
    "tokens": ("An agent used more tokens than its budget.",
               "In one run an AI agent used up the token budget that is written in the code."),
    "definition": ("A stored agent differs from the lock.",
                   "The definition of an AI agent in the Foundry project differs from the one that the repository locks, so somebody changed it outside a release."),
    "drift": ("A drift check failed.",
              "The drift check found that something that guards the agents is not as the repository says."),
}
SUBJECT = f"{SUBJECT_PREFIX} An agent safeguard stopped the investigation"
SWITCH_PAGE = "/ops/pause"


def switch_reason(code: str) -> str:
    """What the kill switch page shows as the reason of a trip."""
    return REASONS.get(code, ("An agent safeguard fired.", ""))[0]


def code_of(reason: str) -> str | None:
    """The code of a trip from the reason that the switch holds, or None for a switch that a person pulled: the letter of a trip that quiet hours held back is made again from it."""
    return next((code for code, (text, _) in REASONS.items() if text == reason), None)


def _when(moment: dt.datetime) -> str:
    moment = moment.replace(tzinfo=dt.timezone.utc) if moment.tzinfo is None else moment.astimezone(dt.timezone.utc)
    return moment.strftime("%A %d %B %Y, %H:%M UTC")


def paragraphs(code: str, detail: str, now: dt.datetime) -> list[tuple[str, str]]:
    """The letter as (kind, text) blocks: h1, p, muted, link (its text; the address is added by the caller)."""
    happened = REASONS.get(code, ("", "An agent safeguard fired."))[1]
    blocks = [
        ("h1", "An agent safeguard stopped the investigation"),
        ("p", happened),
    ]
    if plain(detail):
        blocks.append(("p", f"Detail: {plain(detail)}"))
    blocks += [
        ("h2", "What is stopped"),
        ("p", "The investigation by the AI agents: it opens no new case until a person releases the switch called Investigation. Waste that Meternaut planted itself, the approval of a change, "
              "the letters and the pages go on."),
        ("h2", "What is not affected"),
        ("p", "Meternaut holds no right to change Azure. A change is made only after a person approves it, with that person's own permissions, as before."),
        ("h2", "What to do"),
        ("p", "Open the kill switch page, read the reason, and resume the switch called Investigation when you have looked at the cause."),
        ("link", "Open the kill switch page"),
        ("h2", "Why you got this"),
        ("muted", "You hold the role owner on the list of people. This letter was written by code from fixed sentences. No AI model wrote it. Replies to it are not read."),
        ("muted", f"Written on {_when(now)}."),
    ]
    return blocks


def letter(code: str, detail: str, base_url: str, now: dt.datetime) -> Letter:
    """The letter of a trip: plain text and a small page that needs nothing from outside (no script, no image, no remote content)."""
    url = f"{base_url.rstrip('/')}{SWITCH_PAGE}"
    text_lines: list[str] = []
    body: list[str] = []
    for kind, value in paragraphs(code, detail, now):
        if kind == "link":
            text_lines += [f"{value}: {url}", ""]
            body.append(f'<p><a href="{html.escape(url, quote=True)}" style="color:#0b5cad;font-weight:600;">{html.escape(value)}</a></p>')
        elif kind in ("h1", "h2"):
            text_lines += [value, ("=" if kind == "h1" else "-") * min(len(value), 72), ""]
            body.append(f"<{kind} style=\"margin:{'0 0 12px' if kind == 'h1' else '20px 0 8px'};font-size:{'22px' if kind == 'h1' else '17px'};\">{html.escape(value)}</{kind}>")
        else:
            text_lines += [value, ""]
            body.append(f'<p style="margin:0 0 12px;color:{"#4a4a4a" if kind == "muted" else "#1b1b1b"};">{html.escape(value)}</p>')
    page = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="color-scheme" content="light dark">\n<title>{html.escape(SUBJECT)}</title>\n</head>\n'
            '<body style="margin:0;padding:16px;font-family:Segoe UI,Arial,sans-serif;font-size:16px;line-height:1.5;color:#1b1b1b;background-color:#ffffff;">\n'
            '<div style="max-width:600px;">\n' + "\n".join(body) + "\n</div>\n</body>\n</html>\n")
    return Letter(SUBJECT, page, "\n".join(text_lines).rstrip() + "\n")
