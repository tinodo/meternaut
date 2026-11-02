#!/usr/bin/env python3
"""Pilot feasibility, the first stage of check C13 (docs/build-plan/03-first-checks.md). Standard library only.

Reads one closed month of the first estate's bill lines, with the read-only roles of the person who runs it,
and reconciles the total with what Cost Management shows for the same scope and month. It writes a
feasibility record that names the estate, so it writes only outside this repository or in local/, the folder
that git ignores, and refuses anywhere else in the repository. It changes nothing in Azure.

    python tools/pilot-feasibility.py --scope /subscriptions/<id> --month 2026-09 --out local/records/feasibility.json
    python tools/pilot-feasibility.py --scope ... --month 2026-09 --file export.csv --out ...

Routes for the per-resource lines:
    details-api  the Cost Details API (Enterprise Agreement and Microsoft Customer Agreement; not management groups)
    file         a CSV that the estate owner already has: an export (its columns or the FOCUS columns), or a
                 pay-as-you-go usage download. The lines need a resource column and a currency column

The scope is never taken from the CLI's default subscription: name it. Calls use a token from `az account
get-access-token`, which is never printed or written, and it is sent only to management.azure.com: a
download link (which carries a signature) is fetched without it, and no message repeats a link's query string.
Run the tests with `python -m unittest discover -s tools/tests`.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ARM = "https://management.azure.com"
DETAILS_API = "2022-05-01"
QUERY_API = "2023-11-01"
DEFAULT_TOLERANCE_PCT = 1.0
UNASSIGNED_WARNING_SHARE = 0.5
CLOSE_AFTER_DAYS = 5
MAX_QUERY_PAGES = 50
ROOT = Path(__file__).resolve().parent.parent

# Column names are compared lower-case with everything but letters and digits removed. The last name of each
# group is the FOCUS name (BilledCost is the actual cost that the Query API calls ActualCost).
ALIASES = {
    "cost": ("costinbillingcurrency", "cost", "pretaxcost", "billedcost"),
    "currency": ("billingcurrencycode", "billingcurrency", "currency"),
    "resource": ("resourceid", "instanceid", "instancename"),
    "payg": ("paygcostinbillingcurrency", "paygcost", "listcost"),
    "effective_price": ("effectiveprice", "xeffectiveunitprice"),
    "unit_price": ("unitprice",),
    "payg_price": ("paygprice", "listunitprice"),
    "pricing_model": ("pricingmodel", "pricingcategory"),
    "charge_type": ("chargetype", "chargecategory"),
    "benefit": ("benefitname", "commitmentdiscountname"),
}

SCOPE = re.compile(
    r"^/(subscriptions/[0-9a-fA-F-]{36}(/resourceGroups/[^/]+)?"
    r"|providers/Microsoft\.Billing/(departments|enrollmentAccounts)/[^/]+"
    r"|providers/Microsoft\.Billing/billingAccounts/[^/]+"
    r"(/(billingProfiles/[^/]+(/invoiceSections/[^/]+)?|departments/[^/]+|enrollmentAccounts/[^/]+|customers/[^/]+))?)$"
)


def clean(text) -> str:
    """Take the query string off every link and any signature out of a message, so that an error cannot leak a download link."""
    text = re.sub(r"(https?://[^\s\"'<>?]+)\?[^\s\"'<>]*", r"\1", str(text))
    return re.sub(r"(?i)\bsig=[^&\s\"'<>]+", "sig=removed", text)


class Problem(Exception):
    """Something the person running the tool can fix; printed without a trace and without a link's query string."""

    def __init__(self, message):
        super().__init__(clean(message))


class Transport:
    """The only place that talks to the network, so that tests can replace it."""

    def __init__(self, token_command=None, sleep=time.sleep, attempts=3):
        self.token_command = token_command or [shutil.which("az") or "az", "account", "get-access-token", "--resource", ARM,
                                               "--query", "accessToken", "-o", "tsv"]
        self.sleep, self.attempts, self._token = sleep, attempts, None

    def token(self) -> str:
        if self._token is None:
            try:
                done = subprocess.run(self.token_command, capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.TimeoutExpired) as e:
                raise Problem(f"could not run the Azure CLI to get a token: {e}")
            if done.returncode != 0 or not done.stdout.strip():
                raise Problem("the Azure CLI gave no token: run `az login` with an account that holds the read-only roles")
            self._token = done.stdout.strip()
        return self._token

    def request(self, method: str, url: str, body: dict | None = None, *, auth: bool = True):
        """Returns (status, headers, bytes). Retries 429 and 5xx, waiting for the longest retry-after.

        The token goes only to management.azure.com; every other link must be https and gets no token."""
        if auth and url != ARM and not url.startswith(ARM + "/"):
            raise Problem("refusing to send the token to a host other than management.azure.com")
        if not url.startswith("https://"):
            raise Problem("refusing a link that is not https")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        for attempt in range(1, self.attempts + 1):
            headers = {"Content-Type": "application/json"} if data else {}
            if auth:
                headers["Authorization"] = f"Bearer {self.token()}"
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=300) as response:
                    return response.status, dict(response.headers.items()), response.read()
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < self.attempts:
                    waits = [float(v) for k, v in e.headers.items() if "retry-after" in k.lower() and str(v).replace(".", "").isdigit()]
                    self.sleep(min(max(waits or [2.0 ** attempt]), 120.0))
                    continue
                return e.code, dict(e.headers.items()), e.read()
            except urllib.error.URLError as e:
                raise Problem(f"could not reach {url.split('?')[0]}: {e}")
        raise Problem("too many retries")


def month_bounds(month: str, today: dt.date | None = None) -> tuple[str, str]:
    """First and last day of a closed month (YYYY-MM). A month counts as closed from the sixth day after it ends:
    Azure closes a billing period typically up to 72 hours after it ends, and usage charges can change until the fifth day.
    That fits an Enterprise Agreement, whose billing period is the calendar month; for another cycle, name the month
    that matches the period's own end date."""
    today = today or dt.date.today()
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise Problem("--month is YYYY-MM")
    year, number = int(month[:4]), int(month[5:])
    if not 1 <= number <= 12:
        raise Problem("--month is YYYY-MM")
    first = dt.date(year, number, 1)
    last = (dt.date(year + (number == 12), number % 12 + 1, 1)) - dt.timedelta(days=1)
    if today <= last + dt.timedelta(days=CLOSE_AFTER_DAYS):
        raise Problem("the month is not closed: charges can change until the fifth day after it ends, so use it from the sixth day")
    return first.isoformat(), last.isoformat()


def check_scope(scope: str) -> str:
    scope = scope.rstrip("/")
    if not SCOPE.match(scope):
        raise Problem("--scope is a subscription, a resource group or a billing scope (billing account, billing profile, "
                      "invoice section, department, enrollment account or customer), for example /subscriptions/<id>")
    return scope


def query_total(transport: Transport, scope: str, first: str, last: str) -> dict[str, float]:
    """The actual cost Cost Management shows for the scope and month, per currency. Follows every page."""
    body = {"type": "ActualCost", "timeframe": "Custom",
            "timePeriod": {"from": f"{first}T00:00:00+00:00", "to": f"{last}T23:59:59+00:00"},
            "dataset": {"granularity": "None", "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}}}}
    url = f"{ARM}{scope}/providers/Microsoft.CostManagement/query?api-version={QUERY_API}"
    totals: dict[str, float] = {}
    for _page in range(MAX_QUERY_PAGES):
        status, _, raw = transport.request("POST", url, body)
        if status == 403:
            raise Problem("403 from Cost Management: the signed-in account needs Cost Management Reader on the scope")
        if status == 204:
            return totals
        if status != 200:
            raise Problem(f"Cost Management answered {status}: {raw.decode('utf-8', 'replace')[:300]}")
        props = json.loads(raw)["properties"]
        names = [c["name"].lower() for c in props["columns"]]
        cost_i = names.index("cost") if "cost" in names else names.index("pretaxcost")
        cur_i = names.index("currency") if "currency" in names else None
        for row in props["rows"]:
            currency = row[cur_i] if cur_i is not None else "unknown"
            totals[currency] = totals.get(currency, 0.0) + float(row[cost_i])
        url = props.get("nextLink")
        if not url:
            return totals
    raise Problem(f"Cost Management returned more than {MAX_QUERY_PAGES} pages of totals")


def _operation_state(manifest: dict | None) -> None:
    """Stop at once on the two end states of a report that is not coming."""
    state = (manifest or {}).get("status")
    if state == "NoDataFound":
        raise Problem("the Cost Details API found no cost data for this scope and month")
    if state == "Failed":
        raise Problem("the Cost Details API reported that the report failed: try again, or use --file with an export")


def details_api_csv(transport: Transport, scope: str, first: str, last: str, *, poll_limit: int = 40) -> str:
    """Request the Cost Details report for the month, poll for it and return the CSV text of all blobs."""
    url = f"{ARM}{scope}/providers/Microsoft.CostManagement/generateCostDetailsReport?api-version={DETAILS_API}"
    status, headers, raw = transport.request("POST", url, {"metric": "ActualCost", "timePeriod": {"start": first, "end": last}})
    if status in (400, 404):
        raise Problem("the Cost Details API does not serve this scope (it needs an Enterprise Agreement or a Microsoft Customer "
                      f"Agreement, and no management group); use --file with an export or a usage download. Answer: {raw.decode('utf-8', 'replace')[:200]}")
    if status == 403:
        raise Problem("403 from the Cost Details API: the signed-in account needs read access to cost on the scope")
    if status == 204:
        raise Problem("the Cost Details API found no cost data for this scope and month")
    if status not in (200, 202):
        raise Problem(f"the Cost Details API answered {status}: {raw.decode('utf-8', 'replace')[:300]}")
    lowered = {k.lower(): v for k, v in headers.items()}
    manifest = json.loads(raw) if status == 200 and raw else None
    _operation_state(manifest)
    location = lowered.get("location")
    waited = 0
    while manifest is None or manifest.get("status") != "Completed":
        if not location:
            raise Problem("the Cost Details API gave no link to poll")
        waited += 1
        if waited > poll_limit:
            raise Problem("the report was not ready in time: try again later")
        transport.sleep(float(lowered.get("retry-after", 10)))
        status, headers, raw = transport.request("GET", location)
        lowered = {k.lower(): v for k, v in headers.items()}
        if status == 204:
            raise Problem("the Cost Details API found no cost data for this scope and month")
        if status not in (200, 202):
            raise Problem(f"polling answered {status}: {raw.decode('utf-8', 'replace')[:300]}")
        manifest = json.loads(raw) if status == 200 and raw else None
        _operation_state(manifest)
    parts = []
    for blob in manifest["manifest"]["blobs"]:
        status, _, content = transport.request("GET", blob["blobLink"], auth=False)
        if status != 200:
            raise Problem(f"a report part could not be downloaded ({status})")
        if content[:2] == b"\x1f\x8b":
            content = gzip.decompress(content)
        parts.append(content.decode("utf-8-sig"))
    if not parts:
        return ""
    head, *rest = parts[0].splitlines(keepends=True)
    body = "".join(rest) + "".join("".join(p.splitlines(keepends=True)[1:]) for p in parts[1:])
    return head + body


def _column(header: list[str], key: str) -> int | None:
    lowered = [re.sub(r"[^a-z0-9]", "", h.lower()) for h in header]
    for alias in ALIASES[key]:
        if alias in lowered:
            return lowered.index(alias)
    return None


def read_lines(csv_text: str) -> dict:
    """Totals and shares from the CSV of bill lines. Raises Problem when the cost, the currency or the resource column is missing."""
    rows = list(csv.reader(io.StringIO(csv_text)))
    if len(rows) < 2:
        raise Problem("the file holds no bill lines")
    header, body = rows[0], rows[1:]
    index = {key: _column(header, key) for key in ALIASES}
    if index["cost"] is None:
        raise Problem("no cost column (costInBillingCurrency, Cost, PreTaxCost or BilledCost) in the lines")
    if index["currency"] is None:
        raise Problem("no currency column (BillingCurrencyCode or BillingCurrency): totals cannot be reconciled without one")
    if index["resource"] is None:
        raise Problem("no resource column (ResourceId or InstanceId): these are not bill lines per resource")
    totals: dict[str, float] = {}
    unassigned = 0.0
    resources: set[str] = set()
    by_charge: dict[str, float] = {}
    by_pricing: dict[str, float] = {}
    payg = effective = 0.0
    benefit_cost = 0.0
    discounted = lines_with_prices = 0
    for number, row in enumerate(body, start=2):
        if not row or len(row) < len(header):
            continue
        try:
            cost = float(row[index["cost"]] or 0)
            currency = row[index["currency"]]
            resource = row[index["resource"]].strip().lower()
            if index["payg"] is not None and row[index["payg"]]:
                payg += float(row[index["payg"]])
                effective += cost
            if index["effective_price"] is not None and index["payg_price"] is not None and row[index["effective_price"]] and row[index["payg_price"]]:
                lines_with_prices += 1
                if float(row[index["effective_price"]]) < float(row[index["payg_price"]]) - 1e-9:
                    discounted += 1
        except ValueError:
            raise Problem(f"line {number}: a cost or price is not a number")
        totals[currency] = totals.get(currency, 0.0) + cost
        if resource:
            resources.add(resource)
        else:
            unassigned += cost
        if index["charge_type"] is not None:
            by_charge[row[index["charge_type"]] or "unknown"] = by_charge.get(row[index["charge_type"]] or "unknown", 0.0) + cost
        if index["pricing_model"] is not None:
            by_pricing[row[index["pricing_model"]] or "unknown"] = by_pricing.get(row[index["pricing_model"]] or "unknown", 0.0) + cost
        if index["benefit"] is not None and row[index["benefit"]].strip():
            benefit_cost += cost
    return {
        "lines": len(body), "resources": len(resources), "totals": totals, "unassigned_cost": unassigned,
        "by_charge_type": by_charge, "by_pricing_model": by_pricing,
        "columns_found": sorted(k for k, v in index.items() if v is not None),
        "price_evidence": {
            "effective_to_payg_ratio": (effective / payg) if payg else None,
            "lines_priced_below_payg": discounted, "lines_with_both_prices": lines_with_prices,
            "cost_with_a_benefit": benefit_cost,
        },
    }


def reconcile(lines_totals: dict[str, float], query_totals: dict[str, float], tolerance_pct: float) -> dict:
    """Compare the two totals per currency; passes only when there is one currency and it is inside the tolerance."""
    currencies = sorted(set(lines_totals) | set(query_totals))
    if len(currencies) != 1:
        return {"pass": False, "reason": f"more than one currency or none: {currencies}", "currencies": currencies}
    currency = currencies[0]
    lines, shown = lines_totals.get(currency, 0.0), query_totals.get(currency, 0.0)
    difference = abs(lines - shown)
    pct = (difference / abs(shown) * 100) if shown else (0.0 if lines == 0 else float("inf"))
    return {"pass": pct <= tolerance_pct, "currency": currency, "lines_total": round(lines, 2),
            "cost_management_total": round(shown, 2), "difference": round(difference, 2),
            "difference_pct": None if pct == float("inf") else round(pct, 4), "tolerance_pct": tolerance_pct}


def price_basis_evidence(stats: dict) -> list[str]:
    """What the lines say about whose rates the figures use; a person writes the basis down."""
    notes = []
    ev = stats["price_evidence"]
    if ev["effective_to_payg_ratio"] is not None:
        notes.append(f"cost is {ev['effective_to_payg_ratio']:.0%} of the pay-as-you-go cost of the same usage")
    if ev["lines_with_both_prices"]:
        notes.append(f"{ev['lines_priced_below_payg']} of {ev['lines_with_both_prices']} lines have an effective price below the pay-as-you-go price")
    if stats["by_pricing_model"]:
        notes.append("cost by pricing model: " + ", ".join(f"{k} {v:,.0f}" for k, v in sorted(stats["by_pricing_model"].items())))
    if ev["cost_with_a_benefit"]:
        notes.append(f"{ev['cost_with_a_benefit']:,.0f} of cost carries a benefit (reservation, savings plan or hybrid benefit)")
    if not notes:
        notes.append("the lines carry no price columns: the basis cannot be read from them")
    return notes


def build_record(scope: str, month: str, route: str, stats: dict, query: dict[str, float], tolerance: float) -> dict:
    result = reconcile(stats["totals"], query, tolerance)
    unassigned = stats["unassigned_cost"]
    total = sum(stats["totals"].values())
    share = round(unassigned / total, 4) if total else None
    warnings = []
    if share is not None and share > UNASSIGNED_WARNING_SHARE:
        warnings.append(f"{share:.0%} of the cost is on lines with no resource id: a person decides whether this is a per-resource bill path")
    return {
        "check": "C13, first stage", "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "scope": scope, "month": month, "route": route,
        "reconciliation": result,
        "lines": {"count": stats["lines"], "distinct_resources": stats["resources"],
                  "unassigned_cost": round(unassigned, 2),
                  "unassigned_share": share,
                  "cost_by_charge_type": {k: round(v, 2) for k, v in stats["by_charge_type"].items()},
                  "columns_found": stats["columns_found"]},
        "price_basis_evidence": price_basis_evidence(stats),
        "warnings": warnings,
        "to_confirm_by_name": {
            "price_basis": "a person writes: contracted, billed or list (docs/design/14-agreements-and-access.md, the price order)",
            "pilot_owner": None, "access": None, "hub": None, "region": None, "model_quota": None,
        },
        "passed_by_the_tool": bool(result["pass"] and stats["resources"] > 0),
        "note": "The Query API gives totals only and does not count as a per-resource bill path. This record names the estate: keep it outside the repository or in local/, which git ignores.",
    }


def git_ignores(path: Path) -> bool:
    """True when git, asked in this repository, ignores the path. What it cannot confirm counts as not ignored."""
    git = shutil.which("git")
    if not git:
        return False
    try:
        relative = path.resolve().relative_to(ROOT).as_posix()
        done = subprocess.run([git, "-C", str(ROOT), "check-ignore", "-q", "--", relative], capture_output=True, timeout=30)
    except (ValueError, OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def refuse_where_git_tracks(out: Path, ignored=git_ignores) -> None:
    """The record names the estate: it goes outside the repository, or into local/, which git ignores."""
    target = out.resolve()
    try:
        target.relative_to(ROOT)
    except ValueError:
        return
    try:
        target.relative_to(ROOT / "local")
    except ValueError:
        raise Problem("--out is inside this repository: the record names the estate, so write it in local/ (git ignores it) or outside the repository") from None
    if not ignored(target):
        raise Problem("--out is in local/, but git does not ignore it: add /local/ to .gitignore first")


def run(args, transport: Transport | None = None, today: dt.date | None = None, ignored=git_ignores) -> int:
    transport = transport or Transport()
    scope = check_scope(args.scope)
    first, last = month_bounds(args.month, today)
    out = Path(args.out)
    refuse_where_git_tracks(out, ignored)
    if args.file:
        csv_text, route = Path(args.file).read_text(encoding="utf-8-sig"), "file"
    else:
        csv_text, route = details_api_csv(transport, scope, first, last), "details-api"
    stats = read_lines(csv_text)
    query = query_total(transport, scope, first, last)
    record = build_record(scope, args.month, route, stats, query, args.tolerance_pct)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    rec = record["reconciliation"]
    print(f"{'PASS' if record['passed_by_the_tool'] else 'NOT PASSED'}: {record['lines']['count']} lines, "
          f"{record['lines']['distinct_resources']} resources, lines {rec.get('lines_total')} against Cost Management "
          f"{rec.get('cost_management_total')} {rec.get('currency', '')} (difference {rec.get('difference_pct')} %, tolerance {args.tolerance_pct} %).")
    for note in record["price_basis_evidence"]:
        print(f"  price basis evidence: {note}")
    for warning in record["warnings"]:
        print(f"  WARNING: {warning}")
    print(f"Record written to {out}. A person still writes the price basis and names the owner, access, hub, region and quota.")
    return 0 if record["passed_by_the_tool"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scope")
    parser.add_argument("--month")
    parser.add_argument("--file", help="a CSV of bill lines instead of the Cost Details API")
    parser.add_argument("--out", help="where to write the record: outside this repository, or in local/")
    parser.add_argument("--tolerance-pct", type=float, default=DEFAULT_TOLERANCE_PCT)
    args = parser.parse_args(argv)
    if not (args.scope and args.month and args.out):
        parser.error("--scope, --month and --out are required")
    try:
        return run(args)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
