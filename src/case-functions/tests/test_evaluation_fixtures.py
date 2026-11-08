"""The invented fixtures of the evaluations answer every tool of the toolbox in the shape of the real tool.

The fixtures (evaluation/cases.jsonl, answered by tools/foundry-evals.py) are a copy of what the tools show, so a change of a tool is a change that the copy does not know. Here the real toolbox
runs on the fake estates of its own tests and the fixtures answer the same call: the two answers must have the same keys, the same columns and the same kinds of value, apart from what is
declared here to come and go with the data. A tool that is changed or added fails here until `answers_of` in tools/foundry-evals.py follows it. Every name, id and number is INVENTED."""
import datetime as dt
import importlib.util
import json
import re
import sys
import unittest

from support import REPO_ROOT
from cases import deeper, toolbox as tb
from deep_estate import ACCOUNT, AI, COLLECTION, MACHINE, RULES, SUB, VM, WORKSPACE, WS, deep, deployment
from test_toolbox import DISK, Estate, ask, point, row, standard, toolbox

METRIC = "Processed Prompt Tokens"
SKIPPED = {"rows", "cols", "same", "properties", "cost_by_service"}  # the cells of a table, and keys that are the data: the tests of the columns and of the cells look at them
WORKSPACE_ROW, ACCOUNT_ROW, MACHINE_ROW, DISK_ROW = "workspaces-one-used-one-empty", "ai-account-with-two-deployments", "busy-machine-under-a-savings-plan", "idle-and-busy-disks"


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
        measure = ask(box, "measure", type=VM, metric="Network In Total")
        fake = self.fixture("unknown-metric-state", "measure", type="microsoft.network/privateendpoints", metric="PEBytesIn")
        self.same_shape(measure, fake)
        self.assertEqual((measure["failed"], fake["failed"], measure["rows"], fake["rows"]), (["r1", "r2"], ["r1", "r2", "r3"], [], []))

    def test_the_cost_lines_the_advice_and_the_paid_features(self):
        self.same_shape(ask(self.box, "cost_lines", limit=3), self.fixture(DISK_ROW, "cost_lines", limit=3))
        self.same_shape(ask(self.box, "advisor_items"), self.fixture(DISK_ROW, "advisor_items"))
        self.same_shape(ask(self.box, "paid_features"), self.fixture(DISK_ROW, "paid_features"))

    def test_an_estate_with_nothing_in_it(self):
        box = toolbox(Estate())
        metric = ROWS["empty-estate"]["metric"]
        for tool, arguments in (("estate_overview", {}), ("list_resources", {"type": DISK}), ("metric_names", {"type": DISK}), ("metric_summary", {"handles": ["r1"], "metric": metric}),
                                ("measure", {"type": DISK, "metric": metric}), ("cost_lines", {}), ("cost_lines", {"type": DISK}), ("advisor_items", {}), ("paid_features", {}),
                                ("describe", {"handle": "r1"}), ("cost_history", {"type": DISK})):
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

    VALID = {"type": "microsoft.compute/disks", "metric": "Percentage CPU", "handle": "r1", "handles": ["r1"], "dimension": "StatusCode", "table": "Heartbeat", "service": "Storage",
             "order_by": "cost", "basis": "actual", "days": 30, "limit": 5, "offset": 0}

    def test_what_every_tool_takes_is_what_the_toolbox_declares(self):
        self.assertEqual(set(evals.PARAMETERS), set(tb.TOOLS))
        for name, tool in tb.TOOLS.items():
            declared = evals.PARAMETERS[name]
            self.assertEqual(list(declared), [param.name for param in tool.params], name)
            for param in tool.params:
                kind, required, limits = declared[param.name]
                self.assertEqual((kind, required), ({"integer": "int", "handles": "list", "choice": "choice"}.get(param.kind, "text"), param.required), (name, param.name))
                if kind == "int":
                    self.assertEqual(limits, (param.low, param.high), (name, param.name))
                if kind == "choice":
                    self.assertEqual(limits, param.choices, (name, param.name))

    def test_a_call_that_does_not_pass_is_bad_arguments_for_the_tool_and_for_the_fixtures(self):
        bad = {"int": ["x", True, -1, 100001], "choice": ["nope", 3], "text": [5, ["r1"], ""], "list": ["r1", [], [7]]}
        for name, declared in evals.PARAMETERS.items():
            good = {param: self.VALID[param] for param in declared if declared[param][1]}
            cases = [{**good, "unknown": 1}] + [{**good, param: value} for param, (kind, required, limits) in declared.items() for value in bad[kind]
                                                 if not (kind == "int" and isinstance(value, int) and not isinstance(value, bool) and limits[0] <= value <= limits[1])]
            cases += [{key: value for key, value in good.items() if key != param} for param in good]
            for arguments in cases:
                real = ask(toolbox(deeper_estate()), name, **arguments)
                fake = self.fixture(WORKSPACE_ROW, name, **arguments)
                self.assertEqual((real, fake), ({"error": "bad-arguments"},) * 2, (name, arguments))

    def test_a_call_that_passes_is_answered_and_the_bounds_are_the_ones_of_the_toolbox(self):
        for name, declared in evals.PARAMETERS.items():
            good = {param: self.VALID[param] for param in declared if declared[param][1]}
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
        self.assertEqual((evals.READER_SOURCES, evals.CHILD_COLUMNS, evals.FIXED_FIELDS), (tb.READER_SOURCES, tb.CHILD_COLUMNS, tb.FIXED_FIELDS))
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


if __name__ == "__main__":
    unittest.main()
