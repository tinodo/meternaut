#!/usr/bin/env python3
"""Reads the front door of the console, with no sign-in, and says whether it is shut.

    python tools/console-check.py door --host <name>.azurewebsites.net [--expect signin|refuse] [--summary FILE]

The console serves a person only after Microsoft Entra has signed them in, and the app refuses every request when that sign-in is not set up. This check
makes the requests that an anonymous visitor (or a script) would make and passes only when none of them gets a page:

  - /healthz answers 200 with the word ok, because a probe has no sign-in;
  - /, /history, /me/decisions, /ok/<id>, /why/<id> and /ops/pause answer a redirect to the sign-in (--expect signin) or the app's own refusal 503
    (--expect refuse), and never 200;
  - the same request with a made-up sign-in header (x-ms-client-principal-id) is not served either: the platform's sign-in has to overwrite it, or the app
    has to refuse it.

Standard library only. It reads; it sends no credential and changes nothing.
"""
from __future__ import annotations

import argparse
import re
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from typing import Callable

PAGES = ("/", "/history", "/me/decisions", "/me/settings", "/me/notes", "/ops/pause", "/ops/permissions", "/ok/0123456789abcdef", "/why/k0123456789abc")
HOST = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,200}[a-z0-9])?$")
SIGN_IN = re.compile(r"^(https://login\.microsoftonline\.com/|/\.auth/login/aad)", re.I)


class Problem(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


Fetch = Callable[[str, dict], "tuple[int, dict, bytes]"]
TRIES = 3  # the app runs on a plan that scales to zero: the first answer after a quiet time can take a minute
TIMEOUT = 60


def fetch(url: str, headers: dict) -> tuple[int, dict, bytes]:
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(url, headers={"User-Agent": "meternaut-console-check", **headers}, method="GET")
    for attempt in range(1, TRIES + 1):
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read(4096)
        except urllib.error.HTTPError as error:
            return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read(4096)
        except (TimeoutError, urllib.error.URLError, OSError) as error:
            if attempt == TRIES:
                raise Problem(f"no answer from {url.split('?')[0]} after {TRIES} tries of {TIMEOUT} seconds ({type(error).__name__})") from error


def verdict(path: str, status: int, headers: dict, expect: str) -> tuple[bool, str]:
    where = headers.get("location", "")
    if expect == "signin":
        ok = status in (301, 302, 303, 307, 308) and bool(SIGN_IN.match(where))
        return ok, f"{status} to {where.split('?')[0][:70]}" if where else str(status)
    return status == 503, str(status)


def door(host: str, expect: str, get: Fetch = fetch) -> tuple[bool, list[tuple[str, str, bool, str]]]:
    if not HOST.match(host):
        raise Problem("--host is a host name")
    if expect not in ("signin", "refuse"):
        raise Problem("--expect is signin or refuse")
    rows: list[tuple[str, str, bool, str]] = []
    status, _, body = get(f"https://{host}/healthz", {})
    rows.append(("/healthz", "no sign-in", status == 200 and body.strip() == b"ok", f"{status} {body.strip()[:10].decode('ascii', 'replace')}"))
    for path in PAGES:
        status, headers, _ = get(f"https://{host}{path}", {})
        ok, text = verdict(path, status, headers, expect)
        rows.append((path, "no sign-in", ok, text))
    forged = {"x-ms-client-principal-id": str(uuid.uuid4()), "x-ms-client-principal-name": "someone@example.com"}
    for path in ("/", "/ok/0123456789abcdef"):
        status, headers, _ = get(f"https://{host}{path}", forged)
        ok, text = verdict(path, status, headers, expect)
        rows.append((path, "made-up sign-in header", ok, text))
    return all(row[2] for row in rows), rows


def main(argv=None, get: Fetch = fetch, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["door"])
    parser.add_argument("--host", required=True)
    parser.add_argument("--expect", default="signin")
    parser.add_argument("--summary")
    args = parser.parse_args(argv)
    try:
        passed, rows = door(args.host.strip().lower(), args.expect, get)
    except Problem as error:
        print(f"console-check: {error}", file=sys.stderr)
        return 2
    lines = [f"{'PASS' if ok else 'FAIL'}  {path:22} {how:24} {text}" for path, how, ok, text in rows]
    print("\n".join(lines), file=out)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write("### The console's front door\n\n```\n" + "\n".join(lines) + "\n```\n\n"
                         + ("Nobody gets a page without a sign-in.\n" if passed else "**A request got something that it should not.**\n"))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
