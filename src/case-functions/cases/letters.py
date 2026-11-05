"""The letters: what Meternaut writes to a person, as pure functions of the data they are given.

A letter is a subject, an HTML body (what Graph's sendMail sends) and a plain-text copy of the same words (kept for the record and for the tests).
Nothing here reads a clock, a store or the network: the caller passes the records, the address of the console and the time.

What every letter does (docs/experience/04-messages-and-cards.md and 05-letters-and-requests.md):
- The subject starts with [Meternaut], says the point in plain words and holds no resource name and no amount of money.
- The body says that an AI wrote it, which AI roles took part (the Detective and the Skeptic are AI models; the plan, the figures, the dates and
  the counts are computed by code) and that a person approves every change. It carries no button that decides: a change is approved on a page.
- A link is the address of the console plus a fixed path, and an opaque id where a plan needs one. No link holds a name, a resource id or a figure.
- Every value that came from a record or from Azure is cut down to one line and escaped. Names from Azure are shown as data and labelled.
- The HTML needs nothing from outside: inline CSS, no script, no image, no remote content. It has real headings, a lang attribute, text that
  meets the contrast of WCAG AA in a light and in a dark palette, and link text that says where the link goes.
- Plain, short, technical wording. No metaphor, no question, no urgency and no countdown. A saving is an estimate until cost lines confirm it.
"""
from __future__ import annotations

import datetime as dt
import html
import math
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from .models import TIME_FORMAT, ActionRecord, CaseRecord, PlanRecord, RunRecord
from .people import Person

SUBJECT_PREFIX = "[Meternaut]"
AI_LINE = "Written by an AI. Figures are computed by tools, not guessed by the AI. Estimates can still be wrong."
MAX_LISTED = 10

# Text and background pairs. The tests check the ratios that WCAG AA asks for (4.5 to 1) for every text colour on the colour it sits on.
LIGHT = {"background": "#ffffff", "text": "#1b1b1b", "muted": "#4a4a4a", "link": "#0b5cad", "head": "#eef2f7", "rule": "#c9ced6"}
DARK = {"background": "#1e1e1e", "text": "#f2f2f2", "muted": "#c8c8c8", "link": "#9cc9ff", "head": "#2b2f36", "rule": "#6b7280"}

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
KIND_WORDS = {
    "orphan-private-endpoint": "a private endpoint without an approved connection",
    "orphan-managed-disk": "a managed disk that is not attached",
    "orphan-public-ip": "a public IP address that is not assigned",
    "load-balancer-without-backends": "a load balancer without backends",
    "empty-app-service-plan": "an App Service plan without apps",
    "stopped-vm": "a virtual machine that is stopped",
    "advisor-cost": "a cost recommendation of Azure Advisor",
}
PLAN_STATE_WORDS = {"open": "open", "approved": "approved, its change is being made", "consumed": "closed because it ran", "declined": "declined",
                    "expired": "expired", "withdrawn": "withdrawn", "failed": "closed because the change failed"}
ACTION_STATE_WORDS = {"queued": "queued", "running": "running", "done": "done", "failed": "failed", "unknown": "not known", "verified": "done and checked"}
DONE_SUBJECTS = {"done": "A change to Azure has run", "verified": "A change to Azure has run", "failed": "A change to Azure did not run",
                 "unknown": "The result of a change to Azure is not known"}
BASE = re.compile(r"(?:https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?|http://(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?)(?:/(?!\.+(?:/|$))[A-Za-z0-9._~-]+)*")
OPAQUE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass(frozen=True)
class Letter:
    subject: str
    html: str
    text: str


# ---- the values -----------------------------------------------------------------------------------------------------------------------------------

def _data(value: object, limit: int = 300) -> str:
    """A value from a record or from Azure as one plain line: no control or format character, white space folded, at most `limit` characters."""
    text = "" if value is None else str(value)
    kept = "".join(" " if ch in "\r\n\t" else ("" if unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn") else ch) for ch in text)
    kept = " ".join(kept.split())
    return kept if len(kept) <= limit else kept[: limit - 3].rstrip() + "..."


def _usd(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return f"USD {value:,.2f}"


def _utc(moment: dt.datetime) -> dt.datetime:
    return moment.replace(tzinfo=dt.timezone.utc) if moment.tzinfo is None else moment.astimezone(dt.timezone.utc)


def _parse(text: object) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(str(text), TIME_FORMAT).replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _when(moment: dt.datetime) -> str:
    return f"{DAYS[moment.weekday()]} {moment.day} {MONTHS[moment.month - 1]} {moment.year}, {moment.hour:02d}:{moment.minute:02d} UTC"


def _stamp(text: object) -> str:
    parsed = _parse(text)
    return _when(parsed) if parsed else (_data(text, 40) or "not recorded")


def _base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not BASE.fullmatch(base):
        raise ValueError("the address of the console is not like https://host")
    return base


def _plan_url(base: str, plan_id: str) -> str:
    if not OPAQUE_ID.fullmatch(plan_id or ""):
        raise ValueError("the id of a plan in a link is an opaque id of letters, digits, hyphens and underscores")
    return f"{base}/ok/{plan_id}"


def _host(base: str) -> str:
    return urlsplit(base).netloc


def _roles(person: Person) -> str:
    return ", ".join(sorted(_data(role, 20) for role in person.roles)) or "none"


def _cannot_be_undone(plan: PlanRecord) -> bool:
    return plan.family.startswith("delete")


def _kind(case: CaseRecord) -> str:
    return KIND_WORDS.get(case.detector) or f"a resource of type {_data(case.resource_type, 80) or 'unknown'}"


def _models(case: CaseRecord) -> str | None:
    models = case.models if isinstance(case.models, dict) else {}
    detective, skeptic = _data(models.get("detective"), 60), _data(models.get("skeptic"), 60)
    if not detective and not skeptic:
        return None
    parts = [f"the Detective ran on {detective}" if detective else "", f"the Skeptic ran on {skeptic}" if skeptic else ""]
    return "For this case " + " and ".join(p for p in parts if p) + "."


# ---- the document ---------------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Heading:
    text: str
    level: int


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
class _Link:
    text: str
    url: str


class _Doc:
    """The blocks of one letter. The words are plain text here: the HTML and the text of the letter are both made from them, and every value is
    escaped when the HTML is written."""

    def __init__(self, point: str) -> None:
        self.subject = f"{SUBJECT_PREFIX} {point}"
        self.blocks: list[object] = [_Heading(point, 1)]

    def heading(self, text: str, level: int = 2) -> None:
        self.blocks.append(_Heading(text, level))

    def paragraph(self, text: str, muted: bool = False) -> None:
        self.blocks.append(_Paragraph(text, muted))

    def facts(self, *rows: tuple[str, str]) -> None:
        self.blocks.append(_Facts(tuple(rows)))

    def items(self, *items: str) -> None:
        self.blocks.append(_Items(tuple(items)))

    def link(self, text: str, url: str) -> None:
        self.blocks.append(_Link(text, url))

    def how_made(self, models: str | None = None) -> None:
        self.heading("How this letter was made")
        self.paragraph(AI_LINE)
        self.paragraph("Two AI model roles take part in the work behind it. The Detective judges whether a resource looks unused. The Skeptic argues against "
                       "that judgement. Neither role can change anything. The plan, the figures, the dates and the counts in this letter were computed by "
                       "code, not by a model. A person approves every change, on a page, after signing in.")
        if models:
            self.paragraph(models)

    def closing(self, why: str | None, now: dt.datetime) -> None:
        if why:
            self.paragraph(why, muted=True)
        self.paragraph(f"Written on {_when(now)}. Replies to this letter are not read, and nothing is approved by e-mail. "
                       "To reach a person, ask whoever put you on my list of people.", muted=True)

    def build(self) -> Letter:
        return Letter(self.subject, _page(self.subject, self.blocks), _plain(self.blocks))


def _plain(blocks: list[object]) -> str:
    lines: list[str] = []
    for block in blocks:
        if isinstance(block, _Heading):
            lines += [block.text, ("=" if block.level == 1 else "-" if block.level == 2 else "~") * min(len(block.text), 72), ""]
        elif isinstance(block, _Paragraph):
            lines += [block.text, ""]
        elif isinstance(block, _Facts):
            lines += [f"{label}: {value}" for label, value in block.rows] + [""]
        elif isinstance(block, _Items):
            lines += [f"- {item}" for item in block.items] + [""]
        elif isinstance(block, _Link):
            lines += [f"{block.text}: {block.url}", ""]
    return "\n".join(lines).rstrip() + "\n"


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _block_html(block: object) -> str:
    light = LIGHT
    if isinstance(block, _Heading):
        size, margin = {1: ("22px", "0 0 12px 0"), 2: ("17px", "24px 0 8px 0")}.get(block.level, ("15px", "16px 0 6px 0"))
        return (f'<h{block.level} class="mn-fg" style="margin:{margin};font-size:{size};line-height:1.3;font-weight:700;color:{light["text"]};">'
                f"{_e(block.text)}</h{block.level}>")
    if isinstance(block, _Paragraph):
        name, color = ("mn-muted", light["muted"]) if block.muted else ("mn-fg", light["text"])
        return f'<p class="{name}" style="margin:0 0 12px 0;color:{color};">{_e(block.text)}</p>'
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
    if isinstance(block, _Link):
        return (f'<p style="margin:0 0 12px 0;"><a class="mn-link" href="{_e(block.url)}" '
                f'style="color:{light["link"]};text-decoration:underline;font-weight:600;">{_e(block.text)}</a></p>')
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
        "}\n</style>\n</head>\n"
        f'<body class="mn-bg mn-fg" style="margin:0;padding:0;background-color:{light["background"]};color:{light["text"]};'
        'font-family:Segoe UI,Arial,sans-serif;font-size:16px;line-height:1.5;">\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="mn-bg" style="background-color:{light["background"]};">\n'
        '<tr><td align="center" style="padding:16px;">\n'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;">\n'
        f'<tr><td align="left" class="mn-fg" style="color:{light["text"]};">\n{body}\n</td></tr>\n'
        "</table>\n</td></tr>\n</table>\n</body>\n</html>\n"
    )


# ---- the four letters -----------------------------------------------------------------------------------------------------------------------------

def first_contact_letter(person: Person, base_url: str, now: dt.datetime) -> Letter:
    """The first letter to a person: who writes, why this person, what happens, what does not, and the page of their settings."""
    base, now = _base(base_url), _utc(now)
    doc = _Doc("An AI assistant for Azure costs will write to you")
    doc.paragraph(f"Hello {_data(person.name, 80)}.")
    doc.paragraph("I am Meternaut, an AI assistant that looks for Azure resources that cost money and are not in use. This is my first letter to you.")
    doc.heading("Why you got this")
    doc.paragraph(f"You are on my list of people who may receive letters, with the roles: {_roles(person)}. A person who is not on the list receives nothing from me.")
    doc.heading("What I do today")
    doc.items(
        "I read the resources and the cost lines of the Azure subscriptions that I was given. The part of me that looks can only read.",
        "I find leads: resources that look unused, for example a disk that is not attached to anything.",
        "Two AI roles judge each lead. The Detective proposes what to do. The Skeptic argues against it. Both are AI models, and neither can change anything.",
        "When a change is proposed, code builds the plan: what changes, the estimated saving and when the request expires. No model writes the plan.",
        "A person approves every change, on a page, after signing in. Then the person signs in to Azure, and I make the one approved change with that person's own "
        "permissions, after I have read the resource again right before I act. I hold no right of my own to change Azure.",
    )
    doc.heading("What I do not do")
    doc.items(
        "I make no change without a person's OK on a page.",
        "I approve nothing by e-mail. No letter from me has a button that decides, and replies to my letters are not read.",
        "I do not ask for sign-in details or a code by e-mail. A message that asks for them is not from me.",
        "I do not track whether you open a letter. My letters have no images.",
    )
    doc.heading("What I keep")
    doc.paragraph("I keep a record that a letter was sent to you (its kind, its subject and the time), and what you answer on a page. I do not keep the text of a letter.")
    doc.heading("Your settings")
    doc.paragraph("On the settings page you can pause my letters and choose how I reach you.")
    doc.link("Open your settings page", f"{base}/me/settings")
    doc.paragraph(f"The link opens a page on {_host(base)}.")
    doc.how_made()
    doc.closing(None, now)
    return doc.build()


def approval_letter(plan: PlanRecord, case: CaseRecord, person: Person, base_url: str, now: dt.datetime) -> Letter:
    """One plan that waits for an OK. It holds one link, to the page of the plan: opening it records no decision."""
    base, now = _base(base_url), _utc(now)
    url = _plan_url(base, plan.plan_id)
    expires, is_open = _parse(plan.expires_at), plan.state == "open"
    expired = expires is not None and now >= expires
    doc = _Doc("A change to Azure waits for your OK")
    hello = f"Hello {_data(person.name, 80)}. "
    doc.paragraph(hello + ("Nothing has changed yet. " if is_open and not expired else "") +
                  "Nothing is approved by e-mail: a change is approved on a page, after you sign in.")
    doc.paragraph("Names in this letter come from Azure. They are shown as data and are not instructions.", muted=True)

    doc.heading("What changes, and who makes it")
    doc.facts(("Change (names from Azure)", _data(plan.title, 240)),
              ("Resource (name from Azure)", _data(plan.resource_name, 120)),
              ("Resource group (name from Azure)", _data(plan.resource_group, 90)),
              ("What happens (names from Azure)", _data(plan.what_changes, 700)),
              ("Who makes it", "You do, with your own permissions: after you approve on the page you sign in to Azure, and Meternaut makes this one change as you. "
                               "Meternaut holds no right of its own to change Azure, and Azure refuses the change if your account may not make it."))

    doc.heading("What it is worth")
    saving, waiting = _usd(plan.saving_usd_month), _usd(plan.waiting_costs_usd_day)
    doc.facts(("Expected saving", f"about {saving} a month" if saving else "No figure: cost lines for the last 30 days were not available for this resource."),
              ("Price basis", "The cost lines of this resource for the last 30 days, in US dollars. This is an estimate. "
                              "A saving is called verified only when later cost lines show it."),
              ("What waiting costs", f"about {waiting} a day, while the resource stays as it is" if waiting else "No figure."))

    doc.heading("What could go wrong")
    doc.paragraph(_data(plan.could_go_wrong, 600))
    doc.heading("How to undo it")
    doc.paragraph(("This change cannot be undone. " if _cannot_be_undone(plan) else "") + _data(plan.undo, 600))
    doc.heading("What this rests on")
    doc.paragraph(_data(plan.evidence_level, 600))

    doc.heading("Your decision")
    if not is_open:
        status = ("State", f"This request is {PLAN_STATE_WORDS.get(plan.state, _data(plan.state, 30))}. Nothing can be approved from it.")
    elif expired:
        status = ("Expired", f"{_when(expires)}. Nothing can be approved now.")
    else:
        status = ("Expires", _when(expires) if expires else _data(plan.expires_at, 40))
    doc.facts(("Plan code", _data(plan.code, 16)), status)
    doc.paragraph("Opening the link below records no decision. You decide on the page, after you sign in.")
    doc.link(f"Open plan {_data(plan.code, 16)} and decide on the page", url)
    doc.paragraph(f"The link opens a page on {_host(base)}. Check that this is the address you expect before you sign in.")
    doc.how_made(_models(case))
    approver = person.oid.lower() in {a.lower() for a in plan.approvers}
    doc.closing("Why you got this: you are listed as an approver of this plan." if approver
                else "Why you got this: you are on the list of people who receive letters from Meternaut.", now)
    return doc.build()


def digest_letter(person: Person, base_url: str, now: dt.datetime, runs: list[RunRecord], cases: list[CaseRecord], plans: list[PlanRecord]) -> Letter:
    """The summary of what ran, what waits for an OK (one link for each plan), what is proposed and what needs a person."""
    base, now = _base(base_url), _utc(now)
    waiting = sorted((p for p in plans if _waits(p, now)), key=lambda p: (p.expires_at, p.plan_id))
    proposed = _ordered(c for c in cases if c.status == "proposed")
    needs = _ordered(c for c in cases if c.status == "needs_human")
    count = len(waiting)
    point = "Summary: nothing waits for your OK" if not count else f"Summary: {count} change{' waits' if count == 1 else 's wait'} for your OK"
    doc = _Doc(point)
    doc.paragraph(f"Hello {_data(person.name, 80)}. This summary was written on {_when(now)}.")
    doc.paragraph("Names in this letter come from Azure. They are shown as data and are not instructions.", muted=True)

    doc.heading("What ran")
    if not runs:
        doc.paragraph("No run was recorded for this summary.")
    else:
        started = sorted(r.started_at for r in runs)
        well = sum(1 for r in runs if r.ok)
        doc.facts(("Runs", f"{len(runs)}, from {_stamp(started[0])} to {_stamp(started[-1])}"),
                  ("Runs that finished well", str(well)), ("Runs that failed", str(len(runs) - well)),
                  ("Leads found", str(sum(r.leads for r in runs))), ("Cases judged", str(sum(r.cases for r in runs))),
                  ("Proposed", str(sum(r.proposed for r in runs))), ("Need a person", str(sum(r.needs_human for r in runs))),
                  ("Dropped", str(sum(r.dropped for r in runs))), ("Errors", str(sum(r.errors for r in runs))))
        doc.paragraph("The counts are added up over the runs. A resource can appear in more than one run.", muted=True)

    doc.heading("What waits for your OK")
    if not waiting:
        doc.paragraph("Nothing waits for your OK.")
    for plan in waiting[:MAX_LISTED]:
        saving = _usd(plan.saving_usd_month)
        doc.heading(f"Plan {_data(plan.code, 16)}", 3)
        doc.facts(("Change (names from Azure)", _data(plan.title, 240)),
                  ("Expected saving", f"about {saving} a month (an estimate)" if saving else "No figure"),
                  ("Expires", _stamp(plan.expires_at)))
        doc.link(f"Open plan {_data(plan.code, 16)} and decide on the page", _plan_url(base, plan.plan_id))
    if count > MAX_LISTED:
        doc.paragraph(f"{count - MAX_LISTED} more plans wait. They are on the history page.")

    doc.heading("What I propose")
    _case_list(doc, proposed, "The AI roles proposed removing these resources. A proposal is not a plan: nothing can change until a plan exists and a person "
                              "approves it.", "No resource is proposed.")
    doc.heading("What needs a person")
    _case_list(doc, needs, "The AI roles could not settle these, or a check held them back. A person has to look at them.", "No case needs a person.")
    doc.link("Open the history page", f"{base}/history")
    doc.paragraph(f"The links open pages on {_host(base)}.")
    doc.how_made()
    doc.closing(f"Why you got this: you are on the list of people who receive letters from Meternaut, with the roles: {_roles(person)}.", now)
    return doc.build()


def done_letter(plan: PlanRecord, action: ActionRecord, case: CaseRecord, person: Person, base_url: str, now: dt.datetime) -> Letter:
    """What happened to the change of one plan, and what the check afterwards found. Cost lines confirm the saving later."""
    base, now = _base(base_url), _utc(now)
    ran = action.state in ("done", "verified")
    doc = _Doc(DONE_SUBJECTS.get(action.state, "The state of a change to Azure"))
    said = {"done": "A change that was approved on a page has run.", "verified": "A change that was approved on a page has run.",
            "failed": "A change that was approved on a page was tried and did not complete.",
            "unknown": "A change that was approved on a page was started, and its result is not known."}
    doc.paragraph(f"Hello {_data(person.name, 80)}. " + said.get(action.state, "This is the state of a change that was approved on a page."))
    doc.paragraph("Names in this letter come from Azure. They are shown as data and are not instructions.", muted=True)

    doc.heading("What ran")
    doc.facts(("Change (names from Azure)", _data(plan.title, 240)),
              ("Resource (name from Azure)", _data(plan.resource_name, 120)),
              ("Resource group (name from Azure)", _data(plan.resource_group, 90)),
              ("Plan code", _data(plan.code, 16)),
              ("State", ACTION_STATE_WORDS.get(action.state, _data(action.state, 30))),
              ("Finished", _stamp(action.finished_at) if action.finished_at else "not finished"))

    doc.heading("The result")
    rows = [("Result", _data(action.result, 600) or "No result text was recorded.")]
    if action.error:
        rows.append(("Error", _data(action.error, 300)))
    check = action.verification if isinstance(action.verification, dict) else {}
    if check.get("gone") is True:
        rows.append(("Check afterwards", "Azure no longer lists the resource."))
    elif check.get("gone") is False:
        rows.append(("Check afterwards", "Azure still lists the resource."))
    if check.get("note"):
        rows.append(("Note of the check", _data(check["note"], 300)))
    after = _usd(check.get("costAfterUsd"))
    if after:
        rows.append(("Cost lines after the change", after))
    doc.facts(*rows)

    doc.heading("How to undo it")
    if ran:
        doc.paragraph(("This change cannot be undone. " if _cannot_be_undone(plan) else "") + _data(plan.undo, 600))
    else:
        doc.paragraph("The result is not a completed change. Look at the resource in Azure before anything else is done with it.")

    if ran:
        doc.heading("What happens next")
        saving = _usd(plan.saving_usd_month)
        doc.paragraph("Cost lines arrive after the change. When they do, I compare them with the estimate"
                      + (f" of about {saving} a month" if saving else "") + " and record the result. Until then the saving is an estimate and is not confirmed.")
    doc.link("Open your decisions on the page", f"{base}/me/decisions")
    doc.paragraph(f"The link opens a page on {_host(base)}.")
    doc.how_made(_models(case))
    approver = person.oid.lower() in {a.lower() for a in plan.approvers}
    doc.closing("Why you got this: you are listed as an approver of this plan." if approver
                else "Why you got this: you are on the list of people who receive letters from Meternaut.", now)
    return doc.build()


def _waits(plan: PlanRecord, now: dt.datetime) -> bool:
    """A plan waits for an OK while it is open and its time is not over. An open plan that is past its time is closed by the loop, not listed."""
    expires = _parse(plan.expires_at)
    return plan.state == "open" and (expires is None or expires > now)


def _ordered(cases) -> list[CaseRecord]:
    return sorted(cases, key=lambda c: (-(c.saving_usd_month or 0.0), _data(c.resource_name, 120).lower(), c.case_id))


def _case_list(doc: _Doc, cases: list[CaseRecord], intro: str, empty: str) -> None:
    if not cases:
        doc.paragraph(empty)
        return
    doc.paragraph(intro)
    for case in cases[:MAX_LISTED]:
        rows = [("Resource (name from Azure)", _data(case.resource_name, 120)), ("What it is", _kind(case)),
                ("Resource group (name from Azure)", _data(case.resource_group, 90))]
        saving = _usd(case.saving_usd_month)
        if saving:
            rows.append(("Estimated saving", f"about {saving} a month"))
        if case.guards:
            rows.append(("Checks that held it back", ", ".join(_data(g, 30) for g in case.guards)))
        doc.facts(*rows)
    if len(cases) > MAX_LISTED:
        doc.paragraph(f"{len(cases) - MAX_LISTED} more are on the history page.")
