# Cold-reader review, novice lens: experience round 2

**Scope.** Read: README (all); 01-people.md lines 1–41 (a range error also displayed 42–119; unused); 04-messages-and-cards.md lines 1–100; C3/C4/C5 PNGs; the SVG (SVG:n = line n). Card templates: not read.

## 1. Verdict
Understand: mostly. Trust or build: not yet, because the worked approval card contradicts itself on ownership, time and scope.

## 2. Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | C4 PNG footer | 4, 8 | "you own the resources this plan changes" | You own 3 of 14; the plan changes 5. | Name the five and owners; "reviewed this plan", not "chose this option". |
| 2 | Blocker | C4 PNG headline, "When" | 4 | "then every weekday evening" | Headline says 19:30; "When" says 22:00. | "Thursday 19:30 CET, then 19:30 each weekday." |
| 3 | Blocker | C4 PNG table | 5, 8 | "Off 19:30–07:30 and weekends" | Stopped VMs bill; deallocated do not (check 1). | "Stopped (deallocated)"; disks still bill. |
| 4 | Major | C4 PNG, "What could go wrong" | 8 | "I switch it back on and tell you" | An action outside the plan table. | A plan row with its own OK, or "I ask first." |
| 5 | Major | 04:93 | 8 | "in place of the Recommendation" | Evidence and alternatives vanish (README:18). | Keep the Recommendation above the plan. |
| 6 | Major | SVG:72 | 4 | "Saves about €940 a month" | Option C saves more than "About €690"; no reason for A. | "I prefer A: C saves more but needs two days of engineering." |
| 7 | Major | C3 PNG; SVG:113 | 4, 8 | "What I checked: You told me a job runs" | Claims a check; it is the owner's answer. | "What you told me"; add "Strongest doubt". |
| 8 | Major | 04:60; README:19; 04:62 | 4 | "Two chips sit beside every money figure" | Payments and "€23 a day" lack chips; C5 lacks "amortised" (04:62). | Basis on every money figure; range and word on savings. |
| 9 | Major | 01:13; 01:17 | 4 | "a purchase's finance-side approval" | Nadia and Lars both claim the finance approval. | Name one finance approver. |
| 10 | Major | 01:11; README:17 | 8 | "one message of up to five items" | Breaks one decision per message. | Information digest; each decision its own card. |
| 11 | Major | 04:87; 04:33; 04:50 | 2, 4 | "'Not now' and 'Not mine' close the message" | "Not now" implies later; C4's "Cancel" is unspecified; help is hidden on C3. | One refusal word per card, with what follows; true help placements. |
| 12 | Major | 04:15; 04:79; README:54 | 4 | "in the conversation" vs "in the card" | Explain and approval each have two homes. | Explain in the card; approval only on the approval page. |
| 13 | Major | 01:30; 04:48 | 4 | "Explain, Challenge and Teach come with every claim" | C11 is a request with Explain only. | Scope the rule to claim and decision cards. |
| 14 | Major | C4 PNG table | 5 | "Pauses when idle" | Auto-pause minimum 15 min, default 60 (check 3). | State the delay, or drop the 19:30 promise. |
| 15 | Major | 04:9; 04:30 | 2 | "Look at the hub"; "ten-part Recommendation" | Undefined; card shows eight parts, text says ten (SVG:131). | Gloss on first use; list the ten once. |
| 16 | Major | SVG:1 | 8 | viewBox="0 0 1260 1110" | Only desktop renderings exist; phone layout untested. | Add a 360 px render of C3 and C4. |
| 17 | Minor | 04:83; 04:64; 01:7; 01:40 | 4 | "the eighth, Details" | Details is part 7 (04:80); CET wrong in June; "maps each" yet two rows say None (01:15, 01:21). | Renumber; CEST; "or a role". |

## 3. Sentences I would delete
- 04:46 "None of the four stops a person from trusting a card too much": class 1; an unraised objection.
- README:7 "The card above is the centre of the design.": padding.
- 04:9 "Look at the hub:": undefined.
- 04:58 "Hello's introduction says it instead.": "Hello" has no card.
- 04:76 "and without guilt": a reply to a reviewer.
- 01:30 "(they come from the ten principles in the README)": not in the README.
- 01:34 "decide fast": pressure; say "decide on what is proposed".

## 4. Fact checks (Learn, read 2026-11-02)
1. https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing: stopped VMs bill; deallocated do not. **Supports Blocker 3.**
2. https://learn.microsoft.com/en-us/azure/cost-management-billing/savings-plan/savings-plan-overview: "can't be canceled or refunded." **Supported;** "exchanged" is not stated.
3. https://learn.microsoft.com/en-us/azure/azure-sql/database/serverless-tier-overview: auto-pause minimum 15 minutes, default 60. **Partly supported:** idle-based, not 19:30.
4. https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data: charges "can change until the fifth day". **Supported;** open-month tiered estimates use the highest tier.
5. https://learn.microsoft.com/en-us/microsoftteams/platform/agents-in-teams/integrate-ai/ai-content-labels: needs `AddAIGenerated()` per message. **"Generally available" not stated;** unverified.

## 5. Words I did not understand
hub; ten-part Recommendation; "send step that no model can steer"; Runner, Detective, Skeptic, Agenda; receipts; claim; recipes; desk; directory; Read-back; "praise without proof"; Hello.

## 6. Questions left unanswered
1. What is "the system", what does it change, and who runs the agents?
2. Which five resources does C4 change, and who owns each?
3. How is "Six people use it" collected, and who sees it?
4. After "Not now" or "Not mine", does the same Recommendation return?
5. If nobody taps C4, what happens? C4 never says that nothing is approved.

## 7. What I would build first
The C4 one-tap plan card and its binding: plan rows with billed state and owner, plan code, person, time, undo.
