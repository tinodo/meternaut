# C14: the small learning demonstration

A small, early look at the project's central idea: when the system meets new evidence, it answers cases it has not seen better than before, and it stays quiet on look-alikes that are legitimate. The check is written in [the first checks](../../docs/build-plan/03-first-checks.md#c14-new-evidence-makes-the-system-better); this folder is the harness that runs it. It does not replace proof point P6, which needs sealed test cases and baselines in phase 1b.

## The flow

1. **Choose a mechanism** that no claim in the snapshot covers, from a verified row of [the cost-trap bank](../../docs/research/cost-trap-bank.md), and a reserve mechanism, and write a *pack* (below) by pull request. A different reviewer from the one who will review the claim writes the cases and the key; if one person holds both roles, the pack is committed before step 2. Then `python evaluation/c14/run.py check PACK`.
2. **The system proposes a claim.** `run.py propose PACK --out DIR` reads the source and drafts a claim with its receipt. Code checks that the quote is on the page and that its hash matches.
3. **A person decides.** In `DIR/review.json` a reviewer sets `decision` to `accepted`, `edited` or `rejected`, names themselves, and edits the claim if needed. Code refuses a claim whose quote is not on the page, that copies five words from a case, names a case or states the amount the key gives for one, that reuses the id of another claim, or whose mechanism the control claim shares; it also refuses `accepted` when the claim differs from the system's draft and `edited` when it does not. The report lists every field the reviewer changed. Only an accepted or edited claim enters memory. Choose the control claim now, one that takes about as many characters in the prompt as the accepted claim, and put it in the pack before the run.
4. **A stop test, then the arms.** `run.py run PACK --out DIR --max-calls 2` shows that the call limit stops a run. Then `run.py run PACK --out DIR` answers every case, several times, in three arms: **frozen** (the snapshot), **control** (the snapshot plus the unrelated claim) and **updated** (the snapshot plus the accepted claim). Runs are interleaved so that a change in the model hits every arm alike, and the model alias, the prompts and the settings are the same in every arm. The title of a case is for the person reading the report; the finder sees only the facts.
5. **The report and a person's reading.** `DIR/report.md` shows a before-and-after table, each pass condition, the cost, the limits, and every updated answer that found a case. A person who did not build the harness reads each one and, in `review.json`, sets `answers_read_by` to their name and `answers_rest_on_the_claim` to `true` or `false`. `run.py report DIR` then works the verdict out again. `DIR/results.json` keeps every reply.

`python evaluation/c14/run.py demo` runs the whole flow on the invented template pack with a scripted stand-in for a model. It shows how the flow works and says nothing about a real model.

## A pack

| File | What it holds |
|---|---|
| `params.json` | The starting values: runs per arm, the number of cases, the smallest snapshot (the plan's starting value is five to ten claims), the pass numbers, the price tolerance, the call limit, the reply limit, the token prices and the spending cap |
| `source.json`, `source.txt` | The public page the new claim must come from, as read on the retrieval date |
| `snapshot/*.json` | The frozen memory: a few claims in the Atlas format, one file each |
| `control.json` | One accepted claim about something unrelated |
| `cases.json` | The unseen cases and the decoys, as the finder sees them. A case shares no run of six words with the source |
| `key.json` | The right answer for each case, never shown to the model: waste or not, the monthly amount, an optional tolerance and optional words the cause must contain |

[`pack-template/`](pack-template/) is a complete example with an invented service. Every figure in it is invented.

## What a pass means

All of these, from the plan: frozen and control each find at most the starting value of the waste cases, by the median of their runs (otherwise there is no headroom, because the model already knows the mechanism: record it and use the reserve mechanism with new cases, and a second case of no headroom goes to the learning review as it stands); the updated arm finds and prices enough of them in enough runs; no decoy is flagged in any updated run (flags in the other arms are reported, not counted); the claim's quote is on its page and the claim gives away no case; a reviewer decided; a person confirms that each updated answer rests on the new claim; and the cost stays inside the cap of the funded stage. `run.py` exits 0 only when every one holds. Until a person has read the answers the verdict is pending, and a pending verdict is not a pass.

A case is *found* when the answer says it wastes money and, if the key lists cause words, contains one of them in its explanation or action; it is *priced* when its amount is inside the tolerance.

## Guards

- A real run refuses to start without a spending cap, token prices, a reply limit and a call limit in `params.json`. The hub is told the reply limit, and before each call the guard refuses the call if the cost so far, the call's prompt (estimated at one token for two characters) and a reply of the full limit could pass the cap. So a run does not end above its cap, and the call that would cross it is never made.
- The calls of `propose` count against the same limit and cap as the arms: `run` starts from what `propose` recorded in `proposal.json`.
- Every model call goes through the hub. The route and the credentials come from the environment (`C14_HUB_CHAT_URL`, `C14_HUB_MODEL`, `C14_HUB_KEY` or `C14_HUB_BEARER`; see `harness/client.py`); nothing is read from a file in the repository, and no key or token is written to a report.
- Cases are synthetic. No estate data, no subscription, no resource is involved.
- The mechanism and the cases used here are retired from the sealed set of phase 1b.

## Tests

```text
python -m unittest discover -s evaluation/c14/tests -t evaluation/c14
```
