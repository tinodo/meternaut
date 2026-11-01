# Options analysis — compute, data, operations and channels (A5)

> Research agent A5 · written 2026-10-31 · **evidence** for [the design](../README.md), not the design. **Today is 31 October 2026.** `[S#]` is a page I fetched (list in §7; "page date" is the page's own `updated_at`). `L###` is a line of the attachment (`Azure-AI-updates_2025-10-31_to_2026-10-31.md`). I name **meters, not prices** (P1 holds prices). `UNVERIFIED` = not confirmed on a fetched page. The design goal throughout: cost-minimal, scale-to-zero, private-networked.

**Reading guide.** *Idle* = what still bills when nobody is using it ("0" = nothing; "floor" = an hourly or monthly meter that runs anyway). *PE* = private endpoint; every PE has an hourly meter and a per-GB data-processed meter in each direction [S33]. Dispositions: `ADOPT` · `ADOPT-PREVIEW` · `EVALUATE` · `WATCH` · `N/A`, as in the brief. Component codes: COMP, DATA, KNW, OPS, OBS, CHAN, LAB, NET, COST.

---

## 1. What this research changes

**Ten findings that bend the design**

1. **Azure Deployment Environments retires 22 Feb 2027** (Dev Box 18 Sep 2028); Azure Lab Services retires 28 Jun 2027 [S75][S111]. The Lab cannot be built on either — use subscription vending + Deployment Stacks + a reaper (§2.i).
2. **Network-isolated Foundry agents exist only in "Standard Setup"**, which forces bring-your-own Cosmos DB, Storage and AI Search (Key Vault too in the manual path), each behind PEs [S3][S4][S5]. That is the unavoidable floor; Cosmos DB *serverless* is allowed [S4], so the real floor is AI Search + PE hours.
3. **AI Search now has a Serverless Developer tier (preview)** — consumption (compute-unit hours + indexed GB), scales to zero, inbound PE supported, billing began 13 Sep 2026 [S60][S62]. Preview limits: no shared private links (indexers cannot reach private sources), no SLA, no migration to/from other tiers [S60]; among EU regions only Denmark East, Poland Central, Sweden Central (plus Switzerland North, UK South) [S61]. First credible scale-to-zero search → `EVALUATE`.
4. **Private networking forces fixed meters on several "pay-per-use" services**: Service Bus PE = Premium only [S65]; ACR PE = Premium [S34]; Managed Grafana PE = Standard only [S86]; AI Search inbound PE = not on Free [S60]; Event Hubs PE = not on Basic [S68]; Container Apps PE (public preview) adds the "Dedicated plan management" meter [S10][S11][S32]. Ledger in §1.2.
5. **Hosted agents are GA (9 Jul 2026) and genuinely scale to zero**, but a session bills until its idle timeout (default 15 min), VNet injection can only be set at account creation, and North Europe is not a region [S1][S3][S6].
6. **Foundry Routines (GA 24 Sep 2026) replace hand-built schedulers** and work in VNet projects; Foundry *workflows* retire 1 Dec 2026 [S29][S30][S31].
7. **FinOps toolkit v15 (Oct 2026)** adds VNet/private modes for hubs, a local-container guide and agent plugins with a scoped read-only MCP server; hubs now deploy as None / ADX / Fabric / Remote [S56]. It is a ready-made ingestion layer to evaluate against our own.
8. **The "embedded engine" is not Microsoft technology.** DuckDB is MIT-licensed [S58] but third-party; flag against "Microsoft technology only". Microsoft-only equivalents: ADX Dev/Test, Synapse serverless SQL [S51][S59].
9. **Teams from a private Foundry project needs a public door**: the portal cannot publish projects that disable public network access; REST publishing with `enable_m365_public_endpoint` opens a source-IP-filtered route (Azure Bot Service / Microsoft 365 ranges) [S99].
10. **The Lab has no hard cap to lean on**: budgets evaluate every 24 h on cost data that lags 8–24 h and stop nothing; no spending limit exists on pay-as-you-go or commitment subscriptions [S107][S108]. Caps must be structural (policy, SKUs, quotas).

*Also notable:* Cosmos DB for PostgreSQL is on a retirement path [S49]; HorizonDB is preview, private-link only [S48]; from 31 Oct 2026 Application Insights routes GenAI content to its own `AppGenAIContent` table, which can sit on the cheaper Basic plan [S88][S90].

### 1.1 Region overlap (EU) — where the new things coexist

| Capability | West Europe | North Europe | Sweden Central |
|---|---|---|---|
| Hosted agents [S1] | listed | **not listed** | listed |
| Foundry managed VNet, new Agent Service [S9] | not listed | not listed | listed |
| AI Search Serverless (preview) [S61] | no | no | yes |
| AI Search agentic retrieval / zones [S61] | yes / yes | yes / yes | yes / yes |
| Dynamic sessions [S16] | yes | yes | yes |
| HorizonDB (preview) [S48] | no | no | yes |

Sweden Central is the only one of the three that carries all of them. Flex Consumption regions are CLI-listed, not on the page (`UNVERIFIED`) [S21].

### 1.2 Always-on meter ledger (what a private, scale-to-zero design still pays for)

| Trigger in our design | Meter that runs while idle | Avoid / alternative |
|---|---|---|
| Foundry Standard Setup (needed for BYO-VNet) | AI Search (dedicated: search-unit hours; serverless: 0), Storage capacity, PE hours ×(account, Search, Cosmos, Storage, Key Vault) [S3][S4] | Serverless AI Search (`EVALUATE`); Cosmos serverless |
| Any PE | hourly + per-GB processed [S33] | share PEs; one Monitor scope (AMPLS) [S84] |
| Container Apps environment with PE | Dedicated-plan-management meter [S10][S11] | internal environment + VNet integration instead of a PE [S12] |
| Private container registry | ACR Premium [S34] | deploy hosted agents from source [S7] |
| Service Bus behind a PE | Premium messaging unit [S65][S66] | Storage Queues + KEDA [S15][S71] |
| Event Grid namespace | throughput-unit hour [S70] | Event Grid Basic (pay per operation) |
| AI Search with inbound PE | dedicated-tier search units (Free has no PE) [S60] | Serverless Developer (preview) |
| Managed Grafana with PE | Standard-tier compute + per-user [S85][S86] | Workbooks; Azure Monitor dashboards with Grafana (no cost) [S85] |
| ADX | cluster compute (stoppable) [S51][S52] | Parquet + embedded engine |
| DTS Dedicated | fixed monthly per capacity unit [S25] | DTS Consumption / Azure Storage provider |
| Foundry managed VNet + FQDN rules | managed Azure Firewall (Standard default, Basic selectable, fixed at deployment) [S9] | BYO VNet behind the landing-zone firewall |
| Hosted-agent idle timeout | billed until timeout (default 15 min) [S1] | set 2 min for batch-style roles |
| Dynamic-session pools | 1-hour allocation increments; custom pools run on E16 [S10] | Sandboxes (preview) |
| ACS numbers; custom avatar/voice endpoint | monthly lease; endpoint hosting [S92][S101] | keep modules off |
| Teams meeting media bot | Windows Server VMs [S106] | not in phase 1 |
| Log Analytics commitment tier | ≥100 GB/day commitment [S81] | stay pay-as-you-go |

The Citadel gateway (APIM) is the largest floor of all and belongs to A1/P1.

### 1.3 Recommended stack at a glance

| Need | Default | Fallback | Idle floor of the default |
|---|---|---|---|
| (a) Hosting | prompt + hosted agents; Container Apps Consumption apps and jobs (internal environment) | MAF agents on Container Apps; Flex; AKS | 0 (beyond Standard Setup) |
| (b) Cost analytics | FOCUS/Parquet exports → private storage → embedded engine in a job | ADX Dev/Test; Synapse serverless; hubs "None" | storage |
| (c) Operational store | Cosmos DB serverless + immutable Blob | Azure SQL serverless with ledger tables | 0 |
| (d) Knowledge | Foundry IQ on the Standard-Setup AI Search (Basic) | AI Search Serverless Developer (preview) | search-unit hours |
| (e) Messaging | Routines; Storage Queues + KEDA jobs; Event Grid Basic | Service Bus Premium (1 unit) | 0 |
| (f) IaC | Bicep + AVM, subscription-scope Stacks, azd, Actions OIDC | Terraform / AzAPI | 0 |
| (g) Observability | per-table plans, one AMPLS, Workbooks + Grafana dashboards | Managed Grafana Standard | PE hours |
| (h) Channels | Foundry → Teams; Graph mail | ACS Email; Agents SDK | 0 |
| (i) Lab | vending + Stacks + reaper | one Lab subscription + reaper | 0 |

---

## 2. Needs

### (a) Hosting for agents and tools — `COMP` `NET`

| Option | Status (page date) | Cost meters | Idle & private networking | Pros (+) / cons (−) | Disp. |
|---|---|---|---|---|---|
| **Foundry hosted agents** | GA — announced 9 Jul 2026 [S6]; Azure Updates row dated 2 Jun (L462), Build post said "by end of June" [S7]; page 2026-10-27 has no preview note [S1] | vCPU-hour + GiB-hour of active sessions (0.5/1/2 vCPU; 1/2/4 GiB) [S1][S2] | **0** idle, but billed until the session's idle timeout (2–240 min, default 15) [S1]. BYO-VNet at account creation only; subnet delegated `Microsoft.App/environments`, ≥/27 [S3]; private ACR only for projects created after 25 Jun 2026 [S3]; egress controls preview, "not intended for production" [S8] | + per-session microVM, own agent identity, state survives idle, deploy from source or container [S1][S7]; − Python/C# only, one version takes 100 % traffic, env vars immutable per version [S1]; − Standard Setup floor; − not North Europe | `ADOPT` |
| Foundry prompt agents | GA; no extra charge for running them [S2] | tokens + tool meters only [S2] | 0; same project networking | + no hosting; − no custom code; Foundry *workflow* agents retire 1 Dec 2026 [S31] | `ADOPT` |
| **Container Apps — Consumption** (workload-profiles env) | no preview note (2026-01-29) [S14] | vCPU-s, GiB-s, HTTP requests; per-subscription monthly free: 180,000 vCPU-s, 360,000 GiB-s, 2 M requests [S10] | **0** at zero replicas; min-replicas > 0 bills the idle rate [S10]. Subnet ≥/27 delegated; internal environment possible [S12]; PE is **public preview** [S32] and adds the management meter [S11][S13] | + MCP servers, tool back-ends, Move runner; AVM modules [S76]; − cold start; − Premium ACR for a private registry [S34] | `ADOPT` |
| Container Apps **jobs** | no preview note [S15] | active vCPU-s/GiB-s per execution; no request meter [S10] | **0**; manual, cron or event (KEDA) triggers; replica timeout [S15] | + ideal for Move runner, nightly consolidation, queue-driven work; self-hosted CI runner pattern [S15]; − no ingress | `ADOPT` |
| ACA **dynamic sessions** | status not stated (pages 2026-04/05); shell + MCP additions preview 18 Nov 2025 (L778) [S16] | code interpreter: session-hours, allocation→deallocation **in 1-hour increments**; custom container: dedicated E16 pool [S10]; each execution ≤ 220 s [S17] | 0 with no sessions; custom pools are not scale-to-zero; "optional network controls" — details `UNVERIFIED` [S16]; West/North Europe, Sweden Central listed [S16] | + prewarmed, Hyper-V isolation; − hour granularity punishes short runs | `EVALUATE` |
| ACA **Sandboxes** | public preview (post: published 2 Jun, modified 15 Oct; L64 dates it 15 Oct) [S19]; Learn page 2026-10-16 states no status [S18] | per-second, same as Consumption; no CPU/memory fees while stopped/suspended [S11][S18] | 0; optional custom VNet, deny-by-default egress proxy with domain/CIDR rules [S19]; EU regions `UNVERIFIED` | + snapshot suspend/resume, microVM, the fabric under hosted agents; − preview, no SLA seen | `EVALUATE` |
| ACA **Express** | page 2026-09-23, no status [S20] | same per-second pricing [S11] | 0; PE and VNet egress supported [S20] | − no jobs, Dapr, Key Vault references, Easy Auth, custom domains | `WATCH` |
| **Functions Flex Consumption** | GA (no preview note) — "the recommended serverless hosting plan" (2026-09-30) [S21] | GB-s of executing on-demand instances (monthly free grant) + executions; always-ready adds a baseline GB-s with no free grant; 1,000 ms minimum then 100 ms rounding [S21] | **0** unless always-ready; VNet integration + PE for the app [S22]; delegation `Microsoft.App/environments` | + MCP tool/resource triggers, MCP Apps GA (L472, L602); one app per plan, no slots; − blob trigger needs Event Grid source [S21] | `ADOPT` |
| Functions serverless agents / agent bindings | Python bindings preview (L92); markdown-agent runtime status not stated (L241, L258) [S23] | as Flex | as Flex | + agent as a step in a queue-driven function; − young | `WATCH` |
| **Durable Task Scheduler** (+ Durable Functions / Durable Task SDKs) | both SKUs documented without preview note (2026-10-13/15) [S24][S25] | Dedicated: fixed monthly per CU (≤3 CUs; HA needs 3); Consumption: per action, no base fee, 500 actions/s, 30-day retention, no HA [S25] | Dedicated = floor; Consumption = 0; PEs supported [S24]; Flex hosts Durable with DTS or Azure Storage only [S21] | + checkpointed waits for human approval; − second state store besides Foundry's | `ADOPT` (Consumption) |
| Agent Framework durable extension | page 2026-10-16; packages prerelease [S26] | host + DTS | Flex scales to zero; or bring-your-own compute [S26] | + MAF workflows survive restarts; − prerelease | `EVALUATE` |
| **AKS** | Free / Standard / Premium tiers [S27] | node VMs + Standard control-plane fee | floor: system pool must run; user pools scale to 0; whole cluster can be stopped [S28] | − no scale-to-zero; capacity risk on restart [S28] | `N/A` default |

**Recommended default.** Prompt agents for single-turn roles; **hosted agents** for roles with custom tools or long loops, idle timeout set to the minimum that keeps checkpoints warm; **Container Apps Consumption (internal environment) apps** for our MCP back-ends and **jobs** for the Move runner and nightly work. Foundry's own durable state store holds MAF checkpoints [S1], so DTS is needed only where a Move must wait across job lifetimes.
**Fallback.** MAF agents self-hosted on Container Apps (loses per-session isolation and platform agent identity, keeps scale-to-zero); Flex Consumption for tiny MCP tools; AKS only for Kubernetes-specific needs.
**Code execution.** Foundry's Code Interpreter in a private BYO setup works only without file upload/download [S3]; use dynamic sessions today, Sandboxes when proven.
**Attachment — new.** Hosted agents GA and "long-running resilience" GA (L462, L18); Copilot harness preview (L18); Sandboxes (L64, L244), ACI sandboxes "emerging technology preview" (L355); AKS pod sandboxing in node auto-provisioning GA (L138); Functions MCP triggers/Apps GA (L472, L602, L804); Foundry Routines GA (L133).

### (b) Cost-data analytics — `DATA` `COST`

| Option | Status (page date) | Cost meters | Idle & private networking | Pros / cons | Disp. |
|---|---|---|---|---|---|
| **Parquet in object storage + embedded engine** in a Container Apps job | Cost Management exports: Parquet + Snappy, FOCUS, partitioned, to firewalled storage supported (2025-09-26) [S57]; DuckDB MIT; Azure extension reads Blob with CLI/managed-identity credential chain [S58] | storage GB-month + operations; PE hours/GB per storage sub-resource; job vCPU/GiB-s | **0 compute**; storage only; PE on storage | + no standing cluster; ≈20 GB per $1M monitored [S54]; − **DuckDB is third-party (MIT)** — check against "Microsoft technology only"; − we own SQL, dashboards, memory limits | `ADOPT` (flag) |
| Synapse serverless SQL pool | page 2026-10-12; retirement not flagged; roadmap vs Fabric `UNVERIFIED` [S59] | per TB processed (rounded per query) + storage [S59] | 0 compute; Private Link to managed workspace VNet [S59] | + Microsoft-only, no cluster; − Synapse workspace baggage | `EVALUATE` |
| **ADX Dev/Test** (no SLA) | page 2025-08-27 [S51] | cluster compute (single node; no ADX markup on dev) [S51]; FinOps hubs estimate ~$120/mo for a single-node cluster [S54] | **floor** unless stopped; auto-stop after 5 days idle, manual restart; not for VNet-injected clusters [S52]; PE supported, not on VNet-injected [S53] | + KQL, hub dashboards; − floor, minutes to start | `EVALUATE` |
| ADX **free cluster** | page 2026-06-11 [S50] | none | no subscription needed; no VNet/CMK/managed identity; no SLA; ~100 GB uncompressed [S50] | − outside the landing zone, cannot be private | `N/A` |
| Azure SQL serverless | page 2026-10-19 [S41] | vCore-seconds between min and max + storage [S41] | **storage only** when paused (GP delay 15 min–7 days, default 60; Hyperscale min 60 min, preview) [S41]; free offer: 100,000 vCore-s + 32 GB per database, ≤10 per subscription, fixed 15-min pause [S42] | + T-SQL, vector type [S43]; − resume latency, scans cost more than Parquet | `EVALUATE` |
| PostgreSQL flexible server | page 2026-09-05 [S45] | compute (Burstable B-series, General Purpose, Memory Optimized) + storage [S113] | stop ≤ 7 days then auto-restart; compute billing stops [S45][S46] | − not scale-to-zero | `N/A` for analytics |
| **FinOps hubs** v15 | Oct 2026 release [S56] | storage + Data Factory runs; optional ADX/Fabric; docs: from ~$120/mo with ADX, ~$5 per $1M monitored without ADX/Fabric [S54] | private mode adds network resources and dedicated Data Factory compute [S55]; v15 adds opt-in NAT Gateway [S56] | + maintained FOCUS ingestion, open data, agent plugin [S56]; − Data Factory dependency | `EVALUATE` |
| Fabric, Databricks | — | — | — | operator excluded | `N/A` |

**Recommended default.** Cost Management FOCUS/Parquet exports → private storage → an embedded engine in a scheduled job; summaries land in the operational store.
**Fallback.** ADX Dev/Test started by a job when a study needs KQL (accept the floor while on), or Synapse serverless; hubs in "None" mode as the ingestion layer if its private-mode cost beats our own ingestion.
**Attachment — new.** FinOps toolkit v15 (private mode, local container, agent plugins) is not in the attachment — I took it from [S56]; Azure MCP Server 3.0 expands Advisor cost tools (L16); Cost Management/pricing toolsets in the ARM MCP server (L208, L261); Claude spend now appears in Cost Management (L25); List Blobs returns Apache Arrow, preview (L189).

### (c) Operational store — `DATA`

| Option | Status (page date) | Cost meters | Idle & private networking | Pros / cons | Disp. |
|---|---|---|---|---|---|
| **Cosmos DB serverless** | no preview note (2026-04-27) [S35] | RUs consumed + storage; no minimum [S35] | **0**; single region only; AZ in designated regions [S35][S37]; max 5,000 RU/s per partition [S36]; no free tier on serverless [S38]; PE used in Foundry's private setup [S3]; Foundry allows serverless [S4] | + zero idle, JSON, change feed; MAF Cosmos memory provider (preview, L178, L275); − no multi-region; RU spikes on cross-partition/vector queries [S40]; vector-index support on serverless not stated — test [S39] | `ADOPT` |
| Cosmos provisioned / autoscale / free tier | free tier: first 1,000 RU/s + 25 GB, one account per subscription [S38] | provisioned RU/s-hours | floor | free tier fits a dev environment only | `ADOPT` (dev only) |
| **Azure SQL serverless** (General Purpose) | page 2026-10-19 [S41] | see (b) | storage only when paused; PE; append-only **ledger tables** with digests in immutable Blob [S44][S112] | + relational integrity, tamper evidence; − login-triggered resume | `EVALUATE` (fallback) |
| PostgreSQL flexible (pgvector, `pg_diskann`, AGE graph) | AGE GA May 2026 (L546); pg_diskann up to 16,000 dims with product quantization preview [S47] | compute + storage | **floor**; VNet integration [S45] | + one engine for relational, vector, graph; − always on | `EVALUATE` (fallback only) |
| **Azure HorizonDB** | **preview**; core-hour compute + storage + backup; private link only (no VNet injection); no CMK; 7-day backup; EU: Germany West Central, Sweden Central [S48] | provisioned compute | floor | − preview limits | `WATCH` |
| Cosmos DB for PostgreSQL | "on a retirement path and no longer recommended for new projects" [S49] | — | — | — | `N/A` |
| Immutable Blob (WORM) | time-based retention and legal hold; block and append blobs [S112] | capacity + operations | 0; PE | + tamper-evident approval record at near-zero cost; − not queryable | `ADOPT` (as sink) |

**Recommended default.** One **Cosmos DB serverless** account of our own (separate from Foundry's) in a single region; containers for Estate Model, Lesson Book, Experiment Ledger and approvals; every approval also appended to an immutable Blob container for the "append-only record" (H9). Foundry's own Standard Setup account needs at least 3,000 RU/s of capacity (five containers at 1,000 RU/s each, two used by the new runtime; multiply per project) — a floor in provisioned mode, not in serverless [S4].
**Fallback.** Azure SQL serverless with ledger tables if joins/integrity outweigh resume latency. PostgreSQL only if vector + graph + SQL in one engine becomes decisive.
**Attachment — new.** HorizonDB preview (L232, L371, L440); Cosmos integrated embeddings, spherical quantization, agent-memory toolkits (L422, L494, L537, L441); DocumentDB GA (L758); SQL MCP Server GA (L350); Cosmos cost tips (L581).

### (d) Vectors and knowledge — `KNW`

| Option | Status (page date) | Cost meters | Idle & private networking | Pros / cons | Disp. |
|---|---|---|---|---|---|
| AI Search **Free** | one per subscription; shared; may be deleted when inactive [S60] | none | no inbound PE, no managed identity, no IP firewall, no zones [S60] | − cannot be private | `N/A` |
| AI Search **Basic** | production, SLA with up to 3 replicas [S60] | search-unit hours | **floor**; inbound PE yes; indexer PE yes, but not for skillsets [S60][S62] | + lowest dedicated tier with PE | `ADOPT` |
| AI Search **Serverless Developer** | **public preview**, billing since 13 Sep 2026 (2026-09-17) [S60] | compute-unit hours + indexed GB-month [S60] | **0** idle ("scales to zero") [S64]; inbound PE and IP rules supported; no shared private links or NSP [S62]; EU: Denmark East, Poland Central, Sweden Central [S61] | + scale-to-zero search; − no SLA, no aliases, no migration, narrow regions; fit as Foundry's BYO Search `UNVERIFIED` | `EVALUATE` |
| **Foundry IQ** knowledge bases | GA 4 Jun 2026 (L374); needs a standard agentic-retrieval plan [S64]; LLM query planning, answer synthesis and non-minimal reasoning effort are preview [S63] | AI Search retrieval tokens + semantic ranking (free monthly allowance, then pay-as-you-go) + model tokens for planning [S63] | private connectivity GA (L373) | + managed retrieval, permission-aware sources; − token meters scale with query complexity | `ADOPT` |
| Cosmos DB vectors | flat (≤505 dims), quantizedFlat and DiskANN (≤4,096) [S39] | RUs | as (c) | + no extra resource; integrated embeddings preview (L422) | `EVALUATE` |
| pgvector / `pg_diskann` | page 2026-07-13 [S47] | compute | floor | − always on | `N/A` default |
| Azure SQL `vector` type | float16 vectors GA [S43]; vector-index status `UNVERIFIED` | vCore-s | as (b) | − young | `WATCH` |

**Recommended default.** Because Standard Setup *forces* an AI Search resource anyway, **reuse it** for the Atlas knowledge base (Foundry IQ) — marginal floor zero; **Basic** is the lowest dedicated tier that can sit behind a PE. Estate/Lesson recall via Cosmos vectors only if a test on serverless passes.
**Fallback.** Serverless Developer once it leaves preview (or if Sweden Central/Poland Central is the home region) — the one move that removes the search floor.
**Attachment — new.** Foundry IQ GA (L374); serverless indexers preview (L410); auto retrieval-reasoning effort preview (L112); AI Search ↔ APIM for Foundry models preview (L370); Purview sensitivity labels in knowledge sources preview (L411).

### (e) Messaging and durability — `COMP` `OPS`

| Option | Status (page date) | Cost meters | Idle & private networking | Pros / cons | Disp. |
|---|---|---|---|---|---|
| **Storage Queues + ACA event jobs (KEDA)** | queue ≤ 64 KB messages [S71]; job event trigger [S15] | operations + capacity | **0**; PE per storage sub-resource | + simplest private pay-per-use path; − no sessions or dead-letter beyond poison handling | `ADOPT` |
| **Foundry Routines** | **GA** 24 Sep 2026 (page 2026-10-23) [S29][S30] | no separate meter stated; agent tokens/compute apply | 0; works in VNet projects; no CMK; not in UK West, Switzerland West, Japan West, UAE North, Norway East [S29] | + timer, recurring (≥5 min), GitHub issue and Teams-channel triggers; one trigger, one action; prompt and hosted agents only [S29] | `ADOPT` |
| Event Grid **Basic** | topics/domains; first 100,000 operations/month free [S70] | per operation (published events, filtering, delivery) | 0; PE for topic/domain ingress [S69]; delivery to private targets `UNVERIFIED` | + cheap trigger for export-landed events (hubs rely on it [S54]) | `ADOPT` |
| Event Grid **namespaces** | standard tier [S70] | throughput-unit hour + MQTT/event operations (1 M free each) | **floor** | − MQTT is not our need | `N/A` |
| **Service Bus** | Basic (queues), Standard (hourly base charge incl. 13 M ops/month), Premium (messaging units 1/2/4/8/16) [S66][S67] | per operation / per unit | **PE requires Premium** [S65] → floor | + sessions, dead-letter, ordering; − Premium floor | `EVALUATE` (fallback) |
| Event Hubs | PE not on Basic [S68] | capacity-based (not fetched) | floor | − no streaming need | `N/A` |
| DTS / Durable Functions | see (a) | | | | `ADOPT` |
| Logic Apps Automation SKU | public preview (L434); Foundry's migration target for workflows [S31] | `UNVERIFIED` | `UNVERIFIED` | + visual orchestration | `WATCH` |

**Recommended default.** Agent scheduling → Routines; non-agent schedules and fan-out → Container Apps cron/event jobs on Storage Queues; export-landed events → Event Grid Basic; durable waits → MAF checkpoints, DTS Consumption only if needed.
**Fallback.** One shared Service Bus Premium namespace (1 unit) if ordering/sessions/dead-letter are required by a Citadel pattern.
**Attachment — new.** Routines GA (L133, L62, L103); long-running MCP tools on Functions with Durable (L318); message brokers for agentic backends (L707); Foundry workflows retire 1 Dec 2026 (L41).

### (f) Infrastructure as code and delivery — `OPS`

| Option | Status (page date) | Cost meters | Notes | Disp. |
|---|---|---|---|---|
| **Bicep + Azure Verified Modules** | AVM Bicep: 173 published + 24 proposed resource modules; now owned by Azure engineering (page 2026-10-26) [S76] | none | modules for container-app, job, managed-environment, session-pool, durable-task scheduler, Cosmos, AI Search, ACS (service + email), APIM, Grafana, Log Analytics, Service Bus, Kusto, PostgreSQL, SQL, Functions, ACR, Bot Service, Key Vault, Foundry account + project; patterns `ai-ml/ai-foundry`, `ai-platform/baseline` [S76]. No module for Sandboxes or hosted-agent versions seen; legacy-wrapper refactoring is real work (L552) | `ADOPT` |
| **Deployment Stacks** | RG, subscription, management-group scope (2026-06-24) [S72] | none | deny settings (≤5 excluded principals — use groups); up to 800 stacks per scope; known issues: deleting the RG bypasses deny assignments (deploy at subscription scope and put the RG in the template), Microsoft Graph provider unsupported, no what-if, cannot delete Key Vault secrets [S72][S73] | `ADOPT` |
| **azd** | no status note; `azd ai agent` extension for hosted agents; extension framework GA 8 Sep 2026; Container App Jobs deployment (L175, L621, L757, L613) [S77] | none | Bicep or Terraform; workflows for GitHub Actions or Azure Pipelines [S77] | `ADOPT` |
| Terraform (azurerm / AzAPI) | AzAPI path for hosted agents (L106); Azure MCP Server 3.0 adds Terraform and AVM tools (L16) | none | fallback where a resource type lags in Bicep | `EVALUATE` |
| **GitHub Actions + OIDC** | `azure/login@v2`; federated credential on an Entra app or user-assigned identity (2026-01-21) [S78] | runner minutes | hosted runners are public; deploying into private resources needs self-hosted runners — a Container Apps event job can be the runner [S15]; reusable workflows (L559) | `ADOPT` |
| Azure Deployment Environments | **retires 22 Feb 2027**; writes blocked, read/delete for a time-bound clean-up [S74][S75] | — | replacements named: Bicep/ARM, AVM, GitHub/DevOps workflows [S75] | `N/A` |

**Recommended default.** Bicep + AVM, deployed as **subscription-scope Deployment Stacks** with deny settings; azd as the developer loop and hosted-agent deploy; GitHub Actions with OIDC and self-hosted runners for private targets. **Fallback.** Terraform/AzAPI per resource family that lacks Bicep types.
**Attachment — new.** azd extension framework GA (L175); azd + Copilot scaffolding (L583); drift-detection patterns (L547, L553, L607); AVM refactoring (L552).

### (g) Observability — `OBS`

| Option | Status (page date) | Cost meters | Notes | Disp. |
|---|---|---|---|---|
| **Log Analytics — table plans** | Analytics / Basic / **Auxiliary-Lake** (the pages' current wording) (2026-09-21) [S79][S80] | Analytics: ingestion, query included, 31 d free retention. Basic: reduced ingestion, per-query charge, 30 d. Auxiliary-Lake: minimal ingestion, slower queries, no alerts, 30 d [S79][S82][S83]; first 5 GB/month per billing account free (Analytics, pay-as-you-go) [S82]; one plan switch per table per week [S80] | put audit/long-retention tables on Auxiliary-Lake, troubleshooting on Basic; commitment tiers start at 100 GB/day and cover only Analytics [S81] — do not buy; if Sentinel's data lake is on, Sentinel meters bill query, search and long-term retention [S81] | `ADOPT` |
| **Application Insights** (workspace-based) | `AppGenAIContent` table; from **31 Oct 2026** content stops flowing to the old tables for new data [S90]; protected-table access preview [S89] | Basic plan supported; Auxiliary not; no ingestion-time transform [S88]; 90 days free retention [S82] | prompts/responses are the volume risk — keep them on Basic, restricted by Privileged Monitoring Data Reader | `ADOPT-PREVIEW` (GA fallback: sample content) |
| **Azure Monitor Private Link Scope** | page 2026-07-13 [S84] | PE hours | use **one** AMPLS per shared DNS; several override each other's zones [S84] | `ADOPT` |
| **Workbooks** | page 2026-04-02; no meter stated [S87] | queries against Basic/Auxiliary tables or long-term data are charged [S83] | in-portal, RBAC-governed | `ADOPT` |
| **Azure Monitor dashboards with Grafana** | in-portal, "no cost", Azure Monitor/Prometheus/Resource Graph sources, current-user auth only [S85] | none | no external sources, alerts or scheduled reports [S85] | `ADOPT` |
| Azure **Managed Grafana** | Standard (X1/X2) only; Essential cannot be created and is fully deprecated by 31 Mar 2027 (2026-06-29) [S86] | Standard compute + per-user [S85] | PE, alerting, SMTP, deterministic outbound IPs only on Standard [S86]; MCP server built in (L623) | `EVALUATE` (fallback) |
| Azure Copilot **Observability Agent** | GA; supports Basic/Auxiliary tables from 1 Sep 2026 (L194) | consumption billing in Azure Agent Credits since 1 Jul 2026 (L288) [S91] | useful, not free | `WATCH` (off by default) |

**Recommended default.** One workspace per environment, per-table plans, one AMPLS, Workbooks + Azure Monitor dashboards with Grafana. **Fallback.** Managed Grafana Standard only for non-Azure sources, Grafana alerts or scheduled reports.
**Attachment — new.** OpenTelemetry direct ingest GA (L361); GenAI content table preview (L284); Observability Agent on Basic/Auxiliary logs (L182, L194); Managed Grafana MCP (L623); SRE Agent reading Grafana dashboards (L162).

### (h) Communication — `CHAN`

| Option | Status (page date) | Cost meters | Private networking & notes | Disp. |
|---|---|---|---|---|
| **Teams via Foundry publish** | GA 18 Sep 2026 (L146); page 2026-09-28 [S99] | Azure Bot Service is free for standard channels, Teams included [S98]; "publisher-pays" for the infrastructure of a published application, not per call [S100] | portal cannot publish projects with public access disabled; REST + `enable_m365_public_endpoint` opens a source-IP-filtered route [S99] | `ADOPT` |
| **Microsoft 365 Agents SDK** | C#, JavaScript, Python; no status note (2026-10-16) [S97] | Bot Service free; hosting is ours | Bot Service PE exists only for the Direct Line App Service extension [S32] → public HTTPS inbound for Teams | `EVALUATE` (when Foundry publish is too narrow) |
| **Microsoft Graph mail** | `sendMail` with `Mail.Send` (application permission ok) [S95]; Exchange RBAC for Applications scopes mailboxes and replaces Application Access Policies (2026-10-27) [S96] | no Azure meter; Exchange limits and throttling apply [S95] | egress to Graph over public endpoints; mailbox licensing `UNVERIFIED`; enables two-way mail (Mail.Read) | `ADOPT` |
| **ACS Email** | separate Email Communication resource; custom domain, SPF/DKIM [S93] | per email + per MB [S92] | Private Link not on the availability list (2026-10-07) [S32]; outbound-only as far as I read | `EVALUATE` (fallback) |
| ACS **SMS** | NL: mobile numbers send/receive, alphanumeric ID send-only; DE and FR: alphanumeric sender ID only (send); GB: mobile + sender ID, unregistered GB IDs blocked since 30 Jun 2024; paid subscription needed; sender-ID eligibility on the France page: MCA, CSP, pay-as-you-go, EA with a case-by-case footnote [S94] | per message + monthly number lease (prices vary) [S92] | **off by default** | `WATCH` |
| **Voice Live** + voice agents | Voice Live integration with Agent Service GA (L449); Learn calls Foundry voice agents "preview", with native telephony through Teams Phone extensibility or Twilio (2026-10-08) [S103] — page wins | token billing by tier (Pro/Standard/Lite/BYO), avatar per minute, custom-endpoint hosting [S101][S102]; 100,000 tokens/min per resource [S104] | Direct SIP / BYO telephony (L14) [S105]; ACS Call Automation via ACS number or direct routing [S103]; private networking for Voice Live `UNVERIFIED` | `ADOPT-PREVIEW` (module off) |
| **Avatar in a Teams meeting** | application-hosted media bot: .NET + Windows Server VMs, GPU for video [S106] | VM floor + avatar minutes | always-on | `N/A` phase 1 |

**Recommended default.** Teams (Adaptive Cards) through Foundry publish; email through Graph with an Exchange-RBAC-scoped app on a shared mailbox, so replies are readable; voice, SMS and avatar modules stay off. **Fallback.** ACS Email for external senders; the Agents SDK for custom channel logic.
**Attachment — new.** Publish-to-Teams GA (L146); Voice Agent with Foundry IQ and a photo avatar (L11); SIP trunks (L14); photo avatar GA (L453); Speech LLM 09-2026 (L33).

### (i) The Lab — `LAB` `COST`

| Option | Status (page date) | Cost meters | Notes | Disp. |
|---|---|---|---|---|
| **Subscription vending** (Bicep and Terraform modules) | Architecture Center guidance (2026-10-05) [S109] | none | creates the subscription, places it in a management group, adds a starter budget, RBAC, policy assignments, Defender for Cloud config, optional peering [S109]; programmatic creation is documented for EA, MCA and MPA agreement types [S110] | `ADOPT` |
| **Deployment Stacks per experiment** | see (f) [S72] | none | delete on unmanage; put the RG inside the template [S73] | `ADOPT` |
| **Budgets + action groups** | page 2025-09-26 [S107] | none | cost data arrives in 8–24 h, budgets evaluate every 24 h, resources are untouched; action groups only at subscription/RG scope [S107]; budget → runbook pattern that disables Azure OpenAI access (L619) | `ADOPT` (alarm, not brake) |
| Spending limit | not available on commitment or pay-as-you-go subscriptions [S108] | — | no hard cap exists for EA/MCA | `N/A` |
| ACA Sandboxes | see (a) | per-second | code-level experiments | `EVALUATE` |
| Azure Deployment Environments / Lab Services | retire 22 Feb 2027 / 28 Jun 2027 [S75][S111] | — | — | `N/A` |

**Recommended default.** A Lab management group; vended subscriptions that stamp budgets, policy (allowed SKUs/regions, deny public IPs — A4) and RBAC; each experiment is a Deployment Stack with a TTL tag, torn down by a scheduled Container Apps job that queries Resource Graph. **Because billing evidence lags 8–24 h, an experiment needs to run ≥ 2 days, so caps must be structural (policy, quotas, SKUs), never budget-triggered.** **Fallback.** One Lab subscription with per-experiment resource groups plus the same reaper.
**Attachment — new.** Sandboxes (L64, L244); budget/runbook cost control (L619); per-task disposable Cosmos environments (L20); cost toolsets in the ARM MCP server (L208, L261).

---

## 3. Source conflicts (the page wins)

| Topic | Says | Page that wins |
|---|---|---|
| Hosted-agents GA | attachment: 2 Jun 2026 (L462) | announced 9 Jul 2026 [S6]; Build post said "by end of June" [S7] |
| Sandboxes preview | attachment: 15 Oct 2026 (L64) | post published 2 Jun, modified 15 Oct [S19] |
| Container Apps PE | how-to page: no status | "Public Preview" on the Private Link list (2026-10-07) [S32] |
| Voice agents | attachment: Voice Live GA (L449) | voice agents "preview" (2026-10-08) [S103]; Voice Live–Agent Service integration is the GA part |
| Managed Grafana | attachment: MCP in "every instance" (L623) | Essential cannot be created, deprecated by 31 Mar 2027 [S86] |
| Foundry IQ plan | Learn: free plan is the default [S63] | pricing page: knowledge bases require a standard plan [S64] |

## 4. Design implications

- **Choose the region first.** Sweden Central is the only EU region of the three that offers hosted agents, managed VNet, serverless AI Search and dynamic sessions together (§1.1).
- **Share, don't multiply.** One Cosmos account per purpose, one AI Search, one AMPLS, one Storage account per tier of sensitivity: each PE is an hourly meter.
- **Prefer internal environments to PEs on Container Apps** while PEs are in preview and carry the management meter.
- **Set hosted-agent idle timeouts per role.** On the documented 15-minute default, a 30-second job bills about thirty times its runtime (my arithmetic).
- **Treat Lab budgets as alarms.** The brake is structure.
- **Prefer a bring-your-own VNet to Foundry's managed VNet** unless the home region is Sweden Central: managed-VNet FQDN rules create one managed Azure Firewall per account that cannot be shared or re-SKU'd [S9].
- **Keep GenAI trace content on the Basic plan** in `AppGenAIContent` [S88]; commitment tiers start at 100 GB/day [S81], which a scale-to-zero estate is unlikely to reach (my assumption).
- **Deploy hosted agents from source** to avoid a Premium registry for them [S7]; Container Apps images still need one for private pulls [S34].
- **Name the third-party dependency.** DuckDB goes to the operator as an explicit exception or is replaced by ADX/Synapse.

## 5. Could not verify

ACA Sandboxes EU regions and the dynamic-sessions network-control details; Flex Consumption's region list; Cosmos serverless vector-index and backup options; Azure SQL vector-index status; Event Grid namespace PEs and delivery to private targets; Event Hubs meters; DTS PE support per SKU and GA date; ACS Private Link (absence from a list is not proof) and ACS inbound email; Voice Live private networking; Graph shared-mailbox licensing and the Bot Service source-IP service tag; whether Foundry's BYO Search accepts the Serverless Developer tier and which tier Standard Setup minimally needs; Bicep/ARM types for hosted-agent versions; Synapse's roadmap; Logic Apps Automation meters; Azure Policy and Resource Graph specifics (A4); GitHub federated-credential limits.

## 6. Counts

9 needs analysed; 68 option rows: 29 `ADOPT`, 2 `ADOPT-PREVIEW`, 17 `EVALUATE`, 7 `WATCH`, 13 `N/A` (a few options recur across needs, so rows overcount distinct products); 113 source entries (117 URLs, §7); 6 source conflicts (§3).

## 7. Sources (all fetched 2026-10-31)

S1 https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents · S2 https://azure.microsoft.com/pricing/details/foundry-agent-service/ · S3 https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks · S4 https://learn.microsoft.com/azure/foundry/agents/concepts/standard-agent-setup · S5 https://learn.microsoft.com/azure/foundry/agents/environment-setup · S6 https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-july-august-2026/ · S7 https://devblogs.microsoft.com/foundry/hosted-agents-build26/ · S8 https://devblogs.microsoft.com/foundry/egress-controls-hosted-agent/ · S9 https://learn.microsoft.com/azure/foundry/how-to/managed-virtual-network · S10 https://learn.microsoft.com/azure/container-apps/billing · S11 https://azure.microsoft.com/pricing/details/container-apps/ · S12 https://learn.microsoft.com/azure/container-apps/custom-virtual-networks · S13 https://learn.microsoft.com/azure/container-apps/how-to-use-private-endpoint · S14 https://learn.microsoft.com/azure/container-apps/plans · S15 https://learn.microsoft.com/azure/container-apps/jobs · S16 https://learn.microsoft.com/azure/container-apps/sessions · S17 https://learn.microsoft.com/azure/container-apps/sessions-code-interpreter · S18 https://learn.microsoft.com/azure/container-apps/sandboxes-overview · S19 https://techcommunity.microsoft.com/blog/appsonazureblog/introducing-azure-container-apps-sandboxes-secure-infrastructure-for-agentic-wor/4524131 · S20 https://learn.microsoft.com/azure/container-apps/express-overview · S21 https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan · S22 https://learn.microsoft.com/azure/azure-functions/functions-networking-options · S23 https://techcommunity.microsoft.com/blog/appsonazureblog/add-ai-to-the-workflows-you-already-have-using-serverless-agents-in-azure-func/4544824 · S24 https://learn.microsoft.com/azure/durable-task/scheduler/durable-task-scheduler · S25 https://learn.microsoft.com/azure/durable-task/scheduler/durable-task-scheduler-billing · S26 https://learn.microsoft.com/agent-framework/integrations/azure-functions · S27 https://learn.microsoft.com/azure/aks/free-standard-pricing-tiers · S28 https://learn.microsoft.com/azure/aks/start-stop-cluster · S29 https://learn.microsoft.com/azure/foundry/agents/concepts/routines · S30 https://devblogs.microsoft.com/foundry/from-chatbots-to-automated-assistants-routines-in-microsoft-foundry-are-now-generally-available/ · S31 https://techcommunity.microsoft.com/t5/azure-integration-services-blog/orchestrate-foundry-prompt-and-hosted-agents-with-logic-apps/ba-p/4566381 · S32 https://learn.microsoft.com/azure/private-link/availability · S33 https://azure.microsoft.com/pricing/details/private-link/ · S34 https://learn.microsoft.com/azure/container-registry/container-registry-private-link · S35 https://learn.microsoft.com/azure/cosmos-db/serverless · S36 https://learn.microsoft.com/azure/cosmos-db/serverless-performance · S37 https://learn.microsoft.com/azure/cosmos-db/throughput-serverless · S38 https://learn.microsoft.com/azure/cosmos-db/free-tier · S39 https://learn.microsoft.com/azure/cosmos-db/nosql/vector-search · S40 https://devblogs.microsoft.com/cosmosdb/7-tips-to-optimize-azure-cosmos-db-costs-for-ai-and-agentic-workloads/ · S41 https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-overview · S42 https://learn.microsoft.com/azure/azure-sql/database/free-offer · S43 https://learn.microsoft.com/sql/t-sql/data-types/vector-data-type · S44 https://learn.microsoft.com/sql/relational-databases/security/ledger/ledger-overview · S45 https://learn.microsoft.com/azure/postgresql/overview · S46 https://learn.microsoft.com/azure/postgresql/configure-maintain/how-to-stop-server · S47 https://learn.microsoft.com/azure/postgresql/extensions/how-to-use-pgdiskann · S48 https://learn.microsoft.com/azure/horizondb/overview · S49 https://learn.microsoft.com/azure/cosmos-db/postgresql/introduction · S50 https://learn.microsoft.com/azure/data-explorer/start-for-free · S51 https://learn.microsoft.com/azure/data-explorer/manage-cluster-choose-sku · S52 https://learn.microsoft.com/azure/data-explorer/auto-stop-clusters · S53 https://learn.microsoft.com/azure/data-explorer/security-network-private-endpoint · S54 https://learn.microsoft.com/cloud-computing/finops/toolkit/hubs/finops-hubs-overview · S55 https://learn.microsoft.com/cloud-computing/finops/toolkit/hubs/private-networking · S56 https://github.com/microsoft/finops-toolkit/releases · S57 https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports · S58 https://github.com/duckdb/duckdb-azure and https://github.com/duckdb/duckdb · S59 https://azure.microsoft.com/pricing/details/synapse-analytics/ and https://learn.microsoft.com/azure/synapse-analytics/sql/on-demand-workspace-overview · S60 https://learn.microsoft.com/azure/search/search-sku-tier · S61 https://learn.microsoft.com/azure/search/search-region-support · S62 https://learn.microsoft.com/azure/search/search-limits-quotas-capacity · S63 https://learn.microsoft.com/azure/search/agentic-retrieval-overview · S64 https://azure.microsoft.com/pricing/details/search/ · S65 https://learn.microsoft.com/azure/service-bus-messaging/private-link-service · S66 https://learn.microsoft.com/azure/service-bus-messaging/service-bus-premium-messaging · S67 https://azure.microsoft.com/pricing/details/service-bus/ · S68 https://learn.microsoft.com/azure/event-hubs/private-link-service · S69 https://learn.microsoft.com/azure/event-grid/configure-private-endpoints · S70 https://azure.microsoft.com/pricing/details/event-grid/ · S71 https://learn.microsoft.com/azure/storage/queues/storage-queues-introduction · S72 https://learn.microsoft.com/azure/azure-resource-manager/bicep/deployment-stacks · S73 https://learn.microsoft.com/azure/azure-resource-manager/bicep/deployment-stacks-known-issues · S74 https://learn.microsoft.com/azure/deployment-environments/overview-what-is-azure-deployment-environments · S75 https://learn.microsoft.com/azure/deployment-environments/deployment-environments-retirement-guide · S76 https://azure.github.io/Azure-Verified-Modules/ (indexes: https://azure.github.io/Azure-Verified-Modules/indexes/bicep/bicep-resource-modules/, https://azure.github.io/Azure-Verified-Modules/indexes/bicep/bicep-pattern-modules/) · S77 https://learn.microsoft.com/azure/developer/azure-developer-cli/overview · S78 https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect · S79 https://learn.microsoft.com/azure/azure-monitor/logs/data-platform-logs · S80 https://learn.microsoft.com/azure/azure-monitor/logs/logs-table-plans · S81 https://learn.microsoft.com/azure/azure-monitor/logs/cost-logs · S82 https://azure.microsoft.com/pricing/details/monitor/ · S83 https://learn.microsoft.com/azure/azure-monitor/fundamentals/cost-usage · S84 https://learn.microsoft.com/azure/azure-monitor/fundamentals/private-link-security · S85 https://learn.microsoft.com/azure/azure-monitor/visualize/visualize-grafana-overview · S86 https://learn.microsoft.com/azure/managed-grafana/overview · S87 https://learn.microsoft.com/azure/azure-monitor/visualize/workbooks-overview · S88 https://learn.microsoft.com/azure/azure-monitor/reference/tables/appgenaicontent · S89 https://learn.microsoft.com/azure/foundry/observability/how-to/traces-sensitive-content · S90 https://learn.microsoft.com/azure/azure-monitor/app/data-model-complete · S91 https://techcommunity.microsoft.com/t5/azure-observability-blog/understanding-billing-for-the-azure-copilot-observability-agent/ba-p/4537780 · S92 https://azure.microsoft.com/pricing/details/communication-services/ · S93 https://learn.microsoft.com/azure/communication-services/concepts/email/email-overview · S94 https://learn.microsoft.com/azure/communication-services/concepts/numbers/phone-number-management-for-netherlands (also …-germany, …-france, …-united-kingdom) · S95 https://learn.microsoft.com/graph/api/user-sendmail · S96 https://learn.microsoft.com/exchange/permissions-exo/application-rbac · S97 https://learn.microsoft.com/microsoft-365/agents-sdk/agents-sdk-overview · S98 https://azure.microsoft.com/pricing/details/bot-services/ · S99 https://learn.microsoft.com/azure/foundry/agents/how-to/publish-copilot · S100 https://learn.microsoft.com/azure/foundry/agents/how-to/agent-applications · S101 https://azure.microsoft.com/pricing/details/speech/ · S102 https://learn.microsoft.com/azure/ai-services/speech-service/voice-live · S103 https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-telephony · S104 https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-faq · S105 https://techcommunity.microsoft.com/blog/microsoftfoundryblog/bring-your-own-telephony-to-voice-agents-via-sip/4562702 · S106 https://learn.microsoft.com/microsoftteams/platform/bots/calls-and-meetings/real-time-media-concepts · S107 https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets · S108 https://learn.microsoft.com/azure/cost-management-billing/manage/spending-limit · S109 https://learn.microsoft.com/azure/architecture/landing-zones/subscription-vending · S110 https://learn.microsoft.com/azure/cost-management-billing/manage/programmatically-create-subscription · S111 https://learn.microsoft.com/azure/lab-services/lab-services-overview · S112 https://learn.microsoft.com/azure/storage/blobs/immutable-storage-overview · S113 https://learn.microsoft.com/azure/postgresql/compute-storage/concepts-compute
