# T-A re-check — `67c037b`

`CLOSED` judges the written design, not spike execution.

| Finding | Status | Closing quote or what is missing |
|---|---|---|
| TA-01 | CLOSED-WITH-RESIDUAL | Honest click/decline ordering is specified; a compromised page can induce sign-in without a click. |
| TA-02 | CLOSED | `<repo>\docs\design\07-security-architecture.md` §4, Separation of duties: “The broker and the runner each check this from the two Entra tokens themselves (signature, nonce, freshness): the two `oid`s differ, and neither `SHA-256(decision id ‖ oid)` equals the permit's `requester_ref` or `preparer_ref`.” |
| TA-06 | OPEN | Fresh reads and heartbeat do not establish cross-client freshness; the lease/deployment race remains possible (TA-M1). |
| TA-08 | CLOSED | `<repo>\docs\design\07-security-architecture.md` §3.3, point 6: “An approval record is create-only and never amended, and the Approval service holds no ledger read role and does no read-back, so its acknowledgement is not a proof.” |
| TA-11 | CLOSED-WITH-RESIDUAL | Consumer sender rights are corrected; the trusted page can still induce a person's sign-in. |
| TA-15 | CLOSED | `<repo>\docs\design\07-security-architecture.md` §3.3, Verifier: “The Auditor's read path is the deterministic `corroborate` operation of the `cost-query` tool, which compares a Verifier outcome's claimed saving with the export and returns the delta, with no model in it; the Auditor agent reads the result and writes the score.” |
| TA-18 | CLOSED-WITH-RESIDUAL | Broker redelivery reconciles; the mutable wait counter can suppress poison handling (TA-M2). |
| TA-22 | CLOSED-WITH-RESIDUAL | Conditional arbitration and repair are specified; late-result rules conflict and caller binding is incomplete (TA-M4/M5). |
| TA-N1 | CLOSED-WITH-RESIDUAL | The nonce does not prove a click: a compromised display can initiate sign-in or misrepresent the target. The stated residual remains without a receipt. |
| TA-N2 | CLOSED-WITH-RESIDUAL | Sender sets now include consumers; their ability to manipulate poison accounting remains (TA-M2). |
| TA-N3 | OPEN | Measuring lag does not prove the two-sided lock safe under Session consistency; the heartbeat does not fix that race (TA-M1). |
| TA-N4 | CLOSED | `<repo>\docs\design\07-security-architecture.md` §4, Signed: “After the Audit Writer acknowledges the approval entry, the Approval service creates a signed `approval-position` marker in `approvals-index` `{approval id, sequence number, block hash}`, signed with its entry key like every marker, and only then enqueues the record id.” |
| TA-N5 | CLOSED-WITH-RESIDUAL | Fail-closed conflicts prevent forgery but a writer can repeatedly deny decisions; attribution remains S-ID-3. |
| TA-N6 | OPEN | Keyless observation lacks a reliable trigger and replay after missed sweeps (TA-M3). |
| TA-N7 | CLOSED | `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.4, `cost-query` callers cell: “Surveyor, Detective, Skeptic, Economist, Conductor, Auditor (`corroborate`)”. |
| TA-N8 | CLOSED-WITH-RESIDUAL | Both poison-queue Sender assignments are specified; minimal trigger rights remain to confirm in S-ID-3. |
| TA-N9 | OPEN | `waits` is writable by queue consumers and can falsify the failure count (TA-M2). |
| TA-N10 | CLOSED | `<repo>\docs\design\05-agents-and-orchestration.md` §4, Register and close: “Besides the agents' `result` call the facade exposes two calls that only the spine's identity may make, through the app role `Run.Manage` assigned directly to it: `register`, before it launches a leaf, and `close`, at the deadline.” |
| TA-N11 | CLOSED-WITH-RESIDUAL | The conditional winner and repair are specified; the conflicting late-result contract and same-role caller binding remain (TA-M4/M5). |
| TA-N12 | CLOSED | `<repo>\docs\design\04-landing-zone-and-citadel.md` §6, `snet-exec`: “So, in production, nothing starts a chain job by a call.” |
| TA-N13 | OPEN | A no-cache read can still miss a newly raised epoch or deny entry (TA-M1). |

## Prior residuals not covered

- **TA-09:** No scheduled trigger or durable replay for the observer is specified; testing the deletion event alone does not establish one (TA-M3).
- **TA-20:** S-ORCH-1 tests a different `azp`, not a different run sharing the same identity (TA-M5).

## New defects

**TA-M1 · Critical ·** `<repo>\docs\design\07-security-architecture.md` §3.3, deployment lock. Quote: “either the broker's fresh read sees the lock”. **Why:** The broker can miss a lock while the pipeline misses its lease on independent stale reads; both proceed. A runner can likewise miss a newly raised epoch at its next step. A measured lag is not a guarantee. [Learn](https://learn.microsoft.com/en-us/azure/cosmos-db/consistency-levels): “reads to that physical partition behave as reads with Eventual Consistency.” **Fix:** require a documented cross-client consistency/fencing guarantee, fail closed when unavailable, and test both races.

**TA-M2 · Major ·** `<repo>\docs\design\07-security-architecture.md` §4, Single use. Quote: “failures = DequeueCount − waits > 3”. **Why:** A queue consumer can inject a message with an inflated `waits`; repeated failures then avoid the promised poison alert until expiry. [Learn](https://learn.microsoft.com/en-us/rest/api/storageservices/update-message): “You can also use this operation to update the contents of a message.” **Fix:** maintain an independently authenticated wait count and reject impossible counters.

**TA-M3 · Major ·** `<repo>\docs\design\07-security-architecture.md` §3.1, Verifier. Quote: “event job on `verify`; no ingress”. **Why:** The scheduled sweeper can remove a grant after the last `verify` message; nothing schedules the Verifier to observe it, and an Audit Writer outage can leave it unrecorded. [Learn](https://learn.microsoft.com/en-us/azure/container-apps/jobs): “Event-driven jobs are triggered by events, such as a message arriving in a queue.” **Fix:** schedule durable observation and retry with an idempotent watermark.

**TA-M4 · Major ·** `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.4, `case-record`. Quote: “the facade accepts a `run-result` only for a run in state `claimed` or `started` whose registered `azp` equals the caller's verified `azp` and whose attempt and epoch match, and rejects any other”. **Why:** `<repo>\docs\design\05-agents-and-orchestration.md` §4 permits one result after `timed-out`; implementing 04 rejects that evidence. **Fix:** explicitly admit one late result without reopening the attempt.

**TA-M5 · Major ·** `<repo>\docs\design\05-agents-and-orchestration.md` §4, Result. Quote: “so no other leaf, and not the Brief service, can end a run that is not its own”. **Why:** Two runs of the same role share an `azp`. If one learns the other's run id, it can supply the matching case, epoch and attempt; no authenticated per-run capability is specified. **Fix:** bind result authority to the invocation and test same-identity cross-case forgery.

## Verdict

ADR-07: **Disagree** — require a real cross-client consistency/fencing guarantee and outage-observer tests.
ADR-08: **Agree with changes** — upgrade after S-ID-3 proves the flow and the trusted-display residual is accepted.
ADR-33: **Disagree** — require per-run authorisation and an unambiguous late-result contract.
C21 protects create-only evidence; C22's idempotent repair is directionally sound but needs the above fixes.
Keep estate changes disabled until the fixes and named spikes pass.
