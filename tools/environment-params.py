#!/usr/bin/env python3
"""Builds the parameter files of the first environment from the deployment workflow's settings (standard library only).

    python tools/environment-params.py build --models environment/models.json --out-dir "$RUNNER_TEMP" [--preview] [--aigateway-policies environment/aigateway/policies.json] >> "$GITHUB_OUTPUT"
    python tools/environment-params.py check --params "$RUNNER_TEMP/kit.parameters.json" --template kit.json --label kit

The settings are environment variables, filled by the workflow from the repository's secrets and variables, so that no
address, name or mail address is in the repository:

    ENV_SUBSCRIPTION_ID, ENV_RESOURCE_GROUP, ENV_LOCATION, ENV_VNET_PREFIX, ENV_PE_SUBNET_PREFIX,
    ENV_DNS_SERVERS (comma separated), ENV_OWNER, ENV_BUDGET_AMOUNT, ENV_ALERT_EMAILS (comma separated),
    ENV_BUDGET_START, GATEWAY_RESOURCE_ID, GATEWAY_APPINSIGHTS_ID, GATEWAY_PRINCIPAL_ID, GATEWAY_CLIENT_ID,
    RECORDING_READER_IDS (comma separated, may be empty), RECORDING_FRAGMENTS (true or false),
    CASES_SYSTEM_PRINCIPAL_ID (may be empty), ENV_FOUNDRY_PROJECT_EXISTS (true or false), ENV_OPS_SUBNET_EXISTS (true or false)

ENV_BUDGET_START is the first day of the month in which the budget was first made, which the workflow reads from the
existing budget (a budget keeps its start date) or, for a new budget, takes from the current month.
GATEWAY_RESOURCE_ID is the resource id of the owner's existing API Management instance; GATEWAY_APPINSIGHTS_ID is the
resource id of the Application Insights component that the instance already logs to; GATEWAY_PRINCIPAL_ID is the object
id of the gateway's user-assigned identity, which does not exist before the first deploy (a `--preview`, for a
what-if, then uses a placeholder, and says so). GATEWAY_CLIENT_ID is that identity's client id, which the Event Hub loggers
name: without it the file for the loggers is not written (and with `--preview` it holds a placeholder).
RECORDING_FRAGMENTS is `true` only when both Event Hub loggers exist in the instance: the workflow reads that from the
instance, and the kit's module then also makes the two policy fragments that use them (default: false).
RECORDING_READER_IDS are the object ids of the people who may read the usage store (a Cosmos DB data role; they also need a network path to its private
endpoint). The identity that the workflow signs in as has no setting here: no template gives it a role on an event hub (the Operator sends the control
events), and the workflow reads its own object id from its token only to find and retire the assignment that it held on the two control hubs.
CASES_SYSTEM_PRINCIPAL_ID is the object id of the cases app's system-assigned identity, which the workflow reads from the app: the Foundry resource of
the agents gives it the Foundry User role on its project. The app has no such identity before the action `cases` has run once; without it the Foundry
file holds a placeholder, says cases_system_principal_known=false, and the workflow refuses to deploy the Foundry resource. Like the other object ids it
is checked as a GUID and never printed when it is not one. CASES_PRINCIPAL_ID, the object id of the user-assigned identity id-meternaut-cases that the
system-assigned one replaced, is no longer read: the workflow does not look for the two retired identities, and a person removes them (environment/BOOTSTRAP.md).
ENV_FOUNDRY_PROJECT_EXISTS is true when the workflow found the Foundry
project in Azure: only then does the cases file carry the project's endpoint (an empty endpoint switches the investigation off).
ENV_AIGW_SUBNET_EXISTS is true when the workflow found the AI Gateway's subnet (snet-aigw) in Azure: the template then leaves it alone (AGENTS.md rule 27).
FOUNDRY_PROJECT_PRINCIPAL_ID (may be empty) is the object id of the Foundry project's system-assigned identity: the AI Gateway template gives it AI Gateway Models User on the
gateway. Nothing sets it before the step that connects the project to the gateway; empty means none yet. It is checked as a GUID.
AGENTS_VIA_AI_GATEWAY (a constant near the top of this file, False) is the switch of the agents' route through the AI Gateway (docs/proposals/08-ai-gateway.md, step 2). While it is False nothing below is read,
no parameter file differs by a byte from what it was, and no output is added. When it is True: AIGATEWAY_HOST is the host name that the service reports for the gateway
(properties.frontend.defaultHostname, under .ai.gateway.azure.com), which the workflow reads from the service and passes only to the actions that need it. It goes into foundry.parameters.json with the
aliases (aiGatewayHost, aiGatewayModels), so that the Foundry resource makes the project's connection; the cases file carries the model names `<connection>/<alias>` (foundryModelInvestigator and
foundryModelSkeptic); and two outputs are added (agents_via_ai_gateway=true and aigateway_connection_name), which the workflow reads. The builder refuses True without the host when ACTION (the job's own setting,
the name of the action) is foundry, and without FOUNDRY_PROJECT_PRINCIPAL_ID when ACTION is aigateway: a --preview, and every other action, goes on without them.
CONSOLE_HOST_NAME (optional) is the host name that the console has on the platform's Application Gateway, which forwards to the cases app (docs/proposals/07-private-by-default.md). Empty: people open the
console on the app's own name. With a name, the console's address (the setting CONSOLE_HOST, which the letters' links and the return address of the Azure sign-in are built from) is that name, the cases file
passes it as consoleHostName, and the outputs console_host (the name that people open: that name, or the app's own) and console_host_set say what the check of the console's front door knocks at.
CASES_APP_PUBLIC_NETWORK_ACCESS is refused as Disabled while no name is set.

It writes five ARM parameter files into --out-dir (seven, with --contract: the contract's and the first cases'; eight when the gateway identity's client id is known):

    environment.parameters.json       for environment/main.bicep (the model side)
    logger.parameters.json            for environment/gateway/logger.bicep
    eventhub-loggers.parameters.json  for environment/gateway/eventhub-loggers.bicep (written when GATEWAY_CLIENT_ID is set, or with --preview)
    kit.parameters.json               for the Citadel gateway-upgrade module (the kit's bicep/infra/apim-gateway-upgrade/main.bicep)
    recording.parameters.json         for environment/recording/main.bicep (the usage recording: Event Hubs, function app, Cosmos DB)
    foundry.parameters.json           for environment/foundry/main.bicep (the Foundry resource of the agents: project, models, guardrail, private endpoint)
    operator.parameters.json          for environment/operator/main.bicep (the Operator: its identity, the subnet of its container groups, its three roles; it names the Event Hubs namespace
                                      whose two control hubs it reads, which the usage recording and the first cases make)
    contract.parameters.json          for environment/gateway/contract.bicep, from --contract (environment/contract.json) and
                                      --contract-policy (environment/gateway/contract-policy.xml)
    aigateway.parameters.json         for environment/aigateway/main.bicep (the AI Gateway: its subnet, models and aliases, and its roles), and
    aigateway-policies.json           the gateway-wide policies that the action aigateway applies to the gateway's default workspace (a plain list, not a parameter file),
                                      both from --aigateway-policies (environment/aigateway/policies.json, checked against the models and against the owner's standing limit
                                      of AGENTS.md rule 15 (g)); neither is written when the virtual network has no free range for the gateway's subnet (the outputs say so)
    cases.parameters.json             for environment/cases/main.bicep (the first cases: the function app that finds leads and writes the
                                      History); written together with the contract, because it names the contract's subscription whose
                                      key the app reads at the start of a run

                                      What each function app takes from the public internet is not a setting of the workflow: USAGE_APP_PUBLIC_NETWORK_ACCESS (Disabled) and CASES_APP_PUBLIC_NETWORK_ACCESS (Enabled until the
                                      people who approve have a path to the console), near the top of this file, go into recording.parameters.json and cases.parameters.json (usageAppPublicNetworkAccess,
                                      casesAppPublicNetworkAccess). Closing an app is one value and a commit, and
                                      the property is always written: an app whose value is not set has its public access switched off by the first private endpoint (docs/proposals/07-private-by-default.md).

                                      Every value is checked before anything is deployed. The name of the model account is worked out here, from the
subscription and the resource group, so it is the same on every run (a run after a removal finds, and the workflow
restores, the soft-deleted account of that name instead of leaving a second one behind); so are the names of the usage
recording's storage account, Event Hubs namespace, Cosmos DB account and function app, which are host names too, and the name of the
Foundry resource of the agents (aif-meternaut-agents-<digest>, also a host name, which is not the model account's). The
function app's subnet is the first /27 of the virtual network that does not overlap the private endpoint subnet, and the
subnet of the first cases' Basic plan is the first /27 that overlaps neither of those two. The Operator's subnet (container groups of Azure Container
Instances) is the last /27 that overlaps none of the three; Microsoft Learn recommends a /24 for container groups, which a small virtual network cannot
spare, and it is passed as a flag when it is in Azure already (ENV_OPS_SUBNET_EXISTS). The AI Gateway's subnet (snet-aigw, delegated to Microsoft.App/environments, for the gateway's own
use) is the last /26 that overlaps none of those four, and the last /27 when the network has no free /26: the service wants at least a /27, and a /26 leaves room to scale. It is passed as a
flag too when it is in Azure already (ENV_AIGW_SUBNET_EXISTS). A network with no free /27 left is not refused here: the AI Gateway is an optional preview service, so its files are not
written, the outputs say so (aigateway_subnet_prefix is empty) and the action aigateway stops with that reason. The gateway's name is aigw-meternaut-<digest>, 23 characters, inside the
service's limit of 24. It prints
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
# What each function app takes from the public internet. The usage app is closed (Disabled): it has no page for people, and its code is published from inside the network, in the Operator, through its
# private endpoint (docs/proposals/07-private-by-default.md, phases 2 and 3). The cases app stays Enabled until the people who approve have a network path to the console, which is the owner's decision
# (the same record, "The console for people"): one value, and a commit, closes it. They go into every parameter file, so that the property is never left unset: for an app whose value is not set,
# the first private endpoint switches public access off by itself (Learn, App Service access restrictions).
PUBLIC_NETWORK_ACCESS = ("Enabled", "Disabled")
USAGE_APP_PUBLIC_NETWORK_ACCESS = "Disabled"
CASES_APP_PUBLIC_NETWORK_ACCESS = "Enabled"
# Whether the two agents of the investigation call their models through the AI Gateway (docs/proposals/08-ai-gateway.md, step 2). False: they call the model deployments of their own Foundry resource, as they
# did before, and no parameter file, no output and no action differs from what it was. One value and a commit turn it on, in a change of its own, after the owner has said yes in plain words and after the actions
# aigateway and aigateway-check have passed on the real estate. True: the action foundry makes the project's connection to the gateway, the action aigateway gives the project's identity AI Gateway Models User
# on the gateway, and the action cases passes the model names `<connection>/<alias>` to the app. The way back is the value False and a run of cases (the record says what stays). Nothing here has run.
AGENTS_VIA_AI_GATEWAY = False
# The name of the project's connection to the gateway (the default of environment/foundry/main.bicep): an agent names its model `<connection>/<alias>`. The two models of the agents are the defaults of
# environment/cases/main.bicep; a test holds the three together.
AIGATEWAY_CONNECTION_NAME = "aigateway"
AGENT_MODELS = {"foundryModelInvestigator": "gpt-6.1-sol", "foundryModelSkeptic": "gpt-6-luna"}
# The host name that the service reports for the gateway (properties.frontend.defaultHostname): under the service's own domain, which the check of the gateway and the workflow ask for too.
AIGATEWAY_HOST = re.compile(r"^(?=.{4,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.ai\.gateway\.azure\.com$")
# The central private DNS zone in which the landing zone's policy registers the names of an App Service app (the app's own and its deployment site's) for the endpoint of the sub-resource `sites`.
# A Flex Consumption deployment ends with a call from the deployment site to the app's own host name, and while the zone has no record of a new endpoint that name does not resolve: the first
# `recording` after the usage app's endpoint was made failed at the publish for that reason (docs/proposals/07-private-by-default.md, phase 1). So the endpoint of an app is always waited for.
APP_ENDPOINT_ZONE = "privatelink.azurewebsites.net"
IDENTITY_NAME = "id-meternaut-gateway"
FOUNDRY_PROJECT_NAME = "meternaut"
FOUNDRY_GUARDRAIL_NAME = "meternaut-agents"
AIGATEWAY_SUBNET_NAME = "snet-aigw"
# A /26 if the network can spare it, never smaller than a /27 (the service's minimum for the gateway's subnet).
AIGATEWAY_SUBNET_LENGTHS = (26, 27)
# The service's own patterns (Learn and the REST specification of Microsoft.ApiManagement/aigateways, read 2026-11-07): the gateway's name, the name of a model resource, which has
# no dots (the deployment's name with its dots replaced by hyphens), and the name of an alias, which is the name that a caller sends and may keep its dots.
AIGATEWAY_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,22}[a-z0-9]$")
AIGATEWAY_MODEL_RESOURCE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
AIGATEWAY_ALIAS = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
# What the gateway-wide policies may hold (environment/aigateway/policies.json): a token limit and a request rate limit, each once, and cost limits with a stable id each, one for each period.
# Every one counts for each caller identity and across the whole workspace (all models), which is how the service's own baseline writes them.
AIGATEWAY_POLICY_KEYS = {
    "tokenLimit": {"type", "count", "period", "counterKey", "scope"},
    "requestRateLimit": {"type", "callsPerPeriod", "periodSeconds", "counterKey", "scope"},
    "costLimit": {"type", "id", "amount", "period", "counterKey", "scope"},
}
AIGATEWAY_TOKEN_PERIODS = {"minute": 1, "hour": 60, "day": 1440}
AIGATEWAY_COST_PERIODS = ("hour", "day", "week", "month", "year")
# The id pattern of the portal's cost limit form: letters, digits, underscore and hyphen, and no hyphen at either end.
AIGATEWAY_COST_ID = re.compile(r"^(?!-)(?!.*-$)[A-Za-z0-9_-]{1,64}$")
# The owner's standing limit, AGENTS.md rule 15 (g): at most 25 EUR of model calls in total and 5 EUR a day. A cost limit of the gateway is in US dollars, so its amount is held to the same
# numbers: while a euro is worth more than a dollar (an assumption, not checked against a rate), an amount in dollars that is at most the figure in euros is under the limit. A test holds
# these numbers to the rule's text. An hour or a day may not be above the daily figure, a longer period not above the total.
AIGATEWAY_COST_CEILING_USD = {"hour": 5, "day": 5, "week": 25, "month": 25, "year": 25}
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
# The name under which people open the console behind the platform's Application Gateway: a name of at least two labels that ends in letters, in lower case. It is an address that
# people type and that the gateway's listener answers to, so it is never a scheme, a port, a path or an address, and never one of the app's own names (<app>.azurewebsites.net).
CONSOLE_HOST_NAME = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
APP_OWN_DOMAIN = ".azurewebsites.net"


def console_host_name(env) -> str:
    """The host name that the console has on the platform's Application Gateway, from the optional variable CONSOLE_HOST_NAME, in lower case; empty when there is none.

    Empty: people open the console on the app's own name, and everything is as it was. A name makes the console's address in the letters and the return address of the Azure sign-in that name
    (the setting CONSOLE_HOST), and tells the platform's sign-in to read the host of a request from the header X-Original-Host that the gateway adds (environment/cases/main.bicep)."""
    value = (env.get("CONSOLE_HOST_NAME") or "").strip().lower()
    if not value:
        return ""
    if value.endswith(APP_OWN_DOMAIN):
        raise Problem("CONSOLE_HOST_NAME is the name that people use on the platform's Application Gateway, and not one of the app's own names: leave it empty when there is no gateway name")
    if not CONSOLE_HOST_NAME.match(value):
        raise Problem("CONSOLE_HOST_NAME is a host name such as console.example.com (letters, digits, hyphens and dots; no scheme, port or path)")
    return value


def console_parameters(env) -> dict:
    """The console, the people and the mail of the cases app, from four optional variables. None of them is a secret: an app registration's client id,
    the people (directory object id, name, roles and address of each), the address of the shared mailbox and the host name that the console has on the platform's Application Gateway.
    Without a client id the sign-in is not set up and the console refuses every request. Without a host name the console is opened on the app's own name."""
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
        "consoleHostName": console_host_name(env),
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


OPS_SUBNET_PREFIX_LENGTH = 27


def ops_subnet(vnet: ipaddress.IPv4Network, endpoints: ipaddress.IPv4Network, functions: ipaddress.IPv4Network, web: ipaddress.IPv4Network) -> ipaddress.IPv4Network:
    """The subnet of the Operator's container groups (environment/operator/main.bicep): the last /27 of the virtual network that overlaps none of the other three subnets.

    A container group of Azure Container Instances runs in a delegated subnet that holds nothing else. Microsoft Learn recommends at least a /24 for them, because a smaller
    subnet is known to run out of addresses (the platform lets go of the address of a deleted group slowly). A /24 does not fit a small virtual network, so this is the largest
    block that the network can spare. It is the last free block, like the Basic plan's subnet, so that no earlier range moves (docs/proposals/07-private-by-default.md)."""
    taken = (endpoints, functions, web)
    if vnet.prefixlen <= OPS_SUBNET_PREFIX_LENGTH:
        for candidate in reversed(list(vnet.subnets(new_prefix=OPS_SUBNET_PREFIX_LENGTH))):
            if not any(candidate.overlaps(other) for other in taken):
                return candidate
    raise Problem("ENV_VNET_PREFIX has no free /27 beside the other three subnets, for the Operator's container groups")


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


def ops_subnet_exists(env: dict) -> bool:
    """Whether the Operator's subnet is in Azure already: the template then leaves it alone, for the reason above (AGENTS.md rule 27)."""
    return exists_flag(env, "ENV_OPS_SUBNET_EXISTS")


def aigateway_name(subscription: str, group: str) -> str:
    """The name of the AI Gateway (environment/aigateway/main.bicep): aigw-meternaut-<digest>, 23 characters, one less than the service's limit of 24.

    It is the first label of the gateway's host name, which the service reports and which nothing here constructs."""
    name = f"aigw-meternaut-{digest(subscription, group)}"
    if not AIGATEWAY_NAME.match(name):
        raise Problem(f"the AI Gateway's name {name} does not fit the service's pattern: 3 to 24 lower-case letters, digits and hyphens")
    return name


def aigw_subnet(vnet: ipaddress.IPv4Network, taken: tuple[ipaddress.IPv4Network, ...]) -> ipaddress.IPv4Network | None:
    """The subnet that the AI Gateway reaches its backends through (environment/aigateway/main.bicep): the last free /26, and the last free /27 when the network has no free /26.

    The service wants a /27 at least, delegated to Microsoft.App/environments and empty, and it takes the subnet when the gateway is made (the portal says that it cannot be changed
    afterwards). A /26 leaves room to scale, and the virtual network of a small environment (a /24) can spare one. Like the Basic plan's and the Operator's, it is the last free block,
    so that no earlier range moves (docs/proposals/07-private-by-default.md). A network with no free /27 gets None: the AI Gateway is an optional preview service, so that is not an
    error of the other actions, and the action aigateway stops with that reason."""
    for length in AIGATEWAY_SUBNET_LENGTHS:
        if vnet.prefixlen <= length:
            for candidate in reversed(list(vnet.subnets(new_prefix=length))):
                if not any(candidate.overlaps(other) for other in taken):
                    return candidate
    return None


def aigw_subnet_exists(env: dict) -> bool:
    """Whether the AI Gateway's subnet is in Azure already: the template then leaves it alone (AGENTS.md rule 27)."""
    return exists_flag(env, "ENV_AIGW_SUBNET_EXISTS")


def ai_gateway_host(env: dict, preview: bool) -> str:
    """The host name of the AI Gateway for the agents' route through it: AIGATEWAY_HOST. Empty while AGENTS_VIA_AI_GATEWAY is False, and then the setting is not even read.

    The workflow reads the host from the service (properties.frontend.defaultHostname), only for the actions that use it, and the builder never makes one up: it is the target of the project's connection.
    A True switch that cannot name the gateway is refused when the action is foundry, the one that makes the connection (ACTION is the job's own setting). A --preview, and every action that makes no
    connection, goes on without a host, and the parameters of the connection are then left out of the file."""
    if not AGENTS_VIA_AI_GATEWAY:
        return ""
    host = (env.get("AIGATEWAY_HOST") or "").strip().lower()
    if not host:
        if (env.get("ACTION") or "").strip() == "foundry" and not preview:
            raise Problem("AGENTS_VIA_AI_GATEWAY (in tools/environment-params.py) is True and the AI Gateway cannot be named: AIGATEWAY_HOST, the host name that the service reports for it, is not set, so the Foundry "
                          "project's connection cannot be made. Run the action aigateway first (the workflow reads the host name from the service), or set the constant back to False")
        return ""
    if not AIGATEWAY_HOST.match(host):
        raise Problem("AIGATEWAY_HOST is the host name that the service reports for the AI Gateway, under .ai.gateway.azure.com")
    return host


def agent_models(models: list[dict]) -> dict[str, str]:
    """The model names that the cases app is given when the agents go through the AI Gateway: `<connection>/<alias>`, the alias being the deployment's name (environment/aigateway/main.bicep)."""
    deployed = {m["name"] for m in models}
    missing = [name for name in AGENT_MODELS.values() if name not in deployed]
    if missing:
        raise Problem(f"AGENTS_VIA_AI_GATEWAY (in tools/environment-params.py) is True and the models of the agents ({', '.join(missing)}) are not in environment/models.json: there is no alias to name")
    if not all(AIGATEWAY_ALIAS.match(m["name"]) for m in models):
        raise Problem("the model names are the gateway's aliases: letters, digits, _ . and - only")
    return {parameter: f"{AIGATEWAY_CONNECTION_NAME}/{name}" for parameter, name in AGENT_MODELS.items()}


def recording_endpoints(names: dict[str, str]) -> list[tuple[str, str]]:
    """The private endpoints of the usage recording and the central private DNS zone that the landing zone registers each in: the three of the storage account, the Cosmos DB account's, the
    Event Hubs namespace's and the function app's own. The workflow waits for every one of them before it publishes the code. The app's own is in the list because the deployment of a package ends
    with a call from the deployment site to the app's own host name, which does not resolve until the zone has the record (docs/proposals/07-private-by-default.md, phase 1)."""
    storage = names["storage_account_name"]
    return [
        *[(f"pe-{storage}-{service}", f"privatelink.{service}.core.windows.net") for service in ("blob", "queue", "table")],
        (f"pe-{names['cosmos_account_name']}", "privatelink.documents.azure.com"),
        (f"pe-{names['event_hub_namespace']}", "privatelink.servicebus.windows.net"),
        (f"pe-{names['function_app_name']}", APP_ENDPOINT_ZONE),
    ]


def cases_endpoints(names: dict[str, str]) -> list[tuple[str, str]]:
    """The private endpoint of the cases app (the console's name and its deployment site) and the central private DNS zone that the landing zone registers it in. The action `cases` waits for it
    before it publishes the code, as `recording` waits for the usage app's: the two apps behave alike, and a later probe from the Operator finds the names."""
    return [(f"pe-{names['cases_function_app_name']}", APP_ENDPOINT_ZONE)]


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


def read_aigateway_policies(path: Path, models: list[dict]) -> list[dict]:
    """The gateway-wide policies of environment/aigateway/policies.json, checked against the models and against the owner's standing limit (AGENTS.md rule 15 (g)).

    Only the three types of the plan are allowed, each with exactly its keys, so that a policy cannot carry a setting that nothing here has seen: an ipFilter or a cors policy
    belongs to the plan only with values, and the file has none. The file holds a token limit, a request rate limit and at least one cost limit, so that a commit that drops one
    is refused. The token limit is held to the largest token rate of the agents' deployments (models.json, agentCapacity), because a limit above it would limit nothing."""
    try:
        policies = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Problem(f"{path} is not a readable JSON list of policies")
    if not isinstance(policies, list) or not 1 <= len(policies) <= 8:
        raise Problem("the gateway-wide policies are a list of 1 to 8 policies")

    def whole(value, low: int, high: int) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high

    per_minute = max(m["agentCapacity"] for m in models) * 1000
    kinds: list[str] = []
    cost_ids: set[str] = set()
    cost_periods: set[str] = set()
    checked = []
    for policy in policies:
        kind = policy.get("type") if isinstance(policy, dict) else None
        if kind not in AIGATEWAY_POLICY_KEYS:
            raise Problem(f"a gateway-wide policy is one of: {', '.join(AIGATEWAY_POLICY_KEYS)}")
        if set(policy) != AIGATEWAY_POLICY_KEYS[kind]:
            raise Problem(f"a {kind} policy has exactly: {', '.join(sorted(AIGATEWAY_POLICY_KEYS[kind]))}")
        if policy["counterKey"] != ["identity"]:
            raise Problem(f'the counterKey of a {kind} policy is ["identity"]: each caller has a counter of its own')
        if policy["scope"] != "workspace":
            raise Problem(f"the scope of a {kind} policy is workspace: it counts across all models")
        if kind == "tokenLimit":
            if policy["period"] not in AIGATEWAY_TOKEN_PERIODS:
                raise Problem(f"the period of the token limit is one of {', '.join(AIGATEWAY_TOKEN_PERIODS)}")
            ceiling = per_minute * AIGATEWAY_TOKEN_PERIODS[policy["period"]]
            if not whole(policy["count"], 1, ceiling):
                raise Problem(f"the count of the token limit is a whole number from 1 to {ceiling}: the largest agentCapacity of environment/models.json for that period")
        elif kind == "requestRateLimit":
            if not whole(policy["callsPerPeriod"], 1, 1000) or not whole(policy["periodSeconds"], 1, 3600):
                raise Problem("the request rate limit is callsPerPeriod from 1 to 1000 and periodSeconds from 1 to 3600")
        else:
            if not isinstance(policy["id"], str) or not AIGATEWAY_COST_ID.match(policy["id"]) or policy["id"] in cost_ids:
                raise Problem("each cost limit has its own stable id: letters, digits, _ and -, with no - at either end")
            if policy["period"] not in AIGATEWAY_COST_PERIODS or policy["period"] in cost_periods:
                raise Problem(f"each cost limit has its own period, one of {', '.join(AIGATEWAY_COST_PERIODS)}")
            ceiling = AIGATEWAY_COST_CEILING_USD[policy["period"]]
            amount = policy["amount"]
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 < amount <= ceiling:
                raise Problem(f"the amount of the cost limit for a {policy['period']} is a number above 0 and at most {ceiling} (US dollars): the owner's standing limit, AGENTS.md rule 15 (g)")
            cost_ids.add(policy["id"])
            cost_periods.add(policy["period"])
        if kind in kinds and kind != "costLimit":
            raise Problem(f"the file holds one {kind} policy at most")
        kinds.append(kind)
        checked.append(dict(policy))
    missing = [kind for kind in AIGATEWAY_POLICY_KEYS if kind not in kinds]
    if missing:
        raise Problem(f"the gateway-wide policies hold a token limit, a request rate limit and a cost limit: {', '.join(missing)} is missing")
    return checked


def aigateway_files(env: dict, subscription: str, group: str, location: str, owner: str, vnet: ipaddress.IPv4Network, taken: tuple[ipaddress.IPv4Network, ...],
                    foundry: dict[str, str], models: list[dict], policies: list[dict], preview: bool = False) -> tuple[dict, dict[str, str]]:
    """The AI Gateway's parameter file and policy file, and its outputs (environment/aigateway/main.bicep; the action aigateway applies the policies).

    A network with no free range for the gateway's subnet gets no file: aigateway_files is false, aigateway_subnet_prefix is empty, and the action says why it stops.
    A model's resource in the gateway has the deployment's name with its dots replaced by hyphens (the service's pattern allows none); its alias keeps the name.
    While AGENTS_VIA_AI_GATEWAY is True the action aigateway gives the Foundry project's identity AI Gateway Models User, so it needs the identity's object id: without it the builder refuses
    (a --preview goes on, and any other action leaves the setting alone)."""
    resources = [m["name"].replace(".", "-") for m in models]
    if len(set(resources)) != len(resources) or not all(AIGATEWAY_MODEL_RESOURCE.match(r) for r in resources):
        raise Problem("the model names make the names of the gateway's model resources (the dots become hyphens): each is 3 to 63 lower-case letters, digits and hyphens, and no two are the same")
    if not all(AIGATEWAY_ALIAS.match(m["name"]) for m in models):
        raise Problem("the model names are the gateway's aliases: letters, digits, _ . and - only")
    project_principal = (env.get("FOUNDRY_PROJECT_PRINCIPAL_ID") or "").strip()
    if project_principal and not GUID.match(project_principal):
        raise Problem("FOUNDRY_PROJECT_PRINCIPAL_ID is the object id of the Foundry project's system-assigned identity, or empty")
    if AGENTS_VIA_AI_GATEWAY and not project_principal and not preview and (env.get("ACTION") or "").strip() == "aigateway":
        raise Problem("AGENTS_VIA_AI_GATEWAY (in tools/environment-params.py) is True and FOUNDRY_PROJECT_PRINCIPAL_ID is not set: the Foundry project's identity gets AI Gateway Models User on the gateway, and "
                      "the project has no identity to give it to. Run the action foundry first, or set the constant back to False")
    name = aigateway_name(subscription, group)
    prefix = aigw_subnet(vnet, taken)
    outputs = {
        "aigateway_name": name,
        "aigateway_subnet_name": AIGATEWAY_SUBNET_NAME,
        "aigateway_subnet_prefix": str(prefix) if prefix else "",
        "aigateway_aliases": " ".join(m["name"] for m in models),
        "aigateway_files": "true" if prefix else "false",
    }
    if prefix is None:
        return {}, outputs
    files = {
        "aigateway.parameters.json": parameters({
            "location": location,
            "owner": owner,
            "gatewayName": name,
            "aigwSubnetPrefix": str(prefix),
            "aigwSubnetExists": aigw_subnet_exists(env),
            "foundryAccountName": foundry["foundry_account_name"],
            "models": [{"name": m["name"], "version": m["version"]} for m in models],
            "foundryProjectPrincipalId": project_principal.lower(),
        }),
        "aigateway-policies.json": policies,
    }
    return files, outputs


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


def build(env, models: list[dict], preview: bool = False, contract: dict | None = None, policy_template: str | None = None,
          aigateway_policies: list[dict] | None = None) -> tuple[dict[str, dict | list], dict[str, str]]:
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
        raise Problem("ENV_PE_SUBNET_PREFIX lies inside the virtual network and is at least a /28: the usage recording has five private endpoints, the model account one, the Foundry resource one and each of the two function apps one, and Azure keeps five addresses of every subnet")
    for setting, value in (("USAGE_APP_PUBLIC_NETWORK_ACCESS", USAGE_APP_PUBLIC_NETWORK_ACCESS), ("CASES_APP_PUBLIC_NETWORK_ACCESS", CASES_APP_PUBLIC_NETWORK_ACCESS)):
        if value not in PUBLIC_NETWORK_ACCESS:
            raise Problem(f"{setting} (in tools/environment-params.py) is Enabled or Disabled, so that the template always writes the property")
    if not isinstance(AGENTS_VIA_AI_GATEWAY, bool):
        raise Problem("AGENTS_VIA_AI_GATEWAY (in tools/environment-params.py) is True or False")
    gateway_host = ai_gateway_host(env, preview)
    console_host = console_host_name(env)
    if CASES_APP_PUBLIC_NETWORK_ACCESS == "Disabled" and not console_host:
        # A closed app answers nobody outside the network, so the check of the console's front door, which knocks from the runner, would have nothing to knock at and would pass or fail for
        # the wrong reason; people would have no address either. Refused here, in every action, rather than left out of a run without a word (docs/proposals/07-private-by-default.md).
        raise Problem("CASES_APP_PUBLIC_NETWORK_ACCESS (in tools/environment-params.py) is Disabled and CONSOLE_HOST_NAME is not set. The cases app would take no public traffic, so nobody could open "
                      "the console, and the check of its front door, which knocks from the runner, would have no address to knock at: what a visitor without a sign-in gets would not be checked. "
                      "Set CONSOLE_HOST_NAME to the console's host name on the platform's Application Gateway once the gateway and its DNS record exist (environment/BOOTSTRAP.md), "
                      "or leave the app's public access Enabled")

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
    ops = ops_subnet(vnet, subnet, func_subnet, web)
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
        "dataReaderPrincipalIds": list(dict.fromkeys(r.lower() for r in readers)),
        "usageAppPublicNetworkAccess": USAGE_APP_PUBLIC_NETWORK_ACCESS,
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
        "ops_subnet_prefix": str(ops),
        "operator_identity_name": "id-meternaut-operator",
        "operator_subnet_name": "snet-ops",
        "recording_endpoints": ",".join(f"{endpoint_name}:{zone}" for endpoint_name, zone in recording_endpoints(names)),
        "cases_endpoints": ",".join(f"{endpoint_name}:{zone}" for endpoint_name, zone in cases_endpoints(cases_names(subscription, group))),
        "appinsights_name": "appi-meternaut",
        "cases_hub_name": "cases-control",
        "console_host": console_host or f"{cases_names(subscription, group)['cases_function_app_name']}{APP_OWN_DOMAIN}",
        "console_host_set": "true" if console_host else "false",
        "cases_public_network_access": CASES_APP_PUBLIC_NETWORK_ACCESS,
        "gateway_url": f"https://{gateway.group(3).lower()}.azure-api.net",
        **names,
        **cases_names(subscription, group),
        **foundry,
        **legacy_names(subscription, group),
    }
    # The connection to the AI Gateway is asked for only while the switch is on and the host is known: the parameters are left out otherwise, so that the file is what it was (the template's defaults are empty).
    foundry_values = {
        "location": location,
        "accountName": foundry["foundry_account_name"],
        "projectName": foundry["foundry_project_name"],
        "guardrailName": foundry["foundry_guardrail_name"],
        "models": agent_deployed,
        "casesSystemPrincipalId": (cases_system_principal or PLACEHOLDER).lower(),
        "owner": owner,
    }
    routed = agent_models(models) if AGENTS_VIA_AI_GATEWAY else {}
    if gateway_host:
        foundry_values["aiGatewayHost"] = gateway_host
        foundry_values["aiGatewayModels"] = [{"name": m["name"], "version": m["version"]} for m in models]
    files = {
        "environment.parameters.json": parameters(environment),
        "logger.parameters.json": parameters(logger),
        "kit.parameters.json": parameters(kit),
        "recording.parameters.json": parameters(recording),
        "foundry.parameters.json": parameters(foundry_values),
        "planted.parameters.json": parameters(planted_parameters(env, location, owner)),
        "operator.parameters.json": parameters({
            "location": location,
            "owner": owner,
            "opsSubnetPrefix": str(ops),
            "opsSubnetExists": ops_subnet_exists(env),
            "eventHubNamespaceName": names["event_hub_namespace"],
        }),
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
            "scopeSubscriptions": subscription.lower(),
            "gatewayUrl": outputs["gateway_url"],
            "gatewayProductSubscriptionId": f"{need(env, 'GATEWAY_RESOURCE_ID')}/subscriptions/{contract_outputs['contract_subscription']}",
            "modelDetective": contract["allowedModels"][0],
            "modelSkeptic": contract["allowedModels"][1],
            "foundryProjectEndpoint": foundry["foundry_project_endpoint"] if foundry_exists else "",
            "casesAppPublicNetworkAccess": CASES_APP_PUBLIC_NETWORK_ACCESS,
            **console_parameters(env),
            **routed,
        })
    if aigateway_policies is not None:
        aigateway_written, aigateway_outputs = aigateway_files(env, subscription, group, location, owner, vnet, (subnet, func_subnet, web, ops), foundry, models, aigateway_policies, preview)
        files.update(aigateway_written)
        outputs.update(aigateway_outputs)
    if AGENTS_VIA_AI_GATEWAY:
        outputs.update({"agents_via_ai_gateway": "true", "aigateway_connection_name": AIGATEWAY_CONNECTION_NAME})
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
        files, outputs = build(environ, models, preview=args.preview, contract=contract, policy_template=policy_template,
                               aigateway_policies=read_aigateway_policies(Path(args.aigateway_policies), models) if args.aigateway_policies else None)
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
    build_parser.add_argument("--aigateway-policies", help="the AI Gateway's gateway-wide policies (environment/aigateway/policies.json); also writes aigateway.parameters.json and aigateway-policies.json")
    check_parser = commands.add_parser("check", help="check a parameter file against a compiled template (az bicep build --outfile)")
    check_parser.add_argument("--params", required=True)
    check_parser.add_argument("--template", required=True)
    check_parser.add_argument("--label", default="parameters")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    return run_build(args, environ) if args.command == "build" else run_check(args)


if __name__ == "__main__":
    sys.exit(main())
