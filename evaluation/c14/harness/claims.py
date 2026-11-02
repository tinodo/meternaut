"""Claims, receipts and the quote check of the learning demonstration (check C14).

A claim has the fields of an Atlas claim (docs/design/04-knowledge-and-learning.md): an id, a statement,
mechanisms from the Cost Grammar, a scope, receipts (source link, retrieval date, quoted text and its hash),
an evidence level and an optional re-check recipe. The Atlas files are YAML; the demonstration reads the
same fields as JSON, so that it needs nothing but the standard library.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

MECHANISMS = (
    "capacity", "consumption", "stock", "flow", "feature", "multiplier", "tier-or-step",
    "commitment", "time-quantum", "coupling", "leftover", "rate-and-benefit", "allowance", "time-cliff",
)
# The two levels that can enter the Atlas; the others live in one estate's ledger.
LEVELS = ("documented", "price-confirmed")
SCOPE_KEYS = ("service", "region", "offer", "sku_or_version", "scale", "date")
RECHECK_KINDS = ("mechanical", "semantic")

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_STATEMENT = 1200
MAX_QUOTE = 400


class ClaimError(ValueError):
    """A claim that does not meet the schema; `problems` lists every reason."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def normalise(text: str) -> str:
    """Collapse whitespace and unify typographic quotes and dashes, so that a quote survives re-wrapping."""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", t).strip()


def quote_hash(quote: str) -> str:
    return hashlib.sha256(normalise(quote).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Receipt:
    url: str
    retrieved: str
    quote: str
    quote_sha256: str


@dataclass(frozen=True)
class Claim:
    id: str
    statement: str
    mechanism: tuple[str, ...]
    scope: dict
    receipts: tuple[Receipt, ...]
    level: str
    recheck: dict | None = field(default=None)

    def to_dict(self) -> dict:
        out = {
            "id": self.id,
            "statement": self.statement,
            "mechanism": list(self.mechanism),
            "scope": dict(self.scope),
            "receipts": [r.__dict__.copy() for r in self.receipts],
            "level": self.level,
        }
        if self.recheck:
            out["recheck"] = dict(self.recheck)
        return out


def _receipt_problems(index: int, data: object) -> tuple[Receipt | None, list[str]]:
    tag = f"receipts[{index}]"
    if not isinstance(data, dict):
        return None, [f"{tag}: an object"]
    problems: list[str] = []
    url, retrieved, quote, digest = (data.get(k) for k in ("url", "retrieved", "quote", "quote_sha256"))
    if not isinstance(url, str) or not url.startswith("https://"):
        problems.append(f"{tag}.url: an https link")
    if not isinstance(retrieved, str) or not DATE_PATTERN.match(retrieved):
        problems.append(f"{tag}.retrieved: an ISO date")
    if not isinstance(quote, str) or not quote.strip():
        problems.append(f"{tag}.quote: required")
    elif len(quote) > MAX_QUOTE:
        problems.append(f"{tag}.quote: at most {MAX_QUOTE} characters")
    if not isinstance(digest, str) or not HASH_PATTERN.match(digest):
        problems.append(f"{tag}.quote_sha256: 64 hexadecimal characters")
    return (None if problems else Receipt(url, retrieved, quote, digest)), problems


def parse_claim(data: object) -> Claim:
    """Build a Claim from parsed JSON, or raise ClaimError listing every problem."""
    if not isinstance(data, dict):
        raise ClaimError(["a claim is a JSON object"])
    problems: list[str] = []

    claim_id = data.get("id")
    if not isinstance(claim_id, str) or not ID_PATTERN.match(claim_id):
        problems.append("id: lower-case letters, digits and hyphens, 3 to 64 characters")

    statement = data.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        problems.append("statement: required")
    elif len(statement) > MAX_STATEMENT:
        problems.append(f"statement: at most {MAX_STATEMENT} characters")

    mechanism = data.get("mechanism")
    if not isinstance(mechanism, list) or not 1 <= len(mechanism) <= 2 or any(m not in MECHANISMS for m in mechanism):
        problems.append("mechanism: one or two of the fourteen Cost Grammar mechanisms")

    scope = data.get("scope")
    if not isinstance(scope, dict):
        problems.append("scope: an object with " + ", ".join(SCOPE_KEYS))
    else:
        for key in SCOPE_KEYS:
            if not isinstance(scope.get(key), str) or not scope[key].strip():
                problems.append(f"scope.{key}: required")
        if isinstance(scope.get("date"), str) and not DATE_PATTERN.match(scope["date"]):
            problems.append("scope.date: an ISO date")

    level = data.get("level")
    if level not in LEVELS:
        problems.append("level: documented or price-confirmed (the other levels belong to one estate's ledger)")

    receipts: list[Receipt] = []
    raw_receipts = data.get("receipts")
    if not isinstance(raw_receipts, list) or not raw_receipts:
        problems.append("receipts: at least one (a claim without a receipt is a rumour)")
    else:
        for i, raw in enumerate(raw_receipts):
            receipt, found = _receipt_problems(i, raw)
            problems.extend(found)
            if receipt:
                receipts.append(receipt)

    recheck = data.get("recheck")
    if recheck is not None and (not isinstance(recheck, dict) or recheck.get("kind") not in RECHECK_KINDS):
        problems.append("recheck: an object whose kind is mechanical or semantic")

    if problems:
        raise ClaimError(problems)
    return Claim(
        id=claim_id, statement=statement.strip(), mechanism=tuple(mechanism), scope=dict(scope),
        receipts=tuple(receipts), level=level, recheck=dict(recheck) if recheck else None,
    )


def verify_receipts(claim: Claim, sources: dict[str, str]) -> list[str]:
    """Problems with a claim's receipts; an empty list means every quote is on its page and its hash is right.

    `sources` maps a source link to the text of that page as read on the retrieval date.
    """
    problems: list[str] = []
    for r in claim.receipts:
        page = sources.get(r.url)
        if page is None:
            problems.append(f"{r.url}: the source text is not available")
            continue
        if normalise(r.quote) not in normalise(page):
            problems.append(f"{r.url}: the quote is not on the page")
        if quote_hash(r.quote) != r.quote_sha256:
            problems.append(f"{r.url}: the quote's hash does not match")
    return problems


def render_for_prompt(claim: Claim) -> str:
    """One claim as the finder sees it: statement, scope and level, never the receipts' page."""
    scope = ", ".join(f"{k}: {claim.scope[k]}" for k in SCOPE_KEYS)
    return f"[{claim.id}] {claim.statement} (mechanism: {', '.join(claim.mechanism)}; scope: {scope}; level: {claim.level})"
