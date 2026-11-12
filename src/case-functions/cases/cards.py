"""The Teams card of a decision brief: an Adaptive Card of schema 1.4, as a pure function of the brief (brief.py) and what the card needs besides it.

The page, the letter and the card are renders of the same brief (AGENTS.md rule 34). A flow of Power Automate posts the card into the chat of a person (teamsqueue.py). It holds what a person needs to
decide in a minute and nothing more: the title and the place under it, the risk, how sure and what a change leaves behind in one line, what it is worth (the words of the pages, cases/stake.py), the
facts, what changes, whether it can be undone, what could go wrong, whose resource it is, the buttons, and ONE footer line (that an AI wrote it and which models, why this person got it, who is
responsible for Meternaut). No reasoning box, no counters, no banner.

The card carries the decision. The action that posts it cannot take an answer back, so each answer is an Action.OpenUrl to a page of the function app that sends it (cardlinks.py): "Approve", "Confirm" (the
first of two people), "Decline", and for advice "Worth acting on" and "Not worth it". A change that cannot be undone asks on the card: "Approve" shows "This cannot be undone: ..." with "No, go back" and
"Yes, delete it", and only "Yes" is a link (proposal 19 says that this toggle is not proven for the Flow bot). A card never carries an Azure token. A card whose links could not be made, or of a request that
a switch holds, has the link to the page only ("Review and decide", "See the request"). When the request ends, closed_card (no button) replaces the card.

Text that did not come from code (names, tag values, what a model wrote) has been through brief.plain and is escaped here for the Markdown that a TextBlock renders, so that it can neither start a link, a
list or a bold run nor hide what the card says. No text of the estate is ever put in a link.

Every card is checked by cardcheck.check, and one that does not pass is not made. A card that is too big for its message is replaced by minimal_card: the headline, the link and the footer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from . import cardcheck, cardlinks
from .brief import CHECK_FIRST_SHORT, GATEWAYS_SHORT, OPTIONS_SHORT, PAUSED_ADVICE, PAUSED_CHANGES, TWO_PEOPLE, Brief, called_of, footer_line, parse_time, plain
from .stake import chips_of, place_of, stake_of, title_text

SENDER = "Meternaut (AI)"
MAX_KINDS = 3  # the kinds of data that nothing reads which a card lists
KIND_LABELS = {"change": "Needs your OK", "advice": "Needs your answer", "result": "Recorded", "first_contact": "Hello", "closed": "Closed"}
# The text of a notification: what Teams shows on a lock screen. No resource name and no amount, like the subject of a letter (AGENTS.md rule 26 (c)).
SUMMARIES = {"change": "[Meternaut] A change to Azure waits for your OK", "advice": "[Meternaut] A decision waits for you", "result": "[Meternaut] A change to Azure has run",
             "first_contact": "[Meternaut] An AI assistant for Azure costs will write to you", "closed": "[Meternaut] A request was closed"}
ENDED = {"done": "Approved and done", "verified": "Approved and done", "unchanged": "Approved, nothing to change", "withdrawn": "Withdrawn"}
PAGE_BASE = re.compile(r"(?:https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?)(?:/(?!\.+(?:/|$))[A-Za-z0-9._~-]+)*")
OPAQUE = re.compile(r"[A-Za-z0-9_-]{1,64}")
# What a TextBlock reads as Markdown (the subset that Teams shows), a < that could open a mention or a tag, and the characters that start a list at the start of a text.
MARKDOWN = re.compile(r"([\\`*_\[\]()#<>])")
GENTLE = re.compile(r"([\\`*_\[\]#<>])")
LIST_DASH = re.compile(r"^[-+](?=\s)")
LIST_NUMBER = re.compile(r"^(\d+)\.(?=\s)")
TEXT_FEATURE = re.compile(r"\{(?=\{)")
WHY_APPROVER = "You got this because you are named as an approver of this request."
SHORT_CARD = "The details did not fit on this card. They are all on the page."


class CardError(Exception):
    """A card that cannot be made, or that does not pass the check. The text names the problems and never holds a token."""


class CardTooLarge(CardError):
    """A card that passes every check but its size: the caller puts minimal_card in its place."""


@dataclass(frozen=True)
class CardContext:
    """What a card needs besides the brief: the address of the page of its request (page_url makes it), why the person got it, who is responsible for Meternaut (as plain text with the address; the card
    names the first) and the addresses of its answer buttons by answer (`links`, from cardlinks.answer_url). Without buttons a card has the link to the page only."""

    page_url: str
    why: str = WHY_APPROVER
    contacts: tuple[str, ...] = ()
    links: Mapping[str, str] = field(default_factory=dict)


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
    """What is at stake, as a tile in the words of the pages (cases/stake.py): the figure a year in large type, its label and the month, its basis or why there is none, and, where a figure is shown, the
    one line that says what the money is in (AGENTS.md rule 13 (c) and 36). How long the request has waited and what waiting costs are on the page and not on the card: neither helps a person decide."""
    stake = stake_of(brief)
    label = f"{md(stake.label, 80)}. {md(stake.month, 40)} a month." if stake.month else f"{md(stake.label, 80)}."
    items = [_block("saving-word", label, weight="Bolder"), _block("price-basis", md(stake.note, 300), isSubtle=True)]
    items += [_block(name, md(text, 300), isSubtle=True) for name, text in (("made-of", stake.made_of), ("estimate", stake.estimate)) if text]
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


def _gateways(brief: Brief) -> list[dict]:
    """What a finding about point-to-site gateways says, in the room that a card has: what was found in one or two sentences, what was not counted when something was, and the choices in one
    line. The page has what these gateways are and the whole of each choice."""
    found = brief.gateways
    if found is None:
        return []
    blocks = [_block("gateways", f"**Gateways.** {md(found.sentence, 300)}")]
    if found.caveat:
        blocks.append(_block("gateways-caveat", md(found.caveat, 120), isSubtle=True))
    if brief.options:
        blocks.append(_block("options", md(GATEWAYS_SHORT, 200)))
    return blocks


def _check_first(brief: Brief) -> list[dict]:
    """What to check before acting on advice about a resource that others share, or that may not be used any more, in one line: the page has the three lines."""
    return [_block("check-first", md(CHECK_FIRST_SHORT, 160))] if brief.check_first else []


def _impact(brief: Brief) -> list[dict]:
    """What removing the resource would do, in one line: the verdict that code derived and its first reason, or that nothing was analysed. The page has the facts, what was not checked and how to undo it."""
    return [_block("impact", md(brief.impact.line, 320))] if brief.impact is not None else []


def _undo(brief: Brief) -> dict:
    """Whether it can be undone: one bold line when it cannot, and nothing decorative."""
    if not brief.undo.reversible:
        return _block("undo", "Undo: This cannot be undone.", weight="Bolder")
    return _block("undo", f"**Undo:** {md(brief.undo.how, 200)}")


def _decision_lines(brief: Brief) -> list[dict]:
    """What changes and with whose rights, whether it can be undone, what could go wrong and whose resource it is: one line each."""
    approving = brief.kind == "change"
    two = (brief.second.line if brief.second is not None else TWO_PEOPLE if brief.two_people else "") if approving else ""
    change = md(brief.change, 300) + (" It runs with your own permissions." if approving else "") + (f" {md(two, 320)}" if two else "")
    return [_block("change", f"**{'If you approve' if approving else 'If you answer'}:** {change}"), _undo(brief),
            _block("risk", f"**Risk, {md(brief.risk.level, 12)}:** {md(brief.risk.text, 240)}"), _block("owner", f"**Owner:** {md(brief.owner.text, 200)}")]


def _page_set(title: str, ctx: CardContext, *, positive: bool = False) -> dict:
    """A card with one action: the link to the page of the request (on the first card, to the web page)."""
    return {"type": "ActionSet", "id": "decisions", "actions": [{"type": "Action.OpenUrl", "id": "page", "title": title, "url": ctx.page_url, **({"style": "positive"} if positive else {})}]}


def _link_parts(brief: Brief, ctx: CardContext) -> list[dict]:
    """The link of a request that waits and that the card has no buttons for: "Review and decide" when this person has an answer to give, "See the request" when a switch holds the answers (and the card says so)."""
    approving = bool({"approve", "confirm"} & set(brief.answers))
    held = [_block("paused", PAUSED_ADVICE if brief.kind == "advice" else PAUSED_CHANGES, weight="Bolder")] if brief.held else []
    return [*held, _page_set("Review and decide" if approving else "See the request", ctx, positive=approving)]


def answers_of(brief: Brief) -> tuple[tuple[str, bool], ...]:
    """The answer buttons of this brief as (answer, whether the card asks twice first): "approve" (the first of two people: "confirm") and "decline", for a request that nothing holds and that this
    person may answer. A change that cannot be undone asks twice: its "approve" opens the question and the link is on the "Yes"."""
    if brief.kind not in ("change", "advice") or brief.state != "open" or brief.held:
        return ()
    first = "confirm" if "confirm" in brief.answers else "approve" if "approve" in brief.answers else ""
    if not first or "decline" not in brief.answers:
        return ()
    return ((first, first == "approve" and brief.kind == "change" and not brief.undo.reversible), ("decline", False))


def _open_url(id_: str, title: str, url: str, style: str = "") -> dict:
    return {"type": "Action.OpenUrl", "id": id_, "title": title, "url": url, **({"style": style} if style else {})}


def _toggle(id_: str, title: str, tooltip: str, targets: Sequence[tuple[str, bool]], style: str = "") -> dict:
    """A button that shows or hides parts of the card, which Teams does itself; each target says which, so that pressing twice cannot turn the wrong way. The tooltip is what a screen reader says."""
    return {"type": "Action.ToggleVisibility", "id": id_, "title": title, "tooltip": tooltip, **({"style": style} if style else {}),
            "targetElements": [{"elementId": element, "isVisible": shown} for element, shown in targets]}


def _sure(brief: Brief, yes_url: str) -> dict:
    """The question before a change that cannot be undone, hidden until "Approve" is pressed: what is lost and where, and two buttons, the safe "No, go back" first."""
    where = " ".join(bit for bit in (md(brief.where.kind, 40), md(brief.where.name, 120)) if bit) + (f" in resource group {md(brief.where.group, 90)}" if brief.where.group else "")
    return {"type": "Container", "id": "sure", "isVisible": False, "style": "attention", "items": [
        _block("sure-text", f"This cannot be undone: {where} is lost. {md(brief.undo.how, 200)}", weight="Bolder"),
        {"type": "ActionSet", "id": "sure-actions", "actions": [
            _toggle("sure-back", cardlinks.BACK_LABEL, "Hides this question. Nothing is changed.", [("sure", False)], "positive"),
            _open_url("sure-yes", cardlinks.sure_label(called_of(brief.family)), yes_url, "destructive")]}]}


def _answer_parts(brief: Brief, ctx: CardContext, answers: Sequence[tuple[str, bool]]) -> list[dict]:
    """The buttons of a request that waits, in the words of the page, then "Open the request"; for a change that cannot be undone also the question that "Approve" opens."""
    buttons, asks = [], ""
    for position, (answer, twice) in enumerate(answers):
        title, style = cardlinks.LABEL[brief.kind][answer], "positive" if position == 0 else ""
        if twice:
            asks = answer
            buttons.append(_toggle(answer, title, "Asks once more: this cannot be undone.", [("sure", True)], style))
        else:
            buttons.append(_open_url(answer, title, ctx.links[answer], style))
    buttons.append(_open_url("page", cardlinks.PAGE_LABEL, ctx.page_url))
    return [{"type": "ActionSet", "id": "decisions", "actions": buttons}, *([_sure(brief, ctx.links[asks])] if asks else [])]


def footer(models: Sequence[str], why: str, contacts: Sequence[str]) -> dict:
    """The one footer line: that an AI wrote this and which models, why the person got it and who is responsible for Meternaut (the first of the contacts, as the page names one person), as
    plain text."""
    line = footer_line([gentle(m, 60) for m in models], gentle(why, 200), [gentle(c, 160) for c in contacts[:1]])
    return _block("ai-footer", line, isSubtle=True, size="Small", separator=True)


def _check_context(ctx: CardContext, brief: Brief) -> None:
    if not isinstance(ctx, CardContext) or not cardlinks.PAGE_ADDRESS.fullmatch(ctx.page_url or ""):
        raise CardError("the card needs the address of the page of its request (page_url)")
    if not ctx.page_url.endswith(f"/ok/{brief.plan_id}") and brief.plan_id:
        raise CardError("the address of the page is not the page of this request")
    for answer, url in ctx.links.items():
        found = cardlinks.ANSWER_ADDRESS.fullmatch(url or "") if answer in cardlinks.VERBS else None
        if found is None or found["verb"] != answer or found["page"] != ctx.page_url:
            raise CardError("the address of a button is not the page of this request, the answer, its code and a link token")


def _finish(card: dict) -> dict:
    problems = cardcheck.check(card)
    if problems:
        size = cardcheck.size_of(card)
        text = "the card does not pass the check: " + "; ".join(problems[:5])
        raise (CardTooLarge if len(problems) == 1 and size is not None and size > cardcheck.MAX_BYTES else CardError)(text)
    return card


def _card(brief: Brief, ctx: CardContext, kind: str, body: list[dict], what: str) -> dict:
    title = title_text(brief)
    return _finish({
        "type": "AdaptiveCard", "$schema": cardcheck.SCHEMA, "version": cardcheck.VERSION, "msteams": {"width": "Full"},
        "fallbackText": f"{SENDER}: {md(title, 200)}. {what} Open it on the page: {ctx.page_url} Written by an AI.",
        "body": [_header(kind), _block("headline", md(title, 200), size="Large", weight="Bolder"), *body, footer(brief.models, ctx.why, ctx.contacts)],
    })


# -- the cards -----------------------------------------------------------------------------------------------------------------------------------

def decision_card(brief: Brief, ctx: CardContext) -> dict:
    """The card of a request that waits for an answer: a change that a person may approve (kind change) or advice (kind advice), with the answer buttons when the context has their links (answers_of), else the link to the page."""
    if brief.kind not in ("change", "advice") or brief.state != "open" or not brief.answers:
        raise CardError("only a request that is open and that this person may answer has a decision card")
    _check_context(ctx, brief)
    answers = answers_of(brief)
    buttons = _answer_parts(brief, ctx, answers) if answers and all(ctx.links.get(answer) for answer, _ in answers) else _link_parts(brief, ctx)
    body = [*_place(brief), _chips(brief), _stake(brief), _block("confidence", f"**How sure: {md(brief.confidence.level, 12)}.** {md(brief.confidence.because, 240)}"), *_learned(brief),
            *_facts(brief), *_unread(brief), *_gateways(brief), *_check_first(brief), *_impact(brief), *_decision_lines(brief), *buttons]
    return _card(brief, ctx, brief.kind, body, "A decision waits for you.")


def result_card(brief: Brief, ctx: CardContext) -> dict:
    """The card of a request that is not open any more, or that a change has run for: what became of it in plain lines, what it saves (the figure of the pages: Verified only when the cost
    lines after the change confirm it), whether it can be undone, and the page."""
    _check_context(ctx, brief)
    outcome = brief.outcome
    body: list[dict] = _place(brief)
    if outcome.state:
        body.append(_block("outcome", md(outcome.title, 80), weight="Bolder"))
        body += [_block(f"outcome-line-{n}", md(line, 300)) for n, line in enumerate(outcome.lines[:4], 1)]
    else:
        body.append(_block("outcome", "Nothing can be answered here now.", weight="Bolder"))
    if outcome.state in ("done", "verified"):
        body += [_stake(brief), _undo(brief)]
    body.append(_page_set("See the request", ctx))
    return _card(brief, ctx, "result", body, "What became of a request.")


def closed_card(brief: Brief, ctx: CardContext) -> dict:
    """The card that replaces one that cannot be answered any more: one line on what became of the request, in the words of its real end, and no button. An open request, or an approved change that
    is not over, has none."""
    _check_context(ctx, brief)
    outcome, moment = brief.outcome, parse_time(brief.outcome.at)
    if outcome.state in ("", "approved", "running"):
        raise CardError("only a request that has ended has a closing card")
    by = md(outcome.by, 80)
    if outcome.state == "expired":
        said = "Expired. Nothing more to do." if outcome.title == "Expired" else f"{md(outcome.title, 40)}. {md(outcome.lines[0], 200)} {md(outcome.lines[1], 80)}"
    elif outcome.state == "failed":
        said = f"Approved by {by}, not made: {md(outcome.lines[0], 200)}"
    else:
        said = f"Decided: {md(ENDED.get(outcome.state, outcome.title), 40)} by {by}" + (f", {moment.day} {moment:%b %H:%M} UTC" if moment else "") + ". Nothing more to do."
    return _card(brief, ctx, "closed", [_block("closed", said, weight="Bolder")], said)


def card_for(brief: Brief, ctx: CardContext) -> dict:
    """The card that shows a brief as it is now: the decision card while the request is open and this person may answer it, the card of what became of it otherwise."""
    if brief.kind in ("change", "advice") and brief.state == "open" and brief.answers:
        return decision_card(brief, ctx)
    return result_card(brief, ctx)


def minimal_card(brief: Brief, ctx: CardContext) -> dict:
    """The card for a message that cannot hold the whole card: the headline, one line that says that the details are on the page, the one link and the footer. It says nothing that the
    page does not say better, and it is made from the same brief, so it is still the card of that request and of that person."""
    _check_context(ctx, brief)
    waiting = brief.kind in ("change", "advice") and brief.state == "open" and bool(brief.answers)
    body = [_block("short", SHORT_CARD, weight="Bolder"), *(_link_parts(brief, ctx) if waiting else [_page_set("See the request", ctx)])]
    return _card(brief, ctx, brief.kind if waiting else "result", body, "A decision waits for you." if waiting else "What became of a request.")


def first_contact_card(name: object, base_url: str, contacts: Sequence[str] = (), why: str = "You got this because you are on my list of people.") -> dict:
    """What Meternaut says before its first card to a person, in three sentences, with the one link to the start page of the web page."""
    base = (base_url or "").strip().rstrip("/")
    if not PAGE_BASE.fullmatch(base):
        raise CardError("the address of the web page is not like https://host")
    return _finish({
        "type": "AdaptiveCard", "$schema": cardcheck.SCHEMA, "version": cardcheck.VERSION, "msteams": {"width": "Full"},
        "fallbackText": f"{SENDER}: an AI assistant for Azure costs will write to you. Open the web page: {base}/ Written by an AI.",
        "body": [_header("first_contact"), _block("headline", "An AI assistant for Azure costs will write to you", size="Large", weight="Bolder"),
                 _block("hello", f"Hello {md(name, 80)}, I am Meternaut, an AI that looks for Azure resources that cost money and are not used, and I write to you when a decision waits for you."),
                 _block("rules", "I change nothing myself. You answer a request with the buttons on its card: an answer button opens a page of mine that sends your answer, "
                                 "and a change to Azure runs with your own Azure rights."),
                 _block("settings", "You can pause or stop my messages under Settings on the web page."),
                 _page_set("Open the web page", CardContext(page_url=f"{base}/")),
                 footer((), why, contacts)],
    })
