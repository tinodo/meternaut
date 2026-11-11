# Platform register: what the experience relies on

**What this document answers.** Which Microsoft features the messages, pages, letters and reports depend on; whether each is generally available or in preview as read on 2026-11-02; what it is used for; and what the experience does when it is missing. Every row cites the vendor's page. A feature that could not be verified is listed as such and is not used. Other documents in this folder link here instead of repeating limits.

**Status words.** *Generally available* (GA): supported for production, subject to availability, permissions, licensing, quotas and cost. *Preview*: used only behind a switch, with a generally available fallback. *Not verified*: not claimed and not used. Re-read a row before relying on it: products change, and the date above is the only date these statuses are good for.

## Teams

| Feature | Status | Used for | If missing | Source |
|---|---|---|---|---|
| Adaptive Cards, schema 1.4 and 1.5 | GA (one page says up to 1.6, another says 1.5; templates declare 1.5; the cards that a flow posts declare 1.4, the version that Power Automate is reported to render) | Every card | A short plain message with the link | [cards reference](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-reference#adaptive-card), [agent card guide](https://learn.microsoft.com/agents/design-guidelines/adaptive-cards-for-agent-design#schema-and-host-compatibility) |
| `Action.Execute` with an `Action.OpenUrl` fallback | GA | Not used: a card that a flow posts takes no answer, so every card has one `Action.OpenUrl` | A client below schema 1.4 shows only `fallbackText`, which carries the page link and the AI line | [universal actions](https://learn.microsoft.com/adaptive-cards/authoring-cards/universal-action-model), [cards in Power Automate](https://learn.microsoft.com/en-us/power-automate/overview-adaptive-cards) |
| `FactSet`, `ActionSet`, `ShowCard`, `ToggleVisibility`, text and choice inputs with `label`, `isRequired`, `errorMessage`; `associatedInputs` | GA | Layout only: a card that the flow posts has no input and no action but the link | Plain text lines | [card format](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-format), [input validation](https://learn.microsoft.com/adaptive-cards/authoring-cards/input-validation), [Action.Execute](https://learn.microsoft.com/adaptive-cards/schema-explorer/action-execute) |
| Badge, ProgressBar, Carousel | Not verified in Teams | Not used | Text and FactSet | [card format](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-format) |
| CodeBlock | GA on web and desktop only, not on mobile | Not used | Plain text | [card format](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-format#codeblock-in-adaptive-cards) |
| Six actions per set, then an overflow menu; 1 to 3 advised | GA | At most six per action set | n/a | [overflow menu](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-format#adaptive-cards-overflow-menu) |
| Message size about 100 KB | GA | Templates stay under 20 KB; 80 KB is the ceiling | n/a | [Teams limits](https://learn.microsoft.com/microsoftteams/limits-specifications-teams#messaging) |
| Single sign-on on `Action.Execute` (token exchange) | GA | Not used: no card takes an answer | The page | [SSO for universal actions](https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/enable-sso-for-your-adaptive-cards-universal-action) |
| "AI Generated" label | Available; Learn gives no status word | Not set: the flow's action takes only the card | The footer line says it | [AI content labels](https://learn.microsoft.com/microsoftteams/platform/agents-in-teams/integrate-ai/ai-content-labels) |
| Feedback buttons (`feedbackLoopEnabled`) | Available per message; Learn gives no status word and does not document them for card messages | Thumbs under a message, where the client shows them (checked in the client matrix) | The card's own "Fewer like this" | [feedback controls](https://learn.microsoft.com/microsoftteams/platform/agents-in-teams/integrate-ai/user-feedback-controls) |
| Citations; a card inside a citation | Citations GA; card inside a citation is preview | Not used | The Details toggle | [AI content labels](https://learn.microsoft.com/microsoftteams/platform/agents-in-teams/integrate-ai/ai-content-labels#citations) |
| Post card in a chat or channel (Power Automate: the Flow bot, in a chat with the recipient) | GA; needs the Workflows app allowed in the Teams admin center and the recipient's mail address | Every card | The letter goes when the queue refuses the card | [Microsoft Teams connector](https://learn.microsoft.com/en-us/connectors/teams/) |
| Install the app for a person | Not needed: there is no app | Not used | n/a | [Microsoft Teams connector](https://learn.microsoft.com/en-us/connectors/teams/) |
| Sending limit of the Flow bot: 25 posts in 300 seconds a connection; about 28 KB a message | GA | Few cards for each person; every message carries a delivery id | A failed try is repeated; the letter goes | [Microsoft Teams connector](https://learn.microsoft.com/en-us/connectors/teams/) |
| `channelData.notification.alert` | GA | The emergency lane only | A normal message | [notification info](https://learn.microsoft.com/javascript/api/botframework-schema/notificationinfo) |
| Do Not Disturb and mute | An app cannot control or read them | Nothing: timing is never promised | n/a | [notification FAQ](https://learn.microsoft.com/graph/teams-send-activityfeednotifications#faqs) |
| Read receipts in a one-to-one chat | Optional, and a permission that the app does not have | Not used: the design knows only whether the person responded | n/a | [read receipts](https://learn.microsoft.com/microsoftteams/platform/bots/build-conversational-capability#receive-a-read-receipt) |
| Private and shared channels | Agents cannot post messages or cards in private channels; shared-channel agents are supported when the app opts in | Not used: people are reached one to one | n/a | [shared and private channels](https://learn.microsoft.com/microsoftteams/platform/build-apps-for-shared-private-channels), [channel conversations](https://learn.microsoft.com/microsoftteams/platform/bots/how-to/conversations/channel-and-group-conversations) |

## E-mail

| Feature | Status | Used for | If missing | Source |
|---|---|---|---|---|
| Graph `sendMail` from one shared mailbox with an application permission | GA | Every letter | n/a | [send as another user](https://learn.microsoft.com/graph/outlook-send-mail-from-other-user) |
| Custom headers must start with `x-` on the JSON form | GA | The machine-readable AI mark (`x-ai-generated: true`) and `X-Auto-Response-Suppress`; letters go as base64 MIME, where a header may be named freely | `Auto-Submitted` needs a MIME-format send or a mail-flow rule | [message resource](https://learn.microsoft.com/graph/api/resources/message), [sendMail](https://learn.microsoft.com/graph/api/user-sendmail) |
| Exchange RBAC for Applications limits mailboxes, not recipients | GA | A mail-flow rule enforces the recipient allow-list | n/a | [application RBAC](https://learn.microsoft.com/exchange/permissions-exo/application-rbac) |
| 30 messages a minute and 10,000 recipients a day per mailbox | GA, fixed | Far above the volume a letter schedule needs | Queue and retry | [sending limits](https://learn.microsoft.com/defender-office-365/outbound-spam-sending-limits-troubleshoot) |
| Actionable Messages in a shared mailbox | Not supported | Not used: e-mail carries links only | n/a | [FAQ](https://learn.microsoft.com/outlook/actionable-messages/actionable-messages-faq) |
| Data loss prevention and service-side sensitivity labels on Graph-sent mail | GA | Apply without client involvement | n/a | [sending mail](https://learn.microsoft.com/graph/outlook-things-to-know-about-send-mail) |
| Classic Outlook renders with a different engine from the web client | GA | Letters use simple tables, inline styles and a plain-text part | n/a | [rendering notes](https://learn.microsoft.com/troubleshoot/dynamics-365/customer-insights/journeys/email/email-troubleshoot-rendering#outlook-classic) |
| Read receipts and tracking pixels | Unreliable; clients block pictures by default | Not used | n/a | [message resource](https://learn.microsoft.com/graph/api/resources/message) |

## Web pages and sign-in

| Feature | Status | Used for | If missing | Source |
|---|---|---|---|---|
| Fluent 2 design tokens in plain CSS; Fluent System Icons (MIT) | GA | Every page | n/a | [Fluent 2 tokens](https://fluent2.microsoft.design/design-tokens), [icons licence](https://github.com/microsoft/fluentui-system-icons/blob/main/LICENSE) |
| `forced-colors` media feature | GA | High-contrast themes without script | n/a | [high contrast](https://learn.microsoft.com/fluent-ui/web-components/design-system/high-contrast) |
| System browser for security keys and passkeys | Microsoft's identity guidance | The approval link opens in the browser, not in an embedded view | The e-mail with the same link, always sent with a purchase, opens the person's own browser | [passkeys and browsers](https://learn.microsoft.com/entra/identity/authentication/concept-passkey-browser-authentication-federated-identity-provider) |
| Teams `secondaryBrowser` | Beta, mobile only | Not used | n/a | [secondaryBrowser](https://learn.microsoft.com/javascript/api/@microsoft/teams-js/secondarybrowser) |
| Entra authentication context with a claims challenge; three built-in strengths | GA (Entra ID P1 or P2) | Step-up before an approval; phishing-resistant strength for two-person approvals | The page refuses and says why | [claims challenge](https://learn.microsoft.com/entra/identity-platform/claims-challenge), [strengths](https://learn.microsoft.com/entra/identity/authentication/concept-authentication-strengths) |
| Response headers on Azure Functions | `host.json` `extensions.http.customHeaders` sets static headers on every response | Static headers there; per-response ones in code: CSP `frame-ancestors 'none'`, `X-Frame-Options`, `Cache-Control: no-store`, Referrer-Policy, anti-forgery token | n/a | [HTTP settings](https://learn.microsoft.com/azure/azure-functions/functions-bindings-http-webhook#hostjson-settings), [anti-forgery](https://learn.microsoft.com/aspnet/core/security/anti-request-forgery), [no-store](https://learn.microsoft.com/azure/security/develop/threat-modeling-tool-sensitive-data) |
| GOV.UK patterns: check your answers, confirmation page, error summary, summary list, warning text | Code MIT, content OGL v3 | Borrowed as patterns, not copied styling | n/a | [design system](https://design-system.service.gov.uk/patterns/check-answers/) |

## Reports

| Feature | Status | Used for | If missing | Source |
|---|---|---|---|---|
| Workbooks | GA; no per-viewer filtering beyond role-based access, no PDF or scheduled export, no error-bar chart; the Custom Endpoint is a client-side call with no Entra sign-in | Dashboards for central roles only | Letters carry the narrative | [data sources](https://learn.microsoft.com/azure/azure-monitor/visualize/workbooks-data-sources#custom-endpoint), [chart types](https://learn.microsoft.com/azure/azure-monitor/visualize/workbooks-chart-visualizations) |
| Logs Ingestion API with a data collection rule into an Analytics-plan custom table | GA | The report events table | n/a | [ingestion tutorial](https://learn.microsoft.com/azure/azure-monitor/logs/tutorial-logs-ingestion-code) |
| Workbooks as Bicep (`Microsoft.Insights/workbooks`) | GA | Dashboards kept in Git | n/a | [template reference](https://learn.microsoft.com/azure/templates/microsoft.insights/workbooks) |
| Azure Monitor dashboards with Grafana | GA (announced at Ignite in November 2025 per [Grafana](https://grafana.com/blog/azure-monitor-offers-grafana-dashboards-natively-for-immediate-real-time-operational-monitoring-now-ga/); Learn's overview shows no status label) | Optional only | Workbooks | [overview](https://learn.microsoft.com/azure/azure-monitor/visualize/visualize-grafana-overview) |

## Meetings and voice

| Feature | Status | Used for | If missing | Source |
|---|---|---|---|---|
| Bot in a meeting chat; side-panel tab | GA | Not used: there is no bot | The one-to-one message | [meeting chat](https://learn.microsoft.com/microsoftteams/platform/apps-in-teams-meetings/build-extensible-conversation-for-meeting-chat) |
| Graph meeting transcripts | GA; off by default: an administrator turns Graph access on, and speaker attribution, a second setting, is off by default (the default `text/vtt` then returns an error, so the module asks for unattributed text) | Post-meeting read | The module says so and carries on | [transcript access](https://learn.microsoft.com/microsoftteams/meeting-transcript-api-access), [get transcript content](https://learn.microsoft.com/graph/api/calltranscript-get?view=graph-rest-1.0) |
| Real-time media bot | Developer preview; not recommended for AI agents | Not used | n/a | [real-time media](https://learn.microsoft.com/microsoftteams/platform/bots/calls-and-meetings/real-time-media-concepts) |
| Voice Live API | GA over WebSocket; WebRTC is preview. For either transport recognition, voice and model processing have separate scopes, possibly outside the resource's region | A voice session on a web page, over WebSocket, after all three scopes are validated | Text | [Voice Live](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live), [regions](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=voice-live#regions) |
| Standard text-to-speech avatar | Some characters are preview; six are based on actors; custom avatars and voices are Limited Access | Not used unless the vendor confirms a character's origin; disclosure is mandatory | No avatar | [standard avatars](https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech-avatar/standard-avatars), [transparency note](https://learn.microsoft.com/azure/foundry/responsible-ai/speech-service/text-to-speech/transparency-note) |

## Review surfaces

| Feature | Status | Used for | If missing | Source |
|---|---|---|---|---|
| GitHub check run: Markdown up to 65,535 characters, images, up to three buttons | GA | The review card of a knowledge change | A pull-request comment | [checks API](https://docs.github.com/en/rest/checks/runs) |
| Rulesets, and an app with no Contents write on the base repository | GA | The app proposes from a fork and posts checks; merging needs Contents write ([merge API](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request)), so only people merge | n/a | [rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) |
| Issue forms | Issues only, not pull requests | A pull-request template carries the checklist | n/a | [issue forms](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms) |
| Copilot code review | GA on GitHub; public preview on Azure DevOps | A second opinion, never the reviewer | Human review | [code review](https://docs.github.com/en/copilot/concepts/agent-capabilities/agent-powered-workflows-and-operations/code-review) |
| Azure DevOps: automatically included reviewers, PR statuses | GA; each policy is Required or Optional and only Required blocks a merge; no CODEOWNERS file | The same two jobs, both Required from creation | n/a | [branch policies](https://learn.microsoft.com/azure/devops/repos/git/branch-policies-overview?view=azure-devops) |

## Standards and rules

| Rule | Status | Effect on the experience | Source |
|---|---|---|---|
| WCAG 2.2 AA | W3C Recommendation since 5 October 2023 | The bar for pages, letters and cards | [WCAG 2.2](https://www.w3.org/TR/WCAG22/) |
| EN 301 549 | Version 3.2.1 carries the presumption of conformity; 4.1.1 (WCAG 2.2) is not yet cited | Meet the higher bar voluntarily | [AccessibleEU Centre](https://accessible-eu-centre.ec.europa.eu/content-corner/news/european-accessibility-standard-en-301-549-has-been-updated-2026-09-07_en) |
| EU AI Act Article 50 | Applies from 2 August 2026; paragraph 5 requires accessible, clear notices; marking grace to 2 December 2026 for systems already on the market, as reported by the Commission | The AI label, the footer line and the machine-readable mark; whether the duties are a provider's or a deployer's is for the adopting organisation to assess | [Article 50](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-50) |
| EU AI Act Article 14(4) | High-risk systems from 2 December 2027 and 2 August 2028 | A design reference, not a classification | [Article 14](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14) |
| European Accessibility Act | Does not cover an internal tool for employees | Not a legal trigger | [Directive 2019/882](https://eur-lex.europa.eu/eli/dir/2019/882/oj) |

## What this register does not claim

A Teams message that interrupts Do Not Disturb or always reports a read; Actionable Messages from a shared mailbox; an avatar that joins a live Teams meeting; a generally available real-time media bot; an error-bar chart in Workbooks; the legal force of EN 301 549 version 4.1.1; the exact clause of the Article 50 marking grace (stated as reported, not as read on EUR-Lex).
