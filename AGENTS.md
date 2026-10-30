# Rules for agents working in this repository

Short, durable and binding for every session and every sub-agent. Each rule comes from the operator; the date is when it was given. Pass them on to any sub-agent you start.

1. **The repository stays PRIVATE until the operator says to switch it** (2026-10-31; decision [D6](docs/plan/01-assumptions-risks-decisions.md#3-decisions-decided-or-assumed)). Never change its visibility, and never publish any of its content elsewhere — no public fork, GitHub Pages site, release, gist, package, or text posted to another repository. Any plan step that says "publish" (kill criterion K5, Phase 8) waits for that word. Going public is a one-way door and is the operator's click.
2. **Ideation first; assume, don't ask** (2026-10-31). Open decisions carry an assumed default on the status board in [plan/01 §3](docs/plan/01-assumptions-risks-decisions.md#3-decisions-decided-or-assumed). Take the recommended option and record it; do not stop to ask the operator questions that have no purpose in ideation.
3. **Licence: MIT** (decision D2, 2026-10-31) — [`LICENSE`](LICENSE).
4. **Keep history.** Never edit `docs/_archive/` (the frozen earlier versions), and keep the raw reports in `docs/reviews/` verbatim apart from their headers and the appended spot-checks. A substantive change is a new version — a git tag and a [CHANGELOG](CHANGELOG.md) entry — never an overwrite.
5. **Before every commit** run `python tools/check-docs.py --strict` (standard library only; install nothing).
