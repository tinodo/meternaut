# The investigation toolbox — a decision record

**Status: ordered by the owner on 2026-11-08 ("build the entire thing"), built the same day, with fakes for every call. Not yet run in Azure: nothing on this page about the new tools was seen in a real run, and a claim that rests on Microsoft Learn alone says so.** This page records what the Investigator's read-only tools gained, why its reads were slow, and what each tool does not tell. It builds on [the Foundry agents](06-foundry-agents.md) and leaves their rules as they are: the tools only read, give typed values and handles instead of names, and no text from the estate reaches a model.

## The problem

On 2026-11-08 the Investigator found seven things and could analyse none of them: its tools showed no volume, no readers and no deployments. A run also ran out of tool time after about 17 calls: ten subscriptions at 45 seconds a call.

## Faster reads

Measured on 2026-11-08 on the pilot subscription (about 400 resources, read only, with the app's own client code): Resource Graph answers in 0.5 to 1.4 seconds. A Cost Management query for the cost of every resource by service over 30 days takes 6 to 16 seconds cold and 1.6 seconds warm. A second query within seconds gets HTTP 429 with a wait of 2 to 21 seconds, **unless the call carries the header `ClientType`**: with it two queries in a row answered 200 in 2 and 5 seconds. That header is on no Microsoft Learn REST page; it is known from [a Microsoft Q&A answer](https://learn.microsoft.com/answers/a/8268839) and [an issue of the REST API specs](https://github.com/Azure/azure-rest-api-specs/issues/24407), so it is a bet: if Azure ignores it, nothing breaks and the 429 handling stays. The documented limits are 12 query units in 10 seconds, 60 a minute and 600 an hour for a tenant, about one unit for each month of data ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/manage-automation)).

| | Before | After |
|---|---|---|
| The count of resources by type, for N subscriptions | N queries of Resource Graph, one after the other | one query for all of them |
| The cost lines of a subscription | read twice a run (the Watch's totals, the tools' lines), each cold | read once, shared by both; the Watch's totals are added up from the same lines |
| Many subscriptions in one call | one after the other, cut at 45 seconds (about 3 to 4 of 10) | four at a time; what is not reached is counted and read by the next call |
| Rows of a listing | cost read for one subscription at a time | the subscriptions that have the type are read together |

Simulated, not measured on ten subscriptions: the real code of both versions against a fake estate with the measured latencies (1 second for Resource Graph, 10 for a cold cost read, all scaled by 1/100). Ten subscriptions: before, the first call read 4 of them (53 s, over the cap of 45) and all ten took three calls and 135 s, with 10 queries of Resource Graph; after, one call read all ten in 47 s (30 s is the ideal, three rounds of four; the rest is thread overhead on a loaded machine), with one query, and in 14 s when the Watch had read the cost lines first. Three subscriptions: 41 s, then 22 s. `test_toolbox_speed.py` proves the call counts and the overlap with fakes. Not done: a read ahead in a second thread (the Foundry client swaps its transport during a call, so a second thread is unsafe) and a cache of whole answers (the data is cached instead).

## The new tools

All are read only, answers are at most 6,000 characters, and every call is on the app's list and a line of [the access file](../../environment/access-requirements.json).

| Tool | Reads | Role |
|---|---|---|
| `data_volume` | what a workspace takes in, by table and day for up to 30 days: its settings and tables (`GET`, 2026-03-01) and its `Usage` records through the query API (`POST https://api.loganalytics.azure.com/v1/workspaces/{id}/query`) | Reader |
| `data_readers` | how many rules (Resource Graph), saved searches, workbooks (2023-06-01) and Sentinel rules (2025-09-01) name each table, and the runs in the query-audit table when it is on | Reader |
| `data_writers` | the data collection rules that send to a workspace (Resource Graph); for one table on the Analytics plan, the resources that wrote most of it on the last day; for any other resource its diagnostic settings (2021-05-01-preview) | Reader |
| `children` | the deployments of an AI services account (2026-09-01; Resource Graph does not list them) as handles with model, version, SKU, capacity, rate limits | Reader |
| `metric_split` | one metric split by one dimension (the metrics read, `$filter=<dimension> eq '*'`, `top`) | Reader |
| `commitments` | cost by pricing model and kind of charge (amortized) and the platform's savings plan (2026-06-01) and reservation (2024-08-01) recommendations | Cost Management Reader |
| `cost_history` | one resource or one type by day for 7 to 90 days, actual or amortized | Cost Management Reader |

`list_resources` and `describe` carry a `reads` field that names the deeper tools of a type, so no description names a kind of resource. A table that the platform made is named; any other is a handle (`t1`), a dimension value that is not a part of the resource is a number or a label, and every text of the estate is counted by code and never shown. Sizes in the properties of gateways and hubs (units, bandwidth, capacity) are shown now: four generic suffixes (`Unit`, `Units`, `Mbps`, `Gbps`) and one exact path were added.

**What the three data tools keep.** Besides the numbers that the Investigator may cite, the record that code checks citations against holds the whole volume of the workspace for the days asked, the kinds of resource of the largest writers of a table on the last closed day (three at most, the largest first), and, for a person's page only, what each table handle stands for. `cases/unread.py` reads that whole record, not only the entries that were cited, to find the kinds of data that nothing reads and to work out the figure ([the decision brief](09-the-decision-brief.md)). The names behind the handles never reach a model.

**Owner hints** are a function, not a tool: `cases/ownership.py`, for the human brief only. The tags of a closed set (owner, contact, team, cost centre, project, environment, created by, manager; at most six, 80 characters each, cleaned) and, from the Activity Log (90 days), who last changed the resource and, when the window shows it, who made it. The orchestrator calls `OwnerReader.hints(resource_id, tags)` once for each case, in `investigate.py::_open_case`; nothing is wired yet.

## What each tool does not tell

- **Volume** is what is charged for, hour by hour from the `Usage` table; it says nothing about what the data is for and shows no record.
- **Readers** count a table whose name a text holds. A column that has the name of a table counts too, a text that scans every table names none (counted apart, and added to the number that can be cited), a workbook that takes its workspace from a parameter is not counted, and the audit table holds only what was run while the setting was on (the 300 most run texts are read). Meternaut's own queries carry a marker comment that the count leaves out; whether Azure keeps comments in the audit table is not verified. A kind of data is called unread only when every source was read and every count is zero: a count that could not be made is unknown, so the kind stays in the whole volume and out of the unread.
- **Writers** by table are read only for the Analytics plan: a read of any other plan is charged by what it scans. Diagnostic settings are read one resource at a time, so no tool lists every resource that sends to a workspace.
- **Children** have no cost of their own: Cost Management bills the account.
- **Split** shows at most the number of values asked for and says when it was reached; the platform does not say in which order it cuts.
- **Commitments** do not say how much of a commitment is used: that is read at a billing scope or at the reservation, which no role of this file gives. The lists of reservation orders and savings plan orders are not read: a `200` with an empty list cannot be told from "no right".
- **Cost history** ends on the last closed day; amounts are in US dollars only.

## Access at each level (rule 12)

No new role. Reader already holds `*/read`, which includes reading the data of a workspace ([Learn](https://learn.microsoft.com/azure/azure-monitor/logs/manage-access)): Meternaut asks only for volumes and counts, with queries of fixed text that code made, and a test keeps text of the estate out of them. A workspace set to refuse that read (a protected table or the access mode that needs a data action) answers 403, and the tool says "not visible with this access", never "none". Cost Management Reader holds `Microsoft.CostManagement/*/read` and `Microsoft.Consumption/*/read`; without R2 the cost tools say so. Whether R2 alone shows the recommendations of an enterprise or a customer agreement was not proved: with the owner's rights both lists answered 200 and empty.

## Not verified

The query API of the pilot workspace resolved to a private address that this workstation cannot reach, so its answer shapes come from Learn only. Every call of the table above, with the audit queries, must be run once from the app's network, and the shape of each answer compared with the tests' fakes.
