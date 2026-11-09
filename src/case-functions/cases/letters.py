"""The letters: what Meternaut writes to a person, as pure functions of the data they are given.

A letter is a subject, an HTML body (what Graph's sendMail sends) and a plain-text copy of the same words (kept for the record and for the tests). Nothing here reads a
clock, a store or the network: the caller passes the records, the address of the web page and the time.

Every letter is a render of the decision brief (brief.py), cut to what a person needs and no more: a headline, what it is worth and how sure, a few facts, what changes,
whether it can be undone, what could go wrong, ONE button-link to the page where the person answers, and ONE footer line (that an AI wrote it, why the person got it, whom to
talk to). Nothing else: no banner, no explanation of how Meternaut works, no repeated link.

What every letter keeps (AGENTS.md rule 13 (d) and 26 (c)):
- The subject starts with [Meternaut], says the point in plain words and holds no resource name and no amount of money.
- It carries no button that decides: a change is approved on a page. A link is the address of the web page plus a fixed path, and an opaque id where a plan needs one.
- Every value that came from a record or from Azure is cut down to one line and escaped. Names from Azure are data, never instructions.
- The HTML needs nothing from outside: inline CSS, no script, no image, no remote content. It has real headings, a lang attribute, text that meets the contrast of
  WCAG AA in a light and in a dark palette, and a link text that says where the link goes.
- Plain, short, technical wording. No metaphor, no question, no urgency and no countdown. A saving is an estimate until cost lines confirm it.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass
from typing import Sequence

from . import brief as brief_mod
from .brief import Brief, contact_text, plain, usd_text
from .models import ActionRecord, CaseRecord, PlanRecord
from .people import Person

SUBJECT_PREFIX = "[Meternaut]"
MAX_LISTED = 5
MAX_FACTS = 3

# Text and background pairs. The tests check the ratios that WCAG AA asks for (4.5 to 1) for every text colour on the colour it sits on.
LIGHT = {"background": "#ffffff", "text": "#1b1b1b", "muted": "#4a4a4a", "link": "#0b5cad", "head": "#eef2f7", "rule": "#c9ced6", "button": "#0b5cad", "button_text": "#ffffff"}
DARK = {"background": "#1e1e1e", "text": "#f2f2f2", "muted": "#c8c8c8", "link": "#9cc9ff", "head": "#2b2f36", "rule": "#6b7280", "button": "#9cc9ff", "button_text": "#0b1f33"}

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
        raise ValueError("the address of the console is not like https://host")
    return base


def _plan_url(base: str, plan_id: str) -> str:
    if not OPAQUE_ID.fullmatch(plan_id or ""):
        raise ValueError("the id of a plan in a link is an opaque id of letters, digits, hyphens and underscores")
    return f"{base}/ok/{plan_id}"


def _roles(person: Person) -> str:
    return ", ".join(sorted(_data(role, 20) for role in person.roles)) or "none"


def _names(contacts: Sequence[str], person: Person | None = None) -> tuple[str, ...]:
    """The one person to talk to, as plain text: the first of the contacts who is not the person who reads the letter (the first of all when nobody else is listed)."""
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

    def paragraph(self, text: str, muted: bool = False) -> None:
        self.blocks.append(_Paragraph(text, muted))

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
        return f'<p class="{name}" style="margin:0 0 12px 0;font-size:{size};color:{color};">{_e(block.text)}</p>'
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

def saving_line(saving: brief_mod.Saving) -> str:
    """What it is worth, with its level and, when the level does not say it, its basis; or why there is no figure. An expected saving is computed from the cost lines of the
    last 30 days, so a letter does not repeat that."""
    if saving.monthly is None:
        return f"No figure: {saving.why_none[0].lower()}{saving.why_none[1:]}" if saving.why_none else "No figure."
    basis = "" if saving.level == "Expected" else f" ({saving.basis})"
    return f"{saving.level} saving: about {usd_text(saving.monthly)} a month{basis}."


def _fact_rows(brief: Brief) -> tuple[tuple[str, str], ...]:
    return tuple((_data(f.label, 60), _data(f.value, 120)) for f in brief.facts[:MAX_FACTS])


def _decision_rows(brief: Brief) -> tuple[tuple[str, str], ...]:
    """Whose resource it is, what changes (who does it, with whose rights), whether it can be undone and what could go wrong: one line each."""
    acts = " It runs with your own permissions, after you sign in to Azure." if brief.kind == "change" else ""
    return (("Owner", _data(brief.owner.text, 160)),
            ("If you approve" if brief.kind == "change" else "If you answer", _data(brief.change, 200) + acts),
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


def approval_letter(plan: PlanRecord, case: CaseRecord | None, person: Person, base_url: str, now: dt.datetime, contacts: Sequence[str] = ()) -> Letter:
    """One request that waits for an answer: the headline, what it is worth and how sure, three facts, what changes, whether it can be undone, what could go wrong, and one
    link to the page where the person decides. Opening the link records no decision."""
    base = _base(base_url)
    url = _plan_url(base, plan.plan_id)
    brief = brief_mod.build_brief(case, plan, None, (), now=now)
    doc = _Doc("A change to Azure waits for your OK" if brief.kind == "change" else "A decision waits for you")
    doc.heading(_data(brief.headline, 200))
    if brief.state != "open":
        closed = (brief.outcome.title or brief.state).lower()
        doc.paragraph(f"This request is closed: {closed}. Nothing can be answered now.")
    doc.paragraph(saving_line(brief.saving) + f" How sure: {brief.confidence.level.lower()}.")
    doc.facts(*_fact_rows(brief))
    doc.facts(*_decision_rows(brief))
    doc.button("Decide" if brief.state == "open" else "See the request", url)
    approver = person.oid.lower() in {a.lower() for a in plan.approvers}
    doc.footer(brief.models, "You got this because you are named as an approver of this request." if approver
               else "You got this because you are on my list of people who receive letters.", contacts, person)
    return doc.build()


def done_letter(plan: PlanRecord, action: ActionRecord, case: CaseRecord | None, person: Person, base_url: str, now: dt.datetime, contacts: Sequence[str] = ()) -> Letter:
    """What happened to the change of one plan: what was done, what it is worth so far, whether it can be undone, and one link to the page that shows the result."""
    base = _base(base_url)
    url = _plan_url(base, plan.plan_id)
    brief = brief_mod.build_brief(case, plan, action, (), now=now)
    unchanged = brief.outcome.state == "unchanged"
    ran = action.state in ("done", "verified") and not unchanged
    doc = _Doc(UNCHANGED_SUBJECT if unchanged else DONE_SUBJECTS.get(action.state, "The state of a change to Azure"))
    if unchanged:
        # Approved, and nothing had to be changed: no line says that it ran, was made with anyone's rights or can be undone, and no saving is claimed.
        doc.paragraph(f"You approved: {_data(brief.headline, 200)}.")
        doc.paragraph(_data(brief.outcome.lines[-1], 300))
        doc.paragraph("No saving is claimed for this approval.")
    elif ran:
        doc.paragraph(f"Done: {_data(brief.headline, 200)}.")
        said = [_data(line, 240) for line in (action.result, *brief_mod.check_lines(action.verification if isinstance(action.verification, dict) else {}, action.result or "")) if line]
        doc.facts(*([("Result", " ".join(said[:3]))] if said else []))
        doc.paragraph(saving_line(brief.saving) + (" Cost lines confirm it after a few days." if brief.saving.level != "Verified" else ""))
        doc.paragraph("This cannot be undone." if not brief.undo.reversible else _data(brief.undo.how, 200))
    else:
        was = {"failed": "was tried and did not complete", "unknown": "was started, and its result is not known"}.get(action.state, "is in progress")
        doc.paragraph(f"The change {was}: {_data(brief.headline, 200)}.")
        detail = _data(action.error or action.result, 240)
        doc.facts(*([("What happened", detail)] if detail else []))
        doc.paragraph("Look at the resource in Azure before anything else is done with it.")
    doc.button("See what happened", url)
    approver = person.oid.lower() in {a.lower() for a in plan.approvers}
    doc.footer(brief.models, "You got this because you are named as an approver of this request." if approver
               else "You got this because you are on my list of people who receive letters.", contacts, person)
    return doc.build()


def _waits(plan: PlanRecord, now: dt.datetime) -> bool:
    """A plan waits for an answer while it is open and its time is not over. An open plan that is past its time is closed by the loop, not listed."""
    end = brief_mod.parse_time(plan.expires_at)
    moment = now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)
    return plan.state == "open" and (end is None or end > moment)


def digest_letter(person: Person, base_url: str, now: dt.datetime, waiting: Sequence[tuple[PlanRecord, CaseRecord | None]], contacts: Sequence[str] = ()) -> Letter | None:
    """The decisions that wait for a person, at most five, one line each, and one link: to the page of the request when only one waits, else to the page that lists them. None
    when nothing waits: nothing is sent then."""
    base = _base(base_url)
    briefs = sorted((brief_mod.build_brief(case, plan, None, (), now=now) for plan, case in waiting if _waits(plan, now)), key=brief_mod.order_key)
    if not briefs:
        return None
    count = len(briefs)
    doc = _Doc(f"{count} decision{' waits' if count == 1 else 's wait'} for you")
    lines = []
    for item in briefs[:MAX_LISTED]:
        figure = f" About {usd_text(item.saving.monthly)} a month, {item.saving.level}." if item.saving.monthly is not None else ""
        lines.append(f"{_data(item.headline, 200)}.{figure}")
    doc.items(*lines)
    if count > MAX_LISTED:
        doc.paragraph(f"{count - MAX_LISTED} more wait on the page.")
    if count == 1:
        doc.button("Decide", _plan_url(base, briefs[0].plan_id))
    else:
        doc.button("Open the decisions", f"{base}/")
    doc.footer((), f"You got this because you are on my list of people, with the roles: {_roles(person)}.", contacts, person)
    return doc.build()
