# Working Backwards — the press release from the future (and the tough questions)

> **Status:** Ideation v1 · **Date:** 2026-10-30 · Part of the [north-star vision](01-north-star-vision.md)
> **Read this as fiction written to test the idea.** "Contoso", the people and every number are invented for illustration. If a sentence here would embarrass us in a real launch, the idea needs to change — that is the point of writing it.

---

## PRESS RELEASE (fictional, dated a day in the future)

### Contoso turns Azure "recommendations nobody reads" into savings nobody has to chase — with AI agents that ask, act and prove, while humans stay in control

*An open-source crew of Microsoft Foundry agents finds waste in how Azure is actually used, asks the right owner in Teams, carries out the approved fix safely, and proves the saving to Finance.*

**CITY —** Contoso's cloud costs were not a mystery. Cost Management showed where the money went; Azure Advisor listed what could be saved. Yet the same waste returned every quarter: gateways scaled up for an event and never scaled down, log workspaces ingesting terabytes nobody queried, environments that outlived their projects, and hundreds of resources nobody could name an owner for.

"We had recommendations addressed to nobody, and savings that never got verified," said **Priya Nair**, Contoso's (fictional) head of cloud platform. "Our engineers were not careless. They were busy, they did not know Advisor existed, and nobody wanted to be the one who broke production."

Contoso adopted *Azure Cost in Action*, an open-source system in which a **crew of AI agents** continuously studies how Contoso's estate is *used*, not only what it costs. For every opportunity the crew builds an evidence-backed case, works out who owns the resource — following the directory when tags are missing, and asking when it cannot tell — and has a **challenger agent try to refute the case** before any human sees it.

Owners then get **one clear ask in Teams**, in their language, with the evidence, the trade-offs and a safe one-tap action. A platform engineer sees: *"Your user-VPN gateway has never needed more than a fraction of its scale units in 90 days. Scaling down saves about €X/month and is reversible for 14 days."* She taps **Approve for Thursday's window**. The crew makes the change, watches the service for harm, and one week later reports the **verified** saving — measured against a counterfactual, reconciled to the invoice.

"The first thing that convinced me was the **regret report**," said **Lars Jensen**, Contoso's (fictional) FinOps lead. "Every week the agents show me what they got wrong. Two rollbacks last month. Both explained. That's why I trusted giving them more room."

For low-risk, repeatable actions — putting development environments to sleep at night, for example — Contoso's FinOps lead and security team ratified **policy envelopes**, so the crew acts within human-authored rules and reports afterwards. Anything irreversible still needs two humans.

"In the quarterly review, the finance partner asked the AI participant — clearly labelled as AI — why commitment utilisation dipped," said **Aïsha Bello**, Contoso's (fictional) CFO. "It answered with evidence, recorded two decisions, and executed nothing until the right people confirmed in the authenticated channel. That's the right behaviour."

Azure Cost in Action is built on Microsoft platforms, follows the Cloud Adoption Framework and the Well-Architected Framework, and is **open source**: the playbooks, evaluations and documentation are public, so customers can read exactly how a recommendation is made and contribute new ones.

**To get started,** run an **Assess** pass: it is read-only, takes a day or two, and delivers a Waste X-ray, an ownership map, a Top-20 list, and a **Time Machine** replay of what Contoso would have saved by acting on past recommendations.

---

## CUSTOMER FAQ (resource owners)

**Why am I getting a message from an AI?**
Because a resource you own appears to cost more than it should, and you are the person best placed to say yes or no. The message tells you it is AI, why you were asked, and who else could answer.

**Will it spam me?**
No. Each person has an **attention budget**. Low-value or low-risk items go to a weekly digest or are handled by a policy you (or your manager) opted in to. You can mute a class of messages.

**What if I disagree or it's wrong?**
Tap *Not now*, *Not mine*, *Never for this resource* or just reply. Your reason becomes remembered context, with an expiry, and we don't ask again for the same reason.

**Can it change my resources without asking?**
Only if you approved that specific change, or you opted into a policy that allows that narrow class of change. Anything irreversible needs two humans. Everything has an undo window.

**What if it breaks something?**
It watches for harm after every change and rolls back automatically. You can undo from the card. The team is not penalised: regret is the platform's budget, not yours.

**Is anyone watching me?**
No. Ownership inference uses the minimum data needed, you can see how it decided, and you can contest it. It is not used for performance management.

---

## INTERNAL FAQ — the tough questions

**1. Why not just use Azure Advisor and Cost Management?**
We *do* — they are inputs. Neither resolves ownership, builds a context-aware case, converses, executes, or verifies realised savings. Our hypothesis is that the **last mile**, not detection, is the bottleneck ([research/03](../research/03-finops-framework-and-evidence.md) tests that). We also look at **usage** (is the log table ever queried? are the gateway units ever needed?) which billing data cannot show.

**2. What about Microsoft's own AI efforts (Azure Copilot, optimisation agents, the Azure MCP Server)?**
They are relevant and moving quickly; the verified state of play is in [research/01](../research/01-azure-native-landscape.md). Our position is complementary: the open, owner-centred, workflow-first *last mile* — and a place for the community to share playbooks. Where Microsoft ships something that does a step better, we use it rather than rebuild it.

**3. What if the AI is wrong?**
Four layers: (a) numbers are computed by deterministic tools, never generated; (b) a **Challenger** tries to refute every case; (c) actions are reversible by default, simulated, canaried, and gated by deterministic policy; (d) an independent **Auditor** measures regret and a **Warden** watches the agents. Humans decide, or author the policy that decides.

**4. Who is accountable when something goes wrong?**
The human who approved the specific plan, or the humans who ratified the policy envelope; every agent has a named **steward**; every action is logged with agent version, evidence and approver. The platform is built so the question "who decided this, and on what evidence?" always has an answer.

**5. Doesn't this just create alert fatigue with a friendlier face?**
Only if we get attention economics wrong, which is why it's a **first-class design constraint**: value-density thresholds, attention budgets, digests, and *policy envelopes that make the trivial invisible*. The metric that guards us is **attention cost**.

**6. Can it be attacked?**
Yes, which is why the guardrail territory ([08](08-trust-safety-and-guardrail-topics.md)) starts with threats like indirect prompt injection via tags and logs, approval phishing, confused-deputy approvals and malicious community playbooks. We do not build before the guardrails exist.

**7. What does it cost to run?**
It is its own FinOps customer: AI inference, data access, orchestration, communication, and people are tracked per case; **economic triage** stops us spending €10 of AI to save €5; if verified savings do not exceed platform cost, the system says so and shrinks its scope.

**8. How is "savings" defined — and can Finance trust it?**
Only **verified** and **sustained** savings reach the headline, measured against a counterfactual, deduplicated across tools and reconciled to the invoice. Projected savings are labelled as projections. Regret appears in the same table.

**9. Isn't looking at log content a privacy problem?**
It could be, so the design starts from *metadata and templates first*, redaction before any model sees content, and strict retention. Whether content analysis is allowed at all is an explicit guardrail decision (G4).

**10. What about regulated workloads and legal holds?**
They are **hard stops**. Protected tags, locks, legal holds and regulated environments default to *advise only* unless a recorded exception exists.

**11. Will this replace our FinOps team?**
No. It changes their job from producing reports to **authoring policy, stewarding agents and coaching teams**. Our default design makes the FinOps lead the person who holds the dial and the kill switch.

**12. Why open source?**
Trust (people can read how a recommendation is made), reach (customers and partners contribute playbooks), and credibility with security teams. The trade-offs — the trust model for community playbooks, naming/trademark, release process — are guardrail topics (G9, G11).

**13. What if the chat platform, or the model, is down?**
Fail safe: the platform degrades to *advise* or *observe*; nothing acts. Fallback channels (email) carry critical items.

**14. Does it only support Azure?**
First, yes. Visibility for other clouds via an open cost format is an outer-rim idea ([M-38](09-outer-rims-moonshots.md)) that has to be reconciled with the Microsoft-technology-only constraint.

**15. How do we avoid optimising away reliability or security?**
Every case shows its **WAF-pillar trade-offs**; security tooling and required retention are protected classes; "urgent" never bypasses a gate.

**16. Will it work for seasonal or "quiet but critical" workloads?**
That is exactly what the Challenger, the evidence horizon and the owner conversation are for. We prefer reversible steps (the scream-test ladder) to deletion on a hunch, and we remember the context ("quarter-end batch") with an expiry.

**17. What is the very first thing we would build?**
Nothing — we run a **Wizard-of-Oz pilot** (humans send the cards) to test whether owners act, then a thin end-to-end slice (see [plan](../plan/00-follow-up-plan.md)).

**18. What would make us stop?**
If owners don't respond even with excellent asks; if regret cannot be held near zero; or if platform cost persistently exceeds verified savings. We define these *stop criteria* before we begin.

Next: the research behind the facts → [research/](../research/) · the plan → [plan/00](../plan/00-follow-up-plan.md).
