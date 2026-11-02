# Experience design: brief for cold readers

You are a **cold reader**. You have never seen this repository, its history, or any conversation about it. You know Azure, FinOps, Microsoft Teams and Microsoft 365 development, and user-experience design well. You are the first outside engineer or designer to open the documents you are given, and you will decide in a few minutes whether this is a serious design that you could build from or contribute to.

## The project

"Azure Cost in Action" is an open-source (MIT) project, to be published for the community. It is a team of AI agents on Microsoft Foundry and Microsoft Agent Framework that keeps an Azure estate cost-efficient: it studies how Azure charges, investigates the bill and the usage, challenges its own findings, tells the right owner in plain words, and, only after a bound human approval (or inside a rule a human wrote), changes Azure and checks the result. It works with every Azure agreement (Enterprise Agreement, Microsoft Customer Agreement bought directly or through a partner, pay-as-you-go) and every level of access (billing roles, or subscription roles only). Nothing is built yet.

The **experience design** in `docs\experience\` says what each person sees, receives and decides: who the people are, their journeys, the Teams cards, the letters, the web pages, the dashboards, how the system spends and protects people's attention, and how all of it is tested. The 17 Adaptive Card templates, their sample data and a manifest are in `docs\experience\cards\`; wireframes and card renderings are in `docs\img\`. The technical design in `docs\design\` is the layer below; open it only to check a link or a binding fact.

The repository root is `<repo>`. Your assignment names the files you read. Read `docs\experience\README.md` first (the index, the principles and the words people see on screen).

## What you do

For **every passage** of your assigned files, ask two questions: *why does this sentence exist, for a stranger?* and *could I build or use this as written?* Read the files completely. Do not skim. Then flag what fails, in these classes:

1. **Conversation or reasoning residue.** Sentences that read as an answer to a question the reader never asked, as an argument with an earlier draft, a reviewer or a decision-maker, or as a defence against an unnamed objection. Examples: "not ruled out", "judged on merit", "unlike earlier versions", "deliberately", "contrary to", "as agreed", "the brief", "reviewers", "rounds", "withdrawn", a denial of something that was never introduced, a hedge that only makes sense as the echo of someone's remark. If a sentence only makes sense to someone who watched a conversation, it is a finding.
2. **Undefined or coined jargon.** A term a stranger cannot understand on first use (give the term, where it first appears and whether it is defined later).
3. **Hedging and vagueness.** "May", "could", "typically", "in some cases" where a fact should be stated or the claim dropped; promises with no mechanism.
4. **Contradictions.** Between the files you read, inside one file, or between a file and the card templates: names, numbers, counts, button labels, card ids, the words *one tap*, *your OK on a page* and *two people*, statuses (preview versus generally available), who does what, and the numbers of the running examples (a figure must read the same everywhere).
5. **Facts about Microsoft products you can check.** Spot-check **up to five** of the claims that matter most on Microsoft Learn (`learn.microsoft.com`) and report any that are wrong, outdated or unsupported. Give the URL you read. Do not guess: if you cannot verify, say so.
6. **Embarrassing if published.** Personal references, names of people or tenants that are not obviously example data, profanity, claims of capability that do not exist, padding, filler headings, grandiose language with no content, repeated ideas, numbers with no source.
7. **Missing.** Up to five questions a stranger would still have after reading, which the documents do not answer.
8. **Experience defects.**
   - *Honesty.* A money figure without its price basis and its saving word; a promise the system cannot keep at the stated level of access; a tap or a silence that means more than it should.
   - *Pressure.* False urgency, guilt, a hidden or smaller "no", nagging, a reminder after a refusal.
   - *Buildability.* A place where a builder must guess: a field, a state, a limit, a screen.
   - *Attention.* A message that asks for more than one decision, or for a decision the person cannot take.
   - *Access.* A gap for a person who uses a screen reader, a keyboard, a phone, another language or high contrast.

## Rules

- **Read-only.** Do not edit any repository file. The only file you create is your report, at the path in your assignment. Do not run git. Do not post anywhere. Do not send any content to a third-party service: the repository is private.
- Verify before you assert. Quote the passage (at most 25 words) and give `file:line`.
- Give a concrete fix for each finding: a replacement sentence or "delete".
- No praise padding, no summary of what the document says.
- The design makes these choices; do not flag them as findings, but flag anything that contradicts them: a person is asked one decision at a time; an approval is bound to an exact plan, a person and a time; nothing is approved by free text, a reply, a text message or voice; silence is never consent; a card never carries a change through a fallback; every message says an AI wrote it; the system never asks two people to approve a purchase it cannot make. Where you think a choice is wrong, say so once, as a Minor finding with your reason.

## Report format (at most 1,800 words)

1. **Verdict**: could a stranger understand, trust and build from these documents? yes, mostly or no, in two sentences.
2. **Findings**: a table with columns `#`, `Severity` (Blocker = wrong or embarrassing; Major = confusing or misleading; Minor = polish), `File:line`, `Class` (1 to 8 above), `Quote`, `Why`, `Fix`. Sorted by severity.
3. **Sentences I would delete** (up to ten, with `file:line`).
4. **Fact checks**: each claim you checked, the URL, and the result.
5. **Questions left unanswered** (up to five).
