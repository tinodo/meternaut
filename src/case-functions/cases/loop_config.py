"""The settings of the loop that follows a case: the store, the writer, the people and the console. They are optional as a whole.

When `STORE_ACCOUNT_NAME` is not set the app is the Watch alone (a run is written to the History and to nothing else), which is what it was before the loop.
When it is set, everything that the loop needs has to be set and valid, and the app refuses to start the loop with a part missing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

STORE_ACCOUNT_NAME = "STORE_ACCOUNT_NAME"
WRITER_RESOURCE_GROUP = "WRITER_RESOURCE_GROUP"
WRITER_SUBSCRIPTION_ID = "WRITER_SUBSCRIPTION_ID"
WRITER_CLIENT_ID = "WRITER_CLIENT_ID"
CONSOLE_HOST = "CONSOLE_HOST"
MAIL_SENDER = "MAIL_SENDER"
PLANTED_TAG = "PLANTED_TAG"
PLAN_TTL_HOURS = "PLAN_TTL_HOURS"
APPROVAL_DELAY_SECONDS = "APPROVAL_DELAY_SECONDS"
RECHECK_DAYS = "RECHECK_DAYS"

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ACCOUNT = re.compile(r"^[a-z0-9]{3,24}$")
GROUP = re.compile(r"^[A-Za-z0-9._()-]{1,90}$")
HOST = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,200}[a-z0-9])?$")
# The sender's address goes into a web address: only what mail.py accepts there.
SENDER_ADDRESS = re.compile(r"^[A-Za-z0-9._-]{1,64}@[A-Za-z0-9.-]{1,200}\.[A-Za-z]{2,24}$")
TAG = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
REQUIRED = (STORE_ACCOUNT_NAME, WRITER_RESOURCE_GROUP, WRITER_SUBSCRIPTION_ID, WRITER_CLIENT_ID, CONSOLE_HOST)


class LoopConfigError(Exception):
    """One or more settings of the loop are missing or wrong; the text lists every one."""


@dataclass(frozen=True)
class LoopSettings:
    store_account: str
    writer_group: str
    writer_subscription: str
    writer_client_id: str
    console_host: str
    mail_sender: str | None
    planted_tag: str
    plan_ttl_hours: int
    approval_delay_seconds: int
    recheck_days: int

    @property
    def base_url(self) -> str:
        return f"https://{self.console_host}"


def _integer(env: Mapping[str, str], name: str, low: int, high: int, default: int, problems: list[str]) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        problems.append(f"{name} is not a whole number")
        return default
    if not low <= value <= high:
        problems.append(f"{name} is not between {low} and {high}")
    return value


def load(env: Mapping[str, str]) -> LoopSettings | None:
    """None when the loop is not configured at all; the settings when it is; LoopConfigError when it is half configured."""
    if not (env.get(STORE_ACCOUNT_NAME) or "").strip():
        return None
    problems = [f"{name} is not set" for name in REQUIRED if not (env.get(name) or "").strip()]
    values = {name: (env.get(name) or "").strip() for name in (*REQUIRED, MAIL_SENDER, PLANTED_TAG)}
    values[CONSOLE_HOST] = values[CONSOLE_HOST].lower()
    for name, pattern, what in ((STORE_ACCOUNT_NAME, ACCOUNT, "a storage account name"), (WRITER_RESOURCE_GROUP, GROUP, "a resource group name"),
                                (WRITER_SUBSCRIPTION_ID, GUID, "a subscription id"), (WRITER_CLIENT_ID, GUID, "a client id"), (CONSOLE_HOST, HOST, "a host name")):
        if values[name] and not pattern.match(values[name]):
            problems.append(f"{name} is not {what}")
    if values[MAIL_SENDER] and not SENDER_ADDRESS.match(values[MAIL_SENDER]):
        problems.append(f"{MAIL_SENDER} is not an address")
    if values[PLANTED_TAG] and not TAG.match(values[PLANTED_TAG]):
        problems.append(f"{PLANTED_TAG} is not a tag name")
    ttl = _integer(env, PLAN_TTL_HOURS, 1, 24 * 14, 72, problems)
    delay = _integer(env, APPROVAL_DELAY_SECONDS, 30, 3600, 120, problems)
    recheck = _integer(env, RECHECK_DAYS, 1, 90, 7, problems)
    if problems:
        raise LoopConfigError("; ".join(problems))
    return LoopSettings(
        store_account=values[STORE_ACCOUNT_NAME], writer_group=values[WRITER_RESOURCE_GROUP], writer_subscription=values[WRITER_SUBSCRIPTION_ID].lower(),
        writer_client_id=values[WRITER_CLIENT_ID], console_host=values[CONSOLE_HOST].lower(), mail_sender=values[MAIL_SENDER] or None,
        planted_tag=values[PLANTED_TAG] or "meternaut-planted", plan_ttl_hours=ttl, approval_delay_seconds=delay, recheck_days=recheck)
