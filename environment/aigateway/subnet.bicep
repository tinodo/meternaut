// The subnet of the AI Gateway and its network security group: the first of the two templates of the action aigateway. The gateway itself is environment/aigateway/main.bicep, which reads
// this subnet by its name and needs it to be there when it is deployed (docs/proposals/08-ai-gateway.md).
//
// Why a template of its own. The landing zone's network manager puts one managed route table on every subnet some 70 seconds to five minutes after the subnet is made (CHANGELOG.md, 2026-11-05).
// The service takes the gateway's backend subnet when the gateway is made and treats it as read-only afterwards, and a gateway whose creation fails may keep the subnet for a long time. A small virtual
// network has little room for another range, so the first creation of the gateway has to happen on the subnet as the landing zone leaves it, and not while the network manager is still writing to
// the subnet. In one template the wait for the route table could only come after the gateway. So the workflow deploys this template, waits until the route table is on the subnet, signs in again
// and only then deploys the gateway.
//
// The subnet is made once and then left alone: it is made only while it is not there (aigwSubnetExists), because a template that makes a subnet again takes away what the landing zone added to it
// (AGENTS.md rule 27). The workflow reads from Azure whether the subnet is there, passes it, and deploys this template only when it is not.
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "aigateway" (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of every resource. The subnet has to be in the gateway\'s region.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Address range of the subnet that the gateway reaches its backends through, inside the virtual network and apart from the other subnets, for example 10.53.0.128/26. At least a /27, in the gateway\'s region and subscription. It is delegated to Microsoft.App/environments and belongs to the gateway alone. The service takes the subnet when the gateway is made, and treats it as read-only afterwards.')
@minLength(9)
@maxLength(18)
param aigwSubnetPrefix string

@description('True when the gateway\'s subnet is in Azure already. The template then leaves it alone: a template that makes the subnet again takes away the route table that the landing zone\'s network manager put on it. The deployment workflow reads this from Azure.')
param aigwSubnetExists bool = false

var tags = {
  workload: workload
  component: 'ai-gateway'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'ai-gateway'
}

var virtualNetworkName = 'vnet-${workload}'
var aigwSubnetName = 'snet-aigw'

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' existing = {
  name: virtualNetworkName
}

// No rule of its own, like the other subnets': the default rules let the gateway reach the virtual network and the internet (the landing zone's firewall decides
// there), and nothing is let in. The portal's in-product text (https://ai.gateway.azure.com, read 2026-11-07) says that no rules are required. Microsoft's lab 18 (Azure/aigateway, labs/18-private-networking)
// adds two allow rules (outbound 443 to Storage and to AzureKeyVault) and no deny rule, so next to the default rules, which allow outbound traffic, they change nothing, and none is made here.
resource aigwNsg 'Microsoft.Network/networkSecurityGroups@2025-05-01' = {
  name: 'nsg-${workload}-aigw'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// Delegated to Microsoft.App/environments, as the function app's subnet is, and it holds nothing else. Made only while it is not there: see aigwSubnetExists, and the header.
resource aigwSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' = if (!aigwSubnetExists) {
  parent: vnet
  name: aigwSubnetName
  properties: {
    addressPrefix: aigwSubnetPrefix
    networkSecurityGroup: {
      id: aigwNsg.id
    }
    delegations: [
      {
        name: 'ai-gateway'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
    defaultOutboundAccess: false
  }
}

output subnetName string = aigwSubnetName
