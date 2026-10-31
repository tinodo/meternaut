# Rubber-Duck Round 2 — Review A: Red team and disposition audit

> **Reviewer:** rubber-duck agent (independent, read-only) · **Date:** 2026-10-30 · **Reviewed:** ideation package **v2** (git tag `ideation-v2`, commit d44de2d)
> **Status of this file:** the reviewer's report, preserved **verbatim** (only this header was added). The orchestrator's spot-check of the reviewer's specific quotes is appended at the very end; the disposition of each finding is in [disposition.md](disposition.md).
> **Lens:** attack the *revisions* made after round 1 — new contradictions, new loopholes, overcorrection — and audit whether the round-1 disposition is actually true.

---
## 1) Verdict

- **Two v2 invariants are still directly violated by the catalog:** collection-reducing actions remain labelled `R1 | L3`, and a cancellation remains `R2 | L3`. These are **Critical** design defects, even though `Ceil` is labelled hypothetical.
- The P2S example still treats **“no objection” as sufficient** for a shared, disruption-bearing change, despite the catalog requiring every affected party’s explicit consent.
- Phase 0.5 is described as **“no writes”** while it enables query audit and sends live Wizard-of-Oz cards before the stated Phase-1 outreach-ethics precondition. That is a guardrail bypass, not merely wording.
- v2 substantially improves the safety model, but several new controls remain **aspirational rather than closed**: the governed-release trust root, control-tag revalidation, cost-brake signal independence, and ledger-erasure design are not yet specified enough to enforce.
- The product remains viable as an **AI-assisted closure system**. Release 1 does **not** validate scalable autonomy: it is mostly Advise, with narrow Assist paths. Do not market it as proving L3/L4 scale until that hypothesis is separately tested.

## 2) Findings

| ID | Severity | Where | What — exact package quote | Why it matters | Concrete fix |
|---|---|---|---|---|---|
| R2-A-01 | **Critical** | `docs/ideation/02-opportunity-catalog.md` §6, DATA-19/DATA-28; `docs/ideation/06-closed-loop-actions-and-autonomy.md` §2 | “`Ingestion capture copies nobody reads … Remove | R1 | L3`”; “`Change feed or inventory … Disable | R1 | L3`”; but R3-Data is “**Any collection-reducing action**” and “**Never L3 or L4**.” | Stopping ingestion capture, change feed, or inventory creates prospective information loss. These rows permit a veto-window path that bypasses the data-owner/security co-sign required for R3-Data. | Classify actions from typed effects, not playbook labels. Add a mandatory `prospectiveInformationLoss` flag; reject any R1/R2/L3/L4 action with that effect. Reclassify DATA-19 and DATA-28 as R3-Data; review TELE-30 and all export/copy controls. Add a catalog lint test. |
| R2-A-02 | **Critical** | `docs/ideation/02-opportunity-catalog.md` §1, IDLE-29; `docs/ideation/06-closed-loop-actions-and-autonomy.md` §§2, 6; `docs/ideation/08-trust-safety-and-guardrail-topics.md` invariant 16 | “`Cancel plans; close subscription | R2 | L3`”; versus “**Purchases, exchanges, renewals and cancellations are never L3–L5.**” | An L3 path could cancel a support/security/backup plan after a veto window instead of requiring an authorised buyer’s signed manifest. “Ceil is hypothetical” does not excuse an invalid safety candidate in the catalog. | Split “close subscription” from “cancel plan.” Make all cancellations a typed transaction semantic that is mechanically rejected outside L2 signed-manifest flow. Remove L3 from IDLE-29. |
| R2-A-03 | **High** | `docs/plan/00-follow-up-plan.md` Phase 0.5; `docs/ideation/03-deep-dives-seed-examples.md` §1.5 | Phase 0.5 is “**no writes**,” yet activities say “enable **query audit (LAQueryLogs) on pilot workspaces now**”; the log design calls this “an **R1** action (it *adds* collection).” | The kill sprint performs a customer configuration/data-collection change before the Guardrail Charter, data-handling rules, and write-safety harness exist. It also creates a privacy and cost footprint. | Either defer this action until Phase 1, or rename Phase 0.5 to “no remediation writes” and require a narrowly scoped pre-Phase-0.5 instrumentation approval: data owner, privacy/security review, retention, cost cap, and rollback/removal date. |
| R2-A-04 | **High** | `docs/ideation/06-closed-loop-actions-and-autonomy.md` §2; `docs/ideation/03-deep-dives-seed-examples.md` §§0, 1.4 | R3 includes “**shortening retention**”; R3-Data also includes “**shortened retention**.” The seed summary says “**R3 for dropped data**,” while §1.4 uses R3-Data. | The claimed “one exact class per operation” is not currently possible. Class determines approvers and autonomous ceiling, so ambiguity can route a retention/data-loss change through the wrong approval path. | Define a mutually exclusive rubric: e.g., R3 for immediate destruction of existing data/state; R3-Data for prospective collection reduction. Specify how retention-policy changes are classified when they also purge existing data. Lint every playbook against it. |
| R2-A-05 | **High** | `docs/ideation/02-opportunity-catalog.md` Decision gates; `docs/ideation/03-deep-dives-seed-examples.md` §§2.6–2.7 | Catalog: “**Shared resources need every affected party’s explicit consent**.” P2S card: “`informed by me; no objection so far`”; execution: “**approved by the Network Platform owner**.” | “No objection” is silence, not explicit consent. This example authorises a change known to reconnect users while affected business-unit IT teams have merely been notified. | Enforce named, authenticated affected-party consent—or a policy-defined, signed quorum/risk-acceptance rule—before execution. Change the card and preconditions; do not equate notice with consent. |
| R2-A-06 | **High** | `docs/ideation/06-closed-loop-actions-and-autonomy.md` §5; `docs/ideation/07-ownership-and-organization.md` §8 | “recently-written-or-inferred tags do not qualify … until **revalidated**”; control-plane tags require “an **independent authority**.” | Cooling-off is only a delay unless revalidation is independently sourced, version-bound, and invalidated by subsequent changes. A manipulated `env`, `cost-exempt`, ownership, or data-class tag could eventually steer automation. | Require signed tag claims with a source/version; ensure revalidator ≠ modifier; invalidate enrolment/envelope eligibility on every control-tag change; bind the approved action to the exact tag-claim version and recheck immediately before execution. |
| R2-A-07 | **High** | `docs/ideation/07-ownership-and-organization.md` §7 | “The custodian is the **owner of last resort**”; “**Retire** \| Delete — a *named human decision* \| Only after snapshot/backup.” | A subscription owner, platform team, or FinOps lead can become a broad substitute owner and delete a resource after an agent concludes it is orphaned. No independent orphanhood review, shared-consumer consent, or custodian conflict rule is specified. | Limit custodian authority to triage/park/restrict by default. Require independently corroborated orphanhood plus a second authority for R2 retirement; require affected-party outreach and change approval for shared resources. Separate custodian appointment/review from custodian action approval. |
| R2-A-08 | **High** | `docs/ideation/06-closed-loop-actions-and-autonomy.md` §6; `docs/ideation/04-agent-crew.md` Buyer | A finite manifest is “**what, how much, which scope, which term**”; the Buyer must not act when “**price, term, scope or quantity differ**.” | Price is not actually named as a signed manifest field. The system cannot prove that the authorised person approved the actual price, currency, billing account/legal entity, offer, or effective transaction conditions. | Define a canonical signed manifest digest: SKU/offer, billing scope/legal entity, quantity, term, total and unit price/currency, quote timestamp/expiry, policy/risk-budget version, signer identity, nonce, and provider transaction ID. Any mismatch requires a new signature. |
| R2-A-09 | **High** | `docs/ideation/04-agent-crew.md` §§3.4, 4.1, 4.6; `docs/plan/01-assumptions-risks-decisions.md` D16 | “ships only as a **governed release**”; but D16 remains “**Trust root and emergency revocation** … Maintainers only · maintainers plus … · the customer alone.” | Governed release is described as a present control while its authority root, quorum, signing boundary, compromise recovery, and revocation path remain undecided. The Warden verifies releases produced under the same unresolved root. | Make D16 a prerequisite before any behaviour-affecting release. Specify key custody, approval quorum, separation from Warden administration, signed provenance, emergency revocation, pinned rollback, and independent audit of release state. |
| R2-A-10 | **High** | `docs/ideation/04-agent-crew.md` §4.6 | “A different model family or provider **where available; otherwise a different version and configuration**”; held-out sets are “**owned by the Warden**.” | Different prompts/configuration and a separate retrieval route are not independent if data ingestion, release authority, and evaluation-set ownership share a trust root. A compromised source or Warden can make Challenger/Auditor agreement meaningless. | Require separate service identities and immutable evidence sources; assign held-out-set custody to an authority independent of release approval and Warden operation; establish promotion thresholds that fail closed when independence evidence is weak. |
| R2-A-11 | **High** | `docs/ideation/06-closed-loop-actions-and-autonomy.md` §3 item 11; `docs/ideation/08-trust-safety-and-guardrail-topics.md` T38 | Cost brake needs an “**independent signal (not the same data that raised the case)**” and a “**service-owner-recorded safe-to-pause contract**.” | “Not the same data” does not establish independent telemetry origin, authority, or tamper resistance. The same compromised service/control plane could shape the contract, both signals, or the apparent incident state. | Bind safe-to-pause contracts to asset IDs, expiry, security/service-owner co-sign, and immutable policy version. Require telemetry from independently administered sources; prevent one principal from changing contract/signal and triggering the brake; fail to paging humans on any integrity uncertainty. |
| R2-A-12 | **Medium** | `docs/ideation/05-human-interaction-concepts.md` §3 | “A shared post names the **resource and the decision needed**”; the ladder posts to a team channel after no response. | Not naming the silent person does not prevent disclosure. Resource names, costs, and the decision may reveal a sensitive project, a security posture, or the likely non-responsive owner to people without a need to know. | Gate every widened audience on recipient authorisation and data classification. Use an opaque routing request or aggregate message until authority is established; prohibit shared posts for regulated/sensitive cases. |
| R2-A-13 | **Medium** | `docs/ideation/03-deep-dives-seed-examples.md` §§1.5, 1.8 | “`start watching` — an **R1** action (it *adds* collection) that opens an **Observing** state”; “A case can be *worth doing later*.” | Observing has no mandatory end date, storage/cost budget, data minimisation rule, or separate consent requirement when it activates new collection. It can become an indefinite instrumentation loophole. | Separate passive observation from active instrumentation. Instrumentation needs its own approval, scope, end date, retention/deletion rule, cost ceiling, and notification. Cases must expire or be re-authorised. |
| R2-A-14 | **Medium** | `docs/ideation/08-trust-safety-and-guardrail-topics.md` invariant 6 | Evidence and personal data are “**stored separately and referenced by hash, so … erasure and retention duties remain possible**.” | Separation plus hashes does not yet demonstrate the stated outcome. The design lacks rules for hash/linkability minimisation, per-tenant key destruction, correction/tombstone records, ledger metadata retention, and proof that deleted evidence cannot be reconstructed. | Define the event schema and prohibited fields; use tenant-scoped keyed references; specify correction/redaction/tombstone mechanics; test erasure while validating chain integrity; make this a release blocker, not just a G4 question. |
| R2-A-15 | **Medium** | `docs/ideation/02-opportunity-catalog.md` §Selection and status; `docs/plan/00-follow-up-plan.md` Phase 7 | Release 1 is “**Advise only**” for log usefulness and PTU; P2S is “**Assist**”; orphans are “**Advise → Assist**.” | This is sensible safety scoping, but it does not test the central scale claim. Release 1 can prove AI-assisted closure, not whether affirmative enrolment and policy envelopes make L3/L4 economical or usable. | Keep the safety limits. Split milestones and claims: validate **closure/Assist** first; later validate **enrolled autonomy** using a non-destructive, tightly bounded action class with pre-registered enrolment, fatigue, and regret criteria. |

## 3) Disposition audit

| Finding ID | Claimed change location | Status | Evidence |
|---|---|---:|---|
| R1 | research/04 Part B; ideation/03 §2.3 | **Confirmed** | `research/04` says connection capacity is “**banded, not linear**”; `03 §2.3` uses a “**versioned lookup**.” |
| R2 | ideation/06 §§2, 9; ideation/05 §4 | **Confirmed** | `06 §9`: “**Undo is class-specific**”; `05 §4` distinguishes R0/R1, R2, and “**R3 / R3-Data — No undo**.” |
| G-01 | ideation/01 §4; ideation/06 §6; ideation/04 Buyer | **Confirmed** | `01 §4`: “**Purchases, exchanges, renewals and cancellations are never L3–L5**”; Buyer ceiling is “**L2 only**.” |
| G-02 | ideation/06 §2; catalog | **Partly** | R3-Data exists and says “**Never L3 or L4**,” but DATA-19/DATA-28 remain `R1 | L3`; see R2-A-01. |
| F1 | research/01 §3; research/06 §§1–2 | **Confirmed** | Research now explicitly records Defender governance rules, SRE Agent Review mode, and Sentinel SOC optimisation with scope limits. |
| F2 | plan/00 Phase 0.5; plan/01 §4 | **Confirmed** | Four-week Phase 0.5 and K1–K7 exist. However, the “no writes” assertion conflicts with enabling query audit; see R2-A-03. |
| R3 | ideation/07 §7 | **Confirmed** | “**owner of last resort**”; deletion is “a **named human decision**”; no-custodian resources are “**left untouched**.” |
| R5 | ideation/10 §8 | **Confirmed** | “**Before any data is seen**” pre-registration, a “**comparison condition**,” and “**Independent judges**.” |
| R7 | ideation/05 §3 | **Confirmed** | “**Private before public**”; “**Silence is never approval**”; ladder ends in a human decision. |
| R9 | ideation/06 §3 item 11 | **Confirmed** | Brake requires safe-to-pause contract, independent signal, incident/SLO check, enumerated R1 action, rate limit, review. |
| R10 | ideation/10 §§1–2.3 | **Confirmed** | “**Net realised value**” subtracts regret/platform cost; “**One saving, one financial outcome**” retains multi-touch provenance. |
| R11 | ideation/07 §2 | **Confirmed** | Adds change/ITSM, billing, shared-platform, and SOC counterparts that “**decide whether a change may happen at all**.” |
| R12 | research/04 A.2; ideation/03 §1.5 | **Confirmed** | Docs inconsistency is recorded; “**Unknown coverage blocks any destructive recommendation**”; canary is required. |
| G-03 | ideation/06 §3 item 5 | **Confirmed** | “**Legal holds and resource locks are never bypassable**.” |
| G-04 | ideation/06 §3 item 6; ideation/08 G1-07 | **Partly** | Final rule requires affirmative enrolment and delivery proof, but “**authenticated**” remains a candidate question in G1-07 rather than a defined enforcement requirement. |
| G-05 | ideation/06 §5; ideation/07 §8 | **Confirmed** | Control-plane tags require “**an independent authority**,” audit, and cooling-off revalidation. Sufficiency remains open; see R2-A-06. |
| G-06 | ideation/04 §4.6 | **Confirmed** | Explicit steward/configuration/data/model/evaluation profile and recurring correlated-failure drill are present. |
| G-10 | ideation/06 §2; catalog | **Partly** | “**one exact class per operation**” is stated, but R3 and R3-Data both include shortened retention; see R2-A-04. |
| G-11 | ideation/06 §3 item 1; §4 | **Confirmed** | Approval binds tenant/resource IDs, source commit SHA, rendered-plan digest, pipeline identity, and target-state hash. |
| G-12 | ideation/08 invariant 6; ideation/04 §4.5 | **Confirmed** | Minimal signed hash chain and separate evidence/personal-data stores are stated. The erasure design remains incomplete; see R2-A-14. |
| G-13 | plan/02 §§4.1–4.2 | **Confirmed** | Control matrix and negative write-safety harness are explicit prerequisites for customer-facing write tests. |
| F3 | plan/01 §4 | **Confirmed** | K1–K7 each have trigger, response, decider, and check cadence. |
| F4 | plan/01 §5; research/06 §§3–5 | **Confirmed** | Explicit ride/copy/build/contribute map, K4 trigger, and quarterly re-check list exist. |
| F9 | plan/03 S1b, S13; ideation/06 §4 | **Confirmed** | IaC detection/source-fix path and stale approval rejection after re-render/rebase are explicitly scoped. |

### False or overstated disposition claims

1. `docs/reviews/round-1/disposition.md` §1 says **“Accepted and applied | 41.”** That overstates completion: G-02 and G-10 are only partly applied because contradictory classifications remain in v2.
2. The G-02 disposition claims the R3-Data correction covers catalog behaviour. `DATA-19` and `DATA-28` contradict it directly.
3. The G-04 disposition says veto windows need **“affirmative, authenticated enrolment.”** The operative text specifies affirmative enrolment and proof of delivery; authentication is still posed as a guardrail question/candidate.
4. The F2 disposition’s **“no writes”** framing is not literally true while Phase 0.5 enables query audit and sends cards before the stated Phase-1 outreach-ethics gate.

## 4) Contradictions between documents

1. **R3 versus R3-Data is non-exclusive.** `docs/ideation/06` §2 assigns “shortening retention” to both classes, while `docs/ideation/03` uses both labels for data-loss scenarios. This defeats the stated one-class invariant.
2. **Catalog cancellation versus autonomy invariant.** `IDLE-29` permits `Cancel plans; close subscription | R2 | L3`; `06` §6 and invariant 16 prohibit cancellations above L2.
3. **Shared-resource consent versus P2S example.** The catalog requires every affected party’s explicit consent; the P2S example permits action after people are merely informed and raise “no objection.”
4. **No-write sprint versus actual changes.** Plan 0.5 says “no writes,” but enables query audit, which the seed design itself labels an R1 action that adds collection.
5. **Private-first escalation versus data minimisation.** The ladder prevents naming non-responsive people but deliberately posts the case and resource in a team channel without an audience-authorisation or sensitivity gate.

## 5) Silently dropped or weakened content

**No confirmed valuable content was silently dropped.** The v1→v2 diff shows the substantive removals are recorded:

- M-05 meeting-intent mining and M-38 multi-cloud are explicitly retired in `docs/ideation/09-outer-rims-moonshots.md` §Decision status.
- Schedules, commitments, security-tool economics, adjacent spend, and sustainability are explicitly parked in `docs/ideation/02-opportunity-catalog.md` §Selection and status.
- L5 commitment transactions, broad cost-brake behaviour, the old P2S sizing model, and universal undo wording were changed in ways documented by the round-1 disposition and changelog.
- The conspicuous v1 README link to `research/02-third-party-and-oss-landscape.md` is **not** a v2 deletion: that file is absent in both `ideation-v1` and `ideation-v2`.

Do not claim “nothing silently dropped” as proof that nothing was weakened; the real issue is not missing content but the unresolved safety contradictions above.

## 6) What v2 does especially well — keep

- The P2S correction is materially better: banded connection capacity, deterministic lookup, customer price data, disruption disclosure, and Assist-only execution.
- Replacing silence-to-delete with a named orphan-custodian path is the correct conceptual reversal.
- R3-Data is the right category and correctly rejects fake “undo” promises for uncollected future evidence.
- Exact-plan binding, stale-approval rejection, tenant fail-closed language, and the negative write-safety harness provide a credible enforcement direction.
- The five-item Release-1 cut, pre-registered comparison pilot, first-party overlap kill criterion, and explicit status model make the package much more falsifiable.

## 7) Questions the operator must answer

1. What is the authoritative, mutually exclusive classification rubric for retention, exports, captures, feeds, copies, and cancellations?
2. Who appoints, audits, and may remove an orphan custodian—and what independent approval is required before that custodian retires a resource?
3. Is Phase 0.5 allowed to instrument customer workspaces or contact real people before Phase-1 privacy/outreach controls are ratified? If yes, who signs that exception?
4. What exact signing root, approver quorum, emergency revocation process, and compromise recovery model governs models, prompts, policies, evaluators, and playbooks?
5. What fields comprise the immutable buyer manifest, and which authoritative system verifies price, billing scope, signer authority, and one-time execution?
6. Who independently certifies a cost-brake class as safe, and what telemetry source is independent enough to trigger it?
7. Which audiences may receive a widened case/resource disclosure, and how are sensitive/regulated workloads excluded?
8. What measurable evidence would justify claiming that enrolled L3/L4 autonomy—not only L2 Assist—is usable, trusted, and economically scalable?

## 8) External-fact note

No external facts were independently relied on for this report. All findings are internal consistency, disposition, and v1→v2 comparison findings based on the reviewed package and its Git revisions; package citations were not independently revalidated against external sources.

---

## Orchestrator spot-check of the reviewer's specific quotes (2026-10-30)

Reviewer A relied on no external facts, so the check is whether each *quoted passage and line reference* is true of tag `ideation-v2`. Line numbers are those of the v2 files.

| Item | Result |
|---|---|
| R2-A-01 — `DATA-19` "Ingestion capture copies nobody reads … Remove \| R1 \| L3" and `DATA-28` "Change feed or inventory … Disable \| R1 \| L3" | **Verified** (`docs/ideation/02-opportunity-catalog.md` lines 259 and 268). `TELE-30` (export removal, `R1 \| L3`, line 231) is the same family and was also reclassified. |
| R2-A-02 — `IDLE-29` "Cancel plans; close subscription \| R2 \| L3" | **Verified** (catalog line 89). The reviewer is right that it contradicts invariant 16 (cancellations never L3–L5). |
| R2-A-03 — Phase 0.5 "no writes" yet "enable query audit (LAQueryLogs) … now", plus a ~10-card Wizard-of-Oz test before the Phase-1 outreach-ethics subset | **Verified** (`docs/plan/00-follow-up-plan.md` lines 13, 40, 46, 51); `03-deep-dives` §1.5 does call "start watching" an R1 action. |
| R2-A-04 — "shortening retention" appears in both R3 and R3-Data | **Verified** (`06-closed-loop-actions-and-autonomy.md` lines 53–54). Also verified: `03-deep-dives` line 16 "**R3** for dropped data" and line 77 "Retention / archive changes \| R3 if shortened". |
| R2-A-05 — P2S card "informed by me; no objection so far"; execution "approved by the Network Platform owner" | **Verified** (`03-deep-dives` lines 244 and 254); the catalog's gate says "every affected party's explicit consent". |
| R2-A-06 … R2-A-15 | Design critiques (judgement), not checkable facts. The quoted passages were each found in the cited sections. |
| Disposition audit — G-02, G-04 and G-10 "Partly" | **Verified.** G-02: DATA-19/28 contradict R3-Data. G-04: the word "authenticated" appears only in the *candidate* answer to G1-07 (`08` line 49), not in the operative loop rule (`06` §3 item 6) or invariant 15 (`08` line 257), yet the round-1 disposition says "affirmative, authenticated enrolment". G-10: the R3/R3-Data overlap is real. |
| "No confirmed valuable content was silently dropped" | Consistent with the orchestrator's own record (changelog and round-1 disposition). Not re-diffed independently. |
| Reviewer's note that `research/02` is absent from both v1 and v2 | **Correct** — it is now added at v3 (`docs/research/02-third-party-and-oss-landscape.md`). |

**Verdict on the report:** 10 of 10 checkable quotes verified; no inaccurate example found. The report is accepted in full (see the disposition for what we changed and the two qualifications).
