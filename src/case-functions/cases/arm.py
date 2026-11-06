"""Read-only calls to Azure Resource Manager: Resource Graph, Cost Management, Advisor, management locks, Azure Monitor metrics and the pricing settings of
Microsoft Defender for Cloud.

Nothing here writes. The two POSTs ask a question (a query), and `http.Client` refuses every other call.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from typing import Callable, NamedTuple
from urllib.parse import quote, urlsplit

from .http import ARM_HOST, SCOPE, Client, HttpError

ARM = f"https://{ARM_HOST}"
GRAPH_API = "2022-10-01"
COST_API = "2023-11-01"
ADVISOR_API = "2023-01-01"
LOCKS_API = "2016-09-01"
METRICS_API = "2023-10-01"
METRIC_DEFINITIONS_API = "2018-01-01"
SECURITY_API = "2024-01-01"
MAX_PAGES = 10
SCOPE_ID = re.compile(SCOPE, re.I)
GROUP_SCOPE = re.compile(r"^(/subscriptions/[^/]+/resourceGroups/[^/]+)", re.I)
RESOURCE_PATH = re.compile(r"/providers/[^/]+/[^/]+/[^/]+", re.I)
METRIC_TIME = "%Y-%m-%dT%H:%M:%SZ"


class CostLine(NamedTuple):
    """The cost of one resource under one service over the period: the resource id in lower case, the service name, the sum and the currency ("" when the
    answer has no currency column)."""

    resource_id: str
    service: str
    amount: float
    currency: str


class MetricPoint(NamedTuple):
    """One daily bucket of a metric. An aggregation that the metric does not have, or that has no value in the bucket, is None."""

    time: str
    total: float | None
    maximum: float | None
    average: float | None


def _bad(what: str) -> HttpError:
    return HttpError(200, f"{what} gave an answer that the app does not understand")


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _utc(moment: dt.datetime) -> dt.datetime:
    return moment.replace(tzinfo=dt.timezone.utc) if moment.tzinfo is None else moment.astimezone(dt.timezone.utc)


def scopes_of(resource_id: str) -> list[str]:
    """The resource itself and its resource group: the two scopes whose locks are asked for one by one."""
    group = GROUP_SCOPE.match(resource_id)
    scopes = [resource_id]
    if group and group.group(1).lower() != resource_id.lower():
        scopes.append(group.group(1))
    return scopes


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
        path = parts.path.lower()
        if parts.scheme != "https" or parts.netloc.lower() != ARM_HOST or not path.startswith(f"/subscriptions/{subscription}/".lower()) \
                or f"/providers/{service}/".lower() not in path + "/":
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

    def _cost_rows(self, subscription: str, start: dt.date, end: dt.date, dimensions: tuple[str, ...]) -> list[tuple[list[str], float, str]]:
        """Every row of one Cost Management query that groups the actual cost from start to end (both days included) by the dimensions: the value of each
        dimension in the order asked for, the sum of the cost and its currency ("" when the answer has no currency column)."""
        body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {"from": f"{start.isoformat()}T00:00:00Z", "to": f"{end.isoformat()}T23:59:59Z"},
            "dataset": {"granularity": "None", "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                        "grouping": [{"type": "Dimension", "name": name} for name in dimensions]},
        }
        url: str | None = f"{ARM}/subscriptions/{subscription}/providers/Microsoft.CostManagement/query?api-version={COST_API}"
        found: list[tuple[list[str], float, str]] = []
        for _ in range(MAX_PAGES):
            data = self.client.request("POST", url, headers=self._headers(), body=body, timeout=60, retries=2, retry_after_max=60).json()
            properties = data.get("properties") if isinstance(data, dict) else None
            if not isinstance(properties, dict):
                raise _bad("Cost Management")
            names = [str(c.get("name", "")).lower() for c in properties.get("columns") or [] if isinstance(c, dict)]
            cost = next((names.index(n) for n in ("cost", "pretaxcost") if n in names), None)
            places = [names.index(name.lower()) if name.lower() in names else None for name in dimensions]
            currency = names.index("currency") if "currency" in names else None
            if cost is None or None in places:
                raise _bad("Cost Management")
            for row in properties.get("rows") or []:
                try:
                    values, amount = [str(row[place]) for place in places], float(row[cost])
                    code = str(row[currency]).upper() if currency is not None else ""
                except (IndexError, TypeError, ValueError):
                    raise _bad("Cost Management") from None
                if not math.isfinite(amount):
                    raise _bad("Cost Management")
                found.append((values, amount, code))
            url = self._next(properties.get("nextLink"), subscription, "Microsoft.CostManagement")
            if not url:
                return found
        raise HttpError(0, f"Cost Management returned more than {MAX_PAGES} pages")

    def costs(self, subscription: str, start: dt.date, end: dt.date) -> tuple[dict[str, float], str | None]:
        """Actual cost lines of every resource from start to end (both days included), by lower-case resource id, and their currency.

        The currency is None when there are no lines and "mixed" when the lines are in more than one.
        """
        totals: dict[str, float] = {}
        currencies: set[str] = set()
        for (resource,), amount, code in self._cost_rows(subscription, start, end, ("ResourceId",)):
            key = resource.lower()
            totals[key] = totals.get(key, 0.0) + amount
            if code:
                currencies.add(code)
        return totals, (None if not currencies else currencies.pop() if len(currencies) == 1 else "mixed")

    def cost_lines(self, subscription: str, start: dt.date, end: dt.date) -> list[CostLine]:
        """The actual cost of every resource under every service from start to end (both days included): one line for each pair, with the resource id in
        lower case. A line that Cost Management cannot tie to a resource has an empty id."""
        return [CostLine(resource.lower(), service.strip(), amount, code)
                for (resource, service), amount, code in self._cost_rows(subscription, start, end, ("ResourceId", "ServiceName"))]

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

    def security_pricings(self, subscription: str) -> list[dict]:
        """The pricing settings of the Microsoft Defender for Cloud plans of one subscription."""
        url = f"{ARM}/subscriptions/{subscription}/providers/Microsoft.Security/pricings?api-version={SECURITY_API}"
        return self._pages(subscription, url, "Microsoft.Security")

    @staticmethod
    def _resource_scope(resource_id: str) -> str:
        """The id of one resource, when it is one: a subscription or a resource group has no metrics of its own, and a dot segment would walk out of the id."""
        if not SCOPE_ID.fullmatch(resource_id) or not RESOURCE_PATH.search(resource_id) or {".", ".."} & set(resource_id.split("/")):
            raise HttpError(0, "the scope is not the id of an Azure resource")
        return resource_id

    def metric_definitions(self, resource_id: str) -> list[dict]:
        """The metric definitions that Azure Monitor has for one resource (the platform metrics: no custom namespace is asked for)."""
        scope = self._resource_scope(resource_id)
        url = f"{ARM}{scope}/providers/Microsoft.Insights/metricDefinitions?api-version={METRIC_DEFINITIONS_API}"
        return self._pages(scope.split("/")[2], url, "Microsoft.Insights")

    def metrics(self, resource_id: str, metric: str, start: dt.datetime, end: dt.datetime) -> tuple[str, list[MetricPoint]]:
        """One metric of one resource in daily buckets from start to end (a time without a zone is UTC): its unit, and a point for each bucket that Azure
        Monitor returned. Without a filter the answer holds one time series, with the dimensions of the metric summed up."""
        scope = self._resource_scope(resource_id)
        if not metric.strip() or len(metric) > 100 or "," in metric:
            raise HttpError(0, "the metric name is not a plain name")
        span = "/".join(_utc(moment).strftime(METRIC_TIME) for moment in (start, end))
        url = (f"{ARM}{scope}/providers/Microsoft.Insights/metrics?api-version={METRICS_API}&metricnames={quote(metric, safe='')}"
               f"&timespan={span}&interval=P1D&aggregation=Total,Maximum,Average")
        data = self.client.request("GET", url, headers=self._headers(), timeout=30, retries=1).json()
        if not isinstance(data, dict) or not isinstance(data.get("value"), list):
            raise _bad("Azure Monitor")
        found = next((item for item in data["value"] if isinstance(item, dict)), None)
        if found is None:
            return "", []
        code = re.sub(r"[^A-Za-z0-9]", "", str(found.get("errorCode") or "Success"))[:40]
        if code.lower() != "success":
            raise HttpError(200, f"Azure Monitor could not read the metric ({code})")
        series = found.get("timeseries")
        if not isinstance(series, list):
            raise _bad("Azure Monitor")
        element = next((item for item in series if isinstance(item, dict)), {})
        points = [MetricPoint(str(item.get("timeStamp") or ""), _number(item.get("total")), _number(item.get("maximum")), _number(item.get("average")))
                  for item in element.get("data") or [] if isinstance(item, dict)]
        return str(found.get("unit") or ""), points

    @staticmethod
    def _lock_scopes(locks: list[dict]) -> list[str]:
        scopes = []
        for lock in locks:
            lock_id = str(lock.get("id", ""))
            index = lock_id.lower().find("/providers/microsoft.authorization/locks/")
            if index > 0:
                scopes.append(lock_id[:index].lower())
        return scopes

    def locks(self, subscription: str) -> list[str]:
        """The scope of every management lock that the subscription-wide list returns, lower case. Without a filter the list returns the locks at, above and
        below its scope (the documentation of Get-AzResourceLock -AtScope says so), but it is paged and can be throttled, so a case also asks for its own
        scopes one by one (locks_at)."""
        url = f"{ARM}/subscriptions/{subscription}/providers/Microsoft.Authorization/locks?api-version={LOCKS_API}"
        return self._lock_scopes(self._pages(subscription, url, "Microsoft.Authorization"))

    def locks_at(self, subscription: str, scope: str) -> list[str]:
        """The scope of every lock that applies to one scope (a subscription, a group or a resource), lower case. With $filter=atScope() the list returns the
        locks at and above the scope: the documentation of Get-AzResourceLock -AtScope says "all locks at or above the specified scope"."""
        if not SCOPE_ID.fullmatch(scope) or not scope.lower().startswith(f"/subscriptions/{subscription}".lower()):
            raise HttpError(0, "the scope is not an Azure resource id of the subscription")
        url = f"{ARM}{scope}/providers/Microsoft.Authorization/locks?api-version={LOCKS_API}&$filter=atScope()"
        return self._lock_scopes(self._pages(subscription, url, "Microsoft.Authorization"))
