// The model behind the hub: one Foundry account with one model, reachable only through a private endpoint.
//
// Left out on purpose (AGENTS.md rule 19), because the landing zone provides it:
//  - private DNS zones, virtual network links and the private endpoint's DNS zone group: a policy
//    registers the endpoint in the central zones about ten minutes after it exists;
//  - peering and route tables: the network manager connects a new virtual network to the hub
//    network and routes it;
//  - an API Management instance: the owner's existing one is used (tools/apim-sync.py).
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of every resource.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Name of the Foundry account. It is also the host name, so it is unique worldwide: 2 to 64 characters, letters, digits and hyphens.')
@minLength(2)
@maxLength(64)
param accountName string

@description('Address space of the virtual network, for example 10.52.0.0/27.')
param vnetAddressPrefix string

@description('Address range of the private endpoint subnet, inside the virtual network, for example 10.52.0.0/28.')
param peSubnetPrefix string

@description('DNS servers of the landing zone. A virtual network on Azure-provided DNS cannot resolve the central private zones.')
@minLength(1)
param dnsServers array

@description('Restore the soft-deleted account of this name instead of creating a new one. The deployment workflow sets it only after the platform reports that such an account exists.')
param restoreAccount bool = false

@description('Model deployed in the account.')
param modelName string = 'gpt-6-luna'

@description('Version of the model.')
param modelVersion string = '2026-09-22'

@description('Deployment type of the model.')
@allowed([
  'DataZoneStandard'
  'GlobalStandard'
])
param modelSku string = 'DataZoneStandard'

@description('Capacity of the deployment, in thousands of tokens a minute.')
@minValue(1)
param modelCapacity int = 50

@description('Principal id of the system-assigned identity of the API Management instance. That identity calls the model; nobody else is granted access.')
@minLength(36)
@maxLength(36)
param apimPrincipalId string

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Monthly budget of the resource group, in the billing currency of the subscription.')
@minValue(1)
param budgetAmount int

@description('Addresses that receive the budget alerts.')
@minLength(1)
param alertEmails array

@description('First day of the month in which the budget was first made, as YYYY-MM-01. A budget keeps its start date, so the workflow reads it from the existing budget and passes it on again; only a new budget starts in the current month.')
@minLength(10)
@maxLength(10)
param budgetStartDate string

var tags = {
  workload: workload
  component: 'hub-backend'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'foundations'
}

// Cognitive Services OpenAI User: the one role that lets a caller run chat completions and nothing else.
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource nsg 'Microsoft.Network/networkSecurityGroups@2025-05-01' = {
  name: 'nsg-${workload}-pe'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' = {
  name: 'vnet-${workload}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    dhcpOptions: {
      dnsServers: dnsServers
    }
    subnets: [
      {
        name: 'snet-pe'
        properties: {
          addressPrefix: peSubnetPrefix
          networkSecurityGroup: {
            id: nsg.id
          }
          privateEndpointNetworkPolicies: 'Disabled'
          defaultOutboundAccess: false
        }
      }
    ]
  }
}

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
    restore: restoreAccount
    networkAcls: {
      defaultAction: 'Deny'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: modelName
  sku: {
    name: modelSku
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    versionUpgradeOption: 'NoAutoUpgrade'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

// No privateDnsZoneGroups child: the landing zone's policy adds it (see the header).
resource privateEndpoint 'Microsoft.Network/privateEndpoints@2025-05-01' = {
  name: 'pe-${accountName}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: vnet.properties.subnets[0].id
    }
    privateLinkServiceConnections: [
      {
        name: 'account'
        properties: {
          privateLinkServiceId: account.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
  dependsOn: [
    modelDeployment
  ]
}

resource apimMayCallTheModel 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account
  name: guid(account.id, apimPrincipalId, openAiUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: apimPrincipalId
    principalType: 'ServicePrincipal'
  }
}

module budget '../infra/budgets/rg-budget.bicep' = {
  name: 'budget'
  params: {
    budgetName: '${workload}-hub'
    amount: budgetAmount
    contactEmails: alertEmails
    startDate: budgetStartDate
  }
}

@description('Base address of the model endpoint (the cognitiveservices.azure.com host that the landing zone registers privately).')
output endpoint string = account.properties.endpoint

output accountName string = account.name
output privateEndpointName string = privateEndpoint.name
