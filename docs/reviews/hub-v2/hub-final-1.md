# Hub review 2, final check: raw report

The same reviewer (gpt-6.1-sol) made one more, narrow check of the branch `hub-existing-apim`, at commit `fe81e94`: the three fixes of [the closure round](hub-closure-1.md), the three findings that were closed in part, the new way of reading an object's state, and a try at breaking the workflow lint with other layouts of valid YAML. The review was read-only: the reviewer ran the tests and the Bicep compile locally and changed nothing in Azure or GitHub. The report is as delivered, except that the file paths were absolute and are shortened here to paths relative to the repository.

## Verdict

**Yes—the package is safe to hand to the owner for pull-request review; no blocking defect was confirmed in this narrow check.** One non-blocking YAML-linter bypass remains, so the claim that all prior findings are completely closed is not yet true.

**Scope:** `fe81e94`, with source and test contents pinned to that commit.

## Status

| ID | Status | Evidence |
|---|---|---|
| **H2-14** | **Closed** | `tools\apim-sync.py:267–287,302–324` — Probes covered 200/201/202 followed by 404 → working → Created; case-insensitive working states; failed/canceled resubmission; permanent working/404 timeouts; read errors; and stateless policy/link/subscription results. The unknown-state assumption is discussed below. |
| **H2-15** | **In part** | `tools\workflow-lint.py:138–153` — The previously reported header and condition-continuation cases are rejected, but a guard embedded in a quoted display name still produces zero findings: **H2-17**. |
| **H2-16** | **Closed** | `hub\README.md:63,74` — Unreadable bodies are correctly documented as 403, and saving a policy is explicitly distinguished from runtime verification. |
| **H2-05** | **Closed** | `tools\apim-sync.py:279–287` — Every accepted write now performs a post-write read with `must_exist=True`, not merely writes returning 202. Existing working objects are settled before comparison; failed ones are resubmitted. |
| **H2-08** | **Closed** | `hub\README.md:74` — The remaining save-time validation overclaim is removed. The previously checked failure-aware workflow summary is unchanged. |
| **H2-12** | **In part** | `tools\workflow-lint.py:109–153` — Ordinary second jobs, duplicate `if` lines, wrong-indentation guards, and `needs`/`environment` without a guard are rejected. Quoted-scalar content can still impersonate a structural guard. |

### Checks

- **168/168 tests passed**, with zero failures, errors or skips. Tests used commit-pinned sources, standard newline handling and memory-only fixture writes; disk mutation and network access were blocked.
- **Both Bicep templates built and linted successfully** using Bicep **0.46.1**, stdout capture and `--no-restore`.
- Readiness failures stop processing; removal still uses DELETE directly and does not enter readiness polling.
- The new “unknown word is final” test verifies that chosen fallback—it does **not** establish Azure’s state vocabulary.

## New defect

| ID | Severity | File:line | What is wrong | Why it matters | Suggested fix |
|---|---|---|---|---|---|
| **H2-17** | **Minor** | `tools\workflow-lint.py:138–153` | `job_conditions()` recognizes an `if:` physical line even when it is inside a multiline double-quoted job `name`. Removing the actual job guard and inserting the display name below returned **zero findings** against the pinned commit. A similar quoted workflow-name decoy also passed. | The checker can approve an unguarded job while believing it found the exact owner/main guard. **The currently committed workflow still has its real guard**; this is a remaining regression-check bypass. | Reject multiline quoted scalars in the supported YAML subset, or make structural scanning quote-aware. Add both job-name and workflow-name decoys as regression tests. |

Reproduction: remove the actual job-level `if:` and replace its display name with:

```yaml
    name: "Hub
    if: github.actor == 'tinodo' && github.ref == 'refs/heads/main'
    "
```

This is one YAML string value. Its apparent `if:` is display text, not a condition.

Trailing spaces, CRLF and an initial document separator did not weaken the guard check. I have **not** counted duplicate-root-key or multi-document examples as GitHub-valid bypasses.

## New first-real-run question: readiness signals

Polling the object’s own built address is **not inherently a defect** and preserves the request-address fence. What still needs confirmation is that APIM’s ordinary GET exposes sufficiently current provisioning information for the write being checked.

The fallback remains a heuristic: probes showed that unlisted words such as `Queued`, `NotStarted` and `In Progress` advance immediately. In a synthetic case, that allowed a dependent PUT to run early; its 409 then stopped apply, leaving partial work rather than reporting success. I have not established that this APIM API emits those unlisted transient values, so I am not presenting that simulation as a confirmed additional defect.

The first owner-started run should therefore establish the actual state vocabulary and post-write GET visibility. If those signals are insufficient, operation-correlated polling through a validated same-resource URL would be needed. No Azure or GitHub changes were performed during this review.
