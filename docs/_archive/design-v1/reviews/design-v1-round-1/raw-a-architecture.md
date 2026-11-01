# Round 1 - lens A (architecture) - raw report

> Reviewed at commit `20390d4` · model `gpt-6.1-sol` · saved as returned by the reviewer (this header added). Orchestrator spot-checks and the disposition of every finding: [disposition.md](disposition.md).

## 1. Verdict — five lines

Direction: sound; the deployment and authority contracts are not yet build-ready.  
Keep the deterministic spine, specialist leaves and human-gated execution.  
The blocking seams are gateway invocation, privilege, durability and recovery—not insufficient AI.  
Assumption: one EU tenant, a shared landing-zone hub and a business-hours Pilot; no deployed behaviour is claimed.  
Must change: make one call/capability/topology contract authoritative across the design, then prove a fail-closed walking skeleton.

## 2. Findings

Read all specified design documents, the five research studies, the north star, AGENTS and the standing brief. Vendor pages below were fetched during this review on 31 October 2026. Tenant permissions, private-repository entitlements, the selected EU judge and live gateway interoperability remain **UNVERIFIED**. Documentation checks failed only for the acknowledged missing prices research; that defect is excluded.

### A-01 — The spine-to-leaf path contradicts the gateway boundary
**Critical · File and heading:** `<repo>\docs\design\05-agents-and-orchestration.md` §1 The pattern: a deterministic spine with agentic leaves; §4 How the spine runs.  
**Quote:** “the spine calls the hosted agent's endpoint under its own managed identity”.  
**Why it matters:** `<repo>\docs\design\07-security-architecture.md` §2 instead says “the only reachable internal destination is the governance hub”; §12 retains A2A controls. `<repo>\docs\design\03-logical-architecture.md` §4 depicts agent handoffs, while 05 forbids them. The prescribed invocation path bypasses the required hub; typed notes remain an injection-propagation path.  
**Fix:** Diagram spine → gateway → leaf → gateway → services. Publish an authenticated invocation proxy without A2A; test that edge alongside model bypass.

### A-02 — Fifteen identities are described as fourteen
**Major · File and heading:** `<repo>\docs\design\05-agents-and-orchestration.md` §2 The roster.  
**Quote:** “Fourteen agents, deployed as **hosted agents** in Foundry Agent Service, in nine groups.”  
**Why it matters:** The table has **15** entries: the Librarian split adds one to fourteen. Identity counts, manifests, sponsors and sizing disagree. Nine groups need not mean nine projects in every account.  
**Fix:** Generate one inventory distinguishing logical roles, identities, projects and environments; correct counts from it. Preserve specialist roles without empty deployments.

### A-03 — Published capabilities cannot execute the workflows
**Major · File and heading:** `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.4 The publish contract: tools, and who may call them.  
**Quote:** “`ledger` | our service | read”.  
**Why it matters:** Except for experiments, prediction writes lack a path. Case-notebook/Estate Model writes, the Consequence engine and roster-required repository/PR operations are absent. A job-backed query needs a request/result bridge. Direct-store permissions would violate the boundary.  
**Fix:** Complete caller/action/data-class permissions, including draft writes and repository operations. Specify HTTP/MCP facades, asynchronous result IDs and service-side authorisation—not prompt-implied permissions.

### A-04 — The execution network boundary is not deployed
**Major · File and heading:** `<repo>\docs\design\07-security-architecture.md` §2 Trust zones, physically.  
**Quote:** “its own subnet; reachable only from the Approval service; **no model call inside this zone**”.  
**Why it matters:** `<repo>\docs\design\04-landing-zone-and-citadel.md` §6 puts “tool services, Approval, Policy, Brief, jobs” in one ACA environment/subnet. Z1 needs Key Vault access despite the hub-only destination claim.  
**Fix:** Name the execution environment/subnet, ingress, identities and routed firewall paths; enumerate bootstrap/telemetry exceptions. Test the topology, not zone labels.

### A-05 — The broker both grants and exercises authority
**Critical · File and heading:** `<repo>\docs\design\07-security-architecture.md` §3.3 The execution identity: just-in-time, without PIM.  
**Quote:** “If the sweeper, the broker and the alert all fail, an unused role assignment still cannot be exercised by anyone”.  
**Why it matters:** The broker grants roles and starts the identity-bearing job. Start can override the execution template: broker compromise bypasses its own approval check before any sweeper. Claimed independent barriers collapse.  
**Fix:** Separate grants from independently validating dispatch; constrain execution artefacts and test template overrides. Broker-local checks are not independent boundaries.  
**Vendor:** https://learn.microsoft.com/en-us/azure/container-apps/jobs — “The container can also use any managed identity”.

### A-06 — Onboarding omits action and deployment authority
**Major · File and heading:** `<repo>\docs\design\11-delivery-and-operations.md` §6 Onboarding and offboarding an estate.  
**Quote:** “**Reader, Cost Management Reader and Monitoring Reader**, nothing else”.  
**Why it matters:** Estate-side constrained delegation to the broker is not provisioned. `<repo>\docs\design\07-security-architecture.md` §3.1 grants release identities RG-scoped Contributor, while foundation stacks/policies operate above that scope.  
**Fix:** Separate privileged bootstrap, read onboarding and consented action onboarding. Enumerate assignment, stack-deny, Graph and billing authority and revocation owners.  
**Vendor:** https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deployment-stacks — Azure Deployment Stack Contributor: “Users can manage deployment stacks, but can't create or delete deny-assignments within the deployment stacks.”

### A-07 — Permission expiry is not identity expiry or immediate revocation
**Major · File and heading:** `<repo>\docs\design\07-security-architecture.md` §3.1 Who has an identity and §3.3.  
**Quote:** “user-assigned managed identities, one per *Move class*”.  
**Why it matters:** Persistent class identities replace per-Move identities. Reuse needs serialization; removing assignments does not prove access stopped. Purchase windows and kill switches must accommodate propagation.  
**Fix:** Specify class/resource leases, activation/revocation probes, bounded execution windows and quarantine before reuse; describe short-lived *estate permissions* honestly.  
**Vendor:** https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting — “it can take up to 10 minutes for changes to take effect.”

### A-08 — Estimated quotas are presented as hard financial caps
**Critical · File and heading:** `<repo>\docs\design\04-landing-zone-and-citadel.md` §3.4 Hardening the defaults.  
**Quote:** “**true**, so token limits are hard budgets”.  
**Why it matters:** Concurrent completions can overshoot. Tokens are not euros across models, cache charges, tools and compute. Caller-supplied agent headers cannot secure per-agent budgets. The denial-of-wallet barrier is overstated.  
**Fix:** Atomically reserve worst-case cost in the spine, authenticate ownership, bound concurrency/output/retries, and state residual overrun. APIM remains secondary.  
**Vendor:** https://learn.microsoft.com/en-us/azure/api-management/llm-token-limit-policy — “concurrent or near-concurrent requests can temporarily exceed the configured token limit.”

### A-09 — Batch is not an interchangeable interactive alias
**Major · File and heading:** `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.2 The alias map.  
**Quote:** “Flex or Batch deployment → interactive alias”.  
**Why it matters:** Batch needs submission, result collection and cancellation, not ordinary response fallback. Claude-to-EU-judge fallback needs a proven common wire protocol. Contract portability does not erase runtime differences.  
**Fix:** Separate interactive/Flex aliases from a batch adapter/lifecycle. Test each fallback's protocol, identity, residency and accounting.  
**Vendor:** https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/batch — “It processes asynchronous groups of requests with separate quota”.

### A-10 — Custom durability is chosen against the wrong alternative
**Major · File and heading:** `<repo>\docs\design\05-agents-and-orchestration.md` §4 How the spine runs.  
**Quote:** “One execution advances a workflow instance to its next wait, checkpoints, and exits.”  
**Why it matters:** Checkpoints do not solve acknowledgements, signal atomicity, duplicate dispatch, timers or crash-after-effect reconciliation. The prerelease MAF Durable Extension is not the only Microsoft alternative.  
**Fix:** Compare ordinary Durable Functions calling hosted leaves against custom queues/checkpoints. Keep MAF within leaves; prove exactly-once *effects*, not record deduplication.  
**Vendor:** https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-overview — “The Durable Functions runtime manages state, checkpoints, retries, and recovery”.

### A-11 — The analytics exception rests on false exclusivity
**Major · File and heading:** `<repo>\docs\design\13-decisions.md` ADR-13 Cost analytics is Parquet and an embedded engine in a job.  
**Quote:** “All are Microsoft-only and all cost more at rest.”  
**Why it matters:** Synapse serverless SQL reserves no chargeable idle compute. DuckDB may win on simplicity or measured queries, but the reason for breaking C1 is invalid.  
**Fix:** Compare network, query and operational costs; obtain an approved exception with owner and expiry if DuckDB wins. Replace the idle-cost assertion with evidence.  
**Vendor:** https://learn.microsoft.com/en-us/azure/synapse-analytics/sql/on-demand-workspace-overview — “There's no charge for resources reserved.”

### A-12 — Recovery can resurrect data and lacks regional reachability
**Major · File and heading:** `<repo>\docs\design\06-data-and-knowledge.md` §7.6 Recovery.  
**Quote:** “**hourly change-feed export** to the immutable lake”.  
**Why it matters:** Default feed misses deletes/intermediate versions; replay can resurrect erased lessons. Checkpoint/dispatch reconciliation is omitted. `<repo>\docs\design\11-delivery-and-operations.md` §8 makes the export lake zone-redundant in the same region: redeployment elsewhere does not make it reachable.  
**Fix:** Define tombstones/snapshots, watermarks and restore ordering, preserve revocations, invalidate uncertain approvals, and keep independently reachable EU backups. Drill regional failure.  
**Vendor:** https://learn.microsoft.com/en-us/azure/cosmos-db/change-feed-modes — “Deletes aren't captured as changes”.

### A-13 — GitHub environments do not enforce two reviewers
**Critical · File and heading:** `<repo>\docs\design\11-delivery-and-operations.md` §3 Pipelines.  
**Quote:** “**two reviewers, neither the author**”.  
**Why it matters:** Listing two permits one approval. Private-repository entitlement is **UNVERIFIED**; no GitHub plan is assumed. The deployment gate is not an enforceable specified control.  
**Fix:** Independently check two-person approval, prevent self-review/bypass, and verify private-repository support before foundation deployment.  
**Vendor:** https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments — “Only one of the required reviewers needs to approve the job for it to proceed.”

### A-14 — GA hosting does not make its integration GA
**Major · File and heading:** `<repo>\docs\design\05-agents-and-orchestration.md` §5 Anatomy of a leaf.  
**Quote:** “**Python**, Agent Framework 1.x pinned”.  
**Why it matters:** Normal Python hosting integration is prerelease, absent from `<repo>\docs\design\09-safeguards-and-drift-controls.md` §5. Service/core-framework GA is insufficient.  
**Fix:** Name entrypoint/packages; register the integration with a tested framework-agnostic hosted endpoint fallback, or prove it is unused.  
**Vendor:** https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent — “The Python `agent-framework-foundry-hosting` integration is prerelease.”

### A-15 — Minute-scale estate alerts have no fast path
**Major · File and heading:** `<repo>\docs\design\01-requirements-and-principles.md` §4 Quality targets.  
**Quote:** “a fast-signal alert reaches an owner within minutes.”  
**Why it matters:** `<repo>\docs\design\05-agents-and-orchestration.md` §3 polls estates hourly; continuous self-watch concerns the platform. No estate fast-signal path answers this target. Enterprise throughput/cold-start budgets are unallocated.  
**Fix:** Specify event → queue → bounded analysis → owner delivery, or change the target. Load-test subscription throttling, session/IP headroom and p95 latency.

### A-16 — Purchase fallback violates the execution rule
**Major · File and heading:** `<repo>\docs\design\14-next-phases.md` §3 Spike register, S-ACT-1.  
**Quote:** “human-executed purchase until solved”.  
**Why it matters:** `<repo>\AGENTS.md` rule 10 requires AI preparation, two named human approvals and AI execution. A failed seam cannot replace the operating model.  
**Fix:** Disable purchases until agreement-specific AI execution is proven; retain proposals and human approvals, not a manual executor.

### A-17 — Completion status and a spike reference disagree
**Minor · File and heading:** `<repo>\docs\design\README.md` How it was reviewed.  
**Quote:** “went through **two rubber-duck rounds with different model families on each lens**”.  
**Why it matters:** All 37 ADRs in `<repo>\docs\design\13-decisions.md` Decisions remain Proposed. `<repo>\docs\design\12-cost-and-finops.md` §5 assigns Terra comparison to S-MOD-1; `<repo>\docs\design\14-next-phases.md` §3 assigns it to EU judges.  
**Fix:** Describe reviews as underway; assign distinct experiments stable references. No other broken anchors were found beyond the excluded prices link.

### A-18 — Private networking does not mandate the full BYO data tier
**Major · File and heading:** `<repo>\docs\design\04-landing-zone-and-citadel.md` §7 The Foundry layout.  
**Quote:** “network-isolated agents need it”.  
**Why it matters:** Current networking guidance supports BYO-VNet with platform-managed data. Standard setup may still be right for sovereignty, but networking alone does not justify repeating its stores across hosted-only accounts. The operational store and Atlas remain separate requirements. Platform-managed data residency here is **UNVERIFIED**.  
**Fix:** Extend S-NET-2 beyond dev; compare supported production layouts and record the actual sovereignty driver before duplicating stores.  
**Vendor:** https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/networking-options — “With BYO virtual network, you can bring your own data resources or use platform-managed data resources.”

## 3. Decision table

Each row cites its unique ADR heading in `<repo>\docs\design\13-decisions.md`. Confidence: **H** high, **M** medium; architectural judgment, not untested seams. Alternatives challenge the rejection, not merely restate it.

| ADR | Verdict | Confidence | Strongest alternative and rejection judgment | What would change my mind |
|---|---|---|---|---|
| 01 | Agree with changes | H | Bounded handoffs: fluid, but weaker boundaries are not justified. | Typed records materially damage measured collaboration quality. |
| 02 | Agree with changes | H | Thin native APIM/Citadel: less fork surface; rejection needs specific contract benefits. | Accelerator fails private/authentication tests or maintainability targets. |
| 03 | Agree with changes | H | One subscription/RGs: smaller, but shared policy/quota blast radius justifies separation. | Pilot footprint exceeds value without isolation benefit. |
| 04 | Agree with changes | M | Hub's region: fewer seams; unused preview features should not dictate geography. | Required endpoint/model tests favour another region. |
| 05 | Agree | H | Managed VNet: less IP work; owned egress makes BYO defensible. | Routing, logging or capacity cannot be operated reliably. |
| 06 | Agree with changes | H | Fewer projects retaining identities/contracts: simpler; nine projects are not proven necessary. | Isolation tests require every physical split. |
| 07 | Disagree | H | Grant-only broker/independent dispatch: unexamined, removes combined authority. | Compromised broker cannot exercise unauthorised grants/template overrides. |
| 08 | Agree with changes | H | Web-only approvals: simpler bootstrap; cards need proven binding. | Replay, entitlement and fresh-authentication channel tests pass. |
| 09 | Agree with changes | H | Regional-only routing: clearer locality; reject on verified availability/cost. | Alias, batch and fallback protocols pass end-to-end tests. |
| 10 | Agree with changes | H | Deterministic checks/same-family judge: viable; family diversity alone is insufficient. | Named EU judge demonstrates error diversity against humans. |
| 11 | Agree | H | Database/Git mirror: viable, but dual truth adds needless synchronization. | Release/index rebuild throughput becomes a bottleneck. |
| 12 | Agree with changes | M | SQL serverless: transactional alternative; do not dismiss before nonce/recovery proof. | Cosmos atomicity, deletion replay and capacity meet objectives. |
| 13 | Disagree | H | Synapse serverless: idle-compute rejection is wrong. | Total cost/effort favours DuckDB; C1 exception approved. |
| 14 | Agree | H | Managed memory: convenient, but second memory authority is unnecessary. | Private/governed retrieval materially improves held-out exams. |
| 15 | Agree with changes | H | Typed HTTP/APIM: simpler for tiny services; MCP must earn protocol work. | Discovery improves without reliability regressions. |
| 16 | Agree with changes | M | Shared capped Lab: sensible Pilot alternative; vending needs isolation justification. | RG isolation/attribution tests fail. |
| 17 | Agree with changes | H | Web/email: least channel work; Teams justified by owner outcomes. | Binding and attention-benefit tests pass. |
| 18 | Agree with changes | H | Narrow analytics telemetry: simpler baseline; cheap plans must preserve detections. | Required queries/alerts work within chosen table budgets. |
| 19 | Agree with changes | H | Minimal in-house gate: smaller trusted surface; keep as baseline. | Toolkit/labels measurably improve attack resistance without false assurances. |
| 20 | Agree | H | Every paid control: broader, but absent entitlement/value cannot justify defaults. | Licensed controls close a demonstrated attack gap. |
| 21 | Agree with changes | H | Policy/manifest diff: simpler, insufficient for world/behaviour drift. | Correction identities and independent heartbeat drills succeed. |
| 22 | Agree with changes | M | Own harness: fewer gateway ambiguities; managed evaluators must prove routing. | Judge/attacker calls are governed; exam independence survives. |
| 23 | Agree with changes | H | Azure DevOps/Bicep: viable sample path; GitHub preference reasonable, assumed gate not. | Bootstrap or private-runner/reviewer support fails. |
| 24 | Agree with changes | H | CMK on classified stores: reject for absent driver, not HSM necessity. | Concrete revocation requirement warrants operational burden. |
| 25 | Agree | H | Regional-only: stricter locality; approved EU scope is proportionate. | Processing terms conflict with the organisation's boundary. |
| 26 | Agree with changes | H | Euro reservation plus quotas: stronger than estimation; unexamined. | Worst-case concurrent overspend stays inside approved bounds. |
| 27 | Agree with changes | M | Human runbooks before SRE Agent: simpler independent baseline; trial against it. | Incident benefit and Citadel-compatible governance justify adoption. |
| 28 | Agree with changes | M | Separate Atlas/code repositories: stronger merge boundary; monorepo needs equivalent controls. | Contributor-isolation and release tests prove equivalence. |
| 29 | Agree with changes | H | Independent assessment/control code: templates alone solve neither accountability nor applicability. | Legal scope, organisational controls and owners confirmed. |
| 30 | Agree with changes | H | Cold EU backups/target: stronger than same-region replay without warm compute. | Regional restore meets objectives and invalidates uncertain approvals. |
| 31 | Agree with changes | H | Retained release bundles: pins cannot preserve retired dependencies. | Previous release survives retirement and schema changes. |
| 32 | Agree with changes | M | SQL ledger: less custom chaining; Blob advantage needs concurrent-write proof. | Ordering, protected appends, signing and audit-failure drills pass. |
| 33 | Disagree | H | Ordinary Durable Functions: not prerelease MAF adapter; custom runtime ownership unproven. | Custom spine proves simpler and equally reliable under faults. |
| 34 | Agree | H | Routines: less scheduling code; rejection reasonable until envelope control proved. | Authenticated budgets/deadlines and governed invocation are preserved. |
| 35 | Agree with changes | M | Existing hub required: narrower support; optional thin hub must prove maintainability. | Trimming preserves controls/upgrades at measured cost. |
| 36 | Agree | H | Single language: fewer toolchains; concrete SDK/test gaps justify split. | One-language services meet integration/assurance needs with less effort. |
| 37 | Agree | H | Hosted-process execution: simpler, but shared agent identity defeats isolation. | Credential, filesystem and egress separation proves equivalent. |

## 4. What is strong — keep

Keep the Librarian split, proposals distinct from approvals, independent scoring, evidence-bearing knowledge releases, receipts/counterfactuals, typed interfaces and reversible-first rollout. Share Citadel rather than clone it per workload. Preserve the logical cast, not unnecessary physical boundaries. These are strengths, not proof of implementation.

Small-team alignment: https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/principles — “Take advantage of centralized operations teams”.

## 5. What is missing — five priorities

1. **Edge inventory:** caller, endpoint/protocol, identity, data class, permitted writes, firewall path and trace correlation.
2. **Transactional actions:** approval consumption, target concurrency, dispatch/outbox, grant/revoke verification and uncertain-effect reconciliation.
3. **Failure-domain recovery:** independent monitoring, regional data reachability, deletion/revocation replay and approval invalidation.
4. **Capacity/latency budgets:** fast signals, queue age, cold starts, subscription throttling and subnet rollout headroom.
5. **Operable Pilot:** exact deployed units, bootstrap/release authority, licensed gates and maintenance effort before every physical split.
