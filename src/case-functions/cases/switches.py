"""The switches: the levels at which a person stops work (the switch `investigation` is the one that the agent harness and the drift check may also pull, and a person releases it), and the one rule for reading them."""
from __future__ import annotations

from .models import Store


def pulled(store: Store, *names: str) -> bool:
    """True when any of the named switches is pulled. A switch that cannot be read counts as pulled: a fault in the store stops the work."""
    try:
        return any(store.switch_get(name).paused for name in names)
    except Exception:  # noqa: BLE001 (every failure to read a switch is a pulled switch)
        return True
