// Waste that Meternaut plants itself: an unattached disk, and when asked an unassigned public IP address, in the project's own resource group, each tagged with
// the tag that the loop looks for. The Watch finds them like any other waste, two AI roles judge them, and a person approves: the change then runs with that
// person's own permissions and removes exactly these. Meternaut holds no right to change Azure, so Azure refuses the change for a person who may not delete them in this group.
// It exists so that the whole loop can be shown from the finding to the removal without changing anything that belongs to another project.
//
// What it costs while it stays: the disk is the smallest Standard SSD size (about 0.30 US dollars a month); a Standard public IP address is about 3.65 a month.
// Nothing here is connected to anything. Deployed only by the workflow .github/workflows/deploy-hub.yml, action "plant" (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of the resources.')
param location string = resourceGroup().location

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('A short word that marks this planting: it is the value of the tag and part of the names, so that a second planting makes other resources.')
@minLength(1)
@maxLength(12)
param plantedId string

@description('Also plant an unassigned public IP address. It needs the landing zone to allow a public IP address in this group.')
param plantPublicIp bool = false

var tags = {
  workload: 'meternaut'
  component: 'planted-waste'
  environment: 'dev'
  owner: owner
  'meternaut-planted': plantedId
}

resource disk 'Microsoft.Compute/disks@2024-03-02' = {
  name: 'planted-disk-${plantedId}'
  location: location
  tags: tags
  sku: {
    name: 'StandardSSD_LRS'
  }
  properties: {
    creationData: {
      createOption: 'Empty'
    }
    diskSizeGB: 4
    networkAccessPolicy: 'DenyAll'
    publicNetworkAccess: 'Disabled'
  }
}

resource address 'Microsoft.Network/publicIPAddresses@2024-05-01' = if (plantPublicIp) {
  name: 'planted-ip-${plantedId}'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
  }
}

output diskName string = disk.name
output diskId string = disk.id
output addressName string = plantPublicIp ? address.name : ''
