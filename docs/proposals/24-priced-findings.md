# Priced findings: a saving that code works out from the bill lines that a finding names — a decision record

**Status: decided on 2026-11-17, built and tested against fakes, not deployed.** Until the function app that carries it is published, nothing here runs. Nothing was changed in Azure, and no model saw a real estate for this change.

## What was asked

A finding that proposes a change must carry a saving that code computes from the real bill, never an amount that a model wrote ([rules 26 (d) and 30](../../AGENTS.md)). The first version could price only two things, each by a module of its own: the data that a workspace stores and nothing reads, and the gateways that carry more scale units than anybody uses. Everything else that the Investigator found had no figure, or the whole cost of the resource, which is the saving of a deletion and of nothing else. An independent read of a real estate, made for this record and not kept in it, showed what a good finding says and what the first version could not express:

- everything that it would remove goes away, and nothing remains (the meters of the named resources);
- a count or a size is reduced, so a part of the bill goes away and the rest stays;
- a resource is needed on some days only;
- the figure rests on the AI's own assumption, which must be said and never widened;
- a switch to something else that a public price list prices (not built: a seam is left);
- a group of resources is priced as the sum of its resources, each by its own meters, counted once;
- some bill lines belong to no resource, and some resources have no bill line that the tool could find: the finding says so and keeps the figure out.

## What the Investigator states

Each finding may hold one block, `change`. It is typed, and code reads it strictly:

| Part | What it holds |
|---|---|
| `action` | One of `remove`, `reduce`, `switch`, `schedule`, `commit`, `none`. `none` is what the Investigator gives when it cannot name the meters |
| `effects` | One for each resource that the change covers: `handle` (a handle that the finding has), `meters` (the meter handles that `cost_meters` showed for that resource itself) and `remains` |
| `remains` | What is left of those meters, in one of four forms (below) |
| `how` | What a person would do, in plain words, at most 300 characters, cleaned like every text of an AI. It is shown to a person in a box that says that no code checked it, and no model is ever given it |

| Form | What the AI states | What code checks | Level |
|---|---|---|---|
| `none` | Nothing: everything that the meters bill goes away (the action `remove`) | Nothing is left to check: the figure follows from the bill | Expected |
| `ratio` | The name of a property or a measurement, the number that a tool returned for it (`from`), and the number after the change (`to`) | `from` is a number that a tool returned for that resource in this run (a property, or the total, the highest value, the average or a recorded total of a measurement); `to` is below `from` and not negative. The share that goes away is `1 - to / from` | Scenario |
| `share_of_days` | `days` of every `of` (whole numbers, at most 31), for a resource that is needed on some days only | Whole numbers and `days < of`. The share that goes away is `1 - days / of` | Scenario |
| `assumed` | `low` and `high`, the smallest and the largest share that stays billed | `0 <= low <= high <= 1`. Never widened: one value is a range of one | Scenario |
| `alternative` | A switch to something that a public price list prices | Refused with the plain reason "a switch to an alternative is not available yet". A later change adds the price list behind this form and nothing else here changes | none |

An action goes with some forms only (`remove` with `none`, `reduce` with `ratio` or `assumed`, `schedule` with `share_of_days` or `assumed`, `switch` with `alternative` or `assumed`, `commit` with `assumed`), and a pair that does not fit is refused.

## What code does with it

`cases/pricing.py` is one module that reads nothing and writes nothing (it imports the standard library, `meters.py` and `roles.py`, which import nothing else). For each resource of a finding:

1. **The meters count only when they are real.** A handle must be in the register of the run (`Toolbox.meters`), it must be a meter of that resource (never the meter of a whole type: a type's meter is the bill of many resources), it must have been read over the full 30 closed days, and it must have cost something. A meter that fails any of these is left out and counted, and the figure says so. The register keeps the longest window that was read for a meter: a later, shorter read of the same bill line shows the same handle and does not replace it.
2. **A bill line counts once.** Two calls that showed the same meter, and a handle named twice, are one line.
3. **The saving is arithmetic.** The cost of the counted meters times the share that goes away, as a low and a high, and never above what the resource cost in the last 30 days. A cost that is not in US dollars gives no figure, and says so.
4. **The point is the low end.** The number that a case counts and the Savings page adds is the low end of the range, so a figure that rests on an assumption is not taken for more than the assumption's cautious end. The range is said in words beside it.
5. **A group is the sum of its resources.** A finding about many resources is one case; its figure is the sum of the figures of the resources that have one, each by its own meters, and the basis says how many of how many are priced.
6. **Azure Advisor's figure stays beside it.** When a tool showed an Advisor item for the resource, the digest keeps Advisor's own estimate next to the figure and the basis says that the two are not added. A case that holds what Advisor says and nothing from this path keeps Advisor's figure, as before ([proposal 22](22-advisor-first-class.md)).
7. **A change that cannot be priced says why, and keeps the figure out.** The words are fixed sentences that start "No saving was worked out:" (the AI did not name the bill lines, they were not found for this resource over 30 days, what remains was not stated in a form that code can check, the cost is not in dollars, the lines cost nothing, a switch is not available yet). A finding that asks to delete a resource and states a change that cannot be priced has no figure at all: the cost of the resource is not offered as its saving. A finding that states no change, or states the action `none`, is priced as it always was (a delete is worth the cost lines of the resource; a look has no figure).

A bill line that no resource owns has no meter handle, so it cannot be named; the finding then has no figure, and the sentence says why ("a bill line that no resource owns has no handle to name").

## What the second AI is shown

The Skeptic is given the model, in typed form, for the resources that are cases of this run (a resource that a guard took out, that was judged lately or that the cap of cases left out is not shown, because it has no rows of evidence): the action; for each resource the rule (`none`, `ratio` with `from`, `to` and the name of what is scaled, `share_of_days` with `days` and `span`, `assumed` with the range of what remains), what the counted lines cost, and the lines (the meter handle, its six words, what it cost, the days that had a cost and how much the daily cost varies); or, for a resource with no figure, the word that says why. The words of a meter pass the same check as in the answer of the tool that showed them, so a word that the owner of an estate could have written is shown as "other". It is not given `how`, any name, or the arithmetic: it judges the model ("Does every line scale with the change that is proposed? Does what remains follow from the evidence rows? Would a smaller size still carry the highest value that the rows show?"). A Skeptic that doubts the model says disagree or unsure, and the finding then needs a person; the figure is kept, and the page says that the second AI doubted.

## What the general instructions say

No kind of resource, no metric and no number is named (rule 30). The Investigator is told to state the change and what remains of the meters, in the four forms, and never to write an amount. It is also told the second kind of waste: for anything that comes in a size, a tier or a number of units, compare what it can carry with the highest value of what it carries, read at the finest grain that its tools offer and not as an average, and say what the next smaller option would still have to carry and what would then remain on the bill. An average can hide the peak that decides what a thing must carry. A principle says what to compare and what to say, never what counts as waste: an earlier wording that said what a low peak is was cut for that reason. The next smaller option is a `ratio` change: the AI proposes the number, and code checks the current one.

## What was retired

`cases/unread.py` and `cases/gateways.py` priced two kinds of resource by rules written for them, and `brief.py`, `cards.py`, `letters.py`, `web/brief_page.py` and `approvals.py` carried blocks written for them. They are gone, with their tests. What each gave a person, and what is left of it:

| Was | Is |
|---|---|
| A figure for a workspace: its cost times the share of its billed volume in kinds of data that nothing reads | The same finding states a `remove` or a `reduce` over the meters that are billed for that data, and code prices those meters. The share is no longer worked out from the volume of each kind: it is what the named meters cost |
| A figure for gateways: the cost times the share of scale units that would go if each were the smallest size of Microsoft's table that carries the most connections seen | A `ratio` change on the number of scale units, from the number that the tool showed to the number that the AI proposes. Code no longer holds Microsoft's table, so that the smaller size carries the peak is the AI's claim and the Skeptic's to judge, and not code's. The family `scale-vpn-gateway` is unchanged ([proposal 14](14-families-of-change.md)) |
| Rows of evidence, one for each kind of data or each gateway, from the toolbox record | The evidence rows that every finding has (the measurements with units and days) and the line "Bill lines it would shrink" |
| Two or three choices with what each puts at risk, in code's words | The AI's own words for a person (`how`), in a box that says that no code checked them |
| A block in the weekly letter and the Teams card | The line of the figure with its level and basis, as for every finding |

The record that the data tools keep (`evidence["volume"]` and `["writers"]`) has no reader now beyond the citation check and is left in `cases/toolbox.py`; `Toolbox.table_names` and `capacity.smallest_for`, which only a test used, are deleted.

## What it changes for a person

The decision brief, the card, the letter and the Savings page show the figure that code worked out, its level (Expected for `remove`, Scenario for every other form) and what it rests on in words ("the 2 bill lines of 1 resource that the change would shrink, over the last 30 days, scaled by the change in units from 12 to 4: the AI's target"; a group says "40 of 60 resources", and the longest sentence that a figure can have is 290 characters, so that a card, which cuts a line at 300, shows all of it). Levels are never mixed ([proposal 21](21-savings-found.md)). The page of a finding that states a change has one more fact, "Bill lines it would shrink", and the box "What the AI says a person would do (not checked by code)". A figure never switches off a check: the verdict that code made of what depends on a resource, the question whether it is still used and the risk of acting on it are what they are with a figure and without one. A case that holds a change is worth what its own record says now (its price, or why it has none), never the figure that its plan was made with.

## What is not proved

- **No real run.** Tests use fakes and invented data, including the real tools over a fake estate. Whether the real Investigator states the block well, names the meters of the right resource, and reads them over the full window has not been seen. A finding whose block is wrong gets no figure, not a wrong one, and says why.
- **The Skeptic's judgement of the model was not tried on a model.** The instruction and the input are pinned by tests; what the second AI does with them is not.
- **A group costs calls.** To price a group by each resource's own meters, the Investigator has to ask `cost_meters` for each resource, which spends calls of its budget. A group in which only some resources were read is priced for those, and says how many.
- **A `ratio` proves the current number and not the target.** Code checks that `from` is what a tool returned; that `to` is a size that still carries the load is the AI's proposal and the Skeptic's to judge.
- **The point is the low end.** The Savings page adds the low end of every range, so a total is cautious by construction; a person who wants the range reads it in the basis.
- **A group's figure trusts its own digest.** `saved()` checks a single resource's figure against the cost of the resource, and a group's against the bill lines that it rests on, not against the sum of the costs of its resources (some have no cost line). The digest is made by code and kept in the private store; a check against the sum was left out.
- **Azure Advisor and the model are counted once.** A resource that Advisor lists and the investigation priced is one case that holds both digests, and Advisor's own case for it is closed (tests with invented data: `test_advisor_parity.py`).
- **The meters are the 30 closed days that `cost_meters` shows.** A cost that moved inside the window (a resource made or changed in it) is averaged by the arithmetic; the daily shape that the Skeptic sees says how steady it was.
- **A meter that belongs to a type and not to a resource** cannot be priced for a resource, by design: the bill lines of a type are the sum of its resources.
- **The `alternative` form is a seam.** Nothing prices a switch yet.
- **What the tests pin.** The rules above were mutation-checked one at a time: the ownership of a meter, the 30-day window, counting a line once, the cap at the cost, the table of actions and forms, the check of the cited number, each bound of a ratio, a share of days and an assumption, the low-end point, the level of each form, the refusal of a delete whose change failed, Advisor's figure beside and never added, what the Skeptic is shown and not shown, the sum of a group and how many are priced.

## What it costs

No new call, resource or permission. The Investigator's instructions grew by about 2,700 characters (to under 9,000), which is the one cost in tokens: every step of an investigation reads them again. The room that the change takes in the upload package of the function app is in [the changelog](../../CHANGELOG.md).
