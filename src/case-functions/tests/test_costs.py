"""The words, the scopes and the address of the cost of a finding (cases/costs.py). Everything in it is INVENTED."""
import unittest
from urllib.parse import unquote

import support  # noqa: F401  (puts the app on the path)

from cases import costs

SUB = "11111111-2222-4333-8444-555555555555"
GROUP = "rg-demo"


class TheScopeOfAnId(unittest.TestCase):
    def test_a_subscription_a_resource_group_and_a_resource_are_told_apart_whatever_the_case(self):
        found = {
            f"/subscriptions/{SUB}": ("subscription", SUB, ""),
            f"/SUBSCRIPTIONS/{SUB.upper()}/": ("subscription", SUB, ""),
            f"/subscriptions/{SUB}/resourceGroups/{GROUP}": ("group", SUB, GROUP),
            f"/subscriptions/{SUB}/RESOURCEGROUPS/Rg-Demo/": ("group", SUB, "Rg-Demo"),
            f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/d1": ("resource", SUB, GROUP),
            f"/subscriptions/{SUB}/providers/Microsoft.Security/pricings/standard": ("resource", SUB, ""),
        }
        for resource_id, expected in found.items():
            with self.subTest(resource_id=resource_id):
                self.assertEqual(tuple(costs.scope_of(resource_id)), expected)

    def test_anything_that_is_not_an_azure_id_is_no_scope(self):
        for bad in ("", None, 5, "/subscriptions", "/subscriptions/not-a-guid", f"subscriptions/{SUB}", f"/other/{SUB}", "https://example.invalid/x"):
            with self.subTest(bad=bad):
                self.assertEqual(tuple(costs.scope_of(bad)), ("", "", ""))

    def test_only_a_subscription_and_a_resource_group_are_containers_and_their_key_is_in_lower_case(self):
        self.assertTrue(costs.is_container(f"/subscriptions/{SUB}"))
        self.assertTrue(costs.is_container(f"/subscriptions/{SUB}/resourceGroups/{GROUP}"))
        self.assertFalse(costs.is_container(f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/d1"))
        self.assertFalse(costs.is_container("nonsense"))
        self.assertEqual(costs.container_key(f"/Subscriptions/{SUB.upper()}"), f"/subscriptions/{SUB}")
        self.assertEqual(costs.container_key(f"/subscriptions/{SUB}/resourceGroups/Rg-Demo"), f"/subscriptions/{SUB}/resourcegroups/rg-demo")
        self.assertEqual(costs.container_key(f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/d1"), "")


class TheAddressOfCostAnalysis(unittest.TestCase):
    BASE = "https://portal.azure.com/#blade/Microsoft_Azure_CostManagement/Menu/open/costanalysis/scope/"

    def test_the_scope_is_the_subscription_or_one_of_its_resource_groups_and_is_encoded(self):
        self.assertEqual(costs.analysis_url(SUB), f"{self.BASE}%2Fsubscriptions%2F{SUB}")
        self.assertEqual(costs.analysis_url(SUB.upper()), f"{self.BASE}%2Fsubscriptions%2F{SUB}", "the id is written in lower case")
        found = costs.analysis_url(SUB, "Rg_(Demo).v2")
        self.assertEqual(found, f"{self.BASE}%2Fsubscriptions%2F{SUB}%2FresourceGroups%2FRg_%28Demo%29.v2")
        self.assertEqual(unquote(found.rsplit("scope/", 1)[1]), f"/subscriptions/{SUB}/resourceGroups/Rg_(Demo).v2")

    def test_an_id_that_is_not_one_and_a_name_that_cannot_be_the_name_of_a_resource_group_make_no_link(self):
        for bad_subscription in ("", None, "x", f"{SUB}/..", SUB + "0", "../" + SUB):
            with self.subTest(subscription=bad_subscription):
                self.assertEqual(costs.analysis_url(bad_subscription), "")
        for bad_group in ("a b", "a/b", "a\\b", "x" * 91, "ends.", "a?b", "a#b", "<script>", "a\nb", "a;b", "javascript:alert(1)", "a%2Fb", "https://evil.example"):
            with self.subTest(group=bad_group):
                self.assertEqual(costs.analysis_url(SUB, bad_group), "")

    def test_a_name_that_azure_allows_is_a_group(self):
        for good in ("rg-demo", "RG_Demo", "a", "x" * 90, "team.apps(1)", "grüne-gruppe", "组"):
            with self.subTest(group=good):
                self.assertTrue(costs.valid_group(good))
                self.assertTrue(costs.analysis_url(SUB, good).startswith(self.BASE))
        for bad in ("", None, 5, "ends."):
            self.assertFalse(costs.valid_group(bad))

    def test_the_address_holds_no_character_that_could_leave_an_attribute_or_a_path(self):
        found = costs.analysis_url(SUB, "grüne-gruppe")
        self.assertRegex(found, r"^https://portal\.azure\.com/#blade/[A-Za-z_]+/Menu/open/costanalysis/scope/[A-Za-z0-9%._-]+$")
        self.assertNotRegex(found, r"""["'<>\s\\]""")


class WhatACostIsMadeOf(unittest.TestCase):
    def test_the_three_largest_services_and_what_the_others_cost_together(self):
        made = costs.parts_of({"Virtual Network": 88.10, "Microsoft Defender for Cloud": 41.25, "Azure Cognitive Search": 19.60, "Grafana": 9.90, "Container Registry": 9.05,
                               "Web PubSub": 8.10, "Storage": 6.10, "Bandwidth": 30.30})
        self.assertEqual(made["services"], [["Virtual Network", 88.1], ["Microsoft Defender for Cloud", 41.25], ["Bandwidth", 30.3]])
        self.assertEqual((made["more"], made["moreUsd"]), (5, 52.75))
        self.assertEqual(round(sum(amount for _, amount in made["services"]) + made["moreUsd"], 2), 212.4)

    def test_fewer_services_than_the_top_leave_nothing_over_and_a_service_without_a_name_is_other(self):
        made = costs.parts_of({"": 3.0, "  ": 2.0, "Storage": 1.0})
        self.assertEqual(made["services"], [["Other", 5.0], ["Storage", 1.0]])
        self.assertEqual((made["more"], made["moreUsd"]), (0, 0.0))

    def test_a_cost_of_nothing_has_no_parts_and_a_credit_is_not_a_service_that_cost_something(self):
        self.assertEqual(costs.parts_of({}), {})
        self.assertEqual(costs.parts_of({"Storage": 0.0, "Support": -1.5}), {})
        made = costs.parts_of({"Storage": 4.0, "Support": -1.5})
        self.assertEqual(made["services"], [["Storage", 4.0]])

    def test_what_a_record_holds_is_read_back_only_when_it_is_what_parts_of_makes(self):
        made = costs.parts_of({"A": 5.0, "B": 3.0, "C": 2.0, "D": 1.0})
        self.assertEqual(costs.valid_parts(made), made)
        for damaged in (None, [], {}, {"services": []}, {"services": [["A", 1.0]] * 4, "more": 0, "moreUsd": 0}, {"services": [["A", "1"]], "more": 0, "moreUsd": 0},
                        {"services": [["", 1.0]], "more": 0, "moreUsd": 0}, {"services": [["A", -1.0]], "more": 0, "moreUsd": 0}, {"services": [["A", 1.0]], "more": -1, "moreUsd": 0},
                        {"services": [["A", 1.0]], "more": True, "moreUsd": 0}, {"services": [["A", 1.0]], "more": 0, "moreUsd": float("nan")}, {"services": [["A", 1.0]], "more": 0}):
            with self.subTest(damaged=str(damaged)[:50]):
                self.assertEqual(costs.valid_parts(damaged), {})


class TheWordsOfEachState(unittest.TestCase):
    def test_each_state_says_what_it_is_in_plain_words(self):
        self.assertEqual(costs.state_words(costs.NONE), "Azure has no cost line for this yet.")
        self.assertEqual(costs.state_words(costs.FAILED), "Cost could not be read just now.")
        self.assertEqual(costs.state_words(costs.CURRENCY), "The cost lines are not in US dollars.")
        self.assertEqual(costs.state_words(""), "No cost line was read yet.")
        self.assertEqual(costs.state_words(costs.LINES), "Cost Management shows no cost for this in the last 30 days.")
        self.assertEqual(costs.state_words("unheard of"), "No cost line was read yet.")

    def test_a_row_that_stands_for_several_says_these(self):
        self.assertEqual(costs.state_words(costs.NONE, many=True), "Azure has no cost line for these yet.")
        self.assertEqual(costs.state_words(costs.LINES, many=True), "Cost Management shows no cost for these in the last 30 days.")
        self.assertEqual(costs.state_words(costs.FAILED, many=True), "Cost could not be read just now.")

    def test_a_read_that_failed_is_told_before_a_cost_of_nothing(self):
        self.assertEqual(costs.worst_state([costs.NONE, costs.FAILED]), costs.FAILED)
        self.assertEqual(costs.worst_state([costs.NONE, costs.CURRENCY]), costs.CURRENCY)
        self.assertEqual(costs.worst_state([costs.NONE, ""]), "", "one that was not read is not said to have no line")
        self.assertEqual(costs.worst_state([costs.LINES, costs.NONE]), costs.NONE)
        self.assertEqual(costs.worst_state([costs.LINES]), costs.LINES)
        self.assertEqual(costs.worst_state([]), "")

    def test_no_word_of_a_state_says_a_cost_of_nothing_for_a_cost_that_azure_does_not_have(self):
        for state in (costs.NONE, costs.FAILED, costs.CURRENCY, ""):
            text = costs.state_words(state)
            self.assertNotRegex(text, r"\$\s?0|\b0\.00\b|zero|\bno cost\b(?! line)", state)


if __name__ == "__main__":
    unittest.main()
