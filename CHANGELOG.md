# Changelog

All notable changes to the ideation package. Newest first. Versions are git tags; earlier versions are archived under [`docs/_archive/`](docs/_archive/) and are never edited.

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
