# Round 2 — lens D (AI engineering, evaluation and drift) — raw report

> Reviewed at commit `7baddcf` · model `claude-sonnet-5` · Round 1's lens D was `gpt-6-sol`.

## 1. Verdict in five lines

1. **Sound, and substantially strengthened.** The three-party authority chain, the Durable Functions spine, the statistical protocol and the dependency graph are rigorous engineering, not just better prose; I independently reproduced the load-bearing statistics in `10-test-and-evaluation.md` §4.
2. **What must change first:** give the *continuous* drift detectors (DR-8's fingerprint probe, DR-12's population-stability test) a powered false-alarm budget with the rigour the release gates already get, and close spike **S-NET-1**, which bundles three questions behind one fallback that does not cover the one the spine↔leaf boundary depends on: whether the hub can front a hosted agent's `/invocations` endpoint at all.
3. **The design still serves the learning system** for Atlas, Agenda and method knowledge — but "compiled knowledge" (Detectors), one of [the learning contract](../../11-the-learning-contract.md)'s six things that change, is named throughout (`09`, `05` W7) yet never given a record schema, states or expiry: the object the dependency graph and Dream both depend on does not formally exist.
4. **W10 is sound**: self-editing is blocked structurally, not by promise — no agent holds a tool that can write a prompt, rubric, tool list or gate; only `atlas-propose` (`atlas/**`) and `moves-propose` (`moves/** YAML`) exist. The human step that turns a proposal into a pull request is simply never named.
5. **Assumption**: single EU-tenant, no controls deployed yet. Every platform claim below was re-fetched from Microsoft Learn on 31 October 2026, not taken from memory or the Round-1 disposition's word; where I could not confirm a number, I say so.

## 2. Disposition audit — Round-1 findings D-01 to D-14, A-10, A-15

All sixteen are **confirmed landed and correct** — no claimed-but-absent or contradicted change found (none are Critical on this ground). Where I add independent verification beyond reading the design text, it is noted. Unqualified document shorthand below (e.g. `05` §2) resolves to `<repo>\docs\design\05-agents-and-orchestration.md`, and likewise for every other numbered design file named by its number alone.

| Round-1 ID | Disposition's claim | Where | Landed? |
|---|---|---|---|
| D-01 | bounded branching, record graph, over-claim removed | `05-agents-and-orchestration.md` §1 | **Yes** — "The spine may branch, fan out competing hypotheses and loop back to an earlier step"; the over-claim is gone |
| D-02 | roster reconciled to 15 instances; Forger/investigator independence tested empirically | `05` §2, `10-test-and-evaluation.md` §3 | **Yes** — "the investigators and an independent control … solve **Forger cases and independently authored cases**"; counts agree everywhere (§5) |
| D-03 | every tool service sanitises; moderation tested on the deployed path | `07-security-architecture.md` §5 | **Yes** — layer 1 is "a library in **every tool service that returns free text**"; the L5 test "fails closed if either is missing" |
| D-04 / A-10 | spine compared with GA Durable Functions, not only the pre-release MAF extension | `13-decisions.md` ADR-33, `05` §4 | **Yes**; Learn confirms today "Azure Storage and Durable Task Scheduler are the only supported storage providers … hosted in the Flex Consumption plan" |
| D-05 | a statistical protocol: non-inferiority, sample sizes, exact bounds, clustering | `10` §4 | **Yes** — see §4 below; three of four worked examples recomputed exactly |
| D-06 | entailment vs. receipt presence; Groundedness conflation separated | `10` §4 "What G5 checks" | **Yes**; Learn confirms verbatim: "Groundedness detection … retires on April 30, 2027" — matches exactly |
| D-07 | exam isolation is physical, not a similarity audit | `10` §3 "Exam isolation" | **Yes** — separate generators, keys, labels; post-freeze, estate-held-out credential cases |
| D-08 | a method-learning workflow (W10) added | `05` §3, `01` §3 FR-G4 | **Yes** |
| D-09 | red-teaming EU availability treated as unverified; self-hosted path mandatory | `09` §5, `10` §9 | **Yes** — the cited contradiction is still live today: the [concept page](https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent) lists France Central/Sweden Central; the [regions page](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network) says "AI red teaming is supported in the following regions. East US 2. North Central US." — unverified remains correct |
| D-10 | fingerprint probe relabelled a statistical alarm; rotating hidden cases; fail-closed | `09` §2.2 DR-8 | **Yes** — "a **statistical alarm**, not an attestation"; one new gap found (Finding D-19): the router now has **built-in automatic failover**, not named here |
| D-11 | a dependency graph from claim/data/tool/evaluator/credential to consumers | `09` §3 | **Yes**, concretely: "every record … carries `depends_on` edges … the producing service writes them when it creates the record"; points at an unspecified Detector (D-15) |
| D-12 | caching wording and model corrected | `05` §7 | **Yes** — "lives at least 30 minutes on those families" matches Learn's prompt-caching page |
| D-13 | gate evidence signed and time-bounded; G9 bound to manifest/domain/cap/expiry | `10` §4 | **Yes** |
| D-14 | Sandboxes GA; hosted agents GA June 2026 | `09` §5 | **Yes** — hosted-agents page says "generally available" verbatim; region list has **Sweden Central**, not **North Europe**, exactly as stated |
| A-15 | event-driven fast path (W3b) plus a load-test spike | `05` §3 W3b, `14-next-phases.md` §3 | **Yes** — W3b fully specified; **S-FAST-1** is a complete registered spike row |

## 3. Findings (new, Round 2; numbered D-15–D-20, continuing Round 1's D-01–D-14 sequence)

**D-15 · Major · File and heading:** `<repo>\docs\design\06-data-and-knowledge.md`, §2, *The information model* · **Quote (verbatim):** "**Move** — a tested, versioned way to change something." (the field table that follows covers Claim, Move, Case/evidence, Approval, Prediction and Lesson — no equivalent table for Detector, though the diagram node `DT` and the arrows `CL --> DT --> CA` show it is load-bearing) · **Why it matters:** `<repo>\docs\11-the-learning-contract.md`, §1, names "**Compiled knowledge** — Detectors, Moves and the investigation recipes" as one of six things that make this a learning system, with its own crosswalk entry: "**Detector and Move states** | drafted · back-tested · lab-tested · attacked · reviewed · shadow · active · demoted · retired". `05` W7 produces "detector candidates" and `09-safeguards-and-drift-controls.md` §3's dependency graph names Detectors as consumers to invalidate — but no design document gives a Detector a schema, a validity domain, an expiry or a promotion gate between states. Without it, "compiled knowledge" cannot be exam-tested, versioned or rolled back the way a Move can. **Fix:** add a Detector record to `06` §2 (`id`, `version`, `validity_domain`, `blind_spots`, `novelty_trigger`, `expiry`, `state`), routed through the same CI/review/shadow pipeline as a Move.

**D-16 · Major · File and heading:** `<repo>\docs\design\07-security-architecture.md`, §4, *Approvals that cannot be forged or reused* · **Quote (verbatim):** "Where a human has granted an **autonomy credential** for a domain, the Approval service signs a record whose basis is that credential instead of a click" · **Why it matters:** `09-safeguards-and-drift-controls.md` §3 ("Evidence, invalidation and withdrawal") says a credential "is **withdrawn automatically** when a node its evidence rests on is invalidated", and `09` §4's authority-chain table says the Policy service "reads nothing about any estate" and only "decides in code whether a rule or an autonomy credential covers the proposal" once, at signing time — no document states the credential's *live* status is re-checked at the broker's grant or the runner's execution. `07` §3.3 itself notes "Moves of a class queue behind its lease: the price is latency, not safety" — so a signed, dispatched approval can sit queued while the credential it rests on is withdrawn, and the only named recovery is the blunt, global "approval epoch", not a credential-scoped one. **Fix:** have the broker verify, at grant time, that the cited credential is still current in the Ledger, and give withdrawal its own scoped deny list distinct from the all-approvals epoch.

**D-17 · Minor · File and heading:** `<repo>\docs\design\10-test-and-evaluation.md`, §4, *Worked examples* · **Quote (verbatim):** "In a simulation of 20,000 trials (60 estates of 5 cases, discordance 0.15, a true difference exactly at the −5 point margin, strong heterogeneity between estates) the estate-level rule passed 5.1 % of candidates and the case-level rule 7.9 %; with no heterogeneity they passed 5.2 % and 5.6 %." · **Why it matters:** I reproduced examples 1–3 exactly (§4 below). Example 4 is the only one whose generative model ("strong heterogeneity") is unstated — no variance or seed, unlike the others. My own independent Monte Carlo (a per-estate random effect on the candidate-win share, 4,000 trials) gave the same direction and a similar size — case-level 8.1 % vs. estate-level 6.9 % under heterogeneity, 5.3 % vs. 5.2 % without — corroborating but not reproducing the exact figures. **Fix:** publish the heterogeneity model and seed inline, as the other three examples do, or point explicitly to the `evals/` test that is the source of truth.

**D-18 · Minor · File and heading:** `<repo>\docs\design\05-agents-and-orchestration.md`, §3, *The workflows* (W10 row) · **Quote (verbatim):** "The output is a proposal, never a change: agent identities may open pull requests only to data paths ([07 §9](07-security-architecture.md#9-supply-chain)), and prompts, tools and rubrics are not data paths, so a human opens it (assumption: the rule holds for W10 too)." · **Why it matters:** This is sounder than the hedge suggests: `04-landing-zone-and-citadel.md` §4.4's tool table shows no agent has a generic "open a pull request" tool — `atlas-propose` writes only `atlas/**`, `moves-propose` only `moves/** YAML`; no tool can touch `agents/**` or `evals/**` even in principle, so self-editing is blocked by absent capability, not convention. But no document names the mechanism by which a human turns W10's proposal into a pull request — every other write path has a named service; this one does not. **Fix:** name that human-facing tool or process explicitly.

**D-19 · Minor · File and heading:** `<repo>\docs\design\09-safeguards-and-drift-controls.md`, §2.1, *Drift in what we own* (DR-7) · **Quote (verbatim):** "Policy compliance (effects take about 15 minutes; the standard compliance cycle runs every 24 hours, so the data can be that old…)" · **Why it matters:** DR-7's detective control is honestly disclosed as up to 24 hours stale between releases, compensated only by gate **G8**'s synchronous check — which runs *at release time*, not continuously; a violation opening and closing between releases is caught by nothing in the table. Separately, I confirmed on Learn today that the model router has gained "built-in automatic failover", and "Failover is enabled by default", silently substituting a member of an already-pinned subset mid-session — a channel beyond "the pool grows" that DR-8 does not name, though its existing controls (resolved-deployment logging, fail-closed on unproven attribution) already happen to cover it. **Fix:** add a continuous synchronous policy check for the highest-risk controls, and name automatic failover in DR-8 as a drift source.

**D-20 · Major · File and heading:** `<repo>\docs\design\14-next-phases.md`, §3, *Spike register* (row **S-NET-1**) · **Quote (verbatim):** "Does the hub forward a hosted agent's `/invocations` routes and its session parameter?" (the row's Fallback column reads: "agents call the hub directly (the default); each route published as its own operation with the session as an explicit parameter; the portal gateway stays off and Policy audits it (B9)") · **Why it matters:** S-NET-1 bundles three questions (toolbox pass-through, `/invocations` pass-through, portal-gateway association) under one exit criterion and one fallback, and that fallback addresses only the third. If the hub cannot forward a hosted agent's `/invocations` routes and session parameter intact, there is no Plan B — yet `05-agents-and-orchestration.md` §4 ("Calling a leaf") rests the entire spine-to-leaf call on exactly this: "The hub is therefore the only route, and a call that skipped it would fail on RBAC at Foundry". This is the largest unverified assumption under the spine↔leaf boundary, in the one spike whose fallback does not match its primary risk. **Fix:** split S-NET-1 into its three questions with independent fallbacks; give `/invocations`-forwarding its own (for example a narrowly scoped, audited direct-to-Foundry bypass with compensating detection).

## 4. The statistics of `10-test-and-evaluation.md` §4, recomputed

Recomputed with Python 3.13's standard library (`math`, `statistics`) on 31 October 2026; no package installed.

- **Rule of three / exact one-sided bound.** `p_U = 1 − 0.05^(1/n)` reproduces the design's own table exactly: n_eff for ceilings 10/5/3/2/1 % is 29/59/99/149/299. Correct.
- **Design effect / effective sample size.** `DE = 1 + (m−1)·ρ`, `n_eff = K·m/DE` is the standard Rao–Scott cluster correction, correctly applied throughout.
- **Example 1 (G3 clustering).** 100 decoys, 20 estates of 5, ρ = 0.3: I reproduce the independent bound 2.951 %, the clustered `n_eff = 45.5`, bound **6.378 %**, and the decoys/estates table (99/99, 218/44, 664/34) exactly, once n_eff is rounded up to 99 first.
- **Example 2 (G4, clustering flips the verdict).** `D = 4/60 = 0.067`; I reproduce the independent SE of 0.052, the estate-level SE of 0.075, the design effect of 2.1, and bounds of **−0.068** (12 estates) and **−0.047** (16 estates) to stated precision. Undisclosed: the "10" in the independent-SE formula is the sum of *absolute* net counts (the minimum discordant-case count consistent with the published data), not derivable from the net counts alone without that assumption — it does not change the (correct) arithmetic.
- **Example 3 (sizing).** `n = (z_{.95}+z_{.80})²·π_disc/δ² = 494.6 ≈ 495`; clustered → 891 cases / **179** estates; the intersection–union power adjustment for `k=3` gives **792** (1.60×). All reproduce exactly. The IUT claim itself is the standard, correct result (Berger, 1982): requiring every one of `k` level-α tests to pass bounds the joint false-pass rate at α without correction, and sizing each at power `1−β/k` bounds joint power at `1−β` by the union bound.
- **Example 4 (simulation).** Direction and rough magnitude independently corroborated (Finding D-17); exact figures not independently reproducible from the design text alone.
- **Two-baseline chaining logic.** Correct: non-inferiority to only the immediate predecessor permits compounding drift (the regulatory "biocreep" problem); the anchor at `Δ = 8 > δ = 5` is the standard retention-of-effect mitigation, and "fails the second release, or the third at the latest" matches a properly calibrated test crossing a true 8-point gap by release 3.
- **Nightly small exam, futility-only.** Correct description of a one-sided futility rule: it can only raise type-II error, never type-I.
- **G5's entailment bound.** `true unentailed rate ≤ flagged rate / judge sensitivity` is a valid conservative upper bound, since ignoring judges' false positives only inflates the numerator in the safe direction. No error found anywhere in §4.


## 5. Consistency of counts across documents

Cross-checked "fourteen roles / fifteen identities / eleven groups" and "two Foundry projects per account" across `README.md`, `01`, `02-technology-landscape.md`, `03-logical-architecture.md`, `04`, `05`, `07`, `13-decisions.md`. **All agree.** `04` §7 states the two-project split as "reasoning (the other thirteen identities) and examination (the Examiner and the Forger)": 13 + 2 = 15, consistent with the roster. No disagreement found on these counts in the documents this lens reads.

## 6. Drift coverage — the nine named types (`09` §2)

| Type | Prevent | Detect | Correct | Verdict |
|---|---|---|---|---|
| Infrastructure | Deployment Stacks + deny settings, Policy Deny/Modify | scheduled `what-if`, Activity Log alert, D17, Policy compliance | redeploy from `main`, Policy `Modify`, lock procedure | Exists (DR-1) |
| Identity | no standing write; constrained ABAC delegation | Resource Graph diff, the sweeper, sign-in alerts | sweeper removes; disable sponsor-less identity | Exists (DR-2) |
| Model | pinned deployments; model subset; approved-model Policy | daily stratified probes + rotating hidden subset + change-point statistic | fallback to pinned alt, fail closed, full exam, re-pin = release | Exists; best-specified of the nine (DR-8) |
| Prompt | repository-only source; baked-in `prompt_hash` | sampled-trace hash check; **nightly tool-behaviour probe** vs. fixtures | redeploy; block the contract | Exists (DR-6) |
| Knowledge | scope + receipts + expiry + recheck recipe; `depends_on` edges at creation | scheduled re-checks; change radar; node-change detection | invalidate every consumer first (DR-11), demote, re-study | Exists; strongest mechanism, points at an unspecified Detector (D-15) |
| Behaviour | gates G3–G5; shadow mode | continuous evaluation; calibration error; population-stability test | pause agent/contract; roll back | Exists (DR-12); no power/false-alarm sizing, unlike the gates |
| Cost | token limits; envelope budgets; atomic reservation | 3× trailing-median alarm; cost-per-case trend | throttle; cheaper alias; Conductor case | Exists (DR-14) |
| Network | Policy *Deny* on public access; network security perimeters | daily canary agent; firewall deny logs | `Modify` back to disabled; redeploy | Exists (DR-3) |
| Policy | initiative as code; tested control map | Policy compliance (**up to 24 h stale**) + G8's synchronous assertion at release | `DeployIfNotExists`; a human task | Exists, with a disclosed ≤24 h gap between releases (D-19) |

## 7. Decision table — all 37 ADRs

`<repo>\docs\design\13-decisions.md`. Confidence reflects my lens; for ADRs outside AI engineering I defer the deep stress-test to lenses A/B/C/E.

| ADR | Verdict | Conf. | Strongest alternative | What would change my mind |
|---|---|---|---|---|
| 01 | Agree | High | Agent handoff/A2A | A paired ablation shows handoff safer and cheaper |
| 02 | Agree w/ changes | Med | Native APIM only | Hub cannot attribute/govern a needed route |
| 03 | Agree | Med | One subscription, RGs per env | Non-production floor swamps pilot value |
| 04 | Agree w/ changes | Med | West Europe (cheaper) | A tested West Europe stack has the full stack |
| 05 | Agree | Med | Managed VNet | It gains logging, BYO firewall, West Europe |
| 06 | Agree w/ changes | High | Coarser groups, shared identity | S-ID-2/S-GW-3 shows `azp` attribution fails |
| 07 | Agree | High | Standing roles, approval-gated | PIM gains licensed active assignment |
| 08 | Agree | High | Teams Approvals app | Target-hash binding shown end to end there |
| 09 | Agree | High | Everything on Global | EU assumption narrows, or Flex reaches GA |
| 10 | Agree | High | Same-family judge | S-MOD-1 shows correlated errors are negligible |
| 11 | Agree w/ changes | Med | Claims in a DB with vectors | Query latency outweighs review/Commons value |
| 12 | Agree w/ changes | Med | Azure SQL serverless | S-DATA-4 shows Cosmos fails recall or cost |
| 13 | Agree w/ changes | Med | Microsoft-only (Synapse) | S-DATA-1 shows no cost/simplicity win |
| 14 | Agree | High | Foundry/platform memory | Memory reaches GA with VNet + provable calls |
| 15 | Agree | Med | Native MCP import day one | Preview schema instability outweighs it |
| 16 | Agree | Med | Shared Lab subscription | Reaper/quota isolation fails under load |
| 17 | Agree | Med | Teams Approvals app for voice | A bound voice-approval path is shown to exist |
| 18 | Agree w/ changes | Med | Full-fidelity tables everywhere | Cheap-plan joins fail in practice |
| 19 | Agree w/ changes | High | Guardrails/Defender alone | Tests prove equivalent coverage without our gate |
| 20 | Agree | High | Every paid Defender plan | Trial shows value over D1–D20 at acceptable cost |
| 21 | Agree w/ changes | Med | Telemetry-based drift agent | Native coverage reaches our detectors' full scope |
| 22 | Agree | High | Foundry evaluations alone | Platform ships sealed holdouts, estate scoring |
| 23 | Agree w/ changes | Med | Terraform/AzAPI | A needed type has no Bicep/AVM support |
| 24 | Agree | High | CMK everywhere | A mandate or measured privacy gap needs it |
| 25 | Agree | High | Global for estate data | Approved change to the residency assumption |
| 26 | Agree w/ changes | Med | Azure budgets alone | Hub counters bound realistic burst spend |
| 27 | Agree | High | SRE Agent always on | Trial shows net savings over its meter |
| 28 | Agree | Med | Atlas/code in two repos | Isolation tests fail under shared-repo rule |
| 29 | Agree w/ changes | Med | Templates as sole evidence | Control-effect tests prove unneeded |
| 30 | Agree w/ changes | Low | Warm second region, day one | A restore drill misses the one-day RTO |
| 31 | Agree w/ changes | High | Floating references | Manifest can't reconcile against live sessions |
| 32 | Agree w/ changes | Med | Confidential Ledger | S-DATA-2's append/rollover spike fails |
| 33 | Agree w/ changes | High | Our checkpoint-and-jobs design | S-NET-1 can't confirm `/invocations` (D-20) |
| 34 | Agree | High | Routines as default clock | Routines confirmed GA with envelope invocation |
| 35 | Agree | Med | Require an existing hub | Minimal-hub fork costs more than it is worth |
| 36 | Agree | High | All-Python | .NET SDK reaches parity, closes the contract gap |
| 37 | Agree | High | Code in the agent's own microVM | Sandbox shows no isolation benefit at its cost |

## 8. What is strong — keep

- **The three-party authority chain and its property tests** (`07` §3.3–§4, `10` §2 L1): "an approval can never cover a target other than its own" and "a lease can never be held twice" are tested as properties; the `depends_on` graph (`09` §3) is a genuine mechanism, not a label.
- **The statistical protocol** (`10` §4): pre-registered, one-sided, clustered by estate, two baselines against chaining, an intersection–union gate, a futility-only nightly exam — every piece I recomputed was correct.
- **Exam isolation** (`10` §3): physically separate generator, keys and labels per tier; the Forger's independence is measured, not assumed.
- **The spine↔leaf boundary**: Durable Functions (deterministic, no model, GA, confirmed to support Flex Consumption today) calling hosted agents (confirmed GA, confirmed in Sweden Central) through a hub holding the only Foundry role — clean in principle, honestly flagged unproven at its one weak joint (S-NET-1, D-20).
- **W10's self-editing control** is structural, not a policy promise.

## 9. What is missing — five priorities

1. **A Detector record schema and lifecycle** (states, validity domain, blind spots, novelty trigger, expiry) — the one piece of "compiled knowledge" the design never formalises (Finding D-15).
2. **A credential-scoped invalidation**, not only the global approval epoch, so withdrawing one autonomy credential does not require choosing between leaving a race window open and halting every other in-flight approval (Finding D-16).
3. **A powered, false-alarm-budgeted continuous monitor** for the fingerprint probe and the population-stability test, matching the rigour `10` §4 already gives the release gates (D-19).
4. **A named mechanism for turning a W10 (or W7 Dream) proposal into an actual pull request**, since no agent tool can do it and the design currently leaves that human step unspecified (D-18).
5. **A cleanly split S-NET-1** with its own fallback for hosted-agent `/invocations` forwarding, independent of the portal-gateway question it is currently bundled with (D-20).

