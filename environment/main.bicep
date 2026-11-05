// The model side of the first environment: a small network (a subnet for private endpoints and a subnet that the usage
// recording's function app is integrated with), one Foundry account with the first models, reachable only through a
// private endpoint, and a budget. The gateway (the owner's existing API Management instance) is configured by the
// workflow separately (environment/gateway).
//
// Left out on purpose (AGENTS.md rule 19), because the landing zone provides it:
//  - private DNS zones, virtual network links and the private endpoint's DNS zone group: a policy registers the
//    endpoint in the central zones about ten minutes after it exists;
//  - peering and route tables: the network manager joins a new virtual network to the hub and routes it;
//  - an API Management instance: the owner's existing one is used.
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

@description('Address space of the virtual network, for example 10.53.0.0/24.')
param vnetAddressPrefix string

@description('Address range of the private endpoint subnet, inside the virtual network, for example 10.53.0.0/27.')
param peSubnetPrefix string

@description('Address range of the subnet that the function app of the usage recording is integrated with, inside the virtual network and apart from the private endpoint subnet, for example 10.53.0.32/27. A Flex Consumption app needs a /27 at least, for itself alone.')
param funcSubnetPrefix string

@description('Address range of the subnet that the Basic plan of the first cases is integrated with, inside the virtual network and apart from the other two subnets, for example 10.53.0.224/27. It is delegated to Microsoft.Web/serverFarms. environment/cases/main.bicep makes the same subnet (snet-cases); it is listed here too, so that this template, run again, does not take it away from the plan.')
param webSubnetPrefix string

@description('DNS servers of the landing zone. A virtual network on Azure-provided DNS cannot resolve the central private zones.')
@minLength(1)
param dnsServers array

@description('Restore the soft-deleted account of this name instead of creating a new one. The workflow sets it only after the platform reports that such an account exists.')
param restoreAccount bool = false

@description('The models deployed in the account: name, version, deployment type and capacity in thousands of tokens a minute. The workflow reads them from environment/models.json, which the gateway configuration reads too, so the two cannot differ.')
param models array

@description('Principal id of the user-assigned identity that the gateway uses to call the models. Nobody else is granted access.')
@minLength(36)
@maxLength(36)
param gatewayPrincipalId string

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
  component: 'model-side'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'first-environment'
}

// Cognitive Services OpenAI User: the one role that lets a caller run chat completions and nothing else. The gateway needs no
// other role for this account; the content-safety and language calls (Cognitive Services User) wait until a contract turns
// them on and a call has shown that they need it.
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource nsg 'Microsoft.Network/networkSecurityGroups@2025-05-01' = {
  name: 'nsg-${workload}-pe'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// No rule of its own: the default rules let the function app reach the virtual network and the internet (the landing zone's
// firewall decides there), and nothing is let in.
resource funcNsg 'Microsoft.Network/networkSecurityGroups@2025-05-01' = {
  name: 'nsg-${workload}-func'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// The same as the function subnet's: no rule of its own. The subnet of the first cases' Basic plan.
resource webNsg 'Microsoft.Network/networkSecurityGroups@2025-05-01' = {
  name: 'nsg-${workload}-web'
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
      {
        // Delegated to Flex Consumption (not to Microsoft.Web/serverFarms, which is for Premium and Dedicated plans). The
        // subnet holds nothing else: it cannot hold a private endpoint.
        name: 'snet-func'
        properties: {
          addressPrefix: funcSubnetPrefix
          networkSecurityGroup: {
            id: funcNsg.id
          }
          delegations: [
            {
              name: 'flex-consumption'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
          defaultOutboundAccess: false
        }
      }
      {
        // The subnet of the first cases' Basic plan: delegated to Microsoft.Web/serverFarms (a subnet has one delegation, and the one above is
        // Flex Consumption's). environment/cases/main.bicep makes it too. It holds nothing else.
        name: 'snet-cases'
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

// One at a time: the account accepts one deployment write at once.
@batchSize(1)
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [for model in models: {
  parent: account
  name: model.name
  sku: {
    name: model.sku
    capacity: model.capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: model.name
      version: model.version
    }
    versionUpgradeOption: 'NoAutoUpgrade'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}]

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

// After the private endpoint, not beside it: the endpoint's connection is written to the account with an If-Match, and a
// role assignment made on the account at the same moment changed it first (IfMatchPreconditionFailed, seen in an earlier
// deploy).
resource gatewayMayCallTheModels 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account
  name: guid(account.id, gatewayPrincipalId, openAiUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: gatewayPrincipalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    privateEndpoint
  ]
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
