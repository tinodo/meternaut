"""The point-to-site gateways that carry more scale units than anybody uses: what code works out from what the tools recorded, for the person who decides.

It is the analysis of a finding about such gateways, in the way that unread.py is the analysis of a finding about a workspace. It tells nobody what to look for: the Investigator finds the
gateways with its generic tools (the scale units of a resource are a number under a key that ends in Unit, a metric is read by its name), and code works out, from everything that the tools
recorded for each of them and not from what the agent cited, how many scale units each has, the most connections at one time that it saw, the smallest listed size that still carries them (the
table of families/capacity.py) and, where the cost lines of the last 30 days were read, a figure. The figure is a Scenario: the cost of a gateway in proportion to the scale units that would be
taken away, since the price list is not read. A gateway whose record lacks the scale units or the connections is counted as not counted, and never as a gateway with none.

The digest of one gateway, and the digest of many (the case of a group stands for all of them), have one shape, so that a digest of many is made from digests: `gateways` (how many the digest
stands for), `counted` (how many of them have both the scale units and the connections), and, over the counted ones, `units` (the scale units that they have together), `target` (what they would
have together at the smallest size for what each of them saw), `peak` (the most connections at one time on any of them), `days` (the fewest days with a value of any of them), `quiet` (how many
saw nobody) and, from the counted ones that have a cost, `costUsd30d` and `savingUsd`. The digest of one gateway also has `limit` (the connections that its scale units carry at one time, when the table
lists its size). It is kept in the facts of the case under `KEY` as numbers, and the brief (cases/brief.py) reads it.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping

from .families import capacity

TYPE = "microsoft.network/p2svpngateways"  # the kind of resource that the digest is for (Learn, "Supported metrics - microsoft.network/p2svpngateways", read on 2026-11-11)
KEY = "gateways"  # the key of the facts of a case
UNITS = "vpnGatewayScaleUnit"  # what the tools show of the scale units of a gateway: a number under this key of its properties
CONNECTIONS = "P2SConnectionCount"  # the metric that counts the connections of a gateway, as the tools record it
MAX_GATEWAYS = 100000  # the most gateways that a digest may stand for and still be believed


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def analyse(block: object, cost: float | None) -> dict:
    """The digest of one gateway, from the record of the tools for it (Toolbox.evidence[handle]) and its cost of the last 30 days in US dollars (None when the cost lines could not be read).

    A gateway that the record gives no scale units for, or no connection count for, is not counted: its digest stands for one gateway and counts none. A count of connections is known when the
    record holds a highest value, or a total of 0 with at least one day that had a value."""
    block = block if isinstance(block, Mapping) else {}
    properties = block.get("properties") if isinstance(block.get("properties"), Mapping) else {}
    metrics = block.get("metrics") if isinstance(block.get("metrics"), Mapping) else {}
    reading = metrics.get(CONNECTIONS) if isinstance(metrics.get(CONNECTIONS), Mapping) else {}
    units = capacity.whole(properties.get(UNITS))
    days = _count(reading.get("days_with_data")) or 0
    peak = _number(reading.get("max"))
    if peak is None and days and _number(reading.get("total")) == 0:
        peak = 0.0
    digest: dict = {"gateways": 1, "counted": 0, "units": 0, "target": 0, "peak": 0, "days": 0, "quiet": 0}
    if units is None or peak is None or peak < 0 or not days:
        return digest
    target = min(units, capacity.smallest_for(peak) or units)
    digest.update(counted=1, units=units, target=target, peak=int(peak) if peak == int(peak) else round(peak, 2), days=days, quiet=1 if peak == 0 else 0)
    limit = capacity.connections_of(units)
    if limit:
        digest["limit"] = limit  # what its scale units carry at one time, for the sentence about one gateway
    if cost is not None and math.isfinite(cost) and cost > 0:
        digest["costUsd30d"] = round(cost, 2)
        saving = round(cost * (units - target) / units, 2)
        if saving > 0:
            digest["savingUsd"] = saving
    return digest


def combine(digests: Iterable[object]) -> dict | None:
    """The digest of many gateways from the digests of each: None when none of them is a digest. The sums add up, the peak is the highest, the days are the fewest of the counted ones."""
    kept = [item for item in digests if isinstance(item, Mapping)]
    if not kept:
        return None
    counted = [item for item in kept if (_count(item.get("counted")) or 0) > 0]
    out: dict = {"gateways": sum(_count(item.get("gateways")) or 0 for item in kept), "counted": sum(_count(item.get("counted")) or 0 for item in counted),
                 "units": sum(_count(item.get("units")) or 0 for item in counted), "target": sum(_count(item.get("target")) or 0 for item in counted),
                 "peak": max((_number(item.get("peak")) or 0 for item in counted), default=0), "days": min((_count(item.get("days")) or 0 for item in counted), default=0),
                 "quiet": sum(_count(item.get("quiet")) or 0 for item in counted)}
    out["peak"] = int(out["peak"]) if out["peak"] == int(out["peak"]) else round(out["peak"], 2)
    if len(counted) == 1 and _count(counted[0].get("limit")):
        out["limit"] = counted[0]["limit"]
    costs = [_number(item.get("costUsd30d")) for item in counted]
    if any(cost is not None for cost in costs):
        out["costUsd30d"] = round(sum(cost for cost in costs if cost is not None), 2)
    savings = [_number(item.get("savingUsd")) for item in counted]
    saved = round(sum(saving for saving in savings if saving is not None), 2)
    if saved > 0:
        out["savingUsd"] = saved
    return out
