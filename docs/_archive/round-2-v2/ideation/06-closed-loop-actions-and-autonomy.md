# The Closed Loop — from decision to action to proof

> **Status:** Ideation **v2** (revised after rubber-duck round 1; v1 archived [here](../_archive/round-1-v1/ideation/06-closed-loop-actions-and-autonomy.md)) · **Date:** 2026-10-30 · Part of the [north-star vision](01-north-star-vision.md)
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

### Reversibility classes — **one exact class per operation**

| Class | Definition | Examples |
|---|---|---|
| **R0** | Trivially reversible, metadata only | Tags (advisory tags only — see control-plane tags below), schedules, alert routing, budgets |
| **R1** | Reversible configuration change, state preserved | Scale up/down, SKU change within family, pause/stop with state retained |
| **R2** | Reversible within a recovery window | Snapshot-then-delete, soft-delete, quarantine-then-delete |
| **R3** | Irreversible or *economically* irreversible | Permanent deletion without backup, shortening retention, reducing redundancy (the lost copy is gone), releasing a static IP address (it may sit in a partner's allow-list), **commitment purchases, exchanges, renewals and cancellations** (exchange/refund is limited and time-limited — see [research/01](../research/01-azure-native-landscape.md)) |
| **R3-Data** | **Prospective information loss.** Any *collection-reducing* action: ingestion filters, narrower diagnostic categories, sampling, dropped columns, excluded namespaces, lowered collection levels, shortened retention. The configuration can be restored; **the evidence not collected in the meantime cannot** | See below |

**Each operation also records separate attributes — they are *not* part of the class** (no hybrid labels such as "R0/R1"): *state preservation* · *prospective information loss* · ***service interruption*** (user-visible, e.g. a P2S scale change may reconnect users) · *dependency blast radius* · *rollback SLA* · *preconditions*. A change can be mechanically reversible (R1) and still interrupt service; the attribute says so.

> **R3-Data rules.** Never L3 or L4. Requires data-owner **and** security approval, calibrated audit coverage, replay, protected-source checks and — where policy mandates — a complete mirror. Applies to every row in the catalog that reduces what is collected, whatever its `Rev` column shows ([catalog](02-opportunity-catalog.md)). A **safety net** (shadow period, short-lived cheap copy — see [03](03-deep-dives-seed-examples.md)) reduces regret but **does not make the action reversible**, and we never say it does.

### Candidate default autonomy by risk (to be ratified)

| Class | Environment | Blast radius | Default ceiling | Who approves |
|---|---|---|---|---|
| R0 (advisory tags) | any | isolated | **L4** policy autopilot | Policy / owner opted in |
| R1 | non-prod | isolated | **L3** veto window — *only for owners enrolled for that class and scope*; **L4 only inside a ratified, enrolled policy envelope** (§5) | Owner (can veto) |
| R1 | prod | isolated | **L2** assist | Owner |
| R2 | non-prod | isolated | **L3** (enrolled); **L4 only inside a ratified, enrolled policy envelope** | Owner (can veto) |
| R2 | prod | isolated or shared | **L2** | Owner **+ all affected parties** if shared |
| R3 | any | any | **L1–L2, two-key** | Owner **+** FinOps lead |
| **R3-Data** | any | any | **L1–L2 only; never L3/L4** | Owner **+** data owner **+** security co-sign |
| **Commitment purchase / exchange / renewal / cancellation** | any | billing scope | **L2 only — individually signed by the legally authorised buyer(s)** against a finite transaction manifest | Workload owner **+** Finance (**+** more above thresholds) |
| any | regulated / critical-tagged | any | **L1 advise only** unless a recorded exception — *and never an exception to a lock or legal hold* | Owner + risk/compliance |

---

## 3. The safe-change toolkit

1. **Approvals bind to the exact change, not to a vibe.** An approval references a specific Plan version, its **preconditions** (configuration hash, utilisation envelope, price) **and the artefact that will run**: tenant and resource IDs, the **source commit SHA**, the **rendered deployment-plan digest**, the deploying pipeline identity and the **target-state hash**. A rebased or re-rendered diff, a different deploying identity, or a world that drifted beyond tolerance makes the approval **stale** and the owner is asked again. CODEOWNERS review is **not** a substitute for authority over the target resource.
2. **Authority check.** The person who taps *Approve* must hold authority over the target (e.g. the right role on that resource). Otherwise the system refuses and routes to someone who does. *Chat must not become privilege escalation.*
3. **Scream-test ladder** for "probably unused" things (instead of deleting on a hunch):

   | Rung | Action | What we watch | Undo |
   |---|---|---|---|
   | 1 | Label and notify likely parties | Replies, complaints | Remove label |
   | 2 | Restrict (e.g. deny new connections) | Failed-connection signals, health probes | Lift restriction |
   | 3 | Stop / deallocate | Anything that breaks | Start |
   | 4 | Snapshot / back up | Backup proof | Restore |
   | 5 | Wait, with a visible countdown | Silence is evidence of *non-use*, **never consent to delete** | Restore from backup |
   | 6 | Delete (R2 → protected by the backup) — **only after a named human decision** (owner, or the orphan custodian for ownerless resources, [07](07-ownership-and-organization.md)) | — | Restore within window |

   Rung 2 (restrict) and rung 3 (stop) can interrupt service, so each rung is recorded with its own *service-interruption* attribute and, in production, needs the owner's approval before it starts.

4. **Shadow mode, dry-run, canary, staging.**
   *Shadow* (what *would* I have done, scored against what humans did) → *dry-run / what-if* → *canary* (one resource, one region, one environment) → *staged* (dev → test → prod) → **SLO watch with auto-rollback**.
5. **Precedence of stops (machine-enforced, in this order).**
   1. **Legal holds and resource locks are never bypassable by the cost system** — not by an exception, not by an emergency.
   2. **Protected / critical scopes** can only be touched by a distinct, pre-authorised action class.
   3. **Change freezes and declared incidents** stop all changes in the affected scope. The only exception is the narrowly defined **cost brake** below.
   4. Everything else follows policy and the autonomy ladder. **No gate has an "urgent" bypass.**
6. **Veto windows require enrolment.** A veto window (L3) runs only for owners who have **affirmatively enrolled** that action class and scope, with **proof the notice was delivered**. *Silence is never consent* — least of all for orphans ([07](07-ownership-and-organization.md)).
7. **Rate limits / blast limiter.** Max concurrent changes per subscription per hour; stop-the-line if failure rate crosses a threshold.
8. **Idempotency and concurrency.** Steps are idempotent; the plan checks it is acting on the same configuration it analysed; detect in-flight human edits.
9. **Two-key for R3.** Two different humans (owner plus FinOps/Finance) approve any irreversible or economically irreversible action.
10. **Rollback bundle** generated *before* execution: pre-state, exact reverse operation, verification steps, owner of the rollback.
11. **The cost brake — deliberately narrow.** A pre-certified emergency action class, never a general override. It may fire automatically only when **all** hold: the resource class has a **service-owner-recorded safe-to-pause contract**; the trigger is an **independent signal** (not the same data that raised the case); **live incident and SLO checks** show it will not worsen an active incident; it is **enumerated** (e.g. pause a specific class of compute pool), **rate-limited**, **reversible (R1)** and followed by a **mandatory post-incident review**. **A cost anomaly alone never pauses anything**: absent a certified class, the system pages humans and records what it knew. The brake does not outrank locks, legal holds or protected scopes (precedence 1–2 above).

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

**An approval binds to the exact change** (§3, item 1): tenant and resource IDs, **source commit SHA**, rendered plan digest, pipeline identity and target-state hash. Any changed diff, re-render or deploying identity invalidates the approval and re-gates it.

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
  require_tags: { env: dev }          # a CONTROL-PLANE tag (it scopes automation)
  exclude_tags: { cost-exempt: true } # a CONTROL-PLANE tag (it removes protection)
  control_plane_tag_rules: independent-authority-and-audit; recently-written-or-inferred tags do not qualify until revalidated
enrolment:
  required: true                      # silence is never consent
  proof_of_notice: true
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

The envelope is **human-authored, versioned, expiring and reviewable**. The agents can *propose* envelopes (from observed approvals: "you approved this 31 times with no regret — want a policy?") but never ratify them. **Every behaviour-affecting artefact — thresholds, prompts, models, evaluators, playbooks, routing rules — is a governed release** (versioned, independently reviewed, evaluated, approved, reversible), never live-self-tuned by the agents ([04](04-agent-crew.md)).

**Control-plane tags.** Tags are not harmless metadata when they decide autopilot scope, exemptions, criticality, ownership or data class. Those are *control-plane* tags: only an **independent authority** may change them (with audit), and a tag that was just written or inferred does **not** qualify a resource for automation until a cooling-off revalidation passes. *Advisory* tags (e.g. a descriptive label) can be written at R0.

---

## 6. Commitments (the Buyer's workflow)

Reservations and savings plans are different animals: large, long, and only partially reversible. **Purchases, exchanges, renewals and cancellations are never L3–L5.** The crew's role is analysis, simulation and scope optimisation; **every transaction is individually signed by the legally authorised buyer(s)** against a **finite transaction manifest** (what, how much, which scope, which term) bound to the finance policy.

1. **Portfolio view first:** coverage, utilisation, scope, expiry, what-if on steady-state baselines (excluding things the crew is about to shrink — *sequence matters: right-size first, then commit*).
2. **Risk budget** set by Finance: maximum commitment as % of baseline, term ladder (e.g. staggered terms), cooling-off periods, minimum utilisation target. The budget **bounds what may be proposed**; it never substitutes for a signature.
3. **Staged purchases** instead of one big bet; **scope optimisation** (a free-saving class, if scope can be changed) before new purchases.
4. **Two-key** (or three-key above a threshold): owner of the workload + FinOps lead (+ Finance), then the authorised buyer signs.
5. **Post-purchase watch:** utilisation, orphaned commitments after SKU changes, exchange/refund options (time-limited policy), expiry planning.
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

- One saving, **one financial outcome** (Advisor vs agent vs human: deduplicate the *amount*), while **keeping multi-touch provenance** of who and what contributed — attribution is recorded, not raced for.
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

- **Undo is class-specific and stated up front:** **R0 and R1** — undo (the card says how long); **R2** — recovery within a stated window; **R3 and R3-Data — no undo**: we show the residual loss, require two humans and never claim automatic harm detection or rollback. A safety net (shadow, cheap copy) is described as a net, not an undo.
- **Panic button** per scope: halts queued actions, optionally rolls back the last N hours *for classes that can be rolled back*.
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
| Change collides with incident | Freeze; only a pre-certified cost-brake class is allowed (§3 item 11) |
| **No owner can be resolved, or the owner has left** | The case goes to the **orphan custodian** ([07](07-ownership-and-organization.md)). Silence never turns into permission; an orphan can be advised, restricted or paused only within what its policy envelope allows, and deletion always needs a named human |
| Owner never answers | Escalate *privately* up the ladder in [05](05-human-interaction-concepts.md); the case stays open, expires, or is parked — it is never auto-approved |
| Approval was given for a plan whose source commit has since changed | Stale approval → re-gate (§3 item 1) |
| Partial execution failure | Stop-the-line; roll back to last consistent state; alert |
| Human reverses the change | Treat as a regret signal; learn; do not argue |
| A dependency appears after the case | Challenger re-opens; Plan re-validated |
| Resource is shared with another tenant/partner | Raise as a *multi-party* case; default to advise-only |

Next: who owns what, and why → [07 — ownership and organisation](07-ownership-and-organization.md).
