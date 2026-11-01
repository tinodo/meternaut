# A1 — The Citadel framework: a precise digest

> Evidence for the design, not the design. Written 2026-10-31 by research agent A1. Everything below was read on the page today unless marked `UNVERIFIED`. Source ids `S1…S24` are in §12 (all fetched). Prices are EUR, retrieved 2026-10-31 from the Azure Retail Prices API, 730 h per month, West Europe unless stated. Where a page and the attachment disagree, the page wins and the text says so. "Citadel" means the Governance Hub accelerator unless stated; `R/` is the raw root of its repository (§12).

## 0. Bottom line

**ADOPT Citadel Governance Hub v1 as the gateway for H2 and H3 — forked, pinned to a commit, and with six conditions the design must carry.**

1. It is a Microsoft-authored *sample* (Azure-Samples, MIT), not a supported service: no GitHub releases or tags, one main committer, commits fell from 60 (July) to 3 (September) [S3].
2. It runs on Azure API Management (`Microsoft.ApiManagement/service`), **not** on the new standalone *AI Gateway* product (`Microsoft.ApiManagement/aigateways`, preview, East US 2 and Sweden Central only) [S13]. Contracts are infrastructure as code, so a later move is a re-implementation of three contract types, not a re-architecture.
3. Its monthly floor is the always-on *usage pipeline* (Cosmos DB 7 × 400 RU/s, Logic App WS1, Event Hubs ≈ €321), not API Management: for the small hub that is 73 % of ≈ €440 (§7).
4. The shipped defaults go stale and loosen security (public APIM endpoint, Event Hubs public, full prompt and completion capture to Log Analytics, retired model names) (§8).
5. The Publish Contract (MCP tools, A2A agents) is preview and writes preview ARM properties (§3.2). Keep the native-APIM import path as the fallback.
6. Foundry's own portal gateway integration and the Citadel connection route are two different mechanisms; use only the Citadel route on our hub (§8).

| Item | Status (date) | Disposition | Fit | Note |
|---|---|---|---|---|
| Citadel Governance Hub v1 (Bicep) | GA, *self-declared* (repo docs 2026-08-06; `master-version` 1.0.3 on `main`, 2026-10-27) [S2,S3] | ADOPT | GW GOV SEC OBS | Pin a commit SHA; no tags exist |
| Backend Contract `1.1.0` | GA (self-declared) | ADOPT | GW MOD | §3.1 |
| Access Contract `1.2.0` | GA (self-declared) | ADOPT | GW ID GOV COST | §3.3 |
| Publish Contract `1.1.0-preview` | Public preview (repo label "Preview") | ADOPT-PREVIEW | GW TOOL | Fallback: import MCP/A2A natively in APIM, grant via Access Contract |
| APIM Gateway Upgrade `1.0.0-preview` | Public preview (repo label "Preview") | ADOPT-PREVIEW | OPS | The standard upgrade path; also the only route onto an existing APIM [S9] |
| Terraform twin `Azure/terraform-ai-gateway-landing-zone` | No releases or tags; created 2026-06-03 [S3] | WATCH | OPS | We use Bicep (H12) |
| AI Landing Zone for Foundry (foundation in Agent Landing Zone, v5.6.0 on 2026-10-30) | README: "currently in preview"; site news: GA since 2025-11-17 — contradiction [S19] | ADOPT-PREVIEW | NET AGT OPS | Fallback: Foundry sample templates 15/19 [S16,S20]; 22 releases in October |
| AI Gateway (`aigateways`) | Public preview; East US 2, Sweden Central; older `AIGateway` SKU *retiring 2027-01-15* [S13] | WATCH | GW | Not parity with APIM; §8 |
| Foundry portal AI Gateway (APIM v2, same subscription) | Public preview [S12] | WATCH | GW | Clashes with Citadel central hub (§8) |
| Foundry bring-your-own-model connections (`ApiManagement`, `ModelGateway`) | GA 2026-04-27 (attachment L563; Learn page 2026-10-25 shows no preview banner) [S15] | ADOPT | AGT GW | Used by the Access Contract |
| APIM MCP servers | GA (attachment L354, 2026-06-10) | ADOPT | TOOL | |
| APIM A2A agent API | Not stated on the Learn page (2026-05-06) [S17]; Citadel docs call it preview; Foundry incoming A2A v1.0 is preview, JSON-RPC only [S7] | WATCH | TOOL | Our agents orchestrate in-process (H1) |
| APIM unified model API | Public preview, "rolling out" [S17] | WATCH | GW MOD | Citadel's own Unified AI API covers it |
| Semantic caching (`llm-semantic-cache-*`) | GA policy, all tiers [S17]; Citadel provisions only the enabler | EVALUATE | GW COST | Probably off for our workloads (§4) |
| Agent 365 ↔ APIM tool governance | Public preview; tool-level control only on the AI Gateway product [S17] | WATCH | ID SEC | Layer 3 of the Blueprint; licensing (A4) |

---

## 1. What Citadel is

- **Three things share the name.** (a) *AI Citadel Blueprint*: a four-layer governance architecture defined in `Azure-Samples/foundry-citadel-platform` (MIT, created 2025-10-02; footer "Microsoft · Global Black Belt") [S10]. L1 Governance Hub (runtime gateway), L2 Agent Operations (Foundry control plane), L3 Agent Management (Agent 365: identity and lifecycle, licence per user), L4 Security Foundation (Defender, Purview, Entra). (b) *Citadel Governance Hub*: the L1 reference implementation, `Azure-Samples/ai-hub-gateway-solution-accelerator` (short link aka.ms/ai-hub-gateway; created 2024-05-06; 322 stars, 213 forks) [S1,S3]; the AI Landing Zones site republishes it as the "AI Gateway Landing Zone" [S19]. (c) Practitioners say "Foundry Citadel Platform" for both [S21].
- Where the name is defined: the Blueprint repository's README, and the Tech Community post of 2026-09-11, which says the architecture is "opinionated" and that "there is no separate Citadel runtime" — it is configuration of native Azure services [S11]. That post also warns that adopters must assess feature availability, preview status and cost per service.
- Topology: hub-and-spoke. One central hub governs production and non-production, or two (prod, non-prod); one Foundry landing zone per business unit or use case is the spoke [S10].

| Attribute | Evidence |
|---|---|
| Maintainer | GitHub `mohamedsaif` (560 commits; next contributor 5) [S3]; Microsoft Global Black Belt (footer). Support = GitHub issues; no SLA stated [S1] |
| Licence | MIT [S1,S3] |
| Versioning | `release.json` tracks: master 1.0.3, routing 1.0.1, backend-contract 1.1.0, access-contract 1.2.0, publish-contract 1.1.0-preview, gateway-upgrade 1.0.0-preview, usage-ingestion 1.1.0 [S2]. SemVer; `-preview` tracks may still change, so pin an exact version in production [S2] |
| Releases | None, no tags. Branches: `main` (head 2026-10-27), `citadel-v1` (now merged into main), `citadel-v1-archive`, `-archive-2`, `main-archive-pre-ga`, `main-archive-v1…v4` — four earlier restructures [S3] |
| Cadence | Commits on `main`: Jan 31, Feb 20, Mar 22, Apr 25, May 38, Jun 31, **Jul 60**, Aug 30, Sep 3, Oct 2 [S3] |
| Open issues | 10; #123 "use an existing APIM" open since 2026-06-12; #175 `unified-ai` BackendConnectionFailure (2026-10-22) [S3,S23] |
| Practitioner view | June: "The repos, parameter schemas, and CLI commands will change"; August: v1 repositions the sample as Layer 1 and labels the old API surface legacy [S21] |

---

## 2. Architecture

### 2.1 Hub components (defaults read from the Bicep, not the README)

| Component | README class | Default configuration | Cost meter / note |
|---|---|---|---|
| API Management | Required | `apimSku` ∈ Developer, Premium, StandardV2, PremiumV2; parameter default Developer ×1; `apimNetworkType` External [S4] | §2.2, §7 |
| Foundry account (`AIServices`, API `2026-01-15-preview`), project `citadel-governance-project` | Required | Serves **Content Safety and Language PII** for the gateway (no separate Content Safety or Language resource is deployed); optional model deployments; agent-subnet network injection off by default (`foundryNetworkInjectionEnabled`) [S4,S5] | No fixed meter; text records |
| API Center | Recommended | Free SKU; `enableAPICenter` is `false` in `main.bicepparam`, `true` in `main.bicep` (mismatch) | Registry for MCP and A2A assets |
| Log Analytics + 3 workspace-based Application Insights (APIM, Logic App, Foundry) | Required | PerGB2018, 30-day retention; BYO workspace supported; custom metrics with dimensions | €2.63/GB after 5 GB |
| Event Hubs | Required | Standard, 1 TU, auto-inflate to 20, 7-day retention; hubs: usage (4 partitions), PII (2) | €19.27 + €0.0246/1M events |
| Cosmos DB (NoSQL) | Required | One region, not zone-redundant, public access disabled; **7 containers, each with its own 400 RU/s**: `ai-usage`, `model-pricing`, `pii-usage`, `llm-usage`, `mcp-usage`, `agent-usage`, `streaming-export-config` | €143/month |
| Logic App Standard **WS1** + storage account (4 private endpoints) | Required | Usage ingestion workflows (llm, ai, pii, mcp, agent); always on | €158/month |
| Key Vault | Required | Standard, public access disabled, soft-delete 90 days, purge protection | ~€0 |
| Azure Managed Redis + embeddings backend | Optional | `enableManagedRedis` false in params (Balanced_B1), true in Bicep (Balanced_B10) | B1 €24, B10 €241 |
| 2 user-assigned identities, VNet, NSGs, private DNS zones | Required | §2.3 | Private endpoint €6.42 each |

### 2.2 Which APIM tier, and why

- The `llm-*` AI policies exist in Developer, Basic, Basic v2, Standard, Standard v2, Premium, Premium v2 — **not Consumption** [S17]. Citadel's allow-list narrows to Developer, Premium, Standard v2 and Premium v2 (our reading: Basic and Basic v2 lack network isolation [S17]).
- Anthropic Messages support, the Foundry portal gateway and the Agent 365 integration need a **v2** tier [S12,S15,S17]. v2 has no multi-region deployment, no backup/restore, no Git configuration, no DDoS Protection, no in-place upgrade from classic [S17]; Citadel's answer to disaster recovery is *multiple full deployments* on Standard v2 behind Front Door or Traffic Manager, not Premium multi-region [S9].
- Network shapes: Developer/Premium classic = VNet injection (needs NSG rules and a route table for the `ApiManagement` tag); Standard v2 = outbound VNet integration (subnet delegated `Microsoft.Web/serverFarms`) plus inbound private endpoint (`apimV2UsePrivateEndpoint`, `apimV2PublicNetworkAccess`); Premium v2 adds injection [S5,S17].
- SLA: Developer none; Basic v2 and Standard v2 99.95 %; Premium v2 99.99 % with zones [S17]. Developer is priced for "non-production use cases and evaluations".
- Sizing guide: Small = no SLA, development only (SKU not named); Medium classic = Premium (≈ 300–500 PTU); Medium v2 = Standard v2 (≈ 200 PTU per unit; scale out by units); Large = multi-zone production (≈ 1,000–1,500 PTU). Its snippet says the default is `StandardV2`; `main.bicepparam` says `Developer`. The code wins [S5,S4].

### 2.3 Networking

- Two patterns: **hub-based** (gateway subnets inside the existing hub VNet) and **hub-spoke-hub** (own spoke VNet peered to the hub; traffic from agent spokes passes the hub firewall first) — the second is the README's recommendation for strict segmentation [S1,S5].
- Greenfield VNet `10.170.0.0/24`: APIM /26, private endpoints /26, Logic App /26 (delegated `Microsoft.Web/serverFarms`), agent /26 (delegated `Microsoft.App/environments`, only when `foundryNetworkInjectionEnabled`). Brownfield: `useExistingVnet` plus subnet names; delegation is exclusive [S5].
- DNS: 12 private zones (cognitiveservices, openai, services.ai, vaultcore, monitor, servicebus, documents, blob, file, table, queue, azure-api) plus azurewebsites and redis when those options are on. Bring them by resource id per zone (`existingPrivateDnsZones`, preferred) or by a single resource group (legacy). Peering does not carry DNS [S5].
- Defaults: Cosmos, Foundry, Key Vault, Redis public access **Disabled**; Event Hubs **Enabled** (must stay enabled during first provisioning with v2 SKUs); Logic App public **true** and no private endpoint; APIM **External**. Fully private = `apimNetworkType=Internal` (or the v2 flags), Logic App flags, `useAzureMonitorPrivateLinkScope` (a global resource that affects every workspace sharing the scope) [S5].
- One Foundry account can expose a private endpoint in each gateway region (the guide's example: Sweden Central account, endpoints in Sweden Central and West Europe) [S9].

### 2.4 Identity

- **Caller → gateway:** the APIM subscription key is *always* required; Entra JWT is layered on per product (`jwtRequired`). JWT-only is "coming soon" [S9]. The `security-handler` fragment validates audience, issuer, signature and expiry; identity comes from `azp`; overrides per product: `jwtAudience`, `jwtIssuer`, `jwtOpenIdConfigUrl` (named values `JWT-TenantId`, `JWT-AppRegistrationId`, `JWT-Issuer`, `JWT-OpenIdConfigUrl`) [S6].
- **Roles and scopes:** the gateway app registration (created by `entra-id-setup/setup.ps1`) defines app roles `Model.Invoke`, `MCP.Invoke`, `Agent.Invoke` and one delegated scope `access_as_user`. A product requires them with `requiredRoles` (OR logic, 403 `insufficient_role`). Roles must be assigned **directly** to service principals and managed identities; group assignments reach users only [S9].
- **Foundry connection:** default `ProjectManagedIdentity` sends the project's managed-identity token (audience `https://cognitiveservices.azure.com`, issuer `https://sts.windows.net/{tenant}/` — v1 tokens) *and* the subscription key as an `api-key` header; the product policy must validate both. Optional hardening — check the token's client id equals the project identity — is not built in [S6].
- **Gateway → backends:** the APIM user-assigned identity needs `Cognitive Services OpenAI User` (Azure OpenAI) or `Cognitive Services User` (Foundry); other providers use named values (Key Vault references preferred) [S8].
- Entra Agent ID tokens are not mentioned anywhere in the hub: `UNVERIFIED` whether `azp` matches an agent identity.

---

## 3. The three contracts

All three are `.bicepparam` files against subscription-scope Bicep (`az deployment sub create`). Access contracts live in `contracts/<business-unit>/<use-case>/<env>/`, publish contracts in `contracts/<contract-name>/<env>/`; both trees are git-ignored in the accelerator, so teams keep theirs in their own repository [S6,S7]. The backend contract is one `main.bicepparam` [S8].

| | Backend Contract | Publish Contract | Access Contract |
|---|---|---|---|
| Answers | *Where* LLM traffic goes (supply) | *What* tools and agents exist (publishing) | *Who* may use *what*, under which limits (demand) |
| Module | `bicep/infra/llm-backend-onboarding` | `bicep/infra/citadel-publish-contracts` | `bicep/infra/citadel-access-contracts` |
| Version / status | `1.1.0` GA | `1.1.0-preview` | `1.2.0` GA |
| Generates | APIM backends, pools, routing fragments, `/version/backend-contract` | APIM APIs of type `mcp` / `a2a`, backends, baseline policy, App Insights metrics, optional API Center entry | APIM product, subscription, policy, Key Vault secrets, Foundry connection |
| Order | first | second | last (grants only what exists) |

### 3.1 Backend Contract

Top-level parameters: `apim` {subscriptionId, resourceGroupName, name}; `apimManagedIdentity` {same three}; `llmBackendConfig[]`; `modelAliases[]` (default empty); `configureCircuitBreaker` (true); `circuitBreakerDefaults`; `configureSessionAffinity` (true); `sessionAffinityDefaults`; for Bedrock only `awsAccessKey`, `awsSecretKey`, `awsRegion` (otherwise named values hold `NOT_CONFIGURED`) [S8].

| `llmBackendConfig[]` field | Type · default · allowed |
|---|---|
| `backendId`, `endpoint`, `backendType`, `supportedModels[]` | required. `backendType` ∈ `ai-foundry`, `azure-openai`, `aws-bedrock`, `aws-bedrock-mantle`, `gemini`, `gemini-openai`, `anthropic`, `azure-flux`, `azure-mai`, `external` |
| `authType` | derived (`ai-foundry`/`azure-openai` → `managed-identity`); else `aws-sigv4`, `api-key-bearer`, `api-key-header`, `api-key-gemini`, `api-key-anthropic`, `none` |
| `authConfig` | `{namedValueKey, keyVaultSecretUri?, secretValue?}` for `api-key-*` |
| `priority` / `weight` | 1–5 (default 1; lower first) / 1–1000 (default 100) |
| `circuitBreaker` | per-backend override: `failureCount` 3, `failureInterval` PT5M, `tripDuration` PT1M, `acceptRetryAfter` true, `errorReasons` ["Server errors"], `statusCodeRanges` 429 and 500–503, `enabled` |
| `sessionAffinity` | `{cookieName: 'ai-gateway-affinity', source: 'Cookie'}` |
| model: `name` | required |
| model: `sku`, `capacity`, `modelFormat`, `modelVersion` | defaults `Standard`, 100, `OpenAI`, `1`; metadata for discovery |
| model: `retirementDate`, `apiVersion` (`2024-02-15-preview`), `timeout` (120 s), `inferenceApiVersion` | metadata and routing |
| model: `sessionAwareModel` | false; true makes a multi-backend pool sticky (Responses/Assistants state) |
| model: `modelPath` | required for `azure-flux` |

`modelAliases[]`: `name` (must not equal a real model), `models[]` (ordered, any providers *but one wire spec*), `strategy` `priority` (default) or `weighted`, `weights[]` (same length). Access control runs on the alias name; on 429 or 5xx before streaming the gateway walks the remaining members, so fallback can cross providers; no protocol translation (a Foundry-or-Bedrock Claude passthrough is "planned") [S8].
Generates: one APIM backend per entry (with the circuit-breaker rule), pools where ≥ 2 backends serve a model, fragments (`set-backend-pools`, `set-target-backend-pool`, `resolve-model-alias`, `get-available-models`, `metadata-config`, `backend-contract`) and a refreshed `GET /version/backend-contract` (secrets redacted). **It registers, it does not deploy** models — deployments come from `aiFoundryInstances` and `aiFoundryModelsConfig` in the main template [S4].

### 3.2 Publish Contract (preview)

Global parameters [S7]: `apim`; `appInsightsLoggerName` (`appinsights-logger`); `managedIdentityClientId` (empty = APIM system identity; for A2A a user-assigned identity holding Foundry Agent Consumer or Azure AI User); `configureCircuitBreaker` (true); `circuitBreakerDefaults`; `ensureUsageFragments` (true); `useAssetTypePathPrefix` (true); `apiCenter` {subscriptionId, resourceGroupName, serviceName, workspaceName}; `publishAssets[]`.

| `assetType` | Endpoint (prefix on) | Backend | Type-specific fields |
|---|---|---|---|
| `mcp-from-api` | `{gw}/mcp/{path}/mcp` | reuses the source API's | `sourceApiName`, `operationNames[]` (the tool allow-list), `subscriptionRequired` (true), `subscriptionKeyHeaderName` (`api-key` or `Ocp-Apim-Subscription-Key`), `forwardSubscriptionKeyToSource` (false), `sourceSubscriptionKeyHeaderName` (`x-mcp-sub-key`) |
| `mcp-existing` | `{gw}/mcp/{path}` | new `<name>-backend` + circuit breaker | `transportType` (`streamable`), `subscriptionRequired` (true), `backend {url, authType, authConfig?, circuitBreaker?}` |
| `a2a` | `{gw}/agent/{path}`; card at `/.well-known/agent.json` | none; managed identity in policy | `agentId`, `agentCardPath`, `agentCardBackendUrl`, `jsonRpcPath` (`/`), `subscriptionRequired` (false), `backend {url, authType, authConfig {resource: https://ai.azure.com}}`; url pattern `https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a` |

Common asset fields: `name`, `displayName`, `description`, `path`, `pathPrefix?`, `policyXml?`, `metadata {version, owner, contactEmail, compliance[], classification: public|internal|confidential}`, `publishToApiCenter?`, `apiCenter {environmentName, lifecycleStage?, versionName?, customProperties?, documentationUrl?, contacts?}`. Backend `authType`: `none`, `managed-identity` (`{resource}`), `api-key-header`, `api-key-bearer` (`{headerName?, namedValueKey, keyVaultSecretUri? | secretValue?}`; prefer Key Vault).

What to know:
- The modules write **preview ARM properties** unknown to Bicep types (`mcpTools`, `backendId`, `mcpPropperties` [sic], `a2aProperties`, `jsonRpcProperties`; API versions `2024-06-01-preview`, `2025-09-01-preview`; BCP037 suppressed). Linters will complain; pin.
- MCP responses stream (SSE): policies must not read the response body, so inbound auth, usage, PII and content safety work; **response-side PII de-anonymization and content safety do not**.
- `mcp-from-api`: the source API must *not* require its own key (otherwise `tools/call` fails with 401 while `initialize` and `tools/list` pass) — unless `forwardSubscriptionKeyToSource: true` and the source reads the forwarded custom header.
- A2A: the publish guide contradicts itself — its auth section says APIM's A2A preview does not validate subscription keys (anonymous in phase 1), its Foundry-A2A notes say client access is subscription-key based; the sample sets `false`. `UNVERIFIED` which holds; test before relying on it. Foundry's incoming A2A is preview, serves v0.3 by default (`A2A-Version: 1.0` for v1.0), JSON-RPC only, text-only, no streaming; it needs Entra, not keys. The gateway rewrites card transport URLs so clients stay on the gateway.
- Enabling the prefix changes every public URL; Key Vault endpoint secrets and Foundry connections keep the old URL until the Access Contract is redeployed.
- Usage: App Insights metrics `McpRequests` (namespace `mcp-usage`) and `A2ARequests` (`a2a-usage`) with `deploymentName` = tool or agent; two scheduled Logic Apps roll them into Cosmos containers.
- Circuit breaker applies to `mcp-existing` only; add a retry policy for A2A.

### 3.3 Access Contract

Parameters [S6]: `apim`, `keyVault` (**required even when unused**), `useTargetAzureKeyVault` (Bicep default **true**; the README table says false), `useCase` {businessUnit, useCaseName, environment}, `apiNameMapping` (code → API names), `services[]`, `productTerms`, `useTargetFoundry` (false), `foundry` {subscriptionId, resourceGroupName, accountName, projectName}, `foundryConfig`, key rotation (`usePrimaryKey` true, `keyRotationEnabled` false, `rotationKeySeed`, `rotationKeyOverride`), resilience (`globalGatewayUrl`, `additionalApimGateways[]`, `additionalKeyVaults[]`, `additionalFoundries[]` with `endpointSource` ∈ `global`, `primary`, `secondary:<n>`).

| `services[]` field | Meaning |
|---|---|
| `code` | `LLM`, `TOOL`, `AGENT` (single type) or `MULTI` (two or more); also `DOC`, `SRCH`, `OAIRT` in the sample mapping. Drives the product name |
| `apiKeySecretName` | the one shared key secret |
| `endpointSecretName` | legacy: endpoint of the *first* API |
| `assetEndpoints[]` / `publishAllAssetEndpoints` | one endpoint secret per asset (`{apiName, endpointSecretName?}`; auto name `<code>-<bu>-<uc>-<env>-<api>-endpoint`) |
| `foundryApiName` | which granted API is the LLM endpoint for the Foundry connection |
| `policyXml` | product policy; empty = `default-ai-product-policy.xml` (LLM) or `default-multi-product-policy.xml` (TOOL/AGENT/MULTI) |

`foundryConfig`: `connectionNamePrefix` (empty ⇒ `Hub-<BU>-<UseCase>-<ENV>`; README examples omit `Hub-`), `connectionCategory` `ApiManagement` | `ModelGateway`, `authType` `ProjectManagedIdentity` | `ApiKey`, `managedIdentityAudience`, `deploymentInPath`, `isSharedToAll` (false; the base contract sets true), `inferenceAPIVersion`, `deploymentAPIVersion`, `staticModels[]`, `listModelsEndpoint`, `getModelEndpoint`, `deploymentProvider` (`AzureOpenAI`|`OpenAI`), `customHeaders`, `authConfig`. The connection carries **the LLM endpoint only**; tools and agents in a `MULTI` contract are reached through Key Vault endpoint secrets plus the same key.

Creates, per service: APIM product `{code}-{BU}-{UseCase}-{ENV}` (`subscriptionRequired: true`, `approvalRequired: false`, `subscriptionsLimit: 10`, `state: published`), the APIs, the policy, subscription `{product}-SUB-01` scoped to the product (two keys), Key Vault secrets (key and endpoints), connection `<prefix>-<code>` in the Foundry project. Deployment identity needs API Management Service Contributor, Key Vault Secrets Officer, Contributor on the Foundry resource group, Reader on the subscription.

Policy knobs set in the product policy (variables unless noted): `allowedModels` (CSV; alias names), `llm-token-limit` (`tokens-per-minute`, `token-quota`, `token-quota-period` Hourly…Yearly, `estimate-prompt-tokens` — **false in the shipped defaults**), `rate-limit-by-key`/`quota-by-key` for tools and agents (60 and 30 calls/min; 10,000 and 5,000 calls per 30 days), `jwtRequired`, `jwtAudience`, `jwtIssuer`, `jwtOpenIdConfigUrl`, `requiredRoles`, `llm-content-safety`, `piiAnonymizationEnabled`, `piiBlockingEnabled`, `piiConfidenceThreshold` (0.8), `piiEntityCategoryExclusions`, `piiDetectionLanguage` (`en`|`auto`), `piiRegexPatterns`, `piiMaxChunkSize` (5000), `piiChunkOverlap` (250), `piiStateSavingEnabled`, `customDimension1/2`, `appId`, `alertsEnabled` and `alertOnThrottling|QuotaExceeded|BackendFailure|AuthFailure|ContentSafety|PiiFailure`, `enableResponseHeaders`, `contractToolApis`, `contractAgentApis`, `allowedBackendPools`. The shipped LLM default allows `gpt-4.1,gpt-5.4-mini` at 1,000 tokens/min and 100,000 tokens/month.

### 3.4 Onboarding flows

- **New agent (greenfield spoke):** backend contract in place → deploy the spoke (project identity enabled) → add `contracts/<bu>/<uc>/<env>/main.bicepparam` plus `ai-product-policy.xml` → `what-if` → deploy → the contract writes key and endpoints to Key Vault and creates the Foundry connection → the agent names its model `<connection>/<model>`, e.g. `Hub-HR-ChatAgent-DEV-LLM/gpt-4.1` (derived from the naming rule) → validate with the access-contract notebook [S6,S18].
- **Existing agent:** repoint endpoint and key to the contract's (read from Key Vault); surfaces: `/unified-ai/v1/*` (recommended), `/models/*` (OpenAI-v1 only), `/openai/deployments/*` (legacy, Azure OpenAI URL shape); JWT optional [S9].
- **Publish then grant:** publish contract first; add the asset's API name to `apiNameMapping['MULTI']`; one key covers LLM, tools and agents.
- **Day 2:** key rotation takes three redeployments: baseline (`usePrimaryKey=true`); `usePrimaryKey=false` pushes the secondary key to Key Vault, connections and mirrored gateways while the primary still works; after owners confirm, `keyRotationEnabled=true` regenerates the idle key [S6]. Upgrade with APIM Gateway Upgrade, never by re-running `main.bicep`; `GET /version` and `/version/backend-contract` (anonymous) show what is live [S2].
- The Python helper `shared/contracttools.py` renders `.bicepparam`, validates policy XML, refuses secrets in parameters, previews and deploys (`access_policy(allowed_models, tokens_per_minute, token_quota, token_quota_period, …)`); it could back agent-drafted contract pull requests (our inference) [S9]. The notebook's "contract request JSON" schema (`policies.jwtAuth.enabled`) is not in that file: `UNVERIFIED`.

---

## 4. Safeguards the gateway enforces

| Safeguard | Mechanism and knob | Status | Notes |
|---|---|---|---|
| Token limits and quotas | `llm-token-limit`, counter per `context.Subscription.Id`; TPM → 429, quota → 403 | GA (policy: Developer…Premium v2; Anthropic Messages only on v2) [S17] | Several scopes stack and the tightest wins [S21]; set `estimate-prompt-tokens=true` for hard budgets |
| Call limits for tools and agents | `rate-limit-by-key`, `quota-by-key` in the multi-asset policy | GA policies | Tokens do not exist for a tool call |
| Model RBAC | `validate-model-access`; 401 `unauthorized_model_access` | Citadel GA | Works on alias names |
| Content safety, prompt shields | `llm-content-safety` (`backend-id=content-safety-backend`, `shield-prompt`, categories Hate/SelfHarm/Sexual/Violence, `EightSeverityLevels`, blocklists, `enforce-on-completions` — false in the sample); 403 on block; also for MCP and A2A (GA 2026-06, attachment L473) | GA | Prompt Shields are limited to 10,000 characters (turn `shield-prompt` off for longer input); €0.33/1K text records; **commented out** in the multi-asset default |
| PII | Citadel fragments over Azure AI Language: anonymize inbound, de-anonymize outbound, `pii-state-saving` to Event Hubs; blocking mode returns 400 | GA in Citadel | Chunks of 5,000 characters (overlap 250); text beyond ≈ 125,000 characters is not analysed (trace warning only); MCP inbound only; €0.88 → €0.22/1K records |
| Authentication | Subscription key always; JWT per product; app roles | GA | JWT-only not yet; keys are shared by everyone holding the connection |
| Semantic caching | APIM `caches` entity on Managed Redis + embeddings backend are provisioned; **no `llm-semantic-cache-*` call appears in the shipped API policies** (searched, none) | Enabler only | A June write-up of the earlier iteration shows `azure-openai-semantic-cache-lookup` at score-threshold 0.8; its cache is shared by all subscribers to a product unless the key is scoped per subscription [S21]. The policy page warns of stale or unsafe hits [S17] |
| Load balancing, failover | Pools by priority/weight; on 429/5xx the retry block walks backends and remaining alias members; session-affinity cookie for stateful models | GA (routing 1.0.1) | No fallback once streaming has started |
| Circuit breaking | APIM backend breaker, defaults above, honours `Retry-After` | GA | Per backend; MCP assets too |
| Responses API isolation | `response_id` owned per subscription and product; cached 30 days | GA | Cross-owner access → 403/404 |
| Usage logging | `ApiManagementGatewayLlmLogs`; App Insights `llm-usage` (dims `productName`, `deploymentName`, `Backend ID`, `appId`, `customDimension1/2`); Event Hubs → Logic App → Cosmos | GA | **Default `largeLanguageModel` logging captures prompts and completions up to 256 KB each** [S4,S9] |
| Cost attribution | Cosmos `model-pricing` container + Power BI template; prices seeded by hand | GA | Estimates, not billing truth; prices go stale |
| Alerts | `raise-alert-events` metric `AI Gateway Alert` (namespace `ai-gateway-alerts`); on: throttling, quota, backend failure; off: auth, content safety, PII | GA | The token-metric policy takes at most six custom dimensions |
| Dashboards | APIM analytics, optional App Insights dashboards (off by default), Power BI | GA | Power BI is outside our stack |
| Release visibility | `/version`, `/version/backend-contract` | GA | Usable as a drift probe |

Not in the hub: AI evaluation at the gateway, Defender and Purview enablement ("coming soon" [S9]); tool threat protection by Defender and Purview exists only on the AI Gateway product and needs delegated (on-behalf-of) tokens, so app-only agents cannot use it [S14].

---

## 5. The AI Landing Zone for Microsoft Foundry (the spoke)

- **Naming.** The reference lives on a docs site and in three repositories: `Azure/AI-Landing-Zones` (docs), `Azure/agent-landing-zone` (the Bicep foundation under `infra/bicep` plus a hosted-agent application; MIT, created 2023-06-27 as GPT-RAG; **22 releases from v4.0.0 on 2026-10-03 to v5.6.0 on 2026-10-30, six of them on 2026-10-27**, two major versions) and `Azure/bicep-ptn-aiml-landing-zone` (standalone Bicep; v2.7.3 on 2026-09-25, still pushed to on 2026-10-30) [S3,S19]. The docs site says the foundation "is maintained in" Agent Landing Zone; `UNVERIFIED` which repository to pin. Terraform: a guide since 2025-11-17, azd-integrated from v5.4.0 (2026-10-28); Bicep stays the default.
- **What it deploys**: Foundry account and project; default models `gpt-5-nano` and `text-embedding-3-large`, both **GlobalStandard**; **Standard Agent Setup** = a second, Foundry-dedicated AI Search, Storage and Cosmos beside the workload's own; workload Search, Storage, Cosmos, Key Vault; App Configuration; Container Registry Premium; a Container Apps environment whose D4 profile is pinned by `min_replicas=1`; Log Analytics and App Insights; with isolation: VNet, NSGs, ~13–15 private endpoints, 15 private DNS zones, firewall, Bastion, jump box, NAT gateway; add-ons: Application Gateway WAF v2, Speech, Bing grounding [S19].
- **Foundry specifics** [S16]: delegated agent subnet `Microsoft.App/environments`, exclusive to one Foundry account, ≥ /27 (/24 for hosted agents), RFC 1918 or 100.64.0.0/10 only; Foundry account and VNet in the **same region**; network injection must be set when the account is created and cannot be added later for hosted agents; BYO Storage, Search and Cosmos for the standard setup (Foundry's alternative: BYO VNet with platform-managed data resources, sample template 11); private endpoints to those three are **not** auto-created; a **project-level capability host** is required before tool calls leave Foundry through the VNet; private ACR works only for projects created after 2026-06-25; Azure Blob files with File Search unsupported; Code Interpreter file transfer limited in private setups. Caller roles for capability settings (`2026-07-15-preview`): Storage Blob Data Contributor and Cosmos DB Operator on the BYO accounts.
- **Prerequisites:** providers `Microsoft.KeyVault`, `CognitiveServices`, `Storage`, `MachineLearningServices`, `Search`, `Network`, `App`, `ContainerService` (`Bing` for Bing grounding); provisioning and runtime use two identities with separate roles; reverse peering and DNS links belong to the hub teams [S16,S19]. `NETWORK_ISOLATION` **defaults to false**; `DEPLOYMENT_MODE=ailz-integrated` only records intent [S19].
- **Regions** with a full deployment (README of `Azure/AI-Landing-Zones`): australiaeast, eastus, francecentral, germanywestcentral, japaneast, koreacentral, norwayeast, polandcentral, southafricanorth, southeastasia, spaincentral, **swedencentral**, switzerlandnorth, uaenorth, uksouth — **not West Europe or North Europe**; partial deployments are unsupported [S19]. AI Search Standard capacity is often exhausted in Sweden Central (`ResourcesForSkuUnavailable`) [S21].
- **Cost** (USD, East US 2, snapshot 2026-05-29, not repriced in the site's 2026-10-18 review): basic ≈ $892, private ≈ $2,184 (firewall $912; a Basic firewall is the default for isolated standalone since v5.5.3), ≈ $380 of private extras when a hub firewall is reused; the doc's illustrative floor without the Agent Service resources and the D4 node is ≈ $332 [S19].
- Teams and Microsoft 365 Copilot publication uses a manually enabled, source-IP-filtered public Activity endpoint — **not private end to end** [S19].

---

## 6. Deployment, versioning, CI/CD

- **Bicep + azd** (`azd init … --branch citadel-v1`, then `azd up`; `main` has since absorbed that branch): 25 resource providers, Owner or Contributor + User Access Administrator; 30–45 minutes in the lab [S18], 45–90 minutes per a practitioner, who hit a managed-identity race (re-run) and a Node 24 npm failure on Windows (use Node 20 LTS) when packaging the Logic App [S1,S5,S21]. `main.bicep` is for the *first* deployment only; an exception path deploys `resources.bicep` at resource-group scope (no `azd up`) [S5].
- **Terraform:** `Azure/terraform-ai-gateway-landing-zone` (azurerm + azapi, Terraform ≥ 1.5, `scripts/deploy.sh`; no releases) with Terraform contract docs [S19].
- **Versioning:** seven SemVer tracks; MAJOR needs migration; upgrades via `apim-gateway-upgrade` with per-feature toggles (`updatePolicyFragments`, `updateUnifiedAiApi`, `updateLLMBackends`, `updateLLMBackendPools`, `updateNamedValues`, `updateRedisCache`, …; Redis, embeddings and Realtime default to false); the first run against a legacy gateway should enable as many as possible, in non-production. Existing `/openai` and `/models` paths collide with the legacy APIs: rename the legacy ones (e.g. `/openai-classic`) or set `azureOpenAIApiPathPrefix` / `universalLLMApiPathPrefix` (e.g. `v2`) [S2,S9].
- **CI/CD:** the only sample is Azure DevOps (`.azdo/pipelines/azure-dev.yml`: `azd provision`, `azd deploy`, service connection). No GitHub Actions workflow ships; OIDC is ours to write. The guides recommend config-as-code pipelines (one run per region) and an unchanged `original` branch synced with upstream and merged by pull request into per-environment branches [S5,S9].
- **Validation** is Jupyter notebooks (routing, aliases, JWT, PII, publish contract, session affinity, alerting); not CI-shaped.

---

## 7. Sizing and indicative monthly cost

Meters read from the Retail Prices API (EUR/hour unless noted): Developer 0.0579; Basic v2 0.1808; Standard v2 0.8438 (West Europe) vs **1.10 (Sweden Central)**; Premium v2 3.3752 vs 4.3878; Premium classic 3.3694; Event Hubs Standard TU 0.0264; Cosmos 100 RU/s 0.007; Logic Apps Standard vCPU 0.1735 and 0.0124 per GiB (WS1 = 1 vCPU, 3.5 GiB); Managed Redis B1 0.0334; private endpoint 0.0088. Included requests: Basic v2 10 M, Standard v2 50 M (then €2.20 per million) [S17,S22].

| Line (EUR/month) | Small: Developer ×1 | Medium v2: Standard v2 ×1 | Medium classic: Premium ×1 |
|---|---|---|---|
| API Management | 42 | 616 (Sweden Central 803) | 2,460 |
| Event Hubs 1 TU | 19 | 19 | 19 |
| Cosmos 7 × 400 RU/s | 143 | 143 | 143 |
| Logic App WS1 | 158 | 158 | 158 |
| Private endpoints (9 / 10 / 9) | 58 | 64 | 58 |
| Storage + Log Analytics (≈ 10 GB) | ≈ 18 | ≈ 18 | ≈ 18 |
| **Total** | **≈ 440** | **≈ 1,020** (+31 with Redis B1; ≈ 1,206 in Sweden Central) | **≈ 2,860** |

Not included: models, content safety (€0.33/1K text records), PII (€0.88 down to €0.22/1K), Front Door, a second region, Defender. The sizing guide's Large hub (multi-zone, ≈ 1,000–1,500 PTU) is not priced here.

**Cost levers**, largest first:
1. **Reuse an existing hub or APIM** — incremental ≈ €0 fixed, but the primary template cannot use an existing APIM (issue #123 open); the preview upgrade module can configure one it did not create.
2. **Switch off or shrink the usage pipeline** (≈ €320): Cosmos on shared throughput (one 400 RU/s ≈ €20) or serverless saves ≈ €123; replacing the always-on Logic App and Event Hubs with Log Analytics queries removes the rest. The template exposes only the per-container `cosmosDbRUs` (default 400) and unit counts, no off switch: a fork or an upstream change. `UNVERIFIED` that Power BI and `model-pricing` can be dropped cleanly.
3. **Tier:** Developer for dev/test (−€574 against Standard v2); one hub for all environments with contracts per environment (the sizing guide allows "one central for production and non-production").
4. **Region:** Standard v2 costs ≈ 30 % more in Sweden Central than in West Europe (€803 vs €616), but West Europe is outside the AI Landing Zone's full-deployment list and the AI Gateway preview.
5. **Per-request costs:** message capture off (default captures 256 KB prompts and completions; Basic €0.57/GB or Auxiliary €0.06/GB plans where the table allows — `UNVERIFIED` for `ApiManagementGatewayLlmLogs`); Content Safety and PII only on contracts that read external text or personal data; semantic cache off unless the measured hit rate beats Redis plus embedding cost.
6. **Foundry spoke** (USD, snapshot above): reuse the hub firewall (−$912); drop the pinned D4 node (−$290); `deployAAfAgentSvc=false` saves ≈ $270 but removes the Agent Service, so it is not ours. Foundry's own "BYO VNet with platform-managed data resources" (sample template 11) avoids the BYO Search/Storage/Cosmos trio; the Agent LZ has no switch for it, and residency is for A2/A3 [S16,S19].

---

## 8. Gaps, preview items and clashes

| # | Gap or clash | Evidence | Mitigation |
|---|---|---|---|
| 1 | **Two gateway products.** New AI Gateway (`aigateways`): providers, registered models, aliases, MCP servers; inline (non-XML) policies; Entra RBAC down to alias or MCP server, including agent identities, plus gateway-scoped API keys (in-product docs). Learn: "Full AI feature parity between the products isn't planned"; backend-pool load balancing, failover, semantic caching and A2A are reasons to stay on APIM | [S13,S14] | Stay on APIM; re-test the new product in 2027; keep contracts portable |
| 2 | **Docs disagree on the new product.** Learn: no private endpoints, no content-safety policy, key in the `Authorization` header. In-product docs: inbound private endpoint, content-safety policy, key in `api-key`, "AI Gateway tier" wording | [S13,S14] | Treat Learn as authoritative; verify on a live gateway |
| 3 | **Foundry portal gateway vs Citadel.** Foundry's integration creates or reuses an APIM **v2** instance in the *same tenant and subscription* as the Foundry resource, applies per-project TPM and quota, routes only *new* portal-created MCP tools that do not use managed OAuth | [S15] | Do not enable it on the Citadel hub; use the access-contract connection |
| 4 | **Bring-your-own-model semantics.** Models behind a gateway connection are "Non-Microsoft Products": *you* implement responsible-AI mitigations and check data handling and location; not supported with the Copilot harness | [S15] | Keep gateway content safety on; `UNVERIFIED` whether agent-level guardrails apply on this path (A3) |
| 5 | **Hosted agents and private networking.** Injection fixed at account creation; project capability host before tool calls; Foundry sample 16 (APIM) does not support tools behind the VNet — template 19 does | [S16,S20] | Start from template 19 plus the Citadel access contract |
| 6 | **MCP and A2A through the gateway.** SSE forbids response-body policies; A2A client auth contradictory; Foundry A2A v1.0 preview | §3.2 | Phase 1: MCP only; no A2A |
| 7 | **Identity.** Key always required; JWT-only and agent identity absent; one connection ⇒ one key shared by the whole Foundry project; projects in one Foundry account share model deployments (sample 16 README) | §2.4, [S20] | Separate Foundry projects for separate trust zones; contract = authoritative attribution; per-project model control comes from the gateway |
| 8 | **Defaults that loosen or age.** APIM External; Event Hubs public; Logic App public; prompts and completions logged; tag `SecurityControl: Ignore` (meaning `UNVERIFIED`); sample models `gpt-4.1` (retirement 2026-10-14) and `gpt-5.4-mini` (2026-09-30) already past; `apimSku` description says "only Developer and Premium" while four values are allowed | [S4,S8] | Our parameter file overrides all |
| 9 | **Usage pipeline weight.** Required components with no off switch; `azd` needs Node for Logic App packaging; private Logic App publishing needs a connected runner | §7, [S5,S21] | Lever 2 |
| 10 | **Single maintainer, no releases, schema churn** (seven archive branches; practitioner: schemas "will change") | [S3,S21] | Fork, pin, own the upgrade tests |
| 11 | **Region intersection.** Hub `location` allow-list lacks North Europe and Germany; Landing Zone list lacks West and North Europe; AI Gateway preview only in Sweden Central and East US 2 | [S4,S19,S13] | Sweden Central is the only region in all three lists |
| 12 | **Layers 3 and 4 are not in the repository.** Agent 365 is licensed per user; Defender for AI is priced on estimated tokens | [S10] | Scope with A4 |

---

## 9. What the Azure landing zone must provide, and what a spoke must do

**The landing zone must already provide** (hub side, or the hub project will wait on other teams):
- A subscription with the 25 resource providers registered and an identity holding Owner (or Contributor + User Access Administrator) [S5]; for Entra setup, a person able to create app registrations and assign app roles (Cloud Application Administrator) and, temporarily, Key Vault network access [S9].
- Address space (a /24 for the hub VNet; a /27 or larger, /24 recommended, per Foundry agent subnet), peering in both directions, a default route to the hub firewall, and firewall rules for the `AzureActiveDirectory` tag, `control-{region}.identity.azure.net`, `{region}.login.microsoft.com` and `login.microsoftonline.com` [S16,S19].
- Private DNS: the zones of §2.3 owned centrally, linked to every client VNet (peering does not propagate), or policy-managed DNS; forwarders for VPN and on-premises clients [S5,S19].
- Central Log Analytics (BYO) and, where used, an Azure Monitor Private Link Scope whose blast radius covers every workspace attached to it [S5].
- Policy that tolerates what the templates do (our inference): the default tag `SecurityControl: Ignore`, temporary Key Vault network access for the Entra setup, Event Hubs public access during first provisioning with v2 SKUs, and model-deployment rules that leave the hub's Foundry account alone.

**A spoke must do** to comply:
1. Call models and tools **only** through the gateway; keep no model deployment of its own (enforce with Azure Policy and `disableLocalAuth`) — `UNVERIFIED` that Citadel offers a check.
2. Create the Foundry account with network injection and a project-level capability host *at creation*; enable the project's managed identity; place private endpoints to its Storage, Search and Cosmos.
3. Obtain an Access Contract per use case and environment; consume key and endpoint from Key Vault, never from deployment output; rotate with the three-step flow.
4. Present key and token: role `Model.Invoke` (and `MCP.Invoke`) assigned directly to the project identity; send the attribution headers the contract policy reads (`x-app-id`, `x-sub-agent-id`, `x-enduser-id` in the sample; names are configurable).
5. Register published tools in API Center with owner, classification and compliance metadata.
6. Accept the contract's limits and handle 429 (`Retry-After`) and 403 (quota).

---

## 10. How our solution plugs in (proposal; numbers are seeds to be fitted by the economics model, not findings)

**Topology.** One **Sweden Central** hub, Standard v2, hub-spoke-hub networking, as the single gateway for all environments; our spoke is the Agent Landing Zone foundation in `DEPLOYMENT_MODE=ailz-integrated` with `NETWORK_ISOLATION=true`, `DEPLOY_AZURE_FIREWALL=false` and the `HUB_INTEGRATION_*` inputs (hub VNet, egress next hop, shared Log Analytics) [S19]. If the operator already runs a Citadel hub, join it (cost lever 1); `UNVERIFIED` whether one exists. Disaster recovery in phase 1: redeploy from code; a second hub is outside the cost target.

**Models.** The backend contract registers one Foundry backend per approved deployment type, with **EU Data Zone** SKUs (`sku: DataZoneStandard`; the accelerator sample and the Agent LZ default to `GlobalStandard`, whose processing location A2 must check against EU residency; the hub passes the SKU through to the deployment — whether routing metadata copes is `UNVERIFIED`) and Batch deployments for nightly consolidation. The spoke keeps its own `modelDeploymentList` minimal (`UNVERIFIED` that an empty list is valid). Agents never name a model; they name an **alias** (H7), one wire spec each: `acia-triage` (small, high volume), `acia-reason` (reasoning: Detective, Skeptic, Economist), `acia-judge` (a *different model family* from `acia-reason`, for the Skeptic's and Examiner's independence), `acia-embed`, `acia-batch`. Each alias is `strategy: priority` with a fallback member. Pin `retirementDate` and alert on it.

**Contracts** (per environment `DEV`, `TEST`, `PROD`; product `MULTI-ACIA-<group>-<ENV>`, one Foundry connection each; DEV = 10 %, TEST = 25 % of PROD quotas):

| Contract | Agents | Aliases | PROD seed: tokens/min · tokens/month | Tools | Safety |
|---|---|---|---|---|---|
| `study` | Scholar, Cartographer | triage, embed | 40,000 · 60 M | ms-learn, docs-fetch | content safety with `shield-prompt` (external text) |
| `survey` | Surveyor | triage | 30,000 · 40 M | estate-read, cost-query | PII anonymization (owner names, emails) |
| `test` | Detective, Skeptic, Economist | reason, judge | 60,000 · 80 M | cost-query, atlas, ledger (read) | content safety; per-agent counters (`x-sub-agent-id`) so one cannot starve the Skeptic |
| `lab` | Experimenter | triage | 10,000 · 5 M (daily quota) | lab-control, ledger (write) | content safety; no estate data |
| `act` | Diplomat, Engineer | reason (small share) | 10,000 · 10 M | channels (draft only), moves (read) | PII anonymization; people are referenced by id, names resolved outside the model |
| `grow` | Auditor, Examiner, Librarian | judge, batch, embed | 30,000 · 60 M | atlas (search), exam-bank (read) | content safety |
| `forger` | Forger | reason | 30,000 · 30 M | none | separate key, no tools, so the adversary shares nothing with the examinee |
| `core` | Conductor | triage, embed | 5,000 · 5 M | none | — |

The Move runner holds **no** contract: it is deterministic code and, per H4, holds nothing until a recorded approval (suspending a subscription — APIM `state` — is the kill switch for a misbehaving agent group). Set `estimate-prompt-tokens=true`.

**Published tools** (publish contract; `publishToApiCenter: true`; metadata `owner` = named human sponsor, `classification`, `compliance: ['GDPR']`; calls per minute default 60, higher for `cost-query`):

| Tool | Asset type | Backend | Note |
|---|---|---|---|
| `ms-learn` | `mcp-existing` | `https://learn.microsoft.com/api/mcp`, auth none | the repository's own sample; public documentation |
| `atlas`, `ledger`, `exam-bank`, `moves` | `mcp-existing` | our Container Apps, `managed-identity` | read and write split into separate tools; writes only in `lab` and Librarian paths |
| `estate-read` | `mcp-existing` | Azure MCP Server with a read-only identity (A3) | no write role exists |
| `cost-query` | `mcp-from-api` | our query API; `operationNames` allow-list; `forwardSubscriptionKeyToSource: true` | source never anonymous |
| `channels`, `lab-control` | `mcp-existing` | our services | draft-only mail and cards; Lab vending with budgets (A5) |

No A2A assets in phase 1: agents orchestrate inside Agent Framework workflows (H1). Revisit when Foundry's incoming A2A leaves preview.

**Identity.** One Foundry project per trust zone (reasoning plane; Examiner and Forger apart), contracts per agent group inside a project, so attribution is by contract and the shared project identity does not blur trust boundaries. Direct app-role assignments; `requiredRoles`; custom `azp` check against the project identity.

**Delivery and drift (H11, H12).** Contracts live in our repository in the accelerator's layout; GitHub Actions with OIDC runs `what-if` on pull requests and deploys on merge; contract changes need the sponsor's approval (CODEOWNERS); keys go only to Key Vault. A scheduled job compares `GET /version` and `/version/backend-contract` with the pinned values and runs `what-if` on every contract to detect portal edits. Whether a Deployment Stack with deny settings can wrap the accelerator's modules without blocking the contract deployments is `EVALUATE`. The hub is upgraded only through the Gateway Upgrade module, first in the lab.

**Observability.** `customDimension1` = agent role, `customDimension2` = case id, so the Economist reads cost per case by KQL from `ApiManagementGatewayLlmLogs` and App Insights (no Power BI); message capture off in production, on only in the lab with short retention.

**Still to settle:** the hub region if the operator's landing zone is in West Europe; whether to fork the usage pipeline away (lever 2); model families per alias (A2); agent-level guardrails on the gateway-connection path (A3); residency of platform-managed agent storage (A2).

---

## 11. Could not verify

- `ai.gateway.azure.com/docs/foundry` is a JavaScript single-page application; its text was recovered from the site bundle (`index-Dd_m5Qbu.js`), not rendered. It documents the new AI Gateway product, not APIM.
- Whether semantic-cache policies are wired in the shipped API policies beyond the files searched (none found); how the `llm-usage` and `ai-usage` Cosmos containers differ.
- The Bryan Avery post on Citadel returned 404; the AI Gateway pricing page says "coming soon" and the Retail Prices API has no AI Gateway meter; the `azure.com/e` estimates linked from the sizing guide were not opened.
- The practitioner caption "21 hours and 31 minutes" for a deployment contradicts the same post's "45–90 minutes"; I used the text.
- Whether Entra Agent ID tokens pass `azp` validation; whether Data Zone SKUs flow through routing; whether Deployment Stacks coexist with the modules; whether Basic or Auxiliary log plans accept `ApiManagementGatewayLlmLogs`; the Private Link data-processing price (only the hourly rate was found); Defender for AI and Purview licensing.
- Which AI Landing Zone repository to pin (`agent-landing-zone` or `bicep-ptn-aiml-landing-zone`), and whether an empty spoke model list is valid.
- The Terraform contracts were read at documentation level only; nothing was deployed or run.

## 12. Sources (all fetched 2026-10-31)

`R/` = `https://raw.githubusercontent.com/Azure-Samples/ai-hub-gateway-solution-accelerator/main` · `P/` = `https://raw.githubusercontent.com/Azure-Samples/foundry-citadel-platform/main` · `L/` = `https://raw.githubusercontent.com/Azure/AI-Landing-Zones/main/docs`

| Id | Source |
|---|---|
| S1 | `https://github.com/Azure-Samples/ai-hub-gateway-solution-accelerator` (README) |
| S2 | `R/release.json` · `R/guides/release-version-management.md` · `R/guides/citadel-v1-ga-announcement.md` |
| S3 | GitHub REST API (`gh api`) for `Azure-Samples/ai-hub-gateway-solution-accelerator`, `Azure-Samples/foundry-citadel-platform`, `Azure/AI-Landing-Zones`, `Azure/agent-landing-zone`, `Azure/bicep-ptn-aiml-landing-zone`, `Azure/terraform-ai-gateway-landing-zone`: repository, branches, commits, contributors, releases, tags, issues |
| S4 | `R/bicep/infra/main.bicep`, `main.bicepparam`, `resources.bicep`, `modules/*/*.bicep` (apic, cosmos-db, event-hub, foundry, functionapp, keyvault, logicapp, monitor, redis) |
| S5 | `R/guides/network-approach.md`, `full-deployment-guide.md`, `post-deployment-guide.md`, `citadel-sizing-guide.md`, `parameters-usage-guide.md` |
| S6 | `R/bicep/infra/citadel-access-contracts/` (README, policy guide, quick-reference, key-rotation and resiliency guides, `main.bicep`, `main.bicepparam`, `modules/`, `policies/`, `base-contracts/`) |
| S7 | `R/bicep/infra/citadel-publish-contracts/` (README, `publish-contract-guide.md`, `main.bicep`, `main.bicepparam`, `modules/`, `policies/`) |
| S8 | `R/bicep/infra/llm-backend-onboarding/` (README, `main.bicepparam`), `R/bicep/infra/modules/apim/README-llm-backends.md` |
| S9 | `R/guides/*.md` (the pages cited above), `R/bicep/infra/{apim-gateway-upgrade,entra-id-setup,foundry-integration}/README.md`, `R/bicep/infra/modules/apim/policies/*.xml`, `R/shared/contracttools.py`, `R/.azdo/pipelines/azure-dev.yml`, `R/validation/README.md` |
| S10 | `P/README.md`, `P/layer-1-governance-hub.md` to `P/layer-4-security-foundation.md`, `P/CITADEL-TECHNICAL-GUIDE.md`, `P/Citadel-WAF-Alignment.md`, `P/organizational-alignment-and-ownership.md`, `P/technical-activation-paths.md` |
| S11 | `https://techcommunity.microsoft.com/t5/azure-architecture-blog/building-on-ai-landing-zones-operationalizing-enterprise-ai-with/ba-p/4551078` |
| S12 | `https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities` |
| S13 | `https://learn.microsoft.com/en-us/azure/ai-gateway/` `overview`, `concepts`, `compare-api-management-service`, `migrate-api-management`, `ai-gateway-resource`, `quickstart-create-ai-gateway`, `toc.json` |
| S14 | `https://ai.gateway.azure.com/docs/foundry` and `https://ai.gateway.azure.com/assets/index-Dd_m5Qbu.js` (docs pages: foundry, networking, policies, security-identity, observability, models, MCP, releases 2026-10-08 and 2026-10-16) |
| S15 | `https://learn.microsoft.com/en-us/azure/foundry/` `configuration/enable-ai-api-management-gateway-portal`, `agents/how-to/ai-gateway`, `agents/how-to/tools/governance`, `control-plane/how-to-enforce-limits-models` |
| S16 | `https://learn.microsoft.com/en-us/azure/foundry/` `agents/how-to/virtual-networks`, `agents/concepts/networking-options`, `how-to/configure-private-link` |
| S17 | `https://learn.microsoft.com/en-us/azure/api-management/` `v2-service-tiers-overview`, `llm-content-safety-policy`, `agent-to-agent-api`, `unified-model-api`, `llm-semantic-cache-lookup-policy`, `llm-token-limit-policy`, `agent-365`; `https://azure.microsoft.com/en-us/pricing/details/api-management/` |
| S18 | `https://microsoftlearning.github.io/mslearn-ai-governance/` and `Instructions/Exercises/` `G-govern-ai-through-a-gateway.html`, `G2-enforce-access-contracts.html`, `G6-publish-hosted-agent-and-a2a.html` |
| S19 | `https://github.com/Azure/AI-Landing-Zones` (README; also `https://raw.githubusercontent.com/Azure/AI-Landing-Zones/main/README.md`), `https://azure.github.io/AI-Landing-Zones/` (home, `whatisnew/`, `architecture/cost-guide/`), `L/whatisnew.md`, `L/ai-gateway-landing-zone/` (index, whats-new, contracts, deploy), `L/bicep/*.md`, `L/agent-landing-zone/*.md` (the pages cited above), `https://raw.githubusercontent.com/Azure/bicep-ptn-aiml-landing-zone/main/README.md`, `https://raw.githubusercontent.com/Azure/terraform-ai-gateway-landing-zone/main/README.md` |
| S20 | `https://raw.githubusercontent.com/microsoft-foundry/foundry-samples/main/infrastructure/infrastructure-setup-bicep/16-private-network-standard-agent-apim-setup/README.md` |
| S21 | `https://sjwiggers.com/2026/06/24/deploying-microsoft-foundry-citadel-platform-azure/` · `https://sjwiggers.com/2026/07/21/citadel-apim-gateway-policies-deep-dive-azure/` · `https://sjwiggers.com/2026/08/12/citadel-v1-ai-hub-gateway-release/` |
| S22 | `https://prices.azure.com/api/retail/prices` (EUR; filters: API Management West Europe and Sweden Central; Event Hubs; Azure Cosmos DB; Logic Apps; Redis Cache; Log Analytics; Azure Monitor; Key Vault; Foundry Tools Content Safety and Azure Language; Virtual Network Private Link) |
| S23 | `https://github.com/Azure-Samples/ai-hub-gateway-solution-accelerator/issues/123` |
| S24 | The attachment `Azure-AI-updates_2025-10-31_to_2026-10-31.md`, rows L165, L354, L473, L563 (summaries; the statuses of APIM MCP servers (L354) and content safety for MCP/A2A (L473) were not re-checked on a page) |
