// The governance of Meternaut's AI: Azure Policy at the project's resource group, the alert rules and the action group that tell the owner when something is wrong, the retention of the AI
// Gateway's telemetry tables, the workbook "Meternaut AI security", and, only where the landing zone has not made one, the diagnostic setting of the Foundry resource of the agents.
// Part of the AI security that the owner ordered (AGENTS.md rule 33, docs/proposals/10-ai-security-and-governance.md says what each part is, where a person sees it, what checks it and what it does not stop).
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "governance" (AGENTS.md rule 18). The telemetry exporter of the gateway is not here: environment/aigateway/telemetry.bicep makes it, by
// the action gateway-telemetry, because it has prerequisites of its own.
//
// What the landing zone gives already, and is not made again here (AGENTS.md rule 19: the landing zone's policies were read, the exemptions as well, on 2026-11-08):
//  - its guardrail sets for Cognitive Services and for Open AI (assignments enforce-gr-cogserv0 and enforce-gr-openai0, enforcement DoNotEnforce, so they report and refuse nothing) evaluate, for the Foundry
//    resource, local authentication off, public network access, network rules, private link, a managed identity, customer-owned storage and resource logs. The compliance of those is READ by the drift check
//    (tools/drift-check.py) and shown in the workbook; it is never assigned a second time, never exempted and never bypassed. A policy exemption is not made by this template, and a test pins that.
//  - its deploy-if-not-exists policy for resource logs makes the Foundry resource's diagnostic setting to the landing zone's central workspace. So the setting below is made only when the deployment workflow
//    has read that no such setting exists (landingZoneDiagnostics false), and then it sends to this project's own workspace.
//  - Defender for Cloud's AI plan is a plan of the subscription: it is read, never changed here. Microsoft lists Sweden Central as a region that it does not cover.
// What is added, because the landing zone has no policy for it:
//  - the built-in policy "Foundry model deployments should only use approved models", with the models of environment/models.json (a model asset id ends in a slash, which matches every version of that model),
//    and "Foundry model deployments should meet eligibility requirements" (models direct from Azure, none in preview). Both are evaluated when a deployment is written, and both take the effect Audit or Deny:
//    Audit until a run has shown every deployment compliant, then Deny, which is one line of tools/environment-params.py.
//  - the preview initiative "Guardrail for Cognitive Services Deployments", which can only audit and is behind a switch, because a preview feature is used only with a generally available fallback (AGENTS.md
//    rule 11 (i)): the fallback is the guardrail meternaut-agents on every deployment, which the drift check reads (the filters, each blocking) whatever this initiative says.
//  - optionally, "Azure AI Services resources should encrypt data at rest with a customer-managed key", with the kinds that it excludes by default (AIServices among them) emptied, so that the Foundry resource is
//    judged. It is off: the owner has not decided on customer-managed keys, which need a key vault with purge protection, and a Foundry resource with Microsoft-managed keys would show as non-compliant.
// All four assignments have the effect Audit or Deny and need no identity: Modify and DeployIfNotExists would need a role for the assignment's own identity, which this project does not give.
//
// The deploy identity needs the role Resource Policy Contributor at this resource group to write a policy assignment (Contributor cannot): a person gives it once (environment/BOOTSTRAP.md, tools/governance-setup.py), and
// the action reads for it before it changes anything.
//
// The alert rules read the workspace log-meternaut: the traces of the cases app (the table AppTraces: the lines `harness.trip` and `drift.fail`, and the heartbeat of the app's own drift check, which the app logs)
// and the AI Gateway's spans and logs (the tables OTelSpans and OTelLogs, which stay empty until the gateway's telemetry is on). One rule for each signal, every 15 minutes or longer, because a log alert rule that is
// evaluated that rarely is the cheapest kind (docs/proposals/10-ai-security-and-governance.md has the prices). A rule's e-mail carries the rule's name, a count and a link, and never a line of the telemetry: the queries
// return rows and nothing is shown of them in the message. The action group sends to the owner's addresses, ENV_ALERT_EMAILS, the same list as the budget.
//
// The workbook reads the same tables and Azure Resource Graph (policy compliance and the alert rules). The callers of the gateway are named from the access list (environment/aigateway/contracts.json) and the
// live object ids of their identities, which the deployment workflow reads from Azure and passes: no id of the estate is in the repository.
//
// No key, no private DNS object, no public endpoint and no new component: the workspace and the component are the base's.
targetScope = 'resourceGroup'

@description('Region of the alert rules and the workbook.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('E-mail addresses that receive the alerts: ENV_ALERT_EMAILS, the list that the budget uses.')
@minLength(1)
param alertEmails array

@description('Name of the Foundry resource of the agents (environment/foundry/main.bicep makes it). Only read: the diagnostic setting is made on it, when none exists.')
@minLength(2)
@maxLength(64)
param foundryAccountName string

@description('The asset ids of the approved models, one for each model of environment/models.json: azureml://registries/azure-openai/models/<name>/ (the trailing slash matches every version of that model and no other model).')
@minLength(1)
param approvedModelAssetIds array

@description('Effect of the approved-models policy. Audit until a run has shown every deployment compliant, then Deny. tools/environment-params.py sets it from the constant APPROVED_MODELS_EFFECT.')
@allowed([
  'Audit'
  'Deny'
])
param approvedModelsEffect string = 'Audit'

@description('Effect of the model eligibility policy (models direct from Azure, none in preview). tools/environment-params.py sets it from the constant MODEL_ELIGIBILITY_EFFECT.')
@allowed([
  'Audit'
  'Deny'
])
param modelEligibilityEffect string = 'Audit'

@description('Whether to assign the preview initiative "Guardrail for Cognitive Services Deployments" (Audit only). The workflow passes false when the tenant does not offer the initiative, and the constant GUARDRAIL_INITIATIVE_PREVIEW of tools/environment-params.py is the switch.')
param guardrailInitiative bool = false

@description('Whether to assign the customer-managed key policy, with the kinds that it excludes by default emptied so that the Foundry resource is judged. Off: the owner has not decided on customer-managed keys. tools/environment-params.py sets it from the constant AUDIT_CUSTOMER_MANAGED_KEYS.')
param auditCustomerManagedKeys bool = false

@description('True when a diagnostic setting of the Foundry resource that sends to a workspace exists already (the landing zone\'s policy makes one). The template then makes none (AGENTS.md rule 19). The deployment workflow reads it from Azure.')
param landingZoneDiagnostics bool = false

@description('The callers of the AI Gateway that the access list (environment/aigateway/contracts.json) names, each with the name of the caller, the object id of its identity and the aliases that it may call: [{"name": "...", "objectId": "...", "aliases": ["..."]}]. The workflow reads each object id from Azure. Empty: the rule that watches for a call outside the access list is not made, and the workbook names no caller.')
param callers array = []

@description('The token limit of the gateway for each caller in one minute, from environment/aigateway/policies.json.')
@minValue(1)
param tokenLimitPerMinute int = 50000

@description('The request limit of the gateway for each caller in one minute, from environment/aigateway/policies.json.')
@minValue(1)
param requestLimitPerMinute int = 60

@description('Percent of a limit at which a minute of use is reported. 80 is the owner\'s line for the limits and for the budget.')
@minValue(1)
@maxValue(100)
param nearLimitPercent int = 80

@description('Refused requests (403 and 429) in one hour at which the rule fires. A starting value: a well formed request that the gateway refuses should be rare, so three in an hour is already an event.')
@minValue(1)
param refusalsPerHour int = 3

@description('Client errors (400, 401 and 404) in one hour at which the rule fires. A starting value.')
@minValue(1)
param clientErrorsPerHour int = 10

@description('Server errors (500 and above) in half an hour at which the rule fires. A starting value.')
@minValue(1)
param serverErrorsPerHalfHour int = 3

@description('Hours without a drift.pass or a drift.fail line of the app\'s own drift check after which the heartbeat rule fires. The check runs daily, so 26 is a day and two hours of slack.')
@minValue(2)
@maxValue(48)
param heartbeatHours int = 26

@description('Days that the AI Gateway\'s telemetry tables keep their data: the retention is capped at the workspace\'s own 30 days and written down, so that nothing is archived (and billed) for longer.')
@minValue(4)
@maxValue(31)
param telemetryRetentionDays int = 30

var tags = {
  workload: workload
  component: 'ai-security'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'ai-security'
}

// Built-in policy and initiative definitions (Azure Policy, read on 2026-11-08 in github.com/Azure/azure-policy and on Learn). They are definitions of the tenant's own built-in set, so their ids are the same everywhere.
var approvedModelsDefinition = '/providers/Microsoft.Authorization/policyDefinitions/aafe3651-cb78-4f68-9f81-e7e41509110f'
var modelEligibilityDefinition = '/providers/Microsoft.Authorization/policyDefinitions/8791d062-ba96-4c34-b604-8538f7e30ca0'
var guardrailInitiativeDefinition = '/providers/Microsoft.Authorization/policySetDefinitions/5207647b-3e83-4e28-b836-c382cb5e2a2e'
var customerManagedKeyDefinition = '/providers/Microsoft.Authorization/policyDefinitions/67121cc7-ff39-4ab8-b7e3-95b84dab487d'

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: 'log-${workload}'
}

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

// Azure Policy at this resource group. Audit and Deny only (the assignments carry no identity), and never an exemption.
resource approvedModels 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'meternaut-approved-models'
  properties: {
    displayName: 'Meternaut: model deployments only of the approved models'
    description: 'Only the models of environment/models.json may be deployed in this resource group. Audit shows a deployment of another model; Deny refuses it.'
    policyDefinitionId: approvedModelsDefinition
    enforcementMode: 'Default'
    parameters: {
      effect: {
        value: approvedModelsEffect
      }
      allowedPublishers: {
        value: []
      }
      allowedAssetIds: {
        value: approvedModelAssetIds
      }
    }
    nonComplianceMessages: [
      {
        message: 'A model deployment of this resource group is not one of the approved models of environment/models.json.'
      }
    ]
  }
}

resource modelEligibility 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'meternaut-model-eligibility'
  properties: {
    displayName: 'Meternaut: model deployments only of models direct from Azure and not in preview'
    description: 'A model deployment of this resource group has to be a model sold directly by Azure and may not be a preview model.'
    policyDefinitionId: modelEligibilityDefinition
    enforcementMode: 'Default'
    parameters: {
      effect: {
        value: modelEligibilityEffect
      }
      onlyAllowDirectFromAzure: {
        value: true
      }
      denyPreviewModels: {
        value: true
      }
    }
    nonComplianceMessages: [
      {
        message: 'A model deployment of this resource group is not a model direct from Azure, or it is a preview model.'
      }
    ]
  }
}

// A preview initiative that can only audit: every content filter of a deployment's guardrail against Microsoft's own default settings. Behind a switch (the generally available fallback is the guardrail meternaut-agents,
// whose filters the drift check reads one by one).
resource guardrailAudit 'Microsoft.Authorization/policyAssignments@2024-04-01' = if (guardrailInitiative) {
  name: 'meternaut-guardrail-audit'
  properties: {
    displayName: 'Meternaut: the guardrail of every model deployment against the default settings (preview, audit only)'
    description: 'Audits the content filters of the guardrail that the model deployments use (preview initiative: it can only audit).'
    policyDefinitionId: guardrailInitiativeDefinition
    enforcementMode: 'Default'
    parameters: {
      effect: {
        value: 'Audit'
      }
    }
  }
}

resource customerManagedKeys 'Microsoft.Authorization/policyAssignments@2024-04-01' = if (auditCustomerManagedKeys) {
  name: 'meternaut-cmk-audit'
  properties: {
    displayName: 'Meternaut: the Foundry resource encrypts its data with a customer-managed key (audit)'
    description: 'The built-in policy leaves the kind AIServices out by default; the list of excluded kinds is empty here, so the Foundry resource is judged.'
    policyDefinitionId: customerManagedKeyDefinition
    enforcementMode: 'Default'
    parameters: {
      effect: {
        value: 'Audit'
      }
      excludedKinds: {
        value: []
      }
    }
  }
}

// The Foundry resource's logs (audit, request and response metadata, usage: not the prompts and the answers) to this project's workspace, only where the landing zone's policy has not made a setting.
resource foundryLogs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!landingZoneDiagnostics) {
  name: 'meternaut-foundry-to-workspace'
  scope: account
  properties: {
    workspaceId: workspace.id
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}

// The AI Gateway's telemetry tables keep 30 days, as the workspace does, and nothing is archived: the retention is written down so that a table never gets a longer one by accident (each month beyond the
// workspace's own costs money). The tables exist in every workspace, so these are updates of a table that is there.
resource spansRetention 'Microsoft.OperationalInsights/workspaces/tables@2023-09-01' = {
  parent: workspace
  name: 'OTelSpans'
  properties: {
    retentionInDays: telemetryRetentionDays
    totalRetentionInDays: telemetryRetentionDays
  }
}

resource logsRetention 'Microsoft.OperationalInsights/workspaces/tables@2023-09-01' = {
  parent: workspace
  name: 'OTelLogs'
  properties: {
    retentionInDays: telemetryRetentionDays
    totalRetentionInDays: telemetryRetentionDays
  }
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${workload}-ai-security'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'mtn-aisec'
    enabled: true
    emailReceivers: [for (address, index) in alertEmails: {
      name: 'owner-${index + 1}'
      emailAddress: address
      useCommonAlertSchema: true
    }]
  }
}

// The lines of the access list and of the names of the callers, as text for a Kusto datatable: the object ids are lower case, as the oid claim of a token is.
var accessListRows = flatten(map(callers, caller => map(caller.aliases, alias => '\'${toLower(caller.objectId)}\', \'${alias}\'')))
var accessList = join(accessListRows, ',\n')
var callerRows = join(map(callers, caller => '\'${toLower(caller.objectId)}\', \'${caller.name}\''), ', ')

var refusalsQuery = loadTextContent('alerts/refusals.kql')
var clientErrorsQuery = loadTextContent('alerts/client-errors.kql')
var serverErrorsQuery = loadTextContent('alerts/server-errors.kql')
var nearLimitQuery = replace(replace(replace(loadTextContent('alerts/near-limit.kql'), '__NEAR_PERCENT__', string(nearLimitPercent)), '__TOKEN_LIMIT__', string(tokenLimitPerMinute)), '__REQUEST_LIMIT__', string(requestLimitPerMinute))
var outsideAccessListQuery = replace(loadTextContent('alerts/outside-access-list.kql'), '__ACCESS_LIST__', accessList)
var harnessTripsQuery = loadTextContent('alerts/harness-trips.kql')
var driftFailQuery = loadTextContent('alerts/drift-fail.kql')
var driftHeartbeatQuery = replace(loadTextContent('alerts/drift-heartbeat.kql'), '__HEARTBEAT_HOURS__', string(heartbeatHours))

// One rule for each signal, evaluated every 15 minutes or less often (the cheapest kind of log alert rule). The window is as long as the interval, so that a row is counted once; the heartbeat looks back two days
// and counts a window of its own inside the query. Severity 1 is for what is a breach or a stopped control, 2 for what is a warning.
var rules = [
  {
    name: 'refusals'
    display: 'AI Gateway: refused requests above the normal band'
    text: 'The AI Gateway refused well formed requests (403 for content safety, a cost limit or a missing role, 429 for a token or request limit) more often than the normal band. Open the workbook Meternaut AI security.'
    severity: 2
    frequency: 'PT1H'
    window: 'PT1H'
    operator: 'GreaterThanOrEqual'
    threshold: refusalsPerHour
    query: refusalsQuery
    create: true
  }
  {
    name: 'client-errors'
    display: 'AI Gateway: client errors above the normal band'
    text: 'The AI Gateway answered with 400, 401 or 404 more often than the normal band: a caller that is wrong, a model that moved, or somebody calling without an identity. Open the workbook Meternaut AI security.'
    severity: 2
    frequency: 'PT1H'
    window: 'PT1H'
    operator: 'GreaterThanOrEqual'
    threshold: clientErrorsPerHour
    query: clientErrorsQuery
    create: true
  }
  {
    name: 'server-errors'
    display: 'AI Gateway: server errors'
    text: 'The AI Gateway answered with a server error (500 and above): the gateway or the model deployment behind it failed. Open the workbook Meternaut AI security.'
    severity: 2
    frequency: 'PT30M'
    window: 'PT30M'
    operator: 'GreaterThanOrEqual'
    threshold: serverErrorsPerHalfHour
    query: serverErrorsQuery
    create: true
  }
  {
    name: 'near-limit'
    display: 'AI Gateway: a caller used most of a limit in one minute'
    text: 'In one minute a caller used at least ${nearLimitPercent} percent of the token limit or of the request limit of the AI Gateway. Open the workbook Meternaut AI security.'
    severity: 2
    frequency: 'PT15M'
    window: 'PT15M'
    operator: 'GreaterThan'
    threshold: 0
    query: nearLimitQuery
    create: true
  }
  {
    name: 'outside-access-list'
    display: 'AI Gateway: a call outside the access list'
    text: 'The AI Gateway answered a call from a caller or for an alias that the access list (environment/aigateway/contracts.json) does not name. If an identity was made again, run the action governance again.'
    severity: 1
    frequency: 'PT1H'
    window: 'PT1H'
    operator: 'GreaterThan'
    threshold: 0
    query: outsideAccessListQuery
    create: !empty(callers)
  }
  {
    name: 'harness-trips'
    display: 'Agent harness: an agent run was stopped'
    text: 'A limit, a check or a guard of the agent harness stopped an agent run (a line that starts with harness.trip). Open the workbook Meternaut AI security.'
    severity: 1
    frequency: 'PT15M'
    window: 'PT15M'
    operator: 'GreaterThan'
    threshold: 0
    query: harnessTripsQuery
    create: true
  }
  {
    name: 'drift-fail'
    display: 'Drift check: a control of the app failed'
    text: 'A control of the app\'s own daily drift check failed (a line that starts with drift.fail). Open the workbook Meternaut AI security, or run the Hub action drift-check.'
    severity: 1
    frequency: 'PT1H'
    window: 'PT1H'
    operator: 'GreaterThan'
    threshold: 0
    query: driftFailQuery
    create: true
  }
  {
    name: 'drift-heartbeat'
    display: 'Drift check: the app\'s own check is silent'
    text: 'No drift.pass or drift.fail line was logged by the app\'s own daily drift check for ${heartbeatHours} hours: the check is not running. Run the Hub action drift-check, which does not depend on the app.'
    severity: 1
    frequency: 'PT1H'
    window: 'P2D'
    operator: 'GreaterThan'
    threshold: 0
    query: driftHeartbeatQuery
    create: true
  }
]

resource alertRules 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = [for rule in rules: if (rule.create) {
  name: 'alert-${workload}-ai-${rule.name}'
  location: location
  tags: tags
  kind: 'LogAlert'
  properties: {
    displayName: rule.display
    description: rule.text
    severity: rule.severity
    enabled: true
    evaluationFrequency: rule.frequency
    windowSize: rule.window
    scopes: [
      workspace.id
    ]
    targetResourceTypes: [
      'Microsoft.OperationalInsights/workspaces'
    ]
    criteria: {
      allOf: [
        {
          query: rule.query
          timeAggregation: 'Count'
          operator: rule.operator
          threshold: rule.threshold
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    autoMitigate: false
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
  }
}]

// The workbook: anyone who may read the workspace may open it in the Azure portal. Its placeholders are filled here: the workspace, this resource group and its subscription (as resource ids, which the workbook
// needs and which nothing keeps in the repository), the callers' names, and the numbers of the limits.
resource aiSecurityWorkbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: guid(resourceGroup().id, 'meternaut-ai-security')
  location: location
  kind: 'shared'
  tags: tags
  properties: {
    displayName: 'Meternaut AI security'
    category: 'workbook'
    version: '1.0'
    sourceId: workspace.id
    serializedData: replace(replace(replace(replace(replace(replace(replace(replace(loadTextContent('ai-security.workbook.json'), '__WORKSPACE_ID__', workspace.id), '__RESOURCE_GROUP__', resourceGroup().name), '__SUBSCRIPTION_RESOURCE__', subscription().id), '__CALLERS__', callerRows), '__TOKEN_LIMIT__', string(tokenLimitPerMinute)), '__REQUEST_LIMIT__', string(requestLimitPerMinute)), '__NEAR_PERCENT__', string(nearLimitPercent)), '__HEARTBEAT_HOURS__', string(heartbeatHours))
  }
}

output actionGroupName string = actionGroup.name
output alertRuleNames array = [for rule in filter(rules, candidate => candidate.create): 'alert-${workload}-ai-${rule.name}']
output workbookName string = aiSecurityWorkbook.name
