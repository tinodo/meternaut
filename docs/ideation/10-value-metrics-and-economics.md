# Value, Metrics & Economics — how we will know it works (and that it pays for itself)

> **Status:** Ideation **v2** (revised after rubber-duck round 1; v1 archived [here](../_archive/round-1-v1/ideation/10-value-metrics-and-economics.md)) · **Date:** 2026-10-30 · Part of the [north-star vision](01-north-star-vision.md)
> **Scope guard:** definitions and shape of measurement. Targets are set in Phase 1–2 from pilot data; all example numbers are **illustrative**.

---

## 1. The scoreboard

### North-star metrics

| Metric | Definition | Why it is the one to watch |
|---|---|---|
| **Verified savings (run-rate, € / month)** | Recurring savings *proven against a counterfactual* and still holding | The only *gross* number Finance should repeat |
| **Net realised value (€ / month)** | Verified, sustained savings **minus** the measurable cost of regret (incident cost, rollback effort, savings lost to boomerangs, human time) **minus** platform cost | The honest number: what is left after the programme has paid for its own mistakes and its own running costs |
| **Time-to-decision** | Median hours from *detection* to a *human decision* — a case that expires or is parked counts as **undecided** (silence is never a decision) | Measures the last mile directly (gaps 1–4) |
| **Action funnel conversion** | Identified → Engaged → Decided → Executed → Verified → Sustained | Shows *where* savings die |
| **Ownership coverage** | % of spend with a *Confirmed or Corroborated* owner | The prerequisite for everything else |
| **Regret rate** | Rollbacks + attributable incidents + boomerangs per 100 actions | The trust metric; must stay near zero |
| **Attention cost** | Asks per human per week, and the share rated *useful* | The guard against alert fatigue |
| **Platform ROI** | Verified savings ÷ total platform cost (AI + compute + data + people) | Integrity test: the tool must pay for itself |

**Reporting unit.** Every metric is reported per **team, service or role** — never per individual by default. Individual-level views exist only for a person's own desk and for audit attribution ([07 §10 and §12](07-ownership-and-organization.md)).

### Supporting metrics

| Area | Metrics |
|---|---|
| **Waste** | Waste ratio (idle + over-provisioned spend ÷ total); dark-spend share; orphan count and age |
| **Rate optimisation** | Commitment coverage; utilisation; effective savings rate; orphaned commitments |
| **Quality** | Case precision (approved ÷ proposed); false-positive rate; Challenger veto rate and later regret rate of passed cases; confidence calibration error |
| **Humans** | Acceptance rate by action class; defer/decline reasons; owner satisfaction; "talk to a human" rate; opt-out rate |
| **Safety** | Gate refusals; stale-approval catches; rollbacks; incidents correlated with actions; kill-switch drills passed |
| **Hygiene** | Tag coverage and accuracy; exception expiry compliance; attestation freshness |
| **Forecast** | Forecast accuracy; budget variance; commitment burn-down accuracy |
| **Speed** | Detection-to-first-message; approval-to-execution; execution duration |
| **Learning** | Playbooks authored/approved; evaluation score trend; calibration trend |

### Counter-metrics (anti-gaming)

Every headline metric has a partner that would reveal gaming:
**Verified savings ↔ regret rate** · **verified savings ↔ net realised value** · **acceptance rate ↔ owner satisfaction** · **time-to-decision ↔ regret of fast decisions** · **messages sent ↔ attention cost** · **savings claimed ↔ invoice reconciliation residual** · **cost down ↔ reliability/security posture regression** · **coverage ↔ ownership accuracy (confirmed, not inferred)**.

---

## 2. The savings ledger — counting rules

The Savings Ledger is the single, deduplicated, audit-grade record. Its integrity *is* the product's credibility with Finance.

### 2.1 States

`Projected → Approved → Executed → Verified → Sustained` plus `Regressed`, `Rolled back`, `Expired`, `Superseded`.
Headline numbers include **Verified** and **Sustained** only.

### 2.2 Categories (never blended in one headline)

| Category | Meaning | Example |
|---|---|---|
| **Run-rate reduction** | Recurring lower spend for the same service level | Gateway scaled down; logs filtered |
| **Rate improvement** | Same usage, cheaper price | Commitment, Hybrid Benefit, scope fix |
| **One-time recovery** | Non-recurring | Deleting abandoned data; credits |
| **Cost avoidance** | Spend that *would have* happened | A deployment-time gate; a prevented runaway |
| **Risk-adjusted expected value** | For projections only | Probability-weighted savings |

### 2.3 Rules

1. **One saving, one financial outcome — with provenance kept.** The *amount* is counted once, whether Advisor, another tool, a human or an agent surfaced it (no double counting). But **multi-touch provenance is recorded**: every contributing signal, tool and person is on the ledger line, so credit is attributable without being raced for.
2. **Counterfactual, not before/after.** Normalise for usage and seasonality (see [06](06-closed-loop-actions-and-autonomy.md) §7).
3. **Reconcile to the invoice.** Residuals are investigated, not ignored.
4. **Declare the evidence horizon** (how long we watched) and the **confidence band**.
5. **Time-box sustainment:** a saving becomes *Sustained* after a defined period (e.g. 90 days) without regression.
6. **Regret is reported in the same table** as savings.
7. **Independent verification:** the Auditor, not the Operator, writes the ledger.
8. **Collection-reducing savings carry their cost.** A saving from an R3-Data action (a log filter, a shorter retention) is booked with what is **no longer collected** and the regret signals being watched (for example "I searched for X and found nothing") — never as a clean number.
9. **Net realised value is shown beside gross verified savings** (see §1), so Finance sees both what was saved and what it cost to save it.
10. **Only the incremental effect is claimed.** Where owners would have acted anyway (a matched control or the historical action rate says so), the ledger counts the *difference* the platform made, not the whole saving.

---

## 3. The funnel (illustrative)

```
Identified   1,000 cases  ████████████████████████████████████████
Challenged     820        ████████████████████████████████
Owner-engaged  700        ████████████████████████████
Decided        520        █████████████████████
 ├ Approved    380        ███████████████
 ├ Deferred     90        ████
 └ Declined     50        ██
Executed       350        ██████████████
Verified       310        ████████████
Sustained (90d) 290       ███████████
```

Every drop is a *diagnosis*: between Identified and Challenged → noisy playbooks; Challenged and Engaged → ownership gap; Engaged and Decided → message quality/attention; Decided and Executed → effort/gating; Executed and Verified → measurement; Verified and Sustained → drift. **The funnel tells us what to build next.**

---

## 4. The economics of the platform itself

> **"Never spend €10 of AI to save €5."** The platform's cost is a first-class metric, watched by the Warden.

### 4.1 Cost components (conceptual)

| Component | Notes |
|---|---|
| **AI inference** | Tokens per case, per conversation, per verification; model choice per task |
| **Data access** | Queries against metrics/logs (querying logs can itself cost money), cost-data exports, inventory scans |
| **Orchestration & storage** | Long-running workflows, case/evidence stores, audit log retention |
| **Communication** | Messaging, voice, email delivery |
| **People** | FinOps lead, stewards, reviewers' time |

### 4.2 Economic triage

Before investing effort in a candidate, the Conductor estimates:

`expected value = P(owner acts) × expected saving × persistence` versus `cost to investigate + cost of human attention`.

Below the threshold → batch into a digest, handle by a policy envelope, or ignore. This is how we avoid spending €2 of analysis on a €5/month resource.

### 4.3 Unit costs we will track

€ per case · € per *decided* case · € per € *verified* · AI cost per conversation · payback period of the platform · marginal cost of one more subscription onboarded.

### 4.4 The honesty test

If **verified savings < platform cost** for two consecutive quarters in a scope, the Warden recommends *reducing scope or autonomy* — and says so in the ledger. The honesty test is hardened into explicit **kill criteria K1–K7** in [plan/01](../plan/01-assumptions-risks-decisions.md); K3 is the economic one (platform cost against verified, Finance-reconciled savings).

---

## 5. Benefits beyond euros

| Benefit | How we would notice |
|---|---|
| **Engineer time returned** | Fewer ad-hoc cost fire drills; hours of manual clean-up avoided |
| **Decision latency** | Median time-to-decision drops from weeks to days/hours |
| **Risk reduction** | Fewer unknown/unowned resources; fewer forgotten publicly reachable assets |
| **Audit readiness** | Decision log and evidence packs on demand |
| **Sustainability** | Estimated emissions avoided alongside euros |
| **Culture** | Voluntary participation; champions; qualitative feedback |
| **Learning** | Playbooks, patterns and calibration that outlast any one case |

---

## 6. Measurement challenges (and how we respect them)

| Challenge | Response |
|---|---|
| Seasonality and growth fake savings | Usage-normalised unit costs; control groups |
| Goodhart's law | Counter-metrics; rotate emphasis; qualitative review |
| Attribution fights | Deduplication rules; credit to owners, not to tools |
| Price changes mid-period | Constant-price comparisons plus a price-effect line |
| Commitments blur run-rate | Separate rate vs usage effects |
| Late-arriving cost data | Explicit data-latency windows before declaring *Verified* |
| Shared resources | Usage-based allocation; Diplomat-recorded agreements |
| Survivorship bias in feedback | Sample declined/deferred cases for review, not only approved ones |
| "Owners would have acted anyway" | Only the **incremental** effect is claimed: compare against a matched control group, a staggered (stepped) rollout, or the historical action rate — chosen *before* the pilot starts (§8) |
| Savings from actions that reduce what is collected | Booked with the information-loss attribute and watched regret signals (ledger rule 8) |

---

## 7. Candidate OKRs per stage (to be set from pilot data)

| Stage | Objective | Example key results |
|---|---|---|
| **Assess** | Earn the right to advise | Waste X-ray delivered in ≤2 days; ownership coverage map; Time-Machine replay accepted by Finance |
| **Advise** | Close attention/context gaps | Median time-to-decision ↓ x%; ≥ y% of messages rated useful; ownership coverage ↑ |
| **Assist** | Close the effort gap | ≥ z% of approved actions executed within window; regret rate < ε |
| **Automate** | Close the scale gap | ≥ n action classes at L3/L4 with zero unreconciled regret; platform ROI ≥ target |

---

## 8. Pilot design and success criteria (strawman — to be pre-registered)

A pilot that is judged by the people who built it, with criteria chosen after the data arrives, proves nothing. The strawman therefore has four parts:

**Pre-registration.** Before any data is seen, write down and date: the hypotheses, the metrics and thresholds, the exclusions, the analysis method and the stop rules. Changes after the start are recorded as *deviations*, not silently absorbed.

**A comparison condition.** Choose one *before* the pilot: a **matched set of teams or subscriptions** that keep the status quo (Cost Management and Advisor alone), or a **stepped rollout** in which each team is its own control. The claim is the **incremental** effect over the comparison, never the absolute saving ([§6](#6-measurement-challenges-and-how-we-respect-them), ledger rule 10).

**Independent judges.** Finance reconciles the money; security and compliance reproduce decisions from the audit trail; a reviewer outside the build team signs the readout.

**Stop rules.** The kill criteria **K1–K7** in [plan/01](../plan/01-assumptions-risks-decisions.md) apply from day one.

**Success criteria (each with a pre-agreed threshold and the comparison condition):**

1. **Owners act** — decision rate on well-evidenced cases within 14 days, versus the comparison condition, with *useful* ratings. Silence counts as *undecided*.
2. **No harm** — zero severity-1 incidents attributable to the crew; regret rate below the agreed bound.
3. **Money is real** — a sample of verified savings reconciles to the invoice, with Finance's sign-off.
4. **Attention respected** — median asks per owner-week within budget; opt-out low.
5. **It pays for itself** — net realised value positive within the pilot scope.
6. **Trust** — security and compliance reviewers can reproduce any decision from the audit trail.

Next: the press release from the future → [11](11-working-backwards-pr-faq.md).
