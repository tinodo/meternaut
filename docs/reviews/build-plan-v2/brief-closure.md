# Build plan v2: brief for the closure checker

The changed plan in `docs\build-plan\` (README and 01 to 04) was read by two reviewers ([raw-a-design.md](raw-a-design.md), 9 findings, and [raw-b-consistency.md](raw-b-consistency.md), 15 findings). Their findings were checked against the files and the plan was changed; [disposition.md](disposition.md) says what was done with each. You check whether the changes closed the findings and whether they broke anything. You edit no plan, design, experience or code file, and you write one report file only (see Output).

Repository: `<repo>` (the local folder keeps its old name; the product and the GitHub repository are called Meternaut). It is private. Context and the owner's four adjustments are in [brief.md](brief.md); read it first. The working tree holds the change: `git --no-pager diff build-plan-v1 -- docs/build-plan docs/design` from the repository root, and the new files under `docs\reviews\build-plan-v2\`.

## What to do

1. **Verdict per finding.** For every finding A1 to A9 and B1 to B15, read the passage it quotes in the **current** files (line numbers in the reports are stale) and give one verdict: `CLOSED` (the passage was fixed, or the plan now answers the concern), `PARTLY`, `OPEN`, or, for an item under "Not adopted" below, `AGREE` or `DISAGREE` with your reason. Cite the current file and line. Do not take the disposition's word for it.
2. **New defects.** Read the changed text for what the fixes broke:
   - a passage that contradicts another, in the plan or in the design documents the plan changed (`docs\design\02-architecture.md`, `docs\design\13-roadmap.md`);
   - a number that no longer adds up: seventeen slices, fourteen checks, nine principles, three reviews; the private endpoints by phase (nine, ten, eleven); phase sizes (phase 0 22 to 30, phase 1a 38 to 52, total 60 to 82, 62 to 85 with the hub accelerator); the three chains (9 to 12, at most 37 to 51, 43 to 59); the months for two and for three builders;
   - the pass model: can the first pass of phase 1a start and finish by the rules written (the done rule, which stages belong to which pass, the three reviews and what each waits for), with nothing that needs its own successor?
   - C13 (two stages), C14 (what is written down first; the three arms; found and priced; the pass and the "no headroom" rule) and the stage spending cap (what is charged, what stops work, what happens to the resources): can a person who has read only the plan carry each out and know when it has passed?
   - an anchor or link that does not resolve; a claim about a Microsoft product that Microsoft Learn does not support; euro figures in the plan; words the repository forbids; and anything that reads as the history of the project (reviews, rounds, "the reviewer said") instead of the plan.
   Look hardest at `docs\build-plan\01-the-slices.md` (the milestone paragraph, the dependency table and diagram), `02-before-you-start.md` (decisions row for stages, the finding record, the done rule), `03-first-checks.md` (How a check works, C13, C14) and `04-cost-effort-and-risks.md` (sizes and chains, the three reviews, the stage-stop paragraph).
3. **Verify on Microsoft Learn** every Microsoft statement that is new or changed in this round and say what you read. At least: budgets and cost alerts only alert and do not stop consumption (the budgets tutorial); the Cost Details API and the Usage Details API as per-resource routes, and what role they need; that the Query API gives totals.
4. **Run** `python tools\check-docs.py --strict` and report any error or warning.

## Not adopted (say AGREE or DISAGREE for each)

- A1: no separate screening step before C14; one mechanism and a reserve are fixed beforehand.
- B2: no split of each slice's size into a first-pass size and a widening size; the milestone figure is labelled "at most".
- A2: C14 is a small exploratory comparison and is not given a statistical design.

## Rules of the repository

[AGENTS.md](../../../AGENTS.md) holds them. The ones that matter here: plain words for a stranger; no euro figure in the plan; no "walking skeleton", "pre-registered" or "pre-registration"; none of the vocabulary the project dropped (lab, exam, Terrarium, wind tunnel, time machine, learner); no review history in the plan; nothing the plan claims about a Microsoft product without a source.

## Rules for you

This is a Microsoft-managed device. Use no public package registry (PyPI, npm, NuGet, PowerShell Gallery) and no workaround. Read nothing from any Azure subscription and run no command that changes or reads Azure resources. Start no OBS Studio (if one is ever started it must carry `--portable`), and post, comment or react on nothing on any GitHub repository. Publish nothing and run no release workflow.

## Output

One file, `docs\reviews\build-plan-v2\closure-1.md`, in this format, and nothing else written:

- `# Build plan v2 closure check 1`, a table `| ID | Verdict | Current file:line | Closure |` with one row per finding (A1 to A9, B1 to B15), a list `## New defects` (severity, file:line, the quoted text, why it is wrong, the fix), `## Verification` (each Microsoft statement, the URL you read and what it said) and a last line `Release: YES` or `Release: NO`.
