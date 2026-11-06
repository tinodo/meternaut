// The Foundry resource of the agents: the place where Meternaut's agents (Microsoft Foundry Agent Service, prompt agents) live and are run.
//
// What it holds: a Foundry resource (kind AIServices) that can hold projects, one project (meternaut) with the agents in it, the same two
// model deployments as the model account, one guardrail (a content safety policy with Prompt Shields) that the deployments use and the agents
// inherit from them, a connection of the project to the Application Insights component of the first environment for the agents' traces, one
// private endpoint, and the roles that connect them.
//
// Why a new resource: the model account (environment/main.bicep) was made with allowProjectManagement false, and Microsoft Learn says that
// setting cannot be changed after the account exists (Create a project for Microsoft Foundry), so that account can never hold a project or an
// agent. It stays as it is and keeps serving the gateway.
//
// The agents call the deployments below directly, not through the gateway. That is a temporary exception to AGENTS.md rule 15 (c): the
// gateway's API Management instance is on the Developer tier, and the API Management connection that Foundry documents for agents needs the
// Standard v2 or the Premium tier and is in preview.
//
// No key, and nothing public (AGENTS.md rule 23):
//  - the resource has local authentication off (disableLocalAuth) and public network access off; it is reached through one private endpoint;
//  - the cases app signs in with its system-assigned managed identity (a Microsoft Entra token for https://ai.azure.com) and holds the Foundry User role on the
//    project, which lets it create agents and run them there, and nothing else here;
//  - the project's own managed identity sends the agents' traces to the Application Insights component with Microsoft Entra ID: it holds
//    Monitoring Metrics Publisher on the component, whose local authentication is off (environment/recording/main.bicep).
//
// Left out on purpose (AGENTS.md rule 19), because the landing zone provides it: private DNS zones, virtual network links and the private
// endpoint's DNS zone group. The landing zone's policy registers the endpoint in the central zones. The project endpoint's host name
// (<resource>.services.ai.azure.com) needs the zone privatelink.services.ai.azure.com, next to privatelink.cognitiveservices.azure.com and
// privatelink.openai.azure.com (Microsoft Learn, Set up private networking for Foundry Agent Service): the workflow waits for it and says so
// when it is not there.
//
// The order is on purpose. The resource accepts one write of its deployments at a time (batchSize 1), the project is made after the last
// deployment, and the private endpoint after every other write to the resource: a write to the resource while its private endpoint
// connection is written made an earlier deploy of the model account fail with IfMatchPreconditionFailed, and Microsoft's own template for a
// private Foundry resource makes the project first because a private endpoint bound before the resource has settled fails with
// AccountProvisioningStateInvalid. The roles come after the private endpoint.
//
// API versions: 2026-09-01, the newest stable one of Microsoft.CognitiveServices that has everything used here (the REST specification lists it; the guardrail's sources
// PostToolCall and the mode Blocking exist since 2025-12-01, projects and allowProjectManagement since 2025-06-01).
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "foundry" (AGENTS.md rule 18).
targetScope = 'resourceGroup'

@description('Region of every resource.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Name of the Foundry resource. It is also the host name, so it is unique worldwide: 2 to 64 characters, letters, digits and hyphens.')
@minLength(2)
@maxLength(64)
param accountName string

@description('Name of the project, where the agents live. It is part of the project endpoint.')
@minLength(2)
@maxLength(64)
param projectName string = 'meternaut'

@description('Name of the guardrail, the content safety policy that the model deployments use and the agents inherit from them.')
@minLength(2)
@maxLength(64)
param guardrailName string = 'meternaut-agents'

@description('Restore the soft-deleted resource of this name instead of creating a new one. The workflow sets it only after the platform reports that such a resource exists.')
param restoreAccount bool = false

@description('The models deployed in the resource: name, version, deployment type and capacity in thousands of tokens a minute. The workflow reads them from environment/models.json: the names, versions and deployment types are the ones of the model account and the gateway configuration, the capacity is the agentCapacity of the model, because an agent reads everything said so far again at every step and needs more tokens a minute than the gateway.')
param models array

@description('Principal id of the system-assigned identity of the cases app. It gets the Foundry User role on the project: it may create agents and run them there, and nothing else here. The workflow reads it from the app, and refuses to deploy this resource while the app has no such identity.')
@minLength(36)
@maxLength(36)
param casesSystemPrincipalId string

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

var tags = {
  workload: workload
  component: 'foundry-agents'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'foundry-core'
}

// Foundry User (named Azure AI User until the rename of the Foundry roles; the id is the same). Its data actions are Microsoft.CognitiveServices/*,
// which include agents/write and agents/read (create and read agents) and responses/write (run one). Given on the project, never on the resource
// or the group: its control plane actions (listkeys, deployments) then reach nothing.
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
// Monitoring Metrics Publisher: the one role that lets the project's identity send telemetry to the component with Microsoft Entra ID.
var monitoringMetricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

resource insights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: 'appi-${workload}'
}

resource account 'Microsoft.CognitiveServices/accounts@2026-09-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
    restore: restoreAccount
    networkAcls: {
      defaultAction: 'Deny'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

// The default guardrail of the models (Microsoft.DefaultV2) with the two Prompt Shields that an agent that reads tool results needs, both blocking:
// user prompt attacks (Jailbreak) on the user input, and indirect attacks (instructions hidden in text that the agent reads) on the user input and
// on the tool results (Prompt, and PostToolCall for agents). Tool response scanning is a preview feature of the Agent Service, and Learn lists the
// tools that support it (Azure AI Search, Azure Functions, OpenAPI and others): it may not apply to the function tools that the cases app runs itself.
// The answers of those tools hold typed values only (AGENTS.md rule 26 (d)), so this is a second layer and not the only one.
// Checked read-only against the service: Microsoft.DefaultV2 exists (mode Blocking), and Jailbreak and Indirect Attack are valid filter names at the source Prompt. Indirect Attack at
// PostToolCall is the control that Learn names for the tool response intervention point; whether the service takes it is read back after the deploy (tools/foundry-check.py).
resource guardrail 'Microsoft.CognitiveServices/accounts/raiPolicies@2026-09-01' = {
  parent: account
  name: guardrailName
  properties: {
    basePolicyName: 'Microsoft.DefaultV2'
    mode: 'Blocking'
    contentFilters: [
      { name: 'Jailbreak', source: 'Prompt', enabled: true, blocking: true }
      { name: 'Indirect Attack', source: 'Prompt', enabled: true, blocking: true }
      { name: 'Indirect Attack', source: 'PostToolCall', enabled: true, blocking: true }
    ]
  }
}

// One at a time: the resource accepts one deployment write at once. The same names, versions and types as the model account's, and the capacity that models.json gives the agents.
@batchSize(1)
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-09-01' = [for model in models: {
  parent: account
  name: model.name
  sku: {
    name: model.sku
    capacity: model.capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: model.name
      version: model.version
    }
    versionUpgradeOption: 'NoAutoUpgrade'
    raiPolicyName: guardrail.name
  }
}]

resource project 'Microsoft.CognitiveServices/accounts/projects@2026-09-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
    description: 'The agents of Meternaut: they look for waste in the pilot estate and judge what they find.'
  }
  dependsOn: [
    modelDeployment
  ]
}

resource projectPublishesTraces 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: insights
  name: guid(insights.id, project.id, monitoringMetricsPublisherRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringMetricsPublisherRoleId)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// The connection that makes the Agent Service send the agents' traces to the component, with the project's managed identity and no key. Microsoft's
// own templates (microsoft-foundry/foundry-samples) write authType ProjectManagedIdentity (their comment calls the value a preview), which the Bicep types do not list, and put the component's
// connection string in the metadata. That string names the component and holds no secret that ingestion accepts: local authentication of the
// component is off. A project has one connection of this category at most.
resource tracesConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-09-01' = {
  parent: project
  name: 'appi-${workload}'
  properties: {
    category: 'AppInsights'
    target: insights.id
    #disable-next-line BCP036
    authType: 'ProjectManagedIdentity'
    isSharedToAll: false
    metadata: {
      ApiType: 'Azure'
      ResourceId: insights.id
      ApplicationInsightsConnectionString: insights.properties.ConnectionString
    }
  }
  dependsOn: [
    projectPublishesTraces
  ]
}

// No privateDnsZoneGroups child: the landing zone's policy adds it (see the header).
resource privateEndpoint 'Microsoft.Network/privateEndpoints@2025-05-01' = {
  name: 'pe-${accountName}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-${workload}', 'snet-pe')
    }
    privateLinkServiceConnections: [
      {
        name: 'account'
        properties: {
          privateLinkServiceId: account.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
  dependsOn: [
    modelDeployment
    project
    tracesConnection
  ]
}

// After the private endpoint, not beside it (see the header).
resource casesMayUseTheAgents 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: project
  name: guid(project.id, casesSystemPrincipalId, foundryUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalId: casesSystemPrincipalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    privateEndpoint
  ]
}

@description('The project endpoint: the address that the cases app calls with its identity, through the private endpoint (an Entra token for https://ai.azure.com).')
output projectEndpoint string = 'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'

output accountName string = account.name
output projectName string = project.name
output guardrailName string = guardrail.name
output privateEndpointName string = privateEndpoint.name
