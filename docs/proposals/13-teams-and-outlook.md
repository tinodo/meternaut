# Teams and Outlook: a card in Teams, a letter in Outlook — a decision record

**Status: deployed, and run on 2026-11-11: a test card and three real requests reached the owner's Teams chat.** The app puts each card on a private queue; a Power Automate flow, described in [proposal 19](19-teams-cards-through-power-automate.md), reads the queue and posts the card. The app cannot tell whether a card arrived (the flow's run history says: `tools/powerplatform.py flow-runs`). Microsoft facts below name their page and were read on 2026-11-11.

## What a person sees

**In Teams** a card arrives in a chat with the person, posted by the Flow bot of Power Automate (the sender is the platform's, not "Meternaut"). The card is the one of [the card rules](../experience/04-messages-and-cards.md) without its buttons and boxes: the headline, the saving with its level and basis, three facts each with its source, one line each for the change, the undo and the risk, and one footer line (written by an AI, why you got this, whom to talk to). It has **one link**, the page of the request. A change has the link "Review and decide": signing in to Azure and approving happen on the page, and **an approval that changes Azure is never taken from Teams**. When a switch holds the answers the card says so and its link reads "See the request". A card takes no answer: it has no box, no `Action.Submit` and no `Action.Execute`, so nothing can be declined, asked or taught in Teams.

**The first card.** A person who chose Teams and was never told gets one welcome card before the first request. It says that Meternaut writes in Teams, that a card cannot be answered, and where the page is.

**Who gets a card.** The person's channel setting decides (`email`, `teams`, `desk`). With `teams` the card goes first, and the letter follows only if no card was put on the queue within 20 minutes; a card and a letter never both go for one request. A card that could not be put on the queue is tried every 15 minutes, up to 12 times, and then the letter goes. Advice cards count against the weekly budget of letters. Inside a person's quiet hours no card is sent; the round that offers cards writes nothing while the hours last, so waiting uses no try.

**In Outlook** nothing changes: the letters from the shared mailbox stay, as the audit-safe fallback. Outlook actionable messages are not built. Since 2026-06-08 only Microsoft Entra tokens are accepted, which needs an app registration with an exposed API, a pre-authorised Microsoft app and a tenant-wide consent, and the recipient needs an individual mailbox ([Entra token](https://learn.microsoft.com/outlook/actionable-messages/enable-entra-token-for-actionable-messages)); the design avoids all of that.

## The path of a card

1. The app decides that a person who chose Teams is to be told, builds the card from the decision brief and checks it ([`cardcheck.py`](../../src/case-functions/cases/cardcheck.py)).
2. It puts one message on the queue `teams-cards` in the storage account of the base: the REST call "Put Message" with a token of the app's managed identity, over the private endpoint. No key, no connection string. The app already holds the right to write to the queues of that account.
3. A Power Automate cloud flow reads the queue through Power Platform's virtual network support, so the queue has no public endpoint, and posts the card with the Teams action "Post card in a chat or channel": poster Flow bot, post in "Chat with Flow bot", recipient the message's `to`.
4. Nothing comes back. The app records that the queue took the message, not that anyone saw a card.

## The message on the queue

One JSON text, UTF-8, not base64, at most 30,000 bytes. The queue's name is the app setting `TEAMS_CARDS_QUEUE`; with no value the app sends no cards.

| Field | Content |
|---|---|
| `v` | `1`, the version of this format |
| `id` | The delivery id: the id of the record that the app keeps of this card (letters, digits, hyphen and underscore; at most 64) |
| `to` | The person's mail address, as the people list has it. Taken only from the people list, not from a resource name, a tag or any other text of the estate |
| `title` | A short plain title, one line, at most 120 characters |
| `card` | The Adaptive Card, schema 1.4 |

A card that does not fit in 30,000 bytes is replaced by a minimal card with the headline and the link; the JSON is never cut. The message lives 24 hours on the queue and then lapses. A text that is not an address on the people list is refused by the app before anything is put on the queue.

## What the app knows and what it does not

The app knows whether the queue took the message. A refusal, a timeout or a server error is a failed try (the words of the record say what happened, without the token), and the letter still goes when the tries are used up. The app does not know whether the flow read the message, whether the Flow bot posted it, or whether the person saw it. **If the flow is off or fails, the person gets no card, and no letter follows a card that the queue took.** The page still lists every request. A receipt from the flow is not in this version; until there is one, delivery is best effort and the cards are never promised.

## No bot, and what that removes

A Teams bot needs an Azure Bot resource, a Teams app package that someone installs, an app registration or a user-assigned identity with a role on the bot channel, a public endpoint that Teams calls, a check of every call's token, and a permission in Microsoft Graph to install the app for a person. Meternaut has none of these. Nothing in Teams calls an endpoint of ours, no permission has to be consented to, and no credential is stored: the queue is read inside the network and written with a managed identity.

What it costs: a card cannot be answered. Taps, replies, a card replaced in place and the typed message to the app are gone; the page and the letters carry every answer.

## What is public

Nothing is new. The queue, the storage account and the app stay private. The flow runs in the Power Platform with a delegated subnet in the project's own network (see the hand steps below). Whoever can write to the queue can put any card, with any link, in front of anyone the flow can address, because the flow posts to the address that the message carries; the project grants that right to the cases app, and the app takes the address from the people list. Such a writer still cannot approve a change, name an approver or reach the estate.

## What Microsoft says (read on 2026-11-11)

| Fact | Source |
|---|---|
| The Teams action posts as the Flow bot, in a chat with the recipient, and needs the recipient's mail address | [Adaptive cards for Teams in Power Automate](https://learn.microsoft.com/en-us/power-automate/overview-adaptive-cards) |
| On a card that a flow posts without waiting for a response only `Action.OpenUrl` works; other actions give an error | The same page |
| A posted message may be about 28 KB; the Flow bot posts 25 times in 300 seconds a connection; the Workflows app must be allowed in the Teams admin center; the Flow bot is not available in GCC | [Microsoft Teams connector](https://learn.microsoft.com/en-us/connectors/teams/) |
| Power Automate posts cards up to schema 1.4 although the Teams pages say 1.5 | An open issue in the Adaptive Cards repository, [8965](https://github.com/microsoft/AdaptiveCards/issues/8965): indirect evidence, not a Learn page |

The cards therefore declare 1.4 and use nothing newer: no `style: heading`, no `metadata`. A card that renders only in part is found by the first card that arrives, not before.

## Costs

The queue costs next to nothing: a few operations for each card and the reads of the flow. There is no Azure Bot resource. The licence of the flow, and of an environment with virtual network support, is not priced here and is not verified.

## What a person does by hand

An administrator of the organisation: allows the Workflows app in the Teams admin center, and sets up the Power Platform environment, the flow and its connection to the queue as [proposal 19](19-teams-cards-through-power-automate.md) says. Each person: chooses Teams in the settings on the web page.

## What is not built

Outlook actionable messages; proof that a card reaches a person, and any receipt from the flow; an answer on a card; a card in a channel; an agent identity for Meternaut in Microsoft Agent 365; a check, in the flow, that the address belongs to the people list.
