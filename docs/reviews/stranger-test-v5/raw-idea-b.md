**Model:** GitHub Copilot | **Assigned files read:** `docs/03-estate-and-investigation.md`, `docs/04-finding-out-without-spending.md` | **Cross-reference files checked:** `docs/01-north-star.md` (vocabulary: Recommendation, Action, evaluation, Ledger, ten agents, six routes, four evidence levels).

## 1. Verdict

**Mostly.** A stranger can picture estate-reading, an Agenda of questions, and five cheap tests that do not build Azure resources — and §14 of `04` is honest about unused meters, headroom, and contract/region scope. Trust wobbles where the same idea is named two ways (ladder vs choose; five evidence *grades* vs four evidence *levels*; two things called Ledger) and where Trial is both a live change and a rung that “costs no Azure resources.”

## 2. Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | `03:168`–`175` | 4 | `Every rung costs a little AI and no Azure resources` then lists **Trial** | Trial in `04:105`–`107` is a change to a running resource. Calling it a zero-Azure-cost rung is false. `04:154` repeats `It never costs Azure resources` after defining Trial as a way of finding out. | After the five read-only routes, write: `Those five cost AI and attention, not Azure. Trial is separate: it changes one existing resource, so it can move the bill; it is not on the free ladder.` Align `04:154` to tokens and minutes only. |
| 2 | Major | `04:24` vs `03:168` / `01:237` | 4 + 1 | `It does not climb a ladder — it chooses` | `01` says find out `in the order below, cheapest first`. `03` names an **evidence ladder**. `04:24` then ranks the six ways `more convincing, and more demanding, than the one before` — a ladder — while denying the word. Residue of an argument the reader never saw. | Delete the denial. One sentence: `The Detective or Economist picks the cheapest test that would change the decision (Ask → Look → Replay → Watch → Pool → Trial), and may pick again.` |
| 3 | Major | `03:191` vs `01:417` | 4 + 2 | `measured → observed → reported → inferred → assumed` | North-star **evidence levels** are `documented → price-confirmed → bill-observed → outcome-confirmed`. `03` never uses those four. `04` uses *bill-observed* (`04:68`) and *documented only* (`04:218`) and never *price-confirmed* or *outcome-confirmed*, so Trial is not named as the path to outcome-confirmed. Two scales, no map. | In `03`, replace the five grades with the four levels, or add one line: `Those grades weigh a fact in a Case; Atlas claims use documented / price-confirmed / bill-observed / outcome-confirmed.` In `04` §7, add: `A successful trial is how a claim becomes outcome-confirmed.` |
| 4 | Major | `03:122` vs `03:248` / `01:67` | 4 + 2 | `Unexplained Spend Ledger` and `the Ledger of predictions and outcomes` | `01`’s **Ledger** is only predictions and outcomes. `03` uses Ledger for unexplained euros *and* for scored predictions. `04:36` dumps `Ledger` into a knowledge bubble with Atlas and Lessons. A stranger cannot tell which book is which. | Keep **Unexplained Spend Ledger** as a proper name. Call the other the **prediction Ledger** (or `01`’s Ledger) on every use. Do not use bare “Ledger” in `04`’s diagram. |
| 5 | Major | `03:170` vs `03:21` | 4 | `A year of experiments somebody already paid for` | Same file: Azure keeps property changes **14 days**, platform metrics **~93**, activity log **90**. Bills can go back ~13 months; *changes against charges* cannot, unless the customer exported. `04:70` admits this; `03`’s Look rung does not. | Replace with: `Bills go back as far as Cost Management retains them; joining a change to a meter only works for history the estate kept (platform defaults: 14 / ~93 / 90 days).` |
| 6 | Major | `03:33` vs `01:154` | 4 | `A role granted since is noticed at the next probe` | Probe is `onboarding and weekly` (`03:33`). `01` says `A role granted tomorrow is noticed tomorrow.` | Pick one. If the probe is weekly: `A role granted later is noticed at the next weekly probe.` Change `01` to match. |
| 7 | Major | `04:12` | 1 | `This system takes the other road` | Answers “why not a spend-to-learn lab?” without ever introducing a lab. Same family: `03:262` `No customer-specific model training is needed`; `04:203` `(generated data, never deployed resources)`. | Delete `the other road`. Open with: `The system does not deploy resources in order to learn. It reads estates that already ran.` Drop the training denial; keep `The Atlas already knows Azure.` Keep “generated data” once, without the lab echo. |
| 8 | Major | `03:152`, `04:158` | 3 | `the ranking is itself learned` / `a bandit-style allocation` | “Learned” with no picture, then an ML allocation named as if chosen. Ideation is not allowed to pick that method; a stranger cannot see what changes. | `The Conductor keeps a simple score per tactic (verified value per euro and per minute) and spends more on tactics that have paid off, with a fixed share for new questions.` Leave bandits to design. |
| 9 | Minor | `04:24` | 3 | `None of them creates anything in Azure except the last` | Trial **changes** an existing resource; it does not create one (`04:109`). | `None writes to Azure except Trial, which only changes one resource the owner already runs.` |
| 10 | Minor | `04:176`–`187` | 2 | `an Action runs at assist level only` | **Action** and *assist* are `01`/`05` terms, undefined here. **evaluation** never appears in either assigned file. | One gloss: `Action: a reviewable change recipe; assist means the owner still taps yes.` Or drop Actions from this Detector diagram. |
| 11 | Minor | `04:145` | 2 | `the Cost Grammar is wrong there` | First use in `04`, no definition. `03:218` `team Atlas` collides with the knowledge Atlas. | `the Cost Grammar (how a meter makes money) is wrong there`. Rename the example team. |
| 12 | Minor | `03:184` | 1 | `The Skeptic is adversarial by design` | `by design` is a defence. | `The Skeptic’s job is to break the case.` |
| 13 | Minor | `04` §3–§8 | 6 | Ask is first in the diagram, last in the prose (`§8`) | A stranger following headings meets Look before Ask. | Put Ask as §3; shift Look–Trial down. |

## 3. Sentences I would delete

1. `04:24` — `It does not climb a ladder — it chooses, and chooses again when a result is not enough.`
2. `04:12` — `This system takes the other road:` (keep the bill-as-results claim).
3. `04:50` — `The hub is not a rule that every question visits every way:` (the diagram already shows choice).
4. `03:262` — `No customer-specific model training is needed to start —`
5. `03:184` — `adversarial by design, rewarded for good objections, not for agreement.`
6. `03:280` — `Illustrative: none of these is a rule the system is given.`
7. `04:158` — `a bandit-style allocation with a protected exploration share`
8. `04:24` — `None of them creates anything in Azure except the last, and the last only changes something an owner already runs.` (replace, don’t keep both halves).
9. `04:203` — `(generated data, never deployed resources)` — say generated data once in §13.
10. `03:218` — `the three development subscriptions of team Atlas` — pick another team name.

## 4. Fact checks

1. **Platform metrics ~93 days** (`03:21`, `04:70`). [Azure Local / Metrics](https://learn.microsoft.com/en-us/azure/azure-local/manage/monitor-cluster-with-metrics): “Platform metrics are stored for 93 days…”. **Supported.** (Chart window max 30 days is extra, not a contradiction.)
2. **Resource property changes 14 days** (`03:21`, `04:70`). [Resource Graph overview](https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview): “View the last 14 days of resource configuration changes”. **Supported** for ARG Change Analysis, not for every “change history” (activity log is longer).
3. **Activity log 90 days** (`03:21` only). [Activity log](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log): “Azure retains activity log events for 90 days”. **Supported.**
4. **Cost data hours–days late, rerated, period closes some days later** (`04:68`, `03:265`). [Understand Cost Management data](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data): EA/MCA typically 8–24h, PAYG up to 72h; period *closes* typically up to 72h after month end; charges can move until day 5. **Directionally right; underspecific.**
5. **Linux Consumption retires 30 September 2028** (`03` gallery). [Consumption plan](https://learn.microsoft.com/en-us/azure/azure-functions/consumption-plan): Linux Consumption retires 30 September 2028. **Supported.**

## 5. Questions left unanswered

1. Who asks the human on **Ask** — Surveyor (`03:89`), Detective (`03:168`), Diplomat (`01` cast), or “the system”?
2. How do Case **evidence grades** (`03:191`) map to Atlas **evidence levels** (`01` glossary), and when does a Trial promote a claim to **outcome-confirmed**?
3. If Trial can move the bill, what is the spend cap, and which writer (Engineer vs “the system”) applies the change after consent?
4. After onboarding, is **Look** limited to 14/93/90 days until exports exist, or do Cost Management bills alone power a year of before-and-afters?
5. What does **evaluation** (north-star harness / report card) have to do with Watch, Replay, and ablations in `04` — same report card, or a different score?
