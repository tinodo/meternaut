# Build plan v2, round 1: disposition

Two reviewers on different model families read the changed plan against the brief in [brief.md](brief.md): A on design validity (gpt-6.1-sol, [raw-a-design.md](raw-a-design.md)) and B on consistency and arithmetic (grok-4.7, [raw-b-consistency.md](raw-b-consistency.md)). A gave 9 findings (7 Major, 2 Minor); B gave 15 (1 Blocker, 12 Major, 2 Minor). This record says what was done with each.

Both reviewers recomputed the sizes, the three chains and the months from the dependency table and found the arithmetic right (phase 0 22 to 30, phase 1a 38 to 52, total 60 to 82, 62 to 85 with the hub accelerator); what they questioned was what the milestone chain means, not the sums. Both ran the strict validator on the working tree and found the same four size errors. Both found the four adjustments in the plan: week-0 feasibility, the early learning demonstration, the measurable finding record and the provisional schedule.

## Reviewer A, findings

| # | Finding (severity) | Verdict | What was done (where) |
|---|---|---|---|
| A1 | C14 chooses its mechanism after seeing results; no limit on screening (Major) | Accepted in part | One mechanism and a reserve are written down before any run, so nothing is screened against the result. A strong frozen result is recorded as "no headroom", not as proof that the claim teaches nothing, and a second one goes to the learning review (C14). A separate screening step was not adopted: the single mechanism fixed beforehand already closes the risk, and a screening stage would grow a check meant to stay small |
| A2 | C14's rule is not reproducible across three runs; a zero-tolerance control (Major) | Accepted | Frozen and control are each judged by the median of their runs against one bar; updated needs five found and four priced in two of three runs; the control matches the claim in length and is chosen after the claim is accepted; every arm has the same model alias, prompts and settings, and the key is in no prompt; every answer is kept and the report says this is a small exploratory comparison, not a statistical claim (C14, `evaluation/c14/`) |
| A3 | The two passes have no completion states; the dependency table lacks the workload review (Major) | Accepted | A slice starts after the first pass of its predecessors; a stage belongs to the first pass unless its check says otherwise; C6 and the repeat of C5 for each added scope belong to the second pass and are required before the phase exits; the dependency table and diagram carry the three reviews on their edges ([01](../../build-plan/01-the-slices.md), [02](../../build-plan/02-before-you-start.md), [03](../../build-plan/03-first-checks.md)) |
| A4 | The deferrals contradict the profile's verification baseline (Major) | Accepted | The private endpoints are counted by phase: nine in 1a, ten in phase 2, eleven in phase 3, in slice 1a.1, in the architecture's profile section and in the roadmap. The full-profile cost column stays the reference; the cost line of 1a.1 is that column less the two endpoints that wait |
| A5 | C13's second stage silently makes an export mandatory (Major) | Accepted | The system's own identity repeats the read by the route chosen for each scope; an export created by the estate owner is needed only where an export is the route (C13) |
| A6 | The stage spending caps have no stopping test (Major) | Accepted | The plan says what a stage is charged, how its total is read, what stops work at the cap (the hub contract is suspended; until the kill switch exists, a harness stops itself at its call limit and cap) and what happens to its resources; C14 runs a two-call stop test before its first full run; the full C12 drill stays later ([04](../../build-plan/04-cost-effort-and-risks.md#the-three-reviews)) |
| A7 | The plan fails its enforced size limits (Major) | Accepted in part | The README is back at its cap and the documents were cut again. The cap of a document and of the folder were raised, with the reason in the changelog (AGENTS.md rule 14 carries the new numbers), because the four adjustments added two slices, a check, three reviews and the finding record. The rule stays; the new numbers are the starting values of this plan |
| A8 | The README still says fifteen slices and thirteen checks (Minor) | Accepted | It says seventeen and fourteen |
| A9 | The review brief is unreachable (Minor) | Accepted | It is indexed in the [review index](../README.md) |

## Reviewer B, findings

| # | Finding (severity) | Verdict | What was done (where) |
|---|---|---|---|
| B1 | A slice is done only when all its stages pass, so the first pass cannot start (Blocker) | Accepted | The pass model of A3: a later slice starts after the first pass of its predecessor, and a second-pass stage is no part of being done for the first pass (01, 02, 03) |
| B2 | 37 to 51 is not the chain to the milestone (Major) | Accepted in part | The figure is labelled "at most": it uses whole-slice sizes, which include the widening after the milestone, so it is a ceiling. Splitting each size in two was not adopted: the sizes are scenario parameters, and completed slices will give the real split (04) |
| B3 | The milestone widens the estate and then runs C6, which must run before it (Major) | Accepted | One order: the second pass runs C6 on synthetic volumes, then widens the estate, then adds 1a.7 and 1a.8 (01, 03) |
| B4 | The workload review is missing from the 1a.7 row of the dependency table and the diagram (Major) | Accepted | The three reviews are edge labels in the table and the diagram (01) |
| B5 | C5 is not repeated for the scopes the second pass adds, so P4 is not proven (Major) | Accepted | C5 repeats for every added scope, and P4 is not called passed until that stage has passed (01, 03) |
| B6 | Nine endpoints against the design's count of eleven; "matches" and "slightly under" cannot both hold (Major) | Accepted | As A4: the pre-release count is nine in 1a, and 1a.1 records a cost line for what is deployed |
| B7 | The finding record ignores effort, is set by the person it measures and can read as a realised saving (Major) | Accepted | A finding counts only if it is distinct, credibly priced, adds discovery or follow-through, and a second reader agrees that the opportunity justifies the effort; the four fields are stored as a confirmation, never as an outcome; the roadmap row carries the same count ([02](../../build-plan/02-before-you-start.md#what-is-recorded-for-each-finding), [roadmap](../../design/13-roadmap.md)) |
| B8 | The root README counts are stale (Major) | Accepted | As A8 |
| B9 | The roadmap's phase 0 exit leaves out slices 0.0 and 0.7 and the two reviews (Major) | Accepted | The phase 0 row names them (roadmap) |
| B10 | The plan's own size rule fails (Major) | Accepted in part | As A7: cut, then raised with a reason, which the reviewer allowed |
| B11 | C14: the claim's reviewers see the cases; "finds" is undefined; the mechanism can be swapped without limit; control is held to a one-case gap (Major) | Accepted | "Found" and "priced" are defined; the cases and key come from someone other than the claim's reviewer, or are committed before the claim is proposed; code checks that the claim copies nothing from a case; one mechanism and a reserve are fixed beforehand; control faces the same bar as frozen (C14) |
| B12 | The learning review asks a wider question than the stand-in tests (Major) | Accepted | The review question is narrowed, and a pass says nothing about retrieval from the Atlas or the Case path (04, C14) |
| B13 | Only three stages have an owner, a cap and a date; the hub deployment has none (Major) | Accepted | Foundations is a fourth stage with its owner, cap and review date, and its review is the phase 0 exit (02 decisions table, 04) |
| B14 | The accelerator totals and chains are missing (Minor) | Accepted | 62 to 85 and the chains with the accelerator are shown beside the default ones (04) |
| B15 | The learning review's "if no" omits stop (Minor) | Accepted | The review's answers are continue, change and repeat, or stop (04) |

## Not adopted

- A separate screening step before C14 (A1): one mechanism fixed beforehand, with a reserve, closes the same risk at a lower cost.
- Two sizes per slice, first pass and widening (B2): the milestone figure is a ceiling until real speeds are known.
- A statistical design for C14 (A2): the check is a small early look, and its report says so.
