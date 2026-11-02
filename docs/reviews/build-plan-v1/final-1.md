# Build plan v1 final check

Checked on 2026-11-02 against the current files, after both closure reports. Paths are relative to the repository root. Paired IDs share one row, as in the brief. One item stays closed only in part; none is open.

| ID | Verdict | Current file:line | Note |
|---|---|---|---|
| cold-1.1 | CLOSED | `docs\build-plan\README.md:57`; `docs\build-plan\01-the-slices.md:15` | Principle 7 and the slice diagram both require that slice's stage of each check, and 02:103 and 03:9 say the same. |
| cold-1.5 | CLOSED | `docs\build-plan\02-before-you-start.md:66` | Thirteen monthly calls seed history, and only the open month is refreshed at most daily, respecting `Retry-After`. |
| cold-3.5 | CLOSED | `docs\build-plan\03-first-checks.md:57` | The pass asks for 429 once the minute's limit is exceeded and allows the call that crosses it. |
| cold-3.6 | CLOSED | `docs\build-plan\03-first-checks.md:65` | The Scheduler price is read from the vendor page, and a line for the chosen backend is added to the cost model before 0.4 is accepted. |
| cold-3.10 | CLOSED | `docs\build-plan\03-first-checks.md:92–93` | The pass requires at least one scope whose billing-role classification matches the probe, on agreement family, cost reach and resource reach. |
| cold-3.17, cold-4.1 | CLOSED | `docs\build-plan\03-first-checks.md:142`; `docs\build-plan\01-the-slices.md:69,72` | Safety is in 1a.3's check column, when the Surveyor first reaches production; Restraint and Honesty are in 1a.6b's, when Cases first recommend. |
| cold-3.18, cold-4.14 | CLOSED | `docs\build-plan\03-first-checks.md:154–155` | The drill trips hub-priced usage over a cap set low for the drill, bounds the call in flight (starting value 15 minutes), records both times, and requires a suspended contract to stop only that agent. |
| cold-3.19 | CLOSED | `docs\build-plan\03-first-checks.md:163` | The 1% test is actual cost, in billing currency, unassigned lines included, for the same scope and month. |
| cold-3.22 | CLOSED | `docs\build-plan\03-first-checks.md:80–81` | A digest is checked on the saving range and its basis, and on what it asks and why, and the answers that apply must match the letter's contract. |
| cold-4.7 | PARTLY | `docs\build-plan\01-the-slices.md:83`; `docs\build-plan\01-the-slices.md:72` | The lake-to-Cost-Management comparison now requires scope, month, currency and cost type written down beforehand, but the simulator replay against the lake still states only a tolerance and "last month's bill". |
| cold-4.9 | CLOSED | `docs\build-plan\02-before-you-start.md:63–67` | The ordered path table tries an export of another dataset before the Usage Details API, matching 01:85. |
| cold-4.11 | CLOSED | `docs\build-plan\01-the-slices.md:109` | 1a.7 keeps five named sections of the Monday letter, defers the other three until phase 3, and ends with the status block. |
| closure-1 N1 | CLOSED | `docs\build-plan\03-first-checks.md:81,86` | A direct send's 202 proves nothing; the pass is a non-delivery report or message trace, and nothing in the owned mailbox within a window written down beforehand. |
| closure-1 N2 | CLOSED | `docs\build-plan\02-before-you-start.md:23`; `docs\design\09-delivery-and-operations.md:44` | A private repository is asked to hold GitHub Enterprise Cloud, because Team has no required reviewer on an environment there. |
| closure-1 N3 | CLOSED | `docs\build-plan\02-before-you-start.md:73` | A firewalled export requires the estate to be in the solution's tenant. |
| cold-2.12, cold-5.5 | CLOSED | `docs\build-plan\02-before-you-start.md:16,18,21,71` | First uses now gloss `judge`, Atlas, Detector, the cost lake and columns mapped to the same layout. |
| cold-5.9 | CLOSED | `docs\build-plan\README.md:22,33,52`; `docs\build-plan\01-the-slices.md:61` | The principle and the three exits say the system makes zero writes to the estate, and the roadmap row says the same. |
| cold-5.17 | CLOSED | `docs\build-plan\02-before-you-start.md:44`; `docs\build-plan\README.md:13` | Acceptable: five to ten is only the starting hint, and one number must be written down before 1a.6a. |
| cold-5.19 | CLOSED | `docs\build-plan\01-the-slices.md:79`; `docs\build-plan\02-before-you-start.md:20,38`; `docs\build-plan\04-cost-effort-and-risks.md:79` | The CI runner is "deployment runner" in the three places that used to say "a runner" or "the runner". |
| closure-2 N1 | CLOSED | `docs\build-plan\01-the-slices.md:196`; `docs\build-plan\04-cost-effort-and-risks.md:65` | The chain is about 12 to 17 months, which is 43 to 59 person-weeks at four days in five. |
| closure-2 N2 | CLOSED | `docs\build-plan\02-before-you-start.md:85` | The kill switch page is placed in phase 3, as the roadmap lists it. |
| closure-2 N3 | CLOSED | `docs\build-plan\02-before-you-start.md:73` | The account privilege is for creation or a later change, the role is a time-boxed elevation, and a stack exception is a reviewed `infra/` change released like any other and then removed. |
| closure-2 N4 | CLOSED | `docs\build-plan\04-cost-effort-and-risks.md:7` | The figures are priced for Sweden Central, and another region must fetch the price snapshot again before 1a.1 compares the fixed lines. |
| closure-2 N5 | CLOSED | `docs\build-plan\02-before-you-start.md:20` | The network request includes peering with the hub's network. |
| closure-2 N6 | CLOSED | `docs\build-plan\04-cost-effort-and-risks.md:75` | Hand delivery keeps slices 0.5 and 1a.7 open. |

## New defects

**One new defect: 0 Blocker, 0 Major, 1 Minor.**

### N1 — Minor — the rewritten gate schedule does not match the slices that can carry it

- **Current file:line:** `docs\build-plan\03-first-checks.md:48,140,142`; `docs\build-plan\01-the-slices.md:72`.
- **Quote:** "each gate on the first release it applies to" and "Cost on every release".
- **Why wrong:** The check table assigns C11 only to 1a.1, 1a.3, 1a.6b and 1a.7, so Cost cannot be recorded on every release from that table, and line 140 says each gate runs on the first release it applies to. The Build and action plane gate, which design 08 includes the price simulator in, is scheduled only on the first release, while 1a.6a builds the simulator and lists only C8.
- **Fix:** Say Cost is recorded where Cases exist (1a.6b and 1a.8). Add a C11 stage to 1a.6a for the price-simulator check, or name that slice's replay as the check.

## Verification

Read on 2026-11-02. These checks verify documentation claims, not a tenant or a deployment.

1. **Graph send mail.** https://learn.microsoft.com/graph/outlook-things-to-know-about-send-mail — Step 1 returns `202 Accepted` when the draft is saved, and the app's interaction with Graph ends there. Step 5 applies tenant policies and can reject the message; steps 5 and 7 return a non-delivery report to the sender. Supports `03:81,86`.
2. **GitHub required reviewers.** https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#required-reviewers — "If you are on a GitHub Free, GitHub Pro, or GitHub Team plan, required reviewers are only available for public repositories." Supports `02:23` and design `09:44`.
3. **Cost Details.** https://learn.microsoft.com/azure/cost-management-billing/automate/get-small-usage-datasets-on-demand — One month per report; up to 13 months of history, seeded by 13 monthly calls; query fresh data at most once per day; use the `Retry-After` header. Supports `02:66`.
4. **Firewalled exports.** https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports — Storage privileges are required only during export creation or modification. "Currently, firewalls are supported for storage accounts in the same tenant. However, firewalls on storage accounts aren't supported for cross-tenant exports." Supports `02:73`.
5. **Token limit.** https://learn.microsoft.com/azure/api-management/llm-token-limit-policy — Without prompt estimation, a prompt may be sent even when the limit is already exceeded; concurrent requests can temporarily exceed the limit; once responses are processed and the limit is exceeded, subsequent requests are blocked (429 for the per-minute rate). Supports `03:57`.
6. **Docs check.** `python tools\check-docs.py --strict` before this file existed: 102 documents, 0 errors, 0 warnings. After it: one error, the expected orphan `docs/reviews/build-plan-v1/final-1.md:1` until the review index links it.

Release: YES
