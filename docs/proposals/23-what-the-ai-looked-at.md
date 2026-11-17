# What the AI looked at: one record of each investigation, and a page that shows it — a decision record

**Status: decided on 2026-11-17, built and tested against fakes, not deployed.** The page is `/ops/activity`, for the roles ops and owner. It reads one new table, `mninvestigations`, which the end of each investigation writes. It is read-only, it shows no resource name, tag or id, and it adds no new part to the [style guide](../ui/style-guide.html). Until the function app that carries it is published, and until an investigation has run after that, it shows nothing.

## The owner's words

The owner asked: "when will I see all that AI that you wired in?" Until now a person saw only the requests that survive the guards. Every other thing that the AI did was in the History of Application Insights, which no page reads: what the Investigator looked at and concluded, the findings that code or the second AI stopped, and why a run ended. This record says what is kept, what the page shows, and what is not proved.

## What was missing

| Place | What it shows of the AI's work | What it leaves out |
|---|---|---|
| Decisions, and the page of a request | The requests that were made, with the AI's reasons | A finding that was dropped, held back or left for a person; what the AI examined |
| Runs and findings | The latest findings of the Watch | What the tools read, why the investigation stopped, how much of the bill it looked at |
| History, Savings found | Counts and money by what became of a finding | The AI's own account |

## What is kept

One record for each investigation that was tried (not one that was switched off, and not one for an app that has no store). It is written when the investigation ends, in the one table `mninvestigations` (partition `i`, a key that sorts the newest first). A write that makes the twenty-first row deletes the oldest, so twenty are kept. The table is made by the first write, like the others, and no read makes it. A run from before this change has no record, and the page says "Not recorded for earlier runs", never zero.

| What | Where it comes from |
|---|---|
| When it began, what started it (`timer`, or `request` for a person or a tool), the two models | The run |
| Calls made and allowed, tokens, seconds made and allowed | The run and the harness's budget |
| Why it ended: `answered`, `time`, `calls`, `refused` or `failed` | The answer's refused calls and its out-of-time flag, and whether the harness held the run |
| The Investigator's own phrases about what it examined (at most 12, each at most 100 characters) | The answer, cleaned |
| Each finding: its basis, proposal, how sure, how many resources, what they cost in 30 days, its sentence (at most 300 characters), the second AI's verdict and at most two objections (120 characters each), what code left out and why, and what became of its resources | The answer, the checks of code and the cases |
| The kinds of resource that the tools touched, and what they did to each (listed, measured, described, split) | The toolbox's log and its handles |
| The 30-day cost by kind of resource that the run read (the dearest 40) and the share that sits in the kinds that were touched | The cost lines that the Watch read, in US dollars |

**What became of a finding's resources** is one of: a request was made, the finding was left for a person (no request yet), it was dropped, or the request was held back for a reason that the History already has (managed by an automation, nobody looked up who changed it, the impact was not checked, nothing to say). The investigation counts them where it makes the case, so the page never works them out again.

**Size.** A usual record is about 5,000 characters. At its limits (twelve phrases and eight findings with every text at its longest, forty kinds) it is about 12,700, against the 30,000 that a table property of the store may hold. Text is cut by the size of its JSON form, so a character that JSON writes six characters long cannot make a record large. Tests pin both.

**What it never holds.** No name, tag, id or description of a resource. The AI's sentences are cleaned like every other text of an AI (no link, no figure of money), and then a subscription or resource id is replaced by "(id removed)" and any word that is the name of a resource that a tool showed in this run, by "(name removed)". A kind of resource is a word of the platform (`provider/type`), and a type that has a part that a customer chose is "other". The labels that the AI used inside a run (r1, r53) stay as written, and the page says in one sentence that they mean nothing outside the run.

**It never stops the Watch.** The writer is called when the investigation ends, whatever the way. A store that cannot be written, or a record that cannot be made, is one line in the log with the kind of the fault and never its text, and the run goes on.

## How "looked at" is counted

A kind counts as looked at when a tool that reads resources named it, or was given the handle of one of its resources, in a call that worked. The toolbox's tools that list, measure, describe or split do that; the tools that show the AI a list and no resource (the overview of the estate, the names of the metrics, Advisor, the plans, what is recalled) touch no kind. A kind that no handle and no cost line shows to exist is not counted, so a type that the AI made up does not raise the figure. A test fails when a tool of the toolbox is in neither list, so a new tool has to be put in one of them.

The share is the cost of the touched kinds divided by all the cost that the run read in US dollars. Cost that has no kind (a line with no resource, or a whole subscription) is in the divisor. A credit, a kind whose lines add up to nothing or less, is left out. A subscription whose cost was not read in dollars is not in either figure, and the tile says how many were read.

## What the page shows

A title and one sentence, three tiles and five blocks, in this order, from the parts of the style guide.

- **Tiles.** *Looked at in the last run*: the share, the number of kinds, and how it was counted. *Findings kept*: how many of the findings that the AI wrote passed the checks of code. *Stopped because*: the word, and the calls and seconds made of the allowed.
- **What the AI looked at and concluded.** When it began, what started it, the two models, and the phrases as a quote labelled "Written by the AI".
- **Findings of the last run.** A table: what the AI says, how sure it is, how many resources, what they cost in 30 days (always with the words "What they cost, not what could be saved": it is never a saving), the second AI's verdict, and what became of the resources.
- **Where the money goes and what the AI did with it.** The dearest 25 kinds of resource with their cost, their share, a mark "Looked at" (with what was done) or "Not looked at", and the number of open requests and open questions of that kind. An open request is a request that waits for a person's answer. An open question is a finding that nobody has been asked about yet. This is the table that answers "did it look at my biggest spend?".
- **Earlier runs.** The ten before it, one line each: when, tool calls, findings kept, share looked at, why it stopped. A run that investigated and has no record is a line that says so.
- **What this page cannot tell.** One paragraph: a phrase is the AI's own claim, "looked at" does not mean looked at deeply, and the costs are the 30 days that the run read.

## Who sees it, and what it says when it cannot read

A person needs the role ops or owner and gets the refusal of the standing permissions page without one; a person who is not listed gets the denied page. The navigation shows it to those two roles beside Savings found, the Operations page links to it, and only the role ops gets the link to "Every run and every finding". It is a GET and changes nothing. A store that cannot give the records is the plain "I cannot reach my records" page. A part that cannot be read (the findings for the open requests, or the runs for the lines "not recorded") is said in a notice and in its cells, and no number is given as complete: a read of 1,000 says "At least".

## One figure that rule 25 may not want

[Rule 25](../../AGENTS.md) says that a figure appears only as part of a case. The table of the money shows the cost of a kind of resource, with no resource, name or id, and at most twenty-five rows. It is there because "how much of the bill did the AI look at" cannot be answered without the bill as the divisor, and the page says that it is not a cost report and that Cost Management has the bill. If the owner reads the rule more strictly, the table and the share are the part to take out; the phrases, the findings and the reason a run ended stay.

## What is not proved

- It has not run against the real table, the real function app or a real estate. The table is made by the app's identity on the first write, which has not been tried.
- It has not been timed. An opening is a read of at most twenty records, the runs, the plans, and three statuses of up to 1,000 findings; a write is one upsert and at most one delete.
- The phrases are the AI's own claims and code did not check them. "Looked at" means that a tool read the kind, not that the analysis was deep, and a kind can be looked at in a call that returned nothing useful.
- The kind of a cost line comes from the type in its resource id. A line that a platform bills under another id than its resource shows under that type or under "other", and the share can be a little too low or too high for it.
- The open requests and questions are counted from at most 1,000 findings of each status, in separate reads, so for a busy store they are at least, and not a snapshot.
- A record is written when the investigation ends. A run that the platform kills in the middle leaves none, and the page then says that the newest investigation was not recorded.
- Twenty records are kept. The page shows the last ten earlier runs.

## What it costs

One small table in the storage account that the app has already, at most twenty rows of up to 13,000 characters, one write for each investigation (about one a week by the timer) and one read of the records for each opening of the page. No new resource, no new permission and no new call. The room that it takes in the upload package of the function app is in [the changelog](../../CHANGELOG.md).
