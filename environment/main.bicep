// The network of Meternaut and its budget: a small virtual network with a subnet for private endpoints (snet-pe), a subnet for a Flex Consumption function app (snet-func), a subnet
// for the cases app (snet-cases), and the budget of the resource group. The action that deploys it is still called model-side: that is its old name, from the time when it also made
// a model account. That account (aif-meternaut-<digest>, with its private endpoint) was removed on 2026-11-07, because since the owner's order of that day every model call goes direct to the
// models of the agents' own Foundry resource (environment/foundry) and nothing called it; the action retire-old deletes it. The models themselves are listed in environment/models.json,
// which the Foundry resource and the AI Gateway read.
//
// Left out on purpose (AGENTS.md rule 19), because the landing zone provides it:
//  - private DNS zones, virtual network links and the private endpoints' DNS zone groups: a policy registers each
//    endpoint in the central zones about ten minutes after it exists;
//  - peering and route tables: the network manager joins a new virtual network to the hub and routes it;
//  - an API Management instance: Meternaut makes none and touches none.
//
// The virtual network is made once (networkExists), and then left alone: the landing zone's network manager puts a route table on each
// subnet of it, and a virtual network that is made again, with its subnets listed here, loses those tables, and with them the subnets'
// way to the landing zone's DNS (AGENTS.md rule 27: it happened to the first cases' subnet on 2026-11-05).
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of every resource.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Address space of the virtual network, for example 10.53.0.0/24.')
param vnetAddressPrefix string

@description('True when the virtual network is in Azure already. The template then leaves it alone: a virtual network that is made again loses the route tables that the landing zone\'s network manager put on its subnets, and an app on such a subnet cannot resolve a name. The deployment workflow reads this from Azure.')
param networkExists bool = false

@description('Address range of the private endpoint subnet, inside the virtual network, for example 10.53.0.0/27.')
param peSubnetPrefix string

@description('Address range of the subnet that a Flex Consumption function app is integrated with, inside the virtual network and apart from the private endpoint subnet, for example 10.53.0.32/27. A Flex Consumption app needs a /27 at least, for itself alone. The subnet is delegated to Flex Consumption and holds nothing else.')
param funcSubnetPrefix string

@description('Address range of the subnet that the Basic plan of the first cases is integrated with, inside the virtual network and apart from the other two subnets, for example 10.53.0.224/27. It is delegated to Microsoft.Web/serverFarms. environment/cases/main.bicep makes the same subnet (snet-cases); it is listed here too, so that this template, run again, does not take it away from the plan.')
param webSubnetPrefix string

@description('DNS servers of the landing zone. A virtual network on Azure-provided DNS cannot resolve the central private zones.')
@minLength(1)
param dnsServers array

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
  component: 'network'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'first-environment'
}

resource nsg 'Microsoft.Network/networkSecurityGroups@2025-05-01' = {
  name: 'nsg-${workload}-pe'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// No rule of its own: the default rules let the function app reach the virtual network and the internet (the landing zone's
// firewall decides there), and nothing is let in. The subnet of a Flex Consumption function app (the cases app moves to one).
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

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' = if (!networkExists) {
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
        // subnet holds nothing else: it cannot hold a private endpoint. The usage app that used it was removed on 2026-11-07; the cases app reuses it.
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

module budget '../infra/budgets/rg-budget.bicep' = {
  name: 'budget'
  params: {
    budgetName: '${workload}-hub'
    amount: budgetAmount
    contactEmails: alertEmails
    startDate: budgetStartDate
  }
}

output virtualNetworkName string = 'vnet-${workload}'
output budgetName string = '${workload}-hub'
