"""The governance template (environment/governance/main.bicep) and what it loads: Azure Policy at the project's group, the alert rules and their action group, the workbook, the retention of two tables
(docs/proposals/10-ai-security-and-governance.md). The tests read the files and call nothing."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "environment" / "governance"
SOURCE = (DIRECTORY / "main.bicep").read_text(encoding="utf-8").replace("\r\n", "\n")
WORKBOOK_TEXT = (DIRECTORY / "ai-security.workbook.json").read_text(encoding="utf-8")
WORKBOOK = json.loads(WORKBOOK_TEXT)
ALERTS = {p.stem: p.read_text(encoding="utf-8") for p in sorted((DIRECTORY / "alerts").glob("*.kql"))}
CODE = re.sub(r"(?m)^\s*//.*$", "", SOURCE)
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
# The built-in definitions and the built-in role that the files name: ids of Azure's own catalog, the same in every tenant, and nothing of this estate.
BUILT_IN = {
    "aafe3651-cb78-4f68-9f81-e7e41509110f", "8791d062-ba96-4c34-b604-8538f7e30ca0", "5207647b-3e83-4e28-b836-c382cb5e2a2e", "67121cc7-ff39-4ab8-b7e3-95b84dab487d",
    "a6b68e3d-a1f0-4c60-8678-237c050cf4ea",
}
# The identity of the workbook's own time range parameter, which the editor of the portal gives as a GUID too: made up for this workbook, and the id of nothing in the estate.
WORKBOOK_PARAMETER_IDS = {"4d9a7c21-8e3b-4c15-a6f0-2b7e5d1c9a31"}


def parameters(source: str) -> dict[str, tuple[str, bool]]:
    return {m.group(1): (m.group(2), m.group(3) is not None) for m in re.finditer(r"(?m)^param (\w+) (\w+)( = .+)?$", source)}


def header(source: str) -> str:
    return re.sub(r"\s*\n//\s*", " ", source.split("targetScope", 1)[0])


class WhatItMakes(unittest.TestCase):
    def test_exactly_these_resources_and_the_workspace_and_the_foundry_resource_are_only_read(self):
        found = {m.group(1): (m.group(2), bool(m.group(3))) for m in re.finditer(r"(?m)^resource (\w+) '([^'@]+)@[^']+' (existing )?= ", CODE)}
        self.assertEqual(found, {
            "workspace": ("Microsoft.OperationalInsights/workspaces", True),
            "account": ("Microsoft.CognitiveServices/accounts", True),
            "approvedModels": ("Microsoft.Authorization/policyAssignments", False),
            "modelEligibility": ("Microsoft.Authorization/policyAssignments", False),
            "guardrailAudit": ("Microsoft.Authorization/policyAssignments", False),
            "customerManagedKeys": ("Microsoft.Authorization/policyAssignments", False),
            "foundryLogs": ("Microsoft.Insights/diagnosticSettings", False),
            "spansRetention": ("Microsoft.OperationalInsights/workspaces/tables", False),
            "logsRetention": ("Microsoft.OperationalInsights/workspaces/tables", False),
            "actionGroup": ("Microsoft.Insights/actionGroups", False),
            "alertRules": ("Microsoft.Insights/scheduledQueryRules", False),
            "aiSecurityWorkbook": ("Microsoft.Insights/workbooks", False),
        })

    def test_the_four_policy_assignments_audit_or_deny_carry_no_identity_and_are_enforced(self):
        assignments = re.findall(r"(?ms)^resource (\w+) 'Microsoft\.Authorization/policyAssignments@[^']+' = (?:if \(\w+\) )?\{\n(.*?)^\}", CODE)
        self.assertEqual([name for name, _ in assignments], ["approvedModels", "modelEligibility", "guardrailAudit", "customerManagedKeys"])
        for name, body in assignments:
            self.assertNotIn("identity:", body, f"{name}: Modify and DeployIfNotExists would need an identity with a role, which this project does not give")
            self.assertIn("enforcementMode: 'Default'", body, name)
            self.assertNotRegex(body, r"(?i)modify|deployIfNotExists|\bdisabled\b", name)
        self.assertEqual(re.findall(r"policy(?:Definition|SetDefinition)s/([0-9a-f-]{36})'", CODE), sorted(BUILT_IN - {"a6b68e3d-a1f0-4c60-8678-237c050cf4ea"}, key=lambda x: CODE.index(x)))
        for effect in ("approvedModelsEffect", "modelEligibilityEffect"):
            self.assertRegex(SOURCE, rf"@allowed\(\[\n  'Audit'\n  'Deny'\n\]\)\nparam {effect} string = 'Audit'", "Audit until a run has shown every deployment compliant, then Deny")

    def test_it_makes_no_exemption_no_remediation_no_role_and_no_other_scope_than_the_group(self):
        for word in ("policyExemptions", "remediations", "roleAssignments", "Microsoft.Authorization/roleDefinitions", "scope: subscription", "scope: managementGroup", "tenant()", "managementGroup(",
                     "listKeys", "listSecrets", "privateDnsZones", "privateEndpoints", "Microsoft.Network"):
            self.assertNotIn(word, CODE, word)
        header_text = header(SOURCE)
        self.assertIn("A policy exemption is not made by this template, and a test pins that.", header_text)

    def test_the_landing_zones_policies_are_read_and_never_assigned_a_second_time_and_the_header_says_so(self):
        text = header(SOURCE)
        for words in ("enforce-gr-cogserv0 and enforce-gr-openai0, enforcement DoNotEnforce", "never assigned a second time, never exempted and never bypassed", "landingZoneDiagnostics false",
                      "Defender for Cloud's AI plan is a plan of the subscription: it is read, never changed here", "Resource Policy Contributor"):
            self.assertIn(words, text, words)
        self.assertIn("resource foundryLogs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!landingZoneDiagnostics) {", CODE)

    def test_the_parameters_have_the_defaults_that_the_design_gives(self):
        declared = parameters(CODE)
        self.assertEqual(declared["approvedModelsEffect"], ("string", True))
        for name in ("owner", "alertEmails", "foundryAccountName", "approvedModelAssetIds"):
            self.assertEqual(declared[name][1], False, f"{name} has no default: the workflow gives it")
        for name, value in (("guardrailInitiative", "false"), ("auditCustomerManagedKeys", "false"), ("landingZoneDiagnostics", "false"), ("tokenLimitPerMinute", "50000"), ("requestLimitPerMinute", "60"),
                            ("nearLimitPercent", "80"), ("heartbeatHours", "26"), ("telemetryRetentionDays", "30"), ("refusalsPerHour", "3"), ("clientErrorsPerHour", "10"), ("serverErrorsPerHalfHour", "3")):
            self.assertRegex(CODE, rf"(?m)^param {name} \w+ = {value}$", name)
        self.assertRegex(CODE, r"@minValue\(4\)\n@maxValue\(31\)\nparam telemetryRetentionDays", "the tables never keep their data longer than the workspace does")
        self.assertRegex(CODE, r"@minValue\(2\)\n@maxValue\(48\)\nparam heartbeatHours")


class TheAlertRules(unittest.TestCase):
    def rules(self):
        return re.findall(r"(?m)^  \{\n    name: '([a-z-]+)'\n    display: '((?:[^'\\\n]|\\.)*)'\n    text: '((?:[^'\\\n]|\\.)*)'\n    severity: (\d)\n    frequency: '(\w+)'\n    window: '(\w+)'\n"
                          r"    operator: '(\w+)'\n    threshold: (\S+)\n    query: (\w+)\n    create: ([^\n]+)\n  \}", CODE)

    def test_one_rule_for_each_signal_and_each_is_evaluated_every_15_minutes_or_less_often(self):
        rules = self.rules()
        self.assertEqual([r[0] for r in rules], ["refusals", "client-errors", "server-errors", "near-limit", "outside-access-list", "harness-trips", "drift-fail", "drift-heartbeat", "timer-round-failed"])
        for name, _, _, severity, frequency, window, _, _, query, _ in rules:
            self.assertIn(frequency, ("PT15M", "PT30M", "PT1H"), f"{name}: the cheapest kind of log alert rule is evaluated every 15 minutes or less often (docs/proposals/10-ai-security-and-governance.md has the prices)")
            self.assertIn(severity, ("1", "2"))
            self.assertIn(window, ("PT15M", "PT30M", "PT1H", "P2D"))
        self.assertEqual(len(ALERTS), 9, "one query for each rule, and no query that no rule uses")

    def test_every_query_file_is_loaded_by_exactly_one_rule_and_every_placeholder_is_filled_by_the_template(self):
        loaded = re.findall(r"loadTextContent\('alerts/([a-z-]+)\.kql'\)", CODE)
        self.assertEqual(sorted(loaded), sorted(ALERTS))
        for name, query in ALERTS.items():
            for placeholder in set(re.findall(r"__[A-Z_]+__", query)):
                self.assertIn(f"'{placeholder}'", CODE, f"{name}: {placeholder} is not replaced by the template")
        for placeholder in set(re.findall(r"__[A-Z_]+__", WORKBOOK_TEXT)):
            self.assertIn(f"'{placeholder}'", CODE, f"the workbook's {placeholder} is not replaced by the template")

    def test_a_rule_tells_the_owner_that_something_happened_and_never_what_the_telemetry_said(self):
        # The e-mail of a rule carries its name, its description, a count and a link. The queries return ids, times and numbers, and the description is a fixed sentence.
        for name, query in ALERTS.items():
            code = "\n".join(line for line in query.splitlines() if not line.lstrip().startswith("//"))
            ending = re.findall(r"\| (project|summarize|where|print)\b", code)
            self.assertTrue(ending, name)
            for column in ("Message", "Body", "Attributes", "Name"):
                self.assertNotRegex(code.split("| project")[-1] if "| project" in code else "", rf"\b{column}\b", f"{name}: no line of the telemetry in what the query returns")
        group = re.search(r"(?ms)^resource actionGroup .*?^\}", CODE).group(0)
        self.assertEqual(re.findall(r"(\w+Receivers):", group), ["emailReceivers"], "e-mail only: no web hook, no SMS and no voice")
        self.assertIn("useCommonAlertSchema: true", group)
        for _, display, text, *_ in self.rules():
            self.assertNotRegex(text + display, r"\$\{(?!nearLimitPercent|heartbeatHours)", "the words of a rule hold a number of the rule and nothing of the estate")
        self.assertNotIn("customProperties", CODE)
        self.assertNotIn("emailSubject", CODE)

    def test_a_rule_is_one_log_alert_on_the_workspace_that_tells_the_action_group_and_only_the_heartbeat_closes_itself(self):
        rule = re.search(r"(?ms)^resource alertRules .*?^\}\]", CODE).group(0)
        for word in ("kind: 'LogAlert'", "autoMitigate: contains(statefulRules, rule.name)", "timeAggregation: 'Count'", "scopes: [\n      workspace.id\n    ]", "actionGroups: [\n        actionGroup.id\n      ]", "enabled: true",
                     "minFailingPeriodsToAlert: 1"):
            self.assertIn(word, rule, word)
        self.assertIn("var statefulRules = [\n  'drift-heartbeat'\n]", CODE, "a silence that goes on is told once when it begins and once when it ends; an event is told every time")
        self.assertIn("if (rule.create)", rule)
        self.assertIn("create: !empty(callers)", CODE, "the rule that watches for a call outside the access list needs the identities that the workflow reads")

    def test_the_heartbeat_rule_is_the_one_that_catches_a_silent_app_and_is_independent_of_it_being_alive(self):
        query = ALERTS["drift-heartbeat"]
        self.assertIn("Message startswith 'drift.pass' or Message startswith 'drift.fail'", query)
        self.assertNotIn("drift.unknown", re.sub(r"(?m)^//.*$", "", query), "an app that reports unknown for everything is alive and tells nothing: it is not counted")
        self.assertIn("__HEARTBEAT_HOURS__", query)
        self.assertIn("LinesInWindow == 0", query)
        rule = re.search(r"name: 'drift-heartbeat'.*?create: true", CODE, re.S).group(0)
        self.assertIn("window: 'P2D'", rule, "a look back of two days, with the window of the hours inside the query")
        self.assertIn("independent", re.sub(r"\s*\n//\s*", " ", query), "the query says that the control-plane check does not depend on the app")

    def test_the_lines_that_the_rules_read_have_the_two_forms_that_the_app_may_log(self):
        for name in ("harness-trips", "drift-fail", "drift-heartbeat"):
            query = ALERTS[name]
            self.assertIn("meternaut_event ", query, f"{name}: the History lines of the app are `meternaut_event {{json}}` with a type")
        self.assertIn("Message startswith 'harness.trip'", ALERTS["harness-trips"])
        self.assertIn("Message startswith 'drift.fail'", ALERTS["drift-fail"])

    def test_a_failed_timer_round_is_read_from_the_error_lines_that_the_app_logs_and_from_the_hosts_failed_invocations_of_its_timer_functions(self):
        app = ROOT / "src" / "case-functions"
        entry = (app / "function_app.py").read_text(encoding="utf-8")
        timers = re.findall(r'@app\.function_name\(name="([a-z-]+)"\)\n@app\.timer_trigger', entry)
        self.assertEqual(timers, ["watch-daily", "drift-daily", "study-weekly", "runner-tick"])
        query = re.sub(r"(?m)^//.*$", "", ALERTS["timer-round-failed"])
        self.assertIn("dynamic([" + ", ".join(f"'{name}'" for name in timers) + "])", query, "a timer function that the app gains has to be in the rule, and one that it loses has to leave it")
        self.assertIn("| where Success == false", query)
        # the words that the app logs when a round fails, and the level that it logs them at: the rule is only as good as these lines
        lines = {
            "run.py": ('LOG.error(redact(f"the run failed: ', 'history.emit("run.failed"'),
            "drift.py": ('LOG.error(redact(f"the drift check failed: ',),
            "loop.py": ('LOG.error(redact(f"the tick failed: ',),
            "study.py": ('LOG.error(redact(f"the Study failed: ', 'LOG.warning("the Study failed: %s"'),
        }
        for file, wanted in lines.items():
            text = (app / "cases" / file).read_text(encoding="utf-8")
            for words in wanted:
                self.assertIn(words, text, f"{file}: {words}")
        for prefix in ("the run failed", "the drift check failed", "the tick failed"):
            self.assertIn(f"Message startswith '{prefix}'", query, prefix)
        self.assertIn("(Message startswith 'the Study failed' and SeverityLevel >= 3)", query, "the Study logs the same words at the level Warning for one source that failed and goes on: only the error is a failed round")
        self.assertIn("""Message contains '"type":"run.failed"'""", query)

    def test_a_failed_round_is_an_event_that_is_told_every_time_hourly_and_the_drift_check_wants_the_rule_to_exist(self):
        rule = re.search(r"(?s)name: 'timer-round-failed'.*?create: true", CODE).group(0)
        for line in ("severity: 2", "frequency: 'PT1H'", "window: 'PT1H'", "operator: 'GreaterThan'", "threshold: 0", "query: timerRoundFailedQuery"):
            self.assertIn(line, rule, line)
        self.assertIn("var statefulRules = [\n  'drift-heartbeat'\n]", CODE, "an event does not close itself: a failed round is not a silence that goes on")
        self.assertIn("var timerRoundFailedQuery = loadTextContent('alerts/timer-round-failed.kql')", CODE)
        tool = (ROOT / "tools" / "drift-check.py").read_text(encoding="utf-8")
        self.assertRegex(tool, r'(?m)^ALERT_RULES = \(.*"timer-round-failed"\)$', "the check of the alert rules wants this one too, so that a drift check says when it is not made yet")


class TheTablesAndTheWorkbook(unittest.TestCase):
    def test_the_two_tables_of_the_gateways_telemetry_keep_what_the_workspace_keeps_and_nothing_is_archived(self):
        for table in ("OTelSpans", "OTelLogs"):
            body = re.search(rf"(?ms)^resource \w+ 'Microsoft\.OperationalInsights/workspaces/tables@[^']+' = \{{\n  parent: workspace\n  name: '{table}'\n(.*?)^\}}", CODE).group(1)
            self.assertIn("retentionInDays: telemetryRetentionDays", body)
            self.assertIn("totalRetentionInDays: telemetryRetentionDays", body, "no archive tier: a longer total retention is billed")

    def test_the_workbook_is_valid_and_every_query_reads_a_table_or_the_graph_and_holds_no_id_of_the_estate(self):
        self.assertEqual(WORKBOOK["version"], "Notebook/1.0")
        items = WORKBOOK["items"]
        self.assertGreaterEqual(len(items), 10)
        for item in items:
            self.assertIn(item["type"], (1, 3, 9))
        queries = [i["content"]["query"] for i in items if i["type"] == 3]
        self.assertGreaterEqual(len(queries), 8)
        joined = "\n".join(queries)
        for table in ("OTelSpans", "OTelLogs", "AppTraces", "policyresources", "scheduledqueryrules"):
            self.assertIn(table, joined if table != "scheduledqueryrules" else joined.lower(), table)
        for file_text in (WORKBOOK_TEXT, *ALERTS.values()):
            self.assertEqual({g.lower() for g in GUID.findall(file_text)} - BUILT_IN - WORKBOOK_PARAMETER_IDS, set(), "no id of the estate is in a file of the repository: the template fills the placeholders when it is deployed")

    def test_the_workbook_names_the_three_things_the_owner_asked_to_see_and_the_template_loads_it_with_the_workspace_as_its_source(self):
        text = " ".join(json.dumps(i) for i in WORKBOOK["items"])
        for words in ("heartbeat", "Azure Policy", "alert rules", "near", "harness"):
            self.assertIn(words.lower(), text.lower(), words)
        body = re.search(r"(?ms)^resource aiSecurityWorkbook .*?^\}", CODE).group(0)
        for word in ("kind: 'shared'", "sourceId: workspace.id", "category: 'workbook'", "loadTextContent('ai-security.workbook.json')", "displayName: 'Meternaut AI security'"):
            self.assertIn(word, body, word)

    def test_no_file_of_the_directory_holds_a_key_a_connection_string_or_an_estate_name(self):
        for path in DIRECTORY.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"(?i)instrumentationkey|accountkey|sharedaccess|primarykey|connectionstring", path.name)
                self.assertNotRegex(text, r"(?i)aif-meternaut-agents-|aigw-meternaut-|func-meternaut-cases-|stmeternautfn", path.name)


if __name__ == "__main__":
    unittest.main()
