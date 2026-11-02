# Brief for the build-plan reviewers (specification round)

You are one of two reviewers on different model families. You have not seen this repository. Read-only: change no file except your own report.

## What this is

The repository `<repo>` holds an idea (`docs\01-north-star.md` and nine more), a technical design (`docs\design\`: fourteen documents and a README; the roadmap is `13-roadmap.md`), and an experience design (`docs\experience\`) for an AI system that finds Azure savings and asks the people who own the resources to decide. Nothing is built.

The next document set is a **build plan** for phase 0 (foundations) and phase 1a (first value on one estate): what is built first, in what order, what is shown at each step, what must be checked before it is relied on, what it costs to run and to build, and what the adopting organisation must provide. It will live in `docs\build-plan\`. It is a plan only: no code, no deployment.

The specification of that plan is `docs\reviews\build-plan-v1\spec.md`. Read it completely, then read what it depends on: `docs\design\13-roadmap.md`, `09-delivery-and-operations.md`, `02-architecture.md`, `10-cost-and-finops.md`, `08-testing-and-evaluation.md`, `14-agreements-and-access.md` and the parts of `03`, `04` and `05` that the slices rely on, and the platform register `docs\experience\13-platform-register.md` and `12-testing-the-experience.md` for the checks that concern people-facing channels. The repository's rules are in `AGENTS.md` (rules 1, 2, 11 and 12 matter most).

## What to do

Challenge the specification the way a senior engineering lead would before committing a team to it. Answer the seven questions at the end of the specification, and in addition:

1. **Order and slicing.** Is each slice thin enough to finish and show? Is a slice missing (for example the report card, the first Study run, a kill-switch drill, the first red-team run, a runbook for on-call), or is one not needed yet? Would a different order reduce risk or time to the first digest?
2. **Dependencies.** Name any slice that cannot start when the specification says it can, and why.
3. **Exit criteria.** Do the slices add up to the exit criteria of phase 0 and phase 1a in the roadmap? What is in the roadmap's exit criteria that no slice delivers?
4. **First checks.** Are the checks passable, measurable and cheap? Is any required check missing (see the design's proof points P1 to P10 and the items that the experience design marks as unverified)? Is any pass condition vague?
5. **Sizes.** Are the person-week ranges plausible as starting estimates for a small team? Say which is most wrong and what a better range is, with your reasoning. The sizes are labelled scenario parameters, not promises.
6. **Prerequisites and decisions.** What would stop a team from starting on a Monday? Is any decision hidden in a table? Is a default missing?
7. **Contradictions** with the design or the experience design: file and line for both sides.
8. **Rules.** Anything in the specification that breaks `AGENTS.md` (personal context, a hedge hardened, review history in the plan, an assumptions list, a linear-pipeline picture, a forbidden word, an invented fact).

Verify every claim about a Microsoft product on Microsoft Learn before you report it (the Learn tools or `web_fetch`). Do not report a style preference.

## Report

Write your report to the file named in your assignment, in plain short sentences, at most 2,000 words:

- Answers to the seven questions of the specification, each in at most 120 words.
- "Findings": at most 15, Blocker or Major only, each as `Severity · where in the specification · what is wrong · the fix`.
- "What I would change first": three items.
- A last line: whether you would commit a team to this plan as it stands.

Use at most 120 tool calls and finish within 40 minutes.
