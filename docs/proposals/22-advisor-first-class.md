# Advisor first class: every cost recommendation of Azure Advisor is shown, and each decision is counted once — a decision record

**Status: decided on 2026-11-17, rebuilt the same day, built and tested against fakes, not deployed.** Until the function app that carries it is published, nothing here runs. Nothing was changed in Azure. The real list of recommendations was read twice, read-only, and only counts and sums were looked at.

## The owner's words

The owner read what Meternaut had found and said that it was "not even on par with Azure Advisor". This record is that floor: what Advisor holds as a cost recommendation, Meternaut shows, with Advisor's own figure and words, so that a person can decide on each one. Finding what Advisor does not find is another job ([rule 30](../../AGENTS.md)); nothing here tells the agents what to look for, and their tool `advisor_items` is as it was ([the toolbox](12-investigation-toolbox.md)).

## What was wrong

**Before this record.** On 2026-11-16 Advisor held 31 cost recommendations for the 10 subscriptions that the Watch reads: 18 reservations of virtual machines, 4 savings plans, 6 reservations of Cosmos DB and 3 unattached disks, and 28 of the 31 name the subscription itself as the impacted resource. In 45 days Meternaut had kept six leads from them, in nine cases, each with no figure: the lead was named by the impacted resource, so everything about one subscription became one lead.

**The first version of this change** made one case for each subscription, type and sub-category and added up every recommendation in it. That counted about 13,700 US dollars a year, several times more than anyone can save: the same purchase was counted again for every term and look-back.

**What the evidence showed.** Read again, read-only, with the new grouping: of the typed fields that Advisor gives, only the term (one or three years), the look-back (7, 30 or 60 days) and the figures that follow from them (the yearly saving and, for a savings plan, the commitment) differ between recommendations for the same size or product, region and scope. Everything else is the same in this estate's list: the offer id, the scope, the quantity, the count of resources (Learn says the quantity can differ between look-backs, which the second review below takes into account). So the 31 are 9 decisions: three disks and six commitments, four of them listed six times and two listed twice. The variants are alternatives, because a person buys one term, not all. Learn says why: the engine evaluates the usage of the past 7, 30 and 60 days and recommends the quantity that saves most ([Reservation recommendations](https://learn.microsoft.com/azure/cost-management-billing/reservations/reserved-instance-purchase-recommendations)), and it asks nobody to buy a reservation and a savings plan for the same use at once. Advisor's own page adds that reservations, savings plans and right-sizing are made from overlapping data and should be followed in that order ([Calculate cost savings](https://learn.microsoft.com/azure/advisor/advisor-how-to-calculate-total-cost-savings)).

**What the second review found, and what changed (2026-11-17).** The quantity was in the key of a decision, but the engine recommends a quantity for each look-back, so it can differ between variants, and a quantity that Advisor recomputes opened a second case and request while the first stayed open and a decline on it was lost: the quantity is out of the key now, and a decision that Advisor no longer lists is closed (only in a subscription whose list was read in that Watch, and never when a person answered or put off its request). A case that an older check or the AIs made for the same resource was rewritten as waiting for a person and counted as made: it only gets Advisor's digest in its facts now. The words "at retail rates" were said of every recommendation that is not a commitment, and Learn says it only of right-sizing and shutdown, and no typed field of Advisor tells which recommendations those are: the clause is gone, and only a commitment says what its figure rests on. A recommendation with no words, no figure, no product and no term was asked about again, as the owner had complained: it says nothing and is held back as before. The page of a request that no AI looked at named the configured models in its foot, and the weekly summary did not say that no AI looked at it. The tests did not vary the region, the scope, the type and the sub-category of the key: they do now.

## What Meternaut does with each recommendation

| Advisor holds | Meternaut makes |
|---|---|
| Recommendations about a whole subscription with the same type, sub-category, size or product, region and scope, which differ by term, look-back and the quantity that is recommended for each look-back | One lead for each recommendation, named by the recommendation. One **decision**: one case, one request, one figure |
| A recommendation that names no term or no look-back | Its own decision. It is never merged by a guess |
| A recommendation about one resource (an unattached disk) | One case and one request for that resource. Recommendations about the same resource overlap, so the larger is counted |
| The same resource, which a check of Meternaut or the investigation found too | One case: the case of that check holds what Advisor says, and the page names both sources |

**How a decision is counted.** Its figure is the smallest of its variants, in US dollars a year, at the level Scenario: Advisor's own estimate. The request says the range in plain words ("the smallest is counted; the largest is X with a term of three years"), shows every variant, and says that they are alternatives. The page, the letter, the card, the History line and Savings found all take this one figure from the case; the month is the year divided by twelve.

**How alternatives across decisions are counted.** Advisor's fields name the size or product of a reservation, but not what a savings plan covers, so they do not say which decisions cover the same spend. So the rule is the cautious one. Among the commitments of one subscription, a product that Advisor offers in another scope counts once, by its larger figure; and the kinds of commitment (Advisor's sub-category) are alternatives of each other, so only the kind whose products add up to most is counted. The others keep their figures, count nothing and say what is counted instead. Since 2026-11-19 nobody is asked about them: a request whose own page says that it adds nothing is a request that a person cannot decide (the rule `NO_FIGURE`, below). Two reservations of different sizes are not alternatives: both are counted.

A recommendation in another currency, or with no figure, is counted and not added, and the page and the History say so. A disk names no currency, so it is read in dollars only when the cost lines of its subscription are in dollars. A case where an older check or the investigation has a figure of its own keeps that figure, and Advisor's is not added to it.

**A commitment, in the right order.** The request says what [proposal 17](17-reservations-instructions-only.md) says: delete what is idle and resize what is too big first, then commit, because a commitment locks in what runs today; and that Meternaut has not checked that what the commitment covers is the right size or will keep running. It builds no purchase tool.

## What each guard does to an Advisor case

Advisor's recommendations are claims with a figure, not findings that the AIs could not measure, so the default is that nothing Advisor says is held back, except a recommendation that states no saving.

| Guard | Decision |
|---|---|
| `UNPRICED`, `UNMEASURED`, `UNCONFIRMED` (`why_not_ask`) | Do not apply: they are about findings of the investigation, and an Advisor case has Advisor's own figure and no objection of an AI. A figure of a few cents still makes a request |
| `NO_FIGURE` (`why_not_ask`, added 2026-11-19) | Applies to an Advisor case that states no saving: an alternative of a purchase that saves more (its figure is not counted), a figure in another currency, or none. Nobody is asked about it, and the History and the start page say "Meternaut counts no saving in dollars from Azure Advisor". A case that says nothing keeps its own reason (`says_nothing`), and a case that carries the finding of an older check about the same resource (the check's lead is left to it: `also` in its digest) is not held back, because the check's lead is left to it and nothing else would ask about the resource |
| "Judged lately" | Does not apply: no AI judges an Advisor case. What a person answered is held for 30 days, as for every request |
| `ADVICE_OPEN_MAX` | Advisor requests are not held by it and not counted by it |
| `says_nothing` | A recommendation with a figure, a product or a term always says something: its rows, with words of code when Advisor wrote none. One with no words, no figure, no product and no term says nothing and is held back as before, and the History says it once |
| `held_reason` | Is about deleting a resource, and an Advisor case never asks to delete. A case of an older check or the investigation for the same resource keeps its own guards and its own flow: it only gets Advisor's digest in its facts, with no new status, time or line of the History |
| `take_back` | Takes back an open request of an Advisor case only when the case states no saving now and the request states none (`NO_FIGURE`, with its own reason `no-figure` and its own words: "... although no saving was counted for it"; [proposal 30](30-escalation.md), item 22); a request that was asked with a saving stays, even when its purchase is an alternative now (a known limit), and so does every request that a person answered. A request of the first version that gave one figure for a whole subscription is closed with its reason, unless a person answered it. A decision that Advisor does not list any more is closed too, in a subscription whose list was read in that Watch |
| Leads left to the investigation | An Advisor case is made whether or not the investigation ran |

## What is not proved

- **Nothing ran in Azure.** The real list was passed through the grouping and not stored: 31 recommendations gave 9 decisions, 2 of them alternatives, and about 1,340 US dollars a year counted (the raw sum was about 13,700). The numbers move each day, because Advisor refreshes its estimates. Whether the request reads well to a stranger was not tested with a person.
- **Advisor may price a commitment for something that no longer runs or that should change first.** Meternaut has not checked that what a reservation or savings plan covers is running, or the right size. A person, or the Investigator, has to.
- **Alternatives across decisions are a rule of caution, not a fact.** Treating every savings plan as an alternative of the reservations of its subscription can count too little where a savings plan covers different spend. The fields do not tell, so only the larger kind is counted.
- **The currency of a disk.** Advisor names none. Reading it as dollars when the cost lines are is an assumption.
- **The hourly commitment of a savings plan** is not shown: its unit was not verified. The list that the Watch reads may differ from the blade where a recommendation is postponed or dismissed; that was not compared.
- **A resource inside a group case of the investigation** gets its own Advisor request beside the group's, and the two can be counted twice. Closing the first version's request, and closing a decision that Advisor no longer lists, ran against fakes only, and rest on a list that Advisor answered: a list that is empty by a fault of Advisor's would close requests.
- **What the tests pin.** The behaviours that the two reviews named were mutation-checked: each field of the key, the quantity, the counted figure, the alternatives, the closing and what stops it, the guards, the rates clause, the footer and the summary. A change to a wording, or to which columns a table shows, was not tried.

## What it costs

No new call, resource or permission. The room that it takes in the upload package of the function app is in [the changelog](../../CHANGELOG.md).
