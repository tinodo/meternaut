# Build plan v1, closure round: disposition

Two closure checkers on other model families verified every finding of the five cold readers against the fixed plan ([brief-closure.md](brief-closure.md)): checker 1 on readers 1, 3 and 4 (gpt-6.1-sol, [closure-1](closure-1.md)) and checker 2 on readers 2 and 5 and on the new text (claude-sonnet-5.5, [closure-2](closure-2.md)). Checker 1 found 30 findings closed, 14 closed in part, 1 open, 2 rejections right and 3 new defects (1 Blocker, 2 Majors). Checker 2 found 28 closed, 5 closed in part, 8 rejections right and 6 new defects (all Minor). Both said "Release: NO". Each item was checked against the files, and each Microsoft claim was read again on Learn on 2026-11-02, before anything changed. The record of the cold readers is [disposition-cold-readers.md](disposition-cold-readers.md).

## New defects

| Defect | Verdict | What was done |
|---|---|---|
| C4 step (c) treated Graph's `202` for a direct send as proof that the recipient protection had failed (checker 1, Blocker) | Accepted. Graph answers `202` at step 1 and applies a tenant's mail-flow rules at step 5, so a protected system would fail C4 every time ([Learn](https://learn.microsoft.com/graph/outlook-things-to-know-about-send-mail)) | The pass is a rejection by Exchange's rule (a non-delivery report or the administrator's message trace) and nothing in the team-owned mailbox within a window written beforehand; the `202` proves nothing |
| The licence row accepted GitHub Team, which has no required reviewer on an environment in a private repository (checker 1) | Accepted ([GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#required-reviewers)) | The row asks for GitHub Enterprise Cloud for a private repository; design 09 §3 says the same |
| A firewalled export works only within one tenant (checker 1) | Accepted | One clause in the paragraph on the firewalled lake: the estate must be in the solution's tenant |
| The months of the longest chain ignored four days in five (checker 2) | Accepted | 12 to 17 months in 01 and 04 |
| The kill switch page was placed in phase 2 (checker 2) | Accepted | Phase 3, as the roadmap lists it |
| The Deployment Stack exception contradicted the delivery rules, and "during creation only" was too narrow (checker 2) | Accepted | "During creation or a later change"; the creator's role is a time-boxed elevation; the exception is a reviewed change to the stack's exclusions in `infra/`, released like any other and removed afterwards |
| The cost figures are Sweden Central prices (checker 2) | Accepted | One sentence in 04: in another region, fetch the price snapshot again before 1a.1 compares the fixed lines |
| The network request left out the peering with the hub (checker 2) | Accepted | Added to the network row |
| The mail risk row left out that hand delivery keeps 0.5 and 1a.7 open (checker 2) | Accepted | Added |

## Closed only in part, or open

| Item | Verdict | What was done |
|---|---|---|
| The slice-done wording in the README and the slice diagram still said "its check passes" (R1#1, R4#4) | Accepted | "Its stage of each check passes" in principle 7 and in the diagram |
| Cost Details: history and refresh were one rule (R1#5) | Accepted | Thirteen monthly calls seed the history; the open month is refreshed at most daily, respecting `Retry-After` |
| The call that crosses a token limit may succeed (R3#5, open) | Accepted ([Learn](https://learn.microsoft.com/azure/api-management/llm-token-limit-policy)) | C1 asks for 429 once the minute's limit is exceeded and allows the crossing call |
| A Scheduler could be chosen with no cost line (R3#6) | Accepted | A line for the chosen backend is added to the cost model before 0.4 is accepted |
| C5 needed an independent classification to match (R3#10) | Accepted in part | At least one scope's classification by a billing-role holder must match the probe's. The portal blades are still not named |
| Roles deploy before 1a.6b (R3#17, R4#1) | Accepted | The Safety gate applies when the first role reaches production (1a.3); Restraint and Honesty when Cases first recommend (1a.6b); C11 is in the check columns of 1a.3, 1a.6b and 1a.7 |
| C12 had no bound for the call in flight, no pass for a suspended contract and a synthetic trip (R3#18, R4#14) | Accepted | The trip reads hub-priced usage over a cap set low for the drill; the call in flight ends within a bound (starting value: 15 minutes); a suspended contract stops only its agent |
| C13 did not fix the cost, currency or unassigned lines (R3#19) | Accepted | Actual cost, billing currency, unassigned lines included |
| C4 comprehension could pass with no question (R3#22) | Accepted | The questions that apply to a digest: the saving range and its basis, and what it asks and why; at least one applies |
| The two reconciliations had no fixed basis (R4#7) | Accepted | Scope, month, currency and cost type are written down beforehand |
| 02 listed Usage Details before the PAYG export (R4#9) | Accepted | The export of another dataset comes first |
| No template for the phase 1a letter (R4#11) | Accepted | 1a.7 names the five sections of the Monday letter that it keeps and the three that wait for phase 3 |
| Atlas, Detectors, `judge`, mapped columns and "the lake" were undefined in 02 (R2#12, R5#5) | Accepted | One clause each, where first used |
| "Zero writes to Azure" contradicted the principle (R5#9) | Accepted | "Zero writes to the estate" in the README, 01 and the roadmap; the principle reads "No system writes to the estate until phase 3" |
| "The runner" named the deployment runner and the action runner (R5#19) | Accepted | "Deployment runner" in 01, 02 and 04 |
| The findings number is a range, not one number (R5#17) | Not adopted | The FinOps lead chooses one number in the range before 1a.6a; a default of the plan's own would guess at someone else's estate |

## Other changes in this round

- **The later checks moved.** The section "Checks for later phases" in 03 is a pointer; each later phase lists its checks in "What comes after phase 1a" in 01, so a reader meets them once.
- **The cost-data list in 01 is short.** The table in 02 is the one place that orders the paths and holds their links.
- **The folder limit is 13,100 words.** Every passage added in this round answers a finding.

## Final check

One more checker (grok-4.7, [final-1](final-1.md)) read the items that the closure round left open or found: 24 of 25 closed, one closed in part and one new Minor defect, and "Release: YES". The part left was that the replay of the price simulator against the lake did not name its basis; the replay now names the same scope, month, currency and cost type, and the simulator's release has a stage of check C11. The new defect was that "Cost on every release" did not fit the slices that carry C11; each later release now repeats the gates that already apply.
