"""What a scale unit of a point-to-site gateway carries, as Microsoft's own table gives it. Pure data and functions, standard library only and no call to Azure, so that the family
(families/gateway.py) and the analysis of a finding (cases/gateways.py) read one table.

Learn, "Virtual WAN FAQ", "For User VPN (point-to-site) - how many clients are supported?" and "What are Virtual WAN gateway scale units?" (read on 2026-11-11): one scale unit is 500 Mbps, the
table lists the sizes 1 to 20 one by one and then 40, 60 and so on to 200, and for each of them the connections that it supports at one time (1 to 3 units: 500, 4 to 6: 1,000, 7 to 10: 5,000,
11 to 20: 10,000, and 500 for each unit from 40 on). A size that the table does not list has no known limit here, and a gateway of such a size is not judged by it. Learn, "User VPN
(point-to-site) concepts": the scale units of a gateway range from 1 to 200.
"""
from __future__ import annotations

SIZES = (*range(1, 21), *range(40, 201, 20))
MBPS_PER_UNIT = 500
LIMITS = {**{units: 500 for units in range(1, 4)}, **{units: 1000 for units in range(4, 7)}, **{units: 5000 for units in range(7, 11)}, **{units: 10000 for units in range(11, 21)},
          **{units: units * 500 for units in range(40, 201, 20)}}


def whole(value: object) -> int | None:
    """A number of scale units: a whole number from 1 to 200, and nothing else (a flag, a text and a fraction are not one)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= SIZES[-1] else None


def connections_of(units: int) -> int | None:
    """The connections at one time that this many scale units support, or None for a size that the table does not list."""
    return LIMITS.get(units)


def mbps_of(units: int) -> int:
    return units * MBPS_PER_UNIT


def one_step_down(units: int) -> int | None:
    """The largest listed size below this one, or None for the smallest size: a gateway is never scaled below 1 unit."""
    return max((size for size in SIZES if size < units), default=None)


def smallest_for(peak: float) -> int | None:
    """The smallest listed size that supports at least `peak` connections at one time (1 unit when nobody was connected), or None when no size does."""
    return next((size for size in SIZES if LIMITS[size] >= max(peak, 1)), None)
