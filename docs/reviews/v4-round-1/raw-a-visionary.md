# Round 1 · Reviewer A — visionary / AI researcher (raw report)

> **Status: RAW — verbatim as returned.** Agent type `rubber-duck`, read-only, 2026-10-31. Brief: judge ambition and whether "learning" is real at mechanism level (v4 draft, commit `d267654`). The orchestrator's spot-checks are appended at the end; the disposition is in [disposition.md](disposition.md).

---

## Verdict

V4 is finally a credible north star rather than an Advisor wrapper: the STUDY–SURVEY–TEST–ACT–GROW model, Lab, and evidence-first posture are genuinely differentiated. But it repeatedly calls storage, scoring, and review “learning” without defining the mechanism that changes beliefs, tactics, or behaviour. Under adversarial scrutiny, it risks becoming a self-updating rule catalogue with an excellent laboratory—not yet a system that demonstrably discovers new economic knowledge. The Lab, Terrarium, Examiner, and Commons are coherent, but their causal and scope claims currently outrun what they establish.

## Critical issues

1. **A-01 — Critical — `<repo>\docs\02-learning-azure.md`, §10 “Learning how to learn”**  
   > “**The system keeps a record of its own method and tunes it:**”

   **Why it matters:** This is the central missing mechanism. An LLM does not learn merely because a receipt, lesson, or outcome is written to durable memory; that is retrieval-backed experience storage unless a defined update process consumes it. The unmechanised verbs recur in `<repo>\docs\01-north-star.md` §§3, 8, 11–12; `<repo>\docs\02-learning-azure.md` §§2, 10; `<repo>\docs\03-estate-and-investigation.md` §§2–3, 6, 9; `<repo>\docs\04-experiments-and-the-lab.md` §§9, 13, 15; `<repo>\docs\06-people-and-conversation.md` §§6, 12; and `<repo>\docs\07-getting-smarter.md` §§2, 6. Claims, receipts, rechecks, and exams are excellent **validation** mechanisms, not learning algorithms.

   **Concrete fix:** Add one explicit “Learning Contract” defining four distinct loops: Bayesian belief updates for Atlas claims; a contextual bandit for Agenda/tactic selection; program synthesis plus test oracles for Detectors/Moves; and a causal estate model for consequence predictions. State the state, evidence, objective, update rule, promotion threshold, and held-out test for each.

2. **A-02 — Critical — `<repo>\docs\10-what-next.md`, §“The thinnest slice”**  
   > “**The slice is done when a person, reading only the Brief, says "yes, that's real and I'd act on it"** — for waste that no rule described.”

   **Why it matters:** The proposed proof can validate a polished, human-seeded workflow, not discovery. It begins with expert-written profiles, a human-authored grammar, a sourced trap bank, and planted Terrarium waste. A persuasive Brief is neither evidence that the system inferred the mechanism nor that it transferred beyond encoded examples.

   **Concrete fix:** Make the founding experiment three-armed: grammar-only learner, expert-profile baseline, and generic tool-using baseline. Test on withheld services, withheld combinations of known mechanisms, and post-cutoff/constructed mechanisms unknown to all arms. Score learning curves and transfer—not only a human’s willingness to act.

## Major issues

3. **A-03 — Major — `<repo>\docs\04-experiments-and-the-lab.md`, §7 “The Time Machine”**  
   > “**The Time Machine is what lets the system prove a change would have been safe before asking anyone to say yes.**”

   **Why it matters:** Replay cannot prove a production counterfactual. Configuration changes alter behaviour, dependencies, workload shape, failure modes, and human operations; historical telemetry omits unobserved demand and rare paths. The document later acknowledges trials and guards, but “prove” creates an epistemic contradiction.

   **Concrete fix:** Make the Consequence Engine a structural causal model with explicit assumptions, uncertainty, and eligibility for synthetic-control/difference-in-differences estimates. Rename replay output “counterfactual evidence under stated assumptions”; reserve confirmation for canary trials or post-change observation.

4. **A-04 — Major — `<repo>\docs\07-getting-smarter.md`, §7 “The Commons”**  
   > “**By the next morning every organisation running the Commons has a verified profile — and a Detector, if one was warranted — without a single customer's data having moved.**”

   **Why it matters:** This conflicts with `<repo>\docs\04-experiments-and-the-lab.md` §11, which correctly says billing can differ by region, currency, and contract. A Lab result can verify a conditional claim, not universal economics or a customer’s effective saving. “Verified profile” currently blurs meter semantics, regional behaviour, price, contract, scale, and estate context.

   **Concrete fix:** Every Atlas claim needs a scope vector: service/SKU/API version, region, offer/contract, feature set, load condition, date, and test environment. The Commons should distribute conditional claims and replication recipes; “same-day” should mean *draft semantics*, not universal verification.

5. **A-05 — Major — `<repo>\docs\07-getting-smarter.md`, §3 “The Exam”**  
   > “**It shares no memory with the investigators, and the investigators never see its questions.**”

   **Why it matters:** No shared memory is not independence. Examiner and investigator can still share a base model, training corpus, grammar, templates, and generator biases. A Terrarium with planted waste may only test recognition of the examiner’s own ontology. The Forger is a strong idea, but it is stranded in `<repo>\docs\08-outer-rims.md` rather than powering core evaluation.

   **Concrete fix:** Promote the Forger into the main Exam: adversarially generate decoys, causal confounders, and mechanism combinations that evade the current grammar. Require provenance-separated, post-cutoff, and retrospective real-case evaluation; mark possible training contamination rather than treating held-out prompts as sufficient.

6. **A-06 — Major — `<repo>\docs\07-getting-smarter.md`, §1 “Everything is a prediction”**  
   > “**From the thousands of scored predictions the system draws its calibration record, the single most honest picture of how much to trust it:**”

   **Why it matters:** “80% confidence” is not meaningful across heterogeneous, dependent predictions. Acceptance is affected by the AI’s message; savings are treatment-confounded; production outcomes arrive late; and LLM verbal confidence is not calibrated uncertainty. Per-domain grouping helps but does not solve selective action, shifting distributions, or causal attribution.

   **Concrete fix:** Define a prediction ontology: target, observation window, counterfactual method, loss/harm, and scoring rule. Use proper probabilistic scores, conformal intervals, and selective abstention. Never convert model tone into a probability without an empirically validated calibration layer.

7. **A-07 — Major — `<repo>\docs\04-experiments-and-the-lab.md`, §13 “Dreaming”**  
   > “**A year in, most of what a customer sees is the output of Detectors; the expensive investigations are reserved for the genuinely new.**”

   **Why it matters:** This is a rulebook in disguise unless sharply constrained. A Detector is explicitly “small, cheap, inspectable logic”; Atlas profiles, grammar entries, and Moves become an expanding compiled catalogue. That is valuable, but “expensive reasoning once, cheap detection forever” is false under changing prices, workloads, and estate meaning.

   **Concrete fix:** Reframe Detectors as expiring, scoped **lead generators**, never conclusions. Each must declare validity domain, false-negative risk, novelty trigger, and mandatory escalation conditions. Preserve expensive reasoning for ambiguous and shifted cases, not only nominally “new” services.

## Minor issue

8. **A-08 — Minor — `<repo>\docs\08-outer-rims.md`, preamble**  
   > “**Each idea is a sentence or three — a direction, not a design.**”

   **Why it matters:** Vocabulary drifts across claim, profile, law, lesson, pattern, Detector, Move, and credential; the maturity ladder does not fully crosswalk to Atlas and Move promotion. Meanwhile, the most important missing mechanisms—Forger, rehearsal estate, Cost Court—are relegated to moonshots. Repeated human-in-the-loop prose across documents also consumes space the learning model needs.

   **Concrete fix:** Add one typed knowledge-lifecycle diagram and glossary crosswalk; elevate Forger and rehearsal estate into the core loop; keep duplicated guardrail language primarily in `<repo>\docs\09-guardrails-later.md`.

## Missing big ideas

1. **Causal Cost World Model** — Add to `<repo>\docs\03-estate-and-investigation.md` §11 and `<repo>\docs\04-experiments-and-the-lab.md` §7. Model configuration, demand, meters, SLOs, dependencies, and business outcome as intervention-aware causal structure—not correlated tables.

2. **Probabilistic Atlas** — Add to `<repo>\docs\02-learning-azure.md` §§4, 10. Claims should be Bayesian, scoped hypotheses with evidence likelihoods; “laws” should emerge through model comparison and replication, not prose consolidation.

3. **Program-synthesised billing science** — Add to `<repo>\docs\04-experiments-and-the-lab.md` §§4–6. Generate factorial meter probes and metamorphic tests from schemas/price changes, then synthesise executable billing laws from observed differences.

4. **Value-flow graph** — Add to `<repo>\docs\03-estate-and-investigation.md` §§1, 7. Connect data, flow, consumers, and business outcomes so “unused” means no demonstrated marginal value—not merely few reads.

5. **Forger self-play as core infrastructure** — Move from `<repo>\docs\08-outer-rims.md` into `<repo>\docs\04-experiments-and-the-lab.md` §14. Let adversarial agents evolve deceptive waste and legitimate decoys faster than Detectives learn them.

6. **Unknown-unknowns engine** — Add to `<repo>\docs\03-estate-and-investigation.md` §§5–6. Use generative bill/configuration residuals and change-point causality to surface patterns outside existing grammar and detector coverage.

7. **Contextual-bandit research director** — Add to `<repo>\docs\04-experiments-and-the-lab.md` §12. Learn which source, question, experiment, or replay maximises verified value per euro and per human minute while preserving deliberate exploration.

8. **Reproducibility lattice for the Commons** — Add to `<repo>\docs\07-getting-smarter.md` §7. Claims earn strength through a graph of independent replications across conditions, making transfer boundaries first-class knowledge.

9. **Proof-carrying Moves** — Add to `<repo>\docs\05-recommend-act-verify.md` §4. A Move should carry machine-checkable preconditions, invariants, rollback properties, and a stated proof boundary—not just a procedural recipe.

10. **Real-options economics** — Add to `<repo>\docs\05-recommend-act-verify.md` §7. Optimise flexibility, staged commitments, and the value of waiting for information—not merely expected discount.

## Genuinely strong

1. **Claims with receipts plus Knowledge CI** is a serious epistemic stance; “documents are evidence, not truth” is exactly right.  
2. **Lab → Terrarium → Exam → report card** is a coherent scientific loop, unusually ambitious for FinOps.  
3. The circular living-system and four-clocks visuals materially fix the previous linear-process problem; local linear diagrams are appropriately used for bounded workflows.

## Top 5 changes, ranked

1. Define the Learning Contract and separate memory, inference, policy learning, and code synthesis.  
2. Build the causal Consequence Engine; remove claims that replay “proves” safety.  
3. Redesign the thinnest slice to prove transfer and discovery against seeded baselines.  
4. Make Atlas/Commons knowledge conditionally scoped and replication-backed.  
5. Treat Detectors as expiring lead generators; move Forger-driven novelty testing into the core system.

---

## Orchestrator spot-checks (2026-10-31)

- **Quotes:** all eight quoted passages (A-01 … A-08) exist verbatim in the cited files (normalised for markdown emphasis).
- **Claims:** this report makes design arguments, not external-fact claims, so nothing further to verify against primary sources. The "unmechanised verbs" list in A-01 was not re-counted; the central point (the documents define validation mechanisms but no update rule) is accepted on reading the documents.
- **Reviewer-added caution to carry:** A-07's "false under changing prices, workloads, and estate meaning" is an argument, not a measurement — handled by making Detectors expiring lead generators.
