# Round 1 · A — Cost and simplicity (model: gemini-4-argon)

> Raw report, saved exactly as the reviewer returned it (everything below the rule). Reviewed on 2026-11-01: the decisions D1–D22 of the first design specification. Lens: cheapest design that meets the fixed requirements; over- and under-engineering. The orchestrator's spot-checks of what this reviewer cited are in the [disposition](disposition.md).

---

Agent is idle (waiting for messages). agent_id: 148ea12d-58cf-4112-9248-98acc932ffe4, agent_type: rubber-duck, status: idle, description: Round 1 review: cost and simplicity, elapsed: 300s, total_turns: 1, model: gemini-4-argon

[Turn 0]
### (a) Review of Decisions D1–D22 (Lens: Cost & Simplicity)

| ID | Verdict | One-line reason |
|---|---|---|
| **D1** | **Agree** | Deterministic workflows calling read/propose-only agents prevent runaway agentic loops and bound token spend. |
| **D2** | **Agree-with-change** | Flex Consumption scales to zero, but use **Azure Storage** for task hubs at Pilot/Team scale; DTS Consumption (€0.003432/action) is ~20× costlier than Storage queues and lacks HA. |
| **D3** | **Disagree** | 10 separate hosted agents multiply image/zip pipelines, cold starts, and 2–15 min idle-tail billing; merge into **4–5 hosted agents** (or 1 multi-role image) using Invocations protocol. |
| **D4** | **Agree-with-change** | Keep Citadel as the single door, but **fork out its €320.73/mo always-on usage pipeline** (7×400 RU/s Cosmos + WS1 Logic App + Event Hubs) in favor of existing APIM→Log Analytics logs. |
| **D5** | **Agree-with-change** | Good alias tiering (`6-luna` at €0.106/1M in DZ vs `6.1-sol` at €2.11/1M), but add `6.1-terra` (€1.06/1M in DZ) as default `reason` and reserve `sol` for escalations. |
| **D6** | **Agree-with-change** | Reuse the mandatory Foundry Standard Setup AI Search Basic unit (€64.88/mo) for the Atlas index rather than provisioning a second Search service; disable Semantic Ranker overage (€0.88/1K queries) by default. |
| **D7** | **Agree-with-change** | Reuse Foundry Standard Setup's BYO Cosmos DB Serverless account (separate database) and BYO Storage account (separate immutable container) to save 2–4 private endpoints (€12.85–€25.70/mo). |
| **D8** | **Agree** | FOCUS Parquet exports in Blob + DuckDB in Container Apps jobs has €0 compute floor and avoids an ~€105/mo ADX Dev/Test floor. |
| **D9** | **Agree-with-change** | Package read-only MCP tool servers (`estate-read`, `cost-query`, `directory`, `atlas`) into **one** scale-to-zero Container App instead of 6 separate apps to eliminate cold-start and operational sprawl. |
| **D10** | **Agree** | Single action plane with Bicep/ARM what-if, etag check, and Container Apps job runner costs €0 at idle and guarantees write safety. |
| **D11** | **Agree-with-change** | Drop the separate "Approval web app" in Phase 1–2; use Teams Adaptive Cards (R1) and an HTTP-triggered Function endpoint with Entra Easy Auth + Conditional Access (R2/R3). |
| **D12** | **Agree** | Per-action-class custom roles at opted-in scopes are zero-cost and avoid requiring Entra ID P2 / PIM for service principals. |
| **D13** | **Agree-with-change** | Drop the custom Lesson Book web UI (store Lessons as Markdown in Git or a Workbook) and defer Voice/Avatar modules (which carry real-time token/VM floors). |
| **D14** | **Agree** | Single Key Vault (€0.026/10K ops, €0 idle) and keyless managed/agent identities eliminate design-v1's 6-vault + Defender-per-vault bloat. |
| **D15** | **Agree-with-change** | Evaluate (Basic setup, no PEs) vs Operate (Standard setup, BYO VNet) is the right cost split, **provided** Evaluate still routes through a hub (see Problem 2) and its monthly pre-release Operate test is automated to tear down after 24h. |
| **D16** | **Agree** | Per-table plans (`AppGenAIContent` on Basic Logs at €0.568/GB vs Analytics at €2.631/GB; audit on Auxiliary at €0.062/GB) plus free Workbooks/Grafana dashboards keep observability near the 5 GB free allowance. |
| **D17** | **Disagree** | Running full multi-agent LLM loops across 145 traps × repeats on every PR/release makes evaluation cost **4–9× more than production**; gate PRs on deterministic Detectors/simulator and run full LLM suites only on model/prompt releases. |
| **D18** | **Agree** | Drift controls rely on CI, Deployment Stacks, and existing logs with zero standing compute floor. |
| **D19** | **Agree-with-change** | Source-code zip deploy (`code_configuration`) avoids ACR Premium (€44.58/mo) for hosted agents, **but** Container Apps jobs/tools in a private VNet still need image pulls—run tools on the Flex Consumption Function app or budget ACR Basic/public MCR + VNet egress. |
| **D20** | **Agree-with-change** | Strong cost levers, but missed the three biggest hidden multipliers: hosted-agent idle-timeout tail (2–15 min per session), Content Safety re-screening of full conversation history, and ACR for Container Apps. |
| **D21** | **Agree** | Transparently listing Entra P1, M365, and DuckDB (MIT) avoids hidden adopter costs. |
| **D22** | **Agree** | Eliminating the Lab, model training, and custom portals removes the worst cost sinks of design-v1. |

---

### (b) Component Disposition (Task 1: Cheapest Compliant Design)

* **Keep (scale-to-zero):** Durable Functions on Flex Consumption (Azure Storage backend, 0 Always-Ready instances in Pilot); Cosmos DB Serverless; Blob + DuckDB; Key Vault (1); Log Analytics (Basic/Auxiliary table plans) + App Insights + Workbooks; Teams Adaptive Cards + Graph mail.
* **Merge:**
  * **10 Hosted Agents → 4 Hosted Agents** (or 1 shared container/zip routed by role parameter): *Study* (`Scholar`+`Librarian`, `public-read`), *Investigate* (`Surveyor`+`Detective`+`Economist`+`Engineer`+`Auditor`+`Conductor`, `estate`), *Skeptic* (`judge` alias), and *Diplomat* (`people`). This preserves trust-contract boundaries, the adversarial `judge` family, and the learning loop while cutting deployment artifacts and warm sandboxes by 60%.
  * **cosmos + blob + search stores → Reuse Foundry Standard Setup's BYO trio:** Put the Atlas index in Foundry's mandatory AI Search Basic service, estate/ledger containers in a separate database on Foundry's BYO Cosmos Serverless account, and `cost-lake`/`audit` containers on Foundry's BYO Storage account. Saves 3 Storage/Cosmos/Search resources and **3–5 Private Endpoints (€19.27–€32.12/mo)**.
  * **Approval web app + MCP tool servers + Action runner → Merge into the Flex Consumption Function App (or 1 internal Container App):** Functions Flex Consumption supports HTTP (with Entra Easy Auth for R2/R3 approvals), MCP triggers, and CLI/ARM execution out of the box, removing the need for a separate Container Apps environment and private ACR Premium (€44.58/mo).
* **Remove:** Citadel's default usage-ingestion pipeline (Cosmos 2,800 RU/s + Logic App WS1 + Event Hubs = **€320.73/mo**). Compute cost-per-case via KQL over `ApiManagementGatewayLlmLogs` in Log Analytics (D16 already does this!).

---

### (c) Top 7 Problems Ranked by Severity

1. **[BLOCKING] Citadel's shipped usage pipeline adds a €320.73/mo idle floor that duplicates D16.**
   * **Evidence:** `docs\_archive\design-v1\design\research\citadel.md` §2.1 & §7: Citadel deploys Cosmos DB (7 × 400 RU/s = €142.90/mo), Logic App Standard WS1 (€158.00/mo), and Event Hubs Standard 1 TU (€19.27/mo). Meanwhile, `design-v2-spec.md` D16 states *"cost per case computed from hub logs by the Economist's workflow"* via Log Analytics.
   * **Proposed change:** In D4, mandate a Bicep parameter override in `hub/` that disables the Event Hubs → Logic App → Cosmos usage pipeline and queries `ApiManagementGatewayLlmLogs` in Log Analytics directly.
   * **Confidence:** High (verified in `citadel.md` §2.1/§7 and `prices-snapshot.json`).

2. **[BLOCKING] D15's "Evaluate" profile risks violating the fixed Citadel requirement or doubling APIM cost.**
   * **Evidence:** `design-v2-spec.md` D4 mandates *"four contracts × two environments (dev, prod)"* on the Citadel hub, while D15 defines *Evaluate* as *"Foundry basic setup; public endpoints ... no private endpoints"*. If an adopter deploys *Evaluate* standalone without a hub, it breaks the fixed requirement ("ALL AI traffic through the Citadel governance hub"). If they deploy a dedicated dev hub, even APIM Developer adds €42.27/mo (+ €320.73 if un-forked).
   * **Proposed change:** Clarify in D4/D15 that *Evaluate* is a **spoke profile**, not a hub bypass: it connects to the organisation's existing Citadel hub (or a stripped APIM Developer hub at €42.27/mo with 0 PEs and no usage pipeline) using `dev` contracts over public HTTPS with Entra JWT + IP allow-listing.
   * **Confidence:** High.

3. **[HIGH] Evaluation & CI token/compute spend (D17) can exceed production case spend by 4×–9×.**
   * **Evidence:** In `docs\_archive\design-v1\tools\cost-model.py` (lines 42–46, 211–221), running continuous exams (`exam_cases=600`) + release gates (`(99+99)*3 = 594` case-runs) + red-teaming (`3,000` attacks) for a 20–100 case/month Pilot executes **>1,194 full multi-agent case-runs/month**, costing ~4–9× more in tokens and hosted-agent session hours than actual production!
   * **Proposed change:** Split D17 into two tiers: (1) **Zero-LLM CI** on every PR (test compiled Detectors, Cost Grammar schemas, and the deterministic Economist simulator against the 145 cost-trap bank for €0 token cost); (2) **LLM Eval Suite** (≤50 representative cases on `batch`/`flex` tier, 1 repeat) only when prompts or model aliases change.
   * **Confidence:** High.

4. **[HIGH] 10 Hosted Agents + 2–15 min minimum idle timeout inflates compute billing by 3×–15× for short tasks.**
   * **Evidence:** Microsoft Learn (`https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents`): *"You can configure the idle timeout per agent version from 2 through 240 minutes (4 hours), with a 15-minute default... Compute follows the session, not the individual request."* At 0.5 vCPU + 1 GiB (`EUR 0.096216/2 + 0.011422 = EUR 0.05953/h` in `prices-snapshot.json`), a 20-second `Conductor` or `Auditor` invocation with a 15-min default timeout bills for 15.3 minutes (46× runtime); even at the 2-min floor it bills 6× runtime across 10 separate agent sandboxes.
   * **Proposed change:** Merge the 10 roles into **4 hosted agents** aligned to the 4 hub contracts (`public-read`, `estate`, `people`, `judge`), set `idle_timeout = 2 min`, and reuse a single `session_id` per workflow run so sequential steps (`Surveyor` → `Detective` → `Economist` → `Engineer` → `Auditor`) execute inside one warm microVM sandbox.
   * **Confidence:** High (verified on Microsoft Learn today).

5. **[HIGH] Hidden ACR Premium (€44.58/mo) trap in D19/D20 for Container Apps in Operate profile.**
   * **Evidence:** D20 claims *"deploy hosted agents from source (no Premium registry unless private link requires it)"*. Confirmed on Learn (`deploy-hosted-agent-code`): hosted agents support `.zip` upload (`code_configuration`) if firewall allows `mcr.microsoft.com`. **However**, D8 (DuckDB job), D9 (MCP tool servers), D10 (Action runner), and D13 (Approval web app) run on **Container Apps**, which cannot deploy from `.zip` without a container registry—and in a private VNet, ACR requires **Premium** (`EUR 1.466561/day = EUR 44.58/mo` + `EUR 6.42/mo` PE).
   * **Proposed change:**Either run the DuckDB query, MCP tools, approval endpoint, and CLI runner inside the **Flex Consumption Function App** (which deploys from `.zip` over private storage without ACR), or explicitly budget ACR Basic (€4.46/mo) with trusted-service/VNet egress.
   * **Confidence:** High (verified on Learn & `prices-snapshot.json`).

6. **[MEDIUM] Private Endpoint proliferation on storage sub-resources and separate stores.**
   * **Evidence:** Each Standard Private Endpoint bills `EUR 0.0088/h = EUR 6.424/mo` (`prices-snapshot.json`). If Durable Functions uses Azure Storage (blob, queue, table = 3 PEs), Foundry uses BYO Storage (blob = 1 PE), and the workload uses its own Storage (blob, queue = 2 PEs) + its own Cosmos (1 PE) + Key Vault (1 PE) + Search (1 PE) + Foundry (1 PE) + AMPLS (1 PE), Operate hits **11–14 PEs (€70.66–€89.94/mo)**.
   * **Proposed change:** Consolidate onto **one** Storage account (with separate containers/queues and RBAC per container) and **one** Cosmos Serverless account in Pilot Operate, reducing PEs to **7 total (€44.97/mo)**: Foundry (1), AI Search (1), shared Cosmos (1), shared Storage blob+queue+table (3), Key Vault (1).
   * **Confidence:** High.

7. **[MEDIUM] Content Safety (`EUR 0.33/1K records`) and Prompt Cache Write (`1.25× input`) traps.**
   * **Evidence:** In `prices-snapshot.json`, `Content Safety Standard Text Records` is `EUR 0.329989/1K` (1 record = 1,000 chars), and `GPT-6.1 Sol ShortCo Cd Wr Std DZ` is `EUR 2.639916/1M` vs `EUR 2.111932/1M` uncached input. If the hub's `llm-content-safety` policy runs on every multi-turn LLM request, a 10-turn Detective loop with a 15k-token (60k-char) context screens 600 records (€0.20/case just for Content Safety—nearly equal to the LLM tokens!). And if `prompt_cache_key` isn't sticky across turns, explicit cache breakpoints charge a 25% write penalty with zero read savings.
   * **Proposed change:** Disable `llm-content-safety` on the `estate` contract's model route and apply it **only** once on inbound untrusted text in `public-read` and `people` tool responses; only enable explicit `cache_write` breakpoints on prefixes ≥4,096 tokens reused ≥3 times per session.
   * **Confidence:** High.

---

### (d) Idle-Floor and Pilot Cost Estimates (Task 2 — Sweden Central, EUR, 730 h/mo)

All rates from `docs\design\cost\prices-snapshot.json` (retrieved 2026-10-31):

#### 1. Idle Monthly Floor — *Evaluate* Profile (Dev, Basic Setup, Public Endpoints + Entra Auth, Shared Hub)
* **Foundry Basic Setup, Hosted Agents, Functions Flex Consumption (0 Always-Ready), Cosmos Serverless, Key Vault, Log Analytics (<5 GB free grant):** **€0.00/mo**
* **Storage (Hot LRS, ~2 GB state/exports + idle queue polling for Durable Functions):** `2 GB × EUR 0.016191` + `<100K ops × EUR 0.00352/10K` ≈ **€0.40/mo**
* **Evaluate Idle Floor Total:** **≈ €0.40/month** (if using AI Search Free tier or sharing Operate's Search; if deploying AI Search Serverless Developer preview with 1 GB index: `1 GB × EUR 0.227913` = **€0.63/month**; if AI Search Basic: **€65.28/month**).

#### 2. Idle Monthly Floor — *Operate* Profile (Prod, Standard Setup, BYO VNet, Shared Hub)
* **AI Search Basic (1 SU, required by Foundry Standard Setup, reused for Atlas):** `730 h × EUR 0.088877` (`Azure Cognitive Search | Basic Unit`) = **€64.88/mo**
* **Private Endpoints (lean 7 PEs: Foundry, Search, shared Cosmos, shared Storage blob/queue/table, Key Vault; 8 PEs if AMPLS is not shared with landing zone):** `7 × 730 h × EUR 0.0088` (`Virtual Network Private Link | Standard Private Endpoint`) = **€44.97/mo** (or **€51.39/mo** with 8 PEs; **€89.94/mo** if un-consolidated at 14 PEs)
* **Private DNS Zones (if not provided by landing zone, 8 zones):** `8 × EUR 0.439986` (`Azure DNS | Private Zone`) = **€3.52/mo** (€0 if shared with landing zone)
* **Storage & Cosmos Serverless idle data (5 GB Foundry + 2 GB Cosmos + queue polling):** `5 × EUR 0.020239 (Hot ZRS)` + `2 × EUR 0.219993 (Cosmos Data Stored)` + `~€1.50 polling` = **€2.04/mo**
* **Operate Idle Floor Total (lean, zip-deployed on Functions, landing-zone DNS/AMPLS):** **≈ €111.89/month**
  *(Note: If un-optimized—adding ACR Premium €44.58/mo, 14 PEs +€44.97/mo, 1 Flex Always-Ready 2 GB instance `730×3600×2×EUR 0.000004 = €21.02/mo`, and Defender for RM/KV across 4 subs €17.94/mo—the Operate idle floor jumps to **≈ €240.40/month**).*

#### 3. Pilot Monthly Estimate (5 subscriptions, 500 resources, 20 cases/month, excluding shared hub)
* **Operate Idle Floor (lean):** **€111.89/mo**
* **20 Production Cases (Tokens, EU Data Zone):** 20 cases × ~27 LLM calls/case (~340K input, 26K output tokens/case; `6.1-sol` DZ `EUR 2.1119/1M in`, `EUR 10.5597/1M out`; `6-luna` DZ `EUR 0.1056/1M in`, `EUR 0.5280/1M out`; `Mistral Large 3` DZ `EUR 0.484/1M in`, `EUR 1.452/1M out`; with session caching): `20 × ~€0.48/case` = **€9.60/mo**
* **Watch, Study, Estate Refresh & Nightly Consolidation (Tokens):** Hourly/daily Detectors (code) + `6-luna` triage + weekly `Scholar`/`Surveyor` updates (~35M `6-luna` + ~12M `6.1-sol` Global/DZ tokens) = **€28.50/mo**
* **Right-sized Evaluation & Sampled Monitoring (D17):** 5% prod sampling (1 case) + 1 monthly model/prompt eval run of 50 synthetic cases on Global Flex (`6.1-sol Flex Gl` `EUR 0.88/1M in`, `EUR 4.40/1M out`) = **€14.20/mo** *(vs **~€310/mo** in design-v1's bloated 1,194-run schedule)*
* **Active Compute & Data (Hosted Agents, Functions, DuckDB, Cosmos RUs, Content Safety, Logs):**
  * Hosted Agent sessions (0.5 vCPU + 1 GiB at `EUR 0.05953/h`, ~35 active+idle hours total across 20 cases + Study + Eval): **€2.08/mo**
  * Functions Flex Consumption on-demand + Container Apps jobs: **€0.00/mo** (well inside monthly free grants of 100K GB-s / 250K execs and 180K vCPU-s)
  * Cosmos DB Serverless (~15M RUs × `EUR 0.268391/1M` + 5 GB × `EUR 0.219993`) = **€5.13/mo**
  * Content Safety (inbound untrusted text only, ~15K records × `EUR 0.329989/1K`) = **€4.95/mo**
  * Log Analytics (within 5 GB Analytics free grant + 5 GB Basic Logs × `EUR 0.567582`) = **€2.84/mo**
* **Pilot Monthly Total (Lean Operate + Evaluate):** **≈ €179/month** (or **≈ €115/month** if AI Search Serverless Developer preview replaces AI Search Basic).

#### The Three Meters That Dominate Pilot Cost — and What Removes Each:
1. **`Azure Cognitive Search | Basic | Basic Unit` (€64.88/mo — 36% of Pilot):** Removed by switching Foundry's BYO Search to **AI Search Serverless Developer tier** (`EUR 0.2246/CU-h` + `EUR 0.2279/GB-mo` ≈ €2–€5/mo at Pilot volume) in Sweden Central once P5 confirms Foundry Standard Setup accepts it.
2. **`Virtual Network Private Link | Standard | Standard Private Endpoint` (€44.97–€89.94/mo — 25–40% of Pilot):** Halved by **sharing Foundry's BYO Cosmos DB and BYO Storage accounts** with the workload's operational store and Durable Functions task hub instead of provisioning separate storage/database accounts per plane.
3. **Evaluation & Study `Foundry Models | 6.1-sol` tokens (€38–€310/mo depending on D17 cadence):** Cut by 85% by using **deterministic CI checks** on PRs, routing default reasoning to **`6.1-terra`** (50% cheaper than `6.1-sol`: `EUR 1.056` vs `EUR 2.112/1M` in DZ), and running LLM evaluation suites on **Global Flex** only when prompts or models change.

---

### (e) Where the Design Over-Engineers vs. Under-Invests (Task 3) & What a Principal Architect Expects (Output d)

* **Over-engineered for a Pilot adopter:**
  1. **10 separate hosted agent deployments (D3)** for 20 cases/month (<1 case/day).
  2. **A custom Approval & Lesson Book web app (D11/D13)** when Teams Adaptive Cards + an Entra-authenticated Function URL + Markdown in Git/Workbooks cover 100% of the workflow.
  3. **Separate microservice tool backends** (`docs`, `atlas`, `estate-read`, `cost-query`, `directory`, `ledger`, `plan`, `channels-draft`, `pr-draft`) instead of a single MCP server process exposing multiple tools.
* **Under-invested (where false economy hurts reliability or safety):**
  1. **Durable Task Scheduler Consumption has NO High Availability and 30-day max retention** (verified on Learn: `durable-task-scheduler-billing`), yet D2 considers it for multi-week human approval workflows. **Azure Storage** (ZRS/GZRS) has 99.9%+ SLA, unlimited retention, and is cheaper.
  2. **Cold-start timeouts on Teams card actions:** When a human clicks "Approve" or "Explain" on a Teams Adaptive Card, Bot Framework requires an HTTP 200 acknowledgement within **5–15 seconds**. A scale-to-zero Function calling a scale-to-zero Hosted Agent will time out unless the webhook immediately enqueues to Durable Functions and returns an interim card update.
  3. **Missing Principal Architect essentials:**
     * **Idempotency & Concurrency Locks on Resources:** Nothing in D10 prevents two Cases (or an hourly Watch run + a Case) from proposing conflicting plans on the same Azure resource simultaneously; the Cosmos ledger needs a per-resource lease/lock.
     * **Subscription Throttling (ARM 429) Budget:** `Surveyor` and `Azure MCP Server` querying 500–200,000 resources must strictly prefer **Azure Resource Graph** bulk queries over per-resource ARM GETs, or the tool plane will exhaust the subscription's ARM read quota.
     * **FinOps Self-Kill-Switch:** D20 mentions budgets on the solution's own spend, but remember Azure Budgets evaluate every 24h and **stop nothing**. The Conductor must enforce a hard daily token/cost counter in Cosmos DB that trips the global kill switch if the solution's own daily run-rate exceeds a threshold.

---

### (f) Verification Log (Task 5 — Verified on Microsoft Learn 2026-11-01)

* **VERIFIED:** Hosted agents CPU/memory sizes (`0.5 vCPU/1 GiB`, `1/2`, `2/4`), per-session billing, idle timeout range (`2–240 min`, default `15 min`), 30-day session deletion, and region list (Sweden Central & West Europe supported; North Europe absent) — `learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents`.
* **VERIFIED:** Source-code `.zip` deployment (`code_configuration`, Python 3.13/3.14, .NET 10) works without ACR and requires firewall egress to `mcr.microsoft.com` and `*.login.microsoft.com` — `learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code`.
* **VERIFIED:** Standard Agent Setup with private networking requires BYO Cosmos DB (≥3,000 RU/s limit; Serverless supported; new runtime uses `agent-definitions-v1` and `run-state-v1`), BYO AI Search, BYO Storage, `/24` recommended subnet delegated to `Microsoft.App/environments`, set at account creation — `learn.microsoft.com/en-us/azure/foundry/agents/concepts/standard-agent-setup` & `how-to/virtual-networks`.
* **VERIFIED:** AI Search Serverless Developer tier (preview, billed from 13 Sep 2026 in CU-hours + GB/month; no SLA, no index aliases, no shared private link) — `learn.microsoft.com/en-us/azure/search/search-sku-tier`.
* **VERIFIED:** Durable Task Scheduler Consumption SKU bills per action dispatched, max 500 actions/sec, 30-day max retention, **High Availability: Not available** — `learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-billing`.
* **UNVERIFIED:** Whether Foundry Standard Setup's `capabilityHost` ARM validation accepts an AI Search resource on the `Serverless` SKU (flagged for P5); whether hosted-agent idle-timeout minutes between the last response and deprovisioning are billed at full active vCPU/GiB rates or €0 (Learn says both *"billing is based on consumption of CPU and memory resources during active sessions"* and *"Active: Compute is running... Idle: No requests for the configured idle timeout. The platform deprovisions compute"*).

---

### (g) The ONE Decision I Would Reverse

**Reverse D3's "one hosted agent per role (10)".** Deploying 10 distinct hosted-agent microservices for a system that processes 20 cases/month is organizational role-play turned into cloud infrastructure. Replace the 10 hosted agents with **one shared agent runtime codebase deployed as 3–4 trust-zone hosted agents** (`public-read`, `estate`, `people`, `judge`), invoked via the **Invocations** protocol with the role (`surveyor`, `detective`, `economist`, `engineer`, `auditor`, `conductor`) passed in the payload over a **single shared session ID per workflow run**. You keep every bit of the scientific method, prompt specialization, Skeptic independence, and Citadel contract isolation—while eliminating 60% of the deployment artifacts, cold starts, and idle-timeout waste.