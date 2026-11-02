#!/usr/bin/env python3
"""Check C14, the learning demonstration (docs/build-plan/03-first-checks.md). Standard library only.

    python evaluation/c14/run.py check PACK              validate a pack and its cases
    python evaluation/c14/run.py propose PACK --out DIR  the system drafts a claim from the source (model call)
    python evaluation/c14/run.py run PACK --out DIR      run the three arms once a reviewer has decided
    python evaluation/c14/run.py report DIR              render report.md again; the verdict is worked out again from review.json,
                                                         where a person records the reading of the updated answers
    python evaluation/c14/run.py demo [--out DIR]        the whole flow on pack-template with a scripted model; keeps nothing without --out

`propose` and `run` call the model through the hub; the environment names the route (see harness/client.py).
A real run needs a spending cap, the token prices, a reply limit and a call limit in the pack's params.json, written by pull
request first, and it exits 0 only when every pass condition holds, a person's reading of the answers included.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import demo, runner  # noqa: E402
from harness.cases import PackError, load_pack  # noqa: E402
from harness.client import ClientError, GuardedClient, HubClient, ScriptedClient, StopRun  # noqa: E402
from harness.report import render_report  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent / "pack-template"
DEMO_PRICES = (1.0, 4.0)  # invented, so that the demo can show a known cost; a real pack sets its own


def _positive(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _limits(pack) -> dict:
    """The limits of a real run. A stage stops at its cap, and a cap can only be enforced with prices and a
    reply limit, so a real run does not start without them: they are written by pull request before the run."""
    p = pack.params
    prices = p.get("price_per_million_tokens_eur") or {}
    missing = [name for name, value in (
        ("spending_cap_eur", p.get("spending_cap_eur")),
        ("max_model_calls", p.get("max_model_calls")),
        ("max_completion_tokens", p.get("max_completion_tokens")),
        ("price_per_million_tokens_eur.input", prices.get("input")),
        ("price_per_million_tokens_eur.output", prices.get("output")),
    ) if not _positive(value)]
    if missing:
        sys.exit("params.json: set " + ", ".join(missing) + " (by pull request, before the run). "
                 "A stage stops at its cap, and the cap is enforced from the prices and the reply limit.")
    return {"cap": float(p["spending_cap_eur"]), "max_calls": int(p["max_model_calls"]), "max_tokens": int(p["max_completion_tokens"]),
            "prices": (float(prices["input"]), float(prices["output"]))}


def _real_client(pack, *, extra_calls: int | None = None, used=(0, 0, 0)) -> GuardedClient:
    """The hub behind the stage's limits. `used` is what `propose` already spent; `extra_calls` limits this step (the stop test)."""
    limit = _limits(pack)
    calls = limit["max_calls"] if not extra_calls else min(limit["max_calls"], used[0] + extra_calls)
    return GuardedClient(HubClient(max_tokens=limit["max_tokens"]), max_calls=calls, prices=limit["prices"],
                         cap_eur=limit["cap"], max_completion_tokens=limit["max_tokens"], used=used)


def _pending(verdict) -> str:
    return ", ".join(name.replace("_", " ") for name, c in verdict["checks"].items() if c["ok"] is None)


def _status(verdict, stopped=None) -> str:
    if verdict and verdict["passed"]:
        return "Passed."
    if verdict and verdict["no_headroom"]:
        return "No headroom: use the reserve mechanism."
    if verdict and not verdict["failed"]:
        return f"Not passed yet; still open: {_pending(verdict)}."
    return f"Not passed: {verdict['failed'] if verdict else stopped}."


def cmd_check(args) -> int:
    pack = load_pack(args.pack)
    waste = sum(c.kind == "waste" for c in pack.cases)
    print(f"{pack.path.name}: {len(pack.snapshot)} claims in the snapshot, {waste} waste cases and {len(pack.cases) - waste} decoys, "
          f"no case shares {6} words with the source. Hashes: " + ", ".join(f"{k} {v[:12]}" for k, v in runner.pack_hashes(pack).items()))
    return 0


def cmd_propose(args) -> int:
    pack = load_pack(args.pack)
    client = _real_client(pack)
    proposal = runner.propose_claim(client, pack.source, pack.cases, pack.key)
    runner.write_proposal(Path(args.out), proposal, pack)
    print(f"proposal.json and review.json written to {args.out}. Problems found by code: {proposal['problems'] or 'none'}.")
    print("A reviewer now sets decision, reviewer and, if edited, the claim in review.json.")
    return 0


def _write(out: Path, results: dict) -> None:
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(render_report(results), encoding="utf-8")


def _run(pack, client, out: Path) -> int:
    decision, accepted, problems = runner.load_review(out, pack.source, pack.cases, pack.key, pack.snapshot, pack.control)
    if accepted is not None and not problems:
        mismatch = runner.control_problem(accepted, pack.control)
        if mismatch:
            problems = [mismatch]
    if accepted is None or problems:
        _write(out, runner.build_results(pack, accepted, decision, problems, None, None, runner.claim_edits(out, accepted)))
        print(f"The arms did not run: decision {decision}. {'; '.join(problems)}")
        return 1 if decision != "rejected" else 0
    outcome = runner.run_arms(pack, accepted, client)
    results = runner.build_results(pack, accepted, decision, problems, outcome, client, runner.claim_edits(out, accepted),
                                   runner.read_confirmation(out))
    results["review"]["fingerprint"] = runner.review_fingerprint(out)
    _write(out, results)
    verdict = results.get("verdict")
    print(f"report.md written to {out}. " + _status(verdict, outcome["stopped"]))
    return 0 if verdict and verdict["passed"] else 1


def cmd_run(args) -> int:
    pack = load_pack(args.pack)
    out = Path(args.out)
    return _run(pack, _real_client(pack, extra_calls=args.max_calls, used=runner.proposal_usage(out)), out)


def cmd_report(args) -> int:
    """Render report.md again; the verdict is worked out again from review.json, where a person records the reading of the answers."""
    directory = Path(args.dir)
    results = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    stored = results.get("review", {}).get("fingerprint")
    if stored and stored != runner.review_fingerprint(directory):
        print("error: review.json changed after the run (the decision, the reviewer or the claim): run the arms again", file=sys.stderr)
        return 2
    results = runner.reevaluate(results, runner.read_confirmation(directory))
    _write(directory, results)
    verdict = results.get("verdict")
    print(f"report.md written to {args.dir}. " + _status(verdict, results.get("stopped")))
    return 0 if verdict and verdict["passed"] else 1


def cmd_demo(args) -> int:
    if args.out:
        return _demo(Path(args.out), f"Output: {args.out}")
    with tempfile.TemporaryDirectory(prefix="c14-demo-") as scratch:
        return _demo(Path(scratch), "Nothing was kept: add --out DIR to keep the report.")


def _demo(out: Path, where: str) -> int:
    pack = load_pack(TEMPLATE)
    client = GuardedClient(ScriptedClient(demo.handler), max_calls=int(pack.params["max_model_calls"]), prices=DEMO_PRICES)
    proposal = runner.propose_claim(client, pack.source, pack.cases, pack.key)
    runner.write_proposal(out, proposal, pack)
    review = json.loads((out / "review.json").read_text(encoding="utf-8"))
    review.update({"decision": "accepted", "reviewer": "demo-reviewer (a script, not a person)",
                   "answers_read_by": "demo-reader (a script, not a person)", "answers_rest_on_the_claim": True})
    (out / "review.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    code = _run(pack, client, out)
    print("Demo with a scripted model, invented prices and a script standing in for the two people, on the invented "
          f"pack-template; nothing here says anything about a real model. {where}")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn, needs_out in (("check", cmd_check, False), ("propose", cmd_propose, True), ("run", cmd_run, True)):
        p = sub.add_parser(name)
        p.add_argument("pack")
        if needs_out:
            p.add_argument("--out", required=True)
        if name == "run":
            p.add_argument("--max-calls", type=int, help="stop after this many model calls (a stop test uses 2)")
        p.set_defaults(fn=fn)
    p = sub.add_parser("report")
    p.add_argument("dir")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("demo")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_demo)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except (PackError, ClientError, StopRun) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
