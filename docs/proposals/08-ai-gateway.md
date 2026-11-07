# An AI Gateway for the agents' model calls — a decision record

**Status: the owner leans to this route (2026-11-06) and has not yet accepted its one hard fact, that the frontend of the service is public only ([the section](#the-frontend-is-public-only-and-what-protects-it)). Step 1 of 2 is built and not deployed: the template, the workflow actions, the check tool and the numbers. Nothing was made in Azure, and the agents were not touched. Step 2, the connection of the Foundry project to the gateway, is not built, and whether it can be made without a key is not known ([the section](#step-2-and-what-is-not-known-about-it)). A statement that was inferred and not read in a source is marked (inferred).** This page records one decision: the two agents, the Investigator and the Skeptic, call their models through our own AI Gateway, Azure's separate service for that, and not straight to the model deployments. No key is used, and the controls for AI security sit at the gateway. It builds on [the Foundry agents](06-foundry-agents.md), whose exception to the gateway rule it is meant to end, and on [private by default](07-private-by-default.md).

## The owner's words

On 2026-11-06, late in the evening:

> "I have a dedicated AI Gateway you can use or you can deploy your own AI Gateway. IF NEEDED FOR AI SECURITY. SO NOT AN AI GATEWAY IN API MANAGEMENT BUT A SEPARATE AI GATEWAY SERVICE. USE THAT WHEN NEEDED. ... you can make an AI Gateway private. No need for public. I LEAN STRONG TOWARDS YOU CREATING AN AI GATEWAY."

And: "You should NOT create a DDOS PLAN."

One thing in those words did not turn out as said: the frontend of the service cannot be made private. The owner leans to a new gateway, so the template makes one of our own and does not use his dedicated one. No DDoS protection plan is made.

## What the service is

Azure's AI Gateway is a preview service with its own resource type, `Microsoft.ApiManagement/aigateways`. It is not an API Management instance and not the AI gateway feature of API Management. Its portal is `https://ai.gateway.azure.com`. A gateway holds one default workspace, and the workspace holds model providers, models, aliases, policies, telemetry exporters, tool servers and API keys.

- **A call.** A caller sends `POST https://<host>/default/models/openai/v1/chat/completions`. The `model` field of the request is the name of an alias. The host name is the one that the service reports in `properties.frontend.defaultHostname`; nothing here makes one up.
- **A model and an alias.** A provider of kind `Foundry` points to the Foundry resource and calls it with the gateway's own managed identity. A model stands for one deployment. An alias is the name that a caller sends, and it points to one or more models.
- **Access.** A caller needs a Microsoft Entra token for the audience `https://azure-api.net/aigateway` (a managed identity uses the scope `https://azure-api.net/aigateway/.default`), and a role on the gateway: *AI Gateway User* (models and tools), *AI Gateway Models User* (models only) or *AI Gateway Tools User*. An API key is the other way in.
- **Policies.** Each is an entry in an inline array on the workspace (for the whole gateway) or on a model or alias: `tokenLimit`, `requestRateLimit`, `costLimit`, `contentSafety`, `ipFilter`, `fallback`, `cors` and `toolThreatProtection`. A PATCH of the array replaces the whole array.

## What is verified, what is inferred, what is not known

"Verified" means that the statement was read in a first-party source on 2026-11-07 (the sources are at the end). The sources are Microsoft's: the REST specification, the portal's own script, Microsoft Learn and Microsoft's samples for the service.

| Statement | State | Where it comes from |
|---|---|---|
| The service is a separate resource type and not an API Management instance | Verified | The specification of `Microsoft.ApiManagement/AIGateway`, the portal |
| The frontend has no private endpoint, and public network access cannot be switched off | Verified | The private networking sample ("Always Enabled"; Disabled is greyed out with "Unavailable until private frontend access is supported"), the troubleshooting guide of the samples ("Private frontend access isn't available for AI Gateway yet"), the portal's own text, and Microsoft Learn ("Private endpoints aren't supported") |
| The owner's test gateway answered a request for its private link resources with HTTP 400, code `AIGatewayPrivateEndpointsNotEnabled` | Reported with this change; not read again here | The research that came with this change |
| The backend leg can be private: a subnet delegated to `Microsoft.App/environments`, in the gateway's region and subscription, at least a /27, dedicated to the gateway | Verified | The private networking sample, the portal, the specification |
| The portal needs no network security group rule for that subnet; the sample asks for outbound TCP 443 to `Storage` and `AzureKeyVault` | Verified, and the two texts differ | The portal's in-product text and the sample. The default rules of a network security group allow outbound traffic; whether the landing zone's route table and firewall let it through is not known (inferred: the check shows) |
| The children of a gateway work at API version 2025-09-01-preview, the one that the portal and every sample use | Verified | The portal and the samples. The research that came with this change found that the newest version is refused for the child resources at the moment |
| A model's resource name has no dots; an alias's resource name may have them, and its `aliasName` is "the client-facing routing name sent in the request model field" | Verified | The specification (`^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$` for a model, `^[a-zA-Z0-9_.-]+$` for an alias) and the portal's own code, which keeps periods when it makes an alias's resource id and shows `aliasName` or else the name |
| A delegated token for the audience can be issued, and the roles are the three above | Verified | The Entra sample. On 2026-11-07 the owner's own Azure CLI sign-in was issued a token for the audience (`aud` as asked, `scp` `Data.All user_impersonation`) |
| A service principal named "Azure AI Gateway Dataplane", application id `18550318-e177-4205-a743-6816d6fcdc3f`, has to exist in the tenant for an app-only token | Reported with this change; found in no first-party text that was read | Read on 2026-11-07 with the owner's own session, read only: that service principal is not in the tenant, and no service principal there carries the audience's identifier. A token was issued to the owner all the same. Whether the Operator's managed identity can get an app-only token without it is not known. The first `aigateway-check` shows it, and says what to do ([what a person does](#what-a-person-does)) |
| The gateway has no policy for Prompt Shields or jailbreak detection | Verified | The specification and the content safety sample |
| A call has to pass the gateway's policies and the content filter of the deployment | Verified | The content safety sample |
| Foundry's agent-level guardrails are not supported for connected models | Verified | Microsoft Learn, "Bring your own model to Foundry Agent Service" |
| Neither a service tag nor a published address range exists for the Foundry Agent Service | Verified as absent: none was found | Microsoft Learn and the samples |
| One meter, "10k AI Gateway Requests", at 0.00 US dollars for 10 thousand in Sweden Central since 2026-09-01; the service is "free during public preview" | Verified | The Azure Retail Prices API (read on 2026-11-06 and again on 2026-11-07) and the command line tool's page of the samples |
| The preview is offered in East US 2 and Sweden Central | Verified | Microsoft Learn (concepts) |
| A cost limit needs a stable `id`, and a cost limit at the gateway keeps one budget for each caller across all models | Verified | The specification and the cost budget sample |
| Whether a Foundry project's connection can use its managed identity to call this gateway | **Not known** | Microsoft's one sample of a connection to this service uses the category `ModelGateway` with an API key. The category `ApiManagement` supports the project's managed identity, but every sample of it points at `*.azure-api.net` |
| Whether the Responses API works upstream through the gateway | **Not known** | Learn says "coming soon" for the AI Gateway tier. The agents are to use Chat Completions |
| Whether the service lets the built-in key `master` be deleted | **Not known** | The action tries it and records the answer |
| Whether the service accepts two cost limits on one scope (one for the day, one for the month) | **Not known** | The `id` of a cost limit suggests that it does. The action `aigateway` says if it does not |
| Whether the subnet can be changed after the gateway is made | Sources disagree | [The section](#the-subnet-cannot-be-changed) |
| Whether the content safety policy works | Sources disagree | The migration page of Learn says that the policy "isn't supported" for a gateway that was moved. The specification and the content safety sample have it. The template uses it, and the read-back shows whether the service took it |
| Whether the gateway reaches the private Foundry resource through its subnet and the landing zone's DNS, and whether it needs the route table first | Inferred | The sample does the same. The check shows it |
| Whether the narrower role *Cognitive Services OpenAI User* is enough for the gateway's identity instead of *Foundry User* | Not tried | The samples use *Foundry User* |

## The frontend is public only, and what protects it

**The owner believed that the gateway can be made private. It cannot, today.** The service has no private endpoint. Its setting for public network access is greyed out in the portal, and a call to set it to Disabled through Azure Resource Manager succeeds and has no effect. Only the way from the gateway to the Foundry resource can be private: the gateway reaches it through a subnet of our virtual network and the landing zone's DNS. The address that callers use is public.

That breaks the rule of [private by default](07-private-by-default.md), that no resource of the project has a public endpoint. So this is an exception that only the owner can make. **He decides whether to accept it before anything is deployed.** If he does not, the gateway is not made, and nothing is lost: the agents keep calling their own resource, as in [the exception that they have now](06-foundry-agents.md#the-model-path-the-one-exception-to-the-gateway-rule).

What protects the public endpoint:

1. **Microsoft Entra ID, and a role.** A call needs a token for the audience and a role on the gateway. The role is *AI Gateway Models User*: it lets a caller list and use the models and nothing else (not the tools). Today only the Operator's identity holds it, so that it can run the check. Step 2 gives it to the Foundry project's identity. The read-back lists who holds a role of the gateway. A call with no token is refused with HTTP 401, and the check sends one to show it.
2. **No API key resource.** The template makes none. The service makes a key named `master` on every gateway and has no switch to refuse key authentication. The action deletes that key when the service lets it, reads first, and reads back. If the service refuses, that is a recorded finding and not a failure: the key then exists and is unused. This project does not read the key's value. Someone who can read it in the portal could call every model up to the limits below, which is why the finding matters.
3. **Limits at the gateway.** A token limit, a request rate limit and cost limits, each counted for every caller alone across all models. They bound what a stolen token can do. The numbers are in [what step 1 builds](#what-step-1-builds).
4. **Content safety at the gateway,** and the deployment's own guardrail behind it ([the layers](#what-the-gateway-adds-to-ai-security-and-what-it-does-not)).

What is not done, and why:

- **No `ipFilter`.** The samples advise one while the frontend is public. It needs a list of addresses to allow, and there is none to write: Microsoft publishes no service tag and no address range for the Foundry Agent Service (the sources have none), so a list that admits the agents cannot be made. A list that admits the Operator alone would cut the agents off. A list that admits every address protects nothing. The file of limits holds no `ipFilter`, and the builder refuses one.
- **No private endpoint.** The service offers none.
- **No DDoS protection plan.** The owner said not to make one. A plan covers public addresses in a virtual network of ours, and the address of this gateway belongs to the service (inferred).

## What the gateway adds to AI security, and what it does not

It adds one place where each caller's use is counted and capped, a content safety policy on every model, access that is granted to an identity with a role, and a record that can be exported ([the telemetry is off](#telemetry-is-off-and-what-turning-it-on-needs)). It also moves the agents' model calls off a direct dependency on the deployments: the gateway's own identity calls them.

It does not add Prompt Shields. The gateway has no policy for jailbreak or indirect-attack detection. The guardrail `meternaut-agents` stays where it is, on the two model deployments, and a call that the gateway makes to a deployment passes it. Foundry's agent-level guardrails are not supported for connected models (Learn), and Meternaut does not set one ([why](06-foundry-agents.md#not-built-and-not-shown-yet)), so a route through the gateway loses none of the screening that exists today.

| Layer | Where | What it covers | On the route through the gateway |
|---|---|---|---|
| Limits and content safety | The AI Gateway | Each call, for each caller | New |
| Guardrail with Prompt Shields | The two model deployments | Every call that reaches a deployment, from any caller | Still runs: the gateway's calls pass it |
| Typed read-only tools | The cases app's code | What the agents can ask for | Unchanged |
| Checks in code ([rule 30 (b)](../../AGENTS.md)) | The cases app's code | Every finding is compared with what the tools returned, and guards, the Skeptic and a person decide | Unchanged |

## What step 1 builds

Code and documents only. Nothing is deployed.

- **The template** [`environment/aigateway/main.bicep`](../../environment/aigateway/main.bicep). The subnet `snet-aigw` with a network security group that has no rule of its own, delegated to `Microsoft.App/environments`, made once and then left alone ([rule 27](../../AGENTS.md)). The gateway `aigw-meternaut-<digest>` with a system-assigned identity and that subnet as its backend subnet. *Foundry User* for the gateway's identity on the Foundry resource of the agents. One provider, and a model and an alias for each model of [`environment/models.json`](../../environment/models.json) (the model resource has the deployment's name with its dots replaced by hyphens, because a model's resource name allows none; the alias keeps the name, because an alias's allows them). A content safety policy at Medium for the four categories on each model. *AI Gateway Models User* for the Operator's identity, and for the Foundry project's identity when its object id is given (empty means none yet; step 2 gives it). No key, no private DNS object, no `ipFilter`. The optional telemetry is off.
- **The limits** in [`environment/aigateway/policies.json`](../../environment/aigateway/policies.json), applied by the action with a merge, because the workspace exists on its own and only a PATCH changes it: 50,000 tokens a minute (the rate of the deployment that the Investigator uses, the largest of the agents'), 60 requests a minute, and 5 US dollars a day and 25 US dollars a month. They are held to the owner's standing limit of [rule 15 (g)](../../AGENTS.md), 5 and 25 euros, as numbers (a euro is worth more than a dollar: an assumption, not checked against a rate), and the builder refuses a file above it. Each limit counts for every caller identity alone. Two identities may hold the role, the Operator (the check costs cents) and the Foundry project, so the sum of two ceilings can be twice the figure.
- **The actions** `aigateway` and `aigateway-check` in [`deploy-hub.yml`](../../.github/workflows/deploy-hub.yml). `aigateway` reads first and stops before it changes anything if the network, the Foundry resource, the Operator, the region or the condition of the deploy identity's right to assign roles is not as the template needs. It deploys, waits until the landing zone has put its route table on the subnet and says which one, signs in again, applies the limits, deletes the built-in key when the service lets it, and reads the gateway back with [`tools/aigateway-prep.py`](../../tools/aigateway-prep.py): the state, the backend subnet and its delegation, the identity, the provider, every model and alias, the limits, the roles, `publicNetworkAccess` as the service reports it (it is printed and not judged) and the names of the keys (never a value). It fails on any key but the built-in one. `aigateway-check` runs [`tools/aigateway-check.py`](../../tools/aigateway-check.py) in the Operator.
- **The check** sends one small chat completion to each alias with the Operator's own token, then one request with no token (expect 401) and one with an alias that does not exist (expect a refusal), and prints statuses and usage numbers only. It asks for 256 tokens and not 16, because the reasoning models of this project refuse a very small cap, as the first environment's smoke test found.

## Cost

One meter, "10k AI Gateway Requests", which is 0.00 US dollars in Sweden Central on 2026-11-06 and again on 2026-11-07, and the page of the command line tool says the AI Gateway tier is "free during public preview". The subnet and the network security group cost nothing. The model calls cost what they cost now: the deployments are the same. A preview has no service level and its terms may change, and a price may start when the preview ends. A cost of about 50 euros a month, or something that cannot be undone in minutes, is the owner's decision ([rule 15 (g)](../../AGENTS.md)), so a price after the preview is put to him then.

## The subnet cannot be changed

The gateway takes its backend subnet when it is made. Microsoft Learn's quickstart says that networking settings are read-only after creation, and the specification marks `backend` as set at creation. The portal's networking page and its in-product text show a PATCH that sets or clears the subnet on an existing gateway. The sources disagree, so it is treated as fixed.

So the range is chosen once: the last free /26 of the virtual network, or a /27 when no /26 is free (the sample recommends a /24 and wants a /27 at the least; a /24 does not fit in a small network). The builder makes no file, and the action says why, when no /27 is free. The way back from a wrong range is to delete the gateway and make another ([the way back](#the-way-back)). A subnet that the gateway uses is dedicated to it and holds nothing else.

## Step 2 and what is not known about it

Step 2 is a later change and not part of this one. It makes a connection from the Foundry project to the gateway, gives the project's identity *AI Gateway Models User*, and switches the model names of the cases app to the aliases.

The open question is whether the connection can authenticate with the project's managed identity and no key. Three outcomes, and who decides:

| Outcome | What happens | Who decides |
|---|---|---|
| It works without a key | The agents call their models through the gateway. The exception in [rule 15 (c)](../../AGENTS.md) ends | The owner reads the proof and strikes the exception |
| It needs a key | The key would be an API key of the gateway, kept by the platform in the connection. [Rule 23](../../AGENTS.md) says no key | The owner, in plain words, with the finding about the built-in key beside it |
| It fails (the Agent Service cannot call the gateway, or Responses is not supported) | The agents keep calling their deployments, as now. The gateway can stay (it is free) or be deleted | The owner |

## The way back

Nothing in step 1 touches the agents, so they never stopped working and nothing has to be restored. To remove the gateway, delete it: the resource, and then by hand the subnet and the network security group, which cost nothing. A role assignment of the deleted gateway's identity on the Foundry resource stays behind, and a person removes it (the deploy identity's condition lets the workflow delete an assignment of *Foundry User* for a service principal, and no action does it yet). The subnet can then be used by another gateway. The built-in key goes with the gateway.

## What a person does

1. **Decide on the public frontend**, before the first run of `aigateway` ([the section](#the-frontend-is-public-only-and-what-protects-it)).
2. **The hand step in the condition.** The deploy identity may give a role to a service principal only for the roles that its condition lists. *AI Gateway Models User* (`a6b68e3d-a1f0-4c60-8678-237c050cf4ea`) is not in it, and *Foundry User* is. A person adds the one id, with the owner's written word and their own sign-in, and reports at once ([the bootstrap page](../../environment/BOOTSTRAP.md#added-on-2026-11-07-for-the-ai-gateway), [rule 18](../../AGENTS.md)). The action `aigateway` stops before it changes anything, and says so, when the id is not in the condition.
3. **The service principal of the data plane.** Read it first (it was not in the tenant on 2026-11-07). The first `aigateway-check` shows whether the Operator's identity can get a token without it. If the check says that the service principal is missing, a person with the right to create one makes it once, with the owner's word ([the bootstrap page](../../environment/BOOTSTRAP.md#added-on-2026-11-07-for-the-ai-gateway)).
4. **The order of the actions:** `foundry` and `cases` have run, and `operator` has. Then `aigateway`. Wait about ten minutes, because a new role takes up to that long to apply. Then `aigateway-check`.

## Telemetry is off, and what turning it on needs

The template has a switch for an OpenTelemetry exporter to the shared Application Insights component, and it is off. The component is shared with the cases app, and its local authentication is off. Turning the exporter on needs three things that no template can do: the component's Azure Monitor workspace ingestion mode has to be on (a change to a component that the cases app also uses, so the owner decides), the resource provider `Microsoft.Monitor` has to be registered, and the gateway's identity needs *Monitoring Metrics Publisher* on the data collection rule that the component gets. That rule lies in a resource group that the platform manages, behind a deny assignment, so a person gives the role with a direct call to Azure Resource Manager, and the exporter is made after the role has applied. This comes from the samples of the service (the monitoring and OpenTelemetry samples and the enterprise reference) and was not tried. The exporter sends no prompt and no answer (`payloadCapture` is false).

## Choices of step 1 that the owner can change

- API version 2025-09-01-preview for every resource of the service, the one that the portal and every sample use.
- The numbers of the limits, and one cost limit for the day and one for the month.
- Content safety at Medium for the four categories.
- *Foundry User* for the gateway's identity, as the samples do, and not the narrower role, which was not tried.
- The models list their `supportedEndpoints` as chat completions and responses; the Responses route is not tried.
- The alias has the deployment's name, dots included.
- The subnet is the last free /26.

## Sources, read on 2026-11-07

The REST specification of the service, [`Azure/azure-rest-api-specs`, `specification/apimanagement/resource-manager/Microsoft.ApiManagement/AIGateway`](https://github.com/Azure/azure-rest-api-specs/tree/main/specification/apimanagement/resource-manager/Microsoft.ApiManagement/AIGateway). The portal's own script, `https://ai.gateway.azure.com`. Microsoft's samples for the service, [`Azure/aigateway`](https://github.com/Azure/aigateway): [the troubleshooting guide](https://github.com/Azure/aigateway/blob/main/labs/TROUBLESHOOTING.md), [private networking](https://github.com/Azure/aigateway/blob/main/labs/18-private-networking/README.md), [Microsoft Entra ID and roles](https://github.com/Azure/aigateway/blob/main/labs/11-entra-rbac/README.md), [cost budgets](https://github.com/Azure/aigateway/blob/main/labs/07-cost-budgets/README.md), [the first model call](https://github.com/Azure/aigateway/blob/main/labs/02-first-model-call/infra/publish-model.bicep) and [the script that merges the limits](https://github.com/Azure/aigateway/blob/main/labs/21-enterprise-reference/infra/scripts/apply-baselines.sh). Microsoft Learn: the articles of the AI Gateway (their source is [`MicrosoftDocs/azure-docs`, `articles/ai-gateway`](https://github.com/MicrosoftDocs/azure-docs/tree/main/articles/ai-gateway)) and [Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway). The Azure Retail Prices API, meter "10k AI Gateway Requests".
