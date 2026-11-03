// The one identity that the Citadel gateway module needs on the existing API Management instance.
//
// The module looks the identity up by name in the instance's own resource group, and uses it to call the models and the
// content-safety and language services of the model account. The workflow attaches it to the instance afterwards
// (environment/gateway is deployed by .github/workflows/deploy-hub.yml, AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of the identity.')
param location string = resourceGroup().location

@description('Name of the identity.')
param identityName string = 'id-meternaut-gateway'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: {
    workload: 'meternaut'
    component: 'gateway-identity'
  }
}

output name string = identity.name
output id string = identity.id
output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
