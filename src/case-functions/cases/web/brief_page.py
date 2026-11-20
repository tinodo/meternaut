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

from ..brief import ADVISOR_KEY, CHANGE, COULD_NOT_LOOK, GUID, HEADS_UP, IF_ACTED, IMPACT, IMPACT_VERDICTS, IN_PLACE, LOOKS_AGAIN, NOT_MADE_BEFORE, NOT_NOW_NEXT, NOT_NOW_TITLE, OPTIONS_END, PAUSED_ADVICE, PAUSED_CHANGES, TWO_PEOPLE, ago_text, group_things, not_now_reason, plan_headline, taken_back, text_of, times_text, waited_text, why_a_person, ways_sentences, Brief
from ..models import ADVISE, GROUP_FACT, HELD, READY, REFUSED, UNKNOWN, ActionRecord, CaseRecord, DecisionRecord, PlanRecord
from . import words
from .common import action_block, confidence, detector_cell, kind_text, off_notice, read
from .core import MAX_NOTE, Ctx, Response, Safe, esc, fmt, join, link_part, number
from .figures import Figure, chart, chip, cost_of, dollars, figure_for, risk_chip, says, series_of, series_reason, short_title, title_of, under, use_block, waiting_words
from .layout import block, button, code, details, error_summary, form, hidden, items, link, notice, page, paragraph, quoted, select, summary, table, textarea

INVESTIGATION = "investigation"  # the detector of the cases that the Watch's own investigation opens (cases/investigate.py)
STEP_HEADERS = ["Step", "Model", "Tokens in", "Tokens out", "Milliseconds", "Result", "Note"]
PAUSED = PAUSED_CHANGES
VERDICT_CHIPS = {"safe": ("low", "circle"), "check": ("mid", "triangle"), "keep": ("high", "diamond")}  # the colour and the shape of the verdict of the impact check
UNCHECKED = "Meternaut did not check the wording."  # what the label of a quote of an AI says besides who wrote it


# -- the parts of the page ------------------------------------------------------------------------------------------------------------------------

def _head(ctx: Ctx, brief: Brief, title: Safe) -> Safe:
    """The way back, the title, and one line: what kind of resource and where, and how long ago it was found. No countdown: nothing closes the request but an answer."""
    _, ago = ago_text(ctx.now, brief.found_at)
    place = f"resource group {brief.where.group}" if brief.where.group and brief.group is None else ""
    named = f"subscription {brief.where.subscription_name}" if brief.where.subscription_name and brief.scope != "subscription" and brief.group is None else ""
    bits: list[object] = [bit for bit in (brief.where.kind if brief.group is None else "", place, named, f"found {ago}" if ago else "") if bit]
    if brief.group is not None and ago:
        bits = [f"They were found {ago}."]  # a finding about many resources has no kind or place of its own to put before it
    meta = fmt('<p class="meta">{meta}</p>', meta=join(bits, " · ")) if bits else Safe("")
    back = paragraph(link(ctx.url("/"), "Back to the decisions"))
    return join([back, fmt('<div class="head"><div><h1>{title}</h1>{meta}</div></div>', title=title, meta=meta)])


def _waiting(ctx: Ctx, brief: Brief) -> Safe:
    """What an open request has waited for, with whom it is now, what waiting has cost so far (by code, from the figure of the request) and who was told, in a few sentences. Nothing for a request that
    is not open."""
    waiting = brief.waiting
    if waiting is None:
        return Safe("")
    days = waited_text(waiting.days)
    lines = [f"It has waited {days}, since {waiting.since}, and it is with {waiting.with_whom}.",
             waiting.cost or "Meternaut cannot say what waiting costs, because nobody has worked out a saving.", *waiting.told, *waiting.pending]
    if waiting.put_off:
        lines.append(f"The people who were asked put it off {times_text(waiting.put_off)}.")
    return join([Safe("<h2>Waiting</h2>"), *(paragraph(line) for line in lines), off_notice(ctx)])


def _chips(brief: Brief) -> Safe:
    """Three chips at most, each with a word and a shape: the risk, how sure the AIs are, and what a change leaves behind (or that the answer changes nothing in Azure)."""
    level = brief.confidence.level
    chips = [risk_chip(brief.risk.level, IF_ACTED if brief.risk.acting else ""), chip(f"{level} confidence", "info" if level == "High" else "")]
    if brief.kind == "change":
        chips.append(chip("Can be undone", "low", "circle") if brief.undo.reversible else chip("Cannot be undone", "high", "diamond"))
    elif brief.kind == "advice":
        chips.append(chip("Held back from a request", "mid", "triangle") if brief.hold is not None else chip("Answering changes nothing in Azure"))
    return fmt('<p class="chips">{chips}</p>', chips=join(chips))


def _asked(brief: Brief) -> Safe:
    """What the person is asked, in the words that the card and the letters say (brief.asked), right after the chips: for advice that waits and that this person may answer. A person who may not answer
    is asked nothing, and the page says who may."""
    return paragraph(brief.asked) if brief.asked and brief.answers else Safe("")


def _outcome(ctx: Ctx, brief: Brief) -> Safe:
    """What became of a request that is not open any more: said once, at the top, in plain lines."""
    outcome = brief.outcome
    if not outcome.state:
        return Safe("")
    kind = {"expired": "warning", "failed": "error", "done": "success", "verified": "success"}.get(outcome.state, "info")
    when = paragraph(ctx.moment(outcome.at)) if outcome.at else Safe("")
    return notice(kind, outcome.title, join(paragraph(line) for line in outcome.lines), when)


def _replaced(ctx: Ctx, case: CaseRecord | None, plan: PlanRecord | None) -> Safe:
    """The request that took the place of this one when Meternaut could make the change itself (taken back as `upgraded`): its title, as a link to it. Nothing for any other request."""
    if case is None or plan is None or taken_back(plan, case) != "upgraded" or not case.plan_id or case.plan_id == plan.plan_id:
        return Safe("")
    new, ok = read(lambda: ctx.store.plan_get(case.plan_id), None)
    if new is None or not ok:
        return Safe("")
    return paragraph(join([Safe("The new request is "), link(ctx.url(f"/ok/{new.plan_id}"), short_title(plan_headline(new), new.resource_group)), Safe(".")]))


def _hold(brief: Brief) -> Safe:
    """Why no request was made, at the top of the page of a finding that a guard holds back: the guard's sentence and what it still needs. Nothing asks the person to approve anything here."""
    found = brief.hold
    return notice("info", found.heading, found.why, found.needs) if found is not None else Safe("")


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
    """The one link of the cost box to Cost analysis in the Azure portal, for the scope that the cost is the cost of (made from ids that code has checked, in cases/costs.py). A screen reader
    hears which scope it is."""
    if not brief.cost_url:
        return Safe("")
    return fmt('<p class="m"><a href="{href}" rel="noopener" aria-label="Open in Cost analysis for {scope}">Open in Cost analysis</a></p>', href=brief.cost_url, scope=brief.cost_scope)


def _worked(brief: Brief) -> Safe:
    """The arithmetic under the figure, as a small table in whole amounts that add up (brief.worked_of): what is paid now, what would be paid after the change and what is saved, a month."""
    if not brief.worked:
        return Safe("")
    return table("worked", "What the change does to the cost", ["What", "Now, a month", "After, a month", "Saved, a month"], [list(row) for row in brief.worked], row_header=True, quiet_caption=True)


def _stake(brief: Brief, figure: Figure) -> Safe:
    """What is at stake, in whole sentences (figures.says): the one that opens it, large (green for a saving), the arithmetic of a figure that code worked out as a small table, then what the figure
    rests on (under the words "How Meternaut worked it out" when there is arithmetic) and what waiting costs, what the cost is made of and the estimate when there are any, the heads-up about a
    resource that something that runs by itself changes (when there is one) and the link to Cost analysis."""
    lead, rest = says(brief, figure)
    waiting = waiting_words(brief, figure)
    heads = fmt('<p class="m"><strong>{label}:</strong> {text}</p>', label=HEADS_UP, text=brief.heads_up) if brief.heads_up else Safe("")
    first = fmt('<p class="say{save}">{lead}</p>', save=" save" if figure.state == "save" else "", lead=lead)
    rest = rest if brief.worked else " ".join(part for part in (rest, waiting) if part)  # what waiting costs follows the basis in the same paragraph, unless the basis is the one of the arithmetic
    how = fmt('<p class="figsub">{label}{rest}</p>', label=Safe("<strong>How Meternaut worked it out.</strong> ") if brief.worked else "", rest=rest) if rest else Safe("")
    return join([first, _worked(brief), how, paragraph(waiting, "figsub") if waiting and brief.worked else Safe(""), under(figure), heads, _analysis(brief)])


def consequences(brief: Brief) -> list[tuple[str, object]]:
    """What happens if the person approves a change, as names and values, in the order of a decision: what changes, who does it with whose rights, what is read again right before, what could go
    wrong and whether it can be undone, each in whole sentences. Advice has no such rows: it is one short paragraph (_happens)."""
    if brief.kind == "info":
        return [("What changes", brief.change)]
    rows: list[tuple[str, object]] = [("What changes", brief.change), ("Who does it", brief.who_acts)]
    if brief.rechecked:
        rows.append(("Checked again", brief.rechecked))
    rows += [("What could go wrong", brief.risk.text), ("Undo", Safe("<strong>This cannot be undone.</strong>") if not brief.undo.reversible else brief.undo.how)]
    if brief.second is not None:
        rows.append(("Who approves", brief.second.line))
    elif brief.two_people:
        rows.append(("Who approves", TWO_PEOPLE))
    return rows


def _here(brief: Brief) -> bool:
    """Whether the block "What happens if you answer" of the page is for advice that waits: it then says what a person would do, and what could go wrong."""
    return brief.kind == "advice" and brief.state in ("open", HELD)


def _happens(brief: Brief) -> Safe:
    """What happens if the person answers: for advice that waits, what an answer does for the kind of request that it is (brief.advice_words), who acts, what the AI says that a person could do
    (a quote: Meternaut did not check the wording) and what could go wrong, from the facts of the finding; for a change, the blocks of what changes, who does it, what is read again, what could go wrong
    and whether it can be undone; for a finding with no request, what changes. The heading says what the person is about to do."""
    if brief.kind == "advice":
        if not _here(brief):
            return Safe("")  # nobody can answer it any more: what became of it is said above
        how = [quoted(f"What the AI says you could do. {UNCHECKED}", brief.how)] if brief.how else []
        risk = [fmt("<p><strong>What could go wrong.</strong> {text}</p>", text=brief.risk.text)] if brief.risk.acting else []
        return fmt('<section aria-labelledby="happens-title"><h2 id="happens-title">What happens if you answer</h2>{lines}</section>', lines=join([paragraph(f"{brief.change} {brief.who_acts}"), *how, *risk]))
    heading = ("If you approve" if brief.state == "open" else "What the change is") if brief.kind == "change" else "What changes"
    if brief.ready is not None and brief.ready.state == REFUSED and brief.kind == "change":
        heading = "What the change would do"  # the form has no answer that approves: the card says what the request is, not what an approval would do
    facts = join(fmt("<dt>{name}</dt><dd>{text}</dd>", name=name, text=text) for name, text in consequences(brief))
    return fmt('<section aria-labelledby="happens-title"><h2 id="happens-title">{heading}</h2><dl class="facts">{facts}</dl></section>', heading=heading, facts=facts)


def _others(brief: Brief) -> Safe:
    """The other ways to save that the finding proposes, for information and not to answer: how many the AI named and how each figure was made (worked out from the bill, the AI's estimate, or not
    priced), and a table of what each saves a month, how Azure does it when that is known and what it gives up. The titles, the words about how Azure does it and about what each gives up are the AI's."""
    if not brief.others:
        return Safe("")
    on = f"these {group_things(brief.group)}" if brief.group is not None else f"this {brief.where.noun}"
    rows = [[fmt('{title}<br><span class="muted">{place}</span>', title=other.title, place=IN_PLACE[other.in_place].format(noun=brief.where.noun)) if other.in_place is not None else other.title, _saves(other),
             other.gives_up or "Not said"] for other in brief.others]
    note = "The titles, how Azure would do each and what each gives up are the AI's words, and Meternaut did not check them."
    if any(other.estimate and other.low is not None for other in brief.others):
        note += " A saving that is the AI's estimate rests on a share of the cost that the AI assumed, and Meternaut did not check that share."
    return join([Safe("<h2>Other ways to save here</h2>"), paragraph(ways_sentences(brief.others, on)),
                 table("others", "Other ways to save here", ["Other way", "Saves a month", "What it gives up"], rows, row_header=True, quiet_caption=True),
                 paragraph(note, "m")])


def _saves(other) -> str:
    """What another way (an `Other` of the brief) saves a month, as the page says other figures: a range, one amount, or that nothing priced it. A way whose saving rests on a share that the AI
    assumed says so in the cell."""
    if other.low is None:
        return "Not priced"
    ranged = other.high is not None and other.high > other.low
    figure = f"{dollars(other.low)} to {dollars(other.high)}" if ranged else dollars(other.low)
    if other.estimate:
        return f"about {figure}, the AI's estimate"
    return figure if ranged else f"about {figure}"


def _decision(brief: Brief, case: CaseRecord | None, now: dt.datetime) -> Safe:
    """The card: what the request is worth or costs, in sentences and in charts (the cost of each day, and, for a kind of resource that has one, its use)."""
    figure = _figure_of(brief, case)
    plot = join([chart(series_of(case.cost_series) if case is not None else None, series_reason(brief, case)), use_block([(brief, case)], now)])
    return fmt('<section class="focus" aria-labelledby="decision-title"><div><h2 class="eyebrow" id="decision-title">{heading}</h2>{stake}</div><div>{plot}</div></section>',
               heading="What it is worth" if figure.state == "save" else "What it costs", stake=_stake(brief, figure), plot=plot)


def _advisor(brief: Brief) -> Safe:
    """What Azure Advisor says, in the words of code: the sentence that adds its figures up, one row for each recommendation (at most twelve), the line that counts the rest, and what was not added up."""
    found = brief.advisor
    if found is None:
        return Safe("")
    parts: list[object] = [Safe("<h3>What Azure Advisor says</h3>"), paragraph(found.sentence),
                           table("advisor", "What Azure Advisor recommends", list(found.columns), [list(row) for row in found.rows], row_header=True, quiet_caption=True)]
    parts += [paragraph(found.more, "muted")] if found.more else []
    parts += [paragraph(found.note, "muted")] if found.note else []
    return join(block(part) for part in parts)


def _measured(brief: Brief) -> Safe:
    """What code read from the estate: each fact with its value and the place that it was read, and what Azure Advisor says when it says something."""
    rows = [[fact.label, fact.value, fmt('<span class="muted">{source}</span>', source=fact.source)] for fact in brief.facts]
    parts: list[object] = [Safe("<h2>What was measured</h2>"),
                           table("measured", "What was measured, and where it was read", ["Fact", "Value", "Where it was read"], rows, row_header=True, quiet_caption=True)
                           if rows else paragraph("No fact is recorded for this finding."), _advisor(brief)]
    return join(block(part) for part in parts)


def _why(brief: Brief) -> Safe:
    """What the AI saw, in its own words (a labelled quote for each, which says that Meternaut did not check the wording), and how sure it is and why: the sentences of code, the second AI's doubt in
    its own quote, and how past requests like this were answered. A request that no AI looked at has no quote and says how sure it is, and nothing of an AI. What the AI says that a person could do, and
    what the second AI doubts, are said under "What happens if you answer" when the request waits (_happens), and not again here."""
    here = _here(brief)
    said = [quoted(f"What the AI says. {UNCHECKED}", brief.reasoning)] if brief.reasoning else []
    said += [quoted(f"What the AI says you could do. {UNCHECKED}", brief.how)] if brief.how and not here else []
    parts: list[object] = [Safe("<h2>What the AI saw</h2>"), *said] if said else []
    parts += [Safe("<h2>Why it is not sure</h2>" if brief.confidence.level == "Low" else "<h2>How sure it is</h2>"), paragraph(brief.confidence.because)]
    parts += [paragraph(line) for line in (brief.past, brief.access) if line]  # how past requests like this were answered, and what the access cannot see when that matters
    if brief.doubt and not (here and brief.doubt in brief.risk.text):
        parts.append(quoted("What the second AI doubts.", brief.doubt))
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
    """Whose it is, in sentences (brief.owner: the tag that names an owner, and who made and last changed the resource, with a day and without an id), and the link to the page of the resource in the
    Azure portal when the finding is about one resource. The kind, the name and the place of the resource are in the line under the title."""
    portal = paragraph(fmt('<a href="{href}" rel="noopener">Open in the Azure portal</a>', href=brief.where.portal_url)) if brief.where.portal_url else Safe("")
    return join([Safe("<h2>Whose is it</h2>"), paragraph(brief.owner.text), portal])


# -- the answer ----------------------------------------------------------------------------------------------------------------------------------

def answer_form(ctx: Ctx, plan: PlanRecord, brief: Brief, values: dict[str, str], errors: dict[str, str]) -> Safe:
    """The one form of the page: one text box (a question, an objection or something to remember), the reason of a decline, and a button for each answer that exists now. The
    plan code and a one-time token are hidden fields. When a switch holds the answer that approves, the form says so and leaves that button out."""
    labels = words.ANSWER_LABEL[brief.kind]
    primary = [button(labels[name], name="decision", value=name, kind="primary" if name in ("approve", "confirm") else "secondary")
               for name in ("confirm", "approve", "decline") if name in brief.answers]
    other = [button(labels[name], name="decision", value=name, kind="subtle sm") for name in ("not_mine", "ask", "later") if name in brief.answers]
    fields = [
        textarea("note", "note", "A question, an objection or something to remember", values.get("note", ""),
                 hint=f"You can leave this empty, but \"Ask or tell\" needs it. It can hold up to {MAX_NOTE} characters. Meternaut records it with your name. It approves nothing, and Meternaut does not answer it yet.",
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
    return join([held, form(ctx.url(f"/ok/{link_part(plan.plan_id)}"), hidden("code", plan.code), hidden("nonce", ctx.nonce(plan.plan_id, 86400)), *fields, *rows)])


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
        parts.append(paragraph(fmt("You confirmed this request on {when}. Nothing has changed. A second person has to approve it.", when=ctx.moment(confirmed.at))))
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
        status_word, meaning = words.CLOSED_BY_THE_BILL if case.status == "expired" and taken_back(plan) == "verified" else words.CASE_STATUS.get(case.status, (case.status, ""))
        if case.status == "needs_human":
            meaning = why_a_person(case) or "A person has to look at it."  # only the reasons that are true of this finding, not the glossary of every one
        run = link(ctx.url(f"/ops/runs?run={link_part(case.run_id)}"), case.run_id) if ctx.principal.has("ops") else code(case.run_id)  # type: ignore[union-attr]
        rows += [("Resource id", code(case.resource_id)), ("Subscription id", code(case.subscription_id)), ("Finding id", code(case.case_id)),
                 ("How it was found", detector_cell(case.detector)), ("Where the finding stands", f"{status_word}. {meaning}".strip()), ("Search run", run),
                 ("First found", ctx.when(case.first_seen_at)), ("Last updated", ctx.when(case.updated_at)), ("Found in", "1 search" if case.runs_seen == 1 else f"{case.runs_seen} searches"),
                 ("Resource type", kind_text(case.resource_type))]
        owner = case.owner if isinstance(case.owner, dict) else {}
        for label, key in (("Created by (an application)", "createdBy"), ("Last changed by (an application)", "changedBy")):  # the page says "an application", and keeps the id here
            who = text_of(owner.get(key), 80)
            if GUID.fullmatch(who):
                rows.append((label, code(who.lower())))
    elif plan is not None:
        rows += [("Resource id", code(plan.resource_id)), ("Subscription id", code(plan.subscription_id))]
    if plan is not None:
        waiting = action is not None and plan.state == "approved" and action.state == "queued" and action.step_up
        rows += [("Request code", fmt("{code}. It is a reference, not proof that this page is genuine.", code=code(plan.code))),
                 ("Where the request stands", words.WAITING_TEXT if waiting else words.CLOSED_BY_THE_BILL[1] if taken_back(plan) == "verified" else words.plan_state(plan.state, plan.family == ADVISE)),
                 ("Request made", ctx.when(plan.created_at))]
        if plan.state == HELD:
            rows.append(("Ends", "It ends when nothing holds the finding back any more."))
    if ctx.services.host:
        rows.append(("Served from", ctx.services.host))
    parts: list[object] = [summary(rows)]
    if case is not None:
        by_code = brief.by_code  # Azure Advisor's own recommendation, made into a request by code: no AI looked at it
        parts += [paragraph("No AI looked at this finding. It is Azure Advisor's own recommendation, which Meternaut's code made into a request.")] if by_code else [
            _ai_words(case), Safe("<h3>Steps</h3>"), _steps(case)]
        from ..brief import PROPOSED  # read here and not at the top: the key is kept by cases/proposals.py, which reads more than a page may load when it starts

        typed = {name: value for name, value in (case.facts if isinstance(case.facts, dict) else {}).items() if name not in (GROUP_FACT, IMPACT, ADVISOR_KEY, CHANGE, PROPOSED)}  # what code made of the estate is in the evidence above, and no AI saw it
        parts.append(table("facts", "The typed facts that Meternaut recorded" if by_code else "The typed facts that the AIs saw", ["Fact", "Value"],
                           [[code(name), _fact(value)] for name, value in sorted(typed.items())], row_header=False)
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
    parts += [_asked(brief), _look(brief), _outcome(ctx, brief), _replaced(ctx, case, plan), _hold(brief), _decision(brief, case, ctx.now), _others(brief), _happens(brief), _waiting(ctx, brief)]
    side: Safe | None = None
    if answer is not None:
        side = fmt('<section class="panel" aria-labelledby="answer-title"><h2 id="answer-title">Your answer</h2>{earlier}{answer}</section>', earlier=_own_answers(ctx, decisions), answer=answer)
    elif brief.state == "open" and plan is not None:
        side = fmt('<section class="panel" aria-labelledby="answer-title"><h2 id="answer-title">Your answer</h2><p>Only the people who are named for this request can answer it.</p></section>')
    reading = join(block(part) for part in (_impact(brief), _measured(brief), _options(brief), _check_first(brief), _why(brief), _whose(brief)))
    parts.append(fmt('<div class="cols{solo}"><div>{reading}</div>{side}</div>', solo="" if side is not None else " solo", reading=reading, side=side if side is not None else Safe("")))
    parts.append(_details(ctx, brief, case, plan, action))
    return page(ctx, plain_title, join(block(p) for p in parts), status=status, ai=True, models=() if brief.by_code else brief.models or None,
                why=why or "you opened a request that Meternaut made", wide=True)
