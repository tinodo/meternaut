# Experience design: brief for the closure checkers

Repository: `<repo>` (private; you only read it). "Azure Cost in Action" is an open-source project (MIT): a team of AI agents on Microsoft Foundry and Microsoft Agent Framework that keeps an Azure estate cost-efficient. Nothing is built. The **experience design** in `docs\experience\` says what each person sees, receives and decides; the 17 Adaptive Card templates are in `docs\experience\cards\` and the pictures in `docs\img\experience-*`.

Cold readers (people who had never seen the repository) read the experience documents and filed findings in `docs\reviews\experience-round-2\raw-*.md`. The documents were then fixed. **You are a closure checker, not a cold reader.** You do not re-audit the documents. For every finding in your assigned reports you say whether the current documents close it, and you look for contradictions the fixes created.

## Read first

1. `brief-cold-reader.md` (this folder): what the cold readers were asked (classes 1 to 8 of a finding).
2. `docs\experience\README.md`: the index, the principles and the words people see on screen.
3. Your assigned reports, then the documents each finding points at. The line numbers in a report refer to the documents as they were; search for the quoted words.

## For every finding in your reports (all severities)

State one of:

- **CLOSED**: quote (at most 25 words, with `file:line`) the sentence now in the document that closes it.
- **CLOSED-BY-DELETION**: the passage is gone; confirm by searching for the quoted words.
- **REJECTED-OK**: the finding was not applied (see `disposition.md` in this folder, if it exists, for the reason; otherwise judge it yourself). Say whether keeping the text is right. For a claim about a Microsoft product, read the page on `learn.microsoft.com` and give the URL and a quote of at most 25 words.
- **PARTLY / OPEN**: say exactly what is still missing and give the replacement sentence.

If a fix made the text worse or created a new problem, say so under new defects, not under the finding.

## Then look for new defects (at most eight, Blocker or Major only)

Use grep across `docs\experience` and `docs\experience\cards`; do not guess:

1. **Plan codes and ids.** One plan code per plan: the one-tap QA shutdown card shows `7F3K-92QD`, the one-year savings plan (the purchase) shows `K4M8-R6TW`, the dev storage run `P2WX-5HNC`. The code is a reference: each approver records one decision against it, a second submit by the same person is refused, the plan is used once when it runs. No document may say the code "works once" or is "single use". Cards are C1 to C17; no document may count sixteen.
2. **Chips and words.** The price-basis chips read exactly "At your agreement's rates", "At the rates on your bill", "At list prices. I cannot see your rates.", "At retail rates. Your partner's rates are not visible."; saving words are Scenario, Expected, Verified; a saving figure never appears without its price basis and its word; any other money figure carries its basis in its own sentence. A range is required where a person may act on a saving.
3. **Reaching a person.** Every card but Hello carries "Why you are getting this" (Hello says it in its intro), and every card ends with "Talk to a person" as the last button above the AI footer, in the same place. Compare each claim in the documents about where these sit with the templates in `cards\`. Explain, Challenge and Teach sit on C3 to C9, C13, C16, C17; Explain alone on C1, C2, C10, C11, C12, C14, C15.
4. **Approval classes in words.** People see "one tap" (one OK in the card; opening the plan approves nothing), "your OK on a page" and "two people". A fallback never carries a change (`Action.OpenUrl`, never `Action.Submit`). Nothing is approved by free text, reply, text message or voice. The words that refuse: "No, leave it as it is" (C3, C5, C9), "Not mine", "Cancel" (C4), "Decline" (the page). "Not now" must not survive anywhere.
5. **The safety check.** A failed safety check rolls back automatically only for a one-tap change; for a change that needs your OK on a page it stops and asks the approver, who restores in one tap inside the undo window.
6. **Links.** A card carries one link (the page); every link a message carries is built by the send step from a configured origin and an opaque id; the purchase request carries none.
7. **Examples.** Every example block starts "(An invented example.)" or "(Invented.)"; the running examples keep their numbers everywhere: the QA environment (about EUR 690 a month, range 620 to 760, about EUR 23 a day; first run Thursday 19:30 CET, undo until Friday 19:30 CET, one reminder Friday 09:00), the orders database (EUR 380 to 520), two unattached disks (about EUR 38), the one-year savings plan (about EUR 4,300 a month, range 3,700 to 4,900; USD 25.00 an hour, USD 219,000 in total, about EUR 205,860 at 0.94 euro to the dollar; about EUR 17,155 a month, which follows the exchange rate), the token spike (about EUR 180 more today), dev storage tiering (about EUR 41 a month, undo until Friday 17:00 CET).
8. **Residue.** Sentences that answer an objection nobody made, defend a choice against an unnamed critic, mention earlier versions, review rounds or the people who commissioned the work.
9. **Claims of a measured result** about a system that is not built.
10. **The cap and the alarms.** After five one-tap approvals in a day further changes go to the page; nothing is blocked and nobody is told. Approving outside a person's hours alerts nobody. Only an approval recorded without a matching tap raises an alarm and pauses that person's one-tap approvals.
11. **Three pauses.** "Pause messages" (a person's holiday), "Pause changes here" (an owner stops standing permissions; Undo also pauses the permission until a person has reviewed it) and the kill switch (platform team; levels: global, per kind of change, per estate, as in design 06). No bare "Pause" for any of them; no "Pause automatic changes here".
12. **Read receipts** are never relied on; no promise depends on "if you have not looked".
13. **Card contract.** The manifest lists for every verb its inputs, plan flag and what a tap returns; every action that takes no input has `associatedInputs` `none`; the plan on C4 is one block per resource.

Report a new defect as: `N-<n> · Severity · file:line · quote (at most 25 words) · why it matters · fix`.

## Rules

- **Read-only.** Do not edit any repository file; the only file you create is your report at the path in your assignment. No git. Do not post anywhere or send repository content to a third-party service (the repository is private).
- Verbatim quotes with `file:line`. Do not invent identifiers. A platform fact needs a Learn URL, or say UNVERIFIED.
- Do not praise. Do not summarise the documents.
- Other agents may still be editing a file while you read; if a file changes under you, re-read it before calling a finding OPEN.

## Report format (at most 2,600 words), saved exactly as returned

1. **Table**: `Report` · `#` · `Severity` · `Status` (CLOSED / CLOSED-BY-DELETION / REJECTED-OK / PARTLY / OPEN) · `Evidence` (the quote with `file:line`, or what is missing and the replacement sentence). One row per finding, in report order.
2. **New defects** (at most eight).
3. **Counts** (closed, closed by deletion, rejected-ok, partly, open) and a one-line verdict: could a stranger read your assigned documents without meeting reasoning residue, a contradiction or an undefined term?
