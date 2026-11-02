// The gateway name of an API Management instance that runs inside a virtual network (internal mode).
//
// The instance's host name is <name>.azure-api.net, which resolves to nothing inside a private network.
// This creates a private DNS zone for that one name, an A record for the instance's private address, and a
// link to each network that must resolve it. The zone is named after the instance, so no other azure-api.net
// name is affected.
//
// Deploy into the resource group of the hub, after the instance is active:
//   az deployment group create -g <hub resource group> --template-file hub/dns-gateway.bicep --parameters <file>
//
// To remove it, delete the links to networks outside the resource group first, then the zone or the group, so that
// no link outlives the zone or the network it joins.
targetScope = 'resourceGroup'

@description('Name of the API Management instance. Its gateway host name is <name>.azure-api.net.')
param apimName string

@description('Resource IDs of the virtual networks that resolve the name. List the hub\'s own network and, to make the name resolvable across the landing zone, the network whose DNS the landing zone uses.')
@minLength(1)
param linkedVirtualNetworkIds array

param tags object = {}

var zoneName = '${apimName}.azure-api.net'
var networkIds = union(linkedVirtualNetworkIds, [])

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource zone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: zoneName
  location: 'global'
  tags: tags
}

resource gateway 'Microsoft.Network/privateDnsZones/A@2024-06-01' = {
  parent: zone
  name: '@'
  properties: {
    ttl: 300
    aRecords: [
      {
        ipv4Address: apim.properties.privateIPAddresses[0]
      }
    ]
  }
}

resource links 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [for vnetId in networkIds: {
  parent: zone
  name: 'link-${uniqueString(vnetId)}'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}]

output zoneName string = zone.name
output gatewayHost string = zoneName
