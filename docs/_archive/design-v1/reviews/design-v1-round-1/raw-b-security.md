# Round 1 - lens B (security, safety and compliance) - raw report

> Reviewed at commit `20390d4` · model `gemini-4-argon` · saved as returned by the reviewer (this header added). Orchestrator spot-checks and the disposition of every finding: [disposition.md](disposition.md).

## 1. Verdict in five lines

Separating a read-only reasoning plane from a deterministic, model-free execution plane (`Z3`) is a sound security foundation.
However, five critical defects break security and residency guarantees: the onboarding module grants only read roles while the Credential Broker needs standing `Role Based Access Control Administrator` in estates (where Azure ABAC cannot constrain target resource scope); the `govern` access contract exposes estate-confidential data to `judge-pub` (Global Claude) and `batch` (Global Flex); shared group contracts and the spoofable `x-sub-agent-id` header break intra-group least privilege; agent-authored PRs trigger self-hosted OIDC runners inside the spoke VNet; and MCP streaming bypasses gateway content-safety screening on tool responses.
**The one thing that must change:** asymmetrically sign every approval in Key Vault (binding live target ARM `etag`), separate role-granting from job-starting, and enforce per-agent JWT `azp`/`oid` allow-lists at the hub with zero Global/Flex aliases on estate-data contracts.

---

## 2. Findings

### B-01 · Critical · Execution-plane RBAC contradiction and unconstrained target scope in Azure ABAC
- **File and heading:** `<repo>\docs\design\04-landing-zone-and-citadel.md` (`### 3.1 Where things live`); `<repo>\docs\design\11-delivery-and-operations.md` (`## 6. Onboarding and offboarding an estate`); `<repo>\docs\design\07-security-architecture.md` (`### 3.3 The execution identity: just-in-time, without PIM`)
- **Quote (verbatim):**
  - `"Nothing in an estate trusts our spokes for writes"`
  - `"The owner of the estate (a management group or subscriptions) deploys the **onboarding module** or accepts it by policy: **Reader, Cost Management Reader and Monitoring Reader**, nothing else"`
  - `"**The broker is the only principal that can grant**, and it holds *Role Based Access Control Administrator* with a **condition** that limits which role definitions it may assign and to which principals (the execution identities only)."`
- **Why it matters:** `04 §3.1` and `11 §6` contradict `07 §3.3`: if onboarding grants `"nothing else"`, the Broker and Sweeper cannot create or delete role assignments in estates. Once onboarding grants standing `Role Based Access Control Administrator` at management-group/subscription scope, estates *do* trust the spoke with privilege-granting rights. Moreover, Azure ABAC on `Microsoft.Authorization/roleAssignments/write` supports only three request attributes (`https://learn.microsoft.com/en-us/azure/role-based-access-control/conditions-authorization-actions-attributes`, quote: `"Role definition IDPrincipal IDPrincipal type"`). ABAC cannot restrict target resource scope below the Broker’s assignment scope or verify a live approval. Since the Broker also starts the Move runner job (`"the Move runner is a job that only the broker can start"`), a compromised Broker can assign Move roles across the entire estate subscription and invoke the runner.
- **Fix:** Update `04 §3.1`, `11 §6`, and `07 §3.3` so onboarding grants constrained `Role Based Access Control Administrator` to the Broker (write/delete) and Sweeper (delete-only) at onboarded scopes, restricted by ABAC to custom Move roles and execution principal IDs. Separate role-granting from job-starting: only the Approval/Policy service starts the Move runner job with a Key Vault-signed approval token, and the Broker grants the role only after verifying that signature.

### B-02 · Critical · `govern` access contract exposes estate-confidential data to Global Claude (`judge-pub`) and Global Flex/Batch (`batch`)
- **File and heading:** `<repo>\docs\design\04-landing-zone-and-citadel.md` (`### 4.3 The access contracts`); `<repo>\docs\design\05-agents-and-orchestration.md` (`## 6. Models and the alias map`)
- **Quote (verbatim):**
  - `"| `govern` | Auditor, Examiner, Librarian (lessons) | judge-eu, judge-pub, batch, embed | 30,000 · 60 M | content safety |"`
  - `"**Claude is never the default and never sees estate data**: no EU Data Zone option exists, it is sold through the Marketplace with Anthropic as a separate processor, and its lifetime as a generally available model is 12 months."`
- **Why it matters:** `07 §6.2` requires `Estate-confidential` data to use `"**EU Data Zone Standard** or regional — never Global"`, enforced per access contract. Yet `04 §4.3` places `Auditor`, `Examiner`, and `Librarian (lessons)`—which read `estate-confidential` lessons, ledgers, and outcomes—under one `govern` contract permitting `judge-pub` (Claude on `acia-global`, Anthropic processor) and `batch` (`acia-flex` Global). `05 §3` `W7 Dream` also consolidates estate lessons using `"batch or flex deployments where the data class allows"`. This breaks the gateway residency boundary (`C9`, `Q-PRV-1`, `ADR-10`, `ADR-25`).
- **Fix:** Remove `judge-pub` and `batch` (`acia-global`/`acia-flex`) from `govern`. Split `govern` into `govern-eu` (`Auditor`, `Librarian (lessons)`, T3 `Examiner` — restricted to `acia-eu` and `acia-judge-eu`) and `govern-pub` (synthetic T1 `Examiner` — zero access to `lessons` or estate `ledger`).

### B-03 · Critical · Shared group contracts, coarse hub app roles, and spoofable `x-sub-agent-id` header break least privilege
- **File and heading:** `<repo>\docs\design\04-landing-zone-and-citadel.md` (`### 4.3 The access contracts` and `### 4.4 The publish contract: tools, and who may call them`)
- **Quote (verbatim):**
  - `"Because one key is shared by everyone holding a contract, per-agent attribution comes from the token's `azp` claim and, until that is proven for Entra agent identities (spike **S-ID-2**), an `x-sub-agent-id` header."`
  - `"content safety; **per-agent counters** so the Detective cannot starve the Skeptic"`
- **Why it matters:** Sharing one APIM contract and key per group creates three escalation paths: (1) Any agent in `investigate` can spoof `x-sub-agent-id: skeptic` to exhaust the Skeptic’s token quota, falsify attribution, or call `acia-judge-eu`. (2) In `04 §4.4`, tools are granted per *group*: in `study`, untrusted-web-reading `Scholar` can call `atlas-propose` (intended only for `Librarian (Atlas)`); in `govern`, `Auditor` and `Librarian (lessons)` can call `exam-bank`, and `Auditor`/`Examiner` can write `lessons`. (3) Citadel’s gateway app defines only three coarse roles (`Model.Invoke`, `MCP.Invoke`, `Agent.Invoke`); without per-product `azp` allow-lists in APIM policy, any agent holding `Model.Invoke` that obtains another group’s key passes JWT validation.
- **Fix:** Enforce an explicit `azp`/`oid` allow-list per APIM product, alias, and MCP tool in APIM policy—never trust `x-sub-agent-id`. Split `Scholar` onto a read-only contract separate from `Librarian (Atlas)`.

### B-04 · Critical · Agent-authored pull requests to the monorepo trigger self-hosted runners with OIDC inside the spoke VNet
- **File and heading:** `<repo>\docs\design\07-security-architecture.md` (`### 5.1 The lethal trifecta, per agent group`); `<repo>\docs\design\10-test-and-evaluation.md` (`## 9. Platform mapping`); `<repo>\docs\design\11-delivery-and-operations.md` (`## 3. Pipelines`)
- **Quote (verbatim):**
  - `"| **Engineer** — Engineer | no estate data in the prompt | **yes**: source repositories, recipes | pull requests to our own repository; reviewed | broken at *private data* |"`
  - `"Anything that calls the hub, a model or a private endpoint runs on **self-hosted runners that are Container Apps event jobs inside the spoke's network**, authenticating with workload identity federation"`
- **Why it matters:** `11 §1` places `infra/`, `contracts/`, `services/`, `workflows/`, `moves/`, and `atlas/` in one monorepo. `Engineer`, `Study`, and method-learning (`FR-G4`) open PRs to this repo (`07 §5.1`). Because the `pr` workflow runs `what-if`, contract tests, and L3 smoke tests on **self-hosted runners inside the spoke VNet with Azure OIDC credentials** (`10 §9`, `11 §3`) on every `pull_request`, a prompt-injected agent can modify a test, script, or Bicep file in a PR and execute code inside the spoke VNet with OIDC credentials *before* human review. Also, `07 §5.1` misclassifies customer source repositories (`FR-A7`) as `"no estate data"`.
- **Fix:** Restrict agent PR tokens to declarative paths (`atlas/`, `moves/`), block bot-authored PRs from triggering self-hosted/OIDC `pr` workflows until a human maintainer approves the run, and classify customer source repositories in `07 §5.1` as `Estate-confidential`.

### B-05 · Critical · Nine-layer prompt-injection defense fails open on MCP tool responses, prompts >10,000 characters, `<documents>` delimiter breakout, and `x-policy-id` override
- **File and heading:** `<repo>\docs\design\07-security-architecture.md` (`## 5. Defence against prompt injection in nine layers`); `<repo>\docs\design\04-landing-zone-and-citadel.md` (`### 4.4 The publish contract: tools, and who may call them`)
- **Quote (verbatim):**
  - `"| 2 | **Gateway screening** | `llm-content-safety` with `shield-prompt` on every route that carries untrusted text; the policy now covers **MCP and A2A** payloads, not only chat |"`
  - `"**Streaming caveat.** MCP responses stream, so gateway policies that read the *response* body (content-safety on the response, PII de-anonymisation) do not apply; inbound screening, authentication, limits and usage logging do."`
- **Why it matters:** Four gaps break Layers 1–4: (1) Attacker-controlled Azure tags, resource names, and invoice lines return via `estate-read` and `cost-query` MCP responses, which neither pass through `docs-fetch` (`04 §4.4`) nor get screened by APIM `llm-content-safety` (which skips streaming MCP responses, `04 §4.4`). (2) Foundry agent tool-response guardrails are Preview and exclude MCP (`https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview`, quote: `"Tool response (Preview) — The content returned from a tool to the agent. Agents only."`; `research/foundry-governance-and-framework.md` §3). (3) APIM `shield-prompt` scans ≤10,000 characters (`research/citadel.md` §4), and Foundry indirect-attack detection requires `<documents>` delimiters (`research/foundry-governance-and-framework.md` §3) that unescaped `</documents>` in tags can break out of. (4) Callers can override deployment guardrails via `x-policy-id` (`research/foundry-governance-and-framework.md` §3), unstripped in `04 §3.4`.
- **Fix:** Run the Document reader’s sanitiser, `</documents>` escaping, length cap, and Prompt-Shields check inside `estate-read`, `cost-query`, `directory-read`, and `Brief service` before returning MCP responses; strip `x-policy-id` in APIM inbound policy; and propagate taint at the run level in Layer 4.

### B-06 · Major · Unsigned approval records in `approvals-index` and incomplete `target_hash` definition allow database forgery and TOCTOU drift
- **File and heading:** `<repo>\docs\design\07-security-architecture.md` (`## 4. Approvals that cannot be forged or reused`); `<repo>\docs\design\06-data-and-knowledge.md` (`### 7.2 The operational store, container by container`)
- **Quote (verbatim):**
  - `"| **Bound to one target** | the approval stores a hash of the Move id and version, the exact resource ids, the parameters and the price or saving shown; the Move runner recomputes the hash and refuses on any difference |"`
  - `"| `approvals-index` | `/approvalId` | for ever; the authoritative record is the audit ledger |"`
- **Why it matters:** `approvals-index` sits in the shared Cosmos DB account (`06 §7.2`) and the WORM ledger (`06 §7.3`) is signed only once daily (`"daily signed digest"`). Without per-approval asymmetric signing by the Approval service, any compromised Cosmos DB writer can inject a forged approval. Also, while `06 §2` says `target_hash` is `"bound to the *state* of the target"`, `07 §4` omits the resource’s live ARM `etag` or configuration hash, enabling TOCTOU overwrites.
- **Fix:** Include the target’s live ARM `etag`/config hash in `target_hash`, sign every approval record at creation with a Key Vault asymmetric key held only by the Approval service, and verify that signature in both the Broker and Move runner.

### B-07 · Major · Approver registry can be poisoned via untrusted tags/replies, and purchase step-up MFA lacks an unlicensed fallback
- **File and heading:** `<repo>\docs\design\07-security-architecture.md` (`## 4. Approvals that cannot be forged or reused`); `<repo>\docs\design\05-agents-and-orchestration.md` (`## 2. The roster`)
- **Quote (verbatim):**
  - `"| **Right person** | the approver must be a registered approver *for that target* in the Estate service (owner or delegate), checked by deterministic code, not by a model |"`
  - `"| **Step-up for money** | purchases require a Conditional Access **authentication context** (fresh MFA) at the approval page; no card can approve a purchase by itself |"`
- **Why it matters:** `Surveyor` and `Diplomat` write ownership proposals to the Estate service from resource tags and user replies (`03 §5`, `05 §2–3`). If agent-inferred owners become registered approvers without RBAC verification, an attacker editing a tag can self-register as approver. Second, Conditional Access authentication contexts (`07 §4`) require Entra P1/P2, violating `01 §2` A5 (`"No licence is assumed beyond Azure subscriptions"`) with no fallback in `07 §11`.
- **Fix:** Derive approver and hat eligibility (`owner` vs `Finance`) exclusively from human-managed Entra groups or Azure RBAC role assignments—never from `Surveyor`/`Diplomat` proposals. Add an unlicensed fallback in the Approval service requiring fresh OIDC login (`prompt=login`, `max_age=300`) and verifying the token’s `amr` MFA claim.

### B-08 · Major · Execution identity per Move *class* and shared `snet-aca` subnet break per-Move isolation and Z3 network segmentation
- **File and heading:** `<repo>\docs\design\07-security-architecture.md` (`## 2. Trust zones, physically` and `### 3.1 Who has an identity`); `<repo>\docs\design\04-landing-zone-and-citadel.md` (`## 6. Network`)
- **Quote (verbatim):**
  - `"| **Execution identities** | user-assigned managed identities, one per *Move class* | a handful | carry out one approved Move | **none** at rest; a time-boxed role assignment exists only while a Move runs ([§3.3](#33-the-execution-identity-just-in-time-without-pim)) |"`
  - `"| `snet-aca` /27 | Container Apps environment (internal), workload-profiles, Consumption | tool services, Approval, Policy, Brief, jobs |"`
- **Why it matters:** Concurrent Moves of the same Move class share one managed identity and simultaneously hold write rights on multiple targets. Also, `07 §2` claims Z3 has `"its own subnet"`, but `04 §6` puts Z2 tool services, Brief, Spine jobs, and Z3 into one `/27` subnet (`snet-aca`) and one Container Apps environment.
- **Fix:** Enforce a single-active-Move lease per execution identity, and split `snet-aca` in `04 §6` into `snet-tools` (Z2/Spine) and `snet-exec` (Z3) with NSG isolation.

### B-09 · Major · Audit ledger on locked WORM append blobs (`ADR-32`) omits `allowProtectedAppendWrites`, hits the 50,000-block limit, and breaks hash-chaining under concurrency
- **File and heading:** `<repo>\docs\design\06-data-and-knowledge.md` (`### 7.3 The audit ledger`)
- **Quote (verbatim):**
  - `"Each entry is a JSON line carrying a sequence number, the hash of the previous entry, the hash of its payload, a pseudonymous actor id and a timestamp; entries are appended to a day's append blob inside a container whose **retention policy is time-based and locked**."`
- **Why it matters:** (1) Locked container WORM policies block `Append Block` unless `allowProtectedAppendWrites` is set before locking (`https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-container-level-worm-policies`, quote: `"Once the time-based retention policy is locked, the allowProtectedAppendWrites and the AllowProtectedAppendWritesAll property settings can't be changed."`). (2) Append blobs allow at most 50,000 blocks (`https://learn.microsoft.com/en-us/rest/api/storageservices/understanding-block-blobs--append-blobs--and-page-blobs`, quote: `"Each block in an append blob can be a different size, up to a maximum of 4 MiB, and an append blob can include up to 50,000 blocks."`), so logging every model/tool/agent call (`FR-X1`) as one block to a single daily blob fails with HTTP 409 `BlockCountExceedsLimit`. (3) Concurrent writers appending directly to one blob interleave and break `hash of the previous entry`.
- **Fix:** Set `allowProtectedAppendWrites: true` before locking, funnel all writes through one ETag-sequenced (`If-Match`) Audit Writer that micro-batches lines and rolls over blobs at 40,000 blocks, and sign critical entries individually.

### B-10 · Major · Nightly `W7 Dream` and `Librarian (lessons)` autonomously write to the Lesson Book without human review, enabling persistent memory poisoning
- **File and heading:** `<repo>\docs\design\05-agents-and-orchestration.md` (`## 2. The roster`, `## 3. The workflows`, and `## 8. People in the spine`)
- **Quote (verbatim):**
  - `"| **Librarian (lessons)** | govern | `acia-reason` | Lesson Book, Atlas | reviewed lessons |"`
  - `"*Teach* creates a lesson draft that a reviewer confirms."`
- **Why it matters:** `05 §8` says a human reviewer confirms lessons, but `05 §2–3` lets the AI agent `Librarian (lessons)` write `"reviewed lessons"` during `W7 Dream` with `"Waits for people: no"`. Poisoned tags or replies can thus be consolidated into active lessons that steer future investigations for 12 months (`06 §7.2`).
- **Fix:** Require authenticated human confirmation before any lesson transitions from `draft` to `active` in `lessons`; `W7 Dream` may propose drafts only.

### B-11 · Major · Unattended Lab experiments (`W6`) allow an agent reading untrusted web pages to deploy real Azure resources without human approval
- **File and heading:** `<repo>\docs\design\05-agents-and-orchestration.md` (`## 3. The workflows`); `<repo>\docs\design\07-security-architecture.md` (`## 8. The Lab as a security boundary`)
- **Quote (verbatim):**
  - `"| **W6** | **Experiment** | a question the Atlas cannot answer | Experimenter plans → Lab controller vends → probe → **waits for the bill** (hours to days) → Skeptic → Librarian | none, but the Lab expiry is a hard stop | Lab budget and expiry; runs at least two days |"`
- **Why it matters:** `04 §4.4` gives `experiment` both `docs-fetch` (`"read, untrusted"`) and `lab-control` (`"write (Lab only)"`), and `W6` runs with `"Waits for people: none"`. An indirect injection in a fetched page can trigger `lab-control` deployments, and since Azure budgets lag 8–24 hours (`07 §8`), an attacker can burn 8–24 hours of Lab SKUs before the budget action group fires.
- **Fix:** Remove `docs-fetch` and `ms-learn` from the `experiment` contract, require every opaque run code to map to a human-merged Bicep recipe in `atlas/recipes/`, and enforce a pre-deploy hourly retail-cost cap inside the deterministic Lab controller.

### B-12 · Major · EU AI Act Annex III and GDPR workplace-monitoring conflict in `DR-17` (per-person approver scoring) and `FR-V3/V4`
- **File and heading:** `<repo>\docs\design\09-safeguards-and-drift-controls.md` (`### 2.3 Drift in behaviour and in people`); `<repo>\docs\design\06-data-and-knowledge.md` (`## 5. Estate knowledge: privacy by design`)
- **Quote (verbatim):**
  - `"| **DR-17** | **Approvers** | decisions become reflexive; one person approves everything | two hats for purchases; hats are enforced by the service | approval-latency distribution (decisions in seconds), approve/decline ratio per person, sampled review of approved cases | a review prompt; rotate the approver; add friction (a re-read step) for the person | human |"`
  - `"personal data is used to reach the right person at the right time and for nothing else — it is never an input to evaluating a person."`
- **Why it matters:** Computing per-person `"approval-latency distribution (decisions in seconds), approve/decline ratio per person"` to judge an employee’s diligence and `"rotate the approver; add friction (a re-read step) for the person"` (`DR-17`), alongside inferring employee working rhythms (`FR-V3/V4`), contradicts `06 §5` and `08 §2.2`, risking classification as workplace behavioural monitoring under EU AI Act Annex III point 4(b) and mandatory works-council co-determination.
- **Fix:** Replace per-person scoring in `DR-17` with uniform confirmation friction for all high-value Moves and aggregate team/system metrics only; make working hours and language strictly user-configured opt-in preferences.

### B-13 · Major · Kill-switch latency and completeness gaps: disabling an Entra Agent ID leaves issued JWTs valid for 60–90 minutes, and stopping the Broker leaves in-flight Moves running
- **File and heading:** `<repo>\docs\design\07-security-architecture.md` (`### 10.3 Kill switches`)
- **Quote (verbatim):**
  - `"| One **agent** | disable its Entra agent identity | no token is issued; the agent cannot call the hub | minutes |"`
  - `"| The **execution plane** | stop the broker (feature flag in the configuration store) and remove its delegated role | no grant, so no change anywhere | seconds to minutes |"`
- **Why it matters:** Disabling an Entra agent identity does not revoke already-issued access tokens (valid for 60–90 minutes) at APIM `validate-jwt` without CAE. Second, stopping the Broker prevents *new* grants but does not stop running Move runner jobs or revoke their active role assignments.
- **Fix:** Add an APIM blocklist check on `azp`/`oid` (plus Foundry Control Plane session stop) for immediate per-agent revocation, and have the execution-plane kill switch trigger the Sweeper to revoke all active execution role assignments and stop running Move runner jobs immediately.

### B-14 · Major · GDPR Art. 22 & Art. 17 misstatements and Citadel APIM PII anonymisation 125,000-character bypass
- **File and heading:** `<repo>\docs\design\08-governance-and-compliance.md` (`### 4.2 Positions`); `<repo>\docs\design\04-landing-zone-and-citadel.md` (`### 4.3 The access contracts`)
- **Quote (verbatim):**
  - `"| **Automated decisions (Art. 22)** | Moves need human approval; the approval is authenticated and recorded, which meets the intent |"`
  - `"| **Subject rights** | access and erasure are served from the Estate service; the audit ledger is pseudonymous, so erasing the **mapping** anonymises the ledger without breaking its chain; retention of the pseudonymous approval record rests on the organisation's audit obligation |"`
- **Why it matters:** `08 §4.2` says `"Moves need human approval"`, overlooking Moves executed autonomously under **autonomy credentials** (`FR-A5`/`FR-X2`). Second, deleting the Estate pseudonym mapping does not achieve GDPR anonymisation if ledger timestamps/resource IDs correlate with user UPNs in Azure Activity Logs; retention must cite **GDPR Art. 17(3)(b)/(e)**. Third, Citadel’s gateway PII anonymisation (`04 §4.3`) stops scanning after ~125,000 characters (`research/citadel.md` §4) and stores raw PII mappings in Cosmos DB `pii-usage` when `piiStateSavingEnabled` is true.
- **Fix:** Clarify in `08 §4.2` that Art. 22 is inapplicable (Moves target cloud resources, not natural persons) and that audit retention rests on Art. 17(3)(b)/(e); pseudonymise PII deterministically in tool services before the hub and set `piiStateSavingEnabled = false`.

### B-15 · Minor · Undeclared public ingress for the web approval page (`07 §4` vs `07 §7`)
- **File and heading:** `<repo>\docs\design\07-security-architecture.md` (`## 4. Approvals that cannot be forged or reused` and `## 7. Network and the short list of exceptions`)
- **Quote (verbatim):**
  - `"| **Authenticated human** | a Teams Adaptive Card `Action.Execute` with single sign-on, or an e-mailed link to an approval page behind Entra sign-in; the Approval service validates the user's token itself |"`
- **Why it matters:** `07 §4` requires an Entra-authenticated web approval page for e-mail links and all commitment purchases, yet `04 §6` and `07 §7` (`X1–X4`) omit this web endpoint from the network topology and `"complete list"` of public-ingress exceptions.
- **Fix:** Declare the web approval page in `04 §6` and `07 §7` (private-only over VPN/Entra Private Access or as exception `X5` in `snet-edge` behind Entra sign-in and WAF).

### B-16 · Minor · Single-tenant Commons cohort fallacy and dynamic-sessions state reuse across cases
- **File and heading:** `<repo>\docs\design\01-requirements-and-principles.md` (`## 2. Assumptions` and `## 4. Quality targets`); `<repo>\docs\design\04-landing-zone-and-citadel.md` (`### 4.4 The publish contract: tools, and who may call them`)
- **Quote (verbatim):**
  - `"| Q-PRV-1 | Estate data stays in the tenant and the EU boundary; the Commons receives only claims, recipes and counts above a minimum cohort. |"`
- **Why it matters:** Under `A3` (`"One Entra tenant, one deployment per organisation"`), any exported "count" comes from N=1 organisation, leaking its estate profile. Second, `ADR-37` batches computations across 1-hour `Container Apps dynamic sessions`; sharing a session across cases or between `investigate` (estate-confidential) and `experiment` (public) leaks state.
- **Fix:** Export zero estate counts to the Commons in single-tenant mode, and scope every dynamic-session ID strictly to `(group, case_id)`.

### B-17 · Minor · Release gate `G8` (`08 §1.3`) relies on 24-hour-delayed Azure Policy compliance state and preview `Audit` policies
- **File and heading:** `<repo>\docs\design\08-governance-and-compliance.md` (`### 1.3 Policy as code`); `<repo>\docs\design\09-safeguards-and-drift-controls.md` (`### 2.1 Drift in what we own`)
- **Quote (verbatim):**
  - `"Policy compliance (effects take about 15 minutes, compliance data up to 24 hours); the release gate **G8**"`
- **Why it matters:** Querying Azure Policy compliance at deploy time reads state up to 24 hours old (`DR-7`) and passes preview `Audit`-only policies (`08 §1.3`) even when violated.
- **Fix:** Implement `G8` as synchronous Azure Resource Graph and Foundry SDK assertions against live resource properties in the release pipeline.

---

## 3. The decision table

| ADR | Verdict | Confidence | Strongest alternative | What would change my mind |
|---|---|---|---|---|
| **ADR-01** | **Agree** | High | A2A handoff/group chat; rejected (propagates injection). | Typed records failing L4 rediscovery benchmarks. |
| **ADR-02** | **Agree with changes** | High | Standalone AI Gateway (`aigateways`, preview/unpriced); keep APIM, strip `x-policy-id`, enforce `azp` allow-lists (**B-03**, **B-05**). | `aigateways` GA in ≥2 EU regions with private link, content safety, and pricing. |
| **ADR-03** | **Agree with changes** | High | Single subscription with RGs; rejected (blast radius/quota), but disclose Broker RBAC delegation in estates (**B-01**). | Removing Z3 for human-applied PRs only. |
| **ADR-04** | **Agree** | High | West Europe; rejected (lacks managed VNet, AI LZ full deploy, hosted-agent meters). | West Europe reaching full feature and meter parity. |
| **ADR-05** | **Agree** | High | Foundry Managed VNet; rejected (unlogged €250–800/mo managed Firewall). | Managed VNet supporting BYO firewall and outbound logs. |
| **ADR-06** | **Agree with changes** | High | Shared project identity or 3 coarse groups; rejected, **but** shared contracts (`study`, `investigate`, `govern`) and spoofable `x-sub-agent-id` break least privilege and residency (**B-02**, **B-03**). Split `Scholar` from `Librarian (Atlas)` and `govern-eu` from `govern-pub`; enforce JWT `azp`/`oid` per tool/alias in APIM. | `S-ID-2` proving Entra Agent ID tokens carry distinct `azp`/`oid` claims enforced per tool/alias in APIM without `x-sub-agent-id`. |
| **ADR-07** | **Agree with changes** | High | PIM eligible assignments for managed identities (impossible per `https://learn.microsoft.com/en-us/azure/role-based-access-control/pim-integration`, quote: `"you can't create eligible role assignments for applications, service principals, or managed identities"`) or standing write roles (violates Q-SEC-1). Fix **B-01**, **B-06**, **B-08**: sign approvals with Key Vault, separate job-start from role-grant, and enforce 1-Move concurrency per identity. | Native Entra PIM JIT activation for managed identities at resource scope conditioned on cryptographic approval tokens. |
| **ADR-08** | **Agree with changes** | High | Teams Approvals app; rejected (no target-hash binding), **but** hash live ARM `etag`/config into `target_hash`, sign approvals with Key Vault, block tag-based approver poisoning, declare web ingress, and add OIDC `max_age` MFA fallback (**B-06**, **B-07**, **B-15**). | Native Foundry/Teams approval primitive with cryptographic target binding, dual-hat checks, and step-up MFA. |
| **ADR-09** | **Agree with changes** | High | All-Global (violates C9) or all-Regional (+30–50%). Fix `04 §4.3` on `govern` (**B-02**) by forbidding Global/Flex pools on estate/personal contracts. | Flex and Batch across all GPT-6 models in the EU Data Zone. |
| **ADR-10** | **Agree with changes** | High | Same-family judge; rejected for correlated blind spots. Isolate `judge-pub` (Global Claude) out of `govern` (**B-02**) into `study` and `govern-pub`. | Claude becoming available under `DataZoneStandard` (EU) covered by the Microsoft DPA. |
| **ADR-11** | **Agree** | High | Database-only Atlas; rejected (Git gives signed releases and PR review). | Sub-second per-estate transactional Atlas writes. |
| **ADR-12** | **Agree with changes** | Medium | Azure SQL serverless (Ledger tables). Cosmos serverless acceptable if `approvals-index` is Key Vault-signed (**B-06**) and RBAC is per-container. | `S-DATA-4`/`S-DATA-5` showing Cosmos serverless costs exceed Azure SQL serverless. |
| **ADR-13** | **Agree** | High | ADX Dev/Test or Synapse serverless; rejected (standing floor/scan cost; C1 exception recorded). | Zero-standing-cost Microsoft embedded Parquet engine. |
| **ADR-14** | **Agree** | High | Foundry Memory; rejected (preview, no VNet, extraction poisoning, bypass `B3`). | Foundry Memory GA with BYO-VNet and gateway routing. |
| **ADR-15** | **Agree with changes** | High | Foundry toolboxes; held until `S-NET-1`. Sanitise untrusted text inside MCP tools (**B-05**) and remove `docs-fetch` from `experiment` (**B-11**). | APIM response-side MCP screening and `S-NET-1` passing. |
| **ADR-16** | **Agree with changes** | High | Deployment Environments/Lab Services (retiring 2027). Require signed Bicep recipes and pre-deploy Price-engine cap in Lab controller (**B-11**). | Hard real-time spend caps on EA/MCA subscriptions. |
| **ADR-17** | **Agree with changes** | High | Foundry Teams publishing; rejected (public route, no bound card approvals). Declare web approval ingress (**B-15**). | Bot Service private-link ingress and signed card callbacks. |
| **ADR-18** | **Agree** | High | Managed Grafana; rejected (standing cost, Essential deprecated). | Azure Monitor dropping `AppGenAIContent` RBAC at GA. |
| **ADR-19** | **Agree with changes** | Medium | Foundry guardrails and Defender alone; rejected because agent guardrails are preview and exclude MCP (`https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview`). Fix the four bypasses in **B-05** (in-tool MCP screening, `</documents>` escaping, >10k-char handling, stripping `x-policy-id`). | Native GA data-flow taint enforcement and APIM response-side MCP screening. |
| **ADR-20** | **Agree with changes** | High | Mandatory Agent 365 and Defender for AI Services; rejected to keep the MIT core licence-free (`https://learn.microsoft.com/en-us/defender-xdr/security-for-ai/transition-agent-security-to-agent-365`, quote: `"Effective July 1, 2026, AI agent security capabilities for Microsoft Copilot Studio and Microsoft Foundry agents require a Microsoft Agent 365 license"`). Add OIDC `max_age` MFA fallback (**B-07**). | Microsoft bundling Agent 365 threat detection and Conditional Access into base Azure subscriptions. |
| **ADR-21** | **Agree with changes** | High | Agent-based drift detection; rejected (probabilistic). Remove per-person scoring from `DR-17` (**B-12**). | Native ARM/Stack drift enforcement for Foundry agent versions. |
| **ADR-22** | **Agree** | High | Foundry evaluations alone; rejected (no held-out synthetic-estate exams). | Native stateful synthetic-estate exams with sealed keys. |
| **ADR-23** | **Agree with changes** | High | Terraform + AzAPI or AzDO; Bicep + Stacks + GHA sound if bot PRs cannot run on self-hosted OIDC runners unreviewed (**B-04**). | Required Azure resource lacking Bicep support. |
| **ADR-24** | **Agree** | High | CMK and Managed HSM everywhere; rejected because hosted-agent `$HOME` cannot use CMK and Managed HSM costs ~€2,000/month without a driver. | Regulated deployment mandating CMK on BYO Cosmos DB, Storage, and AI Search. |
| **ADR-25** | **Agree with changes** | High | All-Regional (+30–50%) or All-Global (violates C9). Fix the `govern` contract leak (**B-02**), disable Citadel `piiStateSavingEnabled`, and pseudonymise PII in tool services before the hub (**B-14**). | Microsoft guaranteeing EU-only processing and abuse-review residency on Global Standard deployments. |
| **ADR-26** | **Agree with changes** | High | Azure Cost Management budgets as primary cap; rejected (8–24h lag). Enforce per-agent token caps via verified JWT `azp`/`oid` (**B-03**). | Synchronous hard euro-spend caps per agent identity in Foundry. |
| **ADR-27** | **Agree** | High | Azure SRE Agent always-on; rejected (~€283/mo idle, bypasses Citadel). | SRE Agent moving to 0 AAU idle consumption behind Citadel. |
| **ADR-28** | **Agree with changes** | High | Managed Marketplace app; rejected (single-tenant phase 1). Isolate bot PRs in monorepo (**B-04**). | Multi-tenant SaaS requirement in phase 2+. |
| **ADR-29** | **Agree with changes** | High | Compliance Manager templates on day one; rejected, but gate `G8` must assert live ARM/Foundry state synchronously (**B-17**). | External auditor requiring Compliance Manager exports. |
| **ADR-30** | **Agree** | High | Warm second region in phase 1; rejected (doubles fixed floor; degrades to ask-only `Q-REL-1`). | SLA requiring <1h RTO for active Move execution. |
| **ADR-31** | **Agree** | High | Floating references; rejected (unpinned models/images/packages invite supply-chain drift). | Nothing; signed pin manifests are mandatory. |
| **ADR-32** | **Agree with changes** | Medium | Confidential Ledger (~€103/month) or Azure SQL Ledger tables. WORM append blobs work **only if** `allowProtectedAppendWrites: true` is set before locking, blobs roll over before 50,000 blocks, a single ETag-sequenced writer prevents hash-chain races, and each approval is signed with Key Vault (**B-06**, **B-09**). | `S-DATA-2` showing append-blob ETag contention; if so, switch to **Azure SQL serverless Ledger tables** + daily WORM digest. |
| **ADR-33** | **Agree** | High | Spine inside hosted agent (breaks identity separation) or pre-release Durable Extension. Verify HMAC on checkpoint load. | Durable Extension GA with verified checkpoint isolation. |
| **ADR-34** | **Agree** | High | Foundry Routines as primary scheduler; rejected (no budget envelope, no CMK). | Routines supporting typed envelopes and multi-step workflows. |
| **ADR-35** | **Agree** | High | Mandating an existing hub; rejected (blocks adoption where none exists). | All target landing zones shipping a pre-deployed Citadel hub. |
| **ADR-36** | **Agree** | High | All-Python or all-C#; rejected (`.NET` needed for `Action.Execute` cards and Z3 static typing). | Python Agents SDK adding `Action.Execute` SSO support. |
| **ADR-37** | **Agree with changes** | High | Running model-written code inside the hosted agent’s microVM; rejected because it shares the agent’s token endpoint. Scope dynamic sessions per `(group, case_id)` so batching never shares state across cases or trust zones (**B-16**). | Container Apps Sandboxes reaching GA in Sweden Central with per-call ephemeral microVMs. |

---

## 4. What is strong

1. **Deterministic spine with agentic leaves (`05 §1`, `ADR-01`):** Forbidding direct agent-to-agent messaging and passing only `case_id` and budgets through deterministic workflows eliminates conversational contagion and bounds runaway loops across envelope, middleware, and gateway.
2. **Zero standing write permissions for agents (`07 §3`, `Q-SEC-1`):** Keeping all fourteen agent identities read-only and placing all estate mutations inside a model-free C# execution plane (`Z3`) is the strongest architectural defence against prompt injection.
3. **Two-instance split of the Librarian and isolated Forger (`05 §2`, `07 §5.1`):** Separate identities and contracts for `Librarian (Atlas)` (public write, no estate read) and `Librarian (lessons)` (estate read, no public write), plus an isolated `Forger` with sealed answer keys, sever exfiltration and exam-cheating paths.
4. **Honest treatment of platform sharp edges (`02 §4`, `04 §8`, `09 §5`):** The gateway-bypass register (`B1–B11`), the preview register with switches and GA fallbacks, and the explicit recognition that Purview lacks network isolation (`https://learn.microsoft.com/en-us/purview/ai-azure-foundry`, quote: `"Microsoft Purview Data Security Policies for Foundry Services interactions apply to API calls that use Microsoft Entra ID authentication with a user-context token"`), Defender for agents moved to Agent 365 (`https://learn.microsoft.com/en-us/defender-xdr/security-for-ai/transition-agent-security-to-agent-365`), and PIM cannot make managed identities eligible (`https://learn.microsoft.com/en-us/azure/role-based-access-control/pim-integration`) reflect genuine verification.
5. **Typed, template-rendered channel for the Diplomat (`07 §5.1`) and non-conversational approvals (`07 §4`):** Pre-resolving recipients in the Brief service, banning model-authored markup/links, and refusing approvals from voice, avatar, SMS, or free-text chat neutralises conversational persuasion and markdown-exfiltration attacks.

---

## 5. What is missing

1. **End-to-end cryptographic chain of custody from Approval to Role Assignment (`07 §3.3`, `07 §4`):** Asymmetric signing of individual approval records (binding the approver's Entra token claims, `target_hash` including live ARM `etag`, `nonce`, and `expires` with a Key Vault key) verified independently by both the Credential Broker and Move runner.
2. **In-tool untrusted-text sanitisation for `estate-read`, `cost-query`, and `directory-read` (`04 §4.4`, `07 §5`):** Mandatory spotlighting, `</documents>` escaping, length truncation, and Prompt-Shields screening inside the MCP tool services that read Azure tags, resource names, invoice lines, and directory fields before returning streaming MCP responses.
3. **Per-agent identity (`azp`/`oid`) binding to tools and aliases at the hub (`04 §4.3`, `04 §4.4`):** An explicit `azp`/`oid`-to-tool and `azp`/`oid`-to-alias enforcement table in APIM policy replacing group-wide tool grants and the spoofable `x-sub-agent-id` header.
4. **CI/CD trust-boundary isolation for agent-authored pull requests (`07 §5.1`, `10 §9`, `11 §3`):** Hard separation preventing untrusted bot/agent PRs (`Engineer`, `Study`, `W7`) from executing on self-hosted runners with OIDC inside the spoke VNet prior to human code review.
5. **Per-container Cosmos DB data-plane RBAC scoping (`06 §7.2`, `07 §3.1`):** Fine-grained Cosmos DB data-plane role assignments scoped to individual containers in the shared operational account so that only the Approval service can write `approvals-index`, only the Spine can read/write `workflow-checkpoints`, and only the operator can write `controls`.
