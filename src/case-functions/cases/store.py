"""The store: Azure Table Storage through its REST API, with the app's managed identity (no key, no connection string, no library).

One table for each kind of record. A record is kept as its JSON text in the property `data`, next to the few scalars that a query filters on.
The calls that the store makes are on its own list (`table_calls`), separate from the Watch's list of reads: a call to any other table, or any
other service, is refused before it leaves the app.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import secrets
from email.utils import format_datetime
from typing import Callable
from urllib.parse import quote

from .http import Client, HttpError, Refused
from .memory_store import parse, stamp, utc_now
from .models import (ActionRecord, CaseRecord, DecisionRecord, MailRecord, NoteRecord, PlanRecord, Record, RunRecord, SettingsRecord, StoreError, SwitchRecord,
                     SWITCH_NAMES, TIME_FORMAT)

RESOURCE = "https://storage.azure.com/"
VERSION = "2020-12-06"
MAX_DATA = 30000
MAX_PAGES = 10
PAGE = 1000

RUNS, CASES, PLANS, DECISIONS, ACTIONS, SWITCHES, SETTINGS, NOTES, NONCES, MAILS = (
    "mnruns", "mncases", "mnplans", "mndecisions", "mnactions", "mnswitches", "mnsettings", "mnnotes", "mnnonces", "mnmail")
TABLES = (RUNS, CASES, PLANS, DECISIONS, ACTIONS, SWITCHES, SETTINGS, NOTES, NONCES, MAILS)

KEY = r"[A-Za-z0-9_.-]{1,120}"
VALUE = re.compile(r"^[A-Za-z0-9_.@:-]{0,200}$")


def table_calls(account: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of every call that the store makes. Only this account's table service, only the app's own tables."""
    host = re.escape(f"https://{account}.table.core.windows.net")
    names = "|".join(TABLES)
    entity = rf"/(?:{names})\(PartitionKey='{KEY}',RowKey='{KEY}'\)"
    return (
        ("POST", re.compile(host + "/Tables", re.I)),
        ("POST", re.compile(host + rf"/(?:{names})", re.I)),
        ("GET", re.compile(host + rf"/(?:{names})\(\)", re.I)),
        ("GET", re.compile(host + entity, re.I)),
        ("PUT", re.compile(host + entity, re.I)),
        ("DELETE", re.compile(host + entity, re.I)),
    )


def compact(text: str) -> str:
    """A time as a key that sorts: 20261105T103000Z."""
    return re.sub(r"[-:]", "", text)


def reverse_key(moment: dt.datetime) -> str:
    """A key that sorts the newest first."""
    return f"{9_999_999_999 - int(moment.timestamp()):010d}"


def _text(value: object) -> str:
    return "" if value is None else str(value)


class TableStore:
    def __init__(self, client: Client, token: Callable[[str], str], account: str, *, clock: Callable[[], dt.datetime] = utc_now) -> None:
        if not re.fullmatch(r"[a-z0-9]{3,24}", account):
            raise StoreError("the storage account name is not a storage account name")
        self.client, self.token, self.account, self.clock = client, token, account, clock
        self.base = f"https://{account}.table.core.windows.net"
        self._ready: set[str] = set()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(RESOURCE)}", "x-ms-version": VERSION, "x-ms-date": format_datetime(self.clock(), usegmt=True),
                "Accept": "application/json;odata=nometadata", "DataServiceVersion": "3.0", **(extra or {})}

    def _call(self, method: str, url: str, *, body: object = None, headers: dict[str, str] | None = None, timeout: float = 30):
        try:
            return self.client.request(method, url, headers=self._headers(headers), body=body, timeout=timeout)
        except (HttpError, Refused) as error:
            raise StoreError(str(error), getattr(error, "status", 0)) from error

    @staticmethod
    def _status(error: StoreError) -> int:
        return error.status

    def _ensure(self, table: str) -> None:
        if table in self._ready:
            return
        try:
            self._call("POST", f"{self.base}/Tables", body={"TableName": table}, headers={"Prefer": "return-no-content"})
        except StoreError as error:
            if self._status(error) != 409:
                raise
        self._ready.add(table)

    @staticmethod
    def _check(value: str) -> str:
        if not re.fullmatch(KEY, value):
            raise StoreError("a key of the store has characters that a key may not have")
        return value

    def _address(self, table: str, pk: str, rk: str) -> str:
        return f"{self.base}/{table}(PartitionKey='{self._check(pk)}',RowKey='{self._check(rk)}')"

    def _entity(self, pk: str, rk: str, record: Record | None, **scalars: object) -> dict:
        entity: dict = {"PartitionKey": self._check(pk), "RowKey": self._check(rk), **{k: v for k, v in scalars.items() if v is not None}}
        if record is not None:
            data = record.to_json()
            if len(data) > MAX_DATA:
                raise StoreError("a record is larger than a table property may be")
            entity["data"] = data
        return entity

    def _upsert(self, table: str, pk: str, rk: str, record: Record | None, **scalars: object) -> None:
        entity, address = self._entity(pk, rk, record, **scalars), self._address(table, pk, rk)
        self._ensure(table)
        self._call("PUT", address, body=entity, headers={"Prefer": "return-no-content"})

    def _insert(self, table: str, pk: str, rk: str, record: Record | None, **scalars: object) -> bool:
        """False when the entity exists already."""
        entity = self._entity(pk, rk, record, **scalars)
        self._ensure(table)
        try:
            self._call("POST", f"{self.base}/{table}", body=entity, headers={"Prefer": "return-no-content"})
        except StoreError as error:
            if self._status(error) == 409:
                return False
            raise
        return True

    def _get(self, table: str, pk: str, rk: str) -> tuple[dict | None, str]:
        address = self._address(table, pk, rk)
        try:
            response = self._call("GET", address)
        except StoreError as error:
            if self._status(error) == 404:
                return None, ""
            raise
        body = response.json()
        return (body if isinstance(body, dict) else None), response.headers.get("etag", "")

    def _delete(self, table: str, pk: str, rk: str, etag: str = "*") -> bool:
        try:
            self._call("DELETE", self._address(table, pk, rk), headers={"If-Match": etag or "*"})
        except StoreError as error:
            if self._status(error) in (404, 412):
                return False
            raise
        return True

    def _query(self, table: str, filter_text: str = "", limit: int = PAGE) -> list[dict]:
        """The rows of a table. A table that is not there yet has no rows: a read never makes one (only the first write does)."""
        rows: list[dict] = []
        next_keys: dict[str, str] = {}
        for _ in range(MAX_PAGES):
            parts = [f"$top={min(limit - len(rows), PAGE)}"]
            if filter_text:
                parts.append("$filter=" + quote(filter_text, safe=""))
            parts += [f"{name}={quote(value, safe='')}" for name, value in next_keys.items()]
            try:
                response = self._call("GET", f"{self.base}/{table}()?" + "&".join(parts), timeout=60)
            except StoreError as error:
                if self._status(error) == 404:
                    break
                raise
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("value"), list):
                raise StoreError("the table service gave an answer that the app does not understand")
            rows += [row for row in body["value"] if isinstance(row, dict)]
            partition = response.headers.get("x-ms-continuation-nextpartitionkey")
            if len(rows) >= limit or not partition:
                break
            next_keys = {"NextPartitionKey": partition}
            if response.headers.get("x-ms-continuation-nextrowkey"):
                next_keys["NextRowKey"] = response.headers["x-ms-continuation-nextrowkey"]
        return rows[:limit]

    @staticmethod
    def _records(rows: list[dict], kind: type[Record]) -> list:
        found = []
        for row in rows:
            try:
                found.append(kind.from_json(row["data"]))
            except (KeyError, ValueError, TypeError) as error:
                raise StoreError(f"a stored {kind.__name__} cannot be read") from error
        return found

    @staticmethod
    def _quoted(value: str) -> str:
        if not VALUE.fullmatch(value):
            raise StoreError("a value in a query has characters that it may not have")
        return value

    def runs_recent(self, limit: int = 20) -> list[RunRecord]:
        return self._records(self._query(RUNS, "PartitionKey eq 'r'", limit), RunRecord)

    def run_put(self, run: RunRecord) -> None:
        self._upsert(RUNS, "r", f"{reverse_key(parse(run.started_at))}_{run.run_id}", run)

    def cases_recent(self, limit: int = 100, status: str | None = None) -> list[CaseRecord]:
        flt = "PartitionKey eq 'c'" + (f" and status eq '{self._quoted(status)}'" if status else "")
        cases = self._records(self._query(CASES, flt, PAGE), CaseRecord)
        return sorted(cases, key=lambda c: (c.updated_at, c.case_id), reverse=True)[:limit]

    def case_get(self, case_id: str) -> CaseRecord | None:
        row, _ = self._get(CASES, "c", case_id)
        return None if row is None else self._records([row], CaseRecord)[0]

    def case_put(self, case: CaseRecord) -> None:
        self._upsert(CASES, "c", case.case_id, case, status=case.status, updatedAt=case.updated_at)

    def plans_open(self) -> list[PlanRecord]:
        rows = self._query(PLANS, "PartitionKey eq 'p' and (state eq 'open' or state eq 'approved')", PAGE)
        return sorted(self._records(rows, PlanRecord), key=lambda p: (p.created_at, p.plan_id), reverse=True)

    def plans_recent(self, limit: int = 50) -> list[PlanRecord]:
        plans = self._records(self._query(PLANS, "PartitionKey eq 'p'", PAGE), PlanRecord)
        return sorted(plans, key=lambda p: (p.created_at, p.plan_id), reverse=True)[:limit]

    def plan_get(self, plan_id: str) -> PlanRecord | None:
        row, _ = self._get(PLANS, "p", plan_id)
        return None if row is None else self._records([row], PlanRecord)[0]

    def plan_put(self, plan: PlanRecord) -> None:
        self._upsert(PLANS, "p", plan.plan_id, plan, state=plan.state)

    def decisions_of_plan(self, plan_id: str) -> list[DecisionRecord]:
        rows = self._query(DECISIONS, f"PartitionKey eq '{self._quoted(plan_id)}'", 50)
        return sorted(self._records(rows, DecisionRecord), key=lambda d: (d.at, d.approver_oid))

    def decisions_by(self, oid: str, limit: int = 100) -> list[DecisionRecord]:
        rows = self._query(DECISIONS, f"approverOid eq '{self._quoted(oid)}'", PAGE)
        return sorted(self._records(rows, DecisionRecord), key=lambda d: (d.at, d.plan_id), reverse=True)[:limit]

    def decision_put(self, decision: DecisionRecord) -> bool:
        row, _ = self._get(DECISIONS, decision.plan_id, decision.approver_oid)
        if row is not None and self._records([row], DecisionRecord)[0].decision != "ask":
            return False
        if row is None:
            return self._insert(DECISIONS, decision.plan_id, decision.approver_oid, decision, approverOid=decision.approver_oid)
        self._upsert(DECISIONS, decision.plan_id, decision.approver_oid, decision, approverOid=decision.approver_oid)
        return True

    def action_get(self, plan_id: str) -> ActionRecord | None:
        row, _ = self._get(ACTIONS, "a", plan_id)
        return None if row is None else self._records([row], ActionRecord)[0]

    def action_put(self, action: ActionRecord) -> None:
        self._upsert(ACTIONS, "a", action.plan_id, action, state=action.state)

    def actions_recent(self, limit: int = 50) -> list[ActionRecord]:
        actions = self._records(self._query(ACTIONS, "PartitionKey eq 'a'", PAGE), ActionRecord)
        return sorted(actions, key=lambda a: (a.queued_at, a.plan_id), reverse=True)[:limit]

    def switch_get(self, name: str) -> SwitchRecord:
        if name not in SWITCH_NAMES:
            raise StoreError(f"{name} is not a switch")
        row, _ = self._get(SWITCHES, "w", name)
        return SwitchRecord(name=name) if row is None else self._records([row], SwitchRecord)[0]

    def switch_put(self, switch: SwitchRecord) -> None:
        if switch.name not in SWITCH_NAMES:
            raise StoreError(f"{switch.name} is not a switch")
        self._upsert(SWITCHES, "w", switch.name, switch)

    def switches(self) -> list[SwitchRecord]:
        return [self.switch_get(name) for name in SWITCH_NAMES]

    def settings_get(self, oid: str) -> SettingsRecord:
        row, _ = self._get(SETTINGS, "s", oid)
        return SettingsRecord(oid=oid) if row is None else self._records([row], SettingsRecord)[0]

    def settings_put(self, settings: SettingsRecord) -> None:
        self._upsert(SETTINGS, "s", settings.oid, settings)

    def settings_delete(self, oid: str) -> None:
        self._delete(SETTINGS, "s", oid)

    def notes_of(self, oid: str) -> list[NoteRecord]:
        rows = self._query(NOTES, f"PartitionKey eq '{self._quoted(oid)}'", 200)
        return sorted(self._records(rows, NoteRecord), key=lambda n: (n.created_at, n.note_id), reverse=True)

    def note_put(self, note: NoteRecord) -> None:
        self._upsert(NOTES, note.oid, note.note_id, note, kind=note.kind)

    def note_delete(self, oid: str, note_id: str) -> None:
        self._delete(NOTES, oid, note_id)

    def do_not_touch(self) -> set[str]:
        now = stamp(self.clock())
        notes = self._records(self._query(NOTES, "kind eq 'do_not_touch'", PAGE), NoteRecord)
        return {n.scope_resource_id.lower() for n in notes if n.scope_resource_id and (not n.expires_at or n.expires_at > now)}

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:48]

    def nonce_new(self, oid: str, purpose: str, ttl_seconds: int = 3600) -> str:
        token = secrets.token_urlsafe(24)
        expires = stamp(self.clock() + dt.timedelta(seconds=ttl_seconds))
        self._upsert(NONCES, "n", self._digest(token), None, oid=self._quoted(oid), purpose=self._quoted(purpose), expires=expires)
        return token

    def nonce_use(self, token: str, oid: str, purpose: str) -> bool:
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", token or ""):
            return False
        key = self._digest(token)
        row, etag = self._get(NONCES, "n", key)
        if row is None or row.get("oid") != oid or row.get("purpose") != purpose:
            return False
        if not self._delete(NONCES, "n", key, etag):
            return False
        return _text(row.get("expires")) > stamp(self.clock())

    def nonces_purge(self) -> int:
        """Removes the one-time tokens that have expired. Returns how many."""
        now = stamp(self.clock())
        removed = 0
        for row in self._query(NONCES, "PartitionKey eq 'n'", PAGE):
            if _text(row.get("expires")) <= now and self._delete(NONCES, "n", _text(row.get("RowKey"))):
                removed += 1
        return removed

    def mail_put(self, mail: MailRecord) -> None:
        self._upsert(MAILS, mail.oid, f"{compact(mail.sent_at)}_{mail.mail_id}", mail, kind=mail.kind)

    def mails_since(self, oid: str, since: str) -> list[MailRecord]:
        flt = f"PartitionKey eq '{self._quoted(oid)}' and RowKey ge '{self._quoted(compact(since))}'"
        return sorted(self._records(self._query(MAILS, flt, PAGE), MailRecord), key=lambda m: (m.sent_at, m.mail_id))
