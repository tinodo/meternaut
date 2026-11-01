# Model: GitHub Copilot (underlying model identifier not exposed) — Files read: stranger-test-brief.md; 06-people-and-conversation.md; 08-outer-rims.md; 01-north-star.md (cross-reference excerpts only)

## 1. Verdict

**No:** the interactions are understandable, but the documents are not yet trustworthy for publication. Unlabelled invented evidence, unexplained recording/sharing boundaries and promises without sufficient mechanisms need revision.

Read both assigned files completely, in the assigned order. Opened `01-north-star.md` only to check referenced vocabulary, private/shared knowledge, generated test data and human authority: lines 61–107, 230–285 and 360–417, plus targeted reference searches. No design documents or other repository documents were opened. Billing-agreement “contract” renaming is excluded; no other ambiguous “contract” use or retired lab/exam/Terrarium/Move/Brief label was found.

## 2. Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | 06-people-and-conversation.md:293,302 | 5,7 | “it records decisions, writes Lessons and follows up on the dates” | An AI label is not recording permission or consent. Capture, late joiners, retention and recipients have no stated boundary; see check 4. | “Before capture, explain purpose, retained content, recipients and retention. Obtain required permission and consent, including late joiners; refusal means no capture. Confirm proposed lessons separately.” |
| 2 | Blocker | 06-people-and-conversation.md:115–123,145–148,186–198,207–224; 08-outer-rims.md:50,60–86 | 6 | “To: Joost de Wit, partner desk”; “−€710 a month, −0.4 tonnes CO₂e a year” | These read like customer evidence and named approvals. The invented-data notice at 06:342 covers §15, not earlier examples; 08 has none. | Add before the first examples in both files: “All example names, resources, dates, figures, approvals and outcomes are invented.” |
| 3 | Blocker | 06-people-and-conversation.md:94 | 5 | “Voice and text need a telephony or messaging service, not Teams” | The categorical exclusion is wrong: Teams supports calling and certain Calling Plan SMS. It also decides delivery technology in ideation. | “Emergency voice and text require approved reachability, country support and a fallback; delivery technology belongs in design.” |
| 4 | Major | 08-outer-rims.md:10,36,86 | 4,7 | “yours or, anonymously, another estate's”; “with no estate's data in it” | Anonymous bills and real decoys remain estate-derived information. Counts are data too; the wording obscures the review/private-knowledge boundary in 01:240,283. | “Keep bills and owner stories private. Share reviewed general claims, generated decoys and opt-in aggregates with safeguards against exposing small groups.” |
| 5 | Major | 06-people-and-conversation.md:301 | 3,5 | “it speaks live in each person's language, with captions” | No experience is specified for different languages sharing one spoken channel. Avatar synthesis does not establish simultaneous individual translation; see check 5. | “The meeting hears one agreed spoken language; each participant can choose a translated text view. Disputed wording and figures are confirmed in writing.” |
| 6 | Major | 08-outer-rims.md:48 | 4 | “rules. Humans can appeal.” | Appeal suggests a binding agent verdict, unlike the human-controlled Recommendation in 01:257,366. What the Judge decides is unclear. | “Agents record the strongest competing arguments and a recommendation; only an authorised human or an existing human-written rule permits action.” |
| 7 | Major | 08-outer-rims.md:38 | 3 | “with a guard that restores it in seconds” | Restarting is not undoing lost requests or missed work. Recovery time and acceptable harm are unbounded. | “Offer only owner-approved trials with demonstrated recovery within an agreed outage budget; state unrecoverable effects. Otherwise use existing observations.” |
| 8 | Major | 08-outer-rims.md:42 | 3 | “the checks the human made without thinking”; “Azure's own what-if preview” | Observation cannot recover silent judgement. Selecting a named validator is design work, not a mechanism for capturing the human’s checks. | “The human narrates checks; the AI reads back observed steps and unknowns, then proposes a recipe for review.” Move validation-product choices to design. |
| 9 | Major | 08-outer-rims.md:72 | 3 | “one covers nothing” | Starting without cost or billing access cannot establish hidden commitments or precise benefits of obtaining access. | “Cost access could replace estimates with observed charges; billing access could reveal unused commitments. Counts and value remain unknown until inspected.” |
| 10 | Major | 08-outer-rims.md:74 | 3,7 | “Cost per customer, per transaction, per feature — linked to revenue” | Costs alone contain neither business units, revenue nor a shared-cost allocation rule. The joining mechanism is missing. | “Owners define units and allocation rules; combine permitted activity and revenue records with costs, and show unallocated shared costs.” |
| 11 | Major | 08-outer-rims.md:78 | 3,7 | “the emissions of a change” | A price model does not yield emissions. Activity sources, accounting boundaries and estimation uncertainty are absent. | “Add carbon only with activity-linked emissions estimates and comparable boundaries; show uncertainty and missing inputs, never infer carbon from euros.” |
| 12 | Major | 08-outer-rims.md:40,76 | 2,3 | “the next nine costs about €4,200 a month” | “Next nine” first appears at 76 and is never defined. Matching a historical bill proves neither threefold-load capacity nor an availability gain. | “Compare named configurations and availability targets; state load and failure assumptions. Label costs as conditional scenarios, not proven reliability improvements.” |
| 13 | Major | 08-outer-rims.md:80 | 3 | “Both make yes safe.” | A dividend and blameless review neither prevent harm nor insure financial loss. “Insurance” has no compensating mechanism. | Rename “savings dividend and blameless review”; replace the sentence with “These reduce approval disincentives; operational harm and financial loss remain possible.” |
| 14 | Major | 06-people-and-conversation.md:365 | 4 | “This summary was composed by an AI” | Disclosure comes at the end of the audio, unlike the opening disclosure in the emergency call. Listeners stopping early miss it. | Open with “This is the AI cost assistant. Here is your ninety-second summary.” |
| 15 | Major | 06-people-and-conversation.md:261–268 | 3,7 | “Working hours and time zone, presence, out-of-office, focus time.” | Mailbox, presence and calendar information require distinct access; Azure access does not guarantee these signals or knowledge of release days. | “Use only provided or authorised availability signals; ask for a preferred schedule when unavailable, and confirm delegates rather than infer them.” |
| 16 | Minor | 06-people-and-conversation.md:179,336 | 4 | “asking the same question twice” | This absolute prohibition conflicts with “keeps asking” and reopening after changed evidence. | “Never repeat a valid answered question; re-ask only with changed facts or explained expiry, and announce escalation.” |
| 17 | Minor | 08-outer-rims.md:34 | 2 | “runs it in shadow” | First use at 34; no definition follows in the assigned files or checked cross-reference excerpts. Does it contact people or just nominate cases? | Say “nominates cases privately for comparison, without contacting owners or changing Azure.” |
| 18 | Minor | 06-people-and-conversation.md:139; 08-outer-rims.md:90 | 1,6 | “Not a notification that informs”; “has no business managing yours” | Defensive contrasts and slogans repeat purpose without adding behaviour. | Delete 06:139 and the final sentence of 08:90; retain the card example and specific self-cost measurement. |
| 19 | Minor | 08-outer-rims.md:64 | 3 | “Every Recommendation is right alone and claims the same euro.” | Not every Recommendation is correct or overlaps. The useful portfolio idea needs neither absolute. | “Recommendations can overlap; replay combined benefits and report joint value rather than adding individual estimates.” |

## 3. Sentences I would delete

- `06-people-and-conversation.md:139`: “Not a notification that informs, but a micro-lesson triggered by what the person is doing now:”
- `08-outer-rims.md:64`: “Every Recommendation is right alone and claims the same euro.” Replace as #19.
- `08-outer-rims.md:80`: “Both make yes safe.” Replace as #13.
- `08-outer-rims.md:90`: “A system that cannot manage its own bill has no business managing yours.”

## 4. Fact checks

Checked **five claims**, against Microsoft Learn pages fetched on **1 November 2026**. These checks distinguish available building blocks from a complete product experience; they do not select an implementation.

1. **Voice/text cannot use Teams — 06:94. Wrong.** Teams provides native internal calling and Teams Phone PSTN connectivity. Calling Plan SMS supports US/Canada numbers with licensing and registration; the page describes GA rollout, not universal availability. This does not prove an arbitrary AI has an outbound SMS interface.
   - https://learn.microsoft.com/en-us/microsoftteams/what-is-phone-system-in-office-365
   - https://learn.microsoft.com/en-us/microsoftteams/sms-overview

2. **Interactive Teams cards — 06:102,238. Supported, conditionally.** Buttons can send data to an application or open a page; neither capability alone grants authority for the exact Azure change. The source is marked legacy documentation, not a declaration that cards are retired.
   - https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-actions

3. **Working hours, timezone and presence — 06:261–263. Supported through distinct sources/access, not guaranteed.** Mailbox settings expose working hours, timezone and automatic replies; presence access has separate permissions. These do not establish release-day plans.
   - https://learn.microsoft.com/en-us/graph/api/resources/mailboxsettings?view=graph-rest-1.0
   - https://learn.microsoft.com/en-us/graph/api/presence-get?view=graph-rest-1.0

4. **An AI meeting participant retaining meeting memory — 06:292–302. Joining supported; retention is conditional.** For Media Access, persisting media or derived data requires policy-based recording and successful recording-status signalling first. Native recording’s explicit-consent policy is separate and configurable. Neither an invitation nor an AI label supplies these permissions.
   - https://learn.microsoft.com/en-us/graph/cloud-communications-concept-overview
   - https://learn.microsoft.com/en-us/graph/api/call-updaterecordingstatus?view=graph-rest-1.0
   - https://learn.microsoft.com/en-us/microsoftteams/meeting-recording

5. **Live multilingual avatar — 06:294–301. Partly supported; the combined experience is unverified.** Speech supports real-time avatar synthesis with supported voices/languages. That does not establish simultaneous per-person translation, Teams hand-raising, chart synchronisation or compliance with the proposed fictional-character policy. These remain desired behaviours, not verified bundled capabilities.
   - https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech-avatar/what-is-text-to-speech-avatar

## 5. Questions left unanswered

1. What happens when a guest or late joiner declines capture, and who controls deletion of transcripts and derived lessons?
2. Which human receives “Talk to a human” outside working hours, and what may that person see?
3. Whose mandate wins when team agents disagree over a shared resource?
4. How are missing business-unit, dependency, emissions or billing inputs made visible before presenting an answer?
5. Who authorises and funds the savings dividend and recovery budget, and what losses do they actually cover?
