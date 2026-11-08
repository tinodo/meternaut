"""The deeper tools of the investigator against a fake estate. Every name, id and number in it is INVENTED (see deep_estate.py)."""
import datetime as dt
import json
import unittest

import support  # noqa: F401  (it puts the app on the path)
from cases import toolbox as tb
from deep_estate import (ACCOUNT, AI, COLLECTION, MACHINE, OTHER_WORKSPACE, RULES, SUB, VM, WORKSPACE, WS, deep, deployment, ident, table, usage)
from test_toolbox import HOSTILE, MARKERS, SUB2, ask, point, row, toolbox

NOT_VISIBLE = "not visible with this access"


class Base(unittest.TestCase):
    def setUp(self):
        self.estate = deep()
        self.notes = []
        self.box = toolbox(self.estate, notes=self.notes)

    def handle(self, kind):
        """The handle of the first resource of a type, which the listing gives."""
        return ask(self.box, "list_resources", type=kind)["rows"][0][0]

    def clean(self, answer):
        text = json.dumps(answer)
        self.assertEqual([marker for marker in MARKERS if marker in text], [])

    def calls_to(self, word):
        return [call for call in self.estate.calls if word in call["url"].lower()]


def by_name(answer):
    return {line[0]: dict(zip(answer["cols"], line)) for line in answer["rows"]}


class TheOffers(Base):
    def test_a_listing_and_a_description_say_which_deeper_reads_a_type_has(self):
        for kind, reads in ((WORKSPACE, ["data_volume", "data_readers", "data_writers"]), (ACCOUNT, ["children"])):
            listing = ask(self.box, "list_resources", type=kind)
            self.assertEqual(listing["reads"], reads)
            self.assertEqual(ask(self.box, "describe", handle=listing["rows"][0][0])["reads"], reads)
        machine = ask(self.box, "list_resources", type=VM)
        self.assertNotIn("reads", machine)
        self.assertNotIn("reads", ask(self.box, "describe", handle=machine["rows"][0][0]))

    def test_a_read_that_a_type_does_not_have_answers_not_offered_and_reads_nothing(self):
        workspace, account, machine = self.handle(WORKSPACE), self.handle(ACCOUNT), self.handle(VM)
        before = len(self.estate.calls)
        for name, handle in (("data_volume", machine), ("data_volume", account), ("data_readers", machine), ("data_readers", account), ("children", machine), ("children", workspace)):
            self.assertEqual(ask(self.box, name, handle=handle), {"error": "not-offered"}, (name, handle))
        self.assertEqual(len(self.estate.calls), before)
        self.assertEqual(ask(self.box, "data_volume", handle="r99"), {"error": "unknown-handle"})
        self.assertEqual(ask(self.box, "data_volume", handle="vm-demo"), {"error": "bad-arguments"})


class TheVolume(Base):
    def test_a_workspace_gives_its_tables_by_the_volume_that_is_charged_for(self):
        handle = self.handle(WORKSPACE)
        answer = ask(self.box, "data_volume", handle=handle)
        self.assertEqual((answer["volume"], answer["settings"], answer["tables_listed"], answer["days"]), ("read", "read", "read", 30))
        self.assertEqual(answer["pricing"], {"tier": "PerGB2018", "retention_days": 30, "ingestion": "RespectQuota", "query_access": "Enabled"})
        self.assertEqual((answer["billable_gb"], answer["free_gb"], answer["tables_with_data"], answer["tables_in_workspace"]), (5.02, 0.05, 4, 4))
        self.assertEqual(answer["cols"], ["table", "plan", "retention_days", "total_retention_days", "gb", "share", "days", "trend", "free_gb"])
        tables = by_name(answer)
        self.assertEqual([line[0] for line in answer["rows"]], ["t1", "Perf", "Heartbeat", "AzureActivity"])  # the largest first
        self.assertEqual(tables["Heartbeat"], {"table": "Heartbeat", "plan": "Analytics", "retention_days": 30, "total_retention_days": 30, "gb": 1, "share": 0.199, "days": 2,
                                               "trend": [1, 0, 0, 0, 0, 0], "free_gb": 0})
        self.assertEqual((tables["Perf"]["gb"], tables["Perf"]["free_gb"]), (1, 0.05))
        self.assertEqual((tables["t1"]["plan"], tables["t1"]["retention_days"], tables["t1"]["gb"]), ("Basic", 8, 3))

    def test_the_read_is_one_query_of_the_closed_days_that_code_wrote(self):
        self.estate.usage = []
        ask(self.box, "data_volume", handle=self.handle(WORKSPACE), days=7)
        (call,) = self.calls_to("api.loganalytics.azure.com")
        self.assertEqual((call["method"], call["path"]), ("POST", f"/v1/workspaces/{tb.deeper.customer_id(self.estate.workspace)}/query"))
        self.assertTrue(call["body"]["query"].startswith("// meternaut:usage\nUsage | where TimeGenerated > ago(9d)"))
        self.assertIn("startofday(ago(7d))", call["body"]["query"])
        self.assertEqual(call["body"]["timespan"], "2026-10-26T00:00:00Z/2026-11-04T12:00:00Z")  # starts two days before the first closed day, so the last hours are in it

    def test_a_table_that_the_platform_did_not_make_is_a_handle_and_its_name_is_never_shown(self):
        self.estate.tables += [table(HOSTILE, plan="Analytics", kind="CustomLog"), table("SecurityEvent", kind="CustomLog")]
        self.estate.usage += [usage(9, HOSTILE, 500.0), usage(9, "SecurityEvent", 100.0), usage(9, "Unlisted_CL", 10.0)]
        answer = ask(self.box, "data_volume", handle=self.handle(WORKSPACE))
        self.clean(answer)
        self.assertEqual(sorted(name for name in by_name(answer) if name.startswith("t")), ["t1", "t2", "t3", "t4"])  # a table of a customer is a handle, even when it is named like one
        self.assertNotIn("SecurityEvent", json.dumps(answer))
        self.assertEqual([line[0] for line in answer["rows"]].count("Heartbeat"), 1)

    def test_the_volume_of_the_first_tables_is_kept_for_the_investigation_to_check_a_claim_against(self):
        handle = self.handle(WORKSPACE)
        ask(self.box, "data_volume", handle=handle)
        metrics = self.box.evidence[handle]["metrics"]
        self.assertEqual(metrics["Billable GB Heartbeat"], {"total": 1, "max": 0.6, "average": 0.5, "days_with_data": 2, "days": 30, "unit": "GB", "totals": [1]})
        self.assertEqual(metrics["Billable GB t1"]["total"], 3)
        self.assertEqual(len(metrics), 4)

    def test_a_second_ask_reads_nothing_again(self):
        handle = self.handle(WORKSPACE)
        first = ask(self.box, "data_volume", handle=handle)
        calls = len(self.estate.calls)
        self.assertEqual(ask(self.box, "data_volume", handle=handle), first)
        self.assertEqual(len(self.estate.calls), calls)
        ask(self.box, "data_volume", handle=handle, days=7)  # another window is another read
        self.assertEqual(len(self.calls_to("api.loganalytics.azure.com")), 2)

    def test_the_tables_are_paged_and_an_answer_stays_under_the_cap(self):
        self.estate.tables += [table(f"Table{n:03d}") for n in range(80)]
        self.estate.usage += [usage(10, f"Table{n:03d}", 10.0 + n) for n in range(80)]
        handle = self.handle(WORKSPACE)
        seen, offset = [], 0
        while True:
            answer = ask(self.box, "data_volume", handle=handle, offset=offset)
            self.assertLessEqual(len(json.dumps(answer, separators=(",", ":"))), tb.MAX_RESULT_CHARS)
            seen += [line[0] for line in answer["rows"]]
            if "next_offset" not in answer:
                break
            offset = answer["next_offset"]
        self.assertEqual(len(seen), 84)
        self.assertEqual(len(set(seen)), 84)

    def test_records_that_this_access_cannot_read_are_said_so_and_never_counted_as_none(self):
        self.estate.failures["query"] = 403
        answer = ask(self.box, "data_volume", handle=self.handle(WORKSPACE))
        self.assertEqual((answer["volume"], answer["tables_listed"]), (NOT_VISIBLE, "read"))
        self.assertNotIn("rows", answer)
        self.assertNotIn("billable_gb", answer)
        self.assertTrue(any("data_volume: the records could not be read" in note for note in self.notes))

    def test_a_workspace_whose_settings_cannot_be_read_cannot_be_asked_for_its_records(self):
        self.estate.failures["workspace"] = 403
        answer = ask(self.box, "data_volume", handle=self.handle(WORKSPACE))
        self.assertEqual((answer["settings"], answer["volume"], answer["tables_listed"]), (NOT_VISIBLE, NOT_VISIBLE, "read"))
        self.assertEqual(self.calls_to("api.loganalytics.azure.com"), [])

    def test_when_neither_the_settings_nor_the_tables_can_be_read_the_answer_is_unavailable(self):
        self.estate.failures.update(workspace=500, tables=500)
        self.assertEqual(ask(self.box, "data_volume", handle=self.handle(WORKSPACE)), {"error": "unavailable"})

    def test_a_read_that_failed_is_not_made_again_in_the_run(self):
        self.estate.failures["query"] = 500
        handle = self.handle(WORKSPACE)
        ask(self.box, "data_volume", handle=handle)
        calls = len(self.calls_to("api.loganalytics.azure.com"))
        self.assertEqual(ask(self.box, "data_volume", handle=handle)["volume"], "unavailable")
        self.assertEqual(len(self.calls_to("api.loganalytics.azure.com")), calls)
        self.assertEqual(sum("data_volume: the records could not be read" in note for note in self.notes), 1)

    def test_a_free_volume_is_shown_only_when_there_is_some(self):
        self.estate.usage = [usage(6, "Heartbeat", 400.0)]
        answer = ask(self.box, "data_volume", handle=self.handle(WORKSPACE))
        self.assertNotIn("free_gb", answer)
        self.assertEqual(answer["cols"][-1], "trend")


class TheReaders(Base):
    def setUp(self):
        super().setUp()
        estate = self.estate
        estate.rule_rows = [row(RULES, "rule-1", properties={"scopes": [WS], "enabled": True, "criteria": {"allOf": [{"query": "Heartbeat | where TimeGenerated > ago(1h) | count"}]}}),
                            row(RULES, "rule-2", properties={"scopes": [WS], "enabled": False, "criteria": {"allOf": [{"query": "Perf | count"}]}}),
                            row(RULES, "rule-3", properties={"scopes": [OTHER_WORKSPACE], "enabled": True, "criteria": {"allOf": [{"query": "Perf | count"}]}})]
        estate.saved = [{"properties": {"query": "AzureActivity | take 10"}}, {"properties": {"query": "search \"anything\""}}, {"properties": {"query": f"// {HOSTILE}\nHeartbeat | take 1"}}]
        estate.workbooks = [{"properties": {"serializedData": json.dumps({"items": [{"content": {"query": "Perf | summarize count()"}}], "scope": WS}), "sourceId": "Azure Monitor"}},
                            {"properties": {"serializedData": json.dumps({"items": [{"content": {"query": "Perf | count"}}]}), "sourceId": "Azure Monitor"}}]
        estate.sentinel = [{"kind": "Scheduled", "properties": {"query": "Heartbeat | take 1"}}, {"kind": "Fusion", "properties": {}}]
        estate.audit_totals = [{"Runs": 7, "Callers": 2}]
        estate.audit_texts = [{"QueryText": "Perf | take 5", "Runs": 5}, {"QueryText": "Heartbeat | take 1", "Runs": 2}]
        self.workspace = self.handle(WORKSPACE)

    def test_each_table_is_counted_by_what_names_it(self):
        answer = ask(self.box, "data_readers", handle=self.workspace)
        self.clean(answer)
        self.assertEqual(answer["cols"], ["table", "rules", "saved_searches", "workbooks", "analytics_rules", "runs"])
        tables = by_name(answer)
        self.assertEqual(tables["Heartbeat"], {"table": "Heartbeat", "rules": 1, "saved_searches": 1, "workbooks": 0, "analytics_rules": 1, "runs": 2})
        self.assertEqual(tables["Perf"], {"table": "Perf", "rules": 0, "saved_searches": 0, "workbooks": 1, "analytics_rules": 0, "runs": 5})
        self.assertEqual(tables["AzureActivity"]["saved_searches"], 1)
        self.assertEqual(tables["t1"], {"table": "t1", "rules": 0, "saved_searches": 0, "workbooks": 0, "analytics_rules": 0, "runs": 0})
        self.assertEqual(answer["sources"], {"rules": {"read": 1, "disabled": 1, "scanning_all": 0}, "saved_searches": {"read": 3, "scanning_all": 1},
                                             "workbooks": {"read": 1, "scanning_all": 0}, "analytics_rules": {"read": 1, "scanning_all": 0},
                                             "query_log": {"runs": 7, "callers": 2, "texts_read": 2}})

    def test_the_sources_are_read_once_and_the_texts_of_the_items_go_nowhere(self):
        ask(self.box, "data_readers", handle=self.workspace)
        calls = len(self.estate.calls)
        ask(self.box, "data_readers", handle=self.workspace, limit=2)
        self.assertEqual(len(self.estate.calls), calls)
        sent = json.dumps([call["body"] for call in self.estate.calls if call["body"]])
        self.assertNotIn("IGNORE", sent)
        self.assertEqual(self.box.notes, [])

    def test_the_query_log_is_read_without_the_reads_of_this_app_and_says_when_it_is_not_recorded(self):
        ask(self.box, "data_readers", handle=self.workspace)
        texts = [call["body"]["query"] for call in self.calls_to("api.loganalytics.azure.com")]
        self.assertEqual(len(texts), 3)  # the usage, the number of runs and the texts of them
        self.assertTrue(all("QueryText !contains \"meternaut:\"" in text for text in texts if "LAQueryLogs" in text))
        self.estate.failures["audit"] = 400
        box = toolbox(self.estate)
        answer = ask(box, "data_readers", handle=ask(box, "list_resources", type=WORKSPACE)["rows"][0][0])
        self.assertEqual(answer["sources"]["query_log"], "not recorded")
        self.assertTrue(all(line[-1] is None for line in answer["rows"]))

    def test_when_the_records_cannot_be_read_the_record_of_the_runs_is_not_asked_for_and_says_the_same(self):
        self.estate.failures["query"] = 403
        answer = ask(self.box, "data_readers", handle=self.workspace)
        self.assertEqual((answer["volume"], answer["sources"]["query_log"]), (NOT_VISIBLE, NOT_VISIBLE))
        self.assertNotIn("rows", answer)
        self.assertEqual(len(self.calls_to("api.loganalytics.azure.com")), 1)  # the read of the volume, and none for the record of the runs
        self.assertEqual(answer["sources"]["rules"], {"read": 1, "disabled": 1, "scanning_all": 0})  # the other sources are read all the same

    def test_a_workspace_that_is_not_onboarded_to_sentinel_has_no_analytics_rules(self):
        self.estate.failures["sentinel"] = 400
        answer = ask(self.box, "data_readers", handle=self.workspace)
        self.assertEqual(answer["sources"]["analytics_rules"], "not enabled")
        self.assertEqual(by_name(answer)["Heartbeat"]["analytics_rules"], 0)

    def test_a_source_that_this_access_cannot_read_has_no_counts_and_no_proof(self):
        self.estate.failures["saved"] = 403
        answer = ask(self.box, "data_readers", handle=self.workspace)
        self.assertEqual(answer["sources"]["saved_searches"], NOT_VISIBLE)
        self.assertTrue(all(line[answer["cols"].index("saved_searches")] is None for line in answer["rows"]))
        metrics = self.box.evidence[self.workspace]["metrics"]
        self.assertEqual((metrics["Readers Heartbeat"]["total"], metrics["Readers Heartbeat"]["days_with_data"]), (None, 0))
        self.assertEqual(metrics["Runs Heartbeat"]["total"], 2)

    def test_the_readers_that_a_table_could_have_include_the_items_that_read_every_table(self):
        answer = ask(self.box, "data_readers", handle=self.workspace)
        metrics = self.box.evidence[self.workspace]["metrics"]
        self.assertEqual(metrics["Readers Heartbeat"]["total"], 1 + 1 + 1 + 1)  # a rule, a saved search, a Sentinel rule, and the one search over every table
        self.assertEqual(metrics["Readers t1"]["total"], 1)  # nothing names it, and one item could be reading it
        self.assertEqual(answer["sources"]["saved_searches"]["scanning_all"], 1)

    def test_without_the_list_of_tables_nothing_is_counted_by_table(self):
        self.estate.failures["tables"] = 403
        answer = ask(self.box, "data_readers", handle=self.workspace)
        self.assertEqual(answer["tables_listed"], NOT_VISIBLE)
        self.assertNotIn("rows", answer)
        self.assertNotIn("sources", answer)

    def test_the_tables_are_paged_by_limit_and_offset(self):
        first = ask(self.box, "data_readers", handle=self.workspace, limit=3)
        self.assertEqual((first["returned"], first["next_offset"]), (3, 3))
        second = ask(self.box, "data_readers", handle=self.workspace, limit=3, offset=3)
        self.assertEqual([line[0] for line in first["rows"] + second["rows"]], ["t1", "Perf", "Heartbeat", "AzureActivity"])

    def test_rules_of_the_workspace_are_asked_for_by_its_id_and_nothing_else_enters_the_query(self):
        ask(self.box, "data_readers", handle=self.workspace)
        (call,) = [c for c in self.estate.calls if c["body"] and "rules-of-workspace" in c["body"].get("query", "")]
        self.assertIn(f"contains '{WS}'", call["body"]["query"])
        self.assertEqual(self.estate.graph_names().count("rules-of-workspace"), 1)


class TheWriters(Base):
    def setUp(self):
        super().setUp()
        self.estate.collection_rows = [
            row(COLLECTION, "dcr-1", kind="Windows", properties={
                "dataSources": {"performanceCounters": [{"name": "a"}, {"name": "b"}], "windowsEventLogs": [{"name": "c"}], "mystery": [{"name": "x"}]},
                "destinations": {"logAnalytics": [{"name": "dest", "workspaceResourceId": WS}]},
                "dataFlows": [{"streams": ["Microsoft-Perf"], "destinations": ["dest"], "transformKql": "source | where Value > 1"}, {"streams": ["Microsoft-Event"], "destinations": ["dest"]},
                              {"streams": ["Custom-Text_CL"], "destinations": ["elsewhere"]}]}),
            row(COLLECTION, "dcr-2", properties={"destinations": {"logAnalytics": [{"name": "dest", "workspaceResourceId": OTHER_WORKSPACE}]}, "dataFlows": []})]
        self.workspace = self.handle(WORKSPACE)

    def test_the_collection_rules_that_send_to_a_workspace_are_handles_with_typed_facts(self):
        answer = ask(self.box, "data_writers", handle=self.workspace)
        self.clean(answer)
        rules = answer["collection_rules"]
        self.assertEqual(rules["total"], 1)
        self.assertEqual(rules["cols"], ["handle", "kind", "sources", "flows", "transforms", "tables"])
        handle, kind, sources, flows, transforms, tables = rules["rows"][0]
        self.assertTrue(handle.startswith("r"))
        self.assertEqual((kind, sources, flows, transforms, tables), ("Windows", {"performanceCounters": 2, "windowsEventLogs": 1, "other": 1}, 2, 1, ["Perf", "other"]))
        self.assertEqual(self.box.handles[handle].resource_type, COLLECTION)

    def test_the_resources_that_wrote_the_most_to_a_table_are_read_for_a_table_whose_reads_are_free(self):
        self.estate.sources = [{"ResourceId": MACHINE.lower(), "Bytes": 800_000_000, "Whole": 1_000_000_000},
                               {"ResourceId": ident("Microsoft.Network/virtualNetworks", "vnet-x", sub=SUB2).lower(), "Bytes": 100_000_000, "Whole": 1_000_000_000},
                               {"ResourceId": "", "Bytes": 50_000_000, "Whole": 1_000_000_000}]
        answer = ask(self.box, "data_writers", handle=self.workspace, table="Heartbeat")
        block = answer["table"]
        self.assertEqual((block["table"], block["plan"]), ("Heartbeat", "Analytics"))
        writers = block["writers"]
        self.assertEqual((writers["day"], writers["billable_gb"], writers["other_share"], writers["cols"]), ("2026-11-03", 1, 0.05, ["handle", "type", "gb", "share"]))
        first, second, third = writers["rows"]
        self.assertEqual(self.box.handles[first[0]].resource_id, MACHINE)
        self.assertEqual(first[1:], ["microsoft.compute/virtualmachines", 0.8, 0.8])
        self.assertEqual(second, [None, "microsoft.network/virtualnetworks", 0.1, 0.1])
        self.assertEqual(third, [None, None, 0.05, 0.05])
        (call,) = [c for c in self.estate.calls if c["body"] and "// meternaut:sources" in c["body"].get("query", "")]
        self.assertIn("let All = Heartbeat |", call["body"]["query"])
        self.assertEqual(call["body"]["timespan"], "2026-11-03T00:00:00Z/2026-11-04T00:00:00Z")

    def test_a_table_whose_reads_are_charged_is_not_read(self):
        ask(self.box, "data_volume", handle=self.workspace)  # the first table that is not made by the platform is t1
        answer = ask(self.box, "data_writers", handle=self.workspace, table="t1")
        self.assertEqual(answer["table"], {"table": "t1", "plan": "Basic", "writers": "not read for this plan"})
        self.assertEqual([c for c in self.estate.calls if c["body"] and "// meternaut:sources" in c["body"].get("query", "")], [])

    def test_a_table_that_the_workspace_does_not_list_is_a_bad_argument(self):
        for table_name in ("Nope", "t9"):
            self.assertEqual(ask(self.box, "data_writers", handle=self.workspace, table=table_name), {"error": "bad-arguments"}, table_name)

    def test_the_writers_of_a_table_that_cannot_be_read_are_not_visible_and_not_none(self):
        self.estate.failures["sources"] = 403
        answer = ask(self.box, "data_writers", handle=self.workspace, table="Heartbeat")
        self.assertEqual(answer["table"]["writers"], NOT_VISIBLE)
        self.assertEqual(answer["collection_rules"]["total"], 1)

    def test_collection_rules_that_cannot_be_read_are_said_so(self):
        self.estate.failures["collection"] = 500
        self.assertEqual(ask(self.box, "data_writers", handle=self.workspace)["collection_rules"], "unavailable")

    def test_any_other_resource_shows_where_it_sends_its_own_data(self):
        self.estate.settings[MACHINE.lower()] = [
            {"name": "send-all", "properties": {"workspaceId": WS, "logs": [{"category": "a", "enabled": True}, {"category": "b", "enabled": False}, {"category": "c", "enabled": True}],
                                                 "metrics": [{"category": "AllMetrics", "enabled": True}], "logAnalyticsDestinationType": "Dedicated"}},
            {"name": HOSTILE, "properties": {"storageAccountId": "/subscriptions/x/storage", "logs": [{"category": "a", "enabled": True}]}},
            {"name": "other", "properties": {"workspaceId": OTHER_WORKSPACE, "eventHubAuthorizationRuleId": "/x", "logs": []}}]
        ask(self.box, "list_resources", type=VM)
        machine = self.box.handles and next(handle for handle, resource in self.box.handles.items() if resource.resource_type == VM)
        answer = ask(self.box, "data_writers", handle=machine)
        self.clean(answer)
        self.assertEqual(answer["diagnostic_settings"]["cols"], ["logs", "metrics", "workspace", "storage", "event_hub", "partner", "own_tables"])
        rows = answer["diagnostic_settings"]["rows"]
        self.assertEqual(rows[0], [2, 1, self.workspace, False, False, False, True])
        self.assertEqual(rows[1], [1, 0, None, True, False, False, False])
        self.assertEqual(rows[2], [0, 0, "other", False, True, False, False])

    def test_diagnostic_settings_that_cannot_be_read_are_not_visible(self):
        ask(self.box, "list_resources", type=VM)
        machine = next(handle for handle, resource in self.box.handles.items() if resource.resource_type == VM)
        self.estate.failures["settings"] = 403
        self.assertEqual(ask(self.box, "data_writers", handle=machine)["diagnostic_settings"], NOT_VISIBLE)

    def test_a_table_is_for_a_workspace_only(self):
        ask(self.box, "list_resources", type=VM)
        machine = next(handle for handle, resource in self.box.handles.items() if resource.resource_type == VM)
        self.assertEqual(ask(self.box, "data_writers", handle=machine, table="Heartbeat"), {"error": "bad-arguments"})


class TheChildren(Base):
    def setUp(self):
        super().setUp()
        self.estate.deployments = [deployment("prod-chat", model="gpt-demo", capacity=50), deployment(HOSTILE.replace(" ", "-"), model="embed-demo", sku="GlobalStandard", capacity=5, tokens=1200)]
        self.account = self.handle(ACCOUNT)

    def test_the_deployments_of_an_account_are_handles_with_typed_facts_and_no_names(self):
        answer = ask(self.box, "children", handle=self.account)
        self.clean(answer)
        self.assertEqual(answer["cols"], ["handle", *tb.CHILD_COLUMNS])
        self.assertEqual((answer["total"], answer["returned"]), (2, 2))
        first, second = answer["rows"]
        self.assertEqual(first[1:], ["gpt-demo", "2026-01-01", "Standard", 50, 360, 6000, "Succeeded", "OnceNewDefaultVersionAvailable"])
        self.assertEqual(second[1:4], ["embed-demo", "2026-01-01", "GlobalStandard"])
        self.assertEqual(second[6], 1200)
        self.assertEqual(self.box.handles[first[0]].resource_type, "microsoft.cognitiveservices/accounts/deployments")

    def test_a_part_has_no_cost_of_its_own_and_says_what_it_is_part_of(self):
        child = ask(self.box, "children", handle=self.account)["rows"][0][0]
        described = ask(self.box, "describe", handle=child)
        self.assertEqual((described["part_of"], described["kind"], described["sku"]), (self.account, "gpt-demo", "Standard"))
        self.assertNotIn("cost30d", described)
        self.assertIsNone(self.box.handles[child].cost_usd_30d)
        self.assertEqual(self.box.evidence[child]["properties"]["capacity"], 50)

    def test_the_parts_are_read_once(self):
        ask(self.box, "children", handle=self.account)
        calls = len(self.calls_to("/deployments"))
        ask(self.box, "children", handle=self.account)
        self.assertEqual(len(self.calls_to("/deployments")), calls)

    def test_a_part_that_this_access_cannot_read_is_not_visible(self):
        self.estate.failures["deployments"] = 403
        self.assertEqual(ask(self.box, "children", handle=self.account), {"handle": self.account, "children": NOT_VISIBLE})

    def test_more_parts_than_fit_are_counted(self):
        self.estate.deployments = [deployment(f"d{n:02d}", model=f"model-{n:02d}", capacity=n + 1) for n in range(60)]
        answer = ask(self.box, "children", handle=self.account)
        self.assertEqual(answer["total"], 60)
        self.assertLessEqual(answer["returned"], tb.MAX_CHILDREN)
        self.assertEqual(answer["returned"] + answer.get("rows_not_shown", 0), min(60, tb.MAX_CHILDREN))
        self.assertLessEqual(len(json.dumps(answer, separators=(",", ":"))), tb.MAX_RESULT_CHARS)


class TheSplit(Base):
    METRIC = "Processed Prompt Tokens"

    def setUp(self):
        super().setUp()
        dims = [{"value": "ModelDeploymentName", "localizedValue": "x"}, {"value": "StatusCode", "localizedValue": "x"}, {"value": "Region", "localizedValue": "x"}]
        self.estate.offer(ACCOUNT, self.METRIC, "Requests")
        self.estate.definitions[ACCOUNT][0]["dimensions"] = dims
        self.estate.deployments = [deployment("prod-chat", capacity=50), deployment("test-embed", capacity=5)]
        self.account = self.handle(ACCOUNT)
        self.key = AI.lower()

    def test_the_dimensions_of_a_metric_are_in_metric_names(self):
        names = ask(self.box, "metric_names", type=ACCOUNT)["metrics"]
        self.assertEqual(names[0]["dimensions"], ["ModelDeploymentName", "StatusCode", "Region"])
        self.assertNotIn("dimensions", names[1])

    def test_a_value_that_is_the_name_of_a_part_is_its_handle_a_number_is_a_number_and_any_other_is_a_label(self):
        self.estate.splits[(self.key, self.METRIC)] = {"prod-chat": [point(5, total=100.0, maximum=60.0, average=50.0), point(6, total=200.0, maximum=90.0, average=100.0)],
                                                       "test-embed": [point(5)], "ghost-deployment": [point(7, total=5.0, maximum=5.0, average=5.0)]}
        answer = ask(self.box, "metric_split", handle=self.account, metric=self.METRIC, dimension="ModelDeploymentName")
        self.clean(answer)
        self.assertEqual((answer["unit"], answer["values"], answer["limit_reached"], answer["days"]), ("Count", 2, False, 30))
        self.assertEqual(answer["cols"], ["value", "total", "max", "avg", "days_with_data"])
        (prod, total, maximum, average, days), (ghost, *_) = answer["rows"]
        self.assertEqual((total, maximum, average, days), (300, 90, 75, 2))
        self.assertEqual(self.box.handles[prod].resource_type, "microsoft.cognitiveservices/accounts/deployments")
        self.assertEqual(ghost, "v1")  # a value with no data in the window has no row; one that no part has the name of is a label
        self.assertEqual(self.box.evidence[prod]["metrics"][self.METRIC]["total"], 300)

    def test_numbers_stay_numbers_and_the_labels_are_for_one_answer(self):
        self.estate.splits[(self.key, self.METRIC)] = {"429": [point(5, total=3.0)], "200": [point(5, total=30.0)], "swedencentral": [point(5, total=1.0)], HOSTILE: [point(5, total=2.0)]}
        answer = ask(self.box, "metric_split", handle=self.account, metric=self.METRIC, dimension="StatusCode")
        self.clean(answer)
        self.assertEqual([(line[0], line[1]) for line in answer["rows"]], [(200, 30), (429, 3), ("v2", 2), ("v1", 1)])  # the labels are in the order of the values that Azure gave

    def test_the_parts_are_read_when_the_agent_has_not_asked_for_them(self):
        self.estate.splits[(self.key, self.METRIC)] = {"test-embed": [point(5, total=1.0)]}
        answer = ask(self.box, "metric_split", handle=self.account, metric=self.METRIC, dimension="ModelDeploymentName")
        self.assertTrue(answer["rows"][0][0].startswith("r"))
        self.assertEqual(len(self.calls_to("/deployments")), 1)

    def test_a_metric_or_a_dimension_that_is_not_offered_is_refused_before_anything_is_read(self):
        before = len(self.calls_to("metrics?"))
        self.assertEqual(ask(self.box, "metric_split", handle=self.account, metric="Nope", dimension="ModelDeploymentName"), {"error": "unknown-metric"})
        self.assertEqual(ask(self.box, "metric_split", handle=self.account, metric=self.METRIC, dimension="Nope"), {"error": "bad-arguments"})
        self.assertEqual(ask(self.box, "metric_split", handle=self.account, metric="Requests", dimension="StatusCode"), {"error": "bad-arguments"})
        self.assertEqual(len(self.calls_to("metrics?")), before)

    def test_the_most_that_was_asked_for_is_said_to_have_been_reached(self):
        self.estate.splits[(self.key, self.METRIC)] = {f"v{n}": [point(5, total=float(n + 1))] for n in range(5)}
        answer = ask(self.box, "metric_split", handle=self.account, metric=self.METRIC, dimension="Region", limit=3)
        self.assertEqual((answer["values"], answer["limit_reached"]), (3, True))
        (call,) = [c for c in self.estate.calls if "$filter" in c["query"]]
        self.assertEqual((call["query"]["$filter"], call["query"]["top"]), (["Region eq '*'"], ["3"]))

    def test_a_split_that_cannot_be_read_is_unavailable(self):
        self.estate.failures["split"] = 500
        self.assertEqual(ask(self.box, "metric_split", handle=self.account, metric=self.METRIC, dimension="Region"), {"error": "unavailable"})


class TheSizesOfResources(Base):
    """The properties that give the size of a resource (its units, its bandwidth, its capacity) reach the tools as numbers, from key names as the REST reference of the network resources
    documents them. The values and the type are invented."""

    PROPERTIES = {"vpnGatewayScaleUnit": 3, "provisioningState": "Succeeded", "connectionConfigurations": [{"name": "a", "properties": {"addressPool": {"addressPrefixes": ["10.0.0.0/24"]}}}, {"name": "b"}],
                  "virtualRouterAutoScaleConfiguration": {"minCapacity": 2}, "serviceProviderProperties": {"bandwidthInMbps": 200}, "autoscaleConfiguration": {"minCapacity": 2, "maxCapacity": 5},
                  "frontendIPConfigurations": [{}, {}, {}], "rules": [{"properties": {"timeoutInMinutes": 4, "enableFloatingIP": False}}], "threatIntelMode": "Alert",
                  "provisionedBandwidthInGbps": 10.5, "throughputUnits": 4}

    def test_the_units_the_bandwidth_and_the_capacity_are_shown_and_the_lists_are_counted(self):
        found = dict(tb.typed_properties(self.PROPERTIES))
        wanted = {"vpnGatewayScaleUnit": 3, "virtualRouterAutoScaleConfiguration.minCapacity": 2, "serviceProviderProperties.bandwidthInMbps": 200, "autoscaleConfiguration.maxCapacity": 5,
                  "frontendIPConfigurationsCount": 3, "connectionConfigurationsCount": 2, "provisionedBandwidthInGbps": 10.5, "throughputUnits": 4}
        self.assertEqual({key: found[key] for key in wanted}, wanted)
        self.assertEqual(found["provisioningState"], "Succeeded")
        self.assertNotIn("threatIntelMode", found)  # a text is shown only under the keys of an enumeration that the toolbox lists
        self.assertNotIn("connectionConfigurations.properties.addressPool.addressPrefixes", found)  # an address is never shown

    def test_a_listing_can_order_such_resources_by_their_size(self):
        kind = "microsoft.network/sizedthings"
        self.estate.rows = [row(kind, "small", properties={"vpnGatewayScaleUnit": 1}), row(kind, "large", properties={"vpnGatewayScaleUnit": 5}),
                            row(kind, "middle", properties={"vpnGatewayScaleUnit": 2})]
        self.estate.cost_rows = [(SUB, 90.0, self.estate.rows[0]["id"].lower(), "Networking"), (SUB, 10.0, self.estate.rows[1]["id"].lower(), "Networking")]
        answer = ask(self.box, "list_resources", type=kind, order_by="count")
        place = answer["cols"].index("vpnGatewayScaleUnit")
        self.assertEqual([line[place] for line in answer["rows"]], [5, 2, 1])
        self.assertEqual([line[place] for line in ask(self.box, "list_resources", type=kind, order_by="cost")["rows"]], [1, 5, 2])


class TheCommitments(Base):
    def setUp(self):
        super().setUp()
        self.estate.models = [(SUB, "OnDemand", "Usage", 1200.0), (SUB, "SavingsPlan", "Usage", 300.0), (SUB, "SavingsPlan", "Purchase", 25.5), (SUB, HOSTILE, "Usage", 1.0)]
        self.estate.benefits["P1Y"] = [{"properties": {"armSkuName": "Compute_Savings_Plan", "term": "P1Y", "lookBackPeriod": "Last30Days", "commitmentGranularity": "Hourly", "currencyCode": "USD",
                                                       "costWithoutBenefit": 1000.0, "recommendationDetails": {"commitmentAmount": 1.5, "coveragePercentage": 70.0,
                                                                                                               "averageUtilizationPercentage": 98.0, "savingsAmount": 120.0}}}]
        self.estate.benefits["P3Y"] = [{"properties": {"armSkuName": "Compute_Savings_Plan", "term": "P3Y", "currencyCode": "USD", "recommendationDetails": {"savingsAmount": 300.0}}}]
        self.estate.reservations = [{"sku": "Standard_D2s_v3", "properties": {"term": "P1Y", "lookBackPeriod": "Last30Days", "resourceType": "VirtualMachines", "recommendedQuantity": 3,
                                                                               "costWithNoReservedInstances": 500.0, "totalCostWithReservedInstances": 350.0, "netSavings": 150.0,
                                                                               "currencyCode": "USD"}}]

    def test_how_the_cost_was_paid_for_and_what_the_platform_recommends(self):
        answer = ask(self.box, "commitments")
        self.clean(answer)
        self.assertEqual((answer["window_days"], answer["basis"]), (30, "amortized"))
        (block,) = answer["subscriptions"]
        self.assertEqual(block["subscription"], "s1")
        self.assertEqual(block["paid_for"][:3], [{"pricing": "OnDemand", "charge": "Usage", "usd": 1200}, {"pricing": "SavingsPlan", "charge": "Usage", "usd": 300},
                                                 {"pricing": "SavingsPlan", "charge": "Purchase", "usd": 25.5}])
        self.assertEqual(block["paid_for"][3], {"pricing": "other", "charge": "Usage", "usd": 1})  # a word of the estate is never shown
        self.assertEqual([plan["term"] for plan in block["savings_plan"]], ["P3Y", "P1Y"])  # the largest saving first
        self.assertEqual(block["savings_plan"][1], {"sku": "Compute_Savings_Plan", "term": "P1Y", "lookback": "Last30Days", "granularity": "Hourly", "commitment_per_hour": 1.5, "coverage": 70,
                                                    "average_use": 98, "saving": 120, "cost_without": 1000, "currency": "USD"})
        self.assertEqual(block["reservation"], [{"sku": "Standard_D2s_v3", "term": "P1Y", "lookback": "Last30Days", "resource_type": "VirtualMachines", "quantity": 3, "cost_without": 500,
                                                 "cost_with": 350, "saving": 150, "currency": "USD"}])

    def test_the_reads_are_the_amortized_cost_and_the_recommendations_for_both_terms(self):
        ask(self.box, "commitments")
        (cost,) = [c for c in self.estate.calls if c["body"] and c["body"].get("type") == "AmortizedCost"]
        self.assertEqual([g["name"] for g in cost["body"]["dataset"]["grouping"]], ["PricingModel", "ChargeType"])
        self.assertEqual(cost["headers"].get("ClientType"), "Meternaut")
        terms = sorted(c["query"]["$filter"][0].split("term eq ")[1] for c in self.calls_to("benefitrecommendations"))
        self.assertEqual(terms, ["'P1Y'", "'P3Y'"])
        self.assertEqual(len(self.calls_to("reservationrecommendations")), 1)

    def test_a_part_that_this_access_cannot_read_is_not_visible_and_the_others_are_still_read(self):
        self.estate.failures.update(benefits=403, reservations=403)
        (block,) = ask(self.box, "commitments")["subscriptions"]
        self.assertEqual((block["savings_plan"], block["reservation"]), (NOT_VISIBLE, NOT_VISIBLE))
        self.assertEqual(block["paid_for"][0]["usd"], 1200)

    def test_a_part_that_failed_for_another_reason_is_unavailable(self):
        self.estate.failures["models"] = 500
        (block,) = ask(self.box, "commitments")["subscriptions"]
        self.assertEqual((block["paid_for"], block["reservation"][0]["saving"]), ("unavailable", 150))

    def test_a_cost_that_is_not_in_us_dollars_is_not_shown(self):
        self.estate.currency = "EUR"
        (block,) = ask(self.box, "commitments")["subscriptions"]
        self.assertEqual(block["paid_for"], "unavailable")
        self.assertTrue(any("not in US dollars" in note for note in self.notes))

    def test_a_second_ask_reads_nothing_again(self):
        ask(self.box, "commitments")
        calls = len(self.estate.calls)
        ask(self.box, "commitments")
        self.assertEqual(len(self.estate.calls), calls)

    def test_a_call_that_has_used_its_time_leaves_the_other_subscriptions_for_the_next_one(self):
        self.estate.models += [(SUB2, "OnDemand", "Usage", 7.0)]
        clock = type("Clock", (), {"now": 0.0, "__call__": lambda self: self.now})()
        box = toolbox(self.estate, subscriptions=(SUB, SUB2))
        box.monotonic, box.read_seconds, box.read_workers = clock, 5.0, 1
        self.estate.on_cost = lambda: setattr(clock, "now", clock.now + 10.0)
        first = ask(box, "commitments")
        self.assertEqual([b["subscription"] for b in first["subscriptions"]], ["s1"])
        self.assertEqual(first["not_read"]["count"], 1)
        clock.now = 0.0
        second = ask(box, "commitments")
        self.assertEqual([b["subscription"] for b in second["subscriptions"]], ["s1", "s2"])
        self.assertEqual(second["subscriptions"][1]["paid_for"], [{"pricing": "OnDemand", "charge": "Usage", "usd": 7}])


class TheHistory(Base):
    def setUp(self):
        super().setUp()
        day = dt.date
        self.estate.daily = [(SUB, day(2026, 10, 20), WS.lower(), 3.0), (SUB, day(2026, 10, 21), WS.lower(), 4.5), (SUB, day(2026, 10, 21), AI.lower(), 9.0),
                             (SUB, day(2026, 10, 22), ident("Microsoft.OperationalInsights/workspaces", "ws-gone").lower(), 1.0), (SUB, day(2026, 11, 4), WS.lower(), 99.0)]
        self.workspace = self.handle(WORKSPACE)

    def test_one_resource_by_day_oldest_first(self):
        answer = ask(self.box, "cost_history", handle=self.workspace)
        self.assertEqual((answer["basis"], answer["days"], answer["from"], answer["to"]), ("actual", 30, "2026-10-05", "2026-11-03"))
        self.assertEqual((answer["total"], answer["days_with_cost"], len(answer["daily"])), (7.5, 2, 30))
        self.assertEqual((answer["daily"][15], answer["daily"][16], sum(answer["daily"])), (3, 4.5, 7.5))  # the open day is not in it
        self.assertEqual(self.box.evidence[self.workspace]["metrics"]["Cost actual USD 30d"],
                         {"total": 7.5, "max": 4.5, "average": 3.75, "days_with_data": 2, "days": 30, "unit": "USD", "totals": [7.5]})

    def test_the_read_asks_for_the_resource_by_its_id_and_a_type_by_the_type(self):
        ask(self.box, "cost_history", handle=self.workspace, days=7, basis="amortized")
        (call,) = [c for c in self.estate.calls if c["body"] and c["body"].get("dataset", {}).get("granularity") == "Daily"]
        self.assertEqual(call["body"]["type"], "AmortizedCost")
        self.assertEqual(call["body"]["dataset"]["filter"]["dimensions"], {"name": "ResourceId", "operator": "In", "values": [WS]})
        self.assertEqual(call["body"]["timePeriod"], {"from": "2026-10-28T00:00:00Z", "to": "2026-11-03T23:59:59Z"})
        ask(self.box, "cost_history", type=ACCOUNT)
        last = self.calls_to("costmanagement/query")[-1]
        self.assertEqual(last["body"]["dataset"]["filter"]["dimensions"], {"name": "ResourceType", "operator": "In", "values": [ACCOUNT]})

    def test_a_type_gives_the_days_of_all_its_resources_and_the_dearest_with_their_totals(self):
        answer = ask(self.box, "cost_history", type=WORKSPACE, days=60)
        self.assertEqual((answer["type"], answer["days"], answer["total"], answer["resources_total"]), (WORKSPACE, 60, 8.5, 2))
        self.assertEqual(answer["resources"], [[self.workspace, 7.5], [None, 1]])  # a resource that is not in the estate any more has no handle
        self.assertNotIn("handle", answer)

    def test_an_answer_is_kept_for_the_run(self):
        ask(self.box, "cost_history", handle=self.workspace)
        calls = len(self.calls_to("costmanagement/query"))
        ask(self.box, "cost_history", handle=self.workspace)
        ask(self.box, "cost_history", handle=self.workspace, basis="amortized")
        self.assertEqual(len(self.calls_to("costmanagement/query")), calls + 1)

    def test_a_handle_or_a_type_and_never_both(self):
        self.assertEqual(ask(self.box, "cost_history"), {"error": "bad-arguments"})
        self.assertEqual(ask(self.box, "cost_history", handle=self.workspace, type=WORKSPACE), {"error": "bad-arguments"})
        for days in (6, 91):
            self.assertEqual(ask(self.box, "cost_history", handle=self.workspace, days=days), {"error": "bad-arguments"}, days)
        self.assertEqual(ask(self.box, "cost_history", handle=self.workspace, basis="forecast"), {"error": "bad-arguments"})
        self.assertEqual(ask(self.box, "cost_history", handle="r77"), {"error": "unknown-handle"})

    def test_a_cost_that_cannot_be_read_is_unavailable(self):
        self.estate.failures["daily"] = 403
        self.assertEqual(ask(self.box, "cost_history", handle=self.workspace), {"error": "unavailable"})

    def test_a_cost_that_is_not_in_us_dollars_is_not_shown(self):
        self.estate.currency = "EUR"
        self.assertEqual(ask(self.box, "cost_history", handle=self.workspace), {"error": "unavailable"})
        self.assertTrue(any("not in US dollars" in note for note in self.notes))

    def test_a_type_with_no_resources_has_no_cost(self):
        answer = ask(self.box, "cost_history", type="microsoft.compute/disks")
        self.assertEqual((answer["total"], answer["days_with_cost"], answer["resources"], answer["resources_total"]), (0, 0, [], 0))


if __name__ == "__main__":
    unittest.main()
