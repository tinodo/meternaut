# Stranger test: closure check (brief for the closure checker)

Repository: `<repo>` (private; you only read it). "Azure Cost in Action" is an open-source project (MIT): a team of AI agents on Microsoft Foundry and Microsoft Agent Framework that keeps an Azure estate cost-efficient. Nothing is built; there are two sets of documents: the **ideation** (`docs\01` to `docs\10`, `docs\research\`: the idea, no technology choices) and the **design** (`docs\design\`: architecture, security, evaluation, cost, decisions).

Cold readers (people who had never seen the repository) read the documents and filed findings in `docs\reviews\stranger-test-v5\raw-*.md`. The documents were then fixed. **You are the closure checker, not a cold reader.** You do not re-audit the documents. For every finding in your assigned reports you say whether the current documents close it, and you look for contradictions the fixes created.

## Read first

1. `brief-cold-reader.md` (this folder): what the cold readers were asked (classes 1 to 7 of a finding).
2. `brief-fixes.md` (this folder): global decisions D1 to D16 that the fixes follow (agreement not contract, evidence levels, scenarios, Trial not free, route Follow, Ledger, public Atlas, invented examples, probe cadence and so on).
3. `docs\01-north-star.md` (vocabulary source of truth for the ideation) and `docs\design\README.md` (glossary of the design).
4. Your assigned reports, then the documents each finding points at. The line numbers in a report refer to the documents as they were; search for the quoted words.

## For every finding in your reports (all severities)

State one of:

- **CLOSED**: quote (at most 25 words, with `file:line`) the sentence now in the document that closes it.
- **CLOSED-BY-DELETION**: the passage is gone; confirm by searching for the quoted words.
- **REJECTED-OK**: the finding was not applied (see `docs\reviews\stranger-test-v5\` for any note; if there is none, judge it yourself). Say whether keeping the text is right. For a claim about a Microsoft product, read the page on `learn.microsoft.com` and give the URL and a quote of at most 25 words.
- **PARTLY / OPEN**: say exactly what is still missing and give the replacement sentence.

If a fix made the text worse or created a new problem, say so under new defects, not under the finding.

## Then look for new defects (at most eight, Critical or Major only)

Search the documents of your assignment (and `docs\01-north-star.md`, `README.md`) for contradictions the fixes may have created. Use grep, do not guess:

1. "contract": in the ideation a customer's commercial arrangement is an **agreement** (Enterprise Agreement, Microsoft Customer Agreement bought directly, sold through a partner (CSP), pay-as-you-go); "contract" survives only in "the learning contract" and "contracted rates". In the design the hub's per-agent "contract" is Citadel's access contract and is fine; it must never mean the customer's agreement.
2. Routes: Ask, Look, Replay, Follow, Pool, Trial (in that order). "Watch" survives only as the Watch clock and the Watch workflow.
3. Evidence levels: documented, price-confirmed, bill-observed, outcome-confirmed describe a claim. Other scales must be called something else ("how the fact was obtained"). Cost-trap bank rows are "source-verified", never "bill-confirmed", and "verified" is never bare.
4. Without a readable bill a figure is a labelled **scenario priced at list prices**; "saving" only when a bill line confirms the meter.
5. Trial changes something an owner already runs, so it can move the bill; nothing says learning "costs no Azure resources". The accurate statement: "learning never provisions anything just to measure it".
6. "Unexplained Spend list" (bill lines the system cannot explain) versus "Ledger" (predictions, decisions, outcomes).
7. The Atlas is public (documented, price-confirmed). A customer's own price sheet, bill-observed and outcome-confirmed claims stay in the estate. Pool shares only a scope and an aggregate, privacy-reviewed, only when several organisations contribute. The Commons shares regression cases; sealed cases and their answers are never shared with the system under test.
8. Every example with named people, invented figures or a made-up service is labelled as invented.
9. The capability profile is probed at onboarding, weekly, and at once after a 401 or 403.
10. "autonomy ladder" is the observe, advise, assist, autopilot progression; no other thing is called a ladder.
11. Residue: sentences that answer an objection nobody made, defend a choice against an unnamed critic, mention earlier versions, labs, exams, rounds, reviewers, or the people who commissioned the work.
12. Any claim of a measured result, or "we found / tested on", about a system that is not built.

Report a new defect as: `N-<n> · Severity · file:line · quote (at most 25 words) · why it matters · fix`.

## Rules

- **Read-only.** Do not edit any repository file; the only file you create is your report at the path in your assignment. No git. Do not post anywhere or send repository content to a third-party service (the repository is private).
- Verbatim quotes with `file:line`. Do not invent identifiers. A platform fact needs a Learn URL, or say UNVERIFIED.
- Do not praise. Do not summarise the documents.
- Other agents may still be writing some ideation files while you read; if a file changes under you, re-read it before calling a finding OPEN.

## Report format (at most 2,600 words), saved exactly as returned

1. **Table**: `Report` · `#` · `Severity` · `Status` (CLOSED / CLOSED-BY-DELETION / REJECTED-OK / PARTLY / OPEN) · `Evidence` (the quote with `file:line`, or what is missing and the replacement sentence). One row per finding, in report order.
2. **New defects** (at most eight).
3. **Counts** (closed, closed by deletion, rejected-ok, partly, open) and a one-line verdict: could a stranger read your assigned documents without meeting reasoning residue, a contradiction or an undefined term?
