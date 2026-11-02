# Brief for the design-v5 reviewers

You are one of two reviewers on different model families. You have not seen this repository. Read-only: change no file except your own report.

## What this is

The repository `<repo>` holds an idea (`docs\01-north-star.md` and nine more), a technical design (`docs\design\`, fourteen documents and a README) and an experience design (`docs\experience\`, fifteen documents, seventeen Adaptive Card templates and a README) for an AI system that finds Azure savings and asks the people who own the resources to decide. Nothing is built.

The experience design needed the system to do 29 things the technical design did not say. They are listed, each with its reason and the design section where it belongs, in `docs\experience\15-asks-of-the-technical-design.md`. Writers have now written those things into the technical design (files `03`, `05`, `06`, `07`, `08`, `09`, `10`, `11`, `12`, `13` and `14` in `docs\design\`; `git diff --stat` and `git diff` show exactly what changed since the last release). The shared wording the writers used is in `docs\reviews\design-v5\writer-sheet.md` (section "Settled wording", S1 to S27; the section "Tasks per file" says who wrote what; the last section lists what was decided after the writers finished, among it S21, how approver readiness is shown): read it first.

Your job is to find what is wrong with the result before it is released as `design-v5`. Your assignment names the parts of the work below that are yours; do the others only where you trip over them.

## What to do

1. **Landing check.** For each of the 29 rows of the asks document, find where the technical design now says it. Give: the row's bold name, the file and section (with a line number), a verdict (LANDED, PARTLY, MISSING or CONTRADICTED) and, if not LANDED, what is missing or wrong. A row is LANDED only if a builder who reads the design alone would build what the row asks.
2. **Contradictions inside the technical design.** The same fact stated two ways, a number that disagrees, a name used two ways, a statement that the new text makes false. Look especially at: the approval record, the plan code, the one-tap cap and the alarm; rollback; the three pauses and the kill switch levels; the Atlas pull-request path (`pr-draft`, rulesets, secrets, repository); the channels (Teams, e-mail, the pages) in `02`, `05`, `06` and `09`; the external e-mail rules in `05` and `14`; the roadmap's mapping of the asks to phases against the sections they live in; the decisions register against the sections; the README glossary against how terms are used.
3. **Contradictions between the technical design and the experience design.** Spot-check at least fifteen specific claims (numbers such as five one-tap approvals a day, day 7 and day 14, push budgets, the 24-hour undo window; names such as Approval service, Runner, R1 to R3; what each page and card does). Cite both places.
4. **Security.** For each new rule (the rollback grant, the cap and the alarm, the page of every request `/ok/<requestId>`, the send step and the delivery contract, fork-based Atlas proposals, the kill switch page, the preferences store, first contact, the AI marks, approver readiness), say whether it creates a new attack path, weakens an existing control, or leaves a gap the text does not admit. Give severity and a fix.
5. **Cost and scale to zero.** Every new component or store should state its idle cost and which line of the cost model carries it. Check `docs\design\10-cost-and-finops.md` for the new paragraph and that nothing outside the generated block types a new euro figure. Run `python tools\cost-model.py --check docs\design\10-cost-and-finops.md`.
6. **The rules of the repository** (`AGENTS.md`, rules 11 (a) to (k), 12 and 13 (b)): review history or conversation residue in a design document, personal context, a hedge hardened into a constraint, undefined jargon or a new term, a sentence a stranger cannot understand, a broken link or anchor. Run `python tools\check-docs.py --strict` (orphan errors for `docs\reviews\design-v5\` and `docs\reviews\build-plan-v1\` are expected until the review record is linked) and `python tools\cardlint.py`.
7. **Facts that changed.** `git diff docs\design\14-agreements-and-access.md` shows facts about agreements, roles and purchases that the writer corrected (who may see or buy what under Enterprise Agreement, Microsoft Customer Agreement, a partner and pay-as-you-go; what a spending-commitment shortfall does; what Cost Management leaves out). Check each changed statement against Microsoft Learn and say which, if any, is wrong or stale. Do the same for any other changed statement about a Microsoft product that you can find in `git diff` (the Logs Ingestion API, Teams limits, GitHub App permissions, Entra authentication contexts, the Graph registration report and its permission).

Verify every claim about a Microsoft product on Microsoft Learn before you report it (the Learn tools or `web_fetch`). Do not report a style preference. Report only what a careful stranger, or an attacker, would trip over.

## Report

Write your report to the file named in your assignment, in plain short sentences, at most 2,400 words:

- A table of the 29 rows: row | file § (line) | verdict | what is wrong.
- "Findings": at most 15, Blocker or Major only, each as `Severity · file:line · "quoted text" · what is wrong · the fix`. Put security findings first.
- A last line: counts, and whether you would release.

Use at most 150 tool calls and finish within 45 minutes.
