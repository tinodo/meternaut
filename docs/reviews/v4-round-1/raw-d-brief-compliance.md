# Round 1 · Reviewer D — brief-compliance and anti-pattern auditor (raw report)

> **Status: RAW — verbatim as returned.** Agent type `general-purpose`, read-only (could run the lint), 2026-10-31. Brief: check the v4 draft (commit `d267654`) against the operator's original brief item by item and against the anti-patterns he rejected. The orchestrator's spot-checks are appended; the disposition is in [disposition.md](disposition.md).

---

Paths are relative to `<repo>\docs\` unless noted.

## Verdict
Not yet. The heart (study · survey · test · act · grow) is real and deep, no register survives under its own name, and the lint is green. But within minutes the operator would see three things: his two examples are still written out in the north star (and flagged on the README); Advisor, the first problem in his brief, appears in none of docs 01–10; and "as many examples as possible" lives only in a 145-row exam appendix the design calls "not a rulebook". The lint cannot catch any of it. **Biggest rejection risk:** he named Advisor and Cost Management, and the package names his two examples instead.

## 1. Lint
`17 documents checked: 0 error(s), 0 warning(s) (strict) -> OK`. I fooled it in memory (no writes): the anchor guard missed 11 of 15 paraphrase probes, including both founding sentences, "idle gateway" and "unused logs"; the bloat guard missed "assumptions list", "open questions", "exit criteria", "honest unknowns". CHANGELOG and AGENTS are exempt; the linear-picture test flags only strict single-path flowcharts; nothing checks rule 8.

## 2. Anchoring
Structure is broad (12 mechanisms, 9 real decodes, Prism spans 7 mechanisms, 37 outer-rim ideas, 145 traps). The narrative is not: by my count about 20 of 37 concrete scenarios in 01–06 and 11 are the two shapes (idle or oversized capacity; data that accumulates or "nobody reads").

**D-01 Major — 01-north-star §2 table; §16 "The founding exam".** Both findings sit outside the two permitted files (rule 6), and the science table uses them as canonical hypotheses: `"This capacity is idle." "This data is never read."` Fix: neutral hypotheses; reduce §16 to a link to 07 §8; drop the README callout.

**D-02 Major — 01 §16 vs 07 §8 vs exam bank.** 01: "They are the **first two exam questions** — and the tips that go with them (what to stop paying for, how to shrink it safely) must come out of the system's own reasoning." 07: "They sit in the exam bank beside the other traps and hold **no special place** in the design." The bank's first-ten list includes its nearest rows, the vWAN hub (#7) and Sentinel (#10). Fix: keep "no special place"; drop "founding/first"; reselect the ten.

**D-03 Major — implicit anchors.** 06 §16: "as the first, which looks unintended - nothing reads it."; 06 §5: "A win: the gateway change you approved in October is verified:"; 08 §D: `"reduce the shared gateway to 40 units" — "we peak at 38 at 09:00 on Mondays; keep 45 and change after 22:00"`; 01 §5's flagship case has the second finding's shape: "The demand signal — query volume — shows a handful of queries an hour. Hypothesis: *sized for a launch that is over.*" Also 02 §2's Flow row ("produced but consumed by nobody; moved further than needed") and 10's slice (capacity, stock, flow). Fix: use other mechanisms (commitments, ML compute, replication).

**D-04 Major — enforcement over-claimed.** AGENTS rule 5: "It checks links, anchors, diagrams and orphans, and enforces rules 6–8." CHANGELOG: "guards that fail the build if the operator's two examples creep into the design or governance paperwork returns". Fix: add phrase patterns (never read, nobody reads, shared gateway, scaled up long ago, honest unknowns), scan docs/**, fail pictures with one path through 80%+ of nodes, drop the rule-8 claim.

## 3. The heart
- **Learn NEW services — Deep** (02 §6–7, 01 §3, 08 §A): radar, parallel readers, decode, Lab, provisional profile, Agenda, back-edges.
- **Gather knowledge — Deep** (02 §3–5, §9–10; 07 §2, §7): trust-ranked sources, claims with receipts, Knowledge CI.
- **Investigate cost — Deep** (03 §5–11): ledger, Agenda, hypothesis states, Skeptic, Consequence Engine.
- **Experiment — Deep** (04): ladder, benches, pre-registration, replication, budgets.
- **Recommend/act — Deep; purchases Thin** (05, 06): Brief, options, Moves, earned autonomy, verification.

Still unclear: how this relates to Advisor and Cost Management; what a *real* first-week output looks like (every end-to-end story is invented: Prism, "support-search"); how the Lab obtains services needing quota or private preview; how "analyse actual consumption" works beyond one-liners.

## 4. Brief coverage
| Brief item | Where | Verdict |
|---|---|---|
| Cost Management as input | 02 §3, 03 §1 | Thin |
| Advisor; "owners don't act" | 11 FAQ only | **Missing** |
| Analyse consumption | 03 §1, §5; 04 §5 | Covered |
| "As many examples as possible" | 08; 02 §2; bank | Thin (narrative) |
| Directory; tag owner | 03 §4; 06 §8 | Covered |
| Email, Teams, SMS, avatars | 06 §4–5, §10, §16 | Covered |
| OK → resize | 05 §4, §6 | Covered |
| Purchase reservations | 05 §7 | Thin |
| Foundry agents; not a chatbot | 01 §9, §13 | Covered (Foundry deferred) |
| Guardrails later; Microsoft-only | 09 | Covered |
| CAF + WAF | 09; 03 §11 | Thin |
| Open source; FULL AI; HITL | 07 §7; 01 §14 | Covered, though 04 §13 says "most of what a customer sees is the output of Detectors" |
| What cost management means in Azure; existing solutions | landscape (learning lens only) | Thin |
| North star; later phases | 01; 10 | Covered |

**D-05 Critical — Advisor and Cost Management absent.** "Advisor": zero hits in README and 01–10. 03 §6's eight Agenda sources exclude native recommendations; 01 §4 lists "**Reads widely** (with permission): the bill, the resource inventory, configuration and change history, telemetry," and no Advisor. Only mention, 11: "It uses Advisor's findings as one input among many, and checks them like any other claim." v3 had it as "the brief's own problem". Fix: add native recommendations, budgets and anomaly alerts as an Agenda source (03 §6) and input (01 §4); a 200-word 05 box, "What happens to an Advisor card"; a territory map atop landscape.

**D-06 Major — CAF/WAF thin.** 09: "It is aligned with the **Cloud Adoption Framework** and the **Well-Architected Framework**." CAF is one line each in README, 09, 10; 01 names neither. Fix: half-page map (pillars to Consequence Engine; CAF Govern/Manage to the loop; FinOps Framework capabilities).

**D-07 Major — purchases contradict each other and the brief ("AUTOMATE… purchase reservations").** 05: "So purchases get their own desk, and they are **always prepared by the AI and executed by named humans.**" 01: "**Purchases get the most care.** Reservations and savings plans are prepared by the AI and executed only after named humans say OK." Fix: one wording: after two named OKs the AI executes the signed purchase.

## 5. Bloat and questions
No questions to the operator; no D/K/R registers. But:

**D-08 Major — risk and spike lists under new names.** 01 §15 is risk→mitigation: "Predictions are scored; lessons are scoped and expire; replication before trust; the Skeptic; people confirm generalisations". 10 renames spikes: "The honest unknowns are not risks to manage but **questions to explore** — each one a small experiment:". Its slice also has a "done when" gate. Fix: delete both (about 400 words); fold two design points into 07 §5.

**D-09 Major — CHANGELOG jargon wall, lint-exempt.** 1,860 of its 2,289 words are v3.2.1-and-older entries (15 D-numbers, 6 "R3-Data", 3 "P2S"); README links it. Fix: collapse v1–v3.2.1 to ten lines (full text stays in tag ideation-v3.2.1; rule 4 bars touching docs/_archive/).

**D-10 Major — volume and duplication.** 01 is 6,072 words ("This is the whole idea in one place."); 01–11 total 33,152; live total 55,126. Cut 01 §10–12 (764; §11 repeats 03 §12, §12 repeats 08), §15, §16, 06 §11–15 (545; personas "come later"), 09's spine (repeats 01 §14), 02 §10 (repeats 07 §6). Target: 01 about 3,500 words; 01–11 about 24,000.

**D-11 Minor — technology leaking (rule 8).** 04 §17: "its own subscription, its own spending cap, its own identity, no network path into any customer estate, no customer data inside it". Fix: one sentence; the rest to 09.

## 6. Pictures (12 Mermaid, 2 SVG)
Hubs, loops, parallel work: 01 hypothesis states, 02 claim states, 04 Lab campus, 05 Brief states, 06 conversation, 07 Exam. Pipelines in disguise (one path through at least 82% of nodes; lint misses all): 04 ladder (100%), 04 Detector (89%), 05 Move authoring (100%), 06 escalation (100%), 10 slice (82%); 02 day-zero is borderline (69%). `living-system.svg`: the memory hub saves a ring that is the old five-step chain closed into a circle. `four-clocks.svg`: four concentric loops, no coupling drawn.

**D-12 Major — 05 §4.** "When a recurring need has no Move — *"this kind of cleanup comes up every week"* — the Engineer **authors** one. It does not go live on trust:" precedes an eight-box chain. 04's ladder draws no jump to the Lab, though its text promises one. Fix: merge Move and Detector chains into one lifecycle state diagram with demotion edges; make 10's slice a hub map.

## 7. Consistency
Links and anchors pass. Otherwise:

**D-13 Minor — grammar.** 01 has 11 mechanisms; 02 has 12 ("| **Rate and benefit** | the price per unit is negotiable | paying list where a benefit applies |"). "Preview pricing carries an expiry date — a **time cliff**." is in neither table. Fix: 12 rows plus "time cliff".

**D-14 Minor — 06 §5.** "3 decisions need you (about 4 minutes), worth about EUR 1,150/month:" but the items are about 135 + 80 plus an ownership question (that VM costs about 310). Fix: about EUR 215.

**D-15 Minor — report card.** 01: "Results go on a public **report card** — including what it is bad at." 07: "plain, public within the organisation, and always led by what the system is *worst* at". World-public would leak estate numbers. Fix: an organisation card plus a separate open benchmark.

**D-16 Minor — vocabulary.** Ledger vs Notebook (04: "Every experiment is **pre-registered** in the Notebook — written down before it runs"; 01: "| **Experiment Ledger** | The register of predictions and results |"); "steward" three ways (03 hat, 07 human adopter, 08 agent); Skeptic is an agent (01) and a human archetype (06 §13); Detectors come from confirmed findings (04 §13) or Pattern lessons (07 §2). Fix: one name each; add Detector, Terrarium, Unexplained Spend Ledger to the glossary.

**D-17 Minor — unverifiable quote.** 10: "Later, we will design the UIs, the personas, the user flows, systems, etc. and THEN we will design, architect and build it." appears nowhere else in the repo (the guardrail quote is verbatim in archive v1). Check against the brief.

## 8. "I miss a lot"
- **M-01** Advisor-card lifecycle (03 §6, 05).
- **M-02** "What it finds": about 30 one-liners across mechanisms and bank families, none a rule (head of 08).
- **M-03** A real 2026 new-service day-zero, plus a second service showing transfer (02 §6).
- **M-04** One "click OK → resized → verified" story: dry-run diff, guard metric, rollback (05 §4).
- **M-05** Reservation purchase after two OKs: portfolio, scope, term ladder, exchange windows (05 §7).
- **M-06** Territory map: Cost Management, Advisor, budgets, Hybrid Benefit, FinOps toolkit, and what this adds (landscape).
- **M-07** WAF/CAF/FinOps-Framework map (09).
- **M-08** Spend-spike playbook: anomaly alert, private Teams card, pause, verify (06 §5 is three sentences).
- **M-09** Licence and benefit families, showback, budgets, forecasts for Finance (02 §2, 05 §8).
- **M-10** A one-page visual of an owner's week to carry "impress me" (README).

## Top 5 changes, ranked
1. Make Advisor, Cost Management and native recommendations first-class (D-05, M-01, M-06).
2. Purge the two examples outside 07 and the bank; let the lint fail (D-01 to D-04).
3. Show breadth: a "what it finds" showcase and a real day-zero (M-02, M-03, D-03).
4. Close brief gaps: purchase wording, CAF/WAF map, spike playbook (D-06, D-07, M-05, M-07, M-08).
5. Cut about a quarter (D-08 to D-10), merge pipeline pictures (D-12), fix vocabulary (D-13 to D-16).

---

## Orchestrator spot-checks (2026-10-31)

- **Quotes:** 24 of 25 quoted passages exist verbatim in the cited files. The one that did not match where cited — "Preview pricing carries an expiry date — a **time cliff**." — is real but lives in `01-north-star.md` (§3 day-zero story), not in 02's Grammar table, which is exactly D-13's point (it is a mechanism label used in prose but absent from both Grammar tables).
- **D-05:** confirmed — the product name "Advisor" appears in none of README and docs 01–10 (the single lowercase hit in 05 is the generic noun in "A good advisor does not hand over the answer"). This is the most important finding: Advisor and Cost Management were the operator's own opening problem.
- **D-17:** the sentence is a faithful, typo-normalised rendering of the operator's brief ("Later, we will design the UI's, the persona's, the user flows, systems, etc. and THEN we will design, architect and build it."). It exists in the session record, not elsewhere in the repo; it will be marked as the operator's words.
- **Counts and word-counts (D-10):** re-counted — `01-north-star.md` is 6,072 words; docs 01–11 total 33,152. Confirmed.
- **Not re-run:** the in-memory lint-fooling experiments (accepted at face value; the new lint will add the phrase patterns the reviewer named); the percentage-of-nodes measurements for the pipeline-in-disguise diagrams (the new lint computes the longest-path ratio itself).
