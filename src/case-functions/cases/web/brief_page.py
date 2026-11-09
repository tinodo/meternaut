"""The page of one request or case: the decision brief (brief.py) as a web page.

A stranger must be able to answer eight questions from this page in a minute, without opening anything else: what am I asked to decide, what do I get, how sure is it and
on what evidence, what exactly happens if I say yes (who does it, with whose rights), can it be undone, what could go wrong, whose resource is it, and what are my choices.
So the page is the headline, one sentence of what it is worth, the evidence (at most five rows, and the words of the two AIs in boxes that say they are not checked), what
happens if the person says yes, whose resource it is, and ONE form with the answers that exist right now. Everything else (the steps, the models, the tokens, the checks, the
ids, the log of the change) is in one collapsed Details disclosure at the end.

What came from the estate or from an AI is escaped and set in a labelled quote, never as a link or a control; the one link to the Azure portal is made from a resource id
that code has checked to be the id of one resource.
"""
from __future__ import annotations

import json

from ..brief import OPTIONS_END, PAUSED_ADVICE, PAUSED_CHANGES, UNREAD, ago_text, Brief, Saving, usd_text
from ..models import ActionRecord, CaseRecord, DecisionRecord, PlanRecord
from . import words
from .common import action_block, confidence, detector_cell, kind_text, read
from .core import MAX_NOTE, Ctx, Response, Safe, esc, fmt, join, link_part, number, parse_time
from .layout import block, button, code, details, error_summary, form, hidden, items, link, notice, page, paragraph, quoted, select, summary, table, textarea

INVESTIGATION = "investigation"  # the detector of the cases that the Watch's own investigation opens (cases/investigate.py)
STEP_HEADERS = ["Step", "Model", "Tokens in", "Tokens out", "Milliseconds", "Result", "Note"]
PAUSED = PAUSED_CHANGES


# -- the parts of the page ------------------------------------------------------------------------------------------------------------------------

def saving_sentence(saving: Saving) -> Safe:
    """What it is worth in one sentence: the level, the figure a month, what it comes from, and what waiting costs; or why there is no figure."""
    if saving.monthly is None:
        return fmt("No figure. {why}", why=saving.why_none)
    waiting = fmt(" Waiting costs about {amount} a day.", amount=usd_text(saving.waiting_per_day)) if saving.waiting_per_day else Safe("")
    return fmt("{level} saving: about {amount} a month, from {basis}.{waiting}", level=saving.level, amount=usd_text(saving.monthly), basis=saving.basis, waiting=waiting)


def _when_line(ctx: Ctx, brief: Brief) -> Safe:
    """Found how long ago, and until when the request is open: plain facts, with no countdown."""
    _, ago = ago_text(ctx.now, brief.found_at)
    found = fmt("Found {ago}.", ago=ago) if ago else Safe("")
    until = fmt(" Open until {when}.", when=ctx.when(brief.expires_at)) if brief.state == "open" and brief.expires_at else Safe("")
    return fmt("{found}{until}", found=found, until=until) if (ago or until) else Safe("")


def _outcome(ctx: Ctx, brief: Brief) -> Safe:
    """What became of a request that is not open any more: said once, at the top, in plain lines."""
    outcome = brief.outcome
    if not outcome.state:
        return Safe("")
    kind = {"expired": "warning", "failed": "error", "done": "success", "verified": "success"}.get(outcome.state, "info")
    when = paragraph(ctx.when(outcome.at)) if outcome.at else Safe("")
    return notice(kind, outcome.title, join(paragraph(line) for line in outcome.lines), when)


def _unread(brief: Brief) -> Safe:
    """The data that a workspace takes in and nothing reads: the method in one sentence, then a typed line for each kind of data, the largest first, and what was not counted."""
    unread = brief.unread
    if unread is None:
        return Safe("")
    lines = [fmt("<strong>{kind}</strong>: {gb} in {days}, {percent} of what is billed. {reads}.", kind=line.kind, gb=line.gb, days=unread.days, percent=line.percent, reads=line.reads)
             for line in unread.lines]
    parts: list[object] = [Safe("<h3>Data that nothing reads</h3>"), paragraph(f"{unread.sentence} {unread.volume}"), items(lines)]
    if unread.more:
        parts.append(paragraph(f"{unread.more} more kind{'' if unread.more == 1 else 's'} of data that nothing reads {'is' if unread.more == 1 else 'are'} not listed.", "muted"))
    if unread.note:
        parts.append(paragraph(unread.note, "muted"))
    return join(block(part) for part in parts)


def _evidence(brief: Brief) -> Safe:
    rows = [(fact.label, fmt('{value}<br><span class="muted">{source}</span>', value=fact.value, source=fact.source)) for fact in brief.facts]
    parts: list[object] = [Safe("<h2>Evidence</h2>"), paragraph(fmt("<strong>How sure: {level}.</strong> {because}", level=brief.confidence.level, because=brief.confidence.because))]
    parts += [paragraph(line) for line in (brief.past, brief.access) if line]  # how past requests like this were answered, and what the access cannot see when that matters
    parts.append(summary(rows) if rows else paragraph("No fact is recorded for this case."))
    parts.append(_unread(brief))
    if brief.reasoning:
        parts.append(quoted("The AI's reasoning (not checked by code)", brief.reasoning))
    if brief.doubt:
        parts.append(quoted("The second AI's doubt", brief.doubt))
    return join(block(part) for part in parts)


def _options(brief: Brief) -> Safe:
    """What a person could do about the finding, in the words that code wrote, each with what it loses or puts at risk. Nothing here changes anything: the section says so."""
    if not brief.options:
        return Safe("")
    rows = [fmt('<li>{what} <span class="muted">At risk: {risk}</span></li>', what=option.what, risk=option.risk) for option in brief.options]
    return join([Safe("<h2>What you could do</h2>"), fmt("<ol>{rows}</ol>", rows=join(rows)), paragraph(OPTIONS_END)])


def _if_you_say_yes(brief: Brief) -> Safe:
    if brief.kind == "info":
        return join([Safe("<h2>What changes</h2>"), paragraph(brief.change)])
    rows: list[tuple[str, object]] = [("What changes", brief.change), ("Who does it", brief.who_acts)]
    if brief.rechecked:
        rows.append(("Checked again", brief.rechecked))
    rows.append(("Undo", Safe('<strong>This cannot be undone.</strong>') if not brief.undo.reversible else brief.undo.how))
    rows.append(("What could go wrong", fmt("{text} Risk: {level}.", text=brief.risk.text, level=brief.risk.level)))
    if brief.two_people:
        rows.append(("Who approves", "Two people approve this, each on their own."))
    return join([Safe("<h2>If you approve</h2>" if brief.kind == "change" else "<h2>If you answer</h2>"), summary(rows)])


def _whose(brief: Brief) -> Safe:
    place = fmt("{kind} {name}, resource group {group}, subscription {sub}.", kind=brief.where.kind, name=brief.where.name, group=brief.where.group, sub=brief.where.subscription)
    portal = paragraph(fmt('<a href="{href}" rel="noopener">Open in the Azure portal</a>', href=brief.where.portal_url)) if brief.where.portal_url else Safe("")
    return join([Safe("<h2>Whose is it</h2>"), paragraph(brief.owner.text), paragraph(place), portal])


# -- the answer ----------------------------------------------------------------------------------------------------------------------------------

def answer_form(ctx: Ctx, plan: PlanRecord, brief: Brief, values: dict[str, str], errors: dict[str, str]) -> Safe:
    """The one form of the page: one text box (a question, an objection or something to remember), the reason of a decline, and a button for each answer that exists now. The
    plan code and a one-time token are hidden fields. When a switch holds the answer that approves, the form says so and leaves that button out."""
    end = parse_time(plan.expires_at)
    seconds = int((end - ctx.now).total_seconds()) if end else 0
    ttl = max(900, min(86400, seconds))
    labels = words.ANSWER_LABEL[brief.kind]
    primary = [button(labels[name], name="decision", value=name, kind="primary" if name == "approve" else "secondary") for name in ("approve", "decline") if name in brief.answers]
    other = [button(labels[name], name="decision", value=name, kind="secondary") for name in ("not_mine", "ask", "later") if name in brief.answers]
    fields = [
        textarea("note", "note", "A question, an objection or something to remember", values.get("note", ""),
                 hint=f"Optional, up to {MAX_NOTE} characters. \"Ask or tell\" needs it. It is recorded with your name, Meternaut does not answer yet, and it approves nothing.",
                 error=errors.get("note", ""), maxlength=MAX_NOTE),
        select("reason", "reason", "Why decline, if you do", words.DECLINE_REASON, values.get("reason", ""), error=errors.get("reason", "")),
    ]
    rows = [fmt('<div class="actions">{b}</div>', b=join(row)) for row in (primary, other) if row]
    if "approve" in brief.answers:
        held = Safe("")
    elif brief.kind == "advice":
        held = notice("warning", "Meternaut is paused", PAUSED_ADVICE, "You can still say that it is not worth it, ask or tell, say that this is not yours, or decide later.")
    else:
        held = notice("warning", "Changes are paused", PAUSED_CHANGES, "You can still decline, ask or tell, say that this is not yours, or decide later.")
    return join([held, form(ctx.url(f"/ok/{link_part(plan.plan_id)}"), hidden("code", plan.code), hidden("nonce", ctx.nonce(plan.plan_id, ttl)), *fields, *rows)])


def _own_answers(ctx: Ctx, decisions: list[DecisionRecord]) -> Safe:
    """What this person said before, shown to them alone: a question that is still open, or "later"."""
    mine = [d for d in decisions if d.approver_oid.lower() == ctx.principal.oid]  # type: ignore[union-attr]
    asked = next((d for d in mine if d.decision == "ask" and d.note), None)
    later = any(d.decision == "later" for d in mine)
    parts: list[object] = []
    if asked is not None:
        parts.append(quoted("Your earlier question", asked.note))
    if later:
        parts.append(paragraph("You chose to decide later. Nothing has changed."))
    return join(block(part) for part in parts)


# -- the details ---------------------------------------------------------------------------------------------------------------------------------

def _fact(value: object) -> Safe:
    if isinstance(value, bool):
        return esc("yes" if value else "no")
    if value is None:
        return esc("not known")
    if isinstance(value, (list, tuple)):
        return join((_fact(item) for item in value), ", ")
    if isinstance(value, dict):
        return code(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)[:500])
    return esc(value)


def _model(case: CaseRecord, role: str) -> str:
    models = case.models if isinstance(case.models, dict) else {}
    return str(models.get(role) or "")


def _steps(case: CaseRecord) -> Safe:
    rows = []
    for step in case.steps:
        step = step if isinstance(step, dict) else {}
        ok = step.get("ok")
        rows.append([code(step.get("step") or ""), step.get("model") or "none", number(step.get("promptTokens")) or "none", number(step.get("completionTokens")) or "none",
                     number(step.get("ms")) or "none", "ok" if ok is True else "not ok" if ok is False else "not known", step.get("note") or ""])
    return table("steps", "Every step of the case", STEP_HEADERS, rows) if rows else paragraph("No step is recorded for this case.")


def _ai_words(case: CaseRecord) -> Safe:
    """Both AIs' words in full, marked as written by AI. A case that ended in an error has no AI text: its summary is the reason that it ended."""
    if case.status == "error":
        return join([Safe("<h3>Why the case ended</h3>"), quoted("Recorded by Meternaut", case.summary or "No reason is recorded.")])
    investigated = case.detector == INVESTIGATION
    first, second = _model(case, "investigator" if investigated else "detective"), _model(case, "skeptic")
    verdict = summary([("Recommendation", words.recommendation_word(case.recommendation)), ("Confidence of the first AI (0 to 1)", confidence(case.confidence))])
    parts: list[object] = [Safe("<h3>What the AIs wrote, in full</h3>"), paragraph("Written by AI. Treat it as text, not as fact."), verdict,
                           quoted(f"Written by AI (model: {first or 'not recorded'}): summary", case.summary or "No text is recorded.")]
    if second:
        parts += [quoted(f"Written by AI (model: {second}): objection {n}", text) for n, text in enumerate(case.objections, 1)] or [paragraph("The second AI raised no objection.")]
    else:
        parts.append(paragraph("The second AI was not asked."))
    return join(block(part) for part in parts)


def _details(ctx: Ctx, brief: Brief, case: CaseRecord | None, plan: PlanRecord | None, action: ActionRecord | None) -> Safe:
    rows: list[tuple[str, object]] = []
    if case is not None:
        status_word, meaning = words.CASE_STATUS.get(case.status, (case.status, ""))
        run = link(ctx.url(f"/ops/runs?run={link_part(case.run_id)}"), case.run_id) if ctx.principal.has("ops") else code(case.run_id)  # type: ignore[union-attr]
        rows += [("Resource id", code(case.resource_id)), ("Subscription", code(case.subscription_id)), ("Case", code(case.case_id)),
                 ("How it was found", detector_cell(case.detector)), ("Status of the case", f"{status_word}. {meaning}".strip()), ("Run", run),
                 ("First seen", ctx.when(case.first_seen_at)), ("Last updated", ctx.when(case.updated_at)), ("Seen in", "1 run" if case.runs_seen == 1 else f"{case.runs_seen} runs"),
                 ("Resource type", kind_text(case.resource_type))]
    elif plan is not None:
        rows += [("Resource id", code(plan.resource_id)), ("Subscription", code(plan.subscription_id))]
    if plan is not None:
        waiting = action is not None and plan.state == "approved" and action.state == "queued" and action.step_up
        rows += [("Plan code", fmt("{code}. It is a reference, not proof that this page is genuine.", code=code(plan.code))),
                 ("State of the plan", words.WAITING_TEXT if waiting else words.PLAN_STATE.get(plan.state, plan.state)), ("Expires", ctx.when(plan.expires_at))]
    if ctx.services.host:
        rows.append(("Served from", ctx.services.host))
    parts: list[object] = [summary(rows)]
    if case is not None:
        parts.append(_ai_words(case))
        parts += [Safe("<h3>Steps</h3>"), _steps(case)]
        typed = {name: value for name, value in (case.facts if isinstance(case.facts, dict) else {}).items() if name != UNREAD}  # the digest that code made is in the evidence above, and no AI saw it
        parts.append(table("facts", "The typed facts that the AIs saw", ["Fact", "Value"], [[code(name), _fact(value)] for name, value in sorted(typed.items())], row_header=False)
                     if typed else paragraph("No typed fact is recorded for this case."))
        parts.append(join([paragraph("These guards fired. A guard stops a case from becoming a proposal, and no model can lift it."),
                           summary([(guard, words.GUARD.get(guard, "")) for guard in case.guards])]) if case.guards else paragraph("No guard fired."))
    if action is not None:
        parts += [Safe("<h3>What happened to the change</h3>"), action_block(ctx, action)]
    return details("Details", *parts)


# -- the whole page -------------------------------------------------------------------------------------------------------------------------------

def render(ctx: Ctx, brief: Brief, *, case: CaseRecord | None, plan: PlanRecord | None, action: ActionRecord | None, decisions: list[DecisionRecord], answer: Safe | None,
           errors: dict[str, str] | None = None, status: int = 200, why: str = "") -> Response:
    """The page of a brief. `answer` is the form (or None): the caller makes it only for a person who may answer a request that is open."""
    parts: list[object] = [fmt("<h1>{headline}</h1>", headline=brief.headline), paragraph(saving_sentence(brief.saving), "lead")]
    meta = _when_line(ctx, brief)
    if meta:
        parts.append(paragraph(meta, "muted"))
    if errors:
        parts.append(error_summary(list(errors.items())))
    parts += [_outcome(ctx, brief), _evidence(brief), _options(brief), _if_you_say_yes(brief), _whose(brief)]
    if answer is not None:
        parts += [Safe("<h2>Your answer</h2>"), _own_answers(ctx, decisions), answer]
    elif brief.state == "open" and plan is not None:
        parts += [Safe("<h2>Your answer</h2>"), paragraph("Only the people who are named for this request can answer it.")]
    parts.append(_details(ctx, brief, case, plan, action))
    return page(ctx, brief.headline, join(block(p) for p in parts), status=status, ai=True, models=brief.models or None, why=why or "you opened a request that Meternaut made")
