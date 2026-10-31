# Design review brief

> Used for both rubber-duck rounds of design phase 1. Each round gives every lens to a **different model** than the round before, so every part of the design is challenged by two different minds. This file is the standing brief; the exact files and the model for each lens are named in each reviewer's prompt and recorded in the round's [disposition](README.md).

## What you are reviewing

The design of **Azure Cost in Action** in `<repo>\docs\design\` (start at `README.md`; the requirements are in `01-requirements-and-principles.md`, the technology decisions in `13-decisions.md`). The *idea* it serves is the [north star](../01-north-star.md); do not re-litigate the idea, review the **design**. Read `AGENTS.md` for the standing rules. The research behind the design is in `docs\design\research\` (evidence, not design).

The operator's brief for this phase, typos normalised: *"completely driven by AI, completely AI infused … Microsoft Foundry and potentially the Microsoft Agent Framework … the latest and greatest new features in the Microsoft AI ecosystem … the AI parts all deployed using the Citadel framework in my landing zone … all possible latest and greatest safeguards and drift controls … security, compliance, test and governance … rubber duck all decisions on technology twice with different models … as cost efficient as possible."* **Today is 31 October 2026.** Anything you remember about Microsoft products from before 2026 may be stale: verify on the vendor's page.

## Your lens

You are given **one lens**; stay in it, but report a defect you cannot ignore from another.

| Lens | You are asked to |
|---|---|
| **A — Architecture** | find where the design does not hold together: contradictions between documents; single points of failure; a product used for what it is not for; a Citadel contract or landing-zone dependency that is wrong or missing; over-engineering; an alternative that was not considered; a Well-Architected pillar that is neglected. |
| **B — Security, safety and compliance** | attack it: gaps in the threat model; the execution plane, the approvals and the identity design; prompt injection, memory and knowledge poisoning, tool abuse, agent-to-agent trust, supply chain, the Lab as a pivot; data protection and residency; whether the EU AI Act, GDPR, NIS2 and ISO/IEC 42001 statements are accurate and whether the controls would really produce the evidence claimed. |
| **C — Cost and operability** | challenge every cost claim: hidden always-on meters, minimum SKUs, per-token and per-call charges nobody counted, the arithmetic and assumptions of the cost model, whether a cheaper option meets the requirement; and whether a small team could really run, monitor and recover this. |
| **D — AI engineering, evaluation and drift** | judge the agent decomposition and orchestration choices, the use of Foundry and the Agent Framework, the evaluation and release-gate design, and whether *every* kind of drift (infrastructure, identity, model, prompt, knowledge, behaviour, cost, network, policy) has a preventive, a detective and a corrective control that actually exists; whether preview features are properly gated with a fallback. |
| **E — Platform fact-check** | verify every statement about a Microsoft product, SKU, region, price, status (GA or preview), limit or licence against the vendor's page **today**; list what is wrong, outdated, over-general or unsupported, with a paste-ready correction. |

## Challenging the decisions

`13-decisions.md` records each technology decision with its alternatives. For **every** decision give a verdict — **Agree**, **Agree with changes** or **Disagree** — with your confidence, **the strongest alternative and why it was or was not right to reject it**, and *what evidence would change your mind*. A decision you only nod through is a finding against you.

## Rules

- **Read-only, with one exception.** Create, edit, move or delete nothing in the repository; run no command that changes state; post nothing anywhere; install nothing (public package registries are blocked on this machine). **The one permitted write is your own report**, saved *exactly as you will return it* to the path named in your prompt, so that the raw record is yours and unedited. You may read any file in the repository, run `python tools\check-docs.py --strict`, and fetch public web pages.
- **Cite precisely.** Give file and heading with the **full absolute Windows path**; any text in quotation marks must be copied **verbatim** — every quote will be checked, and findings whose quotes do not exist are discarded.
- **Cite sources.** For a claim about a Microsoft product, give the URL you fetched and a quote of at most 25 words. Mark what you could not verify `UNVERIFIED`; never invent a URL, feature or price.
- **Severity.** *Critical* = would likely cause a security failure, a wrong decision or a false claim in the design; *Major*; *Minor*.

## Output (at most about 3,500 words)

1. A **verdict in five lines**: is this design sound for your lens, and what is the one thing that must change?
2. **Findings**, numbered `<lens>-NN`, each with *Severity · File and heading (full path) · Quote (verbatim) · Why it matters · Fix*.
3. The **decision table**: `ADR · verdict · confidence · strongest alternative · what would change my mind`.
4. **What is strong** — what to keep.
5. **What is missing** — the five most important omissions for your lens.
