# T-B closure check (`87925dd`)

`--self-test` 17/17 caught; `--check docs\design\12-cost-and-finops.md` green. `--quotas Pilot` has **no TEST rows**; `investigate` DEV planned 323.0 M / quota 485 M (the old TEST exam volume). `--quotas Team` still has TEST.

## Closure table

| ID | Status | Closing quote or what is missing |
|---|---|---|
| **TB-01** | **CLOSED** | `<repo>\docs\design\12-cost-and-finops.md` §1 How the model works: “if a quota exists for an environment that a scenario never creates (Pilot has no TEST account, so its exams and gates are quota'd in DEV)”. Self-test line: “caught: a TEST quota at Pilot scale, where no TEST account exists”. |
| **TB-02** | **CLOSED-WITH-RESIDUAL** | `<repo>\docs\design\05-agents-and-orchestration.md` §4 How the spine runs: “The euro cap is the **worst case of every metered part of the call** … **tokens** … the leaf's **own session compute**, vCPU and GiB for the role's **idle timeout** … **Content Safety records** … **metered tools**”; “An actual **above the reservation** … is **debited to the head**”; “The reservation id is `<case id>:<step>:<epoch>:<attempt>`”; “a restore **double-reserves, which is safe, and never reserves nothing**.” Residual: usage-record id and “how its lines are shared” still *to confirm* in S-COST-1; refuse of caller tier is *to confirm* in S-GW-1; compute is reserved **per call** at the idle timeout while 05 §5 bills **one session per role per case** (over-blocks, does not overspend). |
| **TB-03** | **CLOSED-WITH-RESIDUAL** | `<repo>\docs\design\12-cost-and-finops.md` §1: “if the table of 04 §4.3 disagrees with the model on a contract, its aliases, its pools or whether it has a PROD product; if the phase profile of [14 §4](../../design/14-next-phases.md#phase-and-capability-profiles) creates an environment in another phase than the one priced here”. Residual — `--check` still misses: (1) **11 §3** vs 14 (only 14 is parsed); (2) the **Agents** column of 04 §4.3; (3) 01 P4 / 05 roster **counts**; (4) a **consistent** wrong `FIRST_PHASE` if 14 is edited to match. Changing 04’s Agents cell, or 11 without 14, would not fail `--check`. |
| **TB-04** | **CLOSED** | `<repo>\docs\design\12-cost-and-finops.md` §2 (generated): “**Hosted-agent sessions of the evaluation case-runs** … Pilot: €77.00, of which €41.46; Team: €302, of which €162; Enterprise: €1,032, of which €556.” §7: “Event Grid operations for drift, cost and Activity Log signals (the first million a month is free, then €0.53 a million: Retail Prices API, Sweden Central, read 2026-11-01”. Lever 17 now points at that generated sentence. |
| **TB-05** | **CLOSED** | `<repo>\docs\design\05-agents-and-orchestration.md` §7 The token economy: “What caching is worth is a scenario, not a constant: about **a fifth** of a case's token cost when a prefix is written once per session (€0.68 with no cache, €0.55 warm), and *worse than no cache* when the prefix is rewritten on every call (€0.73)”. |

## New defects

### TB-N1 · Minor · File and heading `<repo>\docs\design\12-cost-and-finops.md` §6 How the system's own spend is governed

**Quote:** “tokens at the dearest alias and the dearest *service tier* the contract allows (the hub refuses a caller's own tier, so priority processing is not reachable, [04 §4.3](../../design/04-landing-zone-and-citadel.md#43-the-access-contracts))”

**Why it matters.** The refuse lives in 04 **§3.4** (“it **refuses any caller-supplied tier selector with a 400**”) and **§4.1**, not §4.3. A reader of the cited heading will not find the control. Not a spend path.

**Fix.** Point the link at §3.4 or §4.1.

No generated-block number disagreed with `--check` at this commit. Envelope `euros: 0.60` is labelled illustrative.

**Spend above reservation, beyond the stated in-flight token overrun:** only if (a) S-GW-1’s 400 does not actually strip `service_tier: priority` — Learn (https://learn.microsoft.com/azure/foundry/openai/concepts/priority-processing): a body `priority` on Standard is billed at Priority; 04 §4.1 already states that; or (b) idle is billed as **active + timeout**, not `max(active, timeout)`, which S-COST-1 still measures. Restore double-reserve is conservative. Cost Management latency is supported: “For EA and MCA subscriptions, cost and usage data is typically available in Cost Management within 8-24 hours. For pay-as-you-go subscriptions, it could take up to 72 hours” (https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data#cost-and-usage-data-updates-and-retention) — 05 §4 matches; 12 §6 layer 3 quotes only the 8–24 h figure for **Azure budgets**, which is the EA/MCA case, not a false claim.

## Verdict (four lines)

TB-01, TB-04 and TB-05 are closed; TB-02 and TB-03 are closed with named residuals (S-COST-1, S-GW-1, `--check` does not read 11). **ADR-26** should now read **Agree with changes**: the budget that holds is designed; what remains is measurement and the hub’s 400, not a missing meter. **ADR-06** should now read **Agree**: eleven groups / twelve contracts / no-PROD / phase floors are pinned by `--check` against 04 and 14. Do not flip ADR-26 to unqualified Agree until S-GW-1 shows the 400.
