# Changelog

All notable changes, newest first. Versions are git tags (`design-v1` for the design, `ideation-v4` for the ideation). Earlier versions are archived under [`docs/_archive/`](docs/_archive/) and are never edited.

## design-v1 — 2026-11-01 — design phase 1: architecture, decisions, cost model and test strategy (tag `design-v1`)

**Why.** With the ideation frozen (tag `ideation-v4`), the operator asked for the design: completely AI-driven; Microsoft Foundry and the Microsoft Agent Framework; every AI part deployed through the Citadel framework in his landing zone; every safeguard and drift control; security, compliance, test and governance; every technology decision put to two rubber-duck rounds on different models; and as cost-efficient as possible.

**What.** [`docs/design/`](docs/design/README.md) — an index and fourteen documents (about 129,000 words): requirements and principles · technology landscape (what was adopted, evaluated, kept behind a preview switch or left out, from the operator's list of 817 platform updates) · logical architecture · landing zone and Citadel (hub contracts per agent group, data class and environment) · agents and orchestration · data and knowledge · security architecture · governance and compliance · safeguards and drift controls · test and evaluation · delivery and operations · cost and FinOps · 37 decisions · next phases. Evidence is in [`docs/design/research/`](docs/design/research/) (16 files from 14 research agents, every vendor page read on the day it is cited) and in a snapshot of 2,468 Azure price meters. Still no code.

### The design in six lines
- **A deterministic spine with agentic leaves**: Durable Functions workflows call fourteen hosted-agent roles (fifteen Entra agent identities, eleven contract groups, twelve contracts) one step at a time through the Citadel hub; agents can only read; the Agent Framework runs only inside the leaves.
- **One small execution plane can change an estate**, and *no single credential completes a change that needs a person's web-page approval*: a Policy permit, a person's Entra-signed approval bound to the target and the decision, an Approval service that signs and starts nothing, a broker that verifies and leases, an event-driven runner that verifies again and acts as an identity that exists only for that Move, write-ahead entries in an append-only ledger. What remains is stated in one place and repeated verbatim.
- **Nineteen drift layers** (each with prevent, detect and correct) and **twenty detections**; a preview register in which every preview feature sits behind a switch with a generally available fallback.
- **A statistical test protocol** with signed gate evidence and an exam the system cannot see.
- **A cost model in code** — about €1.2k a month at Pilot, €4.3k at Team and €27k at Enterprise scale (shared hub, list prices) — and a budget that is the spine's atomic reservation of the worst case of every metered part of a call, with the hub's limits as a second layer.
- **34 spikes** that could invalidate a decision, in seven build phases; nothing that changes an estate is switched on before S-ID-1, S-ID-3 and S-ACT-1 pass.

### How it was reviewed
Three passes, nine models, every lens on a different model each time. **Round 1** (five lenses: architecture · security, safety and compliance · cost and operability · AI engineering, evaluation and drift · platform fact-check) found 77 issues; **Round 2** reviewed the revision with other models and found 55 (about 45 distinct); a **targeted third pass** by two further models on the parts Round 2 had *redesigned* found 33 more. Raw reports are kept verbatim in [`docs/reviews/`](docs/reviews/README.md) with the orchestrator's own spot-checks and a disposition for every finding.

### What review changed
- **The spine** moved from a custom checkpoint-and-jobs design to Durable Functions on Flex Consumption (Round 1).
- **The execution chain** was reversed twice and hardened a third time: the broker no longer grants *and* dispatches (Round 1); the signer no longer starts the runner, which is event-driven (Round 2, after Learn confirmed that starting a Container Apps job can override its template); the third pass bound the decision into the sign-in nonce, made control items and markers verifiable by signature ("only narrowing is unsigned"), put write-ahead entries before every effect, required the broker to read the approval's own ledger block, and found two things that could not have been deployed — a private endpoint in a delegated subnet and cross-environment calls over internal ingress.
- **The leaf-call rule**: a hosted agent that returns at once is deprovisioned at its idle timeout, so each role's timeout now covers its active time, and completion is a persisted, identity-bound `run-result` record with the event only as a doorbell.
- **The budget**: the hub's token limits are not euros; the spine's reservation now covers tokens, session compute, screening and tools, and the hub refuses any caller-supplied service tier (a request-level priority tier would have been billed at a rate nothing priced).
- **The cost model was rebuilt** and the estimate more than doubled for Team (draft €657 / €1,818 / €17.5k a month for Pilot / Team / Enterprise → €1,244 / €4,278 / €27.0k): it now counts one product per contract and environment, hosted-agent compute including the idle tail, prompt-cache write prices, Content Safety windows, always-ready Flex capacity (which has no free grants), the gate plan and the evaluation work that carries the design's claims (evaluation costs 9.3 / 3.6 / 0.6 times the production cases).
- **Foundry layout**: two projects per account, not nine; environments and private accounts are created in the phase that needs them.

### Tools and rules
- [`tools/cost-model.py`](tools/cost-model.py): rebuilt; generates the cost tables of the design and the hub's quotas; `--check` also guards the access-contract table of 04 §4.3 (names, aliases, pools, PROD products) and the phase profile of 14 §4; `--self-test` holds 17 negative fixtures.
- [`tools/check-docs.py`](tools/check-docs.py): a design scope (links, anchors, diagrams, banned stale phrases, counts).
- [`AGENTS.md`](AGENTS.md) rule 11 gains: say what a compromised party can still do; numbers in 12 come from the model; sweep the seams after a large parallel revision.

## v4 — 2026-10-31 — rebuilt around a learning system (tag `ideation-v4`)

**Why.** The operator rejected the whole v1 → v3.2.1 package. It was built around his two example findings (cast as "seed examples" and release plays); it lacked the heart of the idea — *how the AI learns about new Azure services, gathers knowledge, investigates cost implications, experiments and recommends*; it was buried in governance paperwork (decisions, assumptions, risks, kill criteria, a threat catalogue) that has no place in ideation; and its pictures were linear pipelines.

**What changed.** The entire live package was replaced. **v3.2.1 is archived untouched** in [`docs/_archive/round-3-v3.2.1/`](docs/_archive/round-3-v3.2.1/) (tag `ideation-v3.2.1`), and its reusable parts — interaction concepts, ownership, moonshots, the 145-trap research, the guardrail inventory — were mined, not deleted.

### New
- A **north star** — [01](docs/01-north-star.md): "a scientist for Azure's economics", five faculties (STUDY · SURVEY · TEST · ACT · GROW) around one memory, four clocks, a cast of 13 agents.
- Six deep-dives: [02 Studying Azure](docs/02-learning-azure.md) (Atlas, a 14-mechanism Cost Grammar, claims with scoped receipts, Knowledge CI, day zero — with a real, documented example) · [03 The estate and the investigation](docs/03-estate-and-investigation.md) (Estate Model, human graph, Agenda, Skeptic, causal Consequence Engine, a gallery of 34 cases across every mechanism) · [04 Experiments and the Lab](docs/04-experiments-and-the-lab.md) · [05 Recommend, act, verify](docs/05-recommend-act-verify.md) (what happens to an Advisor card, Moves, earned autonomy, the Commitment Desk, verification) · [06 People and conversation](docs/06-people-and-conversation.md) · [07 Getting smarter](docs/07-getting-smarter.md) (predictions, the Exam and its independence, the report card, the Commons).
- [11 The learning contract](docs/11-the-learning-contract.md) — what *changes* when it learns (six things, each with evidence, update rule, the moment it is relied on and a test), what "verified" means, the gates that replace the single word "trusted", counterfactual evidence versus proof, baselines, and whether it pays for itself.
- [08 Outer rims](docs/08-outer-rims.md) (37 learning-centred ideas) · [09 Guardrails, later](docs/09-guardrails-later.md) (themes, plus the CAF / WAF / FinOps map) · [10 What next](docs/10-what-next.md) (a first experiment with baselines) · [12 Press release from the future](docs/12-press-release-from-the-future.md).
- Research: [the landscape through the lens of learning](docs/research/landscape.md), [inspirations — how agents learn](docs/research/inspirations.md) (24 papers, every identifier checked against arXiv), and the 145-trap catalogue re-cast as an [exam bank](docs/research/exam-bank-cost-traps.md).
- Three pictures built from loops, hubs and state changes: [living system](docs/img/living-system.svg), [four clocks](docs/img/four-clocks.svg), [escalation as widening circles](docs/img/escalation-rings.svg).
- A new [`tools/check-docs.py`](tools/check-docs.py): links, anchors (GitHub slug rules), diagrams, orphans, and guards against the operator's two examples creeping into the design, governance paperwork returning, and pipelines in disguise.
- [`docs/reviews/`](docs/reviews/README.md): the rubber-duck record — rounds 1 and 2, four independent reviewers each, with raw reports, spot-checks and a disposition for each round.

### Removed from the live package (kept in the archive)
Decision register, assumption and risk registers, kill criteria, spikes, the 305-row opportunity catalog as a design artefact, release plans built on the two examples, the threat catalogue, and every linear pipeline picture.

### Rules
[`AGENTS.md`](AGENTS.md) now also records: this is a learning system, not a rulebook; the two original findings are exam questions only; pictures show loops; ideation is not technology; no governance paperwork during ideation; one wording for purchases (prepared by the AI, approved by two named humans, executed by the AI).

## Earlier versions (v1 → v3.2.1) — superseded by v4

- **v3.2.1** — the repository stays private until the operator says to switch it; `AGENTS.md` added.
- **v3.2** — licence decided: MIT; `LICENSE` added.
- **v3.1** — a patch after two post-v3 audits (17 defects: catalog reclassification, normative text, evidence re-verified).
- **v3** — after review round 2: a red team, a Learn-grounded fact-check and a consistency review; the safety model made one normative set of rules.
- **v2** — after review round 1: three reviewers, 41 findings accepted; plan, research and decision status added.
- **v1** — the first ideation pass: a vision, an opportunity catalog, an agent crew, interaction concepts and a follow-up plan.

The full text of those entries is in [`CHANGELOG-through-v3.2.1.md`](docs/_archive/round-3-v3.2.1/CHANGELOG-through-v3.2.1.md) (it opens with an abandoned draft of the v4 entry, written before the rebuild and kept as found); the tags are `ideation-v1` … `ideation-v3.2.1`.
