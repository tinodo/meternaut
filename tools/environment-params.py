#!/usr/bin/env python3
"""Builds the parameter files of the first environment from the deployment workflow's settings (standard library only).

    python tools/environment-params.py build --models environment/models.json --out-dir "$RUNNER_TEMP" [--preview] >> "$GITHUB_OUTPUT"
    python tools/environment-params.py check --params "$RUNNER_TEMP/kit.parameters.json" --template kit.json --label kit

The settings are environment variables, filled by the workflow from the repository's secrets and variables, so that no
address, name or mail address is in the repository:

    ENV_SUBSCRIPTION_ID, ENV_RESOURCE_GROUP, ENV_LOCATION, ENV_VNET_PREFIX, ENV_PE_SUBNET_PREFIX,
    ENV_DNS_SERVERS (comma separated), ENV_OWNER, ENV_BUDGET_AMOUNT, ENV_ALERT_EMAILS (comma separated),
    ENV_BUDGET_START, GATEWAY_RESOURCE_ID, GATEWAY_APPINSIGHTS_ID, GATEWAY_PRINCIPAL_ID, GATEWAY_CLIENT_ID,
    RECORDING_DEPLOYER_ID, RECORDING_READER_IDS (comma separated, may be empty), RECORDING_FRAGMENTS (true or false),
    CASES_SYSTEM_PRINCIPAL_ID (may be empty), ENV_FOUNDRY_PROJECT_EXISTS (true or false)

ENV_BUDGET_START is the first day of the month in which the budget was first made, which the workflow reads from the
existing budget (a budget keeps its start date) or, for a new budget, takes from the current month.
GATEWAY_RESOURCE_ID is the resource id of the owner's existing API Management instance; GATEWAY_APPINSIGHTS_ID is the
resource id of the Application Insights component that the instance already logs to; GATEWAY_PRINCIPAL_ID is the object
id of the gateway's user-assigned identity, which does not exist before the first deploy (a `--preview`, for a
what-if, then uses a placeholder, and says so). GATEWAY_CLIENT_ID is that identity's client id, which the Event Hub loggers
name: without it the file for the loggers is not written (and with `--preview` it holds a placeholder).
RECORDING_FRAGMENTS is `true` only when both Event Hub loggers exist in the instance: the workflow reads that from the
instance, and the kit's module then also makes the two policy fragments that use them (default: false).
RECORDING_DEPLOYER_ID is the object id of the identity that the workflow signs in as (the workflow reads it from its own
token): it gets the right to send to the control hub of the usage recording, so that the check can start a copy job once.
Nothing reads the usage store with it (the store has no public endpoint). RECORDING_READER_IDS are the object ids of the
people who may read the usage store (a Cosmos DB data role; they also need a network path to its private endpoint).
CASES_SYSTEM_PRINCIPAL_ID is the object id of the cases app's system-assigned identity, which the workflow reads from the app: the Foundry resource of
the agents gives it the Foundry User role on its project. The app has no such identity before the action `cases` has run once; without it the Foundry
file holds a placeholder, says cases_system_principal_known=false, and the workflow refuses to deploy the Foundry resource. Like the other object ids it
is checked as a GUID and never printed when it is not one. CASES_PRINCIPAL_ID, the object id of the user-assigned identity id-meternaut-cases that the
system-assigned one replaced, is no longer read: the workflow does not look for the two retired identities, and a person removes them (environment/BOOTSTRAP.md).
ENV_FOUNDRY_PROJECT_EXISTS is true when the workflow found the Foundry
project in Azure: only then does the cases file carry the project's endpoint (an empty endpoint switches the investigation off).

It writes five ARM parameter files into --out-dir (seven, with --contract: the contract's and the first cases'; eight when the gateway identity's client id is known):

    environment.parameters.json       for environment/main.bicep (the model side)
    logger.parameters.json            for environment/gateway/logger.bicep
    eventhub-loggers.parameters.json  for environment/gateway/eventhub-loggers.bicep (written when GATEWAY_CLIENT_ID is set, or with --preview)
    kit.parameters.json               for the Citadel gateway-upgrade module (the kit's bicep/infra/apim-gateway-upgrade/main.bicep)
    recording.parameters.json         for environment/recording/main.bicep (the usage recording: Event Hubs, function app, Cosmos DB)
    foundry.parameters.json           for environment/foundry/main.bicep (the Foundry resource of the agents: project, models, guardrail, private endpoint)
    contract.parameters.json          for environment/gateway/contract.bicep, from --contract (environment/contract.json) and
                                      --contract-policy (environment/gateway/contract-policy.xml)
    cases.parameters.json             for environment/cases/main.bicep (the first cases: the function app that finds leads and writes the
                                      History); written together with the contract, because it names the contract's subscription whose
                                      key the app reads at the start of a run

Every value is checked before anything is deployed. The name of the model account is worked out here, from the
subscription and the resource group, so it is the same on every run (a run after a removal finds, and the workflow
restores, the soft-deleted account of that name instead of leaving a second one behind); so are the names of the usage
recording's storage account, Event Hubs namespace, Cosmos DB account and function app, which are host names too, and the name of the
Foundry resource of the agents (aif-meternaut-agents-<digest>, also a host name, which is not the model account's). The
function app's subnet is the first /27 of the virtual network that does not overlap the private endpoint subnet, and the
subnet of the first cases' Basic plan is the first /27 that overlaps neither of those two. It prints
key=value lines for GitHub to read as step outputs.

The contract names only models that are deployed (environment/models.json) and only the two inference APIs that the
kit's module makes here, asks for a token rate that the smallest of its model deployments can serve, and its policy is
the template with the contract's numbers put in and then read back as XML, so a template that lost a rule, that gained
one (a branch, a second assignment of the models, anything the template does not have, at any depth), or that counted
the tokens of all consumers together, is refused here.

The settings of the kit's module are chosen here and explained here, not in the workflow, so that a test can hold them:
  - The personal-data flag stays on, because the module creates the `ai-foundry-compatibility` policy fragment only then,
    and the inference APIs' policies include that fragment unconditionally. The Language and Content Safety addresses are
    the model account's own (a named value may not be empty).
  - No prompt and no answer is logged: the LLM log settings say `none` for both, so only token counts and the model's name
    are kept. The service refuses the value `none` for the messages, so environment/kit-patches/llm-log-messages-none.patch
    makes the kit's inference-api.bicep leave the request and response settings out when the parameter says `none`.
  - The two policy fragments that send usage records to an Event Hub (`ai-usage`, `pii-state-saving`) are created only when
    both loggers that they need (`usage-eventhub-logger`, `pii-usage-eventhub-logger`) exist in the instance: the service
    refuses a fragment whose logger is missing, and the module does not make the loggers. The workflow makes the loggers
    (environment/gateway/eventhub-loggers.bicep) once the usage recording's Event Hubs namespace exists, reads the instance, and
    sets RECORDING_FRAGMENTS to true when both are there; the patch
    environment/kit-patches/no-usage-recording-fragments.patch (applied to the kit's checkout) makes the module take that choice.
  - The Unified AI API is not deployed (its update flag is off), but its enable flag is on: the module creates the
    `set-response-headers` policy fragment only with that flag, and the policies of both inference APIs include it, so
    without it the service refuses their policies ("Policy fragment ... could not be found").
  - A call that is not made with a contract's key is refused on the two inference APIs by
    environment/kit-patches/contract-required.patch: the key of the instance itself and any key that is not tied to a product
    never run a contract's policy, so its models and limits would not apply to them.
  - JWT checking is off (callers use the contract's key) until an app registration exists; the Realtime, Redis, embeddings
    and release-version parts are off; no second logger and no diagnostic setting is made for Azure Monitor.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
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
FOUNDRY_PROJECT_NAME = "meternaut"
FOUNDRY_GUARDRAIL_NAME = "meternaut-agents"
CONTRACT_NAME = re.compile(r"^[a-z][a-z0-9-]{1,58}[a-z0-9]$")
CONTRACT_KEYS = {"name", "description", "apis", "allowedModels", "tokensPerMinute", "tokenQuotaPerMonth"}
CONTRACT_APIS = ("universal-llm-api", "azure-openai-api")
POLICY_PLACEHOLDERS = ("@@ALLOWED_MODELS@@", "@@TOKENS_PER_MINUTE@@", "@@TOKEN_QUOTA@@")
POLICY_TAGS = {"policies", "inbound", "backend", "outbound", "on-error", "base", "include-fragment", "set-variable", "llm-token-limit"}
MAX_QUOTA = 1_000_000_000

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
    return f"aif-meternaut-{digest(subscription, group)}"


def digest(subscription: str, group: str) -> str:
    """Eight hex characters that depend on the subscription and the group only, so that every name made from them is stable."""
    return hashlib.sha256(f"{subscription}/{group}".lower().encode("utf-8")).hexdigest()[:8]


def recording_names(subscription: str, group: str) -> dict[str, str]:
    """The names of the usage recording's services that are host names, so unique worldwide, each inside its own length limit."""
    token = digest(subscription, group)
    return {
        "storage_account_name": f"stmeternautfn{token}",
        "event_hub_namespace": f"evhns-meternaut-{token}",
        "cosmos_account_name": f"cosmos-meternaut-{token}",
        "function_app_name": f"func-meternaut-usage-{token}",
    }


def legacy_names(subscription: str, group: str) -> dict[str, str]:
    """The key-based usage recording that the keyless one replaced: a Logic App, its plan, its connection and its storage account.

    The workflow removes exactly these four, by these names, before it deploys the keyless one, and nothing else."""
    token = digest(subscription, group)
    return {
        "legacy_logic_app_name": f"logic-meternaut-usage-{token}",
        "legacy_plan_name": "asp-meternaut-usage",
        "legacy_connection_name": "azuremonitorlogs",
        "legacy_storage_account_name": f"stmeternaut{token}",
    }


def cases_names(subscription: str, group: str) -> dict[str, str]:
    """The name of the cases app, a host name too. Everything else of the cases app has a fixed name inside the project's group."""
    return {"cases_function_app_name": f"func-meternaut-cases-{digest(subscription, group)}"}


def foundry_names(subscription: str, group: str) -> dict[str, str]:
    """The names of the Foundry resource of the agents (environment/foundry/main.bicep).

    The resource's name is a host name too, so it carries the digest, and it is not the model account's (aif-meternaut-<digest>): that account can never hold a
    project. The project's name is part of the project endpoint, which is built here from the two names, so that the workflow, the template and the cases app
    cannot disagree about it."""
    account = f"aif-meternaut-agents-{digest(subscription, group)}"
    return {
        "foundry_account_name": account,
        "foundry_project_name": FOUNDRY_PROJECT_NAME,
        "foundry_guardrail_name": FOUNDRY_GUARDRAIL_NAME,
        "foundry_private_endpoint": f"pe-{account}",
        "foundry_project_endpoint": f"https://{account}.services.ai.azure.com/api/projects/{FOUNDRY_PROJECT_NAME}",
    }


def planted_parameters(env, location: str, owner: str) -> dict:
    """The waste that the action `plant` makes: a short word for this planting (the tag value and part of the names) and whether a public IP address is planted too."""
    planted_id = (env.get("PLANTED_ID") or "demo").strip().lower()
    if not re.fullmatch(r"[a-z0-9]{1,12}", planted_id):
        raise Problem("PLANTED_ID is one to twelve lower-case letters or digits")
    public_ip = (env.get("PLANT_PUBLIC_IP") or "false").strip().lower()
    if public_ip not in ("true", "false"):
        raise Problem("PLANT_PUBLIC_IP is true or false")
    return {"location": location, "owner": owner, "plantedId": planted_id, "plantPublicIp": public_ip == "true"}


ROLES_OF_PEOPLE = ("owner", "approver", "ops")
ADDRESS = re.compile(r"^[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9.-]{1,200}\.[A-Za-z]{2,24}$")


def console_parameters(env) -> dict:
    """The console, the people and the mail of the cases app, from three optional variables. None of them is a secret: an app registration's client id,
    the people (directory object id, name, roles and address of each) and the address of the shared mailbox. Without a client id the sign-in is not set up
    and the console refuses every request."""
    client = (env.get("CONSOLE_APP_CLIENT_ID") or "").strip()
    if client and not GUID.match(client):
        raise Problem("CONSOLE_APP_CLIENT_ID is the client id of the console's app registration")
    raw = (env.get("CONSOLE_PEOPLE") or "").strip()
    people: list = []
    if raw:
        try:
            people = json.loads(raw)
        except ValueError:
            raise Problem("CONSOLE_PEOPLE is JSON")
        if not isinstance(people, list) or not 1 <= len(people) <= 20:
            raise Problem("CONSOLE_PEOPLE is a list of one to twenty people")
        for person in people:
            if not isinstance(person, dict) or not GUID.match(str(person.get("oid", ""))) or not str(person.get("name", "")).strip():
                raise Problem("each person of CONSOLE_PEOPLE has an oid (a directory object id) and a name")
            if not isinstance(person.get("roles"), list) or not person["roles"] or not all(r in ROLES_OF_PEOPLE for r in person["roles"]):
                raise Problem(f"each person of CONSOLE_PEOPLE has roles from {', '.join(ROLES_OF_PEOPLE)}")
            if person.get("mail") and not ADDRESS.match(str(person["mail"])):
                raise Problem("each address in CONSOLE_PEOPLE is an address")
        if len({p["oid"].lower() for p in people}) != len(people):
            raise Problem("an oid is listed twice in CONSOLE_PEOPLE")
    if client and not people:
        raise Problem("CONSOLE_APP_CLIENT_ID is set and CONSOLE_PEOPLE is not: the sign-in would let nobody through")
    sender = (env.get("MAIL_SENDER") or "").strip()
    if sender and not ADDRESS.match(sender):
        raise Problem("MAIL_SENDER is the address of the shared mailbox")
    return {
        "consoleAppClientId": client.lower(),
        "consolePeople": json.dumps([{**p, "oid": p["oid"].lower()} for p in people], separators=(",", ":")) if people else "[]",
        "consoleUserObjectIds": [p["oid"].lower() for p in people],
        "mailSender": sender,
    }


def function_subnet(vnet: ipaddress.IPv4Network, endpoints: ipaddress.IPv4Network) -> ipaddress.IPv4Network:
    """The subnet of the function app: the first /27 of the virtual network that does not overlap the private endpoint subnet.

    A Flex Consumption app needs a /27 at least, for itself alone: the subnet is delegated to it and cannot hold a private endpoint."""
    if vnet.prefixlen > 27:
        raise Problem("ENV_VNET_PREFIX is at least a /27 wide, so that a /27 subnet fits for the function app")
    for candidate in vnet.subnets(new_prefix=27):
        if not candidate.overlaps(endpoints):
            return candidate
    raise Problem("ENV_VNET_PREFIX has no free /27 beside the private endpoint subnet, for the function app")


def web_subnet(vnet: ipaddress.IPv4Network, endpoints: ipaddress.IPv4Network, functions: ipaddress.IPv4Network) -> ipaddress.IPv4Network:
    """The subnet of the first cases' Basic plan: the last /27 of the virtual network that overlaps neither the private endpoint subnet nor the function subnet.

    A Basic plan's virtual network integration needs a subnet of its own, delegated to Microsoft.Web/serverFarms: the function subnet is delegated to Flex Consumption
    (Microsoft.App/environments) and a subnet has one delegation. It is the last free /27, and not the first, because the first version of this subnet (snet-web, the
    first free /27) lost the route table that the landing zone's network manager had put on it, to a deploy that made the subnet again, and was replaced: the new one
    (snet-cases) takes a range that the old one never held, so that both can exist until the old one is removed."""
    for candidate in reversed(list(vnet.subnets(new_prefix=27))):
        if not candidate.overlaps(endpoints) and not candidate.overlaps(functions):
            return candidate
    raise Problem("ENV_VNET_PREFIX has no free /27 beside the private endpoint subnet and the function subnet, for the Basic plan of the first cases")


def exists_flag(env: dict, name: str) -> bool:
    """Whether the workflow found something in Azure already: true or false, and false when nobody looked.

    A template that makes a network resource again takes away what the landing zone's network manager added to it (the route table of a subnet), so the templates make the
    virtual network and the Basic plan's subnet only while they are not there, and the workflow reads that from Azure before it asks for the files."""
    value = (env.get(name) or "").strip().lower()
    if value not in ("", "true", "false"):
        raise Problem(f"{name} is true or false")
    return value == "true"


def web_subnet_exists(env: dict) -> bool:
    """Whether the Basic plan's integration subnet is in Azure already."""
    return exists_flag(env, "ENV_WEB_SUBNET_EXISTS")


def recording_endpoints(names: dict[str, str]) -> list[tuple[str, str]]:
    """The private endpoints of the usage recording and the central private DNS zone that the landing zone registers each in."""
    storage = names["storage_account_name"]
    return [
        *[(f"pe-{storage}-{service}", f"privatelink.{service}.core.windows.net") for service in ("blob", "queue", "table")],
        (f"pe-{names['cosmos_account_name']}", "privatelink.documents.azure.com"),
        (f"pe-{names['event_hub_namespace']}", "privatelink.servicebus.windows.net"),
    ]


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
        if not isinstance(model, dict) or set(model) != {"name", "version", "sku", "capacity", "agentCapacity", "retirementDate"}:
            raise Problem("each model has exactly: name, version, sku, capacity, agentCapacity, retirementDate")
        if not isinstance(model["name"], str) or not MODEL_NAME.match(model["name"]) or model["name"] in seen:
            raise Problem(f"model name {model['name']!r} is not a valid, unique deployment name")
        if not isinstance(model["version"], str) or not DATE.match(model["version"]):
            raise Problem(f"the version of {model['name']} is a date such as 2026-09-22")
        if model["sku"] not in SKUS:
            raise Problem(f"the sku of {model['name']} is one of {', '.join(SKUS)}")
        if not isinstance(model["capacity"], int) or isinstance(model["capacity"], bool) or not 1 <= model["capacity"] <= 1000:
            raise Problem(f"the capacity of {model['name']} is a whole number from 1 to 1000 (thousands of tokens a minute)")
        if not isinstance(model["agentCapacity"], int) or isinstance(model["agentCapacity"], bool) or not 1 <= model["agentCapacity"] <= 1000:
            raise Problem(f"the agentCapacity of {model['name']} is a whole number from 1 to 1000 (thousands of tokens a minute)")
        if not isinstance(model["retirementDate"], str) or not DATE.match(model["retirementDate"]):
            raise Problem(f"the retirementDate of {model['name']} is a date such as 2028-03-11")
        seen.add(model["name"])
        checked.append(dict(model))
    return checked


def parameters(values: dict) -> dict:
    return {"$schema": SCHEMA, "contentVersion": "1.0.0.0", "parameters": {k: {"value": v} for k, v in values.items()}}


def read_contract(path: Path, models: list[dict]) -> dict:
    """The contract of environment/contract.json, checked against the models that are deployed."""
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Problem(f"{path} is not a readable JSON contract")
    if not isinstance(contract, dict) or set(contract) != CONTRACT_KEYS:
        raise Problem("the contract has exactly: " + ", ".join(sorted(CONTRACT_KEYS)))
    name, description, apis = contract["name"], contract["description"], contract["apis"]
    if not isinstance(name, str) or not CONTRACT_NAME.match(name):
        raise Problem("the contract's name is 3 to 60 lowercase letters, digits and hyphens, starting with a letter")
    if not isinstance(description, str) or not 1 <= len(description) <= 400 or any(ord(c) < 32 for c in description):
        raise Problem("the contract's description is 1 to 400 characters on one line")
    if not isinstance(apis, list) or not 1 <= len(apis) <= len(CONTRACT_APIS) or len(set(map(str, apis))) != len(apis) or any(a not in CONTRACT_APIS for a in apis):
        raise Problem(f"the contract's apis are some of {', '.join(CONTRACT_APIS)}, each once")
    deployed = {m["name"]: m for m in models}
    allowed = contract["allowedModels"]
    if (not isinstance(allowed, list) or not 1 <= len(allowed) <= len(deployed) or len(set(map(str, allowed))) != len(allowed)
            or any(not isinstance(m, str) or m not in deployed for m in allowed)):
        raise Problem("the contract's allowedModels are models of environment/models.json, each once")
    rate, quota = contract["tokensPerMinute"], contract["tokenQuotaPerMonth"]
    for label, value in (("tokensPerMinute", rate), ("tokenQuotaPerMonth", quota)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise Problem(f"the contract's {label} is a whole number of at least 1")
    ceiling = min(deployed[m]["capacity"] for m in allowed) * 1000
    if rate > ceiling:
        raise Problem(f"the contract's tokensPerMinute ({rate}) is more than the smallest of its model deployments can serve ({ceiling} a minute)")
    if not rate <= quota <= MAX_QUOTA:
        raise Problem(f"the contract's tokenQuotaPerMonth is at least its tokensPerMinute and at most {MAX_QUOTA}")
    return dict(contract)


def contract_policy(template: str, contract: dict) -> str:
    """The product policy: the template with the contract's numbers in it, read back as XML to see that its rules are all there."""
    for placeholder in POLICY_PLACEHOLDERS:
        if template.count(placeholder) != 1:
            raise Problem(f"the policy template holds {placeholder} exactly once")
    policy = (template.replace("@@ALLOWED_MODELS@@", ",".join(contract["allowedModels"]))
              .replace("@@TOKENS_PER_MINUTE@@", str(contract["tokensPerMinute"]))
              .replace("@@TOKEN_QUOTA@@", str(contract["tokenQuotaPerMonth"])))
    if "@@" in policy:
        raise Problem("the policy template holds a placeholder that the contract does not fill")
    try:
        root = ET.fromstring(policy)
    except ET.ParseError as e:
        raise Problem(f"the contract's policy is not well-formed XML: {e}")
    # Only the rules of the template may be in the policy, at any depth: a <choose>, a <return-response> or a second
    # set-variable could undo the models and the limits below, and a contract is only worth what its policy holds.
    for element in root.iter():
        if element.tag not in POLICY_TAGS:
            raise Problem(f"the contract's policy holds <{element.tag}>, a rule that the policy template does not have: only {', '.join(sorted(POLICY_TAGS))} are allowed")
    inbound = root.find("inbound")
    if inbound is None:
        raise Problem("the contract's policy has no inbound section")
    models = [v for v in inbound.findall("set-variable") if v.get("name") == "allowedModels"]
    limits = inbound.findall("llm-token-limit")
    fragments = [f.get("fragment-id") for f in inbound.findall("include-fragment")]
    if len(models) != 1 or models[0].get("value") != ",".join(contract["allowedModels"]):
        raise Problem("the contract's policy sets allowedModels once, to the contract's models")
    if "set-llm-requested-model" not in fragments:
        raise Problem("the contract's policy includes set-llm-requested-model: the gateway reads the requested model with it")
    if len(limits) != 1:
        raise Problem("the contract's policy has exactly one llm-token-limit")
    expected = {"counter-key": "@(context.Subscription.Id)", "tokens-per-minute": str(contract["tokensPerMinute"]),
                "token-quota": str(contract["tokenQuotaPerMonth"]), "token-quota-period": "Monthly", "estimate-prompt-tokens": "false"}
    if {k: limits[0].get(k) for k in expected} != expected:
        raise Problem("the contract's token limit counts for each subscription, per minute and per month, as the contract says")
    # The whole shape, as a last check: the four sections in order, nothing but <base /> after the inbound section, and
    # exactly these rules, with exactly these attributes, in the inbound section.
    if root.tag != "policies" or [c.tag for c in root] != ["inbound", "backend", "outbound", "on-error"]:
        raise Problem("the contract's policy has the sections inbound, backend, outbound and on-error, in this order")
    for section in list(root)[1:]:
        if [(c.tag, dict(c.attrib), len(c)) for c in section] != [("base", {}, 0)]:
            raise Problem(f"the contract's policy has nothing but <base /> in its {section.tag} section")
    rules = [("base", {}), ("include-fragment", {"fragment-id": "set-llm-requested-model"}),
             ("set-variable", {"name": "allowedModels", "value": ",".join(contract["allowedModels"])}),
             ("llm-token-limit", expected), ("set-variable", {"name": "enableResponseHeaders", "value": "@(true)"})]
    if [(c.tag, dict(c.attrib), len(c)) for c in inbound] != [(tag, attributes, 0) for tag, attributes in rules]:
        raise Problem("the contract's inbound section has exactly the rules of the policy template, in its order: base, set-llm-requested-model, allowedModels, the token limit, enableResponseHeaders")
    return policy


def contract_files(contract: dict, template: str, gateway_name: str) -> tuple[dict, dict[str, str]]:
    subscription_name = f"{contract['name']}-sub-01"
    document = parameters({
        "apimName": gateway_name,
        "contractName": contract["name"],
        "subscriptionName": subscription_name,
        "contractDescription": contract["description"],
        "apiNames": contract["apis"],
        "policyXml": contract_policy(template, contract),
    })
    outputs = {"contract_name": contract["name"], "contract_subscription": subscription_name, "contract_apis": ",".join(contract["apis"])}
    return document, outputs


def build(env, models: list[dict], preview: bool = False, contract: dict | None = None, policy_template: str | None = None) -> tuple[dict[str, dict], dict[str, str]]:
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
    deployer = need(env, "RECORDING_DEPLOYER_ID")
    if not GUID.match(deployer):
        raise Problem("RECORDING_DEPLOYER_ID is the object id of the identity that the workflow signs in as")
    client = (env.get("GATEWAY_CLIENT_ID") or "").strip()
    if client and not GUID.match(client):
        raise Problem("GATEWAY_CLIENT_ID is the client id of the gateway's user-assigned identity")
    fragments = (env.get("RECORDING_FRAGMENTS") or "false").strip().lower()
    if fragments not in ("true", "false"):
        raise Problem("RECORDING_FRAGMENTS is true or false")
    cases_system_principal = (env.get("CASES_SYSTEM_PRINCIPAL_ID") or "").strip()
    if cases_system_principal and not GUID.match(cases_system_principal):
        raise Problem("CASES_SYSTEM_PRINCIPAL_ID is the object id of the cases app's system-assigned identity")
    foundry_exists = exists_flag(env, "ENV_FOUNDRY_PROJECT_EXISTS")
    raw_readers = (env.get("RECORDING_READER_IDS") or "").strip()
    readers = [r.strip() for r in raw_readers.split(",")] if raw_readers else []
    if len(readers) > 5 or len(set(r.lower() for r in readers)) != len(readers) or not all(GUID.match(r) for r in readers):
        raise Problem("RECORDING_READER_IDS is a comma-separated list of up to 5 object ids, each once, or empty")

    vnet = network(need(env, "ENV_VNET_PREFIX"), "ENV_VNET_PREFIX")
    subnet = network(need(env, "ENV_PE_SUBNET_PREFIX"), "ENV_PE_SUBNET_PREFIX")
    if not vnet.subnet_of(PRIVATE_SPACE) or not 16 <= vnet.prefixlen <= 28:
        raise Problem("ENV_VNET_PREFIX is inside 10.0.0.0/8 and between /16 and /28")
    if not subnet.subnet_of(vnet) or subnet.prefixlen > 28:
        raise Problem("ENV_PE_SUBNET_PREFIX lies inside the virtual network and is at least a /28: the usage recording has five private endpoints and the model account one, and Azure keeps five addresses of every subnet")

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
    names = recording_names(subscription, group)
    foundry = foundry_names(subscription, group)
    func_subnet = function_subnet(vnet, subnet)
    web = web_subnet(vnet, subnet, func_subnet)
    endpoint = f"https://{name}.cognitiveservices.azure.com"
    deployed = [{k: m[k] for k in ("name", "version", "sku", "capacity")} for m in models]
    # The Foundry resource of the agents deploys the same models with a capacity of its own: an agent that calls tools reads everything said so far again at every step,
    # so one run uses many more tokens a minute than the gateway's detective does.
    agent_deployed = [{"name": m["name"], "version": m["version"], "sku": m["sku"], "capacity": m["agentCapacity"]} for m in models]

    environment = {
        "location": location,
        "accountName": name,
        "vnetAddressPrefix": str(vnet),
        "networkExists": exists_flag(env, "ENV_NETWORK_EXISTS"),
        "peSubnetPrefix": str(subnet),
        "funcSubnetPrefix": str(func_subnet),
        "webSubnetPrefix": str(web),
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
    recording = {
        "location": location,
        "owner": owner,
        "storageAccountName": names["storage_account_name"],
        "eventHubNamespaceName": names["event_hub_namespace"],
        "cosmosAccountName": names["cosmos_account_name"],
        "functionAppName": names["function_app_name"],
        "gatewayPrincipalId": principal.lower(),
        "gatewayAppInsightsSubscriptionId": insights.group(1).lower(),
        "gatewayAppInsightsResourceGroup": insights.group(2),
        "gatewayAppInsightsName": insights.group(3),
        "workflowPrincipalId": deployer.lower(),
        "dataReaderPrincipalIds": list(dict.fromkeys(r.lower() for r in readers)),
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
        "enableUnifiedAiApi": True,
        "updateReleaseVersionApi": False,
        "updateOpenAIRealtimeApi": False,
        "updateRedisCache": False,
        "enableRedisCache": False,
        "updateEmbeddingsBackend": False,
        "enableEmbeddingsBackend": False,
        "updateAppInsightsDiagnostics": True,
        "deployAzureMonitorLogger": False,
        "deployUsageRecordingFragments": fragments == "true",
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
        "cases_system_principal_known": "true" if cases_system_principal else "false",
        "function_subnet_prefix": str(func_subnet),
        "web_subnet_prefix": str(web),
        "recording_endpoints": ",".join(f"{endpoint_name}:{zone}" for endpoint_name, zone in recording_endpoints(names)),
        "appinsights_name": "appi-meternaut",
        "cases_hub_name": "cases-control",
        "gateway_url": f"https://{gateway.group(3).lower()}.azure-api.net",
        **names,
        **cases_names(subscription, group),
        **foundry,
        **legacy_names(subscription, group),
    }
    files = {
        "environment.parameters.json": parameters(environment),
        "logger.parameters.json": parameters(logger),
        "kit.parameters.json": parameters(kit),
        "recording.parameters.json": parameters(recording),
        "foundry.parameters.json": parameters({
            "location": location,
            "accountName": foundry["foundry_account_name"],
            "projectName": foundry["foundry_project_name"],
            "guardrailName": foundry["foundry_guardrail_name"],
            "models": agent_deployed,
            "casesSystemPrincipalId": (cases_system_principal or PLACEHOLDER).lower(),
            "owner": owner,
        }),
        "planted.parameters.json": parameters(planted_parameters(env, location, owner)),
    }
    if client or preview:
        files["eventhub-loggers.parameters.json"] = parameters({
            "apimName": gateway.group(3),
            "eventHubHost": f"{names['event_hub_namespace']}.servicebus.windows.net",
            "usageHubName": "ai-usage",
            "piiHubName": "pii-usage",
            "identityClientId": (client or PLACEHOLDER).lower(),
        })
    if contract is not None:
        if policy_template is None:
            raise Problem("a contract needs its policy template")
        files["contract.parameters.json"], contract_outputs = contract_files(contract, policy_template, gateway.group(3))
        outputs.update(contract_outputs)
        if len(contract["allowedModels"]) < 2:
            raise Problem("the contract's allowedModels hold at least two models: the Skeptic of the first cases has to be another model than the Detective")
        files["cases.parameters.json"] = parameters({
            "location": location,
            "owner": owner,
            "storageAccountName": names["storage_account_name"],
            "eventHubNamespaceName": names["event_hub_namespace"],
            "functionAppName": outputs["cases_function_app_name"],
            "webSubnetPrefix": str(web),
            "webSubnetExists": web_subnet_exists(env),
            "workflowPrincipalId": deployer.lower(),
            "scopeSubscriptions": subscription.lower(),
            "gatewayUrl": outputs["gateway_url"],
            "gatewayProductSubscriptionId": f"{need(env, 'GATEWAY_RESOURCE_ID')}/subscriptions/{contract_outputs['contract_subscription']}",
            "modelDetective": contract["allowedModels"][0],
            "modelSkeptic": contract["allowedModels"][1],
            "foundryProjectEndpoint": foundry["foundry_project_endpoint"] if foundry_exists else "",
            **console_parameters(env),
        })
    return files, outputs


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
        models = read_models(Path(args.models))
        contract = policy_template = None
        if args.contract or args.contract_policy:
            if not (args.contract and args.contract_policy):
                raise Problem("--contract and --contract-policy go together")
            contract = read_contract(Path(args.contract), models)
            try:
                policy_template = Path(args.contract_policy).read_text(encoding="utf-8")
            except OSError:
                raise Problem(f"{args.contract_policy} is not a readable policy template")
        files, outputs = build(environ, models, preview=args.preview, contract=contract, policy_template=policy_template)
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
    build_parser.add_argument("--contract", help="the contract (environment/contract.json); also writes contract.parameters.json")
    build_parser.add_argument("--contract-policy", help="the contract's policy template (environment/gateway/contract-policy.xml)")
    check_parser = commands.add_parser("check", help="check a parameter file against a compiled template (az bicep build --outfile)")
    check_parser.add_argument("--params", required=True)
    check_parser.add_argument("--template", required=True)
    check_parser.add_argument("--label", default="parameters")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    return run_build(args, environ) if args.command == "build" else run_check(args)


if __name__ == "__main__":
    sys.exit(main())
