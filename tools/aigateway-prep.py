#!/usr/bin/env python3
"""Applies the gateway-wide policies to the AI Gateway, deletes its built-in key when the service lets it be deleted, and reads the gateway back (standard library only).

    python tools/aigateway-prep.py policies --subscription S --resource-group G --gateway N --file aigateway-policies.json [--summary FILE] [--timeout SECONDS]
    python tools/aigateway-prep.py remove-key --subscription S --resource-group G --gateway N [--summary FILE] [--timeout SECONDS]
    python tools/aigateway-prep.py read-back --subscription S --resource-group G --gateway N --vnet V --subnet SN --foundry-account A --operator-identity ID \
        --models environment/models.json --policies aigateway-policies.json [--project-principal OBJECT-ID] [--summary FILE] [--timeout SECONDS]

It calls the Azure CLI (`az rest`), which the workflow has signed in, and only Azure Resource Manager: the gateway's own endpoint is public and is never called from here (the check
runs in the Operator, tools/aigateway-check.py). Only GitHub Actions may write (AGENTS.md rule 18): the two writing commands refuse to run anywhere else. Nothing that a response holds is
printed but names, states and numbers, and no key is read: a list of API keys is read for the names of the keys alone.

policies    The gateway-wide policies (a token limit, a request rate limit and cost limits for each caller) live in the `policies` array of the gateway's default workspace. The workspace
            exists on its own with the gateway and the service lets only a PATCH change it, and a PATCH replaces the whole array. So the array is read, the policies of the file are
            merged into it (a policy of the same type, and for a cost limit of the same id, is updated in place and keeps what else it holds, such as the spend that it has counted; the
            others are appended; a policy of another type, which a person may have added in the portal, is left as it is), and the merged array is written back only when it differs.
            The same way as the service's own script for it (Azure/aigateway, labs/21-enterprise-reference/infra/scripts/apply-baselines.sh). Then it reads the workspace again and fails
            unless every policy of the file is there with its numbers.
remove-key  The service makes a key named master on every gateway, an all-access key, and has no switch to refuse key authentication. Nothing of this project uses it (rule 23): the
            callers use Microsoft Entra ID and a role. So the key is read, deleted when it is there, and read again. When the service refuses the delete, that is said plainly as a
            FINDING and is not a failure: the key then exists and is unused, and the proposal records it. A refusal is an answer of the service that says no (a bad request, a conflict, a
            method that is not allowed, a failed precondition); a refusal of the deploy identity (401 and 403), a transient error and a timeout fail the run, because nothing is then
            known about the service's answer. A key with another name is never deleted here: it is not the built-in one and not this project's.
read-back   Reads the gateway and what hangs on it and fails for each thing that is not as the template and the file say: the state of the gateway, the backend subnet and its delegation,
            the system-assigned identity, the provider, every model (deployment, version, content safety at Medium for the four categories), every alias, the gateway-wide policies, the
            roles (the Operator's identity holds AI Gateway Models User on the gateway, the gateway's identity holds Foundry User on the Foundry resource) and the names of the API keys. It
            prints publicNetworkAccess as the service reports it and does not judge it: the service has no private frontend, and the template says so.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

API = "2025-09-01-preview"
NETWORK_API = "2025-05-01"
ACCOUNT_API = "2025-06-01"
AUTHORIZATION_API = "2022-04-01"
IDENTITY_API = "2023-01-31"
ARM = "https://management.azure.com"
PROVIDER = "foundry"
BUILT_IN_KEY = "master"
SUBNET_DELEGATION = "Microsoft.App/environments"
SEVERITY = "Medium"
CATEGORIES = ("hateSeverity", "violenceSeverity", "sexualSeverity", "selfHarmSeverity")
FOUNDRY_USER = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
MODELS_USER = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"
AI_GATEWAY_ROLES = {
    "caad7a21-134e-43f4-a550-c5ffc17e051c": "AI Gateway User",
    MODELS_USER: "AI Gateway Models User",
    "dce03f8d-857f-4e40-a90d-67770fa6ecd2": "AI Gateway Tools User",
}
# The policies that this project manages, and what an update of one of them has to leave alone: it is matched by its type, and a cost limit by its id too.
MANAGED_TYPES = ("tokenLimit", "requestRateLimit", "costLimit")
STATES = ("Succeeded", "Failed", "Canceled", "Creating", "Updating", "Deleting", "Accepted", "Running", "Provisioning")
ACCESS = ("Enabled", "Disabled")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SUBSCRIPTION = GUID
GROUP = re.compile(r"^[A-Za-z0-9._()-]{1,90}$")
GATEWAY = re.compile(r"^[a-z0-9][a-z0-9-]{1,22}[a-z0-9]$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
HOST_SUFFIX = ".ai.gateway.azure.com"
NOT_FOUND = re.compile(r"NotFound|ResourceNotFound|Not Found|\b404\b", re.I)
# The deploy identity is not allowed (401, 403), or has no valid sign-in: nothing is known about what the service would say.
DENIED = re.compile(r"Forbidden|Unauthorized|AuthorizationFailed|AuthenticationFailed|ExpiredAuthenticationToken|InvalidAuthenticationToken|\b40[13]\b", re.I)
# The service says no to a request that it understood: a bad request, a conflict, a method that is not allowed, a failed precondition.
REFUSED = re.compile(r"BadRequest|Bad Request|Conflict|MethodNotAllowed|Method Not Allowed|PreconditionFailed|Precondition Failed|\b(?:400|405|409|412)\b"
                     r"|cannot be deleted|can't be deleted|not allowed|not supported|built-in|builtin", re.I)
# How long one read of Azure may take, how many pages one list may have, and how often the result of a write is read again.
TIMEOUT_SECONDS = 120
MAX_PAGES = 20
READ_BACK_ATTEMPTS = 6
READ_BACK_SECONDS = 10

Runner = Callable[[list[str]], tuple[int, str, str]]
Line = tuple[str, str]


class Gone(Exception):
    """Azure says that the resource is not there."""


class Unreadable(Exception):
    """Azure gave no usable answer. The text is the first line of its error, which holds no token."""


class Stuck(Exception):
    """`az` did not answer in time. The rest is not read: a second read would wait just as long."""


class Denied(Exception):
    """Azure refuses the deploy identity (401 or 403), or the identity has no valid sign-in."""


class Refused(Exception):
    """The service understood the request and says no."""


class Problem(Exception):
    """Something the owner can fix or must know; printed without a trace."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def ok(text: str) -> Line:
    return ("ok", text)


def failed(text: str) -> Line:
    return ("FAILED", text)


def note(text: str) -> Line:
    return ("note", text)


def finding(text: str) -> Line:
    return ("FINDING", text)


class Target:
    """The gateway that the commands work on, and the paths of what hangs on it."""

    def __init__(self, subscription: str, group: str, name: str):
        self.subscription = subscription
        self.group = group
        self.name = name

    @property
    def group_path(self) -> str:
        return f"/subscriptions/{self.subscription}/resourceGroups/{self.group}"

    @property
    def id(self) -> str:
        return f"{self.group_path}/providers/Microsoft.ApiManagement/aigateways/{self.name}"

    @property
    def workspace(self) -> str:
        return f"{self.id}/workspaces/default"

    @property
    def keys(self) -> str:
        return f"{self.id}/apiKeys"


def describe(arguments: list[str]) -> str:
    """Which request it was, for a message: the method and the address without its query, or a plain word when the arguments name none."""
    if "--url" in arguments and arguments.index("--url") + 1 < len(arguments):
        method = arguments[arguments.index("--method") + 1].upper() if "--method" in arguments and arguments.index("--method") + 1 < len(arguments) else "GET"
        return method + " " + arguments[arguments.index("--url") + 1].split("?")[0].replace(ARM, "")
    return "a request"


def run_az(arguments: list[str], timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, str]:
    try:
        done = subprocess.run([os.environ.get("AZ", "az"), *arguments], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Stuck(f"az did not answer within {timeout} seconds ({describe(arguments)})")
    return done.returncode, done.stdout, done.stderr


def first_line(text: str) -> str:
    return ((text or "").strip().splitlines() or ["no answer"])[0][:300]


def send(az: Runner, method: str, path: str, api: str, body: dict | None = None, query: str = "") -> dict:
    """One request of Azure Resource Manager. A failure is one of five things, by what Azure says: not there, not allowed, refused by the service, unreadable, or too slow (Stuck)."""
    arguments = ["rest", "--method", method, "--url", f"{ARM}{path}?api-version={api}" + (f"&{query}" if query else ""), "--only-show-errors", "--output", "json"]
    if body is not None:
        arguments += ["--body", json.dumps(body)]
    code, out, err = az(arguments)
    if code != 0:
        message = first_line(err)
        if NOT_FOUND.search(err or ""):
            raise Gone()
        if DENIED.search(err or ""):
            raise Denied(message)
        if REFUSED.search(err or ""):
            raise Refused(message)
        raise Unreadable(message)
    if not (out or "").strip():
        return {}
    try:
        document = json.loads(out)
    except ValueError:
        raise Unreadable("the answer is not JSON")
    if not isinstance(document, dict):
        raise Unreadable("the answer is not an object")
    return document


def get(az: Runner, path: str, api: str = API, query: str = "") -> dict:
    return send(az, "get", path, api, query=query)


def get_all(az: Runner, path: str, api: str = API, query: str = "") -> list:
    """Every item of a list that Azure gives in pages: nextLink is followed until there is none, to addresses of Azure Resource Manager only, and for a limited number of pages."""
    items: list = []
    document = get(az, path, api, query)
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
        code, out, err = az(["rest", "--method", "get", "--url", link, "--only-show-errors", "--output", "json"])
        if code != 0:
            raise Unreadable("a later page of the list could not be read: " + first_line(err))
        try:
            document = json.loads(out)
        except ValueError:
            raise Unreadable("a later page of the list is not JSON")
        if not isinstance(document, dict):
            raise Unreadable("a later page of the list is not an object")
        pages += 1


def safe(value, limit: int = 64) -> str:
    """A name from an answer of Azure, for a line of output: only the characters of a name, and not more than the limit of them."""
    return re.sub(r"[^A-Za-z0-9._-]", "?", str(value))[:limit]


def word(value, allowed: tuple[str, ...]) -> str:
    """A state that the service reports, for a line of output: one of the words that it is known to use, and for anything else a plain statement that it was not one of them."""
    if value is None:
        return "None"
    return value if isinstance(value, str) and value in allowed else "an unexpected value"


def tail(resource_id) -> str:
    return safe(str(resource_id or "").rstrip("/").rsplit("/", 1)[-1]) or "nothing"


def number(value) -> str:
    return f"{value:g}" if isinstance(value, (int, float)) and not isinstance(value, bool) else "?"


def normal(value):
    """A value as it is compared: a number is a number (5 and 5.0 are the same, and a switch is not a number), and a text, a list and an object are compared as they are."""
    if isinstance(value, bool):
        return ("switch", value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return [normal(item) for item in value]
    if isinstance(value, dict):
        return {key: normal(item) for key, item in value.items()}
    return value


def find(policies: list, wanted: dict) -> int | None:
    """Where the policy that `wanted` stands for is in the list: the first one of its type, and for a cost limit the one with its id."""
    for index, policy in enumerate(policies):
        if isinstance(policy, dict) and policy.get("type") == wanted.get("type") and (wanted.get("type") != "costLimit" or policy.get("id") == wanted.get("id")):
            return index
    return None


def holds(policy: dict, wanted: dict) -> bool:
    """Whether the policy has every setting of the wanted one with the same value: what else it holds does not matter."""
    return all(key in policy and normal(policy[key]) == normal(value) for key, value in wanted.items())


def label(policy: dict) -> str:
    return f"{safe(policy.get('type'))} {safe(policy['id'])}" if policy.get("type") == "costLimit" and policy.get("id") else safe(policy.get("type"))


def describe_policy(policy: dict) -> str:
    """What a policy limits, in names and numbers, for a line of output."""
    kind = policy.get("type")
    if kind == "tokenLimit":
        return f"tokenLimit: {number(policy.get('count'))} tokens a {safe(policy.get('period'))} for each caller ({safe(policy.get('scope'))})"
    if kind == "requestRateLimit":
        return f"requestRateLimit: {number(policy.get('callsPerPeriod'))} calls in {number(policy.get('periodSeconds'))} seconds for each caller ({safe(policy.get('scope'))})"
    if kind == "costLimit":
        return f"costLimit {safe(policy.get('id'))}: {number(policy.get('amount'))} US dollars a {safe(policy.get('period'))} for each caller ({safe(policy.get('scope'))})"
    return f"{safe(kind)}: a policy of this type is there (not managed here)"


def shown(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return number(value)
    if isinstance(value, str):
        return safe(value, 40)
    return "?" if value is None else safe(type(value).__name__)


def merge(current: list, wanted: list[dict]) -> tuple[list, list[str]]:
    """The policies after the merge, and a sentence for each change: a policy of the file is added, or updated in place when one is there already (it keeps what else it holds)."""
    merged = [dict(policy) if isinstance(policy, dict) else policy for policy in current]
    changes = []
    for policy in wanted:
        index = find(merged, policy)
        if index is None:
            merged.append(dict(policy))
            changes.append(f"adds {label(policy)}")
            continue
        updated = {**merged[index], **policy}
        if normal(updated) != normal(merged[index]):
            differing = [f"{key} {shown(merged[index].get(key))} to {shown(value)}" for key, value in policy.items() if normal(merged[index].get(key)) != normal(value)]
            merged[index] = updated
            changes.append(f"updates {label(policy)} ({', '.join(differing)})")
    return merged, changes


def only_in_actions() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise Problem("this command writes to Azure, and only a GitHub Actions run may do that (AGENTS.md rule 18)", 2)


def guarded(action: Callable[[], list[Line]]) -> list[Line]:
    """The lines of an action, with every failure of Azure turned into a line that says what happened and that nothing was repaired from here."""
    try:
        return action()
    except Gone:
        return [failed("something that was read is not there")]
    except Denied as e:
        return [failed(f"Azure does not allow the deploy identity this request: {e}")]
    except Refused as e:
        return [failed(f"the service refused the request: {e}")]
    except Unreadable as e:
        return [failed(f"Azure gave no usable answer: {e}")]
    except Stuck as e:
        return [failed(f"{e}. Nothing after it was read or written")]


def gateway_state(az: Runner, target: Target) -> tuple[str | None, dict]:
    document = get(az, target.id)
    return (document.get("properties") or {}).get("provisioningState"), document


def run_policies(az: Runner, target: Target, wanted: list[dict], sleep: Callable[[float], None] = time.sleep) -> list[Line]:
    def action() -> list[Line]:
        lines: list[Line] = []
        try:
            state, _ = gateway_state(az, target)
        except Gone:
            return [failed(f"The gateway {target.name} is not there: nothing was changed. The deploy step of the action makes it")]
        if state != "Succeeded":
            return [failed(f"The gateway is in the state {word(state, STATES)} and not Succeeded: nothing was changed. Run the action again when the service has finished")]
        try:
            workspace = get(az, target.workspace)
        except Gone:
            return [failed("The gateway's default workspace is not there: it exists on its own with the gateway, so the gateway is not as it should be. Nothing was changed")]
        current = (workspace.get("properties") or {}).get("policies")
        current = [] if current is None else current
        if not isinstance(current, list):
            return [failed("The workspace reports its policies in a shape that is not a list: nothing was changed")]
        merged, changes = merge(current, wanted)
        if not changes:
            lines.append(ok("The gateway-wide policies are as environment/aigateway/policies.json says: nothing to change"))
        else:
            for change in changes:
                lines.append(note(f"The merge {change}"))
            try:
                send(az, "patch", target.workspace, API, {"properties": {"policies": merged}})
            except Refused as e:
                return [*lines, failed(f"The service refused the policies: {e}. Nothing else was changed. If it refuses a second cost limit, the file environment/aigateway/policies.json holds "
                                       "one for the day and one for the month: keep the one that the owner's standing limit needs first (AGENTS.md rule 15 (g)) and run the action again")]
            lines.append(ok("The merged policies were written to the workspace (one PATCH)"))
        for attempt in range(1, READ_BACK_ATTEMPTS + 1):
            after = (get(az, target.workspace).get("properties") or {}).get("policies") or []
            wrong = [label(policy) for policy in wanted if (found := find(after, policy)) is None or not holds(after[found], policy)]
            if not wrong:
                for policy in wanted:
                    lines.append(ok(f"Read back: {describe_policy(after[find(after, policy)])}"))
                return lines
            lines.append(note(f"Read back (check {attempt} of {READ_BACK_ATTEMPTS}): not there yet or different: {', '.join(wrong)}"))
            if attempt < READ_BACK_ATTEMPTS:
                sleep(READ_BACK_SECONDS)
        lines.append(failed(f"After the write the workspace does not hold: {', '.join(wrong)}"))
        return lines

    return guarded(action)


def key_names(az: Runner, target: Target) -> list[str]:
    """The names of the API keys of the gateway, and nothing else of them."""
    return sorted(safe(item.get("name")) for item in get_all(az, target.keys) if isinstance(item, dict) and item.get("name"))


def run_remove_key(az: Runner, target: Target, sleep: Callable[[float], None] = time.sleep) -> list[Line]:
    def action() -> list[Line]:
        lines: list[Line] = []
        try:
            names = key_names(az, target)
        except Gone:
            return [failed(f"The gateway {target.name} is not there, so its keys cannot be read")]
        others = [name for name in names if name != BUILT_IN_KEY]
        lines.append(note(f"The API keys of the gateway, by name: {', '.join(names) if names else 'none'}"))
        if others:
            lines.append(note(f"The key(s) {', '.join(others)} are not the built-in key and are not deleted here: they are not this project's. The read-back fails while one exists (AGENTS.md rule 23)"))
        if BUILT_IN_KEY not in names:
            lines.append(ok(f"The built-in key {BUILT_IN_KEY} is not there: nothing to delete"))
            return lines
        try:
            send(az, "delete", f"{target.keys}/{BUILT_IN_KEY}", API)
        except Gone:
            lines.append(note(f"The service says that the key {BUILT_IN_KEY} is not there any more"))
        except Refused as e:
            lines.append(finding(f"The service refuses to delete the built-in key {BUILT_IN_KEY}: {e}. The key path exists and is unused: nothing of this project sends the key, and its callers use Microsoft "
                                 "Entra ID and a role. This is recorded in docs/proposals/08-ai-gateway.md and is not a failure"))
            return lines
        for attempt in range(1, READ_BACK_ATTEMPTS + 1):
            if BUILT_IN_KEY not in key_names(az, target):
                lines.append(ok(f"Read back: the built-in key {BUILT_IN_KEY} is deleted"))
                return lines
            lines.append(note(f"Read back (check {attempt} of {READ_BACK_ATTEMPTS}): the key {BUILT_IN_KEY} is still listed"))
            if attempt < READ_BACK_ATTEMPTS:
                sleep(READ_BACK_SECONDS)
        lines.append(finding(f"The service accepted the delete of the built-in key {BUILT_IN_KEY} and still lists it. The key path exists and is unused: nothing of this project sends the key, and its "
                             "callers use Microsoft Entra ID and a role. This is recorded in docs/proposals/08-ai-gateway.md and is not a failure"))
        return lines

    return guarded(action)


def read_models(path: Path) -> list[dict]:
    try:
        models = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Problem(f"{path} is not a readable JSON list of models", 2)
    if not isinstance(models, list) or not models or any(not isinstance(m, dict) or not {"name", "version"} <= set(m) or not isinstance(m["name"], str) or not isinstance(m["version"], str) for m in models):
        raise Problem(f"{path} is not a list of models with a name and a version", 2)
    return models


def read_policies(path: Path) -> list[dict]:
    try:
        policies = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Problem(f"{path} is not a readable JSON list of policies", 2)
    if not isinstance(policies, list) or not policies or any(not isinstance(p, dict) or p.get("type") not in MANAGED_TYPES for p in policies):
        raise Problem(f"{path} is not a list of policies of the types {', '.join(MANAGED_TYPES)}", 2)
    return policies


def role_of(assignment: dict) -> str:
    return str((assignment.get("properties") or {}).get("roleDefinitionId") or "").rsplit("/", 1)[-1].lower()


def read_back(az: Runner, target: Target, vnet: str, subnet: str, foundry_account: str, operator_identity: str, models: list[dict], wanted: list[dict],
              project_principal: str = "") -> list[Line]:
    """One line for each thing that was read. A thing that cannot be read is a failure too."""
    found: list[Line] = []
    halted: list[str] = []
    subnet_id = f"{target.group_path}/providers/Microsoft.Network/virtualNetworks/{vnet}/subnets/{subnet}"
    account_id = f"{target.group_path}/providers/Microsoft.CognitiveServices/accounts/{foundry_account}"
    providers = f"{target.workspace}/modelProviders"
    resources = {model["name"]: model["name"].replace(".", "-") for model in models}

    def say(line: Line) -> None:
        found.append(line)

    def fetch(what: str, path: str, api: str = API, pages: bool = False, query: str = ""):
        """The document at the path, or all items of the list there (pages=True). Once az has not answered in time nothing more is read."""
        if halted:
            return None
        try:
            return get_all(az, path, api, query) if pages else get(az, path, api, query)
        except Gone:
            say(failed(f"{what} is not there"))
        except Denied as e:
            say(failed(f"{what} could not be read, Azure does not allow it: {e}"))
        except (Unreadable, Refused) as e:
            say(failed(f"{what} could not be read: {e}"))
        except Stuck as e:
            halted.append(str(e))
            say(failed(f"{what} could not be read: {e}. The read-back stops here: nothing after it was read"))
        return None

    gateway_principal = ""
    document = fetch(f"The gateway {target.name}", target.id)
    if document is not None:
        properties = document.get("properties") or {}
        state = properties.get("provisioningState")
        say(ok(f"The gateway is in the state {word(state, STATES)}") if state == "Succeeded" else failed(f"The gateway is in the state {word(state, STATES)} and not Succeeded"))
        say(note(f"The service reports publicNetworkAccess {word(properties.get('publicNetworkAccess'), ACCESS)}. The frontend is public whatever that says: the service has no private endpoint and no "
                 "private frontend, and a request needs a Microsoft Entra token and a role on the gateway (docs/proposals/08-ai-gateway.md)"))
        reported = ((properties.get("backend") or {}).get("subnet") or {}).get("id")
        same = isinstance(reported, str) and reported.lower() == subnet_id.lower()
        say(ok(f"The backend subnet of the gateway is {subnet}") if same else failed(f"The backend subnet of the gateway is not {subnet} (the service reports {tail(reported)})"))
        identity = document.get("identity") or {}
        gateway_principal = str(identity.get("principalId") or "").lower()
        has_identity = "SystemAssigned" in str(identity.get("type") or "") and bool(GUID.match(gateway_principal))
        say(ok("The gateway has a system-assigned identity") if has_identity else failed("The gateway has no system-assigned identity"))
        host = (properties.get("frontend") or {}).get("defaultHostname")
        say(ok("The service reports the gateway's host name") if isinstance(host, str) and host.endswith(HOST_SUFFIX) else failed(f"The service does not report a host name under {HOST_SUFFIX}"))
        sku = (document.get("sku") or {}).get("name")
        if sku:
            say(note(f"The service reports the sku {safe(sku)}, which it owns (the template sends none)"))

    document = fetch(f"The subnet {subnet}", subnet_id, NETWORK_API)
    if document is not None:
        properties = document.get("properties") or {}
        delegations = [str((d.get("properties") or {}).get("serviceName")) for d in properties.get("delegations") or [] if isinstance(d, dict)]
        say(ok(f"The subnet {subnet} is delegated to {SUBNET_DELEGATION} and to nothing else") if delegations == [SUBNET_DELEGATION]
            else failed(f"The subnet {subnet} is not delegated to {SUBNET_DELEGATION} alone (delegations: {', '.join(safe(d) for d in delegations) or 'none'})"))
        say(note(f"The subnet carries a route table: {'yes' if (properties.get('routeTable') or {}).get('id') else 'no'}"))

    items = fetch("The model providers", providers, pages=True)
    if items is not None:
        by_name = {i.get("name"): i for i in items if isinstance(i, dict)}
        say(note(f"The model providers of the gateway, by name: {', '.join(safe(n) for n in sorted(by_name, key=str)) or 'none'}"))
        provider = by_name.get(PROVIDER)
        if provider is None:
            say(failed(f"The provider {PROVIDER} is not there"))
        else:
            properties = provider.get("properties") or {}
            behind = properties.get("foundry") or {}
            authentication = (behind.get("authentication") or {}).get("kind")
            resource_ids = [str(r).lower() for r in behind.get("resourceIds") or []]
            good = properties.get("kind") == "Foundry" and authentication == "ManagedIdentity" and account_id.lower() in resource_ids
            say(ok(f"The provider {PROVIDER}: kind Foundry, the Foundry resource {foundry_account}, called with the gateway's managed identity and no key") if good
                else failed(f"The provider {PROVIDER} differs from its template (kind {safe(properties.get('kind'))}, authentication {safe(authentication)}, Foundry resources {len(resource_ids)}, "
                            f"{'the Foundry resource of the agents is' if account_id.lower() in resource_ids else 'not'} among them)"))

    items = fetch(f"The models of the provider {PROVIDER}", f"{providers}/{PROVIDER}/models", pages=True)
    if items is not None:
        by_name = {i.get("name"): i for i in items if isinstance(i, dict)}
        for model in models:
            resource = resources[model["name"]]
            item = by_name.get(resource)
            if item is None:
                say(failed(f"The model {resource} is not there"))
                continue
            properties = item.get("properties") or {}
            deployment = properties.get("deployment") or {}
            safety = [p for p in properties.get("policies") or [] if isinstance(p, dict) and p.get("type") == "contentSafety"]
            problems = []
            if deployment.get("modelName") != model["name"] or deployment.get("modelVersion") != model["version"]:
                problems.append("the model and its version")
            if not str(deployment.get("resourceId") or "").lower().endswith(f"/accounts/{foundry_account}/deployments/{model['name']}".lower()):
                problems.append("the deployment that it points to")
            # The service does not echo `apiFormat` back (read from the live gateway on 2026-11-07: a model holds its deployment, version, policies, provider kind and its supported
            # endpoints, and no format). So the format is judged by what the service does report: a format that is reported must be the template's, and the endpoints must list the chat completions route.
            reported_format = properties.get("apiFormat")
            if reported_format is not None and reported_format != "OpenAIChatCompletions":
                problems.append("the API format")
            if "/openai/v1/chat/completions" not in (properties.get("supportedEndpoints") or []):
                problems.append("the chat completions endpoint")
            if len(safety) != 1 or any(safety[0].get(category) != SEVERITY for category in CATEGORIES):
                problems.append(f"content safety at {SEVERITY} for the four categories")
            say(ok(f"The model {resource}: deployment {safe(model['name'])} version {safe(model['version'])}, content safety {SEVERITY} for the four categories") if not problems
                else failed(f"The model {resource} differs from its template: {', '.join(problems)}"))
        for extra in sorted(set(map(str, by_name)) - set(resources.values())):
            say(note(f"The provider also holds the model {safe(extra)}"))

    items = fetch("The aliases", f"{target.workspace}/aliases", pages=True)
    if items is not None:
        by_name = {i.get("name"): i for i in items if isinstance(i, dict)}
        for model in models:
            item = by_name.get(model["name"])
            if item is None:
                say(failed(f"The alias {safe(model['name'])} is not there"))
                continue
            properties = item.get("properties") or {}
            targets = [t for t in properties.get("backendModels") or [] if isinstance(t, dict)]
            right = (properties.get("aliasName") == model["name"] and len(targets) == 1
                     and str(targets[0].get("resourceId") or "").lower().endswith(f"/models/{resources[model['name']]}".lower()))
            say(ok(f"The alias {safe(model['name'])} points to the model {resources[model['name']]}, and to nothing else") if right
                else failed(f"The alias {safe(model['name'])} differs from its template (it has {len(targets)} target(s))"))
        for extra in sorted(set(map(str, by_name)) - {m["name"] for m in models}):
            say(note(f"The gateway also holds the alias {safe(extra)}"))

    document = fetch("The default workspace", target.workspace)
    if document is not None:
        current = (document.get("properties") or {}).get("policies") or []
        current = current if isinstance(current, list) else []
        for policy in wanted:
            index = find(current, policy)
            if index is None:
                say(failed(f"The policy {label(policy)} is not there"))
            elif holds(current[index], policy):
                say(ok(f"The policy {describe_policy(current[index])}"))
            else:
                say(failed(f"The policy {label(policy)} differs from environment/aigateway/policies.json: it holds {describe_policy(current[index])}"))
        for other in current:
            if isinstance(other, dict) and find(wanted, other) is None:
                say(note(f"The workspace also holds a policy: {describe_policy(other)}"))

    operator_principal = ""
    document = fetch(f"The Operator's identity {operator_identity}", f"{target.group_path}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{operator_identity}", IDENTITY_API)
    if document is not None:
        operator_principal = str((document.get("properties") or {}).get("principalId") or "").lower()
    items = fetch("The role assignments at the gateway", f"{target.id}/providers/Microsoft.Authorization/roleAssignments", AUTHORIZATION_API, pages=True, query="%24filter=atScope()")
    if items is not None:
        assignments = [(role_of(a), str((a.get("properties") or {}).get("principalId") or "").lower(), str((a.get("properties") or {}).get("scope") or "").lower())
                       for a in items if isinstance(a, dict)]
        here = target.id.lower()
        if operator_principal:
            has = (MODELS_USER, operator_principal, here) in assignments
            say(ok("The Operator's identity holds AI Gateway Models User on the gateway") if has else failed("The Operator's identity does not hold AI Gateway Models User on the gateway"))
        if project_principal:
            has = (MODELS_USER, project_principal.lower(), here) in assignments
            say(ok("The Foundry project's identity holds AI Gateway Models User on the gateway") if has else failed("The Foundry project's identity does not hold AI Gateway Models User on the gateway"))
        else:
            say(note("No principal of the Foundry project was given: the step that connects the project to the gateway gives it AI Gateway Models User"))
        expected = {operator_principal, project_principal.lower()} - {""}
        for role, principal, scope in assignments:
            if role in AI_GATEWAY_ROLES and principal not in expected:
                say(note(f"{AI_GATEWAY_ROLES[role]} is also held on the gateway by the principal {safe(principal)} (scope {tail(scope)})"))

    items = fetch("The role assignments at the Foundry resource", f"{account_id}/providers/Microsoft.Authorization/roleAssignments", AUTHORIZATION_API, pages=True, query="%24filter=atScope()")
    if items is not None and gateway_principal:
        held = any(role_of(a) == FOUNDRY_USER and str((a.get("properties") or {}).get("principalId") or "").lower() == gateway_principal for a in items if isinstance(a, dict))
        say(ok(f"The gateway's identity holds Foundry User on the Foundry resource {foundry_account}") if held
            else failed(f"The gateway's identity does not hold Foundry User on the Foundry resource {foundry_account}, so it cannot call the model deployments"))

    names = fetch("The API keys of the gateway", target.keys, pages=True)
    if names is not None:
        listed = sorted(safe(i.get("name")) for i in names if isinstance(i, dict) and i.get("name"))
        others = [n for n in listed if n != BUILT_IN_KEY]
        if others:
            say(failed(f"API keys exist that the template does not make: {', '.join(others)}. No key is used by this project (AGENTS.md rule 23)"))
        elif listed:
            say(note(f"The API keys of the gateway, by name: {', '.join(listed)}. The service makes the built-in key {BUILT_IN_KEY}; it is unused, and it is a recorded finding when the service does not let it be deleted"))
        else:
            say(ok("The gateway has no API key"))
    return found


def report(title: str, lines: list[Line], summary: str | None, extra: str = "") -> int:
    text = "\n".join(f"{level}: {message}" for level, message in lines)
    print(text)
    broken = [message for level, message in lines if level == "FAILED"]
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"### {title}\n\n{extra}```\n{text}\n```\n")
    if broken:
        print(f"{len(broken)} thing(s) are not as they should be. The run fails; nothing is repaired from here.", file=sys.stderr)
        return 1
    return 0


def parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, names in (("policies", ("file",)), ("remove-key", ()),
                        ("read-back", ("vnet", "subnet", "foundry-account", "operator-identity", "models", "policies"))):
        sub = commands.add_parser(name)
        for flag in ("subscription", "resource-group", "gateway", *names):
            sub.add_argument(f"--{flag}", required=True)
        sub.add_argument("--summary", help="a file to append the lines to as Markdown (the step summary of a workflow run)")
        sub.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS, help=f"seconds that one request of Azure may take (default {TIMEOUT_SECONDS})")
        if name == "read-back":
            sub.add_argument("--project-principal", default="", help="the object id of the Foundry project's system-assigned identity, when it is known")
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error("--timeout is a number of seconds, one or more")
    return args


def target_of(args: argparse.Namespace) -> Target:
    if not SUBSCRIPTION.match(args.subscription) or not GROUP.match(args.resource_group) or not GATEWAY.match(args.gateway):
        raise Problem("--subscription is a subscription id, --resource-group a resource group name and --gateway the name of an AI Gateway", 2)
    return Target(args.subscription.lower(), args.resource_group, args.gateway)


def main(argv=None, az: Runner | None = None, sleep: Callable[[float], None] = time.sleep) -> int:
    args = parse(argv)
    runner = az or (lambda arguments: run_az(arguments, args.timeout))
    try:
        target = target_of(args)
        if args.command == "policies":
            only_in_actions()
            lines = run_policies(runner, target, read_policies(Path(args.file)), sleep)
            return report("The gateway-wide policies of the AI Gateway", lines, args.summary)
        if args.command == "remove-key":
            only_in_actions()
            lines = run_remove_key(runner, target, sleep)
            return report("The built-in key of the AI Gateway", lines, args.summary)
        for flag in ("vnet", "subnet", "foundry_account", "operator_identity"):
            if not NAME.match(getattr(args, flag)):
                raise Problem(f"--{flag.replace('_', '-')} is a resource name", 2)
        if args.project_principal and not GUID.match(args.project_principal):
            raise Problem("--project-principal is an object id, or empty", 2)
        lines = read_back(runner, target, args.vnet, args.subnet, args.foundry_account, args.operator_identity, read_models(Path(args.models)), read_policies(Path(args.policies)),
                          args.project_principal)
        return report("The AI Gateway, read back from Azure", lines, args.summary)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
