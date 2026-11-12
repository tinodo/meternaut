import datetime as dt
import json
import unittest

from support import SUBSCRIPTION, TOKEN
from cases import arm as arm_module
from cases.arm import Arm
from cases.http import Client, HttpError, allowed_calls
from cases.redact import Redactor
from test_http import Script, ok

RESOURCE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-app/providers/Microsoft.Network/privateEndpoints/pe-one"


def arm_with(*answers):
    script = Script(*answers)
    client = Client(allowed_calls(), Redactor(), transport=script, sleep=lambda s: None, jitter=lambda: 0.5)
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
    PAGE = {"properties": {"columns": [{"name": "Cost"}, {"name": "ResourceId"}, {"name": "ServiceName"}, {"name": "Currency"}],
                           "rows": [[1.5, RESOURCE, "Storage", "USD"], [2.0, RESOURCE.upper(), "Bandwidth", "USD"], [0.25, "/subscriptions/x/other", "Support", "USD"]]}}

    def test_the_cost_lines_of_a_resource_are_added_up_by_lower_case_id(self):
        arm, script = arm_with(ok(self.PAGE))
        totals, currency = arm.costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))
        self.assertEqual((totals[RESOURCE.lower()], totals["/subscriptions/x/other"], currency), (3.5, 0.25, "USD"))
        body = json.loads(script.calls[0][3])
        self.assertEqual(body["type"], "ActualCost")
        self.assertEqual(body["timePeriod"], {"from": "2026-10-05T00:00:00Z", "to": "2026-11-03T23:59:59Z"})
        self.assertEqual(body["dataset"]["grouping"], [{"type": "Dimension", "name": "ResourceId"}, {"type": "Dimension", "name": "ServiceName"}],
                         "the totals are added up from the lines by resource and service, which the tools of the investigation use too")

    def test_the_next_page_is_read_from_the_same_service_only(self):
        link = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/query?api-version=2023-11-01&$skiptoken=abc"
        second = {"properties": {"columns": self.PAGE["properties"]["columns"], "rows": [[4.0, RESOURCE, "Storage", "USD"]]}}
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
        mixed = {"properties": {"columns": self.PAGE["properties"]["columns"], "rows": [[1.0, "a", "S", "USD"], [1.0, "b", "S", "EUR"]]}}
        self.assertEqual(arm_with(ok(mixed))[0].costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))[1], "mixed")
        empty = {"properties": {"columns": self.PAGE["properties"]["columns"], "rows": []}}
        self.assertEqual(arm_with(ok(empty))[0].costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3)), ({}, None))

    def test_a_pre_tax_cost_column_is_read_too(self):
        page = {"properties": {"columns": [{"name": "PreTaxCost"}, {"name": "ResourceId"}, {"name": "ServiceName"}], "rows": [[2.0, "a", "S"]]}}
        self.assertEqual(arm_with(ok(page))[0].costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3)), ({"a": 2.0}, None))

    def test_an_answer_that_is_not_a_cost_table_is_an_error(self):
        for answer in ({"properties": {"columns": [{"name": "Other"}], "rows": []}}, {"nope": 1}, [], {"properties": {"columns": self.PAGE["properties"]["columns"], "rows": [["x", "a", "S", "USD"]]}}):
            with self.assertRaises(HttpError):
                arm_with(ok(answer))[0].costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))

    def test_the_lines_are_read_once_for_a_period_and_the_totals_and_the_lines_share_the_read(self):
        arm, script = arm_with(ok(self.PAGE))
        first, last = dt.date(2026, 10, 5), dt.date(2026, 11, 3)
        lines = arm.cost_lines(SUBSCRIPTION, first, last)
        self.assertEqual(arm.costs(SUBSCRIPTION, first, last)[0][RESOURCE.lower()], 3.5)
        self.assertEqual(arm.cost_lines(SUBSCRIPTION.upper(), first, last), lines, "the id of the subscription has no case")
        self.assertEqual(len(script.calls), 1, "one read of Cost Management for the subscription and the period")
        arm.cost_lines(SUBSCRIPTION, first, dt.date(2026, 11, 2))
        self.assertEqual(len(script.calls), 2, "another period is another read")

    def test_a_read_that_failed_is_not_kept_so_the_next_caller_reads_again(self):
        arm, script = arm_with(*([(500, {}, b"{}")] * 5), ok(self.PAGE))
        with self.assertRaises(HttpError):
            arm.cost_lines(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))
        self.assertEqual(len(arm.cost_lines(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))), 3)

    def test_the_lines_that_the_caller_gets_are_a_copy(self):
        arm, _ = arm_with(ok(self.PAGE))
        arm.cost_lines(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3)).clear()
        self.assertEqual(len(arm.cost_lines(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))), 3)

    def test_a_subscription_with_more_lines_than_the_pages_that_are_read_still_has_its_totals_from_the_single_grouping(self):
        link = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/providers/Microsoft.CostManagement/query?api-version=2023-11-01&$skiptoken=abc"
        full = {"properties": {**self.PAGE["properties"], "nextLink": link}}
        totals = {"properties": {"columns": [{"name": "Cost"}, {"name": "ResourceId"}, {"name": "Currency"}], "rows": [[7.0, RESOURCE, "USD"]]}}
        arm, script = arm_with(*([ok(full)] * 10), ok(totals))
        self.assertEqual(arm.costs(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3)), ({RESOURCE.lower(): 7.0}, "USD"))
        self.assertEqual(json.loads(script.calls[-1][3])["dataset"]["grouping"], [{"type": "Dimension", "name": "ResourceId"}])
        with self.assertRaises(HttpError):
            arm_with(*([ok(full)] * 10))[0].cost_lines(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))

    def test_every_cost_read_names_its_own_client_type_so_that_it_does_not_share_the_quota_of_every_caller_that_names_none(self):
        arm, script = arm_with(ok(self.PAGE), ok({"properties": {"columns": [{"name": "Cost"}, {"name": "PricingModel"}, {"name": "ChargeType"}, {"name": "Currency"}],
                                                                  "rows": [[5.0, "OnDemand", "Usage", "USD"]]}}))
        arm.cost_lines(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))
        arm.cost_models(SUBSCRIPTION, dt.date(2026, 10, 5), dt.date(2026, 11, 3))
        self.assertEqual([call[2]["ClientType"] for call in script.calls], ["Meternaut", "Meternaut"])


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


class LocksAtAScope(unittest.TestCase):
    GROUP = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/Rg-App"

    def test_the_locks_of_one_scope_are_asked_for_at_that_scope_with_the_filter_that_adds_the_scopes_above_and_come_back_in_lower_case(self):
        lock = f"{self.GROUP}/providers/Microsoft.Authorization/locks/protect"
        inherited = f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Authorization/locks/protect"
        arm, script = arm_with(ok({"value": [{"id": lock}, {"id": inherited}]}))
        self.assertEqual(arm.locks_at(SUBSCRIPTION, self.GROUP), [self.GROUP.lower(), f"/subscriptions/{SUBSCRIPTION}"])
        ((method, url, headers, _, _),) = script.calls
        self.assertEqual(method, "GET")
        self.assertEqual(url, f"https://management.azure.com{self.GROUP}/providers/Microsoft.Authorization/locks?api-version=2016-09-01&$filter=atScope()")
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")

    def test_a_resource_and_a_child_resource_are_scopes_too(self):
        child = f"{RESOURCE}/privateDnsZoneGroups/default"
        for scope in (RESOURCE, child):
            arm, script = arm_with(ok({"value": []}))
            self.assertEqual(arm.locks_at(SUBSCRIPTION, scope), [])
            self.assertTrue(script.calls[0][1].startswith(f"https://management.azure.com{scope}/providers/Microsoft.Authorization/locks?"))

    def test_a_scope_that_is_not_one_of_the_subscription_is_refused_before_a_call_is_made(self):
        other = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg"
        for scope in (other, "/subscriptions/not-a-guid", f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/../x", "", "/",
                      f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/providers/Microsoft.Network", f"{self.GROUP}?x=1", f"{self.GROUP}/x y"):
            arm, script = arm_with(ok({"value": []}))
            with self.assertRaises(HttpError, msg=scope):
                arm.locks_at(SUBSCRIPTION, scope)
            self.assertEqual(script.calls, [], scope)

    def test_the_next_page_of_the_list_stays_on_the_locks_of_the_subscription(self):
        lock = f"{self.GROUP}/providers/Microsoft.Authorization/locks/a"
        link = f"https://management.azure.com{self.GROUP}/providers/Microsoft.Authorization/locks?api-version=2016-09-01&$skiptoken=1"
        arm, script = arm_with(ok({"value": [{"id": lock}], "nextLink": link}), ok({"value": []}))
        self.assertEqual(arm.locks_at(SUBSCRIPTION, self.GROUP), [self.GROUP.lower()])
        self.assertEqual(script.calls[1][1], link)
        arm, _ = arm_with(ok({"value": [], "nextLink": "https://evil.example/subscriptions/x/providers/Microsoft.Authorization/locks"}))
        with self.assertRaises(HttpError):
            arm.locks_at(SUBSCRIPTION, self.GROUP)


class ScopesOf(unittest.TestCase):
    GROUP = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-app"

    def test_a_resource_has_itself_and_then_its_group(self):
        self.assertEqual(arm_module.scopes_of(RESOURCE), [RESOURCE, self.GROUP])
        child = f"{RESOURCE}/privateDnsZoneGroups/default"
        self.assertEqual(arm_module.scopes_of(child), [child, self.GROUP])

    def test_a_group_is_its_own_scope_in_any_case(self):
        self.assertEqual(arm_module.scopes_of(self.GROUP), [self.GROUP])
        self.assertEqual(arm_module.scopes_of(self.GROUP.upper()), [self.GROUP.upper()])

    def test_an_id_without_a_group_has_only_itself(self):
        self.assertEqual(arm_module.scopes_of(f"/subscriptions/{SUBSCRIPTION}"), [f"/subscriptions/{SUBSCRIPTION}"])


ZONE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.azure-api.net"


class TheListsOfTheImpactCheck(unittest.TestCase):
    def test_the_dns_zone_groups_of_an_endpoint_and_the_address_records_of_a_zone_are_two_reads_of_exactly_their_addresses(self):
        arm, script = arm_with(ok({"value": [{"name": "default"}, "not an item"]}), ok({"value": [{"name": "apim-demo"}]}))
        self.assertEqual(arm.zone_groups(RESOURCE), [{"name": "default"}])
        self.assertEqual(arm.zone_records(ZONE), [{"name": "apim-demo"}])
        first, second = script.calls
        self.assertEqual((first[0], first[1]), ("GET", f"https://management.azure.com{RESOURCE}/privateDnsZoneGroups?api-version=2026-01-01"))
        self.assertEqual((second[0], second[1]), ("GET", f"https://management.azure.com{ZONE}/A?api-version=2018-09-01&$top=1000"))
        self.assertEqual((first[2]["Authorization"], second[2]["Authorization"]), (f"Bearer {TOKEN}", f"Bearer {TOKEN}"))

    def test_an_id_that_is_not_an_endpoint_or_a_zone_is_refused_before_any_call(self):
        arm, script = arm_with(ok({"value": []}))
        group = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg"
        for method, value in ((arm.zone_groups, f"{group}/providers/Microsoft.Compute/disks/d"), (arm.zone_groups, RESOURCE.replace("pe-one", "..")), (arm.zone_groups, RESOURCE + "'"),
                              (arm.zone_groups, RESOURCE + "/privateDnsZoneGroups/default"), (arm.zone_records, RESOURCE), (arm.zone_records, ZONE + "/virtualNetworkLinks/x"),
                              (arm.zone_records, ZONE.replace("privatelink.azure-api.net", ".."))):
            with self.subTest(value=value):
                with self.assertRaises(HttpError):
                    method(value)
        self.assertEqual(script.calls, [])

    def test_an_answer_that_is_not_a_list_is_an_error_and_a_next_link_that_leaves_azure_is_not_followed(self):
        for answer in ({"value": "x"}, [], "text"):
            arm, _ = arm_with(ok(answer))
            with self.assertRaises(HttpError):
                arm.zone_groups(RESOURCE)
        arm, script = arm_with(ok({"value": [], "nextLink": "https://evil.example/x"}))
        with self.assertRaises(HttpError):
            arm.zone_records(ZONE)
        self.assertEqual(len(script.calls), 1)


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
