# Changelog

All notable changes to the ideation package. Newest first. Versions are git tags; earlier versions are archived under [`docs/_archive/`](docs/_archive/) and are never edited.

## v4 — 2026-10-31 — rebuilt around a learning system (tag `ideation-v4`)

**Why.** The operator rejected the whole v1 → v3.2.1 package. It was built around his two example findings (cast as "seed examples" and release plays), it lacked the heart of the idea — *how the AI learns about new Azure services, gathers knowledge, investigates cost implications, experiments and recommends* — it was buried in governance paperwork (decisions, assumptions, risks, kill criteria, threat catalogue) that has no place in ideation, and its pictures were linear pipelines.

**What changed.** The entire live package was replaced; **v3.2.1 is archived untouched** in [`docs/_archive/round-3-v3.2.1/`](docs/_archive/round-3-v3.2.1/) (tag `ideation-v3.2.1`) and its reusable parts (interaction concepts, ownership, moonshots, the 145-trap research, the guardrail inventory) were mined, not deleted.

### New
- A **north star** — [01](docs/01-north-star.md): "a scientist for Azure's economics" with five faculties (STUDY · SURVEY · TEST · ACT · GROW) around one memory, four clocks, a cast of 13 agents, and the *founding exam*.
- Six deep-dives: [02 Studying Azure](docs/02-learning-azure.md) (Atlas, Cost Grammar, claims with receipts, Knowledge CI, day zero) · [03 The estate and the investigation](docs/03-estate-and-investigation.md) (Estate Model, intent, human graph, Agenda, Skeptic, Consequence Engine) · [04 Experiments and the Lab](docs/04-experiments-and-the-lab.md) (benches, wind tunnel, Time Machine, Terrarium, Detectors) · [05 Recommend, act, verify](docs/05-recommend-act-verify.md) (Brief, Moves, earned autonomy, Commitment Desk, verification) · [06 People and conversation](docs/06-people-and-conversation.md) · [07 Getting smarter](docs/07-getting-smarter.md) (predictions, Exam, report card, Commons).
- [08 Outer rims](docs/08-outer-rims.md) (~35 learning-centred moonshots) · [09 Guardrails, later](docs/09-guardrails-later.md) (themes only) · [10 What next](docs/10-what-next.md) (the thinnest slice) · [11 Press release from the future](docs/11-press-release-from-the-future.md).
- Research: [the landscape through the lens of learning](docs/research/landscape.md), [inspirations — how agents learn](docs/research/inspirations.md) (24 papers, every identifier checked against arXiv), and the 145-trap catalogue re-cast as an [exam bank](docs/research/exam-bank-cost-traps.md).
- Two pictures with loops, not lines: [living system](docs/img/living-system.svg) and [four clocks](docs/img/four-clocks.svg).
- A new [`tools/check-docs.py`](tools/check-docs.py): links, anchors, diagrams, orphans — and guards that fail the build if the operator's two examples creep into the design or governance paperwork returns.

### Removed from the live package (kept in the archive)
Decision register, assumption and risk registers, kill criteria, spikes, the 305-row opportunity catalog as a design artefact, release plans built on the two examples, the threat catalogue, and every linear pipeline picture.

### Rules
[`AGENTS.md`](AGENTS.md) now also records: this is a learning system, not a rulebook; the two original findings are exam questions only; pictures show loops; ideation is not technology; no governance paperwork during ideation.

## v3.2.1 — 2026-10-31 — visibility rule recorded (tag `ideation-v3.2.1`)

- **D6 decided: the repository stays private until the operator says to switch it.** No agent changes its visibility or publishes its content; every "publish" step in the plan (K5, Phase 8) waits for that word.
- New [`AGENTS.md`](AGENTS.md) records this and the other standing rules (assume rather than ask during ideation; MIT; keep history; run the lint) so they survive a session restart and bind sub-agents.

## v3.2 — 2026-10-31 — operator decision: MIT (tag `ideation-v3.2`)

- **D2 decided: MIT**, for code, documents and playbook specs. [`LICENSE`](LICENSE) added (copyright holder: the package owner named throughout, Tino Donderwinkel). MIT is also the FinOps toolkit's licence, so detector specs and Waste Lab scenarios can be contributed upstream without licence friction.
- **Stance recorded:** an open-source demonstrator of what AI and Foundry agents can do inside governed workflows. The remaining open items — name (D1), employer/OSPO/IP (D13), and the design-level D3–D12 and D14–D18 — are **not ideation questions**: [plan/01 §3](docs/_archive/round-3-v3.2.1/plan/01-assumptions-risks-decisions.md#3-decisions-decided-or-assumed) now carries a status board with each recommended option as an *assumed default* and a *revisit trigger*. Nothing was dropped and nothing blocks; the safety rules are unchanged (D14 stays "yes": purchases are never L3–L5).
- Softened accordingly: the "rename within about two weeks" and "start the approval now" advice (the repository stays private under its working title until publication, D6); a lab-only demonstration on the Waste Lab needs no outside signer for the Phase-0.5 exception (D17).
- No change to the catalog, the safety model or the counts (26 assumptions, 27 risks, 18 decisions).

## v3.1 — 2026-10-30 — after the post-v3 audits (tag `ideation-v3.1`)

Two further read-only audits of the committed v3 — *is the round-2 record true?* and a *contradiction hunt* over the live package — found **17 defects, all real**. The documents keep their v3 header; this patch is recorded here. Row by row in [`docs/reviews/round-2/disposition.md` §12](docs/_archive/round-3-v3.2.1/reviews/round-2/disposition.md#12-post-v3-audit-v31); raw reports in [04](docs/_archive/round-3-v3.2.1/reviews/round-2/04-audit-disposition-truth.md) and [05](docs/_archive/round-3-v3.2.1/reviews/round-2/05-audit-contradiction-hunt.md).

### Fixed
- **22 catalog rows reclassified.** The examples round 2 named were a sample; a whole-catalog scan found the rest. **15 → R3:** paid-plan and commitment changes (IDLE-12, RATE-13/17/18/19/24, TELE-09, SEC-01/04, AI-14/23) and removal of redundancy or scarce capacity (IDLE-31, IDLE-33, DATA-13, PLAT-14). **3 → R3-Data:** availability and network-monitoring tests (IDLE-39, TELE-14, NET-12). **3 → R2:** IDLE-07, IDLE-11, IDLE-28. **1 → advice only:** RATE-15. R1 now means "can be put back exactly; durable state preserved"; R2 means "a recovery path exists and is proven"; a row that lists alternatives takes the class of its most consequential one.
- **Normative text caught up with its own glossary and record:** control-plane claims are *signed*, and the signature is verified at re-read; the signature record and the provider's transaction ID are specified; held-out evaluation sets are held by the independent evaluation custodian everywhere (four stale "owned by the Warden" statements); the full eight-field enrolment key everywhere, and the FAQ no longer lets "your manager" opt in; dropping log data is R3-Data, not R3; rollback is promised only "where the class allows"; L5 has no write actions; the shared-workspace log example classes silent consumers consent-required or inform-only; the voice script's cost brake is conditional on every condition of the class's contract.
- **Evidence:** five claims the round-2 fact-checker could not read were re-verified against primary sources — the Advisor "up to a day" delay, the 24-hour and 48-hour settings delays, the Advisor alert categories, the management-group exclusion for FOCUS exports, the Azure Optimization Engine README banner. All confirmed; research/01 and the disposition now agree.

### Tooling
- [`tools/check-docs.py`](tools/check-docs.py) flags, as errors, a catalog row that reads like a transaction, reduces observability data or removes redundancy but wears a lower class, and warns on an R1 row that deletes something; an exemption needs a written reason. New `--self-test` (12 cases) proves it catches mislabelled rows and passes clean ones.

## v3 — 2026-10-30 — after review round 2 (tag `ideation-v3`)

A red team and disposition audit, a Microsoft-Learn-grounded fact-check and a brief-compliance and consistency review raised **15 + 9 numbered findings and 38 checked claims**. Everything was accepted except one reviewer artefact (R2-C-01: "301 catalog IDs" — the catalog really has 305) and one over-cautious fact-check verdict (the 63% AI-spend figure). The row-by-row record, including corrections to the round-1 record, is in [`docs/reviews/round-2/disposition.md`](docs/_archive/round-3-v3.2.1/reviews/round-2/disposition.md).

### Safety model — now one normative, mechanically checkable set of rules ([06](docs/_archive/round-3-v3.2.1/ideation/06-closed-loop-actions-and-autonomy.md))
- **Classification is derived, not declared:** an ordered rubric (first match wins) assigns **one** class from an operation's typed effects; a declared class below the derived one is rejected. **R3-Data** is the only enum value (R3-D is a catalog column abbreviation). Observability and evidence data → R3-Data; backups and business data → R3; every **transaction** → R3, L2 at most.
- **Catalog contradictions fixed:** DATA-19, DATA-28, TELE-30, TELE-31, NET-16 → R3-Data, L2; **IDLE-29** (cancelling plans) → R3, L2, security co-sign; RATE-03 and RATE-22 → L2.
- **Silence is never consent — closed properly:** one **enrolment key** (owner or delegate, tenant, scope, environment, action class, reversibility class, expiry, envelope version); *dev never authorises prod*; **affected-party consent** for shared resources (named acknowledgement or a named risk acceptance; "no objection" is silence).
- **Instrumentation is an action** (own approval, cost cap, end date, deletion rule); "Observing" expires.
- **Control-plane tags** are signed, versioned claims; revalidator ≠ changer; any change invalidates enrolment, envelope membership and approvals.
- **Cost brake** bound to asset IDs, expiry and a security co-sign, with an independent signal and a page-a-human default; **commitment transactions** have one normative approval matrix and a canonical manifest (price, currency, billing scope, quote expiry, signer, nonce); **custodian** appointment ≠ action, retirement needs a second key; **widening** an escalation needs authorisation; **ledger erasure** is a release blocker; the **trust root (D16)** is a prerequisite for any behaviour-affecting artefact.
- Threats **T39–T41** (classification laundering, instrumentation creep, custodian overreach); invariants 3, 4, 5, 6, 12, 15, 16 tightened (still 16).

### Product and plan
- **Release 1 = five plays on one skeleton** (stated identically everywhere); item 4 is now **Orphans and Advisor-recommendation closure** — the brief's own problem. **Release 1 proves AI-assisted closure only**; **enrolled autonomy (L3/L4)** is a separate hypothesis (A25); **L5** is reserved — advice and simulation only.
- **Phase 0.5 is "no remediation writes"**, with entry conditions and one narrowly approved instrumentation exception (D17). Slices renamed **SL0–SL8** (they collided with spike IDs S1–S22).
- **Spike register:** three waves, dependencies, owner, decision date, result and ADR slot; S2 (Advisor access) on the critical path; P2S scaling treated as disruptive until measured.
- New **build / ride / contribute** call per Release-1 play; third-party overlap logged quarterly (R27); new decisions **D17** and **D18**; assumptions 24 → 26, risks 25 → 27, decisions 16 → 18, threats 38 → 41.

### Corrected facts (primary sources, 2026-10-30)
- **Reservation exchange** is narrowing: from **1 Feb 2027** reservations bought after that date are not exchangeable where savings plans cover the service; earlier ones keep one final exchange (not "until further notice").
- **P2S scaling:** Microsoft says to *plan for downtime*; the "TCP reconnects" sentence is the ExpressRoute entry (a round-1 attribution error, owned in the disposition).
- Toolkit v15 *fixed* the idle Application Gateway and idle public-IP alert queries (it did not add the alerts); the Azure MCP `advisor` tools include state-write and remediation tools; `optimization` is not compute-only; Defender's manager mail is a weekly overdue summary; SRE Agent default modes and about USD 292/month always-on; budgets can include reservation purchases; "Easy Buttons" is an *additional* State-of-FinOps theme; Application Gateway "min 0" does not remove the fixed charge; "inconsistent" → "unreconciled" for the query-audit pages. WAF pillar and CAF methodology names verified.

### New material
- [`docs/ideation/00-one-page-overview.md`](docs/_archive/round-3-v3.2.1/ideation/00-one-page-overview.md) — the executive visual; the catalog's *At a glance*; research/05's *Where to start*.
- [`docs/research/02-third-party-and-oss-landscape.md`](docs/_archive/round-3-v3.2.1/research/02-third-party-and-oss-landscape.md) — 22 commercial products in four archetypes, the open-source gap, four independently verified claims, ideas to borrow.
- [`tools/check-docs.py`](tools/check-docs.py) — a standard-library-only lint for links, anchors, the catalog's classification rules, README counts, Mermaid labels and retired phrases.
- [`docs/reviews/round-2/`](docs/_archive/round-3-v3.2.1/reviews/round-2/) — raw reports with spot-checks, and the disposition.

### Housekeeping
- v2 frozen in [`docs/_archive/round-2-v2/`](docs/_archive/round-2-v2/) (tag `ideation-v2`). The round-1 disposition is left as written; corrections to it are recorded in the round-2 disposition.

## v2 — 2026-10-30 — after review round 1 (tag `ideation-v2`)

Three independent reviewers (product and human factors, safety and governance, strategy) raised **41 findings**; all were accepted, four with a qualification. The full row-by-row record is in [`docs/reviews/round-1/disposition.md`](docs/_archive/round-3-v3.2.1/reviews/round-1/disposition.md).

### Corrected facts
- **Virtual WAN P2S sizing.** Connection capacity is **banded**, not 500 per scale unit (units 1–3 → 500, 4–6 → 1,000, 7–10 → 5,000, 11–20 → 10,000, then +10,000 per extra pair of instances); throughput is linear at 0.5 Gbps per unit. Scaling can reconnect users. The seed example is now an **Assist-level, disruption-bearing** action, not "low-risk automation".
- **Query audit (LAQueryLogs).** The Microsoft documentation is inconsistent about what it records; scheduled alert executions are not logged. Coverage is **measured per workspace with a canary query**, and the audit should be switched on early because it is off by default.
- **First-party landscape.** Defender governance rules (owner → manager email), the SRE Agent (approve-then-execute) and Sentinel SOC optimization (unused tables) already exist; the claimed gaps are narrowed to the *cost* combination. New [first-party tear-down](docs/_archive/round-3-v3.2.1/research/06-first-party-teardown.md).
- **FOCUS.** A native FOCUS export exists (labelled 1.2-preview against the ratified FOCUS 1.4).

### Safety and governance
- New reversibility class **R3-Data** (collection-reducing actions; never L3/L4) and **exactly one class per action** plus separate attributes.
- **Silence is never consent:** veto windows need affirmative enrolment; ownerless resources go to a named **orphan custodian**, not a countdown.
- **Purchases, exchanges, renewals and cancellations are never L3–L5**; each is signed by the authorised buyer against a finite manifest.
- Approvals bind to the exact artefact (commit SHA, plan digest, target-state hash); **tenant identity on every artefact, fail closed**; locks and legal holds are never bypassable; the **cost brake** is narrowed to pre-certified classes.
- **Control-plane tags**, an **independence profile** for the Challenger and Auditor, **governed releases** for every behaviour-affecting artefact, threats **T31–T38**, and **16 candidate invariants** (was 13).

### Product and plan
- **Release 1 = five items**; schedules, commitments, security-tool economics, adjacent spend and sustainability are **parked** with re-open triggers; two catalog rows and two moonshots are **retired**.
- New **Phase 0.5 kill-or-confirm sprint** (four weeks, no writes) and **kill criteria K1–K7**.
- **Private-first escalation ladder** — nobody is named in a shared space for not answering.
- **Net realised value**, one financial outcome with multi-touch provenance, and a **pre-registered pilot design** with a comparison condition.
- Class-specific undo wording everywhere; card footers read "AI-composed · figures computed".
- Assumptions 20 → 24, risks 20 → 25, decisions 12 → 16; spikes 22 → 19 active.

### Housekeeping
- v1 frozen in [`docs/_archive/round-1-v1/`](docs/_archive/round-1-v1/) (tag `ideation-v1`).
- Raw reviewer reports preserved verbatim with the orchestrator's spot-checks.

## v1 — 2026-10-30 — first full ideation set (tag `ideation-v1`)

North-star vision, 305-row opportunity catalog, deep dives of the two seed examples, a 20-role agent crew, interaction concepts, the closed loop and autonomy ladder, ownership design, the guardrail territory, 40 moonshots, metrics and economics, a working-backwards PR/FAQ, a phased follow-up plan, and a primary-source research set.
