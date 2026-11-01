# Round 1 - lens C (cost and operability) - raw report

> Reviewed at commit `20390d4` · model `grok-4.7` · saved as returned by the reviewer (this header added). Orchestrator spot-checks and the disposition of every finding: [disposition.md](disposition.md).

Assumptions: shared-hub ownership (A2) is not confirmed, so the own-hub columns are the planning numbers until design 14's week-1 check. "Standard setup in production" may mean only prod pays for search; dev and test still need a private data plane if exams run there. Numeric Language PII rates below are from the project's research, not re-read off the pricing page (that page rendered `$-`). GPT euro figures are from the snapshot of 2026-10-31T20:44:12Z. I re-ran `python tools\cost-model.py --lines Team` (total €1,817.99).

## Verdict

The design is cost-aware and, on the lines it prices, arithmetically honest. It is not yet a bill for the layout it describes.

The published shared-hub totals (€657 / €1,818 / €17,533) match the script and the snapshot. They do not match four Foundry accounts, PII on two contracts, a sandbox the roster calls, a Foundry IQ plan the pricing page bills separately, or the token quotas in design 04.

"Tokens dominate beyond the pilot" follows from the table at Team (66%) and Enterprise (82%). It does not follow at Pilot once a second and third search unit are added, and the 3% / 0.45% / 0.22% break-even figures follow only if the spend seeds are real and labour is excluded.

One operator cannot run the release gate as written: it needs two reviewers who are not the author, on top of a forked single-maintainer gateway.

What must change: fit the model to the layout and the quotas before anyone treats those three totals as the cost, and staff the platform as a small crew, not a side duty.

## Findings

### C-01 · Major · `<repo>\docs\design\12-cost-and-finops.md` §2 and §3; layout in `<repo>\docs\design\04-landing-zone-and-citadel.md` §7

Quote: "one Foundry account (`AIServices`) per environment: dev, test, prod, and one for the Lab"

Quote: "AI Search Basic (Foundry standard setup and the Atlas)" is priced at 1 unit for Pilot and Team (`search_units=1` in `<repo>\tools\cost-model.py`).

Why it matters. Standard setup brings its own Cosmos, Storage and AI Search. The model prices one Basic unit (€0.088877/hour × 730 = €64.88) through Team scale, plus "20 M and 5 GB for Foundry" on a single Cosmos line. Four accounts are four floors. Three unpriced Basic units are about €195 a month, 30% of the Pilot total, before extra private endpoints. Design 06 calls search "a floor that is already paid" — paid once in the model, possibly four times in the layout. Serverless is not the escape: Learn says "Private networking for indexers: Not supported" and "Shared Private Link resources: No planned support for the Serverless model" (https://learn.microsoft.com/en-us/azure/search/search-sku-tier, page dated 2026-08-04). The −€65 lever in design 12 §5 may never meet the private-network requirement.

Fix. Price one standard-setup trio per account that is actually private, or state that dev, test and Lab use platform-managed data (spike S-NET-2) and do not create those accounts until the phase that needs them. Do not call serverless a dated saving.

### C-02 · Major · `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.3 and `<repo>\docs\design\12-cost-and-finops.md` §2

Quote: "PII anonymisation (owner names, e-mail)" on `survey`, and "PII anonymisation" on `converse`.

Quote from research, not re-priced today: "PII (€0.88 down to €0.22/1K)" in `<repo>\docs\design\research\citadel.md` §7. The model prices Content Safety and not PII. The snapshot has no Language meter.

Why it matters. The vendor page lists PII on Standard (S), separate from the free shared 5,000-record bundle, and states "Text Records correspond to the number of 1,000-character units" (https://azure.microsoft.com/en-us/pricing/details/language/, fetched 2026-10-31; dollar amounts rendered `$-`, so the €0.88–€0.22 band is UNVERIFIED on that page). A 15,000-token prompt is on the order of 60 text records. Survey plus Diplomat at Team scale is a few thousand calls; at the research rates that is tens of euros to low hundreds, not cents, and it is absent from both the token table and §7's omissions. Content Safety itself is counted correctly against the snapshot: Team records 46,000, minus 5,000, times €0.329989 per 1,000 = €13.53, matching the generated line. The 5,000-free credit is the research figure (security catalogue SG5); I could not re-read it on a rendered Content Safety price table.

Fix. Add a PII line, seeded from characters on the survey and converse contracts only, and name the rate's source. Do not subtract a free tier unless the paid SKU grants it.

### C-03 · Major · `<repo>\tools\cost-model.py` and `<repo>\docs\design\13-decisions.md` ADR-37

Quote: `SANDBOX_H_PER_CASE = 0.0`.

Quote: "Dynamic sessions bill in one-hour increments, so computations are batched."

Why it matters. The roster gives `sandbox` to investigate, experiment and engineer (`04` §4.4). The pricing page bills "per session-hour" for the platform-managed interpreter (https://azure.microsoft.com/en-us/pricing/details/container-apps/, fetched 2026-10-31; the hour-rounding claim was not on that page — UNVERIFIED). The session-pool page sets cooldown to "between `300` and `3600`" seconds (https://learn.microsoft.com/en-us/azure/container-apps/session-pool, dated 2026-03-31). Snapshot rate: €0.026399 per hour in Sweden Central. Batched to one session-hour per case, Team is about €26 and Enterprise about €528. Unbatched, ten Detective sessions at a full hour each is about €260 at Team and about €5,200 at Enterprise — enough to dent "compute is a small line", not enough to dethrone tokens. Zero is not a seed; it is a deletion. The same gap covers the AI Red Teaming Agent: research R1 prices it as "Target, attacker and evaluator model consumption (`UNVERIFIED`)" and the model has no line.

Fix. Put a batched session-hour seed in the model, and a red-team token seed marked UNVERIFIED until measured. Keep batching; do not price the path at zero.

### C-04 · Major · `<repo>\docs\design\04-landing-zone-and-citadel.md` §4.3 and design 12 §2

Quote: "The seeds below are *starting points to be fitted by the cost model*"

Quote: investigate prod seed "60,000 · 80 M".

Why it matters. The cost model never reads those quotas. One case's investigate calls (Detective, Skeptic, Economist in `CASE_WORK`) are about 261,000 input-plus-output tokens. 80 million divided by 261,000 is about 306 cases a month. The Team scenario is 1,000 cases; Enterprise is 20,000. Govern is capped at 60 M tokens a month while Team exams alone are 1,350 synthetic cases. Either the hub stops the work the table prices, or the caps will be raised and are not yet a control. ADR-26 says the hub is the spending cap. A cap that is not the forecast is not a cap.

Fix. Scale each group's monthly quota to the scenario it is supposed to allow, print the implied euro cap next to the scenario total, and fail `--check` if they diverge by more than a stated margin.

### C-05 · Major · `<repo>\docs\design\04-landing-zone-and-citadel.md` §3.2 and design 12 §7

Quote: "the cost is modest and is counted in [12](12-cost-and-finops.md)."

Quote: "data egress and peering (cents per gigabyte, small here)" — listed under "What the model leaves out".

Why it matters. Design 04 asserts a cost is in the model. Design 12 says the model omits it. The money is probably small (token payloads are megabytes, not terabytes). The defect is a false claim that a cross-region spoke, which ADR-04 accepts, has been costed. Same pattern, smaller: ADR-05 and the always-on table say the managed firewall is "€250–800", while the optional table and the snapshot agree on Standard Deployment €1.099965/hour × 730 = €803 before data processed (€0.01408/GB). Avoiding it is still right; the range is not.

Fix. Delete "counted". Add a peering line, even if the seed is 10 GB. Replace €250–800 with the snapshot's deployment hour plus a data seed.

### C-06 · Major · design 12 §3 and `<repo>\docs\design\01-requirements-and-principles.md` §4 Q-COST-1

Quote: "One case costs well under a euro."

Quote: "after the first quarter the system's all-in cost is below the savings it has verified."

Why it matters. €0.633 is the marginal token cost of one case on the EU Data Zone. The table's own "Per case" column is the all-in share: €6.57 at Pilot, €1.82 at Team, €0.88 at Enterprise. Design 12 §7 leaves out "people's time". At Pilot the cloud bill is €657. Twenty hours of an operator already exceeds that. The 3.29% break-even is €657 / €20,000, and €20,000 is a seed (€4,000 per subscription per month), not a measurement. Halve the spend seed and the break-even share doubles. Q-COST-1's "all-in" and the model's "all-in" are not the same quantity. The arithmetic of the published percentages is correct; the claim that break-even is "a small share" is a claim about the denominator.

Fix. Say "marginal tokens" wherever €0.63 appears. Define all-in as cloud bill plus named labour, or stop saying all-in. Replace spend seeds with the first estate's export before quoting a percentage.

### C-07 · Major · `<repo>\docs\design\11-delivery-and-operations.md` §1 and §3

Quote: "by one operator and a few contributors"

Quote: "two reviewers, neither the author"

Quote, ADR-02: "a **single-maintainer sample** with no releases"

Why it matters. Counted from the design: 6 stack layers per spoke, 7 pipelines, 27 contract products (9 groups × 3 environments) with quarterly key rotation, 14 agents (the design 05 §2 table has fifteen lines against "Fourteen agents"), 18 drift layers, 5 clocks, 11 runbooks, up to 4 Foundry accounts × 9 projects, a weekly gated framework bump, and a Citadel fork with no upstream releases. The release gate cannot be satisfied by one person. Ask-only degradation is the right steady state; it does not shrink that weekly load. Operator time is the real Pilot cost (C-06), and this surface is where it goes.

Fix. Publish a minimum crew: three people who can release, one of them the sponsor of record. Do not create the Lab account, the second spoke's full standard setup, or nine projects per account until the phase in design 14 that needs them. Keep the Citadel fork's upgrade as a named, budgeted job, not an implicit evening.

### C-08 · Minor · design 05 §5 and §7, and `cost-model.py` `HOSTED_H_PER_CASE` / `CASE_WORK`

Quote: "the default is 15, which would bill a 30-second job thirty-fold"

Quote: "the prefix is written once per release, not per case."

Why it matters. The hosted-agent page deprovisions "when the idle timeout is reached" and shows active, idle and resumed states (https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents, dated 2026-10-19). It does not say idle minutes are billed. The thirty-fold claim is the design's inference — UNVERIFIED. The seed is 0.45 hours per case against 26 calls in `CASE_WORK`. If each call is a session and idle is billed, idle alone is about 0.87 hours. If one session per role, 0.45 hours can cover it. Diplomat's 15-minute timeout is not in the seed. Team hosted agents are only €147, so the money is second-order. Separately, the model charges cache-write on every call (`cw=6_000`) while design 05 writes the prefix once per release. That is why caching only moves 0.633 to 0.676. Under the design's rule the saving is larger. Pessimistic, and still the wrong lesson.

Fix. Derive hosted hours from sessions × (active + idle), and state whether idle is billed once a page says so. Charge cache-write once per release in the sensitivity, and rewrite the sentence to match.

### Arithmetic (five checks, all matched)

Prices from `<repo>\docs\design\cost\prices-snapshot.json`, Sweden Central unless noted. FX 0.87997.

1. Detective, EU Data Zone, GPT-6.1 Sol ShortCo Standard: input €2.111932/1M, cached input €0.105597, cache write €2.639916, output €10.559662. Per call (15,000 in, 70% cached, 6,000 write, 1,500 out) = €0.04229; × 10 calls = €0.423. Table: 0.423.
2. Skeptic, Mistral Large 3 Data Zone, €0.000484 and €0.001452 per 1K, uncached: 4 × (12,000 × €0.484 + 1,000 × €1.452) / 1e6 = €0.029. Table: 0.029.
3. Team private endpoints: 28 × €0.0088 × 730 = €179.87. Table line: €179.87. Search Basic: €0.088877 × 730 = €64.88. ACR Premium: €1.466561 × 30.4 = €44.58.
4. Team Cosmos: (200 + 20) × €0.268391 + (10 + 5) × €0.219993 = €62.35. Content Safety: 41 × €0.329989 = €13.53. Both match `--lines Team`.
5. Break-even: €1,817.99 / €400,000 = 0.4545%, published 0.45%. Pilot €657 / €20,000 = 3.285%, published 3.29%. Enterprise €17,533 / €8,000,000 = 0.219%, published 0.22% (the prose's "0.2 %" is a slip). Terra instead of Sol halves the reason-role prices in the snapshot and yields €0.332 per case, 48% below €0.633. Lever 4's "about −48 %" matches. Global versus Data Zone is €0.529 / €0.633 = 16% less, as the prose says.

Seeds that move the total: at Enterprise, `cases` (20,000 × €0.633 = €12,651, 72% of the bill), then Detective calls and input size (€0.423 of €0.633). At Pilot, `exam_cases` (€217 of €657) and a shared hub (€440–€1,200 if absent). Cache share moves a case by about 6%. `study_changes=40` everywhere is plausible; `survey_calls` at 30 per subscription is linear; exam volumes of 600 / 1,350 / 2,700 are a ceiling, which is why exams exceed cases at Pilot (€217 versus €63). That sentence is true. "A third of the money is the floor" is not: €272 / €657 = 41%.

## Decision table

| ADR | Verdict | Confidence | Strongest alternative | What would change my mind |
|---|---|---|---|---|
| 01 | Agree | High | Handoff or A2A through the hub | A measured token saving that beats the extra injection path and the lost envelope |
| 02 | Agree with changes | High | Standalone AI Gateway (no price today) | A published price, private ingress and a contract path; until then budget the fork's maintainer |
| 03 | Agree with changes | High | One subscription, or one nonprod account | S-NET-2 shows a hosted-agent project can be private without a second search floor |
| 04 | Agree | High | West Europe, about 30% cheaper API Management on the research figures | West Europe gains the missing capability list, including a hosted-agent meter |
| 05 | Agree | High | Managed VNet | It gains outbound logs, a bring-your-own firewall, and a price below the landing-zone firewall. The €250–800 range is low versus the snapshot |
| 06 | Agree | Medium | Three coarse groups | S-ID-2 fails and header attribution becomes permanent |
| 07 | Agree | High | Standing write roles | PIM can activate these identities under the licences the tenant has |
| 08 | Agree | High | Teams Approvals app | Published agents gain target-bound card actions |
| 09 | Agree with changes | High | Terra (or Luna) as the default reason tier, Sol only after the exam | S-MOD-1 shows a material quality loss on Terra. Global-for-everything still violates C9 |
| 10 | Agree | Medium | Same-family judge | No cheaper independent EU family passes the exam. The "not a luxury" sentence is true only for the Mistral proxy the model hard-codes |
| 11 | Agree | High | Atlas in Cosmos or PostgreSQL | Foundry IQ's paid plan is unavoidable and a database is cheaper at rest. It is not, today |
| 12 | Agree | High | Azure SQL serverless, the named fallback | The vector test fails, or the hourly export misses the one-hour target |
| 13 | Agree | High | ADX Dev/Test at about €105, or Synapse per TB | A Microsoft engine with zero standing compute appears. The C1 exception is the right one |
| 14 | Agree | High | Memory for the Diplomat only | Memory is generally available, private, and its calls pass the hub |
| 15 | Agree | Medium | Foundry toolboxes | S-NET-1 shows toolbox calls in the hub logs |
| 16 | Agree | High | One shared Lab subscription | A product with a hard cap exists. Budgets still stop nothing |
| 17 | Agree | High | Foundry publish to Teams | Card actions and private ingress exist. Voice off is correct |
| 18 | Agree | High | Managed Grafana | Private Grafana no longer forces a paid tier, or the cheap table plans reject the hub's tables |
| 19 | Agree | High | Guardrails and Defender alone | The attack suite shows a deterministic gate is unnecessary |
| 20 | Agree | High | Enable every Defender and Agent 365 plan | Defender for AI stays cheaper than the tokens it scans. At €0.000704/1K it does not, on the cheap tiers |
| 21 | Agree | High | An agent that reads telemetry | Native drift detection covers hosted agents and contracts |
| 22 | Agree with changes | High | Foundry evaluations alone | Red-team and judge tokens are measured and still inside the exam seed |
| 23 | Agree | High | Terraform, or Azure DevOps as the accelerator ships it | A required resource has no Bicep type |
| 24 | Agree | High | Customer-managed keys everywhere | A named compliance driver. Managed HSM at about €2,000 a month stays unjustified |
| 25 | Agree | High | Regional deployments only (+30–50% in the research) | A recorded decision allows Global for a named class |
| 26 | Agree with changes | High | Budget-triggered disable | The quotas in design 04 are fitted to design 12, or a platform hard-spend limit appears. Budgets remain alarms |
| 27 | Agree | High | SRE Agent as the operator | A 30-day trial beats 4 × 730 × €0.096797 = €283 a month of own-detector work |
| 28 | Agree | High | A marketplace managed application | Adopters ask, and multi-tenant is in scope. It is not |
| 29 | Agree | High | Premium assessment templates now | An audit date is set |
| 30 | Agree | Medium | A warm second region | The operator judges a regional outage of this system intolerable. Doubling the floor is then a choice, not a surprise |
| 31 | Agree | High | Floating references | Nothing. Pins are the cost-control surface |
| 32 | Agree | High | Confidential Ledger at about €103 | S-DATA-2 shows appends fail under the locked policy |
| 33 | Agree | High | Durable Extension on Functions | S-ORCH-1 loses or double-runs a step. Scale-to-zero while a person decides is the point |
| 34 | Agree | High | Routines as the only clock | A routine can carry an envelope and a budget |
| 35 | Agree with changes | High | Refuse to run without an existing hub | A2 is confirmed. Until then the business case uses the own-hub column, not €0 |
| 36 | Agree | Medium | All Python | The Python SDK gains card-action routing. Two toolchains are an operability cost, accepted |
| 37 | Agree with changes | Medium | Code in the hosted microVM | A measured session is cheaper than the risk. The model still needs a non-zero seed. Hosted agents "push it to Azure Container Registry" (page in C-08); private endpoint "available in the Premium container registry service tier" (https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-endpoints, dated 2026-02-11). Source deploy is not that path |

## What is strong

Keep the selector rule, the generated table, and `--check`. The five hand checks matched. Avoiding the managed firewall, Managed HSM, a standing Data Explorer cluster, SRE Agent's 4 units an hour, and Provisioned Throughput is the right reading of cost-efficient. Cosmos serverless, jobs rather than warm replicas, and routing public work off the EU premium are the same idea. The always-on ledger is the right artefact; add the rows in C-01 to C-03, do not replace it. Putting exams in the model, and saying they cost more than the cases they protect at Pilot, is the most useful sentence in the document. DuckDB behind a swappable interface is a justified C1 exception. Cost per verified euro saved is the right unit only if the denominator is measured and the numerator includes the crew.

## What is missing

1. A model line per Foundry account that uses standard setup, not one search unit for the whole estate of environments.
2. PII text records, Foundry IQ agentic retrieval ("Foundry IQ knowledge bases require a subscription and a standard agentic retrieval plan", https://azure.microsoft.com/en-us/pricing/details/search/, fetched 2026-10-31; the euro rate rendered as `$-` and is UNVERIFIED), and a non-zero session-hour seed. Semantic ranker is a listed add-on on that page; its price was not readable — UNVERIFIED.
3. Contract quotas fitted to the three scenarios, with the euro cap printed beside the total.
4. Labour and the minimum crew inside Q-COST-1, or an explicit statement that "all-in" means cloud only.
5. A conditional Container Apps management hour. Learn bills "private endpoints and planned maintenance" as a Dedicated plan management charge "regardless of whether you use the Consumption or Dedicated plans" (https://learn.microsoft.com/en-us/azure/container-apps/billing, updated 2026-03-25). The design's endpoint list does not include Container Apps. If an implementation adds one, the snapshot's Environment Private Endpoint meter is €0.114396/hour, about €83.50 a month each, and it is not in the model.
