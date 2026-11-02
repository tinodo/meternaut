# Decision review brief: experience design (common to every reviewer)

## What you review

*Azure Cost in Action*: an open-source (MIT), AI-driven, human-in-the-loop Azure cost-optimisation system built on Microsoft Foundry, Microsoft Agent Framework and a governance hub. Workflows call agents; it is not a chatbot. It learns from documentation, price lists, bills, replays, owners' answers and small owner-approved trials, never by spending money to learn. It serves every Azure agreement and access level (Enterprise Agreement, Microsoft Customer Agreement bought directly, Microsoft Customer Agreement sold through a partner, pay-as-you-go) and every level of access (billing reach, subscription with costs, subscription without costs).

The technical design is released: `<repo>\docs\design\` (README, then 01 to 14). The idea is in `docs\01-north-star.md` to `docs\10-*.md`; the people-and-conversation idea is `docs\06-people-and-conversation.md`.

**You are reviewing the next layer: the experience design.** What each person sees, receives and decides; in which channel; in what words; how the system spends and protects people's attention. It will live in `docs\experience\`. Nothing is built. The source of truth for the decisions is the spec:

`<session>\files\exp-spec\spec.md` (read it in full, 20 sections; the decisions are section 17, X1 to X27; the attention numbers are section 11; the card catalogue is section 7).

Assets already made (look at them, they are part of the proposal):
- 15 Adaptive Card templates: `<repo>\docs\experience\cards\*.json` (sample data in `cards\data\`, catalogue in `cards\manifest.json`).
- 6 wireframes: `<repo>\docs\img\experience-*.svg` (view them as images if you can; they are plain SVG text otherwise).
- The verified platform facts: `<session>\files\research-exp\R1-teams.md` to `R9-regulation-accessibility.md` (each fact has a status and a URL).

## Fixed requirements (do not argue with them; judge whether the experience design meets them)

1. Completely AI-driven; a person approves every change that touches Azure (human in the loop); never a chatbot as the main interface.
2. Microsoft technology only; open source (MIT); runs in the adopting organisation's Azure; Teams and Outlook are the places people already are.
3. The standard of care is the same at every level of access and under every agreement; what the system cannot see changes the words and the buttons, never the standard.
4. As cost-efficient as possible, including its own running cost and the cost of people's attention.
5. Written for the Azure community: plain, lean, no personal references, no jargon. The experience must be usable by people who have never heard of the project.
6. The examples in the experience documents are invented. They must not be built on the original findings that started the project (they live only as ordinary rows in `docs\research\cost-trap-bank.md`).

## How to review

- Read what your assignment names, in full. Be adversarial but fair: one line on what is good, then spend your words on what is wrong, missing or unsafe. Push back on decisions you think are wrong, and say what you would do instead and why. The spec is not gospel.
- Facts: before you assert that a claim about a Microsoft product or a regulation is wrong, verify it on Microsoft Learn or the primary source (tools `microsoft-learn-microsoft_docs_search` and `microsoft-learn-microsoft_docs_fetch`, or `web_fetch`) and cite the URL. Today is 2026-11-02. Do not assert from memory; products change.
- Do not edit or create repository files. Write your report with the `create` tool to the path your assignment gives you (a single file), and keep your final message to 120 words: the path and your five most important findings.
- Judge the proposal as an experience designer would: would a busy resource owner act on this? Would a finance approver trust it? Would an attacker abuse it? Would it survive a works council, an auditor and a person with a screen reader?

## Report format (at most 1,800 words)

1. Verdict (3 lines).
2. Top 5 changes I would make to the decisions (each: what, why, what it costs).
3. Findings table: `# | Severity | Where (spec section or card id or wireframe) | What is wrong or missing | Proposed change`. Severity: **blocker** (wrong, unsafe or violates a fixed requirement), **major** (misleading, inconsistent, or missing something important), **minor** (polish).
4. Decisions I agree with, and the strongest reason each might still be wrong (X-numbers; at most 8 lines).
5. What is missing entirely (journeys, surfaces, states, people, failure modes).
6. What I verified myself (URLs and which claim each confirmed or refuted) and what I could not verify.
