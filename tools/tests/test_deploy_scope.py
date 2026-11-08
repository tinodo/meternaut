"""What the deployment identity touches: the project's own resource group, and nothing outside it (AGENTS.md rule 18, rule 15 (c)).

On 2026-11-07 the owner ordered the undo of what Meternaut had added to his API Management instance, and the Hub's actions that made those objects were removed. What is left of the
workflow, the templates and the tools that the Hub runs reads and writes in the project's own resource group only, so the custom role that the deployment identity held in the
resource group of that instance, *Meternaut gateway deployer*, is used by nothing and is retired (item W8 of environment/access-requirements.json).

These tests read the files and call nothing. They are the evidence for that sentence, and the guard against the next step that reads somewhere else: a new kind of call, an id of another
subscription or group, or a template that reads a resource outside its own group, fails here, and whoever adds it has to say why the deployment identity needs a right there."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


WORKFLOW = text(".github/workflows/deploy-hub.yml")
CHECKS = text(".github/workflows/checks.yml")
BOOTSTRAP = text("environment/BOOTSTRAP.md")
PROJECT_GROUP = r"/subscriptions/\$ENV_SUBSCRIPTION_ID/resourceGroups/\$ENV_RESOURCE_GROUP"
TEMPLATES = sorted((ROOT / "environment").rglob("*.bicep")) + sorted((ROOT / "infra" / "budgets").glob("*.bicep"))


def code_lines(source: str):
    """(number, line) of every line that is not a comment."""
    return [(n, line) for n, line in enumerate(source.splitlines(), 1) if not line.lstrip().startswith("#")]


def commands(source: str):
    """Every shell command of the workflow with its continuation lines joined, as (number of its first line, the command)."""
    found, current, start = [], "", 0
    for number, line in code_lines(source):
        stripped = line.strip()
        if not current:
            start = number
        current += " " + stripped.rstrip("\\").strip() if current else stripped.rstrip("\\").strip()
        if not stripped.endswith("\\"):
            found.append((start, current))
            current = ""
    return found


class TheWorkflowTouchesOnlyTheProjectsGroup(unittest.TestCase):
    def test_every_resource_id_that_the_workflow_builds_is_in_the_project_subscription_and_group(self):
        problems = []
        for number, line in code_lines(WORKFLOW):
            if "/subscriptions/" not in line:
                continue
            rest = re.sub(PROJECT_GROUP, "", line)
            if "/subscriptions/" in rest and not re.search(r"grep -Eq? '\^/subscriptions/", rest):
                problems.append(f"line {number}: {line.strip()[:160]}")
        self.assertEqual(problems, [], "an id of another subscription or group: the deployment identity holds no right there (the checks of an id with grep -Eq are the only other use)")

    def test_every_subscription_that_the_workflow_names_is_the_projects(self):
        found = [(n, m.group(1)) for n, line in code_lines(WORKFLOW) for m in re.finditer(r"--subscription\s+(\S+)", line)]
        self.assertGreater(len(found), 10, "the calls of the tools name the subscription")
        self.assertEqual([x for x in found if x[1] != '"$ENV_SUBSCRIPTION_ID"'], [])
        for number, line in code_lines(WORKFLOW):
            self.assertNotRegex(line, r"az account set|--tenant-id\s+\S*[0-9a-f]{8}-", f"line {number}")

    def test_the_only_kinds_of_az_call_are_the_ones_that_were_looked_at_and_each_names_the_project_group_or_an_id_built_from_it(self):
        heads = {}
        for number, command in commands(WORKFLOW):
            if command.startswith("echo ") or " az " not in " " + command:
                continue
            for match in re.finditer(r"(?<![\w./-])az ((?:[a-z][a-z-]*)(?: [a-z][a-z-]*)?(?: [a-z][a-z-]*)?)", command):
                words = match.group(1).split()
                head = " ".join(words[:2])
                if words[0] == "network":
                    head = " ".join(words[:3]) if words[1] == "private-endpoint" and words[2] == "list" else " ".join(words[:4])
                heads.setdefault(head, []).append(number)
        allowed = {"bicep build", "bicep lint", "rest", "resource list", "resource delete", "group show", "provider show", "role assignment",
                   "network private-endpoint list", "network private-endpoint dns-zone-group", "functionapp deployment"}  # functionapp deployment: the Teams bot's publish, the one app that is public
        self.assertEqual({head for head in heads if head not in allowed}, set(),
                         "a new kind of az call (for example az identity, az apim, az monitor or az ad): say which resource group it reads and why the deployment identity may, and add it here")

    def test_every_az_call_that_lists_or_shows_names_the_project_group(self):
        for number, command in commands(WORKFLOW):
            for pattern, required in ((r"\baz resource list\b", r'--resource-group "\$ENV_RESOURCE_GROUP"'), (r"\baz network private-endpoint (?:dns-zone-group )?list\b", r'--resource-group "\$ENV_RESOURCE_GROUP"'),
                                      (r"\baz group show\b", r'--name "\$ENV_RESOURCE_GROUP"')):
                if re.search(pattern, command) and not command.lstrip().startswith("echo"):
                    self.assertRegex(command, required, f"line {number}: {command[:160]}")

    def test_every_call_of_az_rest_goes_to_an_id_built_from_the_project_group_or_to_a_variable_that_was_built_from_it(self):
        urls = [(n, m.group(1)) for n, command in commands(WORKFLOW) for m in re.finditer(r"az rest .*?--url\s+(\S+)", command)]
        self.assertGreater(len(urls), 20)
        for number, url in urls:
            ok = (re.fullmatch(r'"https://management\.azure\.com\$\{\w+\}[^"]*"', url) or re.fullmatch(r'"https://management\.azure\.com' + PROJECT_GROUP + r'/[^"]*"', url)
                  or re.fullmatch(r'"\$url"', url))
            self.assertTrue(ok, f"line {number}: {url}")
            self.assertNotRegex(url, r"/tenants/|/providers/Microsoft\.(?:Management|ApiManagement/service|Insights/components)/|managementGroups", f"line {number}")

    def test_no_variable_of_the_job_names_something_outside_the_project_any_more(self):
        # The last one was the secret GATEWAY_APPINSIGHTS_ID, which the builder read for the usage recording's copy jobs (they read the old gateway's Application Insights). The recording was removed on
        # 2026-11-07, nothing reads the secret, and the owner deletes it in his repository settings.
        for name in ("GATEWAY_APPINSIGHTS_ID", "GATEWAY_RESOURCE_ID", "GATEWAY_PRINCIPAL_ID", "GATEWAY_CLIENT_ID", "RECORDING_FRAGMENTS", "RECORDING_READER_IDS", "GATEWAY_URL", "GATEWAY_PRODUCT_SUBSCRIPTION_ID"):
            self.assertNotIn(name, WORKFLOW)
            self.assertNotIn(name, CHECKS)
        builder = text("tools/environment-params.py")
        for name in ("GATEWAY_APPINSIGHTS_ID", "GATEWAY_RESOURCE_ID", "RECORDING_READER_IDS"):
            self.assertNotIn(f'"{name}"', builder, f"{name}: the builder reads no setting of the old gateway's side")

    def test_the_builder_calls_nothing(self):
        builder = text("tools/environment-params.py")
        for word in ("import subprocess", "os.system", "urllib", "http.client", "import socket", "import requests", "os.popen"):
            self.assertNotIn(word, builder, word)

    def test_no_step_reads_the_instance_its_identity_its_loggers_or_a_contract(self):
        for word in ("Microsoft.ApiManagement/service", "apim-gateway-upgrade", "listSecrets", "loggers", "az identity list", "Meternaut gateway deployer"):
            for number, line in code_lines(WORKFLOW):
                self.assertNotIn(word, line, f"line {number}")


class TheTemplatesReadNothingOutsideTheirOwnGroup(unittest.TestCase):
    @staticmethod
    def without_strings(source: str) -> str:
        return re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("//")))

    @staticmethod
    def body_of(source: str, start: int) -> str:
        depth, i = 0, source.index("{", start)
        begin = i
        while i < len(source):
            depth += source[i] == "{"
            depth -= source[i] == "}"
            i += 1
            if depth == 0:
                return source[begin:i]
        raise AssertionError("a block that is not closed")

    def test_the_templates_are_the_ones_that_the_hub_and_the_checks_know(self):
        names = [str(p.relative_to(ROOT)).replace("\\", "/") for p in TEMPLATES]
        self.assertEqual(names, ["environment/aigateway/main.bicep", "environment/aigateway/subnet.bicep", "environment/aigateway/telemetry.bicep", "environment/base/main.bicep", "environment/cases/main.bicep",
                                 "environment/cases/planted.bicep", "environment/foundry/main.bicep", "environment/governance/main.bicep", "environment/main.bicep", "environment/operator/main.bicep",
                                 "environment/teams/main.bicep",
                                 "infra/budgets/rg-budget.bicep"], "a new template is added to this list on purpose, after it was looked at for what it reads")
        for name in (n for n in names if n.startswith("environment/")):
            if name == "environment/teams/main.bicep" and "          - teams\n" not in WORKFLOW:
                continue  # until the action teams is in the Hub workflow, the Teams template is built and linted by tools/tests/test_teams_template.py and not yet by a workflow (docs/proposals/13-teams-and-outlook.md)
            self.assertIn(name, WORKFLOW + CHECKS, f"{name}: a template that no workflow compiles")

    def test_no_template_reads_or_writes_in_another_group_subscription_tenant_or_management_group(self):
        for path in TEMPLATES:
            source = self.without_strings(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
            name = path.name
            self.assertNotRegex(source, r"\bresourceGroup\(\s*[^)\s]", f"{name}: resourceGroup() with a name")
            self.assertNotRegex(source, r"\bsubscription\(\s*[^)\s]", f"{name}: subscription() with an id")
            self.assertNotRegex(source, r"\bscope:\s*(?:subscription|tenant|managementGroup)\(", f"{name}: a scope above the group")
            self.assertNotRegex(source, r"\b(?:tenantResourceId|managementGroupResourceId|extensionResourceId)\(", f"{name}: an id above the group")
            self.assertNotRegex(source, r"\b(?:reference|list[A-Z]\w*)\(", f"{name}: a read of a resource at deployment time")
            self.assertEqual(set(re.findall(r"\btargetScope\s*=\s*'([^']*)'", path.read_text(encoding="utf-8"))) - {"resourceGroup"}, set(), f"{name}: a template of the project's group has no other target scope")

    def test_an_existing_resource_is_in_the_group_of_the_deployment(self):
        for path in TEMPLATES:
            source = self.without_strings(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
            for match in re.finditer(r"\bresource\s+\w+\s+''\s+existing\s*=", source):
                body = self.body_of(source, match.end())
                self.assertNotRegex(body, r"(?m)^\s*scope\s*:", f"{path.name}: {source[match.start():match.end()]} reads in another scope")

    def test_a_role_id_is_the_only_thing_that_is_built_from_the_subscription(self):
        for path in TEMPLATES:
            original = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            for match in re.finditer(r"subscriptionResourceId\(\s*([^,)]+)", original):
                self.assertEqual(match.group(1).strip(), "'Microsoft.Authorization/roleDefinitions'", f"{path.name}: {match.group(0)}")

    def test_the_old_gateways_telemetry_is_named_by_no_template(self):
        # The usage recording's template read the old gateway's Application Insights component in the owner's lab subscription, by three parameters; it was removed on 2026-11-07.
        for template in TEMPLATES:
            source = template.read_text(encoding="utf-8")
            self.assertNotIn("gatewayAppInsights", source, str(template))
            self.assertNotIn("GATEWAY_APPINSIGHTS_ID", source, str(template))


class TheRoleIsRetired(unittest.TestCase):
    def test_the_bootstrap_page_no_longer_gives_the_role_and_says_how_it_is_retired(self):
        self.assertNotIn("--role 'Meternaut gateway deployer'", BOOTSTRAP)
        self.assertNotIn("az role definition create --role-definition", BOOTSTRAP.split("## Added on 2026-11-04 for the usage recording")[0])
        section = BOOTSTRAP.split("## The custom role (no longer used)\n")[1].split("\n## ")[0]
        for words in ("it is the item W8 of [`access-requirements.json`](access-requirements.json)", "`python tools/access-requirements.py retire --only W8 --gateway <resource id of the API Management instance>`",
                      "a dry run first", "It deletes no identity", "no Hub action, template or tool of the repository reads or writes anything outside the project's own resource group"):
            self.assertIn(words, " ".join(section.split()), words)

    def test_the_file_retires_it_the_way_it_retired_the_key_reader(self):
        manifest = json.loads(text("environment/access-requirements.json"))
        retired = {item["id"]: item for item in manifest["retired"]}
        self.assertEqual((retired["W7"]["place"], retired["W8"]["place"]), ("gatewayGroup", "gatewayGroup"))
        self.assertEqual(retired["W8"]["role"], "Meternaut gateway deployer")
        self.assertNotIn("replacedBy", retired["W8"])
        self.assertNotIn("Meternaut gateway deployer", manifest["roles"])

    def test_the_change_log_says_that_nothing_reads_outside_the_group_and_that_a_person_retires_the_role(self):
        top = text("CHANGELOG.md").split("\n## ")
        entry = " ".join(next(part for part in top if part.startswith("The undo of what Meternaut added to the owner's API Management instance, part 2")).split())
        for words in ("*Meternaut gateway deployer*", "item W8", "`python tools/access-requirements.py retire --only W8`", "tools/tests/test_deploy_scope.py",
                      "no Hub step and no template reads or writes outside the project's own resource group"):
            self.assertIn(words, entry, words)


if __name__ == "__main__":
    unittest.main()
