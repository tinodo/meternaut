# Decisions of the experience design

**What this document answers.** The choices behind what people see, receive and decide: what was chosen, what it replaced, what it costs, what it means for security and privacy, and how hard it would be to change later. Every number in the other documents is a starting value that the adopting organisation sets; these decisions are the choices behind them. Platform facts behind them are in [the platform register](13-platform-register.md). How the decisions were challenged is recorded in [the review record](../reviews/README.md).

**How to read the tables.** The number is a stable identifier, and the tables group the decisions by topic. The last column gives the cost (people's attention and effort count as well as money), the effect on security and privacy, and the reversibility, in that order, separated by dots. *Easy* means a setting or a template; *moderate* means a change to the approval record or a flow; *hard* would mean breaking a promise made to people.

## Channels and pages

| # | Decision | Instead of | Cost · security and privacy · reversibility |
|---|---|---|---|
| 1 | **Teams is the default channel for owners.** E-mail carries letters, the fallback and requests to people outside the directory | E-mail first (a letter cannot carry a button that acts: Actionable Messages are unsupported from a shared mailbox); a portal people must remember to visit | No new service · cards reach only members of the directory, through the stored one-to-one conversation · easy: a per-person channel profile |
| 2 | **One voice: "Cost in Action (AI)".** No human name, no default avatar | A named persona or mascot | Free · nobody is impersonated; the "(AI)" suffix stays even if the product is renamed · easy |
| 5 | **Server-rendered pages with no client framework:** six owner routes and one platform route | A single-page application; a Teams tab (embedded web views break security keys and passkeys) | Scales to zero; the page requests step-up sign-in itself · small attack surface; security headers and a CSRF token set in code · moderate: the routes are the contract |
| 6 | **Dashboards are Workbooks fed by small business events;** letters carry the narrative; no custom portal | A custom portal; Power BI as the only surface (the FinOps toolkit's reports stay an optional companion); Azure Monitor dashboards with Grafana (generally available, optional) | A sliver of one gigabyte a month; no PDF or scheduled export · access follows Azure roles; events carry no object id · easy |
| 16 | **Requests to partners and billing owners are plain-text e-mail:** minimum estate data, an allow-list, an external flag, no figures in the subject line | A card (outsiders get none); a link into the organisation's pages | A longer letter, complete enough to act on without a call · little data leaves; a mail-flow rule enforces the allow-list · easy |
| 21 | **No text message or voice call to owners.** Those reach only the platform team, through action groups | Paging owners | Free · no private phone numbers are held (people data is an object id, a role and stated preferences) · easy |
| 24 | **Owners and team leads use web pages; Workbooks serve the FinOps lead, platform owner and security;** finance and executives get the monthly letter with a CSV | Workbooks for everyone (no per-viewer filtering beyond Azure roles, no export) | A CSV each month · each person sees only their own scope, filtered on the server · easy |

## How a change is approved

| # | Decision | Instead of | Cost · security and privacy · reversibility |
|---|---|---|---|
| 3 | **Two steps, in one place.** "Review the plan" replaces the Recommendation in the same message with the exact plan (a button, "Open the Recommendation", brings it back); a second tap gives the OK, and the first authorises nothing | An OK on the first card (the plan unseen); a second message (a second interruption) | One more tap · the exact plan is seen before any OK · moderate: the plan cards and the approval record change together |
| 4 | **One tap in Teams only for one-tap changes; everything else on a page.** No approval by reply, text message, voice or free text. A fallback never carries a change: a client below schema 1.5 gets the page link, and an older client's button opens the page; never a Submit action | Approval by e-mail button (unsupported from a shared mailbox) or by reply; a Submit fallback (no token exchange, no replacement card) | Larger changes need a trip to a page · every approval rests on the tapper's own token · moderate: widening it reopens the security design |
| 20 | **Two independent approvers, asked in parallel.** Neither sees the other's answer or note until both have decided; one directory object never fills both roles | Sequential approval (the second person is anchored by the first) | A slightly richer page · independence by construction · moderate: the shape of the approval record |
| 22 | **A pre-planned one-step path for one-tap changes stays off** until its cost and its staleness are measured | Turning it on now | Keeps the second tap · the look at the exact plan is what catches a stale plan · easy: a switch |
| 25 | **A page for "your OK on a page" or "two people" opens in the system browser,** never in an embedded view; a device test is a release gate, and the e-mail link, always sent with a purchase, is the verified fallback | An embedded view in Teams or Outlook | A client matrix before go-live · security keys and passkeys keep working · moderate: it follows what each client documents |
| 31 | **A tap is bound to the plan, the person and the time.** The plan code, eight characters from the plan's hash, is a reference echoed on every tap and page submit: each approver records one decision against it, and the plan is used once, when it runs. The tapper must be the designated approver or a named delegate. After five one-tap approvals in a day (a starting value) further changes go to the page | A code that is shown but not checked; no cap; an alert whenever someone approves outside their hours | A little state in the approval record · a stale or forwarded card is refused; a stolen signed-in device can do little before the cap; only an approval recorded without the authenticated event of its route raises an alarm, which does not prove who tapped · moderate |
| 37 | **The system never asks two people to approve a purchase it cannot make.** Where it has no billing reach (access variants B to D, described in [the people](01-people.md)) the approval is of a request, and the owner's or partner's quote settles the number | Approving a list-price scenario as if it were a purchase | A two-stage flow for those scopes · no signature on a number that nobody can honour · easy |
| 38 | **The words that refuse are plain.** "No, leave it as it is" closes the ask and nothing follows; "Not mine" hands the item to cover; "Cancel" drops a plan; "Decline" on the page closes the request | A deferral label, which promises a return that nobody has scheduled | A label to keep consistent · a refusal costs one tap and no reason, and is never chased · easy |

## Attention and people

| # | Decision | Instead of | Cost · security and privacy · reversibility |
|---|---|---|---|
| 7 | **The attention budget:** pushes counted per person, a slow start per person, one reminder, a weekly desk that holds what waits and does not count, a fatigue review instead of a penalty | Notifying whenever something is found; a budget per team; ranking people by response | A policy step in the send workflow; some Recommendations wait for the desk · nobody is profiled or scored, and silence is not treated as "ignored" · easy: every number is a parameter |
| 18 | **Working days, time zone and quiet hours are stated by the person,** not taken from calendars, presence or out-of-office | Inferring availability | One question at first contact · no use of calendar or presence data · easy |
| 19 | **A standing permission is introduced before its first run;** each run is announced within minutes, summarised weekly, and can be paused where it applies | Telling people only in a weekly summary; no way to pause one place | More messages in the first weeks · nothing happens in a person's scope that they could not have read about · easy |
| 28 | **Coverage routing, not escalation.** A parked Case goes to an appointed delegate or the custodian queue; a line manager hears only if the owner appointed them; no message tells a third person that someone did not answer | Escalating to the line manager | A custodian queue to staff · silence is not turned into monitoring · easy |
| 29 | **A note's scope never exceeds what its author owns.** A wider scope becomes a request to the person who owns it, with the number of resources affected | One owner widening a note to everywhere | Some notes wait for a person · one owner cannot silence another's resources · easy |
| 33 | **Counts over fewer than five people roll up.** No individual signal is offered to managers, results that a subtraction could isolate are suppressed, and nothing is offered for performance review | Per-person response statistics | Coarser team views · respects privacy and labour rules, including works-council consultation where one applies · moderate: easy to tighten, but loosening breaks a promise to people |
| 40 | **Three different pauses have three names:** "Pause messages" (a person's holiday mode), "Pause changes here" (an owner stopping standing permissions) and the kill switch (the platform team) | One word, "Pause", for all three | A vocabulary to keep · nobody stops the wrong thing · easy |

## Honest numbers and words

| # | Decision | Instead of | Cost · security and privacy · reversibility |
|---|---|---|---|
| 8 | **Every saving figure carries its price basis and one of Scenario, Expected or Verified;** any other money figure carries its basis in its own sentence | A single saving number | More text on each card · a list-price scenario cannot pass as a promise, and agreements cannot be compared falsely · easy |
| 10 | **People never see internal names:** a layer maps the design's words to screen words | Showing the design's terms | A vocabulary to keep in step with the design · none · easy |
| 23 | **Finance letters and the Savings ledger add FinOps Foundation terms** (run rate reduction, cost avoidance, and savings only against a budget finance set) beside Scenario, Expected and Verified | The Foundation's terms alone (no confidence axis; its glossary calls "savings" ambiguous); ours alone (finance cannot reconcile) | A column in two reports · none · easy |
| 27 | **Personas map to the FinOps Framework personas** | The older cloud-adoption "cost-conscious organization" roles page (deprecated, removal date 30 November 2026) | None · none · easy |
| 34 | **Figure notes.** Savings and waste are amortised; budgets and invoices are as invoiced; a figure for a period not yet invoiced is marked estimate | One cost view (a resource covered by a commitment then looks free, or a budget fails to reconcile) | A word on some cards · none · easy |
| 35 | **A verified saving subtracts the unused commitment a change creates;** a reduction made while a spending commitment is behind is held back from Verified and labelled "freed capacity inside the commitment" until the shortfall and its prepayment credit are settled | Counting every drop in a resource's cost | A rule in the saving check and a field in the report feed · a shortfall is charged at the end date as prepayment credit, so moving it is not saving · easy |
| 36 | **The Monday letter goes to the FinOps lead and the platform owner;** finance and executives get the monthly letter after the period closes | One letter for every role (finance would read estimates) | A second letter · no operational detail reaches roles that do not need it · easy |
| 41 | **A commitment is shown in the currency it is bought in,** with the home-currency amount as an estimate at a stated rate | Only the home currency (under a Microsoft Customer Agreement a savings plan is priced in US dollars and billed at the monthly rate) | A second figure on the purchase page · the approval binds the amount Azure will accept · easy |

## Trust and safety

| # | Decision | Instead of | Cost · security and privacy · reversibility |
|---|---|---|---|
| 9 | **Notes are visible and editable by owners;** every note has a scope and an expiry | Hidden memory | A page to build and keep accurate · people can see, correct and delete what is kept (GDPR Articles 17 and 21), and a note never widens a permission · easy |
| 17 | **Machine-readable AI marks in e-mail headers and in the message's AI-generated entity,** beside the visible label | A visible label only | A custom `x-ai-generated` header (Graph's JSON form allows only `x-`) and the entity set by `addAiGenerated()` · supports the marking duty in EU AI Act Article 50 (dates in the platform register) · easy |
| 30 | **Bound text is hostile text:** URLs are stripped and markdown is escaped in every bound value, and every link is built from a configured origin and an opaque id | Trusting resource names, tags and owners' words | A sanitising step in the send workflow · a persuasive resource name cannot become a link · easy |
| 32 | **Trust repair is designed:** an "Our mistake" card, and "I did not approve this" on every Done card | A generic error message | A card and a runbook · the button starts the incident path, pauses that person's one-tap approvals, alerts the platform team and keeps the record; Undo reverses the change · easy |
| 39 | **"Talk to a person" ends every card,** in the same place, and sits in the same place on every page; a card plan is one block per resource, not a table | A help button inside Details or a collapsed block; a four-column plan table | One more visible button; a taller plan · a person can always be reached, and a fake message can be reported there · easy |

## Access, language and testing

| # | Decision | Instead of | Cost · security and privacy · reversibility |
|---|---|---|---|
| 11 | **WCAG 2.2 AA and EN 301 549 are the bar,** with a language policy | WCAG 2.1 AA (what EN 301 549 version 3.2.1 still carries); no stated bar | Testing with assistive technology in Teams itself · the AI notice is itself accessible (EU AI Act Article 50(5)) · easy to raise |
| 12 | **Experience as code:** templates and message catalogs live in Git with CI checks, including a comprehension check | Cards and letters edited by hand; review by eye | A card lint, a renderer and a comprehension check · no silent change to the words of an approval · easy |
| 13 | **Wording comparisons are disclosed, with the prediction recorded first,** and never run on the text of an approval | Click-through tests | Slower learning about wording · approval text is never tuned for a click · easy |

## Optional modules and review surfaces

| # | Decision | Instead of | Cost · security and privacy · reversibility |
|---|---|---|---|
| 14 | **Meetings and voice are optional, and text comes first.** Consent before capture; nothing said aloud changes anything; the avatar is clearly an AI | Voice first; a seat in the live meeting (the media platform is developer preview); live notes and translation (Microsoft's Facilitator and Interpreter cover them) | Per-use meters, only when used · no cloned voice; a refusal stops this app reading the transcript (Teams still transcribes); the transcript is not kept, the summary is · easy: optional modules |
| 15 | **Developer cost comments are optional:** advisory, one per pull request, updated in place | A blocking cost check | A comment bot; no first-party tool joins What-If output to prices, and Infracost reads ARM JSON but reads Bicep only after it is compiled · advisory only, so it cannot block a merge · easy |
| 26 | **The review card is a GitHub check run,** mirrored as one pull-request comment that is updated in place | A comment alone; an issue form (not available for pull requests) | A GitHub App with Pull requests and Checks write access and no Contents write on the base repository, proposing from a fork; three buttons at most · the app cannot merge (merging needs Contents write), and contributor text is escaped · easy |

## What tests and measurements settle

- **Decision 25.** A device test of what `Action.OpenUrl` opens on each Teams client (desktop, web, iOS, Android) is a release gate. Until it passes, the e-mail link is the verified route.
- **Decision 22.** The one-step path stays off until a measurement shows what it saves and how often a plan goes stale.
- **Decisions 7 and 31.** Pushes per week, the reminder days and the daily cap are pilot settings to test, not thresholds established by research.
