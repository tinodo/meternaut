"""The two prompts of the demonstration: the finder that answers a case, and the proposer that writes a claim."""
from __future__ import annotations

import json

from .cases import Case, Source
from .claims import MECHANISMS, Claim, render_for_prompt

FINDER_SYSTEM = (
    "You review one Azure resource for cost waste. You are given what is known about how Azure bills "
    "(the memory: claims, each with an id) and the facts of one resource. You may also use what you know "
    "about Azure; say so in price_basis when an amount does not come from the memory or the facts. "
    "Say there is waste only when the facts show money spent on something that is not needed. "
    "If the memory and the facts do not show it, say there is no waste.\n"
    "Reply with one JSON object and nothing else: "
    '{"waste": true or false, '
    '"monthly_waste_eur": a number, or null when there is no waste, '
    '"price_basis": "where the amount comes from, in a few words", '
    '"claim_ids": [the ids of the memory claims you relied on], '
    '"explanation": "one or two sentences", '
    '"action": "the change you would propose, or none"}.'
)

PROPOSER_SYSTEM = (
    "You read one passage from a public Azure documentation page and write one claim about how Azure bills, "
    "for a knowledge base. Write only what the passage says. Copy the quote exactly from the passage, "
    "in one or two sentences, without changing a word.\n"
    "Reply with one JSON object and nothing else: "
    '{"id": "a-short-slug", '
    '"statement": "what the page says, in one or two sentences, with the conditions under which it holds", '
    '"mechanism": [one or two of: ' + ", ".join(MECHANISMS) + "], "
    '"scope": {"service": "...", "region": "...", "offer": "...", "sku_or_version": "...", "scale": "...", '
    '"date": "the retrieval date given below"}, '
    '"level": "documented", '
    '"quote": "the exact words from the passage that carry the claim"}. '
    'Write "any" for a scope the page does not limit.'
)


def finder_user(memory: list[Claim], case: Case) -> str:
    claims = "\n".join(f"- {render_for_prompt(c)}" for c in memory) if memory else "none"
    facts = json.dumps(case.facts, indent=2, sort_keys=True, ensure_ascii=False)
    return f"Memory:\n{claims}\n\nResource facts (JSON):\n{facts}"


def proposer_user(source: Source) -> str:
    return f"Source: {source.url}\nRetrieved: {source.retrieved}\n\nPassage:\n{source.text.strip()}"
