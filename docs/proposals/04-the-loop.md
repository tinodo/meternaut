# The loop — a proposal

**Status: approved on 2026-11-05 (the owner: "GO", for the whole solution), built the same day. Nothing in this page is true of the real environment until the changelog says that it was deployed and what was checked.** This page says how a case that the Watch finds becomes a person's answer and, for the one kind of resource that Meternaut may touch, a checked change to Azure: the console, the approval, the runner, the mail, the resources that Meternaut plants itself, and what stays with a person. It follows the [first cases](02-first-cases.md), whose "Not built, and next" this is, and it builds on the [access requirements](03-access-and-onboarding.md). The pages are designed in [the web pages](../experience/06-web-pages.md).

## What it is for

Until now Meternaut found leads, two AI roles judged them and the History recorded the work, and nothing reached a person except by opening a portal workbook. A workbook is a poor first contact: it reads its data from the browser, so a network that resolves the Azure Monitor query addresses to a private IP address (a corporate VPN, for instance) shows "Query failed", and the person has nobody to answer to. The loop closes that gap:

1. a case that is proposed for deletion becomes a plan that **code** writes, with its evidence, what could go wrong and how to undo it;
2. the person who may approve it gets a letter with a link;
3. the person signs in, reads the plan on a page and answers it;
4. after a delay in which the person can still cancel, **one writer** makes the change, after it has read the resource again;
5. later the writer's result is checked against Azure and against the cost lines, and the person is told.

Only a resource that Meternaut planted itself, in its own resource group, can reach step 4. Everything else is still reported and never changed: no other project's resource is a target ([rule 18 of AGENTS.md](../../AGENTS.md)). That is deliberate: the loop is proven end to end on resources that nobody else owns, before any estate owner is asked for a write right.

## The path of one case

| Step | What happens | Who or what does it |
|---|---|---|
| 1. Find | The Watch (daily, or when the control hub is asked) lists leads, puts the waste that Meternaut planted itself first (it is the one kind that the writer can act on), drops the ones judged in the last seven days so that the slots of a run go to new leads, and takes up to three | The Watch, as before |
| 2. Judge | Two AI roles on two different models, then the guards in code (lock, keep tag, too new, managed group). A planted resource is not held back for being new; every other guard still holds | The Watch |
| 3. Record | Each case is written to the store with its steps, models and facts. A case that is proposed for deletion of an unattached managed disk or an unassigned public IP address, with the planted tag, in the writer's resource group, gets a **plan** | The Watch, then the approvals code |
| 4. Tell | A letter to each person who may approve: the first letter to a person says who Meternaut is and what it will and will not do; the approval letter has the link `https://<console>/ok/<plan>` | The mailer, as the shared mailbox |
| 5. Answer | The person signs in with Microsoft Entra and opens the page. It shows the exact change, the evidence level, what could go wrong, how to undo it and the saving. The answers: approve, decline, ask a question, or "not mine". The form carries the plan's 8-character code and a one-use token, so an answer to a plan that has changed, or a form that was used already, is refused | The person |
| 6. Wait | An approval writes a decision and queues an action that starts after a delay (120 seconds by default). Until then the person can cancel it on the same page | The approvals code |
| 7. Change | A timer, every minute, takes the actions whose time has come. The runner re-reads the resource, checks every precondition again, deletes it with its own identity and reads until Azure says that it is gone | The runner |
| 8. Tell again | A letter says what ran and what the outcome was | The mailer |
| 9. Check | Two days later the runner reads the resource again (it must still be gone) and the cost lines of the resource's cost scope; the case becomes `verified`, and a last letter says so | The runner |

The plan's words (title, what changes, what could go wrong, how to undo it, the evidence level) are written by code from the lead's typed facts. A model contributes only the objections that the Skeptic raised, shown in the notebook, and never a sentence of the plan. The plan's code is the first 8 characters of the SHA-256 of the plan id, the family, the resource id and the expiry time: a changed plan has a new code, so an old approval cannot be reused for it.

## What is built

| Part | What it is | Identity and rights |
|---|---|---|
| The store | Ten tables of the usage recording's storage account (runs, cases, plans, decisions, actions, switches, settings, notes, one-use form tokens, mail records), written over HTTPS with the Azure Table REST API. The app's list of allowed calls holds the account's table address and nothing else for this part. A form token is stored as a hash, never as the token | `id-meternaut-cases`, with Storage Table Data Contributor on the account (a role that the workflow already gives to a function app) |
| The console | The web pages, served by the same function app from the root address. One function takes every route. `/healthz` answers `ok` with no sign-in; every other route is behind the platform's sign-in, and the app refuses (503) when the platform says that sign-in is not on | The platform's sign-in (below); the pages read and write the store with `id-meternaut-cases` |
| The sign-in | App Service authentication with Microsoft Entra, in front of every route but `/healthz`. The app registration has **no secret and no certificate**: it trusts one user-assigned identity, `id-meternaut-console-auth`, through a federated identity credential, and that identity does nothing else. People must be assigned to the app, and the platform lets in only the object ids of the list of people | `id-meternaut-console-auth` (no Azure role) |
| The people | One setting, a list of the people of the console: object id, name, roles (`owner`, `approver`, `ops`) and the address that letters go to. A person who is not on the list sees nothing, and no letter goes to an address that is not on it | None |
| The approvals | The code that makes a plan, takes an answer and records it. It is the one `Decider` that the pages call | `id-meternaut-cases` |
| The runner | The only code that changes Azure. It has its own identity, its own HTTP client and its own list of calls: read and delete of a managed disk and of a public IP address in one resource group, and a read of management locks | `id-meternaut-runner`, with the custom role *Meternaut waste remover* on the project's resource group (W1 in the [access requirements](03-access-and-onboarding.md)) |
| The timer | `runner-tick`, every minute: closes the plans whose time is over, runs the actions that are due (at most three at a time), marks an action that has been running for more than 15 minutes as `unknown`, verifies the actions of two days ago, sends the letters about them and clears the used form tokens once an hour | The two identities above, each for its own part |
| The mail | One shared mailbox sends every letter through Microsoft Graph `sendMail`, with the identity `id-meternaut-cases`. Exchange's role-based access for applications limits that identity to that one mailbox, and the identity holds no Microsoft Entra permission for mail | `id-meternaut-cases`, with the Exchange role *Application Mail.Send* limited by a management scope |
| The planted waste | The Hub action `plant` makes an unattached managed disk and, when asked, an unassigned public IP address in the project's resource group, tagged `meternaut-planted`. They are the resources that the loop may touch. A public IP address is optional because the landing zone's policy may deny it | The deployment identity, as for any other resource of the project |

## Who may do what

- A person is known only by the object id that the platform's sign-in puts in a header after it has signed the person in. A form field, a link or a cookie never says who someone is. The app trusts the header only because it refuses to serve anything when the platform's sign-in is off.
- **owner**, **approver** and **ops** are the roles. An approval needs the role *approver* and the person's object id in the plan's list of approvers, which the code takes from the list of people when the plan is made. The pause page needs *ops*; the permissions page needs *ops* or *owner*. Every person on the list can read the History and manage their own settings, notes and decisions.
- A person cannot approve for somebody else, and cannot approve a plan that is not open, has expired, or has a changed code.
- A person can say "not mine": the plan is closed and the case goes back to the people who decide by hand. A person can ask a question: it is recorded, the plan stays open and nothing is approved.

## Safety

- **One writer, and nothing else writes.** The Watch, the console and the mailer have no Azure write. The test of the app's packaging allows a PUT or a DELETE in the store (Table Storage) and in the runner (Resource Manager) and in no other file; the web package makes no call at all. The runner's list holds five calls (read and delete of a disk, read and delete of a public IP address, read of locks), and a test compares that list with the five actions of the custom role: the two are the same.
- **What the runner checks again, right before it deletes.** The plan is `approved` and not older than its expiry; the action is due; no switch is pulled; the resource still exists, is still unattached or unassigned, still has the planted tag, is still in the writer's resource group, has no management lock (read at the resource and above it), and is not marked do-not-touch. A single failed check ends the action as `failed` with the reason and changes nothing. It deletes once; it never retries a delete. It then reads the resource until Azure answers 404 (up to six reads, ten seconds apart).
- **The delay is a safety.** The first approver can cancel until the start time. After it, the change cannot be cancelled by anyone but a pulled switch.
- **Switches.** `all`, `changes` and `messages` can be pulled on the pause page by a person with the role *ops*. A pulled `changes` switch stops approvals from being recorded and stops the runner from starting a change; `messages` stops letters. A switch that cannot be read counts as pulled.
- **No secret, anywhere.** The sign-in uses a federated credential; the mail uses an identity and Exchange's scoped role; the store and the changes use identities. The test that scans for keys (rule 23) covers the new code and templates, and the app registration is checked by a tool that refuses an app that holds a secret or a certificate.
- **The plan is not a model's.** A model's output is checked against the same schema as before; the plan is built from typed facts, and a test fails if a model's sentence reaches a plan or a letter.
- **A letter says what matters and nothing that is not needed.** The subject starts with `[Meternaut]`, says the point and holds no resource name and no amount of money. The sender's display name ends with "(AI)" and the message carries the header `x-ai-generated: true`. The mailer sends only to an address on the list of people, only as that person on the list, and keeps a record of the kind, subject, time and outcome of each letter, and never its text. Graph's answer 202 means that Graph took the letter, not that it arrived: delivery is proved by receipt.
- **Letters are limited.** A person's weekly budget, a pause that a person set and the choice of the weekly desk hold a letter; an approval letter is the one kind that no budget holds, because a plan that waits for an answer has to reach its approver. A letter that is held or refused is written down with the reason.
- **Forms.** A form is accepted only as a POST from the same site, in the form content type, at most 16 KB, with a one-use token that belongs to the person and the plan. Every page carries a strict content security policy and no script; a page never shows a trace, and a fault says only that nothing was changed.
- **The loop is optional.** If the store's name is not set, the app is the Watch alone, as it was before. If it is set, every setting that the loop needs has to be valid, or the loop does not start.

## What a person has to do once

A person who owns the place does each of these once, with their own sign-in. Each has a tool that reads before it writes, changes nothing without `--apply`, refuses to run in a pipeline and removes nothing. The commands are in [the bootstrap page](../../environment/BOOTSTRAP.md#added-on-2026-11-05-for-the-console-and-the-approval-loop).

| What | Tool | Who |
|---|---|---|
| The writer's custom role and its one assignment, in the project's resource group (W1) | `tools/access-requirements.py` | A person who may assign roles in the project's group |
| The app registration for the sign-in, with no secret, and the people who may sign in | `tools/entra-setup.py` | A person who may administer Microsoft Entra |
| The shared mailbox and the one scoped right to send as it | `tools/exchange-setup.py` | A person who may administer Exchange Online |
| The repository variables `CONSOLE_APP_CLIENT_ID`, `CONSOLE_PEOPLE` and `MAIL_SENDER` | `gh variable set` | The owner of the repository |

After the first run of the action `cases`, which makes the two new identities, and these steps, the action `cases` is run again so that the platform's sign-in is switched on; the action `loop-check` then reads the front door from outside and fails if anything but `/healthz` can be read without signing in, or if a forged sign-in header opens a page.

## Price

About zero a month more. The tables are in the existing storage account, and a few hundred small records cost cents. The timer runs a function every minute, which the Flex Consumption free grant absorbs for a function that mostly reads one table. Mail through Graph from a shared mailbox without a licence costs nothing (a shared mailbox that is not over 50 GB and is not used to sign in needs no licence, [Learn](https://learn.microsoft.com/exchange/recipients-in-exchange-online/manage-user-mailboxes/shared-mailboxes)). The planted disk (4 GiB, Standard SSD) costs less than a euro a month until it is deleted, which is the point; the optional public IP address costs about three euros a month until it is deleted.

## What proves it

| Check | Shown by |
|---|---|
| A plan is made only for the two kinds of resource, with the tag, in the writer's group | Unit tests of `why_not` for each condition, and of `build_plan` for the exact text |
| An approval needs the role, the list, an open plan, the code, a one-use token and a switch that is not pulled | Unit tests for each refusal, and for a double answer |
| Nothing starts before the delay, a cancel works until then, a pulled switch stops it and releasing it lets it run | The end-to-end test: a Watch with a planted disk, the letters, the approval, two timer rounds, the delete and the verification, through the real store code against a model of the tables |
| Only the writer's token can delete | The end-to-end test gives the delete to the writer's token only, and a run with the reader's token fails with a refusal |
| The runner's calls are the role's actions | A test that maps each call of the runner to an action and compares the list with the manifest of the access requirements |
| A letter goes to a listed person only, once, with no resource name in its subject | Tests of the mailer and of the letters |
| The front door is shut | `tools/console-check.py door` in the action `loop-check`: no page without sign-in, a forged header opens nothing |
| The sign-in app has no secret | `tools/entra-setup.py check` |
| The change really happened | Resource Manager answers 404 for the planted disk; the Activity Log shows one delete by the runner's identity; the console and a letter say so |

## Known limits

Written down so that nobody has to find them.

- **The runner is a function of the same app.** It uses another identity, another HTTP client with another list of calls and another set of rights, but it runs in the same process and the same deployment as the Watch. A flaw in the app's code that can call the runner's token function could use that token for the five calls that the role allows, in the one resource group. A separate app for the runner is the next tightening.
- **The first approver cancels, nobody else.** A second approver who is told about a plan cannot cancel the first one's approval, and there is no rule yet that two people must approve.
- **Quiet hours are not applied.** A letter can arrive at any hour. The settings page holds the choice, and the mailer does not read it yet.
- **Approvals are not counted against the weekly budget of letters,** by design, so a plan always reaches its approver; a person who wants fewer of them can pause messages, and then the plan expires.
- **Teams is not built.** The person is told by letter only. A Teams card needs an app that a guest of the tenant may not be able to install; it is untested.
- **The mail is accepted, not proved to be delivered.** Graph's 202 is not receipt. The first delivery to a person's inbox in another organisation is the proof, and a mail-flow rule that rejects mail from the mailbox to anybody who is not on the list of people is not made by any tool here.
- **Exchange needs time.** A new role assignment or a changed scope applies to live sends after 30 minutes to two hours.
- **The saving of a new resource is unknown at first.** A resource that was made a moment ago has no cost lines, so the plan shows no saving and says so; the check two days later reads the cost lines.
- **Only two kinds of resource.** The writer cannot delete anything else, and it cannot resize, stop or buy anything. A resize and a reservation are later families, each behind its own role and its own proof.
- **The History workbook still depends on the viewer's network.** The console shows the same runs and cases from the store.

## Not built, and next

A Teams card for the approval (after a test of whether a guest of the tenant can receive it), the approval by a second person for a larger change, the agents' move into the Foundry Agent Service as hosted agents, a separate app for the runner, quiet hours, an alert when a timer round fails, and more families of change (resize a virtual machine, start or stop on a schedule, purchase advice that a person carries out in the portal). Each of them follows the same path: a plan that code writes, a person's answer, a writer with one narrow role, a re-check right before the change, and a check afterwards.
