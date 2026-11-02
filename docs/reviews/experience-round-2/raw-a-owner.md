# Cold read A: the resource owner's experience

Key: README, 01, 02 = the assigned files; `c\` = `cards\`; `d\` = `cards\data\`; 03, 04, 06, 08 = sibling documents opened only to check a fact; SVGs are in `docs\img`.

## 1. Verdict

Mostly: a stranger can follow the eight journeys, find each card's words in the templates and trust the one-decision, honest-number idea. But the documents break their own promises (a reminder that tells no one, an undo reminder that needs read receipts Teams lacks, figures without ranges), leave ownership and Pause undefined, and never say what the product is.

## 2. Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | 02:104–105; d\reminder.json:13 | 4, 8 | "I will not tell anyone else that you did not answer." | Day 14 sends the Case to her delegate or the custodian queue ("Ownership or cover needs confirming"), which discloses her silence. | "I will park it, tell you once and ask your cover to confirm ownership. I will not say you did not answer." |
| 2 | Major | d\done.json:9; 02:154 | 8, 4 | "I will remind you on Friday at 09:00 if you have not looked." | Teams gives a bot no read receipt (04:264), so this and "never lapses unseen" cannot be kept. Thursday 22:00 to Friday 17:00 is 19 h, not 24 h, and not "the weekend". | "I will remind you once on Friday at 09:00, whether or not you looked." Make the window 24 h. |
| 3 | Major | 02:23, 31, 213; d\recommendation.json:38; d\your-ok.json:36 | 4, 8 | "The first Recommendation says the owner is a guess" | Nothing stops a guessed owner from OK-ing a change to 14 resources; the directory lists her for 3. C3 cites that, C4 says "you own the resources"; J8 says only confirmation counts. | Until she taps "Yes, I look after these", send only "Is this yours?". Footers: "you confirmed on [date]…". |
| 4 | Major | 01:80; 02:48; c\recommendation.json | 4, 8 | "On every Recommendation … One line." | The access line has no field in C3, no part in the wireframe and no sample text. | Add an `accessLine` block and sample to C3, or drop the claim. |
| 5 | Major | README:19; 01:72; card SVG:64,72,107; access SVG:13; d\weekly-desk.json:13; d\result.json:9; d\heads-up.json:9; d\told-afterwards.json:8 | 4, 8 | "Every figure has a range" | Options B and C, desk items and the five access tiles show points, against the callout "never a point"; 01:72 says the access picture keeps "the range". Result and Heads-up put a method or a condition in the range slot. C8's cap omits "expected saving". | Add ranges or state the exceptions; rename the slot where it is no range; copy C17's cap wording. |
| 6 | Major | 02:48, 160 | 8 | "Scenario only, in the result too" | A Result is "measured on the closed bill"; variant C cannot read one, and nothing says what the owner receives. | For variant C send "I cannot measure this here", no saving word; add the sample. |
| 7 | Major | access SVG:109; 01:68 | 4 | "buys it after two people approve." | The system cannot buy in E, yet two people approve "it"; columns B to D approve the request, as the design requires. | "Two people approve the request; someone with Owner or Reservation Purchaser then decides whether to buy." |
| 8 | Major | README:43; 01:24; 02:109, 126; c\hello.json:106 | 4 | "Pause stops the system's changes." | "Pause" is the kill switch (stops changes), a person's holiday mode (stops asks and cover; silent on changes) and "Pause changes here" (stops permissions, not suggestions). | Name them apart (Mute, Pause changes here, Pause everything); say what Mute does to standing permissions. |
| 9 | Major | README:3 | 7 | "The technical design says what the system does." | No sentence says what Cost in Action is, who it serves or what it may change. | Add two sentences: what it is, who it serves, and that it changes Azure only after a bound approval. |
| 10 | Major | README:19, 38 | 2 | "Scenario, Expected or Verified" | The three words that govern every figure are undefined in README, 01 and 02 (04:61 defines them). | Add: Scenario = no rate or bill line behind it; Expected = a bill line confirms the meter; Verified = measured after the change. |
| 11 | Major | d\your-ok.json:16, 22, 25 | 8 | "Off 19:30–07:30 and weekends; on the last Tuesday" | The exact plan a tap binds to is ambiguous ("on" as state or preposition); "Pauses when idle; on the last Tuesday" is unreadable; "I switch it back on" is no plan row. | "Stays on during the last Tuesday of the month"; add a row for the switch-back rule. |
| 12 | Major | 02:49, 156 | 3, 8 | "A person samples approvals afterwards, in confidence; never an accusation" | Who, how often, with what record? A cap hit "tells the platform team" about one named person; 02:192 promises "No league tables of people". | Name the role and cadence, or delete; report cap hits as counts. |
| 13 | Major | README:96 | 6 | "Three checks run before every commit and release." | I found no hook or workflow (no .github, no active .git\hooks): automation that may not exist. | "Three tools check the work; run them before each commit", or add the hook. |
| 14 | Major | c\hello.json; 02:16, 184, 205 | 4, 8 | "reads what is kept and who sees it" | Hello has no such text (only Explain); J7's "Every card has a line 'Why you are getting this'" is false for C1; no language field. | Add "What I keep and who sees it" and a language field to Hello; fix J7 and J8. |
| 15 | Major | 02:51, 109, 112, 139, 151; README:18, 36, 39, 44 | 2, 4 | "emergency lane", "coverage routing", "the notebook page" | Used before any definition ("regret" at 02:139, defined 02:170; "claim"; "catch"). "Price checked" and "Price check" differ by a letter. README:44 says Atlas is "Never shown"; reviewers see it (01:15). | Define at first use or link 06/08; rename "Price checked" to "Price confirmed". |
| 16 | Minor | 02:126, 139 | 8 | "Undo reverses the last change only" | Whether Undo pauses the permission is unsaid (03:88 hints it); the next run may redo what she undid. | "Undo also pauses that permission for those resources until a person lifts it." |
| 17 | Minor | README:42; 01:24; 02:39 | 4 | "One tap" | E1 takes two taps (Review the plan, then OK), so "needs more than one tap in Teams" describes every change. | Call it "one OK in the card"; reword 01:24. |
| 18 | Minor | 02:46 | 8 | "Not now" | It closes the message (04:87) but reads as a deferral; there is no plain "No", and "Not mine" re-routes the case (02:189) and skews the accuracy measure (02:27). | Label it "No, leave it as it is". |
| 19 | Minor | c\heads-up.json:255 (11 templates); c\weekly-desk.json:94 | 8 | "For example: the job on the last Tuesday is real" | The Challenge and Teach placeholders are E1 text in 11 templates; desk items share one "Open" label, no tooltip. | Bind placeholders to data; title the button "Open: ${title}". |
| 20 | Minor | notes SVG:60–61, 73–74 | 4, 8 | "Tags are hints, so I will ask before treating one as a rule." | The "legal" Note is a rule and not a rule. No journey sets a Do-not-touch mark; 02:151 omits it; it has no expiry, unlike a Note. | "I will not propose changes to resources tagged legal"; add the mark to J3 and J5. |
| 21 | Minor | 02:112 | 1 | "Coverage routing replaces escalation." | Answers an earlier draft; "escalation" is never introduced. | Delete. |
| 22 | Minor | README:17; 01:38; 02:53; d\weekly-desk.json:7 | 4 | "One decision, one person, one minute" | The target elsewhere is two minutes (01:38, 02:53), and the sample desk of three items takes "about 10 minutes". | Say "about two minutes" everywhere. |

## 3. Sentences I would delete

1. 02:112 "Coverage routing replaces escalation."
2. 02:124 "Before her first OK of any kind, the plan (C4) says how to undo and until when."
3. 02:130 "Follow the loop: a permission runs and tells, and only people widen it again."
4. 02:184 "Ending or deleting a Lesson never resumes a paused permission."
5. 02:53 "The approval rate is never a target." (also 01:38)
6. 02:126 "(her first)"
7. 01:72 "What the system cannot see changes the words and the buttons, never the standard." (repeats README:24)
8. README:11 ", not a dashboard,"
9. 02:49 "A person samples approvals afterwards, in confidence; never an accusation."

## 4. Fact checks

- **Savings plans cannot be cancelled** (d\ok-on-page.json:9) ✔ "you can't cancel, exchange, or refund a savings plan". <https://learn.microsoft.com/azure/cost-management-billing/savings-plan/manage-savings-plan>
- **No savings plan on pay-as-you-go** (01:68, access SVG) ✔ discounts apply only under EA, MCA or MPA. <https://learn.microsoft.com/azure/cost-management-billing/savings-plan/permission-buy-savings-plan>
- **CSP costs at retail rates, reservation usage shows no charge** (01:67) ✔; missing precondition: the partner's cost-visibility policy is off by default, so without it the scope is variant C. <https://learn.microsoft.com/azure/cost-management-billing/costs/get-started-partners>
- **Web sign-up creates an MCA account, MS-AZR-0017G** (01:87) partly. Offer IDs and the account update are right (<https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data>, <https://learn.microsoft.com/azure/cost-management-billing/understand/mosp-new-customer-experience>); "in some regions a web sign-up creates" is on neither page: unsupported.
- **"Teams adds its own AI-generated label"** (card SVG:94) ✘ imprecise: Teams shows the label only when the app marks the message (`AddAIGenerated`). Fix: "The app marks the message as AI-generated; Teams then shows its own label." <https://learn.microsoft.com/microsoftteams/platform/bots/how-to/bot-messages-ai-generated-content>

Not Microsoft: 01:7 "Framework 2026": <https://www.finops.org/framework/personas/> lists five allied personas ✔; "2026" unconfirmed.

## 5. Questions left unanswered

1. If Maya never answers the safety-check question (E2, 02:171), what restores the database?
2. How long does a Note last by default, who sets it (samples run 3 and 6 months), and how long is a Case parked (02:105)?
3. After the first undo window, how does an owner stop E1's recurring schedule ("then every weekday evening")?
4. How are the 17 templates localised, when their strings are English and Settings offers four languages?
5. What does "Yes, this is expected" on a Heads-up change: a Note, a mute or nothing, and for how long?
