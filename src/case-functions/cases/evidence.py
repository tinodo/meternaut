"""The case that a model sees: typed facts only. Anything else is refused before a prompt is made.

A name, a tag or a description of the estate is text that somebody else wrote, and a prompt that held it could be steered by it.
So the case holds an opaque id, the detector's name, the resource type, the typed facts of the detector, four flags from the guards and the
cost, which code computed. A string among the facts has to be a word of the closed vocabulary of detectors.py (or one of its few shapes),
and a value that is not a fact is an error: the case ends in an error without a model call.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import replace

from .detectors import DETECTOR_NAMES, Lead, is_fact_word, known_type
from .guards import Guards

MAX_CASE_CHARS = 6000
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,30}$")
CASE_ID = re.compile(r"^c[0-9]{1,3}$")


class EvidenceError(Exception):
    """A value of a case is not a typed fact."""


def model_lead(lead: Lead, fixture: bool) -> Lead:
    """The lead as the models see it. Waste that Meternaut planted itself is declared as planted, and its age is left out: a planted resource is new by
    construction, the guards leave its age aside, and a model that was shown the age asks whether the resource was only just made. Any other lead is unchanged."""
    if not fixture:
        return lead
    facts = {name: value for name, value in lead.facts.items() if name != "ageDays"}
    return replace(lead, facts={**facts, "planted": True})


def _scalar(value: object, path: str) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise EvidenceError(f"{path} is not a finite number")
        return
    if isinstance(value, str):
        if not is_fact_word(value):
            raise EvidenceError(f"{path} is not a word of the fixed vocabulary")
        return
    raise EvidenceError(f"{path} is not a typed fact")


def validate(value: object, path: str = "case") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not KEY.match(key):
                raise EvidenceError(f"{path} has a key that is not a plain name")
            validate(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scalar(item, f"{path}[{index}]")
    else:
        _scalar(value, path)


def case_dto(number: int, lead: Lead, guards: Guards) -> dict:
    """The case for the models: what the case is, never what it is called."""
    case_id = f"c{number}"
    resource_type = known_type(lead.resource_type)
    if not CASE_ID.match(case_id) or lead.detector not in DETECTOR_NAMES:
        raise EvidenceError("the case has an id or a detector that is not one of the app's")
    dto = {
        "caseId": case_id,
        "detector": lead.detector,
        "resourceType": resource_type,
        "facts": lead.facts,
        "flags": dict(guards.flags),
        "costUsd30d": lead.cost_usd_30d,
    }
    validate(dto["facts"], "facts")
    validate(dto["flags"], "flags")
    validate(dto["costUsd30d"], "costUsd30d")
    if len(json.dumps(dto, separators=(",", ":"))) > MAX_CASE_CHARS:
        raise EvidenceError("the case is larger than a prompt may be")
    return dto
