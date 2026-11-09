"""The digest of a plan: what a person approves is exactly what runs.

A plan holds more than the words that a person reads: a family, a resource, the parameters of the change (a VM size, a disk tier), the facts that are checked again right before it,
the place, the time at which it expires and the people who may approve it. The digest is a SHA-256 over the canonical JSON (sorted keys, no spaces, ASCII) of EVERY field of the plan
except the three that change or follow from it: its state (an open plan becomes an approved one and then a used one), the digest itself, and the code that is made from it. So a
change of any other field, by anybody and at any time after the plan was made, gives another digest.

It is kept in the plan, and the eight characters that a person sees as the plan's code are the first eight of it. The sign-in to Azure binds it into the state of its round trip
(delegated.py), and the runner compares it again right before it acts (runner.execute): a plan whose digest is not the one that was approved is refused, and nothing is changed.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json

from ..models import PlanRecord

EXCLUDED = ("state", "digest", "code")
# Why a plan may not be acted on, as fragments of a sentence (no capital, no full stop): the page, the letter and the runner put each in a sentence of their own.
NOT_BOUND = "the request was made before requests were bound to what a person approves"
CHANGED = "something in the request changed after it was made, so it is not the request that was approved"
OTHER = "this approval was made for another request than the one that is stored now"


def canonical(plan: PlanRecord) -> str:
    """The text that the digest is made of: every field of the plan but its state, its digest and its code."""
    fields = {key: value for key, value in dataclasses.asdict(plan).items() if key not in EXCLUDED}
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest_of(plan: PlanRecord) -> str:
    """The SHA-256 of the plan, as 64 lower-case hexadecimal characters."""
    return hashlib.sha256(canonical(plan).encode("ascii")).hexdigest()


def code_of(digest: str) -> str:
    """The code that a person sees: the first eight characters of the digest, in capitals. A reference, not a proof: the proof is the whole digest."""
    return digest[:8].upper()


def sealed(plan: PlanRecord) -> PlanRecord:
    """The plan with its digest and its code made from every other field."""
    digest = digest_of(plan)
    return dataclasses.replace(plan, digest=digest, code=code_of(digest))


def problem(plan: PlanRecord, approved: str) -> str:
    """Why the plan may not be acted on, as a fragment of a sentence, or an empty text when it may: it has a digest, the digest is the one that its fields give now, and it is the one that
    was approved."""
    if not plan.digest:
        return NOT_BOUND
    if digest_of(plan) != plan.digest:
        return CHANGED
    if approved != plan.digest:
        return OTHER
    return ""


def refusal(problem_text: str) -> str:
    """The plain words for a page that refuses an approval because of `problem`."""
    return f"This request cannot be approved: {problem_text}. Nothing is approved. A new message will bring a new request and its code."
