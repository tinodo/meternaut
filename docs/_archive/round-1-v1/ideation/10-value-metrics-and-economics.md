# Value, Metrics & Economics — how we will know it works (and that it pays for itself)

> **Status:** Ideation v1 · **Date:** 2026-10-30 · Part of the [north-star vision](01-north-star-vision.md)
> **Scope guard:** definitions and shape of measurement. Targets are set in Phase 1–2 from pilot data; all example numbers are **illustrative**.

---

## 1. The scoreboard

### North-star metrics

| Metric | Definition | Why it is the one to watch |
|---|---|---|
| **Verified savings (run-rate, € / month)** | Recurring savings *proven against a counterfactual* and still holding | The only number Finance should repeat |
| **Time-to-decision** | Median hours from *detection* to a *human decision* | Measures the last mile directly (gaps 1–4) |
| **Action funnel conversion** | Identified → Engaged → Decided → Executed → Verified → Sustained | Shows *where* savings die |
| **Ownership coverage** | % of spend with a *Confirmed or Corroborated* owner | The prerequisite for everything else |
| **Regret rate** | Rollbacks + attributable incidents + boomerangs per 100 actions | The trust metric; must stay near zero |
| **Attention cost** | Asks per human per week, and the share rated *useful* | The guard against alert fatigue |
| **Platform ROI** | Verified savings ÷ total platform cost (AI + compute + data + people) | Integrity test: the tool must pay for itself |

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
**Verified savings ↔ regret rate** · **acceptance rate ↔ owner satisfaction** · **messages sent ↔ attention cost** · **savings claimed ↔ invoice reconciliation residual** · **cost down ↔ reliability/security posture regression** · **coverage ↔ ownership accuracy (confirmed, not inferred)**.

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

1. **One saving, one claim.** Attribution across Advisor, other tools, humans and agents is deduplicated; the first credible *executed* claim wins, others are recorded as *corroboration*.
2. **Counterfactual, not before/after.** Normalise for usage and seasonality (see [06](06-closed-loop-actions-and-autonomy.md) §7).
3. **Reconcile to the invoice.** Residuals are investigated, not ignored.
4. **Declare the evidence horizon** (how long we watched) and the **confidence band**.
5. **Time-box sustainment:** a saving becomes *Sustained* after a defined period (e.g. 90 days) without regression.
6. **Regret is reported in the same table** as savings.
7. **Independent verification:** the Auditor, not the Operator, writes the ledger.

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

If **verified savings < platform cost** for two consecutive quarters in a scope, the Warden recommends *reducing scope or autonomy* — and says so in the ledger.

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

---

## 7. Candidate OKRs per stage (to be set from pilot data)

| Stage | Objective | Example key results |
|---|---|---|
| **Assess** | Earn the right to advise | Waste X-ray delivered in ≤2 days; ownership coverage map; Time-Machine replay accepted by Finance |
| **Advise** | Close attention/context gaps | Median time-to-decision ↓ x%; ≥ y% of messages rated useful; ownership coverage ↑ |
| **Assist** | Close the effort gap | ≥ z% of approved actions executed within window; regret rate < ε |
| **Automate** | Close the scale gap | ≥ n action classes at L3/L4 with zero unreconciled regret; platform ROI ≥ target |

---

## 8. Pilot success criteria (strawman)

1. **Owners act** — decision rate on delivered cases above a pre-agreed threshold, with *useful* ratings.
2. **No harm** — zero severity-1 incidents attributable to the crew; regret rate below the agreed bound.
3. **Money is real** — a sample of verified savings reconciles to the invoice, sign-off by Finance.
4. **Attention respected** — median asks per owner-week within budget; opt-out low.
5. **It pays for itself** — platform ROI positive within the pilot scope.
6. **Trust** — security and compliance reviewers can reproduce any decision from the audit trail.

Next: the press release from the future → [11](11-working-backwards-pr-faq.md).
