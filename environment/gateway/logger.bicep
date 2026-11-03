// The Application Insights logger with the name that the Citadel gateway module expects.
//
// The module's APIs and its service-level diagnostic point at a logger called appinsights-logger. An instance that the
// kit did not create usually has a logger under another name, so a second one is added, on the Application Insights
// that the instance already writes to. Nothing is lost: both loggers feed the same component.
//
// This template makes no Event Hub logger. Two of the module's policy fragments (ai-usage and pii-state-saving) send usage
// records to an Event Hub through loggers that the kit's own deployment makes together with the Event Hub, and the service
// refuses to save a fragment whose logger does not exist; it also refuses a logger whose address does not resolve, so an
// empty placeholder does not work (tried, 2026-11-03). The usage recording is left out on purpose (an Event Hub, a Logic
// App and a Cosmos DB: about 265 euros a month), so environment/kit-patches/no-usage-recording-fragments.patch leaves out
// the two fragments too. No API of this environment uses them.
targetScope = 'resourceGroup'

@description('Name of the existing API Management instance, in this resource group.')
param apimName string

@description('Name of the Application Insights component that the instance already logs to.')
param appInsightsName string

@description('Resource group of that component. Empty means this resource group.')
param appInsightsResourceGroup string = ''

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

output loggerName string = logger.name
