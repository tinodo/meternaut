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
| Reasoning, doubt | The first AI's reason and the second AI's strongest objection, in labelled boxes marked as not checked by code |
| Change | What changes, who makes it (the approver, signed in to Azure, so Azure checks their rights) and what is read again just before |
| Undo, risk | Whether it can be undone and how; one sentence of what could go wrong, with a level |
| Owner | Who the resource probably belongs to, as plain facts from the tags and the Activity Log. A missing owner is said |
| Where, age | Group, kind of resource in words, one link to the Azure portal (web page only); "Found 3 days ago. Open until ...", with no urgency |
| Answers, footer | The choices that exist now for this person; one footer line: an AI wrote it and which models, why this person got it, whom to talk to (a name and an address as text) |

Text from the estate, from a tag, from a person or from a model passes one function, `plain()`, in every render: one line, no hidden or direction character, no Markdown link, no address that a client would link, and a length limit. A link is made from an id, never from text. Tests put the worst texts into every field of every page, letter and card.

## What a person sees

- **Decisions**, the start page. "Waiting for you (N)": the larger saving first, then the oldest; each row has the headline, saving and level, risk, age and one button, Open. Below it, five one-line rows of what was decided lately.
- **A decision** (`/ok/<id>`; `/why/<id>` shows the same page). The headline, one sentence of saving, the facts, the two boxes of AI words, change, undo and risk, the owner, and one answer form. Everything else (steps, models, tokens, guards, ids, the log of the action) sits in one collapsed Details.
- **History**, "What happened": 30 days of decisions, changes made and checked, and the number of new findings each day. The old addresses of My decisions and What I did here answer with it.
- **Settings:** channel, quiet hours, the most messages a week, pause. **Operations**, for the platform team: the switches, the runs and cases, the permissions; moved from the start page, not extended.
- **Letters.** The decision letter (about 130 words): headline, saving and level, the top facts, change, undo and risk in a line each, the footer. The result letter: what was done, what it saved so far, how to undo it. The weekly letter: at most five waiting decisions, sent only when something waits. The first letter: three sentences. Each has one link, to the page of the decision (or the start page), no resource name or amount in its subject, and a plain-text copy.

The buttons Explain, Challenge and Teach became one answer, "Ask or tell": a text box for a question, an objection or something to remember. It is recorded with the person's name and approves nothing.

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

`advise` never reaches Azure: the sign-in to Azure refuses an advise plan, the runner has no call for it, and a test pins that the two modules do not know the family.

Records stay readable: new fields have defaults and unknown fields are dropped. `CaseRecord.owner` is new: a dictionary with the keys `tagOwner`, `tagName`, `createdBy`, `createdAt`, `changedBy`, `changedAt` and `lookedUp`. Another part of the system has to fill it from the tags and the Activity Log; until then the page says that nobody has looked up the owner.

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

- **The Teams cards** and their templates (in [the web pages](../experience/06-web-pages.md) and the messages design) still show three answer buttons and a link to a person. They will be rebuilt from the same decision brief.
- **The owner is not looked up yet:** until something fills `CaseRecord.owner`, every page says so.
- **Nothing learns from the answers yet.** They are stored; nothing reads them.
- **Forwarding a finding to its likely owner** is not built; it needs the owner's word on contacting people outside the list.
- **The link to the Azure portal** is `https://portal.azure.com/#resource` and the resource id, made only from an id of the shape of one resource. The portal's documentation also shows a shape with the directory in it. Neither was tried against the real portal.
- **The check in a browser after the deployment** needs the deployed page.
