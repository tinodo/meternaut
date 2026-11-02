"""The two steps of the demonstration, and the run of the three arms.

1. `propose_claim`: the system reads the new source and drafts a claim with its receipt. Code checks that
   the quote is on the page. The draft goes to a reviewer, who accepts, edits or rejects it (review.json).
2. `run_arms`: the finder answers every case in three arms, several times each: frozen (the snapshot),
   control (the snapshot plus an unrelated accepted claim) and updated (the snapshot plus the accepted claim).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .cases import ARMS, Pack, Source, copied_from_cases, pack_hashes
from .claims import Claim, ClaimError, parse_claim, quote_hash, render_for_prompt, verify_receipts
from .client import ClientError, GuardedClient, ModelClient, StopRun
from .prompts import FINDER_SYSTEM, PROPOSER_SYSTEM, finder_user, proposer_user
from .scoring import CaseScore, RunSummary, decide, extract_json_object, parse_answer, score_case, summarise_run

DECISIONS = ("accepted", "edited", "rejected")
LIMITS = (
    "A handful of synthetic cases written by the team, one mechanism, one model alias. "
    "It shows that the loop works, not how far it generalises; proof point P6 in phase 1b tests that."
)


def propose_claim(client: ModelClient, source: Source, cases=(), key: dict | None = None) -> dict:
    """Ask the system for a claim from the source. Returns the draft, the problems found and the raw reply."""
    completion = client.complete(PROPOSER_SYSTEM, proposer_user(source))
    result = {"claim": None, "problems": [], "raw": completion.text,
              "tokens": [completion.prompt_tokens, completion.completion_tokens]}
    obj = extract_json_object(completion.text)
    if obj is None:
        result["problems"].append("the reply holds no JSON object")
        return result
    quote = str(obj.pop("quote", ""))
    obj["receipts"] = [{"url": source.url, "retrieved": source.retrieved, "quote": quote, "quote_sha256": quote_hash(quote)}]
    try:
        claim = parse_claim(obj)
    except ClaimError as e:
        result["problems"].extend(e.problems)
        return result
    result["claim"] = claim
    result["problems"].extend(verify_receipts(claim, {source.url: source.text}))
    copied = copied_from_cases(" ".join([claim.statement] + [r.quote for r in claim.receipts]), cases, key)
    if copied:
        result["problems"].append(f"the draft gives away a case, so the cases are no longer unseen: {copied}")
    return result


def write_proposal(out: Path, proposal: dict, pack: Pack) -> None:
    out.mkdir(parents=True, exist_ok=True)
    draft = proposal["claim"].to_dict() if proposal["claim"] else None
    (out / "proposal.json").write_text(json.dumps({
        "draft": draft, "problems": proposal["problems"], "raw_reply": proposal["raw"], "tokens": proposal["tokens"],
        "usage": {"calls": 1, "prompt_tokens": proposal["tokens"][0], "completion_tokens": proposal["tokens"][1]},
        "source": {"url": pack.source.url, "retrieved": pack.source.retrieved},
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    review = out / "review.json"
    if not review.exists():
        review.write_text(json.dumps({
            "decision": "pending", "reviewer": "", "notes": "",
            "claim": draft,
            "answers_read_by": "", "answers_rest_on_the_claim": None,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def proposal_usage(out: Path) -> tuple[int, int, int]:
    """Calls and tokens that `propose` already used, so that the stage's limit and cap cover both steps."""
    path = out / "proposal.json"
    if not path.exists():
        return (0, 0, 0)
    usage = json.loads(path.read_text(encoding="utf-8")).get("usage") or {}
    return (int(usage.get("calls", 0)), int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))


def review_fingerprint(out: Path) -> str | None:
    """A hash of what the reviewer decided (the decision, the reviewer and the claim), so that a change after a run shows."""
    path = out / "review.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    material = {key: data.get(key) for key in ("decision", "reviewer", "claim")}
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


def read_confirmation(out: Path) -> bool | None:
    """True when a named person recorded that every updated answer rests on the new claim; False when they
    recorded that one does not; None until a person has read them."""
    path = out / "review.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not str(data.get("answers_read_by", "")).strip():
        return None
    verdict = data.get("answers_rest_on_the_claim")
    return verdict if isinstance(verdict, bool) else None


def load_review(out: Path, source: Source, cases=(), key: dict | None = None, snapshot=(), control: Claim | None = None
                ) -> tuple[str, Claim | None, list[str]]:
    """The reviewer's decision, the claim that enters memory (None when rejected) and any problem with it."""
    path = out / "review.json"
    if not path.exists():
        return "pending", None, ["review.json does not exist: run propose first"]
    data = json.loads(path.read_text(encoding="utf-8"))
    decision = data.get("decision")
    if decision not in DECISIONS:
        return "pending", None, ["review.json: a person sets decision to accepted, edited or rejected"]
    if not str(data.get("reviewer", "")).strip():
        return decision, None, ["review.json: name the reviewer"]
    if decision == "rejected":
        return decision, None, []
    try:
        claim = parse_claim(data.get("claim"))
    except ClaimError as e:
        return decision, None, [f"review.json: {x}" for x in e.problems]
    problems = verify_receipts(claim, {source.url: source.text})
    copied = copied_from_cases(" ".join([claim.statement] + [r.quote for r in claim.receipts]), cases, key)
    if copied:
        problems.append(f"the claim gives away a case, so the cases are no longer unseen: {copied}")
    changed = claim_edits(out, claim)
    if decision == "accepted" and changed:
        problems.append(f"the decision is accepted but the claim differs from the system's draft ({', '.join(changed)}): set decision to edited")
    if decision == "edited" and not changed:
        problems.append("the decision is edited but the claim equals the system's draft: set decision to accepted")
    held = {c.id for c in snapshot} | ({control.id} if control else set())
    if claim.id in held:
        problems.append(f"the claim's id {claim.id!r} is already used by a claim of the snapshot or the control")
    if control and set(claim.mechanism) & set(control.mechanism):
        problems.append("the control claim must be unrelated to the new one, but they share a mechanism: choose another control")
    return decision, claim, problems


def claim_edits(out: Path, accepted: Claim | None) -> list[str]:
    """The fields that the reviewer changed from the system's draft, for the report."""
    path = out / "proposal.json"
    if accepted is None or not path.exists():
        return []
    draft = json.loads(path.read_text(encoding="utf-8")).get("draft")
    if not isinstance(draft, dict):
        return ["the system's draft was not a valid claim"]
    final = accepted.to_dict()
    changed = [k for k in ("id", "statement", "mechanism", "scope", "level") if draft.get(k) != final.get(k)]
    if [r.get("quote") for r in draft.get("receipts", [])] != [r["quote"] for r in final["receipts"]]:
        changed.append("quote")
    return changed


def control_problem(accepted: Claim, control: Claim, tolerance: float = 0.3) -> str | None:
    """The control claim must look like the new one to the finder: the same length as it appears in the prompt."""
    a, c = len(render_for_prompt(accepted)), len(render_for_prompt(control))
    if abs(c - a) > tolerance * a:
        return f"the control claim takes {c} characters in the prompt against {a} for the new claim; match them within {tolerance:.0%}"
    return None


def memory_hash(claims: list[Claim]) -> str:
    return hashlib.sha256(json.dumps([c.to_dict() for c in claims], sort_keys=True).encode("utf-8")).hexdigest()


def run_arms(pack: Pack, accepted: Claim, client: GuardedClient) -> dict:
    """Run every arm `runs_per_arm` times over every case. A stop at the call limit or the cap ends the run early."""
    memories = {
        "frozen": list(pack.snapshot),
        "control": [*pack.snapshot, pack.control],
        "updated": [*pack.snapshot, accepted],
    }
    runs: dict[str, list[list[CaseScore]]] = {arm: [] for arm in ARMS}
    records: list[dict] = []
    stopped = None
    tolerance = pack.params["price_tolerance_pct"]
    try:
        for run_index in range(int(pack.params["runs_per_arm"])):
            scores_now = {arm: [] for arm in ARMS}
            for arm in ARMS:
                for case in pack.cases:
                    try:
                        reply = client.complete(FINDER_SYSTEM, finder_user(memories[arm], case))
                        answer = parse_answer(reply.text)
                    except ClientError as e:
                        raise StopRun(f"the hub failed: {e}")
                    score = score_case(case, pack.key[case.id], answer, tolerance)
                    scores_now[arm].append(score)
                    records.append({
                        "arm": arm, "run": run_index + 1, "case": case.id, "reply": reply.text,
                        "cites_new_claim": bool(answer and accepted.id in answer.claim_ids),
                        "answer": None if answer is None else {
                            "waste": answer.waste, "monthly_waste_eur": answer.monthly_waste_eur,
                            "claim_ids": list(answer.claim_ids), "explanation": answer.explanation, "action": answer.action},
                        "score": score.__dict__, "tokens": [reply.prompt_tokens, reply.completion_tokens],
                    })
            for arm in ARMS:
                runs[arm].append(scores_now[arm])
    except StopRun as e:
        stopped = str(e)
    return {
        "memories": {arm: {"claims": [c.id for c in claims], "sha256": memory_hash(claims)} for arm, claims in memories.items()},
        "runs": runs, "records": records, "stopped": stopped,
    }


def _within_cap(cost: float | None, cap) -> bool | None:
    return None if cost is None else (cap is None or cost <= cap)


def build_results(pack: Pack, accepted: Claim | None, decision: str, review_problems: list[str],
                  outcome: dict | None, client: GuardedClient | None, edits: list[str] | None = None,
                  answers_ok: bool | None = None) -> dict:
    """Everything the report needs, as plain data."""
    results = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pack": str(pack.path.name), "params": pack.params, "hashes": pack_hashes(pack),
        "review": {"decision": decision, "problems": review_problems, "edits": edits or [],
                   "claim": accepted.to_dict() if accepted else None},
        "limits": LIMITS,
    }
    if outcome is None:
        results["verdict"] = None
        return results
    complete = outcome["stopped"] is None
    summaries = {arm: [summarise_run(r) for r in outcome["runs"][arm]] for arm in ARMS}
    cost = client.cost_eur if client else None
    within_cap = _within_cap(cost, pack.params.get("spending_cap_eur"))
    results.update({
        "memories": outcome["memories"], "stopped": outcome["stopped"],
        "summaries": {arm: [s.__dict__ for s in rows] for arm, rows in summaries.items()},
        "cites_new_claim": sum(r["cites_new_claim"] for r in outcome["records"] if r["arm"] == "updated" and r["score"]["found"]),
        "usage": {"calls": client.calls if client else 0, "prompt_tokens": client.prompt_tokens if client else 0,
                  "completion_tokens": client.completion_tokens if client else 0, "cost_eur": cost},
        "answers_confirmed": answers_ok,
        "records": outcome["records"],
    })
    if complete and all(len(summaries[arm]) == int(pack.params["runs_per_arm"]) for arm in ARMS):
        results["verdict"] = decide(summaries, pack.params, quote_ok=not review_problems,
                                    review_ok=decision in ("accepted", "edited"), within_cap=within_cap, answers_ok=answers_ok)
    else:
        results["verdict"] = None
    return results


def reevaluate(results: dict, answers_ok: bool | None) -> dict:
    """The verdict of a finished run again, once a person has read the updated answers and recorded what they found."""
    if results.get("verdict") is None or "summaries" not in results:
        return results
    summaries = {arm: [RunSummary(**row) for row in rows] for arm, rows in results["summaries"].items()}
    params, review = results["params"], results["review"]
    results["answers_confirmed"] = answers_ok
    results["verdict"] = decide(summaries, params, quote_ok=not review["problems"], review_ok=review["decision"] in ("accepted", "edited"),
                                within_cap=_within_cap(results["usage"]["cost_eur"], params.get("spending_cap_eur")), answers_ok=answers_ok)
    return results
