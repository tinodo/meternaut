"""The page of a case: the same decision brief as the page of its request (brief_page.py), for any listed person.

A person who may answer the request of the case sees its form too; anybody else reads the brief and cannot answer. The page shows only fields of the stored records: what
came from the estate or from an AI is escaped and set in a labelled quote, never as a link or a control.
"""
from __future__ import annotations

from . import brief_page
from .common import brief_of, may_answer, read
from .core import Ctx, Response
from .layout import message_page


def notebook(ctx: Ctx, case_id: str) -> Response:
    case = ctx.store.case_get(case_id)
    if case is None:
        return message_page(ctx, 404, "I cannot find this finding", "No finding has this address. Nothing has changed.", back=("/history", "Back to the history"), ai=True,
                            why="you opened an address that holds no finding")
    plan, action, decisions = None, None, []
    if case.plan_id:
        plan, _ = read(lambda: ctx.store.plan_get(case.plan_id), None)
        action, _ = read(lambda: ctx.store.action_get(case.plan_id), None)
        decisions, _ = read(lambda: ctx.store.decisions_of_plan(case.plan_id), [])
    answerable = plan is not None and may_answer(ctx.principal, plan)  # type: ignore[arg-type]
    seen = decisions if answerable else []  # who answered is shown to the people who are named for the request, and to nobody else
    brief = brief_of(ctx, plan, case, action=action, decisions=seen, answerable=answerable)
    answer = brief_page.answer_form(ctx, plan, brief, {}, {}) if brief.answers and plan is not None else None
    return brief_page.render(ctx, brief, case=case, plan=plan, action=action, decisions=seen, answer=answer, why="you opened the record of one finding that Meternaut looked at")
