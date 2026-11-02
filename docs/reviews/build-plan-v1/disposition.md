# Build plan v1, round 1: disposition

Two reviewers on different model families read the specification (`spec.md`) before any plan document was written: A on delivery realism (gemini-4-argon, [raw-a-delivery.md](raw-a-delivery.md)) and B as adversary (gpt-6-sol, [raw-b-adversary.md](raw-b-adversary.md)). Both would **not** commit a team to the plan as specified; A would after three changes, B listed fifteen. This record says what was done with each finding. The revised specification is [spec-v2.md](spec-v2.md); section numbers below are its sections.

Checks the orchestrator made before acting (every external fact was read on Microsoft Learn on 2026-11-02): Exchange RBAC for Applications grants add to organisation-wide Entra grants, so a scoped Exchange role does not limit an app that also holds `Mail.Send` in Entra, and its changes follow a cache of 30 minutes to 2 hours that `Test-ServicePrincipalAuthorization` bypasses ([Learn](https://learn.microsoft.com/exchange/permissions-exo/application-rbac)); a new subscription can need up to 48 hours before Cost Management features work ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets)); the design's FOCUS, Cost Details, Usage Details and Query paths and their limits (design 14 §4); the design's Detector life cycle (design 04 §5), release gates (design 08 §8), failure drills (design 07 §5) and onboarding (design 09 §9). One thing the reviewers read in the specification was the specification's own invention, not the design's: a mail-flow rule that rejects recipients off the allow-list. The design enforces the allow-list in the send step (design 05 §6), so the plan tests that and adds no transport rule.

## Reviewer B, findings

| # | Finding (severity) | Verdict | What was done (where) |
|---|---|---|---|
| B1 | C1 assigned to empty apps; role before suite (Blocker) | Accepted | Slices reordered: 0.2 is infrastructure and the first half of C1; the tool, pins and the first suite come in 0.3; the first hosted agent in 0.4, only after its suite passes; C1 completes in 0.4 (3.2, 3.5) |
| B2 | Capability profile is stored by Estate refresh; explained spend needs the join; a priced draft needs 1a.6 (Blocker) | Accepted | 1a.1 shows raw probe evidence, 1a.3 stores the profile and measures explained spend, 1a.4 shows a retrieval answer, the priced draft is 1a.6b; "starts after" and "passes with" are separated (3.2, 3.3) |
| B3 | FOCUS, Cost Details and Query are not a per-resource path for every agreement (Blocker) | Accepted | A source-by-access mapping, and the rule that a first estate must offer a per-resource bill path to pass the explained-spend exit; list-price-only or aggregate-only is a different, non-passing pilot; new check C13 (3.4, 3.5) |
| B4 | Verified bank rows are not promoted Detectors (Major) | Accepted | Seed Detectors are back-tested and run in shadow; promotion is a person's decision on numbers written beforehand and is outside the exit; first Cases come from the Agenda (Advisor and anomaly leads, the Unexplained Spend list, hunches) (1a.5) |
| B5 | C6 covers one estate; C5 cannot prove an unseen agreement (Major) | Accepted | C6 generates Team and Enterprise volume and covers Detector back-tests; C5 records untested agreement types and levels as unproven, never as passed |
| B6 | Exchange RBAC is unsafe unless the grant is RBAC-only (Blocker) | Accepted | 0.5 and C4: no organisation-wide Entra `Mail.Send` or `Mail.Read`; only the scoped role `Application Mail.Send`; a denied second mailbox tested after propagation and with `Test-ServicePrincipalAuthorization`; `Mail.Read` waits for phase 2 |
| B7 | "Every one holds" does not define delivery; 202 is not delivery (Major) | Accepted | C4 (d) to (f): inspect the received message and headers, prove delivery by receipt, record unknown outcomes and check before any retry, render in classic Outlook and the reader's client. With no mail path in 1a there is no automatic digest: a person delivers it by hand while the path is repaired |
| B8 | First contact needs a page and opt-out; the letter links to sections that do not exist (Major) | Accepted | An explicit pilot introduction agreed with the FinOps lead replaces the owner first-contact flow; the 1a letter leaves out sections that need later phases and has no links to the report card, pages or settings; a short status block replaces the report card; five people read it cold before it goes live (1a.7) |
| B9 | P7 is nearly vacuous without propose tools; the release gate needs sealed baselines (Major) | Accepted in part | C7 now starts from a path matrix (every untrusted source against every sink), seeded attacks, canaries, the wallet test and one person-led session, and repeats in phase 3. The gate conflict is a required, recorded decision (C11), not a silent waiver; the plan recommends a default and names the alternative |
| B10 | P2 and P9 checks too thin (Major) | Accepted | C2 forces failures and compares both backends on measured price and recovery; C3 mutates every pin field and records in-line rejection as tested or open |
| B11 | The exit must be reaching the count, not "or revise the plan"; C8 needs a fixed margin and a join to billed lines (Blocker) | Accepted | The exit is reached only when the number is reached; a smaller number is a new number with its reason; C8 has a starting margin, a closed billing month and an allocation rule written beforehand (3.1, 3.5) |
| B12 | The Pilot column is not an upper bound; omitting two endpoints contradicts the profile (Major) | Accepted | The Operate profile is deployed in full (eleven private endpoints) except the `bot` app; the Pilot column is a reference scenario; 1a.1 re-runs the model for the deployed parts and the estate's volumes; hub and runner are shown separately (3.8) |
| B13 | "Kill switches exist" is not a readiness test (Major) | Accepted | A runbook and a first drill in 0.6 (dev), a second in the pre-release `operate` environment in 1a.1; check C12 |
| B14 | C10 expects approvals in phase 2; "published front door" contradicts private approvals (Major) | Accepted | C10 covers page reachability, sign-in and failure messages only; bound approvals stay with P3; the fallback is a tested private route, and public ingress is a separate decision |
| B15 | "No other role", "licences already owned", missing defaults; no stranger test (Major) | Accepted | The requests table names who can grant each need; no licence is asserted; choices with no safe default are marked required; the stranger test is part of the plan's own release (reviews README) |

## Reviewer A, findings

| # | Finding (severity) | Verdict | What was done (where) |
|---|---|---|---|
| A1 | C1 assigned to a slice with no agent or tool (Blocker) | Accepted | As B1 |
| A2 | Export-creation roles missing (Blocker) | Accepted | The requests table asks for export-creating rights or an export created once by the estate or billing owner; 1a.2 notes the roles and the storage rule (3.4, 3.6) |
| A3 | No clear path to clear a tripped switch; the Monday letter links to nothing that exists (Blocker) | Accepted | The runbook is the way to pull and release in 1a, exercised by two people; the 1a letter has no such links (B8, B13) |
| A4 | 1a.6 too wide and missing a dependency on 1a.3 (Major) | Accepted | Split into 1a.6a (price simulator, Economist, typed records) and 1a.6b (Detective, Skeptic, Case workflow, P7); both depend on 1a.3; sized together at 12 to 18 person-weeks |
| A5 | No pre-release rehearsal, restore test or switch drill (Major) | Accepted | In 1a.1 (design 09 §2, design 07 §5) |
| A6 | Atlas v0 and seed Detectors lack dependencies and bounds (Major) | Accepted | 1a.4 starts after 0.2, 0.3 and 1a.1 and covers the five to ten largest services; 1a.5 starts after 1a.4 and covers ten to fifteen Detectors (starting values) |
| A7 | Pass conditions lack numbers; parts of P1, P4 and the experience layers missing; the PII meter price is UNVERIFIED (Major) | Accepted | Starting values in every pass condition; the sandbox probe and the Policy denial in C1; Cosmos serverless limits and back-test volume in C6; comprehension and cold-read tests in 1a.7; the four prices not in the price API are read from the vendor's pages in 1a.1 |
| A8 | Deploying the hub from scratch is under-sized (Major) | Accepted | Two scenarios for 0.2: 4 to 5 person-weeks with an existing hub, 6 to 8 if the accelerator is deployed; the cost document's own-hub row is pointed at |
| A9 | Cold-start history rules can block 1a.8 (Major) | Accepted | 1a.2 backfills 13 months of cost where the path allows and 93 days of metrics; onboarding thresholds are set in 1a.1 |
| A10 | Slice 0.6 omits its dependency on the Microsoft 365 set-up (Major) | Accepted | The mail path becomes its own slice, 0.5, which starts after 0.1 and runs in parallel with 0.2 to 0.4; 0.6 starts after 0.4 and 0.5 |

Reviewer A's other observations: the card lint in 0.1 is **not** premature (the templates and the lint already exist in the repository, so CI runs them from the first slice); the GitHub App for Atlas proposals is needed from phase 1b, and the requests table now lists it for that phase; the second model family for the `judge` alias is now a pre-flight check in 0.2 (design 03 §5 says what is lost where none is deployable); the week-0 readiness idea became access checks that the pre-flight job gains one at a time, run by hand in week 0 (3.6).

## What the reviewers asked that was not adopted

- A first Study smoke test and a full report card in 1a (B): both belong to phase 1b in the roadmap; a short status block in the letter covers the pilot's need.
- A separate "published front door" fallback (spec): removed, see B14.

## Sizes

Phase 0 moved from 16 to 21 to **18 to 24** person-weeks, phase 1a from 27 to 37 to **38 to 52**, the whole first stretch from 43 to 58 to **56 to 76**: roughly eight to eleven months for two builders and five to eight for three, before the organisation's approvals and before a billing month closes. They remain scenario parameters, re-estimated at the end of 0.4 and after the first real Case in 1a.6b.
