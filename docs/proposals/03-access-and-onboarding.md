# Access and onboarding — the requirements

**Status: written on 2026-11-05, after the first cases ran on the real estate. Meternaut holds no write right: every grant below only reads, and a change to Azure is made with the token of the person who approves it. The installer in this page is built; the pipeline is not.** This page says what Meternaut needs granted outside its own resource group, who must grant it, why a pipeline cannot make the first grant on its own, and what an installer or a pipeline has to do. The design's [onboarding steps](../design/09-delivery-and-operations.md#9-onboarding-an-estate) describe the finished system; this page is what is true and built today. The changelog says what was done and checked.

## The problem

- The deployment workflow's identity may change only the project's own resource group. It holds no right in the subscriptions that Meternaut reads or in the gateway's, and it must not get one ([rule 18](../../AGENTS.md)).
- The workflow makes the identities that the apps run as: one for the usage recording and one for the first cases. Those identities need rights in other places, and only a person who may assign roles there can give them.
- Until now a person did that by hand, once for each identity, on the owner's written word, and reported it at once. The commands are in [the bootstrap page](../../environment/BOOTSTRAP.md).
- That does not scale to a second subscription, a second estate or another organisation. So the grants are written down as data, in [`environment/access-requirements.json`](../../environment/access-requirements.json), and a tool reads them: [`tools/access-requirements.py`](../../tools/access-requirements.py).

## What must be granted

One line is one role of one identity at one place. The table is printed by `python tools/access-requirements.py markdown`, and a test fails when this page and the file differ. Every line only reads: Meternaut holds no write right, and [the next section](#a-change-is-made-as-the-person-who-approves-it) says how a change is made.

<!-- access-requirements:start -->
| # | Identity | Role | Where | What it is for |
|---|---|---|---|---|
| R1 | `id-meternaut-cases` | Reader | Each subscription that the Watch reads (the app setting SCOPE_SUBSCRIPTIONS), or a management group above them | Reads the resources, their tags and management locks, Azure Advisor's cost recommendations, the platform metrics that Azure Monitor keeps for a resource and the pricing settings of the Microsoft Defender for Cloud plans: the detectors, the guards and the read-only tools of the investigator. It also reads a managed disk or a public IP address of the project's own resource group when the timer checks that a deleted resource is gone. The role reads and changes nothing |
| R2 | `id-meternaut-cases` | Cost Management Reader | Each subscription that the Watch reads (the app setting SCOPE_SUBSCRIPTIONS), or a management group above them | Reads the cost lines of every resource for the last 30 days, so that every figure is Cost Management's and never a model's |
| R3 | `id-meternaut-cases` | Meternaut gateway key reader (custom role) | The one subscription of the gateway's access product that the Watch uses, below the API Management instance | Reads the one key of the gateway's access product at the start of each run, because the gateway always asks for it. The role allows that read and nothing else of the gateway (the one remaining key: AGENTS.md rule 23) |
| R4 | `id-meternaut-usage` | Monitoring Reader | The gateway's Application Insights component | Reads the gateway's Application Insights component, where the gateway records the token metrics of every call |
| R5 | `id-meternaut-usage` | Meternaut usage reader (custom role) | The central workspace that the component writes to | Reads one table (AppMetrics) of the central workspace. The component is workspace-based and the workspace asks for workspace permissions, so the role on the component alone returns no rows |
<!-- access-requirements:end -->

What the roles allow, read from Azure on 2026-11-05:

- **Reader** is `*/read` and nothing else. **Cost Management Reader** reads cost, billing periods, Advisor recommendations and management groups, and, as the built-in role has it, holds `Microsoft.Support/*` (support requests). **Monitoring Reader** is `*/read`, a workspace search and `Microsoft.Support/*`.
- **The two custom roles** hold three actions (usage reader, all reads of one table) and two (key reader: read the access product's subscription, and read its key). Each is defined for one resource group only. The key reader is assigned on one resource: the one subscription of the access product.
- **Which call needs which grant.** The Watch and the timer's checks make eleven kinds of call outside the app's own store, its mailbox and the sign-in, and the file names ten of them. The Watch makes nine: Resource Graph queries, Advisor reads, management lock lists, the platform metrics and their definitions, and the pricing settings of the Defender plans need R1; the Cost Management query needs R2; the key read needs R3; the model call through the gateway needs the key and no Azure role. The timer's checks add two reads in the project's own resource group, of a managed disk and of a public IP address, to see that a deleted resource is gone (its list holds the lock read too, the same kind as the Watch's). They need R1, so R1 has to cover the project's subscription; it does when the estate is the project's subscription, which is the installer's default. The calls of the investigation to its own Foundry project (its agents and conversations) need no line of this file: the app's identity holds *Foundry User* on that project, which the template assigns inside the project's own resource group ([the Foundry agents](06-foundry-agents.md)).
- **The calls are checked against the file.** Tests compare the Watch's list of allowed calls and the timer's list with the file, in both directions, so a new call cannot ship without a requirement and the file lists no call that the app does not make. Two further checks fail if the Watch's list holds anything but reads, queries, the key read and the model call, or if the timer's list holds anything but reads.
- **No write.** The file holds no role that changes Azure and no identity that does. A test fails if any custom role gets an action that is not a read (the key read is the one named exception), a wildcard, a write or a delete, if a role is marked as one that changes Azure, or if the file lists an identity other than the two that read. The Activity Log of both subscriptions shows one operation by the cases identity during the first run on the real estate: the key read. No write. What the apps write in their own resource group (their own store, with the roles that the deployment gives them) and the letters that they send as the one shared mailbox are not rights over anything of the customer's, and are not in this file.

## A change is made as the person who approves it

Meternaut finds waste, judges it and, for the one kind of resource that it plants itself, proposes a change. It makes no change with a right of its own. When a person approves a plan, the console sends the person to Microsoft Entra to sign in to Azure Resource Manager, and the one change is made with that person's own token. Azure checks that person's rights, and the Activity Log is expected to show the person as the caller. The decision and the options that were compared are in [run as the approver](05-run-as-the-approver.md).

- **The sign-in.** The OAuth 2.0 authorization code flow with PKCE, with the delegated scope `https://management.azure.com/user_impersonation` and the OpenID Connect scopes `openid` and `profile` (`profile` is needed for the `oid` claim, which names the person who signed in). The consent that the platform's own sign-in already uses (`User.Read`) covers the two OpenID Connect scopes, so no permission is added to the file for them. No refresh token is requested, so nothing can use the permission after the person has left.
- **The credential.** The console redeems the code with the app registration's federated credential: the managed identity `id-meternaut-console-auth` presents a token for `api://AzureADTokenExchange` as the client assertion. There is no secret and no certificate ([rule 23](../../AGENTS.md)). The app registration is a confidential client: public client flows are off (`isFallbackPublicClient` is false, E4 below), so a sign-in code can be redeemed only with that credential and is worth nothing to anybody else.
- **The token.** It is used for one change, kept in memory for that request, and never stored or logged.
- **The rights.** What the change may do is what the person may do: a person who may not delete the resource cannot make Azure delete it by approving.

**Why.** No customer should give a tool a standing right to write to its resources: a right that is held between uses can be used at any time, by a fault in the tool or by anyone who takes over its identity. The Well-Architected Framework's security guidance on identity and access management asks for access that is limited to what is needed ([SE:05](https://learn.microsoft.com/azure/well-architected/security/identity-access)), and the Microsoft cloud security benchmark asks to avoid standing privileged access ([PA-2](https://learn.microsoft.com/security/benchmark/azure/mcsb-v2-privileged-access)). A delegated sign-in follows both: the standing rights of Meternaut over a customer's resources are the reads in the table above, and a write exists only while the person who approved it is present, and only with that person's rights.

**What Microsoft Entra needs for it.** The console's one app registration, "Meternaut console", carries this sign-in next to the platform's own sign-in of the console's pages. `tools/entra-setup.py` reads and makes all four requirements, and `check` reports each of them. The tool adds and never removes: a redirect address or a permission that somebody else added to the app registration stays. It sends back every address and permission that is there together with what is missing, reads the app registration again just before it writes, and shows what it leaves alone as a note, never as a difference. The one thing that it turns off is public client flows (E4), and only when they are on; it sends nothing else of the app registration with that.

| # | Requirement | What it is | Who gives it |
|---|---|---|---|
| E1 | The delegated permission `user_impersonation` of Azure Service Management, asked for by the app registration | Resource application id `797f4846-ba00-4fd7-ba43-dac1f8f63013`, delegated permission id `41094075-9dad-400e-a0bd-54e686782033`, next to the delegated `User.Read` of Microsoft Graph that the console's own sign-in has. The tool adds these two to what the app registration asks for already | The person who runs the tool |
| E2 | The consent of the tenant's administrator for it | An OAuth 2.0 permission grant of the app's enterprise application, for all users and for that one scope, so that nobody is asked at the first sign-in | A tenant administrator: the tool gives it when the person who runs it may, and otherwise says so in plain words and prints the address that an administrator opens |
| E3 | The redirect address `https://<console host>/arm/return` | Next to the platform's own `https://<console host>/.auth/login/aad/callback`. Microsoft Entra sends the person back to it after the sign-in to Azure Resource Manager | The person who runs the tool |
| E4 | Public client flows off | `isFallbackPublicClient` of the app registration is false or not set, so that the app is a confidential client and a sign-in code can be redeemed only with the app's federated credential. `check` reports it as missing when it is true; `apply` sets it to false only then, and sends nothing else of the app registration with it | The person who runs the tool |

**What a customer's tenant administrator does.** Grants the consent for that one delegated permission, once, for the whole tenant: by opening `https://login.microsoftonline.com/<tenant id>/adminconsent?client_id=<client id>` and accepting, or with `tools/entra-setup.py` when the administrator is also the person who makes the app registration. The consent gives Meternaut no standing right. Meternaut can act only as a signed-in person, with that person's own rights, while that person is present; no refresh token is requested; and the person's token is used for one change and never stored or logged. The administrator can remove the consent at any time: after that no change can be made, and the reads go on.

## What earlier versions granted, and is retired

An earlier version of the console gave Meternaut a writer: one custom role, *Meternaut waste remover*, assigned to the identity `id-meternaut-runner` on the project's own resource group. It is gone from the file and has to be gone from Azure. The file lists it under `retired`, a test fails if a retired role or identity is also a current one, and the table is printed by `python tools/access-requirements.py markdown --retired`. On 2026-11-05 the owner removed the assignment and the role by hand, with his own sign-in, and a run of `retire` without `--apply` then reported W1 as gone and the identity as still there: nothing to retire, exit 0.

<!-- access-retired:start -->
| # | Identity | Role | Where | Why it is retired |
|---|---|---|---|---|
| W1 | `id-meternaut-runner` | Meternaut waste remover (custom role) | The project's own resource group, where Meternaut plants waste of its own | The writer of an earlier version: a custom role that read and deleted a managed disk and a public IP address in this group, held by this identity. Meternaut holds no write right now: a change is made with the token of the person who approved it, and Azure checks that person's own rights. The role's assignments and the role are removed with retire; the identity is removed by the deployment workflow or by the owner |
<!-- access-retired:end -->

`python tools/access-requirements.py retire` removes what is still there, and nothing else:

- **It reads first.** For each retired item it looks for the identity by name in the project's resource group, for the assignments of the retired custom role at that place and below it, whoever holds them, and for the custom role. An identity that was deleted leaves its assignment in Azure, which the portal shows as "Identity not found": the tool finds it by the role, not by the identity.
- **It is a dry run unless told otherwise.** Without `--apply` it prints the exact `az` commands and exits 1 while something is left to retire. With `--apply` it runs them with the signed-in person's own sign-in: the assignments first, then the role, and only when no assignment of it remains. A role that can also be assigned outside the place is not the one that was granted there, and is left alone.
- **It never deletes an identity.** It reports the identity and says that the deployment workflow or the owner removes it.
- **It repeats safely and is refused in a pipeline.** A second run says that there is nothing to retire, and `--apply` is refused under GitHub Actions like the other commands.

```powershell
python tools/access-requirements.py retire --project-subscription $sub --project-group $group
python tools/access-requirements.py retire --project-subscription $sub --project-group $group --apply
```

## Who may grant

- To assign a role at a place, a person needs `Microsoft.Authorization/roleAssignments/write` there. *Owner*, *User Access Administrator* and *Role Based Access Control Administrator* have it ([Learn](https://learn.microsoft.com/azure/role-based-access-control/delegate-role-assignments-overview)). The last can be limited by a condition to some roles and some principals.
- To make a custom role, a person needs `Microsoft.Authorization/roleDefinitions/write`. *Owner* and *User Access Administrator* have it; *Role Based Access Control Administrator* and *Contributor* do not (read from Azure on 2026-11-05). Removing an assignment and removing a custom role (`retire`) take the delete actions at the same places.
- The places usually have different owners: the estate's subscription, the gateway, the central workspace. One person who holds the right at all three is the exception; the pilot is one.
- To give the consent for the whole tenant (E2), a person needs a Microsoft Entra role that may grant tenant-wide admin consent ([Learn](https://learn.microsoft.com/entra/identity/enterprise-apps/grant-admin-consent)). To make the app registration and assign people to its enterprise application (E1, E3, E4), a person needs Microsoft Entra roles that allow that. One person who holds all of them, a Global Administrator for example, does everything in one run of `tools/entra-setup.py`. Where that is two people, the one who may not give the consent runs the tool all the same: it makes the rest and prints the address that the other opens.
- The deployment workflow's identity is none of these and must not become one.

## What a new environment needs besides roles

| Need | Who | Needed by |
|---|---|---|
| The project's resource groups, the deployment identity and its federated credential, with its roles on the project's group and on the gateway's group | An Azure administrator, once ([bootstrap](../../environment/BOOTSTRAP.md)) | The first workflow run |
| The resource providers that the templates use, registered in the project's subscription | Someone who may register providers there: the deployment identity cannot | The first workflow run |
| An existing API Management instance with Citadel's objects (the workflow adds them), and model quota in the region | The gateway's owner | The first workflow run |
| An address range and the landing zone's DNS server for the project's virtual network. Private DNS zones are never created | A network administrator | The first workflow run |
| A GitHub repository whose workflow signs in with OpenID Connect | The repository's owner | The first workflow run |
| The grants of the table above | The owner of each place | After the Hub action `recording` (R4, R5) and `cases` (R1 to R3) have made the identities |
| Microsoft Entra: one app registration for the console's sign-in and for the approving person's sign-in to Azure Resource Manager, with no secret and public client flows off; the delegated permissions `User.Read` of Microsoft Graph and `user_impersonation` of Azure Service Management; the redirect addresses `/.auth/login/aad/callback` and `/arm/return`; one enterprise application that requires assignment; the people who may sign in | A person who may administer Microsoft Entra, once: `tools/entra-setup.py` | After the Hub action `cases` has made the identity of the sign-in (`id-meternaut-console-auth`) |
| Microsoft Entra: the administrator's consent for both delegated permissions, for all users (E2) | A tenant administrator, once: `tools/entra-setup.py` does it for an administrator and prints the address for anybody else to pass on | After the app registration exists |
| What an earlier version left in the project's resource group: the writer's role assignments and custom role (W1, retired) | A person who may assign roles there, once: `tools/access-requirements.py retire`. The deployment workflow or the owner removes the identity `id-meternaut-runner` | After the version without a writer is deployed |
| Exchange Online: one shared mailbox that sends the letters, and the one right to send as that mailbox only (Exchange's role-based access for applications, limited by a management scope), for the identity that sends | A person who may administer Exchange Online, once: `tools/exchange-setup.py` | After the Hub action `cases` has made the identity that sends (`id-meternaut-cases`) |

The Teams app and its consent are not built, and they have no Azure role, so they are not in the file; each one gets its own line on this page when it is real. The app registration and the mailbox have no Azure role either: each has a tool of its own that reads before it writes, makes nothing without `--apply` and never runs in a pipeline ([the loop](04-the-loop.md#what-a-person-has-to-do-once)). The design's [onboarding steps](../design/09-delivery-and-operations.md#9-onboarding-an-estate) and [the build plan](../build-plan/02-before-you-start.md) describe the finished system.

## Why a pipeline cannot make the first grant

A pipeline can assign a role only with an identity that already may assign roles at that place. So either a person assigns, or a person first gives a pipeline identity that right. A right to assign roles is the most valuable one an identity can hold, so it must be narrow: *Role Based Access Control Administrator* with a condition that names the roles in the file and the identities of Meternaut. That identity itself needs one grant from a person at each place it works in, or once at a management group above them. It cannot make a custom role either, so the two custom roles are made by a person first.

## The options

| Option | What it is | A standing right to assign roles | A person is needed | State |
|---|---|---|---|---|
| **1. The installer, run by the person who owns the place** | `tools/access-requirements.py`. It reads the file and Azure, shows what is missing and the exact commands, and with `--apply` makes them with that person's own sign-in. It never runs in a pipeline | None between runs | Once for each estate, and again for a new identity | **Built.** Run read only against the real environment before the console: 5 of 5 present (R1 to R5). `retire` is new: it removes the one grant that an earlier version made (W1). Its dry run against the real environment found W1 already gone, removed by hand |
| **2. The same installer at a management group** | The roles are inherited by every subscription below the group ([Learn](https://learn.microsoft.com/azure/role-based-access-control/scope-overview)), so one run covers all of them | None between runs | Once for the group | Works now: the place may be a management group. The app still reads only the subscriptions in `SCOPE_SUBSCRIPTIONS` |
| **3. A pipeline with an onboarding identity** | A workflow signs in as an identity that holds the limited right above, and runs the same file for the places that an estate owner names | Yes, limited by a condition | Once for each place, to give the onboarding identity its right; then none for each new subscription below it | **Not built.** It needs the owner's approval, in plain words, of the identity and its condition (rule 18) |
| **4. Azure Lighthouse** | A subscription of another tenant is projected into the tenant that manages it | No | Once, by the customer | **Does not fit.** It supports no custom roles, and the key reader is one ([Learn](https://learn.microsoft.com/azure/lighthouse/concepts/tenants-users-roles)). Meternaut is deployed in the adopting organisation's own tenant |

**Recommendation.** Use option 1 now, and option 2 where the estate has a management group. Add option 3 only when an organisation wants new subscriptions onboarded without a person each time. Option 1 leaves no standing right to assign roles anywhere between runs, and it is the one step that already has a name for it in the design: the estate owner deploys the onboarding module. Its cost is one run by a person for each estate, which is small next to a standing right that could grant anything the condition allows.

## What an installer or a pipeline must do

| # | Requirement | The installer today |
|---|---|---|
| I1 | Uses an identity, never a key or a password: the person's own Azure CLI sign-in, or a federated workload identity | Yes. It reads and writes no secret, and a test scans the tool for the words that a key leaves behind |
| I2 | Reads before it writes, and says for each requirement: present, missing, or why it cannot be present yet | Yes: `check` |
| I3 | Changes nothing unless told: the default is a dry run that prints the exact commands | Yes |
| I4 | Grants only what the file lists, at the places named, and only to a service principal | Yes. A test checks every role in a command; another checks that the file holds only reads |
| I5 | Repeating it changes nothing | Yes: a second run says there is nothing to grant |
| I6 | Compares a custom role that exists with the file, reports a role that can do more, and never changes it | Yes |
| I7 | Reads back after it writes | Yes |
| I8 | Works for a subscription, a management group or a resource group, and for any number of places | Yes |
| I9 | Never runs in a pipeline that must not hold the right; the Hub workflow never calls it | Yes: it refuses under GitHub Actions, and a test holds that |
| I10 | Leaves a record of who granted what, where and when | The Azure Activity Log records each assignment. The tool prints what it did, to paste into the changelog |
| I11 | Offboarding: removes exactly what it granted | Not built. The design reverses the onboarding steps ([design 09](../design/09-delivery-and-operations.md#9-onboarding-an-estate)) |
| I12 | The identities exist before the first deploy, so that no run has to be repeated after a hand step | Not built. Today the workflow makes an identity, a person grants, and the run is repeated. Making the identities first, in the bootstrap, and having the templates attach them removes that |
| I13 | Removes a grant that the file no longer lists, when the file says so (`retired`), and never an identity | Yes: `retire`. It reads first, is a dry run unless `--apply`, removes the assignments before the role, leaves a role that can be assigned outside the place alone, and a second run finds nothing |

## The app should say what is missing

When a read is refused, the Watch writes Azure's own message, which is correct and long. It should name the requirement that is missing (R1 to R5). A caller can read its own effective permissions at a place, so the Watch can check each requirement at the start of a run and write one plain line for each that is missing. Not built. Until then `check` is the read-back.

## Known limits

- **`check` reads role assignments.** It does not evaluate conditions, deny assignments or role eligibility. The proof that a grant works is a run of the Watch.
- **A grant above a named management group is not recognised.** An assignment at that group, and at a management group above a subscription, is.
- **The built-in roles are wider than the Watch needs.** Reader reads every resource of the subscription; Cost Management Reader and Monitoring Reader carry `Microsoft.Support/*`. Custom read roles are the tightening that [the first cases' known limits](02-first-cases.md#known-limits) already name.
- **A new assignment can take minutes to apply.** The first run after the grants of 2026-11-05 worked within three minutes.
- **`retire` sees what the signed-in person can read.** An assignment of the retired role at a place that the person cannot read is not listed. Azure refuses to remove a role that still has an assignment, and the tool then stops and says so.
- **`retire` has been run against the real environment as a dry run only, and the new items of `tools/entra-setup.py` not at all.** The steps of `retire` that remove something (`--apply`) and the new items of `tools/entra-setup.py` have run only against models of Azure and of Microsoft Entra; the first run of each in the real environment is read back with the tool's own second run.
- **`tools/entra-setup.py` removes nothing, so a redirect address or a permission that nobody meant stays until a person removes it in the portal.** `check` shows each as a note under the line of the app registration. An extra redirect address is an address that receives sign-in responses, so the note is worth reading; the tool does not judge it.
- **The permission is not narrower than the person.** `user_impersonation` lets the console act in Azure Resource Manager with everything that the signed-in person may do; the permission does not limit it to one kind of change. What the console does with a token is limited by the app's own short list of calls and by a test, not by the consent. Removing the consent ends the permission for everyone.
