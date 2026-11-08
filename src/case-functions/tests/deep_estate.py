"""A fake estate for the deeper tools of the investigator: a workspace that keeps records of the data written to it, an AI services account with deployments, diagnostic settings,
daily cost lines and the platform's purchase recommendations. It answers at the level of the transport, so every call also passes the real client and its list of calls.

Everything in it is INVENTED: the names, the ids, the numbers and the texts."""
import json
import re
from urllib.parse import parse_qs, urlsplit

from support import SUBSCRIPTION
from cases import toolbox as tb
from test_toolbox import Estate, row

SUB = SUBSCRIPTION
WORKSPACE = "microsoft.operationalinsights/workspaces"
ACCOUNT = "microsoft.cognitiveservices/accounts"
RULES = "microsoft.insights/scheduledqueryrules"
COLLECTION = "microsoft.insights/datacollectionrules"
VM = "microsoft.compute/virtualmachines"
CUSTOMER = "0a1b2c3d-1111-2222-3333-444455556666"  # the id that the query API names the invented workspace by
OTHER_WORKSPACE = f"/subscriptions/{SUB}/resourceGroups/rg-other/providers/Microsoft.OperationalInsights/workspaces/ws-elsewhere"


def ident(kind, name, sub=SUB, group="rg-demo"):
    return f"/subscriptions/{sub}/resourceGroups/{group}/providers/{kind}/{name}"


WS = ident("Microsoft.OperationalInsights/workspaces", "ws-demo")
AI = ident("Microsoft.CognitiveServices/accounts", "ai-demo")
MACHINE = ident("Microsoft.Compute/virtualMachines", "vm-demo")


def table(name, plan="Analytics", kind="Microsoft", retention=30, total=30):
    """A table as the list of tables of a workspace gives it."""
    return {"name": name, "properties": {"plan": plan, "retentionInDays": retention, "totalRetentionInDays": total, "schema": {"tableType": kind}}}


def usage(day, name, billable, free=0.0):
    """A row of the usage read: the day in October 2026, the table, and the megabytes."""
    return {"Day": f"2026-10-{day:02d}T00:00:00Z", "DataType": name, "BillableMB": billable, "FreeMB": free}


def deployment(name, model="gpt-demo", version="2026-01-01", sku="Standard", capacity=10, requests=60, tokens=6000, state="Succeeded", upgrade="OnceNewDefaultVersionAvailable"):
    return {"id": f"{AI}/deployments/{name}", "name": name, "sku": {"name": sku, "capacity": capacity},
            "properties": {"model": {"format": "OpenAI", "name": model, "version": version}, "versionUpgradeOption": upgrade, "currentCapacity": capacity, "provisioningState": state,
                           "rateLimits": [{"key": "request", "renewalPeriod": 10, "count": requests}, {"key": "token", "renewalPeriod": 60, "count": tokens}]}}


def answer_table(columns, rows):
    return {"tables": [{"name": "PrimaryResult", "columns": [{"name": name, "type": "string"} for name in columns], "rows": rows}]}


class Deep(Estate):
    """What the deeper tools read, in the shapes of the answers that were recorded or documented. `failures` maps a source to a status that is answered instead: workspace, tables, query,
    audit, saved, sentinel, workbooks, deployments, settings, daily, models, benefits, reservations, split, rules, collection."""

    def __init__(self):
        super().__init__()
        self.workspace = {"properties": {"customerId": CUSTOMER, "sku": {"name": "PerGB2018"}, "retentionInDays": 30, "workspaceCapping": {"dailyQuotaGb": -1, "dataIngestionStatus": "RespectQuota"},
                                         "publicNetworkAccessForQuery": "Enabled"}}
        self.tables, self.usage, self.sources, self.audit_texts = [], [], [], []
        self.audit_totals = [{"Runs": 0, "Callers": 0}]
        self.saved, self.sentinel, self.workbooks, self.deployments = [], [], [], []
        self.settings, self.splits = {}, {}
        self.daily, self.models, self.reservations = [], [], []
        self.benefits = {"P1Y": [], "P3Y": []}
        self.rule_rows, self.collection_rows = [], []
        self.on_cost = None  # called before a cost read is answered: a test moves its clock with it

    # -- the routes ------------------------------------------------------------------------------------------------------------------------------
    def __call__(self, method, url, headers, data, timeout):
        parts = urlsplit(url)
        body = json.loads(data.decode("utf-8")) if data else None
        query = parse_qs(parts.query)
        handled = self._deep(method, parts.netloc.lower(), parts.path.lower(), query, body)
        if handled is None:
            return super().__call__(method, url, headers, data, timeout)
        with self.lock:
            self.calls.append({"method": method, "url": url, "path": parts.path, "query": query, "body": body, "headers": dict(headers)})
        return handled

    def _answer(self, source, document):
        failed = self._failure(source)
        if failed == 400 and source == "sentinel":
            return 400, {}, b'{"error":{"code":"BadRequest","message":"The workspace is not onboarded to Microsoft Sentinel."}}'
        if failed == 400 and source == "audit":
            return 400, {}, b'{"error":{"code":"BadArgumentError","message":"Failed to resolve table or column expression named LAQueryLogs"}}'
        return self._refused(failed) if failed else self._json(document)

    def _deep(self, method, host, lower, query, body):
        if host == "api.loganalytics.azure.com":
            return self._query(lower, body)
        if re.fullmatch(r"/subscriptions/[^/]+/resourcegroups/[^/]+/providers/microsoft\.operationalinsights/workspaces/[^/]+", lower):
            return self._answer("workspace", self.workspace)
        if lower.endswith("/tables") and "/workspaces/" in lower:
            return self._answer("tables", {"value": self.tables})
        if lower.endswith("/savedsearches"):
            return self._answer("saved", {"value": self.saved})
        if lower.endswith("/providers/microsoft.securityinsights/alertrules"):
            return self._answer("sentinel", {"value": self.sentinel})
        if lower.endswith("/providers/microsoft.insights/workbooks"):
            return self._answer("workbooks", {"value": self.workbooks})
        if lower.endswith("/deployments") and "/accounts/" in lower:
            return self._answer("deployments", {"value": self.deployments})
        if lower.endswith("/providers/microsoft.insights/diagnosticsettings"):
            return self._answer("settings", {"value": self.settings.get(lower[:-len("/providers/microsoft.insights/diagnosticsettings")], [])})
        if lower.endswith("/providers/microsoft.costmanagement/benefitrecommendations"):
            term = re.search(r"properties/term eq '(P[13]Y)'", query["$filter"][0]).group(1)
            return self._answer("benefits", {"value": self.benefits[term]})
        if lower.endswith("/providers/microsoft.consumption/reservationrecommendations"):
            return self._answer("reservations", {"value": self.reservations})
        if "/providers/microsoft.costmanagement/query" in lower and (body["dataset"]["granularity"] == "Daily" or body["type"] == "AmortizedCost"):
            return self._cost(lower, body)
        if lower.endswith("/providers/microsoft.insights/metrics") and "$filter" in query:
            return self._split(lower[:-len("/providers/microsoft.insights/metrics")], query)
        return None

    def _graph(self, body):
        name = re.match(r"// meternaut:(\S+)", body["query"]).group(1)
        if name in ("rules-of-workspace", "collection-rules-of-workspace"):
            failed = self._failure("rules" if name.startswith("rules") else "collection") or self._failure("graph")
            if failed:
                return self._refused(failed)
            found = self.rule_rows if name.startswith("rules") else self.collection_rows
            wanted = re.search(r"contains '([^']+)'", body["query"]).group(1).lower()
            data = [r for r in found if wanted in json.dumps(r["properties"]).lower()]
            return self._json({"count": len(data), "data": data})
        return super()._graph(body)

    # -- the records of a workspace ----------------------------------------------------------------------------------------------------------------
    def _query(self, lower, body):
        text = body["query"]
        if "// meternaut:usage" in text:
            failed = self._failure("query")
            if failed:
                return self._refused(failed)
            return self._json(answer_table(["Day", "DataType", "BillableMB", "FreeMB"], [[r["Day"], r["DataType"], r["BillableMB"], r["FreeMB"]] for r in self.usage]))
        if "// meternaut:sources" in text:
            failed = self._failure("sources")
            if failed:
                return self._refused(failed)
            return self._json(answer_table(["ResourceId", "Bytes", "Whole"], [[r["ResourceId"], r["Bytes"], r["Whole"]] for r in self.sources]))
        if "// meternaut:audit" in text:
            rows = self.audit_texts if "by QueryText" in text else self.audit_totals
            columns = ["QueryText", "Runs"] if "by QueryText" in text else ["Runs", "Callers"]
            return self._answer("audit", answer_table(columns, [[r.get(column) for column in columns] for r in rows]))
        raise AssertionError(f"a read of the records that the fake does not know: {text[:60]}")

    # -- a metric split by a dimension -------------------------------------------------------------------------------------------------------------
    def _split(self, resource_id, query):
        failed = self._failure("split")
        if failed:
            return self._refused(failed)
        metric = query["metricnames"][0]
        dimension = re.match(r"(\w+) eq '\*'", query["$filter"][0]).group(1)
        values = self.splits.get((resource_id, metric), {})
        series = [{"metadatavalues": [{"name": {"value": dimension, "localizedValue": dimension}, "value": value}], "data": points} for value, points in values.items()][:int(query["top"][0])]
        return self._json({"value": [{"id": f"{resource_id}/providers/Microsoft.Insights/metrics/{metric}", "name": {"value": metric, "localizedValue": metric}, "unit": "Count",
                                      "timeseries": series, "errorCode": "Success"}]})

    # -- the cost by day and by how it was paid for ------------------------------------------------------------------------------------------------
    def _cost(self, lower, body):
        if self.on_cost:
            self.on_cost()
        sub = re.search(r"/subscriptions/([^/]+)/", lower).group(1)
        if body["dataset"]["granularity"] == "Daily":
            failed = self._failure("daily")
            if failed:
                return self._refused(failed)
            start, end = (int(body["timePeriod"][key][:10].replace("-", "")) for key in ("from", "to"))
            wanted = body["dataset"].get("filter", {}).get("dimensions")
            rows = []
            for s, day, resource, amount in self.daily:
                if s.lower() != sub or not start <= int(day.strftime("%Y%m%d")) <= end:
                    continue
                if wanted and wanted["name"] == "ResourceId" and resource not in [value.lower() for value in wanted["values"]]:
                    continue
                if wanted and wanted["name"] == "ResourceType" and tb.type_of_id(resource) != wanted["values"][0].lower():
                    continue
                rows.append([amount, int(day.strftime("%Y%m%d")), resource, self.currency])
            columns = [{"name": "Cost"}, {"name": "UsageDate"}, {"name": "ResourceId"}, {"name": "Currency"}]
            return self._json({"properties": {"columns": columns, "rows": rows}})
        failed = self._failure("models")
        if failed:
            return self._refused(failed)
        rows = [[amount, pricing, charge, self.currency] for s, pricing, charge, amount in self.models if s.lower() == sub]
        return self._json({"properties": {"columns": [{"name": "Cost"}, {"name": "PricingModel"}, {"name": "ChargeType"}, {"name": "Currency"}], "rows": rows}})


def deep():
    """An estate of one subscription with a workspace, an AI services account and a machine. The workspace has four tables."""
    estate = Deep()
    estate.rows = [row(WORKSPACE, "ws-demo", id=WS, sku={"name": "PerGB2018"}, properties={"retentionInDays": 30, "provisioningState": "Succeeded"}),
                   row(ACCOUNT, "ai-demo", id=AI, kind="OpenAI", sku={"name": "S0"}, properties={"publicNetworkAccess": "Enabled"}),
                   row(VM, "vm-demo", id=MACHINE, properties={"hardwareProfile": {"vmSize": "Standard_D2s_v3"}})]
    estate.cost_rows = [(SUB, 90.0, WS.lower(), "Log Analytics"), (SUB, 40.0, AI.lower(), "Foundry Models"), (SUB, 10.0, MACHINE.lower(), "Virtual Machines")]
    estate.tables = [table("Heartbeat"), table("AzureActivity"), table("Perf"), table("AppLog_CL", plan="Basic", kind="CustomLog", retention=8, total=8)]
    estate.usage = [usage(6, "Heartbeat", 400.0), usage(7, "Heartbeat", 600.0), usage(6, "Perf", 1000.0, 50.0), usage(7, "AppLog_CL", 3000.0), usage(8, "AzureActivity", 20.0)]
    return estate
