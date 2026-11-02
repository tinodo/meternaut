"""The report of check C14: a before-and-after table, the pass conditions, the cost and the limits."""
from __future__ import annotations

ARM_LABELS = {
    "frozen": "Frozen memory",
    "control": "Control: an unrelated claim added",
    "updated": "Updated: the new claim added",
}
EXPLANATION_CHARS = 220


def _table(rows: list[list[str]], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _headline(results: dict) -> str:
    verdict = results.get("verdict")
    if "summaries" not in results:
        return "The arms have not run."
    if verdict is None:
        return f"**The run is incomplete**: {results.get('stopped') or 'not every run finished'}."
    if verdict.get("no_headroom"):
        return ("**No headroom.** A baseline finds more of the cases than the bar allows, so the model already knows the mechanism. "
                "Record this result, use the reserve mechanism with new cases, and keep this report.")
    if verdict["passed"]:
        return "**Every pass condition holds.**"
    if verdict["pending"] and not verdict["failed"]:
        names = {"within_cap": "the cost, read from the hub's logs", "answers_read": "a person's reading of the updated answers"}
        waiting = [names.get(n, n) for n, c in verdict["checks"].items() if c["ok"] is None]
        return "**Every pass condition that the code can read holds. Still open: " + ", ".join(waiting) + ".**"
    return f"**Not passed:** {', '.join(verdict['failed'])}."


def _answers_to_read(results: dict) -> list[str]:
    """Every updated answer that found a case, for the person who did not build the harness to read."""
    rows = []
    for r in results.get("records", []):
        if r["arm"] == "updated" and r["score"]["found"]:
            explanation = ((r.get("answer") or {}).get("explanation") or "").replace("\n", " ")[:EXPLANATION_CHARS]
            rows.append([r["case"], str(r["run"]), "yes" if r["cites_new_claim"] else "NO", explanation])
    if not rows:
        return []
    return ["## Updated answers to read", "",
            "A person who did not build the harness reads each one and confirms that it rests on the new claim. "
            "They then set `answers_read_by` (their name) and `answers_rest_on_the_claim` (true or false) in `review.json` "
            "and run `python evaluation/c14/run.py report` on this folder; the pass is not reached before that.", "",
            _table(rows, ["Case", "Run", "Cites the new claim", "Explanation"]), ""]


def render_report(results: dict) -> str:
    params = results["params"]
    review = results["review"]
    out = [f"# Check C14: {results['pack']}", ""]
    edits = review.get("edits") or []
    out += [
        f"Created {results['created']}. Reviewer's decision on the proposed claim: **{review['decision']}**; "
        f"fields the reviewer changed: {', '.join(edits) if edits else 'none'}."
        + (f" Problems: {'; '.join(review['problems'])}." if review["problems"] else ""),
        "",
        _headline(results), "",
    ]
    verdict = results.get("verdict")

    if "summaries" in results:
        rows = []
        for arm, summaries in results["summaries"].items():
            found = ", ".join(str(s["found"]) for s in summaries)
            priced = ", ".join(str(s["priced"]) for s in summaries)
            flagged = ", ".join(str(s["false_positives"]) for s in summaries)
            rows.append([ARM_LABELS.get(arm, arm), found, priced, flagged])
        waste, decoys = params["waste_cases"], params["decoy_cases"]
        out += [
            f"## Answers, one number per run ({waste} cases where the mechanism wastes money, {decoys} decoys)", "",
            _table(rows, ["Arm", f"Waste found (of {waste})", "Priced inside the tolerance", f"Decoys flagged (of {decoys})"]), "",
        ]
        if verdict:
            out += ["## Pass conditions", ""]
            out += [f"- {'yes' if c['ok'] else 'NOT YET' if c['ok'] is None else 'NO'}: {c['detail']}" for c in verdict["checks"].values()]
            out.append("")
        usage = results["usage"]
        cost = "read it from the hub's logs" if usage["cost_eur"] is None else f"{usage['cost_eur']:.2f} EUR"
        cap = params.get("spending_cap_eur")
        cap_text = f"The spending cap of the stage is {cap} EUR" if cap is not None else "No spending cap is set (a real run refuses to start without one)"
        out += [
            "## Cost", "",
            f"{usage['calls']} model calls, {usage['prompt_tokens']} input and {usage['completion_tokens']} output tokens; cost: {cost}. "
            f"{cap_text}, and the call limit is {params['max_model_calls']}.", "",
        ]
        out += _answers_to_read(results)
    if review.get("claim"):
        claim = review["claim"]
        quote = claim["receipts"][0]["quote"]
        out += ["## The claim that entered memory", "", f"`{claim['id']}`: {claim['statement']}", "", f"> {quote}", "",
                f"Source: {claim['receipts'][0]['url']}, read {claim['receipts'][0]['retrieved']}.", ""]
    out += ["## What was fixed before the first run", ""]
    out += [f"- {name}: `{digest[:16]}`" for name, digest in results["hashes"].items()]
    out += ["", "## Limits", "", results["limits"], ""]
    return "\n".join(out)
