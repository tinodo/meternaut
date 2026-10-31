# The landscape, seen through the lens of learning

> **Question:** *Does anything in the market, in open source or in research already do what this project imagines — an AI that **learns** how Azure's economics work, studies each estate, tests its beliefs, and improves from outcomes?*
> **Retrieved:** 2026-10-31 for the new checks (marked **Re-read**); 2026-10-30 for the earlier rounds the archived notes carry. **This is a snapshot, and "not found" always means "not found by this search", never "does not exist".**
> Part of the [north star](../01-north-star.md). Source notes from earlier rounds are in [the archive](../_archive/round-3-v3.2.1/research/).

**Labels.** **Confirmed** = the primary page or paper was read directly · **Partly** = a secondary source, or a search summary citing a page not read in full · **Not found** = searched, nothing matching found (the searches are named).

---

## The short version

1. **Almost everything in the field "answers" or "adapts"; very little *learns how billing works*.** What exists is (a) natural-language query layers over existing cost data, (b) statistical anomaly detection tuned to each customer's own history, (c) rule- or algorithm-driven "autonomous" execution, and (d) hand-written recommendation catalogues.
2. **One real precedent for automatic learning exists in Microsoft's own portfolio — but for incidents, not cost.** The Azure SRE Agent extracts learnings from every investigation with no manual training, and loads authored skills when relevant.
3. **Sandbox verification of how a service bills appears to be unbuilt.** The nearest architecture is a Microsoft Research framework that injects faults into sandboxed microservice systems to evaluate agents — for reliability, not spend.
4. **No shared benchmark for cloud-cost reasoning was found.** The few relevant papers each define their own one-off evaluation.
5. **The raw material is unusually rich.** Prices, usage, estate shape, metrics, API specifications, policy aliases, announcements and the documentation's own change history are all machine-readable today.

---

## 1. Who claims to learn?

### Microsoft — first-party

| Asset | Label | What it does for *learning* |
|---|---|---|
| **Azure SRE Agent** — memory and skills | **Confirmed · Re-read** — [Memory](https://learn.microsoft.com/en-us/azure/sre-agent/memory), [Skills](https://learn.microsoft.com/en-us/azure/sre-agent/skills) (both dated 2026-10-28) | Explicit automatic learning: it "doesn't need any manual training"; after each thread goes quiet it captures symptoms, steps that worked, root cause and pitfalls, and keeps "knowledge files" that load into every conversation; skills (`SKILL.md` plus tools) load when relevant. **Domain: incidents and reliability — no evidence it is applied to pricing or SKU knowledge.** The strongest precedent for the *shape* of the learning loop. |
| **Azure Copilot Optimization Agent** | **Confirmed** — [Learn](https://learn.microsoft.com/azure/copilot/optimization-agent) | Preview; VM/VMSS only; explains recommendations and generates scripts. No claim of self-updating cost knowledge or sandbox verification. |
| **Azure Resource Manager MCP server** (cost and pricing tools) | **Confirmed** — [docs](https://github.com/Azure/Azure-Resource-Manager-MCP/blob/main/docs/CostManagementAndPricingTools.md) | Natural-language access to cost, price and forecast operations. A query bridge, not a learner. |
| **Azure Advisor** (cost) | **Confirmed** in the earlier round | Hand-authored rules (for example VM shutdown/right-size with published percentile thresholds); savings at retail rates that ignore existing commitment coverage; recognises a change only after "up to a day"; **no realised-savings check found**. |
| **FinOps toolkit** | **Confirmed** — [AI configuration](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/hubs/configure-ai) | Agents grounded by static instructions on the FOCUS schema and hub queries — prompt-grounding, not learning. Alerts are explicitly rule-based. Open data and MIT licence make it a valuable substrate. |
| **Defender for Cloud governance rules; Sentinel SOC optimization** | **Confirmed** in the earlier round | Owner/due-date assignment (security); data-value recommendations on unused tables (Sentinel, 30-day window). Rules, not learning. |
| **Foundry Agent Service** — the imagined home | **Confirmed · Re-read** — [overview](https://learn.microsoft.com/en-us/azure/foundry/agents/overview) | Prompt agents, hosted agents (bring your own code), the Responses API; **toolboxes** (web and file search, code interpreter, MCP servers) behind one managed endpoint; **observability** (tracing, metrics, evaluations); an **agent optimizer (preview)** that evaluates behaviour and generates better instructions, skills, tool descriptions and model choices; **memory (preview)** with extraction and consolidation into stores; identity and publishing to Teams. A platform for building agents like these — not a cost-learning product. |

### Commercial products

| Product | Label | What it claims (and what it does not) |
|---|---|---|
| **Sedai** | **Confirmed** — [blog](https://sedai.io/blog/2025-in-review-the-year-of-the-autonomous-cloud) | Distinguishes "automation" (static rules) from "autonomy" (continuous adaptation to live telemetry). Learns **workload and scaling behaviour** — not how billing works from documentation; not Azure-specific. |
| **Vantage** (and its MCP server) | **Confirmed** — [docs](https://docs.vantage.sh/vantage_mcp) | The MCP is "a bridge to Vantage's existing APIs". Algorithmic commitment purchasing. No learning claim found. |
| **CloudZero** | **Confirmed** (marketing page) | Allocation engine, streaming telemetry, ML anomaly detection, cost answers for agents and IDEs. No claim of learning new SKUs or pricing from documentation. |
| **Datadog Cloud Cost / Bits AI** | **Partly** | Anomaly detection adapts to each account's history; a conversational "cost skill" over precomputed data. |
| **nOps, Harness, Apptio/Cloudability, Flexera, Finout, Ternary, Archera, Zesty** | **Partly** (secondary sources) | "Autonomous", "agentic" and conversational labels; underlying mechanisms read as rate/commitment algorithms, rule-based automation or statistics over a customer's own telemetry. |
| **Cast AI** | **Not found** — not searched this pass | A gap, not a conclusion. |

> Several vendors use "learns" or "self-updating" for what is statistical anomaly detection on the customer's own time series. This project should be precise in its own claims to avoid sounding the same.

### Open source

| Project | Label | Relevance |
|---|---|---|
| **Infracost — agent skills and MCP server** | **Confirmed · Re-read** — [blog, Oct 2026](https://www.infracost.io/resources/blog/infracost-mcp-server) | Gives any AI assistant a team's FinOps policies, guardrail history and already-investigated waste findings, and drafts fix pull requests. Claims *"that context compounds… the longer Infracost runs, the more they know"* — institutional memory built from **human-authored policies and approvals**; it accumulates decisions, it does not learn billing mechanics itself. Infrastructure-as-code focus, not Azure-only. |
| **Cloud Custodian** (and a small community MCP that turns natural-language requests into policies) | **Partly** | A mature hand-written policy engine; the community MCP is hobby-scale. The "opposite baseline": rules authored by people. |
| **OpenCost** (CNCF) | **Partly** | Real-time Kubernetes cost allocation; a potential data substrate, not a learner. |
| **A populated pricing / SKU knowledge graph** | **Not found** | Searched for open-source cloud pricing or SKU knowledge graphs; only generic graph tooling surfaced. |

---

## 2. Research literature

| Paper | Label | What it shows |
|---|---|---|
| **FinOps Agent — A Use-Case for IT Infrastructure and Cost Optimization** (Vo et al., arXiv:2510.25914, Oct 2025) | **Confirmed · Re-read** | A goal-driven agent simulating the FinOps workflow end to end; benchmarked across models against the authors' own metrics. No shared dataset. |
| **ABACUS: A FinOps Service for Cloud Cost Optimization** (Deochake, arXiv:2501.14753, Dec 2024) | **Confirmed · Re-read** | Budget enforcement from pre-deployment estimates; leaves ML and agents as future work. |
| **Cost Trade-offs of Reasoning and Non-Reasoning LLMs in Text-to-SQL** (Deochake et al., arXiv:2512.22364, Dec 2025) | **Confirmed · Re-read** | LLM choice changes a BigQuery bill independently of correctness — a rare study linking a design choice to cloud cost; scoped to one service. |
| **AIOpsLab: A Holistic Framework to Evaluate AI Agents for Enabling Autonomous Clouds** (Microsoft Research, arXiv:2501.06706) | **Confirmed · Re-read** | Deploys microservice environments, injects faults, generates workload, exports telemetry and evaluates agents. **The closest published analogue to a sandbox that verifies system behaviour** — for incidents, not billing. |

**Not found:** a canonical cloud-pricing or cloud-cost-reasoning benchmark (three searches), and any paper testing an *agent that reads pricing documentation and then verifies its understanding by experiment*. All four papers above are preprints; the literature on this exact question is thin and very recent.

The foundational work on **how agents learn** — skill libraries, reflection, experience extraction, tool-making, automated discovery — is catalogued separately in [inspirations](inspirations.md).

---

## 3. What Azure already exposes, machine-readably

| Surface | Label | What it can teach an AI |
|---|---|---|
| **Retail Prices API** — unauthenticated REST, filterable by service, region and SKU | **Confirmed** — [Learn](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) | The unit-price ground truth, meter by meter, including savings-plan rates (preview). |
| **Cost Management exports and FOCUS** | **Confirmed** | Realised spend, normalised across providers, to reconcile with list prices. |
| **Azure Resource Graph** — KQL across subscriptions, with property change history | **Confirmed** | The shape of an estate and how it changed. |
| **Advisor through Resource Graph** | **Partly** (table name known, page not read in full) | Advisor's catalogue as queryable data. |
| **Azure Monitor metric definitions and metrics** | **Confirmed** | The utilisation signal, per resource type — the "signal of real need" in the Cost Grammar. |
| **`azure-rest-api-specs`** and **`bicep-types-az`** | **Confirmed** | Every resource type, property and API version — and, by diffing, **default changes**. |
| **Azure Policy aliases** | **Confirmed** | A version-stable vocabulary for properties across API churn. |
| **Azure Updates** — filterable feed, RSS, and a Microsoft Release Communications **MCP server** for AI discovery | **Confirmed · Re-read** | The trigger for "a new service just shipped — go and learn it". |
| **Learn documentation source and history** — every page carries its git source URL and commit | **Confirmed · Re-read** | Documentation *changes* are diffs the AI can read and date. |

---

## 4. What was not found

- A vendor, Microsoft team or research group claiming a **"day-zero" service-cost profile**, a **populated cost knowledge graph**, **lab-based billing verification as a practice**, or production agents that **author new cost detectors from scratch** (rather than follow human-written templates) — searched with several phrasings. When pushed, the search tool could only describe how such a thing *would* work.
- Any production system combining **all four** of: reading documentation, verifying in a sandbox, studying the estate, and learning from accept/reject feedback.
- Peer-reviewed publication for any of the four papers above (all are preprints).

---

## 5. What this means for the idea — judgement, not fact

1. **The learning claim is largely open ground — but treat that as a hypothesis.** The searches were not exhaustive and the market moves quickly.
2. **The Azure SRE Agent's memory and skills are a ready-made blueprint** for the *mechanics* — extract learnings after each session, persist them as readable files, load the relevant ones — pointed at billing and estates rather than incidents.
3. **AIOpsLab is the nearest architecture to the Lab:** a sandbox with workload generation, telemetry and an evaluation harness. The step to "deploy it, observe the bill, check the mental model" looks genuinely new.
4. **Infracost's "context compounds" is the closest real analogue to the Lesson Book** — but it accumulates human decisions rather than learning the underlying mechanics.
5. **A shared benchmark for cloud-cost reasoning would be a first** — which is why the [exam bank](exam-bank-cost-traps.md) is planned to open.
6. **Be exact with words.** "Learns" is overloaded marketing language; this project's claim is specific — *predictions scored against outcomes, claims with receipts, an exam it cannot see*.

---

## 6. Gaps in this snapshot (carry forward)

Cast AI was not searched; most commercial vendors were checked through secondary sources only; Advisor-through-Resource-Graph and diagnostic-setting log categories were not read in full; GitHub licence, star and commit metadata for the small open-source projects was not exposed by the fetch tool. The earlier round's [first-party teardown](../_archive/round-3-v3.2.1/research/06-first-party-teardown.md) and [third-party landscape](../_archive/round-3-v3.2.1/research/02-third-party-and-oss-landscape.md) hold the wider (owner-routing-oriented) survey; **re-check this page quarterly**, since the field is moving fast.
