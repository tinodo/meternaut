# Round 2 · D — Cost honesty and efficiency (model: gpt-5.6-sol)

> Raw report, saved exactly as the reviewer returned it (everything below the rule). Reviewed on 2026-11-01: `docs/design/10-cost-and-finops.md`, `02`, `09`, `11`, `tools/cost-model.py` and the price snapshot (commit `3543f3b`). Lens: honesty and efficiency of the design's cost figures; recomputation of 14 Pilot line items. The orchestrator's spot-checks of what this reviewer cited are in the [disposition](disposition.md).

---

## Verdict

The snapshot and arithmetic are unusually reproducible: all 14 Pilot spot-checks below match the model and document after rounding.  
However, the headline is not a fully loaded cost, and the no-existing-hub calculation uses an API Management tier Microsoft explicitly excludes from production.  
One blocker and several major corrections are needed before the break-even figures are finance-grade.

## Top 5 fixes and savings

| Change | Estimated saving/month: Pilot / Team / Enterprise | Trade-off |
|---|---:|---|
| Enforce Terra-first, Sol-on-escalation instead of hard-coded Sol | €13 / €127 / €1,272 on Case tokens | Must prove equivalent quality in P10 |
| Use Global Standard for estate data where policy permits | €4 / €44 / €451 | Weaker data-residency boundary |
| Halve log ingestion through sampling and stricter table routing | €1 / €26 / €319 | Less forensic detail |
| Replace dedicated Atlas Search with an embedded index, or measured Serverless | Up to €68 / €139 / €241 | Custom retrieval work, or preview/no SLA |
| Remove the always-ready Durable instance | €22 / €20 / €9 | Cold starts and polling latency |

Cosmos serverless, Blob stock and Key Vault are already small at Pilot scale. Durable state is only €4; increasing polling intervals saves little but delays wake-ups. Private endpoints/DNS are primarily security costs—each removed endpoint saves about €6.42/month but weakens isolation.

## Pilot recomputation

| Line item | Hand arithmetic from the snapshot | EUR |
|---|---|---:|
| Watch tokens | `[200×(1,500×.105597+300×.527983)+30×1,500×.131996+170×1,500×.01056]/1M` | 0.07 |
| Embeddings | `3,000 × €0.000114/1K` | 0.34 |
| Hosted agents | `(20×1.4+730×4/60+1,216×3.5/60+400×.4/60)×(.5×.096216+.011422)` | 8.95 |
| Always-ready Functions | `2 GB × 3,600 × 730 × €0.000004/GB-s` | 21.02 |
| Functions execution | `20,650.24×2×.000014 + 20,650.24/10×.000004`; on-demand remains free | 0.59 |
| AI Search Basic | `1 × €0.088877 × 730` | 64.88 |
| Semantic ranker | `(4,048−1,000)/1,000 × €0.879972` | 2.68 |
| Cosmos DB | `1.1M RU×.268391 + 2GB×.219993` | 0.74 |
| Blob | `3GB×.020767 + 10×10K writes×.071454` | 0.78 |
| Private endpoints | `8 × €0.0088 × 730` | 51.39 |
| Private Link data | `20GB × 2 directions × €0.0088` | 0.35 |
| Log ingestion | `4GB×.567582 + 1.6GB×.061598`; Analytics share under 5GB | 2.37 |
| Content Safety | `38,480/1,000 × €0.329989` | 12.70 |
| Key Vault | `20×10K operations × €0.026399` | 0.53 |

`--self-test` passed, `--check` returned success, and the generated JSON agrees with document 10.

**Token check:** one Case is `600+90+75+48+20+10+18 = 861K` input and `30+6+7.5+6+3+1.2+1.8 = 55.5K` output tokens. Pilot therefore uses 17.22M input and 1.11M output monthly—about 566K/36.5K daily. This is plausible as a deliberately high deep-investigation seed, but not as a forecast: it represents 44 effective model calls per Case. It is most sensitive to Case count/length, Detective calls, cache success, and the reason model. A cache miss adds €15.86 to Pilot Case tokens and €45.88 overall.

**Meter materiality:** material omissions or uncertainties are the hub, Defender for AI sensitivity (€15/€165/€1,956), the unverified PII price at Enterprise (€176), private Function endpoints at Pilot, and metered Foundry safety/red-team evaluations if enabled. DNS, Cosmos 30-day PITR (€0.35/€1.76/€17.60), extra storage operations and ordinary bandwidth are below 3% under seeded volumes. A 20,000-ACU Agent Prepurchase Plan could save roughly €73/month averaged over a year at Enterprise usage; it is not attractive for Pilot or Team.

## Findings

| # | Severity | File:line | Quote | What is wrong | Proposed fix |
|---|---|---|---|---|---|
| 1 | **blocker** | `<repo>\tools\cost-model.py:326` | “API Management Developer” | Developer is nonproduction and has no SLA. Standard v2 is about €819/month today versus roughly €43 Developer. The €439 hub add-on is therefore invalid; it becomes about €1.2K if Standard v2 suffices. | Price the actual production Citadel topology and show marginal shared-hub and fully loaded own-hub cases separately. |
| 2 | major | `<repo>\docs\design\09-delivery-and-operations.md:34`; `<repo>\tools\cost-model.py:105` | “Always-ready instances default to 0” | The documented default is zero, but the headline model sets one. Pilot is overstated by about €22 relative to the stated default. | Make zero the base and one always-ready instance an availability sensitivity, or change document 09. |
| 3 | major | `<repo>\docs\design\03-agents-and-workflows.md:58`; `<repo>\tools\cost-model.py:183` | “Work starts on `triage`” | The model sends every Detective, Economist, Diplomat and Engineer call to Sol. It does not cost the designed triage-first escalation. | Add per-role escalation probabilities and Terra-first/Sol-escalation scenarios. |
| 4 | major | `<repo>\tools\cost-model.py:39-46` | “search_units=1 … 2 … 3” | Search units grow with scenario size without an index-size, throughput, replica-SLA or latency calculation. | Model partitions and replicas from Atlas size, QPS and SLO; benchmark embedded and Serverless alternatives in P5. |
| 5 | major | `<repo>\docs\design\02-architecture.md:57-60,138` | “Private endpoints … Eight” | The eight endpoints cover dependencies, but not the `tools` and `runner` apps described as private. Private DNS zones are also absent. | Generate endpoint/DNS costs from the actual network graph; add at least €12.85/month if two Function private endpoints are required. |
| 6 | major | `<repo>\docs\design\10-cost-and-finops.md:175` | “model counts tokens only” | The default evaluation path is ambiguous. Foundry safety, red-team and playground evaluations have their own meters; the modeled 1,000-attack token volume would be about €195/run on that path. | Make PyRIT-only versus Foundry-metered evaluation an explicit switch and include both totals. |
| 7 | major | `<repo>\docs\design\10-cost-and-finops.md:69` | “share of managed spend” | This is a flattering denominator and an incomplete numerator: hub allocation, runner, human time, and expected loss from wrong applied advice are absent. | Use addressable spend and report verified net savings after fully loaded cost, labour, rollback/incident cost and expected loss. |
| 8 | major | `<repo>\docs\design\10-cost-and-finops.md:184` | “hard stops are … token quotas” | Token quotas do not stop runaway Functions, Cosmos RU, Content Safety, logging or evaluation charges; Cost Management data is delayed. | Add service-native counters/caps, Log Analytics daily caps, concurrency limits, evaluation quotas and actual-versus-model reconciliation by meter. |

## What I verified myself

- [Hosted agents](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents): active-session CPU/memory billing, 0.5-vCPU/1-GiB minimum, and 2–240-minute timeout.
- [Durable Functions storage provider](https://learn.microsoft.com/azure/durable-task/durable-functions/durable-functions-azure-storage-provider#flex-consumption-plan): one always-ready instance is a recommendation, not a requirement; faster polling raises storage cost.
- [API Management tiers](https://learn.microsoft.com/azure/api-management/api-management-features): Developer is nonproduction/no-SLA.
- [AI Search tiers](https://learn.microsoft.com/azure/search/search-sku-tier): Serverless is preview/no-SLA; dedicated Search bills continuously.
- [Azure Monitor Logs](https://learn.microsoft.com/azure/azure-monitor/logs/cost-logs): Basic/Auxiliary queries, retention, search jobs and export have additional meters.
- [Foundry observability pricing](https://azure.microsoft.com/pricing/details/foundryobservability/): safety, red-team and playground evaluations use the AI-evaluation meter.
- [Agent Prepurchase Plan](https://learn.microsoft.com/azure/cost-management-billing/reservations/agent-pre-purchase): one-year commitment and 5%/10%/15% discount tiers.
- [Retail Prices API](https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview): current EUR evaluation, APIM, DNS and Search meters.

## What I could not verify

The exact Azure Language text-PII rate represented by the manual €0.88/1K figure, actual runner cost, or whether production traffic will consume the seeded hosted-session, RU, logging and Search volumes. These require P10 measurements and a deployed network proof.
