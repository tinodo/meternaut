// The Foundry resource of the agents: the place where Meternaut's agents (Microsoft Foundry Agent Service, prompt agents) live and are run.
//
// What it holds: a Foundry resource (kind AIServices) that can hold projects, one project (meternaut) with the agents in it, the model
// deployments of environment/models.json, one guardrail (a content safety policy with Prompt Shields) that the deployments use and the agents
// inherit from them, a connection of the project to the Application Insights component of the first environment for the agents' traces, one
// private endpoint, and the roles that connect them. Only when the host name of the AI Gateway is given (aiGatewayHost), also a second connection of the project:
// to that gateway, with the project's own managed identity and no key, so that the agents can name their models `<connection>/<alias>`
// (docs/proposals/08-ai-gateway.md, step 2). Empty, which is the default, none of it is made and the template is as it was.
//
// Why a resource of its own: the first model account was made with allowProjectManagement false, and Microsoft Learn says that
// setting cannot be changed after the account exists (Create a project for Microsoft Foundry), so that account could never hold a project or an
// agent. Nothing called it, so it was removed on 2026-11-07 (the action retire-old); this resource serves the agents and the Detective and the Skeptic.
//
// The agents call their models through the connection to the AI Gateway (AGENTS.md rule 15 (c)) while the switch AGENTS_VIA_AI_GATEWAY in tools/environment-params.py is True, which it is since the owner's
// order of 2026-11-07: the workflow then passes the gateway's host name (aiGatewayHost) and this template makes the connection. With the switch False, which is the way back, no connection is made and the agents
// call the deployments below directly, which rule 15 (c) allows only as the owner's written exception. Whether the service takes the connection is shown by the first run of the action foundry with the switch on
// (docs/proposals/08-ai-gateway.md, step 2).
//
// No key, and nothing public (AGENTS.md rule 23):
//  - the resource has local authentication off (disableLocalAuth) and public network access off; it is reached through one private endpoint;
//  - the cases app signs in with its system-assigned managed identity (a Microsoft Entra token for https://ai.azure.com) and holds the Foundry User role on the
//    project, which lets it create agents and run them there, and nothing else here;
//  - the project's own managed identity sends the agents' traces to the Application Insights component with Microsoft Entra ID: it holds
//    Monitoring Metrics Publisher on the component, whose local authentication is off (environment/base/main.bicep);
//  - the Operator's identity (the tools that check the agents run with it, inside the network) holds the Foundry User role on the project too, while its object id is given
//    (operatorPrincipalId), and so does the project's own identity, for a continuous evaluation rule (docs/proposals/11-agent-harness-and-evaluation.md says why, and what each allows).
//
// Left out on purpose (AGENTS.md rule 19), because the landing zone provides it: private DNS zones, virtual network links and the private
// endpoint's DNS zone group. The landing zone's policy registers the endpoint in the central zones. The project endpoint's host name
// (<resource>.services.ai.azure.com) needs the zone privatelink.services.ai.azure.com, next to privatelink.cognitiveservices.azure.com and
// privatelink.openai.azure.com (Microsoft Learn, Set up private networking for Foundry Agent Service): the workflow waits for it and says so
// when it is not there.
//
// The order is on purpose. The resource accepts one write of its deployments at a time (batchSize 1), the project is made after the last
// deployment, and the private endpoint after every other write to the resource: a write to the resource while its private endpoint
// connection is written made an earlier deploy of the first model account fail with IfMatchPreconditionFailed, and Microsoft's own template for a
// private Foundry resource makes the project first because a private endpoint bound before the resource has settled fails with
// AccountProvisioningStateInvalid. The connection to the AI Gateway is one more such write: it comes after the connection for traces (one write at a
// time) and before the private endpoint. The roles come after the private endpoint.
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

@description('The models deployed in the resource: name, version, deployment type and capacity in thousands of tokens a minute. The workflow reads them from environment/models.json: the names, versions and deployment types are the ones that the AI Gateway reads too, the capacity is the agentCapacity of the model, because an agent reads everything said so far again at every step and needs more tokens a minute than the gateway.')
param models array

@description('Principal id of the system-assigned identity of the cases app. It gets the Foundry User role on the project: it may create agents and run them there, and nothing else here. The workflow reads it from the app, and refuses to deploy this resource while the app has no such identity.')
@minLength(36)
@maxLength(36)
param casesSystemPrincipalId string

@description('Principal id of the user-assigned identity of the Operator (id-meternaut-operator), which runs the tools that check the agents from inside the network: agents-drift, foundry-evals and foundry-redteam. It gets the Foundry User role on the project, and nothing else here: the narrowest built-in role that reads the agents and the connections and makes the evaluations. Empty, which is the default, no role is made: the workflow passes it only when the identity is there, so that this template still deploys on an estate that has no Operator yet.')
@maxLength(36)
param operatorPrincipalId string = ''

@description('Host name of the AI Gateway (the separate service that environment/aigateway/main.bicep makes), as the service reports it in properties.frontend.defaultHostname: under .ai.gateway.azure.com. The workflow reads it from the service and passes it only while the switch AGENTS_VIA_AI_GATEWAY in tools/environment-params.py is True. Empty: no connection to the gateway is made, and nothing here is different for an estate that has no gateway.')
@maxLength(253)
param aiGatewayHost string = ''

@description('The models of the AI Gateway that the connection lists, each with the name of its alias (the deployment\'s name, which is what an agent sends as the model) and the version of the model. The workflow reads them from environment/models.json. Used only with aiGatewayHost.')
param aiGatewayModels array = []

@description('Name of the connection to the AI Gateway. An agent names its model `<connection name>/<alias>`. Used only with aiGatewayHost; tools/environment-params.py (AIGATEWAY_CONNECTION_NAME) holds the same name, and a test holds the two together.')
@minLength(2)
@maxLength(64)
param aiGatewayConnectionName string = 'aigateway'

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

// The default guardrail of the models (Microsoft.DefaultV2) with the two Prompt Shields that an agent that reads tool results needs, both blocking (and, besides them, every filter that the audit initiative asks for: the block at contentFilters):
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
    // The preview initiative "Guardrail for Cognitive Services Deployments" (the audit assignment of environment/governance/main.bicep) looks for these filters by name and source, and its
    // policies read only the filters that this guardrail names itself, not those that it takes from Microsoft.DefaultV2: with the three Prompt Shields alone the drift check found nine of its
    // controls unmet. The names, the sources and the severity range are the initiative's (Azure/azure-policy, built-in policy set 5207647b-3e83-4e28-b836-c382cb5e2a2e); it takes Medium or High
    // for Hate, Sexual, Violence and Selfharm, and Medium is written here. Indirect Attack at PostToolCall is ours: the initiative has no control for it.
    // Not tried against the service yet: whether the Agent Service takes Indirect Attack Spotlighting at Prompt, and the other filters at these sources, with blocking. tools/foundry-check.py reads
    // every one of them back after the deploy (REQUIRED_FILTERS there is this list, and a test holds the two together), and the run fails when one is not as written here.
    contentFilters: [
      { name: 'Hate', source: 'Prompt', enabled: true, blocking: true, severityThreshold: 'Medium' }
      { name: 'Hate', source: 'Completion', enabled: true, blocking: true, severityThreshold: 'Medium' }
      { name: 'Sexual', source: 'Prompt', enabled: true, blocking: true, severityThreshold: 'Medium' }
      { name: 'Sexual', source: 'Completion', enabled: true, blocking: true, severityThreshold: 'Medium' }
      { name: 'Violence', source: 'Prompt', enabled: true, blocking: true, severityThreshold: 'Medium' }
      { name: 'Violence', source: 'Completion', enabled: true, blocking: true, severityThreshold: 'Medium' }
      { name: 'Selfharm', source: 'Prompt', enabled: true, blocking: true, severityThreshold: 'Medium' }
      { name: 'Selfharm', source: 'Completion', enabled: true, blocking: true, severityThreshold: 'Medium' }
      { name: 'Profanity', source: 'Prompt', enabled: true, blocking: true }
      { name: 'Profanity', source: 'Completion', enabled: true, blocking: true }
      { name: 'Protected Material Code', source: 'Completion', enabled: true, blocking: true }
      { name: 'Protected Material Text', source: 'Completion', enabled: true, blocking: true }
      { name: 'Jailbreak', source: 'Prompt', enabled: true, blocking: true }
      { name: 'Indirect Attack', source: 'Prompt', enabled: true, blocking: true }
      { name: 'Indirect Attack Spotlighting', source: 'Prompt', enabled: true, blocking: true }
      { name: 'Indirect Attack', source: 'PostToolCall', enabled: true, blocking: true }
    ]
  }
}

// One at a time: the resource accepts one deployment write at once. The names, versions and types of environment/models.json, and the capacity that models.json gives the agents.
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

// The connection that lets the agents call their models through the AI Gateway (docs/proposals/08-ai-gateway.md, step 2): made only when the host name of the gateway is given. An agent then names its model
// `<connection name>/<alias>`. It is the shape of Microsoft's own samples, with one difference that is not known to work and has not been tried:
//  - category ApiManagement with authType ProjectManagedIdentity, an audience and empty credentials is the sample for API Management (microsoft-foundry/foundry-samples,
//    infrastructure-setup-bicep/01-connections/apim), whose every example points at *.azure-api.net. The one sample for this service (01-connections/ai-gateway-tier) uses the category ModelGateway with an API key.
//    No key is used here (AGENTS.md rule 23): whether the service accepts this category for this target, and whether the Agent Service then calls the gateway with a token of the project's identity, is what the
//    first run shows. If it needs a key, the owner decides, and no template builds that path.
//  - the audience is the one that the gateway asks for (a Microsoft Entra token for https://azure-api.net/aigateway, and the role AI Gateway Models User on the gateway, which environment/aigateway/main.bicep gives
//    the project's identity when its object id is given).
//  - the target is the base of the gateway's OpenAI route (https://<host>/default/models/openai/v1): the Agent Service adds chat/completions, because Responses routing is not offered for this service yet (Learn, "Bring your own
//    model to Foundry Agent Service"), and the model goes in the request body (deploymentInPath false), where the alias is read. A static list of the models lets the runtime resolve `<connection>/<alias>` without a lookup.
//  - not shared to the other projects of the resource.
// The bicep types do not list the value ProjectManagedIdentity (the connection for traces is written the same way), and may not list audience either: the warnings are switched off on those two lines only.
// It is written after the connection for traces and before the private endpoint, like every other write to the resource (see the header): the resource accepts one write at a time.
var aiGatewayModelList = [for model in aiGatewayModels: {
  name: model.name
  properties: {
    model: {
      name: model.name
      version: model.version
      format: 'OpenAI'
    }
  }
}]

resource aiGatewayConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-09-01' = if (!empty(aiGatewayHost)) {
  parent: project
  name: aiGatewayConnectionName
  properties: {
    category: 'ApiManagement'
    target: 'https://${aiGatewayHost}/default/models/openai/v1'
    #disable-next-line BCP036
    authType: 'ProjectManagedIdentity'
    #disable-next-line BCP037
    audience: 'https://azure-api.net/aigateway'
    isSharedToAll: false
    credentials: {}
    metadata: {
      deploymentInPath: 'false'
      models: string(aiGatewayModelList)
    }
  }
  dependsOn: [
    tracesConnection
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
    aiGatewayConnection
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

// The Operator runs tools/agents-drift.py, tools/foundry-evals.py and tools/foundry-redteam.py from inside the network with its own identity, and without a role on the project they read nothing: the first real run of
// agents-drift (2026-11-08) was answered 403 for the agents and 401 for the connections. Foundry User is the narrowest built-in role that fits (Learn, "Role-based access control for Microsoft Foundry", read 2026-11-09): Foundry
// Agent Consumer holds the one data action that interacts with agent endpoints, and Foundry Project Runtime User only the responses; neither reads agents or connections, and neither makes an evaluation. So the Operator can
// also create, change, delete and run the agents of the project, which is wider than a reader needs. In Azure itself it is a reader (Learn's table: no creating of projects or accounts, no managing of models, no role assignments), and, as
// Learn says, a role on the project alone does not authorize model inference. Made only while the object id is given, and after the private endpoint, like the other roles. The way back is to delete the assignment.
resource operatorMayCheckTheAgents 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(operatorPrincipalId)) {
  scope: project
  name: guid(project.id, operatorPrincipalId, foundryUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalId: operatorPrincipalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    privateEndpoint
  ]
}

// A continuous evaluation rule runs as the project's own identity, and Learn ("Set up permissions for Microsoft Foundry evaluation workflows", read 2026-11-09) asks for Foundry User for it, at the Foundry resource or at the
// project: the project, which is the narrower. The scope of the resource, which Learn asks for when evaluation runs in an isolated resource, would let the identity call the deployments direct (AGENTS.md rule 15 (c)): it is not made here.
resource projectMayRunTheEvaluationRule 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: project
  name: guid(project.id, 'the-project-itself', foundryUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalId: project.identity.principalId
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
