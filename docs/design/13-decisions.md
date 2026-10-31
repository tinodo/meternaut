# Design 13 — Decisions

> **What this is:** the architecture decision records (ADRs) of design phase 1. Each decision names the **strongest alternative** and why it lost, what the decision **costs and locks in**, and what would make us **revisit** it. Every ADR was put to two rubber-duck rounds with different model families ([review record](../reviews/README.md)); a decision whose status is **Proposed** has not yet been through both. Evidence is in the [research](research/) and the [feature register](research/feature-register.md); the requirements are in [01](01-requirements-and-principles.md). Part of the [design](README.md).

**How to read a record.** *Reversibility*: **easy** (a config or contract change), **moderate** (a redeploy or migration), **one-way** (cannot be changed without re-creating a resource). *Lock-in*: what we would have to replace to leave. *Preview*: whether the decision depends on a preview feature (and where its fallback is — [09 §5](09-safeguards-and-drift-controls.md#5-the-preview-register-and-the-dependency-register)).

## Summary

| ADR | Decision | Reversibility | Preview dependency |
|---|---|---|---|
| [01](#adr-01-a-deterministic-spine-calls-agentic-leaves) | A deterministic spine calls hosted-agent leaves; agents never call each other | moderate | no |
| [02](#adr-02-the-gateway-is-the-citadel-governance-hub-on-api-management) | The gateway is the Citadel Governance Hub on API Management | moderate | the publish contract |
| [03](#adr-03-two-spokes-a-lab-management-group-and-read-only-estates) | Two spokes, a Lab management group, read-only estates | moderate | no |
| [04](#adr-04-sweden-central-is-the-primary-region) | Sweden Central is the primary region | one-way (per account) | no |
| [05](#adr-05-bring-your-own-vnet-injection-not-the-managed-vnet) | Bring-your-own-VNet injection, not the managed VNet | one-way | no |
| [06](#adr-06-an-entra-agent-identity-per-agent-and-eleven-contract-groups) | An Entra agent identity per agent; eleven contract groups; authorisation per tool | moderate | partly |
| [07](#adr-07-execution-identities-are-granted-just-in-time-by-a-broker-on-a-signed-approval) | Execution identities granted just in time by a broker on a signed approval; three parties verify independently | moderate | no |
| [08](#adr-08-approvals-are-authenticated-actions-bound-to-one-target) | Approvals are authenticated actions bound to one target | moderate | no |
| [09](#adr-09-models-are-aliases-and-the-data-class-chooses-the-deployment-type) | Models are aliases; the data class chooses the deployment type | easy | Flex |
| [10](#adr-10-judges-are-a-different-model-family-and-claude-never-sees-estate-data) | Judges are a different family; Claude never sees estate data | easy | no |
| [11](#adr-11-the-atlas-is-git-with-a-derived-search-index) | The Atlas is Git with a derived search index | easy | no |
| [12](#adr-12-the-operational-store-is-cosmos-db-serverless) | The operational store is Cosmos DB serverless | moderate | no |
| [13](#adr-13-cost-analytics-is-parquet-and-an-embedded-engine-in-a-job) | Cost analytics is Parquet and an embedded engine in a job | easy | no — an exception to C1 |
| [14](#adr-14-no-platform-memory) | No platform memory | easy | n/a |
| [15](#adr-15-tools-are-mcp-servers-published-through-the-hub) | Tools are MCP servers published through the hub | easy | the publish contract |
| [16](#adr-16-the-lab-is-vended-subscriptions-stacks-and-a-reaper) | The Lab is vended subscriptions, stacks and a reaper | moderate | no |
| [17](#adr-17-teams-through-our-own-adapter-e-mail-through-graph-voice-off) | Teams through our own adapter, e-mail through Graph, voice off | easy | no |
| [18](#adr-18-observability-is-opentelemetry-into-azure-monitor-with-cheap-table-plans) | Observability is OpenTelemetry into Azure Monitor with cheap table plans | easy | the protected content table |
| [19](#adr-19-nine-layers-against-injection-with-a-deterministic-gate) | Nine layers against injection with a deterministic gate | easy | several, each with a fallback |
| [20](#adr-20-security-monitoring-feeds-the-landing-zone-licence-bound-controls-are-optional) | Security monitoring feeds the landing zone; licence-bound controls are optional | easy | no |
| [21](#adr-21-drift-is-controlled-by-deterministic-detectors-and-a-preview-register) | Drift is controlled by deterministic detectors and a preview register | easy | no |
| [22](#adr-22-evaluation-is-foundry-evaluations-our-own-exam-and-open-attack-suites) | Evaluation is Foundry evaluations, our own exam and open attack suites | easy | red-teaming agent |
| [23](#adr-23-bicep-with-verified-modules-deployment-stacks-and-github-actions) | Bicep with Verified Modules, Deployment Stacks and GitHub Actions | moderate | no |
| [24](#adr-24-keyless-by-default-platform-managed-keys) | Keyless by default; platform-managed keys | moderate | no |
| [25](#adr-25-estate-and-personal-data-stay-in-the-eu-data-zone) | Estate and personal data stay in the EU Data Zone | easy | no |
| [26](#adr-26-the-hub-is-the-spending-cap-budgets-are-alarms) | The hub is the spending cap; budgets are alarms | easy | no |
| [27](#adr-27-the-system-operates-itself-sre-agent-is-off-by-default) | The system operates itself; SRE Agent is off by default | easy | no |
| [28](#adr-28-packaging-is-a-monorepo-an-azd-template-and-bicep-modules) | Packaging is a monorepo, an azd template and Bicep modules | easy | no |
| [29](#adr-29-compliance-rests-on-the-security-benchmark-and-policy-as-code) | Compliance rests on the security benchmark and policy as code | easy | no |
| [30](#adr-30-recovery-is-redeploy-from-code-with-no-second-region-in-phase-1) | Recovery is redeploy from code; no second region in phase 1 | moderate | no |
| [31](#adr-31-every-release-is-a-signed-manifest-of-pins) | Every release is a signed manifest of pins | easy | no |
| [32](#adr-32-the-audit-ledger-is-hash-chained-append-blobs-in-immutable-storage) | The audit ledger is hash-chained append blobs in immutable storage | moderate | no |
| [33](#adr-33-the-spine-is-durable-functions-on-flex-consumption-calling-leaves-through-the-hub) | The spine is Durable Functions on Flex Consumption; our checkpoint design is the named fallback | moderate | no |
| [34](#adr-34-clocks-are-timer-triggers-and-queues-routines-are-optional-and-preview) | Clocks are timer triggers and queues; Routines are optional and preview | easy | no |
| [35](#adr-35-a-minimal-hub-is-a-separate-optional-deliverable) | A minimal hub is a separate, optional deliverable | easy | no |
| [36](#adr-36-c-for-the-spine-the-execution-plane-and-the-teams-adapter-python-for-agents) | C# for the spine, the execution plane and the Teams adapter; Python for agents | moderate | no |
| [37](#adr-37-model-written-code-runs-only-in-a-sandbox-with-no-identity) | Model-written code runs only in a sandbox with no identity | easy | no (Sandboxes are GA; EU regions and price unverified) |

---

## Decisions

### ADR-01 A deterministic spine calls agentic leaves
**Status** Proposed · **Reversibility** moderate · **Revisit when** a partner's agent must be called, or an A2A path through the hub is generally available and its authentication is unambiguous.
**Decision.** Workflows are deterministic and contain no model. They invoke **hosted agents** (fourteen roles, fifteen identities) one step at a time through the hub with an envelope of ids and budgets. Agents never call each other; they read and write typed records ([05 §1](05-agents-and-orchestration.md#1-the-pattern-a-deterministic-spine-with-agentic-leaves)). The spine may branch, fan out competing hypotheses and loop back to an earlier step; the evidence is an immutable, versioned record graph that keeps contrary evidence.
**Because.** It removes the *agent-to-agent* channel along which an injected instruction would travel (free text inside typed records is still a path, which is why the source sanitiser, the typed-field policy and the session taint rule exist), makes budgets and retries deterministic, and makes each leaf separately testable and replaceable.
**Strongest alternative.** Agents that hand off to each other (Agent Framework handoff, group chat, or A2A through the hub): more fluid collaboration and less schema work. Rejected because each hop is an injection path, A2A through the hub is preview with contradictory authentication notes, and cost control moves into prompts.
**Consequences.** Schema upkeep; less emergent behaviour; every leaf needs a typed output. No lock-in beyond the Agent Framework inside the leaves and Durable Functions for the spine ([ADR-33](#adr-33-the-spine-is-durable-functions-on-flex-consumption-calling-leaves-through-the-hub)).
**Round 1** (A-10, D-01): bounded branching and a record graph with contrary evidence added; the over-claim that nothing is left for an injection to travel along removed.

### ADR-02 The gateway is the Citadel Governance Hub on API Management
**Status** Proposed · **Reversibility** moderate · **Revisit when** the AI Gateway product meets the criteria in [04 §9](04-landing-zone-and-citadel.md#9-the-ai-gateway-product-a-decision-gate).
**Decision.** All model, tool and agent traffic passes the Citadel Governance Hub, forked and pinned to a commit, with contracts in our repository ([04](04-landing-zone-and-citadel.md)). The fork is hardened (`useTargetAzureKeyVault` set to true and no key-bearing deployment outputs; `x-policy-id` and API-version overrides stripped), and **each agent is authorised per tool** by its verified `azp`/`oid` and app roles assigned directly to its identity; the `x-sub-agent-id` header is attribution only.
**Because.** It is the framework the brief names, it is hub-and-spoke, and its contracts (backend, access, publish) are exactly the supply, demand and publishing surfaces we need; API Management's AI policies are generally available.
**Strongest alternative.** The new standalone AI Gateway product (calendar budgets, tool-level governance) — preview, two regions, no price, policies that do not match Citadel's contracts. A second alternative, Foundry's portal gateway, can create a second API Management next to the hub, may be able to associate an existing one (tested in S-NET-1), and routes only some tools.
**Consequences.** The hub is a **single-maintainer sample** with no releases; a fixed monthly floor of about €320 in its usage pipeline unless shared or trimmed; contracts as data keep exit cheap. Risk R4 in [08](08-governance-and-compliance.md#8-risk-register).
**Round 1** (B-03, E-05, E-06): per-tool authorisation by verified identity (spike S-GW-3), the hardening additions, and the portal-gateway claim softened.

### ADR-03 Two spokes, a Lab management group and read-only estates
**Status** Proposed · **Reversibility** moderate · **Revisit when** the non-production floor of a standard-setup Foundry account proves too costly ([12](12-cost-and-finops.md)).
**Decision.** `acia-prod` and `acia-nonprod` spokes; vended Lab subscriptions in their own management group; estates are other subscriptions onboarded in two consented parts — **read** onboarding, and a separate **action** onboarding that grants the broker a constrained delegation ([04 §3](04-landing-zone-and-citadel.md#3-topology), [ADR-07](#adr-07-execution-identities-are-granted-just-in-time-by-a-broker-on-a-signed-approval)).
**Because.** Environments need separate trust boundaries and separate quota; the Lab must have no route to anything real.
**Strongest alternative.** One subscription with resource groups per environment: cheaper, one quota pool, and a single noisy agent group can starve the others.
**Consequences.** Three or more subscriptions to vend; the Foundry standard setup repeats **per private account** (an AI Search service, a Cosmos DB account and a Storage account each, priced in [12](12-cost-and-finops.md)); accounts are created in the phase that needs them, and a cheaper shape for dev and production is spike **S-NET-2**.
**Round 1** (C-01, C-07, B-01): the floor is priced per account and creation is staged.

### ADR-04 Sweden Central is the primary region
**Status** Proposed · **Reversibility** one-way per Foundry account · **Revisit when** West Europe gains managed VNet, the full AI Landing Zone deployment and serverless search.
**Decision.** Sweden Central hosts the spokes; the hub is wherever the landing zone puts it ([04 §3.2](04-landing-zone-and-citadel.md#32-region)).
**Because.** It is the only EU region present in every capability list that matters (hosted agents, managed VNet, the AI Landing Zone, the hub's region list); serverless search is also offered in Denmark East and Poland Central, and Learn flags Sweden Central for new search services (see the consequences).
**Strongest alternative.** West Europe: the likely home of the operator's landing zone, about 30 % cheaper API Management, and hosted agents are listed there — but no hosted-agent meter appears in the price API, and managed VNet and the AI Landing Zone are absent.
**Consequences.** Cross-region peering if the connectivity hub differs; a different region for the Foundry account later means re-creating it. Learn flags Sweden Central as "in high demand, which prevents the creation of new search services", so the Search services are created on day zero, with another EU region as the fallback. Learn's pages disagree on whether the Search service may live in another region than the Foundry account (the networking page says only the Foundry resource and the VNet must share a region; the Agent Service FAQ says all resources must), so spike S-NET-3 decides; cross-region traffic is costed in [12](12-cost-and-finops.md).

### ADR-05 Bring-your-own-VNet injection, not the managed VNet
**Status** Proposed · **Reversibility** one-way · **Revisit when** managed VNet offers outbound logging, a bring-your-own firewall and West Europe.
**Decision.** Agents run in a delegated `/24` subnet of our spoke; egress passes the landing zone's firewall with an FQDN allow-list ([04 §6](04-landing-zone-and-citadel.md#6-network)).
**Because.** The managed VNet's FQDN rules create a managed Azure Firewall — Standard by default, Basic selectable and then fixed at deployment ([Learn, managed virtual network](https://learn.microsoft.com/azure/foundry/how-to/managed-virtual-network#pricing)) — which bills **€803 a month for the Standard deployment hour plus €0.014 a GB**, has no outbound logging and no custom firewall, and cannot be switched off.
**Strongest alternative.** Managed VNet: no address planning and fewer resources for us to own.
**Consequences.** We own the subnet; subnet exhaustion is silent (HTTP 429), so it is monitored; the choice is made at account creation and cannot be changed.

### ADR-06 An Entra agent identity per agent and eleven contract groups
**Status** Proposed · **Reversibility** moderate · **Revisit when** the hub accepts identity without a shared key.
**Decision.** Each hosted agent has its own Entra agent identity, a named sponsor and no standing roles; agents are gathered into **eleven groups** (study, curate, survey, investigate, experiment, converse, engineer, govern, examine, forge, conduct) — fourteen roles and fifteen identities, because the Librarian runs twice — with **one hub contract per group, data class and environment**: `engineer` and `govern` are EU-only and `examine` has a synthetic and a real-estate contract. Authorisation is **per tool**, by the verified `azp`/`oid` and app roles assigned directly to the agent identity ([05 §2](05-agents-and-orchestration.md#2-the-roster), [04 §4](04-landing-zone-and-citadel.md#43-the-access-contracts)).
**Because.** The groups are the capability classes of the lethal-trifecta matrix; the Scholar (the one reader of untrusted web text) and the Librarian (the Atlas writer) are apart; the Forger and the Conductor are separate so the adversary shares nothing with the examinee and the budget holder cannot spend another group's budget; and no contract mixes data classes.
**Strongest alternative.** One shared project identity per Foundry project (the legacy behaviour) or three coarse groups: fewer contracts, blurred blast radius.
**Consequences.** Per-agent attribution and per-tool authorisation depend on the token's `azp` and roles for agent identities (spikes S-ID-2 and S-GW-3); until then a header carries attribution only and authorisation falls back to the group. Conditional Access for agents is licence-bound and optional. Eleven groups across environments is many contracts: they are data, generated from one table.
**Round 1** (A-02, B-02, B-03): nine groups became eleven; `govern` no longer mixes data classes; the header is no longer an authorisation input.

### ADR-07 Execution identities are granted just in time by a broker on a signed approval
**Status** Proposed · **Reversibility** moderate · **Revisit when** PIM supports time-bound activation for workload identities with our licences.
**Decision.** Three parties, none able to complete a change alone. The **Approval service** authenticates the approver, signs the approval with a Key Vault key that only it can use (approver claims, a target hash that includes live-state etags and the policy decision id, an expiry and a nonce) and dispatches the Move runner job from a fixed template. The **credential broker** — small and deterministic, holding *Role Based Access Control Administrator* limited by condition to our custom Move roles and the execution identities — creates a role assignment at the exact target scope only after *itself* verifying the signature, the expiry, the nonce and the policy decision, and cannot start the job. The **Move runner** verifies the signature, the target hash and the live ARM state before it acts. Execution identities are **leased exclusively** (one Move at a time) with activation and revocation probes; an independent delete-only sweeper and a Resource Graph alert catch leftovers ([07 §3.3](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim), [07 §4](07-security-architecture.md#4-approvals-that-cannot-be-forged-or-reused)).
**Because.** PIM cannot make managed identities or service principals eligible; standing write roles would violate Q-SEC-1; and a single broker that both grants and dispatches would make one compromised service enough.
**Strongest alternative.** PIM time-bound *active* assignments for the execution identities (unverified for service principals); or standing roles guarded only by the approval check.
**Consequences.** The delegation can constrain roles, principal ids and principal type but **not the target scope**, so target scoping is deterministic code plus detection, not ABAC; the estate must consent to a separate *action* onboarding. RBAC changes can take up to ten minutes to propagate, so purchase windows and the kill-switch table say so. Each of the three is small, typed (C#), property-tested, has no model inside and is separately monitored. Spikes S-ID-1, S-ID-3 and S-ACT-1.
**Round 1** (A-05, A-06, A-07, B-01, B-06, B-08, B-13): **reversed** from "the broker grants and dispatches" — the reviewer's disagreement was accepted.

### ADR-08 Approvals are authenticated actions bound to one target
**Status** Proposed · **Reversibility** moderate · **Revisit when** published Foundry agents can carry authenticated card actions with target binding.
**Decision.** An approval is a Teams Adaptive Card `Action.Execute` with single sign-on, or an Entra-authenticated web page (public-ingress exception X5), validated by the Approval service; it binds a target hash that includes the live state, expires, is single-use and **signed** with the Approval service's key, and for purchases needs two people with different hats and a fresh sign-in (an authentication context where licensed, otherwise a code-enforced fresh sign-in: `prompt=login`, a nonce bound to the approval, the token's `iat` and an `amr` check; `max_age` and `auth_time` are not documented for the Microsoft identity platform, so nothing depends on them). Approver standing comes only from human-administered Entra groups or RBAC roles on the target. Voice, avatar, text and e-mail replies never approve ([07 §4](07-security-architecture.md#4-approvals-that-cannot-be-forged-or-reused)).
**Because.** An approval authorises the only irreversible thing the system does; a model's reading of a chat is not an authorisation.
**Strongest alternative.** Teams' Approvals app (Power Automate) — authenticated and audited, but no target-hash binding or deterministic verification and an added platform; or agent on-behalf-of flows, which Bot-integrated agents cannot use today.
**Consequences.** We run a small bot (public ingress exception X1) in .NET for typing and shared contracts with the Approval service (the Python Agents SDK also registers `Action.Execute` handlers, so the language is a choice, not a constraint); the web page is a second public ingress (X5).
**Round 1** (B-06, B-07, B-15, E-02): approvals are signed; standing comes from human-administered groups; the web page is declared; the Python claim was wrong and is removed.

### ADR-09 Models are aliases and the data class chooses the deployment type
**Status** Proposed · **Reversibility** easy · **Revisit when** Flex reaches general availability, or a new EU Data Zone model changes the cost ratio.
**Decision.** Agents name aliases; the hub maps each to a model and a pool. **Estate and personal data: EU Data Zone Standard** (about +20 % over Global on the GPT-6 family, about +10 % on earlier models; it varies by meter). **Public and synthetic data: Global, Flex or Batch.** GPT-6 Luna carries volume, GPT-6.1 Sol reasoning; GPT-6 Astra is never a default; **`acia-batch` is a separate alias** from the interactive ones ([05 §6](05-agents-and-orchestration.md#6-models-and-the-alias-map)).
**Because.** Models change faster than code, residency is a property of data, and the EU premium should be paid only where the data needs it.
**Strongest alternative.** Everything on Global (≈16 % cheaper in the model, flex-eligible) — violates C9 for estate data; or everything on a regional deployment (+30–50 %).
**Consequences.** Contracts must enforce the data class; Flex has no SLA and returns 429 when short, so it serves only delay-tolerant public work; Batch is not an interactive fallback, so phase 1 uses Flex and Batch waits for an adapter.
**Round 1** (A-09, E-09): Batch split from the interactive aliases; the premium is qualified by model family.

### ADR-10 Judges are a different model family and Claude never sees estate data
**Status** Proposed · **Reversibility** easy · **Revisit when** a Claude model gains an EU Data Zone option.
**Decision.** `acia-judge-eu` resolves to a different family than `acia-reason`, chosen by exam; `acia-judge-pub` may be a Claude model on Global Standard for public and synthetic data only. A contract test enforces independence.
**Because.** A judge from the same family shares blind spots with what it judges; Claude has no EU Data Zone deployment and is billed through the Marketplace with Anthropic as a separate processor.
**Strongest alternative.** A same-family judge: cheaper, one fewer contract, correlated errors.
**Consequences.** A second model family to evaluate and pin; the independent EU option is chosen by measurement, not preference. A Claude model on Foundry is pinned to one hosting version and has no EU Data Zone option, so it is reachable only from public-class contracts.

### ADR-11 The Atlas is Git with a derived search index
**Status** Proposed · **Reversibility** easy · **Revisit when** Foundry IQ's planning and synthesis features reach general availability and pass the exam.
**Decision.** Claims live in a Git repository; a signed release builds a search index on the production account's AI Search service (spike S-DATA-3 confirms a second index there); retrieval uses Foundry IQ's generally available parts or a direct hybrid query ([06 §7.5](06-data-and-knowledge.md#75-atlas-retrieval-and-vectors)).
**Because.** Review, versioning and a public mirror come free; the index is disposable.
**Strongest alternative.** Keeping the Atlas in a database with vectors (Cosmos DB or PostgreSQL): one fewer service, but no review workflow and no public mirror.
**Consequences.** A CI build step and an embeddings call per release; retrieval quality is exam-measured.

### ADR-12 The operational store is Cosmos DB serverless
**Status** Proposed · **Reversibility** moderate · **Revisit when** the vector-index test on serverless fails, or relational integrity becomes decisive.
**Decision.** One Cosmos DB for NoSQL serverless account of our own holds estate knowledge, cases, the Agenda, the Ledger and budget reservations ([06 §7](06-data-and-knowledge.md#7-the-physical-stores)); the spine's orchestration state lives in the Durable Functions task hub ([ADR-33](#adr-33-the-spine-is-durable-functions-on-flex-consumption-calling-leaves-through-the-hub)).
**Because.** No minimum throughput, JSON documents, change feed, and Foundry's own standard setup accepts serverless, so nothing in the design needs a provisioned floor.
**Strongest alternative.** **Azure SQL serverless** — a free offer exists, ledger tables give tamper evidence, and joins are natural; it pauses to storage-only cost but resumes on login with latency. It is the named fallback. PostgreSQL has graph and vector in one engine but is always on.
**Consequences.** Single region (no multi-region serverless); restore relies on an hourly export ([06 §7.6](06-data-and-knowledge.md#76-recovery)).

### ADR-13 Cost analytics is Parquet and an embedded engine in a job
**Status** Proposed · **Reversibility** easy · **Exception** to constraint C1 · **Revisit when** a Microsoft scale-to-zero columnar engine fits.
**Decision.** Cost Management exports (FOCUS, Parquet) land in the lake; the Cost query service runs typed queries in a Container Apps job with **DuckDB** (MIT); only the answers enter the operational store ([06 §7.4](06-data-and-knowledge.md#74-cost-data-parquet-and-an-embedded-engine)).
**Because.** It has **zero standing compute** and the fewest moving parts (Parquet files and a library), and it is the cheapest at our volumes on the model's seeds; a cluster would cost more than the rest of the data tier.
**Strongest alternative.** Azure Data Explorer Dev/Test (about $120 a month floor, minutes to start), Synapse serverless SQL (per terabyte processed; it also reserves no idle compute, so zero standing cost is *not* unique to our choice), or the FinOps toolkit hubs with a Data Explorer back end. All are Microsoft-only; ADX and the hubs cost more at rest.
**Consequences.** An open-source *library* in our container, not a Microsoft service; the exception rests on **measured simplicity and cost**, so spike S-DATA-1 compares it with Synapse serverless and the exception record carries an owner and an expiry date ([08 §10](08-governance-and-compliance.md#10-exceptions)); swappable behind the Cost query interface.
**Round 1** (A-11): the exclusivity claim was wrong and is removed.

### ADR-14 No platform memory
**Status** Proposed · **Reversibility** easy · **Revisit when** Foundry Memory is generally available with private networking and its model calls can be shown to pass the hub.
**Decision.** Foundry Memory is not used; conversation state is the case record ([05 §5](05-agents-and-orchestration.md#5-anatomy-of-a-leaf)).
**Because.** It is preview, has no VNet support, is available in few EU regions, and extraction creates a poisoning and a gateway-bypass path.
**Strongest alternative.** Memory for the Diplomat's per-person preferences only: convenient, but preferences belong to the Estate service where erasure is designed.
**Consequences.** We store preferences ourselves; no lock-in.

### ADR-15 Tools are MCP servers published through the hub
**Status** Proposed · **Reversibility** easy · **Revisit when** toolbox calls are proven to pass the hub (spike S-NET-1).
**Decision.** Every tool is an MCP server — ours on Container Apps, Microsoft's Learn and release-feed servers, and the Azure MCP Server in read-only mode — published through the hub's publish contract with **per-agent, per-tool authorisation** ([04 §4.4](04-landing-zone-and-citadel.md#44-the-publish-contract-tools-and-who-may-call-them)); a tool that returns free text uses the shared source sanitiser. Where the native API Management MCP server is used, its policies apply to **all tools of a server**, so servers are separated by trust class. The Resource Manager MCP server's cost tools run only as a signed-in user and include a write tool; they are not used unattended.
**Because.** One protocol, one front door, one place to filter and meter.
**Strongest alternative.** Foundry toolboxes (generally available for hosted agents): central credentials and tool search, but whether their calls pass the hub is unproven.
**Consequences.** MCP is an open standard (low lock-in); the 2026-07-28 revision is breaking, so a protocol matrix per hop is kept.
**Round 1** (E-03, B-05): the per-tool allow-list fallback was wrong for native MCP servers; the sanitiser applies to every free-text tool.

### ADR-16 The Lab is vended subscriptions, stacks and a reaper
**Status** Proposed · **Reversibility** moderate · **Revisit when** a Microsoft lab product with hard caps appears.
**Decision.** Subscription vending, Deployment Stacks per experiment with an expiry tag, a scheduled reaper, and budgets as *alarms*; the cap is structural (Policy, SKUs, quotas). The Experimenter only **plans**; a deterministic **Lab controller** deploys only **signed recipes** within a pre-deploy cost cap from the price engine, and new recipes are human-reviewed. Experiments run at least two days because billing evidence lags ([07 §8](07-security-architecture.md#8-the-lab-as-a-security-boundary)).
**Because.** Azure Deployment Environments retires 22 February 2027 and Lab Services 28 June 2027; budgets evaluate once a day on data 8–24 hours old and stop nothing; no spending limit exists on EA, MCA or pay-as-you-go subscriptions.
**Strongest alternative.** One shared Lab subscription with resource groups: cheaper and simpler, a larger blast radius.
**Consequences.** Agreement-dependent vending (spike S-ACT-1); policy must carry the real cap.

### ADR-17 Teams through our own adapter, e-mail through Graph, voice off
**Status** Proposed · **Reversibility** easy · **Revisit when** Foundry-published agents can handle card actions with target binding, or Bot Service gains private ingress for Teams.
**Decision.** A Microsoft 365 Agents SDK adapter in a separate external Container Apps environment handles Teams cards; e-mail goes through Microsoft Graph from an Exchange-RBAC-scoped application on a shared mailbox; voice, SMS and avatar modules stay off by default.
**Because.** Approvals need card actions, which Foundry publishing does not describe; the portal cannot even publish a project with public access disabled.
**Strongest alternative.** Foundry publishing to Teams (generally available): least code, conversational, but public Activity route and no approval story. Azure Communication Services e-mail is a fallback for external senders.
**Consequences.** Public-ingress exception X1 with compensating controls ([07 §7](07-security-architecture.md#7-network-and-the-short-list-of-exceptions)).

### ADR-18 Observability is OpenTelemetry into Azure Monitor with cheap table plans
**Status** Proposed · **Reversibility** easy · **Revisit when** the protected content table is generally available.
**Decision.** Agent Framework and Foundry traces and hub logs go to workspace-based Application Insights and Log Analytics, one workspace per environment, per-table plans (Basic or Auxiliary for verbose and long-retention tables), one Private Link Scope, Workbooks and Azure Monitor dashboards with Grafana; content capture is off by default.
**Because.** No extra resource, no standing cost, native to the platform.
**Strongest alternative.** Managed Grafana (private endpoint needs Standard; Essential is deprecated) or a third-party tracing stack with a standing cost.
**Consequences.** Since 31 October 2026 prompt and tool content lands in its own table; old queries break and are rewritten.

### ADR-19 Nine layers against injection with a deterministic gate
**Status** Proposed · **Reversibility** easy · **Revisit when** the Agent Governance Toolkit reaches general availability, or FIDES stabilises.
**Decision.** The nine layers of [07 §5](07-security-architecture.md#5-defence-against-prompt-injection-in-nine-layers), of which layers 0, 1, 6 and 8 are deterministic. Layer 1 is a **source sanitiser** shared by every tool service that returns free text (delimiter escaping, control-character stripping, length caps, an *untrusted* label, chunking at 10,000 characters); the hub's built-in `llm-content-safety` screens MCP and A2A *responses* with a sliding window, while custom policies must not touch the response body; once untrusted text enters a session, privileged tools are blocked or need a human. The gate before a tool call is the Agent Governance Toolkit **if** it proves out, otherwise an in-house check with the same contract.
**Because.** Probabilistic screening reduces but never eliminates injection; the architecture must not depend on it.
**Strongest alternative.** Relying on Foundry guardrails and Defender alone — several are preview, agent guardrails *override* the model's, document attacks are off by default, and agent-level Defender protection moved behind a licence.
**Consequences.** More code of our own in the gate and the sanitiser; the open-source toolkit has breaking changes between majors. Foundry guardrails moderate only the **first 1,000 characters** of a text input (Learn, service limits), so they are never the control for long untrusted text; the sanitiser's chunking and the hub's screening are. An L5 test asserts that the invocation-protocol moderation setting exists on the deployed path and plants an injection beyond character 1,000 and beyond 10,000.
**Round 1** (B-05, D-03, E-04): the sanitiser covers every free-text route, not only documents; the streaming caveat was wrong for the built-in policy; spike S-GW-4.

### ADR-20 Security monitoring feeds the landing zone; licence-bound controls are optional
**Status** Proposed · **Reversibility** easy · **Revisit when** the adopting organisation licenses Agent 365 or Defender for AI broadly.
**Decision.** Diagnostics are deployed by Policy to the platform workspace; we do not run a SIEM. Default paid Defender plans are Resource Manager and Key Vault (≈ €30 a month for the default tier); Agent 365, Defender for AI Services, Defender for APIs, Purview and Conditional Access for agents are optional modules with fallbacks ([07 §11](07-security-architecture.md#11-optional-modules-and-their-fallbacks)).
**Because.** The MIT core must work without any licence; Defender for AI Services is token-metered and can cost more than cheap inference.
**Strongest alternative.** Enable everything: broader detection, a per-token fee on the highest-volume tier, and per-user licences the operator may not have.
**Consequences.** Our own detections D1–D20 carry the baseline (D13–D20 guard the authority chain and the ledger); the Auditor's cross-check of approvals against sign-in logs needs Entra P1 or P2 for the Graph sign-in log.

### ADR-21 Drift is controlled by deterministic detectors and a preview register
**Status** Proposed · **Reversibility** easy · **Revisit when** the platform offers drift detection for hosted agents and gateway contracts natively.
**Decision.** A drift controller of small deterministic jobs compares declared with actual for eighteen layers and emits typed findings; auto-correction only where the declared state is authoritative and reversible; a dependency graph from every claim, dataset, tool, evaluator and credential to its consumers invalidates what a drift touches; the model-fingerprint probe is a *statistical alarm*, not proof; every preview dependency sits in a register with a switch and a fallback ([09](09-safeguards-and-drift-controls.md)).
**Because.** Hosted agents are data-plane objects that Bicep cannot guard, the router changes under a fixed label, and nothing native covers the whole stack.
**Strongest alternative.** An agent that detects drift from telemetry: flexible, probabilistic, and itself subject to drift.
**Consequences.** We build and test the detectors; Foundry's Control Plane complements rather than replaces them.

### ADR-22 Evaluation is Foundry evaluations, our own Exam and open attack suites
**Status** Proposed · **Reversibility** easy · **Revisit when** the red-teaming agent covers function tools and non-Azure tools.
**Decision.** Foundry evaluations (generally available) for built-in and custom evaluators; our own Terrarium and Exam for workflow evaluation and credentials, under a **statistical protocol** (paired non-inferiority against a frozen baseline, one-sided exact bounds, clustering by estate, a human veto on critical cases); PyRIT and ASSERT self-hosted in CI (the AI Red Teaming Agent is optional because its EU availability is unverified); judges through the hub ([10 §9](10-test-and-evaluation.md#9-platform-mapping)).
**Because.** The platform's evaluators grade a run; only our exam measures *rediscovery, restraint and calibration* against baselines.
**Strongest alternative.** Foundry evaluations alone: less to build, no independent examination and no credential gate.
**Consequences.** Judge-prompt caching and composite evaluators keep cost down; Groundedness *detection* (Content Safety) retires on 30 April 2027, while the Foundry Groundedness *evaluator* remains, so gate G5 rests on entailment, receipt hash and freshness, and numeric provenance. Exams are isolated from training (separate generator, keys and labels; post-freeze held-out cases).
**Round 1** (D-05, D-06, D-07, D-09, E-08): statistics, entailment and isolation added; the red-teaming availability is no longer assumed.

### ADR-23 Bicep with Verified Modules, Deployment Stacks and GitHub Actions
**Status** Proposed · **Reversibility** moderate · **Revisit when** a resource we need has no Bicep type.
**Decision.** Bicep with Azure Verified Modules, subscription-scope Deployment Stacks with deny settings, GitHub Actions with workload identity federation for *privileged* workflows only, self-hosted runners as Container Apps event jobs for private targets; `azd` is the developer's inner loop ([11 §2–3](11-delivery-and-operations.md#2-infrastructure-as-code)). **Agent identities may open pull requests only to data paths** (`atlas/**`, `moves/**` YAML); workflows triggered by such pull requests run on GitHub-hosted runners with no secrets and no federation; privileged workflows run from the base branch after a human approves; a required check counts **two distinct approvers who are not the author**.
**Because.** Microsoft-first, no state file, native drift protection through stacks.
**Strongest alternative.** Terraform with AzAPI (covers new resource types sooner; the Citadel accelerator has a Terraform twin with no releases) or Azure DevOps (the only pipeline the accelerator ships).
**Consequences.** Stack limits (five excluded principals, resource-group deletion bypass, and moving a managed resource out of a stack removes its protection — detected and covered by a planted-drift test); no module for sandboxes or agent versions. A GitHub environment needs only one of several reviewers, hence the required check; private-repository entitlement is spike S-DEL-2, and with a single operator promotion is limited to shadow and reversible Moves.
**Round 1** (B-04, A-13, E-11).

### ADR-24 Keyless by default, platform-managed keys
**Status** Proposed · **Reversibility** moderate · **Revisit when** a compliance driver names customer-managed keys.
**Decision.** Managed identities and workload identity federation everywhere; key authentication denied by Policy; platform-managed encryption keys; Key Vault only where a secret cannot be avoided; no Managed HSM ([07 §6](07-security-architecture.md#6-secrets-keys-and-data-protection)).
**Because.** Customer-managed keys for Foundry need bring-your-own stores each keyed, hosted-agent `$HOME` cannot be encrypted that way, and Managed HSM costs about €2,000 a month.
**Strongest alternative.** Customer-managed keys everywhere: stronger control posture, a large fixed cost and operational burden.
**Consequences.** Adding keys later means re-creating some resources.

### ADR-25 Estate and personal data stay in the EU Data Zone
**Status** Proposed · **Reversibility** easy · **Revisit when** an organisation's policy allows Global for specific classes.
**Decision.** Estate-confidential and personal data are processed only on EU Data Zone or regional deployments; the data class is enforced at the hub ([07 §6.2](07-security-architecture.md#62-data-classes-and-what-each-may-touch)).
**Because.** C9, and abuse-monitoring and processing locations differ between deployment types.
**Strongest alternative.** Regional deployments only (+30–50 %): stricter locality, higher cost, fewer models.
**Consequences.** About +20 % on estate-data tokens for the GPT-6 family (about +10 % on earlier models; it varies by meter), offset by routing public work to cheaper types.

### ADR-26 The hub is the spending cap; budgets are alarms
**Status** Proposed · **Reversibility** easy · **Revisit when** a platform feature enforces a hard spend limit.
**Decision.** Token limits and quotas per contract at the hub — **computed from the cost model**, not typed ([12](12-cost-and-finops.md)) — envelopes per run with an **atomic worst-case reservation in the spine** before each leaf call, `max_tokens` set deliberately, cost per case as a release gate; Azure budgets alert only.
**Because.** Budgets evaluate daily on old data and stop nothing; quota is pooled per subscription and is not a cost tool.
**Strongest alternative.** Budget-triggered automation that disables access: a useful backstop, too slow to be the cap.
**Consequences.** The hub's `estimate-prompt-tokens` must be on; the hub is the single point whose availability matters. `llm-token-limit` can overshoot when requests run concurrently, so the residual overrun is bounded by a contract's concurrency times its largest call and is stated, not hidden: the cap is *a* control, not a hard budget.
**Round 1** (A-08, C-04).

### ADR-27 The system operates itself; SRE Agent is off by default
**Status** Proposed · **Reversibility** easy · **Revisit when** a 30-day trial shows value beating the always-on meter.
**Decision.** Self-watch (W9) with deterministic detectors, the Auditor and the Conductor; Azure SRE Agent is not adopted by default; the Observability Agent is an optional human aid ([11 §7.4](11-delivery-and-operations.md#74-who-operates-the-platform-the-system-itself)).
**Because.** SRE Agent bills 4 agent units an hour for as long as it exists (roughly €280–350 a month in Sweden Central), stopping it does not stop billing, and it is not scale-to-zero.
**Strongest alternative.** SRE Agent as the operator: broad diagnostics and a 30-day trial, at a fixed cost larger than the rest of the compute.
**Consequences.** We write our runbooks as detectors and cases.

### ADR-28 Packaging is a monorepo, an azd template and Bicep modules
**Status** Proposed · **Reversibility** easy · **Revisit when** adopters ask for a marketplace offer.
**Decision.** One repository; an `azd` template and Bicep modules for the spokes, the onboarding module and the optional hub; GitHub releases of the signed manifest; MIT. Contributions by agents are pull requests to data paths only ([ADR-23](#adr-23-bicep-with-verified-modules-deployment-stacks-and-github-actions)).
**Because.** Self-hosted, one tenant per deployment (A3 in [01](01-requirements-and-principles.md#2-assumptions)); the operator's tools are `azd`, Bicep and GitHub.
**Strongest alternative.** A managed application in a marketplace: easier adoption, a multi-tenant design we explicitly deferred.
**Consequences.** Adopters operate their own copy.

### ADR-29 Compliance rests on the security benchmark and policy as code
**Status** Proposed · **Reversibility** easy · **Revisit when** an audit needs a premium template.
**Decision.** The Microsoft cloud security benchmark v2 AI domain and Azure Policy are the spine; a control map in the repository ties each control to its evidence; Compliance Manager templates are bought only for an audit ([08](08-governance-and-compliance.md)).
**Because.** Free, enforceable, and testable in CI (gate G8).
**Strongest alternative.** Premium assessment templates from the start: useful for certification, not needed to build the evidence.
**Consequences.** Regulatory positions marked *to confirm* need legal review before production use.

### ADR-30 Recovery is redeploy from code with no second region in phase 1
**Status** Proposed · **Reversibility** moderate · **Revisit when** the operator judges a regional outage intolerable.
**Decision.** RPO ≤ 1 hour for approvals, audit and lessons; RTO one working day; no standing second region ([11 §8](11-delivery-and-operations.md#8-resilience-and-recovery)).
**Because.** The platform has no automatic cross-region failover; a second region doubles the always-on floor.
**Strongest alternative.** A warm second region: faster recovery, roughly doubled fixed cost and a second one-way door.
**Consequences.** Quota and subnet in a second region may be requested and kept dormant. Restore preserves what must not return: snapshots and tombstones so erased data is not resurrected, revocations kept, approvals older than the restore point invalidated, and a geo-redundant secondary so the export lake is reachable in a regional outage ([06 §7.6](06-data-and-knowledge.md#76-recovery)).
**Round 1** (A-12).

### ADR-31 Every release is a signed manifest of pins
**Status** Proposed · **Reversibility** easy · **Revisit when** n/a.
**Decision.** A release manifest names every pin (agent versions and image digests, contract versions, aliases and resolved models, Atlas release, Move versions, framework versions, the Citadel commit); rollback is redeploying the previous manifest ([11 §5](11-delivery-and-operations.md#5-releases-and-versioning)).
**Because.** The platform's own units drift; only a manifest says what we *meant*.
**Strongest alternative.** Floating references with tests: simpler, unreproducible.
**Consequences.** Pins must be maintained; Dependabot and the pipeline help.

### ADR-32 The audit ledger is hash-chained append blobs in immutable storage
**Status** Proposed · **Reversibility** moderate · **Revisit when** immutable append semantics fail the spike S-DATA-2.
**Decision.** Entries are chained append blobs in a container with a locked time-based retention policy; a single **Audit Writer** sequences the entries, and each approval and execution entry is signed by the service that produced it; blobs roll over before the 50,000-block limit; `allowProtectedAppendWrites` is set *before* the policy is locked (it cannot be changed afterwards); a signed daily digest is anchored in a second account; a nightly job verifies the chain ([06 §7.3](06-data-and-knowledge.md#73-the-audit-ledger)).
**Because.** Tamper-evidence at near-zero cost, in the tenant, with no standing compute.
**Strongest alternative.** Azure Confidential Ledger (about €103 a month for the smallest standard instance; about €289 for a three-node managed CCF): stronger attestation, a standing cost. It is an optional module. SQL ledger tables are a second alternative.
**Consequences.** Not queryable (an index lives in the operational store); erasure works by deleting the pseudonym mapping. No change without a ledger entry: if the Audit Writer is down, the execution plane fails closed.
**Round 1** (B-09).

### ADR-33 The spine is Durable Functions on Flex Consumption, calling leaves through the hub
**Status** Proposed · **Reversibility** moderate · **Revisit when** spike S-ORCH-1 fails, or the Durable Extension for the Agent Framework is generally available *and* beats Durable Functions in that spike.
**Decision.** The spine is **Durable Functions** (C#, isolated worker) on the **Flex Consumption** plan with the Azure Storage provider; the Durable Task Scheduler is a drop-in upgrade if the provider proves too slow. Orchestrators are deterministic and call no model: activities start leaf runs *through the hub* and return a result id; orchestrators wait for external events (from the Approval service, the Brief service, a "record written" notification) racing a deadline timer; competing hypotheses fan out and in; instance ids are idempotency keys; the spine reserves each call's worst-case cost atomically before it starts. The Agent Framework runs only *inside* leaves ([05 §4](05-agents-and-orchestration.md#4-how-the-spine-runs)).
**Because.** It is generally available, it scales to zero (nothing runs while a person decides), it runs under the spine's own identity outside any agent boundary, and it supplies the checkpointing, timers, external events, fan-out and versioning that our own design would have to build, test and secure. Learn lists Flex Consumption as fully supported for both providers.
**Strongest alternative.** **Our own checkpoint-and-jobs design** — Agent Framework graph workflows as short-lived Container Apps jobs with a custom checkpoint store in Cosmos DB — was the draft's choice. It is now the **named fallback** and would need JSON-only state, an inbox and outbox, lease fencing and idempotent effects. A workflow inside a hosted agent would run the spine inside a leaf's identity; the Durable Extension for the Agent Framework is pre-release and is not used.
**Consequences.** C# for the spine ([ADR-36](#adr-36-c-for-the-spine-the-execution-plane-and-the-teams-adapter-python-for-agents)); one always-ready instance for the `durable` group (about €21 a month) and queue polling at 10 seconds or less, both from Learn's Flex guidance; orchestrator code must stay deterministic and in-flight instances need a versioning plan; long waits are loops of timers. Lock-in to Durable Functions semantics; the storage provider is swappable.
**Round 1** (A-10, D-04): **reversed**. The draft weighed its own design against the wrong alternative — the pre-release extension for the Agent Framework — instead of the generally available Durable Functions runtime beneath it.

### ADR-34 Clocks are timer triggers and queues; Routines are optional and preview
**Status** Proposed · **Reversibility** easy · **Revisit when** a Routine is confirmed generally available and can start our orchestration with its envelope.
**Decision.** Five clocks implemented as Functions timer triggers that start orchestrations or enqueue work; Foundry Routines are allowed for a single-agent clock but are not the default and are **treated as preview**, because the records conflict (a Foundry devblog and Learn say generally available; the Azure release record says preview) ([05 §9](05-agents-and-orchestration.md#9-the-five-clocks)).
**Because.** The spine needs one mechanism for everything, with budget reservation and an envelope; a routine has one trigger and one action and supports no customer-managed keys; its inputs can be text or JSON, so an envelope is possible, but the status is unclear.
**Strongest alternative.** Routines as the scheduler: nothing to run, but weaker control of invocation and an exclusion list of regions.
**Consequences.** We run the timer triggers.
**Round 1** (E-01): the "cannot carry an envelope" claim was overstated.

### ADR-35 A minimal hub is a separate, optional deliverable
**Status** Proposed · **Reversibility** easy · **Revisit when** n/a.
**Decision.** The preferred model is a shared hub owned by the platform team; if none exists, a documented, tested minimal hub is deployed from the same fork ([04 §10](04-landing-zone-and-citadel.md#10-minimal-hub-if-the-landing-zone-has-none)).
**Because.** A governance hub is a platform capability; but a design that cannot run without one cannot be adopted.
**Strongest alternative.** Require an existing hub: cleaner, narrower adoption.
**Consequences.** We maintain the hardening and the pipeline trimming.

### ADR-36 C# for the spine, the execution plane and the Teams adapter; Python for agents
**Status** Proposed · **Reversibility** moderate · **Revisit when** the Foundry .NET SDK and hosting reach general availability with parity, or the Z3 dependency surface changes.
**Decision.** C# for the **spine** (Durable Functions), the Approval service, Policy service, Credential broker, Move runner, Audit Writer and the Teams adapter; Python for the agents, evaluation, analytics and the attack suites ([05 §5](05-agents-and-orchestration.md#5-anatomy-of-a-leaf)).
**Because.** The code that sequences work and moves money is small, security-critical and benefits from static typing, property-based tests, a small dependency surface and **shared, signed contracts** between the Approval service, the broker and the runner; Durable Functions is most mature on .NET; Python has the richest agent, evaluation and attack-suite ecosystem. The Python Agents SDK *does* register `Action.Execute` handlers, so the adapter is C# for typing and shared contracts, not because a handler is missing.
**Strongest alternative.** All Python (one language) or all C# (the Foundry .NET SDK is still beta, and the attack suites are Python).
**Consequences.** Two toolchains and two sets of pins; the typed contracts are generated from one schema. The prerelease Python hosting package is a convenience, not a dependency: spike S-HOST-1 compares it with a framework-agnostic container.
**Round 1** (E-02, A-10).

### ADR-37 Model-written code runs only in a sandbox with no identity
**Status** Proposed · **Reversibility** easy · **Revisit when** spike S-SBX-1 has verified the EU regions and price of Container Apps Sandboxes, or typed tools make a sandbox unnecessary.
**Decision.** Where an agent must compute, it calls the Sandbox tool: Container Apps dynamic sessions or **Container Apps Sandboxes (generally available since September 2026; EU regions and price unverified)**, no identity, no secrets, egress denied, one session scope per (group, case); typed query tools are preferred wherever they suffice ([05 §5](05-agents-and-orchestration.md#5-anatomy-of-a-leaf)).
**Because.** A hosted agent's process can reach its own token endpoint; code a model writes must not run there.
**Strongest alternative.** Run it in the hosted agent's own microVM: simpler and cheaper, but the code shares the agent's credentials.
**Consequences.** Dynamic sessions are priced per hour, rounding unverified, so computations are batched; the cost model carries one batched session-hour per case ([12](12-cost-and-finops.md)).
**Round 1** (D-14, C-03, B-16): the "preview" label was stale; the sandbox is priced, no longer zero.
