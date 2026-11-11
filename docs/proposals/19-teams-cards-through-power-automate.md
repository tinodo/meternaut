# Teams cards through Power Automate: no bot, no app registration, no public endpoint — a decision record

**Status: decided by the owner on 2026-11-11; built, not deployed, and not run in Power Platform or in Teams.** The Azure part (a subnet, an enterprise policy and a queue) is in templates and compiles. The flow is an unpacked Power Platform solution that has never been imported anywhere. The tool that makes and links the environment has only ever run its read-only command (`status`), against the owner's tenant on 2026-11-11. Whether a card reaches a person is not proven until the first card arrives in a chat. Every Microsoft fact below names its page and was read on 2026-11-11.

## The owner's words

"Teams bot? What … teams bot? I didn't ask for a bot. I asked for team cards … I do NOT want any app registrations that need specific permissions." And: "use the same mechanism as tinodo/secure-request-classifier", which is the owner's own repository ([secure-request-classifier](https://github.com/tinodo/secure-request-classifier), MIT licence): a Power Platform flow that reaches private Azure resources over virtual network support, with no public endpoint and no stored credential.

## What this is

A person who chose Teams gets the card in a Teams chat. The cases app writes the card as one message on a private Storage queue. A Power Automate flow, which runs in a subnet of the project's own virtual network, reads the message and posts the card with Microsoft's own Teams connector.

What is not needed any more: an Azure Bot resource, a public endpoint, an app registration, a Graph permission, a Teams app package, a secret and a key. [Proposal 13](13-teams-and-outlook.md) described a bot; the last section says what became of it.

How the flow reaches a queue that has no public endpoint: Power Platform has *virtual network support*. A Power Platform environment is linked to an *enterprise policy* of kind NetworkInjection, and the policy names a subnet that is delegated to `Microsoft.PowerPlatform/enterprisePolicies`. From then on the connectors that support it (the Azure Queues connector is one, generally available) run their calls from containers in that subnet, so the storage account is reached over its private endpoint, as the function apps reach it ([overview](https://learn.microsoft.com/power-platform/admin/vnet-support-overview), [set up](https://learn.microsoft.com/power-platform/admin/vnet-support-setup-configure)). Nothing of the landing zone is touched: the template makes a subnet and a policy in the project's own group and network, and no private DNS zone, link, peering or route ([AGENTS.md rule 19](../../AGENTS.md)).

## The data path

| # | Step | Where it runs | Whose identity |
|---|---|---|---|
| 1 | The cases app decides that a person gets a card and writes one message to the queue `teams-cards`. | The cases app, to the storage account of the base, over its private endpoint. | The app's managed identity; it holds Storage Queue Data Contributor on the whole account, which covers this queue. |
| 2 | The flow *Meternaut cards* looks at the queue every minute: the trigger *When there are messages in a queue (V2)* of the Azure Queues connector. | A container in the subnet `snet-powerplatform` of the project's network, then the queue's private endpoint. | The person whose Azure Queues connection the flow uses (a Microsoft Entra ID sign-in, with a data role on this queue). |
| 3 | The flow reads the JSON and posts the card: the Teams action *Post card in a chat or channel*, poster *Flow bot*, post in *Chat with Flow bot*, recipient the message's `to`. | Power Platform to Teams. The Teams connector is not on the list of connectors that use the subnet, so this call goes the normal way (not proven). | The person whose Teams connection the flow uses. |
| 4 | Only after the post has succeeded, the flow deletes the message. | As step 2. | As step 2. |
| 5 | The person sees the card in a chat with the app *Workflows* (the Flow bot). | Teams. | None: the person installs nothing of ours. |

## The message

One JSON text on the queue, not base64:

```json
{"v":1,"id":"<delivery id>","to":"<mail address>","title":"<short title>","card":{ "type": "AdaptiveCard", "...": "..." }}
```

`v` is the version, always 1; `id` is the delivery id that names the card in the run history; `to` is the person's mail address; `title` is a short title, used in the run history only; `card` is the Adaptive Card as JSON. The cases app takes the queue's name from its setting `TEAMS_CARDS_QUEUE`, which [the cases template](../../environment/cases/main.bicep) sets to `teams-cards` (the queue is made there, next to `cases-control`). The whole message is at most 30,000 bytes.

Three rules follow from what Microsoft says, and the card has to keep them:

- **Buttons open links and do nothing else.** A card that is posted by this action cannot collect an answer: any button other than `Action.OpenUrl` shows an error in Teams, and `Action.Submit` too, unless the card is posted by one of the "wait for a response" actions, which this flow does not use ([Power Automate: adaptive cards for Teams, known issues](https://learn.microsoft.com/power-automate/overview-adaptive-cards#known-issues)). So the page of the request is the card's one link, and an answer is given on that page, not in Teams.
- **No templating.** Power Automate does not support Adaptive Cards that use the templating feature ([Copilot Studio: send a proactive adaptive card](https://learn.microsoft.com/microsoft-copilot-studio/advanced-proactive-message#send-a-proactive-adaptive-card)), so the app sends a finished card.
- **The card has to stay under about 28 KB.** An action that posts a message is limited to about 28 KB, all markup counted; a larger one fails with "Request Entity too large" ([Teams connector, known issues and limitations](https://learn.microsoft.com/connectors/teams/)). The queue allows 64 KB and the app's own limit is 30,000 bytes, so a card of 28 KB to 30 KB passes the app and is refused by Teams; the flow deletes such a message (see the next section).

The app should also give the message a time to live. A queue keeps a message for seven days unless the writer says otherwise ([Put Message](https://learn.microsoft.com/rest/api/storageservices/put-message)), and a card that waited longer than a day is not worth posting.

## What the flow does with a message

The definition is [one JSON file](../../powerplatform/solution/src/Workflows/MeternautCards-E6272F40-4E93-4EF9-B20B-2FCD222057AF.json) in an unpacked solution. The trigger looks once a minute, which is the least that Power Automate allows, takes up to 32 messages at a time and hides each of them for 15 minutes. One run handles one message, one run at a time.

| What happens | What the flow does with the message |
|---|---|
| The post succeeds | Deletes the message. |
| The message is not a card message of version 1 | Deletes it and ends the run as failed. The text stays in the run history. |
| Teams answers 400 (the card is wrong), 404 (the person is not found) or 413 (the card is too large) | Deletes it and ends the run as failed: these do not get better with time. |
| Anything else: a timeout, 401 or 403 (the Workflows app is not allowed, or a connection needs a new sign-in), 429 (too many cards), 5xx | Leaves it. It is visible again after the 15 minutes and is tried again, until it expires. The run is marked failed. |

Delivery is at least once. If a post succeeded and the delete did not arrive, the message comes back after 15 minutes and the card is posted a second time. That is rare and is accepted.

**The app does not learn of any of this.** The queue is one way. The app knows that it queued a card and not that a person saw it. There is no dead-letter queue: Storage queues have none (the Functions host makes a `-poison` queue for the queues that it reads itself, and this one is read by the flow). A card that was refused for good, and a card that kept failing until its message expired, show up in one place only, the failed runs of the flow, which Power Automate keeps for 28 days by default ([run history](https://learn.microsoft.com/power-automate/dataverse/cloud-flow-run-metadata)). A second queue for answers back is how the app could learn; it is not built. Whatever the app does when no card arrives, such as sending a letter, cannot depend on the card having been posted.

## What each part is and what it costs

| Part | What it is | Cost |
|---|---|---|
| The subnet `snet-powerplatform` and its network security group | A subnet delegated to `Microsoft.PowerPlatform/enterprisePolicies`, in the project's network, with a group that has no rule of its own. [The template](../../environment/powerplatform/main.bicep). | No meter. |
| The enterprise policy `ep-meternaut-netinjection` | Kind NetworkInjection, location `sweden`, one virtual network. | No price was found: the Retail Prices API has no item for it (read 2026-11-11). To be confirmed on the first bill. |
| The queue `teams-cards` | In the storage account of the base. | 0.004 US dollars per 10,000 operations and 0.045 per GB and month (Retail Prices API, `swedencentral`, Queues v2, Standard LRS, read 2026-11-11). A look every minute is about 43,200 operations a month, so under 0.02 dollars. |
| The Power Platform environment | A Developer environment costs nothing and is for development and test, with 750 flow runs a month and 2 GB of data, not for production use. Each person can have one ([Developer Plan](https://learn.microsoft.com/power-platform/developer/plan)). | The environment is free; running flows in it as a Managed Environment needs the licence of the next row. Cards for other people, or for a customer, belong in a Sandbox or Production environment, which has its own capacity and licences. |
| Managed Environments | Virtual network support needs a Managed Environment. From 15 November 2026 no unmanaged developer environment can be made, and the existing ones are suspended from 15 December 2026 ([deprecation](https://learn.microsoft.com/power-platform/important-changes-coming#deprecation-of-unmanaged-developer-environments-and-the-power-apps-developer-plan)). | **To be confirmed against the owner's licences.** The Developer Plan does not include the use rights of a Managed Environment: the person who runs a flow there needs a premium licence, such as Power Automate Premium or Power Apps Premium, or the flow needs its own capacity ([Developer Plan](https://learn.microsoft.com/power-platform/developer/plan), [Managed Environments licensing](https://learn.microsoft.com/power-platform/admin/managed-environment-licensing), [Power Automate licensing FAQ](https://learn.microsoft.com/power-platform/admin/power-automate-licensing/faqs#licensing-compliance-for-power-automate)). |
| The Azure Queues connector | A premium connector ([connector page](https://learn.microsoft.com/connectors/azurequeues/)). | **To be confirmed against the owner's licences**: the same premium licence as above. |
| The Microsoft Teams connector | A standard connector ([connector page](https://learn.microsoft.com/connectors/teams/)). | No licence of its own. |

## The room in the network

The project's /24 holds five subnets: the private endpoints (a /27), the cases app (a /27), the Operator (a /27), the web page (a /27) and the AI Gateway (a /26). One /26 is free. [The parameter builder](../../tools/environment-params.py) (`--powerplatform`) takes the last free /27 of the network for `snet-powerplatform`, so one /27 stays free. If the network has no free /27, the builder makes no file and says why in its output (`powerplatform_reason`); it never invents a range.

| Size | Fits |
|---|---|
| /28 (11 usable addresses) | The least. A Sandbox or Developer environment needs 6 to 10 addresses, and Azure keeps five in every subnet. |
| /27 (27 usable) | The default here: a Developer or Sandbox environment with room, and one /27 left in the network. |
| /26 (59 usable) | A Production environment, which needs 25 to 30 addresses ([subnet size](https://learn.microsoft.com/power-platform/admin/vnet-support-overview#estimating-subnet-size-for-power-platform-environments)). It takes the whole free block. |

**This is the owner's decision, and it has to be made before the first deploy.** The address range of a delegated subnet and the DNS servers of its network cannot be changed while an environment is linked: the environment has to be unlinked first, the change made, and the link made again; after a change of DNS servers, wait 30 minutes before linking ([FAQ](https://learn.microsoft.com/power-platform/admin/vnet-support-overview)). The size is the constant `POWERPLATFORM_SUBNET_LENGTH` in the parameter builder. Power Platform uses the network's own DNS servers, which here are the landing zone's, so the name of the storage account has to resolve to its private address from the subnet, as it does for the function apps.

## What a person does by hand, in order

`python tools/powerplatform.py steps` prints these steps with the names filled in from its arguments. It sends nothing.

**The owner, in Azure**

1. Decide the size of the subnet (above), if /27 is not right.
2. Start the Hub actions `base` and `cases` if they have not run: `cases` makes the queue. Then start the Hub action `powerplatform`, which runs after `cases`. It checks that the resource provider `Microsoft.PowerPlatform` is registered (the workflow's identity cannot register it: `az provider register --namespace Microsoft.PowerPlatform`), makes the subnet and the enterprise policy, waits for the landing zone's route table to appear on the subnet, as the AI Gateway's step does, and reads everything back. A policy that is linked cannot be written again by Power Platform, so the template makes it only when it does not exist.
3. Give the person whose connection the flow uses a data role on the queue, and nothing wider. A role takes up to ten minutes to apply:

   ```
   az role assignment create --assignee-object-id <object id of the person> --assignee-principal-type User --role "Storage Queue Data Message Processor" --scope /subscriptions/<subscription id>/resourceGroups/<resource group>/providers/Microsoft.Storage/storageAccounts/<storage account>/queueServices/default/queues/teams-cards
   ```

   The role reads, peeks and deletes messages ([built-in roles](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/storage)). The deploy identity can give roles to service principals only, so this one is a hand step. The connector wants a Microsoft Entra ID connection; guest accounts are not supported.
4. If the Power Platform administrator who links the environment cannot read the policy, give that person Reader on it:

   ```
   az role assignment create --assignee-object-id <object id of the administrator> --assignee-principal-type User --role Reader --scope /subscriptions/<subscription id>/resourceGroups/<resource group>/providers/Microsoft.PowerPlatform/enterprisePolicies/ep-meternaut-netinjection
   ```

**A Teams administrator**

5. Check that the app *Workflows* (formerly Power Automate) is allowed in the [Teams admin center](https://admin.teams.microsoft.com/policies/manage-apps). The action that posts a card needs it ([Teams connector, known issues](https://learn.microsoft.com/connectors/teams/)).

**A Power Platform administrator, with the tool and their own `az login`.** Each command is a dry run until `--apply` is added. The tool never runs in a pipeline: its output names environments of the estate, and the deploy identity holds no right in Power Platform.

6. `python tools/powerplatform.py create-environment --name <environment name> --sku Developer --apply` (region `sweden`, Dataverse, euro, English; it waits until the environment is Ready; an environment of that name is left alone).
7. `python tools/powerplatform.py managed --environment <environment name> --apply`.
8. `python tools/powerplatform.py link --environment <environment name> --subscription <subscription id> --resource-group <resource group> --apply`. It checks first that the environment is in Sweden, is a type that supports virtual network support, is a Managed Environment and is not linked to another policy, and that the policy and its subnet look right. Then wait: connections can be unstable for up to 30 minutes after a link or an unlink. `status --environment <environment name>` must say that the project's policy is linked.

**The person of step 3, in the maker portal**

9. `python tools/powerplatform-pack.py` makes `powerplatform/out/meternaut-cards.zip`, the same bytes every time. In the environment: Solutions, Import solution, that file.
10. Sign in the two connections: Azure Queues with *Microsoft Entra ID Integrated* (not an access key), and Microsoft Teams. Set the two environment variables: *Storage queue endpoint* to the whole address, `https://<storage account>.queue.core.windows.net/`, and *Queue name* to `teams-cards`. No address of the estate is in the repository. Open the flow *Meternaut cards* and turn it on.
11. Send the first card before the app does: a second flow in the same environment with a manual trigger and one *Put a message on a queue (V2)* action with the same connection, endpoint and queue, and a message in the format above. It needs the role *Storage Queue Data Message Sender* on the queue for the time of the test. The card should arrive in the person's chat within a few minutes, and the queue should be empty.

The import by an API call (`ImportSolutionAsync`) is not written: its connection references and environment variable values go in as a collection of entities that the Web API reference gives no example of.

**The way back.** Turn the flow off, so that cards wait in the queue; `python tools/powerplatform.py unlink ...` (only the project's own policy is unlinked, and the tool deletes nothing); wait 30 minutes; then remove the subnet and the policy, the policy only after the unlink.

## The limits

| Limit | What it is | Source |
|---|---|---|
| Looking at the queue | At most once a minute, 32 messages at a time, so a card arrives within a minute or two. | [Limits](https://learn.microsoft.com/power-automate/limits-and-config), the connector's definition |
| Cards posted as the Flow bot | 25 requests per connection in 300 seconds. A burst above that is delayed by the retry of 15 minutes. | [Teams connector, throttling](https://learn.microsoft.com/connectors/teams/) |
| A flow that fails | A cloud flow whose trigger or actions fail without a break for 14 days is turned off. One that nothing triggers for 90 days may be turned off, unless its owner has a premium licence. | [Limits of cloud flows](https://learn.microsoft.com/power-automate/limits-and-config) |
| A developer environment | One that is inactive for 30 days is disabled. Whether a flow that only looks at a queue counts as use is not stated. | [Developer Plan](https://learn.microsoft.com/power-platform/developer/plan) |
| A person behind the flow | The connections belong to a person. If that account is disabled, or a sign-in rule asks for a new sign-in, the flow stops and the cards wait in the queue until their messages expire. A dedicated service user is the usual cure; it needs its own licences and is not decided. | [Azure Queues connector](https://learn.microsoft.com/connectors/azurequeues/) |
| A private channel | Posting to a private channel is not supported; the flow posts to a person's chat only. | [Teams connector](https://learn.microsoft.com/connectors/teams/) |
| Region | The Power Platform region `sweden` maps to `swedencentral` only, so there is one network and no second region to fail over to. | [Supported regions](https://learn.microsoft.com/power-platform/admin/vnet-support-overview#supported-regions) |

## What is proven, and what is not

**Proven**, on 2026-11-11, with the owner's own sign-in and read-only calls:

- The list of environments, and one environment's detail, answer in the shape that the tool reads (`status` ran against the tenant).
- The definitions of the two connectors on the Power Apps API: the Azure Queues trigger `OnMessages_V2` and the action `DeleteMessage_V2` with their parameter names, and the Teams operation `PostCardToConversation` with the poster *Flow bot* and the place *Chat with Flow bot*.
- The templates compile and pass the Bicep linter; the tests run the tool, the packer and the template checks against fakes.

**Not proven.** None of this has run.

- The solution has never been imported. The flow's JSON follows the owner's reference repository and the shapes of the two connector definitions, not an export from the maker portal. The designer may mark an action or write the definition again.
- The names of the Teams action's inputs (`recipient` and `messageBody`) come from the connector's own description, not from a run.
- That the trigger reaches the queue from the delegated subnet. It depends on the landing zone's DNS resolving the account's name and on the landing zone's route table and firewall letting the containers out, which Learn says are the network's own policies.
- That the subnet gets its route table on time, and that the delegation survives it.
- That the *Workflows* app is allowed in the owner's tenant, and how the card looks in the chat.
- That the licences of the owner cover a Managed Environment and a premium connector.
- That a flow which only looks at a queue keeps a developer environment alive.
- The API version of the enterprise policy: the template uses `2020-10-30-preview`, the one that the Bicep reference and the Learn page list; Microsoft's own module deploys `2020-10-30`. If the preview version is refused, it is one word.
- The custom prefix of the solution's parts is `mtnaut`, not `meternaut`: a publisher prefix has 2 to 8 characters ([pac solution init](https://learn.microsoft.com/power-platform/developer/cli/reference/solution#pac-solution-init)).

## What replaced the bot

The decision of 2026-11-11 replaces the delivery that [proposal 13](13-teams-and-outlook.md) described: the Azure Bot resource, the public route `POST /api/messages`, the identity of the bot, the hand-written check of Microsoft's tokens and the Teams app package are removed, and with them the need for a request in writing for a public endpoint ([rule 15 (c)](../../AGENTS.md)). What stays is what the card says, which the decision brief decides. What goes is the tap: a card has link buttons only, and every answer is given on the page.

| What | Where it is |
|---|---|
| The subnet, its network security group and the enterprise policy | [`environment/powerplatform/main.bicep`](../../environment/powerplatform/main.bicep); the range comes from `python tools/environment-params.py --powerplatform` |
| The queue and the app's setting | [`environment/cases/main.bicep`](../../environment/cases/main.bicep) |
| The flow, as an unpacked solution | [`powerplatform/solution/src`](../../powerplatform/solution/src) |
| The packer | [`tools/powerplatform-pack.py`](../../tools/powerplatform-pack.py) |
| The tool for the environment, the link and the steps | [`tools/powerplatform.py`](../../tools/powerplatform.py) |

The reference repository's Bicep, scripts and solution are adapted here with credit in each file ([secure-request-classifier](https://github.com/tinodo/secure-request-classifier), MIT).

## Sources

All read on 2026-11-11: [VNet support overview](https://learn.microsoft.com/power-platform/admin/vnet-support-overview), [set up VNet support](https://learn.microsoft.com/power-platform/admin/vnet-support-setup-configure), [Azure Queues connector](https://learn.microsoft.com/connectors/azurequeues/), [Microsoft Teams connector](https://learn.microsoft.com/connectors/teams/), [adaptive cards in Power Automate](https://learn.microsoft.com/power-automate/overview-adaptive-cards), [limits of cloud flows](https://learn.microsoft.com/power-automate/limits-and-config), [flow run history](https://learn.microsoft.com/power-automate/dataverse/cloud-flow-run-metadata), [Developer Plan](https://learn.microsoft.com/power-platform/developer/plan), [Managed Environments licensing](https://learn.microsoft.com/power-platform/admin/managed-environment-licensing), [Queue Storage](https://learn.microsoft.com/azure/storage/queues/storage-queues-introduction), [Put Message](https://learn.microsoft.com/rest/api/storageservices/put-message), [enterprise policies (ARM reference)](https://learn.microsoft.com/azure/templates/microsoft.powerplatform/enterprisepolicies), Microsoft's [EnterprisePolicies module](https://github.com/microsoft/PowerPlatform-EnterprisePolicies) for the link and unlink calls, and the owner's [secure-request-classifier](https://github.com/tinodo/secure-request-classifier).
