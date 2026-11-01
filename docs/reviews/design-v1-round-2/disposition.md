# Design phase 1 — Round 2 disposition

**Reviewed at commit `7baddcf`** (the design after the Round-1 revisions, with the cost model of that commit; `git show 7baddcf:docs/design/<file>` reproduces what the reviewers read). Five lenses again, each on a **different model from its Round-1 lens** (four families: Gemini, Grok, GPT, Claude twice); every reviewer wrote its own raw report, saved unedited next to this file. Round 2 was asked to attack the Round-1 *revisions*, not the direction: "did every claimed fix land, is it right, and what did the fixes break?"

| Lens | Model | Raw report | Findings | ADR verdicts |
|---|---|---|---|---|
| **A** Architecture | gemini-4-argon | [raw-a-architecture](raw-a-architecture.md) | 11 (4 Critical, 7 Major) | 25 Agree, 12 Agree with changes |
| **B** Security, safety, compliance | grok-4.7 | [raw-b-security](raw-b-security.md) | 8 (3 Critical, 4 Major, 1 Minor) | 24 Agree, 12 Agree with changes, 1 Disagree (ADR-07) |
| **C** Cost and operability | gpt-6.1-sol | [raw-c-cost-ops](raw-c-cost-ops.md) | 11 (3 Critical, 6 Major, 2 Minor); 11 numbers re-derived, all matched | 13 Agree, 23 Agree with changes, 1 Disagree (ADR-26) |
| **D** AI engineering, evaluation, drift | claude-sonnet-5 | [raw-d-ai-engineering](raw-d-ai-engineering.md) | 6 (3 Major, 3 Minor); the statistics of 10 §4 recomputed, no error | 21 Agree, 16 Agree with changes |
| **E** Platform fact-check | claude-sonnet-5.5 | [raw-e-platform-factcheck](raw-e-platform-factcheck.md) | 19 (7 Major, 12 Minor); 17 prices re-derived, 15 matched | 27 Agree, 10 Agree with changes |

Totals: **55 findings** (10 Critical, 27 Major, 18 Minor); about 45 distinct issues once duplicates are merged (B-01 = A-03; C-01 = A-06; A-04 = E-05; A-09 = E-18).

**Outcome in one paragraph.** Every Round-1 *disposition* was found landed and, for the statistics, the authority chain's properties and the drift controls, right. No reviewer found a conceptual seam. What Round 2 found is what a large revision breaks: **mechanical contradictions in the Round-1 fixes**. The worst: the Approval service, which signs, also held the right to start the runner job, and Learn confirms that *Jobs - Start* can override the job's image, command and environment, so a compromised signer could run any image with the runner's identities — the "three parties, none able to complete a change alone" claim was false (B-01, A-01, A-03). The runner could not be given an approval id by a start with no template, the network rules forbade the calls the sequence needs, and the Policy decision was ordered before and after the approval in different documents (A-01, A-02). A hosted leaf that returns at once under a 2-minute idle timeout would be deprovisioned mid-run (A-04, E-05). The cost model claimed a closure it did not have: four contracts without quotas, workloads missing, euro "caps" that were forecasts, a gate plan priced as an exam seed (C-01 … C-08). **Almost every finding was accepted.** The substantive reversals are the authority chain (the signer no longer starts anything; an event-driven runner; independent verification of a Policy permit and a person's Entra-signed token), the leaf-call rule, and a cost model rebuilt around the twelve contracts, the gate plan and a per-environment inventory — which **roughly doubles the Team estimate** and says why.

## 1. Orchestrator spot-checks

Reviewer-cited facts were re-checked against their primary source before they drove a change.

| Claim (reviewer) | Check | Result |
|---|---|---|
| *Jobs - Start* accepts an execution template that overrides the image, command and environment, so whoever may start a job can use its secrets and managed identities (B-01, A-01) | Learn, Container Apps jobs, Permissions: "The Jobs - Start REST API accepts an optional execution template that can override the main and init container images, commands, and environment variables … The container can also use any managed identity configured to be available to it." | **Confirmed** — B-01 stands. The same page documents the fix: *Event* jobs "trigger job executions when there are messages in the queue" |
| `llm-content-safety` screens responses in windows of 1,000 characters by default and prompts in windows of 10,000 (B-04) | Learn policy page: `window-size` "configurable only for responses; for requests, prompts window size is always 10,000", "1,000 characters for responses"; overlap "if you don't specify a value, windows don't overlap" | **Confirmed** — the design's "10,000-character windows" for responses was wrong |
| `auth_time` is not a documented claim (B-08) against `auth_time` and `amr` are documented optional claims (E-01) | Learn "optional claims reference": `auth_time` — "Time when the user last authenticated"; `amr` — "Identifies how the subject of the token was authenticated" | **E-01 is right, B-08's premise is wrong** — the design keeps both claims and requests them (see 2.1) |
| Always-ready billing has no free grants (C-03) | Learn, Flex Consumption plan, Billing: "In always ready billing, there are no free grants" — and, found while checking, "no fewer than two always-ready instances per function or function group while zone redundancy is enabled" | **Confirmed**; the second statement is **new to the design** |
| A hosted agent is deprovisioned when no request arrives within the idle timeout (A-04, E-05) | Learn, hosted agents: "Idle — No requests for the configured idle timeout"; the timeout is 2 to 240 minutes, default 15; the Responses protocol has "background: true with platform-managed polling and cancellation"; the Invocations adapter "doesn't prescribe a status or polling contract" | **Confirmed**; the fix keeps the immediate-return design and makes it safe (see 2.4) |
| *Key Vault Crypto User* includes `keys/update/action` (E-06) | Learn built-in roles, Security: the role's data actions include `keys/read`, `keys/update/action`, `keys/backup/action`, encrypt, decrypt, wrap, unwrap, sign, verify | **Confirmed** — a signer must not hold it |
| Model router has built-in automatic failover, on by default (D-19) | Learn, model router concepts: "Failover is enabled by default — no additional configuration is required" | **Confirmed** |
| The Microsoft cloud security benchmark v2 is a preview (E-03); orchestration versioning is a preview (E-04); the Durable Task Scheduler Consumption SKU is generally available (E-08) | Learn benchmark introduction: "v2 (preview)"; Release Communications 498144 "Public Preview … Orchestration versioning", status *In preview*; 560957 "Generally Available: … durable task scheduler Consumption SKU", status *Launched*, GA 2026-04 (Learn's Durable Functions billing page still says "Consumption (preview)") | **All three confirmed** |
| Inter-region transfer is USD 0.02 per GB and a GZRS block blob in Sweden Central is EUR 0.0405 per GB-month (C-08) | Retail Prices API, 2026-10-31: Bandwidth, *Standard Inter-Region Data Transfer*, SE Central, 0.02 USD per GB; Storage, *General Block Blob v2*, *Hot GZRS*, first tier EUR 0.0405 | **Confirmed**; neither meter is in the snapshot, so both are named manual figures in the model |
| Standard-tier Content Safety has no free allowance (C-04) | Retail Prices API: *Free Text Records* and *Standard Text Records* are separate meters (EUR 0 and 0.329989 per 1,000) | **Confirmed** — the 5,000-record credit was the Free tier's |
| The design has no Detector record (D-15); the model's `--check` never read document 04 (C-01); the logical architecture still says "13 roles · 14 identities" (E-18, A-09) | `grep` over `docs/design/06`, `09`; the model's `main`/`validate`; `03` line 43 | **All three confirmed** |

**Not independently re-fetched** (taken on the reviewer's quoted source and marked in the text where the design depends on them): the AVM index status of the Bot Service module (E-09), the network-security-perimeter coverage table (E-11), the approved-models policy's prefix matching (E-17), the 48-hour wait for a vended subscription's first budget (E-15), the Cost Management export path with public access off (E-14, which is why it becomes a test). **Adjusted where two lenses disagreed:** B-08 against E-01 (above), and A-10 against Round 1's own B-lens on signing vaults (see 4).

## 2. Dispositions

**Accepted** = changed as proposed. **Adjusted** = accepted with a different fix. **Not adopted** = reason in section 4.

### 2.1 The authority chain: mechanics, keys, claims

*B-01, A-01, A-02, A-03, A-07, A-10, B-06, B-03, B-08, D-16, E-01, E-06, ADR-07 (Disagree, B)*

| Finding | Disposition | Change |
|---|---|---|
| B-01, A-03 a compromised Approval service completes a change alone (it signs *and* may start the runner job, and the broker trusts only its signature) | **Accepted** | The Approval service **starts nothing**: no `Microsoft.App/jobs/*` action. It enqueues the record id on a queue; the **runner is an event-driven job** with a queue scale rule and a template fixed by the pipeline; only the `deploy` pipeline may write or start the job, and any other start is detection D16. The **Policy service signs a permit** that binds the target hash; the **broker and the runner verify** the Approval signature, the permit signature and — for every irreversible Move, every purchase and every credential grant — the **person's Entra-signed ID token** (nonce = the target hash, audience, issuer, expiry, `auth_time`, `amr`, approver standing read live), then the epoch and deny lists, the nonce marker and the lease. Teams card actions approve in place only for the lowest reversible class. The unqualified claims are **replaced by an honest residual** (a compromised Approval service cannot fabricate a permit or a person's token; Approval and Policy together can forge only credential-based approvals within the credential's cap, scope and expiry) — 07 §3.3 and §4, 09 §4, ADR-07 and ADR-08 |
| A-01 the runner cannot receive an `approval_id` from a start with no template, and starts in parallel with the broker | **Accepted** | Resolved by the same change: the **broker acquires the lease and grants before it enqueues `run`**; the runner reads the id from its message. The `leases` container is new (A-07) |
| A-02 `snet-exec` forbids the calls the sequence needs; the Policy decision is ordered before approval in 07 and after it in 03 | **Accepted** | One order everywhere (**Policy permit → Brief → approval → signed record → broker → runner → Verifier**); a dedicated storage account **`stchain`** in each chain environment holds the queues `dispatch`, `run`, `verify` and `spine-events` (ids only); the spine reads `spine-events` through a queue-triggered function; Policy and the Audit Writer take internal ingress, the broker, runner and Verifier none; the outbound allow-list of `snet-exec` is enumerated — 04 §6, 03 §4, 07 §3.1 |
| A-07 no `leases` container; the chain's reads of `controls` are not granted | **Accepted** | Fifteen containers (`leases` added); `controls` is read by every chain service with a cache of at most 60 seconds and **a stale cache fails closed** — 06 §7.2, 07 §3.1 |
| B-06 fail-closed trusts the Audit Writer's acknowledgement; the nightly check is the writer's own | **Accepted** | The broker, runner and Verifier **read their appended block back** and match its hash before they proceed; the nightly verifier is a **separate identity and code path** — 07, 06 §7.3 |
| A-10 six signing vaults, the Audit Writer is a synchronous single point, rollbacks need a ledger entry | **Adjusted** | **Kept:** a vault per signing party (see 4). **Accepted:** a rollback to the pre-state named in the signed record **runs without a ledger entry** from a signed outbox and the gap is flagged D19 and reconciled; **signed human approvals are kept** in `approval-records` while the Audit Writer is down and dispatched once their entry commits; key rotation is **one scheduled workflow** (RB-12), not six procedures |
| D-16 an autonomy credential can be withdrawn while an approval that rests on it sits in a queue | **Accepted** | The broker checks the credential's **live status** at grant; a withdrawal has its **own scoped deny list**, separate from the all-approvals epoch — 07, 09 §3 |
| E-06 *Key Vault Crypto User* lets a signer re-enable a disabled key | **Accepted** | Custom roles: `acia-signer` (`keys/read` and `keys/sign/action` on the party's own vault) and `acia-key-reader` (`keys/read`, key-scoped, for the verifiers); DR-19 checks that no signing identity holds `keys/update/action` |
| B-03 the audit ledger is listed as a store of names, e-mails and Teams ids | **Accepted** | 08 §4.1's cell corrected; an **L1 property test**: the ledger-entry schema rejects `name`, `email`, `upn`, `oid` and Teams-id fields (10 §2, 06 §7.3) |
| B-08 `auth_time` is stored where 07 says it does not exist: drop it | **Not adopted** (E-01 is right) | `auth_time` and `amr` are documented optional claims; the **app registration requests both**, the verifiers require `auth_time` later than the approval's creation and `amr` to contain `mfa`, `max_age` is not used (undocumented), and S-ID-3 asserts both arrive for a web sign-in and for a Teams single sign-on. 07 §3.4 and §4 corrected; ADR-08's "*to confirm*" removed |
| ADR-07 Disagree (B) | **Accepted** | ADR-07 and ADR-08 rewritten for the above; status Proposed with the changes |

### 2.2 Untrusted text, injection layers, the repository

*B-04, B-05, E-11, E-12, E-16, E-17, E-09*

| Finding | Disposition | Change |
|---|---|---|
| B-04 the screening windows are misstated; taint is enforced in the agent process; the group fallback of ADR-06 is a hole | **Accepted** | Responses are screened in windows of **1,000 characters by default** (configurable, overlap optional), prompts in windows of 10,000 — every "10,000-character window" that meant responses is fixed in 04, 07, 09, 13. **Taint is enforced in the tool service and at the hub**, not in agent middleware: a write tool refuses a call whose envelope taint is `untrusted` unless the field is on its allow-list. ADR-06's fallback **fails closed** |
| B-05 one injected pull request to `moves/**` plus one CODEOWNERS merge reaches `deploy`; `pr-spoke` contradicts the base-branch rule | **Accepted** | `moves/**` needs **two approvers (not the author) before merge**; a Move's schema has **no executable field**; `pr-spoke` runs **after the merge**, inside `deploy`; the agents' repository credential is a GitHub App installation scoped to the data paths, its key in the secrets vault; the human step that turns a method proposal into a pull request is **named** (the *method desk*, D-18) — 07 §9, 11 §3 |
| E-12 a vendor quotation is not verbatim | **Accepted** | quoted exactly or without quotation marks (02, 04, 07, 09) |
| E-11 network security perimeters do not cover every resource named | **Accepted** | Storage, Key Vault and Foundry are covered both ways; **AI Search is inbound-only** and Cosmos DB is preview, so Search's outbound path stays on private endpoints and shared private links — 07 §7 |
| E-16 layer 6 (per-tool authorisation) is labelled GA | **Accepted** | *Evaluated* (S-GW-3); separate servers per trust class is the generally available fallback |
| E-17 the approved-models policy matches asset ids by prefix | **Accepted** | AI-1's asset ids end with `/`, asserted by the exam — 08 §3 |
| E-09 the AVM Bot Service module is only Proposed | **Accepted** | stated; Bot Service and the Durable Task Scheduler are plain Bicep behind a thin local module — 11 §2 |

### 2.3 Legal and privacy statements

*B-02, B-07*

| Finding | Disposition | Change |
|---|---|---|
| B-02 the logical architecture lets small counts leave a single tenant | **Accepted** | 03 §3 Z5: in single-tenant mode **no counts, however small, leave the tenant**; counts flow to the Commons only in the opt-in multi-tenant mode with the written thresholds |
| B-07 legal effect (the open-source exemption) is asserted where the design promised *to confirm* | **Accepted** | 08 §2.1 says *to confirm with counsel* |

### 2.4 The leaf call, the spine and recovery

*A-04, E-05, A-05, E-04, E-08, E-10, C-08*

| Finding | Disposition | Change |
|---|---|---|
| A-04, E-05 a leaf that returns a run id under a 2-minute idle timeout is deprovisioned mid-run; "record written" wakes the spine on the first record | **Adjusted** | The reviewers proposed holding the request open or polling. **Decision:** keep the immediate return, and make it safe: **each role's idle timeout is at least its p99 active time plus a margin** (Detective 20 minutes, Skeptic and Economist 10, Diplomat 15, Triage and Auditor 5; priced as billed, the larger of active time and timeout); **completion is one terminal `run-completed` event** emitted at handler exit by the leaf wrapper — a record written during the run is data, not a signal — with the spine's deadline timer as backstop. **Fallbacks decided by spike S-HOST-1** (whose test is now "a leaf that returns at once and works ten minutes with no further request: does it finish, and what is billed?"): hold the `POST /invocations` request open (server-sent events), or the Responses protocol's background mode with platform-managed polling. The resilient-task APIs stay off — 05 §4–§5, 09 §5, 14 |
| A-05 the task hub is not restored, so in-flight case budgets and multi-day timers are lost; 11 §8 and 05 §4 disagree on instance ids | **Accepted** | per-case spend and every timer deadline are **persisted in `cases` and `budgets`**; a restore creates a new task hub and re-opens open cases as `<workflow>:<case id>:<epoch>` **with spend and deadlines rebuilt**; the instance-id format is `<workflow>:<case id>` everywhere — 05 §4, 06 §7.6, 11 §8 |
| E-04 orchestration versioning is a preview and absent from the register | **Accepted** | added to 09 §5 with its fallback (a new orchestrator function name per breaking change, the old one drained) |
| E-08 the Durable Task Scheduler Consumption SKU is generally available | **Accepted** | 05 §4, 14 S-ORCH-1, 12 corrected |
| E-10 "geo-zone redundancy is not a path we can read" is over-general | **Accepted** | "unless the account is RA-GZRS or fails over (customer-managed unplanned failover may lose writes); we rely on neither" — 06 §7.6, 11 §8 |
| C-08 recovery prices copies, not the copy process | **Accepted** | the model prices the inter-region transfer, the ledger's GZRS account and the delta job; the recovery test measures **watermark age including job duration and retries**; the private route and DNS of the recovery lake are mapped |

### 2.5 Contracts, quotas, environments

*A-06, C-01, C-02, C-09, A-08, A-09, A-11 (part)*

| Finding | Disposition | Change |
|---|---|---|
| A-06, C-01 the model's quotas cover seven groups, not twelve contracts; no tokens per minute, daily limits or overrun bounds; `--check` never reads document 04 | **Accepted** | `tools/cost-model.py` now emits **every contract in every environment where it has planned work** (36 rows at Team), each with a quota, a starting tokens-per-minute limit, a daily quota for `experiment`, and an **in-flight overrun bound**; `--check` **parses the contract table of 04 §4.3** and fails on a missing or extra contract or a different alias set; `--self-test` holds negative fixtures for each defect |
| C-02 the euro "caps" are forecasts (Team `conduct` permits Sol, so 30 M output tokens would cost far more than the printed euros) | **Accepted** | the column is renamed *forecast-equivalent*; a **worst case at the dearest alias the contract lists** is generated beside it; the **spine's atomic euro reservation** is stated as the budget that holds and the hub's limit as a second, coarser layer (ADR-26, Disagree from C, answered) |
| C-09 phases create the test account in phase 3, but the pipeline promotes dev → test and `pr-spoke` expects a test hub | **Accepted** | **phase and capability profiles** decide the deployment target and the gates: phases 0–2 release dev → prod (shadow, read-only; the rehearsal uses a dry-run runner); phase 3 adds test and the chain; phase 4 the Lab; no TEST hub or Lab account is required before its phase — 11 §3, 14 §4. TEST and DEV carry synthetic data only, so their products use the **public pools** |
| A-08 the publish matrix blocks the Examiner, the Conductor, the Skeptic and W10 | **Accepted** | `case-record` read for the Examiner and Conductor, the Skeptic's read tools, and W10 assigned to a role with tools that read `evals/` and write a `method-proposals` record — 04 §4.4, 05 §2–§3, 03 §5 |
| A-09, E-18 residual diagrams and counts | **Accepted** | 03 §2 and §4 route every leaf interaction through `SPN` and `GW`; **fourteen roles · fifteen identities**; ten workflows and W3b; **nineteen** drift layers; Batch deferred in 02 §3; the README no longer says "went through two rounds" in the past tense while every ADR is Proposed |
| A-11 operational inflation: merge contracts (12 → 8), consolidate the tool services into two apps, cut vaults | **Adjusted** | the **minimum viable profile** (11 §7, 14 §4): direct hybrid retrieval, typed queries before sandboxed code, the generally available hosting fallback, **only the phase's leaves and contracts**, and an **operating budget in hours**; the merges are not adopted (see 4) |

### 2.6 The cost model

*C-02 … C-08, C-10, C-11, E-13, E-19*

| Finding | Disposition | Change |
|---|---|---|
| C-03 the Flex line mixes always-ready and on-demand rates | **Accepted** | production executions split by `FN_READY_SHARE` at the always-ready execution rates, **no free grant**; test executions on demand after one subscription's grant; replay billing stays an unverified multiplier until S-ORCH-1 |
| C-04 Standard Content Safety receives a Free-tier allowance; the volume is not derived | **Accepted** | allowance removed; records derived per route in 1,000-character windows with overlap (tool responses, replies, Surveyor text, feed, documents, attacks), screened **once where the text enters**; screening every prompt on every call is a named sensitivity |
| C-05 the per-account floor ignores Foundry file storage, an environment inventory and the day-zero Search reservation | **Accepted** | a printed **inventory** (accounts, Search units, spine and chain environments, vaults, endpoints), a Foundry file-storage line, and an **idle floor by phase** with the early Search reservation shown separately; direct hybrid retrieval is the stated baseline and Foundry IQ is off and unpriced |
| C-06 an exam seed is not the gate plan | **Accepted** | a **gate plan** (decoys, comparison cases, repeats, domain-releases a month, case-runs, tokens, reviewer hours) priced with real aliases; the Auditor, W5, W3b, W9, W10, the forger, the T3 judge, Lab experiments and DEV smoke tests are explicit workloads; Flex share is a seed (80 %) with a no-Flex sensitivity |
| C-07 cached share and written prefix do not reconcile | **Accepted** | the model takes the **prefix length** per role, bills written tokens at the write price instead of the input price, charges a session's first call at full input, and calls the baseline a **warm-cache scenario**, not a proven saving |
| C-10, C-11 ADR-27 and ADR-30 wording | **Accepted** | ADR-27 qualifies the Pilot comparison and adds incremental labour; ADR-30 says *no warm second compute estate; dual-region storage is required* |
| E-13 two regional price mix-ups | **Accepted** | West Europe's API Management Standard v2 is about 23 % cheaper than Sweden Central's; SRE Agent is €283 in Sweden Central and €349 in West Europe — 04, 05, 11, ADR-27 |
| E-19 prices are prose | **Adjusted** | price statements carry region, meter and retrieval date; generating every price line from the snapshot is not adopted for the registers |

### 2.7 AI engineering and drift

*D-15 … D-20, E-02, E-03*

| Finding | Disposition | Change |
|---|---|---|
| D-15 "compiled knowledge" (Detectors) has no record schema | **Accepted** | 06 §2 gains the **Detector record** (`id`, `version`, `validity_domain`, `blind_spots`, `novelty_trigger`, `expiry`, `state`, `depends_on`) with the nine states of the learning contract, promoted by the Move pipeline, demoted when a dependency is invalidated |
| D-17 example 4's heterogeneity model is unstated | **Accepted** | published inline with its seed, or the `evals/` test named as the source |
| D-18 nothing names how a human turns a W10 proposal into a pull request | **Accepted** | the **method desk** (see 2.2) |
| D-19 DR-7 is up to 24 hours stale between releases; the model router's automatic failover is not named | **Accepted** | DR-7 gains a continuous check for the highest-risk controls; DR-8 names automatic failover as a drift source (pin the member list, alert on a change) |
| D-20 S-NET-1 bundles three questions under one fallback | **Accepted** | split into **S-NET-1a** (toolbox pass-through), **S-NET-1b** (`/invocations` forwarding and the session parameter) and **S-NET-1c** (portal gateway), each with its own fallback |
| E-02 capability *settings* (a preview API) beside capability hosts | **Accepted** | 04 §7 and 09 §5 name both; S-NET-3 decides and tests the caller-role failure; the `foundation` pipeline identity gets the two roles for that step only |
| E-03 MCSB v2 is a preview | **Accepted** | 02 §3, ADR-29 and the register; the repository's control map stays authoritative |
| E-14 Cost Management exports into a storage account with public access off are untested | **Accepted** | an acceptance test in S-NET-2 / onboarding, with a recorded Policy exemption if only the trusted-services path works |
| E-15 a vended Lab subscription cannot have a budget at once | **Accepted** | the Lab controller creates it on its first successful call (retried up to 48 hours); the structural cap is the control until then and **no experiment starts before the budget exists** |

## 3. ADR verdicts, summarised

Of 37 ADRs, no reviewer rejected the direction of more than two. **ADR-07** (B, Disagree) and **ADR-26** (C, Disagree) are answered above. Changes to the ADRs, all still **Proposed**: **04** (prices), **05** (the managed firewall exists only with an FQDN rule), **06** (fail closed), **07** and **08** (rewritten), **12** (fifteen containers), **19** (windows; taint at the tool service), **21** (nineteen layers), **23** (`moves/**`, `pr-spoke`, AVM), **24** (`acia-signer`; public-key pins, S-ID-3), **26** (the reservation is primary; generated quotas and bounds), **27** (qualified), **29** (MCSB v2 preview), **30** (no warm second compute estate), **32** (read-back, independent verifier, rollback exemption), **33** (the leaf-call rule, task-hub restore, versioning preview, DTS Consumption GA).

## 4. Not adopted, and why

| Proposal | Reason |
|---|---|
| B-08 drop `auth_time` from the approval record | The premise is wrong (E-01, checked on Learn). The design now relies on the documented claims |
| A-10 consolidate the four ledger-entry keys into one vault with key-scoped roles | Round 1's security lens asked for a vault per signing party, Learn's guidance is a vault per application per environment, and key-scoped roles share one vault's control plane and diagnostics. The cost is about €6 per vault and per endpoint; the toil is removed by automating rotation (one scheduled workflow), not by weakening separation |
| A-11 merge `study` with `curate` and `survey` with `investigate` (12 → 8 contracts) | The contracts are the unit of budget, quota and data class (ADR-06). Merging them weakens per-group isolation for a saving that phase profiles already deliver (only the phase's contracts exist) |
| A-11 consolidate the 14 tool services into two apps | One identity per app would give each service the union of its neighbours' data access; per-tool authorisation keys on the hub's verified `azp`, but the data-plane identity is the service's own. The build toil is addressed by the profile, not by shared identities |
| A-04 poll `GET /invocations/{id}` as the primary leaf contract | The adapter prescribes no status or polling contract and Learn does not say that a poll resets the idle clock; it stays a spike-decided fallback, not the design |
| D-19 a *synchronous* full compliance check between releases | Policy compliance state is up to 24 hours old by design; the adopted continuous check is an Activity Log and Event Grid alert on assignment and exemption changes for the highest-risk controls, which is cheap and near-real-time |
| E-19 generate every price line in the registers from the snapshot | The model generates doc 12; the registers cite region, meter and date. Generating prose from the snapshot would couple the registers to a tool they do not need |

## 5. What remains open after Round 2

- **Every spike that this round added or sharpened** — S-HOST-1 (the leaf outliving its request), S-ID-3 (key pins; the two claims), S-NET-1a/b/c, S-NET-3 (capability settings), S-ORCH-1 (replay billing, versioning) — is a *to confirm*, not a result. The design says so at each place it depends on one.
- **The cost model's seeds are still seeds.** Round 2 made it honest about *what* is priced; S-COST-1 still has to say *how much* (idle billing, cache writes, replays, Flex share, screening volume, gate cadence).
- **Both second-order effects of the authority-chain redesign are untested:** queue-scoped roles by ABAC condition and identity-based queue scaling for the runner (*to confirm* on Learn in the first build sprint).
