# Research 01 — Azure & Microsoft native landscape for cost management and optimisation (October 2026)

> **Status:** research report v1 · **Retrieved:** 2026-10-30 · **Produced by:** research agent (desk research), spot-checked by the orchestrator (see *Orchestrator addendum*)
> Legend: **V** = Verified (primary Microsoft Learn/GitHub source read), **PV** = Partially verified (secondary source, search synthesis or inference), **not found** = could not confirm. URLs are `learn.microsoft.com` or GitHub unless noted.
> Used by: [vision](../ideation/01-north-star-vision.md), [PR/FAQ](../ideation/11-working-backwards-pr-faq.md), [plan](../plan/00-follow-up-plan.md), [capability radar](../plan/03-capability-radar.md).

---

## 1. Microsoft Cost Management

| Capability | Key facts | Verif. |
|---|---|---|
| Cost analysis | Multidimensional cost/usage views; built-in, customisable and shared views ([Quickstart](https://learn.microsoft.com/azure/cost-management-billing/costs/quick-acm-cost-analysis)) | V |
| Budgets | Cost/usage budgets scoped to subscription, resource group or billing scope; multiple thresholds ([Tutorial](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets)) | V |
| Action groups / automation hooks | Budgets trigger action groups **only at subscription and resource-group scope**. Microsoft's canonical pattern: Budget → Action Group (webhook) → Logic App → Automation runbook webhook → Stop-VM ([Manage costs with budgets](https://learn.microsoft.com/azure/cost-management-billing/manage/cost-management-budget-scenario)) | V |
| Anomaly detection & alerts | Daily per-subscription evaluation against a **60-day forecast baseline**; delivered by **email only** — no native Teams/webhook target. Documented DIY pattern: Logic Apps/Power Automate watching a shared mailbox to raise ITSM tickets ([Identify anomalies](https://learn.microsoft.com/azure/cost-management-billing/understand/analyze-unexpected-charges)) | V |
| Exports (incl. FOCUS) | Scheduled exports to Storage: actual/amortised cost-and-usage, price sheet, reservation details/recommendations/transactions ([Tutorial](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports)). **No native "export as FOCUS" dataset found**; Microsoft publishes a manual mapping to convert exports to FOCUS 1.0/1.1/1.2-preview ([Convert to FOCUS](https://learn.microsoft.com/cloud-computing/finops/focus/convert)) | V (exports) / not found (native FOCUS export) |
| Scheduled actions/emails | Budget email alerts; Advisor recommendation digest (weekly/bi-weekly/monthly, multi-category, via action group) ([Digest](https://learn.microsoft.com/azure/advisor/advisor-recommendations-digest)) | V |
| Cost allocation rules | Moves/splits shared cost between subscriptions/resource groups/tags; **does not change the invoice** — reporting-layer re-attribution only ([Intro](https://learn.microsoft.com/azure/cost-management-billing/costs/cost-allocation-introduction)) | V |
| Tag inheritance | Copies billing/RG/subscription tags onto **child usage records only**, never onto the resource; 8–24 h propagation; EA/MCA can choose resource-tag-wins or inherited-tag-wins ([Tag inheritance](https://learn.microsoft.com/azure/cost-management-billing/costs/enable-tag-inheritance)) | V |
| APIs | Query, Forecast, Budgets, Exports, Generate-Cost-Details-Report (EA/MCA), Price Sheet/Balances/Tags (EA via Consumption API), Reservation Details/Summaries/Recommendations/Transactions, Benefit- and Savings-Plan-Utilization-Summaries ([Automation scenarios](https://learn.microsoft.com/azure/cost-management-billing/manage/cost-management-automation-scenarios), [Consumption API](https://learn.microsoft.com/rest/api/consumption/)) | V |
| Power BI | Legacy Desktop **connector** and EA/MCA-only **template app** are being superseded by the **FinOps toolkit Power BI reports** ([Power BI setup](https://learn.microsoft.com/cloud-computing/finops/toolkit/power-bi/setup)) | V |
| Billing scopes | EA = Billing Account → Department → Enrollment Account; MCA = Billing Account → Billing Profile → Invoice Section; CSP = Billing Account → Billing Profile → Customer; PAYG has the narrowest feature surface ([Scopes](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-work-scopes)) | V |
| Data latency | EA/MCA: 8–24 h; **PAYG: up to 72 h**; current-period estimates refresh 6× per day ([Understand cost data](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data)) | V |
| RBAC | Built-in **Cost Management Reader/Contributor**; management-group scope needs Reader/Contributor **plus** User Access Administrator/Owner (and for EA the "AO view charges" switch); reacting to a budget via action group needs **Monitoring Contributor** on the RG holding the group ([Assign access](https://learn.microsoft.com/azure/cost-management-billing/costs/assign-access-acm-data)) | V |
| Throttling/limits | Only a generic "503 — retry in an hour" is documented for exports; explicit numeric request-rate limits **not found** | not found |

## 2. Azure Advisor — cost recommendations

VM/VMSS right-size-or-shutdown is Advisor's most fully documented algorithm ([source](https://learn.microsoft.com/azure/advisor/advisor-cost-recommendations), V):

- **Shutdown:** triggers if P95 max CPU is under 3% **and** the P100 3-day average CPU is at most 2% **and** outbound network is under 2%; memory is deliberately excluded.
- **Resize:** fits load to a cheaper SKU (including cross-family and cross-generation) while keeping P95 CPU/network at most 40% and P99 memory at most 60% (user-facing) or at most 80%/80% (non-user-facing); "user-facing" is itself ML-classified from utilisation shape.
- **Burstable-SKU:** a separate check against B-series baseline/credit sufficiency.
- Lookback is configurable (**7/14/21/30/60/90 days**; up to 48 h to re-apply); a per-subscription CPU-threshold filter takes up to 24 h.
- **Documented limitation:** savings use retail/pay-as-you-go rates and **ignore existing reservation/savings-plan coverage** — Microsoft's own doc warns a cross-series resize can *increase* effective cost if reservation-covered. Dismiss/Postpone is a first-class action.

**Delivery & governance:** five categories (Cost, Security, Performance, Reliability, Operational Excellence); **alerts on new recommendations support only High Availability, Performance and Cost — Security is explicitly excluded** ([Advisor alerts](https://learn.microsoft.com/azure/advisor/advisor-alerts-portal), V). Recommendation digest by category via action group (V). Resource Graph (`advisorresources` family) for cross-subscription KQL ([source](https://learn.microsoft.com/azure/advisor/advisor-azure-resource-graph), V); REST API exists ([source](https://learn.microsoft.com/rest/api/advisor/), V; specific operations not enumerated, PV). Advisor score ≈ average of five category scores using pay-as-you-go cost estimates that ignore discounts ([source](https://learn.microsoft.com/azure/advisor/advisor-score), V). After acting on a recommendation, Advisor can take **"up to a day"** to recognise the change ([overview](https://learn.microsoft.com/azure/advisor/advisor-overview), V) — this is re-scan latency, **not** a realised-savings check; **no evidence of actual saving verification was found anywhere.**

## 3. Microsoft AI in cost/optimisation

| Asset | Status | Does | Does **not** do / hands to human | Source |
|---|---|---|---|---|
| **Azure Copilot Optimization Agent** | **Preview** | VM/VMSS-only: explains a recommendation and alternatives, charts cost and carbon impact, **generates CLI/PowerShell scripts** | Explicitly "can't automatically create or update budgets and alerts"; max 10 items per query; a human runs the script | [Learn](https://learn.microsoft.com/azure/copilot/optimization-agent) (V) |
| Microsoft Copilot in Azure (core) | **GA** (reported since ~2025) while individual agents such as Optimization stay in preview | Chat-driven Azure operations | — | [Blog](https://techcommunity.microsoft.com/blog/azureinfrastructureblog/microsoft-copilot-in-azure-is-now-generally-available/4402033) (PV) |
| **Azure MCP Server — `advisor` tool** | GA tool surface | `recommendation list` / `summary`, `metadata get/list`, **`recommendation apply`** (writes Advisor rules into **ARM/Terraform**; Bicep unsupported) | Design-time only: edits IaC source files; **does not call a runtime remediation API** against a live resource | [Learn](https://learn.microsoft.com/azure/developer/azure-mcp-server/tools/azure-advisor) (V) |
| Azure MCP Server — **`optimization` tool** | *See addendum* | *See addendum* | *See addendum* | Orchestrator-observed |
| Stand-alone Microsoft "FinOps agent" product | — | — | Not found beyond the Optimization Agent and the FinOps-toolkit Copilot Studio template (§4) | — |

## 4. Open-source Microsoft assets

- **FinOps toolkit** ([overview](https://learn.microsoft.com/cloud-computing/finops/toolkit/finops-toolkit-overview), V) — MIT licence, `microsoft/finops-toolkit`, monthly releases. Ships **FinOps hubs** (ADX/Fabric/remote-hub reporting), **Power BI reports**, **FinOps workbooks** (cost optimisation and governance), the **Azure Optimization Engine** (now a toolkit component), a **PowerShell module**, **Bicep Registry modules**, and **Open data** (pricing units, regions, resource types, FOCUS categories, sample exports). v14 (April 2026, PV) added Advisor/custom-ARG recommendation ingestion into hubs and a **Copilot Studio "FinOps Hub Agent"** template for natural-language cost Q&A aimed at finance users.
- **Azure Optimization Engine** (original `helderpinto/AzureOptimizationEngine`) — **superseded:** its own README banner says it "migrated … to the Microsoft FinOps Toolkit", with the old code kept "for historical reasons" and an open discussion about "AOE v2" ([repo](https://github.com/helderpinto/AzureOptimizationEngine), [discussion #753](https://github.com/microsoft/finops-toolkit/discussions/753)), V.
- **azqr (Azure Quick Review)** — actively maintained (`Azure/azqr`; CI/CodeQL/OpenSSF badges, frequent releases), V. Combines Resource-Graph queries from the **Azure Proactive Resiliency Library v2 (APRL)** with the community `dolevshor/azure-orphan-resources` project plus native rules; Excel output; also an Azure MCP Server tool ([README](https://github.com/Azure/azqr), V). Reliability/compliance-first; orphan-resource detection is bundled in rather than cost-primary.
- **Azure Cost Optimization workbook** (WAF-aligned; Advisor workbooks gallery; "Preview") — tabs: Overview, Rate Optimization (Hybrid Benefit/Reservations/Savings Plan), Usage Optimization (Compute/Storage/Network/other); filter, export, and **"Quick Fix"**; disclaims that it "doesn't guarantee cost reduction" ([Workbook](https://learn.microsoft.com/azure/advisor/advisor-workbook-cost-optimization), V).
- **Orphaned-resource detection is not a single first-party product** — assembled from Azure Monitor workbooks plus azqr's bundled use of the external orphan-resources queries.

## 5. Native automation primitives for *acting*

- **Budget → remediation pipeline:** action groups fire only at subscription/RG scope; canonical example Budget → Action Group webhook → Logic App → Runbook → Stop-VM; contact emails/roles/groups are the three notification primitives ([tutorial](https://learn.microsoft.com/azure/cost-management-billing/manage/cost-management-budget-scenario), V).
- **Azure Policy** — 11 effects (`addToNetworkGroup, append, audit, auditIfNotExists, deny, denyAction, deployIfNotExists, disabled, manual, modify, mutate`); evaluation order and layered scopes are cumulative-most-restrictive ([Effects](https://learn.microsoft.com/azure/governance/policy/concepts/effects), V). CAF names cost-relevant built-ins (disallowed resource types, allowed locations, tag governance) under "Automate cost governance" ([CAF Govern](https://learn.microsoft.com/azure/cloud-adoption-framework/govern/cost-management/), V).
- **VM auto-shutdown** (single VM, portal): shutdown schedule only; no native start schedule without an Automation/Functions/Logic Apps add-on (PV).
- **Start/Stop VMs v2:** current, GA, **Azure Functions-based** (v1, Automation-runbook-based, was deprecated and removed from the marketplace from Feb 2024); modes: Scheduled / Sequenced (tag-driven) / **AutoStop** (CPU-triggered) ([What's new](https://learn.microsoft.com/azure/automation/whats-new#february-2024), [Deploy v2](https://learn.microsoft.com/azure/azure-functions/start-stop-v2/deploy), V).
- **Reservations — exchange/refund:** exchange is same-type only, processed as cancel + repurchase where the new commitment must be at least the old one's remaining value, term resets; Microsoft's own doc flags the compute-reservation exchange grace period as available **"until further notice"** (time-limited). Refund is prorated, **capped at USD 50,000 per rolling 12 months per billing profile/EA enrolment**; no early-termination fee "currently" but a possible future 12% fee is flagged; only the reservation **owner** can self-serve; CSP end customers cannot self-serve ([Exchanges & refunds](https://learn.microsoft.com/azure/cost-management-billing/reservations/exchange-and-refund-azure-reservations), V).
- **Savings plans for compute:** term/scope/exchange mechanics **not independently verified** in this pass.
- **Azure Hybrid Benefit:** Windows Server needs on-premises core licences with active Software Assurance/subscription (minimum 8 cores per VM); Linux (RHEL/SLES) supports seamless bidirectional PAYG ↔ BYOS without redeploy ([Windows](https://learn.microsoft.com/windows-server/get-started/azure-hybrid-benefit), [Linux](https://learn.microsoft.com/azure/virtual-machines/linux/azure-hybrid-benefit-linux), V).
- **Dev/Test offer:** tied to an active Visual Studio subscription; monthly credit plus discounted non-production rates ([overview](https://learn.microsoft.com/azure/devtest/offer/overview-what-is-devtest-offer-visual-studio), V).

## 6. Guidance anchors

**Cloud Adoption Framework** — the live Govern guidance retrieved is a five-step flow (team → assess risks → document policies → **enforce** → monitor), with cost as one of six automatable governance categories inside "Enforce", not a stand-alone "Cost Management discipline" page as in earlier CAF generations — **re-verify this structure before anchoring a citation to it** (V). A separate operational page, [Manage costs and billing](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-setup-guide/manage-costs), covers portal support-ticket mechanics only (V).

**WAF Cost Optimization checklist** ([source](https://learn.microsoft.com/azure/well-architected/cost-optimization/checklist), V):

| ID | Title | ID | Title |
|---|---|---|---|
| CO:01 | Create a culture of financial responsibility | CO:08 | Optimize environment costs |
| CO:02 | Create and maintain a cost model | CO:09 | Optimize flow costs |
| CO:03 | Collect and review cost data | CO:10 | Optimize data costs |
| CO:04 | Set spending guardrails | CO:11 | Optimize code costs |
| CO:05 | Get the best rates from providers | CO:12 | Optimize scaling costs |
| CO:06 | Align usage to billing increments | CO:13 | Optimize personnel time |
| CO:07 | Optimize component costs | CO:14 | Consolidate resources and responsibility |

## 7. Gap analysis

| Lifecycle step | What native tools do today | The gap |
|---|---|---|
| **Detect** | Cost Analysis, anomaly detection (60-day baseline), Advisor usage rules, azqr/APRL | Pattern detectors are narrow (mostly VM CPU/network); nothing found for "ingested-but-unqueried Log Analytics data" or "idle P2S VPN gateway scale units" |
| **Diagnose** | Advisor metadata (impact/benefit/remediation text), Cost Optimization workbook | Resource-centric; no cross-service "why" narrative tying usage to business context |
| **Ownership resolution** | Resource tags, Resource Graph joins | **No native primitive found** that resolves tag → Entra user → manager chain; every documented automation routes to a **pre-configured** email/action group |
| **Notification** | Budget/anomaly/Advisor-alert emails; digest (email/SMS via action group) | No native Teams adaptive-card delivery with evidence |
| **Persuasion / decision** | Advisor score; Optimization Agent explanation + chart | No one-click in-chat approve/reject of a specific change found; Optimization Agent output is a script, not a decision object |
| **Execution** | Budget → action group → Logic App → runbook; Advisor "apply" writes IaC; workbook "Quick Fix" | A **human runs a script or clicks Apply** everywhere documented; no agent found executing a runtime change end-to-end after approval |
| **Verification** | Advisor re-scan ("up to a day") removes a stale recommendation | **No evidence found** of realised-saving confirmation anywhere in Cost Management, Advisor or the FinOps toolkit |
| **Sustainment / drift** | Azure Policy (deny/audit), recurring budgets, continuous Advisor scan | Drift is caught passively on the next scan; no proactive "this saving regressed" signal found |

## 8. Implications for our idea (from the research agent)

1. Ownership resolution (tag → Entra → manager chain) has **no native Microsoft primitive** — the clearest differentiator.
2. Nothing in this landscape verifies **realised** savings after a change — a verification loop is itself a gap.
3. The Optimization Agent deliberately stops at script generation — a true approve-and-execute loop is unoccupied space.
4. Budget automation is VM-stop-centric and subscription/RG-scoped in Microsoft's reference pattern — a general "any safe action" executor is new.
5. FOCUS is a documented conversion target, not a native export — FOCUS-native pipelines by default beat current Microsoft guidance.
6. azqr/APRL plus the orphan-resources project are reliability-first; a consumption-first detector has no named Microsoft catalogue entry.
7. `advisor recommendation apply` edits IaC source, not live resources — every Microsoft agentic surface found stops at the human-executes boundary.
8. Reservation exchange is explicitly "until further notice" — commitment automation must design for its possible retirement.
9. The FinOps toolkit's Copilot Studio "FinOps Hub Agent" is an integration point, not a competitor.
10. Advisor alerts exclude Security from new-recommendation alerting — cross-category correlation is unexplored even inside Microsoft's tools.

---

## Orchestrator addendum (spot-checks, 2026-10-30)

| Item | Finding |
|---|---|
| **Azure MCP `optimization` tool** (agent: "not found as a separate namespace") | **It exists in the Azure MCP Server build available in the operator's environment.** Discovery-mode listing (no subscription touched) shows three read-only commands: `optimization_recommendation_list` (ranked cost-saving recommendations across subscriptions, with currency-normalised annual savings, via a curated Resource Graph query), `optimization_recommendation_alternatives` (other resize/SKU options for a VM/VMSS with filters for SKU/series/processor type) and `optimization_recommendation_explain` (current-vs-target utilisation time series over a 7-day window). All **advise only**; **compute (VM/VMSS) only**. It is not in the public Learn catalogue the agent consulted, so treat it as a newer/preview surface. Implication unchanged: first-party tooling stops at *recommend and explain*. |
| Agent could not write files | The research agent type is read-only; the orchestrator saved this report. |

**Confidence note for the project:** statements about first-party AI features (Optimization Agent preview status, `advisor`/`optimization` tool capabilities) are **fast-moving** — re-verify at Phase 1 and again at Phase 4 (assumption A14).
