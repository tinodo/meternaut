"""The conversation references: where a card for one person goes.

When a person adds the app, or writes to it, Teams tells the bot which conversation that is and which Connector serves it (`serviceUrl`). The bot keeps that, one row for each person, in a
table of its own (`mnteams`) in the storage account of the loop, with the app's managed identity. A reference is what makes a proactive card possible: the Connector sends into a
conversation only when the bot says which one. It holds no token, no secret and no text of a message: the ids that Teams gave, the tenant, and the time it was written.

A reference is trusted only as far as the person it names: it is written from an activity whose token was checked (botauth.py) for a person on the list of people, and the address in it is one
of Teams' Connector (connector.SERVICE_URL), checked again when it is read. The cases app's list of calls does not hold this table: only the bot app reads and writes it.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Callable

from .connector import CONVERSATION_ID, GUID, MEMBER_ID, SERVICE_URL
from .http import Client
from .memory_store import stamp, utc_now
from .models import Record, StoreError
from .store import KEY, TableStore

REFERENCES = "mnteams"


@dataclass(frozen=True)
class Reference(Record):
    oid: str  # the directory object id of the person, in lower case: the key
    conversation_id: str  # the personal conversation of the person with the bot
    service_url: str  # the Connector that serves it: https://smba.trafficmanager.net/<region>/
    user_id: str  # the person's id in Teams (29:...), as the last activity named it
    tenant_id: str
    updated_at: str = ""

    def problems(self) -> list[str]:
        found = []
        if not GUID.fullmatch(self.oid or ""):
            found.append("the person is not a directory object id")
        if not CONVERSATION_ID.fullmatch(self.conversation_id or ""):
            found.append("the conversation id is not one of Teams")
        if not SERVICE_URL.fullmatch(self.service_url or ""):
            found.append("the address is not the Connector of Teams")
        if self.user_id and not MEMBER_ID.fullmatch(self.user_id):
            found.append("the id of the person in Teams is not an id")
        if not GUID.fullmatch(self.tenant_id or ""):
            found.append("the tenant is not a tenant id")
        return found


def references_calls(account: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The calls that the references table needs, in the form of store.table_calls: this one table of this one account, and nothing else."""
    host = re.escape(f"https://{account}.table.core.windows.net")
    entity = rf"/{REFERENCES}\(PartitionKey='{KEY}',RowKey='{KEY}'\)"
    return (
        ("POST", re.compile(host + "/Tables", re.I)),
        ("POST", re.compile(host + rf"/{REFERENCES}", re.I)),
        ("GET", re.compile(host + entity, re.I)),
        ("PUT", re.compile(host + entity, re.I)),
        ("DELETE", re.compile(host + entity, re.I)),
    )


def made(oid: str, conversation_id: str, service_url: str, user_id: str, tenant_id: str, now: dt.datetime) -> Reference:
    """The reference for a person, in the form that is kept (the object id and the tenant in lower case, the address with its closing slash). It raises ValueError for one that is not valid."""
    address = (service_url or "").strip()
    reference = Reference((oid or "").strip().lower(), (conversation_id or "").strip(), address if address.endswith("/") else address + "/", (user_id or "").strip(),
                          (tenant_id or "").strip().lower(), stamp(now))
    problems = reference.problems()
    if problems:
        raise ValueError("; ".join(problems))
    return reference


class ReferenceTable(TableStore):
    """The references, in Azure Table Storage: the machinery of the store, with a client whose list of calls holds this table alone."""

    def __init__(self, client: Client, token: Callable[[str], str], account: str, *, clock: Callable[[], dt.datetime] = utc_now) -> None:
        super().__init__(client, token, account, clock=clock)

    def reference_get(self, oid: str) -> Reference | None:
        row, _ = self._get(REFERENCES, "r", (oid or "").lower())
        found = None if row is None else self._records([row], Reference)[0]
        return found if found is not None and not found.problems() else None

    def reference_put(self, reference: Reference) -> None:
        if reference.problems():
            raise StoreError("a reference that is not valid is not kept")
        self._upsert(REFERENCES, "r", reference.oid, reference)

    def reference_delete(self, oid: str) -> None:
        self._delete(REFERENCES, "r", (oid or "").lower())


class MemoryReferences:
    """The same, in memory: for the tests, and for a process that has no table."""

    def __init__(self) -> None:
        self.rows: dict[str, Reference] = {}

    def reference_get(self, oid: str) -> Reference | None:
        found = self.rows.get((oid or "").lower())
        return found if found is not None and not found.problems() else None

    def reference_put(self, reference: Reference) -> None:
        if reference.problems():
            raise StoreError("a reference that is not valid is not kept")
        self.rows[reference.oid] = reference

    def reference_delete(self, oid: str) -> None:
        self.rows.pop((oid or "").lower(), None)
