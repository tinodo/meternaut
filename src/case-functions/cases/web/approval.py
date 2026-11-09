"""The page of a request and what happens when a person answers it.

The page is the decision brief (brief_page.py), built from the stored records and never from a model's prose. An answer is a POST of the one form of the page, with the plan
code and a one-time token. Declining, asking, "not mine", "later" and the answer "worth acting on" of an advise plan (which changes nothing in Azure) are recorded by the
decider. Approving a change sends the person to the sign-in to Azure (Microsoft Entra), and the page that the person comes back to (`/arm/return`) shows what came of it:
the change is made right there, with the person's own token. When Azure asks for an extra sign-in check, that page is a redirect to the sign-in once more, and the page that
the person comes back to then shows what came of it. Each kind of result has a plain page of its own.
"""
from __future__ import annotations

import re

from ..brief import PAUSED_ADVICE, called_of
from ..models import ADVISE, DECLINE_REASONS, MAX_SIGNIN_PATH, DecideResult, PlanRecord
from . import brief_page
from .common import brief_of, may_answer, read
from .core import MAX_NOTE, Ctx, Response, Safe, clean_line, fmt, link_part
from .layout import SIGNIN_ORIGIN, link, message_page, paragraph

REFUSED_ROLE = "I cannot take your OK on this request."
PAUSED = brief_page.PAUSED
CHANGED = "This plan changed. Nothing is approved. A new message will bring the new plan and code."
# The only address that an approval may send a person to: the sign-in of Microsoft Entra, with a query that holds nothing but escaped characters. The same check holds for the
# first sign-in (`begin`) and for the second one that Azure's claims challenge asks for (the result of `finish`).
SIGNIN_ADDRESS = re.compile(re.escape(SIGNIN_ORIGIN) + rf"/[A-Za-z0-9._~%/+=&?-]{{1,{MAX_SIGNIN_PATH}}}")
STATUS = {"declined": 200, "asked": 200, "not_mine": 200, "later": 200, "acknowledged": 200, "ran": 200, "ran_unconfirmed": 200, "running": 200, "unchanged": 200, "stopped": 409,
          "azure_refused": 403, "failed": 502, "signin_failed": 400, "step_up_failed": 400, "refused_code": 409, "refused_state": 409, "refused_role": 403, "refused_paused": 409,
          "expired": 410, "duplicate": 409, "error": 500}
WHY = "you answered a request on this page"
ANSWERS = ("approve", "decline", "ask", "not_mine", "later")


def _base(ctx: Ctx, plan_id: str) -> str:
    return ctx.url(f"/ok/{link_part(plan_id)}")


def _refused_role(ctx: Ctx) -> Response:
    return message_page(ctx, 403, REFUSED_ROLE, "Nothing is approved. If this request should be yours, use Talk to a person below.", back=("/", "Back to the decisions"),
                        ai=True, why="you opened a request that is not yours to answer")


def _not_found(ctx: Ctx) -> Response:
    return message_page(ctx, 404, "I cannot find this request", "No request has this address. Nothing has changed.", back=("/", "Back to the decisions"), ai=True,
                        why="you opened an address that holds no request")


def _gate(ctx: Ctx, plan_id: str) -> tuple[PlanRecord | None, Response | None]:
    """Who may see and answer a plan: a person named in it, with the role approver (for advice, the owner too). Nobody else sees its details, and a person who may not approve
    a change learns nothing about which ids exist."""
    principal = ctx.principal
    if not (principal.has("approver") or principal.has("owner")):  # type: ignore[union-attr]
        return None, _refused_role(ctx)
    plan = ctx.store.plan_get(plan_id)
    if plan is None:
        return None, (_not_found(ctx) if principal.has("approver") else _refused_role(ctx))  # type: ignore[union-attr]
    if not may_answer(principal, plan):  # type: ignore[arg-type]
        return None, _refused_role(ctx)
    return plan, None


# -- the page ------------------------------------------------------------------------------------------------------------------------------------

def render_plan(ctx: Ctx, plan: PlanRecord, *, values: dict[str, str] | None = None, errors: dict[str, str] | None = None, status: int = 200) -> Response:
    """The page of a request, for a person who may answer it. The form appears only while the request is open; the approve button is left out while changes are paused."""
    values, errors = values or {}, errors or {}
    case, _ = read(lambda: ctx.store.case_get(plan.case_id), None)
    decisions, _ = read(lambda: ctx.store.decisions_of_plan(plan.plan_id), [])
    action, _ = read(lambda: ctx.store.action_get(plan.plan_id), None)
    brief = brief_of(ctx, plan, case, action=action, decisions=decisions, answerable=True)
    answer = brief_page.answer_form(ctx, plan, brief, values, errors) if brief.answers else None
    return brief_page.render(ctx, brief, case=case, plan=plan, action=action, decisions=decisions, answer=answer, errors=errors, status=status,
                             why="you are named as an approver of this request, and you have the role approver")


def approval_page(ctx: Ctx, plan_id: str) -> Response:
    plan, refused = _gate(ctx, plan_id)
    return refused if refused is not None else render_plan(ctx, plan)  # type: ignore[arg-type]


# -- the answers ---------------------------------------------------------------------------------------------------------------------------------

def _back(ctx: Ctx, plan_id: str | None) -> tuple[str, str]:
    return (f"/ok/{link_part(plan_id)}", "Back to the request") if plan_id else ("/", "Back to the decisions")


def _no_token(ctx: Ctx, plan_id: str) -> Response:
    return message_page(ctx, 403, "This form cannot be used", "The form has no token, so it was not accepted. Nothing was changed.",
                        "Open the request again and use the buttons on its page.", back=_back(ctx, plan_id), ai=True, why=WHY)


def _call(fn) -> DecideResult:
    try:
        result = fn()
    except Exception:  # noqa: BLE001 (a decider that fails has recorded nothing that this page knows of)
        return DecideResult(False, "error", "")
    return result if isinstance(result, DecideResult) else DecideResult(False, "error", "")


def _plan_of(ctx: Ctx, result: DecideResult, plan_id: str | None) -> PlanRecord | None:
    stored, _ = read(lambda: ctx.store.plan_get(plan_id), None) if plan_id else (None, False)
    return stored or result.plan


def _called(plan: PlanRecord | None) -> str:
    """The change as a noun of a sentence ("delete", "stop", "resize"), as the family of the plan calls it; "change" when no plan is known."""
    return called_of(plan.family if plan is not None else None)


def outcome(ctx: Ctx, result: DecideResult, plan_id: str | None) -> Response:
    """Every kind of result as a plain page. A refusal says that nothing changed; a change says that it was made with the person's own permissions; an approval that found nothing to
    change says that nothing was changed."""
    kind = result.kind if result.kind in STATUS else "error"
    status = STATUS[kind]
    back = _back(ctx, plan_id)
    show = lambda title, *lines, back_to=back: message_page(ctx, status, title, *lines, back=back_to, ai=True, why=WHY)  # noqa: E731
    text = clean_line(result.message)[:400]
    history = paragraph(link(ctx.url("/history"), "See the history"))
    if kind == "ran":
        return show("The change was made", text or "Done.",
                    "It was made with your own permissions: Azure's Activity Log shows your name as the person who made it. Meternaut holds no right of its own to change Azure.",
                    history)
    if kind == "ran_unconfirmed":
        called = _called(_plan_of(ctx, result, plan_id))
        return show(f"The {called} was accepted", text or f"Azure accepted the {called}.", "Meternaut looks again in a few minutes and records what it finds. It was made with your own permissions.")
    if kind == "running":
        return show("The change is being made", text or "Azure accepted the change and is still making it.",
                    "Meternaut reads the resource again in a few minutes and records what it finds. It was made with your own permissions, and it is not made a second time.", history)
    if kind == "unchanged":
        return show("Nothing was changed", text or "Nothing was changed.",
                    "The resource was already as the plan wants, so Meternaut wrote nothing, and no saving is claimed for this approval.", history)
    if kind == "stopped":
        return show("The change was stopped", text or "A check failed before the change.", "Nothing was changed. The request is closed.")
    if kind == "azure_refused":
        return show("Azure refused the change", text or "Azure refused the change.",
                    "Meternaut holds no right of its own: the change is made with your permissions. If you should be able to make it, ask whoever manages access to this resource group.")
    if kind == "failed":
        return show("The change failed", text or "The change failed.", "Look at the resource in Azure before anything is tried again.")
    if kind == "signin_failed":
        return show("The sign-in to Azure was not completed", text or "Nothing is approved.", "The request stays open. Open it again to try again.")
    if kind == "step_up_failed":
        return show("The extra sign-in check was not completed", text or "The extra sign-in check that Azure asked for was not completed. The change was not made.",
                    "Nothing was changed. The request is closed.")
    if kind == "declined":
        plan = _plan_of(ctx, result, plan_id)
        if plan is not None and plan.family == ADVISE:
            return show("Recorded: not worth it", "Recorded. Nothing was changed. The request is closed.", history)
        return show("Declined", "Declined. Nothing has changed. The request is closed.", history)
    if kind == "acknowledged":
        return show("Recorded: worth acting on", "Recorded. Nothing was changed in Azure.", history)
    if kind == "asked":
        plan = _plan_of(ctx, result, plan_id)
        until = paragraph(fmt("The request stays open until {when}.", when=ctx.when(plan.expires_at))) if plan is not None else Safe("")
        return show("Recorded: your words", "Recorded with your name. It approves nothing, and Meternaut does not answer yet.", until)
    if kind == "later":
        return show("Noted", "Noted. Nothing is approved and nothing has changed. The request stays in your list.", back_to=("/", "Back to the decisions"))
    if kind == "not_mine":
        return show("Recorded: not yours", "Recorded. Nothing is approved. The request goes back to finding the right owner.", back_to=("/", "Back to the decisions"))
    if kind == "refused_code":
        return show("This plan changed", CHANGED)
    if kind == "refused_state":
        return show("This request cannot take an answer", text or "This request is not open for an answer now. It may be answered, expired or replaced. Nothing has changed.")
    if kind == "refused_role":
        return _refused_role(ctx)
    if kind == "refused_paused":
        plan = _plan_of(ctx, result, plan_id)
        if plan is not None and plan.family == ADVISE:
            return show("Meternaut is paused", PAUSED_ADVICE)
        return show("Changes are paused", PAUSED)
    if kind == "expired":
        plan = _plan_of(ctx, result, plan_id)
        when = ctx.when(plan.expires_at, "its expiry time") if plan is not None else "its expiry time"
        return show("This request expired", paragraph(fmt("This request expired on {when}. Nothing has changed.", when=when)))
    if kind == "duplicate":
        return show("Already answered", "You answered this request already. Your first answer stands, and nothing has changed.")
    return show("I could not take your answer", text or "The approval service did not answer.", "Open the request again to see where it stands.")


def _post(ctx: Ctx, plan_id: str) -> tuple[PlanRecord | None, str, Response | None]:
    """The checks that every answer shares. Returns the plan, the token and a page when the answer is refused here."""
    plan, refused = _gate(ctx, plan_id)
    if refused is not None:
        return None, "", refused
    nonce = ctx.request.form.get("nonce", "")
    if not nonce:
        return None, "", _no_token(ctx, plan_id)
    return plan, nonce, None


def _to_sign_in(ctx: Ctx, location: str, plan_id: str | None) -> Response:
    """To the sign-in of Microsoft Entra: the address is taken only if it is the one that an approval may send a person to, whatever made it."""
    if not isinstance(location, str) or not SIGNIN_ADDRESS.fullmatch(location):
        # The delegate builds this address from its settings. A page that is told to send the person anywhere else refuses: the policy of the page would stop only a browser
        # that checks a redirect after a form post.
        return outcome(ctx, DecideResult(False, "error", ""), plan_id)
    return Response(303, {"Location": location, "Cache-Control": "no-store"}, b"")


def _begin(ctx: Ctx, plan_id: str, nonce: str) -> Response:
    """Approving: the person is sent to the sign-in to Azure. Nothing is recorded yet, and nothing changes: the approval is made when the person comes back."""
    form_data = ctx.request.form
    try:
        begun = ctx.services.delegate.begin(ctx.principal, plan_id, form_data.get("code", ""), nonce, form_data.get("note", ""),  # type: ignore[arg-type]
                                            ctx.request.headers.get("x-ms-client-principal-name", ""))
    except Exception:  # noqa: BLE001 (nothing was recorded that this page knows of)
        return outcome(ctx, DecideResult(False, "error", ""), plan_id)
    if begun.refusal is not None or not begun.location:
        return outcome(ctx, begun.refusal or DecideResult(False, "error", ""), plan_id)
    return _to_sign_in(ctx, begun.location, plan_id)


def _answer(ctx: Ctx, plan: PlanRecord, nonce: str, decision: str) -> Response:
    """One answer of the form, after the checks that every answer shares. A change is approved at the sign-in to Azure; every other answer is the decider's."""
    plan_id = plan.plan_id
    form_data = ctx.request.form
    note, reason = form_data.get("note", ""), form_data.get("reason", "")
    if len(note) > MAX_NOTE:
        return render_plan(ctx, plan, values={"note": note, "reason": reason}, errors={"note": f"The note has {len(note)} characters. The most is {MAX_NOTE}."}, status=400)
    if decision == "ask" and not note:
        return render_plan(ctx, plan, values={"note": note, "reason": reason}, errors={"note": "Write your question, your objection or what to remember."}, status=400)
    if reason and reason not in DECLINE_REASONS:
        return render_plan(ctx, plan, values={"note": note}, errors={"reason": "Choose one of the reasons in the list."}, status=400)
    if decision == "approve" and plan.family != ADVISE:
        return _begin(ctx, plan_id, nonce)
    return outcome(ctx, _call(lambda: ctx.services.decider.decide(ctx.principal, plan_id, decision, form_data.get("code", ""), nonce, note, reason)), plan_id)  # type: ignore[arg-type]


def approval_decide(ctx: Ctx, plan_id: str) -> Response:
    plan, nonce, refused = _post(ctx, plan_id)
    if refused is not None:
        return refused
    decision = ctx.request.form.get("decision", "")
    if decision not in ANSWERS:
        return message_page(ctx, 400, "Choose an answer", "The form did not say which answer you chose. Nothing was recorded.", back=_back(ctx, plan_id), ai=True, why=WHY)
    return _answer(ctx, plan, nonce, decision)  # type: ignore[arg-type]


def arm_return(ctx: Ctx) -> Response:
    """Where the sign-in to Azure sends the person back to. The approval is recorded and the change is made here, with the person's own token.

    When Azure asks for an extra sign-in check, the answer is a redirect to the sign-in of Microsoft Entra once more (the kind step_up, with its address), through the same
    check as the first one. Anything else is the page of what came of it."""
    result = _call(lambda: ctx.services.delegate.finish(ctx.principal, ctx.request.query))  # type: ignore[arg-type]
    plan_id = result.plan.plan_id if result.plan is not None else None
    if result.kind == "step_up" or result.location:
        if result.kind == "step_up" and result.location:
            return _to_sign_in(ctx, result.location, plan_id)
        return outcome(ctx, DecideResult(False, "error", ""), plan_id)
    return outcome(ctx, result, plan_id)


def approval_ask(ctx: Ctx, plan_id: str) -> Response:
    """The older address of the question: the same answer as the button of the form."""
    plan, nonce, refused = _post(ctx, plan_id)
    return refused if refused is not None else _answer(ctx, plan, nonce, "ask")  # type: ignore[arg-type]


def approval_not_mine(ctx: Ctx, plan_id: str) -> Response:
    """The older address of "not mine": the same answer as the button of the form."""
    plan, nonce, refused = _post(ctx, plan_id)
    return refused if refused is not None else _answer(ctx, plan, nonce, "not_mine")  # type: ignore[arg-type]
