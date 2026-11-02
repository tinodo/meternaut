# Cold read 3: are the checks passable, honest and safe?

## Verdict

No. A stranger can see what each check is for, but three can pass without proving the question, or spend with no stop but the control under test, so this folder is not safe to run as written.

## Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | 03-first-checks.md:39 | 8 | "no lost or repeated step" | Durable "events arrive at least once, so every step is idempotent" (11-technology-register.md:86). A correct replay fails C2, so the pass does not prove P2. | "Every forced failure resumes; a repeated step is idempotent and recorded; no step is lost." |
| 2 | Blocker | 03-first-checks.md:44 | 8 | "a loop that burns tokens" | The loop's only stop is the control under test. Budgets "only alert" and "consumption continues" (07-safeguards-and-drift.md:113); Cosmos serverless "has no spending cap" (07:121). | Cap tokens, and name who kills the loop, before it starts. The hard stop must trip inside that cap. |
| 3 | Blocker | 03-first-checks.md:40 | 8 | "recorded as tested or open" | P9 passes only when "A changed tool is rejected" (13-roadmap.md:44). Line 13 says a failure stays failed. A 15-minute probe lets an open hub pin pass. | If the hub does not refuse, record C3 failed and apply the fallback. Do not pass on "open". |
| 4 | Major | 03-first-checks.md:38 | 8 | "try to create a model deployment there" | If Policy does not deny, the check creates a billable deployment and nothing deletes it. | If the create is not denied, delete it in the same step and record C1 failed. Do not call it. |
| 5 | Major | 03-first-checks.md:38 | 5 | "The call above the limit gets 429." | 429 applies after the rate is already exceeded. The crossing call can succeed, so a working policy can fail this pass. | Allow the crossing call. Require 429 on the next one. |
| 6 | Major | 03-first-checks.md:39 | 8 | "stay inside their lines of the cost document" | Only the Azure Storage provider has a cost line (10-cost-and-finops.md:68). Scheduler cannot be priced. "The other backend" is the selection rule, not a fallback. | Add a Scheduler line before C2, or leave it unpriced and not choosable. Fallback: the own adapter, only if neither recovers. |
| 7 | Major | 03-first-checks.md:40 | 3 | "worth the cost of hosting it" | No number, no missing capability, and the cost document has no Azure MCP Server line. "Worth" does not prove P9's second question. | Write a max hosting cost and one capability the typed tool lacks, in `evaluation/`, before the check. Otherwise do not adopt. |
| 8 | Major | 03-first-checks.md:41 | 8 | "Send to an address off the allow-list" | Step (c) then sends through Graph. If the rule is missing, mail leaves the list, to an address the team need not own. | Use a team-owned mailbox that is off the list. If Graph accepts it, record failed and do not retry. |
| 9 | Major | 03-first-checks.md:41 | 4 | "a person delivers the digest by hand" | Line 13 retests a fallback against the same pass. Hand delivery cannot meet it, and phase 1a ends with a Monday e-mail (README.md:13). | Hand delivery keeps 0.5 and 1a.7 open. It is not a pass and does not meet the exit. |
| 10 | Major | 03-first-checks.md:42 | 8 | "holds the same roles as the system" | The same roles share the same blindness, so "unknown" agrees with "unknown". Design 14 says the quota id is not the agreement. The blade is unnamed. | Name the blades. One scope must be classifiable by a billing reader, or the probe is unproven. |
| 11 | Major | 03-first-checks.md:43 | 8 | "Generate 13 months of cost data" | No row shape. The how wants 15 Detectors; 1a.5 builds "ten to fifteen" (01-the-slices.md:71) and does not split the parts. Serverless has no spend cap (07:121). | Define rows and a bill cap in `evaluation/` before generation. Back-test in 1a.5 only, on at least 10 Detectors. |
| 12 | Major | 03-first-checks.md:44 | 8 | "or a written reason it cannot happen" | P7 passes when "screening catches seeded attacks" (13-roadmap.md:42). A written reason is argument. Line 7 says measurement settles these questions. | Delete the written-reason pass. A cell with no seeded attack is failed. |
| 13 | Major | 03-first-checks.md:45 | 8 | "1a.6a (start) … the closed month" | The pass needs a closed month, which only 1a.8 has, but a slice is done only when its checks pass. | 1a.6a passes when the margin and allocation rule are merged. Only 1a.8 is judged on the 30%. |
| 14 | Major | 03-first-checks.md:46 | 8 | "The matrix is filled in." | Go-live requires no cut-off title at 360 px, and a system browser or the e-mail (12-testing-the-experience.md:87). A matrix of failures still passes C9. | Pass a client only if it meets that bar. A tested e-mail fallback is a failed client, not a pass of the card. |
| 15 | Major | 03-first-checks.md:65 | 5 | "may not take security keys and passkeys" | The cited page is brokered external-IdP sign-in on Android, iOS and macOS. It does not say a Teams card's embedded view rejects Microsoft Entra passkeys. | Delete the citation, or replace it with a page that says that, after someone has read it. Keep the device test. |
| 16 | Major | 03-first-checks.md:47 | 4 | "then with a phishing-resistant method" | It runs at the start of phase 2. Authentication context is a phase 3 need and phishing-resistant sign-in a phase 4 need (13-roadmap.md:26-27). The fallback is another private route; the how already uses one. | Move those sign-ins to phases 3 and 4. If sign-in fails, fall back to the tested e-mail link. |
| 17 | Major | 03-first-checks.md:58 | 8 | "the Capability gate … cannot block" | The pass is a weakening, not a failed gate on record (line 13). Gates run in 1a.6b, but the pass says they pass on the 1a.1 release. | Record Capability failed until 1b. Run Safety, Cost and isolation before the 1a.1 release is production. |
| 18 | Major | 03-first-checks.md:49 | 8 | "Quiet within 5 minutes of the pull" | In-flight work is not ended (07-safeguards-and-drift.md:95-96). Hub-traffic refusal and contract suspension have no pass. The trip reads Hub logs (07:106); the how never says so. | Pass draining in 5 minutes; quiet only after in-flight calls end. State the Hub-down passes. Generate Hub-priced spend inside a cap. |
| 19 | Major | 03-first-checks.md:50 | 8 | "within 1 % of Cost Management's" | `BilledCost` and `EffectiveCost` differ, and Cost Management omits credits, taxes and support (design 14). The blade is unnamed. "State in writing" has no owner. | Compare `BilledCost` with that scope's actual-cost view. The FinOps lead owns the next estate. A written statement means phase 1a does not exit. |
| 20 | Major | 01-the-slices.md:89 | 4 | "Owner while the export is created" | Creating an export is an ARM write on the estate scope. Phase 1a ends at "zero writes to Azure" (01-the-slices.md:61). The system identity "may" create it. | The estate owner creates the export before 1a.2. A system export create fails the zero-write exit. |
| 21 | Minor | 03-first-checks.md:45 | 8 | "A cheaper model tier; smaller prompts" | A model-versus-bill miss is not fixed by spending less. The design chose this fallback; it does not change the failed comparison. | Correct the allocation rule or the model, then remeasure. A cheaper tier is a separate decision. |
| 22 | Minor | 03-first-checks.md:41 | 3 | "It reads right in both, and the check passes." | "Reads right" is not a pass. The six questions are about a change (12-testing-the-experience.md:13); a digest may have none. | Judge the four AI marks, plus questions that apply. None applying is not a comprehension pass. |
| 23 | Minor | 03-first-checks.md:38 | 3 | "an agent with no grants reaches little" | Design 06 names inference and session storage (06-security-and-governance.md:108), not "little". | Use that list in the name and the pass. |

## Sentences I would delete

- 03-first-checks.md:40 — "Whether the hub refuses at once is recorded as tested or open."
- 03-first-checks.md:41 — "It reads right in both, and the check passes."
- 03-first-checks.md:44 — "or a written reason it cannot happen".
- 03-first-checks.md:46 — "The matrix is filled in."
- 03-first-checks.md:65 — "which may not take security keys and passkeys", with the Learn link as used.

## Fact checks

**C1, token limit.** Supported, with a limit the pass ignores. 429 is after the per-minute rate is already exceeded; 403 is the quota. The crossing call can still succeed. Both API routes are listed. https://learn.microsoft.com/azure/api-management/llm-token-limit-policy

**C1, no grants.** Supported. With no explicit role, a hosted agent still has project-endpoint inference and session-storage read and write. That is design 06, not "little". https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions

**C3, hub pin.** Not found as a Microsoft feature. A Learn search for a stored fingerprint that refuses a changed tool returned no feature page. Inline rejection is already unverified (06-security-and-governance.md:72). Azure MCP Server is real; I did not read its self-hosted Foundry guide. https://learn.microsoft.com/azure/developer/azure-mcp-server/overview

**C4.** Supported. Application RBAC acts in addition to Entra grants; `Test-ServicePrincipalAuthorization` excludes those grants; the cache is 30 minutes to 2 hours and the test command bypasses it. https://learn.microsoft.com/exchange/permissions-exo/application-rbac — `sendMail` `202 Accepted` does not mean delivered. https://learn.microsoft.com/graph/api/user-sendmail

**C6.** Partly supported. Serverless bills request units and storage, one region, 5,000 RU/s per physical partition: https://learn.microsoft.com/azure/cosmos-db/serverless. Limits add 500 containers and one region: https://learn.microsoft.com/azure/cosmos-db/concepts-limits. Neither page is a spend cap.

**C9.** Unsupported as used. The page is external-IdP broker sign-in on Android, iOS and macOS. It does not document a Teams card embedded view, or Microsoft Entra passkeys there. https://learn.microsoft.com/entra/identity/authentication/concept-passkey-browser-authentication-federated-identity-provider

## Questions left unanswered

1. How many bill rows per resource-day are Team and Enterprise, and what euro cap stops C6?
2. Who writes the C8 allocation rule, and which invoice meter names join a hub log to a bill?
3. Which portal blades must C5 match if the system identity has no billing role?
4. What harness maximum bounds C7 and C12, and who kills the run if the trip does not fire?
5. Is C13's 1% actual or amortized cost, and who picks the next estate the day it fails?
