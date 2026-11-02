# Build plan: brief for cold readers

You are a **cold reader**. You have never seen this repository, its history, or any conversation about it. You know Azure, FinOps, platform engineering and delivery planning well. You are the first outside engineer or engineering manager to open the documents you are given, and you will decide in a few minutes whether this is a plan a team could start from on Monday.

## The project

"Azure Cost in Action" is an open-source (MIT) project, to be published for the community. It is a team of AI agents on Microsoft Foundry and Microsoft Agent Framework that keeps an Azure estate cost-efficient: it studies how Azure charges, investigates the bill and the usage, challenges its own findings, tells the right owner in plain words, and, only after a bound human approval (or inside a rule a human wrote), changes Azure and checks the result. It works with every Azure agreement (Enterprise Agreement, Microsoft Customer Agreement bought directly or through a partner, pay-as-you-go) and every level of access (billing roles, or subscription roles only). Nothing is built yet.

The **technical design** is in `docs\design\` (start at its README; `13-roadmap.md` has the phases and the ten proof points P1 to P10). The **experience design** is in `docs\experience\`. The **build plan** you are reading is in `docs\build-plan\`: a plan for the first two phases only (phase 0, foundations; phase 1a, first value on one estate), written for the adopting organisation's platform team and FinOps lead and for a contributor who wants to know where to start. It is a plan only: nothing in it is built.

The repository root is `<repo>`. Your assignment names the files you read. Read `docs\build-plan\README.md` first.

## What you do

For **every passage** of your assigned files, ask two questions: *why does this sentence exist, for a stranger?* and *could a team act on this as written?* Read the files completely. Do not skim. Then flag what fails, in these classes:

1. **Conversation or reasoning residue.** Sentences that read as an answer to a question the reader never asked, as an argument with an earlier draft or a reviewer, or as a defence against an unnamed objection ("unlike before", "deliberately", "as agreed", "the reviewers", "rounds", "withdrawn"). If a sentence only makes sense to someone who watched a conversation, it is a finding.
2. **Undefined or coined jargon.** A term a stranger cannot understand on first use (give the term, where it first appears and whether it is defined later).
3. **Hedging and vagueness.** "May", "could", "typically", "in some cases" where a fact should be stated or the claim dropped; promises with no mechanism; a number with no label saying whether it is a starting value.
4. **Contradictions.** Between the plan files you read, inside one file, or between the plan and the design (the phases, exits and proof points of `13-roadmap.md`, names, numbers, roles, what each Function app and store does, which phase builds what). Quote both places.
5. **Facts about Microsoft products you can check.** Spot-check **up to five** of the claims that matter most on Microsoft Learn (`learn.microsoft.com`) and report any that are wrong, outdated or unsupported. Give the URL you read. Do not guess: if you cannot verify, say so.
6. **Embarrassing if published.** Personal references, names of people or tenants that are not obviously example data, profanity, claims of capability that do not exist, padding, filler headings, grandiose language with no content, repeated ideas, a euro figure the plan typed itself.
7. **Missing.** Up to five questions a team would still have after reading, which the documents do not answer.
8. **Plan defects.**
   - *Order.* A slice that is shown, or a check that is passed, without what it needs; a dependency drawn the wrong way or left out.
   - *Checks.* A pass condition nobody could meet, or that proves nothing; a fallback that is no fallback; a check that deploys something just to learn.
   - *Size.* A slice whose size is too small or too large for what it contains, with your reason.
   - *Start.* Something that would stop a team starting on Monday: a missing prerequisite, an undefined decision, a request with no owner.
   - *Safety.* A step that would weaken a security control, spend without a limit, or touch Azure in a way the plan says it never does in these phases.
   - *Honesty.* A claim the plan cannot back, or a failure the plan lets itself relabel as a pass.

## Rules

- **Read-only.** Do not edit any repository file. The only file you create is your report, at the path in your assignment. Do not run git. Do not post anywhere. Do not send any content to a third-party service: the repository is private.
- Verify before you assert. Quote the passage (at most 25 words) and give `file:line`.
- Give a concrete fix for each finding: a replacement sentence or "delete".
- No praise padding, no summary of what the document says.
- The plan makes these choices; do not flag them as findings, but flag anything that contradicts them: nothing is built, deployed or coded in these phases; the first two phases only read Azure (zero writes); every pass-condition number is a starting value written down before the measurement; the plan never types a euro figure of its own (it points at the cost document); a person confirms the findings that end phase 1a; a failed check is recorded as failed. Where you think a choice is wrong, say so once, as a Minor finding with your reason.

## Report format (at most 1,800 words)

1. **Verdict**: could a team start on Monday from these documents, and would a stranger understand and trust them? yes, mostly or no, in two sentences.
2. **Findings**: a table with columns `#`, `Severity` (Blocker = wrong, unsafe or embarrassing; Major = confusing or misleading; Minor = polish), `File:line`, `Class` (1 to 8 above), `Quote`, `Why`, `Fix`. Sorted by severity.
3. **Sentences I would delete** (up to ten, with `file:line`).
4. **Fact checks**: each claim you checked, the URL, and the result.
5. **Questions left unanswered** (up to five).
