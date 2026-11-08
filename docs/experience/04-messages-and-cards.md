# The anatomy of a message and the Teams cards

**What this document answers.** What every message carries, and why; how the Recommendation card is built; what the seventeen Teams cards are for; how access changes a Recommendation; how a card is made, sent and answered; and what a card cannot do.

## The layers of a message

A message is short on purpose. Whatever a person may want to check is one step away, in four more layers.

Look at the message in the middle: every layer leads out of it and back.

```mermaid
flowchart LR
    M("The message<br/>layer 0")
    D["Details<br/>layer 1, inside the card"]
    E["Ask or tell<br/>layer 2, asked in the card"]
    N["The notebook page<br/>layer 3"]
    P["A person<br/>layer 4"]
    L["A new Note, or another look at the finding"]
    M <-->|"Details toggle"| D
    M <-->|"one button"| E
    M <-->|"Evidence row"| N
    M <-->|"name and address in the footer"| P
    E -->|"a question or a note"| L
    L -->|"a changed Recommendation"| M
```

| Layer | What it holds |
|---|---|
| 0. The message | The card as sent |
| 1. Details | Other options and the rest of the [ten-part Recommendation](../design/03-agents-and-workflows.md#6-what-a-person-receives) |
| 2. Ask or tell | A question, or something the AI should know, typed in the card and answered in the thread; it approves nothing |
| 3. The notebook page | Full reasoning and receipts, from the Evidence row of the approval page ([web pages](06-web-pages.md)) |
| 4. A person | A person's name and address, in the footer line |

## What every message carries

**The AI label, four ways.**

| Where | What |
|---|---|
| Sender name | "Meternaut (AI)"; the adopting organisation may rename the product, never the suffix |
| Footer line | One line: "Written by an AI; a person approves every change.", why this person got the card, whom to talk to |
| Teams label | The AI-generated entity (`addAiGenerated()`) makes Teams show its "AI Generated" label; documented per message, so the device test checks it on a card ([Learn](https://learn.microsoft.com/microsoftteams/platform/agents-in-teams/integrate-ai/ai-content-labels)) |
| Machine-readable mark | The same entity in the message; in e-mail, the header `x-ai-generated: true` |

**Talking back.** Every card has one way to ask or tell something: "Ask or tell", a text box and a button. What a person writes is recorded with their name and approves nothing.

**Ask or tell** is answered in the thread. A question gets the reasoning in plain steps, with receipts and an evidence level; an objection gets the recorded objections and what was done about each, and new information earns another round. Something the AI should know is read back with a proposed scope (this resource, this team or everywhere), never wider than the person owns; a wider scope is a request (C11) to whoever owns it.

**One footer line.** Every card ends with one subtle line: that an AI wrote it and a person approves every change, why this person got the card, and whom to talk to, as the name and address of a person at the adopting organisation, never a button or a link.

**Whose prices, and how sure.** Every saving figure carries two chips, in words, never colour alone: the price basis, for example "At the rates on your bill", and the saving word: **Scenario saving** (priced without your rates or a bill line to confirm it), **Expected saving** (a bill line confirms the meter) or **Verified saving** (measured after the change and compared with the prediction). A range sits under every saving a person may act on; a list that only points at decisions, such as the weekly desk, shows "about" and the saving word, with the range one tap away. Any other money figure in a sentence carries its basis there, as in "as invoiced". A **price check** is the system's own stored price computation, with the time it was made and the time it expires.

**Figure notes.** A savings or waste figure is **amortised**: a commitment's cost spread over its term. A budget, invoice or monthly-close figure is **as invoiced**. A figure for a period not yet invoiced is an **estimate**: charges can change until the fifth day after the period ends ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data); [reports and dashboards](07-reports-and-dashboards.md) has the rest). C5 says "amortised" beside its saving and "as invoiced" beside its payment.

## The Recommendation card in detail

(An invented example.) The wireframe shows the Recommendation (C3) that Maya receives.

![Wireframe of the Recommendation card with eight numbered parts, from sender to footer, and the Details panel open.](../img/experience-recommendation-card.svg)

| Part | What it holds |
|---|---|
| 1. Sender row | "Meternaut (AI)" and the type label "Recommendation" |
| 2. Headline and scope | The one change proposed, in the owner's words, ending in a question; its scope |
| 3. Value tile | A range, never a single figure; the price-basis chip; the saving word; what keeping things as they are forgoes, stated once |
| 4. Why I think so, What I checked | The evidence in a line or two and why I prefer this option to one that saves more; the strongest objection and what was done about it, side by side |
| 5. Decisions | Review the plan, "No, leave it as it is", Not mine: one tap each |
| 6. Talk back | The Details toggle, and "Ask or tell", which opens a small input |
| 7. Details | The hidden part the toggle opens, see below |
| 8. Footer | The one footer line |

Five controls are visible: three decisions and two toggles.

**The ten parts.** The numbers above mark places on the screen. The Recommendation itself has ten parts ([design](../design/03-agents-and-workflows.md#6-what-a-person-receives)): what it proposes; why, and how to check; options; consequences; what was tested; what would change my mind; effort; reversibility; what happens on yes; how everyone will know. The face shows the first three, plus short forms of consequences and what was tested. **Inside Details** are at most two other options, each with its own button, range, saving word and price basis, then the other seven parts and "Fewer like this".

**A refusal is never chased.** "No, leave it as it is" closes this ask and no reminder follows; the same Recommendation returns only if the evidence changes materially or a note expires, and then it says why. "Not mine" hands the item to cover, says nothing about the person and optionally asks why.

**An unresolved objection becomes a Question first.** If the strongest objection is a fact only the owner knows, the system asks a Question (C2) and sends the Recommendation after the answer. (An invented example.) The Question asks "Does anything run in rg-webshop-qa at night on the last Tuesday?" Maya taps "Something else" and writes "that is the month-end regression"; a Read-back (C10) confirms a Note, and the next Recommendation leaves the environment on that night.

## The plan cards

"Review the plan" authorises nothing. The [bot](../design/05-data-and-integrations.md#6-channels) answers the tap with the plan: the plan card replaces the Recommendation card in the thread, so the exact plan is on screen before anyone is asked for an OK. C4 keeps "Cancel", which drops the plan and changes nothing, and "Open the Recommendation", which puts the Recommendation (evidence, other options) back in the thread and approves nothing. The [approval class](../design/06-security-and-governance.md#approval-classes) decides which plan card appears; C5's header is the class, "Two people" for a purchase and "Your OK on a page" for one person.

| | C4 Your OK (small change) | C5 Your OK on a page |
|---|---|---|
| For | A small, reversible change the person owns | A change that needs a stronger sign-in, or two people |
| Shows | The plan as one block per resource (bold "resource: setting", then From and To lines), when, what could go wrong, undo, the plan code | The headline, a class sentence, the figure, a summary, the plan code |

**On a phone.** At 360 px, in the reference renderer, C3 and C4 stay readable and their buttons wrap; each Teams client wraps in its own way, which the [client matrix](12-testing-the-experience.md#the-client-matrix-layer-5) tests.

![Recommendation card at 360 px: buttons wrap over three rows.](../img/experience-card-c3-recommendation-phone.png)

![Your OK card at 360 px: one block per resource.](../img/experience-card-c4-your-ok-phone.png)

(An invented example.) Maya's plan has the code 7F3K-92QD and three blocks: vm-qa-web-01, vm-qa-web-02 and sql-qa-orders. The order platform's savings-plan purchase is another plan, with its own request and code: its card (C5) says "Plan code K4M8-R6TW. The page shows the same code. Nothing is approved in this message."

**The plan code is a reference**, not a secret and not a token: eight characters from the hash of the plan, shown on the card, the page and the waiting e-mail so a person can check that they match. The [Approval service](../design/05-data-and-integrations.md#7-the-approval-record) refuses a wrong or expired code and a second submit by the same person; the other approver's decision still counts. The plan itself is used once, when it runs.

**The card cannot approve.** A Teams card cannot carry an Azure token, so the button of C4 and C5 opens the page, where the person signs in to Azure and the change is made at that moment, with their own rights.

**The page may open inside Teams.** For a purchase, C5 says "Opens in your browser. If Teams opens it in its own view and your passkey or security key is not accepted, use the link in the e-mail I sent." ([Web pages](06-web-pages.md) says when that e-mail is sent.)

A plan card cannot make a person read the plan; the approver's own Azure rights and an [allow-list](../design/06-security-and-governance.md#5-action-plane-safety) that refuses anything the plan does not name stand between a tired approval and a bad change.

## The seventeen cards

The Card column is the name used here; on the card (the manifest's `displayTitle`) C4 reads "Your OK", C5 its class ("Two people" or "Your OK on a page"), C8 "Done under a standing permission", C11 "A request about a note", C12 "Your weekly desk" and C15 "I could not do that". The last column lists a card's own buttons, as titled on the templates.

| ID | Card | Sent when | Its own buttons |
|---|---|---|---|
| C1 | [Hello](cards/hello.json) | First contact, after the announcement; it says what I keep and who sees it | One decision: Yes, I look after these or Not mine. Offered once, nothing waits on them: Pause messages · My hours and language (working days as seven checkboxes, a summary day, quiet hours, and a time zone and language from lists bound to data) |
| C2 | [Question](cards/question.json) | The system needs a fact only a person has | Two short answers · Not sure · Something else · Not mine |
| C3 | [Recommendation](cards/recommendation.json) | A finding survived challenge and no open fact remains | Review the plan · No, leave it as it is · Not mine · Details |
| C4 | [Your OK (small change)](cards/your-ok.json) | After "Review the plan" on a small change; replaces C3 | Open the page to approve · Cancel · Open the Recommendation |
| C5 | [Your OK on a page](cards/ok-on-page.json) | After "Review the plan" on a page or two-person change; replaces C3 | Review and give your OK · No, leave it as it is · Not mine |
| C6 | [Done](cards/done.json) | A change ran; the undo link only where Azure allows an undo | Open the page to undo · I did not approve this |
| C7 | [Result](cards/result.json) | After verification; not sent where costs cannot be read | Yes, it matches · No, it does not |
| C8 | [Told afterwards](cards/told-afterwards.json) | Optional mode, not built: a standing permission ran | Open the page to undo · Pause changes here |
| C9 | [Reminder](cards/reminder.json) | The one reminder, on day 7; inside the weekly desk instead once the person's push budget is used up | Open the Recommendation · No, leave it as it is · Not mine |
| C10 | [Read-back](cards/read-back.json) | After a person teaches a Note | Yes, that is right · Not quite · No, forget it · Ask for a wider scope |
| C11 | [Widen request](cards/widen-request.json) | Others taught a similar Note, and this person owns the wider scope | Widen the note · Keep it narrow · Show the resources |
| C12 | [Weekly desk](cards/weekly-desk.json) | Weekly, on the person's chosen day | Open, for each item |
| C13 | [Heads-up](cards/heads-up.json) | A spend spike | Yes, this is expected · No, not expected · Not sure |
| C14 | [Settings](cards/settings.json) | On request, or from Hello | Save · More settings |
| C15 | [I could not](cards/could-not.json) | The system cannot do something | Try again |
| C16 | [Our mistake](cards/our-mistake.json) | Advice was wrong, or a change did not do what it said; it gives the state (restored, restoring or unknown), what is paused and who will update by when | What was affected |
| C17 | [A standing permission starts](cards/permission-starts.json) | Optional mode, not built: before the first run of a standing permission: who granted it, its place, cap and expiry, that it never covers a purchase, what each run does, how to pause it | Pause changes here · Not mine |

(Invented.) The pictures are reference renderings of invented sample data, in the light theme, made with the official Adaptive Cards library. Teams draws cards with its own settings, so the look differs slightly: desktop and web have light, dark and high-contrast themes, iOS and Android only light and dark ([Learn](https://learn.microsoft.com/microsoftteams/platform/concepts/design/design-teams-app-color)), where the device's own accessibility settings apply. The templates in `cards/` are the source, and [`cards/manifest.json`](cards/manifest.json) lists all seventeen.

### First contact and settings

![Hello card: the AI introduces itself, asks one decision and offers two settings.](../img/experience-card-c1-hello.png)

![Settings card: channel, language, working days, time zone and quiet hours, then Save.](../img/experience-card-c14-settings.png)

### Asking and deciding

![Question card: does anything run on the last Tuesday night?](../img/experience-card-c2-question.png)

![Recommendation card: switch off a QA environment at night, about €690 a month, Expected saving.](../img/experience-card-c3-recommendation.png)

![Your OK card: three plan blocks, the plan code; Open the page to approve, Cancel and Open the Recommendation.](../img/experience-card-c4-your-ok.png)

![Your OK on a page card, headed Two people, with plan code K4M8-R6TW.](../img/experience-card-c5-ok-on-page.png)

### After the change

![Done card: the change ran, and a link opens the page to undo.](../img/experience-card-c6-done.png)

![Result card: a Verified saving of about €670 a month, inside the predicted range.](../img/experience-card-c7-result.png)

### Standing permissions

![A standing permission starts card (optional mode, not built): grantor, cap and expiry.](../img/experience-card-c17-permission-starts.png)

![Told afterwards card: dev containers moved to a cooler tier under a standing permission.](../img/experience-card-c8-told-afterwards.png)

### Staying in touch

![Reminder card: the figure again, the date it will be parked, no chasing.](../img/experience-card-c9-reminder.png)

![Weekly desk card: two decisions with saving and price basis, and one question.](../img/experience-card-c12-weekly-desk.png)

![Heads-up card: an AI assistant used six times its normal tokens, nothing changed.](../img/experience-card-c13-heads-up.png)

### Teaching the system

![Read-back card: what the AI understood, a choice of scope and an expiry date.](../img/experience-card-c10-read-back.png)

![Widen request card: should a note cover 38 resources owned by nine people?](../img/experience-card-c11-widen-request.png)

### When something goes wrong

![I could not card: the plan no longer matches, so nothing changed.](../img/experience-card-c15-could-not.png)

![Our mistake card: a stopped change, restored; what is paused; who writes by 14:00 CET.](../img/experience-card-c16-our-mistake.png)

## The same Recommendation at five levels of access

(An invented example.) A one-year compute commitment for the order platform, as its value tile reads at each level ([people](01-people.md) has the picture; [agreements and access](../design/14-agreements-and-access.md) defines the levels).

| Access | Value tile | Buying it |
|---|---|---|
| A. Billing reach | About €4,300 a month, range €3,700 to €4,900, "At your agreement's rates", "Expected saving" | The AI buys, on one plan bound to a price check |
| B. Subscription with costs | About €4,100 a month, range €3,500 to €4,700, "At the rates on your bill", "Expected saving" | A request for the billing owner |
| C. Subscription without costs | About €4,900 a month, range €4,200 to €5,600, "At list prices. I cannot see your rates.", "Scenario saving" | A request for the billing owner, as a scenario; the owner's quote settles the number |
| D. Partner-sold | About €4,700 a month, range €4,100 to €5,300, "At retail rates. Your partner's rates are not visible.", "Scenario saving" | A request for the partner, whose quote settles the number |
| E. Pay-as-you-go | About €2,600 a month, range €2,200 to €3,000, "At the rates on your bill", "Expected saving" | A reservation for the steady machines only, bought by an Owner or Reservation Purchaser; a pay-as-you-go bill is at list prices; savings plans need an Enterprise, Customer or Partner agreement ([Learn](https://learn.microsoft.com/azure/cost-management-billing/savings-plan/permission-buy-savings-plan)) |

Only the figure, the words and the purchase path change, never the buttons.

## How a card is built and sent

For builders. A card is a template plus data: a JSON file with `${...}` placeholders, bound to a small object of data by Microsoft's Adaptive Cards templating library. The card lint (`tools/cardlint.py`) is a floor, not the standard ([testing](12-testing-the-experience.md)).

### The send step

Agents draft and workflows send ([data and integrations](../design/05-data-and-integrations.md#6-channels)). The send step:

- **takes the recipient** from the directory's owner of record, never from the draft, and sends one to one through the app; outsiders get e-mail. Names and language are resolved at render time;
- **treats bound text as hostile.** URLs are stripped and markdown is escaped in every bound value, because Teams renders markdown links in cards ([Learn](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-format#format-cards-with-markdown)). Owner text appears in a labelled quote, never in the plan itself;
- **pins the one link,** `${pageUrl}`, to the configured origin plus an opaque request id, and drops every other link;
- **sends one activity per message:** `text` is a one-sentence notification line (`notificationText` in the sample data), the card is the attachment, and the AI-generated entity, a locale and the stored conversation reference complete it. Which of `text` and `summary` Teams shows in the toast and the chat-list preview is a client-matrix test.

### What a button sends

A button sends an opaque request id, a verb and, when it decides something, the plan code and a one-time token that was made for that person; at most an option key, a scope or a reason chip joins them. A decision carries no prose: only "Ask or tell" and the text boxes send words, which are bounded, screened and quoted as untrusted data, and free text never approves. (An invented example.) "Cancel" sends the verb `cancel`, the request id `r_9vK2xQ` and the plan code `7F3K-92QD`.

[`cards/manifest.json`](cards/manifest.json) lists, for each verb of each card, the input ids it accepts (the service ignores any other id), whether it needs the plan code, and what the tap returns: a `receipt`, an `answer`, a `handoff` or a named `card`; a button that only opens the page is listed under `openUrl`. One `contract` covers every verb: who may tap (the card's addressee; for a decision, the designated approver or a named delegate, by directory object id), what a repeated tap does (nothing: the service answers "already recorded"), when a verb is refused (the request is expired, changed, answered or paused; "I did not approve this" stays open) and what a tap returns (one immediate response, then the outcome by updating the same message).

A tap reaches the bot as an `adaptiveCard/action` request. The bot checks the Connector's signed token, knows the person by the directory object id in the request, records an answer that changes nothing in Azure (a decline, a question, "not mine", "later", or "worth acting on" for a finding that only asks that) through the same Approval service as the web page, and answers with a replacement card ([Learn](https://learn.microsoft.com/adaptive-cards/authoring-cards/universal-action-model)).

An approval of a change is never taken on a card: its one link opens the page, where the person signs in to Azure and Azure checks that person's own rights. Every tap gets a visible reply within about a second, the card the manifest names for the verb or a receipt, because a bot that takes longer than 10 to 15 seconds times out ([Learn](https://learn.microsoft.com/azure/bot-service/bot-builder-howto-long-operations-guidance)).

### The fallback and the inputs

Cards use schema 1.5 ([cards reference](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-reference#adaptive-card), [agent design](https://learn.microsoft.com/agents/design-guidelines/adaptive-cards-for-agent-design#schema-and-host-compatibility)), and the [client matrix](12-testing-the-experience.md#the-client-matrix-layer-5) lists the clients that meet it. A client below 1.5 shows only `fallbackText`, which ends with the page link, the same single link as the card, and "Written by an AI."

Every `Action.Execute` still carries an `Action.OpenUrl` fallback to the page, on purpose not the `Action.Submit` that Teams advises for backward compatibility: a bot cannot answer a Submit with a new card ([Learn](https://learn.microsoft.com/adaptive-cards/authoring-cards/universal-action-model)).

The input of "Ask or tell" sits inside an `Action.ShowCard` card, never on the face, because an `Action.Execute` sends the inputs of its own card and, inside a ShowCard, of every parent card ([Learn](https://learn.microsoft.com/adaptive-cards/schema-explorer/action-execute)). Only Read-back and Settings have face inputs, because their buttons exist to send them; there the manifest lists them for the verb `ask` too, and on Read-back "Not quite" also carries the chosen scope. Every action that takes no input sets `associatedInputs` to `none`, so a face input travels only with a verb that lists it.

### Limits

| Limit | Rule |
|---|---|
| Buttons on a card | At most eight visible and four behind a toggle. Titles have at most 24 characters: a house rule so that each fits alone on a 360 px row, not a Teams limit. Teams' own card limits are in the [platform register](13-platform-register.md) |
| Thumbs | Learn documents Teams' thumbs (`feedbackLoopEnabled`, [Learn](https://learn.microsoft.com/microsoftteams/platform/agents-in-teams/integrate-ai/user-feedback-controls)) per message, not for card messages: they are set where the client supports them, and the [client matrix](12-testing-the-experience.md#the-client-matrix-layer-5) checks whether they show on a card message. They mean only "was this useful" and never change a Recommendation |
| Delivery | A blocked or uninstalled app (403) retires the stored conversation, and the item goes by e-mail. Sends are queued per person and throttled per app and per conversation ([platform register](13-platform-register.md) has the numbers); 429, 412, 502 and 504 are retried with back-off. A send whose result is unknown is recorded as unknown and checked before it is retried; buttons are idempotent, so a duplicate does no harm; the request id is for matching, not a promise that a retry never sends twice ([Learn](https://learn.microsoft.com/microsoftteams/platform/bots/how-to/rate-limit)) |

## The life of one message

Look at the loops: a conversation, a reminder and a reopened item all lead back to the open message, and a refusal ends it.

```mermaid
stateDiagram-v2
    [*] --> Sent : the Recommendation arrives
    Sent --> Talking : Ask or tell
    Talking --> Sent : the answer arrives in the same thread
    Sent --> PlanShown : Review the plan
    PlanShown --> Closed : approved on the page or the plan expires
    PlanShown --> Sent : Cancel or Open the Recommendation
    Sent --> Reminded : day 7, once
    Reminded --> Sent : Open the Recommendation
    Reminded --> Parked : day 14, the person is told once
    Parked --> Sent : the person reopens it
    Parked --> Closed : the expiry passes
    Sent --> Closed : No, leave it as it is, or Not mine
    Reminded --> Closed : No, leave it as it is, or Not mine
    Closed --> [*]
```

The days are starting values; [attention and trust](08-attention-and-trust.md) has the ladder, the cover and the custodian queue. After an OK, Done (C6) and, where costs can be read, Result (C7) arrive as new messages.

## What a card cannot do

| A card cannot | Instead |
|---|---|
| Carry a decision that needs a sign-in to Azure, a security key or a second person | It opens the approval page ([web pages](06-web-pages.md)); no approval is given in Teams |
| Show a chart, a long table or several heading levels | The headline is the one heading, columns are short and no input sits in the hidden Details panel; charts live on a page or in a workbook ([access, language and inclusion](11-access-language-inclusion.md)) |
| Promise that anyone sees it: read receipts reach an agent only in a one-to-one chat, with `ChatMessageReadReceipt.Read.Chat`, and the administrator or the person can switch them off ([Learn](https://learn.microsoft.com/microsoftteams/platform/bots/build-conversational-capability#receive-a-read-receipt)); the design knows only whether the person responded | Timing is never promised; an unanswered Recommendation follows the reminder ladder ([attention and trust](08-attention-and-trust.md)) |
| Be posted in a private channel (agents cannot post messages or cards there, [Learn](https://learn.microsoft.com/microsoftteams/platform/bots/how-to/conversations/channel-and-group-conversations)) or in a shared one (an opt-in this design does not use) | One to one for people, e-mail for outsiders ([letters](05-letters-and-requests.md), [platform register](13-platform-register.md)) |
| Prove that it is genuine: the plan code is a reference | The announcement names the app, its publisher and the one address of the approval page; no card asks for a password or a code |

## Read next

- [Letters and requests](05-letters-and-requests.md): the e-mail fallback.
- [Web pages](06-web-pages.md): where a card hands over.
- [Attention and trust](08-attention-and-trust.md): how often, and trust.
- [Access, language and inclusion](11-access-language-inclusion.md): every reader.
- [Testing the experience](12-testing-the-experience.md): device tests.
- [Platform register](13-platform-register.md): each feature's status.
