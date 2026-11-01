# Model: GitHub Copilot (underlying model identifier not exposed) | Files read: `docs\01-north-star.md`, `docs\02-learning-azure.md`; cross-reference checks only: selected passages of `docs\09-the-learning-contract.md` (bill-observed gate, price ownership and sealed evaluation).

## Verdict

**No:** a stranger can understand the goal but cannot yet trust the access, evidence, privacy and safety promises as written. The ten named agents and Recommendation/Action/evaluation mostly agree across both assigned files; Ledger and the four evidence levels do not.

## Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | `01-north-star.md:160,168,257`; `02-learning-azure.md:167` | 4 | “Subscription reach without costs ... estimates at list prices” | These readers cannot match their own bill, yet 02 requires that match *before advice*. The linked gate confirms no exception (`09-the-learning-contract.md:38,52`). List-priced Recommendations in 01 cannot pass. | “Without bill access, offer usage leads and labelled list-price scenarios; a savings Recommendation requires an authorised bill check.” |
| 2 | Blocker | `02-learning-azure.md:161,165,276,281` | 4 | “The first two live in the Atlas.” | “Price-confirmed” includes a customer's own price sheet, while the Atlas is public; a two-estate observation is not automatically anonymous. The linked contract puts customer rates in the estate (`09-the-learning-contract.md:30`). | “The open Atlas holds public prices and privacy-reviewed aggregate behaviours; contracted rates and small-cohort observations stay in the estate.” |
| 3 | Blocker | `02-learning-azure.md:81,193,203` | 6 | “None of these was typed in as a rule. They are what the grammar produces” | Nothing has been built. Hand-written examples and “the Scholar's first-hour decode” read like observed system output, unlike the explicitly fictional Prism story. | “These are hand-worked examples of what the proposed grammar should infer; no agent has run them.” |
| 4 | Blocker | `01-north-star.md:265` | 5 | “check them against synthetic data and Azure's own what-if preview” | ARM what-if previews *template deployments*, not arbitrary Actions such as purchases or schedules; it also requires write permissions. This overpromises a safety check. | “Use a change preview where supported; otherwise disclose its absence and require Action-specific checks before approval.” |
| 5 | Blocker | `01-north-star.md:232,241,365` | 4 | “Learning spends no Azure resources: it reads what already exists.” | An owner-approved trial changes a billable existing resource and can incur charges that rollback cannot undo. “No new resource” does not mean “no Azure cost.” | “Learning never provisions solely to measure; an approved trial can incur charges and must disclose a cost ceiling and rollback risk.” |
| 6 | Major | `02-learning-azure.md:122,138,156`; `01-north-star.md:417` | 4 | “STATE Documented · seen on 2 estates' bills” | The example collapses public claim state and local bill evidence. The 01 glossary presents a mandatory-looking ladder; 02 says the four levels are *not* grades and its diagram skips price-confirmed. | “Atlas evidence: documented; estate evidence: bill-observed in two scopes.” Define evidence kinds, not a mandatory sequence, in the glossary. |
| 7 | Major | `01-north-star.md:67,177`; `02-learning-azure.md:165` | 2 | “the Ledger” / “the Unexplained Spend Ledger” | The first term is never defined in 01's glossary; the second tracks unanswered spend, while 02's lowercase ledger tracks predictions and outcomes. A stranger cannot tell whether these are one store. | “The Outcome Ledger records predictions and results; the Unexplained Spend Ledger tracks costs not yet explained.” Define both on first use and in the glossary. |
| 8 | Major | `01-north-star.md:117`; `02-learning-azure.md:116` | 3 | “The first bill that contains the meter settles the argument” | A line showing a charge cannot by itself prove a refund policy, rounding rule or causal link; bill periods and usage/change events must align. | “A closed bill line matched to usage and change history may support a scoped claim; unmatched charges leave it disputed.” |
| 9 | Major | `01-north-star.md:281,283`; `02-learning-azure.md:52` | 4 | “sealed test cases” / “test cases — is open source” | These files never separate published cases from withheld evaluation cases. If agents see the Commons cases, the claimed sealed rediscovery/transfer result is contaminated. | “Commons contains public regression cases; sealed evaluation cases and answer keys remain inaccessible to agents.” |
| 10 | Major | `01-north-star.md:122`; `02-learning-azure.md:48-52` | 4 | “Every meter, in every service, is one or a few of fourteen mechanisms” | The next document introduces *accrual* precisely because none of the fourteen fits. The universal claim defeats the proposed learning mechanism. | “Fourteen mechanisms are the starting vocabulary; unmatched meters trigger human-reviewed additions.” |
| 11 | Major | `02-learning-azure.md:199` | 4 | “a cap that bites (a candidate new mechanism)” | The AAU allocation limit stops work; it does not generate a charge. Treating every important constraint as a fifteenth billing mechanism blurs the grammar. | “The AAU limit is an availability constraint that caps active work, not a way money arises.” |
| 12 | Major | `02-learning-azure.md:102,219` | 3 | “every change is a diff the AI can read” | Public document revisions cannot cover private price sheets, negotiated terms or changes first visible on a bill, which both files otherwise rely on. | “Compare public revisions when available, authorised private price records when accessible, and closed bills for unannounced changes.” |
| 13 | Major | `01-north-star.md:265,269,363-368` | 7 | “The AI can write new Actions” / “it then carries the purchase out” | Approval is described, but the idea never states the essential boundary: agents propose, one executor writes Azure, and every model/tool call passes the adopter's Citadel hub. | “Agents only read and propose; Citadel governs every model/tool call, and a separate executor performs only the exact approved Azure write.” |
| 14 | Major | `01-north-star.md:218` | 3 | “what happens to the bill — and to reliability, performance and security — if we do X?” | The offered mechanism, the cost-focused Atlas, cannot alone infer workload SLO, performance or security effects. Those predictions have no identified evidence path. | “Predict charges from the Atlas; assess non-cost risks from estate telemetry, dependencies and owner constraints, or mark them unknown.” |
| 15 | Major | `01-north-star.md:354`; `02-learning-azure.md:4,101` | 6 | “The product runs on Microsoft's platforms and technology.” | Documents that declare themselves idea-only choose platforms and list implementation-specific Bicep/API sources; this mixes the *why* with an unevaluated *how*. | “The idea requires access to documented meters, usage and prices; platform and adapter choices belong in design.” |
| 16 | Minor | `01-north-star.md:330` | 4 | “Once the bill data has caught up (hours to days)” | This is still under “the first 24 hours”; a bill delayed days makes its owner questions impossible on day one. | “Day one maps access and resources; owner questions follow when the bill has posted.” |
| 17 | Minor | `01-north-star.md:126-128`; `02-learning-azure.md:185-187` | 6 | “Tuesday 09:00: Microsoft announces Azure Prism” | The long invented scenario appears nearly verbatim in adjacent documents. | “A new service can receive a documented profile before its first bill; see the full Prism scenario in 02.” |
| 18 | Minor | `01-north-star.md:322` | 6 | “predictions 81% right (I said 79%) · explained spend 72%” | The mock Monday email is not labelled fictional; precise figures can look like measured results for a product not built. | “Fictional example: these figures illustrate the report card, not measured results.” |
| 19 | Minor | `01-north-star.md:46` | 1 | “The scientific method is not a metaphor here; it is the operating system.” | This answers an unstated objection with a slogan instead of showing the method. | “It records predictions before tests, seeks contrary evidence and revises claims when outcomes disagree.” |

## Sentences I would delete

- `02-learning-azure.md:81` — “None of these was typed in as a rule.”
- `02-learning-azure.md:126` — “Claims live a life, not a status:”
- `01-north-star.md:46` — “The scientific method is not a metaphor here; it is the operating system.”
- `01-north-star.md:354` — “The product runs on Microsoft's platforms and technology.”
- `01-north-star.md:365` — “Learning spends no Azure resources: it reads what already exists.”

## Fact checks

1. **Confirmed:** same-region availability-zone transfer is not charged (`01:222`, `02:250`): https://learn.microsoft.com/en-us/azure/reliability/availability-zones-overview .
2. **Confirmed:** SRE Agent always-on costs 4 AAUs/agent-hour; its active-flow limit does not stop that charge; the trial waives always-on for up to 30 days (`02:197-199`): https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing and https://learn.microsoft.com/en-us/azure/sre-agent/evaluate .
3. **Confirmed:** Flex Consumption supports Linux only, and Linux Consumption retires 30 September 2028 (`02:70`): https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale .
4. **Confirmed:** Azure AI Search Serverless Developer is preview, without an SLA or in-place conversion to/from other tiers (`02:72`): https://learn.microsoft.com/en-us/azure/search/search-sku-tier .
5. **Overstated:** ARM what-if (`01:265`) predicts ARM-template deployment changes, not all Actions, and requires deployment write permissions: https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/deploy-what-if .

## Questions left unanswered

1. What useful, non-savings advice can a no-cost-access subscriber receive without passing the local-bill gate?
2. Who consents to open contributions, suppresses rare observations, and can retract an unsafe release?
3. How are Citadel routing and the exact approval-to-execution boundary enforced?
4. How are sealed evaluation cases isolated from the Commons' public test cases?
5. Which estate evidence supports non-cost consequence predictions when telemetry or SLOs are missing?
