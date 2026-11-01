# Round 2 · C — Security, safety and compliance, adversarial (model: grok-4.6)

> Raw report, saved exactly as the reviewer returned it (everything below the rule). Reviewed on 2026-11-01: the written design (`docs/design/`, commit `3543f3b`). Lens: attack paths, Round-1 landing check, compliance claims, identity matrix. Line references like `05:136` mean line 136 of `05-data-and-integrations.md`. The orchestrator's spot-checks of what this reviewer cited are in the [disposition](disposition.md).

---

**Verdict.** Round-1 security fixes **landed and cohere**: bound single-use approvals, credentials as code, per-agent Hub contracts, screening at ingress, time-boxed purchases, DoW trips, and documented in-flight stop limits. The action plane is still **not specified tightly enough to build**: R1 identity trusts the bot, `workflows` can delete the consumption marker, purchase **scope** is unbound, and Foundry session data is outside erasure. Do not treat the written design as fail-closed until those four are closed.

**Top 5 fixes.** (1) Approval service must verify the approver’s **Entra token** (SSO/`acrs`); never trust Bot Framework `from`. (2) Split Cosmos: `workflows` **C-only** on ledger except Respond’s Lessons; consumption items **C-only for runner**. (3) Bind purchase **quote + billing/reservation scope**; name **Savings plan purchaser**; ABAC on role, principal, **and assignment scope**. (4) GitHub App: **draft PRs only**, no push to default. (5) Erase **Foundry conversation history**; isolate Evaluate from the prod Hub (or test the contract firewall as a release gate); add DORA / Responsible AI as adopter mappings, not silence.

### Round-1 security landing (rows 1–3, 5–10, 19–21)

| # | Status | Evidence |
|---|---|---|
| 1 Approval bound/displayed/single-use/fail-closed | **Landed** | `06:127–139`, `05:149–161`, `12:65–67` |
| 2 Credentials as code on model-unwritable facts | **Landed** | `06:88,151`, `03:192`, `08:123` |
| 3 Contract per agent + Entra token; key ≠ identity | **Landed** | `06:101,108`, `02:69`, `12:25` |
| 5 Screen where untrusted text enters | **Landed** | `06:67,172`, `05:107,125`, `07:18` |
| 6 Time-boxed purchase identity, not standing | **Partly** | Create/remove `06:155–160`; **scope of the bought reservation / savings-plan role unnamed** |
| 7 Denial of wallet | **Landed** | `06:77`, `07:116–119`, `08:109` |
| 8 Tool rug-pull | **Partly** | Pin + `tools/list` `05:101`, `07:32`; **P9 unverified** `07:155`; same-schema change still open `06:71` area |
| 9 Untrusted text ↛ Engineer | **Partly** | Rule `06:87`, `03:15,34,38`; **enforced by workflow code**, invocation **bypasses Hub** `03:25`, `02:72` |
| 10 At-least-once; no blind purchase retry | **Landed** | `06:139`, `03:56`, `12:61` |
| 19 Evaluate isolation | **Partly** | No prod roles `02:137–139`, `06:214`, CI `08:11`; **same Hub** `02:137` |
| 20 Missing controls | **Landed** (homes exist) | RBAC `05:41–49`; break-glass `06`/`09`; SBOM `06`/`09`; single-flight `03`; throttling `05`; bot ack `05:135`; switches `07`; Strategy `03`; recovery `09`; shadow `08`; traffic `02:69–72` |
| 21 Stop vs in-flight | **Landed** | `06:166`, `07:94`, `08:124` |

### Attack paths

| # | Attacker / entry | Steps | What the docs stop | Residual | Buildable? |
|---|---|---|---|---|---|
| 1 Injection → Engineer/Diplomat | Estate owner / public page | Tag, log, Atlas quote, ticket, or reply as instruction | Excerpts + host split; Engineer gets ids/numbers; Diplomat cannot send or approve | Screening miss → wrong **draft**; Diplomat still **reads** replies `03:38`; workflow can put anything in Invocations `03:25` | **Partial** (P7); invocation payload not a platform control |
| 2 Approval replay / TOCTOU | Stolen card URL; racing ARM | Reuse id; swap plan; change SKU after tap | Opaque id, plan hash, etags, quote, expiry, consumption create-once `06:127–139` | Etags miss some types; **`workflows` W can delete consumption** `05:39,46,53` then re-trigger | Hash/etag **yes**; consumption integrity **no** |
| 3 Card spoof / coercion | Stolen bot secret; social | Fake Teams activity “who tapped”; or bully an owner | R2/R3 page + `acrs`/phishing-resistant; bot forwards id only | **R1**: bot asserts identity `05:136` vs “Entra sign-in” `06` R1 row; coercion **not** stopped (`07` table) | **Silent/contradictory** for R1 |
| 4 Confused deputy | Compromised tool or bot | Call runner/what-if or approvals without a bound record | Tools check caller token `06` threat table; bot has no Cosmos/`Mail` | **`plan` → runner what-if already holds family roles** `05` plan row; bot→approvals contract **unspecified** | **Not specific** |
| 5 Runner family role | Compromised `runner` MI | Resize/stop every opted-in scope | Narrow custom role; approval required; drill `07` | **Standing write** at all opted-in scopes until revoked (`06:73`); MI disable ~token lifetime | Specific enough; residual **accepted** but large |
| 6 ABAC purchase escalation | Compromised `approvals` | Assign Reservation Purchaser; buy **shared-scope** RI / savings plan | Condition on role+principal `06:158`; stored quote `06:159`; alarms | Condition **does not bind reservation scope**; Learn allows **shared billing-context** discount from a subscription purchaser ([prepare-buy](https://learn.microsoft.com/azure/cost-management-billing/reservations/prepare-buy-reservation)); savings-plan role **unnamed**; `approvals` is the trust anchor `05` end | **Too weak** |
| 7 Poison Lessons/Atlas/Detectors | PR comment / Teach box | Merge bad claim or Lesson | Human merge, knowledge CI, Lessons ≠ credential `06:88`; Engineer no free text | Poisoned **advice**; Respond-only Lessons is a **code** rule `05:51`; `workflows` **W** on lessons/ledger | CI for Atlas **yes**; Lesson writer **not** platform-enforced |
| 8 Rug-pull / alias swap | Hub/tool/model owner | Same schema, new behaviour; alias fallback | Digest probe `07:32`; pin list pulls global switch | Same-schema MCP; **P9**; Standard auto-upgrade at retirement `07:43`; fallback member can serve **unevaluated** model until 410 | Probe **yes**; behaviour **no** |
| 9 Denial of wallet + kill-switch bypass | Injected loop; in-flight run | Burn tokens; start purchase; pull terminate | Quotas, Case budget, run-rate trip `07:116–119`; switch fail-closed if unread | Purchase ≠ token; **terminate does not stop activities** `07:94` ([instance management](https://learn.microsoft.com/azure/durable-task/common/durable-task-instance-management)); submitted buy not recalled `06:166` | **Yes**, residual documented |
| 10 Exfil / eval leak / supply chain | Diplomat; eval identity; dependency | Draft/mail canaries; call prod contract; hostile pin | Recipients from directory; strip links; eval no tools/prod roles; SBOM + digest pins | Prose to **owner of record**; **same Hub** `02:137`; Foundry **history** `06:200`; hub accelerator **no releases** `09:104`; **prerelease** hosting `03:23`; GitHub App rights **unspecified** `05:121`; MCP stream unscreened at Hub | Pins **yes**; App/Hub/eval **under-specified** |

Audit tamper: immutable blob stops **edits**, not a **false append** from `approvals`/`runner` (`05` “does not stop”).

### Findings

| # | Severity | File:line | Quote (≤25 words) | What is wrong | Proposed fix |
|---|---|---|---|---|---|
| 1 | **blocker** | `05:136` vs R1 in `06` | “forwards only the opaque request id and who tapped” | R1 approver is a **bot assertion**, not an Entra token; stolen bot secret forges taps | Approval service accepts only user token + `acrs`; bot may pass `requestId` only |
| 2 | **blocker** | `05:39,46,53` | “W creates, replaces and deletes” / consumption in `ledger` | `workflows` can **delete** the single-use marker → replay | Runner **C** on `consumption`; workflows no replace/delete on those ids |
| 3 | **blocker** | `06:157–159` | “Reservation Purchaser role on one subscription” / “buys exactly the stored quote” | Quote fields omit **scope**; shared-scope buy is enrollment-wide; savings-plan role missing | Bind scope in quote+hash; ABAC on assignment scope; name Savings plan purchaser |
| 4 | **major** | `03:25`, `02:72` | “Invocations protocol… That call is not Hub traffic” | Engineer isolation is a **workflow promise**; Invocations skip Hub screening (Learn: Invocations need extra RAI settings or **nothing is screened**) | Schema-validate invocation body in the **host**; treat Hub skip as a testable invariant |
| 5 | **major** | `05:121` | “GitHub App key in Key Vault” | App could push/merge if over-permissioned; supply-chain of Atlas/Actions | Least-privilege GitHub App: PRs on protected branches only; CODEOWNERS required |
| 6 | **major** | `02:137` | “Dev contracts on the **same hub**” | Eval/prod share APIM/backends; isolation is contract+CI only | Separate products/gateways or deny-by-default + **release-gated** negative tests |
| 7 | **major** | `06:200,203`; `05:185` | Foundry keeps messages; erasure lists estate/lessons/drafts/traces | Session history **not** in erasure; 30-day idle delete ≠ Art. 17 | Delete sessions on case end **and** on erasure; document Foundry as processor |
| 8 | **major** | `05:46,51` | Lessons write is “a code rule… not a platform rule” | Compromised `workflows` forges Lessons that steer later Cases | Separate identity for Respond, or C with service-enforced type |
| 9 | **minor** | `09:17` vs `02:61` | Bot listed under `apps/approvals` | Identity story splits: own app vs approvals tree | One app, one MI, one CODEOWNERS path |
| 10 | **major** | `06:251–255` | Mapping table: AI Act, GDPR, NIS2, ISO 42001 | **DORA** and **Microsoft Responsible AI Standard** absent; “likely not high-risk” is the **adopter’s** call (already said, still easy to over-read) | Add “out of scope / adopter” rows; keep class undecided |

**Compliance.** Claims are mostly **mapping, not certification** — good. GDPR minimisation (ids, not names) is real; people in data: **owner/approver object ids**, **tag values**, **`changedBy` emails** (mapped), **mailbox replies**, **Graph `Mail.Read`**, **Foundry transcripts**, **abuse-monitoring review at Microsoft** (`06:205`). Art. 22 is reasonably treated as human approval of **resource** decisions. Art. 50 human label is specified; **machine-readable** mark “where the channel allows” is hand-wavy for Teams cards. NIS2/ISO 42001 deferred to adopter — fair. **Missing:** DORA (ICT incident, resilience testing — drills exist but unmapped) and Responsible AI Standard (impact assessment). Not overreaching except the flavour of “likely not high-risk.”

**Identities (contradictions / excess).**

| Who | Identity | Stated job | Excess / clash |
|---|---|---|---|
| 5 hosted agents | Entra Agent ID + Hub key | Model/MCP on **own** contract; no Azure | Implicit **project inference** `06:106` — mitigated only if spoke has **zero** deployments |
| `workflows` | MI | Orchestrate, send mail, invoke agents | **W** ledger/lessons/estate; **C** switches; **Foundry invoke** bypassing Hub; `Mail.Send` unless EXO app RBAC |
| `tools` | MI | Read estate/cost; `plan` front | Deputy into **runner what-if** (write-capable MIs) |
| `approvals` | MI + ABAC RBAC Admin | Records, credentials, switches, **assign purchaser** | Trust anchor; Graph group checks; **purchase blast radius** |
| `runner` + family MIs + purchase MI | User-assigned MIs | Execute approved Actions | Family MI = **all opted-in scopes**; purchase MI after assign |
| `bot` | MI, public | Opaque id → approvals | **R1 identity proxy**; 09 vs 02 path clash |
| Evaluation | Own contract, no tools | Synthetic/redacted | Same Hub as Operate |
| `pr-draft` | GitHub App key | Draft PRs | Permissions unspecified |
| Verifier | (inside `runner`) | Confirm/rollback | Same write MIs as runner |

**What I verified.** [Hosted agent permissions](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions): agents have **implicit project inference** — design `06:106` **confirmed**. [Prepare to buy](https://learn.microsoft.com/azure/cost-management-billing/reservations/prepare-buy-reservation): built-in Reservation Purchaser on a **subscription**; custom role cannot buy; **shared** billing-context scope exists — design **under-binds**. [Delegate assignments](https://learn.microsoft.com/azure/role-based-access-control/delegate-role-assignments-overview): RBAC Administrator **with conditions** is the right pattern. [Guardrails](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-guardrails): omit `rai_config` ⇒ no agent-boundary policy; Invocations unscanned without extra settings; tool-response list **excludes MCP**. [Durable instance management](https://learn.microsoft.com/azure/durable-task/common/durable-task-instance-management): terminate **does not** stop in-flight activities — `07:94` **confirmed**.

**Could not verify.** Whether APIM can inspect MCP bodies (design marks **P9 UNVERIFIED**); Citadel accelerator “capture on / public by default”; Savings plan purchaser vs Reservation Purchaser; Adaptive Cards carrying Art. 50 machine marks; ISO 42001 **product** vs **customer AMS** wording on the cited Learn page (not re-fetched).
