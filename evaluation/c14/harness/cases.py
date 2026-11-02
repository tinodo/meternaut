"""A pack for check C14: the claims, the source, the cases, the answer key and the starting values.

A pack is a folder (see pack-template/):

    params.json     the starting values, written down by pull request before any run
    source.json     {"url", "retrieved", "file"}: the public page the new claim must come from
    source.txt      the text of that page as read on the retrieval date (the file named in source.json)
    snapshot/*.json the frozen memory: a few claims, one JSON file each
    control.json    one accepted claim about something unrelated (the control arm)
    cases.json      the unseen cases and the decoys; what the finder sees, never the answer
    key.json        the answer for each case, kept out of every prompt
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .claims import Claim, ClaimError, normalise, parse_claim

KINDS = ("waste", "decoy")
ARMS = ("frozen", "control", "updated")
REQUIRED_PARAMS = (
    "runs_per_arm", "waste_cases", "decoy_cases", "snapshot_claims_min", "baseline_found_max", "updated_found_min",
    "updated_priced_min", "updated_runs_required", "price_tolerance_pct", "max_model_calls",
)
LEAK_WORDS = 6
NAME_LIKE = re.compile(r"^[a-z0-9]+(?:[-_.][a-z0-9]+)+$", re.I)
SMALLEST_LEAKING_AMOUNT = 100


class PackError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Case:
    id: str
    kind: str
    title: str
    facts: dict


@dataclass(frozen=True)
class KeyEntry:
    waste: bool
    monthly_waste_eur: float | None
    tolerance_pct: float | None
    required_any: tuple[str, ...]


@dataclass(frozen=True)
class Source:
    url: str
    retrieved: str
    file: str
    text: str


@dataclass(frozen=True)
class Pack:
    path: Path
    params: dict
    source: Source
    snapshot: tuple[Claim, ...]
    control: Claim
    cases: tuple[Case, ...]
    key: dict[str, KeyEntry]


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PackError([f"{path.name}: missing"])
    except json.JSONDecodeError as e:
        raise PackError([f"{path.name}: not valid JSON ({e})"])


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalise(text).lower())


def shared_run(text: str, source_text: str, min_words: int = LEAK_WORDS) -> str | None:
    """The first run of `min_words` words that `text` shares with the source, or None."""
    source = _words(source_text)
    grams = {" ".join(source[i:i + min_words]) for i in range(len(source) - min_words + 1)}
    words = _words(text)
    for i in range(len(words) - min_words + 1):
        gram = " ".join(words[i:i + min_words])
        if gram in grams:
            return gram
    return None


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def load_pack(path: str | Path) -> Pack:
    """Load and validate a pack, or raise PackError listing every problem."""
    root = Path(path)
    problems: list[str] = []

    params = _load_json(root / "params.json")
    for name in REQUIRED_PARAMS:
        if _number(params.get(name)) is None:
            problems.append(f"params.json: {name} must be a number")
    if problems:
        raise PackError(problems)

    meta = _load_json(root / "source.json")
    try:
        source_text = (root / meta["file"]).read_text(encoding="utf-8")
    except (KeyError, FileNotFoundError):
        raise PackError(["source.json: the file it names is missing"])
    source = Source(str(meta.get("url", "")), str(meta.get("retrieved", "")), meta["file"], source_text)
    if not source.url.startswith("https://") or not re.match(r"^\d{4}-\d{2}-\d{2}$", source.retrieved):
        problems.append("source.json: an https url and an ISO retrieved date")

    snapshot: list[Claim] = []
    for p in sorted((root / "snapshot").glob("*.json")):
        try:
            snapshot.append(parse_claim(_load_json(p)))
        except ClaimError as e:
            problems.extend(f"snapshot/{p.name}: {x}" for x in e.problems)
    control = None
    try:
        control = parse_claim(_load_json(root / "control.json"))
    except ClaimError as e:
        problems.extend(f"control.json: {x}" for x in e.problems)
    ids = [c.id for c in snapshot] + ([control.id] if control else [])
    if len(ids) != len(set(ids)):
        problems.append("claim ids must be unique across the snapshot and the control claim")
    if len(snapshot) < params["snapshot_claims_min"]:
        problems.append(f"snapshot/: {len(snapshot)} claims, and params.json says at least {int(params['snapshot_claims_min'])} "
                        "(the plan's starting value is five to ten)")

    raw_cases = _load_json(root / "cases.json")
    cases: list[Case] = []
    if not isinstance(raw_cases, list):
        problems.append("cases.json: a list of cases")
        raw_cases = []
    for raw in raw_cases:
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS or not isinstance(raw.get("facts"), dict) or not raw.get("id"):
            problems.append(f"cases.json: every case has an id, a kind (waste or decoy), a title and facts: {str(raw)[:80]}")
            continue
        cases.append(Case(str(raw["id"]), raw["kind"], str(raw.get("title", "")), raw["facts"]))
    if len({c.id for c in cases}) != len(cases):
        problems.append("cases.json: case ids must be unique")

    raw_key = _load_json(root / "key.json")
    key: dict[str, KeyEntry] = {}
    for case_id, entry in (raw_key.items() if isinstance(raw_key, dict) else []):
        if not isinstance(entry, dict) or not isinstance(entry.get("waste"), bool):
            problems.append(f"key.json: {case_id}: waste must be true or false")
            continue
        key[case_id] = KeyEntry(
            waste=entry["waste"],
            monthly_waste_eur=_number(entry.get("monthly_waste_eur")),
            tolerance_pct=_number(entry.get("tolerance_pct")),
            required_any=tuple(str(x).lower() for x in entry.get("required_any", [])),
        )

    for c in cases:
        k = key.get(c.id)
        if k is None:
            problems.append(f"key.json: no answer for case {c.id}")
        elif (c.kind == "waste") != k.waste:
            problems.append(f"{c.id}: the kind and the key disagree")
        elif k.waste and not (k.monthly_waste_eur and k.monthly_waste_eur > 0):
            problems.append(f"{c.id}: a waste case needs a positive monthly_waste_eur in the key")
        for text in _strings(c.facts) + [c.title]:
            shared = shared_run(text, source.text)
            if shared:
                problems.append(f"{c.id}: shares words with the source, so it is not unseen: {shared!r}")
                break
    for extra in sorted(set(key) - {c.id for c in cases}):
        problems.append(f"key.json: {extra} is not a case")

    waste_n = sum(1 for c in cases if c.kind == "waste")
    decoy_n = len(cases) - waste_n
    if waste_n != params["waste_cases"] or decoy_n != params["decoy_cases"]:
        problems.append(f"params say {params['waste_cases']} waste cases and {params['decoy_cases']} decoys; cases.json has {waste_n} and {decoy_n}")

    if problems:
        raise PackError(problems)
    return Pack(root, params, source, tuple(snapshot), control, tuple(cases), key)


def pack_hashes(pack: Pack) -> dict[str, str]:
    """Hashes that the report records, so that a file changed after the first run shows."""
    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    snapshot = json.dumps([c.to_dict() for c in pack.snapshot], sort_keys=True).encode("utf-8")
    return {
        "params": sha(pack.path / "params.json"),
        "cases": sha(pack.path / "cases.json"),
        "key": sha(pack.path / "key.json"),
        "source": sha(pack.path / pack.source.file),
        "snapshot": hashlib.sha256(snapshot).hexdigest(),
        "control": sha(pack.path / "control.json"),
    }


def _names(case: Case) -> list[str]:
    """What identifies a case: its id and every name-like value in its facts (for example `shop-search`)."""
    values = [s.strip() for s in _strings(case.facts)]
    return [case.id] + [v for v in values if len(v) >= 5 and NAME_LIKE.match(v)]


def _amount_forms(value: float) -> list[str]:
    """The ways a person writes an amount: 1168, 1,168, 1168.00, 1,168.00 and 1,168.5."""
    forms = {f"{value:g}", f"{value:.2f}", f"{value:,.2f}", f"{value:,.2f}".rstrip("0").rstrip(".")}
    if float(value).is_integer():
        forms |= {str(int(value)), f"{int(value):,}"}
    return sorted(forms, key=len, reverse=True)


def copied_from_cases(text: str, cases, key: dict | None = None) -> str | None:
    """The first case that a claim gives away, or None. A claim must not copy a run of five words from a case,
    name a case (its id or a name-like value in its facts), or state the amount that the key gives for a case."""
    lowered = text.lower()
    for case in cases:
        for piece in _strings(case.facts) + [case.title]:
            run = shared_run(text, piece, 5)
            if run:
                return f"{case.id}: {run!r}"
        for name in _names(case):
            if re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", lowered):
                return f"{case.id}: the name {name!r}"
        entry = (key or {}).get(case.id)
        if entry and entry.monthly_waste_eur and entry.monthly_waste_eur >= SMALLEST_LEAKING_AMOUNT:
            for form in _amount_forms(entry.monthly_waste_eur):
                if re.search(rf"(?<![0-9.,]){re.escape(form)}(?![0-9])", text):
                    return f"{case.id}: the amount {form} that the key gives"
    return None
