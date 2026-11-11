#!/usr/bin/env python3
"""Reads the front door of the console, with no sign-in, and says whether it is shut; waits for the app's health address from inside the network; and measures how fast it answers.

    python tools/console-check.py door --host <name> [--expect signin|refuse] [--proxied] [--private] [--summary FILE]
    python tools/console-check.py health --host <name>.azurewebsites.net [--tries 60] [--interval 10] [--timeout 15] [--private]
    python tools/console-check.py latency --host <name>.azurewebsites.net --private --minutes N --interval S [--idle-minutes M] [--after-idle K] [--timeout 75]

door    The console serves a person only after Microsoft Entra has signed them in, and the app refuses every request when that sign-in is not set up. This
        check makes the requests that an anonymous visitor (or a script) would make and passes only when none of them gets a page:

  - /healthz answers 200 with the word ok, because a probe has no sign-in;
  - /, /history, /me/decisions, /ok/<id>, /why/<id>, /ops/pause and /arm/return (the return address of the Azure Resource Manager sign-in that an approval
    starts), the last one with and without the query ?code=x&state=y that Microsoft Entra adds, answer a redirect to the sign-in (--expect signin) or the
    app's own refusal 503 (--expect refuse), and never 200;
  - the same request with a made-up sign-in header (x-ms-client-principal-id) is not served either: the platform's sign-in has to overwrite it, or the app
    has to refuse it. That is asked of /, of /ok/<id> and of /arm/return with a code and a state, the page that takes a value from the address.

        --host is the name that people open: the console's host name behind the platform's Application Gateway when there is one (the Hub workflow reads it
        from the secret CONSOLE_HOST_NAME of the environment hub), the app's own name otherwise. With --proxied it is the name of a reverse proxy, and a redirect to the
        sign-in has to carry that name too: the return address that the platform's sign-in builds (redirect_uri, or post_login_redirect_uri when the redirect is
        the sign-in's own) must name --host and not the app's own name, which a closed app cannot answer on. A redirect that shows no return address with a host
        in it passes, and the line says so. Without --proxied the check is what it was.

        With --private the name has to resolve to private addresses only (the app's private endpoint, registered in the landing zone's central zone), and that is
        read first: a name that resolves to a public address, or not at all, makes no request and ends the check with one failed line that says which. The
        check is made this way, in the Operator and on the app's own name, when the app that serves the web page takes no public traffic and no host name of a
        gateway is set: a closed app answers nobody outside the network, so there is nothing to knock at from the runner, and an answer over a public address
        would prove nothing about the path that people take. The expected answers are the same.

health  Waits until https://<host>/healthz answers 200 with the word ok, for the check that the cases app answers after its code was published. It runs in the
        Operator, a container group inside the network (operator/run-tool.sh runs this file there), because an app that takes no public traffic answers nobody
        outside it. One request each try, no redirect followed, and a line for each try. With --private the name has to resolve to private addresses only (the
        app's private endpoint, registered in the landing zone's central zone): an answer over a public address proves nothing about the path that people take.

latency Measures how long the web page takes to answer, for the decision in docs/proposals/07-private-by-default.md ("The web page on Flex Consumption"). It asks
        https://<host>/healthz, which needs no sign-in, once every --interval seconds (5 to 60) for --minutes minutes (1 to 20: the Operator's container group has to finish
        within 25 minutes), one line for each request (the time in UTC, the status, the seconds), and then waits --idle-minutes with no request (8 for a run of 16 minutes or
        more, half the run below that, 0 for none: the platform scales an idle app down to zero in a few minutes) and asks --after-idle more times (3), so that the first
        answer after the gap shows what a start from zero costs. A request may take --timeout seconds (75), longer than the minute that the platform's front end held requests
        for on 2026-11-05. It ends with a summary line: the count, the median, the 95th percentile, the slowest, the number of requests that were not answered 200 with the
        word ok, and the numbers that took more than 5 and more than 15 seconds, and one line that applies the rule: the exit code is 0 when no request took more than 15
        seconds and none was not 200, and 1 otherwise (and when --private finds a public address). It runs in the Operator, over the app's private endpoint, as health does.

Standard library only. It reads; it sends no credential and changes nothing.
"""
from __future__ import annotations

import argparse
import datetime
import http.client
import ipaddress
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Callable

PAGES = ("/", "/history", "/me/decisions", "/me/settings", "/me/notes", "/ops/pause", "/ops/permissions", "/ok/0123456789abcdef", "/why/k0123456789abc",
         "/arm/return", "/arm/return?code=x&state=y")
FORGED_PAGES = ("/", "/ok/0123456789abcdef", "/arm/return?code=x&state=y")
HOST = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,200}[a-z0-9])?$")
SIGN_IN = re.compile(r"^(https://login\.microsoftonline\.com/|/\.auth/login/aad)", re.I)
# The parameters in which the platform's sign-in puts the address that a person comes back to: the one that it gives Microsoft Entra, and the one that it keeps in
# its own redirect. Both are built from the host that the sign-in believes the request was made to, which behind a reverse proxy is the name that its
# forwardProxy setting reads from a header (environment/cases/main.bicep).
RETURN_PARAMETERS = ("redirect_uri", "post_login_redirect_uri")
# The addresses that a private endpoint is given: the ranges of RFC 1918. A name that resolves to anything else is a public address.
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
HEALTH_TRIES_MAX, HEALTH_INTERVAL_MAX, HEALTH_TIMEOUT_MAX = 120, 60, 60
# The latency measurement: one request every few seconds for some minutes, and a few more after a quiet time, so that a start from zero shows. The Operator's container group has to finish in 25 minutes
# (the group is made for the run and a start takes one to two minutes), so a run is 20 minutes at the most. A line is about 45 characters and the log of a container keeps 16 KB and the run's summary
# 300 lines, so a request every five seconds at the fastest. A request may wait longer than the minute that the platform's front end held requests for on 2026-11-05, so that a stall shows as it was.
LATENCY_MINUTES_MAX, LATENCY_INTERVAL_MIN, LATENCY_INTERVAL_MAX, LATENCY_TIMEOUT_DEFAULT, LATENCY_TIMEOUT_MAX = 20, 5, 60, 75, 120
LATENCY_IDLE_DEFAULT_MINUTES, LATENCY_AFTER_IDLE_DEFAULT, LATENCY_AFTER_IDLE_MAX = 8, 3, 10
# The two limits of the rule in docs/proposals/07-private-by-default.md ("The web page on Flex Consumption"): the web page stays on Flex only if no request took longer than the second and none was not 200.
SLOW_SECONDS, STALL_SECONDS = 5.0, 15.0


class Problem(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


Fetch = Callable[[str, dict], "tuple[int, dict, bytes]"]
TRIES = 3  # the app runs on a plan that scales to zero: the first answer after a quiet time can take a minute
TIMEOUT = 60
# The platform's sign-in sends a visitor whose User-Agent is a browser's to Microsoft Entra and answers any other client with 401. The check asks the way a
# person's browser does, so that it proves where a person is sent.
USER_AGENT = "Mozilla/5.0 (compatible; meternaut-console-check)"


def fetch(url: str, headers: dict) -> tuple[int, dict, bytes]:
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers}, method="GET")
    for attempt in range(1, TRIES + 1):
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read(4096)
        except urllib.error.HTTPError as error:
            return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read(4096)
        except (TimeoutError, urllib.error.URLError, OSError) as error:
            if attempt == TRIES:
                raise Problem(f"no answer from {url.split('?')[0]} after {TRIES} tries of {TIMEOUT} seconds ({type(error).__name__})") from error


def fetch_once(url: str, headers: dict, timeout: float = TIMEOUT) -> tuple[int, dict, bytes]:
    """One request and no second try: the loop of the health check is the one that tries again. A failure to answer is an OSError, a HTTPException or a Problem."""
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers}, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read(4096)
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read(4096)


def return_hosts(location: str) -> list[str]:
    """The host names that the return addresses in a redirect to the sign-in name, in lower case. A return address that is a path only names none."""
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(location).query)
    hosts = []
    for name in RETURN_PARAMETERS:
        for value in query.get(name, []):
            parts = urllib.parse.urlsplit(value)
            if parts.scheme and parts.netloc:
                hosts.append((parts.hostname or "").lower())
    return hosts


def verdict(path: str, status: int, headers: dict, expect: str, proxied_host: str | None = None) -> tuple[bool, str]:
    where = headers.get("location", "")
    if expect == "signin":
        ok = status in (301, 302, 303, 307, 308) and bool(SIGN_IN.match(where))
        text = f"{status} to {where.split('?')[0][:70]}" if where else str(status)
        if ok and proxied_host:
            hosts = return_hosts(where)
            elsewhere = sorted({h for h in hosts if h != proxied_host})
            if elsewhere:
                return False, f"{text}, but the return address names {', '.join(elsewhere)[:60]}"
            text += ", return address names the host" if hosts else ", no return address with a host in it"
        return ok, text
    return status == 503, str(status)


def door(host: str, expect: str, get: Fetch = fetch, proxied: bool = False, private: bool = False,
         resolve: Callable[[str], list[str]] | None = None) -> tuple[bool, list[tuple[str, str, bool, str]]]:
    if not HOST.match(host):
        raise Problem("--host is a host name")
    if expect not in ("signin", "refuse"):
        raise Problem("--expect is signin or refuse")
    named = host if proxied else None
    rows: list[tuple[str, str, bool, str]] = []
    if private:
        ok, text = private_name(host, resolve or resolve_host)
        rows.append(("name", "private address", ok, text))
        if not ok:
            return False, rows
    status, _, body = get(f"https://{host}/healthz", {})
    rows.append(("/healthz", "no sign-in", status == 200 and body.strip() == b"ok", f"{status} {body.strip()[:10].decode('ascii', 'replace')}"))
    for path in PAGES:
        status, headers, _ = get(f"https://{host}{path}", {})
        ok, text = verdict(path, status, headers, expect, named)
        rows.append((path, "no sign-in", ok, text))
    forged = {"x-ms-client-principal-id": str(uuid.uuid4()), "x-ms-client-principal-name": "someone@example.com"}
    for path in FORGED_PAGES:
        status, headers, _ = get(f"https://{host}{path}", forged)
        ok, text = verdict(path, status, headers, expect, named)
        rows.append((path, "made-up sign-in header", ok, text))
    return all(row[2] for row in rows), rows


def resolve_host(host: str) -> list[str]:
    """The addresses that a name resolves to, as the machine that runs this resolves them (inside the network that is the landing zone's DNS)."""
    return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})


def is_private(address: str) -> bool:
    try:
        value = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(value in network for network in PRIVATE_NETWORKS)


def private_name(host: str, resolve: Callable[[str], list[str]]) -> tuple[bool, str]:
    """Whether the name resolves, as this machine resolves it, to private addresses only, and the words that say what was seen. A closed app is reached through its private endpoint and nowhere else."""
    try:
        addresses = resolve(host)
    except OSError as error:
        return False, f"{host} does not resolve ({type(error).__name__})"
    if addresses and all(is_private(address) for address in addresses):
        return True, f"{addresses[0]} (private)"
    public = [address for address in addresses if not is_private(address)]
    seen = f"{public[0]} (public)" if public else "no address"
    return False, f"{host} resolves to {seen}, and a private address is required: the landing zone has not registered the endpoint's name, or this DNS does not see it"


def health(host: str, tries: int, interval: float, timeout: float, private: bool, get: Callable[..., "tuple[int, dict, bytes]"] = fetch_once,
           resolve: Callable[[str], list[str]] = resolve_host, sleep: Callable[[float], None] = time.sleep, out=sys.stdout) -> bool:
    """Waits until https://<host>/healthz answers 200 with the word ok. A line for each try says what was seen; the first one that answers ends the wait."""
    if not HOST.match(host):
        raise Problem("--host is a host name")
    if not 1 <= tries <= HEALTH_TRIES_MAX:
        raise Problem(f"--tries is a number from 1 to {HEALTH_TRIES_MAX}")
    if not 0 <= interval <= HEALTH_INTERVAL_MAX:
        raise Problem(f"--interval is a number of seconds from 0 to {HEALTH_INTERVAL_MAX}")
    if not 1 <= timeout <= HEALTH_TIMEOUT_MAX:
        raise Problem(f"--timeout is a number of seconds from 1 to {HEALTH_TIMEOUT_MAX}")
    url = f"https://{host}/healthz"
    for attempt in range(1, tries + 1):
        seen = f"try {attempt} of {tries}:"
        try:
            addresses = resolve(host)
        except OSError as error:
            print(f"{seen} {host} does not resolve ({type(error).__name__})", file=out)
        else:
            kind = "private" if addresses and all(is_private(a) for a in addresses) else "public"
            where = f"{addresses[0] if addresses else 'no address'} ({kind})"
            if private and kind != "private":
                print(f"{seen} {host} resolves to {where}, and a private address is required: the landing zone has not registered the endpoint's name, or this DNS does not see it", file=out)
            else:
                try:
                    status, _, body = get(url, {}, timeout)
                except (OSError, http.client.HTTPException, Problem) as error:
                    print(f"{seen} {where}, no answer ({type(error).__name__})", file=out)
                else:
                    word = body.strip()[:10].decode("ascii", "replace")
                    if status == 200 and body.strip() == b"ok":
                        print(f"ok: {url} answered {status} {word} at try {attempt}, {where}", file=out)
                        return True
                    print(f"{seen} {where}, HTTP {status} {word}".rstrip(), file=out)
        if attempt < tries:
            sleep(interval)
    print(f"FAIL: {url} did not answer 200 ok in {tries} tries", file=out)
    return False


def percentile(sorted_seconds: list[float], percent: float) -> float:
    """The nearest-rank percentile of a sorted list: the smallest value that at least `percent` per cent of the values do not exceed."""
    rank = max(1, -(-len(sorted_seconds) * percent // 100))
    return sorted_seconds[int(rank) - 1]


def latency(host: str, minutes: int, interval: float, private: bool, idle_minutes: int | None = None, after_idle: int = LATENCY_AFTER_IDLE_DEFAULT,
            timeout: float = LATENCY_TIMEOUT_DEFAULT, get: Callable[..., "tuple[int, dict, bytes]"] = fetch_once, resolve: Callable[[str], list[str]] = resolve_host,
            sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
            now: Callable[[], datetime.datetime] = lambda: datetime.datetime.now(datetime.timezone.utc), out=sys.stdout) -> int:
    """Asks https://<host>/healthz every `interval` seconds for `minutes` minutes, and says how long each answer took and what the whole run came to.

    The run is a steady part, then a quiet gap of `idle_minutes` with no request (long enough for the platform to scale the app down to zero), then `after_idle` requests, so that the first
    answer after the gap shows what a start from zero costs. A request that took more than the timeout, or that got no answer, is a line of its own and counts as not answered with 200.
    One line for each request (the time in UTC, the status, the seconds), a summary line (the count, the median, the 95th percentile, the slowest, how many were not 200, how many took more than 5
    and more than 15 seconds) and a last line that applies the rule of docs/proposals/07-private-by-default.md. Returns 0 when no request took more than 15 seconds and none was not 200, 1 when
    one did, and 1 when the name did not resolve to a private address (with --private) and nothing was asked. It reads only and sends no credential."""
    if not HOST.match(host):
        raise Problem("--host is a host name")
    if not 1 <= minutes <= LATENCY_MINUTES_MAX:
        raise Problem(f"--minutes is a whole number from 1 to {LATENCY_MINUTES_MAX}: the Operator's container group has to finish within 25 minutes")
    if not LATENCY_INTERVAL_MIN <= interval <= LATENCY_INTERVAL_MAX:
        raise Problem(f"--interval is a number of seconds from {LATENCY_INTERVAL_MIN} to {LATENCY_INTERVAL_MAX}")
    if not 1 <= timeout <= LATENCY_TIMEOUT_MAX:
        raise Problem(f"--timeout is a number of seconds from 1 to {LATENCY_TIMEOUT_MAX}")
    if idle_minutes is None:
        idle_minutes = LATENCY_IDLE_DEFAULT_MINUTES if minutes >= 2 * LATENCY_IDLE_DEFAULT_MINUTES else minutes // 2
    if idle_minutes < 0 or idle_minutes >= minutes:
        raise Problem("--idle-minutes is a whole number from 0 up to one less than --minutes")
    if idle_minutes and not 1 <= after_idle <= LATENCY_AFTER_IDLE_MAX:
        raise Problem(f"--after-idle is a number of requests from 1 to {LATENCY_AFTER_IDLE_MAX}")
    steady = minutes * 60 - idle_minutes * 60 - ((after_idle - 1) * interval if idle_minutes else 0)
    if steady < interval:
        raise Problem("the run is too short for its quiet gap: raise --minutes or lower --idle-minutes")
    url = f"https://{host}/healthz"
    if private:
        ok, text = private_name(host, resolve)
        print(f"name: {text}", file=out)
        if not ok:
            print("FAIL: no request was made: with --private the name has to resolve to private addresses only", file=out)
            return 1
    gap = f", then {idle_minutes} minutes with no request, then {after_idle} requests" if idle_minutes else ""
    print(f"latency: {url} every {interval:g} seconds for {minutes} minutes (requests for {minutes - idle_minutes} minutes{gap}), a request may take {timeout:g} seconds", file=out)
    seconds: list[float] = []
    cold: list[float] = []
    not_ok = 0

    def ask(label: str) -> None:
        nonlocal not_ok
        at = now().strftime("%H:%M:%S")
        started = clock()
        try:
            status, _, body = get(url, {}, timeout)
        except (OSError, http.client.HTTPException, Problem) as error:
            took = clock() - started
            answer, verdict_ok = f"no answer ({type(error).__name__})", False
        else:
            took = clock() - started
            word = body.strip()[:10].decode("ascii", "replace")
            verdict_ok = status == 200 and body.strip() == b"ok"
            answer = str(status) if verdict_ok else f"{status} {word}".rstrip()
        seconds.append(took)
        if label:
            cold.append(took)
        if not verdict_ok:
            not_ok += 1
        print(f"{at}  {answer:24} {took:7.3f} s{'  ' + label if label else ''}", file=out)

    begun = clock()
    while True:
        began = clock()
        ask("")
        wait = max(interval - (clock() - began), 0)
        if clock() - begun + wait >= steady:
            break
        sleep(wait)
    if idle_minutes:
        print(f"{now().strftime('%H:%M:%S')}  quiet gap of {idle_minutes} minutes: no request", file=out)
        sleep(idle_minutes * 60)
        for number in range(after_idle):
            began = clock()
            ask("after the quiet gap")
            if number < after_idle - 1:
                sleep(max(interval - (clock() - began), 0))
    ordered = sorted(seconds)
    slow, stalled = sum(1 for value in seconds if value > SLOW_SECONDS), sum(1 for value in seconds if value > STALL_SECONDS)
    print(f"latency: {len(seconds)} requests, p50 {percentile(ordered, 50):.2f} s, p95 {percentile(ordered, 95):.2f} s, max {ordered[-1]:.2f} s, "
          f"{not_ok} not 200, {slow} slower than {SLOW_SECONDS:g} s, {stalled} slower than {STALL_SECONDS:g} s", file=out)
    if cold:
        first = cold[0]
        print(f"after the quiet gap: {len(cold)} requests, the first took {first:.2f} s, the slowest {max(cold):.2f} s", file=out)
    if stalled == 0 and not_ok == 0:
        print(f"verdict: no request took more than {STALL_SECONDS:g} seconds and none was not 200", file=out)
        return 0
    print(f"verdict: {stalled} of {len(seconds)} requests took more than {STALL_SECONDS:g} seconds and {not_ok} did not answer 200: the rule of docs/proposals/07-private-by-default.md is not met", file=out)
    return 1


def main(argv=None, get: Callable[..., "tuple[int, dict, bytes]"] | None = None, out=sys.stdout,
         resolve: Callable[[str], list[str]] = resolve_host, sleep: Callable[[float], None] = time.sleep,
         clock: Callable[[], float] = time.monotonic, now: Callable[[], datetime.datetime] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["door", "health", "latency"])
    parser.add_argument("--host", required=True)
    parser.add_argument("--expect", default="signin", help="door: signin or refuse")
    parser.add_argument("--proxied", action="store_true", help="door: the host is a reverse proxy's name, and the sign-in's return address has to name it")
    parser.add_argument("--summary", help="door: append the rows to this file")
    parser.add_argument("--tries", type=int, default=60, help="health: most tries")
    parser.add_argument("--interval", type=float, default=10, help="health and latency: seconds between two tries or requests")
    parser.add_argument("--timeout", type=float, default=None, help="health: seconds that one request may take (15); latency: the same (75)")
    parser.add_argument("--private", action="store_true", help="door, health and latency: the name has to resolve to private addresses only")
    parser.add_argument("--minutes", type=int, default=20, help=f"latency: minutes that the run takes, at most {LATENCY_MINUTES_MAX}")
    parser.add_argument("--idle-minutes", type=int, default=None, help="latency: minutes with no request before the last few requests (8 for a run of 16 minutes or more, half the run below that; 0 for none)")
    parser.add_argument("--after-idle", type=int, default=LATENCY_AFTER_IDLE_DEFAULT, help="latency: requests after the quiet gap")
    args = parser.parse_args(argv)
    host = args.host.strip().lower()
    try:
        if args.command == "health":
            request = get if get is not None else fetch_once
            return 0 if health(host, args.tries, args.interval, 15.0 if args.timeout is None else args.timeout, args.private, request, resolve, sleep, out) else 1
        if args.command == "latency":
            request = get if get is not None else fetch_once
            return latency(host, args.minutes, args.interval, args.private, args.idle_minutes, args.after_idle,
                           LATENCY_TIMEOUT_DEFAULT if args.timeout is None else args.timeout, request, resolve, sleep, clock,
                           now or (lambda: datetime.datetime.now(datetime.timezone.utc)), out)
        passed, rows = door(host, args.expect, get or fetch, args.proxied, args.private, resolve)
    except Problem as error:
        print(f"console-check: {error}", file=sys.stderr)
        return 2
    lines = [f"{'PASS' if ok else 'FAIL'}  {path:28} {how:24} {text}" for path, how, ok, text in rows]
    print("\n".join(lines), file=out)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write("### The console's front door\n\n```\n" + "\n".join(lines) + "\n```\n\n"
                         + ("Nobody gets a page without a sign-in.\n" if passed else "**A request got something that it should not.**\n"))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
