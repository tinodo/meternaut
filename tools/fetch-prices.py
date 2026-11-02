#!/usr/bin/env python3
"""Reproducible Azure retail price snapshot. Standard library only; installs nothing.

What it does
  1. Reads a query specification (default: docs/design/cost/price-queries.json).
  2. Calls the unauthenticated Azure Retail Prices API
         https://prices.azure.com/api/retail/prices
     once per query and per currency (EUR and USD), following NextPageLink to the end.
  3. Keeps the meters a query selects (server-side $filter plus client-side include/exclude
     regular expressions), merges EUR and USD on the meter identity and writes one record per
     meter, sorted by key, to the snapshot (default: docs/design/cost/prices-snapshot.json).
  4. Copies the hand-recorded prices of the specification (prices that the API does not carry,
     source "page") into the snapshot, and re-checks them - plus a list of API meters - against
     the public pricing pages, whose HTML embeds the USD price per region in data-amount
     attributes.

Usage
  python tools/fetch-prices.py                       fetch, build and write the snapshot
  python tools/fetch-prices.py --only apim,storage   run only some queries (writes to --out!)
  python tools/fetch-prices.py --no-pages            skip the pricing-page checks
  python tools/fetch-prices.py --dry-run             print the API calls and exit (no network)
  python tools/fetch-prices.py --compare OLD.json    after the run, diff the meter keys against OLD
  python tools/fetch-prices.py compare OLD.json NEW.json [--prices]
                                                     offline diff of two snapshots; exit 1 if the
                                                     meter keys differ (or, with --prices, if any
                                                     price differs)
  python tools/fetch-prices.py --self-test           offline unit tests

Exit codes: 0 ok · 1 differences found by compare · 2 a query failed (nothing written) ·
            3 --strict and the run raised anomalies that need a look.
"""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = ROOT / "docs" / "design" / "cost" / "price-queries.json"
DEFAULT_OUT = ROOT / "docs" / "design" / "cost" / "prices-snapshot.json"
SCHEMA = "meternaut/prices-snapshot@1"
API_BASE = "https://prices.azure.com/api/retail/prices"
USER_AGENT = "Mozilla/5.0 (compatible; meternaut-fetch-prices/1)"
LIST_FIELDS = ("meters", "manual", "pageChecks", "anomalies", "queries")


class FetchError(RuntimeError):
    pass


# ------------------------------------------------------------------ small helpers

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def num(x):
    """Integral floats become ints (tier minimum units are whole numbers); everything else is kept."""
    if isinstance(x, float) and x.is_integer() and abs(x) < 1e15:
        return int(x)
    return x


def log(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(msg, file=sys.stderr, flush=True)


def http_get(url: str, accept: str, timeout: float, retries: int, quiet: bool = False) -> bytes:
    """GET with retry on 429, 5xx and transport errors; honours Retry-After (capped at 60 s)."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise FetchError(f"HTTP {e.code} for {url}") from e
            wait = min(60.0, float(e.headers.get("Retry-After") or 2 ** attempt))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            wait = min(60.0, 2.0 ** attempt)
        if attempt < retries:
            log(f"  retry {attempt + 1}/{retries} in {wait:.0f}s ({last})", quiet)
            time.sleep(wait)
    raise FetchError(f"giving up on {url}: {last}")


# ------------------------------------------------------------------ the API

def expand_regions(tokens: list[str], groups: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for t in tokens:
        for r in groups.get(t, [t]):
            if r not in out:
                out.append(r)
    return out


def odata_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_filter(query: dict, groups: dict[str, list[str]]) -> str:
    parts = []
    if query.get("filter"):
        parts.append(f"({query['filter']})")
    regions = expand_regions(query.get("regions", []), groups)
    if regions:
        parts.append("(" + " or ".join(f"armRegionName eq {odata_literal(r)}" for r in regions) + ")")
    if not parts:
        raise FetchError(f"query {query.get('id')!r} has neither filter nor regions: refusing a full-catalogue download")
    return " and ".join(parts)


def api_url(flt: str, currency: str, api_version: str | None) -> str:
    q = []
    if api_version:
        q.append(f"api-version={api_version}")
    q.append(f"currencyCode={urllib.parse.quote(odata_literal(currency), safe='')}")
    q.append("$filter=" + urllib.parse.quote(flt, safe=""))
    return API_BASE + "?" + "&".join(q)


def is_api_url(url: str) -> bool:
    u = urllib.parse.urlsplit(url)
    return u.scheme == "https" and u.hostname == "prices.azure.com" and u.path == "/api/retail/prices"


def fetch_items(flt: str, currency: str, args, spec_api: dict) -> tuple[list[dict], int, str]:
    """All pages of one filter in one currency -> (items, pages, retrievedAt of the first page)."""
    url = api_url(flt, currency, spec_api.get("apiVersion"))
    items: list[dict] = []
    seen: set[str] = set()
    pages = 0
    first_at = ""
    while url:
        if url in seen:
            raise FetchError("NextPageLink loop")
        seen.add(url)
        if not is_api_url(url):
            raise FetchError(f"refusing to follow a NextPageLink outside the API: {url}")
        body = http_get(url, "application/json", args.timeout, args.retries, args.quiet)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise FetchError(f"not JSON: {url}: {e}") from e
        pages += 1
        if not first_at:
            first_at = utc_now()
        items.extend(data.get("Items") or [])
        url = data.get("NextPageLink")
        if url and args.delay:
            time.sleep(args.delay)
    return items, pages, first_at


# ------------------------------------------------------------------ selection and identity

def selected(item: dict, query: dict) -> bool:
    types = query.get("priceTypes")
    if types and item.get("type") not in types:
        return False
    for field, pattern in (query.get("include") or {}).items():
        if not re.search(pattern, str(item.get(field) or ""), re.I):
            return False
    for field, pattern in (query.get("exclude") or {}).items():
        if re.search(pattern, str(item.get(field) or ""), re.I):
            return False
    return True


def identity(it: dict) -> tuple:
    """Two rows are the same meter only if every one of these agree. meterName is part of it because the API
    can give one meterId (and skuId, price) to two differently named meters, e.g. 'Hot LRS Write Operations'
    and 'LRS List and Create Container Operations'."""
    return (it.get("meterId"), it.get("skuId"), it.get("productName"), it.get("skuName"), it.get("meterName"),
            it.get("armRegionName"), it.get("type"), it.get("reservationTerm") or "", num(it.get("tierMinimumUnits") or 0))


def meter_key(it: dict) -> str:
    """Readable and unique: region|service|product|sku|meter|type[:term]|tier|meterId8:skuSuffix.
    The API can list one meter under two skuId values (same meterId and price), hence the suffix."""
    term = it.get("reservationTerm")
    ptype = it.get("type", "") + (f":{term}" if term else "")
    sku_id = it.get("skuId") or ""
    tail = (it.get("meterId") or "")[:8] + (":" + sku_id.rsplit("/", 1)[-1] if "/" in sku_id else "")
    return "|".join([
        it.get("armRegionName") or "(none)", it.get("serviceName", ""), it.get("productName", ""),
        it.get("skuName", ""), it.get("meterName", ""), ptype,
        "t" + str(num(it.get("tierMinimumUnits") or 0)), tail,
    ])


def meter_record(it: dict, queries: list[str], retrieved_at: str) -> dict:
    rec = {
        "key": meter_key(it),
        "source": "api",
        "service": it.get("serviceName"),
        "serviceFamily": it.get("serviceFamily"),
        "product": it.get("productName"),
        "sku": it.get("skuName"),
        "armSkuName": it.get("armSkuName"),
        "meter": it.get("meterName"),
        "region": it.get("armRegionName"),
        "location": it.get("location"),
        "unitOfMeasure": it.get("unitOfMeasure"),
        "priceType": it.get("type"),
        "reservationTerm": it.get("reservationTerm"),
        "tierMinimumUnits": num(it.get("tierMinimumUnits") or 0),
        "prices": {},
        "effectiveStartDate": (it.get("effectiveStartDate") or "")[:10],
        "meterId": it.get("meterId"),
        "skuId": it.get("skuId"),
        "productId": it.get("productId"),
        "isPrimaryMeterRegion": it.get("isPrimaryMeterRegion"),
        "retrievedAt": retrieved_at,
        "queries": sorted(queries),
    }
    return {k: v for k, v in rec.items() if v is not None}


def add_flag(rec: dict, flag: str) -> None:
    if flag not in rec.setdefault("flags", []):
        rec["flags"] = sorted(rec["flags"] + [flag])


def merge_currency(meters: dict, anomalies: list, qid: str, currency: str, items: list[dict], at: str,
                   flags: list[str] | None = None) -> int:
    """Fold one currency's selected items into `meters` (identity -> record). Returns the count kept."""
    by_id: dict[tuple, dict] = {}
    for it in items:
        ident = identity(it)
        prev = by_id.get(ident)
        if prev is None:
            by_id[ident] = it
            continue
        keep, drop = (it, prev) if (it.get("effectiveStartDate") or "") > (prev.get("effectiveStartDate") or "") else (prev, it)
        by_id[ident] = keep
        anomalies.append({"type": "duplicate-identity", "query": qid, "currency": currency,
                          "key": meter_key(keep), "kept": (keep.get("effectiveStartDate") or "")[:10],
                          "dropped": (drop.get("effectiveStartDate") or "")[:10]})
    for ident, it in by_id.items():
        rec = meters.get(ident)
        if rec is None:
            rec = meter_record(it, [qid], at)
            meters[ident] = rec
        elif qid not in rec["queries"]:
            rec["queries"] = sorted(rec["queries"] + [qid])
        for f in flags or []:
            add_flag(rec, f)
        rec["prices"][currency] = it["unitPrice"]
        for sp in it.get("savingsPlan") or []:
            rec.setdefault("savingsPlan", {}).setdefault(sp.get("term"), {})[currency] = sp.get("unitPrice")
        if it.get("retailPrice") != it.get("unitPrice"):
            anomalies.append({"type": "retail-unit-price-differ", "key": rec["key"], "currency": currency,
                              "retailPrice": it.get("retailPrice"), "unitPrice": it.get("unitPrice")})
    return len(by_id)


# ------------------------------------------------------------------ FX and anomalies on prices

def observed_fx(meters: list[dict]) -> dict:
    """EUR per USD seen across the list prices (meters with both prices >= 1 are precise enough)."""
    ratios = [m["prices"]["EUR"] / m["prices"]["USD"] for m in meters
              if m.get("prices", {}).get("EUR", 0) >= 1 and m["prices"].get("USD", 0) >= 1]
    if not ratios:
        return {"eurPerUsd": None, "n": 0}
    ratios.sort()
    return {"eurPerUsd": round(statistics.median(ratios), 5), "n": len(ratios),
            "p05": round(ratios[int(0.05 * (len(ratios) - 1))], 5),
            "p95": round(ratios[int(0.95 * (len(ratios) - 1))], 5),
            "basis": "median of EUR/USD unit price over meters with both prices >= 1"}


def flag_precision(meters: list[dict], fx: float | None, anomalies: list) -> None:
    """EUR prices are rounded to 4 decimals: tiny per-second or per-token meters collapse to 0."""
    for m in meters:
        p = m["prices"]
        eur, usd = p.get("EUR"), p.get("USD")
        if eur is None or usd is None:
            anomalies.append({"type": "missing-currency", "key": m["key"], "have": sorted(p)})
            continue
        if eur == 0 and usd > 0:
            add_flag(m, "eur-rounded-to-zero")
        elif fx and usd > 0 and eur > 0 and abs(eur / (usd * fx) - 1) > 0.02:
            add_flag(m, "eur-precision-loss")


# ------------------------------------------------------------------ pricing pages

class PageTables(html.parser.HTMLParser):
    """Collects the tables of an azure.microsoft.com pricing page.

    The pages render prices with JavaScript from <span class="price-data" data-amount='{"regional":
    {"europe-west": 0.2, ...}}'> (USD, per region slug); the visible text is "$-" until then.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._table: dict | None = None
        self._row: list[dict] | None = None
        self._cell: dict | None = None
        self._heading_tag: str | None = None
        self._heading = ""
        self._last_heading = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h2", "h3", "h4"):
            self._heading_tag, self._heading = tag, ""
        elif tag == "table":
            self._table = {"heading": self._last_heading, "headers": [], "rows": []}
            self.tables.append(self._table)
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {"text": "", "prices": [], "th": tag == "th"}
        elif tag == "span" and self._cell is not None and "price-data" in (a.get("class") or ""):
            try:
                amount = json.loads(a.get("data-amount") or "{}")
            except json.JSONDecodeError:
                amount = {}
            regional = amount.get("regional") if isinstance(amount, dict) else None
            self._cell["prices"].append(regional if isinstance(regional, dict) else {})
            self._cell["text"] += " [price] "

    def handle_endtag(self, tag):
        if tag == self._heading_tag:
            self._last_heading = " ".join(self._heading.split()) or self._last_heading
            self._heading_tag = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row and all(c["th"] for c in self._row) and not self._table["rows"]:
                self._table["headers"].append([" ".join(c["text"].split()) for c in self._row])
            elif self._row:
                self._table["rows"].append(self._row)
            self._row = None
        elif tag == "table":
            self._table = None

    def handle_data(self, data):
        if self._heading_tag:
            self._heading += data
        if self._cell is not None:
            self._cell["text"] += data


def parse_page(html_text: str) -> list[dict]:
    p = PageTables()
    p.feed(html_text)
    return p.tables


def squash(text: str) -> str:
    return " ".join(text.split())


def page_value(tables: list[dict], addr: dict) -> tuple[float | None, str]:
    """Locate one price on a parsed page: table heading regex (tableIndex picks the k-th such table),
    row-label regex (rowIndex picks the k-th such row), optional column-header regex, and the index of the
    price span inside the row (or inside the column's cell). -> (USD per `slug`, human-readable label)."""
    table_rx = re.compile(addr.get("table", ""), re.I)
    row_rx = re.compile(addr["row"], re.I)
    col_rx = re.compile(addr["column"], re.I) if addr.get("column") else None
    want = addr.get("rowIndex", 0)
    candidates = [t for t in tables if table_rx.search(t["heading"])]
    if "tableIndex" in addr:
        candidates = candidates[addr["tableIndex"]:addr["tableIndex"] + 1]
    seen = 0
    for t in candidates:
        headers = t["headers"][0] if t["headers"] else []
        for row in t["rows"]:
            if not row_rx.search(squash(row[0]["text"])):
                continue
            if seen < want:
                seen += 1
                continue
            cells = row[1:]
            if col_rx:
                idx = [i for i, h in enumerate(headers[1:] if len(headers) == len(row) else headers) if col_rx.search(h)]
                if not idx:
                    return None, f"column {addr['column']!r} not in {headers}"
                cells = [cells[idx[0]]] if idx[0] < len(cells) else []
            spans = [s for c in cells for s in c["prices"]]
            k = addr.get("span", 0)
            if k >= len(spans):
                return None, f"row {squash(row[0]['text'])!r} has {len(spans)} price span(s)"
            value = spans[k].get(addr.get("slug", "europe-west"))
            label = f"{t['heading']} > {squash(row[0]['text'])}" + (f" > {addr['column']}" if col_rx else "")
            return value, label
    return None, "row not found"


class PageCache:
    def __init__(self, args):
        self.args, self.pages = args, {}

    def get(self, url: str) -> tuple[list[dict] | None, str]:
        if url not in self.pages:
            try:
                body = http_get(url, "text/html", self.args.timeout, self.args.retries, self.args.quiet)
                self.pages[url] = (parse_page(body.decode("utf-8", "replace")), utc_now())
            except FetchError as e:
                log(f"  page unavailable: {e}", self.args.quiet)
                self.pages[url] = (None, utc_now())
        return self.pages[url]


def find_meter(meters: list[dict], sel: dict) -> list[dict]:
    return [m for m in meters if all(m.get(k) == v for k, v in sel.items())]


def tolerance(api: float) -> float:
    return max(5e-7, 0.002 * abs(api))


def run_page_checks(spec: dict, meters: list[dict], cache: PageCache) -> list[dict]:
    out = []
    for chk in spec.get("pageChecks", []):
        rec = {"id": chk["id"], "page": chk["page"], "slug": chk.get("slug", "europe-west"), "meterSelector": chk["meter"]}
        found = find_meter(meters, chk["meter"])
        if len(found) != 1:
            rec.update(status="unresolved-meter", note=f"{len(found)} meters match the selector")
            out.append(rec)
            continue
        m = found[0]
        rec["meterKey"] = m["key"]
        tables, at = cache.get(chk["page"])
        rec["pageRetrievedAt"] = at
        if tables is None:
            rec.update(status="page-unavailable")
            out.append(rec)
            continue
        value, label = page_value(tables, {**chk["address"], "slug": rec["slug"]})
        if value is None:
            rec.update(status="unresolved-page", note=label)
            out.append(rec)
            continue
        scale = chk.get("scale", 1)
        api_usd = m["prices"].get("USD")
        rec.update(pageLabel=label, pageUsd=value, scale=scale, apiUsd=api_usd, apiEur=m["prices"].get("EUR"),
                   unitOfMeasure=m.get("unitOfMeasure"))
        rec["status"] = "match" if api_usd is not None and abs(value * scale - api_usd) <= tolerance(api_usd) else "mismatch"
        if chk.get("note"):
            rec["note"] = chk["note"]
        out.append(rec)
    return out


def finish_manual(spec: dict, fx: float | None, cache: PageCache, anomalies: list) -> list[dict]:
    out = []
    for m in spec.get("manual", []):
        rec = {"key": m["key"], "source": "page", "url": m["url"], "date": m["date"]}
        for f in ("kind", "service", "product", "sku", "meter", "region", "unitOfMeasure", "tierMinimumUnits", "allowance", "note"):
            if f in m:
                rec[f] = m[f]
        prices = dict(m.get("prices", {}))
        if m.get("eur") == "derive" and "USD" in prices and fx:
            prices["EUR"] = round(prices["USD"] * fx, 4)
            rec["eurDerived"] = f"USD x {fx} (observed list FX)"
        rec["prices"] = prices
        chk = m.get("check")
        if chk:
            tables, at = cache.get(m["url"])
            value, label = (None, "page unavailable") if tables is None else page_value(tables, chk)
            scale = chk.get("scale", 1)
            usd = prices.get("USD")
            if value is None:
                rec["pageCheck"] = {"status": "unresolved-page", "note": label, "retrievedAt": at}
                anomalies.append({"type": "manual-unchecked", "key": m["key"], "note": label})
            else:
                ok = usd is not None and abs(value * scale - usd) <= tolerance(usd)
                rec["pageCheck"] = {"status": "match" if ok else "mismatch", "pageUsd": value, "scale": scale,
                                    "pageLabel": label, "retrievedAt": at}
                if not ok:
                    anomalies.append({"type": "manual-mismatch", "key": m["key"], "recorded": usd, "page": value * scale})
        out.append(rec)
    return out


# ------------------------------------------------------------------ snapshot

def keys_hash(keys: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()


def build_snapshot(spec: dict, spec_bytes: bytes, spec_path: Path, args) -> dict:
    api = spec.get("api", {})
    currencies = [c.strip().upper() for c in (args.currencies.split(",") if args.currencies else api.get("currencies", ["EUR", "USD"]))]
    groups = spec.get("regionGroups", {})
    wanted = set(args.only.split(",")) if args.only else None
    queries = [q for q in spec["queries"] if not wanted or q["id"] in wanted]
    if wanted and {q["id"] for q in queries} != wanted:
        raise FetchError(f"unknown query id(s): {sorted(wanted - {q['id'] for q in queries})}")
    meters: dict[tuple, dict] = {}
    anomalies: list[dict] = []
    summary: list[dict] = []
    stamps: list[str] = []
    for q in queries:
        flt = build_filter(q, groups)
        row = {"id": q["id"], "topic": q.get("topic", ""), "filter": flt, "returned": {}, "selected": {}, "pages": 0}
        for cur in currencies:
            items, pages, at = fetch_items(flt, cur, args, api)
            stamps.append(at)
            chosen = [i for i in items if selected(i, q)]
            row["returned"][cur], row["pages"] = len(items), row["pages"] + pages
            row["selected"][cur] = merge_currency(meters, anomalies, q["id"], cur, chosen, at, q.get("flags"))
        if q.get("expectMin") and min(row["selected"].values()) < q["expectMin"]:
            anomalies.append({"type": "underfilled", "query": q["id"], "selected": row["selected"], "expectMin": q["expectMin"]})
        summary.append(row)
        log(f"  {q['id']:<28} returned {row['returned']} selected {row['selected']} ({row['pages']} page(s))", args.quiet)
    recs = [meters[k] for k in meters]
    recs.sort(key=lambda m: m["key"])
    keys = [m["key"] for m in recs]
    if len(set(keys)) != len(keys):
        dup = sorted({k for k in keys if keys.count(k) > 1})
        raise FetchError(f"meter keys are not unique, first: {dup[:3]}")
    fx = observed_fx(recs)
    flag_precision(recs, fx.get("eurPerUsd"), anomalies)
    cache = PageCache(args)
    pages_on = not args.no_pages
    checks = run_page_checks(spec, recs, cache) if pages_on else []
    manual = finish_manual(spec, fx.get("eurPerUsd"), cache, anomalies) if not args.only else []
    for c in checks:
        if c["status"] != "match":
            anomalies.append({"type": "page-check-" + c["status"], "id": c["id"], "note": c.get("note", "")})
    anomalies.sort(key=lambda a: json.dumps(a, sort_keys=True))
    snap = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "tool": "tools/fetch-prices.py",
        "source": {"api": API_BASE, "apiVersion": api.get("apiVersion"), "currencies": currencies,
                   "retrievedFrom": min(stamps) if stamps else None, "retrievedUntil": max(stamps) if stamps else None},
        "spec": {"path": relative(spec_path), "sha256": hashlib.sha256(spec_bytes).hexdigest(), "queries": len(queries)},
        "fx": fx,
        "counts": {"meters": len(recs), "manual": len(manual), "pageChecks": len(checks),
                   "pageChecksMatched": sum(c["status"] == "match" for c in checks),
                   "anomalies": len(anomalies)},
        "meterKeysSha256": keys_hash(keys),
        "queries": summary,
        "anomalies": anomalies,
        "meters": recs,
        "manual": sorted(manual, key=lambda m: m["key"]),
        "pageChecks": checks,
    }
    return snap


def relative(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def dumps_snapshot(snap: dict) -> str:
    """Pretty top level, one compact JSON object per line for the long lists (diff- and grep-friendly)."""
    out = ["{"]
    items = list(snap.items())
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if k in LIST_FIELDS and isinstance(v, list):
            if not v:
                out.append(f" {json.dumps(k)}: []{comma}")
                continue
            out.append(f" {json.dumps(k)}: [")
            out.append(",\n".join("  " + json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in v))
            out.append(f" ]{comma}")
        else:
            body = json.dumps(v, ensure_ascii=False, indent=1).replace("\n", "\n ")
            out.append(f" {json.dumps(k)}: {body}{comma}")
    out.append("}")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ compare

def load_snapshot(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare_snapshots(old: dict, new: dict, with_prices: bool = False) -> tuple[bool, list[str]]:
    a = {m["key"]: m for m in old["meters"]}
    b = {m["key"]: m for m in new["meters"]}
    lines = [f"meters: old {len(a)} / new {len(b)}  meterKeysSha256 old {old.get('meterKeysSha256', '?')[:12]} / new {new.get('meterKeysSha256', '?')[:12]}"]
    removed, added = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    lines += [f"  only in old ({len(removed)}):"] + [f"    {k}" for k in removed[:25]]
    lines += [f"  only in new ({len(added)}):"] + [f"    {k}" for k in added[:25]]
    changed = [k for k in sorted(set(a) & set(b))
               if (a[k]["prices"], a[k].get("savingsPlan")) != (b[k]["prices"], b[k].get("savingsPlan"))]
    lines.append(f"  price changes among common meters: {len(changed)}")
    for k in changed[:25]:
        lines.append(f"    {k}: {a[k]['prices']} -> {b[k]['prices']}")
    differ = bool(removed or added or (with_prices and changed))
    return differ, lines


# ------------------------------------------------------------------ self-test

def self_test() -> int:
    groups = {"eu": ["westeurope", "swedencentral"], "global": ["Global", ""]}
    q = {"id": "t", "filter": "serviceName eq 'X'", "regions": ["eu", "global"]}
    assert build_filter(q, groups) == ("(serviceName eq 'X') and (armRegionName eq 'westeurope' or armRegionName eq 'swedencentral' "
                                       "or armRegionName eq 'Global' or armRegionName eq '')")
    try:
        build_filter({"id": "bad"}, groups)
        raise AssertionError("an unbounded query must be refused")
    except FetchError:
        pass
    assert odata_literal("O'Neil") == "'O''Neil'"
    assert is_api_url("https://prices.azure.com:443/api/retail/prices?$skip=1000")
    assert not is_api_url("https://evil.example/api/retail/prices") and not is_api_url("http://prices.azure.com/api/retail/prices")
    url = api_url("serviceName eq 'A B'", "EUR", "2023-01-01-preview")
    assert "currencyCode=%27EUR%27" in url and "$filter=serviceName%20eq%20%27A%20B%27" in url and "api-version=2023-01-01-preview" in url
    base = {"meterId": "0213351e-59d6-57b0-93d9-5c39b101d9c3", "skuId": "S/1", "armRegionName": "westeurope", "type": "Consumption",
            "tierMinimumUnits": 100.0, "serviceName": "API Management", "productName": "API Management", "skuName": "Consumption",
            "meterName": "Consumption Calls", "unitOfMeasure": "10K", "effectiveStartDate": "2024-03-01T00:00:00Z",
            "retailPrice": 0.03, "unitPrice": 0.03, "currencyCode": "EUR", "location": "EU West", "serviceFamily": "Developer Tools"}
    assert meter_key(base) == "westeurope|API Management|API Management|Consumption|Consumption Calls|Consumption|t100|0213351e:1"
    assert selected(base, {"include": {"meterName": "calls$"}, "exclude": {"skuName": "^Premium"}, "priceTypes": ["Consumption"]})
    assert not selected(base, {"include": {"meterName": "^Unit"}})
    meters: dict = {}
    anomalies: list = []
    merge_currency(meters, anomalies, "q1", "EUR", [base], "t0")
    merge_currency(meters, anomalies, "q2", "USD", [{**base, "unitPrice": 0.034, "retailPrice": 0.034, "currencyCode": "USD"}], "t0")
    rec = next(iter(meters.values()))
    assert rec["prices"] == {"EUR": 0.03, "USD": 0.034} and rec["queries"] == ["q1", "q2"] and rec["tierMinimumUnits"] == 100
    merge_currency(meters, anomalies, "q1", "EUR", [{**base, "savingsPlan": [{"term": "1 Year", "unitPrice": 0.02, "retailPrice": 0.02}]}], "t0")
    assert rec["savingsPlan"] == {"1 Year": {"EUR": 0.02}}
    tiny = {"key": "k", "prices": {"EUR": 0.0, "USD": 3e-06}}
    flag_precision([tiny], 0.88, anomalies)
    assert tiny["flags"] == ["eur-rounded-to-zero"]
    fx = observed_fx([{"prices": {"EUR": 8.8, "USD": 10.0}}, {"prices": {"EUR": 0.0088, "USD": 0.01}}, {"prices": {"EUR": 44.0, "USD": 50.0}}])
    assert fx["eurPerUsd"] == 0.88 and fx["n"] == 2
    page = ("<h2>Pricing</h2><table><thead><tr><th>x</th><th>Basic</th><th>Standard</th></tr></thead><tbody>"
            "<tr><td>Price<sup>1</sup></td><td><span class='price-data ' data-amount='{\"regional\":{\"europe-west\":0.5}}'>$-</span></td>"
            "<td><span class='price-data ' data-amount='{\"regional\":{\"europe-west\":1.5}}'>$-</span></td></tr></tbody></table>")
    tables = parse_page(page)
    assert page_value(tables, {"table": "Pricing", "row": "^Price", "column": "Standard", "slug": "europe-west"})[0] == 1.5
    assert page_value(tables, {"row": "^Price", "span": 0, "slug": "europe-west"})[0] == 0.5
    assert page_value(tables, {"row": "^Nothing"})[0] is None
    old = {"meters": [{"key": "a", "prices": {"EUR": 1}}, {"key": "b", "prices": {"EUR": 2}}], "meterKeysSha256": "x"}
    new = {"meters": [{"key": "a", "prices": {"EUR": 1.5}}, {"key": "c", "prices": {"EUR": 3}}], "meterKeysSha256": "y"}
    differ, _ = compare_snapshots(old, new)
    assert differ and not compare_snapshots(old, {"meters": old["meters"]}, True)[0]
    text = dumps_snapshot({"schema": "s", "counts": {"a": 1}, "meters": [{"key": "a"}, {"key": "b"}], "manual": []})
    assert json.loads(text)["meters"][1]["key"] == "b" and '\n  {"key":"b"}\n ]' in text
    print("self-test OK")
    return 0


# ------------------------------------------------------------------ main

def dry_run(spec: dict, args) -> int:
    api = spec.get("api", {})
    groups = spec.get("regionGroups", {})
    for q in spec["queries"]:
        if args.only and q["id"] not in args.only.split(","):
            continue
        for cur in api.get("currencies", ["EUR", "USD"]):
            print(f"{q['id']:<28} {api_url(build_filter(q, groups), cur, api.get('apiVersion'))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="*", help="compare OLD NEW (offline diff of two snapshots)")
    ap.add_argument("--spec", default=str(DEFAULT_SPEC))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--only", help="comma-separated query ids (the snapshot then holds only those; use --out)")
    ap.add_argument("--currencies", help="override the specification, e.g. EUR,USD")
    ap.add_argument("--no-pages", action="store_true", help="skip the pricing-page checks")
    ap.add_argument("--compare", metavar="OLD", help="after the run, diff the new snapshot against OLD")
    ap.add_argument("--prices", action="store_true", help="with compare: price changes also count as differences")
    ap.add_argument("--dry-run", action="store_true", help="print the API calls and exit")
    ap.add_argument("--strict", action="store_true", help="exit 3 when the run raised anomalies")
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--delay", type=float, default=0.1, help="seconds between result pages")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.command:
        if args.command[0] != "compare" or len(args.command) != 3:
            ap.error("usage: compare OLD.json NEW.json")
        differ, lines = compare_snapshots(load_snapshot(args.command[1]), load_snapshot(args.command[2]), args.prices)
        print("\n".join(lines))
        print("DIFFERENT" if differ else "SAME meter keys" + (" and prices" if args.prices else ""))
        return 1 if differ else 0

    spec_path = Path(args.spec)
    spec_bytes = spec_path.read_bytes()
    spec = json.loads(spec_bytes)
    if args.dry_run:
        return dry_run(spec, args)
    t0 = time.time()
    log(f"Azure Retail Prices API -> {relative(Path(args.out))}", args.quiet)
    try:
        snap = build_snapshot(spec, spec_bytes, spec_path, args)
    except FetchError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps_snapshot(snap), encoding="utf-8", newline="\n")
    c = snap["counts"]
    log(f"wrote {relative(out)}: {c['meters']} meters, {c['manual']} manual, page checks {c['pageChecksMatched']}/{c['pageChecks']} matched, "
        f"{c['anomalies']} anomalies, keys sha256 {snap['meterKeysSha256'][:16]}, {time.time() - t0:.0f}s", args.quiet)
    status = 0
    if args.compare:
        differ, lines = compare_snapshots(load_snapshot(args.compare), snap, args.prices)
        print("\n".join(lines))
        print("DIFFERENT" if differ else "SAME meter keys" + (" and prices" if args.prices else ""))
        status = 1 if differ else 0
    if args.strict and snap["anomalies"]:
        return 3
    return status


if __name__ == "__main__":
    sys.exit(main())
