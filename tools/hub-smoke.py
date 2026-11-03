#!/usr/bin/env python3
"""Checks that the hub answers the way its contract says (standard library only).

    HUB_SMOKE_KEY=<the contract's key> python tools/hub-smoke.py --url https://<instance>.azure-api.net/meternaut/llm/v1/chat/completions [--limits]

It sends a few small requests to the hub's chat route and prints one line for each:

    valid        the contract's key and model get a completion (200). A new private endpoint, its DNS record and the
                 gateway's role on the model account take a while to settle, so a gateway or access error is retried
                 until --wait seconds have passed; an error that cannot settle (the contract refusing, a wrong key) is not.
    no key       401
    wrong key    401
    other model  403, from the contract (the model is never called)
    no model     403, from the contract
    limit        only with --limits: one request that uses more tokens than the contract allows per minute, then a
                 small one that must be refused with 429. It costs about one minute's allowance of tokens and
                 blocks the key for up to a minute, so it is opt-in and runs last.

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
KEY = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
TRANSIENT = (0, 500, 502, 503, 504)


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


def chat(model: str | None, text: str = "Reply with the single word: ok", max_tokens: int = 64) -> dict:
    body: dict = {"messages": [{"role": "user", "content": text}], "max_completion_tokens": max_tokens}
    if model:
        body["model"] = model
    return body


def snippet(data: bytes, key: str) -> str:
    text = data.decode("utf-8", "replace").replace(key, "***")
    return re.sub(r"\s+", " ", text).strip()[:200]


def settles(status: int, data: bytes) -> bool:
    """Whether a failed answer may still turn into a good one: the network, the gateway or the role is not ready yet."""
    text = data.decode("utf-8", "replace").lower()
    if status in TRANSIENT:
        return True
    if status == 403 and "model_not_allowed" in text:
        return False
    if status == 401 and "subscription key" in text:
        return False
    if status == 404:
        return "resource not found" in text  # the gateway has not picked up the new API yet; the model's own 404 names a deployment
    return status in (401, 403)


def check_valid(client, key, model, wait, sleep, now):
    deadline = now() + wait
    attempt = 0
    while True:
        attempt += 1
        status, data = client.post(chat(model), key)
        if status == 200:
            try:
                reply = json.loads(data)
                tokens = (reply.get("usage") or {}).get("total_tokens")
                if isinstance(reply.get("choices"), list) and reply["choices"]:
                    return True, f"200 after {attempt} attempt(s), {tokens} tokens"
            except ValueError:
                pass
            return False, "200, but the answer is not a completion"
        if not settles(status, data) or now() >= deadline:
            return False, f"{status or 'no answer'}: {snippet(data, key)}" + (f" (gave up after {attempt} attempts)" if attempt > 1 else "")
        print(f"  waiting ({status or 'no answer'}): the endpoint, its DNS record or the gateway's role may still be settling", flush=True)
        sleep(30)


def expect(wanted: int, client, body: dict, sent_key: str | None, real_key: str, needle: str = ""):
    status, data = client.post(body, sent_key)
    ok = status == wanted and needle in data.decode("utf-8", "replace")
    return ok, f"{status or 'no answer'}" + ("" if ok else f" (wanted {wanted}): {snippet(data, real_key)}")


def check_limit(client, key, model, tokens_per_minute, sleep):
    words = int(tokens_per_minute * 1.2)
    status, data = client.post(chat(model, "word " * words, max_tokens=1), key)
    if status == 429:
        return True, "429 already for the large request"
    if status != 200:
        return False, f"the large request was not accepted ({status or 'no answer'}): {snippet(data, key)}"
    for attempt in range(1, 4):
        status, data = client.post(chat(model), key)
        if status == 429:
            return True, f"large request 200, the next one 429 (attempt {attempt})"
        sleep(2)
    return False, f"large request 200, but the next ones were {status or 'no answer'}, not 429: {snippet(data, key)}"


def run_checks(client, key, contract: dict, limits: bool, wait: float, sleep=time.sleep, now=time.monotonic) -> list[tuple[str, bool, str]]:
    model = contract["models"][0]
    results = [("valid", *check_valid(client, key, model, wait, sleep, now))]
    if not results[0][1]:
        return results  # the rest says nothing while the route does not work
    wrong = "x" * 32
    results += [
        ("no key", *expect(401, client, chat(model), None, key)),
        ("wrong key", *expect(401, client, chat(model), wrong, key)),
        ("other model", *expect(403, client, chat("not-a-model-of-this-contract"), key, key, "model_not_allowed")),
        ("no model", *expect(403, client, chat(None), key, key, "model_not_allowed")),
    ]
    if limits:
        results.append(("limit", *check_limit(client, key, model, int(contract["tokensPerMinute"]), sleep)))
    return results


def main(argv=None, client=None, environ=None, sleep=time.sleep, now=time.monotonic) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="the hub's chat completions route")
    parser.add_argument("--contract", default=str(ROOT / "hub" / "contract.json"))
    parser.add_argument("--limits", action="store_true", help="also check that the token rate is enforced (costs about a minute's allowance)")
    parser.add_argument("--wait", type=float, default=900.0, help="seconds to keep retrying the first request while the route settles")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    try:
        key = environ.get("HUB_SMOKE_KEY", "")
        if not KEY.match(key):
            raise Problem("HUB_SMOKE_KEY is the contract's key (letters and digits, 16 to 128 characters)")
        try:
            contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
            if not contract["models"] or int(contract["tokensPerMinute"]) <= 0:
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError):
            raise Problem(f"{args.contract} needs a model and a tokensPerMinute")
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
