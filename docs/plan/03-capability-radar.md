# Capability Radar & Spike Catalogue (non-binding)

> **Status:** Ideation **v2** (revised after rubber-duck round 1; v1 archived [here](../_archive/round-1-v1/plan/03-capability-radar.md)) · **Date:** 2026-10-30 · Part of the [follow-up plan](00-follow-up-plan.md) (Phase 4 input)
> **This is a radar, not a design.** It lists the Microsoft building blocks we will *evaluate*, and the time-boxed spikes that will tell us what is feasible. Ideation deliberately ignored feasibility; this is where feasibility gets its turn. Product names are as understood on 2026-10-30 and **must be re-verified at Phase 4** — several of these products are evolving or being renamed quickly (verified state of the Azure-native cost tooling is in [research/01](../research/01-azure-native-landscape.md)).

---

## 1. The radar — what to evaluate and why

| # | Building block (Microsoft) | Why it is on the radar | Core question | Links |
|---|---|---|---|---|
| 1 | **Microsoft Foundry** (agent service, models, evaluations, tracing, content/safety controls) | Home for the crew and its evaluation harness | Can it run durable, multi-agent, wait-state workflows with evaluations, tracing and cost controls? | A11, A12, G5 |
| 2 | **Agent orchestration SDKs/frameworks** from Microsoft | Role composition, tools, handoffs | Which pattern best fits "workflow, not chat" and separation of duties? | A11 |
| 3 | **Durable workflow runtimes** (e.g. durable functions, logic-app workflows) | Cases last days/weeks with timers and escalations | Reliability, cost and observability of long waits | A11 |
| 4 | **Microsoft Teams** (adaptive cards, bots, actionable messages, meeting participation) | The primary conversation channel | Can an authenticated, user-bound approval be carried safely? Mobile? Tenant policies? | A3, G7 |
| 5 | **Outlook / Exchange** | Digests, formal approvals, fallback | Actionable messages vs. signed deep link; spoofing resistance | A3, G7-05 |
| 6 | **Microsoft Graph & Entra ID** (users, managers, groups, presence, out-of-office, lifecycle events, access reviews, agent identities) | "Follow the directory"; agent identity | Which least-privilege reads? JML triggers? Agent identity model? | A17, G2 |
| 7 | **Cost Management APIs and exports** (incl. the open cost format), **Advisor**, **Resource Graph**, **Azure Monitor** (metrics, Logs/KQL, query audit), **Activity Log** | Sensing | Coverage, latency, throttling, retention, scopes (EA/MCA/CSP) | A6, A19 |
| 8 | **Azure Policy, locks, RBAC, Privileged Identity Management** | Preventive guardrails; least privilege | Can the policy envelope be enforced deterministically at the Azure layer? | G2, G3 |
| 9 | **Azure Communication Services** (SMS, voice, email) and **Azure Speech** (voice, avatar) | Urgent channels; meeting/voice moonshots | Consent, deliverability in the EU, voice confirmation flows | M-03/04, G7 |
| 10 | **GitHub / Azure DevOps** | Fix-at-source pull requests, CODEOWNERS, repo-based ownership | PR automation with cost deltas; reviewers from CODEOWNERS | [06 §4](../ideation/06-closed-loop-actions-and-autonomy.md) |
| 11 | **Microsoft Fabric / Data Explorer / Log Analytics / Power BI** | Analytic store for the ledger, usage analysis, reports | Which store for which data; cost of storing evidence | A12 |
| 12 | **Power Platform** (approvals, low-code, Copilot Studio) | Alternative approval/UX layer; citizen-maker owners | Role of low-code vs. code for the owner-facing surface | — |
| 13 | **Defender for Cloud / Sentinel** | Security-tool economics; protected log sources; **Sentinel SOC optimization already covers unused tables/columns on Sentinel workspaces; Defender governance rules are the owner-routing pattern to copy** | Interplay and *protected-source* lists; where our log playbook starts and theirs ends | T14, [research/06](../research/06-first-party-teardown.md) |
| 14 | **Microsoft Purview** (labels, DLP) | Data classification respect | Can classification gate what agents read? | G4-07 |
| 15 | **API gateway for AI calls** | Budgeting, rate limits, observability for model calls | Denial-of-wallet protection; per-case cost attribution | G6-02 |
| 16 | **First-party agentic/optimisation offerings** (e.g. Azure Copilot agents, the Azure MCP Server, the Azure SRE Agent, the FinOps toolkit agent plugins) | Overlap and integration (A14); the SRE Agent as an *optional execution runtime* (ride) | Ride, copy, build or contribute? Re-check quarterly | A14, K4, [research/06](../research/06-first-party-teardown.md) |
| 17 | **Hosting options** (container, function, Kubernetes) | Where the platform runs | Decide *after* the spikes | — |
| 18 | **IaC and packaging** (Bicep/Terraform with verified modules; developer CLI) | Reference architecture, one-click deploy | WAF-aligned landing zone; "Deploy to Azure" experience | CAF/WAF |
| 19 | **Key Vault & managed identities** | Secrets and credentials | Agents never see secrets | G2-06 |
| 20 | **Chaos and load testing services** | Guardrail drills | Chaos experiments for kill switch, outages | G10 |

---

## 2. The spike catalogue (Phase 4)

Each spike: **1–3 days**, a written pass criterion, an owner, an outcome (**Green / Amber / Red**) and an ADR. *Guardrail-dependent* means we need the relevant [guardrail decision](02-guardrails-workplan.md) first.

**Changes after review round 1:** three spikes are **deferred** (S14, S15, S21), one is **folded into a slice** (S22 into slice S1), and one is **added** (S1b) — **19 active spikes**. S5 gains an audit-coverage canary, S7 a banded-capacity lookup, and S13 binds approvals to the exact artefact. The strawman **Release-1 critical path** is S1, S1b, S3, S4, S5, S7, S8, S10, S11, S12, S13, S16, S17, S19 and S20 (S2, S6, S9 and S18 support it).

| ID | Spike | Question | Pass criterion (strawman) | Guardrail-dependent |
|---|---|---|---|---|
| **S1** | Cost data coverage & latency | Per-resource cost, tags, commitment/benefit utilisation at the needed freshness and scale? | Daily data within an agreed lag; throttling budget fits N subscriptions; pilot's billing scope supported | — |
| **S1b** *(new)* | IaC detection and fix path | Can we tell whether a resource is IaC-managed (and by which repository and pipeline) so the fix goes **at the source** instead of a direct change the next deployment would revert (T11)? | ≥ an agreed % of seed-playbook resources correctly classified as IaC-managed or not; the target repository identified for the managed ones | G3 |
| **S2** | Advisor data access | Coverage, refresh cadence and dismissal-state sync for cost recommendations? | Recommendations retrievable programmatically; dismissal state readable/writable | — |
| **S3** | Inventory & topology | Can we build dependency edges (network, identity, configuration) with enough fidelity for blast radius? | ≥ agreed % of edges for the seed playbooks | — |
| **S4** | Metric availability for the seed playbooks | Is the *used* signal (e.g. P2S connection counts, capacity usage) available for long enough, at what granularity? | Required metrics for ≥ the evidence horizon, or a documented alternative | — |
| **S5** | Log usage signals | Is query auditing on? **Calibrate coverage per workspace with a canary query** — the documentation is inconsistent about what is recorded (hunting, Investigation Graph, Sentinel investigation clients) and scheduled alert executions are not logged. Can queries, alerts, workbooks and exports be mapped to tables? Which consumers are unobservable? | Table-level "last used by whom" with a **canary-measured** blind-spot list; Sentinel workspaces identified and excluded (covered by SOC optimization) | G4 |
| **S6** | Ingestion transformation dry-run & shadow | Can we measure *would-have-dropped* volume and replay existing queries/alerts against filtered data? | Shadow measurement within ±x% of actual filter effect; replay detects result changes | G3, G4 |
| **S7** | P2S gateway scale operation | **Banded capacity lookup:** throughput is linear (0.5 Gbps per unit) but connection capacity is banded (units 1–3 → 500, 4–6 → 1,000, 7–10 → 5,000, 11–20 → 10,000, then +10,000 per extra pair of instances). Is scaling online or disruptive; how long; how does rollback behave? | The lookup returns the smallest band that satisfies *both* connections and bandwidth plus headroom, and matches the current documentation; documented reconnect/downtime behaviour; safe window length; scripted rollback | G3 |
| **S8** | Teams actionable approvals | Authenticated, user-bound approvals; mobile; tenant policies; anti-phishing properties | Security review passes; approval bound to user and plan | G2, G7 |
| **S9** | Email approvals | Actionable message vs. signed deep link to an authenticated approval page | Spoofing-resistant design accepted by security | G7-05 |
| **S10** | Directory reads | Manager chain, delegates, presence, out-of-office, time zone, language, lifecycle events under least privilege | Required reads available with minimal scopes | G4, G2 |
| **S11** | Agent workflows | Durable, long-running, wait-state workflows with retries, evaluations and tracing | Cases survive restarts and multi-day waits; trace complete; cost per case measured | G10 |
| **S12** | Agent identities & RBAC | Per-role identities, JIT elevation, on-behalf-of vs self | Least-privilege model demonstrated; audit trail attributes every action | G2 |
| **S13** | IaC pull-request automation | Open PRs with cost delta, reviewers from CODEOWNERS. **Approval binds to the exact artefact** — tenant and resource IDs, source commit SHA, rendered plan digest, pipeline identity, target-state hash — so a rebase or re-render invalidates it | PR created with evidence and rollback; no auto-merge; a re-rendered or rebased change is rejected as stale | G3 |
| **S14** | SMS/voice — **deferred** | Deliverability, consent, EU constraints, voice confirmation flow | Meets consent and attention rules. *Re-open with the voice-brake idea ([M-04](../ideation/09-outer-rims-moonshots.md)) and decision D12* | G7 |
| **S15** | Meeting participant/avatar — **deferred** | Feasibility, latency, disclosure, recording consent | Likely *Defer*; document. *Re-open with M-03 (Review Room)* | G7, G12 |
| **S16** | Cost per case | Tokens/queries per playbook; model routing; caching | Cost per decided case below the economic-triage ceiling | G6 |
| **S17** | Model choice & data boundary | Model families, regions/data zones, retention and no-training settings, built-in safety controls | Meets the data-handling statement | G4, G5 |
| **S18** | Open-source release process | Required internal steps and timeline | Process documented; owner named | G11 |
| **S19** | Policy-envelope enforcement | Deterministic gating: where it lives, how it is tested | Gate cannot be bypassed by agents; tests pass | G1, G3 |
| **S20** | Waste Lab realism | Cheap, realistic synthetic estates with ground truth | Seeded cases detected/evaluated reproducibly | — |
| **S21** | Anomaly input — **deferred** | Consume native anomaly signals and correlate with changes? | Useful precision on a sample. *Re-open with the ANOM family and the cost brake* | — |
| **S22** | Fallback channels — **folded into slice S1** | Behaviour during chat or model outage | Degrades to advise; critical items still reach a human — tested inside the orphans slice | G10 |

**Spike hygiene:** time-boxed; documented as ADRs; outcomes feed Phase 5 and *change scope* if needed (a Red on a Release-1 playbook either re-scopes it or defers it with a recorded alternative).
