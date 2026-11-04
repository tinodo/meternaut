import datetime as dt
import json
import unittest

from support import SUBSCRIPTION, TOKEN
from cases import arm as arm_module
from cases.arm import Arm
from cases.http import Client, HttpError, allowed_calls
from cases.redact import Redactor
from test_http import PRODUCT_SUBSCRIPTION, Script, ok

RESOURCE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-app/providers/Microsoft.Network/privateEndpoints/pe-one"


def arm_with(*answers):
    script = Script(*answers)
    client = Client(allowed_calls("example-apim.azure-api.net", f"{PRODUCT_SUBSCRIPTION}/listSecrets"), Redactor(), transport=script, sleep=lambda s: None, jitter=lambda: 0.5)
    return Arm(client, lambda resource: TOKEN), script


class Graph(unittest.TestCase):
    def test_one_query_one_subscription_and_the_bearer_token_of_the_identity(self):
        arm, script = arm_with(ok({"data": [{"id": "a"}, {"id": "b"}, "not a row"]}))
        self.assertEqual(arm.graph(SUBSCRIPTION, "resources | take 1"), [{"id": "a"}, {"id": "b"}])
        ((method, url, headers, data, timeout),) = script.calls
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01")
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(json.loads(data), {"subscriptions": [SUBSCRIPTION], "query": "resources | take 1", "options": {"resultFormat": "objectArray", "$top": 1000}})

    def test_every_page_is_read(self):
        arm, script = arm_with(ok({"data": [{"id": "a"}], "$skipToken": "next"}), ok({"data": [{"id": "b"}]}))
        self.assertEqual([r["id"] for r in arm.graph(SUBSCRIPTION, "q")], ["a", "b"])
        self.assertEqual(json.loads(script.calls[1][3])["options"]["$skipToken"], "next")

    def test_too_many_pages_are_an_error_not_a_silent_cut(self):
        arm, _ = arm_with(ok({"data": [{"id": "a"}], "$skipToken": "again"}))
        with self.assertRaises(HttpError):
            arm.graph(SUBSCRIPTION, "q")

    def test_an_answer_that_is_not_a_result_is_an_error(self):
        for answer in ([], {"data": "x"}, None):
            arm, _ = arm_with(ok(answer))
            with self.assertRaises(HttpError):
                arm.graph(SUBSCRIPTION, "q")


class Costs(unittest.TestCase):
    PAGE = {"properties": {"columns": [{"name": "Cost"}, {"name": "ResourceId"}, {"name": "Currency"}],
                           "rows": [[1.5, RESOURCE, "USD"], [2.0, RESOURCE.upper(), "USD"], [0.25, "/subscriptions/x/other", "USD"]]}}

    def test_the_cost_lines_of_a_resource_are_added_up_by_lower_case_id(self):
        arm, script = arm_with(ok(self.PAGE))
        totals, currency = arm.costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))
        self.assertEqual((totals[RESOURCE.lower()], totals["/subscriptions/x/other"], currency), (3.5, 0.25, "USD"))
        body = json.loads(script.calls[0][3])
        self.assertEqual(body["type"], "ActualCost")
        self.assertEqual(body["timePeriod"], {"from": "2026-10-05T00:00:00Z", "to": "2026-11-03T23:59:59Z"})
        self.assertEqual(body["dataset"]["grouping"], [{"type": "Dimension", "name": "ResourceId"}])

    def test_the_next_page_is_read_from_the_same_service_only(self):
        link = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/query?api-version=2023-11-01&$skiptoken=abc"
        second = {"properties": {"columns": self.PAGE["properties"]["columns"], "rows": [[4.0, RESOURCE, "USD"]]}}
        arm, script = arm_with(ok({"properties": {**self.PAGE["properties"], "nextLink": link}}), ok(second))
        totals, _ = arm.costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))
        self.assertEqual(totals[RESOURCE.lower()], 7.5)
        self.assertEqual(script.calls[1][1], link)

    def test_a_link_to_another_place_is_refused(self):
        for link in ("https://evil.example/subscriptions/x/providers/Microsoft.CostManagement/query", "http://management.azure.com/x",
                     f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Compute/virtualMachines",
                     "https://management.azure.com/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.CostManagement/query"):
            arm, script = arm_with(ok({"properties": {**self.PAGE["properties"], "nextLink": link}}))
            with self.assertRaises(HttpError, msg=link):
                arm.costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))
            self.assertEqual(len(script.calls), 1)

    def test_more_than_one_currency_is_said_and_no_line_has_no_currency(self):
        mixed = {"properties": {"columns": self.PAGE["properties"]["columns"], "rows": [[1.0, "a", "USD"], [1.0, "b", "EUR"]]}}
        self.assertEqual(arm_with(ok(mixed))[0].costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))[1], "mixed")
        empty = {"properties": {"columns": self.PAGE["properties"]["columns"], "rows": []}}
        self.assertEqual(arm_with(ok(empty))[0].costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3)), ({}, None))

    def test_a_pre_tax_cost_column_is_read_too(self):
        page = {"properties": {"columns": [{"name": "PreTaxCost"}, {"name": "ResourceId"}], "rows": [[2.0, "a"]]}}
        self.assertEqual(arm_with(ok(page))[0].costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3)), ({"a": 2.0}, None))

    def test_an_answer_that_is_not_a_cost_table_is_an_error(self):
        for answer in ({"properties": {"columns": [{"name": "Other"}], "rows": []}}, {"nope": 1}, [], {"properties": {"columns": self.PAGE["properties"]["columns"], "rows": [["x", "a", "USD"]]}}):
            with self.assertRaises(HttpError):
                arm_with(ok(answer))[0].costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))


class AdvisorAndLocks(unittest.TestCase):
    def test_the_cost_recommendations_of_every_page(self):
        link = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Advisor/recommendations?api-version=2023-01-01&$skiptoken=1"
        arm, script = arm_with(ok({"value": [{"id": "a"}], "nextLink": link}), ok({"value": [{"id": "b"}, "x"]}))
        self.assertEqual([r["id"] for r in arm.advisor_cost(SUBSCRIPTION)], ["a", "b"])
        self.assertIn("$filter=Category%20eq%20%27Cost%27", script.calls[0][1])
        self.assertEqual(script.calls[0][0], "GET")

    def test_a_lock_is_the_scope_it_is_on_in_lower_case(self):
        group_lock = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/Rg-App/providers/Microsoft.Authorization/locks/protect"
        resource_lock = f"{RESOURCE}/providers/Microsoft.Authorization/locks/protect"
        subscription_lock = f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Authorization/locks/protect"
        arm, _ = arm_with(ok({"value": [{"id": group_lock}, {"id": resource_lock}, {"id": subscription_lock}, {"id": "garbage"}, {}]}))
        self.assertEqual(arm.locks(SUBSCRIPTION), [f"/subscriptions/{SUBSCRIPTION}/resourcegroups/rg-app", RESOURCE.lower(), f"/subscriptions/{SUBSCRIPTION}"])

    def test_a_link_to_another_service_is_refused(self):
        link = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Compute/virtualMachines"
        arm, _ = arm_with(ok({"value": [], "nextLink": link}))
        with self.assertRaises(HttpError):
            arm.locks(SUBSCRIPTION)


class NothingWrites(unittest.TestCase):
    def test_the_module_only_asks_questions(self):
        import re
        from pathlib import Path
        source = Path(arm_module.__file__).read_text(encoding="utf-8")
        self.assertEqual(sorted(set(re.findall(r'request\(\s*"([A-Z]+)"', source))), ["GET", "POST"])
        for word in ("PUT", "DELETE", "PATCH", "/delete", "/write", "/start", "/deallocate", "/resize"):
            self.assertNotIn(f'"{word}"', source)


if __name__ == "__main__":
    unittest.main()
