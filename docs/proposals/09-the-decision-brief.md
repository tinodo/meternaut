# The decision brief: one page, one letter, one answer — a decision record

**What this document answers.** Why every page and letter was rebuilt around one object, the decision brief; what a person sees now; how a finding that Meternaut may not change gets an answer; what was taken out and what is not done. A change is still made by the approver, with the approver's own rights ([run as the approver](05-run-as-the-approver.md)).

## The problem

The first pages and letters showed what was easy to show: runs, cases, switches, explanations of how Meternaut works, and the same request said three times. A stranger could not tell from one page what they were asked or what would happen if they said yes. A finding about a resource that Meternaut may not change had no plan, so a person could read it and could not answer it.

## The test

Every screen and message must let a stranger, who does not know the resource, answer these eight questions in under a minute, without opening anything else:

1. What am I asked to decide?
2. What do I get?
3. How sure is it, and on what evidence?
4. What exactly happens if I say yes, who does it, and with whose rights?
5. Can it be undone?
6. What could go wrong?
7. Whose resource is it?
8. What are my choices?

Anything that helps none of the eight leaves the default view: it sits under one Details disclosure, or on a page for the platform team.

## The decision brief

One object, made by code from a case, its plan and its action, in `src/case-functions/cases/brief.py`: pure functions, no input or output, no clock. The page, the letter and, later, the Teams card are renders of it, so the three say the same thing, and an answer is recorded once.

| Part | What it holds |
|---|---|
| Headline | A verb, an object and a place, written by code: "Delete the unattached disk disk-x in group rg-y". Never a model's sentence |
| Saving | A monthly figure in US dollars, what it is computed from, and its level (Verified, Expected or Scenario). Without a backed figure: "No figure" and why |
| Confidence | High, Medium or Low, derived by code from the second reviewer's verdict, the guards and how many cited numbers code re-checked |
| Facts | At most five rows (label, value with unit, source and period), chosen by code from the typed facts |
| Unread data, choices | For a finding about a workspace only: the method in one sentence, up to six rows of data that nothing reads, and three choices with what each puts at risk, all in code's words (below) |
| Group | For a finding that asks for a look at many resources: one case and one request. The headline says how many, of what kind and in how many groups, and names the first; the rows say what they cover, what they cost together and which they are (below) |
| Reasoning, doubt | The first AI's reason and the second AI's strongest objection, in labelled boxes marked as not checked by code |
| Change | What changes, who makes it (the approver, signed in to Azure, so Azure checks their rights) and what is read again just before |
| Undo, risk | Whether it can be undone and how; one sentence of what could go wrong, with a level |
| Owner | Who the resource probably belongs to, as plain facts from the tags and the Activity Log. A missing owner is said |
| Where, age | Group, kind of resource in words, one link to the Azure portal (web page only); "Found 3 days ago. Open until ...", with no urgency |
| Answers, footer | The choices that exist now for this person; one footer line: an AI wrote it and which models, why this person got it, whom to talk to (a name and an address as text) |

Text from the estate, from a tag, from a person or from a model passes one function, `plain()`, in every render: one line, no hidden or direction character, no Markdown link, no address with a scheme (it is split from its slashes), and a length limit. A link is made from an id, never from text. A mail or chat client may still turn a bare host name in such text into a link: that is a known limit, and the one link that matters, to the page of the decision, is made from an id. Tests put the worst texts into every field of every page, letter and card.

## What a person sees

- **Decisions**, the start page. "Waiting for you (N)": the larger saving first, then the oldest; each row has the headline, saving and level, risk, age and one button, Open. Below it, five one-line rows of what was decided lately.
- **A decision** (`/ok/<id>`; `/why/<id>` shows the same page). The headline, one sentence of saving, the facts, the two boxes of AI words, change, undo and risk, the owner, and one answer form. Everything else (steps, models, tokens, guards, ids, the log of the action) sits in one collapsed Details.
- **History**, "What happened": 30 days of decisions, changes made and checked, and the number of new findings each day. The old addresses of My decisions and What I did here answer with it.
- **Settings:** channel, quiet hours, the most messages a week, pause. **Operations**, for the platform team: the switches, the runs and cases, the permissions; moved from the start page, not extended.
- **Letters.** The decision letter (about 130 words): headline, saving and level, the top facts, change, undo and risk in a line each, the footer. The result letter: what was done, what it saved so far, how to undo it. The weekly letter: at most five waiting decisions, sent only when something waits. The first letter: three sentences. Each has one link, to the page of the decision (or the start page), no resource name or amount in its subject, and a plain-text copy.

The buttons Explain, Challenge and Teach became one answer, "Ask or tell": a text box for a question, an objection or something to remember. It is recorded with the person's name and approves nothing.

**An irreversible change asks twice.** A person once pressed the wrong answer and a delete ran after one press and the sign-in. Now "Approve and sign in to Azure" on a request whose undo says it cannot be undone (a delete) opens a second page first, "Confirm: <short title>": that this cannot be undone, what would be lost and where, and two buttons, "No, go back" (the main one, first) and "Yes, <delete> it and sign in to Azure". Nothing is recorded and nothing is changed before that second press and the sign-in. A change that can be undone (stop, resize, tier) and advice never ask, so the question keeps its weight. The one-time token and the note travel to the second page and come back with it. A person who posts the form with `confirm=yes` straight away skips the page; that is accepted, because the page guards against a slip and not against a client, and the token, the sign-in, the checks and the switches are unchanged.

## A finding that Meternaut may not change

Such a finding (outside the one group where a change may be made, or of a kind with no change) now gets a plan of the family `advise`. It changes nothing in Azure and uses the same plan code, one-time token, expiry (72 hours) and decision record as every plan.

| Answer | What is recorded |
|---|---|
| Worth acting on | The plan closes and the case becomes `acknowledged`, with the person's note |
| Not worth it | The plan and the case are declined, with a reason: still needed, the figure is wrong, already handled, other |
| This is not mine | The plan closes and the case goes back to needing a person |
| Ask or tell | The words, with the name; the plan stays open |
| Decide later | A snooze that only changes the order; the plan stays open |

A person named on the plan with the role owner or approver may answer it; a change still needs the role approver. The full stop switch holds "worth acting on", as it holds every approval; the other answers still go through. A request that nobody answered closes as expired, with no letter and no call to Azure. A finding that a person answered is not put to them again for 30 days. Advice gets no letter of its own: it waits on the page and in the weekly letter.

A person's time is the scarce thing, so code decides whether a finding is worth a request (`approvals.why_not_ask`, `ADVICE_MIN_USD`, `ADVICE_OPEN_MAX`). A finding that no measurement backs, that names no saving and whose resource cost under 50 dollars in 30 days gets no request: the first live Watch opened 49 such requests, 46 of them for private endpoints with the one doubt "missing telemetry, not measured inactivity", and each said "no figure". Only ten requests for findings that the AIs did not settle wait at the same time; a finding that both AIs agree on and that code re-checked is not held by that limit. What is not asked stays a case and an open question: the Investigator gets it again through `recall_open_questions`, a request is made when it is backed or a place is free, and the start page says in one sentence how many findings are held back, so that nothing is dropped silently.

`advise` never reaches Azure: the sign-in to Azure refuses an advise plan, the runner has no call for it, and a test pins that the two modules do not know the family.

Records stay readable: new fields have defaults and unknown fields are dropped. `CaseRecord.owner` is new: a dictionary with the keys `tagOwner`, `tagName`, `createdBy`, `createdAt`, `changedBy`, `changedAt` and `lookedUp`. Another part of the system has to fill it from the tags and the Activity Log; until then the page says that nobody has looked up the owner.

## Data that a workspace stores and nothing reads

The first live Watch found a workspace that stores billable tables that no rule, saved search, workbook or analytics rule names. Its page said "No figure", showed two numbers and the AI's one sentence, "Reduce diagnostic ingestion", and called the workspace "the resource". The owner asked what goes into the workspaces, whether all of it is used, which of it is not needed and how to filter it. The page now answers, and code writes every word and figure of the answer (`cases/unread.py`, `brief.py`). Advice still changes nothing in Azure.

| Part | What it holds |
|---|---|
| Instructions | The Investigator cites, for each kind of data that it names, both the volume and the readers. It says that nothing reads the data only where the tool that counts the readers said which sources it read: a source that could not be read is unknown, never none |
| Record | The tools keep what they showed beyond what was cited: the whole volume for the days asked, the volume and the readers of each kind (twelve at most), the kinds of resource of the largest writers of a kind on the last closed day, and what each table handle stands for (for a person's page, never for a model). Code reads that record |
| Figure | A Scenario: the cost of the workspace in the last 30 days times the share of its billed volume that sits in kinds of data with a verified count of zero readers and no query run, never above the cost, rounded to cents. The share is over the whole volume that the last read of the volume reported, for the days that it covered: rows that an earlier read of other days left in the record are not used, and rows with no whole volume (or more than it) make no figure. It is a typed fact of the case (`facts.unread`) and the advise plan takes it as its saving when the request is made; the case has no figure of its own, as for every change (`decide.py`). A page, letter or card shows the figure of the digest that the case holds now, the same numbers as the rows, so a Watch that judged the case again while the request waited cannot show an older figure beside new rows; the plan keeps the figure that it was made with, as the record. A kind whose readers could not be counted is in the whole volume and not among the unread. Where the audit of queries is off or was cut, the rows say "queries run: not recorded" and the kind still counts. Without the volume, or with no kind verified, there is no figure, and one sentence says which is missing |
| Evidence | The headline gives the type its word ("Consider changing the <type> ws-x in group rg-y": every type that has words in `TYPE_WORDS` gets its own, and the workspace was added; before, it read "the resource"). Then the method in one sentence ("About 52 percent of what this workspace is billed for is data that nothing reads"), and up to six rows, one for each kind: the GB in 30 days, its share of the billed volume, and what reads it (0 rules, 0 saved searches, 0 workbooks, 0 queries run) |
| What you could do | Three choices, each with what it puts at risk, ending "Nothing changes in Azure when you answer": stop sending the data at its source (the log categories of a diagnostic setting, or the collection rule that writes it); filter it in the transformation of the collection rule; keep it but cheaper (the Basic or Auxiliary plan for a table that is only searched now and then, or a shorter retention). The kinds of resource of the largest writers of the data are named only where a tool showed them |
| Letters, card | The weekly letter, when one decision waits, has the method, three rows and one line of choices; when several wait, one line each. The Teams card has the same in short. When something could not be counted (the queries that people run, or what reads some kinds), the page says it in a sentence, and the card and the letters in a few words ("Not counted: the queries people run."); a decision letter gives up its last rows for those words, and keeps its first |

What the choices say is kept to what [diagnostic settings](https://learn.microsoft.com/azure/azure-monitor/data-collection/diagnostic-settings) (they choose the categories that are sent), [data collection transformations](https://learn.microsoft.com/azure/azure-monitor/data-collection/data-collection-transformations) (a transformation drops rows or columns before they are stored; a workspace has one transformation rule, for data that no rule of its own sends), [table plans](https://learn.microsoft.com/azure/azure-monitor/logs/logs-table-plans) and [pricing](https://learn.microsoft.com/azure/azure-monitor/logs/cost-logs) (Basic and Auxiliary offer fewer query features and charge each query by the data it scans) and [retention](https://learn.microsoft.com/azure/azure-monitor/logs/data-retention-configure) say. The five pages were not read again when this was built (no network was used): the first run in Azure should read them again.

## A finding that covers many resources

The first live Watch made one case and one request for each of 60 private endpoints that had no traffic data: dozens of look-alike rows that no person can use, when the unit of the decision is the finding. Now a finding that asks for a look (the proposal investigate) and has more than five resources left after the checks of code is one case and one request ("60 private endpoints without traffic data, together 357 US dollars in 30 days: worth looking at?"). A delete or a change is never grouped, because each resource needs its own decision, and neither is a finding of five resources or fewer.

- **One case, owned by one resource.** It belongs to the dearest of the resources (the first of them when the cost is the same), so the link to the portal, a person's do-not-touch note, the quiet days after an answer and the open questions of the Investigator work on that resource. A Watch that finds the group again takes the case that it made before, even when the costs have moved, so that no second case and no second request are made while the first waits or was answered. The answers mean what they mean for one resource and are recorded on that case.
- **Which resources it stands for.** The case keeps the short ids of its resources, and their resource ids in lower case (at most 200) for its daily cost, which is the sum of theirs. A case that was judged lately stands for a later finding only when it stands for at least 80 percent of that finding's resources, whether or not the resource that the case belongs to is one that the finding names (the Investigator's lists differ from run to run, and the dearest resource may be missing from one); the resources that it does stand for are not asked about again, and the others are a group of their own, whose first resource is the dearest of them. So a later finding that names the first resource of an old group together with six new ones of 500 US dollars each reaches a person.
- **Do-not-touch.** A resource that a person marked do-not-touch is never one of a group: it is left out before the group is made, and the case says how many. A mark on the dearest resource does not silence the group, which then belongs to the next one. When five or fewer resources that nobody marked are left, each is a case as ever, and a marked one gets no request. A mark on the first resource of a group that was judged lately holds nothing back until the days of the recheck have passed. The marks are read before the agents run: when they cannot be read, the investigation does not run, nothing is spent, and the History says so.
- **What is at stake.** The cost of the case is what all of them cost. It has no figure of its own, and the rule of a request is the same as for one resource: with no measurement behind it and under 50 US dollars together, no request is made and the case stays an open question.
- **Still per resource.** A resource that a guard holds is not part of the group, the resources that no measurement backs are counted one by one, and the status comes from the first AI's confidence and the second AI's verdict as for any resource. The cap of 60 cases a run counts resources, and a group that it cut says in its first row how many more it left out.
- **The older requests.** The first version asked about each resource of such a finding on its own, and those requests were still open when the request of the group was made (49 of them, on the first real run). After the investigation the Watch closes the open advice requests for the other resources of a group whose request is open, as expired, since they only ask the same question again, and the History says how many. A request that a person answered, put off or asked about, the request of a change and the request of another group are never closed, and neither is anything when the request of the group is not open. The closed requests end at the time of closing. An advice that nobody answered is no row of "Recently decided" any more (a change that nobody answered is), and the History says "Closed with no answer: N requests to look at a finding" once a day.
- **What a person sees.** The headline says how many, of what kind and in how many groups, and names the first ("Look at 60 private endpoints in 14 groups, the first is pe-60"). The rows say what it covers ("60 private endpoints in 14 resource groups", and "and 10 more that the limit of one run left out" when the cap cut it), what they cost together and which they are ("pe-60, pe-59, ... and 54 more"). The weekly letter adds what they cost together. Nothing else on the page changes.

## What was taken out, and why

| Taken out | Why |
|---|---|
| The About paragraph, the list of what Meternaut can change, the switches, the runs and the cases on the start page | They answer none of the eight questions. The platform team has its own pages |
| "Check before you approve" and the forms with paragraphs of explanation | They said again what the page had just said |
| My decisions and What I did here as two pages | Two lists of the same records: now one History |
| Settings other than channel, quiet hours, weekly maximum and pause | Four are enough to start. The stored values stay |
| Banners, legal-sounding lines, how Meternaut works and repeated links in a letter | A letter read in a minute cannot carry them |
| Explain, Challenge and Teach as three buttons, and a link to a person | One answer and one footer line |

## What is not done

- **The Teams cards** are rebuilt from the same decision brief ([the Teams record](13-teams-and-outlook.md)): built and tested, not deployed. The older templates in [the web pages](../experience/06-web-pages.md) and the messages design still show three answer buttons and a link to a person.
- **The owner** is looked up for a case that the investigation opens (a tag of a closed set and the Activity Log: [the toolbox record](12-investigation-toolbox.md)); a case of the fixed detectors, the planted waste, has none, and the page says so.
- **The figure of data that nothing reads** assumes that the bill falls with the volume: a commitment tier on the workspace breaks that. It counts what the tools recorded (the twelve largest kinds of the last read of the volume, over the whole volume that the read reported), so a workbook that takes its workspace from a parameter is not counted, and the audit of queries holds only the 300 most run texts: when it returned all 300, a kind that none of them names has no count (unknown, not none) ([the toolbox record](12-investigation-toolbox.md)). It was not run in Azure: tests run it over a fake estate with the real tools. The weekly letter has the rows and the choices only when one decision waits.
- **Nothing learns from the answers yet.** They are stored; nothing reads them.
- **The cases of a group that older runs made one by one** stay as they were: their requests expire, and they stay open questions until a person answers them. A group whose dearest resource has left the finding gets a new case. A group of resources of different types is called resources, and a group of workspaces does not show the analysis of the data that nothing reads, which is the analysis of one workspace.
- **Forwarding a finding to its likely owner** is not built; it needs the owner's word on contacting people outside the list.
- **The link to the Azure portal** is `https://portal.azure.com/#resource` and the resource id, made only from an id of the shape of one resource. The portal's documentation also shows a shape with the directory in it. Neither was tried against the real portal.
- **The check in a browser after the deployment** needs the deployed page.
