"""The family `change-setting`: lower a number of a resource, when a person approves it, in a group of the owner's real resources.

The Investigator states what a finding proposes as data (cases/proposals.py: a key path, the value that the tools showed and a smaller one), and code checked it against the tools of the same
run. This family makes it, as the person who approved it and with that person's own token (AGENTS.md rule 29). It knows no kind of resource and no setting: it takes the key path as the
platform spells it and reads the rest from the resource itself. It is held by the owner's line and the list of real groups (gates.py), and not by the planted gates of the other families.
It has never changed a real resource: it is built and tested against fakes of Azure.

It changes numbers that go down only (`0 <= to < from`), one to three on one resource, by a path of plain keys with no list in it. A path is relative to `properties`, as the tools show it, except a
path that starts with `sku`, which is at the root. A path that is not in the live resource, runs through a list or does not hold a plain number equal to `from` is refused. A tier, a flag, a text, a
list and a rebuild are other decisions and are not made here.

What Azure documents, as it was read on 2026-11-20:
- "Providers - Get", api-version 2021-04-01: the resource types of a namespace, each with its `apiVersions`. The newest that is not a preview is used; none means no plan.
- The resource provider contract of Azure Resource Manager (v1.0, in a public copy of it, because the page of the Azure repository did not load): a PUT states the whole resource and updates it when it
  exists (200, or 201 or 202 with Azure-AsyncOperation or Location); `name`, `type` and `id` belong to a GET; "if the user does a PUT with provisioningState (e.g. after doing a GET), the resource
  provider should treat the field as a normal readonly property"; and a PUT with no `If-Match` is 200 on a resource that exists. So the body here is the resource as it was read without
  `id`, `name`, `type` and `systemData` at the root and without `etag` and `provisioningState` at any depth, with the numbers changed and nothing else. No PATCH (many providers allow tags only) and
  no `If-Match` (not every provider checks it; the resource is read again just before the PUT).
- "Status of asynchronous operations": the address of Azure-AsyncOperation or Location is followed (families/lro.py) with the same token, on the reads that the client of this one request allows.

The re-check is the family's own safety and no rule of what counts as waste: it is the same resource in a real group, with no lock and no do-not-touch note, its last operation worked, every number
is as it was, and each cited measurement, read again over the same days, is not above what the plan recorded. A reading that cannot be made counts against the change.
"""
from __future__ import annotations

import copy
import datetime as dt
import math
from dataclasses import replace
from urllib.parse import quote

from .. import proposals
from ..http import HttpError, Refused
from ..models import CaseRecord, PlanRecord
from ..roles import clean_text
from . import calls, words
from .base import Env, Family, Located, Planned, Stop, Unreadable, Verdict, evidence_text, per_day_check, read_resource, refusal, skeptic_sentence, subscription_words
from .gates import Gates

ENVELOPE = frozenset({"id", "name", "type", "systemdata"})  # what only a GET has, at the root of the resource
READ_ONLY = frozenset({"etag", "provisioningstate"})  # what Azure fills in itself, at every depth
METRIC_TIME = "%Y-%m-%dT%H:%M:%SZ"
MAX_DAYS = 30
BUSY = "something else is changing the resource right now, or its last operation did not work"
# The words of a refusal right before the change, as the end of "Meternaut did not change the <kind>: ...", for the two gates of the owner.
GATES = {"outside": "the resource is not in a resource group on the owner's list of places where a real change may be made", "switch-off": "the owner has not allowed changes of real resources"}
Aim = tuple[str, float, float]


class Cannot(Stop, Unreadable):
    """No change can be made: `key` is the key of cases/proposals.py CANNOT that says why (the request that asks the person instead keeps it), and the text is the end of a sentence for a refusal."""

    def __init__(self, key: str, text: str = "") -> None:
        super().__init__(text or proposals.CANNOT[key])
        self.key = key


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _whole(value: object) -> bool:
    return _number(value) and value == int(value)  # type: ignore[arg-type]


def aims_of(settings: tuple[proposals.Setting, ...]) -> list[Aim]:
    """The settings that this family may make, as (path, from, to), or Cannot('unsupported'): one to three, each a path of plain keys, a number that goes down to one that is not below nothing, and a
    whole number only to a whole number. A path is not named twice."""
    found = [(item.path, item.now, item.to) for item in settings]
    if not found or len({path.lower() for path, _, _ in found}) != len(found):
        raise Cannot("unsupported")
    if any(not words.SETTING_PATH.fullmatch(path) or not _number(now) or not _number(to) or not 0 <= to < now or (_whole(now) and not _whole(to)) for path, now, to in found):
        raise Cannot("unsupported")
    return found  # type: ignore[return-value]


def _key(node: object, word: str) -> str | None:
    """The one key of a dict that is this word in any case; None when there is none or two."""
    found = [key for key in node if isinstance(key, str) and key.lower() == word.lower()] if isinstance(node, dict) else []
    return found[0] if len(found) == 1 else None


def find(resource: dict, path: str) -> tuple[dict, str, str] | None:
    """Where a key path is in the live resource: the dict that holds it, its key and the path in the live spelling (relative to `properties`, as the tools show it, except `sku`, which is at the
    root). None when it is not there or runs through a list."""
    keys = path.split(".")
    node: object = resource
    if keys[0].lower() != "sku":
        node = resource.get(_key(resource, "properties") or "")
    spelled = []
    for word in keys:
        key = _key(node, word)
        if key is None:
            return None
        spelled.append(key)
        parent, node = node, node[key]  # type: ignore[index]
    return parent, key, ".".join(spelled)  # type: ignore[return-value]


def provisioning_of(resource: dict) -> str:
    """The provisioning state of the resource in lower case; empty when none is shown."""
    properties = resource.get("properties")
    state = properties.get("provisioningState") if isinstance(properties, dict) else None
    return state.strip().lower()[:30] if isinstance(state, str) else ""


def values_of(resource: dict, aims: list[Aim]) -> list[object]:
    """What the live resource shows at each path of the settings: the plain number, or None when the path is not there or is no plain number."""
    shown = [find(resource, path) for path, _, _ in aims]
    return [w[0][w[1]] if w is not None and _number(w[0][w[1]]) else None for w in shown]


def judge(resource: dict, aims: list[Aim]) -> tuple[str, str] | None:
    """What stops the change on the live resource, as (the key of CANNOT, the end of a sentence), in the order unsupported, busy, mismatch; None when nothing does."""
    shown = values_of(resource, aims)
    for (path, _, _), value in zip(aims, shown):
        if value is None:
            return "unsupported", f"{proposals.label(path)} is not a plain number of the resource as Azure shows it now"
    if provisioning_of(resource) not in ("", "succeeded"):
        return "busy", BUSY
    for (path, now, _), value in zip(aims, shown):
        if value != now:
            return "mismatch", f"{proposals.label(path)} is {proposals.shown(value)} now and was {proposals.shown(now)} when the request was made"
    return None


def api_version(listing: object, collection: str) -> str | None:
    """The newest api-version of a resource type that is not a preview, from the answer of "Providers - Get"; None when the type is not listed or has none."""
    kinds = listing.get("resourceTypes") if isinstance(listing, dict) else None
    for item in kinds if isinstance(kinds, list) else []:
        if isinstance(item, dict) and str(item.get("resourceType", "")).lower() == collection.lower():
            return max((v for v in item.get("apiVersions", []) if isinstance(v, str) and calls.RELEASED.fullmatch(v)), default=None)
    return None


def aim_of(plan: PlanRecord) -> tuple[list[Aim], str]:
    """What a plan changes: its settings as (path, from, to) and the api-version that it is made with. A plan that names anything else is refused before it is used in a call."""
    target = plan.target if isinstance(plan.target, dict) else {}
    items = target.get("set") if isinstance(target.get("set"), list) else []
    api = target.get("apiVersion")
    try:
        aims = aims_of(tuple(proposals.Setting(i.get("path"), i.get("from"), i.get("to")) for i in items if isinstance(i, dict) and isinstance(i.get("path"), str)))
    except Cannot as error:
        raise Stop("the request names a change of a number that Meternaut does not make") from error
    if len(aims) != len(items) or not isinstance(api, str) or not calls.RELEASED.fullmatch(api):
        raise Stop("the request names a change of a number that Meternaut does not make")
    return aims, api


def _strip(node: object, top: bool = False) -> object:
    if isinstance(node, dict):
        return {key: _strip(value) for key, value in node.items() if str(key).lower() not in READ_ONLY and not (top and str(key).lower() in ENVELOPE)}
    return [_strip(item) for item in node] if isinstance(node, list) else node


def put_body(resource: dict, aims: list[Aim]) -> dict:
    """The body of the PUT: the resource as it was read, without what Azure fills in itself, with the numbers changed and nothing else. Raises Stop when a number is not where it was."""
    body = copy.deepcopy(resource)
    for path, _, to in aims:
        where = find(body, path)
        if where is None:
            raise Stop("the resource changed after it was checked: a number of the request is not in it any more")
        where[0][where[1]] = int(to) if isinstance(where[0][where[1]], int) and _whole(to) else to
    return _strip(body, top=True)  # type: ignore[return-value]


def read_total(env: Env, located: Located, name: str, days: int) -> float:
    """The total of a measurement over the last `days` days (Learn, "Metrics - List": the sum of the daily totals), read with the token of `env`. Raises Stop when it cannot be read."""
    end = env.clock().astimezone(dt.timezone.utc)
    span = "/".join(moment.strftime(METRIC_TIME) for moment in (end - dt.timedelta(days=days), end))
    try:
        data = env.azure.get(located.url(calls.METRICS, f"metricnames={quote(name, safe='')}&timespan={span}&interval=P1D&aggregation=Total", api=calls.METRICS_API)).json()
    except HttpError as error:
        if error.status in (401, 403):
            raise Stop(refusal(error, f"read {name}"), "azure_refused") from error
        raise Stop(f"{name} could not be read again ({error.status or 'no answer'})", unread=True) from error
    except Refused as error:
        raise Stop(f"the app may not read {name}", unread=True) from error
    found = data.get("value") if isinstance(data, dict) else None
    series = found[0].get("timeseries") if isinstance(found, list) and found and isinstance(found[0], dict) else None
    totals = [p.get("total") for item in series or [] if isinstance(item, dict) for p in item.get("data", []) if isinstance(p, dict)]
    totals = [value for value in totals if _number(value) and value >= 0]
    if not totals:
        raise Stop(f"Azure Monitor shows no value of {name} to compare with, and a reading that cannot be made counts against the change", unread=True)
    return math.fsum(totals)


def measured_of(preconditions: dict) -> list[tuple[str, float, int]]:
    """The measurements that a plan cites, as (name, total, days)."""
    items = preconditions.get("measured") if isinstance(preconditions.get("measured"), list) else []
    return [(i["name"], i["total"], i["days"]) for i in items if isinstance(i, dict) and isinstance(i.get("name"), str) and words.METRIC_WORDS.fullmatch(i["name"])
            and _number(i.get("total")) and i["total"] >= 0 and isinstance(i.get("days"), int) and 0 < i["days"] <= MAX_DAYS]


def cited(facts: object) -> list[dict]:
    """The measurements that the case cites, as typed values (name, total, days), at most three: the ones that Azure Monitor can be asked for again by name."""
    metrics, days = (facts.get("metrics"), facts.get("metricDays")) if isinstance(facts, dict) else (None, None)
    rows = [{"name": name, "total": total, "days": days[name]} for name, total in (metrics.items() if isinstance(metrics, dict) else []) if isinstance(days, dict) and name in days]
    return [row for row in rows if words.METRIC_WORDS.fullmatch(row["name"]) and _number(row["total"]) and row["total"] >= 0 and isinstance(row["days"], int) and 0 < row["days"] <= MAX_DAYS][:3]


class ChangeSetting(Family):
    """Lowers numbers of one resource to the smaller ones that a finding proposes, by a PUT of the resource as it was read. The numbers are data that code checked, never a model's words."""

    name = "change-setting"
    summary = words.SHOWN["change-setting"].summary
    does = "change the resource"
    recommendations = ("change",)
    reads_to_plan = True
    real = True  # held by the owner's line and the list of real groups (gates.py), and not by the planted gates

    def matches(self, resource_type: str) -> bool:
        return True

    def locate(self, resource_id: str, gates: Gates, api: str = "") -> Located:
        """The resource of an id in a group of REAL_CHANGE_SCOPES, at the api-version `api` when it is given. Raises Cannot (a Stop) when the id is not one that this family may change."""
        if calls.GENERIC_ID.fullmatch(resource_id or "") is None:
            raise Cannot("unsupported", "the request names a resource that is not a resource of the top level of a group")
        found = calls.located_for(resource_id, gates)
        if found is None:
            raise Cannot("outside", GATES["outside"])
        located = Located(*found)
        return replace(located, kind=replace(located.kind, api=api))

    # -- the facts and the plan ------------------------------------------------------------------------------------------------------------------------------

    def facts(self, env: Env, lead: object, located: Located | None = None) -> dict:
        """What the plan needs from Azure, in this order: the settings, the owner's gates, the do-not-touch note, the api-version that the provider lists, the resource and its locks. Raises Cannot."""
        found = proposals.settings(getattr(lead, "facts", {}))
        if not found:
            raise Unreadable("the finding proposes no number to change")  # the family does not apply: nothing is said about it
        aims = aims_of(found)
        located = self.locate(getattr(lead, "resource_id"), env.gates)
        why = env.gates.why_not_real(located.scope.subscription, located.scope.group)
        if why:
            raise Cannot(why, GATES[why])
        if located.path.lower() in env.do_not_touch():
            raise Cannot("do-not-touch")
        try:
            listing = env.azure.get(f"https://{calls.ARM_HOST}/subscriptions/{located.scope.subscription}/providers/{located.kind.provider}?api-version={calls.PROVIDERS_API}").json()
            api = api_version(listing, located.kind.collection)
            if api is None:
                raise Cannot("no-version")
            located = replace(located, kind=replace(located.kind, api=api))
            resource = read_resource(env, located)
            locked = resource is not None and self.locked(env, located)
        except Cannot:
            raise
        except (Stop, HttpError, Refused) as error:
            raise Cannot("unreadable") from error
        if resource is None:
            raise Cannot("unreadable")
        if locked:
            raise Cannot("locked")
        return {"resource": resource, "api": api, "aims": aims}

    def plan(self, case: CaseRecord, lead: object, facts: dict, located: Located, gates: Gates) -> Planned:
        resource, api, aims = facts["resource"], facts["api"], facts["aims"]
        stopped = judge(resource, aims)
        if stopped is not None:
            raise Cannot(stopped[0])
        sets = [{"path": find(resource, path)[2], "from": now, "to": to} for path, now, to in aims]  # type: ignore[index]
        target = {"set": sets, "apiVersion": api, "location": clean_text(str(resource.get("location") or ""), 40)}
        group, name = clean_text(getattr(lead, "resource_group"), 90), clean_text(getattr(lead, "name"), 120)
        pre = {"family": self.name, "resourceType": getattr(lead, "resource_type").lower(), "resourceGroup": group.lower(), "measured": cited(getattr(lead, "facts", {}))}
        kind, said, back, now = words.kind_words(getattr(lead, "resource_id")), words.changes_text(target), words.changes_text(target, "back"), words.changes_text(target, "now")
        reading = words.measured_text(pre)
        many = len(aims) != 1
        command = " ".join(f"{s['path'] if s['path'].lower().startswith('sku') else 'properties.' + s['path']}={proposals.shown(s['from'])}" for s in sets)
        return Planned(
            title=f"Scale down the {kind} {name} in resource group {group}: {said}",
            what_changes=(f"When you approve, Meternaut changes the {kind} {name} in resource group {group} (subscription {subscription_words(lead)}): {said}, with your own permissions. "
                          f"It sends the {kind} back to Azure as it was read, with only {'those numbers' if many else 'that number'} changed. Right before it acts, it reads the {kind} again and stops unless "
                          f"{'every old value is' if many else 'the old value is'} still the one shown here, the last operation on the {kind} worked, no lock and no do-not-touch note is on it, "
                          "and its resource group is still on the owner's list of places for real changes."
                          + (f" It also reads {words._list([n for n, _, _ in measured_of(pre)])} again over the same number of days, and stops if "
                             f"{'it is' if len(measured_of(pre)) == 1 else 'any of them is'} above what this request was made with." if reading else "")),
            could_go_wrong=(f"Meternaut does not know what a lower number takes away from what uses the {kind}. "
                            + (f"What it checked: {reading}, and that no lock is on the {kind}. " if reading else f"No measurement of its use is cited. It checked that no lock is on the {kind}. ")
                            + f"Azure carries out the update in the background and may need minutes: Meternaut follows it for half a minute, and a later check reads the {kind} again. "
                            f"If your account may not change the {kind}, Azure refuses and nothing changes. {skeptic_sentence(case)}"),
            undo=(f"Set {back} again: on the page of the {kind} in the Azure portal, or with az resource update --ids <resource id> --set {command} --api-version {api}. "
                  "That update takes minutes too and needs the same right."),
            evidence=evidence_text(lead, f"the {kind} shows {now} as Azure returns it now (read by code)." + (f" {reading}, which the AI's tools read and code checked." if reading else "")),
            target=target, preconditions=pre, saving_usd_month=case.saving_usd_month if (case.saving_usd_month or 0) > 0 else None)

    # -- the re-check -------------------------------------------------------------------------------------------------------------------------------------------

    def recheck(self, env: Env, plan: PlanRecord) -> tuple[Located, dict | None]:
        """Reads the resource again with the token of `env` and checks everything that the plan states: the same resource in a real group while the owner's line is on, no lock and no do-not-touch
        note, the last operation worked, every number as it was, and each cited measurement not above what the plan recorded. Raises Stop. Makes no call but reads."""
        aims, api = aim_of(plan)
        located = self.locate(plan.resource_id, env.gates, api)
        pre = plan.preconditions if isinstance(plan.preconditions, dict) else {}
        if pre.get("family") != plan.family or str(pre.get("resourceGroup", "")).lower() != located.scope.group.lower():
            raise Stop("the details of the request do not fit the resource that it names")
        why = env.gates.why_not_real(located.scope.subscription, located.scope.group)
        if why:
            raise Stop(GATES[why])
        resource = self.read(env, located)
        if resource is None:
            return located, None
        if str(resource.get("id", "")).lower() != plan.resource_id.lower():
            raise Stop("Azure answered with another resource than the one in the request")
        if plan.resource_id.lower() in env.do_not_touch():
            raise Stop("a person marked the resource do-not-touch after the request was made")
        if self.locked(env, located):
            raise Stop("the resource or its resource group has a management lock")
        if not self.already(plan, resource):
            stopped = judge(resource, aims)
            if stopped is not None:
                raise Stop(stopped[1])
            for name, total, days in measured_of(pre):
                now = read_total(env, located, name, days)
                if now > total:
                    raise Stop(f"{name} is {proposals.shown(round(now, 2))} over the last {days} days, above the {proposals.shown(total)} that the request was made with, so something may use the resource")
        return located, resource

    def already(self, plan: PlanRecord, resource: dict) -> str:
        try:
            aims, _ = aim_of(plan)
        except Stop:
            return ""
        if provisioning_of(resource) in ("", "succeeded") and values_of(resource, aims) == [to for _, _, to in aims]:
            return f"The {words.kind_words(plan.resource_id)} already showed {words.changes_text(plan.target, 'new')} when Meternaut looked. Nothing to change."
        return ""

    # -- the change and the check after it ---------------------------------------------------------------------------------------------------------------------

    def call(self) -> calls.Call:
        return calls.RESOURCE_PUT

    def write(self, env: Env, plan: PlanRecord, located: Located):
        aims, _ = aim_of(plan)
        resource = read_resource(env, located)  # read once more, as late as it can be: the body is this reading with the numbers changed
        if resource is None:
            raise Stop("the resource does not exist any more")
        stopped = judge(resource, aims)
        if stopped is not None:
            raise Stop(f"the resource changed after it was checked: {stopped[1]}")
        return env.azure.write(self.call(), located.url(), put_body(resource, aims))

    def verify(self, env: Env, plan: PlanRecord) -> Verdict:
        try:
            aims, api = aim_of(plan)
            resource = read_resource(env, self.locate(plan.resource_id, env.gates, api))
        except Stop:
            return Verdict("unknown", "The resource could not be read, so it is not known what it shows now.")
        if resource is None:
            return Verdict("unknown", "The resource could not be found, so it is not known what it shows now.")
        state, shown = provisioning_of(resource), values_of(resource, aims)
        evidence = {"values": shown, "provisioning": state}
        if state in ("failed", "canceled"):
            return Verdict("failed", "Azure shows that the last operation on the resource did not work. The numbers that it shows may be the ones that were asked for, and the resource may keep running as it did.", evidence)
        if state in ("", "succeeded") and shown == [to for _, _, to in aims]:
            now = words.changes_text(plan.target, "new")
            return Verdict("done", f"Azure shows the {words.kind_words(plan.resource_id)} with {now}, and its last operation worked.", {**evidence, "now": f"{now}."})
        return Verdict("pending" if state in ("", "succeeded", "updating") else "unknown", "Azure does not show the new numbers as made yet.", evidence)

    def cost_check(self, before_30d, after_total, days_after):
        return per_day_check(before_30d, after_total, days_after, "the resource")
