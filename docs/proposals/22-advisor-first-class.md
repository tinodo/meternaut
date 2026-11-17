# Advisor first class: every cost recommendation of Azure Advisor is a request with Advisor's own figure — a decision record

**Status: decided on 2026-11-17, built and tested against fakes, not deployed.** Until the function app that carries it is published, nothing here runs. Nothing was changed in Azure. The real list of recommendations was read once, read-only, and only counts and sums were looked at.

## The owner's words

The owner read what Meternaut had found and said that it was "not even on par with Azure Advisor". This record is that floor: what Advisor holds as a cost recommendation, Meternaut shows, with Advisor's own figure and words, so that a person can decide on each one. Finding what Advisor does not find is another job ([rule 30](../../AGENTS.md)); nothing here tells the agents what to look for, and their tool `advisor_items` is as it was ([the toolbox](12-investigation-toolbox.md)).

## What was wrong

On 2026-11-16 Advisor held 31 cost recommendations for the 10 subscriptions that the Watch reads, about 14,000 US dollars a year: 18 reservations of virtual machines (in two subscriptions), 4 savings plans, 6 reservations of Cosmos DB and 3 unattached disks. 28 of the 31 name the subscription itself as the impacted resource. In 45 days Meternaut had kept six leads from them, in nine cases, each asking only to look, each with no figure.

The lead was named by the impacted resource. All recommendations about one subscription became one lead, one of them survived, and its figure did not reach the request. Two guards made it worse: a lead that the investigation could cover was left to it, and a finding with no words was held back as "nothing to say".

## What Advisor gives

Read on Microsoft Learn on 2026-11-17 and on the real list.

- A recommendation has an impacted field, an impact, a type id, a short problem and solution (Advisor's own sentences) and extended properties whose keys depend on the kind. A reservation has the yearly and monthly saving, the currency, the term (one or three years), the size or product, the quantity, the region, the look-back (7, 30 or 60 days), the scope (one subscription or shared) and an offer id. A savings plan has an hourly commitment in place of a quantity. A disk has a yearly saving, a product and a region, and names no currency and no term.
- The monthly saving and the yearly saving are in the currency that the recommendation names. Learn's sample query for Advisor adds them up by currency, so more than one currency can occur ([Resource Graph samples for Advisor](https://learn.microsoft.com/azure/advisor/resource-graph-samples)).
- What the figures rest on differs by kind. Learn says that the forecasts for reservations and savings plans are based on actual rates and usage, and those for right-sizing and shutdown on retail rates. It also says that these kinds are made from overlapping data, and gives an order of work: right-size or shut down first, then reservations, then savings plans ([Calculate cost savings](https://learn.microsoft.com/azure/advisor/advisor-how-to-calculate-total-cost-savings)).

## What Meternaut does with each recommendation

| Advisor holds | Meternaut makes |
|---|---|
| A recommendation about a whole subscription (a reservation, a savings plan) | One lead for each recommendation, named by the recommendation itself. One case and one request for each subscription, type and sub-category, with the sum and the rows |
| A recommendation about one resource (an unattached disk) | One case and one request for that resource |
| The same resource, which a check of Meternaut or the investigation found too | One case: the case of that check holds what Advisor says, and the page names both sources. Never two requests |

A request shows what Advisor says in words of code and typed values: how many recommendations, what they add up to, and a row for each (what it covers and how many, where, for how long, what it saves a year, how far back Advisor looked, and whether it applies to one subscription or all). At most twelve rows are shown, the largest first, then "and N more" with their sum. A column that Advisor filled for no row is left out. Advisor's own sentences are text for a person; no model sees them. The case is made by code and no model judges it: the request says so.

**The figure.** A month is the year divided by twelve, in US dollars, for each recommendation. It is a Scenario ([the decision brief](09-the-decision-brief.md)): Advisor's own estimate, for the commitments based on the rates and usage that Advisor read, for the other kinds at retail rates. The basis says that the rows can be alternatives or overlap, so buying saves less than the sum. A recommendation in another currency is counted and not added, and the page and the History say so; Meternaut does not change currencies. A disk names no currency, so it is read in dollars only when the cost lines of its subscription are in dollars. A case where an older check or the investigation has a figure of its own keeps that figure, and Advisor's is not added to it, so [Savings found](21-savings-found.md) counts each case once and at one level.

**A commitment, in the right order.** For a reservation or a savings plan the request says in plain words what [proposal 17](17-reservations-instructions-only.md) says: delete what is idle and resize what is too big first, then commit, because a commitment locks in what runs today; and that Meternaut has not checked that what the commitment covers is the right size or will keep running. It points to the steps of proposal 17 for buying and builds no purchase tool. Its risk is high, because a refund counts against a cap and an exchange is limited.

## What each guard does to an Advisor case

Advisor's recommendations are claims with a figure, not findings that the AIs could not measure, so the default is that nothing Advisor says is held back.

| Guard | Decision |
|---|---|
| `ADVICE_MIN_USD` (a finding that no measurement backs, with no saving and a small cost) | Does not apply: the case has a figure and no objection of an AI. A figure of a few cents still makes a request |
| "Judged lately" | Does not apply: no AI judges an Advisor case. What a person answered is held as for every request: 30 days. An unanswered request that ended is asked again after the days that the AI findings wait |
| `ADVICE_OPEN_MAX` (ten requests for what the AIs did not settle) | Advisor requests are not held by it and not counted by it |
| `says_nothing` | An Advisor case always says something: its rows. A recommendation with no words gets words of code, never "Review the resource" |
| `held_reason` (an automation, nobody looked up who changed it, impact) | These are about deleting a resource, and an Advisor case never asks to delete. A case of an older check or the investigation that asks to delete keeps its guards, does not take Advisor's words, and when held the History says why (`case.held`) and the run counts it |
| `take_back` | Takes back no Advisor case. It closes the one request of the first version for a whole subscription, with the reason in its own words, unless a person answered it |
| Leads left to the investigation | An Advisor case is made whether or not the investigation ran. The lead of an older check about a resource that Advisor names is left to Advisor's case, except for waste that Meternaut planted, which keeps its own |

The History lists the first 50 leads of a Watch and says how many more there are; each Advisor case has its own line with its figure, and a Watch says how many recommendations it counted and did not add.

## What a person sees

The page, the letter and the card are renders of one brief. The page has the sum, the table of rows, the order of work, the risk and how sure Meternaut is, which says that no AI looked at it. The letter and the card carry the sum, and the order of work in one line. The Decisions page shows a row for each request. Savings found counts each case once, at Scenario.

## What is not proved

- **Nothing ran in Azure.** The real list was read once and passed through the new code without being stored: 31 recommendations gave 31 leads and 8 cases (the groups above), and the sum of the cases equals the sum of the recommendations read without the code, about 13,800 US dollars a year on the day, 267 less than the day before (Advisor refreshes its estimates). Whether the request reads well to a stranger was not tested with a person.
- **The currency of a disk.** Advisor names none. Reading it as dollars when the cost lines are is an assumption.
- **The hourly commitment of a savings plan** is not shown: its unit was not verified. The recommendation list that the Watch reads may differ from the blade where a recommendation is postponed or dismissed; that was not compared.
- **Overlap.** A reservation and a savings plan of one subscription can cover the same usage. Savings found adds each case as it is, so its total can be larger than what could be saved at once.
- **A resource inside a group case of the investigation** gets its own Advisor request beside the group's, and the two can be counted twice.
- **The older request.** Closing the first version's request for a whole subscription ran against fakes only.

## What it costs

No new call, resource or permission. It reads the list that the Watch already read. The room that it takes in the upload package of the function app is in [the changelog](../../CHANGELOG.md).
