# Design 08 — Governance and compliance

> **What this answers:** *Who is accountable for what, how do the EU AI Act, GDPR, NIS2, ISO/IEC 42001 and the NIST AI RMF map onto the design, and how does the system produce its own compliance evidence?* The regulatory facts come from the [security and compliance research](research/security-and-compliance.md), read on 2026-10-31. **This is a design mapping, not legal advice**: each regulatory position marked *to confirm* needs a lawyer before the system is put into service. Part of the [design](README.md); the controls referred to are in [07](07-security-architecture.md) and [09](09-safeguards-and-drift-controls.md).

---

## 1. The governance model

### 1.1 Roles

Every role is a *named human*, recorded in the repository (`GOVERNANCE.md`) and in Entra (as owner or sponsor), never a team alias.

| Role | Accountable for | Holds |
|---|---|---|
| **System owner** (the operator) | the system as a whole; accepting residual risk; exceptions | Owner of the production subscription; the right to pull any kill switch |
| **Sponsor**, per agent group and per execution identity | what that identity may do; its quotas; its contract | CODEOWNERS on its contract; Entra sponsor of the identity |
| **Approvers** | decisions on Moves; for a purchase, an irreversible Move that needs two approvers and a credential grant, **two people with different hats** (for a purchase, workload owner and Finance), neither the requester nor the preparer | standing **only from human-administered Entra groups or RBAC roles on the target**, checked at the approval, read live again by the broker at grant, and never inferred by an agent from tags, replies or the directory; PIM-eligible only where licensed |
| **FinOps lead** | the commercial truth: price books, commitments, the system's own unit economics | review of Atlas pricing claims; owner of [12](12-cost-and-finops.md) |
| **Security lead** | the security architecture, detections, red-team scope, incident response | owner of [07](07-security-architecture.md) |
| **Atlas reviewers** | what enters the public knowledge base | merge rights on the Atlas, never on code that executes |
| **Data protection contact** | the privacy record: inventory, DPIA, subject requests | owner of §4 |
| **Platform owner** (landing zone) | the hub, connectivity, policy baseline | owner of the dependencies in [04 §2](04-landing-zone-and-citadel.md#2-the-landing-zone-what-we-need-one-by-one) |
| **Estate owner** (of an onboarded estate) | granting and revoking our access at their scope: *read onboarding*, and the separate, consented *action onboarding* that delegates constrained role-assignment rights to the broker ([07 §3.3](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim)); administering the approver groups | the right to offboard at any time ([11 §6](11-delivery-and-operations.md#6-onboarding-and-offboarding-an-estate)) |
| **Platform operator** | running the platform: releases, runbooks, on-call | pipeline rights; **never the approver of their own release** — a required check counts two distinct approvers who are not the author ([07 §9](07-security-architecture.md#9-supply-chain)) |

**Single-operator mode.** While one person holds the system-owner, security-lead and platform-operator roles, the platform runs in single-operator mode: promotion is limited to **shadow mode and reversible Moves**, and anything else waits for a second reviewer who did not author the change. The minimum crew that lifts the limit is three people: the operator, a second reviewer or approver, and a security reviewer ([11 §7.2](11-delivery-and-operations.md#72-support-model)).

### 1.2 Who decides what

**R** responsible · **A** accountable · **C** consulted · **I** informed. *Agents are never accountable.*

| Decision | System owner | Sponsor | Security lead | FinOps lead | Approvers | Atlas reviewer |
|---|---|---|---|---|---|---|
| Change a **model alias** or resolve it to a new model | A | R | C | C | | |
| Change a **contract** (limits, tools, safety) | I | A, R | C | C | | |
| Add a **Move** to the catalogue | A | C | C | C | | |
| Grant an **autonomy credential** | A | R | C | C | R (the domain's owners) | |
| **Promote** a release | A | C | C | I | | |
| Merge an **Atlas** change | I | | | C | | A, R |
| Approve a **purchase** | | | | C | R (two hats) | |
| Confirm a **lesson** (draft to confirmed) | I | | | | A, R (the owner of its scope, by an authenticated action) | |
| Accept an **exception** to a design rule | A | R | C | C | | |
| **Pull a kill switch** | A | R | R | | | |

A lesson is *draft* until an owner confirms it by an authenticated action, and a draft is never an instruction to an acting agent. An **autonomy credential** is an item in `controls` that only a named human's grant action writes, and it carries the Approval service's signature on the record of the two named approvers, which every reader verifies ([07 §4](07-security-architecture.md#4-approvals-that-cannot-be-forged-or-reused)); no agent, pipeline or pull request can produce a valid one. The estate owner's own decisions — read onboarding, action onboarding, the approver groups, offboarding — are not in the table because they belong to the adopting organisation; the system owner is informed.

### 1.3 Policy as code

Governance that lives in a document drifts. The control set is an **Azure Policy initiative** assigned as code, mapped to the **Microsoft cloud security benchmark v2, AI security domain** (v2 is labelled preview, so the control map in the repository stays authoritative; AI-1 approved models, AI-2 multi-layer filtering, AI-3 safety meta-prompts, AI-4 least privilege for agent functions, AI-5 human in the loop, AI-6 monitoring, AI-7 continuous red teaming).

| Policy | Effect: production · non-production · Lab | State |
|---|---|---|
| Foundry and AI Services: **key access disabled**, **public network access disabled**, private endpoints, managed identity, diagnostics deployed | Deny · Deny · Audit | GA |
| **Approved models and model eligibility**; the router's subset | Deny · Deny · Audit | GA (router policy: preview) |
| Foundry agents and toolboxes: only **approved tools** | Audit · Audit · Audit | preview |
| Minimum **content-filter** level for agents and deployments | Audit · Audit · Audit | preview |
| API Management: VNet, no direct management endpoint, authenticated backends, certificate validation, secrets in Key Vault, subscriptions not scoped to all APIs | Audit · Audit · Audit (the hub's owner enforces) | GA |
| Container Apps: network injection, public access off, HTTPS only, managed identity | Deny · Deny · Audit | GA |
| AI Search and Key Vault: local auth off, public access off, purge protection, private link | Deny · Deny · Audit | GA |
| **Tags**: owner, sponsor, environment, expiry (Lab: mandatory) | Deny · Audit · Deny | GA |
| **Allowed SKUs and regions** (Lab: a short list, no public IPs) | n/a · n/a · Deny | GA |

**Compliance state is not live state.** Azure Policy compliance data can be up to 24 hours old — the standard evaluation cycle runs once every 24 hours ([Learn](https://learn.microsoft.com/azure/governance/policy/how-to/get-compliance-data#evaluation-triggers)) — and an *Audit* effect blocks nothing. So G8 adds **synchronous Azure Resource Graph and SDK assertions** against the live properties of every control that gates an action (public network access, key authentication, the contract's data class, the role assignments on every signing vault — only `acia-signer` and `acia-key-reader`, none holding `keys/update/action` — and on the chain's jobs and queues, where only the pipeline that deploys the environment (`deploy` for dev and test, `release` for production) holds `jobs/write`, the production `release` pipeline holds no `jobs/start/action`, and each party holds a role on its own queues only), and uses Policy compliance as the standing record, not as the gate.

**The control map.** `governance/controls.yaml` lists every control with its requirement, the query that proves it, the test that exercises it and its owner. **Release gate G8** ([10 §4](10-test-and-evaluation.md#4-release-gates)) fails when a control cannot show evidence *from live state* — compliance is a build output, not a quarterly scramble.

## 2. The EU AI Act

**Position (to confirm).** The operator is both **provider** (builds the system and puts it into service under his name) and **deployer** (uses it). The system is **not high-risk by purpose**: it works on cost and resources, and it is designed to *stay out of* employment and work-management uses. Where a use would enter Annex III, the design bans it rather than manages it.

### 2.1 Timeline as of 2026-10-31

Every date and effect in this section and in §2.2 is a reading of the sources on 2026-10-31 and is **to confirm with counsel** before the system is put into service.

| Date | What applies |
|---|---|
| 2 Feb 2025 | Prohibited practices (Art. 5) and AI literacy (Art. 4) |
| 2 Aug 2025 | General-purpose AI model obligations (on the model providers) |
| 27 Jul 2026 | The AI Omnibus enters into force (the regulation number is *to confirm*) |
| **2 Aug 2026** | The remainder of the Act, **including Art. 50 transparency**. The grace period for machine-readable marking (Art. 50(2)) runs to 2 Dec 2026 *only for systems already on the market*; a new system gets none |
| 2 Dec 2026 | Ban on non-consensual intimate-image and child-abuse-material generators |
| 2 Dec 2027 | Annex III high-risk obligations (postponed) |
| 2 Aug 2028 | Annex I high-risk obligations (postponed) |

### 2.2 What it means for the design

| Obligation | How the design answers it |
|---|---|
| **Art. 5 prohibitions** | **No emotion recognition** on staff in meetings or calls: the voice and avatar modules do no mood or sentiment inference. **No ranking or scoring of individuals**: cases attribute cost to resources, services and teams, never to a person's performance, and approver behaviour is watched only through **role-level and aggregate** signals ([09 DR-17](09-safeguards-and-drift-controls.md#23-drift-in-behaviour-and-in-people)) — no per-person score and no inference of a named person's working rhythm. No manipulative techniques: Briefs state the saving, the evidence and the alternatives, and never use urgency, shame or social pressure. These are red-team categories ([10](10-test-and-evaluation.md)) |
| **Art. 4 AI literacy** | a short training record for operators and approvers, kept in the evidence pack |
| **Art. 50(1) tell people it is AI** | disclosure at first interaction in *every* channel: a card footer, an e-mail banner, a voice greeting, an avatar label, the first text message |
| **Art. 50(2) mark synthetic content** | machine-readable marking in e-mail headers and card metadata; marks on audio and video where the service offers them (to confirm); the voluntary code of practice on transparency of AI-generated content is the reference |
| **Art. 50(4) deepfakes (deployer)** | a clearly synthetic avatar by default; consent and disclosure for any personal voice or custom photo avatar |
| **General-purpose model duties** | rest with the model providers; **no fine-tuning or distillation into a new general-purpose model** without a legal check |
| **Open-source** | the Act leaves free and open-source AI systems out of most obligations *unless* they fall under Art. 5, Art. 50 or high-risk; an MIT release therefore does **not** exempt the transparency duties, and the design does not depend on any exemption: whether our release counts as free and open-source in the Act's sense is *to confirm with counsel* |

### 2.3 Voluntary alignment with the high-risk requirements

Not required, but a useful quality bar, and cheap because the design already produces the evidence:

| Requirement (Arts. 9–15) | Where it is answered |
|---|---|
| Risk management | the risk register ([§8](#8-risk-register)) and the threat model ([07 §12](07-security-architecture.md#12-threats-controls-and-what-remains)) |
| Data and data governance | [06](06-data-and-knowledge.md): provenance, scope, expiry; no estate data in the Commons |
| Technical documentation | this design, the ADRs, the agent cards and the system card ([§6](#6-responsible-ai-and-the-system-card)) |
| Record-keeping | the append-only audit ledger, whose entries are signed by the services that produced them, and traces |
| Transparency to users | Briefs with *Explain*, receipts on every claim |
| **Human oversight** | approvals, two-person purchases, kill switches, credentials with expiry |
| Accuracy, robustness, cybersecurity | the exam, the attack suite, the drift controller |

## 3. Security regulation and benchmarks

**NIS2 (to confirm applicability).** Directive 2022/2555 covers medium and large entities in listed sectors, with management accountability; the Commission proposed targeted simplification in January 2026 (status to confirm) and national transposition varies. Whether the adopting organisation is in scope is its decision; the controls that would carry the obligations are here: MCSB v2 and Policy (§1.3), Defender for Resource Manager and Key Vault, central logging, PIM for administrators, an incident runbook ([11](11-delivery-and-operations.md)), supply-chain controls ([07 §9](07-security-architecture.md#9-supply-chain)).

**Microsoft cloud security benchmark v2, AI domain.** The control spine; each AI-n maps to controls and evidence:

| Control | Our answer |
|---|---|
| **AI-1** approved models | Azure Policy approved models, whose asset ids **end with `/`** because the policy matches each id as a prefix ([Learn](https://learn.microsoft.com/azure/foundry/how-to/model-deployment-policy)); asserted by the exam; alias map; the exam on every change |
| **AI-2** multi-layer filtering | model guardrails, gateway screening, deterministic gate, human approval ([07 §5](07-security-architecture.md#5-defence-against-prompt-injection-in-nine-layers)) |
| **AI-3** safety meta-prompts | versioned instructions with hashes; tested, never trusted as the boundary |
| **AI-4** least privilege for agent functions | zero standing write; read-only tool identities; per-tool app roles per agent identity ([07 §5](07-security-architecture.md#5-defence-against-prompt-injection-in-nine-layers), layer 6) |
| **AI-5** human in the loop | signed approvals that carry the person's Entra-signed token; two-person purchases |
| **AI-6** monitoring | traces, hub logs, detections D1–D20, the drift controller |
| **AI-7** continuous red teaming | attack suite in CI; scheduled red teaming; canaries |

## 4. Privacy and GDPR

### 4.1 Personal data in the system

| Data | Why it exists | Where | Minimisation |
|---|---|---|---|
| Owner and approver **names, e-mail addresses, Teams identifiers** | to ask the right person and to record who decided | Estate service (mapping); Brief service; the erasable signed approval records — **not the audit ledger** | prompts see **pseudonyms**; the mapping never leaves the tenant; **names exist only in erasable stores**, and the ledger's entry schema rejects name, e-mail, UPN, `oid` and Teams-id fields (an L1 property test, [10 §2](10-test-and-evaluation.md#2-the-layers)) |
| **Directory data**: manager, team and **contact preferences** (language, preferred hours) | to ask at a humane time, in the right language | Estate service | only the fields a Brief needs; preferences are stated, **never inferred from behaviour**, and never used to evaluate the person |
| **Approvals**: who, when, from which channel, what they saw | accountability | audit ledger (a pseudonymous id and a hash of the signed record); the signed record, which carries the person's Entra-signed ID token (two for a purchase, an irreversible Move that needs two approvers or a credential grant) and so the directory object id, tenant, `amr` and `auth_time`, in the erasable `approval-records` container (the permanent `approvals-index` holds ids, hashes, state and a pseudonymous id only) | the ledger holds pseudonymous ids and hashes only; the mapping and the full record sit in stores where an erasure can reach them |
| **Replies** to questions (free text) | lessons | Brief store; Lesson Book | untrusted text; stored as testimony with expiry; no special-category inference |
| **Traces** with prompts and tool results | debugging, evaluation | App Insights, the protected table | content capture **off** by default; short retention; restricted role |
| **Voice and meeting audio** (optional module) | conversation by voice | transient | **off by default**; consent; no storage by default |

### 4.2 Positions

| Topic | Position (to confirm with the adopting organisation's privacy function) |
|---|---|
| **Roles** | the adopting organisation is the **controller**; Microsoft is a **processor** under the Products and Services DPA; we ship MIT software and process nothing ourselves |
| **Residency** | estate and personal data: **EU Data Zone or regional** deployments only; Global deployments only for the public and synthetic data classes ([07 §6.2](07-security-architecture.md#62-data-classes-and-what-each-may-touch)); voice, speech and avatar regions are checked before the module is enabled |
| **Prompts and training** | the platform states that prompts, completions and embeddings are not used to train models |
| **Abuse monitoring** | Microsoft personnel may review prompts; managed customers may apply to modify this. **Decide, record and put it in the DPIA** |
| **Lawful basis** | to confirm per organisation (legitimate interest for cost communication is the likely basis for workplace e-mail; staff-facing voice and meeting agents need more) |
| **DPIA** | prepared before the first production use; a template ships in `governance/` |
| **Employee consultation** | works-council or labour-law consultation is *to confirm* before any staff-facing voice, avatar or meeting module is enabled — which is why those modules are off by default — and before any measure of approver behaviour finer than role-level aggregates |
| **Automated decisions (Art. 22)** | the system's decisions are about cloud resources, not natural persons; a Move runs on a named human's authenticated, signed approval or, within a human-granted *autonomy credential*, under a rule a human wrote. Where a decision touches a person, it is that person's own authenticated act. Whether Art. 22 applies at all is *to confirm with counsel*; the design does not rely on the answer |
| **Subject rights** | access and erasure are served from the **erasable stores** (the Estate service, the Brief store, the Lesson Book, the signed approval records). The audit ledger is immutable by design and holds **pseudonymous ids and hashes**, not personal data (no name, e-mail, UPN, `oid` or Teams id, which its schema rejects); erasing the mapping removes the link from a pseudonym to a person *in our stores*. Whether the remaining record is anonymous to a party that also holds the tenant's Activity Log or Entra logs, and on what basis the pseudonymous approval record is retained (the organisation's audit obligation is the likely one), are *to confirm with counsel*; backups re-apply erasures ([§4.3](#43-retention)) |
| **Breach** | the 72-hour notification clock starts at detection; the runbook ([11](11-delivery-and-operations.md)) names who decides |

### 4.3 Retention

| Data | Default retention | Where set |
|---|---|---|
| Traces (spans, metrics) | 30 days hot; longer only on cheap plans | table plans |
| Prompt and tool content (if enabled) | 7 days, protected table | Application Insights |
| Brief and conversation records | 90 days | Brief store |
| Lessons | expire by design (default 12 months, renewable) | Lesson Book |
| Audit ledger | per the organisation's audit obligation (default 7 years) | immutable storage policy |
| Stored model responses | `store=false` where retention matters; the platform default is 30 days | agent configuration |
| Evaluation samples | redacted before storage; 30 days | evaluation store |
| Signed approval records (with the approver's Entra claims) | 90 days after the approval expires, and at once on an erasure by identity — a design default, *to confirm with counsel* | `approval-records` container |
| Export objects and snapshots of the operational store | 35 days, then deleted; ledger copies keep the ledger's retention — a design default, *to confirm with counsel* | recovery lake |
| Tombstones of erased items | the id and the erase time only, kept longer than the export retention so that no surviving snapshot outlives its tombstone; a restore **re-applies every erasure** before the stores serve traffic ([06 §7.6](06-data-and-knowledge.md#76-recovery)) | export lake |

## 5. ISO/IEC 42001 and the NIST AI RMF

**ISO/IEC 42001.** Microsoft Foundry is in scope of Microsoft's certificate (per feature scope to confirm on the Service Trust Portal), which helps but certifies **nothing of ours**. An organisation that wants its own certification needs its own assessor; the design is built so that the management-system evidence already exists.

| Clause theme | Evidence in this system |
|---|---|
| Context and scope | [01](01-requirements-and-principles.md), the north star |
| Leadership and roles | [§1](#1-the-governance-model); `GOVERNANCE.md` |
| Planning: risk and impact assessment | risk register; threat model; DPIA; the AI system impact assessment (system card) |
| Support: competence, awareness | AI literacy record |
| Operation: lifecycle, data, third parties | [05](05-agents-and-orchestration.md), [06](06-data-and-knowledge.md), supply chain |
| Performance evaluation | the exam, continuous evaluation, drift metrics, internal audit by the Auditor |
| Improvement | lessons, ADR reviews, incident learnings |

**NIST AI RMF.**

| Function | Mapping |
|---|---|
| **Govern** | roles, decision rights, policy as code, exceptions, the evidence pack |
| **Map** | system card and agent cards; intended use and limits; capability matrix; threat model; data classes |
| **Measure** | exams with baselines, calibration, decoys, red teaming, cost and latency per case |
| **Manage** | gates, kill switches, drift controller, incident response, autonomy credentials with expiry |

## 6. Responsible AI and the system card

The design follows Microsoft's Responsible AI principles. The Transparency Note for Agent Service urges human oversight and caution for irreversible or highly consequential actions: Moves and purchases are exactly that, so they carry approvals, and purchases carry two named approvers.

| Principle | How |
|---|---|
| Fairness | cases never attribute cost to a person's performance; attributions are to resources, services and teams |
| Reliability and safety | the exam, restraint on decoys (zero tolerance for a harmful recommendation), shadow mode, rollback |
| Privacy and security | [07](07-security-architecture.md); pseudonyms; EU residency |
| Inclusiveness | Briefs in the owner's language; plain text equivalents of cards; no dependence on voice |
| Transparency | receipts, *Explain*, disclosure of AI in every channel, the system card |
| Accountability | named sponsors and approvers; the audit ledger |

**The system card** and an **agent card per agent** are generated from the repository (instructions, tools, contract, aliases, evaluation results, known failure modes) at every release, so documentation cannot drift from the system (DR-18).

## 7. The evidence pack

Evidence is produced **automatically** by the pipeline and the drift controller and stored with the release manifest; a person only reviews.

| Artefact | Produced by | Cadence |
|---|---|---|
| Control-map results (every control, its query, its result) | CI, gate G8 | every release |
| Policy compliance export | scheduled job | daily |
| SBOM, licence report, signed images | CI, gate G1 | every build |
| Exam, red-team and resilience reports | the Examiner, the schedules | nightly, weekly, per release |
| Release manifest (every pin) | pipeline | every release |
| Approval statistics at role level and in aggregate, cross-checks against sign-in logs (D13), anomalies | the Auditor | weekly |
| Key rotations (the RB-12 workflow), lease and probe records, intent reconciliations, poison-queue alerts, sweeper findings, the ledger verifier's nightly result | the Approval service, the broker, the Verifier, the sweeper, the ledger verifier | per rotation; nightly; monthly |
| Drift findings and their time to correct | drift controller | continuous |
| DPIA, record of processing, DPA acceptance | data protection contact | on change |
| AI literacy record | system owner | annual |
| ADR index and exceptions register | repository | on change |
| Incident log and post-incident reviews | security lead | on event |

## 8. Risk register

Qualitative; each risk has a named owner and appears with its ADR.

| # | Risk | L | I | Controls | Residual | ADR |
|---|---|---|---|---|---|---|
| R1 | A prompt-injected agent causes a wrong *proposal* | H | M | no write power; Skeptic; approval gate; layers 0–9 | low | 19 |
| R2 | A compromised execution component changes an estate | L | H | a just-in-time execution identity; *no single credential completes a change that needs a person's web-page approval.* A compromised Approval service cannot start a job, fabricate a permit or fabricate a person's Entra-signed token. On the card path (reversible Moves of the lowest class only) the proof is the bot channel's assertion, which a compromised Approval service can fabricate; that is why the path ends at that class. A compromised Approval and Policy service can approve within an autonomy credential's constraints, which the broker and the runner check against the credential itself. A compromised broker can grant constrained Move roles without a lease; a compromised release pipeline can run code as a runner identity while it holds a role. Each is bounded and detected as stated in [07 §3.3](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim); in addition the sweeper, kill switches with stated latencies, Defender for Resource Manager, D14–D16 | low–medium | 07, 08 |
| R3 | A **preview** dependency changes or disappears | H | M | the preview register; switches; fallbacks | low | 21 |
| R4 | The **Citadel hub** is a single-maintainer sample | M | H | fork and pin; contract tests; native APIM fallback; contracts as data | medium | 02 |
| R5 | **Token cost overrun** | M | M | caps at the hub; envelopes; cost-per-case gate; Flex and Batch for public work | low | 26 |
| R6 | A **model is retired or changes silently** | H | M | aliases; pins; fingerprint probe; 180-day alerts | low | 09, 10 |
| R7 | **Regulation moves** (AI Act, NIS2) | M | M | the dependency register includes regulation; quarterly review; legal confirmation items | medium | 29 |
| R8 | **Approver fatigue** or a coerced approver | M | H | two hats; multifactor authentication strength on the approval app (Entra ID P1; without it those classes stay off); DR-17 at role level and in aggregate, with no individual scoring; kill switches | medium | 08 |
| R9 | **Personal data** reaches a Global deployment or a log | L | H | data classes at the hub; pseudonymisation in the tool services before the hub; contract tests; protected tables; DPIA | low | 25 |
| R10 | **Licence-dependent controls** are unavailable | H | L | optional modules with fallbacks; where the fallback is to fail closed (Entra ID P1 for the approval page's multifactor enforcement) the irreversible Moves, purchases and credential grants stay off | low | 20 |
| R11 | **Platform region constraints** (one region carries all features) | M | M | redeploy-from-code recovery; second-region path documented | medium | 04, 30 |
| R12 | **Lock-in** to Foundry, APIM and hosted agents | M | M | contracts as data; Agent Framework is open; aliases; MCP and A2A are open protocols | accepted, costed in [13](13-decisions.md) | 01, 02 |
| R13 | A **forged or replayed approval**, misuse of a signing key, or two colluding compromised services (credential-based approvals only) | L | H | a Policy permit and a person's Entra-signed token that the Approval service cannot fabricate, bound to the target, the decision and a per-request challenge; two verified proofs where two approvers are needed; the approval's own ledger entry, which the broker verifies; producer-signed markers and leases; the broker and the runner verify again; single-use nonce, expiry and live-state hash; approval epoch, key and credential deny lists; signing-only key roles; the credential's own signed grant record, never the caps in the permit; the approval page is the person's display, so it shows the target's short code, the Brief in the second channel shows the same code and D13 cross-checks every approval against the sign-in logs; *no single credential completes a change that needs a person's web-page approval*, and a compromised Approval and Policy service can approve only within an autonomy credential's constraints ([07 §3.3](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim)); D13, D15, D16, D18, D20 | low–medium | 07, 08 |
| R14 | **Lease collision** or slow revocation of an execution identity | M | M | exclusive leases signed by the broker, with fence tokens; the activation probe and a two-part revocation probe (the assignment list is empty and a call as the identity fails); quarantine; the ten-minute RBAC propagation delay inside every window; a redelivered message is reconciled and never repeated (delivery is at least once, and exactly-once is not claimed); D14 | low–medium | 07 |
| R15 | A **poisoned approver registry** (standing inferred from a tag or a reply) | M | H | standing only from human-administered groups or roles; D10 | low | 08 |
| R16 | **CI poisoning** through agent-authored pull requests | M | H | data paths only, through a GitHub App installation; two approvers who are not the author on `moves/**` and no executable field in a Move; GitHub-hosted runners without secrets or federation; privileged workflows from the base branch after a human approves, and `pr-spoke` only after the merge (spike S-DEL-2); a compromised release pipeline, the only holder of `Microsoft.App/jobs/write` (the production `release` pipeline holds no `jobs/start/action`), can run code as a runner identity while it holds a role, which the lease, signed-image admission and the two-approver release rule bound and D16 detects, and a deployment lock keeps an honest deployment from overlapping a lease ([07 §3.3](07-security-architecture.md#33-the-execution-identity-just-in-time-without-pim)) | low–medium | 23, 28 |
| R17 | The **audit ledger** is unavailable or inconsistent | L | M | one Audit Writer; fail closed, so no change without a ledger entry: every effect is preceded by a signed intent entry that the actor reads back and followed by an outcome entry (the rollback to the signed pre-state, which includes removing a granted role, is the one exemption, from a signed outbox); producers read their block back, and the broker reads the approval's own block before it grants; a nightly verifier that is not the writer; rollover and signed digests; D19 | low–medium | 32 |
| R18 | **One person holds every role** (single-operator mode) | H | M | promotion limited to shadow mode and reversible Moves; a second reviewer before anything else; a minimum crew of three | medium | 23 |

## 9. Open-source governance

**MIT.** Contributions use a developer certificate of origin sign-off; `SECURITY.md` names private vulnerability reporting; `CODE_OF_CONDUCT.md` and `GOVERNANCE.md` name maintainers. The **Commons** accepts only claims and recipes, and counts only above a minimum cohort — **none at all in single-tenant mode**, where a cohort of one would re-identify the organisation; a scanner rejects anything resembling estate data before review. Third-party licences are checked in CI (gate G1). The project does not use Microsoft marks as its own and states plainly that it is *not* a Microsoft product.

## 10. Exceptions

A design rule may be broken only by an **exception record**: a short ADR with the rule, the reason, the compensating control, an **owner** and an **expiry date**. The register is part of the evidence pack and the Auditor reviews it quarterly. Standing exceptions:

- **The embedded analytics engine** (DuckDB) is an open-source library rather than a Microsoft service, accepted against constraint C1 in [ADR-13](13-decisions.md#adr-13-cost-analytics-is-parquet-and-an-embedded-engine-in-a-job). It is **not** the only option: Synapse serverless SQL reserves no compute while idle and charges for the data processed ([Learn](https://learn.microsoft.com/azure/synapse-analytics/sql/on-demand-workspace-overview)). The exception therefore rests on **measured simplicity and cost, compared against that Microsoft-only option in spike S-DATA-1**, and keeps a Microsoft-only fallback behind the same interface. **Owner:** the sponsor of the Cost query service, a named human in `GOVERNANCE.md`. **Expires 2027-04-30** (an assumption: six months from this design), or when S-DATA-1 reports, whichever comes first; renewal needs the measured comparison.
- **The public-ingress exceptions X1–X5** are declared with their compensating controls in [07 §7](07-security-architecture.md#7-network-and-the-short-list-of-exceptions), including the Entra-authenticated approval web page (X5), which is the default approval path. They follow the same rule: **owner:** the security lead; each is re-affirmed at the quarterly review and lapses if it is not.

## 11. Review cadence

Quarterly governance review (risks, exceptions, evidence gaps, regulation); each ADR carries a **review trigger** (a date or an event such as "the AI Gateway product reaches general availability") and every exception carries its expiry date; the dependency register and the release feed raise triggers automatically; and any change to a regulatory position marked *to confirm* is a change to this document, not a footnote.
