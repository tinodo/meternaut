# Design review brief

> Used for both rubber-duck rounds of design phase 1 and, in a narrowed form (see the last section), for the targeted third pass. Each round gives every lens to a **different model** than the round before, so every part of the design is challenged by two different minds. This file is the standing brief; the exact files and the model for each lens are named in each reviewer's prompt and recorded in the round's [disposition](README.md).

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

## Round 2 — what is different

Round 2 reviews the design **after** the Round-1 revisions, with a **different model on each lens than in Round 1**. The record of Round 1 — what the reviewers said, what was checked, what was changed — is [`design-v1-round-1/disposition.md`](design-v1-round-1/disposition.md) and the raw reports next to it. In addition to the lens work above:

1. **Do not re-raise** a Round-1 finding that was fixed, unless the fix is wrong, incomplete or contradicted elsewhere; say which.
2. **Audit the disposition for truth.** For every Round-1 finding in your lens, open the file and section the disposition says changed and confirm the change is there and correct. A change that is claimed but absent, or present but contradicted by another document, is a **Critical** finding.
3. **Attack the new material first**: the three-party authority chain (Approval service signs and dispatches; broker verifies and grants; Move runner verifies live state; Audit Writer), the eleven contract groups with per-tool authorisation, the Durable Functions spine, the source sanitiser, the statistical protocol and signed gate evidence, the ledger and recovery changes, the CI and supply-chain rules, the fast-signal path (W3b) and method learning (W10), the new spikes, and the corrected cost model (`<repo>\tools\cost-model.py`, which you may run read-only).
4. **Consistency after a large edit.** Counts (fourteen roles, fifteen identities, eleven groups, two Foundry projects per account), names, anchors and numbers must agree across all documents; list every disagreement you find.
5. **Platform facts.** Anything that changed in Round 1 is a new claim and must be verified on the vendor's page today, not accepted because the disposition says so.

## Targeted third pass — what is different

Round 2 *redesigned* four things rather than patching them, and a redesign is exactly where a reviewer who saw only the earlier version cannot vouch for the new one. The third pass is **two reviewers, each on two of the four subjects, each on a model that reviewed none of the earlier rounds**, and it looks at nothing else. **T-A** takes *the authority chain* and *the leaf-call rule*; **T-B** takes *the spend budget* and *the contract × environment model*. The record is [`design-v1-round-2/disposition.md`](design-v1-round-2/disposition.md) (themes 2.1–2.7 say what was redesigned and why).

The four subjects, and the question for each:

| Subject | Where it lives | The question |
|---|---|---|
| **The authority chain** | `07-security-architecture.md`, `08-governance-and-compliance.md`, `13-decisions.md` ADR-07 and ADR-08, `05-agents-and-orchestration.md`, `09-safeguards-and-drift-controls.md` (controls Z3, D16, D19) | Policy permit → Brief → person's approval (Entra token, nonce = target hash) → Approval service signs and **enqueues** (holds no `Microsoft.App/jobs/*` action) → queue-triggered broker verifies, leases, grants, writes the ledger and reads it back → event-driven runner job → Verifier. Can any **one** compromised party — code or identity — complete, start, forge, replay or hide a change? Is every statement of what a party can do true of the *other* documents? Is the honest residual stated everywhere, and nowhere hidden by a stronger sentence? |
| **The leaf-call rule** | `05-agents-and-orchestration.md`, `03-logical-architecture.md`, `04-landing-zone-and-citadel.md`, ADR-33 | The spine calls a hosted-agent leaf, gets an immediate return, and learns of completion from one terminal `run-completed` event; per-role idle timeouts exceed p99 active time; a deadline timer is the backstop; a restore re-opens cases as `<workflow>:<case id>:<epoch>`. Can a case hang, be deprovisioned mid-run, be run twice, lose its spend, or complete without the event? Do the idle timeouts in the text, in `tools\cost-model.py` and in the spike S-HOST-1 agree? |
| **The spend budget** | `12-cost-and-finops.md`, ADR-26, `04-landing-zone-and-citadel.md` §4.3 | The spine's reservation is the budget; the hub's token limits are a second layer; the Euro figures are *forecast-equivalent* and *worst case*, never a cap. Is there a path by which spend exceeds the reservation by more than the stated in-flight overrun? Does every number in the generated block follow from the model, and does the text around it say only what the numbers show? (You may run `python tools\cost-model.py --check docs\design\12-cost-and-finops.md` and `--quotas`.) |
| **The contract × environment model** | `04-landing-zone-and-citadel.md` §4.3, `12-cost-and-finops.md`, `11-delivery-and-operations.md` | Twelve contracts across DEV, TEST and PROD where work is planned; TEST and DEV synthetic-only on public pools; phase profiles that add environments by phase. Do counts, names, aliases and per-phase floors agree across the documents, and does the phase profile in 11 match the one priced in 12? |

You are **not** asked to re-litigate a decision, to judge style, or to re-review anything Round 2 did not touch. Do **not** re-raise a Round-1 or Round-2 finding the disposition says was fixed unless the fix is wrong, incomplete or contradicted; say which document contradicts it.

Everything else in the standing brief applies — read-only except your own report, verbatim quotes with full absolute paths, vendor URL and a quote of at most 25 words for every platform claim, `UNVERIFIED` where you could not confirm. Number findings `TA-NN` or `TB-NN`. Give the five-line verdict and the findings (at most about 2,500 words), and an **Agree / Agree with changes / Disagree** with the evidence that would change your mind for the ADRs of your subjects (T-A: ADR-07, ADR-08, ADR-33; T-B: ADR-26 and ADR-06). The orchestrator checks every quote and re-verifies every platform fact you rely on before using it.

