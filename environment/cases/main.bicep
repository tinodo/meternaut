// The first cases of Meternaut: the function app that finds leads in the pilot estate, lets two model roles work on each one
// through the gateway, and writes every step to a History that a workbook shows (docs/proposals/02-first-cases.md).
//
//   timer (daily) or one control event --> Watch --> Resource Graph, Advisor, Cost Management (read only)
//   Watch --> Detective and Skeptic (the gateway's chat route) --> guards in code --> one telemetry line per step --> workbook
//
// What it holds: a user-assigned identity, a Flex Consumption plan with the function app, a package container in the storage
// account of the usage recording, one more event hub (the control hub) in the namespace of the usage recording, the roles that
// connect them, a longer retention for the traces table of the workspace, and the History workbook.
//
// It makes no storage account, no namespace, no private endpoint and no network: the app shares the integration subnet, the storage
// account (blob, queue and table private endpoints) and the Event Hubs namespace (private endpoint) of environment/recording/main.bicep,
// so nothing new is billed except tokens. The recording has to exist first.
//
// No key of any kind (AGENTS.md rule 23): the app's host storage, its package, its Event Hubs trigger and its telemetry use its
// identity. The only key it ever touches is the gateway access product's, which the Watch reads from the gateway at the start of
// a run with its identity (the call needs a role in the gateway's subscription that the template cannot give) and keeps in memory.
//
// The identity can read nothing of the pilot estate yet: its Reader and Cost Management Reader roles on the pilot subscription, and the
// role that reads the access product's key, are given once, outside this template, on the owner's written word (environment/BOOTSTRAP.md,
// AGENTS.md rule 18), because the deployment workflow's identity has no right there and must not get one.
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "cases" (AGENTS.md rule 18). The code of the function app
// is published by the same action, from src/case-functions.
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

@description('Model deployment of the Skeptic.')
param modelSkeptic string = 'gpt-6-luna'

@description('Most cases that one run takes up.')
@minValue(1)
@maxValue(10)
param maxCasesPerRun int = 3

@description('Days that the traces of the workspace are kept: the History lives there.')
@minValue(31)
@maxValue(730)
param historyRetentionDays int = 365

var tags = {
  workload: workload
  component: 'cases'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'first-cases'
}

var virtualNetworkName = 'vnet-${workload}'
var functionSubnetName = 'snet-func'
var controlHubName = 'cases-control'
var deploymentContainerName = 'app-package-cases'

var eventHubsDataSenderRoleId = '2b629674-e913-4c01-ae53-ef4638d8f975'
var eventHubsDataReceiverRoleId = 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
var monitoringMetricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' existing = {
  name: virtualNetworkName
}

resource functionSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' existing = {
  parent: vnet
  name: functionSubnetName
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

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: deploymentContainerName
  properties: {
    publicAccess: 'None'
  }
}

// The three containers that every Functions host of the account shares: host locks, host secrets and the Event Hubs checkpoints. They
// exist already (the usage recording's host made them). The usage recording's package container is not among them, so the code of the
// recording cannot be read or replaced with the identity of this app.
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
// the app reads it and cannot send. Storage Blob Data Owner on four containers only (its own package container and the three that the
// Functions hosts of the account share), Storage Queue Data Contributor and Storage Table Data Contributor on the account (the host's
// documented set for an identity-based host storage; the account holds no queue and no table of anybody else's). Monitoring Metrics
// Publisher: the app's telemetry, with Entra ID instead of the instrumentation key.
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

resource functionOwnsOwnPackage 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: deploymentContainer
  name: guid(deploymentContainer.id, casesIdentity.id, storageBlobDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
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

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${workload}-cases'
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

var eventHubHost = replace(replace(eventHubs.properties.serviceBusEndpoint, 'https://', ''), ':443/', '')

// Like the usage recording's app: no Azure Files content share, no storage connection string, no basic-authentication deployment.
// The ceiling of 4 instances is for the price: a run is one function execution that waits for models, and two runs at once are
// harmless but never needed.
resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${casesIdentity.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    clientAffinityEnabled: false
    virtualNetworkSubnetId: functionSubnet.id
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainerName}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: casesIdentity.id
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 4
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.13'
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      appSettings: [
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
      ]
    }
  }
  dependsOn: [
    functionReceivesControl
    functionOwnsOwnPackage
    functionOwnsHostContainers
    functionUsesQueues
    functionUsesTables
    functionPublishesTelemetry
    deploymentContainer
    controlConsumerGroup
  ]
}

// No password for the deployment endpoint either: the workflow publishes with its own identity's token.
resource noBasicAuthForDeployment 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: functionApp
  name: 'scm'
  properties: {
    allow: false
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
@description('Principal id of the function app\'s identity. It reads the pilot estate with two roles on the pilot subscription, and the gateway access product\'s key with a role in the gateway\'s subscription: both are given once, on the owner\'s written word (environment/BOOTSTRAP.md).')
output casesIdentityPrincipalId string = casesIdentity.properties.principalId
output casesIdentityClientId string = casesIdentity.properties.clientId
output controlHubName string = controlHub.name
output historyWorkbookId string = historyWorkbook.id
