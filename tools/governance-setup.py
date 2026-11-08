#!/usr/bin/env python3
"""The hand steps of the AI security (standard library only): reads what is there, shows what it would make, and with --apply makes what is missing.

    python tools/governance-setup.py check --subscription S --resource-group G [--identity-group B --deploy-identity-name N]
    python tools/governance-setup.py grant --subscription S --resource-group G --deploy-principal-id OID [--step G1,G2,G3,G4] [--identity-group B --deploy-identity-name N] [--apply] [--yes]

These are the things that no Hub action can do, because each needs a right that the deploy identity does not hold and that only a person gives (AGENTS.md rule 18: the bootstrap is the only step taken outside a
workflow): a person runs this with their own sign-in (az login), on the owner's written word. environment/BOOTSTRAP.md, the section "The AI security", gives each step with its exact command, why it is needed and
how to undo it; this tool is the same steps with a read first.

  G1  The deploy identity holds Resource Policy Contributor on the project's resource group, so that the action governance can write the two policy assignments of the AI security (Contributor cannot).
  G2  The resource providers that the AI security needs are registered in the subscription, Microsoft.Monitor among them (the OpenTelemetry ingestion of the component makes a managed Azure Monitor workspace).
  G3  The AI Gateway's own identity holds Monitoring Metrics Publisher on the component's data collection rule, so that the telemetry exporter can send. The rule is in a resource group that the platform
      manages, behind a deny assignment: no template and no Hub action can give the role. It needs the action base (which turns the ingestion on) to have run, and the endpoints a few minutes after it.
  G4  The read-only identity of the independent drift check (the workflow drift.yml): a user-assigned managed identity, with a federated credential for the main branch of this repository, copied from the deploy
      identity's own, and the role Reader on the project's resource group, which covers the Foundry resource and the AI Gateway in it, and no other role. It lives next to the deploy identity (--identity-group),
      not in the project's group, where the deploy identity could change it. The repository variable DRIFT_CLIENT_ID is then set to its client id (the last line says how).

`check` only reads. `grant` is a dry run unless it is given --apply, then makes only what is missing, each step once, reads again and says what it found. It adds and never deletes or changes. It refuses to run in a
pipeline (GITHUB_ACTIONS=true): a hand step is the one thing that does not go through a workflow. With --apply and no terminal it needs --yes. Nothing secret is read or printed: ids and states only.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Mapping

RESOURCE_POLICY_CONTRIBUTOR = "36243c78-bf99-498c-9df9-86d9f8d28608"
OWNER_ROLE = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
MONITORING_METRICS_PUBLISHER = "3913510d-42f4-4e42-8a64-420c390055eb"
READER_ROLE = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
PROVIDERS = ("Microsoft.Authorization", "Microsoft.Insights", "Microsoft.OperationalInsights", "Microsoft.PolicyInsights", "Microsoft.Monitor")
DRIFT_IDENTITY = "id-meternaut-drift"
CREDENTIAL_NAME = "github-main"
ISSUER = "https://token.actions.githubusercontent.com"
AUDIENCE = "api://AzureADTokenExchange"
COMPONENT = "appi-meternaut"
GATEWAY_API = "2025-09-01-preview"
INSIGHTS_API = "2020-02-02"
STEPS = ("G1", "G2", "G3", "G4")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
PRESENT, MISSING, DIFFERS, UNREADABLE, WAITING = "present", "MISSING", "DIFFERS", "UNREADABLE", "WAITING"
REGISTER_TRIES = 12
REGISTER_SECONDS = 10

Runner = Callable[[list[str]], tuple[int, str, str]]


class Problem(Exception):
    """A setting or a state that the caller can fix; printed without a trace."""


def load_params():
    spec = importlib.util.spec_from_file_location("environment_params_of_the_governance_setup", Path(__file__).with_name("environment-params.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def az_command() -> list[str]:
    """`az`, or the command in the variable AZ (it may hold a path with spaces in quotes, and arguments)."""
    value = os.environ.get("AZ", "").strip()
    if not value:
        return [shutil.which("az") or "az"]
    parts = shlex.split(value, posix=(os.name != "nt"))
    return [p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]


def run_az(arguments: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([*az_command(), *arguments], capture_output=True, text=True, timeout=600)
    return done.returncode, done.stdout, done.stderr


def first_line(text: str) -> str:
    return (text.strip().splitlines() or ["no answer"])[0][:200]


class Item:
    def __init__(self, step: str, state: str, text: str, command: list[str] | None = None, after: str = ""):
        self.step, self.state, self.text, self.command, self.after = step, state, text, command, after


class Setup:
    """The reads and the commands of the four steps, for one project."""

    def __init__(self, az: Runner, subscription: str, group: str, deploy_principal: str = "", identity_group: str = "", deploy_identity: str = "", sleep: Callable[[float], None] = time.sleep):
        for what, value in (("--subscription", subscription), ("--resource-group", group)):
            if not value:
                raise Problem(f"{what} is required")
        if not GUID.match(subscription):
            raise Problem("--subscription is a subscription id")
        if deploy_principal and not GUID.match(deploy_principal):
            raise Problem("--deploy-principal-id is the object id of the deploy identity")
        self.az, self.subscription, self.group = az, subscription, group
        self.deploy_principal, self.identity_group, self.deploy_identity, self.sleep = deploy_principal.lower(), identity_group, deploy_identity, sleep
        params = load_params()
        self.gateway = params.aigateway_name(subscription, group)

    @property
    def group_id(self) -> str:
        return f"/subscriptions/{self.subscription}/resourceGroups/{self.group}"

    def run(self, arguments: list[str]) -> tuple[int, str, str]:
        """Every call names the subscription: the CLI's default subscription is never taken as the pilot's scope (AGENTS.md rule 15 (b))."""
        return self.az([*arguments, "--subscription", self.subscription])

    def read(self, arguments: list[str]) -> str:
        code, out, err = self.run(arguments)
        if code != 0:
            raise Problem(first_line(err))
        return out.strip()

    def rest(self, path: str, api: str, query: str) -> str:
        value = self.read(["rest", "--method", "get", "--url", f"https://management.azure.com{path}?api-version={api}", "--query", query, "--output", "tsv", "--only-show-errors"])
        return "" if value in ("None", "null") else value

    def roles_of(self, principal: str, scope: str, inherited: bool = False) -> list[tuple[str, str]]:
        arguments = ["role", "assignment", "list", "--assignee-object-id", principal, "--scope", scope, "--fill-principal-name", "false", "--fill-role-definition-name", "false"]
        if inherited:
            arguments.append("--include-inherited")
        arguments += ["--query", "[].[scope, roleDefinitionId]", "--output", "tsv", "--only-show-errors"]
        rows = [line.split("\t") for line in self.read(arguments).splitlines() if line.strip()]
        return [(row[0], row[1].rsplit("/", 1)[-1].lower()) for row in rows if len(row) == 2]

    def assignment(self, principal: str, role: str, scope: str, kind: str = "ServicePrincipal") -> list[str]:
        return ["role", "assignment", "create", "--assignee-object-id", principal, "--assignee-principal-type", kind, "--role", role, "--scope", scope, "--output", "none"]

    def credential(self, subject: str) -> list[str]:
        return ["identity", "federated-credential", "create", "--identity-name", DRIFT_IDENTITY, "--resource-group", self.identity_group, "--name", CREDENTIAL_NAME, "--issuer", ISSUER,
                "--subject", subject, "--audiences", AUDIENCE, "--output", "none"]

    # G1
    def policy_role(self) -> Item:
        if not self.deploy_principal:
            return Item("G1", UNREADABLE, "The object id of the deploy identity was not given (--deploy-principal-id), so its roles cannot be looked at.")
        try:
            held = self.roles_of(self.deploy_principal, self.group_id, inherited=True)
        except Problem as e:
            return Item("G1", UNREADABLE, f"The roles of the deploy identity on the group could not be read: {e}")
        group = self.group_id.lower()

        def applies(scope: str) -> bool:
            above = scope.lower().rstrip("/")
            return above == group or group.startswith(above + "/") or scope == "/" or above.startswith("/providers/microsoft.management/managementgroups/")

        good = any(role in (RESOURCE_POLICY_CONTRIBUTOR, OWNER_ROLE) and applies(scope) for scope, role in held)
        if good:
            return Item("G1", PRESENT, "The deploy identity holds a role on the group that can write a policy assignment (Resource Policy Contributor, or Owner).")
        return Item("G1", MISSING, "The deploy identity holds no role that can write a policy assignment on the group. It would be given Resource Policy Contributor on the group.",
                    self.assignment(self.deploy_principal, RESOURCE_POLICY_CONTRIBUTOR, self.group_id))

    # G2
    def providers(self) -> list[Item]:
        items = []
        for namespace in PROVIDERS:
            try:
                state = self.read(["provider", "show", "--namespace", namespace, "--query", "registrationState", "--output", "tsv"])
            except Problem as e:
                items.append(Item("G2", UNREADABLE, f"The registration of {namespace} could not be read: {e}"))
                continue
            if state == "Registered":
                items.append(Item("G2", PRESENT, f"The resource provider {namespace} is registered."))
            else:
                items.append(Item("G2", MISSING, f"The resource provider {namespace} is {state or 'not registered'}. It would be registered.", ["provider", "register", "--namespace", namespace, "--wait"], namespace))
        return items

    # G3
    def metrics_role(self) -> Item:
        try:
            principal = self.rest(f"{self.group_id}/providers/Microsoft.ApiManagement/aigateways/{self.gateway}", GATEWAY_API, "identity.principalId").lower()
            rule = self.rest(f"{self.group_id}/providers/Microsoft.Insights/components/{COMPONENT}", INSIGHTS_API, "properties.DataCollectionRuleResourceId")
        except Problem as e:
            return Item("G3", UNREADABLE, f"The gateway or the component could not be read: {e}")
        if not GUID.match(principal):
            return Item("G3", WAITING, "The AI Gateway has no identity yet: run the action aigateway first.")
        if not re.match(r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Insights/dataCollectionRules/[^/]+$", rule):
            return Item("G3", WAITING, "The component reports no data collection rule yet: run the action base (it turns the OpenTelemetry ingestion on), and wait about ten minutes.")
        try:
            held = self.roles_of(principal, rule)
        except Problem as e:
            return Item("G3", UNREADABLE, f"The roles on the data collection rule could not be read: {e}")
        if any(role == MONITORING_METRICS_PUBLISHER and scope.lower().rstrip("/") == rule.lower() for scope, role in held):
            return Item("G3", PRESENT, "The AI Gateway's identity holds Monitoring Metrics Publisher on the component's data collection rule.")
        return Item("G3", MISSING, "The AI Gateway's identity does not hold Monitoring Metrics Publisher on the component's data collection rule. It would be given the role there; it takes up to ten minutes to apply.",
                    self.assignment(principal, MONITORING_METRICS_PUBLISHER, rule))

    # G4
    def read_only_identity(self) -> list[Item]:
        if not self.identity_group or not self.deploy_identity:
            return [Item("G4", UNREADABLE, "The group of the deploy identity (--identity-group) and its name (--deploy-identity-name) were not given, so the read-only identity cannot be looked at or made.")]
        items = []
        try:
            exists = self.read(["identity", "show", "--name", DRIFT_IDENTITY, "--resource-group", self.identity_group, "--query", "[principalId, clientId]", "--output", "tsv"])
        except Problem as e:
            exists = ""
            if "ResourceNotFound" not in str(e) and "not found" not in str(e).lower():
                return [Item("G4", UNREADABLE, f"The identity {DRIFT_IDENTITY} could not be read: {e}")]
        principal, client = (exists.split() + ["", ""])[:2]
        if not GUID.match(principal):
            try:
                subject = self.read(["identity", "federated-credential", "show", "--identity-name", self.deploy_identity, "--resource-group", self.identity_group, "--name", CREDENTIAL_NAME, "--query", "subject", "--output", "tsv"])
                location = self.read(["group", "show", "--name", self.identity_group, "--query", "location", "--output", "tsv"])
            except Problem as e:
                return [Item("G4", UNREADABLE, f"The deploy identity's federated credential {CREDENTIAL_NAME} or the group {self.identity_group} could not be read: {e}")]
            items.append(Item("G4", MISSING, f"The identity {DRIFT_IDENTITY} is not there. It would be made in {self.identity_group}.",
                              ["identity", "create", "--name", DRIFT_IDENTITY, "--resource-group", self.identity_group, "--location", location, "--output", "none"]))
            items.append(Item("G4", MISSING, f"It would get a federated credential {CREDENTIAL_NAME} with the subject of the deploy identity's own (the main branch of this repository).", self.credential(subject)))
            items.append(Item("G4", MISSING, "It would get the role Reader on the project's resource group, which covers the Foundry resource and the AI Gateway in it, and no other role.", None, "reader"))
            return items
        items.append(Item("G4", PRESENT, f"The identity {DRIFT_IDENTITY} is there."))
        try:
            wanted = self.read(["identity", "federated-credential", "show", "--identity-name", self.deploy_identity, "--resource-group", self.identity_group, "--name", CREDENTIAL_NAME, "--query", "subject", "--output", "tsv"])
            subjects = self.read(["identity", "federated-credential", "list", "--identity-name", DRIFT_IDENTITY, "--resource-group", self.identity_group, "--query", "[].subject", "--output", "tsv"]).split()
        except Problem as e:
            return items + [Item("G4", UNREADABLE, f"The federated credentials could not be read: {e}")]
        if subjects == [wanted]:
            items.append(Item("G4", PRESENT, "It has one federated credential, with the subject of the deploy identity's own (the main branch of this repository)."))
        elif not subjects:
            items.append(Item("G4", MISSING, "It has no federated credential. It would get one with the subject of the deploy identity's own (the main branch of this repository).", self.credential(wanted)))
        else:
            items.append(Item("G4", DIFFERS, "Its federated credentials are not exactly the one of the deploy identity's subject. Nothing is changed here: a person looks at them."))
        try:
            held = [tuple(line.split("\t")) for line in self.read(["role", "assignment", "list", "--assignee-object-id", principal, "--all", "--fill-principal-name", "false", "--fill-role-definition-name", "false",
                                                                  "--query", "[].[scope, roleDefinitionId]", "--output", "tsv", "--only-show-errors"]).splitlines() if line.strip()]
        except Problem as e:
            return items + [Item("G4", UNREADABLE, f"The roles of {DRIFT_IDENTITY} could not be read: {e}")]
        roles = [(scope, role.rsplit("/", 1)[-1].lower()) for scope, role in held]
        others = [(scope, role) for scope, role in roles if role != READER_ROLE]
        if others:
            items.append(Item("G4", DIFFERS, f"It holds {len(others)} role assignment(s) other than Reader: a read-only identity holds nothing that can change anything. Nothing is changed here: a person looks at them."))
        if any(role == READER_ROLE and scope.lower() == self.group_id.lower() for scope, role in roles):
            items.append(Item("G4", PRESENT, "It holds the role Reader on the project's resource group."))
        else:
            items.append(Item("G4", MISSING, "It does not hold the role Reader on the project's resource group. It would be given.", self.assignment(principal, READER_ROLE, self.group_id)))
        items.append(Item("G4", PRESENT, f"Its client id is {client}: set the repository variable DRIFT_CLIENT_ID to it (gh variable set DRIFT_CLIENT_ID --body {client})."))
        return items

    def examine(self, steps: tuple[str, ...]) -> list[Item]:
        items: list[Item] = []
        if "G1" in steps:
            items.append(self.policy_role())
        if "G2" in steps:
            items.extend(self.providers())
        if "G3" in steps:
            items.append(self.metrics_role())
        if "G4" in steps:
            items.extend(self.read_only_identity())
        return items


def show(items: list[Item], out: Callable[[str], None]) -> None:
    for item in items:
        out(f"{item.step}  {item.state:<10} {item.text}")


def run_steps(setup: Setup, items: list[Item], out: Callable[[str], None]) -> None:
    for item in items:
        if item.state != MISSING:
            continue
        if item.after == "reader":
            # the identity was made above: its object id is read now, because the role is given to it
            principal = setup.read(["identity", "show", "--name", DRIFT_IDENTITY, "--resource-group", setup.identity_group, "--query", "principalId", "--output", "tsv"])
            command = setup.assignment(principal, READER_ROLE, setup.group_id)
        else:
            command = item.command
        out(f"{item.step}  making: {' '.join(command[:4])} ...")
        code, _, err = setup.run(command)
        if code != 0:
            raise Problem(f"{item.step}: {' '.join(command[:4])} failed: {first_line(err)}")
        if item.after and item.after != "reader":
            for _ in range(REGISTER_TRIES):
                if setup.read(["provider", "show", "--namespace", item.after, "--query", "registrationState", "--output", "tsv"]) == "Registered":
                    break
                setup.sleep(REGISTER_SECONDS)


def parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("check", "read only: which steps are in order"), ("grant", "a dry run; with --apply, make what is missing")):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--subscription", default=os.environ.get("ENV_SUBSCRIPTION_ID", ""))
        sub.add_argument("--resource-group", default=os.environ.get("ENV_RESOURCE_GROUP", ""))
        sub.add_argument("--deploy-principal-id", default="", help="the object id of the deploy identity (G1)")
        sub.add_argument("--identity-group", default="", help="the resource group of the deploy identity, where the read-only identity is made (G4)")
        sub.add_argument("--deploy-identity-name", default="", help="the name of the deploy identity, whose federated credential is copied (G4)")
        sub.add_argument("--step", default=",".join(STEPS), help="comma separated: G1, G2, G3, G4 (default: all)")
        if name == "grant":
            sub.add_argument("--apply", action="store_true", help="make the changes (the default is a dry run)")
            sub.add_argument("--yes", action="store_true", help="do not ask first")
    return parser.parse_args(argv)


def main(argv=None, az: Runner = run_az, out: Callable[[str], None] = print, ask: Callable[[str], str] = input, env: Mapping[str, str] | None = None, sleep: Callable[[float], None] = time.sleep,
         interactive: bool | None = None) -> int:
    args = parse(argv)
    env = os.environ if env is None else env
    try:
        steps = tuple(part.strip().upper() for part in args.step.split(",") if part.strip())
        if not steps or set(steps) - set(STEPS):
            raise Problem(f"--step is a list of {', '.join(STEPS)}")
        if args.command == "grant" and args.apply and env.get("GITHUB_ACTIONS") == "true":
            raise Problem("a hand step is not run in a pipeline: it needs a person's own sign-in (AGENTS.md rule 18). Run it on a machine, with az login.")
        setup = Setup(az, args.subscription, args.resource_group, args.deploy_principal_id, args.identity_group, args.deploy_identity_name, sleep)
        items = setup.examine(steps)
        show(items, out)
        problems = [i for i in items if i.state in (DIFFERS, UNREADABLE)]
        missing = [i for i in items if i.state == MISSING]
        waiting = [i for i in items if i.state == WAITING]
        if args.command == "check":
            out(f"{len(missing)} to make, {len(waiting)} waiting for another action, {len(problems)} that a person has to look at.")
            return 0 if not (missing or waiting or problems) else 1
        if not args.apply:
            for item in missing:
                if item.command:
                    out(f"  would run: az {' '.join(item.command)}")
                elif item.after == "reader":
                    out(f"  would run: az role assignment create --assignee-object-id <the new identity> --role Reader --scope {setup.group_id}")
            out("This was a dry run. Run again with --apply to make what is missing.")
            return 0 if not problems else 1
        if problems:
            raise Problem("something could not be read or differs, and nothing is changed until a person has looked at it (the lines above)")
        if not args.yes:
            interactive = sys.stdin.isatty() if interactive is None else interactive
            if not interactive:
                raise Problem("--apply needs --yes when there is no terminal to ask in")
            if ask(f"Make the {len(missing)} change(s) above in subscription {args.subscription}? [yes/no] ").strip().lower() != "yes":
                out("Nothing was changed.")
                return 1
        run_steps(setup, items, out)
        after = setup.examine(steps)
        out("Read again:")
        show(after, out)
        return 0 if not [i for i in after if i.state in (MISSING, DIFFERS, UNREADABLE)] else 1
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
