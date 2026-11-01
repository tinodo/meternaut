Model: GitHub Copilot | Files read: `stranger-test-brief.md`, `docs/design/06-security-and-governance.md`, and `docs/design/07-safeguards-and-drift.md`; no other design files were opened.

## 1. Verdict

No. Core claims about the sole writer, purchase permissions, personal data, and automatic drift responses contradict either these documents or current Microsoft Learn guidance.

## 2. Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | `07:35`; cf. `06:22,123` | 4 | “The pipeline redeploys safe classes … from Git.” | This creates a second Azure writer outside the action plane and contradicts both “Green is the only place that changes Azure” and the read-only checker at `07:27`. No approval, credential, identity, or action record is specified. | Replace with: “The read-only check pulls the per-estate switch and opens a remediation request; the action plane applies an allow-listed repair only under a bound approval or credential.” |
| 2 | Blocker | `06:164` | 5 | “A subscription role is enough for a reservation …” | Wrong and dangerously broad. Learn requires built-in **Owner** or **Reservation Purchaser** on an eligible subscription; Reader, Contributor, or a custom imitation is not enough. | Replace “a subscription role” with “the built-in Owner or Reservation Purchaser role on an eligible subscription.” |
| 3 | Blocker | `06:203,205`; cf. `06:57,135` | 4 | “Ids and hashes only … so an erasure never touches an immutable record.” | Entra object IDs are treated as people data earlier and can identify a person through the directory. The later claim that the audit log “holds none” is internally inconsistent and overstates the GDPR conclusion. | Replace with: “The audit log may contain pseudonymous personal identifiers; the adopter must define lawful basis, retention, access, and any applicable erasure restriction before making it immutable.” |
| 4 | Major | `07:38,86` | 4 | “More Action proposals remove the propose tools from the `engineer` contract …” | The same document says trips and checks have no Hub or Foundry write rights. The actor and authorization for this contract mutation do not exist. | Replace with: “A band breach pulls the engineer contract’s switch and pages the platform team; a person changes tool grants through the release process.” |
| 5 | Major | `07:32,154` | 4 | “The Hub rejects a tool whose digest changed …” | The table presents rejection as implemented, while section 7 says P9 must prove or replace it. A stranger cannot tell which safeguard exists now. | Mark the table control `UNVERIFIED (P9)` and state the interim response: suspend the contract and require manual re-pin. |
| 6 | Major | `06:174` | 5 | “The Hub cannot read streamed MCP responses.” | The cited Learn page does not establish this limitation. Because this sentence justifies moving screening out of the Hub, it needs a precise supported limitation, not an assertion. | Replace with a sourced statement naming the exact APIM policy/transport limitation, or label it `UNVERIFIED (P9)` and test it. |
| 7 | Major | `06:102` | 4 | “Five Function apps … one per action family … its own for purchases … the `bot` app’s identity …” | A fixed count is combined with a variable number of action families, plus purchase and bot identities. The principal inventory cannot be reconstructed. | Replace the row with one row per app/identity and remove “Five” unless all five apps are named. |
| 8 | Major | `06:55,69,77`; `07:20,27` | 2 | “Git (Atlas)”; “a flood of Cases”; “single flight”; “Detector” | Core coined nouns appear before definition. `Case`, `Atlas`, `contract`, `Action`, `Detector`, and “single flight” remain unclear; `credential` is defined only much later. | Add a linked glossary before section 1 and define every capitalised artifact at first use. |
| 9 | Major | `07:86,106` | 4 | “A trip pulls a switch …”; “Autopilot credentials pause” | The silent-check trip does not pull any of the three switches defined at `07:47`, contradicting the categorical description of a trip. | Either define an autopilot switch and use it here, or replace `07:86` with: “A trip narrows state by pulling a switch or pausing credentials.” |
| 10 | Major | `07:31` | 3 | “the Models API for retirement dates” | No product, endpoint, API version, response field, permission, or failure behavior is named. The central retirement check is not implementable from this text. | Name and link the exact API and fields, or replace this mechanism with a documented source and a fail-closed behavior when it is unavailable. |
| 11 | Major | `06:10` | 6 | “An agent can be talked into anything, so no agent can do harm.” | This is an absolute slogan, not a defensible security property; later sections admit wrong drafts, proposals, and messages remain possible. | Replace with: “Assume every agent can be compromised; agents cannot write Azure directly, and the action plane accepts only typed, authorised records.” |
| 12 | Major | `06:190`; `07:43` | 5 | “a missing policy fails open” | Current Learn confirms that omitting `rai_config` means no boundary guardrail, but it does not support this broader deleted-or-unresolvable-policy claim. | State only the documented omission behavior, and add a test result before claiming how a missing named policy behaves. |
| 13 | Minor | `07:27` | 1 | “A drift check is not a Detector” | “Detector” has not been introduced; the denial reads like an answer to an earlier review. | Replace with: “A drift check compares declared state with actual state.” |
| 14 | Minor | `06:58` | 2 | “one repository key” | The repository and purpose are never named, and the key is never mentioned again. | Name the repository integration and why it needs a key, or delete this example. |
| 15 | Minor | `07:134` | 3 | “for R2 and R3 the Verifier asks” | It never says whom it asks, what decision is offered, or how an irreversible R3 outcome is handled. | Replace with the named recipient, available decisions, timeout, and resulting state transition. |

## 3. Sentences I would delete

- `06:10` — “An agent can be talked into anything, so no agent can do harm.”
- `06:174` — “The Hub cannot read streamed MCP responses.”
- `07:27` — “A drift check is not a Detector; it compares declared with actual.”
- `07:43` — “A missing guardrail policy fails open.”
- `07:86` — “A trip pulls a switch and does little else.”

## 4. Fact checks

1. **Reservation purchase role (`06:164`) — wrong.** [Learn](https://learn.microsoft.com/azure/cost-management-billing/reservations/prepare-buy-reservation) requires built-in Owner or Reservation Purchaser on an eligible subscription and explicitly rejects custom imitations.
2. **Hosted-agent guardrails (`06:190`, `07:43`) — partly confirmed.** [Overview](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-guardrails) confirms preview status and that omitted `rai_config` means no boundary guardrail. [Supported tools](https://learn.microsoft.com/azure/foundry/guardrails/intervention-points#supported-tools) omits MCP. Neither page supports the broader “missing policy fails open” claim.
3. **APIM cannot read streamed MCP responses (`06:174`) — unsupported by the cited page.** [Learn](https://learn.microsoft.com/azure/api-management/mcp-server-overview) says policies apply to all exposed tool operations and monitoring can capture requests and responses; it does not document the claimed inspection limitation.
4. **Deployment Stacks (`07:43`) — confirmed.** [Learn](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deployment-stacks-known-issues) says what-if is unavailable and moving a managed resource removes stack protection.
5. **Managed-identity token cache (`07:95`) — confirmed with narrower scope.** [Learn](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations) says backend services cache tokens per resource URI for around 24 hours and group/role-claim changes can take several hours.

## 5. Questions left unanswered

1. Which named component and identity writes automatic trips and switch changes, and how is it prevented from widening state?
2. Is infrastructure drift ever remediated outside the action plane, or is `07:35` an error?
3. What are the authoritative definitions and schemas for Case, Action, Atlas, contract, Detector, and report card?
4. Which exact API and fields prove deployed model version and retirement date, and what happens when that source is unavailable?
5. What is the measured worst-case time from pulling a switch to “Stopped,” including in-flight Azure calls and cached identity tokens?
