// The AI Gateway of Meternaut's model calls: Azure's AI Gateway (preview), the separate service Microsoft.ApiManagement/aigateways, which is not a classic
// API Management instance (docs/proposals/08-ai-gateway.md). It is the governance hub of the Citadel design: every model call of Meternaut goes through it, with no direct path
// (AGENTS.md rule 15 (c)). This template is step 1 of 2: the gateway, its models and aliases, and its roles, which serve the Detective and the Skeptic of the cases app.
// Step 2 (on in code, behind the switch AGENTS_VIA_AI_GATEWAY in tools/environment-params.py, which is True) connects the Foundry project to it so that the agents call through it too, and moves their model names.
// This template only gives the Foundry project's identity its role (below); the connection and the model names are made by the actions foundry and cases (docs/proposals/08-ai-gateway.md).
//
// What it holds:
//  - the gateway aigw-<workload>-<suffix>, with a system-assigned identity and the subnet snet-aigw as its backend subnet. The gateway reaches its backends through that subnet, so the call
//    to the private Foundry resource of the agents never leaves the virtual network. THE SUBNET IS NOT MADE HERE: it has to be there when this template is deployed. The template
//    environment/aigateway/subnet.bicep makes it (delegated to Microsoft.App/environments, once, AGENTS.md rule 27), and the action aigateway deploys that one first, waits until the
//    landing zone's network manager has put its route table on the subnet, and only then deploys this one, so that the gateway is made on the subnet as the landing zone leaves it.
//  - Foundry User for the gateway's identity on the Foundry resource of the agents, so that it can call the model deployments without a key.
//  - one model provider of kind Foundry, and for each model of environment/models.json one model and one alias. The alias is the name that a caller sends in the
//    `model` field of a request. It is the deployment's name, as the portal makes it for a Foundry import, and the model resource has that name with its dots
//    replaced by hyphens, because the name of a model resource does not allow dots.
//  - on each model, a content safety policy at Medium for the four categories. The deployment's own guardrail (environment/foundry/main.bicep) still runs on every
//    call that the gateway makes to the deployment: a request has to pass each of the two. The gateway has no Prompt Shields; the guardrail has.
//  - AI Gateway Models User on the gateway for the Operator's identity (the Operator, environment/operator/main.bicep, runs the check, tools/aigateway-check.py),
//    for the cases app's identity when its principal id is given (its Detective and Skeptic call the gateway with it), and for the Foundry project's identity when its principal id is given.
//    Step 2 gives the project's (the workflow passes its object id while the switch of step 2 is on), and an empty value means none yet.
//  - optionally, the OpenTelemetry exporter to the shared Application Insights component. It is off, and what is missing for turning it on is in the proposal.
//
// THE FRONTEND IS PUBLIC, AND NO TEMPLATE CAN CHANGE THAT. The service offers no private endpoint, and the setting publicNetworkAccess Disabled has no effect (Learn,
// "Migrate from the AI Gateway tier in API Management", read 2026-11-07: "Private endpoints aren't supported"; the AI Gateway samples, the private networking page: "setting
// publicNetworkAccess to Disabled through Azure Resource Manager has no effect"). Only the backend side is private. The endpoint is protected by Microsoft Entra ID and by role
// assignments: this template makes no API key and no IP filter. The service also keeps a built-in key named master, which no template can remove; the action aigateway
// deletes it when the service lets it, and reads back which keys exist (tools/aigateway-prep.py).
//
// Left out on purpose:
//  - the gateway-wide policies (a token limit, a request rate limit and a cost limit for each caller). They live on the default workspace, which exists on its own and which
//    the service's samples only ever read, because a PUT replaces the whole workspace. The action aigateway applies environment/aigateway/policies.json to it with a merge,
//    as the samples' own script does (tools/aigateway-prep.py policies).
//  - an API key, a private DNS zone, a link to one and a zone group (AGENTS.md rules 19 and 23): the landing zone's DNS resolves the Foundry resource's name to its private
//    address, and the gateway reaches it through its subnet.
//
// API versions: 2025-09-01-preview for every aigateways resource. It is the one that the portal and every Microsoft sample use. The service accepts newer ones for the
// gateway itself, and the children only up to 2026-09-01-preview when this was probed. Bicep has no type definitions for any of them yet, so the BCP081 warning is suppressed
// on each such resource. The service is a preview: this template changes with it, and it has no service level agreement.
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "aigateway" (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of every resource. The preview offers the service in a few regions, and the subnet has to be in the gateway\'s region.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Name of the gateway: 3 to 24 lower-case letters, digits and hyphens, starting and ending with a letter or digit (the service\'s pattern). It is the first label of the gateway\'s host name, which the service reports and nothing constructs.')
@minLength(3)
@maxLength(24)
param gatewayName string

@description('Name of the Foundry resource of the agents (environment/foundry/main.bicep makes it). The template only reads it: the gateway calls its model deployments.')
@minLength(2)
@maxLength(64)
param foundryAccountName string

@description('The models of the agents\' Foundry resource: name and version. The workflow reads them from environment/models.json. Each gets a model and an alias in the gateway.')
param models array

@description('Principal id of the system-assigned identity of the Foundry project. It gets AI Gateway Models User on the gateway. Empty means none yet: the step that connects the project to the gateway gives it. The template works without it.')
@maxLength(36)
param foundryProjectPrincipalId string = ''

@description('Principal id of the system-assigned identity of the cases app. It gets AI Gateway Models User on the gateway: every model call of the Detective and the Skeptic goes through the gateway with that identity. Empty means none: the app has no identity before the action cases has made it, and the action aigateway then makes the gateway without the role (the next run gives it). The workflow reads it from the app.')
@maxLength(36)
param casesPrincipalId string = ''

@description('Switch for the OpenTelemetry exporter to the shared Application Insights component. Off. Turning it on needs three things that no template can do: the component\'s Azure Monitor workspace ingestion has to be on, the resource provider Microsoft.Monitor has to be registered, and the gateway\'s identity needs Monitoring Metrics Publisher on the component\'s data collection rule, which a person gives (the proposal lists them).')
param telemetryEnabled bool = false

@description('Name of the Application Insights component that the exporter sends to, when it is on.')
param telemetryComponentName string = 'appi-${workload}'

var tags = {
  workload: workload
  component: 'ai-gateway'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'ai-gateway'
}

var virtualNetworkName = 'vnet-${workload}'
var aigwSubnetName = 'snet-aigw'
// The name of the Operator's identity, as environment/operator/main.bicep makes it (a test holds the two together). The action operator runs before aigateway.
var operatorIdentityName = 'id-${workload}-operator'
var providerName = 'foundry'
// What a model of this provider serves, as the service's samples and the portal's import write it. The check and the agents use chat completions.
var supportedEndpoints = [
  '/openai/v1/chat/completions'
  '/openai/v1/responses'
]
// The lowest severity that a content safety policy blocks: Medium blocks medium and high.
var contentSafetySeverity = 'Medium'

// Foundry User (named Azure AI User until the rename of the Foundry roles; the id is the same): the role that the service's samples give the gateway's identity on the
// Foundry resource. The narrower Cognitive Services OpenAI User may be enough for chat completions; that was not tried.
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
// AI Gateway Models User: its data actions list and invoke the models of the gateway, and nothing else (not the tools). Given on the gateway, never on the group.
var aiGatewayModelsUserRoleId = 'a6b68e3d-a1f0-4c60-8678-237c050cf4ea'

// Only read, so an API version that has types serves, the one of environment/main.bicep: the endpoint and the id are all that this template takes from the resource.
resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource operatorIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: operatorIdentityName
}

// A system-assigned identity, and no sku: the service owns it (the portal sends none). publicNetworkAccess Enabled is what the portal sends; it is the only value that
// has an effect (see the header). The subnet is named by its id, which is the same on every run, so a second deploy sends the value that the first one did. It is not
// made here: it is in Azure already, with the landing zone's route table on it when the landing zone puts one on this network (the workflow waits for that; see the header).
#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
    backend: {
      subnet: {
        id: resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, aigwSubnetName)
      }
    }
  }
}

// Exists on its own with the gateway, and is only read here: the parent of the provider, the aliases and the exporter.
#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

// The name uses the gateway's id, as the roles of the function apps do (a system-assigned identity ends with its resource: a gateway that is made again gets a new
// identity, and the old assignment is removed first, which the proposal says).
resource gatewayCallsFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account
  name: guid(account.id, gateway.id, foundryUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalId: gateway.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// The provider authenticates with the gateway's managed identity, for the audience of the Foundry resource. No key is stored in it. It comes after the role.
#disable-next-line BCP081
resource foundryProvider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' = {
  parent: workspace
  name: providerName
  properties: {
    kind: 'Foundry'
    displayName: 'Foundry resource of the agents'
    description: 'The model deployments of the Foundry resource of the agents, called with the gateway\'s own identity and no key.'
    foundry: {
      endpoint: endsWith(account.properties.endpoint, '/') ? account.properties.endpoint : '${account.properties.endpoint}/'
      resourceIds: [
        account.id
      ]
      authentication: {
        kind: 'ManagedIdentity'
        managedIdentity: {
          resource: 'https://cognitiveservices.azure.com/'
        }
      }
    }
  }
  dependsOn: [
    gatewayCallsFoundry
  ]
}

// One at a time: the models of a provider are written one after another. The deployment is named as the model is in environment/models.json, which is how
// environment/foundry/main.bicep names it. The resource's name has no dots; the alias below keeps the name as it is.
@batchSize(1)
#disable-next-line BCP081
resource modelOfProvider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' = [for model in models: {
  parent: foundryProvider
  name: replace(model.name, '.', '-')
  properties: {
    displayName: model.name
    description: 'Deployment ${model.name} of the Foundry resource of the agents.'
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: supportedEndpoints
    deployment: {
      resourceId: resourceId('Microsoft.CognitiveServices/accounts/deployments', foundryAccountName, model.name)
      modelName: model.name
      modelVersion: model.version
    }
    policies: [
      {
        type: 'contentSafety'
        hateSeverity: contentSafetySeverity
        violenceSeverity: contentSafetySeverity
        sexualSeverity: contentSafetySeverity
        selfHarmSeverity: contentSafetySeverity
      }
    ]
  }
}]

// The name that a caller sends in the `model` field. The resource name and `aliasName` are both the deployment's name, dots included: the specification allows dots in an
// alias's name (^[a-zA-Z0-9_.-]+$, where a model's name allows none) and the portal's own code keeps them, so a caller gets that name whether the service reads the property or the
// resource name at this API version (docs/proposals/08-ai-gateway.md). One target each, so there is no routing and no failover: priority and weight are the service's own defaults.
// One at a time too, and only after every model is written: the service is a preview, nothing is known of how it takes two writes into one workspace at once, and the one resource of this project that
// takes one write at a time (the Foundry resource) refuses the second with a precondition error. The extra minute costs nothing; a refused write costs a run.
@batchSize(1)
#disable-next-line BCP081
resource aliasOfModel 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = [for (model, index) in models: {
  parent: workspace
  name: model.name
  properties: {
    aliasName: model.name
    description: 'The name of deployment ${model.name} of the agents\' Foundry resource.'
    backendModels: [
      {
        resourceId: modelOfProvider[index].id
        priority: 0
        weight: 1
      }
    ]
  }
  dependsOn: [
    modelOfProvider
  ]
}]

// The Operator runs the check: it calls each alias with its own token. It may list and invoke the models and nothing else, and it holds no right to change the gateway.
// A new role takes up to ten minutes to apply, so the check runs after that.
resource operatorCallsTheModels 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: gateway
  name: guid(gateway.id, operatorIdentity.id, aiGatewayModelsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aiGatewayModelsUserRoleId)
    principalId: operatorIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// The Foundry project calls the models through a connection (step 2): the workflow passes the object id of the project's identity while the switch of step 2 is on. Empty means none yet.
resource projectCallsTheModels 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(foundryProjectPrincipalId)) {
  scope: gateway
  name: guid(gateway.id, foundryProjectPrincipalId, aiGatewayModelsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aiGatewayModelsUserRoleId)
    principalId: foundryProjectPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// The cases app calls the models for the Detective and the Skeptic, with its own identity: every model call of Meternaut goes through this gateway (AGENTS.md rule 15 (c)). It may list and invoke
// the models and nothing else. Empty until the app has an identity (the action cases makes the app), and the role needs up to ten minutes to apply, so a Watch started right after waits for it.
resource casesCallsTheModels 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(casesPrincipalId)) {
  scope: gateway
  name: guid(gateway.id, casesPrincipalId, aiGatewayModelsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aiGatewayModelsUserRoleId)
    principalId: casesPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: telemetryComponentName
}

// The properties of the component that name its OTLP endpoints are not in the Bicep types yet, and they exist only once its Azure Monitor workspace ingestion is on.
var otlp = any(insights.properties)

// Off. The same shape as the service's own sample (OpenTelemetry, the endpoints of the component, the gateway's identity for the audience https://monitor.azure.com, and
// no payload of any request or answer). The identity needs Monitoring Metrics Publisher on the component's data collection rule, which lies in a managed resource group
// that a deployment cannot write to: a person gives that role, and until it has applied the service refuses this resource.
#disable-next-line BCP081
resource telemetryExporter 'Microsoft.ApiManagement/aigateways/workspaces/telemetryExporters@2025-09-01-preview' = if (telemetryEnabled) {
  parent: workspace
  name: 'appinsights'
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
  }
}

output gatewayName string = gateway.name
@description('The host name of the gateway\'s frontend, as the service reports it (a read only property). It is public.')
output gatewayHost string = gateway.properties.frontend.defaultHostname
output subnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, aigwSubnetName)
