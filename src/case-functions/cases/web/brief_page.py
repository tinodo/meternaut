"""The page of one request or case: the decision brief (brief.py) as a web page, built from the style guide (docs/ui/style-guide.html).

A stranger must be able to answer eight questions from this page in a minute, without opening anything else: what am I asked to decide, what do I get, how sure is it and
on what evidence, what exactly happens if I say yes (who does it, with whose rights), can it be undone, what could go wrong, whose resource is it, and what are my choices.
So the page is the title, what is at stake in figures (a year and a month, with its level and basis, and a chart of the cost, and of the use for a kind of resource that has one) and what
happens if the person says yes, in one card;
then what was measured, why the two AIs think so (in boxes that say they are not checked), whose resource it is, and, beside them on a wide screen, ONE form with the answers
that exist right now. Everything else (the steps, the models, the tokens, the checks, the ids, the log of the change) is in one collapsed Details disclosure at the end.

What came from the estate or from an AI is escaped and set in a labelled quote, never as a link or a control; the one link to the Azure portal is made from a resource id
that code has checked to be the id of one resource.
"""
from __future__ import annotations

import datetime as dt
import json

from ..brief import ACTING, COULD_NOT_LOOK, GATEWAYS, IF_ACTED, IMPACT, IMPACT_VERDICTS, LOOKS_AGAIN, NOT_MADE_BEFORE, NOT_NOW_NEXT, NOT_NOW_TITLE, OPTIONS_END, PAUSED_ADVICE, PAUSED_CHANGES, TWO_PEOPLE, UNREAD, ago_text, not_now_reason, Brief
from ..models import GROUP_FACT, READY, REFUSED, UNKNOWN, ActionRecord, CaseRecord, DecisionRecord, PlanRecord
from . import words
from .common import action_block, confidence, detector_cell, kind_text, read
from .core import MAX_NOTE, Ctx, Response, Safe, esc, fmt, join, link_part, number, parse_time
from .figures import Figure, a_year, chart, chip, cost_of, dollars, figure_for, risk_chip, series_of, series_reason, title_of, under, use_block
from .layout import block, button, code, details, error_summary, form, hidden, items, link, notice, page, paragraph, quoted, select, summary, table, textarea

INVESTIGATION = "investigation"  # the detector of the cases that the Watch's own investigation opens (cases/investigate.py)
STEP_HEADERS = ["Step", "Model", "Tokens in", "Tokens out", "Milliseconds", "Result", "Note"]
PAUSED = PAUSED_CHANGES
MONEY = Safe('<p class="m">Money is in US dollars, and a year is twelve times the month.</p>')
VERDICT_CHIPS = {"safe": ("low", "circle"), "check": ("mid", "triangle"), "keep": ("high", "diamond")}  # the colour and the shape of the verdict of the impact check


# -- the parts of the page ------------------------------------------------------------------------------------------------------------------------

def _head(ctx: Ctx, brief: Brief, title: Safe) -> Safe:
    """The way back, the title, and one line: what kind of resource and where, how long ago it was found, and until when the request is open. No countdown."""
    _, ago = ago_text(ctx.now, brief.found_at)
    place = f"resource group {brief.where.group}" if brief.where.group else ""
    named = f"subscription {brief.where.subscription_name}" if brief.where.subscription_name and brief.scope != "subscription" else ""
    bits: list[object] = [bit for bit in (brief.where.kind, place, named, f"found {ago}" if ago else "") if bit]
    if brief.state == "open" and brief.expires_at:
        bits.append(fmt("open until {when}", when=ctx.when(brief.expires_at)))
    meta = fmt("<p>{meta}</p>", meta=join(bits, " · ")) if bits else Safe("")
    back = paragraph(link(ctx.url("/"), "Back to the decisions"))
    return join([back, fmt('<div class="head"><div><h1>{title}</h1>{meta}</div></div>', title=title, meta=meta)])


def _chips(brief: Brief) -> Safe:
    """Three chips at most, each with a word and a shape: the risk, how sure the AIs are, and what a change leaves behind (or that the answer changes nothing in Azure)."""
    level = brief.confidence.level
    chips = [risk_chip(brief.risk.level, IF_ACTED if brief.risk.text.startswith(ACTING) else ""), chip(f"{level} confidence", "info" if level == "High" else "")]
    if brief.kind == "change":
        chips.append(chip("Can be undone", "low", "circle") if brief.undo.reversible else chip("Cannot be undone", "high", "diamond"))
    elif brief.kind == "advice":
        chips.append(chip("Answering changes nothing in Azure"))
    return fmt('<p class="chips">{chips}</p>', chips=join(chips))


def _outcome(ctx: Ctx, brief: Brief) -> Safe:
    """What became of a request that is not open any more: said once, at the top, in plain lines."""
    outcome = brief.outcome
    if not outcome.state:
        return Safe("")
    kind = {"expired": "warning", "failed": "error", "done": "success", "verified": "success"}.get(outcome.state, "info")
    when = paragraph(ctx.when(outcome.at)) if outcome.at else Safe("")
    return notice(kind, outcome.title, join(paragraph(line) for line in outcome.lines), when)


def _look(brief: Brief) -> Safe:
    """What a look at the resource said, at the top of the page, for a change that waits for an OK: when the checks of the runner would refuse it, a box that says what Meternaut will not do and
    why, in plain words, that nothing was changed and what happens next (the form then has no answer that approves). When the look could not be made, one line says so (Approve stays, because
    the runner looks again with the approver's own rights right before it acts and changes nothing if a check fails), and when the last try of this request was refused before anything was
    written, the reason of that try comes first: the look that is made now cannot say that it is put right. Nothing when the look found nothing in the way."""
    found = brief.ready
    if brief.kind != "change" or brief.state != "open":
        return Safe("")
    noun = brief.where.noun
    if found is not None and found.state == REFUSED:
        return notice("warning", NOT_NOW_TITLE.format(noun=noun), not_now_reason(found.why), NOT_NOW_NEXT)
    if found is not None and found.state == READY:
        return Safe("")
    if found is not None and found.state == UNKNOWN:
        said = COULD_NOT_LOOK.format(noun=noun)
        return notice("warning", NOT_MADE_BEFORE, brief.refused_before, f"{said} {LOOKS_AGAIN}") if brief.refused_before else notice("info", "", f"{said} {LOOKS_AGAIN}")
    return notice("warning", NOT_MADE_BEFORE, brief.refused_before, LOOKS_AGAIN) if brief.refused_before else Safe("")


def _figure_of(brief: Brief, case: CaseRecord | None) -> Figure:
    return figure_for([brief], [cost_of(brief, case)])


def _analysis(brief: Brief) -> Safe:
    """The one link of the cost box to Cost analysis in the Azure portal, for the scope that the cost is the cost of (made from ids that code has checked, in cases/costs.py)."""
    if not brief.cost_url:
        return Safe("")
    return fmt('<p class="m"><a href="{href}" rel="noopener">Open in Cost analysis</a> <span class="muted">for {scope}</span></p>', href=brief.cost_url, scope=brief.cost_scope)


def _stake(brief: Brief, figure: Figure) -> Safe:
    """What is at stake: the figure a year, then the figure a month with its level and its basis (or what it costs, and why no saving is shown when the finding has a reason of its own),
    what the cost is made of and the estimate when there are any, what waiting costs, the money that the page is in, once, and the link to Cost analysis."""
    note = figure.note if figure.state == "save" or not brief.saving.specific else brief.saving.why_none
    if figure.monthly is None:
        return fmt('<p class="fig">—</p><p class="figsub">{label}. {note}</p>{under}{money}{link}', label=figure.label, note=note, under=under(figure), money=MONEY, link=_analysis(brief))
    waiting = f" Waiting costs about {dollars(brief.saving.waiting_per_day)} a day." if figure.state == "save" and brief.saving.waiting_per_day else ""
    return fmt('<p class="fig{save}">{year}<small> a year</small></p><p class="figsub">{label}. {month} a month. {note}{waiting}</p>{under}{money}{link}',
               save=" save" if figure.state == "save" else "", year=a_year(figure.monthly), label=figure.label, month=dollars(figure.monthly), note=note, waiting=waiting,
               under=under(figure), money=MONEY, link=_analysis(brief))


def consequences(brief: Brief) -> list[tuple[str, object]]:
    """What happens if the person says yes, as names and values: what changes, who does it with whose rights, what is read again, whether it can be undone and what could go wrong."""
    if brief.kind == "info":
        return [("What changes", brief.change)]
    rows: list[tuple[str, object]] = [("What changes", brief.change), ("Who does it", brief.who_acts)]
    if brief.rechecked:
        rows.append(("Checked again", brief.rechecked))
    rows.append(("Undo", Safe("<strong>This cannot be undone.</strong>") if not brief.undo.reversible else brief.undo.how))
    rows.append(("What could go wrong", fmt("{text} Risk: {level}.", text=brief.risk.text, level=brief.risk.level)))
    if brief.second is not None:
        rows.append(("Who approves", brief.second.line))
    elif brief.two_people:
        rows.append(("Who approves", TWO_PEOPLE))
    return rows


def _decision(brief: Brief, case: CaseRecord | None, now: dt.datetime) -> Safe:
    """The card: what is at stake in figures and in charts (the cost of each day, and, for a kind of resource that has one, its use), and what happens if the person says yes. The heading says
    what the person is about to do."""
    figure = _figure_of(brief, case)
    heading = {"change": "If you approve", "advice": "If you answer"}.get(brief.kind, "What changes")
    if brief.ready is not None and brief.ready.state == REFUSED and brief.kind == "change":
        heading = "What the change would do"  # the form has no answer that approves: the card says what the request is, not what an approval would do
    facts = join(fmt("<dt>{name}</dt><dd>{text}</dd>", name=name, text=text) for name, text in consequences(brief))
    plot = join([chart(series_of(case.cost_series) if case is not None else None, series_reason(brief, case)), use_block([(brief, case)], now)])
    return fmt('<section class="focus" aria-labelledby="decision-title"><div><h2 class="eyebrow" id="decision-title">{heading}</h2>{stake}</div><div>{plot}</div><dl class="facts">{facts}</dl></section>',
               heading=heading, stake=_stake(brief, figure), facts=facts, plot=plot)


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


def _gateways(brief: Brief) -> Safe:
    """What a finding about point-to-site gateways says, in the words of code: what these gateways are, then what was found in figures, and what was not counted."""
    found = brief.gateways
    if found is None:
        return Safe("")
    parts: list[object] = [Safe("<h3>The gateways</h3>"), paragraph(found.what), paragraph(found.sentence)]
    if found.note:
        parts.append(paragraph(found.note, "muted"))
    return join(block(part) for part in parts)


def _measured(brief: Brief) -> Safe:
    """What code read from the estate: each fact with its value and the place that it was read, the data that nothing reads when the finding is about a workspace, and what the gateways are
    when it is about those."""
    rows = [[fact.label, fact.value, fmt('<span class="muted">{source}</span>', source=fact.source)] for fact in brief.facts]
    parts: list[object] = [Safe("<h2>What was measured</h2>"),
                           table("measured", "What was measured, and where it was read", ["Fact", "Value", "Where it was read"], rows, row_header=True, quiet_caption=True)
                           if rows else paragraph("No fact is recorded for this finding."), _unread(brief), _gateways(brief)]
    return join(block(part) for part in parts)


def _why(brief: Brief) -> Safe:
    """How sure the AIs are and why, in their own words, each in a box that says that no code checked it, and how past requests like this were answered."""
    parts: list[object] = [Safe("<h2>Why the AIs think so</h2>"), paragraph(fmt("<strong>How sure: {level}.</strong> {because}", level=brief.confidence.level, because=brief.confidence.because))]
    parts += [paragraph(line, "muted") for line in (brief.past, brief.access) if line]  # how past requests like this were answered, and what the access cannot see when that matters
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


def _impact(brief: Brief) -> Safe:
    """What removing the resource would do (cases/impact.py): the verdict that code derived from the facts, its reasons, what was read and where it was read, what happens to traffic and DNS, how
    to undo it, and what was not checked. No AI writes any of it. A finding whose kind of resource has no check says in one line that nothing was analysed."""
    found = brief.impact
    if found is None:
        return Safe("")
    if not found.verdict:
        return join([Safe("<h2>Impact</h2>"), paragraph(found.line)])
    rows = [[name, value, fmt('<span class="muted">{source}</span>', source=source)] for name, value, source in found.rows]
    parts: list[object] = [Safe("<h2>Impact</h2>"), paragraph(chip(IMPACT_VERDICTS[found.verdict], *VERDICT_CHIPS[found.verdict])), paragraph(found.read, "muted"), items(found.reasons)]
    parts += [table("impact", "What was read, and where it was read", ["Fact", "Value", "Where it was read"], rows, row_header=True, quiet_caption=True)] if rows else []
    parts += [Safe("<h3>If it is removed</h3>"), items(found.removal)] if found.removal else []
    parts += [Safe("<h3>How to undo it</h3>"), paragraph(found.undo)] if found.undo else []
    parts += [paragraph(found.unchecked, "muted")] if found.unchecked else []
    return join(block(part) for part in parts)


def _check_first(brief: Brief) -> Safe:
    """What to check before acting on advice about a resource that others share, or that may not be used any more: what it connects to, who owns it and its traffic, in the words of code."""
    if not brief.check_first:
        return Safe("")
    return join([Safe("<h2>Check first</h2>"), fmt("<ol>{rows}</ol>", rows=join(fmt("<li>{text}</li>", text=line) for line in brief.check_first))])


def _whose(brief: Brief) -> Safe:
    """Whose it is: the kind and the name of what the finding is about, where it is (the resource group, and the subscription by its name: the start of its id when the name was not read), and the
    link to the page of the resource in the Azure portal when the finding is about one resource."""
    where = brief.where
    sub = where.subscription_name or where.subscription
    if brief.scope == "subscription":
        place = fmt("{kind} {name}.", kind=where.kind, name=where.name if where.subscription_name else where.subscription)
    elif brief.scope == "group":
        place = fmt("{kind} {name}, subscription {sub}.", kind=where.kind, name=where.name, sub=sub)
    else:
        place = fmt("{kind} {name}, resource group {group}, subscription {sub}.", kind=where.kind, name=where.name, group=where.group, sub=sub)
    portal = paragraph(fmt('<a href="{href}" rel="noopener">Open in the Azure portal</a>', href=where.portal_url)) if where.portal_url else Safe("")
    return join([Safe("<h2>Whose is it</h2>"), paragraph(brief.owner.text), paragraph(place), portal])


# -- the answer ----------------------------------------------------------------------------------------------------------------------------------

def answer_form(ctx: Ctx, plan: PlanRecord, brief: Brief, values: dict[str, str], errors: dict[str, str]) -> Safe:
    """The one form of the page: one text box (a question, an objection or something to remember), the reason of a decline, and a button for each answer that exists now. The
    plan code and a one-time token are hidden fields. When a switch holds the answer that approves, the form says so and leaves that button out."""
    end = parse_time(plan.expires_at)
    seconds = int((end - ctx.now).total_seconds()) if end else 0
    ttl = max(900, min(86400, seconds))
    labels = words.ANSWER_LABEL[brief.kind]
    primary = [button(labels[name], name="decision", value=name, kind="primary" if name in ("approve", "confirm") else "secondary")
               for name in ("confirm", "approve", "decline") if name in brief.answers]
    other = [button(labels[name], name="decision", value=name, kind="subtle sm") for name in ("not_mine", "ask", "later") if name in brief.answers]
    fields = [
        textarea("note", "note", "A question, an objection or something to remember", values.get("note", ""),
                 hint=f"Optional, up to {MAX_NOTE} characters. \"Ask or tell\" needs it. It is recorded with your name, Meternaut does not answer yet, and it approves nothing.",
                 error=errors.get("note", ""), maxlength=MAX_NOTE),
        select("reason", "reason", "Why decline, if you do", words.DECLINE_REASON, values.get("reason", ""), error=errors.get("reason", "")),
    ]
    rows = [fmt('<div class="acts{stack}">{b}</div>', stack=" stack" if row is primary else "", b=join(row)) for row in (primary, other) if row]
    if not brief.held:
        held = Safe("")
    elif brief.kind == "advice":
        held = notice("warning", "Meternaut is paused", PAUSED_ADVICE, "You can still say that it is not worth it, ask or tell, say that this is not yours, or decide later.")
    else:
        held = notice("warning", "Changes are paused", PAUSED_CHANGES, "You can still decline, ask or tell, say that this is not yours, or decide later.")
    return join([held, form(ctx.url(f"/ok/{link_part(plan.plan_id)}"), hidden("code", plan.code), hidden("nonce", ctx.nonce(plan.plan_id, ttl)), *fields, *rows)])


def _own_answers(ctx: Ctx, decisions: list[DecisionRecord]) -> Safe:
    """What this person said before, shown to them alone: a question that is still open, "later", or the confirmation of a plan that waits for a second person."""
    mine = [d for d in decisions if d.approver_oid.lower() == ctx.principal.oid]  # type: ignore[union-attr]
    asked = next((d for d in mine if d.decision == "ask" and d.note), None)
    later = any(d.decision == "later" for d in mine)
    confirmed = next((d for d in mine if d.decision == "confirm"), None)
    parts: list[object] = []
    if asked is not None:
        parts.append(quoted("Your earlier question", asked.note))
    if later:
        parts.append(paragraph("You chose to decide later. Nothing has changed."))
    if confirmed is not None:
        parts.append(paragraph(fmt("You confirmed this request on {when}. Nothing has changed: a second person has to approve it.", when=ctx.when(confirmed.at))))
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
    return table("steps", "Every step of the finding", STEP_HEADERS, rows) if rows else paragraph("No step is recorded for this finding.")


def _ai_words(case: CaseRecord) -> Safe:
    """Both AIs' words in full, marked as written by AI. A case that ended in an error has no AI text: its summary is the reason that it ended."""
    if case.status == "error":
        return join([Safe("<h3>Why the finding ended</h3>"), quoted("Recorded by Meternaut", case.summary or "No reason is recorded.")])
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
        rows += [("Resource id", code(case.resource_id)), ("Subscription", code(case.subscription_id)), ("Finding", code(case.case_id)),
                 ("How it was found", detector_cell(case.detector)), ("Status of the finding", f"{status_word}. {meaning}".strip()), ("Run", run),
                 ("First seen", ctx.when(case.first_seen_at)), ("Last updated", ctx.when(case.updated_at)), ("Seen in", "1 run" if case.runs_seen == 1 else f"{case.runs_seen} runs"),
                 ("Resource type", kind_text(case.resource_type))]
    elif plan is not None:
        rows += [("Resource id", code(plan.resource_id)), ("Subscription", code(plan.subscription_id))]
    if plan is not None:
        waiting = action is not None and plan.state == "approved" and action.state == "queued" and action.step_up
        rows += [("Request code", fmt("{code}. It is a reference, not proof that this page is genuine.", code=code(plan.code))),
                 ("State of the request", words.WAITING_TEXT if waiting else words.PLAN_STATE.get(plan.state, plan.state)), ("Expires", ctx.when(plan.expires_at))]
    if ctx.services.host:
        rows.append(("Served from", ctx.services.host))
    parts: list[object] = [summary(rows)]
    if case is not None:
        parts.append(_ai_words(case))
        parts += [Safe("<h3>Steps</h3>"), _steps(case)]
        typed = {name: value for name, value in (case.facts if isinstance(case.facts, dict) else {}).items() if name not in (UNREAD, GROUP_FACT, GATEWAYS, IMPACT)}  # what code made of the estate is in the evidence above, and no AI saw it
        parts.append(table("facts", "The typed facts that the AIs saw", ["Fact", "Value"], [[code(name), _fact(value)] for name, value in sorted(typed.items())], row_header=False)
                     if typed else paragraph("No typed fact is recorded for this finding."))
        parts.append(join([paragraph("These guards fired. A guard stops a finding from becoming a request, and no model can lift it."),
                           summary([(guard, words.GUARD.get(guard, "")) for guard in case.guards])]) if case.guards else paragraph("No guard fired."))
    if action is not None:
        parts += [Safe("<h3>What happened to the change</h3>"), action_block(ctx, action)]
    return details("Details", *parts)


# -- the whole page -------------------------------------------------------------------------------------------------------------------------------

def render(ctx: Ctx, brief: Brief, *, case: CaseRecord | None, plan: PlanRecord | None, action: ActionRecord | None, decisions: list[DecisionRecord], answer: Safe | None,
           errors: dict[str, str] | None = None, status: int = 200, why: str = "", banner: Safe | None = None) -> Response:
    """The page of a brief. `answer` is the form (or None): the caller makes it only for a person who may answer a request that is open. `banner` is one box under the title, for a person
    who is going through their requests one by one. On a wide screen the answer stands beside what was measured and why; on a narrow one it follows them."""
    title, plain_title = title_of(brief)
    parts: list[object] = [_head(ctx, brief, title), _chips(brief)]
    if banner is not None:
        parts.append(banner)
    if errors:
        parts.append(error_summary(list(errors.items())))
    parts += [_look(brief), _outcome(ctx, brief), _decision(brief, case, ctx.now)]
    side: Safe | None = None
    if answer is not None:
        side = fmt('<section class="panel" aria-labelledby="answer-title"><h2 id="answer-title">Your answer</h2>{earlier}{answer}</section>', earlier=_own_answers(ctx, decisions), answer=answer)
    elif brief.state == "open" and plan is not None:
        side = fmt('<section class="panel" aria-labelledby="answer-title"><h2 id="answer-title">Your answer</h2><p>Only the people who are named for this request can answer it.</p></section>')
    reading = join(block(part) for part in (_impact(brief), _measured(brief), _options(brief), _check_first(brief), _why(brief), _whose(brief)))
    parts.append(fmt('<div class="cols{solo}"><div>{reading}</div>{side}</div>', solo="" if side is not None else " solo", reading=reading, side=side if side is not None else Safe("")))
    parts.append(_details(ctx, brief, case, plan, action))
    return page(ctx, plain_title, join(block(p) for p in parts), status=status, ai=True, models=brief.models or None, why=why or "you opened a request that Meternaut made", wide=True)
