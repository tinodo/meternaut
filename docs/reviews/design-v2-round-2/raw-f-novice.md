# Round 2 · F — Novice reader (model: claude-haiku-5.5)

> Raw report, saved exactly as the reviewer returned it (everything below the rule). The reviewer read only `docs/design/README.md` and `docs/design/01-goals-and-scope.md`, as a cloud engineer who had never heard of the project, and answered a fixed set of comprehension questions (commit `3543f3b`, 2026-11-01). The line numbers it cites for "goals" were taken by the reviewer with a read-only shell. The orchestrator's spot-checks are in the [disposition](disposition.md).

---

**1. WHAT IS THIS**

Azure Cost in Action is a proposed design, nothing built yet, for a team of AI agents (ten roles in five hosted agents) that keeps an Azure estate cost-efficient. It watches the bill and usage, investigates waste, asks the owner with evidence and options, and changes things only after a bound approval or inside a rule a person wrote. Then it verifies the result. Users are resource owners, FinOps leads, platform and security people. Versus Azure Advisor, it asks people and acts, and it quantifies savings rather than listing rule-based suggestions at retail prices. Versus Cost Management, it acts and explains, while budgets and alerts only notify. It deploys nothing to learn.

**2. QUESTIONS**

- **Saving found?** A Recommendation card goes to the owner (what, why, options, "do nothing", how to check). Nothing changes until approval or a human-written credential.
- **Who approves?** A person, normally the owner, for changes; two people with different roles for commitment purchases. Choice of "right owner" not stated.
- **Spends alone?** No. The AI prepares commitment purchases, two people approve, and the AI executes. No spend ceiling is stated.
- **Changes without a person?** Yes, only inside a human-written credential. How far one reaches is not stated.
- **Needs before it runs?** Subscriptions with deploy and role rights; Cost Management Reader; a Citadel hub; model quota; Entra ID P1; Microsoft 365 or web page; a Git host; six people-roles. Skills: not stated.
- **Deliberately not?** Lab deployments to learn; phase-1 model training; multi-organisation deployments; a custom portal; chat as the product; other clouds; unapproved changes.
- **Learns a new service?** From documentation, price lists, bills, cost replays, owners' answers and outcomes, each claim with a source and evidence level. Unused meters cannot be found this way.
- **Running cost?** Not stated. Its only cost figures are model outputs from a price snapshot (README 99); detail is in 10-cost-and-finops.md, which I did not open.
- **Where to start?** Not stated. I would start with 02-architecture.md, then 09-delivery-and-operations.md.

**3. CONFUSION LIST** (goals = 01-goals-and-scope.md; lines via read-only PowerShell)

- "Approval is bound and single-use": README 45. "Bound" to what? Probably one exact plan.
- "Citadel governance hub": README 9. Product or internal name? Never explained.
- "Action plane: approval, runner": README 18 (diagram). "Runner" never defined; recurs at 45, 97.
- "one component writes": README 39. Which component? Probably the runner; cannot tell.
- "Five hosted agents, ten roles": README 41. No role-to-agent mapping.
- "the judge is another model family": README 43. "Judge" undefined; probably a grading model.
- "frozen and updated memory": README 48. Cannot tell what is frozen.
- "replays of cost history under another SKU": README 33. Re-pricing past usage, I guess.
- "bill-observed and outcome-confirmed": README 33. Rank order and promotion rule only implied.
- "small approved trials": goals 40. Clashes with "no lab" (README 93); unclear if real resources change.
- "injection paths, runner roles, tool pinning": README 97. Proof-point jargon, undefined.
- "budgets of attention": goals 30. Cannot tell what is budgeted.
- "four clocks": goals 71. Which four? Not listed.
- Also undefined: "Explain, Challenge, Teach" (goals 73); "Idle floor" (86); "Stoppable at three levels" (90); "P9" (60); "cost lake" and "FOCUS" (57); "Agent 365" (104).

**4. OVERSELL**

- "keeps an Azure estate cost-efficient without waiting to be asked" (README 7): present tense for an unbuilt system.
- "it changes nothing without a bound approval" (README 9): drops the credential route that goals 44 and 84 allow.
- "a workflow can wait days for a person at no cost" (README 40): absolute, unmeasured cost claim.
- Otherwise candid: "proposed" status, unproven list (README 95–100), labelled cost figures.

**5. SCORES**

- Clarity: 3. Plain intro and tables, but "bound", "runner", "four clocks" and "P9" stay undefined.
- Honesty: 4. Status, unproven list and labelled cost figures are candid; present tense and "at no cost" overreach.
- Keep reading: 3. The problem section persuades, but no worked Case shows what an owner receives.

**6. THE FIVE SENTENCES**

1. README 7: "is a team of AI agents that keeps an Azure estate" becomes "is a proposed design for AI agents that would keep an Azure estate".
2. README 9: "it changes nothing without a bound approval" becomes "it changes Azure only after an approval bound to one exact plan (define 'bound') or inside a human-written credential".
3. README 40: "a workflow can wait days for a person at no cost" becomes "a workflow can wait days for a person at a cost not yet measured".
4. Goals 40: "and small approved trials" becomes "and trials that are small, reversible changes to real resources, approved first and listed here".
5. Goals 71: "Watch cost, usage and change on four clocks" becomes "Watch cost, usage and resource change on four named schedules, listed here with their intervals".
