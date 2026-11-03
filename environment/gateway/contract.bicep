// The first contract: what one consumer may do at the gateway. It is the same four objects as the Citadel kit's
// citadel-access-contracts/modules/apimOnboardService.bicep (a product, the APIs it grants, its policy, one subscription), in
// the gateway's resource group, without the kit's Key Vault and Foundry parts. The consumer's key is the subscription's
// key: it is not an output of this template and is stored nowhere; the workflow reads it from the gateway when it tests the
// contract (tools/environment-smoke.py), and a consumer is given it when there is one.
//
// The policy carries the contract's rules: the models the consumer may ask for and the tokens it may use a minute and a
// month. tools/environment-params.py builds it from environment/contract.json and environment/gateway/contract-policy.xml,
// and checks every value before anything is deployed.
//
// The APIs must exist: this runs after the Citadel module has been applied ("gateway"). It only adds objects (a product, its
// links, its policy and its subscription); it deletes nothing.

@description('The existing API Management instance.')
param apimName string

@description('The contract, and its product: letters, digits and hyphens.')
@minLength(3)
@maxLength(60)
param contractName string

@description('The consumer\'s subscription: the one whose key is the contract\'s key.')
@minLength(3)
@maxLength(80)
param subscriptionName string

@description('What the contract is for, shown on the product.')
@maxLength(400)
param contractDescription string

@description('The names of the APIs that the contract grants. They exist in the instance already.')
param apiNames array

@description('The contract\'s policy: its models, its tokens a minute and its tokens a month.')
param policyXml string

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource product 'Microsoft.ApiManagement/service/products@2024-05-01' = {
  parent: apim
  name: contractName
  properties: {
    displayName: contractName
    description: contractDescription
    subscriptionRequired: true
    approvalRequired: true
    subscriptionsLimit: 1
    state: 'published'
  }
}

@batchSize(1)
resource productApis 'Microsoft.ApiManagement/service/products/apis@2024-05-01' = [for apiName in apiNames: {
  parent: product
  name: apiName
}]

resource productPolicy 'Microsoft.ApiManagement/service/products/policies@2024-05-01' = {
  parent: product
  name: 'policy'
  dependsOn: [
    productApis
  ]
  properties: {
    format: 'rawxml'
    value: policyXml
  }
}

resource consumerSubscription 'Microsoft.ApiManagement/service/subscriptions@2024-05-01' = {
  parent: apim
  name: subscriptionName
  dependsOn: [
    productPolicy
  ]
  properties: {
    displayName: subscriptionName
    scope: product.id
    state: 'active'
  }
}

output productName string = product.name
output subscriptionName string = consumerSubscription.name
