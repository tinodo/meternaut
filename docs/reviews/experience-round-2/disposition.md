# Disposition: cold readers of the experience design (round 2)

Eight readers on different model families read the finished experience folder, each with a different lens and none of them told what had been decided or why. Each wrote one report, kept as received ([brief](brief-cold-reader.md)).

| Lens | Model | Read | Raw report | Findings (blocker, major, minor) |
|---|---|---|---|---|
| A. The resource owner | claude-sonnet-5.5 | README, people, owner journeys, cards | [raw-a-owner](raw-a-owner.md) | 22 (1, 14, 7) |
| B. FinOps and finance | gpt-6-sol | organisation journeys, reports, decisions | [raw-b-finops](raw-b-finops.md) | 13 (5, 7, 1) |
| C. Teams cards | gpt-5.6-sol | messages and cards, the templates | [raw-c-teams](raw-c-teams.md) | 10 (2, 7, 1) |
| D. Letters and pages | grok-4.6 | letters, web pages, the wireframes | [raw-d-web](raw-d-web.md) | 12 (1, 6, 5) |
| E. Attention, trust and inclusion | gemini-4-argon | attention and trust, access and language | [raw-e-trust](raw-e-trust.md) | 20 (4, 9, 7) |
| F. Platform, reviewers, voice, testing | gpt-6.1-terra | reviewers, voice, testing, register, asks | [raw-f-platform](raw-f-platform.md) | 27 (7, 18, 2) |
| G. A novice at the front door | claude-haiku-5.5 | README, people, cards | [raw-g-novice](raw-g-novice.md) | 17 (3, 13, 1) |
| H. Cross-document consistency | gpt-5.3-codex | all documents and templates | [raw-h-consistency](raw-h-consistency.md) | 5 (1, 3, 1) |

That is 126 findings: 24 blockers, 77 majors and 25 minors.

**How it was checked.** A reviewer is not gospel. Claims about Microsoft products were read on Microsoft Learn before anything changed: read receipts reach an agent in a one-to-one chat, only with a permission and only while nobody has switched them off, so the claim that Teams has none was wrong ([Learn](https://learn.microsoft.com/microsoftteams/platform/bots/build-conversational-capability#receive-a-read-receipt)); a savings plan under a Microsoft Customer Agreement is priced in US dollars and billed in the local currency at the monthly rate ([Learn](https://learn.microsoft.com/azure/cost-management-billing/savings-plan/savings-plan-overview)); a missed spending commitment or milestone is charged as prepayment credit, not as money lost ([Learn](https://learn.microsoft.com/azure/cost-management-billing/benefits/macc/track-consumption-commitment)); a reservation renews automatically unless auto-renew is switched off, and its renewal price appears only 30 days before expiry ([Learn](https://learn.microsoft.com/azure/cost-management-billing/reservations/reservation-renew)); Azure Monitor dashboards with Grafana became generally available in November 2025, although Learn's overview page still says Preview ([Grafana](https://grafana.com/blog/azure-monitor-offers-grafana-dashboards-natively-for-immediate-real-time-operational-monitoring-now-ga/)); Teams says to retry 429, 412, 502 and 504 and allows 7 messages a second to one conversation ([Learn](https://learn.microsoft.com/microsoftteams/platform/bots/how-to/rate-limit)). Learn's two pages on channels differ: one says agent apps are supported in shared and private channels, the other that agents cannot post cards in private ones; the register states both and the design uses neither. Where a claim could not be confirmed it was removed (two cases: a "generally available" label that Learn does not give, and a `Retry-After` header that the rate-limit page does not mention) or hedged (Workbooks accessibility).

**Decisions the findings had in common.** One rule for the plan code: a reference, with one decision per approver. The one-tap cap sends further changes to the page and alerts nobody; only an approval without the authenticated event of its route raises an alarm. "Talk to a person" is the last button of every card. The words that refuse are "No, leave it as it is", "Not mine", "Cancel" and "Decline". Three pauses have three names. A commitment is shown in the currency it is bought in. A renewal, a shortfall and an invoice are described as Azure documents them. The plan on a card is one block per resource, with renderings at 360 px. Every action that takes no input says so, and the manifest is the action contract. The decisions are in [14](../../experience/14-decisions.md) (38 to 41 are new).

## The closure round

Four checkers on other model families read all 126 findings again against the fixed text ([1](closure-1.md) gpt-6-sol, [2](closure-2.md) gpt-6.1-terra, [3](closure-3.md) claude-sonnet-5.5, [4](closure-4.md) grok-4.7). They closed 89 findings, closed 2 more because the sentence was deleted, agreed that 4 were right to reject, closed 30 only in part and left 1 open. They also filed 25 new defects, 20 of them distinct: most were fixes that had not reached every place (the same request id on unrelated examples, a chip with a bracket, a plan block that named a range of four machines, a cap without its price basis, a bare "Pause", a quote of a refused label), and two were real design gaps (a button inside a ShowCard also sends the inputs of its parent card; a card's fallback led to a page that did not match it). Each was checked against the files and fixed in the same way: facts first, then one pass per document, then the templates, the pictures and the lint.

| Finding | What was done, and why |
|---|---|
| 2 C, a versioned activity envelope and an SDK example for each card | **Not applied.** The experience design says what a message carries; the envelope and the calls belong to the technical design and the build ([15](../../experience/15-asks-of-the-technical-design.md)) |
| 2 C, legal states for every verb | **Applied as one rule.** The manifest has a `contract` for every verb: who may tap, what a repeat does, when a verb is refused and what a tap returns. The states of a plan belong to the Approval service |
| 2 A, a Result card for a scope without costs | **Applied differently.** No Result follows where costs cannot be read, and Done says "I cannot measure this here"; a card without a measurement would have nothing to compare |
| 2 C, the Settings and Read-back inputs in separate ShowCards | **Applied differently.** On those two cards Explain is one plain tap with no input, and the manifest lists the scope that "Not quite" carries |
| 4 G, the plan card cannot reach the Recommendation | **Applied.** C4 has a third button, "Open the Recommendation", that brings the Recommendation back and approves nothing |
| The four findings that were rejected in round 2 and checked again | **Kept.** The checkers agreed that a reason is never demanded, that the Workbooks claim stays hedged, that the Monday letter is an agenda for two roles and that "One tap" is defined |

Two final checkers on other model families ([1](final-1.md) gemini-4-argon, [2](final-2.md) gpt-6.1-sol) then checked every part-closed or new item again, 56 in all: 49 were fixed and 7 fixed in a different but sound way, and none was left. They read the fixes for what they broke and found one more defect: management-group scope covers only the subscriptions that are in the group and on the purchaser's billing profile, so the savings-plan examples now say so. Both ran the lints and the renderer against the templates, which passed.

## Not applied, or applied differently

Every other finding was applied as written or with an equivalent fix.

| Finding | What was done instead, and why |
|---|---|
| D, one primary ask in the Monday letter | **Not applied.** The letter is a weekly agenda for two roles; it keeps at most three asks, each a link to one page |
| E, `isRequired` on the optional Challenge, "No, it does not" and "No, not expected" boxes | **Not applied.** A reason is never demanded; only a required input carries an error message |
| E, route a parked item to cover only after "Not mine" | **Applied differently.** Cover routing stays (it is in the technical design); the promise changed: the owner is told that cover is asked to confirm who owns the item, and no message says that anyone did not answer |
| E, one decision on Hello | **In part.** Hello asks one decision; its two settings controls (Pause messages, hours and language) are offered once and nothing depends on them |
| C, move the Settings form inside a ShowCard | **Applied differently.** Every action that takes no input says `none`, and each verb lists the inputs it accepts. On Read-back and Settings, which have inputs on their face, Explain is one plain tap, so the face form travels only with Save, Yes, that is right and Not quite |
| C, fall back to `Action.Submit` | **Not adopted.** An approval must never travel the older path. A client below schema 1.5 gets the page link in `fallbackText` |
| C, typed money objects in every field | **In part.** The rule is stated as it holds (a saving carries two chips; other money carries its basis in its sentence), and three lines were fixed; prose cannot be linted |
| A, a range on every figure | **In part.** A range is required where a person may act on a saving; lists and report tiles show "about" and the saving word |
| A, rename "One tap" | **Not renamed.** It is defined: one OK in the card; opening the plan approves nothing |
| E, Workbooks have an accessibility statement | **Hedged.** Learn lists Azure's conformance reports, not Workbooks specifically, and the document says so |

## Corrections to our own work

- The fix sheet listed the wrong levels of the kill switch; two writers caught it against the technical design (global, per kind of change, per estate) and the documents follow the design.
- Fixing the first-run time showed that the sample Done card said the undo window "closes during the weekend" when it closed on Friday at 17:00. The window is now 24 hours, to Friday 19:30, which is after the working day, so the reminder at 09:00 is real.
- The card lint missed an unlabelled input inside a top-level ShowCard and a top-level `Action.Http`; it now walks every action, accepts any script in a button title, and checks the manifest's action contract.
- The closure round showed that the lint still dropped the parent inputs of an action inside a ShowCard, that the sample plan named "vm-qa-web-01 to 04" (a range, not four resources), that unrelated examples shared one request id, and that C5 and the text claimed words ("amortised", "as invoiced") that the card did not carry. The lint now counts parent inputs, requires the AI line in every fallback text and refuses a request id shared by unrelated examples; the plan names each resource; C5 carries its words.
