# Design phase 1 — Round 1 disposition

**Reviewed at commit `20390d4`** (the draft of all fourteen design documents, the research and the tools; `git show 20390d4:docs/design/<file>` reproduces what the reviewers read). Five lenses, each on a different model family; every reviewer wrote its own raw report, saved unedited next to this file.

| Lens | Model | Raw report | Findings | ADR verdicts |
|---|---|---|---|---|
| **A** Architecture | gpt-6.1-sol | [raw-a-architecture](raw-a-architecture.md) | 18 (4 Critical, 13 Major, 1 Minor) | 3 Disagree (ADR-07, 13, 33), 24 Agree with changes, 10 Agree |
| **B** Security, safety, compliance | gemini-4-argon | [raw-b-security](raw-b-security.md) | 17 (5 Critical, 9 Major, 3 Minor) | 17 Agree with changes, 20 Agree |
| **C** Cost and operability | grok-4.7 | [raw-c-cost-ops](raw-c-cost-ops.md) | 8 (all Major or Minor); 5 hand-checked numbers all matched | 6 Agree with changes, 31 Agree |
| **D** AI engineering, evaluation, drift | gpt-6-sol | [raw-d-ai-engineering](raw-d-ai-engineering.md) | 14 (1 Critical, 13 Major) | 25 Agree with changes, 12 Agree |
| **E** Platform fact-check | gpt-5.6-sol | [raw-e-platform-factcheck](raw-e-platform-factcheck.md) | 20 (13 errors or over-generalisations, 7 confirmed correct) | 10 premises challenged |

**Outcome in one paragraph.** The reviewers agreed that the *direction* is sound — read-only reasoning, a deterministic execution boundary, approvals bound to a target, the preview register, the retirement calendar — and independently found the same **seams**: the authority chain around the credential broker; the contract boundaries at the hub (data class and per-agent authorisation); the gateway path from the spine to a leaf; untrusted text entering through tools other than the Document reader; a CI path that agent-authored pull requests could poison; the audit ledger's platform limits; a cost model that did not match the layout it describes; release gates without statistical definitions; and about a dozen platform statements that were wrong, outdated or over-general. **Almost every finding was accepted.** The three substantive reversals are ADR-33 (the spine moves to Durable Functions), ADR-07 (the broker no longer grants *and* dispatches) and the foundation of the Foundry layout (two projects per account, not nine).

## 1. Orchestrator spot-checks

Reviewer-cited facts were re-checked against their primary source before they drove a change. All of these held:

| Claim (reviewer) | Check | Result |
|---|---|---|
| The Python Microsoft 365 Agents SDK exposes `Action.Execute` handlers (E-02) | Learn Python API reference, `AdaptiveCard.action_execute`: "Register an `Action.Execute` handler that receives the action data." | **Our claim was wrong** — corrected |
| `llm-content-safety` supports MCP and A2A requests *and responses*, with a sliding-window buffer for streams (E-04) | Learn policy page: "The policy can also enforce content safety checks on requests or responses for MCP tools or A2A Agent APIs"; "the stream handler buffers events in a sliding window" | **Our streaming caveat was wrong for this policy.** Separately, MCP server pages say *custom* policies must not read `context.Response.Body` — both statements are now in the design |
| Native APIM MCP policies apply to all tools of a server (E-03) | Learn MCP overview: "Currently, policies apply to all API operations exposed as tools in the MCP server." | **Our "per-tool allow-lists" fallback was over-general** — corrected |
| Standard setup provisions five Cosmos DB containers per project, each 1,000 RU/s; serverless is supported (E-07) | Learn standard-agent-setup | Confirmed — drove "two projects per account" |
| Container Apps Sandboxes are generally available (D-14) | Release Communications record 561262: `"generalAvailabilityDate":"2026-09"`, title "Generally Available: Azure Container Apps Sandboxes" | **Our "preview" label was stale** — corrected |
| Hosted agents reached GA in June 2026, not "announced 9 July" (E-13) | Release Communications record 563596: `"generalAvailabilityDate":"2026-06"` | Corrected |
| PIM cannot create eligible assignments for applications, service principals or managed identities (D, E-15) | Learn PIM integration page | Confirmed; it does not say time-bound *active* assignments are impossible, so spike S-ID-1 stays open |
| Role-assignment delegation can constrain roles and principal types, not the target scope (B-01) | Learn "Delegate Azure role assignment management… with conditions" | Confirmed — the target scope is bounded only by where the delegate holds the role |
| `allowProtectedAppendWrites` allows appends to append blobs under a time-based policy; it cannot be changed once the policy is locked (B-09) | Learn container-level WORM page and the `ImmutabilityPolicyProperty` reference | Confirmed |
| MAF Python checkpoint stores use `pickle` for non-JSON state (D-04) | Learn Agent Framework checkpoints page | Confirmed |
| GitHub environments need only **one** of several required reviewers to approve (A-13) | GitHub documentation on deployments and environments | Confirmed |
| Groundedness *detection* retires on 30 April 2027 (E-08) | Learn Content Safety groundedness quickstart: "Groundedness detection in Azure AI Content Safety and Azure OpenAI retires on April 30, 2027" | Confirmed (the Foundry evaluator is a different product and remains) |
| An append blob holds at most 50,000 blocks (B-09) | Learn "Understanding block blobs, append blobs, and page blobs": "an append blob can include up to 50,000 blocks" | Confirmed |
| AI Search Serverless regions in Europe (E-10) | Learn "Supported regions for Azure AI Search": Serverless is marked for Denmark East, Poland Central, Sweden Central, Switzerland North and UK South — **three EU regions** | Confirmed; the same page flags **Sweden Central** as "in high demand, which prevents the creation of new search services" — **new to the design**, now a day-zero check |
| Serverless Developer takes private endpoints but no shared private links or network security perimeter (C-01) | Learn "Service limits in Azure AI Search": "doesn't support shared private links or network security perimeter (NSP) to data sources. Private Endpoints … are supported"; preview, no SLA, not recommended for production | Confirmed — the "−€65 serverless lever" is removed |
| The managed-VNet firewall for FQDN rules is Azure Firewall, Standard by default, Basic selectable (C-05) | Learn "Configure managed virtual network for Microsoft Foundry projects", Pricing | Confirmed — priced from the snapshot (Standard €803 a month plus data) |
| Durable Functions on Flex Consumption (A-10, D-04) | Learn "Durable task storage providers": Flex Consumption *fully supported* for the Durable Task Scheduler, the Azure Storage provider and MSSQL; Flex guidance: always-ready instance for the `durable` group and polling at 10 s or less | Confirmed — drove the reversal of ADR-33 |

**Not independently re-fetched** (taken on the reviewer's quoted source, marked in the changes): Claude hosting versions (E-12), the Deployment Stacks "move" bypass (E-11), the red-teaming region conflict (D-09). **Corrected from our own research instead of the reviewer** (E-06): `useTargetAzureKeyVault` — our Citadel research records the Bicep default as *true* and the README table as *false*, so the reviewer's "defaults to false" is one of two conflicting sources; the design says only that we set it explicitly to true and assert on the deployed result (to confirm on the pinned commit). Where a design statement now depends on one of these, it carries *to confirm*.

## 2. Dispositions

**Accepted** = changed as proposed. **Adjusted** = accepted with a different fix. **Not adopted** = reason given.

### 2.1 The authority chain: broker, approvals, execution identities

*A-05, A-06, A-07, A-04, B-01, B-06, B-07, B-08, B-13, ADR-07 (Disagree)*

| Finding | Disposition | Change |
|---|---|---|
| A-05 the broker grants *and* dispatches | **Accepted** | Three parties, each verifying independently: the **Approval service** signs and dispatches; the **broker** grants only after *itself* verifying the signature; the **Move runner** verifies signature, target hash and live ARM state. The broker cannot start the job; the runner image is pinned and its start accepts no template override ([07 §3.3](../../design/07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim)) |
| B-06 unsigned approvals; hash omits live state | **Accepted** | each approval is signed with a Key Vault key held only by the Approval service; the target hash includes ARM etags or configuration hashes and the policy decision id; the Auditor cross-checks approvals against Entra sign-in logs ([07 §4](../../design/07-security-architecture.md#4-approvals-that-cannot-be-forged-or-reused)) |
| B-01, A-06 estate-side delegation is not provisioned; ABAC cannot scope the target | **Accepted** | the onboarding module has two parts — *read* onboarding and a separate, consented *action* onboarding that grants the broker a **constrained** RBAC delegation (our custom Move roles only, execution identities only) at the onboarded scope, and the sweeper delete-only. The honest statement is now in [04 §3.1](../../design/04-landing-zone-and-citadel.md#31-where-things-live), [07 §3.3](../../design/07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim) and [11 §6](../../design/11-delivery-and-operations.md#6-onboarding-and-offboarding-an-estate): *the estate trusts the broker with a constrained delegation; target scoping is deterministic code plus detection, not ABAC* |
| B-08, A-07 identity per class is shared by concurrent Moves; propagation and revocation are not instant | **Accepted** | execution identities are **leased exclusively** (one active Move each, fenced); an activation probe before and a revocation probe after; quarantine before reuse; RBAC changes can take up to ten minutes, so purchase windows and kill-switch semantics say so |
| B-13 kill switches are slower than stated | **Accepted** | the kill-switch table states *what* stops *when*: contract suspension in seconds; disabling an agent identity blocks new tokens only; the execution plane stops new grants and dispatch at once and aborts in-flight Moves cooperatively; role removal can take minutes |
| B-07 approver registry poisoned through tags and replies; no fallback for step-up without Entra P1 | **Accepted** | approver standing comes only from **human-administered** Entra groups or RBAC roles on the target, never from agent-inferred ownership; step-up falls back to a code-enforced fresh sign-in with an `amr` check where authentication contexts are unlicensed |
| A-04, B-08 Z3 has no network of its own | **Accepted** | a separate internal Container Apps environment and subnet `snet-exec`; allowed paths enumerated ([04 §6](../../design/04-landing-zone-and-citadel.md#6-network)) |
| ADR-07 Disagree (A) | **Accepted** | ADR-07 rewritten; status Proposed with the changes |

### 2.2 The hub: invocation path, contracts, data class, per-agent authorisation

*A-01, A-02, A-03, B-02, B-03, B-05 (parts), E-03, E-05, E-06, E-07, A-18, A-09*

| Finding | Disposition | Change |
|---|---|---|
| A-01 the spine-to-leaf call bypasses the hub | **Accepted** | each leaf's endpoint is published through the hub as an ordinary API (not A2A); the spine's identity has **no** Foundry role except through the hub; the bypass register gains B12 ([04 §8](../../design/04-landing-zone-and-citadel.md#8-the-gateway-bypass-register)); the main-loop diagram in [03](../../design/03-logical-architecture.md) shows record hand-offs mediated by the spine |
| B-02 `govern` mixes data classes (Claude on Global, Flex) | **Accepted** | **one contract per group, data class and environment**; `govern` becomes EU-only; the Examiner moves to `examine` with a synthetic and a real-estate contract; the Engineer becomes EU-only because it reads customer source |
| B-03 shared contracts, spoofable header, over-broad tool grants | **Accepted** | `x-sub-agent-id` is *attribution only*; authorisation is by verified `azp`/`oid` through per-tool app roles assigned directly to agent identities; the Scholar (untrusted reader) and the Librarian (Atlas writer) move to separate groups (`study`, `curate`) — eleven groups |
| A-02 fifteen identities, "fourteen" agents; nine groups ≠ nine projects | **Accepted** | counts corrected everywhere: fourteen roles, **fifteen** hosted identities, eleven groups, **two** Foundry projects per account |
| E-07, A-18 five Cosmos containers per project; BYO data not mandatory | **Accepted** | two projects per account (reasoning, examination); S-NET-2 extended to production; standard setup stays the production default until it proves otherwise |
| A-03 published tools cannot execute the workflows | **Accepted** | the tool matrix gains the case-record facade, the Consequence engine, repository pull requests (data paths only), asynchronous result ids |
| A-09 Batch is not an interactive fallback | **Accepted** | `acia-batch` split from interactive aliases; phase 1 uses Flex for delay-tolerant public work; Batch needs an adapter and waits |
| E-03 native APIM MCP per-tool allow-lists | **Accepted** | fallback corrected: server-level policies; separate MCP servers by trust class |
| E-05 the portal gateway may associate an existing APIM | **Accepted** | B9 reworded; S-NET-1 tests association with the hub |
| E-06 the Citadel sample's `useTargetAzureKeyVault` default (reviewer: false; our research: Bicep true, README false) | **Adjusted** | the documented defaults conflict, so the hardening table sets it explicitly to true and asserts on the deployed result that no key-bearing output exists (to confirm on the pinned commit) |

### 2.3 Untrusted text, injection layers, protocol facts

*B-05, D-03, E-04, B-16*

| Finding | Disposition | Change |
|---|---|---|
| B-05 (1), D-03 other routes carry untrusted text | **Accepted** | layer 1 becomes a **source sanitiser** used by *every* tool service that returns free text (tags, names, invoice lines, replies, documents): delimiter escaping, control-character stripping, field-length caps, an *untrusted* label; the Document reader is its web instance |
| E-04 streaming caveat wrong for `llm-content-safety` | **Accepted** | the built-in policy screens MCP and A2A *responses* with a sliding window; **custom** policies must not read the response body; S-GW-4 confirms on our hub |
| B-05 (3, 4) 10,000-character window; `x-policy-id` header | **Accepted** | long inputs are chunked by the sanitiser; the hub strips `x-policy-id` and API-version overrides in the product policy |
| D-03 invocation-protocol moderation is inert without its setting | **Accepted** | an L5 test asserts the moderation setting exists on the *deployed protocol path* and fails closed when absent |
| B-05 (3) taint at session level | **Accepted** | once untrusted text enters a session, privileged tools require human confirmation or are blocked for that session |
| B-16 dynamic-session reuse; Commons counts from a cohort of one | **Accepted** | sessions are scoped `(group, case)`; in single-tenant mode the Commons receives **no counts** |

### 2.4 CI/CD and supply chain

*B-04, A-13, A-06, E-11*

| Finding | Disposition | Change |
|---|---|---|
| B-04 agent-authored pull requests trigger self-hosted runners with OIDC | **Accepted** | agent identities may open pull requests only to **data paths**; their workflows run on GitHub-hosted runners with no secrets and no federation; privileged workflows run from the base branch after a human approves ([11 §3](../../design/11-delivery-and-operations.md#3-pipelines), [07 §9](../../design/07-security-architecture.md#9-supply-chain)) |
| A-13 a GitHub environment does not enforce two reviewers | **Accepted** | a required check counts **two distinct approvers who are not the author**; private-repository entitlement checked (S-DEL-2); with a single operator, promotions are limited to shadow and reversible Moves until a second reviewer exists |
| E-11 moving a managed resource removes stack protection | **Accepted** | detection of resource moves, a planted-drift test, a documented lock procedure |

### 2.5 Data, ledger, recovery, lessons, Lab

*B-09, A-12, B-10, B-11, B-14, B-15, B-17*

| Finding | Disposition | Change |
|---|---|---|
| B-09 ledger limits and chain races | **Accepted** | a single **Audit Writer** sequences entries; blobs roll over before the 50,000-block limit; `allowProtectedAppendWrites` is set *before* locking; each approval and execution entry is signed |
| A-12 recovery can resurrect erased data; the export lake is not independently reachable | **Accepted** | snapshots and tombstones; restore ordering; revocations preserved; approvals older than the restore point invalidated; a geo-redundant secondary for reachability |
| B-10 autonomous lessons | **Accepted** | a lesson is *draft* until an owner confirms it by an authenticated action; drafts are never instructions to an acting agent |
| B-11 unattended Lab deploys | **Accepted** | the Experimenter *plans*; a deterministic Lab controller deploys only **signed recipes** within a pre-deploy cost cap from the price engine; new recipes are reviewed |
| B-14 PII bypass; Art. 22 and erasure wording | **Adjusted** | PII is pseudonymised in tool services before the hub; `piiStateSavingEnabled=false`; the legal citations the reviewer supplied are *not* adopted as fact — the positions stay *to confirm* |
| B-15 web approval page is an undeclared ingress | **Accepted** | declared as exception X5 |
| B-17 G8 reads 24-hour-old policy state | **Accepted** | G8 adds synchronous Resource Graph and SDK assertions |
| B-12 per-person approver scoring and rhythm inference | **Adjusted** | DR-17 reworked to *role-level and aggregate* signals; no individual scoring; FR-V3/V4 limited to contact preferences |

### 2.6 Orchestration, evaluation, learning, drift

*A-10, D-01, D-02, D-04–D-13, ADR-33 (Disagree)*

| Finding | Disposition | Change |
|---|---|---|
| A-10, D-04, ADR-33 custom durability against the wrong alternative | **Accepted — the largest reversal** | the spine is **Durable Functions** (generally available; Flex Consumption; Azure Storage provider, Durable Task Scheduler optional) calling leaves through the hub; our checkpoint-and-jobs design becomes the named fallback; MAF stays *inside* leaves ([05 §4](../../design/05-agents-and-orchestration.md#4-how-the-spine-runs), [ADR-33](../../design/13-decisions.md)) |
| D-01 the spine is too rigid | **Adjusted** | bounded branching, fan-out of competing hypotheses and return edges are allowed; the evidence is an immutable, versioned record graph with contrary evidence; "no agent-to-agent channel" stays, the over-claim "nothing to travel along" is removed |
| D-02 Forger independence from investigators | **Accepted** | an empirical independence test, different generators |
| D-05 gate statistics | **Accepted** | a statistical protocol: paired non-inferiority, sample sizes, one-sided exact bounds, clustering by estate |
| D-06, E-08 receipts ≠ entailment; Groundedness conflation | **Accepted** | entailment, receipt hash and freshness, numeric provenance; the *detection* retirement is distinguished from the evaluator |
| D-07 exam isolation | **Accepted** | physical separation of generator, keys, labels; post-freeze held-out cases; per-domain reporting |
| D-08 W7 is not method learning | **Accepted** | a method-learning section and workflow W10 |
| D-09 red-teaming EU availability | **Accepted** | EU cloud runs *unverified*; the self-hosted PyRIT/ASSERT path is mandatory |
| D-10 fingerprint probe | **Accepted** | relabelled a statistical alarm; rotating hidden cases; fail closed when attribution is unproven |
| D-11 invalidation | **Accepted** | a dependency graph from claim, data, tool, evaluator and credential to every consumer |
| D-12, C-08 caching claim | **Accepted** | wording and model corrected (cache lifetime is minutes; cache writes per session) |
| D-13 gate evidence | **Accepted** | gates emit signed, time-bounded evidence keyed to the manifest; G9 is bound to manifest, domain, cap and expiry |
| D-14, E-13 | **Accepted** | Sandboxes are generally available; hosted agents reached GA in June 2026 |

### 2.7 Cost and operability

*C-01–C-08, A-08, A-11, A-15, A-16, E-09, E-10*

| Finding | Disposition | Change |
|---|---|---|
| C-01 one search unit priced for several accounts | **Accepted** | the model prices a standard-setup trio **per private account**; test and Lab accounts are created in the phase that needs them |
| C-02, C-03 PII, sandbox hours, red-teaming spend | **Accepted** | lines added, rates marked unverified where the price API has no meter |
| C-04, A-08 quotas do not match the scenarios; "hard budgets" | **Accepted** | quotas are *computed* from the model and printed with their euro cap; the spine reserves worst-case cost atomically; the residual overrun from concurrent requests is stated |
| C-05, C-06, E-09, E-10 | **Accepted** | false "counted" claim removed; peering line; marginal versus all-in; labour sensitivity; "a third" corrected to 41 %; 0.22 %; EU premium qualified to the GPT-6 family; three EU search regions |
| C-07 one operator cannot release | **Accepted** | a minimum crew; staged creation of environments |
| A-11 exclusivity claim for the analytics exception | **Accepted** | Synapse serverless reserves no idle compute; the exception now rests on measured simplicity and cost, with an owner and an expiry |
| A-15 fast signals | **Accepted** | an event-driven fast path (W3b) and a load-test spike |
| A-16 manual purchase fallback | **Accepted** | purchases stay disabled until AI execution is proven for the agreement type |

### 2.8 Platform facts

| Finding | Disposition | Change |
|---|---|---|
| E-01 Routines GA | **Accepted** | conflicting records (a Foundry devblog and Learn say GA; the Azure release record says preview): treated as **preview** |
| E-02 Python card actions | **Accepted** | the claim is removed; the Teams adapter stays C# for typing and shared contracts with the Approval service, not because Python lacks the handler |
| E-12 Claude hosting versions | **Accepted** | pin a hosting version; still no EU Data Zone |
| A-14 hosting integration is prerelease | **Accepted** | added to the preview register with a framework-agnostic fallback |
| A-17 README wording | **Accepted** | corrected at the end of the round |

## 3. ADR verdicts, summarised

All 37 ADRs were challenged by four reviewers each; the consolidated outcome:

- **Reversed:** ADR-33 (spine), ADR-07 (broker authority).
- **Substantially amended:** ADR-02 (hardening, per-agent authorisation, the portal-gateway claim), ADR-03/06 (projects, groups), ADR-09/10 (data-class contracts, Claude hosting), ADR-13 (exception rationale), ADR-15 (MCP fallback), ADR-19 (injection layers), ADR-22 (Groundedness, statistics), ADR-23 (stack bypasses, CI), ADR-26 (caps), ADR-32 (ledger), ADR-34 (Routines status), ADR-36 (language rationale), ADR-37 (Sandboxes GA).
- **Unchanged in substance:** ADR-01 (clarified), 04, 05, 11, 12, 14, 16, 17, 18, 20, 21, 24, 25, 27–31, 35.

## 4. Not adopted, and why

- **B-14's specific GDPR article citations** (Art. 17(3), Art. 22 inapplicability) as design statements: they are legal conclusions the design must not assert; they remain *to confirm* with counsel.
- **A-17's "reviews underway"**: accurate on the day of the draft; the README is corrected when the second round completes.
- **A reviewer suggestion to separate Atlas and code into two repositories (ADR-28 alternative)**: the data-path rule and workflow separation give the same merge boundary at lower cost; revisit if contributor isolation tests fail.

## 5. What round 2 is asked to attack

The *new* material: the three-party authority chain; the eleven contract groups and per-tool authorisation; the Durable Functions spine; the sanitiser layer; the statistical protocol; the corrected cost model; and anything the first round could not see because it was hidden behind what has now changed.
