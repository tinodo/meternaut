# Assumptions, Risks & Decisions Needed

> **Status:** Ideation v1 · **Date:** 2026-10-30 · Part of the [follow-up plan](00-follow-up-plan.md)
> Everything the vision *leans on* without proof is listed here, with a cheap test and a home in the plan. Operator-only decisions (one-way doors) are marked 🚪.

---

## 1. Load-bearing assumptions

| ID | Assumption | If false… | Cheapest test | Phase |
|---|---|---|---|---|
| A1 | **Owners act when asked well** (right person, channel, evidence, one tap) — bet B1 | The product thesis shifts toward policy-first automation or shift-left | Wizard-of-Oz pilot: manual cards/emails, 30–50 cases | 2 |
| A2 | Owners can be resolved with useful accuracy from available signals + conversation | Everything stalls at gap #1; fall back to central triage | Measure resolution accuracy on 200 resources with known owners | 2–4 |
| A3 | Chat/email can carry **authenticated approvals** acceptable to security | Approvals move to a stronger channel (portal step-up), hurting UX | Prototype one approval path; security review | 4 |
| A4 | Customers will grant **write** permissions with guardrails — bet B8 | Product remains advise-only (L1) | Guardrail workshops with 3 customers' security teams | 1 |
| A5 | AI-built **case files** are trusted by engineers — bet B2 | Need more human analysis; slower, costlier | Blind review of AI vs human analyses | 2 |
| A6 | Usage signals (metrics, query audit, activity history) cover a long enough **evidence horizon** | More cases need scream-test ladders and owner confirmation | Inventory signal retention per playbook | 4 |
| A7 | **Log usefulness** can be judged from metadata/templates without exposing sensitive content | The log playbook needs stronger privacy controls or is limited to table-level analysis | Offline experiment on a consenting workspace | 4 |
| A8 | **Shadow measurement + replay** make log filtering safe enough — bet B4 | Log filtering stays advise-only | Replay existing queries/alerts against would-be-filtered data | 4–6 |
| A9 | **Counterfactual savings** convince Finance — bet B5 | Savings are reported as "estimated" only; weaker business case | Reconcile three real savings against invoices with Finance | 2–7 |
| A10 | **Attention budgets** keep HITL manageable — bet B6 | Need more policy envelopes sooner; autonomy pressure rises | Simulate message load on a real estate; fatigue survey | 2 |
| A11 | Foundry can host **long-running, multi-agent, wait-state workflows** with evaluations and tracing at tolerable cost | Re-plan the orchestration layer within Microsoft platforms | Spike | 4 |
| A12 | **Cost per case** is low enough that ROI is positive above the economic-triage threshold | Narrow to higher-value playbooks; heavier deterministic pre-filtering | Measure tokens/queries per case on the spikes | 4 |
| A13 | A community will contribute playbooks — bet B7 | Slower library growth; maintainers write most playbooks | Publish five playbooks early | 8 |
| A14 | Microsoft first-party optimisation capabilities remain **complementary** | Strategy shifts to "the open, owner-centred workflow layer" or contribution upstream | Track announcements; verified in [research/01](../research/01-azure-native-landscape.md) | 1, continuous |
| A15 | GDPR, EU AI Act and works-council implications of ownership inference are **manageable** | Owner Graph restricted to declared signals and conversation | Legal/DPIA screening | 1 |
| A16 | Publishing as open source by a Microsoft employee is **approvable** within internal rules | Hosting/ownership of the project changes | Check the internal release process | 1 |
| A17 | Directory reads needed (manager chain, delegates, presence, out-of-office) are available under **least privilege** | Weaker escalation ladders | Spike | 4 |
| A18 | Enterprises accept agent-executed changes inside existing **change management** | Provide standard-change mapping and CAB integrations earlier | Interviews | 2 |
| A19 | Cost/Advisor data is **fresh and complete** enough for the candidate playbooks | Slower detection; more reliance on resource telemetry | Spike | 4 |
| A20 | Approvers will not degrade into **rubber stamps** | Add friction proportional to risk; sample audits | Observe approval dwell time in the pilot | 7 |

---

## 2. Risk register

| ID | Risk | L | I | Mitigation | Owner (role) |
|---|---|---|---|---|---|
| R1 | Strategic overlap with first-party Azure optimisation agents | M | H | Consume their outputs; differentiate on open, owner-centred workflow; contribute upstream where sensible | Product |
| R2 | **An early harmful action** destroys trust | L | **VH** | Start at L0/L1; reversible by default; canary; Warden; no-blame rollback | FinOps lead |
| R3 | Scope creep (40 moonshots) | **H** | M | H1 scope cut in Phase 1; moonshots only as enablers | Product |
| R4 | Compromise of an agent identity | L | VH | Least privilege; JIT; separate read/write; anomaly detection | Security |
| R5 | People-data backlash (works council, employees) | M | H | Purpose limitation; transparency; contest path; opt-in signals | Privacy |
| R6 | Alert fatigue | **H** | H | Attention budgets; digests; envelopes | Product |
| R7 | Platform cost exceeds savings | M | H | Economic triage; Warden; stop rule | FinOps lead |
| R8 | Model/provider change shifts behaviour | M | M | Version pinning; regression gates | AI lead |
| R9 | Open-source governance burden | M | M | Minimal governance model; clear maintainers | Maintainers |
| R10 | Naming/trademark conflict | M | M | Resolve in Phase 1 (decision D1) | Operator |
| R11 | Over-engineering before validation | **H** | M | Wizard-of-Oz first; thin slices | Product |
| R12 | Customers refuse data/permission access | M | H | Assess/Advise modes; read-only first | Sales/CSA |
| R13 | No ground truth for evaluation | M | H | Waste Lab; Time Machine replays | AI lead |
| R14 | Perverse incentives (gaming savings) | M | M | Baselines fixed before programmes; verified-only | Finance |
| R15 | Dependence on a single chat platform/model | L | M | Fallback channels; degrade modes | Platform |
| R16 | Single-maintainer / bus factor | **H** | M | Document decisions; recruit co-maintainers early | Operator |
| R17 | Regulatory reclassification (e.g. employee-related use) | L | H | Keep ownership inference out of HR/performance use; counsel review | Legal |
| R18 | Savings accounting disputes | M | M | Ledger rules; Auditor independence | Finance |
| R19 | Community playbook supply-chain attack | M | H | Declared capabilities; signing; review; sandbox | Security |
| R20 | Hype: "AI will fix cost" expectations | M | M | Honest metrics; regret report; confidence calibration | Product |

*(L = likelihood, I = impact; VH = very high.)*

---

## 3. Decisions needed from you

| ID | Decision | Options | Recommendation | Reversibility |
|---|---|---|---|---|
| **D1** 🚪 | **Project name** | See §4 | Keep *Azure Cost in Action* as a working title until trademark/availability checks are done in Phase 1 | Costly to change after publication |
| **D2** 🚪 | **Licence** | MIT; Apache-2.0 | Decide in Phase 1. MIT matches common Microsoft FinOps assets; Apache-2.0 adds an explicit patent grant. Verify in the guardrails phase | Hard to change later |
| **D3** 🚪 | **Deployment model** | (a) single-tenant, customer-owned, self-hosted; (b) partner-operated; (c) multi-tenant service | **(a)** for the ideation assumption (data stays in the customer tenant; partner-deployable) | Architectural one-way door |
| **D4** | **First-release scope** | The 8–12 playbooks to specify first | Seeds: log usefulness, vWAN P2S, orphans, schedules, ownership; commitments advise-only | Reversible |
| **D5** | **Pilot partner and Wizard-of-Oz permission** | Internal team; a friendly customer | A friendly customer with a named executive sponsor and security contact | Reversible |
| **D6** 🚪 | **Repository visibility** | Private now → public at Phase 8, or earlier | **Stay private** until the guardrail charter and the internal release process check are done | **Public release is a one-way door** |
| **D7** | **Assess-first go-to-market** | Build the read-only *Assess* mode first as a CSA accelerator | Strongly consider: earns trust, safe, quick value | Reversible |
| **D8** | **Adjacent spend scopes** (SaaS/GitHub/M365) | In vision / later / never | *Later* (H4); keep the architecture open | Reversible |
| **D9** | **Multi-cloud stance** | Azure-only / visibility via open cost format later | Azure-only first; revisit at Phase 7 gate | Reversible |
| **D10** | **People and time** | Who else is on the project; hours per week | Needed to sequence Phases 1–3 | Reversible |
| **D11** | **Stop criteria thresholds** | Numeric thresholds for "owners don't respond", "regret", "ROI" | Set in Phase 1 with Finance and security | Reversible |
| **D12** | **Voice/avatar stance** | Explore / defer | Defer until text channels are proven; AI disclosure rules first | Reversible |

---

## 4. Naming candidates (placeholder — to be checked in Phase 1)

| Candidate | Idea | Concern to check |
|---|---|---|
| **Azure Cost in Action** (working title) | Descriptive; echoes the brief | Use of "Azure" in a project name — Microsoft trademark guidance; might read like a GitHub Action |
| **Reclaim** | Reclaiming wasted spend | Crowded name space |
| **Gleaner** | Gathering what is left after the harvest | Obscure |
| **Prune** | Pruning waste; short; verb-like | Collides with common CLI verbs |
| **Steward** | A steward of the estate; fits the "agent steward" role | Generic |
| **Closed Loop** | The loop is the product | Generic; used elsewhere |
| **Tally** | Counting, ledger | Existing products |
| **Cairn** | A trail marker — "owner left a mark" | Obscure link to the idea |

Checklist per candidate: GitHub organisation/repo, trademark search, package registries, domain, Microsoft naming guidance, pronunciation across NL/EN/DE/FR.

---

## 5. Open questions (not yet decisions)

1. Which **customers or internal teams** can host the Wizard-of-Oz pilot, and who approves outreach?
2. Which **languages** matter first (EN/NL/DE/FR)?
3. Do we need **non-production sandbox subscriptions** for the Waste Lab and the slices? Who pays?
4. What do **Finance** and **security** need to see to say yes to write access?
5. Is there an existing **internal community** (CSAs, FinOps practitioners) to co-design with?
6. How do we handle **customers in regulated sectors** (financial services, public sector) from day one?
7. What is the **support model** after launch (community, partner, none)?
8. Do we want an **advisory board** (customers, Microsoft engineers, FinOps Foundation members)?
9. How do we position vs. first-party offerings in communications?
10. What is the plan if a first-party feature makes a slice obsolete?
