# Cold read: letters, approval page, mail and sign-in

## 1. Verdict

Mostly. A stranger can see that mail never acts and that an OK is bound to a signed-in person, but they cannot build the two-person submit, the no-script forms, or the phone layout without guessing, and the published wireframe contradicts the copy on Decline size and on what a forwarded plan does.

## 2. Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | 06-web-pages.md:64 | 8 | "a code works once" | R3 needs two independent POSTs of the same plan code. Once-only globally blocks the second OK, or a replay of the first person's POST is allowed if "once" is only per person. Forged/replayed/stale submits cannot be specified until this is one rule. | "The plan code is echoed on every submit. Each designated approver may record one decision; a second submit from the same directory object is refused. The other approver's submit still succeeds." |
| 2 | Major | 05-letters-and-requests.md:91; 06-web-pages.md:37 | 4 | "about EUR 4,700 a month (range 4,100 to 5,300)" vs "about EUR 4,300 a month … (range 3,700–4,900)" | README says running-example numbers stay the same. E4's monthly saving and range do not. Retail vs agreement does not excuse two different Expected/Scenario figures for one purchase. | Pick one monthly figure, range, basis and saving word; use them on the letter, the page and the SVG. |
| 3 | Major | 06-web-pages.md:47; experience-approval-page.svg:101–104 | 8 | "Decline sits beside Approve, as tall and as easy to hit." | Approve is 247×38; Decline is 84×38. A smaller "no" on an irreversible €205,860 purchase is pressure, and it contradicts the sentence. Four controls in one row will not fit a phone without wrapping. | Make Decline the same height and width as Approve. Stack the four actions on small viewports. Specify the no-script forms: each action is a submit; Ask/Decline-reason is a second page with a textarea, method POST, hidden plan code and anti-forgery field. |
| 4 | Major | 06-web-pages.md:29 | 5 | "no always-ready instance, a fixed monthly cost" | Flex Consumption with zero always-ready instances is billed on demand (GB-seconds and executions, minus a free grant), not a fixed monthly cost. | "The page starts with zero always-ready instances, so hosting cost follows executions. Add always-ready instances only if p95 first load exceeds five seconds." |
| 5 | Major | 06-web-pages.md:43 vs experience-approval-page.svg:76 | 4 | "a collapsed Evidence row that links to the notebook" vs "▸ Show the evidence (your last 12 months…" | Builder cannot tell whether Evidence is a GET to `/why/<id>` (works without script) or an in-page disclosure. If the latter is JS, the no-script rule fails. | "Evidence is a link to `/why/<id>`. Optionally wrap the same URL in HTML `details` for in-page preview; no script." |
| 6 | Major | experience-approval-page.svg:124 | 4 | "a stale or forwarded plan is refused" | Binding (06:66) refuses the *wrong person*, not a forwarded URL used by the designated approver. The callout teaches the opposite and would break a mailed link. | "A forwarded URL does not authorise the recipient. The designated approver (or named delegate) may still submit their own request id after sign-in." |
| 7 | Major | 06-web-pages.md:31, 75 | 8 | "elsewhere the card's button fails and the request expires unapproved" / "A purchase starts as soon as the second OK is in" | Off-network phone and the e-mail fallback cannot open a private-endpoint page, so R2/R3 die on expiry. After the second R3 OK a purchase has no Cancel, but the confirmation copy still says "Nothing has changed yet". | State the network rule on the waiting letter. Split confirmation: non-purchase keeps Cancel until start; purchase after the second OK says "The purchase is submitted. It cannot be cancelled." |
| 8 | Minor | 06-web-pages.md:57 | 1 | "Step-up is custom code." | Reads as an answer to a reviewer about Easy Auth. | "The page requests the authentication context with a claims challenge and checks `acrs` on the token that returns." |
| 9 | Minor | experience-monday-letter.svg:42–58 | 8 | "€412k this four weeks (an estimate…" / "€1,840 a month, measured against comparison groups" | Honesty rule: every figure needs price basis, range and a saving word. The letter SVG drops them on the bill total and the win. | Put basis and saving word beside every money figure, including estimates and verified wins. |
| 10 | Minor | 05-letters-and-requests.md:80 | 8 | "At most three asks, including what more access would buy" | The Monday letter asks several decisions in one message (cover, price sheet, renew permission). | One primary ask in the letter; the others are links, each to one page. |
| 11 | Minor | 06-web-pages.md:123 | 2 | "the opt-in emergency lane still applies" | First use; not defined in 05 or 06. | Define on first use, or drop. |
| 12 | Minor | experience-monday-letter.svg:24 | 4 | "(documented, price checked)" | Screen words are "From Microsoft's documentation", "Price checked", "Seen on your bills". | Use those three phrases in the letter SVG. |

## 3. Sentences I would delete

1. 06-web-pages.md:41 — "Five choices shape the numbered parts:" (process talk).
2. 06-web-pages.md:57 — "Step-up is custom code."
3. 06-web-pages.md:57 — "That code is ours whichever sign-in the app uses, built-in authentication or its own."
4. experience-approval-page.svg:653–670 — "Approval is deliberate: no pre-ticked box, no countdown."
5. 05-letters-and-requests.md:147 — "Every letter except the purchase request leads to the pages node." ("pages node")
6. 06-web-pages.md:31 — "or through its own front door" (Azure Front Door vs the site origin).
7. 05-letters-and-requests.md:23 — the Microsoft Q&A example URL; keep the product links to RBAC and mail-flow rules.
8. experience-monday-letter.svg:1018 — "I never ask for passwords or secrets." on a weekly report (belongs on first-contact).
9. 06-web-pages.md:93 — "a one-tap change can still be given in Teams" on the down page for an R3 purchase (wrong class).
10. 05-letters-and-requests.md:15 — "The `x-` prefix is Graph's rule for the JSON form's custom headers." if letters are MIME; put custom headers in the MIME.

## 4. Fact checks

1. **Graph `sendMail` JSON vs MIME.** Claim (05:15): JSON takes one body, so letters go as MIME with text and HTML. **Result: correct.** JSON `body` is one `itemBody` (text *or* HTML). MIME is supported on the same API with `Content-Type: text/plain` and **base64** MIME in the body. Custom headers on JSON messages must start with `x-` ([message resource](https://learn.microsoft.com/graph/api/resources/message); [user: sendMail](https://learn.microsoft.com/graph/api/user-sendmail)). The file does not say the MIME must be base64.

2. **Actionable Messages on shared mailboxes.** Claim (05:9): not supported for shared mailboxes. **Result: correct.** FAQ: "Actionable Messages only support single user mailboxes. Group and shared mailboxes aren't supported." ([FAQ](https://learn.microsoft.com/outlook/actionable-messages/actionable-messages-faq))

3. **Exchange send caps.** Claim (05:5): 30 messages a minute and 10,000 recipients a day. **Result: correct.** ([outbound sending limits](https://learn.microsoft.com/defender-office-365/outbound-spam-sending-limits-troubleshoot))

4. **Entra authentication context.** Claim (06:53–57): R2 uses an authentication context; the page sends a claims challenge and checks the claim. **Result: correct** for app-owned step-up ([developer guide](https://learn.microsoft.com/entra/identity-platform/developer-guide-conditional-access-authentication-context), [claims challenge](https://learn.microsoft.com/entra/identity-platform/claims-challenge)). Auth context needs Entra ID P1 and is not in Free; the pages never say that. I did not verify that Functions built-in authentication can issue the challenge; the file's "custom code" claim is the safe reading.

5. **Functions `host.json` headers and Flex cost.** Claim (06:23): a function app can declare fixed headers in `host.json`. **Result: correct** (`extensions.http.customHeaders`, [HTTP bindings](https://learn.microsoft.com/azure/azure-functions/functions-bindings-http-webhook)). Claim (06:29): zero always-ready instances is a fixed monthly cost. **Result: wrong.** Flex Consumption on demand bills execution time and counts, not a fixed month ([Flex Consumption billing](https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan#billing)).

**RBAC / mail-flow (extra):** RBAC for Applications scopes *mailboxes*, not recipients ([application RBAC](https://learn.microsoft.com/exchange/permissions-exo/application-rbac)). The Q&A example at `learn.microsoft.com/answers/a/12392036` exists and shows a transport rule allow-list; it is not product spec.

**Replay/forge (build, not Learn):** GET `/ok/<requestId>` is view-only. POST needs Entra object id, anti-forgery, matching plan code, unexpired plan, not paused. Forwarded mail cannot approve. Stolen session on R2 is admitted. The once-only code (finding 1) is the hole.

## 5. Questions left unanswered

1. Is the plan code single-use per request or per approver, and which POST fields besides the code bind the submit (request id, anti-forgery, `acrs`)?
2. Exact no-script HTML for Approve / Decline / Ask or suggest / Not mine (two pages? field names? how a keyboard user reaches Decline first)?
3. After the second R3 OK on a purchase, is there any Cancel, and what does the confirmation page say?
4. If the app is on a private endpoint, how does an approver on a phone or home browser complete "your OK on a page"?
5. How is an e-mail reply matched to a Recommendation so Explain / Challenge / Teach work, if a reply still cannot approve?
