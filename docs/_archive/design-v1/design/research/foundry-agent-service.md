# Foundry Agent Service, models, knowledge, memory and voice — research snapshot (A2)

> Evidence for [the design](../README.md), not the design. Research agent A2, 2026-10-31. Everything below was read on the pages listed in Appendix B on that day; `[Sx]` points to them. Where the attachment (or a blog) and a Learn page disagree, the page wins and the clash is named. EUR figures are Azure Retail Prices API list prices for West Europe, retrieved 2026-10-31 [S51] — anchors for the cost model, not quotes (P1 owns the snapshot). `UNVERIFIED` marks what I could not confirm.

## 0. The ten findings that matter most

1. **Foundry workflow agents retire on 1 December 2026** [S2][S29]. Orchestration belongs in Microsoft Agent Framework (MAF) code inside hosted agents; Routines only *start* an agent.
2. **Hosted agents are GA (9 July 2026)** [S28]: per-session VM sandbox, scale to zero (idle 2–240 min), billed per active vCPU- and GiB-hour (≈ €0.12/h for 1 vCPU + 2 GiB in Sweden Central) [S4][S51]. Not offered in North Europe.
3. **Citadel fits hosted agents, not prompt agents.** The bring-your-own-model (BYOM) route through APIM works for prompt agents only, over Chat Completions only ("The Response API isn't supported at present") [S15]; GPT-6.1 Sol tool calls need Responses [S18].
4. **EU Data Zone is a price tier**: +20 % over Global for models launched on or after 1 Sep 2026 (+10 % older); PTU increases hit existing customers [S19][S51]. In the EU, Claude is Global-only; Flex is Global-only; Priority covers Global and the US Data Zone only; fine-tuning Data Zone is US-only [S12][S34][S35].
5. **The GPT-6 generation is cheaper per token** (GPT-6.1 Sol €1.76 / €8.80 per 1M in/out Global; GPT-6 Luna €0.088 / €0.44), but on GPT-5.6+ models cache *writes* are billed too [S10][S51].
6. **Private-only gaps**: Foundry Memory has no VNet support [S26]; browser automation, computer use, image generation, Logic Apps and Fabric data agent are unsupported under network isolation; web search, Bing and SharePoint grounding use public endpoints [S30]; Teams/M365 publishing needs a public, IP-filtered route [S31]; AI Search Serverless has no shared private link [S25].
7. **Foundry IQ is GA only in part**: Search REST `2026-04-01` covers minimal, extractive retrieval over four source kinds; LLM query planning, answer synthesis and most other sources are preview, and both portals are preview-only [S22][S23][S24].
8. **Quota is subscription-level with tiers (Free, 1–6)**; GPT-6/5.6 need Tier 5/6 or a quota request, so fresh Lab subscriptions may start short [S7][S11].
9. **Drift is built in**: GA models retire after 18 months (12 for Anthropic, DeepSeek, Mistral, Fireworks; ≥ 6 for Grok 4.7+) [S40]; router version `2025-11-18` gains models *in place* [S9]; `gpt-chat-latest` is a rolling preview alias [S7].
10. **Decisions API (`gpt-6-luna`)** returns typed probabilities (predicate / choice / score) — a cheap triage primitive worth a test [S38].

## 1. Capability register

Status is as on the page, with its date. Components use the brief's codes.

| # | Capability | Status | Disp. | Comp. | Fit / main caveat |
|---|---|---|---|---|---|
| 1 | Foundry resource + projects (`AIServices`) | GA | ADOPT | AGT GOV NET | Resource = governance, project = dev boundary; 100 resources/region/sub |
| 2 | Agents v2 on the Responses API | GA (16 Mar 2026) [S44] | ADOPT | AGT | Replaces Assistants/threads; Entra auth only |
| 3 | Prompt agents | GA | ADOPT | AGT | No platform fee; private networking supported; BYOM only via chat completions |
| 4 | Hosted agents (+ long-running resilience) | GA 9 Jul 2026; resilience GA 28 Oct [S28][S38] | ADOPT | AGT COMP FW | Python/C# only; West Europe listed but no price meter found |
| 5 | Voice-based prompt agents | Public preview (24 Sep) [S18] | WATCH | AGT CHAN | 60-min sessions; optional module |
| 6 | Microsoft Copilot harness | Public preview (28 Oct) [S38] | WATCH | AGT | No BYOM, no Foundry Memory → bypasses Citadel |
| 7 | Workflow agents | Preview; **retire 1 Dec 2026** [S2] | N/A | FW | Use MAF workflows |
| 8 | Routines | GA (24 Sep) [S18] | ADOPT | AGT OPS | One trigger → one agent; no CMK |
| 9 | Toolbox + tool search | GA (30 Jun; search 24 Sep) [S39][S18] | ADOPT | TOOL | Prompt-agent toolboxes preview; skills preview |
| 10 | Toolbox skills | Preview [S13] | WATCH | TOOL | Versioned, immutable |
| 11 | MCP tool (public / private) | GA tool; MCP auth guide preview [S33] | ADOPT | TOOL | Private MCP needs a dedicated subnet |
| 12 | A2A (v1.0) | GA v1.0; v0.3 preview [S3][S36] | ADOPT | TOOL GW | Incoming A2A needs Responses protocol |
| 13 | OpenAPI / Azure Functions tools | GA overall; per-tool labels not checked [S2] | ADOPT | TOOL | Reach private APIs through the agent subnet |
| 14 | Code interpreter | GA | EVALUATE | TOOL LAB | Files limited in private setups; our Lab uses sandboxes |
| 15 | File search / vector stores | GA | WATCH | KNW | Atlas lives in AI Search; Blob source unsupported under isolation |
| 16 | Web search / Grounding with Bing | GA | WATCH | TOOL SEC | Outside the DPA and geographic boundary [S36] |
| 17 | Browser automation | GA 19 Oct [S52] | WATCH | TOOL | Not supported under network isolation [S30] |
| 18 | Computer use | Not stated (model `computer-use-preview`; capability also listed on GPT-5.6/6.x) [S7][S14] | N/A | TOOL | Few regions; not under isolation |
| 19 | Foundry IQ (knowledge bases, agentic retrieval) | Partial GA [S2] | ADOPT-PREVIEW | KNW | GA subset at `2026-04-01`; fall back to direct AI Search |
| 20 | AI Search Serverless Developer tier | Public preview; billing from 13 Sep [S25] | EVALUATE | KNW COST | Scales to zero; no SLA, no private indexers |
| 21 | Foundry Memory | Public preview [S26] | WATCH | KNW | No VNet; 5 EU regions; use own store |
| 22 | Foundry model catalogue (> 10,000 models; "sold by Azure" subset) | GA | ADOPT | MOD | Launch order Global → Data Zone → regional [S40] |
| 23 | GPT-6.1 / GPT-6 / GPT-5.x | GA | ADOPT | MOD | 1.05M context; tier-gated quota |
| 24 | Claude (Hosted on Azure) | GA models; Fable preview [S12] | EVALUATE | MOD | Marketplace/CCU billing; Global-only for EU |
| 25 | Mistral Large 4 and EU open-weight models | Public preview (Oct) [S45] | EVALUATE | MOD | Sweden Central, Global + EU Data Zone |
| 26 | Model router | GA (18 Nov 2025) [S39] | EVALUATE | MOD COST | Needs an eval baseline; router price UNVERIFIED |
| 27 | Decisions API | Not stated (rolling out) | EVALUATE | MOD COST | `gpt-6-luna` only |
| 28 | Data Zone Standard (EU) | GA | ADOPT | MOD GOV | +20 % on new models |
| 29 | Global Standard | GA | ADOPT | MOD COST | Public-data workloads only (design choice) |
| 30 | Batch (Global / Data Zone) | GA | EVALUATE | MOD COST | EU Data Zone Batch lists few models |
| 31 | Flex processing | Preview [S34] | ADOPT-PREVIEW | MOD COST | −50 %, Global Standard only, no SLA |
| 32 | Priority processing; PTU | Not stated; GA | N/A | MOD | Not phase 1 |
| 33 | Prompt caching | GA | ADOPT | MOD COST | Cache-write charges on GPT-5.6+ |
| 34 | Fine-tuning, distillation | GA managed; programmed preview [S35] | WATCH | MOD | Data Zone training US-only |
| 35 | Voice Live API | No preview label [S27] | EVALUATE | CHAN | WebSocket; token-priced; optional |
| 36 | Avatars | Standard/custom photo GA (Jun) [S50] | WATCH | CHAN | Optional module |
| 37 | Publish to Teams / M365 Copilot | GA [S39] | EVALUATE | CHAN | Conflicts with private-only unless public route |
| 38 | Foundry-native AI Gateway (APIM) | Preview [S2] | WATCH | GW | APIM v2 tiers, same subscription; Citadel supersedes |
| 39 | BYOM connection (APIM / model gateway) | Not stated (older text: preview) [S15] | ADOPT-PREVIEW | GW | Prompt agents + chat completions |
| 40 | SDKs (`azure-ai-projects` 2.x; .NET 3.0 beta) | GA / beta [S28] | ADOPT | DEV | .NET and azd Foundry extensions still beta |

## 2. Resource and project model

- A **Foundry resource** (`Microsoft.CognitiveServices/accounts`, kind `AIServices`) carries networking, security, model deployments and connections; a **project** (`…/accounts/projects`) is the development boundary for agents, files and evaluations. Storage, Key Vault and AI Search stay separate resources with their own governance [S5].
- Limits: 100 Foundry resources per region per subscription, 250 projects per resource, 32 model deployments per resource [S11].
- Roles (recently renamed from "Azure AI …"): Foundry User, Project Manager, Account Owner, Owner. Agents, evaluations, workflows and Content Understanding need Entra ID — API keys do not work there [S2][S5].
- **Quota** is per subscription since 7 May 2026: one Global pool per model+version across regions, one Data Zone pool per zone (the EU zone counts as one). Seven tiers (Free, 1–6) move up with usage; `NoAutoUpgrade` is a preview opt-out. Microsoft says quota is not the cost-control tool [S11].
- **No automatic cross-region failover**; Global and Data Zone Standard share a primary-region outage risk [S5][S6].
- Agent state: *basic* setup keeps threads and files in Microsoft-managed multitenant storage; *standard* setup uses your Storage, AI Search and Cosmos DB, isolated per project, provisioned through capability settings (API `2026-07-15-preview`) [S5][S14][S30]. The Cosmos DB for NoSQL account needs a total throughput limit of at least 3,000 RU/s (multiply by the number of projects); **provisioned and serverless modes are both supported**, and the new runtime uses the containers `agent-definitions-v1` and `run-state-v1` [S53].
- Endpoints: project `https://<res>.services.ai.azure.com/api/projects/<proj>`; OpenAI `…openai.azure.com/openai/v1`; Claude `…/anthropic` [S47].
- GA table caveats: monitoring, tracing-in-VNet, Operate pages and agent guardrails are still preview. Preview features can be hidden with tags or blocked with a custom RBAC role [S2].

## 3. Agent Service

### 3.1 Agent types

| Type | Status | Runs on | Cost | Limits / notes |
|---|---|---|---|---|
| Prompt | GA | Foundry-managed | No platform charge; tokens + tools [S20] | Versioned; ≤ 1,000 versions, ≤ 128 tools/agent [S14] |
| Voice-based prompt | Preview | Foundry + Voice Live | Voice Live + model tokens | 60-min sessions; audio kept 60 days [S14] |
| Hosted | GA | Your container or zip, per-session sandbox | vCPU-h + GiB-h while active | Below |
| Prompt + Copilot harness | Preview | Managed harness sandbox | Tokens + tools; a "Skills Execution Container" meter exists (€0.032/h Sweden Central; link to the harness UNVERIFIED) [S51] | No BYOM, no Memory; Germany WC, Sweden C, West Europe, UK South [S14] |
| Workflow | Preview, retiring | Visual builder | — | No outbound VNet injection; hosted agents not supported [S29][S30] |
| Ephemeral (Responses API) | GA | Your process | Tokens | No harness, no optimizer [S3] |

### 3.2 Runtime: conversations and the Responses API

An agent is a named, versioned definition; a conversation stores items server-side; a response is one execution [S47]. Saving a change creates a new version. Published agents get a stable endpoint with `version_selector` ("always latest" or pinned) [S31]. Stored responses are kept 30 days by default and can be deleted by ID; `store=false` is allowed [S46]. Limits: 100,000 messages per thread, 1.5M characters per message, 512 MB per file, 10,000 files per agent, 300 GB total [S14]. Data is regional: "data is stored in the same region as the endpoint" [S14]. mTLS is unsupported and Azure service tags do not work for MCP client traffic [S46].

### 3.3 Hosted agents

- **Isolation and state**: one VM-isolated sandbox per session, persistent `$HOME` and `/files` (≤ 20 GiB at ≥ 1 vCPU), restored on resume. Idle timeout 2–240 min (default 15); sessions deleted after 30 days idle [S4]. A durable key-value state store (default 30-day idle expiry, configurable to never) holds framework checkpoints [S4].
- **Sizes**: 0.5 vCPU/1 GiB, 1/2, 2/4. No replica count, no warm pool; billing = CPU + memory across active sessions [S4].
- **Limits**: 1,000 concurrent sessions per subscription and region (2,000 in Sweden Central and six others); 429 `session_quota_exceeded` beyond [S14].
- **Protocols**: Responses, Invocations, Invocations (WebSocket), Activity (bridged for Teams), A2A v1.0 [S4]. One version serves 100 % of traffic — no splitting; versions are immutable, including environment variables [S4].
- **Identity**: a dedicated Entra identity and endpoint per agent at deploy; default access covers model calls and session storage; other resources need manual RBAC. OBO flows when a user token exists [S4].
- **Networking**: BYO VNet injection must be set when the Foundry account is created; a private ACR works only for projects created after 25 Jun 2026; the agent subnet cannot be shared between Foundry resources [S30]. Sessions try to reach `agent365.svc.cloud.microsoft` for telemetry unless `a365LoggingEnabled=false` [S30]. Egress rules (allow/deny/rewrite by host, audit or enforce) are in public preview [S39:571821].
- **Regions (EU/EEA + CH/UK)**: France Central, Germany West Central, Italy North, Norway East, Poland Central, Spain Central, Sweden Central, Switzerland North/West, West Europe, UK South/West. **Not North Europe** [S4].
- **Price anchors** (Sweden Central, €/h): vCPU 0.0962, GiB 0.0114 → 1 vCPU + 2 GiB ≈ 0.119; 0.5 vCPU + 1 GiB ≈ 0.060 [S51]. No West Europe hosted meter appeared in the API (UNVERIFIED why).
- **Languages**: Python and C#; Agent Framework, LangGraph, OpenAI Agents SDK, Anthropic Agent SDK, Copilot SDK or custom [S3][S4].

### 3.4 Tools and the toolbox

A **toolbox** is a managed, versioned MCP endpoint over curated tools with central auth (Entra, OAuth passthrough, keys) and guardrails; any MCP client can use it. **Tool search** swaps full tool lists for `tool_search` + `call_tool`, cutting input tokens [S13][S18].

| Tool | In toolbox | Network isolation [S30] | Meter / note |
|---|---|---|---|
| MCP (public/private) | yes | private via VNet subnet | Approval flow per call [S33] |
| A2A | yes | via VNet subnet | v1.0 GA |
| OpenAPI, Azure Functions | OpenAPI yes; Functions direct only | via VNet subnet | — |
| Azure AI Search | yes | private endpoint | Search tier |
| File search | yes | private endpoint | €0.088/GB-day (1 GB free) [S20][S51] |
| Code interpreter | yes | backbone; no file I/O in BYO setups | €0.026/session |
| Web search / Bing | yes / direct | **public endpoint** | €12.32/1k transactions; outside DPA [S36] |
| SharePoint, Fabric IQ, Work IQ | partial | SharePoint public; Fabric IQ partial; Work IQ not listed | Separate licences |
| Browser automation, computer use, image gen | partial | **not supported** | GA 19 Oct (browser) |

Tool availability varies by region (file search missing in Italy North; computer use only in Sweden Central, Switzerland West, West Europe in Europe) and by model — many open-weight models lack MCP, OpenAPI or A2A [S14]. Custom tools can be MCP servers on Azure Functions (`/runtime/webhooks/mcp`) or private MCP on Container Apps with internal ingress; the remote Azure DevOps MCP server is a catalogue item [S3][S33]. Tool auth: key, Entra (agent or project managed identity), OAuth passthrough (OBO) or none [S3]. Foundry A2A lets agents call agents by name through a managed endpoint, with identity, content safety and audit logging applied on every hop [S39:563716]. The portal has public and private tool catalogues [S17].

### 3.5 Routines, publishing, optimisation

- **Routines** (GA): trigger = timer, cron-style recurring, GitHub issue, or Teams-channel message; action = invoke one prompt or hosted agent as its agent identity; run history with traces; works in VNet projects; **no CMK** [S32].
- **Publishing** (GA): Teams and Microsoft 365 Copilot via Azure Bot Service; Foundry data-handling warning for M365 processing; with public access disabled the portal cannot publish — use REST and `enable_m365_public_endpoint` (source-IP-filtered Activity route) [S31]. Entra Agent Registry distribution [S3].
- **Agent optimizer**: limited preview; **Insights**: public preview [S2][S18]. Agent 365 (Microsoft 365 admin centre) can enable or disable Foundry agents — GA Aug 2026 [S39:571826].

### 3.6 Security and identity notes

- Guardrails: model level GA; agent level and the tool-call / tool-response intervention points are preview; cross-prompt-injection mitigation is described for agents (A3 owns configuration) [S2][S3][S5].
- Hosted agents: no secrets in images or environment variables; treat uploads in `$HOME` as untrusted input; data sent to non-Microsoft services may leave your compliance boundary [S4].
- MCP tool calls can be reviewed and approved before execution — the natural human-in-the-loop hook [S33].
- Entra auth is mandatory for agents; prefer agent identity over keys; keep RBAC on the agent identity minimal [S2][S4].

### 3.7 SDKs and tooling

Python `azure-ai-projects` and JavaScript `@azure/ai-projects` are stable 2.x (2.5.0 at end of August, 2.8.0 in October); Java `azure-ai-projects` is 2.x; .NET `Azure.AI.Projects` is 3.0.0-beta [S28][S18][S47]. The Foundry SDK is the thin client over all project APIs; use the OpenAI SDK for embeddings and maximum compatibility and the Anthropic SDK for Claude [S47]. Hosted-agent runtime packages export Azure Monitor traces at 100 % sampling by default — review volume and cost [S18]. The azd agents extension is beta (azd ≥ 1.34.2 from beta.18); Foundry Toolkit for VS Code is GA; Foundry Canvas in the GitHub Copilot app is preview [S18][S28].

## 4. Models

### 4.1 Catalogue

More than 10,000 models; "sold by Azure" (billed by Microsoft, SLA) versus partners and community [S1][S7].

- **OpenAI**: GPT-6.1 Sol (29 Sep) and Terra (26 Oct), GPT-6 Astra/Sol/Luna, GPT-5.6 Sol/Terra/Luna, GPT-5.5, GPT-5.4 (+ mini, nano, pro), gpt-oss, embeddings, realtime/audio, image; 1.05M-token context (922k in, 128k out) for GPT-5.6/6.x; `gpt-chat-latest` preview alias [S7].
- **Claude (Hosted on Azure, GA)**: Haiku 5.5, Sonnet 5/5.5, Opus 4.8/5/5.5 (+ fast). Fable is Anthropic-hosted preview; Mythos gated. Anthropic is seller and data processor; Marketplace subscription; billed in Claude Consumption Units, MACC-eligible, now in Cost Management with tags (GA Oct 2026); no CSP, trial or credit-only subscriptions [S12][S39:577260].
- **Others sold by Azure**: Mistral Large 3, Medium 3.5; DeepSeek V3.2/V4; Grok 4.x; Kimi; Llama 3.3/4; Phi-4; Cohere (Command, Rerank v4); MAI-Thinking-1; Microsoft-Decision-1 [S8]. **Mistral Large 4**: public preview via Microsoft, "Sweden Central … Global Standard and EU DataZone" [S45].
- Model support in Agent Service is per model and tool; check the portal filter `capabilities=agentsv2` [S14].

### 4.2 Deployment types and EU availability

| Type | Processing | EU position (West Europe unless noted) |
|---|---|---|
| Global Standard | any region | All GPT-6/5.6 incl. 6.1 Terra; North Europe lacks 5.6/6.x |
| **Data Zone Standard** | EU data boundary (incl. NO, CH) | GPT-6.1 Sol/Terra, GPT-6 Sol/Luna and GPT-5.6 in FR, DE, IT, NO, PL, ES, SE, CH-N, WE (not North Europe); Astra and GPT-5.5/5.4 also in North Europe; embeddings in FR, DE, IT, PL, ES, SE, WE; router everywhere; Claude absent [S8] |
| Regional Standard | one region | Essentially gpt-4.1 (Sweden C, CH-N) and some embeddings; no GPT-5.x/6.x [S8] |
| Regional Provisioned | one region | gpt-5.4 in Germany WC and Sweden C; GPT-5.6 only in UK South [S8] |
| Data Zone Provisioned | EU zone | GPT-6.1 Sol, GPT-6 Luna in FR, DE, IT, PL, ES, SE, WE; GPT-5.6 also NO, CH-N; 5.5, 5.4 [S8] |
| Global / Data Zone Batch | 50 % off, 24 h | Page lists gpt-4.1 family and o4-mini for EU Data Zone Batch; gpt-5, 5.4, 5.4-mini added for Global Batch [S6][S8] |
| Developer | any region | Fine-tuned model evaluation only, 24 h, no SLA |

Launch order is Global → Global Provisioned → Data Zone → regional, so new models reach EU Data Zone later [S40]. Clash: the 15 Oct blog says GPT-6 Astra is US-Data-Zone-only; the region page (19 Oct) shows it in EU Data Zone — page wins [S18][S8]. "Instant access" (call by name, no deployment) is preview [S6].

### 4.3 Price anchors (EUR per 1M tokens, West Europe, short context)

| Model | Global in / out | EU Data Zone in / out | Cached in (Global) | Flex (Global) in / out |
|---|---|---|---|---|
| GPT-6 Astra | 8.80 / 44.00 | 10.56 / 52.80 | 0.88 | 4.40 / 22.00 |
| GPT-6.1 Sol | 1.76 / 8.80 | 2.11 / 10.56 | 0.088 | 0.88 / 4.40 |
| GPT-6 Luna | 0.088 / 0.44 | 0.106 / 0.528 | 0.0088 | 0.044 / 0.22 |
| GPT-5.6 Sol | 3.52 / 17.60 | 3.87 / 19.36 | — | — |
| GPT-5.6 Terra | 1.76 / 10.56 | 1.94 / 11.62 | — | — |
| GPT-5.6 Luna | 0.176 / 1.056 | 0.194 / 1.162 | — | — |
| GPT-5.5 | 4.40 / 26.40 | 4.84 / 29.04 (Batch 2.42 / 14.52, meter only) | 0.44 | — |

Source [S51]; USD list prices in the blog agree (Sol $2/$10) [S18]. Long-context requests cost more. Embeddings are negligible: `text-embedding-3-large` in the EU Data Zone shows €0.0001 per 1k tokens, `3-small` rounds to zero [S51]. Cache write on GPT-6.1 Sol: €2.20 Global, €2.64 Data Zone (1.25 × input) [S51]. The EU premium comes from the 1 Sep policy: Data Zone +20 % (was +10 %), regional +30–50 % (West and North Europe +50 %, Sweden/Germany +30 %), applying to new Standard models and to all PTU [S19]. Meters for GPT-5.4 variants and Terra 6.1 were not captured.

**Illustration (my assumptions):** 1,000 cases a month, 20 model calls each, 20k input tokens per call (80 % cache reads), 2k output tokens, cache-write charges ignored. On GPT-6.1 Sol in the EU Data Zone that is 80M uncached + 320M cached input and 40M output tokens ≈ €625; on GPT-6 Luna ≈ €33. Hosted compute for the same cases, five active minutes each on 1 vCPU/2 GiB, ≈ €10. Model choice, not compute, drives the bill.

### 4.4 Model router

GA since 18 Nov 2025; deploys like a model; version `2025-11-18` is updated in place with new models (older versions frozen). Modes: Balanced (default), Cost, Quality; **model subset** you choose (new models are not auto-added); automatic failover inside the subset; Global and Data Zone Standard; routes only to eligible models and honours data zones; Claude must be deployed separately first. Effective context = smallest model in the subset. Pool today: GPT-6 Astra, GPT-5.6/5.5/5.4/5.2/5 families, o4-mini, GPT-4.1/4o, gpt-oss-120b, Claude, Grok, DeepSeek, Llama, Fireworks GLM/Kimi [S9]. 32 regions (North Europe, Norway East added in September); session affinity and routing metadata are preview; Azure Policy governs the subset (preview) [S18][S39:563636]. Quota by tier: Tier 1 = 1,000 RPM / 1M TPM Global and 300 RPM / 300k TPM Data Zone; Tier 6 = 15,000 / 15M and 4,000 / 4M [S9]. Billing: "charged for input prompts at the rate listed on the pricing page"; I found no router meter in the API and no router text on the pricing pages — **UNVERIFIED** whether a router surcharge applies [S9][S51].

### 4.5 Caching, batch, Flex, PTU

- **Prompt caching** is automatic from 1,024 identical leading tokens (128-token steps up to GPT-5.5). GPT-5.6+ adds `prompt_cache_key`, explicit breakpoints (≤ 4 writes per request), a 30-minute minimum lifetime, `cache_write_tokens` billing, and no support on PTU-M; earlier models allow `prompt_cache_retention` up to 24 h. Caches are not shared across subscriptions [S10]. Under the router, hits occur only if the same model serves consecutive turns [S9].
- **Flex** (preview): −50 %, `service_tier=flex`, Global Standard only, no SLA; unsupported models return 400 [S34]. **Priority**: Global or Data Zone (US) only [S34].
- **PTU**: Global, Data Zone and Regional; Global PTU reservations became region-agnostic (GA, Jun 2026) [S39:563212]. Standing capacity contradicts scale-to-zero (H6) — not phase 1.

### 4.6 Fine-tuning and distillation

Managed Training is GA (SFT, DPO, RFT; distillation via teacher-generated SFT data); Programmed Training is preview and gated. Training types: Standard (regional, residency-safe), Global, Developer (spot, preemptible; Developer Training tier preview), **Data Zone — US only**. Serving: serverless, Managed Compute (preview), Fireworks (preview); Data Zone Standard serving is US-only [S35][S39:525952].

### 4.7 Lifecycle

Stages: Preview → GA → Legacy → Deprecated → Retired (HTTP 410). "Existing customer" is per subscription, so a new Lab subscription cannot deploy a deprecated version [S40]. Lifetimes in finding 9. September carried two scheduled deadlines: MAI-Transcribe-1 (15 Sep) and the `gpt-chat-latest` 2026-06-24 snapshot (24 Sep) [S18].

## 5. Knowledge: Foundry IQ and agentic retrieval

- **What it is**: a *knowledge base* (reasoning effort minimal/low/medium) over *knowledge sources*, executed by Azure AI Search; usable from Agent Service, MAF, the retrieve REST action or an MCP endpoint (a candidate for a hub-published tool, UNVERIFIED). Runs under the caller's Entra identity; ACL sync, Purview labels (preview) [S22][S23][S24].
- **Status split**: `2026-04-01` is GA for minimal, extractive retrieval with **search index, Azure Blob, OneLake and Web** sources. Preview (`2026-08-01-preview`): LLM query planning, answer synthesis, multi-turn messages; Azure SQL, File, SharePoint, Fabric Data Agent/Ontology, MCP server, Work IQ sources [S23][S24]. Learn calls Foundry IQ "Partial GA (API-level GA; portal access remains Preview)" [S2]; the 4 Jun announcement says GA [S39:563222].
- **Limits**: sources and bases per service — Free 3, Basic 5–15, S1 50, S2/S3 200, Serverless Developer 30; up to 10 sources per base (Free 3, Basic 5–10); retrieve runtime 10–600 s (default 90) [S25].
- **Pricing model**: AI Search service (dedicated SUs or serverless CUs + GB) + retrieval tokens (semantic ranking) + Azure OpenAI tokens for planning/synthesis. API anchors: medium-effort retrieval €0.0001 per 1k tokens, the low and minimum meters €0 (LLM tokens still billed separately), free monthly allowance on the free plan [S24][S51].
- **Serverless Developer tier** (preview, billing from 13 Sep): scales to zero, no SLA, no index aliases, no indexer private networking, no shared private link, limited regions [S25]. Attractive for H6, unusable for private ingestion today.
- **Networking**: private connectivity (shared private link or network security perimeter) GA in June [S39:563516]; but auto-generated indexers of indexed knowledge sources "don't support the private execution environment" [S30] — **clash, test before relying**. Private AI Search as an agent tool needs the new portal. APIM in front of Foundry models used by Search (embeddings, vectorizers, GenAI skill) is preview [S39:563451].
- **EU**: agentic retrieval is in "select regions" — list not verified [S24].

## 6. Memory

- **Foundry Memory** (public preview; refreshed 2 Jun 2026): managed long-term store with user-profile, chat-summary and procedural memory; item CRUD, store-level TTL, remember/forget commands; accessed through a memory-search tool or store APIs [S26][S39:563616].
- **Limits**: 100 scopes per store, 10,000 memories per scope, 1,000 search and 1,000 update requests per minute; needs Azure OpenAI chat and embedding deployments; **no VNet integration**; not with the Copilot harness [S14][S26].
- **EU regions**: France Central, Italy North, Norway East, Sweden Central, Switzerland North, UK South [S26].
- **Pricing**: model tokens plus meters per 1k — long-term memories €0.242/month, retrievals €0.484, short-term events €0.242 (Sweden Central) [S51].
- **Risks**: LLM extraction invites poisoning and prompt injection; the refresh added content-safety filtering on writes [S26][S39:563616].
- **Alternatives**: MAF memory/context providers, Cosmos DB providers (preview, Python), our operational store (H5).

## 7. Voice

- **Voice Live API**: WebSocket speech-to-speech, compatible with the Azure OpenAI Realtime event set; > 140 locales in, > 600 voices out; noise suppression, echo cancellation, end-of-turn detection, avatar output; managed models from `gpt-realtime-2.1` (+ `-datazone`, `-regional`) to GPT-4.1/5.x/6.x text models with cascaded STT/TTS [S27]. Priced per token in three tiers (Pro, Standard, Lite) by model; separate meters for LLM text/audio/image, standard and custom speech, and BYO [S27][S51].
- **Status trail**: pricing live since 1 Jul 2025; integration with Agent Service GA 2 Jun 2026; hosted agents + Voice Live GA (Jul/Aug); **voice-based prompt agents public preview 24 Sep** — Learn's GA table still shows "Agents — Voice Live: Preview" [S2][S18][S28][S39:563601].
- **Voice-agent limits**: 60-min sessions, 60-day audio retention, not in Poland Central or Spain Central, WebRTC avatars (phone callers get audio only), single trace view, no single-turn or simulated-conversation evaluation [S3][S14]. Phones: Teams Phone extensibility (Azure Communication Services + Event Grid) and Twilio; the Learn overview says direct SIP is not offered, while the 30 Oct blog announces SIP trunks — newer blog, status not stated [S3][S45].
- **EU**: Voice Live resource regions in Europe include France Central, Germany West Central, Italy North, North Europe, Norway East, Sweden Central, Switzerland North, West Europe. EU Data Zone realtime models exist in Sweden Central (2.1, 1.5, base) and France Central (1.5, base); HD voices are Regional in Sweden Central, France Central and West Europe, Data Zone elsewhere [S27].
- **Avatars**: standard and custom photo avatar GA (Jun 2026), custom video avatar portal GA, voice sync in Voice Live preview; 512×512 photo, 1080p video [S37][S50].
- **Cost drivers**: audio tokens, session length, tools, avatar, `store` (default false), ACS telephony, App Insights; traces carry estimated cost per turn [S37]. Idle cost is nil, so "off by default" (H10) is cheap to honour.

## 8. Behind a Citadel gateway

**BYOM mechanics** [S15]: an admin-connected model connection of type `ApiManagement` (defaults `/deployments`, provider `AzureOpenAI`; subscription key or Entra) or `ModelGateway` (static or dynamic model discovery; API key or OAuth 2.0). Enter the base path only — Foundry appends `chat/completions`; a switch adds the deployment name to the path; static headers are allowed. With managed identity the project identity presents a token for a configured *audience*, which APIM checks with `validate-azure-ad-token` (audience plus the identity's application ID). Each listed model becomes a Foundry deployment addressed as `<connection>/<model>`. Bicep samples: foundry-samples `01-connections`; the fully private pattern is `16-private-network-standard-agent-apim-setup`.

| Capability | Behaviour behind APIM / Citadel |
|---|---|
| Model calls from your code (hosted agent, MAF, tools) | Fully governable: APIM governs chat completions, responses and real-time; 429 on tokens-per-minute, 403 on quota; Entra token validation [S43][S16] |
| Prompt agent model call | Only through a BYOM connection (`ApiManagement` or `ModelGateway`), model id `<connection>/<model>`; prompt agents only; Chat Completions only; tools limited to code interpreter, functions, file search, OpenAPI, Foundry IQ, SharePoint, Fabric Data Agent, MCP, browser automation; private setup needs the dedicated template; harness unsupported [S15] |
| Foundry-native AI Gateway | Preview; APIM v2 tiers in the same tenant **and subscription** as Foundry; created public even for private Foundry; limits per project [S16][S30][S42]. A hub in another subscription is not in the portal list; a BYOM connection to the hub is the documented alternative (my inference) |
| Hosted agents | Your code chooses the endpoint: call the hub with the agent identity. Project-endpoint calls bypass it unless the project is attached to a Foundry gateway (Responses coverage UNVERIFIED). Egress rules can force this (preview) [S4][S39:571821] |
| MCP tools | Foundry-gateway routing only for new portal-created MCP tools without managed OAuth; SharePoint, OpenAPI, code-first MCP excluded; no tool traces; policies editable only in the Azure portal [S17]. Toolbox endpoints: Citadel publish-contract fronting UNVERIFIED |
| A2A | Endpoint `…/agents/<name>/endpoint/protocols/a2a`; a natural candidate for publish contracts [S4] |
| Model router | Just another deployment to the gateway; chosen model visible only via usage fields and routing metadata (preview) [S18] |
| Claude | Anthropic Messages API on `/anthropic`; APIM supports it on v2 tiers [S43]; BYOM expects chat-completions, so prompt agents cannot use it unchanged (UNVERIFIED with the unified model API preview) [S15][S43] |
| Foundry IQ / Search | Retrieve calls hit the search service; planning, embedding and vectorizer model calls can sit behind APIM (preview) [S39:563451] |
| Memory | Extraction and embedding run on Foundry deployments; interposition not documented (UNVERIFIED) [S26] |
| Voice Live | WebSocket; APIM governs real-time APIs [S43]; `self_deployed` voice models use your own deployment [S37]; end-to-end behind the hub UNVERIFIED |
| Teams/M365 publish | Activity route is a public, IP-filtered endpoint, outside the hub [S31] |

## 9. Design implications

1. **H1 stands, with an edit.** Prompt agents for single-turn roles with GA tools; hosted agents (GA) for anything with custom tools or loops; MAF workflows *inside* hosted agents replace Foundry workflows. Routines are triggers for the Watch clock, nothing more.
2. **H2 needs a split.** Route every model, MCP and A2A call from hosted-agent code through the hub using the agent identity. Treat prompt agents as a second-class path: Chat Completions only, so GPT-6.1 Sol loses tool calling there — prefer hosted agents or Terra/5.x for prompt agents.
3. **Data classification drives the deployment type.** Estate data: EU Data Zone Standard (+20 %). Public documentation work (Scholar): Global Standard is ≈ 17 % cheaper and opens Flex (−50 %) and Claude. Encode the choice in each access contract.
4. **Tier by role (H7).** Luna-class for volume (€0.088/€0.44 Global), Sol-class for Detective, Skeptic, Economist (€1.76/€8.80), Astra never by default. Test Decisions API for triage and the router with a subset against a fixed baseline. Keep prefixes stable, set `prompt_cache_key`, and watch cache-write cost; use tool search for large toolboxes.
5. **Nightly consolidation**: Data Zone Batch in the EU covers few models; plan on Data Zone Standard with caching for estate data and Global Batch or Flex for public data. Re-check the batch table at design time.
6. **Knowledge**: Foundry IQ with GA source kinds and minimal retrieval, or direct AI Search hybrid queries; adopt the Serverless tier only when private indexing is not needed (Atlas build runs in a job, not through Search indexers).
7. **Memory**: skip Foundry Memory in phase 1 (preview, no VNet, five regions); keep the Lesson Book and conversation memory in our own store.
8. **Network**: one Foundry resource per environment (dev, test, prod, Lab), each with its own /24 agent subnet delegated to `Microsoft.App/environments`, VNet injection at creation, project created after 25 Jun 2026 for a private ACR, BYO Cosmos DB (serverless mode keeps it scale-to-zero, A5)/Storage/Search behind private endpoints, project-level capability host, firewall allow-list including the Agent 365 telemetry FQDN or `a365LoggingEnabled=false`.
9. **Identity (H4/H9).** Hosted agents get a standing Entra identity at deploy. Keep the reasoning plane read-only; run Moves outside hosted agents, or grant time-boxed RBAC to the agent identity.
10. **Channels (H10).** Foundry publishing is conversational and conflicts with private-only; deliver Adaptive Cards through the Microsoft 365 Agents SDK (A3) and treat Foundry publishing as optional. Voice, avatar and SIP stay modules.
11. **Drift (H11).** Pin model versions and expect retirement within 12–18 months; use a router subset, `version_selector` pins, toolbox version promotion, Azure Policy to deny `GlobalStandard` where residency demands, and block preview features by tag or custom role.
12. **Cost (H6).** Prompt agents carry no platform fee; hosted sessions bill only while active (≈ €0.06–0.24/h by size); the big meters are tokens, search and tools. Per-meter budgets belong in access contracts; quota is not a budget.

## 10. Gotchas

1. BYOM = Chat Completions; GPT-6.1 Sol tool calls need Responses.
2. Foundry's gateway wizard lists only APIM **v2** instances in the same subscription; the gateway it creates is public.
3. Only portal-created, non-managed-OAuth MCP tools go through the Foundry gateway; later-added tools are not mediated.
4. The Learn pages lag: SIP, hosted-agent resilience, Voice Live labels and Astra Data Zone differ between pages and blogs.
5. Outbound VNet injection cannot be added later; the agent subnet is exclusive to one Foundry resource.
6. Hosted-agent sessions are capped at 1,000 concurrent per region by default; subnet exhaustion returns 429 `subnet_exhausted`.
7. Hosted sessions try to reach the Agent 365 telemetry endpoint; a locked-down firewall logs denials and traces are not exported unless you disable it.
8. Code interpreter in private setups cannot move files unless you create the container through the SDK; file search with Blob is unsupported.
9. Web search sends queries outside the DPA; the same applies to Bing custom search.
10. Routines do not support customer-managed keys.
11. Responses data persist 30 days by default; set `store=false` where GDPR retention matters.
12. Claude needs a Marketplace purchase, a non-CSP paid subscription, and is Global-only; GA lifetime 12 months.
13. Quota is per subscription, pooled: one noisy agent group can starve others unless the gateway caps it.
14. New subscriptions may start at Free tier with zero quota for GPT-6/5.6 and Grok 4.7.
15. Router quotas are lower in Data Zone than Global at every tier.
16. Copilot harness: no `temperature`, `tool_choice`, `max_output_tokens` or `prompt_cache_key`; every request needs a conversation.
17. Agent versions cap at 1,000 (terminal error); tool cap 128.
18. Hosted and prompt agents are absent from North Europe; plan West Europe or Sweden Central pairs.
19. Memory and voice agents are missing from some EU regions (Memory: no West Europe; voice: no Poland, Spain).
20. SDK drift: the .NET package is beta; the azd `azure.ai.*` extensions are beta and change command shapes between releases [S18].

## Appendix A — Could not verify

- Model router surcharge (no meter, no pricing-page text); GPT-6.1 Terra, GPT-5.4 variant and embedding prices; PTU minimums.
- Why no West Europe hosted-agent meter exists; whether Foundry-project calls from hosted agents pass through a Foundry gateway for Responses.
- Whether a BYOM connection or Foundry gateway accepts an APIM in another subscription; Citadel fronting of toolbox endpoints; Voice Live and Memory behind the hub.
- EU deployability of Data Zone Batch for gpt-5.5 (price meters exist, region table says no); Search regions for agentic retrieval; avatar regions and prices; SIP maturity; Decisions API status; Foundry IQ private ingestion clash.
- Azure Updates item pages are script-rendered; I read their text through the release-communications API `[S39]`.

## Appendix B — Sources (all fetched 2026-10-31)

`L` = `https://learn.microsoft.com/en-us/azure/`; bare paths below are relative to `L`. IDs are stable labels (S21, S41, S48–49 are unused). S1 foundry/what-is-foundry · S2 foundry/concepts/general-availability · S3 foundry/agents/overview · S4 foundry/agents/concepts/hosted-agents · S5 foundry/concepts/architecture · S6 foundry/foundry-models/concepts/deployment-types · S7 foundry/foundry-models/concepts/models-sold-directly-by-azure · S8 foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability · S9 foundry/openai/concepts/model-router · S10 foundry/openai/how-to/prompt-caching · S11 foundry/foundry-models/quotas-limits · S12 foundry/foundry-models/concepts/claude-models, foundry/foundry-models/concepts/claude-models-hosting-comparison, foundry/foundry-models/how-to/use-foundry-models-claude · S13 foundry/agents/concepts/toolbox-overview · S14 foundry/agents/concepts/limits-quotas-regions · S15 foundry/agents/how-to/ai-gateway · S16 foundry/configuration/enable-ai-api-management-gateway-portal · S17 foundry/agents/how-to/tools/governance · S18 `https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-september-2026/` · S19 `https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/microsoft-foundry-model-deployment-pricing-update/4535385` · S20 `https://azure.microsoft.com/en-us/pricing/details/foundry-agent-service/` · S22 foundry/agents/concepts/what-is-foundry-iq · S23 search/agentic-retrieval-how-to-migrate · S24 search/agentic-retrieval-overview, search/agentic-knowledge-source-overview · S25 search/search-sku-tier, search/search-limits-quotas-capacity · S26 foundry/agents/concepts/what-is-memory · S27 ai-services/speech-service/voice-live, ai-services/speech-service/regions · S28 `https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-july-august-2026/` · S29 foundry/agents/concepts/workflow · S30 foundry/agents/how-to/virtual-networks, foundry/how-to/configure-private-link · S31 foundry/agents/how-to/publish-copilot · S32 foundry/agents/concepts/routines · S33 foundry/agents/how-to/tools/model-context-protocol · S34 foundry/openai/how-to/flex-processing, foundry/openai/concepts/priority-processing · S35 foundry/fine-tuning/overview · S36 foundry/agents/how-to/tools/web-search, foundry/agents/how-to/enable-agent-to-agent-endpoint · S37 foundry/agents/concepts/voice-agent-pricing, ai-services/speech-service/text-to-speech-avatar/what-is-text-to-speech-avatar · S38 foundry/openai/how-to/decisions, `https://devblogs.microsoft.com/foundry/microsoft-copilot-harness-in-foundry/` · S39 Azure Updates via `https://www.microsoft.com/releasecommunications/api/v2/azure/<id>` (571821, 563536, 571816, 571826, 563481, 563716, 563222, 563601, 563616, 560992, 526330, 563451, 563516, 563636, 563212, 577260, 525952, 563282, 563491, 564176, 563436, 563456, 563506); canonical pages `https://azure.microsoft.com/en-us/updates/?id=<id>` · S40 foundry/openai/concepts/model-retirements · S42 foundry/control-plane/how-to-enforce-limits-models · S43 api-management/genai-gateway-capabilities · S44 `https://devblogs.microsoft.com/foundry/foundry-agent-service-ga/` · S45 `https://techcommunity.microsoft.com/t5/microsoft-foundry-blog/mistral-large-4-in-microsoft-foundry-build-sovereign-ai-within-a/ba-p/4568546`, `https://techcommunity.microsoft.com/t5/microsoft-foundry-blog/bring-your-own-telephony-to-voice-agents-via-sip/ba-p/4562702`, `https://techcommunity.microsoft.com/t5/microsoft-foundry-blog/turn-enterprise-knowledge-into-a-personalized-voice-and-avatar/ba-p/4564809` · S46 foundry/openai/how-to/responses · S47 foundry/agents/concepts/runtime-components, foundry/agents/concepts/prompt-agents, foundry/how-to/develop/sdk-overview · S50 = S39 avatar items · S51 `https://prices.azure.com/api/retail/prices` (filters on `Foundry Agents`, `Azure OpenAI GPT6/GPT5`, `Voice Live`, `Interpreter`, `Assistants`, `Grounding with Bing`, `AI Search agentic`) · S52 `https://devblogs.microsoft.com/foundry/browser-automation-tool-ga/` and `https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-build-2026/` · S53 foundry/agents/concepts/standard-agent-setup.
