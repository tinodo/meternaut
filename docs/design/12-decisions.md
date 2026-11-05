# Decisions

**What this document answers.** The decisions that shape the design: what was chosen, what was rejected, what it costs, what it means for security, and how hard it is to reverse. How the decisions were challenged is recorded in [the review record](../reviews/README.md). Decisions about what people see and receive are in [the experience design](../experience/14-decisions.md).

## 1. Workflows are code, agents think, one component writes · Accepted

- **Decision.** Order, retries, timers, loops, budgets and waiting for people are ordinary code. Agents return typed result records and hold only read tools and a few propose tools. Only the action plane changes Azure.
- **Instead of.** Agent-driven orchestration: non-deterministic, unbounded in cost, and an injection can steer control flow.
- **Cost · security · reversibility.** Cheap and testable · bounds what a compromised agent can do · high ([agents](03-agents-and-workflows.md), [security](06-security-and-governance.md)).

## 2. Our code runs on Azure Functions; Durable Functions on the Azure Storage provider · Accepted

- **Decision.** Five Function apps (Flex Consumption, Python, zip deployment; the Teams `bot` follows the Agents SDK language): `workflows`, `tools`, `approvals`, `runner` and `bot`.
- **Instead of.** Foundry workflow agents (retire 1 December 2026); Agent Framework workflows inside hosted agents (sessions time out; the hosting and durable packages are prerelease); Logic Apps Standard (always-on floor); Container Apps (a registry, premium behind a private link). Durable Task Scheduler Consumption is preview, has no high availability and keeps 30 days: an option, not the default.
- **Cost · security · reversibility.** Scales to zero · separate identity per app · medium (the Agent Framework durable extension is the planned switch).

## 3. Five hosted agents, one per trust boundary, hosting ten roles · Accepted

- **Decision.** `study`, `investigate`, `skeptic`, `diplomat`, `engineer` as Foundry hosted agents built with Agent Framework 1.0, zip-deployed, small, with a short idle timeout and one session per workflow run. The Engineer alone holds propose tools and never sees free text.
- **Instead of.** One hosted agent per role (idle tails, ten deployments); one agent for everything (no separation); prompt agents (the hub's bring-your-own-model route is Chat Completions only), so hosted or prompt is chosen by capability.
- **Cost · security · reversibility.** Fewer idle hours · identities follow trust boundaries · high (a role can move into its own agent if testing finds an injection path).

## 4. The Citadel hub is the only door to models and tools; one contract per hosted agent · Accepted

- **Decision.** Contracts `study`, `investigate`, `skeptic`, `diplomat`, `engineer`, `evaluation`, each in dev and prod. Identity is the agent's Entra token; the key Citadel requires is a secret, not identity. Hard token quotas per contract.
- **Instead of.** Direct model access; the Foundry portal gateway; the new `aigateways` product (preview, no feature parity); one shared contract (a leaked key or forged header becomes the whole estate).
- **Cost · security · reversibility.** The hub is shared platform cost; an organisation without one budgets the accelerator ([cost](10-cost-and-finops.md)) · strongest single control · contracts are code, so moving gateways re-implements three contract types.

## 5. Models are chosen by alias; the judge is another family · Accepted

- **Decision.** Aliases `triage`, `reason`, `judge`, `embed`, `batch`. Escalate on objective signals, never on self-reported confidence. Resolved version, protocol and processing location are pinned per alias. The initial mapping is settled by evaluation (P10).
- **Instead of.** Naming models in agent code.
- **Cost · security · reversibility.** A cheaper tier can replace a dearer one without code change · estate data stays in the adopter's data boundary · high.

## 6. The Atlas lives in Git and is served from AI Search; humans merge · Accepted

- **Decision.** Claims, profiles, Detectors and Action templates are files; agents propose by pull request from a fork, so a person merges, never automatically; a claim can never fill an Action parameter; a release rebuilds the index. One AI Search Basic service.
- **Instead of.** Vector stores inside agents; Foundry Memory (preview, no virtual-network support); a wiki.
- **Cost · security · reversibility.** One search unit is the main fixed knowledge cost · a poisoned claim needs a human to merge it · high. AI Search Serverless and Foundry IQ are evaluated under P5.

## 7. Estate knowledge in Cosmos DB serverless; the audit log holds ids, never names · Accepted

- **Decision.** Our own account; approvals and credentials written only by the approval service; one open plan per resource. Immutable blob for the audit log, ids and hashes only. [Preferences](05-data-and-integrations.md#8-privacy-retention-and-recovery) are one record per directory object id; a person can export or delete theirs and their own Lessons.
- **Instead of.** Sharing Foundry's agent-state store (blast radius); SQL or a graph database (not needed).
- **Cost · security · reversibility.** Pay per use · separation of writers, erasure possible · medium (a provisioned-throughput switch exists for very large estates).

## 8. Cost data: FOCUS exports to Blob, DuckDB in the `tools` app · Accepted

- **Decision.** Manifest-based replacement ingestion; where the agreement offers no FOCUS export, the Cost Details, Usage Details or Query API fills the same layout; billed and effective cost kept apart; monthly reconciliation. DuckDB (MIT) is the one non-Microsoft engine.
- **Instead of.** Azure Data Explorer, Fabric, Databricks, FinOps hubs: more engine than phase-1 volumes need; P4 measures the volume at which one would pay for itself.
- **Cost · security · reversibility.** Storage only · no standing cluster to secure · high (adapters).

## 9. Tools are HTTPS APIs published through the hub as MCP; structured fields only · Accepted

- **Decision.** Free text reaches agents only as a screened, length-capped `untrusted_excerpt`. Our own typed `estate-read` is the default read tool; Azure MCP Server 3.0 is an optional extra settled by P9. Tools are pinned and `tools/list` drift is rejected.
- **Instead of.** Self-hosted MCP servers on Functions (preview: a switch; the MCP tool trigger is generally available); passing raw tool output into prompts.
- **Cost · security · reversibility.** Small · cuts the shortest injection paths · high.

## 10. The action plane is the only writer and fails closed · Accepted

- **Decision.** Catalogue → plan → approval → runner → verifier → audit. Any mismatch aborts; the runner never refreshes and proceeds. Idempotent runs; a purchase is never retried automatically.
- **Instead of.** Letting agents run commands; "refresh and proceed".
- **Cost · security · reversibility.** Runner cost is small · the control that matters most · the catalogue grows by pull request.
- **Superseded in part** by [decision 24](#24-a-change-runs-as-the-approver-meternaut-holds-no-right-to-change-azure--accepted) on 2026-11-05.

## 11. Approval is a bound, displayed, single-use authorization · Accepted

- **Decision.** The approval service renders the canonical plan; cards carry an opaque id; the record binds plan hash, etags, quote, approver id and role, and the authentication claim; consumed once, through a create-only item that only the runner can write. The approver comes from the approver's own token, never from the bot. Purchases need two distinct directory roles. Credentials (autopilot) are policies evaluated in code on facts the model cannot set, never for purchases.
- **Limits and undo.** One-tap approvals are [capped at five per approver per day](06-security-and-governance.md#approval-classes) (a starting value), and one alarm catches an approval with no card tap or page sign-in behind it (a stolen signed-in session escapes it). Only an R1 change rolls back by itself on a failed check; for R2 and R3 the approver restores with a [rollback grant](05-data-and-integrations.md#7-the-approval-record), usable once; a purchase cannot be undone.
- **Instead of.** Trusting a row plus a card; tags or lessons deciding scope.
- **Cost · security · reversibility.** Small · closes replay, swap and confused-deputy paths · signing the record is a later hardening.
- **Superseded in part** by [decision 24](#24-a-change-runs-as-the-approver-meternaut-holds-no-right-to-change-azure--accepted).

## 12. Runner roles per action family; no standing purchase role · Accepted

- **Decision.** One narrow custom role per action family at scopes the organisation opts in. Purchases: a role assignment with an end time, created and removed by the approval service and bound to a stored quote; alarms disable the identity. Where the identity cannot buy, the same approved quote goes as a request to [whoever can buy](14-agreements-and-access.md#four-purchase-paths). P8 settles propagation and revocation.
- **Instead of.** One broad role; a standing purchaser.
- **Cost · security · reversibility.** Role assignments are free · limits blast radius; a compromised runner can still perform its family's actions in opted-in scopes · high.
- **Superseded in part** by [decision 24](#24-a-change-runs-as-the-approver-meternaut-holds-no-right-to-change-azure--accepted).

## 13. Agents draft, workflows send; recipients come from the directory · Accepted

- **Decision.** A model never chooses or supplies a recipient or a link; free text never approves. Teams cards use the Agents SDK in .NET or JavaScript, in a small `bot` app that validates the Bot Framework token; Azure Bot Service offers no IP allow-list, so token validation is the control. Email uses an app-only mailbox with a recipient allow-list; Azure Communication Services Email is not used. Cards go only to members of the directory; outsiders get plain-text e-mail.
- **Instead of.** Agents sending messages; approval by reply.
- **Cost · security · reversibility.** Small · stops exfiltration by mail and forged approvals · high.

## 14. Two profiles; Operate uses platform-managed Foundry data · Accepted

- **Decision.** Evaluate (synthetic data, public with Entra sign-in, no production roles) and Operate (bring-your-own virtual network, platform-managed agent data, private endpoints).
- **Instead of.** Bring-your-own Cosmos DB, Storage and Search for Foundry by default (adds endpoints and stores; available as a parameter).
- **Cost · security · reversibility.** Dev costs little · dev cannot reach prod, tested · a one-way door per account (a profile change is a new account).

## 15. Evaluation in three tiers; learning shown by frozen versus updated memory · Accepted

- **Decision.** Zero-LLM checks on every pull request; LLM suites on change, on Flex where it is available (preview; Global Standard otherwise); sampled production scoring and safety suites before each autonomy level. Only the source-verified rows of the [cost-trap bank](../research/cost-trap-bank.md) become gold, adjudicated by a person; sealed rotating test sets.
- **Instead of.** Full suites on every change; a judge as truth.
- **Cost · security · reversibility.** The main variable cost of the Evaluate profile ([cost](10-cost-and-finops.md)) · red team gates autonomy · high ([evaluation](08-testing-and-evaluation.md)).

## 16. Drift controls name their check, interval, owner and response · Accepted

- **Decision.** Every kind of drift has a check, an interval, an owner and a fail-closed response ([drift](07-safeguards-and-drift.md)).
- **Instead of.** A list of things to watch.
- **Cost · security · reversibility.** Small · catches silent loosening · high.

## 17. Learning never provisions anything just to measure it · Accepted

- **Decision.** Learning comes from documents, price lists, schemas, release notes, bills, replays, owners' answers and small owner-approved reversible trials. Known limit: a meter nobody has used cannot be discovered this way, so advice about a new service is labelled.
- **Instead of.** A budget-capped sandbox subscription running billing experiments (spends money to learn what money is spent on; needs its own governance).
- **Cost · security · reversibility.** No sandbox spend · no sandbox estate to secure · a trial can still move the bill of the one resource it changes · reversible: an organisation that wants experiments can add its own environment later ([knowledge](04-knowledge-and-learning.md)).

## 18. Cost is a design constraint · Accepted

- **Decision.** Scale to zero; Detectors for cheap leads; small model first; Batch and Flex for non-urgent work; evaluation on change plus sampling; one Key Vault, one AI Search, no container registry; the solution watches its own bill.
- **Cost · security · reversibility.** The [idle floor](10-cost-and-finops.md) is the fixed cost that remains · quotas double as safety limits · high.

## 19. Licences and non-Microsoft parts are listed, not presumed · Accepted

- **Decision.** [Goals and scope](01-goals-and-scope.md) lists what each feature needs; [the register](11-technology-register.md) lists non-Microsoft parts with a Microsoft alternative.
- **Cost · security · reversibility.** n/a · no hidden dependency · high.

## 20. Single-tenant; one organisation, many subscriptions · Accepted

- **Decision.** Multi-tenant or service-provider operation is out of scope until at least phase 5.
- **Instead of.** Designing tenancy boundaries now.
- **Cost · security · reversibility.** Simpler everything · no cross-tenant data path · high.

## 21. Each scope's agreement and access are probed, and the system adapts · Accepted

- **Decision.** For every scope the Estate refresh workflow runs read-only probes for the agreement family, the cost reach (billing, subscription, none), the cost data path, the price basis and the purchase path; it stores a capability profile and probes again weekly and after any 401 or 403. Every number names the [prices it rests on](14-agreements-and-access.md).
- **Instead of.** Assuming one agreement and full billing access; asking an administrator to enter the agreement type by hand (it goes stale and is often wrong).
- **Cost · security · reversibility.** A few read-only calls per scope a week · no scope is asked for more access than a question needs, and one scope's data never reaches another's · high.

## 22. Coverage routing replaces escalation up a management line; the attention budget is code · Accepted

- **Decision.** A waiting Case is [reminded once, then parked](03-agents-and-workflows.md#4-seven-workflows); cover (the owner's delegate, else the custodian queue) is asked to confirm ownership. [Code counts unprompted messages per person](05-data-and-integrations.md#6-channels); humans set the ceilings.
- **Cost · security · reversibility.** A custodian queue to staff · no message says that someone did not answer; routing authorises nothing · easy: starting values.

## 23. Every card has one page and one verb contract · Accepted

- **Decision.** [A request's page](05-data-and-integrations.md#6-channels) shows the exact plan for a decision and the card's own words otherwise, and opening it records nothing; [the card manifest](05-data-and-integrations.md#7-the-approval-record) lists, for each verb, who may tap, what a repeat does and what a tap returns.
- **Instead of.** Buttons that carry the plan.
- **Cost · security · reversibility.** Pages run in the `approvals` app · a forwarded or repeated tap does no harm · moderate: the routes are the contract.

## 24. A change runs as the approver; Meternaut holds no right to change Azure · Accepted

- **Decision.** Decided on 2026-11-05 ([proposal 05](../proposals/05-run-as-the-approver.md)). Approving a plan sends the approver to Microsoft Entra to sign in for the delegated scope `https://management.azure.com/user_impersonation` (authorization code flow with PKCE, no refresh token). The managed identity's federated assertion redeems the code, so there is no secret. The token lives in memory for the one request, and Azure's Activity Log shows the approver as the caller.
- **Reason.** The product's owner, on a tool identity that holds write rights: "NOT A SINGLE CUSTOMER WILL DO THAT". The runner's role was narrow but standing, and each new kind of change would widen it. [Well-Architected SE:05](https://learn.microsoft.com/azure/well-architected/security/identity-access) asks for access just in time and just enough, and [Microsoft cloud security benchmark PA-2](https://learn.microsoft.com/security/benchmark/azure/mcsb-v2-privileged-access) asks to avoid standing access.
- **Supersedes.** In part: decisions 10 and 12, and the runner, Credentials and automatic rollback in decision 11.
- **Consequences.** The approver needs the right in Azure, and Azure's own checks apply. A Teams card cannot carry an Azure token, so it can only open the page where the person signs in. A purchase or a scheduled change needs the approver's sign-in at the moment of the change, so a change at a set time cannot run unattended.
- **Cost · security · reversibility.** One consent instead of a role at each scope · Meternaut holds no right to change Azure · medium: a change that must run without a person needs a new design.
