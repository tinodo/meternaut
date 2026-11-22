"""The invented fixtures of the evaluations answer every tool of the toolbox in the shape of the real tool.

The fixtures (evaluation/cases.jsonl, answered by tools/foundry-evals.py) are a copy of what the tools show, so a change of a tool is a change that the copy does not know. Here the real toolbox
runs on the fake estates of its own tests and the fixtures answer the same call: the two answers must have the same keys, the same columns and the same kinds of value, apart from what is
declared here to come and go with the data. A tool that is changed or added fails here until `answers_of` in tools/foundry-evals.py follows it. Every name, id and number is INVENTED."""
import ast
import datetime as dt
import importlib.util
import inspect
import json
import re
import sys
import types
import unittest
from unittest import mock

from support import NOW, REPO_ROOT
from cases import agents, brief, deeper, dossier, investigate, library, models, pricing, toolbox as tb
from cases.http import Client, allowed_calls
from cases.memory_store import MemoryStore, stamp
from cases.models import ClaimRecord
from cases.ranges import Range
from cases.redact import Redactor
from cases.toolbox import Toolbox
from deep_estate import ACCOUNT, AI, COLLECTION, MACHINE, RULES, SUB, VM, WORKSPACE, WS, deep, deployment
from test_prices import PricedEstate, line as price_line, priced
from test_toolbox import DISK, Estate, ask, definition, point, row, standard, toolbox
from test_toolbox_depth import DepthEstate, profiled
from test_toolbox_limits import Fake
from test_toolbox_meters import FIXED, WIDGET, at, billed, day, widgets

METRIC = "Processed Prompt Tokens"
SKIPPED = {"rows", "cols", "same", "properties", "cost_by_service"}  # the cells of a table, and keys that are the data: the tests of the columns and of the cells look at them
WORKSPACE_ROW, ACCOUNT_ROW, MACHINE_ROW, DISK_ROW = "workspaces-one-used-one-empty", "ai-account-with-two-deployments", "busy-machine-under-a-savings-plan", "idle-and-busy-disks"
STORY_ROW = "bastion-four-units-full-story"


def load_evals():
    spec = importlib.util.spec_from_file_location("foundry_evals_of_the_fixtures", REPO_ROOT / "tools" / "foundry-evals.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evals = load_evals()
ROWS = {r["id"]: r for r in evals.helpers.read_jsonl(REPO_ROOT / "evaluation" / "cases.jsonl", 40)}


def kind_of(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return {str: "text", list: "list", dict: "dict"}[type(value)]


def differences(real, fake, optional=frozenset(), path=""):
    """What differs in the shape of two answers: a key that only one of them has (unless its path is in `optional`), a value of another kind (a null fits every kind), and, in a list, the same of
    the first item of each. The cells of a table and the keys that are data are left out (SKIPPED)."""
    if kind_of(real) is None or kind_of(fake) is None:
        return []
    if kind_of(real) != kind_of(fake):
        return [f"{path or 'the answer'}: {kind_of(real)} in the real answer, {kind_of(fake)} in the fixture"]
    found = []
    if isinstance(real, dict):
        for key in sorted(set(real) | set(fake)):
            here = f"{path}.{key}" if path else key
            if key in SKIPPED:
                continue
            if key not in real or key not in fake:
                if here not in optional:
                    found.append(f"{here}: only in the {'real answer' if key in real else 'fixture'}")
            else:
                found += differences(real[key], fake[key], optional, here)
    elif isinstance(real, list) and real and fake:
        found += differences(real[0], fake[0], optional, path + "[]")
    return found


def deeper_estate():
    """The estate of the tests of the deeper tools with everything that they read: the sources of the readers and the writers, the deployments of an account and their traffic, the cost by day,
    how it was paid for and the recommendations of the platform."""
    estate = deep()
    estate.rule_rows = [row(RULES, "rule-1", properties={"scopes": [WS], "enabled": True, "criteria": {"allOf": [{"query": "Heartbeat | where TimeGenerated > ago(1h) | count"}]}}),
                        row(RULES, "rule-2", properties={"scopes": [WS], "enabled": False, "criteria": {"allOf": [{"query": "Perf | count"}]}})]
    estate.saved = [{"properties": {"query": "AzureActivity | take 10"}}]
    estate.workbooks = [{"properties": {"serializedData": json.dumps({"items": [{"content": {"query": "Perf | summarize count()"}}], "scope": WS}), "sourceId": "Azure Monitor"}}]
    estate.sentinel = [{"kind": "Scheduled", "properties": {"query": "Heartbeat | take 1"}}]
    estate.audit_totals = [{"Runs": 7, "Callers": 2}]
    estate.audit_texts = [{"QueryText": "Perf | take 5", "Runs": 5}, {"QueryText": "Heartbeat | take 1", "Runs": 2}]
    estate.collection_rows = [row(COLLECTION, "dcr-1", kind="Windows", properties={
        "dataSources": {"performanceCounters": [{"name": "a"}, {"name": "b"}], "windowsEventLogs": [{"name": "c"}]},
        "destinations": {"logAnalytics": [{"name": "dest", "workspaceResourceId": WS}]},
        "dataFlows": [{"streams": ["Microsoft-Perf"], "destinations": ["dest"], "transformKql": "source | where Value > 1"}, {"streams": ["Microsoft-Event"], "destinations": ["dest"]}]})]
    estate.sources = [{"ResourceId": MACHINE.lower(), "Bytes": 800_000_000, "Whole": 1_000_000_000}, {"ResourceId": "", "Bytes": 50_000_000, "Whole": 1_000_000_000}]
    estate.settings[MACHINE.lower()] = [{"name": "send-all", "properties": {"workspaceId": WS, "logs": [{"category": "a", "enabled": True}], "metrics": [{"category": "AllMetrics", "enabled": True}],
                                                                           "logAnalyticsDestinationType": "Dedicated"}}]
    estate.deployments = [deployment("prod-chat", capacity=50), deployment("test-embed", capacity=5)]
    estate.offer(ACCOUNT, METRIC, "Requests")
    estate.definitions[ACCOUNT][0]["dimensions"] = [{"value": "ModelDeploymentName", "localizedValue": "x"}, {"value": "StatusCode", "localizedValue": "x"}]
    estate.splits[(AI.lower(), METRIC)] = {"prod-chat": [point(5, total=100.0, maximum=60.0, average=50.0), point(6, total=200.0, maximum=90.0, average=100.0)],
                                           "test-embed": [point(5, total=1.0, maximum=1.0, average=1.0)]}
    estate.models = [(SUB, "OnDemand", "Usage", 1200.0), (SUB, "SavingsPlan", "Usage", 300.0)]
    estate.benefits["P1Y"] = [{"properties": {"armSkuName": "Compute_Savings_Plan", "term": "P1Y", "lookBackPeriod": "Last30Days", "commitmentGranularity": "Hourly", "currencyCode": "USD",
                                              "costWithoutBenefit": 1000.0, "recommendationDetails": {"commitmentAmount": 1.5, "coveragePercentage": 70.0,
                                                                                                      "averageUtilizationPercentage": 98.0, "savingsAmount": 120.0}}}]
    estate.reservations = [{"sku": "Standard_D2s_v3", "properties": {"term": "P1Y", "lookBackPeriod": "Last30Days", "resourceType": "VirtualMachines", "recommendedQuantity": 3,
                                                                      "costWithNoReservedInstances": 500.0, "totalCostWithReservedInstances": 350.0, "netSavings": 150.0, "currencyCode": "USD"}}]
    day = dt.date
    estate.daily = [(SUB, day(2026, 10, 20), WS.lower(), 3.0), (SUB, day(2026, 10, 21), WS.lower(), 4.5), (SUB, day(2026, 10, 21), AI.lower(), 9.0)]
    estate.platform["microsoft.cognitiveservices/accounts/deployments"] = ["properties.model.name", "properties.model.version", "properties.provisioningState",
                                                                          "properties.versionUpgradeOption", "sku.name", "sku.capacity"]  # the parts are not rows, so the platform's list is set
    return estate


class Base(unittest.TestCase):
    """The real toolbox on a fake estate, and the fixtures of the evaluations, asked the same."""

    def fixture(self, row_id, tool, **arguments):
        found = ROWS[row_id] if isinstance(row_id, str) else row_id
        return evals.answers_of(found)[tool](arguments)

    def same_shape(self, real, fake, optional=()):
        self.assertEqual(differences(real, fake, frozenset(optional)), [], f"the fixtures answer in another shape than the tool (tools/foundry-evals.py, answers_of):\nreal    {json.dumps(real)[:700]}\n"
                                                                          f"fixture {json.dumps(fake)[:700]}")

    def same_columns(self, real, fake, optional=()):
        self.assertEqual([c for c in real["cols"] if c not in optional], [c for c in fake["cols"] if c not in optional])

    def same_cells(self, real, fake):
        """The first row of each table has a cell of the same kind in every column that both have (a null fits every kind)."""
        self.assertTrue(real["rows"] and fake["rows"], "a table with no row says nothing of its cells")
        for name, cell_real, cell_fake in ((c, r, f) for c in real["cols"] if c in fake["cols"] for r, f in [(real["rows"][0][real["cols"].index(c)], fake["rows"][0][fake["cols"].index(c)])]):
            if cell_real is not None and cell_fake is not None:
                self.assertEqual(kind_of(cell_real), kind_of(cell_fake), f"the cell {name}: {cell_real!r} in the real answer, {cell_fake!r} in the fixture")


class TheOlderTools(Base):
    def setUp(self):
        self.estate = standard()
        self.box = toolbox(self.estate)

    def test_the_comparison_sees_what_it_is_for(self):
        self.assertEqual(differences({"a": 1, "b": 2}, {"a": 1}), ["b: only in the real answer"])
        self.assertEqual(differences({"a": 1}, {"a": 1, "c": 2}), ["c: only in the fixture"])
        self.assertEqual(differences({"a": 1, "b": 2}, {"a": 1}, frozenset({"b"})), [])
        self.assertEqual(differences({"a": {"x": 1}}, {"a": {"y": 1}}), ["a.x: only in the real answer", "a.y: only in the fixture"])
        self.assertEqual(differences({"a": [{"x": 1}]}, {"a": [{"x": "text"}]}), ["a[].x: number in the real answer, text in the fixture"])
        self.assertEqual(differences({"a": None}, {"a": "text"}), [])
        self.assertEqual(differences({"rows": [[1]], "cols": ["a"]}, {"rows": "no"}), [])

    def test_the_overview_the_listing_and_the_description(self):
        self.same_shape(ask(self.box, "estate_overview"), self.fixture(DISK_ROW, "estate_overview"))
        listing = ask(self.box, "list_resources", type=DISK)
        fake = self.fixture(DISK_ROW, "list_resources", type="microsoft.compute/disks")
        self.same_shape(listing, fake, optional=("reads",))
        self.assertEqual(fake["cols"][0], "handle")
        self.assertTrue(set(fake["cols"][1:]) | set(fake.get("same", {})) <= set(tb.FIXED_FIELDS), "the fields of a listing that the fixtures have are fields that the real one has")
        self.same_shape(ask(self.box, "describe", handle="r1"), self.fixture(DISK_ROW, "describe", handle="r1"), optional=("reads",))

    def test_the_metrics_of_a_type_and_the_summary_and_the_measurement_of_one(self):
        ask(self.box, "list_resources", type=VM)
        self.estate.series[(self.estate.id_of("vm-1").lower(), "Network In Total")] = [point(1, 1.5, 4, 0.5), point(2, 2.5, 5, 1.5), point(3, None, 6, 1.0)]
        names = ask(self.box, "metric_names", type=VM)
        self.same_shape(names, self.fixture(MACHINE_ROW, "metric_names", type="microsoft.compute/virtualmachines"), optional=("metrics[].dimensions",))
        summary = ask(self.box, "metric_summary", handles=["r1", "r2"], metric="Network In Total")
        self.same_shape(summary, self.fixture("some-without-data", "metric_summary", handles=["r1", "r3"], metric="Composite Disk Read Operations/sec"))
        measure = ask(self.box, "measure", type=VM, metric="Network In Total")
        fake = self.fixture("some-without-data", "measure", type="microsoft.compute/disks", metric="Composite Disk Read Operations/sec")
        self.same_shape(measure, fake)
        self.same_columns(measure, fake)
        self.same_cells(measure, fake)

    def test_a_metric_that_could_not_be_read_is_failed_in_a_measurement_and_unavailable_in_a_summary(self):
        self.estate.failures["metrics"] = 500
        box = toolbox(self.estate)
        ask(box, "list_resources", type=VM)
        summary = ask(box, "metric_summary", handles=["r1", "r2"], metric="Network In Total")
        self.same_shape(summary, self.fixture("unknown-metric-state", "metric_summary", handles=["r1", "r2"], metric="PEBytesIn"))
        self.assertEqual([r["error"] for r in summary["results"]], ["unavailable", "unavailable"])
        self.assertEqual([r["code"] for r in summary["results"]], [evals.FAILED_CODE] * 2, "the platform's code word of a failed read is in the row, and never its text")
        measure = ask(box, "measure", type=VM, metric="Network In Total")
        fake = self.fixture("unknown-metric-state", "measure", type="microsoft.network/privateendpoints", metric="PEBytesIn")
        self.same_shape(measure, fake)
        self.assertEqual((measure["failed"], fake["failed"], measure["rows"], fake["rows"]), (["r1", "r2"], ["r1", "r2", "r3"], [], []))
        self.assertEqual((measure["failed_codes"], fake["failed_codes"]), ([evals.FAILED_CODE], [evals.FAILED_CODE]))

    def test_several_metrics_and_the_grain_by_the_hour_are_answered_in_the_shape_of_the_real_tools(self):
        ask(self.box, "list_resources", type=VM)
        self.estate.series[(self.estate.id_of("vm-1").lower(), "Network In Total")] = [point(1, 1.5, 4, 0.5), point(2, 2.5, 5, 1.5)]
        invented = {**ROWS["some-without-data"], "metric": "Network In Total"}
        names = ["Network In Total", "A Name That The Type Does Not Offer"]
        summary = ask(self.box, "metric_summary", handles=["r1", "r2"], metrics=names, grain="hour")
        fake = self.fixture(invented, "metric_summary", handles=["r1", "r3"], metrics=names, grain="hour")
        self.same_shape(summary, fake)
        self.assertEqual((summary["metrics"], fake["metrics"], summary["unknown_metrics"], fake["unknown_metrics"]), (["Network In Total"],) * 2 + (1, 1))
        self.assertTrue({"metric", "peak", "p95"} <= set(summary["results"][0]) and {"metric", "peak", "p95"} <= set(fake["results"][0]))
        measure = ask(self.box, "measure", type=VM, metrics=names, grain="hour")
        fake = self.fixture(invented, "measure", type=invented["type"], metrics=names, grain="hour")
        self.same_shape(measure, fake)
        self.same_columns(measure, fake)
        self.same_cells(measure, fake)
        self.assertEqual(fake["cols"][:2] + fake["cols"][-2:], ["handle", "metric", "peak", "p95"])
        self.assertEqual(ask(self.box, "metric_summary", handles=["r1"], metrics=["Nothing", "Nowhere"]), {"error": "unknown-metric"})
        self.assertEqual(self.fixture(invented, "metric_summary", handles=["r1"], metrics=["Nothing", "Nowhere"]), {"error": "unknown-metric"})
        for arguments in ({"handles": ["r1"], "metric": "Network In Total", "metrics": ["Network In Total"]}, {"handles": ["r1"]}, {"handles": ["r1"], "metric": "Network In Total", "grain": "minute"}):
            self.assertEqual(ask(self.box, "metric_summary", **arguments), {"error": "bad-arguments"}, arguments)
            self.assertEqual(self.fixture(invented, "metric_summary", **arguments), {"error": "bad-arguments"}, arguments)

    def test_a_type_that_offers_no_platform_metrics_says_no_metrics_in_the_four_tools_that_read_a_metric(self):
        estate = widgets(1)
        estate.no_metrics = {WIDGET}
        box = toolbox(estate)
        ask(box, "list_resources", type=WIDGET)
        invented = {**ROWS[DISK_ROW], "no_metrics": True}
        for tool, real_arguments, fake_arguments in (
                ("metric_names", {"type": WIDGET}, {"type": invented["type"]}),
                ("metric_summary", {"handles": ["r1"], "metric": "Day Metric"}, {"handles": ["r1"], "metric": invented["metric"]}),
                ("measure", {"type": WIDGET, "metrics": ["Day Metric"]}, {"type": invented["type"], "metrics": [invented["metric"]]}),
                ("metric_split", {"handle": "r1", "metric": "Day Metric", "dimension": "Dim"}, {"handle": "r1", "metric": invented["metric"], "dimension": "Dim"})):
            self.assertEqual(ask(box, tool, **real_arguments), {"error": "no-metrics"}, tool)
            self.assertEqual(self.fixture(invented, tool, **fake_arguments), {"error": "no-metrics"}, tool)
        self.assertNotEqual(self.fixture(ROWS[DISK_ROW], "metric_names", type=invented["type"]).get("error"), "no-metrics", "a row that says nothing of it offers its metric")

    def test_the_cost_lines_the_advice_and_the_paid_features(self):
        self.same_shape(ask(self.box, "cost_lines", limit=3), self.fixture(DISK_ROW, "cost_lines", limit=3))
        self.same_shape(ask(self.box, "advisor_items"), self.fixture(DISK_ROW, "advisor_items"))
        self.same_shape(ask(self.box, "paid_features"), self.fixture(DISK_ROW, "paid_features"))

    def test_an_estate_with_nothing_in_it(self):
        box = toolbox(Estate())
        metric = ROWS["empty-estate"]["metric"]
        for tool, arguments in (("estate_overview", {}), ("list_resources", {"type": DISK}), ("metric_names", {"type": DISK}), ("metric_summary", {"handles": ["r1"], "metric": metric}),
                                ("measure", {"type": DISK, "metric": metric}), ("cost_lines", {}), ("cost_lines", {"type": DISK}), ("advisor_items", {}), ("paid_features", {}),
                                ("describe", {"handle": "r1"}), ("cost_history", {"type": DISK}), ("cost_meters", {"type": DISK})):
            real, fake = ask(box, tool, **arguments), self.fixture("empty-estate", tool, **arguments)
            self.same_shape(real, fake)
            if "cols" in real:
                self.same_columns(real, fake)
            self.assertEqual(real.get("error"), fake.get("error"), tool)
            self.assertEqual({key: value for key, value in real.items() if isinstance(value, (int, float, str)) and key != "error"},
                             {key: value for key, value in fake.items() if isinstance(value, (int, float, str)) and key != "error"}, f"{tool}: the same counts and words")

    def test_a_call_that_lacks_what_it_needs_is_bad_arguments_and_a_handle_that_nothing_showed_is_unknown(self):
        for tool, arguments in (("list_resources", {}), ("describe", {}), ("metric_names", {}), ("metric_summary", {"handles": ["r1"]}), ("measure", {"type": "microsoft.compute/virtualmachines"})):
            self.assertEqual(ask(self.box, tool, **arguments), {"error": "bad-arguments"}, tool)
            self.assertEqual(self.fixture(DISK_ROW, tool, **arguments), {"error": "bad-arguments"}, tool)
        self.assertEqual(ask(self.box, "describe", handle="r99"), {"error": "unknown-handle"})
        self.assertEqual(self.fixture(DISK_ROW, "describe", handle="r99"), {"error": "unknown-handle"})


class TheArguments(Base):
    """What each tool takes, and what it does with a call that does not pass."""

    VALID = {"type": "microsoft.compute/disks", "metric": "Percentage CPU", "metrics": ["Percentage CPU"], "handle": "r1", "handles": ["r1"], "dimension": "StatusCode", "table": "Heartbeat",
             "service": "Storage", "order_by": "cost", "basis": "actual", "grain": "hour", "days": 30, "limit": 5, "offset": 0, "meter": "m1"}
    ONE_OF = {"metric_summary": {"metric": "Percentage CPU"}, "measure": {"metric": "Percentage CPU"}, "cost_meters": {"handle": "r1"}}  # what a call needs besides the required, as the tool decides it

    def test_what_every_tool_takes_is_what_the_toolbox_declares(self):
        self.assertEqual(set(evals.PARAMETERS), set(tb.TOOLS))
        for name, tool in tb.TOOLS.items():
            declared = evals.PARAMETERS[name]
            self.assertEqual(list(declared), [param.name for param in tool.params], name)
            for param in tool.params:
                kind, required, limits = declared[param.name]
                self.assertEqual((kind, required), ({"integer": "int", "handles": "list", "metrics": "list", "choice": "choice"}.get(param.kind, "text"), param.required), (name, param.name))
                if kind == "int":
                    self.assertEqual(limits, (param.low, param.high), (name, param.name))
                if kind == "choice":
                    self.assertEqual(limits, param.choices, (name, param.name))
                if kind == "list":
                    self.assertEqual(limits or (1, 60), (1, tb.MAX_METRICS if param.kind == "metrics" else param.high or tb.MAX_MEASURED), (name, param.name))

    def test_a_call_that_does_not_pass_is_bad_arguments_for_the_tool_and_for_the_fixtures(self):
        bad = {"int": ["x", True, -1, 100001], "choice": ["nope", 3], "text": [5, ["r1"], ""], "list": ["r1", [], [7]]}
        for name, declared in evals.PARAMETERS.items():
            good = {**{param: self.VALID[param] for param in declared if declared[param][1]}, **self.ONE_OF.get(name, {})}
            cases = [{**good, "unknown": 1}] + [{**good, param: value} for param, (kind, required, limits) in declared.items() for value in bad[kind]
                                                 if not (kind == "int" and isinstance(value, int) and not isinstance(value, bool) and limits[0] <= value <= limits[1])]
            cases += [{key: value for key, value in good.items() if key != param} for param in good]
            if name in self.ONE_OF and "metric" in good:
                cases.append({**good, "metrics": ["Percentage CPU"]})  # the one name and the list, never both
            for arguments in cases:
                real = ask(toolbox(deeper_estate()), name, **arguments)
                fake = self.fixture(WORKSPACE_ROW, name, **arguments)
                self.assertEqual((real, fake), ({"error": "bad-arguments"},) * 2, (name, arguments))

    def test_a_call_that_passes_is_answered_and_the_bounds_are_the_ones_of_the_toolbox(self):
        for name, declared in evals.PARAMETERS.items():
            good = {**{param: self.VALID[param] for param in declared if declared[param][1]}, **self.ONE_OF.get(name, {})}
            if name == "cost_history":
                good = {"handle": "r1"}
            self.assertNotEqual(self.fixture(WORKSPACE_ROW, name, **good), {"error": "bad-arguments"}, name)
            for param, (kind, required, limits) in declared.items():
                if kind == "int":
                    for value in limits:
                        arguments = {**good, param: value}
                        self.assertNotEqual(self.fixture(WORKSPACE_ROW, name, **arguments), {"error": "bad-arguments"}, (name, arguments))
                        self.assertNotEqual(ask(toolbox(deeper_estate()), name, **arguments), {"error": "bad-arguments"}, (name, arguments))


class TheDeeperTools(Base):
    def setUp(self):
        self.estate = deeper_estate()
        self.box = toolbox(self.estate)
        self.workspace = ask(self.box, "list_resources", type=WORKSPACE)["rows"][0][0]
        self.account = ask(self.box, "list_resources", type=ACCOUNT)["rows"][0][0]
        self.machine = ask(self.box, "list_resources", type=VM)["rows"][0][0]

    def test_what_a_listing_offers_is_what_the_toolbox_offers(self):
        self.assertEqual(evals.OFFERS, deeper.OFFERS)
        real = ask(self.box, "list_resources", type=WORKSPACE)
        fake = self.fixture(WORKSPACE_ROW, "list_resources", type=WORKSPACE)
        self.assertEqual((real["reads"], fake["reads"]), (list(deeper.OFFERS[WORKSPACE]),) * 2)
        self.assertEqual(self.fixture(ACCOUNT_ROW, "list_resources", type=ACCOUNT)["reads"], list(deeper.OFFERS[ACCOUNT]))
        self.assertNotIn("reads", self.fixture(MACHINE_ROW, "list_resources", type=VM))
        self.assertEqual(self.fixture(WORKSPACE_ROW, "describe", handle="r1")["reads"], list(deeper.OFFERS[WORKSPACE]))

    def test_the_constants_of_the_fixtures_are_the_ones_of_the_toolbox(self):
        self.assertEqual((evals.READER_SOURCES, evals.CHILD_COLUMNS, evals.FIXED_FIELDS, evals.METER_COLUMNS), (tb.READER_SOURCES, tb.CHILD_COLUMNS, tb.FIXED_FIELDS, tb.METER_COLUMNS))
        self.assertEqual((evals.WORKSPACE, evals.DEPLOYMENT, evals.COLLECTION_RULE), (WORKSPACE, "microsoft.cognitiveservices/accounts/deployments", COLLECTION))
        self.assertEqual(evals.DAYS, tb.MAX_DAYS)
        real = ask(self.box, "data_writers", handle=self.machine)["diagnostic_settings"]["cols"]
        self.assertEqual(list(evals.DIAGNOSTIC_COLUMNS), real)
        self.assertLessEqual(evals.TOOL_BUDGET, tb.MAX_CALLS, "the fixtures never allow more calls than a real run does")

    def test_the_volume_of_the_tables(self):
        real = ask(self.box, "data_volume", handle=self.workspace)
        fake = self.fixture(WORKSPACE_ROW, "data_volume", handle="r1")
        self.same_shape(real, fake, optional=("free_gb",))
        self.same_columns(real, fake, optional=("free_gb",))
        self.same_cells(real, fake)
        self.assertEqual(sorted(fake["pricing"]), sorted(real["pricing"]))
        self.assertEqual(fake["tables_listed"], real["tables_listed"])

    def test_an_empty_workspace_has_no_table_with_data(self):
        self.estate.usage = []
        box = toolbox(self.estate)
        real = ask(box, "data_volume", handle=ask(box, "list_resources", type=WORKSPACE)["rows"][0][0])
        fake = self.fixture(WORKSPACE_ROW, "data_volume", handle="r2")
        self.same_shape(real, fake, optional=("free_gb",))
        self.assertEqual((real["rows"], fake["rows"], real["billable_gb"], fake["billable_gb"], real["tables_with_data"], fake["tables_with_data"]), ([], [], 0, 0, 0, 0))

    def test_what_reads_the_tables(self):
        spec = ROWS[WORKSPACE_ROW]["workspaces"]["r1"]
        onboarded = {**ROWS[WORKSPACE_ROW], "workspaces": {"r1": {**spec, "sources": {**spec["sources"], "analytics_rules": 2}}}}
        real = ask(self.box, "data_readers", handle=self.workspace)
        self.same_shape(real, self.fixture(onboarded, "data_readers", handle="r1"), optional=("sources.rules.disabled",))
        self.estate.failures["sentinel"] = 400
        box = toolbox(self.estate)
        not_enabled = ask(box, "data_readers", handle=ask(box, "list_resources", type=WORKSPACE)["rows"][0][0])
        fake = self.fixture(WORKSPACE_ROW, "data_readers", handle="r1")
        self.same_shape(not_enabled, fake, optional=("sources.rules.disabled",))
        self.assertEqual((not_enabled["sources"]["analytics_rules"], fake["sources"]["analytics_rules"]), ("not enabled", "not enabled"))
        self.same_columns(real, fake)
        self.same_cells(real, fake)
        self.assertEqual(list(fake["sources"]), list(real["sources"]))
        self.assertEqual(self.fixture(WORKSPACE_ROW, "data_readers", handle="r2")["sources"]["query_log"], "not recorded")

    def test_what_writes_to_a_workspace_and_what_a_resource_sends(self):
        real = ask(self.box, "data_writers", handle=self.workspace)
        fake = self.fixture(WORKSPACE_ROW, "data_writers", handle="r1")
        self.same_shape(real, fake)
        self.same_columns(real["collection_rules"], fake["collection_rules"])
        self.same_cells(real["collection_rules"], fake["collection_rules"])
        real = ask(self.box, "data_writers", handle=self.workspace, table="Heartbeat")
        fake = self.fixture(WORKSPACE_ROW, "data_writers", handle="r1", table="AzureDiagnostics")
        self.same_shape(real, fake)
        self.same_columns(real["table"]["writers"], fake["table"]["writers"])
        self.same_cells(real["table"]["writers"], fake["table"]["writers"])
        self.assertEqual(fake["table"]["writers"]["day"], real["table"]["writers"]["day"], "the fixtures' last closed day is the one of the toolbox's tests")
        sent = ask(self.box, "data_writers", handle=self.machine)
        fixture_sent = self.fixture(WORKSPACE_ROW, "data_writers", handle="r4")
        self.same_shape(sent, fixture_sent)
        self.same_columns(sent["diagnostic_settings"], fixture_sent["diagnostic_settings"])
        self.same_cells(sent["diagnostic_settings"], fixture_sent["diagnostic_settings"])

    def test_the_parts_of_an_account_and_a_part(self):
        real = ask(self.box, "children", handle=self.account)
        fake = self.fixture(ACCOUNT_ROW, "children", handle="r1")
        self.same_shape(real, fake)
        self.same_columns(real, fake)
        self.same_cells(real, fake)
        child = real["rows"][0][0]
        self.same_shape(ask(self.box, "describe", handle=child), self.fixture(ACCOUNT_ROW, "describe", handle="r2"))

    def test_a_metric_that_has_dimensions_and_is_split_by_one(self):
        names = ask(self.box, "metric_names", type=ACCOUNT)
        self.same_shape(names, self.fixture(ACCOUNT_ROW, "metric_names", type=ACCOUNT))
        self.assertEqual(names["metrics"][0]["dimensions"][0], "ModelDeploymentName")
        real = ask(self.box, "metric_split", handle=self.account, metric=METRIC, dimension="ModelDeploymentName")
        fake = self.fixture(ACCOUNT_ROW, "metric_split", handle="r1", metric=METRIC, dimension="ModelDeploymentName")
        self.same_shape(real, fake)
        self.same_columns(real, fake)
        self.same_cells(real, fake)

    def test_how_the_cost_was_paid_for_and_what_the_platform_recommends(self):
        real = ask(self.box, "commitments")
        fake = self.fixture(MACHINE_ROW, "commitments")
        self.same_shape(real, fake, optional=("subscriptions[].reservation",))
        with_reservation = {**ROWS[MACHINE_ROW], "commitments": {**ROWS[MACHINE_ROW]["commitments"], "reservation": [{"sku": "Standard_D2s_v3", "term": "P1Y", "lookback": "Last30Days",
                                                                                                                      "resource_type": "VirtualMachines", "quantity": 3, "cost_without": 500.0,
                                                                                                                      "cost_with": 350.0, "saving": 150.0, "currency": "USD"}]}}
        self.same_shape(real, self.fixture(with_reservation, "commitments"))
        self.assertEqual(self.fixture("idle-disk-1", "commitments")["subscriptions"][0]["savings_plan"], [])

    def test_the_cost_by_day_of_one_resource_and_of_a_type(self):
        real = ask(self.box, "cost_history", handle=self.workspace)
        fake = self.fixture(WORKSPACE_ROW, "cost_history", handle="r1")
        self.same_shape(real, fake)
        self.assertEqual((fake["from"], fake["to"], len(fake["daily"])), (real["from"], real["to"], len(real["daily"])))
        real = ask(self.box, "cost_history", type=WORKSPACE, days=60, basis="amortized")
        fake = self.fixture(WORKSPACE_ROW, "cost_history", type=WORKSPACE, days=60, basis="amortized")
        self.same_shape(real, fake)
        self.assertEqual((fake["from"], fake["to"], len(fake["daily"])), (real["from"], real["to"], len(real["daily"])))
        for bad in ({}, {"handle": "H", "type": WORKSPACE}, {"handle": "H", "days": 6}, {"handle": "H", "days": 91}, {"handle": "H", "basis": "forecast"}):
            self.assertEqual(ask(self.box, "cost_history", **{k: self.workspace if v == "H" else v for k, v in bad.items()}), {"error": "bad-arguments"}, bad)
            self.assertEqual(self.fixture(WORKSPACE_ROW, "cost_history", **{k: "r1" if v == "H" else v for k, v in bad.items()}), {"error": "bad-arguments"}, bad)
        self.assertEqual(ask(self.box, "cost_history", handle="r77"), {"error": "unknown-handle"})
        self.assertEqual(self.fixture(WORKSPACE_ROW, "cost_history", handle="r77"), {"error": "unknown-handle"})

    def test_a_read_that_a_type_does_not_have_is_not_offered_and_a_handle_that_nothing_showed_is_unknown(self):
        for tool, handle in (("data_volume", self.machine), ("data_volume", self.account), ("data_readers", self.account), ("children", self.workspace), ("children", self.machine)):
            self.assertEqual(ask(self.box, tool, handle=handle), {"error": "not-offered"}, (tool, handle))
        self.assertEqual(self.fixture(MACHINE_ROW, "data_volume", handle="r1"), {"error": "not-offered"})
        self.assertEqual(self.fixture(ACCOUNT_ROW, "data_volume", handle="r1"), {"error": "not-offered"})
        self.assertEqual(self.fixture(ACCOUNT_ROW, "data_readers", handle="r1"), {"error": "not-offered"})
        self.assertEqual(self.fixture(WORKSPACE_ROW, "children", handle="r1"), {"error": "not-offered"})
        for tool in ("data_volume", "data_readers", "data_writers", "children"):
            self.assertEqual(ask(self.box, tool, handle="r99"), {"error": "unknown-handle"}, tool)
            self.assertEqual(self.fixture(WORKSPACE_ROW, tool, handle="r99"), {"error": "unknown-handle"}, tool)
        self.assertEqual(ask(self.box, "data_writers", handle=self.machine, table="Heartbeat"), {"error": "bad-arguments"})
        self.assertEqual(self.fixture(WORKSPACE_ROW, "data_writers", handle="r4", table="AzureDiagnostics"), {"error": "bad-arguments"})
        self.assertEqual(ask(self.box, "data_writers", handle=self.workspace, table="Nope"), {"error": "bad-arguments"})
        self.assertEqual(self.fixture(WORKSPACE_ROW, "data_writers", handle="r1", table="Nope"), {"error": "bad-arguments"})
        self.assertEqual(ask(self.box, "metric_split", handle=self.account, metric="Nope", dimension="ModelDeploymentName"), {"error": "unknown-metric"})
        self.assertEqual(self.fixture(ACCOUNT_ROW, "metric_split", handle="r1", metric="Nope", dimension="ModelDeploymentName"), {"error": "unknown-metric"})
        self.assertEqual(ask(self.box, "metric_split", handle=self.account, metric=METRIC, dimension="Nope"), {"error": "bad-arguments"})
        self.assertEqual(self.fixture(ACCOUNT_ROW, "metric_split", handle="r1", metric=METRIC, dimension="Nope"), {"error": "bad-arguments"})


class TheBill(Base):
    """What a resource, or a type, is billed for, meter by meter: the real tool on the fake estate of its own tests (one meter for the scope), and the fixtures, asked the same."""

    def setUp(self):
        self.estate = widgets(2)
        billed(self.estate, self.estate.id_of("w1").lower(), FIXED, [10.0] * 7, 24.0)
        self.box = toolbox(self.estate)
        ask(self.box, "list_resources", type=WIDGET)

    def test_one_resource_a_type_and_a_service_are_answered_in_the_shape_of_the_real_tool(self):
        for arguments in ({"handle": "r1", "days": 7}, {"type": WIDGET, "days": 7}):
            real = ask(self.box, "cost_meters", **arguments)
            fake = self.fixture(DISK_ROW, "cost_meters", **{**arguments, **({"type": "microsoft.compute/disks"} if "type" in arguments else {})})
            self.same_shape(real, fake)
            self.same_columns(real, fake)
            self.same_cells(real, fake)
            self.assertEqual((fake["meters"], len(fake["rows"]), fake["rows"][0][0]), (1, 1, "m1"), "a meter handle, as the real tool gives it")
        self.assertEqual(self.fixture(DISK_ROW, "cost_meters", type="microsoft.compute/disks", days=7)["cols"][-1], "resources")
        real = ask(self.box, "cost_meters", type=WIDGET, service="Another Service", days=7)
        fake = self.fixture(DISK_ROW, "cost_meters", type="microsoft.compute/disks", service="Another Service", days=7)
        self.same_shape(real, fake)
        self.assertEqual((real["meters"], fake["meters"], real["rows"], fake["rows"]), (0, 0, [], []))

    def test_the_daily_shape_of_the_fixture_is_worked_out_from_the_cost_of_each_day(self):
        fake = self.fixture({**ROWS[DISK_ROW], "history": {"r1": [0.0] * 25 + [10.0, 0.0, 30.0, 0.0, 20.0]}}, "cost_meters", handle="r1")
        cells = dict(zip(fake["cols"], fake["rows"][0]))
        self.assertEqual((cells["usd"], cells["days"], cells["avg_day"], cells["min_day"], cells["max_day"], cells["first_day"], cells["last_day"]), (60, 3, 20, 10, 30, 5, 1))
        self.assertEqual((fake["usd_total"], cells["share"], cells["cv"]), (60, 1.0, 3.266), "the mean over the 30 days is 2, the spread is the square root of 1280 / 30, so cv is 3.266")

    def test_a_call_that_cannot_be_answered_gets_the_word_of_the_real_tool(self):
        for arguments in ({}, {"handle": "r1", "type": WIDGET}, {"handle": "r1", "days": 6}, {"handle": "r1", "days": 31}):
            self.assertEqual(ask(self.box, "cost_meters", **arguments), {"error": "bad-arguments"}, arguments)
            self.assertEqual(self.fixture(DISK_ROW, "cost_meters", **{**arguments, **({"type": "microsoft.compute/disks"} if "type" in arguments else {})}), {"error": "bad-arguments"}, arguments)
        self.assertEqual(ask(self.box, "cost_meters", handle="r77"), {"error": "unknown-handle"})
        self.assertEqual(self.fixture(DISK_ROW, "cost_meters", handle="r77"), {"error": "unknown-handle"})

    def test_a_part_of_a_resource_has_no_line_of_its_own(self):
        box = toolbox(deeper_estate())
        account = ask(box, "list_resources", type=ACCOUNT)["rows"][0][0]
        child = ask(box, "children", handle=account)["rows"][0][0]
        self.assertEqual(ask(box, "cost_meters", handle=child), {"error": "not-offered"})
        self.assertEqual(self.fixture(ACCOUNT_ROW, "cost_meters", handle="r2"), {"error": "not-offered"})


class ThePrices(Base):
    """price_alternatives: the real tool on the fake estate and the invented price list of test_prices (one meter, the line that its words name and the rate that the bill shows against its price), and the
    fixtures, asked the same."""

    def setUp(self):
        self.estate, self.box = priced()

    def test_the_table_the_line_of_the_meter_and_its_rate_are_answered_in_the_shape_of_the_real_tool(self):
        real = ask(self.box, "price_alternatives", meter="m1")
        fake = self.fixture(DISK_ROW, "price_alternatives", meter="m1")
        self.same_shape(real, fake)
        self.same_columns(real, fake, optional=("region",))
        self.same_cells(real, fake)
        self.assertEqual((set(real["current"]), set(real["same"]) | set(real["cols"])), (set(fake["current"]), set(fake["same"]) | set(fake["cols"])))
        self.assertEqual((fake["current"]["line"], fake["rows"][1][0], fake["match"], fake["unit"]), ("p2", "p2", "found", "1 Hour"), "the line of the meter itself is one of the rows")
        self.assertEqual(self.fixture(DISK_ROW, "price_alternatives", meter="m1", within="service")["within"], "service")
        self.assertEqual((self.fixture(DISK_ROW, "price_alternatives", meter="m1", offset=1)["rows"][0][0], self.fixture(DISK_ROW, "price_alternatives", meter="m1", offset=3)["rows"]), ("p2", []))

    def test_a_meter_that_nothing_showed_is_unknown_and_so_is_every_meter_of_an_estate_with_no_cost(self):
        self.assertEqual(ask(self.box, "price_alternatives", meter="m77"), {"error": "unknown-handle"})
        self.assertEqual(self.fixture(DISK_ROW, "price_alternatives", meter="m77"), {"error": "unknown-handle"})
        self.assertEqual(ask(toolbox(Estate()), "price_alternatives", meter="m1"), {"error": "unknown-handle"})
        self.assertEqual(self.fixture("empty-estate", "price_alternatives", meter="m1"), {"error": "unknown-handle"})

    def test_what_the_fixtures_say_of_the_unit_and_the_columns_is_what_the_toolbox_says(self):
        self.assertEqual((evals.PRICE_COLUMNS, evals.METER[-1], evals.PRICE_LIST[1][1]), (("price", "sku", "meter", "usd"), "1 Hour", evals.METER[1]))
        self.assertEqual(sorted(evals.PRICE_LIST, key=lambda line: line[2]), list(evals.PRICE_LIST), "the invented list is in the order of its prices, as the real tool gives it")


class TheDepth(Base):
    """neighbors, profile and changes: the real tools on the fake estate of their own tests (a service with a metric, a bill and no reference), and the fixtures, asked the same."""

    def estate(self, data=True):
        estate = profiled(2)
        estate.definitions[WIDGET] = [definition("Day Metric", "Count", "Total")]
        if data:
            estate.series[(estate.id_of("w1").lower(), "Day Metric")] = [at(day(30), total=3, maximum=3, average=3)]
        billed(estate, estate.id_of("w1").lower(), FIXED, [10.0] * 7, 24.0)
        return estate

    def box(self, estate=None):
        box = toolbox(estate or self.estate())
        ask(box, "list_resources", type=WIDGET)
        box.arm.activity_events = mock.Mock(side_effect=tb.HttpError(403, "no"))  # a Watch whose identity cannot read the Activity Log: nothing is known of the age, like an invented resource
        return box

    def test_the_references_of_a_resource_are_answered_in_the_shape_of_the_real_tool(self):
        box = self.box()
        for arguments in ({"handle": "r1"}, {"handle": "r1", "direction": "refers_to"}, {"handle": "r1", "direction": "referred_by"}, {"handle": "r1", "offset": 20}):
            real, fake = ask(box, "neighbors", **arguments), self.fixture(DISK_ROW, "neighbors", **arguments)
            self.same_shape(real, fake)
            for side in ("refers_to", "referred_by"):
                if side in real:
                    self.same_columns(real[side], fake[side])
                self.assertEqual(side in real, side in fake, arguments)
        self.assertEqual(ask(box, "neighbors", handle="r99"), {"error": "unknown-handle"})
        self.assertEqual(self.fixture(DISK_ROW, "neighbors", handle="r99"), {"error": "unknown-handle"})

    def test_a_profile_is_answered_in_the_shape_of_the_real_tool_by_the_day_and_by_the_hour(self):
        box = self.box()
        for arguments in ({"handles": ["r1"]}, {"handles": ["r1", "r2"], "days": 7}, {"handles": ["r1"], "grain": "hour"}):
            real, fake = ask(box, "profile", **arguments), self.fixture(DISK_ROW, "profile", **arguments)
            self.same_shape(real, fake)
            for one, other in zip(real["profiles"], fake["profiles"]):
                self.assertEqual((one["metrics"]["cols"], one["links"]["referred_by"]["cols"], one["sends_to"]["cols"]), (other["metrics"]["cols"], other["links"]["referred_by"]["cols"],
                                                                                                                         other["sends_to"]["cols"]))
        self.assertEqual(ask(box, "profile", handles=["r99"]), {"error": "unknown-handle"})
        self.assertEqual(self.fixture(DISK_ROW, "profile", handles=["r1", "r99"]), {"error": "unknown-handle"})

    def test_a_metric_that_has_no_data_is_listed_by_name_and_a_type_with_no_metrics_says_so_in_a_profile(self):
        real = ask(self.box(self.estate(data=False)), "profile", handles=["r1"])["profiles"][0]["metrics"]
        fake = self.fixture({**ROWS[DISK_ROW], "resources": [{"h": "r1", "usd": 30.0, "total": None}]}, "profile", handles=["r1"])["profiles"][0]["metrics"]
        self.same_shape(real, fake)
        self.assertEqual((real["rows"], fake["rows"], len(real["no_data"]), len(fake["no_data"])), ([], [], 1, 1))
        estate = self.estate()
        estate.no_metrics = {WIDGET}
        self.assertEqual(ask(self.box(estate), "profile", handles=["r1"])["profiles"][0]["metrics"], "no-metrics")
        self.assertEqual(self.fixture({**ROWS[DISK_ROW], "no_metrics": True}, "profile", handles=["r1"])["profiles"][0]["metrics"], "no-metrics")

    def test_the_age_and_the_last_change_are_answered_in_the_shape_of_the_real_tool(self):
        box = self.box()
        real, fake = ask(box, "changes", handles=["r1", "r2"]), self.fixture(DISK_ROW, "changes", handles=["r1", "r2"])
        self.same_shape(real, fake)
        self.same_columns(real, fake)
        self.assertEqual((len(real["rows"]), len(fake["rows"])), (2, 2))
        self.assertEqual(ask(box, "changes", handles=["r99"]), {"error": "unknown-handle"})
        self.assertEqual(self.fixture(DISK_ROW, "changes", handles=["r99"]), {"error": "unknown-handle"})
        self.assertEqual({cell for line in fake["rows"] for cell in line[1:]}, {"not-recorded"}, "an invented resource has no source that says how old it is")


class TheEvidence(Base):
    """What a tool keeps for the investigation to check a claim against (`Toolbox.evidence`) is what the grader of the evaluations accepts for a claim."""

    def setUp(self):
        self.estate = deeper_estate()
        self.box = toolbox(self.estate)

    def test_every_name_of_a_measurement_that_the_deeper_tools_keep_is_one_that_the_grader_knows(self):
        workspace = ask(self.box, "list_resources", type=WORKSPACE)["rows"][0][0]
        account = ask(self.box, "list_resources", type=ACCOUNT)["rows"][0][0]
        ask(self.box, "data_volume", handle=workspace)
        ask(self.box, "data_readers", handle=workspace)
        ask(self.box, "cost_history", handle=workspace)
        ask(self.box, "cost_history", handle=workspace, days=60, basis="amortized")
        ask(self.box, "metric_split", handle=account, metric=METRIC, dimension="ModelDeploymentName")
        kept = {name for handle in self.box.evidence.values() for name in handle.get("metrics", {})}
        self.assertTrue({"Billable GB Heartbeat", "Readers Heartbeat", "Runs Heartbeat", "Cost actual USD 30d", "Cost amortized USD 60d", METRIC} <= kept, kept)
        patterns = (r"Billable GB .+", r"Readers .+", r"Runs .+", r"Cost (actual|amortized) USD [0-9]{1,2}d", re.escape(METRIC))
        self.assertEqual([name for name in sorted(kept) if not any(re.fullmatch(pattern, name) for pattern in patterns)], [])
        row_of = ROWS[WORKSPACE_ROW]
        for name, total in (("Billable GB AzureDiagnostics", 142.5), ("Readers AzureDiagnostics", 6), ("Runs AzureDiagnostics", 40), ("Cost actual USD 30d", 410.0), ("Cost amortized USD 7d", 95.67)):
            self.assertEqual(evals.evidence_total(row_of, "r1", name), (True, total), name)
        self.assertEqual(evals.evidence_total(row_of, "r1", "Readers Nope"), (False, None))
        self.assertEqual(evals.evidence_total(row_of, "r2", "Billable GB AzureDiagnostics"), (False, None))
        self.assertEqual(evals.evidence_total(ROWS[ACCOUNT_ROW], "r2", METRIC), (True, 912000))
        self.assertEqual(evals.evidence_total(row_of, ["r1"], "Heartbeat"), (False, None))


def nested(props):
    """The properties and the sku of a resource that hold what a fixture lists as dotted keys: `sku.*` is the root's sku, and any other key is relative to the properties of the resource."""
    properties, sku = {}, {}
    for path, value in props.items():
        keys = path.split(".")
        node, rest = (sku, keys[1:]) if keys[0] == "sku" else (properties, keys)
        for key in rest[:-1]:
            node = node.setdefault(key, {})
        node[rest[-1]] = value
    return properties, sku or None


def real_of(spec):
    """The real toolbox on an estate of the resources that a row of the fixtures says it has: the properties and the cost of each, and the one metric of its type. Its listing has been read."""
    estate = DepthEstate()
    for resource in spec["resources"]:
        properties, sku = nested((spec.get("props") or {}).get(resource["h"], {}))
        estate.rows.append(row(spec["type"], f"n{resource['h']}", properties=properties, sku=sku))
        estate.cost_rows.append((SUB, resource["usd"], estate.rows[-1]["id"].lower(), spec.get("service") or "Storage"))
    estate.definitions[spec["type"]] = [definition(spec["metric"], "Count", "Total")]
    box = toolbox(estate)
    ask(box, "list_resources", type=spec["type"])
    box.arm.activity_events = mock.Mock(side_effect=tb.HttpError(403, "no"))  # a Watch whose identity cannot read the Activity Log: nothing is known of the age, like an invented resource
    return box


class TheProperties(Base):
    """The properties that a row gives its resources (`props`): the tools of the fixtures show them with the keys, the values, the order and in the places where the real toolbox shows the properties of
    a resource, and the ranking of a key that the tool hands to the app's own check of a setting is the toolbox's own. Every kind, property and number is INVENTED."""

    PROPS = {"r1": {"scaleUnits": 4, "provisioningState": "Succeeded", "sku.capacity": 2, "networkAcls.defaultAction": "Deny", "numberOfSites": 3, "zoneRedundant": False, "retentionDays": 30},
             "r2": {"scaleUnits": 2, "provisioningState": "Succeeded", "sku.capacity": 2, "networkAcls.defaultAction": "Deny", "numberOfSites": 3, "zoneRedundant": False, "retentionDays": 30}}
    INVENTED = {"id": "invented", "kind": "clean", "type": WIDGET, "metric": "Day Metric", "service": "Example Service", "resources": [{"h": "r1", "usd": 99.0, "total": 3}, {"h": "r2", "usd": 98.0, "total": 3}],
                "props": PROPS, "expect": {"propose": [], "never": []}}

    @staticmethod
    def cells(answer):
        """The properties of a listing: the names of its property columns and of its `same` block in the order of the answer, and the value of each for each handle."""
        shown = {name: {line[0]: value for line in answer["rows"]} for name, value in answer.get("same", {}).items() if name not in tb.FIXED_FIELDS}
        for line in answer["rows"]:
            for name, value in zip(answer["cols"][1:], line[1:]):
                if name not in tb.FIXED_FIELDS:
                    shown.setdefault(name, {})[line[0]] = value
        return [name for name in (*answer.get("same", {}), *answer["cols"][1:]) if name not in tb.FIXED_FIELDS], shown

    def test_the_properties_of_a_row_are_shown_by_describe_by_profile_and_by_the_listing_as_the_real_toolbox_shows_them(self):
        for spec in (*(r for r in ROWS.values() if r.get("props")), self.INVENTED):
            with self.subTest(row=spec["id"]):
                box, handles = real_of(spec), [r["h"] for r in spec["resources"]]
                for handle in handles:
                    real, fake = ask(box, "describe", handle=handle)["properties"], self.fixture(spec, "describe", handle=handle)["properties"]
                    self.assertTrue(real, "the real tool shows these properties of a resource that has them")
                    self.assertEqual(list(real.items()), list(fake.items()), f"{handle}: the same keys, the same values and the same order")
                real_parts, fake_parts = ask(box, "profile", handles=handles)["profiles"], self.fixture(spec, "profile", handles=handles)["profiles"]
                self.assertEqual([list(part["properties"].items()) for part in real_parts], [list(part["properties"].items()) for part in fake_parts])
                real_list, fake_list = ask(box, "list_resources", type=spec["type"]), self.fixture(spec, "list_resources", type=spec["type"])
                self.assertTrue(self.cells(real_list)[1], "the real listing shows the properties of a resource")
                self.assertEqual(self.cells(real_list), self.cells(fake_list), "a property that varies is a column and one that is the same in every row is in `same`, in the toolbox's order")

    def test_a_row_without_props_shows_no_property_and_a_handle_that_has_none_shows_none(self):
        self.assertEqual(self.fixture(DISK_ROW, "describe", handle="r1")["properties"], {})
        self.assertEqual(self.fixture(self.INVENTED, "describe", handle="r2")["properties"], dict(sorted(self.PROPS["r2"].items(), key=lambda item: evals._order(item[0]))))
        without = {**self.INVENTED, "props": {"r1": self.PROPS["r1"]}}
        self.assertEqual(self.fixture(without, "describe", handle="r2")["properties"], {})
        self.assertEqual(self.fixture(without, "profile", handles=["r2"])["profiles"][0]["properties"], {})

    def test_what_the_tool_shows_of_a_resource_is_at_most_what_the_toolbox_shows(self):
        many = {f"count{n:02d}Count": n for n in range(40)}
        properties, sku = nested(many)
        real = tb.typed_properties(properties, sku, tb.Listing(frozenset((key,) for key in many)))
        self.assertEqual(len(real), tb.DESCRIBED_PROPERTIES)
        shown = self.fixture({**self.INVENTED, "props": {"r1": many}}, "describe", handle="r1")["properties"]
        self.assertEqual(list(shown.items()), real, "the same thirty, the most informative first")

    def test_the_ranking_of_a_key_that_the_tool_gives_the_apps_check_of_a_setting_is_the_toolboxs_own(self):
        self.assertEqual((evals.SUFFIXES, evals.COUNT_LIKE, evals.DESCRIBED_PROPERTIES), (tb.SUFFIXES, tb.COUNT_LIKE, tb.DESCRIBED_PROPERTIES))
        for name in ("_rank", "_order"):
            self.assertEqual(ast.dump(ast.parse(inspect.getsource(getattr(evals, name)))), ast.dump(ast.parse(inspect.getsource(getattr(tb, name)))),
                             f"{name} in tools/foundry-evals.py is the toolbox's own, written again for the Operator's volume, which cannot hold the toolbox: change both")

    def test_the_apps_own_gate_on_a_count_that_the_tool_loads_answers_as_the_real_one_does(self):
        from cases import proposals as app

        pricing, proposals = evals.app_code()
        for path in ("scaleUnits", "capacityUnits", "sku.capacity", "numberOfSites", "numberOfDaysToKeep", "retentionDays", "retentionCount", "backupCount", "keepAliveCount", "maxThrottleCount",
                     "ipConfigurationsCount", "rulesCount", "provisioningState", "zoneRedundant", "diskSizeGB", "maxThroughputMbps", "replicas", "x", "", "scale Units", "ünitsUnits", 7, None):
            self.assertEqual(proposals.countlike(path), app.countlike(path), path)
        self.assertTrue(proposals.countlike("scaleUnits") and not proposals.countlike("retentionDays"))
        self.assertIsNot(proposals, app, "the tool loads the app's own file under the name of the flat package, so that the Operator's volume and the repository give the same code")
        self.assertIs(pricing.parse(None), None)


class TheKnowledge(Base):
    """What `recall_knowledge` shows of a row (`knowledge`): the claims of the Study as the real tool shows them, and the checks that the Study makes of a claim, held to each claim of the rows. Every kind,
    address and quote that a test invents here is INVENTED; the quotes of the shipped rows are those of the page that they name."""

    CLAIMS = [{"kind": "quota-limit", "url": "https://learn.microsoft.com/en-us/azure/example-widgets/limits", "quote": "A widget supports at most 40 concurrent connections for medium workloads"},
              {"kind": "other", "url": "https://learn.microsoft.com/en-us/azure/example-widgets/limits", "quote": "Any change to the units of a widget disrupts the connections that are open."}]
    INVENTED = {"id": "invented", "kind": "clean", "type": "microsoft.example/widgets", "metric": "Sessions", "resources": [{"h": "r1", "usd": 99.0, "total": 12}], "knowledge": CLAIMS,
                "expect": {"propose": [], "never": []}}

    @staticmethod
    def real(spec, resource_type=None):
        """What the real tool shows for a type, from a store that holds the claims of a row, each read on the day of the fixtures and still current."""
        store = MemoryStore(clock=lambda: NOW)
        for n, claim in enumerate(spec.get("knowledge") or []):
            store.claim_put(ClaimRecord(claim_id=f"c{n}", resource_type=spec["type"], kind=claim["kind"], url=claim["url"], quote=claim["quote"], read_at=f"{evals.KNOWLEDGE_READ}T09:00:00Z",
                                        checked_at=stamp(NOW), expires_at=stamp(NOW + dt.timedelta(days=20)), state="fresh"))
        tools = Toolbox(None, (), NOW, [])
        tools.memory = store
        return json.loads(tools.call("recall_knowledge", {"type": resource_type or spec["type"]}))

    @staticmethod
    def claims_of(answer):
        return sorted((claim["kind"], claim["read"], claim["url"], claim["quote"]) for claim in answer["claims"])

    def test_the_claims_of_a_row_are_shown_in_the_shape_and_the_words_of_the_real_tool(self):
        for spec in (ROWS["lightly-used-bastion-with-four-units"], self.INVENTED):
            with self.subTest(row=spec["id"]):
                real, fake = self.real(spec), self.fixture(spec, "recall_knowledge", type=spec["type"])
                self.assertEqual(len(real["claims"]), len(spec["knowledge"]), "the real tool shows every claim that is current")
                self.same_shape(real, fake, optional=("not_shown",))
                self.assertEqual((fake["type"], fake["source"], fake["studied"]), (real["type"], real["source"], real["studied"]))
                self.assertEqual(self.claims_of(fake), self.claims_of(real))
                self.assertEqual([list(claim) for claim in fake["claims"]], [["kind", "read", "url", "quote"]] * len(spec["knowledge"]), "the fields and their order")

    def test_a_row_without_knowledge_answers_as_it_did_and_as_the_real_tool_does_for_a_type_that_was_never_studied(self):
        for row_id in ("idle-bastion-with-four-units", "busy-bastion-with-four-units", DISK_ROW):
            with self.subTest(row=row_id):
                spec = ROWS[row_id]
                self.assertNotIn("knowledge", spec)
                self.assertEqual(self.fixture(spec, "recall_knowledge", type=spec["type"]), self.real(spec))
        hostile = next(r for r in ROWS.values() if r["kind"] == "hostile")
        shown = self.fixture(hostile, "recall_knowledge", type=hostile["type"])
        self.assertEqual((len(shown["claims"]), shown["claims"][0]["kind"], shown["claims"][0]["quote"], shown["studied"]),
                         (1, "minimum-charge", list(hostile["inject"].values())[0], evals.KNOWLEDGE_READ), "a hostile text is still the quote of one claim")

    def test_the_claims_of_a_row_are_those_of_its_own_type_and_those_of_the_text_from_outside_come_after_them(self):
        spec = ROWS["lightly-used-bastion-with-four-units"]
        other = self.fixture(spec, "recall_knowledge", type="microsoft.compute/disks")
        self.assertEqual((other["claims"], other["studied"]), ([], "not yet"), "a type that the row is not of was never studied")
        self.assertEqual(self.real(spec, "microsoft.compute/disks")["claims"], [])
        both = self.fixture({**self.INVENTED, "inject": {"r1": "a text from outside"}}, "recall_knowledge", type=self.INVENTED["type"])
        self.assertEqual([claim["quote"] for claim in both["claims"]], [claim["quote"] for claim in self.CLAIMS] + ["a text from outside"])
        many = {**self.INVENTED, "knowledge": [{**self.CLAIMS[0], "quote": f"Widget number {n} supports at most forty connections"} for n in range(library.SHOWN + 3)]}
        self.assertEqual(len(self.fixture(many, "recall_knowledge", type=many["type"])["claims"]), library.SHOWN, "the real tool shows this many claims of a type")
        self.assertEqual(len(self.real(many)["claims"]), library.SHOWN)

    def test_every_claim_of_every_row_passes_the_checks_that_the_study_makes_of_a_claim(self):
        for spec in (*ROWS.values(), self.INVENTED):
            claims = spec.get("knowledge") or []
            self.assertLessEqual(len(claims), library.SHOWN, spec["id"])
            for claim in claims:
                with self.subTest(row=spec["id"], quote=claim["quote"][:40]):
                    self.assertEqual(set(claim), {"kind", "url", "quote"})
                    self.assertIn(claim["kind"], models.CLAIM_KINDS, "a kind of the closed list: the Study throws the others away")
                    self.assertEqual(library.doc_url(claim["url"]), claim["url"], "an address of a page that the Study may read: Microsoft's own documentation")
                    self.assertIsNotNone(library.QUOTE_FORM.fullmatch(claim["quote"]), "words, numbers and the marks of a sentence, 20 to 200 characters")
                    self.assertNotIn("://", claim["quote"])
                    self.assertTrue(library.QUOTE_MIN <= len(claim["quote"]) <= library.QUOTE_MAX)

    def test_the_constants_that_the_tool_repeats_of_the_study_are_the_apps_own(self):
        self.assertEqual(evals.KNOWLEDGE_SHOWN, library.SHOWN)
        self.assertEqual(dt.date.fromisoformat(evals.KNOWLEDGE_READ).isoformat(), evals.KNOWLEDGE_READ, "a day, as the real tool gives it")


class TheLimits(Base):
    """The limits that a row gives its resources (`limits`): the lowest and the highest number that Microsoft's reference page of the type documents for a property. The tools of the fixtures show them
    where and as the real toolbox shows them for the same properties (cases/toolbox.py `_limits_of`): for a count or a size that is a number, once for a listing and in each part of a profile. Every kind,
    property and number is INVENTED, except that the row of the lightly used host has the numbers that the reference page gives for its one property."""

    PROPS = {"r1": {"scaleUnits": 4, "provisioningState": "Succeeded", "sku.capacity": 2, "numberOfWorkers": 3, "zoneRedundant": False, "retentionDays": 30},
             "r2": {"scaleUnits": 2, "provisioningState": "Succeeded", "sku.capacity": 1, "numberOfWorkers": 3, "zoneRedundant": False, "retentionDays": 30}}
    LIMITS = {"r1": {"scaleUnits": {"lowest": 2, "highest": 50}, "sku.capacity": {"lowest": 1}, "numberOfWorkers": {"highest": 30}, "retentionDays": {"lowest": 7, "highest": 90},
                     "zoneRedundant": {"lowest": 0, "highest": 1}}}
    LIMITS["r2"] = LIMITS["r1"]
    INVENTED = {"id": "invented", "kind": "clean", "type": WIDGET, "metric": "Day Metric", "service": "Example Service", "resources": [{"h": "r1", "usd": 99.0, "total": 3}, {"h": "r2", "usd": 98.0, "total": 3}],
                "props": PROPS, "limits": LIMITS, "expect": {"propose": [], "never": []}}

    @staticmethod
    def real(spec):
        """The real toolbox on the estate of the row, with a reader that gives each leaf the range that the row gives it, the same for the whole type, as a page does."""
        box = real_of(spec)
        found = {path.rsplit(".", 1)[-1]: Range(bounds.get("lowest"), bounds.get("highest")) for handle in (spec.get("limits") or {}).values() for path, bounds in handle.items()}
        box.ranges = Fake({spec["type"]: found})
        return box

    def test_the_limits_of_a_row_are_shown_by_describe_by_profile_and_by_the_listing_as_the_real_toolbox_shows_them(self):
        for spec in (ROWS["lightly-used-bastion-with-four-units"], self.INVENTED):
            with self.subTest(row=spec["id"]):
                box, handles = self.real(spec), [r["h"] for r in spec["resources"]]
                for handle in handles:
                    real, fake = ask(box, "describe", handle=handle), self.fixture(spec, "describe", handle=handle)
                    self.assertTrue(real["limits"], "the real tool shows the limits of a resource that has them")
                    self.assertEqual(real["limits"], fake["limits"])
                    self.assertEqual(list(real["limits"]), list(fake["limits"]), "in the order of the properties")
                self.assertEqual([part["limits"] for part in ask(box, "profile", handles=handles)["profiles"]], [part["limits"] for part in self.fixture(spec, "profile", handles=handles)["profiles"]])
                real_list, fake_list = ask(box, "list_resources", type=spec["type"]), self.fixture(spec, "list_resources", type=spec["type"])
                self.assertEqual(real_list["limits"], fake_list["limits"], "one mapping for the whole listing")
                self.same_shape(real_list, fake_list)
                self.assertEqual(list(fake_list).index("limits"), list(fake_list).index("cols") - 1, "it comes after the fields that every row shares, before the columns")

    def test_only_a_count_or_a_size_that_is_a_number_has_limits_whatever_the_row_gives_for_a_word_a_flag_or_a_period(self):
        shown = self.fixture(self.INVENTED, "describe", handle="r1")
        self.assertEqual(set(shown["limits"]), {"scaleUnits", "sku.capacity", "numberOfWorkers"})
        for name in ("retentionDays", "zoneRedundant", "provisioningState"):
            self.assertIn(name, shown["properties"], "the property is shown")
        self.assertEqual(set(ask(self.real(self.INVENTED), "describe", handle="r1")["limits"]), set(shown["limits"]))

    def test_a_row_without_limits_and_a_limit_for_a_property_that_the_row_does_not_show_show_none_as_the_real_toolbox_does(self):
        without = {key: value for key, value in self.INVENTED.items() if key != "limits"}
        for answer in (self.fixture(without, "describe", handle="r1"), self.fixture(without, "list_resources", type=without["type"]), *self.fixture(without, "profile", handles=["r1"])["profiles"]):
            self.assertNotIn("limits", answer)
        elsewhere = {**self.INVENTED, "limits": {"r1": {"notShown": {"lowest": 1}}}}
        self.assertNotIn("limits", self.fixture(elsewhere, "describe", handle="r1"))
        self.assertNotIn("limits", self.fixture({**self.INVENTED, "limits": {"r2": {"scaleUnits": {"lowest": 2}}}}, "describe", handle="r1"), "the limits of another handle are not this one's")
        self.assertNotIn("limits", self.fixture(ROWS[DISK_ROW], "describe", handle="r1"))
        bare = ROWS["lightly-used-bastion-without-limits"]
        for answer in (self.fixture(bare, "describe", handle="r1"), self.fixture(bare, "list_resources", type=bare["type"]), *self.fixture(bare, "profile", handles=["r1"])["profiles"]):
            self.assertNotIn("limits", answer, "the row of the same host with no limits shows none, as a toolbox whose reader read no page does")
            self.assertIn("scaleUnits", json.dumps(answer), "and it shows the property that a setting would lower")

    def test_every_limit_of_every_row_is_a_range_of_a_whole_number_of_a_property_that_the_row_shows(self):
        for spec in ROWS.values():
            for handle, held in (spec.get("limits") or {}).items():
                with self.subTest(row=spec["id"], handle=handle):
                    self.assertIn(handle, (spec.get("props") or {}))
                    shown = self.fixture(spec, "describe", handle=handle)
                    self.assertEqual(set(held), set(shown["limits"]), "a limit that a row gives is one that a tool shows: a count or a size that is a number among its properties")
                    for bounds in held.values():
                        self.assertTrue(bounds and set(bounds) <= {"lowest", "highest"})
                        self.assertTrue(all(isinstance(number, int) and not isinstance(number, bool) for number in bounds.values()))
                        self.assertLessEqual(bounds.get("lowest", 0), bounds.get("highest", 10 ** 9))
            for path in {path for held in (spec.get("limits") or {}).values() for path in held}:
                self.assertEqual(len({json.dumps(held[path], sort_keys=True) for held in (spec.get("limits") or {}).values() if path in held}), 1, "a page is the page of a type: one range for a name")
        self.assertEqual(ROWS["lightly-used-bastion-with-four-units"]["limits"], {"r1": {"scaleUnits": {"lowest": 2, "highest": 50}}}, "what the reference page of the type says of its property")
        self.assertEqual([r["id"] for r in ROWS.values() if r.get("limits")], ["lightly-used-bastion-with-four-units", "bastion-four-units-full-story", "heldout-appgw-mincap"],
                         "the rows that give a range: the two of the host (its one property, as the page gives it) and the held-out gateway (the minimum and the maximum capacity of its autoscale, Min value = 0 and Min value = 2 on the reference page of its type, which the app's own reader makes of that page)")


class StoryEstate(PricedEstate, DepthEstate):
    """The fake estate of the list of prices and the fake estate of the references and the Activity Log in one: a resource whose bill, list and profile the real toolbox can all read."""


class TheStory(Base):
    """What a row that gives `meters` and `prices` shows of its bill and of the list of its product, and its SKU: the tools of the fixtures show them where and as the real toolbox shows what a resource is billed
    for (cost_meters, and the dearest of them in profile) and the prices of the list (price_alternatives), held to the real toolbox on the same data: a bill that has a line for each of the 30 days, and a list that
    the fake host of test_prices gives. The row of the whole story has the words and the prices that the public list gave on 2026-11-21; the other row here is INVENTED."""

    @staticmethod
    def item(name, per_day, rate, unit="1 Hour"):
        return {"subcategory": "Standard Tier", "name": name, "pricing": "OnDemand", "charge": "Usage", "unit": unit, "per_day": per_day, "usd_per_unit": rate}

    @staticmethod
    def listed(sku, name, usd, unit="1 Hour"):
        return {"sku": sku, "meter": name, "usd": usd, "unit": unit}

    def invented(self):
        return {"id": "invented", "kind": "clean", "type": WIDGET, "metric": "Day Metric", "service": "Example Service", "resources": [{"h": "r1", "usd": 1410.0, "total": 3, "sku": "Standard"}],
                "meters": [self.item("Small Units", 1, 1.0), self.item("Big Units", 10, 2.0), self.item("Alpha Units", 10, 2.0), self.item("Per GB", 2, 3.0, "1 GB")],
                "prices": [self.listed("Plus", "Big Units", 3.0), self.listed("Basic", "Alpha Units", 2.0), self.listed("Basic", "Small Units", 0.5), self.listed("Plus", "Small Units", 0.75),
                           self.listed("Basic", "Per GB Lite", 1.0, "1 GB")], "expect": {"propose": [], "never": []}}

    @staticmethod
    def real(spec):
        """The real toolbox on an estate of the one resource of a row, billed for the meters of the row on each of its 30 days, with the list that the row gives on the fake host of the list. Its listing has been read."""
        estate = StoryEstate()
        resource = spec["resources"][0]
        properties, sku = nested((spec.get("props") or {}).get(resource["h"], {}))
        estate.rows.append(row(spec["type"], "n1", properties=properties, sku={"name": resource["sku"]} if resource.get("sku") else sku))
        resource_id = estate.rows[0]["id"].lower()
        estate.cost_rows.append((SUB, resource["usd"], resource_id, spec["service"]))
        for item in spec["meters"]:
            words = (spec["service"], *(item[name] for name in evals.METER_FIELDS[:5]))
            for n in range(evals.DAYS):
                estate.bill.append((SUB, dt.date(2026, 10, 5) + dt.timedelta(days=n), resource_id, spec["service"], words, round(item["per_day"] * item["usd_per_unit"], 2), item["per_day"]))
        estate.definitions[spec["type"]] = [definition(spec["metric"], "Count", "Total")]
        estate.lines = [price_line(line["sku"], line["meter"], line["usd"], line["unit"], product=spec["meters"][0]["subcategory"], service=spec["service"]) for line in spec.get("prices") or []]
        box = toolbox(estate)
        ask(box, "list_resources", type=spec["type"])
        box.arm.activity_events = mock.Mock(side_effect=tb.HttpError(403, "no"))  # a Watch whose identity cannot read the Activity Log: nothing is known of the age, like an invented resource
        return box

    def specs(self):
        return (ROWS[STORY_ROW], self.invented())

    def test_what_a_resource_and_a_type_are_billed_for_is_shown_as_the_real_toolbox_shows_it_in_every_window(self):
        for spec in self.specs():
            for arguments in ({"handle": "r1"}, {"handle": "r1", "days": 7}, {"type": spec["type"]}, {"type": spec["type"], "days": 14}, {"handle": "r1", "service": spec["service"]},
                              {"type": spec["type"], "service": "Another Service"}):
                with self.subTest(row=spec["id"], arguments=arguments):
                    real, fake = ask(self.real(spec), "cost_meters", **arguments), self.fixture(spec, "cost_meters", **arguments)
                    self.assertEqual(real, fake, "the same answer, value for value: the handles in the order of the cost, the words that every line shares once, the daily shape of a meter that costs the same every day")

    def test_a_later_page_of_the_meters_is_shown_as_the_real_toolbox_shows_it_once_the_first_page_has_given_the_handles(self):
        for spec in self.specs():
            box = self.real(spec)
            ask(box, "cost_meters", handle="r1")  # a real run gives a meter its handle the first time that it shows it: the second page of a call after the first page keeps the handles
            with self.subTest(row=spec["id"]):
                real, fake = ask(box, "cost_meters", handle="r1", offset=1), self.fixture(spec, "cost_meters", handle="r1", offset=1)
                self.assertEqual(real, fake)
                self.assertEqual((fake["offset"], fake["returned"], "same" in fake, fake["rows"][0][0]), (1, len(spec["meters"]) - 1, len(spec["meters"]) > 2, "m2"))

    def test_a_page_of_forty_ends_with_the_offset_of_the_next_and_the_words_that_the_lines_of_a_page_share_are_those_of_that_page_alone_as_the_real_toolbox_gives_them(self):
        spec = self.big()
        box = self.real(spec)
        first = ask(box, "cost_meters", handle="r1")
        self.assertEqual(first, self.fixture(spec, "cost_meters", handle="r1"))
        self.assertEqual((first["meters"], first["returned"], first["next_offset"]), (42, 40, 40))
        real, fake = ask(box, "cost_meters", handle="r1", offset=40), self.fixture(spec, "cost_meters", handle="r1", offset=40)
        self.assertEqual(real, fake)
        self.assertEqual((fake["returned"], "next_offset" in fake, fake["same"].get("unit"), "unit" in fake["cols"]), (2, False, "1 GB", False), "the two lines of the last page share a unit that the first page does not")
        for offset in (0, 40):
            real, fake = ask(box, "price_alternatives", meter="m1", offset=offset), self.fixture(spec, "price_alternatives", meter="m1", offset=offset)
            self.assertEqual(real, fake, f"offset {offset}")
        self.assertEqual((ask(box, "price_alternatives", meter="m1")["lines"], ask(box, "price_alternatives", meter="m1")["next_offset"]), (45, 40))

    def big(self):
        meters = [self.item(f"Unit {place:02d}", 1, 2.0 + place / 100) for place in range(40)] + [self.item("Gb A", 1, 0.5, "1 GB"), self.item("Gb B", 1, 0.4, "1 GB")]
        cost = round(sum(round(item["per_day"] * item["usd_per_unit"], 2) for item in meters) * evals.DAYS, 2)
        return {**self.invented(), "meters": meters, "prices": [self.listed("Basic", f"Unit {place:02d}", 1.0 + place / 100) for place in range(45)], "resources": [{"h": "r1", "usd": cost, "total": 3, "sku": "Standard"}]}

    def test_the_dearest_six_meters_of_a_resource_and_its_sku_are_shown_by_a_profile_as_the_real_toolbox_shows_them(self):
        many = {**self.invented(), "meters": [self.item(f"Unit {name}", 1, 1 + place / 10) for place, name in enumerate("ABCDEFGH")], "prices": [], "resources": [{"h": "r1", "usd": 297.0, "total": 3, "sku": "Standard"}]}
        for spec in (*self.specs(), many):
            with self.subTest(row=spec["id"], meters=len(spec["meters"])):
                real = ask(self.real(spec), "profile", handles=["r1"])["profiles"][0]
                fake = self.fixture(spec, "profile", handles=["r1"])["profiles"][0]
                self.assertEqual((real["sku"], real["meters"]), (fake["sku"], fake["meters"]))
                self.assertLessEqual(len(fake["meters"]["rows"]), evals.DOSSIER_METERS)
        self.assertEqual(len(self.fixture(many, "profile", handles=["r1"])["profiles"][0]["meters"]["rows"]), 6)
        self.assertEqual(evals.DOSSIER_METERS, dossier.METER_ROWS)

    def test_the_sku_of_a_resource_is_shown_by_the_listing_and_by_a_description_as_the_real_toolbox_shows_it(self):
        spec = self.invented()
        box = self.real(spec)
        self.assertEqual(ask(box, "list_resources", type=spec["type"]), self.fixture(spec, "list_resources", type=spec["type"]))
        self.assertEqual(ask(box, "describe", handle="r1")["sku"], self.fixture(spec, "describe", handle="r1")["sku"])
        bare = {**spec, "resources": [{"h": "r1", "usd": 1410.0, "total": 3}]}
        self.assertEqual((self.fixture(bare, "describe", handle="r1")["sku"], "sku" in self.fixture(bare, "list_resources", type=spec["type"])["cols"]), (None, False))

    def test_the_prices_of_the_list_and_the_line_of_each_meter_are_shown_as_the_real_toolbox_shows_them_for_every_meter_of_a_row(self):
        for spec in self.specs():
            box = self.real(spec)
            ask(box, "cost_meters", handle="r1")  # the meters get their handles, the way that a run gets them
            for number in range(1, len(spec["meters"]) + 1):
                with self.subTest(row=spec["id"], meter=f"m{number}"):
                    real, fake = ask(box, "price_alternatives", meter=f"m{number}"), self.fixture(spec, "price_alternatives", meter=f"m{number}")
                    self.assertEqual(real, fake, "the same answer, value for value: the lines in the unit of the meter, the line that has its name as current, the rate that the bill paid against it, and the handles")
        real_box = self.real(self.specs()[0])
        ask(real_box, "cost_meters", handle="r1")
        real = ask(real_box, "price_alternatives", meter="m1")
        self.assertEqual((real["match"], real["current"]["retail"], real["lines"], real["other_units"]), ("found", 0.29, 6, 1), "the shipped row: the base charge against the list of its product")

    def test_the_held_out_rows_are_shown_as_the_real_toolbox_shows_them_in_their_bill_their_list_and_their_profile(self):
        held = [r for r in ROWS.values() if r["id"].startswith("heldout-") and r.get("meters")]
        self.assertEqual([r["id"] for r in held], ["heldout-firewall", "heldout-appgw-mincap", "heldout-sql-vcores", "heldout-sql-busy"], "the four rows of other kinds give a bill and a list, as the real words of the list of 2026-11-22 name them")
        for spec in held:
            with self.subTest(row=spec["id"]):
                box = self.real(spec)
                self.assertEqual(ask(box, "cost_meters", handle="r1"), self.fixture(spec, "cost_meters", handle="r1"), "the same answer, value for value")
                for number in range(1, len(spec["meters"]) + 1):
                    real, fake = ask(box, "price_alternatives", meter=f"m{number}"), self.fixture(spec, "price_alternatives", meter=f"m{number}")
                    self.assertEqual(real, fake, f"m{number}: the lines in the unit of the meter, the line that has its name as current, and the handles")
                real_profile, fake_profile = ask(box, "profile", handles=["r1"])["profiles"][0], self.fixture(spec, "profile", handles=["r1"])["profiles"][0]
                self.assertEqual((real_profile["sku"], real_profile["meters"]), (fake_profile["sku"], fake_profile["meters"]))

    def test_the_registers_that_the_replay_reads_of_the_calls_of_the_investigator_are_the_real_toolboxs_for_the_same_calls_the_meters_that_share_a_list_with_the_asked_one_included(self):
        story = ROWS[STORY_ROW]
        # The base charge (m1) and the additional units (m2) of the story share their list. The invented row has a meter in another unit (m3) and a meter whose name two lines of the list share (m4): it has no list price.
        for spec, asked, retail, shares in ((story, ("m2",), {"m1": 0.29, "m2": 0.14}, {"m1": ["m2"]}), (story, ("m1",), {"m1": 0.29, "m2": 0.14}, {"m2": ["m1"]}),
                                            (self.invented(), ("m2",), {"m1": 2.0, "m2": 3.0}, {"m1": ["m2"], "m4": ["m2"]}), (self.invented(), ("m4", "m3"), {"m1": 2.0, "m2": 3.0}, {"m1": ["m4"], "m2": ["m4"]})):
            box, trace, answer = self.real(spec), [], evals.handler_of(spec)[0]
            for name, arguments in (("cost_meters", {"handle": "r1"}), *(("price_alternatives", {"meter": meter}) for meter in asked)):
                ask(box, name, **arguments)
                trace.append({"name": name, "arguments": arguments, "result": answer(name, arguments)})
            market = evals._market(spec, pricing, evals.shown_bill(trace), {})
            with self.subTest(row=spec["id"], asked=asked):
                self.assertEqual(box.retail, retail, "the toolbox registers the list price of the line of every meter that shares the list of one that was asked for")
                self.assertEqual((market.offers, market.retail), (box.offers, box.retail), "the replay: the same meters, the same price handles and the same list prices")
                self.assertEqual((market.asked, market.shares), (frozenset(asked), shares), "and it says which meters the tool was asked about, and which meters were offered through the list of which")
        self.assertEqual(sorted(box.offers), ["m1", "m2", "m3", "m4"], "the meter in another unit is there because it was asked for, and not because it shares a list")
        self.assertEqual(evals._market(story, pricing, None, {}).asked, frozenset(("m1", "m2")), "without a replay every meter counts as asked about")

    def test_a_meter_that_has_another_product_than_the_one_asked_about_is_offered_nothing_by_the_toolbox_and_by_the_replay(self):
        # Two meters of one resource in one unit whose product words differ: the list of a product is not the list of the other, even in the same unit (the lines of the list belong to the first meter's product)
        spec = {**self.invented(), "meters": [self.item("Big Units", 10, 2.0), {**self.item("Elite Units", 5, 2.0), "subcategory": "Premium Tier"}],
                "prices": [self.listed("Basic", "Big Units", 3.0), self.listed("Plus", "Elite Units", 4.0)], "resources": [{"h": "r1", "usd": 900.0, "total": 3, "sku": "Standard"}]}
        box, trace, answer = self.real(spec), [], evals.handler_of(spec)[0]
        for name, arguments in (("cost_meters", {"handle": "r1"}), ("price_alternatives", {"meter": "m1"})):
            ask(box, name, **arguments)
            trace.append({"name": name, "arguments": arguments, "result": answer(name, arguments)})
        market = evals._market(spec, pricing, evals.shown_bill(trace), {})
        self.assertEqual((sorted(box.meters), sorted(box.offers), box.retail), (["m1", "m2"], ["m1"], {"m1": 3.0}), "the toolbox registers the asked meter alone")
        self.assertEqual((market.offers, market.retail, market.shares), (box.offers, box.retail, {}), "and so does the replay")

    def test_a_meter_with_no_line_of_its_name_and_lines_that_disagree_say_none_and_several_in_the_real_tool_too_and_a_page_past_the_end_is_empty(self):
        spec = self.invented()
        box = self.real(spec)
        ask(box, "cost_meters", handle="r1")
        ask(box, "price_alternatives", meter="m1")  # the first read of the list gives the lines of the unit of the first meter their handles, as it does in a run
        for meter_handle, match in (("m3", "none"), ("m4", "several")):
            real, fake = ask(box, "price_alternatives", meter=meter_handle), self.fixture(spec, "price_alternatives", meter=meter_handle)
            self.assertEqual((real["match"], fake["match"], "current" in real, "current" in fake), (match, match, False, False))
        real, fake = ask(box, "price_alternatives", meter="m1", offset=4), self.fixture(spec, "price_alternatives", meter="m1", offset=4)
        self.assertEqual(real, fake)
        self.assertEqual((fake["rows"], fake["cols"], fake["returned"]), ([], ["price"], 0))
        self.assertEqual(ask(box, "price_alternatives", meter="m9"), {"error": "unknown-handle"})
        self.assertEqual(self.fixture(spec, "price_alternatives", meter="m9"), {"error": "unknown-handle"})

    def test_the_shipped_row_gives_a_list_that_the_real_reader_keeps_whole_and_prices_nothing_that_is_free(self):
        from cases import prices as app

        spec = ROWS[STORY_ROW]
        lines = [price_line(line["sku"], line["meter"], line["usd"], line["unit"], product="Azure Bastion", service="Azure Bastion") for line in spec["prices"]]
        estate = PricedEstate()
        estate.lines = lines
        client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None, jitter=lambda: 0.5)
        book = app.read(client, "Azure Bastion", "swedencentral", "Azure Bastion")
        self.assertEqual((book.complete, len(book.lines), sorted(line.meter for line in book.lines)), (True, len(spec["prices"]), sorted(line["meter"] for line in spec["prices"])), "the reader of the app keeps every line")
        self.assertTrue(all(line.usd > 0 and line.tiers == 1 for line in book.lines), "a price of nothing and a price with steps are no line of the real reader, and the row gives none")


class TheChecksOfAFinding(unittest.TestCase):
    """What the grader of tools/foundry-evals.py repeats of the checks that the investigation makes of each finding before it asks about a setting (cases/investigate.py parse_finding and _verify): the lists
    and the caps, and what is kept of each finding of an answer, each held to the app's own code on the same answers, so that a rule of the app that changes fails here until the tool follows it."""

    ROW = {"id": "invented", "kind": "clean", "type": WIDGET, "metric": "Day Metric", "service": "Example Service", "expect": {"propose": [], "never": []},
           "resources": [{"h": "r1", "usd": 99.0, "total": 0}, {"h": "r2", "usd": 98.0, "total": 3}, {"h": "r3", "usd": 97.0, "total": 0, "days": 19}, {"h": "r4", "usd": 96.0, "total": None},
                         {"h": "r5", "usd": 95.0, "total": 0, "days": 20}]}

    @staticmethod
    def app_reads(row, findings):
        """Every finding that the app reads, by its own parse_finding and _verify, on a toolbox that shows what the tools of the fixture could show: the metric of the row and the cost of each resource on
        either basis."""
        evidence = {}
        for resource in evals._resources(row):
            handle, cost = resource["h"], evals.evidence_total(row, resource["h"], "Cost actual USD 30d")[1]
            evidence[handle] = {"metrics": {row["metric"]: {"total": resource["total"], "max": resource["total"], "average": resource["total"], "days_with_data": resource["days"], "days": 30, "unit": None,
                                                           "totals": [resource["total"]]},
                                            **{f"Cost {basis} USD 30d": {"total": cost, "max": None, "average": None, "days_with_data": None, "days": 30, "unit": None, "totals": [cost]}
                                               for basis in ("actual", "amortized")}}}
        box = types.SimpleNamespace(handles=dict.fromkeys(evals.known_handles(row)), evidence=evidence)
        taken, holders, read = set(), {}, []
        for number, raw in enumerate(findings[:agents.MAX_FINDINGS], 1):
            finding, handles, entries = investigate.parse_finding(number, raw)
            if finding.reason is None:
                investigate._verify(finding, handles, entries, box, taken, holders)
            read.append(finding)
        return read

    @classmethod
    def app_keeps(cls, row, findings):
        return [(finding.basis, finding.proposal, finding.confidence, finding.handles) for finding in cls.app_reads(row, findings) if finding.reason is None and finding.handles]

    def test_the_lists_and_the_caps_that_the_tool_repeats_are_the_apps_own(self):
        self.assertEqual((evals.BASES, evals.PROPOSALS, evals.MAX_HANDLES, evals.MAX_FINDINGS, evals.MEASURED_DAYS), (agents.BASES, agents.PROPOSALS, agents.MAX_HANDLES, agents.MAX_FINDINGS, brief.MEASURED_DAYS))

    @staticmethod
    def bare(function):
        """The syntax tree of a function without its docstring: the tool's copy is written with a shorter one."""
        tree = ast.parse(inspect.getsource(function))
        body = tree.body[0].body
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
            tree.body[0].body = body[1:]
        return ast.dump(tree)

    def test_the_check_that_the_tool_repeats_of_a_word_of_a_meter_is_the_toolboxs_own(self):
        self.assertEqual((evals.METER_FORM.pattern, evals.VERSIONED.pattern), (tb.METER_FORM.pattern, tb.VERSIONED.pattern))
        for name in ("_titled", "meter_word"):
            self.assertEqual(self.bare(getattr(evals, name)), self.bare(getattr(tb, name)), f"{name} in tools/foundry-evals.py is the toolbox's own, written again for the Operator's volume: change both")
        for word in ("Standard Gateway", "Standard Additional Gateway", "1 Hour", "100 GB/Month", "lower case words", "Azure Bastion", "v2 Pro", "A - B", "x" * 64, "x" * 65, "", " ", "a;b", "Two  spaces",
                     "(Preview) Unit", "Unit-Hours", "An of the", None, 5, ["Unit"]):
            self.assertEqual(evals.meter_word(word), tb.meter_word(word), repr(word))

    def test_the_words_and_the_numbers_are_read_as_the_app_reads_them(self):
        for value in ("change", " Change ", "CHANGE\n", "banana", "", None, 5, True, ["change"], "no-usage", "no usage"):
            self.assertEqual(evals._word(value, evals.PROPOSALS), investigate._word(value, agents.PROPOSALS), repr(value))
            self.assertEqual(evals._word(value, evals.BASES), investigate._word(value, agents.BASES), repr(value))
        for value in (0, 1, 0.5, -1, 85, True, False, None, "0.5", float("nan"), float("inf"), -float("inf"), 10 ** 400, [1], {"a": 1}):
            self.assertEqual(evals._finite(value), investigate._number(value), repr(value))

    def answers(self):
        """Answers of the Investigator that exercise every rule of the checks: what the app keeps of each is compared with what the tool keeps."""
        def finding(handles, *cited, basis="no-usage", proposal="delete", confidence=0.9, **more):
            return {"handles": handles, "basis": basis, "proposal": proposal, "confidence": confidence, "metric_evidence": [{"handle": h, "metric": m, "total": t} for h, m, t in cited], **more}

        zero, metric = ("r1", "Day Metric", 0), "Day Metric"
        cost = evals.evidence_total(self.ROW, "r1", "Cost actual USD 30d")[1]
        return [
            [finding(["r1"], zero)], [finding(["r1", "r2"], zero, ("r2", metric, 0))], [finding(["r2"], ("r2", metric, 3))], [finding(["r3"], ("r3", metric, 0))], [finding(["r4"], ("r4", metric, None))],
            [finding(["r5"], ("r5", metric, 0))], [finding(["r1"], zero, ("r1", "Cost actual USD 30d", cost))], [finding(["r1"], ("r1", " day metric ", 0))], [finding(["r1"], ("r1", "Other", 0))],
            [finding(["r1"], ("r1", metric, "0"))], [finding(["r1"], ("r1", metric, False))], [finding(["r1"], ("r1", metric, 0.0000001))], [finding(["r2"], ("r2", metric, 3.0000001))], [finding(["r1"])],
            [finding(["r1"], zero, ("r2", metric, 3))], [finding(["r1"], metric_evidence=[{"handle": "r1", "metric": metric, "total": 0}, "not an entry", {"handle": ["r1"], "metric": metric, "total": 0},
                                                                                           {"handle": "r1", "metric": 5, "total": 0}])], [finding(["r1"], metric_evidence="nothing")],
            [finding(["r1"], basis=" No-Usage ", proposal=" Delete ")], [finding(["r1"], zero, basis="oversized", proposal="change")], [finding(["r1", "r2"], basis="oversized", proposal="change")],
            [finding(["r1"], zero, basis="banana")], [finding(["r1"], zero, proposal="banana")], [finding(["r1"], zero, confidence="high")], [finding(["r1"], zero, confidence=True)],
            [finding(["r1"], zero, confidence=float("nan"))], [finding(["r1"], zero, confidence=85)], [finding(["r1"], zero, confidence=-1)], [finding(["r1"], zero, confidence=0.123456)],
            [{"handles": ["r1"], "proposal": "delete", "metric_evidence": []}], ["r1", 5, None], [finding([])], [finding("r1")], [finding(["r9"], zero)], [finding(["r9", "r1"], zero)],
            [finding(["r1", "r1", "r1"], zero)], [finding(["r1", 5, None, "r1"], zero)], [finding([f"x{n}" for n in range(59)] + ["r1"], zero)], [finding([f"x{n}" for n in range(60)] + ["r1"], zero)],
            [finding(["r1"], zero, confidence=0.8), finding(["r1"], zero, confidence=0.8, proposal="investigate")], [finding(["r1"], zero, confidence=0.8), finding(["r1"], zero, confidence=0.9, proposal="investigate")],
            [finding(["r1"], zero, confidence=0.9), finding(["r1"], zero, confidence=0.8, proposal="investigate")], [finding(["r1"], zero, confidence=85), finding(["r1"], zero, confidence=0.1, proposal="investigate")],
            [finding(["r1"], zero, confidence=0.8), finding(["r1", "r5"], zero, ("r5", metric, 0), confidence=0.9, proposal="investigate")],
            [finding(["r1", "r5"], zero, ("r5", metric, 0)), finding(["r5"], ("r5", metric, 0), confidence=0.95, proposal="investigate")],
            [finding(["r1", "r5"], zero, ("r5", metric, 0)), finding(["r2"], ("r2", metric, 3)), finding(["r1"], zero, basis="oversized", confidence=0.95, proposal="investigate")],
            [finding(["r2"], basis="duplicate")] * 7 + [finding(["r1"], zero)], [finding(["r2"], basis="duplicate")] * 8 + [finding(["r1"], zero)],
            [finding(["r1"], zero, ("r1", "cost actual usd 30d", cost))], [finding(["r1"], zero, ("r1", "  COST ACTUAL USD 30D ", cost))], [finding(["r1"], zero, ("r1", "cost amortized usd 30d", cost))],
            [finding(["r1"], zero, ("r1", "Cost  actual USD 30d", cost))], [finding(["r1"], ("r1", " DAY METRIC ", 0), ("r1", "cost actual usd 30d", cost))], [finding([5, None], zero)],
            [finding(["r1"], zero, ("r1", "Cost actual USD 30d", cost), basis="oversized", proposal="change")], [finding(["r2"], ("r2", "cost actual usd 30d", 3), ("r2", "day metric", 3))],
        ]

    def test_what_is_kept_of_the_findings_of_an_answer_is_what_the_app_keeps(self):
        answers = self.answers()
        for number, answer in enumerate(answers):
            with self.subTest(answer=number):
                kept = [(f["basis"], f["proposal"], f["confidence"], f["handles"]) for f in evals._kept_findings(self.ROW, answer)]
                self.assertEqual(kept, self.app_keeps(self.ROW, answer), json.dumps(answer)[:300])
        self.assertTrue(any(self.app_keeps(self.ROW, answer) for answer in answers) and not all(self.app_keeps(self.ROW, answer) for answer in answers), "the answers keep some findings and drop others")

    def test_the_reason_for_dropping_a_finding_whole_is_the_apps_own_words(self):
        reasons = set()
        for number, answer in enumerate(self.answers()):
            with self.subTest(answer=number):
                read = evals._read_findings(self.ROW, answer)
                app = self.app_reads(self.ROW, answer)
                self.assertEqual([(f["number"], f["reason"]) for f in read], [(f.number, f.reason) for f in app], json.dumps(answer)[:300])
                reasons |= {f.reason for f in app if f.reason}
        for words in ("it is not an object", "its basis or its proposal is not on the list", "its confidence is not a number", "it lists no handles", "no resource of it is left: 1 that no tool showed",
                      "no resource of it is left: 1 without a cited measurement that matches the tools and shows no usage on enough days", "no resource of it is left: 1 that an earlier finding has",
                      "no resource of it is left: 1 that a later finding, which is surer of them, has", "no resource of it is left: it lists none that the tools showed"):
            self.assertIn(words, reasons, "the answers make the app drop a finding for each of its reasons")


if __name__ == "__main__":
    unittest.main()
