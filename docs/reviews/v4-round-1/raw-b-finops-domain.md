# Round 1 · Reviewer B — FinOps and Azure billing domain expert (raw report)

> **Status: RAW — verbatim as returned.** Agent type `cloud-solution-architect`, read-only, Learn-grounded, 2026-10-31. Brief: fact-check Azure/FinOps statements, domain completeness, savings-accounting realism, claims to hedge (v4 draft, commit `d267654`). The orchestrator's spot-checks are appended; the disposition is in [disposition.md](disposition.md).

---

# Reviewer B report: FinOps and Azure billing domain review

## Verdict

The Cost Grammar is directionally sound, and most decoded behaviours hold on Learn: Premium always-warm floor, Container Apps idle rate, SFTP hourly, stopped vs deallocated, Fabric pause, AI Search replicas × partitions. I found no Critical errors. A FinOps expert would catch five things in the first five minutes. One is a firewall/NAT row that lumps two different services. Another is an overconfident billing-minimum "law". A third is an outdated Functions lever. A fourth is AI Search shown as one pricing model. The fifth is "last twelve months" replays that native Azure retention cannot supply. The Money model is the thinnest layer: agreement type, MACC, licensing, egress, support and amortisation share one paragraph. Savings accounting is aspirational until the unit of account is defined.

## Findings

The Learn MCP failed intermittently, so I switched to alternate Learn endpoints.

**B-01 · Major · 02 §2 decodes.**
- Quote: "A NAT or firewall appliance: a fixed hourly fee plus per-GB processing" (lever: "consolidate, or remove in non-production").
- Learn on firewalls: "billing stops and starts accordingly" on stop/start (https://learn.microsoft.com/azure/firewall/firewall-faq). The WAF guide advises deallocating firewalls used only in business hours (https://learn.microsoft.com/azure/well-architected/service-guides/azure-firewall#cost-optimization).
- Learn on NAT Gateway: I found no documented stop. Learn's lever is removal: "NAT gateways incur hourly charges and data processing costs" (https://learn.microsoft.com/cloud-computing/finops/best-practices/networking#nat-gateway).
- Fix: split into two rows. Firewall: deallocate off-hours. NAT Gateway: delete when no subnet is attached.
- Not verified: the Firewall per-GB meter. I found it only in Microsoft Q&A, not product docs.

**B-02 · Major · 02 §2 Laws.**
- Quote: "Short-lived resources nearly always pay a minimum, whatever the document says."
- Learn counter-evidence:
  - VMs "bill per second used" (https://learn.microsoft.com/azure/architecture/aws-professional/compute#compare-aws-and-azure-compute-services).
  - A 15-minute Foundry PTU deployment "is charged at 1/4 of the hourly rate" (https://learn.microsoft.com/azure/foundry/openai/concepts/provisioned-throughput-billing#hourly-billing).
  - But Front Door bills "each hour, or partial hour" (https://learn.microsoft.com/azure/frontdoor/billing#base-fees).
  - SQL Managed Instance bills "every started hour" (https://learn.microsoft.com/azure/azure-sql/managed-instance/instance-stop-start-how-to).
- Fix: "Billing granularity varies by meter — per second, prorated hour or started hour; record and test it per meter."

**B-03 · Major (highest impact) · 04 §7, 03 §3, 02 §3.**
- Quotes: "would it have survived every peak of the last twelve months?" and "Resource Graph (resources, and the change history of their properties)".
- Learn:
  - Changes are "queryable for 14 days" (https://learn.microsoft.com/azure/governance/resource-graph/changes/resource-graph-changes#data-retention).
  - Platform metrics are typically kept 93 days (https://learn.microsoft.com/azure/azure-monitor/metrics/data-platform-metrics#retention-of-metrics).
  - EA "Reservation prices are only available for the current month price sheet and can't be retrieved for historical exports" (https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports#limitations).
- Fix: replay depth equals what the customer exported or retained (diagnostic settings, recurring price-sheet exports). Otherwise history starts on day one.

**B-04 · Major · 02 §2 decodes.**
- Quote: "A premium serverless plan that always keeps at least one instance warm" (lever: "move idle apps to a consumption plan").
- The floor is correct (https://learn.microsoft.com/azure/azure-functions/functions-scale).
- The lever is outdated: "The option to host function apps on Linux in a Consumption plan is retiring on 30 September 2028" (https://learn.microsoft.com/azure/azure-functions/consumption-plan). Flex Consumption is the documented migration target (https://learn.microsoft.com/azure/azure-functions/migration/migrate-plan-consumption-to-flex).
- Fix: "move idle apps to a plan that scales to zero (Flex Consumption)".

**B-05 · Major · 02 §2 Multiplier.**
- Quote: "adding one to each of two dimensions quadruples the bill".
- Learn documents two models (https://learn.microsoft.com/azure/search/search-sku-manage-costs):
  - Dedicated: replicas × partitions Search Units at the tier's hourly rate. "To stop billing entirely, you must delete the service."
  - Serverless preview: "no compute charge when idle".
  - You cannot convert between them.
- Fix: "On a Dedicated service, 1×1 to 2×2 quadruples Search Units; Serverless (preview) has no replicas or partitions."
- Bank row TRAP-AI-004 (marked "Verified") needs the same qualifier.

**B-06 · Minor · 02 §3 and landscape.md surfaces.**
- (a) Quote: "The unit-price ground truth, meter by meter, including savings-plan rates (preview)."
  - `retailPrice` is "Microsoft Retail Prices without discount". USD is the pricing currency, non-USD is "for your reference", and the API is commercial cloud only. The "(preview)" label is right (https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices).
  - Fix: "list-price ground truth (USD base), never the customer's price."
- (b) Quote: "Cost Management exports in the open FOCUS format".
  - FOCUS is one dataset and is unsupported at management-group scope. "Azure MOSP billing scopes and subscriptions don't support FOCUS datasets" (https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports).
- (c) Quote: "savings at retail rates that ignore existing commitment coverage".
  - This is true only for VM right-size/shutdown: the recommendations "don't take into account the presence of Reserved Instances (RI) / Savings plan purchases" (https://learn.microsoft.com/azure/advisor/advisor-cost-recommendations#limitations).
  - Commitment forecasts "are based on actual rates and usage" (https://learn.microsoft.com/azure/advisor/advisor-how-to-calculate-total-cost-savings).

**B-07 · Minor · 05 §7.**
- Quote: "The rules change (Microsoft has announced narrower reservation exchange from February 2027)".
- Learn says exactly (https://learn.microsoft.com/azure/cost-management-billing/reservations/reservation-exchange-policy-changes):
  - "Starting February 1, 2027, reservations purchased after this date aren't eligible for exchange if the corresponding service is supported by savings plans."
  - Earlier purchases "keep the right to one final exchange".
  - Trade-in to a savings plan stays.
  - Renewals count as new purchases.
  - Refunds are capped at USD 50,000 per rolling 12 months.
- The bullet's "exchanged, resized or cancelled" ignores two facts. Savings plans "can't cancel or exchange" (https://learn.microsoft.com/azure/cost-management-billing/savings-plan/manage-savings-plan). Databricks pre-purchase is final (https://learn.microsoft.com/azure/cost-management-billing/reservations/prepay-databricks-reserved-capacity).
- Fix: "From 1 Feb 2027, reservations bought on or after that date for savings-plan-eligible services (VMs, App Service, SQL Database…) can't be exchanged; earlier ones keep one final exchange; trade-in to a savings plan remains."

**B-08 · Minor · 05 §11.**
- Quote: "by the end of the term. These three workloads could move onto it."
- A MACC is not a pool that workloads attach to. It counts eligible Azure consumption on the billing account. Marketplace purchases count only if Azure-benefit-eligible and bought through Azure in the term (https://learn.microsoft.com/azure/cost-management-billing/benefits/macc/track-consumption-commitment; https://learn.microsoft.com/marketplace/macc-frequently-asked-questions).
- Fix: "…eligible spend now outside this billing account, or eligible Marketplace purchases, could count toward it."

**B-09 · Minor · exam bank, 8 non-Verified rows spot-checked.**
- STOP-007, "only the Serverless tier can auto-pause": stale for SQL MI General Purpose, where stopped instances pay storage only (https://learn.microsoft.com/azure/azure-sql/managed-instance/instance-stop-start-how-to).
- NET-012, "being retired/phased out": "On September 30, 2025, Basic SKU public IPs were retired" (https://learn.microsoft.com/azure/virtual-network/ip-services/public-ip-upgrade).
- DATA-006, "limited early exit": Learn says "All purchases are final". A Marketplace refund page conflicts and is unreconciled (https://learn.microsoft.com/azure/cost-management-billing/reservations/prepay-databricks-reserved-capacity).
- ORPH-009 and DATA-012 are supportable, so upgrade them (https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-overview#pricing-and-billing; https://learn.microsoft.com/azure/architecture/serverless/event-hubs-functions/performance-scale#event-hubs-scaling).
- COMMIT-010 and REGION-003 hold. "All cross-region connectivity incurs data transfer charges" (https://learn.microsoft.com/azure/networking/design-guide/cross-region#cost-considerations), a better source than the cited Private Link page.
- STOR-004 (default GRS): not confirmed on Learn. Scope it to the portal flow or drop it.

## Domain gaps

1. **Agreement type as an entity** (EA, MCA direct, CSP, pay-as-you-go).
   - It differs in price-sheet access, MACC tracking (direct EA/MCA only), data latency (EA/MCA 8–24 h, PAYG up to 72 h; https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data), FOCUS support and refund pools.
   - Home: 03 §1 Money; 02 §9.
2. **"Commitment" is one row; it needs three.**
   - Hourly benefits: reservations apply first, and unused hourly commitment "doesn't roll over" (https://learn.microsoft.com/azure/cost-management-billing/savings-plan/savings-plan-overview).
   - Pools (Databricks DBCU).
   - Agreement-level (MACC, Marketplace eligibility).
   - Home: 02 §2; 05 §7.
3. **Rate levers beyond negotiation:** Hybrid Benefit/licences, dev/test (`DevTestConsumption` price type), Spot, capacity reservations, credits and free grants, with a stacking order. Home: 02 §2 "Rate and benefit".
4. **Price mechanics:** graduated tiers (`tierMinimumUnits`), free allowances (Container Apps grants), billing quantum, USD pricing vs billing currency with a monthly FX lock, and tax. Home: 02 §2 (new Allowance mechanism), 02 §3.
5. **Non-resource charges:** Marketplace/SaaS and support plans. "A spending limit doesn't prevent all charges" (https://learn.microsoft.com/azure/cost-management-billing/manage/spending-limit). Home: 05 §11.
6. **Network economics:** egress, cross-region, inter-zone and Private Link processing hide inside Flow/Coupling. They need a path-aware model. Home: 02 §2; 03 §5.
7. **Cost views and allocation:** actual vs amortised (https://learn.microsoft.com/azure/cost-management-billing/costs/customize-cost-analysis-views), showback/chargeback, shared-cost allocation and untagged spend. Home: 03 §1; 05 §8.
8. **Unit economics and carbon** sit only in 08 §E. Learn puts Unit economics under "Quantify business value" (https://learn.microsoft.com/cloud-computing/finops/framework/capabilities). Add a driver/denominator to the Intent layer. Home: 03 §1.
9. **Layered meters:** Databricks bills DBUs plus separately charged compute, storage and networking (https://learn.microsoft.com/azure/cost-management-billing/reservations/reservation-discount-databricks). The "Capacity × time" decode misses this. Home: 02 §2.

## FinOps practitioner challenges

1. **Unit of account undefined.**
   - 05 §8 says a saving is what the bill is versus "what it would have been". Which bill: actual or amortised; list, contracted or effective?
   - Learn's toolkit splits savings into negotiated (List − Contracted) and commitment (Contracted − Effective), with an Effective Savings Rate (https://learn.microsoft.com/cloud-computing/finops/toolkit/hubs/savings-calculations; https://learn.microsoft.com/cloud-computing/finops/toolkit/power-bi/rate-optimization).
   - Book usage savings (Workload optimization) and rate savings (Rate optimization) on separate lines. Learn's lifecycle is Inform → Optimize → Operate (https://learn.microsoft.com/cloud-computing/finops/framework/finops-framework#lifecycle).
2. **Commitments make Moves non-additive.**
   - Reservation benefit is use-it-or-lose-it hourly. It moves to another matching resource when a covered VM stops (https://learn.microsoft.com/azure/cost-management-billing/reservations/benefit-application-order).
   - Advisor warns that rightsizing, reservation and savings-plan savings overlap and must be sequenced (B-06 URL). A per-Move ledger double-counts.
3. **Counterfactual precision.**
   - Learn's forecast KPI is "<12% variance when there are no anomalies" (https://learn.microsoft.com/cloud-computing/finops/framework/quantify/forecasting). A €690/month Move vanishes in a bill-level baseline.
   - Verify at meter level (driver-normalised unit cost). "Untouched similar resources" are rarely comparable.
4. **Hold price and FX constant.** FX is fixed monthly. Otherwise both leak into "savings".
5. **Timing.** "one month (a full bill cycle)" cannot close before the period-close lag (up to 72 h). Define provisional → reconciled → Finance-accepted.
6. **Realised vs annualised.** 06's "Verified savings this month: one hundred forty thousand euro run-rate" mixes the two.
7. **Net of what?** Lab, model and telemetry spend are programme costs with no ledger line. Cost avoidance versus realised saving needs separating. This is practitioner convention; I found no Learn definition.
8. **Calibration noise.** A "published" calibration error from few Moves is noise. Show intervals and a materiality threshold.

## Claims to hedge

- 01 "Four clocks", Watch "minutes to hours": billing data lags 8–24 h (EA/MCA) and up to 72 h (PAYG). A watch on billing cannot be minutes; only non-billing signals could.
- Day-zero speed claims:
  - "within hours a draft Profile exists" (08 §A).
  - "By the next morning every organisation running the Commons has a verified profile" (07).
  - "the Atlas profiles it the same day" (01).
  - "useful the same day" (02 §6).
  - "fall — to hours" (01 §16).
  - A draft from docs and prices is plausible. Cost verification happens only when the bill lands.
- "By the end of the day the owners of the five largest unexplained blocks have each received one question." (01, 03): first-day bill lag.
- "No customer-specific training is needed" conflicts with 02 §9's customer-specific price book.
- "is re-checked daily" (02 §4): a target schedule, not a capability.
- "a region that is quietly 18% cheaper for the same thing" (08 §A): list price only. Mark it illustrative.

## Verified OK

- Feb-2027 exchange narrowing; savings plans not exchangeable (B-07 URLs).
- Retail Prices: unauthenticated, USD base, savings-plan rates only in 2023-01-01-preview (B-06 URL).
- "hours to days" (04 §4): https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data
- Container Apps idle rate applies only when minimum replicas > 0 and the replica is idle (<0.01 vCPU, <1,000 bytes/s): https://learn.microsoft.com/azure/container-apps/billing#consumption-plan
- AI Search scaling takes "minutes to several hours": https://learn.microsoft.com/azure/search/search-capacity-planning
- SFTP hourly charge: https://learn.microsoft.com/azure/storage/blobs/secure-file-transfer-protocol-support
- VM Stopped is billed, Deallocated is not: https://learn.microsoft.com/azure/virtual-machines/states-billing
- Fabric pause keeps storage billing, and also bills outstanding overage: https://learn.microsoft.com/fabric/enterprise/pause-resume
- Versioning and soft delete accumulate (they add, not "multiply"): https://learn.microsoft.com/azure/storage/common/storage-plan-manage-costs
- Advisor "up to a day": https://learn.microsoft.com/azure/advisor/advisor-overview
- Policy aliases span API versions: https://learn.microsoft.com/azure/governance/policy/concepts/definition-structure-alias
- Foundry prompt/hosted agents, Responses API, toolboxes, agent optimizer: https://learn.microsoft.com/azure/foundry/agents/overview
- Unverified: preview labels on the optimizer and memory; Databricks default auto-termination; Firewall/NAT per-GB meters in product docs; metric-definition completeness.

---

## Orchestrator spot-checks (2026-10-31)

**Quotes.** Ten of twelve quoted passages exist verbatim where cited. Two are **misattributed files, not invented text**: the "Resource Graph (resources, and the change history of their properties)" sentence is in `02-learning-azure.md` §3 (not 03 §3); the "unit-price ground truth … (preview)" sentence is in `research/landscape.md` (not 02 §3).

**Facts verified directly on the Learn pages (2026-10-31)** — all confirmed:
- Azure Firewall FAQ: "When stopping and starting the firewall, billing stops and starts accordingly" (B-01 firewall half).
- Functions Consumption: "The option to host function apps on Linux in a Consumption plan is retiring on 30 September 2028"; Flex Consumption is the migration target (B-04).
- AI Search: Dedicated (SUs per hour; "to stop billing entirely, you must delete the service") vs Serverless (preview; "no compute charge when idle") (B-05).
- Resource Graph change data "queryable for 14 days"; platform metrics stored 93 days (B-03).
- Reservation exchange policy: from February 1, 2027 reservations bought after that date are not exchangeable where savings plans support the service; earlier purchases keep one final exchange; $50,000 cancellation cap per rolling 12 months; trade-in unchanged (B-07).
- MACC is tracked on the billing account (B-08).
- *(added after the exam-bank edits)* SQL Managed Instance General Purpose: a stopped instance is "no longer billed for compute and licensing costs but still billed for data and backup storage", with vCores and licence billed per started hour; Basic SKU public IPs "were retired" on September 30, 2025; the Databricks prepurchase page says "Cancel and exchange isn't supported … All purchases are final" (B-09 rows STOP-007, NET-012, DATA-006).
- Savings plans: "Unlike reservations, you can't cancel or exchange savings plans" and "Unused commitment for an hour expires and doesn't roll over"; Advisor's VM cost recommendations "don't take into account the presence of Reserved Instances (RI) / Savings plan purchases" (B-06c, B-07).

**Not independently verified (accepted on principle, not relied on for specifics):** the Front Door / SQL MI / PTU billing-granularity counter-examples in B-02 (the principle "granularity varies by meter" is clearly right; the SQL MI "started hour" part was confirmed above); the exam-bank rows ORPH-009 and DATA-012, and COMMIT-010 / REGION-003 (the reviewer found them supportable; not edited); the Firewall per-GB meter (the reviewer found it only on Q&A — kept hedged).
