"""What more than one page needs: reading the store without failing a whole page, the switches, who may answer a plan, what happened to a change,
and the rows of the tables of cases and runs."""
from __future__ import annotations

import math
from typing import Callable, Iterable, TypeVar

from ..brief import Brief, build_brief
from ..models import ADVISE, SWITCH_NAMES, ActionRecord, CaseRecord, DecisionRecord, PlanRecord, Principal, RunRecord, SwitchRecord
from . import words
from .core import Ctx, Safe, esc, fmt, join, link_part, number, parse_time, usd
from .figures import chip
from .layout import code, paragraph, summary

T = TypeVar("T")


def read(fn: Callable[[], T], default: T) -> tuple[T, bool]:
    """Calls a store read. A read that fails gives the default and False, so that one section of a page can say so and the rest still shows."""
    try:
        return fn(), True
    except Exception:  # noqa: BLE001 (any failure of a read is a section that cannot be read)
        return default, False


def cases_by_id(ctx: Ctx, wanted: set[str]) -> dict[str, CaseRecord]:
    """The cases with these ids: the recent cases in one read, and the others one by one. A case that cannot be read is left out."""
    recent, _ = read(lambda: ctx.store.cases_recent(1000), [])
    found = {case.case_id: case for case in recent if case.case_id in wanted}
    for case_id in sorted(wanted - found.keys()):
        case, _ = read(lambda case_id=case_id: ctx.store.case_get(case_id), None)
        if case is not None:
            found[case_id] = case
    return found


def brief_of(ctx: Ctx, plan: PlanRecord | None, case: CaseRecord | None, *, action: ActionRecord | None = None, decisions: Iterable[DecisionRecord] = (), answerable: bool = False) -> Brief:
    """The brief of one request, as the signed-in person sees it. A switch that holds this kind of answer (a change is held by `all` and `changes`, advice by `all`) takes the
    answer that it holds out of the brief."""
    paused = answerable and plan is not None and plan.state == "open" and pulled(ctx, *(("all",) if plan.family == ADVISE else ("all", "changes")))
    return build_brief(case, plan, action, list(decisions), now=ctx.now, may_answer=answerable, changes_paused=paused)


def switch_states(ctx: Ctx) -> list[tuple[str, SwitchRecord | None]]:
    """Each switch with its record, or None when it cannot be read."""
    states: list[tuple[str, SwitchRecord | None]] = []
    for name in SWITCH_NAMES:
        record, ok = read(lambda name=name: ctx.store.switch_get(name), None)
        states.append((name, record if ok else None))
    return states


def pulled(ctx: Ctx, *names: str) -> bool:
    """True when a named switch is pulled. A switch that cannot be read counts as pulled."""
    for name in names:
        record, ok = read(lambda name=name: ctx.store.switch_get(name), None)
        if not ok or record is None or record.paused:
            return True
    return False


def may_answer(principal: Principal, plan: PlanRecord) -> bool:
    """Only a person named in the plan may answer it, checked by directory object id, and with the role approver. Advice changes nothing in Azure, so the owner may answer it too."""
    named = principal.oid.lower() in {a.lower() for a in plan.approvers}
    return named and (principal.has("approver") or (plan.family == ADVISE and principal.has("owner")))


def is_expired(ctx: Ctx, plan: PlanRecord) -> bool:
    """A plan whose time is over, also when the record still says open. A time that cannot be read counts as over."""
    end = parse_time(plan.expires_at)
    return end is None or ctx.now >= end


def effective_state(ctx: Ctx, plan: PlanRecord) -> str:
    return "expired" if plan.state == "open" and is_expired(ctx, plan) else plan.state


# -- what happened to the change ---------------------------------------------------------------------------------------------------------------------

def _money_in(amount: object, currency: object) -> str:
    if currency in (None, "", "USD"):
        return usd(amount)
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
        return "no figure"
    return f"{amount:,.2f} {currency}"


def verification_text(ctx: Ctx, data: object) -> Safe:
    """What the check after a change found, in words. Only the fields of the record are shown."""
    if not isinstance(data, dict) or not data:
        return esc("Not checked yet.")
    if data.get("noChange") is True:
        return esc("Nothing was changed, so there is nothing to check afterwards.")
    lines: list[object] = []
    if "gone" in data:
        lines.append("Azure no longer lists the resource." if data["gone"] else "Azure still lists the resource.")
    if data.get("checkedAt"):
        lines.append(fmt("Checked {when}.", when=ctx.when(data["checkedAt"])))
    if "costAfterUsd" in data:
        lines.append(f"Cost lines after the change: {_money_in(data['costAfterUsd'], data.get('currency'))}.")
    if data.get("costLinesFrom"):
        lines.append(f"Cost lines read from {data['costLinesFrom']}" + (f" to {data['costLinesTo']}." if data.get("costLinesTo") else "."))
    if "costBeforeUsd30d" in data:
        lines.append(f"Cost lines of the 30 days before: {usd(data['costBeforeUsd30d'])}.")
    if data.get("costAskedOn") and "costAfterUsd" not in data:
        lines.append(f"Cost lines were last asked for on {data['costAskedOn']}.")
    if data.get("note"):
        lines.append(f"Note: {data['note']}")
    known = {"gone", "checkedAt", "costAfterUsd", "currency", "costLinesFrom", "costLinesTo", "costBeforeUsd30d", "costAskedOn", "costGaveUp", "note"}
    lines += [f"{name}: {value}" for name, value in sorted(data.items()) if name not in known and isinstance(value, (str, int, float, bool))][:5]
    return join((paragraph(line) for line in lines)) if lines else esc("Not checked yet.")


def action_rows(ctx: Ctx, action: ActionRecord) -> list[tuple[str, object]]:
    """What happened to the change of one plan, and what the check afterwards found, as names and values."""
    state = words.ACTION_STATE.get(action.state, action.state)
    if action.no_change and action.state in ("done", "verified", "unknown"):
        state = words.NOTHING_CHANGED_STATE
    rows: list[tuple[str, object]] = [("State", state), ("Queued", ctx.when(action.queued_at))]
    if action.started_at:
        rows.append(("Started", ctx.when(action.started_at)))
    if action.finished_at:
        rows.append(("Finished", ctx.when(action.finished_at)))
    if action.result and action.result != state:
        rows.append(("Result", action.result))
    if action.error and action.error != action.result:
        rows.append(("Error", action.error))
    if action.verification or action.state in ("done", "verified", "unknown"):
        rows.append(("Checked afterwards", verification_text(ctx, action.verification)))
    if action.verified_at:
        rows.append(("Verified", ctx.when(action.verified_at)))
    return rows


def action_block(ctx: Ctx, action: ActionRecord) -> Safe:
    return summary(action_rows(ctx, action))


# -- tables of runs and cases ----------------------------------------------------------------------------------------------------------------------

def kind_text(resource_type: str) -> Safe:
    """The kind of a resource in words, with its type name."""
    plain = words.resource_type_words(resource_type)
    return fmt("{plain} ({type})", plain=plain, type=code(resource_type)) if plain else code(resource_type)


def resource_cell(name: str, resource_type: str, group: str) -> Safe:
    """The name, the kind and the group of a resource: text from the estate, escaped."""
    return fmt('{name}<br><span class="muted">{kind}. Resource group {group}.</span>', name=name, kind=kind_text(resource_type), group=group)


def detector_cell(detector: str) -> Safe:
    plain = words.DETECTOR.get(detector)
    return fmt("{plain}<br><code>{id}</code>", plain=plain, id=detector) if plain else code(detector)


def figure(value: object) -> str:
    return usd(value) if value is not None else "no figure"


def confidence(value: object) -> str:
    return f"{value:.2f}" if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else "none"


CASE_HEADERS = ["Resource", "Found by", "Status", "Recommendation", "Confidence (0 to 1)", "Estimated saving a month", "Last updated", "Page"]


def case_rows(ctx: Ctx, cases: Iterable[CaseRecord]) -> list[list[object]]:
    """The rows of a table of cases, in the order of CASE_HEADERS."""
    rows: list[list[object]] = []
    for case in cases:
        rows.append([
            resource_cell(case.resource_name, case.resource_type, case.resource_group), detector_cell(case.detector), status_chip(case.status),
            words.recommendation_word(case.recommendation), confidence(case.confidence), figure(case.saving_usd_month), ctx.when(case.updated_at),
            fmt('<a href="{href}">Open<span class="visually-hidden"> the page of {name}</span></a>', href=ctx.url(f"/why/{link_part(case.case_id)}"),
                name=case.resource_name),
        ])
    return rows


# The look of each status word of a case: a colour class and a shape (the guide: a chip is a word and a shape). A status that is not listed is shown as it is stored, as a plain chip.
STATUS_LOOK = {"proposed": ("info", "square"), "needs_human": ("mid", "triangle"), "dropped": ("", "square"), "error": ("high", "diamond"), "awaiting_ok": ("info", "square"),
               "approved": ("info", "square"), "running": ("info", "square"), "done": ("low", "circle"), "failed": ("high", "diamond"), "declined": ("", "square"),
               "expired": ("", "square"), "verified": ("low", "circle"), "acknowledged": ("info", "square")}


def status_chip(status: str) -> Safe:
    kind, shape = STATUS_LOOK.get(status, ("", "square"))
    return chip(words.case_status(status), kind, shape)


def run_result(run: RunRecord) -> Safe:
    """How a run ended, as a chip and, for a failure, the reason after it (the text reads "Failed: the reason")."""
    if not run.ok:
        return fmt("{chip}{reason}", chip=chip("Failed", "high", "diamond"), reason=f": {run.reason}" if run.reason else "")
    return chip("OK", "low", "circle") if run.finished_at else chip("Started, not finished", "info", "square")


def count(value: object) -> str:
    return number(value) if isinstance(value, int) and not isinstance(value, bool) else "0"


def legend() -> Safe:
    """What each status word means."""
    return summary([(word, meaning) for word, meaning in words.CASE_STATUS.values()])
