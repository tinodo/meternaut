# Round 1 · B — Security and safety (model: grok-4.7)

> Raw report, saved exactly as the reviewer returned it (everything below the rule). Reviewed on 2026-11-01: the decisions D1–D22 of the first design specification. Lens: threat model of the action plane, untrusted-text paths, identity, hub integration. The orchestrator's spot-checks of what this reviewer cited are in the [disposition](disposition.md).

---

Agent is idle (waiting for messages). agent_id: a3a8a459-a727-4184-b72f-60e1f66b891f, agent_type: rubber-duck, status: idle, description: Round 1 review: security and safety, elapsed: 429s, total_turns: 1, model: grok-4.7

[Turn 0]
## (a) D1–D22

| ID | Verdict | Reason |
|---|---|---|
| D1 | Agree-with-change | Workflow-owned control is right; propose tools and in-session tool loops are still side effects and a wallet. |
| D2 | Agree | Durable Functions fits multi-day waits. It does not make the activities it calls safe. |
| D3 | Agree-with-change | One identity per role matters only with a distinct hub principal. Omitting `rai_config` means no agent-boundary guardrail. |
| D4 | Agree-with-change | The hub should be the only model/tool door. A shared estate key plus forgeable role headers is not a door. |
| D5 | Agree-with-change | Aliases are right. A Global-only judge on estate cases exports customer data. |
| D6 | Agree | Git, human merge, and knowledge CI are the right Atlas control. A rubber-stamped merge still lands. |
| D7 | Agree-with-change | Separate stores are right. Approvals and credentials need distinct data-plane writers. The immutable log fights erasure. |
| D8 | Agree | A job-scoped engine is fine. The Parquet lake is still a bulk-exfil target. |
| D9 | Agree-with-change | An allow-list is necessary. A schema hash does not pin behaviour. "Read-only mode" is UNVERIFIED. |
| D10 | Agree-with-change | One Azure writer is right. Re-verify must fail closed on etag or quote mismatch, not refresh and proceed. |
| D11 | Disagree | An unsigned row the runner trusts, plus a credential that skips a fresh OK, is not approval integrity. |
| D12 | Agree-with-change | Per-class roles are necessary and still standing privileges. PIM cannot make those principals eligible. |
| D13 | Agree-with-change | Draft-then-send is right. Free text and card payloads must not approve, and the model must not choose the recipient. |
| D14 | Agree-with-change | No-permission agent IDs are correct and irrelevant while the hub accepts a shared subscription key. "Keyless" contradicts Citadel. |
| D15 | Agree-with-change | Operate isolation is right. The evaluate profile must be incapable of calling prod contracts or real scopes. |
| D16 | Agree-with-change | Fleet stop is useful. GenAI traces that store prompts are both a leak and an injection store. |
| D17 | Agree-with-change | Gates and a second model family are necessary. A report card must not mint write credentials. |
| D18 | Disagree | A list of drift kinds is not a control. No detector, interval, owner, or fail-closed response. |
| D19 | Agree-with-change | OIDC and stacks help code drift. They do not cover Entra, portal policy, or Foundry prompt edits. |
| D20 | Agree | Scale-to-zero and hard quotas are the right cost shape. They do not bound purchases. |
| D21 | Agree-with-change | List licences, but P1 is not agent Conditional Access, not PIM, and Defender for AI does not cover these agents. |
| D22 | Agree-with-change | The exclusions are right, except treating a credential as equivalent to an informed OK. |

The §5.2 "reads untrusted text = no" mark on Engineer, Economist, Auditor, and Conductor is false if the case notebook, which quotes tags and logs, is in their prompt. That is the shortest injection path the table pretends is clean.

## (b) Top 7

1. **Credential matched on model-influenced scope.** A tag or log says `env=nonprod` or "this is a dev disk." Surveyor stores that. A human-written credential ("tiering, non-prod, under €X") matches. The runner writes with no fresh OK. **Change:** a credential is a policy evaluated in code against Azure facts the model cannot set (management group, Policy exemption, Entra owner id). Tags, names, and lessons cannot satisfy it. Every run still writes a single-use authorization row. **Confidence:** high. Spec D11, D7, D10; north star §14.3–4.

2. **Approval is a Cosmos row plus a card.** The runner trusts the row. The card can show one summary and post another action value. Email "yes" is not forbidden. Replay, same person in two hats, and time-of-check/time-of-use (etag changed, re-verify "refreshes" and runs) are unspecified. Signing is deferred to P3. **Change:** the Approval service renders the canonical plan; the card carries only an opaque id; Entra object id, auth-context, plan hash, resource etag, and reservation *calculate* quote are bound; single-use; fail closed; two distinct directory roles, not two names. **Confidence:** high on the gap, medium on Teams invoke details (not re-fetched). Spec D11, D13; citadel.md §2.4 (key, not signature, is the caller).

3. **One estate key, seven agents, propose tools.** `plan`, `pr-draft`, and `ledger-propose` sit on the same contract as Detective. Attribution headers are not identity. Citadel requires the subscription key always; JWT is per product and optional. A leaked key or a forged `x-sub-agent-id` is the estate. **Change:** one principal and one tool allow-list per agent, enforced at the hub from `azp`, not from a header. Readers cannot call `plan` or `pr-draft`. **Confidence:** high. Spec D4, §5.5; citadel.md §2.4 and gap 7.

4. **The filters do not cover the paths that matter.** Prompt Shields are specified for `public-read` only. Agent tool-response screening does not apply to MCP. Omitting `rai_config` disables the agent-boundary guardrail. A missing policy fails open. **Change:** deterministic quarantine (untrusted text in a separate field, never beside tool schemas) on tags, logs, docs, and replies; hub `shield-prompt` on estate and people; treat Foundry agent guardrails as preview with a gateway fallback. **Confidence:** high. [Hosted agent guardrails](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-guardrails); [intervention points](https://learn.microsoft.com/azure/foundry/guardrails/intervention-points) (supported tools exclude MCP).

5. **Standing purchase identity.** PIM cannot make a service principal eligible. Amount caps inside the runner are skipped if that identity is used any other way. Azure Reservation Purchaser cannot express a euro cap. **Change:** no standing purchase role. The Approval service creates a time-bound assignment and deletes it; a deny-assignment covers every other path; the quote id and amount are the only purchasable object. **Confidence:** high. [PIM integration](https://learn.microsoft.com/azure/role-based-access-control/pim-integration); spec D12.

6. **Denial of wallet.** Bounds in the workflow do not bound a hosted-agent tool loop. Citadel quotas are per shared key; shipped defaults leave `estimate-prompt-tokens` false, so caps under-count. A purchase is not a token. **Change:** per-agent and per-case hard quotas the Conductor cannot raise; a circuit breaker outside the agents; purchase count and amount alarms that disable the purchase identity. **Confidence:** high on the shape; the Citadel default is from the 2026-10-31 evidence, not re-fetched today.

7. **Tool rug pull and output poisoning.** Pinning name, description, and schema hash does not stop a same-schema behaviour change, a lied `readOnlyHint`, or a log line inside a pinned tool. Azure MCP "read-only mode" was not found; the server acts as its identity, and annotations are hints. **Change:** pin the server digest, not only the schema; hub rejects `tools/list` drift; own tools return structured fields, with a length-capped quoted excerpt that cannot invoke tools. **Confidence:** medium-high. [Azure MCP security](https://learn.microsoft.com/azure/developer/azure-mcp-server/security).

## (c) Three untrusted-text-to-write paths

1. **Log or tag → notebook → Engineer → `plan` / `pr-draft` → runner.** The table says Engineer reads no untrusted text. The notebook is untrusted text. **Cut:** Engineer receives only schema-checked ids and numbers. Action-template pull requests cannot be opened by a session that ingested untrusted text. Template parameters are not model-filled. Purchases bind to the stored quote, not to prose.

2. **Tag or name → Surveyor → credential match, or owner address → send.** Nearest effects are an Azure write under autopilot, or email of the case to an attacker-controlled address. **Cut:** directory object id only, resolved outside the model; refuse model-supplied recipients; tags never classify production or ownership for a credential.

3. **Reply, Teams invoke, or mail → Diplomat / Respond → lesson, approval, or outbound mail.** A "yes" in text, or a card action value swapped under a real SSO token, is a wrong OK or an exfil. **Cut:** free text never approves; lessons cannot widen credentials or scopes; the bot validates the Bot Framework token and may only submit the opaque id to the Approval service.

Scholar/Librarian web text is the same class, one step slower: poisoned claim, human merge, later case. No auto-merge. A claim cannot fill an action parameter.

## (d) What a principal would still expect

Missing: a data-plane RBAC matrix (who writes approvals, credentials, lessons); break-glass that cannot disable the purchase kill switch alone; access reviews; retention versus erasure (no owner data in the immutable log); incident paths for a leaked hub key, a compromised runner, and a poisoned Atlas; SBOM and pinned MCP digests; secret scanning of tool output before it enters a prompt; app-only Graph mail locked to a recipient allow-list; evaluate/prod contract isolation tested, not assumed.

What the stated safeguards do **not** stop: read-only agents do not stop propose tools or the runner; the hub does not stop ARM calls by the runner, a leaked key, or forged headers; Prompt Shields do not stop false negatives, unwrapped text, or MCP tool responses; pinning does not stop a semantic rug pull; the Approval service does not stop its own stolen identity, a mismatched card, or a credential bypass; per-class roles do not stop every action of that class in every opted-in scope; kill switches do not stop an in-flight purchase or exfil; red teaming and a 5% sample do not stop a targeted production injection; deployment stacks do not stop Entra or portal drift; "keyless" does not stop Citadel's mandatory subscription key.

## (e) Reverse D11

Reverse "separation of duties is enough; signing can wait; a credential is as good as an OK." Separation of who may write a row does not make the row a bound, displayed, single-use, fail-closed authorization. Ship that binding in phase 0. Do not earn autopilot by weakening it.

**Verified 2026-11-01:** PIM cannot create eligible assignments for service principals or managed identities. Agent guardrails are preview; no `rai_config` means no agent-boundary filter; a missing policy can fail open. Tool-call and tool-response controls do not apply to MCP. Prompt Shields do not establish provenance; document-attack on tool responses is preview and tool-limited. Agent Conditional Access needs Microsoft 365 E7, or Agent 365 plus Entra P1. Agent ID itself is available to all Entra customers. Defender's agent threat detection is preview and Agent 365-scoped.

**UNVERIFIED today:** Azure MCP "read-only mode"; Prompt Shields' 10,000-character cap; Defender for AI Services token price; Citadel's current key/JWT defaults (used the 2026-10-31 evidence); whether Citadel accepts an Agent ID `azp`; hosted-agent idle timeouts; Bot Framework invoke binding.
