// The Azure side of Teams cards that go straight from the cases app to Teams, through the Bot Connector, with an app principal
// (docs/proposals/20-teams-cards-through-a-bot.md). It is an alternative to the queue and the Power Automate flow of proposal 19, it is off until the owner switches it on
// (the setting TEAMS_DELIVERY of the cases app is `queue` until then), and it is a notification-only bot: nothing is ever received, so the cases app has no route for Teams to call.
//
// Two phases, in one deployment, because the order of the objects is fixed by what depends on what:
//   phase 1 (botAppId empty):  the user-assigned managed identity id-<workload>-teams, and nothing else. The identity has to exist before the app registration "Meternaut Teams" can trust it:
//                              the owner runs `python tools/entra-setup.py teams-bot` (a hand step; Microsoft Entra is not Azure Resource Manager and the deploy identity holds no right there), which
//                              makes the app registration, its service principal and one federated identity credential whose subject is this identity's object id, and prints the app registration's
//                              client id.
//   phase 2 (botAppId set):    the client id goes into the secret TEAMS_BOT_APP_ID of the environment hub, and this template then also makes the Azure Bot resource (kind azurebot, single tenant, with that
//                              client id) and its Microsoft Teams channel.
//
// What the identity is for. The cases app presents a token of this identity for api://AzureADTokenExchange as the client assertion, and Microsoft Entra gives it a token of the app registration for
// https://api.botframework.com/.default (the OAuth 2.0 client credentials flow: app only, no delegated scope, no consent, no secret, no certificate). That token goes to the Bot Connector. The identity holds
// NO role anywhere (AGENTS.md rule 29): this template makes no role assignment, and the Hub action `teams` reads the identity's role assignments after the deploy and fails when there is one. The identity is
// user-assigned and not system-assigned because the app registration's federated credential names its object id, which has to exist before the app can be told about it, and because it is the one thing that
// is attached to the cases app for this and nothing else.
//
// What the bot resource is. A registration that tells the Bot Connector and Teams which Microsoft Entra application the bot is. msaAppType is SingleTenant: the type UserAssignedMSI is the legacy form (it
// asks for an identity of the bot resource itself and a role on the channel) and MultiTenant is deprecated (https://learn.microsoft.com/azure/bot-service/bot-service-resources-faq-security). The property
// endpoint is mandatory (Learn, Microsoft.BotService/botServices, API version 2022-09-15, read 2026-11-13) and has to be an https address. It names the route /api/messages of the cases app, which does not exist: the
// cases app takes no public traffic, and a notification-only bot is never called. Nothing in Teams reaches it, and no code of the app validates a token that Microsoft sends (there is none to validate). The host
// name comes from the function app, which the workflow reads from Azure and masks (a parameter, never printed). disableLocalAuth is true: the bot is reached with Microsoft Entra only (AGENTS.md rule 23).
// The price: the SKU F0 is the free one, and the standard channels, Microsoft Teams among them, carry an unlimited number of messages (https://azure.microsoft.com/pricing/details/bot-services/); S1 is
// the paid one for premium channels and is allowed here for the case that a subscription refuses a second F0.
//
// The API version is 2022-09-15, the latest one that is not a preview (the page lists 2023-09-15-preview as the latest). It has every property used here: disableLocalAuth, msaAppTenantId, msaAppType SingleTenant.
// The Microsoft Teams channel is the child resource `MsTeamsChannel` with channelName MsTeamsChannel; isEnabled is the one required property of its body, and calling is off.
//
// Left out on purpose: role assignments of any kind (the identity holds none), a Graph permission, a private endpoint, a private DNS object, a key, and any other channel. The Teams app (its package, and its
// installation for the people) is not an Azure object: tools/teams-app.py builds the package, and a Teams administrator uploads it.
//
// Deployed only by the workflow .github/workflows/deploy-hub.yml, action "teams" (AGENTS.md rule 18). It makes no change to the cases app: the action `cases` attaches the identity and gives the app its settings.
targetScope = 'resourceGroup'

@description('Region of the identity. The Bot Service is a global resource, and its location is written as global below.')
param location string = resourceGroup().location

@description('Short name of the workload, used in resource names and tags.')
param workload string = 'meternaut'

@description('Owner of the resources, as a tag.')
@minLength(1)
param owner string

@description('Client id of the Microsoft Entra app registration "Meternaut Teams" (a GUID), which tools/entra-setup.py teams-bot makes. Empty: phase 1, and only the identity is made.')
param botAppId string = ''

@description('Name of the Azure Bot resource, the same on every run: bot-<workload>-<eight characters of the digest of the subscription and the resource group>, which is how the other resources with a global name are named. Used in phase 2 only.')
@maxLength(64)
param botName string = 'bot-meternaut'

@description('The host name of the cases app, as Azure reports it (properties.defaultHostName of the site), which the workflow reads from Azure and masks. The bot\'s mandatory endpoint is https://<this host name>/api/messages, a route that does not exist: the bot is notification-only and nothing is ever received. Used in phase 2 only, where it is required.')
param functionAppHost string = ''

@description('The SKU of the Azure Bot resource. F0 is the free one; the standard channels, Microsoft Teams among them, carry an unlimited number of messages on it. S1 is the paid one, for premium channels.')
@allowed([
  'F0'
  'S1'
])
param botSku string = 'F0'

var tags = {
  workload: workload
  component: 'teams'
  environment: 'dev'
  owner: owner
  'meternaut-stage': 'teams-bot'
}

// Phase 2 asks for the bot, and only then are the app registration's client id and the app's host name needed.
var botIsWanted = !empty(botAppId)

// User-assigned, so that its object id exists before the app registration names it in a federated credential. It holds no role.
resource teamsIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workload}-teams'
  location: location
  tags: tags
}

// kind azurebot is the Azure Bot resource. SingleTenant: only this tenant's application. The endpoint is a registration value that nothing calls.
resource bot 'Microsoft.BotService/botServices@2022-09-15' = if (botIsWanted) {
  name: botName
  location: 'global'
  kind: 'azurebot'
  sku: {
    name: botSku
  }
  tags: tags
  properties: {
    displayName: 'Meternaut'
    description: 'AI-written recommendations for Azure cost savings. A person approves every change. It only sends cards and never receives anything.'
    endpoint: 'https://${functionAppHost}/api/messages'
    msaAppId: botAppId
    msaAppType: 'SingleTenant'
    msaAppTenantId: tenant().tenantId
    disableLocalAuth: true
  }
}

// The Microsoft Teams channel, with calling off: the bot sends cards in a personal chat and does nothing with calls.
resource teamsChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = if (botIsWanted) {
  parent: bot
  name: 'MsTeamsChannel'
  location: 'global'
  properties: {
    channelName: 'MsTeamsChannel'
    properties: {
      isEnabled: true
      enableCalling: false
    }
  }
}

output identityName string = teamsIdentity.name
output identityId string = teamsIdentity.id
@description('Object (principal) id of the identity: the subject of the federated credential, and the id whose role assignments the workflow reads (there must be none).')
output identityPrincipalId string = teamsIdentity.properties.principalId
@description('Client id of the identity: the app setting TEAMS_BOT_IDENTITY_CLIENT_ID of the cases app.')
output identityClientId string = teamsIdentity.properties.clientId
output botName string = botIsWanted ? botName : ''
