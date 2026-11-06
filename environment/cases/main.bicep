// The first cases of Meternaut: the function app that finds leads in the pilot estate, lets two model roles work on each one
// through the gateway, and writes every step to a History that a workbook shows (docs/proposals/02-first-cases.md).
//
//   timer (daily) or one control event --> Watch --> Resource Graph, Advisor, Cost Management (read only)
//   Watch --> Detective and Skeptic (the gateway's chat route) --> guards in code --> one telemetry line per step --> workbook
//
// What it holds: two user-assigned identities, a Basic (B1, Linux, always on) plan with the function app (which has a system-assigned identity too) and the subnet
// that the plan is integrated with, one more event hub (the control hub) in the namespace of the usage recording, the roles that connect them, a longer
// retention for the traces table of the workspace, and the History workbook.
//
// Identities, and no right to change Azure. The owner prefers system-assigned identities, so the app moves from `id-meternaut-cases` to its own system-assigned
// identity in two steps (environment/BOOTSTRAP.md). This is the first: the app has the system-assigned identity next to the two user-assigned ones, that identity
// holds every role that `id-meternaut-cases` holds in this template, and the settings still name `id-meternaut-cases`, so nothing that the app does changes. The
// second step moves the settings to the system-assigned identity and takes `id-meternaut-cases` off the app, after the roles outside this group have been given to
// the new identity; a person removes the identity itself later, after `tools/access-requirements.py retire` has taken away its grants. `id-meternaut-cases` reads the
// pilot estate, its cost lines and the gateway's access key, stores the records, and holds the roles below that are for
// the app. `id-meternaut-console-auth` stays a user-assigned identity (Microsoft documents the secretless sign-in of an App Service app only with that kind:
// https://learn.microsoft.com/azure/app-service/configure-authentication-provider-aad#use-a-managed-identity-instead-of-a-secret) and holds no role: the
// console's app registration trusts it through a federated credential, so that the platform's sign-in, and the console when it redeems the code of an Azure
// Resource Manager sign-in, present its token as the client assertion instead of a client secret. Nothing here gives Meternaut a right to write in Azure. When a
// person approves a plan, the console sends that person to Microsoft Entra to sign in to Azure Resource Manager (authorization code flow with PKCE, the delegated
// scope https://management.azure.com/user_impersonation, no refresh token) and runs the one change with that person's token: Azure checks that person's own
// rights, and its Activity Log names that person (docs/proposals/04-the-loop.md, docs/proposals/05-run-as-the-approver.md).
//
// Why not Flex Consumption, which the first cases ran on: its front end held some requests to the console for 15 to 60 seconds and
// answered some with "The service is unavailable" (CHANGELOG.md). A Basic plan has no such front end, no cold start, and runs the
// timers, the control hub's trigger and the console on one instance for about 13 US dollars a month.
//
// It makes no storage account, no namespace and no private endpoint: the app shares the storage account (blob, queue and table private
// endpoints) and the Event Hubs namespace (private endpoint) of environment/recording/main.bicep, so nothing new is billed except the
// plan and tokens. The only network it makes is the app's own integration subnet (the usage recording's subnet is delegated to Flex
// Consumption and cannot serve a Basic plan) and that subnet's network security group. The recording has to exist first.
//
// The subnet is made once and then left alone (webSubnetExists): the landing zone's network manager puts a route table on a new subnet
// about a minute after it is made, and a template that makes the subnet again takes that table away, and with it the subnet's way to
// the landing zone's DNS. The app on it then cannot resolve a name, and cannot start. That happened to the first subnet (snet-web) on
// 2026-11-05, in the second deploy of this template, and the subnet was replaced by this one (snet-cases).
//
// No key of any kind (AGENTS.md rule 23): the app's host storage, its Event Hubs trigger and its telemetry use its identity, and its
// code is pushed with the deployment workflow's own identity token (no deployment password). The only key it ever touches is the
// gateway access product's, which the Watch reads from the gateway at the start of a run with its identity (the call needs a role in the
// gateway's subscription that the template cannot give) and keeps in memory.
//
// The cases identity can read nothing of the pilot estate yet: its Reader and Cost Management Reader roles on the pilot subscription, and the
// role that reads the access product's key, are given once, outside this template, on the owner's written word (environment/BOOTSTRAP.md,
// AGENTS.md rule 18), because the deployment workflow's identity has no right there and must not get one.
//
// The agents: when the Foundry resource of the agents exists (environment/foundry/main.bicep, the action foundry), the workflow passes the address of its
// project, and the app then lets agents of that project investigate the estate (the settings FOUNDRY_* and INVESTIGATE*). The app signs in to the project with
// its own identity, and the template of the Foundry resource gives that identity its role on the project. Without the address the investigation is off.
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "cases" (AGENTS.md rule 18). The code of the function app
// is published by the same action, from src/case-functions. A Basic plan cannot take over a Flex Consumption app: the action removes
// the Flex app and its plan first, when they are still there, and this template then makes an app of the same name, so that the host
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

@description('Address range of the subnet that the app\'s Basic plan is integrated with, inside the virtual network and apart from the other two subnets, for example 10.53.0.224/27. It is delegated to Microsoft.Web/serverFarms and holds nothing else.')
param webSubnetPrefix string

@description('True when the app\'s integration subnet is in Azure already. The template then leaves it alone: a template that makes the subnet again takes away the route table that the landing zone\'s network manager put on it, and the app on it loses its way to the landing zone\'s DNS. The deployment workflow reads this from Azure.')
param webSubnetExists bool = false

@description('Object id of the identity that the deployment workflow signs in as. It may send to the control hub, so that the workflow can start one run and read the History. It reads nothing else.')
@minLength(36)
@maxLength(36)
param workflowPrincipalId string

@description('The subscriptions that the Watch reads, comma separated.')
@minLength(36)
param scopeSubscriptions string

@description('Address of the gateway, https://<name>.azure-api.net.')
@minLength(1)
param gatewayUrl string

@description('Resource id of the gateway access product\'s subscription, whose key the Watch reads at the start of a run.')
@minLength(1)
param gatewayProductSubscriptionId string

@description('Model deployment of the Detective.')
param modelDetective string = 'gpt-6-luna'

@description('Model deployment of the Skeptic. It has to be another model than the Detective: the app refuses to start with the same model for both.')
param modelSkeptic string = 'gpt-6.1-sol'

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

@description('Address of the shared mailbox that the app sends its letters from. Empty: the app sends no letter.')
param mailSender string = ''

@description('Hours that a plan waits for a person before it expires.')
@minValue(1)
@maxValue(336)
param planTtlHours int = 72

@description('Endpoint of the Microsoft Foundry project whose agents investigate the estate, https://<resource>.services.ai.azure.com/api/projects/<project>. Empty: the investigation is off. The deployment workflow passes it only when the project is in Azure (the action foundry makes it, and gives the app its role there).')
param foundryProjectEndpoint string = ''

@description('Model deployment of the Investigator agent, in the Foundry resource of the agents (environment/foundry/main.bicep deploys the models of environment/models.json).')
param foundryModelInvestigator string = 'gpt-6.1-sol'

@description('Model deployment of the Skeptic agent, in the same resource. It has to be another model than the Investigator, so that the Skeptic is more independent.')
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
var controlHubName = 'cases-control'

// The app takes the three settings of the sign-in to Azure (SIGNIN_TENANT_ID, SIGNIN_CLIENT_ID and OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID) together or not at all, and
// refuses to run the loop with a part of them. Until the console's app registration exists (consoleAppClientId is empty) nobody can sign in and nobody can approve a change,
// so none of the three is set; the first run of the action "cases" that has a client id sets all three.
var signInIsSetUp = !empty(consoleAppClientId)

var eventHubsDataSenderRoleId = '2b629674-e913-4c01-ae53-ef4638d8f975'
var eventHubsDataReceiverRoleId = 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
var monitoringMetricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' existing = {
  name: virtualNetworkName
}

// No rule of its own, like the other function subnet's: the default rules let the app reach the virtual network and the internet (the landing
// zone's firewall decides there), and nothing is let in.
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
// there: see webSubnetExists, and the header.
resource webSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' = if (!webSubnetExists) {
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

resource casesIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workload}-cases'
  location: location
  tags: tags
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

// The hub for the control events of the deployment workflow: one event starts one run now.
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

// Each role on the one resource that the caller uses, never on the group: the workflow sends to the control hub and cannot read it;
// the app reads it and cannot send. Storage Blob Data Owner on the three containers that the Functions hosts of the account share,
// Storage Queue Data Contributor and Storage Table Data Contributor on the account (the host's documented set for an identity-based host
// storage; the account holds no queue and no table of anybody else's). Monitoring Metrics Publisher: the app's telemetry, with Entra ID
// instead of the instrumentation key.
resource workflowSendsControl 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: controlHub
  name: guid(controlHub.id, workflowPrincipalId, eventHubsDataSenderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataSenderRoleId)
    principalId: workflowPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource functionReceivesControl 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: controlHub
  name: guid(controlHub.id, casesIdentity.id, eventHubsDataReceiverRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataReceiverRoleId)
    principalId: casesIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionOwnsHostContainers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (name, i) in sharedHostContainerNames: {
  scope: sharedHostContainers[i]
  name: guid(sharedHostContainers[i].id, casesIdentity.id, storageBlobDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: casesIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource functionUsesQueues 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, casesIdentity.id, storageQueueDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalId: casesIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionUsesTables 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, casesIdentity.id, storageTableDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalId: casesIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionPublishesTelemetry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: insights
  name: guid(insights.id, casesIdentity.id, monitoringMetricsPublisherRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringMetricsPublisherRoleId)
    principalId: casesIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// A Basic plan, Linux, one instance, always on: the console, the timers and the control hub's trigger run on it side by side. About 13 US dollars a month at the
// price list of Sweden Central (0.018 US dollars an hour), whatever it does. It takes the integration subnet above; a plan is in the region of its subnet.
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${workload}-cases-basic'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

var eventHubHost = replace(replace(eventHubs.properties.serviceBusEndpoint, 'https://', ''), ':443/', '')

// No Azure Files content share, no storage connection string, no deployment password (the workflow pushes the code with its own identity's token to the app's
// deployment endpoint, which keeps it on the plan's own storage and runs the app from that package).
resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${casesIdentity.id}': {}
      '${authIdentity.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    clientAffinityEnabled: false
    virtualNetworkSubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, webSubnetName)
    vnetRouteAllEnabled: false
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.13'
      alwaysOn: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'WEBSITE_RUN_FROM_PACKAGE', value: '1' }
        // The host's start-up asks the DNS of the landing zone for the names of the storage account, the namespace and the gateway, and each lookup of a subnet that cannot reach
        // that DNS waits 30 seconds. The platform gives a container 230 seconds by default to answer, and then stops the whole site and starts it again; ten minutes let a slow start finish.
        { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: '600' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'false' }
        { name: 'ENABLE_ORYX_BUILD', value: 'false' }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__clientId', value: casesIdentity.properties.clientId }
        { name: 'AzureWebJobsStorage__blobServiceUri', value: storage.properties.primaryEndpoints.blob }
        { name: 'AzureWebJobsStorage__queueServiceUri', value: storage.properties.primaryEndpoints.queue }
        { name: 'AzureWebJobsStorage__tableServiceUri', value: storage.properties.primaryEndpoints.table }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
        { name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING', value: 'ClientId=${casesIdentity.properties.clientId};Authorization=AAD' }
        { name: 'AZURE_CLIENT_ID', value: casesIdentity.properties.clientId }
        { name: 'EventHubConnection__fullyQualifiedNamespace', value: eventHubHost }
        { name: 'EventHubConnection__credential', value: 'managedidentity' }
        { name: 'EventHubConnection__clientId', value: casesIdentity.properties.clientId }
        { name: 'EVENTHUB_CASES_CONTROL_NAME', value: controlHubName }
        { name: 'SCOPE_SUBSCRIPTIONS', value: scopeSubscriptions }
        { name: 'GATEWAY_URL', value: gatewayUrl }
        { name: 'GATEWAY_PRODUCT_SUBSCRIPTION_ID', value: gatewayProductSubscriptionId }
        { name: 'MODEL_DETECTIVE', value: modelDetective }
        { name: 'MODEL_SKEPTIC', value: modelSkeptic }
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
        { name: 'CONSOLE_HOST', value: '${functionAppName}.azurewebsites.net' }
        { name: 'CONSOLE_PEOPLE', value: consolePeople }
        { name: 'MAIL_SENDER', value: mailSender }
        { name: 'PLAN_TTL_HOURS', value: string(planTtlHours) }
        // The agents of the Foundry resource (environment/foundry/main.bicep). The app calls the project endpoint with its identity (id-meternaut-cases) and holds no key: the
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
      ]
    }
  }
  dependsOn: [
    webSubnet
    functionReceivesControl
    functionOwnsHostContainers
    functionUsesQueues
    functionUsesTables
    functionPublishesTelemetry
    controlConsumerGroup
  ]
}

// Step one of the move to a system-assigned identity: every role above, for the app's own identity as well. The settings still name `id-meternaut-cases`, so these roles
// are used only after the second step. A role assignment's name has to be known when the deployment starts, and the principal id of a system-assigned identity exists only
// once the app does: so the names are seeded with the app's id (the identity lives and dies with the app) and the principal id is in the properties, which is read later.
// They depend on the app, and the app does not depend on them: the app starts before its own identity has these roles, which is why its settings keep the identity that already has them.
resource systemReceivesControl 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: controlHub
  name: guid(controlHub.id, functionApp.id, eventHubsDataReceiverRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataReceiverRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource systemOwnsHostContainers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (name, i) in sharedHostContainerNames: {
  scope: sharedHostContainers[i]
  name: guid(sharedHostContainers[i].id, functionApp.id, storageBlobDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource systemUsesQueues 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, functionApp.id, storageQueueDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource systemUsesTables 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, functionApp.id, storageTableDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource systemPublishesTelemetry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: insights
  name: guid(insights.id, functionApp.id, monitoringMetricsPublisherRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringMetricsPublisherRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
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

resource noBasicAuthForFtp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
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
    }
  }
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
@description('Principal id of the function app\'s identity that reads and stores (id-meternaut-cases). It reads the pilot estate with two roles on the pilot subscription, and the gateway access product\'s key with a role in the gateway\'s subscription: both are given once, on the owner\'s written word (environment/BOOTSTRAP.md).')
output casesIdentityPrincipalId string = casesIdentity.properties.principalId
output casesIdentityClientId string = casesIdentity.properties.clientId
@description('Principal id of the function app\'s system-assigned identity, which takes over from id-meternaut-cases: the same roles inside this group (this template) and the same roles outside it (a person gives them once, with tools/access-requirements.py: environment/BOOTSTRAP.md). The Foundry resource gives it its role on the project.')
output casesSystemPrincipalId string = functionApp.identity.principalId
@description('Principal id of the identity that the console\'s sign-in presents to Microsoft Entra: the federated credential of the app registration names it. It holds no role.')
output authIdentityPrincipalId string = authIdentity.properties.principalId
output authIdentityClientId string = authIdentity.properties.clientId
output consoleUrl string = 'https://${functionApp.properties.defaultHostName}'
output controlHubName string = controlHub.name
output historyWorkbookId string = historyWorkbook.id
