# The press release from the future — and the tough questions

> A working-backwards exercise: write the announcement first, then answer the questions that would make it fall apart. Everything here is **fictional** — a company, a customer and numbers invented to make the idea concrete.
> Part of the [north star](01-north-star.md).

---

## PRESS RELEASE (fictional, dated a day in October 2027)

### Contoso's Azure bill now explains itself — and the AI that explains it learns something new every week

*An open-source "scientist for Azure's economics" studies new Azure services within hours, tests how they really bill, and works with the people who own the spend. Humans decide; the AI learns from every answer.*

**AMSTERDAM** — Today the Azure Cost in Action community released version 1.0 of an open-source system that treats cloud cost optimisation as a **science** rather than a checklist. Instead of matching a fixed list of rules, it **studies** how each Azure service charges, **surveys** each organisation's estate — what things are *for*, who owns them, when they are busy — **tests** its beliefs in a walled-off sandbox where it can create things, break them and watch the bill form, **acts** with people through short, specific questions and decisions in Microsoft Teams and email, and **grows** by being examined on tests it cannot see.

Contoso, a retailer running about 3,000 Azure resources across five countries, adopted the system in January. By October:

- **72%** of Contoso's Azure bill is *explained* — the AI can say what each part is for, who needs it, and what it would take to need less — up from 31% in week one.
- Of the changes the AI proposed, **68%** were accepted by the owners, **12%** declined with a reason, and **5%** countered with a better idea. Every decline became a lesson.
- **€1.9 million** a year of savings are *verified* against comparison groups, after the AI's own running costs. One quarter of the AI's recommendations were to **spend more** — and paid for themselves.
- When Azure announced a new service in September, the AI's draft profile was ready in **nine hours**, and the first Lab run found a small billing surprise the documentation did not mention.

"What surprised us was that it keeps *asking*," said a platform lead at Contoso. "Not more questions — *fewer*, and better. In March it asked whether a test environment could sleep at night. I said no, there's a month-end run. It remembered that, asked the next team a different question, and last week it told me one of my own environments was costing three times what it should and showed me exactly why. I didn't have a rule for that. Neither did it."

The system's knowledge of Azure — its **Atlas** of how services bill, its tested change recipes, its lab experiments, and an open **benchmark** for cloud cost reasoning — is published as open source under the MIT licence, so every participating organisation benefits from what every other one's AI learns, **without any estate data ever leaving its owner**.

"This is the part that I think matters," said the project lead. "The knowledge isn't locked in a product. You can read it, re-run the experiments behind it, and tell us when it's wrong."

*To get started, point it at a subscription in read-only mode. It will ask its first question within a day. It will never change anything without a human's say-so, or a rule a human wrote.*

---

## THE TOUGH QUESTIONS

**Isn't this just Azure Advisor with a chat window?**
Advisor ships hand-written recommendations for things Microsoft has already worked out. This system's centre of gravity is the *opposite*: it works out what nobody has written down — by studying a new service, running experiments to see how it really bills, and finding waste with no rule for it. It uses Advisor's findings as one input among many, and checks them like any other claim. And it is not a chat window: it runs long, resumable research programmes, and talks to people mostly through short cards and letters.

**Why would anyone trust an AI to change their estate?**
It doesn't, on day one. It starts by observing and predicting, and earns each kind of autonomy — one narrow domain at a time, with a cap and an expiry — by being right, in public, on a report card that leads with what it is worst at. It cannot do anything its approver could not do, anything irreversible needs two named people, and a purchase is always prepared by the AI and executed by humans. When it slips, it demotes itself.

**What if it learns something wrong?**
Then it will — and the design assumes so. Every claim carries receipts and a way to re-check it. Lessons from people are scoped, dated, expiring and editable, and conflicting ones are put side by side for a human, never silently overwritten. A confirmed finding must survive a Skeptic whose only job is to break it, and an important one is replicated. The exam is set by an independent agent and includes **decoys** — things that look wasteful but are not — so recommending a harmful change is the worst mark on the card.

**Does it read the internet? Couldn't someone poison it?**
It reads documentation, specifications, price lists and public discussion — and treats all of it as **data, never instructions**, graded by how much it can be trusted. Forum posts are leads, not facts; nothing becomes "known" until it has been tested or reviewed. The knowledge it contributes to the open **Commons** is reviewed by people, signed, and re-checkable by anyone.

**What happens when Azure changes a price or retires a service?**
That is the everyday case. A change radar watches announcements, price books, API specifications and documentation changes; every claim has a freshness and a re-check recipe. A price change re-tests the claims that depend on it and puts the affected estates on the Agenda — often before anyone has noticed.

**Does it need all our data? What about privacy?**
It reads what you permit, inside your boundary. The Estate Model and the Lesson Book never leave. What the Commons shares is knowledge about *Azure*, and — only if you opt in — anonymous counts such as "this kind of advice paid off in 71% of cases." The system works out *who owns things*, never how well anyone works.

**Does it replace our FinOps people?**
It replaces the hours they spend finding things and chasing owners — and gives them work they never had time for: deciding what counts as a good saving, reading the report card, granting or withdrawing autonomy, and teaching the AI what only they know. It makes a small FinOps team behave like a large one, and a large one like a research group.

**Is it only for large companies?**
The learning is shared, so a small company starts with the world's Atlas rather than from nothing. Its estate may be small, but its first day looks like everyone else's: the AI already knows Azure.

**What does it cost to run?**
It publishes its own bill on the report card and optimises it with the same grammar it applies to yours: smaller models for reading, larger ones only where needed, cheap Detectors for what it already understands. A learning system that cannot keep its own costs below its verified savings has failed its own exam.

**What if the Lab's findings don't match production?**
Every claim says whether it was *tested* or *inferred*, and in what conditions. Differences by region, contract or scale are exactly what replication is for: the Lab and the community re-run a recipe in other conditions and learn **where it holds**. Outcomes in real estates feed back into the Atlas — a claim that works in the Lab but fails in production is demoted, with the reason.

**Who owns all this knowledge?**
Everyone who runs Azure. The Atlas, the tested change recipes, the Lab experiments and the benchmark are open source under the MIT licence, maintained by the community and by an AI that opens pull requests for people to review.

**What's the point of the open benchmark?**
Nobody should have to take our word for it. Anyone can run any system — this one, a commercial product, a student project — against the same exam, and see how it does on rediscovery, restraint, honesty about its own limits, and the rest. An exam other people can run is an exam that cannot be quietly softened.
