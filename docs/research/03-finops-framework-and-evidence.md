# Research 03 — FinOps Framework alignment & the evidence base

> **Status:** research report v1 · **Retrieved:** 2026-10-30 · **Produced by:** research agent (desk research), spot-checked by the orchestrator (see *Orchestrator addendum*, which **corrects two points**)
> Verification key: **Verified** = primary source read in the session; **Partially verified** = credible secondary source or AI-generated search summary not independently cross-checked; **Unverified** = could not confirm — flagged as a gap, not stated as fact.
> **Tooling note from the agent:** its web-search tool failed intermittently (HTTP 502/504/timeouts) for about half of its queries. No statistic is reported unless read on a primary page or clearly flagged as secondary.
> Used by: [vision](../ideation/01-north-star-vision.md), [metrics](../ideation/10-value-metrics-and-economics.md), [ownership & people-data](../ideation/07-ownership-and-organization.md), [guardrail territory G8](../ideation/08-trust-safety-and-guardrail-topics.md).

---

## 1. FinOps Framework (current version, 2026)

Organised as: Principles → Personas → Phases → Maturity model → Domains → Capabilities → Scopes → Technology categories. *Verified* — https://www.finops.org/framework/

**Principles (6, unordered):** teams need to collaborate · business value drives technology decisions · **everyone takes ownership for their technology usage** · FinOps data should be accessible, timely and accurate · FinOps should be enabled centrally · take advantage of the variable cost model of the cloud. *Verified* — https://www.finops.org/framework/principles/

**Phases:** *Inform* (visibility and allocation), *Optimize* (rates and usage), *Operate* (continuous improvement and accountability culture); practitioners cycle through them rapidly rather than as a waterfall. *Verified* — https://www.finops.org/framework/phases/

**Domains (4) and capabilities** (the finops.org capability list is client-side rendered; the agent used Microsoft's official static mirror co-authored with the Foundation; Learn page updated 2026-05-27):

| Domain | Capabilities |
|---|---|
| **Understand Usage & Cost** | Data Ingestion · Allocation · Reporting & Analytics · **Anomaly Management** |
| **Quantify Business Value** | Planning & Estimating · Forecasting · Budgeting · Benchmarking · Unit Economics |
| **Optimize Usage & Cost** | Architecting for the Cloud · **Workload Optimization** · **Rate Optimization** · Licensing & SaaS · Cloud Sustainability |
| **Manage the FinOps Practice** | FinOps Education & Enablement · FinOps Practice Operations · Onboarding Workloads · **Policy & Governance** · **Invoicing & Chargeback** · FinOps Assessment · FinOps Tools & Services · Intersecting Disciplines/Frameworks |

*Verified* — https://learn.microsoft.com/cloud-computing/finops/framework/capabilities; domain pages at https://www.finops.org/framework/domains/.

**Maturity model (Crawl / Walk / Run)** with sample KPIs from the community benchmarking site: *Crawl* ≥70% of cost allocated to a known owner, ~60% commitment coverage, <20% forecast variance · *Walk* ≥85%, >75%, <10% · *Run* >90%, >80%, <5%. The Foundation is explicit that "Run" is **not** a universal goal — maturity should track business value. *Verified* — https://www.finops.org/framework/maturity-model/

**Personas:** *Core* personas (the FinOps team and always-present stakeholders; the exact current roster is rendered as graphics and was **not captured** — *Unverified*) and *Allied* personas explicitly named: ITAM, ITFM, Sustainability, ITSM/ITIL, **Security**. *Verified* (structure and allied list) — https://www.finops.org/framework/personas/

**Scopes → Technology Categories (2026):** a scope is "a defined segment of technology-related spending aligned to business constructs" (not an infrastructure boundary). The 2026 framework adds **technology categories**: FinOps for SaaS, Data Center, Data Cloud Platforms, **FinOps for AI**, Public Cloud. FinOps for AI addresses "cost complexity, faster development cycle, spend unpredictability, and the need for a greater degree of policy and governance … through allocation, forecasting, and optimization decisions." *Verified* — https://www.finops.org/framework/technology-categories/

---

## 2. FOCUS specification

- **Current version: FOCUS 1.4**, ratified **4 June 2026** — adds two datasets (Invoice Detail, Billing Period), 47 columns, 6 attributes, 17 glossary entries, with "zero incompatible changes" from 1.3. The validator supports 1.3 now; 1.4 support slated for Q3 2026. **FOCUS 1.5 (planned)** adds a **Price Sheet dataset for unit/token economics** — relevant to AI cost. *Verified* — https://www.finops.org/insights/introducing-focus-1-4/ , https://focus.finops.org/
- **Azure support:** Cost Management exports a FOCUS-formatted cost-and-usage-details file. The Learn schema page read is headed **"Version 1.2-preview"** (last updated 2025-10-09) — i.e. Azure's native FOCUS export **lags the ratified 1.4** (re-verify at implementation time). *Verified* (content) / *Partially verified* (currency) — https://learn.microsoft.com/azure/cost-management-billing/dataset-schema/cost-usage-details-focus
- **Columns most relevant to ownership, tags and commitments (present in Azure's export):** `Tags` (JSON custom key-values — our primary ownership signal) · **`x_AccountOwnerId`** ("email address of the identity responsible for billing for this subscription") · `x_CostCenter` · `x_ResourceGroupName`, `ResourceId`, `SubAccountId/Name` · `CommitmentDiscountId/Category/Status/Type` · `x_InvoiceSectionId/Name`. *Verified* — same page.
- **Relevance:** FOCUS gives a vendor-neutral normalisation layer; `x_AccountOwnerId`, `Tags` and `x_CostCenter` are exactly the fields owner resolution would consume **before** falling back to directory lookups.

---

## 3. State of FinOps — 2026 (current) and 2025

The survey is the Foundation's annual primary-research instrument since 2020: **2026 = 6th annual report; 2025 = 5th**, covering organisations responsible for >$69bn of cloud spend. *Verified* — https://data.finops.org/ , https://data.finops.org/2025-report/

**Key figures, 2026 (N varies by question, 523–698 respondents):**

| Topic | Figure |
|---|---|
| AI spend management | **98%** now manage AI spend (up from **63%** in 2025 and **31%** in 2024) |
| Scope beyond cloud | SaaS **90%** (from 65%) · licensing **64%** (from 49%) · private cloud **57%** (from 39%) · data center **48%** (from 36%) · **28%** starting to include labour costs |
| Organisational position | **78%** of practices report into the CTO/CIO organisation (8% into the CFO); teams with VP/C-suite engagement show markedly more influence over technology selection (e.g. cloud service selection 53% vs 24%) |
| Operating model | **81%** use centralised enablement (60%) or hub-and-spoke (21%); teams stay lean even at $100M+ spend (8–10 practitioners, 3–10 contractors) |
| Top unmet tooling requests | **(1)** granular AI spend monitoring (tokens, LLM requests, GPU utilisation); **(2)** shift-left pre-deployment architecture costing; **(3)** a single pane of glass across technology categories — with **"Automated Remediation & Easy Buttons" called out explicitly as an unmet theme** |
| Practitioner quotes (the "last mile" and incentive gap) | *"We have hit the 'big rocks' of waste and now face a high volume of smaller opportunities that require more effort to capture"*; *"Once you fix it, it's gone… how do we give developers credit for shift-left activities?"* |

*Verified* — https://data.finops.org/

**2025 comparison:** workload optimisation/waste reduction was the #1 current priority (50% of respondents) but projected to fall ~21 points as a *future* priority in favour of governance/policy at scale; "Organizational Alignment" stayed the top-cited need; "Investment and Tooling" (incl. automation) rose +20 points year on year. *Verified* — https://data.finops.org/2025-report/

**AI-spend-management maturity (2026):** top challenges — visibility into AI costs, allocating AI costs to business units, determining AI ROI ("*Is your AI providing value? No one can answer that question yet*"). Early "AI for FinOps" use cases cited: anomaly detection, automated right-sizing recommendations, natural-language querying, automated discount-instrument procurement, auto-tagging for allocation. *Verified* — https://data.finops.org/

---

## 4. Evidence for the "last mile" problem

**Waste estimate (Verified, primary):** Flexera's **2026 State of the Cloud Report** (15th annual; N = 753; surveyed winter 2025): *"Estimated wasted cloud spend ticked up to **29%**, reversing a five-year downward trend"* (from 27% the prior year), attributed to cost complexity from AI and new IaaS/PaaS services. Also: fewer than half of organisations use even one commitment discount per cloud provider; **63%** now have a FinOps team; **71%** have a Cloud Center of Excellence; 85% of large enterprises report a dedicated team/senior leader for AI oversight; 49% use unit economics (from 40%). *Verified* — https://info.flexera.com/CM-REPORT-State-of-the-Cloud

**The specific "last mile" statistic — the share of recommendations acted upon, time to remediate:** **no credible, independently verifiable figure was found.** Several vendor blogs imply such numbers exist, but none could be traced to a primary report. **This is an explicit evidence gap.** The best-documented *proxies* are:
- State of FinOps 2026's qualitative findings (diminishing returns on optimisation, the shift-left credit problem, "Automated Remediation & Easy Buttons" as an unmet need);
- the **Flexera reversal**: waste *rose* to 29% despite record FinOps-team (63%) and CCoE (71%) prevalence — consistent with, but **not proof of**, "detection scaled, outcomes didn't".

**Why recommendations are ignored:** no generic academic citation was verified. The only verified first-party evidence is the practitioner-quoted incentive/attribution gap above. Treat claims about trust, risk-aversion and time-poverty as **reasonable hypotheses consistent with practitioner quotes**, not as measured findings.

> **Policy for this project:** never state a "percentage of recommendations ignored" anywhere in our materials. Use the verified proxies, label the gap as untested, and let the Wizard-of-Oz pilot produce our *own* number.

---

## 5. Behavioural and organisational evidence

- **Showback → allocation → chargeback is the Foundation's recommended *sequence*, not interchangeable options:** "we generally recommend most organizations start with showback … then implement cost allocation … and lastly implement chargeback." *Verified* — https://learn.microsoft.com/cloud-computing/finops/framework/manage/invoicing-chargeback
- **Policy rollout discipline:** the Policy & Governance capability recommends "**start with audit rules and slowly (and safely) expand coverage** to drive compliance without negatively impacting engineering efforts", and tagging for "business and application owners" to support anomaly response — a verified precedent for a staged, soft-launch automation posture. *Verified* — https://learn.microsoft.com/cloud-computing/finops/framework/manage/governance
- **Ownership principle:** "Everyone takes ownership for their technology usage … accountability is pushed to the edge, with engineers taking ownership of costs from architecture design to ongoing operations …" *Verified* — https://www.finops.org/framework/principles/
- **Gaps (not fabricated):** no verified peer-reviewed or credibly sourced study on gamification, "savings dividend" schemes or nudge theory specific to cloud-cost behaviour was found. **Follow-up:** FinOps X talk abstracts and case studies on data.finops.org.

---

## 6. Autonomy / human-in-the-loop evidence

- **Verified FinOps precedent:** the audit-first, staged-expansion rollout (above) is the clearest primary-sourced *crawl-walk-run for automation* guidance: start in observe/recommend-only mode, expand to auto-execution only for narrow, reversible, well-tested actions.
- **Gap — Microsoft Responsible AI Standard / agent-oversight guidance:** not fetched in the session; **Unverified**. **Action:** verify against https://www.microsoft.com/ai/responsible-ai and the Foundry/agent-framework Learn documentation before citing a specific oversight requirement (guardrail domain G12).

---

## 7. Regulatory and ethical anchors (to validate with counsel — not legal advice)

**EU AI Act, Article 50 (transparency for AI systems that interact with people)** — text confirmed: providers must ensure natural persons are informed they are interacting with an AI system (unless obvious); synthetic content must be machine-readably marked; deployers of emotion-recognition/biometric-categorisation systems must inform exposed persons. *Verified* — https://artificialintelligenceact.eu/article/50/

**"Digital Omnibus / AI Omnibus" status (verified by the orchestrator against two sources, see addendum):** proposed 19 Nov 2025; political agreement May 2026; Parliament adopted 16 Jun 2026; Council 29 Jun 2026; published in the Official Journal 24 Jul 2026; **in force 27 Jul 2026**. *Verified* — https://digital-strategy.ec.europa.eu/en/news/ai-omnibus-enters-force , https://fpf.org/blog/the-ai-act-implementation-timeline-what-changes-under-the-ai-omnibus/

**GDPR (employee/owner data used for ownership resolution)** — *Unverified in the session; flagged for counsel.* Resolving an owner via directory + tags processes personal data (name, email, manager chain). Counsel should check lawful basis, **purpose limitation** (directory data collected for IT reused for cost-accountability naming), and member-state employment-context rules before any pilot that contacts a named individual.

**Works councils (NL/DE)** — *Unverified in the session; flagged for counsel.* A system that attributes consumption and automated recommendations to named individuals and messages them directly may qualify as a system capable of monitoring employee conduct or performance under Dutch (Wet op de ondernemingsraden) and German (Betriebsverfassungsgesetz) co-determination regimes, which commonly require works-council consultation or approval. Verify with local counsel in each target jurisdiction.

---

## 8. Implications for our idea (from the research agent)

1. **Lead with FOCUS, not Azure-native schemas** — `x_AccountOwnerId`, `Tags`, `x_CostCenter` give a provider-native ownership starting point before directory lookups; re-verify the exported FOCUS *version* (1.2-preview vs ratified 1.4).
2. **Position inside "Optimize Usage & Cost" + "Manage the FinOps Practice"** and frame Teams/email nudges as an implementation of *Policy & Governance* and *Invoicing & Chargeback* — the Foundation's own vocabulary.
3. **Adopt "FinOps for AI" as a named category from day one** — and have the crew report its *own* token/compute cost with the same instrumentation it recommends.
4. **"Automated Remediation / Easy Buttons" is an explicit, dated unmet need** (State of FinOps 2026) — direct evidence the "one-click safe action" concept addresses a named gap.
5. **Do not invent a "% of recommendations ignored" statistic.** Use the verified proxy: waste is *rising* (29%) despite record FinOps/CCoE adoption.
6. **Solve the "shift-left credit" problem as a product feature** — "your approved actions saved €X, verified" answers *"how do we give developers credit."*
7. **Mirror the Foundation's rollout pattern** — audit-only → scoped automation → broader automation, with promotion tied to false-positive/rollback rates.
8. **Treat Article 50 as already binding** — see the addendum for the precise 50(1)/50(2) split.
9. **Scope the GDPR/works-council review early** — the differentiator *is* resolving and contacting a named human, which carries more employee-monitoring-adjacent risk than Advisor ever did.
10. **Two follow-up research tasks:** (a) a credible, primary-sourced figure on recommendation action rates/time-to-remediate (e.g. Azure product telemetry); (b) Microsoft's Responsible AI Standard oversight clauses and any Foundation-published behavioural-science material.

---

## Orchestrator addendum (spot-checks, 2026-10-30)

| Item | Result |
|---|---|
| **Article 50 was "not delayed by the Omnibus"** (agent's *Partially verified* inference) | **Only half right.** FPF's timeline (retrieved 2026-10-30): *"While Article 50 becomes generally applicable on **2 August 2026**, the AI Omnibus **postpones Article 50(2)** (transparency obligations for GPAI models generating synthetic content) **to 2 December 2026**."* So **Article 50(1) — informing people they are interacting with an AI — applies now**, which is the provision our messaging/voice/avatar design must satisfy; the machine-readable-marking duty in 50(2) is postponed. The Commission also published *Guidelines on transparency of AI-generated content* (20 Jul 2026) and a related Code of Practice. |
| **Employment-related high-risk use** | Verified with the Commission page: **Annex III high-risk obligations now apply from 2 December 2027** (previously 2 Aug 2026); Annex I from 2 Aug 2028. Annex III includes AI used in employment/worker management — which is why guardrail **G8-04** insists ownership inference stays *out of any performance or HR use*. |
| **FOCUS in Azure** | The agent's reading is right: a native **"Cost and usage details (FOCUS)"** export exists (not at management-group scope). [research/01](01-azure-native-landscape.md) originally said "no native FOCUS export" and has been **corrected**. Open question: the schema page is labelled **1.2-preview** vs the ratified **1.4**. |
| **AI literacy obligation** | The Omnibus softened Article 4 (providers/deployers must *support the development of* AI literacy rather than *ensure* a sufficient level) — relevant to how we document staff enablement; low impact. |
