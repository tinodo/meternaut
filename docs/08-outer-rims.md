# The outer rims — moonshots, wild cards and "what if?"

> Ideas that become possible *because the system learns*: directions, not designs. Nothing here is built; the technical design is in [docs/design](design/README.md). They run on evidence that already exists — bills, price sheets, recorded usage, changes people were making anyway, owners' answers, reviewed aggregates from several organisations. Learning never provisions anything just to measure it: most ideas cost AI and attention and nothing in Azure, and a rare trial — a small change an owner approves, to something already running — can move the bill. **Every name, resource, date, figure, approval and outcome in the examples below is invented.**
> Part of the [north star](01-north-star.md).

---

## A. Learning Azure faster, deeper, sooner

**Azure moves; you benefit.** A new service enters preview and within hours a *provisional* profile exists. The first bill lines that contain it confirm or correct the profile for their own estate; a saving is claimed once *your* bill agrees, and what several organisations see reaches the open Atlas only as a reviewed aggregate. When a new SKU is cheaper for a workload shaped like yours, a letter arrives with last month's usage re-priced under it.

**Law-finding.** From the changes it has followed and the bill lines that settled them, the AI looks for **laws** nobody wrote down: *"a thing that is stopped but not released often keeps its most expensive meter"*, *"a short-lived resource pays a minimum only where its meter says so."* It predicts services it has never touched; sealed test cases and the next bills say whether it was right. A surviving law joins the Cost Grammar.

**Change detectives.** API specifications and documentation are versioned, so the AI can diff them: *"this property now defaults to on — and it is the one that adds a meter"*; *"'per hour' became 'per started hour'."* Defaults and small words change bills without anyone deciding; the detectives catch them as they ship, then look for the first bill line that shows whether they matter.

---

## B. Understanding a company the way a long-serving colleague does

**The estate's autobiography.** *"Tell me the story of this subscription."* A short, evidence-backed history — what was built and why, which migrations and incidents shaped it, where the spend came from — with sources. It gives a new platform lead a starting point and an audit its answer to "why is it like this".

**Zombie dependencies.** Real dependencies live in traffic and call patterns, not documents. The AI finds the *zombies* — the only consumer of something else, which makes a whole chain look used — and the reverse: a quiet dependency that makes an "unused" thing critical.

**The Hunch Box.** Anyone can drop a hunch — *"I bet the test clusters sit idle at weekends"* — in a form, a Teams message or a line in office hours. It becomes a hypothesis, and the person gets back evidence: a yes, a no, or *"half true; here is the half."* Good hunches become Detectors.

---

## C. Finding out in cleverer ways

**Overnight consolidation.** While the world is quiet the system re-reads its own cases — solved, dropped, refuted — and asks what they have in common. By morning: a short list of patterns worth a Detector, and sometimes an uncomfortable one (an invented example: *"five of this month's refutations had the same cause"*).

**Self-writing Detectors.** For every confirmed, general finding the AI writes a cheap, scoped, expiring *lead generator*, back-tests it on recorded bills and runs it **in shadow**: it nominates cases privately for comparison, without contacting owners or changing Azure. Then it proposes the Detector for review: expensive reasoning once, cheap nominations afterwards, ambiguous cases still going to a Detective.

**The decoy collector.** A costly mistake is not missing waste but "fixing" something that only looks wasteful — the idle replica that is the failover, the database that wakes at quarter-end. When an owner explains why a thing is fine, the system keeps the look-alike in that estate's Lesson Book and tests every Detector against it. The owner's story stays private; a reviewer can turn its general shape into a *generated* decoy for the open regression cases.

**Polite scream tests.** The classic way to learn whether anyone uses something: switch it off and wait for the screaming. Done properly it is a [trial](04-finding-out-without-spending.md) with manners (in non-production; anywhere else it is an ordinary Action with its own approval): offered only when the owner approves after seeing a cost ceiling and recovery has been shown to fit an agreed outage budget, with **a note on the thing itself** saying whom to talk to. Anything that cannot be undone is never tried. Otherwise the system uses the usage evidence it already has.

**Replay the peak.** *"Imagine next Black Friday at three times the traffic: which meters explode and which stay flat?"* The AI scales last November's recorded usage and re-prices it meter by meter — once the same replay has reproduced last November's real bill — and lists the cliffs: the tier that jumps, the quota that bites. The answer is evidence under stated assumptions about how load scales, not a promise.

**Action by demonstration.** A human does a cleanup once — *"watch me"* — saying aloud the checks they make, and the AI, with consent, observes. It reads back the steps it saw and what it could not tell, then drafts an **Action** with a rollback, checks it against synthetic data and, where the platform offers one, a change preview, and offers it for review.

---

## D. Working with people in new ways

**Cost Court.** For contested, high-value cases a *Prosecutor* argues for the change, a *Defender* for keeping things as they are, and a *Judge* — a differently configured agent — sums up. The agents record the strongest arguments on each side and a recommendation; only an authorised human, or a rule a human wrote, can permit an action. The transcript explains more than a score and rehearses every objection the owner might raise.

**Team agents.** Each team can have an agent that represents its constraints — budget, service levels, maintenance windows — and *learns them by being corrected*. The central AI works through shared changes with it (an invented example: *"shrink the shared build pool to 40 agents" — "we peak at 38 on Mondays; keep 45, change after 22:00"*). People set each agent's mandate; if agents disagree over a shared resource, the owners' priorities and those mandates decide, and the agents only present the options.

---

## E. Agreements, commitments and the economics of things that matter

*They work at whatever reach the system has: where it cannot read the bill, a figure is a scenario priced at list prices, and each idea says what its numbers rest on ([every agreement, every level of access](01-north-star.md)). They feed the [Commitment Desk](05-recommend-act-verify.md), where purchases are prepared.*

**The renewal radar.** With billing reach, the radar keeps the calendar nobody keeps — every commitment has a last day and most agreements a renewal date, held by different people — and starts six months ahead: how much of each commitment was really used, which planned migrations land before it ends, a negotiating pack. (An invented example: *"The commitment ends on 31 March. You used 91% of it; two of its services shrink in Q4. Renew at 80%, with a step-up after a year."*)

**The discount archaeologist.** Two identical virtual machines, one list price, two different amounts on the bill. From the bill lines, and the price sheet where it may see one, the archaeologist names each layer in the order it applied (an invented example: *the agreement's discount, a licence benefit, a reservation that covered 83% of the hours, a credit that ran out in March*). Finance gets an answer to *"why does team A pay half of what team B pays?"* — often a benefit that landed on one team's hours: a sharing rule to agree, not luck.

**Benefit Tetris.** Pieces of different shapes fall into the year: reservations, a savings plan, licence benefits, dev/test rates. Placed well they interlock; placed badly, one sits unused because another got there first, and uncovered hours bill at the unreduced rate. Recommendations can overlap; the replay combines their benefits and reports the joint value instead of adding the individual estimates. It plays the whole board on a year of recorded usage, once a replay has reproduced the real bill.

**The partner whisperer.** Where a partner sells the commitments or a central team holds the right to buy, the AI cannot — and must not — go around them. It writes a complete request — what to buy and where, the saving with its range and price basis, what would make it a mistake, who has agreed, what a week of waiting costs — chases politely at the rhythm it has learned for that partner, and watches the bill to see whether the purchase landed. (An invented example: *a week of waiting costs about €1,100*; this partner answers on Thursdays.)

**The price-sheet watcher.** A Recommendation is a sentence with a price in it; when the price moves, the sentence must too. The watcher reads the organisation's own price sheet where it may see one, notices what changed — a rate renewed higher, a meter replaced, a discount that lapsed — and re-prices every open Recommendation (an invented example: *"3 got smaller, 2 got bigger, 1 flipped from worth doing to not"*). It also lays the bill beside the sheet and writes up any disagreement for whoever can raise it with the seller.

**The commitment thermostat.** A spending commitment is a thermostat set at the start of the term: a level of spend to reach by the end. With billing reach on a direct agreement, the thermostat forecasts the end of the term and, when a shortfall is coming, proposes work the owners already said can move — the migration deferred to Q3, a retraining run — never spending to fill a hole. A shortfall found in July is a plan; found in December, a surprise.

**The access menu.** The system starts on the access it was given — one subscription, no cost data, list prices — and says what each step up would change. (An invented example: *"Cost access here would replace the list-price estimates under 6 of your 14 open Recommendations with billed charges. The price sheet would price the rest at your rates. Billing reach would let me look for unused commitments; how many, and how much, stays unknown until I can inspect them."*) Each line names who can grant the access; the menu never asks for more than a question needs.

**Unit economics.** Owners define the units — customer, transaction, feature — and the rules for splitting shared costs; permitted activity and revenue records are combined with the cost data, and shared costs nobody allocated show as *unallocated*. The system can then surface the tenant that costs more than it earns.

**The price of the next nine.** A "nine" is one more 9 of availability: 99.9% to 99.99%. The system compares named configurations — zone redundancy, a second region, a hot standby — against the target and load an owner states, with failure assumptions beside each. Costs are conditional scenarios, not proven reliability gains. (An invented example: *"under these assumptions the next nine costs about €4,200 a month at list prices"*.)

**Cost and carbon in one Recommendation.** Where an emissions estimate linked to activity exists and its accounting boundary is stated, a second column can sit beside the euros, with the uncertainty and the missing inputs shown; emissions are never derived from euros. (An invented example: *"−€710 a month at billed rates; about −0.4 tonnes CO₂e a year, estimated; network missing"*.)

**Savings dividend and blameless review.** The budget owner can agree in advance to return a share of *verified, sustained* savings to the saving team's own budget, funded from those savings, so saving is worth doing. And when an Action causes harm it is rolled back where possible and reviewed without blame: regret is material to learn from, not a verdict on the owner. These reduce the reasons to say no; operational harm and financial loss remain possible.

---

## F. Growing — and growing together

**The cost weather map.** Organisations that opt in share only a scope and an aggregate — never a bill line, a name or an identifier — and the Commons publishes a figure only when several contribute, so no small group can be picked out. (An invented example: *"a new default in service X is hitting 14% of participating estates this week"*.)

**The Atlas beyond this system.** Any assistant, deployment tool or code editor can *ask* a copy of the open Atlas: *"what are the cost traps of this configuration?"* The same knowledge teaches people — *"explain this bill line like I'm new"*, published regression cases as **training scenarios** on generated estates — so a new hire can learn FinOps from the source the AI uses.

**FinOps for the AI itself.** The AI's own spend — models, agents, hosting — is on the report card, counted against its verified savings and optimised with the same grammar; *€ saved per € spent* is published.

---

## G. Wild cards

**Adjacent spend.** The same *study → survey → test → act → grow* loop fits any recurring cost with a signal of real need: seats and licences nobody uses, build minutes, idle developer environments, AI assistant seats.

**The voice of the bill.** A two-minute weekly audio for each team — *"what your platform did with its money this week"* — that opens by saying the AI is speaking, in the team's own language: the one thing worth knowing, the one thing worth asking.

---

## Where each idea plugs in

| Faculty | Ideas that extend it |
|---|---|
| **STUDY** | Azure moves; law-finding; change detectives; the price-sheet watcher |
| **SURVEY** | estate autobiography; zombie dependencies; Hunch Box; the discount archaeologist; the renewal radar; the access menu |
| **TEST** | overnight consolidation; self-writing Detectors; the decoy collector; polite scream tests; replay the peak; Action by demonstration; Benefit Tetris |
| **ACT** | Cost Court; team agents; the voice of the bill; the partner whisperer; the commitment thermostat |
| **GROW** | the cost weather map; the Atlas beyond this system; FinOps for the AI itself; savings dividend and blameless review |
| **Beyond cost** | unit economics; the price of the next nine; cost and carbon; adjacent spend |
