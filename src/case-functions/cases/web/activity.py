"""What the AI looked at, for the roles ops and owner: the latest investigation as its two AIs left it, and which kinds of resource its tools read (docs/proposals/23).

It shows what the app kept of each investigation (cases/activity.py): no name, tag, id or amount of money; the labels that the AI used inside a run (r1, r53) stay as written. It changes nothing.
"""
from __future__ import annotations

from ..brief import BASIS_WORDS, plain, without_ids
from ..models import INVESTIGATION_TOUCHES, KEPT_INVESTIGATIONS, InvestigationRecord
from . import words
from .common import counted, kind_text, read
from .core import Ctx, Response, Safe, fmt, join
from .layout import head, items, kpi, kpis, link, notice, nowrap, page, paragraph, quoted, table

EARLIER = 10
WHY = "your role ops or owner lets you see what the AI looked at"
LEAD = "The AI's own account of its latest investigation: what it looked at, what it concluded and what became of its findings. This page changes nothing."
LABELS = "Labels such as r1 and r53 stand for a resource inside that run only. They mean nothing outside it, and this page does not say which resource they were."
LIMITS = ('The phrases are the AI\'s own claims, and code did not check them. "Looked at" means that a tool read the kind of resource. It does not mean that the AI judged all of it. '
          "A run from before this page existed was not recorded, which is not the same as nothing.")
KINDS = ("A kind of resource is a type that Azure gives to a resource. The estate has the kinds that the cost lines and the tools showed. They are in the order of what each cost in "
         "the last 30 days, the dearest first, and no amount is shown. \"Looked at\" means that a tool read that kind in the last investigation. It does not mean that the AI judged all of it.")
NOT_RECORDED = "Not recorded for earlier runs"
NO_KINDS = "No kind of resource is known for this run: no cost line was read and no tool showed a resource."
STARTED = {"timer": "the daily timer", "request": "a person or a tool that asked for a run"}
# How the Investigator's run ended: the word of the tile, and what it means.
ENDS = {"answered": ("It gave its answer", "It gave its answer within its limits."), "time": ("Its time ran out", "Its time for tool calls ran out, so it was told to answer with what it had."),
        "calls": ("Its calls ran out", "It used all its tool calls, so it was told to answer with what it had."),
        "tokens": ("Its tokens ran out", "The tokens that it was allowed ran out, so it was told to answer with what it had."),
        "refused": ("It was not allowed to run", "A safeguard around the agents did not let it run, or stopped it."),
        "failed": ("It failed", "It gave no answer that could be read.")}
BEATS = ("The AI looked at the estate in parts, one after the other. Code chose the parts by what each kind of resource cost in the last 30 days, the dearest first, and no amount is shown. "
         "Each part is a short session of its own, with its own tool calls, seconds and tokens, and the lines of the bill that no resource owns can be a part too.")
STOPS = {"tokens": "its token limit was used up", "switch": "a switch that holds the agents is pulled", "refusals": "too many of its tool calls were refused"}
VERDICTS = {"agree": "Agrees", "disagree": "Disagrees", "unsure": "Is not sure"}
# What became of the resources of a finding (the words of cases/approvals.py for a request that was held back).
FATES = {"request": "a request was made", "person": "left for a person, no request yet", "dropped": "dropped, no change is suggested", "nothing": "held back, nothing to say",
         "automation": "held back, managed by an automation", "unchecked": "held back, not checked who changed it", "impact": "held back, impact not checked"}
LEFT = {"unknown": "that no tool showed", "unproven": "with no measurement that proves it", "repeated": "that an earlier finding has", "guarded": "held back by a guard",
        "recent": "judged lately", "capped": "beyond the cap of one run", "small": "too small to open a case"}


def _text(value: object, limit: int = 300) -> str:
    """Text that an AI wrote, as one safe line with no id: never trusted, escaped where it is put in."""
    return plain(without_ids("" if value is None else str(value)), limit)


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _of(record: InvestigationRecord) -> str:
    """How many of the kinds of resource that the estate is known to have the tools read: "12 of 41"."""
    return f"{_count(record.looked)} of {_count(record.known)}"


def _tiles(record: InvestigationRecord | None) -> Safe:
    if record is None:
        gone = "No investigation is recorded yet."
        return kpis(kpi("Looked at in the last run", "—", "", gone), kpi("Findings kept", "—", "", gone), kpi("Stopped because", "—", "", gone), label="The latest investigation")
    if record.known:
        looked = kpi("Looked at in the last run", _of(record), "kinds of resource", f"A tool read {_count(record.looked)} of the {counted(_count(record.known), 'kind')} of resource that the estate is known to have.")
    else:
        looked = kpi("Looked at in the last run", "—", "", NO_KINDS)
    if record.answered:
        kept = sum(1 for found in record.findings if found.get("kept"))
        found_tile = kpi("Findings kept", f"{kept} of {len(record.findings)}", "findings", f"The checks of code kept {kept} of the {len(record.findings)} findings that the AI wrote.")
    else:
        found_tile = kpi("Findings kept", "—", "", "The AI gave no answer that code could read, so there is no finding to check.")
    word, meaning = ENDS.get(record.end, ENDS["failed"])
    used = f"It made {record.calls} of the {record.max_calls} tool calls that it was allowed and used {record.seconds} of the {record.max_seconds} seconds."
    why = f" {STOPS[record.stop].capitalize()}." if record.end == "refused" and record.stop in STOPS else ""
    unread = " Its answer could not be read." if not record.answered and record.end in ("time", "calls", "tokens") else ""
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
    return [says, f"{sure:.2f}" if isinstance(sure, (int, float)) and not isinstance(sure, bool) else "none", str(resources) if found.get("kept") else f"{resources} listed", _second(found), _fates(found)]


def _findings(record: InvestigationRecord) -> Safe:
    if not record.findings:
        return paragraph("The AI wrote no finding." if record.answered else "There is no finding: the AI gave no answer that code could read.")
    parted = bool(record.beats)
    rows = [([str(_count(found.get("beat")))] if parted else []) + _finding(found) for found in record.findings]
    more = [paragraph(f"The record has room for {len(record.findings)} findings. {_count(record.more)} more were written, and they are not listed here.")] if _count(record.more) else []
    return join([paragraph("The sentences of the first column were written by the AI.") if not parted else paragraph("The sentences of the second column were written by the AI."),
                 table("findings", "Findings of the last run", (["Part"] if parted else []) + ["What it says", "How sure (0 to 1)", "Resources", "The second AI", "What became of it"], rows), *more])


def _beats(record: InvestigationRecord) -> Safe:
    """One row for each part that the AI looked at: its kinds, what it used and how it ended, how many of its kinds its tools read, how many findings it wrote and what it said that it examined."""
    rows = []
    for beat in record.beats:
        kinds = [kind_text(str(kind)) for kind in (beat.get("kinds") if isinstance(beat.get("kinds"), list) else [])]
        if beat.get("billing"):
            kinds.append(Safe("the lines of the bill that no resource owns"))
        if _count(beat.get("more")):
            kinds.append(Safe(counted(_count(beat.get("more")), "more kind")))
        said = [_text(phrase, 100) for phrase in (beat.get("says") if isinstance(beat.get("says"), list) else [])]
        rows.append([str(_count(beat.get("n"))), join(kinds, ", ") if kinds else Safe("—"), f"{_count(beat.get('calls'))} of {_count(beat.get('max_calls'))}", str(_count(beat.get("seconds"))),
                     f"{_count(beat.get('tokens')):,}", ENDS.get(beat.get("end"), ENDS["failed"])[0], f"{_count(beat.get('looked'))} of {len(beat.get('kinds') or [])}" if beat.get("kinds") else "—",
                     str(_count(beat.get("found"))), join((fmt("{phrase}", phrase=phrase) for phrase in said), "<br>") if said else Safe("—")])
    return join([paragraph(BEATS), table("beats", "The parts that the AI looked at, in order", ["Part", "Kinds of resource", "Tool calls", "Seconds", "Tokens", "Stopped because", "Kinds looked at", "Findings",
                                                                                              "What the AI said it examined"], rows)])


def _kinds(record: InvestigationRecord) -> Safe:
    known, looked = _count(record.known), _count(record.looked)
    if not known:
        return paragraph(NO_KINDS)
    parts: list[object] = [paragraph(KINDS)]
    if not record.subs_costed:
        parts.append(paragraph("No cost was read in US dollars, so the kinds are in the order of their names."))
    elif record.subs_costed < record.subs:
        parts.append(paragraph(f"The order rests on the cost of {record.subs_costed} of {record.subs} subscriptions."))
    done = [[kind_text(str(k[0])), ", ".join(INVESTIGATION_TOUCHES[x] for x in str(k[1]) if x in INVESTIGATION_TOUCHES)] for k in record.kinds if isinstance(k, (list, tuple)) and len(k) == 2]
    for table_id, title, count, rows, headers in (("looked", "Looked at", looked, done, ["Kind of resource", "What the tools did"]),
                                                  ("unread", "Not looked at", max(0, known - looked), [[kind_text(str(k))] for k in record.unread], ["Kind of resource"])):
        parts.append(paragraph(f"{title}: {count} of {counted(known, 'kind')}." + (f" The {len(rows)} dearest are shown." if count > len(rows) else "")))
        if rows:
            parts.append(table(table_id, f"{title}: kinds of resource, the dearest first", headers, rows, row_header=True))
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
                         _of(line) if line.known else "not known", ENDS.get(line.end, ENDS["failed"])[0]])
        else:
            rows.append([nowrap(ctx.when(line.started_at)), NOT_RECORDED, "—", "—", "—"])
    return table("earlier", f"The {EARLIER} investigations before the latest, newest first", ["Started", "Tool calls", "Findings kept", "Kinds looked at", "Stopped because"], rows)


def activity_page(ctx: Ctx) -> Response:
    records = ctx.store.investigations_recent(KEPT_INVESTIGATIONS)  # a store that cannot be read is the fault page of the router: "I cannot reach my records"
    runs, runs_ok = read(lambda: ctx.store.runs_recent(KEPT_INVESTIGATIONS * 2), [])
    latest = records[0] if records else None
    recorded = {record.run_id for record in records}
    unrecorded = [run for run in runs if run.investigated and run.run_id not in recorded]
    parts: list[object] = [head("What the AI looked at", LEAD), _tiles(latest)]
    newer = [run for run in unrecorded if latest is not None and run.started_at > latest.at]
    if newer:
        parts.append(notice("warning", "The newest investigation was not recorded", fmt("It began {when}. What follows is from the latest one that is recorded.", when=ctx.when(newer[0].started_at))))
    if not runs_ok:
        parts.append(notice("error", "The runs cannot be read", "I cannot read the runs now, so a run with no record is not listed. Nothing has changed."))
    if latest is not None:
        if latest.end in ("failed", "refused") and latest.note:
            parts.append(notice("warning", "It did not finish", _text(latest.note, 200)))
        parts += [Safe("<h2>What the AI looked at and concluded</h2>"), _how(ctx, latest), *([Safe("<h2>The parts that the AI looked at</h2>"), _beats(latest)] if latest.beats else []),
                  Safe("<h2>Findings of the last run</h2>"), _findings(latest), Safe("<h2>Which kinds of resource the AI looked at</h2>"), _kinds(latest)]
    else:
        parts.append(notice("info", "", "No investigation is recorded yet. An investigation that ran before this page existed was not recorded."))
    parts += [Safe("<h2>Earlier runs</h2>"), _earlier(ctx, records[1:], unrecorded), Safe("<h2>What this page cannot tell</h2>"), paragraph(LIMITS)]
    if ctx.principal.has("ops"):  # the page of every run is for that role alone
        parts.append(paragraph(link(ctx.url("/ops/runs"), "Every run and every finding")))
    return page(ctx, "What the AI looked at", join(parts), current="/ops/activity", ai=True, why=WHY, wide=True)
