# Learning — a decision record

**Status: built with fakes on 2026-11-09 and deployed with the app; no lesson exists yet. The claim that learning improves what Meternaut proposes is withdrawn: the first run of its check missed two thresholds that were written first, and the hold that the claim was about is off.** The rules of [the Foundry agents](06-foundry-agents.md) stand: no text of an estate or of a person reaches a model, every model call goes through the AI Gateway, and only the approver changes Azure.

## What is learned, from what

| From | What is kept | Table | Who reads it |
|---|---|---|---|
| The outcome of a closed request | One lesson for each plan: type, family, the stated confidence, the second AI's verdict, a few signals in buckets, the person's last word and reason, the predicted saving and the measured one | `mnlessons` | Code (the line of the decision brief, the hold); the Investigator, as counts |
| Microsoft's documentation | One claim: a kind from a closed list, the page, a quote of 20 to 200 characters that code found on that page | `mnclaims` | The Investigator; no decision of code |
| What the app's identity can see | One profile for each run, in words of a closed list | `mnprofiles` | The tool `commitments`; one sentence of the decision brief |

None holds the name of a person or of a resource, an address or a text of an estate, and no model reads a lesson as text. There is no screen to edit them: the owner removes a row, or turns a part off (`STUDY`, `LEARNING_HOLD`, the switches `all` and `investigation`).

## Outcome lessons

The loop's tick runs a sweep every fifth minute (`learning.sync`): it writes the lesson of every plan that ended, adds the saving that the verifier measured from the cost lines and, for a change on a resource that Meternaut did not plant, looks in the Activity Log for the resource made again within 28 days (a boomerang). Every render of the decision brief carries one line from the counts of a type and family: *Past cases like this: 3 of 4 approved; savings came in at 92 percent of the estimate.* Below three answered requests it says *no history yet*.

The calibration is a bucket correction, with no model and no curve. A stated confidence is in one of three bands (below 0.7, 0.7 to 0.85, 0.85 and up). With at least five labelled outcomes of the type and family in the band (approved, or declined as still needed or with a wrong figure; any other answer says nothing about the finding), the share approved is what the lessons support. The hold uses it one way only: a proposal at or above 0.7 whose supported share is below 0.7 becomes a finding that needs a person, with a first note by code. It never makes a finding stronger, never drops one, and the person still gets the request.

## The learning check

`tools/learning-check.py` replays closed requests in time order, offline and with no model, and decides each twice: with frozen memory (the stated confidence decides) and with updated memory (the lessons of requests that closed on an earlier day, through the `learning.hold` that the Watch calls). The later half is graded. The thresholds in `evaluation/learning-thresholds.json` were committed first, then the tool, then the replay set, then the first run. The set is 78 invented requests of seven kinds of resource over 155 days, written once and not changed after the run; the second table says what each kind shows.

<!-- learning-check:start -->
| Threshold, written first | Bar | First run | |
|---|---|---|---|
| Graded requests that say whether the finding was right | at least 20 | 32 of the 39 graded | met |
| Calibration: the Brier score of the deciding confidence | better by at least 0.02 | 0.206 with frozen memory and 0.190 with updated memory, better by 0.017 | **missed** |
| Proposals that people declined as wrong, held back for a person | at least 0.5 | 7 of the 9, 0.78 | met |
| Proposals that people approved, held back by mistake | at most 0.25 | 9 of the 23, 0.39 | **missed** |
| Proposals with too few outcomes in their band, decided as before | all | 47 of the 47 | met |

| Kind of resource, graded part | What the replay gives it | Declined held | Approved held |
|---|---|---|---|
| microsoft.compute/disks | right nine times in ten | 0 of 1 | 0 of 6 |
| microsoft.compute/snapshots | an unlucky start | 0 of 0 | 2 of 5 |
| microsoft.web/serverfarms | sure and mostly wrong | 3 of 3 | 2 of 2 |
| microsoft.sql/servers/databases | the bands tell apart | 3 of 3 | 1 of 4 |
| microsoft.storage/storageaccounts | people changed their minds | 1 of 1 | 4 of 4 |
| microsoft.network/publicipaddresses | few labelled outcomes | 0 of 1 | 0 of 1 |
| microsoft.cache/redis | too few answers | 0 of 0 | 0 of 1 |
<!-- learning-check:end -->

**What it says.** Updated memory holds back most of the proposals that people declined as wrong, and pays for it: 9 of the 23 that people approved were held too, 4 of them in the kind whose people changed their minds and 2 in the kind with an unlucky start. What was learned is not forgotten, so a hold lifts only as new approvals outweigh old declines; so too the calibration gain, 0.017, falls short of 0.02. Two ideas were tried afterwards on the same set as a what-if, not a run: holding only when the upper bound of the share approved is below 0.7 holds back 7 of the 23, and a window of the newest 5, 6, 8 or 10 outcomes holds back 9 or 10. Neither reaches 0.25, so neither is claimed as a fix.

**What follows** ([rule 14 (c)](../../AGENTS.md)). The claim is withdrawn, and the hold is off until the owner switches `LEARNING_HOLD` on. A second experiment needs new requests, because these have been seen, and thresholds written first. The lessons, the line of the decision brief and the recall tools stay on: they count and decide nothing. Not measured: real requests (the set is invented: the result shows how the mechanism behaves on these patterns, not how often real findings are over-confident), money, the Investigator's use of its tools, the claims of the Study and boomerangs.

## A hold that follows a change of mind

A lesson has no resource of its own, so a person who answered the same finding the other way later was counted twice. `learning.sync` now weighs the answers about one resource and one family against each other: the newest answer that says whether the finding was right is what the person thinks now. An older answer that says the opposite is released (`superseded`) and no longer counts for the calibration or for `recall_lessons`; one that the newest agrees with is kept. The count in the decision brief stays as it was. A changed resource looks like a changed mind. Built with fakes; the replay set has no such rows, so its numbers did not change.

## The check on real requests

Operations has the button "Download the answers" (role ops): one row for each closed request, in the row shape of the check, with a number for the resource and no name. `tools/learning-check.py --real --cases FILE` replays it against the same thresholds. Only the app can read the table. Built with fakes; no lesson exists yet to run it on.

## The Investigator's tools that recall

Three tools read our own store and nothing of the estate. `recall_lessons` gives counts and rates as typed values. `recall_knowledge` gives the claims of a type with their pages and quotes, as fetched data and never as an instruction. `recall_open_questions` gives up to 15 typed rows for resources whose earlier finding no person has decided: the handle, the type word, how many Watches saw it, the days since it was first seen and the confidence of the last judgement, with no text and no name of a person. The instructions say that the tools exist and what they return, never what to find. When the Investigator cites such a resource again the Watch judges it again at once, so that a finding that stayed "needs a person" with no figure comes back until it is decision-ready or dropped. The model is not forced to call a tool; a real run shows whether it does.

## The Study of documentation

Once a week (the timer `study-weekly`, Mondays at 04:30 UTC) the Scholar, a third agent in the Foundry project, reads Microsoft's public pages about the kinds of resource that the estate has, at most four kinds a run. It is off until `STUDY` is on, needs the Foundry project, stops when the switch `all` or `investigation` is pulled, and calls its model through the AI Gateway. Its one tool, `fetch_doc`, reads only Microsoft's own documentation and price pages (Learn's `azure`, `rest` and `lifecycle` folders), with every redirect checked and a page cut into windows of 4,500 characters.

A claim that passes the guard reaches the Investigator through `recall_knowledge`: text from outside the estate, the one exception to the typed values of [rule 30](../../AGENTS.md) (b), kept narrow by the guard and the data marking. The owner allows it, and the switch is a variable of the Hub ([below](#how-the-study-is-switched-on-and-run)): `STUDY` stays off until it says on.

A claim is kept only after a guard of code (`study.accept`): the type was asked for, the kind is on the closed list, the page is one that this run read, and the quote is plain words of 20 to 200 characters that the text of that page holds exactly. Anything else is thrown away and counted; at most four claims for a type and 16 a run. The kinds are in the input of a run, not in the instructions: nothing tells the Scholar what to find. A claim is current for 30 days and is read again after seven; a quote that is gone makes it stale. A run is held to 400,000 tokens: $2 to $3 a run and $9 to $13 a month of weekly runs at the price snapshot of 2026-10-31 ($5 per million input tokens, $30 output), a calculation and not a measurement. `tools/study-evals.py` replays the Scholar on invented pages against thresholds written first and grades it with the same guard; it has not run on Foundry.

## How the Study is switched on and run

Added 2026-11-16. The Study was built and nothing gave the app its switch, so the timer said `state: off` every Monday. Now one variable switches it and one Hub action runs it once.

**The switch.** The variable `STUDY` of the environment `hub` is `on` or `off` (`1`, `true`, `yes` and `0`, `false`, `no` read the same; not set is off). It is plain configuration with no identifier of the estate, so it is a variable and not a secret ([rule 18](../../AGENTS.md) (b)). `tools/environment-params.py` refuses any other word, without echoing it, and gives the cases file one bool, which the template hands to the app as the setting `STUDY`. The app has it after the next run of `cases`. The limits `STUDY_MAX_*` are not passed: the defaults of the code hold (four kinds, eight pages, 300 seconds, 400,000 tokens). The action `cases` refuses `on` while the Foundry project is not in Azure, because the app reads `STUDY` on with no project as a mistake in its settings.

**Running it once.** The action `study-run` is `cases-run` for the Study. The Operator, from inside the network, puts `{"job": "study", "requestId": ...}` in the private queue `cases-control` and reads the History of that request from Application Insights. It uses the container script and the tool of `cases-run` (`operator/run-tool.sh`, and the command `study` of `tools/cases-check.py`), so no new file goes to the Operator. The public log gets counts and plain words only: the state, the kinds of resource given to the Scholar and read about, the pages read, the claims kept and thrown away, the tokens, the seconds, and the notes of the run with every id, resource group and host name of the estate masked. The step fails when the Study ended `failed`, `held` or `off`, when it ran and read no page although a kind of resource waited, when the app refused the message, or when no line arrived in 20 minutes. Each failure says in words what to check. The app reports one more number for it: `study.finished` carries `pages`, and the note about refused reads carries the closed words of the page reader (`unavailable 3`), never an address.

**What must be true, and how the run shows it if it is not.**

| What must be true | If it is not |
|---|---|
| `STUDY` is on, and `cases` ran after it was set | The step says that `STUDY` is off in the app |
| The Foundry project is in Azure and the app's identity may use it | The step says that no Foundry project is set, or that the Scholar was not made |
| The Scholar's stored definition is the one in `agents.lock.json`, and its model (the Investigator's alias) answers through the AI Gateway | The step says that the Scholar was not made or gave no answer, and the note names the route; `agents-drift` shows a stored definition that differs |
| The app's network lets `learn.microsoft.com`, `azure.microsoft.com` and `prices.azure.com` through on port 443 (the landing zone's firewall and its DNS: nothing in Meternaut opens it, and the app's list of calls, `http.docs_calls`, is not widened) | The Scholar calls its tool and no page comes back: `Pages read: 0` and a note such as `unavailable 3`, and the step says that the documentation could not be reached from the app's network. The platform team decides |

**What is not proved.** Nothing here ran in Azure, on Foundry or on the Hub. Not known: that the Foundry service accepts the Scholar (it has never run there; the replay ran on invented pages), that the three hosts are reachable from the app's subnet, what a run costs, how many claims survive the guard on real pages, that a claim helps the Investigator, that the timer starts a run once the setting is on, and that the masking of the log holds against real telemetry (it was tested on invented lines). The first real run shows the first four: state `ran`, at least one kind given to the Scholar, at least one page read, and the tokens and seconds against their limits.

## The capability profile

What a finding can say depends on what the identity can see: without the right to list reservations, "this estate has none" is not known. Each investigation reads once the first page of the billing accounts, the reservation orders and the savings plan orders, one line of the price sheet of the first subscription and the quota ids that the list of subscriptions already gives. Each answer is one of four words: *visible*, *not visible with this access* (a 401 or 403, or an empty list, which holds only what the caller may see and is never "none"), *unavailable* or *unknown*. The profile is kept in `mnprofiles`. The tool `commitments` shows its words, so that no model reads an empty list as "none", and a finding about a commitment that does not fit the use carries one sentence of the decision brief: *This estate's reservations and savings plans are not visible with the current access, so no commitment advice.*

| What the profile finds | What it means |
|---|---|
| An `enterprise`, `customer` or `partner` agreement | Savings plans are offered. The orders are seen with the roles T1 to T3 ([access](03-access-and-onboarding.md#reads-at-the-tenant-which-no-role-at-a-subscription-gives)); Learn gives a partner no billing role for them, so only the two Azure roles at the tenant scope do |
| A `pay-as-you-go` agreement | Savings plans are not offered (Learn, "What are savings plans?"): the decision brief says so, and it is no matter of access |
| No billing account visible | The quota ids hint: `PayAsYouGo` is pay-as-you-go, `CSP` a partner, `EnterpriseAgreement` an enterprise agreement or the Azure plan of a customer agreement (the two cannot be told apart); anything else says nothing |

The price sheet is read with the Cost Management Reader that the Watch has, and an agreement may still refuse it. The three lists at the tenant need a person to grant a role, which `tools/access-requirements.py` neither checks nor gives; until then the profile says *not visible with this access*, never that there is no agreement.

## What would prove each part in Azure

| Part | The real call | What is read back |
|---|---|---|
| Lessons | A real request answered on the web page | A row in `mnlessons`; the line on the page |
| The probes | A Watch run, then again after T1 to T3 are given | A row in `mnprofiles`; *not visible* becomes *visible* |
| Open questions | A Watch run while earlier findings are undecided | A `recall_open_questions` call in the History |
| The Study | The Hub action `study-run` with `STUDY` on | The lines `study.started`, `study.claim` and `study.finished` of that request, and rows in `mnclaims` whose quotes are on their pages |
| The Scholar's replay | `tools/study-evals.py run` on the Operator | Its code graders against their thresholds |
| The check on real requests | Operations, "Download the answers", then `tools/learning-check.py --real` on the file | Its thresholds, again, before the hold is on |

## What is not built

The evaluators and the red team of the Foundry service for the Scholar: none means anything before it runs in Azure. The Hub action `study-run` is built and has not run. Also not built: a check of T1 to T3 by the access tool, and any proof from Azure: whether the Foundry service accepts the Scholar, whether the documentation can be reached from the app's network, and what a run really costs.
