# Changelog

All notable changes to the ideation package. Newest first. Versions are git tags; earlier versions are archived under [`docs/_archive/`](docs/_archive/) and are never edited.

## v3 — 2026-10-30 — after review round 2 (tag `ideation-v3`)

A red team and disposition audit, a Microsoft-Learn-grounded fact-check and a brief-compliance and consistency review raised **15 + 9 numbered findings and 38 checked claims**. Everything was accepted except one reviewer artefact (R2-C-01: "301 catalog IDs" — the catalog really has 305) and one over-cautious fact-check verdict (the 63% AI-spend figure). The row-by-row record, including corrections to the round-1 record, is in [`docs/reviews/round-2/disposition.md`](docs/reviews/round-2/disposition.md).

### Safety model — now one normative, mechanically checkable set of rules ([06](docs/ideation/06-closed-loop-actions-and-autonomy.md))
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
- [`docs/ideation/00-one-page-overview.md`](docs/ideation/00-one-page-overview.md) — the executive visual; the catalog's *At a glance*; research/05's *Where to start*.
- [`docs/research/02-third-party-and-oss-landscape.md`](docs/research/02-third-party-and-oss-landscape.md) — 22 commercial products in four archetypes, the open-source gap, four independently verified claims, ideas to borrow.
- [`tools/check-docs.py`](tools/check-docs.py) — a standard-library-only lint for links, anchors, the catalog's classification rules, README counts, Mermaid labels and retired phrases.
- [`docs/reviews/round-2/`](docs/reviews/round-2/) — raw reports with spot-checks, and the disposition.

### Housekeeping
- v2 frozen in [`docs/_archive/round-2-v2/`](docs/_archive/round-2-v2/) (tag `ideation-v2`). The round-1 disposition is left as written; corrections to it are recorded in the round-2 disposition.

## v2 — 2026-10-30 — after review round 1 (tag `ideation-v2`)

Three independent reviewers (product and human factors, safety and governance, strategy) raised **41 findings**; all were accepted, four with a qualification. The full row-by-row record is in [`docs/reviews/round-1/disposition.md`](docs/reviews/round-1/disposition.md).

### Corrected facts
- **Virtual WAN P2S sizing.** Connection capacity is **banded**, not 500 per scale unit (units 1–3 → 500, 4–6 → 1,000, 7–10 → 5,000, 11–20 → 10,000, then +10,000 per extra pair of instances); throughput is linear at 0.5 Gbps per unit. Scaling can reconnect users. The seed example is now an **Assist-level, disruption-bearing** action, not "low-risk automation".
- **Query audit (LAQueryLogs).** The Microsoft documentation is inconsistent about what it records; scheduled alert executions are not logged. Coverage is **measured per workspace with a canary query**, and the audit should be switched on early because it is off by default.
- **First-party landscape.** Defender governance rules (owner → manager email), the SRE Agent (approve-then-execute) and Sentinel SOC optimization (unused tables) already exist; the claimed gaps are narrowed to the *cost* combination. New [first-party tear-down](docs/research/06-first-party-teardown.md).
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
