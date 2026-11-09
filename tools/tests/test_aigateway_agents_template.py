"""The connection of the Foundry project to the AI Gateway (environment/foundry/main.bicep), step 2 of docs/proposals/08-ai-gateway.md: what it is, what it is not, where it is written and
that nothing is made while the host name of the gateway is empty.

The shape is the one of Microsoft's own samples (category ApiManagement with the project's managed identity, an audience and empty credentials) pointed at the AI Gateway, and it has not been tried: the
tests pin what the template says, and the comment of the template says what is not known. No test calls Azure."""
import importlib.util
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "environment" / "foundry" / "main.bicep").read_text(encoding="utf-8").replace("\r\n", "\n")
CODE = re.sub(r"(?m)^\s*//.*$", "", SOURCE)
CHECK_SPEC = importlib.util.spec_from_file_location("aigateway_check_of_the_agents_template_tests", ROOT / "tools" / "aigateway-check.py")
CHECK = importlib.util.module_from_spec(CHECK_SPEC)
CHECK_SPEC.loader.exec_module(CHECK)


def resource(name):
    match = re.search(rf"(?ms)^resource {name} '([^'@]+)@([^']+)'(?: existing)? = (.*?)^\}}\n", SOURCE)
    assert match, name
    return match.group(1), match.group(2), match.group(3)


def depends_on(body):
    match = re.search(r"^  dependsOn: \[\n(.*?)^  \]", body, re.M | re.S)
    return set(re.findall(r"\w+", match.group(1))) if match else set()


KIND, VERSION, BODY = resource("aiGatewayConnection")


class TheConnectionIsWhatTheSamplesWriteForTheProjectsIdentity(unittest.TestCase):
    def test_it_is_a_connection_of_the_project_at_the_version_of_the_connection_for_traces_and_only_while_a_host_is_given(self):
        self.assertEqual((KIND, VERSION), ("Microsoft.CognitiveServices/accounts/projects/connections", "2026-09-01"))
        self.assertEqual(resource("tracesConnection")[:2], (KIND, VERSION), "the version that is in use already")
        self.assertTrue(BODY.startswith("if (!empty(aiGatewayHost)) {\n"), "nothing is made while the host name is empty")
        for line in ("  parent: project\n", "  name: aiGatewayConnectionName\n"):
            self.assertIn(line, BODY)

    def test_the_properties_are_pinned_line_for_line(self):
        properties = re.search(r"(?ms)^  properties: \{\n(.*?)^  \}\n", BODY).group(1)
        self.assertEqual([line.strip() for line in properties.splitlines() if not line.strip().startswith("#")], [
            "category: 'ApiManagement'",
            "target: 'https://${aiGatewayHost}/default/models/openai/v1'",
            "authType: 'ProjectManagedIdentity'",
            "audience: 'https://azure-api.net/aigateway'",
            "isSharedToAll: false",
            "credentials: {}",
            "metadata: {",
            "deploymentInPath: 'false'",
            "models: string(aiGatewayModelList)",
            "}",
        ])
        self.assertEqual(len(re.findall(r"#disable-next-line BCP036\n    authType:", BODY)), 1, "the same warning that the connection for traces switches off, on that line alone")
        self.assertEqual(len(re.findall(r"#disable-next-line BCP037\n    audience:", BODY)), 1)
        self.assertEqual(BODY.count("#disable-next-line"), 2)

    def test_the_target_is_the_base_of_the_route_that_the_check_of_the_gateway_calls_and_the_audience_is_the_one_that_it_asks_a_token_for(self):
        self.assertEqual(CHECK.CHAT_PATH, "/default/models/openai/v1/chat/completions")
        self.assertIn("target: 'https://${aiGatewayHost}" + CHECK.CHAT_PATH.removesuffix("/chat/completions") + "'", BODY, "the Agent Service adds chat/completions, as Learn says")
        self.assertIn(f"audience: '{CHECK.AUDIENCE}'", BODY)
        self.assertNotIn("responses", BODY.lower(), "Responses routing is not offered for this service yet (Learn): the agents use Chat Completions, and the template does not ask for Responses")

    def test_the_models_are_listed_statically_with_the_alias_as_the_name_and_the_model_and_its_version_in_it(self):
        model_list = re.search(r"(?ms)^var aiGatewayModelList = \[for model in aiGatewayModels: \{\n(.*?)^\}\]\n", SOURCE).group(1)
        self.assertEqual([line.strip() for line in model_list.splitlines()],
                         ["name: model.name", "properties: {", "model: {", "name: model.name", "version: model.version", "format: 'OpenAI'", "}", "}"])
        self.assertIn("deploymentInPath: 'false'", BODY, "the model goes in the request body, where the gateway reads the alias")

    def test_the_metadata_holds_these_two_keys_and_nothing_else(self):
        metadata = re.search(r"(?ms)^    metadata: \{\n(.*?)^    \}\n", BODY).group(1)
        self.assertEqual(re.findall(r"(?m)^      (\w+):", metadata), ["deploymentInPath", "models"])

    def test_no_key_and_no_secret_is_in_it_and_the_only_credentials_are_empty(self):
        self.assertEqual(re.findall(r"credentials[^\n]*", CODE), ["credentials: {}"], "one place, and it is empty: the project's identity is the credential (AGENTS.md rule 23)")
        for word in ("ApiKey", "apiKey", "api-key", "authHeader", "key:", "@secure", "listKeys", "listSecrets", "secret", "password", "ConnectionString", "OAuth", "ModelGateway", "AAD'"):
            self.assertNotIn(word, BODY, word)
        for name in ("aiGatewayHost", "aiGatewayModels", "aiGatewayConnectionName"):
            self.assertNotIn("@secure", re.search(rf"(?ms)(.{{0,200}})^param {name} ", SOURCE).group(1), name)

    def test_it_is_not_shared_with_the_other_projects_of_the_resource(self):
        self.assertIn("isSharedToAll: false", BODY)
        self.assertNotIn("isSharedToAll: true", CODE)


class TheOrderOfTheWritesIsKept(unittest.TestCase):
    def test_it_is_written_after_the_connection_for_traces_and_the_private_endpoint_after_it(self):
        self.assertEqual(depends_on(BODY), {"tracesConnection"}, "one write to the resource at a time: after the connection for traces, which comes after the role that its identity needs")
        self.assertIn("projectPublishesTraces", depends_on(resource("tracesConnection")[2]))
        self.assertTrue({"modelDeployment", "project", "tracesConnection", "aiGatewayConnection"} <= depends_on(resource("privateEndpoint")[2]), "the private endpoint after every other write to the resource")
        self.assertIn("privateEndpoint", depends_on(resource("casesMayUseTheAgents")[2]))
        self.assertLess(SOURCE.index("resource aiGatewayConnection"), SOURCE.index("resource privateEndpoint"), "and it is written first in the file too")

    def test_nothing_else_is_written_to_the_resource_beside_it(self):
        names = re.findall(r"(?m)^resource (\w+) '", SOURCE)
        written = {name for name in names if re.search(r"^  (parent|scope): (account|project)$", resource(name)[2], re.M)}
        roles = {"casesMayUseTheAgents", "operatorMayCheckTheAgents", "projectMayRunTheEvaluationRule"}
        self.assertEqual(written, {"aiGatewayConnection", "guardrail", "modelDeployment", "project", "tracesConnection"} | roles)

        def before(name, seen):
            body = re.sub(r"(?m)^\s*//.*$", "", resource(name)[2])
            for other in names:
                if other != name and other not in seen and (other in depends_on(body) or re.search(rf"\b{other}\b", body)):
                    seen.add(other)
                    before(other, seen)
            return seen

        earlier = before("privateEndpoint", set())
        self.assertEqual(sorted(written - roles - earlier), [], "every write to the resource but the roles is before the private endpoint")
        for role in sorted(roles):
            self.assertIn("privateEndpoint", before(role, set()), f"and {role} is after it")

    def test_the_header_says_so(self):
        header = SOURCE.split("targetScope = ")[0]
        flat = re.sub(r"\s*\n//\s*", " ", header)
        self.assertIn("The connection to the AI Gateway is one more such write: it comes after the connection for traces (one write at a time) and before the private endpoint.", flat)
        self.assertIn("Only when the host name of the AI Gateway is given (aiGatewayHost), also a second connection of the project", flat)
        self.assertIn("Empty, which is the default, none of it is made and the template is as it was.", flat)


class NothingChangesWhileTheHostIsEmpty(unittest.TestCase):
    def test_the_three_parameters_are_optional_and_empty_by_default(self):
        self.assertRegex(SOURCE, r"(?m)^param aiGatewayHost string = ''$")
        self.assertRegex(SOURCE, r"(?m)^param aiGatewayModels array = \[\]$")
        self.assertRegex(SOURCE, r"(?m)^param aiGatewayConnectionName string = 'aigateway'$")
        self.assertRegex(SOURCE, r"(?m)^@maxLength\(253\)\nparam aiGatewayHost string = ''$")
        self.assertRegex(SOURCE, r"(?m)^@minLength\(2\)\n@maxLength\(64\)\nparam aiGatewayConnectionName string = 'aigateway'$", "the limits of a connection's name")

    def test_the_connection_and_the_role_of_the_operator_are_the_only_resources_with_a_condition_and_every_other_resource_is_declared_as_it_was(self):
        self.assertEqual(re.findall(r"(?m)^resource (\w+) '[^']+' = if ", SOURCE), ["aiGatewayConnection", "operatorMayCheckTheAgents"])
        self.assertEqual(sorted(re.findall(r"(?m)^resource (\w+) '", SOURCE)),
                         ["account", "aiGatewayConnection", "casesMayUseTheAgents", "guardrail", "insights", "modelDeployment", "operatorMayCheckTheAgents", "privateEndpoint", "project",
                          "projectMayRunTheEvaluationRule", "projectPublishesTraces", "tracesConnection"])

    def test_it_makes_no_output_of_the_connection_so_the_outputs_are_the_ones_the_workflow_reads(self):
        self.assertEqual(re.findall(r"(?m)^output (\w+) ", CODE), ["projectEndpoint", "accountName", "projectName", "guardrailName", "privateEndpointName"])

    @unittest.skipUnless(shutil.which("az") or Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe").exists(), "no Azure CLI on this machine: the workflow and the checks compile every template")
    def test_the_template_compiles_and_the_connection_is_conditional_and_after_the_other(self):
        python = Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe")
        az = [str(python), "-IBm", "azure.cli"] if python.exists() else [shutil.which("az")]
        bicep = Path.home() / ".azure" / "bin" / ("bicep.exe" if python.exists() else "bicep")
        if not bicep.exists():
            self.skipTest("no Bicep CLI on this machine")
        done = subprocess.run([*az, "bicep", "build", "--file", str(ROOT / "environment" / "foundry" / "main.bicep"), "--stdout"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        compiled = json.loads(done.stdout)
        resources = compiled["resources"].values() if isinstance(compiled["resources"], dict) else compiled["resources"]
        conditional = {r["type"]: r for r in resources if "condition" in r}
        self.assertEqual(set(conditional), {KIND, "Microsoft.Authorization/roleAssignments"}, "the connection and the role of the Operator")
        self.assertEqual(conditional["Microsoft.Authorization/roleAssignments"]["condition"], "[not(empty(parameters('operatorPrincipalId')))]")
        connection = conditional[KIND]
        self.assertEqual(connection["condition"], "[not(empty(parameters('aiGatewayHost')))]")
        self.assertEqual(connection["type"], KIND)
        properties = connection["properties"]
        self.assertEqual((properties["category"], properties["authType"], properties["audience"], properties["isSharedToAll"], properties["credentials"]),
                         ("ApiManagement", "ProjectManagedIdentity", "https://azure-api.net/aigateway", False, {}))
        self.assertEqual(set(properties["metadata"]), {"deploymentInPath", "models"})
        self.assertEqual(properties["metadata"]["deploymentInPath"], "false")
        for name, default in (("aiGatewayHost", ""), ("aiGatewayModels", []), ("aiGatewayConnectionName", "aigateway"), ("operatorPrincipalId", "")):
            self.assertEqual(compiled["parameters"][name]["defaultValue"], default, name)
        self.assertEqual(set(compiled["outputs"]), {"projectEndpoint", "accountName", "projectName", "guardrailName", "privateEndpointName"})


if __name__ == "__main__":
    unittest.main()
