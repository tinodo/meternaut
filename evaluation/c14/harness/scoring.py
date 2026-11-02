"""Scoring for check C14: read an answer, score a case, summarise a run and decide the pass."""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass

from .cases import Case, KeyEntry


@dataclass(frozen=True)
class Answer:
    waste: bool
    monthly_waste_eur: float | None
    price_basis: str
    claim_ids: tuple[str, ...]
    explanation: str
    action: str


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    kind: str
    answered: bool
    flagged: bool
    found: bool            # a waste case flagged as waste, with a cause term when the key lists any
    priced: bool           # found, and the amount inside the tolerance
    false_positive: bool   # a decoy flagged as waste


@dataclass(frozen=True)
class RunSummary:
    found: int
    priced: int
    false_positives: int
    unanswered: int
    waste_cases: int
    decoy_cases: int


def extract_json_object(text: str) -> dict | None:
    """The first JSON object in `text`; models sometimes wrap it in prose or a code fence."""
    start = text.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict):
                        return obj
                    break
        start = text.find("{", start + 1)
    return None


def parse_answer(text: str) -> Answer | None:
    """An Answer, or None when the reply holds no JSON object with a true or false `waste`."""
    obj = extract_json_object(text)
    if not obj or not isinstance(obj.get("waste"), bool):
        return None
    amount = obj.get("monthly_waste_eur")
    amount = float(amount) if isinstance(amount, (int, float)) and not isinstance(amount, bool) else None
    ids = obj.get("claim_ids")
    return Answer(
        waste=obj["waste"],
        monthly_waste_eur=amount,
        price_basis=str(obj.get("price_basis", "")),
        claim_ids=tuple(str(x) for x in ids) if isinstance(ids, list) else (),
        explanation=str(obj.get("explanation", "")),
        action=str(obj.get("action", "")),
    )


def score_case(case: Case, entry: KeyEntry, answer: Answer | None, default_tolerance_pct: float) -> CaseScore:
    if answer is None:
        return CaseScore(case.id, case.kind, False, False, False, False, False)
    if case.kind == "decoy":
        return CaseScore(case.id, case.kind, True, answer.waste, False, False, answer.waste)
    text = f"{answer.explanation} {answer.action}".lower()
    cause_ok = not entry.required_any or any(term in text for term in entry.required_any)
    found = answer.waste and cause_ok
    tolerance = entry.tolerance_pct if entry.tolerance_pct is not None else default_tolerance_pct
    priced = (
        found and answer.monthly_waste_eur is not None
        and abs(answer.monthly_waste_eur - entry.monthly_waste_eur) <= entry.monthly_waste_eur * tolerance / 100
    )
    return CaseScore(case.id, case.kind, True, answer.waste, found, priced, False)


def summarise_run(scores: list[CaseScore]) -> RunSummary:
    return RunSummary(
        found=sum(s.found for s in scores),
        priced=sum(s.priced for s in scores),
        false_positives=sum(s.false_positive for s in scores),
        unanswered=sum(not s.answered for s in scores),
        waste_cases=sum(s.kind == "waste" for s in scores),
        decoy_cases=sum(s.kind == "decoy" for s in scores),
    )


def decide(runs: dict[str, list[RunSummary]], params: dict, *, quote_ok: bool, review_ok: bool, within_cap: bool | None,
           answers_ok: bool | None = None) -> dict:
    """The pass conditions of check C14, each with its figures. `within_cap` is None until the cost is known;
    `answers_ok` is None until a person who did not build the harness has read the updated answers.

    Frozen and control are the two baselines: each is judged by the median of its runs against the same bar.
    A baseline above the bar means there is no headroom: the model already finds the cases without the new claim.
    """
    frozen = [r.found for r in runs["frozen"]]
    control = [r.found for r in runs["control"]]
    updated = runs["updated"]
    bar = params["baseline_found_max"]
    good_updated = [r for r in updated if r.found >= params["updated_found_min"] and r.priced >= params["updated_priced_min"]]
    updated_flags = sum(r.false_positives for r in updated)
    other_flags = {arm: sum(r.false_positives for r in runs[arm]) for arm in ("frozen", "control")}
    checks = {
        "baselines_below_the_bar": {
            "ok": statistics.median(frozen) <= bar and statistics.median(control) <= bar,
            "detail": (f"frozen found {frozen} (median {statistics.median(frozen)}) and control found {control} "
                       f"(median {statistics.median(control)}); each median is at most {bar}"),
        },
        "updated_finds_and_prices": {
            "ok": len(good_updated) >= params["updated_runs_required"],
            "detail": (
                f"updated found {[r.found for r in updated]} and priced {[r.priced for r in updated]}; "
                f"{len(good_updated)} runs reach {params['updated_found_min']} found and {params['updated_priced_min']} priced "
                f"(need {params['updated_runs_required']})"
            ),
        },
        "decoys_quiet": {
            "ok": updated_flags == 0,
            "detail": (f"{updated_flags} decoy answers of the updated arm flagged waste in all runs; flags in the other arms are reported, "
                       f"not counted (frozen {other_flags['frozen']}, control {other_flags['control']})"),
        },
        "quote_on_page": {"ok": quote_ok, "detail": "every quote of the accepted claim is on its page, its hash matches, and the claim copies nothing from a case"},
        "review_recorded": {"ok": review_ok, "detail": "a reviewer accepted or edited the claim, and the decision is recorded"},
        "within_cap": {
            "ok": within_cap,
            "detail": "the cost of all runs is inside the spending cap" if within_cap is not None else "the cost is not known yet: read it from the hub logs",
        },
        "answers_read": {
            "ok": answers_ok,
            "detail": ("a person who did not build the harness read each updated answer that found a case and confirmed that it rests on the new claim"
                       if answers_ok is not False else "a person read the updated answers and found one that does not rest on the new claim"),
        },
    }
    known = [c["ok"] for c in checks.values() if c["ok"] is not None]
    return {
        "checks": checks,
        "passed": all(known) and len(known) == len(checks),
        "pending": len(known) != len(checks),
        "failed": [name for name, c in checks.items() if c["ok"] is False],
        "no_headroom": not checks["baselines_below_the_bar"]["ok"],
    }
