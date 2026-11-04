// The usage recording of the Citadel gateway, made for this environment: where the numbers of the gateway's calls are
// copied to and kept, as Citadel's observability guide describes it.
//
//   Application Insights of the gateway --(copy jobs, a function app, 8 times a day)--> Cosmos DB
//   gateway --(two Event Hub loggers)--> Event Hubs --(two Event Hub triggers of the same function app)--> Cosmos DB
//
// What it holds: a Log Analytics workspace and an Application Insights component for the function app itself, a storage
// account (its host storage and its code package), an Event Hubs namespace with the hubs, a Cosmos DB account (serverless) with
// the database and containers that the copy jobs write to, a user-assigned identity, a Flex Consumption plan with the function
// app, and the private endpoints and roles that connect them.
//
// No key of any kind, and no opt-out of a policy (AGENTS.md rule 23):
//  - every caller uses an identity (Microsoft Entra ID): the function app its user-assigned identity, the gateway its own
//    identity, the deployment workflow its federated identity;
//  - the storage account has Shared Key access off, the Cosmos DB account has local authentication off, the Event Hubs
//    namespace has local authentication off, the Application Insights component and the workspace take no
//    instrumentation key or shared key for ingestion without Entra ID;
//  - storage and Cosmos DB have public network access off and are reached through private endpoints; the function app
//    reaches them from a subnet of its own (virtual network integration). Event Hubs keeps public access on, because
//    the gateway sends to it and the deployment workflow sends one control event to it; the function app reaches it
//    through a private endpoint, so that public access can be switched off later with one setting;
//  - nothing relies on the tag SecurityControl = Ignore: the tenant's policies change a storage account or a Cosmos DB account
//    to exactly this state, so there is nothing for them to change.
//
// Left out on purpose (AGENTS.md rule 19), because the landing zone provides it: private DNS zones, virtual network links
// and the private endpoints' DNS zone groups (a policy registers each endpoint in the central zones about ten minutes after
// it exists), peering and route tables.
//
// Made after the kit's bicep/infra/apim-gateway-upgrade/supporting-services.bicep and its services/*.bicep, at the commit that
// the workflow checks out, with these differences, each on purpose:
//  - the kit runs the copy jobs as a Logic App Standard. That needs the account key of its storage (an Azure Files share
//    mounted with it, which cannot use an identity) and the connection string of Cosmos DB, so it cannot run on a
//    storage account without Shared Key. The five workflows are rewritten as a Python function app (src/usage-functions)
//    that does the same, with the same documents, with identities only;
//  - the kit's templates assume that the gateway, its Application Insights and its identity are in the same resource group
//    as the stack; here they are in another subscription, so the Application Insights of the gateway is a parameter;
//  - Cosmos DB is serverless: the kit gives each of its seven containers 400 RU/s of its own (2,800 RU/s, about 147 euros a
//    month) for a few hundred small documents a day; serverless costs what is read and written;
//  - the roles are the ones that each caller needs on the one resource it uses: no role on the whole group.
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "recording" (AGENTS.md rule 18). The code of the
// function app is published by the same action, from src/usage-functions.
targetScope = 'resourceGroup'

@description('Region of every resource.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Name of the storage account of the function app: 3 to 24 lowercase letters and digits, unique worldwide.')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Name of the Event Hubs namespace: 6 to 50 letters, digits and hyphens, unique worldwide.')
@minLength(6)
@maxLength(50)
param eventHubNamespaceName string

@description('Name of the Cosmos DB account: 3 to 44 lowercase letters, digits and hyphens, unique worldwide.')
@minLength(3)
@maxLength(44)
param cosmosAccountName string

@description('Name of the function app. It is also its host name, so it is unique worldwide.')
@minLength(2)
@maxLength(60)
param functionAppName string

@description('Principal id of the gateway identity. It may send to the two usage event hubs, and does nothing else here.')
@minLength(36)
@maxLength(36)
param gatewayPrincipalId string

@description('Subscription of the Application Insights component that the gateway writes its token metrics to.')
@minLength(36)
@maxLength(36)
param gatewayAppInsightsSubscriptionId string

@description('Resource group of that component.')
@minLength(1)
param gatewayAppInsightsResourceGroup string

@description('Name of that component.')
@minLength(1)
param gatewayAppInsightsName string

@description('Object id of the identity that the deployment workflow signs in as. It may send to the control hub, so that the workflow can start a copy job once and read the result from the telemetry. It reads nothing.')
@minLength(36)
@maxLength(36)
param workflowPrincipalId string

@description('Principals that may read the usage documents (a Cosmos DB data role). Cosmos DB has no public endpoint, so a reader also needs a network path to the private endpoint.')
param dataReaderPrincipalIds array = []

var tags = {
  workload: workload
  component: 'usage-recording'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'first-environment'
}

var virtualNetworkName = 'vnet-${workload}'
var privateEndpointSubnetName = 'snet-pe'
var functionSubnetName = 'snet-func'
var usageHubName = 'ai-usage'
var piiHubName = 'pii-usage'
var controlHubName = 'usage-control'
var databaseName = 'ai-usage-db'
var deploymentContainerName = 'app-package-usage'
var storageServices = [
  'blob'
  'queue'
  'table'
]

// The containers that the copy jobs read and write, with the partition key that each one is made for.
var containers = [
  { name: 'ai-usage-container', partitionKey: '/productName' }
  { name: 'pii-usage-container', partitionKey: '/type' }
  { name: 'llm-usage-container', partitionKey: '/productName' }
  { name: 'mcp-usage-container', partitionKey: '/productName' }
  { name: 'agent-usage-container', partitionKey: '/productName' }
  { name: 'model-pricing', partitionKey: '/model' }
  { name: 'streaming-export-config', partitionKey: '/type' }
]

// Azure Event Hubs Data Sender: the gateway and the workflow write events and cannot read them. Azure Event Hubs Data
// Receiver: the function app reads events and cannot write them. Storage Blob Data Owner, Storage Queue Data Contributor and
// Storage Table Data Contributor: what the Functions host needs on its host storage and on the container of its code package
// (the documented set for an identity-based host storage). Monitoring Metrics Publisher: the function app's telemetry, with
// Entra ID instead of the instrumentation key. Each on the one resource, never on the group.
var eventHubsDataSenderRoleId = '2b629674-e913-4c01-ae53-ef4638d8f975'
var eventHubsDataReceiverRoleId = 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
var monitoringMetricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'
// The built-in data roles of Cosmos DB are not Azure roles; they live in the account. Data Contributor reads and writes items
// and reads the account's metadata; the function app needs nothing more. Data Reader is for the people in dataReaderPrincipalIds.
var cosmosDataReaderRoleId = '00000000-0000-0000-0000-000000000001'
var cosmosDataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' existing = {
  name: virtualNetworkName
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' existing = {
  parent: vnet
  name: privateEndpointSubnetName
}

resource functionSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' existing = {
  parent: vnet
  name: functionSubnetName
}

resource usageIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workload}-usage'
  location: location
  tags: tags
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${workload}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: json('0.5')
    }
    features: {
      disableLocalAuth: true
    }
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${workload}'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    IngestionMode: 'LogAnalytics'
    DisableLocalAuth: true
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    allowCrossTenantReplication: false
    defaultToOAuthAuthentication: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      bypass: 'None'
      defaultAction: 'Deny'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: deploymentContainerName
  properties: {
    publicAccess: 'None'
  }
}

resource eventHubs 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: eventHubNamespaceName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
    capacity: 1
  }
  properties: {
    disableLocalAuth: true
    isAutoInflateEnabled: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource usageHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubs
  name: usageHubName
  properties: {
    messageRetentionInDays: 7
    partitionCount: 4
  }
}

resource usageConsumerGroup 'Microsoft.EventHub/namespaces/eventhubs/consumergroups@2024-01-01' = {
  parent: usageHub
  name: 'aiUsageIngestion'
}

resource piiHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubs
  name: piiHubName
  properties: {
    messageRetentionInDays: 7
    partitionCount: 2
  }
}

resource piiConsumerGroup 'Microsoft.EventHub/namespaces/eventhubs/consumergroups@2024-01-01' = {
  parent: piiHub
  name: 'piiUsageIngestion'
}

// The hub for the control events of the deployment workflow: one event starts one copy job now.
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
  name: 'usageControl'
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  tags: tags
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    disableLocalAuth: true
    disableKeyBasedMetadataWriteAccess: true
    minimalTlsVersion: 'Tls12'
    publicNetworkAccess: 'Disabled'
    networkAclBypass: 'None'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: cosmos
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// One at a time: the account accepts one change of its containers at once.
@batchSize(1)
resource usageContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = [for container in containers: {
  parent: database
  name: container.name
  properties: {
    resource: {
      id: container.name
      partitionKey: {
        paths: [
          container.partitionKey
        ]
        kind: 'Hash'
      }
    }
  }
}]

// No private DNS zone group in the endpoints below: the landing zone's policy adds it (see the header). One endpoint after
// the other on the same service, and the roles on a service after its endpoints: a change of the service while its connection
// list is written made an earlier deploy fail with IfMatchPreconditionFailed.
@batchSize(1)
resource storageEndpoints 'Microsoft.Network/privateEndpoints@2025-05-01' = [for service in storageServices: {
  name: 'pe-${storageAccountName}-${service}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: service
        properties: {
          privateLinkServiceId: storage.id
          groupIds: [
            service
          ]
        }
      }
    ]
  }
  dependsOn: [
    deploymentContainer
  ]
}]

resource cosmosEndpoint 'Microsoft.Network/privateEndpoints@2025-05-01' = {
  name: 'pe-${cosmosAccountName}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'sql'
        properties: {
          privateLinkServiceId: cosmos.id
          groupIds: [
            'Sql'
          ]
        }
      }
    ]
  }
  dependsOn: [
    usageContainers
  ]
}

resource eventHubsEndpoint 'Microsoft.Network/privateEndpoints@2025-05-01' = {
  name: 'pe-${eventHubNamespaceName}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'namespace'
        properties: {
          privateLinkServiceId: eventHubs.id
          groupIds: [
            'namespace'
          ]
        }
      }
    ]
  }
  dependsOn: [
    usageConsumerGroup
    piiConsumerGroup
    controlConsumerGroup
  ]
}

resource gatewaySends 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: eventHubs
  name: guid(eventHubs.id, gatewayPrincipalId, eventHubsDataSenderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataSenderRoleId)
    principalId: gatewayPrincipalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    eventHubsEndpoint
  ]
}

resource workflowSends 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: eventHubs
  name: guid(eventHubs.id, workflowPrincipalId, eventHubsDataSenderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataSenderRoleId)
    principalId: workflowPrincipalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    eventHubsEndpoint
  ]
}

resource functionReceives 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: eventHubs
  name: guid(eventHubs.id, usageIdentity.id, eventHubsDataReceiverRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataReceiverRoleId)
    principalId: usageIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    eventHubsEndpoint
  ]
}

resource functionOwnsBlobs 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, usageIdentity.id, storageBlobDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: usageIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    storageEndpoints
  ]
}

resource functionUsesQueues 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, usageIdentity.id, storageQueueDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalId: usageIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    storageEndpoints
  ]
}

resource functionUsesTables 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, usageIdentity.id, storageTableDataContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalId: usageIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    storageEndpoints
  ]
}

resource functionPublishesTelemetry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: insights
  name: guid(insights.id, usageIdentity.id, monitoringMetricsPublisherRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringMetricsPublisherRoleId)
    principalId: usageIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionWritesUsage 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, usageIdentity.id, cosmosDataContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosDataContributorRoleId}'
    principalId: usageIdentity.properties.principalId
    scope: cosmos.id
  }
  dependsOn: [
    cosmosEndpoint
  ]
}

resource readersOfTheData 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = [for principalId in dataReaderPrincipalIds: {
  parent: cosmos
  name: guid(cosmos.id, principalId, cosmosDataReaderRoleId)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosDataReaderRoleId}'
    principalId: principalId
    scope: cosmos.id
  }
  dependsOn: [
    functionWritesUsage
  ]
}]

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${workload}-usage'
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

// A Flex Consumption app has no Azure Files content share and no storage connection string: its host storage and its code package
// are reached with the identity (the AzureWebJobsStorage__ settings and deployment.storage.authentication below), and
// it takes no basic-authentication deployment at all. The Event Hub triggers use the identity too (EventHubConnection__).
// The ceiling of 10 instances is for the price: three Event Hub triggers and three timers each scale as a group of their own.
resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${usageIdentity.id}': {}
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
            userAssignedIdentityResourceId: usageIdentity.id
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 10
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
        { name: 'AzureWebJobsStorage__clientId', value: usageIdentity.properties.clientId }
        { name: 'AzureWebJobsStorage__blobServiceUri', value: storage.properties.primaryEndpoints.blob }
        { name: 'AzureWebJobsStorage__queueServiceUri', value: storage.properties.primaryEndpoints.queue }
        { name: 'AzureWebJobsStorage__tableServiceUri', value: storage.properties.primaryEndpoints.table }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
        { name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING', value: 'ClientId=${usageIdentity.properties.clientId};Authorization=AAD' }
        { name: 'AZURE_CLIENT_ID', value: usageIdentity.properties.clientId }
        { name: 'EventHubConnection__fullyQualifiedNamespace', value: eventHubHost }
        { name: 'EventHubConnection__credential', value: 'managedidentity' }
        { name: 'EventHubConnection__clientId', value: usageIdentity.properties.clientId }
        { name: 'EVENTHUB_USAGE_NAME', value: usageHubName }
        { name: 'EVENTHUB_PII_NAME', value: piiHubName }
        { name: 'EVENTHUB_CONTROL_NAME', value: controlHubName }
        { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
        { name: 'COSMOS_DATABASE', value: databaseName }
        { name: 'COSMOS_CONTAINER_CONFIG', value: 'streaming-export-config' }
        { name: 'COSMOS_CONTAINER_AI_USAGE', value: 'ai-usage-container' }
        { name: 'COSMOS_CONTAINER_PII_USAGE', value: 'pii-usage-container' }
        { name: 'COSMOS_CONTAINER_LLM_USAGE', value: 'llm-usage-container' }
        { name: 'COSMOS_CONTAINER_MCP_USAGE', value: 'mcp-usage-container' }
        { name: 'COSMOS_CONTAINER_AGENT_USAGE', value: 'agent-usage-container' }
        { name: 'GATEWAY_APPINSIGHTS_ID', value: resourceId(gatewayAppInsightsSubscriptionId, gatewayAppInsightsResourceGroup, 'Microsoft.Insights/components', gatewayAppInsightsName) }
      ]
    }
  }
  dependsOn: [
    functionReceives
    functionOwnsBlobs
    functionUsesQueues
    functionUsesTables
    functionPublishesTelemetry
    functionWritesUsage
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

output functionAppName string = functionApp.name
output functionAppId string = functionApp.id
@description('Principal id of the function app\'s identity. The copy jobs read the gateway\'s Application Insights with it, which needs two roles in the gateway\'s subscription and in the subscription of its workspace (environment/BOOTSTRAP.md).')
output usageIdentityPrincipalId string = usageIdentity.properties.principalId
output usageIdentityClientId string = usageIdentity.properties.clientId
output eventHubNamespaceName string = eventHubs.name
output eventHubHost string = eventHubHost
output cosmosAccountName string = cosmos.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output appInsightsId string = insights.id
