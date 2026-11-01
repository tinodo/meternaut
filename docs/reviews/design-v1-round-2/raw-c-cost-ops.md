# Round 2 — C: Cost and operability

Reviewed commit: `7baddcf076713057f833059f61475b3e862546df` · reviewer: `gpt-6.1-sol`.
Review date: 31 October 2026; live vendor checks crossed midnight into 1 November CET. Assumptions: shared hub already funded; dynamic sessions and direct hybrid retrieval are the priced baseline; labour hours mean the whole crew's combined hours, not hours per person. No deployment, installation or price refresh was performed.

## Verdict — five lines

Direction: sound for a staged shadow pilot, not yet a verified production cost envelope.  
Arithmetic: the generated numbers reproduce; deployment and workload coverage do not.  
Controls: the quota disposition is untrue, and blended token prices are not spending caps.  
Operations: three people are necessary, not proof of sustainable staffing or one-day regional recovery.  
Must change: generate one phase-aware deployment/workload/contract inventory and check the bill and every limit against it.

## Findings

### C-01 · Critical · Quota closure is not true

**File and heading:** `<repo>\docs\design\04-landing-zone-and-citadel.md` · §4.3 The access contracts.

> The tokens per minute and per month of every contract are derived from the cost model for the scenario the contract must allow

**Why:** Reopens Round-1 C-04/A-08. There are twelve contracts, but the output omits `experiment`, `engineer`, `forge` and `examine-eu`; it emits `examine/exam`, not the declared contract/environment keys. No TPM, daily experiment quota, DEV/TEST scaling or numerical concurrency-overrun bound is generated. `<repo>\tools\cost-model.py` · `main`/`validate` reads only the snapshot and document 12: an instrumented read-only `--check` returned 0 without reading document 04. Validation checks its own generated quotas, not declared contracts.

**Fix:** Generate the exact contract/data-class/environment matrix, TPM, daily limits and overrun bounds; reject missing rows and mismatched deployment configuration. Add negative fixtures for each.

### C-02 · Major · Euro caps are forecasts

**File and heading:** `<repo>\docs\design\12-cost-and-finops.md` · §2 The results.

> The euro cap is the quota priced at the group's own blended price:

**Why:** Team `conduct` permits 30 M tokens and reports €3.32, but its contract also permits Sol: 30 M output tokens at the snapshot price cost €316.79. This is an upper-price illustration, not a predicted workload. The atomic reservation is the useful control; the blended-price column is not its worst-case bound. A concurrency multiplier without configured concurrency and maximum call cost is not a numerical bound either.

**Fix:** Rename the column as forecast-equivalent spend; independently generate enforced euro reservations and maximum-price/concurrency bounds, including fallback models and metered tools.

### C-03 · Major · Revised Flex billing mixes modes

**File and heading:** `<repo>\tools\cost-model.py` · `Model.scenario`, compute calculation.

> `max(0.0, gbs - 100_000) * fx`

**Why:** `fx` is the on-demand execution-time rate, applied to all executions after a grant, despite the always-ready instance. Microsoft distinguishes always-ready execution time and executions, without free grants [V1]. With the same Team execution seed, an illustrative all-always-ready calculation is €31.21, not €35.26; this is not a substitute estimate until the mode split is measured. The €21.024 baseline itself is correct.

**Fix:** Split always-ready/on-demand execution seconds and counts, grants by consuming subscription, and nonproduction instances. Keep replay billing explicitly unverified until S-ORCH-1.

### C-04 · Major · Standard Content Safety receives a Free-tier allowance

**File and heading:** `<repo>\tools\cost-model.py` · `Model.scenario`, token calculation.

> 5,000 free

**Why:** The selected meter is Standard, but 5,000 records are subtracted. The snapshot's own manual allowance belongs to the separate Free resource, which stops at its limit; the vendor table does not grant it to Standard [V2]. The erroneous credit is €1.65/month. More importantly, billing counts 1,000-character units, not calls: the forty-record case seed does not derive screening volume across the new free-text routes, response windows, exams and attacks.

**Fix:** Remove the unsupported Standard credit; seed characters, chunk overlap and screening calls per route, then measure them. The positive Language PII line and its unverified rate are improvements, not this defect.

### C-05 · Critical · Per-account floor closure remains incomplete

**File and heading:** `<repo>\docs\design\12-cost-and-finops.md` · §1 How the model works.

> an AI Search service, a Cosmos DB account and a Storage account

**Why:** Reopens C-01 only for the incomplete fix: Search multipliers and Foundry Cosmos quantities landed, but Foundry file/intermediate-blob capacity and transactions have no quantity or line. Nine vaults and 28/34/40 endpoints remain global seeds, not an application/environment inventory; nonproduction signing parties are not reconciled [V5]. Also, document 14 deliberately creates Search services on day zero, including ahead of their accounts, while the model couples Search floors to staged accounts.

**Fix:** Inventory each account, signing party, environment and endpoint subresource. Price the deliberate early Search reservation separately. Select the direct-hybrid baseline explicitly: enabling Foundry IQ needs retrieval-token quantities and its separate standard plan [V4], not a zero inferred from owning Search.

### C-06 · Major · An exam seed is not the revised gate plan

**File and heading:** `<repo>\docs\design\10-test-and-evaluation.md` · §4 Release gates / The statistical protocol.

> The demand of each gate is priced

**Why:** The model prices synthetic W4 plus 30% cloned judge work, not Forger generation, the named Claude Examiner/Atlas Librarian, two-family G5 judging or gate-by-gate quantities. W4 omits its Auditor; W5, W3b, W9 and W10 have no explicit workloads. Lab accounts are counted, but two-day experiment resources are not. The document's own 891-case comparison, run three times, needs 2,673 candidate runs before weekly cadence or other domains: already beyond Team's 1,350 monthly exam cases.

**Fix:** Generate a gate/domain/cadence/run-count plan with real aliases and human-review hours. Price Lab recipes and signal rates. Keep the existing narrow-claim/shadow fallback; do not thin statistical requirements to fit the seed.

### C-07 · Major · Cache fractions and writes do not reconcile

**File and heading:** `<repo>\tools\cost-model.py` · `CASE_WORK`.

> `tin=15_000, cached=0.70, cw=6_000`

**Why:** Under the documented single explicit static-prefix breakpoint, the Detective reads 10,500 cached tokens per call but writes a 6,000-token prefix. There is no explanation or price for populating the additional reusable prefix. The Economist has the same mismatch. Constraining reads to those written prefixes produces €0.540/case, before cold-start misses, versus €0.441. Explicit mode uses only explicit breakpoints [V3].

**Fix:** Model actual prefix lengths, first-call misses, expiry/burst boundaries and retained earlier breakpoints. Mark the baseline as a warm-cache scenario, not a proven saving.

### C-08 · Major · Recovery prices copies, not the copy process

**File and heading:** `<repo>\tools\cost-model.py` · `Model.scenario`, recovery lake.

> the copy traffic between regions is cents

**Why:** `(35 × ops_gb + ledger_gb) × 2` prices snapshots at one region's Cool ZRS rate; hourly delta volume, reads/writes, restore retrieval and cross-region transfer have no quantities. The peering line covers only hub traffic. Copying Enterprise's 100 GB daily snapshot for thirty days means 3 TB/month; the vendor's European intra-continental $0.02/GB gives approximately €52.80 before deltas [V6]. The ledger's two-Hot-ZRS proxy is not the declared GZRS SKU.

**Fix:** Price each copy's region, actual storage redundancy and transfer/operation meters; map its private route/DNS. Test watermark age including job duration/retries, not merely hourly scheduling.

### C-09 · Critical · Staged environments conflict with the release path

**File and heading:** `<repo>\docs\design\11-delivery-and-operations.md` · §3 Pipelines.

> deploy dev; L3–L5; promote to test when green

**Contradicting file and heading:** `<repo>\docs\design\14-next-phases.md` · §4 Phases.

> the test account in phase 3

**Why:** Reopens C-07's staged-creation closure, not its corrected minimum crew. Foundation/Study merges reach a pipeline that promotes to an account deliberately absent until phase 3; `pr-spoke` also expects a test hub. Either deployment fails or it creates an earlier floor than the advertised phase costs.

**Fix:** Make phase/capability profiles control deployment targets and applicable gates; preserve the deliberate day-zero Search exception. Prove phase-0/1 releases without creating TEST/Lab accounts.

### C-10 · Minor · SRE comparison retained its old compute premise

**File and heading:** `<repo>\docs\design\13-decisions.md` · ADR-27 The system operates itself; SRE Agent is off by default.

> at a fixed cost larger than the rest of the compute.

**Why:** €283 exceeds Pilot compute (€147), not revised Team (€458) or Enterprise (€4,145). Keeping it off is reasonable, but renting diagnostics could beat more than approximately 3.77 crew-hours/month at €75/hour, before active-flow charges [V10].

**Fix:** Qualify the Pilot comparison; evaluate incremental labour and active-flow costs, not just the floor.

### C-11 · Minor · Recovery ADR describes the wrong boundary

**File and heading:** `<repo>\docs\design\13-decisions.md` · ADR-30 Recovery is redeploy from code with no second region in phase 1.

> no standing second region

**Why:** The revised recovery design explicitly requires second-region storage and an hourly-metered endpoint. What is absent is a second compute estate, not a standing second-region footprint. The ADR's generic doubled-floor rationale obscures this distinction.

**Fix:** Say no warm second compute estate; name the required dual-region storage and the conditional capacity assumptions behind the one-working-day RTO.

## Disposition audit

All fourteen requested ids were checked against their changed sections; closed portions are not re-raised.

| Round-1 ids | Result and inspected evidence |
|---|---|
| C-01 | Partial: per-account Search/Cosmos landed; C-05 above covers incomplete accounting. `<repo>\docs\design\12-cost-and-finops.md` §1–2; `<repo>\docs\design\04-landing-zone-and-citadel.md` §7. |
| C-02, C-03 | Positive PII, sandbox and red-team lines landed, with uncertainties labelled. `<repo>\docs\design\12-cost-and-finops.md` §1–2. Additional revised-workflow omissions: C-06. |
| C-04, A-08 | Not closed: C-01 above. `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.3; `<repo>\tools\cost-model.py` · `validate`/`main`. |
| C-05 | Old false-counted claim removed; peering and corrected firewall rates landed. `<repo>\docs\design\04-landing-zone-and-citadel.md` §3.2/§7; `<repo>\docs\design\12-cost-and-finops.md` §2/§7. |
| C-06, E-09 | Marginal/all-lines/labour distinctions, shares, Enterprise 0.22% and family-qualified residency premium landed correctly. `<repo>\docs\design\12-cost-and-finops.md` §2–3. |
| C-07 | Three-role crew landed; staged pipeline contradiction remains C-09. `<repo>\docs\design\11-delivery-and-operations.md` §3/§7.2; `<repo>\docs\design\14-next-phases.md` §4. |
| C-08 | Session-weighted hosted hours and session/burst cache wording landed. `<repo>\docs\design\05-agents-and-orchestration.md` §7; `<repo>\tools\cost-model.py` · `HOSTED_SESSIONS`. Idle billing remains a conservative assumption; the GA announcement says active execution only [V11]. |
| A-11 | Synapse's zero-idle alternative and a benchmark/expiry requirement landed [V9]. `<repo>\docs\design\06-data-and-knowledge.md` §7.4. Cheapest remains a hypothesis pending S-DATA-1. |
| A-15 | W3b and S-FAST-1 landed; no dedicated cost seed yet. `<repo>\docs\design\05-agents-and-orchestration.md` §3; `<repo>\docs\design\14-next-phases.md` §3. |
| A-16 | Purchase execution stays disabled until agreement-specific proof. `<repo>\docs\design\14-next-phases.md` §2/§4. |
| E-10 | Three EU Serverless regions and Sweden's creation warning confirmed [V7]. `<repo>\docs\design\04-landing-zone-and-citadel.md` §3.2. |

## Independent arithmetic and §3 interpretation

Inputs: `<repo>\docs\design\cost\prices-snapshot.json` · `meters`/`fx`, and `<repo>\tools\cost-model.py` · scenario/workload seeds. These are independently multiplied, not accepted from the generator. **All eleven checks below match §2's generated table or its component lines from `--lines Team`; matching arithmetic does not validate the billing assumptions.**

| Check | Hand derivation, euros |
|---|---|
| Always-ready / Team spine | `2 × 3600 × 730 × 0.000004 = 21.024`; current formula adds `(717000−100000)×0.000023 + (358500−250000)/10×0.000004 = 14.2344`, giving **35.2584**. Billing defect: C-03. |
| Search | `2/3/5 × 730 × 0.088877` = **129.76 / 194.64 / 324.40**. |
| Team endpoints | `34 × 730 × 0.0088` = **218.416**. |
| Hosted hours | Session minutes `17+11+10+17+5=60`; `(2350×60/60)+40+125+15=2530 h`; `2530×(0.096216+2×0.011422)` = **301.2218**. |
| Semantic ranker | `(20000+4000+3000−1000)/1000 × 0.879972` = **22.879272**. |
| Recovery capacity | `(35×10+5)×2×0.01144` = **8.1224**. |
| Detective / case | `[10×(4500×2.111932+10500×0.105597+1500×10.559662)+6000×2.639916]/1M` = **0.280359051**. Other roles **0.029040+0.091763468+0.038120381+0.002193776** give **0.441476677** total. |
| Investigate quota/cap | `1000×[10×16500+4×13000+4×11000]=261 M`; `ceil(261×1.5)=392 M`; `401.162519×392/261` = **602.512289**. |
| Signing-party Defender | `5×730×0.006072 + 9×730×0.000299` = **24.12723**. Six named signing parties plus three other vaults are seeded; instantiated environments remain uncounted. |
| Sandbox / PII | `2350×0.026399` = **62.03765**; `(1500+2000)×10/1000×0.88` = **30.80**, with the PII rate **UNVERIFIED**. |
| Break-even / labour | `2024.02/400000×100=0.506005%`; adding `40×75` gives **1.256005%**. At 40 h Pilot is **19.04595%**, Enterprise **0.25301525%**. |

§3's **16% residency saving** is `1−0.370097196/0.441476677 = 16.168%`; cache savings are **34.696%** once/session and **6.433%** every call. Cloud/all-lines per case **€8.09/€2.02/€0.86**, the evaluation-to-case ratios and labour sensitivity reproduce. They are conditional scenarios: Pilot capability-not-payback is sensible framing, not proof that no Pilot can pay back.

DTS alternative: `730×0.783537=€571.98/CU`, **€1,715.95** for three-CU HA. The live Consumption meter is **€0.003432 per action**: 705,000 activity start/result actions alone imply **€2,419.56**, before other actions and compute [V12]. Zero idle does not make it the cheaper Team backend.

## Can three people operate this?

From `<repo>\docs\design\11-delivery-and-operations.md` §2–3/§7, `<repo>\docs\design\07-security-architecture.md` §10.2, `<repo>\docs\design\09-safeguards-and-drift-controls.md` §2/§5 and `<repo>\docs\design\14-next-phases.md` §3:

- Six stack layers; eight named workflow jobs in seven table rows (`nightly`/`weekly` separate; `drift` is runtime governance); fifteen runbooks; twenty detections; eighteen drift layers.
- Twelve contracts, potentially **36 access products across DEV/TEST/PROD**, plus backend/publish configuration; nine seeded vaults; fourteen roles/fifteen identities per roster, instantiated counts unspecified.
- **32 spikes**, thirty numerically timeboxed, totalling **86 working-day limits**; eighteen dependency-register rows, seventeen containing preview/prerelease/experimental elements, including disabled and GA-with-preview-API entries.
- Seven weekly obligations: full exam, attacks, cost report, image rebuilding, lease review, W9 and W10; nightly exams, model alarms, chain verification and fallback-image builds add load.

This is runnable **conditionally**, recoverable only after the drills—not a demonstrated 20/40-hour monthly service. The six-day S-ORCH-1 box cannot contain a real thirty-day soak; distinguish engineering effort from elapsed qualification. Three people leave no release-review cover when one is absent.

**Cut first:** default to direct hybrid retrieval, typed queries and the GA hosting fallback; activate only phase-relevant leaves/contracts. Keep real minimum statistics, approvals and fail-closed recovery. Before claiming one-day regional RTO, demonstrate second-copy connectivity and recreatable Search/Foundry capacity with the primary region unavailable.

## Decision table — all 37

Source: `<repo>\docs\design\13-decisions.md` · Decisions / ADR-01–ADR-37. Alternatives below include why rejection is or is not justified.

| ADR | Verdict | Confidence | Strongest alternative; assessment | What would change my mind |
|---|---|---|---|---|
| 01 | Agree | High | Handoffs: fewer schemas, weaker deterministic accounting. | Lower all-in cost with identical denial/retry proofs. |
| 02 | Agree with changes | High | Native APIM: less fork upkeep; contract parity unproven. | Parity tests and measured fork-maintenance hours. |
| 03 | Agree with changes | High | One nonprod account: cheaper, shared data boundary. | S-NET-2 isolation and complete environment inventory. |
| 04 | Agree with changes | Medium | Hub-local West Europe: unused capabilities weakly justify rejection. | Required-capability, creation and regional-cost proofs. |
| 05 | Agree | High | Managed VNet: simpler, unshareable firewall floor. | Equivalent outbound evidence at lower all-in cost. |
| 06 | Agree with changes | High | Coarse groups: fewer contracts, weaker tool separation. | Verified tokens/roles and actual generated contract limits. |
| 07 | Agree with changes | High | PIM active assignments: simpler, workload support unproven. | Licensed activation, fencing and revocation proofs. |
| 08 | Agree | High | Teams Approvals: simpler, target binding unproven. | Independent signature/target/replay verification. |
| 09 | Agree with changes | High | Terra first: cheaper; quality not yet established. | S-MOD-3 plus measured cold/warm-cache bills. |
| 10 | Agree with changes | Medium | Same-family judge: simpler, correlated blind spots. | Human-labelled independence benefit and actual judge cost. |
| 11 | Agree with changes | High | Direct hybrid: avoids IQ metering; accept baseline. | Measured paid-IQ retrieval gain and token quantities. |
| 12 | Agree with changes | High | SQL serverless: relational guarantees, different schema/latency. | Reservation consistency, RU and restore comparisons. |
| 13 | Agree with changes | High | Synapse serverless: zero idle too; must benchmark. | Twenty-query cost/operations comparison. |
| 14 | Agree | High | Platform memory: convenience, extra ownership/poisoning surface. | Private GA operation, hub accounting and erasure proof. |
| 15 | Agree with changes | High | Typed HTTP: less protocol surface, less reuse. | MCP authorization and overhead measurements. |
| 16 | Agree with changes | High | Shared Lab: simpler, larger experiment boundary. | Priced recipes and automatic cleanup under ceilings. |
| 17 | Agree | Medium | Mail/web first: fewer adapters, weaker card experience. | Adoption and adapter-maintenance measurements. |
| 18 | Agree with changes | High | Central workspaces: less ownership, access boundary to prove. | Table compatibility, alert/query charges and access tests. |
| 19 | Agree with changes | High | In-house gate: fewer previews, still owned code. | Whole-text attack coverage and latency/cost evidence. |
| 20 | Agree | High | Full licence stack: broader coverage, entitlement/cost burden. | Priced licensed profile and tested weaker fallback. |
| 21 | Agree with changes | High | Policy only: simpler, misses data-plane/behaviour drift. | Detector coverage and maintenance-hour measurements. |
| 22 | Agree with changes | High | Own harness only: avoids preview dependency; L4 indispensable. | Gate-by-gate quantities, cost and human-review hours. |
| 23 | Agree with changes | High | Azure DevOps: native accelerator route, migration burden. | Trusted, phase-aware private release and entitlement proofs. |
| 24 | Agree | High | CMK everywhere: more control, no named driver yet. | Mandated requirement and complete key-lifecycle cost. |
| 25 | Agree | High | Regional only: stricter locality, fewer choices. | Required tighter boundary or lower verified regional cost. |
| 26 | Disagree | High | Spine euro reservation: must be primary, not blended caps. | All contracts/limits validated with overrun bounds. |
| 27 | Agree with changes | High | SRE Agent: rent diagnostics, not approval controls. | Trial labour savings net of active-flow charges. |
| 28 | Agree | High | Two repositories: clearer isolation, duplicate release work. | Path-guard failure or lower measured merge overhead. |
| 29 | Agree | Medium | Premium templates: useful for audit, not core enforcement. | Named audit requirement and priced evidence gap. |
| 30 | Agree with changes | High | Warm region: faster recovery, higher floor. | Cold regional drill meets one day with capacity available. |
| 31 | Agree | High | Floating versions: lower upkeep, unreproducible recovery. | Demonstrated reproducible rollback without version pins. |
| 32 | Agree with changes | High | Confidential Ledger: outsources chain, €103 floor. | Custom ledger maintenance below 1.37 h/month and drills. |
| 33 | Agree with changes | High | DTS Dedicated: fewer backend operations, €572/CU. | Correct mode billing and backend cost/latency comparison. |
| 34 | Agree | High | Routines: fewer owned clocks, unsettled support. | GA support, envelope, accounting and cancellation proof. |
| 35 | Agree with changes | High | Existing hub only: less fork work, narrower adoption. | Confirmed hub owner, allocation and maintenance commitment. |
| 36 | Agree | High | All Python: one toolchain, less shared static enforcement. | Equivalent proofs with lower measured lifecycle cost. |
| 37 | Agree with changes | High | Typed queries: avoid code/meter; strongest default. | S-SBX-1 isolation, EU availability and actual charges. |

## Vendor evidence

Live reads; each excerpt is at most 25 words. Snapshot arithmetic remains explicitly frozen.

- **V1** [Flex plan · Billing](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan): “In always ready billing, there are no free grants.”
- **V2** [Content Safety pricing · FAQ](https://azure.microsoft.com/en-us/pricing/details/content-safety/): “Usage is stopped if the transaction limit is reached on the Free tier.”
- **V3** [Prompt caching · Configure prompt cache breakpoints](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching): “Azure OpenAI uses only explicit breakpoints for cache reads and writes.”
- **V4** [Search pricing · Overview](https://azure.microsoft.com/en-us/pricing/details/search/): “Foundry IQ knowledge bases require a subscription and a standard agentic retrieval plan.”
- **V5** [Key Vault RBAC · Best Practices](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide): “use a vault per application per environment”.
- **V6** [Bandwidth pricing · Inter Region](https://azure.microsoft.com/en-us/pricing/details/bandwidth/): “$0.02 per GB”.
- **V7** [Search regions · Europe](https://learn.microsoft.com/en-us/azure/search/search-region-support): “This region is in high demand, which prevents the creation of new search services.”
- **V8** [Graph · signIn resource type](https://learn.microsoft.com/en-us/graph/api/resources/signin?view=graph-rest-1.0): “You must have a Microsoft Entra ID P1 or P2 license to download sign-in logs by using the Microsoft Graph API.”
- **V9** [Synapse pricing · Serverless](https://azure.microsoft.com/en-us/pricing/details/synapse-analytics/): “You only pay for executed queries”.
- **V10** [SRE pricing · Always-on flow](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing): “4 AAUs per agent-hour”.
- **V11** [Hosted agents GA · description](https://www.microsoft.com/releasecommunications/api/v2/azure/563596): “Agents are suspended between conversation turns, so you pay only for active execution.”
- **V12** [DTS billing · What is an action?](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-billing): “Processing the result of an activity, entity call, entity lock, or suborchestration”.
- **V13** [Container Apps pricing · Consumption plan](https://azure.microsoft.com/en-us/pricing/details/container-apps/): “Azure Container Apps Express and Sandboxes follow the same pay-per-second pricing as Consumption Plan.”
- **V14** [Managed VNet · Select Azure Firewall version](https://learn.microsoft.com/en-us/azure/foundry/how-to/managed-virtual-network): “The default SKU is Standard for the Firewall.”

Additional checks: [standard setup](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/standard-agent-setup), [Serverless limits](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity), [BYO networking](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/networking-options), [Storage provider/Flex recommendations](https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-azure-storage-provider), [Language pricing](https://azure.microsoft.com/en-us/pricing/details/language/), and [Sandbox GA record](https://www.microsoft.com/releasecommunications/api/v2/azure/561262). PII amounts and dynamic-session rounding remain **UNVERIFIED**; Sandbox GA and its per-second pricing basis are confirmed, EU availability remains unverified.

Live Retail API query, including the unusual Consumption action unit, exactly as fetched: [DTS EUR meters](https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&currencyCode=EUR&%24filter=serviceName+eq+%27Durable+Task+Scheduler%27+and+armRegionName+eq+%27swedencentral%27). Live Flex, hosted-compute, Sol and GZRS selectors also matched their reported rates; GZRS capacity was €0.040479/GB-month.

## What is strong

Keep the reproducible snapshot, generated block and exact selectors; budgets reserved outside agent judgement; corrected marginal/cloud/labour distinctions; separate signing authorities and fail-closed ledger; staged activation; conservative cache/idle disclosures; explicit licence fallback. D13's P1/P2 dependency is real [V8], and §7 correctly excludes it rather than pricing it at zero.

Read-only checks: `--lines Team`, `--quotas Team`, `--check`, and `python -B tools\check-docs.py --strict` passed; the documentation checker reported 54 documents, zero errors/warnings.

## What is missing — five priorities

1. Exact, enforced contract/quota/euro/concurrency configuration, independently checked.
2. Instantiated account/vault/endpoint/storage inventory, including early reserved Search capacity.
3. Complete gate, signal, learning and Lab workloads with genuine model aliases.
4. Metered regional export/restore and capacity-qualified recovery evidence.
5. Crew-hours, reviewer cover and phase-aware operational qualification—not just a headcount.

**Findings: 3 Critical · 6 Major · 2 Minor.**
