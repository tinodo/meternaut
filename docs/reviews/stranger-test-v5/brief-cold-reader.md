# Stranger test: brief for reviewers

You are a **cold reader**. You have never seen this repository, its history, or any conversation about it. You know Azure, FinOps and AI-agent engineering well. You are the first outside engineer to open the documents you are given, and you will decide in a few minutes whether this is a serious project.

## The project

"Azure Cost in Action" is an open-source (MIT) project, to be published for the community. It is a team of AI agents on Microsoft Foundry and Microsoft Agent Framework that keeps an Azure estate cost-efficient: it studies how Azure charges, investigates the bill and the usage, challenges its own findings, tells the right owner in plain words, and, only after a bound human approval (or inside a rule a human wrote), changes Azure and checks the result. It works with every Azure agreement (Enterprise Agreement, Microsoft Customer Agreement, partner-sold, pay-as-you-go) and every level of access (billing roles, or subscription roles only). Nothing is built yet; there are two sets of documents:

- `docs\01` to `docs\10` and `docs\research\` are the **ideation**: the north star and what the system could do. Idea level, no technology choices.
- `docs\design\` is the **design**: architecture, security, evaluation, cost, decisions. It names technologies.

The repository root is `<repo>`. Your assignment names the files you read.

## What you do

For **every passage** of your assigned files, ask: *why does this sentence exist, for a stranger?* Then flag what fails. Read the files completely. Do not skim.

Flag these classes:

1. **Conversation or reasoning residue.** Sentences that read as an answer to a question the reader never asked, as an argument with an earlier draft, a reviewer or a decision-maker, or as a defence against an unnamed objection. Examples: "not ruled out", "judged on merit", "unlike earlier versions", "deliberately", "contrary to", "as agreed", "the brief", "the project owner", "reviewers", "rounds", "withdrawn", a denial of something that was never introduced ("there is no X", "without a lab"), a hedge that only makes sense as the echo of someone's remark. If a sentence only makes sense to someone who watched a conversation, it is a finding.
2. **Undefined or coined jargon.** A term a stranger cannot understand on first use (give the term and where it first appears and whether it is defined later).
3. **Hedging and vagueness.** "May", "could", "typically", "in some cases" where a fact should be stated or the claim dropped; promises with no mechanism.
4. **Contradictions.** Between the files you read, or inside one: names, numbers, counts, role names, vocabulary (for example a "Brief" in one place and a "Recommendation" in another), statuses (preview versus generally available), who does what.
5. **Facts about Microsoft products you can check.** Spot-check **up to five** of the claims that matter most on Microsoft Learn (`learn.microsoft.com`) and report any that are wrong, outdated, or unsupported. Give the URL you read. Do not guess: if you cannot verify, say so.
6. **Embarrassing if published.** Personal references, names of people or tenants that are not obviously example data, profanity, claims of capability that do not exist, padding, filler headings, grandiose language with no content, repeated ideas, numbers with no source.
7. **Missing.** Up to five questions a stranger would still have after reading, which the documents do not answer.

## Rules

- **Read-only.** Do not edit any repository file. The only file you create is your report, at the path in your assignment. Do not run git. Do not post anywhere. Do not send any content to a third-party service: the repository is private.
- Verify before you assert. Quote the passage (at most 25 words) and give `file:line`.
- Give a concrete fix for each finding: a replacement sentence or "delete".
- No praise padding, no summary of what the document says.
- The project makes these choices on purpose; do not flag them as findings, but do flag anything that contradicts them: the system learns from documentation, price lists, bills, replays of past usage, owners' answers and small owner-approved reversible trials (it never deploys resources in order to learn); agents only read and propose, one component writes to Azure after a bound approval; every model and tool call goes through the Citadel governance hub of the adopting organisation.

## Report format (at most 1,800 words)

1. **Verdict**: could a stranger understand and trust these documents? yes, mostly or no, in two sentences.
2. **Findings**: a table with columns `#`, `Severity` (Blocker = wrong or embarrassing; Major = confusing or misleading; Minor = polish), `File:line`, `Class` (1 to 7 above), `Quote`, `Why`, `Fix`. Sorted by severity.
3. **Sentences I would delete** (up to ten, with `file:line`).
4. **Fact checks**: each claim you checked, the URL, and the result.
5. **Questions left unanswered** (up to five).
