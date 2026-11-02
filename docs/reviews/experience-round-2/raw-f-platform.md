# Cold-reader review: platform and compliance

## Verdict

No: a stranger can follow the intent, but cannot safely build these surfaces. Platform and test guarantees conflict with sources and scripts.

## Findings

Paths are relative to `docs/experience/` unless prefixed `design/` (`docs/design/`) or `tools/`.

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | `09-reviewers-and-contributors.md:91`; `13-platform-register.md:78` | 5 | “The GitHub App cannot merge” | Contents write permits the merge API after required rules pass; exclusion from bypass only prevents skipping rules. [G] | Draft in a separate fork; deny the checks app base-repository Contents write and restrict merging to people. |
| 2 | Blocker | `13-platform-register.md:12`; `cards/your-ok.json:4-5` | 5, 8 | “an older client opens the page instead” | Clients below schema 1.5 see `fallbackText`, not the nested action fallback; C4's text has no link. [L2] | Send a trusted page link or e-mail for clients below 1.5; retain action fallback for compatible hosts. |
| 3 | Blocker | `13-platform-register.md:27` | 5 | “A bot cannot post there” | This groups private and shared channels. Current Learn describes agent responses in enabled shared channels, while private-channel posting remains restricted. [L3] | “Private-channel agent posts are unsupported; shared-channel agents can respond when enabled. This project uses neither.” |
| 4 | Blocker | `13-platform-register.md:61` | 5 | “Dashboards with Grafana”; “Preview” | Azure Monitor dashboards with Grafana became GA in November 2025. [V] | “Azure Monitor dashboards with Grafana: GA; optional by project choice.” |
| 5 | Blocker | `10-voice-and-meetings.md:20,42,90` | 4, 8 | “It stores nothing and mines nothing else” | The summary persists in chat and an extracted request proceeds to a persistent Case (`design/05-data-and-integrations.md:31`). The notice discloses only chat retention. | “The transcript is not retained; the chat keeps the summary and authorised requests become Cases under the configured retention policy.” |
| 6 | Blocker | `10-voice-and-meetings.md:52,90` | 4, 8 | “counts and report-card figures” | The example posts a resource-specific request to the shared chat, contradicting the aggregate-only rule and exposing it to the chat audience. | Post aggregate counts only; route resource-specific requests privately to their authorised owner. |
| 7 | Blocker | `12-testing-the-experience.md:30,36` | 4, 8 | “no label; a required input without an error message” | In-memory mutations show an unlabelled required input inside a top-level ShowCard and a top-level `Action.Http` both pass lint (`tools/cardlint.py:119,176`). | Walk all top-level actions and nested cards for element and input validation; add both regression tests. |
| 8 | Major | `09-reviewers-and-contributors.md:93` | 5, 8 | “automatically included reviewers” | Reviewers and status policies can be optional; conditional status can also fail to block. [L1] | Require both policies from PR creation, exclude the author, reset on changes, and deny bypass. |
| 9 | Major | `09-reviewers-and-contributors.md:55,58-74` | 4, 8 | “new commits send a change back to proposed” | The diagram omits that transition from checked and in-review; check buttons also appear only after completion. Neutral checks can pass branch protection. [G] | Complete the check as `action_required` until a decision; reset on every new head or changed diff and dismiss stale reviews. |
| 10 | Major | `09-reviewers-and-contributors.md:25` | 8 | “automatic ‘quote found at the URL’ check” | Contributor-controlled URLs and redirects have no specified fetch boundary, allowing requests to private services or metadata endpoints. | Fetch only public HTTPS destinations, revalidate redirects and DNS, isolate credentials, and cap response size and time. |
| 11 | Major | `13-platform-register.md:68`; `10-voice-and-meetings.md:20` | 5, 8 | “speaker attribution is a separate setting” | Attribution defaults off. Graph's default `text/vtt` then returns `SpeakerAttributionNotAllowed`; the read has no specified format fallback. [L4] | Request unattributed transcript text when attribution is off; never infer a speaker; report Graph-access denial separately. |
| 12 | Major | `10-voice-and-meetings.md:46-47` | 4, 8 | “a refusal means no capture” | Teams already captured the transcript; this module can only prevent its own read. Anonymous participants cannot invoke the bot. [L4] | “Refusal prevents this app reading the existing transcript, not Teams transcription; anonymous and phone participants can tell the organiser.” |
| 13 | Major | `10-voice-and-meetings.md:21`; `13-platform-register.md:70` | 5, 8 | “WebRTC is preview and processes sessions in the nearest region” | WebSocket does not guarantee local processing either: recognition, voice and inference have separate scopes and can leave the resource region. [L5] | Validate and record all three processing scopes for either transport; use text when none fits the approved boundary. |
| 14 | Major | `10-voice-and-meetings.md:25,49` | 3, 8 | “nor describes as based on a real actor” | Absence of an actor label does not prove the promised absence of a real person's likeness. | Pin an available character only after affirmative vendor confirmation of its origin; otherwise use no avatar. |
| 15 | Major | `12-testing-the-experience.md:14,55` | 4 | “snapshots in light, dark and high contrast” | Only light exists today; the renderer is JavaScript-only, so .NET parity is unproved. | “Today JavaScript renders light output; .NET parity and dark and high-contrast snapshots are planned.” |
| 16 | Major | `12-testing-the-experience.md:15` | 3, 8 | “every template and language”; “a miss is a missing line” | Question cards need not have a plan or saving; a miss can also be a model error. | Mark questions applicable per card; treat mismatches as review signals, not proof. |
| 17 | Major | `12-testing-the-experience.md:34`; `tools/cardlint.py:185` | 4, 8 | “Over 24 characters or only symbols” | The Latin-only test rejects the Chinese word `保存` as symbols; the in-memory test confirms it. | Accept Unicode letters and test CJK and Arabic titles, including expanded values. |
| 18 | Major | `12-testing-the-experience.md:76` | 8 | “Minutes of attention per decision, from the first tap or page view” | Elapsed time includes idle time and excludes reading before the first interaction; it is not attention. | “Measure elapsed time from first observable interaction; estimate active attention separately in consented studies.” |
| 19 | Major | `12-testing-the-experience.md:72`; `15-asks-of-the-technical-design.md:37` | 8 | “No individual figure goes to a manager” | Five-person suppression and removing IDs do not prevent subtraction across overlapping groups or periods. | Suppress complementary and differencing results, restrict dimensions, and test reconstruction across releases. |
| 20 | Major | `13-platform-register.md:48`; `12-testing-the-experience.md:63` | 4, 8 | “use a device where your security key or passkey is available” | A key can be present while Teams opens an unsuitable embedded view; the fallback differs from the tested e-mail route. | Offer the tested e-mail link that opens the system browser; do not blame the person's device. |
| 21 | Major | `15-asks-of-the-technical-design.md:21-22` | 4, 8 | “works once”; “A forwarded or old card can still be tapped” | If the first response consumes the code, the second fails. The design already checks expiry, hash and consumption (`design/05-data-and-integrations.md:160-176`). | Make the code display-only; accept two authenticated responses, consume the plan once, and describe the remaining forwarding gap. |
| 22 | Major | `15-asks-of-the-technical-design.md:23` | 8 | “any approval that arrives without a tap raises an alarm” | A stolen session or automated UI can produce the same action event; the service cannot prove a physical human tap. | Validate the action and alert on anomalies; state that this does not prove human intent. |
| 23 | Major | `15-asks-of-the-technical-design.md:25`; `cards/done.json:88-92` | 8 | “it revokes the approval” | The button also appears after execution, when a consumed approval cannot recall a change or purchase. | Revoke unused approvals; after consumption preserve the audit, stop remaining work where possible, and start incident and rollback handling. |
| 24 | Major | `15-asks-of-the-technical-design.md:30` | 4 | “An external e-mail path” | The allow-listed sender and partner request already exist in `design/05-data-and-integrations.md:152` and `design/14-agreements-and-access.md:115-119`. | Ask only for the missing external flag, data minimisation and subject-line rule; retain the existing path. |
| 25 | Major | `15-asks-of-the-technical-design.md:31` | 4, 5 | “Machine-readable AI marks” | `design/06-security-and-governance.md:257` already asks for these. If “card metadata” means the root property, it requires 1.6, not 1.5; a header alone does not establish Article 50 compliance. [L2, E] | Specify supported message-activity metadata and test mark survival; assess provider duty and exceptions. |
| 26 | Minor | `13-platform-register.md:5` | 3 | “Generally available (GA): used freely” | GA does not mean free of cost, permissions, licensing, regional or quota limits. | “GA means supported for production, subject to availability, permissions, licensing, quotas and cost.” |
| 27 | Minor | `10-voice-and-meetings.md:32` | 1 | “This project does not compete with them.” | Answers an objection nobody raised. | Delete. |

## Sentences I would delete

- `10-voice-and-meetings.md:32`: “This project does not compete with them.”
- `10-voice-and-meetings.md:56`: “Look at the middle: every module starts from or returns to the written flows, and nothing changes anywhere else.”
- `12-testing-the-experience.md:98`: “Look at the template in the middle: every layer examines it and sends one kind of finding back.”

## Fact checks

Five Microsoft Learn checks, read 2026-11-02:

1. **[L1] Azure DevOps reviewer enforcement:** [branch policies](https://learn.microsoft.com/azure/devops/repos/git/branch-policies?view=azure-devops) distinguish Required and Optional; author-vote and status settings are separate.
2. **[L2] Adaptive Card compatibility:** [root schema](https://learn.microsoft.com/adaptive-cards/schema-explorer/adaptive-card) specifies `fallbackText` below the root version and introduces card `metadata` in 1.6.
3. **[L3] Shared channels:** [channel support](https://learn.microsoft.com/microsoftteams/platform/build-apps-for-shared-private-channels) describes shared-channel agent responses; [agent guidance](https://learn.microsoft.com/microsoftteams/platform/bots/how-to/conversations/channel-and-group-conversations) restricts private-channel posts.
4. **[L4] Meeting transcripts:** [Graph API](https://learn.microsoft.com/graph/api/calltranscript-get?view=graph-rest-1.0) documents RSC, the two 403 cases and unattributed format; [meeting chat](https://learn.microsoft.com/microsoftteams/platform/apps-in-teams-meetings/build-extensible-conversation-for-meeting-chat) says anonymous users cannot invoke bots.
5. **[L5] Voice stack:** [API reference](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-api-reference-2026-07-15) is non-preview; WebRTC is preview. [Regions](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=voice-live#regions) distinguishes processing scopes. [Avatars](https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech-avatar/standard-avatars) marks `vasa-2` preview and names six actor-based; other characters' GA status and non-person origin remain unverified.

Other primary sources:

- **[G] GitHub:** [merge permissions](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request), [check actions and forks](https://docs.github.com/en/rest/checks/runs), and [required-check conclusions](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) support findings 1 and 9.
- **[V] Grafana:** its [GA announcement](https://grafana.com/blog/azure-monitor-offers-grafana-dashboards-natively-for-immediate-real-time-operational-monitoring-now-ga/) dates the change to November 2025.
- **[E] EU AI Act:** the Commission's [timeline](https://ai-act-service-desk.ec.europa.eu/en/ai-act/timeline/timeline-implementation-eu-ai-act) confirms 2 August 2026, the limited 2 December 2026 transition, and Annex III/I dates in 2027/2028. [Article 50](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-50) distinguishes provider duties and exceptions.

All 22 design anchors resolved; 58 register URLs and ten fragments were reachable. `cardlint.py --self-test` passed; finding 7's mutations did not.

## Questions left unanswered

1. How is refusal recorded for late, anonymous or phone joiners before transcript retrieval?
2. What retention and deletion controls apply to requests extracted from a transcript?
3. How are day-five figures corrected when invoices change?
4. Which service and languages support translated captions?
5. How are reviewer permissions and fork-PR identities resolved when check-run `pull_requests` is empty?
