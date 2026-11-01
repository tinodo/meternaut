# Round 2 — lens B (security, safety and compliance)

Reviewed at commit `7baddcf` · model `grok-4.7` · 2026-11-01. Read-only except this file. Assumption: phase 1 is A3, one deployment per tenant, so single-tenant mode is the operating case, not a later option. Compromised means that component's code or identity is attacker-controlled — the threat the three-party sentence is written to answer.

## 1. Verdict in five lines

The read-only reasoning plane, the split of `govern`, the signed approval, and the honest ABAC limit are sound, and Round 1's B-01–B-15 and B-17 fixes are in the files the disposition names.
The three-party sentence is false: the Approval service holds both the only signature the broker trusts and `jobs/start`, and Learn says that start replaces the job template, so one compromise dispatches attacker code as the execution identity.
Detection (D13, D16, D18) does not stop that, and D13's unlicensed fallback is the attacker's own record.
Two claimed Round-1 fixes are contradicted elsewhere: Commons counts (B-16) and names in the immutable ledger.
**The one thing that must change:** take job start away from the signer, and make the broker require a permit the signer cannot forge.

## 2. Disposition audit (B-01–B-17)

Landed, not re-raised: B-01's delegation text, B-02's EU-only `govern`, B-03's `azp` wording, B-04's runner split, B-05's sanitiser, B-06's signatures and etags, B-07's standing and `amr` fallback, B-08's leases and `snet-exec`, B-09's writer and rollover, B-10, B-11, B-12, B-13, B-14's *to confirm* rows and `piiStateSavingEnabled=false`, B-15, B-17. Failed below: B-16 contradicted by `03` §3; the pseudonymous ledger contradicted by `08` §4.1. Roster counts agree (fourteen roles, fifteen identities, eleven groups, twelve contracts, two projects).

## 3. Findings

### B-01 · Critical · The three-party claim is false for a compromised Approval service

- **File and heading:** `<repo>\docs\design\09-safeguards-and-drift-controls.md` (`## 4. The safeguards between a mistake and an irreversible action`, `#### The authority chain`); `<repo>\docs\design\03-logical-architecture.md` (`## 3. Trust boundaries`); `<repo>\docs\design\07-security-architecture.md` (`### 3.3 The execution identity: just-in-time, without PIM`, `### 10.2 Detections we ship as code`)
- **Quote (verbatim):**
  - `"The core is an **authority chain of three parties, each of which verifies independently and none of which can complete a change alone**"`
  - `"**A model never sits inside the decision to execute, and no single component completes a change.**"`
  - `"it is small, holds no model and cannot grant or act."`
  - `"a **runner job started outside the Approval service**, or running an image other than the pinned digest (*to confirm* that job executions expose the image or template)"`
- **Why it matters:** The broker and the honest runner verify a signature only the Approval service can make, so a compromised signer passes both checks for anything policy will sign and the honest runner executes it. Learn, fetched 2026-11-01, [Jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs) (page dated 2026-09-16): "When you override a configuration, the job's entire template configuration is replaced with the new configuration." Start belongs to the signer, so the no-template rule dies with that compromise. D16 misses a start by the Approval service; the image check is to confirm and after the fact. The broker row lists `the **Policy service's own signature**` and not a permit verdict or hash equality. D18 misses a signer who also writes the ledger line. D13 needs Entra P1/P2; without it the fallback is "the signed record's own token claims". The nonce marker is unique only inside partition `/approvalId` (`06` §7.2: "an id is unique within its partition key"). Epoch and deny lists are read by code the attacker replaced, and `controls` is cached.
- **Fix:** A principal that is not the Approval service is the only one with `Microsoft.App/jobs/start/action`; it accepts an approval id and refuses any template body. The broker refuses unless the Policy service's signed verdict is permit and binds the same target hash. Human approvals also carry an Entra-signed token the Approval service cannot mint. State the credential path as residual: a compromised signer can still cause a policy-permitted Move to run through an honest runner. Drop the sentence that no single component completes a change, and the claim that the Approval service cannot act, until that split exists. Partition the nonce marker by the nonce.

### B-02 · Critical · B-16's Commons rule is contradicted by the logical architecture

- **File and heading:** `<repo>\docs\design\03-logical-architecture.md` (`## 3. Trust boundaries`); contrast `<repo>\docs\design\01-requirements-and-principles.md` (`## 4. Quality targets`) and `<repo>\docs\design\07-security-architecture.md` (`## 2. Trust zones, physically`)
- **Quote (verbatim):**
  - `"| **Z5 — the Commons** | open claims, recipes, Moves, counts | public | only generalised, reviewed, estate-free content; counts above a minimum cohort |"`
  - `"the Commons receives only claims and recipes, and counts only above a minimum cohort — none in single-tenant mode, where a cohort of one re-identifies."`
  - `"**no counts in single-tenant mode**, where a cohort of one would re-identify the organisation"`
- **Why it matters:** The disposition says B-16 was accepted: no counts in single-tenant mode. That sentence is in `06` §5 and `07` §2, and in Q-PRV-1. `03` §3, the crossing rule, omits it. A3 is one deployment per organisation, so phase 1 has no cohort above one. Following `03` publishes estate-shaped counts. A change present but contradicted is Critical under the brief.
- **Fix:** Replace the `03` Z5 crossing rule with the Q-PRV-1 sentence, including the single-tenant ban. Add a contract test that the Commons export contains no count field when the deployment is single-tenant.

### B-03 · Critical · Names are placed in the immutable ledger

- **File and heading:** `<repo>\docs\design\08-governance-and-compliance.md` (`### 4.1 Personal data in the system` and `### 4.2 Positions`)
- **Quote (verbatim):**
  - `"| Owner and approver **names, e-mail addresses, Teams identifiers** | to ask the right person and to record who decided | Estate service (mapping); Brief service; audit ledger |"`
  - `"The audit ledger is immutable by design and holds **pseudonymous ids and hashes**, not personal data"`
- **Why it matters:** §4.2, `06` §2 and `07` §4 say the WORM ledger never holds claims or names, so erasure deletes the mapping and leaves the chain. §4.1 lists the audit ledger as a store of names, e-mail addresses and Teams identifiers. Locked retention cannot delete those lines. That contradicts the erasure design the disposition adopted (B-14 adjusted, A-12 accepted) and makes the 7-year ledger a permanent personal-data store. `approval-records` being erasable does not help if the names were also appended.
- **Fix:** Delete the audit ledger from that Where cell. State that names exist only in erasable stores. Add an L1 property: a ledger entry schema rejects name, e-mail, `oid` and Teams id.

### B-04 · Major · The injection layers overclaim what they screen, and taint is not a boundary

- **File and heading:** `<repo>\docs\design\09-safeguards-and-drift-controls.md` (`## 4. The safeguards between a mistake and an irreversible action`); `<repo>\docs\design\07-security-architecture.md` (`## 5. Defence against prompt injection in nine layers`); `<repo>\docs\design\13-decisions.md` (`### ADR-06 An Entra agent identity per agent and eleven contract groups`)
- **Quote (verbatim):**
  - `"| **content that harms** | model guardrails and gateway screening (10,000-character windows) at every untrusted-text route; typed channel for the Diplomat |"`
  - `"responses in a configurable window (1,000 by default)"`
  - `"**session-level taint**: once untrusted text has entered a session, privileged tools require human confirmation or are blocked for it"`
  - `"until then a header carries attribution only and authorisation falls back to the group"`
- **Why it matters:** Learn, fetched 2026-11-01, [llm-content-safety](https://learn.microsoft.com/en-us/azure/api-management/llm-content-safety-policy): "prompts window size is always 10,000"; response default "1,000 characters for responses"; "If you don't specify a value, windows don't overlap." `09` calls the windows 10,000. Foundry guardrails, same day, [service limits](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/region-availability#service-limits): "The first 1000 characters for text scenarios will be moderated using Guardrails." The sanitiser chunks at 10,000 with no overlap. Session taint and the tool gate sit in the agent process (layer 5). The hub does not see taint, so a fooled model calls any tool its identity holds. ADR-06's group fallback undoes the B-03 fix until the spikes pass; S-GW-3's fallback (the tool service checks the forwarded token) is the only acceptable one.
- **Fix:** Set and test a non-zero overlap; stop saying 10,000 for responses. Enforce taint in the tool service or the hub, not in the agent. Fail closed — no group-wide tool use — until S-ID-2 and S-GW-3 pass.

### B-05 · Major · An injected agent reaches a federated workflow after one merge; `pr-spoke` contradicts the base-branch rule

- **File and heading:** `<repo>\docs\design\11-delivery-and-operations.md` (`## 3. Pipelines`); `<repo>\docs\design\07-security-architecture.md` (`### 3.1 Who has an identity`)
- **Quote (verbatim):**
  - `"They **never check out or run code from an unmerged pull request**"`
  - `"| **pr-spoke** | a pull request by a person, **after a maintainer approves the run** | self-hosted in the spoke, federated; never for agent identities |"`
  - `"| **deploy** | merge to main | self-hosted, federated, as on `main` | deploy dev; L3–L5; promote to test when green |"`
  - `"reads the Move catalogue and the rules and credentials it evaluates"`
- **Why it matters:** The two-approver check is on `release`, not on merge. An injected Engineer may open a pull request to `moves/**` YAML. One CODEOWNERS merge puts it on `main`, and `deploy` runs it in the spoke with federation (L3–L5, including Move dry runs). Nothing forbids a command, image or template field in that YAML. The Policy service reads that catalogue, so the same merge widens what policy permits in B-01. `pr-spoke` is federated and self-hosted on a pull request; it cannot test the head without the checkout rule 3 forbids, and one maintainer approves the run. GitHub, fetched 2026-11-01, [secure use](https://docs.github.com/en/actions/reference/security/secure-use): "Any user with write access to your repository has read access to all secrets configured in your repository." The agent credential is not specified as path-limited. Autonomy credentials have no named store or writer ACL.
- **Fix:** Treat `moves/**` and recipe paths like code: two distinct approvers before merge, and a schema with no executable fields. Run `pr-spoke` only after merge, inside `deploy`, which is already the spike fallback. Scope the agent credential to those paths. Name the credential store and its writers; agents are not among them.

### B-06 · Major · The fail-closed ledger rule trusts the writer to tell the truth

- **File and heading:** `<repo>\docs\design\06-data-and-knowledge.md` (`### 7.3 The audit ledger`); `<repo>\docs\design\07-security-architecture.md` (`### 10.2 Detections we ship as code`)
- **Quote (verbatim):**
  - `"acknowledges each only after its block is appended"`
  - `"the Audit Writer's chain verification"`
- **Why it matters:** Fail-closed is the producer's belief in the writer's acknowledgement, not a read-back of the blob. A compromised Audit Writer can acknowledge a grant or an execution that was never appended, and can sign the daily digest of a chain that omits entries. D19 is that same writer's verification. The writer cannot grant or start, so it cannot complete a change alone, but it can hide one and can unblock a producer that treats the ack as the entry. The second-account anchor does not help if the same key signs it.
- **Fix:** The broker and the runner read the appended block back, by sequence and payload hash, before they grant or act. A nightly verifier that is not the Audit Writer recomputes the chain and the digest. D19's signal is that job, not the writer.

### B-07 · Major · Legal effect is asserted where the design promised *to confirm*

- **File and heading:** `<repo>\docs\design\08-governance-and-compliance.md` (`### 2.1 Timeline as of 2026-10-31`, `### 2.2 What it means for the design`)
- **Quote (verbatim):**
  - `"the Act leaves free and open-source AI systems out of most obligations *unless* they fall under Art. 5, Art. 50 or high-risk; an MIT release therefore does **not** exempt the transparency duties"`
- **Why it matters:** §2's opening marks the provider/deployer classification *to confirm*. §2.1 then states dates as what applies, and the open-source row states what the Act leaves out, with no *to confirm* on that sentence. I did not re-verify the Act in this review: **UNVERIFIED**. §4.2's table header does mark its rows *to confirm*; that part of B-14 landed. DR-17's role-level limit landed and is consistent with `08` §2.2 and `06` §5. The 7-year ledger figure is a design default, not cited as a statute; leave it that way.
- **Fix:** Mark §2.1 and the open-source sentence *to confirm with counsel*, or cite the article and the consolidation actually read. Do not let an MIT release depend on an unmarked exemption.

### B-08 · Minor · `auth_time` is stored where the design says it does not exist

- **File and heading:** `<repo>\docs\design\06-data-and-knowledge.md` (`## 2. The information model`); `<repo>\docs\design\07-security-architecture.md` (`### 3.4 Conditional Access and the licence line`)
- **Quote (verbatim):**
  - `"the Entra identity claims (`oid`, `tid`, `amr`, `auth_time`) — **personal data**"`
  - `"`max_age` and `auth_time` are not documented for the Microsoft identity platform, so nothing depends on them (*to confirm*)."`
- **Why it matters:** B-07's fallback was rewritten so nothing depends on `auth_time`. `06` still stores it. An implementer will invent the claim or fail the schema. Same class of drift: `07` §13's S-ID-3 line omits key distribution, which `14` §3 includes; `controls` is read with a short cache while the kill-switch table says seconds.
- **Fix:** Drop `auth_time` from the record. Point `07` §13 at the `14` spike text. Bound the `controls` cache below the kill-switch time, or stop saying seconds.

## 4. Decision table

| ADR | Verdict | Confidence | Strongest alternative | What would change my mind |
|---|---|---|---|---|
| 01 | Agree | High | A2A handoff (free text would travel). | Hub A2A with no free-text fields, injection suite green. |
| 02 | Agree with changes | High | Standalone AI Gateway (preview, wrong contracts). Do not ship the group fallback (B-04). | S-GW-3 green. |
| 03 | Agree | High | One subscription (quota and blast radius). Delegation is now disclosed. | A zone that forbids cross-subscription role assignment. |
| 04 | Agree | Medium | West Europe. Residency is the pool, not the spoke. | A residency control Sweden Central cannot meet. |
| 05 | Agree | High | Managed VNet (unlogged firewall, fixed at deploy). | Outbound logs and a customer firewall. |
| 06 | Agree with changes | High | Three coarse groups. Group fallback reopens B-03 (B-04). Fail closed until the spikes. | S-ID-2 and S-GW-3 green; fallback deleted. |
| 07 | **Disagree** | High | A start proxy that is not the signer, plus a broker check of a permit the signer cannot forge (B-01). PIM for managed identities stays unavailable. | Start cannot carry a template, and the broker rejects a signature the Approval service alone can make, shown in a Lab. |
| 08 | Agree with changes | High | Teams Approvals app (no target hash). Broker must see more than the signer's signature (B-01). Drop `auth_time` (B-08). | A platform approval that binds etag, hat and a human token. |
| 09 | Agree | High | All-Global (breaks C9). Data-class pools are right; the `govern` leak is closed. | EU Data Zone for Flex and Claude. |
| 10 | Agree | High | Same-family judge (correlated blind spots). Claude stays off estate contracts. | Claude on an EU Data Zone under the Microsoft DPA. |
| 11 | Agree | High | Database-only Atlas (no review). Git is the control. | Signed review without a pull request. |
| 12 | Agree with changes | Medium | Azure SQL serverless ledger tables. Cosmos is fine if the nonce is not partitioned by `approvalId` (B-01). | A marker that cannot be replayed across approval ids. |
| 13 | Agree | Medium | Synapse serverless, if the library is pinned and scanned. Exception is recorded. | A Microsoft engine at the same idle cost. |
| 14 | Agree | High | Foundry Memory (preview, no VNet, poisoning). | Memory GA, BYO network, gateway-only writes. |
| 15 | Agree with changes | High | Foundry toolboxes, unproven through the hub. Set response overlap (B-04). | S-GW-4 catches a boundary plant. |
| 16 | Agree with changes | High | One shared Lab subscription (blast radius). Signed recipes are right; one-reviewer merge is not (B-05). Price-engine cap is not a platform spend limit. | A hard spend cap, or a recipe schema with no executable fields and two approvers. |
| 17 | Agree | High | Foundry Teams publishing (public route, no bound approval). X5 is declared. | Private Activity ingress with signed callbacks. |
| 18 | Agree | High | Managed Grafana (standing cost). Content capture off is the control. | A GA table that is the only place content can land. |
| 19 | Agree with changes | Medium | Guardrails alone. Layers 0, 6 and 8 carry the weight; 2 and 4 do not (B-04). | Hub-enforced taint and a measured window past character 1,000. |
| 20 | Agree | High | Agent 365 and Defender for AI by default (licence and token meter). D13's weaker fallback is not a control (B-01). | Those detections in the base subscription. |
| 21 | Agree | High | An agent detector (probabilistic). DR-17 is the right shape. | Native drift enforcement for hosted-agent versions. |
| 22 | Agree | High | Foundry evaluations alone (no held-out exam). Isolation is not a security defect. | A platform exam with sealed keys. |
| 23 | Agree with changes | High | Terraform or Azure DevOps. Bicep is fine; the CI rule is not, until B-05. | `pr-spoke` off pull requests; two approvers on `moves/**` before `deploy`. |
| 24 | Agree with changes | High | CMK everywhere (hosted-agent home directory, cost). Signing-key pin distribution is still spike S-ID-3. | Pins the signer cannot write, tested. |
| 25 | Agree | High | All-regional (cost, fewer models). The `govern` leak is closed. | Estate data processed outside the EU on a deployment labelled EU. |
| 26 | Agree | High | Budgets as the cap (8–24 h lag). The stated overrun is honest. | A synchronous euro cap per identity. |
| 27 | Agree | High | SRE Agent always on (standing meter, path around the hub). | SRE Agent at zero idle, behind the hub. |
| 28 | Agree with changes | Medium | Two repositories. The single-repo rejection holds only if B-05's path rule is real. | An agent token that cannot write `.github/` or `infra/`. |
| 29 | Agree with changes | High | Compliance Manager on day one. G8 landed. Fix B-03 before calling the ledger evidence. | An auditor who accepts Policy compliance state as the gate. |
| 30 | Agree | High | A warm second region. Export copy, tombstones and epoch are specified. | An RTO the export lake cannot meet. |
| 31 | Agree | High | Floating references. Signed pins are mandatory. | Nothing. |
| 32 | Agree with changes | Medium | Confidential Ledger. Keep blobs only with producer read-back and a second verifier (B-06). | S-DATA-2 plus that verifier in the design. |
| 33 | Agree | High | A spine inside a hosted agent (one identity). Durable Functions is right if effects stay idempotent. | A replay that re-runs an effect the ledger already has. |
| 34 | Agree | High | Routines as the clock (preview, no envelope). | Routines GA with a budget and a signed input. |
| 35 | Agree | High | Requiring a pre-built hub. The minimal hub must still be the only model path. | A deployment that calls Foundry without a hub and passes G2. |
| 36 | Agree | High | All-Python. The small C# approval surface is the security reason. | A measured reason the C# surface is the larger one. |
| 37 | Agree | High | Code in the hosted agent's microVM (shared token endpoint). Session scope landed. EU regions still to confirm. | A sandbox that can inherit an identity, or no EU region. |

## 5. What is strong

Keep read-only agent identities, `snet-exec`, and the honest line that ABAC cannot scope the target. Keep signed approvals, human-administered standing, the `amr` fallback, X5, draft lessons, DR-17, G8 as a live assertion, and the rule that the Experimenter plans and only a signed recipe deploys. The residual paragraphs in `07` §3.3 are closer to the truth than the headlines. Round-1 B-02, B-07 through B-13, B-15 and B-17 landed.

## 6. What is missing

1. A start principal that cannot sign, and a broker check of a permit the signer cannot forge (B-01).
2. An independent ledger verifier and a producer read-back (B-06).
3. A named store and writer ACL for autonomy credentials and for `controls`, so an agent pull request cannot widen policy or lower the epoch.
4. A configuration-hash definition for targets that have no ARM etag — billing scopes and reservations — which are the purchases.
5. Hub-enforced taint, a required response-window overlap, and a production ban on group-wide tool authorisation (B-04).
