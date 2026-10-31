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
| [06](#adr-06-an-entra-agent-identity-per-agent-and-nine-contract-groups) | An Entra agent identity per agent; nine contract groups | moderate | partly |
| [07](#adr-07-execution-identities-are-granted-just-in-time-by-a-broker) | Execution identities granted just in time by a broker | moderate | no |
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
| [33](#adr-33-the-spine-runs-as-container-apps-jobs-with-our-checkpoint-store) | The spine runs as Container Apps jobs with our checkpoint store | moderate | the alternative is preview |
| [34](#adr-34-clocks-are-cron-jobs-and-queues-routines-are-optional) | Clocks are cron jobs and queues; Routines are optional | easy | no |
| [35](#adr-35-a-minimal-hub-is-a-separate-optional-deliverable) | A minimal hub is a separate, optional deliverable | easy | no |
| [36](#adr-36-python-for-agents-c-for-the-execution-plane) | Python for agents; C# for the execution plane | moderate | no |
| [37](#adr-37-model-written-code-runs-only-in-a-sandbox-with-no-identity) | Model-written code runs only in a sandbox with no identity | easy | sandboxes preview |

---

## Decisions

### ADR-01 A deterministic spine calls agentic leaves
**Status** Proposed · **Reversibility** moderate · **Revisit when** a partner's agent must be called, or an A2A path through the hub is generally available and its authentication is unambiguous.
**Decision.** Workflows are deterministic and contain no model. They invoke fourteen **hosted agents** one step at a time with an envelope of ids and budgets. Agents never call each other; they read and write typed records ([05 §1](05-agents-and-orchestration.md#1-the-pattern-a-deterministic-spine-with-agentic-leaves)).
**Because.** It removes the channel along which an injected instruction would travel between agents, makes budgets and retries deterministic, and makes each leaf separately testable and replaceable.
**Strongest alternative.** Agents that hand off to each other (Agent Framework handoff, group chat, or A2A through the hub): more fluid collaboration and less schema work. Rejected because each hop is an injection path, A2A through the hub is preview with contradictory authentication notes, and cost control moves into prompts.
**Consequences.** Schema upkeep; less emergent behaviour; every leaf needs a typed output. No lock-in beyond the Agent Framework's open-source workflow model.

### ADR-02 The gateway is the Citadel Governance Hub on API Management
**Status** Proposed · **Reversibility** moderate · **Revisit when** the AI Gateway product meets the criteria in [04 §9](04-landing-zone-and-citadel.md#9-the-ai-gateway-product-a-decision-gate).
**Decision.** All model, tool and agent traffic passes the Citadel Governance Hub, forked and pinned to a commit, with contracts in our repository ([04](04-landing-zone-and-citadel.md)).
**Because.** It is the framework the brief names, it is hub-and-spoke, and its contracts (backend, access, publish) are exactly the supply, demand and publishing surfaces we need; API Management's AI policies are generally available.
**Strongest alternative.** The new standalone AI Gateway product (calendar budgets, tool-level governance) — preview, two regions, no price, policies that do not match Citadel's contracts. A second alternative, Foundry's portal gateway, creates a second API Management in the same subscription as Foundry and routes only some tools.
**Consequences.** The hub is a **single-maintainer sample** with no releases; a fixed monthly floor of about €320 in its usage pipeline unless shared or trimmed; contracts as data keep exit cheap. Risk R4 in [08](08-governance-and-compliance.md#8-risk-register).

### ADR-03 Two spokes, a Lab management group and read-only estates
**Status** Proposed · **Reversibility** moderate · **Revisit when** the non-production floor of a standard-setup Foundry account proves too costly ([12](12-cost-and-finops.md)).
**Decision.** `acia-prod` and `acia-nonprod` spokes; vended Lab subscriptions in their own management group; estates are other subscriptions with read-only roles granted by an onboarding module ([04 §3](04-landing-zone-and-citadel.md#3-topology)).
**Because.** Environments need separate trust boundaries and separate quota; the Lab must have no route to anything real.
**Strongest alternative.** One subscription with resource groups per environment: cheaper, one quota pool, and a single noisy agent group can starve the others.
**Consequences.** Three or more subscriptions to vend; the Foundry standard setup repeats per account. A cheaper shape for dev is spike **S-NET-2**.

### ADR-04 Sweden Central is the primary region
**Status** Proposed · **Reversibility** one-way per Foundry account · **Revisit when** West Europe gains managed VNet, the full AI Landing Zone deployment and serverless search.
**Decision.** Sweden Central hosts the spokes; the hub is wherever the landing zone puts it ([04 §3.2](04-landing-zone-and-citadel.md#32-region)).
**Because.** It is the only EU region present in every capability list that matters (hosted agents, managed VNet, the AI Landing Zone, the hub's region list, serverless search).
**Strongest alternative.** West Europe: the likely home of the operator's landing zone, about 30 % cheaper API Management, and hosted agents are listed there — but no hosted-agent meter appears in the price API, and managed VNet and the AI Landing Zone are absent.
**Consequences.** Cross-region peering if the connectivity hub differs; a different region for the Foundry account later means re-creating it.

### ADR-05 Bring-your-own-VNet injection, not the managed VNet
**Status** Proposed · **Reversibility** one-way · **Revisit when** managed VNet offers outbound logging, a bring-your-own firewall and West Europe.
**Decision.** Agents run in a delegated `/24` subnet of our spoke; egress passes the landing zone's firewall with an FQDN allow-list ([04 §6](04-landing-zone-and-citadel.md#6-network)).
**Because.** The managed VNet's FQDN rules create a managed Azure Firewall that bills about €250–800 a month, has no outbound logging and no custom firewall, and cannot be switched off.
**Strongest alternative.** Managed VNet: no address planning and fewer resources for us to own.
**Consequences.** We own the subnet; subnet exhaustion is silent (HTTP 429), so it is monitored; the choice is made at account creation and cannot be changed.

### ADR-06 An Entra agent identity per agent and nine contract groups
**Status** Proposed · **Reversibility** moderate · **Revisit when** the hub accepts identity without a shared key.
**Decision.** Each hosted agent has its own Entra agent identity, a named sponsor and no standing roles; agents are gathered into **nine groups** (study, survey, investigate, experiment, converse, engineer, govern, forge, conduct), each with one hub contract per environment ([05 §2](05-agents-and-orchestration.md#2-the-roster), [04 §4](04-landing-zone-and-citadel.md#43-the-access-contracts)).
**Because.** The groups are the capability classes of the lethal-trifecta matrix; the Forger and the Conductor are separate so the adversary shares nothing with the examinee and the budget holder cannot spend another group's budget.
**Strongest alternative.** One shared project identity per Foundry project (the legacy behaviour) or three coarse groups: fewer contracts, blurred blast radius.
**Consequences.** Per-agent attribution at the hub depends on the token's `azp` for agent identities (spike S-ID-2); until then a header carries it. Conditional Access for agents is licence-bound and optional.

### ADR-07 Execution identities are granted just in time by a broker
**Status** Proposed · **Reversibility** moderate · **Revisit when** PIM supports time-bound activation for workload identities with our licences.
**Decision.** A small deterministic **credential broker**, holding *Role Based Access Control Administrator* limited by condition, creates a role assignment at the exact target scope for one approved Move and removes it afterwards; an independent sweeper and a Resource Graph alert catch leftovers ([07 §3.3](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim)).
**Because.** PIM cannot make managed identities or service principals eligible; standing write roles would violate Q-SEC-1.
**Strongest alternative.** PIM time-bound *active* assignments for the execution identities (unverified for service principals); or standing roles guarded only by the approval check.
**Consequences.** The broker is the crown jewel: small, typed (C#), property-tested, no model inside, separately monitored. Spikes S-ID-1 and S-ACT-1.

### ADR-08 Approvals are authenticated actions bound to one target
**Status** Proposed · **Reversibility** moderate · **Revisit when** published Foundry agents can carry authenticated card actions with target binding.
**Decision.** An approval is a Teams Adaptive Card `Action.Execute` with single sign-on, or a link to an Entra-protected page, validated by the Approval service; it binds a target hash, expires, is single-use, and for purchases needs two people with different hats and a fresh-MFA authentication context. Voice, avatar, text and e-mail replies never approve ([07 §4](07-security-architecture.md#4-approvals-that-cannot-be-forged-or-reused)).
**Because.** An approval authorises the only irreversible thing the system does; a model's reading of a chat is not an authorisation.
**Strongest alternative.** Teams' Approvals app (Power Automate) — authenticated and audited, but no target-hash binding or deterministic verification and an added platform; or agent on-behalf-of flows, which Bot-integrated agents cannot use today.
**Consequences.** We run a small bot (public ingress exception X1) and write it in .NET, because card-action handlers are absent from the Python Agents SDK.

### ADR-09 Models are aliases and the data class chooses the deployment type
**Status** Proposed · **Reversibility** easy · **Revisit when** Flex reaches general availability, or a new EU Data Zone model changes the cost ratio.
**Decision.** Agents name aliases; the hub maps each to a model and a pool. **Estate and personal data: EU Data Zone Standard** (about +20 % over Global). **Public and synthetic data: Global, Flex or Batch.** GPT-6 Luna carries volume, GPT-6.1 Sol reasoning; GPT-6 Astra is never a default ([05 §6](05-agents-and-orchestration.md#6-models-and-the-alias-map)).
**Because.** Models change faster than code, residency is a property of data, and the EU premium should be paid only where the data needs it.
**Strongest alternative.** Everything on Global (≈17 % cheaper, flex-eligible) — violates C9 for estate data; or everything on a regional deployment (+30–50 %).
**Consequences.** Contracts must enforce the data class; Flex has no SLA and returns 429 when short, so it serves only delay-tolerant public work.

### ADR-10 Judges are a different model family and Claude never sees estate data
**Status** Proposed · **Reversibility** easy · **Revisit when** a Claude model gains an EU Data Zone option.
**Decision.** `acia-judge-eu` resolves to a different family than `acia-reason`, chosen by exam; `acia-judge-pub` may be a Claude model on Global Standard for public and synthetic data only. A contract test enforces independence.
**Because.** A judge from the same family shares blind spots with what it judges; Claude has no EU Data Zone deployment and is billed through the Marketplace with Anthropic as a separate processor.
**Strongest alternative.** A same-family judge: cheaper, one fewer contract, correlated errors.
**Consequences.** A second model family to evaluate and pin; the independent EU option is chosen by measurement, not preference.

### ADR-11 The Atlas is Git with a derived search index
**Status** Proposed · **Reversibility** easy · **Revisit when** Foundry IQ's planning and synthesis features reach general availability and pass the exam.
**Decision.** Claims live in a Git repository; a signed release builds a search index on the existing AI Search service; retrieval uses Foundry IQ's generally available parts or a direct hybrid query ([06 §7.5](06-data-and-knowledge.md#75-atlas-retrieval-and-vectors)).
**Because.** Review, versioning and a public mirror come free; the index is disposable.
**Strongest alternative.** Keeping the Atlas in a database with vectors (Cosmos DB or PostgreSQL): one fewer service, but no review workflow and no public mirror.
**Consequences.** A CI build step and an embeddings call per release; retrieval quality is exam-measured.

### ADR-12 The operational store is Cosmos DB serverless
**Status** Proposed · **Reversibility** moderate · **Revisit when** the vector-index test on serverless fails, or relational integrity becomes decisive.
**Decision.** One Cosmos DB for NoSQL serverless account of our own holds estate knowledge, cases, the Agenda, the Ledger and checkpoints ([06 §7](06-data-and-knowledge.md#7-the-physical-stores)).
**Because.** No minimum throughput, JSON documents, change feed, and Foundry's own standard setup accepts serverless, so nothing in the design needs a provisioned floor.
**Strongest alternative.** **Azure SQL serverless** — a free offer exists, ledger tables give tamper evidence, and joins are natural; it pauses to storage-only cost but resumes on login with latency. It is the named fallback. PostgreSQL has graph and vector in one engine but is always on.
**Consequences.** Single region (no multi-region serverless); restore relies on an hourly export ([06 §7.6](06-data-and-knowledge.md#76-recovery)).

### ADR-13 Cost analytics is Parquet and an embedded engine in a job
**Status** Proposed · **Reversibility** easy · **Exception** to constraint C1 · **Revisit when** a Microsoft scale-to-zero columnar engine fits.
**Decision.** Cost Management exports (FOCUS, Parquet) land in the lake; the Cost query service runs typed queries in a Container Apps job with **DuckDB** (MIT); only the answers enter the operational store ([06 §7.4](06-data-and-knowledge.md#74-cost-data-parquet-and-an-embedded-engine)).
**Because.** It is the only option with **zero standing compute**; a cluster would cost more than the rest of the data tier.
**Strongest alternative.** Azure Data Explorer Dev/Test (about $120 a month floor, minutes to start), Synapse serverless SQL (per terabyte processed), or the FinOps toolkit hubs with a Data Explorer back end. All are Microsoft-only and all cost more at rest.
**Consequences.** An open-source *library* in our container, not a Microsoft service; recorded as an exception ([08 §10](08-governance-and-compliance.md#10-exceptions)); swappable behind the Cost query interface.

### ADR-14 No platform memory
**Status** Proposed · **Reversibility** easy · **Revisit when** Foundry Memory is generally available with private networking and its model calls can be shown to pass the hub.
**Decision.** Foundry Memory is not used; conversation state is the case record ([05 §5](05-agents-and-orchestration.md#5-anatomy-of-a-leaf)).
**Because.** It is preview, has no VNet support, is available in few EU regions, and extraction creates a poisoning and a gateway-bypass path.
**Strongest alternative.** Memory for the Diplomat's per-person preferences only: convenient, but preferences belong to the Estate service where erasure is designed.
**Consequences.** We store preferences ourselves; no lock-in.

### ADR-15 Tools are MCP servers published through the hub
**Status** Proposed · **Reversibility** easy · **Revisit when** toolbox calls are proven to pass the hub (spike S-NET-1).
**Decision.** Every tool is an MCP server — ours on Container Apps, Microsoft's Learn and release-feed servers, and the Azure MCP Server in read-only mode — published through the hub's publish contract with per-group allow-lists ([04 §4.4](04-landing-zone-and-citadel.md#44-the-publish-contract-tools-and-who-may-call-them)). The Resource Manager MCP server's cost tools run only as a signed-in user and include a write tool; they are not used unattended.
**Because.** One protocol, one front door, one place to filter and meter.
**Strongest alternative.** Foundry toolboxes (generally available for hosted agents): central credentials and tool search, but whether their calls pass the hub is unproven.
**Consequences.** MCP is an open standard (low lock-in); the 2026-07-28 revision is breaking, so a protocol matrix per hop is kept.

### ADR-16 The Lab is vended subscriptions, stacks and a reaper
**Status** Proposed · **Reversibility** moderate · **Revisit when** a Microsoft lab product with hard caps appears.
**Decision.** Subscription vending, Deployment Stacks per experiment with an expiry tag, a scheduled reaper, and budgets as *alarms*; the cap is structural (Policy, SKUs, quotas). Experiments run at least two days because billing evidence lags ([07 §8](07-security-architecture.md#8-the-lab-as-a-security-boundary)).
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
**Decision.** The nine layers of [07 §5](07-security-architecture.md#5-defence-against-prompt-injection-in-nine-layers), of which layers 0, 1, 6 and 8 are deterministic; the gate before a tool call is the Agent Governance Toolkit **if** it proves out, otherwise an in-house check with the same contract.
**Because.** Probabilistic screening reduces but never eliminates injection; the architecture must not depend on it.
**Strongest alternative.** Relying on Foundry guardrails and Defender alone — several are preview, agent guardrails *override* the model's, document attacks are off by default, and agent-level Defender protection moved behind a licence.
**Consequences.** More code of our own in the gate; the open-source toolkit has breaking changes between majors.

### ADR-20 Security monitoring feeds the landing zone; licence-bound controls are optional
**Status** Proposed · **Reversibility** easy · **Revisit when** the adopting organisation licenses Agent 365 or Defender for AI broadly.
**Decision.** Diagnostics are deployed by Policy to the platform workspace; we do not run a SIEM. Default paid Defender plans are Resource Manager and Key Vault (≈ €30 a month for the default tier); Agent 365, Defender for AI Services, Defender for APIs, Purview and Conditional Access for agents are optional modules with fallbacks ([07 §11](07-security-architecture.md#11-optional-modules-and-their-fallbacks)).
**Because.** The MIT core must work without any licence; Defender for AI Services is token-metered and can cost more than cheap inference.
**Strongest alternative.** Enable everything: broader detection, a per-token fee on the highest-volume tier, and per-user licences the operator may not have.
**Consequences.** Our own detections D1–D12 carry the baseline.

### ADR-21 Drift is controlled by deterministic detectors and a preview register
**Status** Proposed · **Reversibility** easy · **Revisit when** the platform offers drift detection for hosted agents and gateway contracts natively.
**Decision.** A drift controller of small deterministic jobs compares declared with actual for eighteen layers and emits typed findings; auto-correction only where the declared state is authoritative and reversible; every preview dependency sits in a register with a switch and a fallback ([09](09-safeguards-and-drift-controls.md)).
**Because.** Hosted agents are data-plane objects that Bicep cannot guard, the router changes under a fixed label, and nothing native covers the whole stack.
**Strongest alternative.** An agent that detects drift from telemetry: flexible, probabilistic, and itself subject to drift.
**Consequences.** We build and test the detectors; Foundry's Control Plane complements rather than replaces them.

### ADR-22 Evaluation is Foundry evaluations, our own Exam and open attack suites
**Status** Proposed · **Reversibility** easy · **Revisit when** the red-teaming agent covers function tools and non-Azure tools.
**Decision.** Foundry evaluations (generally available) for built-in and custom evaluators; our own Terrarium and Exam for workflow evaluation and credentials; PyRIT and ASSERT in CI; the AI Red Teaming Agent on a schedule; judges through the hub ([10 §9](10-test-and-evaluation.md#9-platform-mapping)).
**Because.** The platform's evaluators grade a run; only our exam measures *rediscovery, restraint and calibration* against baselines.
**Strongest alternative.** Foundry evaluations alone: less to build, no independent examination and no credential gate.
**Consequences.** Judge-prompt caching and composite evaluators keep cost down; Groundedness retires in April 2027, so a receipts check replaces it.

### ADR-23 Bicep with Verified Modules, Deployment Stacks and GitHub Actions
**Status** Proposed · **Reversibility** moderate · **Revisit when** a resource we need has no Bicep type.
**Decision.** Bicep with Azure Verified Modules, subscription-scope Deployment Stacks with deny settings, GitHub Actions with workload identity federation, self-hosted runners as Container Apps event jobs for private targets; `azd` is the developer's inner loop ([11 §2–3](11-delivery-and-operations.md#2-infrastructure-as-code)).
**Because.** Microsoft-first, no state file, native drift protection through stacks.
**Strongest alternative.** Terraform with AzAPI (covers new resource types sooner; the Citadel accelerator has a Terraform twin with no releases) or Azure DevOps (the only pipeline the accelerator ships).
**Consequences.** Stack limits (five excluded principals, resource-group deletion bypass); no module for sandboxes or agent versions.

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
**Consequences.** About +20 % on estate-data tokens, offset by routing public work to cheaper types.

### ADR-26 The hub is the spending cap; budgets are alarms
**Status** Proposed · **Reversibility** easy · **Revisit when** a platform feature enforces a hard spend limit.
**Decision.** Token limits and quotas per contract at the hub, envelopes per run, `max_tokens` set deliberately, cost per case as a release gate; Azure budgets alert only ([12](12-cost-and-finops.md)).
**Because.** Budgets evaluate daily on old data and stop nothing; quota is pooled per subscription and is not a cost tool.
**Strongest alternative.** Budget-triggered automation that disables access: a useful backstop, too slow to be the cap.
**Consequences.** The hub's `estimate-prompt-tokens` must be on; the hub is the single point whose availability matters.

### ADR-27 The system operates itself; SRE Agent is off by default
**Status** Proposed · **Reversibility** easy · **Revisit when** a 30-day trial shows value beating the always-on meter.
**Decision.** Self-watch (W9) with deterministic detectors, the Auditor and the Conductor; Azure SRE Agent is not adopted by default; the Observability Agent is an optional human aid ([11 §7.4](11-delivery-and-operations.md#74-who-operates-the-platform-the-system-itself)).
**Because.** SRE Agent bills 4 agent units an hour for as long as it exists (roughly €280–350 a month in Sweden Central), stopping it does not stop billing, and it is not scale-to-zero.
**Strongest alternative.** SRE Agent as the operator: broad diagnostics and a 30-day trial, at a fixed cost larger than the rest of the compute.
**Consequences.** We write our runbooks as detectors and cases.

### ADR-28 Packaging is a monorepo, an azd template and Bicep modules
**Status** Proposed · **Reversibility** easy · **Revisit when** adopters ask for a marketplace offer.
**Decision.** One repository; an `azd` template and Bicep modules for the spokes, the onboarding module and the optional hub; GitHub releases of the signed manifest; MIT.
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
**Consequences.** Quota and subnet in a second region may be requested and kept dormant.

### ADR-31 Every release is a signed manifest of pins
**Status** Proposed · **Reversibility** easy · **Revisit when** n/a.
**Decision.** A release manifest names every pin (agent versions and image digests, contract versions, aliases and resolved models, Atlas release, Move versions, framework versions, the Citadel commit); rollback is redeploying the previous manifest ([11 §5](11-delivery-and-operations.md#5-releases-and-versioning)).
**Because.** The platform's own units drift; only a manifest says what we *meant*.
**Strongest alternative.** Floating references with tests: simpler, unreproducible.
**Consequences.** Pins must be maintained; Dependabot and the pipeline help.

### ADR-32 The audit ledger is hash-chained append blobs in immutable storage
**Status** Proposed · **Reversibility** moderate · **Revisit when** immutable append semantics fail the spike S-DATA-2.
**Decision.** Entries are chained append blobs in a container with a locked time-based retention policy; a signed daily digest is anchored in a second account; a nightly job verifies the chain ([06 §7.3](06-data-and-knowledge.md#73-the-audit-ledger)).
**Because.** Tamper-evidence at near-zero cost, in the tenant, with no standing compute.
**Strongest alternative.** Azure Confidential Ledger (about €103 a month for the smallest standard instance; about €289 for a three-node managed CCF): stronger attestation, a standing cost. It is an optional module. SQL ledger tables are a second alternative.
**Consequences.** Not queryable (an index lives in the operational store); erasure works by deleting the pseudonym mapping.

### ADR-33 The spine runs as Container Apps jobs with our checkpoint store
**Status** Proposed · **Reversibility** moderate · **Revisit when** the Durable Extension for the Agent Framework is generally available.
**Decision.** Agent Framework graph workflows execute as short-lived Container Apps jobs triggered by queues; checkpoints in our Cosmos DB through the framework's storage protocol; the Approval service enqueues the signal that resumes a waiting workflow ([05 §4](05-agents-and-orchestration.md#4-how-the-spine-runs)).
**Because.** The spine must run *outside* any agent identity, with no model, on scale-to-zero compute that bills nothing while a person decides.
**Strongest alternative.** The **Durable Extension** (Functions Flex Consumption with the Durable Task Scheduler): waits cost no compute, but the packages are prerelease. It is the named fallback (spike S-ORCH-1). A workflow inside a hosted agent would run the spine inside a leaf's identity.
**Consequences.** We own the checkpoint store's integrity (JSON only, signed, spine-only access).

### ADR-34 Clocks are cron jobs and queues; Routines are optional
**Status** Proposed · **Reversibility** easy · **Revisit when** a routine can carry an envelope.
**Decision.** Five clocks implemented as Container Apps cron jobs enqueueing work; Foundry Routines (generally available since 24 September 2026) are allowed for a single-agent clock but are not the default ([05 §9](05-agents-and-orchestration.md#9-the-five-clocks)).
**Because.** A routine has one trigger and one action and cannot carry an envelope; it supports no customer-managed keys; the spine needs one mechanism for everything.
**Strongest alternative.** Routines as the scheduler: nothing to run, but weaker control of invocation and an exclusion list of regions.
**Consequences.** We run the cron jobs.

### ADR-35 A minimal hub is a separate, optional deliverable
**Status** Proposed · **Reversibility** easy · **Revisit when** n/a.
**Decision.** The preferred model is a shared hub owned by the platform team; if none exists, a documented, tested minimal hub is deployed from the same fork ([04 §10](04-landing-zone-and-citadel.md#10-minimal-hub-if-the-landing-zone-has-none)).
**Because.** A governance hub is a platform capability; but a design that cannot run without one cannot be adopted.
**Strongest alternative.** Require an existing hub: cleaner, narrower adoption.
**Consequences.** We maintain the hardening and the pipeline trimming.

### ADR-36 Python for agents, C# for the execution plane
**Status** Proposed · **Reversibility** moderate · **Revisit when** the Python Agents SDK gains card-action routing or the Z3 dependency surface changes.
**Decision.** Python for agents, evaluation and analytics; C# for the Approval service, Policy service, Credential broker, Move runner and the Teams adapter ([05 §5](05-agents-and-orchestration.md#5-anatomy-of-a-leaf)).
**Because.** The money-moving code is small, security-critical and benefits from static typing, property-based tests and a small dependency surface; Python has the richest agent, evaluation and attack-suite ecosystem; Teams card actions exist in .NET and JavaScript only.
**Strongest alternative.** All Python (one language) or all C# (the Foundry .NET SDK is still beta, and the attack suites are Python).
**Consequences.** Two toolchains and two sets of pins.

### ADR-37 Model-written code runs only in a sandbox with no identity
**Status** Proposed · **Reversibility** easy · **Revisit when** Container Apps Sandboxes are generally available in EU regions.
**Decision.** Where an agent must compute, it calls the Sandbox tool: Container Apps dynamic sessions (generally available), no identity, no secrets, egress denied; typed query tools are preferred wherever they suffice ([05 §5](05-agents-and-orchestration.md#5-anatomy-of-a-leaf)).
**Because.** A hosted agent's process can reach its own token endpoint; code a model writes must not run there.
**Strongest alternative.** Run it in the hosted agent's own microVM: simpler and cheaper, but the code shares the agent's credentials. Sandboxes bill per second and cost nothing while suspended; they are preview.
**Consequences.** Dynamic sessions bill in one-hour increments, so computations are batched.
