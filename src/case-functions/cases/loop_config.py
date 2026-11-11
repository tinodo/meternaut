"""The settings of the loop that follows a case: the store, the resource groups where a change may be made, the sign-in to Azure, the people, the console and the Teams cards.
They are optional as a whole.

When `STORE_ACCOUNT_NAME` is not set the app is the Watch alone (a run is written to the History and to nothing else), which is what it was before the loop.
When it is set, everything that the loop needs has to be set and valid, and the app refuses to start the loop with a part missing. The three settings of the
sign-in to Azure are set together or not at all: without them the loop works, but nobody can approve a change (the app says so). `MAIL_SENDER` is the shared mailbox that the
letters go from, and `TEAMS_CARDS_QUEUE` the name of the Storage queue, in the same storage account, that the Teams cards are put on (cases/teamsqueue.py): each is optional, and without
it that way of telling a person is off.

`CHANGE_SCOPES` is the list of Meternaut's OWN resource groups in which a change may be made: `<subscription id>/<resource group>`, separated by commas. The template gives it exactly the
one group where Meternaut plants waste of its own. Reading more does not widen it (AGENTS.md rule 29), and nothing here lets a change reach a resource that Meternaut did not plant:
cases/families/gates.py holds that second gate. An app that was deployed before the list existed has the two older settings `CHANGE_RESOURCE_GROUP` and `CHANGE_SUBSCRIPTION_ID`, which
name the same one group: they are read only when `CHANGE_SCOPES` is not set.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .families.gates import ChangeScope, Gates, parse_scopes

STORE_ACCOUNT_NAME = "STORE_ACCOUNT_NAME"
CHANGE_SCOPES = "CHANGE_SCOPES"
CHANGE_RESOURCE_GROUP = "CHANGE_RESOURCE_GROUP"
CHANGE_SUBSCRIPTION_ID = "CHANGE_SUBSCRIPTION_ID"
SIGNIN_TENANT_ID = "SIGNIN_TENANT_ID"
SIGNIN_CLIENT_ID = "SIGNIN_CLIENT_ID"
# The setting that the platform's own sign-in reads, too: the client id of the managed identity that presents the federated assertion of the app registration.
SIGNIN_ASSERTION_CLIENT_ID = "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"
CONSOLE_HOST = "CONSOLE_HOST"
MAIL_SENDER = "MAIL_SENDER"
# The name of the Storage queue (in the same storage account as the records) that a flow of Power Automate reads to post the Teams cards (cases/teamsqueue.py). Not set: no card is sent.
TEAMS_CARDS_QUEUE = "TEAMS_CARDS_QUEUE"
PLANTED_TAG = "PLANTED_TAG"
PLAN_TTL_HOURS = "PLAN_TTL_HOURS"
RECHECK_DAYS = "RECHECK_DAYS"

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ACCOUNT = re.compile(r"^[a-z0-9]{3,24}$")
# The name of a queue: 3 to 63 lowercase letters, digits and hyphens, beginning and ending with a letter or a digit, with no two hyphens in a row.
QUEUE = re.compile(r"^(?=.{3,63}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
GROUP = re.compile(r"^[A-Za-z0-9._()-]{1,90}$")
HOST = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,200}[a-z0-9])?$")
# The sender's address goes into a web address: only what mail.py accepts there.
SENDER_ADDRESS = re.compile(r"^[A-Za-z0-9._-]{1,64}@[A-Za-z0-9.-]{1,200}\.[A-Za-z]{2,24}$")
TAG = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
REQUIRED = (STORE_ACCOUNT_NAME, CONSOLE_HOST)
SIGNIN = (SIGNIN_TENANT_ID, SIGNIN_CLIENT_ID, SIGNIN_ASSERTION_CLIENT_ID)


class LoopConfigError(Exception):
    """One or more settings of the loop are missing or wrong; the text lists every one."""


@dataclass(frozen=True)
class LoopSettings:
    store_account: str
    change_scopes: tuple[ChangeScope, ...]
    console_host: str
    mail_sender: str | None
    planted_tag: str
    plan_ttl_hours: int
    recheck_days: int
    signin_tenant_id: str | None = None
    signin_client_id: str | None = None
    signin_assertion_client_id: str | None = None
    cards_queue: str | None = None  # the queue that the Teams cards are put on; None: no card is sent

    @property
    def base_url(self) -> str:
        return f"https://{self.console_host}"

    @property
    def gates(self) -> Gates:
        return Gates(self.change_scopes, self.planted_tag)


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


def _scopes(env: Mapping[str, str], problems: list[str]) -> tuple[ChangeScope, ...]:
    """The scopes of a change: CHANGE_SCOPES, or, when it is not set, the one group that the two older settings name. A problem is added to `problems`, never raised."""
    listed = (env.get(CHANGE_SCOPES) or "").strip()
    if listed:
        scopes, found = parse_scopes(listed)
        problems += [f"{CHANGE_SCOPES}: {problem}" for problem in found]
        return scopes
    group, subscription = (env.get(CHANGE_RESOURCE_GROUP) or "").strip(), (env.get(CHANGE_SUBSCRIPTION_ID) or "").strip()
    if not group and not subscription:
        problems.append(f"{CHANGE_SCOPES} is not set")
        return ()
    for name, value, pattern, what in ((CHANGE_RESOURCE_GROUP, group, GROUP, "a resource group name"), (CHANGE_SUBSCRIPTION_ID, subscription, GUID, "a subscription id")):
        if not value:
            problems.append(f"{name} is not set")
        elif not pattern.match(value):
            problems.append(f"{name} is not {what}")
    return (ChangeScope(subscription.lower(), group),) if group and subscription and GROUP.match(group) and GUID.match(subscription) else ()


def load(env: Mapping[str, str]) -> LoopSettings | None:
    """None when the loop is not configured at all; the settings when it is; LoopConfigError when it is half configured."""
    if not (env.get(STORE_ACCOUNT_NAME) or "").strip():
        return None
    problems = [f"{name} is not set" for name in REQUIRED if not (env.get(name) or "").strip()]
    values = {name: (env.get(name) or "").strip() for name in (*REQUIRED, *SIGNIN, MAIL_SENDER, TEAMS_CARDS_QUEUE, PLANTED_TAG)}
    values[CONSOLE_HOST] = values[CONSOLE_HOST].lower()
    for name, pattern, what in ((STORE_ACCOUNT_NAME, ACCOUNT, "a storage account name"), (CONSOLE_HOST, HOST, "a host name"), (TEAMS_CARDS_QUEUE, QUEUE, "a queue name"),
                                (SIGNIN_TENANT_ID, GUID, "a tenant id"), (SIGNIN_CLIENT_ID, GUID, "a client id"), (SIGNIN_ASSERTION_CLIENT_ID, GUID, "a client id")):
        if values[name] and not pattern.match(values[name]):
            problems.append(f"{name} is not {what}")
    scopes = _scopes(env, problems)
    given = [name for name in SIGNIN if values[name]]
    if given and len(given) != len(SIGNIN):
        problems.append(f"{', '.join(SIGNIN)} are set together or not at all")
    if values[MAIL_SENDER] and not SENDER_ADDRESS.match(values[MAIL_SENDER]):
        problems.append(f"{MAIL_SENDER} is not an address")
    if values[PLANTED_TAG] and not TAG.match(values[PLANTED_TAG]):
        problems.append(f"{PLANTED_TAG} is not a tag name")
    ttl = _integer(env, PLAN_TTL_HOURS, 1, 24 * 14, 72, problems)
    recheck = _integer(env, RECHECK_DAYS, 1, 90, 7, problems)
    if problems:
        raise LoopConfigError("; ".join(problems))
    return LoopSettings(
        store_account=values[STORE_ACCOUNT_NAME], change_scopes=scopes, console_host=values[CONSOLE_HOST].lower(), mail_sender=values[MAIL_SENDER] or None,
        planted_tag=values[PLANTED_TAG] or "meternaut-planted", plan_ttl_hours=ttl, recheck_days=recheck, signin_tenant_id=values[SIGNIN_TENANT_ID].lower() or None,
        signin_client_id=values[SIGNIN_CLIENT_ID].lower() or None, signin_assertion_client_id=values[SIGNIN_ASSERTION_CLIENT_ID].lower() or None,
        cards_queue=values[TEAMS_CARDS_QUEUE] or None)
