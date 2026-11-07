#!/usr/bin/env python3
"""Checks the AI Gateway from inside the network: one small chat completion for each alias, and the two refusals that must happen (standard library only).

    python tools/aigateway-check.py run --host <host name of the gateway> --alias <alias> [--alias <alias> ...] [--max-completion-tokens 256] [--summary FILE]

The Hub workflow runs it in a container group of the Operator (operator/run-tool.sh, tools/operator-run.py), which is signed in with the Operator's own identity: the Azure CLI
gives the token. The Operator holds AI Gateway Models User on the gateway (environment/aigateway/main.bicep) and no key exists. The tool refuses to run without the gateway's
host name, and only a GitHub Actions run may start it: a call to a model bills, a very little (AGENTS.md rule 18).

What it sends, to https://<host>/default/models/openai/v1/chat/completions, the route of the gateway's OpenAI-compatible models:

  alias <name>    for each --alias: one tiny chat completion with `Authorization: Bearer <a Microsoft Entra token for https://azure-api.net/aigateway>`. The request's `model`
                  is the alias. It passes when the gateway answers 200 with token usage. It prints the status, the model name that the service reports, and the usage numbers.
  no token        the same request without any token. It passes when the gateway answers 401.
  wrong alias     a request with the token and an alias that does not exist. It passes when the gateway answers with a status of 400 to 499.

It prints nothing else of any answer: no header, no body, no text that a model wrote. An error body is never printed, so a status says what a refusal was, and a short fixed hint says
what usually causes the statuses that are not the expected ones. A token is never printed, and a request goes only to a host under .ai.gateway.azure.com, over https, so that the
token cannot be sent anywhere else. A redirect is an answer like any other and is not followed. The cap of the completion is max_completion_tokens (256 by default), not max_tokens:
these models reason before they answer, and a cap that is too small is refused with a 400, which environment-smoke.py found out for the gateway of the first environment.

The exit code is 0 when every check passed, 1 when one failed or the tool could not get a token, 2 when the tool refused to run.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

# The runtime of the AI Gateway (Learn, "Migrate from the AI Gateway tier in API Management": the new resource type gets the domain ai.gateway.azure.com). A token goes to nothing else.
HOST_SUFFIX = ".ai.gateway.azure.com"
HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
CHAT_PATH = "/default/models/openai/v1/chat/completions"
# The audience of the gateway's runtime tokens. An application or a managed identity asks for it with the scope https://azure-api.net/aigateway/.default; the Azure CLI, which
# the Operator signs in with, asks for the resource.
AUDIENCE = "https://azure-api.net/aigateway"
ALIAS = re.compile(r"^[A-Za-z0-9_](?:[A-Za-z0-9_.-]{0,253}[A-Za-z0-9_])?$")
WRONG_ALIAS = "meternaut-no-such-alias"
PROMPT = "Reply with the word ok."
DEFAULT_COMPLETION_TOKENS = 256
MAX_COMPLETION_TOKENS = 1024
TIMEOUT_SECONDS = 120
# The application id of Microsoft's own "Azure AI Gateway Dataplane" service principal, which a tenant needs for a token for the audience above (named in the proposal).
SERVICE_PRINCIPAL = "18550318-e177-4205-a743-6816d6fcdc3f"
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
# What the service calls the model in an answer: a short plain name. Anything else is not printed.
MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+ -]{0,79}$")

HINTS = {
    401: ("the token was not accepted: the tenant may have no service principal for the gateway's audience (a person creates it once, and "
          "docs/proposals/08-ai-gateway.md says how), or the token is for another audience"),
    403: ("the Operator may hold no AI Gateway Models User role on the gateway yet (a new role takes up to ten minutes to apply, and the action aigateway gives it), "
          "or the role is on another scope"),
    404: "the gateway knows no alias of this name, or the route is wrong",
    429: "the gateway's own limit, or the model deployment's rate limit, answered: wait a minute and run the check again",
    0: ("the gateway could not be reached from the Operator's subnet: the landing zone's firewall may not allow the gateway's host name, or the name does not resolve "
        "(the gateway's frontend is public, and nothing in the network blocks it by itself)"),
}


class Problem(Exception):
    """Something the person running the tool can fix; printed without a trace. `code` is the exit code: 2 for a refusal to run, 1 for the rest."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an answer like any other. The request is not repeated at the address it names, because that would carry the bearer token along."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def run_az(args: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([os.environ.get("AZ", "az"), *args], capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def post_http(url: str, headers: dict, body: bytes) -> tuple[int, bytes]:
    """The status and the body of one POST. 0 and the name of the error when the request could not be made at all."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        return 0, type(e).__name__.encode("ascii", "replace")


class Gateway:
    """The two things that touch the outside: the Azure CLI, which gives the token, and the network. A test replaces both."""

    def __init__(self, runner=run_az, post=post_http):
        self.runner, self.post = runner, post

    def token(self) -> str:
        code, out, err = self.runner(["account", "get-access-token", "--resource", AUDIENCE, "--query", "accessToken", "--output", "tsv", "--only-show-errors"])
        token = out.strip()
        if code != 0 or not token:
            raise Problem(f"no token for {AUDIENCE}: {why_no_token(err)}")
        return token


def why_no_token(error: str) -> str:
    """One short line about a failed sign-in, without ids and without anything that looks like a token."""
    text = (error or "").strip()
    if "AADSTS500011" in text:
        return (f"the tenant has no service principal for the gateway's audience (the application {SERVICE_PRINCIPAL}, named Azure AI Gateway Dataplane). "
                "A person with the right to add one creates it once, with their own sign-in, on the owner's written word: docs/proposals/08-ai-gateway.md")
    first = re.sub(r"\s+", " ", text.splitlines()[0]).strip() if text else "no message"
    first = GUID.sub("<id>", first)
    first = re.sub(r"[A-Za-z0-9_.~+/=-]{40,}", "<hidden>", first)
    return first[:140]


def check_host(host: str) -> str:
    name = (host or "").strip().lower()
    if not name:
        raise Problem("--host is the host name of the gateway, which the service reports (properties.frontend.defaultHostname): there is none", 2)
    if not HOST.match(name) or not name.endswith(HOST_SUFFIX) or len(name) <= len(HOST_SUFFIX):
        raise Problem(f"--host is a host name under {HOST_SUFFIX}, without a scheme, a port or a path: the token is sent to nothing else", 2)
    return name


def check_aliases(aliases: list[str] | None) -> list[str]:
    if not aliases:
        raise Problem("--alias is the name of an alias of the gateway, and at least one is needed", 2)
    found: list[str] = []
    for alias in aliases:
        if not ALIAS.match(alias or "") or alias == WRONG_ALIAS or alias in found:
            raise Problem("--alias is the name of an alias (letters, digits, underscore, hyphen and period), each given once", 2)
        found.append(alias)
    return found


def only_in_actions() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise Problem("this command calls models, which bill, and only a GitHub Actions run may start it (AGENTS.md rule 18)", 2)


def request_body(model: str, completion_tokens: int) -> bytes:
    return json.dumps({"model": model, "messages": [{"role": "user", "content": PROMPT}], "max_completion_tokens": completion_tokens}, separators=(",", ":")).encode("utf-8")


def usage_of(answer: bytes) -> tuple[str, dict | None]:
    """The model name that the service reports and the three usage numbers, from the answer to a completion. Nothing else of the answer is read."""
    try:
        document = json.loads(answer.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return "", None
    if not isinstance(document, dict):
        return "", None
    model = document.get("model")
    name = model if isinstance(model, str) and MODEL_NAME.match(model) else ""
    usage = document.get("usage")
    numbers = {key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")} if isinstance(usage, dict) else {}
    if not numbers or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in numbers.values()) or not numbers["total_tokens"]:
        return name, None
    return name, numbers


def result(label: str, status: int, expected: str, ok: bool, extra: str = "", hint: str = "") -> tuple[bool, str, str]:
    shown = f"status {status}" if status else "no answer"
    return ok, f"{'ok' if ok else 'FAILED'}: {label}: {shown} (expected {expected}){extra}", ("" if ok else hint)


def check_alias(gateway: Gateway, host: str, token: str, alias: str, completion_tokens: int) -> tuple[bool, str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {token}"}
    status, answer = gateway.post(f"https://{host}{CHAT_PATH}", headers, request_body(alias, completion_tokens))
    label = f"alias {alias}"
    if status != 200:
        return result(label, status, "200", False, hint=HINTS.get(status, ""))
    model, numbers = usage_of(answer)
    if numbers is None:
        return result(label, status, "200 with usage", False, ", and the answer carries no usage numbers (the limits of the gateway count tokens)")
    reported = f"model {model}" if model else "no model name that is a plain name"
    return result(label, status, "200", True, f", {reported}, usage prompt {numbers['prompt_tokens']}, completion {numbers['completion_tokens']}, total {numbers['total_tokens']}")


def check_no_token(gateway: Gateway, host: str, alias: str, completion_tokens: int) -> tuple[bool, str, str]:
    status, _ = gateway.post(f"https://{host}{CHAT_PATH}", {"Content-Type": "application/json", "Accept": "application/json"}, request_body(alias, completion_tokens))
    return result("no token", status, "401", status == 401, hint="a request with no token must be refused: the gateway took it, so Microsoft Entra is not the only way in")


def check_wrong_alias(gateway: Gateway, host: str, token: str, completion_tokens: int) -> tuple[bool, str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {token}"}
    status, _ = gateway.post(f"https://{host}{CHAT_PATH}", headers, request_body(WRONG_ALIAS, completion_tokens))
    return result("wrong alias", status, "a status of 400 to 499", 400 <= status < 500, hint=HINTS.get(status, ""))


def command_run(args, gateway: Gateway) -> int:
    only_in_actions()
    host = check_host(args.host)
    aliases = check_aliases(args.alias)
    if not 1 <= args.max_completion_tokens <= MAX_COMPLETION_TOKENS:
        raise Problem(f"--max-completion-tokens is a number from 1 to {MAX_COMPLETION_TOKENS}", 2)
    token = gateway.token()
    checks = [check_alias(gateway, host, token, alias, args.max_completion_tokens) for alias in aliases]
    checks.append(check_no_token(gateway, host, aliases[0], args.max_completion_tokens))
    checks.append(check_wrong_alias(gateway, host, token, args.max_completion_tokens))
    lines = []
    for ok, text, hint in checks:
        lines.append(text)
        if hint:
            lines.append(f"  hint: {hint}")
    print("\n".join(lines))
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as summary:
            summary.write(f"### The AI Gateway, called from inside the network\n\nHost: `{host}`\n\n```\n" + "\n".join(lines) + "\n```\n")
    failed = [text for ok, text, _ in checks if not ok]
    if failed:
        print(f"{len(failed)} of {len(checks)} checks failed.", file=sys.stderr)
        return 1
    print(f"All {len(checks)} checks passed.")
    return 0


def main(argv=None, gateway: Gateway | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="call each alias once, and send the two requests that the gateway must refuse")
    run.add_argument("--host", required=True, help="the host name of the gateway, as the service reports it")
    run.add_argument("--alias", action="append", help="an alias to call; give it once for each alias")
    run.add_argument("--max-completion-tokens", type=int, default=DEFAULT_COMPLETION_TOKENS)
    run.add_argument("--summary", help="a file to append the lines to as Markdown (the step summary of a workflow run)")
    args = parser.parse_args(argv)
    try:
        return command_run(args, gateway or Gateway())
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
