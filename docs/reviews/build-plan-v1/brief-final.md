# Build plan v1: brief for the final checker

Two closure checkers ([closure-1](closure-1.md), [closure-2](closure-2.md)) checked every finding of the five cold readers against the plan. They found 20 findings closed only in part or open and 9 new defects (1 Blocker, 2 Majors, 6 Minors); all were fixed in the plan, the design or the experience design. You check that the fixes closed them and broke nothing. You edit no plan, design or experience file.

## What to do

1. **Verdict per item.** For each item in the list below, read the **current** passage and give `CLOSED`, `PARTLY` or `OPEN`, with the current file and line and one sentence.
2. **New defects.** Read each passage the fixes touched, and the sentences around it, for what the fixes broke: a contradiction with another passage, a number that no longer adds up, a claim about a Microsoft product that Learn does not support, a table row over 800 characters or a paragraph over 1,100, forbidden words, and history of the project where the plan should state a rule.
3. **Verify on Microsoft Learn** what is new: the Graph send mail process (the `202 Accepted` comes before the transport policies that a mail-flow rule belongs to, and a rejection comes back as a non-delivery report); the GitHub environment rule (required reviewers need Enterprise in a private repository); the Cost Details guidance (thirteen monthly calls for history, at most daily for fresh data, `Retry-After`); the export prerequisites (during creation or modification only; same tenant only).
4. Run `python tools\check-docs.py --strict`; orphan errors for the files of `docs\reviews\build-plan-v1\` are expected until the review index is updated.

## The items

**Closed only in part or open (closure-1):** cold-1.1 (the slice-done wording in the README and the slice diagram), cold-1.5 (Cost Details backfill and refresh), cold-3.5 (the call that crosses a token limit), cold-3.6 (a cost line for the chosen Durable backend), cold-3.10 (C5 needs an independent classification), cold-3.17 and cold-4.1 (gates for the first roles), cold-3.18 and cold-4.14 (C12 bounds), cold-3.19 (C13 basis), cold-3.22 (C4 comprehension for a digest), cold-4.7 (basis of the two reconciliations), cold-4.9 (path order in 02), cold-4.11 (the sections of the phase 1a letter).

**New defects (closure-1):** N1, C4 step (c) treated the 202 as a failure of the recipient protection; N2, the licence row accepted GitHub Team although required reviewers on an environment need Enterprise in a private repository; N3, the firewalled lake needs the same tenant.

**Closed only in part (closure-2):** cold-2.12 and cold-5.5 (terms in 02), cold-5.9 ("zero writes"), cold-5.17 (the findings number stays a range that the FinOps lead narrows to one number; judge whether that is acceptable), cold-5.19 (the word "runner").

**New defects (closure-2):** N1 (months for the longest chain), N2 (the phase of the kill switch page), N3 (the Deployment Stack exception and the roles of the export creator), N4 (prices are for Sweden Central), N5 (hub peering in the network request), N6 (consequence of hand delivery).

## Output

One file, `docs\reviews\build-plan-v1\final-1.md`: `# Build plan v1 final check`, a table `| ID | Verdict | Current file:line | Note |`, `## New defects` (severity, file:line, quote, why, fix), `## Verification` (statement, URL, what it said) and a last line `Release: YES` or `Release: NO`. Release YES means no open Blocker or Major and no item left `OPEN`.
