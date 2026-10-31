# Rubber-Duck Round 1 — Review C: Strategy, positioning and sequencing

> **Reviewer:** strategy agent (independent) · **Date:** 2026-10-30 · **Reviewed:** ideation package v1
> **Status of this file:** the reviewer's report, preserved **verbatim** (formatting normalised only). The orchestrator's spot-check of every external source the reviewer cited is at the end — **its headline finding (F1) was substantially confirmed**. Dispositions are in [disposition.md](disposition.md).

---

*Scope (reviewer): read the vision, plan 00–03, research 01/03/04, and the catalog, crew, guardrails, ownership and outer-rim docs, skimming the long ones. Did not open docs/reviews (to stay independent); research/02 did not exist yet. **V** = primary source read today (documentation only, nothing exercised). **U** = unverified. Probabilities and timelines are the reviewer's judgement.*

## 1. Verdict

1. **Proceed, but narrower and faster.** The idea merits testing; the plan reaches real evidence too late.
2. **The documented wedge is partly falsified by primary sources.** An owner→manager primitive exists (Defender), approve-then-execute exists (SRE Agent), and Sentinel already flags unused tables.
3. **What survives is content, not plumbing:** usage-truth detectors, owner-as-approver for cost, verified savings, and an open ground-truth eval harness.
4. **Re-aim from "platform" to portable playbooks + owner graph + savings ledger + Waste Lab** that run on any first-party agent runtime. Foundry stays the reference runtime.
5. **Sequence by risk:** a four-week kill-or-confirm sprint before the guardrail marathon, numeric stop criteria first, and release 1 = four things.

## 2. Strategic assessment

**Q1 — Is the wedge real and defensible?** Real, but thinner than claimed.
- **Still true (V):** anomaly alerts are email-only [S1]; the Optimization Agent is preview, VM/VMSS only, and generates scripts [S2].
- **Not true (V):**
  - Defender for Cloud governance rules read an owner from a tag, set due dates, email owners weekly and email the owner's manager when overdue [S3]. It is security-scoped, but the primitive exists.
  - Azure SRE Agent has Teams/Outlook connectors, scheduled tasks, a Review mode that executes approved CLI/ARM operations, hooks for external approvals and a private skills marketplace. Learn names cost-optimisation recommendations as a Review use, though only SRE Agent Administrators can approve [S4].
  - Sentinel SOC optimization gives table-level "unused" verdicts and unused-column hints [S5].
- FinOps toolkit v15 (28 Oct) added read-only agent plugins and an ecosystem page [S6]. Cloud Custodian offers policy-as-code with actions on Azure [S7].
- **12-month odds (U, low–medium confidence):** more advice and scripts ≥85%; owner-routed cost recommendations ~40%; a first-party cost skill pack on an approve→execute runtime ~50%; owner (not admin) approval ~30%; counterfactual saving verification ~20%.
- **Implication:** Teams delivery, approvals, scheduling and orchestration are already commodity. What is defensible is validated usage-truth playbooks with ground truth, owner methodology and savings-counting rules.
- **Position:** complement (ship the owner-approval and authority gate as an SRE Agent hook or MCP tool, keep skills portable), contribute (detectors and Waste Lab into the MIT toolkit), and accept that the plumbing will be obsoleted. The moat is time.

**Q2 — Is "OSS + Microsoft-only + FULL AI + HITL + guardrails-first" coherent?** Yes. No tension is fatal, but three need fixing now.
1. **Executable community playbooks are the trust-killer.** Make playbooks declarative and read-only, able only to *reference* actions from a small maintainer-owned typed catalog. That reconciles "open" with "write access".
2. **Closed models.** Principle 15 ("no black boxes") overclaims, and version pinning is time-limited: some Foundry models retire with no deprecation period [S8]. Say instead: open logic and evidence, with the model as a replaceable, evaluated component. Microsoft's own toolkit targets Claude Code and Copilot CLI [S6], so keep "Microsoft-only" a runtime rule, not a contribution rule.
3. **Incentive, IP and liability.** A Microsoft employee shipping write-capable software that *reduces* Azure consumption is an unaddressed question (U: the reviewer cannot see internal policy).

"FULL AI" on a deterministic spine is right; state exactly where the AI does the work.

**Q3 — First customer and entry point.** An Azure-heavy enterprise with a FinOps/CoE lead as sponsor, a security contact who can grant read access now, and an existing relationship. The brief's vWAN and Log Analytics customers are ideal. Assumption: below roughly €1–2M/yr, attention cost eats the saving.
- Owners are users and CSAs are a channel; neither buys.
- Assess-as-report recreates the failure the thesis attacks (a list nobody acts on) and competes with free assessments. A generic Teams approval is commodity.
- **The wedge is Assess-and-Close:** two usage-truth detectors, an ownership map, and a human-delivered last mile on 10–15 cases, verified at +30/+60 days.
- Ownership is the deeper entry point. It unblocks cost, security and reliability recommendations alike. Start with declared + conversation, not inference.
- The CSA channel needs an approved Microsoft home.

**Q4 — Sequencing.** The plan retires the wrong risk first.
- Phase 1 (eight workstreams with security, legal, DPO, Finance, works council) is calendar-bound for a solo operator, yet is needed only before the first *write*.
- The cheapest decisive tests (A1, A2, A9, A14, A16) need no write access. The plan already lets the Wizard-of-Oz start early; make that the default.
- Spec playbooks after running them by hand. Fold spikes into slices; defer S14/S15/S21 and fold S22 into S1. Build Waste Lab early. Use risk-based duck gates instead of per-phase ones.
- At ~10 h/week (assumption; D10 is open), Phase 7 lands 9–15 months out, beyond the 12-month window.

**Q5 — Bets.** Test cheapest first:
1. **A one-hour CoE interview:** "top-10 known-but-unfixed items, and why?" Is it information, owner, effort, incentive or risk? research/03 admits there is no verifiable action-rate figure, and practitioners say the big rocks are done.
2. **A2 before B1.** "Owners act" is untestable if owner resolution fails.
3. **B8** with concrete least-privilege role definitions reviewed by a real security person, plus the IaC-PR path. S1–S4 read as live changes that IaC would revert (T11), and PRs are only spike S13.
4. **A14/A16**, with dates.

Demote B3 (a 2-day spike; the real question is B8), B7 (vanity for v1 and the largest attack surface) and B5 (deterministic savings need no counterfactual).

**Q6 — Release-1 scope.** Four things:
- **Owner Graph.** Pull S5 forward.
- **Log usefulness.** Advisory only, non-Sentinel, template-level.
- **P2S capacity right-sizing.** Assist level. V: €0.3177/unit-hour, so 100 units ≈ €23k/month at list [S9].
- **Orphans.** As the loop-proving vehicle only; detection is commodity.

Swap one AI-workload playbook (PTU utilisation) in for schedules and commitments. State of FinOps 2026 (per research/03; not re-verified): 98% manage AI spend, up from 63%, and AI-spend monitoring is the top unmet request.

- **Park:** schedules (Start/Stop v2 exists), commitments (irreversible, Finance-gated, crowded), SEC-tool economics, ADJ.
- **Outer-rim enablers:** M-22, M-14, M-35, M-27, M-25.
- **Distractions now:** M-01/02/03/04/07/10/13/19/20.
- **Never:** M-05 (works-council landmine) and M-38 (breaks F2).
- **Crew:** ship the 7-role skeleton with at most 4 LLM-backed roles.

**Q7 — Reasons not to build; stop criteria.**
- **Reasons:** plumbing is commoditising; time-to-evidence exceeds the window; the causal thesis is unproven and the long tail is where HITL economics are worst; write access in customer production from a personally maintained project; EU people-data exposure; model-retirement and eval upkeep with no contributors (R16).
- **Stop criteria are not sharp.** They are named three times (FAQ 18, R7, D11), never quantified, product-only, and have no decider or date.
- **Pre-register these strawman thresholds (reviewer's judgement):**

| Trigger | Condition | Response |
|---|---|---|
| K1 | <30% of well-evidenced cases decided in 14 days, cause = incentives | Pivot to policy-first |
| K2 | Any Sev-1, or ≥2 rollbacks per 100 actions | Freeze writes / back to L1 |
| K3 | Platform cost >30% of verified run-rate savings at pilot month 6, or no Finance-reconciled saving by month 4 | Shrink scope |
| K4 | First-party ships owner-routed + owner-approved execution for ≥3 release-1 playbooks | Contribute-only |
| K5 | No sponsor + read access by week 4 | Publish the research as a guide |
| K6 | No approved publication path by week 6 | Internal accelerator; revisit OSS |
| K7 | <5 h/week for six weeks (adjust to D10) | Freeze |

**Q8 — Name, licence, governance.**
- **Name.** "Azure" is a Microsoft mark. The reviewer verified only that the guidelines say many uses "require a license first" [S10]; the rule for third-party project names is U. Microsoft's own FinOps project avoids it. Rename now (free while private) to a neutral finalist, and use "for Azure" descriptively once OSPO agrees.
- **Licence.** Low urgency: freely changeable while private and single-author, so "hard to change later" bites only after contributors or release. MIT if hosted in a Microsoft org or aligned with the toolkit; Apache-2.0 only if counsel wants the patent grant; CC-BY for docs and playbook specs.
- **Governance.** BDFL plus 1–2 co-maintainers recruited from toolkit contributors, SECURITY.md, CODEOWNERS, and an as-is/no-SLA stance.
- **Timing.** Home and permission now (long lead), name within two weeks, licence before the first outside contribution. Stay private; D6 is right.

## 3. Findings

| ID | Severity | Where | What | Recommendation |
|---|---|---|---|---|
| F1 | **Critical** | research/01 §7–8; vision §1; FAQ 1–2 | Three headline gaps are false or overstated: owner→manager primitive (Defender) [S3], approve-then-execute (SRE Agent) [S4], "no unused-table verdict" (Sentinel) [S5]. The SRE Agent appears only as a radar row. | Restate gaps narrowly (cost domain; owner-as-approver; non-Sentinel template level; verification). Add a dated first-party tear-down, correct vision/FAQ, repeat quarterly. |
| F2 | **Critical** | plan/00 §2–3; A1/A2 | Real evidence arrives at Phase 2/7, behind an eight-workstream guardrail marathon. No capacity model (D10). | Weeks 1–4 kill-or-confirm sprint; charter gates the first write path only. |
| F3 | High | D11; FAQ 18; R7 | Stop criteria unquantified, product-only, no decider or date. | Pre-register K1–K7 before the first concierge case. |
| F4 | High | A14/R1; radar #16 | Overlap is handled as "track announcements", with no trigger, response or ride/build/contribute map. Toolkit v15 postdates research/01, and AOE is still being updated. | Add K4, the map, and a channel to the toolkit maintainers; ship runtime-portable skills. |
| F5 | High | A16; D1/D2/D6; G11-05 | Home and permission (longest lead) sit inside Phase 1. Licence is framed as a one-way door though free to change while private. The name uses the Azure mark. | Decide home and permission now; rename now; licence later. |
| F6 | High | vision §1; research/03 §4 | The central causal claim is unevidenced (no action-rate figure; "big rocks" done). | Run one-hour "top-10 unfixed and why" interviews first; classify causes. |
| F7 | High | deep-dive §1; research/04 A.2 | Log usefulness has a hidden critical path: query audit is off by default, the horizon is 90 days, and it is blind to scheduled rules and hunting. The clock hasn't started. | Enable LAQueryLogs on 3–5 pilot workspaces this week (low cost; needs the customer's change approval); advisory only. |
| F8 | High | G9-04; B7; Phase 3 | Executable community playbooks are deferred as a guardrail topic. | Declarative read-only playbooks; actions only from a maintainer-owned typed catalog; defer contribution machinery. |
| F9 | High | B8/A4; S1–S4 vs S13 | Write access is tested via generic workshops, and IaC-managed estates revert direct changes (T11). | Test with least-privilege roles and a real security reviewer; make IaC-PR a first-class path. |
| F10 | Medium | D4; catalog; doc 09; crew | Scope sprawl (6 areas, 17 families, 40 moonshots, 20 agents, 22 spikes). AI and shift-left market pull is sequenced H3/H4. | Release 1 per Q6; park the rest with re-open triggers. |
| F11 | Medium | A16; G11-05 | The incentive, IP and liability of a Microsoft employee shipping consumption-reducing, write-capable software is unstated. | One-paragraph stance; manager/OSPO sign-off. |
| F12 | Medium | principle 15; R8/T23 | "No black boxes" and pinning overclaim; models retire, some without deprecation [S8]. | Reword; budget re-evals; model-agnostic skills/MCP. |
| F13 | Medium | A20; 07 §12; 10 §1 | Per-owner learning, attention budgets and responsiveness signals drift toward worker monitoring (EU exposure; research/03 flags it, unverified). | Team/role-level metrics by default; counsel before naming individuals. |
| F14 | Low | README; plan/00 §1 | Status text claims two completed duck rounds and links research/02, which doesn't exist yet. | Keep status text true at each commit. |

## 4. What to keep

- **Evidence honesty:** V/PV labels, never stating a "percent ignored" figure, and orchestrator spot-checks.
- **The deterministic spine:** typed tools and the 13 invariants, especially no urgent bypass and "degrade to advise".
- **The seed examples** and the single provisioned-vs-used comparator.
- **Ownership states:** no inference becomes Confirmed without a human; people-signals are opt-in.
- **Wizard-of-Oz first** and the walking-skeleton crew.
- **Measurement:** regret report, counter-metrics and the platform-ROI honesty test.
- **Waste Lab and Time Machine.**
- **Private until the charter** (D6).

## 5. Three decisions this week

1. **Home and permission.** Ask manager/OSPO/legal: may I build and publish this, where does it live (Microsoft org or personal), and which naming rules apply? Rename now. Open a conversation with the FinOps toolkit maintainers.
2. **Wedge and customer.** Commit to Assess-and-Close with 1–2 named customers. Ask for a sponsor, read access, the one-hour top-10-unfixed interview, and query auditing on 3–5 workspaces.
3. **Pre-register stop criteria, time budget and the release-1 cut.** One page: K1–K7 with numbers, decider and dates; hours per week; the four-item scope with re-open triggers.

## Sources (as cited by the reviewer)

S1 `learn.microsoft.com/azure/cost-management-billing/understand/analyze-unexpected-charges` · S2 `…/azure/copilot/optimization-agent` · S3 `…/azure/defender-for-cloud/governance-rules` · S4 `…/azure/sre-agent/overview` and `/run-modes` · S5 `…/azure/sentinel/soc-optimization/soc-optimization-reference` · S6 `github.com/microsoft/finops-toolkit/releases/tag/v15`; `microsoft.github.io/finops-toolkit/agent-plugin` · S7 `cloudcustodian.io/docs/azure/gettingstarted.html` · S8 Learn, Azure OpenAI in Foundry Models deprecations and retirements · S9 `prices.azure.com/api/retail/prices` · S10 `microsoft.com/en-us/legal/intellectualproperty/trademarks`. *Unverified by the reviewer:* probabilities, timelines, internal Microsoft IP/OSS policy, EU works-council and AI Act applicability, State of FinOps and Flexera figures.

---

## Orchestrator spot-check of the reviewer's cited sources (2026-10-30)

| Source / claim | Result |
|---|---|
| **S3 Defender governance rules** — "read an owner from a tag, set due dates, email owners weekly, email the owner's manager when overdue" | **CONFIRMED.** Learn: owners can be set "by resource tag" (the rule "reads the name of the resource owner from the tag"; unspecified if none found); due dates of 7/14/30/90 days; "by default, email notifications are sent weekly to resource owners"; "by default, the resource owner's manager receives an email that shows overdue recommendations, if the manager's email is found in the organizational Microsoft Entra ID." **Scope:** security recommendations; requires the **Defender CSPM plan**; Contributor/Security Admin/Owner to create. So an owner → manager notification primitive **does** exist natively — for *security* recommendations, not (found) for cost recommendations. |
| **S4 SRE Agent** — Review mode executes approved CLI/ARM operations; only SRE Agent Administrators can approve | **CONFIRMED.** Run-modes page: Review (default) = agent proposes, "you approve or deny" for **Azure infrastructure operations (Azure CLI commands, ARM operations, similar write actions)**; Autonomous = executes and reports; per response plan / scheduled task; Hooks and Tool Access Policies for other actions; "**Only SRE Agent Administrators can approve actions**"; the agent can request temporary access via Entra on-behalf-of. The page's guidance table lists "Cost and usage reports → Autonomous". The reviewer's "Learn names cost-optimisation recommendations as a Review use" was **not found on the run-modes page** (may be elsewhere; unconfirmed). |
| **S5 Sentinel SOC optimization** — table-level "unused" verdicts and unused-column hints | **CONFIRMED, with scope.** "Data value optimizations only look at billable tables that ingested data **in the past 30 days**"; observations include *"The table wasn't used at all in the last 30 days → stop data ingestion and remove the table or move to long-term retention"*, *"not used by analytics rules … but used by other sources such as workbooks, log queries, hunting queries → analytics rule templates or Basic plan"*, and **unused columns (Preview)** (example: `ConditionalAccessPolicies` in sign-in tables). Scope: **Sentinel workspaces**, security-oriented, **30-day window**, with an explicit warning to check compliance before changing ingestion. Also notes Sentinel in the Azure portal is retired after **31 March 2027** (Defender portal only). |
| **S6 FinOps toolkit v15** | **CONFIRMED.** Release notes "New in October 2026": ecosystem page; hubs local-container guide; **agent plugins for Claude Code and GitHub Copilot CLI (5 agents, 4 commands, a FinOps hubs KQL skill, a scoped read-only Azure MCP server)**; AOE reference; instance-size-flexibility open data; PowerShell commands incl. `Get-FinOpsCommitmentDiscountEligibility`; **FinOps alerts** fixes for idle application gateway and idle public IP queries. (research/01 had only v14 / April 2026.) |
| **S8 Foundry model retirements "with no deprecation period"** | **PARTLY CONFIRMED / OVERSTATED.** Learn states "**at least 60 days' notice before model retirement for GA models**" and at least 30 days for preview upgrades. Models do retire on a vendor timetable (so version pinning is time-limited — the reviewer's point stands), but "no deprecation period" was **not** found. |
| **S9 Retail Prices API** | **CONFIRMED** (orchestrator queried it too): VPN P2S Scale Unit €0.3177/hour, West Europe. |
| S1, S2 | Consistent with research/01 (anomaly alerts email-only; Optimization Agent preview, VM/VMSS, scripts). |
| S7, S10 | Not re-fetched (low impact); treated as *Unverified*. |

**Net:** the reviewer's most consequential finding (F1) is **substantially correct**. Our research/01 §7–8 and the vision's "What the primary sources already confirm" overstated three gaps; both are corrected in v2 (see disposition).
