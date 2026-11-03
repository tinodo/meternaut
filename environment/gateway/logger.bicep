// The loggers that the Citadel gateway module expects to find on the instance.
//
// appinsights-logger. The module's APIs and its service-level diagnostic point at a logger of that name. An instance that
// the kit did not create usually has a logger under another name, so a second one is added, on the Application Insights
// that the instance already writes to. Nothing is lost: both loggers feed the same component.
//
// usage-eventhub-logger and pii-usage-eventhub-logger. Two of the module's policy fragments (ai-usage and
// pii-state-saving) send usage records to an Event Hub through loggers of these names, and the service refuses to save a
// fragment whose logger does not exist ("Logger not found"). The module does not make those loggers: the kit's own
// deployment does, together with the Event Hub. The Event Hub belongs to Citadel's usage recording (an Event Hub, a Logic
// App and a Cosmos DB), which this environment leaves out on purpose: about 26 euros a month for the Event Hub with its
// private endpoint, about 265 with the rest. So the two loggers are placeholders. They point at an address that cannot
// exist (the .invalid top-level domain is reserved so that it never resolves), and nothing is lost by that: no API that the
// module makes here includes those two fragments, and neither does the contract's policy (the kit uses them only in its
// own access-contract policy templates, which this repository does not use), and a test holds that. The tokens of a call
// are counted by llm-emit-token-metric, in the set-llm-usage fragment, and go to Application Insights. When the usage
// recording is added, these loggers are pointed at the real Event Hub: same names, new address.
targetScope = 'resourceGroup'

@description('Name of the existing API Management instance, in this resource group.')
param apimName string

@description('Name of the Application Insights component that the instance already logs to.')
param appInsightsName string

@description('Resource group of that component. Empty means this resource group.')
param appInsightsResourceGroup string = ''

@description('Client id of the gateway\'s user-assigned identity, which the placeholder loggers name as their credential, as the real ones will.')
param gatewayIdentityClientId string

var placeholderAddress = 'usage-recording-not-deployed.invalid'

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
  scope: resourceGroup(empty(appInsightsResourceGroup) ? resourceGroup().name : appInsightsResourceGroup)
}

resource logger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'appinsights-logger'
  properties: {
    loggerType: 'applicationInsights'
    description: 'Application Insights logger that the Citadel gateway module expects'
    resourceId: appInsights.id
    credentials: {
      instrumentationKey: appInsights.properties.InstrumentationKey
    }
    isBuffered: true
  }
}

resource usageLogger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'usage-eventhub-logger'
  dependsOn: [
    logger
  ]
  properties: {
    loggerType: 'azureEventHub'
    description: 'Placeholder: the Event Hub of Citadel usage recording is not deployed. Named so that the module\'s ai-usage fragment can be saved; no API of this instance uses that fragment.'
    credentials: {
      name: 'ai-usage'
      endpointAddress: placeholderAddress
      identityClientId: gatewayIdentityClientId
    }
    isBuffered: true
  }
}

resource piiUsageLogger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'pii-usage-eventhub-logger'
  dependsOn: [
    usageLogger
  ]
  properties: {
    loggerType: 'azureEventHub'
    description: 'Placeholder: the Event Hub of Citadel usage recording is not deployed. Named so that the module\'s pii-state-saving fragment can be saved; no API of this instance uses that fragment.'
    credentials: {
      name: 'pii-usage'
      endpointAddress: placeholderAddress
      identityClientId: gatewayIdentityClientId
    }
    isBuffered: true
  }
}

output loggerName string = logger.name
output usageLoggerNames array = [
  usageLogger.name
  piiUsageLogger.name
]
