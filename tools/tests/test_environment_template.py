import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Everything each template may create. AGENTS.md rule 19: in a landing zone no private DNS zone, no link to one and no
# zone group (a policy registers the endpoint's name), no peering or route by hand (the network manager does it), and
# no second API Management instance (the gateway objects go into the existing one by the kit's module).
ALLOWED = {
    "environment/main.bicep": {
        "Microsoft.Network/networkSecurityGroups",
        "Microsoft.Network/virtualNetworks",
        "Microsoft.CognitiveServices/accounts",
        "Microsoft.CognitiveServices/accounts/deployments",
        "Microsoft.Network/privateEndpoints",
        "Microsoft.Authorization/roleAssignments",
    },
    "environment/gateway/identity.bicep": {"Microsoft.ManagedIdentity/userAssignedIdentities"},
    "environment/gateway/logger.bicep": {"Microsoft.ApiManagement/service", "Microsoft.Insights/components", "Microsoft.ApiManagement/service/loggers"},
    "environment/gateway/contract.bicep": {
        "Microsoft.ApiManagement/service",
        "Microsoft.ApiManagement/service/products",
        "Microsoft.ApiManagement/service/products/apis",
        "Microsoft.ApiManagement/service/products/policies",
        "Microsoft.ApiManagement/service/subscriptions",
    },
    "infra/budgets/rg-budget.bicep": {"Microsoft.Consumption/budgets"},
}


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def resources(source):
    """Symbolic name -> (type, body) of every top-level resource of a Bicep file, loops included."""
    found = {}
    pattern = r"^resource (\w+) '([^'@]+)@[^']+' (?:existing )?= (?:\[for [^\n]*\n)?\{?\n?(.*?)^(?:\}|\}\])\n"
    for match in re.finditer(pattern, source, re.M | re.S):
        found[match.group(1)] = (match.group(2), match.group(3))
    return found


def depends_on(body):
    match = re.search(r"^  dependsOn: \[\n(.*?)^  \]", body, re.M | re.S)
    return set(re.findall(r"\w+", match.group(1))) if match else set()


class Templates(unittest.TestCase):
    def test_only_the_resource_types_of_the_design_are_declared(self):
        for path, allowed in ALLOWED.items():
            declared = {m.group(1) for m in re.finditer(r"^resource \w+ '([^'@]+)@", text(path), re.M)}
            self.assertEqual(declared, allowed, path)

    def test_the_model_side_declares_no_gateway_object_and_no_dns(self):
        source = re.sub(r"//.*", "", text("environment/main.bicep"))
        for word in ("Microsoft.ApiManagement", "privateDnsZones", "virtualNetworkPeerings", "routeTables", "privateDnsZoneGroups"):
            self.assertNotIn(word, source, word)

    def test_the_model_side_has_the_resources_and_the_order_that_a_real_deploy_needed(self):
        found = resources(text("environment/main.bicep"))
        self.assertEqual(set(found), {"nsg", "vnet", "account", "modelDeployment", "privateEndpoint", "gatewayMayCallTheModels"})
        # the private endpoint after every model deployment, the role assignment after the private endpoint
        self.assertIn("modelDeployment", depends_on(found["privateEndpoint"][1]))
        self.assertIn("privateEndpoint", depends_on(found["gatewayMayCallTheModels"][1]))

    def test_nothing_else_is_written_to_the_account_beside_the_private_endpoint(self):
        # The endpoint's connection is written to the account with an If-Match. Any other write to the account at the same
        # time makes it fail with IfMatchPreconditionFailed: a role assignment did, in an earlier deploy.
        found = resources(text("environment/main.bicep"))
        before = depends_on(found["privateEndpoint"][1])
        beside = []
        for name, (_, body) in found.items():
            if name != "privateEndpoint" and re.search(r"^  (parent|scope): account$", body, re.M):
                if name not in before and "privateEndpoint" not in depends_on(body):
                    beside.append(name)
        self.assertEqual(beside, [], f"{beside} would be written to the account while the private endpoint is")

    def test_the_account_is_private_and_has_no_keys(self):
        source = text("environment/main.bicep")
        self.assertIn("publicNetworkAccess: 'Disabled'", source)
        self.assertIn("disableLocalAuth: true", source)
        self.assertIn("versionUpgradeOption: 'NoAutoUpgrade'", source)

    def test_the_gateway_may_run_completions_and_nothing_more_on_the_account(self):
        source = text("environment/main.bicep")
        self.assertIn("var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'", source)
        self.assertEqual(len(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", source)), 1)
        self.assertIn("principalType: 'ServicePrincipal'", source)

    def test_the_logger_has_the_name_the_module_expects(self):
        self.assertIn("name: 'appinsights-logger'", text("environment/gateway/logger.bicep"))

    def test_the_two_event_hub_loggers_are_placeholders_made_one_after_the_other(self):
        source = text("environment/gateway/logger.bicep")
        for name in ("usage-eventhub-logger", "pii-usage-eventhub-logger"):
            self.assertIn(f"name: '{name}'", source)
        self.assertIn("var placeholderAddress = 'usage-recording-not-deployed.invalid'", source)
        self.assertEqual(re.findall(r"endpointAddress: (\S+)", source), ["placeholderAddress", "placeholderAddress"])
        self.assertEqual(source.count("loggerType: 'azureEventHub'"), 2)
        found = resources(source)
        self.assertEqual(set(found), {"apim", "appInsights", "logger", "usageLogger", "piiUsageLogger"})
        # the service takes one write to the instance at a time
        self.assertEqual(depends_on(found["usageLogger"][1]), {"logger"})
        self.assertEqual(depends_on(found["piiUsageLogger"][1]), {"usageLogger"})

    def test_no_policy_of_ours_includes_the_fragments_whose_loggers_are_placeholders(self):
        policy = text("environment/gateway/contract-policy.xml")
        for fragment in ("ai-usage", "pii-state-saving"):
            self.assertNotIn(f'fragment-id="{fragment}"', policy)

    def test_the_gateway_identity_template_makes_only_the_identity(self):
        self.assertIn("param identityName string = 'id-meternaut-gateway'", text("environment/gateway/identity.bicep"))

    def test_the_contract_is_a_published_product_that_needs_a_key_and_has_one_subscription(self):
        source = text("environment/gateway/contract.bicep")
        for line in ("subscriptionRequired: true", "approvalRequired: true", "subscriptionsLimit: 1", "state: 'published'", "format: 'rawxml'", "scope: product.id"):
            self.assertIn(line, source)
        found = resources(source)
        self.assertEqual(set(found), {"apim", "product", "productApis", "productPolicy", "consumerSubscription"})
        # the links before the policy, the policy before the subscription: a key never works before its rules are in place
        self.assertIn("productApis", depends_on(found["productPolicy"][1]))
        self.assertIn("productPolicy", depends_on(found["consumerSubscription"][1]))

    def test_the_contract_hands_out_no_key_and_deletes_nothing(self):
        source = re.sub(r"//.*", "", text("environment/gateway/contract.bicep"))
        self.assertEqual(re.findall(r"^output (\w+)", source, re.M), ["productName", "subscriptionName"])
        for word in ("listSecrets", "primaryKey", "secondaryKey", "@secure", "Delete", "delete"):
            self.assertNotIn(word, source, word)

    def test_the_contract_takes_every_rule_from_a_parameter(self):
        source = text("environment/gateway/contract.bicep")
        for name in ("apimName", "contractName", "subscriptionName", "contractDescription", "apiNames", "policyXml"):
            self.assertRegex(source, rf"(?m)^param {name} (string|array)$")
        self.assertNotIn("loadTextContent", source)


class Workflow(unittest.TestCase):
    """Structure of the deploy workflow that its lint does not see: what may write, and when."""

    def setUp(self):
        self.text = text(".github/workflows/deploy-hub.yml")
        self.steps = re.split(r"(?m)^      - ", self.text)[1:]

    def test_the_kit_is_pinned_to_the_same_commit_in_the_deploy_workflow_and_in_the_checks(self):
        refs = []
        for path in (".github/workflows/deploy-hub.yml", ".github/workflows/checks.yml"):
            match = re.search(r"repository: Azure-Samples/ai-hub-gateway-solution-accelerator\n\s+ref: ([0-9a-f]{40})\n", text(path))
            self.assertIsNotNone(match, path)
            refs.append(match.group(1))
        self.assertEqual(refs[0], refs[1])

    def test_every_step_that_writes_to_azure_names_the_actions_it_runs_in_and_never_what_if(self):
        writers = 0
        for block in self.steps:
            if "az-deploy.py create" in block or "gateway-prep.py attach-identity" in block:
                writers += 1
                condition = re.search(r"(?m)^        if: (.+)$", block)
                self.assertIsNotNone(condition, block[:80])
                self.assertNotIn("'what-if'", condition.group(1))
                self.assertNotIn("always()", condition.group(1))
        self.assertGreaterEqual(writers, 5)

    def test_the_conditions_name_only_actions_that_the_workflow_offers(self):
        options = re.search(r"options:\n((?:          - .+\n)+)", self.text)
        self.assertIsNotNone(options)
        offered = set(re.findall(r"- (\S+)", options.group(1)))
        used = set(re.findall(r"inputs\.action == '([a-z-]+)'", self.text))
        self.assertTrue(used <= offered, used - offered)
        self.assertTrue(offered <= used, f"an action with no step of its own: {offered - used}")

    def test_the_workflow_makes_no_resource_group_no_role_and_no_dns(self):
        for word in ("az group delete", "az group create", "az role assignment", "az role definition", "privateDnsZones", "az network private-dns"):
            self.assertNotIn(word, self.text, word)

    def contract_steps(self):
        return [block for block in self.steps if "inputs.action == 'contract'" in block]

    def test_the_key_of_the_contract_is_read_masked_and_handed_to_one_command_only(self):
        (block,) = [b for b in self.steps if "listSecrets" in b]
        self.assertTrue(block.startswith("name: Test the gateway with the contract's key"))
        self.assertEqual(len(re.findall(r"listSecrets", self.text)), 1)
        self.assertLess(block.index("listSecrets"), block.index('echo "::add-mask::$key"'))
        self.assertLess(block.index('echo "::add-mask::$key"'), block.index("tools/environment-smoke.py"))
        self.assertIn('GATEWAY_SMOKE_KEY="$key" python3 tools/environment-smoke.py', block)
        # nothing keeps the key: not a secret, an output, the environment file, the summary or a file of the run
        self.assertNotRegex(block, r"(?m)^\s*export ")
        for word in ("GITHUB_ENV", "GITHUB_OUTPUT", "gh secret", "--debug", "set -x", "az account get-access-token"):
            self.assertNotIn(word, block, word)
        for line in block.splitlines():
            if "$key" in line and "add-mask" not in line and "GATEWAY_SMOKE_KEY" not in line and "key=$(" not in line:
                self.fail(f"the key is used somewhere else: {line.strip()}")
        for other in self.steps:
            if other is not block:
                self.assertNotIn("$key", other)

    def test_the_loggers_are_added_only_with_the_real_client_id_of_the_identity(self):
        (block,) = [b for b in self.steps if b.startswith("name: Add the loggers that the module expects")]
        self.assertIn("if: inputs.action == 'gateway-prepare'", block)
        self.assertLess(block.index("00000000-0000-0000-0000-000000000000"), block.index("az-deploy.py create"))
        self.assertIn("exit 1", block.split("az-deploy.py create")[0])
        settings = [b for b in self.steps if b.startswith("name: Work out the settings\n")][0]
        self.assertIn("clientId", settings)
        self.assertIn('GATEWAY_CLIENT_ID="$client"', settings)

    def test_the_contract_is_added_only_after_the_gateway_has_the_apis_it_grants(self):
        first, second = [b for b in self.steps if b.startswith("name: What the first contract would change")], self.contract_steps()
        self.assertEqual(len(first), 1)
        self.assertIn("inputs.action == 'what-if' || inputs.action == 'contract'", first[0])
        self.assertIn("run gateway first", first[0].lower().replace("::error::", ""))
        names = [re.match(r"name: (.+)", b).group(1) for b in second]
        self.assertEqual(names[:3], ["What the first contract would change in the gateway", "Add the first contract to the gateway", "Test the gateway with the contract's key"])
        order = [self.text.index(f"- name: {n}") for n in names[:3]]
        self.assertEqual(order, sorted(order))

    def test_the_limit_check_is_opt_in_and_reaches_the_script_only_through_the_environment(self):
        self.assertRegex(self.text, r"(?s)check_limits:\n\s+description: .+?\n\s+type: boolean\n\s+required: false\n\s+default: false")
        (block,) = [b for b in self.steps if "CHECK_LIMITS" in b]
        self.assertIn("CHECK_LIMITS: ${{ inputs.check_limits }}", block)
        self.assertNotIn("${{ inputs.check_limits }}", block.split("run:")[1])


if __name__ == "__main__":
    unittest.main()
