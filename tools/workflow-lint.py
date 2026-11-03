#!/usr/bin/env python3
"""Checks the repository's GitHub Actions workflows against the rules in AGENTS.md (standard library only).

    python tools/workflow-lint.py [--dir .github/workflows]

The rules, each of which a workflow file can break by accident and a reviewer can miss:

  1. Every `uses:` is pinned to a full 40-character commit, so a moved tag cannot change what runs.
  2. Every `actions/checkout` sets `persist-credentials: false`.
  3. No `${{ ... }}` expression inside a `run:` script: a value (an input, a title, a name) would become
     part of the script. A value reaches a script through `env:` and is read as a shell variable.
  4. Each workflow sets `permissions:`; nothing is granted `write` except `id-token` in deploy-hub.yml.
  5. No workflow runs on `pull_request_target`, `workflow_run` or `issue_comment`.
  6. Only deploy-hub.yml signs in to Azure (`azure/login`, `az login`), and it runs on `workflow_dispatch` alone,
     only on main and only for the owner, with a `concurrency` group and without `continue-on-error: true`.

It reads the files as text, because a YAML parser is not part of the standard library; the layout it relies on
(two-space indentation, one key per line) is the one the workflows use. The exit code is 0 for no findings, 1 for
findings, 2 when there is nothing to check.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = "deploy-hub.yml"
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
STEP_START = re.compile(r"^(\s*)- (?:name|uses|run|id|if|env|with|shell|working-directory|continue-on-error|timeout-minutes):")
FORBIDDEN_EVENTS = {"pull_request_target", "workflow_run", "issue_comment"}
ALLOWED_WRITES = {DEPLOY: {"id-token"}}


def indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def code(line: str) -> str:
    """The line without a trailing comment (a # that follows a space)."""
    return re.split(r"\s#", line, maxsplit=1)[0].rstrip()


def steps(lines: list[str]):
    """Yields (first line number, lines) for every step of every job."""
    starts = [i for i, line in enumerate(lines) if STEP_START.match(line)]
    for n, start in enumerate(starts):
        dash = indent(lines[start])
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if not lines[j].strip():
                continue
            if indent(lines[j]) < dash or (indent(lines[j]) == dash and lines[j].lstrip().startswith("- ")):
                end = j
                break
        yield start, lines[start:end]


def script_lines(block: list[str], first: int):
    """Yields (line number, text) of every `run:` script in a step."""
    for i, line in enumerate(block):
        match = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", line)
        if not match:
            continue
        key_indent = len(match.group(1)) + (2 if line.lstrip().startswith("- ") else 0)
        value = match.group(2)
        if re.fullmatch(r"[|>][+-]?\d*", value.strip()):
            for j in range(i + 1, len(block)):
                if block[j].strip() and indent(block[j]) <= key_indent:
                    break
                yield first + j + 1, block[j]
        else:
            yield first + i + 1, value


def events(lines: list[str]) -> set[str]:
    for i, line in enumerate(lines):
        match = re.match(r"^(?:on|\"on\"|'on'):\s*(.*)$", line)
        if not match:
            continue
        inline = code(match.group(1)).strip()
        if inline:
            return {e.strip(" \"'") for e in inline.strip("[]{}").split(",") if e.strip()}
        found = set()
        for j in range(i + 1, len(lines)):
            if lines[j].strip() and indent(lines[j]) == 0:
                break
            key = re.match(r"^ {2}([A-Za-z_]+):", lines[j])
            if key:
                found.add(key.group(1))
        return found
    return set()


def permission_writes(lines: list[str]) -> list[tuple[int, str]]:
    found = []
    for i, line in enumerate(lines):
        if re.match(r"^\s*permissions:\s*(write-all|read-all)\s*$", code(line)):
            found.append((i + 1, code(line).split(":")[1].strip()))
        match = re.match(r"^\s+([a-z-]+):\s*write\s*$", code(line))
        if match:
            found.append((i + 1, match.group(1)))
    return found


def lint_file(path: Path) -> list[str]:
    name = path.name
    lines = path.read_text(encoding="utf-8").splitlines()
    problems: list[str] = []

    def add(number: int, message: str) -> None:
        problems.append(f"{name}:{number}: {message}")

    for i, line in enumerate(lines):
        match = re.match(r"^\s*(?:- )?uses:\s*([^\s#]+)", line)
        if match and not PINNED.match(match.group(1)):
            add(i + 1, f"`{match.group(1)}` is not pinned to a full commit (owner/repo@<40 hex characters>)")

    for first, block in steps(lines):
        text = "\n".join(block)
        if re.search(r"uses:\s*actions/checkout@", text) and not re.search(r"persist-credentials:\s*false\b", text):
            add(first + 1, "actions/checkout without `persist-credentials: false`")
        for number, script in script_lines(block, first):
            if "${{" in script:
                add(number, "a `${{ }}` expression inside a run script; pass the value through `env:` and read it as a shell variable")

    if not any(re.match(r"^permissions:", line) for line in lines):
        add(1, "no top-level `permissions:`")
    for number, what in permission_writes(lines):
        if what in ("write-all", "read-all"):
            add(number, f"`permissions: {what}`; name each permission")
        elif what not in ALLOWED_WRITES.get(name, set()):
            add(number, f"`{what}: write` is not allowed in {name}")

    triggers = events(lines)
    for event in sorted(triggers & FORBIDDEN_EVENTS):
        add(1, f"runs on `{event}`, which runs repository code with more trust than a pull request should have")

    azure_login = [i + 1 for i, line in enumerate(lines) if re.search(r"azure/login@|\baz login\b", line)]
    if name != DEPLOY:
        for number in azure_login:
            add(number, f"signs in to Azure; only {DEPLOY} may")
    else:
        if triggers != {"workflow_dispatch"}:
            add(1, f"must run on `workflow_dispatch` alone, not on {sorted(triggers) or 'nothing'}")
        text = "\n".join(lines)
        if not re.search(r"^\s+if:.*github\.actor == 'tinodo'.*", text, re.M) or "github.ref == 'refs/heads/main'" not in text:
            add(1, "the job must run only for the owner (`github.actor == 'tinodo'`) and only on main (`github.ref == 'refs/heads/main'`)")
        if not re.search(r"^concurrency:", text, re.M):
            add(1, "no `concurrency:` group: two runs could change the same resources at once")
        for i, line in enumerate(lines):
            if re.match(r"^\s*continue-on-error:\s*true\b", code(line)):
                add(i + 1, "`continue-on-error: true` would let a failed step pass")
        if not azure_login:
            add(1, "does not sign in to Azure")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=str(ROOT / ".github" / "workflows"))
    args = parser.parse_args(argv)
    files = sorted(Path(args.dir).glob("*.yml")) + sorted(Path(args.dir).glob("*.yaml"))
    if not files:
        print(f"error: no workflow files in {args.dir}", file=sys.stderr)
        return 2
    problems = [p for f in files for p in lint_file(f)]
    for problem in problems:
        print(problem)
    print(f"{len(files)} workflow(s) checked, {len(problems)} finding(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
