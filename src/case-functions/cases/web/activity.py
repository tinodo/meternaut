"""What the AI looked at, for the roles ops and owner: the latest investigation as the Investigator and the Skeptic left it, and how much of the 30-day cost its tools read (docs/proposals/23).

It shows what the app kept of each investigation (cases/activity.py): the Investigator's own phrases, every finding and what became of it, why the run stopped, and the kinds of resource that the tools
touched against the cost of those kinds. It shows no name, tag or id of a resource, and the labels that the AI used inside a run (r1, r53) are left as they are. It changes nothing.
"""
from __future__ import annotations

from ..brief import BASIS_WORDS, plain, without_ids
from ..models import INVESTIGATION_TOUCHES, KEPT_INVESTIGATIONS, InvestigationRecord
from . import words
from .common import counted, effective_state, kind_text, read
from .core import Ctx, Response, Safe, fmt, join
from .figures import chip, dollars
from .layout import head, items, kpi, kpis, link, notice, nowrap, page, paragraph, quoted, table
from .savings import PER

KINDS_SHOWN = 25  # the kinds of resource of the table of the money
EARLIER = 10
WHY = "your role ops or owner lets you see what the AI looked at"
LEAD = "The AI's own account of its latest investigation: what it looked at, what it concluded and what became of its findings. This page changes nothing."
LABELS = "Labels such as r1 and r53 stand for a resource inside that run only. They mean nothing outside it, and this page does not say which resource they were."
LIMITS = ('The phrases are the AI\'s own claims, and code did not check them. "Looked at" means that a tool read the kind of resource, not that the analysis went deep. The costs are the last 30 days '
          "that the run read, in US dollars, and are here only to show how much of the bill the AI looked at: this is not a cost report, and Cost Management has the bill. A run from before this page "
          "existed was not recorded, which is not the same as nothing.")
NOT_RECORDED = "Not recorded for earlier runs"
STARTED = {"timer": "the daily timer", "request": "a person or a tool that asked for a run"}
# How the Investigator's run ended: the word of the tile, and what it means.
ENDS = {"answered": ("It gave its answer", "It gave its answer within its limits."), "time": ("Its time ran out", "Its time for tool calls ran out, so it was told to answer with what it had."),
        "calls": ("Its calls ran out", "It used all its tool calls, so it was told to answer with what it had."), "refused": ("It was not allowed to run", "A safeguard around the agents did not let it run, or stopped it."),
        "failed": ("It failed", "It gave no answer that could be read.")}
STOPS = {"tokens": "its token limit was used up", "switch": "a switch that holds the agents is pulled", "refusals": "too many of its tool calls were refused"}
VERDICTS = {"agree": "Agrees", "disagree": "Disagrees", "unsure": "Is not sure"}
# What became of the resources of a finding: a request was made, it was left for a person, it was dropped, or a rule held the request back (the words that the History says: cases/approvals.py).
FATES = {"request": "a request was made", "person": "left for a person, no request yet", "dropped": "dropped, no change is suggested", "nothing": "held back, nothing to say",
         "automation": "held back, managed by an automation", "unchecked": "held back, not checked who changed it", "impact": "held back, impact not checked"}
LEFT = {"unknown": "that no tool showed", "unproven": "with no measurement that proves it", "repeated": "that an earlier finding has", "guarded": "held back by a guard",
        "recent": "judged lately", "capped": "beyond the cap of one run"}


def _share(part: object, whole: object) -> str | None:
    """A share as a whole percent ("under 1%" for a little), or None when there is nothing to divide by."""
    if not isinstance(part, (int, float)) or not isinstance(whole, (int, float)) or whole <= 0:
        return None
    percent = 100 * part / whole
    return "under 1%" if 0 < percent < 1 else f"{round(percent)}%"


def _text(value: object, limit: int = 300) -> str:
    """Text that an AI wrote, as one safe line with no id: never trusted, escaped where it is put in."""
    return plain(without_ids("" if value is None else str(value)), limit)


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _tiles(record: InvestigationRecord | None) -> Safe:
    if record is None:
        gone = "No investigation is recorded yet."
        return kpis(kpi("Looked at in the last run", "—", "", gone), kpi("Findings kept", "—", "", gone), kpi("Stopped because", "—", "", gone), label="The latest investigation")
    share = _share(record.cost_looked, record.cost_total)
    kinds = f"{counted(_count(record.looked), 'kind')} of resource."
    if share is None:
        looked = kpi("Looked at in the last run", "—", "", f"{kinds} No share can be told: the run read no cost in US dollars.")
    else:
        costed = f" The cost of {record.subs_costed} of {record.subs} subscriptions was read." if record.subs_costed < record.subs else ""
        looked = kpi("Looked at in the last run", share, "of the 30-day cost",
                     f"{kinds} How it is counted: the cost of the kinds of resource that its tools read, divided by all the cost that the run read, in US dollars.{costed}")
    if record.answered:
        kept = sum(1 for found in record.findings if found.get("kept"))
        found_tile = kpi("Findings kept", f"{kept} of {len(record.findings)}", "findings", f"The checks of code kept {kept} of the {len(record.findings)} findings that the AI wrote.")
    else:
        found_tile = kpi("Findings kept", "—", "", "The AI gave no answer that code could read, so there is no finding to check.")
    word, meaning = ENDS.get(record.end, ENDS["failed"])
    used = f"It made {record.calls} of the {record.max_calls} tool calls that it was allowed and used {record.seconds} of the {record.max_seconds} seconds."
    why = f" {STOPS[record.stop].capitalize()}." if record.end == "refused" and record.stop in STOPS else ""
    unread = " Its answer could not be read." if not record.answered and record.end in ("time", "calls") else ""
    return kpis(looked, found_tile, kpi("Stopped because", word, "", f"{used} {meaning}{why}{unread}"), label="The latest investigation")


def _how(ctx: Ctx, record: InvestigationRecord) -> Safe:
    phrases = [_text(phrase, 100) for phrase in record.examined]
    body: list[object] = [paragraph(fmt("The investigation began {when}, started by {trigger}. The first AI was {first} and the second AI was {second}.", when=ctx.when(record.at),
                                        trigger=STARTED.get(record.trigger, "a source that was not recorded"), first=_text(record.investigator, 60) or "not recorded",
                                        second=_text(record.skeptic, 60) or "not recorded"))]
    body += [quoted("Written by the AI", items(phrases)), paragraph(LABELS)] if phrases else [paragraph("The AI wrote no phrase about what it examined in this run.")]
    return join(body)


def _fates(found: dict) -> Safe:
    fates = found.get("fates") if isinstance(found.get("fates"), dict) else {}
    left = found.get("left") if isinstance(found.get("left"), dict) else {}
    lines = [f"{counted(_count(n), 'resource')}: {FATES.get(name, 'not known')}" for name, n in fates.items()]
    gone = ", ".join(f"{counted(_count(n), 'resource')} {LEFT[name]}" for name, n in left.items() if name in LEFT and _count(n))
    if not found.get("kept"):
        lines.append("Dropped: no resource of it was left" + (f" ({gone})" if gone else ""))
    elif gone:
        lines.append(f"Left out: {gone}")
    return join((fmt("{line}", line=line) for line in lines), "<br>") if lines else Safe("Not recorded")


def _second(found: dict) -> Safe:
    if not found.get("kept"):
        return Safe("Not asked: the finding was dropped before it")
    doubts = [_text(doubt, 120) for doubt in (found.get("doubts") if isinstance(found.get("doubts"), list) else [])]
    return fmt("{verdict}{doubts}", verdict=VERDICTS.get(found.get("verdict"), "Gave no verdict"), doubts=fmt("<br>{list}", list=items(doubts)) if doubts else "")


def _finding(found: dict) -> list[object]:
    basis = BASIS_WORDS.get(found.get("basis"), "Another reason") if found.get("basis") else "No reason that code could read"
    proposal = words.recommendation_word(found.get("proposal")).lower() if found.get("proposal") else "none"
    sure = found.get("sure")
    says = fmt('{says}<br><span class="muted">{basis}. Proposal: {proposal}.</span>{note}', says=_text(found.get("says")) or "The AI wrote no sentence.", basis=basis, proposal=proposal,
               note=fmt('<br><span class="muted">Code: {note}</span>', note=_text(found.get("note"), 160)) if found.get("note") else "")
    resources = _count(found.get("resources"))
    usd = found.get("usd")
    cost = fmt('{usd}<br><span class="muted">What they cost, not what could be saved.</span>', usd=dollars(usd)) if isinstance(usd, (int, float)) else Safe("No cost line was read for them")
    return [says, f"{sure:.2f}" if isinstance(sure, (int, float)) and not isinstance(sure, bool) else "none", str(resources) if found.get("kept") else f"{resources} listed", cost, _second(found), _fates(found)]


def _findings(record: InvestigationRecord) -> Safe:
    if not record.findings:
        return paragraph("The AI wrote no finding." if record.answered else "There is no finding: the AI gave no answer that code could read.")
    return join([paragraph("The sentences of the first column were written by the AI."),
                 table("findings", "Findings of the last run. The cost is what the resources cost in 30 days, not what could be saved.",
                       ["What it says", "How sure (0 to 1)", "Resources", "What they cost in 30 days", "The second AI", "What became of it"], [_finding(found) for found in record.findings])])


def _open(ctx: Ctx) -> tuple[dict[str, list[int]], bool, bool]:
    """The open requests and the open questions of each kind of resource, from the findings: a request waits for a person's answer, and a question is a finding that nobody has been asked about
    yet. Whether a read failed, and whether one read was full (there may be more)."""
    plans, ok = read(ctx.store.plans_open, [])
    asked = {plan.case_id for plan in plans if effective_state(ctx, plan) == "open"}
    counts: dict[str, list[int]] = {}
    cut = len(plans) >= PER
    for status in ("proposed", "needs_human", "awaiting_ok"):
        cases, fine = read(lambda status=status: ctx.store.cases_recent(PER, status), [])
        ok, cut = ok and fine, cut or len(cases) >= PER
        for case in cases:
            if case.case_id in asked or status != "awaiting_ok":
                counts.setdefault((case.resource_type or "").lower(), [0, 0])[0 if case.case_id in asked else 1] += 1
    return counts, not ok, cut


def _money(ctx: Ctx, record: InvestigationRecord) -> Safe:
    counts, failed, cut = _open(ctx)
    kinds = [entry for entry in record.kinds[:KINDS_SHOWN] if isinstance(entry, (list, tuple)) and len(entry) == 3 and isinstance(entry[1], (int, float))]
    rows = []
    for kind, usd, verbs in kinds:
        none = kind == "other"
        if none:
            seen = Safe("No tool can look at it: Cost Management ties it to no resource")
        elif verbs:
            seen = fmt('{chip}<br><span class="muted">{verbs}</span>', chip=chip("Looked at", "low", "circle"), verbs=", ".join(INVESTIGATION_TOUCHES.get(letter, "") for letter in str(verbs)))
        else:
            seen = chip("Not looked at", "mid", "triangle")
        asked, questions = counts.get(str(kind), [0, 0])
        unknown = "Cannot be read now" if failed else ("Not applicable" if none else None)
        lead = "At least " if cut else ""
        rows.append([Safe("Cost that no kind of resource has") if none else kind_text(str(kind)), dollars(usd, cents=False), _share(usd, record.cost_total) or "not known", seen,
                     unknown or f"{lead}{asked}", unknown or f"{lead}{questions}"])
    parts: list[object] = [paragraph("The dearest kinds of resource by their cost in the last 30 days, in US dollars, from the cost lines that the run read. \"Looked at\" means that a tool read that kind "
                                     "in the last investigation. An open request waits for a person's answer. An open question is a finding that nobody has been asked about yet.")]
    if failed:
        parts.append(notice("error", "Part of the findings cannot be read", "I cannot read all of them now, so the open requests and questions are missing. Nothing has changed."))
    if not rows:
        return join([*parts, paragraph("No cost in US dollars was read in this run, so there is nothing to show.")])
    parts.append(table("money", "The dearest kinds of resource, their cost in 30 days and what the AI did with them",
                       ["Kind of resource", "Cost in 30 days", "Share of the cost read", "In the last investigation", "Open requests", "Open questions"], rows, row_header=True))
    share = _share(sum(entry[1] for entry in kinds), record.cost_total)
    if share is not None:
        parts.append(paragraph(f"The rows of this table are {share} of the cost that the run read."))
    return join(parts)


def _earlier(ctx: Ctx, records: list[InvestigationRecord], unrecorded: list) -> Safe:
    lines = sorted([(r.at, r) for r in records] + [(run.started_at, run) for run in unrecorded], key=lambda line: line[0], reverse=True)[:EARLIER]
    if not lines:
        return paragraph("No earlier investigation is recorded.")
    rows: list[list[object]] = []
    for _, line in lines:
        if isinstance(line, InvestigationRecord):
            kept = sum(1 for found in line.findings if found.get("kept"))
            rows.append([nowrap(ctx.when(line.at)), f"{line.calls} of {line.max_calls}", f"{kept} of {len(line.findings)}" if line.answered else "none: no answer",
                         _share(line.cost_looked, line.cost_total) or "not known", ENDS.get(line.end, ENDS["failed"])[0]])
        else:
            rows.append([nowrap(ctx.when(line.started_at)), NOT_RECORDED, "—", "—", "—"])
    return table("earlier", f"The {EARLIER} investigations before the latest, newest first", ["Started", "Tool calls", "Findings kept", "Share of the cost looked at", "Stopped because"], rows)


def activity_page(ctx: Ctx) -> Response:
    records = ctx.store.investigations_recent(KEPT_INVESTIGATIONS)  # a store that cannot be read is the fault page of the router: "I cannot reach my records"
    runs, runs_ok = read(lambda: ctx.store.runs_recent(KEPT_INVESTIGATIONS * 2), [])
    latest = records[0] if records else None
    known = {record.run_id for record in records}
    unrecorded = [run for run in runs if run.investigated and run.run_id not in known]
    parts: list[object] = [head("What the AI looked at", LEAD), _tiles(latest)]
    newer = [run for run in unrecorded if latest is not None and run.started_at > latest.at]
    if newer:
        parts.append(notice("warning", "The newest investigation was not recorded", fmt("It began {when}. What follows is from the latest one that is recorded.", when=ctx.when(newer[0].started_at))))
    if not runs_ok:
        parts.append(notice("error", "The runs cannot be read", "I cannot read the runs now, so a run with no record is not listed. Nothing has changed."))
    if latest is not None:
        if latest.end in ("failed", "refused") and latest.note:
            parts.append(notice("warning", "It did not finish", _text(latest.note, 200)))
        parts += [Safe("<h2>What the AI looked at and concluded</h2>"), _how(ctx, latest), Safe("<h2>Findings of the last run</h2>"), _findings(latest),
                  Safe("<h2>Where the money goes and what the AI did with it</h2>"), _money(ctx, latest)]
    else:
        parts.append(notice("info", "", "No investigation is recorded yet. An investigation that ran before this page existed was not recorded."))
    parts += [Safe("<h2>Earlier runs</h2>"), _earlier(ctx, records[1:], unrecorded), Safe("<h2>What this page cannot tell</h2>"), paragraph(LIMITS)]
    if ctx.principal.has("ops"):  # the page of every run is for that role alone
        parts.append(paragraph(link(ctx.url("/ops/runs"), "Every run and every finding")))
    return page(ctx, "What the AI looked at", join(parts), current="/ops/activity", ai=True, why=WHY, wide=True)
