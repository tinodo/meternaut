# Cold read 2: `04-finding-out-without-spending.md`, `design\README.md`, `design\14-agreements-and-access.md`

Beyond my three files I opened only for cross-references: `docs\01-north-star.md` (status line, glossary) and, by search, `design\03`, `05`, `06`, `10`. Learn pages read are listed under fact checks.

## 1. Explain it back

A proposed, unbuilt team of AI agents (Microsoft Foundry, Agent Framework, every call through a Citadel gateway) that keeps an Azure estate cost-efficient. It reads bills, usage and documentation, investigates waste, challenges itself, tells owners in plain words and, after an approval bound to one exact plan, one runner changes Azure and verifies.

A service it has never seen enters a Git-held Atlas as a documented claim, is price-confirmed against price lists, then bill-observed and outcome-confirmed through bills, replays, owners' answers, pooled observations and owner-approved trials. It never deploys to learn.

For bill impact it writes a blueprint first, replays history under another SKU or commitment, and prices in the order contracted, billed, list, naming the basis.

For another agreement or access level it probes read-only, stores a per-scope capability profile, falls back to list prices and hands purchases to the billing owner or partner.

**I could not answer**
- How a never-seen service gets its first claims (who extracts, who reviews); "within hours" has no mechanism here.
- How `price-sim` maps a change to meters; what tolerance "reproduced the real bill" means.
- Who performs a trial's automatic rollback, under which approval.
- The minimum cohort size, who runs the privacy review, and what stops a mistaken or hostile contributor from steering the shared Atlas.

## 2. Findings

| # | Severity | File:line | Quote | Why | Fix |
|---|---|---|---|---|---|
| 1 | Blocker | 14:20, 14:64 | "No billing scope: subscriptions only" | Wrong: Learn says a pay-as-you-go billing account exists, so step 2's rule ("one or more means billing reach") cannot hold for it. | "A billing account exists (account administrator) but no FOCUS export; costs are read per subscription." Step 2: only EA, MCA, partner accounts count as billing reach. |
| 2 | Major | README:9 | "it works with whatever agreement and level of access an organisation has" | Absolute. 14:148 says classic CSP and sponsorship subscriptions give "nothing about their cost"; 14:146 says partner discounts are "not visible". | "It adapts to the agreement and access it finds and says what it cannot see (14, section 8)." |
| 3 | Major | 04:109 | "no bill line, name or identifier travels with it" | The only data-leaves-the-estate promise is absolute, yet "its receipts" travel and are undefined. Cohort size, privacy reviewer and the holding place of unpublished observations are missing. | Define a receipt (meter, unit, quantity band, region), the cohort, the reviewer, the staging place; state that negotiated rates never leave. |
| 4 | Major | 04:216, README:33 | "Until a bill line contains it, a claim stays *documented only*" | README and the north-star glossary add *price-confirmed* (price list shows the rate). README then says a never-used meter "cannot be found this way", yet documents and price lists find it. | "…stays documented or price-confirmed, never bill-observed"; README: "cannot be bill-observed". |
| 5 | Major | 04:4, 04:155, 04:195 | "a new service can get a provisional profile within hours" | Doc 04 never says nothing is built (the north star does) and speaks as an operating system; a latency and a "year in" share read as facts. | Header: "Status: ideation, nothing built; 'does' means 'is designed to'." Recast both as targets. |
| 6 | Major | 14:57, 14:115 | "reservation and savings plan effects come from `EffectiveCost`" | Learn: partner-sold subscriptions show reservation usage at zero actual and amortised cost; Partner Center says purchases "aren't shown in cost data", the partners page says they are. The partner path's check may never fire; 14:3 promised to flag such conflicts. | Add both to section 8; confirm partner purchases with the partner, not the bill. |
| 7 | Major | 14:17 | "Enterprise Agreement (EA). Billing scopes: enrollment, department, enrollment account" | Missing: EA bought through a reseller. Learn error `IndirectCostDisabled` (https://learn.microsoft.com/azure/cost-management-billing/costs/cost-management-error-codes): cost views need the partner to publish prices. Not in the probe list (14:65). | Add an "EA, indirect" case: probe error, price basis, whom to ask. |
| 8 | Major | README:64, 67 | "(Passwords and keys are called keys and secrets)" | Two coined terms (Credential, Contract) collide with Azure vocabulary and are patched by disclaimers (67: "nothing to do with an Azure agreement") that only a witness of the naming debate needs. | Rename Credential "Autopilot rule" (north star too); use Citadel's "access contract"; delete both disclaimers. |
| 9 | Major | README:82 | "a pilot costs a few hundred euros a month, mostly fixed (search, private endpoints, an always-ready function instance)" | Leaves out the Citadel hub the same page lists as a need; `10-cost-and-finops.md:122`: the hub is "not in the totals". | "…excluding the Citadel hub (shared platform cost; a gateway adds to it, see 10)"; say "a month" for the enterprise figure. |
| 10 | Minor | 04:74, 04:214, README:33, 14:99 | "built by nobody" · "Honesty is part of the method." · "which Partner Center's page requires" | Flourishes and a half-explained aside read as discussion residue; 14:99 hints at a source conflict never stated (06:168 says Reservation Purchaser, Partner Center says Owner). | Delete the first two and "The honest gap"; 14:99: "Partner Center requires Owner"; reconcile with 06. |
| 11 | Minor | 04:70, 04:152, README:50 | "The AI reads them four ways." | Counts do not match: three ways plus a rule; "Two budgets" then three bullets; ten decisions plus "One more". | "three ways, plus a rule"; "two budgets and a research director"; "an eleventh principle". |
| 12 | Minor | 04:109, 04:117, 04:144, README:40, 47, 110, 14:47, 61 | "canary saving" · "review tier" · "Durable group" · "cost-trap bank" · `price-sim` | Undefined at first use. "Profile" means three things (service, capability, deployment); "directory" clashes (14:116 partners are "not in the directory"; 14:139 the Directory holds the partner contact); "Lesson" is person-taught (README:75) but system-written (04:164); README:46 "the AI executes" purchases with "no standing purchase role", 14:114 has the identity "hold the purchase right". | Define or link once (`docs\research\cost-trap-bank.md` exists; Citadel is never linked: github.com/Azure-Samples/ai-hub-gateway-solution-accelerator, which I confirmed); "deployment profiles"; "the runner buys, under a grant removed after the run". |
| 13 | Minor | 04:1, 04:24, 04:208, 14:93 | "improve its own process without being rebuilt" · "nothing in Azure" | Absolutes without mechanism: Trial can move the bill, the AI itself bills in Azure, self-changes have no stated review, 14:93 ("never reaches another's") has no isolation mechanism. | "Finding out without deploying"; "nothing in the customer's estate"; "the Conductor proposes, a person approves"; link the isolation mechanism. |
| 14 | Minor | 14:22, 14:67, 04:80 | "Management groups work as a cost scope for EA and pay-as-you-go" | Learn: management-group exports are EA-only; data is kept at least seven years (portal and APIs show 13 months, older via Exports REST API); Dev/Test offers MS-AZR-0148P/0148G also map to EA/MCA. | Correct each; "for example" before the offer ids. |

## 3. Fact checks

| Claim | URL read | Result |
|---|---|---|
| Pay-as-you-go has "no billing scope" (14:20) | https://learn.microsoft.com/azure/cost-management-billing/manage/view-all-accounts | Wrong: "A billing account for a Microsoft Online Services Program is created when you sign up". |
| Partner-sold: retail rates, no partner discounts, cost visibility off by default; customer needs Owner (14:19, 14:99) | https://learn.microsoft.com/azure/cost-management-billing/costs/get-started-partners ; https://learn.microsoft.com/partner-center/customers/give-customers-permission | Supported. Both pages add what 14 omits: zero-cost reservation usage; purchases shown versus "aren't shown in cost data". |
| Savings plans not offered under pay-as-you-go; role and policy rules (14:100) | https://learn.microsoft.com/azure/cost-management-billing/savings-plan/permission-buy-savings-plan | Supported (EA, MCA, partner only; billing profile owners buy even if the policy is off). |
| Query API 12/60/600 query units, a month costs one; Cost Details refreshed every four hours, 2 GB; no FOCUS for pay-as-you-go (14:42-45) | https://learn.microsoft.com/azure/cost-management-billing/costs/manage-automation ; https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports | Supported. |
| Management groups for EA and pay-as-you-go (14:22); "13 months" (04:80) | https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports ; https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data | Partly wrong (EA-only exports; retention at least seven years, 13 months in the portal). |

## 4. Verdict

Yes, after small fixes. One wrong Microsoft fact, an unqualified privacy promise, an unstated "nothing is built" in doc 04 and a handful of residue sentences would cost a stranger's trust, but the work is otherwise sourced, dated and candid about its limits.
