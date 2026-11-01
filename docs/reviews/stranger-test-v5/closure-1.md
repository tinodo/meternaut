# Closure check 1: design README, 01 to 05, 14

Read 2026-11-01 16:59. The files changed at 16:51 and 16:58, so every quote was searched again at 16:59. `02:53` is `docs\design\02-architecture.md`, line 53; `NS` is `docs\01-north-star.md`. Reports: A = `raw-design-a`, B = `raw-design-b`, C = `raw-design-c`. Learn pages read (L1 to L11) are listed under the table.

## 1. Findings

| Rep | # | Sev | Status | Evidence |
|---|---|---|---|---|
| A | 1 | Blocker | CLOSED | `02:53` "the hosted agents also deploy from a zip of source code, so there is no image to build and no container registry". L1: "without building or pushing a container image". L2 (concept page) still describes an ACR image; one clause saying so would prevent a repeat finding. |
| A | 2 | Blocker | CLOSED | `README:33` "Its learning costs model tokens and the platform's own running cost"; `02:63` "storage transactions and any always-ready instance still bill". |
| A | 3 | Blocker | CLOSED | `02:63` "A hosted-agent session can idle and resume, but it is deleted after 30 idle days and is not where a person's deadline belongs". L2: "permanently deletes a session after 30 days of inactivity". |
| A | 4 | Major | CLOSED | `README:46` "the AI executes where the agreement allows"; `01:45` "Administering the agreement itself". |
| A | 5 | Major | CLOSED | `02:41` column "Changes the managed estate?"; `02:37` "only the action plane changes the resources of the estate being managed". |
| A | 6 | Major | CLOSED | `02:117` "Every model request and tool call from an agent goes through the hub." |
| A | 7 | Major | CLOSED | `02:109` "else owner declines with a reason"; `02:111` "else no answer" (remind, park, no Lesson). |
| A | 8 | Major | CLOSED | `02:102` "alt owner chooses to act"; the authorising step stays "approve (MFA)". |
| A | 9 | Major | CLOSED | `01:53` "some of them model-based (virtual machines and scale sets)"; "savings are computed at retail rates and ignore discounts and commitment coverage". L3 says both. |
| A | 10 | Major | CLOSED | `01:7` "fixed rules cover the well-known services and need revisiting whenever prices, usage or workloads change". |
| A | 11 | Major | CLOSED | `02:131` "phase 0 adds a `hub/` folder"; `01:98` "added in phase 0". The repository root has no `hub\`, so the future tense is true. |
| A | 12 | Minor | CLOSED | `README:7` "**Atlas** (a tested knowledge base of how Azure charges)"; `README:9` "**Citadel governance hub** (an API Management based gateway". |
| A | 13 | Minor | CLOSED | `01:15` "the effort to reduce it the system can state with confidence"; "cost-to-reduce" is gone. |
| A | 14 | Minor | CLOSED-BY-DELETION | "The full list, with alternatives" now occurs once (`README:50`). |
| A | 15 | Minor | PARTLY | `README:106` "describes the idea this design realises and uses the same terms". The reassurance stayed and is untrue (N-7). Replace: "The north star describes the idea this design realises." |
| A | 16 | Minor | CLOSED | `README:110` `"are measurements the [roadmap](13-roadmap.md) schedules"`; "not arguments" is gone. |
| A | 17 | Minor | CLOSED | `02:145` "A pre-release check counts the private endpoints of a short-lived Operate environment against this table". The leftover parenthetical gives provenance only. |
| B | 1 | Blocker | CLOSED | `04:51-53` "that version is billed at its full length, and so is the oldest version left in the original tier; archiving bills every version and snapshot in full". L4: "You also pay for the full content length of the oldest version in the original tier." |
| B | 2 | Major | CLOSED | `03:7` "Roles that share a hosted agent share its identity and contract; the workflow keeps them apart". |
| B | 3 | Major | CLOSED | `03:70` "the Diplomat drafts the reply or the Lesson, and after the person confirms, Respond stores the Lesson itself". `ledger-propose` on `engineer`: see N-5. |
| B | 4 | Major | CLOSED | `03:112` "In observe mode a surviving Case ends as a Lesson instead of a card; under a matching credential a covered Action goes … straight to planning". |
| B | 5 | Major | CLOSED | `03:36` "In the Study workflow it gets the Scholar's candidate claim and the receipt URLs and re-fetches the sources through `docs`." |
| B | 6 | Major | CLOSED | `03:17` "The workflow picks the alias for each step: `triage` (a small, cheap model), `reason` (a larger one)"; tools link to `05#4-tools`. |
| B | 7 | Major | CLOSED | `04:222` "(the resources the Estate model groups by purpose)"; "uses diagnostic logs or trailing billed usage, or abstains for that meter". |
| B | 8 | Major | CLOSED-BY-DELETION | "model weights" and "not in phase 1": no match in `04`. |
| B | 9 | Minor | REJECTED-OK | `03:17` keeps "until then, ten hosted agents would cost more and isolate no more where two roles read the same data", now after the positive rule (split a role only if P7 finds a path to a propose tool). It answers "why five, not ten?". Keep. |
| B | 10 | Minor | CLOSED | `03:29` "Both use fixed schemas, not free-form chat history." |
| B | 11 | Minor | CLOSED | `03:17` `"proof point P7, a measurement the [roadmap](13-roadmap.md) schedules"`; `03:23` "proof point P2 (a measurement of workflow-to-agent calls"; `README:110` lists P1 to P10. |
| B | 12 | Minor | CLOSED | `03:112` "then involves the next person the directory names (a delegate, the manager or the custodian)". |
| B | 13 | Minor | CLOSED | `03:185` "dry-run plans match the what-if results of Azure Resource Manager". |
| B | 14 | Minor | CLOSED-BY-DELETION | "working taxonomy": no match in `04`. |
| B | 15 | Minor | CLOSED-BY-DELETION | "not a measurement": no match in `04`; the story carries `04:182` "(the service is invented)". |
| B | 16 | Minor | CLOSED | `04:232` "regret (an approved change whose outcome was worse than doing nothing), boomerangs (changes reversed within weeks)". |
| B | 17 | Minor | CLOSED | `04:309` "Learning from bills, replays and small trials has limits." |
| C | 1 | Blocker | CLOSED | `14:63` "The quota id is only a hint": the offers table "lists the same id for an Enterprise Agreement and a direct Microsoft Customer Agreement subscription"; step 2 (`14:64`) settles it by billing account. L5 shows `EnterpriseAgreement_2014-09-01` on both. |
| C | 2 | Major | CLOSED | `14:42` "Pay-as-you-go subscriptions cannot export FOCUS (Learn says so); the probe may try the other export datasets". |
| C | 3 | Major | CLOSED | `14:42` "Cost Management Contributor, Contributor or Owner on the subscription; a billing role at billing scope". L6: Cost Management Contributor may create, read, update and delete exports. |
| C | 4 | Major | CLOSED | `14:65` "`AccountCostDisabled` (Enterprise Agreement: account owners cannot view charges), `DepartmentCostDisabled` (the department setting is off)"; MCA 401 means no role that can view charges. L7 agrees. |
| C | 5 | Major | CLOSED | `14:100` "An enterprise administrator with write access, or Owner or Savings plan purchaser on a subscription of the enrollment"; the MCA cell adds the owners' exemption. L8: "Since June 2025". |
| C | 6 | Major | CLOSED | `14:99` "the customer holds Owner on the subscription, which Partner Center's page requires". L9: "Verify the customer is assigned the Owner role". |
| C | 7 | Major | CLOSED | `14:34` "Partner billing roles (admin agent, billing admin) exist only in the partner's tenant". |
| C | 8 | Major | CLOSED | `14:126` "EA and direct MCA; not Windows Server, which has no scope-level option, and not customers whose CSP partner manages Azure for them". L10 says the same. |
| C | 9 | Major | CLOSED | `05:196` "removes the object id from `estate-model`, `lessons`, `ledger`, drafts and traces"; approvals and audit log are named. |
| C | 10 | Major | CLOSED | `05:144` `"(the approval classes, defined in [security](06-security-and-governance.md))"`; `03:58` "The approval classes are R1, one tap; R2, a confirmed web page; R3, two people." |
| C | 11 | Minor | CLOSED | `14:51` column "The recommendation says". |
| C | 12 | Minor | CLOSED | `14:93` "on N open recommendations". |
| C | 13 | Minor | CLOSED | `14:127` "Pay-as-you-go Dev/Test is a separate offer that needs no EA." L5 lists MS-AZR-0023P. |
| C | 14 | Minor | CLOSED-BY-DELETION | "proof point", "P4": no match in `14`; `14:149` keeps a plain acceptance test. |
| C | 15 | Minor | CLOSED-BY-DELETION | "Fabric", "Databricks": no match in `05`. |
| C | 16 | Minor | PARTLY | `05:10` defines the capitalised terms and `hat`. `14:61` "the Surveyor reads it and explains the errors" has no gloss. Replace: `"the Surveyor (the role that maps the estate, see 03-agents-and-workflows.md) reads it"`. |

Delete-list extras (not table rows). Still present: `04:184` "Nobody wrote a Prism rule.", `04:230` "People are witnesses, not oracles.", `04:276` "Learning starts from money.", `05:89` "It is the one non-Microsoft engine." Each precedes a stated mechanism or is a fact; Minor, keep. Report C fact-check 21 stands: `05:64`, `14:47`, `04:316` say "within 8 to 24 hours"; L5 says "typically available" and "could take up to 72 hours". Add "typically" and "up to".

Learn pages (https://learn.microsoft.com/): L1 `azure/foundry/agents/how-to/deploy-hosted-agent-code`; L2 `azure/foundry/agents/concepts/hosted-agents`; L3 `azure/advisor/advisor-cost-recommendations`; L4 `azure/storage/blobs/versioning-overview`; L5 `azure/cost-management-billing/costs/understand-cost-mgt-data`; L6 `…/costs/understand-work-scopes`; L7 `…/costs/cost-management-error-codes`; L8 `…/savings-plan/permission-buy-savings-plan`; L9 `partner-center/customers/give-customers-permission`; L10 `…/scope-level/overview-azure-hybrid-benefit-scope`; L11 `azure/foundry/agents/concepts/long-running-agent-resilience` (supports `03:116`: "Use a workflow engine for … durable timers").

## 2. New defects

- **N-1 · Major · `05:104`** · "which agreement it sits under and how much of the bill and the contract the system can see" · "the contract" means the customer's agreement, but the glossary defines Contract as the hub's access contract with "nothing to do with an Azure agreement" (`README:67`) · Fix: "how much of the bill, the prices and the commitments the system can see".
- **N-2 · Major · `04:278`** · "The ledger feeds the **Agenda**, the ranked list of open questions" · the paragraph above defines the Unexplained Spend list, which `NS:410` calls "the engine of the Agenda. Not the Ledger" · Fix: "The Unexplained Spend list, with residuals and discoveries, feeds the **Agenda**".
- **N-3 · Major · `04:220`, `04:236`** · "Five channels teach the system without any experiment of its own." · a small trial changes a resource an owner runs; `NS:243` says it "can move the bill", shows "a cost ceiling" first and has "automatic rollback". `04:236` says none of this and limits automatic rollback to R1 · Fix `04:220`: "Four channels read what already exists; the fifth, a small trial, changes one resource an owner already runs." Add to `04:236`: "The owner sees a cost ceiling first; the trial can raise the bill." Make rollback automatic for every trial, or amend `NS:243`.
- **N-4 · Major · `01:21`, `01:76`** · "estate knowledge never leaves the organisation"; "never share estate knowledge" · absolutes with no mechanism; `NS:242` and `13:16` allow "a privacy-reviewed scope and aggregate" that its owner agreed to share · Fix: "nothing leaves an estate except a privacy-reviewed scope and aggregate its owner has agreed to share".
- **N-5 · Major · `05:130`, `02:37`** · "agents hold only read tools and four propose tools" (`02:37` lists them: a record, a message, a pull request, a what-if) · the message draft is `channels-draft`, which `diplomat` holds (`03:14`); yet `03:15` says `engineer` is "the only contract with propose tools" and `06:97` says `diplomat` holds "no propose tool" · Fix: "three propose tools (`plan`, `pr-draft`, `ledger-propose`), held only by `engineer`, and one draft tool (`channels-draft`) for `diplomat`" in both places.
- **N-6 · Major · `README:110`** · "agent quality on verified cases" · bare "verified": the cost-trap bank's Verified rows were found on the cited Microsoft page, not confirmed by a bill (`08:30`) · Fix: "agent quality on the source-verified rows of the cost-trap bank".
- **N-7 · Major · `README:106`** · "uses the same terms" · the north star has six routes (Ask, Look, Replay, Follow, Pool, Trial; `NS:238-243`); `04:218-236` has five channels (bills, replays, owners, outcomes, small trials) and no Pool · Fix: README as in A-15; add to `04:220`: "North-star routes: Ask is owners, Look is bills, Replay is replays, Follow is outcomes, Trial is small trials; Pool is phase 5."
- **N-8 · Major · `03:163`** · "Where the agreement hides the customer's rates, the saving is an estimate" · with no readable bill the figure is a scenario priced at list prices, and a "saving" only when a bill line confirms the meter (`NS:167`); `14:55` now says "Scenario at list prices" · Fix: "Where no bill is readable, the figure is a scenario priced at list prices and the card says so; it is called a saving only when a bill line confirms the meter."

## 3. Counts and verdict

Counts: closed 41 · closed by deletion 6 · rejected-ok 1 · partly 2 · open 0.

Verdict: no, not yet. Reasoning residue is mostly gone (Minor slogans remain) and the factual errors are fixed, but a stranger still meets eight contradictions or undefined terms (N-1 to N-8).
