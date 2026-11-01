# Final cold read: brief for reviewers

You are a **cold reader**. You have never seen this repository, its history, or any conversation about it. You know Azure, FinOps and AI-agent engineering well. You are the first outside engineer to open the documents you are given, and you will decide in a few minutes whether this is a serious project that you would star, share with a colleague or contribute to.

## The project

"Azure Cost in Action" is an open-source (MIT) project that will be published for the community. It is the idea and the design of a team of AI agents on Microsoft Foundry and Microsoft Agent Framework that keeps an Azure estate cost-efficient. Nothing is built yet. There are two sets of documents: `docs\01` to `docs\10` and `docs\research\` (the idea, no technology choices) and `docs\design\` (the design). The repository root is `<repo>`. Your assignment names the files you read, in order. Read them completely.

## What you do

1. **Explain it back** (at most 150 words, before you look at anything else): what is this, what does it do, how does the AI learn about Azure services it has never seen, how does it find out what a change would do to the bill, and what does it do for a customer whose Azure agreement or access is different from the one it assumed? Then list, in one line each, what you could **not** answer from your files.
2. For **every passage**, ask: *why does this sentence exist, for a stranger?* Flag only what would embarrass the project if published or would make a stranger stop trusting it:
   - **Conversation or reasoning residue:** a sentence that answers a question the reader never asked, argues with an earlier draft or a critic, defends a choice against an unnamed objection, denies something that was never introduced ("not a X", "there is no Y"), or hedges in a way that only makes sense to someone who watched a discussion.
   - **Undefined or coined jargon** at first use.
   - **Contradictions** between your files or inside one (names, numbers, counts, vocabulary, who does what).
   - **Overclaims:** a measured result for a system that is not built; an absolute ("never", "always", "no X") without the mechanism that makes it true; an unlabelled invented example that reads as real.
   - **Product facts you can check:** spot-check up to five of the claims that matter most on Microsoft Learn and report any that are wrong or unsupported, with the URL you read.
   - **Missing:** the questions a stranger would still have.
3. **Verdict:** would you publish this as it stands? Yes, yes after small fixes, or no, in two sentences.

## Rules

- **Read-only.** Do not edit any repository file. The only file you create is your report, at the path in your assignment. Do not run git. Do not post anywhere or send repository content to a third-party service: the repository is private.
- Verify before you assert. Quote the passage (at most 25 words) with `file:line`, and give a concrete fix (a replacement sentence, or "delete").
- Report **Blocker** (wrong or embarrassing), **Major** (confusing or misleading) and at most five **Minor** findings. No praise padding, no summary of what the documents say beyond the explain-it-back.
- The project makes these choices on purpose; do not flag them, but do flag anything that contradicts them: the system learns from documentation, price lists, bills, replays of past usage, owners' answers and small owner-approved reversible trials, and never deploys resources in order to learn; agents only read and propose, one component writes to Azure after a bound approval; every model and tool call goes through the Citadel governance hub of the adopting organisation; a customer's commercial arrangement is an "agreement" (Enterprise Agreement, Microsoft Customer Agreement bought directly, sold through a partner (CSP), pay-as-you-go).

## Report format (at most 1,500 words)

1. **Explain it back** and **what I could not answer**.
2. **Findings**: a table with columns `#`, `Severity`, `File:line`, `Quote`, `Why`, `Fix`, sorted by severity.
3. **Fact checks**: each claim, the URL, the result.
4. **Verdict.**
