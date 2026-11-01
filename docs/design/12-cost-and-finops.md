# Design 12 — Cost and FinOps

> **What this answers:** *What does the system cost to run at three scales, where does the money go, which parts are always on and why, and how is the system's own spend governed?* The numbers are not typed into this document: they are produced by [`tools/cost-model.py`](../../tools/cost-model.py) from a reproducible [price snapshot](cost/prices-snapshot.json), so a changed price list changes the document, not our memory of it. Cost is a design constraint ([C7](01-requirements-and-principles.md#1-constraints--what-is-not-negotiable), [Q-COST-1](01-requirements-and-principles.md#4-quality-targets)); the choices it shaped are in [13](13-decisions.md). Part of the [design](README.md).

---

## 1. How the model works

1. **Prices.** `tools/fetch-prices.py` reads the Azure Retail Prices API with the queries in [`cost/price-queries.json`](cost/price-queries.json) and writes the [snapshot](cost/prices-snapshot.json): about 2,500 meters in euros and dollars, for Sweden Central, West Europe, North Europe and global meters, plus allowances that only a pricing page states, each **checked against the pricing page it came from**. The method and its checks are in the [price research](research/prices.md).
2. **Selectors, not memory.** Every line of the model names its meter with an exact selector. A selector that matches nothing, or matches two different prices, **stops the run** — so a renamed meter can never silently change a number.
3. **Seeds.** The quantities — cases a month, tokens per call, hours of compute — are **seeds** in the script, chosen to be plausible and *wrong in the useful direction* (generous). Spike **S-COST-1** replaces them with measurements ([14](14-next-phases.md#3-spike-register)).
4. **Scenarios** are those of [A6 in 01](01-requirements-and-principles.md#2-assumptions): **Pilot** (5 subscriptions, about 500 resources, 5 people), **Team** (50, about 10,000, 100) and **Enterprise** (1,000, about 200,000, 2,000). Each scenario also fixes the number of **private Foundry accounts**, one per environment ([04 §7](04-landing-zone-and-citadel.md#7-the-foundry-layout)): Pilot 2 (development and production), Team 4 (adds test and the Lab), Enterprise 4. Each account brings its own standard-setup trio — an AI Search service, a Cosmos DB account and a Storage account — so **each is priced as a floor of its own**; accounts are created in the phase that needs them ([14 §4](14-next-phases.md#4-phases)), except the AI Search services, which are created on day zero and are priced by phase in the floor table. The **inventory** (accounts, Search units, spine and chain environments, vaults, endpoints) is printed with the results, so the floor is a count, not a seed.
5. **Quotas come from the same plan.** The model lists every token workload with its **contract** and **environment**, prices it, and derives from the same list the monthly token quota of every one of the **twelve contracts** of [04 §4.3](04-landing-zone-and-citadel.md#43-the-access-contracts) in every environment where it has planned work, with a starting tokens-per-minute limit, a daily quota for `experiment` and an in-flight overrun bound. The hub's limits are therefore *outputs* of the model, not seeds typed next to it. `--check` fails if a quota would block planned work; if the table of 04 §4.3 disagrees with the model on a contract, its aliases, its pools or whether it has a PROD product; if the phase profile of [14 §4](14-next-phases.md#phase-and-capability-profiles) creates an environment in another phase than the one priced here; if a quota exists for an environment that a scenario never creates (Pilot has no TEST account, so its exams and gates are quota'd in DEV); or if the summed forecast-equivalent euros exceed twice the plan; `--self-test` holds negative fixtures that prove each of those checks can fail.
6. **Reproducible and checked.** `python tools/cost-model.py --check docs/design/12-cost-and-finops.md` fails if the table below is stale or a quota diverges from the plan; the pipeline runs it with the release gate for cost (G6, [10](10-test-and-evaluation.md#4-release-gates)).

**List prices.** These are retail prices. Enterprise-agreement or customer price levels, commitments and credits will be lower; the system itself learns the operator's real price levels ([02 of the north star](../02-learning-azure.md#9-learning-the-commercial-reality)) and can re-price its own bill. **Unverified inputs** are marked in the line notes: the Language PII rate (the vendor page rendered no amount), whether hosted-agent idle time is billed (priced as billed), the sandbox's hour rounding, the red-teaming token volumes, whether orchestrator replays on Flex Consumption bill more executions than the 150 a case the model counts (S-ORCH-1), the share of exam and gate tokens that Flex can serve (80 % here), the Content Safety volume per route (screened once where the text enters, not on every prompt), the gate cadence and repeats, the Claude model behind `judge-pub` and the forger's second family (Mistral Large 3 stands in for both), and the Lab experiment cap. **Four per-second meters** (the Flex Consumption always-ready baseline and both execution meters, and Container Apps memory) have euro prices of one significant digit that the API rounds to six decimals; the model uses the listed euro value, which is about 14 % above the dollar price at the snapshot's rate, so those lines err on the high side. **The cache figures are a warm-cache scenario**, not a measured saving.

## 2. The results

<!-- cost-model:begin -->
_Generated by `tools/cost-model.py` from `docs/design/cost/prices-snapshot.json` (prices retrieved 2026-10-31T20:44:12Z; EUR per USD 0.87997). Do not edit by hand._

| Scenario | Fixed and platform | Compute | Tokens | **Total, shared hub** | Own hub, small | Own hub, medium | Cloud per case, all lines | Per subscription | Break-even, cloud only |
|---|---|---|---|---|---|---|---|---|---|
| **Pilot** | €431 | €166 | €647 | **€1,244** | €1,683 | €2,444 | €12.44 | €248.72 | 6.22 % |
| **Team** | €824 | €754 | €2,700 | **€4,278** | €4,717 | €5,478 | €4.28 | €85.56 | 1.07 % |
| **Enterprise** | €2,339 | €4,324 | €20,319 | **€26,982** | €27,421 | €28,182 | €1.35 | €26.98 | 0.34 % |

Monthly euros, list prices. *Fixed and platform* is data, network, observability and security; *shared hub* means the Citadel hub belongs to the landing zone. *Cloud per case* divides **every** cloud line by the cases (it is not the marginal token cost, which is in the table below). Break-even is the share of monitored cloud spend the system must verifiably save to cover its own **cloud** cost (monitored spend, a seed: Pilot €20,000, Team €400,000, Enterprise €8,000,000 a month). Private Foundry accounts, one per environment, each with its own AI Search, Cosmos DB and Storage: Pilot 2, Team 4, Enterprise 4 (Pilot: development and production; Team and Enterprise add test and the Lab). They are created in the phase that needs them, except the AI Search services, which are created on day zero.

**The inventory behind the floor** (design [04 §7](04-landing-zone-and-citadel.md#7-the-foundry-layout), [07 §6.1](07-security-architecture.md#61-secrets)):

| Scenario | Foundry accounts | AI Search units | Spine environments | Chain environments | Key Vaults | Private endpoints |
|---|---|---|---|---|---|---|
| Pilot | 2 | 2 | 2 | 1 | 9 | 32 |
| Team | 4 | 4 | 3 | 2 | 16 | 51 |
| Enterprise | 4 | 5 | 3 | 2 | 16 | 51 |

A spine environment holds the Durable Functions app, its storage and one secrets vault; a chain environment adds the 6 signing parties' vaults (Approval, Policy, broker, runner, Verifier, Audit Writer) and the queue storage account `stchain`; one more vault holds the pipeline's signing key. Endpoints: 4 per Foundry account, one per vault, 3 per spine environment, 1 per chain environment and 8 shared.

**Shares of the total (shared hub):** Pilot: tokens 52 %, compute 13 %, fixed and platform 35 %; Team: tokens 63 %, compute 18 %, fixed and platform 19 %; Enterprise: tokens 75 %, compute 16 %, fixed and platform 9 %.

**The idle floor by phase** (design [14 §4](14-next-phases.md#4-phases); monthly euros with nothing running: Search, endpoints, Key Vault and Resource Manager Defender, the registry and, from phase 2, the spine's always-ready instance). The AI Search services are created on day zero, so a phase pays for the ones whose account does not exist yet:

| Phase | Accounts that exist (Pilot / Team / Enterprise) | Idle floor € (Pilot / Team / Enterprise) | Of which Search reserved ahead of its account, € |
|---|---|---|---|
| 0 Foundation | 1 / 1 / 1 | 293 / 419 / 487 | 64.88 / 195 / 260 |
| 1 Study | 1 / 1 / 1 | 293 / 419 / 487 | 64.88 / 195 / 260 |
| 2 Survey and investigate, in shadow | 2 / 2 / 2 | 374 / 497 / 590 | 0.00 / 130 / 130 |
| 3 Brief, approve, act | 2 / 3 / 3 | 421 / 647 / 743 | 0.00 / 64.88 / 64.88 |
| 4 The Lab and learning | 2 / 4 / 4 | 421 / 678 / 778 | 0.00 / 0.00 / 0.00 |

**The gate plan** (design [10 §4](10-test-and-evaluation.md#the-statistical-protocol): decoys for G3, comparison cases for G4, each run `r` times; the baselines are frozen and reused, so only the candidate runs; G5 is judged on the same runs, which the 30 % judge work covers):

| Scenario | Gated domain-releases a month | Decoys | Comparison cases | Runs a case | Case-runs a month | Gate tokens € | Reviewer hours a month |
|---|---|---|---|---|---|---|---|
| Pilot | 1 | 99 | 99 | 3 | 594 | €221 | 6 |
| Team | 1 | 218 | 891 | 3 | 3,327 | €1,240 | 6 |
| Enterprise | 4 | 218 | 891 | 3 | 13,308 | €4,961 | 24 |

Pilot gates one narrow domain in shadow: its claim narrows instead of its statistics thinning. Reviewer hours are a person reading the failed critical cases and a fifth of the passed ones and labelling the judges' sample, 6 hours per gated domain-release (a seed).

**Evaluation against production** (everything that runs the exams, the gates, the attacks, the forger and method learning, including the hosted-agent, sandbox, function and screening time that carry them, against the same lines for the production cases):

| Scenario | Evaluation € | Production cases € | Evaluation as a multiple of production cases | Evaluation as a share of the total |
|---|---|---|---|---|
| Pilot | €619 | €66.25 | 9.3 x | 50 % |
| Team | €2,403 | €663 | 3.6 x | 56 % |
| Enterprise | €8,201 | €13,251 | 0.6 x | 30 % |

**Hosted-agent sessions of the evaluation case-runs** (lever 17 of section 5: evaluate on jobs that run the same image), of which the idle tail, which is billed here on the conservative reading: Pilot: €77.00, of which €41.46; Team: €302, of which €162; Enterprise: €1,032, of which €556.

**Contract quotas next to the plan** (token quotas at 1.5 x the planned tokens). The *forecast-equivalent* euros price the quota at the contract's own blended price; the *worst case* prices it at the dearest rate of the dearest alias the contract lists, and neither is a hard cap: the spine's atomic euro reservation is the budget that holds, and the hub's token limit is a second, coarser layer with a bounded overrun (section 6): Pilot: forecast-equivalent €926, worst case €8,074, token plan €596; Team: forecast-equivalent €3,942, worst case €32,627, token plan €2,498; Enterprise: forecast-equivalent €31,434, worst case €211,325, token plan €18,653.

**Where the tokens go** (shared hub):

| Workload | Pilot | Team | Enterprise |
|---|---|---|---|
| Cases (W4) on the EU Data Zone | €54.46 | €545 | €10,892 |
| Watch (W1): triage of the release feed | €0.53 | €0.53 | €0.53 |
| Study (W2): Scholar, Cartographer, Librarian | €32.24 | €32.24 | €32.24 |
| Survey (W3): Surveyor on changes | €0.87 | €8.63 | €142 |
| Dream (W7): nightly consolidation | €9.18 | €16.38 | €168 |
| Continuous exams (W8) on synthetic estates | €224 | €503 | €1,006 |
| Release gates: G3 decoys and G4 comparison runs (design 10 section 4) | €221 | €1,240 | €4,961 |
| Red teaming (L5): attacker, target and evaluator (UNVERIFIED seed) | €20.20 | €53.85 | €162 |
| Embeddings (Atlas releases and retrieval) | €2.99 | €4.86 | €44.48 |
| Other workflows: engineer, signals (W3b), commitments (W5), self-watch (W9), experiments (W6), method learning (W10), forger, T3 exam | €9.41 | €72.18 | €1,223 |
| Development and CI smoke tests (every contract, dev environment) | €21.31 | €21.31 | €21.31 |
| Content Safety screening of untrusted text (Standard tier: no free allowance) | €47.30 | €171 | €1,050 |
| Personal-data pseudonymisation (Language PII) in the tool services | €3.08 | €30.80 | €616 |

**One case, on the strongest tier, by role** (EU Data Zone, marginal tokens only; a **warm-cache scenario**, not a measured saving: each role's session writes its static prefix once, bills it at the write price and reads it on later calls):

| Role | Alias | € per case |
|---|---|---|
| Detective | `acia-reason` | 0.370 |
| Skeptic | `acia-judge-eu` | 0.029 |
| Economist | `acia-reason` | 0.099 |
| Diplomat | `acia-reason` | 0.038 |
| Triage | `acia-triage` | 0.002 |
| Auditor | `acia-judge-eu` | 0.006 |
| **Total** | | **0.545** |

**Sensitivity** (one case, marginal tokens):

| Variant | € per case |
|---|---|
| Baseline: one case on the EU Data Zone, cache written once per session | 0.545 |
| Cache written on every call (the pessimistic reading) | 0.728 |
| The same case on Global (not allowed for estate data: the price of residency) | 0.456 |
| Investigation tier on Terra instead of Sol | 0.291 |
| No prompt caching | 0.682 |

**Sensitivity of the monthly total** (change against the table above, shared hub, one assumption at a time):

| Assumption that moves | Pilot | Team | Enterprise |
|---|---|---|---|
| Exam, gate and red-team tokens all on Global Standard (no Flex) | +€277 | +€1,069 | +€3,642 |
| Twice as many gated domain-releases a month | +€297 | +€1,666 | +€6,663 |
| The hub screens every prompt on every call with Content Safety | +€699 | +€2,886 | +€16,861 |
| Content Safety applied to the safety exams and attacks only, not to the capability exams and gates | −€31.52 | −€123 | −€423 |
| Hosted-agent idle time not billed (the GA record's wording) | −€44.94 | −€197 | −€1,250 |
| Orchestrator replays bill twice the executions | +€6.06 | +€25.84 | +€148 |
| Direct hybrid retrieval only: the semantic ranker off (lever 13) | −€4.66 | −€22.88 | −€407 |

**With labour: the all-in break-even** (share of monitored spend; labour at €75 an hour is a stated seed, not a measurement; the gate review hours above are part of it; the 40-hour row is the Pilot-scale operating budget in [11 §7.2](11-delivery-and-operations.md#the-minimum-viable-profile-and-the-operating-budget)):

| Labour a month | Pilot | Team | Enterprise |
|---|---|---|---|
| none (cloud only) | 6.22 % | 1.07 % | 0.34 % |
| 20 h (€1,500) | 13.72 % | 1.44 % | 0.36 % |
| 40 h (€3,000) | 21.22 % | 1.82 % | 0.37 % |
| 80 h (€6,000) | 36.22 % | 2.57 % | 0.41 % |
| 160 h (€12,000) | 66.22 % | 4.07 % | 0.49 % |

**Contract quotas at Team scale: every contract of [04 §4.3](04-landing-zone-and-citadel.md#43-the-access-contracts) in every environment where it has planned work.** A quota is the planned tokens times 1.5, rounded up to a whole million; TEST and DEV carry at least 25% and 10% of production's plan, or their own planned work where that is larger (exams, gates and attacks run in TEST on synthetic data, so TEST and DEV products reach the public pools). Pilot has no TEST account, so there DEV carries the exams, the gates and the attacks and its quotas are sized for them. The starting tokens a minute is the contract's peak concurrency times its largest call times two calls a minute; the in-flight overrun is the concurrency times the largest call, priced at the dearest rate. The tokens a minute are what the hub is configured to allow, not what the subscription is granted: Foundry quota follows the subscription's tier (Free and Tiers 1 to 6) and more is requested through the quota request form ([Learn](https://learn.microsoft.com/azure/foundry/openai/quotas-limits)); the day-zero request of [14 §5](14-next-phases.md#5-pre-flight-checklist-day-zero) sizes it (assumption 7). `python tools/cost-model.py --quotas Pilot` (or `Enterprise`) prints the others, and `--check` fails if the table of 04 §4.3 disagrees with the model on a contract, its aliases, its pools or whether it has a PROD product, if the phase profile of 14 §4 creates an environment in another phase than the one priced here, or if a quota exists for an environment that a scenario never creates:

| Contract | Environment | Planned, M tokens | Quota, M tokens | Starting tokens a minute | Forecast-equivalent € | Worst case at the dearest alias € | In-flight overrun, tokens (€ at the dearest rate) |
|---|---|---|---|---|---|---|---|
| `study` | PROD | 20.4 | 31 | 176 K | €41.28 | €273 | 88 K (€0.77) |
| `study` | TEST | 5.1 | 8 | 176 K | €10.65 | €70.40 | 88 K (€0.77) |
| `study` | DEV | 2.0 | 4 | 4 K | €12.67 | €35.20 | 2 K (€0.02) |
| `curate` | PROD | 37.6 | 57 | 66 K | €15.85 | €502 | 33 K (€0.29) |
| `curate` | TEST | 9.4 | 15 | 66 K | €4.17 | €132 | 33 K (€0.29) |
| `curate` | DEV | 3.8 | 6 | 4 K | €19.01 | €52.80 | 2 K (€0.02) |
| `survey` | PROD | 12.9 | 20 | 138 K | €13.37 | €211 | 69 K (€0.73) |
| `survey` | TEST | 3.2 | 5 | 138 K | €3.34 | €44.00 | 69 K (€0.61) |
| `survey` | DEV | 1.3 | 2 | 4 K | €6.34 | €17.60 | 2 K (€0.02) |
| `investigate` | PROD | 261.7 | 393 | 516 K | €751 | €4,150 | 258 K (€2.72) |
| `investigate` | TEST | 1,249.5 | 1,875 | 396 K | €1,908 | €16,499 | 198 K (€1.74) |
| `investigate` | DEV | 26.2 | 40 | 4 K | €127 | €352 | 2 K (€0.02) |
| `experiment` | PROD | 0.4 | 1 (0.1 M a day) | 88 K | €2.14 | €8.80 | 44 K (€0.39) |
| `experiment` | TEST | 0.1 | 1 (0.1 M a day) | 88 K | €2.14 | €8.80 | 44 K (€0.39) |
| `experiment` | DEV | 0.6 | 1 (0.1 M a day) | 4 K | €3.17 | €8.80 | 2 K (€0.02) |
| `converse` | PROD | 13.6 | 21 | 82 K | €58.37 | €222 | 41 K (€0.43) |
| `converse` | TEST | 63.6 | 96 | 82 K | €133 | €845 | 41 K (€0.36) |
| `converse` | DEV | 1.4 | 3 | 4 K | €9.50 | €26.40 | 2 K (€0.02) |
| `engineer` | PROD | 21.2 | 32 | 136 K | €88.09 | €338 | 68 K (€0.72) |
| `engineer` | TEST | 5.3 | 8 | 136 K | €22.02 | €70.40 | 68 K (€0.60) |
| `engineer` | DEV | 2.1 | 4 | 4 K | €12.67 | €35.20 | 2 K (€0.02) |
| `govern` | PROD | 19.6 | 30 | 88 K | €36.49 | €317 | 44 K (€0.46) |
| `govern` | TEST | 51.4 | 78 | 44 K | €40.56 | €686 | 22 K (€0.19) |
| `govern` | DEV | 2.0 | 3 | 4 K | €9.50 | €26.40 | 2 K (€0.02) |
| `examine-pub` | TEST | 470.6 | 706 | 704 K | €611 | €6,213 | 352 K (€3.10) |
| `examine-pub` | DEV | 0.6 | 1 | 4 K | €3.17 | €8.80 | 2 K (€0.02) |
| `examine-eu` | PROD | 1.2 | 2 | 52 K | €1.12 | €2.90 | 26 K (€0.04) |
| `examine-eu` | TEST | 0.3 | 1 | 52 K | €0.56 | €1.45 | 26 K (€0.04) |
| `examine-eu` | DEV | 0.6 | 1 | 4 K | €0.68 | €1.45 | 2 K (€0.00) |
| `forge` | TEST | 11.8 | 18 | 304 K | €11.25 | €158 | 152 K (€1.34) |
| `forge` | DEV | 0.6 | 1 | 4 K | €3.17 | €8.80 | 2 K (€0.02) |
| `conduct` | PROD | 23.0 | 35 | 51 K | €3.96 | €370 | 26 K (€0.27) |
| `conduct` | TEST | 92.6 | 139 | 26 K | €7.64 | €1,223 | 13 K (€0.12) |
| `conduct` | DEV | 2.3 | 4 | 4 K | €12.67 | €35.20 | 2 K (€0.02) |
| **All contracts** | **PROD** | **411.6** | **622** | | **€1,011** | **€6,393** | |
| **All contracts** | **TEST** | **1,963.1** | **2,950** | | **€2,755** | **€25,952** | |
| **All contracts** | **DEV** | **43.4** | **70** | | **€219** | **€609** | |

**Optional modules, off by default** (monthly euros, standalone):

| Module | € a month | Basis |
|---|---|---|
| Azure SRE Agent, always on (4 units an hour) | 283 | price API |
| Agent 365 for 5 sponsors (list) | 66.00 | research/security-and-compliance.md D4 (USD per user per month, list) |
| Defender for AI Services at 100 M tokens | 70.40 | research/security-and-compliance.md D3 (EUR per 1K tokens) |
| Front Door Premium, base only | 290 | research/security-and-compliance.md W1 (EUR per month, base) |
| Confidential Ledger, smallest standard instance | 103 | research/features-07.md F7 (Standard instance, EUR per month, West Europe) |
| Azure Data Explorer Dev/Test, if kept on | 105 | research/options-analysis.md section 2b (about USD 120 per month, EUR) |
| Azure Firewall Standard, if the landing zone has none (deployment plus 100 GB) | 804 | price API |
| Durable Task Scheduler Dedicated, one capacity unit, only if the storage provider proves too slow | 572 | price API |
<!-- cost-model:end -->

## 3. Reading the numbers

**Where the money goes.** The shares line under the table gives the split: tokens are about half of the bill at Pilot scale, nearly two-thirds at Team scale and three-quarters at Enterprise scale. At Pilot scale a third of the money is *fixed and platform* — private endpoints, one AI Search service for each private Foundry account, a Premium registry, a vault for each signing party — paid whether or not a single case is open ([the inventory](#2-the-results) is printed beside the table). Hosted compute grows with case-runs (a session is billed here at the larger of its active time and its idle timeout, because the pricing page is silent) and the sandbox, the Durable Functions spine and the Container Apps tool services are small beside it.

**Evaluation costs more than production at Pilot and Team scale, and about a third of the bill at Enterprise scale.** The evaluation table prices everything that runs the exams, the gates, the attacks, the forger and method learning, with the hosted-agent, sandbox, function and screening time that carry them: about nine times the production cases at Pilot scale, three and a half times at Team scale and 0.6 times at Enterprise scale. The reason is the **gate plan**, priced as [10 §4](10-test-and-evaluation.md#the-statistical-protocol) writes it: one gated domain-release at Team scale is 218 decoys and 891 comparison cases at three runs each, 3,327 case-runs, which makes the release gates the largest single line below Enterprise scale. The statistics ask for that volume, and the design's rule stays: where the exam budget cannot buy the effective sample size a gate needs, **the claim narrows** (fewer domains, or the release stays in shadow) instead of the statistics thinning. This is the system's largest discretionary lever (§5): a monthly release train rather than a release for every change, a sequential gate that stops a failing candidate early, two repeats where S-EVAL-1 shows run-to-run noise is small, a small nightly exam *only when something changed*, judge prompts with a static prefix so caching applies, composite evaluators to cut judge input by about two-thirds, evaluation on jobs that run the same agent image rather than on hosted sessions with an idle tail, and Flex (a per-request tier on Global Standard, preview) for the synthetic estates, with Batch once it has an adapter ([10 §9](10-test-and-evaluation.md#9-platform-mapping)). Red-teaming volumes are an unverified seed until the first scans are measured; the self-hosted harness pays the same tokens as the cloud agent.

**A case's marginal tokens cost about half a euro; the all-in cloud cost per case is a different number.** On the strongest tier in the EU Data Zone a whole case — Detective, Skeptic, Economist, Diplomat, triage and Auditor — costs about €0.55 of tokens in the warm-cache scenario, about €0.73 if the cache prefix is rewritten on every call; the Detective alone is about two-thirds of it. The Skeptic and the Auditor are cheap because their judge model is from another family at a lower price, so independence is not a luxury here. Dividing *every* cloud line by the cases gives about €12, €4 and €1.4 at the three scales: that is the number that must fall as cases per subscription grow, and it is what the claim in [Q-COST-1](01-requirements-and-principles.md#4-quality-targets) is about.

**Residency has a price, and it is small.** Running the same case on a Global deployment would cost about 16 % less; that difference is what **C9** costs. For the GPT-6 family the Data Zone list price is about 20 % above Global (about 10 % on earlier models, and it varies by meter), and it is paid only on estate and personal data because the hub routes public work to cheaper deployment types ([ADR-09](13-decisions.md#adr-09-models-are-aliases-and-the-data-class-chooses-the-deployment-type)).

**How much caching helps depends on how cache writes are billed, and the saving is a scenario.** Written once per session, as [05 §7](05-agents-and-orchestration.md#7-the-token-economy) assumes, with the first call of a session reading nothing and the written prefix billed at the write price instead of the input price, caching takes a case from about €0.68 to about €0.55. Rewritten on every call it costs *more* than no caching (about €0.73), because a written token costs a quarter more than an input token and nothing reads it. The model takes each role's real prefix length rather than a share of the input, so the saving is a fifth, not the third that a 70 %-cached seed implied. Spike S-COST-1 measures which is true, and cache lifetime is minutes, so a prefix is not "written once per release".

**Break-even depends on what is counted, and the denominator is a seed.** Counting only the cloud bill, the system must verify savings of about 6 % of monitored spend at Pilot scale, 1.1 % at Team scale and 0.3 % at Enterprise scale. Counting named labour changes the Pilot story completely: at 40 hours a month the all-in break-even at Pilot scale is about a fifth of monitored spend, so **a pilot proves capability, not payback**; from Team scale it is under 2 % and at Enterprise scale 0.4 % (labour table above). The monitored-spend figures are seeds until the first estate's cost export replaces them, and the system tracks the claim from week one as **cost per verified euro saved**, with cloud and all-in side by side ([Q-COST-1](01-requirements-and-principles.md#4-quality-targets); labour is a named, operator-declared number of hours at a declared rate, assumption A8).

**The euro "cap" of a contract is a forecast, not a cap.** The quota table prints, for every contract and environment, the quota priced at the contract's own blended price (*forecast-equivalent*) and at the dearest rate of the dearest alias the contract lists (*worst case*). The two differ by an order of magnitude because a contract that lists Sol could, in principle, spend Sol's output price on every token of its quota (`conduct` lists Sol and uses Luna). Neither is a limit. The budget that holds is the **spine's atomic euro reservation** (§6); the hub's token limit is a second, coarser layer, and its overrun is bounded by the in-flight column of the table: a contract's concurrency times its largest call, priced at the dearest rate, which is a few euros a contract.

## 4. What still costs money when nothing is happening

Scale to zero is the rule ([P10](01-requirements-and-principles.md#5-design-principles)), but a **private** design carries fixed meters. They are listed so they are chosen, not discovered.

| Always-on meter | Why it exists | We pay it? | Alternative and why not |
|---|---|---|---|
| **Private endpoints**, about €6.42 a month each, about 32–51 of them | every PaaS resource is private; each private Foundry account alone needs four (account, Search, Cosmos DB, Storage), and each vault (9 to 16: a secrets vault per spine environment, one for the pipeline's signing key, and one per signing party in each chain environment), the spine's task-hub storage, the chain's queue storage and the recovery lake add more | **yes** — the largest fixed line below Enterprise scale | share accounts; one Private Link Scope; internal Container Apps environments instead of endpoints |
| **AI Search Basic**, about €65 a unit, **one per private Foundry account** | Foundry's standard setup requires it for each private account; the Atlas index shares production's. The services are created **on day zero**, before their accounts exist (the one early meter, because Sweden Central may refuse a new service): the floor table shows what each phase pays for the ones that wait | **yes** | Serverless Developer is preview, has no SLA and is not recommended for production; it accepts private endpoints but supports neither shared private links nor a network security perimeter ([Learn, service limits](https://learn.microsoft.com/azure/search/search-limits-quotas-capacity#shared-private-link-resource-limits), read 2026-10-31); whether the standard setup accepts it is untested (S-NET-2, S-DATA-3) |
| **Container Registry Premium**, about €45 | a private endpoint needs Premium | **yes** | deploy hosted agents from source |
| **Durable Functions always-ready instance** (the `durable` group on Flex Consumption), about €21 per 2 GB instance | Learn recommends one always-ready instance for the `durable` group; without it a spine step can start with a cold start of seconds ([05 §4](05-agents-and-orchestration.md#4-how-the-spine-runs)). Always-ready billing has **no free grants**, and Learn requires **at least two** such instances per group if zone redundancy is enabled, which the design does not enable at Pilot and Team scale (recovery is a redeploy) | **yes** | none cheaper that keeps the spine's latency; dropping it is lever 11 |
| **Defender for Resource Manager and Key Vault**, about €5 a subscription | detection | **yes** | none cheaper |
| **The hub's usage pipeline**, about €320 | Cosmos DB with seven containers, a Logic App plan, Event Hubs | **no** if the hub is shared; trimmed if ours | log-based usage reporting |
| **API Management Standard v2**, about €800 in Sweden Central (about €616 in West Europe) | the gateway | **no** if the hub is shared | Developer tier (€42, no SLA) for dev |
| **A firewall in the spoke**, Azure Firewall Standard €803 a month for the deployment hour plus €0.014 a GB (Premium €1,124 plus data) | outbound FQDN rules | **avoided** | BYO-VNet behind the landing zone's firewall ([ADR-05](13-decisions.md#adr-05-bring-your-own-vnet-injection-not-the-managed-vnet)) |
| **Azure SRE Agent**, about €283 in Sweden Central (€349 in West Europe) | always-on at 4 units an hour | **avoided** | our own detectors ([ADR-27](13-decisions.md#adr-27-the-system-operates-itself-sre-agent-is-off-by-default)) |
| **Durable Task Scheduler Dedicated**, about €572 a capacity unit | the fully managed alternative to the Azure Storage provider | **avoided** | the Azure Storage provider, switched only if S-ORCH-1 shows it too slow |
| **Service Bus Premium** | private endpoints need it | **avoided** | Storage queues with event jobs |
| **Log Analytics commitment tier** (from 100 GB a day) | discount at volume | **avoided** | pay-as-you-go with cheap table plans |
| **Azure Data Explorer** | KQL analytics | **avoided** unless started | embedded engine over Parquet |
| **Managed HSM**, about €2,000 | customer-managed keys | **avoided** | platform-managed keys |

## 5. Levers, in order

Estimates use the model; each is a decision with an owner, not a wish.

| # | Lever | Effect | Condition |
|---|---|---|---|
| 1 | **Share a hub** rather than deploying one | −€440 to −€1,200 a month | the landing zone offers one |
| 2 | **Trim the hub's usage pipeline** if we run it | up to −€320 a month | a fork change |
| 3 | **Run exams only when something changed**; Flex and caching on the rest | about a third to a half of exam spend | path filters in the pipeline; exam still runs weekly and at release |
| 4 | **Terra instead of Sol** for the investigation tier | about −46 % per case | the exam shows no loss of quality (spike S-MOD-3) |
| 5 | **A cheaper shape for dev** | about −€95 a month for each account that needs no private trio (AI Search €65, four private endpoints €26, Cosmos DB and Storage) | spike S-NET-2, extended to production |
| 6 | **Create environments in the phase that needs them** | about €30 a month for each of the test and Lab accounts until their phase (four endpoints and the stores); the AI Search service of each is created on day zero, about €65 more, the one early meter | staged creation ([14 §4](14-next-phases.md#4-phases)) |
| 7 | **Reuse the landing zone's firewall** | −€803 a month versus a spoke-local Standard firewall | the landing zone has one |
| 8 | **Log content capture off; Basic and Auxiliary table plans** | a large share of ingestion | already the default |
| 9 | **Route public work to Global, Flex, Batch** | avoids the Data Zone premium (about 20 % on the GPT-6 family) on that work | already the design |
| 10 | **Typed query tools instead of model-written code** | removes the sandbox line and the tokens of writing the code | already preferred |
| 11 | **Drop the always-ready instance of the spine** | −€21 a month per instance | accept a cold start of seconds on a spine step (Learn recommends the instance; S-ORCH-1 measures the effect) |
| 12 | **Hosted-agent idle timeouts at each role's p99 active time, and no longer** | the idle part of every session (idle is billed here because the page is silent); the timeouts may not go *below* the p99, or the platform deprovisions a leaf that is still working ([05 §5](05-agents-and-orchestration.md#5-anatomy-of-a-leaf)) | spike S-COST-1 measures what is billed; if idle is free, the sensitivity table shows the saving |
| 13 | **Semantic ranker only where it earns its price** | up to the whole semantic-ranker line (about €23 at Team scale, about €400 at Enterprise scale) | the exam shows no retrieval gain without it ([06 §7.5](06-data-and-knowledge.md#75-atlas-retrieval-and-vectors)) |
| 14 | **A monthly release train**: batch prompt, tool and model changes into one gated release per domain a month; a security hotfix goes through G1 and G2 only | the gate line grows linearly with releases (twice as many costs about €1,700 a month more at Team scale) | the gate plan of [10 §4](10-test-and-evaluation.md#the-statistical-protocol); a change that cannot wait is a hotfix with a narrower, registered gate |
| 15 | **A sequential gate**: look after the first third of the cases and stop a candidate that already fails | the remaining runs of every failing candidate; a passing candidate still needs its full sample | registered in the protocol (changing it is a release); the nightly futility-only exam is the first step |
| 16 | **Two repeats instead of three** where S-EVAL-1 shows run-to-run variance far below case-to-case variance | a third of the gate runs (about €400 a month of tokens at Team scale) | S-EVAL-1 measures both variances ([10 §4](10-test-and-evaluation.md#the-statistical-protocol)) |
| 17 | **Evaluate on jobs that run the same agent image**, not on hosted sessions | the sessions and the idle tail of the evaluation case-runs (about €300 a month at Team scale, of which about €160 is the idle tail; the sentence under the evaluation table in §2 is generated and has the exact figures) | S-HOST-1 shows the image behaves the same off the hosted runtime; the release gate still runs on the shipped runtime |
| 18 | **Screen the capability exams' tool responses on a sample only** | about €120 a month at Team scale (the sensitivity table) | the safety exams and the attacks keep full screening |

Serverless AI Search is **not** on this list as a dated saving: it is preview, has no SLA and no shared private links, so it can serve at most a development Atlas index, not the standard setup of a private account.

## 6. How the system's own spend is governed

Five layers, from the one nearest the work to the one furthest from it — each *independent* of the others:

1. **The envelope** of every invocation: tokens, euros, seconds and tool calls ([05 §4](05-agents-and-orchestration.md#4-how-the-spine-runs)). Before each leaf call the spine **reserves the call's worst-case cost atomically** against the case's and the group's budget: tokens at the dearest alias and the dearest *service tier* the contract allows (the hub refuses a caller's own tier, so priority processing is not reachable, [04 §4.3](04-landing-zone-and-citadel.md#43-the-access-contracts)), the leaf's **own session compute** (vCPU and memory for the role's idle timeout, which this model bills), the Content Safety records the call may add, and the metered tools the call may use. The hub's usage record shows tokens, so the compute, screening and tool parts stay reserved at their worst case until the daily cost export reconciles them; an actual above the reservation is **debited to the head**, and the next reservation against it is refused. A case cannot start work it has not been allowed to pay for. **This is the budget that holds**; the layers below catch what escapes it, and S-COST-1 measures what the reservation leaves open (whether the hub's usage record carries the reservation id; reserved against billed over the first hundred cases).
2. **The agent's middleware**: stops the loop at the envelope's limits.
3. **The contract at the hub**: token limits per minute and per month, with `estimate-prompt-tokens` on ([04 §4.3](04-landing-zone-and-citadel.md#43-the-access-contracts)). This is a **second, coarser layer**, not an exact one: `llm-token-limit` can be overrun by the requests that are in flight when the counter trips, so the residual overrun is bounded by the concurrency of a contract times its largest call (the in-flight column of the quota table), and the quotas, the per-minute limits and the bounds are *computed* from the plan (`tools/cost-model.py --quotas`) for every contract and environment rather than typed. Tokens are not euros: cached input, tool calls, sandbox hours, a different model behind an alias and a priority service tier price differently, which is why the hub's limit is not the budget. Azure budgets evaluate once a day on data eight to twenty-four hours old and stop nothing.
4. **Detection**: spend or tokens per contract above three times the trailing median, or a budget head below zero (an actual above its reservation), raises D4 ([07 §10](07-security-architecture.md#102-detections-we-ship-as-code)); Azure budgets alert as a backstop.
5. **The Agenda**: the platform's own cost is the *first* item the Conductor ranks (FR-X4), with the question "what would this cost less if it were done differently?"

**Unit economics, tracked weekly:** cost per case (marginal tokens and all-in, kept apart); **cost per verified euro saved**, cloud and all-in with named labour side by side ([Q-COST-1](01-requirements-and-principles.md#4-quality-targets)); tokens as a share of cost; evaluation cost as a share of cost; the always-on floor; the break-even share of monitored spend. The **FinOps Framework** structure applies to ourselves: *Understand* (allocation by contract, agent, case and environment, from the hub's dimensions and tags), *Quantify* (the unit economics above), *Optimise* (the levers of §5), and *Manage the practice* (the weekly cost report is a pipeline output, not a meeting).

## 7. What the model leaves out

GitHub minutes and storage; the landing zone's shared services (connectivity, firewall, DNS, SIEM); Microsoft 365, Teams and Exchange licences; **Entra ID P1 or P2**, which the Auditor's cross-check of approvals against the sign-in log (detection D13) needs for the Graph sign-in log and which the approval page's multifactor authentication strength (Conditional Access) needs — without P1 the web page's irreversible, purchase and credential classes stay off ([07 §3.4](07-security-architecture.md#34-conditional-access-and-the-licence-line)) — and which is a licence dependency, not a meter; Agent 365 and other optional licences (priced in the table above on their own); internet egress and Key Vault operations (cents); Event Grid operations for drift, cost and Activity Log signals (the first million a month is free, then €0.53 a million: Retail Prices API, Sweden Central, read 2026-11-01, so a few euros even at Enterprise signal volumes); peering is a line, but only to a hub in another region; model deployments of partner families that the price API does not list (a Claude model is billed through the Marketplace, so Sol on Global stands in for `judge-pub` and Mistral Large 3 for the forger's second family); voice, SMS and avatar modules (off by default); reserved capacity and committed-use discounts; AI Search features we do not use (**Foundry IQ and agentic retrieval**, which would need retrieval-token quantities and a separate standard plan: direct hybrid retrieval is the baseline). **People's time is not a line** but a sensitivity: the labour table in §2 shows the all-in break-even for 20 to 160 hours a month at a stated rate, and the gate plan's reviewer hours are part of it. Taxes and negotiated discounts change the absolute numbers, not the proportions.

## 8. Keeping it true

The snapshot is refreshed monthly by re-running `tools/fetch-prices.py` and reviewing the diff; the model is re-run, and `--check` fails the build if this document is stale, a quota has drifted from the plan, the table of [04 §4.3](04-landing-zone-and-citadel.md#43-the-access-contracts) or the phase profile of [14 §4](14-next-phases.md#phase-and-capability-profiles) disagrees with the model (`--self-test` proves each of those checks can fail). Two figures come from the Retail Prices API outside the snapshot (inter-region transfer and the GZRS block-blob price, both read 2026-10-31) and are named in the model's manual table. Seeds are replaced by measurements as soon as the first hundred synthetic cases have run on the pinned stack (S-COST-1), and every phase exit in [14](14-next-phases.md#4-phases) reports *measured* cost per case next to the model's.
