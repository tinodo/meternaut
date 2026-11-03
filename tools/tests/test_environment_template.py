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

    def test_the_gateway_identity_template_makes_only_the_identity(self):
        self.assertIn("param identityName string = 'id-meternaut-gateway'", text("environment/gateway/identity.bicep"))


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


if __name__ == "__main__":
    unittest.main()
