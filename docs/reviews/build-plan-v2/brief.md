# Build plan v2: the brief for the reviewers

You review a change to a plan. Read only: edit no file in the repository, and touch nothing outside it. Do not use public package registries. A claim about a Microsoft product is checked on Microsoft Learn before you rely on it.

Repository: `<repo>` (the local folder keeps its old name; the product and the GitHub repository are called Meternaut). It is private. The system it describes is a team of AI agents that finds waste in Azure bills, tells the owners, and acts only with a person's OK. The plan under review is `docs\build-plan\` (README and four documents); it covers phase 0 (foundations) and phase 1a (first value on one estate) of `docs\design\13-roadmap.md`. The last released version is the tag `build-plan-v1`; the working tree holds the change. See it with `git --no-pager diff build-plan-v1 -- docs/build-plan` from the repository root.

## What the owner asked for

After reading build-plan-v1 the owner asked for four adjustments, which he called his biggest concerns:

1. **Bring a small learning demonstration forward.** Phase 1a could succeed on seeded knowledge, Detectors and Advisor leads without showing the project's distinguishing capability. Run a small demonstration alongside the early agent work: introduce new evidence, show an improved answer on an unseen case, and reject a similar-looking legitimate configuration. Keep the stronger phase 1b evaluation later. Do not spend months finding out whether the central idea works.
2. **Establish pilot-data feasibility immediately.** The check of the per-resource bill (C13) was required only before slice 1a.2. Bring an initial version into week 0: obtain one closed month through an authorised existing route, reconcile it and establish its price basis; confirm the pilot owner, access, hub, region and quota alongside it.
3. **Make "worth acting on" measurable.** For each confirmed finding record whether it is distinct rather than a duplicate, the credible financial opportunity and the effort to implement, and whether it adds discovery or useful follow-through to existing Azure advice. Keep the rule that a confirmation is not a claim of realised savings. Five to ten findings stays a reasonable starting target.
4. **Treat the schedule as provisional.** Sizes are scenario parameters; completed slices establish the real speed. The first useful demonstration should cover one workload end to end, not wait for broad service coverage, enterprise-volume hardening or unused future components. Preserve the necessary governance; reduce the initial breadth.

He also authorised building the repository foundations, the minimal agent, hub and model path, spend and stop controls, the pilot-data feasibility and the small learning demonstration, each with a named owner, a spending cap and a review date, "to answer the remaining uncertainties, not to mechanically implement every page".

## What the working tree does about it

| Ask | Where | How |
|---|---|---|
| 1 | `01` slice 0.7; `03` check C14; `04` the learning review | A frozen snapshot of a few Atlas claims; one new source; the system proposes a claim with a receipt; code checks the quote; a person accepts; three arms (frozen, control, updated) of three runs on six unseen cases and three decoys; pass numbers are starting values; P6 stays in phase 1b |
| 2 | `01` slice 0.0; `03` check C13 (two stages); `04` the feasibility review | Week-0 slice with no deployment; C13 first stage by hand with read-only roles; price basis recorded; owner, access, hub, region and quota confirmed by name; the review gates slice 0.2 |
| 3 | `02` "What is recorded for each finding"; `01` phase 1a intro; `02` decisions table | Four fields (distinct, opportunity with price basis, effort, adds: discovery, follow-through or nothing new); only findings that are distinct, credible and add something count toward the number |
| 4 | `01` the first-workload milestone; `01` table rows; `04` sizes and the workload review; README | Phase 1a built in two passes: one workload first, then the estate; check C6 (volume) and slices 1a.7 and 1a.8 follow the workload review; `approvals`, `runner`, `bot` and two private endpoints are not deployed until their phase; sizes of existing slices unchanged; two new slices add 4 to 6 person-weeks; a provisional-schedule rule |

Other decisions: the command that records a finding moved from 1a.8 to 1a.6b so that the milestone can record one; C9 and C10 (phase 2 previews) were shortened; a "Sizes and elapsed time" section of `01` was folded into `04`.

## What to attack

1. **Check C14 as an experiment.** Can six cases, three decoys and three runs per arm tell a real gain from noise or leakage? Is the control arm useful? Is "frozen finds at most two of six" a sound precondition? Can the model already know the mechanism, so that frozen does well for the wrong reason? Does the stand-in finder (a model call with claims as context) show the project's idea, or something weaker? Are the numbers sensible? Is anything a reviewer could game left open?
2. **The two-pass structure.** Does it contradict the roadmap's phase 1a exit, the checks (C5, C6, C7, C8, C11), a slice's "done" rule in `02`, or the dependency table and diagram? Is anything the milestone needs missing? Is moving C6 to the second pass compatible with proof point P4 and the exit?
3. **The deferrals.** Is leaving out the `approvals` and `runner` apps and their two private endpoints in phase 1a compatible with `docs\design\02-architecture.md` (the Operate profile and its eleven private endpoints), the cost model and `docs\design\09-delivery-and-operations.md`?
4. **Arithmetic.** Phase 0 is 22 to 30 person-weeks and the first stretch 60 to 82 (62 to 85 with the hub accelerator); the longest chains are 9 to 12 (to the learning review), 37 to 51 (to the first-workload milestone) and 43 to 59 (to the end of 1a); the months use 0.8 of a week per person-week and 4.345 weeks a month. Recompute them from the slice sizes and the dependency table.
5. **Gates and reviews.** Slice 0.2 starts after the feasibility review, 1a.1 after the learning review (through 0.7), 1a.7 after the workload review. Are they stated the same way in `README`, `01`, `02` and `04`? Does the plan say who holds each review and what each can decide?
6. **The finding record.** Is it measurable, can it be gamed, does it keep "a confirmation is never a claim of realised savings", and does it fit the ledger and the roadmap's wording?
7. **Consistency.** Counts (seventeen slices, fourteen checks, nine principles), anchors, cross-references, and places that still carry an old number or statement, inside `docs\build-plan\` and outside it (root `README.md`, `AGENTS.md`, `docs\design\`, `docs\experience\`): "fifteen slices", "thirteen checks", "56 to 76", "eight principles", "in full", "eleven private endpoints".
8. **Plain words.** Jargon a stranger would not know, conversation residue, anything that only makes sense to someone who saw the owner's message, review history, euro figures (the plan never types one), the words lab, exam, Terrarium, wind tunnel, time machine and learner (not allowed anywhere), "walking skeleton" and "pre-registered" (not allowed in the plan), and the two original findings of the project (never used as examples).
9. **Fidelity.** Does each of the four asks land as he meant it? Is a hedge hardened into a constraint? Is anything he asked for missing? Is anything added that he did not ask for and would not want?

## What to return

A report of at most 1,800 words, in this form, and nothing else:

- A table of findings: `#`, severity (Blocker, Major, Minor), file and line, what is wrong, the fix you propose. A Blocker makes a statement false or the plan unusable; a Major misleads or contradicts; a Minor is wording.
- A short list of what you checked and found right (with the file and line), so that the author knows what not to touch.
- For anything about C14, your reasoning for its severity in one sentence.

Do not praise. Do not restate the plan.
