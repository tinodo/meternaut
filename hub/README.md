# hub/

> **Withdrawn on 2026-11-03. Do not follow the steps on this page.** The hub it describes was deployed by hand from a machine, it added a second API Management instance next to the owner's own, and it created private DNS zones and a virtual network that the landing zone does not want. Its resource group was deleted. Every change to Azure goes through a GitHub Actions workflow ([AGENTS.md](../AGENTS.md) rule 18), the landing zone provides private DNS and the network (rule 19), and the owner's existing API Management instance is used. This folder is rewritten when the new hub is built.

The hub is the one door to every AI model that Meternaut uses. It is an API Management service: it checks who is calling, allows only the models a contract names, limits the tokens each contract may use, and records how many tokens each call used. Agents never call a model directly. Other names for the same thing are the *AI gateway* and, for Microsoft's open-source accelerator that provides it, the *Citadel governance hub*. It is not a network hub and not a Foundry hub.

An adopting organisation normally brings its own hub ([architecture](../docs/design/02-architecture.md#6-the-landing-zone-and-the-hub)). This folder deploys the smallest hub that works for development, for an organisation that has none ([before you start](../docs/build-plan/02-before-you-start.md)). It is built from [the accelerator](https://github.com/Azure-Samples/ai-hub-gateway-solution-accelerator) at the commit pinned in [`accelerator.json`](accelerator.json), plus a small patch.

## What gets deployed

| Part | What it is | Why it is there |
|---|---|---|
| API Management, Developer tier | The gateway, injected in the hub's own network in internal mode: no public gateway address. No service level agreement | The one door to the models |
| Microsoft Foundry account | One model, `gpt-6-luna` (EU data zone). Public access and key access are off; only the gateway's managed identity may call it | The model |
| Event Hubs, Standard, one throughput unit | Where the gateway's usage logger writes | The accelerator's logging fragments need it |
| Key Vault | Each contract's key and endpoint | Secrets stay out of deployment outputs |
| Log Analytics and Application Insights | Token counts and request metadata, with a daily cap on ingestion | Spend is counted from these logs |
| Three private endpoints, private DNS zones | For the model account, the vault and the event hub | A landing zone that denies public access to these services |
| A virtual network of its own | Holds the gateway and the endpoints | Peering to the rest of the landing zone is up to that landing zone |

## What the patch changes

[`accelerator-changes.patch`](accelerator-changes.patch) is the only difference from the pinned commit, applied by the steps below.

- **A switch for the usage-ingestion add-on** (`deployUsageIngestion`). It is on upstream and off here: it adds Cosmos DB, a Logic App, a storage account and an identity that nothing in the build plan reads, and together they cost more than the rest of the hub.
- **Event Hubs:** minimum TLS 1.2 and no local keys, which a landing zone with a TLS policy requires, and no auto-inflate, so the namespace stays at its one throughput unit.
- **Model logging:** the request and response objects are left out when message capture is `none`, because API Management rejects the value `none`. Token counts and the model are always logged.
- **Foundry:** key access is off, and two switches (`grantFoundryKeyVaultAccess`, `grantDeployerFoundryAccess`) turn off grants that nothing uses: the account's access to the vault, and the deploying person's role on the account, which would allow calling the model past the gateway.
- **Log Analytics:** a daily ingestion cap.

## Deploy it

You need the Azure CLI with Bicep, Owner (or Contributor plus User Access Administrator) on the subscription, the `Microsoft.ApiManagement` resource provider registered, and quota for the model in the region.

1. **Fetch the accelerator at the pin and apply the patch.** `local/` is ignored by git.

   ```text
   git init local/accelerator
   git -C local/accelerator fetch --depth 1 https://github.com/Azure-Samples/ai-hub-gateway-solution-accelerator <commit in accelerator.json>
   git -C local/accelerator checkout FETCH_HEAD
   git -C local/accelerator apply --ignore-whitespace ../../hub/accelerator-changes.patch
   ```

2. **Name what is specific to you in the environment.** The variables are listed at the top of [`meternaut-dev.bicepparam`](meternaut-dev.bicepparam): `HUB_OWNER` (required), the resource group, the names of the gateway and the vault, and the hub's address ranges, which must not overlap a network that peers with it. Nothing in the repository names a subscription.

3. **Check, then deploy** at subscription scope. Use `az deployment`, not `azd up`: the accelerator's `azure.yaml` also lists the Logic App that this profile does not create. The first deployment takes about 35 minutes, because API Management takes that long to create; a repeat takes about 7. A switch suppresses creation, never deletion: if the add-on or a grant was ever on in this group, delete what it made by hand (the Cosmos DB, the Logic App, the storage account, the identity and its role assignments), and read the group's resources and role assignments afterwards.

   ```text
   az deployment sub what-if --subscription <id> --location <region> --template-file local/accelerator/bicep/infra/main.bicep --parameters hub/meternaut-dev.bicepparam
   az deployment sub create  --subscription <id> --location <region> --template-file local/accelerator/bicep/infra/main.bicep --parameters hub/meternaut-dev.bicepparam
   ```

4. **Make the gateway's name resolve.** The gateway's host name, `<name>.azure-api.net`, resolves to nothing inside a private network. [`dns-gateway.bicep`](dns-gateway.bicep) creates a private DNS zone for that one name (no other `azure-api.net` name is affected), an A record with the gateway's private address, read from the instance, and a link to each network that must resolve it: the hub's own network and the network whose resolver the landing zone uses. Deploy it into the hub's resource group. If the gateway's address ever changes, for example when the instance is re-created, deploy it again to update the record; callers keep the old answer for up to five minutes.

   ```text
   az deployment group create --subscription <id> -g <resource group> --template-file hub/dns-gateway.bicep --parameters apimName=<gateway name> linkedVirtualNetworkIds='["<hub network id>","<resolver network id>"]'
   ```

   A machine whose DNS server does not forward to that resolver can still call the hub: the harness takes the gateway's address (`C14_HUB_CONNECT_ADDRESS`) and keeps the name for TLS. That address changes with the gateway's too.

5. **Add a contract**, at subscription scope. [`contracts/learning-demo-dev/`](contracts/learning-demo-dev/) is the contract of the learning demonstration: one model, 30,000 tokens a minute and 2,000,000 a month. Its key and endpoint go to the vault, and no key appears in the deployment's output.

   ```text
   az deployment sub create --subscription <id> --location <region> --template-file local/accelerator/bicep/infra/citadel-access-contracts/main.bicep --parameters hub/contracts/learning-demo-dev/main.bicepparam
   ```

   Then suspend the key that API Management made for the administrator on the accelerator's default product, `unified-ai-product`, which has no limits: list the instance's subscriptions (`az rest --method get` on `.../service/<name>/subscriptions?api-version=2022-08-01`), find the one whose scope ends in `/products/unified-ai-product`, and patch its `state` to `suspended` (`az rest --method patch`, header `If-Match=*`).

   The contract template reads `HUB_SUBSCRIPTION_ID` and the names of the group, the instance and the vault from the environment: the same `HUB_RESOURCE_GROUP`, `HUB_APIM_NAME` and `HUB_KEY_VAULT_NAME` as in step 2. If you left a name empty there, read the derived one from the resource group first. The key is a secret in the vault, which only the private network reaches; an authorised person can also read it with the management API (`listSecrets` on the contract's subscription in the instance). Put it in the environment of the one process that needs it and nowhere else.

6. **Put a budget on the group** with [`infra/budgets/rg-budget.bicep`](../infra/budgets/rg-budget.bicep), whose parameters are the budget's name, the monthly cap in the subscription's billing currency and the addresses that receive the alerts. A budget only alerts; deleting the resource group is what stops the cost.

   ```text
   az deployment group create --subscription <id> -g <resource group> --template-file infra/budgets/rg-budget.bicep --parameters budgetName=<name> amount=<monthly cap> contactEmails='["<owner address>"]'
   ```

7. **Try it** with the harness of check C14: set `C14_HUB_CHAT_URL` (the gateway's `/unified-ai/v1/chat/completions` route), `C14_HUB_MODEL`, `C14_HUB_KEY` and, if needed, `C14_HUB_CONNECT_ADDRESS`, then run `python evaluation/c14/run.py hub-check`. It makes one call of about a hundred tokens.

CI does the first step on every change: it fetches the pin, applies the patch and compiles the template, the parameter files and the DNS template, so a patch that no longer applies fails the build.

## What was checked

On the deployed hub, from a machine with a network path to it. A refused call is not a model call: no prompt reaches the model.

| Check | Expected | Result |
|---|---|---|
| A chat completion with the contract's key | 200, the reply and its token counts | Passed |
| No key; a wrong key; the contract's key on another API of the instance | 401 | Passed |
| A route that does not exist | 404 | Passed |
| A model the contract does not allow; the model's alias `triage` | 403 | Passed |
| A prompt whose estimated tokens exceed the minute's limit | 429 from the gateway, no model call | Passed |
| The model account directly, without credentials, with the hub's key, and with the token of the person who deployed it | 401 | Passed |
| The workspace after the calls | The model and the token counts of each call in the model log, the caller and the status in the gateway log; the prompt and answer columns are empty | Passed |

What these checks do not show: slice 0.2 of the build plan also calls for the solution's own Foundry account without any model deployment, a policy that refuses a deployment there, and a limit on what the agents' network may reach. Those belong to the Evaluate profile and are not built, so check C1 is open ([first checks](../docs/build-plan/03-first-checks.md#c1-the-hub-path-works-end-to-end)).

## What it does not do

- **Callers are identified by a subscription key.** Validating an Entra token needs an app registration and the contract's token and role settings, which this contract does not set; until they are, a contract's key is the only proof of who calls. Keep the key out of anything but the vault and the process that uses it.
- **Other subscriptions of the instance are not bound to a contract.** The contract's limits apply to calls made with the contract's key. API Management also makes a key for the administrator on each product, and the accelerator's default product, `unified-ai-product`, carries no limits: step 5 suspends the key on it. The built-in all-access subscription stays active for the instance's administrators, so treat access to the instance as access to every model behind it.
- **Aliases are not onboarded.** The contract allows the model's own name, not `triage`. The hub also adds debugging headers (the model and backend that served the call); they are for development.
- **The gateway has no service level agreement.** The Developer tier is for development.
- **Not everything is private.** The gateway, the model account, the event hub and the vault are. Log Analytics and Application Insights accept authenticated ingestion and queries over the public network, and the API Management management endpoint is public.
- **What is logged.** Token counts, the model, the caller and request metadata such as the client address. Prompts and answers are not logged. A call that the gateway refuses is logged with its *estimated* tokens and no model name, so spend is the sum of the tokens of the rows that name a model. That is a floor, not a guarantee: a call that fails after the model has started may report no usage, and the Azure bill is what settles the count.
- **Private-endpoint DNS belongs to the hub's own network.** The template creates the zones and the zone group of each private endpoint itself and links the zones to the hub's network only. A landing zone that also creates zone groups by policy reports a failed `PolicyDeployment_` deployment in the group ("more than one private dns zone group"): the endpoint already has one, and the hub works. The price is that the landing zone's central zones hold no records for these endpoints, so nothing outside the hub's network resolves them by name. A platform team that wants central records deploys the accelerator's existing-network path instead: it brings its own network, with its DNS servers, and passes in the central zones.

## What it costs

`python tools/cost-model.py --dev-hub` prices one month of the gateway, the event hub, the endpoints, the DNS zones, the vault and the log ingestion at list prices from the repository's price snapshot, and says which volumes it assumes. It is a sizing, not a billing guarantee: the log ingestion is priced as if the workspace took in its daily cap every day, DNS queries and vault operations are assumed, and the data that the endpoints process is left out. It also prices the contract's monthly token quota, read from the contract's policy, as if all of it were used. A hub that stays after its work is done is the cost to watch: delete it as soon as the learning demonstration is finished.

To add up the tokens that the hub has served, run this in the workspace (the portal's Logs page, or the Log Analytics query API). Rows without a model name are calls that the gateway refused and carry an estimate:

```text
ApiManagementGatewayLlmLog
| where isnotempty(ModelName)
| summarize PromptTokens = sum(PromptTokens), CompletionTokens = sum(CompletionTokens) by bin(TimeGenerated, 1d)
```

## Remove it

Delete the links that [`dns-gateway.bicep`](dns-gateway.bicep) made to networks outside the group, then delete the resource group. API Management, the Foundry account and the Key Vault stay soft-deleted for a while: purge the first two if the names are needed again. A vault with purge protection keeps its name for 90 days, so give the next one a numbered name.
