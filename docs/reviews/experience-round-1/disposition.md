# Disposition: decision review of the experience design (round 1)

Four reviewers on different model families challenged the decisions of the experience design before any document was written. Each read the same brief ([brief](brief.md)), the specification of the decisions, the card templates and the wireframes, and wrote one report, kept as received.

| Lens | Model | Raw report | Findings |
|---|---|---|---|
| A. People, attention and trust | gpt-6.1-sol | [raw-a-people](raw-a-people.md) | 12, plus 5 top changes and a list of missing states |
| B. The adversary: security, abuse, privacy | grok-4.7 | [raw-b-adversary](raw-b-adversary.md) | 12, plus 5 top changes and a list of gaps |
| C. FinOps, finance, procurement and agreements | gemini-4-argon | [raw-c-finops](raw-c-finops.md) | 12, plus 5 top changes and a list of gaps |
| D. Platform feasibility and accessibility | claude-sonnet-5 | [raw-d-platform](raw-d-platform.md) | 14, plus 5 top changes and a list of gaps |

**How it was checked.** The reviewers were told the specification was not gospel. Each finding was checked against the templates, the wireframes and the technical design before anything changed. Every Azure claim that would change a decision was re-read on Microsoft Learn: savings plans exist only for subscriptions under an Enterprise Agreement, a Microsoft Customer Agreement or a partner agreement ([permissions](https://learn.microsoft.com/azure/cost-management-billing/savings-plan/permission-buy-savings-plan)); a pay-as-you-go account on the Online Services Agreement does not show commitment purchases, and a billing period closes up to 72 hours after it ends with charges changing until the fifth day ([cost data](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data)); a partner's customer sees reservation usage at zero charge ([partners](https://learn.microsoft.com/azure/cost-management-billing/costs/get-started-partners)); from 1 February 2027 a reservation for a service that savings plans cover is not exchangeable, and refunds are capped at USD 50,000 in 12 months ([exchanges](https://learn.microsoft.com/azure/cost-management-billing/reservations/exchange-and-refund-azure-reservations)); each hour of a savings plan is use-it-or-lose-it ([discount application](https://learn.microsoft.com/azure/cost-management-billing/savings-plan/discount-application)); a spending-commitment shortfall is charged at the end date ([MACC](https://learn.microsoft.com/azure/cost-management-billing/benefits/macc/track-consumption-commitment)); a monthly savings plan payment under a Microsoft Customer Agreement follows the exchange rate ([buy a savings plan](https://learn.microsoft.com/azure/cost-management-billing/savings-plan/buy-savings-plan)). The templates were also run through the official Adaptive Cards libraries after the changes: all 16 parse, validate and expand.

| Verdict | Count |
|---|---|
| Accepted: the decision or an example changed | 46 of the 50 numbered findings |
| Adjusted: the finding was right, the proposed fix was not | 4 (A6, A11, C F1, C F3), and A's top change 2 |
| Not adopted | 0 of the numbered findings; one suggestion in a list of missing items (renaming four screen words) |

Two parts of the findings were already in the technical design and were kept consistent with it: the design already measures savings in effective cost and already says that a partner's customer sees reservation usage at zero charge (C F1, C F3, C F5).

## A. People, attention and trust

| # | Finding | Verdict and change |
|---|---|---|
| Top 1 | The Recommendation card has 19 text blocks and 11 controls; an unresolved risk sits beside a "Choose A" button | **Accepted.** The card shows one change, three decision buttons and four toggles (about seven controls); other options sit inside Details; an unresolved fact becomes a Question first |
| Top 2 | Show the fresh plan first and skip the second message | **Adjusted.** The second message goes: "Review the plan" replaces the card in place with the exact plan, and a second tap gives the OK. A pre-planned one-step path stays off, because B12 shows it drops the look that catches a stale plan |
| Top 3, 1, 2 | Count every push; slow start per person; ask working days once | **Accepted.** One push a week for 30 days after a person's own first contact, then three; the reminder and the desk count; days and hours are asked once |
| Top 4 | Replace manager-chain escalation | **Accepted.** Coverage routing to an appointed delegate or the custodian queue; no message tells a third person that a named person did not answer (also B4) |
| Top 5 | Design trust repair | **Accepted.** A new card, "Our mistake" (C16), and "I did not approve this" on the Done card |
| 3, 4, 5 | The reminder ladder, the fatigue guard and the answer times have no evidence | **Accepted.** Ladder 0, 7, 14 with one reminder in the desk; the guard is a review trigger with a denominator and never a penalty; receipt as fast as the host allows. Every number is marked a testable starting value |
| 6 | Explain, Challenge and Teach on every card is clutter | **Adjusted.** Utility cards (Hello, Read-back, Widen request, Settings, Weekly desk, I could not) carry Explain and Talk to a person; claim-bearing cards keep all three. Challenge and Teach stay separate: one re-examines now, the other keeps a note |
| 7 | Yes is one tap, No needs a form; "waiting costs" frames a loss | **Accepted.** One-tap "Not now" and "Not mine" with an optional reason afterwards; "Keeping things as they are forgoes about €23 a day" |
| 8 | Hello says an OK is only given on a page, but C4 approves in Teams | **Accepted (blocker).** Hello states both paths |
| 9 | The plan code is not proof; the footer sounds like a guarantee | **Accepted.** The code is a reference; the footer adds "Estimates can still be wrong" |
| 10 | "Stop this here" bundles things | **Accepted.** "Pause automatic changes here" is separate from "Fewer suggestions" |
| 11 | The Heads-up card is generic; the desk can evade limits | **Adjusted.** The Heads-up card is for spend spikes, with a money tile; the desk is limited by effort as well as count |
| 12 | The first approval still anchors the second | **Accepted.** Two independent approvers are asked in parallel and see each other's answer only after both decide |
| Missing | Joiner, leaver, contractor, shared mailbox, absent owner, first failure, team lead | **Accepted.** Added to journeys J1 to J8 |
| Missing | Rename "Your OK", "Challenge", "Teach", "Not mine" | **Not adopted** as a rename; native-speaker tests and disclosed wording comparisons decide (X13) |

## B. The adversary

| # | Finding | Verdict and change |
|---|---|---|
| 1 | An `Action.Submit` fallback can approve without the tapper's token (blocker) | **Accepted.** The fallback is an `Action.OpenUrl` to the page; `Action.Submit` is rejected by the lint |
| 2 | The plan code is public and not echoed (blocker) | **Accepted.** Echoed on every tap and submit; single use; the tapper must be the designated approver or a named delegate; the cap is shown on the card |
| 3 | An owner can teach "everywhere" in one tap (blocker) | **Accepted.** A note's scope never exceeds what its author owns; a wider scope is a request to the person who owns it, with the affected count |
| 4 | Escalation to a manager profiles non-response (blocker) | **Accepted** (see A top 4); counts over fewer than five people are rolled up |
| 5 | Bound text can carry markdown links | **Accepted.** The send step strips URLs and escapes markdown; the lint checks sample data |
| 6 | A compromised bot could approve without a tap; the cap has no number | **Accepted.** A starting cap of five a day, shown on the card, with an alarm for an approval that arrives without a tap (asked of the technical design) |
| 7 | R3 checks roles, not people | **Accepted.** Different directory objects; requester excluded |
| 8, 9, 10 | Subject lines carry money; voice and transcripts; review surfaces | **Accepted.** No figures in subjects; audio plays on the page with a disclosure and no download; a transcript is read for one purpose and not stored; contributor text is escaped, fork pull requests get the comment |
| 11 | The sender name can be copied | **Accepted.** Change cards are accepted only through the stored one-to-one conversation with this app; only directory members receive cards |
| 12 | A one-step fast path drops the look that catches a stale plan | **Accepted.** Stays off; wording comparisons extend to R1 |
| Missing | A "this was not me" action; guests; retention; a works-council gate | **Accepted** |

## C. FinOps, finance, procurement and agreements

| # | Finding | Verdict and change |
|---|---|---|
| F1 | Variants D and E misstate commitment rules (blocker) | **Adjusted.** The pay-as-you-go row is right for the Online Services Agreement; an account created on the web under a Microsoft Customer Agreement is variant A or B. Added: a partner's customer may buy when the partner allows it; reservation usage shows no charge in a partner customer's view |
| F2 | Two people approve a €205,860 purchase at list prices (blocker) | **Accepted.** The example is now variant A with a stored price check; under variants B to D the approval is of a request and the owner's or partner's quote settles the number. "Quote" on screen means only an offer from a person; the system's own computation is a "price check" |
| F3 | The price basis omits actual versus amortised and estimates | **Accepted.** Figure notes: savings amortised, invoices as invoiced, open periods marked estimate. Not adopted as chips: offer-specific modifiers (Hybrid Benefit, Dev/Test) stay in the technical design's price-basis logic |
| F4 | The commitment page omits payment, scope, renewal, exchange rules | **Accepted** (verified) |
| F5 | A saving ignores commitment vacancy | **Accepted.** Asked of the technical design's Verifier |
| F6 | A spending-commitment shortfall can cancel a saving | **Accepted** (verified): pace shown; reductions made while behind are labelled |
| F7, F8 | One letter for every role; finance lives in spreadsheets | **Accepted.** The Monday letter goes to the FinOps lead and platform owner; finance and executives get a monthly letter after the period closes, with a CSV |
| F9 | "Explained spend" ignores allocation | **Accepted.** Split into allocated, shared by rule, unallocated |
| F10, F11 | Variant figures are not coherent; chip strings differ | **Accepted** |
| F12 | Unit economics missing | **Accepted** as an optional volume denominator |

## D. Platform feasibility and accessibility

| # | Finding | Verdict and change |
|---|---|---|
| 1 | Nothing caps the total buttons on a card (blocker) | **Accepted.** The lint caps visible (8) and hidden (4) buttons per card and options (2 beyond the main one) |
| 2 | What `Action.OpenUrl` opens on each client is unverified (blocker) | **Accepted.** A device test is a release gate; the e-mail link is the verified fallback |
| 3 | A ShowCard action sends its parent card's inputs | **Accepted.** Root-level inputs only where the manifest says so |
| 4, 12 | Flat headings; Table on a phone | **Accepted.** Tooltips on toggles; testing with real assistive technology and a client matrix |
| 5 | `fallbackText` and `Activity.text` are different | **Accepted.** Both are set |
| 6 | Letters must stay image-free | **Accepted** |
| 7, 8 | Step-up is custom code; cold starts | **Accepted.** No always-ready instance in the starting configuration; added if the first load exceeds 5 seconds at the 95th percentile |
| 9 | The report table's retention is too short | **Accepted.** At least 13 months |
| 10, 11, 13, 14 | .NET templating; two feedback channels; avatar character; check-run buttons | **Accepted** |
| Missing | Channel reach, client tests, a dead approval page, partners and guests | **Accepted** |

## What the review did not touch

The vocabulary layer, the ten principles, Workbooks as the report surface for the roles that live in Azure, the system-browser decision's direction, WCAG 2.2 AA with EN 301 549, and the FinOps Framework persona mapping were all confirmed or left as proposed.
