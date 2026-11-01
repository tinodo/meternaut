# Decisions

**What this document answers.** The decisions that shape the design: what was chosen, what was rejected, what it costs, what it means for security, and how hard it is to reverse. Status is *Accepted* unless marked *Proposed* (settled by a proof point in [the roadmap](13-roadmap.md)). How the decisions were challenged is recorded in [the review record](../reviews/README.md).

## 1. Workflows are code, agents think, one component writes · Accepted

- **Decision.** Order, retries, timers, loops, budgets and waiting for people are ordinary code. Agents return typed result records and hold only read tools and a few propose tools. The action plane is the only thing that changes Azure.
- **Instead of.** Agent-driven orchestration: non-deterministic, unbounded in cost, and an injection can steer control flow.
- **Cost · security · reversibility.** Cheap and testable · bounds what a compromised agent can do · high ([agents](03-agents-and-workflows.md), [security](06-security-and-governance.md)).

## 2. Our code runs on Azure Functions; Durable Functions on the Azure Storage provider · Accepted

- **Decision.** Five Function apps (Flex Consumption, Python, zip deployment; the Teams `bot` follows the Agents SDK language): `workflows`, `tools`, `approvals`, `runner` and `bot`, each with its own identity. A workflow that waits days for a person costs nothing while it waits.
- **Instead of.** Foundry workflow agents (retire 1 December 2026); Agent Framework workflows inside hosted agents (sessions time out; the hosting and durable packages are prerelease); Logic Apps Standard (always-on floor); Container Apps with a registry (extra service and, behind a private link, a premium registry). Durable Task Scheduler Consumption is preview, has no high availability and keeps 30 days: an option, not the default.
- **Cost · security · reversibility.** Scales to zero · separate identity per app · medium (the Agent Framework durable extension is the planned switch).

## 3. Five hosted agents, one per trust boundary, hosting ten roles · Accepted

- **Decision.** `study`, `investigate`, `skeptic`, `diplomat`, `engineer` as Foundry hosted agents built with Agent Framework 1.0, zip-deployed, small, with a short idle timeout and one session per workflow run. Each has its own agent identity and hub contract. The Engineer alone holds propose tools and never sees free text.
- **Instead of.** One hosted agent per role (idle tails, ten deployments); one agent for everything (no separation); prompt agents (the hub's bring-your-own-model route is Chat Completions only). Hosted or prompt is chosen by capability. The Librarian returns a change set and the Study workflow opens the pull request, so no role in `study` holds a propose tool.
- **Cost · security · reversibility.** Fewer idle hours · identities follow trust boundaries · high (a role can move into its own agent if testing finds an injection path).

## 4. The Citadel hub is the only door to models and tools; one contract per hosted agent · Accepted

- **Decision.** Contracts `study`, `investigate`, `skeptic`, `diplomat`, `engineer`, `evaluation`, each in dev and prod. Identity is the agent's Entra token; the key Citadel requires is a secret, not identity. Hard token quotas per contract. The dev environment also uses the hub.
- **Instead of.** Direct model access; the Foundry portal gateway; the new `aigateways` product (preview, no feature parity); one shared contract (a leaked key or forged header becomes the whole estate).
- **Cost · security · reversibility.** The hub is shared platform cost; an organisation without one budgets the accelerator ([cost](10-cost-and-finops.md)) · strongest single control · contracts are code, so moving gateways re-implements three contract types.

## 5. Models are chosen by alias; the judge is another family · Accepted

- **Decision.** Aliases `triage`, `reason`, `judge`, `embed`, `batch`. Escalate on objective signals, never on self-reported confidence. Resolved version, protocol and processing location are pinned per alias. The initial mapping is settled by evaluation (P10).
- **Instead of.** Naming models in agent code.
- **Cost · security · reversibility.** A cheaper tier can replace a dearer one without code change · estate data stays in the adopter's data boundary · high.

## 6. The Atlas lives in Git and is served from AI Search; humans merge · Accepted

- **Decision.** Claims, profiles, Detectors and Action templates are files; agents propose by pull request; a person merges, never automatically; a claim can never fill an Action parameter; a release rebuilds the index. One AI Search Basic service.
- **Instead of.** Vector stores inside agents; Foundry Memory (preview, no virtual-network support); a wiki.
- **Cost · security · reversibility.** One search unit is the main fixed knowledge cost · a poisoned claim needs a human to merge it · high. Retrieval options (Serverless, Foundry IQ) are Proposed, settled by P5.

## 7. Estate knowledge in Cosmos DB serverless; the audit log holds ids, never names · Accepted

- **Decision.** Our own account; approvals and credentials written only by the approval service; one open plan per resource. Immutable blob for the audit log, ids and hashes only.
- **Instead of.** Sharing Foundry's agent-state store (blast radius); SQL or a graph database (not needed).
- **Cost · security · reversibility.** Pay per use · separation of writers, erasure possible · medium (a provisioned-throughput switch exists for very large estates).

## 8. Cost data: FOCUS exports to Blob, DuckDB in the `tools` app · Accepted

- **Decision.** Manifest-based replacement ingestion; billed and effective cost kept apart; monthly reconciliation. DuckDB (MIT) is the one non-Microsoft engine.
- **Instead of.** Azure Data Explorer, Fabric, Databricks, FinOps hubs: judged on merit, **not needed in phase 1**; P4 sets the threshold; a hub adapter is phase 4.
- **Cost · security · reversibility.** Storage only · no standing cluster to secure · high (adapters).

## 9. Tools are HTTPS APIs published through the hub as MCP; structured fields only · Accepted

- **Decision.** Free text reaches agents only as a screened, length-capped `untrusted_excerpt`. Our own typed `estate-read` is the default read tool; Azure MCP Server 3.0 is an optional extra (its remote host is Container Apps, settled by P9) and would run with its Read only option and a Reader identity. Tools are pinned and `tools/list` drift is rejected.
- **Instead of.** Self-hosted MCP servers on Functions (preview: a switch; the MCP tool trigger is generally available); passing raw tool output into prompts.
- **Cost · security · reversibility.** Small · cuts the shortest injection paths · high.

## 10. The action plane is the only writer and fails closed · Accepted

- **Decision.** Catalogue → plan (what-if, hash, etags) → approval → runner → verifier → audit. Any mismatch aborts; the runner never refreshes and proceeds. Idempotent runs; a purchase is never retried automatically.
- **Instead of.** Letting agents run commands; "refresh and proceed".
- **Cost · security · reversibility.** Runner cost is small · the control that matters most · the catalogue grows by pull request.

## 11. Approval is a bound, displayed, single-use authorization · Accepted

- **Decision.** The approval service renders the canonical plan; cards carry an opaque id; the record binds plan hash, etags, quote, approver id and role, and the authentication claim; consumed once. Purchases need two distinct directory roles. Credentials (autopilot) are policies evaluated in code on facts the model cannot set, never for purchases.
- **Instead of.** Trusting a row plus a card; tags or lessons deciding scope.
- **Cost · security · reversibility.** Small · closes replay, swap and confused-deputy paths · signing the record is a later hardening.

## 12. Runner roles per action family; no standing purchase role · Accepted

- **Decision.** One narrow custom role per action family at scopes the organisation opts in. Purchases: a role assignment with an end time, created and removed by the approval service, bound to a stored quote; alarms disable the identity. P8 settles propagation and revocation.
- **Instead of.** One broad role; a standing purchaser. Privileged Identity Management cannot make service principals eligible.
- **Cost · security · reversibility.** Role assignments are free · limits blast radius; a compromised runner can still perform its family's actions in opted-in scopes · high.

## 13. Agents draft, workflows send; recipients come from the directory · Accepted

- **Decision.** A model never chooses or supplies a recipient; free text never approves. Teams cards use the Agents SDK in .NET or JavaScript (card routing is not in the Python SDK), in a small `bot` app that validates the Bot Framework token and forwards only an opaque id; Azure Bot Service offers no IP allow-list, so token validation is the control. Approvals above R1 open the web page. Email uses an app-only mailbox with a recipient allow-list; Azure Communication Services Email retires in 2028 and is not used.
- **Instead of.** Agents sending messages; approval by reply.
- **Cost · security · reversibility.** Small · stops exfiltration by mail and forged approvals · high.

## 14. Two profiles; Operate uses platform-managed Foundry data · Accepted

- **Decision.** Evaluate (synthetic data, public with Entra sign-in, no private endpoints, dev contracts, no production roles) and Operate (bring-your-own virtual network, platform-managed agent data, private endpoints). The network setting is fixed at account creation, so a profile change is a new account.
- **Instead of.** Bring-your-own Cosmos DB, Storage and Search for Foundry by default (adds endpoints and stores; available as a parameter).
- **Cost · security · reversibility.** Dev costs little · dev cannot reach prod, tested · a one-way door per account.

## 15. Evaluation in three tiers; learning shown by frozen versus updated memory · Accepted

- **Decision.** Zero-LLM checks on every pull request; LLM suites on change, on Flex where it is available (preview; Global Standard otherwise); sampled production scoring and safety suites before each autonomy level. Only verified bank rows become gold, adjudicated by a person; sealed rotating test sets.
- **Instead of.** Full suites on every change; a judge as truth.
- **Cost · security · reversibility.** The main variable cost of the Evaluate profile ([cost](10-cost-and-finops.md)) · red team gates autonomy · high ([evaluation](08-testing-and-evaluation.md)).

## 16. Drift controls name their check, interval, owner and response · Accepted

- **Decision.** Every kind of drift (models, prompts, tools, knowledge, prices, infrastructure, Entra and portal edits, hub contracts, behaviour, savings, permissions, own spend) has a check, an interval, an owner and a fail-closed response ([drift](07-safeguards-and-drift.md)).
- **Instead of.** A list of things to watch.
- **Cost · security · reversibility.** Small · catches silent loosening · high.

## 17. No lab: the system never deploys resources to learn · Accepted

- **Decision.** Learning comes from documents, price lists, schemas, release notes, bills, replays, owners' answers and small owner-approved reversible trials. The honest gap: a meter nobody has used cannot be discovered this way, and the first organisation to use a new service meets surprises, so its advice is labelled.
- **Instead of.** A budget-capped sandbox subscription running billing experiments (costly, needs its own governance).
- **Cost · security · reversibility.** Avoids the largest cost in the first design · no experiment estate to secure · reversible: an organisation that wants experiments can add its own environment later ([knowledge](04-knowledge-and-learning.md)).

## 18. Cost is a design constraint · Accepted

- **Decision.** Scale to zero; Detectors for cheap leads; small model first; Batch and Flex for non-urgent work; evaluation on change plus sampling; one Key Vault, one AI Search, no container registry; the solution watches its own bill. Azure budgets only alert, so hard stops are the hub's token quotas and a run-rate trip.
- **Cost · security · reversibility.** The point · quotas double as safety limits · high.

## 19. Licences and non-Microsoft parts are listed, not presumed · Accepted

- **Decision.** [Goals and scope](01-goals-and-scope.md) lists what each feature needs (Entra P1, P2, Agent 365, Microsoft 365); [the register](11-technology-register.md) lists non-Microsoft parts with a Microsoft alternative.
- **Cost · security · reversibility.** n/a · no hidden dependency · high.

## 20. Single-tenant; one organisation, many subscriptions · Accepted

- **Decision.** Multi-tenant or service-provider operation is out of scope until at least phase 5.
- **Instead of.** Designing tenancy boundaries now.
- **Cost · security · reversibility.** Simpler everything · no cross-tenant data path · high.
