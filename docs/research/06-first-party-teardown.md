# Research 06 — First-party tear-down (what Microsoft already ships, and where we stand)

> **Status:** research note **v2** (corrected after rubber-duck round 2; v1 archived [here](../_archive/round-2-v2/research/06-first-party-teardown.md)) · **Retrieved:** 2026-10-30 · **Written by:** orchestrator, from primary sources read during Rubber-Duck Round 1 spot-checks and from [research/01](01-azure-native-landscape.md) and [research/04](04-seed-example-facts.md); round-2 corrections from the Learn-grounded fact-check ([reviews/round-2/02](../reviews/round-2/02-factcheck-learn.md))
> **Why this exists:** Reviewer C (strategy) found that parts of our "gap" story were overstated. This note is the corrected, dated picture, with a **ride / build / contribute** position per asset. **Repeat quarterly** (see the checklist at the end).
> Legend: ✓ present · ◐ partial or different scope · ✗ none found · **V** verified (primary source read) · **PV** partly verified · **U** unverified.

---

## 1. The assets

| # | Asset | Status (2026-10-30) | What it does (verified) | Limits |
|---|---|---|---|---|
| 1 | **Azure Advisor — cost** | GA | VM/VMSS shutdown and right-size rules (P95/P100 thresholds, configurable lookback), reservation/savings-plan advice, idle resources; digest, alerts (not Security), Resource Graph and REST access | Retail-rate savings; **ignores existing commitment coverage**; dismiss/postpone; no owner routing; re-scan only, no realised-savings check (V — research/01) |
| 2 | **Azure Copilot Optimization Agent** | **Preview** | VM/VMSS only: explains a recommendation and alternatives, charts cost and carbon, **generates CLI/PowerShell scripts** | A human runs the script; cannot create budgets/alerts (V — research/01) |
| 3 | **Azure MCP Server — `advisor` and `optimization` tools** | Available | `advisor`: list/summary/metadata and **`recommendation apply`** (returns Advisor rules to apply to an ARM/Terraform IaC file — design-time); *the current server build also exposes* **`advisor_recommendation_update`** (complete, dismiss, postpone or reactivate — a runtime write of **Advisor state**), **`advisor_remediation_get`** (remediation steps and artefacts with destructive/reversible/confidence/effort metadata) and `advisor_servicegroupintelligence_get`. `optimization`: `_recommendation_list` (**subscription- or tenant-wide** ranked cost recommendations), `_alternatives` and `_explain` (**VM/VMSS only**) | Advice, scripts, IaC edits and recommendation-state changes; **no remediation executed on a live resource** (V — research/01 + round-2 tool discovery) |
| 4 | **Cost Management anomalies and budgets** | GA | 60-day baseline anomaly alerts; budgets with action groups (subscription/RG scope); budgets can include **reservation purchase** costs | **Documented delivery is email** for anomalies (no Teams/webhook target documented); VM-stop-centric reference automation (V) |
| 5 | **FinOps toolkit v15 (Oct 2026)** | MIT-licensed, monthly releases | Hubs, Power BI reports, workbooks, Azure Optimization Engine (merged in), PowerShell, open data (incl. instance-size flexibility), **FinOps alerts (idle Application Gateways and idle public IPs — v15 *fixed* those queries; the alerts pre-date v15 and none covers VPN/P2S)**, **agent plugins for Claude Code and GitHub Copilot CLI (5 agents, 4 commands, KQL skill, scoped read-only Azure MCP server)**, Copilot Studio "FinOps Hub Agent" template (v14), ecosystem page | Read-only agents; reporting-centric; no execution (V — release notes) |
| 6 | **Defender for Cloud governance rules** | GA; needs **Defender CSPM** | Assign **owner (from a resource tag or fixed email)** and **due date (7/14/30/90 days)** to *security* recommendations; **weekly email to owners; the owner's manager receives a weekly summary of overdue recommendations** (manager found via Entra ID) — a default digest, not an event mail; governance report; the rules also cover AWS and GCP | Security recommendations only; email; no execution (V) |
| 7 | **Azure SRE Agent** | Available (GA status U) | Operations agent: Teams/Outlook connectors, scheduled tasks, **Review mode — proposes Azure CLI/ARM operations; executes after Approve/Deny**; autonomy per response plan/task (**default Autonomous** there; **agent-level default Review**); hooks and tool-access policies; Entra on-behalf-of elevation | **Only SRE Agent Administrators approve**; operations focus, not a cost workflow; guidance lists "Cost and usage reports" as Autonomous; **always-on billing 4 AAU per agent-hour at about USD 0.10 per AAU ≈ USD 292/month per agent before token usage** (trial of up to 30 days waives it) — material if it is the "optional execution runtime" (V for run modes; cost reviewer-cited) |
| 8 | **Microsoft Sentinel SOC optimization** | GA/Preview mix | **Data-value recommendations:** billable tables ingested in the past **30 days** unused by rules or unused at all → analytics templates / Basic plan / stop ingestion / long-term retention; **unused columns (Preview)**; a third observation flags tables **used only by Azure Monitor** → move to a non-security workspace | **Sentinel-only, security-scoped, 30-day window**; the Sentinel experience in the Azure portal retires after **31 March 2027** (Defender portal only) (V) |
| 9 | **Azure Monitor cost guidance, Workspace Insights, Advisor log recommendations** | GA | Volume analysis, Basic-plan and tier advice, ingestion anomaly | **No "never queried" signal**; query audit off by default (V — research/04) |
| 10 | **Azure Policy, Start/Stop VMs v2, VM auto-shutdown** | GA | Preventive guardrails; scheduled/tag-driven/CPU-triggered stop-start | No owner conversation; no verification (V — research/01) |

---

## 2. Coverage of the loop

| Loop step | Advisor | Optimization Agent / MCP | Cost Mgmt | FinOps toolkit v15 | Defender governance | SRE Agent | Sentinel SOC opt. | **Our proposition** |
|---|---|---|---|---|---|---|---|---|
| **Detect usage-based waste** (cost domain) | ◐ VM rules, idle | ◐ VM/VMSS | ✗ (anomalies only) | ◐ workbooks, alerts | ✗ | ✗ | ◐ unused tables (Sentinel, 30 d) | **Usage-truth playbooks** incl. non-Sentinel logs, longer horizons, capacity units |
| **Resolve owner from directory** | ✗ | ✗ | ✗ | ✗ | ✓ tag → owner → manager (**security**) | ✗ | ✗ | **Owner Graph** for cost: tags + directory + history + conversation |
| **Deliver in Teams with evidence** | ✗ email | ✗ chat/scripts | ✗ email | ✗ | ✗ email | ◐ Teams connector (ops) | ✗ | **Decision cards + digests** (cost) |
| **Owner (not admin) approves** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ (admins only) | ✗ | **Owner-as-approver with authority check** |
| **Execute after approval** | ✗ | ✗ (scripts / IaC edits) | ◐ budget automation | ✗ | ✗ | ✓ CLI/ARM (admins) | ✗ | **Typed, gated execution; IaC-PR first-class** |
| **Verify realised savings** | ✗ | ✗ | ✗ | ◐ reporting | ◐ governance report (progress) | ✗ | ✗ | **Savings Ledger with counterfactual** |
| **Sustain / detect drift** | ◐ re-scan | ✗ | ◐ anomalies | ◐ | ◐ | ✗ | ✗ | **Drift guard, regression watch** |
| **Open, portable playbooks + ground-truth eval** | ✗ | ✗ | ✗ | ◐ open data / KQL | ✗ | ◐ skills | ✗ | **Open Waste Rules + Waste Lab** |

**Reading the table honestly:** every *individual plumbing capability* now exists somewhere in Microsoft's stack (owner→manager email, approve-then-execute, Teams delivery, unused-table detection). **What does not exist, as far as first-party primary sources show:** the **combination for cost** — owner-resolved, owner-approved, evidence-bearing, executed, **verified** — plus **usage-truth detectors with ground truth** that work outside Sentinel and beyond 30 days, and an **open evaluation harness**. *Outside Microsoft* the picture is similar but not empty: [research/02](02-third-party-and-oss-landscape.md) found 22 commercial products in four archetypes; the closest to our loop (for example an in-channel approval gate for two Azure actions in one observability product — confirmed — and autonomous Azure commitment buying *claimed by* several rate-optimisation vendors — partly verified at best) cover *pieces*; no directory-resolved owner approval combined with counterfactual verification was found — an **absence of evidence, not proof of absence**.

---

## 3. Position per asset

| Position | Assets | What we do |
|---|---|---|
| **Ride** (use as inputs or runtimes) | Advisor and `optimization` data; Cost Management + FOCUS exports; FinOps hubs/open data (e.g. instance-size flexibility); FinOps alerts; SRE Agent as an *optional execution runtime* | Consume their outputs; do not rebuild reporting |
| **Copy the proven pattern** | Defender governance rules (tag → owner → due date → manager nudge) | Replicate the *pattern* for cost, with the guardrails that pattern lacks (consent, escalation rules, no named-person pressure) |
| **Build (our differentiation)** | Usage-truth playbooks (log usefulness outside Sentinel, capacity-unit right-sizing); cost-domain Owner Graph and owner-as-approver authority gate; verified-savings ledger; Waste Lab | Validate each with ground truth before building plumbing |
| **Contribute** | Detector specs, Waste Lab scenarios, ledger counting rules | Offer upstream to the FinOps toolkit (MIT) and keep skills runtime-portable (agent plugins, MCP) |
| **Accept obsolescence** | Teams plumbing, scheduling, generic approvals | The moat is *time and validated content*, not plumbing |
| **Watch (not a dependency)** | Third-party FinOps products and open-source tools ([research/02](02-third-party-and-oss-landscape.md)) | The product stays Microsoft-only; log overlap at the quarterly re-check (risk R27), borrow ideas, keep the open cost format as the interchange |

---

## 4. Re-assessment trigger (kill criterion K4)

If **first-party tooling ships owner-routed and owner-approved execution for three or more release-1 playbooks**, the project moves to **contribute-only** mode (see [plan/01](../plan/01-assumptions-risks-decisions.md)). A *third-party* equivalent does **not** trigger K4 — there is nothing to contribute to — but is logged at the same re-check (plan/01 risk R27).

*Reviewer C's 12-month odds (judgement, unverified): more advice and scripts ≥85%; owner-routed cost recommendations ~40%; a first-party cost skill pack on an approve→execute runtime ~50%; owner (not admin) approval ~30%; counterfactual saving verification ~20%.*

---

## 5. Quarterly re-check checklist

Re-read, and diff against this note: Advisor cost recommendation catalog · Azure Copilot Optimization Agent status · Azure MCP `advisor`/`optimization` tool lists (including the state-write and remediation tools) · Cost Management anomaly alert targets (still email-only?) · FinOps toolkit release notes (v16+: agent plugins, alerts, execution?) · Defender governance rules scope (cost recommendations?) · SRE Agent run modes, approver roles, cost skills, **GA status and always-on pricing** · Sentinel SOC optimization scope (non-Sentinel workspaces? window length?) · Azure Monitor query-audit coverage notes · **the reservation exchange policy (the 1 Feb 2027 cutoff)** · **the third-party landscape in [research/02](02-third-party-and-oss-landscape.md)** (new execution gates, autonomous commitment products, open-source agent skills). Add a dated row for every change.

---

## 6. Corrections after Rubber-Duck Round 2

Applied from the Learn-grounded fact-check ([reviews/round-2/02](../reviews/round-2/02-factcheck-learn.md)); the five largest were re-read against primary sources by the orchestrator: **(1)** the Azure MCP tools (rows 3 — state-write and remediation tools exist; `optimization_recommendation_list` is tenant-wide); **(2)** toolkit v15 *fixed* the alert queries rather than adding the alerts (row 5); **(3)** the Defender manager mail is a weekly overdue summary and the rules cover other clouds (row 6); **(4)** the SRE Agent's default modes and running cost (row 7); **(5)** the Sentinel "only used by Azure Monitor" observation (row 8). Anomaly-alert delivery is reworded to "documented delivery is email" (row 4), because "no Teams/webhook target" was an inference from silence. **Still unverified:** the SRE Agent's GA status and the AOE README banner.
