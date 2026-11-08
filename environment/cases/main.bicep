// The first cases of Meternaut: the function app that finds leads in the estate that its identity can read, lets two model roles work on each one
// through the AI Gateway, and writes every step to a History that a workbook shows (docs/proposals/02-first-cases.md).
//
//   timer (daily) or one control event --> Watch --> Resource Graph, Advisor, Cost Management (read only)
//   Watch --> Detective and Skeptic (chat completions through the AI Gateway, with the app's identity and no key) --> guards in code --> one telemetry line per step --> workbook
//
// What it holds: one user-assigned identity (the console's sign-in), a plan with the function app, which has a system-assigned identity of its own (the plan is of the kind that
// casesAppPlan names: Flex Consumption, or Basic, which is B1, Linux, always on), the subnet that the app is integrated with, one more event hub (the control hub) in the namespace of the
// usage recording, the roles that connect them, a longer retention for the traces table of the workspace, and the History workbook.
//
// Identities, and no right to change Azure. The app's own system-assigned identity reads the subscriptions that it was given the read-only roles for, and their cost lines, stores the
// records, holds Foundry User on its own Foundry project (a role that environment/foundry/main.bicep gives, inside the project's group: it lets the app make and run its agents),
// holds AI Gateway Models User on the AI Gateway (a role that environment/aigateway/main.bicep gives, in the same group: it lets the app call the gateway's models, which is how every model
// call of the Detective and the Skeptic goes), and holds the roles below that are for the app. The owner prefers system-assigned identities, so it took over from the user-assigned identity
// `id-meternaut-cases` in two steps (environment/BOOTSTRAP.md): first it was given the roles of the old identity next to it, and a person gave it the roles outside this
// group; then the settings moved to it and the old identity was taken off the app. This template no longer makes the old identity and no deployment removes it: a person
// removes it, and what it still holds, after `tools/access-requirements.py retire` has taken away its grants outside this group. The object id of a system-assigned
// identity exists only once the app does, so its roles are made after the app, and a new estate's app starts before it has them and waits for them. `id-meternaut-console-auth`
// stays a user-assigned identity (Microsoft documents the secretless sign-in of an App Service app only with that kind:
// https://learn.microsoft.com/azure/app-service/configure-authentication-provider-aad#use-a-managed-identity-instead-of-a-secret) and holds no role: the
// console's app registration trusts it through a federated credential, so that the platform's sign-in, and the console when it redeems the code of an Azure
// Resource Manager sign-in, present its token as the client assertion instead of a client secret. Nothing here gives Meternaut a right to write in Azure. When a
// person approves a plan, the console sends that person to Microsoft Entra to sign in to Azure Resource Manager (authorization code flow with PKCE, the delegated
// scope https://management.azure.com/user_impersonation, no refresh token) and runs the one change with that person's token: Azure checks that person's own
// rights, and its Activity Log names that person (docs/proposals/04-the-loop.md, docs/proposals/05-run-as-the-approver.md).
//
// Which plan, and why. The first cases ran on Flex Consumption. On 2026-11-05 its front end held some requests to the console for 15 to 60 seconds and answered some with "The service is
// unavailable" (CHANGELOG.md), and the app moved to a Basic plan, which has no such front end and no cold start, for about 13 US dollars a month. On 2026-11-07 the owner ordered it back
// onto Flex Consumption, which scales to zero and bills per execution: a tool that finds waste must not carry an idle plan. Whether the stall is still there is measured (the action
// page-latency) and the Basic definition stays here as the way back: one value, CASES_APP_PLAN in tools/environment-params.py, and the action cases
// (docs/proposals/07-private-by-default.md, "The web page on Flex Consumption").
//
// It makes no storage account and no namespace: the app shares the storage account (blob, queue and table private
// endpoints) and the Event Hubs namespace (private endpoint) of environment/recording/main.bicep, so nothing new is billed except the
// plan, tokens and the app's own private endpoint (below). A Flex app makes no subnet: it uses the function subnet snet-func, which the model side made and delegated to Microsoft.App/environments
// (the owner's network is small), and it keeps its code package in one container of that storage account. A Basic app makes its own integration subnet (snet-func is delegated to Flex
// Consumption and cannot serve a Basic plan) and that subnet's network security group. Either one makes one endpoint, which goes into the endpoint subnet that the model side made.
// The recording has to exist first.
//
// The app has a private endpoint of its own, for the console's name and for the deployment site (the group `sites`, in the endpoint subnet; no private DNS zone group: the landing zone's
// policy adds it, rule 19). The Operator uses it to publish the code since phase 2 of docs/proposals/07-private-by-default.md (the action cases runs operator/publish.sh in a container group of the
// Operator, as the deploy identity) and to ask the app's health address once the code is published. Nobody reaches the console on the app's own name from outside the network once it is closed: people reach it on
// consoleHostName, a host name on the platform's Application Gateway, which forwards to this endpoint (the objects that the platform team adds are in the same record), or, with no gateway (the owner's decision
// of 2026-11-07) and no consoleHostName, on the app's own name from the private network, where it resolves to this endpoint. The console keeps its public
// access until the owner closes it, which the parameter casesAppPublicNetworkAccess says, so that closing it is one value (the parameter builder takes that value with a console host name and without one:
// with none, the check of the front door runs in the Operator). The value
// is written to the app every time and is never left empty: Learn says that for a site whose value is not set, a private endpoint switches public access off by itself, and
// the people who approve a change reach the console from outside the network. The workflow waits until the landing zone has registered the endpoint's names before it publishes, so that the
// two apps behave alike: the usage app's deployment ends with a call to the app's own host name, which does not resolve before.
//
// A Basic app's subnet is made once and then left alone (webSubnetExists): the landing zone's network manager puts a route table on a new subnet
// about a minute after it is made, and a template that makes the subnet again takes that table away, and with it the subnet's way to
// the landing zone's DNS. The app on it then cannot resolve a name, and cannot start. That happened to the first subnet (snet-web) on
// 2026-11-05, in the second deploy of this template, and the subnet was replaced by this one (snet-cases).
//
// No key of any kind (AGENTS.md rule 23): the app's host storage, its Event Hubs trigger and its telemetry use its identity, its calls to the AI Gateway carry its identity's token, and its code is pushed with the deployment workflow's own identity token (no deployment password). The app reads no key at all.
//
// The app's system-assigned identity can read nothing until its Reader and Cost Management Reader roles are given, outside this template, by a person on the owner's
// written word (environment/BOOTSTRAP.md, AGENTS.md rule 18), because the deployment workflow's identity has no right there and must not get one. A person gives them
// on the pilot subscription, or on the tenant root management group: the Watch reads every subscription that its identity can read (scopeAllSubscriptions, below), so a
// grant at the group is all that it takes to watch the entire estate, and removing it brings the Watch back to the subscriptions that are still granted. This template grants nothing.
//
// The agents: when the Foundry resource of the agents exists (environment/foundry/main.bicep, the action foundry), the workflow passes the address of its
// project, and the app then lets agents of that project investigate the estate (the settings FOUNDRY_* and INVESTIGATE*). The app signs in to the project with
// its own identity, and the template of the Foundry resource gives that identity its role on the project. Without the address the investigation is off.
//
// The model calls of the Detective and the Skeptic need the AI Gateway (environment/aigateway/main.bicep, the action aigateway), which is the one address that they call: the workflow reads its host
// name from the service and passes it as aiGatewayHost, and the action cases stops when the gateway is not there. They are what judges the waste that Meternaut planted itself, and every one of them ends
// in an error that says so when the app's identity does not yet hold AI Gateway Models User on the gateway (the action aigateway gives it, once this app has its identity).
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "cases" (AGENTS.md rule 18). The code of the function app
// is published by the same action, from src/case-functions. An app cannot move between a Flex Consumption plan and a Basic plan: when casesAppPlan names the other kind than the one that the
// app runs on, the action removes that app, its plan and its private endpoint first, and this template then makes an app of the same name, so that the host
// name, the sign-in's reply address and the links in the letters stay as they were.
targetScope = 'resourceGroup'

@description('Region of every resource.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Name of the storage account of the usage recording. It already exists.')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Name of the Event Hubs namespace of the usage recording. It already exists.')
@minLength(6)
@maxLength(50)
param eventHubNamespaceName string

@description('Name of the function app. It is also its host name, so it is unique worldwide.')
@minLength(2)
@maxLength(60)
param functionAppName string

@description('Which plan the web page and the app run on: Flex (Flex Consumption, scales to zero, billed per execution: the app takes the function subnet snet-func that the model side made, which is delegated to Microsoft.App/environments) or Basic (B1, Linux, always on, about 13 US dollars a month, with the subnet snet-cases below: the way back). tools/environment-params.py sets it from the constant CASES_APP_PLAN. Moving the app between the two needs a new app: the action cases removes the app of the other kind and its plan first.')
@allowed([
  'Flex'
  'Basic'
])
param casesAppPlan string = 'Flex'

@description('Address range of the subnet that the app\'s Basic plan is integrated with, inside the virtual network and apart from the other two subnets, for example 10.53.0.224/27. It is delegated to Microsoft.Web/serverFarms and holds nothing else. Only a Basic app uses it: a Flex app uses snet-func.')
param webSubnetPrefix string

@description('True when the app\'s integration subnet is in Azure already. The template then leaves it alone: a template that makes the subnet again takes away the route table that the landing zone\'s network manager put on it, and the app on it loses its way to the landing zone\'s DNS. The deployment workflow reads this from Azure.')
param webSubnetExists bool = false

@description('The subscriptions that the Watch reads, comma separated. While scopeAllSubscriptions is true it is only the fallback, for a run that cannot get the list of subscriptions that the app\'s identity can read.')
@minLength(36)
param scopeSubscriptions string

@description('True: the Watch reads every subscription that the app\'s own system-assigned identity can read (the list that Azure Resource Manager gives it at the start of each run). A person widens or narrows that list with the read-only roles Reader and Cost Management Reader, at a subscription or at the management group above it, outside this template (AGENTS.md rule 18): this parameter grants nothing, and the one resource group where the console may run a change stays the one below. False: only scopeSubscriptions. The parameter builder (tools/environment-params.py) passes true.')
param scopeAllSubscriptions bool = false

@description('Model of the Detective: an alias of the AI Gateway, which has the name of a model deployment of the Foundry resource of the agents (environment/models.json). The Detective calls it for a chat completion through the AI Gateway, as every model call of Meternaut goes (AGENTS.md rule 15 (c)).')
param modelDetective string = 'gpt-6-luna'

@description('Model of the Skeptic, an alias of the same gateway. It has to be another model than the Detective: the app refuses to start with the same model for both.')
param modelSkeptic string = 'gpt-6.1-sol'

@description('The host name of the AI Gateway, as the service reports it (properties.frontend.defaultHostname, under .ai.gateway.azure.com). The only address that the Detective and the Skeptic call: the deployment workflow reads it from the service, and the action cases stops when the gateway is not there. The app refuses to start without it.')
@minLength(22)
@maxLength(253)
param aiGatewayHost string

@description('Most cases that one run takes up. The app refuses a higher number than 3.')
@minValue(1)
@maxValue(3)
param maxCasesPerRun int = 3

@description('Days that the traces of the workspace are kept: the History lives there.')
@minValue(31)
@maxValue(730)
param historyRetentionDays int = 365

@description('Client id of the console\'s app registration in Microsoft Entra. Empty: the sign-in of the console is not set up yet, and the console refuses every request (it never serves a page without it). It is also the client id of the sign-in to Azure Resource Manager that an approval starts.')
param consoleAppClientId string = ''

@description('The people who may use the console, as JSON: [{"oid": "<directory object id>", "name": "...", "roles": ["owner", "approver", "ops"], "mail": "<address>"}]. The same list is the sign-in\'s list of allowed principals.')
param consolePeople string = '[]'

@description('Directory object ids of the people above: the built-in sign-in lets only these through.')
param consoleUserObjectIds array = []

@description('Whether the console and the function app take requests from the public internet: Enabled or Disabled. Enabled until the platform\'s Application Gateway forwards to the app\'s private endpoint on the console\'s host name (consoleHostName) and the owner has said so, because the people who approve then reach the console through the gateway. The code is published through the private endpoint, from a container group inside the network, whatever this value is. It is always written to the app and never left empty: for an app whose value is not set, a private endpoint switches public access off by itself.')
@allowed([
  'Enabled'
  'Disabled'
])
param casesAppPublicNetworkAccess string = 'Enabled'

@description('Address of the shared mailbox that the app sends its letters from. Empty: the app sends no letter.')
param mailSender string = ''

@description('The host name under which people open the console, for example the name of a listener of the platform\'s Application Gateway that forwards to this app. Empty: they open it on the app\'s own name, <function app name>.azurewebsites.net, and nothing is different from before. With a name, the setting CONSOLE_HOST (the links in the letters and the return address of the Azure sign-in) is that name, and the platform\'s sign-in reads the host of a request from the header X-Original-Host, which the Application Gateway adds, so that its own return address names the console and not the app (docs/proposals/07-private-by-default.md).')
param consoleHostName string = ''

@description('Hours that a plan waits for a person before it expires.')
@minValue(1)
@maxValue(336)
param planTtlHours int = 72

@description('Endpoint of the Microsoft Foundry project whose agents investigate the estate, https://<resource>.services.ai.azure.com/api/projects/<project>. Empty: the investigation is off. The deployment workflow passes it only when the project is in Azure (the action foundry makes it, and gives the app its role there).')
param foundryProjectEndpoint string = ''

@description('Model of the Investigator agent. By default a deployment in the Foundry resource of the agents (environment/foundry/main.bicep deploys the models of environment/models.json). While the switch AGENTS_VIA_AI_GATEWAY in tools/environment-params.py is on, the workflow passes `<connection>/<alias>` instead: the name of the Foundry project\'s connection to the AI Gateway and the gateway\'s alias for the model.')
param foundryModelInvestigator string = 'gpt-6.1-sol'

@description('Model of the Skeptic agent, as for the Investigator: a deployment in the same resource by default, `<connection>/<alias>` while the switch is on. It has to be another model than the Investigator, so that the Skeptic is more independent.')
param foundryModelSkeptic string = 'gpt-6-luna'

@description('Most tool calls and model answers that one investigation may take in all. The code accepts no more than 40 (LIMIT_INVESTIGATE_CALLS in src/case-functions/cases/config.py).')
@minValue(1)
@maxValue(40)
param investigateMaxCalls int = 40

@description('Most seconds that one investigation may take. The code accepts no more than 600 (LIMIT_INVESTIGATE_SECONDS in src/case-functions/cases/config.py).')
@minValue(30)
@maxValue(600)
param investigateMaxSeconds int = 420

var tags = {
  workload: workload
  component: 'cases'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'first-cases'
}

var virtualNetworkName = 'vnet-${workload}'
var webSubnetName = 'snet-cases'
var functionSubnetName = 'snet-func'
var privateEndpointSubnetName = 'snet-pe'
var controlHubName = 'cases-control'
var deploymentContainerName = 'app-package-cases'

// Flex: Flex Consumption, which scales to zero and bills per execution; the app uses snet-func, the subnet that the model side made for it. Basic: the B1 plan on snet-cases.
var isFlex = casesAppPlan == 'Flex'
var integrationSubnetName = isFlex ? functionSubnetName : webSubnetName

// The app takes the three settings of the sign-in to Azure (SIGNIN_TENANT_ID, SIGNIN_CLIENT_ID and OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID) together or not at all, and
// refuses to run the loop with a part of them. Until the console's app registration exists (consoleAppClientId is empty) nobody can sign in and nobody can approve a change,
// so none of the three is set; the first run of the action "cases" that has a client id sets all three.
var signInIsSetUp = !empty(consoleAppClientId)

// The address that people open and that the app writes into its letters and into the return address of the Azure sign-in (the setting CONSOLE_HOST, which the app reads as a host name and builds
// https://<host> from): the console's host name on the platform's Application Gateway when there is one, the app's own name otherwise.
var consoleHost = empty(consoleHostName) ? '${functionAppName}.azurewebsites.net' : consoleHostName

var eventHubsDataReceiverRoleId = 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
var monitoringMetricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' existing = {
  name: virtualNetworkName
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' existing = {
  parent: vnet
  name: privateEndpointSubnetName
}

// No rule of its own, like the other function subnet's: the default rules let the app reach the virtual network and the internet (the landing
// zone's firewall decides there), and nothing is let in. It belongs to the Basic plan's subnet below and is written whatever the plan is, so that
// nothing changes for the way back.
resource webNsg 'Microsoft.Network/networkSecurityGroups@2025-05-01' = {
  name: 'nsg-${workload}-web'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// The same subnet is in environment/main.bicep, so that a later run of the model-side action does not take it away from the plan. Delegated to
// Microsoft.Web/serverFarms, which is what a Basic plan's regional virtual network integration needs (the usage recording's subnet is delegated
// to Microsoft.App/environments, for Flex Consumption, and a subnet has one delegation). It holds nothing else. It is made only while it is not
// there: see webSubnetExists, and the header. A Flex app does not use it, and the template then leaves it as it is: it stays for the way back to Basic.
resource webSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' = if (!isFlex && !webSubnetExists) {
  parent: vnet
  name: webSubnetName
  properties: {
    addressPrefix: webSubnetPrefix
    networkSecurityGroup: {
      id: webNsg.id
    }
    delegations: [
      {
        name: 'app-service-plan'
        properties: {
          serviceName: 'Microsoft.Web/serverFarms'
        }
      }
    ]
    defaultOutboundAccess: false
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: 'log-${workload}'
}

resource insights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: 'appi-${workload}'
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}

resource eventHubs 'Microsoft.EventHub/namespaces@2024-01-01' existing = {
  name: eventHubNamespaceName
}

// The identity that the console's app registration trusts through a federated credential, so that the app presents its token (for api://AzureADTokenExchange)
// as the client assertion instead of a client secret: the built-in sign-in does it to sign a person in, and the console does it to redeem the code of the
// Azure Resource Manager sign-in that an approval starts. It holds no role and is used for nothing else. No identity of this app holds a right to change Azure.
resource authIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workload}-console-auth'
  location: location
  tags: tags
}

// The two containers and the checkpoints that every Functions host of the account shares: host locks, host secrets and the Event Hubs
// checkpoints. They exist already (the usage recording's host made them). The usage recording's package container is not among them, so the
// code of the recording cannot be read or replaced with the identity of this app. This app's own code is not in the account at all: the
// deployment workflow pushes it to the app, which keeps it on the plan's own storage.
var sharedHostContainerNames = [
  'azure-webjobs-hosts'
  'azure-webjobs-secrets'
  'azure-webjobs-eventhub'
]

resource sharedHostContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = [for name in sharedHostContainerNames: {
  parent: blobService
  name: name
}]

// A Flex Consumption app keeps its code package in a container of its own in the shared storage account, as the usage recording's app does in another one, and reads it with its
// system-assigned identity. Only a Flex app has it: a Basic app runs from a package on its plan's own storage. The action cases removes the container, and the role on it, when the
// app goes back to Basic.
resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (isFlex) {
  parent: blobService
  name: deploymentContainerName
  properties: {
    publicAccess: 'None'
  }
}

// The hub for the control events of the check action: one event, sent by the Operator (environment/operator/main.bicep, which holds Azure Event Hubs Data Sender on this hub), starts one run now.
resource controlHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubs
  name: controlHubName
  properties: {
    messageRetentionInDays: 1
    partitionCount: 1
  }
}

resource controlConsumerGroup 'Microsoft.EventHub/namespaces/eventhubs/consumergroups@2024-01-01' = {
  parent: controlHub
  name: 'casesControl'
}

// The History is the app's own telemetry: one line per step in the traces table. A year of it, for a few megabytes, costs cents.
resource tracesRetention 'Microsoft.OperationalInsights/workspaces/tables@2023-09-01' = {
  parent: workspace
  name: 'AppTraces'
  properties: {
    retentionInDays: historyRetentionDays
    totalRetentionInDays: historyRetentionDays
  }
}

// Each role on the one resource that the caller uses, never on the group: the app reads the control hub and cannot send to it. Storage Blob Data Owner on the three
// containers that the Functions hosts of the account share, Storage Queue Data Contributor and Storage Table Data Contributor on the account (the host's documented set
// for an identity-based host storage; the account holds no queue and no table of anybody else's). Monitoring Metrics Publisher: the app's telemetry, with Entra ID
// instead of the instrumentation key. The deployment workflow's identity holds no role on the control hub: the Operator sends the control event (it holds Azure Event Hubs
// Data Sender on this hub, in environment/operator/main.bicep), and the namespace takes no traffic from the workflow's runner. The role that the workflow's identity held here
// is retired by the action cases, which deletes that one assignment after the deploy when it is still there, because a template never removes an assignment that it stops declaring.
//
// The app's roles are for its own system-assigned identity. A role assignment's name has to be known when the deployment starts, and the principal id of a
// system-assigned identity exists only once the app does: so the names are seeded with the app's id (the identity lives and dies with the app, and an app that is
// deleted and made again needs its old assignments removed first), and the principal id is in the properties, which is read later. The roles wait for the app and the
// app does not wait for them, so the first start of an app on a new estate comes before the roles and the host waits for them; on an estate that has the roles already,
// the names are the same and nothing changes.
resource functionReceivesControl 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: controlHub
  name: guid(controlHub.id, functionApp.id, eventHubsDataReceiverRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataReceiverRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionOwnsHostContainers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (name, i) in sharedHostContainerNames: {
  scope: sharedHostContainers[i]
  name: guid(sharedHostContainers[i].id, functionApp.id, storageBlobDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}]

// The Flex app reads and replaces its own code package: Storage Blob Data Owner on its one container, and on no other container of its own.
resource functionOwnsOwnPackage 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (isFlex) {
  scope: deploymentContainer
  name: guid(deploymentContainer.id, functionApp.id, storageBlobDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionUsesQueues 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, functionApp.id, storageQueueDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionUsesTables 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, functionApp.id, storageTableDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionPublishesTelemetry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: insights
  name: guid(insights.id, functionApp.id, monitoringMetricsPublisherRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringMetricsPublisherRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// The plan is of the kind that casesAppPlan says. Flex: Flex Consumption (FC1), which scales to zero and bills for the memory of an instance while it executes and for the executions, after a free
// monthly grant, so that an idle web page costs nothing; it is named plan-<workload>-cases. Basic: B1, Linux, one instance, always on: the console, the timers and the control hub's trigger run on
// it side by side, about 13 US dollars a month at the price list of Sweden Central (0.018 US dollars an hour), whatever it does; it is named plan-<workload>-cases-basic. The two have different names,
// so that the action cases removes the plan of the other kind by its exact name. A plan is in the region of its subnet.
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: isFlex ? 'plan-${workload}-cases' : 'plan-${workload}-cases-basic'
  location: location
  tags: tags
  kind: isFlex ? 'functionapp' : 'linux'
  sku: isFlex ? {
    name: 'FC1'
    tier: 'FlexConsumption'
  } : {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

var eventHubHost = replace(replace(eventHubs.properties.serviceBusEndpoint, 'https://', ''), ':443/', '')

// Only a Basic app is given these: a Flex Consumption app refuses them, and takes its runtime and its package from functionAppConfig instead.
var basicOnlyAppSettings = isFlex ? [] : [
  { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
  { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
  { name: 'WEBSITE_RUN_FROM_PACKAGE', value: '1' }
  // The host's start-up asks the DNS of the landing zone for the names of the storage account and the namespace, and each lookup of a subnet that cannot reach
  // that DNS waits 30 seconds. The platform gives a container 230 seconds by default to answer, and then stops the whole site and starts it again; ten minutes let a slow start finish.
  { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: '600' }
  { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'false' }
  { name: 'ENABLE_ORYX_BUILD', value: 'false' }
]

// No Azure Files content share, no storage connection string, no deployment password. Basic: the workflow pushes the code with its own identity's token to the app's deployment endpoint, which keeps it
// on the plan's own storage and runs the app from that package. Flex: the code is a package in the container app-package-cases, which the app reads with its system-assigned identity, and which the
// Operator replaces with `az functionapp deployment source config-zip` as it does for the usage recording's app. One instance at the most: a run is one function execution that waits for
// models, a timer must not run twice at once, the control hub has one partition and one person uses the web page (the limit is per group of functions: with four, the group of the web page scaled out
// to four instances for one request every four seconds, and every fourth request waited 40 to 46 seconds). No always-ready instance: the app scales to zero and bills nothing while it is idle.
resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${authIdentity.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: casesAppPublicNetworkAccess
    clientAffinityEnabled: false
    virtualNetworkSubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, integrationSubnetName)
    vnetRouteAllEnabled: isFlex ? null : false
    functionAppConfig: isFlex ? {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainerName}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 1
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.13'
      }
    } : null
    siteConfig: {
      linuxFxVersion: isFlex ? null : 'PYTHON|3.13'
      alwaysOn: isFlex ? null : true
      minTlsVersion: '1.2'
      ftpsState: isFlex ? null : 'Disabled'
      appSettings: concat(basicOnlyAppSettings, [
        // No client id in the connections and no AZURE_CLIENT_ID: a connection without one uses the app's system-assigned identity, which is the identity that the roles
        // above are for. The sign-in's identity (below) is the one user-assigned identity that the app has, and it is named by its own setting.
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__blobServiceUri', value: storage.properties.primaryEndpoints.blob }
        { name: 'AzureWebJobsStorage__queueServiceUri', value: storage.properties.primaryEndpoints.queue }
        { name: 'AzureWebJobsStorage__tableServiceUri', value: storage.properties.primaryEndpoints.table }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
        { name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING', value: 'Authorization=AAD' }
        { name: 'EventHubConnection__fullyQualifiedNamespace', value: eventHubHost }
        { name: 'EventHubConnection__credential', value: 'managedidentity' }
        { name: 'EVENTHUB_CASES_CONTROL_NAME', value: controlHubName }
        { name: 'SCOPE_SUBSCRIPTIONS', value: scopeSubscriptions }
        { name: 'SCOPE_ALL_SUBSCRIPTIONS', value: scopeAllSubscriptions ? 'true' : 'false' }
        { name: 'MODEL_DETECTIVE', value: modelDetective }
        { name: 'MODEL_SKEPTIC', value: modelSkeptic }
        // The AI Gateway: the one address of every model call of the Detective and the Skeptic. The app's own identity calls it with a token for https://azure-api.net/aigateway and holds the role
        // AI Gateway Models User on the gateway (environment/aigateway/main.bicep gives it). No key: the gateway accepts only a Microsoft Entra token.
        { name: 'AIGATEWAY_HOST', value: aiGatewayHost }
        { name: 'MAX_CASES_PER_RUN', value: string(maxCasesPerRun) }
        { name: 'STORE_ACCOUNT_NAME', value: storage.name }
        // The one resource group, in the one subscription, in which the console runs a change (it refuses one anywhere else). Azure allows the change only when the
        // approving person's own rights allow it: the app holds no right to change anything.
        { name: 'CHANGE_RESOURCE_GROUP', value: resourceGroup().name }
        { name: 'CHANGE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
        // The sign-in to Azure Resource Manager that an approval starts: this tenant, and the console's app registration (the one of the platform's sign-in). These two and
        // the identity's client id below are set together, or none of the three is (signInIsSetUp).
        { name: 'SIGNIN_TENANT_ID', value: signInIsSetUp ? tenant().tenantId : '' }
        { name: 'SIGNIN_CLIENT_ID', value: consoleAppClientId }
        { name: 'CONSOLE_HOST', value: consoleHost }
        { name: 'CONSOLE_PEOPLE', value: consolePeople }
        { name: 'MAIL_SENDER', value: mailSender }
        { name: 'PLAN_TTL_HOURS', value: string(planTtlHours) }
        // The agents of the Foundry resource (environment/foundry/main.bicep). The app calls the project endpoint with its system-assigned identity and holds no key: the
        // role that lets it create and run agents is given by the template of the Foundry resource, on the project. No endpoint: the investigation is off.
        { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
        { name: 'FOUNDRY_MODEL_INVESTIGATOR', value: foundryModelInvestigator }
        { name: 'FOUNDRY_MODEL_SKEPTIC', value: foundryModelSkeptic }
        { name: 'INVESTIGATE', value: empty(foundryProjectEndpoint) ? 'off' : 'on' }
        { name: 'INVESTIGATE_MAX_CALLS', value: string(investigateMaxCalls) }
        { name: 'INVESTIGATE_MAX_SECONDS', value: string(investigateMaxSeconds) }
        // The client id of the identity whose token is the client assertion: the platform's sign-in reads it, and so does the console when it redeems the code of the
        // Azure Resource Manager sign-in (the app registration's federated credential trusts that identity).
        { name: 'OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID', value: signInIsSetUp ? authIdentity.properties.clientId : '' }
      ])
    }
  }
  dependsOn: [
    webSubnet
    deploymentContainer
    controlConsumerGroup
  ]
}

// No password for the deployment endpoint (basic authentication stays off for the app's deployment site) and none for FTP: the workflow publishes with its own
// identity's token.
resource noBasicAuthForDeployment 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: functionApp
  name: 'scm'
  properties: {
    allow: false
  }
}

// A Flex Consumption app has no FTP endpoint, so only a Basic app has this policy.
resource noBasicAuthForFtp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = if (!isFlex) {
  parent: functionApp
  name: 'ftp'
  properties: {
    allow: false
  }
}

// The built-in sign-in of the console: every request needs a person of the tenant, and only the listed directory object ids get through. The app registration
// trusts the identity above through a federated credential, so the sign-in holds no secret. Without a client id nothing is set up and the console refuses.
resource consoleSignIn 'Microsoft.Web/sites/config@2024-04-01' = if (!empty(consoleAppClientId)) {
  parent: functionApp
  name: 'authsettingsV2'
  properties: {
    platform: {
      enabled: true
      runtimeVersion: '~1'
    }
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
      excludedPaths: [
        '/healthz'
      ]
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
          clientId: consoleAppClientId
          clientSecretSettingName: 'OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID'
        }
        validation: {
          allowedAudiences: [
            'api://${consoleAppClientId}'
            consoleAppClientId
          ]
          defaultAuthorizationPolicy: {
            allowedPrincipals: {
              identities: consoleUserObjectIds
            }
          }
        }
      }
    }
    login: {
      tokenStore: {
        enabled: false
      }
      preserveUrlFragmentsForLogins: false
      cookieExpiration: {
        convention: 'FixedTime'
        timeToExpiration: '08:00:00'
      }
    }
    httpSettings: {
      requireHttps: true
      routes: {
        apiPrefix: '/.auth'
      }
      // The platform's Application Gateway sends a request to this app under the app's own host name (the backend setting picks the host name from the backend address) and adds the host that
      // the visitor used in the header X-Original-Host. The sign-in builds its own return address from the host that it believes the request was made to, and without this setting that is the
      // app's own name, which a closed app does not answer on. Learn: https://learn.microsoft.com/azure/app-service/overview-app-gateway-integration#authentication-easy-auth (the property
      // is httpSettings.forwardProxy, https://learn.microsoft.com/azure/templates/microsoft.web/sites/config-authsettingsv2). Without a console host name the sign-in keeps its default, NoProxy.
      // Nothing else of this resource needs the host: login.allowedExternalRedirectUrls is "typically only needed by Windows Store application backends" and "URLs within the current domain are
      // always implicitly allowed" (the same reference), and no other setting here names a host.
      forwardProxy: empty(consoleHostName) ? {
        convention: 'NoProxy'
      } : {
        convention: 'Custom'
        customHostHeaderName: 'X-Original-Host'
      }
    }
  }
}

// The private endpoint of the app itself, in the endpoint subnet that the model side made and in the same form as the other endpoints of the project (no DNS zone group: the landing
// zone's policy adds it, see the header). One endpoint serves the console's name and the deployment site, `<app>.scm.azurewebsites.net`. It comes after every other write to the app, as an
// endpoint does on every service of the usage recording: the connection is written to the app with an If-Match, and a change of the app at the same time would fail it.
resource functionAppEndpoint 'Microsoft.Network/privateEndpoints@2025-05-01' = {
  name: 'pe-${functionAppName}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'sites'
        properties: {
          privateLinkServiceId: functionApp.id
          groupIds: [
            'sites'
          ]
        }
      }
    ]
  }
  dependsOn: [
    noBasicAuthForDeployment
    noBasicAuthForFtp
    consoleSignIn
  ]
}

// The History: a workbook over the app's telemetry. Anyone who may read the component may open it in the Azure portal.
resource historyWorkbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: guid(resourceGroup().id, 'meternaut-history')
  location: location
  kind: 'shared'
  tags: tags
  properties: {
    displayName: 'Meternaut history'
    category: 'workbook'
    version: '1.0'
    sourceId: insights.id
    serializedData: replace(loadTextContent('history.workbook.json'), '__APPINSIGHTS_ID__', insights.id)
  }
}

output functionAppName string = functionApp.name
output functionAppId string = functionApp.id
@description('Principal id of the function app\'s system-assigned identity. It reads what two roles let it read, Reader and Cost Management Reader, on the pilot subscription or on the tenant root management group: a person gives them (environment/BOOTSTRAP.md). The Foundry resource gives it its role on the project, Foundry User, and the AI Gateway gives it AI Gateway Models User, which it uses for the chat completions of the Detective and the Skeptic. It reads no key and holds no other role.')
output casesSystemPrincipalId string = functionApp.identity.principalId
@description('Principal id of the identity that the console\'s sign-in presents to Microsoft Entra: the federated credential of the app registration names it. It holds no role.')
output authIdentityPrincipalId string = authIdentity.properties.principalId
output authIdentityClientId string = authIdentity.properties.clientId
output consoleUrl string = 'https://${consoleHost}'
output controlHubName string = controlHub.name
output historyWorkbookId string = historyWorkbook.id
