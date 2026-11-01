# Model: not exposed by this runtime (GitHub Copilot); files read: README.md, 01-goals-and-scope.md, 02-architecture.md

## 1. Verdict

**No: not publication-ready.** Incorrect hosting and cost claims, ambiguous authority boundaries, and drafting residue prevent a stranger from trusting this as an implementation design.

Scope: all three files read completely, in the assigned order. No other design files opened. Cross-reference checks tested local link destinations and the cited `hub\` directory's existence without reading their contents. References below are relative to `docs\design\`.

## 2. Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | 02-architecture.md:53; :43 | 4, 5 | “no container registry and no container platform to run” | The reasoning plane uses Foundry hosted agents: custom code packaged into container images and pushed to Azure Container Registry. The Functions-only claim omits a required deployment dependency. | “Workflow, tool, engagement and action services run on Azure Functions; agent code runs in Foundry-managed containers deployed from Azure Container Registry.” |
| 2 | Blocker | README.md:33, :81; 02-architecture.md:63 | 3, 4, 5 | “learning adds nothing to the Azure bill”; “costs nothing while it waits” | Not deploying experimental resources does not make model, search, storage or replay computation free. README already identifies an always-ready cost floor. Durable waiting stops orchestration execution charges, not storage or always-ready baseline charges. | “Learning deploys no experimental resources, but its model, storage and compute use remains billable.” Replace the waiting claim with “Orchestration execution charges stop during waiting; storage and configured always-ready capacity remain billable.” |
| 3 | Blocker | 02-architecture.md:63 | 5 | “A hosted-agent session cannot wait” | Current Learn documents sessions that idle, persist state and resume, with deletion after 30 days of inactivity. This categorical limitation is outdated; it is not necessary to justify Durable Functions. | “Hosted sessions can idle and resume; Durable Functions owns approval deadlines and workflow state independently of agent sessions.” |
| 4 | Major | README.md:46, :67; 01-goals-and-scope.md:44–45 | 2, 4 | “where the contract allows”; “Administering the contract itself” | The glossary defines Contract as gateway configuration, but these passages mean the Azure billing agreement. A reader cannot distinguish commercial purchase eligibility from gateway authorisation. | Use “where the billing agreement and purchase role permit it” and “Administering the billing agreement itself.” Reserve Contract for hub configuration. |
| 5 | Major | 02-architecture.md:41–45, :57 | 4 | “Writes to Azure?” | The control and knowledge planes say No, while workflow state and Cosmos DB records are Azure writes. The intended restriction concerns managed estate changes, not platform persistence. | Rename the column “Changes managed estate resources?” State: “Platform services can persist their own state; only the runner can change opted-in estate resources.” |
| 6 | Major | 02-architecture.md:37, :98, :115 | 4 | “Every arrow from an agent goes through the hub.” | The sequence diagram sends the skeptic's result directly to the workflow. The blanket statements blur model/tool invocations with agent responses and internal service traffic. | “All model requests and agent tool invocations traverse the hub; agent responses and platform service traffic follow the paths in section 4.” |
| 7 | Major | 02-architecture.md:109–110 | 3, 4 | “else owner declines or is silent”; “reason becomes a Lesson” | Silence supplies neither a message nor an owner's reason. This flow would turn an absent answer into attributed estate knowledge. | Separate branches: “Decline with a reason: propose a sourced Lesson”; “Timeout: park or remind; record no Lesson.” |
| 8 | Major | 02-architecture.md:102–105 | 4 | “alt owner approves” | This approval precedes presentation of the canonical plan; a second approval follows. The diagram conflates willingness to consider a change with the bound decision that authorises execution. | Replace the first branch label with “owner requests plan review”; retain “approve canonical plan with MFA” for the authorising decision. |
| 9 | Major | 01-goals-and-scope.md:53 | 5 | “Rule-based cost recommendations in the portal” | The cited Learn page describes machine-learning-based VM/VMSS recommendations. Its retail-price and commitment exclusions concern those recommendations, not necessarily every Advisor cost recommendation. | “Advisor includes ML-based VM/VMSS recommendations; their savings estimates use retail prices and exclude discounts and commitment coverage.” |
| 10 | Major | 01-goals-and-scope.md:7 | 2, 3, 6 | “every rule covers the well-known head and goes stale the day it is written” | An unsupported universal presents a straw-man baseline. “Head” is undefined; no evidence establishes day-one obsolescence. | “Fixed recommendations need revalidation when service prices, usage or workload constraints change.” |
| 11 | Major | 02-architecture.md:129 | 4, 6 | “the repository's `hub/` instructions deploy the accelerator at a pinned commit” | The referenced `hub\` directory does not exist. Proposed capabilities are acceptable, but this reads as an available installation path. | “Phase 0 will add `hub/` instructions that pin and secure the accelerator before deployment.” |
| 12 | Minor | README.md:9, :17, :58, :66 | 2 | “Citadel governance hub”; “Atlas” | Citadel first appears at line 9, defined at 66 and linked only in Architecture. Atlas first appears at 17, defined at 58. Both are unfamiliar names in the opening explanation. | At first use write “Citadel, an API Management-based governance gateway” and label the diagram “Atlas: Azure charging knowledge.” |
| 13 | Minor | 01-goals-and-scope.md:15 | 2 | “cost-to-reduce” | This coined measure is not defined in the assigned files. It could mean attainable savings or the expense of making a change. | Replace with “estimated cost of implementing a reduction.” |
| 14 | Minor | README.md:52 | 1, 6 | “The full list, with alternatives, cost, security and reversibility, is in [decisions](12-decisions.md).” | Exact duplicate of the sentence at line 50. | Delete. |
| 15 | Minor | README.md:105 | 1, 6 | “in the same words” | The vocabulary reassurance makes sense as an answer to a previous consistency objection. The glossary already explains the terms. | “The [north star](../01-north-star.md) describes the product vision.” |
| 16 | Minor | README.md:109 | 1 | “are measurements, not arguments” | The unnamed contrast belongs to a review conversation, not an explanation of outstanding validation. | “Proof points P1–P10 will test the hub path, integration, approval integrity, data scale, retrieval, quality, injection resistance, permissions, tool pinning and cost.” |
| 17 | Minor | 02-architecture.md:143 | 1 | “eleven is our own sum, because Learn gives per-resource rules, not a total” | This defends arithmetic against an unintroduced objection. The resource inventory and acceptance check are useful; the defence is not. | “Release tests must reconcile the deployed private endpoints against this inventory.” |

## 3. Sentences I would delete

- README.md:52 — the duplicated decisions-link sentence quoted in finding 14.
- README.md:105 — the sentence beginning “The [north star](../01-north-star.md) is the idea this design realises, in the same words”; replace with the simple vision link.
- 01-goals-and-scope.md:7 — “Cost advice is written by people, and people do not scale.”
- 02-architecture.md:63 — “A hosted-agent session cannot wait, which is why waiting lives in workflows”; replace with the ownership rationale in finding 3.
- 02-architecture.md:115 — “Every arrow from an agent goes through the hub.”

## 4. Fact checks

Checked on **1 November 2026**, using public product terms and URLs only.

1. **Foundry hosted-agent deployment and lifecycle** — 02-architecture.md:43, :53, :63. [Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents), updated 27 October 2026: agents are custom container images pushed to ACR; sessions persist through idle periods and resume, with 30-day inactivity deletion. **Contradicts both the registry exclusion and categorical inability to wait.** This does not promise an indefinitely running request.
2. **Durable waiting is free** — 02-architecture.md:63. [Durable billing](https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-billing), updated 2 June 2026, stops invocation billing during await/yield but retains storage charges. [Flex billing](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan#billing), updated 30 September 2026, bills always-ready baseline memory. **Correct only for orchestration execution time, not total platform cost.**
3. **Foundry network injection is chosen at account creation; BYO networking supports platform-managed data** — 02-architecture.md:137, :143. [Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/networking-options), updated 9 September 2026: **supported**. Injection cannot be added to an existing account. No Microsoft-published eleven-endpoint total is asserted here.
4. **Advisor's recommendation method and savings exclusions** — 01-goals-and-scope.md:53. [Learn](https://learn.microsoft.com/en-us/azure/advisor/advisor-cost-recommendations), updated 1 April 2026: VM/VMSS recommendations use ML; their savings estimates exclude account discounts and reservations/savings plans. **Savings caveat supported for that scope; “rule-based” and the broader scope are misleading.**
5. **Azure Copilot Optimization Agent limitations** — 01-goals-and-scope.md:57. [Learn](https://learn.microsoft.com/en-us/azure/copilot/optimization-agent), updated 10 August 2026: **preview, VM/VMSS support and ten-item limit confirmed**. More precisely, it cannot automatically create or update budgets and alerts; “no budgets or alerts” is overcompressed.

## 5. Questions left unanswered

These concern the assigned entry documents; linked chapters may answer them.

1. Which Actions and agreement/access combinations form the minimum end-to-end phase-1 acceptance test?
2. What changes to the eleven-endpoint inventory and cost floor follow from the required container registry, particularly a private registry?
3. Can an owner review and approve the canonical plan from email outside the corporate network, or is network access mandatory?
4. How are “regret,” “surprises” and causal net savings measured, including displaced commitment coverage, corrected bills and the system's own cost?
5. After regional recovery from an optional geo-export, how is lost approval-consumption state handled so an already executed action cannot run again?
