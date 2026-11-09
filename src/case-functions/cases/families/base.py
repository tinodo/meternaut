"""The interface of a family of change, and what every family shares.

A family is one kind of change on one or more kinds of resource (AGENTS.md rule 26 (a)). It has its own plan text, its own re-check right before it acts, its own call to Azure, its own
check afterwards and its own test. The registry (registry.py) holds them; the runner and the approval loop know the interface and nothing of any one family.

The interface, in the order that a change goes through it:

- `matches(resource_type)` and `selects(recommendation)`: which resources and which recommendations of a finding lead to this family. A model's recommendation only selects among the
  families that match; it never makes a plan, and it supplies no parameter of one.
- `facts(env, lead, located)`: what code reads to write the plan (with the reader's token, and only for a resource that passed both gates): typed values, each checked against a pattern.
- `plan(case, lead, facts, located, gates)`: the fields of the plan that the family decides, written by code from the facts and the cost lines: a title (a verb, an object and a place), what
  changes, what could go wrong, how to undo it, the saving with its basis, the target (the parameters of the change) and the preconditions (the facts that are read again).
- `recheck(env, plan)`: right before the change, with the approver's token, read the resource and its locks again and stop unless every precondition still holds.
- `write(env, plan, located)`: the one call, made once. Its method and address are in calls.py, the api-version is the one that Microsoft's page for the call shows.
- `verify(env, plan)`: read the resource and say whether the change took effect: done, still being made, failed or not known. It makes no write, so the timer can run it with the reader's token.
- `words`: what the decision brief shows for a plan of this family (the headline, the change, what is read again, the risk, the undo) is not a method of the family: it is in words.py, which
  holds no way to reach Azure, so that the page, the letter and the card need no special case for any family and the brief can read it without loading the rest.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from ..http import HttpError, Refused, Response
from ..models import CaseRecord, PlanRecord
from . import words
from .azure import Azure
from .calls import ARM_HOST, LOCKS_API, NAME, RESOURCE_ID, Call, Kind
from .gates import ChangeScope, Gates


class Stop(Exception):
    """A check that fails before the change: the text says which, and nothing has been changed. `kind` is `stopped`, or `azure_refused` when Azure refused a read."""

    def __init__(self, message: str, kind: str = "stopped") -> None:
        super().__init__(message)
        self.kind = kind


class Unreadable(Exception):
    """What a plan needs could not be read, or is not as a plan needs it: the text says why in plain words, and no plan of a change is made (the advise plan asks a person instead)."""


@dataclass(frozen=True)
class Env:
    """What a family works with: the calls (with a token), the places and the mark that a change may be made on, and the do-not-touch notes (a person's third gate)."""

    azure: Azure
    gates: Gates
    do_not_touch: Callable[[], set[str]] = lambda: set()


@dataclass(frozen=True)
class Located:
    """The resource of a plan, found in a scope: the scope, the kind of resource and its name."""

    scope: ChangeScope
    kind: Kind
    name: str

    @property
    def path(self) -> str:
        return self.kind.path(self.scope, self.name)

    def url(self, suffix: str = "", query: str = "", api: str | None = None) -> str:
        extra = f"&{query}" if query else ""
        return f"https://{ARM_HOST}{self.path}{suffix}?api-version={api or self.kind.api}{extra}"


@dataclass(frozen=True)
class Planned:
    """What a family decides about a plan. The rest of the record (the ids, the approvers, the times, the digest) is the same for every family and is made by the approval loop."""

    title: str
    what_changes: str
    could_go_wrong: str
    undo: str
    evidence: str
    target: dict
    preconditions: dict
    saving_usd_month: float | None = None


@dataclass(frozen=True)
class Verdict:
    """What a read after the change shows: `done`, `pending` (the change is being made), `failed` (Azure says that it did not work), or `unknown` (what is shown is not what the plan
    wanted and not a failure either). `text` is a plain sentence of code; `evidence` is what was read, as typed values."""

    state: str
    text: str
    evidence: dict = field(default_factory=dict)


def sentence(text: str) -> str:
    """A sentence that ends in a full stop, whatever it ended in."""
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def skeptic_sentence(case: CaseRecord) -> str:
    """What the second AI said, as one sentence of code: how many objections it raised."""
    count = len(case.objections)
    return f"The Skeptic role raised {count} objection{'s' if count != 1 else ''}: they are in the notebook." if count else "The Skeptic role raised no objection."


NOT_MEASURED = "Not measured yet: the saving, which cost lines confirm after the change."
JUDGED_ROLES = "Judged: two AI roles running on different models agree."
JUDGED_AGENTS = "Judged: the Investigator proposed it, the Skeptic agreed, and code re-checked the numbers that the Investigator cited."


def per_day_check(before_30d: float | None, after_total: float, days_after: int, what: str) -> tuple[bool, str, float | None]:
    """What the cost lines after a change that lowers a cost without ending it say: the daily rate after against the daily rate before. Confirmed when it is lower; the saving that it
    shows is the difference over thirty days. `after_total` is the cost of the whole days after the day of the change, `days_after` how many they are. A resource that still bills has
    some cost in them: a total of nothing means that its lines are not in yet, and is never a confirmation (the runner does not even ask the family then)."""
    if before_30d is None or before_30d <= 0 or days_after <= 0:
        return False, "Not confirmed: there are no cost lines from before the change to compare with.", None
    if after_total <= 0:
        return False, f"Not confirmed: there is no cost line of {what} after the day of the change to compare with yet.", None
    before_day, after_day = before_30d / 30, after_total / days_after
    if after_day < before_day:
        saved = round((before_day - after_day) * 30, 2)
        return True, f"Confirmed: the cost lines of {what} after the day of the change are lower: {round(after_day, 2)} a day against {round(before_day, 2)} before.", saved
    return False, f"Not confirmed: the cost lines of {what} after the day of the change are {round(after_day, 2)} a day against {round(before_day, 2)} before.", None


def evidence_text(lead: object, observed: str) -> str:
    """What the plan rests on, in three parts: what code read (`observed`), who judged it, and what is not measured yet. The judges differ by where the finding came from."""
    judged = JUDGED_AGENTS if getattr(lead, "detector", "") == "investigation" else JUDGED_ROLES
    return f"Observed now: {observed} {judged} {NOT_MEASURED}"


def locate(resource_id: str, gates: Gates, kinds: tuple[Kind, ...]) -> Located:
    """The resource of an id, found in a scope and of one of these kinds. Raises Stop when the id is not one that may be changed."""
    found = RESOURCE_ID.fullmatch(resource_id or "")
    if found is None:
        raise Stop("the plan names a resource that is not in the one resource group, subscription and kind that a change may be made on")
    subscription, group, provider, collection, name = found.groups()
    scope = gates.scope_of(subscription, group)
    kind = next((k for k in kinds if k.provider.lower() == provider.lower() and k.collection.lower() == collection.lower()), None)
    if scope is None or kind is None or not re.fullmatch(NAME, name):
        raise Stop("the plan names a resource that is not in the one resource group, subscription and kind that a change may be made on")
    return Located(scope, kind, name)


def read_resource(env: Env, located: Located, suffix: str = "", query: str = "") -> dict | None:
    """The resource as Azure shows it now; None when Azure says that it does not exist. Raises Stop when the person may not read it or it cannot be read."""
    try:
        data = env.azure.get(located.url(suffix, query)).json()
    except HttpError as error:
        if error.status == 404:
            return None
        if error.status in (401, 403):
            raise Stop(refusal(error, "read the resource"), "azure_refused") from error
        raise Stop(f"the resource could not be read ({error.status or 'no answer'})") from error
    except Refused as error:
        raise Stop("the app may not read this resource") from error
    if not isinstance(data, dict):
        raise Stop("Azure answered with something that is not a resource")
    return data


class Family:
    """One family of change. A subclass sets the class attributes and the methods that differ; the gates, the re-check and the reads are here."""

    name: str = ""
    summary: str = ""  # what the family does, as the console says it: "delete an unattached managed disk"
    kinds: tuple[Kind, ...] = ()
    recommendations: tuple[str, ...] = ()
    detectors: tuple[str, ...] = ()  # the older detectors whose leads this family takes (they stay only for waste that Meternaut plants itself)
    deletes: bool = False  # the change removes the resource: a resource that is not there is the aim, not a fault
    reads_to_plan: bool = False  # a plan needs facts that code reads from Azure first (a delete of an unattached disk or address needs none: the lead says it)
    does: str = "delete the resource"  # what the change does, for the words of a refusal: "Azure refused to delete the resource ..."

    @property
    def called(self) -> str:
        """The change as a noun of a sentence ("The delete was refused or failed ..."): the family's own word in words.py, where the brief reads it too."""
        return words.SHOWN[self.name].called

    @property
    def cost_ends(self) -> bool:
        """Whether the change ends the cost of the resource (a delete, a stop), so that no cost line after it is the aim. A resize or a change of tier only lowers the cost: the resource still
        bills, so a missing cost line after it means that the line is not in yet. The flag is in words.py, where the brief reads it too."""
        return words.SHOWN[self.name].cost_ends

    # -- which resources and which findings ------------------------------------------------------------------------------------------------------------------

    def matches(self, resource_type: str) -> bool:
        return (resource_type or "").lower() in {kind.type for kind in self.kinds}

    def selects(self, recommendation: str | None) -> bool:
        return (recommendation or "") in self.recommendations

    def locate(self, resource_id: str, gates: Gates) -> Located:
        """The resource of an id, found in a scope and of a kind of this family. Raises Stop when the id is not one that this family may change."""
        return locate(resource_id, gates, self.kinds)

    # -- the facts and the plan ------------------------------------------------------------------------------------------------------------------------------

    def facts(self, env: Env, lead: object, located: Located) -> dict:
        """What code reads to write the plan. The default reads nothing: the lead already says what the plan needs. Raises Unreadable."""
        return {}

    def needs_reads(self, lead: object) -> bool:
        """Whether the plan needs facts that code reads from Azure first."""
        return self.reads_to_plan

    def plan(self, case: CaseRecord, lead: object, facts: dict, located: Located, gates: Gates) -> Planned | str:
        """The plan as the family writes it, or the plain reason why there is none."""
        raise NotImplementedError

    def saving(self, case: CaseRecord, lead: object, facts: dict) -> float | None:
        """What the change is worth a month, from the cost lines of the case, or None. Never a model's figure."""
        return case.saving_usd_month if case.cost_usd_30d else None

    # -- the re-check -----------------------------------------------------------------------------------------------------------------------------------------

    def check_state(self, env: Env, plan: PlanRecord, located: Located, resource: dict) -> None:
        """The checks that are the family's own, on the resource as it is now. Raises Stop."""
        raise NotImplementedError

    def already(self, plan: PlanRecord, resource: dict) -> str:
        """A sentence that says that the end state that the plan wants holds already (so nothing is changed and the change is done), or an empty text."""
        return ""

    def recheck(self, env: Env, plan: PlanRecord) -> tuple[Located, dict | None]:
        """Reads the resource again and checks everything the plan states. Returns where it is and the resource, or None when it is gone already. Raises Stop when a check fails."""
        located = self.locate(plan.resource_id, env.gates)
        pre = plan.preconditions if isinstance(plan.preconditions, dict) else {}
        if pre.get("family") != plan.family or str(pre.get("resourceGroup", "")).lower() != located.scope.group.lower() or str(pre.get("resourceType", located.kind.type)).lower() != located.kind.type:
            raise Stop("the plan's own preconditions do not match what a change may be")
        resource = self.read(env, located)
        if resource is None:
            return located, None
        if str(resource.get("id", "")).lower() != plan.resource_id.lower():
            raise Stop("Azure answered with another resource than the one in the plan")
        tags = resource.get("tags") if isinstance(resource.get("tags"), dict) else {}
        tag = str(pre.get("tag", ""))
        if not tag or not any(str(k).lower() == tag.lower() and str(v).strip() for k, v in tags.items()):
            raise Stop(f"the resource does not carry the {pre.get('tag')} tag any more")
        why = env.gates.why_not_planted(tags, located.kind.type, located.name)
        if why is not None:
            raise Stop(why)
        self.check_state(env, plan, located, resource)
        if str(plan.resource_id).lower() in env.do_not_touch():
            raise Stop("a person marked the resource do-not-touch after the plan was made")
        if self.locked(env, located):
            raise Stop("the resource or its resource group has a management lock")
        return located, resource

    def read(self, env: Env, located: Located, suffix: str = "", query: str = "") -> dict | None:
        """The resource as Azure shows it now; None when Azure says that it does not exist. Raises Stop when the person may not read it or it cannot be read."""
        return read_resource(env, located, suffix, query)

    def locked(self, env: Env, located: Located) -> bool:
        for scope in (located.path, f"/subscriptions/{located.scope.subscription}/resourceGroups/{located.scope.group}"):
            url = f"https://{ARM_HOST}{scope}/providers/Microsoft.Authorization/locks?api-version={LOCKS_API}"
            try:
                data = env.azure.get(url).json()
            except HttpError as error:
                if error.status in (401, 403):
                    raise Stop(refusal(error, "read the locks"), "azure_refused") from error
                raise
            except Refused as error:
                raise Stop("the app may not read the locks, and an unread guard counts as on") from error
            if not isinstance(data, dict) or not isinstance(data.get("value", []), list):
                raise Stop("the locks could not be read, and an unread guard counts as on")
            if data.get("value"):
                return True
        return False

    # -- the change and the check after it --------------------------------------------------------------------------------------------------------------------

    def call(self) -> Call:
        """The write call of this family: one of calls.WRITES."""
        raise NotImplementedError

    def write(self, env: Env, plan: PlanRecord, located: Located) -> Response:
        raise NotImplementedError

    def verify(self, env: Env, plan: PlanRecord) -> Verdict:
        """Reads the resource and says whether the change took effect. Never writes. Raises Stop only for a plan that names a resource that is not a family's to change."""
        raise NotImplementedError

    def cost_check(self, before_30d: float | None, after_total: float, days_after: int) -> tuple[bool, str, float | None]:
        """What the cost lines after the change say, once they are there: whether they confirm the saving, a plain sentence, and the saving a month that they show (or None).
        The default is that of a change that stops a cost altogether (a delete, a stop): no cost line is left."""
        if after_total == 0:
            return True, "Confirmed: no cost lines for this resource after the day of the change.", None
        return False, f"Not confirmed: cost lines of {after_total} still exist after the day of the change.", None


def refusal(error: HttpError, what: str) -> str:
    """The plain words for an answer of Azure that says that the person may not do this, with the error's name."""
    named = re.search(r": \d{3} ([A-Za-z]{4,60})", str(error))
    return (f"Azure refused to {what} ({error.status}{', ' + named.group(1) if named else ''}): your account has no right to do this here. "
            "Nothing was changed.")


def unreadable(error: Exception) -> str:
    """Why a read for a plan failed, in plain words."""
    if isinstance(error, Refused):
        return "the app may not read this resource"
    if isinstance(error, HttpError):
        return f"Azure did not answer the read ({error.status or 'no answer'})"
    return "the read failed"
