# Round 2 — review of the v2 package

> **Status:** **in progress** (started 2026-10-30). This folder will hold the verbatim reports of the second review round, the orchestrator's spot-check of every external fact the reviewers cite, and a disposition table in the same shape as [round 1](../round-1/disposition.md).

Round 2 reviews **v2** (the package after round 1's findings were applied), so it attacks the *revisions* rather than repeating round 1. The planned lenses:

| # | Lens | Question |
|---|---|---|
| 1 | **Red team and disposition audit** | Did any v2 change introduce a new contradiction or a new loophole? Is every row of the [round-1 disposition](../round-1/disposition.md) actually true — does the cited section contain the change? Is anything silently dropped? |
| 2 | **Fact-check, grounded in Microsoft Learn** | Do the Azure, Microsoft and Well-Architected / Cloud Adoption Framework claims in the research notes, the catalog evidence map and the deep dives hold against primary sources today? |
| 3 | **Consistency and completeness** | Are definitions, counts, anchors and cross-references consistent across all documents (reversibility classes, invariants, threat IDs, release-1 scope, kill criteria)? |

Raw reports will be saved here unedited as `01-…`, `02-…`, `03-…`; the orchestrator's spot-checks and the disposition follow; the package is then revised to **v3** (v2 is archived first, never overwritten).
