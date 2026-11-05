"""The two pages for the platform team: the standing permissions (none exist, read-only) and the kill switch (three levels)."""
from __future__ import annotations

from ..models import SWITCH_NAMES, SwitchRecord
from . import words
from .common import switch_states
from .core import MAX_REASON, Ctx, Response, Safe, fmt, join, stamp
from .home import switch_text
from .layout import block, button, error_summary, field, form, hidden, message_page, notice, page, paragraph

PERMISSIONS_WHY = "Your role lets you see how Meternaut is allowed to act."
PAUSE_WHY = "Your role ops lets you stop work at three levels."


def permissions(ctx: Ctx) -> Response:
    parts: list[object] = [
        Safe("<h1>Standing permissions</h1>"),
        paragraph("A standing permission would let Meternaut make a kind of change without asking each time. None exists. Meternaut makes a change only after a person approves "
                  "that exact change on its own page.", "lead"),
        paragraph("This page only shows what exists. It cannot write, change or end a permission."),
        Safe("<h2>What the runner may change</h2>"),
        paragraph(fmt("The runner may only {writer}. It changes nothing else.", writer=ctx.services.writer)),
    ]
    return page(ctx, "Standing permissions", join(block(p) for p in parts), current="/ops/permissions", why=PERMISSIONS_WHY)


def _switch_form(ctx: Ctx, name: str, record: SwitchRecord | None, errors: dict[str, str], values: dict[str, str]) -> Safe:
    label, stops, button_word = words.SWITCH[name]
    pause = record is None or not record.paused
    # A switch that cannot be read is offered only as a pause: the safe side.
    action = "pause" if pause else "resume"
    reason = field(f"reason-{name}", "reason", "Reason (optional)", values.get("reason", "") if values.get("name") == name else "", hint=f"Up to {MAX_REASON} characters. It is kept with the last change of this switch.",
                   error=errors.get(f"reason-{name}", ""), maxlength=MAX_REASON)
    return join([
        fmt('<section aria-labelledby="switch-{name}"><h2 id="switch-{name}">{label}</h2>', name=name, label=label),
        paragraph(fmt("<strong>State:</strong> {state}", state=switch_text(ctx, name, record))),
        paragraph(fmt("<strong>What it stops:</strong> {stops}", stops=stops)),
        form(ctx.url("/ops/pause"), hidden("name", name), hidden("action", action), hidden("nonce", ctx.nonce("pause")), reason,
             fmt('<div class="actions">{b}</div>', b=button(f"{'Pause' if pause else 'Resume'} {button_word}", kind="danger" if pause else "primary"))),
        Safe("</section>"),
    ])


def pause_page(ctx: Ctx, *, banner: Safe | None = None, errors: dict[str, str] | None = None, values: dict[str, str] | None = None, status: int = 200) -> Response:
    errors, values = errors or {}, values or {}
    parts: list[object] = [
        Safe("<h1>The kill switch</h1>"),
        paragraph("Pull a switch to stop the work that is written under its name. A change that was already sent to Azure is not recalled. Resume lets the work start again.", "lead"),
        paragraph("Only the last change of each switch is kept, with the person, the time and the reason. Earlier changes are not kept."),
        paragraph("A switch that cannot be read counts as pulled."),
    ]
    if banner is not None:
        parts.append(banner)
    if errors:
        parts.append(error_summary(list(errors.items())))
    states = dict(switch_states(ctx))
    parts += [_switch_form(ctx, name, states.get(name), errors, values) for name in SWITCH_NAMES]
    return page(ctx, "The kill switch", join(block(p) for p in parts), current="/ops/pause", status=status, why=PAUSE_WHY)


def pause_save(ctx: Ctx) -> Response:
    form_data = ctx.request.form
    if not ctx.store.nonce_use(form_data.get("nonce", ""), ctx.principal.oid, "pause"):  # type: ignore[union-attr]
        return message_page(ctx, 403, "This form cannot be used", "The form is out of date, was used already or has no token. Nothing was changed.",
                            "Open the page again and use the form there.", back=("/ops/pause", "Back to the kill switch"))
    name, action, reason = form_data.get("name", ""), form_data.get("action", ""), form_data.get("reason", "")
    if name not in SWITCH_NAMES or action not in ("pause", "resume"):
        return message_page(ctx, 400, "Nothing was changed", "The form did not name one of the three switches and one of the two actions.", back=("/ops/pause", "Back to the kill switch"))
    if len(reason) > MAX_REASON:
        return pause_page(ctx, errors={f"reason-{name}": f"The reason has {len(reason)} characters. The most is {MAX_REASON}."}, values=dict(form_data), status=400)
    try:
        ctx.store.switch_put(SwitchRecord(name=name, paused=action == "pause", by=ctx.principal.name, at=stamp(ctx.now), reason=reason))  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 (a switch that could not be written is said plainly, and the runbook is the way)
        return message_page(ctx, 503, "The switch was not written", "The store did not take the change. Nothing was changed.",
                            "If work must stop now, use the commands of the runbook.", back=("/ops/pause", "Back to the kill switch"))
    label = words.SWITCH[name][0]
    banner = notice("success", "Paused" if action == "pause" else "Resumed", f"{label}: {'paused' if action == 'pause' else 'resumed'} by {ctx.principal.name}.")  # type: ignore[union-attr]
    return pause_page(ctx, banner=banner)
