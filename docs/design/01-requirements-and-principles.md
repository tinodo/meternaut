# Design 01 — Requirements and principles

> **What this answers:** *What must the design satisfy, what may it not do, and which principles settle the arguments?* The functional requirements come from the [north star](../01-north-star.md); the quality targets and constraints come from the operator's design-phase brief and the rules in [AGENTS.md](../../AGENTS.md).
> Part of the [design](README.md). Every requirement below is answered somewhere in documents 03–12; the matrix at the end says where.

---

## 1. Constraints — what is not negotiable

| # | Constraint | Source |
|---|---|---|
| C1 | **Microsoft technology only**; open source under **MIT**. | the brief |
| C2 | **Completely AI-driven**: agents do the work; people decide. Not a chatbot, not a rulebook with a model on top. | the brief, the north star |
| C3 | **Human in the loop** at the five places the north star names; purchases are *prepared by the AI, approved by two named humans, executed by the AI*. | [north star §14](../01-north-star.md#14-where-humans-stay-in-charge), AGENTS rule 10 |
| C4 | Built on **Microsoft Foundry** and, where it earns its place, the **Microsoft Agent Framework**; the latest generally available features are used, preview features only behind a switch with a generally available fallback. | the design brief |
| C5 | Every AI part is deployed through the **Citadel framework** in the operator's **Azure landing zone**: model, tool and agent traffic through the governance hub, contracts as code. | the design brief |
| C6 | Security, compliance, testing, governance, safeguards and drift controls are designed in from the first day, to the limit of what the platform offers. | the design brief |
| C7 | **Cost-efficient by construction**: scale to zero by default, no standing analytics cluster, models matched to the task, every component with a line in the cost model. | the design brief |
| C8 | Aligned with the **Cloud Adoption Framework**, the **Well-Architected Framework** (including its AI-workload guidance) and the **FinOps Framework**. | the brief |
| C9 | **EU operator**: assume EU data residency; no data leaves the EU data boundary without a recorded decision. | the operator's location |
| C10 | **No Databricks, no Fabric.** | the design brief |
| C11 | The operator's two original findings stay *exam questions*, never the foundation of the design. | AGENTS rule 6 |

## 2. Assumptions

Stated rather than asked; each is revisited when a document depends on it.

| # | Assumption | Consequence if it is wrong |
|---|---|---|
| A1 | The operator's landing zone follows the Azure landing zone pattern (management groups, a connectivity hub, central identity and policy). | [Design 04](04-landing-zone-and-citadel.md#2-the-landing-zone-what-we-need-one-by-one) shows the landing-zone dependencies one by one, so a gap is visible. |
| A2 | The **Citadel Governance Hub** is, or will be, a shared platform capability of that landing zone. Our solution **onboards to it** with contracts it ships. If no hub exists, design 04 describes a minimal one as a separate, optional deliverable. | The contracts stay valid; only the hub's owner changes. |
| A3 | **One Entra tenant, one deployment per organisation** (self-hosted). No multi-tenant software-as-a-service in phase 1; one deployment can serve many subscriptions and management groups of the same tenant. | Multi-tenancy would be a new design, not a patch. |
| A4 | The estates under management are readable from the same tenant with Azure RBAC (reader at management-group scope; cost data through exports and the billing account's own roles). | Cross-tenant delegation is a later extension. |
| A5 | No licence is assumed beyond Azure subscriptions, with one named exception: **Entra ID P1** for the approval page's multifactor step-up (Conditional Access). Where any other control needs a Microsoft 365, Purview or Defender licence, the design says so and names the Azure-only fallback. | Without P1 the web page is not used for irreversible Moves, purchases or credential grants (only the lowest reversible class remains, by card); every other control is marked *optional* in design 07. |
| A6 | Three **scale scenarios** drive the sizing and the cost model: **Pilot** (one organisation, 5 subscriptions, about 500 resources, 5 people receiving decisions), **Team** (50 subscriptions, about 10,000 resources, 100 owners), **Enterprise** (1,000 subscriptions, about 200,000 resources, 2,000 owners). | Numbers move; the architecture does not. |
| A7 | The platform is run by a **minimum crew of three**: the operator, a second reviewer/approver and a security reviewer ([11 §7.2](11-delivery-and-operations.md#72-support-model)). Until the second reviewer exists it runs in **single-operator mode**. | Single-operator mode limits promotion to shadow and reversible Moves; a second reviewer is required before anything else is released. |
| A8 | **Named labour.** Any all-in cost counts the crew's labour as an **operator-declared** number of hours a month at a **declared** rate; [design 12](12-cost-and-finops.md) carries the seed and a sensitivity. | A figure labelled all-in without its hours and rate is a defect; the cloud-only measure stays valid whatever is declared. |

## 3. What the system must do

Each capability traces to the north star. The last column is the home of the *design* answer.

### STUDY — learn how Azure bills

| ID | Capability | North star |
|---|---|---|
| FR-S1 | **Change radar**: notice new or changed services, SKUs, prices and retirements as they are published. | [02 §7](../02-learning-azure.md#7-staying-current--the-change-radar) |
| FR-S2 | **Claims with receipts and scope**: extract checkable statements from documents, specifications and price lists. | [02 §4](../02-learning-azure.md#4-from-reading-to-knowing-claims-receipts-life-cycle) |
| FR-S3 | **Decode meters** with the Cost Grammar; propose a new mechanism when none fits. | [02 §2](../02-learning-azure.md#2-the-cost-grammar--how-it-reasons-about-services-it-has-never-seen) |
| FR-S4 | **Billing experiments in the Lab**: build, probe, break and tear down real resources to see how the bill forms. | [04 §4](../04-experiments-and-the-lab.md#4-the-billing-bench--how-does-this-thing-really-bill) |
| FR-S5 | **Atlas** publication, versioning and **knowledge CI** (every claim re-checks itself). | [02 §5](../02-learning-azure.md#5-knowledge-ci--facts-that-test-themselves) |
| FR-S6 | **Commons** contributions: scoped claims, recipes and counts — never estate data. | [07 §7](../07-getting-smarter.md#7-the-commons) |

### SURVEY — understand an estate and its people

| ID | Capability | North star |
|---|---|---|
| FR-V1 | **Estate inventory and change feed** across subscriptions. | [03 §1](../03-estate-and-investigation.md#1-the-estate-model--a-story-not-an-inventory) |
| FR-V2 | **Cost and usage ingestion**: exports, price sheets, reservations and commitments, with the agreement's own price levels. | [02 §9](../02-learning-azure.md#9-learning-the-commercial-reality) |
| FR-V3 | **Human graph**: owners, delegates and **contact preferences** (language, time zone, preferred channel, working hours — as the directory or the person declares them). Nothing is inferred about how a named person works. | [03 §4](../03-estate-and-investigation.md#4-the-human-graph--following-the-directory) |
| FR-V4 | **Intent, rhythm and calendar** of workloads and teams: why a resource exists and when it is busy, quiet or frozen, from usage, release plans and the business calendar. The subject of an inference is a workload or a role, never a named person. | [03 §2–3](../03-estate-and-investigation.md#2-understanding-intent) |
| FR-V5 | **Estate Model and Lesson Book**: scoped, dated, expiring, editable. | [03 §10](../03-estate-and-investigation.md#10-the-lesson-book--memory-you-can-read) |
| FR-V6 | **Unexplained Spend Ledger and Agenda**: what the system is wondering about, ranked by what an answer is worth. | [03 §5–6](../03-estate-and-investigation.md#5-the-bill-as-a-tree--and-the-ledger-of-what-is-unexplained) |
| FR-V7 | **Fast signals** (the Watch clock): an event that cannot wait for the hourly refresh — a metric or activity-log change, a deployment that moved a meter, a budget alert — is analysed within bounds and reaches an owner within minutes; the bill itself still lags by hours to days. The workflow is [W3b](05-agents-and-orchestration.md#3-the-workflows). | [01 §2](../01-north-star.md#four-clocks) |

### TEST — investigate and experiment

| ID | Capability | North star |
|---|---|---|
| FR-T1 | **Investigation**: hypotheses, a Skeptic that tries to break each case, a case notebook. | [03 §7–8](../03-estate-and-investigation.md#7-the-investigation-toolkit) |
| FR-T2 | **Consequence Engine**: what happens to cost, reliability, performance and security if we do X — as ranges. | [03 §11](../03-estate-and-investigation.md#11-the-consequence-engine--what-happens-to-the-bill-if) |
| FR-T3 | **Time Machine** and **wind tunnel**: replay and re-price history; map cost against performance. | [04 §6–7](../04-experiments-and-the-lab.md#6-the-wind-tunnel--the-cost-and-performance-frontier) |
| FR-T4 | **Guarded real-world trials**, with owner consent, a guard metric and a rollback. | [04 §8](../04-experiments-and-the-lab.md#8-experiments-in-the-real-world--carefully) |
| FR-T5 | **Terrarium, Exam and Forger**: synthetic estates with planted waste and decoys; independent scoring against baselines. | [07 §3](../07-getting-smarter.md#3-the-exam) |

### ACT — work with people and change things

| ID | Capability | North star |
|---|---|---|
| FR-A1 | **Brief**: a decision in a minute, with Explain, Challenge and Teach on every message. | [05 §1](../05-recommend-act-verify.md#1-the-brief--a-decision-not-a-recommendation) |
| FR-A2 | **Channels**: Teams cards and email first; attention budgets; escalation that widens privately. | [06](../06-people-and-conversation.md) |
| FR-A3 | **Voice, text and an AI participant in meetings** — optional modules. | [06 §10](../06-people-and-conversation.md#10-the-ai-in-the-room--meetings-voice-and-avatars) |
| FR-A4 | **Moves**: a catalogue of tested, versioned change recipes, authored by people and by the AI. | [05 §4](../05-recommend-act-verify.md#4-moves--tested-reusable-ways-to-change-things) |
| FR-A5 | **Execution with approvals** and **autonomy credentials** per domain. | [05 §6](../05-recommend-act-verify.md#6-autonomy-is-earned) |
| FR-A6 | **Commitment Desk**: prepare, two named approvals, execute. | [05 §7](../05-recommend-act-verify.md#7-the-commitment-desk) |
| FR-A7 | **Verification** against a counterfactual; drift guards; fixing at the source with pull requests. | [05 §5, §8](../05-recommend-act-verify.md#8-verification--did-it-work) |
| FR-A8 | **Decision rooms** when more than one person owns the answer. | [05 §1b](../05-recommend-act-verify.md#1b-when-more-than-one-person-owns-the-answer) |

### GROW — get smarter, visibly

| ID | Capability | North star |
|---|---|---|
| FR-G1 | **Prediction ledger**, calibration and the report card. | [07 §1, §4](../07-getting-smarter.md#1-everything-is-a-prediction) |
| FR-G2 | **Exams**, including the credential exam that gates autonomy. | [07 §3](../07-getting-smarter.md#3-the-exam) |
| FR-G3 | **Learning budget** and Lab return on investment. | [04 §12](../04-experiments-and-the-lab.md#12-the-curiosity-budget--and-a-lab-that-pays-its-way) |
| FR-G4 | **Method learning**: the system studies *how it investigates* — which sources, tactics, questions, experiments and models paid off, for which kind of case — through post-mortems on exam misses and method hypotheses tested on paper and Lab estates. A change is *proposed* as a pull request to its prompts, tools or rubrics with exam evidence against the retrieval-only and expert-seed baselines; the system never edits itself, and a protected, budgeted share of effort keeps exploring. The workflow is [W10](05-agents-and-orchestration.md#3-the-workflows). | [07 §6](../07-getting-smarter.md#6-learning-how-to-learn) |
| FR-G5 | **Dreaming**: nightly consolidation of the day into lessons, Detectors and Atlas changes. | [04 §13](../04-experiments-and-the-lab.md#13-dreaming--consolidation-while-the-world-is-quiet) |

### Cross-cutting

| ID | Capability |
|---|---|
| FR-X1 | A complete, tamper-evident **audit trail**: every agent run, tool call, model call, approval and change. |
| FR-X2 | **Autonomy credentials**: granted by people, per domain, with a cap and an expiry, and withdrawn automatically on regret. |
| FR-X3 | A **kill switch and rollback** at every level: one agent, one contract, one Move, the whole execution plane. |
| FR-X4 | **FinOps for itself**: the system's own spend, tokens and experiments are the first entries on its own Agenda. |
| FR-X5 | **Isolation** of one organisation's estate knowledge from every other, and of the Commons from all of it. |

## 4. Quality targets

These are **design targets** to be validated in the first experiment ([north star §16](../01-north-star.md#16-how-we-will-know-it-is-learning)), not service-level agreements.

| ID | Target |
|---|---|
| Q-SEC-1 | **No standing write permission** for any agent identity in any estate. Writes happen only in the execution plane, with a short-lived, scoped identity, after a recorded approval: the Policy service signs a **permit**, a person approves (on the web page, with an Entra-signed token whose nonce binds the target and the decision to approve, for every irreversible Move, every purchase and every credential grant; on a Teams card only for a reversible Move of the lowest class), the Approval service signs the record and only **enqueues** it, and the credential broker and the event-driven Move runner each **verify everything for themselves** before they grant or act. The residual is stated, not hidden. *No single credential completes a change that needs a person's web-page approval.* A compromised Approval service cannot start a job, fabricate a permit or fabricate a person's Entra-signed token. On the card path (reversible Moves of the lowest class only) the proof is the bot channel's assertion, which a compromised Approval service can fabricate; that is why the path ends at that class. A compromised Approval and Policy service can approve within an autonomy credential's constraints, which the broker and the runner check against the credential itself. A compromised broker can grant constrained Move roles without a lease; a compromised release pipeline can run code as a runner identity while it holds a role. Each is bounded and detected as stated in [07 §3.3](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim); the approval rules are in [§4](07-security-architecture.md#4-approvals-that-cannot-be-forged-or-reused). |
| Q-SEC-2 | **Every model, tool and agent call passes the gateway**; direct calls are blocked by the network and by policy, and the block is tested. |
| Q-SEC-3 | **No secrets in code, prompts, traces or contracts**; keys exist only where an identity cannot be used, and then in Key Vault with rotation. |
| Q-SAF-1 | **Every irreversible action has a recorded human approval or a rule a human wrote.** Purchases have two named approvers with different hats. |
| Q-SAF-2 | **External text is data, never instructions** — by whichever tool it arrives. Every tool service that returns free text (tags, names, invoice lines, replies, documents) sanitises it at the source, and once untrusted text has entered a session, privileged tools need a human's confirmation. An injection test suite runs in every release and in production sampling; a regression blocks the release. |
| Q-PRV-1 | Estate data stays in the tenant and the EU boundary; personal data is pseudonymised in the tool services before any text reaches the hub; the Commons receives only claims and recipes, and counts only above a minimum cohort — none in single-tenant mode, where a cohort of one re-identifies. |
| Q-REL-1 | If the gateway or the execution plane is down, the system **degrades to ask-only**; an approval that has expired or whose target has changed is never executed; if the audit ledger cannot be written, no approval is dispatched and no grant is made (**fail closed**): signed approvals are kept and dispatched when their entry commits, and the one exemption is a rollback to the pre-state named in the signed record, which runs from a signed outbox and is reconciled afterwards. |
| Q-REL-2 | Approvals, audit trail and the Lesson Book are recoverable to within an hour; the platform is recoverable to a working state within a working day; a restore never resurrects erased data and never revives an approval older than the restore point. |
| Q-PERF-1 | A **provisional mechanism profile** within hours of a service announcement (an aspiration, scored by the new-service race); first decisions for a new estate within a day of its cost data arriving; a fast-signal alert reaches an owner within minutes through the event-driven fast path (W3b), whose latency and throttling headroom are load-tested (spike S-FAST-1) before the target is promised. |
| Q-COST-1 | The platform's own cloud bill is bounded per scale scenario ([design 12](12-cost-and-finops.md)), and its cost is measured two ways from week one — never as one unlabelled figure. **Cloud break-even:** after the first quarter the cloud bill is below the savings the system has *verified* (**cloud cost per verified euro saved**). **All-in:** the cloud bill plus named labour — an operator-declared number of hours a month at a declared rate (assumption A8) — as the **all-in cost per verified euro saved**, reported from week one and targeted from Team scale upward; at Pilot scale labour dominates, so the Pilot proves capability, not payback. The marginal token cost of a case is a different quantity from the all-in cost per case and is never quoted as it. |
| Q-OPS-1 | Every agent run is traced end to end with its cost; every release is evaluated; any agent or contract can be paused in one action. |
| Q-EVO-1 | Models are replaceable **behind the gateway** without code changes; contracts, prompts, Moves and Atlas releases are versioned and pinned. |
| Q-COMP-1 | The design maps to the EU AI Act, GDPR, NIS2, ISO/IEC 42001 and the NIST AI RMF ([design 08](08-governance-and-compliance.md)). |
| Q-OPEN-1 | Everything the project authors — code, contracts, claims, Moves — can be published under MIT **without a byte of any customer's data.** |

## 5. Design principles

When two options are both reasonable, these decide.

| # | Principle | In practice |
|---|---|---|
| P1 | **AI does the knowledge work; code does the guarding.** | Agents plan, investigate, write and argue. Deterministic code is reserved for what must not be improvised: identity, approvals, policy, arithmetic over price lists, the gateway. |
| P2 | **Two planes.** | The reasoning plane can read and think; the execution plane can change things only for one approved Move at a time. |
| P3 | **Everything through the gateway.** | One place to meter, limit, filter, log and switch off models, tools and agents. |
| P4 | **An identity per agent and a person behind every agent.** | Each agent has its own identity, a named human sponsor and the narrowest role that works: fourteen roles, **fifteen** hosted-agent identities (the Librarian is deployed twice) and **eleven** trust groups, each group one contract per data class (**twelve** contracts: `examine` has a public and an EU one) and per environment where it has planned work ([04 §4.3](04-landing-zone-and-citadel.md#43-the-access-contracts)). |
| P5 | **A prompt is not a security boundary.** | Authorisation lives in identity, role assignments, tool contracts and runtime policy — never in the instructions to a model. |
| P6 | **External text is data.** | Documents, web pages, tickets, tags, names, replies and tool output are untrusted input, however authoritative they look; each tool service sanitises its own text at the source. |
| P7 | **Evidence gates releases.** | A change to a model, prompt, Move, contract or Atlas release ships only when the exam and the security suite say it did not get worse. |
| P8 | **Pin it, version it, diff it.** | Models, prompts, Moves, contracts, Atlas releases, infrastructure: all versioned, all pinned, all comparable. |
| P9 | **Drift is a first-class risk.** | Each layer has a preventive control, a detective control and a corrective one ([design 09](09-safeguards-and-drift-controls.md)). |
| P10 | **Scale to zero; pay for thinking, not for waiting.** | Serverless and jobs by default; always-on only with a written reason; cheap models for volume, expensive ones for judgement; batch for what can wait. |
| P11 | **Reversible by default.** | Prefer the change that can be undone; make the irreversible one rare, visible and doubly approved. |
| P12 | **Open by default, private by default.** | What is true about Azure is open and re-checkable; what is true about an estate never leaves it. |
| P13 | **Observe everything the system does, including to itself.** | Traces, costs and outcomes are data the agents themselves can reason about. |
| P14 | **Use the platform's newest *generally available* feature before building our own — and keep a way out.** | A preview feature is adopted behind a switch with a named fallback; a lock-in is named and costed ([design 13](13-decisions.md)). |

## 6. Where each requirement is answered

The matrix is the contract between this document and the rest of the design: each requirement names where it is *answered* and where it is *tested*. A requirement with no entry in the second column would be a defect in the design.

### Functional requirements

| Requirement | Answered in | Tested in |
|---|---|---|
| **FR-S1** change radar | [05 §3](05-agents-and-orchestration.md#3-the-workflows) W1; [09](09-safeguards-and-drift-controls.md) DR-9 | [10](10-test-and-evaluation.md) L4 new-service races |
| **FR-S2** claims with receipts and scope | [06 §2–3](06-data-and-knowledge.md#2-the-information-model) | G5 honesty (entailment, receipt hash and freshness, numeric provenance) |
| **FR-S3** decode meters | [05 §2](05-agents-and-orchestration.md#2-the-roster) (Cartographer, price engine) | L3, L4 |
| **FR-S4** billing experiments in the Lab | [07 §8](07-security-architecture.md#8-the-lab-as-a-security-boundary) (the Lab controller deploys signed recipes under a cost cap); [05 §3](05-agents-and-orchestration.md#3-the-workflows) W6; [11](11-delivery-and-operations.md) | L4 T2 estates |
| **FR-S5** Atlas and knowledge CI | [06 §3](06-data-and-knowledge.md#3-the-knowledge-pipeline); [06 §7.5](06-data-and-knowledge.md#75-atlas-retrieval-and-vectors) | knowledge CI |
| **FR-S6** the Commons | [06 §5](06-data-and-knowledge.md#5-estate-knowledge-privacy-by-design); [08 §9](08-governance-and-compliance.md#9-open-source-governance) | the estate-content scan |
| **FR-V1** inventory and change feed | [05 §3](05-agents-and-orchestration.md#3-the-workflows) W3; [04 §4.4](04-landing-zone-and-citadel.md#44-the-publish-contract-tools-and-who-may-call-them) | L2; L5 sanitiser attacks on tags and names |
| **FR-V2** cost and usage ingestion | [06 §4, §7.4](06-data-and-knowledge.md#4-cost-and-usage-data) | S-DATA-1; L2 |
| **FR-V3, FR-V4** contact preferences; intent and rhythm of workloads | [06 §5](06-data-and-knowledge.md#5-estate-knowledge-privacy-by-design); [08 §4](08-governance-and-compliance.md#4-privacy-and-gdpr); [09 §2.3](09-safeguards-and-drift-controls.md#23-drift-in-behaviour-and-in-people) (role-level and aggregate signals only) | L2 contract tests (the estate service returns contact preferences only); L4 |
| **FR-V5** Estate Model and Lesson Book | [06 §2](06-data-and-knowledge.md#2-the-information-model) (a lesson is a draft until an owner confirms it); [06 §7.2](06-data-and-knowledge.md#72-the-operational-store-container-by-container) | L4 |
| **FR-V6** Unexplained Spend Ledger and Agenda | [05 §2](05-agents-and-orchestration.md#2-the-roster) (Conductor) | L4 |
| **FR-V7** fast signals | [05 §3](05-agents-and-orchestration.md#3-the-workflows) W3b (event, queue, bounded analysis, owner) | S-FAST-1; L7 latency |
| **FR-T1, FR-T2, FR-T3** investigation, consequences, time machine | [05 §2–3](05-agents-and-orchestration.md#2-the-roster) W4; [06 §2](06-data-and-knowledge.md#2-the-information-model) (the evidence graph) | L3, L4 |
| **FR-T4** guarded trials | [09 §4](09-safeguards-and-drift-controls.md#4-the-safeguards-between-a-mistake-and-an-irreversible-action) | L6, shadow |
| **FR-T5** Terrarium, Exam, Forger | [10 §3](10-test-and-evaluation.md#3-the-terrarium-as-the-test-harness), §9 | the exam itself; the Forger-independence test |
| **FR-A1** the Brief | [05 §8](05-agents-and-orchestration.md#8-people-in-the-spine) | phase-2 design documents |
| **FR-A2, FR-A3** channels, voice | [ADR-17](13-decisions.md#adr-17-teams-through-our-own-adapter-e-mail-through-graph-voice-off); [07 §7](07-security-architecture.md#7-network-and-the-short-list-of-exceptions) (exceptions X1 and X5) | S-CHAN-1 |
| **FR-A4** Moves | [03 §5](03-logical-architecture.md#5-who-owns-which-data); [11 §1](11-delivery-and-operations.md#1-the-repository); [11 §3](11-delivery-and-operations.md#3-pipelines) (agents open pull requests to data paths only) | L2 dry run and rollback |
| **FR-A5, FR-X2** execution with approvals; credentials | [07 §3.3, §4](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim) (the authority chain: permit, approval, broker, runner, Verifier) | L1 properties (the runner rejects an approval whose hash or live state differs; the broker rejects unsigned, expired or replayed approvals and any whose permit or person's token fails its own check, a decline token and a repeated or same-person proof; a forged marker is ignored; a lease is never held twice; the runner starts only from its queue); S-ID-1, S-ID-3; G9 |
| **FR-A6** Commitment Desk | [03 §4](03-logical-architecture.md#a-commitment-purchase); [07 §4](07-security-architecture.md#4-approvals-that-cannot-be-forged-or-reused) | phase 5, after S-ACT-1 (purchases stay disabled until then) |
| **FR-A7** verification and drift guards | [09 §4](09-safeguards-and-drift-controls.md#4-the-safeguards-between-a-mistake-and-an-irreversible-action) | L4, L8 |
| **FR-A8** decision rooms | [05 §8](05-agents-and-orchestration.md#8-people-in-the-spine) | phase-2 design documents |
| **FR-G1, FR-G2** ledger, calibration, exams | [06 §7.2](06-data-and-knowledge.md#72-the-operational-store-container-by-container); [10](10-test-and-evaluation.md) | G4, G5, G9 |
| **FR-G3** learning budget | [12 §6](12-cost-and-finops.md#6-how-the-systems-own-spend-is-governed) | G6 |
| **FR-G4** method learning | [05 §3](05-agents-and-orchestration.md#3-the-workflows) W10; [05 §11](05-agents-and-orchestration.md#11-the-life-of-an-agent-version) (shipping a change) | held-out exam gains against the retrieval-only and expert-seed baselines; G2–G6 on any change |
| **FR-G5** dreaming | [05 §3](05-agents-and-orchestration.md#3-the-workflows) W7 | L7 |
| **FR-X1** audit trail | [06 §7.3](06-data-and-knowledge.md#73-the-audit-ledger) (one Audit Writer; signed entries); [ADR-32](13-decisions.md#adr-32-the-audit-ledger-is-hash-chained-append-blobs-in-immutable-storage) | chain verification job; the Audit Writer-down drill (L6) |
| **FR-X3** kill switches and rollback | [07 §10.3](07-security-architecture.md#103-kill-switches) (with their real latencies) | L6 drills, G7 |
| **FR-X4** FinOps for itself | [12](12-cost-and-finops.md) | G6; `cost-model.py --check` |
| **FR-X5** isolation | [07 §2](07-security-architecture.md#2-trust-zones-physically); [06 §5](06-data-and-knowledge.md#5-estate-knowledge-privacy-by-design) | L5 |

### Quality targets and constraints

| Target | Answered in | Tested in |
|---|---|---|
| **Q-SEC-1** no standing write | [07 §3](07-security-architecture.md#3-identity); [07 §3.3](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim) (the authority chain) | D2; L1; G2 |
| **Q-SEC-2** everything through the gateway | [04 §8](04-landing-zone-and-citadel.md#8-the-gateway-bypass-register) (the bypass register, B1–B12) | the daily canary; G2 |
| **Q-SEC-3** no secrets | [07 §6](07-security-architecture.md#6-secrets-keys-and-data-protection); [04 §3.4](04-landing-zone-and-citadel.md#34-hardening-the-defaults) (no key-bearing deployment outputs) | L0 scanning; the deployment-output assertion |
| **Q-SAF-1** approvals | [07 §4](07-security-architecture.md#4-approvals-that-cannot-be-forged-or-reused) | L1, L6 |
| **Q-SAF-2** external text is data | [07 §5](07-security-architecture.md#5-defence-against-prompt-injection-in-nine-layers) (the source sanitiser, the typed-field policy, session taint) | L5 (sanitiser attacks, taint, the moderation setting present), G2 |
| **Q-PRV-1** residency, pseudonymisation and the Commons | [07 §6.2](07-security-architecture.md#62-data-classes-and-what-each-may-touch); [08 §4](08-governance-and-compliance.md#4-privacy-and-gdpr); [06 §5](06-data-and-knowledge.md#5-estate-knowledge-privacy-by-design) | contract tests |
| **Q-REL-1** degrade to ask-only | [03 §6](03-logical-architecture.md#6-degraded-modes); [11 §7.2](11-delivery-and-operations.md#72-support-model) | L6 (including Audit Writer down and signing key unavailable), G7 |
| **Q-REL-2** recovery targets | [06 §7.6](06-data-and-knowledge.md#76-recovery); [11 §8](11-delivery-and-operations.md#8-resilience-and-recovery) | monthly restore drill (erased data stays erased; stale approvals are refused) |
| **Q-PERF-1** speed to a provisional profile; fast signals | [05 §3](05-agents-and-orchestration.md#3-the-workflows) W1–W2, W3b | phase 1 exit; S-FAST-1 |
| **Q-COST-1** bounded run cost; two stated measures | [12](12-cost-and-finops.md) (the cloud bill, the labour sensitivity, the unit economics) | G6; S-COST-1; the weekly cost report prints both measures with their labour hours and rate |
| **Q-OPS-1** traced, evaluated, pausable | [11 §7](11-delivery-and-operations.md#7-operating-the-platform); [07 §10.3](07-security-architecture.md#103-kill-switches) | L8 |
| **Q-EVO-1** models replaceable behind the gateway | [05 §6](05-agents-and-orchestration.md#6-models-and-the-alias-map); [09 DR-8](09-safeguards-and-drift-controls.md#22-drift-under-us) | the fingerprint probe |
| **Q-COMP-1** regulatory mapping | [08](08-governance-and-compliance.md) | G8 |
| **Q-OPEN-1** MIT without customer data | [08 §9](08-governance-and-compliance.md#9-open-source-governance) | the estate-content scan |
| **C1–C11** constraints | [02](02-technology-landscape.md) and the decisions in [13](13-decisions.md) | the review rounds |
