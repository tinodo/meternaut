# Targeted third pass — authority chain and leaf calls

Reviewed commit `6694d15`; the working tree changed during review. Findings are against that commit.

## Verdict

Unsafe for estate-changing action.  
Authentication does not prove a positive approval (V1).  
Single-party authority and audit gaps remain.  
Leaf completion and retries lack durable enforcement.  
Block execution until independent controls and fault tests pass.

## Findings

Findings attack Round 2's redesign and its incomplete or contradicted fixes.

**TA-01 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.3, The execution identity. Quote: “BRF->>APR: the token and the decision”.
**Why:** Compromised Approval relabels a decline and dispatches the real token; authentication checks cannot prove a positive click (V1). Round 2 B-01's fix is incomplete. **Fix:** independently sign a page receipt binding positive decision, displayed transaction and fresh challenge; broker/runner verify it. Disclose trusted-display risk.

**TA-02 · Critical ·** `<repo>\docs\design\03-logical-architecture.md` §4, A commitment purchase. Quote: “APR->>APR: with the approver set from the Estate service, check two distinct people, two different hats, not the requester”.
**Why:** Broker checks don't independently require distinct people, hats and requester exclusion. Compromised Approval can duplicate a dual-hatted person's valid token. **Fix:** broker and runner independently enforce these conditions; test duplicated proofs.

**TA-03 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §10.3, Kill switches. Quote: “its role is create-only on deny and epoch items”.
**Why:** `<repo>\docs\design\06-data-and-knowledge.md` §7.2 also puts active credentials in `controls`. Container-scoped create cannot restrict item type (V2): compromised Governance can create a credential honest services treat as human-granted. **Fix:** separate grant and denial stores; verify signed human grants.

**TA-04 · Critical ·** `<repo>\docs\design\06-data-and-knowledge.md` §7.2, The operational store. Quote: “create only: the Approval service (the entry), the broker (the grant marker) and the runner (its start and done markers)”.
**Why:** Each identity can create any item there (V2). Before the runner writes, compromised Approval can forge its done marker and signal premature revocation and verification. Ownership isn't enforced. **Fix:** separate writer-scoped containers or verify producer-signed markers.

**TA-05 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.3, The delegation. Quote: “It cannot limit the target scope”.
**Why:** Compromised broker credentials can grant roles at opted-in scopes to identities without leases (V17). The leased-identity claim is false; D15 is detective. **Fix:** state the residual, reduce delegated scopes and independently authorise grants.

**TA-06 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.3, Only the deploying pipeline. Quote: “whoever holds `Microsoft.App/jobs/start/action` can run any code as the job's identities”.
**Why:** During an honest lease, compromised deployment code can start an overridden job using the privileged runner identity (V3), subject to image admission. Compromised runner code can similarly exceed approved parameters. D16 is retrospective. **Fix:** use separately gated, time-limited job authority; drain active leases and state both residuals.

**TA-07 · Major ·** `<repo>\docs\design\07-security-architecture.md` §3.3, Leases, probes and quarantine. Quote: “a read of the assignments that shows none”.
**Why:** Listing a deleted assignment doesn't establish loss of effective access (V5); reuse can overlap targets. `<repo>\docs\design\11-delivery-and-operations.md` §6 additionally requires a failed call. **Fix:** quarantine until effective-access probes and propagation criteria pass.

**TA-08 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.3, execution sequence. Quote: “AWR-->>APR: acknowledged”.
**Why:** Approval lacks ledger read-back. Compromised Audit Writer can acknowledge without appending the approval, then append later entries; broker and runner proceed. Nightly chain verification alone cannot prove the omission. Round 2 B-06 is incomplete. **Fix:** independently verify approval-entry inclusion before dispatch.

**TA-09 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.3, execution sequence. Quote: “BRK->>ARM: grant the leased identity a constrained role on the exact target”.
**Why:** Grant logging follows the grant; the runner likewise changes the target before appending. An intervening outage leaves unrecorded effects. `<repo>\docs\design\03-logical-architecture.md` §4 also omits the rollback exemption. **Fix:** read back signed intent before effects; reconcile missing outcomes.

**TA-10 · Critical ·** `<repo>\docs\design\09-safeguards-and-drift-controls.md` §4, The authority chain. Quote: “within that credential's cap, scope and expiry”.
**Why:** Compromised Policy and Approval can sign overstated caps. A conforming broker/runner that independently checks only live *status* will accept them. The residual is not demonstrably bounded. **Fix:** independently compare permit and target with the credential's full live constraints.

**TA-11 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.3, What the chain promises. Quote: “the proof is the bot channel's assertion, which a compromised Approval service can fabricate”.
**Why:** This contradicts `<repo>\docs\design\03-logical-architecture.md` §3: “so it cannot complete a change that needs a person”. Residuals also differ in `<repo>\docs\design\01-requirements-and-principles.md` Q-SEC-1, `<repo>\docs\design\02-technology-landscape.md` H4/H10, `<repo>\docs\design\05-agents-and-orchestration.md` W4, `<repo>\docs\design\08-governance-and-compliance.md` R13, `<repo>\docs\design\09-safeguards-and-drift-controls.md` §4 and `<repo>\docs\design\13-decisions.md` ADR-07. **Fix:** state card and runner/pipeline residuals consistently.

**TA-12 · Critical ·** `<repo>\docs\design\14-next-phases.md` §3, S-ID-3. Quote: “if a claim does not arrive, the page forces a fresh sign-in with `prompt=login` and the verifiers rely on `iat`”.
**Why:** This contradicts `<repo>\docs\design\07-security-architecture.md` §4: issuance time doesn't prove MFA; password-only authentication is possible (V1, V6). **Fix:** fail closed without required proof or independently enforce step-up.

**TA-13 · Major ·** `<repo>\docs\design\07-security-architecture.md` §4, Claims the verifiers check. Quote: “`auth_time` later than the approval's creation”.
**Why:** If creation means the signed record, login necessarily precedes it. Five-minute `iat`/`exp` wording is ambiguous against an ordinarily hour-long token (V1). **Fix:** define pre-login request time and token-age, expiry and skew rules.

**TA-14 · Major ·** `<repo>\docs\design\06-data-and-knowledge.md` §2, Approval. Quote: “read live again at grant and at start”.
**Why:** `<repo>\docs\design\07-security-architecture.md` §3.1 grants the runner no Graph membership permission. Standing removed after grant may not stop it; filtered Graph queries can use a stale index (V7). **Fix:** specify start-time checks, consistency and fail-closed behavior.

**TA-15 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.1, The execution chain. Quote: “creates its outcome records in `ledger`; reads `controls`; appends and reads back”.
**Why:** No prediction read is granted, yet comparison requires it. Compromised Verifier can also sign a false success; the Auditor lacks independent estate evidence. **Fix:** grant prediction reads and corroborate outcomes using a separately authenticated estate reader.

**TA-16 · Critical ·** `<repo>\docs\design\04-landing-zone-and-citadel.md` §6, Network. Quote: “the private endpoint of `stchain`”.
**Why:** The `/27` environment subnet is delegated and cannot host a private endpoint (V8). A-02's fix cannot deploy. **Fix:** use a nondelegated endpoint subnet; update routes, DNS and tests.

**TA-17 · Critical ·** `<repo>\docs\design\04-landing-zone-and-citadel.md` §6, Network. Quote: “the Audit Writer takes internal ingress from every producer”.
**Why:** Cross-environment producers cannot directly reach per-app internal ingress (V9); Approval and Policy share this problem. No environment-level route is specified. **Fix:** use external app ingress on internal environments or explicit private routes, with restrictions.

**TA-18 · Major ·** `<repo>\docs\design\07-security-architecture.md` §4, Single use. Quote: “a second create fails with HTTP 409”.
**Why:** A crash after a nonce/start marker makes redelivery fail, even before the effect; `<repo>\docs\design\09-safeguards-and-drift-controls.md` §4 promises retry. Visibility, replicas and poison handling are unspecified (V4, V10). **Fix:** durable attempt states, `parallelism=1`, `replicaCompletionCount=1`, visibility renewal, poison handling and uncertain-effect reconciliation.

**TA-19 · Critical ·** `<repo>\docs\design\05-agents-and-orchestration.md` §4, Calling a leaf. Quote: “the leaf wrapper emits a single terminal `run-completed` event when the handler exits, in a `finally`”.
**Why:** The call returns immediately. If `finally` wraps the HTTP handler, it fires before background work finishes. A-04's fix is incomplete. **Fix:** wrap the actual worker and persist its terminal result.

**TA-20 · Critical ·** `<repo>\docs\design\05-agents-and-orchestration.md` §2, The roster. Quote: “the Conductor, the Examiner and the Forger, who write no typed records”.
**Why:** Brief and facade share `spine-signals`; queue authorization is not per message (V16). Compromised Brief can forge another case's completion; a different leaf may also do so through the facade. Event-only leaves have no terminal record to re-read. **Fix:** authenticate and bind terminal records to caller, case, step, invocation and epoch.

**TA-21 · Major ·** `<repo>\docs\design\05-agents-and-orchestration.md` §10, Failure and degradation. Quote: “a repeat returns the earlier run's record instead of running twice”.
**Why:** A lost response causes a retry with the same id; the adapter documents echoing, not deduplication (V11). No atomic run registry is specified. **Fix:** persist invocation ownership and result; test retries and process loss.

**TA-22 · Major ·** `<repo>\docs\design\05-agents-and-orchestration.md` §5, Completion. Quote: “the case id, the step, the idempotency key, the outcome (succeeded or failed), an error code and the ids of the records written”.
**Why:** No workflow or epoch identifies the instance. After restore an old leaf's event can be discarded or misrouted; duplicates and late events can race the deadline. Crash or idle eviction can skip `finally`; an unreconciled reservation remains held. **Fix:** persist epoch-fenced terminal state, arbitrate races and reconcile spend conservatively.

**TA-23 · Major ·** `<repo>\docs\design\05-agents-and-orchestration.md` §4, Identity and idempotency. Quote: “printable ASCII, at most 100 characters”.
**Why:** A valid 100-character id exceeds the limit when `:epoch` is appended; some printable characters are disallowed (V13). **Fix:** reserve suffix space, encode or hash ids and test restore.

**TA-24 · Major ·** `<repo>\docs\design\05-agents-and-orchestration.md` §4, Calling a leaf. Quote: “the stream must send its headers and keep-alives at once”.
**Why:** The SSE fallback doesn't disable response buffering; small keep-alives can miss an intermediary timeout (V14). **Fix:** set `buffer-response=false` and test every hop for the longest active duration.

**TA-25 · Major ·** `<repo>\docs\design\07-security-architecture.md` §4, Permitted by policy. Quote: “the permit's id is the policy decision id that the target hash covers”.
**Why:** §3.3 sends the hash to Policy before it returns the permit id; preallocation isn't specified. **Fix:** allocate the immutable id before hashing and pass both to Policy.

**TA-26 · Major ·** `<repo>\docs\design\07-security-architecture.md` §4, Authenticated human. Quote: “a federated identity credential on the page's managed identity”.
**Why:** Documented trust is on the app registration, with the user-assigned identity as subject (V15). The confidential-client sign-in flow remains **UNVERIFIED**. **Fix:** correct the direction and prove the authorization-code flow.

**TA-27 · Major ·** `<repo>\docs\design\04-landing-zone-and-citadel.md` §6, Network. Quote: “only the `deploy` pipeline holds `Microsoft.App/jobs/write` and `Microsoft.App/jobs/start/action`”.
**Why:** `<repo>\docs\design\11-delivery-and-operations.md` §3 assigns production to `release`. Literal implementation breaks deployment or grants the wrong identity. **Fix:** align ADR-07 and the environment matrix.

**TA-28 · Major ·** `<repo>\docs\design\09-safeguards-and-drift-controls.md` §4, What stops when. Quote: “the execution plane's switch stops new grants and dispatches at once”.
**Why:** `<repo>\docs\design\07-security-architecture.md` §10.3 permits a 60-second cache; grants or steps can use the old flag. **Fix:** state the bound or prove faster invalidation.

## ADR verdicts

Source: `<repo>\docs\design\13-decisions.md` ADR-07, ADR-08 and ADR-33.

| ADR | Verdict · confidence | Strongest alternative and tradeoff | What would change my mind |
|---|---|---|---|
| ADR-07 | Disagree · high | Per-Move identities and time-bound assignments reduce reuse but add churn; PIM support **UNVERIFIED**. | Independent grant, deployment and effect enforcement. |
| ADR-08 | Disagree · high | Signed transaction approval and trusted display add a component but prove more than sign-in. | Rejection, duplicate-hat, card and relay attacks fail closed. |
| ADR-33 | Agree with changes · high | Checkpoint-and-jobs offers control but adds recovery machinery. | Durable, authenticated completion and crash/epoch-safe idempotency. |

## What is strong

The signer no longer has a job-start right; separate keys, scoped queues, independent broker/runner checks, read-back by three producers and a deadline backstop are useful layers. They are not independent enforcement against compromised code.

**Authority map.** Positive rights only; omitted rights are not assumed. Sources: `<repo>\docs\design\07-security-architecture.md` §3.1, `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.4 and §6, and `<repo>\docs\design\11-delivery-and-operations.md` §3 and §7.5.

| Party | Declared authority |
|---|---|
| Person | Receives Brief, authenticates and decides; named humans grant credentials. Entra signs tokens. |
| Policy | Receives proposals; reads rules and credentials; signs permits and entries; calls Audit Writer. |
| Brief/page | Receives decisions, relays proof to Approval, writes Briefs, sends `spine-signals`. |
| Approval | Signs records/entries; reads controls and Policy key; creates approval/index items; sends `dispatch` and `spine-events`. |
| Broker | Receives `dispatch`; reads proofs, controls and standing; creates markers/leases; grants/revokes roles; signs entries; sends class `run`. |
| Runner | Receives class `run`; reads proofs/lease/controls; signs entries; creates start/done; acts under lease; sends `spine-events`. |
| Verifier | Receives `verify`; reads estate/controls; signs entry, writes outcome, sends `spine-events`. |
| Audit Writer | Receives signed entries, reads keys/lease, writes ledger and signs digest. Nightly ledger verifier reads and checks independently. |
| Spine | Calls Policy, starts leaves through hub; reads index/budgets, writes reservations; sends `verify`; receives both signal queues. |
| Case-record facade | Receives leaf records/events, reads and creates cases, sends `spine-signals`. |
| Deploy/release pipelines | Sign release artifacts; write and start their environment's jobs; grant conditioned roles on own resource groups. |
| Operator | Uses authorised controls and runbooks; elevated bootstrap is protected and exceptional. |

Forged `dispatch` and `run` messages wake the broker and runner but should fail proof/lease checks. Forged `verify` wakes the Verifier; a matching done proof isn't specified. Any chain sender can send to `spine-events`; Brief or facade can send to `spine-signals`. Shared queues don't establish per-message producer authority (V16).

`<repo>\docs\design\11-delivery-and-operations.md` §7.5 RB-12 publishes new pins before signing and retains the previous key for the longest approval validity; RB-13 retains signed approvals unless expiry or epoch intervenes. Neither makes TA-08/09 or TA-28 disappear.

**Platform evidence, fetched 2026-11-01:**

- V1 https://learn.microsoft.com/en-us/entra/identity-platform/id-tokens — “proof of authentication”; “By default, an ID token is valid for one hour”.
- V2 https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-connect-role-based-access-control — “a single container, the most granular scope”.
- V3 https://learn.microsoft.com/en-us/azure/container-apps/jobs — “For any job type, you can start a job execution on demand.”; “accepts an optional execution template”; “each job execution typically processes a single event”.
- V4 https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2026-07-01/jobs — “parallel replicas of a job”; “successful replica completions”; “identity that is assigned to the job”.
- V5 https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting — “up to 10 minutes”.
- V6 https://learn.microsoft.com/en-us/entra/identity-platform/optional-claims-reference — “user last authenticated”; “how the subject of the token was authenticated”; “only when the user has completed MFA.”
- V7 https://learn.microsoft.com/en-us/graph/api/group-list-transitivemembers?view=graph-rest-1.0 — “index that might not be up-to-date”.
- V8 https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks — “You must delegate your subnet to `Microsoft.App/environments`.” https://learn.microsoft.com/en-us/azure/virtual-network/subnet-delegation-overview — “Can't be used with a private endpoint if the subnet is delegated.”
- V9 https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview — “directly reachable only from within the same Container Apps environment”.
- V10 https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-azure-and-service-bus-queues-compared-contrasted — “Automatic dead lettering | No | Yes”; “Lease/Lock duration | 30 seconds (default)”.
- V11 https://learn.microsoft.com/en-us/python/api/overview/azure/ai-agentserver-invocations-readme?view=azure-python — “Echoed if provided, otherwise a UUID is generated”.
- V12 https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-external-events — “External events have an *at-least-once* delivery guarantee.”; “the event message is added to an in-memory queue”; “the event message is discarded.”
- V13 https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-orchestrations — “They must be between 1 and 100 characters.”; “They must not contain `/`, `\`, `#`, or `?` characters.”
- V14 https://learn.microsoft.com/en-us/azure/api-management/how-to-server-sent-events — “Turn off response buffering”. https://learn.microsoft.com/en-us/azure/api-management/forward-request-policy — “chunks are buffered (8 KB, unless end of stream is detected)”.
- V15 https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-config-app-trust-managed-identity — “application to trust a managed identity.”
- V16 https://learn.microsoft.com/en-us/azure/storage/queues/secure-queues — “they aren't individually access-controlled beyond queue-level authorization.”
- V17 https://learn.microsoft.com/en-us/azure/role-based-access-control/delegate-role-assignments-overview — “constrain the roles that Dara can assign, constrain the principals”.

Additional checks: https://learn.microsoft.com/en-us/azure/container-apps/scale-app — “including Azure Queue Storage, Azure Service Bus, and Azure Event Hubs, also support managed identity.” V4 documents job scale-rule `identity`; its queue-scoped combination is **UNVERIFIED**. V16 — “Queue-level scope is supported for the built-in queue data roles.” https://learn.microsoft.com/en-us/azure/storage/queues/queues-auth-abac-attributes — “Azure attribute-based access control (Azure ABAC) is generally available (GA)”. https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/security — Crypto User includes “Microsoft.KeyVault/vaults/keys/read”, “Microsoft.KeyVault/vaults/keys/update/action” and “Microsoft.KeyVault/vaults/keys/sign/action”; proposed custom roles need deployment tests.

https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents — “the platform deprovisions the compute and persists the session state.” Responses background has “platform-managed polling and cancellation”; crash recovery is separate: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/long-running-agent-resilience — “Recovery after the process that owns the work stops.” https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-eternal-orchestrations — “The same instance ID is kept, but the orchestrator function's history resets.” https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-storage-providers lists Flex with Azure Storage as “Fully supported”; https://www.microsoft.com/releasecommunications/api/v2/azure/498144 says “Public Preview: Orchestration versioning”. Early events for an existing instance are buffered; events for nonexistent instances are discarded (V12).

## What is still unproven — run first

1. S-ID-1/S-ID-3: direct broker misuse, marker forgery, queue-scaler identity, real effective revocation, key rotation and epoch changes during a Move; Graph denial and propagation.
2. S-ID-3/S-ACT-1: positive-decision proof, two distinct hats, claim arrival, token time predicates and the confidential-client flow; purchases remain disabled until proven.
3. S-HOST-1: crash, immediate-return and idle-tail tests; the three fallbacks are listed but tested only if the primary fails, in order until one passes.
4. S-ORCH-1: duplicate and early events, timeout races, old-epoch leaves, maximum-length ids, ambiguous effects and budget reconciliation.
5. Starting timeouts in `<repo>\docs\design\05-agents-and-orchestration.md` §5 match `<repo>\tools\cost-model.py` `HOSTED_SESSIONS`: 20/10/10/15/5/5 minutes exceed the corresponding 12/6/5/2/3/2 active-minute seeds. Actual p99s, idle billing and overrun tails are **UNVERIFIED**.

Validation: all 28 finding quotations match `6694d15`; strict documentation check on the current worktree passed (56 documents).
