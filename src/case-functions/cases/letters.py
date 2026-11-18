"""The letters: what Meternaut writes to a person, as pure functions of the data they are given.

A letter is a subject, an HTML body (what Graph's sendMail sends) and a plain-text copy of the same words (kept for the record and for the tests). Nothing here reads a
clock, a store or the network: the caller passes the records, the address of the web page and the time.

Every letter is a render of the decision brief (brief.py), cut to what a person needs and no more: a title and the place under it, the risk, how sure and what a change leaves behind as
words, what it is worth (the figure a year and a month with its level and its basis, in the words of the pages: cases/stake.py), a few facts, what changes, whether it can be undone,
what could go wrong, ONE button-link to the page where the person answers, and ONE footer line (that an AI wrote it, why the person got it, who is responsible for Meternaut). Nothing
else: no banner, no explanation of how Meternaut works, no repeated link.

What every letter keeps (AGENTS.md rule 13 (d), 26 (c) and 36):
- The subject starts with [Meternaut], says the point in plain words and holds no resource name and no amount of money.
- It carries no button that decides: a change is approved on a page. A link is the address of the web page plus a fixed path, and an opaque id where a plan needs one.
- Every value that came from a record or from Azure is cut down to one line and escaped. Names from Azure are data, never instructions.
- The HTML needs nothing from outside: inline CSS, no script, no image, no remote content. It has real headings, a lang attribute, text that meets the contrast of
  WCAG AA in a light and in a dark palette, and a link text that says where the link goes. The words that the code writes are ASCII in the plain text; a name that came from Azure is
  shown as Azure has it (a resource group may use other letters), after the hidden and direction characters are taken out.
- Plain, short, technical wording. No metaphor, no question, no urgency and no countdown. A saving is an estimate until cost lines confirm it.
- Money is said in the words of the pages and only once in US dollars. A letter never says that it has no figure: it says what is known and why the rest is not.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass
from typing import Collection, Sequence

from . import brief as brief_mod
from .brief import Brief, contact_text, plain
from .models import ActionRecord, CaseRecord, PlanRecord, started
from .people import Person
from .stake import LINE_CHARS, Stake, chips_of, decisions_of, place_of, stake_of, title_text, waited_line

SUBJECT_PREFIX = "[Meternaut]"
MAX_LISTED = 5
WEEKLY_LISTED = 10  # the lines of the weekly letter of the escalation contacts
MAX_HELD = 3  # the findings that are held back which the weekly letter lists: a short block, and the page has the rest
MAX_FACTS = 3

# Text and background pairs. The tests check the ratios that WCAG AA asks for (4.5 to 1) for every text colour on the colour it sits on. "save" is the green of the figure of a saving (the pages'
# green for money saved); it never stands alone: the label "Saves, Expected" is beside it.
LIGHT = {"background": "#ffffff", "text": "#1b1b1b", "muted": "#4a4a4a", "link": "#0b5cad", "head": "#eef2f7", "rule": "#c9ced6", "button": "#0b5cad", "button_text": "#ffffff", "save": "#0e700e"}
DARK = {"background": "#1e1e1e", "text": "#f2f2f2", "muted": "#c8c8c8", "link": "#9cc9ff", "head": "#2b2f36", "rule": "#6b7280", "button": "#9cc9ff", "button_text": "#0b1f33", "save": "#54b054"}

DONE_SUBJECTS = {"done": "A change to Azure has run", "verified": "A change to Azure has run", "failed": "A change to Azure did not run",
                 "unknown": "The result of a change to Azure is not known"}
UNCHANGED_SUBJECT = "Nothing had to change in Azure"
BASE = re.compile(r"(?:https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?|http://(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?)(?:/(?!\.+(?:/|$))[A-Za-z0-9._~-]+)*")
OPAQUE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass(frozen=True)
class Letter:
    subject: str
    html: str
    text: str


# ---- the values -----------------------------------------------------------------------------------------------------------------------------------

def _data(value: object, limit: int = 300) -> str:
    """A value from a record or from Azure as one plain line (brief.plain): no hidden or direction character, no line break, no link, at most `limit` characters."""
    return plain(value, limit)


def _base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not BASE.fullmatch(base):
        raise ValueError("the address of the function app is not like https://host")
    return base


def _plan_url(base: str, plan_id: str) -> str:
    if not OPAQUE_ID.fullmatch(plan_id or ""):
        raise ValueError("the id of a plan in a link is an opaque id of letters, digits, hyphens and underscores")
    return f"{base}/ok/{plan_id}"


def _roles(person: Person) -> str:
    return ", ".join(sorted(_data(role, 20) for role in person.roles)) or "none"


def _names(contacts: Sequence[str], person: Person | None = None) -> tuple[str, ...]:
    """The one person who is responsible for Meternaut, as plain text: the first of the contacts who is not the person who reads the letter (the first of all when nobody else is listed)."""
    cleaned = [c for c in (_data(c, 150) for c in contacts) if c]
    own = contact_text(person.name, person.mail) if person is not None else ""
    return tuple(([c for c in cleaned if c != own] or cleaned)[:1])


# ---- the document ---------------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Heading:
    text: str


@dataclass(frozen=True)
class _Paragraph:
    text: str
    muted: bool = False
    strong: bool = False


@dataclass(frozen=True)
class _Figure:
    """The figure of a request: a large line (the figure a year, empty when there is none), the line under it (its label, the month, its basis or its reason) and, where money is shown, the
    one line that says what the money is in. `saving` colours the large line green: the label beside it says what it is."""

    year: str
    sub: str
    money: str
    saving: bool


@dataclass(frozen=True)
class _Facts:
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _Items:
    items: tuple[str, ...]


@dataclass(frozen=True)
class _Button:
    text: str
    url: str


class _Doc:
    """The blocks of one letter. The words are plain text here: the HTML and the text of the letter are both made from them, and every value is
    escaped when the HTML is written."""

    def __init__(self, point: str) -> None:
        self.subject = f"{SUBJECT_PREFIX} {point}"
        self.blocks: list[object] = [_Heading(point)]

    def heading(self, text: str) -> None:
        self.blocks[0] = _Heading(text)

    def paragraph(self, text: str, muted: bool = False, strong: bool = False) -> None:
        self.blocks.append(_Paragraph(text, muted, strong))

    def figure(self, stake: Stake, then: str = "") -> None:
        """The figure in the words of the pages, and `then` (what happens next to it) at the end of the line under it. What the cost of a whole subscription is made of, and the estimate at list
        price for a disk that Azure has no cost line for (which says that it is an estimate, and the date of its price table), stand in the same line, after the figure's own words."""
        self.blocks.append(_Figure(stake.year, " ".join(part for part in (_data(stake.line, LINE_CHARS), _data(stake.extra, 400), then) if part), stake.money, stake.state == "save"))

    def facts(self, *rows: tuple[str, str]) -> None:
        if rows:
            self.blocks.append(_Facts(tuple(rows)))

    def items(self, *items: str) -> None:
        self.blocks.append(_Items(tuple(items)))

    def button(self, text: str, url: str) -> None:
        self.blocks.append(_Button(text, url))

    def footer(self, models: Sequence[str], why: str, contacts: Sequence[str], person: Person | None = None) -> None:
        self.paragraph(brief_mod.footer_line(models, why, _names(contacts, person)), muted=True)

    def build(self) -> Letter:
        return Letter(self.subject, _page(self.subject, self.blocks), _plain(self.blocks))


def _plain(blocks: list[object]) -> str:
    lines: list[str] = []
    for block in blocks:
        if isinstance(block, _Heading):
            lines += [block.text, "=" * min(len(block.text), 72), ""]
        elif isinstance(block, _Paragraph):
            lines += [block.text, ""]
        elif isinstance(block, _Figure):
            lines += [line for line in (block.year, block.sub, block.money) if line] + [""]
        elif isinstance(block, _Facts):
            lines += [f"{label}: {value}" for label, value in block.rows] + [""]
        elif isinstance(block, _Items):
            lines += [f"- {item}" for item in block.items] + [""]
        elif isinstance(block, _Button):
            lines += [f"{block.text}: {block.url}", ""]
    return "\n".join(lines).rstrip() + "\n"


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _block_html(block: object) -> str:
    light = LIGHT
    if isinstance(block, _Heading):
        return (f'<h1 class="mn-fg" style="margin:0 0 12px 0;font-size:20px;line-height:1.3;font-weight:700;color:{light["text"]};">{_e(block.text)}</h1>')
    if isinstance(block, _Paragraph):
        name, color = ("mn-muted", light["muted"]) if block.muted else ("mn-fg", light["text"])
        size = "14px" if block.muted else "16px"
        weight = "font-weight:600;" if block.strong else ""
        return f'<p class="{name}" style="margin:0 0 12px 0;font-size:{size};{weight}color:{color};">{_e(block.text)}</p>'
    if isinstance(block, _Figure):
        name, color = ("mn-save", light["save"]) if block.saving else ("mn-fg", light["text"])
        big = (f'<p class="{name}" style="margin:0;font-size:32px;line-height:1.25;font-weight:700;color:{color};">{_e(block.year)}</p>' if block.year else "")
        sub = f'<p class="mn-fg" style="margin:0 0 {4 if block.money else 12}px 0;color:{light["text"]};">{_e(block.sub)}</p>'
        money = f'<p class="mn-muted" style="margin:0 0 12px 0;font-size:14px;color:{light["muted"]};">{_e(block.money)}</p>' if block.money else ""
        return big + sub + money
    if isinstance(block, _Facts):
        border = f'1px solid {light["rule"]}'
        rows = "".join(
            f'<tr><th scope="row" align="left" valign="top" class="mn-head mn-fg mn-rule" style="width:34%;padding:6px 8px;border:{border};'
            f'background-color:{light["head"]};color:{light["text"]};font-weight:600;">{_e(label)}</th>'
            f'<td valign="top" class="mn-fg mn-rule" style="padding:6px 8px;border:{border};color:{light["text"]};">{_e(value)}</td></tr>'
            for label, value in block.rows)
        return f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 12px 0;">{rows}</table>'
    if isinstance(block, _Items):
        items = "".join(f'<li class="mn-fg" style="margin:0 0 6px 0;color:{light["text"]};">{_e(item)}</li>' for item in block.items)
        return f'<ul style="margin:0 0 12px 0;padding-left:22px;">{items}</ul>'
    if isinstance(block, _Button):
        return (f'<p style="margin:4px 0 16px 0;"><a class="mn-button" href="{_e(block.url)}" style="display:inline-block;padding:10px 22px;'
                f'background-color:{light["button"]};color:{light["button_text"]};border-radius:4px;font-weight:700;text-decoration:none;">{_e(block.text)}</a></p>')
    raise TypeError("unknown block")


def _page(subject: str, blocks: list[object]) -> str:
    light, dark = LIGHT, DARK
    body = "\n".join(_block_html(block) for block in blocks)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n<meta name="supported-color-schemes" content="light dark">\n'
        f"<title>{_e(subject)}</title>\n"
        "<style>\n:root { color-scheme: light dark; }\n@media (prefers-color-scheme: dark) {\n"
        f"  .mn-bg {{ background-color: {dark['background']} !important; }}\n"
        f"  .mn-fg {{ color: {dark['text']} !important; }}\n"
        f"  .mn-muted {{ color: {dark['muted']} !important; }}\n"
        f"  .mn-save {{ color: {dark['save']} !important; }}\n"
        f"  .mn-link {{ color: {dark['link']} !important; }}\n"
        f"  .mn-head {{ background-color: {dark['head']} !important; }}\n"
        f"  .mn-rule {{ border-color: {dark['rule']} !important; }}\n"
        f"  .mn-button {{ background-color: {dark['button']} !important; color: {dark['button_text']} !important; }}\n"
        "}\n</style>\n</head>\n"
        f'<body class="mn-bg mn-fg" style="margin:0;padding:0;background-color:{light["background"]};color:{light["text"]};'
        'font-family:Segoe UI,Arial,sans-serif;font-size:16px;line-height:1.5;">\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="mn-bg" style="background-color:{light["background"]};">\n'
        '<tr><td align="center" style="padding:16px;">\n'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;">\n'
        f'<tr><td align="left" class="mn-fg" style="color:{light["text"]};">\n{body}\n</td></tr>\n'
        "</table>\n</td></tr>\n</table>\n</body>\n</html>\n"
    )


# ---- what the letters say -------------------------------------------------------------------------------------------------------------------------

def _fact_rows(brief: Brief) -> tuple[tuple[str, str], ...]:
    return tuple((_data(f.label, 60), _data(f.value, 120)) for f in brief.facts[:MAX_FACTS])


def _decision_rows(brief: Brief) -> tuple[tuple[str, str], ...]:
    """Whose resource it is, what changes (who does it, with whose rights), whether it can be undone and what could go wrong: one line each. A change that needs two people says so in the
    same line, in words that stay true whatever has happened since the letter was written."""
    acts = " It runs with your own permissions." if brief.kind == "change" else ""
    two = f" {brief_mod.TWO_PEOPLE}" if brief.kind == "change" and brief.two_people else ""
    return (("Owner", _data(brief.owner.text, 160)),
            ("If you approve" if brief.kind == "change" else "If you answer", _data(brief.change, 200) + acts + two),
            ("Undo", "This cannot be undone." if not brief.undo.reversible else _data(brief.undo.how, 160)),
            (f"Risk, {brief.risk.level}", _data(brief.risk.text, 200)))


def first_contact_letter(person: Person, base_url: str, now: dt.datetime, contacts: Sequence[str] = (), plan_id: str | None = None) -> Letter:
    """The first letter to a person, in three sentences: who writes and what for, what I do and do not do, and where to pause or stop the letters. Its one link is the page
    of the first request that waits for the person (the start page when it is not sent for one)."""
    base = _base(base_url)
    doc = _Doc("An AI assistant for Azure costs will write to you")
    doc.paragraph(f"Hello {_data(person.name, 80)}, I am Meternaut, an AI that looks for Azure resources that cost money and are not used, and I write to you when a "
                  "decision waits for you.")
    doc.paragraph("I change nothing myself: you decide on a web page, and a change runs with your own Azure rights.")
    doc.paragraph("You can pause or stop my letters under Settings on that page.")
    doc.button("See the first decision" if plan_id else "Open the web page", _plan_url(base, plan_id) if plan_id else f"{base}/")
    doc.footer((), f"You got this because you are on my list of people, with the roles: {_roles(person)}.", contacts, person)
    return doc.build()


def _place(doc: "_Doc", brief: Brief) -> None:
    """The line under the title: the kind of resource and its resource group (a request for many resources has none: its title counts them)."""
    place = place_of(brief)
    if place:
        doc.paragraph(_data(place, 160), muted=True)


def _heads_up(brief: Brief) -> str:
    """The warning about a resource that something that runs by itself changes, as the one line that every letter says it in ("" for a request that has none)."""
    return f"{brief_mod.HEADS_UP}: {_data(brief.heads_up, 320)}" if brief.heads_up else ""


def approval_letter(plan: PlanRecord, case: CaseRecord | None, person: Person, base_url: str, now: dt.datetime, contacts: Sequence[str] = ()) -> Letter:
    """One request that waits for an answer: the title and the place, the risk, how sure and whether it can be undone as words (a letter has no shapes: the words carry it), what it is
    worth (the figure a year and a month with its level and its basis, and once that money is in US dollars), three facts, what changes, what could go wrong, and one link to the page where
    the person decides. Opening the link records no decision."""
    base = _base(base_url)
    url = _plan_url(base, plan.plan_id)
    brief = brief_mod.build_brief(case, plan, None, (), now=now)
    about_group = brief.group is not None and brief.kind == "advice"  # a finding about many resources: its rows say how many, what they cost together and which, and the letter keeps to them
    doc = _Doc("A change to Azure waits for your OK" if brief.kind == "change" else "A decision waits for you")
    doc.heading(_data(title_text(brief), 200))
    if brief.state != "open":
        closed = (brief.outcome.title or brief.state).lower()
        doc.paragraph(f"This request is closed: {closed}. Nothing can be answered now.")
    _place(doc, brief)
    doc.paragraph(", ".join(chips_of(brief)), strong=True)
    doc.figure(stake_of(brief))
    if brief.heads_up:
        doc.paragraph(_heads_up(brief))
    for line in (brief.past, brief.access):
        if line:
            doc.paragraph(_data(line, 240))
    if about_group:
        rows = _fact_rows(brief)
        doc.facts(*(rows[:2] if brief.group.capped else rows))  # a group that the limit of a run cut says so in its first row, and then a letter has no room for the examples as well
        said = _decision_rows(brief)
        doc.facts(*said[:2], said[3])  # whose it is, that the answer changes nothing in Azure, and the risk of acting on it: a letter for many resources has no room for more
    else:
        doc.facts(*_fact_rows(brief))
        doc.facts(*_decision_rows(brief))
    if brief.advisor is not None and brief.options:
        doc.paragraph(_data(brief_mod.ADVISOR_SHORT, 200))  # the order of work for a commitment, in a line: the page has the whole of each step
    if brief.check_first:
        doc.paragraph(brief_mod.CHECK_FIRST_SHORT)
    if brief.impact is not None:
        doc.paragraph(_data(brief.impact.line, 340))
    doc.button("Review and decide" if brief.state == "open" else "See the request", url)
    approver = person.oid.lower() in {a.lower() for a in plan.approvers}
    doc.footer(brief.models, "You got this because you are named as an approver of this request." if approver
               else "You got this because you are on my list of people who receive letters.", contacts, person)
    return doc.build()


def done_letter(plan: PlanRecord, action: ActionRecord, case: CaseRecord | None, person: Person, base_url: str, now: dt.datetime, contacts: Sequence[str] = ()) -> Letter:
    """What happened to the change of one plan: what was done and what came of it (what it saves, in the words of the pages: Verified only when the cost lines after the change confirm it),
    whether it can be undone, and one link to the page that shows the result."""
    base = _base(base_url)
    url = _plan_url(base, plan.plan_id)
    brief = brief_mod.build_brief(case, plan, action, (), now=now)
    title = _data(title_text(brief), 200)
    unchanged = brief.outcome.state == "unchanged"
    ran = action.state in ("done", "verified") and not unchanged
    doc = _Doc(UNCHANGED_SUBJECT if unchanged else DONE_SUBJECTS.get(action.state, "The state of a change to Azure"))
    if unchanged:
        # Approved, and nothing had to be changed: no line says that it ran, was made with anyone's rights or can be undone, and no saving is claimed.
        doc.paragraph(f"You approved: {title}.")
        doc.paragraph(_data(brief.outcome.lines[-1], 300))
        doc.paragraph("No saving is claimed for this approval.")
    elif ran:
        doc.paragraph(f"Done: {title}.")
        _place(doc, brief)
        said = [_data(line, 240) for line in (action.result, *brief_mod.check_lines(action.verification if isinstance(action.verification, dict) else {}, action.result or "")) if line]
        doc.facts(*([("Result", " ".join(said[:3]))] if said else []))
        stake = stake_of(brief)
        doc.figure(stake, then="Cost lines confirm it after a few days." if stake.state == "save" and stake.level != "Verified" else "")
        doc.paragraph("This cannot be undone." if not brief.undo.reversible else _data(brief.undo.how, 200))
    else:
        was = {"failed": "was tried and did not complete", "unknown": "was started, and its result is not known"}.get(action.state, "is in progress")
        doc.paragraph(f"The change {was}: {title}.")
        detail = _data(action.error or action.result, 240)
        doc.facts(*([("What happened", detail)] if detail else []))
        doc.paragraph("Look at the resource in Azure before anything else is done with it.")
    doc.button("See what happened", url)
    approver = person.oid.lower() in {a.lower() for a in plan.approvers}
    doc.footer(brief.models, "You got this because you are named as an approver of this request." if approver
               else "You got this because you are on my list of people who receive letters.", contacts, person)
    return doc.build()


def _waits(plan: PlanRecord, now: dt.datetime) -> bool:
    """A plan waits for an answer while it is open: no clock ends it (AGENTS.md rule 38)."""
    return plan.state == "open"


def digest_letter(person: Person, base_url: str, now: dt.datetime, waiting: Sequence[tuple[PlanRecord, CaseRecord | None]], contacts: Sequence[str] = (), later: Collection[str] = (),
                  held: Sequence[tuple[PlanRecord, CaseRecord | None]] = ()) -> Letter | None:
    """The decisions that wait for a person, counted and ranked as the Decisions page does it (the page's own code groups them, so that findings of one kind about several resources are one
    line here as they are one row there, "4 storage accounts in 3 resource groups", and the number in the subject is the number that the page shows; `later` holds the plans that the person
    put off, which the page ranks last). At most five lines, one for each decision, with its title and its figure a year with its level ("$1,682 a year, Expected") and no total: a total is
    the page's. One link: to the page of the request when only one request waits, else to the page that lists them. None when nothing waits: nothing is sent then.

    `held` holds the requests of the findings that a guard holds back that this person is named for (cases/approvals.py Approvals.settle): one short block after the decisions, with at most
    MAX_HELD lines (the title, the figure a year with its level, the guard's sentence and what it still needs) and the count of the rest. It asks for nothing: no button, no link of its own. A
    person with only such findings gets a letter that says so in its subject, and its link is the page that lists them."""
    base = _base(base_url)
    rows = decisions_of([(brief_mod.build_brief(case, plan, None, (), now=now), case, plan.plan_id in later) for plan, case in waiting if _waits(plan, now)])
    kept = [(plan, case) for plan, case in held if brief_mod.held_of(plan)]
    if not rows and not kept:
        return None
    count = len(rows)
    doc = _Doc(f"{count} decision{' waits' if count == 1 else 's wait'} for you" if rows else f"{len(kept)} finding{' is' if len(kept) == 1 else 's are'} held back from a request")
    if rows:
        doc.items(*(f"{_data(row.title, 200)}: {row.stake.short}." + (" No AI looked at it." if row.brief is not None and row.brief.by_code else "")
                    + (f" {_heads_up(row.brief)}" if row.brief is not None and row.brief.heads_up else "") for row in rows[:MAX_LISTED]))
    if count > MAX_LISTED:
        doc.paragraph(f"{count - MAX_LISTED} more wait on the page.")
    if kept:
        found = sorted((brief_mod.build_brief(case, plan, None, (), now=now) for plan, case in kept), key=lambda b: (-(stake_of(b).monthly or 0.0), title_text(b), b.plan_id))  # what is at stake first
        doc.paragraph("Found, and held back from a request. Nothing is asked of you to approve, and nothing changes in Azure.", strong=True)
        doc.items(*(f"{_data(title_text(b), 200)}: {stake_of(b).short}. {_data(b.hold.why, 240)} {_data(b.hold.needs, 240)}" for b in found[:MAX_HELD] if b.hold is not None))
        if len(found) > MAX_HELD:
            doc.paragraph(f"{len(found) - MAX_HELD} more are held back. They are on the page.")
    only = rows[0].brief if count == 1 else None
    if only is not None:
        doc.button("Review and decide", _plan_url(base, only.plan_id))
    else:
        doc.button("Open the decisions" if rows else "See the held findings", f"{base}/")
    doc.footer((), f"You got this because you are on my list of people, with the roles: {_roles(person)}.", contacts, person)
    return doc.build()


# ---- the escalation of a request that waits (cases/escalation.py) ----------------------------------------------------------------------------------

ESCALATION_WHY = {
    "same": "This is a reminder. You are named as an approver of this request, and nobody has answered it.",
    "manager": "You are told because you are the manager of {who}, who was asked first and has not answered.",
    "tag": "You are told because your address is in the escalation tag of this resource, of its resource group or of its subscription.",
    "contact": "You are told because you are an escalation contact: when nobody answers a request, it comes to you.",
    "owners": "You are told because no manager and no escalation contact could be found, so a request that nobody answers comes to the owners of Meternaut.",
}
# The same reasons in a few words, for a line of a letter that lists several requests.
ESCALATION_WHY_SHORT = {
    "same": "It is a reminder: you are named as an approver.",
    "manager": "You are told because you are the manager of the person who was asked.",
    "tag": "You are told because your address is in the escalation tag.",
    "contact": "You are told because you are an escalation contact.",
    "owners": "You are told because no manager or escalation contact could be found.",
}
ESCALATION_INTRO = ("I am Meternaut, an AI that looks for Azure resources that cost money and are not used. I write to a person when a decision about one has waited and nobody has answered it. "
                    "I change nothing myself: a person decides on a web page.")
ESCALATION_ADDED = "You were added to the people who answer this request after it was made."
ESCALATION_ADDED_SOME = "You were added to the people who answer some of these requests after they were made."
ESCALATION_CAN = "You can answer on the page: it is worth acting on, it is not worth it, you have a question, it is not yours (then I pass it on), or you decide later (at most three times)."
ESCALATION_CAN_NOT = "The page opens only for the people on my list, and you are not on it yet. Tell one of the people below what you decide, or ask them to add you."


def waited_days(plan: PlanRecord, now: dt.datetime, own: bool = False) -> int:
    """How many whole days the request has waited since the wait began (a request that stands for others keeps their start), or, with `own`, since this request was made."""
    since = brief_mod.parse_time(plan.created_at if own else started(plan))
    moment = now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)
    return 0 if since is None else max(0, (moment - since).days)


def _days(days: int) -> str:
    return f"{days} day{'s' if days != 1 else ''}"


def escalation_letter(plan: PlanRecord, case: CaseRecord | None, person: Person, base_url: str, now: dt.datetime, contacts: Sequence[str] = (), *, source: str, asked: str = "",
                      notes: Sequence[str] = (), told: Sequence[str] = (), pending: Sequence[str] = (), first: bool = False, put_off: int = 0, added: bool = False) -> Letter:
    """One request that has waited without an answer, to the person that the ladder has come to: why this person is told (and, to a person who never heard of Meternaut, who writes), the
    request as its page has it (title, place, figure with its level), how long it has waited, what waiting has cost so far, who was told before and when, and what the person can do. Names
    come from a directory and are cut and escaped. A saving that nobody measured says so, and no cost of waiting is worked out for it."""
    base = _base(base_url)
    brief = brief_mod.build_brief(case, plan, None, (), now=now)
    days = waited_days(plan, now)
    stake = stake_of(brief)
    doc = _Doc(f"A decision has waited {_days(days)}")
    doc.heading(_data(title_text(brief), 200))
    if first:
        doc.paragraph(ESCALATION_INTRO)
    doc.paragraph(ESCALATION_WHY.get(source, ESCALATION_WHY["owners"]).format(who=_data(asked, 120) or "the person who was asked first"))
    if added:
        doc.paragraph(ESCALATION_ADDED)
    for note in notes:
        doc.paragraph(_data(note, 200), muted=True)
    _place(doc, brief)
    doc.paragraph(", ".join(chips_of(brief)), strong=True)
    doc.figure(stake)
    if brief.heads_up:
        doc.paragraph(_heads_up(brief))
    waited = waited_line(stake, days, plan.waited_usd, waited_days(plan, now, True))
    rows = [("Waiting", f"{_days(days)}, since {_data(started(plan)[:10], 12)}"),
            ("What waiting has cost", waited or "No saving has been measured, so what waiting costs is not worked out."),
            ("Told before", "; ".join(_data(t, 160) for t in told[:4]) or "Nobody else yet.")]
    if pending:
        rows.append(("Not told yet", "; ".join(_data(t, 160) for t in pending[:4])))
    if put_off:
        rows.append(("Put off", f"{put_off} time{'s' if put_off != 1 else ''} by the people who were asked."))
    doc.facts(*rows)
    listed = bool(person.roles)  # a person from the directory who is not on the list cannot open the page
    doc.paragraph(ESCALATION_CAN if listed else ESCALATION_CAN_NOT)
    if listed:
        doc.button("Review and decide", _plan_url(base, plan.plan_id))
    doc.footer(brief.models, "You got this because a request has waited without an answer and I tell the next person.", contacts, person)
    return doc.build()


def escalation_digest_letter(person: Person, base_url: str, now: dt.datetime, rows: Sequence[tuple[PlanRecord, CaseRecord | None, str]], contacts: Sequence[str] = (), *, first: bool = False,
                             added: bool = False) -> Letter:
    """One letter for the several requests that the ladder has come to for the same person on the same day: nobody gets more than one a day. Each line has the title, the figure with its level,
    how long it has waited and why the person is told; one link to the page that lists them."""
    base = _base(base_url)
    count = len(rows)
    doc = _Doc(f"{count} decisions have waited without an answer")
    if first:
        doc.paragraph(ESCALATION_INTRO)
    if added:
        doc.paragraph(ESCALATION_ADDED_SOME)
    lines = []
    for plan, case, source in rows[:MAX_LISTED]:
        brief = brief_mod.build_brief(case, plan, None, (), now=now)
        stake, days = stake_of(brief), waited_days(plan, now)
        lines.append(" ".join(part for part in (f"{_data(title_text(brief), 200)}: {stake.short}.", f"Waiting {_days(days)}.", waited_line(stake, days, plan.waited_usd, waited_days(plan, now, True)),
                                                 ESCALATION_WHY_SHORT.get(source, ESCALATION_WHY_SHORT["owners"]), _heads_up(brief)) if part))
    doc.items(*lines)
    if count > MAX_LISTED:
        doc.paragraph(f"and {count - MAX_LISTED} more.")
    listed = bool(person.roles)
    doc.paragraph(ESCALATION_CAN if listed else ESCALATION_CAN_NOT)
    if listed:
        doc.button("Open the decisions", f"{base}/")
    doc.footer((), "You got this because requests have waited without an answer and I tell the next person.", contacts, person)
    return doc.build()


def escalation_weekly_letter(person: Person, base_url: str, now: dt.datetime, rows: Sequence[tuple[PlanRecord, CaseRecord | None]], contacts: Sequence[str] = (),
                             problems: Sequence[str] = (), *, first: bool = False) -> Letter:
    """The weekly letter to an escalation contact: every request that waits, oldest first and ten at most, each with its own figure and how long it has waited (no total: a total is no part of a case),
    and what stops Meternaut from finding people (a missing permission, a message that could not be delivered), once each."""
    base = _base(base_url)
    count = len(rows)
    doc = _Doc(f"{count} decision{' waits' if count == 1 else 's wait'} for an answer" if count else "What stops Meternaut from escalating")
    if first:
        doc.paragraph(ESCALATION_INTRO)
    lines = []
    for plan, case in rows[:WEEKLY_LISTED]:
        brief = brief_mod.build_brief(case, plan, None, (), now=now)
        stake, days = stake_of(brief), waited_days(plan, now)
        lines.append(" ".join(part for part in (f"{_data(title_text(brief), 200)}: {stake.short}.", f"Waiting {_days(days)}.", waited_line(stake, days, plan.waited_usd, waited_days(plan, now, True)),
                                                 _heads_up(brief)) if part))
    if lines:
        doc.items(*lines)
    if count > WEEKLY_LISTED:
        doc.paragraph(f"and {count - WEEKLY_LISTED} more.")
    for problem in problems:
        doc.paragraph(_data(problem, 300))
    doc.button("Open the decisions", f"{base}/")
    doc.footer((), f"You got this because you are an escalation contact or an owner of Meternaut, with the roles: {_roles(person)}.", contacts, person)
    return doc.build()
