# Build plan v2, closure: disposition

A closure checker on a third model family (claude-sonnet-5.5) read every finding of round 1 against the fixed plan, not against [disposition.md](disposition.md), and read the changed text for what the fixes broke ([closure-1.md](closure-1.md)). Of the 24 findings, 18 were closed, 4 were closed in part (A7, B7, B10, B13), none was open, and the checker agreed with the three parts that were not adopted. It found 11 new defects, all Minor, and its verdict was Release: NO until the changelog gave the reason for the new size caps, the stages were tied to slices and the second reader's duties were complete. It read every Microsoft statement that is new or changed on Microsoft Learn and found none contradicted; two were supported only with caveats that the plan left out (the lag and coverage of tags in cost data, and when a month is closed). This record says what was done with each.

## Findings closed in part

| # | Finding | Verdict | What was done (where) |
|---|---|---|---|
| A7, B10 | The size caps were raised, but the reason was not in the changelog | Accepted | The changelog entry of this edition gives the reason. The first disposition said that AGENTS.md carries it as well; AGENTS.md carries the new numbers and the rule that a reason belongs in the changelog |
| B7 | The second reader agreed to the facts and the effort but not to "distinct" and "adds", the fields that the count turns on, and might be a builder; "the next step" made every Case count as follow-through | Accepted | The second reader, who did not build the system, agrees that the facts are right, that the finding is distinct, that it adds discovery or follow-through and that the opportunity justifies the effort; follow-through means adding the owner, a price on a named basis or the evidence that applies here ([02](../../build-plan/02-before-you-start.md#what-is-recorded-for-each-finding)) |
| B13 | The plan never said which slices a stage covers, and the review of foundations had no holder, evidence or answers | Accepted | [04](../../build-plan/04-cost-effort-and-risks.md#the-three-reviews) lists the four funded stages with their slices, and says that foundations is reviewed at the phase 0 exit, against the roadmap's exit tests, by the same people with the same answers |

## New defects

| # | Finding (severity) | Verdict | What was done (where) |
|---|---|---|---|
| N1 | The closure report was not linked from the index (Minor) | Accepted | It is, with this record |
| N2 | A sentence about the Autonomy level gate appeared twice in a row; "The two new slices add to the roadmap's phase 0" reads as history (Minor) | Accepted | One copy deleted; the second sentence deleted, because the roadmap row now lists both slices |
| N3 | "Gates" in the dependency of 1a.7 is ambiguous (Minor) | Accepted | "Release gates", and the workload review is its own item (01) |
| N4 | "Early in phase 1a" and "the milestone comes earlier" state a hope as a fact (Minor) | Accepted | "Before phase 1a widens"; the sentence is deleted (plan README) |
| N5 | A stage's cost is read by tag, which can miss resource types and arrives late, and the text did not say who suspends the contract (Minor) | Accepted | A tag reaches cost data only for types that carry it and only after a refresh, so resources are tagged when created; cost data is 8 to 72 hours late, so the cap is set below what the organisation can afford to lose; the stage's owner suspends the contract (04). Verified on Learn (understand-cost-mgt-data) |
| N6 | "Stage" means a part of a check in one place and a funded stretch of work in another (Minor) | Accepted | The second sense is "funded stage" in 02, 03 and 04, and 04 defines it |
| N7 | In C14, "the limit" is undefined, "a reserve" reads as money and its set is not required, and a decoy flagged by a baseline arm fails the check although decoys test the updated arm (Minor) | Accepted | The harness stops at its call limit; a reserve mechanism gets its own source, cases, decoys and key before its own run; decoys are counted for the updated arm, and flags in the other arms are reported, not counted (03, `evaluation/c14`) |
| N8 | C13 does not say when a month is closed, what "the same month" means, which API fits which agreement, or what an unassigned line is (Minor) | Accepted | [02](../../build-plan/02-before-you-start.md#choosing-the-first-estate) defines a closed month (from the sixth day after it ends, Learn) and says to read both totals for the same dates or, where the Cost Details API accepts one, the same billing period or invoice; C13 points to the path that fits the agreement and says "lines with no resource"; the probe refuses a month before its sixth day |
| N9 | The second stage of C13 is both a condition for starting 1a.2 and a check of 1a.2, and one sentence is true of the first stage only (Minor) | Accepted | It is a condition: 1a.2 starts after it, and it is no longer in that slice's checks (01); the sentence about the export is deleted, because C13 already says which path each stage uses |
| N10 | In week 0 no identity of the system exists, so who holds the read roles is unasked (Minor) | Accepted | The read-roles row asks for a named person in week 0 and the system's identities by 1a.1 (02), and slice 0.0 says so (01); the week-0 check of prerequisites is no longer tied to slice 0.0 |
| N11 | "Nothing is built" no longer holds (Minor) | Accepted | The plan README says it builds and deploys nothing itself; the design README says nothing is deployed |

The size caps held: the folder was cut to fit its limit again after these additions, so no cap moved in this round.
