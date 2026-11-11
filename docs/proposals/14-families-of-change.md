# Families of change: what an approval can do to Azure, and what stops it — a decision record

**What this document answers.** What a person's OK can change in Azure now that it is more than a delete: the six families of change, the two gates that every change passes, how the approved plan is the plan that runs, what happens when Azure takes minutes, what each family costs on planted waste, how a family is added, and what is not built. A change is still made by the approver, with the approver's own rights ([run as the approver](05-run-as-the-approver.md)), and only on waste that Meternaut planted itself.

## The decision

Until 2026-11-08 an approval could do two things, both written into the runner: delete an unattached managed disk and delete an unassigned public IP address. They are now two of six **families**, kept in a registry in `src/case-functions/cases/families/`. A family is one kind of change on one or more kinds of resource, with its own plan, re-check, call, check afterwards and tests. The runner and the approval loop know the interface and nothing of any one family, and the decision brief reads each family's words (`words.py`, which holds no way to reach Azure), so no page, letter or card has a case of its own ([the decision brief](09-the-decision-brief.md)). The first two keep their calls and their words, except for what happens after the change (below).

| Family | What it changes | The call and its api-version | Read again right before it acts | Undo | The approver's role must allow |
|---|---|---|---|---|---|
| `delete-disk` | Deletes an unattached managed disk | `DELETE` the disk, 2024-03-02 | Still unattached | None: the data is lost | `Microsoft.Compute/disks/delete` |
| `delete-public-ip` | Deletes an unassigned public IP address | `DELETE` the address, 2024-05-01 | Still unassigned | None | `Microsoft.Network/publicIPAddresses/delete` |
| `stop-vm` | Stops a machine and releases its compute (deallocate); disks and addresses keep billing | `POST` the machine's `deallocate`, 2026-04-01 | Running or stopped, last operation finished, no scale set or platform manages it | Start it again | `Microsoft.Compute/virtualMachines/deallocate/action` |
| `resize-vm` | Changes the size to the largest smaller one of the series; a running machine restarts | `PATCH` the machine, `hardwareProfile.vmSize`, 2026-04-01 | Same size, a state a resize is made in, the new size still on Azure's list for this machine, and quota for a larger one | Resize back | `Microsoft.Compute/virtualMachines/write` |
| `change-disk-tier` | One step down: Premium SSD to Standard SSD, zone-redundant likewise, Standard SSD to Standard HDD only above 16 GiB (a Standard HDD is billed from 32 GiB and would cost more) | `PATCH` the disk, `sku.name`, 2026-03-02 | Same tier; unattached, or on a machine of Meternaut's own that is stopped and released | Change back (twice a day at most) | `Microsoft.Compute/disks/write` |
| `delete-idle-resource` | Deletes a snapshot, network interface, NAT gateway, load balancer or private endpoint that nothing uses | `DELETE`, 2026-03-02 for a snapshot, 2026-01-01 for the others | Each kind has its own reader of "nothing uses it" (a private endpoint whose connections are all Disconnected) | None | The `delete` action of the kind |

Every family also re-reads, with the approver's token, the tag, the planted list, the resource group, the management locks (an unread lock counts as on) and a person's do-not-touch note. Each api-version is the one that the REST reference of the call shows (Microsoft Learn, read on 2026-11-08): [Deallocate](https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/deallocate), [Update](https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/update), [Disks Update](https://learn.microsoft.com/en-us/rest/api/compute/disks/update), [converting disk types](https://learn.microsoft.com/en-us/azure/virtual-machines/disks-convert-types). `calls.py` is the one module that names a method that writes: ten calls, and the lists of the clients are built from it, so a call that is not there is refused before it is sent. No machine is ever deleted.

## Two gates, pinned by tests

1. **The scope.** `CHANGE_SCOPES` lists Meternaut's own resource groups, each as `<subscription id>/<resource group>`, separated by commas. It replaces `CHANGE_RESOURCE_GROUP` and `CHANGE_SUBSCRIPTION_ID`, which an app deployed before still has and which are read as one group only while the list is absent. The template gives it exactly the group where Meternaut plants waste of its own. Reading more subscriptions does not widen it.
2. **The planted gate.** A resource is changed only when it carries the tag `meternaut-planted` and is on the planted list: a type and a name of the shape `planted-<kind>-<id>` that [`planted.bicep`](../../environment/cases/planted.bicep) makes (a test holds the list and the template together). A tag alone proves nothing: anybody who may write tags in the group could add one. `CHANGE_REQUIRES_PLANTED_TAG` in `gates.py` is `True` and is not a setting: no variable, deployment, agent or person on the web page reaches it, only the owner may change that line, and a test pins the value and the comment.

A third gate is a person's do-not-touch note. Each gate is checked when the plan is made, again right before the change with the approver's token, and in the runner before any call.

## A plan is written by code, and what is approved is what runs

A model's recommendation (delete or change) only selects among the families that match the resource's type. Code reads the resource with the reader's token, in the scope groups only, and writes the whole plan: title, change, risk, undo, target (a size, a tier) and the facts that are read again. A model supplies no parameter, and text from the estate is never put in a plan: a name is cut to one line and must fit the planted shape. The size is the largest smaller one of the series in Azure's own list for that machine; the tier is a step of a table. A finding that no family can plan gets the plan of the family `advise`, which changes nothing.

The plan carries a digest: SHA-256 over every field except its state, the digest and its code, whose eight characters are the start of it. The sign-in to Azure binds the digest into its round-trip state (on the server, one use, bound to the person and the plan) and compares it when the person returns; the runner compares it again, with the digest recorded in the approval, before any call. A plan that changed in any field after it was approved is refused, and nothing changes.

## When Azure takes minutes

A stop or a resize answers 200 or 202. For a 202 the runner follows `Azure-AsyncOperation`, else `Location` ([asynchronous operations](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/async-operations)), waits as Azure asks but two to five seconds, and looks at most six times. A status that the approver's token may not read is not a failure: the resource is read instead. A resize is done only when the provisioning state is `Succeeded` and the size is the new one, because a failed resize still shows the size that was asked for. A write is made once and never retried.

If the end is not there yet, the action is `running`, the plan is used, and the page says that the change is being made. The timer then reads the resource with the reader's token, which holds no write, until Azure shows it: done (confirmed by the later check), failed, or unknown after an hour, which makes no second try. A new try is a new approval.

## After the change

Two checks follow a change. The family's own read says that it took effect. The cost lines then say whether it saved anything. They are read for whole days only, from the day after the change to a day that ended at least a day ago, and once a day: Cost Management is 8 to 72 hours late ([Learn](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data)). A resource with no line yet is "no data yet", never a cost of zero. A stop or a delete is confirmed when no cost is left, a resize or a change of tier only by a lower daily figure. After seven days without a figure the record says so and stops asking.

An approval that finds the resource as the plan wants it, or gone, writes nothing: it says "Nothing was changed", is not checked by cost lines and claims no saving. A plan left approved because the app stopped before it wrote is closed as failed after two days, and its resource is free again.

## What each family costs on planted waste

Prices are Sweden Central's, for Linux, from the public Retail Prices API, read on 2026-11-08, in US dollars an hour.

| Family | Proved on | While it stands | After the change |
|---|---|---|---|
| `delete-disk` | `planted-disk-<id>`, an unattached Premium SSD of 4 GiB | 0.0011 | 0 |
| `change-disk-tier` | the same kind of disk, from a second planting | 0.0011 | 0.0004 (Standard SSD) |
| `delete-public-ip` | `planted-ip-<id>` (`--plant-public-ip`) | 0.0050 | 0 |
| `stop-vm` | `planted-vm-<id>`, a Standard_B4als_v2 (`--plant-vm`) | 0.138, and 0.0004 for its OS disk | 0.0004 |
| `resize-vm` | the same machine | 0.138 | 0.0389 (Standard_B2als_v2) |
| `delete-idle-resource` | not proved in Azure | 0 | 0 |

The Hub action `plant` with the input `plant_vm` plants the machine with its network interface in the subnet `snet-pe` and an empty 4 GiB OS disk: no public IP address, no account, no key. The action deletes nothing, and a full planting costs about 0.14 an hour while the machine runs. A Standard_B4als_v2 because the cheapest size has no smaller one in its series, and because the older Standard_B2s is not available to the pilot's subscription in Sweden Central (the first real planting, on 2026-11-09, was refused for it; prices of this size were read on that day). The OS disk is attached empty (`createOption: Attach`, no `osProfile`), so Azure should show the machine running with nothing on it: the template compiles, and that has not been tried. The planted network interface belongs to the machine, so it is not idle, and nothing plants a snapshot, a NAT gateway, a load balancer or a private endpoint: `delete-idle-resource` is tested on fakes and cannot change anything real yet.

## What the first real approvals showed (2026-11-09)

The owner approved the first two changes by hand, at 12:06 and 12:07 UTC. **`delete-disk` ran**: from the approval to the end of the action took three seconds, and Azure no longer lists `planted-disk-r298`. It cannot be undone, and nothing asks a second time before a delete, which is a gap (the owner had chosen the wrong action). **`stop-vm` was stopped by its own re-check**: "the machine is not running or stopped any more (its power state is not shown)", though the machine was there and `PowerState/stopped`. The re-check read the machine without its instance view, where Azure puts the power state, and a read that shows none is never a good one, so it refused and nothing was changed. The plan and the check afterwards asked for the instance view; the re-check did not, and the fake of Azure in the tests answered every read with the power state, which Azure does not. Both machine families had it. Each now names the query of its re-read (`read_query`), the fake shows the state only when it is asked for (63 tests fail without the fix), and a case whose change failed or was stopped is taken up again by the next Watch and asked about again, because its request is closed and nothing was changed. The fix is deployed (local run 314), and the next Watch (run 315) took the stopped machine up again and wrote a new `stop-vm` request for it, which the start page lists and which the owner approved himself the same afternoon (15:07 UTC, found done by run 316): `stop-vm` ran to the end, and the later check confirmed that the machine is stopped and released. `resize-vm` has not run in Azure yet.

## How a family is added

The checklist of [rule 26 (a)](../../AGENTS.md): a class in `families/` with its kinds, plan, re-check, write and check afterwards; its call in `WRITES` with the api-version that Learn shows; its words in `words.py`; an entry in the registry; for a resource that Meternaut changes, a planting and an entry on the planted list; and tests for the scope, the planted gate, each re-check that stops, the call with its body, a long operation and every render of the decision brief. The registry refuses to load when a family has no words, and a test fails when a family has no case among the renders.

## What is not built

- **Purchases and the scale-down of logs or networks** are not families yet: they need prices and another re-check. Nothing here buys or commits anything.
- **The price list is not read.** `resize-vm` shows a Scenario saving (the cost lines scaled by the share of processors that is left), and `change-disk-tier` claims no figure.
- **A disk attached to a machine** gets the managed guard when the case is judged, so only unattached disks are planned in practice.
- **No letter for a result that stays unknown**, as before: the page and the History say so.
- **Nothing has run in Azure** ([rule 32](../../AGENTS.md)): it is tested against fakes of Azure on the owner's machine, and a family is proved only when the planting above has run.

## What none of this stops

An approver with broad rights can do anything in Azure outside Meternaut. A planted machine that somebody put a workload on is stopped when it is approved, and the plan says that what runs on it stops. Between the last re-check and the write is a short window that no check closes. A person who approves a bad plan approves it. What the gates do is smaller and firm: with the owner's line unchanged, Meternaut cannot change a resource that it did not plant, in a group that is not its own, or on a plan that is not the one that was approved.
