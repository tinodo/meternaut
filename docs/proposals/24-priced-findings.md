# Priced findings: a saving that code works out from the bill lines that a finding names — a decision record

**Status: decided on 2026-11-17, built and tested against fakes, not deployed.** Until the function app that carries it is published, nothing here runs. Nothing was changed in Azure, and no model saw a real estate for this change. The base of the figure (a month at the rate of the last 7 days, not the sum of the last 30) and a fifth form, `quantity`, were decided the same day: [the last section](#priced-at-what-it-costs-now-and-a-change-stated-in-the-quantity-of-a-meter) says how, and where it differs from what is written above it, it is the later word. The form `alternative`, which was a seam here, is built and described in [proposal 28](28-alternative-prices.md#the-form-alternative-a-switch-priced-by-code).

## What was asked

A finding that proposes a change must carry a saving that code computes from the real bill, never an amount that a model wrote ([rules 26 (d) and 30](../../AGENTS.md)). The first version could price only two things, each by a module of its own: the data that a workspace stores and nothing reads, and the gateways that carry more scale units than anybody uses. Everything else that the Investigator found had no figure, or the whole cost of the resource, which is the saving of a deletion and of nothing else. An independent read of a real estate, made for this record and not kept in it, showed what a good finding says and what the first version could not express:

- everything that it would remove goes away, and nothing remains (the meters of the named resources);
- a count or a size is reduced, so a part of the bill goes away and the rest stays;
- a resource is needed on some days only;
- the figure rests on the AI's own assumption, which must be said and never widened;
- a switch to something else that a public price list prices ([built in step two of proposal 28](28-alternative-prices.md#the-form-alternative-a-switch-priced-by-code));
- a group of resources is priced as the sum of its resources, each by its own meters, counted once;
- some bill lines belong to no resource, and some resources have no bill line that the tool could find: the finding says so and keeps the figure out.

## What the Investigator states

Each finding may hold one block, `change`. It is typed, and code reads it strictly:

| Part | What it holds |
|---|---|
| `action` | One of `remove`, `reduce`, `switch`, `schedule`, `commit`, `none`. `none` is what the Investigator gives when it cannot name the meters |
| `effects` | One for each resource that the change covers: `handle` (a handle that the finding has), `meters` (the meter handles that `cost_meters` showed for that resource itself) and `remains` |
| `remains` | What is left of those meters, in one of five forms (below) |
| `how` | What a person would do, in plain words, at most 300 characters, cleaned like every text of an AI. It is shown to a person in a box that says that no code checked it, and no model is ever given it |

| Form | What the AI states | What code checks | Level |
|---|---|---|---|
| `none` | Nothing: everything that the meters bill goes away (the action `remove`) | Nothing is left to check: the figure follows from the bill | Expected |
| `quantity` | `from` and `to`, how much of one billed meter is used before and after the change, in the meter's own unit and over the same window | The effect names one meter, which is the resource's own, and `from` is that meter's own quantity as `cost_meters` showed it (to a hundred-thousandth, because the tool shows six significant digits); `to` is below `from` and not negative. The share that goes away is `1 - to / from` | Scenario |
| `ratio` | The name of a property or a measurement, the number that a tool returned for it (`from`), and the number after the change (`to`) | `from` is a number that a tool returned for that resource in this run (a property, or the total, the highest value, the average or a recorded total of a measurement); `to` is below `from` and not negative. The share that goes away is `1 - to / from` | Scenario |
| `share_of_days` | `days` of every `of` (whole numbers, at most 31), for a resource that is needed on some days only | Whole numbers and `days < of`. The share that goes away is `1 - days / of` | Scenario |
| `assumed` | `low` and `high`, the smallest and the largest share that stays billed | `0 <= low <= high <= 1`. Never widened: one value is a range of one | Scenario |
| `alternative` | `price`, a price handle that the tool for alternatives showed for that meter (the action `switch`, one meter) | The price was shown in this run for that meter, of its service and unit, with one price for the whole quantity, and the list price of the meter's own line is known (else it is not priced). The share that remains is the alternative's list price times the rate that the bill pays against list, over what the bill paid for a unit (that is, over the list price of the meter's own line), and at list prices alone for the other end of a range: the same share at every rate; the digest also keeps the plain names of both ends (`now`, `to`), and a switch whose alternative cannot be named is not priced ([proposal 28](28-alternative-prices.md#the-form-alternative-a-switch-priced-by-code)) | Scenario |

An action goes with some forms only (`remove` with `none`, `reduce` with `quantity`, `ratio` or `assumed`, `schedule` with `share_of_days`, `quantity` or `assumed`, `switch` with `alternative` or `assumed`, `commit` with `assumed`), and a pair that does not fit is refused.

## What code does with it

`cases/pricing.py` is one module that reads nothing and writes nothing (it imports the standard library, `meters.py` and `roles.py`, which import nothing else). For each resource of a finding:

1. **The meters count only when they are real.** A handle must be in the register of the run (`Toolbox.meters`), it must be a meter of that resource (never the meter of a whole type: a type's meter is the bill of many resources), it must give a rate (a read of 7 days or more, and 3 days of cost at least: below), and it must have cost something. A meter that fails any of these is left out and counted, and the figure says so. The register keeps the longest window that was read for a meter: a later, shorter read of the same bill line shows the same handle and does not replace it.
2. **A bill line counts once.** Two calls that showed the same meter, and a handle named twice, are one line.
3. **The saving is arithmetic.** What the counted meters cost a month now, at the rate of the last 7 days and at the mean since they began (below), times the share that goes away, as a low and a high, and never above what the resource costs a month on the same rates. A cost that is not in US dollars gives no figure, and says so.
4. **The point is the low end.** The number that a case counts and the Savings page adds is the low end of the range, so a figure that rests on an assumption is not taken for more than the assumption's cautious end. The range is said in words beside it.
5. **A group is the sum of its resources.** A finding about many resources is one case; its figure is the sum of the figures of the resources that have one, each by its own meters, and the basis says how many of how many are priced.
6. **Azure Advisor's figure stays beside it.** When a tool showed an Advisor item for the resource, the digest keeps Advisor's own estimate next to the figure and the basis says that the two are not added. A case that holds what Advisor says and nothing from this path keeps Advisor's figure, as before ([proposal 22](22-advisor-first-class.md)).
7. **A change that cannot be priced says why, and keeps the figure out.** The words are fixed sentences that start "No saving was worked out:" (the AI did not say which charges on the bill the change would shrink, they were not found for this resource or have under 3 days of cost, what remains was not stated in a form that code can check, the cost is not in dollars, the charges cost nothing in the last 7 days, the alternative was not found as a price for the charge or its price changes with the quantity or Meternaut cannot name it in plain words, the units differ, the list price of the current meter is not known, the alternative costs as much or more, the charge has no cost per unit). A finding that asks to delete a resource and states a change that cannot be priced has no figure at all: the cost of the resource is not offered as its saving. A finding that states no change, or states the action `none`, is priced as it always was (a delete is worth the cost lines of the resource; a look has no figure).

A bill line that no resource owns has no meter handle, so it cannot be named; the finding then has no figure, and the sentence says why ("a bill line that no resource owns has no handle to name").

## What the second AI is shown

The Skeptic is given the model, in typed form, for the resources that are cases of this run (a resource that a guard took out, that was judged lately or that the cap of cases left out is not shown, because it has no rows of evidence): the action; for each resource the rule (`none`, `quantity` with `from`, `to` and the unit of the meter, `ratio` with `from`, `to` and the name of what is scaled, `share_of_days` with `days` and `span`, `assumed` with the range of what remains), what the counted lines cost a month at the lower of their two rates and at each of them, and the lines (the meter handle, its six words, what it cost in its window, what it costs a month at the rate of its last 7 days and at the mean since it began, its days of life, the days that had a cost and how much the daily cost varies over its life); or, for a resource with no figure, the word that says why. The words of a meter pass the same check as in the answer of the tool that showed them, so a word that the owner of an estate could have written is shown as "other". It is not given `how`, any name, or the arithmetic: it judges the model ("Does every line scale with the change that is proposed? Does what remains follow from the evidence rows? Would a smaller size still carry the highest value that the rows show?"). A Skeptic that doubts the model says disagree or unsure, and the finding then needs a person; the figure is kept, and the page says that the second AI doubted.

## What the general instructions say

No kind of resource, no metric and no number is named (rule 30). The Investigator is told to state the change and what remains of the meters, in the five forms, and never to write an amount. It is also told the second kind of waste: for anything that comes in a size, a tier or a number of units, compare what it can carry with the highest value of what it carries, read at the finest grain that its tools offer and not as an average, and say what the next smaller option would still have to carry and what would then remain on the bill. An average can hide the peak that decides what a thing must carry. A principle says what to compare and what to say, never what counts as waste: an earlier wording that said what a low peak is was cut for that reason. The next smaller option is a `ratio` change on a number that a tool showed for the resource, or a `quantity` change on a meter: the AI proposes the number, and code checks the current one.

## What was retired

`cases/unread.py` and `cases/gateways.py` priced two kinds of resource by rules written for them, and `brief.py`, `cards.py`, `letters.py`, `web/brief_page.py` and `approvals.py` carried blocks written for them. They are gone, with their tests. What each gave a person, and what is left of it:

| Was | Is |
|---|---|
| A figure for a workspace: its cost times the share of its billed volume in kinds of data that nothing reads | The same finding states a `remove` or a `reduce` over the meters that are billed for that data, and code prices those meters. The share is no longer worked out from the volume of each kind: it is what the named meters cost |
| A figure for gateways: the cost times the share of scale units that would go if each were the smallest size of Microsoft's table that carries the most connections seen | A `ratio` change on the number of scale units, from the number that the tool showed to the number that the AI proposes. Code no longer holds Microsoft's table, so that the smaller size carries the peak is the AI's claim and the Skeptic's to judge, and not code's. The family `scale-vpn-gateway` is unchanged ([proposal 14](14-families-of-change.md)) |
| Rows of evidence, one for each kind of data or each gateway, from the toolbox record | The evidence rows that every finding has (the measurements with units and days) and the line "Charges it would shrink" |
| Two or three choices with what each puts at risk, in code's words | The AI's own words for a person (`how`), in a box that says that no code checked them |
| A block in the weekly letter and the Teams card | The line of the figure with its level and basis, as for every finding |

The record that the data tools keep (`evidence["volume"]` and `["writers"]`) has no reader now beyond the citation check and is left in `cases/toolbox.py`; `Toolbox.table_names` and `capacity.smallest_for`, which only a test used, are deleted.

## What it changes for a person

The decision brief, the card, the letter and the Savings page show the figure that code worked out in one sentence ("Meternaut worked out that this could save about $1,682 a year ($140 a month).") and say what it rests on in the next one ("At the rate of the last 7 days this resource costs about $144 a month for what the change would remove. That comes from your bill." for `remove`, which is Expected, and "At the rate of the last 7 days this resource costs about $144 a month for what the change would shrink. The AI assumes that 30 to 60 percent of that would go away. That is the AI's own assumption, and Meternaut did not check it." for the form `assumed`, and for a quantity, a ratio and a share of days the sentences that say what the bill shows (with the days that the meter was read for), what the AI says that the change would do to it, and that Meternaut checked the first and not the second ([proposal 09](09-the-decision-brief.md#say-what-changes-and-what-an-answer-does-2026-11-20)), all of them a Scenario; a group says "40 of the 60 resources", and of a quantity the sum and what each has, of a number or a share of days "on each of them", and nothing of a quantity when its resources state different ones, and the longest sentence of what a figure rests on is under 840 characters (`stake.NOTE_CHARS`), so that a card, which cuts that line there, shows all of it). Levels are never mixed ([proposal 21](21-savings-found.md)). The page of a finding that states a change has one more fact, "Charges it would shrink", and the quote "What the AI says. Meternaut did not check the wording." A figure never switches off a check: the verdict that code made of what depends on a resource, the question whether it is still used and the risk of acting on it are what they are with a figure and without one. A case that holds a change is worth what its own record says now (its price, or why it has none), never the figure that its plan was made with.

## What is not proved

- **No real run.** Tests use fakes and invented data, including the real tools over a fake estate. Whether the real Investigator states the block well, names the meters of the right resource, and reads them over the full window has not been seen. A finding whose block is wrong gets no figure, not a wrong one, and says why.
- **The Skeptic's judgement of the model was not tried on a model.** The instruction and the input are pinned by tests; what the second AI does with them is not.
- **A group costs calls.** To price a group by each resource's own meters, the Investigator has to ask `cost_meters` for each resource, which spends calls of its budget. A group in which only some resources were read is priced for those, and says how many.
- **A `ratio` proves the current number and not the target.** Code checks that `from` is what a tool returned; that `to` is a size that still carries the load is the AI's proposal and the Skeptic's to judge.
- **The point is the low end.** The Savings page adds the low end of every range, so a total is cautious by construction; a person who wants the range reads it in the basis.
- **A group's figure trusts its own digest.** `saved()` checks a single resource's figure against the cost of the resource, and a group's against the bill lines that it rests on, not against the sum of the costs of its resources (some have no cost line). The digest is made by code and kept in the private store; a check against the sum was left out.
- **Azure Advisor and the model are counted once.** A resource that Advisor lists and the investigation priced is one case that holds both digests, and Advisor's own case for it is closed (tests with invented data: `test_advisor_parity.py`).
- **The meters are read over 7 to 30 closed days.** What this means for a cost that moved inside the window is in the last section.
- **A meter that belongs to a type and not to a resource** cannot be priced for a resource, by design: the bill lines of a type are the sum of its resources.
- **The `alternative` form was a seam and is built (2026-11-17, [proposal 28](28-alternative-prices.md#the-form-alternative-a-switch-priced-by-code)).** It is not proved that the rate of the bill carries over to another size.
- **What the tests pin.** The rules above were mutation-checked one at a time: the ownership of a meter, the 30-day window, counting a line once, the cap at the cost, the table of actions and forms, the check of the cited number, each bound of a ratio, a share of days and an assumption, the low-end point, the level of each form, the refusal of a delete whose change failed, Advisor's figure beside and never added, what the Skeptic is shown and not shown, the sum of a group and how many are priced.

## What it costs

No new call, resource or permission. The Investigator's instructions grew by about 2,700 characters (to under 9,000), which is the one cost in tokens: every step of an investigation reads them again. The room that the change takes in the upload package of the function app is in [the changelog](../../CHANGELOG.md).

## Priced at what it costs now, and a change stated in the quantity of a meter

**Decided on 2026-11-17, built and tested against fakes and with a read-only look at a real bill (no model), not deployed.** Where this section differs from the ones above, it is the later word.

### Why the 30 days are the wrong base

A saving is a figure a month about what is to come. The sum of the last 30 closed days says what was spent, and it is wrong exactly where it matters:

- A resource that is four days old has four days of cost in the window. If it costs 8 a day, the window shows 32 and the resource costs 240 a month.
- A resource whose rate rose or fell inside the window costs neither what it did at the start nor what it does now. The sum is in between.
- A resource that was shrunk or stopped lately is over-stated: the part that is already saved is counted again as a saving.

An independent read of a real estate used the rate of the last 7 closed days times 30 as its headline figure. Code can state that now, and the figure that a case counts rests on it.

### The rates of a meter

`cases/meters.py` works out, for each meter, from its daily cost (`rates`):

| Rate | How it is worked out |
|---|---|
| The last 7 days | The mean of the daily cost of the last 7 closed days, times 30. A day without a line counts as nothing. A meter that began later has only its own days, from the first day that has a cost |
| Since it began | The mean from the first day that has a cost to the last day, times 30. It is given for a meter that began inside the window, and for a meter that was already there when a window of 30 days began (then it is the cost of the 30 days). A read of 7 to 29 days of a meter that already cost on its first day cannot say it, because the meter may be older: no mean is claimed |
| A typical day | The median of the days that have a cost, times 30, when 3 or more days have one. A charge made once (a set-up) or a rise of the last days does not move a median, so it is the rate that a spike cannot inflate |

The fewest days that a rate rests on is 3. One day may be a part of a day, a charge made once or a bill that is late, and is not stretched into a month; a meter with fewer days of life has no rate, is not counted, and the finding says so. A read of under 7 days gives no rate. A meter that cost nothing in its last 7 days saves nothing at its rate now, and the finding says that.

The low end of a saving is worked out on the lowest of the three rates, the high end on the higher of the first two, and then the share of the form applies as before. The figure that a case counts is still the low end. So a rate that is rising or falling is shown, and counted at its cautious end: a meter whose cost halved in the last week counts what it costs now, and shows what it cost before as the high end. A meter that is a few days old and had a one-off charge (a first day of 100 and then 1 a day, over 3 days) is counted at 30 a month and not at the 1,020 that its mean of 3 days gives; the same spike on a meter of 20 days or of 30 days (178.50 and 129 on the mean) is counted at 30 as well. The first review of this work found that the 1,020 was counted and called Expected.

### The level follows from the bill alone

A removal is Expected only when it follows from the bill alone: no line of the figure is uneven (`UNEVEN`), and the lowest of the rates that the digest holds is at least three quarters of the highest (`DIFFER`). When a line is uneven or the rates differ by more, a removal is a Scenario, like every other form, and the sentence says why in plain words: "The cost of this resource has changed over the days that the figure counts, so the figure is less certain", or "1 charge is uneven from day to day, so the figure is less certain". A figure made before the rates holds none to differ and stays as it was.

### The cap, on the same basis

A saving is never above what the resource costs a month. The cap moves to the same rates. It is the sum of every meter of the resource that a tool showed in this run (a bill line once), on the lowest rates for the low end and on the higher rates for the high end. A credit takes off what it gave back in its window, scaled to a month by the days of that window, and never its rate of the last days: a refund of 20 once would otherwise read as 150 a month and wipe out a real saving. When the credits leave nothing of the lines that the finding names, the finding says that the credit is why there is no saving, and not that the lines cost nothing. Nothing is read for the cap: the meters are already in the register of the run, and a resource whose meters were not shown has no cap beyond its own meters. The cost of the resource in 30 days still bounds the figure, but loosely, because a rate can be much above a total over 30 days: at most 30 divided by the days of life of its youngest meter, and by 7 when no meter began inside the window. `saved()` reads the digest again with the same bound, and refuses a high above the lines that it rests on. A digest made before this change has no rates and is read as it was, bounded by the cost of the 30 days.

### What a person and the second AI are told

The digest holds the rates as numbers (`weekUsd`, `sinceUsd`, and `steadyUsd` when a typical day is the lowest), the days of life of the youngest meter that began inside the window (`life`) and how many of the lines are uneven (`uneven`). The sentence of the figure says which rate it is, as what the resource costs a month: "At the rate of the last 7 days"; "At the rate of the 4 days since it began" for one resource whose lines are all younger than a week; "At the lower of the rates of the last 7 days and the last 30 days" when the two differ by more than 5 percent (the lower is counted); "At the rate of a typical day" when a typical day is more than 5 percent under both. A digest made before the rates says "Over the last 30 days ... paid about ...". A figure that rests on lines whose daily cost spreads by more than their mean says so: "1 charge is uneven from day to day". The numbers, 5 percent, a quarter and a spread of 1 against the mean, are plain constants of `cases/pricing.py` (`ALIKE`, `DIFFER`, `UNEVEN`). They are statistics about a bill and say nothing about what is waste (rule 30). A line counts as uneven only when it carries at least a tenth of what the figure rests on (`MATERIAL`): a small line that jumps about does not make the figure rough. The fact "Charges it would shrink" shows what the lines cost a month at the lowest rate. The Skeptic is shown the same numbers for each line. The Investigator is told in one sentence that code works the saving out as a monthly rate from the latest days. Neither is told a threshold. The sentence of a figure can be long, so a card shows 840 characters of it and a letter 910 of its line, which holds the label and the month before it (`stake.NOTE_CHARS`, `stake.LINE_CHARS`): the longest sentence that a figure can have, a switch with both names at 40 characters and Azure Advisor's figure at its end, fits both, and a test holds that.

### The form `quantity`

The first real run of the whole stack showed what a ratio on a property cannot know. The Investigator stated a `ratio` on a number that a tool showed for a resource (4 units, to 2) and applied it to a meter that bills only the units above those that are included. The meter billed 1,440 unit-hours in 30 days for 201.60 (2 units for 720 hours), so the honest change from 2 extra units to none is 201.60. The ratio from 4 to 2 halved the meter and booked 100.80. A ratio on a property is right only when the meter follows that property, and code cannot know that.

So a fifth form works on what the bill measures, the quantity of one meter: `{"form":"quantity","from":..,"to":..}`. Code checks that the effect names one meter, that the meter is the resource's own, that `from` is that meter's own quantity as `cost_meters` showed it over the window (to a hundred-thousandth: the tool shows six significant digits, so a quantity with more digits is shown rounded), and that `to` is not negative and below `from`. The share that remains is `to / from`, and it is applied to both rates of the meter. The level is Scenario: the target is the AI's proposal, and the starting point is checked by code. It goes with the actions `reduce` and `schedule`. The `ratio` stays, because some meters do follow a property, and the instruction says to state a change in how much of a meter is used in the quantity of that meter. The unit of the meter is kept only when it passes the same check of a word of a meter that the tools make, and is plain words; the Skeptic is shown it, and the sentences say it as the bill gives it ("250 GB"), with a plain word of it such as Hour in lower case and with an s ("1,440 hours"): "The bill shows 1,440 hours of it in the last 30 days, and Meternaut checked that number against the bill. The AI says the change would lower that to 720 hours, which takes away 50 percent of it, and Meternaut did not check that.". The digest also keeps the days that the meter was read for (`read`, for the words "in the last 14 days") and, when the name of the meter passes the same check, that name (`charge`, for the title); neither goes to the Skeptic. A change that spans several meters is several effects, one for each meter, each with its own numbers: the row then says that its rules differ.

### What is not proved

- **No model saw this.** The tests use invented data. The read-only look at a real bill priced the same generic change for 23 resources and showed the counts below, but it did not run the Investigator, so whether the real AI states the quantity form well, and reads the meters over the longest window, is not seen. What the Skeptic does with the two rates is not seen either.
- **What the real bill showed.** Of the 20 resources that got a figure, the rate of the last 7 days differed from the 30 days by more than 10 percent for 9, by more than 25 percent for 6 and by more than 50 percent for 3; the counted figure moved by more than 25 percent for 5, and the counted figures of the 20 together fell by about a fifth. One resource that the 30 days priced at hundreds a month is under 20 a month at its last week. Six resources had a line that began inside the window. This is one estate on one day.
- **The first day of a new meter is usually a part of a day**, so the rate of a very young meter is a little low. That errs on the cautious side. The last closed day can also be incomplete for a meter whose bill is late; that is not corrected.
- **A quantity share is the share of the window.** `to / from` is applied to the rates, and when the quantity itself changed inside the window the share of the window is not the share of today (a quantity that was halved 10 days ago, stated from 1,200 to 720, books about 12 of 30 a month for a state that is already reached). The sentence says "the share of the window", and the Skeptic is shown `moved` when the rate of the last 7 days differs from the mean of the window by more than a quarter. Subtracting the cost of `to` at the price of the window would handle that better, but it also rests on a price that does not change with the volume, and the simpler form was kept. The Skeptic sees both rates beside the two numbers.
- **A typical day is the median of the days that have a cost.** It tells a charge made once from a rate, and it errs low: a meter whose cost really did grow in the last days is counted at its old typical day and shown at the new rate (a Scenario), and a meter that bills on a few days only is counted at those days. A meter of 3 days with one expensive day among them is the weakest case, because 3 days are few.
- **The cap knows only the meters that a tool showed.** `cost_meters` registers the dearest 40 lines of a call: a credit beyond them is not taken off. A meter that cost more than it gave back over the window, but whose last week was a refund, is taken off at its rate now.
- **A resource with a young line and an old line that was read for fewer than 30 days** says "since it began" for both. This needs a short read of one resource and a long one of another line, and is left.
- **The bound on a rate by the cost of 30 days is loose** (4 times for a meter that is not young). It catches a figure that is far off, and not one that is 3 times too high.

### What it costs

No new call, resource or permission. The Investigator's instructions grew by about 560 characters (to under 10,000, the pin of the test, raised on purpose with its reason). The room in the upload package is in [the changelog](../../CHANGELOG.md).
