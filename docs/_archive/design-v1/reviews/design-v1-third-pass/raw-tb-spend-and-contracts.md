# T-B third pass — spend budget and contract × environment model

Reviewed commit `6694d15`. Lens T-B. Model did not review rounds 1–2.

## 1. Verdict (five lines)

The reservation-is-the-budget redesign is the right shape, and the generated block of 12 is arithmetically honest: five headline numbers re-derived from the snapshot, `--check` green, `--self-test` green. It is not yet a budget that *holds*. The spine reserves an envelope euro cap of tokens (and “metered tools”) while hosted-agent vCPU/memory, the idle tail, Content Safety and sandbox hours bill outside that cap; settlement of actual > reserved is unspecified; the hub usage header is still *to confirm*. The twelve-contract matrix agrees on names; it disagrees on *where work runs at Pilot*: exams and gates are quota’d on TEST, which Pilot never has, and `--check` cannot see that. That is the one thing that must change: pin every workload to an environment the phase profile actually creates, and put non-token meters into the same atomic reservation or name them as a residual with a number.

## 2. Findings

### TB-01 · Major · File and heading `<repo>\docs\design\14-next-phases.md` §4 Phase and capability profiles; `<repo>\tools\cost-model.py` `workloads`; `<repo>\docs\design\10-test-and-evaluation.md` §5 Environments and promotion

**Quote (14):** “At Pilot scale there are only DEV and PROD accounts ([12](12-cost-and-finops.md)), and the first Moves are rehearsed in DEV by the dry-run runner.”  
**Quote (10 §5):** “until TEST exists DEV carries the exams and the gates run there.”  
**Quote (cost-model.py):** “exams and gates run W4 on synthetic estates in the TEST environment”

**Why it matters.** `python tools/cost-model.py --quotas Pilot` still emits a full TEST matrix (`investigate` TEST planned 322.4 M tokens, quota 484 M; `examine-pub` TEST 125.4 M / 189 M). Pilot `SCENARIOS` has `accounts=2`, `envs=2` and `t3_cases=0`. The DEV `investigate` row is 2.6 M planned / 4 M quota — smoke tests only. Sequence: phase 0–6 at Pilot never create TEST (11 §3: “at Pilot scale there is no TEST account”); W8 and G3/G4 still run; if they follow 10/14 they hit DEV products whose quota is ~80× too small and the hub 403s the gate; if they follow the model they deploy TEST products on an account that does not exist. `--check` passed anyway.

**Fix.** Drive `workloads()` and `quotas()` from the same `phase_floor` / `accounts` inventory: when TEST is absent, exam/gate/red-team/forger rows go to DEV (and DEV floors become those volumes, not 10 % of PROD). Fail `--check` if a quota row’s environment is not in the scenario’s `present` list. Do not re-raise C-01/C-09 as such: those asked for generated quotas and a phase profile; this is the new seam between the two.

### TB-02 · Major · File and heading `<repo>\docs\design\12-cost-and-finops.md` §6 How the system's own spend is governed; `<repo>\docs\design\05-agents-and-orchestration.md` §4 How the spine runs (Budget reservation); `<repo>\docs\design\13-decisions.md` ADR-26

**Quote (12 §6):** “Before each leaf call the spine **reserves the call's worst-case cost atomically** (tokens at the dearest alias the contract lists, and the metered tools the call may use) against the case's and the group's budget”  
**Quote (05 §4):** “reserves the call's worst case — the envelope's euro cap — against two heads in the operational store (`budgets`”  
**Quote (05 envelope):** “budget: { tokens: 150000, euros: 0.60, seconds: 300, tool_calls: 25 }”

**Why it matters.** Attack question 1, path by path:

| Path | Closed / bounded / open |
|---|---|
| Parallel leaves racing one head | **Closed** if Cosmos filter predicates work: 06 §7.2 `budgets` “a reservation is created and its head patched in one transactional batch”; 05 “conditional patch … so a retried activity cannot reserve twice.” Two heads are two partitions / two batches; a crash between them is a retry of the same reservation id. |
| Cheapest alias vs dear failover | **Bounded for aliases on the contract** (ADR-26: dearest listed alias). **Open for Priority processing**: Learn (deployment types, fetched 2026-11-01, https://learn.microsoft.com/azure/ai-foundry/openai/how-to/deployment-types) “Data Zone Standard supports priority processing for faster response times on a pay-as-you-go basis.” The hub strips `x-ms-service-tier` for Flex; it does not say it forbids Priority. A Priority call is not the listed Standard rate. |
| Retry / replay / `:<epoch>` | **Closed for retries** (same reservation id). **Open on restore:** 05 “keys on every effect (reservation id …) are what let a re-opened step find what the first run did”; the envelope id `rsv-c-0042-skeptic-2` has no epoch. A new reservation id on `<workflow>:<case id>:<epoch>` double-reserves; reusing a settled id reserves nothing. |
| Settlement / refund | **Open.** “When the hub's usage record arrives (the reservation id travels in a header the record keeps — *to confirm* on our hub), a deterministic reconciler replaces the reservation with the actual spend; one with no record after a day stays reserved.” Staying reserved over-blocks; it does not debit actual > reserved. Hub usage is tokens, not hosted-agent GB-s. |
| Non-token meters | **Open, unnumbered.** Hosted-agent vCPU and memory (Pilot line €87.47 vs W4 tokens €54.46), idle tail (priced as billed, UNVERIFIED), Content Safety (€47.30), sandbox hours (€34.16), Functions executions, Search queries, Lab recipes. 12 §6 names “metered tools”; the leaf’s own compute is not a tool. Envelope `euros: 0.60` is a token cap (Skeptic marginal tokens €0.029 in 12 §2). After `POST /invocations` returns, compute stays up until the idle timeout (05 §5); that tail is never reserved. |
| Lab | **Bounded.** 07 §8: no experiment starts before the budget exists; structural SKU/quota cap for up to 48 h; pre-deploy price-engine cap (`LAB_EUR_PER_EXPERIMENT = 25.0`, a seed). Not the spine reservation. |
| Gates/exams in the pipeline | **Open at Pilot (TB-01).** If they are W8 on the spine they reserve; G6 only fails a *release*, it does not stop a running loop. |
| Leaf ignores envelope | **Bounded** by hub `llm-token-limit` after the counter moves, plus in-flight column. Learn (https://learn.microsoft.com/azure/api-management/llm-token-limit-policy, fetched 2026-11-01): “concurrent or near-concurrent requests can temporarily exceed the configured token limit.” That is the stated residual, not hosted-agent euros. |

**Fix.** Put hosted-agent (active minutes and idle timeout), sandbox, Content Safety records and Functions GB-s into the same conditional patch, converted at the snapshot rates, or print a residual euro bound next to the in-flight token column. Pin reservation id = `<case>:<step>:<epoch>`. Fail closed if the hub usage header is absent (S-GW already *to confirm*). Refuse `service_tier=priority` at the hub.

This is not a re-raise of C-02 (euro “caps” were forecasts). Round 2 made the *token* column honest; non-token spend was left beside the budget.

### TB-03 · Major · File and heading `<repo>\tools\cost-model.py` `check_contracts` / `check_rows`; `<repo>\docs\design\12-cost-and-finops.md` §1 How the model works; `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.3 The access contracts

**Quote (12 §1):** “`--check` fails if a quota would block planned work, if a contract of the table in 04 is missing from the model or priced with other aliases”  
**Quote (04 §4.3):** “`tools/cost-model.py --check` parses **this table** — the contract names and, in the fourth column, each contract's alias set — and fails on a missing or extra contract or a different alias set”

**Why it matters.** `doc_contracts` takes only `` `[a-z-]+` `` in column 1 and `\b(triage|reason|judge-eu|judge-pub|embed|batch)\b` in column 4. `check_rows` requires a DEV row and `quota ≥ 1.2 × planned`. Changes `--check` would **not** catch: (1) adding a PROD product for `examine-pub` or `forge` in 04 prose or in Bicep; (2) giving Pilot a TEST row (TB-01); (3) swapping pools (`acia-eu` vs `acia-global`) or data class; (4) adding an alias the regex does not know (`priority`, `luna`, `acia-reason`); (5) changing Agents or Safety; (6) TPM/overrun figures; (7) 14’s phase floors vs quota environments. Disposition 2.5 claimed `--check` “parses the contract table of 04 §4.3 and fails on a missing or extra contract or a different alias set” — true, and narrower than “the contract × environment model”.

**Fix.** Parse environment presence (`no PROD product`), pool names, and the scenario’s `present` environments; extend the alias regex from `CONTRACT_ALIASES`; fail on a quota row for an environment the inventory does not create.

### TB-04 · Minor · File and heading `<repo>\docs\design\12-cost-and-finops.md` §5 Levers, in order (row 17); §7 What the model leaves out

**Quote (12 §5 lever 17):** “the sessions and the idle tail of the TEST case-runs (about €300 a month at Team scale, of which about €160 is the idle tail)”

**Why it matters.** Every other sensitivity in §2 is generated. Lever 17’s €300 / €160 do not appear in the generated block or in `monthly_sensitivities()`. They are unlabelled seeds. §7 correctly omits Entra P1/P2, GitHub minutes, Agent 365 (optional table), internet egress “cents”, Bot Service, Event Grid, Service Bus (avoided), storage transactions. Log Analytics *is* a line (Pilot €2.37). Event Grid for drift alerts is not a line. Optimistic: Content Safety “screened once where the text enters” (named sensitivity if every prompt is screened: Pilot +€699); Flex share 80 % (named); hosted idle billed (named). Missing meter that would move a decision: Event Grid at Enterprise signal volume — not a budget hole, a completeness hole.

**Fix.** Generate lever 17 from `HOSTED_SESSIONS` × TEST case-runs, or mark it a seed like labour.

### TB-05 · Minor · File and heading `<repo>\docs\design\05-agents-and-orchestration.md` §7 The token economy — incomplete C-07

**Quote (05 §7):** “What caching is worth ranges from a few percent to about a third of a case's token cost ([12 §3](12-cost-and-finops.md#3-reading-the-numbers))”  
**Quote (12 §3):** “the saving is a fifth, not the third that a 70 %-cached seed implied”

**Why it matters.** Disposition 2.6 C-07 accepted the fifth. 05 still cites 12 and says “about a third”. Not a spend-path bug; it is the Round-2 honesty claim contradicted in the token-economy section.

**Fix.** Replace “about a third” with 12’s range (€0.68 → €0.55, a fifth; rewritten every call €0.73).

## 3. ADR verdicts

| ADR | Verdict | Confidence | Strongest alternative | What would change my mind |
|---|---|---|---|---|
| **26** The spine's reservation is the budget; the hub's limits are a second layer | **Agree with changes** | 0.7 | Budget-triggered disable of the product (rightly rejected: daily, 8–24 h lag, stops nothing). Making the hub the cap was C-02; do not go back. | S-COST-1 bill showing hosted idle *and* Content Safety inside the reconciled euro head; hub usage carrying `reservation_id`; Priority stripped. If hosted idle is free and tools are in the patch, Agree. |
| **06** An Entra agent identity per agent and eleven contract groups | **Agree with changes** | 0.8 | Merge 12 → 8 (A-11, not adopted): cheaper, mixes data class and budget heads. Isolation is the point of the budget. | `--check` pinning environments and pools (TB-03) so the matrix cannot drift; S-ID-2 showing distinct `azp`. If eleven groups cannot be generated per phase, Disagree and cut by phase only. |

ADR-04/05/30 were read as context; not T-B subjects.

## 4. What is strong

Counts agree: 01 P4, 04 §4.3, 05 §2, 07 §2/§5.1, 12 §2 and `CONTRACT_ALIASES` — fourteen roles, fifteen identities, eleven groups, twelve contracts; `examine-pub` and `forge` have no PROD row in the Team table; `engineer`/`govern` EU-only. Phase floors in 12 §2 (1/1/1 → 2/2/2 → 2/3/3 → 2/4/4) match 14 §4, 11 §3 and `phase_floor()`. Forecast-equivalent vs worst-case split answers C-02 (`conduct` Team PROD €3.96 vs €370). In-flight column is concurrency × largest call at the dearest rate (investigate PROD 12 × 21,500 = 258 K, €2.72).

Re-derived from `docs/design/cost/prices-snapshot.json` (2026-10-31T20:44:12Z, EUR/USD 0.87997), matching the generated block:

- Detective marginal, Sol ShortCo DZ: inp €2.111932, out €10.559662, cd €0.105597, cw €2.639916 / 1M → **€0.370** (12 §2).
- Flex Always Ready Baseline €4e-06 / GB-s × 2 GB × 3600 × 730 = **€21.02** (12 §4 “about €21”).
- AI Search Basic Unit €0.088877/h × 730 = **€64.88**; Pilot 2 units **€129.76**.
- PE Standard €0.0088/h × 730 = **€6.424**; 32 × = **€205.57**.
- Pilot total **€1,243.58** → **€1,244**; tokens 52 %, compute 13 %, fixed 35 %; break-even 6.22 %.
- Content Safety Standard Text Records €0.329989 / 1k × 143,340 = **€47.30**.
- Hosted 1,469 h × (0.5 × €0.096216 + €0.011422) = **€87.45** ≈ €87.47.
- DZ vs Global Sol input 2.111932/1.759944 = **+20 %** (12 §3). Cache write/input = **1.25×**. No-cache €0.682 → warm €0.545 = **a fifth**.

Platform claims (fetched 2026-11-01): `llm-token-limit` concurrent overrun — “concurrent or near-concurrent requests can temporarily exceed the configured token limit” (https://learn.microsoft.com/azure/api-management/llm-token-limit-policy). Flex always-ready — “In always ready billing, there are no free grants”; “no fewer than two always-ready instances … while zone redundancy is enabled” (https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan). Hosted agents — “Billing is based on cpu + memory consumed across all active sessions”; idle timeout 2–240 min, default 15; idle *price* **UNVERIFIED** (https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents). Prompt cache — “On GPT-5.6 models and later … cache writes can incur charges”; reads discounted (https://learn.microsoft.com/azure/ai-services/openai/how-to/prompt-caching). Deployment types — Global Standard lowest price; Data Zone Standard pay-per-token in-zone; Batch “50% less cost”; Flex on Global Standard; Data Zone Standard documents Priority, not Flex (https://learn.microsoft.com/azure/ai-foundry/openai/how-to/deployment-types). DTS Dedicated = CU/month, Consumption = per action, no HA (https://learn.microsoft.com/azure/durable-task/scheduler/durable-task-scheduler-billing). Content Safety F0/S0; Standard meter has no free grant in the snapshot.

`--self-test` and `--check docs/design/12-cost-and-finops.md` both passed at this commit.

## 5. Still unproven (run first)

1. **S-COST-1** — hosted idle billed or not; cache writes per session vs per call; reservation vs bill on 100 cases (the reservation residual is a number only after this).
2. **Hub `reservation_id` header** — 05 §4 *to confirm*; without it settlement is fiction.
3. **Pilot/phase exam routing** — TB-01; a contract test that DEV at Pilot can actually run G3/G4 under its quota.
4. **Priority processing and model-router failover** — does the hub pin Standard rates, or can Foundry bill Priority / a dearer member?
5. **Subscription TPM vs generated TPM** — examine-pub TEST 704 K tokens/min, investigate PROD 516 K. Learn quotas are tiered and, from May 2026, subscription-pooled (https://learn.microsoft.com/azure/foundry/openai/quotas-limits). 14 §5 already asks for GPT-6 quota requests; until the tier is known, 704 K is a hope. Default Free/Tier-1 **UNVERIFIED** for GPT-6.1 Sol in Sweden Central.
