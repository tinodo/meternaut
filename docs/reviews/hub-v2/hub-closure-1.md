# Hub review 2, closure: raw report

The same reviewer (gpt-6.1-sol) checked each fix of [hub-review-1.md](hub-review-1.md) against the files at commit `a511e5d` of the branch `hub-existing-apim`, and read the fixes for what they broke. The review was read-only: the reviewer ran the tests and the Bicep compile locally and changed nothing in Azure or GitHub. The report is as delivered, except that the file paths were absolute and are shortened here to paths relative to the repository.

## Verdict

**No, not yet ready for the owner's pull-request review as the corrected deployment package.** The destructive ownership escape is fixed and all 158 tests pass, but APIM readiness remains incomplete, the workflow linter still accepts guard bypasses, and some documentation overclaims remain.

## Closure of H2-01 to H2-13

| ID | Status | Evidence |
|---|---|---|
| **H2-01** | **Closed** | `tools\apim-sync.py:38,85–90,246–253`: the original query/fragment escape is rejected. The reviewer's probes of the id, the substituted contract name, the `key` command, percent-encoding, backslashes, Unicode, trailing dots and long names found no service-root or foreign-namespace escape. |
| **H2-02** | **Closed** | `tools\apim-sync.py:40,186–193`: the prefix is now constant, and a manifest declaring a foreign prefix is refused before requests are sent. |
| **H2-03** | **Closed** | `tools\apim-sync.py:290–300`: product deletion no longer requests subscription cascading. The relationship-aware tests retain a foreign subscription; ordinary removal and a second removal both pass. |
| **H2-04** | **Closed** | `tools\apim-sync.py:267–271,316–325`: updates with bodies receive `If-Match: *`; a second successful apply writes nothing. Policy and diagnostic update headers and the bodyless product-API link PUT match the REST reference. |
| **H2-05** | **In part** | `tools\apim-sync.py:274–285`: the 202 case waits, but the documented API-creation 200/201 asynchronous responses do not. Existing failed resources can also be skipped. See H2-14. |
| **H2-06** | **Closed** | `.github\workflows\deploy-hub.yml:94–116`; `hub\main.bicep:206`: the existing date is read and passed through. Bash probes preserved an ISO date, selected the current UTC month only for not-found, and stopped on authorisation failure; compilation confirmed the module parameter wiring. |
| **H2-07** | **Closed** | `tools\hub-smoke.py:107–172`: missing, zero, Boolean and string usage values are rejected; an OpenAI-shaped backend 429 fails rather than passing. An accepted large request must report usage at least equal to the allowance. |
| **H2-08** | **In part** | `.github\workflows\deploy-hub.yml:295–311`: all 24 summary-outcome probes passed. However, `hub\README.md:74` still overstates save-time policy validation; see H2-16. |
| **H2-09** | **Closed** | `hub\BOOTSTRAP.md:109–119`: bootstrap reversal and purge now require separate plain-word approval; normal removal remains the workflow's job. |
| **H2-10** | **Closed** | `.github\workflows\deploy-hub.yml:125–138`: the preview now retries the specific restore signal with `restoreAccount=true`. Normal, restore, failed-restore and unrelated-failure Bash probes behaved correctly under the runner flags. |
| **H2-11** | **Closed** | `hub\apim\policies\contract.xml:8–55`: string-type and model checks and the streaming refusal precede the limiter. `hub\apim\policies\llm-api.xml:8–23` retains the missing-product-variable refusal before routing. |
| **H2-12** | **In part** | `tools\workflow-lint.py:109–139,184–188`: the original OR mutation and an ordinary second job are rejected, but valid YAML header variants and a continued condition still pass with zero findings. See H2-15. |
| **H2-13** | **Closed** | `hub\BOOTSTRAP.md:23`: the text explicitly acknowledges that Contributor can delete the entire assigned hub resource group. |

## Defects found in the fixes

| ID | Severity | File:line | What is wrong | Why it matters | Suggested fix |
|---|---|---|---|---|---|
| **H2-14** | **Major** | `tools\apim-sync.py:267–287,316–325` | **Readiness is still confused with HTTP status or property equality.** The exact 2024-05-01 API definition marks PUT as long-running; its minimal example returns **200 and 201 with `provisioningState: InProgress` and polling headers**. The code only waits after 202. A 201 probe proceeded to the dependent write without polling. Separately, an existing API reporting `Failed` but matching the wanted properties produced exit 0, eight "unchanged" objects and zero PUTs. | Initial deployment can advance before API creation finishes. A rerun can claim reconciliation without repairing, or even rejecting, a failed API. The private endpoint already exists and bills at this point. | Recognise asynchronous responses from their headers and state, not only status 202. Poll the validated `Location` to a terminal result under a bounded deadline. Check readiness before skipping an API as unchanged: wait for `InProgress`, and explicitly fail or resubmit an approved definition for `Failed`. Add realistic 200/201 and existing-failed-state tests. |
| **H2-15** | **Minor** | `tools\workflow-lint.py:109–139,184–188` | **Unsupported YAML is still silently accepted.** A second job headed `probe: # comment`, `probe: &anchor`, a quoted job key, or a flow-style job is ignored by `jobs_of()`. All passed with zero findings. An indented `\|\| true` continuation after the otherwise correct job `if:` also passed: the linter checks only its first physical line. | A valid workflow can contain an unguarded job or an always-true condition while passing the promised exactly-one-job and exact-guard check. The current workflow itself remains correctly guarded. | Reject unrecognised entries at the jobs-mapping level instead of appending or discarding them. Parse the complete condition scalar, or explicitly reject continuations. Add the demonstrated comment, anchor, quoted-key, flow-style and multiline-condition cases. No new dependency is necessary for a conservative fail-closed subset. |
| **H2-16** | **Minor** | `hub\README.md:63,74`; `hub\apim\policies\contract.xml:8–44` | **Two claims remain inaccurate.** An unreadable body is documented as 400, but the model-reading catch returns an empty string, so the first refusal returns **403** before the streaming branch. The README also implies that saving rejects policy mistakes and prevents a half-working policy; Microsoft explicitly documents limited expression verification and possible runtime errors. | Readers get the wrong negative-path contract and a stronger validation guarantee than exists. The actual refusals remain fail-closed. | Document 403 for unreadable bodies, or deliberately introduce a separate parse-failure branch if 400 is required. Describe policy saving as partial validation, not runtime proof; keep successful execution checks as the evidence of behaviour. |

The protocol evidence for H2-14 is the exact 2024-05-01 API definition in the Azure REST API specifications (`apimapis.json`, long-running operation handling with `final-state-via: location`) and its minimal create example (`ApiManagementCreateApi.json`), which contains the in-progress 200 and 201 responses.

## Verified right

- **Checks passed:** 158 tests, zero failures, errors or skips, which is the expected count and 17 more than the previous round. As before, fixture writes were virtualised in memory, bytecode was disabled, and real filesystem mutation and network access were blocked during the tests.
- **Bicep passed:** version 0.46.1 built and linted both templates successfully. The compiled ARM requires `budgetStartDate`, passes it to the budget module and sets the model-role assignment's `principalType` to `ServicePrincipal`. It still declares no new APIM service, private DNS zone, link or zone group, manual peering or route table.
- **The ownership fix survived renewed attack:** 132 resource-id cases and 104 contract-file, `--var` and command combinations produced no effective ownership escape. Query values remained encoded rather than becoming paths. Eight Unicode case-folding variants matched the id pattern, but the actual HTTP request encoder rejected their raw paths before connecting; they did not escape the boundary. Long or otherwise invalid names were not mistaken for authority or path escapes.
- **REST update forms are appropriate:** a wildcard `If-Match` is valid for owned policy and diagnostic updates. The product-API association remains a bodyless PUT with an empty wire body, rather than a fabricated properties document.
- **The new policy expressions have no identified C# type or ordering defect:** `JTokenType.String`, the string cast, the Boolean return, storage and cast, and the LINQ calls are supported by Microsoft's policy-expression reference. Model and streaming refusals precede counting; missing product variables stop a different subscription scope before backend authentication. This is static and reference verification, not execution in APIM.
- **The ABAC addition is correct:** both the write/`@Request` and the delete/`@Resource` arms match Microsoft's "Constrain roles and principal types" example, with the permitted type restricted to `ServicePrincipal`. The Bicep assignment satisfies that filter. Both PowerShell blocks parsed without errors.
- **Shell control flow checked out:** existing, missing and forbidden budget cases, four preview and restore cases, and all 24 summary combinations passed using a fake CLI under `bash --noprofile --norc -eo pipefail`, with file sinks replaced by in-memory capture. The workflow lint and the strict documentation lint also passed: two workflows and 121 documents.

## New acceptance points that need a real run

Only additions introduced by this revision:

- The approved bootstrap must actually install the new principal-type condition, and Azure must accept the intended service-principal grant under it.
- The budget-read step must receive and retain the real budget's date across subsequent deployments, including its real not-found response on first creation.
- APIM must execute the new typed model and Boolean streaming branches as inspected. The tightened smoke test must also see real usage and the expected gateway-refusal format. Its large request is 36,000 words, 180,000 characters; that is not proof of tokenizer usage or of Azure's capacity estimate. It must cross the 30,000-token gateway allowance without first exhausting the 50,000-token backend capacity.
- After H2-14 is fixed, the new plan-driven skipping behaviour needs a real round trip: equivalent server-normalised objects should yield zero APIM PUTs on reapply, without skipping unfinished or failed provisioning.

The known failures above should be corrected offline, not deferred to that first deployment.
