#!/usr/bin/env python3
"""The learning check: does updated memory beat frozen memory? (standard library only; offline; it calls no model, no service and no network)

    python tools/learning-check.py [--cases FILE] [--thresholds FILE]

It replays the invented closed requests of evaluation/learning-cases.jsonl in time order. A row is one finding that a person was asked to decide: the type of the resource, the family of the plan,
the confidence that the first AI stated, the last word of the person (and the reason of a decline), the day on which the Watch judged it (`opened`) and the day on which the request closed
(`closed`). Each row is decided twice:

  frozen    nothing is learned: a finding is a proposal when the confidence that was stated is at or above the gate of the app (decide.PROPOSE_CONFIDENCE);
  updated   the lessons of the requests that had closed before the day of the judgement are in a store of the app (cases/memory_store.py) and the proposal goes through learning.hold, the call
            that the Watch makes: a proposal that people rarely approved when the AI was this sure goes to a person instead of being proposed.

Only the later half of the rows is graded: the first half builds the lessons. A row says that the finding was right when a person approved it and that it was wrong when a person declined it as
still needed or with a wrong figure (learning.label_of, the app's own definition); the other outcomes say nothing and are not graded. Every row is taken to be a finding that the Watch would
propose when its confidence is at or above the gate (the second AI agreeing, no guard, a measurement that backs it): the replay holds only what the memory can change. What is held against
evaluation/learning-thresholds.json, which was written before this tool, the replay set and the first run:

  size         enough graded requests say whether the finding was right;
  calibration  the Brier score of the confidence that decides (the stated one, or the calibrated one when it is lower) is lower with updated memory than with frozen memory by a margin;
  decoys       the share of the proposals that people declined as wrong which updated memory holds back is at least a minimum;
  good         the share of the proposals that people approved which updated memory holds back is at most a maximum (a hold costs a person a decision, never a finding);
  no history   a proposal of a type with too few outcomes in its band is decided exactly as frozen memory decides it.

A threshold that cannot be measured (no decoy in the graded part, say) is missed, because nothing is proved. One rule of the code is checked as well, and is not a threshold: no hold ever makes
a finding stronger. The tool says what it does not measure (the thresholds file lists it). It exits 0 when every threshold holds, 1 when one is missed (the claim of learning is then withdrawn,
and the proposal and the README say so: AGENTS.md rule 14 (c)) and 2 when a file cannot be read or is not well formed. It reads two files, writes nothing and never calls a model.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "case-functions"
CASES = ROOT / "evaluation" / "learning-cases.jsonl"
THRESHOLDS = ROOT / "evaluation" / "learning-thresholds.json"

if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
from cases import decide, learning, models  # noqa: E402 (after the path is set)
from cases.memory_store import MemoryStore, stamp  # noqa: E402

KEYS = ("id", "type", "family", "stated", "answer", "reason", "opened", "closed")
OPTIONAL = ("note",)  # a sentence for the people who read the file: nothing reads it
MAX_ROWS = 400
MAX_DAY = 3650
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
START = dt.datetime(2026, 1, 5, tzinfo=dt.timezone.utc)  # the day 0 of a replay: any day will do, the lessons only need an order
# The thresholds, and for each one the key of its rule: nothing else is read from the file, and a name that is missing is an error, not a pass.
RULES = {"labelledMin": "min", "brierImprovementMin": "min", "decoysHeldShareMin": "min", "goodHeldShareMax": "max", "coldStartIdentical": "equals"}


class Problem(Exception):
    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


# -- the files ---------------------------------------------------------------------------------------------------------------------------------------

def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_row(row: object, number: int) -> dict:
    if not isinstance(row, dict):
        raise Problem(f"line {number} of the replay set is not an object")
    name = row.get("id") if isinstance(row.get("id"), str) else f"line {number}"
    unknown, missing = sorted(set(row) - set(KEYS) - set(OPTIONAL)), [key for key in KEYS if key not in row]
    if unknown or missing:
        raise Problem(f"{name}: the keys are {', '.join(KEYS)} and optionally note (unknown: {', '.join(unknown) or 'none'}; missing: {', '.join(missing) or 'none'})")
    kind = row["type"]
    problems = [
        (not (isinstance(row["id"], str) and ID.fullmatch(row["id"])), "the id is lower-case letters, digits and hyphens"),
        (not (isinstance(kind, str) and kind != "other" and learning.type_word(kind) == kind), "the type is a resource type as Azure names it, in lower case"),
        (row["family"] not in (*models.FAMILIES, models.ADVISE), "the family is one of the families of a plan"),
        (not (_is_number(row["stated"]) and 0 <= row["stated"] <= 1), "the stated confidence is a number from 0 to 1"),
        (row["answer"] not in models.LESSON_ANSWERS, f"the answer is one of {', '.join(models.LESSON_ANSWERS)}"),
        (row["reason"] != "" and not (row["answer"] == "decline" and row["reason"] in models.DECLINE_REASONS), f"only a decline has a reason, one of {', '.join(models.DECLINE_REASONS)}"),
        (not all(isinstance(row[key], int) and not isinstance(row[key], bool) for key in ("opened", "closed")), "opened and closed are whole numbers of days"),
        (all(isinstance(row[key], int) for key in ("opened", "closed")) and not 0 <= row["opened"] < row["closed"] <= MAX_DAY, f"a request closes after it opens, within {MAX_DAY} days"),
        ("note" in row and not (isinstance(row["note"], str) and len(row["note"]) <= 240), "a note is at most 240 characters"),
    ]
    for wrong, words in problems:
        if wrong:
            raise Problem(f"{name}: {words}")
    return row


def parse_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(check_row(json.loads(line), number))
        except ValueError:
            raise Problem(f"line {number} of the replay set is not JSON") from None
    if not rows:
        raise Problem("the replay set holds no request")
    if len(rows) > MAX_ROWS:
        raise Problem(f"the replay set holds more than {MAX_ROWS} requests")
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise Problem("two requests of the replay set have the same id")
    return rows


def parse_thresholds(text: str) -> dict:
    """The thresholds, the date that they were written and what is not measured, from the file; an error for anything that is missing, unknown or of the wrong shape."""
    try:
        document = json.loads(text)
    except ValueError:
        raise Problem("the thresholds file is not JSON") from None
    if not isinstance(document, dict) or not isinstance(document.get("thresholds"), dict):
        raise Problem("the thresholds file holds no `thresholds` object")
    found = DATE.search(document.get("writtenBefore") if isinstance(document.get("writtenBefore"), str) else "")
    if not found:
        raise Problem("the thresholds file does not say on which day it was written (`writtenBefore`)")
    rules = document["thresholds"]
    if sorted(rules) != sorted(RULES):
        raise Problem(f"the thresholds are {', '.join(sorted(RULES))}; the file holds {', '.join(sorted(rules))}")
    for name, key in RULES.items():
        rule = rules[name]
        value = rule.get(key) if isinstance(rule, dict) else None
        if not isinstance(rule, dict) or not (value is True if key == "equals" else _is_number(value) and value >= 0) or not isinstance(rule.get("why"), str) or not rule["why"]:
            raise Problem(f"the threshold {name} has a `{key}` and a `why`")
    unmeasured = document.get("notMeasured")
    if not isinstance(unmeasured, list) or not unmeasured or not all(isinstance(item, str) and item for item in unmeasured):
        raise Problem("the thresholds file lists what is not measured (`notMeasured`)")
    return {"date": found.group(0), "thresholds": rules, "notMeasured": unmeasured}


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        raise Problem(f"{path.name} cannot be read") from None


# -- the replay --------------------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Judged:
    """One request, decided twice."""

    row: dict
    label: bool | None  # True: the finding was right; False: it was wrong; None: the outcome says nothing about it
    calibrated: learning.Calibrated | None  # what the lessons that were known then support for the stated confidence
    frozen: str  # the status that frozen memory decides
    updated: str  # the status that updated memory decides

    @property
    def forecast(self) -> float:
        """The confidence that decides with updated memory: the stated one, or the calibrated one when it is lower (learning only ever makes a finding weaker)."""
        stated = self.row["stated"]
        return stated if self.calibrated is None else min(stated, self.calibrated.rate)


def lesson_of(row: dict) -> models.LessonRecord:
    opened, closed = (stamp(START + dt.timedelta(days=row[key])) for key in ("opened", "closed"))
    return models.LessonRecord(lesson_id=row["id"], resource_type=row["type"], family=row["family"], confidence=row["stated"], answer=row["answer"], reason=row["reason"], opened_at=opened,
                               closed_at=closed, updated_at=closed)


def frozen_decision(row: dict) -> decide.Decision:
    status = "proposed" if row["stated"] >= decide.PROPOSE_CONFIDENCE else "needs_human"
    return decide.Decision(status=status, recommendation="change", confidence=row["stated"], summary="", objections=(), guards=[], monthly_saving_usd=None)


def replay(rows: list[dict]) -> list[Judged]:
    """The requests in the order in which the Watch judged them (a tie goes by id). A lesson is in the store of a judgement only when its request closed on an earlier day: a request never
    teaches the judgement of a request that opened before it closed, and never its own."""
    ordered = sorted(rows, key=lambda row: (row["opened"], row["id"]))
    closing = sorted(rows, key=lambda row: (row["closed"], row["id"]))
    store, learned, judged = MemoryStore(), 0, []
    for row in ordered:
        while learned < len(closing) and closing[learned]["closed"] < row["opened"]:
            store.lesson_put(lesson_of(closing[learned]))
            learned += 1
        frozen = frozen_decision(row)
        updated, _ = learning.hold(store, row["type"], row["family"], row["stated"], frozen)
        known = [lesson for lesson in store.lessons_of(row["type"]) if lesson.family == row["family"]]
        judged.append(Judged(row, learning.label_of(lesson_of(row)), learning.calibrated_confidence(row["stated"], known), frozen.status, updated.status))
    return judged


def graded_part(judged: list[Judged]) -> list[Judged]:
    return judged[len(judged) // 2:]


# -- the numbers -------------------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Numbers:
    rows: int
    graded: int
    labelled: int  # the graded requests that say whether the finding was right
    brier_frozen: float | None
    brier_updated: float | None
    decoys: int  # graded proposals of frozen memory that people declined as wrong
    decoys_held: int
    good: int  # graded proposals of frozen memory that people approved
    good_held: int
    cold: int  # proposals of frozen memory (in the whole replay) of a type with too few outcomes in its band
    cold_same: int  # of those, the ones that updated memory decided in the same way
    stronger: int  # requests that updated memory proposed and frozen memory did not


def _mean(values) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def measure(judged: list[Judged]) -> Numbers:
    graded = graded_part(judged)
    labelled = [item for item in graded if item.label is not None]
    proposals = [item for item in graded if item.frozen == "proposed"]
    decoys = [item for item in proposals if item.label is False]
    good = [item for item in proposals if item.label is True]
    cold = [item for item in judged if item.frozen == "proposed" and item.calibrated is None]
    return Numbers(
        rows=len(judged), graded=len(graded), labelled=len(labelled), brier_frozen=_mean((item.row["stated"] - item.label) ** 2 for item in labelled),
        brier_updated=_mean((item.forecast - item.label) ** 2 for item in labelled), decoys=len(decoys), decoys_held=sum(1 for item in decoys if item.updated != "proposed"), good=len(good),
        good_held=sum(1 for item in good if item.updated != "proposed"), cold=len(cold), cold_same=sum(1 for item in cold if item.updated == item.frozen),
        stronger=sum(1 for item in judged if item.updated == "proposed" and item.frozen != "proposed"))


@dataclass(frozen=True)
class Verdict:
    name: str
    passed: bool
    words: str


def verdicts(numbers: Numbers, rules: dict) -> list[Verdict]:
    """One verdict for each threshold, in plain words. A number that cannot be had (nothing to divide) is a threshold that is missed."""
    n = numbers
    found: list[Verdict] = []
    need = rules["labelledMin"]["min"]
    found.append(Verdict("labelledMin", n.labelled >= need, f"size: {n.labelled} of the {n.graded} graded requests say whether the finding was right (at least {need:g} are needed)"))
    need = rules["brierImprovementMin"]["min"]
    if n.brier_frozen is None or n.brier_updated is None:
        found.append(Verdict("brierImprovementMin", False, "calibration: not measured, no graded request says whether the finding was right"))
    else:
        better = round(n.brier_frozen - n.brier_updated, 6)
        found.append(Verdict("brierImprovementMin", better >= need, f"calibration: the Brier score of the deciding confidence is {n.brier_frozen:.3f} with frozen memory and "
                                                                    f"{n.brier_updated:.3f} with updated memory, better by {better:.3f} (at least {need:g} is needed)"))
    need = rules["decoysHeldShareMin"]["min"]
    if n.decoys == 0:
        found.append(Verdict("decoysHeldShareMin", False, "decoys: not measured, no graded proposal was declined as wrong"))
    else:
        share = round(n.decoys_held / n.decoys, 6)
        found.append(Verdict("decoysHeldShareMin", share >= need, f"decoys: updated memory holds back {n.decoys_held} of the {n.decoys} proposals that people declined as wrong, {share:.2f} (at least {need:g} is needed)"))
    need = rules["goodHeldShareMax"]["max"]
    if n.good == 0:
        found.append(Verdict("goodHeldShareMax", False, "good proposals: not measured, no graded proposal was approved"))
    else:
        share = round(n.good_held / n.good, 6)
        found.append(Verdict("goodHeldShareMax", share <= need, f"good proposals: updated memory holds back {n.good_held} of the {n.good} proposals that people approved, {share:.2f} (at most {need:g} is allowed)"))
    if n.cold == 0:
        found.append(Verdict("coldStartIdentical", False, "no history: not measured, every proposal of the replay had outcomes in its band"))
    else:
        found.append(Verdict("coldStartIdentical", n.cold_same == n.cold, f"no history: {n.cold_same} of the {n.cold} proposals with too few outcomes in their band were decided as frozen memory decides them (all are needed)"))
    return found


# -- the report --------------------------------------------------------------------------------------------------------------------------------------

def table(judged: list[Judged]) -> list[str]:
    """The graded part by type and family: where learning acted, and on what."""
    groups: dict[tuple[str, str], list[Judged]] = {}
    for item in graded_part(judged):
        groups.setdefault((item.row["type"], item.row["family"]), []).append(item)
    rows = [("type", "family", "graded", "right/wrong", "decoys held", "good held")]
    for (kind, family), items in sorted(groups.items()):
        proposals = [item for item in items if item.frozen == "proposed"]
        decoys = [item for item in proposals if item.label is False]
        good = [item for item in proposals if item.label is True]
        rows.append((kind, family, str(len(items)), f"{sum(1 for item in items if item.label is True)}/{sum(1 for item in items if item.label is False)}",
                     f"{sum(1 for item in decoys if item.updated != 'proposed')} of {len(decoys)}", f"{sum(1 for item in good if item.updated != 'proposed')} of {len(good)}"))
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    return ["  " + "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows]


def run(rows: list[dict], rules: dict, cases_name: str = CASES.name, thresholds_name: str = THRESHOLDS.name) -> tuple[list[str], int]:
    """The lines of the report and the exit code."""
    judged = replay(rows)
    numbers = measure(judged)
    results = verdicts(numbers, rules["thresholds"])
    graded = graded_part(judged)
    types = len({item.row["type"] for item in judged})
    lines = [f"learning check: {numbers.rows} invented closed requests of {types} type{'' if types == 1 else 's'} in {cases_name}, replayed in time order (days {judged[0].row['opened']} to "
             f"{max(item.row['closed'] for item in judged)}); graded: the later half, {numbers.graded} requests from day {graded[0].row['opened']}",
             f"thresholds: {thresholds_name}, written on {rules['date']}, before this tool, the replay set and the first run", ""]
    lines += [f"{'PASS' if verdict.passed else 'FAIL'}  {verdict.words}" for verdict in results]
    lines.append(f"{'PASS' if numbers.stronger == 0 else 'FAIL'}  rule: no hold made a finding stronger ({numbers.stronger} of {numbers.rows} requests)")
    lines += ["", "the graded part by type (graded; right/wrong; the decoys and the good proposals that updated memory held back):"] + table(judged) + [""]
    lines += [f"not measured: {item}" for item in rules["notMeasured"]] + [""]
    missed = [verdict.name for verdict in results if not verdict.passed] + (["neverStronger"] if numbers.stronger else [])
    if missed:
        lines.append(f"result: the claim of learning is withdrawn (missed: {', '.join(missed)}); docs/proposals/15-learning.md and the README say so (AGENTS.md rule 14 (c))")
    else:
        lines.append("result: on these invented requests and these thresholds updated memory beats frozen memory; what is listed above as not measured is not claimed")
    return lines, 1 if missed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", type=Path, default=CASES, help="the replay set (JSON lines)")
    parser.add_argument("--thresholds", type=Path, default=THRESHOLDS, help="the thresholds, written before the first run")
    args = parser.parse_args(argv)
    try:
        rows, rules = parse_rows(read(args.cases)), parse_thresholds(read(args.thresholds))
    except Problem as error:
        print(f"error: {error}", file=sys.stderr)
        return error.code
    lines, code = run(rows, rules, args.cases.name, args.thresholds.name)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
