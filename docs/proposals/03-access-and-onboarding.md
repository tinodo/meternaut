# Access and onboarding — the requirements

**Status: written on 2026-11-05, after the first cases ran on the real estate. The installer in this page is built; the pipeline is not.** This page says what Meternaut needs granted outside its own resource group, who must grant it, why a pipeline cannot make the first grant on its own, and what an installer or a pipeline has to do. The design's [onboarding steps](../design/09-delivery-and-operations.md#9-onboarding-an-estate) describe the finished system; this page is what is true and built today. The changelog says what was done and checked.

## The problem

- The deployment workflow's identity may change only the project's own resource group. It holds no right in the subscriptions that Meternaut reads or in the gateway's, and it must not get one ([rule 18](../../AGENTS.md)).
- The workflow makes the identities that the apps run as: one for the usage recording and one for the first cases. Those identities need rights in other places, and only a person who may assign roles there can give them.
- Until now a person did that by hand, once for each identity, on the owner's written word, and reported it at once. The commands are in [the bootstrap page](../../environment/BOOTSTRAP.md).
- That does not scale to a second subscription, a second estate or another organisation. So the grants are written down as data, in [`environment/access-requirements.json`](../../environment/access-requirements.json), and a tool reads them: [`tools/access-requirements.py`](../../tools/access-requirements.py).

## What must be granted

One line is one role of one identity at one place. The table is printed by `python tools/access-requirements.py markdown`, and a test fails when this page and the file differ.

<!-- access-requirements:start -->
| # | Identity | Role | Where | What it is for |
|---|---|---|---|---|
| R1 | `id-meternaut-cases` | Reader | Each subscription that the Watch reads (the app setting SCOPE_SUBSCRIPTIONS), or a management group above them | Reads the resources, their tags and management locks, and Azure Advisor's cost recommendations: the detectors and the guards of the Watch. The role reads and changes nothing |
| R2 | `id-meternaut-cases` | Cost Management Reader | Each subscription that the Watch reads (the app setting SCOPE_SUBSCRIPTIONS), or a management group above them | Reads the cost lines of every resource for the last 30 days, so that every figure is Cost Management's and never a model's |
| R3 | `id-meternaut-cases` | Meternaut gateway key reader (custom role) | The one subscription of the gateway's access product that the Watch uses, below the API Management instance | Reads the one key of the gateway's access product at the start of each run, because the gateway always asks for it. The role allows that read and nothing else of the gateway (the one remaining key: AGENTS.md rule 23) |
| R4 | `id-meternaut-usage` | Monitoring Reader | The gateway's Application Insights component | Reads the gateway's Application Insights component, where the gateway records the token metrics of every call |
| R5 | `id-meternaut-usage` | Meternaut usage reader (custom role) | The central workspace that the component writes to | Reads one table (AppMetrics) of the central workspace. The component is workspace-based and the workspace asks for workspace permissions, so the role on the component alone returns no rows |
<!-- access-requirements:end -->

What the roles allow, read from Azure on 2026-11-05:

- **Reader** is `*/read` and nothing else. **Cost Management Reader** reads cost, billing periods, Advisor recommendations and management groups, and, as the built-in role has it, holds `Microsoft.Support/*` (support requests). **Monitoring Reader** is `*/read`, a workspace search and `Microsoft.Support/*`.
- **The two custom roles** hold three actions (usage reader, all reads of one table) and two (key reader: read the access product's subscription, and read its key). Each is defined for one resource group only. The key reader is assigned on one resource: the one subscription of the access product.
- **Which call needs which grant.** The Watch makes six kinds of call, and the file names them: Resource Graph queries, Advisor reads and management lock lists need R1; the Cost Management query needs R2; the key read needs R3; the model call through the gateway needs the key and no Azure role. A test compares this list with the calls that the app's HTTP client allows, so a new call cannot ship without a requirement.
- **No write.** The file holds only read roles, and a test fails if a custom role gets a write, a delete or a wildcard. The Activity Log of both subscriptions shows one operation by the cases identity during the first run on the real estate: the key read. No write.

## Who may grant

- To assign a role at a place, a person needs `Microsoft.Authorization/roleAssignments/write` there. *Owner*, *User Access Administrator* and *Role Based Access Control Administrator* have it ([Learn](https://learn.microsoft.com/azure/role-based-access-control/delegate-role-assignments-overview)). The last can be limited by a condition to some roles and some principals.
- To make a custom role, a person needs `Microsoft.Authorization/roleDefinitions/write`. *Owner* and *User Access Administrator* have it; *Role Based Access Control Administrator* and *Contributor* do not (read from Azure on 2026-11-05).
- The places usually have different owners: the estate's subscription, the gateway, the central workspace. One person who holds the right at all three is the exception; the pilot is one.
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
| Microsoft Entra: nothing so far. No app registration, no directory permission, no Graph permission | | |

The next slice needs steps that only a tenant administrator can take: a shared mailbox and a sender permission scoped by Exchange, the Teams app and its consent, and an app registration for the approval page ([design 09](../design/09-delivery-and-operations.md#9-onboarding-an-estate), [the build plan](../build-plan/02-before-you-start.md)). They have no Azure role, so they are not in the file; each one gets its own line on this page when it is real.

## Why a pipeline cannot make the first grant

A pipeline can assign a role only with an identity that already may assign roles at that place. So either a person assigns, or a person first gives a pipeline identity that right. A right to assign roles is the most valuable one an identity can hold, so it must be narrow: *Role Based Access Control Administrator* with a condition that names the roles in the file and the identities of Meternaut. That identity itself needs one grant from a person at each place it works in, or once at a management group above them. It cannot make a custom role either, so the two custom roles are made by a person first.

## The options

| Option | What it is | A standing right to assign roles | A person is needed | State |
|---|---|---|---|---|
| **1. The installer, run by the person who owns the place** | `tools/access-requirements.py`. It reads the file and Azure, shows what is missing and the exact commands, and with `--apply` makes them with that person's own sign-in. It never runs in a pipeline | None between runs | Once for each estate, and again for a new identity | **Built.** Run read only against the real environment: 5 of 5 present |
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

## The app should say what is missing

When a read is refused, the Watch writes Azure's own message, which is correct and long. It should name the requirement that is missing (R1 to R5). A caller can read its own effective permissions at a place, so the Watch can check each requirement at the start of a run and write one plain line for each that is missing. Not built. Until then `check` is the read-back.

## Known limits

- **`check` reads role assignments.** It does not evaluate conditions, deny assignments or role eligibility. The proof that a grant works is a run of the Watch.
- **A grant above a named management group is not recognised.** An assignment at that group, and at a management group above a subscription, is.
- **The built-in roles are wider than the Watch needs.** Reader reads every resource of the subscription; Cost Management Reader and Monitoring Reader carry `Microsoft.Support/*`. Custom read roles are the tightening that [the first cases' known limits](02-first-cases.md#known-limits) already name.
- **A new assignment can take minutes to apply.** The first run after the grants of 2026-11-05 worked within three minutes.
