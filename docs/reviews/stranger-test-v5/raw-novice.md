# Stranger test (novice). Model: GitHub Copilot agent (model identifier not exposed to this session). Files read, in order: README.md; docs/01-north-star.md; docs/design/README.md.

Snapshot note: docs/design/README.md changed during review (a repeated sentence is gone; glossary rows added at lines 59–60). Line numbers are current.

## Explain it back

Azure Cost in Action is a proposed, not yet built, MIT-licensed set of AI agents on Microsoft Foundry and Microsoft Agent Framework. It watches an Azure estate's spend and usage, investigates waste, challenges its own findings, asks owners short questions, and changes Azure only after a person approves that exact plan, or inside a rule a person wrote.

It learns services it has never seen by reading documentation and price lists, decoding each meter with a "Cost Grammar" of fourteen mechanisms, and publishing a provisional, documented-only profile. Bills, replays of past usage, owner answers and rare owner-approved trials then confirm or refute it. It never deploys resources to learn.

Approvals: agents read and propose. One runner writes to Azure. Purchases need two named humans. People grant autonomy per domain, based on a report card.

Subscription-only access: it works within the subscriptions it can reach. With cost access it prices at bill rates, per subscription. Without cost access it estimates at list prices and says so. Partner-sold or central-billing estates: it prepares the purchase request for whoever holds billing reach, then watches the bill to confirm it happened.

**Could not answer from these three files:**
- Which five hosted agents carry the ten roles, and what the seven workflows are.
- How the Cost Grammar recognises the shape of an unseen meter.
- How the partner (CSP) path exposes prices and bills.
- Where the system itself runs, and who needs deploy rights there.
- What "Citadel" is, and the preview or GA status of hosted agents.
- Which content the MIT licence covers, and the Atlas and Commons licence.
- What the version labels (Ideation v5, Design v3) mean, and the measure targets.

## 1. Verdict

Mostly. A newcomer grasps the idea in a minute, and the Azure facts I checked largely hold, but the contract rules, access rules and worked examples contradict each other, and a named person appears in an unlabelled, invented case.

## 2. Findings

`north star` = docs/01-north-star.md · `design` = docs/design/README.md · class numbers as in the brief.

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | README.md:27–30 | 6 | "for Priya Nair"; "her answer teaches it" | Named person, invented quote and figures, unlabelled; reads as a real case. | Mark "(illustrative, invented)"; use a role, not a name; cut the quote. |
| 2 | Major | north star:126, 128 | 4 | "This goes from free to paid on 1 March." | Conflicts with the preview-price "time cliff" (126) and with bills already charging (128). | "This goes from preview pricing to list pricing on 1 March." |
| 3 | Major | north star:222–226, 314–322 | 4, 6 | "[documented only, no bill line yet]" beside "Refuted (3 bill lines)" | The Monday email contradicts itself; 9%, €2,300 and 81% read as measured. | Label the example and email "illustrative, invented"; at 314 write "(provisional; 3 bill lines in)". |
| 4 | Major | north star:164 | 4 | "A role granted tomorrow is noticed tomorrow." | The same bullet probes weekly, so detection can take seven days. | "A role granted tomorrow is noticed at the next weekly probe." |
| 5 | Major | design:3, 79 | 4 | "the accelerator deployed from this repository"; "Nothing is built yet" | Implies a deployable artefact that the status says does not exist. | "a Citadel hub (the organisation's own, or Microsoft's open-source sample)". |
| 6 | Major | north star:160, 345; design:79 | 4 | "Subscription reach without costs"; "read access to cost data"; "It knows when your commitments end" | North star says the no-cost tier works; design requires cost access. | Design: "read access to cost data (without it: usage and list prices, north star §5)". Line 345: add "with billing reach". |
| 7 | Major | design:79 | 5 | "billing-level roles unlock price sheets and purchases" | Learn's Price Sheet API is per subscription and names no billing role (check 4). | Name the gating role with a Learn link, or delete the claim. |
| 8 | Major | README.md:19; north star:151; design:92 | 4, 5 | "bought directly or through a partner"; "a partner (CSP)" | Three classifications of partner-sold Azure; Learn's MCA page does not describe MCA as partner-sold (check 3). | One list everywhere: "EA · MCA (direct) · partner (CSP) · pay-as-you-go". |
| 9 | Major | north star:356 | 4 | "Built on Microsoft's own frameworks." | The FinOps Framework belongs to the FinOps Foundation; breaks README:60. | "Built on Microsoft's frameworks, and aligned with the FinOps Framework (FinOps Foundation)." |
| 10 | Major | north star:240, 283 | 3, 4 | "never a byte of customer data"; "Estate knowledge never leaves the customer." | Privacy promise with no mechanism; "anonymised observations" come from customer bills. | Name the mechanism (threshold, review, exclusions) or cut "never a byte"; say what leaves an estate. |
| 11 | Major | north star:17–18 | 6 | "thousands of accidental experiments a month" | Unsourced numbers; "the bill records each result" overclaims. | Cite a count and date, or write "many"; "each change shows up as a bill line". |
| 12 | Major | README.md:13–17 | 6 | "it learns how every Azure service really charges" | Present tense for an unbuilt system; the status arrives at line 58. | Add "is designed to" to each bullet. |
| 13 | Major | north star:267, 352, 412; design:14, 42, 64, 67 | 2, 4 | "not scripts" vs "plain code"; "Earned, revocable permission" vs "An autopilot rule a person wrote"; "One contract per hosted agent" | Workflow, credential and contract mean different things across files. | Workflow = plain code; one credential definition; rename the hub "Contract" to "hub policy". |
| 14 | Minor | north star:4, 13, 24, 46, 87, 134, 352, 362, 420; README.md:21, 60; design:9, 64 | 1 | "It is **not** a rulebook, a chatbot or a dashboard." | Denials of positions no reader was given; line 420 is term-cleanup residue. | Delete (section 3). |
| 15 | Minor | README.md:13, 37; north star:67, 139, 177, 239, 267 | 2 | "claims with receipts"; "the Atlas"; "control meters"; "revoked when regret appears" | Undefined on first use; "Ledger" names two things (67, 177). | Gloss on first use; rename the experience store "Outcome Ledger". |
| 16 | Minor | design:33; north star:365 | 3 | "so learning adds nothing to the Azure bill" | Trials change running resources (north star:241), so the bill can move. | "Learning deploys nothing; its only Azure writes are owner-approved trials." |
| 17 | Minor | design:40, 81 | 4 | "Scales to zero"; "an always-ready function instance" | A fixed always-ready instance contradicts scale-to-zero, unexplained. | "Scales to zero, except one always-ready instance kept for latency (a fixed cost)." |
| 18 | Minor | README.md:53; design:75 vs north star:418 | 4 | "fifteen short documents"; "written once from a confirmed finding" | Fifteen counts the index; the Detector drops "expiring". | "fourteen documents plus this index"; add "scoped, expiring" to the design glossary. |
| 19 | Minor | README.md:60, 63; design:73 | 4 | "Microsoft technology only" | Git, FOCUS and Python break the principle as written. | "Microsoft technology for the product; standards and repo tooling are excepted." |
| 20 | Minor | north star:55, 122, 322; README.md:9; design:63 | 2, 3, 6 | "(I said 79%)"; "not a closed list"; "A sceptical agent"; "a bottleneck nobody talks about" | "Every meter … fourteen mechanisms" (122) contradicts "not a closed list"; spelling clashes with "Skeptic". | "(last month: 79%)"; "Most meters are one or a few of fourteen mechanisms"; "skeptical"; delete "nobody talks about" and design:63's RBAC sentence. |

## 3. Sentences I would delete

1. README.md:21 — "It is **not** a rulebook, a chatbot or a dashboard." — delete.
2. README.md:60 — "· not a chatbot" — delete.
3. north star:13 — "Not a rulebook." — delete.
4. north star:46 — "The scientific method is not a metaphor here; it is the operating system." — delete.
5. north star:87 — "there is no "first"" — delete the clause.
6. north star:134 — "Not an inventory —" — delete.
7. north star:352 — "Chat is one way to ask the system a question; it is not the product." — delete.
8. north star:362 — "Human-in-the-loop is not a button on the end." — delete; "It is five places:" becomes "Human-in-the-loop has five places:".
9. north star:420 — "every term, with the one word kept for each —" — delete.
10. design:9 — "It is not a chatbot:" — delete.

## 4. Fact checks

1. north star:143, "Advisor's own documentation says it prices shutdown savings at retail rates." https://learn.microsoft.com/en-us/azure/advisor/advisor-cost-recommendations — **Supported**: the Limitations section says savings "are based on retail rates".
2. north star:222, "traffic between availability zones is not [billed per gigabyte]". https://learn.microsoft.com/en-us/azure/availability-zones/az-overview — **Supported**: "Azure doesn't charge for data transfer between availability zones in the same region."
3. README.md:19; north star:151; design:92 (MCA through a partner). https://learn.microsoft.com/en-us/azure/cost-management-billing/understand/mca-overview — **Not supported as written**: the page does not describe MCA as partner-sold. It says only that CSP-bought Azure "might" show a partner billing profile.
4. design:79, "billing-level roles unlock price sheets". https://learn.microsoft.com/en-us/rest/api/consumption/price-sheet/get — **Unsupported**: the endpoint is per subscription (`/subscriptions/{subscriptionId}/providers/Microsoft.Consumption/pricesheets/default`) and names no billing role. Not verified either way.
5. design:66, 79, Citadel as "an open-source sample". No URL. **Could not verify**: one Learn search found no page mentioning Citadel.

## 5. Questions left unanswered

1. Which role gates price sheets and cost data for each contract, and what does a partner-sold (CSP) estate expose? (north star:158–160; design:79, 92)
2. Where does the system itself run, and who needs deploy rights there? (design:79)
3. Which of the five hosted agents carries which of the ten roles, and what are the seven workflows? (README.md:53)
4. How does the Cost Grammar recognise an unseen meter, and what happens when it is misclassified? (north star:116)
5. Under what licence are the Atlas and Commons published, given that MIT covers the repository? (README.md:59; north star:283)
