# Round 1 · Reviewer C — the skeptic (raw report)

> **Status: RAW — verbatim as returned.** Agent type `rubber-duck`, read-only, 2026-10-31. Brief: find where "the AI learns" breaks (v4 draft, commit `d267654`). The orchestrator's spot-checks are appended; the disposition is in [disposition.md](disposition.md).

---

## Verdict

Do **not** fund the full programme yet. Fund a tightly capped falsification phase only: the documents describe an unusually thoughtful learning loop, but they do not yet establish that it can learn *customer-relevant Azure economics* rather than produce increasingly elaborate, self-confirming documentation and sandbox results. I would stop if a blinded test cannot beat a simple retrieval/rule baseline on held-out billing behaviour, show calibrated transfer after one correction, and demonstrate positive **all-in** economics. “Learning” is currently a strong aspiration and evaluation narrative, not yet a demonstrated causal capability.

## Findings

1. **C-01 — Critical — Reading is not commercial reality**  
   **File/heading:** `<repo>\docs\02-learning-azure.md`, §1 *What it means to “know” a service*  
   **Quote:** “Knowing a service is not remembering its marketing page. It is being able to answer, for any resource of that service, in any estate:”  
   **Failure scenario:** A new preview service has incomplete price data, delayed meter publication, regional availability limits, and a customer-specific private price, credits, reservation allocation, or chargeback rule. The Lab can establish that a meter appeared in its subscription; it cannot establish the customer’s effective invoice, allocation, or marginal saving. The design correctly mentions an effective price book, but does not define when a generic mechanism may become a customer-facing cost claim. “Ready within hours” will be read as economically ready, not merely provisionally documented.  
   **Fix:** Define two non-interchangeable claim types: **mechanism-verified in a named Lab scope** and **commercially verified for a named billing scope**. State that a new-service profile is never “ready” for savings advice until its rate, agreement treatment, region, billing lag, and allocation assumptions have been reconciled against that customer’s own export.

2. **C-02 — Critical — The Lab proves local behaviour, not safe production advice**  
   **File/heading:** `<repo>\docs\04-experiments-and-the-lab.md`, §7 *The Time Machine — replay and re-price history*  
   **Quote:** “The Time Machine is what lets the system **prove** a change *would have been safe* before asking anyone to say yes.”  
   **Failure scenario:** A small synthetic replay validates a lower SKU, but production has rare traffic, quota contention, private-network paths, tenant-wide commitments, data gravity, or a once-a-quarter recovery path absent from the replay. A separate sandbox also cannot reproduce production scale or negotiated economics. The documents acknowledge this limitation, but still use “prove,” “frontier,” and lab-derived recommendations as if external validity follows from replication. It does not.  
   **Fix:** Cut “prove.” Add an explicit **external-validity envelope** to every Lab result: configuration, region, scale, traffic fidelity, agreement assumptions, and known untested interactions. Only a customer shadow period or a reversible, guarded production trial may support “safe in this estate.” Set portfolio-level learning ROI and stop rules, not just per-experiment caps and expiry timers.

3. **C-03 — Critical — The Exam can become a curriculum, not an independent test**  
   **File/heading:** `<repo>\docs\07-getting-smarter.md`, §3 *The Exam*  
   **Quote:** “A miss is gold: it is turned into an Agenda question and, once understood, a Lesson — so the exam is also a teacher.”  
   **Failure scenario:** The same programme defines the Cost Grammar, builds Terrariums, creates the Forger, runs the agents, curates the exam, and consumes misses as lessons. A hidden question is not independent if its distribution, generators, and answer-key assumptions are shaped by the same people/models. Thirteen roles do not create independent evidence when they share models, memory, incentives, and a Conductor; they can create correlated confirmation bias and expensive theatre. Calibration will also look better than it is if outcomes are sparse, selected, or only observed where humans replied.  
   **Fix:** Require an externally stewarded, time-frozen credential exam with a leakage audit, pre-registered scoring, confidence intervals, and a hand-authored/RAG baseline. Keep official credential tests separate from public benchmarks, Terrariums, agent memories, and post-mortem lessons. “Examiner reviewed by humans” is insufficient; the Examiner needs independent operation and adversarial audit.

4. **C-04 — Major — Human answers are treated as truth too quickly**  
   **File/heading:** `<repo>\docs\06-people-and-conversation.md`, §5 *Message families*  
   **Quote:** “Every question says **why it is being asked** and **what it will do with the answer** — and the answer is remembered, so the same question is never asked twice.”  
   **Failure scenario:** A politically exposed engineer answers “not mine,” a departing owner describes an obsolete rhythm, or a meeting participant supplies a confident but wrong constraint. Scope, expiry, and read-back help, but a single answer can still redirect ownership, suppress future investigation, or generalise a local exception. Meanwhile, “silence is never consent” means unresolved high-value cases can accumulate behind scarce people; escalation may become attention debt rather than learning.  
   **Fix:** Treat human input as attributed, fallible testimony—not a fact. Require corroboration or observable evidence before widening ownership, intent, or constraints; retain a low-friction way to re-ask after evidence changes. Define success as reduced **decision burden**, not fewer questions, and explicitly measure unanswered-case backlog and correction rate.

5. **C-05 — Critical — The economics are asserted, not modelled**  
   **File/heading:** `<repo>\docs\04-experiments-and-the-lab.md`, §12 *The curiosity budget — and a Lab that pays its way*  
   **Quote:** “The Lab's cost is on the report card, next to what the knowledge it produced was worth.”  
   **Failure scenario:** The total cost includes models, 13-agent orchestration, delayed billing observation, Lab runs, human reviewers, Finance reconciliation, owner attention, Commons maintenance, and false-positive/regret handling. The report-card wording visibly includes Lab and models, but not a credible all-in counterfactual against existing FinOps practice. “Spend more” can be smart, but it can also let the system claim business growth, avoided loss, or resilience value without a defensible causal baseline.  
   **Fix:** Add a product thesis with a hard adoption threshold: all-in cost-to-serve, incremental human minutes, baseline-tool comparison, verified incremental value, and a minimum opportunity size. Classify “spend more” as an **investment recommendation**, never savings, until a business owner and Finance predefine and verify its outcome metric.

6. **C-06 — Major — The Commons has no viable trust or stewardship proposition yet**  
   **File/heading:** `<repo>\docs\07-getting-smarter.md`, §7 *The Commons*  
   **Quote:** “The Commons is the open, versioned, open-source (MIT) half of the knowledge.”  
   **Failure scenario:** A plausible-looking poisoned profile, detector, or Lab recipe can propagate across estates; stale claims can free-ride on prior trust. The network effect requires maintainers to review, reproduce, revoke, and support claims, but identifies no accountable operating model or incentive. MIT may cover project-authored material but does not itself settle rights to redistribute source excerpts, third-party terms, or customer-derived outcome claims. Counts-only sharing can still reveal commercially sensitive patterns in small cohorts.  
   **Fix:** State a Commons constitution: claim tiers, named maintainership and decision rights, reproducibility requirements, revocation/SLA policy, provenance and licence compatibility rules, minimum cohort rules, and who bears responsibility for a materially harmful published claim. This is a core viability proposition, not deferred implementation detail.

7. **C-07 — Major — The proposed proof does not support the scaling claim**  
   **File/heading:** `<repo>\docs\10-what-next.md`, *The thinnest slice*  
   **Quote:** “If this small loop works for three services, it works for three hundred.”  
   **Failure scenario:** Three curated capacity/stock/flow services can demonstrate a pleasant Terrarium puzzle. They do not cover commitments, private pricing, preview instability, quota-bound services, cross-service billing, regional variance, rare operations, or production performance. Worse, the initial Atlas and Grammar are explicitly expert-authored, so success may demonstrate seeded taxonomy plus retrieval—not discovery or compounding learning.  
   **Fix:** Replace the sentence with a bounded hypothesis. Require a coverage matrix across mechanism, commercial variation, region, lifecycle, interaction complexity, and evidence type; claim scale only after held-out transfer beats a retrieval/rule baseline across that matrix.

## Contradictions and overclaims

- `<repo>\README.md` promises it “is ready for a brand-new service within hours.” Yet `<repo>\docs\01-north-star.md`, §15 says, “The Lab cannot reproduce everything — scale, negotiated prices, quotas.” Call the first a **provisional mechanism profile**, not readiness.

- `<repo>\docs\01-north-star.md`, *In one minute*: “So we do not write the advice. We build an AI that learns Azure's economics for itself.” But `<repo>\docs\10-what-next.md` starts with “ten Service Cost Profiles written by experts.” Seeding is legitimate; obscuring the authored baseline makes “learning” untestable.

- `<repo>\docs\07-getting-smarter.md` says, “The score that matters is the one the system **cannot see in advance.**” It also says, “The exam bank, once opened, is a **public benchmark for cloud cost reasoning**.” A held-out subset is mentioned, but credential scores need a hard, auditable partition from public training material.

- `<repo>\docs\07-getting-smarter.md` promises, “By the next morning **every** organisation running the Commons has a verified profile,” while `<repo>\docs\02-learning-azure.md` says, “The same meter costs different amounts for different customers.” A generic billing mechanism can be verified; a customer-relevant economic recommendation cannot be globally verified overnight.

## The five-minute kill

1. **What result would prove this learns causal billing mechanisms better than a well-maintained RAG/rule system seeded with the same expert profiles?**
2. **Which specific customer invoice outcomes can a separate Lab validly predict, and which remain unknowable until a guarded production observation?**
3. **What is the all-in cost per verified incremental euro, including people and review, versus existing FinOps practice—and below what opportunity size is this irrational to deploy?**

### The cheapest falsifying experiment

Use existing historical evidence—no full Lab, Teams integration, or 13-agent system. Freeze public documentation, schemas, and prices at a past date for one service family; withhold two real billing exports and one related service. Have the proposed learner create pre-registered meter, lag, uncertainty, and diagnosis predictions; reveal one outcome as a lesson, then test transfer on the sibling service. Compare it with a retrieval-only baseline and a FinOps expert. Kill the thesis if it neither materially improves after correction nor beats retrieval on the held-out case with honest calibration.

**No:** `<repo>\docs\10-what-next.md` has useful questions, but its “thin slice” is not this falsifier: it requires a Lab, Terrarium, multiple agents, Teams, and ends when one person says “yes,” not when learning beats a baseline under blinded conditions.

## Genuinely strong

1. Claims, receipts, staleness, and outcome scoring are materially stronger than generic “agent learns” rhetoric.  
2. The design explicitly recognises that documentation and real bills diverge.  
3. It treats reversibility, restraint, attention, regret, and “do nothing” as first-class—not merely savings volume.

## Top 5 changes, ranked

1. Define **verified**, its scope, and the Lab-to-customer evidentiary boundary.  
2. Replace the three-to-three-hundred claim with a preregistered, baseline-controlled learning test.  
3. Make the Examiner genuinely independent, leak-audited, and externally stewarded.  
4. Publish an all-in economic model and adoption threshold before building the full agent society.  
5. Define Commons stewardship, liability, provenance, licensing, and revocation as a product prerequisite.

---

## Orchestrator spot-checks (2026-10-31)

- **Quotes:** all 14 quoted passages (C-01, C-03 … C-07 and the six contradiction quotes) exist verbatim in the cited files. C-02's quote is the same Time Machine sentence checked under A-03.
- **Claims:** a design-logic review; no external facts to verify. Two reviewer statements were checked against the text: that §15 of the north star contains "The Lab cannot reproduce everything" (yes), and that `10-what-next.md` starts with "ten Service Cost Profiles written by experts" (yes).
- **Tension to resolve consciously:** C wants a hard, baseline-controlled falsifier; reviewer D calls "gates" and "honest unknowns" lists bloat. Resolution in the disposition: present the falsifier as the *first experiment* (with baselines and a transfer test), not as a gate, kill criterion or register.
