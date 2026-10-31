# Round 2 · Reviewer A — fresh reader through the operator's eyes (raw report)

> **Status: RAW — verbatim as returned.** Agent type `rubber-duck`, read-only, 2026-10-31. Brief: read the revised v4 (commit `cbd6756`) as the operator would — README, then the north star in full, then the deep-dives — and test his complaint against it; look for leaks of his two examples, bloat, contradictions, missing scenes and padded voice. The orchestrator's spot-checks are appended; the disposition is in [disposition.md](disposition.md).

---

**(i–ii) Answered:** `02` gives a real new-service mechanism—change radar → parallel readers → Cost Grammar → scoped provisional Profile → Lab—and a credible knowledge loop of sources, receipts, claim states and re-checks.  
**(iii–iv) Answered:** `03 §11` explains forward cost/risk investigation; `04` makes the Lab a budget-capped, isolated, pre-registered experiment programme with guarded real-world trials.  
**(v–vi) Answered:** `05–06` provide human decisions, cards, email, meetings, Moves and earned autonomy; the SVGs and Mermaid diagrams are loops/state machines, not one whole-system linear pipeline.  
**(vii) Partly:** there is no separate risk register or operator-facing question list, but `01` is still a 6,226-word, 19-section keystone with repeated detail and a substantial vocabulary wall; the founding-example boundary has thin leaks.  
**(viii) Answered, with caveats:** Atlas/Grammar/Lab/Exam/learning contract make this an agent research programme rather than a chatbot or LLM veneer. No Critical blocker found, but the Major issues below could blunt the “impress me” effect.  

## Findings

### A2-01 — Founding-example containment is not fully clean
- **Severity:** Major  
- **File and heading:**  
  - `<repo>\docs\02-learning-azure.md` — §2, “The grammar at work on real services (illustrative decodes)”  
  - `<repo>\docs\research\landscape.md` — §1, “Microsoft — first-party”  
- **Quote:**
  > | A managed firewall: billed while it is allocated — deallocating it stops the billing | **Capacity** | does anything need it outside business hours? | deallocate where it is used only in office hours |
  >
  > | A NAT gateway: documented hourly and data-processing charges, and no stopped state — only removal stops them | **Capacity** + **Flow** | does any subnet still depend on it? | remove it when nothing needs it |
  >
  > Owner/due-date assignment (security); data-value recommendations on unused tables (Sentinel, 30-day window). Rules, not learning.
- **Why it matters:** These are thin echoes of the two founding exam questions: idle capacity in named managed networking services, and unused data. They are not verbatim restatements, but they undermine the deliberate claim that the examples now live only in `07 §8` and the exam bank. A reader primed by the original brief may still see the system being illustrated through those cases.
- **Fix:** Replace the firewall/NAT rows with unrelated capacity/flow examples, and shorten the landscape entry to “data-value recommendations” without the unused-table detail. Keep the specific examples exclusively in the permitted exam locations.

### A2-02 — The north star re-specifies the deep dives instead of being the irresistible front door
- **Severity:** Major  
- **File and heading:** `<repo>\docs\01-north-star.md` — opening status and §§2–16  
- **Quote:**
  > This is the whole idea in one place.
- **Why it matters:** The document is coherent and ambitious, but it is also 6,226 words across 19 top-level sections. A fresh reader is likely to slow down in §2’s scientific-method table, the three-memory taxonomy, six-part learning definition, faculty table, and four clocks—before reaching the vivid day-zero story. It then repeats material owned by the deep dives: §3/`02`, §4–5/`03`, §6/`04`, §7/`05–06`, §8/`07`, and §12/`08`. This makes “the entire idea” feel like a specification rather than a north star.
- **Fix:** Keep the sentence-on-the-wall, one-minute section, five-faculty picture, one day-zero story, one owner Brief, the human spine, and one learning-proof paragraph. Move the detailed scientific-method table and six-learning-things to `11`; the full Grammar to `02`; investigation state machine/worked case to `03`; experiment catalogue to `04`; 13-agent cast to `10`; and the Monday email, annual timeline, outer rims, limits, measures, and glossary to their owning deep dives or an appendix.

### A2-03 — The core lacks a shared-resource, multi-party decision scene
- **Severity:** Major  
- **File and heading:**  
  - `<repo>\docs\05-recommend-act-verify.md` — §1, “The Brief — a decision, not a recommendation”  
  - `<repo>\docs\08-outer-rims.md` — §D, “Working with people in new ways”  
- **Quote:**
  > A confirmed [Case](03-estate-and-investigation.md#7-the-investigation-toolkit) becomes a **Brief**: everything a person needs to decide in under a minute, with everything behind it one tap away.
  >
  > **Cost Court.** For contested, high-value cases, a *Prosecutor* argues for the change, a *Defender* argues for keeping things as they are, and a *Judge* — a differently configured agent — rules. Humans can appeal.
- **Why it matters:** The strongest examples are one-owner decisions. In real Azure estates, the largest opportunities—shared platforms, network paths, reservations, data platforms, resilience changes—have several owners, consumers, budget holders, and incompatible constraints. The only answer is currently an optional “outer rim,” so the core human-in-the-loop story feels weaker exactly where its stakes are highest.
- **Fix:** Promote one multi-party case into `01 §7` and `05`: a shared platform change with competing teams, cost allocation, SLO/risk objections, alternatives, a joint decision, and a verified outcome. It should show collaboration rather than a single owner receiving a card.

### A2-04 — “Trusted” has three incompatible promotion gates
- **Severity:** Major  
- **File and heading:**  
  - `<repo>\docs\01-north-star.md` — §14, “Where humans stay in charge”  
  - `<repo>\docs\11-the-learning-contract.md` — §1, “Six things that change”  
  - `<repo>\docs\02-learning-azure.md` — §4, “From reading to knowing: claims, receipts, life cycle”  
- **Quote:**
  > **What counts as known.** Knowledge becomes *trusted* only after peer review — by the Skeptic and by people — and carries its receipts forever.
  >
  > it has been **replicated** across conditions, not merely read
  >
  > Every claim that will be *relied on to change something* must have passed the Skeptic and a person with domain standing — **and, before it becomes advice for a particular estate, been reconciled with that customer's own bill**
- **Why it matters:** Replication, human/Skeptic review, and commercial verification are all sensible gates, but the documents use “trusted” for different ones. That makes the central promise—what the AI may know, advise, and act on—ambiguous.
- **Fix:** Make `11` the sole authority and name distinct states: **reproduced** (evidence), **reviewed** (Skeptic + human), **advice-eligible** (commercially verified in the estate), and **autopilot-eligible** (credential plus Move record). Replace bare “trusted” elsewhere.

### A2-05 — Voice: five cuts would make the serious ideas sound more credible
- **Severity:** Minor  
- **Files and headings:**  
  - `<repo>\docs\04-experiments-and-the-lab.md` — §13  
  - `<repo>\docs\03-estate-and-investigation.md` — §9  
  - `<repo>\docs\05-recommend-act-verify.md` — §10  
  - `<repo>\docs\07-getting-smarter.md` — §7  
  - `<repo>\docs\08-outer-rims.md` — §G  
- **Quotes:**
  > At night, with no one waiting, the system does what a good analyst does on a train: **re-reads the day and makes it stick.**
  >
  > It is the way physicists find a missing planet: the model is good enough that its failures are informative.
  >
  > A system that only ever says "less" is a spreadsheet with opinions.
  >
  > **The network effect nobody has to trust anyone for**
  >
  > **The voice of the bill.** A two-minute weekly audio for each team — *"what your platform did with its money this week"* — in the team's own language, with the one thing worth knowing and the one thing worth asking. Playful, low-risk, humane; it makes the bill a thing people *listen to*.
- **Why it matters:** These phrases are memorable individually, but together make a rigorous learning proposition occasionally sound like a product manifesto or generated concept deck.
- **Fix:** Keep at most one evocative line per document; replace the rest with observable behaviour, evidence, or a scene.

## Cross-document consistency

No additional material contradiction found. “No first step” describes the five concurrent faculties, while `10` describes a project sequence and explicitly permits overlap. Conversational entry points are consistently presented as pull channels, not the product. Autonomy is consistently constrained by a human-authored rule or earned credential. The two substantive consistency problems are the example leakage in A2-01 and the knowledge-state ambiguity in A2-04.

## What is strong (keep)

- The **day-zero new-service loop** is the clearest answer to the original rejection: it has sources, mechanism inference, uncertainty, experimentation, scope, and an estate-specific follow-up.
- The **Lab** is unusually well imagined: prediction-first, cheapest decisive test, expiry/Janitor, synthetic customer shapes, external-validity limits, trials, and value-of-information budgeting.
- **Explain / Challenge / Teach** makes human interaction part of learning rather than notification decoration.
- The system has real epistemic discipline: Skeptic, receipts, claim life cycles, held-out exams, decoys, calibration, retrieval-only and expert-seed baselines.
- The living-system and four-clocks SVGs communicate concurrent faculties exceptionally well. Strict lint also passes: 20 documents, zero errors and zero warnings.

## Top-10 missing ideas or scenes

1. **FinOps practitioner — allocation arbitration:** A shared platform has weak tags and disputed consumers; the AI proposes a defensible allocation, shows confidence, hears objections, and improves the allocation model.
2. **CFO — portfolio decision:** “Reduce run-rate by 8%, preserve growth capacity, and do not consume more than 40 executive minutes this quarter.” Show the AI assembling and sequencing a portfolio rather than emitting isolated Briefs.
3. **Resource owner / platform lead — shared-resource decision room:** Make the A2-03 multi-party case core, not an outer-rim idea.
4. **FinOps / CFO — forecast-to-close loop:** Show forecast, budget variance, billing lag, commitment timing, finance close, and the next operational decision as one recurring rhythm.
5. **AI-agent researcher — novel-mechanism discovery:** Tell the story of a meter that fits no Grammar category: competing explanations, designed probe, failed first theory, proposed new mechanism, transfer test.
6. **AI-agent researcher — scientific disagreement:** Show a Commons replication that disproves a popular Atlas claim, splits its scope, demotes a Detector, and teaches the system to abstain.
7. **Resource owner — trust recovery:** A guarded change nearly harms a workload, rolls back, explains itself, changes its future behaviour, and visibly re-earns the owner’s willingness to engage.
8. **Microsoft field architect — Azure feedback loop:** Proven documentation, metric, pricing, or UX ambiguity should become a structured signal back to an Azure service team, improving the platform for everyone.
9. **Microsoft field architect — federated-enterprise story:** A central platform team, acquired business unit, independent product teams, and multiple agreements learn together while decisions remain local.
10. **Open-source contributor — contribution journey:** An operator finds a region-specific exception, reproduces it, submits a scoped claim and Lab recipe, receives challenge/review, and sees downstream users get the correction.

---

## Orchestrator spot-checks (2026-10-31)

- **Quotes:** every quoted passage in A2-01 … A2-05 exists verbatim at the cited location (checked by search: the firewall and NAT rows at `02-learning-azure.md` lines 98–99; the landscape sentence at line 45; the north-star sentence at line 3; the two Brief/Cost Court sentences at `05` line 10 and `08` line 60; the three "trusted/replicated/commercially verified" gates at `01` line 325, `11` line 13 and `02` line 178; the five voice quotes at `04` 242, `03` 181, `05` 295, `07` 274, `08` 106).
- **Facts:** "6,226 words" and "19 top-level sections" — measured 6,224 words and 19 `##` headings in `01-north-star.md`. "Strict lint passes: 20 documents, zero errors" — reproduced.
- **Judgement items:** A2-01 is partly a matter of taste (a firewall and a NAT gateway are generic capacity examples, and the landscape row is a factual description of a Microsoft feature); the cheap, safe response was taken (see the disposition). A2-02 conflicts with the brief's request for one file with *the entire idea*; taken in part. The ten missing scenes are design suggestions, not facts; they were scored on how directly they answer the operator's complaint.
