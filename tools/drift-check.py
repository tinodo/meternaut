#!/usr/bin/env python3
"""The control-plane half of the drift check of Meternaut's AI security (standard library only).

    python tools/drift-check.py --subscription S --resource-group G --models environment/models.json --policies environment/aigateway/policies.json \
        --access-list environment/aigateway/contracts.json [--commit SHA --app-dir src/case-functions] [--accepted-exemptions LIST --accepted-deny LIST] \
        [--cases-public-access Enabled] [--read-subscription] [--graph --console-client-id ID] [--only ID,ID] [--json FILE] [--summary FILE] [--timeout SECONDS]
    python tools/drift-check.py --selftest

It reads what the design rests on from Azure Resource Manager (and, with --graph, from Microsoft Graph) and says, for each control, PASS, FAIL or UNKNOWN. It never changes anything: it makes GET requests, and the
two reads that need a POST (Azure Resource Graph, for the compliance of the policies, and the query of Application Insights, for the lines that the app's own check logs) and nothing else; every other call is refused
before it is made. The result of a control is {control, layer, state, detail, readAt}: the same shape as the lines of the app's own check (the agent harness: `drift.pass`, `drift.fail` and `drift.unknown` lines of
`cases/drift.py`), so that one report can hold both halves. The layers are those of the AI Citadel Blueprint: L1 the governance hub (the AI Gateway), L2 agent operations (the Foundry resource, the guardrail, the
models), L3 agent management (identities, owners), L4 the security foundation (policy, roles, network, the release, the check itself).

Rules that every control follows:
  - A thing that cannot be read with the rights of the identity that runs this is UNKNOWN, with the reason and the right that would read it. UNKNOWN is never PASS and is never hidden.
  - What is read is compared with what the repository says (environment/models.json, environment/aigateway/policies.json and contracts.json, the templates' names) and, where the repository cannot say it, with a
    baseline that a person accepted and that lives in a repository variable and not in a file (a policy exemption that the owner knows of: --accepted-exemptions; a policy that is non-compliant with the effect
    Deny and that he knows of: --accepted-deny). With no baseline the control is UNKNOWN and prints what it found, so that he can accept it; it is never PASS.
  - A FAIL of a control whose breach means that the agents run outside what was designed is fail-closed: the run ends with exit code 1 and the summary says so. The app's own check pulls the switch of the investigation
    (only narrow: a person puts it back); this tool changes nothing, so it only fails the run and says it. Any other FAIL ends the run with exit code 1 as well, and says that it is not fail-closed.
  - The check does not rest on the app (docs/design/07-safeguards-and-drift.md: never inside an agent or an app that it watches). It runs from a runner, as the deploy identity (the Hub action drift-check) and as the
    read-only identity of the workflow drift.yml, and it reads the lines that the app's own check logged, so a silent app is a FAIL here.

--selftest builds a fake estate that is as the repository says, runs every control against it, and then breaks one thing at a time and requires the control that watches it to say FAIL. No call is made to Azure.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlsplit

ARM = "https://management.azure.com"
GRAPH = "https://graph.microsoft.com"
ACCOUNT_API = "2025-06-01"
FOUNDRY_API = "2026-09-01"
GATEWAY_API = "2025-09-01-preview"
AUTHORIZATION_API = "2022-04-01"
POLICY_API = "2024-04-01"
EXEMPTION_API = "2022-07-01-preview"
WEB_API = "2024-04-01"
IDENTITY_API = "2023-01-31"
INSIGHTS_API = "2020-02-02"
ALERT_API = "2023-12-01"
ACTION_GROUP_API = "2023-01-01"
WORKBOOK_API = "2023-06-01"
DIAGNOSTIC_API = "2021-05-01-preview"
STORAGE_API = "2023-05-01"
WORKSPACE_API = "2023-09-01"
RESOURCES_API = "2021-04-01"
GRAPH_RESOURCE_API = "2021-03-01"
QUERY_API = "2018-04-20"
SECURITY_API = "2024-01-01"

NOT_FOUND = re.compile(r"NotFound|ResourceNotFound|Not Found|\b404\b", re.I)
DENIED = re.compile(r"Forbidden|Unauthorized|AuthorizationFailed|AuthenticationFailed|InvalidAuthenticationToken|LinkedAuthorizationFailed|\b40[13]\b", re.I)
TIMEOUT_SECONDS = 120
MAX_PAGES = 20
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

# What the repository says about names that no parameter carries: the workspace and the component of the base, the identities of the Operator and of the console's sign-in.
WORKSPACE = "log-meternaut"
COMPONENT = "appi-meternaut"
OPERATOR_IDENTITY = "id-meternaut-operator"
CONSOLE_IDENTITY = "id-meternaut-console-auth"
EXPORTER = "appinsights"
GATEWAY_PROVIDER = "foundry"
GATEWAY_MODELS_USER = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"
FOUNDRY_USER = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
FOUNDRY_PROJECT_MANAGER = "eadc314b-1a2d-4efa-be10-5d325db5065e"
WIDER_FOUNDRY_ROLES = {FOUNDRY_PROJECT_MANAGER: "Foundry Project Manager", "e47c6f54-e4a2-4754-9501-8e0985b135e1": "Foundry Account Owner", "c883944f-8b7b-4483-af10-35834be79c4a": "Foundry Owner"}
MONITOR_AUDIENCE = "https://monitor.azure.com"
SHIELDS = (("Jailbreak", "Prompt"), ("Indirect Attack", "Prompt"), ("Indirect Attack", "PostToolCall"))
GATEWAY_AUDIENCE = "https://azure-api.net/aigateway"
GATEWAY_PATH = "/default/models/openai/v1"
CATEGORIES = ("hateSeverity", "violenceSeverity", "sexualSeverity", "selfHarmSeverity")
CONTENT_SAFETY = "Medium"
ENTRA_AUTH_TYPES = ("ProjectManagedIdentity", "AAD", "ManagedIdentity")
# The policies of environment/governance/main.bicep (names of the assignments at the project's group) and the rules that it makes (a test holds this list to the template).
OUR_ASSIGNMENTS = ("meternaut-approved-models", "meternaut-model-eligibility")
OPTIONAL_ASSIGNMENTS = ("meternaut-guardrail-audit", "meternaut-cmk-audit")
ALERT_RULES = ("refusals", "client-errors", "server-errors", "near-limit", "harness-trips", "drift-fail", "drift-heartbeat")
ALERT_RULE_OF_ACCESS_LIST = "outside-access-list"
ACTION_GROUP = "ag-meternaut-ai-security"
WORKBOOK_NAME = "Meternaut AI security"
# How long the app's own check may be silent: it runs daily, and the alert rule fires after this many hours (environment/governance/main.bicep, heartbeatHours).
HEARTBEAT_HOURS = 26
LOOK_BACK_DAYS = 60
# The days before a model retires at which the control speaks: a notice, a warning, and the last stretch, where it fails closed.
LIFECYCLE_NOTICE_DAYS = 180
LIFECYCLE_WARNING_DAYS = 90
LIFECYCLE_CLOSED_DAYS = 30
# Resource types of the project's group that carry no network exposure of their own (the ones below are read by the control I-network; any other type makes it UNKNOWN, so that a new kind of resource is noticed).
QUIET_TYPES = {
    "microsoft.network/virtualnetworks", "microsoft.network/networksecuritygroups", "microsoft.network/privateendpoints", "microsoft.network/networkinterfaces", "microsoft.network/publicipaddresses",
    "microsoft.managedidentity/userassignedidentities", "microsoft.web/serverfarms", "microsoft.insights/workbooks", "microsoft.insights/actiongroups", "microsoft.insights/scheduledqueryrules",
    "microsoft.insights/metricalerts", "microsoft.alertsmanagement/smartdetectoralertrules", "microsoft.compute/disks", "microsoft.containerinstance/containergroups", "microsoft.apimanagement/aigateways",
    "microsoft.insights/webtests", "microsoft.insights/diagnosticsettings", "microsoft.authorization/roleassignments", "microsoft.operationsmanagement/solutions",
    # a project is part of the Foundry resource, whose flags are read; an Event Grid system topic (the platform makes one for a storage account's events) has no endpoint of its own
    "microsoft.cognitiveservices/accounts/projects", "microsoft.eventgrid/systemtopics",
}
READ_TYPES = {"microsoft.storage/storageaccounts", "microsoft.cognitiveservices/accounts", "microsoft.web/sites", "microsoft.insights/components", "microsoft.operationalinsights/workspaces"}

Runner = Callable[[list[str]], tuple[int, str, str]]


class Gone(Exception):
    """Azure says that the resource is not there."""


class Denied(Exception):
    """The identity that runs this has no right to read it."""


class Unreadable(Exception):
    """Azure gave no usable answer. The text is the first line of its error, which holds no token."""


class Stuck(Exception):
    """`az` did not answer in time. Nothing more is read: a second read would wait just as long."""


class Refused(Exception):
    """A call that is not a read. This tool makes none: the call is refused before it is made."""


class Missing(Exception):
    """A resource that a control reads is not there (the control says so as a FAIL)."""


class CannotRead(Exception):
    """A resource that a control reads cannot be read (the control says so as UNKNOWN)."""


class Problem(Exception):
    """Something the caller can fix; printed without a trace."""


def load_sibling(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plain(value: object, limit: int = 60) -> str:
    """A value of an answer as it may be printed: letters, digits and . _ : / - only, cut, and never two colons in a row."""
    text = re.sub(r"[^A-Za-z0-9._:/ -]", "?", "" if value is None else str(value)).replace("::", ": :")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def tail(resource_id: object) -> str:
    return plain(str(resource_id or "").rstrip("/").rsplit("/", 1)[-1]) or "nothing"


def short(object_id: object) -> str:
    """The start of an object id: enough to tell two apart in a line of output, not the id."""
    return plain(str(object_id or "")[:8]) + "..."


def first_line(text: str) -> str:
    return (text.strip().splitlines() or ["no answer"])[0][:300]


def describe(arguments: list[str]) -> str:
    if "--url" in arguments and arguments.index("--url") + 1 < len(arguments):
        method = arguments[arguments.index("--method") + 1].upper() if "--method" in arguments and arguments.index("--method") + 1 < len(arguments) else "GET"
        return method + " " + arguments[arguments.index("--url") + 1].split("?")[0].replace(ARM, "").replace(GRAPH, "")
    return "a request"


def run_az(arguments: list[str], timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, str]:
    try:
        done = subprocess.run([os.environ.get("AZ", "az"), *arguments], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Stuck(f"az did not answer within {timeout} seconds ({describe(arguments)})")
    return done.returncode, done.stdout, done.stderr


def is_read(method: str, url: str) -> bool:
    """Whether this call only reads: every GET of Azure Resource Manager or Microsoft Graph, and the two POSTs that are reads (a query of Azure Resource Graph and of an Application Insights component)."""
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if method == "get":
        return base in (ARM, GRAPH)
    if method == "post" and base == ARM:
        return parts.path == "/providers/Microsoft.ResourceGraph/resources" or bool(re.fullmatch(r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Insights/components/[A-Za-z0-9._-]+/query", parts.path, re.I))
    return False


class Reader:
    """The reads of Azure through `az rest`, with the answers as documents and the failures as the words above. A call that is not a read is refused."""

    def __init__(self, az: Runner):
        self.az = az
        self.calls: list[str] = []

    def send(self, method: str, url: str, body: dict | None = None) -> dict:
        if not is_read(method, url):
            raise Refused(f"{method.upper()} {url.split('?')[0]}")
        arguments = ["rest", "--method", method, "--url", url, "--only-show-errors", "--output", "json"]
        if body is not None:
            arguments += ["--body", json.dumps(body)]
        self.calls.append(describe(arguments))
        code, out, err = self.az(arguments)
        if code != 0:
            if NOT_FOUND.search(err):
                raise Gone()
            if DENIED.search(err):
                raise Denied(first_line(err))
            raise Unreadable(first_line(err))
        try:
            document = json.loads(out) if out.strip() else {}
        except ValueError:
            raise Unreadable("the answer is not JSON")
        if not isinstance(document, dict):
            raise Unreadable("the answer is not an object")
        return document

    def get(self, path: str, api: str, query: str = "") -> dict:
        return self.send("get", f"{ARM}{path}?api-version={api}" + (f"&{query}" if query else ""))

    def get_all(self, path: str, api: str, query: str = "") -> list:
        items: list = []
        document = self.get(path, api, query)
        pages = 1
        while True:
            items.extend(document.get("value") or [])
            link = document.get("nextLink")
            if not link:
                return items
            if pages >= MAX_PAGES:
                raise Unreadable(f"the list has more than {MAX_PAGES} pages")
            if not isinstance(link, str) or not link.startswith(ARM + "/"):
                raise Unreadable("the list goes on at an address that is not of Azure Resource Manager, and that is not followed")
            try:
                document = self.send("get", link)
            except Gone:
                raise Unreadable("a later page of the list is not there")
            pages += 1

    def graph(self, query: str) -> dict:
        return self.send("get", f"{GRAPH}/v1.0/{query}")

    def resource_graph(self, subscription: str, query: str) -> list:
        document = self.send("post", f"{ARM}/providers/Microsoft.ResourceGraph/resources?api-version={GRAPH_RESOURCE_API}",
                             {"subscriptions": [subscription], "query": query, "options": {"resultFormat": "objectArray", "$top": 1000}})
        data = document.get("data")
        if not isinstance(data, list):
            raise Unreadable("the answer of Azure Resource Graph holds no rows")
        return data

    def query_component(self, path: str, query: str) -> list[dict]:
        document = self.send("post", f"{ARM}{path}/query?api-version={QUERY_API}", {"query": query})
        tables = document.get("tables") or []
        if not tables:
            raise Unreadable("the answer of the query holds no table")
        columns = [c.get("name") for c in tables[0].get("columns") or []]
        return [dict(zip(columns, row)) for row in tables[0].get("rows") or []]


class Outcome:
    def __init__(self, state: str, detail: str, closed: bool = False):
        self.state, self.detail, self.closed = state, detail, closed


def passed(detail: str) -> Outcome:
    return Outcome(PASS, detail)


def failed(detail: str, closed: bool = True) -> Outcome:
    return Outcome(FAIL, detail, closed)


def unknown(detail: str) -> Outcome:
    return Outcome(UNKNOWN, detail)


def parse_when(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    found = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value)
    if not found:
        return None
    try:
        return date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
    except ValueError:
        return None


def normal(value):
    """A value as it is compared: a number is a number (5 and 5.0 are the same, and a switch is not a number)."""
    if isinstance(value, bool):
        return ("switch", value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return [normal(item) for item in value]
    if isinstance(value, dict):
        return {key: normal(item) for key, item in value.items()}
    return value


def find_policy(policies: list, wanted: dict) -> int | None:
    for index, policy in enumerate(policies):
        if isinstance(policy, dict) and policy.get("type") == wanted.get("type") and (wanted.get("type") != "costLimit" or policy.get("id") == wanted.get("id")):
            return index
    return None


def holds(policy: dict, wanted: dict) -> bool:
    return all(key in policy and normal(policy[key]) == normal(value) for key, value in wanted.items())


def policy_label(policy: dict) -> str:
    return f"{plain(policy.get('type'))} {plain(policy.get('id'))}" if policy.get("type") == "costLimit" and policy.get("id") else plain(policy.get("type"))


def keys_of(value: str) -> set[str]:
    """The keys of a baseline that a person accepted: comma separated, and the word none for a baseline that accepts nothing (an estate that has none of them)."""
    if (value or "").strip().lower() == "none":
        return set()
    return {part.strip() for part in (value or "").split(",") if part.strip()}


class Context:
    """What the controls share: the reader, the names that the repository gives, the files that it holds, and the answers that more than one control needs."""

    def __init__(self, reader: Reader, subscription: str, group: str, models: list[dict], policies: list[dict], access: dict, options: dict | None = None):
        params = load_sibling("environment_params_of_the_drift_check", "environment-params.py")
        self.params = params
        self.reader = reader
        self.subscription = subscription
        self.group = group
        self.models = models
        self.policies = policies
        self.access = access
        self.options = options or {}
        names = params.foundry_names(subscription, group)
        self.account = names["foundry_account_name"]
        self.project = names["foundry_project_name"]
        self.guardrail = names["foundry_guardrail_name"]
        self.gateway = params.aigateway_name(subscription, group)
        self.cases_app = params.cases_names(subscription, group)["cases_function_app_name"]
        self.storage = params.base_names(subscription, group)["storage_account_name"]
        self.now: datetime = self.options.get("now") or datetime.now(timezone.utc)
        self.halted = False
        self.cache: dict[str, object] = {}

    @property
    def group_path(self) -> str:
        return f"/subscriptions/{self.subscription}/resourceGroups/{self.group}"

    def at(self, provider_path: str) -> str:
        return f"{self.group_path}/providers/{provider_path}"

    @property
    def account_path(self) -> str:
        return self.at(f"Microsoft.CognitiveServices/accounts/{self.account}")

    @property
    def project_path(self) -> str:
        return f"{self.account_path}/projects/{self.project}"

    @property
    def gateway_path(self) -> str:
        return self.at(f"Microsoft.ApiManagement/aigateways/{self.gateway}")

    @property
    def workspace_path(self) -> str:
        return f"{self.gateway_path}/workspaces/default"

    @property
    def component_path(self) -> str:
        return self.at(f"Microsoft.Insights/components/{COMPONENT}")

    @property
    def site_path(self) -> str:
        return self.at(f"Microsoft.Web/sites/{self.cases_app}")

    def attempt(self, label: str, call: Callable[[], object], needs: str = "Reader at the project's group"):
        """One read, with the words for each way that it can go wrong: not there (the control fails), no right to read it, no usable answer, or no answer in time (nothing more is read after that)."""
        if self.halted:
            raise CannotRead(f"{label} was not read: an earlier read did not answer in time")
        try:
            return call()
        except Gone:
            raise Missing(label)
        except Denied as e:
            raise CannotRead(f"{label} cannot be read with this identity ({plain(e, 120)}): it needs the right to read it ({needs})")
        except Unreadable as e:
            raise CannotRead(f"{label} could not be read: {plain(e, 160)}")
        except Stuck as e:
            self.halted = True
            raise CannotRead(f"{label} could not be read: {plain(e, 160)}. Nothing after it was read")

    def read(self, label: str, path: str, api: str, query: str = "", pages: bool = False):
        """The document at the path (or all items of the list there), cached; a resource that is not there or cannot be read ends the control with the words for it."""
        key = f"{path}|{api}|{query}|{pages}"
        if key in self.cache:
            return self.cache[key]
        value = self.attempt(label, lambda: self.reader.get_all(path, api, query) if pages else self.reader.get(path, api, query))
        self.cache[key] = value
        return value

    def principal(self, kind: str) -> str:
        """The object id of one of the identities of the access list, read from the resource that carries it; empty when that resource is not there yet."""
        try:
            if kind == "cases":
                return str((self.read("The cases app", self.site_path, WEB_API).get("identity") or {}).get("principalId") or "").lower()
            if kind == "foundry-project":
                return str((self.read("The Foundry project", f"{self.account_path}/projects/{self.project}", FOUNDRY_API).get("identity") or {}).get("principalId") or "").lower()
            if kind == "operator":
                return str((self.read("The Operator's identity", self.at(f"Microsoft.ManagedIdentity/userAssignedIdentities/{OPERATOR_IDENTITY}"), IDENTITY_API).get("properties") or {}).get("principalId") or "").lower()
        except Missing:
            return ""
        raise Problem(f"{kind} is not an identity of the access list")


CONTROLS: list[tuple[str, str, Callable[[Context], Outcome]]] = []


def control(control_id: str, layer: str):
    def register(function: Callable[[Context], Outcome]) -> Callable[[Context], Outcome]:
        CONTROLS.append((control_id, layer, function))
        return function
    return register


@control("I-foundry-flags", "L2")
def foundry_flags(ctx: Context) -> Outcome:
    document = ctx.read(f"The Foundry resource {ctx.account}", ctx.account_path, ACCOUNT_API)
    properties = document.get("properties") or {}
    acls = properties.get("networkAcls") or {}
    problems = []
    if properties.get("publicNetworkAccess") != "Disabled":
        problems.append(f"public network access is {plain(properties.get('publicNetworkAccess')) or 'not set'}, not Disabled")
    if properties.get("disableLocalAuth") is not True:
        problems.append("local authentication (the keys) is not off")
    if acls.get("defaultAction") not in (None, "Deny"):
        problems.append("the network rules do not deny by default")
    if acls.get("ipRules"):
        problems.append("the network rules allow an address range")
    if acls.get("virtualNetworkRules"):
        problems.append("the network rules allow a virtual network")
    if properties.get("allowProjectManagement") is not True:
        problems.append("project management is off")
    if not (document.get("identity") or {}).get("principalId"):
        problems.append("it has no identity of its own")
    if document.get("kind") != "AIServices":
        problems.append(f"its kind is {plain(document.get('kind'))}, not AIServices")
    if problems:
        return failed(f"The Foundry resource differs from its template: {'; '.join(problems)}.")
    return passed("Public network access is Disabled, local authentication is off, the network rules deny by default and name no address, project management is on, and the resource has an identity of its own.")


@control("I-deployments", "L2")
def deployments(ctx: Context) -> Outcome:
    items = ctx.read("The model deployments", f"{ctx.account_path}/deployments", FOUNDRY_API, pages=True)
    deployed = {d.get("name"): d for d in items if isinstance(d, dict)}
    problems = []
    for model in ctx.models:
        found = deployed.get(model["name"])
        if found is None:
            problems.append(f"{model['name']} is not deployed")
            continue
        properties = found.get("properties") or {}
        made = properties.get("model") or {}
        capacity = model.get("agentCapacity", model["capacity"])
        wrong = [word for word, ok in (("model", made.get("name") == model["name"]), ("version", made.get("version") == model["version"]),
                                       ("deployment type", (found.get("sku") or {}).get("name") == model["sku"]), ("capacity", (found.get("sku") or {}).get("capacity") == capacity),
                                       ("guardrail", properties.get("raiPolicyName") == ctx.guardrail), ("version upgrade", properties.get("versionUpgradeOption") in (None, "NoAutoUpgrade"))) if not ok]
        if wrong:
            problems.append(f"{model['name']} differs from environment/models.json or its template ({', '.join(wrong)})")
    extra = sorted(plain(n, 40) for n in deployed if n not in {m["name"] for m in ctx.models})
    if extra:
        problems.append(f"a deployment that environment/models.json does not list: {', '.join(extra)}")
    if problems:
        return failed("; ".join(problems) + ".")
    return passed(f"Every model of environment/models.json is deployed with its version, deployment type, capacity and guardrail {ctx.guardrail}, and nothing else is deployed ({len(ctx.models)} deployments).")


@control("I-guardrail", "L2")
def guardrail(ctx: Context) -> Outcome:
    document = ctx.read(f"The guardrail {ctx.guardrail}", f"{ctx.account_path}/raiPolicies/{ctx.guardrail}", FOUNDRY_API)
    properties = document.get("properties") or {}
    filters = [f for f in properties.get("contentFilters") or [] if isinstance(f, dict)]
    off = []
    for name, source in SHIELDS:
        named = [f for f in filters if f.get("name") == name and f.get("source") == source]
        if not named or not all(f.get("enabled") is True and f.get("blocking") is True for f in named):
            off.append(f"{name} at {source}")
    problems = []
    if off:
        problems.append(f"it does not block {', '.join(off)}")
    if properties.get("mode") not in (None, "Blocking"):
        problems.append(f"its mode is {plain(properties.get('mode'))}, not Blocking")
    if problems:
        return failed(f"The guardrail {ctx.guardrail}: {'; '.join(problems)}.")
    return passed("The guardrail blocks Jailbreak and Indirect Attack on the user input and Indirect Attack on the tool results, and its mode is Blocking.")


@control("I-model-lifecycle", "L2")
def model_lifecycle(ctx: Context) -> Outcome:
    items = ctx.read("The models of the Foundry resource", f"{ctx.account_path}/models", ACCOUNT_API, pages=True)
    today = ctx.now.date()
    listed = {}
    for item in items:
        model = item.get("model") if isinstance(item, dict) and isinstance(item.get("model"), dict) else item
        if isinstance(model, dict) and model.get("name"):
            listed[(model.get("name"), model.get("version"))] = model
    failing: list[Outcome] = []
    fine: list[str] = []
    for model in ctx.models:
        known = listed.get((model["name"], model["version"]))
        dates = [parse_day(model.get("retirementDate"))]
        status = ""
        if known is not None:
            status = str(known.get("lifecycleStatus") or "")
            dates.append(parse_day((known.get("deprecation") or {}).get("inference")))
            dates += [parse_day(s.get("deprecationDate")) for s in known.get("skus") or [] if isinstance(s, dict)]
        retires = min((d for d in dates if d), default=None)
        days = (retires - today).days if retires else None
        label = f"{model['name']} {model['version']}"
        if status == "Deprecated" or (days is not None and days <= 0):
            failing.append(failed(f"{label} is retired (lifecycleStatus {plain(status) or 'unknown'}, retirement {retires}): calls to it fail."))
        elif days is not None and days <= LIFECYCLE_CLOSED_DAYS:
            failing.append(failed(f"{label} retires in {days} days ({retires}): move to its successor now."))
        elif days is not None and days <= LIFECYCLE_WARNING_DAYS:
            failing.append(failed(f"{label} retires in {days} days ({retires}): the move to its successor is due.", closed=False))
        elif days is not None and days <= LIFECYCLE_NOTICE_DAYS:
            failing.append(failed(f"{label} retires in {days} days ({retires}): plan the move to its successor.", closed=False))
        elif status == "Deprecating":
            failing.append(failed(f"{label} is Deprecating: existing deployments only, and it will retire.", closed=False))
        else:
            fine.append(f"{label}: {days if days is not None else 'no'} days to retirement" + ("" if known is not None else " (the date of environment/models.json: the service does not list it)"))
    if failing:
        return Outcome(FAIL, " ".join(o.detail for o in failing), any(o.closed for o in failing))
    return passed(f"No model of environment/models.json is within {LIFECYCLE_NOTICE_DAYS} days of its retirement: " + "; ".join(fine) + ".")


@control("I-gateway-policies", "L1")
def gateway_policies(ctx: Context) -> Outcome:
    document = ctx.read("The default workspace of the AI Gateway", ctx.workspace_path, GATEWAY_API)
    current = (document.get("properties") or {}).get("policies") or []
    current = current if isinstance(current, list) else []
    problems = []
    for wanted in ctx.policies:
        index = find_policy(current, wanted)
        if index is None:
            problems.append(f"the policy {policy_label(wanted)} is not there")
        elif not holds(current[index], wanted):
            problems.append(f"the policy {policy_label(wanted)} differs from environment/aigateway/policies.json")
    if problems:
        return failed("; ".join(problems) + ".")
    extra = [policy_label(p) for p in current if isinstance(p, dict) and find_policy(ctx.policies, p) is None]
    return passed(f"The token limit, the request limit and the cost limits of environment/aigateway/policies.json are on the gateway's workspace, for each caller" + (f"; it also holds {', '.join(extra)}" if extra else "") + ".")


@control("I-gateway-models", "L1")
def gateway_models(ctx: Context) -> Outcome:
    providers = f"{ctx.workspace_path}/modelProviders"
    account_id = ctx.account_path.lower()
    resources = {m["name"]: m["name"].replace(".", "-") for m in ctx.models}
    problems = []
    items = ctx.read("The model providers of the AI Gateway", providers, GATEWAY_API, pages=True)
    by_name = {i.get("name"): i for i in items if isinstance(i, dict)}
    provider = by_name.get(GATEWAY_PROVIDER)
    if provider is None:
        problems.append(f"the provider {GATEWAY_PROVIDER} is not there")
    else:
        behind = (provider.get("properties") or {}).get("foundry") or {}
        ids = [str(r).lower() for r in behind.get("resourceIds") or []]
        if (provider.get("properties") or {}).get("kind") != "Foundry" or (behind.get("authentication") or {}).get("kind") != "ManagedIdentity" or ids != [account_id]:
            problems.append("the provider differs from its template (it is the Foundry resource of the agents alone, called with the gateway's managed identity)")
    if set(map(str, by_name)) - {GATEWAY_PROVIDER}:
        problems.append("another model provider is on the gateway: " + ", ".join(sorted(plain(n, 30) for n in by_name if n != GATEWAY_PROVIDER)))
    items = ctx.read("The models of the AI Gateway", f"{providers}/{GATEWAY_PROVIDER}/models", GATEWAY_API, pages=True)
    models = {i.get("name"): i for i in items if isinstance(i, dict)}
    for model in ctx.models:
        item = models.get(resources[model["name"]])
        if item is None:
            problems.append(f"the model {resources[model['name']]} is not on the gateway")
            continue
        properties = item.get("properties") or {}
        deployment = properties.get("deployment") or {}
        safety = [p for p in properties.get("policies") or [] if isinstance(p, dict) and p.get("type") == "contentSafety"]
        wrong = []
        if deployment.get("modelName") != model["name"] or deployment.get("modelVersion") != model["version"]:
            wrong.append("model or version")
        if not str(deployment.get("resourceId") or "").lower().endswith(f"/accounts/{ctx.account}/deployments/{model['name']}".lower()):
            wrong.append("deployment")
        if len(safety) != 1 or any(safety[0].get(category) != CONTENT_SAFETY for category in CATEGORIES):
            wrong.append(f"content safety at {CONTENT_SAFETY}")
        if wrong:
            problems.append(f"the model {resources[model['name']]} differs from its template ({', '.join(wrong)})")
    extra_models = sorted(plain(n, 40) for n in models if n not in set(resources.values()))
    if extra_models:
        problems.append(f"a model on the gateway that environment/models.json does not list: {', '.join(extra_models)}")
    items = ctx.read("The aliases of the AI Gateway", f"{ctx.workspace_path}/aliases", GATEWAY_API, pages=True)
    aliases = {i.get("name"): i for i in items if isinstance(i, dict)}
    for model in ctx.models:
        item = aliases.get(model["name"])
        if item is None:
            problems.append(f"the alias {plain(model['name'])} is not there")
            continue
        targets = [t for t in (item.get("properties") or {}).get("backendModels") or [] if isinstance(t, dict)]
        if len(targets) != 1 or not str(targets[0].get("resourceId") or "").lower().endswith(f"/models/{resources[model['name']]}".lower()):
            problems.append(f"the alias {plain(model['name'])} does not point to the model {resources[model['name']]} alone")
    extra_aliases = sorted(plain(n, 40) for n in aliases if n not in {m["name"] for m in ctx.models})
    if extra_aliases:
        problems.append(f"an alias that environment/models.json does not list: {', '.join(extra_aliases)}")
    if problems:
        return failed("; ".join(problems) + ".")
    return passed(f"The gateway holds the provider of the Foundry resource, one model and one alias for each model of environment/models.json ({len(ctx.models)}), each with content safety at {CONTENT_SAFETY}, and nothing else.")


@control("I-gateway-roles", "L1")
def gateway_roles(ctx: Context) -> Outcome:
    identities = {"cases": ctx.principal("cases"), "foundry-project": ctx.principal("foundry-project"), "operator": ctx.principal("operator")}
    items = ctx.read("The role assignments at the AI Gateway", f"{ctx.gateway_path}/providers/Microsoft.Authorization/roleAssignments", AUTHORIZATION_API, query="%24filter=atScope()", pages=True)
    here = ctx.gateway_path.lower()
    direct = []
    for item in items:
        properties = (item or {}).get("properties") or {}
        if str(properties.get("scope") or "").lower().rstrip("/") == here:
            direct.append((str(properties.get("roleDefinitionId") or "").rsplit("/", 1)[-1].lower(), str(properties.get("principalId") or "").lower(), str(properties.get("principalType") or "")))
    problems = []
    named = {principal for principal in identities.values() if principal}
    for role, principal, kind in direct:
        if role != GATEWAY_MODELS_USER:
            problems.append(f"the principal {short(principal)} holds the role {short(role)} on the gateway, and only AI Gateway Models User is meant to be held there")
        elif principal not in named:
            problems.append(f"the principal {short(principal)} ({plain(kind)}) holds AI Gateway Models User on the gateway and is not on the access list")
    for kind, principal in identities.items():
        if principal and (GATEWAY_MODELS_USER, principal) not in {(role, who) for role, who, _ in direct}:
            problems.append(f"the identity {kind} of the access list does not hold AI Gateway Models User on the gateway")
    if problems:
        return failed("; ".join(problems) + ".")
    absent = sorted(kind for kind, principal in identities.items() if not principal)
    listed = len([e for e in ctx.access.get("contracts", [])])
    return passed(f"Exactly the identities of the access list hold AI Gateway Models User on the gateway ({len(named)} of {listed}" + (f"; not made yet: {', '.join(absent)}" if absent else "") + "), and no other role is held there.")


@control("I-telemetry", "L1")
def telemetry(ctx: Context) -> Outcome:
    items = ctx.read("The telemetry exporters of the AI Gateway", f"{ctx.workspace_path}/telemetryExporters", GATEWAY_API, pages=True)
    exporters = [i for i in items if isinstance(i, dict)]
    if not exporters:
        return failed("The AI Gateway sends no telemetry: it has no exporter. The action gateway-telemetry makes it, after its prerequisites (environment/BOOTSTRAP.md).", closed=False)
    problems = []
    for exporter in exporters:
        properties = exporter.get("properties") or {}
        if properties.get("payloadCapture") is not False:
            problems.append(f"the exporter {plain(exporter.get('name'), 30)} does not say payloadCapture false (the service reports {plain(properties.get('payloadCapture')) or 'nothing'}): prompts and answers may reach the telemetry")
    if problems:
        return failed("; ".join(problems) + ".")
    exporter = next((e for e in exporters if e.get("name") == EXPORTER), None)
    if exporter is None:
        return failed(f"The exporter {EXPORTER} is not on the gateway (it holds {', '.join(plain(e.get('name'), 30) for e in exporters)}).", closed=False)
    properties = exporter.get("properties") or {}
    otel = properties.get("openTelemetry") or {}
    credentials = otel.get("credentials") or {}
    wrong = []
    if properties.get("kind") != "OpenTelemetry":
        wrong.append("its kind is not OpenTelemetry")
    if set(credentials) - {"managedIdentity"} or (credentials.get("managedIdentity") or {}).get("resource") != MONITOR_AUDIENCE:
        wrong.append("it does not sign in with the gateway's own identity alone (audience " + MONITOR_AUDIENCE + "), or it carries another credential")
    component = ctx.read("The Application Insights component", ctx.component_path, INSIGHTS_API).get("properties") or {}
    for field, key in (("tracesEndpoint", "OTLPTracesEndpoint"), ("logsEndpoint", "OTLPLogsEndpoint"), ("metricsEndpoint", "OTLPMetricsEndpoint")):
        if component.get(key) and str(otel.get(field) or "").rstrip("/") != str(component.get(key)).rstrip("/"):
            wrong.append(f"its {field} is not the component's")
    if wrong:
        return failed(f"The exporter {EXPORTER} differs from its template: {'; '.join(wrong)}.", closed=False)
    ingestion = str(component.get("AzureMonitorWorkspaceIngestionMode") or "")
    return passed(f"The exporter {EXPORTER} sends logs, traces and metrics to the project's component with the gateway's own identity and no key, and payloadCapture is false: no prompt and no answer is sent"
                  + (f" (the component's OpenTelemetry ingestion is {plain(ingestion)})." if ingestion else "."))


@control("I-connection", "L2")
def connection(ctx: Context) -> Outcome:
    foundry = load_sibling("foundry_check_of_the_drift_check", "foundry-check.py")
    gateway_doc = ctx.read("The Foundry resource's gateway", ctx.gateway_path, GATEWAY_API)
    host = str(((gateway_doc.get("properties") or {}).get("frontend") or {}).get("defaultHostname") or "")
    name = ctx.params.AIGATEWAY_CONNECTION_NAME
    base = f"{ctx.account_path}/projects/{ctx.project}/connections"
    document = ctx.read(f"The connection {name} of the project to the AI Gateway", f"{base}/{name}", FOUNDRY_API)
    if not host:
        return unknown("The AI Gateway does not report its host name yet, so the target of the project's connection cannot be compared with it.")
    findings = foundry.gateway_connection(document, host, name, ctx.models)
    bad = [text for ok, text in findings if not ok]
    items = ctx.read("The connections of the project", base, FOUNDRY_API, pages=True)
    traces = [c for c in items if isinstance(c, dict) and (c.get("properties") or {}).get("category") == "AppInsights"]
    if len(traces) != 1 or (traces[0].get("properties") or {}).get("authType") not in ENTRA_AUTH_TYPES:
        bad.append("the project's connection to Application Insights is missing or is not made with an identity")
    others = [c for c in items if isinstance(c, dict) and (c.get("properties") or {}).get("category") not in ("AppInsights", "ApiManagement")]
    if others:
        bad.append("the project has a connection that the template does not make: " + ", ".join(plain(c.get("name"), 30) for c in others))
    if bad:
        return failed("; ".join(b.rstrip(".") for b in bad) + ".")
    return passed("The project's connection to the AI Gateway is the one of the template (ProjectManagedIdentity, the gateway's audience, host and path, every alias, no credentials), its traces go to Application Insights with an identity, and it has no other connection.")


def exemption_key(item: dict) -> str:
    properties = item.get("properties") or {}
    return f"{str(properties.get('policyAssignmentId') or '').rstrip('/').rsplit('/', 1)[-1]}/{item.get('name')}"


@control("I-policy-assignments", "L4")
def policy_assignments(ctx: Context) -> Outcome:
    path = ctx.at("Microsoft.Authorization/policyAssignments")
    items = ctx.read("The policy assignments of the project's group", path, POLICY_API, query="%24filter=atExactScope()", pages=True)
    by_name = {i.get("name"): i for i in items if isinstance(i, dict)}
    problems = []
    expected = {"meternaut-approved-models": ctx.params.APPROVED_MODELS_EFFECT, "meternaut-model-eligibility": ctx.params.MODEL_ELIGIBILITY_EFFECT}
    for name in OUR_ASSIGNMENTS:
        item = by_name.get(name)
        if item is None:
            problems.append(f"the assignment {name} is not on the group")
            continue
        properties = item.get("properties") or {}
        effect = ((properties.get("parameters") or {}).get("effect") or {}).get("value")
        if properties.get("enforcementMode") != "Default":
            problems.append(f"the assignment {name} is not enforced (enforcementMode {plain(properties.get('enforcementMode'))})")
        if effect != expected[name]:
            problems.append(f"the assignment {name} has the effect {plain(effect)}, and tools/environment-params.py says {expected[name]}")
    if problems:
        return failed("; ".join(problems) + ".")
    exemptions = ctx.read("The policy exemptions of the project's group", ctx.at("Microsoft.Authorization/policyExemptions"), EXEMPTION_API, query="%24filter=excludeExpired()", pages=True)
    found = sorted({exemption_key(i) for i in exemptions if isinstance(i, dict)})
    accepted = ctx.options.get("accepted_exemptions")
    optional = sorted(n for n in by_name if n in OPTIONAL_ASSIGNMENTS)
    held = f"The assignments {', '.join(OUR_ASSIGNMENTS)} are on the group with the effects of tools/environment-params.py" + (f", and {', '.join(optional)}" if optional else "")
    if accepted is None:
        return unknown(f"{held}. No baseline of the policy exemptions was accepted, so the {len(found)} that exist cannot be judged: set the repository variable DRIFT_ACCEPTED_EXEMPTIONS to the list "
                       f"{', '.join(found) or '(none)'} when the owner knows them.")
    fresh = [key for key in found if key not in accepted]
    if fresh:
        return failed(f"{held}, but a policy exemption exists that was not accepted: {', '.join(fresh)}. An exemption takes a control away, so it is a finding until the owner accepts it.")
    return passed(f"{held}. {len(found)} policy exemption(s) exist, and each was accepted by the owner.")


@control("I-policy-compliance", "L4")
def policy_compliance(ctx: Context) -> Outcome:
    query = ("policyresources\n| where type =~ 'microsoft.policyinsights/policystates'\n| where resourceGroup =~ '" + ctx.group.replace("'", "") + "'\n"
             "| where tostring(properties.complianceState) == 'NonCompliant'\n"
             "| extend Effect = tolower(tostring(properties.policyDefinitionAction)), Assignment = tostring(properties.policyAssignmentName), Reference = tostring(properties.policyDefinitionReferenceId), "
             "Type = tolower(tostring(properties.resourceType)), Resource = tostring(properties.resourceId)\n"
             "| summarize Resources = dcount(Resource) by Effect, Assignment, Reference, Type")
    try:
        rows = ctx.attempt("The compliance of the policies", lambda: ctx.reader.resource_graph(ctx.subscription, query), "Reader at the project's group, which Azure Resource Graph needs")
    except Missing:
        return unknown("Azure Resource Graph did not know the compliance of the policies.")
    except CannotRead as e:
        return unknown(str(e))
    deny = sorted({f"{r.get('Assignment')}/{r.get('Reference') or '-'}/{r.get('Type')}" for r in rows if isinstance(r, dict) and r.get("Effect") == "deny"})
    counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            counts[str(row.get("Effect") or "other")] = counts.get(str(row.get("Effect") or "other"), 0) + 1
    ours = [r for r in rows if isinstance(r, dict) and str(r.get("Assignment")) in OUR_ASSIGNMENTS + OPTIONAL_ASSIGNMENTS]
    by_effect = ", ".join(f"{effect}: {number}" for effect, number in sorted(counts.items())) or "none"
    if ours:
        return failed("A resource is not compliant with a policy of Meternaut's own: " + ", ".join(sorted({f"{r.get('Assignment')} ({plain(r.get('Type'), 50)})" for r in ours})) + ".")
    accepted = ctx.options.get("accepted_deny")
    if accepted is None:
        return unknown(f"Non-compliant policy and resource pairs by effect: {by_effect}. No baseline of the non-compliant Deny policies was accepted, so the {len(deny)} that exist cannot be judged: set the repository "
                       f"variable DRIFT_ACCEPTED_DENY to the list {', '.join(deny) or '(none)'} when the owner knows them.")
    fresh = [key for key in deny if key not in accepted]
    if fresh:
        return failed(f"A policy with the effect Deny is non-compliant that was not accepted: {', '.join(fresh)}.")
    return passed(f"No resource is non-compliant with a policy of Meternaut's own, and every Deny policy that is non-compliant was accepted by the owner ({len(deny)}). Pairs by effect: {by_effect}.")


@control("I-defender", "L4")
def defender(ctx: Context) -> Outcome:
    if not ctx.options.get("read_subscription"):
        return unknown("Not read: the plans of Defender for Cloud are set on the subscription, outside the project's group, where no identity of this project has a right (AGENTS.md rule 18). The owner reads it in the "
                       "portal (Defender for Cloud, Environment settings, plan AI services). Microsoft does not cover every region, Sweden Central among them, so the plan alone would not say that the resource is covered.")
    try:
        document = ctx.attempt("The Defender plan", lambda: ctx.reader.get(f"/subscriptions/{ctx.subscription}/providers/Microsoft.Security/pricings/AI", SECURITY_API), "Reader on the subscription")
    except Missing:
        return unknown("The subscription has no Defender plan named AI.")
    except CannotRead as e:
        return unknown(str(e))
    tier = (document.get("properties") or {}).get("pricingTier")
    if tier == "Standard":
        return passed("The Defender plan AI is Standard on the subscription. The plan is read, not the coverage: Microsoft does not cover every region, Sweden Central among them.")
    return failed(f"The Defender plan AI is {plain(tier)}, not Standard.", closed=False)


WRITE_FREE = re.compile(r"/read$|^Microsoft\.Authorization/\*/read$", re.I)


def writes(definition: dict) -> bool:
    """Whether a role definition holds an action of Azure Resource Manager that is not a read (a data action is not one)."""
    permissions = (definition.get("properties") or {}).get("permissions") or []
    return any(isinstance(action, str) and not WRITE_FREE.search(action) for p in permissions for action in (p.get("actions") or []))


@control("I-role-assignments", "L4")
def role_assignments(ctx: Context) -> Outcome:
    items = ctx.read("The role assignments of the project's group", ctx.at("Microsoft.Authorization/roleAssignments"), AUTHORIZATION_API, query="%24filter=atScope()", pages=True)
    here = ctx.group_path.lower()
    own = {
        "the cases app": ctx.principal("cases"), "the Foundry project": ctx.principal("foundry-project"), "the Operator": ctx.principal("operator"),
        "the Foundry resource": str((ctx.read("The Foundry resource", ctx.account_path, ACCOUNT_API).get("identity") or {}).get("principalId") or "").lower(),
        "the AI Gateway": str((ctx.read("The AI Gateway", ctx.gateway_path, GATEWAY_API).get("identity") or {}).get("principalId") or "").lower(),
    }
    try:
        own["the console's sign-in"] = str((ctx.read("The console's identity", ctx.at(f"Microsoft.ManagedIdentity/userAssignedIdentities/{CONSOLE_IDENTITY}"), IDENTITY_API).get("properties") or {}).get("principalId") or "").lower()
    except Missing:
        own["the console's sign-in"] = ""
    names = {principal: who for who, principal in own.items() if principal}
    definitions: dict[str, dict] = {}
    problems = []
    unreadable = []
    others = set()
    for item in items:
        properties = (item or {}).get("properties") or {}
        if str(properties.get("scope") or "").lower().rstrip("/") != here:
            continue
        role = str(properties.get("roleDefinitionId") or "")
        principal = str(properties.get("principalId") or "").lower()
        if role not in definitions:
            try:
                definitions[role] = ctx.read(f"The role definition {tail(role)}", role, AUTHORIZATION_API) if role.startswith("/") else {}
            except (Missing, CannotRead):
                definitions[role] = {}
        if not definitions[role]:
            if principal in names:
                unreadable.append(tail(role)[:8] + "...")
            continue
        if principal in names:
            if writes(definitions[role]):
                problems.append(f"{names[principal]} holds a role at the group that can change Azure ({tail(role)[:8]}...): no identity of Meternaut holds a right to change Azure (AGENTS.md rule 29)")
        elif writes(definitions[role]):
            others.add(principal)
    if problems:
        return failed("; ".join(sorted(set(problems))) + ".")
    if unreadable:
        return unknown(f"The role definition(s) {', '.join(sorted(set(unreadable)))} held by an identity of Meternaut at the group could not be read, so it is not known whether they can change Azure.")
    return passed(f"None of the {len(names)} identities of Meternaut that run at the group holds a role that can change Azure; {len(others)} other principal(s) hold one at the group (the deploy identity and the people who "
                  "approve a change: they are not judged here).")


FOUNDRY_DATA = re.compile(r"^(\*|microsoft\.cognitiveservices/)", re.I)
PROJECT_LEVEL, RESOURCE_LEVEL = "the Foundry project", "the Foundry resource"


def level_of(ctx: Context, scope: object) -> str:
    """Where a role is held, in words, for the scopes that `atScope()` lists: the Foundry project and everything above it."""
    text = str(scope or "").lower().rstrip("/")
    if text == ctx.project_path.lower():
        return PROJECT_LEVEL
    if text == ctx.account_path.lower():
        return RESOURCE_LEVEL
    if text == ctx.group_path.lower():
        return "the project's resource group"
    if re.fullmatch(r"/subscriptions/[^/]+", text):
        return "the subscription"
    if text.startswith("/providers/microsoft.management/managementgroups/"):
        return "a management group"
    return "the root of the tenant" if not text else "a scope above the project"


def reach_of(ctx: Context, role: str) -> tuple[str, str] | None:
    """The name of a role and what it holds beyond reading: "user" (Foundry User), "wider" (a wider role of Foundry), "writes" (an action of Azure Resource Manager that is not a read), "data" (a data action that
    reaches the Foundry resource, and so its model deployments, or every data action) or "" (nothing). None when the definition cannot be read."""
    guid = tail(role).lower()
    if guid == FOUNDRY_USER:
        return "Foundry User", "user"
    if guid in WIDER_FOUNDRY_ROLES:
        return WIDER_FOUNDRY_ROLES[guid], "wider"
    try:
        definition = ctx.read(f"The role definition {tail(role)}", role, AUTHORIZATION_API) if role.startswith("/") else {}
    except (Missing, CannotRead):
        definition = {}
    if not definition:
        return None
    properties = definition.get("properties") or {}
    name = plain(properties.get("roleName"), 50) or f"the role {tail(role)[:8]}..."
    if writes(definition):
        return name, "writes"
    if any(isinstance(data, str) and FOUNDRY_DATA.match(data) for p in properties.get("permissions") or [] for data in (p.get("dataActions") or [])):
        return name, "data"
    return name, ""


def judge_foundry_role(ctx: Context, who: str, principal: str, items: list, missing: str, purpose: str) -> Outcome:
    """What one identity holds at the Foundry project and at every scope above it, which is what `atScope()` lists (the Foundry resource, the group, the subscription, the management groups). The design is exactly
    Foundry User on the project. A role anywhere in that list that can change Azure, that holds data actions that reach the Foundry resource (and so its model deployments, which only the AI Gateway may call: AGENTS.md
    rule 15 (c)) or that is wider than Foundry User is a FAIL, whatever its scope; a role whose definition cannot be read is UNKNOWN, never a pass."""
    held = set()
    for item in items:
        properties = (item or {}).get("properties") or {}
        if str(properties.get("principalId") or "").lower() == principal:
            held.add((str(properties.get("scope") or ""), str(properties.get("roleDefinitionId") or "")))
    has_role = False
    elsewhere = False
    problems = []
    unreadable = []
    for scope, role in sorted(held):
        level = level_of(ctx, scope)
        reach = reach_of(ctx, role)
        if reach is None:
            unreadable.append(f"{tail(role)[:8]}... at {level}")
            continue
        name, kind = reach
        if kind == "user" and level == PROJECT_LEVEL:
            has_role = True
        elif kind:
            elsewhere = elsewhere or kind == "user"
            why = {"writes": "which can change Azure", "wider": "which is wider than Foundry User", "data": "which holds data actions of the Foundry resource", "user": "which is meant for the project alone"}[kind]
            if level != PROJECT_LEVEL and kind != "writes":
                why += ": a role there reaches the model deployments, and a role on the project alone does not"
            problems.append(f"{who} holds {name} {'on' if level in (PROJECT_LEVEL, RESOURCE_LEVEL) else 'at'} {level}, {why}")
    if not has_role and not elsewhere:
        problems.append(missing)
    if problems:
        return failed("; ".join(problems) + ".", closed=False)
    if unreadable:
        return unknown(f"The role(s) that {who} holds at or above the Foundry project could not be read ({', '.join(sorted(unreadable))}), so it is not known whether they reach beyond Foundry User.")
    return passed(f"{who[0].upper() + who[1:]} holds Foundry User on the Foundry project, and nothing wider there, on the Foundry resource or above them: {purpose}.")


def project_roles_of(ctx: Context) -> list:
    """The role assignments at the Foundry project and at every scope above it (`atScope()` lists them all). A project that is not there ends the control."""
    ctx.read("The Foundry project", ctx.project_path, FOUNDRY_API)
    return ctx.read("The role assignments at the Foundry project", f"{ctx.project_path}/providers/Microsoft.Authorization/roleAssignments", AUTHORIZATION_API, query="%24filter=atScope()", pages=True)


@control("I-operator-role", "L4")
def operator_role(ctx: Context) -> Outcome:
    """The roles that the Operator holds at the Foundry project and at every scope above it: Foundry User on the project, which the tools that check the agents from inside the network read the project with
    (docs/proposals/11-agent-harness-and-evaluation.md), and no role anywhere above that can change Azure or reaches the model deployments (rule 15 (c): they are called through the AI Gateway alone)."""
    operator = ctx.principal("operator")
    if not operator:
        return passed("The Operator's identity is not made yet (the action operator makes it), so it holds no role on the Foundry project; the action foundry gives it Foundry User there.")
    return judge_foundry_role(ctx, "the Operator", operator, project_roles_of(ctx),
                              "the Operator does not hold the role Foundry User on the Foundry project, so agents-drift, foundry-evals and foundry-redteam, which read the project with its identity, are answered 403 or 401 "
                              "(the action foundry gives it the role, after the action operator)",
                              "the tools that check the agents from inside the network read the project with it")


@control("I-project-role", "L4")
def project_role(ctx: Context) -> Outcome:
    """The same for the Foundry project's own identity, which a continuous evaluation rule runs as: Foundry User on the project and no role above it that can change Azure or reaches the model deployments."""
    items = project_roles_of(ctx)
    principal = ctx.principal("foundry-project")
    if not principal:
        return failed("The Foundry project has no identity of its own, so a continuous evaluation rule cannot run as it and no role is held for it (the action foundry makes the project with one).", closed=False)
    return judge_foundry_role(ctx, "the Foundry project's identity", principal, items,
                              "the Foundry project's identity does not hold the role Foundry User on the Foundry project, so a continuous evaluation rule cannot run as it (the action foundry gives it the role)",
                              "a continuous evaluation rule runs as it")


@control("I-network", "L4")
def network(ctx: Context) -> Outcome:
    items = ctx.read("The resources of the project's group", f"{ctx.group_path}/resources", RESOURCES_API, pages=True)
    seen = {str(i.get("type") or "").lower() for i in items if isinstance(i, dict)}
    unread = sorted(t for t in seen if t not in QUIET_TYPES and t not in READ_TYPES)
    problems = []
    accepted = []
    if "microsoft.storage/storageaccounts" in seen:
        storage = ctx.read(f"The storage account {ctx.storage}", ctx.at(f"Microsoft.Storage/storageAccounts/{ctx.storage}"), STORAGE_API).get("properties") or {}
        if storage.get("publicNetworkAccess") != "Disabled":
            problems.append("the storage account takes public traffic")
        if storage.get("allowSharedKeyAccess") is not False:
            problems.append("the storage account allows Shared Key access")
    if "microsoft.web/sites" in seen:
        site = ctx.read("The cases app", ctx.site_path, WEB_API).get("properties") or {}
        wanted = ctx.options.get("cases_public_access") or ctx.params.CASES_APP_PUBLIC_NETWORK_ACCESS
        if site.get("publicNetworkAccess") != wanted:
            problems.append(f"the cases app's public network access is {plain(site.get('publicNetworkAccess'))}, and the accepted value is {plain(wanted)}")
        elif wanted == "Enabled":
            accepted.append("the cases app's web page is public on purpose (it has its own sign-in)")
    for kind, path, api, label in (("microsoft.insights/components", ctx.component_path, INSIGHTS_API, "Application Insights"), ("microsoft.operationalinsights/workspaces", ctx.at(f"Microsoft.OperationalInsights/workspaces/{WORKSPACE}"), WORKSPACE_API, "the workspace")):
        if kind in seen:
            properties = ctx.read(label, path, api).get("properties") or {}
            if "Enabled" in (properties.get("publicNetworkAccessForIngestion"), properties.get("publicNetworkAccessForQuery")):
                accepted.append(f"{label} takes ingestion and queries over the public network: the Azure Monitor private link scope is not built")
    accepted.append("the AI Gateway's front door is public because the service has no private one: it needs a Microsoft Entra token and a role")
    if problems:
        return failed("; ".join(problems) + ".")
    if unread:
        return unknown("These kinds of resource are in the group and this check does not read them: " + ", ".join(plain(t, 60) for t in unread) + ". Teach the check what they expose, or remove them.")
    return passed("Everything else is private (the Foundry resource's own flags are read by I-foundry-flags). Public on purpose or by necessity: " + "; ".join(accepted) + ".")


@control("I-entra-console", "L3")
def entra_console(ctx: Context) -> Outcome:
    client = ctx.options.get("console_client_id")
    if not ctx.options.get("graph") or not client:
        return unknown("Not read: the app registration of the console is in the directory, and the identity that runs this has no right to read the directory. Run it with --graph and --console-client-id, "
                       "as an identity that holds Application.Read.All.")
    try:
        document = ctx.attempt("The app registration of the console", lambda: ctx.reader.graph(f"applications(appId='{quote(str(client))}')?$select=passwordCredentials,keyCredentials"), "Application.Read.All")
    except Missing:
        return failed("The app registration of the console is not in the directory.", closed=False)
    except CannotRead as e:
        return unknown(str(e))
    if document.get("passwordCredentials") or document.get("keyCredentials"):
        return failed("The app registration of the console holds a secret or a certificate: it signs in with the federated credential of a managed identity alone (AGENTS.md rule 23).")
    return passed("The app registration of the console holds no secret and no certificate.")


@control("I-entra-agents", "L3")
def entra_agents(ctx: Context) -> Outcome:
    if not ctx.options.get("graph"):
        return unknown("Not read: the agent identities are in the directory, and the identity that runs this has no right to read the directory. Run it with --graph, as an identity that holds Application.Read.All.")
    prefix = ctx.account.replace("'", "")

    def collect():
        expression = quote(f"startswith(displayName,'{prefix}-') and servicePrincipalType eq 'ServiceIdentity'", safe="(),'")
        found = ctx.reader.graph(f"servicePrincipals?$filter={expression}&$select=id,displayName&$top=50")
        identities = [i for i in found.get("value") or [] if isinstance(i, dict) and i.get("id")]
        without = []
        for identity in identities:
            owners = ctx.reader.graph(f"servicePrincipals/{identity['id']}/owners?$select=id&$top=1").get("value") or []
            sponsors = ctx.reader.graph(f"servicePrincipals/{identity['id']}/sponsors?$select=id&$top=1").get("value") or []
            if not owners and not sponsors:
                without.append(plain(identity.get("displayName"), 60))
        return identities, without
    try:
        identities, without = ctx.attempt("The agent identities", collect, "Application.Read.All")
    except Missing:
        return unknown("No agent identity of the Foundry resource was found in the directory.")
    except CannotRead as e:
        return unknown(str(e))
    if not identities:
        return unknown("No agent identity of the Foundry resource was found in the directory.")
    if without:
        return failed(f"Agent identities with neither an owner nor a sponsor: {', '.join(without)}.", closed=False)
    return passed(f"Every one of the {len(identities)} agent identities has an owner or a sponsor.")


@control("I-agent-365", "L3")
def agent365(ctx: Context) -> Outcome:
    """Microsoft Agent 365 registers and logs the prompt agents of a Foundry resource by itself while the resource's logging flag is on (docs/proposals/10-ai-security-and-governance.md). The flag and its status
    are read at the generally available API version, on 2026-11-08, from the real resource: it was true and Enabled with nothing in the template that sets it, so the platform's default is what is read here, and nothing
    is written. What no API shows (the licence, the one-time consent of a Global Administrator, the registry's list of agents in the Microsoft 365 admin center) is for a person to look at."""
    properties = ctx.read(f"The Foundry resource {ctx.account}", ctx.account_path, FOUNDRY_API).get("properties") or {}
    logging_on, status = properties.get("a365LoggingEnabled"), properties.get("a365Status")
    if logging_on is None and status is None:
        return unknown("The Foundry resource reports no Agent 365 setting (a365LoggingEnabled and a365Status are not in its properties), so it is not known whether its agents are registered and logged. "
                       "The registry itself is in the Microsoft 365 admin center, and no API of this check shows it: a person looks.")
    if logging_on is False:
        return failed("Agent 365 logging is off on the Foundry resource (a365LoggingEnabled is false): its agents are neither registered nor logged by Agent 365. Nothing in the repository switches it off, so it was "
                      "changed outside the workflow.", closed=False)
    if logging_on is True and status == "Enabled":
        return passed("Agent 365 logging is on for the Foundry resource (a365LoggingEnabled true) and the platform reports its status Enabled. That the tenant holds the licence, that the one-time consent of a "
                      "Global Administrator was given and that the registry lists the two agents is read in the Microsoft 365 admin center: portal only, a person checks.")
    return unknown(f"Agent 365 logging is {'on' if logging_on is True else 'not reported'} and the platform reports the status {plain(status) or 'nothing'}, not Enabled: that depends on the tenant (the licence, "
                   "the one-time consent of a Global Administrator), which this check cannot read.")


@control("I-release", "L4")
def release(ctx: Context) -> Outcome:
    tags = ctx.read("The cases app", ctx.site_path, WEB_API).get("tags") or {}
    live_commit = str(tags.get("meternaut-build-commit") or "").lower()
    live_digest = str(tags.get("meternaut-package-sha256") or "").lower()
    if not live_commit and not live_digest:
        return unknown("The cases app carries no record of the release that runs: the action cases writes the tags meternaut-build-commit and meternaut-package-sha256 after it has published the code and the app answers, "
                       "so either it has not run since they were added, or its last run stopped before that (a deploy takes the tags off, and the publish puts them back).")
    commit = str(ctx.options.get("commit") or "").lower()
    main_digest = ""
    if ctx.options.get("app_dir"):
        try:
            main_digest = load_sibling("source_digest_of_the_drift_check", "source-digest.py").digest(Path(ctx.options["app_dir"]))
        except Exception as e:  # a folder that is not the app: the comparison by digest is then not possible
            return unknown(f"The digest of the app's files at main could not be worked out: {plain(e, 120)}.")
    if not commit and not main_digest:
        return unknown(f"The app runs commit {live_commit[:12] or 'unknown'}; no commit of main and no digest was given to compare it with.")
    if commit and live_commit == commit:
        return passed(f"The cases app runs commit {commit[:12]}, which is main.")
    if main_digest and live_digest:
        if live_digest == main_digest:
            return passed(f"The cases app runs commit {live_commit[:12] or 'unknown'} and main is {commit[:12] or 'newer'}, and the digest of the app's own files is the same: main changed nothing of the app.")
        return failed(f"The cases app runs commit {live_commit[:12] or 'unknown'} with the digest {live_digest[:12]}, and main has {commit[:12] or 'a newer commit'} with the digest {main_digest[:12]}: the app is not "
                      "the code of main. Either a merge has not been deployed yet (run the action cases), or the app was changed outside the workflow.", closed=False)
    if commit and live_commit:
        return failed(f"The cases app runs commit {live_commit[:12]} and main is {commit[:12]}, and the digest of the app's files was not compared: a merge has not been deployed yet (run the action cases), "
                      "or the app was changed outside the workflow.", closed=False)
    return unknown(f"The app runs commit {live_commit[:12] or 'unknown'} and main is {commit[:12] or 'unknown'}; the app has no commit or no digest recorded, so the files cannot be compared.")


LINE = re.compile(r"^drift\.(pass|fail|unknown)\b")


@control("I-heartbeat", "L4")
def heartbeat(ctx: Context) -> Outcome:
    rows = in_app_rows(ctx)
    if isinstance(rows, Outcome):
        return rows
    seen = [parse_when(r.get("timestamp")) for r in rows if r.get("line") in ("drift.pass", "drift.fail")]
    seen = [w for w in seen if w]
    if not seen:
        return unknown(f"The app's own drift check logged no drift.pass or drift.fail line in {LOOK_BACK_DAYS} days: it has not run yet, or it is silent. The alert rule alert-meternaut-ai-drift-heartbeat fires after {HEARTBEAT_HOURS} hours; this check does not depend on it.")
    age = ctx.now - max(seen)
    if age > timedelta(hours=HEARTBEAT_HOURS):
        return failed(f"The app's own drift check last logged a result {int(age.total_seconds() // 3600)} hours ago, and it runs daily (the limit is {HEARTBEAT_HOURS} hours): it has stopped, or the app cannot be trusted to say so.")
    return passed(f"The app's own drift check logged a result {int(age.total_seconds() // 3600)} hours ago (the limit is {HEARTBEAT_HOURS} hours).")


@control("I-inapp-results", "L2")
def in_app_results(ctx: Context) -> Outcome:
    rows = in_app_rows(ctx)
    if isinstance(rows, Outcome):
        return rows
    fresh = [r for r in rows if (parse_when(r.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)) > ctx.now - timedelta(hours=HEARTBEAT_HOURS)]
    if not fresh:
        return unknown("The app's own drift check has no result from the last day, so what it sees in the Foundry project (the agents, their tools and instructions) is not known here.")
    failing = sorted(plain(r.get("control"), 40) for r in fresh if r.get("line") == "drift.fail")
    if failing:
        return failed(f"The app's own drift check reports a failing control: {', '.join(failing)}. The app switches the investigation off by itself; a person puts it back after the cause is fixed.")
    unsure = [r for r in fresh if r.get("line") == "drift.unknown"]
    return passed(f"The app's own drift check reports {len(fresh) - len(unsure)} control(s) passing" + (f" and {len(unsure)} it could not read" if unsure else "") + ", none failing.")


def in_app_rows(ctx: Context):
    if "in_app" in ctx.cache:
        return ctx.cache["in_app"]
    query = (f"traces\n| where timestamp > ago({LOOK_BACK_DAYS}d)\n| where message startswith 'drift.pass ' or message startswith 'drift.fail ' or message startswith 'drift.unknown '\n"
             "| extend line = tostring(split(message, ' ')[0]), body = parse_json(substring(message, indexof(message, ' ') + 1))\n| extend control = tostring(body.control)\n"
             "| summarize arg_max(timestamp, line) by control\n| project control, line, timestamp")
    try:
        result = ctx.attempt("The lines of the app's own drift check", lambda: ctx.reader.query_component(ctx.component_path, query), "Reader on the Application Insights component")
    except Missing:
        result = unknown("The Application Insights component is not there, so the lines of the app's own drift check cannot be read.")
    except CannotRead as e:
        result = unknown(str(e))
    ctx.cache["in_app"] = result
    return result


@control("I-alerts", "L4")
def alerts(ctx: Context) -> Outcome:
    items = ctx.read("The alert rules of the project's group", ctx.at("Microsoft.Insights/scheduledQueryRules"), ALERT_API, pages=True)
    by_name = {i.get("name"): i for i in items if isinstance(i, dict)}
    wanted = [f"alert-meternaut-ai-{rule}" for rule in ALERT_RULES]
    callers = [c for c in (ctx.principal(k) for k in ("cases", "foundry-project", "operator")) if c]
    if callers:
        wanted.append(f"alert-meternaut-ai-{ALERT_RULE_OF_ACCESS_LIST}")
    problems = []
    for name in wanted:
        rule = by_name.get(name)
        if rule is None:
            problems.append(f"{name} is not there")
        elif (rule.get("properties") or {}).get("enabled") is not True:
            problems.append(f"{name} is disabled")
        elif not ((rule.get("properties") or {}).get("actions") or {}).get("actionGroups"):
            problems.append(f"{name} tells nobody (no action group)")
    group = ctx.read("The action group", ctx.at(f"Microsoft.Insights/actionGroups/{ACTION_GROUP}"), ACTION_GROUP_API) if not problems else {}
    if not problems and not [r for r in (group.get("properties") or {}).get("emailReceivers") or [] if isinstance(r, dict) and r.get("emailAddress")]:
        problems.append(f"the action group {ACTION_GROUP} has no e-mail receiver")
    workbooks = ctx.read("The workbooks of the project's group", ctx.at("Microsoft.Insights/workbooks"), WORKBOOK_API, query="category=workbook&canFetchContent=false", pages=True) if not problems else []
    if not problems and not [w for w in workbooks if isinstance(w, dict) and (w.get("properties") or {}).get("displayName") == WORKBOOK_NAME]:
        problems.append(f"the workbook {WORKBOOK_NAME} is not there")
    if problems:
        return failed("; ".join(problems) + ". The action governance makes them.", closed=False)
    return passed(f"The {len(wanted)} alert rules are on and tell the owner by e-mail, and the workbook {WORKBOOK_NAME} is there.")


@control("I-diagnostics", "L4")
def diagnostics(ctx: Context) -> Outcome:
    items = ctx.read("The diagnostic settings of the Foundry resource", f"{ctx.account_path}/providers/Microsoft.Insights/diagnosticSettings", DIAGNOSTIC_API, pages=True)
    sending = []
    for item in items:
        properties = (item or {}).get("properties") or {}
        enabled = [log for log in properties.get("logs") or [] if isinstance(log, dict) and log.get("enabled") is True]
        if properties.get("workspaceId") and enabled:
            sending.append(plain(item.get("name"), 40))
    if not sending:
        return failed("No diagnostic setting sends the logs of the Foundry resource to a workspace: the landing zone's policy makes one, and the action governance makes one where it does not.", closed=False)
    return passed(f"The logs of the Foundry resource go to a workspace ({len(sending)} setting(s)).")


def run_controls(ctx: Context, only: set[str] | None = None) -> tuple[list[dict], set[str]]:
    """The result of every control, in order, and the ids of those that failed closed."""
    results: list[dict] = []
    closed: set[str] = set()
    for control_id, layer, function in CONTROLS:
        if only and control_id not in only:
            continue
        read_at = ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            outcome = function(ctx)
        except Missing as e:
            outcome = failed(f"{e} is not there.")
        except CannotRead as e:
            outcome = unknown(str(e))
        except Refused as e:
            outcome = unknown(f"The check tried a call that is not a read and was stopped: {e}")
        except Exception as e:  # a control that breaks says so, and never says PASS
            outcome = unknown(f"This control could not run ({type(e).__name__}: {plain(e, 120)}).")
        results.append({"control": control_id, "layer": layer, "state": outcome.state, "detail": outcome.detail, "readAt": read_at})
        if outcome.state == FAIL and outcome.closed:
            closed.add(control_id)
    return results, closed


def report_of(results: list[dict], closed: set[str], ctx: Context) -> dict:
    counts = {state: sum(1 for r in results if r["state"] == state) for state in (PASS, FAIL, UNKNOWN)}
    return {"report": "meternaut-drift-control-plane", "readAt": ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ"), "summary": counts, "failClosed": sorted(closed), "controls": results}


def markdown_of(report: dict) -> str:
    counts, closed = report["summary"], set(report["failClosed"])
    lines = [f"### Drift check, control plane: {counts[PASS]} PASS, {counts[FAIL]} FAIL, {counts[UNKNOWN]} UNKNOWN", ""]
    if closed:
        lines += [f"**Fail-closed controls that failed: {', '.join(sorted(closed))}.** The agents run outside what was designed: a person switches the investigation off until the cause is fixed.", ""]
    lines += [f"Read at {report['readAt']}. UNKNOWN is never PASS: it says what this identity could not read, and why.", "", "| State | Control | Layer | What was read |", "| --- | --- | --- | --- |"]
    order = {FAIL: 0, UNKNOWN: 1, PASS: 2}
    for result in sorted(report["controls"], key=lambda r: (order[r["state"]], r["control"])):
        mark = " (fail-closed)" if result["control"] in closed else ""
        lines.append(f"| {result['state']}{mark} | {result['control']} | {result['layer']} | {result['detail'].replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def read_json(path: str, what: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Problem(f"{path} is not a readable JSON file ({what})")


def build_context(args, reader: Reader, now: datetime | None = None) -> Context:
    models = read_json(args.models, "the models")
    policies = read_json(args.policies, "the gateway-wide policies")
    access = read_json(args.access_list, "the access list")
    options = {"commit": args.commit, "app_dir": args.app_dir, "read_subscription": args.read_subscription, "graph": args.graph, "console_client_id": args.console_client_id,
              "cases_public_access": args.cases_public_access, "now": now,
              "accepted_exemptions": keys_of(args.accepted_exemptions) if args.accepted_exemptions is not None else None,
              "accepted_deny": keys_of(args.accepted_deny) if args.accepted_deny is not None else None}
    for name, value in (("--subscription", args.subscription), ("--resource-group", args.resource_group)):
        if not value:
            raise Problem(f"{name} is required")
    return Context(reader, args.subscription, args.resource_group, models, policies, access, options)


def parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true", help="run every control against a fake estate, then break one thing at a time; calls nothing")
    parser.add_argument("--subscription")
    parser.add_argument("--resource-group")
    parser.add_argument("--models", default="environment/models.json")
    parser.add_argument("--policies", default="environment/aigateway/policies.json")
    parser.add_argument("--access-list", default="environment/aigateway/contracts.json")
    parser.add_argument("--commit", default="", help="the commit of main that the cases app is compared with (GITHUB_SHA)")
    parser.add_argument("--app-dir", default="", help="the app's folder at that commit (src/case-functions), for the digest of its own files")
    parser.add_argument("--accepted-exemptions", default=None, help="the policy exemptions that the owner knows of, as assignment/exemption, comma separated (the repository variable DRIFT_ACCEPTED_EXEMPTIONS); unset: not judged")
    parser.add_argument("--accepted-deny", default=None, help="the non-compliant Deny policies that the owner knows of, as assignment/reference/type, comma separated (DRIFT_ACCEPTED_DENY); unset: not judged")
    parser.add_argument("--cases-public-access", default="", choices=("", "Enabled", "Disabled"), help="the public network access that the cases app is accepted to have (default: the constant of tools/environment-params.py)")
    parser.add_argument("--read-subscription", action="store_true", help="also read the Defender plan, which is set on the subscription (needs Reader there)")
    parser.add_argument("--graph", action="store_true", help="also read Microsoft Graph (the console's app registration, the agent identities); needs Application.Read.All")
    parser.add_argument("--console-client-id", default="", help="the application (client) id of the console's app registration; with --graph")
    parser.add_argument("--only", default="", help="only these controls, comma separated")
    parser.add_argument("--json", default="", help="a file to write the JSON report to")
    parser.add_argument("--summary", default="", help="a file to append the Markdown report to (the step summary of a workflow run)")
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS, help=f"seconds that one read of Azure may take (default {TIMEOUT_SECONDS})")
    return parser.parse_args(argv)


def main(argv=None, az: Runner | None = None, now: datetime | None = None) -> int:
    args = parse(argv)
    if args.selftest:
        return selftest()
    if args.timeout < 1:
        print("error: --timeout is a number of seconds, one or more", file=sys.stderr)
        return 2
    reader = Reader(az or (lambda arguments: run_az(arguments, args.timeout)))
    try:
        ctx = build_context(args, reader, now)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    only = {part.strip() for part in args.only.split(",") if part.strip()}
    known = {control_id for control_id, _, _ in CONTROLS}
    if only - known:
        print(f"error: unknown control(s): {', '.join(sorted(only - known))}; they are {', '.join(sorted(known))}", file=sys.stderr)
        return 2
    results, closed = run_controls(ctx, only or None)
    report = report_of(results, closed, ctx)
    text = markdown_of(report)
    print(text)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write(text)
    failing = report["summary"][FAIL]
    if failing:
        print(f"{failing} control(s) FAILED" + (f", {len(closed)} of them fail-closed ({', '.join(sorted(closed))})" if closed else ", none of them fail-closed") + ". The run fails; nothing is repaired from here.", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The fake estate of --selftest, and of the tests of this tool: an Azure that is as the repository says, to the shapes that the real services answered with (read-only, 2026-11-08).

SELFTEST_SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
SELFTEST_GROUP = "rg-example"
SELFTEST_NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
SELFTEST_COMMIT = "a" * 40
SELFTEST_DIGEST = "b" * 64
SELFTEST_IDS = {"cases": "12345678-dddd-eeee-ffff-123456789012", "foundry-project": "12345678-eeee-ffff-1111-123456789012", "operator": "12345678-aaaa-bbbb-cccc-123456789012",
                "account": "12345678-1111-2222-3333-123456789012", "gateway": "12345678-4444-5555-6666-123456789012", "console": "12345678-7777-8888-9999-123456789012",
                "deploy": "12345678-0000-0000-0000-123456789012", "stranger": "12345678-9999-9999-9999-123456789012"}
SELFTEST_READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
SELFTEST_OPENAI_USER = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"


def assignment_of(scope: str, role: str, principal: str, kind: str = "ServicePrincipal") -> dict:
    """A role assignment as Azure answers with it: the role definition is named by its path in the subscription."""
    return {"properties": {"scope": scope, "roleDefinitionId": f"/subscriptions/{SELFTEST_SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/{role}", "principalId": principal, "principalType": kind}}


def fake_estate(models: list[dict], policies: list[dict], names: dict[str, str]) -> dict[str, object]:
    """A dictionary from a path (lower case, without the query) to the document that Azure answers with, for every read of the controls, in the state that the repository asks for."""
    sub, group = SELFTEST_SUBSCRIPTION, SELFTEST_GROUP
    base = f"/subscriptions/{sub}/resourceGroups/{group}"
    account, gateway = names["account"], names["gateway"]
    account_path = f"{base}/providers/Microsoft.CognitiveServices/accounts/{account}"
    gateway_path = f"{base}/providers/Microsoft.ApiManagement/aigateways/{gateway}"
    workspace = f"{gateway_path}/workspaces/default"
    host = f"{gateway}.swedencentral.ai.gateway.azure.com"
    resources = {m["name"]: m["name"].replace(".", "-") for m in models}
    guardrail = names["guardrail"]
    connection_models = json.dumps([{"name": m["name"], "properties": {"model": {"name": m["name"], "version": m["version"], "format": "OpenAI"}}} for m in models])
    estate: dict[str, object] = {
        account_path: {"kind": "AIServices", "identity": {"principalId": SELFTEST_IDS["account"]},
                       "properties": {"publicNetworkAccess": "Disabled", "disableLocalAuth": True, "allowProjectManagement": True, "networkAcls": {"defaultAction": "Deny", "ipRules": [], "virtualNetworkRules": []},
                                      "a365LoggingEnabled": True, "a365Status": "Enabled"}},
        f"{account_path}/deployments": {"value": [{"name": m["name"], "sku": {"name": m["sku"], "capacity": m.get("agentCapacity", m["capacity"])},
                                                  "properties": {"model": {"name": m["name"], "version": m["version"]}, "raiPolicyName": guardrail, "versionUpgradeOption": "NoAutoUpgrade"}} for m in models]},
        f"{account_path}/raiPolicies/{guardrail}": {"properties": {"mode": "Blocking", "basePolicyName": "Microsoft.DefaultV2",
                                                                    "contentFilters": [{"name": n, "source": s, "enabled": True, "blocking": True} for n, s in SHIELDS]}},
        f"{account_path}/models": {"value": [{"kind": "OpenAI", "model": {"name": m["name"], "version": m["version"], "lifecycleStatus": "GenerallyAvailable",
                                                                          "deprecation": {"inference": m["retirementDate"] + "T00:00:00Z"}, "skus": [{"name": m["sku"], "deprecationDate": m["retirementDate"] + "T00:00:00Z"}]}} for m in models]},
        f"{account_path}/projects/{names['project']}": {"identity": {"principalId": SELFTEST_IDS["foundry-project"]}},
        # What `atScope()` answers: the assignments at the project and those above it. The Operator holds Reader at the group by design; the deploy identity's Owner at the subscription is nobody's business here.
        f"{account_path}/projects/{names['project']}/providers/Microsoft.Authorization/roleAssignments": {"value": [
            assignment_of(f"{account_path}/projects/{names['project']}", FOUNDRY_USER, SELFTEST_IDS[k]) for k in ("cases", "foundry-project", "operator")] + [
            assignment_of(base, SELFTEST_READER, SELFTEST_IDS["operator"]),
            assignment_of(f"/subscriptions/{sub}", "8e3af657-a8ff-443c-a75c-2fe8c4bcb635", SELFTEST_IDS["deploy"], "User")]},
        f"{account_path}/projects/{names['project']}/connections": {"value": [
            {"name": "aigateway", "properties": {"category": "ApiManagement"}}, {"name": "appinsights", "properties": {"category": "AppInsights", "authType": "ProjectManagedIdentity"}}]},
        f"{account_path}/projects/{names['project']}/connections/aigateway": {"properties": {
            "category": "ApiManagement", "authType": "ProjectManagedIdentity", "audience": GATEWAY_AUDIENCE, "target": f"https://{host}{GATEWAY_PATH}", "isSharedToAll": False,
            "metadata": {"deploymentInPath": "false", "models": connection_models}}},
        f"{account_path}/providers/Microsoft.Insights/diagnosticSettings": {"value": [{"name": "setByPolicy", "properties": {"workspaceId": "/subscriptions/x/workspaces/central", "logs": [{"categoryGroup": "audit", "enabled": True}]}}]},
        gateway_path: {"identity": {"principalId": SELFTEST_IDS["gateway"], "type": "SystemAssigned"}, "properties": {"frontend": {"defaultHostname": host}}},
        workspace: {"properties": {"policies": copy.deepcopy(policies)}},
        f"{workspace}/modelProviders": {"value": [{"name": GATEWAY_PROVIDER, "properties": {"kind": "Foundry", "foundry": {"authentication": {"kind": "ManagedIdentity"}, "resourceIds": [account_path]}}}]},
        f"{workspace}/modelProviders/{GATEWAY_PROVIDER}/models": {"value": [{"name": resources[m["name"]], "properties": {
            "deployment": {"modelName": m["name"], "modelVersion": m["version"], "resourceId": f"{account_path}/deployments/{m['name']}"},
            "policies": [{"type": "contentSafety", **{c: CONTENT_SAFETY for c in CATEGORIES}}]}} for m in models]},
        f"{workspace}/aliases": {"value": [{"name": m["name"], "properties": {"aliasName": m["name"], "backendModels": [{"resourceId": f"{workspace}/modelProviders/{GATEWAY_PROVIDER}/models/{resources[m['name']]}"}]}} for m in models]},
        f"{gateway_path}/providers/Microsoft.Authorization/roleAssignments": {"value": [
            {"properties": {"scope": gateway_path, "roleDefinitionId": f"/providers/Microsoft.Authorization/roleDefinitions/{GATEWAY_MODELS_USER}", "principalId": SELFTEST_IDS[k], "principalType": "ServicePrincipal"}}
            for k in ("cases", "foundry-project", "operator")] + [
            {"properties": {"scope": f"/subscriptions/{sub}", "roleDefinitionId": "/providers/Microsoft.Authorization/roleDefinitions/owner", "principalId": SELFTEST_IDS["deploy"], "principalType": "User"}}]},
        f"{workspace}/telemetryExporters": {"value": [{"name": EXPORTER, "properties": {"kind": "OpenTelemetry", "payloadCapture": False, "openTelemetry": {
            "tracesEndpoint": "https://otlp.example/v1/traces", "logsEndpoint": "https://otlp.example/v1/logs", "metricsEndpoint": "https://otlp.example/v1/metrics",
            "credentials": {"managedIdentity": {"resource": MONITOR_AUDIENCE}}}}}]},
        f"{base}/providers/Microsoft.Insights/components/{COMPONENT}": {"properties": {"OTLPTracesEndpoint": "https://otlp.example/v1/traces", "OTLPLogsEndpoint": "https://otlp.example/v1/logs",
                                                                                          "OTLPMetricsEndpoint": "https://otlp.example/v1/metrics", "AzureMonitorWorkspaceIngestionMode": "Enabled",
                                                                                          "publicNetworkAccessForIngestion": "Enabled", "publicNetworkAccessForQuery": "Enabled"}},
        f"{base}/providers/Microsoft.OperationalInsights/workspaces/{WORKSPACE}": {"properties": {"publicNetworkAccessForIngestion": "Enabled", "publicNetworkAccessForQuery": "Enabled"}},
        f"{base}/providers/Microsoft.Authorization/policyAssignments": {"value": [
            {"name": "meternaut-approved-models", "properties": {"enforcementMode": "Default", "parameters": {"effect": {"value": names["approved_effect"]}}}},
            {"name": "meternaut-model-eligibility", "properties": {"enforcementMode": "Default", "parameters": {"effect": {"value": names["eligibility_effect"]}}}}]},
        f"{base}/providers/Microsoft.Authorization/policyExemptions": {"value": [{"name": "waiver", "properties": {"policyAssignmentId": "/providers/Microsoft.Authorization/policyAssignments/Deny-Public-Endpoints"}}]},
        f"{base}/providers/Microsoft.Authorization/roleAssignments": {"value": [
            {"properties": {"scope": base, "roleDefinitionId": "/providers/Microsoft.Authorization/roleDefinitions/contributor", "principalId": SELFTEST_IDS["deploy"]}},
            {"properties": {"scope": base, "roleDefinitionId": "/providers/Microsoft.Authorization/roleDefinitions/reader", "principalId": SELFTEST_IDS["cases"]}},
            {"properties": {"scope": base, "roleDefinitionId": "/providers/Microsoft.Authorization/roleDefinitions/queue-data", "principalId": SELFTEST_IDS["operator"]}}]},
        "/providers/microsoft.authorization/roledefinitions/contributor": {"properties": {"permissions": [{"actions": ["*"], "notActions": []}]}},
        "/providers/microsoft.authorization/roledefinitions/reader": {"properties": {"permissions": [{"actions": ["*/read"]}]}},
        "/providers/microsoft.authorization/roledefinitions/queue-data": {"properties": {"permissions": [{"actions": [], "dataActions": ["Microsoft.Storage/*/write"]}]}},
        f"/subscriptions/{sub}/providers/Microsoft.Authorization/roleDefinitions/{SELFTEST_READER}": {"properties": {"roleName": "Reader", "permissions": [{"actions": ["*/read"], "dataActions": []}]}},
        f"/subscriptions/{sub}/providers/Microsoft.Authorization/roleDefinitions/{SELFTEST_OPENAI_USER}": {"properties": {"roleName": "Cognitive Services OpenAI User", "permissions": [{
            "actions": ["Microsoft.CognitiveServices/*/read", "Microsoft.Authorization/roleAssignments/read", "Microsoft.Authorization/roleDefinitions/read"],
            "dataActions": ["Microsoft.CognitiveServices/accounts/OpenAI/*/read", "Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action", "Microsoft.CognitiveServices/accounts/OpenAI/responses/*"]}]}},
        f"{base}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{OPERATOR_IDENTITY}": {"properties": {"principalId": SELFTEST_IDS["operator"]}},
        f"{base}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{CONSOLE_IDENTITY}": {"properties": {"principalId": SELFTEST_IDS["console"]}},
        f"{base}/providers/Microsoft.Web/sites/{names['cases_app']}": {"identity": {"principalId": SELFTEST_IDS["cases"]}, "properties": {"publicNetworkAccess": "Enabled"},
                                                                       "tags": {"meternaut-build-commit": SELFTEST_COMMIT, "meternaut-package-sha256": SELFTEST_DIGEST}},
        f"{base}/providers/Microsoft.Storage/storageAccounts/{names['storage']}": {"properties": {"publicNetworkAccess": "Disabled", "allowSharedKeyAccess": False}},
        f"{base}/resources": {"value": [{"type": t} for t in ("Microsoft.Storage/storageAccounts", "Microsoft.CognitiveServices/accounts", "Microsoft.Web/sites", "Microsoft.Insights/components",
                                                              "Microsoft.OperationalInsights/workspaces", "Microsoft.Network/virtualNetworks", "Microsoft.ApiManagement/aigateways")]},
        f"{base}/providers/Microsoft.Insights/scheduledQueryRules": {"value": [{"name": f"alert-meternaut-ai-{rule}", "properties": {"enabled": True, "actions": {"actionGroups": ["/x/ag"]}}}
                                                                              for rule in (*ALERT_RULES, ALERT_RULE_OF_ACCESS_LIST)]},
        f"{base}/providers/Microsoft.Insights/actionGroups/{ACTION_GROUP}": {"properties": {"emailReceivers": [{"emailAddress": "owner@example.com"}]}},
        f"{base}/providers/Microsoft.Insights/workbooks": {"value": [{"properties": {"displayName": WORKBOOK_NAME}}]},
    }
    return estate


class FakeAz:
    """An `az` that answers from a fake estate, and refuses what is not a read. `rows` answers the two reads that need a POST."""

    def __init__(self, estate: dict[str, object], graph_rows: list | None = None, app_rows: list | None = None):
        self.estate = {k.lower(): v for k, v in estate.items()}
        self.graph_rows = [] if graph_rows is None else graph_rows
        self.app_rows = [] if app_rows is None else app_rows
        self.calls: list[list[str]] = []
        self.denied: set[str] = set()

    def __call__(self, arguments: list[str]) -> tuple[int, str, str]:
        self.calls.append(arguments)
        method = arguments[arguments.index("--method") + 1]
        url = arguments[arguments.index("--url") + 1]
        parts = urlsplit(url)
        path = parts.path.lower()
        if method == "post" and path == "/providers/microsoft.resourcegraph/resources":
            return 0, json.dumps({"data": self.graph_rows}), ""
        if method == "post" and path.endswith("/query"):
            columns = [{"name": n} for n in ("control", "line", "timestamp")]
            return 0, json.dumps({"tables": [{"columns": columns, "rows": [[r["control"], r["line"], r["timestamp"]] for r in self.app_rows]}]}), ""
        if method != "get":
            return 1, "", f"the fake estate does not answer {method}"
        if any(path.startswith(prefix) for prefix in self.denied):
            return 1, "", "(AuthorizationFailed) The client does not have authorization to perform the action"
        if path in self.estate:
            return 0, json.dumps(self.estate[path]), ""
        return 1, "", "(ResourceNotFound) The Resource was not found."


def selftest_inputs() -> tuple[list[dict], list[dict], dict, dict[str, str]]:
    ep = load_sibling("environment_params_of_the_selftest", "environment-params.py")
    root = Path(__file__).resolve().parents[1]
    models = json.loads((root / "environment" / "models.json").read_text(encoding="utf-8"))
    policies = json.loads((root / "environment" / "aigateway" / "policies.json").read_text(encoding="utf-8"))
    access = json.loads((root / "environment" / "aigateway" / "contracts.json").read_text(encoding="utf-8"))
    foundry = ep.foundry_names(SELFTEST_SUBSCRIPTION, SELFTEST_GROUP)
    names = {"account": foundry["foundry_account_name"], "project": foundry["foundry_project_name"], "guardrail": foundry["foundry_guardrail_name"], "gateway": ep.aigateway_name(SELFTEST_SUBSCRIPTION, SELFTEST_GROUP),
             "cases_app": ep.cases_names(SELFTEST_SUBSCRIPTION, SELFTEST_GROUP)["cases_function_app_name"], "storage": ep.base_names(SELFTEST_SUBSCRIPTION, SELFTEST_GROUP)["storage_account_name"],
             "approved_effect": ep.APPROVED_MODELS_EFFECT, "eligibility_effect": ep.MODEL_ELIGIBILITY_EFFECT}
    return models, policies, access, names


def selftest_context(az: FakeAz, models, policies, access, **options) -> Context:
    settings = {"now": SELFTEST_NOW, "commit": SELFTEST_COMMIT, "accepted_exemptions": {"Deny-Public-Endpoints/waiver"}, "accepted_deny": set(), "cases_public_access": "Enabled"}
    settings.update(options)
    return Context(Reader(az), SELFTEST_SUBSCRIPTION, SELFTEST_GROUP, models, policies, access, settings)


def healthy_rows(now: datetime = SELFTEST_NOW) -> list[dict]:
    return [{"control": "A-agents", "line": "drift.pass", "timestamp": (now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"control": "A-tools", "line": "drift.pass", "timestamp": (now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")}]


def states(ctx: Context) -> dict[str, str]:
    return {r["control"]: r["state"] for r in run_controls(ctx)[0]}


def selftest() -> int:
    models, policies, access, names = selftest_inputs()
    broken: list[str] = []

    def world(change: Callable[[dict], None] | None = None, graph_rows: list | None = None, **options) -> dict[str, str]:
        estate = fake_estate(models, policies, names)
        if change:
            change(estate)
        return states(selftest_context(FakeAz(estate, graph_rows=graph_rows, app_rows=healthy_rows()), models, policies, access, **options))

    base = f"/subscriptions/{SELFTEST_SUBSCRIPTION}/resourceGroups/{SELFTEST_GROUP}"
    account_path = f"{base}/providers/Microsoft.CognitiveServices/accounts/{names['account']}"
    gateway_path = f"{base}/providers/Microsoft.ApiManagement/aigateways/{names['gateway']}"
    project_path = f"{account_path}/projects/{names['project']}"
    project_roles = f"{project_path}/providers/Microsoft.Authorization/roleAssignments"
    operator_id = SELFTEST_IDS["operator"]
    project_id = SELFTEST_IDS["foundry-project"]
    management_group = "/providers/Microsoft.Management/managementGroups/example-root"

    healthy = world()
    expected_unknown = {"I-defender", "I-entra-console", "I-entra-agents"}
    for control_id, state in healthy.items():
        if (state == UNKNOWN) != (control_id in expected_unknown) or state == FAIL:
            broken.append(f"a healthy estate: {control_id} says {state}")
    cases = [
        ("I-foundry-flags", lambda e: e[account_path]["properties"].update(publicNetworkAccess="Enabled")),
        ("I-foundry-flags", lambda e: e[account_path]["properties"].update(disableLocalAuth=False)),
        ("I-deployments", lambda e: e[f"{account_path}/deployments"]["value"].append({"name": "unlisted", "sku": {"name": "GlobalStandard", "capacity": 1}, "properties": {}})),
        ("I-deployments", lambda e: e[f"{account_path}/deployments"]["value"][0]["properties"].update(raiPolicyName="Microsoft.DefaultV2")),
        ("I-guardrail", lambda e: e[f"{account_path}/raiPolicies/{names['guardrail']}"]["properties"]["contentFilters"].pop()),
        ("I-model-lifecycle", lambda e: e[f"{account_path}/models"]["value"][0]["model"].update(lifecycleStatus="Deprecated")),
        ("I-gateway-policies", lambda e: e[f"{gateway_path}/workspaces/default"]["properties"]["policies"].pop(0)),
        ("I-gateway-models", lambda e: e[f"{gateway_path}/workspaces/default/aliases"]["value"].append({"name": "sneaky", "properties": {"backendModels": []}})),
        ("I-gateway-roles", lambda e: e[f"{gateway_path}/providers/Microsoft.Authorization/roleAssignments"]["value"].append(
            {"properties": {"scope": gateway_path, "roleDefinitionId": f"/providers/Microsoft.Authorization/roleDefinitions/{GATEWAY_MODELS_USER}", "principalId": SELFTEST_IDS["stranger"], "principalType": "User"}})),
        ("I-telemetry", lambda e: e[f"{gateway_path}/workspaces/default/telemetryExporters"]["value"][0]["properties"].update(payloadCapture=True)),
        ("I-connection", lambda e: e[f"{account_path}/projects/{names['project']}/connections/aigateway"]["properties"].update(credentials={"key": "x"})),
        ("I-policy-assignments", lambda e: e[f"{base}/providers/Microsoft.Authorization/policyExemptions"]["value"].append(
            {"name": "new", "properties": {"policyAssignmentId": "/providers/Microsoft.Authorization/policyAssignments/Other"}})),
        ("I-role-assignments", lambda e: e[f"{base}/providers/Microsoft.Authorization/roleAssignments"]["value"].append(
            {"properties": {"scope": base, "roleDefinitionId": "/providers/Microsoft.Authorization/roleDefinitions/contributor", "principalId": SELFTEST_IDS["cases"]}})),
        ("I-network", lambda e: e[f"{base}/providers/Microsoft.Storage/storageAccounts/{names['storage']}"]["properties"].update(publicNetworkAccess="Enabled")),
        ("I-operator-role", lambda e: e[project_roles].update(value=[a for a in e[project_roles]["value"] if a["properties"]["principalId"] != operator_id])),
        ("I-operator-role", lambda e: e[project_roles]["value"].append(assignment_of(project_path, FOUNDRY_PROJECT_MANAGER, operator_id))),
        ("I-operator-role", lambda e: e[project_roles]["value"].append(assignment_of(account_path, FOUNDRY_USER, operator_id))),
        ("I-operator-role", lambda e: e[project_roles]["value"].append(assignment_of(base, SELFTEST_OPENAI_USER, operator_id))),
        ("I-operator-role", lambda e: e[project_roles]["value"].append(assignment_of(management_group, SELFTEST_OPENAI_USER, operator_id))),
        ("I-project-role", lambda e: e[project_roles].update(value=[a for a in e[project_roles]["value"] if a["properties"]["principalId"] != project_id])),
        ("I-project-role", lambda e: e[project_roles]["value"].append(assignment_of(account_path, FOUNDRY_USER, project_id))),
        ("I-project-role", lambda e: e[project_roles]["value"].append(assignment_of(f"/subscriptions/{SELFTEST_SUBSCRIPTION}", SELFTEST_OPENAI_USER, project_id))),
        ("I-release", lambda e: e[f"{base}/providers/Microsoft.Web/sites/{names['cases_app']}"]["tags"].update({"meternaut-build-commit": "c" * 40, "meternaut-package-sha256": "d" * 64})),
        ("I-alerts", lambda e: e[f"{base}/providers/Microsoft.Insights/scheduledQueryRules"]["value"].pop()),
        ("I-diagnostics", lambda e: e[f"{account_path}/providers/Microsoft.Insights/diagnosticSettings"]["value"].clear()),
        ("I-agent-365", lambda e: e[account_path]["properties"].update(a365LoggingEnabled=False)),
    ]
    for control_id, change in cases:
        if world(change).get(control_id) != FAIL:
            broken.append(f"{control_id} did not say FAIL when its thing was broken")
    for what, change in (("reports no Agent 365 setting", lambda e: [e[account_path]["properties"].pop(k) for k in ("a365LoggingEnabled", "a365Status")]),
                         ("reports the status Pending", lambda e: e[account_path]["properties"].update(a365Status="Pending"))):
        if world(change).get("I-agent-365") != UNKNOWN:
            broken.append(f"I-agent-365 did not say UNKNOWN when the Foundry resource {what}")
    new_deny = [{"Effect": "deny", "Assignment": "Some-Policy", "Reference": "ref", "Type": "microsoft.storage/storageaccounts", "Resources": 1}]
    if world(graph_rows=new_deny).get("I-policy-compliance") != FAIL:
        broken.append("I-policy-compliance did not say FAIL for a Deny policy that was not accepted")
    if world(graph_rows=new_deny, accepted_deny={"Some-Policy/ref/microsoft.storage/storageaccounts"}).get("I-policy-compliance") != PASS:
        broken.append("I-policy-compliance did not say PASS for a Deny policy that the owner accepted")
    if world(accepted_deny=None).get("I-policy-compliance") != UNKNOWN:
        broken.append("I-policy-compliance did not say UNKNOWN with no accepted baseline")
    for control_id, identity in (("I-operator-role", operator_id), ("I-project-role", project_id)):
        if world(lambda e, who=identity: e[project_roles]["value"].append(assignment_of(base, "00000000-0000-0000-0000-00000000dead", who))).get(control_id) != UNKNOWN:
            broken.append(f"{control_id} did not say UNKNOWN for a role above the project whose definition cannot be read")
    # a control that cannot read says UNKNOWN, and never PASS
    estate = fake_estate(models, policies, names)
    denied = FakeAz(estate, app_rows=healthy_rows())
    denied.denied.add(account_path.lower())
    if states(selftest_context(denied, models, policies, access)).get("I-foundry-flags") != UNKNOWN:
        broken.append("I-foundry-flags did not say UNKNOWN when it could not read")
    silent = Reader(FakeAz(fake_estate(models, policies, names), app_rows=[]))
    if states(Context(silent, SELFTEST_SUBSCRIPTION, SELFTEST_GROUP, models, policies, access, {"now": SELFTEST_NOW})).get("I-heartbeat") != UNKNOWN:
        broken.append("I-heartbeat did not say UNKNOWN when the app never logged a result")
    stale = FakeAz(fake_estate(models, policies, names), app_rows=[{"control": "A-agents", "line": "drift.pass", "timestamp": (SELFTEST_NOW - timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%SZ")}])
    if states(selftest_context(stale, models, policies, access)).get("I-heartbeat") != FAIL:
        broken.append("I-heartbeat did not say FAIL when the app's check was silent for 40 hours")
    # nothing here may write
    writer = Reader(FakeAz(fake_estate(models, policies, names)))
    for method, url in (("put", f"{ARM}/subscriptions/x"), ("delete", f"{ARM}/subscriptions/x"), ("patch", f"{ARM}/subscriptions/x"), ("post", f"{ARM}/subscriptions/x/providers/Microsoft.Authorization/roleAssignments")):
        try:
            writer.send(method, url)
            broken.append(f"{method} {url} was not refused")
        except Refused:
            pass
    for problem in broken:
        print(f"SELFTEST FAILED: {problem}", file=sys.stderr)
    if broken:
        return 1
    print(f"selftest: {len(CONTROLS)} controls say PASS on a healthy estate (UNKNOWN only where they read what this identity may not), {len(cases)} breakages each say FAIL, an unreadable thing says UNKNOWN, and no write is made.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
