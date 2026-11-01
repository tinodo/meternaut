# Closure check — raw idea D and E

| Report | # | Severity | Status | Evidence |
|---|---:|---|---|---|
| raw-idea-d | 1 | Blocker | CLOSED | “it asks, and a refusal means no capture.” (`06-people-and-conversation.md:292`) The same paragraph covers late joiners, recipients, retention, lessons and deletion requests. |
| raw-idea-d | 2 | Blocker | CLOSED | “Every name, resource, date, figure, approval and outcome in the examples below is invented.” (`06-people-and-conversation.md:3`; `08-outer-rims.md:3`) |
| raw-idea-d | 3 | Blocker | CLOSED | “only on a route that person agreed to, in a country where it is allowed, with a fallback when nobody answers” (`06-people-and-conversation.md:95`) |
| raw-idea-d | 4 | Major | CLOSED | “The owner's story stays private” (`08-outer-rims.md:34`); organisations “share only a scope and an aggregate” (`08-outer-rims.md:82`). |
| raw-idea-d | 5 | Major | CLOSED | “the meeting hears one agreed spoken language; each person can choose a translated text view” (`06-people-and-conversation.md:298`) |
| raw-idea-d | 6 | Major | CLOSED | “only an authorised human, or a rule a human wrote, can permit an action.” (`08-outer-rims.md:46`) |
| raw-idea-d | 7 | Major | CLOSED | “recovery has been shown to fit an agreed outage budget and anything that cannot be undone is stated” (`08-outer-rims.md:36`) |
| raw-idea-d | 8 | Major | CLOSED | “saying aloud the checks they make”; the AI “reads back the steps it saw and what it could not tell” (`08-outer-rims.md:40`). |
| raw-idea-d | 9 | Major | CLOSED | “Billing reach would let me look for unused commitments; how many, and how much, stays unknown until I can inspect them.” (`08-outer-rims.md:68`) |
| raw-idea-d | 10 | Major | CLOSED | “Owners define the units — customer, transaction, feature — and the rules for splitting shared costs”; unallocated shared costs remain visible (`08-outer-rims.md:70`). |
| raw-idea-d | 11 | Major | CLOSED | “emissions estimate linked to activity”; its boundary, uncertainty and missing inputs are shown, and emissions are not derived from euros (`08-outer-rims.md:74`). |
| raw-idea-d | 12 | Major | CLOSED | “A ‘nine’ is one more 9 of availability”; configurations, target, load, failure assumptions and conditional scenarios are stated (`08-outer-rims.md:72`). |
| raw-idea-d | 13 | Major | CLOSED | The “budget owner” funds the dividend “from those savings”; “operational harm and financial loss remain possible.” (`08-outer-rims.md:76`) |
| raw-idea-d | 14 | Major | CLOSED | The summary must “open with ‘This is the AI cost assistant’” (`06-people-and-conversation.md:289`; example at `:362`). |
| raw-idea-d | 15 | Major | CLOSED | Availability signals are “provided or authorised” (`06-people-and-conversation.md:258`); delegates are “confirmed with the person, never inferred” (`:260`). |
| raw-idea-d | 16 | Minor | CLOSED | “repeating a question that already has a valid answer (re-ask only when the facts changed or the answer expired, and say so)” (`06-people-and-conversation.md:332`) |
| raw-idea-d | 17 | Minor | CLOSED | Shadow means it “nominates cases privately for comparison, without contacting owners or changing Azure.” (`08-outer-rims.md:32`) |
| raw-idea-d | 18 | Minor | CLOSED-BY-DELETION | Searches for “Not a notification that informs” and “has no business managing yours” returned no matches in the two documents. |
| raw-idea-d | 19 | Minor | CLOSED | “Recommendations can overlap; the replay combines their benefits and reports the joint value instead of adding the individual estimates.” (`08-outer-rims.md:60`) |
| raw-idea-e | 1 | Blocker | CLOSED | Advisor situations are now described as “some by plain checks, some by machine learning” (`10-press-release-from-the-future.md:35`), with Learn links. |
| raw-idea-e | 2 | Major | CLOSED | Routes are “Ask · Look · Replay · Follow · Pool · Trial” (`09-the-learning-contract.md:120`); the separate “Autonomy ladder” is named at `:121`. |
| raw-idea-e | 3 | Major | CLOSED | “Skeptic (tries to refute everything)” (`09-the-learning-contract.md:14`), Economist and Auditor both receive inline role glosses (`:49-50`). |
| raw-idea-e | 4 | Major | CLOSED | “status *Verified*, which means *source-verified*”; “That makes it *documented*; no bill has confirmed it.” (`07-getting-smarter.md:100`) |
| raw-idea-e | 5 | Major | CLOSED | Commons is defined as “the open, shared half of what the system has learned about Azure; never a customer's own data” (`10-press-release-from-the-future.md:26`). |
| raw-idea-e | 6 | Minor | CLOSED | “Idea-level: what the system commits to, not how it is built.” (`09-the-learning-contract.md:4`) |
| raw-idea-e | 7 | Minor | CLOSED | “None of this learning depends on retraining a model's weights.” (`09-the-learning-contract.md:19`) |
| raw-idea-e | 8 | Minor | CLOSED-BY-DELETION | Search for “deliberately not a verdict” returned no match; the Detector definition now directly says “it nominates, investigators decide” (`09-the-learning-contract.md:117`). |
| raw-idea-e | 9 | Minor | CLOSED | Case is “a confirmed finding about one estate, with its notebook” (`09-the-learning-contract.md:122`); “purchases are prepared at the **Commitment Desk**” (`:125`). |
| raw-idea-e | 10 | Minor | CLOSED | First use now says “the Atlas, the open knowledge base of how Azure charges” (`09-the-learning-contract.md:12`). |
| raw-idea-e | 11 | Minor | CLOSED | The figures now include “15% are still open or expired unanswered.” (`10-press-release-from-the-future.md:19`) |

## New defects

- `N-1 · Major · 06-people-and-conversation.md:191 · “Saving: about EUR 4,300/month, a scenario at list prices” ·` This contradicts the document's own rule at line 107: without a readable bill it is a scenario, not a saving. **Fix:** `Scenario value: about EUR 4,300/month at list prices; your quote decides — send it and I will re-check.`
- `N-2 · Major · 01-north-star.md:168 · “the expected saving (a labelled list-price scenario where the bill cannot be read)” ·` The vocabulary source contradicts line 167 by calling the same no-bill figure both a saving and a scenario. **Fix:** `the expected value — a labelled list-price scenario where the bill cannot be read`.
- `N-3 · Major · 10-press-release-from-the-future.md:59 · “tries again weekly and after any refusal” ·` The required trigger is immediate after a 401 or 403; “refusal” is undefined and “at once” is missing. Lines `01:166` and `09:115` use the same undefined shorthand. **Fix in all three:** `The capability profile is probed at onboarding, weekly, and at once after a 401 or 403.`
- `N-4 · Major · 06-people-and-conversation.md:215 · “the storage-tiering change you approved in October is verified” ·` “Verified” is bare and bypasses the four evidence levels, although the next line supplies outcome evidence. **Fix:** `the storage-tiering change you approved in October is outcome-confirmed:`.

### Questions left unanswered — current answer

- **D-Q1:** Answered: consent, late joiners, retention, recipients, separate lesson confirmation and human-decided deletion are covered at `06:292`.
- **D-Q2:** Partly answered: emergencies use an agreed on-call route and wider recipients need entitlement (`06:95,274`), but generic **Talk to a human** outside hours is not assigned.
- **D-Q3:** Answered: owners' priorities and human-set mandates decide; agents only present options (`08:48`).
- **D-Q4:** Answered: unavailable access, allocation, load, failure, emissions and boundary inputs are shown as unknown, unallocated or missing (`08:68-74`).
- **D-Q5:** Answered: the budget owner authorises, verified sustained savings fund the dividend, and operational or financial losses remain possible rather than insured (`08:76`).
- **E-Q1:** Answered: downgrade the claim, tell affected owners and retain the correction in the Ledger (`09:53`).
- **E-Q2:** Answered: a stated regret-rate threshold/window, one defined-severity regret, or human revocation withdraws the credential (`09:53`).
- **E-Q3:** Answered: the missing 15% are open or expired unanswered (`10:19`).
- **E-Q4:** Answered: the lower gate verdict stands until new evidence settles the disagreement (`09:53`).
- **E-Q5:** Answered: use the escalation path, then expire and record the question as unanswered; silence is never consent (`09:73`).

Counts: closed 28; closed by deletion 2; rejected-ok 0; partly 0; open 0.

Verdict: No — all assigned findings are closed, but four new Major defects still expose contradictions or undefined evidence/cadence wording.
