#!/usr/bin/env python3
"""Builds the parameter files of the first environment from the deployment workflow's settings (standard library only).

    python tools/environment-params.py build --models environment/models.json --out-dir "$RUNNER_TEMP" [--preview] >> "$GITHUB_OUTPUT"
    python tools/environment-params.py check --params "$RUNNER_TEMP/kit.parameters.json" --template kit.json --label kit

The settings are environment variables, filled by the workflow from the repository's secrets and variables, so that no
address, name or mail address is in the repository:

    ENV_SUBSCRIPTION_ID, ENV_RESOURCE_GROUP, ENV_LOCATION, ENV_VNET_PREFIX, ENV_PE_SUBNET_PREFIX,
    ENV_DNS_SERVERS (comma separated), ENV_OWNER, ENV_BUDGET_AMOUNT, ENV_ALERT_EMAILS (comma separated),
    ENV_BUDGET_START, GATEWAY_RESOURCE_ID, GATEWAY_APPINSIGHTS_ID, GATEWAY_PRINCIPAL_ID

ENV_BUDGET_START is the first day of the month in which the budget was first made, which the workflow reads from the
existing budget (a budget keeps its start date) or, for a new budget, takes from the current month.
GATEWAY_RESOURCE_ID is the resource id of the owner's existing API Management instance; GATEWAY_APPINSIGHTS_ID is the
resource id of the Application Insights component that the instance already logs to; GATEWAY_PRINCIPAL_ID is the object
id of the gateway's user-assigned identity, which does not exist before the first deploy (a `--preview`, for a
what-if, then uses a placeholder, and says so).

It writes three ARM parameter files into --out-dir:

    environment.parameters.json   for environment/main.bicep (the model side)
    logger.parameters.json        for environment/gateway/logger.bicep
    kit.parameters.json           for the Citadel gateway-upgrade module (the kit's bicep/infra/apim-gateway-upgrade/main.bicep)

Every value is checked before anything is deployed. The name of the model account is worked out here, from the
subscription and the resource group, so it is the same on every run (a run after a removal finds, and the workflow
restores, the soft-deleted account of that name instead of leaving a second one behind). It prints key=value lines for
GitHub to read as step outputs.

The settings of the kit's module are chosen here and explained here, not in the workflow, so that a test can hold them:
  - The personal-data flag stays on, because the module creates the `ai-foundry-compatibility` policy fragment only then,
    and the inference APIs' policies include that fragment unconditionally. The Language and Content Safety addresses are
    the model account's own (a named value may not be empty).
  - No prompt and no answer is logged: the LLM log settings say `none` for both, so only token counts and the model's name
    are kept.
  - JWT checking is off (callers use the contract's key) until an app registration exists; the Unified AI, Realtime,
    Redis, embeddings and release-version parts are off; no second logger and no diagnostic setting is made for Azure Monitor.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
from pathlib import Path

SCHEMA = "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#"
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
GROUP = re.compile(r"^[A-Za-z0-9._-]{1,89}[A-Za-z0-9_-]$")
LOCATION = re.compile(r"^[a-z0-9]{3,30}$")
OWNER = re.compile(r"^[A-Za-z0-9@._+ -]{1,64}$")
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
BUDGET_START = re.compile(r"^(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-01$")
DATE = re.compile(r"^(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")
MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{0,62}$")
NAME = r"[A-Za-z0-9._()-]{1,90}"
GATEWAY_ID = re.compile(rf"^/subscriptions/([0-9a-fA-F-]{{36}})/resourceGroups/({NAME})/providers/Microsoft\.ApiManagement/service/([A-Za-z0-9-]{{1,50}})$", re.I)
APPINSIGHTS_ID = re.compile(rf"^/subscriptions/([0-9a-fA-F-]{{36}})/resourceGroups/({NAME})/providers/microsoft\.insights/components/([A-Za-z0-9._()-]{{1,260}})$", re.I)
PRIVATE_SPACE = ipaddress.ip_network("10.0.0.0/8")
SKUS = ("DataZoneStandard", "GlobalStandard")
PLACEHOLDER = "00000000-0000-0000-0000-000000000000"
IDENTITY_NAME = "id-meternaut-gateway"

AZURE_MONITOR_LOG_SETTINGS = {
    "frontend": {"request": {"headers": [], "body": {"bytes": 0}}, "response": {"headers": [], "body": {"bytes": 0}}},
    "backend": {"request": {"headers": [], "body": {"bytes": 0}}, "response": {"headers": [], "body": {"bytes": 0}}},
    "largeLanguageModel": {
        "logs": "enabled",
        "requests": {"messages": "none", "maxSizeInBytes": 0},
        "responses": {"messages": "none", "maxSizeInBytes": 0},
    },
}
APP_INSIGHTS_LOG_SETTINGS = {
    "headers": ["Content-type", "User-agent", "x-ms-region", "x-ratelimit-remaining-tokens", "x-ratelimit-remaining-requests"],
    "body": {"bytes": 0},
}


class Problem(Exception):
    """A setting the owner can fix; printed without a trace."""


def need(env, name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise Problem(f"{name} is not set (a repository secret or variable of the deployment workflow)")
    return value


def network(value: str, name: str) -> ipaddress.IPv4Network:
    try:
        net = ipaddress.ip_network(value, strict=True)
    except ValueError:
        raise Problem(f"{name} is an address range such as 10.53.0.0/24, with the host bits zero")
    if not isinstance(net, ipaddress.IPv4Network):
        raise Problem(f"{name} is an IPv4 range")
    return net


def items(value: str, name: str, limit: int) -> list[str]:
    parts = [p.strip() for p in value.split(",")]
    if not 1 <= len(parts) <= limit or any(not p for p in parts):
        raise Problem(f"{name} is a comma-separated list of 1 to {limit} values")
    return parts


def account_name(subscription: str, group: str) -> str:
    digest = hashlib.sha256(f"{subscription}/{group}".lower().encode("utf-8")).hexdigest()
    return f"aif-meternaut-{digest[:8]}"


def read_models(path: Path) -> list[dict]:
    try:
        models = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Problem(f"{path} is not a readable JSON list of models")
    if not isinstance(models, list) or not 1 <= len(models) <= 8:
        raise Problem("the model list holds 1 to 8 models")
    seen = set()
    checked = []
    for model in models:
        if not isinstance(model, dict) or set(model) != {"name", "version", "sku", "capacity", "retirementDate"}:
            raise Problem("each model has exactly: name, version, sku, capacity, retirementDate")
        if not isinstance(model["name"], str) or not MODEL_NAME.match(model["name"]) or model["name"] in seen:
            raise Problem(f"model name {model['name']!r} is not a valid, unique deployment name")
        if not isinstance(model["version"], str) or not DATE.match(model["version"]):
            raise Problem(f"the version of {model['name']} is a date such as 2026-09-22")
        if model["sku"] not in SKUS:
            raise Problem(f"the sku of {model['name']} is one of {', '.join(SKUS)}")
        if not isinstance(model["capacity"], int) or isinstance(model["capacity"], bool) or not 1 <= model["capacity"] <= 1000:
            raise Problem(f"the capacity of {model['name']} is a whole number from 1 to 1000 (thousands of tokens a minute)")
        if not isinstance(model["retirementDate"], str) or not DATE.match(model["retirementDate"]):
            raise Problem(f"the retirementDate of {model['name']} is a date such as 2028-03-11")
        seen.add(model["name"])
        checked.append(dict(model))
    return checked


def parameters(values: dict) -> dict:
    return {"$schema": SCHEMA, "contentVersion": "1.0.0.0", "parameters": {k: {"value": v} for k, v in values.items()}}


def build(env, models: list[dict], preview: bool = False) -> tuple[dict[str, dict], dict[str, str]]:
    subscription = need(env, "ENV_SUBSCRIPTION_ID")
    group = need(env, "ENV_RESOURCE_GROUP")
    location = need(env, "ENV_LOCATION")
    owner = need(env, "ENV_OWNER")
    if not GUID.match(subscription):
        raise Problem("ENV_SUBSCRIPTION_ID is a subscription id")
    if not GROUP.match(group):
        raise Problem("ENV_RESOURCE_GROUP is a resource group name (letters, digits, . _ -)")
    if not LOCATION.match(location):
        raise Problem("ENV_LOCATION is a region name such as swedencentral")
    if not OWNER.match(owner):
        raise Problem("ENV_OWNER is a short label (letters, digits, @ . _ + - and spaces)")

    gateway = GATEWAY_ID.match(need(env, "GATEWAY_RESOURCE_ID"))
    if not gateway:
        raise Problem("GATEWAY_RESOURCE_ID is the resource id of the API Management instance")
    insights = APPINSIGHTS_ID.match(need(env, "GATEWAY_APPINSIGHTS_ID"))
    if not insights:
        raise Problem("GATEWAY_APPINSIGHTS_ID is the resource id of an Application Insights component")
    if insights.group(1).lower() != gateway.group(1).lower():
        raise Problem("the Application Insights component is in the gateway's subscription")
    principal = (env.get("GATEWAY_PRINCIPAL_ID") or "").strip()
    principal_known = bool(principal)
    if not principal_known:
        if not preview:
            raise Problem("GATEWAY_PRINCIPAL_ID is not set: it is the object id of the gateway identity, made by the first deploy (a --preview run may leave it out)")
        principal = PLACEHOLDER
    if not GUID.match(principal):
        raise Problem("GATEWAY_PRINCIPAL_ID is the object id of the gateway's user-assigned identity")

    vnet = network(need(env, "ENV_VNET_PREFIX"), "ENV_VNET_PREFIX")
    subnet = network(need(env, "ENV_PE_SUBNET_PREFIX"), "ENV_PE_SUBNET_PREFIX")
    if not vnet.subnet_of(PRIVATE_SPACE) or not 16 <= vnet.prefixlen <= 28:
        raise Problem("ENV_VNET_PREFIX is inside 10.0.0.0/8 and between /16 and /28")
    if not subnet.subnet_of(vnet) or subnet.prefixlen > 29:
        raise Problem("ENV_PE_SUBNET_PREFIX lies inside the virtual network and is at least a /29")

    dns = items(need(env, "ENV_DNS_SERVERS"), "ENV_DNS_SERVERS", 3)
    for server in dns:
        try:
            address = ipaddress.ip_address(server)
        except ValueError:
            raise Problem(f"ENV_DNS_SERVERS holds an address, not {server!r}")
        if address.version != 4 or not address.is_private:
            raise Problem("ENV_DNS_SERVERS holds private IPv4 addresses: the landing zone's resolver, not a public one")

    emails = items(need(env, "ENV_ALERT_EMAILS"), "ENV_ALERT_EMAILS", 5)
    if not all(EMAIL.match(e) for e in emails):
        raise Problem("ENV_ALERT_EMAILS holds mail addresses")
    try:
        budget = int(need(env, "ENV_BUDGET_AMOUNT"))
    except ValueError:
        budget = 0
    if not 1 <= budget <= 10000:
        raise Problem("ENV_BUDGET_AMOUNT is a whole number from 1 to 10000")
    start = need(env, "ENV_BUDGET_START")
    if not BUDGET_START.match(start):
        raise Problem("ENV_BUDGET_START is the first day of a month, as YYYY-MM-01")

    name = account_name(subscription, group)
    endpoint = f"https://{name}.cognitiveservices.azure.com"
    deployed = [{k: m[k] for k in ("name", "version", "sku", "capacity")} for m in models]

    environment = {
        "location": location,
        "accountName": name,
        "vnetAddressPrefix": str(vnet),
        "peSubnetPrefix": str(subnet),
        "dnsServers": dns,
        "models": deployed,
        "gatewayPrincipalId": principal.lower(),
        "owner": owner,
        "budgetAmount": budget,
        "alertEmails": emails,
        "budgetStartDate": start,
    }
    logger = {
        "apimName": gateway.group(3),
        "appInsightsName": insights.group(3),
        "appInsightsResourceGroup": insights.group(2),
    }
    backend = {
        "backendId": name,
        "backendType": "ai-foundry",
        "endpoint": endpoint + "/",
        "authType": "managed-identity",
        "priority": 1,
        "weight": 100,
        "supportedModels": [
            {
                "name": m["name"],
                "sku": m["sku"],
                "capacity": m["capacity"],
                "modelFormat": "OpenAI",
                "modelVersion": m["version"],
                "retirementDate": m["retirementDate"],
            }
            for m in models
        ],
    }
    kit = {
        "apimServiceName": gateway.group(3),
        "managedIdentityName": IDENTITY_NAME,
        "updatePolicyFragments": True,
        "enablePIIAnonymization": True,
        "enableAIModelInference": True,
        "updateNamedValues": True,
        "aiLanguageServiceUrl": endpoint + "/",
        "contentSafetyServiceUrl": endpoint + "/",
        "updateJwtNamedValues": True,
        "enableJwtAuth": False,
        "updateLLMBackends": True,
        "updateLLMBackendPools": True,
        "updateLLMPolicyFragments": True,
        "llmBackendConfig": [backend],
        "updateUniversalLLMApi": True,
        "updateAzureOpenAIApi": True,
        "updateUnifiedAiApi": False,
        "enableUnifiedAiApi": False,
        "updateReleaseVersionApi": False,
        "updateOpenAIRealtimeApi": False,
        "updateRedisCache": False,
        "enableRedisCache": False,
        "updateEmbeddingsBackend": False,
        "enableEmbeddingsBackend": False,
        "updateAppInsightsDiagnostics": True,
        "deployAzureMonitorLogger": False,
        "azureMonitorLogSettings": AZURE_MONITOR_LOG_SETTINGS,
        "appInsightsLogSettings": APP_INSIGHTS_LOG_SETTINGS,
    }
    outputs = {
        "account_name": name,
        "private_endpoint": f"pe-{name}",
        "vnet_name": "vnet-meternaut",
        "nsg_name": "nsg-meternaut-pe",
        "endpoint": endpoint,
        "gateway_subscription": gateway.group(1).lower(),
        "gateway_resource_group": gateway.group(2),
        "gateway_name": gateway.group(3),
        "identity_name": IDENTITY_NAME,
        "principal_known": "true" if principal_known else "false",
    }
    return {
        "environment.parameters.json": parameters(environment),
        "logger.parameters.json": parameters(logger),
        "kit.parameters.json": parameters(kit),
    }, outputs


TYPES = {"string": str, "securestring": str, "int": int, "bool": bool, "array": list, "object": dict, "secureObject": dict}


def check_against(document: dict, template: dict, label: str) -> list[str]:
    """What is wrong with a parameter file for a compiled template: an unknown name, a wrong type, a missing required one."""
    declared = template.get("parameters", {})
    given = document.get("parameters", {})
    problems = []
    for name, wrapped in given.items():
        if name not in declared:
            problems.append(f"{label}: {name} is not a parameter of the template")
            continue
        expected = TYPES.get(declared[name].get("type"))
        value = wrapped.get("value")
        if expected and (not isinstance(value, expected) or (expected is int and isinstance(value, bool))):
            problems.append(f"{label}: {name} should be of type {declared[name].get('type')}")
    for name, spec in declared.items():
        if "defaultValue" not in spec and name not in given:
            problems.append(f"{label}: {name} has no default in the template and is not given")
    return problems


def run_check(args) -> int:
    try:
        document = json.loads(Path(args.params).read_text(encoding="utf-8"))
        template = json.loads(Path(args.template).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"error: cannot read the files: {e.__class__.__name__}", file=sys.stderr)
        return 2
    problems = check_against(document, template, args.label)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if not problems:
        print(f"{args.label}: the parameter file fits the template")
    return 1 if problems else 0


def run_build(args, environ) -> int:
    try:
        files, outputs = build(environ, read_models(Path(args.models)), preview=args.preview)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for file_name, document in files.items():
        (out_dir / file_name).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    for key, value in outputs.items():
        print(f"{key}={value}")
    return 0


def main(argv=None, environ=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="write the parameter files from the settings")
    build_parser.add_argument("--models", required=True, help="the JSON list of models (environment/models.json)")
    build_parser.add_argument("--out-dir", required=True, help="where to write the ARM parameter files")
    build_parser.add_argument("--preview", action="store_true", help="for a what-if: the gateway identity may not exist yet")
    check_parser = commands.add_parser("check", help="check a parameter file against a compiled template (az bicep build --outfile)")
    check_parser.add_argument("--params", required=True)
    check_parser.add_argument("--template", required=True)
    check_parser.add_argument("--label", default="parameters")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    return run_build(args, environ) if args.command == "build" else run_check(args)


if __name__ == "__main__":
    sys.exit(main())
