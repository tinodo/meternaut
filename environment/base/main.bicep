// The base that the other parts of Meternaut build on: a Log Analytics workspace and an Application Insights component (where the apps and the agents send their logs), and a storage account
// (the host storage of the cases app, which also holds the cases app's control queue that environment/cases/main.bicep makes, its records and its code), with the private
// endpoints of the storage account. Nothing else: the usage recording that used to live here (a function app, a Cosmos DB account and three event hubs, made for the calls of
// the owner's API Management instance) was removed on 2026-11-07, because nothing fed it any more, and so was the model account that nothing calls (the action retire-old deletes both).
// The Event Hubs namespace that the cases app's control events used to go through is not made here any more: the control message goes through a Storage queue in the storage account, and the
// action retire-event-hubs deletes the namespace and its private endpoint once the queue path has been proved.
//
// The subnets are not made here: environment/main.bicep (the action model-side) makes the virtual network with snet-pe, snet-func, snet-cases, and this template only reads snet-pe.
//
// No key of any kind, and no opt-out of a policy (AGENTS.md rule 23):
//  - the storage account has Shared Key access off, and the Application Insights component and the workspace take no
//    instrumentation key or shared key for ingestion without Entra ID;
//  - storage has public network access off and is reached through private endpoints: the cases app and the Operator (environment/operator/main.bicep, which puts the control message of the check
//    that starts a Watch in the queue) use the queue endpoint;
//  - nothing relies on the tag SecurityControl = Ignore: the tenant's policies change a storage account to exactly this state, so there is nothing for them to change.
//
// Left out on purpose (AGENTS.md rule 19), because the landing zone provides it: private DNS zones, virtual network links and the private endpoints' DNS zone groups (a policy
// registers each endpoint in the central zones about ten minutes after it exists), peering and route tables.
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "base" (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of every resource.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Name of the storage account: 3 to 24 lowercase letters and digits, unique worldwide.')
@minLength(3)
@maxLength(24)
param storageAccountName string

var tags = {
  workload: workload
  component: 'base'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'first-environment'
}

var virtualNetworkName = 'vnet-${workload}'
var privateEndpointSubnetName = 'snet-pe'
var storageServices = [
  'blob'
  'queue'
  'table'
]
var sharedHostContainerNames = [
  'azure-webjobs-hosts'
  'azure-webjobs-secrets'
]

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' existing = {
  name: virtualNetworkName
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' existing = {
  parent: vnet
  name: privateEndpointSubnetName
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

// The containers that every Functions host of the account shares: host locks and host secrets. The host of the usage app used to make them when it first started
// (they exist on an estate that had it); the roles of the cases app name them (environment/cases/main.bicep), so this template makes them, and a new estate has them before the first app starts.
resource sharedHostContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for name in sharedHostContainerNames: {
  parent: blobService
  name: name
  properties: {
    publicAccess: 'None'
  }
}]

// No private DNS zone group in the endpoints below: the landing zone's policy adds it (see the header). One endpoint after the other on the same service: a change of the service
// while its connection list is written made an earlier deploy fail with IfMatchPreconditionFailed.
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
    sharedHostContainers
  ]
}]

output storageAccountName string = storage.name
output appInsightsId string = insights.id
