# Stranger test v5 — raw final 3

## Explain it back
Azure Cost in Action is an unbuilt design for an AI-agent team that helps organizations manage Azure costs. It learns service economics from Microsoft documentation, published price lists, bills, usage and outcomes—not model memory. For an unfamiliar service it classifies meters, tracks evidence and uncertainty, then estimates changes by replaying recorded usage against the customer’s price basis. It adapts advice to each agreement, discount, benefit and permission scope; if it cannot read costs, it labels list-price figures as scenarios and routes purchases to someone with authority.

**What I could not answer from these files:**
- How the Foundry and Agent Framework roles, tools, storage, model routing and required Citadel governance hub map to deployable components.
- Which identity permissions, consent, retention and security controls are required for billing reach, exports, metrics, repositories and pipelines.
- How cross-estate pooling enforces privacy beyond “several organisations” and a review (cohort threshold, re-identification testing and release criteria).
- Any measured accuracy, usability, operating cost or ROI; the system is not built.

**Files opened:** `final-read-brief.md`; `docs\02-learning-azure.md`, `docs\05-recommend-act-verify.md`, and `docs\09-the-learning-contract.md` in the requested order. No other repository files were opened.

## Findings

| # | Severity | File:line | Quote | Why | Fix |
|---|---|---|---|---|---|
| 1 | Major | `docs\09-the-learning-contract.md:87` | “a harness the system cannot see into sets test cases with known answers” | The agent cannot make a prediction without receiving a case input, yet later the same paragraph says the sealed cases are run. It is unclear whether inputs, answer keys, or both are withheld, weakening the central claim that learning is tested independently. | State that the case bank and labels stay hidden during development; at evaluation the harness supplies each input to the agent while retaining the answer key. |
| 2 | Major | `docs\02-learning-azure.md:106,131-132` | “a claim stays *documented* until a real bill line confirms it” | The state diagram lets a price list move a claim to *price-confirmed* before a bill makes it *bill-observed*. The prose skips that distinct level and contradicts the diagram. | Say that a claim starts documented, may become price-confirmed from a published price list, and becomes bill-observed only for an estate whose closed bill supports it. |
| 3 | Major | `docs\02-learning-azure.md:222; docs\09-the-learning-contract.md:31-32,50,96` | “A figure is called a *saving* only when a bill line confirms the meter.” | The contract calls bill-observed evidence a “savings claim,” but reserves counting a saving as achieved for outcome-confirmed measurement against a counterfactual. This unqualified wording collapses an estimate into a realized result. | Use “bill-observed savings claim/estimate” before outcome verification; reserve “achieved/verified saving” for an outcome-confirmed result, with Finance acceptance where reported. |
| 4 | Major | `docs\05-recommend-act-verify.md:49` | “Advisor's own documentation names two limits” | The Learn page checked supports the retail-rate basis for rightsizing/shutdown forecasts, but does not explicitly say those forecasts ignore existing reservations or savings plans. The sentence overstates what the cited documentation establishes. | Cite a Microsoft source that explicitly states the exclusion, or label it as an inference from retail-rate estimates and soften the attribution. |
| 5 | Minor | `docs\05-recommend-act-verify.md:10` | “everything a person needs to decide in under a minute” | This is a measurable performance promise for an unbuilt system, not a validated result. | Label it as a design target and say it must be measured with users. |
| 6 | Minor | `docs\05-recommend-act-verify.md:18,34-36` | “saves ~€710/month” | The card contract requires each consequence as a range or unknown, but the example gives point estimates for each option. | Give ranges for the example’s costs and effects, or explicitly mark the card as abbreviated and link the full version. |
| 7 | Minor | `docs\05-recommend-act-verify.md:50` | “found through the human graph” | “Human graph” is unexplained at first use; a stranger cannot tell whether it means a directory, org chart or relationship model. | Replace with plain language or link to a one-sentence definition. |

## Fact checks
*Microsoft Learn spot-checks read 2026-11-01; five claims checked.*

- **Confirmed — Linux Consumption retirement / Flex Consumption** (`docs\02-learning-azure.md:72`): support for Linux Consumption retires September 30, 2028; Flex Consumption is Linux-based. [Migration article](https://learn.microsoft.com/en-us/azure/azure-functions/migration/migrate-plan-consumption-to-flex) · [Flex plan](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan).
- **Confirmed — Container Apps idle billing** (`docs\02-learning-azure.md`, illustrative decodes): idle charges require a minimum replica count above zero and replicas at that minimum; they do not apply to serverless GPU apps. [Billing](https://learn.microsoft.com/en-us/azure/container-apps/billing) · [Serverless GPUs](https://learn.microsoft.com/en-us/azure/container-apps/gpu-serverless-overview).
- **Confirmed — SRE Agent AAU example and trial** (`docs\02-learning-azure.md:194-196`): 4 AAUs per agent-hour, token/model-based active usage, an active-flow limit that leaves always-on charges running, and up to 30 days of waived always-on charges for new customers. [Pricing and billing](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing) · [Evaluation](https://learn.microsoft.com/en-us/azure/sre-agent/evaluate).
- **Partly supported — Advisor limitations** (`docs\05-recommend-act-verify.md:49`): Learn confirms rightsizing/shutdown forecasts use retail rates and that reservations/savings-plan forecasts use actual rates and usage. It does not explicitly state that rightsizing/shutdown estimates ignore existing benefits. [Calculate cost savings](https://learn.microsoft.com/en-us/azure/advisor/advisor-how-to-calculate-total-cost-savings).
- **Confirmed — reservation exchange policy** (`docs\05-recommend-act-verify.md:216`): from February 1, 2027, reservations for services supported by savings plans are ineligible for exchange when purchased after the date; pre-date reservations retain one final exchange and trade-in remains available. [Policy changes](https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/reservation-exchange-policy-changes).

## Verdict
Yes after small fixes. Before publication, clarify the held-out test protocol and evidence labels, and cite or soften the Advisor claim.