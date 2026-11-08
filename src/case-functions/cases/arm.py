"""Read-only calls to Azure Resource Manager and to the Logs query API: Resource Graph, Cost Management, Advisor, management locks, Azure Monitor metrics, the pricing settings of
Microsoft Defender for Cloud, and the reads of the investigation's deeper tools (a Log Analytics workspace, its tables, its usage records and its readers, the deployments of an AI
services account, the diagnostic settings of a resource, the activity log, the platform's own purchase recommendations).

Nothing here writes. The POSTs ask a question (a query), and `http.Client` refuses every other call. Every read cites the page of Microsoft Learn that it was written from.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import threading
from typing import Callable, NamedTuple, Sequence
from urllib.parse import quote, urlsplit

from .http import AI_ACCOUNT, ARM_HOST, GUID, LOG_ANALYTICS_HOST, LOG_ANALYTICS_RESOURCE, SCOPE, WORKSPACE, Client, HttpError

ARM = f"https://{ARM_HOST}"
GRAPH_API = "2022-10-01"
COST_API = "2023-11-01"
ADVISOR_API = "2023-01-01"
LOCKS_API = "2016-09-01"
METRICS_API = "2023-10-01"
METRIC_DEFINITIONS_API = "2018-01-01"
SECURITY_API = "2024-01-01"
SUBSCRIPTIONS_API = "2022-12-01"
# Learn, REST reference "Workspaces - Get", "Tables - List By Workspace" and "Saved Searches - List By Workspace" (Log Analytics): 2026-03-01 is the version of all three pages; the first two were
# read in the pilot with 2025-02-01 and with this one.
LOG_ANALYTICS_API = "2026-03-01"
DIAGNOSTIC_API = "2021-05-01-preview"  # Learn, "Diagnostic Settings - List"
WORKBOOKS_API = "2023-06-01"  # Learn, "Workbooks - List By Subscription": the content of a workbook is returned only with canFetchContent=true
SENTINEL_API = "2025-09-01"  # Learn, "Alert Rules - List" (Microsoft Sentinel)
DEPLOYMENTS_API = "2026-09-01"  # Learn, the template reference of Microsoft.CognitiveServices/accounts/deployments lists it as the latest version that is not a preview
ACTIVITY_API = "2015-04-01"  # Learn, "Activity Logs - List"
BENEFITS_API = "2026-06-01"  # Learn, "Benefit Recommendations - List"
RESERVATIONS_API = "2024-08-01"  # Learn, "Reservation Recommendations - List" (Microsoft.Consumption)
# Cost Management throttles by the type of the client as well as by the tenant, and a call that names no client type shares the quota of every caller that does not either: in the pilot it got
# HTTP 429 with a wait of 2 to 21 seconds while the same call with this header got 200. The header is described in Microsoft Q&A (learn.microsoft.com/answers/a/8268839) and by the owners
# of the REST specifications (Azure/azure-rest-api-specs issue 24407), and not on a page of the REST reference.
CLIENT_TYPE = "Meternaut"
MAX_PAGES = 10
SUBSCRIPTION_PAGES = 30  # the pages of the list of subscriptions that are followed, at most
SCOPE_ID = re.compile(SCOPE, re.I)
WORKSPACE_ID = re.compile(WORKSPACE, re.I)
AI_ACCOUNT_ID = re.compile(AI_ACCOUNT, re.I)
GROUP_NAME = re.compile(r"[A-Za-z0-9._()-]{1,90}")
WORKSPACE_GUID = re.compile(GUID)
GROUP_SCOPE = re.compile(r"^(/subscriptions/[^/]+/resourceGroups/[^/]+)", re.I)
RESOURCE_PATH = re.compile(r"/providers/[^/]+/[^/]+/[^/]+", re.I)
DIMENSION = re.compile(r"[A-Za-z][A-Za-z0-9]{0,40}")  # the name of a dimension of a metric, as Azure Monitor gives it
METRIC_TIME = "%Y-%m-%dT%H:%M:%SZ"
TABLE_FIELDS = ("plan", "retentionInDays", "totalRetentionInDays", "retentionInDaysAsDefault", "totalRetentionInDaysAsDefault", "protectionLevel", "provisioningState")


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


class TooManyPages(HttpError):
    """A Resource Graph result that has more pages than the app reads. It is an HttpError (status 0) as it always was; graph_many tells it from the others."""


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
        # The cost lines of a subscription for one period are read once for as long as this object lives (a run): the Watch and the tools of the investigation ask for the same lines, and Cost
        # Management is the slowest and the most throttled of the reads. Only a read that succeeded is kept, so a read that failed is made again by the next caller.
        self._lines: dict[tuple[str, dt.date, dt.date], tuple[CostLine, ...]] = {}
        self._line_locks: dict[tuple[str, dt.date, dt.date], threading.Lock] = {}
        self._memo_lock = threading.Lock()

    def _headers(self, resource: str = ARM) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(resource)}"}

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

    def graph(self, subscription: "str | Sequence[str]", query: str) -> list[dict]:
        """The rows of one Resource Graph query in one subscription, or in a list of them (a row names its own subscription in `subscriptionId`), every page of them."""
        subscriptions = [subscription] if isinstance(subscription, str) else list(subscription)
        rows: list[dict] = []
        skip = None
        for _ in range(MAX_PAGES):
            options: dict[str, object] = {"resultFormat": "objectArray", "$top": 1000}
            if skip:
                options["$skipToken"] = skip
            body = {"subscriptions": subscriptions, "query": query, "options": options}
            data = self.client.request("POST", f"{ARM}/providers/Microsoft.ResourceGraph/resources?api-version={GRAPH_API}", headers=self._headers(),
                                       body=body, timeout=60).json()
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise _bad("Resource Graph")
            rows += [row for row in data["data"] if isinstance(row, dict)]
            skip = data.get("$skipToken")
            if not skip:
                return rows
        raise TooManyPages(0, f"Resource Graph returned more than {MAX_PAGES} pages")

    def graph_many(self, subscriptions: Sequence[str], query: str) -> list[dict]:
        """The rows of one query across several subscriptions, from one query for all of them: Learn recommends grouping subscriptions (fewer than 300 in a group) over a query for
        each one, because a group costs less of the quota (the quota is 15 queries in 5 seconds, and a page of a result is a query too). A result of more than MAX_PAGES pages
        does not fit: the same query is then made for each half of the list, and so on down to one subscription, whose own result may be as long as it always could be."""
        try:
            return self.graph(list(subscriptions), query)
        except TooManyPages:
            if len(subscriptions) < 2:
                raise
            middle = len(subscriptions) // 2
            return self.graph_many(subscriptions[:middle], query) + self.graph_many(subscriptions[middle:], query)

    def subscriptions(self) -> list[dict]:
        """The subscriptions that the identity can read, as Azure Resource Manager lists them (every state of them), every page. The next-page link is followed only on the same
        host and the same path."""
        found: list[dict] = []
        link: str | None = f"{ARM}/subscriptions?api-version={SUBSCRIPTIONS_API}"
        for _ in range(SUBSCRIPTION_PAGES):
            data = self.client.request("GET", link, headers=self._headers(), timeout=60).json()
            if not isinstance(data, dict) or not isinstance(data.get("value", []), list):
                raise _bad("Azure Resource Manager")
            found += [item for item in data.get("value", []) if isinstance(item, dict)]
            link = self._next_subscriptions(data.get("nextLink"))
            if not link:
                return found
        raise HttpError(0, f"the list of subscriptions has more than {SUBSCRIPTION_PAGES} pages")

    @staticmethod
    def _next_subscriptions(link: object) -> str | None:
        """The next page of the list of subscriptions, only when it is on the same host and the same path (a link to anywhere else is not followed)."""
        if not link:
            return None
        parts = urlsplit(str(link))
        if parts.scheme != "https" or parts.netloc.lower() != ARM_HOST or parts.path.lower().rstrip("/") != "/subscriptions":
            raise _bad("Azure Resource Manager")
        return str(link)

    def _cost_rows(self, subscription: str, start: dt.date, end: dt.date, dimensions: tuple[str, ...], *, kind: str = "ActualCost", daily: bool = False,
                   where: tuple[str, tuple[str, ...]] | None = None) -> list[tuple[list[str], float, str]]:
        """Every row of one Cost Management query (Learn, "Query - Usage") that groups the cost from start to end (both days included) by the dimensions: the value of each
        dimension in the order asked for, the sum of the cost and its currency ("" when the answer has no currency column). `kind` is ActualCost or AmortizedCost. With `daily` the
        granularity is Daily and the answer has a column UsageDate (a number such as 20261031), which a dimension of that name asks for: it is not a grouping. `where` is a dimension and the
        values that a row must have (an In filter)."""
        grouping = [{"type": "Dimension", "name": name} for name in dimensions if name != "UsageDate"]
        dataset: dict[str, object] = {"granularity": "Daily" if daily else "None", "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}}}
        if grouping:
            dataset["grouping"] = grouping
        if where is not None:
            dataset["filter"] = {"dimensions": {"name": where[0], "operator": "In", "values": list(where[1])}}
        body = {"type": kind, "timeframe": "Custom", "timePeriod": {"from": f"{start.isoformat()}T00:00:00Z", "to": f"{end.isoformat()}T23:59:59Z"}, "dataset": dataset}
        url: str | None = f"{ARM}/subscriptions/{subscription}/providers/Microsoft.CostManagement/query?api-version={COST_API}"
        found: list[tuple[list[str], float, str]] = []
        for _ in range(MAX_PAGES):
            data = self.client.request("POST", url, headers={**self._headers(), "ClientType": CLIENT_TYPE}, body=body, timeout=60, retries=2, retry_after_max=60).json()
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
        raise TooManyPages(0, f"Cost Management returned more than {MAX_PAGES} pages")

    def costs(self, subscription: str, start: dt.date, end: dt.date) -> tuple[dict[str, float], str | None]:
        """Actual cost lines of every resource from start to end (both days included), by lower-case resource id, and their currency.

        The currency is None when there are no lines and "mixed" when the lines are in more than one.

        The totals are added up from the cost lines of cost_lines, which are read once for the period (the tools of the investigation use them too). When the lines do not fit in the pages
        that are read (a subscription with very many resources), the totals are asked for by themselves, as they always were."""
        totals: dict[str, float] = {}
        currencies: set[str] = set()
        try:
            lines = self.cost_lines(subscription, start, end)
        except TooManyPages:
            for (resource,), amount, code in self._cost_rows(subscription, start, end, ("ResourceId",)):
                key = resource.lower()
                totals[key] = totals.get(key, 0.0) + amount
                if code:
                    currencies.add(code)
        else:
            for line in lines:
                totals[line.resource_id] = totals.get(line.resource_id, 0.0) + line.amount
                if line.currency:
                    currencies.add(line.currency)
        return totals, (None if not currencies else currencies.pop() if len(currencies) == 1 else "mixed")

    def cost_lines(self, subscription: str, start: dt.date, end: dt.date) -> list[CostLine]:
        """The actual cost of every resource under every service from start to end (both days included): one line for each pair, with the resource id in
        lower case. A line that Cost Management cannot tie to a resource has an empty id.

        The lines of one subscription and period are read once for as long as this object lives, by whoever asks first; a caller that asks while another is reading waits for that read."""
        key = (subscription.lower(), start, end)
        with self._memo_lock:
            kept = self._lines.get(key)
            gate = self._line_locks.setdefault(key, threading.Lock())
        if kept is None:
            with gate:
                with self._memo_lock:
                    kept = self._lines.get(key)
                if kept is None:
                    kept = tuple(CostLine(resource.lower(), service.strip(), amount, code)
                                 for (resource, service), amount, code in self._cost_rows(subscription, start, end, ("ResourceId", "ServiceName")))
                    with self._memo_lock:
                        self._lines[key] = kept
        return list(kept)

    def cost_days(self, subscription: str, start: dt.date, end: dt.date, *, amortized: bool = False,
                  where: tuple[str, tuple[str, ...]] | None = None) -> list[tuple[dt.date, str, float, str]]:
        """The cost of each day from start to end (both days included) of one subscription, by resource: (day, resource id in lower case, cost, currency). `amortized` asks for the amortized
        cost (a purchase spread over its term) instead of the actual cost. `where` is a dimension and the values that a row must have, such as ResourceId or ResourceType. Learn, "Query - Usage"."""
        rows = self._cost_rows(subscription, start, end, ("UsageDate", "ResourceId"), kind="AmortizedCost" if amortized else "ActualCost", daily=True, where=where)
        found = []
        for (day, resource), amount, code in rows:
            try:
                moment = dt.datetime.strptime(day[:8], "%Y%m%d").date()
            except ValueError:
                raise _bad("Cost Management") from None
            found.append((moment, resource.lower(), amount, code))
        return found

    def cost_models(self, subscription: str, start: dt.date, end: dt.date) -> list[tuple[str, str, float, str]]:
        """The amortized cost from start to end (both days included) of one subscription by how it was paid for and what kind of charge it is: (pricing model, charge type, cost, currency),
        with the words as Cost Management gives them. A purchase is spread over its term, and a part of a commitment that nothing used is a charge of its own. Learn, "Query - Usage"."""
        return [(values[0], values[1], amount, code) for values, amount, code in self._cost_rows(subscription, start, end, ("PricingModel", "ChargeType"), kind="AmortizedCost")]

    def _pages(self, subscription: str, url: str, service: str, headers: dict[str, str] | None = None) -> list[dict]:
        found: list[dict] = []
        link: str | None = url
        for _ in range(MAX_PAGES):
            data = self.client.request("GET", link, headers={**self._headers(), **(headers or {})}, timeout=60).json()
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

    def metrics_split(self, resource_id: str, metric: str, dimension: str, start: dt.datetime, end: dt.datetime, top: int = 50) -> tuple[str, list[tuple[str, list[MetricPoint]]]]:
        """One metric of one resource in daily buckets from start to end, with one time series for each value of one dimension of the metric (Learn, "Metrics - List": $filter=<dimension> eq '*'
        returns a series for every value, `top` is the most that it returns for the resource): the unit, and for each series the value of the dimension as Azure Monitor gives it (text from the
        estate: the caller turns it into a handle or a label and never shows it) with its points. A time without a zone is UTC."""
        scope = self._resource_scope(resource_id)
        if not metric.strip() or len(metric) > 100 or "," in metric:
            raise HttpError(0, "the metric name is not a plain name")
        if not DIMENSION.fullmatch(dimension):
            raise HttpError(0, "the dimension is not a plain name")
        span = "/".join(_utc(moment).strftime(METRIC_TIME) for moment in (start, end))
        everything = quote(f"{dimension} eq '*'", safe="")
        url = (f"{ARM}{scope}/providers/Microsoft.Insights/metrics?api-version={METRICS_API}&metricnames={quote(metric, safe='')}&timespan={span}&interval=P1D"
               f"&aggregation=Total,Maximum,Average&$filter={everything}&top={int(top)}")
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
        result: list[tuple[str, list[MetricPoint]]] = []
        for element in series:
            if not isinstance(element, dict):
                continue
            values = [item.get("value") for item in element.get("metadatavalues") or []
                      if isinstance(item, dict) and isinstance(item.get("name"), dict) and str(item["name"].get("value", "")).lower() == dimension.lower()]
            label = values[0] if values and isinstance(values[0], (str, int)) and not isinstance(values[0], bool) else ""
            points = [MetricPoint(str(item.get("timeStamp") or ""), _number(item.get("total")), _number(item.get("maximum")), _number(item.get("average")))
                      for item in element.get("data") or [] if isinstance(item, dict)]
            result.append((str(label), points))
        return str(found.get("unit") or ""), result

    # -- the deeper reads: Log Analytics, deployments, diagnostic settings, the activity log, the platform's purchase recommendations ----------------------------------------------

    @staticmethod
    def _workspace_scope(resource_id: str) -> str:
        """The id of one Log Analytics workspace, when it is one (a dot segment would walk out of the id)."""
        if not WORKSPACE_ID.fullmatch(resource_id) or {".", ".."} & set(resource_id.split("/")):
            raise HttpError(0, "the scope is not the id of a Log Analytics workspace")
        return resource_id

    def workspace(self, resource_id: str) -> dict:
        """One Log Analytics workspace as Azure Resource Manager gives it (Learn, "Workspaces - Get"): its pricing tier (sku), retention, daily cap and the id (customerId) that the query API
        names it by."""
        scope = self._workspace_scope(resource_id)
        data = self.client.request("GET", f"{ARM}{scope}?api-version={LOG_ANALYTICS_API}", headers=self._headers(), timeout=60).json()
        if not isinstance(data, dict) or not isinstance(data.get("properties"), dict):
            raise _bad("Log Analytics")
        return data

    def workspace_tables(self, resource_id: str) -> list[dict]:
        """The tables of one workspace (Learn, "Tables - List By Workspace"), cut to what the tools use: the name, the creator of the table (type, subType: Microsoft or a customer) and the
        fields of TABLE_FIELDS (the plan, the retention, how long the data is kept in all, whether those come from the workspace, the protection level). The answer holds the columns of
        every table, a few megabytes for a workspace, and none of it is kept."""
        scope = self._workspace_scope(resource_id)
        items = self._pages(scope.split("/")[2], f"{ARM}{scope}/tables?api-version={LOG_ANALYTICS_API}", "Microsoft.OperationalInsights")
        found = []
        for item in items:
            properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
            schema = properties.get("schema") if isinstance(properties.get("schema"), dict) else {}
            found.append({"name": item.get("name"), "type": schema.get("tableType"), "subType": schema.get("tableSubType"), **{field: properties.get(field) for field in TABLE_FIELDS}})
        return found

    def saved_searches(self, resource_id: str) -> list[dict]:
        """The saved searches and functions of one workspace (Learn, "Saved Searches - List By Workspace"), as Azure gives them: each has its query (text from the estate)."""
        scope = self._workspace_scope(resource_id)
        return self._pages(scope.split("/")[2], f"{ARM}{scope}/savedSearches?api-version={LOG_ANALYTICS_API}", "Microsoft.OperationalInsights")

    def sentinel_rules(self, resource_id: str) -> list[dict]:
        """The analytics rules of Microsoft Sentinel on one workspace (Learn, "Alert Rules - List"). A workspace that is not onboarded to Sentinel answers HTTP 400."""
        scope = self._workspace_scope(resource_id)
        return self._pages(scope.split("/")[2], f"{ARM}{scope}/providers/Microsoft.SecurityInsights/alertRules?api-version={SENTINEL_API}", "Microsoft.OperationalInsights")

    def workbooks(self, subscription: str, category: str = "workbook") -> list[dict]:
        """The workbooks of one category in a subscription, with their content (Learn, "Workbooks - List By Subscription": canFetchContent=true). The content is text from the estate."""
        url = (f"{ARM}/subscriptions/{subscription}/providers/Microsoft.Insights/workbooks?category={quote(category, safe='')}&canFetchContent=true"
               f"&api-version={WORKBOOKS_API}")
        return self._pages(subscription, url, "Microsoft.Insights")

    def log_query(self, workspace_id: str, query: str, start: dt.datetime, end: dt.datetime, *, timeout: float = 60) -> list[dict]:
        """The rows of one query of the Logs query API (Learn, "Request format for the Azure Monitor Logs query API") on one workspace, which is named by its id (a GUID), over the time from
        start to end: one dict for each row, by column name. The query is a text that code made (logs.py); a slow query is not asked again, and an answer that is partial is an error."""
        if not WORKSPACE_GUID.fullmatch(workspace_id):
            raise HttpError(0, "the workspace id is not a GUID")
        if not query.strip() or len(query) > 8000:
            raise HttpError(0, "the query is empty or too long")
        span = "/".join(_utc(moment).strftime(METRIC_TIME) for moment in (start, end))
        url = f"https://{LOG_ANALYTICS_HOST}/v1/workspaces/{workspace_id}/query"
        data = self.client.request("POST", url, headers=self._headers(LOG_ANALYTICS_RESOURCE), body={"query": query, "timespan": span}, timeout=timeout, retries=1,
                                   retry_network=False).json()
        tables = data.get("tables") if isinstance(data, dict) else None
        if not isinstance(tables, list) or not tables or not isinstance(tables[0], dict):
            raise _bad("Log Analytics")
        if isinstance(data.get("error"), dict):
            code = re.sub(r"[^A-Za-z0-9]", "", str(data["error"].get("code") or "Error"))[:40]
            raise HttpError(200, f"Log Analytics gave a partial answer ({code})")
        columns = [str(column.get("name")) for column in tables[0].get("columns") or [] if isinstance(column, dict)]
        return [dict(zip(columns, row)) for row in tables[0].get("rows") or [] if isinstance(row, list)]

    def diagnostic_settings(self, resource_id: str) -> list[dict]:
        """The diagnostic settings of one resource (Learn, "Diagnostic Settings - List"): where it sends its logs and metrics, and which categories."""
        scope = self._resource_scope(resource_id)
        return self._pages(scope.split("/")[2], f"{ARM}{scope}/providers/Microsoft.Insights/diagnosticSettings?api-version={DIAGNOSTIC_API}", "Microsoft.Insights")

    def deployments(self, resource_id: str) -> list[dict]:
        """The deployments of one AI services account (Learn, template reference of Microsoft.CognitiveServices/accounts/deployments; they are not in Resource Graph): each with its model,
        its SKU and capacity and its rate limits."""
        if not AI_ACCOUNT_ID.fullmatch(resource_id) or {".", ".."} & set(resource_id.split("/")):
            raise HttpError(0, "the scope is not the id of an AI services account")
        return self._pages(resource_id.split("/")[2], f"{ARM}{resource_id}/deployments?api-version={DEPLOYMENTS_API}", "Microsoft.CognitiveServices")

    def activity_events(self, subscription: str, since: dt.datetime, until: dt.datetime, *, resource_id: str | None = None, group: str | None = None,
                        max_pages: int = 3) -> tuple[list[dict], bool]:
        """The management events of the activity log of one subscription from `since` to `until`, newest first (Learn, "Activity Logs - List": only the filters of that page are allowed), for
        one resource or one resource group, at most `max_pages` pages of them. Returns the events as Azure gives them and whether every page was read."""
        flt = f"eventTimestamp ge '{_utc(since).strftime(METRIC_TIME)}' and eventTimestamp le '{_utc(until).strftime(METRIC_TIME)}'"
        if resource_id is not None:
            if not SCOPE_ID.fullmatch(resource_id) or not resource_id.lower().startswith(f"/subscriptions/{subscription}".lower()) or "'" in resource_id:
                raise HttpError(0, "the scope is not an Azure resource id of the subscription")
            flt += f" and resourceUri eq '{resource_id}'"
        elif group is not None:
            if not GROUP_NAME.fullmatch(group):
                raise HttpError(0, "the resource group is not a plain name")
            flt += f" and resourceGroupName eq '{group}'"
        link: str | None = (f"{ARM}/subscriptions/{subscription}/providers/Microsoft.Insights/eventtypes/management/values?api-version={ACTIVITY_API}"
                            f"&$filter={quote(flt, safe='')}")
        events: list[dict] = []
        for _ in range(max_pages):
            data = self.client.request("GET", link, headers=self._headers(), timeout=75, retries=1).json()
            if not isinstance(data, dict) or not isinstance(data.get("value", []), list):
                raise _bad("the activity log")
            events += [item for item in data.get("value", []) if isinstance(item, dict)]
            link = self._next(data.get("nextLink"), subscription, "Microsoft.Insights")
            if not link:
                return events, True
        return events, False

    def benefit_recommendations(self, subscription: str, term: str) -> list[dict]:
        """The platform's own recommendations to buy a savings plan for one subscription (Learn, "Benefit Recommendations - List"), for the single scope, the last 30 days and one term (P1Y or
        P3Y), as Azure gives them."""
        if term not in ("P1Y", "P3Y"):
            raise HttpError(0, "the term is P1Y or P3Y")
        flt = quote(f"properties/scope eq 'Single' AND properties/lookBackPeriod eq 'Last30Days' AND properties/term eq '{term}'", safe="")
        url = f"{ARM}/subscriptions/{subscription}/providers/Microsoft.CostManagement/benefitRecommendations?api-version={BENEFITS_API}&$filter={flt}"
        return self._pages(subscription, url, "Microsoft.CostManagement", {"ClientType": CLIENT_TYPE})

    def reservation_recommendations(self, subscription: str) -> list[dict]:
        """The platform's own recommendations to buy reservations for one subscription (Learn, "Reservation Recommendations - List", Microsoft.Consumption), for the single scope, as Azure
        gives them."""
        flt = quote("properties/scope eq 'Single'", safe="")
        url = f"{ARM}/subscriptions/{subscription}/providers/Microsoft.Consumption/reservationRecommendations?api-version={RESERVATIONS_API}&$filter={flt}"
        return self._pages(subscription, url, "Microsoft.Consumption")
