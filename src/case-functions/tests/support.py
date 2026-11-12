"""Helpers shared by the tests: a fake estate that answers the calls of the app, a clock and a log capture.

The tests use the standard library only and need no network and no Azure. Run them from the repository root:

    python -m unittest discover -s src/case-functions/tests
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

# With a handler on the root logger, logging.info() does not configure logging by itself and print to the console.
logging.getLogger().addHandler(logging.NullHandler())

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
# The app holds no key. This is a secret value that must never reach a log line, a History line or an error text: the tests use it for any secret that a service may echo.
KEY = "K3y-VALUE-that-must-never-be-logged-0123456789abcdef"
TOKEN = "eyJhbGciOiJub25lIn0.eyJvaWQiOiJ4In0.signature-value-123"
NOW = dt.datetime(2026, 11, 4, 12, 0, 0, tzinfo=dt.timezone.utc)
# The Foundry project of the agents (the investigation's agents and conversations; the model calls of the Detective and the Skeptic do not go there: they go through the AI Gateway).
FOUNDRY_ENDPOINT = "https://example-account.services.ai.azure.com/api/projects/meternaut"
# The AI Gateway, which every model call goes through: its host (the service reports it) and its one route of a chat completion.
GATEWAY_HOST = "aigw-meternaut-0123abcd.swedencentral-01.ai.gateway.azure.com"
CHAT_ROUTE = "/default/models/openai/v1/chat/completions"

# INVESTIGATE is off: the tests of the Watch judge every lead with the Detective and the Skeptic, as they always did. A test that wants the investigation turns it on.
ENV = {
    "AZURE_CLIENT_ID": "99999999-8888-7777-6666-555555555555",
    "SCOPE_SUBSCRIPTIONS": SUBSCRIPTION,
    "MODEL_DETECTIVE": "gpt-6-luna",
    "MODEL_SKEPTIC": "gpt-6.1-sol",
    "AIGATEWAY_HOST": GATEWAY_HOST,
    "MAX_CASES_PER_RUN": "3",
    "CASES_CONTROL_QUEUE_NAME": "cases-control",
    "FOUNDRY_PROJECT_ENDPOINT": FOUNDRY_ENDPOINT,
    "INVESTIGATE": "off",
    "IDENTITY_ENDPOINT": "http://127.0.0.1:8081/msi/token",
    "IDENTITY_HEADER": "identity-header-value",
}
# The same without a Foundry project: the app does not investigate, and the Detective and the Skeptic judge the leads through the AI Gateway as before.
ENV_NO_PROJECT = {k: v for k, v in ENV.items() if k not in ("FOUNDRY_PROJECT_ENDPOINT", "INVESTIGATE")}

RG = f"/subscriptions/{SUBSCRIPTION}/resourceGroups"


def pe_row(name: str, group: str = "rg-app", states=("Disconnected",), groups=("blob",), **changes) -> dict:
    row = {"id": f"{RG}/{group}/providers/Microsoft.Network/privateEndpoints/{name}", "name": name, "type": "microsoft.network/privateendpoints",
           "resourceGroup": group, "subscriptionId": SUBSCRIPTION, "location": "swedencentral", "tags": None, "managedBy": "",
           "states": list(states), "groups": list(groups)}
    row.update(changes)
    return row


def disk_row(name: str, group: str = "rg-app", **changes) -> dict:
    row = {"id": f"{RG}/{group}/providers/Microsoft.Compute/disks/{name}", "name": name, "type": "microsoft.compute/disks", "resourceGroup": group,
           "subscriptionId": SUBSCRIPTION, "location": "swedencentral", "tags": {"owner": "someone"}, "managedBy": "", "skuName": "Premium_LRS",
           "sizeGb": 256, "timeCreated": "2026-01-02T10:00:00.1234567+00:00"}
    row.update(changes)
    return row


def model_reply(content: str, prompt: int = 700, completion: int = 150) -> tuple[int, dict]:
    return 200, {"choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}}


def detective_says(recommendation: str = "delete", confidence: float = 0.9, summary: str = "The connection was never approved and nothing uses it.") -> str:
    return json.dumps({"recommendation": recommendation, "confidence": confidence, "summary": summary})


def skeptic_says(verdict: str = "agree", objections=(), summary: str = "No reason to keep it.") -> str:
    return json.dumps({"verdict": verdict, "objections": list(objections), "summary": summary})


class FakeEstate:
    """Answers every call that the app makes, from the lists below, and keeps them in `calls`.

    `graph` maps the name that heads a Resource Graph query (`// meternaut:<name>`) to its rows. `locks` is the answer of the subscription-wide list of
    locks and `locks_at` maps a lower-case scope to the answer of the list of that scope. `days` holds the daily cost lines (a date, a resource id, a cost) that a query by day
    asks for. `metrics` maps (a resource id in lower case, a metric name) to {a day: its value} for a read of Azure Monitor in daily buckets: a value is a number (the bucket has it as its total,
    its maximum and its average), a (total, maximum, average) tuple, or None (a bucket with no value); a day that is not there is a bucket with no value too. `failures` maps a source
    (`graph:<name>`, `advisor`, `locks`, `locks_at`, `costs`, `daily`, `metrics`, `metrics:<name of a metric>`, `chat`) to a status that is answered instead (or to a list of statuses, one
    for each call).
    `after_chat` is called after each answer of the model, to move a clock. `first_call` is called before the first call of any kind, for the same reason.
    """

    def __init__(self) -> None:
        self.graph: dict[str, list[dict]] = {"orphan-private-endpoint": [], "orphan-managed-disk": [], "orphan-public-ip": [], "load-balancer-without-backends": [],
                                             "empty-app-service-plan": [], "stopped-vm": [], "recent-creations": [], "managed-groups": []}
        self.advisor: list[dict] = []
        self.locks: list[dict] = []
        self.locks_at: dict[str, list[dict]] = {}
        self.cost_rows: list[list] = []
        self.days: list[tuple[dt.date, str, float]] = []
        # What Cost Management gives for a whole subscription or one resource group: `scope_rows` are the lines (cost, service, resource group in lower case, "" for a line that has no group, such as a
        # plan of Microsoft Defender for Cloud) that a query by service reads, and `scope_days` the cost of each day (day, cost, group) that a query by day of a whole scope reads.
        self.scope_rows: list[tuple[float, str, str]] = []
        self.scope_days: list[tuple[dt.date, float, str]] = []
        self.subscription_name: str | None = None  # the display name that a read of the subscription gives; None: that read is answered with 404
        self.metrics: dict[tuple[str, str], dict[dt.date, object]] = {}
        self.currency = "USD"
        self.failures: dict[str, object] = {}
        self.chat_replies: list[tuple[int, object]] = []
        self.calls: list[dict] = []
        self.sleeps: list[float] = []
        self.after_chat = None
        self.first_call = None
        self.recommendation = "delete"  # what the Detective answers: a deletion of a resource outside a group where a change may be made is held back by the rules (cases/brief.py held_reason), so a test that needs a request says "change"
        self.activity: list[dict] = []  # the events that the Activity Log of any resource shows (a failure of source `activity` makes the read fail)

    # -- the answers ---------------------------------------------------------------------------------------------------------------------------
    def model(self, model: str, system: str, user: str) -> tuple:
        """The reply to one chat call: (status, body) or (status, headers, body)."""
        if self.chat_replies:
            return self.chat_replies.pop(0)
        if system.startswith("You are the Detective"):
            return model_reply(detective_says(self.recommendation))
        return model_reply(skeptic_says())

    def _failure(self, source: str):
        planned = self.failures.get(source)
        if isinstance(planned, list):
            return planned.pop(0) if planned else None
        return planned

    def __call__(self, method: str, url: str, headers, data, timeout):
        if self.first_call and not self.calls:
            self.first_call()
        parts = urlsplit(url)
        body = json.loads(data.decode("utf-8")) if data else None
        self.calls.append({"method": method, "url": url, "host": parts.netloc, "path": parts.path, "headers": dict(headers), "body": body, "timeout": timeout})
        path = parts.path.lower()
        if path.endswith("/providers/microsoft.resourcegraph/resources"):
            name = re.match(r"// meternaut:(\S+)", body["query"]).group(1)
            failed = self._failure(f"graph:{name}")
            return (failed, {}, b'{"error":{"code":"Failed","message":"boom"}}') if failed else self._json({"count": len(self.graph[name]), "data": self.graph[name]})
        if "/providers/microsoft.costmanagement/query" in path:
            daily = body["dataset"]["granularity"] == "Daily"
            failed = self._failure("daily" if daily else "costs")
            if failed:
                return failed, {"retry-after": "1"} if failed == 429 else {}, b'{"error":{"code":"Throttled","message":"slow down"}}'
            asked = body["dataset"].get("filter", {}).get("dimensions")
            by_service = [g["name"] for g in body["dataset"].get("grouping", [])] == ["ServiceName"]
            if (asked and asked["name"] == "ResourceGroup") or (not asked and (by_service or (daily and "grouping" not in body["dataset"]))):
                return self._by_scope(body, daily, asked)
            if daily:
                return self._by_day(body)
            return self._json({"properties": {"columns": [{"name": "Cost"}, {"name": "ResourceId"}, {"name": "ServiceName"}, {"name": "Currency"}],
                                              "rows": [[cost, rid, "Storage", self.currency] for cost, rid in self.cost_rows]}})
        if path.endswith("/providers/microsoft.insights/metrics"):
            return self._metrics(parts)
        if "/providers/microsoft.advisor/recommendations" in path:
            failed = self._failure("advisor")
            return (failed, {}, b'{"error":{"code":"Failed","message":"boom"}}') if failed else self._json({"value": self.advisor})
        if "/providers/microsoft.insights/eventtypes/management/values" in path:
            failed = self._failure("activity")
            return (failed, {}, b'{"error":{"code":"Failed","message":"boom"}}') if failed else self._json({"value": self.activity})
        if "/providers/microsoft.authorization/locks" in path:
            if path == f"/subscriptions/{SUBSCRIPTION}/providers/microsoft.authorization/locks":
                failed = self._failure("locks")
                return (failed, {}, b'{"error":{"code":"Failed","message":"boom"}}') if failed else self._json({"value": self.locks})
            failed = self._failure("locks_at")
            scope = path.split("/providers/microsoft.authorization/locks")[0]
            return (failed, {}, b'{"error":{"code":"Failed","message":"boom"}}') if failed else self._json({"value": self.locks_at.get(scope, [])})
        if path.endswith(CHAT_ROUTE):
            failed = self._failure("chat")
            if failed:
                return failed, {"retry-after": "1"} if failed == 429 else {}, b'{"statusCode":%d,"message":"refused"}' % failed
            messages = body["messages"]
            reply = self.model(body["model"], messages[0]["content"], messages[1]["content"])
            if self.after_chat:
                self.after_chat()
            if len(reply) == 3:
                status, answer_headers, answer = reply
                return status, answer_headers, json.dumps(answer).encode("utf-8")
            return self._json(reply[1], reply[0])
        if method == "GET" and path == f"/subscriptions/{SUBSCRIPTION}" and self.subscription_name is not None:
            return self._json({"id": f"/subscriptions/{SUBSCRIPTION}", "subscriptionId": SUBSCRIPTION, "displayName": self.subscription_name, "state": "Enabled"})
        return 404, {}, b"{}"

    @staticmethod
    def _json(document, status: int = 200):
        return status, {}, json.dumps(document).encode("utf-8")

    def _by_scope(self, body, daily: bool, asked):
        """The answer to a query of Cost Management about a whole subscription or one resource group of it: the cost of each service, or of each day, of the lines of `scope_rows` or
        `scope_days` whose group is one of the groups that the filter names (all of them without a filter), without regard to the case of a name."""
        groups = {value.lower() for value in asked["values"]} if asked else None
        sums: dict = {}
        if daily:
            for day, cost, group in self.scope_days:
                if groups is None or group.lower() in groups:
                    sums[int(day.strftime("%Y%m%d"))] = sums.get(int(day.strftime("%Y%m%d")), 0.0) + cost
            name = "UsageDate"
        else:
            for cost, service, group in self.scope_rows:
                if groups is None or group.lower() in groups:
                    sums[service] = sums.get(service, 0.0) + cost
            name = "ServiceName"
        return self._json({"properties": {"columns": [{"name": "Cost"}, {"name": name}, {"name": "Currency"}], "rows": [[cost, key, self.currency] for key, cost in sums.items()]}})

    def _by_day(self, body):
        """The answer to a query of Cost Management by day: the lines of `days` of the resources that the query names, each with its day as a number (20261103)."""
        asked = {value.lower() for value in body["dataset"]["filter"]["dimensions"]["values"]}
        return self._json({"properties": {"columns": [{"name": "Cost"}, {"name": "UsageDate"}, {"name": "ResourceId"}, {"name": "Currency"}],
                                          "rows": [[cost, int(day.strftime("%Y%m%d")), rid.lower(), self.currency] for day, rid, cost in self.days if rid.lower() in asked]}})

    def _metrics(self, parts):
        """The answer to a read of one metric of one resource in daily buckets (Learn, "Metrics - List"): a bucket for each day of the timespan that the call names, with the values that
        `metrics` holds for it and no value for a day that it does not hold. A resource and a metric that `metrics` does not know are answered like any metric with no data."""
        query = parse_qs(parts.query)
        metric = query["metricnames"][0]
        failed = self._failure(f"metrics:{metric}") or self._failure("metrics")
        if failed:
            return failed, {"retry-after": "1"} if failed == 429 else {}, b'{"error":{"code":"Throttled","message":"slow down"}}'
        start, end = (dt.datetime.strptime(moment, "%Y-%m-%dT%H:%M:%SZ").date() for moment in query["timespan"][0].split("/"))
        resource = re.sub(r"(?i)/providers/microsoft\.insights/metrics$", "", parts.path)
        known = self.metrics.get((resource.lower(), metric), {})
        data = []
        for n in range((end - start).days):
            day = start + dt.timedelta(days=n)
            bucket: dict = {"timeStamp": f"{day.isoformat()}T00:00:00Z"}
            value = known.get(day)
            if value is not None:
                total, maximum, average = value if isinstance(value, tuple) else (value, value, value)
                bucket.update({"total": total, "maximum": maximum, "average": average})
            data.append(bucket)
        return self._json({"cost": 0, "timespan": query["timespan"][0], "interval": "P1D",
                           "value": [{"id": f"{resource}/providers/Microsoft.Insights/metrics/{metric}", "type": "Microsoft.Insights/metrics", "name": {"value": metric, "localizedValue": metric},
                                      "unit": "Count", "timeseries": [{"metadatavalues": [], "data": data}], "errorCode": "Success"}]})

    # -- what the tests ask -----------------------------------------------------------------------------------------------------------------------
    def prompts(self) -> list[str]:
        return [call["body"]["messages"][1]["content"] for call in self.calls if call["path"].endswith(CHAT_ROUTE)]

    def chat_calls(self) -> list[dict]:
        return [call for call in self.calls if call["path"].endswith(CHAT_ROUTE)]


def identity_fetch(url, headers, timeout):
    return 200, json.dumps({"access_token": TOKEN, "expires_on": str(int(NOW.timestamp()) + 3600), "resource": "x"}).encode("utf-8")


class Ticker:
    """A monotonic clock that moves a little at every reading, and a way to move it a lot."""

    def __init__(self, step: float = 0.1) -> None:
        self.now, self.step = 1000.0, step

    def __call__(self) -> float:
        self.now += self.step
        return self.now

    def jump(self, seconds: float) -> None:
        self.now += seconds


def fixed_clock() -> dt.datetime:
    return NOW


class LogCapture(logging.Handler):
    """Collects the records of the root logger while it is in a with block, also when nothing is logged."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def __enter__(self) -> "LogCapture":
        root = logging.getLogger()
        self._level = root.level
        root.setLevel(logging.DEBUG)
        root.addHandler(self)
        return self

    def __exit__(self, *exc_info) -> None:
        root = logging.getLogger()
        root.removeHandler(self)
        root.setLevel(self._level)

    def messages(self) -> list[str]:
        return [record.getMessage() for record in self.records]

    def events(self) -> list[dict]:
        from cases.events import EVENT_PREFIX
        return [json.loads(m[len(EVENT_PREFIX):]) for m in self.messages() if m.startswith(EVENT_PREFIX)]


def run_watch(estate: FakeEstate, env: dict | None = None, trigger: str = "control", request_id: str | None = "a" * 32, ticker: Ticker | None = None, **overrides):
    """One whole run against the fake estate. Returns the summary, the History lines and every log message."""
    from cases import run
    ids = iter(f"{n:032x}" for n in range(1, 1000))
    options = dict(clock=fixed_clock, monotonic=ticker or Ticker(), sleep=estate.sleeps.append, transport=estate, fetch=identity_fetch, new_id=lambda: next(ids))
    options.update(overrides)
    with LogCapture() as capture:
        summary = run.run_watch(trigger, request_id, env or dict(ENV), **options)
    return summary, capture.events(), capture.messages()
