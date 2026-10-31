# Design 02 — Technology landscape

> **What this answers:** *What does the Microsoft AI ecosystem offer today — as of 2026-10-31 — and which of it does this design adopt, hold behind a switch, evaluate or leave alone?* The operator supplied a year of updates (817 rows, 31 October 2025 to 31 October 2026); this document is the verdict on all of them, and the evidence behind every verdict is in the research files it links. Part of the [design](README.md).

---

## 1. How the landscape was built

1. **Every one of the 817 updates was triaged exactly once**, by eight parallel research agents, each reading a slice of about 100 rows and *following the links* to Learn pages, specifications, release notes and the Release Communications API (the Azure Updates pages are script-rendered shells and return no text). Each row got a disposition; related rows were merged into **267 clusters** with a status, a fit, a note on cost or security, and sources.
2. **Five core studies** went deeper where the design needed precision: the [Citadel framework](research/citadel.md), [Foundry Agent Service, models, knowledge and memory](research/foundry-agent-service.md), [Foundry governance, identity, networking, evaluation and the Agent Framework](research/foundry-governance-and-framework.md), [security and compliance](research/security-and-compliance.md) and an [options analysis](research/options-analysis.md) of hosting, data, operations and channels. A reproducible [price snapshot](research/prices.md) feeds the [cost model](12-cost-and-finops.md).
3. **The register is generated, never hand-edited:** `tools/merge-features.py` merges the eight digests into the [feature register](research/feature-register.md) and checks that every row is covered once.
4. **Evidence rules.** The **page wins** over the attachment when they disagree (the research names each clash). Every status carries its date and its source. A claim that rests on the attachment alone is marked *unverified*. Prices are **indicative**, from the Retail Prices API on 2026-10-31.

| Slice | Attachment rows | Digest |
|---|---|---|
| F1 | 11–112 | [features-01](research/features-01.md) |
| F2 | 113–214 | [features-02](research/features-02.md) |
| F3 | 215–316 | [features-03](research/features-03.md) |
| F4 | 317–418 | [features-04](research/features-04.md) |
| F5 | 419–520 | [features-05](research/features-05.md) |
| F6 | 521–622 | [features-06](research/features-06.md) |
| F7 | 623–724 | [features-07](research/features-07.md) |
| F8 | 725–827 | [features-08](research/features-08.md) |

| Disposition | Clusters | Rows | Meaning |
|---|---|---|---|
| **ADOPT** | 52 | 75 | generally available and fit for the design |
| **ADOPT-PREVIEW** | 20 | 31 | fit, but preview: only behind a switch with a named fallback |
| **EVALUATE** | 101 | 131 | plausible; a spike or a measurement decides |
| **WATCH** | 88 | 322 | relevant later, or not yet mature |
| **N/A** | 6 | 258 | out of scope (Databricks and Fabric by constraint C10; other products) |

## 2. The twelve hypotheses, judged

The research brief began with twelve hypotheses about the platform. This is what the evidence did to each.

| # | Hypothesis | Verdict | What changed | Answered in |
|---|---|---|---|---|
| **H1** | Foundry Agent Service, with Agent Framework workflows | **Confirmed, with an edit** | Foundry visual workflows retire **1 Dec 2026**; hosted agents are generally available; prompt agents leave the critical path (reaching the gateway needs a connection limited to Chat Completions, while the strongest models need Responses for tool calls); orchestration moves *out* of any agent into a deterministic spine | [05](05-agents-and-orchestration.md), [ADR-01](13-decisions.md#adr-01-a-deterministic-spine-calls-agentic-leaves) |
| **H2** | Everything through the Citadel hub | **Confirmed, with a split** | "AI gateway" now means three things; Citadel is a **single-maintainer sample**, not a service; hosted agents call the hub from code; a **bypass register** lists eleven paths that skip it and how each is closed | [04](04-landing-zone-and-citadel.md), [ADR-02](13-decisions.md#adr-02-the-gateway-is-the-citadel-governance-hub-on-api-management) |
| **H3** | Private networking only | **Partly** | four named public-ingress or non-private exceptions; managed VNet is a one-way door with a managed-firewall charge; the standard setup forces bring-your-own stores; Purview's Foundry integration does not support network isolation | [04 §6–7](04-landing-zone-and-citadel.md#6-network), [07 §7](07-security-architecture.md#7-network-and-the-short-list-of-exceptions) |
| **H4** | Two planes with just-in-time identity | **Holds; the mechanism changed** | PIM cannot make a managed identity eligible, so a broker creates and removes a scoped role assignment | [07 §3.3](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim), [ADR-07](13-decisions.md#adr-07-execution-identities-are-granted-just-in-time-by-a-broker) |
| **H5** | Git plus a search index plus one serverless store; columnar files and an embedded engine | **Confirmed** | Cosmos DB serverless chosen with Azure SQL as fallback; the embedded engine is a **recorded exception to C1**; Foundry Memory not used | [06 §7](06-data-and-knowledge.md#7-the-physical-stores), [ADR-12](13-decisions.md#adr-12-the-operational-store-is-cosmos-db-serverless), [ADR-13](13-decisions.md#adr-13-cost-analytics-is-parquet-and-an-embedded-engine-in-a-job) |
| **H6** | Scale to zero | **Confirmed, with a ledger of exceptions** | private networking forces fixed meters (private endpoints, a Premium registry, search units, the hub's usage pipeline); SRE Agent bills always-on | [12](12-cost-and-finops.md), [options analysis §1.2](research/options-analysis.md) |
| **H7** | Models tiered by role, budgets in the contract | **Confirmed, sharpened** | **EU Data Zone costs +20 %** over Global; Flex (−50 %, Global only) and Batch serve public work; the router's pool drifts under a fixed label; Claude has no EU Data Zone option | [05 §6](05-agents-and-orchestration.md#6-models-and-the-alias-map), [ADR-09](13-decisions.md#adr-09-models-are-aliases-and-the-data-class-chooses-the-deployment-type) |
| **H8** | Safety in layers | **Holds, with gaps** | agent guardrails are preview and *override* the model's; document-attack screening is off by default; agent-level Defender protection moved behind a licence; hosted-agent egress rules are "not intended for production" | [07 §5](07-security-architecture.md#5-defence-against-prompt-injection-in-nine-layers), [ADR-19](13-decisions.md#adr-19-nine-layers-against-injection-with-a-deterministic-gate) |
| **H9** | An identity and a sponsor per agent; authenticated approvals | **Holds** | Entra Agent ID is free and generally available; Conditional Access for agents needs a licence; the primary audit trail must be ours | [07 §3–4](07-security-architecture.md#3-identity), [ADR-06](13-decisions.md#adr-06-an-entra-agent-identity-per-agent-and-nine-contract-groups) |
| **H10** | Teams and e-mail first; voice off | **Confirmed** | Foundry's publishing route is public and conversational; approvals need our own .NET adapter; Voice Live is generally available with Agent Service but voice agents are preview | [ADR-17](13-decisions.md#adr-17-teams-through-our-own-adapter-e-mail-through-graph-voice-off) |
| **H11** | Drift controlled at every layer | **Confirmed, made concrete** | hosted agents are data-plane objects that Bicep cannot guard; the platform changes under unchanged labels; so a drift controller of deterministic detectors | [09](09-safeguards-and-drift-controls.md), [ADR-21](13-decisions.md#adr-21-drift-is-controlled-by-deterministic-detectors-and-a-preview-register) |
| **H12** | Bicep, stacks, GitHub Actions, gated releases | **Confirmed** | stack limits (five excluded principals; resource-group deletion bypass); `azd`'s agent extension is beta; no module for sandboxes or agent versions; Deployment Environments retires | [11](11-delivery-and-operations.md), [ADR-23](13-decisions.md#adr-23-bicep-with-verified-modules-deployment-stacks-and-github-actions) |

## 3. The technology map

What the design uses, by component. **GA** is used by default; **Preview** only behind a switch with the fallback in [09 §5](09-safeguards-and-drift-controls.md#5-the-preview-register-and-the-dependency-register); **Evaluated** is on a spike; **Not used** has its reason in [05 §12](05-agents-and-orchestration.md#12-what-is-deliberately-not-used) or the ADRs.

| Component | GA (default) | Preview (behind a switch) | Evaluated | Not used |
|---|---|---|---|---|
| **Gateway** (GW) | Citadel Governance Hub v1 on API Management v2; backend and access contracts; AI policies (token limits, content safety incl. MCP and A2A); MCP management in API Management | the publish contract; unified model API and aliases | the AI Gateway product; semantic caching | Foundry's portal gateway on the hub |
| **Agent runtime** (AGT) | hosted agents; Entra Agent ID; Foundry RBAC at agent scope | hosted-agent egress rules (audit only); long-running resilience | Routines for a single-agent clock; toolboxes | prompt agents on the critical path; Copilot harness; visual workflows |
| **Framework** (FW) | Agent Framework 1.0: graph workflows, orchestrations, declarative YAML, checkpoints, human-in-the-loop, middleware, skills | Durable Extension; hosting packages | the Harness; CodeAct | A2A inside the system |
| **Models** (MOD) | GPT-6 and 5.6 families; Decisions API; EU Data Zone and Batch; embeddings | Flex (public data only) | the model router with a pinned subset; a second EU family for judges | Astra by default; Claude for estate data; fine-tuning |
| **Knowledge** (KNW) | Foundry IQ's minimal retrieval; AI Search Basic; keyless Search-to-Foundry | AI Search Serverless Developer | Cosmos DB vectors | Foundry Memory |
| **Tools** (TOOL) | MCP servers on Container Apps; Azure MCP Server 3.0 (read-only); Microsoft Learn MCP; the keyless release-feed MCP | — | Functions MCP triggers for tiny tools; the SQL MCP Server | the Resource Manager MCP cost tools unattended |
| **Identity** (ID) | Entra Agent ID; managed identities; workload identity federation; PIM for humans | agent-identity on-behalf-of | Conditional Access for agents (licence) | project shared identity |
| **Security** (SEC) | Policy approved models; MCSB v2; NSP for Foundry; model guardrails; Defender for Resource Manager and Key Vault | agent guardrails; Agent Governance Toolkit; FIDES | Defender for AI Services, CSPM, APIs | Managed HSM |
| **Governance** (GOV) | Azure Policy initiative; Foundry Control Plane inventory | Control Plane compliance panes | Agent 365; Compliance Manager premium templates | Purview for network-isolated flows |
| **Observability** (OBS) | OpenTelemetry into Application Insights; table plans; Workbooks; Azure Monitor dashboards with Grafana | protected GenAI content table; Insights in Foundry | the Observability Agent | Managed Grafana |
| **Evaluation** (EVAL) | Foundry evaluations; PyRIT; ASSERT | AI Red Teaming Agent (cloud); composite evaluators | the agent optimizer (never self-deploys) | prompt flow (retiring) |
| **Data** (DATA) | Cosmos DB serverless; immutable Blob; Data Lake Parquet; Key Vault | — | Azure SQL serverless; ADX Dev/Test; FinOps hubs | PostgreSQL always-on; HorizonDB |
| **Compute** (COMP) | Container Apps Consumption apps and jobs; dynamic sessions | Container Apps Sandboxes | Functions Flex; Durable Task Scheduler | AKS |
| **Network** (NET) | private endpoints; BYO-VNet injection; the landing zone's firewall; Private Link Scope | — | managed VNet | managed-VNet firewall |
| **Channels** (CHAN) | Agents SDK adapter with Azure Bot; Microsoft Graph mail | — | Foundry publishing; Communication Services e-mail | voice, SMS, avatar (modules, off) |
| **Delivery** (OPS, DEV) | Bicep and Verified Modules; Deployment Stacks; GitHub Actions with OIDC; `azd` inner loop | `azd` agent extension | Terraform and AzAPI | Deployment Environments (retiring) |
| **Cost** (COST) | gateway caps; EU Data Zone routing; Batch; FOCUS exports | Flex | FinOps toolkit v15 | budget-triggered stops as a cap |
| **Lab** (LAB) | subscription vending; Deployment Stacks; reaper | Container Apps Sandboxes | — | Lab Services (retiring) |

## 4. Findings that change the design

The twenty that moved a decision, ranked by how much they moved it. Each is evidenced in the digests and the core studies.

| # | Finding | Effect on the design |
|---|---|---|
| 1 | **Foundry visual workflows retire 1 Dec 2026**; hosted agents are generally available (announced 9 Jul 2026) | orchestration is Agent Framework code; agents are hosted agents |
| 2 | **The Citadel hub is a sample**, built on API Management, with a ≈ €320 a month always-on usage pipeline | fork and pin; share or trim; contracts as data |
| 3 | **Prompt agents reach a gateway only through a Chat Completions connection**; the strongest models need Responses for tool calls | hosted agents call the hub from code |
| 4 | **PIM cannot make service principals or managed identities eligible** | a broker creates a scoped role assignment per Move |
| 5 | **EU Data Zone is a price tier** (+20 %); Flex and Batch are cheaper but Global | routing by data class at the hub |
| 6 | **The router's pool changes under an unchanged version label** | aliases, pins, a behavioural fingerprint, an exam on change |
| 7 | **Agent guardrails are preview and override the model's**; document-attack screening is off by default | layered defence with deterministic layers carrying the weight |
| 8 | **Defender for agents moved behind an Agent 365 licence**; Defender for AI Services is token-metered | optional modules with fallbacks; our own detections |
| 9 | **Purview's Foundry integration does not support network isolation** | our own append-only audit ledger |
| 10 | **Network choices are one-way**: BYO-VNet at account creation; managed VNet creates a firewall | a pre-flight check; BYO-VNet chosen |
| 11 | **Sweden Central is the only EU region in every list that matters** | primary region |
| 12 | **Hosted-agent versions are data-plane objects** | a drift controller; immutable versions; manifests |
| 13 | **Azure Deployment Environments and Lab Services retire** (22 Feb and 28 Jun 2027) | the Lab is vending, stacks and a reaper |
| 14 | **Budgets alert on old data and stop nothing**; no spending limit on EA, MCA or pay-as-you-go | the hub is the cap; Lab caps are structural |
| 15 | **SRE Agent bills 4 units an hour always-on** | off by default |
| 16 | **A Teams-published agent needs a public, source-filtered route**; card actions are in the .NET and JavaScript Agents SDKs, not Python | our own adapter; exception X1 |
| 17 | **Private networking forces fixed meters** on services that are otherwise pay-per-use | a ledger of always-on meters in [12](12-cost-and-finops.md) |
| 18 | **Embedded analytics is the only zero-standing-compute option**, and it is open-source rather than Microsoft | a recorded exception to C1 |
| 19 | **Opaque run codes made experiments exact** (100 % against 68 % for parameters in prompts) | the Experimenter passes codes, not parameters |
| 20 | **The release feed and the Learn MCP server are keyless sources** | the change radar is cheap and structured |

## 5. Currency: the landscape is a living document

A snapshot ages in weeks: during this study alone, labels disagreed between pages (hosted agents: preview or generally available; Routines; Voice Live; Astra's data zone) and the research names each clash. The register therefore has an owner and a clock: **the Scholar's change radar watches the release feed for everything in it** ([09 DR-9](09-safeguards-and-drift-controls.md#22-drift-under-us)), a status that expires after thirty days is flagged for re-verification, and a change to an ADOPT or ADOPT-PREVIEW row opens an item on the Agenda. The dates of known retirements are in the dependency register ([09 §5](09-safeguards-and-drift-controls.md#5-the-preview-register-and-the-dependency-register)).

## 6. What this document does not claim

Dispositions are **fit for this design**, not statements about product quality. Statuses are those of the day and the page cited. Where the research could not confirm a fact (a price that renders as a dash, a region list that did not load, a status absent from a page), it says so, and the design either avoids depending on it or turns it into a **spike** ([14 §3](14-next-phases.md#3-spike-register)).
