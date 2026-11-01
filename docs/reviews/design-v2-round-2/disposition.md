# Design v2 · Round 2 — disposition

Six independent reviewers (six model families, six lenses) challenged the written design on 2026-11-01, at commit `3543f3b`: [A · learning and the core idea](raw-a-learning.md) (gpt-6-sol), [B · platform facts on Microsoft Learn](raw-b-learn-facts.md) (claude-sonnet-5), [C · security, safety and compliance](raw-c-security.md) (grok-4.6), [D · cost honesty](raw-d-cost.md) (gpt-5.6-sol), [E · consistency, tone and readability](raw-e-consistency.md) (gemini-3.8-flash), [F · a novice who read two documents](raw-f-novice.md) (claude-haiku-5.5). After the fixes, the same reviewers re-read the changed design and looked for holes the fixes had introduced: their replies are in [closure checks](raw-closure-checks.md). This page says, finding by finding, what was accepted, adjusted or rejected, and where the change landed. The design is in [docs/design](../../design/README.md).

## What changed

| # | Finding (reviewer) | Disposition | Landed in |
|---|---|---|---|
| A1 | "The worst a wrong claim can do is put a wrong sentence": a claim can steer which Action is proposed (A, blocker) | **Accepted.** An Action is proposed only when its own guards pass on facts tools read; a disputed claim, or one below `bill-observed` for this estate, never qualifies an Action for autopilot (raised from `price-confirmed` after the closure check) | 04, 03, 06 |
| A2 | The path from a new meter to a resource, bill line and owner is illustrated, not specified (A) | **Accepted.** Explicit join; unmatched and ambiguous lines counted and never guessed; the explained, ambiguous and unmatched shares lead the report card; P6 now drills a launch with its real first invoice | 04, 08, 13 |
| A3 | "The bill settles the dispute": one lagged or rerated observation is not settlement (A) | **Accepted.** `bill-observed` needs a closed period, matched usage and change history, and a residual inside the profile's error bound; the day-zero story was rewritten to obey it | 04 |
| A4 | The frozen-versus-updated test can mistake copied knowledge for learning; power and margin unset (A) | **Accepted.** Pinned source snapshots, separate stores, three or more repeats, paired lift with an interval clustered by service, margin and minimum services set before the run, a leakage audit that voids a case but not a shared mechanism, and the capability gate applies only to a release that changes memory | 08 |
| A5 | Investigated Cases are selected, so shadow precision and learned Agenda value can be self-confirming (A) | **Accepted.** Weekly shadow audit of resources a Detector did not flag; blind grading of a sample of shadow leads; a small random share of Agenda slots with logged selection probability | 04 |
| A6 | Break-even and new-service learning cost omit people and the hub (A) | **Adjusted.** Verified net savings is the judgement (savings confirmed in the bill, less cost, people's time at the organisation's hourly rate, and applied wrong advice); the denominator caveat is stated; learning one service is its Study tokens plus one pull request review. The hub stays outside the totals, with its own-hub sensitivity | 10 |
| A7 | Five cheap additions: coverage ledger, prospective forecasts, shadow audits, Agenda exploration, planned-change observation (A) | **Accepted.** The blueprint is stored before the bill lands, so an expected absence is scored; planned changes register control meters first | 04 |
| A8 | The fourteen-part grammar can become a ceiling; 79 rows are not 79 mechanisms; qualify the overclaims (A) | **Accepted.** "A working taxonomy"; unexplained residuals kept; "79 verified traps across the fourteen mechanisms"; "pays for itself" tied to verified net savings | 04, 08, 10 |
| A9 | The Conductor's value-of-information and the Auditor's comparison belong in code (A) | **Accepted.** Ranking is arithmetic in the workflow; the model extracts inputs and explains | 03 |
| A10 | Predeclare numbers for P2, P4, P5, P8, P10 (A) | **Adjusted.** The roadmap fixes the rule (numbers are written before the measurement) rather than inventing values now | 13 |
| B1 | `llm-content-safety` is documented for Consumption (B, the only "wrong" finding) | **Rejected after checking.** The policy page lists Developer, Basic, Basic v2, Standard, Standard v2, Premium and Premium v2, not Consumption; the register was right and now links the page | 11 |
| B2 | "Eight private endpoints" is the design's own sum, not a Learn fact (B) | **Accepted.** Stated as our own sum (now eleven with the three inbound endpoints); a pre-release check counts the endpoints of a short-lived Operate environment | 02 |
| B3 | Unverified: Decisions API region claim, guardrail tool list, red-team region discrepancy, Azure MCP Server version and date (B) | **Checked, two softened.** Decisions API and guardrail list verified on Learn; the unverifiable wording became "generally available (3.x)" and "only some regions" | 05, 08, 11 |
| C1 | R1 approver is a bot assertion; a stolen bot secret forges taps (C, blocker) | **Accepted.** The bot gets the tapper's own token (Agents SDK user authorization, on-behalf-of exchange); the Approval service validates it itself; if P3 shows cards cannot carry the token, R1 opens the web page | 05, 06, 02, 12, 13 |
| C2 | `workflows` could delete the single-use marker (C, blocker) | **Accepted.** An eighth container, `consumption`: the runner may only create, no one may replace or delete | 05, 06, 12 |
| C3 | Purchase scope unbound; savings-plan role unnamed (C, blocker) | **Accepted.** The quote includes the billing subscription and the applied scope; the Savings plan purchaser role is named; shared and management-group scope is off by default | 06, 05, 12, 13 |
| C4 | Invocations are not Hub traffic, so the Engineer's isolation is a workflow promise (C) | **Accepted.** The `engineer` host validates every invocation body against one schema (unknown fields rejected); CI sends it free text | 06, 03 |
| C5 | GitHub App rights unspecified (C) | **Accepted.** Rulesets bar the App from pushing or merging to the default branch | 05 |
| C6 | Evaluate shares the Hub with Operate (C) | **Adjusted.** Same hub, dev contracts, no production backend reachable; negative tests gate every release. A second gateway would cost about €1.2k a month | 02, 06, 08 |
| C7 | Foundry conversation history is outside erasure (C) | **Accepted, cause corrected.** With the Invocations protocol the platform stores no history; session files last up to 30 days; the workflow deletes each session when its run ends | 03, 05, 06 |
| C8 | Lessons are written only by a code rule (C) | **Accepted as a stated residual.** One app has one identity; Lessons are scoped, expire and never widen a credential | 05 |
| C9 | `bot` listed under `apps/approvals` (C) | **Accepted.** `apps/bot` has its own code-owner path | 09, 11 |
| C10 | DORA and the Responsible AI Standard missing (C) | **Accepted** as adopter mapping rows; the risk class stays the adopter's call | 06 |
| C11 | Runner family roles are wide at opted-in scopes; terminating an orchestration does not stop running activities (C) | **Accepted as stated residuals** | 06, 07 |
| D1 | The own-hub sensitivity uses API Management Developer, which has no SLA (D, blocker) | **Accepted.** Standard v2, about €1.2k a month more; Developer is for evaluation only | cost model, 10 |
| D2 | The model counts an always-ready instance the text says defaults to zero (D) | **Accepted.** The model counts one; a pilot may set zero; the sensitivity shows the saving | 09, 10 |
| D3 | Triage-first escalation is not costed (D) | **Adjusted.** A triage-share sensitivity; the headline stays the high estimate and says so | cost model, 10 |
| D4 | Search units follow scenario size, not index size (D) | **Adjusted.** Units mean SLA levels (two replicas for queries, three for indexing); capacity is left to the build, where P5 compares embedded and serverless retrieval on cost per query | cost model, 13 |
| D5 | Private endpoints omit the Function apps (D) | **Accepted.** Eleven endpoints; DNS zones belong to the landing zone | 02, 10, cost model |
| D6 | The evaluation path is ambiguous: Foundry's own evaluation meters are billed apart (D) | **Accepted.** PyRIT and our own graders (tokens) by default; Foundry meters off and not in the model | 08, 10 |
| D7 | Break-even is a flattering share of managed spend (D) | **Adjusted.** See A6 | 10 |
| D8 | Token quotas do not bound Functions, Cosmos DB, Content Safety, logging or evaluation spend (D) | **Accepted.** Instance limits, a Log Analytics daily cap, excerpt caps, evaluation budgets and a daily reconciliation against the model | 07 |
| D9 | Meters were hard to audit (D) | **Accepted.** A generated appendix lists every meter and every quoted figure | cost/meters-used.md, cost model |
| E1 | The `bot` is lumped into `apps/approvals` in 09 and 11 (E, blockers) | **Accepted** | 09, 11 |
| E2 | "79 mechanisms" (E) | **Accepted** | 08 |
| E3 | Who opens pull requests: agents or workflows (E) | **Accepted.** The Engineer drafts through `pr-draft`; the Study workflow calls the GitHub API; people merge | 05, 09 |
| E4 | Graph permission on a bot said to have no Graph rights (E) | **Accepted.** One statement of what the bot's identity can do; an alert on installs for non-owners | 02, 05, 06, 07 |
| E5 | `kill switches` against `switches`; P9 overloaded (E) | **Accepted** | 07, 13 |
| E6 | "Exam-bank" file name; north-star sentence; internal digest citations (E) | **Adjusted.** The sentence and citations were replaced; the file name is **rejected**, because it names a frozen ideation file | 04, 10 |
| E7 | Unexpanded acronyms; "role" and "credential" mean several things; duplicated passages (E) | **Accepted.** Acronyms expanded; the glossary separates role, RBAC role and directory group, and credential from key and secret; duplicates reduced to one home each | README, 01 to 12 |
| E8 | Conversational first person in the Monday digest sample (E) | **Rejected.** It is sample output of the Diplomat | 04 |
| F1 | A novice could not say what it costs, where to start, what "bound", "runner", "judge", "cost lake" mean, or what "small approved trials" are (F) | **Accepted.** Glossary rows, a cost sentence and a start row in the README; trials, clocks, idle floor and stop levels explained in the goals | README, 01 |

## Closure check: what the second look found

The first fix pass itself introduced defects, which only a second look could catch.

| Finding (reviewer) | Disposition | Landed in |
|---|---|---|
| `bot` is public but the Approval service and queues are private, so taps and sends have no network path (C, blocker) | **Accepted.** Each app calls out through virtual network integration (supported for Flex Consumption, checked on Learn); only `bot` also takes public calls | 02 |
| Queue messages carry no signature (C) | **Adjusted.** A signature does not help against a compromised bot, which sends and holds the Bot Framework credential; Respond caps replies per sender and the residual is stated | 05, 06 |
| A compromised bot can install the Teams app for anyone (C) | **Accepted.** Residual stated; installs for anyone who is not an owner of record raise an alert | 06, 07 |
| The private approval page is unreachable off-network, and a silent failure looks like non-approval (C) | **Accepted.** Stated: the button fails and the request expires unapproved; an organisation may publish the page through its own front door | 06 |
| A stolen on-behalf-of token is replayable until it expires (C) | **Adjusted.** Stated: it is worth only that person's own R1 approvals; R2 and R3 never use it | 06 |
| The invocation schema covers tool arguments only (C) | **Accepted.** One schema for the whole body; unknown fields rejected | 06 |
| "FOCUS carries both on every line" is false: a purchase or an indirectly related charge may have no resource id (A) | **Accepted.** Confirmed on Learn (FOCUS conformance report); such lines join a profile by meter id and stay unattributed to a workload | 04 |
| The Prism story promotes a next-day charge to `bill-observed`, against the closed-period rule (A) | **Accepted.** Rewritten | 04 |
| `price-confirmed` confirms a price, not the effect of a change (A) | **Accepted.** Autopilot needs `bill-observed` for the meters concerned | 03, 04 |
| The leakage audit could void legitimate mechanism transfer; the capability gate blocks a release that changes no memory (A) | **Accepted** | 08 |
| Shadow leads need blind grading; "without selection bias" overclaims (A) | **Accepted** | 04 |
| People's time stays in hours; per-service cost unpriced (A) | **Accepted** (see A6) | 10 |
| The Terra sensitivity halves Sol prices, Flex included; Terra Standard meters are in the snapshot, Terra Flex meters are not (D) | **Accepted.** Re-priced from the meters: −€15 / −€129 / −€1,274 a month, not −€48 / −€179 / −€1,351 | cost model, 10 |
| Defender for AI Services has an API meter, so it is not UNVERIFIED (D) | **Accepted.** Read from the snapshot (€0.000704 per 1,000 tokens); the generated appendix now lists four quoted figures, not five | cost model |
| Defaults still price every `reason` call on Sol; search sizing does not follow index size (D) | **Adjusted.** Stated as the high estimate; capacity is left to the build and P5 | 10, 13 |
| The exam-bank file is linked under two names (E) | **Rejected.** Both documents link `../research/exam-bank-cost-traps.md`; the reviewer misread line 37 | none |
| "On-behalf-of" used before it is defined (E) | **Accepted.** Glossed where it first appears | 05 |
| "Tap", "bound", "guard metric", "hidden cases", a unit on "a few thousand", unnumbered proof points (F) | **Accepted.** Credential and Approval rows reworded; sealed cases defined; a guard metric glossed; "euros" added; P1 to P10 labelled. Reviewer F's re-read scored clarity, honesty and "keep reading" 4, 4 and 4 (first read: 3, 4 and 3) | README, 01 |
| Ten new platform claims (B) | **All ten confirmed** on Learn, including the Savings plan purchaser role, the on-behalf-of exchange, the Teams install permission, no stored history with the Invocations protocol, the search SLA replica counts, API Management Standard v2, Flex networking, queue-level roles, the Log Analytics daily cap and the guardrail tool list | none |

## Orchestrator spot-checks (2026-11-01)

Facts a reviewer cited were re-checked against the primary source before use.

| Claim | Result |
|---|---|
| B: `llm-content-safety` is documented for Consumption | **Wrong** (the page lists Developer, Basic, Basic v2, Standard, Standard v2, Premium, Premium v2); the register was right |
| C: Foundry keeps conversation history | **Real gap, wrong cause.** Learn (manage hosted sessions): with the Invocations protocol the platform stores no history; session files persist up to 30 days; a delete operation exists. The design's own sentence claiming history was the error, and was corrected |
| C: savings plans have their own purchase role | Confirmed: administrator, purchaser, contributor and reader roles exist; the purchaser needs non-billing-admin purchasing enabled |
| C: the approver must come from the approver's token | Feasible: Agents SDK user authorization with an on-behalf-of exchange exists for .NET, JavaScript and Python. Whether a Teams card action can carry it is proof point P3 |
| The Graph permission `TeamsAppInstallation.ReadWriteSelfForUser.All` | Confirmed as an application permission; the app must be in the organisation's catalogue (B, second pass) |
| D: API Management Developer against Standard v2 | Confirmed from the snapshot: €42.27 against €802.97 a month (Basic v2 €173.44); Developer has no SLA |
| D: Terra prices are not in the snapshot (the orchestrator's first note) | **Wrong, corrected in the closure pass.** Terra Standard meters (Data Zone and Global) exist; only Terra Flex meters are missing |
| D (closure): Defender for AI Services is not in the price API | **Wrong.** `Microsoft Defender for AI Services / Standard Tokens` is in the snapshot with source `api` |
| A: `ResourceId` can be null in FOCUS | Confirmed on Learn (conformance report: "Purchases may not have an assigned resource ID"; null when a resource is only indirectly related) |
| E: facts disagreeing across documents (bot placement, `kill switches`, P9, 79 mechanisms, digest sources) | Verified true |
| E: the exam-bank file should be renamed | Rejected: it is the frozen ideation research file |
| E (closure): `08:37` links a different file name | **Wrong**; both documents link the same file |
| Decisions API runs on `gpt-6-luna` only and excludes East US 2 | Verified on Learn |
| Azure MCP Server version and date; "two Learn pages list different EU regions" | Unverifiable; softened |
| Hosted agents became generally available on a given date | Not claimed beyond the user's list of updates (2026-06-02), which the register links |
| Foundry guardrail tool list | Verified on the intervention-points page (eight tools including Bing Custom Search; MCP is not supported); the design now lists it with the link |
| B: ARM what-if needs the same permissions as the deployment | Confirmed |

## Residuals the design states and does not remove

- Per-family runner identities hold write rights at every opted-in scope until revoked; disabling the identity takes about one token lifetime.
- Terminating an orchestration does not stop an activity already running; a submitted purchase is not recalled.
- Lessons are written by a code rule inside the `workflows` app; a compromised app could write a false Lesson, which is scoped, expires and never widens a credential.
- The evaluation profile shares the hub with production; separation is by contract and by negative tests that gate releases.
- A compromised bot can drop taps, post any text to people who have the app installed and install it for anyone; it cannot approve for anyone else.
- Search capacity, a Terra Flex price, the language PII price (still UNVERIFIED) and proof point P3 are measured or checked at build time, not decided here.

## Size budget

The design's size limit was raised from 42,000 to 42,500 words in the first fix pass (the reason is in `AGENTS.md` and the changelog). The closure fixes were paid for by removing duplicated passages (profile immutability, session erasure, the credential definition, the Azure MCP Server paragraph, a second publishing note), so the design stays within 42,500.
