# The Outer Rim — moonshots, wild cards and "what if?"

> **Status:** Ideation **v3** (unchanged in substance by round 2, one re-open trigger aligned with decision D18; v2 archived [here](../_archive/round-2-v2/ideation/09-outer-rims-moonshots.md), v1 [here](../_archive/round-1-v1/ideation/09-outer-rims-moonshots.md)) · **Date:** 2026-10-30 · Part of the [north-star vision](01-north-star-vision.md)
> **The brief:** *"explore the outer rims of what is possible using AI and Foundry within proper workflows — not as a chatbot."* Technical feasibility is **deliberately ignored** here. Each idea states its **conceptual hard part** (what makes it difficult in principle: trust, privacy, accountability) and a **smallest experiment** that would teach us something without building the platform.

Horizons: **H1** close the last mile · **H2** consumption intelligence · **H3** preventive & predictive · **H4** governed autonomy.

**Decision status (v2).** A menu without decisions is a wish list, so every idea now has a status — see the [status table](#decision-status-v2) at the end: **Enabler** (a foundation Release 1 needs) · **Candidate** (research queue, no commitment) · **Parked** (kept, with a re-open trigger) · **Retired** (removed, reason recorded).

---

## A. Conversation & collaboration

**M-01 · Cost Court (adversarial debate).** For contested or high-impact cases, a *Prosecutor* argues for the change, a *Defender* argues for keeping things as they are, and a *Judge* (a differently configured agent) rules. Humans can appeal. The transcript becomes part of the Case file — a far richer explanation than a score.
*Hard part:* theatre vs. value; cost per case; correlated model blind spots. *Experiment:* replay 50 historical cases; measure extra catches vs. cost. **H2**

**M-02 · Agent-to-agent negotiation (federated stewards).** Each team has a **Steward agent** that represents its constraints (budget, SLOs, maintenance windows). The central crew negotiates shared-resource changes with the stewards ("reduce the shared gateway to 40 units" → "we peak at 38 at 09:00 on Mondays; keep 45 and schedule the change after 22:00"). Humans set each steward's **mandate**.
*Hard part:* accountability for a negotiated outcome; mandate limits. *Experiment:* two stewards negotiating about one shared workspace on paper. **H4**

**M-03 · The FinOps Review Room.** A clearly-labelled **AI participant** joins the weekly cost review (voice, optional avatar): gives a 90-second recap, answers "what if we turn off X?" with evidence, and records decisions as Cases. Nothing executes without confirmation from an authorised human in an authenticated channel.
*Hard part:* real-time accuracy under pressure; consent and recording; cross-talk. *Experiment:* a text-only participant in the meeting chat first. **H3**

**M-04 · The voice cost brake (parked).** A runaway spend spike triggers a **call** to on-call after the card goes unanswered: *"Spend rate is forty times normal. A confirmation prompt is on your phone."* Only a **pre-certified, narrowly enumerated** brake may ever act without a human — and only for a resource class whose service owner recorded a *safe-to-pause contract*, on an independent signal, with a live incident check and a mandatory post-incident review ([06 §3](06-closed-loop-actions-and-autonomy.md)). **A cost anomaly alone never pauses anything.**
*Hard part:* voice is **not** authentication — confirmation must complete in an authenticated channel; false alarms at 02:00 burn trust; a forged anomaly must not be able to trigger a pause (T38). *Experiment:* a tabletop exercise with on-call. **H3** · *Parked until a safe-to-pause contract exists.*

**M-05 · Meeting-intent mining (retired).** With consent, detect "we're sunsetting Project Phoenix" in meeting notes and propose a teardown plan.
*Hard part:* privacy, works councils, creepiness, accuracy. **Retired in v2:** it mines people's conversations — the line [07 §12](07-ownership-and-organization.md) draws — and invites works-council and GDPR scrutiny out of proportion to the value. The safe sibling is explicit: a team *tells* the Herald "we are sunsetting Project Phoenix" in a card or form. Re-open only on a customer's explicit request with works-council approval. **H4**

**M-06 · Budget conversations.** Instead of a static threshold email, a mid-month dialogue: *"Forecast is +18% vs last month because of X. Expected? [Yes, planned] [No, investigate] [Explain]."* Answers **label** anomalies and teach the model what "normal" means per team.
*Hard part:* over-messaging. *Experiment:* five owners, manual weekly conversations for a month. **H2**

**M-07 · Hands-free approval from the phone lock screen.** Approve/defer from a notification with secure step-up — for the owner who is between meetings.
*Hard part:* secure step-up UX; *tap-through* approvals. *Experiment:* paper prototype of the approval flow with security review. **H2**

---

## B. Prediction & prevention (shift left)

**M-08 · The shift-left cost bot.** Reviews infrastructure-as-code pull requests: cost delta, peer comparison, cheaper alternatives, WAF trade-offs ("this adds €1.2k/month; the usual pattern for this workload is a quarter of that").
*Hard part:* estimate accuracy; developer annoyance. *Experiment:* run on 30 past PRs; compare estimates with actual cost. **H3**

**M-09 · Deployment-time cost gate.** A deployment above a threshold asks: *"This will cost ≈ €1.2k/month. Continue?"* — approvals logged, owner set at birth. Solves ownership at creation.
*Hard part:* friction; bypass. *Experiment:* advisory-only mode. **H3**

**M-10 · Calendar-aware scaling.** Scale for business events and release trains (read from shared calendars and release plans): warm up before the product launch, release capacity after.
*Hard part:* signal quality; permissions. *Experiment:* one service, one shared calendar. **H3**

**M-11 · Cost SLOs and burn-rate alerts.** Treat **cost per unit** (per 1,000 requests, per active user) as an SLO with an error budget; alert on **burn rate**, exactly as SRE does for reliability.
*Hard part:* choosing unit definitions per service. *Experiment:* three services, eight weeks. **H3**

**M-12 · The Pricing & Retirement Radar.** Watches announcements (retirements, new SKUs, price changes) and opens cases: *"v3 SKU retiring; here is the cheaper equivalent; 14 VMs affected; migration windows proposed."*
*Hard part:* turning announcements into resource-level impact reliably. *Experiment:* a manual monthly radar summary. **H2**

**M-13 · Digital twin / what-if simulator.** Simulate the estate-level effect of a policy (sleep schedules, a commitment purchase, a gateway consolidation) with **risk distributions**, not point estimates.
*Hard part:* model fidelity. *Experiment:* Monte-Carlo for the commitment portfolio only. **H3**

**M-14 · The Time Machine.** Replay the last 90 days: *"If you had acted on everything we recommended, you'd have saved €X, with Y regrets."* The best sales and trust tool we have.
*Hard part:* honest counterfactuals. *Experiment:* run it in **Assess** mode for a friendly customer. **H1**

---

## C. Code- and context-aware optimisation

**M-15 · Code-level optimisation pull requests.** Link a **cost line to a code line**: *"This log statement in `OrderService` produces 38% of your ingestion — here is a PR changing it to debug level"*; polling loops; chatty dependencies; N+1 queries driving database cost.
*Hard part:* attributing telemetry to source; developer trust. *Experiment:* start with log templates → source mapping on one service. **H3**

**M-16 · Preview-environment reaper.** Per-PR/branch environments outlive their pull request. Correlate *PR closed ↔ environment alive* and tear down, with the PR author as owner.
*Hard part:* environments others adopted. *Experiment:* one repository. **H1**

**M-17 · Duplicate-data detector.** Find identical datasets copied across storage accounts and lakes; propose consolidation.
*Hard part:* access to content hashes; ownership of copies. *Experiment:* one data lake. **H2**

**M-18 · Context mining.** Read READMEs, ADRs, wikis and pipeline definitions to learn **what a resource is for** — avoiding the classic false positive ("unused" storage account = infrastructure-as-code state).
*Hard part:* access and noise. *Experiment:* 20 "unused" candidates; count false positives avoided. **H2**

**M-19 · Cost-aware autoscaler author.** Proposes scale rules (and schedules) tuned to actual load patterns and SLOs, with simulation.
*Hard part:* safety margins. *Experiment:* three stateless services. **H3**

**M-20 · Architecture alternatives generator (reverse design review).** For the most expensive workloads, propose alternative designs (consolidation, PaaS, event-driven) with migration effort and risk — grounded in CAF/WAF patterns.
*Hard part:* design quality vs. an architect's judgement. *Experiment:* five past workloads vs. architects' recommendations. **H3**

---

## D. Learning, community and open source

**M-21 · Open Waste Rules ("Sigma for FinOps").** A vendor-neutral, declarative, testable **playbook format** — signal → evidence → case → *proposed* action → verification — with community-contributed rules and test data. Playbooks are **read-only data, never executable code**: a playbook describes, it does not run. The crew *uses and drafts* them; humans approve each one as a governed release.
*Hard part:* format design; governance; keeping playbooks declarative so the trust model stays tractable. *Experiment:* write ten rules and their test data. **H2**

**M-22 · The Waste Lab.** A generator that builds a **synthetic estate with injected waste and ground truth**, so agents and playbooks can be evaluated for precision and recall — and so the community can test safely.
*Hard part:* realism. *Experiment:* 30 injected cases and a Scout run. **H1**

**M-23 · The playbook flywheel.** The Alchemist notices "I've seen this pattern in 37 cases" and drafts a new *declarative* playbook (sanitised, no customer data) for governed human review and optional upstream contribution.
*Hard part:* privacy boundaries; review load. *Experiment:* one pattern end-to-end. **H3**

**M-24 · Peer benchmarking.** "Teams like yours spend 30% less on logs" — within one organisation first; cross-organisation only with explicit opt-in and aggregation.
*Hard part:* comparability; privacy. *Experiment:* intra-organisation only. **H3**

**M-25 · Confidence calibration league.** Publish how well the crew's stated confidence matches outcomes ("when we say 90%, we are right 88% of the time") — honesty as a feature.
*Hard part:* institutional courage. *Experiment:* calibrate on the Time Machine replay. **H2**

---

## E. Economics & incentives

**M-26 · The savings dividend.** A share of **verified, sustained** savings returns to the owning team's budget. Aligns the incentive (gap #6).
*Hard part:* baseline fairness; gaming; Finance policy. *Experiment:* one team, one quarter. **H3**

**M-27 · Blameless regret ("savings insurance").** When an agent action causes regret, the platform rolls back automatically *where the action's class allows it*, and the review is **blameless**: it asks what the system, the policy and the controls should change. The audit still records who approved what — **attribution is not blame** — and organisational accountability follows the customer's RACI ([08 G1-13](08-trust-safety-and-guardrail-topics.md)). R3 and R3-Data actions have no automatic rollback, so the promise is stated per class. Regret is the platform's budget to learn from, not a verdict on the owner. Makes saying *yes* safe (gap #4).
*Hard part:* writing the policy so everyone believes it — and so it does not contradict who is accountable. *Experiment:* draft the policy text with HR, Finance and Legal. **H2**

**M-28 · The commitment portfolio advisor (advice and simulation only; parked).** A robo-*advisor* for reservations and savings plans: staged terms, utilisation targets, risk budget, back-tested simulations and scope-optimisation advice. **It never transacts:** purchases, exchanges, renewals and cancellations are never L3–L5; each is individually signed by the legally authorised buyer against a finite manifest ([06 §6](06-closed-loop-actions-and-autonomy.md), [invariant 16](08-trust-safety-and-guardrail-topics.md#4-candidate-safety-invariants-non-negotiables-to-ratify)).
*Hard part:* Finance accountability and sign-off fatigue; irreversibility stays with humans. *Experiment:* back-test on historical usage in shadow mode. **H3**

**M-29 · The contract-aware agent.** Knows EA/MACC commitments, burn-down and renewal dates; steers spend and prepares **renewal evidence packs**.
*Hard part:* confidentiality of contract data. *Experiment:* feed a sanitised contract; test burn-down forecasting. **H3**

**M-30 · Unit economics.** Cost per customer/transaction/feature linked to revenue; surfaces unprofitable tenants (a powerful lens for SaaS builders).
*Hard part:* mapping telemetry to cost. *Experiment:* one service. **H3**

**M-31 · The cost-of-nines explorer.** Show the **price of reliability** (zone redundancy, DR, tiers) so owners choose consciously: *"the next nine costs €X/month"* — the WAF reliability-vs-cost trade-off made tangible.
*Hard part:* presenting without nudging into under-protection. *Experiment:* five services. **H2**

---

## F. Governance & trust

**M-32 · The natural-language policy compiler.** *"No dev resource runs at night unless tagged."* → a compiled policy envelope, scheduled actions, preventive policy, and a simulated impact report — for humans to ratify.
*Hard part:* ambiguity in natural language. *Experiment:* ten sentences compiled and judged by reviewers. **H3**

**M-33 · The exception court.** Exceptions **expire**. At expiry the Historian presents the case for renewal, and owners re-justify with evidence — no immortal exceptions.
*Hard part:* fatigue. *Experiment:* an expiry campaign over existing exceptions. **H2**

**M-34 · Spend anomalies as a security signal.** A sudden compute or egress spike (mining, exfiltration) is routed to the SOC with context; conversely, security findings imply cost.
*Hard part:* shared ownership between SecOps and FinOps. *Experiment:* a tabletop exercise with the SOC. **H3**

**M-35 · FinOps for the agents themselves.** The crew optimises its own token and compute spend: model routing (small vs large), caching, batching, cut-offs — and publishes **€ per case** and **€ saved per € spent**.
*Hard part:* none conceptually — it is the integrity test of the whole idea. *Experiment:* instrument from day one. **H1**

---

## G. Wild cards

**M-36 · The cost whisperer in the IDE.** Hints while writing infrastructure-as-code or app config, via the developer's existing assistant: *"this SKU is 3× the typical choice for this pattern"*. **H3**

**M-37 · Adjacent-spend scopes.** The same loop for **SaaS and developer-platform spend**: inactive licences and seats, capacity add-ons, build minutes, idle developer environments, AI/Copilot seats and capacity. **H4**

**M-38 · Multi-cloud visibility via an open cost format (retired).** Ingest other clouds' cost data for *visibility and ownership*, while actions remain Azure-native. **Retired in v2:** it conflicts with the founding constraint *Microsoft technology only* (F2) and widens scope beyond what Release 1 can prove. (Importing *Azure's own* FOCUS export is native and unaffected.) Re-open only if the constraint itself changes. **H4**

**M-39 · Savings stories.** Auto-generated, owner-approved "what we fixed and what we learned" posts for internal communities — culture as a by-product. **H3**

**M-40 · FinOps tabletop game.** The Waste Lab reused as a training game where teams practise decisions against a simulated estate. **H3**

---

## Quick map

| | **Low trust risk** | **Higher trust risk** |
|---|---|---|
| **High wow** | Time Machine (M-14) · Shift-left bot (M-08) · Waste Lab (M-22) · Open Waste Rules (M-21) · Pricing Radar (M-12) · Cost-of-nines (M-31) · Cost SLOs (M-11) | Commitment advisor (M-28, advice only) · Voice brake (M-04, parked) · Agent-to-agent negotiation (M-02, parked) · *Meeting-intent mining (M-05) — retired* |
| **Quietly valuable** | Exception court (M-33) · Preview-environment reaper (M-16) · Duplicate data (M-17) · Context mining (M-18) · FinOps for agents (M-35) | Savings dividend (M-26) · Code-level PRs (M-15) |

---

## Decision status (v2)

| Status | Meaning | Ideas |
|---|---|---|
| **Enabler** | A foundation that Release 1 needs | **M-14** Time Machine (as an Assess-mode replay, no writes) · **M-22** Waste Lab (the evaluation harness) · **M-35** FinOps for the agents (instrument from day one — it feeds kill criterion K3) · **M-25** Confidence calibration league (calibration is measured on the Time Machine replay) · **M-27** Blameless regret (the policy text that makes saying *yes* safe) |
| **Candidate** | Research queue; no commitment | M-06 · M-08 · M-09 · M-11 · M-12 · M-15 · M-16 · M-17 · M-18 · M-21 · M-23 · M-24 · M-30 · M-31 · M-32 · M-33 · M-34 · M-36 · M-39 · M-40 |
| **Parked** | Kept, with a **re-open trigger** | **M-01** Cost Court (Release 1 shows Challenger catch and regret numbers, and a contested case type where debate adds value) · **M-02** (human-run multi-owner cases prove the pattern first) · **M-03** Review Room (the written flows are trusted; text first) · **M-04** (a service owner and security record a safe-to-pause contract (decision D18) *and* the write-safety harness passes) · **M-07** (the secure step-up design passes security review and attention data exists) · **M-10** (schedules are parked until the loop is proven) · **M-13** (with M-28; a commitment scenario is un-parked) · **M-19** (scale rules are un-parked) · **M-20** (Release 1 is done and a design-review partner exists) · **M-26** (a Finance-reconciled saving exists and a baseline policy is agreed) · **M-28** (Release 1 proves the loop and Finance maintains an authorised-signer register) · **M-29** (with commitments) · **M-37** (adjacent spend scopes, after the Azure loop is proven) |
| **Retired** | Removed; reason recorded | **M-05** (mines people's conversations; works-council and GDPR exposure) · **M-38** (conflicts with *Microsoft technology only*) |

No moonshot is in Release 1 itself: Release 1 is deliberately built from the catalog's best-evidenced plays ([02](02-opportunity-catalog.md), [plan/00](../plan/00-follow-up-plan.md)). The moonshots earn a place by what Release 1 teaches.

Next: how we measure success → [10](10-value-metrics-and-economics.md).
