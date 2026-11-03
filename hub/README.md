# hub/

The hub is the one door to every AI model that Meternaut uses. It is an API Management service: it checks who is calling, allows only the models a contract names, limits the tokens each contract may use, and records how many tokens each call used. Agents never call a model directly. Other names for the same thing are the *AI gateway* and, for Microsoft's open-source accelerator that provides it, the *Citadel governance hub*. It is not a network hub and not a Foundry hub.

An adopting organisation normally brings its own hub ([architecture](../docs/design/02-architecture.md#6-the-landing-zone-and-the-hub)). This folder builds what development needs on top of an API Management instance that already exists: it does not create a gateway, a DNS zone, a peering or a route, because the landing zone provides them.

## What it builds

| Part | What it is |
|---|---|
| **The gateway** | The existing API Management instance. Meternaut adds a handful of objects whose names start with `meternaut-` ([listed below](#what-is-added-to-the-api-management-instance)) and touches nothing else on it |
| **The model** | One Microsoft Foundry account in a resource group of its own, with one model, `gpt-6-luna` (EU data zone). Public access and key access are off; the instance's own identity is the only caller, with the one role that runs chat completions |
| **A private endpoint** | The only way to the model account. The landing zone's policy registers its name in the central private DNS zone about ten minutes after it exists; the template creates no DNS zone, link or zone group |
| **A small network** | One virtual network with one subnet for the endpoint, on the landing zone's DNS server. The landing zone's network manager peers and routes it by itself |
| **A budget** | One monthly budget on the resource group, with alerts to the owner |

[`main.bicep`](main.bicep) is the template. [`contract.json`](contract.json) is the development contract: one model, 30,000 tokens a minute and 2,000,000 a month. [`apim/`](apim/) holds the objects added to the instance.

## How a change reaches Azure

Only through the workflow [`deploy-hub.yml`](../.github/workflows/deploy-hub.yml) ([AGENTS.md](../AGENTS.md) rule 18). Nobody deploys from a machine. The owner starts it from the Actions tab (*Hub*, *Run workflow*) and picks one action:

| Action | What it does |
|---|---|
| `what-if` | Shows what a deploy would create in Azure and in the instance. Changes nothing. An agent may start this one |
| `deploy` | Builds or updates the network, the model account and the endpoint; waits until the landing zone has registered the endpoint's name (up to 40 minutes); adds the Meternaut objects to the instance; then checks the hub with real calls ([`tools/hub-smoke.py`](../tools/hub-smoke.py)); a check passes only with evidence, such as the model's own token usage in the reply. Tick `check_limits` to also check that the token rate is enforced: the gateway itself must refuse the second request with a 429. It uses about a minute's allowance of tokens and blocks the key for up to a minute |
| `pause` | Takes the Meternaut objects out of the instance and deletes the private endpoint, the only fixed cost. Everything else stays and costs nothing while idle. `deploy` brings it back |
| `remove` | Takes everything away: the objects, the endpoint, the model account, the network and the budget, each by name. Anything else in the resource group is left alone. The account is soft-deleted; the next `deploy` restores it by itself |

What the workflow does first, every time: the tests of the tools and the Bicep compile ([`tools/workflow-lint.py`](../tools/workflow-lint.py) also checks the workflow itself), then it signs in with OpenID Connect as an identity that can act only in the hub's resource group and on the `meternaut-` objects of the instance. It runs only on `main`, only for the owner, and never two at once. It touches the instance only after the endpoint's name is registered: if that never happens, nothing has been added to it. The objects are then written one after another and the hub is checked afterwards, so a failed run can leave some of them in place and the endpoint running. Running `deploy` again is safe and repeats only what is missing, and the run's summary says plainly when it did not finish and what may still exist.

The identity and the workflow's settings are made once, by hand, with the owner's yes: [`BOOTSTRAP.md`](BOOTSTRAP.md). It is the only manual step, and it lists the identity's rights and what they cannot do.

| Setting | Kind | What it holds |
|---|---|---|
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | secret | The identity and where it signs in |
| `HUB_APIM_RESOURCE_ID` | secret | The resource id of the API Management instance |
| `HUB_RESOURCE_GROUP`, `HUB_LOCATION` | variable | The hub's resource group and region |
| `HUB_VNET_PREFIX`, `HUB_PE_SUBNET_PREFIX` | variable | The network's address range and the endpoint's subnet, inside `10.0.0.0/8` |
| `HUB_DNS_SERVERS` | variable | The landing zone's DNS server. A network without it cannot resolve the central private DNS zones |
| `HUB_OWNER`, `HUB_ALERT_EMAILS`, `HUB_BUDGET_AMOUNT` | variable | The owner tag, the budget's alert addresses and its monthly amount |
| `HUB_APIM_LOGGER` | variable | The name of the instance's Application Insights logger, where the Meternaut API sends its metrics |

[`tools/hub-params.py`](../tools/hub-params.py) checks every value before anything is deployed, works out the model account's name from the subscription and the group so that it is the same on every run, and passes on the budget's start date, which the workflow reads from the existing budget (a budget keeps the date it started with).

## What is added to the API Management instance

[`tools/apim-sync.py`](../tools/apim-sync.py) writes these, and removes them again. It refuses any object whose name does not start with `meternaut-`, the instance itself, its global policy, its network, its loggers and every other API and product, and it refuses to write (`apply`, `remove`) anywhere but GitHub Actions. After each write it reads the object until the service reports it finished, because the service may answer before it is done; an object that reports failed is made again from the approved definition.

| Object | What it is |
|---|---|
| Product `meternaut-learning-demo-dev` | The contract: published, a key required, one key. Its policy names the allowed models and counts tokens |
| API `meternaut-llm` | The route `/meternaut/llm/v1/chat/completions`, a key in the `api-key` header. Its policy checks the model, sends the call to the model account on the instance's own identity and drops the caller's key |
| Operation `chat-completions` | The one operation of the API |
| Subscription `meternaut-learning-demo-dev-sub-01` | The contract's key. It is read only through the workflow's check and never printed |
| Diagnostic `applicationinsights` on the API | Request metadata and token metrics to the instance's logger; no prompts or answers |

`python tools/apim-sync.py plan` (the workflow's `what-if` runs it) shows each object as `create`, `update` or `unchanged` before anything is written.

## How a call is checked

1. The instance asks for a key (a missing or wrong key is a 401). Only the contract's key reaches the Meternaut API with a list of allowed models; the instance's all-access key and every other key carry none, so the API's own check (step 4) refuses them.
2. The contract's policy reads the request once. The model must be a JSON string on the contract's list, otherwise the answer is 403 and the model is never called; a body it cannot read has no model, so that is a 403 too. Streaming is refused with 400 (a streamed reply's tokens would be estimated, not counted).
3. Only then does it count the key's tokens, from what the model reports, against 30,000 a minute and 2,000,000 a month (a 429 past the rate, a 403 past the quota). A refused call is never counted.
4. The API's policy checks again, and fails closed: no model or no list at all is a 403. Then the call goes to the model account's private endpoint on the instance's own identity, and the caller's key is dropped first.
5. The reply's token counts go to the instance's logger as metrics.

## Use it

For check C14 ([`evaluation/c14/`](../evaluation/c14/README.md)): `C14_HUB_CHAT_URL` is `<the instance's gateway address>/meternaut/llm/v1/chat/completions`, `C14_HUB_MODEL` is `gpt-6-luna` and `C14_HUB_KEY` is the contract's key. `python tools/apim-sync.py key --apim <resource id>` prints the key; it needs the signed-in person's right to read subscription keys on the instance. Put it in the environment of the one process that needs it, and nowhere else. Then `python evaluation/c14/run.py hub-check` makes one call of about a hundred tokens.

## What has been checked, and what has not

Nothing is deployed. The tests that run on every change use no Azure: the gateway tool against a stand-in for the management service (what it writes, what it refuses, that a second run changes nothing, that it removes only what it made), the smoke test against a stand-in for the hub, the parameter checks, the workflow rules, and the Bicep compile and lint. The workflow's own shell steps were also run under the runner's shell flags against a fake Azure CLI (the restore retry, the not-found handling, the order of removal, the polling, the key never printed); that harness is not part of the repository. The policies follow the accelerator's working fragments and Microsoft's reference for `llm-token-limit` and `llm-emit-token-metric`. The instance checks a policy when it is saved, but only in part: some expression errors show only when a request runs, so a saved policy is no proof that it works. The smoke test, with real calls, is that proof.

Not yet seen, and the reason the first run is `what-if` and the second a `deploy` with `check_limits`: that the identity, with only its narrow rights, can do every step (the preview and the restore included); that the landing zone's policy registers this endpoint and the name then resolves from the instance (the workflow waits for the zone group, which is not the same as a resolving name, and the smoke test retries for fifteen minutes); that the instance reaches the model through the lab's DNS and routes; that the v1 chat route answers on this account and its reply carries token usage; that the instance accepts the exact objects and policy expressions, and runs the typed model and streaming checks as written; which provisioning states the instance reports while it makes an object (the tool waits for the words that clearly mean "working", stops on the ones that mean "failed", takes any other word as final and prints it as a note, so the first run shows the real words; a following write that starts too early fails and stops the run, and a second run finishes it); that Azure accepts the principal-type role condition; that the budget step reads the real start date and the real not-found answer; that the token limit refuses as designed, with the large request crossing the contract's 30,000 tokens a minute without first meeting the model's own 50,000; and a whole lifecycle (deploy, deploy again, pause, deploy, remove, deploy). Each is a step of the workflow that stops with a plain message.

## What it does not do

- **Callers are identified by a subscription key.** Checking an Entra token needs an app registration and settings that this contract does not have.
- **The gateway is the instance's public address.** The workflow's check calls it from a GitHub-hosted runner, so the instance's gateway must be reachable from the internet; for an instance reachable only from inside a network, the check would have to run from inside it, which is not built. The model account has no public access either way.
- **The token limit counts what the model reports.** The request that crosses the limit still completes; the next one is refused. Calls that run at the same moment can overshoot a little. It is accounting, not a spending guarantee: the budget alerts, and the model deployment's own capacity (50,000 tokens a minute) is a ceiling. Streaming is refused, so no estimate ever stands in for a count.
- **The model name is read by a JSON parser that keeps the last of two duplicate keys.** The model account holds only the one allowed deployment, so a request that the model reads differently reaches nothing else; a second deployment in the account would need a stricter check first.
- **The role on the instance is wide.** *API Management Service Contributor* covers the whole instance. The tool's prefix rule, the plan and the owner's click are what hold the workflow to the `meternaut-` objects ([bootstrap](BOOTSTRAP.md#what-the-identity-can-and-cannot-do)).
- **The instance has its own limits.** A Developer-tier instance has no service level agreement, and what else runs on it is the owner's business.
- **Dimensions in the token metrics** (the model, the key) show in the metrics explorer only if the Application Insights resource has *alerting on custom metric dimensions* turned on. Without it the metric is still emitted.
- **Aliases are not onboarded.** The contract allows the model's own name, not `triage`.
- **What is logged.** Token counts, the model, the key and request metadata. Prompts and answers are not logged.

## What it costs

`python tools/cost-model.py --dev-hub` prices one month at list prices from the repository's price snapshot: the private endpoint, about 6.4 euros, and the contract's monthly token quota if it were used in full, about 1 euro. The instance, the private DNS zones and the Log Analytics workspace belong to the landing zone and cost the same without Meternaut. Virtual network, subnet security group and budget are free. It is a sizing, not a billing guarantee: the data the endpoint processes, and any charge of the landing zone's central logging or network manager for this traffic, are not counted. `pause` ends the endpoint's cost.

## Pause and remove

Start the workflow with `pause` to stop the only fixed cost and keep everything else, or with `remove` to take the hub away. To take away the identity and the settings as well, see [Undoing it](BOOTSTRAP.md#undoing-it). A removed model account is soft-deleted and keeps its name for a while; the workflow restores it on the next `deploy`, and the owner can purge it at once.
