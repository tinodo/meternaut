# Families of change: what an approval can do to Azure, and what stops it — a decision record

**What this document answers.** What a person's OK can change in Azure now that it is more than a delete: the six families of change, the two gates that every change passes, how the plan that is approved is the plan that runs, what happens when Azure takes minutes to finish, how a family is added, and what is not built. A change is still made by the approver, with the approver's own rights ([run as the approver](05-run-as-the-approver.md)), and only on waste that Meternaut planted itself.

## The decision

Until 2026-11-08 an approval could do two things: delete an unattached managed disk and delete an unassigned public IP address. Both sat inside the runner and the approval code. They are now two of six **families**, kept in a registry in `src/case-functions/cases/families/`. A family is one kind of change on one or more kinds of resource, with its own plan, its own re-check, its own call, its own check afterwards and its own tests. The runner and the approval loop know the interface and nothing of any one family, and the decision brief reads each family's words (`words.py`, which holds no way to reach Azure), so no page, letter or card has a case of its own for a family ([the decision brief](09-the-decision-brief.md)). The two first families behave as they did: tests hold their old texts word for word.

| Family | What it changes | The call and its api-version | Read again right before it acts | Undo | The approver's role must allow |
|---|---|---|---|---|---|
| `delete-disk` | Deletes an unattached managed disk | `DELETE` the disk, 2024-03-02 | Still unattached | None: the data is lost | `Microsoft.Compute/disks/delete` |
| `delete-public-ip` | Deletes an unassigned public IP address | `DELETE` the address, 2024-05-01 | Still unassigned | None: the address is released | `Microsoft.Network/publicIPAddresses/delete` |
| `stop-vm` | Stops a machine and releases its compute (deallocate): disks and public IP addresses keep billing | `POST` the machine's `deallocate`, 2026-04-01 | Running or stopped, last operation finished, no scale set or platform manages it | Start it again | `Microsoft.Compute/virtualMachines/deallocate/action` |
| `resize-vm` | Changes the size of a machine to the largest smaller size of its series; a running machine restarts | `PATCH` the machine, body `hardwareProfile.vmSize`, 2026-04-01 | Same size as planned, a state a resize is made in, the new size still on the list that Azure gives for this machine, no own vCPU settings, and the quota for a larger one | Resize back | `Microsoft.Compute/virtualMachines/write` |
| `change-disk-tier` | Changes the tier of a disk one step down: Premium SSD to Standard SSD, Standard SSD to Standard HDD, zone-redundant Premium SSD to zone-redundant Standard SSD | `PATCH` the disk, body `sku.name`, 2026-03-02 | Same tier as planned; unattached, or attached to a machine of Meternaut's own that is stopped and released | Change back (twice a day at most) | `Microsoft.Compute/disks/write` |
| `delete-idle-resource` | Deletes a snapshot, a network interface, a NAT gateway, a load balancer or a private endpoint, when nothing uses it | `DELETE` the resource, 2026-03-02 for a snapshot and 2026-01-01 for the others | Each kind has its own reader of "nothing uses it" (for example a private endpoint whose connections are all Disconnected) | None | The `delete` action of the kind |

Every family also re-reads, with the approver's token, the tag, the planted list, the resource group, the management locks (an unread lock counts as on) and a person's do-not-touch note. Each api-version is the one that the REST reference of the call shows (Microsoft Learn, read on 2026-11-08): [Deallocate](https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/deallocate), [Update](https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/update), [Disks Update](https://learn.microsoft.com/en-us/rest/api/compute/disks/update) and [converting disk types](https://learn.microsoft.com/en-us/azure/virtual-machines/disks-convert-types). `calls.py` is the one module that names a method that writes: ten calls, and the lists of the clients are built from it, so a call that is not there is refused before it is sent. No machine is ever deleted, and the one `POST` is the deallocate.

## Two gates, pinned by tests

1. **The scope.** `CHANGE_SCOPES` lists Meternaut's own resource groups, each as `<subscription id>/<resource group>`, separated by commas. It replaces `CHANGE_RESOURCE_GROUP` and `CHANGE_SUBSCRIPTION_ID`, which an app deployed before still has and which are read as the same one group only while the new list is absent. The template gives it exactly the one group where Meternaut plants waste of its own. Reading more subscriptions does not widen it.
2. **The planted gate.** A resource is changed only when it carries the tag `meternaut-planted` and is on the planted list: a type and a name of the shape `planted-<kind>-<id>` that [`planted.bicep`](../../environment/cases/planted.bicep) makes. A tag alone proves nothing, since anybody who may write tags in the group could add one. `CHANGE_REQUIRES_PLANTED_TAG` in `gates.py` is `True` and is not a setting: no variable, deployment, agent or person on the web page reaches it, only the owner may change that line, and a test pins the value and the comment.

A third gate is a person's do-not-touch note. Each gate is checked at three places: when the plan is made, again right before the change with the approver's token, and in the runner before any call. A kind that the planting does not make has no place on the list, so no family can change one: the closed list of `delete-idle-resource` names five kinds, and today only a planted network interface can pass.

## A plan is written by code, and what is approved is what runs

A model's recommendation (delete or change) only selects among the families that match the type of the resource. Code reads the resource with the reader's token, in the scope groups only, and writes the whole plan: the title, the change, what could go wrong, the undo, the target (a size, a tier) and the facts that are read again. A model supplies no parameter, and text from the estate is never put in a plan: a name is cut to one line and must fit the planted shape. The size is the largest smaller one of the same series in Azure's own list for that machine; the tier is one step of a table. A finding that no family can plan gets the plan of the family `advise`, which changes nothing.

The plan carries a digest: SHA-256 over every field except its state, the digest and its code. The eight characters that a person sees are the start of it. The sign-in to Azure binds the digest into the state of its round trip (on the server, one use, bound to the person and the plan) and compares it when the person returns. The runner compares it again, with the digest recorded in the approval, before it makes a call. A plan that changed in any field after it was approved is refused and nothing is changed.

## When Azure takes minutes

A stop or a resize answers 200 or 202. For a 202 the runner follows the header `Azure-AsyncOperation`, else `Location` ([asynchronous operations](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/async-operations)), waits as Azure asks but between two and five seconds, and looks at most six times. A status that the approver's token may not read is not a failure: the resource is read instead, and a resize counts as done only when its provisioning state is `Succeeded` and its size is the new one (a failed resize still shows the size that was asked for). A write is made once and never retried.

If the end is not there yet, the action is `running`, the plan is used, and the person's page says that the change is being made. The timer then reads the resource with the reader's token, which holds no write, until Azure shows it: done (confirmed by the later check), failed, or unknown after an hour, which says so and makes no second try. A new try is a new approval. The cost lines confirm a saving later, as for a delete: a family that lowers a cost without ending it compares the daily rate after with the rate before.

## How a family is added

The checklist of [rule 26 (a)](../../AGENTS.md): a class in `families/` with its kinds, its plan, its re-check, its write and its check afterwards; its call in `WRITES` with the api-version that Learn shows; its words in `words.py` (change, what is read again, risk, undo); an entry in the registry; for a resource that Meternaut changes, a template that plants it and an entry on the planted list, which a test holds against the template; and tests for the scope, the planted gate, each re-check that stops, the call with its body and its api-version, a long operation, and every render of the decision brief. The registry refuses to load when a family has no words, and a test fails when a family of the registry has no case among those renders.

## What is not built

- **Purchases and the scale-down of logs or networks** are not families yet: they need prices and a different re-check. Nothing here buys or commits anything.
- **The price list is not read.** `resize-vm` shows a Scenario saving (the cost lines scaled by the share of processors that is left), and `change-disk-tier` claims no figure.
- **A disk attached to a machine** gets the managed guard when the case is judged, so in practice only unattached disks are planned. The check for a stopped machine of Meternaut's own is there for when that guard changes.
- **A snapshot, a NAT gateway, a load balancer and a private endpoint** have a family and no planted resource, so nothing proves them against Azure yet; the fakes of the tests do.
- **No letter for a result that stays unknown** (as before): the page and the History say so.
- **Nothing here has run in Azure.** It is built and tested against fakes of Azure on the owner's machine ([rule 32](../../AGENTS.md)): what each family does to a real resource is proved by the planting described next, and until it has run there, it is not proved.

## What none of this stops

An approver whose own rights are broad can do anything in Azure outside Meternaut. A planted machine that somebody put a workload on is stopped when it is approved, and the plan says that what runs on it stops. Between the last re-check and the write is a short window that no check closes. A person who approves a bad plan approves it. What the gates do is smaller and firm: with the owner's line unchanged, Meternaut cannot change a resource that it did not plant, in a group that is not its own, or on a plan that is not the one that was approved.
