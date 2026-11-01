# Round 2 · A — Learning and the core idea (model: gpt-6-sol)

> Raw report, saved exactly as the reviewer returned it (everything below the rule). Reviewed on 2026-11-01: the written design (`docs/design/`, commit `3543f3b`). Lens: does the design deliver a system that learns instead of encoding known tips? The orchestrator's spot-checks of what this reviewer cited are in the [disposition](disposition.md).

---

## Verdict

The design preserves the north star’s *scientist, not rulebook* spirit: claims have receipts, investigations invite refutation, and outcomes feed memory. It is also candid that removing the Lab leaves some meters unknowable until an adopter uses them.  
**The core learning claim is not yet demonstrated.** The cold-start path lacks a specified meter-to-estate reconciliation test, and the proposed learning test could mistake copied knowledge for learning.  
One safety claim needs correction before implementation: a wrong claim can influence a change even when it cannot supply an Action parameter.

## Top five fixes

1. Gate Action **selection and eligibility**, not just parameter values, on scoped evidence.
2. Prove a blind, end-to-end new-service discovery and billing trace.
3. Define when a bill observation is sufficiently settled and attributable to promote a claim.
4. Isolate and power the frozen-versus-updated test; audit contamination.
5. Independently sample Detector non-leads and Agenda questions to break feedback loops.

### 1. New service test

The intended trace is coherent: a new announcement, price meter or schema diff triggers parallel Scholar reads; the Skeptic challenges claims; knowledge CI and a person review the Librarian’s draft; the released Atlas prompts an estate search and a *documented-only* heads-up. An adopter’s subsequent bill, replay or approved trial can strengthen the estate-specific claim; a confirmed finding can become a back-tested, shadowed Detector ([04-knowledge-and-learning.md:167–228](file:///<repo>/docs/design/04-knowledge-and-learning.md#L167-L228), [04-knowledge-and-learning.md:230–254](file:///<repo>/docs/design/04-knowledge-and-learning.md#L230-L254), [03-agents-and-workflows.md:68](file:///<repo>/docs/design/03-agents-and-workflows.md#L68)).

**The trace becomes vague at reconciliation.** It does not specify how a newly named retail meter joins to a resource, SKU, workload, bill line and owner; how ambiguous or absent matches are counted; or what fidelity lets `price-sim` advise rather than abstain. A service unused by the adopter remains provisional, appropriately. The seeded monthly Study cost is **€8–31**, within total scenarios of **€292–4,741**, but reviewer time, a novel service’s marginal investigation and any approved trial’s Azure charges lack a per-discovery estimate ([10-cost-and-finops.md:14–16,36,71,86](file:///<repo>/docs/design/10-cost-and-finops.md#L14-L86)). Source detection, human review and billing confirmation therefore need a blind build-and-test drill, not just the invented Prism story.

### 2. Experimenting without a Lab

Replays that disclose their fit to the original bill, scoped Lessons, registered outcomes and reversible approved trials form a credible **evidence** loop—not a substitute for testing an unused meter or an unseen performance frontier. The design generally says this honestly ([04-knowledge-and-learning.md:220–228,303–310](file:///<repo>/docs/design/04-knowledge-and-learning.md#L220-L310)). Five inexpensive additions, in value-for-cost order:

1. **Meter coverage ledger.** Reconcile each new meter against inventory, FOCUS lines and candidate owners, retaining unmatched and ambiguous joins. This makes missing knowledge observable rather than silently classifying a service as understood.
2. **Prospective shadow forecasts.** Timestamp predictions—including meters expected *not* to appear—before the first export. Score all predictions after settlement, not just the bill lines that matched.
3. **Independent shadow audits.** Blindly inspect sampled Detector leads **and non-leads**, stratified by service and spend. Comparing shadow leads only with Cases Detectives happened to examine cannot measure missed waste ([04-knowledge-and-learning.md:254](file:///<repo>/docs/design/04-knowledge-and-learning.md#L254)).
4. **Read-only priority exploration.** Randomly investigate a small, human-capped share of eligible Agenda questions and log selection probabilities. Replaying only previously chosen Cases cannot establish that learned priorities beat a fixed order ([04-knowledge-and-learning.md:279](file:///<repo>/docs/design/04-knowledge-and-learning.md#L279)).
5. **Observe planned changes.** Register control meters and likely confounders before an owner’s already-planned resize or rollout. Such natural experiments add evidence without creating resources or asking for a change solely to learn.

### 3. Learning test

Holding models, prompts and tools fixed and splitting by service and time are strong starting controls ([08-testing-and-evaluation.md:39,54–58](file:///<repo>/docs/design/08-testing-and-evaluation.md#L39-L58)). But **updated wins** could mean a person or seed bank supplied the exact trap to the Atlas or Detector; **updated loses** could mean the sealed cases contain none of what it learned. Bank-derived fixtures, public source pages, Atlas claims and Lessons need a contamination audit. Pin both arms’ source/tool snapshots, run them read-only with isolated stores, repeat stochastic runs, and predeclare a meaningful paired lift with intervals clustered by independent service/estate—not generated rows. The design specifies neither counts per held-out domain nor power or a lift margin. It correctly notes that even zero harms in 100 independent decoys leaves roughly a 3% upper risk; correlated variants of 79 verified rows are weaker still ([08-testing-and-evaluation.md:30–41,82,162](file:///<repo>/docs/design/08-testing-and-evaluation.md#L30-L162)).

### 4. Hard-coded knowledge

The fourteen-part Cost Grammar is useful **scaffolding** because a reviewer can add a mechanism; Detectors nominate leads rather than decide them ([04-knowledge-and-learning.md:75–96,230–254](file:///<repo>/docs/design/04-knowledge-and-learning.md#L75-L254)). It becomes a ceiling if every unfamiliar meter is forced into a familiar category or the simulator assumes that category specifies its billing formula. The 145-row bank is useful test seed material, but only 79 *rows* are Verified—not 79 independent mechanisms—and bank-derived cases alone cannot demonstrate discovery beyond known tips ([08-testing-and-evaluation.md:30–41](file:///<repo>/docs/design/08-testing-and-evaluation.md#L30-L41)). Permit “unknown/compound rule,” retain unexplained residuals, and test genuinely later services.

### 5. Proof points

P1, P3 and P9 have useful negative-path pass conditions; P4 and P10 test scale and operating cost. P6 tests **known bank rows**, not the highest-risk claim: discovering, mapping, pricing and cautiously advising on a genuinely unseen service ([13-roadmap.md:24–33](file:///<repo>/docs/design/13-roadmap.md#L24-L33)). Add that proof point, measuring launch-to-detection—not merely first-read-to-profile—and subsequent invoice-level prediction error. Predeclare numeric budgets, quality margins and safe revocation windows for P2/P4/P5/P8/P10; “red team finds none” in P7 establishes only that its tested attacks found none.

### 6. Agents and workflows

These are **real loops**, not merely AI labels: Study reads in parallel, Detective and Skeptic iterate, Respond reopens Cases, and Evaluate can retire Detectors. The Skeptic independently retrieves facts but can still share the Scholar’s erroneous sources; the design acknowledges that limit ([03-agents-and-workflows.md:66–70,144–146](file:///<repo>/docs/design/03-agents-and-workflows.md#L66-L146)). Keep AI for extracting disputed claims, hypotheses, options and explanations. The Auditor’s numerical comparison and the Conductor’s stated value-of-information formula are candidates for **code**, reserving model calls for ambiguous inputs ([03-agents-and-workflows.md:12,200–204](file:///<repo>/docs/design/03-agents-and-workflows.md#L12-L204)).

### 7. Overclaiming

Qualify these sentences: **“Money on Azure arises in fourteen ways”** (a taxonomy, not an exhaustive finding); **“The bill is the oracle”** (observation is not causation); **“the worst a wrong claim can do is put a wrong sentence”** (it can steer Action choice); **“the gold covers 79 mechanisms”** (79 Verified rows); **“If updated memory does not beat frozen memory … learned nothing”** (test relevance and power matter); and **“the system pays for itself”** (the quoted break-even excludes people and, where needed, the hub) ([04-knowledge-and-learning.md:75,161,184](file:///<repo>/docs/design/04-knowledge-and-learning.md#L75-L184), [08-testing-and-evaluation.md:41,54](file:///<repo>/docs/design/08-testing-and-evaluation.md#L41-L54), [10-cost-and-finops.md:153–154,171–173](file:///<repo>/docs/design/10-cost-and-finops.md#L153-L173)).

| # | Severity | File:line | Quote (≤25 words) | What is wrong | Proposed fix |
|---|---|---|---|---|---|
| 1 | **blocker** | [04-knowledge-and-learning.md:161](file:///<repo>/docs/design/04-knowledge-and-learning.md#L161) | “the worst a wrong claim can do is put a wrong sentence” | Typed parameters do not prevent a false claim selecting an unsuitable Action or guard, including under a credential. | Validate applicability and required evidence in code; exclude disputed or weakly evidenced cases from autopilot. |
| 2 | **major** | [04-knowledge-and-learning.md:167–184](file:///<repo>/docs/design/04-knowledge-and-learning.md#L167-L184) | “Inventory finds two preview deployments” | Discovery-to-meter-to-resource attribution is illustrated, not specified or tested. | Define join, unmatched and abstention contracts; run a blind cold-start proof. |
| 3 | **major** | [04-knowledge-and-learning.md:184,220–223](file:///<repo>/docs/design/04-knowledge-and-learning.md#L184-L223) | “the bill settles the dispute” | One lagged or rerated observation may not isolate a scale-down’s billing rule; simulator fit has no acceptance threshold. | Require settled meter-period evidence, matched usage/change history and a published error bound. |
| 4 | **major** | [08-testing-and-evaluation.md:30–54,162](file:///<repo>/docs/design/08-testing-and-evaluation.md#L30-L162) | “updated memory no better than frozen memory” | Seed overlap, irrelevant test cases and unspecified statistical power can produce either false verdict. | Isolate sources and stores; audit leakage; preregister clustered paired lift and uncertainty. |
| 5 | **major** | [04-knowledge-and-learning.md:254,279](file:///<repo>/docs/design/04-knowledge-and-learning.md#L254-L279) | “compared with what Detectives find” | Investigated Cases are selected, so shadow precision, recall and learned Agenda value can be self-confirming. | Audit sampled non-leads and randomly selected read-only questions. |
| 6 | **major** | [10-cost-and-finops.md:71,153,173](file:///<repo>/docs/design/10-cost-and-finops.md#L71-L173) | “The hub is shared platform cost. It is not in the totals.” | Break-even and new-service learning cost omit material conditional and human costs. | Show adopter-inclusive ROI and marginal cost/time per reviewed profile and trial. |

**What I verified myself.** Microsoft Learn confirms [retail prices are undiscounted and paginated at 1,000 records](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices), supporting the need for the adopter’s price sheet; [FOCUS distinguishes billed, contracted and effective cost and exposes meter/resource fields](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus); and [Cost Management data can lag, rerate, and differ from current ARM inventory](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data), limiting the day-next bill story.

**What I could not verify.** Nothing is built: actual new-service coverage, meter attribution, causal savings, reviewer minutes, model-token volumes and any P1–P10 result remain unmeasured.
