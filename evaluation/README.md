# evaluation/

The tests that show whether the system does what the design says, and the numbers that decide a pass. The code owners are the Atlas reviewers ([design 09](../docs/design/09-delivery-and-operations.md#1-the-repository)); the plan for what is shown first is [the build plan](../docs/build-plan/README.md).

| Path | What it holds |
|---|---|
| [`c14/`](c14/README.md) | Check C14, the small learning demonstration: a harness, an invented template pack and its tests |

**Numbers are written before the measurement.** Every pass condition, margin, budget and time window is a starting value, written here by a pull request before anything is measured. A different number later is a new pull request with its reason, and the earlier result stays on record.

**Nothing here touches an estate or a subscription.** The harness reads local files and, for a real run, calls a model through the governance hub. Cases are synthetic data.

Run every test of the folder from the repository root:

```text
python -m unittest discover -s evaluation/c14/tests -t evaluation/c14
```
