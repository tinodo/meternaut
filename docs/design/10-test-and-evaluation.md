# Design 10 — Test and evaluation strategy

> **What this answers:** *How do we know — before every release and every day after — that the system finds real waste, stays quiet on decoys, cannot be talked into harm, and has not got worse?*
> The ideation already invented the instrument: the **Terrarium** and the **Exam** ([north star](../01-north-star.md#8-grow--how-it-gets-better), [getting smarter §3](../07-getting-smarter.md#3-the-exam)). This document turns them into the project's own test harness and wraps the rest of the test pyramid around them. Part of the [design](README.md); the release gates feed [delivery and operations](11-delivery-and-operations.md) and the drift controls in [09](09-safeguards-and-drift-controls.md).

---

## 1. How testing an AI system differs

| Ordinary software | This system |
|---|---|
| a test passes or fails | an evaluation is a **rate with an interval**: "the rediscovery rate is 71% (63–78%)" |
| the same input gives the same output | the same input gives a *distribution*; tests run repeatedly and are seeded where they can be |
| the spec is the oracle | the oracle is an **answer key held apart from the system** (the Examiner's), a rubric, or a human |
| code changes cause regressions | **models, prompts, Moves, Atlas releases, contracts and the world** cause regressions — the last without any commit |
| security tests probe code | security tests also probe **persuasion**: documents, tool output and other agents that try to steer the model |

So three rules run through everything below. **Deterministic code gets deterministic tests.** **Agent behaviour gets statistical evaluations with confidence intervals and baselines.** **Safety and security tests are release blockers, not scores.**

## 2. The layers

| Layer | What is tested | How | When |
|---|---|---|---|
| **L0 Static** | code, infrastructure, contracts, prompts, dependencies | linters, type checks, infrastructure what-if and policy-as-code checks, secret and licence scanning, an SBOM, schema validation of prompts, agent definitions and contracts | every commit |
| **L1 Unit** | the deterministic services: price engine arithmetic, policy decisions, the two-key approval rule, credential broker, document sanitiser | ordinary and property-based tests; golden files for prices; **an approval can never cover a target other than its own** is a property, not an example | every commit |
| **L2 Contract** | tool and agent interfaces; gateway policies; Move preconditions, dry runs and rollbacks | schema tests of every tool and agent card; gateway policy tests against a test gateway (token limit trips, content-safety verdicts, redaction); each Move's dry run and rollback exercised against a Lab fixture | every pull request |
| **L3 Agent evaluations** | one agent at a time: task adherence, groundedness against receipts, tool-call accuracy, arithmetic-from-tools, abstention | golden cases with rubrics; deterministic checks first, a judge model second, **two judges that must agree** and a human sample; thresholds on the *lower* bound of the interval | every change to a prompt, model, tool or contract |
| **L4 Workflow evaluations** | the whole loop on synthetic estates — [§3](#3-the-terrarium-as-the-test-harness) | rediscovery, decoys, transfer, new-service races, calibration, explanation, cost per case | nightly (small), weekly and before release (full) |
| **L5 Security and safety** | injection (direct, indirect, through tool output, through memory, between agents), jailbreak, exfiltration through tools, privilege escalation, excessive agency, gateway bypass | a maintained attack suite, an **AI red-teaming agent** on a schedule, a canary agent that tries to reach a model or an estate directly and must be blocked and alerted, a human red team each quarter | every release; scheduled; continuously for the canary |
| **L6 Resilience** | degraded modes ([03 §6](03-logical-architecture.md#6-degraded-modes)), idempotency, rollback | chaos drills: gateway down, approval expired, target changed, credential expired, model outage, Lab budget exceeded, duplicate delivery; a restore drill for the approval and audit stores | monthly; before release |
| **L7 Cost and performance** | tokens, latency and cost per case; cache hit rate; the system's own bill | each evaluation also records **tokens, euros and seconds**; a regression in cost per case fails like a regression in accuracy | every evaluation |
| **L8 Production** | the live system, on its own traces | shadow mode for new agents and Moves; **continuous evaluation** on sampled traces; online alerts on drift in evaluator scores, refusals, tool errors and cost | continuously |

## 3. The Terrarium as the test harness

Three tiers of estate, cheapest first, so most questions cost almost nothing.

| Tier | What it is | Cost | Used for |
|---|---|---|---|
| **T1 Paper estates** | purely synthetic data: resource inventories, cost exports, metrics, activity logs, documents — **no Azure deployment** | pennies | most exam questions; every pull request; the injection suite |
| **T2 Lab estates** | miniature estates actually deployed in a Lab subscription for tests that need *real billing behaviour* | euros, with an expiry | mechanism-verification, Move dry runs and rollbacks, wind-tunnel checks |
| **T3 Real estates** | labelled retrospective cases from real estates, with consent, **post-cutoff** | none | the credential exam; leakage-free scoring |

- **The Forger generates; the Examiner scores.** Waste, decoys and confounders are generated from a seeded recipe (so a failure reproduces), and the **answer key is stored where no agent identity can read it**. The scoring service has its own identity; the reasoning plane has none that reaches the key.
- **Three exams, kept apart** ([getting smarter §3](../07-getting-smarter.md#independence--who-examines-the-examiner)): the *training Terrarium* (the system learns from its misses), the *public benchmark* (open; never used for credentials), the *credential exam* (held out, run by people outside the day-to-day, used only to decide autonomy).
- **Baselines on every exam**: a retrieval-only system, the expert-written seed and an experienced practitioner. A change that does not beat the baseline it should beat does not ship.
- **Canaries in the tests**: the Forger also plants *known* failures in the evaluations themselves (a judge that must catch a deliberately bad answer), so a blind judge is noticed.

## 4. Release gates

Each gate has evidence and an initial threshold. **Thresholds are starting values**, calibrated against baselines in phase 2; what is fixed is the *kind* of evidence.

| Gate | Evidence | Blocks release when |
|---|---|---|
| **G1 Build integrity** | L0–L2 green; SBOM and licence report; signed artefacts | any failure |
| **G2 Safety** | L5 attack suite | any **critical** finding; resistance below the previous release's by more than the interval |
| **G3 Restraint** | L4 decoys | a **harmful** recommendation on any decoy (zero tolerance), or false alarms above the baseline's |
| **G4 Capability** | L3 and L4 against the baselines | the lower bound of the interval falls below the baseline's or below the previous release's by more than a margin |
| **G5 Honesty** | calibration, abstention, claims scoped to their receipts | calibration error above its limit; any claim without a receipt |
| **G6 Cost** | tokens, euros and seconds per case | cost per case above its budget in the agent's contract |
| **G7 Resilience** | L6 drills | a drill fails, or its recovery exceeds the objective |
| **G8 Compliance** | the control checks of [design 08](08-governance-and-compliance.md#13-policy-as-code) | a control cannot show its evidence |
| **G9 Autonomy** (separate) | the **credential exam** and the Move's shadow record | not passed: no credential is granted or renewed — whatever the other gates say |

A release that changes **only** an agent's prompt still passes G2–G6 for that agent and for every workflow it takes part in. A change of **model version** is a release.

## 5. Environments and promotion

| Environment | Reads | Acts | Purpose |
|---|---|---|---|
| **Local** | paper estates | nothing | development; L0–L3 |
| **Dev** | paper and Lab estates | the Lab only | L4, L5, L6; contract tests against a real gateway |
| **Shadow** | the real estate, read-only | **nothing** — every Move runs as a dry run and is logged | the new agent or Move proves itself on real data without effect; L8 |
| **Production** | the real estate | only what an approval or a credential allows | the credential exam and the Move's record decide |

Promotion to the next environment is the passing of the gates above for that environment. Nothing skips shadow.

## 6. Privacy in testing

Synthetic data by default. Production traces used for continuous evaluation are **sampled, redacted of personal data before they are stored for evaluation, and kept for a short, stated period**; evaluators run inside the tenant. Estate data never leaves the tenant and the EU boundary for testing any more than for operation ([Q-PRV-1](01-requirements-and-principles.md#4-quality-targets)).

## 7. Testing the tests

- **Judge drift.** When a judge model or its prompt changes, the baselines are re-run and the change is itself a release with its own gate.
- **Mutation and planted failures** for the deterministic services and the evaluators.
- **Human sampling**: a small, regular sample of evaluations is read by a person, and disagreements with the judges become new golden cases.
- **Leakage audit** before every credential exam: nothing the system may have seen resembles a question.
- **Flake budget**: a test that fails intermittently is statistical by nature; it gets an interval and an owner, not a retry loop.

## 8. What feeds back

Every evaluation produces data the system itself uses: misses become Agenda questions and lessons; the cost and accuracy numbers become the [report card](../07-getting-smarter.md#4-the-report-card); a drift alert becomes a case for the Auditor. Testing is not a phase of the project; it is one of the faculties of the system.

## 9. Platform mapping

How the layers of [§2](#2-the-layers) and the gates of [§4](#4-release-gates) are run on the platform chosen in [04](04-landing-zone-and-citadel.md), [05](05-agents-and-orchestration.md) and [11](11-delivery-and-operations.md). Platform facts come from the [Foundry governance research](research/foundry-governance-and-framework.md) and the [security research](research/security-and-compliance.md), checked on 2026-10-31.

**Where tests run.** Static and unit tests run on GitHub-hosted runners with recorded fixtures and paper estates. Anything that calls the hub, a model or a private endpoint runs on **self-hosted runners that are Container Apps event jobs inside the spoke's network**, authenticating with workload identity federation — GitHub-hosted runners cannot reach private endpoints. Model calls in tests go through the **non-production hub contracts**, so evaluation spend is metered and capped like everything else.

| Layer | Mechanism | Platform state | If unavailable |
|---|---|---|---|
| **L0 Static** | Bicep build and lint; `what-if` on every infrastructure change; Policy-as-code checks; secret scanning with push protection; dependency review; SBOM and licence report; image signing (to confirm: Notation with a Key Vault key — spike **S-DEL-1**) | generally available | — |
| **L1 Unit** | xUnit with property-based tests for the execution plane (C#); pytest with Hypothesis for Python; golden files for prices from the price snapshot | open-source libraries | — |
| **L2 Contract** | HTTP-level contract tests against a **test hub**: token limit trips (429), quota (403), model access (401 `unauthorized_model_access`), role check (403 `insufficient_role`), content-safety block (403), MCP `tools/list` hash; MCP tool schema tests; each Move's dry run and rollback against a Lab fixture | the hub's own validation is Jupyter notebooks, which are not CI-shaped, so these tests are ours | — |
| **L3 Agent evaluations** | **Foundry evaluations** (generally available) with built-in and custom evaluators; deterministic evaluators first (arithmetic-from-tools: every figure in an output must equal a tool result; receipt presence); judge calls through the `govern` contract's judge aliases; **two judges must agree**; judge prompts keep a static prefix so caching applies (measured on the platform: cached tokens from under 1 % to about 70 %, judge input down 61–71 % with composite evaluators, which are preview) | evaluations GA; composite evaluators preview; **Groundedness retires 30 Apr 2027**, so groundedness is a custom receipts check, not that evaluator | our own harness as Container Apps jobs calling the hub |
| **L4 Workflow evaluations** | the **Terrarium** ([§3](#3-the-terrarium-as-the-test-harness)): the Forger generates paper estates; the spine runs W4 against a test case store with agents in *dev*; the **Examiner's scoring service** has its own identity and the answer keys sit in a separate storage account that only it can read; T2 estates are deployed in Lab subscriptions as Deployment Stacks | our code | — |
| **L5 Security and safety** | **PyRIT** and **ASSERT** attack suites in CI (open source, MIT); the **AI Red Teaming Agent** (cloud runs: Sweden Central and France Central in the EU) on a schedule in a purple environment — it covers Foundry prompt and container agents with Azure tools, **not** function tools, non-Azure tools or workflow agents, so PyRIT covers the rest; the daily **canary agent**; planted injections in every untrusted source; a quarterly human red team | red-teaming agent: cloud API preview | PyRIT alone |
| **L6 Resilience** | scripted drills as pipeline jobs: suspend a hub product, expire an approval, change a target, expire a credential, point an alias at a dead backend, exceed a Lab budget, duplicate a delivery; a monthly restore drill of the ledger and the operational store; each kill switch pulled | our code | — |
| **L7 Cost and performance** | every evaluation records tokens, euros and seconds from the hub's logs (`customDimension2` carries the run id) and from traces | hub logs and Application Insights | — |
| **L8 Production** | the **shadow** environment (the production spoke reading the real estate with every Move a dry run); **continuous evaluation** on sampled traces (the platform's default is 100 runs an hour, which we lower); evaluator-score drift alerts (DR-12); Insights in Foundry (preview) as a human aid | continuous evaluation per the platform; Insights preview | our own sampler job |

**Evaluations inside the private network.** The platform's *managed virtual network for evaluations* (generally available) lets evaluation runs reach private endpoints; its EU region list is unverified, so the fallback is the self-hosted harness above.

**Release gates, as pipeline stages**

| Gate | Implemented as |
|---|---|
| **G1 Build integrity** | required status checks on protected branches; SBOM, licence report and signature verified before a promotion |
| **G2 Safety** | the L5 job's result; a critical finding or a drop beyond the interval fails the stage; the canary's status is an input |
| **G3 Restraint** | the L4 decoy job: a harmful recommendation on any decoy fails; false alarms are compared with the baseline |
| **G4 Capability** | L3 and L4 results compared with the stored baselines in `evals/baselines/` using the lower bound of the interval |
| **G5 Honesty** | calibration and abstention from the Ledger on synthetic cases; the receipts check |
| **G6 Cost** | the per-case cost from L7 against the agent's contract budget |
| **G7 Resilience** | the L6 drill report and its recovery times |
| **G8 Compliance** | the control-map check ([08 §1.3](08-governance-and-compliance.md#13-policy-as-code)) |
| **G9 Autonomy** | **no pipeline can grant it**: the credential exam is run by people outside the day-to-day, the result is written to the Ledger, and an autonomy credential is a human act |

**Environments** ([§5](#5-environments-and-promotion)) map to subscriptions: *local* (a development container, paper estates, the Agent Framework's local debugger — never deployed), *dev* and *test* (separate Foundry accounts in the non-production spoke), *shadow* and *production* (the production spoke), with the Lab as its own management group. **Nothing skips shadow.**
