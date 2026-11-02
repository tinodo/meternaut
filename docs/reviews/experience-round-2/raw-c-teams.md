# Verdict

No. The intent is understandable, but a Microsoft 365 Agents SDK builder cannot safely implement it without inventing the activity envelope, proactive-delivery contract, action lifecycle and mobile fallback; two stated Teams behaviours are wrong or unsafe.

# Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | `04-messages-and-cards.md:224`; `cards/settings.json:52,297,346` | 8 | “inside a ShowCard, of every parent card” | That rule is correct, but C14 puts all settings inputs on the parent card. Its **Explain** action therefore submits the unsaved settings plus `level`; **Talk to a person** submits every setting. Default `associatedInputs` is `auto`. This is silent data transmission and an unusable route contract. | Put the settings form inside its own ShowCard, leaving conversation actions on an input-free parent. Set `associatedInputs: "none"` on every action that needs no inputs, and specify accepted input ids per verb. |
| 2 | Blocker | `04-messages-and-cards.md:264`; `cards/data/done.json:9` | 4, 5 | “Teams documents no read receipt for a bot” / “if you have not looked” | Current Teams supports read-receipt events in personal agent chats when `ChatMessageReadReceipt.Read.Chat` is consented and tenant/user read receipts are enabled. The text is false, while C6 simultaneously promises behaviour based on read state without naming that optional permission or its fallback. | Replace with: “Read receipts are optional and may be unavailable. Without one, I know only whether you responded.” Change C6 to “if you have not responded,” or document the RSC permission and disabled-receipt path. |
| 3 | Major | `04-messages-and-cards.md:207,233` | 5, 7, 8 | “sends … one to one through the app” / “per-person send budget is far below Teams’ limits” | First contact requires the personal app to be installed or a conversation to be created, then durably stored. Delivery can return blocked/uninstalled `403`s. A low per-person budget does not satisfy the current 50-RPS app/tenant limit or per-thread limits. No queue, retry, `Retry-After`, idempotency or failure state is defined. | Add a proactive-delivery contract: installation path, conversation storage key, blocked/uninstalled outcome, queue partitioning, 429/412/502/504 backoff, global/per-thread throttles and duplicate suppression. |
| 4 | Major | `04-messages-and-cards.md:222`; all templates’ `fallbackText` | 5, 8 | “Every `Action.Execute` carries … an `Action.OpenUrl` … A client … shows ‘Open on the page’” | `Action.OpenUrl` is schema-legal fallback, but Microsoft’s Teams backward-compatibility guidance requires `Action.Submit`. More importantly, a client rejecting the root 1.5 card can show only `fallbackText`; these strings contain no URL. The generic `${pageUrl}` also loses the intended verb. | State a 1.5+ client floor. Provide a tested whole-message fallback containing a signed page link, and use action-specific page URLs. Do not claim unsupported clients necessarily render the per-action OpenUrl. |
| 5 | Major | `04-messages-and-cards.md:216-218` | 4, 8 | “answers with a replacement card” / “Every tap gets a visible receipt … finishes asynchronously” | One `Action.Execute` invoke returns one immediate response. The document never says whether the replacement is the plan, the receipt or a terminal card, nor how a later update finds the original activity. It also says every tap calls the Approval service, although Explain, settings and handoff are not approvals. | Add a per-verb response matrix: Agents SDK route, auth handler, immediate invoke response, replacement/update/new-message behaviour, stored activity id, asynchronous completion and idempotency rule. |
| 6 | Major | `04-messages-and-cards.md:43-44,210` | 7, 8 | “sets `Activity.text`” / “Machine-readable mark: In the message data” | The templates, sample data and manifest define only card content. They do not define notification text, `Activity.Summary`, the AI-generated activity entity/helper, feedback metadata, locale or attachment wrapper. A builder must invent the actual Teams message. | Add a versioned message-envelope schema and one complete Agents SDK example for every card: `Text`, `Summary`, attachment, AI entity, optional feedback, locale and conversation metadata. Make notification text required sample data. |
| 7 | Major | `cards/manifest.json:46-65`; `cards/recommendation.json:225,259,295,441` | 7, 8 | C3 declares `option`, `not-now`, `not-mine`, `fewer`; template also sends `explain`, `challenge`, `teach`, `human`. | The manifest is not an implementable action contract. It omits common verbs, input ids, payload types, auth requirements, allowed states and response cards. “The lint rejects any other key” cannot be implemented from this manifest. | Replace `verbs` with complete action definitions: verb, inputs/data, plan-code requirement, auth handler, legal source states, idempotency key and response card/state. |
| 8 | Major | `04-messages-and-cards.md:93,98`; `cards/your-ok.json:57-60` | 8 | “The plan as a table (resource, setting, from, to)” / `"type": "Table"` | C4 makes an approval depend on a four-column table containing long resource and schedule text. Learn supports schema 1.5 but explicitly requires narrow-form testing; no phone rendering or alternate linear layout is supplied. The reference image is wide desktop only. | Supply a mobile-safe C4 template using one labelled vertical container per resource, or route mobile approval to the page. Make phone, screen-reader and 200%-zoom renderings release artefacts. |
| 9 | Major | `04-messages-and-cards.md:60`; `cards/data/question.json:7`; `cards/data/ok-on-page.json:8`; `cards/data/told-afterwards.json:8` | 4, 8 | “Two chips sit beside every money figure” | The templates permit money inside arbitrary strings: €1,100 has no certainty word; €205,860 and €23.50/hour lack adjacent basis/certainty; €500 in C8 has neither. This contradicts the stated invariant and cannot be enforced reliably by card lint. | Represent every monetary value as a structured object (`amount`, `period`, `basis`, `certainty`, `kind`) rendered by one shared component; reject currency symbols in free-text fields. |
| 10 | Minor | `cards/manifest.json:134-136,184-201,241-243`; `cards/told-afterwards.json:32`; `cards/widen-request.json:32`; `cards/weekly-desk.json:32`; `cards/could-not.json:32` | 4 | “Told afterwards” / “Done under a standing permission” | Four visible type labels differ from their manifest/document names (also Widen request/A request about a note, Weekly desk/Your weekly desk, I could not/I could not do that). Tests, telemetry and support language have no canonical title. | Add `displayTitle` to the manifest and use it verbatim in each template and document table. |

# Sentences I would delete

- `04-messages-and-cards.md:264` — “Teams documents no read receipt for a bot.”
- `04-messages-and-cards.md:233` — “The per-person send budget is far below Teams’ limits.”
- `04-messages-and-cards.md:222` — “A client that cannot run the action shows ‘Open on the page’…”

# Fact checks

1. **Schema/features.** Teams supports Adaptive Cards 1.6 or earlier; Table was introduced in 1.5; ShowCard and ToggleVisibility are supported. Version 1.5 is valid, but Learn still requires narrow/mobile testing.  
   https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-reference  
   https://learn.microsoft.com/en-us/adaptive-cards/schema-explorer/table
2. **Universal Actions.** Returning an Adaptive Card from `Action.Execute` replaces the current card: verified. Teams guidance says backward-compatible cards must use `Action.Submit` fallback; the document’s OpenUrl policy is a deliberate, unverified alternative.  
   https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/work-with-universal-actions-for-adaptive-cards  
   https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/sequential-workflows
3. **ShowCard inputs.** Verified: `Action.Execute` gathers current-card and parent-card inputs by default. This confirms finding 1.  
   https://learn.microsoft.com/en-us/adaptive-cards/schema-explorer/action-execute
4. **Activity versus card metadata.** `fallbackText` is only for a client unable to render the card. The AI label is activity-level metadata (`AddAIGenerated`), not template JSON. The cited API does not substantiate the notification-preview behaviour attributed to `Activity.text`.  
   https://learn.microsoft.com/en-us/dotnet/api/microsoft.teams.cards.adaptivecard.fallbacktext  
   https://learn.microsoft.com/en-us/microsoftteams/platform/agents-in-teams/integrate-ai/ai-content-labels
5. **Delivery, rates and reads.** Proactive personal messages require installation/conversation state; current limits include 50 RPS globally plus per-thread limits; personal-chat read receipts now exist but are permission- and setting-dependent.  
   https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages  
   https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/rate-limit  
   https://learn.microsoft.com/en-us/microsoftteams/platform/bots/build-conversational-capability#receive-a-read-receipt

# Questions left unanswered

1. What exact Agents SDK activity envelope is persisted and sent for each card?
2. What is the request/response/auth/idempotency contract for every verb?
3. How is the personal app installed and the proactive conversation created, stored and retired?
4. What does “Talk to a person” do when nobody is available, and what receipt replaces the card?
5. What is the approved mobile rendering of C4 and of the expanded C3 Details panel?
