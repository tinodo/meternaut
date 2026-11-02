"""A scripted stand-in for a model, for the demonstration of the pipeline and for the tests.

It knows the invented mechanism of pack-template (a Prism replica bills per hour whether or not it serves
a query) only when a claim that says so is in the memory it is shown, which is what the real arms test.
"""
from __future__ import annotations

import json
import math

from .cases import Source
from .claims import quote_hash

REPLICA_QUOTE = "Each replica is billed per hour for every hour it is provisioned, whether or not it serves any query."
CLAIM_ID = "prism-replica-billing"


def proposer_reply(source: Source) -> str:
    return json.dumps({
        "id": CLAIM_ID,
        "statement": "A Prism replica is billed per hour for every hour it is provisioned, whether or not it serves a query.",
        "mechanism": ["capacity"],
        "scope": {"service": "Azure Prism (invented)", "region": "any", "offer": "any", "sku_or_version": "any",
                  "scale": "any", "date": source.retrieved},
        "level": "documented",
        "quote": REPLICA_QUOTE,
    })


def finder_reply(user: str) -> str:
    memory, _, facts_text = user.partition("Resource facts (JSON):\n")
    knows = "billed per hour for every hour" in memory
    facts = json.loads(facts_text)
    none = json.dumps({"waste": False, "monthly_waste_eur": None, "price_basis": "", "claim_ids": [],
                       "explanation": "Nothing in the memory or the facts shows waste.", "action": "none"})
    replicas = facts.get("replicas")
    if not knows or not isinstance(replicas, int):
        return none
    needed = max(1, math.ceil(facts["peak_queries_per_minute"] / facts["capacity_per_replica_queries_per_minute"]))
    if "availability_requirement" in facts:
        needed = max(needed, 2)
    if replicas <= needed:
        return none
    waste = round(facts["monthly_cost_eur"] * (replicas - needed) / replicas, 2)
    return json.dumps({
        "waste": True, "monthly_waste_eur": waste, "price_basis": "the monthly cost shared by replica",
        "claim_ids": [CLAIM_ID],
        "explanation": f"Every replica bills per hour whether or not it serves a query, and {replicas - needed} replicas are more than the load needs.",
        "action": f"Reduce the replica count from {replicas} to {needed}.",
    })


def handler(system: str, user: str) -> str:
    if system.startswith("You read one passage"):
        source = Source("", user.split("Retrieved: ", 1)[1].split("\n", 1)[0], "", "")
        return proposer_reply(source)
    return finder_reply(user)


__all__ = ["handler", "proposer_reply", "finder_reply", "REPLICA_QUOTE", "CLAIM_ID", "quote_hash"]
