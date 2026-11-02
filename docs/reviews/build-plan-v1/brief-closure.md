# Build plan v1: brief for the closure checkers

The written plan in `docs\build-plan\` (README, 01 to 04) was read cold by five readers ([cold-1](cold-1.md) to [cold-5](cold-5.md)). Their findings were checked against the files and the plan was changed. You check whether the changes closed the findings and whether they broke anything. You do not edit any plan, design or experience file.

## What to do

1. **Verdict per finding.** For every finding of your assigned reports, read the passage it quotes in the **current** files (line numbers in the reports are stale) and give one verdict: `CLOSED` (the passage was fixed, or the plan now answers the concern), `PARTLY`, `OPEN`, or, for a finding in the list "Not adopted" below, `AGREE` or `DISAGREE` with the reason for not adopting it. Cite the current file and line.
2. **New defects.** Read the changed text for what the fixes broke: a passage that contradicts another, a number that no longer adds up (sizes, counts, anchors), a claim about a Microsoft product that Learn does not support, a table row over 800 characters or a paragraph over 1,100, words the repository forbids, and anything that reads as the history of the project (reviews, rounds, "the reader said") instead of the plan. Look hardest at `03-first-checks.md` (rewritten as one section per check), `02-before-you-start.md` (the network row, the region check, the firewalled lake paragraph, the roles and licences rows), `04-cost-effort-and-risks.md` (the cost bullets) and `README.md`.
3. **Verify the Microsoft facts that are new in this round** on Microsoft Learn, and say what you read: the AI Search region footnote for Sweden Central and the other three regions; the hosted-agent region list; the agent subnet that one Foundry account only may use, and the second subnet that a Flex Consumption app needs (a Container Apps environment and a Flex Consumption app cannot share one); the export prerequisites for a firewalled storage account (Owner or a custom role with `Microsoft.Authorization/roleAssignments/write` and `Microsoft.Authorization/permissions/read`, trusted Azure services, the copy scope From any storage account, same tenant only); GitHub rulesets and environments on private repositories; what the passkey page says about embedded WebViews.
4. **Run** `python tools\check-docs.py --strict`. Orphan errors for files in `docs\reviews\` are expected until the review index is updated; report any other error or warning.

## Not adopted (say AGREE or DISAGREE for each)

- cold-5 finding 1, "no container registry": hosted agents deploy from a zip of source code ([Learn](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code)); the container path is for custom runtimes and is not used.
- cold-5 fact checks 3 and 5 (the 48 hours and the 30 minutes to 2 hours "not found"): the first is on the budgets tutorial and the exports tutorial, the second on the Exchange RBAC page; three other readers verified both, and cold-5 read only the first characters of each page.
- cold-5 finding 2: slice 0.1 gets no check of its own; its evidence is a pull request blocked by a failing check.
- cold-1 finding 2: no start dependency from the cost lake to Atlas v0; Atlas v0 starts from resource counts and adds by spend when the lake lands.
- cold-3 finding 16: the sign-in test C10 stays at the start of phase 2 as an early test; bound approvals stay with proof point P3 in phase 3.
- cold-5 finding 21: the label "Surprise:" in the slice sections stays.
- cold-2 finding 15: design 09 already lists Cost Management Contributor among the export roles.
- cold-2's suggestions to delete the sentence "It is a plan only" and the risk row on scope creep.

## Rules of the repository

[AGENTS.md](../../../AGENTS.md) holds them. The ones that matter here: plain words for a stranger; no euro figure in the plan; no "walking skeleton", "pre-registered" or "pre-registration"; none of the vocabulary the project dropped (lab, exam, Terrarium, wind tunnel, time machine, learner); no review history in the plan; nothing the plan claims about a Microsoft product without a source.

## Output

One file, in this format, and nothing else written:

- `# Build plan v1 closure check N`, a table `| ID | Verdict | Current file:line | Closure |` with one row per finding of your reports, a list `## New defects` (severity, file:line, the quoted text, why it is wrong, the fix), `## Verification` (each Microsoft statement, the URL you read and what it said) and a last line `Release: YES` or `Release: NO`.

## Assignments

| Checker | Reports | Write to |
|---|---|---|
| 1 | cold-1 (6 findings), cold-3 (23), cold-4 (18) | `docs\reviews\build-plan-v1\closure-1.md` |
| 2 | cold-2 (15), cold-5 (22); and the new-defect read of README, 01, 02 and 04 | `docs\reviews\build-plan-v1\closure-2.md` |
