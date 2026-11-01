# Round 2 · Lens E — Platform fact-check

Design phase 1 of "Azure Cost in Action" · reviewed commit `7baddcf` · 31 October 2026 · reviewer model claude-sonnet-5.5 (Round-1 lens E: gpt-5.6-sol).

Assumptions: "today" is 31 Oct 2026 and every vendor page was read that day (Learn search/fetch, Azure Release Communications API, Retail Prices API in EUR, the AVM module index, raw GitHub). Where Learn, a release record and a blog disagree I say so and take the more restrictive reading. `UNVERIFIED` = not confirmed on a primary page. Round-2 numbering restarts at E-01; Round-1 ids are written "R1 E-nn". The only file written is this one. `python tools\check-docs.py --strict` passes (54 documents, 0 errors).

## 1. Verdict (five lines)

1. **Sound.** About 70 platform statements were re-checked today and nearly all hold; all 13 R1 lens-E changes landed and are right (§2). No Critical.
2. **The one thing that must change:** the preview register (09 §5) is incomplete — orchestration versioning, capability settings, MCSB v2 and the long-running/cancel behaviour behind the leaf call are preview or undocumented, yet carry load outside it (E-02…E-05), so "nothing depends on preview" is not yet true.
3. **A wrong fact:** `auth_time` and `amr` *are* documented Entra optional claims; 07 says they are not, while 06 already stores them (E-01).
4. **Security-relevant:** *Key Vault Crypto User* includes `keys/update/action`, so a signer can re-enable the key the kill switch disabled (E-06); ADR-05's "cannot be switched off" premise is conditional (E-07).
5. **Numbers:** 17 euro figures re-derived from the Retail Prices API; all match except two regional mix-ups (E-13). ADRs: 27 Agree, 10 Agree with changes, 0 Disagree.

**Counts: Critical 0 · Major 7 · Minor 12.**

## 2. Disposition audit (R1 lens E)

Every claimed change is present in the file the disposition names and is correct today. None is absent or contradicted, so no Critical.

| R1 | Landed where | Right today? |
|---|---|---|
| E-01 Routines | `02` §4 ("What the first review round changed in the landscape"), ADR-34 title "Routines are optional and preview" | Yes. Release record 563536 "Public Preview: Foundry Routines in Foundry Agent Service" (In preview) still conflicts with Learn's GA table; fail-closed is right |
| E-02 Python card actions | ADR-17 (adapter stays C# for typing) | Yes |
| E-03 APIM per-tool | `04` §4.4 Fallback ("one MCP server per trust class") | Yes — Learn: policies apply to all tools |
| E-04 `llm-content-safety` | `02` H8, `07` layers | Yes — GA record 562880 (2026-06); sliding window; no 403 on streams |
| E-05 portal gateway | `04` B9, S-NET-1 | Yes — existing APIM must be v2, same tenant and subscription |
| E-06 `useTargetAzureKeyVault` | `04` §3.4 (set explicitly `true`) | Yes, and the "to confirm" can close: at pinned `81599b3` the Bicep default is `= true`, the sample `main.bicepparam` sets `= false` |
| E-07 five containers, two projects | `04` §7, `11` §2 | Yes — 5 × 1,000 RU/s, serverless supported |
| E-08 Groundedness | `02` §3/§4, `09` §5 | Yes — *detection* retires 30 Apr 2027; evaluator separate |
| E-09 DZ premium | ADR-09, ADR-25 | Yes — API ratio DZ/Global 1.200 (GPT-6), 1.100 (GPT-5.6) |
| E-10 EU Search regions | `04` §3.2 | Yes — Denmark East, Poland Central, Sweden Central; "high demand" flag quoted correctly |
| E-11 stack move bypass | `11` §2, `02` §4, `09` DR-1 | Yes (Learn known issues) |
| E-12 Claude hosting versions | `05` §6, `04` §4.2, `02` §4, ADR-10 | Yes |
| E-13 hosted agents GA | `05` §5, `09` §5 | Yes — record 563596, GA 2026-06 |
| E-14, E-17, E-19, E-20 ("correct") | `09` §5 consolidated hosted-agent row and retirement dates; `05` §5/`09` §5 package statuses; Citadel `81599b3` | Yes; `81599b3` is still head of `main` |
| E-15 PIM | `07` §3.3 | Yes |
| E-16 meter ids and effective dates instead of price prose | **not done** | prices remain prose (E-19) |
| E-18 EU AI Act dates | outside Microsoft-product scope | UNVERIFIED by me |

The disposition has no row for the "correct" items E-14 and E-16–E-20; only E-16's suggestion is still open. R1's five "what is missing" items are not addressed (see §7).

## 3. Findings

### Major

**E-01 · Major · Step-up: `auth_time` and `amr` are documented claims.**
File: `<repo>\docs\design\07-security-architecture.md` — "3.4 Conditional Access and the licence line"; also §4 "Signed" row, `<repo>\docs\design\06-data-and-knowledge.md` — "The records that matter most", `<repo>\docs\design\13-decisions.md` — "ADR-08".
- **Quote** (`07-security-architecture.md`): "`max_age` and `auth_time` are not documented for the Microsoft identity platform, so nothing depends on them (*to confirm*)."
- **Quote** (`06-data-and-knowledge.md`): "the Entra identity claims (`oid`, `tid`, `amr`, `auth_time`)"
- **Quote** (`07-security-architecture.md`): "the sign-in time (the token's `iat`; an `auth_time` claim is *to confirm*)"
- **Quote** (`07-security-architecture.md`): "an optional claim to request in the app registration"

Why: 07 says nothing depends on `auth_time`, 06 stores it in the signed record, and 07 §4 lists it as *to confirm*: a contradiction. Learn documents `auth_time` and `amr` (with OIDC values) as optional claims. The cited anchor `optional-claims#amr-claim` covers SAML (`include_granular_amr`); the ID-token claims reference has no `amr`, so it must be requested and tested. Only `max_age` stays undocumented (UNVERIFIED either way).
Fix (paste-ready, end of §3.4): "`auth_time` and `amr` are documented optional claims ([reference](https://learn.microsoft.com/entra/identity-platform/optional-claims-reference)); the app registration requests both. A purchase approval is accepted only if `auth_time` is later than the approval's creation, `amr` contains `mfa`, the `nonce` matches and `iat` agrees; `max_age` is not used. S-ID-3 asserts both claims arrive for a Teams single sign-on and for a web sign-in." Also: point the `amr` anchor at `optional-claims-reference`; in §4 write "the sign-in time (`auth_time`, cross-checked with `iat`)"; delete "(*to confirm*)" in ADR-08.
Source: https://learn.microsoft.com/entra/identity-platform/optional-claims-reference — "Time when the user last authenticated." and "Identifies how the subject of the token was authenticated". `prompt=login`: https://learn.microsoft.com/entra/identity-platform/v2-protocols-oidc — "forces the user to enter their credentials on that request, which negates single sign-on".

**E-02 · Major · Capability hosts versus "capability settings" (preview API).**
File: `<repo>\docs\design\04-landing-zone-and-citadel.md` — "7. The Foundry layout".
- **Quote** (`04-landing-zone-and-citadel.md`): "capability hosts (REST/ARM only; no in-place update)"
- **Quote** (`04-landing-zone-and-citadel.md`): "with account- and project-level *capability hosts* as code"

Why: Learn's virtual-networks page now describes *capability settings* provisioned through ARM/Bicep API `2026-07-15-preview`, with caller roles on every BYO account. The release pipeline (07 §3.1) holds neither role, the preview register omits the API, and S-NET-3 does not test it. The repo's own research flagged the semantics `UNVERIFIED` (`research\foundry-governance-and-framework.md`) and recorded the roles (`research\citadel.md`), but neither reached the design. Whether settings supersede hosts for new accounts is UNVERIFIED.
Fix: add to 09 §5: "Capability settings (ARM/Bicep API `2026-07-15-preview`) — preview — fallback: the legacy capability host through the portal/REST — leave when GA and shown in S-NET-3". In 07 §3.1 give the `foundation` pipeline identity *Storage Blob Data Contributor* and *Cosmos DB Operator* on each BYO account for that step only. Reword 04 §7: "capability settings (preview API) or the legacy capability host (no in-place update); S-NET-3 decides which and tests the caller-role failure".
Source: https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks — "A caller that can create the Foundry account but lacks Storage Blob Data Contributor or Cosmos DB Operator fails capability settings provisioning".

**E-03 · Major · MCSB v2 is labelled preview, the design lists it as GA.**
File: `<repo>\docs\design\02-technology-landscape.md` — "3. The technology map"; `<repo>\docs\design\13-decisions.md` — "ADR-29".
- **Quote** (`02-technology-landscape.md`): "Policy approved models; MCSB v2; NSP for Foundry; model guardrails; Defender for Resource Manager and Key Vault"
- **Quote** (`13-decisions.md`): "The Microsoft cloud security benchmark v2 AI domain and Azure Policy are the spine"

Why: the Security row sits in the GA column and ADR-29 makes v2 the spine of compliance. The AI-1…AI-7 names in 08 are correct, but the benchmark itself is preview, which breaks the rule that preview needs a switch and a fallback.
Fix: move "MCSB v2" to the Preview column; add to 09 §5: "MCSB v2 AI security domain — preview — the repository's control map (each AI-n → control and evidence) stays authoritative; map to MCSB v1 control ids where v2 changes — leave when v2 is GA". Amend ADR-29: "…v2 (preview) AI domain, with the control map as the fallback".
Source: https://learn.microsoft.com/security/benchmark/azure/introduction — "The Microsoft cloud security benchmark v2 (preview) is now available."

**E-04 · Major · Orchestration versioning is preview on the release record and absent from the register.**
File: `<repo>\docs\design\05-agents-and-orchestration.md` — "4. How the spine runs" (Versioning row); `<repo>\docs\design\09-safeguards-and-drift-controls.md` — "5. The preview register and the dependency register"; RB-15 in `11-delivery-and-operations.md` §7.5.
- **Quote** (`05-agents-and-orchestration.md`): "**orchestration versioning** (worker extension 1.14.0 or later; any provider)"
- **Quote** (`09-safeguards-and-drift-controls.md`): "orchestration versioning for in-flight work (RB-15,"

Why: the spine's upgrade path, the version-drain drill and RB-15 all rest on it. Release record 498144 is "Public Preview", status In preview, and I found no later GA record; Learn's page carries no label. The register lists Flex rolling updates but not this.
Fix: add to 09 §5: "Durable orchestration versioning — preview per release record 498144; Learn unlabelled, so treated as preview — fallback: a new orchestrator function name per breaking change, old name drained, `Recreate` only at zero in-flight — leave when a GA record exists". S-ORCH-1 already runs the drill; add "and the fallback".
Source: Azure Release Communications id 498144 (`https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=id eq '498144'`) — "Public Preview: Orchestration versioning for Durable Functions and durable task SDKs".

**E-05 · Major · The leaf call ("returns at once") and the 2-minute idle timeout are untested against the documented idle rule.**
File: `<repo>\docs\design\05-agents-and-orchestration.md` — "4. How the spine runs" (Calling a leaf) and "5. Anatomy of a leaf" (Runtime); `09` §5.
- **Quote** (`05-agents-and-orchestration.md`): "it returns **at once with a run id**, and the protocol also offers `GET` for status and `cancel` for a cooperative abort"
- **Quote** (`05-agents-and-orchestration.md`): "idle timeout **2 minutes** for batch-style roles, 15 for the Diplomat"
- **Quote** (`09-safeguards-and-drift-controls.md`): "the long-running APIs stay off, because the spine owns long-running work"

Why: Learn defines idle by requests, not by work: the platform deprovisions when "no request arrives within that window". A leaf that returns a run id and keeps reasoning (the cost model seeds a Detective at about 12 active minutes) has no open request after the first response. The Invocations adapter prescribes no status or polling contract; `GET` and `cancel` are optional handlers (404 until registered); the platform's own path for background work is the resilient-task API, which is preview and which the register switches off. Nothing in S-NET-1, S-COST-1 or S-HOST-1 tests that background work survives a 2-minute idle timeout.
Fix (05 §4): "The activity holds the `POST /invocations` request open (server-sent events with keep-alive) until the leaf has written its result to the case store, so the idle timer, which counts requests, cannot fire mid-run. `GET /invocations/{id}` and `cancel` are optional handlers and are not relied on; the resilient-task APIs stay off. A leaf that must outlive one request gets an idle timeout of at least its p99 active time, priced as billed." Add to S-COST-1: "a leaf that returns at once and works ten minutes with no further request, under a 2-minute idle timeout: does it finish, and what is billed?" Check the hub's backend timeout for a held request (UNVERIFIED).
Source: https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents — "If no request arrives within that window, the platform deprovisions the compute and persists the session state". https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-contract — "The Invocations adapter doesn't prescribe a status or polling contract". https://learn.microsoft.com/azure/foundry/agents/how-to/cancel-hosted-agent-turn — "Without a registered handler, calling it returns `404 not_found`." and "Long-running agents are in preview. APIs and package versions can change."

**E-06 · Major · *Key Vault Crypto User* is not least privilege for a signer.**
File: `<repo>\docs\design\07-security-architecture.md` — "3.1 Who has an identity" and "10.3 Kill switches"; also `04` §6, `11` §6, `09` DR-19 (§2.1).
- **Quote** (`07-security-architecture.md`): "*Key Vault Crypto User* on the approval-signing key's own vault"
- **Quote** (`09-safeguards-and-drift-controls.md`): "Crypto User on each signing key for its own service only"
- **Quote** (`07-security-architecture.md`): "disable the key and add its id to the verifiers' deny list"

Why: the built-in role's data actions include `Microsoft.KeyVault/vaults/keys/update/action` ("Updates the specified attributes associated with the given key."), so a compromised Approval service can re-enable a key the kill switch disabled, or change its operations. The verifiers' deny list stays the real stop, which limits the harm, but the authority chain's stated principle is least privilege.
Fix: replace the role in 07 §3.1/§6.1, 04 §6, 11 §6 and DR-19 with a custom data-plane role `acia-signer` holding only `Microsoft.KeyVault/vaults/keys/read` and `Microsoft.KeyVault/vaults/keys/sign/action`, assigned at the party's own vault; add a drift detector "no signing identity holds `keys/update/action`".
Source: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/security — role *Key Vault Crypto User*, data action `Microsoft.KeyVault/vaults/keys/update/action`.

**E-07 · Major · ADR-05's cost premise is conditional.**
File: `<repo>\docs\design\13-decisions.md` — "ADR-05 Bring-your-own-VNet injection, not the managed VNet"; `<repo>\docs\design\04-landing-zone-and-citadel.md` — "3.2 Region".
- **Quote** (`13-decisions.md`): "The managed VNet's FQDN rules create a managed Azure Firewall"
- **Quote** (`13-decisions.md`): "has no outbound logging and no custom firewall, and cannot be switched off"
- **Quote** (`04-landing-zone-and-citadel.md`): "| Foundry managed VNet | no | no | yes |"

Why: Learn says the managed firewall is created only when an outbound FQDN rule is added; with service-tag and private-endpoint rules only there is none. The €803 a month therefore applies only if FQDN rules are needed, and "cannot be switched off" is wrong as written. The decision still holds (no outbound logging, no custom firewall). The same Learn page contradicts itself on regions (an explicit list without West Europe; also "supported in all regions that the Foundry Agent service with custom virtual network is supported in"), so "no" for West Europe rests on one reading.
Fix (ADR-05 *Because*): "The managed VNet creates its Azure Firewall only when an outbound FQDN rule is added — Standard by default, Basic selectable and then fixed — which bills about €803 a month plus €0.014 a GB for Standard in Sweden Central; with no FQDN rule agents reach only service tags and private endpoints. It has no outbound logging and no custom firewall." In 04 §3.2 note: "West Europe: no on Learn's explicit list; the same page also says all regions that support BYO-VNet — S-NET-2 pins it."
Source: https://learn.microsoft.com/azure/foundry/how-to/managed-virtual-network — "The firewall isn't created until you add an outbound FQDN rule"; "No logging of outbound traffic support yet"; "Managed virtual network is supported in all regions that the Foundry Agent service with custom virtual network is supported in".

### Minor

**E-08 · Minor · Durable Task Scheduler Consumption SKU is GA.** `<repo>\docs\design\05-agents-and-orchestration.md` — "4. How the spine runs" (provider row); `<repo>\docs\design\14-next-phases.md` — "3. Spike register" (S-ORCH-1).
- **Quote** (`05-agents-and-orchestration.md`): "labelled *preview* on one Learn page only"
- **Quote** (`14-next-phases.md`): "its Consumption SKU counts as preview"

Why: record 560957 is GA 2026-04 (record 525518, Nov 2025, had it in preview); only Learn's billing page is stale; `research\features-08.md` already held the record. Fix: "Consumption SKU — generally available since April 2026 (release record 560957); Learn's Durable Functions billing page still says preview". Source: Release Communications 560957 — "Generally Available: Azure Functions durable task scheduler Consumption SKU"; https://learn.microsoft.com/azure/durable-task/durable-functions/durable-functions-billing — "Consumption (preview)".

**E-09 · Minor · The AVM Bot Service module is only Proposed.** `<repo>\docs\design\11-delivery-and-operations.md` — "2. Infrastructure as code".
- **Quote** (`11-delivery-and-operations.md`): "The modules exist for almost everything we use: Container Apps environments and jobs, Cosmos DB, AI Search, API Management, Key Vault, Log Analytics, the registry, Bot Service, and a Foundry account and project pattern."

Why: the index lists `avm/res/bot-service/bot-service` and `avm/res/durable-task/scheduler` as Proposed (no published module); the others named are Available, and `avm/ptn/ai-ml/ai-foundry` is Available. Fix: delete "Bot Service," and add "There is no published module yet for Bot Service or the Durable Task Scheduler (both Proposed); they are plain Bicep resources behind a thin local module." Source: https://raw.githubusercontent.com/Azure/Azure-Verified-Modules/main/docs/static/module-indexes/BicepResourceModules.csv — "Microsoft.BotService,botServices,Bot Service,,avm/res/bot-service/bot-service,n/a,Proposed".

**E-10 · Minor · Geo-zone redundancy "not a path we can read" is over-general.** `<repo>\docs\design\06-data-and-knowledge.md` — "7.6 Recovery"; `<repo>\docs\design\11-delivery-and-operations.md` — "8. Resilience and recovery".
- **Quote** (`06-data-and-knowledge.md`): "WORM and geo-zone redundancy, which protect the data but are not a path we can read from during a regional loss"
- **Quote** (`11-delivery-and-operations.md`): "geo-zone-redundant and immutable, which is not a path we can read from during a regional loss"

Why: the secondary is unreadable "unless there's a failover" for GRS/GZRS, but RA-GZRS reads it, and immutable storage is compatible with customer-managed unplanned failover. The hourly copy to the second-region lake stays right. Fix: "…not a path we can read during a regional loss unless the account is RA-GZRS or fails over (customer-managed unplanned failover, which may lose writes since the last sync); we do not rely on either". Source: https://learn.microsoft.com/azure/storage/common/storage-redundancy — "unless there's a failover"; https://learn.microsoft.com/azure/storage/blobs/immutable-storage-overview — "compatible with customer-managed unplanned failover".

**E-11 · Minor · Network security perimeters do not cover everything named.** `<repo>\docs\design\07-security-architecture.md` — "7. Network and the short list of exceptions" (rule 3).
- **Quote** (`07-security-architecture.md`): "protect Storage, Key Vault, AI Search and Foundry from exfiltration"

Why: Learn's onboarded-resource table gives Storage, Key Vault and Foundry GA in both directions; AI Search is GA for inbound only, outbound not available; Cosmos DB is public preview. Fix: "…protect Storage, Key Vault and Foundry from exfiltration (GA both ways); Azure AI Search is inbound-only, so its outbound path (indexers, skills) stays on private endpoints and shared private links". Source: https://learn.microsoft.com/azure/private-link/network-security-perimeter-concepts — row "Azure AI Search Microsoft.Search/searchServices Generally Available Not Available".

**E-12 · Minor · A vendor quotation is not verbatim.** `<repo>\docs\design\07-security-architecture.md` — "5. Defence against prompt injection in nine layers" (layer 7); same string in `04` §6, `09` §5, `02` H8.
- **Quote** (`07-security-architecture.md`): "not intended for production use"
- **Quote** (`09-safeguards-and-drift-controls.md`): "not intended for production use"

Why: Learn's sentence is longer; the wording matters because the design builds the audit-only rule on it. Fix: replace with "are not intended to be used in production or in a live operating environment" (or drop the quotation marks). Source: https://learn.microsoft.com/azure/foundry/agents/how-to/add-hosted-agent-guardrails — "Preview features are provided without a service-level agreement and are not intended to be used in production or in a live operating environment."

**E-13 · Minor · Regional price mix-ups.** `<repo>\docs\design\04-landing-zone-and-citadel.md` — "3.2 Region" and "3.3 The hub and its cost"; `<repo>\docs\design\05-agents-and-orchestration.md` — "12. What is deliberately not used"; also `11` §7.4 and ADR-27.
- **Quote** (`04-landing-zone-and-citadel.md`): "| API Management Standard v2 price | cheaper (≈ 30 %) | — | dearer |"
- **Quote** (`04-landing-zone-and-citadel.md`): "Developer for dev and lab (a saving of ≈ €574 a month against Standard v2)"
- **Quote** (`05-agents-and-orchestration.md`): "a fixed cost of roughly €280–350 a month in Sweden Central"

Why (Retail Prices API, 2026-10-31): Standard v2 unit hour is €1.099965 in Sweden Central (€803 a month) and €0.843805 in West and North Europe (€616), so West Europe is ≈ 23 % cheaper (Sweden Central ≈ 30 % dearer). The "€574" saving is the West Europe figure (€761 in Sweden Central). SRE Agent at 4 units is €283 in Sweden Central (€0.096797 per unit-hour) and €349 in West Europe (€0.119676): the range spans two regions. Fix: "cheaper (≈ 23 %)"; "a saving of ≈ €761 a month in Sweden Central (≈ €574 in West Europe)"; "about €283 a month in Sweden Central (€349 in West Europe)".

**E-14 · Minor · Cost Management exports versus "public network access off" (UNVERIFIED combination).** `<repo>\docs\design\06-data-and-knowledge.md` — "7.1 The stores"; `<repo>\docs\design\07-security-architecture.md` — "7. Network and the short list of exceptions" (rule 1).
- **Quote** (`06-data-and-knowledge.md`): "Cost Management exports write Parquet to firewalled storage"
- **Quote** (`07-security-architecture.md`): "Every PaaS resource we own has public network access **off** and a private endpoint; Azure Policy denies the opposite."

Why: Learn's documented export path is a storage firewall with *Allow trusted Azure services access*; that firewall governs the public endpoint. Learn documents that previously configured exceptions remain in effect when public access is later set to Disabled, but not that a fresh Disabled account accepts export writes. Fix: add to S-NET-2 or the onboarding acceptance test: "a Cost Management export lands in the cost lake with public access 'selected networks' plus the trusted-services exception, and, separately, with Disabled; the Policy exemption is recorded if only the former works". Source: https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports — "Enable Allow trusted Azure services access on the storage account."; https://learn.microsoft.com/azure/storage/common/storage-network-security-limitations — "By design, access to a storage account from trusted services takes the highest precedence over other network access restrictions."

**E-15 · Minor · A vended Lab subscription cannot have a budget at once.** `<repo>\docs\design\07-security-architecture.md` — "2. Trust zones, physically" and "12. Threats, controls and what remains" (T4).
- **Quote** (`07-security-architecture.md`): "it has its own budget, policy and expiry, and no network route to anything in Z4"
- **Quote** (`07-security-architecture.md`): "Lab budgets that stop"

Why: Learn: a new subscription cannot immediately create a budget or use other Cost Management features. Fix: "the budget is created by the Lab controller on its first successful call (retried for up to 48 hours); until then the structural cap (policy, SKUs, quotas) is the control, and no experiment starts before the budget exists". Source: https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets — "It might take up to 48 hours before you can use all Cost Management features."

**E-16 · Minor · Layer 6 is labelled GA, the capability is not.** `<repo>\docs\design\07-security-architecture.md` — "5. Defence against prompt injection in nine layers" (layer 6); `<repo>\docs\design\02-technology-landscape.md` — "3. The technology map".
- **Quote** (`07-security-architecture.md`): "so tools of different trust classes sit on separate servers | GA | n/a |"
- **Quote** (`02-technology-landscape.md`): "per-tool authorisation by `azp` and app roles (S-GW-3)"

Why: 02 files per-tool authorisation under *Evaluated*, the Publish contract is preview, and Learn documents no per-tool allow-list. Fix: layer 6 status "Evaluated (S-GW-3); separate servers per trust class is the GA fallback". The 18 Jun 2026 Tech Community post on a tools/list-plus-tools/call filter is a custom-policy pattern, not a platform feature: cite it as S-GW-3's candidate.

**E-17 · Minor · The approved-models policy matches asset ids by prefix.** `<repo>\docs\design\08-governance-and-compliance.md` — "3. Security regulation and benchmarks" (AI-1 row); `09` DR-8.
- **Quote** (`08-governance-and-compliance.md`): "| **AI-1** approved models | Azure Policy approved models; alias map; the exam on every change |"

Why: an id without a trailing slash also approves other models whose names begin with the same characters, which could approve GPT-6 Astra ("never a default") through a `gpt-6` prefix. Fix: add to the AI-1 row "asset ids end with `/` (prefix match), asserted by the exam". Source: https://learn.microsoft.com/azure/foundry/how-to/model-deployment-policy — "Each asset ID is matched as a prefix."

**E-18 · Minor · Count disagreement after the edit.** `<repo>\docs\design\03-logical-architecture.md` — "2. The building blocks" (diagram, line 43).
- **Quote** (`03-logical-architecture.md`): "Agent society<br/>13 roles · 14 identities"
- **Quote** (`07-security-architecture.md`): "fifteen identities for fourteen roles, in eleven contract groups"

Fix: "14 roles · 15 identities". This is the only count disagreement I found (fourteen roles, fifteen identities, eleven groups, two projects agree everywhere else).

**E-19 · Minor · R1 E-16 is still open: prices are prose.** `<repo>\docs\design\13-decisions.md` — "ADR-05"; `09` §5.
- **Quote** (`13-decisions.md`): "€803 a month for the Standard deployment hour plus €0.014 a GB"

Why: E-13 shows what prose invites (the wrong region's figure). Fix: price lines in 04, 09 §5, 12 and the ADRs carry a snapshot key (region, meter, effective date) from `docs\design\cost\prices-snapshot.json`, e.g. "€803 (swedencentral, Azure Firewall Standard Deployment, retrieved 2026-10-31)".

## 4. Price spot-check (Retail Prices API, EUR, 2026-10-31)

| Claim | API | Match |
|---|---|---|
| Azure Firewall Standard, 12 §4/ADR-05 €803 + €0.014/GB (Premium €1,124) | €1.099965/h → €802.97; €0.01408/GB; Premium €1.539951/h | ✓ |
| APIM Standard v2, Sweden Central €803 | €1.099965/h (West Europe €0.843805) | ✓; ≈ 30 % table wrong (E-13) |
| APIM Developer | €0.057902/h → €42.3 | ✓ |
| AI Search Basic, Sweden Central ≈ €65 | €0.088877/h → €64.9 | ✓ |
| Semantic ranker | €0.879972 per 1K | ✓ |
| Container Registry Premium | €1.466561/day → €44.6 | ✓ |
| Flex always-ready baseline, 2 GB | €0.000004/GB-s → €21.0 | ✓ |
| Private endpoint | €0.0088/h → €6.42 | ✓ |
| Durable Task Scheduler Dedicated CU | €0.783537/h → €572 | ✓ |
| Defender for AI Services, 100 M tokens (€70.40) | €0.000704 per 1K | ✓ |
| Defender for Resource Manager "about €5 a subscription" | €0.006072/h → €4.43 (+ €0.22 per vault) | ✓ rounded |
| ADR-20 "≈ €30 a month" default Defender | not derivable without the subscription count | UNVERIFIED |
| SRE Agent "€280–350 in Sweden Central" | €283 (SC), €349 (WE) | ✗ range (E-13) |
| Hosted agents, Sweden Central | €0.096216/vCPU-h, €0.011422/GiB-h; no West/North Europe meter | ✓ |
| DZ over Global | GPT-6.1-sol input €2.111932 vs €1.759944 per M = 1.200; GPT-5.6 = 1.100 | ✓ |
| Managed HSM "about €2,000 a month" (ADR-24) | Key Vault HSM Pool Standard B1 €2.81591/h → €2,056 | ✓ |
| Dynamic sessions | €0.026399/h; no Container Apps Sandboxes meter | ✓ ("price unverified") |
| Regional premium "+30–50 %" (ADR-09/25) | no regional GPT-5/6 meter in swedencentral/westeurope; Tech Community post table: Sweden +30 %, EU West/North +50 % | ✓ against the post; UNVERIFIED in the API |

## 5. Decision table (all 37 ADRs in `<repo>\docs\design\13-decisions.md`)

| ADR | Verdict | Conf. | Strongest alternative | What would change my mind |
|---|---|---|---|---|
| 01 Spine calls leaves | Agree | High | Foundry-hosted workflows | S-ORCH-1 fails, or the E-05 test shows a leaf call cannot be held |
| 02 Citadel hub on APIM | Agree | High | AI Gateway product (preview) | AI Gateway GA with load balancing, A2A, caching |
| 03 Two spokes, Lab MG | Agree | High | One spoke | An estate owner refuses read onboarding |
| 04 Sweden Central | Agree with changes | Med | West Europe (≈ 23 % cheaper APIM) | S-NET-3 refuses Search in Sweden Central; fix E-13 |
| 05 BYO-VNet | Agree with changes | Med | Managed VNet, no FQDN rules | Learn adds outbound logging and settles its region contradiction (E-07) |
| 06 Agent identity per agent | Agree | High | One identity per group | S-ID-2: agent token fails at the hub |
| 07 JIT execution identity | Agree | High | PIM eligibility (not possible for apps) | Learn allows eligible assignments for service principals |
| 08 Approvals | Agree with changes | Med | Authentication context (needs P1) | E-01 closed; P1 licensed |
| 09 Aliases and data class | Agree | High | Everything Global (≈ 16 % cheaper) | EU premium shrinks |
| 10 Judges and Claude | Agree | High | Same family | Anthropic offers EU Data Zone hosting |
| 11 Atlas is Git | Agree | High | AI Search as master | Atlas outgrows Git |
| 12 Cosmos serverless | Agree | High | PostgreSQL | Change feed without deletes blocks a use |
| 13 Parquet and embedded engine | Agree with changes | Med | ADX/Fabric | Exports cannot land with public access off (E-14) |
| 14 No platform memory | Agree | High | Foundry Memory (preview) | Memory GA in Sweden Central with EU residency |
| 15 MCP through the hub | Agree | Med | Per-tool allow-list policy | S-GW-3 proves it (E-16) |
| 16 Lab vended | Agree with changes | Med | Manual subscriptions | E-15 fixed |
| 17 Teams adapter | Agree | High | Python adapter | Python typing gap closes |
| 18 OpenTelemetry, table plans | Agree | High | Application Insights only | Protected-table path GA |
| 19 Nine layers | Agree | Med | Fewer layers | S-SEC-2: first-1,000-character limit bites |
| 20 Security monitoring | Agree with changes | Med | Defender everywhere | State the €30 derivation; MCSB v2 (E-03, E-11) |
| 21 Drift and register | Agree with changes | High | Manual review | Register completed (E-02…E-05, E-08) |
| 22 Evaluation | Agree | High | Foundry only | Red-teaming EU regions settled |
| 23 Bicep, AVM, stacks | Agree with changes | Med | Terraform | E-02, E-09 fixed |
| 24 Keyless | Agree | High | CMK/Managed HSM (€2,056) | A compliance driver names CMK |
| 25 EU Data Zone | Agree | High | Regional only (+30/+50 %) | Policy allows Global for a class |
| 26 Hub is the cap | Agree | Med | PTU or quotas | S-COST-1 shows a large overshoot |
| 27 SRE Agent off | Agree | High | Always-on operator | Trial shows value above €283 |
| 28 Monorepo, azd | Agree | Med | Multi-repo | azd extension pins unstable (beta; UNVERIFIED) |
| 29 Benchmark and policy | Agree with changes | High | Compliance Manager templates | E-03 closed |
| 30 Redeploy recovery | Agree | High | Second region now | An RTO below redeploy time |
| 31 Signed manifest | Agree | High | Lockfiles only | — |
| 32 Ledger | Agree | High | Immutable table | 50,000-block limit hit; E-10 wording |
| 33 DF on Flex | Agree with changes | Med | Own checkpoint spine; DTS | E-04/E-05 tests fail; DTS Consumption GA (E-08) |
| 34 Clocks, Routines | Agree | High | Routines as default | Routines GA on the release record |
| 35 Minimal hub | Agree | Med | Require a hub | Developer tier SLA needed |
| 36 C# and Python | Agree | High | One language | Hosted-agent C# parity |
| 37 Sandbox | Agree | Med | Run in the agent microVM | Sandboxes EU regions and price verified (S-SBX-1) |

## 6. What is strong

- Fail-closed treatment where sources disagree (Routines, rolling updates, DTS), each with a fallback and a spike.
- Conflicts between Learn pages are named, not smoothed over (BYO-resource regions, red-teaming regions).
- The hosted-agent, Flex and Durable limits are correct to the detail: always-ready `durable` group, 10-second polling, client-id identity, six-day timers, 90/30-day retention.
- WORM facts (`allowProtectedAppendWrites` before locking, 50,000 blocks, `409`), the delegation condition (no scope attribute), the 10-minute RBAC propagation and Cosmos container scoping are all right.
- The cost model is reproducible (`--check` passes) and its prices match the API; one MCP server per trust class is the right fallback.

## 7. What is missing (five omissions)

1. **A platform-status manifest** that reconciles release record, Learn and blog per dependency, re-run by script (E-03, E-04, E-08).
2. **A per-account service-limit and capability model** (capability settings and caller roles, hosted-agent concurrency by region, AI Search availability) — R1's omission, still open.
3. **A package-level bill of materials** with status per package, generated from the manifest.
4. **Meter-level price rules** in the registers (E-19, E-13).
5. **A test that background work survives the idle timeout and a session stop**, and a **gateway capability matrix** by APIM tier (E-05, E-16).

## Appendix A — verified-correct claims (read 31 Oct 2026)

| Claim | URL | Evidence |
|---|---|---|
| Durable on Flex: always-ready `durable` group at 1; polling ≤ 10 s | https://learn.microsoft.com/azure/durable-task/durable-functions/durable-functions-azure-storage-provider | "Set the always ready instance count for the durable group to 1"; "Reduce the queue polling interval to 10 seconds or less" |
| Timers: six days for JavaScript, Python, PowerShell; .NET and Java unbounded | https://learn.microsoft.com/azure/durable-task/common/durable-task-timers | "limited to six days"; "Up-to-date .NET and Java apps support arbitrarily long timers" |
| Versioning defaults `CurrentOrOlder`, `Reject`; extension ≥ 1.14.0 | https://learn.microsoft.com/azure/durable-task/common/durable-orchestration-versioning | page text (no preview label) |
| Native APIM MCP: policies apply to all tools | https://learn.microsoft.com/azure/api-management/mcp-server-overview | "policies apply to all API operations exposed as tools" |
| APIM MCP management (products, Bicep) GA June 2026 | https://techcommunity.microsoft.com/blog/azureintegrationservicesblog/productize-observe-version-and-automate-mcp-servers-in-azure-api-management/4526931 | "new generally available capabilities for MCP server management in Azure API Management" (04 §4.4 is right) |
| `llm-content-safety` for MCP/A2A GA | Release Communications 562880 | "Generally Available: Azure API Management now supports content safety controls for MCP and A2A APIs." |
| Hosted agents GA June 2026; idle 2–240 min, default 15 | Release Communications 563596; https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-sessions | "Generally Available: Hosted agents in Foundry Agent Service"; idle 2 through 240 minutes, default 15 |
| Routines: release record preview vs Learn GA | Release Communications 563536; https://learn.microsoft.com/azure/foundry/concepts/general-availability | "Public Preview: Foundry Routines in Foundry Agent Service" |
| Sandboxes GA Sep 2026; dynamic sessions GA 2024-11 | Release Communications 561262, 467838 | "Generally Available: Azure Container Apps Sandboxes" |
| Flex rolling updates: GA record exists, Learn pages say preview | Release Communications 562365 | "Generally Available: Rolling updates in Flex Consumption" (the register's fail-closed is right) |
| Decisions API rolling out (EU endpoint UNVERIFIED) | https://learn.microsoft.com/azure/foundry/openai/how-to/decisions | "The Decisions API is rolling out to regions where `gpt-6-luna` is available." |
| Flex processing: per-request tier, Global Standard, no automatic fallback | https://learn.microsoft.com/azure/foundry/openai/how-to/flex-processing | page text (`x-ms-service-tier`, Global Standard) |
| Regional premium applies to models launched on or after 1 Sep 2026 | https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/azure-openai-pricing-update/4535385 | "the planned premiums apply only to models launched on or after September 1, 2026." |
| MCSB v2 AI-1…AI-7 names match 08 | https://learn.microsoft.com/security/benchmark/azure/mcsb-v2-artificial-intelligence-security | "AI-1: Ensure use of approved models" |
| Approved-models policy exists (renamed) | https://learn.microsoft.com/azure/foundry/how-to/model-deployment-policy | "Foundry model deployments should only use approved models" |
| Guardrails first 1,000 characters vs Content Safety 10K | https://learn.microsoft.com/azure/ai-services/content-safety/region-availability#service-limits | verified earlier in this review (paraphrase) |
| RBAC delegation conditions: role definition, principal, principal type, no scope; propagation ≤ 10 min | https://learn.microsoft.com/azure/role-based-access-control/delegate-role-assignments-overview | verified earlier (paraphrase) |
| WORM append blobs: `allowProtectedAppendWrites`, 50,000 blocks → 409 | https://learn.microsoft.com/azure/storage/blobs/immutable-storage-overview | verified earlier (paraphrase) |
| AI Search Europe: Sweden Central, West/North Europe, Germany West Central flagged "in high demand"; serverless Denmark East, Poland Central, Sweden Central | https://learn.microsoft.com/azure/search/search-region-support | verified earlier (paraphrase) |
| Cosmos DB: container-scoped RBAC; HTTP 409 on a duplicate id | https://learn.microsoft.com/azure/cosmos-db/how-to-connect-role-based-access-control | verified earlier (paraphrase) |
| Deployment Stacks: moving a resource removes protection; no Graph provider; ≤ 5 excluded principals | https://learn.microsoft.com/azure/azure-resource-manager/bicep/deployment-stacks | verified earlier (paraphrase) |
| Managed-identity tokens cached about 24 h | https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations | verified earlier (paraphrase) |
| Groundedness detection retires 30 Apr 2027; evaluator separate | https://learn.microsoft.com/azure/ai-services/content-safety/concepts/groundedness | verified earlier (paraphrase) |
| Citadel `81599b3` is head of `main`; MIT; no releases | https://github.com/Azure-Samples/ai-hub-gateway-solution-accelerator | verified earlier with `gh api` (paraphrase) |
| Azure MCP Server 3.0 GA (Oct 2026) | Release Communications 578662 | "Generally Available: Azure MCP Server 3.0" |
| Foundry IQ and Toolboxes GA; tool search preview | Release Communications 563222, 563481, 563506 | "Public Preview: Tool search in Microsoft Foundry toolboxes" |
