# The landscape, seen through the lens of learning

> **Question:** *Does anything in the market, in open source or in research do what this project imagines — an AI that **learns** how Azure's economics work, studies each estate, checks its beliefs against the bills people already pay, and improves from outcomes?*
> **Retrieved:** 2026-10-31 for pages marked **Re-read**; 2026-10-30 for the rest. **This is a snapshot: "not found" always means "not found by this search", never "does not exist".**
> Part of the [north star](../01-north-star.md).

**Labels.** **Confirmed** = the primary page or paper was read directly · **Partly** = a secondary source, or a search summary citing a page not read in full · **Not found** = searched, nothing matching found.

---

## The short version

1. **Almost everything in the field "answers" or "adapts"; very little *learns how billing works*.** What exists is (a) natural-language query layers over existing cost data, (b) statistical anomaly detection tuned to each customer's own history, (c) rule- or algorithm-driven "autonomous" execution, and (d) hand-written recommendation catalogues. The one real precedent for automatic learning in Microsoft's portfolio is for incidents, not cost: the Azure SRE Agent extracts learnings from every investigation with no manual training and loads authored skills when relevant.
2. **No shared benchmark for cloud-cost reasoning was found.** The few relevant papers each define their own evaluation; the nearest published harness for cloud agents scores incident response, not spend.
3. **The raw material is unusually rich.** Prices, usage, estate shape, metrics, API specifications, policy aliases, announcements, documentation change history and the bills themselves are machine-readable today. Each resize or forgotten resource has already changed a bill: an observational case, not an experiment; rates, workload and other changes can confound attribution.
4. **Agreements and access are often assumed away** — see [Agreements and access](#agreements-and-access).

---

## Territory map — what Azure already ships for cost, and what this idea adds

| Native tool | What it does today | What it leaves open — and what this idea adds |
|---|---|---|
| **Cost Management** — analysis, budgets, anomaly alerts, exports | shows what was spent; alerts on budgets and anomalies (anomaly alerts by email; budget alerts by email or, at subscription and resource-group scope, an action group); data arrives hours to days late | *why* and *what for*; each alert routed to the right owner with reasoning, as a question or a decision |
| **Azure Advisor** | hand-authored cost recommendations; VM savings at retail rates, ignoring commitments; a change is recognised after up to a day | each card checked against the estate and the commitments; a measured saving at the end |
| **Reservations, savings plans, Hybrid Benefit, dev/test pricing** | rate levers, with their own rules and exchange limits | finding unused entitlements and sequencing them with right-sizing; a commitment-purchase process needing two human approvals |
| **FinOps toolkit** | open reports, hubs, workbooks, Logic Apps-based FinOps alerts, an agent plugin (its bundled Azure MCP server is read-only) | a substrate to read from, not a system that learns |
| **Azure Copilot Optimization Agent and MCP servers** | chat and scripts over existing recommendations and cost/price APIs (the agent is VM/VMSS only, in preview) | investigation, learning from the bill, and acting with people |
| **Azure SRE Agent** (memory and skills) | learns from every conversation, keeps readable knowledge files | the same *shape* of learning, pointed at cost |

---

## Agreements and access

Several tools in this survey assume one agreement and full billing access: Advisor prices its VM savings at retail rates, the Retail Prices API returns list prices only, and the FOCUS export is not available at every scope or for every agreement type (§3). Azure estates sit under an Enterprise Agreement (EA), a Microsoft Customer Agreement (MCA) bought directly, an agreement sold through a partner (CSP), pay-as-you-go, or several at once. This project treats the agreement type and the level of access as part of every recommendation: each number says whether it rests on contracted, billed or list prices, a purchase goes to whoever can make it, and the system says what more access would add ([north star §5](../01-north-star.md#5-every-agreement-every-level-of-access)).

---

## 1. Who claims to learn?

### Microsoft — first-party

| Asset | Label | What it does for *learning* |
|---|---|---|
| **Azure SRE Agent** — memory and skills | **Confirmed · Re-read** — [Memory](https://learn.microsoft.com/en-us/azure/sre-agent/memory), [Skills](https://learn.microsoft.com/en-us/azure/sre-agent/skills) (both dated 2026-10-28) | Explicit automatic learning: it "doesn't need any manual training"; after each thread goes quiet it captures symptoms, steps that worked, root cause and pitfalls, and keeps knowledge files — an overview file loads into every conversation; skills (`SKILL.md` plus tools) load when relevant. **Domain: incidents and reliability — no evidence it is applied to pricing or SKU knowledge.** |
| **Azure Copilot Optimization Agent** | **Confirmed** — [Learn](https://learn.microsoft.com/azure/copilot/optimization-agent) | Preview; VM/VMSS only; explains recommendations and generates scripts. No claim of self-updating cost knowledge. |
| **Azure Resource Manager MCP server** (cost and pricing tools) | **Confirmed** — [docs](https://github.com/Azure/Azure-Resource-Manager-MCP/blob/main/docs/CostManagementAndPricingTools.md) | Natural-language access to cost, price and forecast operations. A query bridge (one budget-creation tool aside); it does not learn. |
| **Azure Advisor** (cost) | **Confirmed · Re-read** ([cost recommendations](https://learn.microsoft.com/en-us/azure/advisor/advisor-cost-recommendations)) | Hand-authored rules (for example VM shutdown/right-size with published percentile thresholds). For those VM recommendations, savings are at retail rates and do **not** account for existing reservations or savings plans; Advisor can take up to a day to recognise a change; **no realised-savings check found**. |
| **FinOps toolkit** | **Confirmed** — [AI configuration](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/hubs/configure-ai) | Agents grounded by static instructions on the FOCUS schema and hub queries — prompt-grounding, not learning. FinOps alerts are Logic Apps that scan for idle resources ([alerts](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/alerts/finops-alerts-overview)). Open data and MIT licence make it a good substrate. |
| **Defender for Cloud governance rules; Sentinel SOC optimization** | **Confirmed** | Owner and due-date assignment for security recommendations; data-value recommendations for a security analytics product. Rules, not learning. |
| **Foundry Agent Service** — the intended home | **Confirmed · Re-read** — [overview](https://learn.microsoft.com/en-us/azure/foundry/agents/overview) | Prompt agents, hosted agents (bring your own code), the Responses API; **toolboxes** (web and file search, code interpreter, MCP servers) behind one managed endpoint; **observability** (tracing, metrics, evaluations); an **agent optimizer (preview)** that evaluates behaviour and generates better instructions, skills, tool descriptions and model choices; **memory (preview)** with extraction and consolidation into stores; identity and publishing to Teams. A platform for building agents like these — not a cost-learning product. |

### Commercial products

| Product | Label | What it claims (and what it does not) |
|---|---|---|
| **Sedai** | **Confirmed** — [vendor blog](https://sedai.io/blog/2025-in-review-the-year-of-the-autonomous-cloud) | Claims "autonomy" ("adapt continuously to what's happening in production") versus "automation" (static rules); how it adapts was not verified. No claim of learning how billing works from documentation; not Azure-specific. |
| **Vantage** (and its MCP server) | **Confirmed** — [docs](https://docs.vantage.sh/vantage_mcp) | The MCP is "a bridge to Vantage's existing APIs". Algorithmic commitment purchasing. No learning claim found. |
| **Infracost** (hosted MCP server) | **Confirmed · Re-read** — [blog, Oct 2026](https://www.infracost.io/resources/blog/infracost-mcp-server) | A hosted Infracost Cloud service (licence not verified) giving AI assistants a team's FinOps policies, guardrail history and investigated waste findings, and drafting fix pull requests. Claims *"that context compounds… the longer Infracost runs, the more they know"* — institutional memory built from **human-authored policies and approvals**, not learned billing mechanics — the closest real analogue to the Lesson Book. Infrastructure-as-code focus, not Azure-only. Separately, its [agent skills](https://github.com/infracost/agent-skills) are open source (Apache-2.0, checked 2026-11-01). |
| **CloudZero** | **Confirmed** (marketing page) | Allocation engine, streaming telemetry, ML anomaly detection, cost answers for agents and IDEs. No claim of learning new SKUs or pricing from documentation. |
| **Datadog Cloud Cost / Bits AI** | **Partly** | Anomaly detection adapts to each account's history; a conversational "cost skill" over precomputed data. |
| **nOps, Harness, Apptio/Cloudability, Flexera, Finout, Ternary, Archera, Zesty** | **Partly** (secondary sources) | "Autonomous", "agentic" and conversational labels; underlying mechanisms read as rate/commitment algorithms, rule-based automation or statistics over a customer's own telemetry. |

### Open source

| Project | Label | Relevance |
|---|---|---|
| **Cloud Custodian** (and a small community MCP that turns natural-language requests into policies) | **Partly** | A mature hand-written policy engine; the community MCP is hobby-scale. The "opposite baseline": rules authored by people. |
| **OpenCost** (CNCF) | **Partly** | Real-time Kubernetes cost allocation; a potential data substrate that does not learn. |
| **A populated pricing / SKU knowledge graph** | **Not found** | Searched for open-source cloud pricing or SKU knowledge graphs; only generic graph tooling surfaced. |

---

## 2. Research literature

| Paper | Label | What it shows |
|---|---|---|
| **FinOps Agent — A Use-Case for IT Infrastructure and Cost Optimization** (Vo et al., arXiv:2510.25914, Oct 2025) | **Confirmed · Re-read** | A goal-driven agent simulating the FinOps workflow end to end; benchmarked across models against the authors' own metrics. No shared dataset. |
| **ABACUS: A FinOps Service for Cloud Cost Optimization** (Deochake, arXiv:2501.14753, Dec 2024) | **Confirmed · Re-read** | Budget enforcement from pre-deployment cost estimates; proposes future research directions. |
| **Cost Trade-offs of Reasoning and Non-Reasoning LLMs in Text-to-SQL** (Deochake et al., arXiv:2512.22364, Dec 2025) | **Confirmed · Re-read** | LLM choice changes the BigQuery on-demand cost estimated from bytes processed, at similar correctness — a rare study linking a design choice to cloud cost; one service. |
| **AIOpsLab: A Holistic Framework to Evaluate AI Agents for Enabling Autonomous Clouds** (Chen et al., arXiv:2501.06706, Jan 2025) | **Confirmed · Re-read** | Deploys microservice environments, injects faults, generates workload, exports telemetry and evaluates agents. **The closest published analogue to a reproducible, scored evaluation of cloud agents** — for incidents, not billing. |

All four are preprints; the literature on this exact question is thin and recent.

The foundational work on **how agents learn** — skill libraries, reflection, experience extraction, tool-making, automated discovery — is catalogued separately in [inspirations](inspirations.md).

---

## 3. What Azure already exposes, machine-readably

| Surface | Label | What it can teach an AI |
|---|---|---|
| **Retail Prices API** — unauthenticated REST, filterable by service, region and SKU | **Confirmed** — [Learn](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) | The **list-price** ground truth (USD base), meter by meter, including savings-plan rates (preview) — never the customer's own price. |
| **Cost Management exports and FOCUS** | **Confirmed** | Realised spend, to reconcile with list prices; FOCUS is one dataset and is not available at every scope or for every agreement type. |
| **Azure Resource Graph** — KQL across subscriptions, with property change history | **Confirmed** | The shape of an estate and how it changed — change data is queryable for only 14 days, so longer history must be collected. |
| **Advisor through Resource Graph** | **Confirmed** | Advisor's catalogue as queryable data (the `advisorresources` table). |
| **Azure Monitor metric definitions and metrics** | **Confirmed** | The utilisation signal, per resource type — the "signal of real need" in the Cost Grammar. |
| **`azure-rest-api-specs`** and **`bicep-types-az`** | **Confirmed** | Every resource type, property and API version — and, by diffing, **default changes**. |
| **Azure Policy aliases** | **Confirmed** | A version-stable vocabulary for properties across API churn. |
| **Azure Updates** — filterable feed, RSS, and a Microsoft Release Communications **MCP server** for AI discovery | **Confirmed · Re-read** | The trigger for "a new service just shipped — go and learn it". |
| **Learn documentation source and history** — pages carry git source metadata and a commit (some point at private repositories; the matching file in the public MicrosoftDocs repository holds the readable history) | **Confirmed · Re-read** | Documentation *changes* are diffs the AI can read and date. |

---

## 4. What was not found

- A canonical cloud-pricing or cloud-cost-reasoning benchmark (three searches).
- A vendor, Microsoft team or research group claiming a **"day-zero" service-cost profile**, a **populated cost knowledge graph**, or production agents that **author new cost detectors from scratch** (rather than follow human-written templates) — searched with several phrasings.

---

## 5. What this means for the idea — judgement, not fact

1. **The learning claim is largely open ground — but treat that as a hypothesis.**
2. **The Azure SRE Agent's memory and skills are a ready-made blueprint** for the *mechanics* — extract learnings after each session, persist them as readable files, load the relevant ones — pointed at billing and estates rather than incidents.
3. **AIOpsLab is the nearest architecture to the evaluation:** scenarios, workload, telemetry and a scoring harness. The same shape for cost — generated test estates with planted waste and look-alike decoys, scored against known answers — was not found in these searches.
4. **No shared benchmark was identified in this search**, so the [cost-trap bank](cost-trap-bank.md) and the recipes that plant its traps in generated estates are planned to open as a public benchmark.
5. **Be exact with words.** "Learns" is overloaded marketing language: several vendors use it, or "self-updating", for statistical anomaly detection on a customer's own time series. This project's claim is specific — *predictions scored against outcomes, claims with receipts, sealed test cases it cannot see*.

---

## 6. Gaps in this snapshot

Cast AI was not searched; most commercial vendors were checked through secondary sources only; licensing and maintenance of the small open-source projects were not checked. Two searches on 2026-11-01 for a product that predicts what a meter should do and then scores the bill against it found only vendor marketing summaries; the question stays open. A wider survey of commercial products is in the [archive](../_archive/round-3-v3.2.1/research/). **Re-check this page quarterly**: the field moves fast.
