#!/usr/bin/env python3
"""Checks that the gateway answers the way the first contract says (standard library only).

    GATEWAY_SMOKE_KEY=<the contract's key> python tools/environment-smoke.py --url https://<instance>.azure-api.net/models/chat/completions [--limits]

It sends a few small requests to the gateway's chat route and prints one line for each:

    valid        the contract's key and model get a completion (200) that carries token usage. A new private endpoint, its
                 DNS record and the gateway's role on the model account take a while to settle, a new key is not known to
                 every part of the gateway at once (a 401 for a short while), and a key that went over its allowance in an
                 earlier run is refused by the gateway itself (429) until the minute is over; all of that is retried until
                 --wait seconds have passed. An error that cannot settle (the contract refusing a model, the model's own 429)
                 is not.
    no key       401
    wrong key    401
    other model  403, from the contract (the model is never called)
    no model     400 or 403, from the gateway (the model is never called)
    limit        only with --limits: one request whose reported usage is more than the contract allows per minute, then a
                 small one that the gateway itself must refuse with 429 ({"statusCode":429,...}; a 429 from the model is
                 not a pass; a failure that may settle is retried until --wait seconds have passed). It costs about one
                 minute's allowance of tokens and blocks the key for up to a minute (a run after it waits that out), so it
                 is opt-in and runs last.

The key comes from the environment, never from an argument, and is never printed. A request goes only to an
https address under .azure-api.net, and a redirect is an error, so the key cannot travel anywhere else.
The exit code is 0 when every check passed, 1 when one failed, 2 when the tool could not run.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST_SUFFIX = ".azure-api.net"
KEY = re.compile(r"[A-Za-z0-9_-]{16,128}")
TRANSIENT = (0, 500, 502, 503, 504)
NOT_ALLOWED = "unauthorized_model_access"


class Problem(Exception):
    """Something the person running the tool can fix; printed without a trace."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    """The only place that talks to the network, so that tests can replace it."""

    def __init__(self, url: str, timeout: float = 120.0):
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme != "https" or not host.endswith(HOST_SUFFIX) or len(host) <= len(HOST_SUFFIX) or parts.username or parts.password:
            raise Problem(f"--url is an https address of an API Management gateway (https://<name>{HOST_SUFFIX}/...)")
        if parts.port not in (None, 443) or parts.query or parts.fragment or not parts.path.endswith("/chat/completions"):
            raise Problem("--url is the chat completions route, without a port, query or fragment")
        self.url, self.timeout = url, timeout
        self._opener = urllib.request.build_opener(_NoRedirect)

    def post(self, body: dict, key: str | None) -> tuple[int, bytes]:
        headers = {"Content-Type": "application/json"}
        if key:
            headers["api-key"] = key
        request = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            return 0, str(e).encode("utf-8", "replace")


def chat(model: str | None, text: str = "Reply with the single word: ok", max_tokens: int = 256) -> dict:
    # The model reasons before it answers: a cap of one token cannot hold even that, and the service refuses it with a 400.
    body: dict = {"messages": [{"role": "user", "content": text}], "max_completion_tokens": max_tokens}
    if model:
        body["model"] = model
    return body


def snippet(data: bytes, key: str) -> str:
    text = data.decode("utf-8", "replace").replace(key, "***")
    return re.sub(r"\s+", " ", text).strip()[:200]


def settles(status: int, data: bytes) -> bool:
    """Whether a failed answer may still turn into a good one: the network, the gateway or the role is not ready yet.
    A new key can be refused for a while before every part of the gateway knows it, and a key that went over its allowance
    (in an earlier run of --limits) is refused by the gateway itself until the minute is over. The model's own refusals do
    not settle: its 429, and a model that the contract does not list."""
    text = data.decode("utf-8", "replace").lower()
    if status in TRANSIENT:
        return True
    if status == 429:
        return from_gateway(data)
    if status == 403 and NOT_ALLOWED in text:
        return False
    if status == 404:
        return "resource not found" in text  # the gateway has not picked up the new API yet; the model's own 404 names a deployment
    return status in (401, 403)


def usage_of(data: bytes) -> int | None:
    """The total tokens the model reported for a completion, if it reported any."""
    try:
        total = (json.loads(data).get("usage") or {}).get("total_tokens")
    except (ValueError, AttributeError):
        return None
    return total if isinstance(total, int) and not isinstance(total, bool) and total > 0 else None


def from_gateway(data: bytes) -> bool:
    """The gateway's own refusal, {"statusCode":429,"message":...}, and not the model's, {"error":{...}}."""
    try:
        body = json.loads(data)
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("statusCode") == 429 and "error" not in body


def check_valid(client, key, model, wait, sleep, now):
    deadline = now() + wait
    attempt = 0
    while True:
        attempt += 1
        status, data = client.post(chat(model), key)
        if status == 200:
            try:
                has_choice = isinstance(json.loads(data).get("choices"), list) and bool(json.loads(data)["choices"])
            except (ValueError, AttributeError):
                has_choice = False
            if not has_choice:
                return False, "200, but the answer is not a completion"
            tokens = usage_of(data)
            if tokens is None:
                return False, "200, but the reply carries no token usage: the contract's limits and the metrics would have nothing to count"
            return True, f"200 after {attempt} attempt(s), {tokens} tokens"
        if not settles(status, data) or now() >= deadline:
            return False, f"{status or 'no answer'}: {snippet(data, key)}" + (f" (gave up after {attempt} attempts)" if attempt > 1 else "")
        print(f"  waiting ({status or 'no answer'}): the endpoint, its DNS record or the gateway's role may still be settling", flush=True)
        sleep(30)


def expect(wanted: tuple[int, ...], client, body: dict, sent_key: str | None, real_key: str, needle: str = ""):
    status, data = client.post(body, sent_key)
    ok = status in wanted and needle in data.decode("utf-8", "replace")
    return ok, f"{status or 'no answer'}" + ("" if ok else f" (wanted {' or '.join(map(str, wanted))}): {snippet(data, real_key)}")


def check_limit(client, key, model, tokens_per_minute, wait, sleep, now):
    words = int(tokens_per_minute * 1.2)
    status, data = client.post(chat(model, "word " * words + "\nReply with the single word: ok"), key)
    if status == 429:
        if from_gateway(data):
            return True, "429 from the gateway already for the large request"
        return False, f"429, but not the gateway's own refusal (the model may be throttling): {snippet(data, key)}"
    if status != 200:
        return False, f"the large request was not accepted ({status or 'no answer'}): {snippet(data, key)}"
    used = usage_of(data)
    if used is None or used < tokens_per_minute:
        return False, (f"the large request used {used or 'an unknown number of'} tokens, fewer than the {tokens_per_minute} a minute "
                       "that the contract allows, so the check proves nothing: the prompt has to be larger")
    # The limit counts the large request after its answer: a small request may still be let through for a moment (a few
    # tries), and a failure that may settle (the network, the gateway) is tried again until the wait is over.
    deadline, accepted, attempt = now() + wait, 0, 0
    while True:
        attempt += 1
        status, data = client.post(chat(model), key)
        if status == 429:
            if from_gateway(data):
                return True, f"the large request used {used} tokens (200), the next one was refused by the gateway with 429 (attempt {attempt})"
            return False, f"429, but not the gateway's own refusal (the model may be throttling): {snippet(data, key)}"
        accepted += status == 200
        if accepted >= 5 or not (status == 200 or settles(status, data)) or now() >= deadline:
            return False, f"the large request used {used} tokens, but the next ones were {status or 'no answer'}, not 429: {snippet(data, key)}"
        sleep(5 if status == 200 else 30)


def run_checks(client, key, contract: dict, limits: bool, wait: float, sleep=time.sleep, now=time.monotonic) -> list[tuple[str, bool, str]]:
    model = contract["allowedModels"][0]
    results = [("valid", *check_valid(client, key, model, wait, sleep, now))]
    if not results[0][1]:
        return results  # the rest says nothing while the route does not work
    wrong = "x" * 32
    results += [
        ("no key", *expect((401,), client, chat(model), None, key)),
        ("wrong key", *expect((401,), client, chat(model), wrong, key)),
        ("other model", *expect((403,), client, chat("not-a-model-of-this-contract"), key, key, NOT_ALLOWED)),
        ("no model", *expect((400, 403), client, chat(None), key, key)),
    ]
    if limits:
        results.append(("limit", *check_limit(client, key, model, int(contract["tokensPerMinute"]), wait, sleep, now)))
    return results


def main(argv=None, client=None, environ=None, sleep=time.sleep, now=time.monotonic) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="the gateway's chat completions route")
    parser.add_argument("--contract", default=str(ROOT / "environment" / "contract.json"))
    parser.add_argument("--limits", action="store_true", help="also check that the token rate is enforced (costs about a minute's allowance)")
    parser.add_argument("--wait", type=float, default=900.0, help="seconds to keep retrying the first request while the route settles")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    try:
        key = environ.get("GATEWAY_SMOKE_KEY", "")
        if not KEY.fullmatch(key):
            raise Problem("GATEWAY_SMOKE_KEY is the contract's key (letters and digits, 16 to 128 characters)")
        try:
            contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
            if not contract["allowedModels"] or int(contract["tokensPerMinute"]) <= 0:
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError):
            raise Problem(f"{args.contract} needs allowedModels and a tokensPerMinute")
        client = client or Client(args.url)
        results = run_checks(client, key, contract, args.limits, args.wait, sleep, now)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for name, ok, detail in results:
        print(f"{'ok  ' if ok else 'FAIL'} {name:<12} {detail}")
    failed = [name for name, ok, _ in results if not ok]
    print(("All " + str(len(results)) + " checks passed.") if not failed else "Failed: " + ", ".join(failed) + ".")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
