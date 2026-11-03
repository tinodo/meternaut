import re
import unittest
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[2] / "hub" / "main.bicep"

# Everything the template may create. AGENTS.md rule 19: in a landing zone no private DNS zone, no link to one and no
# zone group (a policy registers the endpoint's name), no peering or route by hand (the network manager does it), and
# no second API Management instance (the gateway objects go into the existing one by hub/apim).
ALLOWED_TYPES = {
    "Microsoft.Network/networkSecurityGroups",
    "Microsoft.Network/virtualNetworks",
    "Microsoft.CognitiveServices/accounts",
    "Microsoft.CognitiveServices/accounts/deployments",
    "Microsoft.Network/privateEndpoints",
    "Microsoft.Authorization/roleAssignments",
}


def resources(text):
    """Symbolic name -> (type, body) of every top-level resource of a Bicep file."""
    found = {}
    for match in re.finditer(r"^resource (\w+) '([^'@]+)@[^']+' = \{\n(.*?)^\}\n", text, re.M | re.S):
        found[match.group(1)] = (match.group(2), match.group(3))
    return found


def depends_on(body):
    match = re.search(r"^  dependsOn: \[\n(.*?)^  \]", body, re.M | re.S)
    return set(re.findall(r"\w+", match.group(1))) if match else set()


class Template(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.resources = resources(self.text)

    def test_the_resources_are_found(self):
        self.assertEqual({"nsg", "vnet", "account", "modelDeployment", "privateEndpoint", "apimMayCallTheModel"}, set(self.resources))

    def test_only_the_resource_types_of_the_design_are_declared(self):
        self.assertEqual({t for t, _ in self.resources.values()}, ALLOWED_TYPES)
        self.assertNotIn("Microsoft.ApiManagement", re.sub(r"//.*", "", self.text))

    def test_the_private_endpoint_comes_after_the_model_deployment(self):
        self.assertIn("modelDeployment", depends_on(self.resources["privateEndpoint"][1]))

    def test_the_role_assignment_comes_after_the_private_endpoint(self):
        self.assertIn("privateEndpoint", depends_on(self.resources["apimMayCallTheModel"][1]))

    def test_nothing_else_is_written_to_the_account_beside_the_private_endpoint(self):
        # The endpoint's connection is written to the account with an If-Match. Any other write to the account at the same
        # time makes it fail with IfMatchPreconditionFailed: a role assignment did, in the first deploy.
        before = depends_on(self.resources["privateEndpoint"][1])
        beside = []
        for name, (_, body) in self.resources.items():
            if name != "privateEndpoint" and re.search(r"^  (parent|scope): account$", body, re.M):
                if name not in before and "privateEndpoint" not in depends_on(body):
                    beside.append(name)
        self.assertEqual(beside, [], f"{beside} would be written to the account while the private endpoint is")


if __name__ == "__main__":
    unittest.main()
