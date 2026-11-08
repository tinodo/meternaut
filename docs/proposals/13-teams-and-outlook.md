# Teams and Outlook: a card in Teams, a letter in Outlook — a decision record

**Status: built, not deployed, and not run in Teams or in Azure. The Hub action `teams` is in the workflow ([`deploy-hub.yml`](../../.github/workflows/deploy-hub.yml)); it refuses to start unless the owner has asked in writing for a public endpoint (the input `public_teams_bot_requested`) and the line `TEAMS_BOT_ENABLED=True` is in `local/hub-local.env` (absent until he says so). Whether a card reaches a person is not proven until the first card arrives. Microsoft facts below name their page and status, read on 2026-11-08.**

## What a person sees

**In Teams** the app "Meternaut (AI)" sends a card into the personal chat, by [the card rules](../experience/04-messages-and-cards.md): the headline, the saving with its level and basis, three facts each with its source, one line each for the change, the undo and the risk, the buttons, one box "Ask or tell", and one footer line (written by an AI, why you got this, whom to talk to). The only link is the page of the request. A change has one button, "Review and decide", which opens the page: signing in to Azure and approving happen there. Advice has "Worth acting on", "Not worth it", "This is not mine" and "Decide later". A message typed to the app gets one plain line. Adding the app gets one welcome card. Someone who is not on the list of people gets a plain refusal.

**Who gets a card.** The person's channel setting decides (`email`, `teams`, `desk`). With `teams` the card goes first, and the letter follows only if no card was sent within 20 minutes; a card and a letter never both go for one request. A card that could not be sent is tried every 15 minutes, up to 12 times. Advice cards count against the weekly budget of letters.

**In Outlook** nothing changes: the letters from the shared mailbox stay, as the audit-safe fallback. Outlook actionable messages are not built. Since 2026-06-08 only Microsoft Entra tokens are accepted, which needs an app registration with an exposed API, a pre-authorised Microsoft app and a tenant-wide consent; the recipient needs an individual mailbox, a shared mailbox as sender is not a documented scenario, and the endpoint would be a second public one ([Entra token](https://learn.microsoft.com/outlook/actionable-messages/enable-entra-token-for-actionable-messages)).

## What is public, and how it is kept narrow

One function app of its own is public: its one function route, `POST /api/messages`; its deployment site, which takes only an Azure token (basic authentication is off) and is where the Hub publishes the code (private apps are published from inside the network); and the host's own endpoints, which refuse a caller with no key. The web page, the Watch and the cases app stay private.

- **Two functions only.** [`tools/build-teams-bot.sh`](../../tools/build-teams-bot.sh) puts the bot's entry ([`teams_function_app.py`](../../src/case-functions/teams_function_app.py)) in place of the cases app's: the messaging route and the timer that offers cards. No console route, no Watch, no loop timer.
- **The token first** ([`botauth.py`](../../src/case-functions/cases/botauth.py)): RS256 only, the issuer, the audience (the bot's app id), the expiry with five minutes of skew, the `serviceUrl` claim equal to the activity's, the channel `msteams` endorsed. The keys come from Microsoft's OpenID metadata, refreshed every six hours and on an unknown key id. A failing call gets 401 or 403 and an empty body.
- **A genuine call cannot approve a change.** An approval that changes Azure is never taken from Teams: the card's only link is the page, where the person signs in to Azure and Azure checks the person's own rights. A card records only answers that change nothing in Azure, for a person on the list, with the plan's code and a one-time token that the server made for that person and that plan. A forged call could at most record one such answer for a listed person, and needs a plan id, its code and a live token.
- **No key, no secret.** The bot's own identity holds no role. The app's system identity holds the four storage roles of an identity-based host and the loop's tables, and no right to read or change the estate. At most two instances.
- **Narrowing by address is not proved.** The service tag `AzureBotService` exists ([service tags](https://learn.microsoft.com/azure/virtual-network/service-tags-overview), GA), but Microsoft names it for the Direct Line channel, and the [security FAQ](https://learn.microsoft.com/azure/bot-service/bot-service-resources-faq-security) says that allow-listing inbound addresses is not supported. The template has the tag behind the parameter `restrictInboundToBotService`, off: it is turned on only with a card at hand, and off again if a tap stops arriving.

## The bot is a managed identity: one outbound flow

The Azure Bot resource has the app type `UserAssignedMSI`. The bot is the user-assigned identity `id-meternaut-teams-bot`: its client id is the bot's app id, the audience of every token that Teams sends and the `botId` of the Teams app. For the token to the Bot Connector the app asks the platform's identity endpoint for the resource `https://api.botframework.com` with that client id; [Authenticate requests with the Bot Connector API](https://learn.microsoft.com/azure/bot-service/rest-api/bot-framework-rest-connector-authentication) describes exactly this flow for this app type (GA). The page's other flow, a federated credential on an app registration, is for `SingleTenant` and is not used. So the bot needs no secret, certificate, federated credential or app registration.

## The verifier is hand-written

The Bot Framework SDK is archived and unsupported since 2025-12-31 ([resources](https://learn.microsoft.com/azure/bot-service/bot-service-resources-links-help)), the Python Agents SDK has no routing for `Action.Execute`, which the cards use, and no vetted token or RSA library is on an approved feed. So the protocol is on the standard library. The RS256 check follows RFC 8017, sections 8.2.2 and 9.2: it rejects a signature as large as the modulus, rebuilds the whole encoded message and compares it with the signature's in constant time, parses no padding, and needs a modulus of at least 2,048 bits and an exponent of at least 65,537. It is tested against OpenSSL known answers, real Bot Framework keys, the classic forgeries and crafted tokens (expired, wrong audience, issuer or service URL, unknown key, `alg` none or HS256). Hand-written code at a public door needs a security review before it is merged, and a vetted library replaces it when one is on an approved feed.

## What each answer does

| Tap | What is recorded | Changes Azure |
|---|---|---|
| Review and decide (a change) | nothing: it opens the page | the approval on the page, with the person's own sign-in |
| Worth acting on (advice) | "worth acting on" | no |
| Not worth it | declined; the request is closed | no |
| This is not mine | recorded; nothing is approved | no |
| Decide later | noted; the request stays open | no |
| Ask or tell | the person's words (300 characters at most), with the name | no |

Each tap goes through the decider that the page's form uses, and the card is replaced, in the response, by one that says what was recorded. A person who may not answer, a closed or expired request and a used one-time token each get one plain line, and nothing is recorded.

## Costs

The Azure Bot resource is the free tier (F0); the app is on Flex Consumption and scales to zero. Retail Prices API, `swedencentral`, read 2026-11-08: 0.000026 US dollars a GB-second after 100,000 free GB-seconds a month. The timer every minute is about 21,600 GB-seconds and 43,200 executions a month, inside the free grants, so an idle bot costs about 0. With no instance kept warm, the first tap after an idle time waits for a start and Teams may show it as failed; one always-ready 512 MB instance (`alwaysReadyInstances`) is about 5.2 dollars a month.

## What a person does by hand, in order

The owner:
1. Asks in writing for a public Teams bot ([AGENTS.md rule 15 (c)](../../AGENTS.md)).
2. Registers the resource provider once, because the workflow's identity cannot: `az provider register --namespace Microsoft.BotService`.
3. Adds the line `TEAMS_BOT_ENABLED=True` to `local/hub-local.env`.
4. Runs the Hub actions `model-side`, `base` and `cases` if they have not run, then `python tools/hub-local.py teams --public-teams-bot-requested --yes`. It deploys, builds, publishes, reads everything back and knocks at the public door with no token ([`tools/teams-check.py`](../../tools/teams-check.py)); it prints the bot's client id.
5. Opens the Azure Bot resource in the Azure portal, Channels, Microsoft Teams, and accepts the terms of the channel if it asks (the template makes the channel with only its name).
6. Builds and checks the package: `python tools/teams-package.py build --bot-id <client id> --site https://<host of the web page> --out teams-app.zip`, then `python tools/teams-package.py check teams-app.zip`.

A Teams administrator:
7. In the Teams admin center, Teams apps, Manage apps, Upload new app, uploads `teams-app.zip` ([custom apps](https://learn.microsoft.com/microsoftteams/teams-custom-app-policies-and-settings): available to the org's users after a few hours, no approval needed).
8. Checks Manage apps, Actions, Org-wide app settings: custom apps are allowed, and no app permission policy blocks the app.
9. Has the app installed: each person adds it from Teams, Apps, Built for your org; or an app setup policy installs it for the people it is assigned to ([setup policies](https://learn.microsoft.com/microsoftteams/teams-app-setup-policies)).

Optionally `python tools/entra-setup.py teams-check --tenant-id <id> --bot-id <client id> --assign <object id>` reads what is in place, and `teams-apply --apply` installs the app for the signed-in person only: Graph's delegated permission works "for the signed-in user" ([install app for user](https://learn.microsoft.com/graph/api/userteamwork-post-installedapps)), so for other people the setup policy is the way. Which Graph scopes the Azure CLI's token carries for Teams is not proven. The tool never runs in a pipeline and removes nothing.

Each person:
10. Adds the app and chooses Teams in the settings on the web page. The first card shows whether delivery works.

## Risks that remain

- The app's system identity can read and write the loop's tables. A flaw that runs code in the bot reaches the cases app's records, not Azure.
- The bot shares the function subnet `snet-func` with the cases app. It is a /27 and is not changed once made. Learn [allows a shared Flex Consumption subnet](https://learn.microsoft.com/azure/azure-functions/flex-consumption-how-to), says that one app can affect the others, and advises a /26 for several apps. The workflow check that gives the web page the subnet to itself, and the same rule in `tools/retire-old.py`, let the bot's app through.
- The Teams app package (manifest schema 1.30, current: [reference](https://learn.microsoft.com/microsoft-365/extensibility/schema/)) and the template were checked by tools and tests, not by Teams or Azure.

## What is not built

Outlook actionable messages; proof that a card reaches a person; an agent identity for Meternaut in Microsoft Agent 365; a web application firewall in front of the endpoint; an inbound restriction proved for Teams; installs for other people through Graph; any approval of a change from Teams.
