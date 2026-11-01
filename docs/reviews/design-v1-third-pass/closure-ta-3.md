# T-A confirmation — `56011b4`

| Finding | Status | Closing quote or what is missing |
|---|---|---|
| TA-M1 | CLOSED-WITH-RESIDUAL | Strong on serverless and read overrides remain **UNVERIFIED**; S-ID-3 must prove the selected path. |
| TA-M2 | CLOSED-WITH-RESIDUAL | Broker signatures protect the counter; a compromised broker can still falsify it. S-ID-3 must exercise poison handling. |
| TA-M3 | OPEN | The observer is scheduled, but duplicate and missing entries remain possible (TA-K1/K2). |
| TA-M4 | CLOSED | `<repo>\docs\design\05-agents-and-orchestration.md` §4, Result: “The facade accepts a `run-result` from the registered `azp`, with the matching attempt, epoch and run token, for a run in `claimed` or `started`; once more, flagged `late: true` at creation and without reopening the attempt, for a run in `timed-out`; for a `completed` run, or a `timed-out` run that already holds its late result, only an identical repeat by the same caller (an idempotent acknowledgement, never stored twice); never for `registered` or `abandoned`, so no other leaf, not the Brief service and not a same-role agent of another case can end a run that is not its own.” |
| TA-M5 | CLOSED-WITH-RESIDUAL | Run-token isolation and non-logging need the named same-role and hub tests. |
| TA-06 | CLOSED-WITH-RESIDUAL | Strong lock reads and their fail-closed fallback need S-ID-3 validation. |
| TA-N3 | CLOSED-WITH-RESIDUAL | The two-sided lock has a Strong-consistency argument; serverless support remains **UNVERIFIED**. |
| TA-N6 | OPEN | Scheduled observation can duplicate or miss a removal (TA-K1/K2). |
| TA-N9 | CLOSED-WITH-RESIDUAL | Unsigned or invalid counters count as zero; the broker's own signing key remains trusted. |
| TA-N13 | CLOSED-WITH-RESIDUAL | Per-step Strong reads are specified; the selected account configuration needs S-ID-3. |

[Learn](https://learn.microsoft.com/en-us/azure/cosmos-db/consistency-levels): “Strong consistency offers a linearizability guarantee.”

## New defects

**TA-K1 · Major ·** `<repo>\docs\design\07-security-architecture.md` §3.3, point 4. Quote: “the observer reads the ledger back before it appends, so a re-run, an overlap or a catch-up appends nothing twice”. **Why:** Two overlapping observers can both read no entry for the same event, then both append; an event id in the payload is not atomic deduplication. **Fix:** enforce event-id uniqueness at the writer or fence observer execution.

**TA-K2 · Major ·** `<repo>\docs\design\07-security-architecture.md` §3.3, point 4. Quote: “the event time of the last `sweep-observed` entry it finds in the ledger, less a 30-minute overlap”. **Why:** A newer event can advance the watermark before an older deletion arrives; an older deletion outside the overlap is never read. [Learn](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log): “Activity log entries are usually available for analysis and alerting within 3 to 20 minutes of the event occurring.” This is not a 30-minute guarantee. **Fix:** initialise a durable cursor and periodically reconcile the retained history, with event-id deduplication and gap alerts.

## Verdict

ADR-07: **Disagree** — require lossless, deduplicated observation and the consistency spike.
ADR-08: **Agree with changes** — the trusted-display residual and S-ID-3 remain.
ADR-33: **Agree with changes** — prove run-token isolation and late-result recovery in S-ORCH-1.
