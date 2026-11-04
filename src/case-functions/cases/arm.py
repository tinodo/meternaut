"""Read-only calls to Azure Resource Manager: Resource Graph, Cost Management, Advisor and management locks.

Nothing here writes. The two POSTs ask a question (a query), and `http.Client` refuses every other call.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable
from urllib.parse import urlsplit

from .http import ARM_HOST, Client, HttpError

ARM = f"https://{ARM_HOST}"
GRAPH_API = "2022-10-01"
COST_API = "2023-11-01"
ADVISOR_API = "2023-01-01"
LOCKS_API = "2016-09-01"
MAX_PAGES = 10


def _bad(what: str) -> HttpError:
    return HttpError(200, f"{what} gave an answer that the app does not understand")


class Arm:
    def __init__(self, client: Client, token: Callable[[str], str]) -> None:
        self.client, self.token = client, token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(ARM)}"}

    def _next(self, link: object, subscription: str, service: str) -> str | None:
        """A next-page link, only when it stays on the same service of the same subscription."""
        if not link:
            return None
        parts = urlsplit(str(link))
        prefix = f"/subscriptions/{subscription}/providers/{service}/".lower()
        if parts.scheme != "https" or parts.netloc.lower() != ARM_HOST or not parts.path.lower().startswith(prefix):
            raise _bad(service)
        return str(link)

    def graph(self, subscription: str, query: str) -> list[dict]:
        """The rows of one Resource Graph query in one subscription, every page of them."""
        rows: list[dict] = []
        skip = None
        for _ in range(MAX_PAGES):
            options: dict[str, object] = {"resultFormat": "objectArray", "$top": 1000}
            if skip:
                options["$skipToken"] = skip
            body = {"subscriptions": [subscription], "query": query, "options": options}
            data = self.client.request("POST", f"{ARM}/providers/Microsoft.ResourceGraph/resources?api-version={GRAPH_API}", headers=self._headers(),
                                       body=body, timeout=60).json()
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise _bad("Resource Graph")
            rows += [row for row in data["data"] if isinstance(row, dict)]
            skip = data.get("$skipToken")
            if not skip:
                return rows
        raise HttpError(0, f"Resource Graph returned more than {MAX_PAGES} pages")

    def costs(self, subscription: str, start: dt.date, end: dt.date) -> tuple[dict[str, float], str | None]:
        """Actual cost lines of every resource from start to end (both days included), by lower-case resource id, and their currency.

        The currency is None when there are no lines and "mixed" when the lines are in more than one.
        """
        body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {"from": f"{start.isoformat()}T00:00:00Z", "to": f"{end.isoformat()}T23:59:59Z"},
            "dataset": {"granularity": "None", "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                        "grouping": [{"type": "Dimension", "name": "ResourceId"}]},
        }
        url: str | None = f"{ARM}/subscriptions/{subscription}/providers/Microsoft.CostManagement/query?api-version={COST_API}"
        totals: dict[str, float] = {}
        currencies: set[str] = set()
        for _ in range(MAX_PAGES):
            data = self.client.request("POST", url, headers=self._headers(), body=body, timeout=60, retries=2, retry_after_max=60).json()
            properties = data.get("properties") if isinstance(data, dict) else None
            if not isinstance(properties, dict):
                raise _bad("Cost Management")
            names = [str(c.get("name", "")).lower() for c in properties.get("columns") or [] if isinstance(c, dict)]
            cost = next((names.index(n) for n in ("cost", "pretaxcost") if n in names), None)
            resource = names.index("resourceid") if "resourceid" in names else None
            currency = names.index("currency") if "currency" in names else None
            if cost is None or resource is None:
                raise _bad("Cost Management")
            for row in properties.get("rows") or []:
                try:
                    key, amount = str(row[resource]).lower(), float(row[cost])
                    code = str(row[currency]).upper() if currency is not None else None
                except (IndexError, TypeError, ValueError):
                    raise _bad("Cost Management") from None
                totals[key] = totals.get(key, 0.0) + amount
                if code:
                    currencies.add(code)
            url = self._next(properties.get("nextLink"), subscription, "Microsoft.CostManagement")
            if not url:
                return totals, (None if not currencies else currencies.pop() if len(currencies) == 1 else "mixed")
        raise HttpError(0, f"Cost Management returned more than {MAX_PAGES} pages")

    def _pages(self, subscription: str, url: str, service: str) -> list[dict]:
        found: list[dict] = []
        link: str | None = url
        for _ in range(MAX_PAGES):
            data = self.client.request("GET", link, headers=self._headers(), timeout=60).json()
            if not isinstance(data, dict) or not isinstance(data.get("value", []), list):
                raise _bad(service)
            found += [item for item in data.get("value", []) if isinstance(item, dict)]
            link = self._next(data.get("nextLink"), subscription, service)
            if not link:
                return found
        raise HttpError(0, f"{service} returned more than {MAX_PAGES} pages")

    def advisor_cost(self, subscription: str) -> list[dict]:
        url = (f"{ARM}/subscriptions/{subscription}/providers/Microsoft.Advisor/recommendations?api-version={ADVISOR_API}"
               "&$filter=Category%20eq%20%27Cost%27")
        return self._pages(subscription, url, "Microsoft.Advisor")

    def locks(self, subscription: str) -> list[str]:
        """The scope of every management lock of the subscription, lower case: the subscription, a group or one resource."""
        url = f"{ARM}/subscriptions/{subscription}/providers/Microsoft.Authorization/locks?api-version={LOCKS_API}"
        scopes = []
        for lock in self._pages(subscription, url, "Microsoft.Authorization"):
            lock_id = str(lock.get("id", ""))
            marker = "/providers/microsoft.authorization/locks/"
            index = lock_id.lower().find(marker)
            if index > 0:
                scopes.append(lock_id[:index].lower())
        return scopes
