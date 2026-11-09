// Waste that Meternaut plants itself: an unattached disk, and when asked an unassigned public IP address and a virtual machine that nothing uses, in the project's own
// resource group, each tagged with the tag that the loop looks for. The Watch finds them like any other waste, two AI roles judge them, and a person approves: the change then
// runs with that person's own permissions and changes exactly these (a disk is deleted or moved a tier down, an address is deleted, a machine is stopped or resized). Meternaut holds no
// right to change Azure, so Azure refuses the change for a person who may not do it in this group. It exists so that the whole loop can be shown from the finding to the change
// without touching anything that belongs to another project.
//
// What it costs while it stays, at the price list of Sweden Central read from the public Retail Prices API on 2026-11-08 (docs/proposals/14-families-of-change.md has the table):
//  - the disk is the smallest Premium SSD size (P1, 4 GiB: 0.78 US dollars a month, about 0.0011 an hour). It is a Premium SSD, and not the smaller price of a Standard SSD, so that the family
//    change-disk-tier has a tier to move it down from; a Standard SSD of that size is not moved, because a Standard HDD is billed from 32 GiB and would cost more;
//  - a Standard public IP address is about 3.65 a month (plantPublicIp);
//  - the machine (plantVm) is a Standard_B4als_v2, which is billed 0.138 US dollars an hour while it runs (Linux), nothing for compute once it is stopped and released, and 0.0389 an hour
//    after a resize to Standard_B2als_v2. Its OS disk is a Standard SSD of 4 GiB (0.30 a month), its network interface costs nothing, and it has no public IP address. It is not the cheapest
//    size (Standard_B2ts_v2, 0.0108 an hour) because that one has no smaller size in its series, and then resize-vm would have nothing to show; and the older Standard_B2s is not
//    available to the subscription of the pilot in Sweden Central (the real run of 2026-11-09 was refused for it).
// Nothing here is connected to anything but the machine's own disk and network interface. The machine has no operating system, no account and no key: its OS disk is an empty disk that is
// attached as it is (createOption Attach, no osProfile), so there is nothing on it to sign in to. Deployed only by the workflow .github/workflows/deploy-hub.yml, action "plant"
// (AGENTS.md rule 18).
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

@description('Also plant a virtual machine that nothing uses, with its network interface and its OS disk and no public IP address, so that the families stop-vm and resize-vm can be shown on it. The network interface is in the subnet snet-pe of the virtual network vnet-<workload>, which the model side made and which this template only reads.')
param plantVm bool = false

@description('The size of the planted virtual machine. tools/environment-params.py sets it: a burstable size that has a smaller one in its series, so that resize-vm has a step to take.')
param plantedVmSize string = 'Standard_B4als_v2'

@description('Short name of the workload, used in the name of the virtual network that the machine\'s network interface is in.')
param workload string = 'meternaut'

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
    name: 'Premium_LRS'
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

// The machine's network interface: in the subnet snet-pe, which has a network security group without a rule of its own, and with a private address only. The subnet is read by its id and
// never made or changed here (AGENTS.md rule 27).
resource nic 'Microsoft.Network/networkInterfaces@2025-05-01' = if (plantVm) {
  name: 'planted-nic-${plantedId}'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-${workload}', 'snet-pe')
          }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
  }
}

// An empty disk that is marked as holding a Linux system, so that Azure takes it as the OS disk of a machine. It is a Standard SSD of the smallest size.
resource osDisk 'Microsoft.Compute/disks@2024-03-02' = if (plantVm) {
  name: 'planted-osdisk-${plantedId}'
  location: location
  tags: tags
  sku: {
    name: 'StandardSSD_LRS'
  }
  properties: {
    osType: 'Linux'
    creationData: {
      createOption: 'Empty'
    }
    diskSizeGB: 4
    networkAccessPolicy: 'DenyAll'
    publicNetworkAccess: 'Disabled'
  }
}

// The machine: the OS disk above attached as it is, the network interface above, no osProfile (so no account, no password and no key), no public IP address and no identity. Deleting the
// machine by hand leaves its disk and its interface (deleteOption Detach): they are planted waste too, and a person approves their removal like any other.
resource machine 'Microsoft.Compute/virtualMachines@2025-04-01' = if (plantVm) {
  name: 'planted-vm-${plantedId}'
  location: location
  tags: tags
  properties: {
    hardwareProfile: {
      vmSize: plantedVmSize
    }
    storageProfile: {
      osDisk: {
        osType: 'Linux'
        createOption: 'Attach'
        caching: 'None'
        deleteOption: 'Detach'
        managedDisk: {
          id: osDisk.id
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
          properties: {
            primary: true
            deleteOption: 'Detach'
          }
        }
      ]
    }
  }
}

output diskName string = disk.name
output diskId string = disk.id
output addressName string = plantPublicIp ? address.name : ''
output machineName string = plantVm ? machine.name : ''
