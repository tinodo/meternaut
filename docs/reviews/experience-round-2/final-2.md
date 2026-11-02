# Final check 2: trust, letters, pages, FinOps and novice

Read on 2026-11-02. I read the closure decisions first. This checks every PARTLY, OPEN and new-defect row in closure-3 and closure-4. Paths without `docs\` start in `docs\experience\`. Line numbers count newline characters.

## Closure checks

| Closure report and row | Status | Evidence: current file, line and quoted text |
|---|---|---|
| closure-3, e-trust 3 | FIXED | `08-attention-and-trust.md:81`: “tells the owner once, first, by notice e-mail”, including when “a real deadline is close”; “Cover gets a Question (C2)”. `05-letters-and-requests.md:35` supplies the parked-item notice. Both channels are specified. |
| closure-3, e-trust 8 | FIXED | `04-messages-and-cards.md:113`: “One decision: Yes, I look after these or Not mine. Offered once, nothing waits on them: Pause messages · My hours and language”. `11-access-language-inclusion.md:108` also says “nothing waits on it”. |
| closure-3, e-trust 16 | FIXED | `08-attention-and-trust.md:125`: “Fewer like this, on the card and the pages”. `06-web-pages.md:90` and `12-testing-the-experience.md:77` use “Fewer like this”. The competing name is absent from the experience folder. |
| closure-3, N-1 | FIXED | `08-attention-and-trust.md:84` identifies “E1's day-7 Reminder (C9)”. `05-letters-and-requests.md:35` gives the day-14 words: “I have parked it and asked your cover to confirm who owns it. I have not said that you did not answer.” |
| closure-3, N-2 | FIXED | `cards\hello.json:153`: `"title": "Pause messages"`. This is the submit button inside the settings control, not just its outer title. |
| closure-3, N-3 | FIXED | `docs\img\experience-approval-page.svg:101`: “Written by an AI. Figures are computed by tools, not guessed by the AI. Estimates can still be wrong.” The whole footer is present. |
| closure-3, N-4 | FIXED | `cards\hello.json:226,300`: `"$data": "${timeZones}"` and `"$data": "${languages}"`; `cards\settings.json:83,139` bind the same lists. `11-access-language-inclusion.md:108` restricts languages to those “whose catalogs are live”. The templates no longer impose the sample lists. |
| closure-4, B-finops 6 | FIXED | `docs\img\experience-approval-page.svg:36–40`: “Management group Order platform (mg-order-platform)”; “Subscriptions a1f0-0001, a1f0-0002 and a1f0-0003”; “Subscription a1f0-0001 … billing profile BP-ORD-01 (Contoso Orders)”. The missing identifiers are supplied. The separate eligibility overclaim is New defect 1 below. |
| closure-4, B-finops 7 | FIXED | `docs\img\experience-approval-page.svg:59–62`: “saves about €700 a month”, “about USD 4,500 a month of the commitment goes unused”, then “From 1 July it saves about €4,300 a month”. Waiting “past then” forgoes €140 a day. `03-organisation-journeys.md:51` matches and labels these Expected, at agreement rates. |
| closure-4, G-novice 1 | FIXED DIFFERENTLY | `cards\data\your-ok.json:14,20,26` names “vm-qa-web-01”, “vm-qa-web-02” and “sql-qa-orders”. At line 46: “you confirmed on Monday that you look after rg-webshop-qa … and this plan changes 3 of them.” Sound: F1 specifies three resources, not the five in the proposed replacement; F2 uses confirmed responsibility rather than choosing an option. |
| closure-4, G-novice 5 | FIXED | `cards\your-ok.json:209–210`: `"title": "Open the Recommendation"`, `"verb": "reopen"`. `cards\manifest.json:218–222` returns C3. `04-messages-and-cards.md:83` says it puts the Recommendation “back in the thread and approves nothing”. The desktop and phone renderings include the button. |
| closure-4, G-novice 7 | FIXED DIFFERENTLY | `cards\data\recommendation.json:16`: “11 weeks of access records … Strongest doubt: a job on that night. You told me one runs, so the schedule leaves it on.” Sound: the retained “What I checked” paragraph distinguishes records from the owner's answer and states the doubt. The Recommendation SVG and rendering agree. |
| closure-4, G-novice 8 | FIXED | `cards\data\recommendation.json:14` and `cards\data\reminder.json:13`: “forgoes about €23 a day, at the rates on your bill.” `cards\data\ok-on-page.json:14` says “amortised”; line 11 says “€17,155 a month as invoiced”. Both appear in the C5 rendering. |
| closure-4, G-novice 12 | FIXED DIFFERENTLY | `README.md:18`: “Details in the message, Explain answered in the thread”. `04-messages-and-cards.md:31`: “asked in the card, answered in the thread”. Sound: the index is shorter than the proposed replacement but no longer assigns Explain a different home. |
| closure-4, N-1 | FIXED | `05-letters-and-requests.md:84`: “Scope: management group "Order platform" (mg-order-platform). Today the plan benefits subscriptions …”. It identifies one scope; the subscriptions are current beneficiaries, not a list-valued scope. The future-members qualification is New defect 1. |
| closure-4, N-2 | FIXED | `cards\hello.json:153`: `"title": "Pause messages"`. Same correction as closure-3 N-2. |
| closure-4, N-3 | FIXED | `03-organisation-journeys.md:111`: “She restores the old size in one tap, inside the undo window”; “only a one-tap change rolls back by itself”; the grant is “usable once, held for a reversible change”. `cards\data\our-mistake.json:9` says “You said yes at 10:48.” |
| closure-4, N-4 | FIXED | `docs\img\experience-report-card.svg:6`: “Savings are amortised and name their price basis; a list-price scenario is its own row, never in a total.” The savings rows state their separate bases. The header does not call savings “as invoiced”. |
| closure-4, N-5 | FIXED | `cards\data\ok-on-page.json:11,14`: “€17,155 a month as invoiced” and “Range €3,700 to €4,900, amortised”. The C5 template expands these fields and the PNG displays both words. The claim in `04-messages-and-cards.md:54` is supported. |

## New defects

1. **Major · `docs\img\experience-approval-page.svg:37` · “Subscriptions a1f0-0001, a1f0-0002 and a1f0-0003 today, and any later member” ·** Management-group membership alone does not make a subscription eligible. [Microsoft Learn, Savings plan scopes](https://learn.microsoft.com/azure/cost-management-billing/savings-plan/scope-savings-plan), read on 2026-11-02, requires both membership and “The same enrollment or billing profile as the subscription used to purchase the benefit.” The page names BP-ORD-01 but never makes that eligibility condition explicit. The same unconditional promise appears in `03-organisation-journeys.md:49` and `05-letters-and-requests.md:84`. A later member on another billing profile would not receive the promised benefit. **Fix:** qualify current and future beneficiaries by the purchaser's billing boundary. For this MCA example, say that they must also belong to BP-ORD-01. Carry that condition into all three places. This is a factual qualification to F19, not a different scope choice.

## Consistency and records

E1's three plan blocks agree with the confirmed-ownership footer. Both VM blocks name the Monday 19:30 to Tuesday 07:30 exception. SQL has the same exception. The €690 figure, €620 to €760 range, €23 daily amount, Thursday 19:30 CET start, Friday 19:30 CET undo deadline and 7F3K-92QD code agree across the checked material.

E4's arithmetic agrees: USD 25 × 8,760 = USD 219,000; at 0.94 that is €205,860, or €17,155 over twelve payments. Its saving range and CEST times agree. The access-variants picture matches the table's figures, ranges and four chip labels. The approval, access, report and Recommendation SVGs contain their assigned corrections.

The raw reports support 126 findings: 24 blockers, 77 majors and 25 minors. The four closure tables support 89 CLOSED, 2 CLOSED-BY-DELETION, 4 REJECTED-OK, 30 PARTLY and 1 OPEN. Their 25 new-defect entries contain five duplicates, leaving 20 distinct defects. Those counts in `docs\reviews\README.md`, the disposition and the changelog agree. The disposition's C4, C5, input-binding and fallback correction claims match the inspected files. The release text correctly says that nothing is built and the Teams client matrix has not been run.

## Required checks

- `python tools\check-docs.py --strict`: PASS before this report; 74 documents, zero errors and zero warnings. Repeated after saving: FAIL; 75 documents, one error, zero warnings: `docs/reviews/experience-round-2/final-2.md:1: ERROR: orphan: not reachable from README.md`. The new report needs an index link. I did not edit the index because only this report may change.
- `python tools\cardlint.py --self-test`: PASS.
- `python tools\cardlint.py`: PASS; zero problems.
- From `tools\render-cards`, `node validate-cards.cjs`: PASS; all 17 cards parse, validate and expand.

The Node command used an in-memory preload that suppressed only its 35 generated output writes, preserving the read-only review. An earlier review wrapper failed on PowerShell quoting before loading the validator; the corrected run passed. No dependencies were installed.

Counts: 16 FIXED, 3 FIXED DIFFERENTLY (sound), 0 NOT FIXED; 1 new Major, 0 Blockers. Release: no; add the billing-boundary qualification and index this review.
