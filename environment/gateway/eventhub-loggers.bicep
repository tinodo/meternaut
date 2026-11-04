// The two Event Hub loggers that two policy fragments of the Citadel gateway module send usage records through.
//
// The fragments ai-usage and pii-state-saving log to an Event Hub through loggers of these names, and the service refuses to
// save a fragment whose logger does not exist; it also refuses a logger whose address does not resolve. So the loggers are
// made after the Event Hubs namespace exists (environment/recording/main.bicep) and before the module is applied with its
// parameter deployUsageRecordingFragments on (environment/kit-patches/no-usage-recording-fragments.patch).
//
// The loggers use the gateway's user-assigned identity (no connection string): that identity has the role Azure Event Hubs
// Data Sender on the namespace, given by the recording's template. Made after the kit's bicep/infra/modules/apim/apim.bicep,
// which makes the same two loggers together with its own Event Hub; here the Event Hub is elsewhere, so its address is a parameter.
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "gateway-prepare" (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Name of the existing API Management instance, in this resource group.')
param apimName string

@description('Host name of the Event Hubs namespace, without scheme or port.')
@minLength(10)
param eventHubHost string

@description('Name of the event hub that receives the usage records.')
param usageHubName string = 'ai-usage'

@description('Name of the event hub that receives the personal-data usage records.')
param piiHubName string = 'pii-usage'

@description('Client id of the gateway identity, which has the role Azure Event Hubs Data Sender on the namespace.')
@minLength(36)
@maxLength(36)
param identityClientId string

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource usageLogger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'usage-eventhub-logger'
  properties: {
    loggerType: 'azureEventHub'
    description: 'Event Hub logger for the gateway usage records'
    credentials: {
      name: usageHubName
      endpointAddress: eventHubHost
      identityClientId: identityClientId
    }
  }
}

resource piiLogger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'pii-usage-eventhub-logger'
  properties: {
    loggerType: 'azureEventHub'
    description: 'Event Hub logger for the personal-data usage records and logs'
    credentials: {
      name: piiHubName
      endpointAddress: eventHubHost
      identityClientId: identityClientId
    }
  }
}

output usageLoggerName string = usageLogger.name
output piiLoggerName string = piiLogger.name
