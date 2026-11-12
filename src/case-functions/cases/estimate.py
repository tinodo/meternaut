"""An estimate of what a managed disk that nothing uses costs in a month, at list price, for a finding that Azure has no cost line for.

It is an estimate and never a measurement. It is shown next to the words "Estimate at list price, not Azure's bill" and the date of the price table, and nowhere is it added to a figure that Cost
Management gave: not to the cost of a request, not to the totals of the Decisions page, not to what the learning counts and not to what the check after a change confirms. It is kept in a
record of its own (CaseRecord.estimate), never in `cost_usd_30d`, so that nothing downstream can mistake it for a cost line.

The table is the list price of each tier of a managed disk, in US dollars a month, in the region East US: the "Consumption" retail prices that the Azure Retail Prices API (Learn, "Azure
Retail Prices REST API overview") gave on TABLE_DATE for the meters "<tier> LRS Disk" and "<tier> ZRS Disk" of Standard HDD, Standard SSD and Premium SSD managed disks. The tiers and their
sizes are those of Learn, "Azure managed disk types" (read on the same day), which also says how a disk is billed: at the monthly price of the nearest offered size above the provisioned
size, prorated by the hour. The tiers up to 4096 GiB are listed; a disk of another type (Ultra Disk, Premium SSD v2: priced by capacity, operations and throughput) or of a larger size
has no estimate. Transactions of a Standard disk and snapshots are not in it. A disk in another region costs more or less: that is why it is an estimate.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from typing import NamedTuple

TABLE_DATE = "2026-11-12"
LABEL = "Estimate at list price, not Azure's bill"
MAX_SIZE_GIB = 4096
DISK_TYPE = "microsoft.compute/disks"  # the type of a managed disk, as Resource Graph gives it in lower case: the one kind of resource that has an estimate
SIZE_PROPERTY = "diskSizeGB"  # the property of a managed disk that holds its size in GiB

# sku (lower case, as Azure names the type of a disk) -> ((largest size of the tier in GiB, tier, list price in US dollars a month), ...), the smallest tier first.
TIERS = {
    "standard_lrs": ((32, "S4", 1.536), (64, "S6", 3.008), (128, "S10", 5.888), (256, "S15", 11.328), (512, "S20", 21.76), (1024, "S30", 40.96), (2048, "S40", 77.824),
                     (4096, "S50", 143.36)),
    "standardssd_lrs": ((4, "E1", 0.30), (8, "E2", 0.60), (16, "E3", 1.20), (32, "E4", 2.40), (64, "E6", 4.80), (128, "E10", 9.60), (256, "E15", 19.20), (512, "E20", 38.40),
                        (1024, "E30", 76.80), (2048, "E40", 153.60), (4096, "E50", 307.20)),
    "standardssd_zrs": ((4, "E1", 0.45), (8, "E2", 0.90), (16, "E3", 1.80), (32, "E4", 3.60), (64, "E6", 7.20), (128, "E10", 14.40), (256, "E15", 28.80), (512, "E20", 57.60),
                        (1024, "E30", 115.20), (2048, "E40", 230.40), (4096, "E50", 460.80)),
    "premium_lrs": ((4, "P1", 0.60), (8, "P2", 1.20), (16, "P3", 2.40), (32, "P4", 5.2795), (64, "P6", 10.207), (128, "P10", 19.71), (256, "P15", 38.012142), (512, "P20", 73.22),
                    (1024, "P30", 135.17), (2048, "P40", 259.0457), (4096, "P50", 495.5657)),
    "premium_zrs": ((4, "P1", 0.90), (8, "P2", 1.80), (16, "P3", 3.60), (32, "P4", 7.919), (64, "P6", 15.31), (128, "P10", 29.565), (256, "P15", 57.018), (512, "P20", 109.81),
                    (1024, "P30", 202.73), (2048, "P40", 388.57), (4096, "P50", 743.35)),
}
TIER = re.compile(r"[SEP][0-9]{1,2}")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


class Estimate(NamedTuple):
    """An estimate as a record keeps it: the monthly list price in US dollars, the tier that it is the price of, the date of the price table and how many disks it is the price of (more than one
    only for the sum that summed() makes for a row of findings)."""

    monthly: float
    tier: str
    table: str
    count: int = 1


def disk_estimate(sku: object, size_gb: object) -> dict:
    """The estimate of a managed disk of this type (as Azure names it: Standard_LRS, StandardSSD_LRS, Premium_ZRS) and this size in GiB, as a record keeps it, or an empty dict for a type or a
    size that the table does not have: the tier is the smallest one that holds the size."""
    tiers = TIERS.get(str(sku or "").strip().lower())
    if isinstance(size_gb, float) and size_gb.is_integer():
        size_gb = int(size_gb)  # a whole number that arrived as a float
    if tiers is None or isinstance(size_gb, bool) or not isinstance(size_gb, int) or not 1 <= size_gb <= MAX_SIZE_GIB:
        return {}
    for largest, tier, price in tiers:
        if size_gb <= largest:
            return {"usdMonth": round(price, 2), "tier": tier, "table": TABLE_DATE}
    return {}


def estimate_of(value: object) -> Estimate | None:
    """The estimate that a record holds, when it is what disk_estimate makes (a price above nothing, a tier of the table, a date); None for anything else."""
    if not isinstance(value, dict):
        return None
    price, tier, table = value.get("usdMonth"), value.get("tier"), value.get("table")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or not 0 < price < 1_000_000:
        return None
    if not isinstance(tier, str) or not TIER.fullmatch(tier) or not isinstance(table, str) or date_words(table) == "":
        return None
    return Estimate(float(price), tier, table)


def date_words(day: str) -> str:
    """A date as words ("12 November 2026"), or an empty text for a text that is not a date of the form YYYY-MM-DD."""
    try:
        moment = dt.date.fromisoformat(day) if isinstance(day, str) and len(day) == 10 else None
    except ValueError:
        moment = None
    return f"{moment.day} {MONTHS[moment.month - 1]} {moment.year}" if moment is not None else ""


def summed(estimates: "list[Estimate | None]") -> Estimate | None:
    """The estimates of several findings added up, when every one of them has one and they are of one price table: a sum of some of them would be a figure that nobody asked for. The tier of
    a sum is a list of the tiers, so that the text says what it rests on."""
    if not estimates or any(item is None for item in estimates) or len({item.table for item in estimates if item}) != 1:
        return None
    found = [item for item in estimates if item]
    tiers = sorted({item.tier for item in found})
    return Estimate(round(sum(item.monthly for item in found), 2), "/".join(tiers), found[0].table, sum(item.count for item in found))


def words(found: Estimate) -> str:
    """The estimate as the sentence that every page, letter and card says it with: that it is an estimate at list price and not Azure's bill, what it is the price of, and the date of the price
    table. Nothing but numbers of the table goes into it."""
    price = f"${found.monthly:,.2f}"
    what = "a disk of this type and size" if found.count == 1 else f"these {found.count} disks"
    tier = f"tier {found.tier}" if "/" not in found.tier else f"tiers {found.tier.replace('/', ', ')}"
    return f"{LABEL}: about {price} a month for {what} ({tier}). East US list prices of {date_words(found.table)}."
