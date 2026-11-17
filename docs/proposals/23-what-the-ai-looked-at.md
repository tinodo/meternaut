# What the AI looked at: one record of each investigation, and a page that shows it — a decision record

**Status: decided on 2026-11-17, built and tested against fakes, not deployed.** The page is `/ops/activity`, for the roles ops and owner. It reads one new table, `mninvestigations`, which the end of each investigation writes. It is read-only, it shows no resource name, tag or id, no amount of money and no share of the bill, and it adds no new part to the [style guide](../ui/style-guide.html). Until the function app that carries it is published, and until an investigation has run after that, it shows nothing.

## The owner's words

The owner asked: "when will I see all that AI that you wired in?" Until now a person saw only the requests that survive the guards. Every other thing that the AI did was in the History of Application Insights, which no page reads: what the Investigator looked at and concluded, the findings that code or the second AI stopped, and why a run ended. This record says what is kept, what the page shows, and what is not proved.

## What was missing

| Place | What it shows of the AI's work | What it leaves out |
|---|---|---|
| Decisions, and the page of a request | The requests that were made, with the AI's reasons | A finding that was dropped, held back or left for a person; what the AI examined |
| Runs and findings | The latest findings of the Watch | What the tools read, why the investigation stopped |
| History, Savings found | Counts and money by what became of a finding | The AI's own account |

## What is kept

One record for each investigation that was tried (not one that was switched off, and not one for an app that has no store). It is written when the investigation ends, in the one table `mninvestigations` (partition `i`, a key that sorts the newest first). A write that makes the twenty-first row deletes the oldest, so twenty are kept. The table is made by the first write, like the others, and no read makes it. A run from before this change has no record, and the page says "Not recorded for earlier runs", never zero.

| What | Where it comes from |
|---|---|
| When it began, what started it (`timer`, or `request` for a person or a tool), the two models | The run |
| Calls made and allowed, tokens, seconds made and allowed (the time that it took, also when it failed before its end) | The run and the harness's budget |
| Why it ended: `answered`, `time`, `calls`, `refused` or `failed` | The answer's refused calls and its out-of-time flag, and whether the harness held the run |
| The Investigator's own phrases about what it examined (at most 12, each at most 100 characters) | The answer, cleaned |
| Each finding: its basis, proposal, how sure, how many resources, its sentence (at most 300 characters), the second AI's verdict and at most two objections (120 characters each), what code left out and why, and what became of its resources | The answer, the checks of code and the cases |
| The kinds of resource that the estate is known to have, how many the tools read, and the first 20 of the kinds that they read (with what they did: listed, measured, described, split) and the first 20 of the kinds that they did not read | The toolbox's log and handles, and the cost lines that the Watch read |

**No amount of money is kept.** The cost lines of the run decide one thing: the order of the kinds, the dearest first. The order is worked out by code when the record is made, and neither the amounts, nor their total, nor a share of them is written down or shown. A finding's cost is not kept either.

**What became of a finding's resources** is one of: a request was made, the finding was left for a person (no request yet), it was dropped, or the request was held back for a reason that the History already has (managed by an automation, nobody looked up who changed it, the impact was not checked, nothing to say). The investigation counts them where it makes the case, so the page never works them out again. A test per outcome pins each word.

**Size.** A usual record is about 5,000 characters. At its limits (twelve phrases and eight findings with every text at its longest, and two lists of twenty kinds of the longest shape that a kind has, 80 characters) it is about 13,600, which a test allows up to 14,000, against the 30,000 that a table property of the store may hold. Text is cut by the size of its JSON form, so a character that JSON writes six characters long cannot make a record large.

**What it never holds.** No name, tag, id or description of a resource. The AI's sentences are cleaned like every other text of an AI (no link, no figure of money), and then a subscription or resource id is replaced by "(id removed)" and any word that is the name of a resource that a tool showed in this run, by "(name removed)". A kind of resource is a word of the platform (`provider/type`); one that is too long or has a part that a customer chose is left out. The labels that the AI used inside a run (r1, r53) stay as written, and the page says in one sentence that they mean nothing outside the run.

**It never stops the Watch.** The writer is called when the investigation ends, whatever the way. A store that cannot be written, or a record that cannot be made, is one line in the log with the kind of the fault and never its text, and the run goes on.

## How "looked at" is counted

A kind counts as looked at when a tool that reads resources named it, or was given the handle of one of its resources, in a call that worked. The toolbox's tools that list, measure, describe or split do that, and so do the tools of the bill of a resource or of a kind (`cost_lines`, `cost_history`, and `cost_meters` once it is in the toolbox); the tools that show the AI a list and no resource (the overview of the estate, the names of the metrics, Advisor, the plans, what is recalled) touch no kind. A test fails when a tool of the toolbox is in neither list, so a new tool has to be put in one of them.

The estate has the kinds that a handle or a cost line shows, so a kind that the AI made up is not counted, and a cost line that has no kind of resource (a whole subscription, or a line with no resource) is not a kind. "Looked at" means that a tool read the kind. It does not mean that the AI judged all of it, and the page says so. A subscription whose cost was not read in dollars does not take part in the order, and the page says how many did.

## What the page shows

A title and one sentence, three tiles and five blocks, in this order, from the parts of the style guide.

- **Tiles.** *Looked at in the last run*: how many of the kinds of resource that the estate is known to have a tool read ("12 of 41"). *Findings kept*: how many of the findings that the AI wrote passed the checks of code. *Stopped because*: the word, and the calls and seconds made of the allowed.
- **What the AI looked at and concluded.** When it began, what started it, the two models, and the phrases as a quote labelled "Written by the AI".
- **Findings of the last run.** A table: what the AI says, how sure it is, how many resources, the second AI's verdict, and what became of the resources.
- **Which kinds of resource the AI looked at.** Two lists, each with its count ("Looked at: 12 of 41 kinds", "Not looked at: 29 of 41 kinds"), the first 20 of each, in the order of what each kind cost in the last 30 days, the dearest first, with no amount shown. The first list says what the tools did to each kind. This is the answer to "did it look at my biggest spend?" without a figure of the bill.
- **Earlier runs.** The ten before it, one line each: when, tool calls, findings kept, kinds looked at, why it stopped. A run that investigated and has no record is a line that says so.
- **What this page cannot tell.** One paragraph: a phrase is the AI's own claim, "looked at" does not mean that the AI judged all of it, and a run from before the page was not recorded.

## Rule 25

[Rule 25](../../AGENTS.md) says that the pages never grow into a cost report or a dashboard of spend, and that a figure appears only as part of a case. An earlier version of this page showed the cost of twenty-five kinds of resource and what share of the bill the tools read; that was a dashboard of spend, and it is gone, from the page, from the record and from this record. What stays is a list order that code works out from the cost lines.

## Who sees it, and what it says when it cannot read

A person needs the role ops or owner and gets the refusal of the standing permissions page without one; a person who is not listed gets the denied page. The navigation shows it to those two roles beside Savings found, the Operations page links to it, and only the role ops gets the link to "Every run and every finding". It is a GET and changes nothing. It reads the records and the runs, and nothing else. A store that cannot give the records is the plain "I cannot reach my records" page, and runs that cannot be read are said in a notice, with the lines "not recorded" left out.

## What is not proved

- It has not run against the real table, the real function app or a real estate. The table is made by the app's identity on the first write, which has not been tried.
- It has not been timed. An opening is a read of at most twenty records and the latest forty runs; a write is one upsert and at most one delete.
- The phrases are the AI's own claims and code did not check them. "Looked at" means that a tool read the kind, not that the analysis was deep, and a kind can be looked at in a call that returned nothing useful.
- The kind of a cost line comes from the type in its resource id. A line that a platform bills under another id than its resource can put a kind in the estate that no tool can list, and the order of the kinds rests on the cost lines of the subscriptions that were read in dollars.
- A record is written when the investigation ends. A run that the platform kills in the middle leaves none, and the page then says that the newest investigation was not recorded.
- Twenty records are kept. The page shows the last ten earlier runs.

## What it costs

One small table in the storage account that the app has already, at most twenty rows of up to 14,000 characters, one write for each investigation (about one a week by the timer) and one read of the records and of the runs for each opening of the page. No new resource, no new permission and no new call. The room that it takes in the upload package of the function app is in [the changelog](../../CHANGELOG.md).
