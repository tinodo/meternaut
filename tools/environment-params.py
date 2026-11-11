#!/usr/bin/env python3
"""Builds the parameter files of the first environment from the deployment workflow's settings (standard library only).

    python tools/environment-params.py build --models environment/models.json --out-dir "$RUNNER_TEMP" [--preview] [--aigateway-policies environment/aigateway/policies.json [--governance environment/aigateway/contracts.json]] [--powerplatform] >> "$GITHUB_OUTPUT"
    python tools/environment-params.py check --params "$RUNNER_TEMP/base.parameters.json" --template base.json --label base

The settings are environment variables, filled by the workflow from the repository's secrets and variables, so that no
address, name or mail address is in the repository:

    ENV_SUBSCRIPTION_ID, ENV_RESOURCE_GROUP, ENV_LOCATION, ENV_VNET_PREFIX, ENV_PE_SUBNET_PREFIX,
    ENV_DNS_SERVERS (comma separated), ENV_OWNER, ENV_BUDGET_AMOUNT, ENV_ALERT_EMAILS (comma separated),
    ENV_BUDGET_START,
    CASES_SYSTEM_PRINCIPAL_ID (may be empty), ENV_FOUNDRY_PROJECT_EXISTS (true or false), ENV_OPS_SUBNET_EXISTS (true or false)

ENV_BUDGET_START is the first day of the month in which the budget was first made, which the workflow reads from the
existing budget (a budget keeps its start date) or, for a new budget, takes from the current month.
Nothing here reads, makes or names anything of the owner's API Management instance, of the usage recording or of the first model account: they were removed on 2026-11-07 (the usage recording
copied the calls of that instance, and nothing called the model account any more), and the action retire-old (tools/retire-old.py) deletes what is left of them in the project's resource group.
The identity that the workflow signs in as has no setting here: no template gives it a role on the control queue (the Operator puts the control message there, with a role of its own on that one queue).
CASES_SYSTEM_PRINCIPAL_ID is the object id of the cases app's system-assigned identity, which the workflow reads from the app: the Foundry resource of
the agents gives it the Foundry User role on its project. The app has no such identity before the action `cases` has run once; without it the Foundry
file holds a placeholder, says cases_system_principal_known=false, and the workflow refuses to deploy the Foundry resource. Like the other object ids it
is checked as a GUID and never printed when it is not one. CASES_PRINCIPAL_ID, the object id of the user-assigned identity id-meternaut-cases that the
system-assigned one replaced, is no longer read: the workflow does not look for the two retired identities, and a person removes them (environment/BOOTSTRAP.md).
ENV_FOUNDRY_PROJECT_EXISTS is true when the workflow found the Foundry
project in Azure: only then does the cases file carry the project's endpoint (an empty endpoint switches the investigation off).
ENV_AIGW_SUBNET_EXISTS is true when the workflow found the AI Gateway's subnet (snet-aigw) in Azure: the template of the subnet (environment/aigateway/subnet.bicep) then leaves it alone (AGENTS.md rule 27).
FOUNDRY_PROJECT_PRINCIPAL_ID (may be empty) is the object id of the Foundry project's system-assigned identity: the AI Gateway template gives it AI Gateway Models User on the
gateway. Nothing sets it before the step that connects the project to the gateway; empty means none yet. It is checked as a GUID.
AIGATEWAY_HOST is the host name that the service reports for the AI Gateway (properties.frontend.defaultHostname, under .ai.gateway.azure.com), which the workflow reads from the service for the
actions that need it and the builder never makes up. Every model call of the cases app goes through the gateway (AGENTS.md rule 15 (c)), so the cases file always carries it (aiGatewayHost, which
the app reads as AIGATEWAY_HOST): the action cases is refused without it, and a --preview and the what-if action use the placeholder PLACEHOLDER_AIGATEWAY_HOST instead. A value that is set is
checked, whatever the action. The same host serves the agents' route when the switch below is on.
CASES_SYSTEM_PRINCIPAL_ID is also the principal of the role AI Gateway Models User on the AI Gateway, which the file of the gateway (casesPrincipalId) gives it: the Detective and the Skeptic call the
gateway with that identity. Empty means none yet, and the gateway is then made without the role; the next run of the action aigateway gives it.
OPERATOR_PRINCIPAL_ID (optional, may be empty) is the object id of the Operator's user-assigned identity (id-meternaut-operator), which the workflow reads from Azure for the actions foundry and what-if (the governance
file reads it too, for the access list). While it is set, foundry.parameters.json carries it as operatorPrincipalId and the Foundry resource gives that identity the Foundry User role on its project, which the tools
agents-drift, foundry-evals and foundry-redteam need (docs/proposals/11-agent-harness-and-evaluation.md); empty, the file is what it was and no role is made. It is checked as a GUID and never printed when it is not one.
AGENTS_VIA_AI_GATEWAY (a constant near the top of this file, True) is the switch of the agents' route through the AI Gateway (docs/proposals/08-ai-gateway.md, step 2). While it is True: AIGATEWAY_HOST goes into
foundry.parameters.json with the aliases (aiGatewayHost, aiGatewayModels), so that the Foundry resource makes the project's connection; the cases file carries the model names `<connection>/<alias>`
(foundryModelInvestigator and foundryModelSkeptic); and two outputs are added (agents_via_ai_gateway=true and aigateway_connection_name), which the workflow reads. The builder refuses True without the host
when ACTION (the job's own setting, the name of the action) is foundry, and without FOUNDRY_PROJECT_PRINCIPAL_ID when ACTION is aigateway: a --preview, and every other action, goes on without them. While it is
False, which is the way back, the Foundry file has no connection and the cases file has the plain model names of the agents, and no output is added.
CONSOLE_HOST_NAME (optional) is the host name that the console has on the platform's Application Gateway, which forwards to the cases app (docs/proposals/07-private-by-default.md). Empty: people open the
console on the app's own name. With a name, the console's address (the setting CONSOLE_HOST, which the letters' links and the return address of the Azure sign-in are built from) is that name, the cases file
passes it as consoleHostName, and the outputs console_host (the name that people open: that name, or the app's own) and console_host_set say what the check of the console's front door knocks at.
CASES_APP_PUBLIC_NETWORK_ACCESS may be Disabled with no name set: that is how the owner closes the web page and reaches it on the private network, and nothing is refused. The output door_in_operator says
where the check of the front door runs. False: from the runner, at the name that people open. True (only for Disabled and no name): inside the network, in the Operator, at the app's own name, because a closed app
answers nobody outside the network (docs/proposals/07-private-by-default.md).
CASES_APP_PLAN (a constant near the top of this file, "Flex") is the plan that the cases app, which serves the web page, runs on: "Flex" (Flex Consumption: it scales to zero and bills per execution, which is what
the owner ordered; on 2026-11-08 the platform held the web page's requests there for 50 to 60 seconds, and the owner ordered Flex again) or "Basic" (B1, always on, about 13 US dollars a month: the way back, and only the
owner's word uses it). It goes into cases.parameters.json as casesAppPlan, and seven outputs tell the workflow what to do with it: cases_app_plan, cases_plan_name and cases_plan_tier (the plan that the template makes), cases_other_plan_name
and cases_other_plan_tier (the plan of the other kind, which the action cases removes by that exact name and only while it is of that tier, with its app, when the kind has changed), cases_subnet_name (snet-func for Flex, snet-cases for
Basic) and function_subnet_name (snet-func). The builder refuses any other value. A test builds the files for both values (docs/proposals/07-private-by-default.md, "The web page on Flex Consumption").

The AI security (docs/proposals/10-ai-security-and-governance.md) adds three things, each of which leaves every file and every output as it was unless its constant or its setting is on.
GATEWAY_TELEMETRY (a constant, True) puts otlpIngestion into base.parameters.json, which turns on the OpenTelemetry ingestion of the Application Insights component that the AI Gateway's telemetry exporter
(environment/aigateway/telemetry.bicep, the action gateway-telemetry) sends to, and adds the output gateway_telemetry=true, so that the action base reads first that the resource provider Microsoft.Monitor is registered.
BUILD_COMMIT (the git commit) and PACKAGE_SHA256 (the digest of the cases app's own files at that commit, tools/source-digest.py) go into cases.parameters.json as buildCommit and packageSha256 when they are set: the cases app
gets them as the app settings BUILD_COMMIT and PACKAGE_SHA256, and the action cases writes them as tags of the app after the publish (tools/drift-check.py reads the tags and compares the commit with main). --governance (with --aigateway-policies) reads the access list of the gateway
(environment/aigateway/contracts.json), checks it against the models and the policies, and writes governance.parameters.json (environment/governance/main.bicep) and gateway-telemetry.parameters.json. The settings
that it reads are OPERATOR_PRINCIPAL_ID (the object id of the Operator's identity; the other two identities of the access list are CASES_SYSTEM_PRINCIPAL_ID and FOUNDRY_PROJECT_PRINCIPAL_ID), ENV_FOUNDRY_DIAGNOSTICS_EXIST
(true when a diagnostic setting of the Foundry resource sends to a workspace already: the landing zone's policy makes one) and GUARDRAIL_INITIATIVE_AVAILABLE (true when the tenant offers the preview initiative); the
constants APPROVED_MODELS_EFFECT and MODEL_ELIGIBILITY_EFFECT (Audit, and Deny after a clean run) set the effect of the two policies of the project's group.

It writes these ARM parameter files into --out-dir:

    environment.parameters.json       for environment/main.bicep (the action model-side: the virtual network with its subnets, and the budget)
    base.parameters.json              for environment/base/main.bicep (the action base: the Log Analytics workspace, Application Insights and the storage account)
    foundry.parameters.json           for environment/foundry/main.bicep (the Foundry resource of the agents: project, models, guardrail, private endpoint)
    operator.parameters.json          for environment/operator/main.bicep (the Operator: its identity, the subnet of its container groups, its two roles; it names the storage account
                                      whose control queue it reads, which the first cases make in the storage account of the base)
    aigateway-subnet.parameters.json  for environment/aigateway/subnet.bicep (the AI Gateway's subnet and its network security group: the action aigateway deploys it first, and waits for the
                                      landing zone's route table on the subnet before it deploys the gateway),
    aigateway.parameters.json         for environment/aigateway/main.bicep (the AI Gateway: its models and aliases, and its roles; the subnet has to be there already), and
    aigateway-policies.json           the gateway-wide policies that the action aigateway applies to the gateway's default workspace (a plain list, not a parameter file),
                                      all three from --aigateway-policies (environment/aigateway/policies.json, checked against the models and against the owner's standing limit
                                      of AGENTS.md rule 15 (g)); none is written when the virtual network has no free range for the gateway's subnet (the outputs say so)
    governance.parameters.json        for environment/governance/main.bicep (the policies of the project's group, the alert rules, the workbook), and
    gateway-telemetry.parameters.json for environment/aigateway/telemetry.bicep (the gateway's telemetry exporter); both only with --governance (environment/aigateway/contracts.json)
    cases.parameters.json             for environment/cases/main.bicep (the first cases: the function app that finds leads and writes the History). It is always written, and it names nothing of
                                      the owner's API Management instance: the Detective and the Skeptic call the AI Gateway, so the file carries the gateway's host name (aiGatewayHost, from
                                      AIGATEWAY_HOST, or the placeholder for a preview and a what-if), and the project's address (when ENV_FOUNDRY_PROJECT_EXISTS says that the project is in Azure). Their two
                                      model names are the defaults of the template, which are names of environment/models.json and the aliases of the gateway (a test holds the three together).
                                      It also says what the Watch reads: scopeSubscriptions (this estate's subscription, the fallback) and
                                      scopeAllSubscriptions, the constant SCOPE_ALL_SUBSCRIPTIONS near the top of this file (True: every subscription that the app's identity can read).

                                      What the cases app takes from the public internet is not a setting of the workflow: CASES_APP_PUBLIC_NETWORK_ACCESS (Enabled until the
                                      owner closes the web page, which he reaches on the private network), near the top of this file, goes into cases.parameters.json
                                      (casesAppPublicNetworkAccess). Closing an app is one value and a commit, and
                                      the property is always written: an app whose value is not set has its public access switched off by the first private endpoint (docs/proposals/07-private-by-default.md).

                                      Every value is checked before anything is deployed. The name of the base's storage account, which is a host name too, and of the
cases app, are worked out here, from the subscription and the resource group, so they are the same on every run; so is the name of the
Foundry resource of the agents (aif-meternaut-agents-<digest>, also a host name). The
function subnet (snet-func, for a Flex Consumption app) is the first /27 of the virtual network that does not overlap the private endpoint subnet, and the
subnet of the first cases' Basic plan is the first /27 that overlaps neither of those two. The Operator's subnet (container groups of Azure Container
Instances) is the last /27 that overlaps none of the three; Microsoft Learn recommends a /24 for container groups, which a small virtual network cannot
spare, and it is passed as a flag when it is in Azure already (ENV_OPS_SUBNET_EXISTS). The AI Gateway's subnet (snet-aigw, delegated to Microsoft.App/environments, for the gateway's own
use) is the last /26 that overlaps none of those four, and the last /27 when the network has no free /26: the service wants at least a /27, and a /26 leaves room to scale. It is passed as a
flag too when it is in Azure already (ENV_AIGW_SUBNET_EXISTS), and it has a parameter file of its own, apart from the gateway's, because the action makes the subnet first and waits for the landing zone's route
table on it before it makes the gateway. A network with no free /27 left is not refused here: the AI Gateway is an optional preview service, so its files are not
written, the outputs say so (aigateway_subnet_prefix is empty) and the action aigateway stops with that reason. The gateway's name is aigw-meternaut-<digest>, 23 characters, inside the
service's limit of 24. It prints
key=value lines for GitHub to read as step outputs.

Virtual network support for Power Platform (docs/proposals/19-teams-cards-through-power-automate.md) is asked for with --powerplatform, and nothing else of the output changes without it. It writes one more file,

    powerplatform.parameters.json     for environment/powerplatform/main.bicep (the subnet snet-powerplatform, delegated to Microsoft.PowerPlatform/enterprisePolicies, and the enterprise policy
                                      ep-meternaut-netinjection of the Power Platform geography Sweden, whose one Azure region is swedencentral),

and these lines: powerplatform_subnet_name, powerplatform_subnet_prefix, powerplatform_policy_name, powerplatform_geography, powerplatform_files (true or false), powerplatform_reason (why there is no file)
and cards_queue_name (the Storage queue that environment/cases/main.bicep makes for the Teams cards). The subnet is the last free /27 of the virtual network beside the five other subnets (the AI Gateway's
included, whether or not its files are asked for); no range is invented: a network with no free /27, or a region other than swedencentral, gets no file and a reason. ENV_PP_SUBNET_EXISTS and ENV_PP_POLICY_EXISTS
(true or false) are what the workflow found in Azure: a subnet that is there is left alone (AGENTS.md rule 27), and a policy that is there is not written again, because Power Platform refuses every write to a
policy that an environment is linked to.
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
PRIVATE_SPACE = ipaddress.ip_network("10.0.0.0/8")
SKUS = ("DataZoneStandard", "GlobalStandard")
PLACEHOLDER = "00000000-0000-0000-0000-000000000000"
# What the cases app takes from the public internet. It stays Enabled until the owner closes it: one value, and a commit, and he then reaches the web page on the private
# network (the build takes Disabled with a host name on a gateway and without one: with none, the check of the front door runs in the Operator, door_in_operator). It goes into the parameter file, so that
# the property is never left unset: for an app whose value is not set, the first private endpoint switches public access off by itself (Learn, App Service access restrictions).
PUBLIC_NETWORK_ACCESS = ("Enabled", "Disabled")
CASES_APP_PUBLIC_NETWORK_ACCESS = "Enabled"
# The plan that the cases app, which serves the web page, runs on: "Flex" (Flex Consumption: it scales to zero and bills per execution, so an idle web page costs nothing; the app uses the function subnet snet-func)
# or "Basic" (B1, always on, about 13 US dollars a month; the app uses its own subnet snet-cases). It is Flex, because the owner ordered it: on 2026-11-07, and again on 2026-11-08 at 09:39, after a move to Basic.
# The first cases ran on Flex and moved to Basic on 2026-11-05 because the platform's front end held requests to the web page for 15 to 60 seconds; on 2026-11-08 the same hold was measured (50 to 60 seconds, some
# answered with a 503 after exactly 60 seconds, from inside the network and from outside it, while the app's own time was 0 seconds), the page went to Basic, and the owner ordered Flex again. The record is
# docs/proposals/07-private-by-default.md, "The web page on Flex Consumption". The measurements are reported to the owner, who decides: the constant goes back to "Basic" only on his word. One value and a commit
# change it, and the action cases then clears the app of the other kind, its plan and its private endpoint (tools/cases-move.py) and makes the new ones.
CASES_APP_PLAN = "Flex"
CASES_APP_PLANS = ("Flex", "Basic")
# The plan of each kind, by its exact name (environment/cases/main.bicep makes them: a test holds the names together) and the tier that Azure reports for it. The action cases removes the other kind's app and plan
# by these names only, and only while the plan is of that tier.
CASES_PLAN_NAMES = {"Flex": "plan-meternaut-cases", "Basic": "plan-meternaut-cases-basic"}
CASES_PLAN_TIERS = {"Flex": "FlexConsumption", "Basic": "Basic"}
# The subnet that the app is integrated with, by kind: the function subnet that the model side made and that is delegated to Microsoft.App/environments (Flex), or the subnet delegated to Microsoft.Web/serverFarms (Basic).
CASES_SUBNET_NAMES = {"Flex": "snet-func", "Basic": "snet-cases"}
# What the Watch of the cases app reads (docs/proposals/02-first-cases.md). True: every subscription that the app's own system-assigned identity can read, which a person widens or narrows with
# the read-only roles Reader and Cost Management Reader at a subscription or at the management group above it (the owner's order of 2026-11-07: watch the entire estate). Until those roles exist
# above the pilot subscription the identity reads only that one, so the Watch simply reads that one. False: only the subscription of this estate (cases.parameters.json: scopeSubscriptions). The value
# reaches the app as the setting SCOPE_ALL_SUBSCRIPTIONS; it grants nothing, and what the console may change stays the one resource group of this estate.
SCOPE_ALL_SUBSCRIPTIONS = True
# Whether the two agents of the investigation call their models through the AI Gateway (docs/proposals/08-ai-gateway.md, step 2). True: the action foundry makes the project's connection to the gateway,
# the action aigateway gives the project's identity AI Gateway Models User on the gateway, and the action cases passes the model names `<connection>/<alias>` to the app. It is True in code since the change
# that the owner ordered on 2026-11-07, and the order of the real run follows from it: aigateway, a wait of about ten minutes for the new role, foundry, cases, cases-run. That run was made on 2026-11-08
# and its record is in docs/proposals/08-ai-gateway.md (what the first real runs showed). False is the way back: the agents then call the model deployments of their own Foundry resource, as they did before, and no parameter file, no
# output and no action differs from what it was (a test holds that, with the constant set to False inside the test). The record says what stays after a way back.
AGENTS_VIA_AI_GATEWAY = True
# The size of the virtual machine that the action plant makes when plant_vm is set (environment/cases/planted.bicep). A burstable size that has a smaller one in its series, so that the family resize-vm
# has a step to take (Standard_B4als_v2 to Standard_B2als_v2). The older burstable sizes (Standard_B2s and its series) are not available to this subscription in Sweden Central (the real run of 2026-11-09
# was refused: NotAvailableForSubscription), and the cheapest size of the v2 series, Standard_B2ts_v2, has none smaller. At the price list of Sweden Central (public Retail Prices API, read on
# 2026-11-09) it costs 0.138 US dollars an hour while it runs (Linux), nothing for compute once it is stopped and released, and 0.0389 after the resize. One value and a commit change it.
PLANTED_VM_SIZE = "Standard_B4als_v2"
# The name of the project's connection to the gateway (the default of environment/foundry/main.bicep): an agent names its model `<connection>/<alias>`. The two models of the agents are the defaults of
# environment/cases/main.bicep; a test holds the three together.
AIGATEWAY_CONNECTION_NAME = "aigateway"
# The Investigator calls tools, so its model has to take function tools on the Chat Completions route, which is the only route that the Agent Service has for the gateway (Learn: Responses
# routing for the AI Gateway tier is "coming soon"). The first three real runs (2026-11-08) showed that neither GPT-6 model of the gateway can: gpt-6.1-sol and gpt-6-luna refuse function tools
# together with any reasoning effort there, and refuse the effort none (low, medium and high only). Learn documents that limit for the gpt-5.6 models only, and lists gpt-5.5 (version 2026-04-24)
# with Chat Completions and function tools and with no such footnote. So the Investigator is gpt-5.5, the third model of environment/models.json, and the Skeptic, which has no tools and sends no
# effort, is gpt-6.1-sol. A test pins the pair and the reason.
AGENT_MODELS = {"foundryModelInvestigator": "gpt-5.5", "foundryModelSkeptic": "gpt-6.1-sol"}
# The host name that the service reports for the gateway (properties.frontend.defaultHostname): under the service's own domain, which the check of the gateway and the workflow ask for too.
AIGATEWAY_HOST = re.compile(r"^(?=.{4,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.ai\.gateway\.azure\.com$")
# What the cases file carries for the gateway's host name in a --preview and in a what-if, where the gateway may not be in Azure yet. It matches the pattern above and is no gateway: the action cases
# never deploys it (it is refused without the real host).
PLACEHOLDER_AIGATEWAY_HOST = "placeholder-gateway.ai.gateway.azure.com"
# The central private DNS zone in which the landing zone's policy registers the names of an App Service app (the app's own and its deployment site's) for the endpoint of the sub-resource `sites`.
# A Flex Consumption deployment ends with a call from the deployment site to the app's own host name, and while the zone has no record of a new endpoint that name does not resolve: the first
# publish after the first Flex Consumption app's endpoint was made failed for that reason (docs/proposals/07-private-by-default.md, phase 1). So the endpoint of an app is always waited for.
APP_ENDPOINT_ZONE = "privatelink.azurewebsites.net"
FOUNDRY_PROJECT_NAME = "meternaut"
FOUNDRY_GUARDRAIL_NAME = "meternaut-agents"
AIGATEWAY_SUBNET_NAME = "snet-aigw"
# A /26 if the network can spare it, never smaller than a /27 (the service's minimum for the gateway's subnet).
AIGATEWAY_SUBNET_LENGTHS = (26, 27)
# Virtual network support for Power Platform (docs/proposals/19-teams-cards-through-power-automate.md; environment/powerplatform/main.bicep). Everything about it is written only with --powerplatform, so that no
# other file and no other line of the output differs from what it was. The subnet is delegated to Microsoft.PowerPlatform/enterprisePolicies and holds nothing else. Its size: an environment that is not
# production needs 6 to 10 addresses and Azure keeps five of every subnet, so a /28 (11 usable) is the least, and a production environment needs 25 to 30, which is a /26 (Learn, "Estimating subnet size for Power
# Platform environments", read 2026-11-11). It is a /27 (27 usable): room for a second environment of the same kind, and a free /27 left in a /24 that has one. The range cannot be changed once the subnet is
# delegated and an environment is linked: an unlink, the change, a wait of 30 minutes, a link, and for the range a request to Microsoft support. So this is one value, chosen before the first deploy; the builder
# never invents a range outside the virtual network, and when the network has no free block of this size it writes no file and says so (powerplatform_reason).
POWERPLATFORM_SUBNET_NAME = "snet-powerplatform"
POWERPLATFORM_SUBNET_LENGTH = 27
# The policy's name is the template's (environment/powerplatform/main.bicep: ep-<workload>-netinjection) and the tool's default; a test holds the three together. The geography is the Power Platform name of the one
# Azure region that the template allows (Learn: Sweden is swedencentral and nothing else); the policy's location is the geography and not an Azure region.
POWERPLATFORM_POLICY_NAME = "ep-meternaut-netinjection"
POWERPLATFORM_GEOGRAPHY = "sweden"
POWERPLATFORM_AZURE_REGION = "swedencentral"
# The queue of the Teams cards (environment/cases/main.bicep makes it; the app's setting TEAMS_CARDS_QUEUE and the flow's environment variable carry the name).
CARDS_QUEUE_NAME = "teams-cards"
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

# The AI security (docs/proposals/10-ai-security-and-governance.md). Each constant is a switch or a setting that one line changes, in a change of its own.
# Whether the Application Insights component has its OpenTelemetry ingestion on. The AI Gateway's telemetry exporter (environment/aigateway/telemetry.bicep, made by the action gateway-telemetry) sends to the
# endpoints that this makes, so the action base carries it (otlpIngestion in base.parameters.json) and reads, before it deploys, that the resource provider Microsoft.Monitor is registered. False is the way back:
# the property is then not written, which is what the template did before.
GATEWAY_TELEMETRY = True
# The effect of the policies that the action governance assigns to the project's resource group: "Audit" shows a model deployment that is not approved, "Deny" refuses it. They start at Audit and go to Deny
# when a run of the action governance and a run of the action drift-check have shown every deployment compliant, which is a change of one line here.
APPROVED_MODELS_EFFECT = "Audit"
MODEL_ELIGIBILITY_EFFECT = "Audit"
POLICY_EFFECTS = ("Audit", "Deny")
# The preview initiative "Guardrail for Cognitive Services Deployments" (it can only audit) is assigned while this is True and the tenant offers it (the workflow reads that: GUARDRAIL_INITIATIVE_AVAILABLE).
# The generally available fallback is the guardrail meternaut-agents on every deployment, whose filters the drift check reads one by one, so False loses no control.
GUARDRAIL_INITIATIVE_PREVIEW = True
# The customer-managed key policy (audit) is assigned while this is True, with the kinds that it leaves out by default emptied so that the Foundry resource is judged. It is False: the owner has not decided on
# customer-managed keys, which need a key vault with purge protection, and a Foundry resource with Microsoft-managed keys would show as non-compliant for ever.
AUDIT_CUSTOMER_MANAGED_KEYS = False
# The asset id of a model of the Azure OpenAI catalog, as the approved-models policy matches it: a prefix, and a slash at the end limits it to that model (every version of it) and no other whose name begins alike.
MODEL_ASSET_PREFIX = "azureml://registries/azure-openai/models/"
# The role that lets an identity list and call the gateway's models and nothing else, and the settings that carry the object ids of the three identities that hold it (environment/aigateway/contracts.json).
GATEWAY_MODELS_USER_ROLE = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"
CONTRACT_IDENTITIES = {"cases": "CASES_SYSTEM_PRINCIPAL_ID", "foundry-project": "FOUNDRY_PROJECT_PRINCIPAL_ID", "operator": "OPERATOR_PRINCIPAL_ID"}
# What has to be run first when an identity of the access list is not there: the cases app's identity is made with the app, the project's with the Foundry resource, the Operator's by the action operator.
CONTRACT_IDENTITY_MAKERS = {"cases": "cases", "foundry-project": "foundry", "operator": "operator"}
# A caller's name goes into a Kusto string and a workbook's JSON: letters, digits, spaces and a few marks, and no quote of either kind.
CALLER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ().,-]{0,62}$")
CONTRACT_KEYS = {"id", "caller", "roles", "identity", "aliases", "purpose", "owner", "dataClass", "limits", "reviewTrigger"}
# A git commit (40 hex digits, or 64 for a repository that uses SHA-256) and the SHA-256 digest of the cases app's own files, as the deploy of the cases app records them (BUILD_COMMIT and PACKAGE_SHA256).
GIT_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


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


def digest(subscription: str, group: str) -> str:
    """Eight hex characters that depend on the subscription and the group only, so that every name made from them is stable."""
    return hashlib.sha256(f"{subscription}/{group}".lower().encode("utf-8")).hexdigest()[:8]


def base_names(subscription: str, group: str) -> dict[str, str]:
    """The name of the base's storage account, which is a host name, so unique worldwide, inside its length limit."""
    token = digest(subscription, group)
    return {"storage_account_name": f"stmeternautfn{token}"}


def cases_names(subscription: str, group: str) -> dict[str, str]:
    """The name of the cases app, a host name too. Everything else of the cases app has a fixed name inside the project's group."""
    return {"cases_function_app_name": f"func-meternaut-cases-{digest(subscription, group)}"}


def foundry_names(subscription: str, group: str) -> dict[str, str]:
    """The names of the Foundry resource of the agents (environment/foundry/main.bicep).

    The resource's name is a host name too, so it carries the digest. The project's name is part of the project endpoint, which is built here from the two names, so that the workflow, the template and the cases app
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
    """The waste that the action `plant` makes: a short word for this planting (the tag value and part of the names), whether a public IP address is planted too, and whether a virtual machine
    that nothing uses is planted too (with the size that PLANTED_VM_SIZE names)."""
    planted_id = (env.get("PLANTED_ID") or "demo").strip().lower()
    if not re.fullmatch(r"[a-z0-9]{1,12}", planted_id):
        raise Problem("PLANTED_ID is one to twelve lower-case letters or digits")
    public_ip = (env.get("PLANT_PUBLIC_IP") or "false").strip().lower()
    if public_ip not in ("true", "false"):
        raise Problem("PLANT_PUBLIC_IP is true or false")
    machine = (env.get("PLANT_VM") or "false").strip().lower()
    if machine not in ("true", "false"):
        raise Problem("PLANT_VM is true or false")
    return {"location": location, "owner": owner, "plantedId": planted_id, "plantPublicIp": public_ip == "true", "plantVm": machine == "true", "plantedVmSize": PLANTED_VM_SIZE}


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
    """The subnet that the AI Gateway reaches its backends through (environment/aigateway/subnet.bicep makes it): the last free /26, and the last free /27 when the network has no free /26.

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


def powerplatform_subnet(vnet: ipaddress.IPv4Network, taken: tuple[ipaddress.IPv4Network, ...]) -> ipaddress.IPv4Network | None:
    """The subnet of Power Platform's connectors (environment/powerplatform/main.bicep makes it): the last free block of POWERPLATFORM_SUBNET_LENGTH that overlaps none of the others.

    Like the Basic plan's, the Operator's and the AI Gateway's it is the last free block, so that no earlier range moves (docs/proposals/07-private-by-default.md). A network with no free block of that
    size gets None: the builder invents no range, and the action says that the owner has to decide (docs/proposals/19-teams-cards-through-power-automate.md)."""
    if vnet.prefixlen <= POWERPLATFORM_SUBNET_LENGTH:
        for candidate in reversed(list(vnet.subnets(new_prefix=POWERPLATFORM_SUBNET_LENGTH))):
            if not any(candidate.overlaps(other) for other in taken):
                return candidate
    return None


def powerplatform_files(env: dict, location: str, owner: str, vnet: ipaddress.IPv4Network, taken: tuple[ipaddress.IPv4Network, ...]) -> tuple[dict, dict[str, str]]:
    """The parameter file of environment/powerplatform/main.bicep and its outputs (the Hub action powerplatform; docs/proposals/19-teams-cards-through-power-automate.md).

    No file is written, and powerplatform_reason says why, when the region is not the one Azure region of the Power Platform geography Sweden, or when the virtual network has no free block for the subnet.
    The two flags say what the workflow found in Azure: a subnet that is there is left alone (AGENTS.md rule 27), and a policy that is there is not written, because Power Platform refuses every write to a
    policy that an environment is linked to."""
    prefix = powerplatform_subnet(vnet, taken)
    reason = ""
    if location != POWERPLATFORM_AZURE_REGION:
        reason = (f"ENV_LOCATION is {location}: the Power Platform geography Sweden has one Azure region, {POWERPLATFORM_AZURE_REGION}, and the subnet and the enterprise policy are made there only")
    elif prefix is None:
        reason = (f"the virtual network has no free /{POWERPLATFORM_SUBNET_LENGTH} beside its other subnets, and no range is invented: the owner decides whether a smaller subnet (a /28 is the least), a larger virtual "
                  "network or another place will do")
    outputs = {
        "powerplatform_subnet_name": POWERPLATFORM_SUBNET_NAME,
        "powerplatform_subnet_prefix": str(prefix) if prefix and not reason else "",
        "powerplatform_policy_name": POWERPLATFORM_POLICY_NAME,
        "powerplatform_geography": POWERPLATFORM_GEOGRAPHY,
        "powerplatform_files": "false" if reason else "true",
        "powerplatform_reason": reason,
        "cards_queue_name": CARDS_QUEUE_NAME,
    }
    if reason:
        return {}, outputs
    files = {
        "powerplatform.parameters.json": parameters({
            "location": location,
            "owner": owner,
            "powerPlatformSubnetPrefix": str(prefix),
            "powerPlatformSubnetExists": exists_flag(env, "ENV_PP_SUBNET_EXISTS"),
            "enterprisePolicyExists": exists_flag(env, "ENV_PP_POLICY_EXISTS"),
        }),
    }
    return files, outputs


def ai_gateway_host(env: dict, preview: bool) -> str:
    """The host name of the AI Gateway: AIGATEWAY_HOST, trimmed and in lower case, or empty when it is not set.

    The workflow reads the host from the service (properties.frontend.defaultHostname), only for the actions that use it, and the builder never makes one up. Every model call of the cases app goes
    through the gateway (AGENTS.md rule 15 (c)), so the action cases is refused without it, and so is the action foundry while AGENTS_VIA_AI_GATEWAY is True (the host is the target of the project's
    connection); ACTION is the job's own setting. A --preview, and every other action, goes on without a host: the cases file then carries the placeholder, and the Foundry file no connection.
    A value that is set is checked whatever the action is, and never echoed."""
    host = (env.get("AIGATEWAY_HOST") or "").strip().lower()
    if host and not AIGATEWAY_HOST.match(host):
        raise Problem("AIGATEWAY_HOST is the host name that the service reports for the AI Gateway, under .ai.gateway.azure.com")
    action = (env.get("ACTION") or "").strip()
    if not host and not preview:
        if action == "cases":
            raise Problem("the AI Gateway cannot be named: AIGATEWAY_HOST, the host name that the service reports for it, is not set, and every model call of the cases app goes through the gateway. "
                          "Run the action aigateway first (the workflow reads the host name from the service)")
        if AGENTS_VIA_AI_GATEWAY and action == "foundry":
            raise Problem("AGENTS_VIA_AI_GATEWAY (in tools/environment-params.py) is True and the AI Gateway cannot be named: AIGATEWAY_HOST, the host name that the service reports for it, is not set, so the Foundry "
                          "project's connection cannot be made. Run the action aigateway first (the workflow reads the host name from the service), or set the constant back to False")
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


def base_endpoints(names: dict[str, str]) -> list[tuple[str, str]]:
    """The private endpoints of the base and the central private DNS zone that the landing zone registers each in: the three of the storage account.
    The workflow waits for every one of them, so that an app that starts after the base is deployed finds the names of its storage private."""
    storage = names["storage_account_name"]
    return [(f"pe-{storage}-{service}", f"privatelink.{service}.core.windows.net") for service in ("blob", "queue", "table")]


def cases_endpoints(names: dict[str, str]) -> list[tuple[str, str]]:
    """The private endpoint of the cases app (the console's name and its deployment site) and the central private DNS zone that the landing zone registers it in. The action `cases` waits for it
    before it publishes the code, and a later probe from the Operator finds the names."""
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
                    foundry: dict[str, str], models: list[dict], policies: list[dict], cases_principal: str = "", preview: bool = False) -> tuple[dict, dict[str, str]]:
    """The AI Gateway's two parameter files and its policy file, and its outputs (environment/aigateway/subnet.bicep, environment/aigateway/main.bicep; the action aigateway applies the policies).

    The subnet has a file of its own, because the action deploys the subnet first, waits until the landing zone has put its route table on it, and only then deploys the gateway (AGENTS.md rule 27).
    A network with no free range for the gateway's subnet gets no file: aigateway_files is false, aigateway_subnet_prefix is empty, and the action says why it stops.
    A model's resource in the gateway has the deployment's name with its dots replaced by hyphens (the service's pattern allows none); its alias keeps the name.
    The gateway file gives AI Gateway Models User to the cases app's identity, whose object id is `cases_principal` (CASES_SYSTEM_PRINCIPAL_ID, which the workflow reads from the app): the Detective and
    the Skeptic call the gateway with it. Empty means none yet, as the app has no identity before the action cases has made it, and the gateway is then made without that role.
    While AGENTS_VIA_AI_GATEWAY is True the action aigateway gives the Foundry project's identity AI Gateway Models User too, so it needs the identity's object id: without it the builder refuses
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
        "aigateway-subnet.parameters.json": parameters({
            "location": location,
            "owner": owner,
            "aigwSubnetPrefix": str(prefix),
            "aigwSubnetExists": aigw_subnet_exists(env),
        }),
        "aigateway.parameters.json": parameters({
            "location": location,
            "owner": owner,
            "gatewayName": name,
            "foundryAccountName": foundry["foundry_account_name"],
            "models": [{"name": m["name"], "version": m["version"]} for m in models],
            "foundryProjectPrincipalId": project_principal.lower(),
            "casesPrincipalId": cases_principal.lower(),
        }),
        "aigateway-policies.json": policies,
    }
    return files, outputs


def read_contracts(path: Path, models: list[dict], policies: list[dict]) -> dict:
    """The access list of the AI Gateway (environment/aigateway/contracts.json), checked against the models and the gateway-wide policies.

    The list says, for each caller identity, which aliases it is meant to call, what for, who owns that, what data it may send, which limits apply and which event makes a person look at the entry again.
    The gateway cannot enforce the aliases (the role covers every model), so what is checked here is that the list is honest: every alias is a model of environment/models.json, every limit named is a
    policy of environment/aigateway/policies.json and every policy of that file is named (the limits count for each caller identity alone, so each caller is under all of them), one entry for each
    identity, and a review that comes from an event and not from a date (AGENTS.md rule 16)."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Problem(f"{path} is not a readable JSON document")
    if not isinstance(document, dict) or set(document) != {"version", "about", "gatewayRole", "identities", "contracts"}:
        raise Problem("the access list has exactly: version, about, gatewayRole, identities, contracts")
    if document["version"] != 1 or not isinstance(document["about"], str) or not 1 <= len(document["about"]) <= 4000:
        raise Problem("the access list is version 1 and says in `about` what it is")
    role = document["gatewayRole"]
    if not isinstance(role, dict) or set(role) != {"name", "id"} or role["id"] != GATEWAY_MODELS_USER_ROLE or not isinstance(role["name"], str):
        raise Problem(f"the role of the access list is AI Gateway Models User, id {GATEWAY_MODELS_USER_ROLE}, which environment/aigateway/main.bicep gives to each caller")
    identities = document["identities"]
    if not isinstance(identities, dict) or set(identities) != set(CONTRACT_IDENTITIES) or not all(isinstance(v, str) and v for v in identities.values()):
        raise Problem(f"the identities of the access list are {', '.join(CONTRACT_IDENTITIES)}, each with a line that says which identity it is")
    entries = document["contracts"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= len(CONTRACT_IDENTITIES):
        raise Problem(f"the access list holds one entry for each identity, {len(CONTRACT_IDENTITIES)} at most")
    deployed = {m["name"] for m in models}
    wanted = {(p["type"], p.get("id", "")) for p in policies}
    ids: set[str] = set()
    callers: set[str] = set()
    used: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != CONTRACT_KEYS:
            raise Problem(f"each entry of the access list has exactly: {', '.join(sorted(CONTRACT_KEYS))}")
        label = entry.get("id")
        if not isinstance(label, str) or not re.fullmatch(r"AC[0-9]{1,2}", label) or label in ids:
            raise Problem("each entry has its own id, AC1, AC2 and so on")
        ids.add(label)
        if not isinstance(entry["caller"], str) or not CALLER_NAME.match(entry["caller"]) or entry["caller"] in callers:
            raise Problem(f"{label}: the caller has its own short name of letters, digits, spaces and . , ( ) -, because the alert rules and the workbook print it")
        callers.add(entry["caller"])
        if entry["identity"] not in CONTRACT_IDENTITIES or entry["identity"] in used:
            raise Problem(f"{label}: the identity is one of {', '.join(CONTRACT_IDENTITIES)} and no two entries share one, so that a call is told to a caller by the identity alone")
        used.add(entry["identity"])
        roles = entry["roles"]
        if not isinstance(roles, list) or not 1 <= len(roles) <= 6 or not all(isinstance(r, str) and CALLER_NAME.match(r) for r in roles):
            raise Problem(f"{label}: roles is a list of 1 to 6 role names, the parts of the app that call the gateway with this identity")
        aliases = entry["aliases"]
        if not isinstance(aliases, list) or not aliases or len(set(aliases)) != len(aliases) or not all(isinstance(a, str) for a in aliases):
            raise Problem(f"{label}: aliases is a list of the aliases that the caller may call, each once")
        unknown = [a for a in aliases if a not in deployed]
        if unknown:
            raise Problem(f"{label}: {', '.join(unknown)} is not a model of environment/models.json, so it is not an alias of the gateway")
        for field in ("purpose", "owner", "dataClass", "reviewTrigger"):
            if not isinstance(entry[field], str) or not 10 <= len(entry[field]) <= 800:
                raise Problem(f"{label}: {field} is a sentence or two, from 10 to 800 characters")
        if re.search(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b|\b(?:daily|weekly|monthly|quarterly|annual(?:ly)?|yearly)\b|\bevery \d+ (?:days?|weeks?|months?|years?)\b", entry["reviewTrigger"], re.I):
            raise Problem(f"{label}: the review comes from an event, never from a date or a period (AGENTS.md rule 16)")
        limits = entry["limits"]
        named = []
        for limit in limits if isinstance(limits, list) else []:
            if not isinstance(limit, dict) or limit.get("type") not in AIGATEWAY_POLICY_KEYS or set(limit) - {"type", "id"}:
                raise Problem(f"{label}: a limit is {{type}} or, for a cost limit, {{type, id}}, with a type of environment/aigateway/policies.json")
            named.append((limit["type"], limit.get("id", "")))
        if not named or len(set(named)) != len(named) or set(named) != wanted:
            raise Problem(f"{label}: the limits of the entry are the policies of environment/aigateway/policies.json, each once, and no other: they count for every caller")
    if used != set(CONTRACT_IDENTITIES):
        raise Problem(f"the access list has an entry for each identity that holds the gateway's role: {', '.join(CONTRACT_IDENTITIES)}")
    return document


def per_minute_limits(policies: list[dict]) -> tuple[int, int]:
    """The token limit and the request limit of one minute, which the near-limit rule reads a minute of use against (environment/governance/alerts/near-limit.kql)."""
    token = next(p for p in policies if p["type"] == "tokenLimit")
    request = next(p for p in policies if p["type"] == "requestRateLimit")
    if token["period"] != "minute":
        raise Problem("the token limit of environment/aigateway/policies.json is per minute: the near-limit rule reads a minute of use. Change the period back, or change the rule")
    if request["periodSeconds"] != 60:
        raise Problem("the request rate limit of environment/aigateway/policies.json is per 60 seconds: the near-limit rule reads a minute of use. Change the period back, or change the rule")
    return token["count"], request["callsPerPeriod"]


def governance_files(env: dict, subscription: str, group: str, location: str, owner: str, emails: list[str], foundry: dict[str, str], models: list[dict], policies: list[dict],
                     contracts: dict, preview: bool = False) -> tuple[dict, dict[str, str]]:
    """The parameter files of the AI security (docs/proposals/10-ai-security-and-governance.md): governance.parameters.json for environment/governance/main.bicep (the policies of the project's group, the
    alert rules, the workbook and the table retention) and gateway-telemetry.parameters.json for environment/aigateway/telemetry.bicep (the AI Gateway's telemetry exporter), and their outputs.

    The access list's three identities are given by the settings CASES_SYSTEM_PRINCIPAL_ID, FOUNDRY_PROJECT_PRINCIPAL_ID and OPERATOR_PRINCIPAL_ID, which the workflow reads from Azure and which are
    checked as GUIDs and never printed when they are not. The rule that watches for a call from outside the access list needs all of them: the action governance (ACTION) is refused when one is missing,
    and the message names the action that makes it. A --preview, and every other action, goes on with the identities that are known, and the rule is left out when none is."""
    for switch, name in ((APPROVED_MODELS_EFFECT, "APPROVED_MODELS_EFFECT"), (MODEL_ELIGIBILITY_EFFECT, "MODEL_ELIGIBILITY_EFFECT")):
        if switch not in POLICY_EFFECTS:
            raise Problem(f"{name} (in tools/environment-params.py) is Audit or Deny, not {switch!r}")
    for switch, name in ((GUARDRAIL_INITIATIVE_PREVIEW, "GUARDRAIL_INITIATIVE_PREVIEW"), (AUDIT_CUSTOMER_MANAGED_KEYS, "AUDIT_CUSTOMER_MANAGED_KEYS"), (GATEWAY_TELEMETRY, "GATEWAY_TELEMETRY")):
        if not isinstance(switch, bool):
            raise Problem(f"{name} (in tools/environment-params.py) is True or False")
    token_limit, request_limit = per_minute_limits(policies)
    callers = []
    missing = []
    for entry in contracts["contracts"]:
        setting = CONTRACT_IDENTITIES[entry["identity"]]
        principal = (env.get(setting) or "").strip()
        if principal and not GUID.match(principal):
            raise Problem(f"{setting} is the object id of the {contracts['identities'][entry['identity']]}, or empty")
        if principal:
            callers.append({"name": entry["caller"], "objectId": principal.lower(), "aliases": list(entry["aliases"])})
        else:
            missing.append(entry["identity"])
    if missing and not preview and (env.get("ACTION") or "").strip() == "governance":
        makers = ", ".join(f"{CONTRACT_IDENTITY_MAKERS[name]} (the {contracts['identities'][name]})" for name in missing)
        raise Problem("the rule that watches the gateway for a call from outside the access list needs the object id of every identity on it, and these are not there yet. Run the action that makes each, then this one: "
                      + makers)
    guardrail_available = exists_flag(env, "GUARDRAIL_INITIATIVE_AVAILABLE")
    files = {
        "governance.parameters.json": parameters({
            "location": location,
            "owner": owner,
            "alertEmails": emails,
            "foundryAccountName": foundry["foundry_account_name"],
            "approvedModelAssetIds": [f"{MODEL_ASSET_PREFIX}{m['name']}/" for m in models],
            "approvedModelsEffect": APPROVED_MODELS_EFFECT,
            "modelEligibilityEffect": MODEL_ELIGIBILITY_EFFECT,
            "guardrailInitiative": GUARDRAIL_INITIATIVE_PREVIEW and guardrail_available,
            "auditCustomerManagedKeys": AUDIT_CUSTOMER_MANAGED_KEYS,
            "landingZoneDiagnostics": exists_flag(env, "ENV_FOUNDRY_DIAGNOSTICS_EXIST"),
            "callers": callers,
            "tokenLimitPerMinute": token_limit,
            "requestLimitPerMinute": request_limit,
        }),
        "gateway-telemetry.parameters.json": parameters({"gatewayName": aigateway_name(subscription, group)}),
    }
    outputs = {
        "governance_files": "true",
        "governance_approved_models_effect": APPROVED_MODELS_EFFECT,
        "governance_model_eligibility_effect": MODEL_ELIGIBILITY_EFFECT,
        "governance_guardrail_initiative": "true" if GUARDRAIL_INITIATIVE_PREVIEW and guardrail_available else "false",
        "governance_callers": str(len(callers)),
        "governance_callers_missing": ",".join(missing),
    }
    return files, outputs


def build(env, models: list[dict], preview: bool = False, aigateway_policies: list[dict] | None = None, contracts: dict | None = None,
          powerplatform: bool = False) -> tuple[dict[str, dict | list], dict[str, str]]:
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

    cases_system_principal = (env.get("CASES_SYSTEM_PRINCIPAL_ID") or "").strip()
    if cases_system_principal and not GUID.match(cases_system_principal):
        raise Problem("CASES_SYSTEM_PRINCIPAL_ID is the object id of the cases app's system-assigned identity")
    operator_principal = (env.get("OPERATOR_PRINCIPAL_ID") or "").strip()
    if operator_principal and not GUID.match(operator_principal):
        raise Problem("OPERATOR_PRINCIPAL_ID is the object id of the Operator's user-assigned identity, or empty")
    foundry_exists = exists_flag(env, "ENV_FOUNDRY_PROJECT_EXISTS")

    vnet = network(need(env, "ENV_VNET_PREFIX"), "ENV_VNET_PREFIX")
    subnet = network(need(env, "ENV_PE_SUBNET_PREFIX"), "ENV_PE_SUBNET_PREFIX")
    if not vnet.subnet_of(PRIVATE_SPACE) or not 16 <= vnet.prefixlen <= 28:
        raise Problem("ENV_VNET_PREFIX is inside 10.0.0.0/8 and between /16 and /28")
    if not subnet.subnet_of(vnet) or subnet.prefixlen > 28:
        raise Problem("ENV_PE_SUBNET_PREFIX lies inside the virtual network and is at least a /28: the base has three private endpoints (the storage account's), the Foundry resource one and the cases app one, and Azure keeps five addresses of every subnet")
    if CASES_APP_PUBLIC_NETWORK_ACCESS not in PUBLIC_NETWORK_ACCESS:
        raise Problem("CASES_APP_PUBLIC_NETWORK_ACCESS (in tools/environment-params.py) is Enabled or Disabled, so that the template always writes the property")
    if not isinstance(AGENTS_VIA_AI_GATEWAY, bool):
        raise Problem("AGENTS_VIA_AI_GATEWAY (in tools/environment-params.py) is True or False")
    if CASES_APP_PLAN not in CASES_APP_PLANS:
        raise Problem(f"CASES_APP_PLAN (in tools/environment-params.py) is Flex or Basic, not {CASES_APP_PLAN!r}: Flex (Flex Consumption) scales to zero and is the plan of the web page, and Basic (B1, always on) is the way back, on the owner's word")
    if not isinstance(SCOPE_ALL_SUBSCRIPTIONS, bool):
        raise Problem("SCOPE_ALL_SUBSCRIPTIONS (in tools/environment-params.py) is True or False")
    gateway_host = ai_gateway_host(env, preview)
    console_host = console_host_name(env)
    # A closed cases app with no host name on a gateway is a state of its own, and nothing is refused: people reach the web page on the private network, at the app's own name. The runner cannot knock at it,
    # because a closed app answers nobody outside the network, so the workflow checks the front door inside the network, in the Operator, at that name (docs/proposals/07-private-by-default.md).
    door_in_operator = CASES_APP_PUBLIC_NETWORK_ACCESS == "Disabled" and not console_host

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

    names = base_names(subscription, group)
    foundry = foundry_names(subscription, group)
    other_cases_plan = next(kind for kind in CASES_APP_PLANS if kind != CASES_APP_PLAN)
    func_subnet = function_subnet(vnet, subnet)
    web = web_subnet(vnet, subnet, func_subnet)
    ops = ops_subnet(vnet, subnet, func_subnet, web)
    # The Foundry resource of the agents deploys the models of environment/models.json with a capacity of its own: an agent that calls tools reads everything said so far again at every step,
    # so one run uses many more tokens a minute than a single model call does.
    agent_deployed = [{"name": m["name"], "version": m["version"], "sku": m["sku"], "capacity": m["agentCapacity"]} for m in models]

    environment = {
        "location": location,
        "vnetAddressPrefix": str(vnet),
        "networkExists": exists_flag(env, "ENV_NETWORK_EXISTS"),
        "peSubnetPrefix": str(subnet),
        "funcSubnetPrefix": str(func_subnet),
        "webSubnetPrefix": str(web),
        "dnsServers": dns,
        "owner": owner,
        "budgetAmount": budget,
        "alertEmails": emails,
        "budgetStartDate": start,
    }
    base = {
        "location": location,
        "owner": owner,
        "storageAccountName": names["storage_account_name"],
    }
    # The OpenTelemetry ingestion of the Application Insights component is what the AI Gateway's exporter sends to (environment/aigateway/telemetry.bicep): written only while the switch is on, so that
    # the file is what it was with the switch off, and the output says that it is on so that the action base reads, first, that the resource provider Microsoft.Monitor is registered.
    if not isinstance(GATEWAY_TELEMETRY, bool):
        raise Problem("GATEWAY_TELEMETRY (in tools/environment-params.py) is True or False")
    if GATEWAY_TELEMETRY:
        base["otlpIngestion"] = True
    # The release that the cases app is deployed for, recorded by the action cases: the git commit and the digest of the app's own files at that commit (the app's settings BUILD_COMMIT and
    # PACKAGE_SHA256; the tags that tools/drift-check.py compares with main are written by the workflow after the publish). Written only when the workflow sets them, so that no other file changes.
    build_commit = (env.get("BUILD_COMMIT") or "").strip().lower()
    if build_commit and not GIT_COMMIT.match(build_commit):
        raise Problem("BUILD_COMMIT is a git commit id: 40 hexadecimal digits")
    package_sha256 = (env.get("PACKAGE_SHA256") or "").strip().lower()
    if package_sha256 and not SHA256.match(package_sha256):
        raise Problem("PACKAGE_SHA256 is a SHA-256 digest: 64 hexadecimal digits")
    release = {**({"buildCommit": build_commit} if build_commit else {}), **({"packageSha256": package_sha256} if package_sha256 else {})}
    outputs = {
        "vnet_name": "vnet-meternaut",
        "nsg_name": "nsg-meternaut-pe",
        "cases_system_principal_known": "true" if cases_system_principal else "false",
        "function_subnet_prefix": str(func_subnet),
        "web_subnet_prefix": str(web),
        "ops_subnet_prefix": str(ops),
        "operator_identity_name": "id-meternaut-operator",
        "operator_subnet_name": "snet-ops",
        "base_endpoints": ",".join(f"{endpoint_name}:{zone}" for endpoint_name, zone in base_endpoints(names)),
        "cases_endpoints": ",".join(f"{endpoint_name}:{zone}" for endpoint_name, zone in cases_endpoints(cases_names(subscription, group))),
        "appinsights_name": "appi-meternaut",
        "cases_queue_name": "cases-control",
        "console_host": console_host or f"{cases_names(subscription, group)['cases_function_app_name']}{APP_OWN_DOMAIN}",
        "console_host_set": "true" if console_host else "false",
        "door_in_operator": "true" if door_in_operator else "false",
        "cases_public_network_access": CASES_APP_PUBLIC_NETWORK_ACCESS,
        "cases_app_plan": CASES_APP_PLAN,
        "cases_plan_name": CASES_PLAN_NAMES[CASES_APP_PLAN],
        "cases_plan_tier": CASES_PLAN_TIERS[CASES_APP_PLAN],
        "cases_other_plan_name": CASES_PLAN_NAMES[other_cases_plan],
        "cases_other_plan_tier": CASES_PLAN_TIERS[other_cases_plan],
        "cases_subnet_name": CASES_SUBNET_NAMES[CASES_APP_PLAN],
        "function_subnet_name": CASES_SUBNET_NAMES["Flex"],
        **names,
        **cases_names(subscription, group),
        **foundry,
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
    # The Operator's role on the project is asked for only while its object id is given: the file is what it was on an estate that has no Operator yet (the template's default is empty).
    if operator_principal:
        foundry_values["operatorPrincipalId"] = operator_principal.lower()
    routed = agent_models(models) if AGENTS_VIA_AI_GATEWAY else {}
    if AGENTS_VIA_AI_GATEWAY and gateway_host:
        foundry_values["aiGatewayHost"] = gateway_host
        foundry_values["aiGatewayModels"] = [{"name": m["name"], "version": m["version"]} for m in models]
    files = {
        "environment.parameters.json": parameters(environment),
        "base.parameters.json": parameters(base),
        "foundry.parameters.json": parameters(foundry_values),
        "planted.parameters.json": parameters(planted_parameters(env, location, owner)),
        "operator.parameters.json": parameters({
            "location": location,
            "owner": owner,
            "opsSubnetPrefix": str(ops),
            "opsSubnetExists": ops_subnet_exists(env),
            "storageAccountName": names["storage_account_name"],
        }),
        # The first cases need nothing of the owner's API Management instance: the file is written in every build, with the Foundry facts of this one. Every model call goes through the AI Gateway, so
        # the file always names its host (the placeholder in a preview and a what-if, where the gateway may not be in Azure yet: the action cases is refused without the real one).
        "cases.parameters.json": parameters({
            "location": location,
            "owner": owner,
            "storageAccountName": names["storage_account_name"],
            "functionAppName": outputs["cases_function_app_name"],
            "webSubnetPrefix": str(web),
            "webSubnetExists": web_subnet_exists(env),
            "casesAppPlan": CASES_APP_PLAN,
            "scopeSubscriptions": subscription.lower(),
            "scopeAllSubscriptions": SCOPE_ALL_SUBSCRIPTIONS,
            "foundryProjectEndpoint": foundry["foundry_project_endpoint"] if foundry_exists else "",
            "aiGatewayHost": gateway_host or PLACEHOLDER_AIGATEWAY_HOST,
            "casesAppPublicNetworkAccess": CASES_APP_PUBLIC_NETWORK_ACCESS,
            **console_parameters(env),
            **routed,
            **release,
        }),
    }
    if aigateway_policies is not None:
        aigateway_written, aigateway_outputs = aigateway_files(env, subscription, group, location, owner, vnet, (subnet, func_subnet, web, ops), foundry, models, aigateway_policies,
                                                               cases_system_principal, preview)
        files.update(aigateway_written)
        outputs.update(aigateway_outputs)
    if contracts is not None:
        if aigateway_policies is None:
            raise Problem("the files of the AI security are checked against the gateway-wide policies: --governance goes with --aigateway-policies")
        governance_written, governance_outputs = governance_files(env, subscription, group, location, owner, emails, foundry, models, aigateway_policies, contracts, preview)
        files.update(governance_written)
        outputs.update(governance_outputs)
    if GATEWAY_TELEMETRY:
        outputs["gateway_telemetry"] = "true"
    if AGENTS_VIA_AI_GATEWAY:
        outputs.update({"agents_via_ai_gateway": "true", "aigateway_connection_name": AIGATEWAY_CONNECTION_NAME})
    if powerplatform:
        # The subnet of Power Platform's connectors is the last free block beside the five others, whether or not the AI Gateway's file is asked for in this build, so that it never overlaps the gateway's subnet.
        gateway_range = aigw_subnet(vnet, (subnet, func_subnet, web, ops))
        taken = (subnet, func_subnet, web, ops) + ((gateway_range,) if gateway_range else ())
        powerplatform_written, powerplatform_outputs = powerplatform_files(env, location, owner, vnet, taken)
        files.update(powerplatform_written)
        outputs.update(powerplatform_outputs)
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
        if args.governance and not args.aigateway_policies:
            raise Problem("the files of the AI security are checked against the gateway-wide policies: --governance goes with --aigateway-policies")
        models = read_models(Path(args.models))
        policies = read_aigateway_policies(Path(args.aigateway_policies), models) if args.aigateway_policies else None
        contracts = read_contracts(Path(args.governance), models, policies) if args.governance else None
        files, outputs = build(environ, models, preview=args.preview, aigateway_policies=policies, contracts=contracts, powerplatform=args.powerplatform)
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
    build_parser.add_argument("--preview", action="store_true", help="for a what-if and for the first pass of the workflow: a fact that is not known yet (the AI Gateway's host name, its project's identity) does not stop the build")
    build_parser.add_argument("--aigateway-policies", help="the AI Gateway's gateway-wide policies (environment/aigateway/policies.json); also writes aigateway-subnet.parameters.json, aigateway.parameters.json and aigateway-policies.json")
    build_parser.add_argument("--governance", help="the AI Gateway's access list (environment/aigateway/contracts.json), checked against the models and the policies; also writes governance.parameters.json and gateway-telemetry.parameters.json. Needs --aigateway-policies")
    build_parser.add_argument("--powerplatform", action="store_true", help="also writes powerplatform.parameters.json for environment/powerplatform/main.bicep (the subnet of Power Platform's connectors and the enterprise policy) and the lines powerplatform_* and cards_queue_name; nothing else changes")
    check_parser = commands.add_parser("check", help="check a parameter file against a compiled template (az bicep build --outfile)")
    check_parser.add_argument("--params", required=True)
    check_parser.add_argument("--template", required=True)
    check_parser.add_argument("--label", default="parameters")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    return run_build(args, environ) if args.command == "build" else run_check(args)


if __name__ == "__main__":
    sys.exit(main())
