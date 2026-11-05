"""The approval page and what happens when a person answers it.

The page shows the plan from the stored plan record and never the models' prose. An answer is a POST with the plan code and a one-time token; the decider
checks the token, the code, the state, the switches and the expiry, and each kind of its result has a plain page of its own.
"""
from __future__ import annotations

from ..models import DecideResult, PlanRecord
from . import words
from .common import action_block, effective_state, may_answer, pulled, read, start_block
from .core import MAX_NOTE, Ctx, Response, Safe, clean_line, fmt, join, link_part, parse_time, usd
from .layout import block, button, code, error_summary, form, hidden, link, message_page, notice, page, paragraph, summary, textarea

REFUSED_ROLE = "I cannot take your OK on this request."
PAUSED = "Changes are paused here. Nothing has changed, and your OK cannot be recorded now."
CHANGED = "This plan changed. Nothing is approved. A new message will bring the new plan and code."
STATUS = {"recorded": 200, "declined": 200, "asked": 200, "not_mine": 200, "withdrawn": 200, "refused_code": 409, "refused_state": 409, "refused_role": 403,
          "refused_paused": 409, "expired": 410, "duplicate": 409, "error": 500}
WHY = "You answered a request on this console."


def _base(ctx: Ctx, plan_id: str) -> str:
    return ctx.url(f"/ok/{link_part(plan_id)}")


def _refused_role(ctx: Ctx) -> Response:
    return message_page(ctx, 403, REFUSED_ROLE, "Nothing is approved. If this request should be yours, use Talk to a person below.", back=("/", "Back to the start page"),
                        ai=True, why="You opened a request that is not yours to answer.")


def _not_found(ctx: Ctx) -> Response:
    return message_page(ctx, 404, "I cannot find this request", "No request has this address. Nothing has changed.", back=("/", "Back to the start page"), ai=True,
                        why="You opened an address that holds no request.")


def _gate(ctx: Ctx, plan_id: str) -> tuple[PlanRecord | None, Response | None]:
    """Who may see and answer a plan: a person with the role approver who is named in the plan. Nobody else sees its details."""
    if not ctx.principal.has("approver"):  # type: ignore[union-attr]
        return None, _refused_role(ctx)
    plan = ctx.store.plan_get(plan_id)
    if plan is None:
        return None, _not_found(ctx)
    if not may_answer(ctx.principal, plan):  # type: ignore[arg-type]
        return None, _refused_role(ctx)
    return plan, None


# -- the page ------------------------------------------------------------------------------------------------------------------------------------

def _what_you_approve(plan: PlanRecord) -> Safe:
    if plan.family in words.FAMILY:
        change, noun = words.FAMILY[plan.family]
        return fmt('{change}: the {noun} named "{name}" in resource group "{group}".', change=change, noun=noun, name=plan.resource_name, group=plan.resource_group)
    return fmt("{title}", title=plan.title)


def _cannot_be_undone(plan: PlanRecord) -> bool:
    return plan.family.startswith("delete") or not plan.undo.strip()


def _warning() -> Safe:
    return Safe('<p class="warning-text"><span class="sign" aria-hidden="true">!</span><strong><span class="visually-hidden">Warning: </span>'
                "This change cannot be undone.</strong></p>")


def _details(ctx: Ctx, plan: PlanRecord) -> Safe:
    undo = join([_warning() if _cannot_be_undone(plan) else Safe(""), paragraph(plan.undo or "No way to undo this change is recorded.")])
    return summary([
        ("What changes", plan.what_changes),
        ("Resource", fmt('{name}, in resource group {group}<br><span class="muted">Resource id: {rid}</span>', name=plan.resource_name, group=plan.resource_group,
                          rid=code(plan.resource_id))),
        ("Who makes the change", fmt("The runner, the part of Meternaut that changes Azure. It may only {writer}.", writer=ctx.services.writer)),
        ("Estimated saving a month", paragraph(fmt("About {amount}. This is an estimate from cost lines of the last 30 days.", amount=usd(plan.saving_usd_month)))
         if plan.saving_usd_month is not None else paragraph("No figure. No cost lines of the last 30 days back an estimate.")),
        ("What waiting costs a day", paragraph(fmt("About {amount} for each day that the resource stays as it is. This is an estimate.", amount=usd(plan.waiting_costs_usd_day)))
         if plan.waiting_costs_usd_day is not None else paragraph("No figure.")),
        ("What could go wrong", plan.could_go_wrong),
        ("How to undo it", undo),
        ("Evidence", join([paragraph(plan.evidence_level), paragraph(link(ctx.url(f"/why/{link_part(plan.case_id)}"), "Open the notebook for this case"))])),
    ])


def _check(ctx: Ctx, plan: PlanRecord) -> Safe:
    """The decision restated in three lines."""
    lines = [
        fmt("You approve: {what}", what=_what_you_approve(plan)),
        fmt("Undo: {undo}", undo="It cannot be undone." if _cannot_be_undone(plan) else plan.undo),
        fmt("Your OK covers this plan only: code {code}. Answer by {when}.", code=plan.code, when=ctx.when(plan.expires_at)),
    ]
    return fmt('<section class="check" aria-labelledby="check-title"><h2 id="check-title">Check before you approve</h2><ol>{lines}</ol></section>',
               lines=join(fmt("<li>{line}</li>", line=line) for line in lines))


def _forms(ctx: Ctx, plan: PlanRecord, paused: bool, values: dict[str, str], errors: dict[str, str]) -> Safe:
    base = _base(ctx, plan.plan_id)
    end = parse_time(plan.expires_at)
    seconds = int((end - ctx.now).total_seconds()) if end else 0
    ttl = max(900, min(86400, seconds))
    approve = Safe("") if paused else button("Approve this exact change", name="decision", value="approve", kind="primary")
    answer = form(base, hidden("code", plan.code), hidden("nonce", ctx.nonce(plan.plan_id, ttl)),
                  textarea("note", "note", "Note (optional)", values.get("note", ""), hint=f"Up to {MAX_NOTE} characters. It is kept with your answer.", error=errors.get("note", ""),
                           maxlength=MAX_NOTE),
                  fmt('<div class="actions">{approve}{decline}</div>', approve=approve, decline=button("Decline", name="decision", value="decline", kind="secondary")))
    ask = form(f"{base}/ask", hidden("code", plan.code), hidden("nonce", ctx.nonce(plan.plan_id, ttl)),
               textarea("ask-note", "note", "Your question, or another way to do it", values.get("ask-note", ""),
                        hint=f"Up to {MAX_NOTE} characters. This approves nothing. It is kept as text and never as an instruction.", error=errors.get("ask-note", ""),
                        maxlength=MAX_NOTE),
               fmt('<div class="actions">{b}</div>', b=button("Send the question or suggestion", kind="secondary")))
    mine = form(f"{base}/not-mine", hidden("code", plan.code), hidden("nonce", ctx.nonce(plan.plan_id, ttl)),
                fmt('<div class="actions">{b}</div>', b=button("This is not mine", kind="secondary")))
    return join([
        fmt("<h2>Your answer</h2>{note}{answer}", note=paragraph("Approve or decline. Declining closes the request and nothing changes.") if not paused else
            notice("warning", "Changes are paused", PAUSED, "You can still decline, ask a question, or say that this is not yours."), answer=answer),
        fmt("<h2>Ask or suggest</h2>{ask}", ask=ask),
        fmt("<h2>Not mine</h2>{p}{mine}", p=paragraph("Nothing is approved. The request goes back to finding the right owner."), mine=mine),
    ])


def _state_notice(ctx: Ctx, plan: PlanRecord, state: str, mine: list, action) -> Safe:
    if state == "open":
        return Safe("")
    when = ctx.when(plan.expires_at)
    if state == "expired":
        return notice("warning", "Expired", paragraph(fmt("This request expired on {when}. Nothing has changed.", when=when)))
    if state == "approved":
        recorded = next((d for d in mine if d.decision == "approve"), None)
        sentence = (paragraph(fmt("Your OK is recorded since {at}. Nothing has changed yet.", at=ctx.when(recorded.at))) if recorded
                    else paragraph("This plan is approved. It waits for the runner. Nothing has changed yet."))
        return notice("info", "Approved", sentence, start_block(ctx, plan, action, bool(recorded)))
    if state == "declined":
        return notice("info", "Declined", "This request was declined. Nothing has changed.")
    if state == "withdrawn":
        return notice("info", "Withdrawn", "This request was withdrawn. Nothing has changed.")
    if state == "consumed":
        return notice("info", "Used", "The runner took this plan. A plan runs once. What it did is below.")
    if state == "failed":
        return notice("error", "Failed", "The runner could not finish the change. What it did is below.")
    return notice("info", words.PLAN_STATE.get(state, state))


def render_plan(ctx: Ctx, plan: PlanRecord, *, values: dict[str, str] | None = None, errors: dict[str, str] | None = None, status: int = 200) -> Response:
    """The approval page. Forms appear only while the plan is open; the approve button is left out while changes are paused."""
    values, errors = values or {}, errors or {}
    state = effective_state(ctx, plan)
    decisions, _ = read(lambda: ctx.store.decisions_of_plan(plan.plan_id), [])
    mine = [d for d in decisions if d.approver_oid.lower() == ctx.principal.oid]  # type: ignore[union-attr]
    action, _ = read(lambda: ctx.store.action_get(plan.plan_id), None)
    asked = next((d for d in mine if d.decision == "ask" and d.note), None)
    parts: list[object] = [
        fmt("<h1>{title}</h1>", title=plan.title),
        paragraph("This change needs two people, each on their own." if plan.approval_class == "R3" else "This change needs your OK on this page.", "lead"),
    ]
    if errors:
        parts.append(error_summary(list(errors.items())))
    parts += [_state_notice(ctx, plan, state, mine, action), _details(ctx, plan)]
    if asked is not None:
        parts.append(fmt("<h2>Your earlier question or suggestion</h2>{quote}", quote=fmt('<blockquote class="quote">{note}</blockquote>', note=asked.note)))
    if action is not None and state != "open":
        parts += [Safe("<h2>What the runner did</h2>"), action_block(ctx, action)]
    if state == "open":
        parts += [_check(ctx, plan), _forms(ctx, plan, pulled(ctx, "all", "changes"), values, errors)]
    extra = join([
        fmt("<p><strong>Plan code {code}.</strong> It is a reference, not proof that this page is genuine.</p>", code=plan.code),
        fmt("<p>This request expires on {when}.</p>", when=ctx.when(plan.expires_at)),
        fmt("<p>This page is served from {host}.</p>", host=ctx.services.host) if ctx.services.host else Safe(""),
    ])
    return page(ctx, plan.title, join(block(p) for p in parts), status=status, ai=True, extra=extra, why="You are named as an approver of this plan, and you have the role approver.")


def approval_page(ctx: Ctx, plan_id: str) -> Response:
    plan, refused = _gate(ctx, plan_id)
    return refused if refused is not None else render_plan(ctx, plan)  # type: ignore[arg-type]


# -- the answers ---------------------------------------------------------------------------------------------------------------------------------

def _back(ctx: Ctx, plan_id: str) -> tuple[str, str]:
    return (f"/ok/{link_part(plan_id)}", "Back to the request")


def _no_token(ctx: Ctx, plan_id: str) -> Response:
    return message_page(ctx, 403, "This form cannot be used", "The form has no token, so it was not accepted. Nothing was changed.",
                        "Open the request again and use the buttons on its page.", back=_back(ctx, plan_id), ai=True, why=WHY)


def _call(fn) -> DecideResult:
    try:
        result = fn()
    except Exception:  # noqa: BLE001 (a decider that fails has recorded nothing that this page knows of)
        return DecideResult(False, "error", "")
    return result if isinstance(result, DecideResult) else DecideResult(False, "error", "")


def _plan_of(ctx: Ctx, result: DecideResult, plan_id: str) -> PlanRecord | None:
    stored, _ = read(lambda: ctx.store.plan_get(plan_id), None)
    return stored or result.plan


def outcome(ctx: Ctx, result: DecideResult, plan_id: str, via: str = "decide") -> Response:
    """Every kind of result of the decider as a plain page. A refusal says that nothing changed."""
    kind = result.kind if result.kind in STATUS else "error"
    status = STATUS[kind]
    back = _back(ctx, plan_id)
    show = lambda title, *lines, back_to=back: message_page(ctx, status, title, *lines, back=back_to, ai=True, why=WHY)  # noqa: E731
    if kind == "recorded":
        plan, action = _plan_of(ctx, result, plan_id), read(lambda: ctx.store.action_get(plan_id), None)[0]
        started = start_block(ctx, plan, action, True) if plan is not None else Safe("")
        return show("Your OK is recorded", "Recorded. Nothing has changed yet.", started)
    if kind == "declined":
        return show("Declined", "Declined. Nothing has changed. The request is closed.", paragraph(link(ctx.url("/me/decisions"), "See my decisions")))
    if kind == "asked":
        plan = _plan_of(ctx, result, plan_id)
        until = paragraph(fmt("The request stays open until {when}.", when=ctx.when(plan.expires_at))) if plan is not None else Safe("")
        return show("Your question is recorded", "Recorded. Your question or suggestion approves nothing.", until)
    if kind == "not_mine":
        return show("Recorded: not yours", "Recorded. Nothing is approved. The request goes back to finding the right owner.", back_to=("/", "Back to the start page"))
    if kind == "withdrawn":
        return show("Cancelled", "Cancelled. Your OK is withdrawn and the request is closed. Nothing has changed.", back_to=("/", "Back to the start page"))
    if kind == "refused_code":
        return show("This plan changed", CHANGED)
    if kind == "refused_state":
        if via == "withdraw":
            return show("Nothing was cancelled", "There is no OK of yours to cancel, or the change has started and cannot be cancelled. Nothing has changed.")
        return show("This request cannot take an answer", "This request is not open for an answer now. It may be answered, cancelled, expired or replaced. Nothing has changed.")
    if kind == "refused_role":
        return _refused_role(ctx)
    if kind == "refused_paused":
        return show("Changes are paused", PAUSED)
    if kind == "expired":
        plan = _plan_of(ctx, result, plan_id)
        when = ctx.when(plan.expires_at, "its expiry time") if plan is not None else "its expiry time"
        return show("This request expired", paragraph(fmt("This request expired on {when}. Nothing has changed.", when=when)))
    if kind == "duplicate":
        return show("Already answered", "You answered this request already. Your first answer stands, and nothing has changed.")
    reason = clean_line(result.message)[:300]
    return show("I could not take your answer", reason or "The approval service did not answer.", "Open the request again to see where it stands.")


def _post(ctx: Ctx, plan_id: str) -> tuple[PlanRecord | None, str, Response | None]:
    """The checks that every answer shares. Returns the plan, the token and a page when the answer is refused here."""
    plan, refused = _gate(ctx, plan_id)
    if refused is not None:
        return None, "", refused
    nonce = ctx.request.form.get("nonce", "")
    if not nonce:
        return None, "", _no_token(ctx, plan_id)
    return plan, nonce, None


def approval_decide(ctx: Ctx, plan_id: str) -> Response:
    plan, nonce, refused = _post(ctx, plan_id)
    if refused is not None:
        return refused
    form_data = ctx.request.form
    decision, note = form_data.get("decision", ""), form_data.get("note", "")
    if decision not in ("approve", "decline"):
        return message_page(ctx, 400, "Choose an answer", "The form did not say Approve or Decline. Nothing was recorded.", back=_back(ctx, plan_id), ai=True, why=WHY)
    if len(note) > MAX_NOTE:
        return render_plan(ctx, plan, values={"note": note}, errors={"note": f"The note has {len(note)} characters. The most is {MAX_NOTE}."}, status=400)  # type: ignore[arg-type]
    return outcome(ctx, _call(lambda: ctx.services.decider.decide(ctx.principal, plan_id, decision, form_data.get("code", ""), nonce, note)), plan_id)  # type: ignore[arg-type]


def approval_ask(ctx: Ctx, plan_id: str) -> Response:
    plan, nonce, refused = _post(ctx, plan_id)
    if refused is not None:
        return refused
    note = ctx.request.form.get("note", "")
    problem = "Write your question or suggestion." if not note else (f"The text has {len(note)} characters. The most is {MAX_NOTE}." if len(note) > MAX_NOTE else "")
    if problem:
        return render_plan(ctx, plan, values={"ask-note": note}, errors={"ask-note": problem}, status=400)  # type: ignore[arg-type]
    return outcome(ctx, _call(lambda: ctx.services.decider.decide(ctx.principal, plan_id, "ask", ctx.request.form.get("code", ""), nonce, note)), plan_id)  # type: ignore[arg-type]


def approval_not_mine(ctx: Ctx, plan_id: str) -> Response:
    _, nonce, refused = _post(ctx, plan_id)
    if refused is not None:
        return refused
    return outcome(ctx, _call(lambda: ctx.services.decider.decide(ctx.principal, plan_id, "not_mine", ctx.request.form.get("code", ""), nonce, "")), plan_id)  # type: ignore[arg-type]


def approval_withdraw(ctx: Ctx, plan_id: str) -> Response:
    _, nonce, refused = _post(ctx, plan_id)
    if refused is not None:
        return refused
    return outcome(ctx, _call(lambda: ctx.services.decider.withdraw(ctx.principal, plan_id, nonce)), plan_id, via="withdraw")  # type: ignore[arg-type]
