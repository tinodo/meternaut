"""The reads of the deeper tools: what each one asks of Azure (path, API version, query, body, token), and what each one refuses to ask. Every id in it is INVENTED."""
import datetime as dt
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from support import SUBSCRIPTION, TOKEN
from cases import arm as arm_module
from cases.arm import Arm
from cases.http import Client, HttpError, Refused, allowed_calls
from cases.redact import Redactor
from test_arm import arm_with
from test_http import Script, ok

GROUP = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-demo"
WS = f"{GROUP}/providers/Microsoft.OperationalInsights/workspaces/ws-demo"
AI = f"{GROUP}/providers/Microsoft.CognitiveServices/accounts/ai-demo"
VM = f"{GROUP}/providers/Microsoft.Compute/virtualMachines/vm-demo"
CUSTOMER = "0a1b2c3d-1111-2222-3333-444455556666"
START = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc)
FIRST, LAST = dt.date(2026, 10, 5), dt.date(2026, 11, 3)


def only(script):
    ((method, url, headers, data, timeout),) = script.calls
    return method, url, headers, (json.loads(data) if data else None), timeout


class TheWorkspace(unittest.TestCase):
    def test_the_settings_are_one_get_at_the_documented_version(self):
        arm, script = arm_with(ok({"properties": {"customerId": CUSTOMER}}))
        self.assertEqual(arm.workspace(WS), {"properties": {"customerId": CUSTOMER}})
        method, url, headers, _, _ = only(script)
        self.assertEqual((method, url), ("GET", f"https://management.azure.com{WS}?api-version={arm_module.LOG_ANALYTICS_API}"))
        self.assertEqual(arm_module.LOG_ANALYTICS_API, "2026-03-01")

    def test_only_the_id_of_a_workspace_is_asked_for(self):
        arm, script = arm_with(ok({"properties": {}}))
        for bad in ("", WS + "/tables", f"{GROUP}/providers/Microsoft.Compute/virtualMachines/vm-demo", f"{GROUP}/providers/Microsoft.OperationalInsights/workspaces/../x", "x",
                    f"{WS}?api-version=1", f"{GROUP}/providers/Microsoft.OperationalInsights/workspaces/ws-demo/../../x"):
            for read in (arm.workspace, arm.workspace_tables, arm.saved_searches, arm.sentinel_rules):
                with self.assertRaises(HttpError, msg=(read.__name__, bad)):
                    read(bad)
        self.assertEqual(script.calls, [])

    def test_an_answer_without_properties_is_an_error(self):
        for answer in ({}, [], {"properties": 5}):
            arm, _ = arm_with(ok(answer))
            with self.assertRaises(HttpError):
                arm.workspace(WS)

    def test_the_tables_are_cut_to_what_the_tools_use_and_every_page_is_read(self):
        item = {"name": "Heartbeat", "properties": {"plan": "Analytics", "retentionInDays": 30, "totalRetentionInDays": 90, "schema": {"tableType": "Microsoft", "tableSubType": "Any",
                                                                                                                                       "columns": [{"name": "x"}] * 50, "source": "x"},
                                                    "retentionInDaysAsDefault": True, "ignored": "x", "provisioningState": "Succeeded"}}
        link = f"https://management.azure.com{WS}/tables?api-version=2026-03-01&$skiptoken=abc"
        arm, script = arm_with(ok({"value": [item], "nextLink": link}), ok({"value": [{"name": "Perf", "properties": {}}, "x"]}))
        found = arm.workspace_tables(WS)
        self.assertEqual(found[0], {"name": "Heartbeat", "type": "Microsoft", "subType": "Any", "plan": "Analytics", "retentionInDays": 30, "totalRetentionInDays": 90,
                                    "retentionInDaysAsDefault": True, "totalRetentionInDaysAsDefault": None, "protectionLevel": None, "provisioningState": "Succeeded"})
        self.assertEqual(found[1]["name"], "Perf")
        self.assertEqual(len(found), 2)
        self.assertEqual([call[1] for call in script.calls], [f"https://management.azure.com{WS}/tables?api-version=2026-03-01", link])
        self.assertNotIn("columns", json.dumps(found))

    def test_a_next_page_that_leads_anywhere_else_is_refused(self):
        arm, script = arm_with(ok({"value": [], "nextLink": "https://evil.example/x"}))
        with self.assertRaises(HttpError):
            arm.saved_searches(WS)
        self.assertEqual(len(script.calls), 1)

    def test_the_saved_searches_and_the_rules_of_sentinel_are_gets_of_their_own_paths(self):
        arm, script = arm_with(ok({"value": [{"properties": {"query": "A"}}]}))
        self.assertEqual(arm.saved_searches(WS), [{"properties": {"query": "A"}}])
        self.assertEqual(script.calls[0][1], f"https://management.azure.com{WS}/savedSearches?api-version=2026-03-01")
        arm, script = arm_with(ok({"value": []}))
        arm.sentinel_rules(WS)
        self.assertEqual(script.calls[0][1], f"https://management.azure.com{WS}/providers/Microsoft.SecurityInsights/alertRules?api-version={arm_module.SENTINEL_API}")
        self.assertEqual(arm_module.SENTINEL_API, "2025-09-01")

    def test_the_workbooks_of_a_subscription_come_with_their_content(self):
        arm, script = arm_with(ok({"value": []}))
        arm.workbooks(SUBSCRIPTION)
        url = urlsplit(script.calls[0][1])
        self.assertEqual(url.path, f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Insights/workbooks")
        self.assertEqual(parse_qs(url.query), {"category": ["workbook"], "canFetchContent": ["true"], "api-version": [arm_module.WORKBOOKS_API]})
        self.assertEqual(arm_module.WORKBOOKS_API, "2023-06-01")


class TheQueryApi(unittest.TestCase):
    ANSWER = {"tables": [{"name": "PrimaryResult", "columns": [{"name": "Day"}, {"name": "Total"}], "rows": [["2026-10-05T00:00:00Z", 5], ["2026-10-06T00:00:00Z", 6], "x"]}]}

    def test_a_query_is_one_post_to_the_host_of_the_api_with_the_token_of_its_own_audience(self):
        asked = []
        script = Script(ok(self.ANSWER))
        client = Client(allowed_calls(), Redactor(), transport=script, sleep=lambda s: None, jitter=lambda: 0.5)
        arm = Arm(client, lambda resource: asked.append(resource) or TOKEN)
        rows = arm.log_query(CUSTOMER, "Usage | take 1", START, END, timeout=30)
        self.assertEqual(rows, [{"Day": "2026-10-05T00:00:00Z", "Total": 5}, {"Day": "2026-10-06T00:00:00Z", "Total": 6}])
        method, url, headers, body, timeout = only(script)
        self.assertEqual((method, url), ("POST", f"https://api.loganalytics.azure.com/v1/workspaces/{CUSTOMER}/query"))
        self.assertEqual(body, {"query": "Usage | take 1", "timespan": "2026-10-05T00:00:00Z/2026-11-04T00:00:00Z"})
        self.assertEqual((asked, timeout), (["https://api.loganalytics.io"], 30))
        self.assertEqual(arm_module.LOG_ANALYTICS_RESOURCE, "https://api.loganalytics.io")

    def test_only_the_id_of_a_workspace_and_a_query_of_a_length_are_sent(self):
        arm, script = arm_with(ok(self.ANSWER))
        for workspace, query in (("DefaultWorkspace", "x"), (CUSTOMER + "/query", "x"), (CUSTOMER, ""), (CUSTOMER, "   "), (CUSTOMER, "x" * 8001), (WS, "x")):
            with self.assertRaises(HttpError, msg=(workspace, query[:10])):
                arm.log_query(workspace, query, START, END)
        self.assertEqual(script.calls, [])

    def test_a_partial_answer_is_an_error_and_so_is_one_that_is_not_a_table(self):
        partial = dict(self.ANSWER, error={"code": "PartialError", "message": "x"})
        for answer in (partial, {}, {"tables": []}, {"tables": ["x"]}, []):
            arm, _ = arm_with(ok(answer))
            with self.assertRaises(HttpError, msg=str(answer)[:60]):
                arm.log_query(CUSTOMER, "x", START, END)

    def test_a_slow_query_is_asked_again_once_at_most_and_a_network_error_is_not_retried(self):
        arm, script = arm_with((503, {}, b"{}"), ok(self.ANSWER))
        self.assertEqual(len(arm.log_query(CUSTOMER, "x", START, END)), 2)
        self.assertEqual(len(script.calls), 2)
        arm, script = arm_with(TimeoutError("slow"))
        with self.assertRaises(HttpError):
            arm.log_query(CUSTOMER, "x", START, END)
        self.assertEqual(len(script.calls), 1)

    def test_the_call_that_the_list_does_not_have_is_refused(self):
        arm, script = arm_with(ok(self.ANSWER))
        for url in (f"https://api.loganalytics.io/v1/workspaces/{CUSTOMER}/query", f"https://api.loganalytics.azure.com/v1/workspaces/{CUSTOMER}/metadata"):
            with self.assertRaises(Refused):
                arm.client.request("POST", url, body={})
        self.assertEqual(script.calls, [])


class TheOthers(unittest.TestCase):
    def test_the_diagnostic_settings_of_a_resource(self):
        arm, script = arm_with(ok({"value": [{"properties": {}}]}))
        self.assertEqual(arm.diagnostic_settings(VM), [{"properties": {}}])
        self.assertEqual(script.calls[0][1], f"https://management.azure.com{VM}/providers/Microsoft.Insights/diagnosticSettings?api-version={arm_module.DIAGNOSTIC_API}")
        self.assertEqual(arm_module.DIAGNOSTIC_API, "2021-05-01-preview")
        with self.assertRaises(HttpError):
            arm.diagnostic_settings("x")

    def test_the_deployments_of_an_account_and_only_of_an_account(self):
        arm, script = arm_with(ok({"value": [{"name": "d1"}]}))
        self.assertEqual(arm.deployments(AI), [{"name": "d1"}])
        self.assertEqual(script.calls[0][1], f"https://management.azure.com{AI}/deployments?api-version={arm_module.DEPLOYMENTS_API}")
        self.assertEqual(arm_module.DEPLOYMENTS_API, "2026-09-01")
        for bad in (VM, AI + "/deployments/d1", f"{GROUP}/providers/Microsoft.CognitiveServices/accounts/../x", ""):
            with self.assertRaises(HttpError, msg=bad):
                arm.deployments(bad)
        self.assertEqual(len(script.calls), 1)

    def test_the_activity_log_is_asked_for_one_resource_or_one_group_with_a_filter_of_the_documented_kind(self):
        event = {"eventTimestamp": "2026-11-01T00:00:00Z", "caller": "x"}
        arm, script = arm_with(ok({"value": [event]}))
        events, complete = arm.activity_events(SUBSCRIPTION, START, END, resource_id=VM)
        self.assertEqual((events, complete), ([event], True))
        url = urlsplit(script.calls[0][1])
        self.assertEqual(url.path, f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Insights/eventtypes/management/values")
        query = parse_qs(url.query)
        self.assertEqual(query["api-version"], [arm_module.ACTIVITY_API])
        self.assertEqual(query["$filter"], [f"eventTimestamp ge '2026-10-05T00:00:00Z' and eventTimestamp le '2026-11-04T00:00:00Z' and resourceUri eq '{VM}'"])
        arm, script = arm_with(ok({"value": []}))
        arm.activity_events(SUBSCRIPTION, START, END, group="rg-demo")
        self.assertIn("and resourceGroupName eq 'rg-demo'", parse_qs(urlsplit(script.calls[0][1]).query)["$filter"][0])
        self.assertEqual(arm_module.ACTIVITY_API, "2015-04-01")

    def test_the_activity_log_says_when_a_page_was_left_unread_and_refuses_what_could_put_text_in_the_filter(self):
        link = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Insights/eventtypes/management/values?api-version=2015-04-01&$skiptoken=abc"
        arm, script = arm_with(ok({"value": [{"a": 1}], "nextLink": link}))
        events, complete = arm.activity_events(SUBSCRIPTION, START, END, resource_id=VM, max_pages=2)
        self.assertEqual((len(events), complete, len(script.calls)), (2, False, 2))
        arm, script = arm_with(ok({"value": []}))
        for kwargs in ({"resource_id": VM + "' or true or '"}, {"resource_id": "/subscriptions/99999999-8888-7777-6666-555555555555/resourceGroups/rg/providers/A.B/c/d"}, {"group": "rg' or '1"},
                       {"group": ""}):
            with self.assertRaises(HttpError, msg=kwargs):
                arm.activity_events(SUBSCRIPTION, START, END, **kwargs)
        self.assertEqual(script.calls, [])

    def test_the_recommendations_of_the_platform_are_reads_of_one_subscription_with_a_filter(self):
        arm, script = arm_with(ok({"value": [{"properties": {}}]}))
        arm.benefit_recommendations(SUBSCRIPTION, "P3Y")
        url = urlsplit(script.calls[0][1])
        self.assertEqual(url.path, f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/benefitRecommendations")
        self.assertEqual(parse_qs(url.query), {"api-version": [arm_module.BENEFITS_API], "$filter": ["properties/scope eq 'Single' AND properties/lookBackPeriod eq 'Last30Days' AND properties/term eq 'P3Y'"]})
        self.assertEqual(script.calls[0][2].get("ClientType"), "Meternaut")
        self.assertEqual(arm_module.BENEFITS_API, "2026-06-01")
        for bad in ("P2Y", "", "p1y", "P1Y' or '1"):
            with self.assertRaises(HttpError, msg=bad):
                arm.benefit_recommendations(SUBSCRIPTION, bad)
        arm, script = arm_with(ok({"value": []}))
        arm.reservation_recommendations(SUBSCRIPTION)
        url = urlsplit(script.calls[0][1])
        self.assertEqual(url.path, f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Consumption/reservationRecommendations")
        self.assertEqual(parse_qs(url.query), {"api-version": [arm_module.RESERVATIONS_API], "$filter": ["properties/scope eq 'Single'"]})
        self.assertEqual(arm_module.RESERVATIONS_API, "2024-08-01")


class TheCostByDay(unittest.TestCase):
    def test_a_daily_read_is_a_query_with_the_granularity_daily_and_the_day_as_a_number(self):
        columns = [{"name": "Cost"}, {"name": "UsageDate"}, {"name": "ResourceId"}, {"name": "Currency"}]
        arm, script = arm_with(ok({"properties": {"columns": columns, "rows": [[1.5, 20261020, VM.upper(), "usd"], [2.0, 20261021, VM, "USD"]]}}))
        rows = arm.cost_days(SUBSCRIPTION, FIRST, LAST, amortized=True, where=("ResourceId", (VM,)))
        self.assertEqual(rows, [(dt.date(2026, 10, 20), VM.lower(), 1.5, "USD"), (dt.date(2026, 10, 21), VM.lower(), 2.0, "USD")])
        _, url, headers, body, _ = only(script)
        self.assertEqual(headers.get("ClientType"), "Meternaut")
        self.assertEqual(body["type"], "AmortizedCost")
        self.assertEqual(body["dataset"]["granularity"], "Daily")
        self.assertEqual(body["dataset"]["grouping"], [{"type": "Dimension", "name": "ResourceId"}])  # the day is a column of the answer and no grouping
        self.assertEqual(body["dataset"]["filter"], {"dimensions": {"name": "ResourceId", "operator": "In", "values": [VM]}})
        self.assertIn("api-version=2023-11-01", url)

    def test_a_day_that_is_not_a_day_is_an_error(self):
        columns = [{"name": "Cost"}, {"name": "UsageDate"}, {"name": "ResourceId"}]
        arm, _ = arm_with(ok({"properties": {"columns": columns, "rows": [[1.0, "someday", VM]]}}))
        with self.assertRaises(HttpError):
            arm.cost_days(SUBSCRIPTION, FIRST, LAST)

    def test_how_the_cost_was_paid_for_is_an_amortized_read_grouped_by_two_dimensions(self):
        columns = [{"name": "Cost"}, {"name": "PricingModel"}, {"name": "ChargeType"}, {"name": "Currency"}]
        arm, script = arm_with(ok({"properties": {"columns": columns, "rows": [[10.0, "OnDemand", "Usage", "USD"], [5.0, "SavingsPlan", "Purchase", "USD"]]}}))
        self.assertEqual(arm.cost_models(SUBSCRIPTION, FIRST, LAST), [("OnDemand", "Usage", 10.0, "USD"), ("SavingsPlan", "Purchase", 5.0, "USD")])
        body = only(script)[3]
        self.assertEqual((body["type"], body["dataset"]["granularity"]), ("AmortizedCost", "None"))
        self.assertEqual([g["name"] for g in body["dataset"]["grouping"]], ["PricingModel", "ChargeType"])


class TheSplit(unittest.TestCase):
    SERIES = {"value": [{"unit": "Count", "errorCode": "Success", "timeseries": [
        {"metadatavalues": [{"name": {"value": "ModelDeploymentName"}, "value": "d1"}], "data": [{"timeStamp": "2026-10-05T00:00:00Z", "total": 5.0, "maximum": 3.0, "average": 2.0}]},
        {"metadatavalues": [{"name": {"value": "ModelDeploymentName"}, "value": "d2"}], "data": []}, {"metadatavalues": [], "data": [{"timeStamp": "2026-10-05T00:00:00Z", "total": 1.0}]}, "x"]}]}

    def test_a_metric_split_by_a_dimension_asks_for_every_value_of_it_and_a_number_of_them(self):
        arm, script = arm_with(ok(self.SERIES))
        unit, series = arm.metrics_split(AI, "Processed Prompt Tokens", "ModelDeploymentName", START, END, top=7)
        self.assertEqual(unit, "Count")
        self.assertEqual([(value, len(points)) for value, points in series], [("d1", 1), ("d2", 0), ("", 1)])
        self.assertEqual((series[0][1][0].total, series[0][1][0].maximum, series[0][1][0].average), (5.0, 3.0, 2.0))
        query = parse_qs(urlsplit(script.calls[0][1]).query)
        self.assertEqual((query["$filter"], query["top"], query["metricnames"], query["interval"], query["aggregation"]),
                         (["ModelDeploymentName eq '*'"], ["7"], ["Processed Prompt Tokens"], ["P1D"], ["Total,Maximum,Average"]))
        self.assertEqual(query["timespan"], ["2026-10-05T00:00:00Z/2026-11-04T00:00:00Z"])

    def test_a_dimension_or_a_metric_that_is_not_a_plain_name_is_refused(self):
        arm, script = arm_with(ok(self.SERIES))
        for metric, dimension in (("a,b", "Region"), ("", "Region"), ("x" * 101, "Region"), ("Requests", "Region' or '1"), ("Requests", ""), ("Requests", "1Region"), ("Requests", "a b")):
            with self.assertRaises(HttpError, msg=(metric, dimension)):
                arm.metrics_split(AI, metric, dimension, START, END)
        self.assertEqual(script.calls, [])

    def test_a_metric_that_could_not_be_read_is_an_error_and_one_that_is_missing_has_no_series(self):
        arm, _ = arm_with(ok({"value": [{"unit": "Count", "errorCode": "InvalidSomething", "timeseries": []}]}))
        with self.assertRaises(HttpError):
            arm.metrics_split(AI, "Requests", "Region", START, END)
        arm, _ = arm_with(ok({"value": []}))
        self.assertEqual(arm.metrics_split(AI, "Requests", "Region", START, END), ("", []))
        for answer in ({}, {"value": "x"}, {"value": [{"errorCode": "Success", "timeseries": "x"}]}):
            arm, _ = arm_with(ok(answer))
            with self.assertRaises(HttpError, msg=str(answer)):
                arm.metrics_split(AI, "Requests", "Region", START, END)


if __name__ == "__main__":
    unittest.main()
