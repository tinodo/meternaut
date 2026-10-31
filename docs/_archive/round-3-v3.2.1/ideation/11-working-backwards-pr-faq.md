# Working Backwards — the press release from the future (and the tough questions)

> **Status:** Ideation **v3** (revised after rubber-duck round 2; v2 archived [here](../_archive/round-2-v2/ideation/11-working-backwards-pr-faq.md), v1 [here](../_archive/round-1-v1/ideation/11-working-backwards-pr-faq.md)) · **Date:** 2026-10-30 · Part of the [north-star vision](01-north-star-vision.md)
> **Read this as fiction written to test the idea.** "Contoso", the people and every number are invented for illustration. If a sentence here would embarrass us in a real launch, the idea needs to change — that is the point of writing it.

---

## PRESS RELEASE (fictional, dated a day in the future)

### Contoso turns Azure "recommendations nobody reads" into savings nobody has to chase — with AI agents that ask, act and prove, while humans stay in control

*An open-source crew of Microsoft Foundry agents finds waste in how Azure is actually used, asks the right owner in Teams, carries out the approved fix safely, and proves the saving to Finance.*

**CITY —** Contoso's cloud costs were not a mystery. Cost Management showed where the money went; Azure Advisor listed what could be saved. Yet the same waste returned every quarter: gateways scaled up for an event and never scaled down, log workspaces ingesting terabytes nobody queried, environments that outlived their projects, and hundreds of resources nobody could name an owner for.

"We had recommendations addressed to nobody, and savings that never got verified," said **Priya Nair**, Contoso's (fictional) head of cloud platform. "Our engineers were not careless. They were busy, they did not know Advisor existed, and nobody wanted to be the one who broke production."

Contoso adopted *Azure Cost in Action*, an open-source system in which a **crew of AI agents** continuously studies how Contoso's estate is *used*, not only what it costs. For every opportunity the crew builds an evidence-backed case, works out who owns the resource — following the directory when tags are missing, and asking when it cannot tell — and has a **challenger agent try to refute the case** before any human sees it.

Owners then get **one clear ask in Teams**, in their language, with the evidence, the trade-offs and a safe one-tap action. A platform engineer sees: *"Your user-VPN gateway has never needed more than a fraction of its scale units in 90 days. Scaling down saves about €X/month and can be scaled back up for 14 days. Microsoft advises planning for downtime, so I suggest an evening window — and I need each business unit that uses the gateway to confirm first."* She taps **Approve for Thursday's window**. The crew makes the change, watches the service for harm, and one week later reports the **verified** saving — measured against a counterfactual, reconciled to the invoice.

"The first thing that convinced me was the **regret report**," said **Lars Jensen**, Contoso's (fictional) FinOps lead. "Every week the agents show me what they got wrong. Two rollbacks last month. Both explained. That's why I trusted giving them more room."

For low-risk, repeatable actions — putting development environments to sleep at night, for example — Contoso's FinOps lead and security team ratified **policy envelopes**, and each team **enrolled** in the ones it wanted, so the crew acts within human-authored rules and reports afterwards. Anything irreversible still needs at least two humans, and **commitment purchases are never automated**: each is signed by the authorised buyer against a finite manifest.

"In the quarterly review, the finance partner asked the AI participant — clearly labelled as AI — why commitment utilisation dipped," said **Aïsha Bello**, Contoso's (fictional) CFO. "It answered with evidence, recorded two decisions, and executed nothing until the right people confirmed in the authenticated channel. That's the right behaviour."

Azure Cost in Action is built on Microsoft platforms, follows the Cloud Adoption Framework and the Well-Architected Framework, and is **open source**: the playbooks, evaluations and documentation are public, so customers can read exactly how a recommendation is made and contribute new ones.

**To get started,** run an **Assess** pass: it is read-only, takes a day or two, and delivers a Waste X-ray, an ownership map, a Top-20 list, and a **Time Machine** replay of what Contoso would have saved by acting on past recommendations.

---

## CUSTOMER FAQ (resource owners)

**Why am I getting a message from an AI?**
Because a resource you own appears to cost more than it should, and you are the person best placed to say yes or no. The message tells you it is AI, why you were asked, and who else could answer.

**Will it spam me?**
No. Each person has an **attention budget**. Low-value or low-risk items go to a weekly digest or are handled by a policy that you, or a delegate you named, enrolled in. You can mute a class of messages.

**What if I disagree or it's wrong?**
Tap *Not now*, *Not mine*, *Never for this resource* or just reply. Your reason becomes remembered context, with an expiry, and we don't ask again for the same reason.

**Can it change my resources without asking?**
Only if you approved that specific change, or you **affirmatively enrolled** in a policy that allows that narrow class of change in that scope. Silence is never consent. Anything irreversible needs at least two humans. **Undo depends on the kind of change, and every card says which:** configuration changes can be undone for a stated window; some changes — permanently deleted data, telemetry we stop collecting, commitment purchases — cannot, and then the card says so plainly and asks for at least two people.

**What if it breaks something?**
It watches for harm after every change and, for the kinds of change that can be rolled back, rolls back automatically; you can also undo from the card. For changes that cannot be undone nothing is fixed automatically — which is exactly why those need two people first. Reviews are blameless: they ask what the system and policy should change. The audit still records who approved what — that is attribution for learning and audit, not blame.

**Is anyone watching me?**
Not in the sense you probably mean — and here is precisely what is recorded. To send a cost question to the right person, the system reads signals about *resources and who appears to own them*: tags, deployment and activity history, directory attributes such as your team and manager. It records which resources you appear to own and what you decided about them. It does **not** score or rank people, it is not used for performance management, and managers do not get individual-level reports by default. You can see how ownership was inferred and contest it (*Not mine*). Optional signals such as collaboration data are off unless your organisation switches them on after its privacy review. Your organisation publishes the full list, the purposes and the retention periods in a disclosure statement.

---

## INTERNAL FAQ — the tough questions

**1. Why not just use Azure Advisor and Cost Management — or Microsoft's other tools?**
We *do* — they are inputs. On their own, Advisor and Cost Management detect and report: neither resolves the owner, builds a context-aware case, converses, executes, or verifies realised savings. Other first-party tools already close *parts* of a loop for *their* domains: Defender for Cloud's governance rules assign an owner and a due date to security recommendations and chase them by weekly email, with an overdue summary to the owner's manager; the Azure SRE Agent can propose an operation and run it after a human approves in Review mode; Sentinel's SOC optimization flags unused tables for Sentinel workspaces. What we **did not find** (dated, with a quarterly re-check in [research/06](../research/06-first-party-teardown.md)) is the same owner-routed, owner-approved, verified loop for **cost optimisation across Azure consumption**. So the bet is narrower than the v1 claim: **usage intelligence plus owner-centred closure**, riding first-party capabilities wherever they exist. Our hypothesis is that the **last mile**, not detection, is the bottleneck ([research/03](../research/03-finops-framework-and-evidence.md) tests that), and that **usage** (is the log table ever queried? are the gateway units ever needed?) is what billing data cannot show.

**2. What about Microsoft's own AI efforts (Azure Copilot, optimisation agents, the Azure MCP Server, the FinOps toolkit)?**
They are relevant and moving quickly; the verified state of play is in [research/01](../research/01-azure-native-landscape.md) and [research/06](../research/06-first-party-teardown.md) (ride / copy / build / contribute). The FinOps toolkit (MIT-licensed) already ships read-only agent plugins and FinOps alerts; we would ride it, not rebuild it. Our position is complementary: the open, owner-centred, workflow-first *last mile* — and a place for the community to share playbooks. Where Microsoft ships something that does a step better, we use it; **if it ships owner-routed, owner-approved execution for three or more Release-1 playbooks, we become contribute-only** (kill criterion K4).

**3. What if the AI is wrong?**
Four layers: (a) numbers are computed by deterministic tools, never generated; (b) a **Challenger**, built to an independence profile and drilled for correlated failure, tries to refute every case; (c) every action has *one* reversibility class — reversible classes are simulated, canaried and rolled back automatically, while irreversible (R3) and collection-reducing (R3-Data) classes need at least two humans (R3-Data: the owner, the data owner and security) and **no rollback is claimed**; (d) an independent **Auditor** measures regret and a **Warden** watches the agents. Humans decide, or author the policy that decides.

**4. Who is accountable when something goes wrong?**
Accountability is layered, following the customer's own RACI: the authorised business approver accepts the *workload trade-off*; the platform owner owns the *controls*; the agent steward owns the *agent's behaviour*; the organisation owns *operational accountability*. Every action is logged with agent version, evidence and approver, so "who decided this, and on what evidence?" always has an answer — as **attribution for learning and audit, not personal blame**.

**5. Doesn't this just create alert fatigue with a friendlier face?**
Only if we get attention economics wrong, which is why it's a **first-class design constraint**: value-density thresholds, attention budgets, digests, and *policy envelopes that make the trivial invisible*. The metric that guards us is **attention cost**.

**6. Can it be attacked?**
Yes, which is why the guardrail territory ([08](08-trust-safety-and-guardrail-topics.md)) starts with threats like indirect prompt injection via tags and logs, approval phishing, confused-deputy approvals and malicious community playbooks — and, since review rounds 1 and 2, evidence manipulation, insider/Buyer collusion, approval abuse, poisoned feedback, evaluation gaming, classification laundering, instrumentation creep and custodian overreach (T1–T41). We do not build before the guardrails exist, and no write test runs before a minimum write-safety harness passes.

**7. What does it cost to run?**
It is its own FinOps customer: AI inference, data access, orchestration, communication, and people are tracked per case; **economic triage** stops us spending €10 of AI to save €5; if verified savings do not exceed platform cost, the system says so and shrinks its scope.

**8. How is "savings" defined — and can Finance trust it?**
Only **verified** and **sustained** savings reach the headline, measured against a counterfactual, counted once across tools (with who contributed kept on the line) and reconciled to the invoice. **Net realised value** shows what is left after regret and platform cost. Projected savings are labelled as projections. Regret appears in the same table.

**9. Isn't looking at log content a privacy problem?**
It could be, so the design starts from *metadata and templates first*, redaction before any model sees content, and strict retention. Whether content analysis is allowed at all is an explicit guardrail decision (G4).

**10. What about regulated workloads and legal holds?**
Locks and legal holds are **never bypassable** — no exception, no emergency. Protected or regulated scopes default to *advise only*; touching them takes a distinct, pre-authorised action class with a recorded exception.

**11. Will this replace our FinOps team?**
No. It changes their job from producing reports to **authoring policy, stewarding agents and coaching teams**. Our default design makes the FinOps lead the person who holds the dial and the kill switch.

**12. Why open source?**
Trust (people can read how a recommendation is made), reach (customers and partners contribute playbooks), and credibility with security teams. The trade-offs — the trust model for community playbooks, naming/trademark, release process — are guardrail topics (G9, G11).

**13. What if the chat platform, or the model, is down?**
Fail safe: the platform degrades to *advise* or *observe*; nothing acts. Fallback channels (email) carry critical items.

**14. Does it only support Azure?**
Yes, deliberately. Multi-cloud visibility ([M-38](09-outer-rims-moonshots.md)) was **retired** because it conflicts with the *Microsoft technology only* constraint. Importing Azure's own FOCUS cost export is a separate, native feature.

**15. How do we avoid optimising away reliability or security?**
Every case shows its **WAF-pillar trade-offs**; security tooling and required retention are protected classes; "urgent" never bypasses a gate.

**16. Will it work for seasonal or "quiet but critical" workloads?**
That is exactly what the Challenger, the evidence horizon and the owner conversation are for. We prefer reversible steps (the scream-test ladder) to deletion on a hunch, and we remember the context ("quarter-end batch") with an expiry.

**17. What is the very first thing we would build?**
Nothing is built first. **Phase 0.5** is a roughly four-week kill-or-confirm sprint with **no remediation writes** — read access, a one-hour "top-10 unfixed recommendations and why" interview with the cloud CoE, a Time Machine replay, and, after a one-page outreach note is agreed, a ~10-card Wizard-of-Oz test. It has exactly **one approved instrumentation exception**: switching on query audit on pilot workspaces (with the data owner's and security's approval, a cost cap and an end date) so the evidence clock starts early. It can stop the project cheaply. Only then **Release 1**: the Owner Graph, log usefulness (advisory), P2S right-sizing (Assist level), orphans and Advisor-recommendation closure as the loop-proving vehicle, and a PTU demand-pull candidate ([plan/00](../plan/00-follow-up-plan.md)).

**18. What would make us stop?**
We define the stop criteria *before* we begin. Strawman, to be ratified in [plan/01](../plan/01-assumptions-risks-decisions.md):

| # | Trigger | Consequence |
|---|---|---|
| K1 | Fewer than 30% of well-evidenced cases decided within 14 days, and the cause is incentives | Pivot to policy-first |
| K2 | Any severity-1 incident, or two or more rollbacks per 100 actions | Freeze writes |
| K3 | Platform cost above 30% of verified savings at month 6, or no Finance-reconciled saving by month 4 | Shrink scope |
| K4 | First-party tooling ships owner-routed, owner-approved execution for three or more Release-1 playbooks | Contribute-only |
| K5 | No sponsor and no read access by week 4 | Publish the research as a guide |
| K6 | No approved publication path by week 6 | Keep it as an internal accelerator |
| K7 | Fewer than five hours a week for six weeks | Freeze |

**19. What happens when nobody answers?**
Silence is never consent. The case follows a **private-first ladder** (owner, then delegate, then an alternate or team lead, then a team post about the *case* — never naming a person, and never revealing more than the audience is entitled to see — then one team-level summary for the accountable manager); at the end a **human decides** (reroute, park with an expiry, accept the risk in writing) or the case expires. Resources with no owner go to a named **orphan custodian**, who can triage, park and restrict but needs a second authority to retire anything — never to a countdown ([05 §3](05-human-interaction-concepts.md), [07 §7](07-ownership-and-organization.md)).

**20. What does Release 1 *not* prove?**
It proves **AI-assisted closure**: owners act on well-evidenced cases, the savings are real and reconciled, and nothing is harmed. It does **not** prove that *enrolled autonomy* — a veto window (L3) or a policy envelope (L4) — is usable, trusted and economical at scale. Release 1 is mostly Advise with narrow Assist paths; enrolled autonomy is a separate, later hypothesis with its own pre-registered criteria, tested first on a bounded non-destructive class such as dev sleep schedules ([01 §4](01-north-star-vision.md)).

**21. Why not let it buy reservations on its own, as some products do?**
Because commitments are large, long and only partly reversible — and the exchange rules are tightening (reservations bought on or after 1 February 2027 are not exchangeable where savings plans cover the service). Several vendors already run *fully autonomous* Azure commitment purchasing ([research/02](../research/02-third-party-and-oss-landscape.md)); we deliberately do not compete there. Every transaction is prepared by the crew and **individually signed by the authorised buyer** against a finite manifest ([06 §6](06-closed-loop-actions-and-autonomy.md)). The trade-off is stated plainly: an autonomous engine will capture more rate savings than a signed flow — and carries a different risk.

Next: the research behind the facts → [research/](../research/) · the plan → [plan/00](../plan/00-follow-up-plan.md).
