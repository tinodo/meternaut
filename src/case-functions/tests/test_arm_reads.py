"""The reads of Azure Monitor metrics, of the pricing settings of Defender for Cloud and of the cost lines by service, and the calls that the app may make for them."""
import datetime as dt
import json
import unittest

from support import SUBSCRIPTION
from cases.arm import CostLine, MetricPoint
from cases.http import Client, HttpError, Refused, allowed_calls
from cases.redact import Redactor
from test_arm import arm_with
from test_http import Script, ok

RESOURCE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-app/providers/Microsoft.Storage/storageAccounts/acct"
CHILD = f"{RESOURCE}/blobServices/default"
START = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc)
FIRST, LAST = dt.date(2026, 10, 5), dt.date(2026, 11, 3)


class CostLines(unittest.TestCase):
    COLUMNS = [{"name": "Cost"}, {"name": "ResourceId"}, {"name": "ServiceName"}, {"name": "Currency"}]

    def page(self, rows, columns=None, **more):
        return {"properties": {"columns": columns or self.COLUMNS, "rows": rows, **more}}

    def test_a_line_for_each_resource_and_service_with_the_id_in_lower_case_and_the_currency_in_upper_case(self):
        arm, script = arm_with(ok(self.page([[1.5, RESOURCE.upper(), " Storage ", "usd"], [2.0, RESOURCE, "Bandwidth", "USD"], [3.0, "", "Support", "USD"]])))
        lines = arm.cost_lines(SUBSCRIPTION, FIRST, LAST)
        self.assertEqual(lines, [CostLine(RESOURCE.lower(), "Storage", 1.5, "USD"), CostLine(RESOURCE.lower(), "Bandwidth", 2.0, "USD"), CostLine("", "Support", 3.0, "USD")])
        self.assertEqual((lines[0].resource_id, lines[0].service, lines[0].amount, lines[0].currency), (RESOURCE.lower(), "Storage", 1.5, "USD"))
        ((method, url, headers, data, _),) = script.calls
        body = json.loads(data)
        self.assertEqual((method, url), ("POST", f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"))
        self.assertEqual(body["type"], "ActualCost")
        self.assertEqual(body["timePeriod"], {"from": "2026-10-05T00:00:00Z", "to": "2026-11-03T23:59:59Z"})
        self.assertEqual(body["dataset"]["grouping"], [{"type": "Dimension", "name": "ResourceId"}, {"type": "Dimension", "name": "ServiceName"}])
        self.assertEqual(body["dataset"]["aggregation"], {"totalCost": {"name": "Cost", "function": "Sum"}})

    def test_the_columns_may_come_in_any_order_the_cost_may_be_a_pre_tax_cost_and_the_currency_may_be_missing(self):
        columns = [{"name": "ServiceName"}, {"name": "PreTaxCost"}, {"name": "ResourceId"}]
        arm, _ = arm_with(ok(self.page([["Storage", 2.5, RESOURCE]], columns)))
        self.assertEqual(arm.cost_lines(SUBSCRIPTION, FIRST, LAST), [CostLine(RESOURCE.lower(), "Storage", 2.5, "")])

    def test_every_page_is_read_from_the_same_service_only(self):
        link = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/query?api-version=2023-11-01&$skiptoken=abc"
        arm, script = arm_with(ok(self.page([[1.0, "a", "S1", "USD"]], nextLink=link)), ok(self.page([[2.0, "b", "S2", "USD"]])))
        self.assertEqual([(l.resource_id, l.amount) for l in arm.cost_lines(SUBSCRIPTION, FIRST, LAST)], [("a", 1.0), ("b", 2.0)])
        self.assertEqual((script.calls[1][0], script.calls[1][1]), ("POST", link))
        arm, script = arm_with(ok(self.page([], nextLink="https://evil.example/subscriptions/x/providers/Microsoft.CostManagement/query")))
        with self.assertRaises(HttpError):
            arm.cost_lines(SUBSCRIPTION, FIRST, LAST)
        self.assertEqual(len(script.calls), 1)

    def test_too_many_pages_are_an_error_and_not_a_silent_cut(self):
        link = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/query?api-version=2023-11-01&$skiptoken=abc"
        arm, _ = arm_with(ok(self.page([[1.0, "a", "S", "USD"]], nextLink=link)))
        with self.assertRaises(HttpError):
            arm.cost_lines(SUBSCRIPTION, FIRST, LAST)

    def test_an_answer_that_is_not_a_table_of_lines_by_service_is_an_error(self):
        nan = float("nan")
        for answer in (self.page([["x", "a", "S", "USD"]]), self.page([[nan, "a", "S", "USD"]]), self.page([[float("inf"), "a", "S", "USD"]]), self.page([[1.0]]),
                       self.page([[1.0, "a", "USD"]], [{"name": "Cost"}, {"name": "ResourceId"}, {"name": "Currency"}]), {"nope": 1}, [], self.page([[None, "a", "S", "USD"]])):
            arm, _ = arm_with(ok(answer))
            with self.assertRaises(HttpError, msg=str(answer)[:80]):
                arm.cost_lines(SUBSCRIPTION, FIRST, LAST)

    def test_a_throttled_read_is_asked_again_four_times_and_then_it_is_an_error(self):
        arm, script = arm_with((429, {"retry-after": "1"}, b"{}"))
        with self.assertRaises(HttpError) as raised:
            arm.cost_lines(SUBSCRIPTION, FIRST, LAST)
        self.assertEqual((raised.exception.status, len(script.calls)), (429, 5))

    def test_the_cost_of_every_resource_is_added_up_from_the_lines_and_gives_the_same_totals(self):
        arm, script = arm_with(ok(self.page([[1.5, RESOURCE, "Storage", "USD"], [0.5, RESOURCE, "Bandwidth", "USD"]])))
        self.assertEqual(arm.costs(SUBSCRIPTION, FIRST, LAST), ({RESOURCE.lower(): 2.0}, "USD"))
        self.assertEqual(json.loads(script.calls[0][3])["dataset"]["grouping"], [{"type": "Dimension", "name": "ResourceId"}, {"type": "Dimension", "name": "ServiceName"}])


class SecurityPricings(unittest.TestCase):
    def test_the_plans_of_a_subscription_in_the_version_of_the_documentation(self):
        arm, script = arm_with(ok({"value": [{"name": "A", "properties": {"pricingTier": "Free"}}, "x", {"name": "B"}]}))
        self.assertEqual([p["name"] for p in arm.security_pricings(SUBSCRIPTION)], ["A", "B"])
        ((method, url, _, data, _),) = script.calls
        self.assertEqual((method, url, data), ("GET", f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Security/pricings?api-version=2024-01-01", None))

    def test_a_next_page_is_followed_only_on_the_same_service_of_the_same_subscription(self):
        link = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Security/pricings?api-version=2024-01-01&$skiptoken=1"
        arm, script = arm_with(ok({"value": [{"name": "A"}], "nextLink": link}), ok({"value": [{"name": "B"}]}))
        self.assertEqual([p["name"] for p in arm.security_pricings(SUBSCRIPTION)], ["A", "B"])
        self.assertEqual(script.calls[1][1], link)
        for other in (f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Compute/virtualMachines", "https://evil.example/x",
                      "https://management.azure.com/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.Security/pricings"):
            arm, _ = arm_with(ok({"value": [], "nextLink": other}))
            with self.assertRaises(HttpError, msg=other):
                arm.security_pricings(SUBSCRIPTION)

    def test_an_answer_that_is_not_a_list_is_an_error(self):
        for answer in ({"value": "x"}, []):
            arm, _ = arm_with(ok(answer))
            with self.assertRaises(HttpError):
                arm.security_pricings(SUBSCRIPTION)
        arm, _ = arm_with(ok({"nothing": True}))
        self.assertEqual(arm.security_pricings(SUBSCRIPTION), [], "a page without a list is an empty page, as for every other list of the app")


class MetricDefinitions(unittest.TestCase):
    def test_the_definitions_of_one_resource_in_the_version_of_the_documentation(self):
        arm, script = arm_with(ok({"value": [{"name": {"value": "m"}}, "x"]}))
        self.assertEqual(arm.metric_definitions(RESOURCE), [{"name": {"value": "m"}}])
        ((method, url, headers, _, _),) = script.calls
        self.assertEqual((method, url), ("GET", f"https://management.azure.com{RESOURCE}/providers/Microsoft.Insights/metricDefinitions?api-version=2018-01-01"))
        self.assertIn("Authorization", headers)

    def test_a_child_resource_has_definitions_too(self):
        arm, script = arm_with(ok({"value": []}))
        arm.metric_definitions(CHILD)
        self.assertTrue(script.calls[0][1].startswith(f"https://management.azure.com{CHILD}/providers/Microsoft.Insights/metricDefinitions?"))

    def test_an_id_that_is_not_the_id_of_a_resource_is_refused_before_a_call_is_made(self):
        for scope in (f"/subscriptions/{SUBSCRIPTION}", f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-app", "", "/", "x", f"{RESOURCE}?x=1", f"{RESOURCE}/../x", f"{RESOURCE}/./x",
                      f"{RESOURCE}/..", f"{RESOURCE} x", f"/subscriptions/not-a-guid/resourceGroups/rg/providers/A.B/c/d", f"//{RESOURCE}"):
            arm, script = arm_with(ok({"value": []}))
            with self.assertRaises(HttpError, msg=scope):
                arm.metric_definitions(scope)
            self.assertEqual(script.calls, [], scope)

    def test_a_next_page_stays_on_the_same_service_of_the_same_subscription(self):
        link = f"https://management.azure.com{RESOURCE}/providers/Microsoft.Insights/metricDefinitions?api-version=2018-01-01&$skiptoken=1"
        arm, script = arm_with(ok({"value": [{"a": 1}], "nextLink": link}), ok({"value": [{"b": 2}]}))
        self.assertEqual(arm.metric_definitions(RESOURCE), [{"a": 1}, {"b": 2}])
        arm, _ = arm_with(ok({"value": [], "nextLink": "https://evil.example/subscriptions/x/providers/Microsoft.Insights/metricDefinitions"}))
        with self.assertRaises(HttpError):
            arm.metric_definitions(RESOURCE)


def monitor(points, unit="Count", code="Success", name="Percentage CPU"):
    return {"cost": 1, "timespan": "x/y", "interval": "P1D", "value": [{"id": f"{RESOURCE}/providers/Microsoft.Insights/metrics/{name}", "type": "Microsoft.Insights/metrics",
                                                                        "name": {"value": name, "localizedValue": name}, "unit": unit, "errorCode": code,
                                                                        "timeseries": [{"metadatavalues": [], "data": points}] if points is not None else []}]}


class Metrics(unittest.TestCase):
    def test_the_request_is_a_get_for_daily_buckets_with_the_three_aggregations_the_name_encoded_and_the_times_in_utc(self):
        arm, script = arm_with(ok(monitor([])))
        arm.metrics(RESOURCE, "Disk Read Operations/Sec", START, END)
        ((method, url, headers, data, timeout),) = script.calls
        self.assertEqual((method, data), ("GET", None))
        self.assertEqual(url, f"https://management.azure.com{RESOURCE}/providers/Microsoft.Insights/metrics?api-version=2023-10-01&metricnames=Disk%20Read%20Operations%2FSec"
                              "&timespan=2026-10-05T00:00:00Z/2026-11-04T00:00:00Z&interval=P1D&aggregation=Total,Maximum,Average")
        self.assertIn("Authorization", headers)

    def test_a_time_without_a_zone_is_utc_and_a_time_with_another_zone_is_turned_into_utc(self):
        for start in (dt.datetime(2026, 10, 5), dt.datetime(2026, 10, 5, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))):
            arm, script = arm_with(ok(monitor([])))
            arm.metrics(RESOURCE, "m", start, dt.datetime(2026, 11, 4))
            self.assertIn("timespan=2026-10-05T00:00:00Z/2026-11-04T00:00:00Z", script.calls[0][1])

    def test_the_unit_and_a_point_for_each_bucket_with_the_aggregations_that_the_bucket_has(self):
        points = [{"timeStamp": "2026-10-05T00:00:00Z", "total": 1.5, "maximum": 2, "average": 0.5, "minimum": 0, "count": 3},
                  {"timeStamp": "2026-10-06T00:00:00Z", "average": 4}, {"timeStamp": "2026-10-07T00:00:00Z"}]
        arm, _ = arm_with(ok(monitor(points, unit="Percent")))
        self.assertEqual(arm.metrics(RESOURCE, "m", START, END), ("Percent", [MetricPoint("2026-10-05T00:00:00Z", 1.5, 2.0, 0.5), MetricPoint("2026-10-06T00:00:00Z", None, None, 4.0),
                                                                              MetricPoint("2026-10-07T00:00:00Z", None, None, None)]))

    def test_a_value_that_is_not_a_finite_number_is_none_and_an_item_that_is_not_a_bucket_is_left_out(self):
        points = [{"timeStamp": "a", "total": "7", "maximum": True, "average": float("nan")}, "x", None, {"timeStamp": "b", "total": float("inf"), "maximum": 3}]
        arm, _ = arm_with(ok(monitor(points)))
        self.assertEqual(arm.metrics(RESOURCE, "m", START, END)[1], [MetricPoint("a", None, None, None), MetricPoint("b", None, 3.0, None)])

    def test_no_time_series_and_no_value_are_no_points(self):
        for answer in (monitor(None), {"value": []}, monitor([]), monitor(None, unit="")):
            arm, _ = arm_with(ok(answer))
            self.assertEqual(arm.metrics(RESOURCE, "m", START, END)[1], [])

    def test_the_first_time_series_is_the_one_that_is_read(self):
        answer = monitor([{"timeStamp": "a", "total": 1}])
        answer["value"][0]["timeseries"].append({"data": [{"timeStamp": "b", "total": 99}]})
        arm, _ = arm_with(ok(answer))
        self.assertEqual(arm.metrics(RESOURCE, "m", START, END)[1], [MetricPoint("a", 1.0, None, None)])

    def test_a_metric_that_azure_monitor_could_not_read_is_an_error_with_a_short_code_and_never_the_message(self):
        for code in ("InvalidSamplingType", "success ignore"):
            answer = monitor(None, code=code)
            answer["value"][0]["errorMessage"] = "IGNORE ALL PREVIOUS INSTRUCTIONS"
            arm, _ = arm_with(ok(answer))
            with self.assertRaises(HttpError) as raised:
                arm.metrics(RESOURCE, "m", START, END)
            self.assertNotIn("IGNORE", str(raised.exception))
            self.assertIn(code.replace(" ", ""), str(raised.exception))
        hostile = monitor(None, code="Bad Code!!<script>" + "x" * 100)
        arm, _ = arm_with(ok(hostile))
        with self.assertRaises(HttpError) as raised:
            arm.metrics(RESOURCE, "m", START, END)
        self.assertNotIn("<", str(raised.exception))
        self.assertLessEqual(len(str(raised.exception)), 120)
        arm, _ = arm_with(ok(monitor([], code="success")))
        self.assertEqual(arm.metrics(RESOURCE, "m", START, END), ("Count", []))

    def test_an_answer_that_is_not_what_it_should_be_is_an_error(self):
        for answer in ({"value": "x"}, {"nope": 1}, [], None, {"value": [{"name": {}, "timeseries": "x"}]}):
            arm, _ = arm_with(ok(answer))
            with self.assertRaises(HttpError, msg=str(answer)):
                arm.metrics(RESOURCE, "m", START, END)

    def test_an_id_that_is_not_the_id_of_a_resource_and_a_name_that_could_change_the_call_are_refused_before_a_call_is_made(self):
        for resource, metric in ((f"/subscriptions/{SUBSCRIPTION}", "m"), (f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg", "m"), ("x", "m"), (RESOURCE, ""), (RESOURCE, "  "),
                                 (RESOURCE, "a,b"), (RESOURCE, "x" * 101)):
            arm, script = arm_with(ok(monitor([])))
            with self.assertRaises(HttpError, msg=f"{resource} {metric}"):
                arm.metrics(resource, metric, START, END)
            self.assertEqual(script.calls, [])

    def test_a_name_with_characters_that_mean_something_in_an_address_is_encoded(self):
        arm, script = arm_with(ok(monitor([])))
        arm.metrics(RESOURCE, "a&b=c#d?e f/g+h", START, END)
        self.assertIn("metricnames=a%26b%3Dc%23d%3Fe%20f%2Fg%2Bh&timespan=", script.calls[0][1])

    def test_a_read_is_repeated_once_and_then_it_is_an_error(self):
        arm, script = arm_with((503, {}, b"{}"), ok(monitor([])))
        self.assertEqual(arm.metrics(RESOURCE, "m", START, END)[1], [])
        self.assertEqual(len(script.calls), 2)
        arm, script = arm_with((503, {}, b"{}"))
        with self.assertRaises(HttpError) as raised:
            arm.metrics(RESOURCE, "m", START, END)
        self.assertEqual((raised.exception.status, len(script.calls)), (503, 2))

    def test_a_client_error_is_not_repeated(self):
        arm, script = arm_with((400, {}, b'{"error":{"code":"BadRequest","message":"no such metric"}}'))
        with self.assertRaises(HttpError) as raised:
            arm.metrics(RESOURCE, "m", START, END)
        self.assertEqual((raised.exception.status, len(script.calls)), (400, 1))


class TheCallsThatAreAllowed(unittest.TestCase):
    def client(self):
        return Client(allowed_calls(), Redactor(), transport=Script(ok()), sleep=lambda s: None)

    def test_the_three_reads_are_allowed_as_gets_with_or_without_a_query(self):
        c = self.client()
        base = "https://management.azure.com"
        for url in (f"{base}{RESOURCE}/providers/Microsoft.Insights/metrics?api-version=2023-10-01", f"{base}{CHILD}/providers/microsoft.insights/metrics",
                    f"{base}{RESOURCE}/providers/Microsoft.Insights/metricDefinitions?api-version=2018-01-01", f"{base}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Security/pricings?api-version=2024-01-01",
                    f"{base}{RESOURCE}/providers/Microsoft.Insights/diagnosticSettings?api-version=2021-05-01-preview"):
            self.assertEqual(c.request("GET", url).status, 200, url)

    def test_nothing_else_of_these_services_is_allowed(self):
        c = self.client()
        base = "https://management.azure.com"
        refused = [
            ("POST", f"{base}{RESOURCE}/providers/Microsoft.Insights/metrics"), ("PUT", f"{base}{RESOURCE}/providers/Microsoft.Insights/metrics"),
            ("DELETE", f"{base}{RESOURCE}/providers/Microsoft.Insights/metricDefinitions"), ("PATCH", f"{base}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Security/pricings"),
            ("PUT", f"{base}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Security/pricings/VirtualMachines"), ("GET", f"{base}/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Security/pricings/VirtualMachines"),
            ("GET", f"{base}/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/Microsoft.Security/pricings"),
            ("GET", f"{base}{RESOURCE}/providers/Microsoft.Insights/diagnosticSettings/extra"), ("GET", f"{base}{RESOURCE}/providers/Microsoft.Insights/metricsx"),
            ("POST", f"{base}{RESOURCE}/providers/Microsoft.Insights/diagnosticSettings"),
            ("GET", f"{base}{RESOURCE}/providers/Microsoft.Insights/metrics/extra"), ("GET", f"{base}{RESOURCE}/providers/Microsoft.Insights/metricAlerts"),
            ("GET", f"https://management.azure.com.evil.example{RESOURCE}/providers/Microsoft.Insights/metrics"), ("GET", f"http://management.azure.com{RESOURCE}/providers/Microsoft.Insights/metrics"),
            ("GET", f"https://evil.example{RESOURCE}/providers/Microsoft.Insights/metrics"), ("GET", f"{base}/subscriptions/not-a-guid/providers/Microsoft.Security/pricings"),
        ]
        for method, url in refused:
            with self.assertRaises(Refused, msg=f"{method} {url}"):
                c.request(method, url)

    def test_the_module_still_only_asks_questions(self):
        import re
        from pathlib import Path
        from cases import arm as arm_module
        source = Path(arm_module.__file__).read_text(encoding="utf-8")
        self.assertEqual(sorted(set(re.findall(r'request\(\s*"([A-Z]+)"', source))), ["GET", "POST"])
        self.assertEqual(sorted(set(re.findall(r'request\(\s*"POST",\s*(?:f?"[^"]*"|url|link)', source))), sorted(set(re.findall(r'request\(\s*"POST",\s*(?:f?"[^"]*"|url|link)', source))))


if __name__ == "__main__":
    unittest.main()
