# Azure Cost in Action

> **AI-infused, agent-driven, human-in-the-loop Azure cost optimisation — from insight to outcome.**
> *Working title.* Status: **ideation v3.2** — both rubber-duck rounds applied ([round 1](docs/reviews/round-1/disposition.md), [round 2](docs/reviews/round-2/disposition.md)) plus two post-v3 audits ([§12](docs/reviews/round-2/disposition.md#12-post-v3-audit-v31)) · private repository · **MIT-licensed** ([LICENSE](LICENSE), decision D2). What changed: [CHANGELOG](CHANGELOG.md).
> **Stance:** an open-source demonstrator of what AI and Foundry agents can do inside governed workflows. Ideation only: every open decision carries an assumed default ([plan/01 §3](docs/plan/01-assumptions-risks-decisions.md#3-decisions-decided-or-assumed)) and nothing waits for an answer.
> **Project home:** GitHub `tinodo/meternaut` (private) · local working copy `<repo>` *(a private-repository convenience — scrub local paths before any publication, decision D6)*.

**New here? Read the [one-page overview](docs/ideation/00-one-page-overview.md) first** — the loop, the five Release-1 plays, who may decide what, and what "it worked" means, on one page.

Azure already tells you **what you spend** (Cost Management) and **what you could save** (Advisor). Almost nobody closes the loop: recommendations are addressed to nobody, owners are busy, trust is low, execution is manual, savings are never verified, and waste drifts back.

**Azure Cost in Action** explores a **crew of AI agents (Microsoft Foundry)** that studies how Azure is *actually used*, builds an evidence-backed **case** for every opportunity, finds the **owner** (and asks when it can't tell), meets them in **Teams or email** with a safe one-tap action, **executes** the approved change, **verifies** the saving, and keeps it from drifting back — with **humans in control** by construction.

> **Every euro spent on Azure has an owner and a reason. Every euro that doesn't becomes a decision — put to the right human, in the place they already work, with evidence and a safe one-tap fix — and then it is executed, proven, and kept from drifting back.**

```mermaid
flowchart LR
    A[Sense] --> B[Investigate] --> C[Challenge] --> D[Resolve owner] --> E[Engage]
    E --> F{Human decision}
    F -->|approve| G[Plan and simulate] --> H[Execute] --> I[Verify] --> J[Sustain] --> K[Learn] --> A
    F -->|defer, decline, delegate| L[Remember] --> K
```

---

## Release 1 at a glance (the first thing we would build — after a four-week kill-or-confirm sprint)

| # | Item | First mode |
|---|---|---|
| 1 | **Owner Graph** — know who owns what, and ask when unsure | Advise |
| 2 | **Log usefulness** (seed example 1) — which ingested data is never used, and how to filter it | **Advise only** (collection-reducing, so no writes) |
| 3 | **P2S gateway right-sizing** (seed example 2) — hidden scale units nobody uses | Assist (human-approved, in a window, with every affected business unit's consent; advise-only until the scale-operation spike is Green) |
| 4 | **Orphans and Advisor-recommendation closure** — the loop-proving vehicle: owner → decision → action → verified saving, starting from the recommendations nobody acts on | Advise → Assist via the resolved owner or a named custodian |
| 5 | **Provisioned-throughput utilisation** — a demand-pull candidate for AI workloads (conditional) | Advise |

Release 1 proves **AI-assisted closure** only; enrolled autonomy (L3/L4) is a separate, later hypothesis. Everything else is a *research-queue* hypothesis, *parked* with a re-open trigger, or *retired* with a reason ([catalog](docs/ideation/02-opportunity-catalog.md#selection-and-status-v2)). We would stop early if the [kill criteria K1–K7](docs/plan/01-assumptions-risks-decisions.md) say so.

---

## Founding constraints

Runs on **Microsoft platforms** (Azure / Power Platform / M365) · **Microsoft technology only** · compliant with the **Cloud Adoption Framework** and **Well-Architected Framework** · **open source** · **FULL AI** · **HITL** · **guardrails before code**.

---

## Start here

| # | Document | What it is |
|---|---|---|
| 0 | [One-page overview](docs/ideation/00-one-page-overview.md) | **The picture first**: the loop, the five Release-1 plays, who may decide what, five rules that never bend, what "it worked" means |
| 1 | [North-star vision](docs/ideation/01-north-star-vision.md) | **The entire idea**: problem, loop, Case, autonomy ladder, "FULL AI", principles, bets |
| 2 | [Opportunity catalog](docs/ideation/02-opportunity-catalog.md) | 305 ideas in 17 families, each with a *usage-truth* signal, decision gates and a status (selected / queue / parked / retired) |
| 3 | [Deep dives: the seed examples](docs/ideation/03-deep-dives-seed-examples.md) | Log Analytics ingestion usefulness and vWAN P2S capacity (banded), end-to-end; dark-spend archaeology |
| 4 | [The Crew](docs/ideation/04-agent-crew.md) | 20 agent roles, separation of duties, the independence profile, governed releases |
| 5 | [Human interaction concepts](docs/ideation/05-human-interaction-concepts.md) | Teams cards, email, SMS, voice, avatars, the private-first escalation ladder, conversation design, storyboards |
| 6 | [Closed loop, actions & autonomy](docs/ideation/06-closed-loop-actions-and-autonomy.md) | **The normative safety model:** the 14-step loop, one *derived* reversibility class per action (R0–R3, R3-Data), the enrolment key, affected-party consent, the transaction matrix, policy envelopes, verification |
| 7 | [Ownership & organisation](docs/ideation/07-ownership-and-organization.md) | Owner Graph, "follow the directory", the orphan custodian, control-plane tags, incentives, people-data ethics |
| 8 | [Trust, safety & the guardrail territory](docs/ideation/08-trust-safety-and-guardrail-topics.md) | 14 guardrail domains, 109 questions, 41 threats, 16 candidate invariants |
| 9 | [The outer rim](docs/ideation/09-outer-rims-moonshots.md) | 40 moonshots with their hard parts, smallest experiments and a decision status |
| 10 | [Value, metrics & economics](docs/ideation/10-value-metrics-and-economics.md) | Scoreboard, net realised value, savings-ledger rules, a pre-registered pilot design |
| 11 | [Press release from the future + tough FAQ](docs/ideation/11-working-backwards-pr-faq.md) | The idea stress-tested as a launch, with kill criteria K1–K7 |

### The plan
| Document | What it is |
|---|---|
| [Follow-up plan](docs/plan/00-follow-up-plan.md) | Phases 0.5–8, risk-based gates, Release 1, where every idea stands |
| [Assumptions, risks, decisions](docs/plan/01-assumptions-risks-decisions.md) | 26 assumptions, 27 risks, 18 decisions (D2 decided: MIT; the rest carry assumed defaults on a status board), kill criteria K1–K7, the first-party overlap map and the build/ride/contribute call per play |
| [Guardrails workplan](docs/plan/02-guardrails-workplan.md) | How the guardrail territory becomes enforceable, tested rules — control matrix and write-safety harness |
| [Capability radar & spikes](docs/plan/03-capability-radar.md) | Non-binding: what to evaluate and the 19 active feasibility spikes, ordered in three waves with a register for owners, results and ADRs |

### The research (primary-source, dated)
| Document | Topic |
|---|---|
| [01 Azure-native landscape](docs/research/01-azure-native-landscape.md) | Cost Management, Advisor, FinOps toolkit, Azure Copilot/agents — and where they stop |
| [02 Third-party & OSS landscape](docs/research/02-third-party-and-oss-landscape.md) | 22 commercial FinOps and AI-entrant products in four archetypes, the open-source gap, four independently verified claims — and what to borrow |
| [03 FinOps framework & evidence](docs/research/03-finops-framework-and-evidence.md) | FinOps Framework, FOCUS, State of FinOps, last-mile evidence, regulatory anchors |
| [04 Seed-example facts](docs/research/04-seed-example-facts.md) | Log Analytics and vWAN P2S mechanics (banded capacity); the capacity-unit pattern |
| [05 Cost traps & dark spend](docs/research/05-cost-traps-and-dark-spend.md) | A sourced catalog of 145 Azure cost traps, with a front-page "where to start" of ten |
| [06 First-party tear-down](docs/research/06-first-party-teardown.md) | Advisor, FinOps toolkit v15, Defender governance, SRE Agent, Sentinel SOC optimization — what exists, what we ride, copy, build or contribute |

### The reviews
| Document | Topic |
|---|---|
| [Round 1 — disposition of all 41 findings](docs/reviews/round-1/disposition.md) | Three independent reviewers (product, safety, strategy); raw reports preserved verbatim next to it |
| [Round 2 — disposition](docs/reviews/round-2/disposition.md) | Red team and disposition audit, a Learn-grounded fact-check, and a brief-compliance and consistency review of the v2 package — plus two post-v3 audits (§12) that found 17 more defects; raw reports in [the folder](docs/reviews/round-2/README.md) |
| [Archive of v1 and v2](docs/_archive/) | The frozen earlier packages ([v1](docs/_archive/round-1-v1/), [v2](docs/_archive/round-2-v2/); git tags `ideation-v1`, `ideation-v2`) |

### The tooling
| Tool | What it does |
|---|---|
| [`tools/check-docs.py`](tools/check-docs.py) | A standard-library-only lint — run `python tools/check-docs.py` before every commit. It checks links and anchors, the catalog (count, unique IDs, one class per row, R3-Data and transactions never above their ceilings, and word heuristics that flag a row reading like a transaction, reducing observability data or removing redundancy under a lower class), the counts quoted in this README, Mermaid labels and a list of phrases the reviews retired. `--self-test` proves it catches mislabelled rows |

---

## Scope guard

This repository is currently **ideation only**. Technology, feasibility and the *content* of guardrails are deliberately deferred to the [plan](docs/plan/00-follow-up-plan.md). Numbers in examples are illustrative unless a source is cited. Nothing here has touched a customer environment.

## Licence

[MIT](LICENSE) — code, documents and playbook specs alike.
