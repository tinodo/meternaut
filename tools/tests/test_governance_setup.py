"""The hand steps of the AI security (tools/governance-setup.py), against a model of Azure: what it reads, what it makes and in which order, that it makes nothing that it was not asked for, that it names the
subscription in every call, and that it does not run in a pipeline."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = load("governance_setup", "governance-setup.py")
params = load("environment_params_for_governance_setup", "environment-params.py")

SUB = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-test"
IDENTITY_GROUP = "rg-identities"
DEPLOY_NAME = "id-deploy"
DEPLOY_OBJECT = "aaaaaaaa-0000-0000-0000-000000000001"
SUBJECT = "repo:someone/somewhere:ref:refs/heads/main"
GATEWAY = params.aigateway_name(SUB, GROUP)
GATEWAY_OBJECT = "bbbbbbbb-0000-0000-0000-000000000002"
RULE = f"/subscriptions/{SUB}/resourceGroups/mrg-managed/providers/Microsoft.Insights/dataCollectionRules/dcr-test"
GROUP_ID = f"/subscriptions/{SUB}/resourceGroups/{GROUP}"
NEW_OBJECT = "cccccccc-0000-0000-0000-000000000003"
NEW_CLIENT = "dddddddd-0000-0000-0000-000000000004"
WRITES = (("role", "assignment", "create"), ("provider", "register"), ("identity", "create"), ("identity", "federated-credential", "create"))


def option(arguments: list[str], name: str) -> str:
    return arguments[arguments.index(name) + 1] if name in arguments else ""


class Azure:
    """A model of the parts of Azure that the tool reads and writes: the calls go in `calls`, and the writes change the state."""

    def __init__(self):
        self.registered = {"Microsoft.Authorization", "Microsoft.Insights", "Microsoft.OperationalInsights", "Microsoft.PolicyInsights"}
        self.roles: list[tuple[str, str, str]] = []
        self.gateway_object = GATEWAY_OBJECT
        self.rule = RULE
        self.identity: dict | None = None
        self.credentials: list[str] = []
        self.calls: list[list[str]] = []
        self.failing: dict[str, str] = {}

    def writes(self) -> list[list[str]]:
        return [call for call in self.calls if any(tuple(call[:len(head)]) == head for head in WRITES)]

    def have(self, principal: str, scope: str, role: str) -> bool:
        return any(p == principal and s.lower() == scope.lower() and r == role for p, s, r in self.roles)

    def __call__(self, arguments: list[str]) -> tuple[int, str, str]:
        self.calls.append(arguments)
        text = " ".join(arguments)
        for part, message in self.failing.items():
            if part in text:
                return 1, "", message
        head = tuple(arguments[:2])
        if head == ("provider", "show"):
            name = option(arguments, "--namespace")
            return 0, ("Registered" if name in self.registered else "NotRegistered") + "\n", ""
        if head == ("provider", "register"):
            self.registered.add(option(arguments, "--namespace"))
            return 0, "", ""
        if head == ("group", "show"):
            return 0, "swedencentral\n", ""
        if head == ("rest", "--method"):
            url = option(arguments, "--url")
            if "/aigateways/" in url:
                return 0, (self.gateway_object or "None") + "\n", ""
            if "/components/" in url:
                return 0, (self.rule or "None") + "\n", ""
            return 1, "", "unknown url"
        if tuple(arguments[:3]) == ("role", "assignment", "list"):
            principal, scope = option(arguments, "--assignee-object-id"), option(arguments, "--scope")
            inherited = "--include-inherited" in arguments
            rows = []
            for p, s, r in self.roles:
                if p != principal:
                    continue
                if "--all" in arguments or s.lower() == scope.lower() or (inherited and (scope.lower().startswith(s.lower().rstrip("/") + "/") or s.startswith("/providers/Microsoft.Management/managementGroups/"))):
                    rows.append(f"{s}\t/providers/Microsoft.Authorization/roleDefinitions/{r}")
            return 0, "\n".join(rows) + ("\n" if rows else ""), ""
        if tuple(arguments[:3]) == ("role", "assignment", "create"):
            self.roles.append((option(arguments, "--assignee-object-id"), option(arguments, "--scope"), option(arguments, "--role")))
            return 0, "", ""
        if head == ("identity", "show"):
            if option(arguments, "--name") == setup.DRIFT_IDENTITY and self.identity:
                if option(arguments, "--query") == "principalId":
                    return 0, f"{self.identity['principalId']}\n", ""
                return 0, f"{self.identity['principalId']}\n{self.identity['clientId']}\n", ""
            return 1, "", "(ResourceNotFound) The Resource 'Microsoft.ManagedIdentity/userAssignedIdentities/x' under resource group 'y' was not found."
        if head == ("identity", "create"):
            self.identity = {"principalId": NEW_OBJECT, "clientId": NEW_CLIENT}
            return 0, "", ""
        if tuple(arguments[:2]) == ("identity", "federated-credential"):
            action = arguments[2]
            if action == "show":
                return 0, SUBJECT + "\n", ""
            if action == "list":
                return 0, "\n".join(self.credentials) + ("\n" if self.credentials else ""), ""
            if action == "create":
                self.credentials.append(option(arguments, "--subject"))
                return 0, "", ""
        return 1, "", "unknown command " + text


class Run:
    def __init__(self, azure: Azure | None = None):
        self.azure = azure or Azure()
        self.lines: list[str] = []
        self.errors = io.StringIO()
        self.asked: list[str] = []

    def __call__(self, *arguments: str, env=None, answer: str | None = "yes", interactive: bool = True) -> int:
        def ask(question: str) -> str:
            self.asked.append(question)
            return answer or ""

        with contextlib.redirect_stderr(self.errors):
            return setup.main(list(arguments), az=self.azure, out=self.lines.append, ask=ask, env={} if env is None else env, sleep=lambda seconds: None, interactive=interactive)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


COMMON = ("--subscription", SUB, "--resource-group", GROUP)
ALL = (*COMMON, "--deploy-principal-id", DEPLOY_OBJECT, "--identity-group", IDENTITY_GROUP, "--deploy-identity-name", DEPLOY_NAME)


class Check(unittest.TestCase):
    def test_an_estate_that_has_none_of_it_shows_every_step_as_missing_or_waiting_and_makes_nothing(self):
        run = Run()
        code = run("check", *ALL)
        self.assertEqual(code, 1)
        for words in ("G1  MISSING", "G2  MISSING    The resource provider Microsoft.Monitor is NotRegistered", "G3  MISSING", "G4  MISSING    The identity id-meternaut-drift is not there", "It would get the role Reader on the project's resource group"):
            self.assertIn(words, run.text)
        self.assertEqual(run.azure.writes(), [])
        self.assertIn("6 to make, 0 waiting for another action, 0 that a person has to look at.", run.text)

    def test_every_call_names_the_subscription_and_none_is_a_write(self):
        run = Run()
        run("check", *ALL)
        self.assertTrue(run.azure.calls)
        for call in run.azure.calls:
            self.assertIn("--subscription", call)
            self.assertEqual(option(call, "--subscription"), SUB)
        self.assertEqual(run.azure.writes(), [])

    def test_the_gateway_and_the_component_are_read_by_the_names_that_the_builder_makes(self):
        run = Run()
        run("check", *COMMON, "--step", "G3")
        urls = [option(call, "--url") for call in run.azure.calls if call[:1] == ["rest"]]
        self.assertIn(f"https://management.azure.com{GROUP_ID}/providers/Microsoft.ApiManagement/aigateways/{GATEWAY}?api-version=2025-09-01-preview", urls)
        self.assertIn(f"https://management.azure.com{GROUP_ID}/providers/Microsoft.Insights/components/appi-meternaut?api-version=2020-02-02", urls)

    def test_a_step_that_waits_for_another_action_says_which(self):
        azure = Azure()
        azure.gateway_object = ""
        run = Run(azure)
        run("check", *COMMON, "--step", "G3")
        self.assertIn("G3  WAITING    The AI Gateway has no identity yet: run the action aigateway first.", run.text)
        azure.gateway_object, azure.rule = GATEWAY_OBJECT, ""
        run = Run(azure)
        self.assertEqual(run("check", *COMMON, "--step", "G3"), 1)
        self.assertIn("run the action base (it turns the OpenTelemetry ingestion on), and wait about ten minutes", run.text)

    def test_a_read_that_fails_is_unreadable_and_never_present(self):
        azure = Azure()
        azure.failing["role assignment list"] = "(AuthorizationFailed) the client does not have authorization"
        run = Run(azure)
        self.assertEqual(run("check", *ALL, "--step", "G1"), 1)
        self.assertIn("G1  UNREADABLE", run.text)
        self.assertIn("AuthorizationFailed", run.text)

    def test_what_is_in_order_reads_as_present_and_the_exit_code_is_zero(self):
        azure = Azure()
        azure.registered.add("Microsoft.Monitor")
        azure.roles = [(DEPLOY_OBJECT, GROUP_ID, setup.RESOURCE_POLICY_CONTRIBUTOR), (GATEWAY_OBJECT, RULE, setup.MONITORING_METRICS_PUBLISHER),
                       (NEW_OBJECT, GROUP_ID, setup.READER_ROLE)]
        azure.identity = {"principalId": NEW_OBJECT, "clientId": NEW_CLIENT}
        azure.credentials = [SUBJECT]
        run = Run(azure)
        self.assertEqual(run("check", *ALL), 0, run.text)
        self.assertNotIn("MISSING", run.text)
        self.assertIn(f"gh variable set DRIFT_CLIENT_ID --body {NEW_CLIENT}", run.text)

    def test_a_policy_right_inherited_from_above_counts_and_one_on_a_resource_below_does_not(self):
        azure = Azure()
        for above in (f"/subscriptions/{SUB}", "/providers/Microsoft.Management/managementGroups/mg-of-the-estate"):
            azure.roles = [(DEPLOY_OBJECT, above, setup.OWNER_ROLE)]
            run = Run(azure)
            run("check", *ALL, "--step", "G1")
            self.assertIn("G1  present", run.text, above)
        azure.roles = [(DEPLOY_OBJECT, f"{GROUP_ID}/providers/Microsoft.Storage/storageAccounts/x", setup.RESOURCE_POLICY_CONTRIBUTOR)]
        run = Run(azure)
        run("check", *ALL, "--step", "G1")
        self.assertIn("G1  MISSING", run.text)

    def test_the_read_only_identity_may_hold_reader_and_nothing_else(self):
        azure = Azure()
        azure.identity = {"principalId": NEW_OBJECT, "clientId": NEW_CLIENT}
        azure.credentials = [SUBJECT]
        azure.roles = [(NEW_OBJECT, GROUP_ID, setup.READER_ROLE), (NEW_OBJECT, GROUP_ID, "b24988ac-6180-42a0-ab88-20f7382dd24c")]
        run = Run(azure)
        self.assertEqual(run("check", *ALL, "--step", "G4"), 1)
        self.assertIn("G4  DIFFERS    It holds 1 role assignment(s) other than Reader", run.text)

    def test_a_credential_with_another_subject_differs_and_one_that_is_missing_is_made(self):
        azure = Azure()
        azure.identity = {"principalId": NEW_OBJECT, "clientId": NEW_CLIENT}
        azure.credentials = ["repo:other/other:ref:refs/heads/main"]
        azure.roles = [(NEW_OBJECT, GROUP_ID, setup.READER_ROLE)]
        run = Run(azure)
        run("check", *ALL, "--step", "G4")
        self.assertIn("G4  DIFFERS    Its federated credentials are not exactly the one of the deploy identity's subject", run.text)
        azure.credentials = []
        run = Run(azure)
        run("check", *ALL, "--step", "G4")
        self.assertIn("G4  MISSING    It has no federated credential", run.text)

    def test_the_read_only_identity_needs_the_group_and_the_name_of_the_deploy_identity(self):
        run = Run()
        self.assertEqual(run("check", *COMMON, "--step", "G4"), 1)
        self.assertIn("G4  UNREADABLE", run.text)
        self.assertIn("--identity-group", run.text)


class Grant(unittest.TestCase):
    def test_a_dry_run_makes_nothing_and_says_what_it_would_run(self):
        run = Run()
        self.assertEqual(run("grant", *ALL), 0, run.errors.getvalue())
        self.assertEqual(run.azure.writes(), [])
        self.assertIn("This was a dry run. Run again with --apply to make what is missing.", run.text)
        self.assertIn("would run: az role assignment create --assignee-object-id " + DEPLOY_OBJECT, run.text)
        self.assertIn("would run: az provider register --namespace Microsoft.Monitor --wait", run.text)
        self.assertIn("would run: az identity create --name id-meternaut-drift", run.text)
        self.assertIn("--role Reader --scope " + GROUP_ID, run.text)

    def test_it_makes_every_missing_step_once_in_order_and_reads_again(self):
        run = Run()
        code = run("grant", *ALL, "--apply", "--yes")
        self.assertEqual(code, 0, run.text + run.errors.getvalue())
        azure = run.azure
        self.assertTrue(azure.have(DEPLOY_OBJECT, GROUP_ID, setup.RESOURCE_POLICY_CONTRIBUTOR))
        self.assertIn("Microsoft.Monitor", azure.registered)
        self.assertTrue(azure.have(GATEWAY_OBJECT, RULE, setup.MONITORING_METRICS_PUBLISHER))
        self.assertEqual(azure.identity["clientId"], NEW_CLIENT)
        self.assertEqual(azure.credentials, [SUBJECT])
        self.assertTrue(azure.have(NEW_OBJECT, GROUP_ID, setup.READER_ROLE))
        self.assertEqual(len(azure.roles), 3)
        self.assertIn("Read again:", run.text)
        after = run.text.split("Read again:")[1]
        self.assertNotIn("MISSING", after)
        self.assertIn(f"gh variable set DRIFT_CLIENT_ID --body {NEW_CLIENT}", after)

    def test_it_only_adds_never_deletes_and_only_the_four_kinds_of_write(self):
        run = Run()
        run("grant", *ALL, "--apply", "--yes")
        for call in run.azure.calls:
            self.assertNotIn("delete", call)
            self.assertNotIn("update", call)
            self.assertNotIn("set", call[:3])
        self.assertTrue(run.azure.writes())
        for call in run.azure.writes():
            self.assertTrue(any(tuple(call[:len(head)]) == head for head in WRITES), call)

    def test_the_read_only_identity_is_made_in_the_group_of_the_deploy_identity_and_holds_only_reader(self):
        run = Run()
        run("grant", *ALL, "--apply", "--yes")
        made = [call for call in run.azure.calls if call[:2] == ["identity", "create"]][0]
        self.assertEqual(option(made, "--resource-group"), IDENTITY_GROUP)
        self.assertEqual(option(made, "--name"), "id-meternaut-drift")
        credential = [call for call in run.azure.calls if call[:3] == ["identity", "federated-credential", "create"]][0]
        self.assertEqual(option(credential, "--issuer"), "https://token.actions.githubusercontent.com")
        self.assertEqual(option(credential, "--audiences"), "api://AzureADTokenExchange")
        self.assertEqual(option(credential, "--subject"), SUBJECT)
        mine = [role for principal, scope, role in run.azure.roles if principal == NEW_OBJECT]
        self.assertEqual(mine, [setup.READER_ROLE])

    def test_a_second_run_makes_nothing(self):
        azure = Azure()
        Run(azure)("grant", *ALL, "--apply", "--yes")
        made = len(azure.writes())
        run = Run(azure)
        self.assertEqual(run("grant", *ALL, "--apply", "--yes"), 0, run.text)
        self.assertEqual(len(azure.writes()), made)

    def test_one_step_can_be_run_alone(self):
        run = Run()
        self.assertEqual(run("grant", *ALL, "--step", "G2", "--apply", "--yes"), 0, run.text)
        self.assertEqual([call[:2] for call in run.azure.writes()], [["provider", "register"]])
        self.assertEqual(run.azure.roles, [])

    def test_it_never_runs_in_a_pipeline(self):
        run = Run()
        self.assertEqual(run("grant", *ALL, "--apply", "--yes", env={"GITHUB_ACTIONS": "true"}), 2)
        self.assertIn("a hand step is not run in a pipeline", run.errors.getvalue())
        self.assertEqual(run.azure.calls, [])

    def test_without_a_terminal_it_needs_yes_and_with_a_terminal_it_asks(self):
        run = Run()
        self.assertEqual(run("grant", *ALL, "--apply", interactive=False), 2)
        self.assertIn("--apply needs --yes when there is no terminal to ask in", run.errors.getvalue())
        self.assertEqual(run.azure.writes(), [])
        run = Run()
        self.assertEqual(run("grant", *ALL, "--apply", answer="no"), 1)
        self.assertEqual(len(run.asked), 1)
        self.assertEqual(run.azure.writes(), [])
        self.assertIn("Nothing was changed.", run.text)
        run = Run()
        self.assertEqual(run("grant", *ALL, "--apply", answer="yes"), 0, run.text)
        self.assertTrue(run.azure.writes())

    def test_it_changes_nothing_while_something_differs_or_cannot_be_read(self):
        azure = Azure()
        azure.identity = {"principalId": NEW_OBJECT, "clientId": NEW_CLIENT}
        azure.credentials = ["repo:other/other:ref:refs/heads/main"]
        run = Run(azure)
        self.assertEqual(run("grant", *ALL, "--apply", "--yes"), 2)
        self.assertIn("nothing is changed until a person has looked at it", run.errors.getvalue())
        self.assertEqual(azure.writes(), [])

    def test_a_write_that_fails_stops_the_run_and_says_which(self):
        azure = Azure()
        azure.failing["provider register"] = "(AuthorizationFailed) no right to register"
        run = Run(azure)
        self.assertEqual(run("grant", *ALL, "--apply", "--yes"), 2)
        self.assertIn("G2: provider register --namespace Microsoft.Monitor failed: (AuthorizationFailed)", run.errors.getvalue())

    def test_the_wait_for_a_provider_is_bounded(self):
        class Stubborn(Azure):
            def __call__(self, arguments):
                code, out, err = super().__call__(arguments)
                if arguments[:2] == ["provider", "register"]:
                    self.registered.discard(option(arguments, "--namespace"))
                return code, out, err

        azure = Stubborn()
        run = Run(azure)
        self.assertEqual(run("grant", *COMMON, "--step", "G2", "--apply", "--yes"), 1)
        shows = [call for call in azure.calls if call[:2] == ["provider", "show"]]
        self.assertLessEqual(len(shows), len(setup.PROVIDERS) + setup.REGISTER_TRIES + len(setup.PROVIDERS))
        self.assertIn("G2  MISSING", run.text.split("Read again:")[1])


class Arguments(unittest.TestCase):
    def test_a_subscription_that_is_not_an_id_and_an_unknown_step_are_refused_before_anything_is_read(self):
        for arguments, words in ((("check", "--subscription", "not-an-id", "--resource-group", GROUP), "--subscription is a subscription id"),
                                 (("check", *COMMON, "--step", "G9"), "--step is a list of G1, G2, G3, G4"),
                                 (("check", "--subscription", SUB), "--resource-group is required"),
                                 (("check", *COMMON, "--deploy-principal-id", "nope"), "--deploy-principal-id is the object id of the deploy identity")):
            with self.subTest(arguments=arguments):
                run = Run()
                self.assertEqual(run(*arguments), 2)
                self.assertIn(words, run.errors.getvalue())
                self.assertEqual(run.azure.calls, [])

    def test_the_default_subscription_of_the_cli_is_never_read_and_only_the_four_roles_are_named_in_the_source(self):
        source = (ROOT / "tools" / "governance-setup.py").read_text(encoding="utf-8")
        self.assertNotIn("account show", source)
        self.assertNotIn("account set", source)
        found = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", source))
        self.assertEqual(found, {setup.RESOURCE_POLICY_CONTRIBUTOR, setup.OWNER_ROLE, setup.MONITORING_METRICS_PUBLISHER, setup.READER_ROLE}, "no id of an estate is in the source")

    def test_the_roles_and_names_are_the_ones_that_the_workflow_and_the_templates_use(self):
        workflow = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8")
        self.assertIn(f"resource_policy_contributor={setup.RESOURCE_POLICY_CONTRIBUTOR}", workflow)
        self.assertIn(f"monitoring_metrics_publisher={setup.MONITORING_METRICS_PUBLISHER}", workflow)
        self.assertIn(f"var readerRoleId = '{setup.READER_ROLE}'", (ROOT / "environment" / "operator" / "main.bicep").read_text(encoding="utf-8"))
        self.assertEqual(setup.COMPONENT, "appi-meternaut")
        self.assertIn("name: 'appi-${workload}'", (ROOT / "environment" / "base" / "main.bicep").read_text(encoding="utf-8"))
        self.assertIn(f'GATEWAY_API = "{setup.GATEWAY_API}"', (ROOT / "tools" / "drift-check.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
