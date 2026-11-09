"""The Teams card of a decision brief: an Adaptive Card of schema 1.5, as a pure function of the brief (brief.py) and what the card needs besides it.

The page, the letter and the card are renders of the same brief (AGENTS.md rule 34), and the card is the one that a person answers fastest. It holds what a person needs to decide
in a minute and nothing more: the title and the place under it, the risk, how sure and what a change leaves behind as one line of words, what it is worth (the figure a year and a month, its
level and its basis, and once that money is in US dollars: the words of the pages, cases/stake.py), the facts, what changes, whether it can be undone, what could go wrong, whose resource it
is, the answers that exist, and ONE footer line (that an AI wrote it and which models, why this person got it, who is responsible for Meternaut). Nothing else: no reasoning box,
no counters, no banner.

The answers. An approval that changes Azure is never taken on a card: the card's one link, "Review and decide", is the page of the request, where the person signs in to Azure and
Azure checks the person's own rights. A card never carries an Azure token. The answers that change nothing in Azure are Action.Execute actions that call the bot with the tapper's own
identity: "Worth acting on" and "Not worth it" for advice, "This is not mine", "Decide later" and one "Ask or tell" with a text box. Every action carries the id of the request, the plan
code and a one-time token that was made for this person (the same checks as the page's form), and an action that takes no input says so (associatedInputs none).

Text that did not come from code (names, tag values, what a model wrote) has been through brief.plain (no hidden or direction character, no line break, no link) and is escaped here
for the Markdown that a TextBlock renders, so that it can neither start a link, a list or a bold run nor hide what the card says. No text of the estate is ever put in a link: the
address of the page is made from the base address and the id of the request alone.

Every card is checked by cardcheck.check before it is handed on, and a card that does not pass is not made.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from . import cardcheck
from .brief import OPTIONS_SHORT, PAUSED_ADVICE, PAUSED_CHANGES, TWO_PEOPLE, Brief, footer_line, plain
from .stake import chips_of, place_of, stake_of, title_text

SENDER = "Meternaut (AI)"
MAX_KINDS = 3  # the kinds of data that nothing reads which a card lists
CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"
MESSAGE_TYPE = "application/vnd.microsoft.activity.message"
VERBS = ("approve", "decline", "not_mine", "later", "ask")  # the answers of the decider (models.DECISIONS); the card's verbs are the same words
MAX_NOTE = 300  # the most characters of the text box: what the decider keeps of a note
TITLES = {
    "change": {"approve": "Review and decide", "decline": "Decline", "not_mine": "This is not mine", "later": "Decide later", "ask": "Ask or tell"},
    "advice": {"approve": "Worth acting on", "decline": "Not worth it", "not_mine": "This is not mine", "later": "Decide later", "ask": "Ask or tell"},
}
KIND_LABELS = {"change": "Needs your OK", "advice": "Needs your answer", "result": "Recorded", "first_contact": "Hello"}
# The text of a notification: what Teams shows on a lock screen. No resource name and no amount, like the subject of a letter (AGENTS.md rule 26 (c)).
SUMMARIES = {"change": "[Meternaut] A change to Azure waits for your OK", "advice": "[Meternaut] A decision waits for you", "result": "[Meternaut] A change to Azure has run",
             "first_contact": "[Meternaut] An AI assistant for Azure costs will write to you"}
PAGE_BASE = re.compile(r"(?:https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?)(?:/(?!\.+(?:/|$))[A-Za-z0-9._~-]+)*")
OPAQUE = re.compile(r"[A-Za-z0-9_-]{1,64}")
PLAN_CODE = re.compile(r"[A-Za-z0-9]{4,16}")
NONCE = re.compile(r"[A-Za-z0-9_-]{20,64}")
# What a TextBlock reads as Markdown (the subset that Teams shows), a < that could open a mention or a tag, and the characters that start a list at the start of a text.
MARKDOWN = re.compile(r"([\\`*_\[\]()#<>])")
GENTLE = re.compile(r"([\\`*_\[\]#<>])")
LIST_DASH = re.compile(r"^[-+](?=\s)")
LIST_NUMBER = re.compile(r"^(\d+)\.(?=\s)")
TEXT_FEATURE = re.compile(r"\{(?=\{)")
WHY_APPROVER = "You got this because you are named as an approver of this request."


class CardError(Exception):
    """A card that cannot be made, or that does not pass the check. The text names the problems and never holds a token."""


@dataclass(frozen=True)
class CardContext:
    """What a card needs besides the brief: the address of the page of its request (page_url makes it), a one-time token that was made for the person and the plan (empty when the
    card shows no answer), why the person got it, and who is responsible for Meternaut (people, each as plain text with the address: the card names the first)."""

    page_url: str
    nonce: str = ""
    why: str = WHY_APPROVER
    contacts: tuple[str, ...] = ()


def page_url(base_url: str, plan_id: str) -> str:
    """The address of the page of a request: the base address of the web page, /ok/ and the opaque id. Nothing else ever goes in a link."""
    base = (base_url or "").strip().rstrip("/")
    if not PAGE_BASE.fullmatch(base):
        raise CardError("the address of the web page is not like https://host")
    if not OPAQUE.fullmatch(plan_id or ""):
        raise CardError("the id of a request in a link is an opaque id of letters, digits, hyphens and underscores")
    return f"{base}/ok/{plan_id}"


def _text(value: object, limit: int) -> str:
    """brief.plain, and no two curly brackets in a row: a TextBlock turns {{DATE(...)}} and {{TIME(...)}} into a date or a time, and no text of the estate may make it do that."""
    return TEXT_FEATURE.sub("{ ", plain(value, limit))


def md(value: object, limit: int = 200) -> str:
    """Text from the estate or from a model, for a TextBlock: one safe line (brief.plain) with every character that Markdown reads escaped, so that it shows as it is written."""
    escaped = MARKDOWN.sub(r"\\\1", _text(value, limit))
    return LIST_NUMBER.sub(r"\1\\.", LIST_DASH.sub(lambda found: "\\" + found.group(0), escaped))


def gentle(value: object, limit: int = 200) -> str:
    """The same for text that people and code wrote (the models of the footer, a name and an address): the characters that start emphasis, code or a link, and not the round brackets."""
    return GENTLE.sub(r"\\\1", _text(value, limit))


# -- the pieces ----------------------------------------------------------------------------------------------------------------------------------

def _block(id_: str, text: str, **more: object) -> dict:
    return {"type": "TextBlock", "id": id_, "text": text, "wrap": True, **more}


def _header(kind: str) -> dict:
    return {"type": "ColumnSet", "id": "header", "columns": [
        {"type": "Column", "width": "stretch", "items": [_block("ai-label", SENDER, weight="Bolder")]},
        {"type": "Column", "width": "auto", "items": [_block("kind", KIND_LABELS[kind], isSubtle=True)]},
    ]}


def _stake(brief: Brief) -> dict:
    """What is at stake, as a tile in the words of the pages (cases/stake.py, which uses the code of the pages): the figure a year in large type, its label and the month, its basis or why
    there is none, and, where a figure is shown, the one line that says what the money is in (AGENTS.md rule 13 (c) and 36). How long the request has waited and what waiting costs are on the
    page and not on the card: neither helps a person decide, and the second one pushes."""
    stake = stake_of(brief)
    label = f"{md(stake.label, 80)}. {md(stake.month, 40)} a month." if stake.month else f"{md(stake.label, 80)}."
    items = [_block("saving-word", label, weight="Bolder"), _block("price-basis", md(stake.note, 300), isSubtle=True)]
    if stake.year:
        items = [_block("value", md(stake.year, 60), size="Large", weight="Bolder"), *items, _block("money", md(stake.money, 120), isSubtle=True, size="Small")]
    return {"type": "Container", "id": "value-tile", "style": "emphasis", "items": items}


def _place(brief: Brief) -> list[dict]:
    """The line under the title: what kind of resource and its resource group (none for a request about many resources: its title counts them)."""
    place = place_of(brief)
    return [_block("place", md(place, 200), isSubtle=True)] if place else []


def _chips(brief: Brief) -> dict:
    """The chips of the page as one line of words: the risk, how sure the AIs are, and what a change leaves behind (or that an answer changes nothing in Azure)."""
    return _block("chips", md(", ".join(chips_of(brief)), 120), weight="Bolder")


def _learned(brief: Brief) -> list[dict]:
    """The one line about how past requests like this were answered, and, when it changes what can be said, the one sentence about what the access cannot see."""
    return [_block(name, md(text, 240)) for name, text in (("past", brief.past), ("access", brief.access)) if text]


def _facts(brief: Brief) -> list[dict]:
    rows = [{"title": md(fact.label, 60), "value": f"{md(fact.value, 120).rstrip('.')}. Source: {md(fact.source, 80).rstrip('.')}."} for fact in brief.facts[:3]]
    return [{"type": "FactSet", "id": "facts", "facts": rows}] if rows else []


def _unread(brief: Brief) -> list[dict]:
    """The data that a workspace takes in and nothing reads, in the room that a card has: the method in one sentence, the first kinds of data (the largest first), what was not counted when
    something was, and the choices in one line. The page has every line, the readers of each, the whole sentence about what was not counted and the whole of every choice."""
    unread = brief.unread
    if unread is None:
        return []
    shown = unread.lines[:MAX_KINDS]
    left = len(unread.lines) - len(shown) + unread.more
    blocks = [_block("unread", f"**Data that nothing reads.** {md(unread.sentence, 240)}")]
    blocks += [_block(f"unread-{number}", f"{md(line.kind, 60)}, {md(line.gb, 24)} ({md(line.percent, 30)})") for number, line in enumerate(shown, 1)]
    if left > 0:
        blocks.append(_block("unread-more", f"{left} more"))
    if unread.caveat:
        blocks.append(_block("unread-caveat", md(unread.caveat, 200), isSubtle=True))
    if brief.options:
        blocks.append(_block("options", md(OPTIONS_SHORT, 200)))
    return blocks


def _undo(brief: Brief) -> dict:
    """Whether it can be undone: one bold line when it cannot, and nothing decorative."""
    if not brief.undo.reversible:
        return _block("undo", "Undo: This cannot be undone.", weight="Bolder")
    return _block("undo", f"**Undo:** {md(brief.undo.how, 200)}")


def _decision_lines(brief: Brief) -> list[dict]:
    """What changes and with whose rights, whether it can be undone, what could go wrong and whose resource it is: one line each."""
    approving = brief.kind == "change"
    change = md(brief.change, 300) + (" It runs with your own permissions, after you sign in to Azure." if approving else "") + (f" {TWO_PEOPLE}" if brief.two_people and approving else "")
    return [_block("change", f"**{'If you approve' if approving else 'If you answer'}:** {change}"), _undo(brief),
            _block("risk", f"**Risk, {md(brief.risk.level, 12)}:** {md(brief.risk.text, 240)}"), _block("owner", f"**Owner:** {md(brief.owner.text, 200)}")]


def _data(brief: Brief, nonce: str) -> dict:
    return {"requestId": brief.plan_id, "planCode": brief.plan_code, "nonce": nonce}


def _execute(brief: Brief, ctx: CardContext, verb: str, title: str, *, inputs: bool = False) -> dict:
    return {"type": "Action.Execute", "title": title, "verb": verb, "data": _data(brief, ctx.nonce), "associatedInputs": "auto" if inputs else "none",
            "fallback": {"type": "Action.OpenUrl", "title": "Open on the page", "url": ctx.page_url}}


def _answer_parts(brief: Brief, ctx: CardContext) -> list[dict]:
    """The answers that exist for this person right now: the link to the page for a change (its approval is made there), the actions that change nothing in Azure, and the text box
    with its own button. A switch that holds an answer has taken it out of brief.answers, and the card says so."""
    titles = TITLES[brief.kind]
    actions: list[dict] = []
    if brief.kind == "change":
        # An approval that changes Azure is made on the page, where the person signs in to Azure: the link is the only way to it.
        approving = "approve" in brief.answers
        actions.append({"type": "Action.OpenUrl", "id": "page", "title": "Review and decide" if approving else "See the request", "url": ctx.page_url,
                        **({"style": "positive"} if approving else {})})
    else:
        for verb in ("approve", "decline"):
            if verb in brief.answers:
                actions.append({**_execute(brief, ctx, verb, titles[verb]), "id": verb, **({"style": "positive"} if verb == "approve" else {})})
        actions.append({"type": "Action.OpenUrl", "id": "page", "title": "See the evidence", "url": ctx.page_url})
    for verb in ("not_mine", "later"):
        if verb in brief.answers:
            actions.append({**_execute(brief, ctx, verb, titles[verb]), "id": verb})
    held = [] if "approve" in brief.answers else [_block("paused", PAUSED_ADVICE if brief.kind == "advice" else PAUSED_CHANGES, weight="Bolder")]
    parts: list[dict] = [*held, {"type": "ActionSet", "id": "decisions", "actions": actions}]
    if "ask" in brief.answers:
        parts.append({"type": "Input.Text", "id": "message", "label": "Ask or tell", "isMultiline": True, "maxLength": MAX_NOTE, "isRequired": True,
                      "errorMessage": "Write a few words first.", "placeholder": "A question, or something I should know. This approves nothing."})
        parts.append({"type": "ActionSet", "id": "ask", "actions": [{**_execute(brief, ctx, "ask", titles["ask"], inputs=True), "id": "send-ask"}]})
    return parts


def footer(models: Sequence[str], why: str, contacts: Sequence[str]) -> dict:
    """The one footer line: that an AI wrote this and which models, why the person got it and who is responsible for Meternaut (the first of the contacts, as the page names one person), as
    plain text."""
    line = footer_line([gentle(m, 60) for m in models], gentle(why, 200), [gentle(c, 160) for c in contacts[:1]])
    return _block("ai-footer", line, isSubtle=True, size="Small", separator=True)


def _check_context(ctx: CardContext, brief: Brief, *, needs_nonce: bool) -> None:
    if not isinstance(ctx, CardContext) or not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~-]+)*/ok/[A-Za-z0-9_-]{1,64}", ctx.page_url or ""):
        raise CardError("the card needs the address of the page of its request (page_url)")
    if not ctx.page_url.endswith(f"/ok/{brief.plan_id}") and brief.plan_id:
        raise CardError("the address of the page is not the page of this request")
    if needs_nonce:
        if not NONCE.fullmatch(ctx.nonce or ""):
            raise CardError("the card needs a one-time token that was made for the person")
        if not OPAQUE.fullmatch(brief.plan_id or "") or not PLAN_CODE.fullmatch(brief.plan_code or ""):
            raise CardError("the card needs the id and the code of the plan")


def _finish(card: dict) -> dict:
    problems = cardcheck.check(card)
    if problems:
        raise CardError("the card does not pass the check: " + "; ".join(problems[:5]))
    return card


def _card(brief: Brief, ctx: CardContext, kind: str, body: list[dict], what: str) -> dict:
    title = title_text(brief)
    return _finish({
        "type": "AdaptiveCard", "$schema": cardcheck.SCHEMA, "version": cardcheck.VERSION, "msteams": {"width": "Full"},
        "fallbackText": f"{SENDER}: {md(title, 200)}. {what} Open it on the page: {ctx.page_url} Written by an AI.",
        "body": [_header(kind), _block("headline", md(title, 200), size="Large", weight="Bolder", style="heading"), *body, footer(brief.models, ctx.why, ctx.contacts)],
    })


# -- the cards -----------------------------------------------------------------------------------------------------------------------------------

def decision_card(brief: Brief, ctx: CardContext, notice: str = "") -> dict:
    """The card of a request that waits for an answer: a change that a person may approve (kind change) or advice that changes nothing (kind advice). `notice` is one plain line
    at the top, for the card that replaces a card after an answer that leaves the request open (a question, or "later")."""
    if brief.kind not in ("change", "advice") or brief.state != "open" or not brief.answers:
        raise CardError("only a request that is open and that this person may answer has a decision card")
    _check_context(ctx, brief, needs_nonce=True)
    body: list[dict] = []
    if notice:
        body.append(_block("notice", md(notice, 240), weight="Bolder"))
    body += [*_place(brief), _chips(brief), _stake(brief), _block("confidence", f"**How sure: {md(brief.confidence.level, 12)}.** {md(brief.confidence.because, 240)}"), *_learned(brief),
             *_facts(brief), *_unread(brief), *_decision_lines(brief), *_answer_parts(brief, ctx)]
    return _card(brief, ctx, brief.kind, body, "A decision waits for you.")


def result_card(brief: Brief, ctx: CardContext, notice: str = "") -> dict:
    """The card of a request that is not open any more, or that a change has run for: what became of it in plain lines, what it saves (the figure of the pages: Verified only when the cost
    lines after the change confirm it), whether it can be undone, and the page. It holds no answer, so it holds no token."""
    _check_context(ctx, brief, needs_nonce=False)
    outcome = brief.outcome
    body: list[dict] = []
    if notice:
        body.append(_block("notice", md(notice, 240), weight="Bolder"))
    body += _place(brief)
    if outcome.state:
        body.append(_block("outcome", md(outcome.title, 80), weight="Bolder"))
        body += [_block(f"outcome-line-{n}", md(line, 300)) for n, line in enumerate(outcome.lines[:4], 1)]
    elif not notice:
        body.append(_block("outcome", "Nothing can be answered here now.", weight="Bolder"))
    if outcome.state in ("done", "verified"):
        body += [_stake(brief), _undo(brief)]
    body.append({"type": "ActionSet", "id": "decisions", "actions": [{"type": "Action.OpenUrl", "id": "page", "title": "See the request", "url": ctx.page_url}]})
    return _card(brief, ctx, "result", body, "What became of a request.")


def card_for(brief: Brief, ctx: CardContext, notice: str = "") -> dict:
    """The card that shows a brief as it is now: the decision card while the request is open and this person may answer it, the card of what became of it otherwise."""
    if brief.kind in ("change", "advice") and brief.state == "open" and brief.answers:
        return decision_card(brief, ctx, notice)
    return result_card(brief, ctx, notice)


def first_contact_card(name: object, base_url: str, contacts: Sequence[str] = (), why: str = "You got this because you are on my list of people.") -> dict:
    """What Meternaut says when the app is added for a person, in three sentences, with the one link to the start page of the web page."""
    base = (base_url or "").strip().rstrip("/")
    if not PAGE_BASE.fullmatch(base):
        raise CardError("the address of the web page is not like https://host")
    return _finish({
        "type": "AdaptiveCard", "$schema": cardcheck.SCHEMA, "version": cardcheck.VERSION, "msteams": {"width": "Full"},
        "fallbackText": f"{SENDER}: an AI assistant for Azure costs will write to you. Open the web page: {base}/ Written by an AI.",
        "body": [_header("first_contact"), _block("headline", "An AI assistant for Azure costs will write to you", size="Large", weight="Bolder", style="heading"),
                 _block("hello", f"Hello {md(name, 80)}, I am Meternaut, an AI that looks for Azure resources that cost money and are not used, and I write to you when a decision waits for you."),
                 _block("rules", "I change nothing myself: a change to Azure is decided on a web page and runs with your own Azure rights. Answers that change nothing, such as a question, "
                                 "are recorded here."),
                 _block("settings", "You can pause or stop my messages under Settings on the web page."),
                 {"type": "ActionSet", "id": "decisions", "actions": [{"type": "Action.OpenUrl", "id": "page", "title": "Open the web page", "url": f"{base}/"}]},
                 footer((), why, contacts)],
    })


# -- what goes to Teams --------------------------------------------------------------------------------------------------------------------------

def attachment(card: dict) -> dict:
    """The card as the attachment of a message activity."""
    return {"contentType": CONTENT_TYPE, "content": card}


def invoke_card(card: dict) -> dict:
    """The answer to an adaptiveCard/action invoke that replaces the card (Universal Actions: the body of the HTTP answer; Learn, "Universal Action Model")."""
    return {"statusCode": 200, "type": CONTENT_TYPE, "value": card}


def invoke_message(text: object) -> dict:
    """The answer to an invoke that shows a message and leaves the card as it is."""
    return {"statusCode": 200, "type": MESSAGE_TYPE, "value": plain(text, 300)}


def message_activity(card: dict, kind: str) -> dict:
    """A message activity that carries the card, with the text of the notification (no resource name, no amount)."""
    return {"type": "message", "summary": SUMMARIES[kind], "attachments": [attachment(card)]}
