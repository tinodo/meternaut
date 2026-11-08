// The telemetry of the AI Gateway: an OpenTelemetry exporter that sends the gateway's logs, traces and metrics to the project's own Application Insights component, with the gateway's own
// managed identity and no key (AGENTS.md rule 23). Made only by the action gateway-telemetry (AGENTS.md rule 18), and only after that action has read that the prerequisites below are in place. It is a
// template of its own, apart from environment/aigateway/main.bicep, because a missing prerequisite makes the service refuse this one resource, and that must never stop the gateway, its models or its roles.
//
// What it makes: one exporter named appinsights in the gateway's default workspace.
//  - kind OpenTelemetry, with the three OTLP endpoints that the component reports once its OpenTelemetry ingestion is on (the base template turns it on: the constant GATEWAY_TELEMETRY in
//    tools/environment-params.py) and the audience https://monitor.azure.com. No header and no connection string: the gateway presents its own identity.
//  - payloadCapture false, written out and not left to the service's default. The gateway then sends metadata only (status, route, model, token counts, durations, policy that ran), and no prompt, no
//    completion and no tool input or output. The service applies no redaction to a payload that is captured, so capture is never turned on here: no parameter can do it, and the check of the gateway
//    (tools/drift-check.py) fails when the live exporter says otherwise.
//  - the four token claims of the service's recommended preset, so that every record names its caller: tid and oid for logs, traces and metrics, appid and azp for logs and traces. Telemetry is not
//    authentication: the gateway only reads the claims that the caller's token already holds. The oid is the object id of the caller's identity, which is how the workbook and the alert rules of
//    environment/governance/main.bicep tell the callers apart (environment/aigateway/contracts.json).
//
// What has to be there first, and who makes it (each is read before this is deployed, and a missing one stops the action before anything is changed):
//  1. The resource provider Microsoft.Monitor is registered in the subscription: the component's OpenTelemetry ingestion makes a managed Azure Monitor workspace, a data collection endpoint and a data
//     collection rule. A person with the right to register a provider does it once (environment/BOOTSTRAP.md).
//  2. The component reports its OTLP endpoints and its data collection rule, a few minutes after the action base has deployed it with the ingestion on.
//  3. The gateway's identity holds Monitoring Metrics Publisher on that data collection rule. The rule lies in a resource group that the platform manages, behind a deny assignment, outside the project's
//     group: the deploy identity has no right there, so a person gives the role once, with tools/governance-setup.py (environment/BOOTSTRAP.md). A role takes up to ten minutes to apply.
//
// API version 2025-09-01-preview, the one that the portal and the service's samples use for every resource of the gateway (environment/aigateway/main.bicep); Bicep has no types for it, so the BCP081
// warning is switched off on the resource. The service is a preview and has no service level.
targetScope = 'resourceGroup'

@description('Name of the AI Gateway (environment/aigateway/main.bicep makes it). The template only reads it: the exporter is a child of its default workspace.')
@minLength(3)
@maxLength(24)
param gatewayName string

@description('Name of the Application Insights component that the exporter sends to. It is the project\'s own component (environment/base/main.bicep), shared with the cases app.')
param telemetryComponentName string = 'appi-meternaut'

@description('Name of the exporter. The portal names it appinsights.')
param exporterName string = 'appinsights'

@description('The token claims that become attributes of the telemetry, and the signals that carry each one: the service\'s recommended preset. The oid is what names a caller in the workbook and in the alert rules.')
param claimAttributes array = [
  {
    source: { kind: 'claims', value: 'tid' }
    signals: ['logs', 'traces', 'metrics']
  }
  {
    source: { kind: 'claims', value: 'oid' }
    signals: ['logs', 'traces', 'metrics']
  }
  {
    source: { kind: 'claims', value: 'appid' }
    signals: ['logs', 'traces']
  }
  {
    source: { kind: 'claims', value: 'azp' }
    signals: ['logs', 'traces']
  }
]

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

resource insights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: telemetryComponentName
}

// The properties of the component that name its OTLP endpoints are not in the Bicep types yet, and they exist only once its OpenTelemetry ingestion is on and the platform has made the endpoints.
var otlp = any(insights.properties)

#disable-next-line BCP081
resource telemetryExporter 'Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters@2025-09-01-preview' = {
  parent: workspace
  name: exporterName
  properties: {
    kind: 'OpenTelemetry'
    payloadCapture: false
    applicationInsights: {
      resourceId: insights.id
    }
    openTelemetry: {
      metricsEndpoint: otlp.OTLPMetricsEndpoint
      logsEndpoint: otlp.OTLPLogsEndpoint
      tracesEndpoint: otlp.OTLPTracesEndpoint
      credentials: {
        managedIdentity: {
          resource: 'https://monitor.azure.com'
        }
      }
    }
    telemetry: {
      attributes: claimAttributes
    }
  }
}

output exporterName string = telemetryExporter.name
