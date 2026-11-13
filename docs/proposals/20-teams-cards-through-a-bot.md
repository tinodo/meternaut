# Teams cards through a bot: an app principal, no user account, no secret — a decision record

**Status: a draft that is built and tested against fakes, off by default and not deployed, pending the owner's plain word that the order of 2026-11-11 against a bot and an app registration is lifted.** Until he says so nothing here runs: the setting `TEAMS_DELIVERY` of the function app stays `queue` (the Power Automate flow of [proposal 19](19-teams-cards-through-power-automate.md) delivers every card), no new Hub action runs unless it is started, and the repository holds no code that Teams can call. If he says no, this proposal is discarded. If he says yes and the bot is proven by the Hub action `teams-test`, it replaces proposal 19, which carries a banner that says so. Every Microsoft fact below names its page; the pages marked *read on 2026-11-13* were read that day for this proposal, and the others are the pages that the design brief of that day names, not read again here.

## The owner's words

On 2026-11-11, about an earlier bot: "Teams bot? What … teams bot? I didn't ask for a bot. I asked for team cards … I do NOT want any app registrations that need specific permissions." That bot was removed, and [rule 25](../../AGENTS.md) says so. On 2026-11-13, about the flow that proposal 19 built: a user account is for users, so no service user stands behind the flow; "A managed identity is acceptable", and apps use an app principal. This proposal is the design that follows from those words and stays inside what he objected to: no route that Teams or anybody calls, no code that validates a token that Microsoft sends, no permission in Microsoft Graph, no permission of any kind on the app registration, no installer of the Teams app, no separate function app and no public endpoint.

## What this is

The function app sends a card straight to a person's Teams chat. It asks Microsoft Entra for a token with its own identity, with no secret, and sends the card to the Bot Connector, Microsoft's service that delivers a bot's messages to Teams. Nothing is received: the bot is a *notification-only* bot, and its one registered address is never called.

| # | Step | Where it runs | Whose identity |
|---|---|---|---|
| 1 | The function app asks the platform for a token of the managed identity `id-meternaut-teams` for `api://AzureADTokenExchange`. | The function app, to the platform's identity endpoint. | The managed identity. |
| 2 | It gives that token to Microsoft Entra as the client assertion of the app registration *Meternaut Teams* and asks for a token for `https://api.botframework.com/.default`: the OAuth 2.0 client credentials flow, app only. | The function app, to `login.microsoftonline.com`. | The app registration, trusted by the identity through a federated credential. |
| 3 | It creates the 1:1 conversation with the approver (the approver's Microsoft Entra object id, from the list of people), then posts the Adaptive Card in it, and later replaces the card with a closing card when the request ends. | The function app, to the Bot Connector at `https://smba.trafficmanager.net/teams/`. | The app registration's token. |
| 4 | The person sees the card in a personal chat with the app *Meternaut*. | Teams. | None. |

The tenant of the app registration is the one of the function app's sign-in (its setting `SIGNIN_TENANT_ID`, which the app has only while its three sign-in settings are set together). Without it, or while the delivery is `bot` and the settings of the bot are incomplete, the way **fails closed**: no card is sent, the letters still go, and the Operations page says why. The two kill switches of the owner (`messages` and `all`) stop the cards on this way too. The card is the one of [proposal 13](13-teams-and-outlook.md): its buttons are links to a page of the function app, which sends the answer after the person's sign-in. Nothing is answered in Teams, so no code receives anything from it.

## The objects, and what each one holds

| Object | What it is | What it holds |
|---|---|---|
| The managed identity `id-meternaut-teams` | A user-assigned managed identity in the project's resource group, attached to the function app. Made by the Hub action `teams` ([the template](../../environment/teams/main.bicep)). | **No Azure role, anywhere.** The action reads its role assignments after every run and fails when there is one. |
| The app registration *Meternaut Teams* | One Microsoft Entra application, this tenant only (`AzureADMyOrg`), with its **service principal in the tenant** (without it Teams reports AADSTS7000229, "missing service principal in the tenant"). Made by `python tools/entra-setup.py teams-bot`, a hand step. | **No secret, no certificate, no API permission, no consent, no redirect address.** One federated credential. |
| The federated credential | On the app registration: issuer `https://login.microsoftonline.com/<tenant id>/v2.0`, subject the **object (principal) id** of the managed identity (a GUID, case-sensitive), audience `api://AzureADTokenExchange`. The app registration and the managed identity have to be in the same tenant. | A trust in one identity and nothing else. Microsoft accepts a wrong value when the credential is made, and it fails only at the first token exchange: the proof is `teams-test`. |
| The Azure Bot resource | `Microsoft.BotService/botServices`, kind `azurebot`, location `global`, API version 2022-09-15 (the latest that is not a preview), SKU F0 (the free one: the standard channels, Teams among them, carry an unlimited number of messages), `msaAppType: SingleTenant` (the type `UserAssignedMSI` is the legacy form and `MultiTenant` is deprecated), the app registration's client id, `disableLocalAuth: true`. Its `endpoint` is mandatory, and it is `https://<the function app's host name>/api/messages`: a route that does not exist. | A registration. It receives nothing, because the function app takes no public traffic and has no such route. |
| Its Microsoft Teams channel | `Microsoft.BotService/botServices/channels`, `MsTeamsChannel`, enabled, calling off. | Nothing else. |
| The Teams app | A package (`manifest.json` and two icons) that [`tools/teams-app.py`](../../tools/teams-app.py) builds outside the repository and a Teams administrator uploads to the organisation's app catalog: one bot, personal scope, notification only, no files. The tool installs nothing. | No permission of its own: no tab, no messaging extension, no sign-in. |

The template reference was read on 2026-11-13: [botServices](https://learn.microsoft.com/azure/templates/microsoft.botservice/botservices), [its channels](https://learn.microsoft.com/azure/templates/microsoft.botservice/botservices/channels) and the manifest [schema 1.30](https://learn.microsoft.com/microsoft-365/extensibility/schema/), the latest that Learn lists.

## Permissions

| Kind | What Meternaut has for this |
|---|---|
| Azure roles | **None** for the managed identity (rule 29: no identity of Meternaut holds a right that changes Azure). The deploy identity needs nothing new: Contributor on the project's group covers the identity and the bot, and no template gives a role. |
| Microsoft Graph | **None.** No application permission and no delegated one; nothing is read from the directory. |
| OAuth | App-only client credentials, scope `https://api.botframework.com/.default`. No delegated scope, no consent, no sign-in of a person. |
| The app registration | No API permission. |

## The network

The function app needs **outbound HTTPS to two hosts** through the landing zone's routing: `login.microsoftonline.com` and `smba.trafficmanager.net`. Nothing is inbound. Whether the landing zone's routing lets those two hosts through is **not known**: `teams-test` probes both from the Operator's subnet, in the same virtual network as the function app, and says which answered, so that a blocked firewall is found in the pipeline and not from a card that never arrives.

## What the app sends and keeps

The app sends one card for each request that needs a person, to the person who is asked, and a closing card when the request ends. The card holds what [proposal 13](13-teams-and-outlook.md) says, which the decision brief decides: the headline, the figures and the choices. The Bot Connector and Teams carry it. The app keeps, for each card, the ids of the conversation and of the message that Teams gave it, so that it can close the card; it keeps no text that a person writes, because it receives none. The app registration and the identity hold no secret and no permission. The source is open and the terms are [the licence](../../LICENSE).

## Guests

The owner is a guest (B2B) of the tenant. Microsoft says that a personal bot that an *app setup policy* preinstalls is **not** available to guests, and that a guest gets the app only if it is in the **global default** app setup policy, or if the guest adds it, through the app's deep link `https://teams.microsoft.com/l/app/<Teams app id>` (personal scope only) ([app setup policies](https://learn.microsoft.com/microsoftteams/teams-app-setup-policies), the page that the design brief names). The runbook covers both ways. A policy change can take hours to reach a person.

## What goes wrong, in plain words

| What | What it looks like | What a person does |
|---|---|---|
| The app is not installed for the person | The creation of the conversation answers 403 (`teams-test`: "create: NOT ok, 403, the Teams app is not installed for the owner"). | Add the app to the global default app setup policy, or send the deep link; wait. |
| The person or the organisation blocks the app | 403 again; `teams-test` says "blocks the app". | A Teams administrator allows the app in the Teams admin center. |
| A wrong subject, audience or issuer of the federated credential | The token exchange fails with an AADSTS code, which `teams-test` prints alone. | Make the credential again: `entra-setup.py teams-bot` says what differs and removes nothing. |
| The service principal is missing | AADSTS7000229. | `entra-setup.py teams-bot --apply` makes it. |
| The way out is blocked | A host gives no answer in the probe, and the token step reports "network". | Ask the landing zone's owners for the two hosts; this is a finding, and the owner decides. |
| Teams slows the app down | 429. | The app tries again later; a burst of cards is the cause. |

## What is not proved until `teams-test` has run

Nothing of this has run in Azure, Microsoft Entra or Teams. Not proved: that the Bot Connector accepts a proactive 1:1 for a **guest** of the tenant and creates the conversation without the person having started it (Microsoft documents proactive messages for an installed app, not for a guest in particular); that the landing zone's routing lets the function app reach the two hosts; that the update of a card (the PUT that closes it) works for a card that the bot created; that Azure accepts `disableLocalAuth` and `SingleTenant` together on an Azure Bot resource with the free SKU; that the live read-back finds each property at the path that the Hub step reads; that the token exchange works with the federated credential as made; and a card to a member of the tenant. The test sends one labelled card to the first person of the list of people who has the role owner, and replaces it with a closing card: four steps (the token exchange, the creation of the chat, the send and the update), each printed in plain words, and one last line. When the function app sent nothing at all, the last line says why in one word: the delivery is not `bot` or its settings are incomplete, there is no owner, a switch of the owner holds the cards, or its settings could not be read.

## The runbook

Each step says who does it. The owner starts the Hub actions.

1. **Hub `cases`**, once, with the new code: it attaches no identity yet and gives the function app its four new settings (empty, and `TEAMS_DELIVERY` is `queue`). **Hub `teams`, phase 1** (the secret `TEAMS_BOT_APP_ID` is empty): it makes the identity and prints, in plain words, that the Microsoft Entra step is next.
2. **The owner** runs `python tools/entra-setup.py teams-bot --tenant-id <tenant id> --subscription <subscription id> --resource-group <resource group>` (a dry run) and then adds `--apply`, with his own `az login`. The tool makes the app registration, its service principal and the one federated credential, reads everything back (no password, no key, one credential with the right values) and prints the client id to his terminal only.
3. **The owner** stores the client id as the secret `TEAMS_BOT_APP_ID` of the environment `hub`: `gh secret set TEAMS_BOT_APP_ID --env hub --repo tinodo/meternaut`. It is a secret and not a variable, because it is an identifier of the estate and GitHub does not mask a variable in the public log ([rule 18](../../AGENTS.md) (b)).
4. **A person** who may registers the resource provider once: `az provider register --namespace Microsoft.BotService`. **Hub `teams`, phase 2**: the Azure Bot resource and its Teams channel, read back (single tenant, the client id matches, calling off), and the identity's role assignments read: zero, as expected.
5. **A Teams administrator** builds the package with `python tools/teams-app.py build` (outside the repository), uploads it in the Teams admin center (Teams apps, Manage apps, Upload new app: the Teams Administrator or the Global Administrator may), and then either adds the app to the **global default app setup policy**, so that a guest gets it, or lets each guest open the deep link and add it. For the people of the tenant an app setup policy can install it for them, which does not reach a guest. Propagation can take hours.
6. **Hub `cases`** with the new settings (`TEAMS_DELIVERY` is still `queue`: the app is given the identity and the client ids and sends nothing through the bot), then **Hub `teams-test`**.
7. **Only after `teams-test` has passed:** the owner sets the variable `TEAMS_DELIVERY` of the environment `hub` to `bot` and runs `cases`.
8. **Later, and not in this change:** retire the Power Platform path.

## Going back

Set `TEAMS_DELIVERY` to `queue` and run `cases`: the cards go through the queue again, as before. Delete the app package in the Teams admin center. No action deletes the identity, the bot or the app registration: a person does, by hand, and none of them costs anything.

## What it costs

The identity and the app registration cost nothing. The bot is on the free SKU; its standard channels carry an unlimited number of messages ([Azure Bot Service pricing](https://azure.microsoft.com/pricing/details/bot-services/), the page that the design brief names). Nothing in it bills while it is idle.

## Sources

Read on 2026-11-13: [botServices](https://learn.microsoft.com/azure/templates/microsoft.botservice/botservices), [botServices/channels](https://learn.microsoft.com/azure/templates/microsoft.botservice/botservices/channels), [the app manifest schema](https://learn.microsoft.com/microsoft-365/extensibility/schema/) with its [developer](https://learn.microsoft.com/microsoft-365/extensibility/schema/root-developer?view=m365-app-1.30) and [description](https://learn.microsoft.com/microsoft-365/extensibility/schema/root-description?view=m365-app-1.30) objects, and [card actions](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-actions) (the domain of an `Action.OpenUrl` belongs in `validDomains`, or Teams says that the URL may lead to untrusted content; the package tool takes it from `CONSOLE_HOST_NAME` or `--valid-domain`). Named by the design brief of that day: [federated identity credentials on an app](https://learn.microsoft.com/entra/workload-id/workload-identity-federation-config-app-trust-managed-identity), [the Bot Framework's authentication](https://learn.microsoft.com/azure/bot-service/rest-api/bot-framework-rest-connector-authentication), [proactive messages](https://learn.microsoft.com/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages) and [app setup policies](https://learn.microsoft.com/microsoftteams/teams-app-setup-policies).
