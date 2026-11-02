# Cold reader 5: build plan README, slices 0.x, before you start

Scope: README and 02 in full; 01 lines 1-58 (59-62 not analysed). Design read only for link checks: glossary anchor; roadmap section 2 and phase rows.

## 1. Verdict

Mostly no: week-0 requests could start Monday, but slice 0.1 has no check to pass and the registry rule is wrong. A stranger gets purpose, audience and phases from the README, but not what is built first, what Atlas, Citadel or the cost lake mean, or the findings number.

## 2. Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | README:61 | 5 | "no container registry" | Learn: hosted agents are container images in Azure Container Registry | Put the hosted-agent image in a registry |
| 2 | Blocker | 01:7; 01:28; 02:99 | 4 | "for most slices, a check that passes" | 0.1 cannot meet the done rule (02:99) | Give 0.1 check C0; write "every slice" |
| 3 | Blocker | 01:30, 01:45; 13-roadmap:44 | 8 | "A changed tool is caught" | P9 requires rejection; a later catch relabels a failure | P9 passes only on inline rejection |
| 4 | Blocker | 02:13 | 8 | "Give the platform team Owner on both" | Prod Owner for builders; README:57 says read-only until phase 3 | Owner on dev, Reader on prod |
| 5 | Major | README:11; 02:14, 02:17, 02:20, 02:82; 01:33 | 2 | "A Citadel governance hub"; "cost lake" | Undefined on first use (README:11 defers them to the design glossary): judge, Foundry (02:15); mapped columns (02:68); Detector (02:83); Watch, Case (01:33); hub logs (README:22) | Expand at first use, or add a term list |
| 6 | Major | README:48 | 3 | "eight to eleven months for two builders" | 56-76 person-weeks over two builders is 6.4-8.7 months; over three, 4.3-5.8 | State the overhead or correct the months |
| 7 | Major | README:22 | 3 | "The number of confirmed findings above is reached" | No number appears above; "is measured" has no threshold | Give one findings number and one threshold |
| 8 | Major | README:13; 02:70 | 1, 8 | "It is never a pass."; "cannot pass the exit" | Reply to a reviewer; a post-miss number breaks "never after" | Delete both; a miss keeps 1a open |
| 9 | Major | README:57; 01:37; 02:84 | 4, 8 | "Read-only until phase 3" | Phase 0 creates budgets and OIDC; 1a's module deploys on customer scopes | Define "write"; count deployed Azure objects |
| 10 | Major | 01:24; 13-roadmap:11-12 | 4 | "This plan adds a first kill-switch drill" | Roadmap phase 0 lacks the drill, Watch and the digest | Amend roadmap phase 0 in the same pull request |
| 11 | Major | 01:49 | 8 | "a switch with a tested fallback" | Backend choice has no owner or date; fallback unnamed | Name owner, date and fallback |
| 12 | Major | 01:53; 02:44 | 4 | "the only way the system reaches people"; "the web page" | Two channel statements disagree; the web page is defined nowhere | Delete "and the web page" or name its slice |
| 13 | Major | 02:20 | 5 | "needs Owner on it during creation" | Learn also allows a custom role; copy scope "From any storage account" is omitted | State both; add copy scope to 1a.2 |
| 14 | Major | 02:19 | 8 | "a subnet delegated to Microsoft.App/environments" | Learn: injection must be set when the Foundry account is created | Create the account after the subnet |
| 15 | Major | 02:25 | 8 | "If a request cannot be granted" | Covers 2 of 11 requests; hub, subscription, network, GitHub, Entra rows have none | Fallback per row, or "none: slice waits" |
| 16 | Major | 02:34 | 5 | "at about a fifth more per token" | Not on the cited Learn page (first 9,000 characters) | Cite the cost-document line, or delete |
| 17 | Major | 02:43 | 3 | "the margin for check C8" | No margin value; "five to ten" is a range | One number each, as starting values |
| 18 | Major | 02:86 | 8 | "Five readers, and a native speaker" | No owner or selection rule; slice 1a.7 depends on them | Platform team lead names them in week 0 |
| 19 | Major | README:57; 02:37 | 2, 4 | "no runner role exist" | "Runner" names both a deployment runner and an Azure role | Call the deployment runner "self-hosted runner" |
| 20 | Minor | 02:39 | 8 | "An always-ready instance" | Needed by 0.2; Function apps first appear in 0.4 | Change "Needed by" to 0.4 |
| 21 | Minor | 01:37-57 | 6 | "Surprise:" | Informal label on six slices | Rename "Risk:" |
| 22 | Minor | 02:91 | 4 | "The pipeline runs in this order" | Omits the pre-flight job (02:35) | Insert it as step one |

## 3. Sentences I would delete

1. README:3 "what the first stretch costs to run and to build,"
2. README:13 "It is never a pass."
3. 01:24 "This plan adds"
4. 01:57 "the first time every part meets is the cheapest time to find that one does not fit"
5. 02:44 "and the web page"
6. 02:70 "It is a different pilot that cannot pass the exit."
7. 02:95 "Builders may use AI coding assistants." (repeats README:63)

## 4. Fact checks

1. Hosted agents "package your agent as a container image and push it to Azure Container Registry": https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents. Contradicts row 1. Sweden Central is listed. "Generally available" not stated; unverified.
2. Subnet "/27 or larger", "/24 recommended": https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks. Confirmed.
3. "Up to 48 hours": cited budgets page https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets lacks it in its first 5,000 characters; it is at https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports. Supported; citation misplaced.
4. Global "may be processed in any Azure region": https://learn.microsoft.com/azure/foundry/foundry-models/concepts/deployment-types. Confirmed. "A fifth more" is absent from the first 9,000 characters (row 16).
5. "30 minutes to 2 hours": https://learn.microsoft.com/exchange/permissions-exo/application-rbac. Not found in the first 10,000 characters; unverified.

Not checked: sendMail 202; Agent Framework prerelease; Usage Details retirement; Cost Details limits.

## 5. Questions left unanswered

1. Who writes each pass-condition number in evaluation/: the FinOps lead (02:43) or the Atlas reviewers (02:83)?
2. Who decides the Durable backend, by when, and its tested fallback (01:49)?
3. Which slice builds "the web page" (02:44)?
4. Who decides P9's second question, whether an Azure MCP Server earns its host (13-roadmap:44)?
