"""Outcome lessons: what closed requests teach (docs/proposals/15-learning.md).

A request that has come to its end (a person said yes, no, not mine, or never answered, and a change was made or not) leaves one `LessonRecord`: the resource type, the family, a few
signals of the case in buckets, what the first AI said and whether the second agreed, the person's last word and, for a change that was made, the saving that was predicted and the one
that the cost lines showed some days later. The record holds typed values only: no name of a person or of a resource, no text, no id of an estate. Nothing here calls a model, and nothing
of it is ever a text that a model reads: the Investigator gets counts and rates through the tool `recall_lessons` (cases/toolbox.py) and nothing else.

What is made of the lessons, all of it by code and all of it explainable:

* `past_of` counts the lessons of one (resource type, family): how many requests people answered, how many said yes, why the others declined, how the saving that was measured compares with
  the one that was predicted, how many changes were undone within weeks. `digest_of` keeps four numbers and a flag of that in the case, and the brief writes the one line from it
  (brief.past_line), or says "no history yet" below MIN_ANSWERED.
* `calibrated_confidence` says what past outcomes support for a confidence that the first AI stated: the share of the labelled outcomes in the same band (BANDS) that were approved, when
  there are at least MIN_BAND of them. `hold` uses it in one way only: a proposal whose stated confidence is at or above the gate and whose calibrated confidence is below it goes to a person
  as a finding that needs one. Learning only ever makes a finding weaker: a calibrated confidence above the stated one changes nothing.
* `sync` is the sweep that the timer of the loop runs: it writes the lesson of every plan that has ended, adds the measured saving when the verifier has read the cost lines, and, for a
  change that was made on a resource that Meternaut did not plant, looks in the Activity Log for the resource made again (a boomerang).

The starting values below were written before anything was measured, and tools/learning-check.py holds them against evaluation/learning-thresholds.json.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import re
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Mapping, Sequence

from . import ownership
from .brief import past_line  # noqa: F401  (the one line of the brief is written there: the brief imports nothing but the records)
from .decide import PROPOSE_CONFIDENCE, Decision
from .memory_store import parse, stamp
from .models import ADVISE, DECLINE_REASONS, ActionRecord, CaseRecord, LessonRecord, PlanRecord, Store, StoreError

LOG = logging.getLogger("meternaut.learning")

# A line of the brief shows numbers only when at least this many requests of the kind were answered by a person; below it, it says that there is no history yet.
MIN_ANSWERED = 3
# A confidence is corrected only when at least this many labelled outcomes lie in its band.
MIN_BAND = 5
# "Savings came in at ..." is said only when at least this many changes have a measured saving.
MIN_MEASURED = 2
# The bands of a stated confidence (low edge included, high edge excluded): below the gate of a proposal, from the gate to the confidence that the brief calls high, and above it.
BANDS = ((0.0, PROPOSE_CONFIDENCE), (PROPOSE_CONFIDENCE, 0.85), (0.85, 1.0 + 1e-9))
BAND_NAMES = ("below 0.7", "0.7 to 0.85", "0.85 and up")
# A decline for one of these reasons says that the finding was wrong; the others ("handled", "other", none) say nothing about it, and neither do "not mine" and a request nobody answered.
WRONG_REASONS = ("still-needed", "figure-wrong")
# A change that is undone within this many days is a boomerang.
BOOMERANG_DAYS = 28
BOOMERANG_EVERY_HOURS = 24  # the Activity Log of one change is read at most once in this time
CLOSED = ("consumed", "declined", "withdrawn", "expired", "failed")
SYNC_PLANS = 100  # the plans that a sweep looks at, newest first
SYNC_LESSONS = 400
SYNC_READS = 5  # the Activity Log reads of one sweep
SYNC_EVERY_MINUTES = 5  # the timer of the loop runs a sweep in each minute that is a multiple of this
SIGNAL_KEYS = ("cost", "usage", "evidence", "window", "age", "owner")
RESOURCE_TYPE = re.compile(r"[a-z0-9.]{1,60}(?:/[a-z0-9._-]{1,50}){1,4}")
WORD = re.compile(r"[a-z][a-z0-9-]{0,39}")
ZERO = "no history yet"


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _word(value: object, allowed: Sequence[str] = ()) -> str:
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if (text in allowed if allowed else WORD.fullmatch(text)) else ""


def type_word(value: object) -> str:
    """A resource type as Azure names it, in lower case, or "other" when the text has not the shape of one."""
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if RESOURCE_TYPE.fullmatch(text) else "other"


def resource_type_of(case: CaseRecord | None, plan: PlanRecord | None = None) -> str:
    """The type as Azure names it, in lower case, from the case or else from the id of the resource of the plan; "other" when it has not the shape of one."""
    candidates = [case.resource_type if case is not None else ""]
    if plan is not None:
        found = re.search(r"/providers/([^/]+)/([^/]+)/[^/]+(?:/([^/]+)/[^/]+)*$", plan.resource_id or "")
        if found:
            candidates.append("/".join(part for part in (found.group(1), found.group(2), found.group(3)) if part))
    return next((word for word in map(type_word, candidates) if word != "other"), "other")


# -- buckets: the signals of a case, with no name and no text ------------------------------------------------------------------------------------------

def _money_bucket(value: object) -> str:
    amount = _number(value)
    if amount is None:
        return "unknown"
    return "0" if amount <= 0 else "<10" if amount < 10 else "10-99" if amount < 100 else "100-999" if amount < 1000 else "1000+"


def _count_bucket(count: int) -> str:
    return "0" if count <= 0 else "1" if count == 1 else "2-3" if count <= 3 else "4+"


def _days_bucket(value: object) -> str:
    days = _number(value)
    if days is None or days < 0:
        return "unknown"
    return "<7" if days < 7 else "7-29" if days < 30 else "30-89" if days < 90 else "90+"


def signals_of(case: CaseRecord | None) -> dict[str, str]:
    """The signals of a case in buckets, for a closed set of keys: the cost of the last 30 days, whether the numbers that code re-checked show any use, how many there are, how many
    days they cover, how old the resource is and whether an owner tag was found. A key whose fact is not in the case is left out. Never a name, a tag or a metric's name."""
    if case is None:
        return {}
    facts = case.facts if isinstance(case.facts, dict) else {}
    found: dict[str, str] = {}
    if case.cost_usd_30d is not None:
        found["cost"] = _money_bucket(case.cost_usd_30d)
    metrics = facts.get("metrics") if isinstance(facts.get("metrics"), dict) else None
    if metrics is not None:
        totals = [_number(total) for total in metrics.values()]
        found["evidence"] = _count_bucket(len(metrics))
        found["usage"] = "unmeasured" if not totals else "some" if any(t is not None and t != 0 for t in totals) else "none"
    spans = facts.get("metricDays") if isinstance(facts.get("metricDays"), dict) else {}
    longest = max((d for d in (_number(v) for v in spans.values()) if d is not None), default=None)
    if longest is not None:
        found["window"] = _days_bucket(longest)
    if _number(facts.get("ageDays")) is not None:
        found["age"] = _days_bucket(facts.get("ageDays"))
    owner = case.owner if isinstance(case.owner, dict) else {}
    if owner:
        found["owner"] = "tag" if owner.get("tagOwner") else "none" if owner.get("lookedUp") else "unknown"
    return {key: found[key] for key in SIGNAL_KEYS if key in found}


# -- one lesson ---------------------------------------------------------------------------------------------------------------------------------------

def _answer(plan: PlanRecord, decisions: Sequence) -> tuple[str, str, str]:
    """The person's last word, the reason of a decline and the time of the decisive answer ("" when nobody decided)."""
    by_time = sorted(decisions, key=lambda d: (d.at, d.approver_oid))

    def latest(*kinds: str):
        return next((d for d in reversed(by_time) if d.decision in kinds), None)

    if plan.state == "declined":
        found = latest("decline")
        return "decline", (found.reason if found and found.reason in DECLINE_REASONS else ""), found.at if found else ""
    if plan.state == "withdrawn":
        found = latest("not_mine")
        return "not_mine", "", found.at if found else ""
    if plan.state in ("consumed", "failed"):
        found = latest("approve")
        return "approve", "", found.at if found else ""
    found = latest("ask", "later")  # a request that ended with nobody deciding: the last thing that anybody said about it
    return (found.decision if found else "expired"), "", ""


def measured_of(plan: PlanRecord, action: ActionRecord | None, days: int | None = None) -> float | None:
    """What a change saved in a month, as the cost lines read afterwards showed, in US dollars: the cost of the 30 days before the change when the lines after it show none, else that cost
    less what the lines after it show, scaled from the days that were read (the verifier reads `days` days after the change: runner.VERIFY_AFTER_DAYS). None when the lines were not read
    or are not in US dollars. Only a change has one: an answer of an advise plan changes nothing."""
    if plan.family == ADVISE or action is None or not isinstance(action.verification, dict):
        return None
    check = action.verification
    before, after = _number(check.get("costBeforeUsd30d")), _number(check.get("costAfterUsd"))
    if before is None or after is None or check.get("currency") not in (None, "", "USD"):
        return None
    if after <= 0:
        return round(max(before, 0.0), 2)
    from .runner import VERIFY_AFTER_DAYS  # imported here: the runner imports the approvals, which the sweep does not need to load first

    return round(max(before - after * 30.0 / max(days or VERIFY_AFTER_DAYS, 1), 0.0), 2)


def _result(plan: PlanRecord, action: ActionRecord | None) -> str:
    if plan.family == ADVISE or action is None:
        return ""
    return "verified" if action.state == "verified" else "failed" if action.state == "failed" or plan.state == "failed" else "ran" if action.state in ("done", "unknown") else ""


def lesson_of(plan: PlanRecord, case: CaseRecord | None, decisions: Sequence, action: ActionRecord | None, now: dt.datetime, previous: LessonRecord | None = None) -> LessonRecord | None:
    """The lesson of a plan that has ended, or None while it has not. `previous` is the lesson that was written before: what only a later look can add (a boomerang) is kept."""
    if plan.state not in CLOSED:
        return None
    answer, reason, decided = _answer(plan, decisions)
    facts = case.facts if case is not None and isinstance(case.facts, dict) else {}
    learned = case.learned if case is not None and isinstance(case.learned, dict) else {}
    measured = measured_of(plan, action)
    predicted = _number(plan.saving_usd_month)
    stated = _number(case.confidence if case is not None else None)
    ended = decided or (action.finished_at if action is not None and action.finished_at and answer == "approve" else "") or plan.expires_at
    return LessonRecord(
        lesson_id=plan.plan_id, resource_type=resource_type_of(case, plan), family=_word(plan.family) or ADVISE, detector=_word(case.detector if case is not None else ""),
        basis=_word(facts.get("basis")), proposal=_word(case.recommendation if case is not None else "", ("delete", "change", "investigate", "keep")), signals=signals_of(case),
        confidence=round(stated, 2) if stated is not None and 0 <= stated <= 1 else None, skeptic=_word(learned.get("skeptic"), ("agree", "disagree", "unsure", "none")),
        answer=answer, reason=reason, opened_at=plan.created_at, closed_at=ended, result=_result(plan, action),
        predicted_usd_month=round(predicted, 2) if predicted is not None else None,
        measured_usd_month=measured if measured is not None else (previous.measured_usd_month if previous else None),
        measured_at=previous.measured_at if previous and previous.measured_at else (stamp(now) if measured is not None else ""),
        boomerang=bool(previous and previous.boomerang), boomerang_checked_at=previous.boomerang_checked_at if previous else "", updated_at=stamp(now))


def _same(a: LessonRecord, b: LessonRecord | None) -> bool:
    return b is not None and replace(a, updated_at="") == replace(b, updated_at="")


# -- what many lessons say ----------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Past:
    """How past requests of one resource type and family were answered, counted from their lessons."""

    resource_type: str
    family: str
    answered: int = 0  # a person said yes, no or not mine
    approved: int = 0
    declined: int = 0
    not_mine: int = 0
    unanswered: int = 0  # the request ended with nobody deciding (it expired, perhaps after a question or a later)
    reasons: tuple[tuple[str, int], ...] = ()  # the reason of each decline that gave one, with its count
    measured: int = 0  # changes whose saving was measured
    predicted_usd: float = 0.0  # what was predicted for those
    measured_usd: float = 0.0
    boomerangs: int = 0

    @property
    def ratio(self) -> float | None:
        """What the cost lines showed, as a share of what was predicted, over the changes that have both; None below MIN_MEASURED of them or when nothing was predicted."""
        return round(self.measured_usd / self.predicted_usd, 2) if self.measured >= MIN_MEASURED and self.predicted_usd > 0 else None


def past_of(lessons: Iterable[LessonRecord], resource_type: str, family: str) -> Past:
    """The counts of the lessons of one type and family."""
    found = [lesson for lesson in lessons if lesson.resource_type == resource_type and lesson.family == family]
    answers = [lesson.answer for lesson in found]
    reasons: dict[str, int] = {}
    for lesson in found:
        if lesson.answer == "decline" and lesson.reason in DECLINE_REASONS:
            reasons[lesson.reason] = reasons.get(lesson.reason, 0) + 1
    both = [lesson for lesson in found if lesson.measured_usd_month is not None and (lesson.predicted_usd_month or 0) > 0]
    return Past(resource_type, family, answered=sum(1 for a in answers if a in ("approve", "decline", "not_mine")), approved=answers.count("approve"), declined=answers.count("decline"),
                not_mine=answers.count("not_mine"), unanswered=sum(1 for a in answers if a in ("expired", "ask", "later")), reasons=tuple(sorted(reasons.items())),
                measured=len(both), predicted_usd=round(sum(lesson.predicted_usd_month or 0 for lesson in both), 2),
                measured_usd=round(sum(lesson.measured_usd_month or 0 for lesson in both), 2), boomerangs=sum(1 for lesson in found if lesson.boomerang))


def digest_of(past: Past) -> dict:
    """What a case keeps of its past in `CaseRecord.learned["past"]`: how many requests a person answered and how many said yes, whether that is enough to say anything (MIN_ANSWERED), the
    ratio when there is one and the number of boomerangs. Numbers and flags only. The brief turns it into its one line (brief.past_line)."""
    found: dict = {"n": past.answered, "approved": past.approved, "enough": past.answered >= MIN_ANSWERED, "boomerangs": past.boomerangs}
    if past.ratio is not None:
        found["ratio"] = past.ratio
    return found


# -- calibration --------------------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Calibrated:
    """What past outcomes support for a stated confidence: the share of the labelled outcomes in its band that were approved, and how many there were."""

    rate: float
    cases: int
    band: str


def band_of(confidence: object) -> int | None:
    value = _number(confidence)
    if value is None or not 0.0 <= value <= 1.0:
        return None
    return next(index for index, (low, high) in enumerate(BANDS) if low <= value < high)


def label_of(lesson: LessonRecord) -> bool | None:
    """Whether a closed request says that the finding was right (approved) or wrong (declined as still needed, or with a wrong figure); None for everything else."""
    if lesson.answer == "approve":
        return True
    if lesson.answer == "decline" and lesson.reason in WRONG_REASONS:
        return False
    return None


def calibrated_confidence(stated: object, lessons: Iterable[LessonRecord]) -> Calibrated | None:
    """What the lessons support for a confidence that the first AI stated, or None (the brief then says that there is no history yet) when fewer than MIN_BAND labelled outcomes lie in the
    band of the stated one. `lessons` are those of one resource type and family. It is a bucket correction: no model, no curve, one count divided by another."""
    band = band_of(stated)
    if band is None:
        return None
    labelled = [label_of(lesson) for lesson in lessons if lesson.confidence is not None and band_of(lesson.confidence) == band]
    labelled = [label for label in labelled if label is not None]
    if len(labelled) < MIN_BAND:
        return None
    return Calibrated(round(sum(1 for label in labelled if label) / len(labelled), 2), len(labelled), BAND_NAMES[band])


def holds(stated: object, calibrated: Calibrated | None, gate: float = PROPOSE_CONFIDENCE) -> bool:
    """Whether what the lessons support holds a proposal back: the stated confidence is at the gate or above it, and the calibrated one is below. Never the other way round."""
    value = _number(stated)
    return calibrated is not None and value is not None and value >= gate > calibrated.rate


def hold(store: Store | None, resource_type: str, family: str, stated: object, outcome: Decision) -> tuple[Decision, bool]:
    """The decision of a case, held back for a person when the lessons say that proposals like this are rarely approved. The note that says why is the first objection and is code's, not the
    second AI's. Reading the store may fail: a case is then decided as it was."""
    if store is None or outcome.status != "proposed":
        return outcome, False
    try:
        calibrated = calibrated_confidence(stated, [lesson for lesson in store.lessons_of(resource_type) if lesson.family == family])
    except StoreError:
        return outcome, False
    if not holds(stated, calibrated):
        return outcome, False
    assert calibrated is not None
    share = round(calibrated.rate * calibrated.cases)
    note = f"{NOTE_PREFIX} were approved only {share} of {calibrated.cases} times when the AI was this sure, so a person has to decide"
    return replace(outcome, status="needs_human", objections=(note, *outcome.objections)), True


NOTE_PREFIX = "past cases like this"


def remember(store: Store | None, case: CaseRecord, plan: PlanRecord, **more: object) -> CaseRecord:
    """Keeps in the case how past requests like it were answered (`learned["past"]`), once the plan is made and its family is known, and what else the caller adds. The case that is kept is the
    one that the store holds now (making the plan linked it to the plan), never the copy that the caller has. Returns the case as it was kept; a store that fails leaves the case as it was
    and never stops the run."""
    if store is None:
        return case
    try:
        current = store.case_get(case.case_id) or case
        kind = resource_type_of(current, plan)
        learned = {**(current.learned if isinstance(current.learned, dict) else {}), "past": digest_of(past_of(store.lessons_of(kind), kind, plan.family)),
                   **{key: value for key, value in more.items() if value}}
        if learned == current.learned:
            return current
        kept = replace(current, learned=learned)
        store.case_put(kept)
        return kept
    except StoreError as error:
        LOG.warning("learning: the past of a case could not be kept (%s)", type(error).__name__)
        return case


# -- what the Investigator may ask --------------------------------------------------------------------------------------------------------------------

def recall(lessons: Iterable[LessonRecord], resource_type: str) -> dict:
    """The answer of the tool `recall_lessons`: counts and rates of the lessons of one type, by family, and the share that was approved in each band of confidence. Typed values and fixed
    words only: no text of a person, no name, nothing that was written by anybody."""
    found = [lesson for lesson in lessons if lesson.resource_type == resource_type]
    answer: dict = {"type": resource_type, "closed": len(found),
                    "source": "how people answered past requests of this type: counts, not facts about this estate"}
    if not found:
        answer["history"] = ZERO
        return answer
    families = []
    for family in sorted({lesson.family for lesson in found}):
        past = past_of(found, resource_type, family)
        row: dict = {"family": family, "answered": past.answered, "approved": past.approved, "declined": past.declined, "not_mine": past.not_mine, "unanswered": past.unanswered}
        if past.reasons:
            row["declined_for"] = dict(past.reasons)
        if past.measured:
            row["measured_changes"] = past.measured
        if past.ratio is not None:
            row["saving_vs_estimate"] = past.ratio
        if past.boomerangs:
            row["undone_within_weeks"] = past.boomerangs
        families.append(row)
    answer["families"] = families
    bands = []
    for index, name in enumerate(BAND_NAMES):
        labelled = [label for lesson in found if lesson.confidence is not None and band_of(lesson.confidence) == index for label in (label_of(lesson),) if label is not None]
        if len(labelled) >= MIN_BAND:
            bands.append({"stated_confidence": name, "labelled": len(labelled), "approved_share": round(sum(1 for label in labelled if label) / len(labelled), 2)})
    if bands:
        answer["bands"] = bands
    return answer


# -- the sweep ----------------------------------------------------------------------------------------------------------------------------------------

def _boomerang(arm: object, plan: PlanRecord, action: ActionRecord, now: dt.datetime) -> bool | None:
    """Whether the resource that a change removed was made again after the change: a write of the resource in the Activity Log with the status code 201, later than the change. None when
    the log could not be read."""
    if not action.finished_at:
        return None
    since = parse(action.finished_at)
    try:
        events, _ = arm.activity_events(plan.subscription_id.lower(), since, now, resource_id=plan.resource_id, max_pages=1)  # type: ignore[attr-defined]
    except Exception as error:  # noqa: BLE001 (a read that fails is no answer, and the sweep goes on)
        LOG.warning("learning: the Activity Log could not be read (%s)", type(error).__name__)
        return None
    return any(when > since for when, _caller in ownership.creations(events, plan.resource_id))


def _watched(plan: PlanRecord, lesson: LessonRecord, now: dt.datetime) -> bool:
    """A change that was made, that removed a resource that Meternaut did not plant (a planted one is made again by the planting, which is no boomerang), inside the weeks that count."""
    removed = plan.family.startswith("delete") and lesson.result in ("ran", "verified")
    planted = bool(isinstance(plan.preconditions, Mapping) and plan.preconditions.get("tag"))
    return removed and not planted and bool(lesson.closed_at) and parse(lesson.closed_at) + dt.timedelta(days=BOOMERANG_DAYS) > now


def _complete(plan: PlanRecord, old: LessonRecord | None, now: dt.datetime) -> bool:
    """Whether nothing more can be added to the lesson that was written: an answer that changes nothing, a request that ended before any change, a change that failed, or a change whose
    saving was measured and that is not watched for a boomerang any more."""
    if old is None:
        return False
    if plan.family == ADVISE or plan.state in ("declined", "withdrawn", "expired") or old.result == "failed":
        return True
    return old.result == "verified" and bool(old.measured_at) and not _watched(plan, old, now)


def sync(store: Store, now: dt.datetime, *, arm: object | None = None, limit: int = SYNC_PLANS) -> int:
    """Writes the lesson of every plan that has ended and has none, and brings the lessons that are not complete up to date (the measured saving, the look for a boomerang). Returns how
    many lessons were written or changed. It never raises: a store that fails ends the sweep, and the next one goes on."""
    written = reads = 0
    try:
        known = {lesson.lesson_id: lesson for lesson in store.lessons_recent(SYNC_LESSONS)}
        for plan in store.plans_recent(limit):
            old = known.get(plan.plan_id)
            if plan.state not in CLOSED or _complete(plan, old, now):
                continue
            action = store.action_get(plan.plan_id) if plan.family != ADVISE else None
            lesson = lesson_of(plan, store.case_get(plan.case_id), store.decisions_of_plan(plan.plan_id), action, now, old)
            if lesson is None:
                continue
            if (arm is not None and action is not None and reads < SYNC_READS and _watched(plan, lesson, now) and not lesson.boomerang
                    and (not lesson.boomerang_checked_at or parse(lesson.boomerang_checked_at) + dt.timedelta(hours=BOOMERANG_EVERY_HOURS) <= now)):
                reads += 1
                found = _boomerang(arm, plan, action, now)
                if found is not None:
                    lesson = replace(lesson, boomerang=found, boomerang_checked_at=stamp(now))
            if not _same(lesson, old):
                store.lesson_put(lesson)
                written += 1
    except StoreError as error:
        LOG.warning("learning: the lessons could not be brought up to date (%s)", type(error).__name__)
    except Exception as error:  # noqa: BLE001 (a sweep of the timer never stops the timer)
        LOG.warning("learning: the sweep failed (%s)", type(error).__name__)
    return written
