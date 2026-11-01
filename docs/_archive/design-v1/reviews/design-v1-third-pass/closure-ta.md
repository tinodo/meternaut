# T-A closure check — `87925dd`

`CLOSED` assesses text, not spike results.

| Finding | Status | Closing quote or what is missing |
|---|---|---|
| TA-01 | OPEN | `<repo>\docs\design\07-security-architecture.md` §3.3: the decision-bound nonce still does not prove a click; TA-N1. |
| TA-02 | OPEN | `<repo>\docs\design\07-security-architecture.md` §4: runner checks pseudonyms, not token `oid`s or preparer exclusion. |
| TA-03 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\06-data-and-knowledge.md` §7.2: signatures need canonical item/type/scope binding; unsigned narrowing permits denial of service. |
| TA-04 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\06-data-and-knowledge.md` §7.2: signatures don't prevent marker-id preemption; TA-N5. |
| TA-05 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\07-security-architecture.md` §3.3: unleased grants acknowledged; broker-only `run` sender is false; TA-N2. |
| TA-06 | OPEN | `<repo>\docs\design\11-delivery-and-operations.md` §3: production start removed; honest deployment still races leases/expiry; TA-N3. |
| TA-07 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\07-security-architecture.md` §3.3: harmless, permission-equivalent purchase probe remains unproven. |
| TA-08 | OPEN | `<repo>\docs\design\06-data-and-knowledge.md` §2/§7.2: second signature and producer read-back lack rights; TA-N4. |
| TA-09 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\07-security-architecture.md` §3.3: missing outcomes need reconciliation; sweeper lacks outbox rights; TA-N6. |
| TA-10 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\07-security-architecture.md` §4: signed-credential field binding, keys and withdrawal races need proof. |
| TA-11 | OPEN | `<repo>\docs\design\07-security-architecture.md` §3.3: broker-only sender is false; web-approval claim unsupported; TA-N1/N2. |
| TA-12 | CLOSED | `<repo>\docs\design\07-security-architecture.md` §3.4: “A forced fresh sign-in (`prompt=login`) with `iat` proves no second factor, so it is **not** a fallback.” |
| TA-13 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\07-security-architecture.md` §4: `received_at` is Approval-attested; expiry-at-receipt validation unspecified. |
| TA-14 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\07-security-architecture.md` §3.4: broker consistency and automatic post-grant epoch/deny updates unproven. |
| TA-15 | OPEN | `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.4: Auditor lacks specified independent cost-query permission; sampling misses claims; TA-N7. |
| TA-16 | CLOSED | `<repo>\docs\design\04-landing-zone-and-citadel.md` §6, `snet-exec` cell: “**Z3**: Policy service and Approval service (VNet ingress, restricted to the named subnets); credential broker, Move runner jobs (one per Move class) and Verifier job (event-driven, **no ingress**); **no private endpoint**, because the subnet is delegated; allowed paths enumerated below”. |
| TA-17 | CLOSED | `<repo>\docs\design\04-landing-zone-and-citadel.md` §6: “Where a document says **VNet ingress, restricted to the named subnets**, it means this; the callers' routes stay listed below, and S-NET-2 tests each route and each network security group.” |
| TA-18 | OPEN | `<repo>\docs\design\07-security-architecture.md` §4: broker redelivery still refused after nonce marker; TA-N8/N9. |
| TA-19 | CLOSED | `<repo>\docs\design\03-logical-architecture.md` §4: “As its terminal act it writes a small **`run-result`** record through the case-record facade (every role does, even those that write no other record), and its wrapper then emits **one `run-completed` event** from the worker's `finally`.” |
| TA-20 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\05-agents-and-orchestration.md` §4: result binding added; spine registration authorization missing, TA-N10. |
| TA-21 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\05-agents-and-orchestration.md` §4: crash after claim strands invocation until deadline. |
| TA-22 | OPEN | `<repo>\docs\design\05-agents-and-orchestration.md` §4: result/deadline arbitration isn't atomic; TA-N11. |
| TA-23 | CLOSED | `<repo>\docs\design\05-agents-and-orchestration.md` §4: “The id has a budget, so that the longest one always fits: the workflow's short name (`w4`, `w3b`, `w10`) at most 16 characters, the case id at most 48 characters from `[A-Za-z0-9._-]` and the epoch at most 8 digits, which composes to at most 74 characters with the colons.” |
| TA-24 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.4: S-HOST-1 must prove unbuffered streaming across every hop. |
| TA-25 | CLOSED | `<repo>\docs\design\07-security-architecture.md` §3.3, Policy service cell: “the proposal against the Move catalogue, its rules, the autonomy credential (cap, scope, expiry, live status) and the price tolerance; then it signs a **permit** whose id is the decision id that the spine allocated before it computed the target hash”. |
| TA-26 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\07-security-architecture.md` §4: authorization-code client-assertion flow **UNVERIFIED**. |
| TA-27 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\04-landing-zone-and-citadel.md` §6: no-manual-start claim contradicts dev/test smoke tests, TA-N12. |
| TA-28 | CLOSED-WITH-RESIDUAL | `<repo>\docs\design\07-security-architecture.md` §10.3: immediate next-step revocation still claimed, TA-N13. |

Vendor checks, fetched today: https://learn.microsoft.com/en-us/azure/virtual-network/subnet-delegation-overview — “Can't be used with a private endpoint if the subnet is delegated.” https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview — “directly reachable only from within the same Container Apps environment”. https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-orchestrations — “They must be between 1 and 100 characters.” https://learn.microsoft.com/en-us/azure/api-management/how-to-server-sent-events — “Turn off response buffering”. https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-config-app-trust-managed-identity — “configure a Microsoft Entra application to trust a managed identity”. https://learn.microsoft.com/en-us/entra/identity/authentication/concept-authentication-strengths — “To use Conditional Access, your tenant needs to have Microsoft Entra ID P1 license.” https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference — “Identifies the expiration time on or after which the JWT can't be accepted for processing.”

## New defects

**TA-N1 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.3, sequence. Quote: “BRF->>ENT: sign in with a nonce bound to the target hash, the decision approve and the challenge”.
**Why:** Sign-in with an *approve* nonce precedes any approve click; a later decline yields a relabellable token. The nonce is app-chosen: https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc — “A value generated and sent by your app”. **Fix:** independently authenticate the positive click; retain trusted-display risk.

**TA-N2 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.1, `stchain`. Quote: “only the broker to `run`”.
**Why:** Runner's `acia-queue-worker` includes `messages/write`, permitting Put Message: https://learn.microsoft.com/en-us/azure/storage/queues/queues-auth-abac-attributes — “Put or update a message”. Runner can enqueue `run`; broker can enqueue `dispatch`. **Fix:** correct residual and isolate renewal authority.

**TA-N3 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.3, deployment lock. Quote: “waits one cache period, 60 seconds”.
**Why:** Broker checks cached absence and pauses; pipeline re-reads no lease and writes; broker then leases. Deployment can also outlive its lock. TTL with no default supports item expiry: https://learn.microsoft.com/en-us/azure/cosmos-db/time-to-live — “An item no longer appears in query responses immediately after the TTL expires”. **Fix:** atomically arbitrate with fencing; abort on lock loss.

**TA-N4 · Critical ·** `<repo>\docs\design\06-data-and-knowledge.md` §2, `ledger_entry`. Quote: “after the Audit Writer's acknowledgement and its own read-back”.
**Why:** `<repo>\docs\design\07-security-architecture.md` §3.1 gives Approval no ledger read; `approval-records` is create-only, yet its record is amended. https://learn.microsoft.com/en-us/azure/cosmos-db/reference-data-plane-security distinguishes “Creates new items” from “Replaces existing items”. **Fix:** grant read and append an immutable second attestation.

**TA-N5 · Major ·** `<repo>\docs\design\06-data-and-knowledge.md` §7.2, `approvals-index`. Quote: “a marker that fails is ignored and raises D14”.
**Why:** A co-writer can occupy the marker id with invalid data; genuine create conflicts and create-only writers cannot remove it. https://learn.microsoft.com/en-us/rest/api/cosmos-db/http-status-codes-for-cosmosdb: “The ID provided for a resource on a `PUT` or `POST` operation has been taken”. **Fix:** isolate writers or authenticate conflict recovery.

**TA-N6 · Major ·** `<repo>\docs\design\07-security-architecture.md` §3.3, outage rollback. Quote: “It runs from a signed **outbox**, an entry that its party signs and creates as a marker in `approvals-index`”.
**Why:** §3.1 gives the sweeper neither signing key nor index-create rights; `<repo>\docs\design\06-data-and-knowledge.md` §7.2 omits it as writer. **Fix:** give it an isolated signed outbox or reconcile ungated revocation.

**TA-N7 · Major ·** `<repo>\docs\design\07-security-architecture.md` §3.3, Verifier. Quote: “the Auditor therefore re-measures verified savings from the cost export through its own read path”.
**Why:** `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.4 omits Auditor's `cost-query` role; sampling misses claims. **Fix:** authorize an independent reader and distinguish sampled from verified outcomes.

**TA-N8 · Major ·** `<repo>\docs\design\07-security-architecture.md` §3.1, Spine. Quote: “the spine's right to add there is *to confirm* in S-ID-3”.
**Why:** Spine has Processor on `spine-events` but no Sender on `spine-events-poison`. https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger — “the functions runtime adds a message to a queue named” the poison queue. **Fix:** provision and test queue-scoped send permission.

**TA-N9 · Major ·** `<repo>\docs\design\07-security-architecture.md` §4, Single use. Quote: “a message that only waits, for a lease or a deployment lock, is put back with a delay and is not counted”.
**Why:** Re-dequeue increments the native count: https://learn.microsoft.com/en-us/rest/api/storageservices/get-messages — “This value is incremented each time the message is subsequently dequeued.” **Fix:** persist a separate failure count; test repeated waits.

**TA-N10 · Major ·** `<repo>\docs\design\05-agents-and-orchestration.md` §4, Calling a leaf. Quote: “registers the run with the case-record facade”.
**Why:** `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.4 grants agents, not spine, the tool role; no alternative is specified. **Fix:** define and test spine registration/read authorization.

**TA-N11 · Major ·** `<repo>\docs\design\05-agents-and-orchestration.md` §4, Arbitration. Quote: “The first of a matching `run-result` and the deadline wins”.
**Why:** An in-time receipt can commit after the timer's re-read, closing the step before its result appears. **Fix:** atomically commit one epoch/attempt decision; reconcile late commits.

**TA-N12 · Minor ·** `<repo>\docs\design\04-landing-zone-and-citadel.md` §6. Quote: “nothing starts a chain job by a call”.
**Why:** It also permits `deploy` smoke starts; `<repo>\docs\design\14-next-phases.md` §3 S-ID-3 repeats the queue-only claim. **Fix:** qualify it to production.

**TA-N13 · Major ·** `<repo>\docs\design\14-next-phases.md` §3, S-ID-3. Quote: “an epoch raised during a Move stops it at its next step”.
**Why:** `<repo>\docs\design\07-security-architecture.md` §10.3 allows a 60-second stale epoch. **Fix:** state the bound or use fresh, fenced checks.

Validation: the closure report is not yet linked; strict documentation checking reports it as an orphan.

## Verdict

ADR-07: **Disagree** — independent authority, lock and recovery gaps remain.  
ADR-08: **Disagree** — the nonce does not independently prove approval.  
ADR-33: **Agree with changes** — result arbitration and registration need implementation.  
The adjusted signature approach improves integrity but leaves preemption and trust residuals.  
Keep estate changes disabled until these defects and the named spikes are resolved.
