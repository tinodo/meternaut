# The press release from the future — and the tough questions

> A working-backwards exercise: write the announcement, then answer the questions that would make it fall apart. Everything here is **fictional** — company, customer, numbers and outcomes — and nothing described has been built.
> Part of the [north star](01-north-star.md).

---

## PRESS RELEASE (fictional, dated 12 October 2027)

### Contoso's Azure bill now explains itself — and the AI that explains it learns something new every week

*An open-source "scientist for Azure's economics" studies how new services really bill, works with the people who own the spend, and learns from every answer. Humans decide.*

**AMSTERDAM, 12 October 2027** — The Meternaut community today released version 1.0 of an open-source system that treats cloud cost optimisation as a **science**. It **studies** how each Azure service charges, **surveys** each estate — what things are *for*, who owns them, when they are busy — **tests** its beliefs against evidence that already exists (bills, usage history, changes people were making anyway), **acts** with people through short questions and decisions in Teams and email, and **grows** by being evaluated on sealed test cases it cannot see.

Contoso, a retailer running about 3,000 Azure resources across five countries, adopted the system in January. By October:

- **72%** of Contoso's Azure bill is *explained* — what each part is for, who needs it, what it would take to need less — up from 31% in week one; the rest sits on its Unexplained Spend list.
- Of the changes proposed, **68%** were accepted, **12%** declined with a reason, **5%** countered with a better idea and **15%** are still open or expired unanswered. Every decline became a lesson.
- **€1.9 million** a year of savings are *outcome-confirmed* — measured on the bills against comparison groups, after the AI's own running costs. A quarter of the recommendations were to **spend more**, and most paid off against the metric each owner named in advance.

"What surprised us was that it keeps *asking*," said a platform lead at Contoso. "Not more questions — *fewer*, and better. In March it asked whether a test environment could sleep at night. I said no, there's a month-end run. It remembered that, asked the next team a different question, and last week told me one of my own environments was costing three times what it should, and why. I didn't have a rule for that. Neither did it."

Advice depends on who is asking. Contoso's platform team has billing access, so its advice is priced at the contracted rates. The web shop's team sees one subscription and no bills, so every number it gets says *"Scenario at list prices — your rates are invisible to me"*; told once what cost access would add, it declined and was not asked again. When a savings plan would pay for itself, the system could not buy it — at Contoso only the finance team's procurement lead may — so it wrote her the request: what to buy, the expected saving and its range, what would make it a mistake, what a week of waiting costs. "The first request from a machine that I did not have to send back with questions," she said. She ordered on Thursday, the day the system had learned she answers, and the next bill showed the discount: the estimate became a bill-observed saving.

What it learns about Azure — the **Atlas** of how services bill, tested Actions and Detectors, and an open **benchmark** for cloud cost reasoning — lives in the **Commons** (the open, shared half of what the system has learned about Azure; never a customer's own data), open source under the MIT licence. Bills, names and owners' stories stay in each estate; only a reviewed aggregate from several organisations that opted in is shared. "The knowledge isn't locked in a product," said the project lead. "You can read it, check the evidence behind it, and tell us when it's wrong."

*To get started, point it at a subscription in read-only mode. It will ask its first question within a day. It will never change anything without a human's say-so, or a rule a human wrote.*

---

## THE TOUGH QUESTIONS

**Isn't this just Azure Advisor with a chat window?**
No. Advisor checks a defined list of situations Microsoft identified in advance, [each documented separately](https://learn.microsoft.com/en-us/azure/advisor/advisor-reference-cost-recommendations): some by plain checks, some by machine learning, such as resizing or shutting down an underused virtual machine; by [its own documentation](https://learn.microsoft.com/en-us/azure/advisor/advisor-cost-recommendations) it prices those savings at retail rates, ignoring the account's discounts and existing reservations or savings plans. This system investigates situations nobody pre-identified and ties every claim to its evidence. Advisor is one input, checked like any other claim.

**Why would anyone trust an AI to change their estate?**
It doesn't, on day one. It starts at the bottom of the **autonomy ladder** — observe, advise, assist with one tap, and only then autopilot inside a rule a human wrote — and climbs one narrow domain at a time, on a report card that leads with what it is worst at. Autopilot is a credential, withdrawn when regret passes a stated threshold and revocable at any time by a person with authority. Anything irreversible, a purchase included, needs two named people.

**What if it learns something wrong?**
It will. Every claim carries receipts and a re-check recipe, and must survive a Skeptic whose only job is to break it. If a challenge succeeds after advice has gone out, the claim is downgraded, the owners who relied on it are told, and the Ledger (the record of predictions, decisions and outcomes) keeps the correction. Sealed test cases include **decoys** — things that look wasteful but are not — so recommending a harmful change is the worst mark on the card.

**Does it read the internet? Couldn't someone poison it?**
It reads documentation, specifications, price lists and public discussion as **data, never instructions**. Forum posts are leads, not claims: a claim needs a receipt anyone can check and a reviewer's attempt to break it, and a saving is claimed only when that estate's own bill agrees. What enters the Commons is reviewed by people and re-checkable by anyone.

**What happens when Azure changes a price or retires a service?**
A change radar watches announcements, price books, specifications and documentation; a price change re-tests the claims that depend on it, re-prices the open Recommendations and puts the affected estates on the Agenda.

**Does it need all our data? What about privacy?**
It reads what you permit, inside your boundary. What it learns about your estate and your people — the Estate Model and the Lesson Book — stays with you. The Commons carries knowledge about *Azure* and, only if you opt in, outcome statistics — a scope and a count, such as "this kind of advice paid off in 71% of cases" (an invented figure) — published only when several organisations contribute, so none can be picked out. It works out *who owns things*, never how well anyone works.

**Does it replace our FinOps people?**
It replaces the hours spent finding things and chasing owners, and leaves the work that needs people: deciding what counts as a good saving, reading the report card, granting or revoking autonomy, teaching the AI what only they know.

**Is it only for large companies?**
No. The learning is shared, so a small company starts with the open Atlas, not from nothing: on day one it has the documented mechanisms and list prices, and says so until its own bill agrees.

**We buy through a partner and nobody here has billing access. Is this useless to us?**
No. It starts from what it may see and does not guess the rest: it tries what it needs — read the bill, read the price sheet, list the commitments — records what works for each scope, and tries again weekly and at once after Azure refuses a request. Where your rates are invisible every figure is a scenario at list prices; with cost data it uses the rates on your bill; with billing access, your contracted rates. It says what more access would add, never asks for more than a question needs, and turns a purchase it may not make into a complete request to the person who can.

**What does it cost to run?**
It publishes its own bill on the report card, next to its outcome-confirmed savings, and optimises it with the grammar it applies to yours: small models for reading, larger ones only where needed, cheap Detectors for what it already understands.

**What if what it learned about Azure doesn't hold for us?**
It may not, and every claim says so: what evidence stands behind it and where it was seen — region, offer, agreement type, scale. Pooled observations from other organisations raise confidence, but until a line of your own bill agrees, advice resting on the claim says *documented only*. The claim learns **where it holds**, and one that fails on your bill is demoted, with the reason.

**What's the point of the open benchmark?**
Nobody should have to take our word for it. The cost-trap bank (sourced Azure cost traps), the recipes that plant them in generated estates and the regression cases are open, so anyone can run any system against the same cases. A public test can be studied for, so it never decides how much autonomy the system earns; the sealed cases and their answers stay hidden from it while they are sealed.
