// The usage recording of the Citadel gateway, made for this environment: where the numbers of the gateway's calls are
// copied to and kept, as Citadel's observability guide describes it.
//
//   Application Insights of the gateway --(copy job, Logic App Standard, 8 times a day)--> Cosmos DB  ---> Power BI
//   gateway --(two Event Hub loggers)--> Event Hubs --(two more workflows of the same Logic App)--> Cosmos DB
//
// What it holds: a Log Analytics workspace and an Application Insights component for the Logic App itself, a storage
// account (the Logic App's state and content share), an Event Hubs namespace with the two hubs, a Cosmos DB account (serverless)
// with the database and containers that the Logic App's workflows expect, the Logic App on a Workflow Standard plan, and
// the Azure Monitor Logs connection that its copy job reads Application Insights through.
//
// Made after the kit's bicep/infra/apim-gateway-upgrade/supporting-services.bicep and its services/*.bicep, at the commit that
// the workflow checks out, with these differences, each on purpose:
//  - the kit's templates assume that the gateway, its Application Insights and its identity are in the same resource group
//    as the stack; here they are in another subscription, so the Application Insights of the gateway is a parameter;
//  - Cosmos DB is serverless: the kit gives each of its seven containers 400 RU/s of its own (2,800 RU/s, about 147 euros a
//    month) for a few hundred small documents a day; serverless costs what is read and written;
//  - Event Hubs has local authentication off and no auto-inflate (a ceiling on the price): the gateway and the Logic App
//    use their identities;
//  - the roles are the ones that each caller needs on the one resource it uses: no role on the whole group, no second
//    identity that nothing uses;
//  - the Logic App can run on one instance only (a ceiling on the price), and its pre-warmed instance is off: it runs eight
//    times a day.
//
// Public endpoints on every service, and two resources that the tenant's governance would otherwise change: see the tag
// SecurityControl below. The owner's subscription has a policy waiver for public network access (Deny effect), and the Logic
// App is published from a GitHub-hosted runner (no private connectivity to it). Private endpoints are a later switch that each
// cost a few euros a month (docs/proposals/01-first-environment.md).
//
// The tag SecurityControl = Ignore is on two resources, the storage account and the Cosmos DB account, and on nothing else. The
// tenant's governance (the initiative GovInitiative, assigned at the tenant root) does not deny them: it changes
// them while they are made, to Shared Key off and public network access off for a storage account, and to local
// authentication off and public network access off for a Cosmos DB account. The first deployment showed it: the account came out
// with Shared Key off, and the Logic App's settings were refused ("Key based authentication is not permitted on this storage
// account"). The policies' own opt-out is that tag, on the resource or on its group (each policy rule says so), and the
// kit's design needs the opposite on both: a Logic App Standard mounts its content share (Azure Files) with the account key,
// and the kit's workflows reach Cosmos DB with its connection string, both over a public endpoint. This is a known, chosen
// deviation from the security controls, for the one stack whose engine cannot run without it; the way out of it is in
// docs/proposals/01-first-environment.md.
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "recording" (AGENTS.md rule 18). The Logic App's
// workflows are published by the same action, from the kit's src/usage-ingestion-logicapp, unchanged.
targetScope = 'resourceGroup'

@description('Region of every resource.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Name of the storage account of the Logic App: 3 to 24 lowercase letters and digits, unique worldwide.')
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

@description('Name of the Logic App. It is also its host name, so it is unique worldwide.')
@minLength(2)
@maxLength(60)
param logicAppName string

@description('Principal id of the gateway identity. It may send to the two event hubs, and does nothing else here.')
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

@description('Principals that may read the usage documents (a Cosmos DB data role): the identity of the workflow, which checks the copy job, and the owner.')
param dataReaderPrincipalIds array = []

var tags = {
  workload: workload
  component: 'usage-recording'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'first-environment'
}

// The opt-out that the tenant's own policies name (see the header): only on the storage account and the Cosmos DB account.
var optOut = {
  SecurityControl: 'Ignore'
}

var usageHubName = 'ai-usage'
var piiHubName = 'pii-usage'
var databaseName = 'ai-usage-db'
var contentShareName = 'usage-logic-content'

// The containers that the Logic App's five workflows read and write, with the partition key that each one is made for.
var containers = [
  { name: 'ai-usage-container', partitionKey: '/productName' }
  { name: 'pii-usage-container', partitionKey: '/type' }
  { name: 'llm-usage-container', partitionKey: '/productName' }
  { name: 'mcp-usage-container', partitionKey: '/productName' }
  { name: 'agent-usage-container', partitionKey: '/productName' }
  { name: 'model-pricing', partitionKey: '/model' }
  { name: 'streaming-export-config', partitionKey: '/type' }
]

// Azure Event Hubs Data Sender: the gateway writes events and cannot read them. Azure Event Hubs Data Receiver: the Logic App
// reads events and cannot write them. Each on the namespace, not on the group.
var eventHubsDataSenderRoleId = '2b629674-e913-4c01-ae53-ef4638d8f975'
var eventHubsDataReceiverRoleId = 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
// The built-in Data Reader role of Cosmos DB. It is not an Azure role; it lives in the account. The Logic App needs no data
// role: it reaches the account with its connection string.
var cosmosDataReaderRoleId = '00000000-0000-0000-0000-000000000001'

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
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: union(tags, optOut)
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    // A Logic App Standard keeps its state and its content share with the account's key; it has no other way to mount the share.
    allowSharedKeyAccess: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

resource files 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource contentShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: files
  name: contentShareName
  properties: {
    shareQuota: 5
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

resource gatewaySends 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: eventHubs
  name: guid(eventHubs.id, gatewayPrincipalId, eventHubsDataSenderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataSenderRoleId)
    principalId: gatewayPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  tags: union(tags, optOut)
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
    // The kit's workflows reach the account with its connection string, so local authentication stays on (see the header).
    disableLocalAuth: false
    disableKeyBasedMetadataWriteAccess: true
    minimalTlsVersion: 'Tls12'
    publicNetworkAccess: 'Enabled'
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

// The types of this resource are incomplete: the kit's own template for it is plain JSON with the same two properties
// (kind V2, and a parameter value set that says the connection authenticates with the Logic App's identity).
resource monitorConnection 'Microsoft.Web/connections@2016-06-01' = {
  name: 'azuremonitorlogs'
  location: location
  tags: tags
  #disable-next-line BCP187
  kind: 'V2'
  properties: {
    displayName: 'conn-azure-monitor'
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azuremonitorlogs')
    }
    #disable-next-line BCP089
    parameterValueSet: {
      name: 'managedIdentityAuth'
      values: {}
    }
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'asp-${workload}-usage'
  location: location
  tags: tags
  kind: 'elastic'
  sku: {
    name: 'WS1'
    tier: 'WorkflowStandard'
    family: 'WS'
    size: 'WS1'
    capacity: 1
  }
  properties: {
    maximumElasticWorkerCount: 1
    reserved: false
  }
}

var storageConnection = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
var eventHubHost = replace(replace(eventHubs.properties.serviceBusEndpoint, 'https://', ''), ':443/', '')

resource logicApp 'Microsoft.Web/sites@2024-04-01' = {
  name: logicAppName
  location: location
  kind: 'functionapp,workflowapp'
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    clientAffinityEnabled: false
    siteConfig: {
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      scmMinTlsVersion: '1.2'
      minimumElasticInstanceCount: 1
      preWarmedInstanceCount: 0
      functionsRuntimeScaleMonitoringEnabled: true
      netFrameworkVersion: 'v6.0'
      cors: {
        allowedOrigins: [
          'https://portal.azure.com'
          'https://ms.portal.azure.com'
        ]
        supportCredentials: false
      }
    }
  }
  dependsOn: [
    contentShare
  ]
}

// Neither the publishing credentials of the site's deployment endpoint nor those of FTP: the workflow publishes with its own
// identity's token.
resource noBasicAuthForDeployment 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: logicApp
  name: 'scm'
  properties: {
    allow: false
  }
}

resource noBasicAuthForFtp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: logicApp
  name: 'ftp'
  properties: {
    allow: false
  }
}

resource appSettings 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: logicApp
  name: 'appsettings'
  properties: {
    APPLICATIONINSIGHTS_CONNECTION_STRING: insights.properties.ConnectionString
    AzureWebJobsStorage: storageConnection
    FUNCTIONS_EXTENSION_VERSION: '~4'
    FUNCTIONS_WORKER_RUNTIME: 'node'
    WEBSITE_NODE_DEFAULT_VERSION: '~20'
    WEBSITE_CONTENTAZUREFILECONNECTIONSTRING: storageConnection
    WEBSITE_CONTENTSHARE: contentShareName
    APP_KIND: 'workflowapp'
    AzureFunctionsJobHost_extensionBundle: 'Microsoft.Azure.Functions.ExtensionBundle.Workflows'
    eventHub_fullyQualifiedNamespace: eventHubHost
    eventHub_name: usageHubName
    eventHub_pii_name: piiHubName
    CosmosDBAccount: cosmos.name
    CosmosDBDatabase: databaseName
    CosmosDBContainerConfig: 'streaming-export-config'
    CosmosDBContainerUsage: 'ai-usage-container'
    CosmosDBContainerPII: 'pii-usage-container'
    CosmosDBContainerLLMUsage: 'llm-usage-container'
    CosmosDBContainerMCPUsage: 'mcp-usage-container'
    CosmosDBContainerAgentUsage: 'agent-usage-container'
    AzureCosmosDB_connectionString: cosmos.listConnectionStrings().connectionStrings[0].connectionString
    AppInsights_SubscriptionId: gatewayAppInsightsSubscriptionId
    AppInsights_ResourceGroup: gatewayAppInsightsResourceGroup
    AppInsights_Name: gatewayAppInsightsName
    AzureMonitor_Resource_Id: monitorConnection.id
    AzureMonitor_Api_Id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azuremonitorlogs')
    #disable-next-line use-resource-symbol-reference
    AzureMonitor_ConnectRuntime_Url: reference(monitorConnection.id, '2016-06-01', 'Full').properties.connectionRuntimeUrl
  }
  dependsOn: [
    usageContainers
  ]
}

#disable-next-line BCP081
resource monitorAccess 'Microsoft.Web/connections/accessPolicies@2016-06-01' = {
  parent: monitorConnection
  name: 'azuremonitorlogs-access'
  location: location
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        tenantId: tenant().tenantId
        objectId: logicApp.identity.principalId
      }
    }
  }
}

resource logicAppReceives 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: eventHubs
  name: guid(eventHubs.id, logicApp.id, eventHubsDataReceiverRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataReceiverRoleId)
    principalId: logicApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource readersOfTheData 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = [for principalId in dataReaderPrincipalIds: {
  parent: cosmos
  name: guid(cosmos.id, principalId, cosmosDataReaderRoleId)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosDataReaderRoleId}'
    principalId: principalId
    scope: cosmos.id
  }
}]

output logicAppName string = logicApp.name
output logicAppId string = logicApp.id
@description('Principal id of the Logic App. The copy job reads the gateway\'s Application Insights with it, which needs one role in the gateway\'s subscription (environment/BOOTSTRAP.md).')
output logicAppPrincipalId string = logicApp.identity.principalId
output eventHubNamespaceName string = eventHubs.name
output eventHubHost string = eventHubHost
output cosmosAccountName string = cosmos.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
