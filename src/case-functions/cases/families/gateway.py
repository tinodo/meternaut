"""The family `scale-vpn-gateway`: lower the scale units of a point-to-site gateway of a virtual hub by one step, when nobody has been connected to it for days.

It changes a gateway that Meternaut planted itself, in its own resource group, with the approver's token (AGENTS.md rules 26 (a) and 29). No gateway is planted and none may be added (rule 15
(g): a virtual hub costs about 450 US dollars a month), so the planted gate (gates.py) holds every gateway back and this family makes no plan of a change in any estate until the owner
changes rule 26 (a). It is built and tested against fakes of Azure and has not run in Azure.

What Azure documents, as it was read on 2026-11-11 on Microsoft Learn:
- "P 2 s Vpn Gateways - Get" and "P 2 s Vpn Gateways - Create Or Update", api-version 2026-01-01: the gateway is `Microsoft.Network/p2svpnGateways`; its scale units are the property
  `properties.vpnGatewayScaleUnit`; they are changed by a PUT, which "creates a virtual wan p2s vpn gateway if it doesn't exist else updates the existing gateway" and answers 200, or 201 with
  `Azure-AsyncOperation` and `Retry-After`; the one PATCH of the resource changes tags only. A PUT states the whole gateway, so the body here is the gateway as it was read, with the keys that
  Azure itself fills in left out and one number changed. The page shows no If-Match header for it.
- "Virtual WAN FAQ": the sizes that exist and what each carries (families/capacity.py), and "be sure to plan for downtime in case you decide to scale up or down on the scale unit".
- "Configure a point-to-site User VPN connection - Microsoft Entra ID authentication": "It can take up to 30 minutes to update a hub."
- "Supported metrics - microsoft.network/p2svpngateways": `P2SConnectionCount`, a count, with the time grain P1D among its grains.
- "Azure permissions for Networking": the action that the approver's role must allow is the `write` of `Microsoft.Network/p2sVpnGateways` ("Puts a P2SVpnGateway").

The re-check is the family's own safety, and no rule of what counts as waste: before it acts it reads the gateway again (the scale units are the ones that the plan was made for, the
provisioning state is Succeeded) and the connection count of the last CONNECTION_DAYS closed days again (a value for at least CONNECTION_MIN_DAYS of them, and 0 at the most at one time), so a
gateway that somebody has begun to use is never scaled down on an old reading. A reading that cannot be made counts against the change.
"""
from __future__ import annotations

import copy
import datetime as dt

from ..http import HttpError, Refused
from ..models import CaseRecord, PlanRecord
from ..roles import clean_text
from . import calls, capacity
from .base import Env, Family, Located, Planned, Stop, Unreadable, Verdict, evidence_text, per_day_check, read_resource, refusal, skeptic_sentence
from .gates import Gates
from .words import CONNECTION_DAYS, CONNECTION_MIN_DAYS

UNITS = "vpnGatewayScaleUnit"
CONNECTIONS = "P2SConnectionCount"
METRIC_TIME = "%Y-%m-%dT%H:%M:%SZ"
# What Azure fills in itself (Learn, "P 2 s Vpn Gateways - Get": the tag etag is "a unique read-only string that changes whenever the resource is updated"; the provisioning states and the
# connection health are states of the gateway, not settings; and the previous policy group associations are what a connection was attached to before). They are not sent back.
READ_ONLY = frozenset({"etag", "provisioningState", "previousConfigurationPolicyGroupAssociations", "vpnClientConnectionHealth"})
UPDATING = "something else is changing the gateway right now"


def _properties(gateway: dict) -> dict:
    return gateway.get("properties") if isinstance(gateway.get("properties"), dict) else {}


def units_of(gateway: dict) -> int | None:
    """The scale units that the gateway has now, or None when Azure does not show a whole number from 1 to 200."""
    return capacity.whole(_properties(gateway).get(UNITS))


def provisioning_of(gateway: dict) -> str:
    """The provisioning state of the gateway in lower case (succeeded, updating, failed, ...); empty when none is shown."""
    state = _properties(gateway).get("provisioningState")
    return state.strip().lower()[:30] if isinstance(state, str) else ""


def aim_of(plan: PlanRecord) -> tuple[int, int]:
    """The scale units a plan changes from and to. It has to be exactly one step of the table of sizes (capacity.py), and any other plan is refused before it is used in a call."""
    target = plan.target if isinstance(plan.target, dict) else {}
    frm, to = capacity.whole(target.get("fromScaleUnit")), capacity.whole(target.get(UNITS))
    if frm is None or to is None or capacity.one_step_down(frm) != to:
        raise Stop("the request names a change of scale units that Meternaut does not make")
    return frm, to


def _without(node: object) -> object:
    """A copy of a value of the gateway without the keys that Azure fills in itself, at every depth."""
    if isinstance(node, dict):
        return {key: _without(value) for key, value in node.items() if key not in READ_ONLY}
    if isinstance(node, list):
        return [_without(item) for item in node]
    return node


def put_body(gateway: dict, units: int) -> dict:
    """The body of the PUT: the gateway as it was read (its place, its tags and every property that is not Azure's own), with the scale units changed and nothing else. Raises Stop when the
    gateway shows no place, which a PUT needs."""
    place = gateway.get("location")
    if not isinstance(place, str) or not place.strip():
        raise Stop("the gateway shows no location, which Azure needs to change it")
    properties = _without(copy.deepcopy(_properties(gateway)))
    properties[UNITS] = units  # type: ignore[index]
    body: dict = {"location": place, "properties": properties}
    if isinstance(gateway.get("tags"), dict):
        body["tags"] = copy.deepcopy(gateway["tags"])
    return body


def _span(now: dt.datetime) -> str:
    """The last CONNECTION_DAYS closed days (UTC) as the `timespan` of Azure Monitor: from midnight that many days ago to the midnight that starts today."""
    moment = now.replace(tzinfo=dt.timezone.utc) if now.tzinfo is None else now.astimezone(dt.timezone.utc)
    end = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return "/".join(point.strftime(METRIC_TIME) for point in (end - dt.timedelta(days=CONNECTION_DAYS), end))


def _day_of(stamp: object) -> dt.date | None:
    """The day of a bucket of Azure Monitor, when its time is the start of a UTC day; None for any other time (the table of usage.py is the Watch's and the page's, not a family's)."""
    try:
        moment = dt.datetime.strptime(str(stamp), METRIC_TIME)
    except ValueError:
        return None
    return moment.date() if moment.time() == dt.time(0, 0) else None


def _highest(data: object, now: dt.datetime) -> tuple[int, float]:
    """The days with a value and the highest value, from the answer of Azure Monitor for one metric in daily buckets. A bucket is a value when it is a day of the span that was asked for and
    its maximum is a finite number that is not below zero; any other bucket is a gap. Raises Stop for an answer of another shape."""
    found = data.get("value") if isinstance(data, dict) else None
    metric = next((item for item in found if isinstance(item, dict)), None) if isinstance(found, list) else None
    if metric is None or str(metric.get("errorCode") or "Success").lower() != "success" or not isinstance(metric.get("timeseries"), list):
        raise Stop("Azure Monitor did not answer with the connection count of the gateway", unread=True)
    first = dt.datetime.strptime(_span(now).split("/")[0], METRIC_TIME).date()
    days: dict[dt.date, float] = {}
    for series in metric["timeseries"]:
        for point in (series.get("data") if isinstance(series, dict) and isinstance(series.get("data"), list) else []):
            day = _day_of(point.get("timeStamp")) if isinstance(point, dict) else None
            value = point.get("maximum") if isinstance(point, dict) else None
            if day is None or not 0 <= (day - first).days < CONNECTION_DAYS or isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value < 0:
                continue
            days[day] = max(days.get(day, 0.0), float(value))
    return len(days), max(days.values(), default=0.0)


def read_connections(env: Env, located: Located) -> tuple[int, float]:
    """The days of the last CONNECTION_DAYS that have a value of the connection count and the most connections at one time in them (Learn, "Metrics - List"), read with the token of `env`.
    Raises Stop when it cannot be read."""
    query = f"metricnames={CONNECTIONS}&timespan={_span(env.clock())}&interval=P1D&aggregation=Maximum"
    try:
        data = env.azure.get(located.url(calls.METRICS, query, api=calls.METRICS_API)).json()
    except HttpError as error:
        if error.status in (401, 403):
            raise Stop(refusal(error, "read the connection count of the gateway"), "azure_refused") from error
        raise Stop(f"the connection count of the gateway could not be read ({error.status or 'no answer'})", unread=True) from error
    except Refused as error:
        raise Stop("the app may not read the connection count of the gateway", unread=True) from error
    return _highest(data, env.clock())


def nobody(days: int, peak: float) -> str | None:
    """None when the reading shows that nobody was connected; else the plain reason why it does not."""
    if days < CONNECTION_MIN_DAYS:
        return (f"Azure Monitor shows the connection count of the gateway for {days} of the last {CONNECTION_DAYS} days, so it is not known that nobody uses it "
                f"(at least {CONNECTION_MIN_DAYS} days with a value are needed)")
    if peak > 0:
        return f"users were connected to the gateway in the last {CONNECTION_DAYS} days (up to {peak:g} at one time)"
    return None


class ScaleVpnGateway(Family):
    """Changes the scale units of a point-to-site gateway to the next lower size of the table, never below 1. The target is chosen by code from the table; no model supplies it."""

    name = "scale-vpn-gateway"
    summary = "lower the scale units of a point-to-site gateway by one step (never below 1) when nobody has been connected for days"
    does = "change the scale units of the gateway"
    kinds = (calls.P2S_GATEWAY,)
    recommendations = ("change",)
    reads_to_plan = True

    def facts(self, env: Env, lead: object, located: Located) -> dict:
        try:
            gateway = read_resource(env, located)
            if gateway is None:
                raise Unreadable("the gateway does not exist any more")
            days, peak = read_connections(env, located)
        except Stop as stop:
            raise Unreadable(str(stop)) from stop
        return {"units": units_of(gateway), "provisioning": provisioning_of(gateway), "days": days, "peak": peak}

    def plan(self, case: CaseRecord, lead: object, facts: dict, located: Located, gates: Gates) -> Planned | str:
        units, state = facts.get("units"), facts.get("provisioning", "")
        if units is None:
            return "Azure does not show the scale units of the gateway as a number from 1 to 200"
        if state != "succeeded":
            return f"the last operation on the gateway is not finished or did not work (its provisioning state is {clean_text(state, 20) or 'not shown'}): {UPDATING}"
        to = capacity.one_step_down(units)
        if to is None:
            return "the gateway has 1 scale unit, the smallest size, so there is nothing to scale down"
        why = nobody(facts.get("days", 0), facts.get("peak", 0.0))
        if why is not None:
            return why
        group = clean_text(getattr(lead, "resource_group"), 90)
        name = clean_text(getattr(lead, "name"), 120)
        now_limit, then_limit = capacity.connections_of(units), capacity.connections_of(to)
        carries = (f" With {to} it carries up to {then_limit:,} connections at one time and {capacity.mbps_of(to):,} Mbps, down from {now_limit:,} and {capacity.mbps_of(units):,}."
                   if now_limit and then_limit else "")
        return Planned(
            title=f"Scale a point-to-site gateway down to {to} scale units in resource group {group}",
            what_changes=(f"When you approve, Meternaut changes the scale units of the point-to-site gateway named {name} in resource group {group} "
                          f"(subscription {getattr(lead, 'subscription_id')[:8]}) from {units} to {to}, with your own permissions. It sends the gateway back to Azure as it was read, with that one "
                          f"number changed. Right before it acts, it reads the gateway and its connection count again and stops unless the gateway still has {units} scale units, its last operation "
                          f"worked, nobody was connected in the last {CONNECTION_DAYS} days, and it is still tagged as planted by Meternaut, still in this resource group and not locked."),
            could_go_wrong=("Azure says to plan for downtime when the scale units of a gateway change, so users who are connected may be disconnected while it changes, and that a hub update "
                            f"can take up to 30 minutes.{carries} If your account may not change the gateway, Azure refuses and nothing changes. {skeptic_sentence(case)}"),
            undo=(f"Set the scale units back to {units} on the Point to site page of the virtual hub in the Azure portal, or with az network p2s-vpn-gateway update --scale-unit {units}. "
                  "That change takes minutes too, and may disconnect users again."),
            evidence=evidence_text(lead, f"the gateway has {units} scale units and its last operation worked, and the most users connected at one time in the {facts.get('days')} of the "
                                         f"last {CONNECTION_DAYS} days that have a value was {facts.get('peak'):g}, as Azure shows it now (read by code)."),
            target={"vpnGatewayScaleUnit": to, "fromScaleUnit": units},
            preconditions={"family": self.name, "resourceType": getattr(lead, "resource_type"), "tag": gates.planted_tag, "resourceGroup": getattr(lead, "resource_group").lower(),
                           "quietDays": CONNECTION_DAYS},
            saving_usd_month=self.saving(case, lead, {"units": units, "target": to}))

    def saving(self, case: CaseRecord, lead: object, facts: dict) -> float | None:
        """The cost lines of the last 30 days of the gateway, scaled by the share of its scale units that is taken away. An estimate (the price list is not read), so a person reads it as Scenario."""
        cost, units, target = case.cost_usd_30d, facts.get("units"), facts.get("target")
        if not cost or not units or not target or target >= units:
            return None
        return round(cost * (1 - target / units), 2)

    def check_state(self, env: Env, plan: PlanRecord, located: Located, resource: dict) -> None:
        frm, to = aim_of(plan)
        units, state = units_of(resource), provisioning_of(resource)
        if units == to and state == "succeeded":
            return  # the aim already: `already` says so
        if state != "succeeded":
            raise Stop(f"the last operation on the gateway is not finished or did not work (its provisioning state is {clean_text(state, 20) or 'not shown'}): {UPDATING}")
        if units != frm:
            raise Stop("the gateway does not have the scale units that the request was made for any more")
        why = nobody(*read_connections(env, located))
        if why is not None:
            raise Stop(why)

    def already(self, plan: PlanRecord, resource: dict) -> str:
        try:
            _, to = aim_of(plan)
        except Stop:
            return ""
        if units_of(resource) == to and provisioning_of(resource) == "succeeded":
            return f"The gateway already had {to} scale units when Meternaut looked. Nothing to change."
        return ""

    def call(self) -> calls.Call:
        return calls.write_for(calls.PUT, calls.P2S_GATEWAY)

    def write(self, env: Env, plan: PlanRecord, located: Located):
        frm, to = aim_of(plan)
        gateway = read_resource(env, located)  # read once more, as late as it can be: the body is this reading with one number changed
        if gateway is None:
            raise Stop("the gateway does not exist any more")
        if units_of(gateway) != frm or provisioning_of(gateway) != "succeeded":
            raise Stop("the gateway changed after it was checked: it does not have the scale units that the request was made for, or its last operation is not finished")
        return env.azure.write(self.call(), located.url(), put_body(gateway, to))

    def verify(self, env: Env, plan: PlanRecord) -> Verdict:
        located = self.locate(plan.resource_id, env.gates)
        try:
            gateway = read_resource(env, located)
        except Stop:
            return Verdict("unknown", "The gateway could not be read, so it is not known how many scale units it has.")
        if gateway is None:
            return Verdict("unknown", "The gateway could not be found, so it is not known how many scale units it has.")
        try:
            _, to = aim_of(plan)
        except Stop:
            return Verdict("unknown", "The plan does not name a change of scale units that Meternaut makes, so the gateway is not judged against it.")
        units, state = units_of(gateway), provisioning_of(gateway)
        evidence = {"scaleUnits": units, "provisioning": state}
        if state in ("failed", "canceled"):
            return Verdict("failed", "Azure shows that the last operation on the gateway did not work. The scale units that it shows may be the ones that were asked for, and the gateway may keep running at the old size.", evidence)
        if units == to and state == "succeeded":
            return Verdict("done", f"Azure shows the gateway with {units} scale units, and its last operation worked.", {**evidence, "now": f"{units} scale units."})
        return Verdict("pending", "Azure does not show the new scale units as made yet.", evidence)

    def cost_check(self, before_30d, after_total, days_after):
        return per_day_check(before_30d, after_total, days_after, "the gateway")
