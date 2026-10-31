# The outer rims — moonshots, wild cards and "what if?"

> **The brief:** *explore the outer rims of what is possible with AI and Foundry, inside proper workflows — not as a chatbot.* Technical feasibility is deliberately ignored here: these are things that become possible **because the system learns**. Each idea is a sentence or three — a direction, not a design.
> Part of the [north star](01-north-star.md).

---

## A. Learning Azure faster, deeper, sooner

**Azure moves; you benefit.** A new service enters preview; within hours a *draft* Profile exists. By general availability it is verified in the Lab. The day a new SKU is cheaper for a workload shaped like yours, you get a letter — *"this changes the answer for these three things; here is the Lab evidence."* Retirements work the same way, in reverse: *"this SKU retires in nine months; the cheaper equivalent behaves like this under your load."*

**Law-finding.** After a few hundred experiments, the AI looks for **laws** — regularities across services that nobody wrote down: *"anything short-lived pays a minimum"*, *"stopped usually means compute stops but storage does not"*, *"a private connection usually adds a per-GB processing meter."* It predicts services it has never touched, and the Exam tests whether the prediction was right. A law that survives becomes part of the Cost Grammar.

**Default-drift radar.** Every API version is published as a machine-readable specification. The AI diffs them: *"in the new version, this property now defaults to on — and it is the one that adds a meter."* Defaults are how bills change without anyone deciding anything; the radar finds them the day they ship.

**Doc-diff detective.** Documentation lives in git; every change has a commit. The AI reads the **diff** of billing pages: *"three words changed in the pricing note for this service — 'per hour' became 'per started hour'."* It runs the Lab experiment that tells whether the words matter.

**The price seismograph.** A continuous watch on the price books: it notices a change, an inconsistency (a bigger SKU cheaper than a smaller one in one region), a region that is quietly 18% cheaper for the same thing, or a free allowance that shrank. Most of what it finds is dull. A few things are worth a letter.

**The crowd as a sensor.** People complain in public about surprise bills — in forums, issue trackers, blog posts. The AI reads them as the **lowest-rank evidence** it has: not a claim, a *lead*. Each becomes a hypothesis on the Agenda, and the Lab confirms or refutes it. The crowd is noisy; the Lab is the filter.

**Meter archaeology.** The bill contains meters that no longer appear in any catalogue, SKUs from three generations ago, charges with names no document mentions. The AI digs: *what is this, when was it introduced, what replaced it, why are we still paying it?* Every bill line gets an explanation — or goes on the [Unexplained Spend Ledger](03-estate-and-investigation.md#5-the-bill-as-a-tree--and-the-ledger-of-what-is-unexplained).

**AI-spend intelligence.** The new frontier of surprise bills: tokens, provisioned model capacity, GPUs, vector indexes, long-running agents. The AI learns the grammar of AI services as fast as any other — *and* watches for what only AI workloads do: a runaway agent loop, a prompt that quietly doubled in size, a model that was swapped for a pricier one, an evaluation job nobody turned off. The State of FinOps survey lists granular AI-spend monitoring among the top unmet needs; an AI that studies AI services is well placed to help fill it.

---

## B. Understanding a company the way a long-serving colleague does

**The estate's autobiography.** *"Tell me the story of this subscription."* The AI writes a short, evidence-backed history: what was built and why, which migrations happened, which incidents shaped it, where the spend came from — as a timeline with sources. It is how a new platform lead gets oriented in a day, how an audit finds out "why is it like this", and how the AI itself checks it understood.

**The rehearsal estate.** A **digital twin** of an estate, built in the Lab from the Estate Model with synthetic data and recorded load shapes. Before the AI proposes a change that matters, it *rehearses* it on the twin — and shows the owner the rehearsal. A step beyond the Time Machine: not only *what would have happened* but *what will*.

**Reading the whiteboard.** A photo of a whiteboard in a wiki, a slide from a design review, a hand-drawn network sketch: the AI reads **pictures** as evidence of intent. *"The diagram says this is the failover site; that explains the idle machines."*

**Dependency archaeology.** Real dependencies are in traffic, connections and call patterns, not in documents. The AI maps them and finds **zombie dependencies** — a thing that is *the only consumer of something else*, which makes a whole chain look used when nothing real depends on it, or the reverse: a quiet dependency that makes an "unused" thing critical.

**The org chart as a cost graph.** Teams reorganise; costs do not follow. When the directory changes, the AI re-maps ownership overnight: *"this platform now belongs to the new team; here is its history, its lessons, and its open questions."* It also notices the quiet side effect of a reorganisation — spend nobody now answers for.

**The Hunch Box.** Anyone can drop a hunch — *"I bet the test clusters sit idle at weekends"*, *"this feels expensive for what it does"* — in a form, a Teams message, a line in office hours. Each hunch becomes a hypothesis, is investigated, and the person gets back evidence — a yes, a no, or *"it is half true, here is the half."* Good hunches become Detectors; the person is credited by name *if they want*.

---

## C. Finding out in cleverer ways

**The Forger.** The Examiner's evil twin: an agent whose job is to **forge waste that fools the Detectives** — cleverly disguised idle capacity, plausible decoys that look like waste but are not, "unused" things that are secretly critical. Detectives and Forger compete in the Terrarium; every Forger win becomes an exam question and a Lesson. It keeps the exam hard in ways no human question-writer could.

**Polite scream tests.** The classic way to find out whether anyone uses something is to switch it off and wait for the screaming. The AI does it *properly*: only where the owner agreed, in a short, announced window, with a guard that restores it in seconds, and **a note on the thing itself** saying who to talk to. It is a [Trial](04-experiments-and-the-lab.md#8-experiments-in-the-real-world--carefully) with manners.

**Synthetic customers.** Simulated users and teams with *behaviour*: busy at quarter end, silent over summer, bursty after releases, occasionally strange. They drive the Terrarium, so detectors are tested against estates that **behave like businesses**, not like load tests.

**The pre-mortem of the future.** *"Imagine next Black Friday at three times the traffic: which meters explode and which stay flat?"* The Lab runs the stress on a copy and returns the list of cost cliffs *before* the day.

**Move by demonstration.** A human does a cleanup once — *"watch me"* — with the AI observing (with consent). It drafts a **Move** from the demonstration: the steps, the checks the human made without thinking about them, the rollback. Then it proves the Move in the Lab and offers it back for review. Teaching by showing, the way an apprentice learns.

---

## D. Working with people in new ways

**Cost Court.** For contested, high-value cases, a *Prosecutor* argues for the change, a *Defender* argues for keeping things as they are, and a *Judge* — a differently configured agent — rules. Humans can appeal. The transcript becomes part of the case notebook: a much richer explanation than a score, and a rehearsal of every objection the owner might raise.

**Steward agents.** Each team can have a **steward** that represents its constraints — budget, service levels, maintenance windows — and that *learns them by being corrected*. The central AI negotiates shared-resource changes with the stewards (*"reduce the shared gateway to 40 units" — "we peak at 38 at 09:00 on Mondays; keep 45 and change after 22:00"*). People set each steward's mandate.

**Policy in plain language.** *"No development resource runs at night unless it is tagged."* The AI compiles it into a standing rule, a preventive control and a **simulated impact report** — what would change, who would be affected, what it would save — for people to ratify. Rules are written the way people think.

**Decisions with receipts.** Architecture decision records get a **cost receipt**: at design time, the Consequence Engine's prediction; ninety days later, what actually happened. Over a year the organisation learns *which kinds of decision it systematically misjudges.* It is the Experiment Ledger, applied to human decisions.

**Calendar-aware everything.** The AI learns the company's **calendar** — launches, freezes, audits, quarter closes, the sales kickoff — and adjusts all of its behaviour: when it asks, what it proposes, how long it watches before calling something idle, when it wakes things up. *"I won't ask you anything in the week before the audit."*

---

## E. Strategy, economics and the cost of things that matter

**Unit economics.** Cost per customer, per transaction, per feature — linked to revenue where the business allows. It surfaces the unprofitable tenant, the feature that costs more than it earns, the unit cost that is falling while the bill rises (good news the bill alone hides).

**The price of the next nine.** Show what each increment of reliability costs — zone redundancy, a second region, a hot standby — so owners *choose* instead of inherit: *"the next nine costs about €4,200 a month; you do not have a stated need for it."* The Well-Architected trade-off made tangible, with no nudge towards under-protection.

**Cost and carbon in one Brief.** The same Consequence Engine can carry a second ledger: the **emissions** side of a change. A Brief shows *"−€710 a month, −0.4 tonnes CO₂e a year"* — and the occasional case where the two pull apart.

**Savings dividend and savings insurance.** Two ideas about incentives. A *share of verified, sustained savings returns to the team's own budget* — so saving is worth doing. And **blameless regret**: when a Move causes harm, it is rolled back where possible and reviewed without blame — the audit records who approved what, but regret is the system's budget to learn from, not a verdict on the owner. Both make *yes* safe.

---

## F. Growing — and growing together

**The cost weather map.** Across the organisations that opt in to share **counts only**, the Commons shows a weather map: *"a new default in service X is hitting 14% of participating estates this week"*, *"this price change affects the largest number of workloads in region Y."* An early-warning system built from many estates, with no estate's data in it.

**Atlas as a service.** The Atlas is not only for this system. Any assistant, deployment tool or code editor can *ask* it: *"what are the cost traps of this configuration?"* An open interface to the world's best-maintained map of Azure's economics — so that **cost sense is available wherever infrastructure is written**, not only where this AI runs.

**The curiosity feed.** A public weekly list of the AI's top five "I wonder…" questions — *"does a paused index of the new service really cost nothing?"* — that the community can answer, argue with or help test. A research programme that does its thinking in the open.

**The Atlas as a teacher.** The same knowledge teaches people: *"explain this bill line like I'm new"*; interactive walk-throughs of the Cost Grammar; exam questions that become **training scenarios** and tabletop games for FinOps newcomers, with the Terrarium as the practice field. A new hire's first week with the AI is also a week of learning FinOps.

**FinOps for the AI itself.** Not an add-on — the **integrity test** of the whole idea. The AI's own spend — models, agents, the Lab — is on the report card, optimised by the same grammar, with *€ saved per € spent* published. A system that cannot manage its own bill has no business managing yours.

---

## G. Wild cards

**Adjacent spend.** The loop is not about Azure resources only. Seats and licences that nobody uses, capacity add-ons, build minutes, idle developer environments, AI assistant seats: the same *study → survey → test → act → grow* loop on any recurring cost with a signal of real need.

**Cost autopsy.** After any surprise, a blameless write-up: what happened, what the system believed, what it did, what it has learned. A short document that turns an unpleasant surprise into something the whole organisation — and the Commons — can use.

**Spend as a security signal.** A sudden compute or egress spike can mean a crypto-miner or an exfiltration; conversely, a security finding implies cost. The AI routes the right spikes, with context, to the people who watch for them, and learns their patterns from the other side.

**The voice of the bill.** A two-minute weekly audio for each team — *"what your platform did with its money this week"* — in the team's own language, with the one thing worth knowing and the one thing worth asking. Playful, low-risk, humane; it makes the bill a thing people *listen to*.

---

## Where each idea plugs in

| Faculty | Ideas that extend it |
|---|---|
| **STUDY** | Azure moves; law-finding; default-drift radar; doc-diff detective; price seismograph; the crowd as a sensor; meter archaeology; AI-spend intelligence |
| **SURVEY** | estate autobiography; rehearsal estate; reading the whiteboard; dependency archaeology; org chart as a cost graph; Hunch Box; calendar-aware everything |
| **TEST** | the Forger; polite scream tests; synthetic customers; pre-mortem of the future; Move by demonstration |
| **ACT** | Cost Court; steward agents; policy in plain language; decisions with receipts; voice of the bill; spend as a security signal |
| **GROW** | the cost weather map; Atlas as a service; curiosity feed; the Atlas as a teacher; FinOps for the AI itself; savings dividend and insurance |
| **Beyond cost** | unit economics; the price of the next nine; cost and carbon; adjacent spend; cost autopsy |

Which of these to try first — the thinnest slice that proves the whole idea — is in [what next](10-what-next.md).
