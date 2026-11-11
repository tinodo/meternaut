"""A store that keeps everything in memory: what the tests of the pages, the approval loop and the change use, and the contract that the Table store has to meet."""
from __future__ import annotations

import datetime as dt
import secrets
from typing import Callable

from .models import (ActionRecord, CapabilityRecord, CaseRecord, ClaimRecord, DecisionRecord, LessonRecord, MailRecord, NoteRecord, PlanRecord, RunRecord, SettingsRecord,
                     SwitchRecord, SWITCH_NAMES, TIME_FORMAT, TwoPeopleRule, can_replace)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def stamp(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime(TIME_FORMAT)


def parse(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, TIME_FORMAT).replace(tzinfo=dt.timezone.utc)


class MemoryStore:
    def __init__(self, clock: Callable[[], dt.datetime] = utc_now) -> None:
        self.clock = clock
        self.runs: dict[str, RunRecord] = {}
        self.cases: dict[str, CaseRecord] = {}
        self.plans: dict[str, PlanRecord] = {}
        self.decisions: dict[tuple[str, str], DecisionRecord] = {}
        self.actions: dict[str, ActionRecord] = {}
        self.switch_records: dict[str, SwitchRecord] = {}
        self.settings: dict[str, SettingsRecord] = {}
        self.rule = TwoPeopleRule()
        self.notes: dict[tuple[str, str], NoteRecord] = {}
        self.nonces: dict[str, tuple[str, str, dt.datetime, str]] = {}
        self.mails: list[MailRecord] = []
        self.lessons: dict[str, LessonRecord] = {}
        self.claims: dict[str, ClaimRecord] = {}
        self.profiles: list[CapabilityRecord] = []

    def runs_recent(self, limit: int = 20) -> list[RunRecord]:
        return sorted(self.runs.values(), key=lambda r: (r.started_at, r.run_id), reverse=True)[:limit]

    def run_put(self, run: RunRecord) -> None:
        self.runs[run.run_id] = run

    def cases_recent(self, limit: int = 100, status: str | None = None) -> list[CaseRecord]:
        items = [c for c in self.cases.values() if status is None or c.status == status]
        return sorted(items, key=lambda c: (c.updated_at, c.case_id), reverse=True)[:limit]

    def case_get(self, case_id: str) -> CaseRecord | None:
        return self.cases.get(case_id)

    def case_put(self, case: CaseRecord) -> None:
        self.cases[case.case_id] = case

    def case_update(self, case_id: str, change: Callable[[CaseRecord], CaseRecord | None]) -> bool:
        case = self.cases.get(case_id)
        changed = None if case is None else change(case)
        if changed is None:
            return False
        self.case_put(changed)
        return True

    def plans_open(self) -> list[PlanRecord]:
        return sorted((p for p in self.plans.values() if p.state in ("open", "approved")), key=lambda p: (p.created_at, p.plan_id), reverse=True)

    def plans_recent(self, limit: int = 50) -> list[PlanRecord]:
        return sorted(self.plans.values(), key=lambda p: (p.created_at, p.plan_id), reverse=True)[:limit]

    def plan_get(self, plan_id: str) -> PlanRecord | None:
        return self.plans.get(plan_id)

    def plan_put(self, plan: PlanRecord) -> None:
        self.plans[plan.plan_id] = plan

    def decisions_of_plan(self, plan_id: str) -> list[DecisionRecord]:
        return sorted((d for (p, _), d in self.decisions.items() if p == plan_id), key=lambda d: (d.at, d.approver_oid))

    def decisions_by(self, oid: str, limit: int = 100) -> list[DecisionRecord]:
        return sorted((d for d in self.decisions.values() if d.approver_oid == oid), key=lambda d: (d.at, d.plan_id), reverse=True)[:limit]

    def decision_put(self, decision: DecisionRecord) -> bool:
        key = (decision.plan_id, decision.approver_oid)
        existing = self.decisions.get(key)
        if existing is not None and not can_replace(existing.decision, decision.decision):
            return False
        self.decisions[key] = decision
        return True

    def action_get(self, plan_id: str) -> ActionRecord | None:
        return self.actions.get(plan_id)

    def action_put(self, action: ActionRecord) -> None:
        self.actions[action.plan_id] = action

    def action_claim(self, action: ActionRecord) -> bool:
        if action.plan_id in self.actions:
            return False
        self.actions[action.plan_id] = action
        return True

    def action_release(self, plan_id: str) -> None:
        action = self.actions.get(plan_id)
        if action is not None and action.state == "queued" and not action.started_at:
            del self.actions[plan_id]

    def actions_recent(self, limit: int = 50) -> list[ActionRecord]:
        return sorted(self.actions.values(), key=lambda a: (a.queued_at, a.plan_id), reverse=True)[:limit]

    def switch_get(self, name: str) -> SwitchRecord:
        if name not in SWITCH_NAMES:
            raise ValueError(f"{name} is not a switch")
        return self.switch_records.get(name, SwitchRecord(name=name))

    def switch_put(self, switch: SwitchRecord) -> None:
        if switch.name not in SWITCH_NAMES:
            raise ValueError(f"{switch.name} is not a switch")
        self.switch_records[switch.name] = switch

    def switches(self) -> list[SwitchRecord]:
        return [self.switch_get(name) for name in SWITCH_NAMES]

    def settings_get(self, oid: str) -> SettingsRecord:
        return self.settings.get(oid, SettingsRecord(oid=oid))

    def settings_put(self, settings: SettingsRecord) -> None:
        self.settings[settings.oid] = settings

    def settings_delete(self, oid: str) -> None:
        self.settings.pop(oid, None)

    def rule_get(self) -> TwoPeopleRule:
        return self.rule

    def rule_put(self, rule: TwoPeopleRule) -> None:
        self.rule = rule

    def notes_of(self, oid: str) -> list[NoteRecord]:
        return sorted((n for (o, _), n in self.notes.items() if o == oid), key=lambda n: (n.created_at, n.note_id), reverse=True)

    def note_put(self, note: NoteRecord) -> None:
        self.notes[(note.oid, note.note_id)] = note

    def note_delete(self, oid: str, note_id: str) -> None:
        self.notes.pop((oid, note_id), None)

    def do_not_touch(self) -> set[str]:
        now = stamp(self.clock())
        return {n.scope_resource_id.lower() for n in self.notes.values()
                if n.kind == "do_not_touch" and n.scope_resource_id and (not n.expires_at or n.expires_at > now)}

    def nonce_new(self, oid: str, purpose: str, ttl_seconds: int = 3600, data: str = "") -> str:
        token = secrets.token_urlsafe(24)
        self.nonces[token] = (oid, purpose, self.clock() + dt.timedelta(seconds=ttl_seconds), data)
        return token

    def nonce_take(self, token: str, oid: str, purpose: str) -> str | None:
        entry = self.nonces.get(token)
        if entry is None:
            return None
        owner, wanted, expires, data = entry
        if owner != oid or wanted != purpose:
            return None
        del self.nonces[token]
        return data if expires > self.clock() else None

    def nonce_use(self, token: str, oid: str, purpose: str) -> bool:
        return self.nonce_take(token, oid, purpose) is not None

    def mail_put(self, mail: MailRecord) -> None:
        self.mails.append(mail)

    def mails_since(self, oid: str, since: str) -> list[MailRecord]:
        return sorted((m for m in self.mails if m.oid == oid and m.sent_at >= since), key=lambda m: (m.sent_at, m.mail_id))

    def lesson_put(self, lesson: LessonRecord) -> None:
        self.lessons[lesson.lesson_id] = lesson

    def lessons_of(self, resource_type: str, limit: int = 500) -> list[LessonRecord]:
        found = [lesson for lesson in self.lessons.values() if lesson.resource_type == resource_type]
        return sorted(found, key=lambda lesson: (lesson.closed_at, lesson.lesson_id), reverse=True)[:limit]

    def lessons_recent(self, limit: int = 300) -> list[LessonRecord]:
        return sorted(self.lessons.values(), key=lambda lesson: (lesson.updated_at, lesson.lesson_id), reverse=True)[:limit]

    def claim_put(self, claim: ClaimRecord) -> None:
        self.claims[claim.claim_id] = claim

    def claims_of(self, resource_type: str) -> list[ClaimRecord]:
        return sorted((c for c in self.claims.values() if c.resource_type == resource_type), key=lambda c: (c.read_at, c.claim_id), reverse=True)

    def claims_recent(self, limit: int = 500) -> list[ClaimRecord]:
        return sorted(self.claims.values(), key=lambda c: (c.read_at, c.claim_id), reverse=True)[:limit]

    def profile_put(self, profile: CapabilityRecord) -> None:
        self.profiles.append(profile)

    def profile_latest(self) -> CapabilityRecord | None:
        return max(self.profiles, key=lambda p: (p.at, p.run_id), default=None)
