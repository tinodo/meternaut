"""The gateway's telemetry (docs/proposals/10-ai-security-and-governance.md): the exporter template environment/aigateway/telemetry.bicep, the component's OpenTelemetry ingestion in environment/base/main.bicep,
and the constant GATEWAY_TELEMETRY that connects them in tools/environment-params.py. The exporter is a template of its own because it has prerequisites that a person gives, and a missing one makes the
service refuse this one resource: it must never stop the gateway, its models or its roles."""
import importlib.util
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY = (ROOT / "environment" / "aigateway" / "telemetry.bicep").read_text(encoding="utf-8").replace("\r\n", "\n")
BASE = (ROOT / "environment" / "base" / "main.bicep").read_text(encoding="utf-8").replace("\r\n", "\n")
GATEWAY = (ROOT / "environment" / "aigateway" / "main.bicep").read_text(encoding="utf-8").replace("\r\n", "\n")
spec = importlib.util.spec_from_file_location("environment_params_of_the_telemetry", ROOT / "tools" / "environment-params.py")
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)


def code_of(source: str) -> str:
    """The text without its comment lines (a URL in the code keeps its two slashes)."""
    return re.sub(r"(?m)^\s*//.*$", "", source)


def header_of(source: str) -> str:
    return re.sub(r"\s*\n//\s*", " ", source.split("targetScope", 1)[0])


CODE = code_of(TELEMETRY)


class TheExporterTemplate(unittest.TestCase):
    def test_it_makes_one_exporter_and_reads_the_gateway_its_workspace_and_the_component(self):
        found = {m.group(1): (m.group(2), bool(m.group(3))) for m in re.finditer(r"(?m)^resource (\w+) '([^'@]+)@[^']+' (existing )?=", CODE)}
        self.assertEqual(found, {
            "gateway": ("Microsoft.ApiManagement/aigateways", True),
            "workspace": ("Microsoft.ApiManagement/aigateways/workspaces", True),
            "insights": ("Microsoft.Insights/components", True),
            "telemetryExporter": ("Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters", False),
        })
        self.assertEqual(re.findall(r"(?m)^output (\w+) ", CODE), ["exporterName"])

    def test_the_exporter_sends_with_the_gateways_own_identity_and_no_key_and_no_payload(self):
        for word in ("kind: 'OpenTelemetry'", "payloadCapture: false", "resource: 'https://monitor.azure.com'", "managedIdentity: {", "tracesEndpoint: otlp.OTLPTracesEndpoint", "logsEndpoint: otlp.OTLPLogsEndpoint",
                     "metricsEndpoint: otlp.OTLPMetricsEndpoint", "resourceId: insights.id"):
            self.assertIn(word, CODE, word)
        self.assertEqual(len(re.findall(r"payloadCapture", CODE)), 1)
        self.assertNotRegex(CODE, r"(?m)^param \w*[Pp]ayload\w* ", "no parameter can turn capture on: the service applies no redaction to a payload that is captured")
        for word in ("connectionString", "ConnectionString", "instrumentationKey", "InstrumentationKey", "'ApplicationInsights'", "headers", "apiKey", "listKeys", "listSecrets"):
            self.assertNotIn(word, CODE, f"{word}: no key (AGENTS.md rule 23)")

    def test_the_four_claims_of_the_services_preset_name_every_caller_in_the_telemetry(self):
        attributes = re.findall(r"source: \{ kind: 'claims', value: '(\w+)' \}\n\s+signals: \[([^\]]*)\]", CODE)
        self.assertEqual([(claim, re.findall(r"'(\w+)'", signals)) for claim, signals in attributes],
                         [("tid", ["logs", "traces", "metrics"]), ("oid", ["logs", "traces", "metrics"]), ("appid", ["logs", "traces"]), ("azp", ["logs", "traces"])])

    def test_the_resource_of_the_service_has_one_api_version_and_its_own_suppression_of_the_missing_types(self):
        self.assertEqual(re.findall(r"@(2025-09-01-preview)'", CODE), ["2025-09-01-preview"] * 3)
        self.assertEqual(len(re.findall(r"(?m)^#disable-next-line BCP081\nresource \w+ 'Microsoft\.ApiManagement/aigateways", TELEMETRY)), 3)
        self.assertEqual(len(re.findall(r"#disable", TELEMETRY)), 3, "no other rule is switched off")

    def test_the_names_are_the_ones_of_the_other_templates(self):
        self.assertIn("param telemetryComponentName string = 'appi-meternaut'", CODE)
        self.assertIn("name: 'appi-${workload}'", BASE)
        self.assertIn("param exporterName string = 'appinsights'", CODE, "the portal names it appinsights")
        self.assertRegex(CODE, r"(?m)^@minLength\(3\)\n@maxLength\(24\)\nparam gatewayName string$")
        self.assertEqual(ep.AIGATEWAY_NAME.pattern, r"^[a-z0-9][a-z0-9-]{1,22}[a-z0-9]$")

    def test_the_header_says_what_has_to_be_there_first_and_who_makes_it(self):
        header = header_of(TELEMETRY)
        for words in ("Made only by the action gateway-telemetry", "The resource provider Microsoft.Monitor is registered", "The component reports its OTLP endpoints", "Monitoring Metrics Publisher on that data collection rule",
                      "a person gives the role once", "A role takes up to ten minutes to apply", "must never stop the gateway, its models or its roles"):
            self.assertIn(words, header, words)

    def test_it_is_deployed_by_no_other_action_and_the_gateway_template_does_not_hold_it_any_more(self):
        for word in ("telemetryExporter", "OpenTelemetry", "payloadCapture", "monitor.azure.com"):
            self.assertNotIn(word, code_of(GATEWAY), word)
        self.assertIn("environment/aigateway/telemetry.bicep", header_of(GATEWAY))


class TheComponentsOpenTelemetryIngestion(unittest.TestCase):
    def test_the_base_takes_a_switch_and_writes_the_property_only_when_it_is_on(self):
        self.assertIn("param otlpIngestion bool = false", BASE)
        self.assertIn("AzureMonitorWorkspaceIngestionMode: 'Enabled'", BASE)
        self.assertRegex(BASE, r"\}, otlpIngestion \? \{\n\s*AzureMonitorWorkspaceIngestionMode: 'Enabled'\n\s*\} : \{\}\)")
        self.assertIn("properties: union({", BASE)
        self.assertEqual(BASE.count("AzureMonitorWorkspaceIngestionMode"), 2, "named in the description and written once")

    def test_the_component_keeps_its_entra_only_ingestion_and_its_workspace(self):
        component = re.search(r"(?ms)^resource insights 'Microsoft\.Insights/components@[^']+' = \{.*?^\}", BASE).group(0)
        for word in ("DisableLocalAuth: true", "WorkspaceResourceId: workspace.id", "Application_Type: 'web'", "IngestionMode: 'LogAnalytics'"):
            self.assertIn(word, component, word)


class TheConstantThatConnectsThem(unittest.TestCase):
    SETTINGS = {
        "ENV_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555", "ENV_RESOURCE_GROUP": "rg-example", "ENV_LOCATION": "swedencentral", "ENV_VNET_PREFIX": "10.53.0.0/24", "ENV_PE_SUBNET_PREFIX": "10.53.0.0/27",
        "ENV_DNS_SERVERS": "10.20.0.4", "ENV_OWNER": "owner@example.com", "ENV_BUDGET_AMOUNT": "25", "ENV_ALERT_EMAILS": "owner@example.com", "ENV_BUDGET_START": "2026-11-01",
        "AIGATEWAY_HOST": "aigw-meternaut-0123abcd.swedencentral.ai.gateway.azure.com",
    }

    def build(self, switch):
        models = ROOT / "environment" / "models.json"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ep, "GATEWAY_TELEMETRY", switch):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = ep.main(["build", "--models", str(models), "--out-dir", tmp], environ=self.SETTINGS)
            files = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in Path(tmp).glob("*.json")}
        return code, dict(line.split("=", 1) for line in out.getvalue().splitlines()), err.getvalue(), files

    def test_it_is_a_constant_of_the_builder_and_it_is_on(self):
        self.assertIs(ep.GATEWAY_TELEMETRY, True)
        source = (ROOT / "tools" / "environment-params.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"(?m)^GATEWAY_TELEMETRY = (True|False)$", source)), 1, "one constant, one line")

    def test_on_the_base_file_asks_for_the_ingestion_and_the_workflow_is_told(self):
        code, outputs, err, files = self.build(True)
        self.assertEqual((code, err), (0, ""))
        self.assertIs(files["base.parameters.json"]["parameters"]["otlpIngestion"]["value"], True)
        self.assertEqual(outputs["gateway_telemetry"], "true")

    def test_off_nothing_is_written_and_nothing_is_said_which_is_the_way_back(self):
        code, outputs, err, files = self.build(False)
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("otlpIngestion", files["base.parameters.json"]["parameters"])
        self.assertNotIn("gateway_telemetry", outputs)

    def test_a_switch_that_is_not_true_or_false_is_refused_by_name(self):
        for bad in ("true", 1, None):
            code, outputs, err, files = self.build(bad)
            self.assertEqual((code, files), (2, {}), bad)
            self.assertIn("GATEWAY_TELEMETRY (in tools/environment-params.py) is True or False", err)


if __name__ == "__main__":
    unittest.main()
