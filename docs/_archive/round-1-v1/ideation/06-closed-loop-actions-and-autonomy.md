# The Closed Loop — from decision to action to proof

> **Status:** Ideation v1 · **Date:** 2026-10-30 · Part of the [north-star vision](01-north-star-vision.md)
> **Scope guard:** the *shape* of safe automation, not its implementation. Thresholds and policies shown are **candidates to be ratified** in the [guardrails workplan](../plan/02-guardrails-workplan.md).

---

## 1. The loop, step by step

| # | Step | AI's job | Human's job | Artifact | Typical failure |
|---|---|---|---|---|---|
| 1 | **Sense** | Notice candidates in cost, usage, topology, context; run playbooks and open-ended curiosity | — | Candidate signal | Alert flood; chasing low-value noise |
| 2 | **Investigate** | Build the case: evidence, seasonality, alternatives, deterministic savings | — | Case file | Evidence horizon too short; hidden consumers |
| 3 | **Challenge** | Refute it: pre-mortem, locks, DR roles, compliance flags | — | Challenge verdict | Correlated blind spots with the Analyst |
| 4 | **Resolve owner** | Combine directory, tags, history; interview when unsure | Confirm or correct ownership | Owner Graph edge | Stale/wrong owner |
| 5 | **Engage** | Right channel, moment, language, tone; handle replies | Read and respond | Message / card / call | Fatigue; mis-timed ask |
| 6 | **Decide** | Offer options with trade-offs; accept free-text negotiation | **Decide** (approve / defer / decline / delegate) | Decision record | Approval by someone without authority |
| 7 | **Plan** | Convert the decision to a precise, reversible plan | Review the preview if desired | Plan (bound to approval) | Plan broader than the approval |
| 8 | **Simulate** | What-if, dry-run, shadow evaluation, replay | — | Simulation report | Simulation ≠ reality |
| 9 | **Gate** | Deterministic policy check; AI explains refusals | Resolve refusals | Gate verdict | Gates too lax, or too strict to be useful |
| 10 | **Execute** | Canary → staged rollout; watch SLOs; auto-rollback | Can pause/undo | Execution record + rollback bundle | Partial failure; race with human change |
| 11 | **Verify** | Counterfactual savings; regret watch; invoice reconciliation | Audit sample | Ledger entry | Seasonality mistaken for savings |
| 12 | **Sustain** | Drift guard; fix-at-source; regression alerts | Fix upstream where needed | Drift events | IaC silently reverts the change |
| 13 | **Remember** | Store context, exceptions (with expiry), preferences | Correct memory | Estate Memory | Memory poisoning |
| 14 | **Learn** | Calibrate confidence, tune thresholds, propose playbooks | Approve playbook changes | Evaluation deltas | Overfitting to loud owners |

---

## 2. The action vocabulary (the verbs)

| Verb | Meaning | Examples |
|---|---|---|
| **Eliminate** | Remove what is not needed | Delete unattached disks, idle gateways, abandoned environments |
| **Pause / Schedule** | Run only when needed | Dev/test sleep, scale-to-zero, calendar-based scaling |
| **Resize / Re-tier** | Match capacity to use | VM/DB SKU, **gateway scale units**, cache, search, storage tier |
| **Re-plan** | Change the pricing model | Reservations, savings plans, Hybrid Benefit, spot, commitment scope |
| **Re-configure** | Change behaviour, not size | **Log ingestion filters**, retention, sampling, lifecycle rules |
| **Re-place** | Move to where it is cheaper | Region, zone redundancy, network path, data co-location |
| **Consolidate** | Merge duplicates | Many small databases → elastic pool; many workspaces → fewer |
| **Modernise** | Change the architecture | VM → PaaS, newer-generation or ARM-based SKUs |
| **Govern** | Prevent recurrence | Tags, policy, budgets, expiry dates |
| **Educate** | Change habits | Nudges in pull requests, design-review hints |
| **Negotiate** | Commercial levers | Renewal evidence packs, commitment strategy |
| **Prevent** | Shift left | Cost delta in pull requests; deployment-time estimates |

### Reversibility classes

| Class | Definition | Examples |
|---|---|---|
| **R0** | Trivially reversible, metadata only | Tags, schedules, alert routing, budgets |
| **R1** | Reversible configuration change, state preserved | Scale up/down, SKU change within family, pause/stop with state retained |
| **R2** | Reversible within a recovery window | Snapshot-then-delete, soft-delete, quarantine-then-delete |
| **R3** | Irreversible or *economically* irreversible | Permanent deletion without backup, **dropping log data at ingestion**, shortening retention, reducing redundancy (the lost copy is gone), releasing a static IP address (it may sit in a partner's allow-list), commitment purchases (exchange/refund is limited — to verify per [research/01](../research/01-azure-native-landscape.md)) |

> **Why R3 matters for the log example:** a filter that drops rows at ingestion is irreversible for the dropped data. The safety net is a **shadow period** and an optional **short-lived cheap copy** (see [03](03-deep-dives-seed-examples.md)).

### Candidate default autonomy by risk (to be ratified)

| Reversibility | Environment | Blast radius | Default ceiling | Who approves |
|---|---|---|---|---|
| R0 | any | isolated | **L4** policy autopilot | Policy / owner opted in |
| R1 | non-prod | isolated | **L3** veto window | Owner (can veto) |
| R1 | prod | isolated | **L2** assist | Owner |
| R2 | non-prod | isolated | **L3** | Owner (can veto) |
| R2 | prod | isolated or shared | **L2** | Owner **+ all affected parties** if shared |
| R3 | any | any | **L1–L2, two-key** | Owner **+** FinOps lead (**+** Finance for purchases) |
| any | regulated / critical-tagged | any | **L1 advise only** unless a recorded exception | Owner + risk/compliance |

---

## 3. The safe-change toolkit

1. **Approvals bind to a Plan, not to a vibe.** An approval references a specific Plan version and its **preconditions** (configuration hash, utilisation envelope, price). If the world drifts beyond tolerance before execution, the approval is **stale** and the owner is asked again.
2. **Authority check.** The person who taps *Approve* must hold authority over the target (e.g. the right role on that resource). Otherwise the system refuses and routes to someone who does. *Chat must not become privilege escalation.*
3. **Scream-test ladder** for "probably unused" things (instead of deleting on a hunch):

   | Rung | Action | What we watch | Undo |
   |---|---|---|---|
   | 1 | Label and notify likely parties | Replies, complaints | Remove label |
   | 2 | Restrict (e.g. deny new connections) | Failed-connection signals, health probes | Lift restriction |
   | 3 | Stop / deallocate | Anything that breaks | Start |
   | 4 | Snapshot / back up | Backup proof | Restore |
   | 5 | Wait, with a visible countdown | Silence is evidence, not proof | Restore from backup |
   | 6 | Delete (R2 → protected by the backup) | — | Restore within window |

4. **Shadow mode, dry-run, canary, staging.**
   *Shadow* (what *would* I have done, scored against what humans did) → *dry-run / what-if* → *canary* (one resource, one region, one environment) → *staged* (dev → test → prod) → **SLO watch with auto-rollback**.
5. **Change windows and freezes.** Respect freeze calendars (month-end close, sales peaks, release trains) and the declared-incident state: **no changes in an affected scope during an incident**, except a pre-approved *cost brake*.
6. **Locks, legal holds, protected tags** are hard stops, not suggestions.
7. **Rate limits / blast limiter.** Max concurrent changes per subscription per hour; stop-the-line if failure rate crosses a threshold.
8. **Idempotency and concurrency.** Steps are idempotent; the plan checks it is acting on the same configuration it analysed; detect in-flight human edits.
9. **Two-key for R3.** Two different humans (owner plus FinOps/Finance) approve any irreversible or economically irreversible action.
10. **Rollback bundle** generated *before* execution: pre-state, exact reverse operation, verification steps, owner of the rollback.

---

## 4. Action as code — fix it at the source

If the resource is defined in infrastructure-as-code, a portal-side change will be **reverted by the next deployment** (and will show up as drift). So:

| Situation | The fix is… |
|---|---|
| Resource is IaC-managed | A **pull request** to the owning repo (CODEOWNERS reviewers), carrying the cost delta, the evidence and the rollback; after merge, the Auditor verifies |
| Resource is not IaC-managed | A direct change by the Operator, recorded with a **drift note** so the next IaC adoption captures it |
| Pipeline will redeploy the old value | Raise a **source fix** *and* a temporary direct change, linked |
| The waste is created by *code* (e.g. a verbose log statement, a polling trigger) | A **code-level pull request** — see [09](09-outer-rims-moonshots.md) |

This also makes *the repository* the place where owners already review changes — a natural channel for the Herald.

---

## 5. From enterprise change management to policy envelopes

Large organisations already know *standard changes*: pre-approved, low-risk, repeatable. Our **policy envelope** is exactly that, expressed so agents can act within it:

```yaml
# Illustrative policy envelope - NOT a final schema
name: dev-sleep-schedule
version: 3
approved_by: [finops-lead, platform-owner]
ratified_on: 2026-11-15
expires_on: 2027-05-15
action_class: pause-schedule
scope:
  subscriptions: [sub-dev-*]
  require_tags: { env: dev }
  exclude_tags: { cost-exempt: true }
preconditions:
  - no_resource_lock
  - not_in_freeze_window
  - owner_resolved: confirmed
limits:
  max_value_per_resource_per_month_eur: 500
  max_changes_per_hour: 20
reversibility: R1
windows: ["Mon-Fri 20:00-07:00 local", "Sat-Sun all day"]
verification: [cost_delta, no_incident_within_72h]
on_regret: downgrade_to_L2
review_cadence_days: 90
```

The envelope is **human-authored, versioned, expiring and reviewable**. The agents can *propose* envelopes (from observed approvals: "you approved this 31 times with no regret — want a policy?") but never ratify them.

---

## 6. Commitments (the Buyer's workflow)

Reservations and savings plans are different animals: large, long, and only partially reversible.

1. **Portfolio view first:** coverage, utilisation, scope, expiry, what-if on steady-state baselines (excluding things the crew is about to shrink — *sequence matters: right-size first, then commit*).
2. **Risk budget** set by Finance: maximum commitment as % of baseline, term ladder (e.g. staggered terms), cooling-off periods, minimum utilisation target.
3. **Staged purchases** instead of one big bet; **scope optimisation** (a free-saving class) before new purchases.
4. **Two-key** (or three-key above a threshold): owner of the workload + FinOps lead (+ Finance).
5. **Post-purchase watch:** utilisation, orphaned commitments after SKU changes, exchange/refund options, expiry planning.
6. **Regret analysis:** back-test decisions against what actually ran.

---

## 7. Verification — savings you can take to Finance

### 7.1 Savings states (the ledger's vocabulary)

`Projected → Approved → Executed → Verified → Sustained` (and `Regressed`, `Rolled back`, `Expired`).

Only **Verified** and **Sustained** appear in headline numbers. Projected savings are labelled *projected* everywhere.

### 7.2 Methods (concept)

| Method | Use |
|---|---|
| **Before/after, usage-normalised** | Compare *unit cost* (cost per request/GB/hour) not total cost, so growth or seasonality does not fake a saving |
| **Counterfactual baseline** | Forecast the "do-nothing" path and compare |
| **Control group** | Compare against similar resources that were **not** changed (difference-in-differences) |
| **Shadow measurement** | For log filters: measure the would-have-dropped volume *before* enabling |
| **Invoice reconciliation** | Prove it shows up on the bill; investigate residuals |

### 7.3 Counting rules

- One saving, **one** credited claim (Advisor vs agent vs human: deduplicate).
- Separate **run-rate reductions**, **one-time savings**, **cost avoidance** and **rate improvements**; never blend them into one headline.
- Report **regret** next to savings: rollbacks, incidents, boomerangs (the thing was scaled back up within N days).

### 7.4 Regret signals

Incident or alert in the affected scope · SLO regression · human reversal · **boomerang** (re-created or re-scaled within 30 days) · owner complaint · "I searched for X and found nothing" (log-filter regret) · security event on a de-protected asset.

---

## 8. Sustainment

| Drift source | Response |
|---|---|
| IaC redeploys the old size | Source PR; temporary direct fix linked |
| New resources follow the old pattern | Playbook triggers on creation; **Coach** nudge at PR time |
| Platform recreates managed resources | Archaeologist traces the creator; fix the cause |
| Exceptions never expire | Exceptions carry an **expiry**; the Herald re-asks at expiry |
| Savings quietly erode | Sentinel regression alerts; case re-opens automatically |

---

## 9. Undo, panic and the kill switch

- **Undo** on every executed action for a defined window (the card says how long).
- **Panic button** per scope: halts queued actions, optionally rolls back the last N hours.
- **Kill switch** for any agent or the whole crew, reachable by the FinOps lead and security; the Warden can invoke it automatically on policy breach.
- **Break-glass** is rare, loud and logged.

---

## 10. Edge cases we must design for

| Situation | Principle |
|---|---|
| Approver is out of office | Delegate chain from the directory; never "approve on behalf" silently |
| Owner approves but lacks authority | Refuse, explain, route |
| Conditions changed after approval | Stale approval → re-ask |
| Two owners disagree | Diplomat convenes; no action until resolved or escalated |
| Change collides with incident | Freeze; only a pre-approved cost brake is allowed |
| Partial execution failure | Stop-the-line; roll back to last consistent state; alert |
| Human reverses the change | Treat as a regret signal; learn; do not argue |
| A dependency appears after the case | Challenger re-opens; Plan re-validated |
| Resource is shared with another tenant/partner | Raise as a *multi-party* case; default to advise-only |

Next: who owns what, and why → [07 — ownership and organisation](07-ownership-and-organization.md).
