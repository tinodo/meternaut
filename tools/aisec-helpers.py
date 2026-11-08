#!/usr/bin/env python3
"""What the AI-security tools share: the Azure CLI token, one HTTP client that goes only to a Foundry project, the spend cap, plain printing, and the code of the app that they hold
the agents against (standard library only).

The tools agents-drift.py, foundry-evals.py, foundry-redteam.py and agent365-check.py run inside the network (operator/run-tool.sh) with the Operator's identity. Each of them loads this
file from its own folder, as cases-check.py loads check-helpers.py, so the Hub workflow sends both to the Operator. The code of the app that they need (lockfile.py, plaintext.py and
drift_rules.py: one comparison logic, the app's own) is loaded from the same folder when it is there, and from the repository otherwise.
"""
from __future__ import annotations

import datetime as dt
import http.client
import importlib
import json
import os
import re
import subprocess
import sys
import time
import types
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CASES = ROOT / "src" / "case-functions" / "cases"
EVALUATION = ROOT / "evaluation"
FOUNDRY_RESOURCE = "https://ai.azure.com"
GRAPH_RESOURCE = "https://graph.microsoft.com"
ENDPOINT = re.compile(r"^https://([a-z0-9][a-z0-9-]{0,62}[a-z0-9])\.services\.ai\.azure\.com/api/projects/([A-Za-z0-9_][A-Za-z0-9_.-]{0,63})$")
NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
TIMEOUT_SECONDS = 120
SPEND_FILE = "limits.json"


class Problem(Exception):
    """Something the person running the tool can fix; printed without a trace. `code` is the exit code: 2 for a refusal to run, 1 for the rest."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class SpendCap(Problem):
    """The run would go beyond the spend cap that the repository writes (evaluation/limits.json). Nothing more is sent."""


# -- plain printing --------------------------------------------------------------------------------------------------------------------------------

def load_cases(folder: Path | None = None):
    """The modules of the app that hold the logic: (lockfile, drift_rules, plaintext). The folder is the tool's own when it holds lockfile.py (the Operator's volume is flat), else the app's."""
    for candidate in [folder, HERE, CASES]:
        if candidate is not None and (candidate / "lockfile.py").is_file() and (candidate / "drift_rules.py").is_file():
            break
    else:
        raise Problem("lockfile.py and drift_rules.py are neither next to the tool nor in the repository", 2)
    name = "cases_flat"
    package = sys.modules.get(name)
    if package is None or list(getattr(package, "__path__", [])) != [str(candidate)]:
        package = types.ModuleType(name)
        package.__path__ = [str(candidate)]  # type: ignore[attr-defined]
        for loaded in [key for key in sys.modules if key.startswith(name + ".")]:
            del sys.modules[loaded]
        sys.modules[name] = package
    return importlib.import_module(f"{name}.lockfile"), importlib.import_module(f"{name}.drift_rules"), importlib.import_module(f"{name}.plaintext")


def say(text: object, out=None, limit: int = 220) -> None:
    """One line of plain characters. A text that begins with two colons is not a command of the runner: a line never does."""
    flat = " ".join(re.sub(r"[^A-Za-z0-9 ,.:;()/+=_#%-]", " ", str(text)).split())
    flat = re.sub(r"(https?|ftp)://\S+", "(link removed)", flat)
    flat = flat.replace("::", ": :")
    print(flat if len(flat) <= limit else flat[: limit - 3] + "...", file=out or sys.stdout, flush=True)


def require_actions(refuse_outside: bool = True) -> None:
    """A tool that calls a model or writes to the project starts only in a run of GitHub Actions (AGENTS.md rule 18)."""
    if refuse_outside and os.environ.get("GITHUB_ACTIONS") != "true":
        raise Problem("this tool starts only in a run of GitHub Actions (AGENTS.md rule 18)", 2)


def check_endpoint(endpoint: str) -> tuple[str, str]:
    """(account, project) of a project endpoint, or a refusal. A token goes to nothing else."""
    found = ENDPOINT.fullmatch(endpoint or "")
    if not found:
        raise Problem("--endpoint is not https://<account>.services.ai.azure.com/api/projects/<project>", 2)
    return found.group(1), found.group(2)


# -- the token and the client ----------------------------------------------------------------------------------------------------------------------

def run_az(args: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([os.environ.get("AZ", "az"), *args], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def default_transport(method: str, url: str, headers: dict, data: bytes | None, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with OPENER.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
        return 0, type(error).__name__.encode("ascii", "replace")


class Client:
    """The calls of a tool to one Foundry project (or to Graph): bearer token from the Azure CLI, https only, one host, no redirect, and a count of the calls made. A test gives a `transport`."""

    def __init__(self, base: str, resource: str, *, runner=run_az, transport=default_transport, sleep: Callable[[float], None] = time.sleep, retries: int = 2) -> None:
        parts = urlsplit(base)
        if parts.scheme != "https" or not parts.netloc:
            raise Problem("a client goes to an https address", 2)
        self.base, self.host, self.resource, self.runner, self.transport, self.sleep, self.retries = base.rstrip("/"), parts.netloc, resource, runner, transport, sleep, retries
        self.calls: list[tuple[str, str, int]] = []
        self._token = ""

    def token(self) -> str:
        if not self._token:
            code, out, _ = self.runner(["account", "get-access-token", "--resource", self.resource, "--query", "accessToken", "--output", "tsv", "--only-show-errors"])
            if code != 0 or not out.strip():
                raise Problem(f"no token could be had for {self.resource}: the Operator's sign-in did not give one", 1)
            self._token = out.strip()
        return self._token

    def request(self, method: str, path: str, body: object = None, *, headers: dict | None = None, timeout: float = TIMEOUT_SECONDS) -> tuple[int, object]:
        """(status, the JSON of the answer or None). 0 when the call could not be made. A status of 429 or 5xx is tried again, twice, after a pause."""
        url = path if path.startswith("https://") else f"{self.base}{path}"
        if urlsplit(url).netloc != self.host:
            raise Problem("a call goes to the host of its own client and to no other", 2)
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        merged = {"Authorization": f"Bearer {self.token()}", "Accept": "application/json", **({"Content-Type": "application/json"} if data is not None else {}), **(headers or {})}
        for attempt in range(self.retries + 1):
            status, raw = self.transport(method, url, merged, data, timeout)
            if status in (429, 500, 502, 503, 504) and attempt < self.retries:
                self.sleep(5 * (attempt + 1))
                continue
            break
        self.calls.append((method, urlsplit(url).path[:60], status))
        try:
            document = json.loads(raw.decode("utf-8")) if raw else None
        except (ValueError, RecursionError):
            document = None
        return status, document


def error_words(document: object) -> str:
    """The code of an error object of a service when it is a plain token, and nothing of its message."""
    error = document.get("error") if isinstance(document, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,40}", code) else ""


def poll(fetch: Callable[[], object], finished: Callable[[object], bool], seconds: float, interval: float = 10.0, *, sleep=time.sleep, clock=time.monotonic):
    """Reads until `finished` says so or the time is out. Returns (the last answer, whether it finished)."""
    deadline = clock() + seconds
    last = fetch()
    while not finished(last) and clock() < deadline:
        sleep(interval)
        last = fetch()
    return last, finished(last)


# -- the spend cap ---------------------------------------------------------------------------------------------------------------------------------

class Spend:
    """What a run may spend, written in evaluation/limits.json before anything was measured (AGENTS.md rule 14 (c)): the rows, the calls of a model through the AI Gateway, the tokens and the
    seconds. `take` refuses what would go beyond a cap (the seconds are counted from the moment that the cap was made, which is the start of the run), `left` says how many seconds remain for a
    wait, and the tool prints how many calls it made, so that the orchestrator can hold the number against the gateway's own telemetry."""

    KEYS = ("maxRows", "maxModelCalls", "maxTokens", "maxSeconds")

    def __init__(self, limits: dict, *, clock: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(limits, dict) or any(not isinstance(limits.get(key), int) or isinstance(limits.get(key), bool) or limits[key] < 0 for key in self.KEYS):
            raise Problem(f"{SPEND_FILE} does not give {', '.join(self.KEYS)} as whole numbers", 2)
        self.limits, self.rows, self.model_calls, self.tokens = limits, 0, 0, 0
        self.clock, self.began = clock, clock()

    def seconds(self) -> float:
        return max(0.0, self.clock() - self.began)

    def left(self) -> float:
        """The seconds that the cap leaves: a wait for a run of the service is cut to this."""
        return max(0.0, self.limits["maxSeconds"] - self.seconds())

    @classmethod
    def load(cls, folder: Path | None = None) -> "Spend":
        for candidate in [folder, HERE, EVALUATION]:
            if candidate is not None and (candidate / SPEND_FILE).is_file():
                try:
                    return cls(json.loads((candidate / SPEND_FILE).read_text(encoding="utf-8")))
                except ValueError:
                    raise Problem(f"{SPEND_FILE} is not JSON", 2) from None
        raise Problem(f"{SPEND_FILE} is neither next to the tool nor in evaluation/: the spend cap has to be written before a run", 2)

    def check(self, *, rows: int = 0, model_calls: int = 0, tokens: int = 0) -> None:
        """Refuses what would go beyond a cap, and counts nothing: a run that is only estimated is checked first and counted when it is accepted."""
        for what, add, cap in (("rows", rows, "maxRows"), ("model calls", model_calls, "maxModelCalls"), ("tokens", tokens, "maxTokens")):
            have = {"rows": self.rows, "model calls": self.model_calls, "tokens": self.tokens}[what]
            if have + add > self.limits[cap]:
                raise SpendCap(f"the spend cap holds: {have + add} {what} would be more than the {self.limits[cap]} that evaluation/{SPEND_FILE} allows ({cap})")
        if self.seconds() > self.limits["maxSeconds"]:
            raise SpendCap(f"the spend cap holds: {int(self.seconds())} seconds have passed, more than the {self.limits['maxSeconds']} that evaluation/{SPEND_FILE} allows (maxSeconds)")

    def take(self, *, rows: int = 0, model_calls: int = 0, tokens: int = 0) -> None:
        self.check(rows=rows, model_calls=model_calls, tokens=tokens)
        self.rows, self.model_calls, self.tokens = self.rows + rows, self.model_calls + model_calls, self.tokens + tokens

    def line(self) -> str:
        return (f"spend: {self.model_calls} calls of a model through the AI Gateway (cap {self.limits['maxModelCalls']}), {self.tokens} tokens (cap {self.limits['maxTokens']}), "
                f"{self.rows} rows (cap {self.limits['maxRows']}), {int(self.seconds())} seconds (cap {self.limits['maxSeconds']})")


def read_jsonl(path: Path, limit: int) -> list[dict]:
    rows: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise Problem(f"{path.name} line {number} is not JSON", 2) from None
        if not isinstance(row, dict):
            raise Problem(f"{path.name} line {number} is not an object", 2)
        rows.append(row)
    if len(rows) > limit:
        raise SpendCap(f"{path.name} has {len(rows)} rows and the cap is {limit} (maxRows)")
    return rows


def parse_answer(text: object) -> dict | None:
    """The first JSON object in a text that holds `findings` (a prose around it and a code fence do not matter), or None."""
    body = text if isinstance(text, str) else ""
    decoder, position = json.JSONDecoder(), body.find("{")
    for _ in range(50):
        if position < 0:
            return None
        try:
            value, end = decoder.raw_decode(body, position)
        except ValueError:
            position = body.find("{", position + 1)
            continue
        if isinstance(value, dict) and isinstance(value.get("findings"), list):
            return value
        position = body.find("{", end)
    return None


# -- the evaluation run in the project --------------------------------------------------------------------------------------------------------------

ROUTES = ("/openai/v1/evals", "/openai/evals?api-version=2025-11-15-preview")  # the SDK's base, and the route of the REST reference of the preview
FINAL = ("completed", "failed", "canceled")
ITEM_SCHEMA = {"type": "object", "properties": {"query": {"type": "array"}, "response": {"type": "array"}, "messages": {"type": "array"}, "tool_definitions": {"type": "array"}},
               "required": ["query", "response"]}
TEXT_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}, "response": {"type": "string"}}, "required": ["query", "response"]}
TEXT_MAPPING = {"query": "{{item.query}}", "response": "{{item.response}}"}
# These two evaluators take the whole interaction as `messages` instead of separate fields (Learn, Risk and Safety Evaluators, read 2026-11-08); the others take query, response and the tool definitions.
AGENT_SAFETY = frozenset({"builtin.prohibited_actions", "builtin.sensitive_data_leakage"})


def criteria(evaluators: list[str], judge_model: str | None, mapped: bool = True, mapping: dict | None = None) -> list[dict]:
    """The testing criteria of an evaluation: built-in evaluators, each with the mapping of its inputs to the fields of an item (the continuous rule gives none: the service maps a response itself),
    and a judge model only for an evaluator that needs one."""
    found = []
    for name in evaluators:
        item = {"type": "azure_ai_evaluator", "name": name.split(".")[-1], "evaluator_name": name}
        if mapped:
            item["data_mapping"] = dict(mapping) if mapping else ({"messages": "{{item.messages}}"} if name in AGENT_SAFETY else
                                                                {"query": "{{item.query}}", "response": "{{item.response}}", "tool_definitions": "{{item.tool_definitions}}"})
        if judge_model:
            item["initialization_parameters"] = {"model": judge_model}
        found.append(item)
    return found


def submit_evaluation(client, spend: "Spend", *, name: str, run_name: str, label: str, evaluators: list[str], model: str | None, items: list[dict], item_schema: dict, floor: float,
                      wait: float, mapping: dict | None = None, demanded: bool = False, sleep=time.sleep, clock=time.monotonic) -> tuple[str, str, str]:
    """One evaluation run in the project (the portal shows it under Build, Evaluations). Returns (label, state, plain words), the state being PASS, FAIL or UNKNOWN.

    UNKNOWN is for what could not be measured: the project did not offer the evaluation (a preview), or the run did not finish in the time that is left. It is never a pass and it fails nothing.
    A judge model is the connection of the lock to the AI Gateway (`model`), its calls are counted before they are made, and a judge that was `demanded` and is refused is a FAIL."""
    if model:
        spend.take(model_calls=len(items) * len(evaluators))
    body = {"name": f"{name}-{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M}", "data_source_config": {"type": "custom", "item_schema": item_schema, "include_sample_schema": False},
            "testing_criteria": criteria(evaluators, model, mapping=mapping)}
    base, created, query = "", None, ""
    status, document = 0, None
    for route in ROUTES:
        status, document = client.request("POST", route, body)
        if status in (200, 201) and isinstance(document, dict) and isinstance(document.get("id"), str):
            base, created, query = route.split("?")[0], document["id"], ("?" + route.split("?", 1)[1]) if "?" in route else ""
            break
    if created is None:
        return label, "FAIL" if demanded else "UNKNOWN", (f"{label}: the project did not accept the evaluation ({status} {error_words(document)})" + (" (the judge is refused: the code graders decide)" if model else ""))
    status, document = client.request("POST", f"{base}/{created}/runs{query}", {"name": run_name, "data_source": {"type": "jsonl", "source": {"type": "file_content", "content": [{"item": item} for item in items]}}})
    run_id = document.get("id") if isinstance(document, dict) else None
    if status not in (200, 201) or not isinstance(run_id, str):
        return label, "FAIL", f"{label}: the run was not accepted ({status} {error_words(document)})"
    seconds = min(wait, spend.left())
    last, done = poll(lambda: client.request("GET", f"{base}/{created}/runs/{run_id}{query}")[1], lambda doc: isinstance(doc, dict) and doc.get("status") in FINAL, seconds, 10.0, sleep=sleep, clock=clock)
    state = last.get("status") if isinstance(last, dict) else None
    if not done or state != "completed":
        ended = f"ended {state}" if done and state else f"is {state or 'not answered'} after {int(seconds)} seconds"
        return label, "UNKNOWN", (f"{label}: the run {ended} and could not be measured (a Foundry without public network access may need the evaluation networking: see the proposal); "
                                  "look at it in the portal, Build, Evaluations")
    counts = last.get("result_counts") if isinstance(last.get("result_counts"), dict) else {}
    passed, failed = int(counts.get("passed") or 0), int(counts.get("failed") or 0)
    total = passed + failed
    if not total:
        return label, "UNKNOWN", f"{label}: the run completed with no result to count: look at it in the portal, Build, Evaluations"
    rate = passed / total
    return label, "PASS" if rate >= floor else "FAIL", f"{label}: {passed} of {total} results passed ({rate:.2f}, at least {floor:.2f}); the run is in the portal under Build, Evaluations"
