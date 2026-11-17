# Held findings: a guard holds back the request, not the finding — a decision record

**Status: decided on 2026-11-17, built and tested against fakes, not deployed.** Nothing here changes Azure ([rule 29](../../AGENTS.md)), and nothing runs until the function app that carries it is published.

## What was wrong

In the real runs of 16 and 17 November the Investigator found things that Meternaut then held back, and a person saw only counts on the start page: "held back: managed by an automation" for ten findings (the dearest worth hundreds of dollars a month) and "held back: not checked who changed it" for six. The guards were right. A change by hand on a resource that something rewrites by itself is undone, a deletion is not asked on a log that was not read, and an impact that was not checked to the end is not asked. They were wrong to make the finding invisible: the waste is real, and the person who can act is not an approver of a click but whoever looks after what rewrites the resource, or after the facts that are missing. A finding that nobody sees is a saving that does not happen.

## What existed

A held finding was a case (status `needs_human` or `proposed`) with no request. The History said why (`case.held`, with `held back: …` words that stay as they are), the run counted it, and the start page said "Held back: N findings" in one sentence. Savings found counted its figure in "Waiting for a person", which says that a person has to answer, though nobody could. No letter, card or page showed its figure, its reason or who may know. The Investigator was given it again as an open question and could judge it again ([proposal 15](15-learning.md)).

## What is decided

**The guards stay.** `brief.held_reason` (an automation changed the resource within 14 days; who changed it was not looked up; what depends on it was not checked), a finding that cannot say what to look at, and a request that was taken back because the rules changed keep deciding what Meternaut may ask a person to approve.

**A held finding is shown as a request of its own.** `Approvals.settle`, which the Watch calls at its end, gives each such finding a request in the new state `held`. It is the existing request that asks a person whether a finding is worth acting on, so the answers that exist work and no second answer system was made: a question, "This is not mine", "Decide later" and "Not worth it" with its reason ("it is still needed", "the figure is wrong", "it is already handled", "another reason"). It has **no Approve**: there is nothing to approve, a sign-in to Azure is never begun for it, and nothing changes in Azure.

**It is no open request.** The state `held` is not `open`, so everything that lists the open requests does not see it: the Decisions page has no row for it, no card is made for it, no letter is sent for it as a request, and `ADVICE_OPEN_MAX` does not count it (a test fills the places and still shows the held findings). It is also no unanswered request in the lessons.

**Its words are written once** (`brief.HOLD_WORDS`, used by the page, the letter and this record):

| Reason | Heading | The guard's sentence | What it still needs |
|---|---|---|---|
| automation | Something that runs by itself changes it | Something that runs by itself changed it N days ago and would change it back, so a change by hand would not last. | Whoever looks after what runs by itself can change it there. Meternaut asks about it as usual when nothing has changed it for 14 days. |
| unchecked | Nobody has looked up who changed it | Nobody has looked up who changed it, so Meternaut does not ask anyone to delete it. | Meternaut looks it up at its next search. Nothing is asked of you. |
| impact | What depends on it was not checked to the end | What depends on it was not checked to the end, so Meternaut does not ask anyone to remove it. | Meternaut checks again at its next search. You can look at what uses it in the meantime. |
| nothing | Meternaut has nothing to say about it yet | Meternaut has no figure, no name of a thing and no words of Azure Advisor for it, so it cannot say what to look at. | Nothing is asked of you. Meternaut asks again when it can say what to look at. |
| rules | Meternaut's rules changed | Meternaut's rules changed, and it had asked about this on less evidence than it asks for now. | Nothing is asked of you. Meternaut looks at it again at its next search. |
| waiting | Waiting for a free place | Nothing holds it back any more, but all the places for requests are taken, so Meternaut has not asked about it yet. | Nothing is asked of you. Meternaut asks about it when a place is free. |

`waiting` is no guard: it is what a held finding becomes when its guard has ended and no request can be made for it yet (see "When a guard ends").

Who may know is the owner line that every page has (the tag, who made the resource, who changed it last): the people that the finding would have gone to are the same list as for any request.

## Where a person sees it

- **Savings found.** A row "Found, and held back from a request" after "Waiting for a person", and below the table a section with one heading for each reason and one line for each finding: a link to its page, the figure with its level and its basis, how sure the AIs are, the guard's sentence and who may know. A finding is in one row only: it leaves "Waiting for a person" when it has its request, so no figure is added twice.
- **"Found in all" counts a held finding's figure.** It is found waste that a person still has to act on, outside Meternaut. The tile says how many of the findings that it counts are held back ("Of which held back: 3"), and the level is the finding's own (Expected or Scenario), as for any other.
- **The page of the finding** (`/why/<id>`, and `/ok/<id>` for a person who is named) has a box with the heading, the sentence and what is needed, the same brief as any request, and the form without Approve. It says that the request ends when nothing holds the finding back, and not on a date; the words after "Ask or tell", "Decide later" and "This is not mine" say where the finding is ("Held back" on the Decisions page, and Savings found) and name no date.
- **The start page** lists, under "Held back", each held finding that the person is named for, with a link and its figure.
- **The weekly letter** has one short block after the decisions: at most three lines (the largest first), each with the title, the figure with its level, the sentence and what is needed, and "N more are held back" for the rest. A person who has only such findings gets a letter that says so in its subject. It has no button of its own and one link, as every letter has; it goes once a week, as the weekly summary does, and is not counted by the weekly budget. A person who has answered the finding does not get it again.
- **No card, ever.** The round of cards looks at open requests only, and a test shows a person who chose Teams getting nothing for a held finding.

## When a guard ends

The automation stops changing the resource, the Activity Log is read, or the impact check completes. The finding is an open question for the Investigator, so at an investigation it is judged again by the normal path (`advise`), with the facts of that day. If nothing holds it back then, it becomes a normal request, and at the end of that Watch `settle` closes the held request, with `takenBack = released` (the page says "No longer held back") and one line in the History, `case.released`, with the words `no longer held back` and the words of the reason that it was held for. The line has no money and no id. The same happens when the finding is dropped, answered, or gets a request of any kind, and a reason that changed is kept as the new reason. **A guard that ends by itself, with no new judgment, does not close it:** the facts of that day were not read, so only a judgment decides.

**It is closed only when a real request exists, or when nobody is to be asked.** If the guard has ended but the normal path makes no request (the places for requests are full), the held request stays, with the reason `waiting`, so that the finding does not lose the one place where a person can see it; it is closed as above once a real request exists. If nobody is to be asked (little is at stake, or a person answered it lately) it is closed at once. A resource that a person marked do-not-touch after the request was made closes it too, with `takenBack = left-alone`, the page word "Left alone" and the History word `closed: a person marked it do-not-touch`.

## Limits

At most 50 held requests are made in one Watch (the rest at the next one); none is made when nobody is on the list of approvers or when what is at stake is not worth a person's time (the rule `why_not_ask` of any request); a finding that a person answered in the last 30 days, or marked do-not-touch, or that has a request open, gets none. A held request never runs out by the clock, so a person may answer it weeks after it was made: the time of the answer is written into its `created_at`, and the 30 days count from the answer. The figure of the case is copied onto a held request at every Watch, so that the letter, the start page and Savings found say the same after a new price. Held requests have a query of their own (`plans_held`, the state `held`), and `plans_recent` leaves them out: the Table store reads the first thousand rows in the order of the key, not of time, so a held request found by a scan of the recent plans would be lost past a thousand plans, and a bulk of them would crowd the newest.

## What is not proved

- It has not run against the real store or the function app. The first Watch after it is published makes the held requests of every held finding at once, up to 50.
- The ten and the six findings of the real runs were not replayed through it, and no stranger has read the five sentences.
- A held finding that the Investigator never cites again stays held until a person answers it or it stops being open: there is no age limit, and the open-questions list gives each its turn, not every investigation.
- The answers of the last 30 days are read from `plans_recent`, as `advise` always did, which the Table store builds from the first thousand rows by key and not by time: past a thousand plans an old answer may be missed. That limit is the normal path's own; the held requests do not depend on it.
- "N days ago" is as old as the last judgment's reading of the Activity Log.
- The people who may know are not always on the list of people (the owner of an automation is often somebody else): the page shows what the tags and the log say, and Meternaut writes to nobody who is not on the list ([rule 15 (g)](../../AGENTS.md)).
- A weekly mention of a finding that asks nothing of a person may be unwelcome; the only mutes are the settings that exist (the weekly budget, "Pause messages").
- Whether the tile should count a held figure at all is a judgment: the page says what it counts.
