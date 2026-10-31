# Design 14 — Next phases

> **What this answers:** *What do we prove first, in what order, and which assumptions are checked by building the smallest thing that can show them wrong?* The design of phase 1 ends with this plan; the build begins with its first spikes. Part of the [design](README.md). Decisions the plan tests are in [13](13-decisions.md); costs in [12](12-cost-and-finops.md).

---

## 1. Principle: evidence before breadth

The riskiest parts of this design are not the agents. They are the **platform seams**: whether an agent identity passes the hub's checks, whether the broker's delegated role assignment works as described, whether a private Foundry spoke really fills its own stores, whether a Teams card can carry a bound approval. Each is a small experiment. **Every phase starts with the spikes that could invalidate its decisions and ends with evidence against a named exit criterion** — evidence the pipeline produces, not a status report.

## 2. Assumptions to confirm in the first week

The design proceeds on stated assumptions ([01 §2](01-requirements-and-principles.md#2-assumptions)). The first week replaces each with a fact or a recorded change.

| # | Assumption | How it is confirmed | If it differs |
|---|---|---|---|
| 1 | A landing zone exists with a connectivity hub, firewall and central DNS | read-only inventory of the platform subscriptions | deploy spoke-local DNS and firewall ([04 §2](04-landing-zone-and-citadel.md#2-the-landing-zone-what-we-need-one-by-one)) |
| 2 | A Citadel hub exists, or the operator wants the minimal hub | ask the platform owner; inspect `GET /version` if it exists | the optional hub deliverable ([04 §10](04-landing-zone-and-citadel.md#10-minimal-hub-if-the-landing-zone-has-none)) |
| 3 | The hub's region is reachable from Sweden Central | latency and peering test | cross-region peering, costed |
| 4 | The agreement type is known (EA, MCA, CSP) | billing account properties | spike S-ACT-1 selects the purchase and vending mechanism |
| 5 | Entra P2 or ID Governance is licensed (for PIM); Agent 365 is not assumed | tenant licence check | optional modules stay off ([07 §11](07-security-architecture.md#11-optional-modules-and-their-fallbacks)) |
| 6 | Teams allows custom apps for the pilot users; a shared mailbox can be created | admin centre check | channel fallback: e-mail first |
| 7 | Foundry quota in Sweden Central reaches the GPT-6 family | quota page; **request on day zero** — lead time is the risk | models fall back to the GPT-5.6 family until quota arrives |

## 3. Spike register

A spike has a question, a method, an exit criterion and a fallback. Timeboxes are in working days and are *limits*, not estimates.

| ID | Question | Tests | Method | Exit criterion | Fallback | Box |
|---|---|---|---|---|---|---|
| **S-ID-1** | Can the broker hold *Role Based Access Control Administrator* with a condition that restricts roles and principals? Does PIM allow time-bound *active* assignments for a managed identity? | [ADR-07](13-decisions.md#adr-07-execution-identities-are-granted-just-in-time-by-a-broker) | build the broker against a Lab subscription; attempt to assign Owner and to assign to another principal (both must fail) | only the approved roles to the approved identities succeed | standing roles with approval gating — rejected; escalate | 3 |
| **S-ID-2** | Does an Entra agent identity's token pass the hub's `azp` and `requiredRoles` checks, so attribution is per agent? Is JWT-only available? | [ADR-06](13-decisions.md#adr-06-an-entra-agent-identity-per-agent-and-nine-contract-groups) | one hosted agent, one contract, direct role assignment | the hub logs the agent's own `azp` and denies without the role | header attribution | 2 |
| **S-ACT-1** | Which role and scope purchase a reservation or savings plan under each agreement type, and which creates subscriptions? | ADR-07, [ADR-16](13-decisions.md#adr-16-the-lab-is-vended-subscriptions-stacks-and-a-reaper) | read the billing roles; a price-only call (no purchase) from the broker identity | a purchase dry run and a vending run succeed | human-executed purchase until solved | 3 |
| **S-GW-1** | Do Data Zone SKUs flow through the hub's routing and aliasing? | [ADR-09](13-decisions.md#adr-09-models-are-aliases-and-the-data-class-chooses-the-deployment-type) | register an EU Data Zone backend, route an alias, read `x-` metadata | the request reaches the EU deployment and is metered | regional deployment | 2 |
| **S-GW-2** | How does A2A authenticate on the hub? | ADR-01 | only when the first A2A asset is proposed | documented behaviour | none needed in phase 1 | — |
| **S-NET-1** | Do toolbox calls pass the hub? Does a Foundry gateway accept a hub in another subscription? | [ADR-15](13-decisions.md#adr-15-tools-are-mcp-servers-published-through-the-hub) | a toolbox pointing at a published tool; read hub logs | calls appear in the hub's logs | agents call the hub directly (the default) | 2 |
| **S-NET-2** | Can a hosted-agent-only project use VNet injection with platform-managed data instead of bring-your-own stores? Residency of that data? | ADR-03, ADR-05 | create a dev account both ways | dev runs for less, with documented residency | standard setup everywhere | 2 |
| **S-NET-3** | The two silent failures: do the bring-your-own stores fill; does private AI Search index with a private execution environment? | ADR-05 | acceptance tests from inside and outside the VNet | 200 inside, 403 outside, data in the stores | fix capability hosts | 2 |
| **S-SEC-1** | Can the Agent Governance Toolkit's policy format serve as the deterministic gate? | [ADR-19](13-decisions.md#adr-19-nine-layers-against-injection-with-a-deterministic-gate) | wrap the Detective's tools; run the attack suite | blocks planted attacks; no false blocks on the exam | in-house gate | 4 |
| **S-SEC-2** | Do Foundry guardrail settings apply to calls made through the hub? | ADR-19 | send a known violation through both paths | the same verdict, or a documented gap | hub screening as the control | 2 |
| **S-SEC-3** | Does hosted-agent egress *enforce* mode work when it reaches GA? | ADR-19 | audit mode in dev, compare with firewall logs | matches the firewall's view | firewall only | on GA |
| **S-ORCH-1** | Does our checkpoint store survive restart, duplicate delivery and a days-long wait? Does the Durable Extension do better? | [ADR-33](13-decisions.md#adr-33-the-spine-runs-as-container-apps-jobs-with-our-checkpoint-store) | one W4 on both; chaos drills | no lost or double step in 100 forced restarts | Durable Extension | 4 |
| **S-AGT-1** | Does the Framework Harness beat a plain loop for the Scholar and Detective on tokens and quality? | [ADR-01](13-decisions.md#adr-01-a-deterministic-spine-calls-agentic-leaves) | A/B on the exam | better quality at no more cost | plain loop | 3 |
| **S-MOD-1** | Which independent-family model is the best EU judge? | [ADR-10](13-decisions.md#adr-10-judges-are-a-different-model-family-and-claude-never-sees-estate-data) | judge-agreement against human labels on paper estates | agreement within a margin of the best | another family | 3 |
| **S-MOD-2** | Does the Decisions API beat structured output for triage on cost and calibration? | ADR-09 | A/B on triage cases | cheaper at equal calibration | structured output | 2 |
| **S-DATA-1** | FinOps hubs ingestion versus our own: maintained schema, or fewer dependencies? | [ADR-13](13-decisions.md#adr-13-cost-analytics-is-parquet-and-an-embedded-engine-in-a-job) | ingest one real export both ways | lower cost per $1M monitored at equal fidelity | our own ingestion | 3 |
| **S-DATA-2** | Do locked immutable containers allow appends to append blobs as the ledger needs? | [ADR-32](13-decisions.md#adr-32-the-audit-ledger-is-hash-chained-append-blobs-in-immutable-storage) | create, append, try to modify and delete | appends succeed; modification and deletion fail | daily sealed files instead of appends | 1 |
| **S-DATA-3** | Can the AI Search service of the standard setup host the Atlas index too? | [ADR-11](13-decisions.md#adr-11-the-atlas-is-git-with-a-derived-search-index) | second index, separate role | no cross-effect; separate RBAC | a second Basic service | 1 |
| **S-DATA-4** | Do Cosmos DB vector indexes work on serverless at our scale? | [ADR-12](13-decisions.md#adr-12-the-operational-store-is-cosmos-db-serverless) | load, query, measure request units | recall and cost acceptable | a second index on search | 2 |
| **S-DATA-5** | What backup modes does serverless offer? | ADR-12 | read the account's properties; restore drill | the hourly export alone meets the one-hour target | — | 1 |
| **S-CHAN-1** | Does a Teams card action with single sign-on reach the Approval service through the edge environment, with the target hash intact? | [ADR-08](13-decisions.md#adr-08-approvals-are-authenticated-actions-bound-to-one-target) | the adapter in .NET, one card | a bound, single-use approval recorded | web approval page only | 4 |
| **S-DEL-1** | Image signing with a Key Vault key and admission only of signed images | [ADR-23](13-decisions.md#adr-23-bicep-with-verified-modules-deployment-stacks-and-github-actions) | sign in CI; deploy an unsigned image | the unsigned image is refused | pipeline-only registry write | 2 |
| **S-COST-1** | What do tokens per case, cache hit rates and compute really cost? | [ADR-26](13-decisions.md#adr-26-the-hub-is-the-spending-cap-budgets-are-alarms) | 100 synthetic cases on the pinned stack | the cost model's inputs replaced by measurements | revise the model | 3 |

## 4. Phases

Sizes are relative effort (**S**, **M**, **L**), not calendar promises. Each phase *proves* a claim from the north star.

| Phase | Builds | Spikes first | Proves | Exit criteria (evidence) |
|---|---|---|---|---|
| **0 — Foundation and walking skeleton** (M) | subscriptions, network, the Foundry account (one-way doors), hub contracts in dev, one hosted agent calling a model and a tool through the hub, the canary, the drift controller v0, the audit ledger v0, the pipeline with gate G1, the evidence pack v0 | S-NET-2, S-NET-3, S-ID-2, S-GW-1, S-DATA-2, S-DEL-1 | *everything passes the gateway, and we can prove it* | the canary is blocked and alerts; a planted drift is found within its service level; a kill switch works; cost per call is measured |
| **1 — Study** (M) | Document reader, Scholar, Cartographer, Librarian (Atlas), knowledge CI, Atlas v0, W1 and W2, Exam v0 with a *new-service race* | S-MOD-1, S-ORCH-1 | *it learns a service it has never seen, with receipts* | a provisional profile within hours of a synthetic announcement; gates G2–G5 for the study group |
| **2 — Survey and investigate, in shadow** (L) | estate reader, cost ingestion, the Estate Model, Detective, Skeptic, Economist, Terrarium T1 with decoys, the prediction ledger | S-DATA-1, S-DATA-4, S-COST-1, S-AGT-1, S-MOD-2 | *it rediscovers planted waste, resists decoys and is calibrated* | beats the baselines on rediscovery and restraint; zero harmful recommendations on decoys; shadow on one real estate, read-only |
| **3 — Brief, approve, act** (L) | the Teams adapter and Brief service, Approval, Policy, broker, Move runner, three reversible Moves | S-CHAN-1, S-ID-1, S-SEC-1, S-SEC-2 | *a person decides in a minute and the change is safe and verified* | a first **verified** saving; zero safeguard failures in the drills; gate G7 green |
| **4 — The Lab and learning** (M) | Lab vending, Experimenter, W6 and W7, method learning by pull request | S-ACT-1 (vending) | *it tests its beliefs and gets better visibly* | an experiment changes a claim; the report card shows a measured improvement |
| **5 — Commitments and autonomy** (M) | the Commitment Desk (two hats), purchase mechanism, the credential exam | S-ACT-1 (purchase) | *autonomy is earned, never assumed* | a purchase prepared by the AI, approved by two named humans, executed by the AI, with a re-price at execution; a credential granted and withdrawn on regret in a drill |
| **6 — Harden and release** (M) | disaster-recovery drill, human red team, DPIA, documentation, the open-source release | — | *safe to share* | restore within the targets; no critical red-team finding; **the repository stays private until the operator decides** |

**What a phase never does:** widen the blast radius before the evidence exists. Phase 3 acts on one estate, three Moves, reversible only; phase 5 is the first time money moves.

## 5. Pre-flight checklist (day zero)

1. **Quota requests** for the GPT-6 family and the hosted-agent session limits in Sweden Central.
2. **Resource providers** registered in the new subscriptions (the research lists about 25 for the hub and the spoke).
3. **Entra**: the hub's app registration with the `Model.Invoke`, `MCP.Invoke`, `Agent.Invoke` roles; a person able to assign app roles.
4. **Networking**: address space (a `/24` per agent subnet, a `/26` for endpoints), peering both ways, firewall rules for the Entra hosts, `*.identity.azure.net`, Application Insights and the hub; private DNS zones linked.
5. **GitHub**: the repository's protected environments, workload identity federation, self-hosted runner job.
6. **Teams and mail**: custom app allowed for pilot users; shared mailbox; Exchange role-based access scoping for the application.
7. **Billing**: Cost Management export destination; reader access on the first estate.
8. **Policy**: the initiative in *audit* mode in the first week, then *deny* in production.
9. **Budgets** as alarms on every subscription; the cost report workflow.

## 6. After design phase 1: the next design documents

The north star promised that **personas, user flows, interfaces and systems** would be designed next. They are *design phase 2* and run in parallel with the first spikes, because they decide what the Brief service and the adapters must build:

| Document | Answers |
|---|---|
| **Personas and journeys** | who receives a Brief, who approves, who administers; the day in each life; the moment of trust and the moment of annoyance |
| **The Brief and card design system** | the anatomy of a decision card; *Explain*, *Challenge*, *Teach*; the plain-text e-mail equivalent; disclosure of AI in every channel |
| **Conversation design** | tone, language, escalation that widens privately, the attention budget |
| **Dashboards and the report card** | what the operator, FinOps and security see; the first-quarter measures |
| **Service contracts** | the typed schemas and APIs of every tool service and of the execution plane |
| **The Move catalogue v0** | the first reversible Moves with dry runs, guards and rollbacks |
| **The exam bank v0** | planted waste, decoys, new-service races, calibration cases |
| **Threat-model workshops** | the abuse cases of [07 §12](07-security-architecture.md#12-threats-controls-and-what-remains), per service |

## 7. Review triggers

The decisions in [13](13-decisions.md) carry review triggers; the calendar and the release feed raise them automatically:

- **1 December 2026** — Foundry visual workflows retire (not used; confirm no dependency).
- **Quarterly** — the governance review ([08 §11](08-governance-and-compliance.md#11-review-cadence)).
- **When the AI Gateway product meets the criteria** in [04 §9](04-landing-zone-and-citadel.md#9-the-ai-gateway-product-a-decision-gate).
- **When a preview dependency in [09 §5](09-safeguards-and-drift-controls.md#5-the-preview-register-and-the-dependency-register) reaches general availability** — remove its switch, or the fallback.
- **Any change of a regulatory position marked *to confirm*** in [08](08-governance-and-compliance.md).
