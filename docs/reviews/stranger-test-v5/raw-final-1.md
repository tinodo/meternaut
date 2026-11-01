# Final cold read: README and north star

## 1. Explain it back

Azure Cost in Action is an unbuilt open-source proposal for AI specialists that investigate Azure costs, ask owners to choose, and verify outcomes. For unknown services it reads documentation and price lists, classifies meters using a cost grammar, checks claims against bills, and shares reviewed cross-estate observations; a novel meter remains provisional until observed. To predict changes it models meter relationships and replays recorded usage under alternative configurations, supplementing this with owner answers, existing changes, and small approved reversible trials. It probes each estate's access and agreement, labels numbers by their available price basis, and directs purchases to an authorised party. Agents propose; a separate executor changes Azure under an approval or human-written rule.

**What I could not answer from the assigned files**

- How does the approval service establish human intent rather than merely receiving a user's token?
- How does it distinguish a change's effect on a bill from other changes, discounts and varying usage?
- How can a partner customer establish its actual charges when only retail cost data is visible?
- How are rare observations and shared memory prevented from exposing information across customers or teams?

**Additional repository files opened for linked cross-checks:** `docs/design/README.md`, `docs/design/14-agreements-and-access.md`, and `docs/design/06-security-and-governance.md`.

## 2. Findings

| # | Severity | File:line | Quote | Why | Fix |
|---|---|---|---|---|---|
| 1 | Blocker | `README.md:18`; `docs/01-north-star.md:370`; `docs/design/06-security-and-governance.md:226` | “Silence is never consent” / “approve that person's R1 requests without a tap” | The linked proposed design admits a compromised bot could use a signed-in person's token to approve a small non-production change without their decision. A plan-bound record is not proof of consent. | Disable the R1 bot-approval path until an independent, plan-bound user interaction is enforced and tested; qualify the unconditional consent claim until then. |
| 2 | Blocker | `docs/01-north-star.md:159,162,167` | “Reads bill lines at the rate actually charged” | The partner paragraph and Microsoft Learn say customer subscription cost data can be retail, not necessarily what the customer pays its partner. Treating it as a billed rate can misstate savings. | “Subscription cost data may use retail rates; for partner-sold subscriptions, label it a retail scenario until customer-specific charges are verified.” |
| 3 | Blocker | `docs/01-north-star.md:234`; `README.md:55` | “The first five routes cost a little AI and some attention, and nothing in Azure” | Foundry model usage is Azure expenditure; some Azure Monitor log queries also incur scan charges. The zero-Azure-cost claim is materially wrong for a cost project. | “The first five routes avoid provisioning resources solely to learn; model, query, storage and data-transfer costs may still apply.” |
| 4 | Blocker | `docs/01-north-star.md:224-225` | “up 9% a month for four months, with no change in traffic” / “the transfer meter tracks request volume” | With steady request volume and one deployment moving all requests across regions, the explained transfer cost steps up; the story gives no driver for four months of compounding growth. | Make the bill jump after the deployment and remove “growing”, or quantify an evolving driver that reconciles to the stated 9% each month. |
| 5 | Major | `docs/01-north-star.md:158` | “sees every subscription under the agreement” | A billing-profile role covers that profile, not necessarily every subscription in the agreement; other visibility and purchase capabilities also depend on scope and role. | “Billing roles expose only their authorised scopes; probe subscription, price-sheet and commitment visibility separately.” |
| 6 | Major | `docs/01-north-star.md:160,332`; `docs/design/14-agreements-and-access.md:67` | “its own agreement: its rates, commitments and reach” | The first-day claim says all are learned, although the no-cost-access case and linked design allow the agreement and rates to remain unknown. | “First it probes its reach; the agreement, rates and commitments remain unknown wherever the available evidence cannot establish them.” |
| 7 | Major | `README.md:19`; `docs/01-north-star.md:126,285` | “only a privacy-reviewed scope and aggregate” / “provisional Profile v0.1” | The README appears to restrict all public knowledge to multi-organisation aggregates, while the day-zero profile is published before any bill observations. | “Public-source profiles can be shared after review; customer-derived observations require privacy-reviewed aggregates from several organisations.” |
| 8 | Major | `docs/01-north-star.md:18,117` | “each change shows up as a bill line” / “settles the argument” | Non-metering changes need not generate a charge, and aggregated or confounded usage can fit multiple explanations. One matched line does not necessarily establish causality. | “Some changes can be correlated with bill and usage data; keep a claim disputed where the evidence cannot distinguish competing explanations.” |
| 9 | Major | `docs/01-north-star.md:128,247` | “A test without a written prediction teaches nothing” / “a second trap nobody predicted” | Exploratory observations can reveal an unexpected fact and generate a hypothesis; the day-zero story itself relies on such a surprise. | “Record predictions before confirmatory tests; exploratory observations can reveal surprises and generate hypotheses.” |
| 10 | Minor | `docs/01-north-star.md:56` | “Detectors and Actions” | Both coined terms appear without an explanation at first use in the north star. | “Findings become Atlas claims, reusable checks that nominate leads (Detectors), and reviewed change recipes (Actions).” |
| 11 | Minor | `README.md:55` | “one governance hub (Citadel)” | The README does not say that this is an API Management gateway supplied by the adopting organisation; the linked design makes that prerequisite clear. | “Every model and tool call passes through the adopting organisation's Citadel governance hub, an API Management gateway.” |
| 12 | Minor | `docs/01-north-star.md:410` | “Not the Ledger” | This defensive correction answers no evident reader question; the Ledger has its own separate definition. | Delete “Not the Ledger.” |

## 3. Fact checks

Checked 2026-11-01:

1. **CSP customer cost data:** The universal actual-rate claim is wrong. [Microsoft Learn](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/get-started-partners) says customer-tenant subscription costs are at retail rates and require the partner's cost-visibility policy; those rates need not be the customer's invoice.
2. **Billing-profile visibility:** The agreement-wide claim is wrong. [Microsoft Learn](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/understand-mca-roles) scopes a profile role to subscriptions for that profile, whereas account roles cover the account.
3. **Cost of reading logs:** The zero-cost claim is wrong. [Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/cost-logs#table-plans) says interactive queries on Basic and Auxiliary tables are billed per GB scanned.
4. **Advisor shutdown savings:** Supported. [Microsoft Learn](https://learn.microsoft.com/en-us/azure/advisor/advisor-how-to-calculate-total-cost-savings) says shutdown and rightsizing estimates use retail rates; reservation and savings-plan estimates use actual rates and usage.
5. **Inter-availability-zone transfer:** Qualified support. Microsoft's [launched update](https://www.microsoft.com/releasecommunications/api/v2/azure/rss/update-on-interavailability-zone-data-transfer-pricing) says there is no inter-zone transfer fee, while [VNet pricing](https://azure.microsoft.com/en-us/pricing/details/virtual-network/) separately charges peering traffic. An older [Microsoft Learn Q&A answer](https://learn.microsoft.com/en-us/answers/questions/1792641/cost-of-bandwidth-with-respect-to-vnet-peering-and) says otherwise, so use the product pricing and update rather than that answer.

## 4. Verdict

No, I would not publish this as it stands. Correct the consent and pricing claims, the zero-cost assertion, and the worked investigation before publication.

**Counts:** Blocker 4 · Major 5 · Minor 3
