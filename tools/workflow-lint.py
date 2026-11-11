#!/usr/bin/env python3
"""Checks the repository's GitHub Actions workflows against the rules in AGENTS.md (standard library only).

    python tools/workflow-lint.py [--dir .github/workflows]

The rules, each of which a workflow file can break by accident and a reviewer can miss:

  1. Every `uses:` is pinned to a full 40-character commit, so a moved tag cannot change what runs.
  2. Every `actions/checkout` sets `persist-credentials: false`.
  3. No `${{ ... }}` expression inside a `run:` script: a value (an input, a title, a name) would become
     part of the script. A value reaches a script through `env:` and is read as a shell variable.
  4. Each workflow sets `permissions:`; nothing is granted `write` except `id-token` in deploy-hub.yml and drift.yml.
  5. No workflow runs on `pull_request_target`, `workflow_run` or `issue_comment`.
  6. Only deploy-hub.yml and drift.yml sign in to Azure (`azure/login`, `az login`). deploy-hub.yml runs on `workflow_dispatch` (by hand) and `workflow_call` (called by the one workflow of
     the owner's private deploy repository: environment/deploy-repo/README.md) and on nothing else, with exactly one job whose `if:` is exactly the owner-and-main guard, a `concurrency` group and no
     `continue-on-error: true`. In a called run the `github` context is the caller's, so deploy-hub.yml never reads the commit or the repository from it (`github.sha`, `GITHUB_SHA`, `github.repository`,
     `GITHUB_REPOSITORY` and their kin: the code's own commit and repository are `job.workflow_sha` and `job.workflow_repository`), and every `actions/checkout` of it names those two, so that the tools and
     the templates that the steps run are this workflow's and never the caller's. drift.yml, the check that can only read (docs/proposals/10-ai-security-and-governance.md),
     runs on `workflow_dispatch` alone for now, and may run on a timer (`schedule`) once the constant DRIFT_ON_A_TIMER is
     set to True, which is done in the change that adds the timer after the read-only identity exists (environment/BOOTSTRAP.md, step G4): until then a `schedule:` is refused. It has exactly one job whose `if:` is exactly the main-and-(owner-or-timer)
     guard, a `concurrency` group, no `continue-on-error: true`, and it never signs in with the deploy identity: the
     read-only identity is another one, with a role that cannot change anything.

  7. No quoted value, and no list or map in brackets, goes on over several lines, and no character that some readers
     take for a line break: this tool reads one line at a time, so a line inside such a value could pass for a setting
     (an `if:` inside a quoted name) or a script line it never sees.

It reads the files as text, because a YAML parser is not part of the standard library; the layout it relies on
(two-space indentation, one key per line) is the one the workflows use, and a structure it does not understand is
reported rather than accepted. The exit code is 0 for no findings, 1 for findings, 2 when there is nothing to check.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = "deploy-hub.yml"
DRIFT = "drift.yml"
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
STEP_START = re.compile(r"^(\s*)- (?:name|uses|run|id|if|env|with|shell|working-directory|continue-on-error|timeout-minutes):")
FORBIDDEN_EVENTS = {"pull_request_target", "workflow_run", "issue_comment"}
ALLOWED_WRITES = {DEPLOY: {"id-token"}, DRIFT: {"id-token"}}
OWNER_GUARD = "github.actor == 'tinodo' && github.ref == 'refs/heads/main'"
# The Hub starts by hand in its own repository and is called by the one workflow of the private deploy repository, which itself starts by hand: nothing else may start it.
DEPLOY_TRIGGERS = {"workflow_dispatch", "workflow_call"}
# In a called run the `github` context, and the variables made from it, are the caller's: its commit and its repository, not the code's own. The code's own are `job.workflow_sha` and `job.workflow_repository`.
CALLER_CONTEXT = re.compile(r"\bGITHUB_(?:SHA|REPOSITORY|WORKFLOW_SHA|WORKFLOW_REF)\b|\bgithub\.(?:sha|repository|workflow_sha|workflow_ref)\b")
OWN_REPOSITORY = re.compile(r"^\s*repository:\s*\$\{\{\s*job\.workflow_repository\s*\}\}\s*$", re.M)
OWN_COMMIT = re.compile(r"^\s*ref:\s*\$\{\{\s*job\.workflow_sha\s*\}\}\s*$", re.M)
# The check that can only read may run on a timer, and a timer has no person behind it: the guard asks for main, and then for the owner or the timer. The identity that it signs in with has a federated
# credential for the main branch alone and a role that cannot change anything, so a run elsewhere could not sign in, and a run that does sign in could change nothing.
DRIFT_GUARD = "github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || github.actor == 'tinodo')"
# False until the owner has made the read-only identity (environment/BOOTSTRAP.md, step G4): a timer would start a run, spend minutes of GitHub Actions that are limited (AGENTS.md rule 35) and sign in with an
# identity that does not exist. The change that adds `schedule:` to drift.yml sets this to True, and nothing else lets a timer through.
DRIFT_ON_A_TIMER = False
GUARDS = {DEPLOY: OWNER_GUARD, DRIFT: DRIFT_GUARD}
# The deploy identity's secret: the read-only check never names it.
DEPLOY_IDENTITY = "secrets.AZURE_CLIENT_ID"
# Control characters, and the line breaks that Python splits on and YAML readers do not all agree about.
ODD_CHARACTERS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x85\u2028\u2029]")
BLOCK_HEADER = re.compile(r"[|>](?:[+-]\d?|\d[+-]?)?(?:\s+#.*)?")
MARKERS = re.compile(r"^\s*(?:[-?:]\s+)*")
KEY = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s"'\[\]{},#&*!|>%@`][^#]*?)\s*:(?:\s+|$)""")


def indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def code(line: str) -> str:
    """The line without a trailing comment (a # that follows a space), and nothing at all for a line that is only a comment."""
    if line.lstrip().startswith("#"):
        return ""
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


def closes(value: str) -> bool:
    """False when a quoted value, or a list or map in brackets, that starts this value is still open at the end of the line.

    A quote mark opens a string only where YAML lets a string start (the first thing in the value, or after `[`, `{`, `,`
    or `:` inside brackets), so an apostrophe inside a plain value, as in `it's` or `== 'main'`, is just a character."""
    if not value or value[0] not in "\"'[{":
        return True
    quote, depth, previous, i = "", 0, "", 0
    while i < len(value):
        c = value[i]
        if quote:
            if quote == '"' and c == "\\":
                i += 2
                continue
            if c == quote:
                if quote == "'" and value[i + 1:i + 2] == "'":
                    i += 2
                    continue
                quote, previous = "", c
                if depth == 0:
                    return True
        elif c in "\"'" and (previous == "" or previous in "[{,:"):
            quote = c
        elif c in "[{":
            depth, previous = depth + 1, c
        elif c in "]}":
            depth, previous = depth - 1, c
            if depth <= 0:
                return True
        elif c != " ":
            previous = c
        i += 1
    return False


def open_values(lines: list[str]) -> list[int]:
    """Numbers of the lines on which a quoted value, or a list or map in brackets, is opened and not closed on that line.

    A value that goes on over the next lines can hold a line that only looks like a setting, or a script line this
    reader never sees, so it is refused. Block scalars (`|`, `>`) are skipped: their lines are text, not YAML."""
    found, body_of = [], None
    for number, line in enumerate(lines, 1):
        if body_of is not None:
            if not line.strip() or indent(line) > body_of:
                continue
            body_of = None
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        rest = MARKERS.sub("", line.rstrip(), count=1)
        key = KEY.match(rest)
        value = (rest[key.end():] if key else rest).strip()
        if BLOCK_HEADER.fullmatch(value):
            body_of = len(line.rstrip()) - len(rest) if key else indent(line)
        elif not closes(value):
            found.append(number)
    return found


def script_lines(block: list[str], first: int):
    """Yields (line number, text) of every `run:` script in a step."""
    for i, line in enumerate(block):
        match = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", line)
        if not match:
            continue
        key_indent = len(match.group(1)) + (2 if line.lstrip().startswith("- ") else 0)
        value = match.group(2)
        if not re.fullmatch(r"[|>][+-]?\d*", value.strip()):
            yield first + i + 1, value
        # a block script, or a plain value that goes on over lines indented deeper than its key: read to the end of it
        for j in range(i + 1, len(block)):
            if block[j].strip() and indent(block[j]) <= key_indent:
                break
            yield first + j + 1, block[j]


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


def jobs_of(lines: list[str]) -> tuple[dict[str, list[str]], list[int]]:
    """The top-level jobs, each with its lines, and the numbers of the lines under `jobs:` that are not a plain job header.

    A plain header is two spaces, a name and a colon, and nothing else on the line. A comment, an anchor, a quoted
    name or flow style is valid YAML that this reader does not follow, so it is reported and never ignored."""
    start = next((i for i, line in enumerate(lines) if re.match(r"^jobs:\s*$", line)), None)
    jobs: dict[str, list[str]] = {}
    odd: list[int] = []
    if start is None:
        return jobs, odd
    current = None
    for number, line in enumerate(lines[start + 1:], start + 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent(line) == 0:
            break
        if indent(line) < 4:
            match = re.fullmatch(r" {2}([A-Za-z_][\w-]*):", line.rstrip())
            if match:
                current = match.group(1)
                jobs[current] = []
            else:
                odd.append(number)
                current = None
        elif current is not None:
            jobs[current].append(line)
    return jobs, odd


def job_conditions(body: list[str]) -> list[str]:
    """The job's own `if:` (four spaces in), with quotes and a ${{ }} wrapper taken off.

    A condition that goes on over the next line is returned with a mark that no guard equals."""
    found = []
    for i, line in enumerate(body):
        match = re.match(r"^ {4}if:\s*(.+?)\s*$", code(line))
        if match:
            value = match.group(1)
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            wrapped = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", value)
            value = wrapped.group(1) if wrapped else value
            following = next((b for b in body[i + 1:] if b.strip() and not b.lstrip().startswith("#")), "")
            found.append(value + " <continued on the next line>" if following and indent(following) > 4 else value)
    return found


def lint_file(path: Path) -> list[str]:
    name = path.name
    text_of_file = path.read_text(encoding="utf-8")
    lines = text_of_file.splitlines()
    problems: list[str] = []

    def add(number: int, message: str) -> None:
        problems.append(f"{name}:{number}: {message}")

    odd = ODD_CHARACTERS.search(text_of_file)
    if odd:
        add(text_of_file.count("\n", 0, odd.start()) + 1, f"the character U+{ord(odd.group()):04X}: a control character, or a line break that readers do not agree about, so the lines as this tool counts them may not be the lines GitHub reads")

    for i, line in enumerate(lines):
        if re.match(r"^ *\t", line):
            add(i + 1, "a tab in the indentation: YAML does not allow it, and this reader would misplace the line")

    for number in open_values(lines):
        add(number, "a quoted value, or a list or map in brackets, that goes on over the next lines: this reader sees one line at a time, so a line inside it could pass for a setting or a script line; put it on one line")

    for i, line in enumerate(lines):
        match = re.match(r"^\s*(?:- )?uses:\s*([^\s#]+)", line)
        if match and not PINNED.match(match.group(1)):
            add(i + 1, f"`{match.group(1)}` is not pinned to a full commit (owner/repo@<40 hex characters>)")

    for first, block in steps(lines):
        text = "\n".join(block)
        if re.search(r"uses:\s*actions/checkout@", text) and not re.search(r"persist-credentials:\s*false\b", text):
            add(first + 1, "actions/checkout without `persist-credentials: false`")
        if name == DEPLOY and re.search(r"uses:\s*actions/checkout@", text) and not (
                len(OWN_REPOSITORY.findall(text)) == 1 and len(re.findall(r"(?m)^\s*repository:", text)) == 1
                and len(OWN_COMMIT.findall(text)) == 1 and len(re.findall(r"(?m)^\s*ref:", text)) == 1):
            add(first + 1, "actions/checkout of the Hub without `repository: ${{ job.workflow_repository }}` and `ref: ${{ job.workflow_sha }}`, each once: a plain checkout is the repository that started the run, "
                           "which for a call is the caller's, so the tools and the templates that the steps run would be the caller's and not this workflow's")
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
    if name not in GUARDS:
        for number in azure_login:
            add(number, f"signs in to Azure; only {DEPLOY} and {DRIFT} may")
    else:
        guard = GUARDS[name]
        if name == DEPLOY and triggers != DEPLOY_TRIGGERS:
            add(1, f"must run on `workflow_dispatch` (by hand) and `workflow_call` (the deploy repository's workflow calls it) and on nothing else, not on {sorted(triggers) or 'nothing'}")
        if name == DRIFT and not ({"workflow_dispatch"} <= triggers <= ({"workflow_dispatch", "schedule"} if DRIFT_ON_A_TIMER else {"workflow_dispatch"})):
            if DRIFT_ON_A_TIMER:
                add(1, f"must run on `workflow_dispatch`, and may run on a timer (`schedule`), and on nothing else, not on {sorted(triggers) or 'nothing'}")
            else:
                add(1, f"must run on `workflow_dispatch` alone, not on {sorted(triggers) or 'nothing'}: a timer is added only after the read-only identity exists (environment/BOOTSTRAP.md, step G4), "
                       "in the change that sets DRIFT_ON_A_TIMER in this tool")
        text = "\n".join(lines)
        jobs, odd = jobs_of(lines)
        for number in odd:
            add(number, "a line under `jobs:` that is not a plain job header (two spaces, a name, a colon): a comment, an anchor, a quoted name or flow style is not followed here, so it is refused")
        if len(jobs) != 1:
            add(1, f"must have exactly one job, not {len(jobs)}: the guard below is checked on that job, so a second one would go unchecked")
        for job, body in jobs.items():
            if job_conditions(body) != [guard]:
                who = "only for the owner and only on main" if name == DEPLOY else "only on main, started by the owner or by its timer"
                add(1, f"job `{job}` must run {who}: its `if:` is exactly `{guard}`")
        if not re.search(r"^concurrency:", text, re.M):
            add(1, "no `concurrency:` group: two runs could change the same resources at once" if name == DEPLOY else "no `concurrency:` group: two runs of the check could overlap")
        for i, line in enumerate(lines):
            if re.match(r"^\s*continue-on-error:\s*true\b", code(line)):
                add(i + 1, "`continue-on-error: true` would let a failed step pass")
            if name == DEPLOY and CALLER_CONTEXT.search(code(line)):
                add(i + 1, f"`{CALLER_CONTEXT.search(code(line)).group()}` is the caller's when this workflow is called, so it would name the deploy repository's commit or repository and not this code's own; "
                           "use `job.workflow_sha` and `job.workflow_repository` (through the step's `env:`)")
            if name == DRIFT and DEPLOY_IDENTITY in code(line):
                add(i + 1, f"`{DEPLOY_IDENTITY}` is the deploy identity, which can change Azure: the read-only check signs in with an identity of its own, whose role cannot change anything (environment/BOOTSTRAP.md, step G4)")
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
