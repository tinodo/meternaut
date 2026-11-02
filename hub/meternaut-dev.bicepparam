using '../local/accelerator/bicep/infra/main.bicep'

// The smallest Citadel governance hub that works in a landing zone that denies public access to PaaS services.
// Names and addresses that are specific to one organisation come from the environment; nothing here names a subscription.
//
//   HUB_OWNER            the owner tag of every resource (required: a hub that costs money has a named owner)
//   HUB_STAGE            the value of the tag that the stage's budget filters on (default: foundations)
//   HUB_RESOURCE_GROUP   resource group to create (default: meternaut-dev-hub-rg)
//   HUB_APIM_NAME        name of the API Management instance; empty lets the template derive a unique one
//   HUB_KEY_VAULT_NAME   name of the Key Vault; empty derives one. Purge protection keeps a deleted vault's name
//                        for 90 days, so give a numbered name when the hub may be deleted and made again
//   HUB_VNET_PREFIX, HUB_APIM_SUBNET, HUB_PE_SUBNET, HUB_FUNCTION_SUBNET, HUB_AGENT_SUBNET
//                        the hub's own network; it must not overlap a network that peers with it

param environmentName = readEnvironmentVariable('HUB_ENVIRONMENT_NAME', 'meternaut-hub-dev')
param location = readEnvironmentVariable('HUB_LOCATION', 'swedencentral')
param apicLocation = ''
param tags = {
  workload: 'meternaut'
  component: 'citadel-governance-hub'
  environment: 'dev'
  owner: readEnvironmentVariable('HUB_OWNER')
  'meternaut-stage': readEnvironmentVariable('HUB_STAGE', 'foundations')
}

param resourceGroupName = readEnvironmentVariable('HUB_RESOURCE_GROUP', 'meternaut-dev-hub-rg')
param apimServiceName = readEnvironmentVariable('HUB_APIM_NAME', '')
param keyVaultName = readEnvironmentVariable('HUB_KEY_VAULT_NAME', '')

// Its own spoke network
param vnetAddressPrefix = readEnvironmentVariable('HUB_VNET_PREFIX', '10.170.0.0/24')
param apimSubnetPrefix = readEnvironmentVariable('HUB_APIM_SUBNET', '10.170.0.0/26')
param privateEndpointSubnetPrefix = readEnvironmentVariable('HUB_PE_SUBNET', '10.170.0.64/26')
param functionAppSubnetPrefix = readEnvironmentVariable('HUB_FUNCTION_SUBNET', '10.170.0.128/26')
param agentSubnetPrefix = readEnvironmentVariable('HUB_AGENT_SUBNET', '10.170.0.192/26')
param foundryNetworkInjectionEnabled = false

// The cheapest gateway that can reach private backends: the classic Developer tier, injected in the network, with no public gateway
param apimSku = 'Developer'
param apimSkuUnits = 1
param apimNetworkType = 'Internal'

// A landing zone that denies public access to these services
param eventHubNetworkAccess = 'Disabled'
param keyVaultExternalNetworkAccess = 'Disabled'
param aiFoundryExternalNetworkAccess = 'Disabled'

// Off: nothing in the build plan reads them, and together they cost more than the rest of the hub
param deployUsageIngestion = false
// Nothing in the gateway reads the vault with the Foundry accounts' identities, so they get no access to it
param grantFoundryKeyVaultAccess = false
// The person who deploys gets no standing role on the Foundry account: every model call goes through the gateway
param grantDeployerFoundryAccess = false
param enableAPICenter = false
param enableManagedRedis = false
param enableDocumentIntelligence = false
param enableAzureAISearch = false
param enableOpenAIRealtime = false
param createAppInsightsDashboards = false
param useAzureMonitorPrivateLinkScope = false

// Subscription keys for now; JWT validation needs an app registration (see README, "What it does not do")
param entraAuth = false

// Token counts and request metadata are logged; prompts and answers are not (checked in the workspace: the message columns are empty)
param azureMonitorLogSettings = {
  frontend: {
    request: { headers: [], body: { bytes: 0 } }
    response: { headers: [], body: { bytes: 0 } }
  }
  backend: {
    request: { headers: [], body: { bytes: 0 } }
    response: { headers: [], body: { bytes: 0 } }
  }
  largeLanguageModel: {
    logs: 'enabled'
    requests: { messages: 'none', maxSizeInBytes: 0 }
    responses: { messages: 'none', maxSizeInBytes: 0 }
  }
}

param aiFoundryInstances = [
  {
    name: ''
    location: readEnvironmentVariable('HUB_LOCATION', 'swedencentral')
    customSubDomainName: ''
    defaultProjectName: 'citadel-governance-project'
    networkInjectionEnabled: false
  }
]

// The design's small model (the `triage` alias), in the EU data zone
param aiFoundryModelsConfig = [
  {
    name: 'gpt-6-luna'
    publisher: 'OpenAI'
    version: '2026-09-22'
    sku: 'DataZoneStandard'
    capacity: 50
    retirementDate: '2028-03-11'
    aiserviceIndex: 0
  }
]
