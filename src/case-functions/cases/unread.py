"""The data that a workspace takes in and that nothing reads: what code works out from what the tools recorded, for the person who decides.

The tools of the Investigator that look into a resource which keeps records of the data written to it record, for each kind of data (a table), the volume that is charged for
("Billable GB <kind>") and what reads it ("Readers <kind>": the rules, saved searches, workbooks and analytics rules that name the kind or read every kind at once; "Runs <kind>": the
queries that people ran and that name it). They record the whole volume and the kinds of resource of the largest writers of a kind of data too (cases/toolbox.py). This module reads that
record, never what the Investigator cited: a cited number says what the agent leaned on, and a figure rests on everything that the tools showed.

A kind of data counts as read by nothing only when the record shows a number for its readers and the number is 0. The number is there only when every source of readers was read: a source
that could not be read leaves it empty, and empty is unknown, never none. The runs are optional: where the record of the runs is not on there are none to show, and the page says so; where
it shows a run, the data is read. The figure is a scenario: the cost of the last 30 days in proportion to the volume that nothing reads, never above the cost. When the readers or the volume were
asked for and the record is not enough, no figure is made and the digest says what is missing. A record that holds a volume and never asked for the readers makes no claim: the finding is about
something else.

The digest is kept in the facts of the case (the key `unread`) as numbers, flags and the names of kinds of data, and the brief (cases/brief.py) reads it. The names of tables are text from the
estate for a person to read: the brief cuts and escapes them, and nothing here sends them to a model.
"""
from __future__ import annotations

import math
import re
from typing import Mapping

WORKSPACE = "microsoft.operationalinsights/workspaces"  # the kind of resource that keeps records of the data written to it
KEY = "unread"  # the key of the facts of a case
VOLUME, READERS, RUNS = "Billable GB ", "Readers ", "Runs "  # the names of the measurements that the tools record, before the kind of data
MAX_KINDS = 6  # the kinds that the digest lists, the largest first
MAX_LABEL = 120
WINDOW = 30  # the days of a measurement that records none
RESOURCE_TYPE = re.compile(r"[a-z0-9.]{1,60}(?:/[a-z0-9._-]{1,50}){1,4}")


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _measurements(block: Mapping) -> tuple[dict[str, tuple[float, int]], dict[str, float | None], dict[str, float | None]]:
    """The volume (and the days that it covers), the readers and the runs that the record holds, each by the kind of data. A reader count that is not a number is None."""
    metrics = block.get("metrics") if isinstance(block.get("metrics"), Mapping) else {}
    volume: dict[str, tuple[float, int]] = {}
    readers: dict[str, float | None] = {}
    runs: dict[str, float | None] = {}
    for name, aggregate in metrics.items():
        if not isinstance(name, str) or not isinstance(aggregate, Mapping):
            continue
        total = _number(aggregate.get("total"))
        for prefix, found in ((VOLUME, volume), (READERS, readers), (RUNS, runs)):
            kind = name[len(prefix):] if name.startswith(prefix) else ""
            if not kind or len(kind) > MAX_LABEL:
                continue
            if found is volume:
                if total is not None and total >= 0:
                    volume[kind] = (total, _count(aggregate.get("days")) or WINDOW)
            else:
                found[kind] = total
    return volume, readers, runs


def _whole(block: Mapping, days: int, held: float) -> float:
    """The whole volume of the window: the one that the tool reported when it covers the same days and is not smaller than the kinds that the record holds, else what the kinds add up to."""
    reported = block.get("volume") if isinstance(block.get("volume"), Mapping) else {}
    total = _number(reported.get("billable_gb"))
    return total if total is not None and _count(reported.get("days")) == days and total >= held else held


def _writers(block: Mapping, kind: str) -> list[str]:
    found = block.get("writers") if isinstance(block.get("writers"), Mapping) else {}
    types = found.get(kind) if isinstance(found.get(kind), list) else []
    return [item for item in types if isinstance(item, str) and RESOURCE_TYPE.fullmatch(item)][:3]


def analyse(block: object, cost: float | None, names: Mapping[str, str] | None = None) -> dict | None:
    """What the record of one resource holds about the data that nothing reads, as the digest for the facts of its case, or None when it holds nothing about data.

    `block` is Toolbox.evidence[handle], `cost` the cost of the last 30 days in US dollars (None when the cost lines could not be read) and `names` what the table handles of the run stand for
    (Toolbox.table_names). The digest has the days that the volume covers, the whole volume, the volume that nothing reads, its share, the listed kinds (each with its volume, its share, its
    runs, and its name and the kinds of its writers when they are known), how many unread kinds are not listed, how many kinds could not be checked, whether the record of the runs was read
    for every unread kind, and the cost and the figure when there is a cost. When no kind can be said to be read by nothing it is only {"missing": "volume"} (the volume was not read) or
    {"missing": "readers"} (what reads the data was not read in full)."""
    block = block if isinstance(block, Mapping) else {}
    volume, readers, runs = _measurements(block)
    if not (volume or readers or runs):
        return None
    days = max((window for _, window in volume.values()), default=WINDOW)
    here = {kind: gb for kind, (gb, window) in volume.items() if window == days}
    if not here:
        return {"missing": "volume"}
    held = sum(here.values())
    if held <= 0:
        return None
    whole = _whole(block, days, held)
    nothing: list[tuple[str, float, float | None]] = []
    unknown = 0
    for kind, gb in here.items():
        if gb <= 0:
            continue
        counted, ran = readers.get(kind), runs.get(kind)
        if (counted is not None and counted > 0) or (ran is not None and ran > 0):
            continue  # something reads it
        if counted is None:
            unknown += 1  # what reads it was not read in full, and that is unknown and not none
        else:
            nothing.append((kind, gb, ran))
    if not nothing:
        return {"missing": "readers"} if unknown and (readers or runs) else None  # the readers were asked for and could not be counted; a record that never asked has no claim to check
    nothing.sort(key=lambda item: (-item[1], item[0]))
    gone = sum(gb for _, gb, _ in nothing)
    share = min(1.0, gone / whole)
    named = names if isinstance(names, Mapping) else {}
    kinds = []
    for kind, gb, ran in nothing[:MAX_KINDS]:
        item: dict = {"kind": kind, "gb": round(gb, 3), "share": round(min(1.0, gb / whole), 4), "runs": None if ran is None else int(round(ran))}
        real = named.get(kind)
        if isinstance(real, str) and real and real != kind:
            item["name"] = real[:MAX_LABEL]
        writers = _writers(block, kind)
        if writers:
            item["writers"] = writers
        kinds.append(item)
    digest: dict = {"days": days, "billableGb": round(whole, 3), "unreadGb": round(gone, 3), "share": round(share, 4), "runsRecorded": all(ran is not None for _, _, ran in nothing),
                    "kinds": kinds, "more": max(0, len(nothing) - MAX_KINDS), "unknown": unknown}
    if cost is not None and math.isfinite(cost) and cost > 0:
        digest["costUsd30d"] = round(cost, 2)
        saving = round(min(cost, cost * share), 2)
        if saving > 0:
            digest["savingUsd"] = saving
    return digest
