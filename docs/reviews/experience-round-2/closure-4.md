# Closure: raw-b-finops (13) and raw-g-novice (17)

## 1. Findings

| Report | # | Severity | Status | Evidence |
|---|---|---|---|---|
| B-finops | 1 | Blocker | CLOSED | `03-organisation-journeys.md:58`: "A reservation renews by default: doing nothing buys a replacement, outside our control". With renewal off, usage returns to pay-as-you-go. |
| B-finops | 2 | Blocker | CLOSED | `03-organisation-journeys.md:51`: "The approval binds the USD commitment, term, payment frequency, auto-renew and scope". `cards\data\ok-on-page.json:11` states USD 25.00 an hour, not a binding euro total. |
| B-finops | 3 | Blocker | CLOSED | `07-reports-and-dashboards.md:68`: "issued as Azure prepayment credit" and "never booked in Verified saving." The bridge row is "Held back, provisional". |
| B-finops | 4 | Blocker | CLOSED | `07-reports-and-dashboards.md:70`: "The ledger reconciles only where an invoice for the same billing scope and currency is readable"; otherwise "Invoice not available". `03-organisation-journeys.md:134` repeats that status. |
| B-finops | 5 | Blocker | CLOSED | `07-reports-and-dashboards.md:79`: "Verified only with the partner's rates and invoice evidence". |
| B-finops | 6 | Major | PARTLY | Scope type and later members are on the page (`experience-approval-page.svg:36`: "Management group Order platform: three production subscriptions today, and any later member"). Benefit-scope id, subscription ids and billing-profile id are still absent. Replacement: "Benefit scope: management group [id]; eligible today: [subscription ids]; paying subscription: [id]; billing profile: [id]; a later member is eligible." |
| B-finops | 7 | Major | PARTLY | Overlap pressure is softened, but `experience-approval-page.svg:59` still says "from 1 July it forgoes about €140 a day" with no unused-commitment figure. Replacement: "Before 30 June, incremental saving on usage the reservation does not cover is [X], with [Y] unused commitment; from 1 July it is [Z], Expected, at your agreement's rates." |
| B-finops | 8 | Major | CLOSED | `03-organisation-journeys.md:58`: "the 60-day notice carries a scenario, not a price check; the price check and two new approvals come later." |
| B-finops | 9 | Major | CLOSED | `03-organisation-journeys.md:63`: "Red Hat, SUSE and pre-purchase plans are excluded; the refund method depends on the agreement." |
| B-finops | 10 | Major | CLOSED | `07-reports-and-dashboards.md:64`: "Beside each saving total sit one currency, one price basis and one cost view". The wireframe selector is "Price basis: your bills", not "all". A leftover header is N-4. |
| B-finops | 11 | Major | CLOSED | `cards\data\ok-on-page.json:9`: `"classLabel": "Two people"`. `04-messages-and-cards.md:89`: "C5's header is the class, \"Two people\" for a purchase". |
| B-finops | 12 | Major | CLOSED | `07-reports-and-dashboards.md:47`: "\"On track\" appears only if the forecast meets every remaining milestone and the final balance by its due date". The tile shows commitment, spend, milestone, invoice date and shortfall. |
| B-finops | 13 | Minor | CLOSED | `03-organisation-journeys.md:71`: "utilisation and unused commitment (vacancy)". |
| G-novice | 1 | Blocker | PARTLY | The false ownership sentence is gone. `cards\data\your-ok.json:39` still ends "and you chose this option" and names no owner for vm-qa-web-01 to 04 or sql-qa-orders. Replacement: "Why you are getting this: you reviewed this plan. It changes vm-qa-web-01 to 04 and sql-qa-orders; the directory lists you for 3 of 14 in rg-webshop-qa, and you created the other 11." |
| G-novice | 2 | Blocker | CLOSED | `cards\data\your-ok.json:11`: "Thursday 19:30 CET, then each weekday at 19:30". "22:00" is absent from `docs\experience`. |
| G-novice | 3 | Blocker | CLOSED | `cards\data\your-ok.json:17`: "Deallocated (compute is not billed) from 19:30 to 07:30 and all weekend". |
| G-novice | 4 | Major | CLOSED | `cards\data\your-ok.json:26`: "I ask you before I switch anything on; I do not do it myself." |
| G-novice | 5 | Major | OPEN | `04-messages-and-cards.md:89` says the Recommendation "stays one tap away in My decisions", but C4 has no such action, and `06-web-pages.md:13` says a card hands that page nothing. Evidence and the other options still leave the thread. Replacement: "The plan card keeps a button, See the Recommendation, opening the evidence and the other options; it approves nothing." |
| G-novice | 6 | Major | CLOSED | `experience-recommendation-card.svg:33`: "prefer this to option C, which saves more but needs about two days of engineering." Option C states €940 with its range, word and basis (`:73`). |
| G-novice | 7 | Major | PARTLY | The checked text now says "You told me" (`cards\data\recommendation.json:16`), but the label is still "What I checked" (`cards\recommendation.json:128`), and the card has no Strongest doubt line though `04-messages-and-cards.md:73` requires it beside the check. Replacement: "What you told me: a job runs on the last Tuesday. Strongest doubt: [the objection], and what was done about it." |
| G-novice | 8 | Major | PARTLY | `04-messages-and-cards.md:58` now puts two chips on saving figures only. Still missing: `cards\data\recommendation.json:14` "forgoes about €23 a day" has no basis in that sentence, and C5 shows neither "amortised" nor "as invoiced" (see N-5). Replacement: "Keeping things as they are forgoes about €23 a day, at the rates on your bill." On C5, put "amortised" beside the saving and "as invoiced" beside the monthly payment. |
| G-novice | 9 | Major | CLOSED | `01-people.md:17`: "Lars, finance approver" decides "Finance approval of a purchase". `01-people.md:13`: Nadia decides interruption and standing permissions, not finance approval. |
| G-novice | 10 | Major | CLOSED | `01-people.md:11`: "Weekly desk (a digest of up to five items, each its own decision)". `cards\weekly-desk.json` offers Open per item, not an approval. |
| G-novice | 11 | Major | CLOSED | `14-decisions.md:30` names "Not now" only as the rejected alternative. `04-messages-and-cards.md:89`: "C4's \"Cancel\" drops the plan and changes nothing." Talk to a person is visible on the C3 rendering. |
| G-novice | 12 | Major | PARTLY | One-tap approval in the card is the defined class (`01-people.md:24`). Explain still has two homes: `README.md:18` "Explain in conversation" against `04-messages-and-cards.md:31` "asked in the card, answered in the thread". Replacement: "Details in the message; Explain is asked in the card and answered in the thread." |
| G-novice | 13 | Major | CLOSED | `04-messages-and-cards.md:48`: C11 is in the Explain-only list. `cards\widen-request.json` has Explain and Talk to a person, not Challenge or Teach. |
| G-novice | 14 | Major | CLOSED | `cards\data\your-ok.json:23`: "After 60 idle minutes". The 19:30 time is the VM deallocation, not the SQL pause. |
| G-novice | 15 | Major | CLOSED | "Look at the hub" is absent. `04-messages-and-cards.md:81` lists the ten parts on first use in that section. `README.md:45`: Hub is "Never shown". |
| G-novice | 16 | Major | CLOSED | `04-messages-and-cards.md:97`: "At 360 px, in the reference renderer, C3 and C4 stay readable", with `experience-card-c3-recommendation-phone.png` and `experience-card-c4-your-ok-phone.png`. |
| G-novice | 17 | Minor | CLOSED | `04-messages-and-cards.md:79`: "Details, part 7, opens on request." `01-people.md:7`: the persona table maps each archetype "where one fits". The cited lines no longer put a June event in CET. |

## 2. New defects

N-1 · Major · `05-letters-and-requests.md:84` · "Scope: subscriptions a1f0-0001, a1f0-0002 and a1f0-0003 (orders-prod-1 to 3)." · A savings-plan scope is one resource group, one subscription, one management group or shared, not a list of three subscriptions ([Learn](https://learn.microsoft.com/azure/cost-management-billing/savings-plan/scope-savings-plan): "Subscription scope - Applies benefits to eligible resources in the selected subscription."). A partner would be asked to buy a scope Azure will not accept. · Fix: name one scope type and its id; list today's members only as who benefits now.

N-2 · Major · `cards\hello.json:153` · `"title": "Pause"` · The confirm button inside "Pause messages" is a bare Pause, which the three named pauses forbid. · Fix: title that button "Pause messages".

N-3 · Major · `03-organisation-journeys.md:111` · "whose rollback grant (optional, usable once) makes restoring one tap." · A page-class safety check must stop and let the approver restore in one tap. An optional grant contradicts `02-owner-journeys.md:48`, which states restoring is one tap. · Fix: "A page-class safety check stops and asks the approver, who restores in one tap inside the undo window. Only a one-tap change rolls back by itself."

N-4 · Major · `docs\img\experience-report-card.svg:6` · "One currency (EUR), as invoiced; each amount names its price basis." · The same board shows a list-price Scenario beside bill-rate savings, while `07-reports-and-dashboards.md:64` says savings are amortised, not as invoiced. · Fix: "Savings: EUR, amortised, at the rates on your bills. List-price scenarios are a separate row, not in this total."

N-5 · Major · `04-messages-and-cards.md:60` · "C5 says \"amortised\" beside its saving and \"as invoiced\" beside its payment." · The C5 template and rendering have neither word, so the sentence and the card disagree. · Fix: add both words on C5, or delete the sentence.

## 3. Counts

Closed 23, closed by deletion 0, rejected-ok 0, partly 6, open 1.

No. A stranger still meets a contradiction: the plan card drops the Recommendation, C5's cost-view words are claimed but absent, the partner request names an invalid scope, and Hello confirms with a bare Pause.
