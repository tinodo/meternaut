# Assumptions, Risks & Decisions

> **Status:** Ideation **v3** (revised after rubber-duck round 2; v2 archived [here](../_archive/round-2-v2/plan/01-assumptions-risks-decisions.md), v1 [here](../_archive/round-1-v1/plan/01-assumptions-risks-decisions.md)) · **Date:** 2026-10-30 · Part of the [follow-up plan](00-follow-up-plan.md)
> Everything the vision *leans on* without proof is listed here, with a cheap test and a home in the plan. 🚪 marks a **one-way door** — revisit it before the door closes (publication, signing artefacts, building for a customer); ✅ marks a **decision taken**.
> **Operator stance (2026-10-31):** this is ideation for an **MIT-licensed demonstrator** of what AI and Foundry agents can do inside governed workflows. **D2 is decided: MIT.** Nothing else waits for an answer — every remaining decision in §3 carries its recommended option as an *assumed default* and a *revisit trigger*, so nothing is dropped and nothing blocks.

---

## 1. Load-bearing assumptions

| ID | Assumption | If false… | Cheapest test | Phase |
|---|---|---|---|---|
| A1 | **Owners act when asked well** (right person, channel, evidence, one tap) — bet B1 | The product thesis shifts toward policy-first automation or shift-left (**K1**) | Wizard-of-Oz pilot to a **pre-registered design with a comparison condition** (matched control or stepped rollout): manual cards/emails, 30–50 cases; a ~10-card test already in the 0.5 sprint | 0.5, 2 |
| A2 | Owners can be resolved with useful accuracy from available signals + conversation | Everything stalls at gap #1; fall back to central triage | Measure resolution accuracy on 200 resources with known owners | 2–4 |
| A3 | Chat/email can carry **authenticated approvals** acceptable to security | Approvals move to a stronger channel (portal step-up), hurting UX | Prototype one approval path; security review | 4 |
| A4 | Customers will grant **write** permissions with guardrails — bet B8 | Product remains advise-only (L1) | Test with **concrete least-privilege role definitions reviewed by a real security person**, plus the IaC-PR path (S1b, S13) — not only generic workshops; guardrail workshops with 3 customers' security teams | 0.5, 1 |
| A5 | AI-built **case files** are trusted by engineers — bet B2 | Need more human analysis; slower, costlier | Blind review of AI vs human analyses | 2 |
| A6 | Usage signals (metrics, query audit, activity history) cover a long enough **evidence horizon** | More cases need scream-test ladders and owner confirmation | Inventory signal retention per playbook; **enable query audit (LAQueryLogs) on pilot workspaces now** — it is off by default, so the evidence clock starts only when it is on — and prove coverage per workspace with a canary | 0.5, 4 |
| A7 | **Log usefulness** can be judged from metadata/templates without exposing sensitive content | The log playbook needs stronger privacy controls or is limited to table-level analysis | Offline experiment on a consenting workspace | 4 |
| A8 | **Shadow measurement + replay** make log filtering safe enough — bet B4 | Log filtering stays advise-only (and as an R3-Data class it never runs at L3/L4 in any case) | Replay existing queries/alerts against would-be-filtered data | 4–6 |
| A9 | **Counterfactual savings** convince Finance — bet B5 | Savings are reported as "estimated" only; weaker business case | Reconcile three real savings against invoices with Finance; compare with a matched control so that only the **incremental** effect is claimed | 2–7 |
| A10 | **Attention budgets** keep HITL manageable — bet B6 | Need more policy envelopes sooner; autonomy pressure rises | Simulate message load on a real estate; fatigue survey | 2 |
| A11 | Foundry can host **long-running, multi-agent, wait-state workflows** with evaluations and tracing at tolerable cost | Re-plan the orchestration layer within Microsoft platforms | Spike | 4 |
| A12 | **Cost per case** is low enough that ROI is positive above the economic-triage threshold | Narrow to higher-value playbooks; heavier deterministic pre-filtering | Measure tokens/queries per case on the spikes | 4 |
| A13 | A community will contribute playbooks — bet B7 | Slower library growth; maintainers write most playbooks | Publish five playbooks early | 8 |
| A14 | Microsoft first-party capabilities remain **complementary for cost optimisation across consumption** — they already close parts of a loop for *their* domains (Defender governance rules, SRE Agent Review mode, Sentinel SOC optimization, FinOps toolkit v15) | **K4**: the project becomes contribute-only | Quarterly re-check of [research/06](../research/06-first-party-teardown.md); landscape in [research/01](../research/01-azure-native-landscape.md) | 0.5, continuous |
| A15 | GDPR, EU AI Act and works-council implications of ownership inference are **manageable** | Owner Graph restricted to declared signals and conversation | Legal/DPIA screening | 1 |
| A16 | Publishing as open source by a Microsoft employee is **approvable** within internal rules | Hosting/ownership changes; **K6** → internal accelerator | Check the internal release process before the repository goes public (D6, D13); until then nothing is published | before D6 |
| A17 | Directory reads needed (manager chain, delegates, presence, out-of-office) are available under **least privilege** | Weaker escalation ladders | Spike | 4 |
| A18 | Enterprises accept agent-executed changes inside existing **change management** | Provide standard-change mapping and CAB integrations earlier | Interviews | 2 |
| A19 | Cost/Advisor data is **fresh and complete** enough for the candidate playbooks | Slower detection; more reliance on resource telemetry | Spike | 4 |
| A20 | Approvers will not degrade into **rubber stamps** | Add friction proportional to risk; sample audits | Observe approval dwell time in the pilot | 7 |
| A21 | A named **orphan custodian** exists (or can be named) for each scope | Orphans stay advise-only; the missing custodian is itself a governance finding | CoE interview; draft a custodian clause for the policy envelope | 0.5, 2 |
| A22 | Owners will **affirmatively enrol** in veto windows (L3) | L3 never materialises; most classes stay at L2 (Assist) and HITL economics worsen | Measure enrolment willingness in the Wizard-of-Oz pilot | 2 |
| A23 | Authorised buyers will **sign each commitment transaction** individually | The commitment portfolio stays advice-only | Finance interview | 1–2 |
| A24 | Query-audit **coverage** can be measured per workspace with a canary | Log usefulness is limited to advice with an explicit coverage caveat | Canary spike on pilot workspaces | 0.5, 4 |
| A25 | **Enrolled autonomy** (L3/L4) is usable, trusted and economical at scale — a separate hypothesis from closure, which Release 1 tests | The product stays at Advise and Assist; HITL economics are then the main constraint | A separate pre-registered test later: enrolment rate, approval fatigue, regret per enrolled class, on a bounded non-destructive class such as dev sleep schedules | 7+ |
| A26 | **Advisor recommendation state** (accepted, dismissed, postponed) can be read — and, where we are authorised, written — through an identity we can govern, so a routed recommendation can be *closed* and *verified* | Closure verification falls back to re-scanning resource state, which Advisor itself recognises only "up to a day" later; the closed-loop claim weakens for Advisor-sourced cases | Spike **S2** (on the Release-1 critical path) | 4 |

---

## 2. Risk register

| ID | Risk | L | I | Mitigation | Owner (role) |
|---|---|---|---|---|---|
| R1 | Strategic overlap with first-party Azure optimisation tools | M | H | Ride / copy / build / contribute map ([research/06](../research/06-first-party-teardown.md)); quarterly re-check; **K4** triggers contribute-only | Product |
| R2 | **An early harmful action** destroys trust | L | **VH** | Start at L0/L1; classed actions (reversible ones canaried and rolled back; R3 needs two keys, R3-Data the owner, the data owner and security); Warden; **blameless** review; **K2** freezes writes | FinOps lead |
| R3 | Scope creep (40 moonshots, 305 catalog rows) | **H** | M | Release-1 cut **pre-registered in Phase 0.5**; every idea has a status (selected / research queue / parked / retired) | Product |
| R4 | Compromise of an agent identity | L | VH | Least privilege; JIT; separate read/write; anomaly detection | Security |
| R5 | People-data backlash (works council, employees) | M | H | Purpose limitation; transparency; contest path; opt-in signals | Privacy |
| R6 | Alert fatigue | **H** | H | Attention budgets; digests; envelopes | Product |
| R7 | Platform cost exceeds savings | M | H | Economic triage; Warden; stop rule | FinOps lead |
| R8 | Model/provider change shifts behaviour | M | M | Version pinning; regression gates | AI lead |
| R9 | Open-source governance burden | M | M | Minimal governance model; clear maintainers | Maintainers |
| R10 | Naming/trademark conflict | M | M | Resolve before publication (decision D1); the working title is kept while private | Operator |
| R11 | Over-engineering before validation | **H** | M | Wizard-of-Oz first; thin slices | Product |
| R12 | Customers refuse data/permission access | M | H | Assess/Advise modes; read-only first | Sales/CSA |
| R13 | No ground truth for evaluation | M | H | Waste Lab; Time Machine replays | AI lead |
| R14 | Perverse incentives (gaming savings) | M | M | Baselines fixed before programmes; verified-only | Finance |
| R15 | Dependence on a single chat platform/model | L | M | Fallback channels; degrade modes | Platform |
| R16 | Single-maintainer / bus factor | **H** | M | Document decisions; recruit co-maintainers early; **K7** freezes the project if the time budget lapses | Operator |
| R17 | Regulatory reclassification (e.g. employee-related use) | L | H | Keep ownership inference out of HR/performance use; counsel review | Legal |
| R18 | Savings accounting disputes | M | M | Ledger rules; Auditor independence | Finance |
| R19 | Community playbook supply-chain attack | M | H | **Declarative, read-only playbooks only**; actions only from a small maintainer-owned typed catalog; signing; review | Security |
| R20 | Hype: "AI will fix cost" expectations | M | M | Honest metrics; regret report; confidence calibration | Product |
| R21 | Evidence-integrity, insider/Buyer-collusion, approval-abuse, poisoned-feedback and evaluation-gaming attacks (T31–T38) | M | H | Control matrix; independence profile and correlated-failure drill; governed releases; preparer ≠ signer | Security |
| R22 | **Silence misread as consent** (veto windows, orphans) | L | **VH** | Invariant 15; affirmative enrolment with proof of delivery; an orphan custodian, not a countdown | Product + Security |
| R23 | Model retirement and evaluation upkeep with a single maintainer | **H** | M | Model-agnostic skills and MCP; budgeted re-evaluations (Learn states at least 60 days' notice before retirement of a GA model) | AI lead |
| R24 | Employer, IP or open-source approval is not obtained | M | H | Decision **D13** (assumed handled by the operator; revisit before publication); **K6** falls back to an internal accelerator | Operator |
| R25 | A mis-sized P2S gateway cuts users off (capacity is banded; Microsoft says to plan for downtime when scaling) | L | H | Banded lookup that satisfies connections *and* bandwidth plus headroom; consent from every affected business unit; human-approved window; rollback; never labelled "low-risk automation" | Product |
| R26 | **Classification laundering, instrumentation creep and custodian overreach** (T39–T41) | M | H | Class derived from typed effects and linted; instrumentation is an action with an end date and cost cap; custodian appointment separate from action, retirement needs a second authority | Security |
| R27 | Third-party products add owner-approved Azure execution (Datadog already offers in-channel approval for two Azure actions) or autonomous commitment buying | M | M | Logged at the quarterly re-check; differentiate on directory-resolved owners, replay-based safety, counterfactual verification — all *not found* in [research/02](../research/02-third-party-and-oss-landscape.md); K4 is first-party only because we cannot contribute to a proprietary product | Product |

*(L = likelihood, I = impact; VH = very high.)*

---

## 3. Decisions: decided or assumed

**Status board.** One line per decision: what is *taken*, or what is *assumed* until its trigger. The reasoning and the alternatives are in the table below the board.

| ID | Status | Default taken | Revisit when |
|---|---|---|---|
| D1 | Assumed | Keep the working title *Azure Cost in Action* while the repository is private | Before the repository goes public (D6) |
| D2 | ✅ **Decided** | **MIT**, for code, documents and playbook specs — [`LICENSE`](../../LICENSE) | — |
| D3 | Assumed | Single-tenant, customer-owned, self-hosted | Phase 5 (architecture) |
| D4 | Assumed | The five-play Release 1 | The Phase-0.5 memo |
| D5 | Assumed | A friendly customer — or an internal estate or the Waste Lab for a lab-only demonstration | When Phase 0.5 is scheduled |
| D6 | Assumed | Private | Before any publication |
| D7 | Assumed | Assess-and-Close | Phase 2 |
| D8 | Assumed | Adjacent spend parked | A sponsor asks |
| D9 | Assumed | Azure-only | Only if founding constraint F2 changes |
| D10 | Assumed | The operator, part-time (K7 is the guard) | When Phase 0.5 is scheduled |
| D11 | Assumed | K1–K7 as written | Pre-registration in Phase 0.5 |
| D12 | Assumed | Voice and avatars deferred | Text channels proven |
| D13 | Assumed | Employer, OSPO and IP are the operator's to handle outside this package; nothing is published while the repository is private (K6 is the fallback if it proves otherwise) | Before D6 |
| D14 | Assumed | **Yes** — purchases are never L3–L5 ([invariant 16](../ideation/08-trust-safety-and-guardrail-topics.md#4-candidate-safety-invariants-non-negotiables-to-ratify)) | Never loosened without a signed-manifest design |
| D15 | Assumed | The platform team is the default custodian, the FinOps lead the backstop | Phase 1 |
| D16 | Assumed | The maintainers (initially the operator) hold the trust root; a customer deployment adds the customer's FinOps lead and security | Before any behaviour-affecting artefact ships |
| D17 | Assumed | The data owner and the customer's security contact sign; a lab-only demonstration needs no outside signer | When Phase 0.5 touches a real estate |
| D18 | Assumed | The service owner plus security | Before the first automatic-pause class |

| ID | Decision | Options | Recommendation | Reversibility |
|---|---|---|---|---|
| **D1** 🚪 | **Project name** | See §6 | **Assumed: keep the working title while the repository is private** — renaming is free until it goes public. Settle it before then (D6): "Azure" is a Microsoft mark; the strategy reviewer read the guidelines (many uses "require a license first") but could not find the rule for third-party project names — ask OSPO at that point. "… for Azure" may be used descriptively once OSPO agrees | Free while private; costly after publication |
| **D2** ✅ | **Licence** | MIT; Apache-2.0; CC-BY for docs and playbook specs | **Decided: MIT**, for code, documents and playbook specs alike (operator, 2026-10-31); [`LICENSE`](../../LICENSE) added. MIT is also the FinOps toolkit's licence, so detector specs and Waste Lab scenarios can be contributed upstream without licence friction | Decided; hard to change once outside contributors arrive |
| **D3** 🚪 | **Deployment model** | (a) single-tenant, customer-owned, self-hosted; (b) partner-operated; (c) multi-tenant service | **(a)** for the ideation assumption — data stays in the customer tenant, **including all model prompts, traces, memories and audit data**; partner-deployable | Architectural one-way door |
| **D4** | **First-release scope** | The Release-1 cut | **Five items:** Owner Graph · log usefulness (advisory, non-Sentinel, template-level) · P2S right-sizing (Assist; advise-only until spike S7 is Green; every affected business unit consents) · **orphans and Advisor-recommendation closure** (the loop-proving vehicle, and the brief's own problem) · provisioned-throughput utilisation (demand-pull, conditional). **Parked:** schedules, commitments, security-tool economics, adjacent spend. **Retired:** M-05, M-38, RATE-11, COMM-05 ([catalog](../ideation/02-opportunity-catalog.md#selection-and-status-v2)) | Reversible |
| **D5** | **Pilot partner and Wizard-of-Oz permission** | Internal team; a friendly customer | A friendly customer with a named executive sponsor and security contact (**K5** applies: no sponsor and read access by week 4 → publish the research as a guide) | Reversible |
| **D6** 🚪 | **Repository visibility** | Private now → public at Phase 8, or earlier | **Stay private** until the guardrail charter and the internal release process check are done | **Public release is a one-way door** |
| **D7** | **Go-to-market wedge** | A read-only *Assess* report · **Assess-and-Close** | **Assess-and-Close:** two usage-truth detectors, an ownership map and a *human-delivered* last mile on 10–15 cases, verified at +30 and +60 days. An Assess report on its own recreates the failure the thesis attacks — a list nobody acts on — and competes with free assessments | Reversible |
| **D8** | **Adjacent spend scopes** (SaaS/GitHub/M365) | In vision / later / never | **Parked** with a trigger (the Azure loop is proven and a sponsor asks); keep the architecture open | Reversible |
| **D9** | **Multi-cloud stance** | Azure-only / visibility via open cost format later | **Azure-only; M-38 is retired** because it conflicts with *Microsoft technology only* (F2). Re-open only if F2 changes | Reversible |
| **D10** | **People and time** | Who else is on the project; hours per week | Needed to sequence Phases 0.5–3; **K7** freezes the project below five hours a week for six weeks | Reversible |
| **D11** | **Stop criteria thresholds** | The strawman K1–K7 in §4, or your own numbers | **Pre-register in Phase 0.5** with a named decider and dates; Finance and security co-own K2 and K3 | Reversible |
| **D12** | **Voice/avatar stance** | Explore / defer | Defer until text channels are proven; AI disclosure rules first | Reversible |
| **D13** 🚪 | **Employer approval, OSPO and IP stance; project home** | Personal project with approval · a Microsoft GitHub organisation · an internal accelerator only | **Assumed: the operator handles it outside this package** — it is not an ideation question, and nothing is published while the repository is private (D6). If it proves not approvable, **K6** falls back to an internal accelerator | Hard to reverse once published |
| **D14** 🚪 | **Are commitment purchases permanently excluded from L3–L5?** | Yes, permanently · revisit later with a signed-manifest design | **Yes.** We only ever *prepare* a manifest; the authorised buyer signs each transaction ([invariant 16](../ideation/08-trust-safety-and-guardrail-topics.md#4-candidate-safety-invariants-non-negotiables-to-ratify)) | Loosening later is possible; tightening after an incident is not |
| **D15** | **Default orphan custodian** | Subscription owner · platform team · FinOps lead | The platform team, with the FinOps lead as backstop. **Appointed and reviewed by someone other than the custodian**; retirement always needs a second authority; a scope with no custodian is itself a governance finding ([07 §7](../ideation/07-ownership-and-organization.md)) | Reversible |
| **D16** 🚪 | **Trust root and emergency revocation** for playbooks, models, prompts and evaluators | Maintainers only · maintainers plus the customer's FinOps lead and security · the customer alone | The **governed-release approver set** (maintainers plus the customer's FinOps lead and security) owns the trust root. **It must be decided before any behaviour-affecting artefact ships, in any release.** It needs: key custody, an approval quorum, separation from Warden administration, signed provenance, emergency revocation, a pinned rollback release and an independent audit of release state ([04 §3.4](../ideation/04-agent-crew.md), invariant 4) | Hard to change once artefacts are signed |
| **D17** 🚪 | **Who signs the Phase-0.5 exception** (query audit on pilot workspaces, a handful of real messages)? | The sponsor and the customer's security contact · the data owner and security · the operator alone | **The data owner and the customer's security contact**, on the one-page outreach note and the instrumentation approval (scope, cost cap, end date, deletion rule). The operator may not sign it alone — it touches a customer's data and people. *A lab-only demonstration on the Waste Lab has no customer data or people to protect: there the operator, as data owner, approves the instrumentation.* | Reversible once removed; the audit records already ingested persist |
| **D18** | **Who certifies a resource class as safe-to-pause** for the cost brake? | The service owner alone · the service owner plus security · an independent reliability or risk function | **The service owner plus security**, recorded as an expiring contract bound to specific assets; the telemetry that may trigger the brake must come from a separately administered source ([06 §3 item 11](../ideation/06-closed-loop-actions-and-autonomy.md)). Until a class is certified, nothing pauses automatically | Reversible |

---

## 4. Kill criteria (strawman — pre-register in Phase 0.5)

The v1 plan named stop criteria three times and never quantified them, gave them no decider and no date. These are the strawman fixes, to be adjusted in decision **D11** and **dated before any pilot data is seen**.

| # | Trigger | Response | Decider | Checked |
|---|---|---|---|---|
| **K1** | Fewer than 30% of well-evidenced cases decided within 14 days, and the cause is incentives (not message quality) | Pivot to policy-first automation | Operator with the sponsor | Phase 2 readout |
| **K2** | Any severity-1 incident attributable to the crew, or two or more rollbacks per 100 actions | Freeze writes; back to L1 | FinOps lead (kill switch), then Operator | Weekly regret report |
| **K3** | Platform cost above 30% of verified run-rate savings at pilot month 6, or no Finance-reconciled saving by month 4 | Shrink scope | Operator with Finance | Months 4 and 6 |
| **K4** | First-party tooling ships owner-routed, owner-approved execution for three or more Release-1 playbooks | Contribute-only | Operator | Quarterly re-check |
| **K5** | No sponsor and no read access by week 4 | Publish the research as a guide | Operator | Week 4 |
| **K6** | No approved publication path by week 6 | Internal accelerator; revisit open source | Operator | Week 6 |
| **K7** | Fewer than five hours a week for six weeks (adjust to D10) | Freeze | Operator | Week 6, then monthly |

*The thresholds are the strategy reviewer's judgement, not verified facts ([reviews/round-1/03](../reviews/round-1/03-duck-strategy.md)); the operator sets the final numbers.*

---

## 5. First-party overlap — ride, copy, build, contribute

[research/06](../research/06-first-party-teardown.md) tears down Advisor, the Optimization Agent and MCP tools, Cost Management, FinOps toolkit v15, Defender governance rules, the SRE Agent, Sentinel SOC optimization and Azure Monitor guidance. Read honestly: every *plumbing* capability now exists somewhere in Microsoft's stack (owner→manager email, approve-then-execute, Teams delivery, unused-table detection). What we did **not find** is the **combination for cost** — owner-resolved, owner-approved, evidence-bearing, executed and *verified* — plus usage-truth detectors that work outside Sentinel and beyond 30 days, and an open evaluation harness.

| Position | Assets | What we do |
|---|---|---|
| **Ride** | Advisor and `optimization` data; Cost Management and FOCUS exports; FinOps hubs and alerts; the SRE Agent as an optional execution runtime | Consume outputs; do not rebuild reporting |
| **Copy the proven pattern** | Defender governance rules (tag → owner → due date → manager nudge) | Replicate for cost, with the guardrails that pattern lacks (consent, escalation rules, no named-person pressure) |
| **Build** | Usage-truth playbooks; the cost-domain Owner Graph and owner-as-approver gate; the verified-savings ledger; the Waste Lab | Validate each with ground truth before building plumbing |
| **Contribute** | Detector specs, Waste Lab scenarios, ledger counting rules | Offer upstream to the FinOps toolkit (MIT) |
| **Accept obsolescence** | Teams plumbing, scheduling, generic approvals | The moat is time and validated content, not plumbing |

**Trigger:** K4. **Re-check quarterly** with the checklist in [research/06 §5](../research/06-first-party-teardown.md), and add a dated row for every change. A **third-party** equivalent (see [research/02](../research/02-third-party-and-oss-landscape.md)) does not trigger K4 — we cannot contribute to a proprietary product — but is logged at the same re-check (risk R27).

### Build, ride or contribute — the decision per Release-1 play

K4 is reactive. Before any implementation investment, the Phase-0.5 memo records an explicit call for each Release-1 play, and Phase 5 re-confirms it before architecture. The default positions, with the overlap that drives them:

| Release-1 play | First-party / OSS overlap | Default position | What would change it |
|---|---|---|---|
| **Owner Graph** | Defender governance rules (tag → owner → weekly mail, manager summary; security recommendations; needs Defender CSPM) | **Build** the cost-domain graph (directory, history, conversation); **copy the pattern** | Defender extends owner routing to cost recommendations |
| **Log usefulness** | Sentinel SOC optimization (Sentinel workspaces, 30-day window, security-scoped) | **Build** for non-Sentinel workspaces; **ride** SOC optimization for Sentinel ones; **contribute** detector specs and Waste Lab scenarios to the FinOps toolkit | A first-party usage-based table-usefulness verdict outside Sentinel |
| **P2S right-sizing** | FinOps toolkit alerts cover idle Application Gateways and idle public IPs — nothing for P2S scale units | **Ride** any detection that appears; **build** the banded lookup and the consent-gated execution; **contribute** the lookup as an open data file | The toolkit or Advisor ships a P2S recommendation |
| **Orphans and Advisor closure** | Advisor cost recommendations; toolkit alerts; the SRE Agent as an optional execution runtime (admin approval only) | **Ride** detection; **build** owner routing, authority-checked approval and verification | The SRE Agent or Advisor ships owner-approved execution for these classes (K4) |
| **PTU utilisation** | Azure Monitor metrics and Foundry billing views | **Build** the advice rule (cheap); contribute upstream if it generalises | A first-party PTU right-sizing recommendation |

---

## 6. Naming candidates (placeholder — the rename decision is D1)

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

> **Trademark note (review round 1):** the strategy reviewer read Microsoft's trademark guidelines on 2026-10-30; they say many uses of Microsoft marks "require a license first". The rule for *third-party project names that contain "Azure"* was **not found and stays unverified** — ask OSPO. Microsoft's own FinOps project does not use "Azure" in its name. Renaming while the repository is private costs nothing.

---

## 7. Open questions (not yet decisions)

1. Which **customers or internal teams** can host the Wizard-of-Oz pilot, and who approves outreach?
2. Which **languages** matter first (EN/NL/DE/FR)?
3. Do we need **non-production sandbox subscriptions** for the Waste Lab and the slices? Who pays?
4. What do **Finance** and **security** need to see to say yes to write access?
5. Is there an existing **internal community** (CSAs, FinOps practitioners) to co-design with?
6. How do we handle **customers in regulated sectors** (financial services, public sector) from day one?
7. What is the **support model** after launch (community, partner, none)?
8. Do we want an **advisory board** (customers, Microsoft engineers, FinOps Foundation members)?
9. How do we position vs. first-party offerings in communications?
10. What is the plan if a first-party feature makes a slice obsolete? (K4 gives the first answer: contribute-only.)
11. What is the **approved publication path** for a Microsoft employee's open-source project (OSPO, IP, trademark)? (A16, D13, K6) — *assumed handled by the operator before publication; not an ideation question.*
12. Which **cloud CoE** can host the one-hour "top-10 unfixed recommendations — and why" interview in Phase 0.5?
