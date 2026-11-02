using '../../../local/accelerator/bicep/infra/citadel-access-contracts/main.bicep'

// The development contract of the learning demonstration (check C14).
// It grants one model through the OpenAI-compatible route of the hub and carries its own token limits.
//
// Where the hub is comes from the environment, so that nothing here names a subscription:
//   HUB_SUBSCRIPTION_ID   the subscription that holds the hub
//   HUB_RESOURCE_GROUP    the resource group of the hub
//   HUB_APIM_NAME         the name of the API Management instance
//   HUB_KEY_VAULT_NAME    the Key Vault of the hub, where the contract's key and endpoint are stored

param apim = {
  subscriptionId: readEnvironmentVariable('HUB_SUBSCRIPTION_ID')
  resourceGroupName: readEnvironmentVariable('HUB_RESOURCE_GROUP')
  name: readEnvironmentVariable('HUB_APIM_NAME')
}

param keyVault = {
  subscriptionId: readEnvironmentVariable('HUB_SUBSCRIPTION_ID')
  resourceGroupName: readEnvironmentVariable('HUB_RESOURCE_GROUP')
  name: readEnvironmentVariable('HUB_KEY_VAULT_NAME')
}

// The key goes into the vault; no key appears in the deployment's outputs
param useTargetAzureKeyVault = true

param useCase = {
  businessUnit: 'Meternaut'
  useCaseName: 'LearningDemo'
  environment: 'DEV'
}

param apiNameMapping = {
  LLM: ['unified-ai-api']
}

param services = [
  {
    code: 'LLM'
    endpointSecretName: 'METERNAUT-LEARNINGDEMO-LLM-ENDPOINT'
    apiKeySecretName: 'METERNAUT-LEARNINGDEMO-LLM-KEY'
    policyXml: loadTextContent('ai-product-policy.xml')
  }
]

param productTerms = 'Development contract of the learning demonstration: synthetic data only, one model, token limits set in the product policy.'

param useTargetFoundry = false
