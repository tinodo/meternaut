# Build Plan (Phase 0 and Phase 1a) Review — Reviewer A (Delivery Realism)

## Answers to the Specification's Seven Questions

### 1. Order, slicing, and missing or premature slices
Four slicing issues need correction:
- **Premature in 0.1:** `cardlint` checks Teams Adaptive Cards (`docs/experience/12-testing-the-experience.md:30`), which belong to Phase 2 (`spec.md:62`). Scope `cardlint` in `0.1` to the existing design templates only.
- **Missing in 1a:** The Monday letter links to the Report card Workbook and Settings (`docs/experience/05-letters-and-requests.md:67`), backed by the Logs Ingestion API custom table (`07-reports-and-dashboards.md:107`). No slice builds that table or Workbook in 1a.
- **Missing operational gate:** No slice runs the pre-release short-lived `operate` rehearsal (restore, isolation, kill-switch drill; `docs/design/09-delivery-and-operations.md:27`) or provides a CLI runbook to clear a tripped switch without the `approvals` web page.
- **Split 1a.6:** At 6–8 person-weeks, `1a.6` is too large; split `price-sim` and tool surfaces from the Detective-Skeptic-Economist loop.

### 2. Dependencies and what is shown without what it needs
Five dependency links are missing or inverted:
- **0.2 vs 0.3:** `0.2` claims `C1` (`spec.md:39, 72`), yet deploys no hosted agent (`0.3` does, `spec.md:40`).
- **0.6 needs M365:** `0.6` sends a real test e-mail (`spec.md:43`), requiring the shared mailbox, `Mail.Send`, Exchange RBAC for Applications, and allow-list mail-flow rule (`spec.md:88`), omitted from `0.6`'s `Depends on`.
- **1a.4 needs 0.2 and 1a.1:** `1a.4` lists only `0.4` (`spec.md:52`), omitting `0.2` (AI Search) and `1a.1` (estate services).
- **1a.6 needs 1a.3:** `1a.6` lists `1a.4, 1a.5` (`spec.md:54`), omitting `1a.3` (`estate-read`, `directory`).
- **1a.7 needs 1a.2 and 1a.3:** The digest reports bill movement and explained spend (`05-letters-and-requests.md:59`).

### 3. First checks: pass conditions, fallbacks, and gaps
The roadmap requires numerical budgets, margins, and windows fixed before measurement (`docs/design/13-roadmap.md:21`):
- **Vague pass conditions:** `C2` ("within the deadline; idle tails within budget"), `C6` ("within the stated budget"), and `C8` ("within a stated margin") omit numbers.
- **Missing from P1:** `C1` (`spec.md:72`) omits probing what a hosted agent reaches inside its sandbox with no grants (`docs/design/06-security-and-governance.md:67`, `13-roadmap.md:25`) and verifying Azure Policy denies spoke model deployments (`06-security-and-governance.md:107`).
- **Missing from P4:** `C6` (`spec.md:77`) omits Cosmos DB serverless limits and Detector back-test volume (`13-roadmap.md:28`, `04-knowledge-and-learning.md:256`).
- **Missing experience checks:** `1a.7` omits Layer 3 comprehension and Layer 4 five-person cold tests (`docs/experience/12-testing-the-experience.md:18-19`).
- **Unverified meter:** The Azure Language PII meter price is `UNVERIFIED` (`docs/design/10-cost-and-finops.md:133`); no check verifies it.

### 4. Plausibility of sizes
The 43–58 person-week total is plausible, but three slices are mis-sized:
- **Most underestimated — 1a.6 (6 to 8 person-weeks, `spec.md:54`):** Bundles three roles, two hosted agents, the Durable challenge loop, `price-sim` (reproducing the prior month's bill first, `04-knowledge-and-learning.md:218`), Prompt Shields, and PyRIT suites. Realistic range: **9 to 12 person-weeks** (split into two 4–6 week slices).
- **Underestimated without an existing hub — 0.2 (4 to 5 person-weeks, `spec.md:39`):** Deploying `hub/` from the accelerator and overriding its public-endpoint and payload-capture defaults (`docs/design/02-architecture.md:87`) takes **6 to 8 person-weeks**.
- **Slightly high — 0.4 (2 person-weeks, `spec.md:41`):** One stub tool and schema-hash check is **1 to 1.5 person-weeks**.

### 5. What stops a team from starting on Monday
Four blockers stop a Monday start:
1. **Missing export-creation permissions (`spec.md:48, 88`):** `1a.1` and `Before you start` ask only for read roles (`Reader`, `Cost Management Reader`, `Monitoring Reader`, `Log Analytics Reader`). Creating FOCUS exports in `1a.2` requires `Cost Management Contributor`, `Contributor`, or `Owner` (or a billing role) plus storage `Owner` (`Microsoft.Authorization/roleAssignments/write`) (`docs/design/09-delivery-and-operations.md:199`, `14-agreements-and-access.md:49`).
2. **Missing GitHub App prerequisite (`spec.md:88`):** `pr-draft` needs a GitHub App with fork/branch permissions (`docs/design/05-data-and-integrations.md:124`), absent from `Before you start`.
3. **Cold-estate history rule (`docs/design/04-knowledge-and-learning.md:300`):** Without a full rhythm cycle, the system outputs only *Scenario* figures ("not enough history"), stalling `1a.8`.
4. **Judge family check:** No week-0 check confirms `Mistral Large 3` (or another second family) is available in the adopter's region and data boundary (`03-agents-and-workflows.md:150`).

### 6. Contradictions with the design or the experience design
1. **C1 in 0.2 vs 0.3:** `spec.md:39, 72` assign C1 to `0.2` (empty apps, no agent) instead of `0.3`/`0.4` (`spec.md:40-41`).
2. **Export permissions:** `spec.md:48, 88` request read roles only, contradicting `05-data-and-integrations.md:52`, `09-delivery-and-operations.md:199`, and `14-agreements-and-access.md:49` (FOCUS exports need `Cost Management Contributor`/`Owner` or a billing role, plus storage Owner).
3. **1a exclusions vs kill-switch clearing and private endpoints:** `spec.md:102` excludes `approvals` and `runner` private endpoints in 1a, but `1a.1` deploys `operate` (`spec.md:48`, 11 private endpoints in `02-architecture.md:101`) and only `approvals` clears a tripped switch (`05-data-and-integrations.md:46`).
4. **Monday letter audience and links:** `spec.md:55, 62` target the FinOps lead only and defer the report card and web pages, contradicting `docs/experience/05-letters-and-requests.md:31, 67` (FinOps lead and platform owner; links to Report card Workbook and Settings).

### 7. Three most likely ways this plan fails, and what to add
1. **Access and network lead times stall Phase 1a:** Discovering in `0.6`/`1a.1`/`1a.2` that Exchange RBAC, `/24` subnets, private DNS, or FOCUS export rights take weeks.
   - *Add:* A **Week-0 readiness script** in `02-before-you-start.md` verifying Entra, Exchange, VNet/DNS, and export rights before Phase 1a.
2. **Slice 1a.6 blowout:** Combining `price-sim` bill reproduction, Durable loops, Prompt Shields, and PyRIT red teaming into one slice hides slip.
   - *Add:* Split `1a.6` into **1a.6a (`price-sim` and bill reproduction)** and **1a.6b (Detective-Skeptic-Economist loop and P7 red team)**.
3. **Unmet 1a.8 exit due to cold-start rules:** A new estate lacks a full cycle of history (`docs/design/04-knowledge-and-learning.md:300`), forcing findings to *Scenario* only.
   - *Add:* Require **13-month cost backfill** (`14-agreements-and-access.md:50`) and 93-day metrics (`05-data-and-integrations.md:87`) in `1a.2`.

---

## Findings

1. **Blocker · `spec.md:39, 72` · C1 is assigned to a slice with no hosted agent or tool.** `0.2` deploys empty Function apps and no hosted agent (`0.3` deploys the first hosted agent, `spec.md:40`; `0.4` publishes the first tool, `spec.md:41`), yet `0.2` claims `C1`. · **Fix:** Keep only negative direct-model-call and Policy deny checks in `0.2`; move full `C1` and `P1` to `0.3` and `0.4`.
2. **Blocker · `spec.md:48, 49, 88` vs `docs/design/09-delivery-and-operations.md:199` and `14-agreements-and-access.md:49` · Missing permissions to create FOCUS exports.** The spec requests only read roles, whereas `1a.2` prefers FOCUS exports, which need `Cost Management Contributor`, `Contributor`, or `Owner` (or a billing role) plus storage `Owner` at creation. · **Fix:** Add export-creation roles (or pre-created exports by the estate/billing owner) to `02-before-you-start.md` and `1a.1`/`1a.2`.
3. **Blocker · `spec.md:48, 55, 62, 102` vs `docs/design/05-data-and-integrations.md:46` and `docs/experience/05-letters-and-requests.md:67` · Phase 1a deploys kill switches with no clear path and sends a Monday letter whose link targets do not exist.** `workflows` can only *create* trip items in `switches`; clearing goes through `approvals` (`05-data-and-integrations.md:46`), which `spec.md:62, 102` defers. And `05-letters-and-requests.md:31, 67` sends the Monday letter to the FinOps lead and platform owner with links to the Report card Workbook and Settings. · **Fix:** Add a CLI switch-clear runbook and either build the minimal Report card Workbook + Logs Ingestion table in `1a.7` or define a linkless Phase 1a letter template.
4. **Major · `spec.md:54` · Slice 1a.6 is too wide (6–8 person-weeks) and omits its dependency on `1a.3`.** It combines three roles, two hosted agents, `price-sim` (which must reproduce the prior month's bill first, `docs/design/04-knowledge-and-learning.md:218`), Prompt Shields screening, and PyRIT red teaming (`P7`), while omitting `1a.3` (`directory` and `estate-read`). · **Fix:** Add `1a.3` to `Depends on`, split `1a.6` into `1a.6a` (`price-sim` + bill reproduction + Economist) and `1a.6b` (Detective + Skeptic loop + P7 red team), and size them at 9–12 person-weeks total.
5. **Major · `spec.md:29, 48` vs `docs/design/09-delivery-and-operations.md:27, 179` · No slice runs the pre-release Operate rehearsal, Cosmos restore test, or kill-switch drill.** Design 09 requires deploying a short-lived `operate` environment in dev (unlocked audit retention), running isolation, Cosmos restore, and kill-switch checks, and deleting it before production locks audit storage. · **Fix:** Add the rehearsal, restore test, kill-switch drill, and their runbooks to `1a.1`.
6. **Major · `spec.md:52, 53` · Missing dependencies and unstated scope for Atlas v0 and seed Detectors.** `1a.4` lists `Depends on: 0.4`, omitting `0.2` (AI Search) and `1a.1` (discovering which services the first estate uses). `1a.5` compiles Detectors from the 83 Verified rows of the cost-trap bank (`docs/design/08-testing-and-evaluation.md:30`) without bounding how many rows Phase 1a requires. · **Fix:** Add `0.2, 1a.1` to `1a.4`'s dependencies, add `1a.4` to `1a.5`'s dependencies, and cap Phase 1a to the first estate's top 5–10 services and 10–15 seed Detectors.
7. **Major · `spec.md:72-80` vs `docs/design/13-roadmap.md:21` · Pass conditions lack pre-set numerical thresholds and omit parts of P1, P4, and Experience Layers 3–4.** `C2`, `C6`, and `C8` lack explicit numbers; `C1` omits the in-sandbox zero-grant check (`06-security-and-governance.md:67`); `C6` omits Cosmos DB serverless and Detector back-test scale (`13-roadmap.md:28`); `1a.7` omits Layer 3 comprehension and Layer 4 five-person cold tests (`docs/experience/12-testing-the-experience.md:18-19`); and no check verifies the `UNVERIFIED` Azure Language PII meter price (`10-cost-and-finops.md:133`). · **Fix:** Commit numerical pass thresholds in `03-first-checks.md` and add the missing checks.
8. **Major · `spec.md:39, 88, 102` · Deploying the Citadel hub from scratch is under-sized and omitted from Phase 0/1a cost notes.** Without an existing hub, `0.2` must build `hub/` at a pinned commit and override its public-endpoint and payload-capture defaults (`docs/design/02-architecture.md:87`), adding ~2–3 person-weeks and ~1,200 EUR/month for APIM Standard v2 (`10-cost-and-finops.md:129`). · **Fix:** Split `0.2` sizing into "reuse hub" (4–5 person-weeks) vs "deploy `hub/`" (6–8 person-weeks) and note the own-hub cost sensitivity in `04-cost-effort-and-risks.md`.
9. **Major · `spec.md:50, 56` vs `docs/design/04-knowledge-and-learning.md:218, 300` · Cold-start history rules can prevent `1a.8` from confirming Expected savings.** `04-knowledge-and-learning.md:300` forbids stating an *Expected* saving on a new estate until a full cycle of history is present and onboarding thresholds are met. · **Fix:** Require `1a.1` to set onboarding thresholds (`09-delivery-and-operations.md:206`) and `1a.2` to backfill 13 months of cost data (`14-agreements-and-access.md:50`) and 93 days of Monitor metrics (`05-data-and-integrations.md:87`).
10. **Major · `spec.md:38, 43, 88` · Slice `0.6` omits its hard dependency on M365/Exchange setup.** `0.6` cannot send a test e-mail from the shared mailbox until the M365 admin configures the mailbox, `Mail.Send`, Exchange RBAC for Applications, and the allow-list mail-flow rule. · **Fix:** Add the Exchange Online prerequisite to `0.6`'s `Depends on` column.

---

## What I Would Change First

1. **Repair slice dependencies and prerequisite permissions (`01-the-slices.md`, `02-before-you-start.md`):** Move `C1`/`P1` completion to `0.3`/`0.4`, add `1a.3` -> `1a.6`, `0.2 + 1a.1` -> `1a.4`, `1a.4` -> `1a.5`, and `1a.2 + 1a.3` -> `1a.7`, and add Cost Management export-creation permissions and the `pr-draft` GitHub App to `02-before-you-start.md`.
2. **Split `1a.6`, bound `1a.4`/`1a.5`, and backfill history in `1a.2` (`01-the-slices.md`, `04-cost-effort-and-risks.md`):** Break `1a.6` into `1a.6a` (`price-sim` bill reproduction and Economist) and `1a.6b` (Detective/Skeptic loop and P7 red team) at 9–12 person-weeks total, cap `1a.4`/`1a.5` to the first estate's top 5–10 services and 10–15 seed Detectors, and backfill 13 months of cost data in `1a.2`.
3. **Close the Phase 1a operational and UX surface gap (`01-the-slices.md`, `03-first-checks.md`):** Add the pre-release short-lived `operate` rehearsal (restore, isolation, kill-switch drill) and a CLI switch-reset runbook to `1a.1`, and either build the minimal Report card Workbook + Logs Ingestion table in `1a.7` or strip Workbook/page links from the Phase 1a Monday letter.

**Commitment verdict:** I would **not** commit a team to this plan as it stands; with the three changes above applied to the specification, I **would** commit a team.
