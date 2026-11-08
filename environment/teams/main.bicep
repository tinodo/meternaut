// The Teams bot of Meternaut: the small function app that Teams calls with a card's answer, the Azure Bot resource that points Teams at it, and the identity that is the bot
// (docs/proposals/13-teams-and-outlook.md). Behind a switch, and the one public endpoint of the project: it is deployed only by the action `teams` of the workflow
// .github/workflows/deploy-hub.yml, which stops at its first step unless the input public_teams_bot_requested is set, which only the owner's written request for a public endpoint allows
// (AGENTS.md rule 15 (c)). Nothing here is deployed by any other action, and the switch TEAMS_BOT_ENABLED (a repository variable, False until the owner says so) is read by the workflow too.
//
//   Teams --(signed JWT, POST /api/messages)--> bot app (public)  --(private endpoint, system-assigned identity)--> the loop's tables
//   bot app --(token of the bot's own identity)--> Bot Connector --> Teams                              (the card, proactively, and the answer to a tap)
//
// What it makes: one user-assigned identity (the bot: its client id is the app id of the bot and the id in the Teams app's manifest), the Azure Bot resource (type UserAssignedMSI, the free
// tier F0, local authentication off) with its Teams channel, a Flex Consumption plan and the function app on it (its own system-assigned identity, no key of any kind), the container of its
// code package and the roles on the shared storage account. It makes no storage account, no subnet and no private endpoint: the app shares the storage account of the base and the function
// subnet snet-func of the model side (several Flex apps may share one subnet: Learn, "Flex Consumption plan", read 2026-11-08), which this template reads and never makes or changes (AGENTS.md
// rule 27: a subnet is made once and then left alone).
//
// Why a separate app, and a public one. The platform's sign-in (Easy Auth) of the cases app refuses every anonymous request, and Teams cannot sign in, so the messaging endpoint cannot live there.
// Microsoft publishes no service tag or address range for the Bot Connector of Teams (Learn, "Authentication with the Bot Connector API", and the Bot Framework documentation, read 2026-11-08), so
// the endpoint cannot be closed to it by address: it is open to the internet and refuses everything but a request with a valid token of the Connector (cases/botauth.py). The separate app keeps
// that public surface to two functions: the messaging endpoint (the route api/messages) and the timer that offers the cards. The cases app, with the web page and the right to read the estate, can
// stay private. The bot app's code is the package `cases` with its own entry (src/case-functions/teams_function_app.py): none of the cases app's routes, timers or rights is in it.
//
// Identities. The system-assigned identity of the app reads and writes the loop's tables (Storage Table Data Contributor on the account, as the cases app) and holds the host's own roles on the
// shared storage account; it holds no right to read the estate and none to change it. The user-assigned identity holds no role at all: its token is for one audience, https://api.botframework.com,
// and Learn says that a bot of this type asks the platform's identity endpoint for it with the identity's own client id ("Authentication with the Bot Connector API", read 2026-11-08). The app does
// not set AZURE_CLIENT_ID: that would make the tables' token the bot's. There is no client secret, no certificate, no federated credential and no app registration: the app type UserAssignedMSI
// needs none of them, which is why tools/entra-setup.py has nothing to add for the bot.
//
// Teams channel. Teams Toolkit's own template makes the channel with only its name; the template does the same, and the terms of the channel are accepted where the Azure Bot resource is shown
// in the portal or the Teams admin center, by a person.
targetScope = 'resourceGroup'

@description('Region of every resource except the Azure Bot resource, which is global.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Name of the storage account of the base. It already exists, and the app shares it: its host storage, its code package and the loop\'s tables are in it.')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Name of the function app of the bot. It is also its host name, so it is unique worldwide.')
@minLength(2)
@maxLength(60)
param botAppName string

@description('Name of the Azure Bot resource, its handle: unique worldwide, letters, digits, dots, underscores and hyphens.')
@minLength(2)
@maxLength(64)
param botName string

@description('The host name that people open the web page at, which the cards link to (the setting CONSOLE_HOST): the console\'s host name on the platform\'s gateway, or the cases app\'s own name.')
@minLength(4)
@maxLength(253)
param consoleHost string

@description('The people (CONSOLE_PEOPLE): the JSON list of directory object ids, names, roles and addresses. The bot answers only a person on it. The workflow passes the same text as the cases app\'s.')
@minLength(2)
param consolePeople string

@description('How long a request waits for an answer, in hours (PLAN_TTL_HOURS): the same as the cases app\'s.')
@minValue(1)
@maxValue(336)
param planTtlHours int = 72

@description('The most instances of the app. The bot is small and a handful of people use it: two is room for a restart without a gap, and a ceiling on what a flood of calls could cost.')
@minValue(1)
@maxValue(10)
param maximumInstanceCount int = 2

@description('The memory of one instance, in MB: Flex Consumption bills the memory of an instance while it runs. The bot does a few table calls and one signature check for a call, so the smallest size is enough.')
@allowed([
  512
  2048
  4096
])
param instanceMemoryMB int = 512

@description('Always-ready instances for the HTTP trigger. 0 (the default): the app scales to zero and bills nothing while it is idle, and the first tap after an idle time waits for a cold start, which Teams may show as a failed tap (the answer is not recorded twice: its token is one-time). 1: one instance is kept warm and billed all month: docs/proposals/13-teams-and-outlook.md has the price.')
@minValue(0)
@maxValue(2)
param alwaysReadyInstances int = 0

var tags = {
  workload: workload
  component: 'teams'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'teams-bot'
}

var virtualNetworkName = 'vnet-${workload}'
// The function subnet that the model side made and delegated to Microsoft.App/environments, which the cases app uses too. Read here and never made or changed.
var functionSubnetName = 'snet-func'
var deploymentContainerName = 'app-package-teams'

var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
var monitoringMetricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

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

// The bot. Its client id is the app id of the Azure Bot resource, the audience of every token that Teams sends, and the botId of the Teams app's manifest. It holds no role and no credential.
resource botIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workload}-teams-bot'
  location: location
  tags: tags
}

// The two containers that every Functions host of the account shares (the base makes them), and this app's own package container.
var sharedHostContainerNames = [
  'azure-webjobs-hosts'
  'azure-webjobs-secrets'
]

resource sharedHostContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = [for name in sharedHostContainerNames: {
  parent: blobService
  name: name
}]

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: deploymentContainerName
  properties: {
    publicAccess: 'None'
  }
}

// Flex Consumption (FC1): scales to zero and bills the memory of an instance while it executes, and the executions, after a free monthly grant, so that an idle bot costs nothing.
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${workload}-teams'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

// The one public endpoint of the project. No key, no connection string, no deployment password: the host storage and the code package are read with the app's system-assigned identity, the
// telemetry uses Entra ID, and the workflow publishes the code with its own identity's token. It runs in the function subnet, outbound, so that the tables are reached through their private endpoints.
// The inbound side is open by necessity (see the header) and the app answers on one route.
resource botApp 'Microsoft.Web/sites@2024-04-01' = {
  name: botAppName
  location: location
  kind: 'functionapp,linux'
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${botIdentity.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    clientAffinityEnabled: false
    virtualNetworkSubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, functionSubnetName)
    functionAppConfig: {
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
        maximumInstanceCount: maximumInstanceCount
        instanceMemoryMB: instanceMemoryMB
        alwaysReady: alwaysReadyInstances > 0 ? [
          {
            name: 'http'
            instanceCount: alwaysReadyInstances
          }
        ] : []
        triggers: {
          http: {
            perInstanceConcurrency: 16
          }
        }
      }
      runtime: {
        name: 'python'
        version: '3.13'
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      appSettings: [
        // No client id in the host's connections and no AZURE_CLIENT_ID: a connection without one uses the app's system-assigned identity, which the roles below are for. The bot's own identity is
        // named by TEAMS_BOT_APP_ID and used for the token of the Bot Connector alone (cases/teams.py).
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__blobServiceUri', value: storage.properties.primaryEndpoints.blob }
        { name: 'AzureWebJobsStorage__queueServiceUri', value: storage.properties.primaryEndpoints.queue }
        { name: 'AzureWebJobsStorage__tableServiceUri', value: storage.properties.primaryEndpoints.table }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
        { name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING', value: 'Authorization=AAD' }
        // The loop's records, which the bot reads and writes with the system-assigned identity: the plans, the decisions, the one-time tokens, the switches, the people's settings and its own table.
        { name: 'STORE_ACCOUNT_NAME', value: storage.name }
        { name: 'CHANGE_RESOURCE_GROUP', value: resourceGroup().name }
        { name: 'CHANGE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
        { name: 'CONSOLE_HOST', value: consoleHost }
        { name: 'CONSOLE_PEOPLE', value: consolePeople }
        { name: 'PLAN_TTL_HOURS', value: string(planTtlHours) }
        // The bot: its app id, which is the client id of its identity and the audience of the tokens that Teams sends, and the tenant that every activity has to come from.
        { name: 'TEAMS_BOT_APP_ID', value: botIdentity.properties.clientId }
        { name: 'TEAMS_TENANT_ID', value: tenant().tenantId }
      ]
    }
  }
  dependsOn: [
    deploymentContainer
  ]
}

// No password for the deployment endpoint: the workflow publishes with its own identity's token. A Flex app has no FTP endpoint.
resource noBasicAuthForDeployment 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: botApp
  name: 'scm'
  properties: {
    allow: false
  }
}

// Each role on the one resource that the caller uses, never on the group, for the app's system-assigned identity (the names are seeded with the app's id: the principal id exists only once the
// app does, and the roles wait for the app). Storage Blob Data Owner on the two shared host containers and on this app's own package container, Storage Queue Data Contributor and Storage Table
// Data Contributor on the account (the host's documented set for an identity-based host storage, and the tables of the loop), and Monitoring Metrics Publisher for the telemetry.
resource botOwnsHostContainers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (name, i) in sharedHostContainerNames: {
  scope: sharedHostContainers[i]
  name: guid(sharedHostContainers[i].id, botApp.id, storageBlobDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: botApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource botOwnsOwnPackage 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: deploymentContainer
  name: guid(deploymentContainer.id, botApp.id, storageBlobDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: botApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource botUsesQueues 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, botApp.id, storageQueueDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalId: botApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource botUsesTables 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, botApp.id, storageTableDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalId: botApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource botPublishesTelemetry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: insights
  name: guid(insights.id, botApp.id, monitoringMetricsPublisherRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringMetricsPublisherRoleId)
    principalId: botApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// The Azure Bot resource: the registration that tells Teams where the bot is. The app type UserAssignedMSI names the bot's identity (client id, resource id and tenant), so that no secret and no
// app registration is needed. The free tier covers standard channels such as Teams; local authentication is off, so that the resource takes no key. The endpoint is the one route of the app.
resource bot 'Microsoft.BotService/botServices@2022-09-15' = {
  name: botName
  location: 'global'
  kind: 'azurebot'
  tags: tags
  sku: {
    name: 'F0'
  }
  properties: {
    displayName: 'Meternaut (AI)'
    description: 'An AI that finds Azure resources that cost money and are not used, and asks a person to decide. Written by an AI.'
    endpoint: 'https://${botApp.properties.defaultHostName}/api/messages'
    msaAppId: botIdentity.properties.clientId
    msaAppType: 'UserAssignedMSI'
    msaAppMSIResourceId: botIdentity.id
    msaAppTenantId: tenant().tenantId
    disableLocalAuth: true
    isStreamingSupported: false
    publicNetworkAccess: 'Enabled'
    schemaTransformationVersion: '1.3'
  }
}

resource teamsChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = {
  parent: bot
  name: 'MsTeamsChannel'
  location: 'global'
  properties: {
    channelName: 'MsTeamsChannel'
  }
}

output botAppName string = botApp.name
output botAppId string = botApp.id
@description('The address that Teams is told to call.')
output messagingEndpoint string = 'https://${botApp.properties.defaultHostName}/api/messages'
@description('The client id of the bot\'s identity: the app id of the bot, the botId of the Teams app\'s manifest (tools/teams-package.py --bot-id) and the setting TEAMS_BOT_APP_ID.')
output botClientId string = botIdentity.properties.clientId
output botIdentityPrincipalId string = botIdentity.properties.principalId
@description('Principal id of the app\'s system-assigned identity: it reads and writes the loop\'s tables and holds the host\'s roles on the shared storage account, and nothing else.')
output botSystemPrincipalId string = botApp.identity.principalId
output botName string = bot.name
