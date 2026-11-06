// The Operator: the executor that works inside the virtual network, for what the deployment workflow cannot do from outside it once the services are private
// (docs/proposals/07-private-by-default.md). The workflow makes a short-lived container group (Azure Container Instances) in the delegated subnet below, with the
// user-assigned identity below, through Azure Resource Manager, which stays reachable. The container runs one script, the workflow reads its log through Azure
// Resource Manager, and the workflow deletes the group (tools/operator-run.py). Nothing runs between two runs, so nothing is paid between two runs.
//
// What this template holds, and nothing else: the identity id-<workload>-operator, the subnet snet-ops that container groups run in, that subnet's network
// security group, and the one role that the first run (the probe, operator/probe.sh) needs: Reader on the project's resource group, to show that the identity signs in
// and can read. The roles of the later steps (Website Contributor on the two function apps, Log Analytics Reader on the workspace, Azure Event Hubs Data Sender on the
// control hub) are added to this template with the step that uses each of them, and to the condition of the deploy identity's role-assignment right by a person
// (environment/BOOTSTRAP.md). The identity is attached to no app and holds no right outside the project's resource group.
//
// The subnet is made once and then left alone (opsSubnetExists), exactly like snet-cases in environment/cases/main.bicep (AGENTS.md rule 27): the landing zone's
// network manager puts a route table on a new subnet some minutes after it is made, a container group on the subnet gets its way out through that table, and a
// template that makes the subnet again takes the table away. The deployment workflow reads whether the subnet is there and passes it, and after the deploy it waits
// until the table is on the subnet. This template makes no route table, no private DNS zone, no link to one and no private endpoint (AGENTS.md rule 19).
//
// Two facts about container groups in a virtual network that Microsoft Learn states (container-instances-vnet, container-instances-virtual-network-concepts): the
// subnet holds container groups only, and a subnet smaller than /24 is known to run out of addresses, because the platform releases the address of a deleted group
// slowly. A /24 does not fit a small virtual network, so the subnet is as large as the network can spare (environment-params.py picks a /27), and the probe repeats
// runs to see whether that is enough. Container groups do not take the DNS servers of the virtual network: the workflow gives each group the landing zone's
// DNS servers itself (tools/operator-run.py, --dns-server), which is what lets a private endpoint's name resolve to its private address.
//
// No key of any kind (AGENTS.md rule 23): the container signs in with the identity below, and the only secret that ever reaches it is a value that the workflow
// passes for one run, which is never stored. Deployed only by the workflow .github/workflows/deploy-hub.yml, action "operator" (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of every resource.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Address range of the subnet that the Operator\'s container groups run in, inside the virtual network and apart from the other subnets, for example 10.53.0.192/27. It is delegated to Microsoft.ContainerInstance/containerGroups and holds nothing else.')
@minLength(9)
@maxLength(18)
param opsSubnetPrefix string

@description('True when the Operator\'s subnet is in Azure already. The template then leaves it alone: a template that makes the subnet again takes away the route table that the landing zone\'s network manager put on it, and the container groups on it lose their way out. The deployment workflow reads this from Azure.')
param opsSubnetExists bool = false

var tags = {
  workload: workload
  component: 'operator'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'private-by-default'
}

var virtualNetworkName = 'vnet-${workload}'
var opsSubnetName = 'snet-ops'

// Reader: the one role that the probe needs, to read the project's resource group with the identity's own token.
var readerRoleId = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' existing = {
  name: virtualNetworkName
}

// No rule of its own, like the other subnets': the default rules let a container group reach the virtual network and the internet (the landing zone's
// firewall decides there), and nothing is let in.
resource opsNsg 'Microsoft.Network/networkSecurityGroups@2025-05-01' = {
  name: 'nsg-${workload}-ops'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// Delegated to container groups, which is what a container group in a virtual network needs, and it holds nothing else. Made only while it is not there: see
// opsSubnetExists, and the header.
resource opsSubnet 'Microsoft.Network/virtualNetworks/subnets@2025-05-01' = if (!opsSubnetExists) {
  parent: vnet
  name: opsSubnetName
  properties: {
    addressPrefix: opsSubnetPrefix
    networkSecurityGroup: {
      id: opsNsg.id
    }
    delegations: [
      {
        name: 'container-groups'
        properties: {
          serviceName: 'Microsoft.ContainerInstance/containerGroups'
        }
      }
    ]
    defaultOutboundAccess: false
  }
}

// User-assigned and not system-assigned: the roles of an identity have to exist, and have to have reached every region of Azure Resource Manager, before a container
// starts with it, and a system-assigned identity exists only once its container group does. The identity is made here, once, and stays.
resource operatorIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workload}-operator'
  location: location
  tags: tags
}

// On the project's resource group and nowhere else. The right to give it is the deploy identity's role-assignment right with its condition, which lists the roles that
// the templates give: Reader is added to that list by a person (environment/BOOTSTRAP.md), and until then the deploy is refused here and nothing else is changed.
resource operatorReadsTheGroup 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: resourceGroup()
  name: guid(resourceGroup().id, operatorIdentity.id, readerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', readerRoleId)
    principalId: operatorIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output identityId string = operatorIdentity.id
@description('Principal id of the Operator\'s identity: the object id that role assignments name.')
output identityPrincipalId string = operatorIdentity.properties.principalId
@description('Client id of the Operator\'s identity: the container passes it to az login --identity.')
output identityClientId string = operatorIdentity.properties.clientId
output subnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, opsSubnetName)
