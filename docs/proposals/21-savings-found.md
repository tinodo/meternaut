# Savings found: every saving that Meternaut has found, added up by what became of it — a decision record

**Status: decided on 2026-11-16, built and tested against fakes, not deployed.** The page is `/ops/savings`, for the roles ops and owner. It is read-only, it shows counts and money and nothing from an estate, and it adds no new part to the [style guide](../ui/style-guide.html). Until the function app that carries it is published, nothing here runs.

## The owner's words

The owner asked: "Can meternaut show all the savings it has found?" Nothing did. He was told so, and chose to have it built. This record says what the page shows, what it counts and why it leaves out what it leaves out, who sees it, and what is not proved.

## What was missing

| Page | What it adds up | What it leaves out |
|---|---|---|
| Decisions | The open decisions that the signed-in person may answer ("Ready to save"), and "Saving measured" over that person's changes among the latest 60 requests | What was decided, and every other person's changes |
| Runs and findings | Nothing: it lists the latest 100 findings, each with its saving | A total, and what became of each finding |
| History | Counts of the findings of each day | Money |

## What the page shows

A title and one sentence, three tiles and one table, built from the parts of the style guide and nothing else. The guide allows at most three tiles.

| Tile | What it says |
|---|---|
| Found in all | A year, how many findings it rests on ("8 findings", or "8 of 10 findings have a saving figure" when some have none), and the levels in it (Scenario, Expected, Verified), weakest first. The levels are added in the tile the way the Decisions page adds "Ready to save"; the table keeps them apart |
| Waiting for a person | The same, for the first row |
| Saving measured | What Cost Management confirmed after changes, a year and a month, and after how many changes, over every person's changes. The Decisions page shows the same tile over the changes of one person, from the same code |

The table has a row for each of eight groups, in the order of what happens to a finding: waiting for a person (needs a person, proposed, waiting for an OK; the findings that are held back, which no request waits for yet, are here too), being made (approved, running), made and not yet confirmed (done), confirmed by Cost Management (verified), worth acting on (acknowledged), declined or expired, dropped, and could not be finished (error, failed). Its columns say what became of it, how many findings, the saving a year, and how many findings have no saving figure and why. *Since 2026-11-17* a finding that a guard holds back and that has a held request has a row of its own, "Found, and held back from a request", after the first, with a section below the table (a heading for each reason and one line for each finding), and "Found in all" says how many of its findings are held back ([proposal 29](29-held-findings.md)).

## What it counts, and what it leaves out

- **Each finding once.** A finding is one record whose id is made from the kind of finding and the resource, so a later search updates it, and one resource can be the subject of two findings of different kinds. Its status is its state now. A record is in the one row of its status, and the counts add up to the number of findings that were read.
- **Added up:** the first five rows. **Counted and not added:** declined or expired (nothing changed), dropped (the AIs advised keeping the resource) and could not be finished. Their cells say that no saving is claimed for them, and the page does not work out a figure for them at all. The note under the table says so too.
- **Levels apart.** A row has one line for each level that is present, weakest first, each with its month and its basis ("Based on …", or "the figures of each, added up" when the findings of that level are based on different things). A line never mixes levels, so no figure of Scenario is ever read as one of Verified. The figure of a finding that states its change follows the same rule: Expected when the change removes everything that the named meters bill, Scenario for the other forms, and the low end of a range is the one that is added ([proposal 24](24-priced-findings.md)).
- **Confirmed means measured.** The saving of a confirmed finding is the one that Cost Management confirmed after the change, the figure of the change and not the one that was expected when it was proposed. When the change is not among the plans and changes that the page read, the finding shows its own figure with its own level, never called Verified.
- **A change that changed nothing claims nothing.** When the resource of an approved change was already gone or already as wanted, nothing was written, the finding stays "made" for good and is never checked. The page counts it in its row with no saving figure and the reason that the page of the request gives ("Nothing was changed, so no saving is claimed for this approval."), and it is not in "Found in all".
- **A cost is not a saving.** A finding with a cost and no saving figure, and a finding with nothing, are counted with the reason that the figures code or the page of the request gives ("the most that a change could save: what it would save was not worked out", or what Azure has or has not reported). The page never adds a cost up and never shows one: Meternaut is not a cost report ([rule 25](../../AGENTS.md)).
- **Money** is in US dollars, a year is twelve times the month, and a saving is an estimate until Cost Management confirms it. Every saving carries its basis and one of the three levels ([rule 13 (c)](../../AGENTS.md)).

## Who sees it

A person needs one of the roles ops and owner, and gets the refusal of the standing permissions page without one. A person who is not listed gets the denied page. The navigation shows the page to those two roles only, the Operations page links to it, and a person with the role ops gets a link to "Every run and every finding"; an owner without that role does not, because that page is for ops alone. No message links here. It shows no resource name, no id, no person and no text from an estate or from a model, and it is a GET that changes nothing.

## What it reads, and what it says when it cannot read

For each status it reads at most 1,000 findings, and it reads at most 1,000 plans and 1,000 changes for the confirmed figures; the table service gives no more in one read. A status that holds that many says "at least", and so do its money and the tiles that rest on it (a plus after the figure, and "Not complete: there may be more."). A source that cannot be read is said in a notice that adds that nothing changed; its row says "Cannot be read now" (or "At least" and "Part of it cannot be read now" when only one of its statuses failed, and then the counts of its findings with no saving figure say "At least" too), and a tile that rests only on sources that failed shows a dash. "Saving measured" needs the plans and the changes both, so it shows a dash when either cannot be read. No number is given as complete when it was not.

## What is not proved

- It has not run against the real table, the real function app or a real estate. The table service gives the first 1,000 rows of a status in the order of its keys, not the newest, so a status above 1,000 shows a part that is not chosen by age.
- Working out a finding takes about a millisecond on a loaded machine, so a store at every limit (eight statuses of 1,000 findings that are worked out; the other five are only counted) takes seconds. It has not been timed on the function app.
- A finding that was confirmed and later came back as a new finding is in the row of its status now. Its confirmed change still counts in "Saving measured" and not in "Found in all", which counts the finding where it is now. Two confirmed changes of one finding are two changes in "Saving measured" and one finding in its row, which shows the newest, so the tile can be larger than the row; the note under the table says so.
- Each opening is fifteen separate reads, not a snapshot, so a finding that changes status while they are made can be counted twice or not at all. The count is exact for a quiet store.
- Two findings about the same resource, of different kinds, can hold savings that overlap or exclude each other (delete or resize). The page adds each finding's figure as it is, as the Decisions page does, so a total can be larger than what could be saved at once.
- "Saving measured" is what the check after a change found in the cost lines of whole days. Whether the total is what the bill shows has not been compared.

## What it costs

Fifteen reads of the tables that the app has already (thirteen statuses, the plans, the changes) for each opening of the page, and no new resource, no new permission and no new call. The room that it takes in the upload package of the function app is in [the changelog](../../CHANGELOG.md).
