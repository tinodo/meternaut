// Virtual network support for Power Platform: the subnet that the connectors of one Power Platform environment run in, and the enterprise policy that names it
// (docs/proposals/19-teams-cards-through-power-automate.md). The cases app puts each Teams card as one message in the Storage queue `teams-cards`; a Power Automate flow in an environment that is
// linked to this policy reads the queue through the queue's private endpoint, from this subnet, and posts the card as the Flow bot. No bot, no app registration, no public endpoint and no key.
// The mechanism is the one of the owner's own reference repository tinodo/secure-request-classifier (MIT: infra/modules/virtual-network.bicep, network-security-group.bicep and
// power-platform-enterprise-policy.bicep), adapted to the landing zone's rules.
//
// What it makes, and nothing else:
//  - the subnet snet-powerplatform in the project's virtual network, delegated to Microsoft.PowerPlatform/enterprisePolicies (the subnet holds nothing else and cannot be shared by two policies), with a
//    network security group of its own that has no rule of its own, like the other subnets' (the default rules let the containers reach the virtual network and the internet, and the landing zone's firewall decides there;
//    the reference's two explicit allow rules for outbound 443 repeat those defaults);
//  - the enterprise policy ep-<workload>-netinjection: kind NetworkInjection, location `sweden`, one virtual network and this subnet.
//
// The two places where a Power Platform name is not an Azure name. (1) The policy's location is the Power Platform geography `sweden`, not an Azure region: Learn's template lists the geographies
// (https://learn.microsoft.com/power-platform/admin/vnet-support-setup-configure, read 2026-11-11). (2) The geography Sweden has one Azure region, swedencentral (the same page lists "Sweden: swedencentral"
// under Supported regions in https://learn.microsoft.com/power-platform/admin/vnet-support-overview), so there is one virtual network and no failover pair, and `location` allows nothing else. The environment
// that is linked must be in the geography Sweden, which tools/powerplatform.py checks before it links.
//
// The API version. Learn's template reference and its manual template name 2020-10-30-preview, and so does the reference repository; the resource provider also lists 2020-10-30 (read from the pilot
// subscription on 2026-11-11), which Microsoft's own PowerShell module (microsoft/PowerPlatform-EnterprisePolicies) writes. The word preview is in the version only: the feature is generally available (Learn, the table of
// supported services). One word changes it, and no property of this template differs between the two.
//
// The subnet is made once and then left alone (powerPlatformSubnetExists), exactly like snet-aigw in environment/aigateway/subnet.bicep (AGENTS.md rule 27): the landing zone's network manager puts a route
// table on a new subnet some minutes after it is made, and a template that makes the subnet again takes the table away. The workflow reads from Azure whether the subnet is there, passes it, and, after the deploy,
// waits until the table is on the subnet, before anybody links an environment (linking can make the subnet unstable for up to 30 minutes: Learn).
//
// The policy is made once too (enterprisePolicyExists), for another reason: Power Platform refuses every write to a policy that an environment is linked to (EnterprisePolicyUpdateNotAllowed), so a second deploy
// of a policy that exists would fail even when nothing in it changed. To change the policy, unlink the environment (tools/powerplatform.py unlink), delete the policy, and deploy again.
//
// The range cannot be changed once the subnet is delegated and an environment is linked, nor can the DNS servers of the virtual network (environment/main.bicep sets the landing zone's): Learn says that the
// environment stops working, and that changing either takes an unlink, the change, a wait of 30 minutes and a link, and for the range a request to Microsoft support. The builder (tools/environment-params.py) takes the
// last free /27 of the virtual network and does not invent a range: a /28 is the least (6 to 10 addresses for an environment that is not production, plus the five that Azure keeps), a /26 is what a production
// environment needs (25 to 30 addresses). Power Platform names no address of its own to open: a connector in the subnet reaches the queue's private endpoint inside the network.
//
// Left out on purpose (AGENTS.md rule 19), because the landing zone provides it: private DNS zones, links, zone groups (a policy registers the queue endpoint's name in the central zone), peering and route tables.
// No role assignment: the Power Platform administrator needs Reader on the policy to link it, which a person gives (the deploy identity may give roles to service principals only), and the person
// whose connection reads the queue needs a data role on the queue (docs/proposals/19-teams-cards-through-power-automate.md has the commands).
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of the subnet and of the virtual network. Sweden Central is the one Azure region of the Power Platform geography Sweden, so nothing else is allowed.')
@allowed([
  'swedencentral'
])
param location string = 'swedencentral'

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Address range of the subnet that Power Platform runs its connectors in, inside the virtual network and apart from the other subnets, for example 10.53.0.96/27. It is delegated to Microsoft.PowerPlatform/enterprisePolicies and holds nothing else. A /28 is the least for an environment that is not production; the range cannot be changed once an environment is linked.')
@minLength(9)
@maxLength(18)
param powerPlatformSubnetPrefix string

@description('True when the subnet is in Azure already. The template then leaves it alone: a template that makes the subnet again takes away the route table that the landing zone\'s network manager put on it. The deployment workflow reads this from Azure.')
param powerPlatformSubnetExists bool = false

@description('True when the enterprise policy is in Azure already. The template then does not write it: Power Platform refuses every write to a policy that an environment is linked to. The deployment workflow reads this from Azure.')
param enterprisePolicyExists bool = false

var tags = {
  workload: workload
  component: 'powerplatform'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'teams-cards'
}

var virtualNetworkName = 'vnet-${workload}'
var powerPlatformSubnetName = 'snet-powerplatform'
var enterprisePolicyName = 'ep-${workload}-netinjection'
// The Power Platform geography that has swedencentral as its region (Learn: Sweden, swedencentral). It is the policy's location, which is not an Azure region.
var enterprisePolicyGeography = 'sweden'

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' existing = {
  name: virtualNetworkName
}

// No rule of its own, like the other subnets': the default rules let the containers reach the virtual network and the internet (the landing zone's firewall decides there), and nothing is let in.
// A tenant policy refuses a subnet that has no group (Deny-Subnet-Without-Nsg in an Azure landing zone), so the subnet below always has this one. The group is written every time, as the others are.
resource powerPlatformNsg 'Microsoft.Network/networkSecurityGroups@2025-05-01' = {
  name: 'nsg-${workload}-powerplatform'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// Delegated to the enterprise policy, which is what lets Power Platform put its containers into the subnet. The delegation's name is the service's, as the reference names it. Made only while it is not there:
// see powerPlatformSubnetExists, and the header. No default outbound access, like every other subnet of the project: what leaves the subnet goes the way the landing zone's route table sends it.
resource powerPlatformSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' = if (!powerPlatformSubnetExists) {
  parent: vnet
  name: powerPlatformSubnetName
  properties: {
    addressPrefix: powerPlatformSubnetPrefix
    networkSecurityGroup: {
      id: powerPlatformNsg.id
    }
    delegations: [
      {
        name: 'Microsoft.PowerPlatform/enterprisePolicies'
        properties: {
          serviceName: 'Microsoft.PowerPlatform/enterprisePolicies'
        }
      }
    ]
    defaultOutboundAccess: false
  }
}

// One virtual network: the geography Sweden has one Azure region. The policy is read-only once an environment is linked to it, so it is made only while it is not there.
resource enterprisePolicy 'Microsoft.PowerPlatform/enterprisePolicies@2020-10-30-preview' = if (!enterprisePolicyExists) {
  name: enterprisePolicyName
  location: enterprisePolicyGeography
  kind: 'NetworkInjection'
  tags: tags
  properties: {
    networkInjection: {
      virtualNetworks: [
        {
          id: vnet.id
          subnet: {
            name: powerPlatformSubnetName
          }
        }
      ]
    }
  }
  dependsOn: [
    powerPlatformSubnet
  ]
}

output subnetName string = powerPlatformSubnetName
output enterprisePolicyName string = enterprisePolicyName
output enterprisePolicyId string = resourceId('Microsoft.PowerPlatform/enterprisePolicies', enterprisePolicyName)
